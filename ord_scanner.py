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
MIN_BARS    = {"W": 80,   "M": 48}

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


def ord_volume_buy(legs: List[Dict]) -> Dict:
    """Evaluate Ord-Volume buy signal on the most recent legs.

    Interpretation: a bullish setup requires the *current* (last) leg to be
    up and the *prior completed* leg to be a down leg whose Ord-Volume is
    substantially lower than the up leg before it. The current up leg must
    then be expanding in Ord-Volume relative to that down leg.
    """
    if len(legs) < 3:
        return {"signal": False, "reason": "insufficient legs"}
    current = legs[-1]
    if current["dir"] != "up":
        return {"signal": False, "reason": "not in up leg"}
    down = legs[-2]
    if down["dir"] != "down":
        return {"signal": False, "reason": "prior leg not down"}

    prev_up = None
    for L in reversed(legs[:-2]):
        if L["dir"] == "up":
            prev_up = L
            break
    if prev_up is None:
        return {"signal": False, "reason": "no prior up leg"}

    shrink = down["ov"] / prev_up["ov"] if prev_up["ov"] > 0 else float("inf")
    expand = current["ov"] / down["ov"] if down["ov"] > 0 else 0.0

    if shrink <= OV_STRONG_SHRINK:
        strength = "STRONG"
    elif shrink <= OV_GOOD_SHRINK:
        strength = "GOOD"
    elif shrink <= OV_MARGINAL_SHRINK:
        strength = "MARGINAL"
    else:
        strength = None

    return {
        "signal": strength is not None,
        "confirmed": bool(expand >= OV_CONFIRM_STOCK),
        "shrink": float(shrink),
        "expand": float(expand),
        "strength": strength or "NONE",
    }


def low_vol_retest(df: pd.DataFrame, legs: List[Dict]) -> Dict:
    """Bar-level Swing P&V: does the most recent pullback probe the last swing
    low on shrinking volume vs the origin bar of that swing low?
    """
    if len(legs) < 3:
        return {"signal": False}
    # find last confirmed swing low idx
    # the down leg legs[-2] ends at a low; that low bar is its end_idx
    down = legs[-2]
    current = legs[-1]
    if down["dir"] != "down" or current["dir"] != "up":
        return {"signal": False}
    origin_idx = down["end_idx"]
    origin_vol = float(df["Volume"].iloc[origin_idx])
    if origin_vol <= 0:
        return {"signal": False}
    # search the *current up leg* for any bar that revisited the origin low
    # on shrinking volume. Exclude the origin bar itself so the ratio can't
    # trivially resolve to 1.0.
    start = origin_idx + 1
    end   = current["end_idx"] + 1
    if end <= start:
        return {"signal": False}
    leg_slice = df.iloc[start:end]
    origin_low = float(df["Low"].iloc[origin_idx])
    probes = leg_slice[leg_slice["Low"] <= origin_low * 1.01]
    if probes.empty:
        return {"signal": False}
    best_ratio = float(probes["Volume"].min() / origin_vol)
    return {
        "signal": best_ratio <= SPV_REVERSAL_MAX,
        "ratio": best_ratio,
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
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(df: pd.DataFrame, ticker: str, theta: float) -> Optional[Dict]:
    df = df.dropna().copy()
    if len(df) < max(BB_LENGTH + 5, TREND_MA + 5):
        return None

    pivots = zigzag(df["High"], df["Low"], theta)
    legs = build_legs(df, pivots)

    ov = ord_volume_buy(legs)
    spv = low_vol_retest(df, legs)
    sq = squeeze_state(df)
    asym = vol_asymmetry(df)

    ma50 = df["Close"].rolling(TREND_MA).mean().iloc[-1]
    close = float(df["Close"].iloc[-1])
    above_ma = bool(close > ma50) if pd.notna(ma50) else False

    score = 0
    if ov["signal"]:
        score += {"STRONG": 3, "GOOD": 2, "MARGINAL": 1}.get(ov["strength"], 0)
        if ov.get("confirmed"):
            score += 2
    if spv["signal"]:
        score += 2
    if sq["released"]:
        score += 3
    elif sq["in_squeeze"] and sq["bw_pctile"] <= SQUEEZE_BW_PCTL:
        score += 2
    elif sq["bw_pctile"] <= SQUEEZE_BW_PCTL:
        score += 1
    if asym["asymmetry"] >= ASYM_MIN_BULLISH:
        score += 1
    if asym["asymmetry"] >= 1.5:
        score += 1
    if above_ma:
        score += 1

    return {
        "ticker": ticker,
        "score": score,
        "close": round(close, 2),
        "ov_sig": ov["signal"],
        "ov_str": ov.get("strength"),
        "ov_shrink": round(ov.get("shrink", np.nan), 2),
        "ov_expand": round(ov.get("expand", np.nan), 2),
        "spv_sig": spv["signal"],
        "spv_ratio": round(spv.get("ratio", np.nan), 2) if spv.get("ratio") is not None else np.nan,
        "squeeze": sq["in_squeeze"],
        "released": sq["released"],
        "bw_pctile": round(sq["bw_pctile"], 2),
        "asym": round(asym["asymmetry"], 2),
        "above_ma50": above_ma,
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


def scan(tickers: List[str], tf: str) -> pd.DataFrame:
    print(f"[scan] downloading {len(tickers)} tickers @ {INTERVAL[tf]} (period={LOOKBACK[tf]})")
    panel = download_panel(tickers, tf)

    rows: List[Dict] = []
    for t in tickers:
        df = extract_ticker_df(panel, t)
        if df is None or df.empty:
            continue
        df = df.dropna()
        if len(df) < MIN_BARS[tf]:
            continue
        try:
            row = score_candidate(df, t, SWING_THETA[tf])
        except Exception as e:
            # keep scanning on per-ticker errors
            continue
        if row is not None:
            rows.append(row)

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values(["score", "asym"], ascending=[False, False])
    return out.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1] if __doc__ else "")
    ap.add_argument("--tf", choices=["W", "M", "both"], default="both",
                    help="timeframe: weekly, monthly, or both (default)")
    ap.add_argument("--top", type=int, default=25, help="top N to print")
    ap.add_argument("--tickers", nargs="+", default=None,
                    help="explicit ticker list (default: live S&P 500 from wiki)")
    ap.add_argument("--min-score", type=int, default=4,
                    help="drop rows below this composite score")
    ap.add_argument("--out-dir", default=".",
                    help="directory to write per-timeframe CSV results")
    args = ap.parse_args()

    tickers = args.tickers if args.tickers else fetch_sp500_tickers()
    print(f"[universe] {len(tickers)} tickers")

    tfs = ["W", "M"] if args.tf == "both" else [args.tf]
    for tf in tfs:
        label = "WEEKLY" if tf == "W" else "MONTHLY"
        print(f"\n================  {label} BREAKOUT CANDIDATES  ================")
        df = scan(tickers, tf)
        if df.empty:
            print("no results")
            continue
        filtered = df[df["score"] >= args.min_score].head(args.top)
        if filtered.empty:
            print(f"no candidates above min-score {args.min_score}; showing top {args.top} by score")
            filtered = df.head(args.top)
        with pd.option_context("display.max_rows", None,
                               "display.max_columns", None,
                               "display.width", 200):
            print(filtered.to_string(index=False))
        import os
        os.makedirs(args.out_dir, exist_ok=True)
        out_path = os.path.join(args.out_dir, f"ord_scan_{label.lower()}.csv")
        df.to_csv(out_path, index=False)
        print(f"[write] full ranking -> {out_path}")


if __name__ == "__main__":
    main()
