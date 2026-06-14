"""
Scan US mid-cap equities for an active "failed bearish setup" and rank the
survivors by a value-tilted composite of price-to-book and fundamentals.

Bearish setup (on the chosen timeframe, weekly by default):
  1. fresh low   : close < min(close[-lookback:-1])
  2. broke 50SMA : close < SMA_short AND SMA_short < SMA_long
  3. broke support: close < min(low[-lookback:-1])

Failed setup (the bullish trigger):
  within `max_bars_to_failure` bars after the setup bar, a close prints
  above the setup bar's high -- the breakdown is reclaimed.

Active filter: only keep tickers whose failure bar is within the last
`--active-bars` bars.

Ranking: z-score composite (higher is better)
  0.35 * -z(P/B) + 0.25 * z(ROE) + 0.15 * -z(D/E)
  + 0.15 * z(profit margin) + 0.10 * z(revenue growth)
with a hard floor of priceToBook > 0 and returnOnEquity > 0.
"""

import argparse
import time
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf


US_EXCHANGES = {"NYQ", "NMS", "NGM", "NCM", "ASE", "BATS"}
US_ETF_EXCHANGES = {"PCX", "NYQ", "NMS", "NGM", "NCM", "ASE", "BATS"}  # PCX = NYSE Arca, primary US ETF venue
BR_EXCHANGES = {"SAO"}  # Brazil B3 / São Paulo

EU_PRIMARY_EXCHANGES = {
    "LSE",  # London .L
    "GER",  # Xetra .DE
    "PAR",  # Paris .PA
    "AMS",  # Amsterdam .AS
    "MIL",  # Milan .MI
    "MCE",  # Madrid .MC
    "STO",  # Stockholm .ST
    "HEL",  # Helsinki .HE
    "CPH",  # Copenhagen .CO
    "OSL",  # Oslo .OL
    "VIE",  # Vienna .VI
    "EBS",  # SIX Swiss .SW
    "BRU",  # Brussels .BR
    "IRE",  # Dublin .IR
    "LIS",  # Lisbon .LS
    "ATH",  # Athens .AT
    "WSE",  # Warsaw .WA
    "PRA",  # Prague .PR
}

EU_COUNTRIES = [
    "United Kingdom", "Germany", "France", "Italy", "Spain",
    "Netherlands", "Switzerland", "Sweden", "Belgium", "Norway",
    "Denmark", "Finland", "Ireland", "Austria", "Portugal",
    "Greece", "Poland", "Czech Republic", "Hungary", "Luxembourg",
]


# Wikipedia index constituent universes. Cached to disk after first fetch.
_WIKI_INDEX_SPEC = {
    # name : (wikipedia_url, suffix_for_yfinance, expected_row_count_min)
    "wiki-spx500":  ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "",   400),
    "wiki-ndx":     ("https://en.wikipedia.org/wiki/Nasdaq-100",                  "",   90),
    "wiki-djia":    ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",  "",   25),
    "wiki-ftse100": ("https://en.wikipedia.org/wiki/FTSE_100_Index",              ".L", 90),
    "wiki-ftse250": ("https://en.wikipedia.org/wiki/FTSE_250_Index",              ".L", 200),
    "wiki-dax":     ("https://en.wikipedia.org/wiki/DAX",                         ".DE", 35),
    "wiki-mdax":    ("https://en.wikipedia.org/wiki/MDAX",                        ".DE", 40),
    "wiki-cac40":   ("https://en.wikipedia.org/wiki/CAC_40",                      ".PA", 35),
    "wiki-mib":     ("https://en.wikipedia.org/wiki/FTSE_MIB",                    ".MI", 35),
    "wiki-aex":     ("https://en.wikipedia.org/wiki/AEX_index",                   ".AS", 20),
    "wiki-omxs30":  ("https://en.wikipedia.org/wiki/OMX_Stockholm_30",            ".ST", 25),
    "wiki-stoxx50": ("https://en.wikipedia.org/wiki/EURO_STOXX_50",               "",    40),
    "wiki-wig20":   ("https://en.wikipedia.org/wiki/WIG20",                       ".WA", 15),
    "wiki-wig40":   ("https://en.wikipedia.org/wiki/MWIG40",                      ".WA", 30),
    "wiki-px":      ("https://en.wikipedia.org/wiki/Prague_Stock_Exchange",       ".PR", 5),
    "wiki-bux":     ("https://en.wikipedia.org/wiki/Budapest_Stock_Exchange",     ".BD", 5),
    "wiki-asx50":   ("https://en.wikipedia.org/wiki/S%26P/ASX_50",                ".AX", 40),
    "wiki-asx200":  ("https://en.wikipedia.org/wiki/S%26P/ASX_200",               ".AX", 150),
    "wiki-tsx60":   ("https://en.wikipedia.org/wiki/S%26P/TSX_60",                ".TO", 50),
    "wiki-nifty50": ("https://en.wikipedia.org/wiki/NIFTY_50",                    ".NS", 40),
    "wiki-nikkei225": ("https://en.wikipedia.org/wiki/Nikkei_225",                ".T", 180),
    "wiki-hsi":     ("https://en.wikipedia.org/wiki/Hang_Seng_Index",             ".HK", 50),
    "wiki-kospi200":("https://en.wikipedia.org/wiki/KOSPI_200",                   ".KS", 150),
    "wiki-ibovespa":("https://en.wikipedia.org/wiki/%C3%8Dndice_Bovespa",         ".SA", 60),
    "wiki-jpx400":  ("https://en.wikipedia.org/wiki/JPX-Nikkei_Index_400",        ".T", 300),
    "wiki-r1k":     ("https://en.wikipedia.org/wiki/Russell_1000_Index",          "",    900),
    "wiki-aim100":  ("https://www.hl.co.uk/shares/stock-market-summary/ftse-aim-100", ".L", 90),
}


def _wiki_union_universe():
    """Union of all working Wikipedia index members, deduplicated."""
    frames = []
    for name in _WIKI_INDEX_SPEC.keys():
        try:
            frames.append(_fetch_wiki_index(name))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="first")]
    # Drop obviously malformed tickers
    df = df[~df.index.astype(str).str.startswith("SEHK")]
    df = df[df.index.astype(str).str.len() <= 20]
    return df

_WIKI_CACHE_DIR = "/tmp/cyclepapa_wiki"
# Durable repo-tracked copy of the Wikipedia index lists.
_WIKI_DURABLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wiki")


def _fetch_wiki_index(name):
    """Fetch a Wikipedia index constituent table, cache locally, return DataFrame.

    Lookup order: /tmp working copy -> data/wiki/ durable copy (auto-inflated
    to /tmp) -> fresh HTTP fetch (then mirrored to both).
    """
    import os
    import requests
    import io
    spec = _WIKI_INDEX_SPEC[name]
    url, suffix, _min = spec
    os.makedirs(_WIKI_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(_WIKI_CACHE_DIR, f"{name}.csv")
    durable_path = os.path.join(_WIKI_DURABLE_DIR, f"{name}.csv")
    # Hydrate working from durable if working missing
    if not os.path.exists(cache_path) and os.path.exists(durable_path):
        try:
            import shutil
            shutil.copy(durable_path, cache_path)
        except Exception:
            pass
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, index_col=0)
            if len(df) >= _min:
                return df
        except Exception:
            pass
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    r = requests.get(url, headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}, timeout=20)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    chosen = None
    # Allow larger constituent tables (e.g., Russell 1000 has ~1003).
    upper_size = max(1500, _min * 2)
    for t in tables:
        cols = [str(c).strip() for c in t.columns]
        has_sym = any(c in ("Symbol", "Ticker", "Ticker symbol", "Code", "EPIC") or
                      ("ymbol" in c) or ("icker" in c) for c in cols)
        if has_sym and _min <= len(t) <= upper_size:
            chosen = t
            break
    if chosen is None:
        raise RuntimeError(f"{name}: could not locate constituent table among "
                           f"{len(tables)} tables (sizes={[len(t) for t in tables[:6]]})")
    cols = [str(c) for c in chosen.columns]
    sym_col = next((c for c in cols if c in ("Symbol", "Ticker", "Ticker symbol", "Code", "EPIC")), None)
    if sym_col is None:
        sym_col = next((c for c in cols if "ymbol" in c or "icker" in c), None)
    syms = chosen[sym_col].astype(str).str.strip()
    # Clean ticker strings (remove dots from non-suffix dots, etc.)
    if suffix:
        syms = syms.apply(lambda s: s if (s.endswith(suffix) or "." in s) else s + suffix)
    name_col = next((c for c in cols if c in ("Security", "Company", "Name", "Company name")), None)
    sector_col = next((c for c in cols if "ector" in c or "ndustry" in c), None)
    out = pd.DataFrame({"name": chosen[name_col] if name_col else syms.values,
                         "sector": chosen[sector_col] if sector_col else None,
                         "exchange": suffix.replace(".", "") if suffix else "US",
                         "_index": name},
                        index=syms.values)
    out = out[~out.index.duplicated(keep="first")]
    out.to_csv(cache_path)
    # Mirror to durable repo-tracked copy
    try:
        os.makedirs(_WIKI_DURABLE_DIR, exist_ok=True)
        out.to_csv(durable_path)
    except Exception:
        pass
    return out


def get_universe(name, sector=None, industry_group=None, industry=None, theme=None):
    # Wikipedia-based index universes (S&P 500, NDX, FTSE, DAX, MDAX, CAC,
    # MIB, AEX, OMXS30, STOXX 50). Cached to /tmp/cyclepapa_wiki/ after
    # first fetch. Useful for guaranteed coverage of named index members
    # plus those missing from financedatabase's classification.
    if name in _WIKI_INDEX_SPEC:
        return _fetch_wiki_index(name)
    if name == "wiki-union":
        return _wiki_union_universe()

    import financedatabase as fd

    equities = fd.Equities()
    if name == "us-mid":
        df = equities.select(country="United States", market_cap="Mid Cap")
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "us-micro":
        df = equities.select(country="United States", market_cap="Micro Cap")
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "us-smid":
        frames = []
        for cap in ["Small Cap", "Mid Cap"]:
            try:
                sub = equities.select(country="United States", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "us-all":
        frames = []
        for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country="United States", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df

    # US per-cap variants (us-mid/us-micro/us-smid/us-midlarge already exist
    # above; add us-large and us-nano for completeness).
    if name == "us-large":
        frames = []
        for cap in ["Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country="United States", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "us-nano":
        sub = equities.select(country="United States", market_cap="Nano Cap")
        sub = sub[sub["exchange"].isin(US_EXCHANGES)]
        return sub
    if name == "uk-smid":
        frames = []
        for cap in ["Small Cap", "Mid Cap"]:
            try:
                sub = equities.select(country="United Kingdom", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "LSE"]
        return df
    if name == "uk-midlarge":
        frames = []
        for cap in ["Mid Cap", "Large Cap"]:
            try:
                sub = equities.select(country="United Kingdom", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "LSE"]
        return df
    if name == "us-midlarge":
        frames = []
        for cap in ["Mid Cap", "Large Cap"]:
            try:
                sub = equities.select(country="United States", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(US_EXCHANGES)]
        return df
    if name == "it-all":
        frames = []
        for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country="Italy", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "MIL"]
        return df
    if name == "de-all":
        frames = []
        for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country="Germany", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "GER"]
        return df
    if name == "eu-smid":
        frames = []
        for country in EU_COUNTRIES:
            for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap"]:
                try:
                    sub = equities.select(country=country, market_cap=cap)
                    if len(sub):
                        frames.append(sub)
                except Exception:
                    continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(EU_PRIMARY_EXCHANGES)]
        return df
    if name == "uk-all":
        frames = []
        for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country="United Kingdom", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"] == "LSE"]
        return df
    if name == "br-all":
        frames = []
        for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country="Brazil", market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(BR_EXCHANGES)]
        return df

    # --- Single-country wideners (all caps, primary listings only) ---
    _COUNTRY_SPEC = {
        "fr-all": ("France",        {"PAR"}),
        "ch-all": ("Switzerland",   {"EBS"}),
        "es-all": ("Spain",         {"MCE"}),
        "nl-all": ("Netherlands",   {"AMS"}),
        "se-all": ("Sweden",        {"STO"}),
        "be-all": ("Belgium",       {"BRU"}),
        "no-all": ("Norway",        {"OSL"}),
        "dk-all": ("Denmark",       {"CPH"}),
        "fi-all": ("Finland",       {"HEL"}),
        "ie-all": ("Ireland",       {"ISE"}),
        "pt-all": ("Portugal",      {"LIS"}),
        "at-all": ("Austria",       {"VIE"}),
        "gr-all": ("Greece",        {"ATH"}),
        "jp-all": ("Japan",         {"JPX"}),  # Tokyo Stock Exchange
        "au-all": ("Australia",     {"ASX"}),
        "ca-all": ("Canada",        {"TOR", "VAN", "CNQ"}),  # TSX, TSXV, CSE
        "in-all": ("India",         {"BSE", "NSE"}),  # BSE + NSE
        "hk-all": ("Hong Kong",     {"HKG"}),
        "sg-all": ("Singapore",     {"SES"}),
        "cn-all": ("China",         {"SHH", "SHZ"}),  # Shanghai + Shenzhen
        "kr-all": ("South Korea",   {"KSC", "KOE"}),  # KOSPI + KOSDAQ
        "tw-all": ("Taiwan",        {"TAI", "TWO"}),
        "mx-all": ("Mexico",        {"MEX"}),
        "za-all": ("South Africa",  {"JNB"}),
        "pl-all": ("Poland",        {"WSE"}),  # Warsaw
        "cz-all": ("Czech Republic", {"PRA"}),  # Prague
        "hu-all": ("Hungary",       {"BUD"}),  # Budapest
        "lu-all": ("Luxembourg",    {"LUX"}),  # Luxembourg
        # New: 9 additional country universes (Q4 expansion)
        "il-all": ("Israel",        {"TLV"}),  # Tel Aviv (.TA)
        "th-all": ("Thailand",      {"SET"}),  # SET (.BK)
        "id-all": ("Indonesia",     {"JKT"}),  # IDX (.JK)
        "my-all": ("Malaysia",      {"KLS"}),  # Bursa (.KL)
        "tr-all": ("Turkey",        {"IST"}),  # BIST (.IS)
        "sa-all": ("Saudi Arabia",  {"SAU"}),  # Tadawul (.SR)
        "ar-all": ("Argentina",     {"BUE"}),  # BCBA (.BA)
        "cl-all": ("Chile",         {"SGO"}),  # Santiago (.SN)
        "nz-all": ("New Zealand",   {"NZE"}),  # NZX (.NZ)
    }
    if name in _COUNTRY_SPEC:
        country, allowed_exchanges = _COUNTRY_SPEC[name]
        frames = []
        for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
            try:
                sub = equities.select(country=country, market_cap=cap)
                if len(sub):
                    frames.append(sub)
            except Exception:
                continue
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(allowed_exchanges)]
        return df

    # --- EU-all = eu-smid + EU large/mega caps (catches Bayer/ASML/SAP/Nestle) ---
    if name == "eu-all":
        frames = []
        for country in EU_COUNTRIES:
            for cap in ["Nano Cap", "Micro Cap", "Small Cap", "Mid Cap", "Large Cap", "Mega Cap"]:
                try:
                    sub = equities.select(country=country, market_cap=cap)
                    if len(sub):
                        frames.append(sub)
                except Exception:
                    continue
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(EU_PRIMARY_EXCHANGES)]
        return df

    # EU per-cap variants (aggregated across all EU countries, primary
    # exchanges only). Mirror the us-micro/-small/-mid/-large structure.
    _EU_CAP_SPEC = {
        "eu-nano":      ["Nano Cap"],
        "eu-micro":     ["Micro Cap"],
        "eu-small":     ["Small Cap"],
        "eu-mid":       ["Mid Cap"],
        "eu-midlarge":  ["Mid Cap", "Large Cap"],
        "eu-large":     ["Large Cap", "Mega Cap"],
    }
    if name in _EU_CAP_SPEC:
        caps = _EU_CAP_SPEC[name]
        frames = []
        for country in EU_COUNTRIES:
            for cap in caps:
                try:
                    sub = equities.select(country=country, market_cap=cap)
                    if len(sub):
                        frames.append(sub)
                except Exception:
                    continue
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        df = df[df["exchange"].isin(EU_PRIMARY_EXCHANGES)]
        return df

    # --- Global-all-developed-equities convenience aggregator ---
    if name == "global-all":
        sub_universes = ["us-all", "uk-all", "eu-all", "jp-all", "au-all",
                         "ca-all", "ch-all", "br-all"]
        frames = []
        for u in sub_universes:
            try:
                frames.append(get_universe(u))
            except Exception as e:
                print(f"  global-all: skip {u}: {e}")
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")]
        return df

    # --- ETF universes (fd.ETFs() instead of fd.Equities()) ---
    if name.endswith("-etfs"):
        try:
            etfs = fd.ETFs()
        except Exception as e:
            raise ValueError(f"financedatabase ETFs failed: {e}")
        df = etfs.select()
        if name == "us-etfs":
            df = df[df["exchange"].isin(US_ETF_EXCHANGES)]
        elif name == "uk-etfs":
            df = df[df["exchange"] == "LSE"]
        elif name == "de-etfs":
            df = df[df["exchange"] == "GER"]
        elif name == "it-etfs":
            df = df[df["exchange"] == "MIL"]
        elif name == "eu-etfs":
            df = df[df["exchange"].isin(EU_PRIMARY_EXCHANGES)]
        else:
            raise ValueError(f"unknown ETF universe: {name}")
        df = df[~df.index.duplicated(keep="first")]
        return df
    raise ValueError(f"unknown universe: {name}")


def apply_universe_filters(df, sector=None, industry_group=None, industry=None, theme=None):
    """Narrow a universe DataFrame by financedatabase metadata.

    sector / industry_group / industry: comma-separated list, case-insensitive.
    theme: text search across name + summary (uses fd.search-equivalent).
    """
    if df is None or len(df) == 0:
        return df
    if sector:
        wanted = [s.strip().lower() for s in sector.split(",")]
        df = df[df["sector"].fillna("").str.lower().isin(wanted)] if "sector" in df.columns else df
    if industry_group and "industry_group" in df.columns:
        wanted = [s.strip().lower() for s in industry_group.split(",")]
        df = df[df["industry_group"].fillna("").str.lower().isin(wanted)]
    if industry and "industry" in df.columns:
        wanted = [s.strip().lower() for s in industry.split(",")]
        df = df[df["industry"].fillna("").str.lower().isin(wanted)]
    if theme:
        keys = [k.strip().lower() for k in theme.split(",") if k.strip()]
        if "summary" in df.columns and keys:
            text = (df["name"].fillna("") + " " + df.get("summary", df["name"]).fillna("")).str.lower()
            mask = text.apply(lambda s: any(k in s for k in keys))
            df = df[mask]
    return df


def _extract_ticker_frame(data, ticker):
    if isinstance(data.columns, pd.MultiIndex):
        if ticker not in data.columns.get_level_values(0):
            return None
        sub = data[ticker].dropna(how="all")
    else:
        sub = data.dropna(how="all")
    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(sub.columns):
        return None
    return sub


def download_prices(tickers, timeframe, years, chunk_size=80, batch_sleep=20.0,
                    checkpoint_path=None):
    import pickle, os
    interval = "1wk" if timeframe == "weekly" else "1mo"
    period = f"{years}y"
    frames = {}
    done_tickers = set()
    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "rb") as f:
                state = pickle.load(f)
            if state.get("timeframe") == timeframe and state.get("years") == years:
                frames = state["frames"]
                done_tickers = set(state["done"])
                print(f"  resumed from checkpoint: {len(frames)} kept, {len(done_tickers)} already attempted")
        except Exception as e:
            print(f"  checkpoint load failed: {e}")
    todo = [t for t in tickers if t not in done_tickers]
    total = len(todo)
    n_batches = (total + chunk_size - 1) // chunk_size
    for i in range(0, total, chunk_size):
        batch_idx = i // chunk_size + 1
        chunk = todo[i : i + chunk_size]
        print(f"  batch {batch_idx}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} of {total} (kept so far: {len(frames)})")
        try:
            data = yf.download(
                chunk,
                period=period,
                interval=interval,
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            print(f"    batch failed: {e}")
            data = None
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    sub = _extract_ticker_frame(data, t)
                    if sub is not None and len(sub) >= 60:
                        frames[t] = sub
                except Exception:
                    continue
        done_tickers.update(chunk)
        if checkpoint_path:
            try:
                tmp = checkpoint_path + ".tmp"
                with open(tmp, "wb") as f:
                    pickle.dump({"timeframe": timeframe, "years": years,
                                 "frames": frames, "done": list(done_tickers)}, f)
                os.replace(tmp, checkpoint_path)
            except Exception as e:
                print(f"    checkpoint save failed: {e}")
        if batch_idx < n_batches:
            time.sleep(batch_sleep)
    return frames


def detect_failed_bearish_setup(
    df,
    lookback=10,
    sma_short=20,
    sma_long=50,
    max_bars_to_failure=5,
):
    if len(df) < sma_long + lookback + max_bars_to_failure:
        return None

    work = df.copy()
    work["sma_s"] = work["Close"].rolling(sma_short).mean()
    work["sma_l"] = work["Close"].rolling(sma_long).mean()
    work["prior_close_min"] = work["Close"].shift(1).rolling(lookback).min()
    work["prior_low_min"] = work["Low"].shift(1).rolling(lookback).min()

    trigger_mask = (
        (work["Close"] < work["prior_close_min"])
        & (work["Close"] < work["sma_s"])
        & (work["sma_s"] < work["sma_l"])
        & (work["Close"] < work["prior_low_min"])
    )
    trigger_mask = trigger_mask.fillna(False)
    triggers = work.index[trigger_mask]
    if len(triggers) == 0:
        return None

    last_trigger = triggers[-1]
    trigger_pos = work.index.get_loc(last_trigger)
    trigger_high = float(work.loc[last_trigger, "High"])
    trigger_low = float(work.loc[last_trigger, "Low"])

    end_pos = min(trigger_pos + 1 + max_bars_to_failure, len(work))
    window = work.iloc[trigger_pos + 1 : end_pos]
    failure = window[window["Close"] > trigger_high]
    if len(failure) == 0:
        return None
    failure_date = failure.index[0]

    return {
        "trigger_date": last_trigger,
        "trigger_high": trigger_high,
        "trigger_low": trigger_low,
        "failure_date": failure_date,
        "failure_close": float(work.loc[failure_date, "Close"]),
        "latest_close": float(work["Close"].iloc[-1]),
        "latest_date": work.index[-1],
    }


def fetch_fundamentals(tickers, base_sleep_s=1.0, max_retries=3):
    rows = []
    sleep_s = base_sleep_s
    rate_limited_streak = 0
    for i, t in enumerate(tickers, 1):
        if i % 10 == 0:
            print(f"  fundamentals {i}/{len(tickers)} (sleep={sleep_s:.1f}s)")
        info = {}
        for attempt in range(max_retries):
            try:
                info = yf.Ticker(t).info or {}
                rate_limited_streak = 0
                break
            except Exception as e:
                msg = str(e).lower()
                if "rate" in msg or "too many" in msg or "429" in msg:
                    rate_limited_streak += 1
                    wait = sleep_s * (2 ** attempt) + 2
                    print(f"    rate limited on {t}, waiting {wait:.0f}s (attempt {attempt + 1})")
                    time.sleep(wait)
                else:
                    break
        if rate_limited_streak >= 3:
            sleep_s = min(sleep_s * 1.5, 10.0)
        rows.append(
            {
                "Ticker": t,
                "priceToBook": info.get("priceToBook"),
                "trailingPE": info.get("trailingPE"),
                "forwardPE": info.get("forwardPE"),
                "enterpriseToEbitda": info.get("enterpriseToEbitda"),
                "enterpriseValue": info.get("enterpriseValue"),
                "returnOnEquity": info.get("returnOnEquity"),
                "debtToEquity": info.get("debtToEquity"),
                "profitMargins": info.get("profitMargins"),
                "revenueGrowth": info.get("revenueGrowth"),
                "marketCap": info.get("marketCap"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "shortName": info.get("shortName") or info.get("longName"),
            }
        )
        time.sleep(sleep_s)
    return pd.DataFrame(rows).set_index("Ticker")


def rank(df, quality=False):
    pb = pd.to_numeric(df["priceToBook"], errors="coerce")
    drop_mask = pb.notna() & (pb <= 0)
    out = df[~drop_mask].copy()
    if quality and not out.empty:
        roe = pd.to_numeric(out["returnOnEquity"], errors="coerce")
        margin = pd.to_numeric(out["profitMargins"], errors="coerce")
        de = pd.to_numeric(out["debtToEquity"], errors="coerce")
        growth = pd.to_numeric(out["revenueGrowth"], errors="coerce")
        keep = (
            (roe > 0.05)
            & (margin > 0)
            & (de.notna() & (de < 200))
            & (growth.notna() & (growth > -0.10))
        )
        n_before = len(out)
        out = out[keep]
        print(f"  quality filter: {len(out)}/{n_before} survive (ROE>5%, margin>0, D/E<200, growth>-10%)")
    if out.empty:
        return out

    def z(series, higher_better):
        s = pd.to_numeric(series, errors="coerce").astype(float)
        std = s.std(ddof=0)
        if std == 0 or np.isnan(std):
            return pd.Series(0.0, index=s.index)
        r = (s - s.mean()) / std
        r = r.fillna(0.0)
        return r if higher_better else -r

    out["z_pb"] = z(out["priceToBook"], higher_better=False)
    out["z_roe"] = z(out["returnOnEquity"], higher_better=True)
    out["z_de"] = z(out["debtToEquity"], higher_better=False)
    out["z_margin"] = z(out["profitMargins"], higher_better=True)
    out["z_growth"] = z(out["revenueGrowth"], higher_better=True)

    out["score"] = (
        0.35 * out["z_pb"]
        + 0.25 * out["z_roe"]
        + 0.15 * out["z_de"]
        + 0.15 * out["z_margin"]
        + 0.10 * out["z_growth"]
    )

    n_complete = out[["priceToBook", "returnOnEquity"]].notna().all(axis=1).sum()
    print(f"  {n_complete}/{len(out)} rows have full P/B + ROE; missing rows rank with z=0")

    return out.sort_values("score", ascending=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", choices=["weekly", "monthly"], default="weekly")
    parser.add_argument("--years", type=int, default=None, help="History length for price download (default: 5y weekly, 15y monthly)")
    parser.add_argument("--lookback", type=int, default=None, help="Bars for fresh-low / support lookback (default: 10 weekly, 6 monthly)")
    parser.add_argument("--sma-short", type=int, default=None, help="Short SMA bars (default: 20 weekly, 10 monthly)")
    parser.add_argument("--sma-long", type=int, default=None, help="Long SMA bars (default: 50 weekly, 20 monthly)")
    parser.add_argument("--max-bars-to-failure", type=int, default=None, help="(default: 5 weekly, 3 monthly)")
    parser.add_argument(
        "--active-bars",
        type=int,
        default=None,
        help="Failure trigger must be within the last N bars to count as active (default: 8 weekly, 4 monthly)",
    )
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--universe", choices=[
        "us-mid", "us-micro", "us-smid", "us-midlarge", "us-all",
        "uk-smid", "uk-midlarge", "uk-all",
        "eu-smid", "it-all", "de-all", "br-all",
        "us-etfs", "uk-etfs", "de-etfs", "it-etfs", "eu-etfs",
    ], default="us-mid")
    parser.add_argument("--sector", default=None,
                        help="Comma-separated sector(s) to keep (e.g. 'Information Technology,Health Care').")
    parser.add_argument("--industry-group", default=None, help="Comma-separated industry group(s).")
    parser.add_argument("--industry", default=None, help="Comma-separated industry/ies.")
    parser.add_argument("--theme", default=None,
                        help="Comma-separated keyword(s) - filter by text search across name+summary "
                             "(e.g. 'robotics,AI,quantum').")
    parser.add_argument("--quality", action="store_true",
                        help="Apply hard quality floor: ROE>5%, margin>0, D/E<200, rev_growth>-10% (drops NaN)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    if args.timeframe == "weekly":
        defaults = dict(years=5, lookback=10, sma_short=20, sma_long=50, max_bars_to_failure=5, active_bars=8)
    else:
        defaults = dict(years=15, lookback=6, sma_short=10, sma_long=20, max_bars_to_failure=3, active_bars=4)
    for k, v in defaults.items():
        cli = getattr(args, k)
        if cli is None:
            setattr(args, k, v)
    print(
        f"Params: timeframe={args.timeframe} years={args.years} lookback={args.lookback} "
        f"sma_short={args.sma_short} sma_long={args.sma_long} "
        f"max_bars_to_failure={args.max_bars_to_failure} active_bars={args.active_bars}"
    )

    print(f"Fetching {args.universe} universe from financedatabase...")
    universe = get_universe(args.universe)
    before_n = len(universe)
    universe = apply_universe_filters(
        universe,
        sector=args.sector,
        industry_group=args.industry_group,
        industry=args.industry,
        theme=args.theme,
    )
    if any([args.sector, args.industry_group, args.industry, args.theme]):
        print(f"  filters narrowed {before_n} -> {len(universe)} tickers")
    tickers = [t for t in universe.index.tolist() if isinstance(t, str) and t]
    print(f"  {len(tickers)} tickers")

    print(f"Downloading {args.timeframe} bars ({args.years}y)...")
    checkpoint_path = f"/tmp/cyclepapa_dl_{args.universe}_{args.timeframe}_{args.years}y.pkl"
    prices = download_prices(tickers, args.timeframe, args.years, checkpoint_path=checkpoint_path)
    print(f"  {len(prices)} tickers with usable data")

    print("Detecting failed bearish setups...")
    signals = {}
    for t, df in prices.items():
        sig = detect_failed_bearish_setup(
            df,
            lookback=args.lookback,
            sma_short=args.sma_short,
            sma_long=args.sma_long,
            max_bars_to_failure=args.max_bars_to_failure,
        )
        if sig is None:
            continue
        bars_since_failure = len(df.loc[sig["failure_date"] :]) - 1
        if bars_since_failure > args.active_bars:
            continue
        signals[t] = sig
    print(f"  {len(signals)} tickers with active failed bearish setup")

    if not signals:
        print("No signals.")
        return

    sig_df = pd.DataFrame.from_dict(signals, orient="index")
    sig_df.index.name = "Ticker"

    signals_path = (
        f"failed_bearish_signals_{args.universe}_{args.timeframe}_{datetime.today():%Y%m%d}.csv"
    )
    sig_df.to_csv(signals_path)
    print(f"Saved signals-only CSV: {signals_path}")

    print("Fetching fundamentals (rate-limit aware; this is slow)...")
    fundamentals = fetch_fundamentals(list(signals.keys()))
    combined = sig_df.join(fundamentals, how="left")

    ranked = rank(combined, quality=args.quality)
    if ranked.empty:
        print("No survivors after P/B filter.")
        return

    ranked["pct_from_failure"] = (
        (ranked["latest_close"] - ranked["failure_close"]) / ranked["failure_close"] * 100
    )

    display_cols = [
        "shortName",
        "sector",
        "priceToBook",
        "enterpriseToEbitda",
        "returnOnEquity",
        "debtToEquity",
        "profitMargins",
        "revenueGrowth",
        "trailingPE",
        "marketCap",
        "trigger_date",
        "failure_date",
        "pct_from_failure",
        "score",
    ]
    display_cols = [c for c in display_cols if c in ranked.columns]
    out = ranked[display_cols]

    out_path = (
        args.out
        or f"failed_bearish_{args.universe}_{args.timeframe}_{datetime.today():%Y%m%d}.csv"
    )
    out.to_csv(out_path)
    print(f"Saved: {out_path}")

    with pd.option_context("display.max_columns", None, "display.width", 200, "display.float_format", "{:.2f}".format):
        print(f"\n=== Top {args.top} by composite score ===")
        print(out.head(args.top).to_string())

        pb = pd.to_numeric(out["priceToBook"], errors="coerce")
        by_pb = out[pb > 0].sort_values("priceToBook", ascending=True)
        print(f"\n=== Top {args.top} cheapest by P/B ===")
        print(by_pb.head(args.top).to_string())

        if "enterpriseToEbitda" in out.columns:
            ev = pd.to_numeric(out["enterpriseToEbitda"], errors="coerce")
            by_ev = out[ev > 0].sort_values("enterpriseToEbitda", ascending=True)
            print(f"\n=== Top {args.top} cheapest by EV/EBITDA ===")
            print(by_ev.head(args.top).to_string())


if __name__ == "__main__":
    main()
