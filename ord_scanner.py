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
# Scoring
# ---------------------------------------------------------------------------

def score_candidate(df: pd.DataFrame, ticker: str, theta: float) -> Optional[Dict]:
    df = df.dropna().copy()
    if len(df) < max(BB_LENGTH + 5, TREND_MA + 5):
        return None

    pivots = zigzag(df["High"], df["Low"], theta)
    legs = build_legs(df, pivots)

    ov   = ord_volume_buy(df, legs)
    spv  = shakeout_retest(df, legs)
    sq   = squeeze_state(df)
    asym = vol_asymmetry(df)
    q    = qullamaggie_setup(df)

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

    q_score = int(q.get("q_score", 0))
    combined = ord_score + q_score

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
    out = pd.DataFrame(rows).sort_values(
        ["combined", "ord_score", "q_score", "asym"],
        ascending=[False, False, False, False],
    )
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
        filtered = df[df["combined"] >= args.min_score].head(args.top)
        if filtered.empty:
            print(f"no candidates above min-score {args.min_score}; showing top {args.top} by combined")
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
