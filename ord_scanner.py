"""
Ord Price/Volume + Volatility Asymmetry + Squeeze Release Scanner
==================================================================

Scans the S&P 500 for weekly and monthly breakout candidates by combining
Tim Ord's methodology (*The Secret Science of Price and Volume*, 2008) with
a TTM-style Bollinger/Keltner squeeze release detector and an up/down
volatility-asymmetry filter.

Signal stack (see spec sections referenced):
    1. Zigzag swings (spec §2.1) -> legs with Ord-Volume = mean(volume)
    2. Ord-Volume buy condition (spec §3.2): last completed down leg has
       OV <= ~50% of the prior up leg, followed by an expanding up leg.
    3. Swing P&V low-volume retest (spec §4.1-§4.2).
    4. TTM-style squeeze: Bollinger Bands inside Keltner Channels, plus
       recent release (squeeze-off flip) and BB-width percentile compression.
    5. Volatility asymmetry: up-bar volume * range >> down-bar volume * range
       over the last N bars.
    6. Trend regime filter: close > 50-period MA on the active timeframe.

The composite score ranks weekly and monthly breakout candidates.

Usage
-----
    python ord_scanner.py                 # weekly + monthly, top 25 each
    python ord_scanner.py --tf W
    python ord_scanner.py --tf M --top 50
    python ord_scanner.py --tickers AAPL MSFT NVDA

Dependencies: yfinance, pandas, numpy, lxml (for pd.read_html).
"""
from __future__ import annotations

import argparse
import sys
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# -------- Calibration constants (see spec Appendix B) ---------------------

SWING_THETA = {"W": 0.05, "M": 0.10}      # zigzag reversal threshold per TF
LOOKBACK    = {"W": "5y", "M": "max"}
INTERVAL    = {"W": "1wk", "M": "1mo"}
MIN_BARS    = {"W": 40,   "M": 24}

OV_TRIGGER_STOCK = 0.55        # fuzzy upper bound of the 50% rule
OV_CONFIRM_STOCK = 1.30        # relaxed 1.5x to catch early-stage breakouts
OV_STRONG_SHRINK = 0.30
OV_GOOD_SHRINK   = 0.50
OV_MARGINAL_SHRINK = 0.55

SPV_REVERSAL_MAX    = 0.92     # retest vol <= 92% of origin = reversal
SPV_CONTINUATION_MIN = 0.97

BB_LENGTH = 20
BB_MULT   = 2.0
KC_LENGTH = 20
KC_MULT   = 1.5
SQUEEZE_BW_PCTL = 0.25         # BB width in bottom 25% of history = loaded

ASYMMETRY_WINDOW = 20          # bars for up/down vol asymmetry
ASYM_MIN_BULLISH = 1.20

TREND_MA = 50

# Consolidation envelope tolerance per timeframe (Ord's "cause" measurement)
CONSOL_TOL = {"W": 0.12, "M": 0.20}

# Regime-strength lookback per timeframe (bars used for SPY rolling return
# that classifies up / chop / down market regimes by tercile)
REGIME_LOOKBACK = {"W": 13, "M": 6}

# ---------------------------------------------------------------------------

def fetch_sp500_tickers() -> List[str]:
    """Fetch the current S&P 500 constituent list.

    Wikipedia blocks default Python user-agents with 403, so route the
    request through `requests` with a real UA and hand the HTML to
    pandas.read_html. Falls back to a static datahub mirror, then to a
    hardcoded large-cap list.
    """
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    # primary: Wikipedia
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        syms = tables[0]["Symbol"].astype(str).tolist()
        return [s.replace(".", "-") for s in syms]
    except Exception as e:
        print(f"[warn] wikipedia fetch failed ({e}); trying datahub mirror", file=sys.stderr)
    # secondary: datahub constituents CSV
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        syms = pd.read_csv(io.StringIO(r.text))["Symbol"].astype(str).tolist()
        return [s.replace(".", "-") for s in syms]
    except Exception as e:
        print(f"[warn] datahub fetch failed ({e}); using fallback list", file=sys.stderr)
    return FALLBACK_SP500


def fetch_sp400_tickers() -> List[str]:
    """Fetch S&P MidCap 400 constituents from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        syms = tables[0]["Symbol"].astype(str).tolist()
        return [s.replace(".", "-") for s in syms]
    except Exception as e:
        print(f"[warn] SP400 wiki fetch failed ({e})", file=sys.stderr)
        return []


def fetch_sp600_tickers() -> List[str]:
    """Fetch S&P SmallCap 600 constituents from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        syms = tables[0]["Symbol"].astype(str).tolist()
        return [s.replace(".", "-") for s in syms]
    except Exception as e:
        print(f"[warn] SP600 wiki fetch failed ({e})", file=sys.stderr)
        return []


def fetch_ftse250_tickers() -> List[str]:
    """Fetch FTSE 250 (UK mid-cap) constituents from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/FTSE_250_Index",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            for col in ("Ticker", "EPIC", "Epic", "ticker", "Symbol"):
                if col in t.columns:
                    syms = t[col].astype(str).tolist()
                    return [s.strip().replace(".", "") + ".L" for s in syms if len(s.strip()) <= 6]
        print("[warn] FTSE250: could not find ticker column", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[warn] FTSE250 fetch failed ({e})", file=sys.stderr)
        return []


def fetch_ftse_smallcap_tickers() -> List[str]:
    """Fetch FTSE SmallCap constituents from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/FTSE_SmallCap_Index",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            for col in ("Ticker", "EPIC", "Epic", "ticker", "Symbol"):
                if col in t.columns:
                    syms = t[col].astype(str).tolist()
                    return [s.strip().replace(".", "") + ".L" for s in syms if len(s.strip()) <= 6]
        print("[warn] FTSE SmallCap: could not find ticker column", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[warn] FTSE SmallCap fetch failed ({e})", file=sys.stderr)
        return []


def fetch_aim100_tickers() -> List[str]:
    """Fetch AIM 100 (UK micro/small) tickers from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/FTSE_AIM_100_Index",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            for col in ("Ticker", "EPIC", "Epic", "ticker", "Symbol"):
                if col in t.columns:
                    syms = t[col].astype(str).tolist()
                    return [s.strip().replace(".", "") + ".L" for s in syms if len(s.strip()) <= 6]
        print("[warn] AIM100: could not find ticker column", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[warn] AIM100 fetch failed ({e})", file=sys.stderr)
        return []


def fetch_asx200_tickers() -> List[str]:
    """Fetch S&P/ASX 200 constituents from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/S%26P/ASX_200",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            for col in ("Code", "Ticker", "Symbol", "ASX code"):
                if col in t.columns:
                    syms = t[col].astype(str).tolist()
                    return [s.strip() + ".AX" for s in syms if len(s.strip()) <= 5 and s.strip().isalpha()]
        print("[warn] ASX200: could not find ticker column", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[warn] ASX200 fetch failed ({e})", file=sys.stderr)
        return []


def fetch_asx_smallords_tickers() -> List[str]:
    """Fetch S&P/ASX Small Ordinaries from Wikipedia."""
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/S%26P/ASX_Small_Ordinaries",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            for col in ("Code", "Ticker", "Symbol", "ASX code"):
                if col in t.columns:
                    syms = t[col].astype(str).tolist()
                    return [s.strip() + ".AX" for s in syms if len(s.strip()) <= 5 and s.strip().isalpha()]
        print("[warn] ASX SmallOrds: could not find ticker column", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[warn] ASX SmallOrds fetch failed ({e})", file=sys.stderr)
        return []


def fetch_ftse_mib_tickers() -> List[str]:
    """Fetch Italian stocks on Milan exchange via financedatabase."""
    try:
        import financedatabase as fd
        eq = fd.Equities()
        it = eq.search(country="Italy", exchange="MIL")
        tickers = [str(idx) for idx in it.index if isinstance(idx, str) and ".MI" in str(idx)]
        if tickers:
            print(f"[italy] {len(tickers)} Milan tickers via financedatabase")
            return tickers
    except Exception as e:
        print(f"[warn] financedatabase Italy failed ({e})", file=sys.stderr)
    # Fallback to Wikipedia
    import io
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (compatible; ord-scanner/1.0)"}
    try:
        r = requests.get(
            "https://en.wikipedia.org/wiki/FTSE_MIB",
            headers=ua, timeout=15,
        )
        r.raise_for_status()
        tables = pd.read_html(io.StringIO(r.text))
        for t in tables:
            for col in ("Ticker", "Ticker symbol", "Symbol", "Epic"):
                if col in t.columns:
                    syms = t[col].astype(str).tolist()
                    return [s.strip() + ".MI" for s in syms if len(s.strip()) <= 6 and s.strip().isalpha()]
    except Exception:
        pass
    return []


def fetch_italy_midcap_tickers() -> List[str]:
    """Fetch Italian mid/small caps — returns tickers not in FTSE MIB."""
    mib = set(fetch_ftse_mib_tickers())
    try:
        import financedatabase as fd
        eq = fd.Equities()
        it = eq.search(country="Italy", exchange="MIL")
        all_milan = [str(idx) for idx in it.index if isinstance(idx, str) and ".MI" in str(idx)]
        midsmall = [t for t in all_milan if t not in mib]
        print(f"[italy_mid] {len(midsmall)} mid/small tickers")
        return midsmall
    except Exception as e:
        print(f"[warn] Italy midcap via financedatabase failed ({e})", file=sys.stderr)
        return []


def _fd_uk_tickers() -> List[str]:
    """Fetch all UK LSE tickers via financedatabase."""
    try:
        import financedatabase as fd
        eq = fd.Equities()
        uk = eq.search(country="United Kingdom", exchange="LSE")
        tickers = [str(idx) for idx in uk.index if isinstance(idx, str) and ".L" in str(idx)]
        print(f"[uk_fd] {len(tickers)} LSE tickers via financedatabase")
        return tickers
    except Exception as e:
        print(f"[warn] financedatabase UK failed ({e})", file=sys.stderr)
        return []


BENCHMARK_MAP = {
    "sp500": "SPY", "sp400": "SPY", "sp600": "SPY", "smid": "SPY", "all": "SPY",
    "uk": "ISF.L", "uk_mid": "ISF.L", "uk_small": "ISF.L", "uk_aim": "ISF.L",
    "asx": "STW.AX", "asx_small": "STW.AX", "asx_all": "STW.AX",
    "italy": "ENI.MI", "italy_mid": "ENI.MI",
}


def fetch_universe(name: str) -> List[str]:
    """Fetch tickers for a named universe."""
    name = name.lower()
    if name == "sp500":
        return fetch_sp500_tickers()
    elif name == "sp400":
        return fetch_sp400_tickers()
    elif name == "sp600":
        return fetch_sp600_tickers()
    elif name in ("smid", "sp400+sp600"):
        return fetch_sp400_tickers() + fetch_sp600_tickers()
    elif name == "all":
        return fetch_sp500_tickers() + fetch_sp400_tickers() + fetch_sp600_tickers()
    # UK
    elif name == "uk":
        wiki = fetch_ftse250_tickers() + fetch_ftse_smallcap_tickers() + fetch_aim100_tickers()
        fd = _fd_uk_tickers()
        combined = list(dict.fromkeys(wiki + fd))  # dedup preserving order
        return combined if combined else wiki or fd
    elif name == "uk_mid":
        return fetch_ftse250_tickers()
    elif name == "uk_small":
        return fetch_ftse_smallcap_tickers() + fetch_aim100_tickers()
    elif name == "uk_aim":
        return fetch_aim100_tickers()
    elif name == "uk_all":
        return _fd_uk_tickers()
    # Australia
    elif name == "asx":
        return fetch_asx200_tickers()
    elif name == "asx_small":
        return fetch_asx_smallords_tickers()
    elif name == "asx_all":
        return fetch_asx200_tickers() + fetch_asx_smallords_tickers()
    # Italy
    elif name == "italy":
        return fetch_ftse_mib_tickers() + fetch_italy_midcap_tickers()
    elif name == "italy_mid":
        return fetch_italy_midcap_tickers()
    else:
        print(f"[warn] unknown universe '{name}'; defaulting to sp500", file=sys.stderr)
        return fetch_sp500_tickers()


# Minimal fallback if wiki is unreachable (top 50 by weight, roughly).
FALLBACK_SP500 = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","BRK-B","LLY","AVGO",
    "JPM","TSLA","UNH","XOM","V","PG","MA","HD","COST","JNJ",
    "MRK","ABBV","NFLX","CVX","CRM","BAC","AMD","PEP","KO","LIN",
    "ADBE","TMO","WMT","ORCL","MCD","CSCO","WFC","ACN","PM","IBM",
    "ABT","GE","TXN","DIS","CAT","VZ","QCOM","INTU","GS","DHR",
]


# ---------------------------------------------------------------------------
# Swing / leg / Ord-Volume primitives
# ---------------------------------------------------------------------------

def zigzag(high: pd.Series, low: pd.Series, theta: float) -> List[tuple]:
    """Percentage-reversal zigzag.

    Returns a list of pivots as (idx, price, direction) where direction is
    +1 for a high pivot and -1 for a low pivot. The final pivot is the
    running (tentative) extreme, used so that the most recent leg can be
    evaluated before a confirmed reversal.
    """
    n = len(high)
    if n < 5:
        return []

    pivots: List[tuple] = []
    direction = 0  # 0 = unknown, +1 = up leg in progress, -1 = down leg in progress
    ext_i = 0
    ext_hi = float(high.iloc[0])
    ext_lo = float(low.iloc[0])

    for i in range(1, n):
        hi = float(high.iloc[i])
        lo = float(low.iloc[i])

        if direction == 0:
            # establish initial direction from first theta-sized excursion
            if ext_hi > 0 and (ext_hi - lo) / ext_hi >= theta:
                pivots.append((ext_i, ext_hi, +1))
                direction = -1
                ext_i, ext_lo = i, lo
            elif ext_lo > 0 and (hi - ext_lo) / ext_lo >= theta:
                pivots.append((ext_i, ext_lo, -1))
                direction = +1
                ext_i, ext_hi = i, hi
            else:
                if hi > ext_hi:
                    ext_hi, ext_i = hi, i
                if lo < ext_lo:
                    ext_lo = lo
            continue

        if direction == +1:
            # tracking an up leg -- extend on new high, reverse on theta pullback
            if hi > ext_hi:
                ext_hi, ext_i = hi, i
            if ext_hi > 0 and (ext_hi - lo) / ext_hi >= theta:
                pivots.append((ext_i, ext_hi, +1))
                direction = -1
                ext_i, ext_lo = i, lo
        else:  # direction == -1
            if lo < ext_lo:
                ext_lo, ext_i = lo, i
            if ext_lo > 0 and (hi - ext_lo) / ext_lo >= theta:
                pivots.append((ext_i, ext_lo, -1))
                direction = +1
                ext_i, ext_hi = i, hi

    # append the running tentative pivot so legs[-1] = leg in progress
    if direction == +1:
        pivots.append((ext_i, ext_hi, +1))
    elif direction == -1:
        pivots.append((ext_i, ext_lo, -1))
    return pivots


def build_legs(df: pd.DataFrame, pivots: List[tuple]) -> List[Dict]:
    """Materialise legs between consecutive pivots with Ord-Volume (mean)."""
    legs: List[Dict] = []
    for k in range(len(pivots) - 1):
        a_i, a_p, _ = pivots[k]
        b_i, b_p, _ = pivots[k + 1]
        if b_i <= a_i:
            continue
        seg = df.iloc[a_i:b_i + 1]
        ov = float(seg["Volume"].mean())
        legs.append({
            "start_idx": a_i,
            "end_idx": b_i,
            "start_price": float(a_p),
            "end_price": float(b_p),
            "n_bars": b_i - a_i + 1,
            "ov": ov,
            "dir": "up" if b_p > a_p else "down",
        })
    return legs


def ord_volume_buy(df: pd.DataFrame, legs: List[Dict]) -> Dict:
    """Spec §3.2 Ord-Volume buy signal (faithful).

    Pattern:
        ..., prev_down, prev_up, L_down (current/just-completed), L_current (up)
    Conditions:
        1. OV(L_down) <= 0.50 * OV(prev_up)   OR   <= 0.50 * OV(prev_down)
        2. During L_down, low[t] <= prev_low   (a probe of the prior swing low)
        3. close[now] > prev_low               (price closed back above)
    Confirmation (§3.2):
        OV(L_current) >= 1.50 * OV(L_down)
    Returns both a strict (spec) and a loose variant (probe dropped, 1.30x expand)
    so the scanner can rank partial setups.
    """
    if len(legs) < 4:
        return {"signal": False, "reason": "need >=4 legs"}
    L_current = legs[-1]
    L_down    = legs[-2]
    prev_up   = legs[-3]
    prev_down = legs[-4]
    if L_current["dir"] != "up" or L_down["dir"] != "down":
        return {"signal": False, "reason": "leg direction mismatch"}
    if prev_up["dir"] != "up" or prev_down["dir"] != "down":
        return {"signal": False, "reason": "insufficient prior legs"}

    # prior swing low = low at end of prev_down (where prev_up started)
    prior_low = float(prev_down["end_price"])

    # (a) probe: L_down's recorded swing low < prior_low?
    probed = float(L_down["end_price"]) < prior_low

    # (b) close back above prior_low
    closed_back = float(df["Close"].iloc[-1]) > prior_low

    # (c) volume shrinkage: spec OR comparator
    shrink_up   = L_down["ov"] / prev_up["ov"]   if prev_up["ov"]   > 0 else float("inf")
    shrink_down = L_down["ov"] / prev_down["ov"] if prev_down["ov"] > 0 else float("inf")
    best_shrink = min(shrink_up, shrink_down)

    expand = L_current["ov"] / L_down["ov"] if L_down["ov"] > 0 else 0.0

    if best_shrink <= 0.25:
        strength = "STRONG"
    elif best_shrink <= 0.50:
        strength = "GOOD"
    elif best_shrink <= 0.55:
        strength = "MARGINAL"
    else:
        strength = None

    signal_strict = (strength is not None) and probed and closed_back
    signal_loose  = (strength is not None) and closed_back

    return {
        "signal": signal_strict,
        "signal_loose": signal_loose,
        "strength": strength or "NONE",
        "shrink": float(best_shrink),
        "shrink_vs_up": float(shrink_up),
        "shrink_vs_down": float(shrink_down),
        "expand": float(expand),
        "confirmed":       bool(expand >= 1.50),
        "confirmed_loose": bool(expand >= 1.30),
        "probed": bool(probed),
        "closed_back": bool(closed_back),
    }


def shakeout_retest(df: pd.DataFrame, legs: List[Dict]) -> Dict:
    """Spec §4.2(f) False Breakout Bottom / Wyckoff shakeout detector.

    Looks *within the most recent down leg* for any bar whose low pierces the
    prior swing low. Volume of the deepest probe bar is compared to the
    volume of the bar that ORIGINATED the prior swing low. Ratio <= 0.92
    with price subsequently closing back above prior_low = shakeout trigger.
    """
    if len(legs) < 4:
        return {"signal": False}
    L_down    = legs[-2]
    prev_down = legs[-4]
    if L_down["dir"] != "down" or prev_down["dir"] != "down":
        return {"signal": False}

    origin_idx = int(prev_down["end_idx"])
    origin_low = float(df["Low"].iloc[origin_idx])
    origin_vol = float(df["Volume"].iloc[origin_idx])
    if origin_vol <= 0:
        return {"signal": False}

    start = int(L_down["start_idx"])
    end   = int(L_down["end_idx"]) + 1
    if end <= start + 1:
        return {"signal": False}
    seg = df.iloc[start:end]
    probes = seg[seg["Low"] <= origin_low]
    if probes.empty:
        return {"signal": False}
    probe_vol = float(probes["Volume"].min())
    ratio = probe_vol / origin_vol
    closed_back = float(df["Close"].iloc[-1]) > origin_low

    return {
        "signal": bool(ratio <= SPV_REVERSAL_MAX and closed_back),
        "ratio": float(ratio),
        "closed_back": bool(closed_back),
    }


def selling_climax(df: pd.DataFrame) -> Dict:
    """Spec §4.2(g) Selling Climax Day detection.

    A climax bar has volume >= 1.20 × max(volume, prior 5 bars) on a
    wide-range-down bar. The buy trigger is a subsequent retest of the
    climax low on volume <= 0.92 × climax volume with close above.

    On weekly/monthly bars this detects capitulation washouts.
    """
    n = len(df)
    if n < 10:
        return {"climax": False, "climax_retest": False}
    vol = df["Volume"].values.astype(float)
    low = df["Low"].values.astype(float)
    high = df["High"].values.astype(float)
    close = df["Close"].values.astype(float)
    opn = df["Open"].values.astype(float)

    # Search last 20 bars for a climax bar
    best_climax_idx = None
    for i in range(max(5, n - 20), n - 1):
        prior_max_vol = max(vol[max(0, i - 5):i])
        if prior_max_vol <= 0:
            continue
        if vol[i] >= 1.20 * prior_max_vol:
            bar_range = high[i] - low[i]
            # Wide range down: close in bottom 30% of bar
            if bar_range > 0 and (close[i] - low[i]) / bar_range <= 0.35:
                best_climax_idx = i

    if best_climax_idx is None:
        return {"climax": False, "climax_retest": False}

    climax_vol = vol[best_climax_idx]
    climax_low = low[best_climax_idx]

    # Look for retest: any bar after climax that probes climax_low on lower vol
    retest_found = False
    for j in range(best_climax_idx + 1, n):
        if low[j] <= climax_low * 1.02:
            if vol[j] <= 0.92 * climax_vol and close[j] > climax_low:
                retest_found = True
                break

    return {
        "climax": True,
        "climax_retest": retest_found,
        "climax_vol_ratio": round(vol[best_climax_idx] / max(vol[max(0, best_climax_idx - 5):best_climax_idx]), 2) if best_climax_idx else np.nan,
    }


def multi_leg_dissipation(legs: List[Dict]) -> Dict:
    """Spec §3.5 Multi-leg dissipation pattern.

    Three or more sequential down legs with monotonically decreasing OV.
    Signals selling exhaustion. The trigger is the first up leg whose OV
    exceeds the most recent down leg by even 5-10%.
    """
    if len(legs) < 5:
        return {"dissipation": False, "diss_legs": 0}

    # Collect the last N down legs in sequence
    down_legs = [L for L in legs[:-1] if L["dir"] == "down"]
    if len(down_legs) < 3:
        return {"dissipation": False, "diss_legs": 0}

    # Check if the last 3+ down legs have monotonically decreasing OV
    recent_downs = down_legs[-4:]  # up to last 4 down legs
    mono_count = 1
    for i in range(len(recent_downs) - 1, 0, -1):
        if recent_downs[i]["ov"] < recent_downs[i - 1]["ov"]:
            mono_count += 1
        else:
            break

    if mono_count < 3:
        return {"dissipation": False, "diss_legs": mono_count}

    # Check if current up leg exceeds the last down leg's OV
    current = legs[-1]
    last_down = down_legs[-1]
    if current["dir"] == "up" and last_down["ov"] > 0:
        expansion = current["ov"] / last_down["ov"]
        triggered = expansion >= 1.05
    else:
        expansion = 0.0
        triggered = False

    return {
        "dissipation": True,
        "diss_triggered": triggered,
        "diss_legs": mono_count,
        "diss_expansion": round(expansion, 2),
    }


def gap_test(df: pd.DataFrame) -> Dict:
    """Spec §5 Gap Test method.

    Detects gaps (size >= 0.5 * ATR(20), gap-day volume >= 1.5 * avg(20))
    and checks if a subsequent pullback into the gap zone occurred on
    shrinking volume (<=0.90 × gap-day volume) with close holding above gap_low.
    """
    n = len(df)
    if n < 25:
        return {"gap_found": False, "gap_test_bull": False}

    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    vol = df["Volume"].values.astype(float)

    # ATR(20)
    tr = np.maximum(high[1:] - low[1:],
         np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    if len(tr) < 20:
        return {"gap_found": False, "gap_test_bull": False}
    atr20 = float(np.mean(tr[-20:]))
    vol_avg20 = float(np.mean(vol[-20:]))

    # Search for bullish gaps in last 20 bars
    best_gap = None
    for i in range(max(1, n - 20), n):
        gap_size = low[i] - high[i - 1]
        if gap_size > 0.5 * atr20 and vol[i] >= 1.5 * vol_avg20:
            best_gap = {"idx": i, "gap_low": float(high[i - 1]),
                        "gap_high": float(low[i]), "gap_vol": float(vol[i])}

    if best_gap is None:
        return {"gap_found": False, "gap_test_bull": False}

    # Look for pullback into gap zone on lower volume
    gi = best_gap["idx"]
    gap_low = best_gap["gap_low"]
    gap_vol = best_gap["gap_vol"]
    test_found = False
    for j in range(gi + 1, n):
        if low[j] <= best_gap["gap_high"]:  # entered gap zone
            if vol[j] <= 0.90 * gap_vol and close[j] > gap_low:
                test_found = True
                break

    return {
        "gap_found": True,
        "gap_test_bull": test_found,
        "gap_vol_ratio": round(vol[min(gi + 1, n - 1)] / gap_vol, 2) if gap_vol > 0 else np.nan,
    }


def _compute_mfi_cmf(df: pd.DataFrame, mfi_period: int = 18,
                     cmf_period: int = 20) -> tuple:
    """Compute MFI and CMF series from an OHLCV DataFrame."""
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)
    hl = (high - low).replace(0, np.nan)
    mfm = ((close - low) - (high - close)) / hl
    mfv = mfm * vol
    cmf = mfv.rolling(cmf_period).sum() / vol.rolling(cmf_period).sum()
    tp = (high + low + close) / 3.0
    tp_diff = tp.diff()
    raw_mf = tp * vol
    pos_mf = (raw_mf.where(tp_diff > 0, 0)).rolling(mfi_period).sum()
    neg_mf = (raw_mf.where(tp_diff < 0, 0)).rolling(mfi_period).sum()
    mfi = 100.0 - (100.0 / (1.0 + pos_mf / neg_mf.replace(0, np.nan)))
    return mfi, cmf


def _detect_zero_cross(series: pd.Series, threshold: float,
                       lookback: int) -> tuple:
    """Return (crossed, cross_idx) for series crossing above threshold."""
    n = len(series)
    window = min(lookback + 1, n)
    vals = series.iloc[-window:].values
    crossed, cross_idx = False, -1
    for i in range(1, len(vals)):
        if np.isfinite(vals[i - 1]) and np.isfinite(vals[i]):
            if vals[i - 1] < threshold and vals[i] >= threshold:
                crossed = True
                cross_idx = n - window + i
    return crossed, cross_idx


def _tcap_pair(trigger_df: pd.DataFrame, struct_df: pd.DataFrame,
               mfi_period: int = 18, cmf_period: int = 20,
               trigger_lookback: int = 8, struct_lookback: int = 6) -> Dict:
    """Core TCAP detection for any two-timeframe pair.

    trigger_df = faster TF (daily for D/W pair, weekly for W/M pair)
    struct_df  = slower TF (weekly for D/W pair, monthly for W/M pair)

    Returns:
      trigger_x:    trigger TF MFI crossed above 50 recently
      struct_near:  structural TF MFI is near 50 (30-70)
      struct_impr:  structural TF MFI improving (now > recent avg > prior avg)
      vol_spike:    structural TF volume spiked (>1.5x 20-bar avg)
      full:         all three aligned
    """
    out = {"trigger_x": False, "struct_mfi_now": np.nan,
           "struct_near": False, "struct_impr": False,
           "vol_spike": False, "full": False}

    # Structural TF: MFI near 50 and improving
    sn = len(struct_df)
    if sn < mfi_period + struct_lookback + 5:
        return out
    s_mfi, s_cmf = _compute_mfi_cmf(struct_df, mfi_period, cmf_period)
    s_mfi_now = float(s_mfi.iloc[-1]) if np.isfinite(s_mfi.iloc[-1]) else np.nan
    out["struct_mfi_now"] = round(s_mfi_now, 1) if np.isfinite(s_mfi_now) else np.nan
    s_recent = float(s_mfi.iloc[-struct_lookback:].mean()) if s_mfi.iloc[-struct_lookback:].notna().any() else np.nan
    ps, pe = max(0, sn - struct_lookback * 2), max(0, sn - struct_lookback)
    s_prior = float(s_mfi.iloc[ps:pe].mean()) if pe > ps and s_mfi.iloc[ps:pe].notna().any() else np.nan
    out["struct_near"] = bool(np.isfinite(s_mfi_now) and 30 <= s_mfi_now <= 70)
    out["struct_impr"] = bool(
        np.isfinite(s_mfi_now) and np.isfinite(s_recent) and np.isfinite(s_prior)
        and s_mfi_now > s_recent and s_recent > s_prior
    )

    # Volume spike on structural TF
    s_vol = struct_df["Volume"].astype(float)
    vol_avg = float(s_vol.rolling(20).mean().iloc[-1]) if sn >= 20 else float(s_vol.mean())
    if vol_avg > 0:
        out["vol_spike"] = bool(float(s_vol.iloc[-1]) > 1.5 * vol_avg)

    # Trigger TF: MFI crosses above 50 recently
    if trigger_df is not None and len(trigger_df) >= mfi_period + trigger_lookback + 5:
        t_mfi, _ = _compute_mfi_cmf(trigger_df, mfi_period, cmf_period)
        out["trigger_x"], _ = _detect_zero_cross(t_mfi, 50.0, trigger_lookback)

    # Full TCAP = trigger cross + structural near 50 & improving + vol spike
    out["full"] = bool(out["trigger_x"] and out["struct_near"]
                       and out["struct_impr"] and out["vol_spike"])
    return out


def mfi_zero_cross(weekly_df: pd.DataFrame,
                   daily_df: Optional[pd.DataFrame] = None,
                   monthly_df: Optional[pd.DataFrame] = None,
                   mfi_period: int = 18, cmf_period: int = 20,
                   weekly_lookback: int = 6, daily_lookback: int = 15) -> Dict:
    """Detect TCAP patterns on two timeframe pairs:

    Daily+Weekly TCAP (fast):
      1. Daily MFI(18) crosses above 50 in last 15 days
      2. Weekly MFI near 50 and improving
      3. Weekly volume spike

    Weekly+Monthly TCAP (slow, bigger moves):
      1. Weekly MFI(18) crosses above 50 in last 8 bars
      2. Monthly MFI near 50 and improving
      3. Monthly volume spike

    Also computes standalone weekly CMF/MFI cross signals.
    """
    n = len(weekly_df)
    empty = {"mfi_cross": False, "cmf_cross": False, "mfi50_cross": False,
             "cmf_now": 0.0, "cmf_improving": False, "vol_spike_cross": False,
             "mfi_now": np.nan, "daily_mfi_x": False, "daily_mfi_now": np.nan,
             "full_tcap": False, "tcap_wm": False, "m_mfi_now": np.nan}
    if n < max(mfi_period, cmf_period) + weekly_lookback + 5:
        return empty

    vol = weekly_df["Volume"].astype(float)
    w_mfi, w_cmf = _compute_mfi_cmf(weekly_df, mfi_period, cmf_period)

    # Standalone weekly signals
    cmf_cross, cmf_cross_idx = _detect_zero_cross(w_cmf, 0.0, weekly_lookback)
    mfi50_cross, _ = _detect_zero_cross(w_mfi, 50.0, weekly_lookback)
    cmf_now = float(w_cmf.iloc[-1]) if np.isfinite(w_cmf.iloc[-1]) else 0.0
    cmf_recent = float(w_cmf.iloc[-weekly_lookback:].mean()) if w_cmf.iloc[-weekly_lookback:].notna().any() else 0.0
    ps, pe = max(0, n - weekly_lookback * 2), max(0, n - weekly_lookback)
    cmf_prior = float(w_cmf.iloc[ps:pe].mean()) if pe > ps else 0.0
    cmf_improving = bool(cmf_now > cmf_recent and cmf_recent > cmf_prior)
    vol_avg = float(vol.rolling(20).mean().iloc[-1]) if n >= 20 else float(vol.mean())
    vol_spike = False
    if cmf_cross_idx >= 0 and cmf_cross_idx < n and vol_avg > 0:
        vol_spike = float(vol.iloc[cmf_cross_idx]) > 1.5 * vol_avg
    if not vol_spike and vol_avg > 0:
        vol_spike = float(vol.iloc[-1]) > 1.5 * vol_avg
    weekly_signal = (cmf_cross or mfi50_cross) and (cmf_improving or cmf_now > 0)
    w_mfi_now = float(w_mfi.iloc[-1]) if np.isfinite(w_mfi.iloc[-1]) else np.nan

    # Daily+Weekly TCAP
    dw = _tcap_pair(daily_df, weekly_df, mfi_period, cmf_period,
                    trigger_lookback=daily_lookback, struct_lookback=weekly_lookback)
    full_tcap_dw = dw["full"]
    daily_mfi_x = dw["trigger_x"]
    daily_mfi_now = np.nan
    if daily_df is not None and len(daily_df) >= mfi_period + 5:
        d_mfi, _ = _compute_mfi_cmf(daily_df, mfi_period, cmf_period)
        daily_mfi_now = float(d_mfi.iloc[-1]) if np.isfinite(d_mfi.iloc[-1]) else np.nan

    # Weekly+Monthly TCAP
    wm = _tcap_pair(weekly_df, monthly_df, mfi_period, cmf_period,
                    trigger_lookback=8, struct_lookback=4) if monthly_df is not None else {
                        "full": False, "struct_mfi_now": np.nan}
    tcap_wm = wm["full"]
    m_mfi_now = wm.get("struct_mfi_now", np.nan)

    return {
        "mfi_cross": bool(full_tcap_dw or tcap_wm or weekly_signal),
        "cmf_cross": bool(cmf_cross),
        "mfi50_cross": bool(mfi50_cross),
        "cmf_now": round(cmf_now, 3),
        "cmf_improving": bool(cmf_improving),
        "vol_spike_cross": bool(vol_spike),
        "mfi_now": round(w_mfi_now, 1) if np.isfinite(w_mfi_now) else np.nan,
        "daily_mfi_x": bool(daily_mfi_x),
        "daily_mfi_now": round(daily_mfi_now, 1) if np.isfinite(daily_mfi_now) else np.nan,
        "full_tcap": bool(full_tcap_dw),
        "tcap_wm": bool(tcap_wm),
        "m_mfi_now": round(m_mfi_now, 1) if np.isfinite(m_mfi_now) else np.nan,
    }


def qullamaggie_setup(df: pd.DataFrame) -> Dict:
    """Qullamaggie-style breakout setup on the active timeframe.

    Components (all on the current TF -- weekly or monthly):
      - Moving average stack: MA10 > MA20 > MA50 (rising) with close > MA10
      - Relative strength: positive 13- and 26-bar returns, 26-bar return >= 15%
      - Range compression: ATR(5) / ATR(20) <= 0.85 (tight consolidation)
      - Volume dry-up: avg(volume,5) / avg(volume,20) <= 0.85
      - Breakout proximity: close within 3% of the 20-bar high

    Returns a score in [0..8] plus the component values.
    """
    n = len(df)
    out = {"q_score": 0, "q_stacked": False, "q_ret13": np.nan, "q_ret26": np.nan,
           "q_compression": np.nan, "q_volratio": np.nan, "q_proximity": np.nan,
           "q_breakout": False}
    if n < 55:
        return out

    close = df["Close"].astype(float)
    hi    = df["High"].astype(float)
    lo    = df["Low"].astype(float)
    vol   = df["Volume"].astype(float)

    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    c    = float(close.iloc[-1])
    m10  = float(ma10.iloc[-1])
    m20  = float(ma20.iloc[-1])
    m50  = float(ma50.iloc[-1])

    stacked = (m10 > m20 > m50) and (c > m10)
    ma10_rising = float(ma10.iloc[-1]) > float(ma10.iloc[-5])
    ma20_rising = float(ma20.iloc[-1]) > float(ma20.iloc[-5])

    ret_13 = (c / float(close.iloc[-14]) - 1.0) if n >= 14 else 0.0
    ret_26 = (c / float(close.iloc[-27]) - 1.0) if n >= 27 else 0.0

    prev_close = close.shift()
    tr = pd.concat([
        hi - lo,
        (hi - prev_close).abs(),
        (lo - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr5  = float(tr.rolling(5).mean().iloc[-1])
    atr20 = float(tr.rolling(20).mean().iloc[-1])
    compression = (atr5 / atr20) if atr20 > 0 else 1.0

    v5  = float(vol.rolling(5).mean().iloc[-1])
    v20 = float(vol.rolling(20).mean().iloc[-1])
    volratio = (v5 / v20) if v20 > 0 else 1.0

    hi20 = float(hi.rolling(20).max().iloc[-1])
    proximity = (c / hi20) if hi20 > 0 else 0.0

    # score components
    q = 0
    if stacked and ma10_rising and ma20_rising:
        q += 2
    elif stacked:
        q += 1
    if ret_26 >= 0.25 and ret_13 > 0:
        q += 2
    elif ret_26 >= 0.15:
        q += 1
    if compression <= 0.70:
        q += 2
    elif compression <= 0.85:
        q += 1
    if volratio <= 0.75:
        q += 1
    elif volratio <= 0.90:
        q += 1  # any dry-up helps
    if proximity >= 0.97:
        q += 2
    elif proximity >= 0.93:
        q += 1

    # breakout bar: last close > prior 20-bar high (ex current) on >avg volume
    prior_hi20 = float(hi.iloc[-21:-1].max()) if n >= 21 else np.nan
    prior_vavg = float(vol.iloc[-21:-1].mean()) if n >= 21 else np.nan
    this_vol   = float(vol.iloc[-1])
    breakout = bool(
        pd.notna(prior_hi20)
        and c > prior_hi20
        and this_vol > 1.3 * prior_vavg
    )
    if breakout:
        q += 1

    return {
        "q_score": q,
        "q_stacked": bool(stacked),
        "q_ret13": round(float(ret_13), 3),
        "q_ret26": round(float(ret_26), 3),
        "q_compression": round(float(compression), 2),
        "q_volratio": round(float(volratio), 2),
        "q_proximity": round(float(proximity), 2),
        "q_breakout": breakout,
    }


# ---------------------------------------------------------------------------
# Squeeze + volatility asymmetry
# ---------------------------------------------------------------------------

def squeeze_state(df: pd.DataFrame) -> Dict:
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    prev_close = close.shift()
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(KC_LENGTH).mean()

    ma = close.rolling(BB_LENGTH).mean()
    sd = close.rolling(BB_LENGTH).std()
    bb_up = ma + BB_MULT * sd
    bb_dn = ma - BB_MULT * sd
    kc_up = ma + KC_MULT * atr
    kc_dn = ma - KC_MULT * atr

    in_sq = (bb_up < kc_up) & (bb_dn > kc_dn)
    bw    = (bb_up - bb_dn) / ma

    now_sq = bool(in_sq.iloc[-1]) if not in_sq.empty else False
    recent_sq = bool(in_sq.iloc[-8:-1].any()) if len(in_sq) >= 8 else False
    released = recent_sq and not now_sq

    bw_pctile = float(bw.rank(pct=True).iloc[-1]) if bw.notna().any() else 1.0

    return {
        "in_squeeze": now_sq,
        "released": released,
        "bw_pctile": bw_pctile,
    }


def vol_asymmetry(df: pd.DataFrame, window: int = ASYMMETRY_WINDOW) -> Dict:
    recent = df.iloc[-window:]
    r = recent["Close"].pct_change()
    v = recent["Volume"].astype(float)
    rng = (recent["High"] - recent["Low"]).astype(float)

    up = r > 0
    dn = r < 0
    up_vol = float(v[up].mean()) if up.any() else 0.0
    dn_vol = float(v[dn].mean()) if dn.any() else 0.0
    up_rng = float(rng[up].mean()) if up.any() else 0.0
    dn_rng = float(rng[dn].mean()) if dn.any() else 0.0

    vol_ratio = up_vol / dn_vol if dn_vol > 0 else float("inf")
    rng_ratio = up_rng / dn_rng if dn_rng > 0 else float("inf")
    # cap to avoid inf dominating the composite
    vol_ratio = min(vol_ratio, 5.0)
    rng_ratio = min(rng_ratio, 5.0)
    asym = (vol_ratio + rng_ratio) / 2.0

    return {
        "vol_ratio": vol_ratio,
        "range_ratio": rng_ratio,
        "asymmetry": asym,
    }


# ---------------------------------------------------------------------------
# Consolidation length + regime-conditional strength
# ---------------------------------------------------------------------------

def consolidation_bars(df: pd.DataFrame, tol: float, cap: int = 104) -> int:
    """Count bars back from the current bar that fit inside a single
    expanding high/low envelope. Walking backward, each new bar widens the
    envelope; once (h_max - l_min) / mid exceeds `tol`, the consolidation
    ends. Returns bar count including the current bar (Ord's "cause").
    """
    n = len(df)
    if n < 2:
        return 0
    highs = df["High"].values
    lows  = df["Low"].values
    h = float(highs[-1])
    l = float(lows[-1])
    count = 1
    for i in range(n - 2, max(-1, n - 2 - cap), -1):
        h = max(h, float(highs[i]))
        l = min(l, float(lows[i]))
        mid = (h + l) / 2.0
        if mid <= 0:
            break
        if (h - l) / mid > tol:
            break
        count += 1
    return count


def compute_regime_frame(spy_df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Build a per-bar market-regime label from SPY returns.

    Classifies each bar into one of three regimes by the tercile of SPY's
    rolling `lookback`-bar return:
        down   = bottom third   (market falling)
        chop   = middle third   (market sideways)
        up     = top third      (market rising)
    """
    c = spy_df["Close"].astype(float)
    out = pd.DataFrame(index=spy_df.index)
    out["mr"] = c.pct_change()
    out["mret_look"] = c.pct_change(lookback)
    valid = out["mret_look"].dropna()
    if len(valid) < 30:
        out["regime"] = None
        return out
    q1 = float(valid.quantile(1.0 / 3.0))
    q2 = float(valid.quantile(2.0 / 3.0))
    out["regime"] = pd.cut(
        out["mret_look"],
        bins=[-np.inf, q1, q2, np.inf],
        labels=["down", "chop", "up"],
    )
    return out


def regime_strength(stock_df: pd.DataFrame, regime_df: pd.DataFrame) -> Dict:
    """For each market regime (up / chop / down), compute the stock's mean
    per-bar excess return vs SPY. The all_weather flag is True iff the
    stock posted positive mean excess returns in all three regimes.
    """
    out = {
        "rs_up": np.nan, "rs_chop": np.nan, "rs_down": np.nan,
        "n_up": 0, "n_chop": 0, "n_down": 0,
        "all_weather": False,
    }
    if regime_df.empty or "regime" not in regime_df.columns:
        return out
    aligned = stock_df[["Close"]].join(regime_df[["mr", "regime"]], how="inner")
    aligned["sr"] = aligned["Close"].pct_change()
    aligned = aligned.dropna(subset=["sr", "mr", "regime"])
    if aligned.empty:
        return out
    means = {}
    for r in ("up", "chop", "down"):
        m = aligned["regime"] == r
        cnt = int(m.sum())
        out[f"n_{r}"] = cnt
        if cnt < 5:
            continue
        excess = aligned.loc[m, "sr"] - aligned.loc[m, "mr"]
        means[r] = float(excess.mean())
        out[f"rs_{r}"] = round(means[r] * 100.0, 3)  # % per bar
    if set(means.keys()) == {"up", "chop", "down"}:
        out["all_weather"] = all(v > 0 for v in means.values())
    return out


# ---------------------------------------------------------------------------
# Relative price (stock/SPY) analysis
# ---------------------------------------------------------------------------

def build_relative_df(stock_df: pd.DataFrame, spy_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Construct a relative-performance OHLCV frame: stock / SPY.

    High of the RS bar = stock_high / spy_close (best-case relative perf).
    Low  of the RS bar = stock_low  / spy_close (worst-case relative perf).
    Close              = stock_close / spy_close.
    Volume             = stock volume (energy applies to the relative move).
    """
    spy_c = spy_df[["Close"]].rename(columns={"Close": "spy_c"})
    aligned = stock_df[["Open", "High", "Low", "Close", "Volume"]].join(spy_c, how="inner")
    if len(aligned) < 30:
        return None
    sc = aligned["spy_c"]
    rel = pd.DataFrame({
        "Open":   aligned["Open"] / sc,
        "High":   aligned["High"] / sc,
        "Low":    aligned["Low"]  / sc,
        "Close":  aligned["Close"] / sc,
        "Volume": aligned["Volume"],
    }, index=aligned.index)
    return rel


def relative_analysis(stock_df: pd.DataFrame, spy_df: pd.DataFrame, theta: float) -> Dict:
    """Run squeeze + Ord-Volume + zigzag on the relative strength line.

    Detects stocks whose relative performance is compressing (RS squeeze)
    or whose RS line is breaking out (stock starting to outperform SPY).
    """
    out = {
        "rs_squeeze": False, "rs_released": False, "rs_bw_pctile": 1.0,
        "rs_breakout": False, "rel_ov_sig": False, "rel_ov_sig_loose": False,
        "rel_ov_str": "NONE", "rel_ov_shrink": np.nan,
        "rel_spv_sig": False,
    }
    rel = build_relative_df(stock_df, spy_df)
    if rel is None:
        return out

    # RS squeeze (BB/KC on the relative line)
    sq = squeeze_state(rel)
    out["rs_squeeze"]   = sq["in_squeeze"]
    out["rs_released"]  = sq["released"]
    out["rs_bw_pctile"] = sq["bw_pctile"]

    # RS at new 20-bar high = relative breakout
    rs_hi20 = rel["Close"].rolling(20).max()
    if len(rs_hi20.dropna()) >= 2:
        out["rs_breakout"] = bool(rel["Close"].iloc[-1] >= rs_hi20.iloc[-2])
    # RS at 13-bar and 26-bar highs (Dalton "RS leading before price")
    if len(rel) >= 14:
        rs_hi13 = rel["Close"].rolling(13).max()
        out["rs_13hi"] = bool(rel["Close"].iloc[-1] >= rs_hi13.iloc[-2])
    else:
        out["rs_13hi"] = False
    if len(rel) >= 27:
        rs_hi26 = rel["Close"].rolling(26).max()
        out["rs_26hi"] = bool(rel["Close"].iloc[-1] >= rs_hi26.iloc[-2])
    else:
        out["rs_26hi"] = False

    # Ord-Volume on RS line (relative volume shrinkage on pullbacks)
    pivots = zigzag(rel["High"], rel["Low"], theta)
    legs = build_legs(rel, pivots)
    ov = ord_volume_buy(rel, legs)
    out["rel_ov_sig"]       = ov.get("signal", False)
    out["rel_ov_sig_loose"] = ov.get("signal_loose", False)
    out["rel_ov_str"]       = ov.get("strength", "NONE")
    out["rel_ov_shrink"]    = ov.get("shrink", np.nan)

    # Shakeout on RS line
    spv = shakeout_retest(rel, legs)
    out["rel_spv_sig"] = spv.get("signal", False)

    return out


# ---------------------------------------------------------------------------
# Early asymmetric opportunity scoring
# ---------------------------------------------------------------------------

def early_asym_score(
    df: pd.DataFrame,
    rel: Dict,
    ov: Dict,
    spv: Dict,
    sq: Dict,
    asym: Dict,
    cause: int,
    q: Dict,
    rs: Dict,
) -> Dict:
    """Score optimised for EARLY-STAGE setups before the big move.

    Rewards: basing after drawdown, volatility compression still loading,
    volume shrinkage on selling (Ord), tight risk/reward, emerging RS
    breakout on relative line, all-weather quality.

    Penalizes: already extended (high returns), already at highs (proximity
    near 1.0), no drawdown from peak.
    """
    close = float(df["Close"].iloc[-1])
    n = len(df)
    hi_lookback = min(n, 104)  # ~2 years weekly or ~8 years monthly
    hi52 = float(df["High"].iloc[-hi_lookback:].max())
    drawdown = 1.0 - close / hi52 if hi52 > 0 else 0.0

    # Base low: minimum low over consolidation or last 10 bars
    base_window = max(cause, 10)
    base_low = float(df["Low"].iloc[-base_window:].min())
    risk_pct = (close - base_low) / close if close > 0 else 1.0

    # R:R = upside (to prior high) / downside (to base low)
    rr = (hi52 - close) / (close - base_low) if (close - base_low) > 0.001 else 0.0

    score = 0

    # --- REWARD: drawdown sweet spot (pulled back, basing, not destroyed) ---
    if 0.15 <= drawdown <= 0.35:
        score += 3
    elif 0.10 <= drawdown < 0.15:
        score += 2
    elif 0.05 <= drawdown < 0.10:
        score += 1

    # --- REWARD: currently IN squeeze (spring loading, not yet fired) ---
    if sq["in_squeeze"]:
        score += 3
        if sq["bw_pctile"] <= 0.15:
            score += 2
        elif sq["bw_pctile"] <= 0.25:
            score += 1

    # --- REWARD: consolidation forming (cause accumulating) ---
    if cause >= 10:
        score += 3
    elif cause >= 6:
        score += 2
    elif cause >= 4:
        score += 1

    # --- REWARD: Ord-Volume selling shrinkage (energy leaving the decline) ---
    ov_str = ov.get("strength", "NONE")
    if ov_str in ("STRONG", "GOOD", "MARGINAL"):
        score += {"STRONG": 3, "GOOD": 2, "MARGINAL": 1}[ov_str]

    # --- REWARD: shakeout (tested support on low vol = spring) ---
    if spv.get("signal"):
        score += 3

    # --- REWARD: early volume asymmetry tilt (subtle shift, not overt) ---
    a = asym.get("asymmetry", 1.0)
    if 1.05 <= a <= 1.30:
        score += 2
    elif a > 1.30:
        score += 1  # less weight: might be late-stage if already extended

    # --- REWARD: tight risk (close near base low = well-defined stop) ---
    if risk_pct <= 0.04:
        score += 3
    elif risk_pct <= 0.07:
        score += 2
    elif risk_pct <= 0.10:
        score += 1

    # --- REWARD: good R:R ratio ---
    if rr >= 5.0:
        score += 3
    elif rr >= 3.0:
        score += 2
    elif rr >= 2.0:
        score += 1

    # --- REWARD: relative strength line signals ---
    if rel.get("rs_squeeze"):
        score += 2
    if rel.get("rs_breakout"):
        score += 2
    if rel.get("rs_13hi"):
        score += 1
    if rel.get("rs_26hi"):
        score += 1
    if rel.get("rs_released"):
        score += 1
    if rel.get("rel_ov_sig"):
        score += 3
    elif rel.get("rel_ov_sig_loose"):
        score += 1
    if rel.get("rel_spv_sig"):
        score += 2

    # --- REWARD: all-weather quality ---
    if rs.get("all_weather"):
        score += 2

    # --- PENALTIES for already-extended names ---
    ret26 = float(q.get("q_ret26") or 0)
    if ret26 > 0.30:
        score -= 4
    elif ret26 > 0.20:
        score -= 2
    # At absolute highs (no pullback) = no asymmetry left
    if drawdown < 0.05:
        score -= 4
    elif drawdown < 0.08:
        score -= 2

    return {
        "early_score": max(score, 0),
        "drawdown": round(drawdown, 3),
        "risk_pct": round(risk_pct, 3),
        "rr": round(rr, 1),
        "base_low": round(base_low, 2),
    }


# ---------------------------------------------------------------------------
# Dalton MOM techniques (adapted from Mind Over Markets for weekly/monthly)
# ---------------------------------------------------------------------------

def rotation_factor(df: pd.DataFrame, n: int = 10) -> Dict:
    """Cumulative rotation factor: +1 if high > prior high, -1 if lower;
    same for lows. Sums the two per bar. A streak of +2 = one-timeframing up."""
    if len(df) < n + 1:
        return {"rf_cum": 0, "rf_streak": 0, "rf_dir": 0}
    recent = df.iloc[-(n + 1):]
    vals = []
    for i in range(1, len(recent)):
        hd = 1 if float(recent.iloc[i]["High"]) > float(recent.iloc[i - 1]["High"]) else (
            -1 if float(recent.iloc[i]["High"]) < float(recent.iloc[i - 1]["High"]) else 0)
        ld = 1 if float(recent.iloc[i]["Low"]) > float(recent.iloc[i - 1]["Low"]) else (
            -1 if float(recent.iloc[i]["Low"]) < float(recent.iloc[i - 1]["Low"]) else 0)
        vals.append(hd + ld)
    cum = sum(vals)
    sign = int(np.sign(vals[-1])) if vals else 0
    streak = 0
    for v in reversed(vals):
        if int(np.sign(v)) == sign and sign != 0:
            streak += 1
        else:
            break
    return {"rf_cum": cum, "rf_streak": streak, "rf_dir": sign}


def directional_performance(df: pd.DataFrame) -> Dict:
    """Dalton's two-question framework on the last bar:
    'Which way is it trying to go? Is it doing a good job?'
    Compares attempt (open-close direction) vs value placement vs volume."""
    if len(df) < 3:
        return {"dp_signal": "N/A", "dp_score": 0}
    w = df.iloc[-1]
    pw = df.iloc[-2]
    rng = float(w["High"]) - float(w["Low"])
    if rng == 0:
        return {"dp_signal": "N/A", "dp_score": 0}
    cp = (float(w["Close"]) - float(w["Low"])) / rng
    # attempted direction
    if cp >= 0.70:
        att = "UP"
    elif cp <= 0.30:
        att = "DOWN"
    else:
        att = "NEUTRAL"
    # value placement
    mid = (float(w["High"]) + float(w["Low"])) / 2
    pmid = (float(pw["High"]) + float(pw["Low"])) / 2
    prng = float(pw["High"]) - float(pw["Low"])
    if prng > 0 and mid > pmid + 0.3 * prng:
        vp = "HIGHER"
    elif prng > 0 and mid < pmid - 0.3 * prng:
        vp = "LOWER"
    else:
        vp = "OVERLAP"
    # volume vs recent avg
    vol_avg = float(df["Volume"].iloc[-10:].mean()) if len(df) >= 10 else float(df["Volume"].mean())
    vr = float(w["Volume"]) / vol_avg if vol_avg > 0 else 1.0
    vol_s = "HIGH" if vr > 1.1 else ("LOW" if vr < 0.9 else "AVG")
    # divergence signals
    score = 0
    signal = "NEUTRAL"
    if att == "UP" and vp == "LOWER":
        signal = "FAILED_UP"
        score = -2
    elif att == "DOWN" and vp == "HIGHER":
        signal = "MIRAGE_BUY"
        score = 2
    elif att == "UP" and vol_s == "LOW":
        signal = "LOW_VOL_RALLY"
        score = -1
    elif att == "DOWN" and vol_s == "LOW":
        signal = "LOW_VOL_SELL"
        score = 1
    elif att == "UP" and vol_s == "HIGH" and vp == "HIGHER":
        signal = "CONFIRMED_UP"
        score = 2
    elif att == "DOWN" and vol_s == "HIGH" and vp == "LOWER":
        signal = "CONFIRMED_DN"
        score = -2
    return {"dp_signal": signal, "dp_score": score, "dp_vol": round(vr, 2)}


def hidden_corrective(df: pd.DataFrame, n: int = 6) -> Dict:
    """Hidden corrective action: selling structure (close < open) with
    higher value midpoint = actually bullish (accumulation on dips).
    Buying structure with lower value = actually bearish."""
    if len(df) < n + 1:
        return {"hidden_bull": 0, "hidden_bear": 0}
    recent = df.iloc[-n:]
    hb, hbe = 0, 0
    for i in range(1, len(recent)):
        d = recent.iloc[i]
        p = recent.iloc[i - 1]
        curr_mid = (float(d["High"]) + float(d["Low"])) / 2
        prev_mid = (float(p["High"]) + float(p["Low"])) / 2
        if float(d["Close"]) < float(d["Open"]) and curr_mid > prev_mid:
            hb += 1
        elif float(d["Close"]) > float(d["Open"]) and curr_mid < prev_mid:
            hbe += 1
    return {"hidden_bull": hb, "hidden_bear": hbe}


# ---------------------------------------------------------------------------
# Bracket / auction-transition analysis (Dalton framework)
# ---------------------------------------------------------------------------

def bracket_analysis(df: pd.DataFrame) -> Dict:
    """Detect the current bracket (multi-bar balance area) and measure
    structural features: duration, edge proximity, rising lows / falling
    highs, Donchian compression, close position, and R:R to destination.

    Uses a wide tolerance (30% for weekly, embedded in input) to capture
    the full multi-month trading range as one bracket.
    """
    n = len(df)
    if n < 20:
        return {
            "brk_bars": 0, "brk_high": np.nan, "brk_low": np.nan,
            "brk_pos": 0.5, "near_top": False, "near_bottom": False,
            "rising_lows": False, "falling_highs": False,
            "donch_pctile": 1.0, "close_pos_26": 0.5,
            "rr_up": 0.0, "rr_dest": 0.0, "one_tf_up": 0, "one_tf_dn": 0,
        }
    high = df["High"].values.astype(float)
    low  = df["Low"].values.astype(float)
    close_arr = df["Close"].values.astype(float)
    c = close_arr[-1]

    # Bracket: walk back with 30% envelope (captures wide multi-month ranges)
    h, l = float(high[-1]), float(low[-1])
    brk_bars = 1
    for i in range(n - 2, max(-1, n - 200), -1):
        h = max(h, float(high[i]))
        l = min(l, float(low[i]))
        mid = (h + l) / 2.0
        if mid <= 0 or (h - l) / mid > 0.35:
            break
        brk_bars += 1
    brk_high, brk_low = h, l
    brk_range = brk_high - brk_low
    brk_pos = (c - brk_low) / brk_range if brk_range > 0 else 0.5

    # Near edge
    near_top = brk_pos >= 0.80
    near_bottom = brk_pos <= 0.20

    # One-timeframing: count consecutive bars with rising lows (bullish) or
    # falling highs (bearish) from the current bar backward.
    one_tf_up = 0
    for i in range(n - 1, max(0, n - 13), -1):
        if i == 0:
            break
        if low[i] >= low[i - 1]:
            one_tf_up += 1
        else:
            break
    one_tf_dn = 0
    for i in range(n - 1, max(0, n - 13), -1):
        if i == 0:
            break
        if high[i] <= high[i - 1]:
            one_tf_dn += 1
        else:
            break

    # Rising lows over last 6 bars (looser than strict one-TF)
    recent = min(6, n)
    lows_window = low[-recent:]
    rising_lows = all(lows_window[i] >= lows_window[i - 1] * 0.995
                      for i in range(1, len(lows_window)))
    highs_window = high[-recent:]
    falling_highs = all(highs_window[i] <= highs_window[i - 1] * 1.005
                        for i in range(1, len(highs_window)))

    # Donchian width (20-bar) percentile
    donch_h = pd.Series(high).rolling(20).max()
    donch_l = pd.Series(low).rolling(20).min()
    donch_w = (donch_h - donch_l) / ((donch_h + donch_l) / 2.0)
    donch_pctile = float(donch_w.rank(pct=True).iloc[-1]) if donch_w.notna().any() else 1.0

    # Close position in 26-bar range
    span26 = min(26, n)
    hi26 = float(high[-span26:].max())
    lo26 = float(low[-span26:].min())
    close_pos_26 = (c - lo26) / (hi26 - lo26) if (hi26 - lo26) > 0 else 0.5

    # R:R for upside: (bracket_high - close) / (close - base)
    base_window = max(brk_bars, 10)
    base_low = float(low[-min(base_window, n):].min())
    rr_up = (brk_high - c) / (c - base_low) if (c - base_low) > 0.01 else 0.0

    # Destination R:R: measured move target = bracket_high + bracket_width
    destination = brk_high + brk_range
    rr_dest = (destination - c) / (c - base_low) if (c - base_low) > 0.01 else 0.0

    # --- Dalton additions ---

    # (1) Close-in-bar position: fraction of recent 13 bars where close
    # is in the UPPER 40% of that bar's range. Persistent bullish closes
    # = "higher prices attracting activity, not cutting it off."
    lookback_cib = min(13, n)
    bullish_close_count = 0
    for i in range(n - lookback_cib, n):
        bar_range = float(high[i]) - float(low[i])
        if bar_range > 0:
            bar_pos = (close_arr[i] - float(low[i])) / bar_range
            if bar_pos >= 0.60:
                bullish_close_count += 1
    close_in_bar = bullish_close_count / lookback_cib

    # (2) Volume-confirms-direction: for bars that make new 10-bar highs,
    # is their volume above the 20-bar average? Measures acceptance.
    vol = df["Volume"].values.astype(float)
    vol_avg_20 = float(pd.Series(vol).rolling(20).mean().iloc[-1]) if n >= 20 else float(np.mean(vol))
    confirm_bars = 0
    confirm_total = 0
    for i in range(max(10, n - 13), n):
        if float(high[i]) >= float(pd.Series(high[max(0, i - 10):i]).max()):
            confirm_total += 1
            if vol[i] >= vol_avg_20:
                confirm_bars += 1
    vol_confirms_dir = confirm_bars / max(confirm_total, 1)

    # (3) Failed-probe detection: in the last 8 bars, did price probe beyond
    # the bracket high/low and then close back inside? = responsive rejection weakening.
    recent_probe_top = False
    recent_probe_bot = False
    probe_window = min(8, n)
    for i in range(n - probe_window, n):
        if float(high[i]) >= brk_high * 0.99 and close_arr[i] < brk_high:
            recent_probe_top = True
        if float(low[i]) <= brk_low * 1.01 and close_arr[i] > brk_low:
            recent_probe_bot = True

    # (4) RS at 13/26-bar highs (relative strength making new highs before price)
    # Requires spy_df — handled in relative_analysis, surfaced via rel dict.
    # Here we add: is the 13-bar RS rolling max at current bar?
    # (computed externally; placeholder flag in bracket_analysis)

    # (5) Range expansion on volume: did the last bar have range > 1.3x avg(range,10)
    # AND volume > avg(vol,20)?
    bar_ranges = pd.Series(high - low)
    avg_range_10 = float(bar_ranges.rolling(10).mean().iloc[-1]) if n >= 10 else float(bar_ranges.mean())
    last_range = float(high[-1]) - float(low[-1])
    last_vol = float(vol[-1])
    range_expand_vol = bool(last_range > 1.3 * avg_range_10 and last_vol > vol_avg_20)

    return {
        "brk_bars": brk_bars,
        "brk_high": round(brk_high, 2),
        "brk_low": round(brk_low, 2),
        "brk_pos": round(brk_pos, 3),
        "near_top": near_top,
        "near_bottom": near_bottom,
        "rising_lows": rising_lows,
        "falling_highs": falling_highs,
        "donch_pctile": round(donch_pctile, 2),
        "close_pos_26": round(close_pos_26, 3),
        "rr_up": round(rr_up, 1),
        "rr_dest": round(rr_dest, 1),
        "one_tf_up": one_tf_up,
        "one_tf_dn": one_tf_dn,
        # Dalton enhancements
        "close_in_bar": round(close_in_bar, 2),
        "vol_confirms": round(vol_confirms_dir, 2),
        "probe_top": recent_probe_top,
        "probe_bot": recent_probe_bot,
        "range_exp_vol": range_expand_vol,
    }


def massive_move_score(
    brk: Dict, sq: Dict, asym: Dict, rel: Dict, rs: Dict,
) -> int:
    """Dalton-style massive-move pre-conditions score (0-100 scale).

    A. Bracket quality (max ~25): duration, edge proximity, structure
    B. Compression (max ~20): ATR/Donchian/BB squeeze
    C. Sponsorship (max ~25): RS leading, up-vol asymmetry, close position
    D. Breakout readiness (max ~20): edge test, range expanding, one-TF
    E. Asymmetry (max ~10): stop close, destination far
    """
    s = 0

    # --- A. Bracket quality ---
    bb = brk["brk_bars"]
    if bb >= 52:
        s += 5
    elif bb >= 26:
        s += 3
    elif bb >= 13:
        s += 1

    if brk["near_top"] or brk["near_bottom"]:
        s += 5
    elif brk["brk_pos"] >= 0.70 or brk["brk_pos"] <= 0.30:
        s += 3

    if bb >= 26:
        s += 5  # wide bracket = more fuel

    if brk["near_top"] and brk["rising_lows"]:
        s += 5
    elif brk["near_bottom"] and brk["falling_highs"]:
        s += 5
    elif brk["rising_lows"] or brk["falling_highs"]:
        s += 2

    # one-timeframing bonus
    otf = max(brk["one_tf_up"], brk["one_tf_dn"])
    if otf >= 6:
        s += 5
    elif otf >= 4:
        s += 3

    # --- B. Compression ---
    if sq["bw_pctile"] <= 0.15:
        s += 5
    elif sq["bw_pctile"] <= 0.25:
        s += 3
    elif sq["bw_pctile"] <= 0.35:
        s += 1

    if brk["donch_pctile"] <= 0.20:
        s += 5
    elif brk["donch_pctile"] <= 0.35:
        s += 3

    if sq["in_squeeze"]:
        s += 5
    elif sq["released"]:
        s += 3

    # --- C. Sponsorship / accumulation ---
    if rel.get("rs_breakout"):
        s += 5
    if rel.get("rs_released"):
        s += 3
    if rel.get("rs_bw_pctile", 1.0) <= 0.25:
        s += 2  # RS line also compressed → about to resolve

    a = asym.get("asymmetry", 1.0)
    if a >= 1.30:
        s += 5
    elif a >= 1.15:
        s += 3

    cp = brk["close_pos_26"]
    if cp >= 0.80:
        s += 5
    elif cp >= 0.65:
        s += 3

    if rs.get("all_weather"):
        s += 5
    elif rs.get("rs_down") is not None and rs["rs_down"] > 0:
        s += 3

    # Dalton: "higher prices attracting activity" (close-in-bar)
    cib = brk.get("close_in_bar", 0)
    if cib >= 0.70:
        s += 5  # 70%+ of recent bars close in upper 40% of range
    elif cib >= 0.55:
        s += 3

    # Volume confirms direction (new highs on above-avg vol)
    vcf = brk.get("vol_confirms", 0)
    if vcf >= 0.70:
        s += 5
    elif vcf >= 0.50:
        s += 3

    # --- D. Breakout readiness ---
    if brk["near_top"] and brk["brk_pos"] >= 0.90:
        s += 5
    elif brk["near_top"]:
        s += 3
    elif brk["near_bottom"] and brk["brk_pos"] <= 0.10:
        s += 5
    elif brk["near_bottom"]:
        s += 3

    if brk["rising_lows"] and brk["near_top"]:
        s += 5

    if cp >= 0.85:
        s += 5

    # Dalton: failed probe = responsive activity weakening at edge
    if brk.get("probe_top") and brk["near_top"]:
        s += 5  # tested top, closed back inside but didn't reject hard
    elif brk.get("probe_bot") and brk["near_bottom"]:
        s += 5

    # Range expansion with volume = acceptance beginning
    if brk.get("range_exp_vol"):
        s += 5

    # --- E. Asymmetry ---
    if brk["rr_dest"] >= 5.0:
        s += 5
    elif brk["rr_dest"] >= 3.0:
        s += 3

    if brk["rr_up"] >= 3.0:
        s += 5
    elif brk["rr_up"] >= 2.0:
        s += 3

    return s


# ---------------------------------------------------------------------------
# Rolling Continuous Ord Score + Inflection / Acceleration Detection
# ---------------------------------------------------------------------------

DECAY_RATE = 0.97  # per-bar decay for leg-based signals (half-life ~23 bars)
DERIV_SPAN = 5     # EMA span for velocity/acceleration smoothing


def _bar_based_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-bar continuous sub-scores from bar-level data (vectorized)."""
    n = len(df)
    out = pd.DataFrame(index=df.index)
    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    # Volume asymmetry (20-bar rolling) -> [-15, +15]
    ret = close.pct_change()
    up_mask = ret > 0
    dn_mask = ret < 0
    up_vol = vol.where(up_mask).rolling(20, min_periods=5).mean()
    dn_vol = vol.where(dn_mask).rolling(20, min_periods=5).mean()
    asym_ratio = (up_vol / dn_vol.replace(0, np.nan)).clip(0.3, 3.0).fillna(1.0)
    out["s_asym"] = ((asym_ratio - 1.0) * 30.0).clip(-15, 15)

    # Squeeze bandwidth -> [-5, +15]
    ma = close.rolling(20).mean()
    sd = close.rolling(20).std()
    prev_c = close.shift()
    tr = pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(20).mean()
    bb_w = (2.0 * sd) / ma.replace(0, np.nan)
    bw_pct = bb_w.rank(pct=True)
    bb_up = ma + 2.0 * sd
    bb_dn = ma - 2.0 * sd
    kc_up = ma + 1.5 * atr
    kc_dn = ma - 1.5 * atr
    in_sq = (bb_up < kc_up) & (bb_dn > kc_dn)
    sq_score = np.where(in_sq & (bw_pct <= 0.15), 15,
               np.where(in_sq & (bw_pct <= 0.30), 10,
               np.where(in_sq, 7,
               np.where(bw_pct <= 0.20, 5,
               np.where(bw_pct >= 0.80, -5, 0)))))
    out["s_squeeze"] = sq_score.astype(float)

    # Trend distance (close vs MA50) -> [-10, +5]
    ma50 = close.rolling(50, min_periods=20).mean()
    dist = ((close - ma50) / ma50.replace(0, np.nan)).fillna(0)
    out["s_trend"] = np.where(dist > 0.05, 5, np.where(dist > 0, 2,
                    np.where(dist > -0.05, -2, np.where(dist > -0.15, -5, -10))))

    # Rotation factor (2-bar sum of H/L direction) -> [-5, +5]
    h_dir = np.sign(high - high.shift(1))
    l_dir = np.sign(low - low.shift(1))
    rf = (h_dir + l_dir).rolling(5, min_periods=2).mean() * 2.5
    out["s_rf"] = rf.clip(-5, 5).fillna(0)

    # Close-in-bar position (bullish close tendency) -> [-5, +5]
    bar_range = high - low
    cib = ((close - low) / bar_range.replace(0, np.nan)).fillna(0.5)
    cib_avg = cib.rolling(8, min_periods=3).mean()
    out["s_cib"] = ((cib_avg - 0.5) * 20).clip(-5, 5)

    return out


def _leg_based_anchors(df: pd.DataFrame, theta: float) -> List[tuple]:
    """Run zigzag once, build legs, compute sub-scores at each leg completion.

    Returns list of (bar_idx, score_dict) anchors where score_dict has
    signed contributions from OV shrinkage, expansion, shakeout, dissipation.
    """
    pivots = zigzag(df["High"], df["Low"], theta)
    legs = build_legs(df, pivots)
    anchors = []

    for k in range(3, len(legs)):
        L_current = legs[k]
        L_down = legs[k - 1] if legs[k - 1]["dir"] == "down" else None
        prev_up = legs[k - 2] if legs[k - 2]["dir"] == "up" else None
        prev_down = legs[k - 3] if legs[k - 3]["dir"] == "down" else None

        anchor_bar = L_current["start_idx"]
        scores = {}

        # OV shrinkage quality [-25, +25]
        if L_down and L_current["dir"] == "up" and prev_up and prev_down:
            shrink_up = L_down["ov"] / prev_up["ov"] if prev_up["ov"] > 0 else 1.0
            shrink_dn = L_down["ov"] / prev_down["ov"] if prev_down["ov"] > 0 else 1.0
            best = min(shrink_up, shrink_dn)
            if best <= 0.25:
                scores["s_ov_shrink"] = 25
            elif best <= 0.40:
                scores["s_ov_shrink"] = 18
            elif best <= 0.50:
                scores["s_ov_shrink"] = 12
            elif best <= 0.60:
                scores["s_ov_shrink"] = 5
            elif best <= 0.75:
                scores["s_ov_shrink"] = 0
            else:
                scores["s_ov_shrink"] = -10

            # OV expansion [-10, +10]
            expand = L_current["ov"] / L_down["ov"] if L_down["ov"] > 0 else 0
            if expand >= 2.0:
                scores["s_ov_expand"] = 10
            elif expand >= 1.5:
                scores["s_ov_expand"] = 7
            elif expand >= 1.3:
                scores["s_ov_expand"] = 4
            elif expand >= 1.0:
                scores["s_ov_expand"] = 0
            elif expand >= 0.7:
                scores["s_ov_expand"] = -5
            else:
                scores["s_ov_expand"] = -10

        # Shakeout quality [-5, +10]
        if L_down and prev_down and L_down["dir"] == "down" and prev_down["dir"] == "down":
            origin_idx = int(prev_down["end_idx"])
            origin_vol = float(df["Volume"].iloc[origin_idx]) if origin_idx < len(df) else 0
            if origin_vol > 0:
                seg = df.iloc[int(L_down["start_idx"]):int(L_down["end_idx"]) + 1]
                origin_low = float(df["Low"].iloc[origin_idx])
                probes = seg[seg["Low"].astype(float) <= origin_low]
                if not probes.empty:
                    ratio = float(probes["Volume"].min()) / origin_vol
                    if ratio <= 0.50:
                        scores["s_shakeout"] = 10
                    elif ratio <= 0.75:
                        scores["s_shakeout"] = 7
                    elif ratio <= 0.92:
                        scores["s_shakeout"] = 4
                    else:
                        scores["s_shakeout"] = -3

        # Multi-leg dissipation [0, +10]
        down_legs = [L for L in legs[:k] if L["dir"] == "down"]
        if len(down_legs) >= 3:
            recent = down_legs[-3:]
            if all(recent[i]["ov"] > recent[i + 1]["ov"] for i in range(len(recent) - 1)):
                scores["s_dissipation"] = 8
            elif len(down_legs) >= 2 and down_legs[-2]["ov"] > down_legs[-1]["ov"]:
                scores["s_dissipation"] = 4

        if scores:
            anchors.append((anchor_bar, scores))

    return anchors


def _apply_decay(anchors: List[tuple], n_bars: int) -> pd.DataFrame:
    """Forward-fill leg-based anchor scores with exponential decay."""
    cols = ["s_ov_shrink", "s_ov_expand", "s_shakeout", "s_dissipation"]
    result = pd.DataFrame(0.0, index=range(n_bars), columns=cols)

    for col in cols:
        last_val = 0.0
        last_bar = 0
        anchor_vals = [(b, sc.get(col, None)) for b, sc in anchors if col in sc]

        for idx, (bar_idx, val) in enumerate(anchor_vals):
            # Decay the old value up to this anchor
            for t in range(last_bar, min(bar_idx, n_bars)):
                decay = DECAY_RATE ** (t - last_bar)
                result.iloc[t][col] = last_val * decay
            # Set new anchor
            last_val = val
            last_bar = bar_idx

        # Decay after last anchor to end
        for t in range(last_bar, n_bars):
            decay = DECAY_RATE ** (t - last_bar)
            result.iloc[t][col] = last_val * decay

    return result


def compute_rolling_ord_score(df: pd.DataFrame, theta: float) -> Dict:
    """Compute the rolling continuous Ord score and return current-bar state.

    Returns a dict with trajectory information for the most recent bar:
      ord_cont: current score
      ord_vel: current velocity (1st derivative)
      ord_acc: current acceleration (2nd derivative)
      ord_trajectory: state label
      ord_early_entry: True if conditions are improving from negative
    """
    n = len(df)
    if n < 30:
        return {"ord_cont": 0, "ord_vel": 0, "ord_acc": 0,
                "ord_trajectory": "INSUFFICIENT", "ord_early_entry": False,
                "ord_bars_since_infl": 99}

    # Bar-based scores (vectorized)
    bar_scores = _bar_based_scores(df)

    # Leg-based scores (discrete with decay)
    anchors = _leg_based_anchors(df, theta)
    leg_scores = _apply_decay(anchors, n)
    leg_scores.index = df.index

    # Combine
    total = bar_scores.sum(axis=1) + leg_scores.sum(axis=1)
    total = total.clip(-100, 100)

    # Velocity (1st derivative, EMA smoothed)
    diff = total.diff().fillna(0)
    velocity = diff.ewm(span=DERIV_SPAN, min_periods=2).mean()

    # Acceleration (2nd derivative)
    vel_diff = velocity.diff().fillna(0)
    accel = vel_diff.ewm(span=DERIV_SPAN, min_periods=2).mean()

    # Detect inflections
    inflection_up = (total.shift(1) < 0) & (total >= 0)

    # Bars since last inflection up
    infl_indices = inflection_up[inflection_up].index
    bars_since = 99
    if len(infl_indices) > 0:
        last_infl_pos = df.index.get_loc(infl_indices[-1])
        bars_since = n - 1 - last_infl_pos

    # Current state
    s = float(total.iloc[-1])
    v = float(velocity.iloc[-1])
    a = float(accel.iloc[-1])

    # Trajectory classification
    if s < 0 and a > 0.3 and v > 0:
        trajectory = "ACCEL_BULL"
    elif s < 0 and v > 0:
        trajectory = "VEL_POS"
    elif bars_since <= 3:
        trajectory = "INFLECT_UP"
    elif s > 0 and v > 0 and a > 0:
        trajectory = "STRONG_UP"
    elif s > 0 and v > 0:
        trajectory = "IMPROVING"
    elif s > 0 and v <= 0 and a < -0.3:
        trajectory = "ACCEL_BEAR"
    elif s > 0 and v <= 0:
        trajectory = "DETERIORATING"
    elif s < 0 and v <= 0:
        trajectory = "DECLINING"
    else:
        trajectory = "FLAT"

    early_entry = trajectory in ("ACCEL_BULL", "VEL_POS", "INFLECT_UP")

    return {
        "ord_cont": round(s, 1),
        "ord_vel": round(v, 2),
        "ord_acc": round(a, 2),
        "ord_trajectory": trajectory,
        "ord_early_entry": early_entry,
        "ord_bars_since_infl": bars_since,
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(
    df: pd.DataFrame,
    ticker: str,
    theta: float,
    consol_tol: float,
    regime_df: Optional[pd.DataFrame] = None,
    spy_df: Optional[pd.DataFrame] = None,
    daily_df: Optional[pd.DataFrame] = None,
    monthly_df: Optional[pd.DataFrame] = None,
) -> Optional[Dict]:
    df = df.dropna().copy()
    if len(df) < max(BB_LENGTH + 5, TREND_MA + 5):
        return None

    pivots = zigzag(df["High"], df["Low"], theta)
    legs = build_legs(df, pivots)

    ov    = ord_volume_buy(df, legs)
    spv   = shakeout_retest(df, legs)
    sq    = squeeze_state(df)
    asym  = vol_asymmetry(df)
    q     = qullamaggie_setup(df)
    cause = consolidation_bars(df, tol=consol_tol)
    rs    = regime_strength(df, regime_df) if regime_df is not None else {
        "rs_up": np.nan, "rs_chop": np.nan, "rs_down": np.nan, "all_weather": False
    }
    rel   = relative_analysis(df, spy_df, theta) if spy_df is not None else {
        "rs_squeeze": False, "rs_released": False, "rs_bw_pctile": 1.0,
        "rs_breakout": False, "rel_ov_sig": False, "rel_ov_sig_loose": False,
        "rel_ov_str": "NONE", "rel_ov_shrink": np.nan, "rel_spv_sig": False,
    }
    clx   = selling_climax(df)
    diss  = multi_leg_dissipation(legs)
    gpt   = gap_test(df)
    mfi   = mfi_zero_cross(df, daily_df=daily_df, monthly_df=monthly_df)
    traj  = compute_rolling_ord_score(df, theta)
    rf    = rotation_factor(df)
    dp    = directional_performance(df)
    hc    = hidden_corrective(df)
    early = early_asym_score(df, rel, ov, spv, sq, asym, cause, q, rs)
    brk   = bracket_analysis(df)
    massive = massive_move_score(brk, sq, asym, rel, rs)

    # MFI zero-cross boost (the TCAP pattern)
    if mfi.get("tcap_wm"):
        early["early_score"] = early.get("early_score", 0) + 8
    if mfi.get("full_tcap"):
        early["early_score"] = early.get("early_score", 0) + 7
    elif mfi.get("mfi_cross") and mfi.get("vol_spike_cross"):
        early["early_score"] = early.get("early_score", 0) + 5
    elif mfi.get("mfi_cross"):
        early["early_score"] = early.get("early_score", 0) + 3
    elif mfi.get("cmf_improving") and mfi.get("cmf_now", 0) > -0.05:
        early["early_score"] = early.get("early_score", 0) + 1

    # Trajectory boost to early_score (the key early-detection layer)
    if traj["ord_trajectory"] == "INFLECT_UP":
        early["early_score"] = early.get("early_score", 0) + 5
    elif traj["ord_trajectory"] == "ACCEL_BULL":
        early["early_score"] = early.get("early_score", 0) + 4
    elif traj["ord_trajectory"] == "VEL_POS":
        early["early_score"] = early.get("early_score", 0) + 3

    # Ord volume signals boost to early_score
    if clx.get("climax_retest"):
        early["early_score"] = early.get("early_score", 0) + 4
    if diss.get("diss_triggered"):
        early["early_score"] = early.get("early_score", 0) + 3
    if gpt.get("gap_test_bull"):
        early["early_score"] = early.get("early_score", 0) + 2

    # Dalton MOM boost to early_score
    if dp["dp_signal"] == "MIRAGE_BUY":
        early["early_score"] = early.get("early_score", 0) + 3
    elif dp["dp_signal"] == "LOW_VOL_SELL":
        early["early_score"] = early.get("early_score", 0) + 2
    elif dp["dp_signal"] == "CONFIRMED_UP":
        early["early_score"] = early.get("early_score", 0) + 1
    if hc["hidden_bull"] >= 2:
        early["early_score"] = early.get("early_score", 0) + 2
    if rf["rf_streak"] >= 4 and rf["rf_dir"] > 0:
        early["early_score"] = early.get("early_score", 0) + 1

    ma50 = df["Close"].rolling(TREND_MA).mean().iloc[-1]
    close = float(df["Close"].iloc[-1])
    above_ma = bool(close > ma50) if pd.notna(ma50) else False

    # ----- Ord composite (spec-driven) ---------------------------------
    ord_score = 0
    if ov["signal"]:
        ord_score += {"STRONG": 4, "GOOD": 3, "MARGINAL": 2}.get(ov["strength"], 0)
        if ov.get("confirmed"):
            ord_score += 2
        elif ov.get("confirmed_loose"):
            ord_score += 1
    elif ov.get("signal_loose"):
        ord_score += {"STRONG": 3, "GOOD": 2, "MARGINAL": 1}.get(ov["strength"], 0)
        if ov.get("confirmed_loose"):
            ord_score += 1
    if spv["signal"]:
        ord_score += 3
    if clx.get("climax_retest"):
        ord_score += 4
    elif clx.get("climax"):
        ord_score += 1
    if diss.get("diss_triggered"):
        ord_score += 3
    elif diss.get("dissipation"):
        ord_score += 1
    if gpt.get("gap_test_bull"):
        ord_score += 3
    elif gpt.get("gap_found"):
        ord_score += 1
    if sq["released"]:
        ord_score += 3
    elif sq["in_squeeze"] and sq["bw_pctile"] <= SQUEEZE_BW_PCTL:
        ord_score += 2
    elif sq["bw_pctile"] <= SQUEEZE_BW_PCTL:
        ord_score += 1
    if asym["asymmetry"] >= 1.5:
        ord_score += 2
    elif asym["asymmetry"] >= ASYM_MIN_BULLISH:
        ord_score += 1
    if above_ma:
        ord_score += 1

    # Consolidation bonus ("cause") -- Ord §9.2
    if cause >= 12:
        ord_score += 2
    elif cause >= 6:
        ord_score += 1

    q_score = int(q.get("q_score", 0))
    combined = ord_score + q_score

    # All-weather relative strength: top-tier badge worth 3 composite points
    if rs.get("all_weather"):
        combined += 3

    return {
        "ticker": ticker,
        "combined": combined,
        "ord_score": ord_score,
        "q_score": q_score,
        "close": round(close, 2),
        # Ord-Volume diagnostics
        "ov_sig": ov["signal"],
        "ov_sig_loose": ov.get("signal_loose", False),
        "ov_str": ov.get("strength"),
        "ov_shrink": round(ov.get("shrink", np.nan), 2),
        "ov_expand": round(ov.get("expand", np.nan), 2),
        "ov_probed": ov.get("probed"),
        "ov_closed_back": ov.get("closed_back"),
        # Shakeout (§4 false breakout bottom)
        "spv_sig": spv["signal"],
        "spv_ratio": round(spv.get("ratio", np.nan), 2) if spv.get("ratio") is not None else np.nan,
        # Squeeze / asymmetry
        "squeeze": sq["in_squeeze"],
        "released": sq["released"],
        "bw_pctile": round(sq["bw_pctile"], 2),
        "asym": round(asym["asymmetry"], 2),
        "above_ma50": above_ma,
        # Qullamaggie
        "q_stacked": q.get("q_stacked"),
        "q_ret13": q.get("q_ret13"),
        "q_ret26": q.get("q_ret26"),
        "q_compress": q.get("q_compression"),
        "q_volratio": q.get("q_volratio"),
        "q_prox": q.get("q_proximity"),
        "q_brk": q.get("q_breakout"),
        # Consolidation length ("cause")
        "cause_bars": cause,
        # Regime-conditional strength
        "rs_up": rs.get("rs_up"),
        "rs_chop": rs.get("rs_chop"),
        "rs_down": rs.get("rs_down"),
        "all_weather": rs.get("all_weather"),
        # Relative strength line (stock/SPY)
        "rel_sq": rel.get("rs_squeeze"),
        "rel_released": rel.get("rs_released"),
        "rel_bw_pct": round(rel.get("rs_bw_pctile", 1.0), 2),
        "rel_brk": rel.get("rs_breakout"),
        "rel_ov": rel.get("rel_ov_sig"),
        "rel_ov_loose": rel.get("rel_ov_sig_loose"),
        "rel_ov_str": rel.get("rel_ov_str"),
        "rel_spv": rel.get("rel_spv_sig"),
        # Early asymmetric opportunity
        "early_score": early.get("early_score"),
        "drawdown": early.get("drawdown"),
        "risk_pct": early.get("risk_pct"),
        "rr": early.get("rr"),
        "base_low": early.get("base_low"),
        # Dalton massive-move pre-conditions
        "massive": massive,
        "brk_bars": brk.get("brk_bars"),
        "brk_pos": brk.get("brk_pos"),
        "near_edge": brk.get("near_top") or brk.get("near_bottom"),
        "rising_lows": brk.get("rising_lows"),
        "donch_pct": brk.get("donch_pctile"),
        "close_pos": brk.get("close_pos_26"),
        "one_tf": max(brk.get("one_tf_up", 0), brk.get("one_tf_dn", 0)),
        "rr_dest": brk.get("rr_dest"),
        # Dalton auction-quality enhancements
        "cib": brk.get("close_in_bar"),       # close-in-bar (upper %)
        "vol_conf": brk.get("vol_confirms"),   # vol confirms direction
        "probe_edge": brk.get("probe_top") or brk.get("probe_bot"),
        "rng_exp_v": brk.get("range_exp_vol"), # range expansion on vol
        "rs_13hi": rel.get("rs_13hi"),
        "rs_26hi": rel.get("rs_26hi"),
        # Ord advanced volume signals
        "climax": clx.get("climax"),
        "clx_retest": clx.get("climax_retest"),
        "diss": diss.get("dissipation"),
        "diss_trig": diss.get("diss_triggered"),
        "diss_n": diss.get("diss_legs"),
        "gap_test": gpt.get("gap_test_bull"),
        # Dalton MOM signals
        "rf_cum": rf.get("rf_cum"),
        "rf_str": rf.get("rf_streak"),
        "dp_sig": dp.get("dp_signal"),
        "dp_vol": dp.get("dp_vol"),
        "h_bull": hc.get("hidden_bull"),
        # MFI / CMF zero-cross (TCAP pattern)
        "mfi_x": mfi.get("mfi_cross"),
        "cmf_x": mfi.get("cmf_cross"),
        "cmf_now": mfi.get("cmf_now"),
        "cmf_impr": mfi.get("cmf_improving"),
        "vol_spk_x": mfi.get("vol_spike_cross"),
        "mfi_now": mfi.get("mfi_now"),
        "d_mfi_x": mfi.get("daily_mfi_x"),
        "d_mfi_now": mfi.get("daily_mfi_now"),
        "full_tcap": mfi.get("full_tcap"),
        "tcap_wm": mfi.get("tcap_wm"),
        "m_mfi_now": mfi.get("m_mfi_now"),
        # Continuous Ord trajectory
        "ord_cont": traj.get("ord_cont"),
        "ord_vel": traj.get("ord_vel"),
        "ord_acc": traj.get("ord_acc"),
        "ord_traj": traj.get("ord_trajectory"),
        "ord_early": traj.get("ord_early_entry"),
        "bars_infl": traj.get("ord_bars_since_infl"),
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def download_panel(tickers: List[str], tf: str) -> pd.DataFrame:
    return yf.download(
        tickers,
        period=LOOKBACK[tf],
        interval=INTERVAL[tf],
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )


def extract_ticker_df(panel: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    try:
        if isinstance(panel.columns, pd.MultiIndex):
            if ticker not in panel.columns.get_level_values(0):
                return None
            df = panel[ticker].copy()
        else:
            df = panel.copy()
        return df if {"Open", "High", "Low", "Close", "Volume"}.issubset(df.columns) else None
    except Exception:
        return None


def scan(tickers: List[str], tf: str, benchmark: str = "SPY") -> pd.DataFrame:
    print(f"[scan] downloading {len(tickers)} tickers @ {INTERVAL[tf]} (period={LOOKBACK[tf]})")
    panel = download_panel(tickers, tf)

    # Fetch benchmark once for regime classification
    spy_df = None
    regime_df = None
    print(f"[benchmark] {benchmark}")
    try:
        spy_raw = yf.download(
            benchmark,
            period=LOOKBACK[tf],
            interval=INTERVAL[tf],
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if isinstance(spy_raw.columns, pd.MultiIndex):
            spy_raw.columns = spy_raw.columns.get_level_values(0)
        spy_df = spy_raw.dropna()
        regime_df = compute_regime_frame(spy_df, REGIME_LOOKBACK[tf])
        print(f"[regime] SPY {len(spy_df)} bars, regimes: "
              f"up={int((regime_df['regime']=='up').sum())} "
              f"chop={int((regime_df['regime']=='chop').sum())} "
              f"down={int((regime_df['regime']=='down').sum())}")
    except Exception as e:
        print(f"[warn] SPY regime fetch failed ({e}); regime cols will be NaN")

    # Fetch daily data for the TCAP daily MFI cross check
    # Fetch daily data for D/W TCAP
    daily_panel = None
    try:
        print(f"[daily] downloading {len(tickers)} tickers @ 1d for D/W TCAP")
        daily_panel = yf.download(
            tickers, period="3mo", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False, threads=True,
        )
    except Exception as e:
        print(f"[warn] daily download failed ({e})")

    # Fetch monthly data for W/M TCAP
    monthly_panel = None
    try:
        print(f"[monthly] downloading {len(tickers)} tickers @ 1mo for W/M TCAP")
        monthly_panel = yf.download(
            tickers, period="5y", interval="1mo",
            group_by="ticker", auto_adjust=True, progress=False, threads=True,
        )
    except Exception as e:
        print(f"[warn] monthly download failed ({e})")

    rows: List[Dict] = []
    for t in tickers:
        df = extract_ticker_df(panel, t)
        if df is None or df.empty:
            continue
        df = df.dropna()
        if len(df) < MIN_BARS[tf]:
            continue
        d_df = None
        if daily_panel is not None:
            d_df = extract_ticker_df(daily_panel, t)
            if d_df is not None:
                d_df = d_df.dropna()
                if len(d_df) < 30:
                    d_df = None
        m_df = None
        if monthly_panel is not None:
            m_df = extract_ticker_df(monthly_panel, t)
            if m_df is not None:
                m_df = m_df.dropna()
                if len(m_df) < 24:
                    m_df = None
        try:
            row = score_candidate(
                df, t,
                theta=SWING_THETA[tf],
                consol_tol=CONSOL_TOL[tf],
                regime_df=regime_df,
                spy_df=spy_df,
                daily_df=d_df,
                monthly_df=m_df,
            )
        except Exception as e:
            continue
        if row is not None:
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1] if __doc__ else "")
    ap.add_argument("--tf", choices=["W", "M", "both"], default="both",
                    help="timeframe: weekly, monthly, or both (default)")
    ap.add_argument("--top", type=int, default=25, help="top N to print")
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="explicit ticker list (overrides --universe)")
    ap.add_argument("--universe", default="sp500",
                    choices=["sp500", "sp400", "sp600", "smid", "all",
                             "uk", "uk_mid", "uk_small", "uk_aim",
                             "asx", "asx_small", "asx_all",
                             "italy", "italy_mid"],
                    help="stock universe: US (sp500/sp400/sp600/smid/all), "
                         "UK (uk/uk_mid/uk_small/uk_aim), "
                         "AU (asx/asx_small/asx_all)")
    ap.add_argument("--min-score", type=int, default=4,
                    help="drop rows below this composite score")
    ap.add_argument("--out-dir", default=".",
                    help="directory to write per-timeframe CSV results")
    ap.add_argument("--aw-only", action="store_true",
                    help="only display all-weather rows (positive excess in up/chop/down regimes)")
    ap.add_argument("--max-price", type=float, default=None,
                    help="filter to stocks below this price (useful for nano/micro-cap screening)")
    ap.add_argument("--min-price", type=float, default=None,
                    help="filter to stocks above this price")
    ap.add_argument("--mode", choices=["breakout", "early", "massive"], default="early",
                    help="'breakout' = rank by combined (already-moving momentum); "
                         "'early' = rank by early_score (pre-move asymmetric setups); "
                         "'massive' = rank by Dalton massive-move pre-conditions (0-100)")
    args = ap.parse_args()

    tickers = args.tickers if args.tickers else fetch_universe(args.universe)
    benchmark = BENCHMARK_MAP.get(args.universe, "SPY")
    print(f"[universe] {len(tickers)} tickers, benchmark={benchmark}")

    tfs = ["W", "M"] if args.tf == "both" else [args.tf]
    for tf in tfs:
        label = "WEEKLY" if tf == "W" else "MONTHLY"
        mode_label = "EARLY ASYMMETRIC" if args.mode == "early" else "BREAKOUT"
        print(f"\n================  {label} {mode_label} CANDIDATES  ================")
        df = scan(tickers, tf, benchmark=benchmark)
        if df.empty:
            print("no results")
            continue

        # Sort based on mode
        if args.mode == "early":
            sort_cols = ["early_score", "rr", "all_weather", "drawdown"]
            sort_asc  = [False, False, False, False]
            score_col = "early_score"
        elif args.mode == "massive":
            sort_cols = ["massive", "rr_dest", "all_weather", "early_score"]
            sort_asc  = [False, False, False, False]
            score_col = "massive"
        else:
            sort_cols = ["combined", "all_weather", "ord_score", "q_score", "asym"]
            sort_asc  = [False, False, False, False, False]
            score_col = "combined"

        df = df.sort_values(sort_cols, ascending=sort_asc).reset_index(drop=True)

        view = df.copy()
        if args.max_price is not None:
            view = view[view["close"] <= args.max_price]
        if args.min_price is not None:
            view = view[view["close"] >= args.min_price]
        if args.aw_only:
            view = view[view["all_weather"] == True]
        filtered = view[view[score_col] >= args.min_score].head(args.top)
        if filtered.empty:
            print(f"no candidates above min-score {args.min_score}; showing top {args.top} by {score_col}")
            filtered = view.head(args.top)
        with pd.option_context("display.max_rows", None,
                               "display.max_columns", None,
                               "display.width", 200):
            print(filtered.to_string(index=False))
        import os
        os.makedirs(args.out_dir, exist_ok=True)
        suffix = f"{args.mode}_{args.universe}" if not args.tickers else args.mode
        out_path = os.path.join(args.out_dir, f"ord_scan_{label.lower()}_{suffix}.csv")
        df.to_csv(out_path, index=False)
        print(f"[write] full ranking -> {out_path}")


if __name__ == "__main__":
    main()
