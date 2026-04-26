"""
Three-screen SMID stock picker.

Screen 1 - Relative-strength breakout: log(stock/index) at a new 52-week
           AND 12-month high.
Screen 2 - Qullamaggie-style volatility asymmetry (port of the Pine Script):
             monthly asymmetry near 50 (balanced base, coiled spring),
             weekly asymmetry rising AND above its EMA AND still "low"
             (i.e. just lifting off, not yet euphoric).
Screen 3 - Max-independent-set on the |weekly corr| > eps graph among
           survivors, greedy by composite RS-breakout score.

Usage: python3 screen.py [us|europe|uk]   (default: us)
"""

import io
import sys
import urllib.request
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Asymmetry tuning (matches Pine defaults).
ASYM_PERIOD = 14
ASYM_SMOOTH = 7
MONTHLY_ASYM_BAND = (45.0, 55.0)   # "near 50"
WEEKLY_ASYM_LOW_MAX = 60.0         # "preferably low"
WEEKLY_ASYM_RISING_BARS = 2        # last N bars all rising

CORR_EPS = 0.5
RS_LOOKBACK_W = 52
RS_LOOKBACK_M = 12

# iShares holdings CSV endpoints. The "fileName" param is just an echo;
# the product ID determines what fund is returned.
ISHARES_URL = (
    "https://www.ishares.com/us/products/{fid}/{slug}/1467271812596.ajax"
    "?fileType=csv&fileName={tag}_holdings&dataType=fund"
)

# Map iShares "Exchange" column to Yahoo Finance suffix. Cross-listed
# names sometimes need a different suffix; this catches the common ones.
EXCHANGE_TO_YAHOO = {
    "London Stock Exchange": ".L",
    "SIX Swiss Exchange": ".SW",
    "Euronext Amsterdam": ".AS",
    "Nyse Euronext - Euronext Amsterdam": ".AS",
    "Nyse Euronext - Euronext Paris": ".PA",
    "Euronext Paris": ".PA",
    "Nyse Euronext - Euronext Brussels": ".BR",
    "Euronext Brussels": ".BR",
    "Nyse Euronext - Euronext Lisbon": ".LS",
    "Euronext Lisbon": ".LS",
    "Euronext Dublin": ".IR",
    "Irish Stock Exchange - All Market": ".IR",
    "Borsa Italiana": ".MI",
    "Bolsa De Madrid": ".MC",
    "Bolsas Y Mercados Espanoles": ".MC",
    "Xetra": ".DE",
    "Deutsche Boerse Ag": ".DE",
    "Frankfurt": ".F",
    "Wiener Boerse Ag": ".VI",
    "Oslo Bors Asa": ".OL",
    "Oslo Bors": ".OL",
    "Omx Nordic Exchange Copenhagen A/S": ".CO",
    "Nasdaq Copenhagen": ".CO",
    "Nasdaq Omx Helsinki Ltd.": ".HE",
    "Nasdaq Helsinki": ".HE",
    "Nasdaq Stockholm": ".ST",
    "Athens Exchange": ".AT",
    "Warsaw Stock Exchange": ".WA",
    "Budapest Stock Exchange": ".BD",
    "Prague Stock Exchange": ".PR",
}

# "Nasdaq Omx Nordic" is umbrella; resolve via Location.
LOCATION_FALLBACK_SUFFIX = {
    "Sweden": ".ST",
    "Finland": ".HE",
    "Denmark": ".CO",
    "Iceland": ".IC",
    "Norway": ".OL",
}

REGIONS = {
    "us": dict(
        fid="239774", slug="ishares-core-sp-smallcap-etf", tag="IJR",
        index="IJR", suffix=None, label="US S&P 600 SmallCap",
    ),
    "europe": dict(
        fid="239537", slug="ishares-msci-europe-smallcap-etf", tag="IEUS",
        index="IEUS", suffix="exchange", label="MSCI Europe Small-Cap",
    ),
    "uk": dict(
        # UK universe from EWUS holdings; benchmark with ISF.L (FTSE 100 in
        # pence) so stock and index are in the same currency (GBp), no FX leak.
        fid="239691", slug="ishares-msci-united-kingdom-smallcap-etf", tag="EWUS",
        index="ISF.L", suffix=".L", label="MSCI UK Small-Cap (vs FTSE 100)",
    ),
}

# Map Yahoo suffix -> local currency code. Used for FX-to-USD conversion.
# 'GBp' = pence (1/100 of GBP), Yahoo's actual returned unit for .L tickers.
SUFFIX_TO_CCY = {
    ".L":  "GBp",
    ".SW": "CHF",
    ".ST": "SEK",
    ".OL": "NOK",
    ".CO": "DKK",
    ".HE": "EUR",
    ".AS": "EUR",
    ".PA": "EUR",
    ".BR": "EUR",
    ".LS": "EUR",
    ".IR": "EUR",
    ".MI": "EUR",
    ".MC": "EUR",
    ".DE": "EUR",
    ".F":  "EUR",
    ".VI": "EUR",
}


def normalise_uk_ticker(t: str) -> str:
    """LSE tickers come like 'BEZ', 'III', 'JD/' (period). Yahoo wants
    'BEZ.L', 'III.L', 'JD.L'. Some have multiple share classes."""
    t = t.strip().rstrip(".").rstrip("/")
    return t.replace(".", "").replace(" ", "")


def normalise_eu_ticker(t: str, suffix: str) -> str:
    """European share-class tickers come with a space, e.g. 'GETI B' on
    Stockholm. Yahoo represents that as 'GETI-B.ST'."""
    t = t.strip().rstrip(".").rstrip("/")
    if not t or t == "-":
        return ""
    parts = t.split()
    base = parts[0].replace(".", "")
    if len(parts) > 1:
        base = base + "-" + "".join(parts[1:])
    return base + suffix


def resolve_suffix(exchange: str, location: str) -> str | None:
    s = EXCHANGE_TO_YAHOO.get(str(exchange).strip())
    if s:
        return s
    return LOCATION_FALLBACK_SUFFIX.get(str(location).strip())


CACHE_DIR = "/tmp"


def _fetch_holdings_csv(cfg: dict) -> str:
    """Fetch iShares holdings CSV, caching to /tmp on success and falling back
    to the cached copy if the iShares CDN returns an error (transient 503s
    happen)."""
    import os
    cache_path = os.path.join(CACHE_DIR, f"{cfg['tag']}.csv")
    url = ISHARES_URL.format(fid=cfg["fid"], slug=cfg["slug"], tag=cfg["tag"])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        body = urllib.request.urlopen(req, timeout=30).read()
        if len(body) > 5000:
            with open(cache_path, "wb") as f:
                f.write(body)
            return body.decode("utf-8-sig")
    except Exception as e:
        print(f"  iShares fetch failed: {e}", file=sys.stderr)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 5000:
        print(f"  Falling back to cached {cache_path}", file=sys.stderr)
        with open(cache_path, "rb") as f:
            return f.read().decode("utf-8-sig")
    raise RuntimeError(f"No live or cached holdings for {cfg['tag']}")


def fetch_universe(region: str) -> tuple[list[str], pd.DataFrame]:
    cfg = REGIONS[region]
    raw = _fetch_holdings_csv(cfg)
    lines = raw.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Ticker,Name"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df = df[df["Asset Class"].astype(str).str.lower() == "equity"].copy()

    if cfg["suffix"] is None:
        # US: tickers as-is, Yahoo uses '-' instead of '.' for share classes.
        df["Yahoo"] = df["Ticker"].astype(str).str.strip().str.replace(".", "-", regex=False)
    elif cfg["suffix"] == "exchange":
        # Map per-row from Exchange column (with Location fallback for Nordic).
        ys = []
        for t, ex, loc in zip(df["Ticker"], df["Exchange"], df["Location"]):
            suf = resolve_suffix(ex, loc)
            ys.append(normalise_eu_ticker(str(t), suf) if suf else "")
        df["Yahoo"] = ys
        df = df[df["Yahoo"].astype(bool)]
    else:
        # Single fixed suffix (UK).
        df["Yahoo"] = df["Ticker"].astype(str).map(lambda t: normalise_eu_ticker(t, cfg["suffix"]))
        df = df[df["Yahoo"].astype(bool)]

    tickers = sorted({t for t in df["Yahoo"] if t and 2 < len(t) < 20})
    return tickers, df


def currency_for_ticker(ticker: str) -> str:
    """Infer local price currency from Yahoo suffix (None => USD)."""
    if "." not in ticker:
        return "USD"
    suf = "." + ticker.rsplit(".", 1)[1]
    return SUFFIX_TO_CCY.get(suf, "USD")


def fetch_fx(currencies: set[str], period: str = "24mo") -> dict:
    """Daily local→USD rate for each non-USD currency. GBp = pence (GBP/100)."""
    needed = sorted({c for c in currencies if c and c != "USD"})
    if not needed:
        return {}
    yahoo_pair = {c: ("GBPUSD=X" if c == "GBp" else f"{c}USD=X") for c in needed}
    syms = sorted(set(yahoo_pair.values()))
    raw = yf.download(syms, period=period, interval="1d",
                      auto_adjust=True, progress=False, threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else pd.DataFrame({syms[0]: raw["Close"]})
    out = {}
    for c, sym in yahoo_pair.items():
        if sym in close.columns:
            s = close[sym].dropna()
            if c == "GBp":
                s = s * 0.01
            out[c] = s
    return out


def usd_close(daily: pd.DataFrame, ticker: str, fx: dict) -> pd.Series:
    """Return Close series in USD (or local if already USD / FX missing)."""
    p = daily["Close"][ticker].dropna()
    ccy = currency_for_ticker(ticker)
    if ccy == "USD":
        return p
    f = fx.get(ccy)
    if f is None:
        return p
    common = p.index.intersection(f.index)
    return p.reindex(common) * f.reindex(common).ffill()


def fetch_ohlc(tickers: list[str], period: str = "24mo") -> pd.DataFrame:
    print(f"Downloading OHLC for {len(tickers)} tickers ({period})...", file=sys.stderr)
    raw = yf.download(
        tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    return raw  # MultiIndex columns: (field, ticker)


def resample_ohlc(daily: pd.DataFrame, ticker: str, freq: str) -> pd.DataFrame:
    """Build resampled OHLC bars for one ticker on the given freq."""
    try:
        sub = pd.DataFrame({
            "High":  daily["High"][ticker],
            "Low":   daily["Low"][ticker],
            "Close": daily["Close"][ticker],
        }).dropna()
    except KeyError:
        return pd.DataFrame()
    return sub.resample(freq).agg({"High": "max", "Low": "min", "Close": "last"}).dropna()


def asymmetry(bars: pd.DataFrame, period: int = ASYM_PERIOD, smooth: int = ASYM_SMOOTH) -> pd.DataFrame:
    """Port of the Pine Volatility Asymmetry indicator.
    Returns columns: asym (0-100, 50 = balanced), asym_ma."""
    prev_close = bars["Close"].shift(1)
    up = (bars["High"] - prev_close).clip(lower=0)
    dn = (prev_close - bars["Low"]).clip(lower=0)
    up_atr = up.ewm(span=period, adjust=False).mean()
    dn_atr = dn.ewm(span=period, adjust=False).mean()
    ratio = up_atr / (up_atr + dn_atr + 1e-9)
    asym = (ratio * 100).ewm(span=smooth, adjust=False).mean()
    asym_ma = asym.ewm(span=period, adjust=False).mean()
    return pd.DataFrame({"asym": asym, "asym_ma": asym_ma}).dropna()


def rs_breakout(stock_close: pd.Series, idx_close: pd.Series, freq: str, lookback: int) -> tuple[bool, float]:
    s = stock_close.resample(freq).last().dropna()
    i = idx_close.resample(freq).last().dropna()
    df = pd.concat([s, i], axis=1, join="inner").dropna()
    if len(df) < lookback + 2:
        return False, np.nan
    rs = np.log(df.iloc[:, 0] / df.iloc[:, 1])
    prior_max = rs.iloc[-(lookback + 1):-1].max()
    current = rs.iloc[-1]
    return bool(current > prior_max), float(current - prior_max)


def fip_score(close: pd.Series, lookback_days: int = 252, skip_days: int = 21) -> tuple[float, float, float]:
    """Frog-in-the-Pan (Da/Gurun/Warachka 2014).

    FIP = sign(R_12-1) * (% negative days - % positive days)
    Lower (more negative) = continuous information = "frog in pan" winners.
    Returns (R, fip, pos_pct). The 12-1 convention skips the most recent
    month to avoid short-term reversal contamination.
    """
    p = close.dropna()
    if len(p) < lookback_days + skip_days + 5:
        return np.nan, np.nan, np.nan
    win = p.iloc[-(lookback_days + skip_days):-skip_days] if skip_days else p.iloc[-lookback_days:]
    rets = win.pct_change().dropna()
    R = float(win.iloc[-1] / win.iloc[0] - 1)
    pos = float((rets > 0).sum() / len(rets))
    neg = float((rets < 0).sum() / len(rets))
    fip = float(np.sign(R) * (neg - pos))
    return R, fip, pos


def prior_relative_return(close: pd.Series, idx_close: pd.Series, weeks: int = 26) -> float:
    """Log-RS gain over the prior `weeks` weeks vs the most recent week."""
    s = close.resample("W-FRI").last().dropna()
    i = idx_close.resample("W-FRI").last().dropna()
    df = pd.concat([s, i], axis=1, join="inner").dropna()
    if len(df) < weeks + 2:
        return np.nan
    rs = np.log(df.iloc[:, 0] / df.iloc[:, 1])
    return float(rs.iloc[-1] - rs.iloc[-weeks])


def screen_rs_and_asymmetry(
    daily: pd.DataFrame,
    idx_close: pd.Series,
    tickers: list[str],
    fx: dict | None = None,
) -> pd.DataFrame:
    fx = fx or {}
    rows = []
    for t in tickers:
        try:
            close_local = daily["Close"][t].dropna()
        except KeyError:
            continue
        if len(close_local) < 260:
            continue

        # For RS comparison we need stock and index in the same currency.
        close_for_rs = usd_close(daily, t, fx) if fx else close_local
        # Asymmetry uses high/low/close ratios within the stock — FX cancels,
        # so we keep the local-currency series. FIP uses returns — also FX-invariant.
        ok_w, mw = rs_breakout(close_for_rs, idx_close, "W-FRI", RS_LOOKBACK_W)
        ok_m, mm = rs_breakout(close_for_rs, idx_close, "ME",    RS_LOOKBACK_M)
        prior_rs_26w = prior_relative_return(close_for_rs, idx_close, weeks=26)
        R12_1, fip, pos_pct = fip_score(close_local, lookback_days=252, skip_days=21)
        # Also keep `close` reference for downstream code that already used it.
        close = close_local

        # Screen 2: volatility asymmetry on weekly + monthly bars
        wbars = resample_ohlc(daily, t, "W-FRI")
        mbars = resample_ohlc(daily, t, "ME")
        if len(wbars) < ASYM_PERIOD + ASYM_SMOOTH + 5 or len(mbars) < ASYM_PERIOD + 2:
            continue
        wa = asymmetry(wbars)
        ma = asymmetry(mbars)
        if wa.empty or ma.empty:
            continue
        w_now, w_ma_now = wa["asym"].iloc[-1], wa["asym_ma"].iloc[-1]
        m_now = ma["asym"].iloc[-1]
        # Rising: last N bars strictly higher than prior bar
        recent = wa["asym"].iloc[-(WEEKLY_ASYM_RISING_BARS + 1):]
        weekly_rising = bool((recent.diff().dropna() > 0).all())
        weekly_above_ma = bool(w_now > w_ma_now)
        weekly_low = bool(w_now <= WEEKLY_ASYM_LOW_MAX)
        monthly_balanced = bool(MONTHLY_ASYM_BAND[0] <= m_now <= MONTHLY_ASYM_BAND[1])

        rows.append(dict(
            ticker=t,
            rs_w=ok_w, rs_m=ok_m, w_margin=mw, m_margin=mm,
            prior_rs_26w=prior_rs_26w,
            R_12_1=R12_1, fip=fip, pos_pct=pos_pct,
            asym_w=float(w_now), asym_w_ma=float(w_ma_now),
            asym_m=float(m_now),
            w_rising=weekly_rising, w_above_ma=weekly_above_ma,
            w_low=weekly_low, m_balanced=monthly_balanced,
            score=(mw if not np.isnan(mw) else 0) + (mm if not np.isnan(mm) else 0),
        ))

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["pass_rs"] = df.rs_w & df.rs_m
    # Qullamaggie pre-breakout setup: prior strong RS run, then a tight base
    # (monthly asym near 50, weekly rising/above MA/low). Requires positive
    # 26-week relative return so we only see "consolidation after uptrend",
    # not "stopped declining."
    prior_uptrend = df.prior_rs_26w > 0.10
    df["pass_setup"] = (
        df.w_rising & df.w_above_ma & df.w_low & df.m_balanced & prior_uptrend
    )
    # Aligned breakout: weekly RS breakout, monthly asym still in 40-60 band,
    # weekly asym rising and above its MA (drop "low" since RS breakout implies
    # asym is already lifting).
    m_band = (df.asym_m >= 40) & (df.asym_m <= 60)
    df["pass_aligned"] = df.rs_w & df.w_rising & df.w_above_ma & m_band
    df["pass_strict"] = df.pass_rs & df.pass_setup
    # Frog-in-the-Pan quality gate. Continuous-information winners have FIP
    # well below zero (more positive than negative days). -0.05 is a mild
    # cutoff; the paper's bottom quintile typically sits around -0.10 to -0.20.
    df["pass_fip"] = df.fip.notna() & (df.fip <= -0.05) & (df.R_12_1 > 0)
    return df.sort_values("score", ascending=False)


def max_independent_set(survivors: pd.DataFrame, daily: pd.DataFrame, eps: float = CORR_EPS) -> pd.DataFrame:
    tickers = survivors.ticker.tolist()
    if len(tickers) <= 1:
        return survivors.assign(selected=True)
    closes = daily["Close"][tickers]
    weekly_ret = closes.resample("W-FRI").last().pct_change().dropna()
    corr = weekly_ret.corr().abs()
    survivors = survivors.set_index("ticker")
    chosen: list[str] = []
    for t in survivors.sort_values("score", ascending=False).index:
        if all(corr.loc[t, c] <= eps for c in chosen):
            chosen.append(t)
    survivors["selected"] = survivors.index.isin(chosen)
    return survivors.reset_index()


def diagnostics(selected: list[str], daily: pd.DataFrame) -> dict:
    if len(selected) < 2:
        return {"n": len(selected)}
    weekly_ret = daily["Close"][selected].resample("W-FRI").last().pct_change().dropna()
    cov = weekly_ret.cov().values
    eig = np.linalg.eigvalsh(cov)
    n_eff = (np.trace(cov) ** 2) / np.trace(cov @ cov)
    corr = weekly_ret.corr().values
    iu = np.triu_indices_from(corr, k=1)
    return {
        "n": len(selected),
        "mean_|corr|": float(np.mean(np.abs(corr[iu]))),
        "max_|corr|":  float(np.max(np.abs(corr[iu]))),
        "N_eff_bets":  float(n_eff),
        "top_eigenvalue_share": float(eig.max() / eig.sum()),
    }


def main() -> None:
    region = (sys.argv[1] if len(sys.argv) > 1 else "us").lower()
    if region not in REGIONS:
        raise SystemExit(f"Unknown region {region!r}; choose from {list(REGIONS)}.")
    cfg = REGIONS[region]
    index = cfg["index"]
    print(f"\n>>> Region: {region} ({cfg['label']}); index = {index}\n", file=sys.stderr)

    try:
        universe, _holdings = fetch_universe(region)
        print(f"Fetched {len(universe)} tickers from {cfg['tag']} holdings.", file=sys.stderr)
    except Exception as e:
        print(f"Universe fetch failed ({e}); aborting.", file=sys.stderr)
        sys.exit(1)

    daily = fetch_ohlc(universe + [index], period="24mo")
    if index not in daily["Close"].columns:
        raise SystemExit(f"Index {index} missing from data.")
    idx_close = daily["Close"][index]
    tickers = [t for t in universe if t in daily["Close"].columns]

    # FX: index is in USD (IEUS) -> convert non-USD stock series to USD for RS.
    # For UK we benchmark against ISF.L (GBp) so all stocks are GBp; no FX needed.
    needed_ccys = {currency_for_ticker(t) for t in tickers}
    idx_ccy = currency_for_ticker(index)
    fx = {}
    if idx_ccy == "USD" and any(c != "USD" for c in needed_ccys):
        print(f"Fetching FX series for {sorted(needed_ccys - {'USD'})}...", file=sys.stderr)
        fx = fetch_fx(needed_ccys)

    df = screen_rs_and_asymmetry(daily, idx_close, tickers, fx=fx)
    print(f"\nUniverse evaluated: {len(df)}")
    print(f"  Pass weekly+monthly RS breakout:         {int(df.pass_rs.sum())}")
    print(f"  Pass Qullamaggie setup (asym only):      {int(df.pass_setup.sum())}")
    print(f"  Pass strict (RS + setup):                {int(df.pass_strict.sum())}")
    print(f"  Pass aligned breakout (RS_w + bal asym): {int(df.pass_aligned.sum())}")
    print(f"  Pass Frog-in-the-Pan (R>0 & FIP<=-0.05): {int(df.pass_fip.sum())}")

    cols = ["ticker", "w_margin", "m_margin", "prior_rs_26w",
            "R_12_1", "fip", "pos_pct",
            "asym_w", "asym_w_ma", "asym_m", "score"]

    modes = [
        ("Mode A: pre-breakout setup (asym only)", "pass_setup"),
        ("Mode B: aligned breakout (weekly RS + balanced monthly asym)", "pass_aligned"),
        ("Mode C: strict (both RS TFs + full asym pattern)", "pass_strict"),
        ("Mode D: aligned breakout AND Frog-in-the-Pan quality", None),
    ]
    for label, key in modes:
        if label.startswith("Mode D"):
            survivors = df[df.pass_aligned & df.pass_fip].copy()
        else:
            survivors = df[df[key]].copy()
        print(f"\n=== {label} — {len(survivors)} survivors ===")
        if survivors.empty:
            print("(none)")
            continue
        print(survivors[cols].head(40).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

        final = max_independent_set(survivors, daily, eps=CORR_EPS)
        selected = final[final.selected].ticker.tolist()
        print(f"\n  Uncorrelated portfolio (|weekly corr| <= {CORR_EPS}): {len(selected)} names")
        print(final[final.selected][cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

        diag = diagnostics(selected, daily)
        print("  Diagnostics:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in diag.items()})


if __name__ == "__main__":
    main()
