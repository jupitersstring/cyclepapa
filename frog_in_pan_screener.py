"""
Frog-in-the-Pan momentum screener for European + UK small/mid-cap equities.

Concept (Da, Gurun, Warachka 2014, "Frog in the Pan"):
    FIP = sign(PRET) * (%neg_days - %pos_days)

A LOW (negative) FIP score for a winner stock means it climbed via many small
continuous moves rather than a few headline jumps. The behavioural claim is
that investors underreact to that drip-feed information, so continuous winners
have stronger forward momentum than discrete winners.

This screener looks for stocks that are:
  - Winners (positive 12m return)
  - "Frog in the pan" on the DAILY timeframe (low daily FIP)
  - LESS frog-in-the-pan on the WEEKLY timeframe (higher weekly FIP)
  - But the weekly FIP is INFLECTING DOWN (becoming smoother on weekly too)

Survivors are then ranked by:
  - Low P/B
  - Low EV/EBITDA
  - High trailing revenue growth
  - High revenue-growth inflection (acceleration)

Run:
    pip install financedatabase yfinance pandas numpy tqdm
    python frog_in_pan_screener.py --out screen.csv
"""

from __future__ import annotations

import argparse
import math
import os
import pickle
import random
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PRICE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".price_cache.pkl")
OHLC_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ohlc_cache.pkl")
SPX_TICKER = "^GSPC"


# Map a company's HQ country to the Yahoo suffix of its likely primary listing.
# Used to deduplicate cross-listings and prefer the local primary ticker for
# fundamentals (Yahoo's .info often only populates on the primary listing).
COUNTRY_TO_SUFFIX = {
    "United Kingdom": ".L",
    "Ireland": ".L",          # Irish-listed-on-LSE is common
    "France": ".PA",
    "Germany": ".DE",
    "Netherlands": ".AS",
    "Belgium": ".BR",
    "Luxembourg": ".LU",
    "Switzerland": ".SW",
    "Austria": ".VI",
    "Italy": ".MI",
    "Spain": ".MC",
    "Portugal": ".LS",
    "Sweden": ".ST",
    "Norway": ".OL",
    "Denmark": ".CO",
    "Finland": ".HE",
    "Iceland": ".IC",
    "Poland": ".WA",
    "Czech Republic": ".PR",
    "Hungary": ".BD",
    "Greece": ".AT",
    "Estonia": ".TL",
    "Latvia": ".RG",
    "Lithuania": ".VS",
    "Slovenia": ".LJ",
    "Slovakia": ".BV",
    "Romania": ".RO",
    "Cyprus": ".CY",
    "Malta": ".MT",
    "Guernsey": ".L",
    "Jersey": ".L",
    "Isle of Man": ".L",
    "Gibraltar": ".L",
    "Liechtenstein": ".SW",
    "Monaco": ".PA",
    "Macedonia": ".AT",
    "Montenegro": ".AT",
}


EUROPEAN_COUNTRIES = [
    "United Kingdom", "Ireland", "France", "Germany", "Netherlands",
    "Belgium", "Luxembourg", "Switzerland", "Austria", "Italy", "Spain",
    "Portugal", "Sweden", "Norway", "Denmark", "Finland", "Iceland",
    "Poland", "Czech Republic", "Hungary", "Greece", "Cyprus", "Malta",
    "Estonia", "Latvia", "Lithuania", "Slovenia", "Slovakia", "Romania",
    # Crown dependencies / micro-states with Yahoo listings
    "Guernsey", "Jersey", "Isle of Man", "Gibraltar", "Liechtenstein",
    "Monaco", "Macedonia", "Montenegro",
]

SMALL_MID_BUCKETS = ["Small Cap", "Mid Cap"]


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def load_universe(min_n: int = 50, primary_only: bool = True) -> pd.DataFrame:
    """Pull European + UK small & mid-caps from financedatabase.

    If primary_only is True, collapse cross-listed duplicates by keeping the
    listing whose Yahoo suffix matches the company's HQ country (so Getinge
    resolves to GETI-B.ST rather than GTN.MU). This dramatically improves
    fundamentals coverage and removes redundant downloads.
    """
    import financedatabase as fd

    eq = fd.Equities()
    df = eq.select(country=EUROPEAN_COUNTRIES, market_cap=SMALL_MID_BUCKETS)
    if df is None or df.empty:
        raise RuntimeError("financedatabase returned empty universe; check installation.")
    df = df.copy()
    df.index.name = "symbol"
    df = df[df.index.notna()]
    df = df[df.index.astype(str).str.contains(r"\.[A-Z]{1,3}$", regex=True)]

    if primary_only and "name" in df.columns and "country" in df.columns:
        idx_str = df.index.astype(str)
        suffix = idx_str.str.extract(r"(\.[A-Z]{1,3})$")[0].to_numpy()
        pref = df["country"].map(COUNTRY_TO_SUFFIX).to_numpy()
        is_primary = pd.Series(suffix == pref, index=df.index).fillna(False)
        df = df.assign(_is_primary=is_primary.values)
        df = df.sort_values(by=["name", "_is_primary"], ascending=[True, False])
        df = df.drop_duplicates(subset="name", keep="first")
        df = df.drop(columns=["_is_primary"])

    if len(df) < min_n:
        print(f"[warn] universe smaller than expected: {len(df)}", file=sys.stderr)
    return df


# ---------------------------------------------------------------------------
# Frog-in-the-pan core math
# ---------------------------------------------------------------------------

def _fip(returns: pd.Series) -> tuple[float, float]:
    """Return (PRET, FIP) for a clean returns series.

    PRET is compounded return over the window.
    FIP  = sign(PRET) * (%neg - %pos)  with zero-return days excluded.
    """
    r = returns.dropna()
    if len(r) < 20:
        return (np.nan, np.nan)
    pret = float((1.0 + r).prod() - 1.0)
    nz = r[r != 0]
    if len(nz) == 0:
        return (pret, np.nan)
    pct_pos = float((nz > 0).mean())
    pct_neg = float((nz < 0).mean())
    sign = 1.0 if pret > 0 else (-1.0 if pret < 0 else 0.0)
    return (pret, sign * (pct_neg - pct_pos))


@dataclass
class FIPResult:
    symbol: str
    pret_d: float
    fip_d: float
    pret_w: float
    fip_w: float
    fip_w_prev: float        # weekly FIP measured one quarter ago (inflection)
    fip_w_inflection: float  # negative => weekly is becoming smoother
    last_price: float
    n_days: int


def compute_fip(symbol: str, prices: pd.Series) -> FIPResult | None:
    prices = prices.dropna()
    if len(prices) < 260:
        return None

    daily_ret = prices.pct_change()
    # Daily FIP over trailing ~252 trading days.
    pret_d, fip_d = _fip(daily_ret.iloc[-252:])

    # Weekly FIP over trailing ~52 weeks (Friday closes).
    weekly = prices.resample("W-FRI").last().dropna()
    if len(weekly) < 70:
        return None
    weekly_ret = weekly.pct_change()
    pret_w, fip_w = _fip(weekly_ret.iloc[-52:])

    # Weekly FIP one quarter ago (drop most recent ~13 weeks, take 52 before that).
    prev_window = weekly_ret.iloc[-(52 + 13):-13]
    _, fip_w_prev = _fip(prev_window)

    inflection = fip_w - fip_w_prev if not (math.isnan(fip_w) or math.isnan(fip_w_prev)) else np.nan

    return FIPResult(
        symbol=symbol,
        pret_d=pret_d,
        fip_d=fip_d,
        pret_w=pret_w,
        fip_w=fip_w,
        fip_w_prev=fip_w_prev,
        fip_w_inflection=inflection,
        last_price=float(prices.iloc[-1]),
        n_days=len(prices),
    )


# ---------------------------------------------------------------------------
# Price download
# ---------------------------------------------------------------------------

def _load_price_cache() -> dict[str, pd.Series]:
    if not os.path.exists(PRICE_CACHE):
        return {}
    try:
        with open(PRICE_CACHE, "rb") as fh:
            return pickle.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _save_price_cache(cache: dict[str, pd.Series]) -> None:
    try:
        with open(PRICE_CACHE, "wb") as fh:
            pickle.dump(cache, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not write price cache: {e}", file=sys.stderr)


def download_prices(
    symbols: list[str],
    period: str = "2y",
    batch: int = 25,
    sleep_between: float = 1.5,
    use_cache: bool = True,
) -> dict[str, pd.Series]:
    """Batched yfinance download with disk cache and rate-limit backoff.

    Returns {symbol -> adj-close series}. The cache is keyed on symbol; if a
    symbol is already cached we don't re-fetch.
    """
    import yfinance as yf
    from yfinance.exceptions import YFRateLimitError

    cache = _load_price_cache() if use_cache else {}
    cached_hits = sum(1 for s in symbols if s in cache)
    if cached_hits:
        print(f"  cache hit on {cached_hits}/{len(symbols)} symbols", file=sys.stderr)
    todo = [s for s in symbols if s not in cache]

    out: dict[str, pd.Series] = {s: cache[s] for s in symbols if s in cache}
    save_every = 5  # batches

    def _fetch_batch(chunk: list[str]) -> pd.DataFrame | None:
        for attempt in range(4):
            try:
                df = yf.download(
                    tickers=" ".join(chunk),
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="ticker",
                )
                return df
            except YFRateLimitError:
                wait = 30 * (2 ** attempt) + random.uniform(0, 5)
                print(f"  [rate-limit] sleeping {wait:.0f}s ...", file=sys.stderr)
                time.sleep(wait)
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] batch fetch error: {e}", file=sys.stderr)
                return None
        return None

    n_batches = (len(todo) + batch - 1) // batch
    for bi, i in enumerate(range(0, len(todo), batch)):
        chunk = todo[i : i + batch]
        df = _fetch_batch(chunk)
        if df is not None:
            if isinstance(df.columns, pd.MultiIndex):
                for sym in chunk:
                    if sym in df.columns.get_level_values(0):
                        s = df[sym].get("Close")
                        if s is not None and len(s.dropna()) > 0:
                            out[sym] = s.dropna()
                            cache[sym] = out[sym]
            else:
                s = df.get("Close")
                if s is not None and len(s.dropna()) > 0:
                    out[chunk[0]] = s.dropna()
                    cache[chunk[0]] = out[chunk[0]]

        if (bi + 1) % save_every == 0:
            _save_price_cache(cache)
            print(f"  batch {bi + 1}/{n_batches}: {len(out)} series cached so far",
                  file=sys.stderr)

        time.sleep(sleep_between)

    _save_price_cache(cache)
    return out


# ---------------------------------------------------------------------------
# OHLC download (needed for volatility-asymmetry indicator)
# ---------------------------------------------------------------------------

def _load_ohlc_cache() -> dict[str, pd.DataFrame]:
    if not os.path.exists(OHLC_CACHE):
        return {}
    try:
        with open(OHLC_CACHE, "rb") as fh:
            return pickle.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def _save_ohlc_cache(cache: dict[str, pd.DataFrame]) -> None:
    try:
        with open(OHLC_CACHE, "wb") as fh:
            pickle.dump(cache, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not write OHLC cache: {e}", file=sys.stderr)


def download_ohlc(
    symbols: list[str],
    period: str = "2y",
    batch: int = 25,
    sleep_between: float = 1.5,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Same shape as download_prices but caches full OHLC frames per symbol."""
    import yfinance as yf
    from yfinance.exceptions import YFRateLimitError

    cache = _load_ohlc_cache() if use_cache else {}
    cached_hits = sum(1 for s in symbols if s in cache)
    if cached_hits:
        print(f"  ohlc cache hit on {cached_hits}/{len(symbols)} symbols", file=sys.stderr)
    todo = [s for s in symbols if s not in cache]
    out: dict[str, pd.DataFrame] = {s: cache[s] for s in symbols if s in cache}

    def _fetch_batch(chunk: list[str]) -> pd.DataFrame | None:
        for attempt in range(4):
            try:
                return yf.download(
                    tickers=" ".join(chunk),
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="ticker",
                )
            except YFRateLimitError:
                wait = 30 * (2 ** attempt) + random.uniform(0, 5)
                print(f"  [rate-limit] sleeping {wait:.0f}s ...", file=sys.stderr)
                time.sleep(wait)
            except Exception as e:  # noqa: BLE001
                print(f"  [warn] ohlc batch error: {e}", file=sys.stderr)
                return None
        return None

    n_batches = (len(todo) + batch - 1) // batch
    save_every = 5
    cols = ["Open", "High", "Low", "Close"]
    for bi, i in enumerate(range(0, len(todo), batch)):
        chunk = todo[i : i + batch]
        df = _fetch_batch(chunk)
        if df is not None:
            if isinstance(df.columns, pd.MultiIndex):
                for sym in chunk:
                    if sym in df.columns.get_level_values(0):
                        sub = df[sym][cols].dropna(how="all")
                        if len(sub) > 60:
                            out[sym] = sub
                            cache[sym] = sub
            else:
                sub = df[cols].dropna(how="all")
                if len(sub) > 60:
                    out[chunk[0]] = sub
                    cache[chunk[0]] = sub

        if (bi + 1) % save_every == 0:
            _save_ohlc_cache(cache)
            print(f"  ohlc batch {bi + 1}/{n_batches}: {len(out)} cached so far",
                  file=sys.stderr)
        time.sleep(sleep_between)

    _save_ohlc_cache(cache)
    return out


def fetch_spx_close(period: str = "2y") -> pd.Series:
    """Fetch SPX (^GSPC) adjusted close as the relative-strength benchmark."""
    import yfinance as yf
    from yfinance.exceptions import YFRateLimitError

    for attempt in range(4):
        try:
            df = yf.download(
                tickers=SPX_TICKER, period=period, interval="1d",
                auto_adjust=True, progress=False, threads=False,
            )
            if df is None or df.empty:
                return pd.Series(dtype=float)
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            return close.dropna()
        except YFRateLimitError:
            time.sleep(30 * (2 ** attempt))
    return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Volatility-asymmetry (exact port of malikmck Pine Script) + RS metrics
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, length: int) -> pd.Series:
    """Pine Script ta.ema = pandas EWM with adjust=False, alpha=2/(length+1)."""
    return series.ewm(span=length, adjust=False, min_periods=1).mean()


def vol_asymmetry(
    ohlc: pd.DataFrame,
    period: int = 14,
    smooth_len: int = 7,
    smooth: bool = True,
) -> pd.Series:
    """Exact port of the asymmetryValue from the malikmck Pine indicator.

        upMove = max(High - Close[-1], 0)
        dnMove = max(Close[-1] - Low, 0)
        upATR = ema(upMove, period); dnATR = ema(dnMove, period)
        ratio = upATR / (upATR + dnATR + 1e-4)
        asym = ema(ratio*100, smooth_len) if smooth else ratio*100
    """
    high = ohlc["High"].astype(float)
    low = ohlc["Low"].astype(float)
    close = ohlc["Close"].astype(float)
    prev_close = close.shift(1)
    up = (high - prev_close).clip(lower=0)
    dn = (prev_close - low).clip(lower=0)
    up_atr = _ema(up, period)
    dn_atr = _ema(dn, period)
    ratio = up_atr / (up_atr + dn_atr + 1e-4)
    asym = ratio * 100.0
    if smooth:
        asym = _ema(asym, smooth_len)
    return asym


def _resample_ohlc(ohlc: pd.DataFrame, rule: str) -> pd.DataFrame:
    return pd.DataFrame({
        "Open":  ohlc["Open"].resample(rule).first(),
        "High":  ohlc["High"].resample(rule).max(),
        "Low":   ohlc["Low"].resample(rule).min(),
        "Close": ohlc["Close"].resample(rule).last(),
    }).dropna()


def _fip_change(series: pd.Series, n: int) -> tuple[float, float]:
    """FIP analogue for a non-return series (e.g. volatility asymmetry).

    Uses cumulative *change* (last - first) for the sign, and the count of
    positive/negative diffs over the same window.
    """
    s = series.dropna().iloc[-n:]
    if len(s) < 20:
        return (np.nan, np.nan)
    delta = float(s.iloc[-1] - s.iloc[0])
    diffs = s.diff().dropna()
    nz = diffs[diffs != 0]
    if len(nz) == 0:
        return (delta, np.nan)
    pct_pos = float((nz > 0).mean())
    pct_neg = float((nz < 0).mean())
    sign = 1.0 if delta > 0 else (-1.0 if delta < 0 else 0.0)
    return (delta, sign * (pct_neg - pct_pos))


@dataclass
class QullaResult:
    symbol: str
    last_price: float
    # RS-vs-SPX FIP
    rs_pret_d: float
    rs_fip_d: float
    rs_fip_w: float
    rs_fip_w_inflection: float
    # Volatility asymmetry levels
    asym_d_last: float
    asym_w_last: float
    asym_w_ma_last: float
    asym_w_above_ma: float    # asym_w - asym_w_ma
    asym_w_roc5: float        # 5-bar change in weekly asymmetry (rising = >0)
    asym_m_last: float
    # FIP on the volatility-asymmetry series (lower = smoother rise/fall)
    va_pret_d: float
    va_fip_d: float


def compute_qulla(symbol: str, ohlc: pd.DataFrame, spx_close: pd.Series) -> QullaResult | None:
    ohlc = ohlc.dropna(how="any")
    if len(ohlc) < 260:
        return None

    # Relative-strength line vs SPX (forward-fill SPX onto local trading days).
    spx_aligned = spx_close.reindex(ohlc.index, method="ffill")
    rs = (ohlc["Close"].astype(float) / spx_aligned).dropna()
    if len(rs) < 260:
        return None
    rs_ret = rs.pct_change()
    rs_pret_d, rs_fip_d = _fip(rs_ret.iloc[-252:])

    rs_w = rs.resample("W-FRI").last().dropna()
    if len(rs_w) < 70:
        return None
    rs_w_ret = rs_w.pct_change()
    _, rs_fip_w = _fip(rs_w_ret.iloc[-52:])
    _, rs_fip_w_prev = _fip(rs_w_ret.iloc[-(52 + 13):-13])
    rs_fip_w_inflection = (
        rs_fip_w - rs_fip_w_prev
        if not (math.isnan(rs_fip_w) or math.isnan(rs_fip_w_prev))
        else float("nan")
    )

    # Volatility asymmetry on three timeframes.
    asym_d = vol_asymmetry(ohlc)
    weekly = _resample_ohlc(ohlc, "W-FRI")
    monthly = _resample_ohlc(ohlc, "ME")
    if len(weekly) < 30 or len(monthly) < 6:
        return None
    asym_w = vol_asymmetry(weekly)
    asym_w_ma = _ema(asym_w, 14)
    asym_m = vol_asymmetry(monthly)

    asym_w_last = float(asym_w.iloc[-1]) if len(asym_w) else float("nan")
    asym_w_ma_last = float(asym_w_ma.iloc[-1]) if len(asym_w_ma) else float("nan")
    asym_w_roc5 = (
        float(asym_w.iloc[-1] - asym_w.iloc[-6])
        if len(asym_w) >= 6 else float("nan")
    )

    # FIP on the smoothed daily asymmetry series.
    va_pret_d, va_fip_d = _fip_change(asym_d, n=252)

    return QullaResult(
        symbol=symbol,
        last_price=float(ohlc["Close"].iloc[-1]),
        rs_pret_d=rs_pret_d,
        rs_fip_d=rs_fip_d,
        rs_fip_w=rs_fip_w,
        rs_fip_w_inflection=rs_fip_w_inflection,
        asym_d_last=float(asym_d.iloc[-1]),
        asym_w_last=asym_w_last,
        asym_w_ma_last=asym_w_ma_last,
        asym_w_above_ma=asym_w_last - asym_w_ma_last,
        asym_w_roc5=asym_w_roc5,
        asym_m_last=float(asym_m.iloc[-1]),
        va_pret_d=va_pret_d,
        va_fip_d=va_fip_d,
    )


def filter_qulla_candidates(
    qrs: list[QullaResult],
    daily_rs_fip_max: float = -0.03,
    asym_m_band: tuple[float, float] = (40.0, 60.0),
    asym_w_max: float = 65.0,
    require_winner: bool = True,
) -> list[QullaResult]:
    """Qullamaggie-style RS breakout setup with stealth volatility profile.

    Keep stocks where:
      - RS line vs SPX shows frog-in-the-pan smoothness on daily
      - Weekly RS FIP is inflecting smoother (stealth becoming clearer)
      - Stock is winning vs SPX over the year
      - Monthly volatility asymmetry sits near 50 (not stretched either way)
      - Weekly volatility asymmetry is rising over the past 5 weeks
      - Weekly volatility asymmetry is above its 14-EMA but still on the
        low side (capped at asym_w_max), so we catch breakouts early
        rather than after the fact.
    """
    lo, hi = asym_m_band
    out = []
    for q in qrs:
        # Required fields must be finite.
        required = [q.rs_pret_d, q.rs_fip_d, q.rs_fip_w, q.rs_fip_w_inflection,
                    q.asym_m_last, q.asym_w_last, q.asym_w_ma_last,
                    q.asym_w_roc5]
        if any(math.isnan(x) for x in required):
            continue
        if require_winner and q.rs_pret_d <= 0:
            continue
        if q.rs_fip_d > daily_rs_fip_max:
            continue
        if q.rs_fip_w_inflection >= 0:
            continue
        if not (lo <= q.asym_m_last <= hi):
            continue
        if q.asym_w_roc5 <= 0:
            continue
        if q.asym_w_last <= q.asym_w_ma_last:
            continue
        if q.asym_w_last >= asym_w_max:
            continue
        out.append(q)
    return out


def build_qulla_table(
    qrs: list[QullaResult],
    funds: dict[str, Fundamentals],
    universe: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for q in qrs:
        fu = funds.get(q.symbol)
        meta = universe.loc[q.symbol] if q.symbol in universe.index else None
        rows.append({
            "symbol": q.symbol,
            "name": (fu.name if fu else (meta["name"] if meta is not None and "name" in meta else q.symbol)),
            "country": meta["country"] if meta is not None and "country" in meta else "",
            "market_cap_bucket": meta["market_cap"] if meta is not None and "market_cap" in meta else "",
            "sector": (fu.sector if fu else "") or (meta["sector"] if meta is not None and "sector" in meta else ""),
            "market_cap": fu.market_cap if fu else float("nan"),
            "last_price": q.last_price,
            "rs_pret_d": q.rs_pret_d,
            "rs_fip_d": q.rs_fip_d,
            "rs_fip_w": q.rs_fip_w,
            "rs_fip_w_inflection": q.rs_fip_w_inflection,
            "asym_d_last": q.asym_d_last,
            "asym_w_last": q.asym_w_last,
            "asym_w_ma_last": q.asym_w_ma_last,
            "asym_w_above_ma": q.asym_w_above_ma,
            "asym_w_roc5": q.asym_w_roc5,
            "asym_m_last": q.asym_m_last,
            "asym_m_dist50": abs(q.asym_m_last - 50.0),
            "va_fip_d": q.va_fip_d,
            "pb": fu.pb if fu else float("nan"),
            "ev_ebitda": fu.ev_ebitda if fu else float("nan"),
            "rev_growth": fu.rev_growth if fu else float("nan"),
            "rev_growth_inflection": fu.rev_growth_inflection if fu else float("nan"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    pb_clean = df["pb"].where(df["pb"] > 0)
    ev_clean = df["ev_ebitda"].where(df["ev_ebitda"] > 0)
    rank_pb       = _pct_rank(pb_clean,                      lower_is_better=True)
    rank_ev       = _pct_rank(ev_clean,                      lower_is_better=True)
    rank_g        = _pct_rank(df["rev_growth"],              lower_is_better=False)
    rank_inf      = _pct_rank(df["rev_growth_inflection"],   lower_is_better=False)
    rank_rs_fip   = _pct_rank(df["rs_fip_d"],                lower_is_better=True)
    rank_rs_pret  = _pct_rank(df["rs_pret_d"],               lower_is_better=False)
    rank_asym_roc = _pct_rank(df["asym_w_roc5"],             lower_is_better=False)
    rank_asym_50  = _pct_rank(df["asym_m_dist50"],           lower_is_better=True)
    rank_va_fip   = _pct_rank(df["va_fip_d"],                lower_is_better=True)

    weights = {
        "rs_fip":   0.20,   # smooth daily RS line (the actual breakout signal)
        "rs_pret":  0.10,   # how strong is the RS uptrend
        "asym_roc": 0.10,   # weekly volasym is rising
        "asym_50":  0.05,   # monthly volasym near 50
        "va_fip":   0.05,   # smooth daily volasym trend
        "rev_g":    0.20,
        "rev_inf":  0.10,
        "pb":       0.10,
        "ev":       0.10,
    }
    df["score"] = (
        weights["rs_fip"]   * rank_rs_fip
        + weights["rs_pret"]  * rank_rs_pret
        + weights["asym_roc"] * rank_asym_roc
        + weights["asym_50"]  * rank_asym_50
        + weights["va_fip"]   * rank_va_fip
        + weights["rev_g"]    * rank_g
        + weights["rev_inf"]  * rank_inf
        + weights["pb"]       * rank_pb
        + weights["ev"]       * rank_ev
    )

    df = df.sort_values("score", ascending=False)
    df = df.drop_duplicates(subset="name", keep="first").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Fundamentals (per ticker)
# ---------------------------------------------------------------------------

@dataclass
class Fundamentals:
    symbol: str
    pb: float
    ev_ebitda: float
    rev_growth: float           # most recent yoy revenue growth (annual)
    rev_growth_prev: float      # prior yoy revenue growth (annual)
    rev_growth_inflection: float  # rev_growth - rev_growth_prev (acceleration)
    name: str
    sector: str
    market_cap: float


def _safe(v) -> float:
    try:
        if v is None:
            return float("nan")
        f = float(v)
        return f if math.isfinite(f) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _annual_revenues(tk) -> pd.Series:
    """Try a few yfinance entry points for an annual revenue series (most recent first)."""
    for attr in ("income_stmt", "financials"):
        try:
            df = getattr(tk, attr)
            if df is not None and not df.empty:
                for key in ("Total Revenue", "TotalRevenue", "Revenue"):
                    if key in df.index:
                        s = df.loc[key].dropna().astype(float)
                        # yfinance columns are dates with most-recent-first; sort to be safe.
                        s.index = pd.to_datetime(s.index, errors="coerce")
                        s = s.dropna().sort_index(ascending=False)
                        if len(s) >= 2:
                            return s
        except Exception:  # noqa: BLE001
            continue
    return pd.Series(dtype=float)


def fetch_fundamentals(symbol: str) -> Fundamentals | None:
    import yfinance as yf
    from yfinance.exceptions import YFRateLimitError

    info: dict = {}
    tk = None
    for attempt in range(4):
        try:
            tk = yf.Ticker(symbol)
            info = tk.info or {}
            break
        except YFRateLimitError:
            wait = 20 * (2 ** attempt) + random.uniform(0, 5)
            time.sleep(wait)
        except Exception:  # noqa: BLE001
            return None
    if tk is None or not info:
        return None

    pb = _safe(info.get("priceToBook"))
    ev_ebitda = _safe(info.get("enterpriseToEbitda"))
    rev_growth_info = _safe(info.get("revenueGrowth"))  # trailing yoy from yfinance
    name = str(info.get("longName") or info.get("shortName") or symbol)
    sector = str(info.get("sector") or "")
    mcap = _safe(info.get("marketCap"))

    rev = _annual_revenues(tk)
    rev_growth = float("nan")
    rev_growth_prev = float("nan")
    if len(rev) >= 3:
        r0, r1, r2 = rev.iloc[0], rev.iloc[1], rev.iloc[2]
        if r1 and r2 and r1 > 0 and r2 > 0:
            rev_growth = (r0 / r1) - 1.0
            rev_growth_prev = (r1 / r2) - 1.0
    elif len(rev) == 2:
        r0, r1 = rev.iloc[0], rev.iloc[1]
        if r1 and r1 > 0:
            rev_growth = (r0 / r1) - 1.0

    # Prefer computed annual growth; fall back to yfinance trailing if unavailable.
    if math.isnan(rev_growth):
        rev_growth = rev_growth_info

    inflection = (
        rev_growth - rev_growth_prev
        if not (math.isnan(rev_growth) or math.isnan(rev_growth_prev))
        else float("nan")
    )

    return Fundamentals(
        symbol=symbol,
        pb=pb,
        ev_ebitda=ev_ebitda,
        rev_growth=rev_growth,
        rev_growth_prev=rev_growth_prev,
        rev_growth_inflection=inflection,
        name=name,
        sector=sector,
        market_cap=mcap,
    )


def fetch_fundamentals_parallel(symbols: Iterable[str], workers: int = 2) -> dict[str, Fundamentals]:
    """Sequentially-ish (low concurrency) fetch — Yahoo aggressively rate-limits .info."""
    syms = list(symbols)
    out: dict[str, Fundamentals] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_fundamentals, s): s for s in syms}
        for done_count, fut in enumerate(as_completed(futures), start=1):
            s = futures[fut]
            try:
                f = fut.result()
            except Exception:  # noqa: BLE001
                f = None
            if f is not None:
                out[s] = f
            if done_count % 10 == 0:
                print(f"  fundamentals progress: {done_count}/{len(syms)} ({len(out)} ok)",
                      file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# Filtering + ranking
# ---------------------------------------------------------------------------

def filter_fip_candidates(
    fips: list[FIPResult],
    daily_fip_max: float = -0.05,
    require_winner: bool = True,
) -> list[FIPResult]:
    """Daily FIP low (frog) and weekly FIP inflecting down (smoothing).

    We deliberately do NOT require fip_w > fip_d so we capture both "mature"
    setups (daily already smoother than weekly) and "emerging" setups (FIP
    pattern just appearing on the weekly first, daily catching up).
    """
    out = []
    for f in fips:
        if any(map(math.isnan, (f.fip_d, f.fip_w, f.fip_w_inflection, f.pret_d))):
            continue
        if require_winner and f.pret_d <= 0:
            continue
        if f.fip_d > daily_fip_max:
            continue
        if f.fip_w_inflection >= 0:      # weekly must be moving toward smoother
            continue
        out.append(f)
    return out


def _pct_rank(series: pd.Series, lower_is_better: bool) -> pd.Series:
    """Return a percentile in [0,1] where HIGHER = better. NaNs map to 0.

    For lower_is_better=True we rank with pandas ascending=False so the
    smallest input value lands at pct ≈ 1.0; for higher_is_better=True we
    use ascending=True so the largest value tops the distribution. NaNs
    are excluded from the rank (na_option="keep") and then filled to 0
    so missing fundamentals never look like a virtue.
    """
    r = series.rank(ascending=not lower_is_better, pct=True, na_option="keep")
    return r.fillna(0.0)


def build_screen_table(
    fips: list[FIPResult],
    funds: dict[str, Fundamentals],
    universe: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    weights = weights or {
        "pb": 0.20,
        "ev_ebitda": 0.25,
        "rev_growth": 0.25,
        "rev_inflection": 0.20,
        "fip_d": 0.10,  # tiebreaker: smoother daily FIP is better
    }

    rows = []
    for f in fips:
        fu = funds.get(f.symbol)
        if fu is None:
            continue
        meta = universe.loc[f.symbol] if f.symbol in universe.index else None
        rows.append({
            "symbol": f.symbol,
            "name": fu.name,
            "sector": fu.sector or (meta["sector"] if meta is not None and "sector" in meta else ""),
            "country": meta["country"] if meta is not None and "country" in meta else "",
            "market_cap_bucket": meta["market_cap"] if meta is not None and "market_cap" in meta else "",
            "market_cap": fu.market_cap,
            "last_price": f.last_price,
            "pret_d": f.pret_d,
            "fip_d": f.fip_d,
            "pret_w": f.pret_w,
            "fip_w": f.fip_w,
            "fip_w_prev": f.fip_w_prev,
            "fip_w_inflection": f.fip_w_inflection,
            "pb": fu.pb,
            "ev_ebitda": fu.ev_ebitda,
            "rev_growth": fu.rev_growth,
            "rev_growth_prev": fu.rev_growth_prev,
            "rev_growth_inflection": fu.rev_growth_inflection,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Guard: P/B and EV/EBITDA should be positive to be meaningful as "low is good".
    pb_clean = df["pb"].where(df["pb"] > 0)
    ev_clean = df["ev_ebitda"].where(df["ev_ebitda"] > 0)

    rank_pb = _pct_rank(pb_clean, lower_is_better=True)
    rank_ev = _pct_rank(ev_clean, lower_is_better=True)
    rank_g = _pct_rank(df["rev_growth"], lower_is_better=False)
    rank_inf = _pct_rank(df["rev_growth_inflection"], lower_is_better=False)
    rank_fip = _pct_rank(df["fip_d"], lower_is_better=True)

    df["score"] = (
        weights["pb"] * rank_pb
        + weights["ev_ebitda"] * rank_ev
        + weights["rev_growth"] * rank_g
        + weights["rev_inflection"] * rank_inf
        + weights["fip_d"] * rank_fip
    )

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["momentum", "qulla"], default="momentum",
                    help="momentum: original price-FIP screen. "
                         "qulla: RS-vs-SPX FIP + volatility-asymmetry (Qullamaggie).")
    ap.add_argument("--out", default="frog_in_pan_screen.csv", help="Output CSV path.")
    ap.add_argument("--limit", type=int, default=0, help="Cap universe size for a quick run (0 = no cap).")
    ap.add_argument("--daily-fip-max", type=float, default=-0.05,
                    help="(momentum) Daily FIP must be <= this to qualify.")
    ap.add_argument("--rs-fip-max", type=float, default=-0.03,
                    help="(qulla) Daily FIP on the RS line must be <= this.")
    ap.add_argument("--asym-monthly-low", type=float, default=40.0,
                    help="(qulla) Monthly volatility asymmetry must be >= this. "
                         "'near 50' interpreted as 50 +/- 10 by default.")
    ap.add_argument("--asym-monthly-high", type=float, default=60.0,
                    help="(qulla) Monthly volatility asymmetry must be <= this.")
    ap.add_argument("--asym-weekly-max", type=float, default=65.0,
                    help="(qulla) Weekly volatility asymmetry must be < this "
                         "('preferably low but above its MA').")
    ap.add_argument("--top", type=int, default=50, help="Print top-N rows to stdout.")
    ap.add_argument("--cooldown", type=int, default=60,
                    help="Seconds to pause between price download and fundamentals phase.")
    ap.add_argument("--no-cache", action="store_true", help="Ignore the on-disk price cache.")
    ap.add_argument("--all-listings", action="store_true",
                    help="Disable primary-ticker dedup (keep every cross-listing).")
    args = ap.parse_args()

    print(f"Mode: {args.mode}")
    print("Loading universe (financedatabase, EU + UK, small & mid cap) ...")
    universe = load_universe(primary_only=not args.all_listings)
    print(f"  universe size: {len(universe)} (primary_only={not args.all_listings})")
    symbols = list(universe.index.astype(str))
    if args.limit:
        symbols = symbols[: args.limit]
        universe = universe.loc[symbols]
        print(f"  capped to {len(symbols)} for this run")

    if args.mode == "momentum":
        return _run_momentum(args, universe, symbols)
    else:
        return _run_qulla(args, universe, symbols)


def _run_momentum(args, universe, symbols):
    print("Downloading 2y daily prices ...")
    prices = download_prices(symbols, use_cache=not args.no_cache)
    print(f"  got prices for {len(prices)}/{len(symbols)} symbols")

    print("Computing FIP scores (daily + weekly + weekly inflection) ...")
    fips: list[FIPResult] = []
    for sym, s in prices.items():
        try:
            r = compute_fip(sym, s)
        except Exception:  # noqa: BLE001
            r = None
        if r is not None:
            fips.append(r)
    print(f"  FIP computed for {len(fips)} symbols")

    candidates = filter_fip_candidates(fips, daily_fip_max=args.daily_fip_max)
    print(f"  passed FIP filter: {len(candidates)}")
    if not candidates:
        print("No FIP candidates passed the filter. Try loosening --daily-fip-max.")
        return 1

    if args.cooldown > 0:
        print(f"Cooling down {args.cooldown}s before fundamentals phase to ease rate limiting ...")
        time.sleep(args.cooldown)

    print("Fetching fundamentals (P/B, EV/EBITDA, revenue growth) ...")
    funds = fetch_fundamentals_parallel([c.symbol for c in candidates])
    print(f"  fundamentals for {len(funds)} candidates")

    table = build_screen_table(candidates, funds, universe)
    if table.empty:
        print("No rows after merging fundamentals.")
        return 1

    table.to_csv(args.out, index=False)
    print(f"\nWrote {len(table)} rows to {args.out}")
    show_cols = [
        "symbol", "name", "country", "market_cap_bucket", "sector",
        "pret_d", "fip_d", "fip_w", "fip_w_inflection",
        "pb", "ev_ebitda", "rev_growth", "rev_growth_inflection", "score",
    ]
    with pd.option_context("display.max_rows", args.top, "display.width", 220, "display.max_colwidth", 32):
        print("\nTop candidates:\n")
        print(table[show_cols].head(args.top).to_string(index=False))
    return 0


def _run_qulla(args, universe, symbols):
    print("Fetching SPX (^GSPC) benchmark ...")
    spx = fetch_spx_close(period="2y")
    if spx.empty:
        print("Could not fetch SPX; aborting.")
        return 1
    print(f"  SPX: {len(spx)} bars")

    print("Downloading 2y daily OHLC for universe ...")
    ohlc_map = download_ohlc(symbols, use_cache=not args.no_cache)
    print(f"  got OHLC for {len(ohlc_map)}/{len(symbols)} symbols")

    print("Computing RS-FIP + volatility-asymmetry metrics ...")
    qrs: list[QullaResult] = []
    for sym, df in ohlc_map.items():
        try:
            q = compute_qulla(sym, df, spx)
        except Exception:  # noqa: BLE001
            q = None
        if q is not None:
            qrs.append(q)
    print(f"  Qullamaggie metrics for {len(qrs)} symbols")

    candidates = filter_qulla_candidates(
        qrs,
        daily_rs_fip_max=args.rs_fip_max,
        asym_m_band=(args.asym_monthly_low, args.asym_monthly_high),
        asym_w_max=args.asym_weekly_max,
    )
    print(f"  passed Qullamaggie filter: {len(candidates)}")
    if not candidates:
        print("No Qullamaggie candidates passed the filter. "
              "Try loosening --rs-fip-max or widening --asym-monthly-* bounds.")
        return 1

    if args.cooldown > 0:
        print(f"Cooling down {args.cooldown}s before fundamentals phase ...")
        time.sleep(args.cooldown)

    print("Fetching fundamentals (P/B, EV/EBITDA, revenue growth) ...")
    funds = fetch_fundamentals_parallel([c.symbol for c in candidates])
    print(f"  fundamentals for {len(funds)} candidates")

    table = build_qulla_table(candidates, funds, universe)
    if table.empty:
        print("No rows after building Qullamaggie table.")
        return 1

    table.to_csv(args.out, index=False)
    print(f"\nWrote {len(table)} rows to {args.out}")
    show_cols = [
        "symbol", "name", "country", "sector",
        "rs_pret_d", "rs_fip_d", "rs_fip_w_inflection",
        "asym_m_last", "asym_w_last", "asym_w_above_ma", "asym_w_roc5",
        "va_fip_d",
        "pb", "ev_ebitda", "rev_growth", "rev_growth_inflection", "score",
    ]
    with pd.option_context("display.max_rows", args.top, "display.width", 240, "display.max_colwidth", 30):
        print("\nTop Qullamaggie / RS-breakout candidates:\n")
        print(table[show_cols].head(args.top).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
