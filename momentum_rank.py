"""
Qullamaggie-style momentum watchlist qualifier.

For each ticker we compute three momentum ratios on DAILY bars:

  mom_1m = last_close / SMA(close, 25)
  mom_3m = last_close / SMA(close, 66)
  mom_6m = last_close / SMA(close, 126)

The universe is ranked by each, the top N (default 30) per metric are
surfaced separately, and the intersection (top N on all three timeframes =
sustained leadership) is the headline list. Output is a CSV that can be
fed directly into volume_screen.py for tightness / POC checks.
"""

import argparse
import contextlib
import io
import os
import pickle
import re
import sys
import time

import numpy as np
import pandas as pd
import yfinance as yf


_RATE_LIMIT_PAT = re.compile(
    r"(rate ?limit|too many requests|429|YFRateLimit|temporarily blocked|throttl)",
    re.IGNORECASE,
)


def _looks_rate_limited(captured_text: str) -> bool:
    """Return True only if captured yfinance stderr shows an actual rate-limit
    signal. 'possibly delisted' alone is NOT rate-limit — it means the ticker
    is genuinely gone (common for old SPAC warrants/units in the universe)."""
    return bool(_RATE_LIMIT_PAT.search(captured_text or ""))

# Reuse the universe definitions from scan_failed_bearish.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_failed_bearish import get_universe, apply_universe_filters  # noqa: E402


PICKLE_TMPL = "/tmp/cyclepapa_dl_{universe}_daily_{years}y.pkl"


def load_pickle_frames(universe, years):
    path = PICKLE_TMPL.format(universe=universe, years=years)
    if not os.path.exists(path):
        return {}, set()
    with open(path, "rb") as f:
        state = pickle.load(f)
    return state.get("frames", {}), set(state.get("done", []))


def save_pickle(universe, years, frames, done):
    path = PICKLE_TMPL.format(universe=universe, years=years)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            pickle.dump({"frames": frames, "done": list(done)}, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f"    checkpoint save failed: {e}")


def download_daily(universe, tickers, years=2, chunk_size=80, batch_sleep=15):
    frames, done = load_pickle_frames(universe, years)
    if frames:
        print(f"  resumed: {len(frames)} kept, {len(done)} already attempted")
    todo = [t for t in tickers if t not in done]
    total = len(todo)
    n_batches = (total + chunk_size - 1) // chunk_size
    consec_rate_limited = 0
    for i in range(0, total, chunk_size):
        b = i // chunk_size + 1
        chunk = todo[i:i + chunk_size]
        kept_before = len(frames)
        print(f"  batch {b}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} of {total} (kept: {kept_before})")
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                data = yf.download(
                    chunk, period=f"{years}y", interval="1d",
                    group_by="ticker", threads=True, progress=False, auto_adjust=True,
                )
        except Exception as e:
            print(f"    batch failed: {e}")
            data = None
        sys.stderr.write(err_buf.getvalue())
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        sub = data[t].dropna(how="all")
                    else:
                        sub = data.dropna(how="all")
                    if "Close" in sub.columns and len(sub) >= 130:
                        frames[t] = sub
                except Exception:
                    continue
        kept_in_batch = len(frames) - kept_before
        # Only treat as rate-limited if yfinance stderr shows an actual
        # 429 / rate-limit / throttling signature. "possibly delisted" alone
        # = genuinely gone tickers (warrants/dead SPACs); mark them done.
        if _looks_rate_limited(err_buf.getvalue()) and kept_in_batch / max(len(chunk), 1) < 0.5:
            consec_rate_limited += 1
            cool_sleep = min(60 + consec_rate_limited * 30, 300)
            print(f"    rate-limited ({kept_in_batch}/{len(chunk)} kept; 429 in stderr); "
                  f"NOT marking done. Cooling for {cool_sleep}s "
                  f"(consec rate-limited batches: {consec_rate_limited})")
            time.sleep(cool_sleep)
            continue
        consec_rate_limited = 0
        done.update(chunk)
        save_pickle(universe, years, frames, done)
        if b < n_batches:
            time.sleep(batch_sleep)
    return frames


SPY_PICKLE = "/tmp/cyclepapa_spy_daily.pkl"
SPY_MONTHLY_PICKLE = "/tmp/cyclepapa_spy_monthly.pkl"
PICKLE_MONTHLY_TMPL = "/tmp/cyclepapa_dl_{universe}_monthly_{years}y.pkl"
PICKLE_INTRADAY_TMPL = "/tmp/cyclepapa_dl_{universe}_{interval}_{period}.pkl"

# Intraday spec for TD MTF per Pine.
# (yfinance interval, yfinance period, internal key, MTF weight)
# Weight: <1.0 = down-weighted vs daily-and-up. Daily/W/M all = 1.0.
INTRADAY_SPEC = [
    # key  yf_interval  yf_period  weight
    ("1m",   "1m",        "5d",     0.1),
    ("5m",   "5m",        "1mo",    0.2),
    ("15m",  "15m",       "60d",    0.4),
    ("1h",   "1h",        "3mo",    0.6),
]
# 4h is derived by resampling 1h


def load_pickle_frames_intraday(universe, interval, period):
    path = PICKLE_INTRADAY_TMPL.format(universe=universe, interval=interval, period=period)
    if not os.path.exists(path):
        return {}, set()
    try:
        with open(path, "rb") as f:
            state = pickle.load(f)
        return state.get("frames", {}), set(state.get("done", []))
    except Exception:
        return {}, set()


def save_pickle_intraday(universe, interval, period, frames, done):
    path = PICKLE_INTRADAY_TMPL.format(universe=universe, interval=interval, period=period)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            pickle.dump({"frames": frames, "done": list(done)}, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f"    intraday {interval} checkpoint save failed: {e}")


def download_intraday(universe, tickers, interval, period, chunk_size=80, batch_sleep=10,
                       min_bars=30):
    """Resumable intraday bar download (yf interval='1m'/'5m'/'15m'/'1h').
    Loads existing pickle first, only attempts unprocessed tickers."""
    frames, done = load_pickle_frames_intraday(universe, interval, period)
    if frames:
        print(f"  intraday {interval} resumed: {len(frames)} kept, {len(done)} attempted")
    todo = [t for t in tickers if t not in done]
    total = len(todo)
    if total == 0:
        return frames
    n_batches = (total + chunk_size - 1) // chunk_size
    consec_rate_limited = 0
    for i in range(0, total, chunk_size):
        b = i // chunk_size + 1
        chunk = todo[i:i + chunk_size]
        kept_before = len(frames)
        print(f"  intraday {interval} batch {b}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} (kept: {kept_before})")
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                data = yf.download(chunk, period=period, interval=interval,
                                   group_by="ticker", threads=True, progress=False,
                                   auto_adjust=True)
        except Exception as e:
            print(f"    batch failed: {e}")
            data = None
        sys.stderr.write(err_buf.getvalue())
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        sub = data[t].dropna(how="all")
                    else:
                        sub = data.dropna(how="all")
                    if "Close" in sub.columns and len(sub) >= min_bars:
                        frames[t] = sub
                except Exception:
                    continue
        kept_in_batch = len(frames) - kept_before
        if _looks_rate_limited(err_buf.getvalue()) and kept_in_batch / max(len(chunk), 1) < 0.5:
            consec_rate_limited += 1
            cool_sleep = min(60 + consec_rate_limited * 30, 300)
            print(f"    rate-limited ({kept_in_batch}/{len(chunk)} kept; 429 in stderr); "
                  f"NOT marking done. Cooling {cool_sleep}s")
            time.sleep(cool_sleep)
            continue
        consec_rate_limited = 0
        done.update(chunk)
        save_pickle_intraday(universe, interval, period, frames, done)
        if b < n_batches:
            time.sleep(batch_sleep)
    return frames


def load_or_download_spy_monthly(years=10):
    """Cached SPY monthly close (1mo bars). ~120 bars at 10y - tiny pickle."""
    if os.path.exists(SPY_MONTHLY_PICKLE):
        try:
            with open(SPY_MONTHLY_PICKLE, "rb") as f:
                spy = pickle.load(f)
            if (pd.Timestamp.today() - spy.index[-1]).days <= 35:
                print(f"  SPY monthly loaded from cache ({len(spy)} bars)")
                return spy
        except Exception:
            pass
    print(f"  Downloading SPY monthly ({years}y)...")
    data = yf.download("SPY", period=f"{years}y", interval="1mo",
                       auto_adjust=True, progress=False)
    if data is None or data.empty:
        return None
    spy_close = data["Close"]
    if isinstance(spy_close, pd.DataFrame):
        spy_close = spy_close.iloc[:, 0]
    spy = pd.to_numeric(spy_close, errors="coerce").dropna()
    try:
        with open(SPY_MONTHLY_PICKLE, "wb") as f:
            pickle.dump(spy, f)
    except Exception:
        pass
    return spy


def load_pickle_frames_monthly(universe, years):
    path = PICKLE_MONTHLY_TMPL.format(universe=universe, years=years)
    if not os.path.exists(path):
        return {}, set()
    with open(path, "rb") as f:
        state = pickle.load(f)
    return state.get("frames", {}), set(state.get("done", []))


def save_pickle_monthly(universe, years, frames, done):
    path = PICKLE_MONTHLY_TMPL.format(universe=universe, years=years)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            pickle.dump({"frames": frames, "done": list(done)}, f)
        os.replace(tmp, path)
    except Exception as e:
        print(f"    monthly checkpoint save failed: {e}")


def download_monthly(universe, tickers, years=10, chunk_size=100, batch_sleep=10):
    """Download yfinance monthly bars (interval='1mo'). ~120 bars/ticker at 10y."""
    frames, done = load_pickle_frames_monthly(universe, years)
    if frames:
        print(f"  monthly resumed: {len(frames)} kept, {len(done)} attempted")
    todo = [t for t in tickers if t not in done]
    total = len(todo)
    n_batches = (total + chunk_size - 1) // chunk_size
    consec_rate_limited = 0
    for i in range(0, total, chunk_size):
        b = i // chunk_size + 1
        chunk = todo[i:i + chunk_size]
        kept_before = len(frames)
        print(f"  monthly batch {b}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} (kept: {kept_before})")
        err_buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(err_buf):
                data = yf.download(chunk, period=f"{years}y", interval="1mo",
                                   group_by="ticker", threads=True, progress=False,
                                   auto_adjust=True)
        except Exception as e:
            print(f"    batch failed: {e}")
            data = None
        sys.stderr.write(err_buf.getvalue())
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        sub = data[t].dropna(how="all")
                    else:
                        sub = data.dropna(how="all")
                    if "Close" in sub.columns and len(sub) >= 24:
                        frames[t] = sub
                except Exception:
                    continue
        kept_in_batch = len(frames) - kept_before
        if _looks_rate_limited(err_buf.getvalue()) and kept_in_batch / max(len(chunk), 1) < 0.5:
            consec_rate_limited += 1
            cool_sleep = min(60 + consec_rate_limited * 30, 300)
            print(f"    rate-limited ({kept_in_batch}/{len(chunk)} kept; 429 in stderr); "
                  f"NOT marking done. Cooling {cool_sleep}s")
            time.sleep(cool_sleep)
            continue
        consec_rate_limited = 0
        done.update(chunk)
        save_pickle_monthly(universe, years, frames, done)
        if b < n_batches:
            time.sleep(batch_sleep)
    return frames


def load_or_download_spy(years=3):
    if os.path.exists(SPY_PICKLE):
        try:
            with open(SPY_PICKLE, "rb") as f:
                spy = pickle.load(f)
            # Refresh if more than 2 days stale
            if (pd.Timestamp.today() - spy.index[-1]).days <= 2:
                print(f"  SPY benchmark loaded from cache ({len(spy)} bars, last={spy.index[-1].date()})")
                return spy
        except Exception:
            pass
    print(f"  Downloading SPY benchmark ({years}y daily)...")
    data = yf.download("SPY", period=f"{years}y", interval="1d",
                       auto_adjust=True, progress=False)
    if data is None or data.empty:
        return None
    spy_close = data["Close"]
    if isinstance(spy_close, pd.DataFrame):
        spy_close = spy_close.iloc[:, 0]
    spy = pd.to_numeric(spy_close, errors="coerce").dropna()
    try:
        with open(SPY_PICKLE, "wb") as f:
            pickle.dump(spy, f)
    except Exception:
        pass
    return spy


def macd(close_series, fast=12, slow=26, signal_n=9):
    ema_fast = close_series.ewm(span=fast, adjust=False).mean()
    ema_slow = close_series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_n, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def dma200_slope_pct(close_series, slope_window=20):
    if len(close_series) < 220:
        return None, None
    dma = close_series.rolling(200).mean().dropna()
    if len(dma) < slope_window:
        return None, None
    last_dma = float(dma.iloc[-1])
    recent = dma.tail(slope_window).values
    slope, _ = np.polyfit(np.arange(len(recent)), recent, 1)
    return float(slope / last_dma * 100), float((close_series.iloc[-1] - last_dma) / last_dma * 100)


def detect_darvas_box(weekly, min_box_weeks=4):
    """Find the most recent Darvas-style box on weekly bars.

    Box top  = the most recent weekly high that has not been exceeded for
               at least min_box_weeks subsequent bars.
    Box bot  = the lowest weekly low since the box-top bar.
    Returns dict of box geometry plus the position of the current close
    within the box. None if no qualifying box exists.
    """
    if len(weekly) < min_box_weeks * 2:
        return None
    high = weekly["High"].astype(float).values
    low = weekly["Low"].astype(float).values
    close = weekly["Close"].astype(float).values
    last_idx = len(weekly) - 1

    box_top_idx = None
    # Walk backward looking for a high that has stood for min_box_weeks+
    for i in range(last_idx - min_box_weeks, -1, -1):
        if np.all(high[i + 1: last_idx + 1] <= high[i]):
            box_top_idx = i
            break
    if box_top_idx is None:
        return None

    box_top = float(high[box_top_idx])
    box_bottom = float(low[box_top_idx: last_idx + 1].min())
    box_len_w = last_idx - box_top_idx
    if box_bottom <= 0 or box_top <= box_bottom:
        return None
    box_height_pct = (box_top - box_bottom) / box_bottom * 100
    last = float(close[-1])
    pos_in_box_pct = (last - box_bottom) / (box_top - box_bottom) * 100
    dist_from_top_pct = (last - box_top) / box_top * 100

    # Look for a nested tighter base inside the most recent 1/2 of this box
    inner = None
    half_start = box_top_idx + box_len_w // 2
    if last_idx - half_start >= min_box_weeks:
        inner_top = float(high[half_start: last_idx + 1].max())
        inner_bot = float(low[half_start: last_idx + 1].min())
        if inner_bot > 0 and inner_top > inner_bot:
            inner_height_pct = (inner_top - inner_bot) / inner_bot * 100
            if inner_height_pct < box_height_pct * 0.6:
                inner = {
                    "inner_top": inner_top,
                    "inner_bottom": inner_bot,
                    "inner_height_pct": inner_height_pct,
                    "inner_weeks": last_idx - half_start,
                }
    out = {
        "box_top": box_top,
        "box_bottom": box_bottom,
        "box_height_pct": float(box_height_pct),
        "box_length_weeks": int(box_len_w),
        "pos_in_box_pct": float(pos_in_box_pct),
        "dist_from_box_top_pct": float(dist_from_top_pct),
    }
    if inner:
        out.update(inner)
    return out


def true_range(high, low, close_prev):
    return np.maximum(
        high - low,
        np.maximum(np.abs(high - close_prev), np.abs(low - close_prev)),
    )


def find_swing_pivots(high_arr, low_arr, lookback=5, min_swing_pct=4.0):
    """ZigZag-style alternating swing pivots: (idx, price, 'H'|'L').
    Each pivot is a local extremum over +/- lookback bars and is at least
    min_swing_pct away from the prior pivot."""
    n = len(high_arr)
    pivots = []
    for i in range(lookback, n - lookback):
        is_high = all(high_arr[i] >= high_arr[i - k] for k in range(1, lookback + 1)) and \
                  all(high_arr[i] >= high_arr[i + k] for k in range(1, lookback + 1))
        is_low = all(low_arr[i] <= low_arr[i - k] for k in range(1, lookback + 1)) and \
                 all(low_arr[i] <= low_arr[i + k] for k in range(1, lookback + 1))
        if is_high and not is_low:
            pivots.append((i, float(high_arr[i]), "H"))
        elif is_low and not is_high:
            pivots.append((i, float(low_arr[i]), "L"))
    if not pivots:
        return []
    cleaned = [pivots[0]]
    for p in pivots[1:]:
        if p[2] != cleaned[-1][2]:
            cleaned.append(p)
        elif (p[2] == "H" and p[1] > cleaned[-1][1]) or (p[2] == "L" and p[1] < cleaned[-1][1]):
            cleaned[-1] = p
    # Apply minimum swing percent filter (ZigZag style) - skip tiny swings
    if min_swing_pct > 0 and len(cleaned) > 1:
        filtered = [cleaned[0]]
        for p in cleaned[1:]:
            prior_px = filtered[-1][1]
            if prior_px == 0 or not np.isfinite(prior_px):
                continue
            swing_pct = abs(p[1] - prior_px) / prior_px * 100
            if swing_pct >= min_swing_pct:
                filtered.append(p)
            else:
                # too small a swing; replace the prior pivot if same direction
                if (p[2] == "H" and p[1] > filtered[-1][1]) or \
                   (p[2] == "L" and p[1] < filtered[-1][1]):
                    filtered[-1] = p
        # Re-dedupe consecutive same-type after replacement
        re_cleaned = [filtered[0]]
        for p in filtered[1:]:
            if p[2] != re_cleaned[-1][2]:
                re_cleaned.append(p)
            elif (p[2] == "H" and p[1] > re_cleaned[-1][1]) or (p[2] == "L" and p[1] < re_cleaned[-1][1]):
                re_cleaned[-1] = p
        cleaned = re_cleaned
    return cleaned


def _near(value, target, tol=0.07):
    return abs(value - target) / target <= tol if target else False


def detect_harmonic(pivots, current_close):
    """Inspect the last 5 alternating pivots for a harmonic pattern."""
    if len(pivots) < 5:
        return None
    X, A, B, C, D = pivots[-5:]
    types = "".join(p[2] for p in [X, A, B, C, D])
    if types == "LHLHL":
        bullish = True
    elif types == "HLHLH":
        bullish = False
    else:
        return None
    xa = abs(A[1] - X[1])
    ab = abs(B[1] - A[1])
    bc = abs(C[1] - B[1])
    cd = abs(D[1] - C[1])
    xc = abs(C[1] - X[1])
    if xa <= 0 or ab <= 0:
        return None
    ab_xa = ab / xa
    bc_ab = bc / ab if ab else 0
    cd_bc = cd / bc if bc else 0
    bc_xa = bc / xa
    cd_xc = cd / xc if xc else 0
    d_x_ratio = abs(D[1] - X[1]) / xa

    is_beyond_x = (bullish and D[1] < X[1]) or (not bullish and D[1] > X[1])

    candidates = []
    # Tolerances widened to 10-12% so the screener catches near-fits;
    # the quality score reflects how tight the actual ratios are.
    def _q(actual, target):
        return max(0.0, 1.0 - abs(actual - target) / target / 2)  # 1.0 perfect, 0.0 50% off

    # Gartley:    AB=0.618, BC 0.30-0.95, CD 1.05-1.70, D=0.786 XA
    if _near(ab_xa, 0.618, 0.12) and 0.30 <= bc_ab <= 0.95 and \
       1.05 <= cd_bc <= 1.70 and _near(d_x_ratio, 0.786, 0.10):
        candidates.append(("Gartley", 0.6 * _q(ab_xa, 0.618) + 0.4 * _q(d_x_ratio, 0.786)))
    # Bat:        AB=0.50,  BC 0.30-0.95, CD 1.50-2.80, D=0.886 XA
    if _near(ab_xa, 0.50, 0.15) and 0.30 <= bc_ab <= 0.95 and \
       1.50 <= cd_bc <= 2.80 and _near(d_x_ratio, 0.886, 0.08):
        candidates.append(("Bat", 0.6 * _q(ab_xa, 0.50) + 0.4 * _q(d_x_ratio, 0.886)))
    # Butterfly:  AB=0.786, BC 0.30-0.95, CD 1.50-2.80, D 1.10-1.70 XA, beyond X
    if _near(ab_xa, 0.786, 0.12) and 0.30 <= bc_ab <= 0.95 and \
       1.50 <= cd_bc <= 2.80 and 1.10 <= d_x_ratio <= 1.70 and is_beyond_x:
        candidates.append(("Butterfly", 0.6 * _q(ab_xa, 0.786) + 0.4 * _q(d_x_ratio, 1.272)))
    # Crab:       AB 0.30-0.65, BC 0.30-0.95, CD 2.0-3.80, D 1.40-1.80 XA, beyond X
    if 0.30 <= ab_xa <= 0.65 and 0.30 <= bc_ab <= 0.95 and \
       2.0 <= cd_bc <= 3.80 and 1.40 <= d_x_ratio <= 1.80 and is_beyond_x:
        candidates.append(("Crab", 0.5 * _q(d_x_ratio, 1.618) + 0.5))
    # Deep Crab:  AB=0.886, BC 0.30-0.95, CD 1.80-3.80, D 1.40-1.80 XA, beyond X
    if _near(ab_xa, 0.886, 0.08) and 0.30 <= bc_ab <= 0.95 and \
       1.80 <= cd_bc <= 3.80 and 1.40 <= d_x_ratio <= 1.80 and is_beyond_x:
        candidates.append(("Deep Crab", 0.6 * _q(ab_xa, 0.886) + 0.4 * _q(d_x_ratio, 1.618)))
    # Cypher:     AB 0.30-0.65, BC 1.05-1.60 of XA, CD=0.786 XC
    if 0.30 <= ab_xa <= 0.65 and 1.05 <= bc_xa <= 1.60 and \
       _near(cd_xc, 0.786, 0.12):
        candidates.append(("Cypher", 0.5 * _q(cd_xc, 0.786) + 0.4))
    # AB=CD (4-point simpler): C retraces ~0.618 of AB, then D where CD ≈ AB
    # Allowing 0.50-0.786 for C, and CD length 0.85-1.15 of AB
    cd_ab = cd / ab if ab else 0
    bc_ab_inv = bc / ab if ab else 0
    if 0.45 <= bc_ab_inv <= 0.85 and 0.85 <= cd_ab <= 1.15:
        candidates.append(("AB=CD", 0.3 + 0.4 * _q(cd_ab, 1.0)))

    if not candidates:
        return None
    pattern, quality = max(candidates, key=lambda c: c[1])
    dist_from_d_pct = (current_close - D[1]) / D[1] * 100
    return {
        "pattern": pattern,
        "direction": "bullish" if bullish else "bearish",
        "quality": quality,
        "D_price": D[1],
        "D_bar_idx": D[0],
        "dist_from_d_pct": dist_from_d_pct,
        "ab_xa": ab_xa,
        "bc_ab": bc_ab,
        "cd_bc": cd_bc,
        "d_x_ratio": d_x_ratio,
    }


def compute_harmonics_for_tf(df_ohlc, lookback=5, min_swing_pct=4.0,
                              recent_d_max_bars=15, close_near_d_pct=10.0):
    """Find most recent harmonic pattern on a single timeframe.
    Returns None if D pivot is too old or current price is too far from D."""
    if "High" not in df_ohlc.columns or len(df_ohlc) < lookback * 2 + 6:
        return None
    high = pd.to_numeric(df_ohlc["High"], errors="coerce").values
    low = pd.to_numeric(df_ohlc["Low"], errors="coerce").values
    close_last = float(pd.to_numeric(df_ohlc["Close"], errors="coerce").iloc[-1])
    pivots = find_swing_pivots(high, low, lookback=lookback, min_swing_pct=min_swing_pct)
    h = detect_harmonic(pivots, close_last)
    if h is None:
        return None
    bars_since_d = len(df_ohlc) - 1 - h["D_bar_idx"]
    if bars_since_d > recent_d_max_bars:
        return None
    if abs(h["dist_from_d_pct"]) > close_near_d_pct:
        # Current price has already moved away from D - pattern played out
        return None
    h["bars_since_d"] = bars_since_d
    return h


def compute_td_sequential(df_ohlc, max_cd=13):
    """TD Sequential current state. Ports the Pine logic supplied by the
    user (Enhanced MTF TD Sequential, malikmck):

      bull_count++ when close<close[-4], capped at 9
      bear_count++ when close>close[-4], capped at 9
      buy_cd starts at 1 when bull_count==9, increments when close<low[-2]
      buy_perfect = bull_count==9 AND low<low[-2] AND low<low[-3]
      stealth_buy = bull_count[-1]==8 AND low<=close[-4] AND bull_count!=9
      double_buy  = bull_count==9 AND prior bull_count==9 occurrence value 9
      triple_buy  = double_buy AND 2nd-prior bull_count==9 also value 9
    """
    if "Close" not in df_ohlc.columns or len(df_ohlc) < 30:
        return None
    close = pd.to_numeric(df_ohlc["Close"], errors="coerce").astype(float).values
    high = pd.to_numeric(df_ohlc["High"], errors="coerce").astype(float).values
    low = pd.to_numeric(df_ohlc["Low"], errors="coerce").astype(float).values
    n = len(close)
    bull = np.zeros(n, dtype=int)
    bear = np.zeros(n, dtype=int)
    cd_buy = np.zeros(n, dtype=int)
    cd_sell = np.zeros(n, dtype=int)
    for i in range(4, n):
        if close[i] < close[i - 4]:
            bull[i] = bull[i - 1] + 1 if bull[i - 1] < 9 else 1
        else:
            bull[i] = 0
        if close[i] > close[i - 4]:
            bear[i] = bear[i - 1] + 1 if bear[i - 1] < 9 else 1
        else:
            bear[i] = 0
        if bull[i] == 9:
            cd_buy[i] = 1
        elif cd_buy[i - 1] > 0 and cd_buy[i - 1] < max_cd and i >= 2 and close[i] < low[i - 2]:
            cd_buy[i] = cd_buy[i - 1] + 1
        else:
            cd_buy[i] = cd_buy[i - 1]
        if bear[i] == 9:
            cd_sell[i] = 1
        elif cd_sell[i - 1] > 0 and cd_sell[i - 1] < max_cd and i >= 2 and close[i] > high[i - 2]:
            cd_sell[i] = cd_sell[i - 1] + 1
        else:
            cd_sell[i] = cd_sell[i - 1]
    last = n - 1
    buy_perfect = bool(bull[last] == 9 and last >= 3 and low[last] < low[last - 2] and low[last] < low[last - 3])
    sell_perfect = bool(bear[last] == 9 and last >= 3 and high[last] > high[last - 2] and high[last] > high[last - 3])
    stealth_buy = bool(last >= 5 and bull[last - 1] == 8 and low[last] <= close[last - 4] and bull[last] != 9)
    stealth_sell = bool(last >= 5 and bear[last - 1] == 8 and high[last] >= close[last - 4] and bear[last] != 9)

    def _prev_9(arr, idx, occ):
        c = 0
        for j in range(idx - 1, -1, -1):
            if arr[j] == 9:
                c += 1
                if c == occ:
                    return j
        return -1

    double_buy = triple_buy = False
    if bull[last] == 9:
        p1 = _prev_9(bull, last, 1)
        if p1 >= 0 and bull[p1] == 9:
            double_buy = True
            p2 = _prev_9(bull, last, 2)
            if p2 >= 0 and bull[p2] == 9:
                triple_buy = True
    double_sell = triple_sell = False
    if bear[last] == 9:
        p1 = _prev_9(bear, last, 1)
        if p1 >= 0 and bear[p1] == 9:
            double_sell = True
            p2 = _prev_9(bear, last, 2)
            if p2 >= 0 and bear[p2] == 9:
                triple_sell = True
    return {
        "buy_setup": int(bull[last]),
        "sell_setup": int(bear[last]),
        "buy_cd": int(cd_buy[last]),
        "sell_cd": int(cd_sell[last]),
        "buy_perfect": buy_perfect,
        "sell_perfect": sell_perfect,
        "stealth_buy": stealth_buy,
        "stealth_sell": stealth_sell,
        "double_buy": double_buy,
        "double_sell": double_sell,
        "triple_buy": triple_buy,
        "triple_sell": triple_sell,
    }


def td_nets(td):
    """Convert TD state into the 5 net signals the user wants surfaced:
    net_setup, net_cd, net_perfect, net_stealth, net_triple.
    Positive = bullish (downtrend exhaustion / buy signal dominant)."""
    if not td:
        return {"net_setup": 0.0, "net_cd": 0.0, "net_perfect": 0,
                "net_stealth": 0, "net_triple": 0}
    return {
        "net_setup": (td["buy_setup"] - td["sell_setup"]) / 9.0,
        "net_cd": (td["buy_cd"] - td["sell_cd"]) / 13.0,
        "net_perfect": int(td["buy_perfect"]) - int(td["sell_perfect"]),
        "net_stealth": int(td["stealth_buy"]) - int(td["stealth_sell"]),
        "net_triple": int(td["triple_buy"]) - int(td["triple_sell"]),
    }


def compute_squeeze_release(df, period=14, smoothing=7, ma_length=14, hist_window=100):
    """Pine Script Squeeze & Release port (malikmck / YourName).

    averageTrueRange  = ema(TR, 14)
    emaOfATR          = ema(ATR, 28)
    volatilityInd     = emaOfATR - ATR        (positive = vol contracting)
    emaHighLowDiff    = ema(high-low, 28)
    squeezeValue      = ema(volInd / emaHL * 100, 7)
    squeezeValueMA    = ema(squeezeValue, 14)

    HIGH squeezeValue + above its MA  = SQUEEZING (vol coiling)
    crossunder MA                      = RELEASE  (vol expanding)
    """
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")
    need = period * 4 + ma_length + 5
    if len(close) < need:
        return None
    prior_close = close.shift(1).bfill()
    tr = pd.concat([
        high - low,
        (high - prior_close).abs(),
        (low - prior_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    ema_atr = atr.ewm(span=period * 2, adjust=False).mean()
    vol_ind = ema_atr - atr
    ema_hl = (high - low).ewm(span=period * 2, adjust=False).mean().replace(0, 1e-10)
    raw_sq = vol_ind / ema_hl * 100
    sq_v = raw_sq.ewm(span=smoothing, adjust=False).mean()
    sq_ma = sq_v.ewm(span=ma_length, adjust=False).mean()
    if len(sq_v) < 2:
        return None
    sv_now = float(sq_v.iloc[-1])
    ma_now = float(sq_ma.iloc[-1])
    sv_prev = float(sq_v.iloc[-2])
    ma_prev = float(sq_ma.iloc[-2])
    squeezing = sv_now > ma_now
    releasing = sv_now < ma_now
    just_release = bool(releasing and (sv_prev >= ma_prev))
    just_squeeze = bool(squeezing and (sv_prev <= ma_prev))
    rising = sv_now > sv_prev
    # Hyper squeeze: positive squeezeValue rising for 5 bars
    hyper = False
    if len(sq_v) >= 6 and sv_now > 0:
        hyper = all(sq_v.iloc[-i] > sq_v.iloc[-i - 1] for i in range(1, 6))
    # Was-high indicator: relative position vs last hist_window bars
    if len(sq_v) >= hist_window:
        recent_window = sq_v.tail(hist_window)
        q75 = float(recent_window.quantile(0.75))
        q90 = float(recent_window.quantile(0.90))
        max_recent = float(recent_window.max())
        was_high_75 = sv_now > q75 or sv_prev > q75  # at or recently above 75th pct
        was_high_90 = sv_now > q90 or sv_prev > q90
        pct_of_max = sv_now / max_recent if max_recent else 0
    else:
        was_high_75 = was_high_90 = False
        pct_of_max = None
    return {
        "sq_value": sv_now,
        "sq_ma": ma_now,
        "sq_squeezing": bool(squeezing),
        "sq_releasing": bool(releasing),
        "sq_just_release": just_release,
        "sq_just_squeeze": just_squeeze,
        "sq_rising": bool(rising),
        "sq_hyper": bool(hyper),
        "sq_was_high_75": bool(was_high_75),
        "sq_was_high_90": bool(was_high_90),
        "sq_pct_of_max": pct_of_max,
    }


def compute_close_only_asymmetry(close_series, period=14, smooth=7, slow=14, min_bars=None):
    """Asymmetry on a close-only series (used for relative-to-SPY price).
    up_move = max(delta, 0), dn_move = max(-delta, 0)."""
    if min_bars is None:
        min_bars = period * 3 + slow + 2
    if len(close_series) < min_bars:
        return None
    delta = close_series.diff().dropna()
    up = delta.clip(lower=0)
    dn = (-delta).clip(lower=0)
    up_s = up.ewm(span=period, adjust=False).mean()
    dn_s = dn.ewm(span=period, adjust=False).mean()
    ratio = up_s / (up_s + dn_s + 1e-10)
    asym = ratio.ewm(span=smooth, adjust=False).mean() * 100
    asym_ma = asym.ewm(span=slow, adjust=False).mean()
    if len(asym) < 2:
        return None
    rising = bool(asym.iloc[-1] > asym.iloc[-2])
    above_ma = bool(asym.iloc[-1] > asym_ma.iloc[-1])
    crossed_up = bool(above_ma and (asym.iloc[-2] <= asym_ma.iloc[-2]))
    return {
        "asym_now": float(asym.iloc[-1]),
        "asym_ma": float(asym_ma.iloc[-1]),
        "asym_rising": rising,
        "asym_above_ma": above_ma,
        "asym_just_crossed_up": crossed_up,
    }


def compute_volatility_asymmetry(df, period=14, smooth=7, slow=14, lookback=5,
                                  threshold_pct=5.0):
    """Pine Script logic (malikmck / YourName):
      upward = max(high - close[1], 0)
      downward = max(close[1] - low, 0)
      ratio = ema(upward, period) / (ema(upward, period) + ema(downward, period))
      asym = ema(ratio * 100, smooth) ; asym_ma = ema(asym, slow)
    """
    high = pd.to_numeric(df["High"], errors="coerce").values
    low = pd.to_numeric(df["Low"], errors="coerce").values
    close = pd.to_numeric(df["Close"], errors="coerce").values
    if len(close) < period * 3 + slow + lookback + 2:
        return None
    prior_close = np.concatenate([[close[0]], close[:-1]])
    up = np.maximum(high - prior_close, 0)
    dn = np.maximum(prior_close - low, 0)
    up_s = pd.Series(up).ewm(span=period, adjust=False).mean()
    dn_s = pd.Series(dn).ewm(span=period, adjust=False).mean()
    ratio = up_s / (up_s + dn_s + 0.0001)
    asym = ratio.ewm(span=smooth, adjust=False).mean() * 100
    asym_ma = asym.ewm(span=slow, adjust=False).mean()
    up_roc = up_s.pct_change(lookback) * 100
    dn_roc = dn_s.pct_change(lookback) * 100
    asym_now = float(asym.iloc[-1])
    asym_ma_now = float(asym_ma.iloc[-1])
    rising = bool(asym.iloc[-1] > asym.iloc[-2])
    above_ma = bool(asym_now > asym_ma_now)
    just_crossed_up = bool(above_ma and asym.iloc[-2] <= asym_ma.iloc[-2])
    upper_asym = bool(up_roc.iloc[-1] > threshold_pct
                      and (abs(dn_roc.iloc[-1]) < threshold_pct / 2 or dn_roc.iloc[-1] < 0))
    return {
        "asym_now": asym_now,
        "asym_ma": asym_ma_now,
        "asym_rising": rising,
        "asym_above_ma": above_ma,
        "asym_just_crossed_up": just_crossed_up,
        "asym_upper_signal": upper_asym,
    }


def compute_ma_respect(close, ma, atr_series, label, slope_lookback_bars=40):
    """MA-respect leg: 5 signals per MA.

    Returns dict with keys ma_{label}_{slope_pct_wk,touch_count,break_count,
    respect_ratio,recovery_bars,vol_asym_near,spring_k,days_above,
    max_run_above_pct,strategy_ir}.
    """
    keys = ["slope_pct_wk", "touch_count", "break_count", "respect_ratio",
            "recovery_bars", "vol_asym_near", "spring_k", "days_above",
            "max_run_above_pct", "strategy_ir"]
    nulls = {f"ma_{label}_{k}": None for k in keys}

    ma_v = ma.dropna()
    if len(ma_v) < slope_lookback_bars or len(close) < 130:
        return nulls

    # 1. Slope %/wk over last slope_lookback_bars
    recent = ma_v.tail(slope_lookback_bars).values
    x = np.arange(len(recent))
    try:
        slope_per_bar, _ = np.polyfit(x, recent, 1)
    except Exception:
        slope_per_bar = 0.0
    slope_pct_wk = float((slope_per_bar * 5) / recent[-1] * 100) if recent[-1] else 0.0

    # 2. Touches + clean breaks over last 60 bars
    n = min(60, len(close) - 1)
    c = close.tail(n).values
    m = ma.reindex(close.tail(n).index).values
    touches = 0
    breaks = 0
    in_break = False
    break_start = None
    recovery_bars = []
    for i in range(len(c)):
        if np.isnan(m[i]) or m[i] == 0:
            continue
        ratio = c[i] / m[i]
        # touch: within +/- 1.5% of MA, close stayed above MA*0.99
        if 0.99 <= ratio <= 1.015:
            touches += 1
        # break: closed below MA*0.98 for 2 consecutive bars
        below = ratio < 0.98
        if below:
            if in_break:
                pass
            else:
                if i > 0 and not np.isnan(m[i - 1]) and m[i - 1] != 0 \
                        and c[i - 1] / m[i - 1] < 0.98:
                    in_break = True
                    break_start = i - 1
                    breaks += 1
        else:
            if in_break and break_start is not None:
                recovery_bars.append(i - break_start)
            in_break = False
            break_start = None
    denom = touches + 2 * breaks
    respect_ratio = float(touches / denom) if denom > 0 else None
    avg_recovery = float(np.mean(recovery_bars)) if recovery_bars else None

    # 3. Vol asymmetry near MA (within 2 ATR)
    ma_vol_asym = None
    atr_v = atr_series.reindex(close.tail(n).index).values
    rets = close.pct_change().reindex(close.tail(n).index).values
    near_mask = (
        ~np.isnan(m) & ~np.isnan(atr_v) & (atr_v > 0)
        & (np.abs(c - m) <= 2 * atr_v)
    )
    near_rets = rets[near_mask]
    near_rets = near_rets[~np.isnan(near_rets)]
    if len(near_rets) >= 6:
        up = near_rets[near_rets > 0]
        dn = near_rets[near_rets < 0]
        if len(up) >= 3 and len(dn) >= 3 and dn.std() > 0:
            ma_vol_asym = float(up.std() / dn.std())

    # 4. Spring constant: r(t+1) = -k * (P(t)-MA(t))/MA(t)
    spring_k = None
    dev = ((close - ma) / ma)
    nxt = close.pct_change().shift(-1)
    valid = (~dev.isna()) & (~nxt.isna()) & (~ma.isna())
    if valid.sum() >= 50:
        xs = dev[valid].values
        ys = nxt[valid].values
        var = xs.var()
        if var > 0:
            cov = float(np.mean((xs - xs.mean()) * (ys - ys.mean())))
            spring_k = float(-cov / var)

    # 5. Days above (current consecutive run) + max run / current run ratio
    above = (close > ma).astype(int)
    above_t = above.tail(252).values
    days_above = 0
    for v in above_t[::-1]:
        if v == 1:
            days_above += 1
        else:
            break
    max_run = 0
    cur = 0
    for v in above_t:
        if v == 1:
            cur += 1
            if cur > max_run:
                max_run = cur
        else:
            cur = 0
    max_run_above_pct = float(days_above / max_run) if max_run > 0 else None

    # 6. Strategy IR: long while close>MA, flat otherwise, last 252 bars
    strategy_ir = None
    in_pos = (close > ma).shift(1).fillna(False).astype(int)
    strat = close.pct_change() * in_pos
    sv = strat.dropna().tail(252)
    if len(sv) >= 100:
        ann_ret = float(sv.mean() * 252)
        ann_vol = float(sv.std() * np.sqrt(252))
        if ann_vol > 0:
            strategy_ir = float(ann_ret / ann_vol)

    return {
        f"ma_{label}_slope_pct_wk": slope_pct_wk,
        f"ma_{label}_touch_count": int(touches),
        f"ma_{label}_break_count": int(breaks),
        f"ma_{label}_respect_ratio": respect_ratio,
        f"ma_{label}_recovery_bars": avg_recovery,
        f"ma_{label}_vol_asym_near": ma_vol_asym,
        f"ma_{label}_spring_k": spring_k,
        f"ma_{label}_days_above": int(days_above),
        f"ma_{label}_max_run_above_pct": max_run_above_pct,
        f"ma_{label}_strategy_ir": strategy_ir,
    }


def compute_minervini(close, high, low, volume, weekly=None, open_series=None):
    """Comprehensive Minervini/VCP screening leg.

    Implements: Stage 2 Trend Template (9 sub-flags), VCP contraction
    detection (weekly), tight-close patterns, inside-day count, closes-in-
    upper-half rate, pocket-pivot detector, dist-to-pivot. Composite
    mv_composite_score in [0, ~30].
    """
    out = {}
    sma50 = close.rolling(50).mean()
    sma150 = close.rolling(150).mean()
    sma200 = close.rolling(200).mean()
    last = float(close.iloc[-1])

    # 52w high/low
    look = min(252, len(close))
    last_low_52w = float(low.tail(look).min())
    last_high_52w = float(high.tail(look).max())

    # ---- Stage 2 Trend Template (9 sub-flags) ----
    def _safe(s, default=False):
        try:
            v = float(s.iloc[-1])
            return v if not np.isnan(v) else None
        except Exception:
            return None
    v_sma50 = _safe(sma50)
    v_sma150 = _safe(sma150)
    v_sma200 = _safe(sma200)
    s2_above_50 = bool(v_sma50 is not None and last > v_sma50)
    s2_above_150 = bool(v_sma150 is not None and last > v_sma150)
    s2_above_200 = bool(v_sma200 is not None and last > v_sma200)
    s2_150_above_200 = bool(v_sma150 is not None and v_sma200 is not None and v_sma150 > v_sma200)
    s2_50_above_150 = bool(v_sma50 is not None and v_sma150 is not None and v_sma50 > v_sma150)
    s2_50_above_200 = bool(v_sma50 is not None and v_sma200 is not None and v_sma50 > v_sma200)
    s2_200_rising = False
    if len(sma200.dropna()) >= 22:
        s2_200_rising = bool(sma200.iloc[-1] > sma200.iloc[-22])
    s2_30_above_low = bool(last_low_52w > 0 and (last / last_low_52w - 1) >= 0.30)
    s2_within_25_of_high = bool(last_high_52w > 0 and (last / last_high_52w) >= 0.75)

    stage2_flags = [s2_above_50, s2_above_150, s2_above_200,
                    s2_150_above_200, s2_50_above_150, s2_50_above_200,
                    s2_200_rising, s2_30_above_low, s2_within_25_of_high]
    stage2_count = sum(stage2_flags)
    out.update({
        "mv_stage2_above_50d": s2_above_50,
        "mv_stage2_above_150d": s2_above_150,
        "mv_stage2_above_200d": s2_above_200,
        "mv_stage2_150_above_200d": s2_150_above_200,
        "mv_stage2_50_above_150d": s2_50_above_150,
        "mv_stage2_50_above_200d": s2_50_above_200,
        "mv_stage2_200_rising": s2_200_rising,
        "mv_stage2_30pct_above_low": s2_30_above_low,
        "mv_stage2_within_25pct_of_high": s2_within_25_of_high,
        "mv_stage2_count": int(stage2_count),
        "mv_stage2_pass": bool(stage2_count >= 9),
    })

    # ---- Tight closes (multi-day pivot) ----
    pct_moves = close.pct_change().abs()
    tight_3d = int((pct_moves.tail(3) < 0.02).sum())
    tight_5d = int((pct_moves.tail(5) < 0.02).sum())
    out["mv_tight_close_3d"] = tight_3d
    out["mv_tight_close_5d"] = tight_5d

    # ---- 5-day volume drying ----
    avg_vol_50 = float(volume.tail(50).mean()) if len(volume) >= 50 else 0.0
    recent_vol_5 = float(volume.tail(5).mean()) if len(volume) >= 5 else 0.0
    out["mv_vol_drying_5d"] = float(recent_vol_5 / avg_vol_50) if avg_vol_50 > 0 else None

    # ---- Inside days (last 5) ----
    inside_days = 0
    if len(close) >= 6:
        for i in range(1, 6):
            if high.iloc[-i] <= high.iloc[-i - 1] and low.iloc[-i] >= low.iloc[-i - 1]:
                inside_days += 1
    out["mv_inside_days_5d"] = int(inside_days)

    # ---- Closes in upper half of day's range ----
    def _upper_half(n):
        if len(close) < n:
            return None
        h = high.tail(n); l = low.tail(n); c = close.tail(n)
        m = (h + l) / 2
        mask = h > l
        if mask.sum() == 0:
            return None
        return float(((c > m) & mask).sum() / mask.sum())
    out["mv_closes_top_half_5d"] = _upper_half(5)
    out["mv_closes_top_half_20d"] = _upper_half(20)

    # ---- Distance to pivot (recent 8w high in daily) ----
    pivot = float(high.tail(40).max()) if len(high) >= 40 else float(high.max())
    out["mv_dist_to_pivot_pct"] = float((pivot - last) / pivot * 100) if pivot > 0 else None
    out["mv_at_pivot"] = bool(out["mv_dist_to_pivot_pct"] is not None
                              and out["mv_dist_to_pivot_pct"] <= 3.0)

    # ---- Pocket pivot (O'Neill / Morales) ----
    pocket = False
    if len(close) >= 12:
        last_up = bool(close.iloc[-1] > close.iloc[-2])
        if last_up:
            vol_today = float(volume.iloc[-1])
            down_vols = []
            for i in range(2, 12):
                if close.iloc[-i] < close.iloc[-i - 1]:
                    down_vols.append(float(volume.iloc[-i]))
            if down_vols and vol_today > max(down_vols):
                pocket = True
    out["mv_pocket_pivot"] = pocket

    # ---- VCP contraction count (weekly) ----
    vcp_count = 0
    contractions = []
    if weekly is not None and len(weekly) >= 12:
        w_close = pd.to_numeric(weekly["Close"], errors="coerce").dropna()
        w_recent = w_close.tail(min(25, len(w_close)))
        # Find local peaks/troughs in 5-bar window
        events = []
        for i in range(2, len(w_recent) - 2):
            win = w_recent.iloc[i - 2:i + 3]
            v = float(w_recent.iloc[i])
            if v == float(win.max()):
                events.append(("peak", i, v))
            elif v == float(win.min()):
                events.append(("trough", i, v))
        # Walk through events, compute peak-to-trough drawdowns
        sorted_events = sorted(events, key=lambda x: x[1])
        for j in range(len(sorted_events) - 1):
            t1, _, p1 = sorted_events[j]
            t2, _, p2 = sorted_events[j + 1]
            if t1 == "peak" and t2 == "trough" and p1 > 0 and p1 > p2:
                contractions.append((p1 - p2) / p1)
        # VCP: count successive tightening contractions from the end
        prior = None
        for amp in reversed(contractions):
            if prior is None:
                prior = amp
                vcp_count += 1
            elif amp < prior * 0.85:  # 15%+ tighter than prior
                vcp_count += 1
                prior = amp
            else:
                break
    out["mv_vcp_count"] = int(vcp_count)
    out["mv_vcp_setup"] = bool(vcp_count >= 2)
    out["mv_vcp_strong_setup"] = bool(vcp_count >= 3)
    out["mv_last_contraction_pct"] = float(contractions[-1] * 100) if contractions else None

    # ---- Composite Minervini score ----
    score = 0.0
    score += stage2_count                          # 0..9
    score += vcp_count * 2                         # 0..6+
    score += tight_5d                              # 0..5
    upper20 = out.get("mv_closes_top_half_20d")
    if upper20 is not None:
        score += upper20 * 5                       # 0..5
    if pocket:
        score += 2
    dist = out.get("mv_dist_to_pivot_pct")
    if dist is not None and dist <= 3.0:
        score += 3
    if out.get("mv_vol_drying_5d") and out["mv_vol_drying_5d"] < 0.8:
        score += 2

    # ============================================================
    # MINERVINI v2 additions (drawn from "Trade Like a Stock Market
    # Wizard" + "Think and Trade Like a Champion")
    # ============================================================

    # ---- All-time high distance (Minervini prefers ATH over 52w high) ----
    ath = float(close.max())
    out["mv_ath"] = ath
    out["mv_dist_from_ath_pct"] = float((ath - last) / ath * 100) if ath > 0 else None
    out["mv_at_ath"] = bool(out["mv_dist_from_ath_pct"] is not None
                            and out["mv_dist_from_ath_pct"] <= 5.0)

    # ---- 3 weeks tight (3 consecutive weekly closes within 1.5%) ----
    three_weeks_tight = False
    if weekly is not None and len(weekly) >= 3:
        w_close = pd.to_numeric(weekly["Close"], errors="coerce").dropna()
        if len(w_close) >= 3:
            last3 = w_close.tail(3).values
            if last3[0] > 0:
                spreads = [(abs(last3[i] - last3[0]) / last3[0]) for i in (1, 2)]
                three_weeks_tight = bool(all(s <= 0.015 for s in spreads))
    out["mv_3w_tight"] = three_weeks_tight
    if three_weeks_tight:
        score += 3  # rare and strong signal

    # ---- Power Trend (Minervini's strongest sustained-trend setup) ----
    # 1) 8+ consecutive weekly closes above weekly 10MA (~50dma equivalent)
    # 2) 200dma rising for 5+ months (110 trading days)
    # 3) Recent 3 weekly closes tight
    power_trend = False
    if weekly is not None and len(weekly) >= 12:
        w_close = pd.to_numeric(weekly["Close"], errors="coerce").dropna()
        if len(w_close) >= 10:
            w_ma10 = w_close.rolling(10).mean()
            recent_w_above_ma = (w_close.tail(8) > w_ma10.tail(8)).all()
        else:
            recent_w_above_ma = False
        sma200_rising_5mo = False
        if len(sma200.dropna()) >= 110:
            sma200_rising_5mo = bool(sma200.iloc[-1] > sma200.iloc[-110])
        power_trend = bool(recent_w_above_ma and sma200_rising_5mo
                           and stage2_count >= 8 and tight_5d >= 2)
    out["mv_power_trend"] = power_trend
    if power_trend:
        score += 5  # rare and strongest

    # ---- Buyable Gap Up (BGU - Morales/Kacher refinement) ----
    # Gap-open up >=5%, day closes in upper half of bar's range,
    # volume >= 1.5x 50d avg
    bgu = False
    if len(close) >= 52:
        prev_close = float(close.iloc[-2])
        today_open = float(open_series.iloc[-1]) if open_series is not None and len(open_series) else None
        today_high = float(high.iloc[-1])
        today_low = float(low.iloc[-1])
        today_close = float(close.iloc[-1])
        today_vol = float(volume.iloc[-1])
        avg_vol_50 = float(volume.tail(50).mean())
        if today_open is not None and prev_close > 0 and today_high > today_low \
                and avg_vol_50 > 0:
            gap_pct = (today_open - prev_close) / prev_close
            close_in_top_half = today_close > (today_high + today_low) / 2
            vol_surge = today_vol / avg_vol_50
            bgu = bool(gap_pct >= 0.05 and close_in_top_half and vol_surge >= 1.5)
    out["mv_buyable_gap_up"] = bgu
    if bgu:
        score += 3

    # ---- Climax top warning (sell-signal) ----
    # Last 2 weeks include largest gain in current trend + largest weekly
    # volume + close in lower half of bar's range
    climax_top = False
    if weekly is not None and len(weekly) >= 30:
        w_close = pd.to_numeric(weekly["Close"], errors="coerce").dropna()
        w_high = pd.to_numeric(weekly["High"], errors="coerce")
        w_low = pd.to_numeric(weekly["Low"], errors="coerce")
        w_vol = pd.to_numeric(weekly["Volume"], errors="coerce")
        w_ret = w_close.pct_change()
        if len(w_ret.dropna()) >= 26:
            last_2w_max_ret = float(w_ret.tail(2).max())
            prior_max_ret = float(w_ret.tail(26).head(24).max())
            last_2w_max_vol = float(w_vol.tail(2).max())
            prior_max_vol = float(w_vol.tail(26).head(24).max())
            climax_top = bool(
                last_2w_max_ret > prior_max_ret
                and last_2w_max_vol > prior_max_vol
                and prior_max_ret > 0.05  # was actually trending
            )
    out["mv_climax_top_warning"] = climax_top

    # ---- Stage 4 / declining (mirror of Stage 2) ----
    stage4_below_50 = bool(v_sma50 is not None and last < v_sma50)
    stage4_below_150 = bool(v_sma150 is not None and last < v_sma150)
    stage4_below_200 = bool(v_sma200 is not None and last < v_sma200)
    stage4_150_below_200 = bool(v_sma150 is not None and v_sma200 is not None and v_sma150 < v_sma200)
    stage4_50_below_150 = bool(v_sma50 is not None and v_sma150 is not None and v_sma50 < v_sma150)
    stage4_200_falling = False
    if len(sma200.dropna()) >= 22:
        stage4_200_falling = bool(sma200.iloc[-1] < sma200.iloc[-22])
    s4_under_25_off_high = bool(last_high_52w > 0 and (last / last_high_52w) < 0.75)
    stage4_count = sum([stage4_below_50, stage4_below_150, stage4_below_200,
                        stage4_150_below_200, stage4_50_below_150,
                        stage4_200_falling, s4_under_25_off_high])
    out["mv_stage4_count"] = int(stage4_count)
    out["mv_stage4_pass"] = bool(stage4_count >= 6)

    # ---- RS Line at new high (vs SPY proxy via mom_6m percentile) ----
    # If we have rel_close index in scope, use it; else approximation via
    # close at a 252d high coinciding with mom_6m positive
    rs_line_new_high = False
    if len(close) >= 252:
        last_close_at_252_high = float(close.iloc[-1]) == float(close.tail(252).max())
        # rel_return_6m_pct would be a better proxy if available later
        rs_line_new_high = bool(last_close_at_252_high)
    out["mv_close_at_252d_high"] = rs_line_new_high

    # ---- Bow-tie (10/21/50 cross / fresh Stage 2 emergence) ----
    bow_tie = False
    if len(close) >= 51:
        ema10 = close.ewm(span=10).mean()
        ema21 = close.ewm(span=21).mean()
        # Recent week: 10 crossed above 50 AND 21 crossed above 50 within last 5 bars
        for lag in range(0, 5):
            j = -1 - lag
            if j - 1 >= -len(close):
                cur10 = float(ema10.iloc[j]); prev10 = float(ema10.iloc[j - 1])
                cur21 = float(ema21.iloc[j]); prev21 = float(ema21.iloc[j - 1])
                cur50 = float(sma50.iloc[j]) if not np.isnan(sma50.iloc[j]) else None
                prev50 = float(sma50.iloc[j - 1]) if not np.isnan(sma50.iloc[j - 1]) else None
                if cur50 is None or prev50 is None:
                    continue
                cross10 = prev10 < prev50 and cur10 > cur50
                cross21 = prev21 < prev50 and cur21 > cur50
                if cross10 and cross21:
                    bow_tie = True
                    break
    out["mv_bow_tie"] = bow_tie
    if bow_tie:
        score += 3  # fresh Stage 2 emergence

    # ---- VCP-with-volume (proper VCP requires volume drying in each contraction) ----
    vcp_with_vol = False
    if weekly is not None and len(weekly) >= 20 and len(contractions) >= 2:
        w_vol = pd.to_numeric(weekly["Volume"], errors="coerce")
        if len(w_vol.dropna()) >= 12:
            # Check if avg vol in last 4 weeks < avg vol in prior 4 weeks
            recent4_vol = float(w_vol.tail(4).mean())
            prior4_vol = float(w_vol.tail(8).head(4).mean())
            if prior4_vol > 0:
                vcp_with_vol = bool(vcp_count >= 2 and recent4_vol < prior4_vol * 0.9)
    out["mv_vcp_with_volume"] = vcp_with_vol
    if vcp_with_vol:
        score += 3  # textbook VCP

    # ---- High Tight Flag (1-3 month 100%+ gain followed by 10-25% pullback) ----
    htf = False
    if len(close) >= 60:
        # Find the highest high in last 60 bars and the low after it
        last60_high = float(high.tail(60).max())
        idx_high = high.tail(60).idxmax()
        post_high = close.loc[idx_high:].tail(40)
        if len(post_high) >= 5:
            post_low = float(post_high.min())
            # Was the 60-day high preceded by a strong rally (>=80% in 60 bars before)?
            try:
                pos_of_high = list(close.index).index(idx_high)
                pre_window = close.iloc[max(0, pos_of_high - 60):pos_of_high]
                if len(pre_window) >= 30 and pre_window.iloc[0] > 0:
                    pre_rally = (last60_high - float(pre_window.iloc[0])) / float(pre_window.iloc[0])
                    pullback = (last60_high - post_low) / last60_high
                    htf = bool(pre_rally >= 0.8 and 0.10 <= pullback <= 0.30
                              and last >= post_low * 1.02)
            except Exception:
                pass
    out["mv_high_tight_flag"] = htf
    if htf:
        score += 4  # rare and powerful

    # ---- Right-side base (current bar is on the upward leg of the base) ----
    # Heuristic: current price > base midpoint AND 50dma rising
    right_side_base = False
    if v_sma50 is not None and len(close) >= 60:
        base_window = close.tail(60)
        midpoint = (float(base_window.max()) + float(base_window.min())) / 2
        sma50_rising = False
        if len(sma50.dropna()) >= 10:
            sma50_rising = bool(sma50.iloc[-1] > sma50.iloc[-10])
        right_side_base = bool(last > midpoint and sma50_rising)
    out["mv_right_side_base"] = right_side_base
    if right_side_base:
        score += 1

    # ---- Constructive base (depth limit + handle position) ----
    # Most recent base depth should be <30% from peak
    constructive_base = False
    if len(close) >= 60:
        recent60 = close.tail(60)
        depth_pct = float((recent60.max() - recent60.min()) / recent60.max())
        constructive_base = bool(depth_pct <= 0.30)
    out["mv_constructive_base"] = constructive_base
    if constructive_base:
        score += 1

    # ---- Wide-and-loose base (rejection - opposite of constructive) ----
    out["mv_wide_loose_base"] = bool(not constructive_base and len(close) >= 60)

    # ---- Acceleration of 200dma slope (second derivative) ----
    # Slope of slope: is the trend curve curving upward?
    ma_accel = None
    if len(sma200.dropna()) >= 60:
        s = sma200.dropna()
        slope_recent = (float(s.iloc[-1]) - float(s.iloc[-21])) / 21
        slope_prior = (float(s.iloc[-21]) - float(s.iloc[-42])) / 21
        ma_accel = float(slope_recent - slope_prior)
    out["mv_sma200_acceleration"] = ma_accel
    out["mv_sma200_accelerating_up"] = bool(ma_accel is not None and ma_accel > 0)

    # ---- "Buy zone" (within 5% above pivot, no more than 10%) ----
    in_buy_zone = False
    pivot_val = float(high.tail(40).max()) if len(high) >= 40 else None
    if pivot_val and pivot_val > 0:
        pct_above_pivot = (last - pivot_val) / pivot_val
        in_buy_zone = bool(0.0 <= pct_above_pivot <= 0.05)
        out["mv_pct_above_pivot"] = float(pct_above_pivot * 100)
    out["mv_in_buy_zone"] = in_buy_zone

    # Final composite
    out["mv_composite_score"] = float(score)
    out["mv_setup_clean"] = bool(stage2_count >= 8 and vcp_count >= 2
                                 and (dist is not None and dist <= 5.0))
    out["mv_setup_premium"] = bool(power_trend or
                                    (bow_tie and stage2_count >= 7) or
                                    (htf) or
                                    (vcp_with_vol and three_weeks_tight))
    return out


def compute_momentum(df, spy_close=None, df_monthly=None, spy_monthly_close=None,
                      intraday_frames=None):
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    # Minimum history: 60 daily bars (~3 months) is enough for daily signals
    # + 12+ weekly bars. Shorter-history tickers (recent IPOs, new listings)
    # are still included; monthly-dependent fields return None for them and
    # have_long_history flag is set to False.
    if len(close) < 60:
        return None
    has_short_history = len(close) < 130
    high = pd.to_numeric(df.loc[close.index, "High"], errors="coerce")
    low = pd.to_numeric(df.loc[close.index, "Low"], errors="coerce")
    volume = pd.to_numeric(df.loc[close.index, "Volume"], errors="coerce")
    last = float(close.iloc[-1])
    # Lookback SMAs - use min(N, available) so short-history tickers still work.
    # sma126 (6-month) will fall back to all-available for tickers <126 bars.
    sma25 = float(close.tail(min(25, len(close))).mean())
    sma66 = float(close.tail(min(66, len(close))).mean())
    sma126 = float(close.tail(min(126, len(close))).mean())
    if min(sma25, sma66, sma126) <= 0:
        return None

    # --- Daily metrics (kept for reference, used for momentum ranks) -------
    sma20 = float(close.tail(20).mean())
    sma50 = float(close.tail(50).mean())
    dist_sma20 = (last - sma20) / sma20 * 100
    dist_sma50 = (last - sma50) / sma50 * 100

    # Stacked moving averages: Price >= EMA10 >= SMA20 >= SMA50 >= SMA100 >= SMA200
    ema10 = float(close.ewm(span=10, adjust=False).mean().iloc[-1])
    sma100 = float(close.tail(100).mean()) if len(close) >= 100 else None
    sma200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    stacked_ma = bool(
        sma200 is not None
        and last >= ema10 >= sma20 >= sma50 >= sma100 >= sma200
    )

    # Position in 20-day range
    high_20d = float(high.tail(20).max())
    low_20d = float(low.tail(20).min())
    span_20d = high_20d - low_20d
    range_20d_pos_pct = (last - low_20d) / span_20d * 100 if span_20d > 0 else 50.0

    # 1-week return (5 trading days)
    week_return_pct = (
        float(close.iloc[-1] / close.iloc[-6] - 1) * 100
        if len(close) >= 6 else None
    )

    # ATR(14) as % of price - used for ATR_RS cross-sectional ranking later
    tr_vals = true_range(high.values[1:], low.values[1:], close.values[:-1])
    atr14 = float(np.mean(tr_vals[-14:])) if len(tr_vals) >= 14 else None
    atr14_pct = (atr14 / last * 100) if atr14 else None

    # --- ADV (Average Daily $-Volume) liquidity leg --------------------------
    # Per "the biggest winners trade at much higher dollar-volume than the
    # $20-50M floor." We compute absolute $-ADV at 20d/60d, the SLOPE of
    # ADV over the last 20 bars (is liquidity ramping?), and acceleration
    # (is the ramp itself accelerating?). Used downstream to filter for
    # "high conviction AND tradeable" subsets, not as a hard exclusion.
    dollar_vol = (close * volume).replace([np.inf, -np.inf], np.nan).dropna()
    if len(dollar_vol) >= 20:
        adv_20d = float(dollar_vol.tail(20).mean())
        adv_60d = float(dollar_vol.tail(min(60, len(dollar_vol))).mean())
        # Rolling 20d mean as a series, then linear-fit its last 20 obs
        rolling_adv = dollar_vol.rolling(20).mean().dropna()
        adv_slope_pct_wk = None
        adv_accel = None
        if len(rolling_adv) >= 20:
            recent = rolling_adv.tail(20).values
            x = np.arange(len(recent))
            try:
                slope, _ = np.polyfit(x, recent, 1)
                # %/wk relative to current ADV
                adv_slope_pct_wk = float((slope * 5) / recent[-1] * 100) if recent[-1] else None
            except Exception:
                adv_slope_pct_wk = None
            if len(rolling_adv) >= 40:
                prior = rolling_adv.tail(40).head(20).values
                try:
                    prior_slope, _ = np.polyfit(np.arange(len(prior)), prior, 1)
                    if recent[-1]:
                        prior_slope_pct = (prior_slope * 5) / recent[-1] * 100
                        adv_accel = float(adv_slope_pct_wk - prior_slope_pct) \
                            if adv_slope_pct_wk is not None else None
                except Exception:
                    adv_accel = None
        log_adv_20d = float(np.log10(adv_20d)) if adv_20d > 0 else None
        # ADV vs longer-term average - is recent liquidity above or below trend?
        adv_20_over_60 = float(adv_20d / adv_60d) if adv_60d > 0 else None
        # ADV in raw $ as a tier ($M)
        adv_20d_millions = float(adv_20d / 1_000_000)
    else:
        adv_20d = adv_60d = adv_slope_pct_wk = adv_accel = None
        log_adv_20d = adv_20_over_60 = adv_20d_millions = None

    # Volatility asymmetry (Pine Script port - daily bars)
    asym = compute_volatility_asymmetry(df) or {}

    # Squeeze & Release on daily bars
    sq_d = compute_squeeze_release(df) or {}

    # Harmonic patterns on daily bars (5-bar ZigZag, 4% min swing)
    h_d = compute_harmonics_for_tf(df, lookback=5, min_swing_pct=4.0,
                                    recent_d_max_bars=15, close_near_d_pct=8.0) or {}

    # --- Weekly metrics (the proper Q base/extension lens) -----------------
    df_ohlcv = pd.DataFrame({
        "Open": pd.to_numeric(df["Open"], errors="coerce") if "Open" in df.columns else close,
        "High": high, "Low": low, "Close": close, "Volume": volume,
    }).dropna()
    weekly = df_ohlcv.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()
    # Need at least 12 weekly bars (~3 months) for box/momentum signals.
    # Shorter still excluded - not enough for TD weekly setups or VCP.
    if len(weekly) < 12:
        return None
    has_short_weekly = len(weekly) < 30

    wclose = weekly["Close"]
    whigh = weekly["High"]
    wlow = weekly["Low"]
    wvol = weekly["Volume"]

    wma10 = float(wclose.tail(10).mean())
    wma30 = float(wclose.tail(30).mean())
    wma40 = float(wclose.tail(40).mean()) if len(wclose) >= 40 else wma30
    dist_wma10 = (last - wma10) / wma10 * 100
    dist_wma30 = (last - wma30) / wma30 * 100
    wma_trend_up = (wma10 > wma30) and (wma30 >= wma40)  # rising structure

    # Weekly stacked MA: Close >= WMA10(EMA) >= SMA20 >= SMA30 (on weekly close)
    wema10 = float(wclose.ewm(span=10, adjust=False).mean().iloc[-1])
    wsma20 = float(wclose.tail(20).mean())
    weekly_stacked_ma = bool(last >= wema10 >= wsma20 >= wma30)

    # Weekly position in last-20-week range
    if len(whigh) >= 20:
        high_20w = float(whigh.tail(20).max())
        low_20w = float(wlow.tail(20).min())
        span_20w = high_20w - low_20w
        weekly_range_pos_pct = (last - low_20w) / span_20w * 100 if span_20w > 0 else 50.0
    else:
        weekly_range_pos_pct = None

    # Weekly asymmetry (run on weekly bars)
    weekly_asym_dict = compute_volatility_asymmetry(weekly, period=14, smooth=7, slow=14, lookback=5) or {}

    # Squeeze & Release on weekly bars
    sq_w = compute_squeeze_release(weekly) or {}

    # TD Sequential on weekly bars (per Pine spec)
    td_w = compute_td_sequential(weekly) or {}
    td_w_nets = td_nets(td_w)

    # Harmonic patterns on weekly bars (3-bar ZigZag, 7% min swing)
    h_w = compute_harmonics_for_tf(weekly, lookback=3, min_swing_pct=7.0,
                                    recent_d_max_bars=8, close_near_d_pct=12.0) or {}

    # Squeeze & Release on monthly bars (use direct monthly download if available)
    monthly_bars_for_td = None
    if df_monthly is not None and len(df_monthly) >= 60:
        sq_m = compute_squeeze_release(df_monthly) or {}
        # Monthly: 2-bar pivots, 10% min swing
        h_m = compute_harmonics_for_tf(df_monthly, lookback=2, min_swing_pct=10.0,
                                        recent_d_max_bars=5, close_near_d_pct=18.0) or {}
        monthly_bars_for_td = df_monthly
    else:
        # resample from daily to monthly
        monthly_from_daily = df_ohlcv.resample("ME").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna()
        sq_m = compute_squeeze_release(monthly_from_daily, period=6, smoothing=4, ma_length=6) or {}
        h_m = compute_harmonics_for_tf(monthly_from_daily, lookback=2, min_swing_pct=10.0,
                                        recent_d_max_bars=5, close_near_d_pct=18.0) or {}
        monthly_bars_for_td = monthly_from_daily

    # TD Sequential on monthly bars
    td_m = compute_td_sequential(monthly_bars_for_td) or {}
    td_m_nets = td_nets(td_m)

    # TD Sequential on RELATIVE price (ticker / SPY) - weekly + monthly
    td_w_rel_nets = {"net_setup": 0.0, "net_cd": 0.0, "net_perfect": 0,
                     "net_stealth": 0, "net_triple": 0}
    td_m_rel_nets = dict(td_w_rel_nets)
    if spy_close is not None:
        try:
            spy_aligned = spy_close.reindex(close.index, method="ffill")
            rel_high_d = high / spy_aligned
            rel_low_d = low / spy_aligned
            rel_close_d = close / spy_aligned
            rel_ohlc = pd.DataFrame({"High": rel_high_d, "Low": rel_low_d,
                                      "Close": rel_close_d}).dropna()
            rel_w = rel_ohlc.resample("W-FRI").agg({
                "High": "max", "Low": "min", "Close": "last"}).dropna()
            if len(rel_w) >= 30:
                td_w_rel = compute_td_sequential(rel_w) or {}
                td_w_rel_nets = td_nets(td_w_rel)
            rel_m = rel_ohlc.resample("ME").agg({
                "High": "max", "Low": "min", "Close": "last"}).dropna()
            if len(rel_m) >= 30:
                td_m_rel = compute_td_sequential(rel_m) or {}
                td_m_rel_nets = td_nets(td_m_rel)
        except Exception:
            pass

    # Monthly asymmetry on direct monthly bars (or resampled)
    monthly_asym_dict = {}
    if df_monthly is not None and len(df_monthly) >= 60:
        monthly_asym_dict = compute_volatility_asymmetry(df_monthly) or {}

    # TD Sequential on intraday timeframes (1m, 5m, 15m, 1h, 4h-from-1h-resample)
    # Each TF returns a dict of 5 net signals; weighted into td_mtf later.
    intraday_td_nets = {}  # {tf_key: nets_dict}
    if intraday_frames:
        for tf_key, frame in intraday_frames.items():
            if frame is None or len(frame) < 30:
                continue
            td = compute_td_sequential(frame)
            if td:
                intraday_td_nets[tf_key] = td_nets(td)
        # Derive 4h from 1h by resample
        if "1h" in intraday_frames and intraday_frames["1h"] is not None:
            h_frame = intraday_frames["1h"]
            if len(h_frame) >= 120:
                try:
                    h4 = h_frame.resample("4h").agg({
                        "Open": "first", "High": "max", "Low": "min",
                        "Close": "last", "Volume": "sum",
                    }).dropna()
                    if len(h4) >= 30:
                        td4h = compute_td_sequential(h4)
                        if td4h:
                            intraday_td_nets["4h"] = td_nets(td4h)
                except Exception:
                    pass

    # Weekly-bar range tightness over last N weeks
    range_4w_w = float((whigh.tail(4).max() - wlow.tail(4).min()) / wclose.tail(4).mean() * 100)
    range_8w_w = float((whigh.tail(8).max() - wlow.tail(8).min()) / wclose.tail(8).mean() * 100)
    range_12w_w = float((whigh.tail(12).max() - wlow.tail(12).min()) / wclose.tail(12).mean() * 100)

    # Pullback from weekly highs
    high_4w_w = float(whigh.tail(4).max())
    high_8w_w = float(whigh.tail(8).max())
    high_26w_w = float(whigh.tail(26).max()) if len(whigh) >= 26 else float(whigh.max())
    pullback_4w_w = (last - high_4w_w) / high_4w_w * 100
    pullback_8w_w = (last - high_8w_w) / high_8w_w * 100

    # Weeks since the last weekly close registered an 8-week high.
    # If the high is the current bar (idxmax == last index), this is 0.
    idx_of_high = whigh.tail(8).idxmax()
    weeks_since_8w_high = int((whigh.index[-1] - idx_of_high).days // 7)

    # Volume drying: last 4w avg vs prior 13w avg (non-overlapping)
    vol_4w = float(wvol.tail(4).mean()) if wvol.tail(4).mean() > 0 else 0
    vol_prior_13w = float(wvol.iloc[-17:-4].mean()) if len(wvol) >= 17 and wvol.iloc[-17:-4].mean() > 0 else 0
    vol_drying_ratio = vol_4w / vol_prior_13w if vol_prior_13w > 0 else None

    # Distance from 40-week MA (long-term anchor, Roque's primary weekly trend)
    dist_wma40 = (last - wma40) / wma40 * 100 if wma40 else None

    # --- Monthly metrics (the long-term Roque "BIG BASE" lens) ----------
    monthly = df_ohlcv.resample("ME").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()
    m_close = monthly["Close"]
    m_high = monthly["High"]
    m_low = monthly["Low"]
    if len(m_close) >= 12:
        mma6 = float(m_close.tail(6).mean())
        mma12 = float(m_close.tail(12).mean())
        dist_mma6 = (last - mma6) / mma6 * 100
        dist_mma12 = (last - mma12) / mma12 * 100
        m_uptrend = mma6 > mma12
        # Monthly base: high minus low over last 6 months as %
        m_range_6m_pct = float((m_high.tail(6).max() - m_low.tail(6).min()) / m_close.tail(6).mean() * 100)
        # Months since a new 6-month high
        try:
            months_since_6m_high = int((m_close.index[-1] - m_high.tail(6).idxmax()).days // 30)
        except Exception:
            months_since_6m_high = None
    else:
        dist_mma6 = dist_mma12 = m_range_6m_pct = None
        m_uptrend = False
        months_since_6m_high = None

    # --- Darvas box on weekly bars (longest current consolidation) ------
    box = detect_darvas_box(weekly, min_box_weeks=4)
    if box is None:
        box = {}

    # Days since 52-week high (calendar days), kept for reference
    try:
        days_since_52w_high = int((close.index[-1] - high.tail(252).idxmax()).days)
    except Exception:
        days_since_52w_high = None

    # --- AQR-style time-series trend score --------------------------------
    # Vol-normalised excess return at 1m/3m/6m/12m horizons, tanh-clipped
    # and summed. Range roughly [-4, +4]. Captures TS-MOM the way AQR's
    # "A Century of Evidence on Trend-Following" defines it but without
    # the risk-free subtraction (small effect on daily lookbacks).
    daily_returns = close.pct_change().dropna()
    aqr_subscores = {}
    for label, n in [("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)]:
        if len(close) < n + 2:
            aqr_subscores[label] = None
            continue
        ret = float(close.iloc[-1] / close.iloc[-n - 1] - 1.0)
        window_returns = daily_returns.tail(n)
        sigma = float(window_returns.std() * np.sqrt(n))
        if not sigma or np.isnan(sigma) or sigma <= 0:
            aqr_subscores[label] = None
            continue
        # Sharpe-like t-stat scaled by 2 then tanh-bounded to [-1, 1]
        aqr_subscores[label] = float(np.tanh((ret / sigma) / 2.0))
    aqr_score = sum(v for v in aqr_subscores.values() if v is not None) \
        if any(v is not None for v in aqr_subscores.values()) else None

    # Weekly MACD on absolute close
    macd_w, signal_w, hist_w = macd(wclose)
    macd_above = bool(macd_w.iloc[-1] > signal_w.iloc[-1])
    macd_hist_rising = bool(hist_w.iloc[-1] > hist_w.iloc[-2]) if len(hist_w) >= 2 else False

    # 200-day MA slope (Roque's "demand line")
    dma200_slope, dist_dma200 = dma200_slope_pct(close)

    # --- MA-respect leg (50d, 200d, 10w) ---
    ma_signals = {}
    try:
        sma50_series = close.rolling(50).mean()
        sma200_series = close.rolling(200).mean()
        # Daily-aligned ATR series for vol-asym-near-MA
        tr_series = pd.Series(
            np.r_[np.nan, true_range(high.values[1:], low.values[1:], close.values[:-1])],
            index=close.index,
        )
        atr14_series = tr_series.rolling(14).mean()
        ma_signals.update(compute_ma_respect(close, sma50_series, atr14_series, "d50"))
        ma_signals.update(compute_ma_respect(close, sma200_series, atr14_series, "d200"))
        # Weekly 10wMA aligned back to daily via ffill
        wma10_series = wclose.rolling(10).mean()
        wma10_daily = wma10_series.reindex(close.index, method="ffill")
        ma_signals.update(compute_ma_respect(close, wma10_daily, atr14_series, "w10"))
    except Exception as e:
        pass

    # --- Minervini / VCP comprehensive leg ---
    minervini_signals = {}
    try:
        open_series = pd.to_numeric(df.loc[close.index, "Open"], errors="coerce") \
            if "Open" in df.columns else None
        minervini_signals = compute_minervini(
            close, high, low, volume, weekly=weekly, open_series=open_series)
    except Exception:
        pass

    has_monthly_data = len(m_close) >= 24  # 2y monthly bars for meaningful monthly signals
    out = {
        "last_close": last,
        "has_short_history": has_short_history,   # <130 daily bars (<6 months)
        "has_short_weekly": has_short_weekly,     # <30 weekly bars (<7 months)
        "has_monthly_data": has_monthly_data,     # >=24 monthly bars for TD/asym/squeeze on monthly
        "n_daily_bars": int(len(close)),
        "n_weekly_bars": int(len(weekly)),
        "n_monthly_bars": int(len(m_close)),
        # ADV / liquidity leg
        "adv_20d_dollar": adv_20d,
        "adv_60d_dollar": adv_60d,
        "adv_20d_millions": adv_20d_millions,
        "adv_20_over_60": adv_20_over_60,
        "adv_slope_pct_wk": adv_slope_pct_wk,
        "adv_accel": adv_accel,
        "log_adv_20d": log_adv_20d,
        "mom_1m": last / sma25,
        "mom_3m": last / sma66,
        "mom_6m": last / sma126,
        # AQR-style trend (vol-normalised TS-MOM, tanh-clipped, summed)
        "aqr_trend_1m": aqr_subscores.get("1m"),
        "aqr_trend_3m": aqr_subscores.get("3m"),
        "aqr_trend_6m": aqr_subscores.get("6m"),
        "aqr_trend_12m": aqr_subscores.get("12m"),
        "aqr_trend_score": aqr_score,
        "week_return_pct": week_return_pct,
        # MA stack
        "ema10": ema10, "sma20": sma20, "sma50": sma50,
        "sma100": sma100, "sma200": sma200,
        "stacked_ma": stacked_ma,
        # 20-day range position
        "range_20d_pos_pct": float(range_20d_pos_pct),
        # ATR
        "atr14_pct": atr14_pct,
        # Volatility asymmetry
        "asym_now": asym.get("asym_now"),
        "asym_ma": asym.get("asym_ma"),
        "asym_rising": asym.get("asym_rising", False),
        "asym_above_ma": asym.get("asym_above_ma", False),
        "asym_just_crossed_up": asym.get("asym_just_crossed_up", False),
        "asym_upper_signal": asym.get("asym_upper_signal", False),
        # weekly variants
        "weekly_stacked_ma": weekly_stacked_ma,
        "weekly_range_pos_pct": weekly_range_pos_pct,
        "asym_w_now": weekly_asym_dict.get("asym_now"),
        "asym_w_rising": weekly_asym_dict.get("asym_rising", False),
        "asym_w_above_ma": weekly_asym_dict.get("asym_above_ma", False),
        "asym_w_just_crossed_up": weekly_asym_dict.get("asym_just_crossed_up", False),
        # monthly asymmetry (price, not relative)
        "asym_m_now": monthly_asym_dict.get("asym_now"),
        "asym_m_rising": monthly_asym_dict.get("asym_rising", False),
        "asym_m_above_ma": monthly_asym_dict.get("asym_above_ma", False),
        "asym_m_just_crossed_up": monthly_asym_dict.get("asym_just_crossed_up", False),
        # Squeeze & Release - daily
        "sq_d_value": sq_d.get("sq_value"),
        "sq_d_ma": sq_d.get("sq_ma"),
        "sq_d_squeezing": sq_d.get("sq_squeezing", False),
        "sq_d_releasing": sq_d.get("sq_releasing", False),
        "sq_d_just_release": sq_d.get("sq_just_release", False),
        "sq_d_was_high_75": sq_d.get("sq_was_high_75", False),
        "sq_d_was_high_90": sq_d.get("sq_was_high_90", False),
        "sq_d_pct_of_max": sq_d.get("sq_pct_of_max"),
        # Squeeze & Release - weekly
        "sq_w_value": sq_w.get("sq_value"),
        "sq_w_ma": sq_w.get("sq_ma"),
        "sq_w_squeezing": sq_w.get("sq_squeezing", False),
        "sq_w_just_release": sq_w.get("sq_just_release", False),
        "sq_w_was_high_75": sq_w.get("sq_was_high_75", False),
        "sq_w_was_high_90": sq_w.get("sq_was_high_90", False),
        "sq_w_hyper": sq_w.get("sq_hyper", False),
        "sq_w_pct_of_max": sq_w.get("sq_pct_of_max"),
        # Squeeze & Release - monthly
        "sq_m_value": sq_m.get("sq_value"),
        "sq_m_squeezing": sq_m.get("sq_squeezing", False),
        "sq_m_just_release": sq_m.get("sq_just_release", False),
        "sq_m_was_high_75": sq_m.get("sq_was_high_75", False),
        # TD Sequential - weekly absolute
        "td_w_buy_setup": td_w.get("buy_setup", 0),
        "td_w_sell_setup": td_w.get("sell_setup", 0),
        "td_w_buy_cd": td_w.get("buy_cd", 0),
        "td_w_sell_cd": td_w.get("sell_cd", 0),
        "td_w_buy_perfect": td_w.get("buy_perfect", False),
        "td_w_sell_perfect": td_w.get("sell_perfect", False),
        "td_w_stealth_buy": td_w.get("stealth_buy", False),
        "td_w_stealth_sell": td_w.get("stealth_sell", False),
        "td_w_triple_buy": td_w.get("triple_buy", False),
        "td_w_triple_sell": td_w.get("triple_sell", False),
        "td_w_net_setup": td_w_nets["net_setup"],
        "td_w_net_cd": td_w_nets["net_cd"],
        "td_w_net_perfect": td_w_nets["net_perfect"],
        "td_w_net_stealth": td_w_nets["net_stealth"],
        "td_w_net_triple": td_w_nets["net_triple"],
        # TD Sequential - monthly absolute
        "td_m_buy_setup": td_m.get("buy_setup", 0),
        "td_m_sell_setup": td_m.get("sell_setup", 0),
        "td_m_buy_cd": td_m.get("buy_cd", 0),
        "td_m_sell_cd": td_m.get("sell_cd", 0),
        "td_m_buy_perfect": td_m.get("buy_perfect", False),
        "td_m_sell_perfect": td_m.get("sell_perfect", False),
        "td_m_stealth_buy": td_m.get("stealth_buy", False),
        "td_m_stealth_sell": td_m.get("stealth_sell", False),
        "td_m_triple_buy": td_m.get("triple_buy", False),
        "td_m_triple_sell": td_m.get("triple_sell", False),
        "td_m_net_setup": td_m_nets["net_setup"],
        "td_m_net_cd": td_m_nets["net_cd"],
        "td_m_net_perfect": td_m_nets["net_perfect"],
        "td_m_net_stealth": td_m_nets["net_stealth"],
        "td_m_net_triple": td_m_nets["net_triple"],
        # TD Sequential - weekly relative-to-SPY
        "td_w_rel_net_setup": td_w_rel_nets["net_setup"],
        "td_w_rel_net_cd": td_w_rel_nets["net_cd"],
        "td_w_rel_net_perfect": td_w_rel_nets["net_perfect"],
        "td_w_rel_net_stealth": td_w_rel_nets["net_stealth"],
        "td_w_rel_net_triple": td_w_rel_nets["net_triple"],
        # TD Sequential - monthly relative-to-SPY
        "td_m_rel_net_setup": td_m_rel_nets["net_setup"],
        "td_m_rel_net_cd": td_m_rel_nets["net_cd"],
        "td_m_rel_net_perfect": td_m_rel_nets["net_perfect"],
        "td_m_rel_net_stealth": td_m_rel_nets["net_stealth"],
        "td_m_rel_net_triple": td_m_rel_nets["net_triple"],
        # Intraday TD nets (1m, 5m, 15m, 1h, 4h) — only present when intraday
        # data was downloaded; otherwise all zero (won't affect MTF average).
        "td_1m_net_setup":   intraday_td_nets.get("1m", {}).get("net_setup", 0.0),
        "td_1m_net_cd":      intraday_td_nets.get("1m", {}).get("net_cd", 0.0),
        "td_1m_net_perfect": intraday_td_nets.get("1m", {}).get("net_perfect", 0),
        "td_1m_net_stealth": intraday_td_nets.get("1m", {}).get("net_stealth", 0),
        "td_1m_net_triple":  intraday_td_nets.get("1m", {}).get("net_triple", 0),
        "td_5m_net_setup":   intraday_td_nets.get("5m", {}).get("net_setup", 0.0),
        "td_5m_net_cd":      intraday_td_nets.get("5m", {}).get("net_cd", 0.0),
        "td_5m_net_perfect": intraday_td_nets.get("5m", {}).get("net_perfect", 0),
        "td_5m_net_stealth": intraday_td_nets.get("5m", {}).get("net_stealth", 0),
        "td_5m_net_triple":  intraday_td_nets.get("5m", {}).get("net_triple", 0),
        "td_15m_net_setup":   intraday_td_nets.get("15m", {}).get("net_setup", 0.0),
        "td_15m_net_cd":      intraday_td_nets.get("15m", {}).get("net_cd", 0.0),
        "td_15m_net_perfect": intraday_td_nets.get("15m", {}).get("net_perfect", 0),
        "td_15m_net_stealth": intraday_td_nets.get("15m", {}).get("net_stealth", 0),
        "td_15m_net_triple":  intraday_td_nets.get("15m", {}).get("net_triple", 0),
        "td_1h_net_setup":   intraday_td_nets.get("1h", {}).get("net_setup", 0.0),
        "td_1h_net_cd":      intraday_td_nets.get("1h", {}).get("net_cd", 0.0),
        "td_1h_net_perfect": intraday_td_nets.get("1h", {}).get("net_perfect", 0),
        "td_1h_net_stealth": intraday_td_nets.get("1h", {}).get("net_stealth", 0),
        "td_1h_net_triple":  intraday_td_nets.get("1h", {}).get("net_triple", 0),
        "td_4h_net_setup":   intraday_td_nets.get("4h", {}).get("net_setup", 0.0),
        "td_4h_net_cd":      intraday_td_nets.get("4h", {}).get("net_cd", 0.0),
        "td_4h_net_perfect": intraday_td_nets.get("4h", {}).get("net_perfect", 0),
        "td_4h_net_stealth": intraday_td_nets.get("4h", {}).get("net_stealth", 0),
        "td_4h_net_triple":  intraday_td_nets.get("4h", {}).get("net_triple", 0),
        # Flag presence of intraday data for each TF (used to weight MTF avg)
        "td_1m_present":  "1m" in intraday_td_nets,
        "td_5m_present":  "5m" in intraday_td_nets,
        "td_15m_present": "15m" in intraday_td_nets,
        "td_1h_present":  "1h" in intraday_td_nets,
        "td_4h_present":  "4h" in intraday_td_nets,
        # Harmonic patterns
        "h_d_pattern": h_d.get("pattern"),
        "h_d_direction": h_d.get("direction"),
        "h_d_quality": h_d.get("quality"),
        "h_d_dist_from_d_pct": h_d.get("dist_from_d_pct"),
        "h_d_bars_since_d": h_d.get("bars_since_d"),
        "h_w_pattern": h_w.get("pattern"),
        "h_w_direction": h_w.get("direction"),
        "h_w_quality": h_w.get("quality"),
        "h_w_dist_from_d_pct": h_w.get("dist_from_d_pct"),
        "h_w_bars_since_d": h_w.get("bars_since_d"),
        "h_m_pattern": h_m.get("pattern"),
        "h_m_direction": h_m.get("direction"),
        "h_m_quality": h_m.get("quality"),
        "h_m_dist_from_d_pct": h_m.get("dist_from_d_pct"),
        "h_m_bars_since_d": h_m.get("bars_since_d"),
        # daily references
        "dist_sma20_pct": dist_sma20,
        "dist_sma50_pct": dist_sma50,
        "dist_dma200_pct": dist_dma200,
        "dma200_slope_pct": dma200_slope,
        "days_since_52w_high": days_since_52w_high,
        # weekly Q / Roque metrics
        "dist_wma10_pct": float(dist_wma10),
        "dist_wma30_pct": float(dist_wma30),
        "dist_wma40_pct": float(dist_wma40) if dist_wma40 is not None else None,
        "wma_trend_up": bool(wma_trend_up),
        "range_4w_w_pct": range_4w_w,
        "range_8w_w_pct": range_8w_w,
        "range_12w_w_pct": range_12w_w,
        "pullback_4w_w_pct": float(pullback_4w_w),
        "pullback_8w_w_pct": float(pullback_8w_w),
        "weeks_since_8w_high": weeks_since_8w_high,
        "vol_drying_ratio": float(vol_drying_ratio) if vol_drying_ratio is not None else None,
        # absolute weekly MACD
        "macd_w": float(macd_w.iloc[-1]),
        "macd_signal_w": float(signal_w.iloc[-1]),
        "macd_hist_w": float(hist_w.iloc[-1]),
        "macd_above_signal": macd_above,
        "macd_hist_rising": macd_hist_rising,
        # monthly
        "dist_mma6_pct": dist_mma6,
        "dist_mma12_pct": dist_mma12,
        "monthly_uptrend": bool(m_uptrend),
        "month_range_6m_pct": m_range_6m_pct,
        "months_since_6m_high": months_since_6m_high,
        # Darvas box on weekly
        "box_top": box.get("box_top"),
        "box_bottom": box.get("box_bottom"),
        "box_height_pct": box.get("box_height_pct"),
        "box_length_weeks": box.get("box_length_weeks"),
        "pos_in_box_pct": box.get("pos_in_box_pct"),
        "dist_from_box_top_pct": box.get("dist_from_box_top_pct"),
        "inner_height_pct": box.get("inner_height_pct"),
        "inner_weeks": box.get("inner_weeks"),
    }

    # --- Relative-to-SPY metrics ----------------------------------------
    if spy_close is not None:
        aligned = pd.concat([close, spy_close], axis=1, join="inner").dropna()
        if len(aligned) >= 140:
            aligned.columns = ["t", "s"]
            rel = aligned["t"] / aligned["s"]
            # Resample to weekly
            rel_w = rel.resample("W-FRI").last().dropna()
            if len(rel_w) >= 30:
                rel_last = float(rel.iloc[-1])
                rel_wma10 = float(rel_w.tail(10).mean())
                rel_wma30 = float(rel_w.tail(30).mean())
                rel_dist_wma10 = (rel_last - rel_wma10) / rel_wma10 * 100
                rel_dist_wma30 = (rel_last - rel_wma30) / rel_wma30 * 100
                rel_trend_up = rel_wma10 > rel_wma30
                rel_macd, rel_sig, rel_hist = macd(rel_w)
                rel_macd_above = bool(rel_macd.iloc[-1] > rel_sig.iloc[-1])
                rel_hist_rising = bool(rel_hist.iloc[-1] > rel_hist.iloc[-2]) if len(rel_hist) >= 2 else False
                # Relative momentum: rel return over 3m and 6m (in days, using daily aligned series)
                try:
                    rel_ret_3m = (rel.iloc[-1] / rel.iloc[-66] - 1) * 100
                    rel_ret_6m = (rel.iloc[-1] / rel.iloc[-126] - 1) * 100
                except Exception:
                    rel_ret_3m = rel_ret_6m = None
                # Volatility asymmetry on relative price (the "RS-strength" signal)
                rel_asym_d = compute_close_only_asymmetry(rel) or {}
                rel_asym_w = compute_close_only_asymmetry(rel_w) or {}
                # Monthly: prefer direct monthly bars (yfinance interval='1mo')
                # over resample-from-daily, since direct gives ~120 bars vs 24.
                if df_monthly is not None and spy_monthly_close is not None and len(df_monthly) >= 30:
                    t_m_close = pd.to_numeric(df_monthly["Close"], errors="coerce").dropna()
                    aligned_m = pd.concat([t_m_close, spy_monthly_close], axis=1, join="inner").dropna()
                    if len(aligned_m) >= 30:
                        aligned_m.columns = ["t", "s"]
                        rel_m_direct = aligned_m["t"] / aligned_m["s"]
                        rel_asym_m = compute_close_only_asymmetry(rel_m_direct) or {}
                    else:
                        rel_asym_m = {}
                else:
                    # Fallback: resample daily to monthly (~24 bars, smaller params)
                    rel_m_resampled = rel.resample("ME").last().dropna()
                    rel_asym_m = compute_close_only_asymmetry(
                        rel_m_resampled, period=5, smooth=3, slow=4
                    ) or {}
                out.update({
                    "rel_dist_wma10_pct": float(rel_dist_wma10),
                    "rel_dist_wma30_pct": float(rel_dist_wma30),
                    "rel_trend_up": bool(rel_trend_up),
                    "rel_macd_above_signal": rel_macd_above,
                    "rel_macd_hist_rising": rel_hist_rising,
                    "rel_return_3m_pct": float(rel_ret_3m) if rel_ret_3m is not None else None,
                    "rel_return_6m_pct": float(rel_ret_6m) if rel_ret_6m is not None else None,
                    # daily asymmetry on rel price
                    "rel_asym_now": rel_asym_d.get("asym_now"),
                    "rel_asym_rising": rel_asym_d.get("asym_rising", False),
                    "rel_asym_above_ma": rel_asym_d.get("asym_above_ma", False),
                    "rel_asym_just_crossed_up": rel_asym_d.get("asym_just_crossed_up", False),
                    # weekly asymmetry on rel price
                    "rel_asym_w_now": rel_asym_w.get("asym_now"),
                    "rel_asym_w_rising": rel_asym_w.get("asym_rising", False),
                    "rel_asym_w_above_ma": rel_asym_w.get("asym_above_ma", False),
                    "rel_asym_w_just_crossed_up": rel_asym_w.get("asym_just_crossed_up", False),
                    # monthly asymmetry on rel price (may be None for short history)
                    "rel_asym_m_now": rel_asym_m.get("asym_now"),
                    "rel_asym_m_rising": rel_asym_m.get("asym_rising", False),
                    "rel_asym_m_above_ma": rel_asym_m.get("asym_above_ma", False),
                    "rel_asym_m_just_crossed_up": rel_asym_m.get("asym_just_crossed_up", False),
                })

    out.update(ma_signals)
    out.update(minervini_signals)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True,
                        help="Universe key (e.g. us-smid, us-midlarge, us-micro, eu-smid).")
    parser.add_argument("--sector", default=None,
                        help="Comma-separated sector(s) (e.g. 'Information Technology,Health Care').")
    parser.add_argument("--industry-group", default=None, help="Comma-separated industry group(s).")
    parser.add_argument("--industry", default=None, help="Comma-separated industry/ies.")
    parser.add_argument("--theme", default=None,
                        help="Comma-separated keyword(s) for text-search across name+summary.")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Drop tickers with last close below this (liquidity floor).")
    parser.add_argument("--intraday", action="store_true",
                        help="Also pull intraday bars (1m/5m/15m/1h) and compute TD on each. "
                             "Caches per (universe,interval) pickle; resumable. Slow.")
    parser.add_argument("--intraday-tfs", default="5m,15m,1h",
                        help="Comma list of intraday TFs to download when --intraday is on. "
                             "Choices: 1m,5m,15m,1h. 4h derived by resampling 1h.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print(f"Loading {args.universe} universe...")
    universe = get_universe(args.universe)
    before_n = len(universe)
    universe = apply_universe_filters(
        universe, sector=args.sector, industry_group=args.industry_group,
        industry=args.industry, theme=args.theme,
    )
    if any([args.sector, args.industry_group, args.industry, args.theme]):
        print(f"  filters narrowed {before_n} -> {len(universe)} tickers")
    tickers = [t for t in universe.index.tolist() if isinstance(t, str) and t]
    print(f"  {len(tickers)} tickers")

    spy_close = load_or_download_spy(years=max(args.years + 1, 3))
    spy_monthly_close = load_or_download_spy_monthly(years=10)

    print(f"Downloading daily bars ({args.years}y)...")
    frames = download_daily(args.universe, tickers, years=args.years)
    print(f"  {len(frames)} tickers with usable daily data")

    print("Downloading monthly bars (10y, interval='1mo')...")
    monthly_frames = download_monthly(args.universe, tickers, years=10)
    print(f"  {len(monthly_frames)} tickers with usable monthly data")

    # Intraday TF downloads (opt-in via --intraday). Each TF is a separate
    # cached pickle keyed by (universe, interval, period). Resumable; never
    # wipes existing data.
    intraday_data_by_tf = {}  # {ticker: {tf_key: dataframe}}
    if args.intraday:
        wanted_tfs = {tf.strip() for tf in args.intraday_tfs.split(",") if tf.strip()}
        for tf_key, interval, period, _weight in INTRADAY_SPEC:
            if tf_key not in wanted_tfs:
                continue
            print(f"Downloading intraday {interval} (period={period})...")
            tf_frames = download_intraday(args.universe, tickers, interval, period)
            for t, frame in tf_frames.items():
                intraday_data_by_tf.setdefault(t, {})[tf_key] = frame
            print(f"  {len(tf_frames)} tickers with usable {interval} data")

    junk_substrings = ("Acquisition Corp", "Acquisition Corporation", "Preferred",
                       "Senior Notes", "Note due", "Notes due",
                       "Warrants", "Rights ", "Trust Units", "Royalty Trust",
                       " Fund", " Fund Inc", "Income Fund", "Bond Fund",
                       "Series A ", "Series B ", "Series C ", "Series D ",
                       "Depositary Shares", "Ordinary Shares", "Class A ordinary")
    def is_junk_ticker(t, nm):
        # preferreds / units / warrants by ticker pattern
        if "-P" in t or "-W" in t or "-U" in t or t.endswith(("U", ".U")):
            return True
        # Guard against non-string names (e.g. NaN from Wikipedia scrape)
        if isinstance(nm, str) and nm and any(s.lower() in nm.lower() for s in junk_substrings):
            return True
        return False

    rows = []
    junk_dropped = 0
    for t, f in frames.items():
        m = compute_momentum(f, spy_close=spy_close,
                              df_monthly=monthly_frames.get(t),
                              spy_monthly_close=spy_monthly_close,
                              intraday_frames=intraday_data_by_tf.get(t))
        if m is None:
            continue
        if m["last_close"] < args.min_price:
            continue
        m["Ticker"] = t
        name_col = "name" if "name" in universe.columns else "shortName"
        nm = universe.loc[t, name_col] if t in universe.index else None
        if is_junk_ticker(t, nm):
            junk_dropped += 1
            continue
        m["name"] = nm
        m["sector"] = universe.loc[t, "sector"] if t in universe.index and "sector" in universe.columns else None
        rows.append(m)
    print(f"  junk filter dropped {junk_dropped} preferreds / SPACs / CEFs / notes")

    if not rows:
        print("No momentum metrics computed.")
        return

    df = pd.DataFrame(rows).set_index("Ticker")
    df["rank_1m"] = df["mom_1m"].rank(ascending=False).astype(int)
    df["rank_3m"] = df["mom_3m"].rank(ascending=False).astype(int)
    df["rank_6m"] = df["mom_6m"].rank(ascending=False).astype(int)
    df["rank_avg"] = (df["rank_1m"] + df["rank_3m"] + df["rank_6m"]) / 3
    df["rank_max"] = df[["rank_1m", "rank_3m", "rank_6m"]].max(axis=1)

    # --- IBD-style cross-sectional RS rank (0..99 percentile) ----------
    df["rs_rank_1w"] = (df["week_return_pct"].rank(pct=True) * 99).round(1)
    df["rs_rank_1m"] = (df["mom_1m"].rank(pct=True) * 99).round(1)
    df["rs_rank_3m"] = (df["mom_3m"].rank(pct=True) * 99).round(1)
    df["rs_rank_6m"] = (df["mom_6m"].rank(pct=True) * 99).round(1)
    df["rs_rank_max"] = df[["rs_rank_1w", "rs_rank_1m", "rs_rank_3m", "rs_rank_6m"]].max(axis=1)

    # ATR RS rank (higher = more volatile / more daily range)
    df["atr_rs"] = (df["atr14_pct"].rank(pct=True) * 99).round(1)

    # Q method criteria booleans (lightened: decent RS instead of strict 97).
    # Use volatility asymmetry on relative-to-SPY price as the RS-strength
    # signal: when rel-asym rises near 50 or crosses above its MA, the stock
    # is taking on relative strength versus the benchmark.
    df["rs_decent"] = df["rs_rank_max"] >= 70  # was 97, now decent threshold
    df["rs_strong"] = df["rs_rank_max"] >= 85
    df["atr_rs_above_50"] = df["atr_rs"] >= 50
    df["price_range_top_half"] = df["range_20d_pos_pct"] >= 50
    df["weekly_range_top_half"] = df["weekly_range_pos_pct"].fillna(0) >= 50
    df["stacked_ma_any"] = df["stacked_ma"].fillna(False) | df["weekly_stacked_ma"].fillna(False)

    # RS-strength signal: rel-asym rising / crossed MA / above MA.
    # Weight: monthly > weekly > daily (weekly+monthly are what matters).
    df["rel_asym_d_signal"] = (
        df["rel_asym_rising"].fillna(False)
        | df["rel_asym_above_ma"].fillna(False)
        | df["rel_asym_just_crossed_up"].fillna(False)
    )
    df["rel_asym_w_signal"] = (
        df["rel_asym_w_rising"].fillna(False)
        | df["rel_asym_w_above_ma"].fillna(False)
        | df["rel_asym_w_just_crossed_up"].fillna(False)
    )
    df["rel_asym_m_signal"] = (
        df.get("rel_asym_m_rising", pd.Series(False, index=df.index)).fillna(False)
        | df.get("rel_asym_m_above_ma", pd.Series(False, index=df.index)).fillna(False)
        | df.get("rel_asym_m_just_crossed_up", pd.Series(False, index=df.index)).fillna(False)
    )
    # Headline rel_asym_signal = weekly OR monthly (weight: w/m matter much more).
    # Daily is bonus only. Monthly-not-available is fine (short history).
    df["rel_asym_signal"] = df["rel_asym_w_signal"] | df["rel_asym_m_signal"]
    # rel_asym_score 0..5 (monthly=3, weekly=2, daily=1, but bonus +1 if monthly+weekly stack)
    df["rel_asym_score"] = (
        df["rel_asym_d_signal"].astype(int) * 1
        + df["rel_asym_w_signal"].astype(int) * 2
        + df["rel_asym_m_signal"].astype(int) * 3
    )

    # Q METHOD PASS (lightened):
    #   - decent RS (rank_max >= 70)
    #   - rel-asym signal up on WEEKLY OR MONTHLY (daily alone insufficient)
    #   - stacked MAs (daily OR weekly)
    #   - ATR_RS >= 50 (above-average daily range)
    #   - price in top half of 20-day OR 20-week range
    df["q_method_pass"] = (
        df["rs_decent"]
        & df["rel_asym_signal"]   # weekly OR monthly rel asym up
        & df["stacked_ma_any"]
        & df["atr_rs_above_50"]
        & (df["price_range_top_half"] | df["weekly_range_top_half"])
    )
    # Higher-conviction variant: requires monthly rel asym confirmation
    df["q_method_pass_monthly_strong"] = (
        df["rs_decent"]
        & df["rel_asym_m_signal"]
        & df["stacked_ma_any"]
        & df["atr_rs_above_50"]
        & (df["price_range_top_half"] | df["weekly_range_top_half"])
    )

    # Weekly-only Q method: same but weekly-bar variants
    df["q_method_pass_weekly"] = (
        df["rs_decent"]
        & df["rel_asym_w_signal"]
        & df["weekly_stacked_ma"].fillna(False)
        & df["atr_rs_above_50"]
        & df["weekly_range_top_half"]
    )

    # ===== Harmonic patterns =====
    # Score per timeframe (presence + direction + quality). Monthly + weekly
    # weighted higher than daily per Candleboxlaw's multi-timeframe workflow.
    def _hscore(direction, quality, weight):
        if pd.isna(quality) or quality is None:
            return 0.0
        sign = 1 if direction == "bullish" else (-1 if direction == "bearish" else 0)
        return sign * float(quality) * weight

    df["h_d_score"] = df.apply(lambda r: _hscore(r.get("h_d_direction"),
                                                  r.get("h_d_quality"), 1.0), axis=1)
    df["h_w_score"] = df.apply(lambda r: _hscore(r.get("h_w_direction"),
                                                  r.get("h_w_quality"), 3.0), axis=1)
    df["h_m_score"] = df.apply(lambda r: _hscore(r.get("h_m_direction"),
                                                  r.get("h_m_quality"), 5.0), axis=1)
    df["harmonic_score"] = df["h_d_score"] + df["h_w_score"] + df["h_m_score"]

    # Consonance: how many timeframes agree on bullish (or bearish) direction
    def _consonance(row):
        dirs = [row.get(c) for c in ("h_d_direction", "h_w_direction", "h_m_direction")]
        bull = sum(1 for d in dirs if d == "bullish")
        bear = sum(1 for d in dirs if d == "bearish")
        # bull-dominant returns positive, bear-dominant negative
        if bull >= 2 and bear == 0:
            return bull
        if bear >= 2 and bull == 0:
            return -bear
        if bull >= 1 and bear == 0:
            return 0.5
        if bear >= 1 and bull == 0:
            return -0.5
        return 0
    df["harmonic_consonance"] = df.apply(_consonance, axis=1)

    # Tag flags
    df["harmonic_bullish_w_or_m"] = (
        (df["h_w_direction"] == "bullish") | (df["h_m_direction"] == "bullish")
    )
    df["harmonic_bullish_consonance"] = df["harmonic_consonance"] >= 2
    df["harmonic_bearish_consonance"] = df["harmonic_consonance"] <= -2

    # ===== TD Sequential MTF proportional composite (per Pine spec) =====
    # Each TF contributes equal weight from daily up (D=W=M=1.0).
    # Intraday TFs down-weighted (when present). The composite is the
    # weighted average of the 5 user-requested net signals across all TFs
    # for both absolute price AND relative-to-SPY.
    def _safe(c):
        return df[c].fillna(0) if c in df.columns else 0

    # Daily-and-up equal weight (1.0). Intraday down-weighted per spec.
    # Per Pine: setup max=9, cd max=13 already normalized to ±1 in td_nets().
    TF_WEIGHTS = {
        "1m":  0.10,
        "5m":  0.20,
        "15m": 0.40,
        "1h":  0.60,
        "4h":  0.80,
        "d":   1.00,
        "w":   1.00,
        "m":   1.00,
    }

    # Build column-name template per timeframe key
    def _col_for(tf, metric, relative=False):
        if tf in ("1m", "5m", "15m", "1h", "4h"):
            return f"td_{tf}_{metric}"
        # daily/weekly/monthly absolute
        if not relative:
            return f"td_{tf}_{metric}"
        # relative-to-SPY only exists for w/m
        return f"td_{tf}_rel_{metric}"

    intraday_tfs = ["1m", "5m", "15m", "1h", "4h"]
    abs_dwm_tfs = ["w", "m"]   # daily TD not currently computed; W+M absolute
    rel_dwm_tfs = ["w", "m"]   # W+M relative-to-SPY

    metrics = ["net_setup", "net_cd", "net_perfect", "net_stealth", "net_triple"]
    for metric_name in metrics:
        total_weight = 0.0
        weighted_sum = 0
        # Intraday TFs (only when data present)
        for tf in intraday_tfs:
            present_col = f"td_{tf}_present"
            col = f"td_{tf}_{metric_name}"
            if col in df.columns and present_col in df.columns:
                mask = df[present_col].fillna(False).astype(bool)
                w = TF_WEIGHTS[tf]
                weighted_sum = weighted_sum + _safe(col) * (mask.astype(float) * w)
                total_weight = total_weight + mask.astype(float) * w
        # Daily-and-up absolute
        for tf in abs_dwm_tfs:
            col = f"td_{tf}_{metric_name}"
            if col in df.columns:
                weighted_sum = weighted_sum + _safe(col) * TF_WEIGHTS[tf]
                total_weight += TF_WEIGHTS[tf]
        # Daily-and-up relative-to-SPY
        for tf in rel_dwm_tfs:
            col = f"td_{tf}_rel_{metric_name}"
            if col in df.columns:
                weighted_sum = weighted_sum + _safe(col) * TF_WEIGHTS[tf]
                total_weight += TF_WEIGHTS[tf]
        df[f"td_mtf_{metric_name}"] = weighted_sum / total_weight if (
            isinstance(total_weight, (int, float)) and total_weight > 0
        ) else (weighted_sum / total_weight.replace(0, 1))

    # Composite TD exhaustion = sum of 5 weighted net metrics
    # Each metric range ±1, so composite range ≈ ±5.
    df["td_mtf_composite"] = (
        df["td_mtf_net_setup"]
        + df["td_mtf_net_cd"]
        + df["td_mtf_net_perfect"]
        + df["td_mtf_net_stealth"]
        + df["td_mtf_net_triple"]
    )
    # Absolute asymmetry: how strong the signal is regardless of direction
    df["td_mtf_asymmetry"] = df["td_mtf_composite"].abs()
    # Keep legacy column name for save_mask compatibility
    df["td_exhaustion_score"] = df["td_mtf_composite"]

    # Bullish/bearish exhaustion tags
    df["td_bullish_exhaustion"] = df["td_mtf_composite"] >= 0.5
    df["td_bullish_exhaustion_strong"] = df["td_mtf_composite"] >= 1.0
    df["td_bearish_exhaustion"] = df["td_mtf_composite"] <= -0.5
    df["td_bearish_exhaustion_strong"] = df["td_mtf_composite"] <= -1.0

    # ===== BREAKOUT_SQUEEZE setup =====
    # Daily squeeze is HIGH and just RELEASING (vol about to expand)
    # Weekly squeeze is HIGH and still SQUEEZING (long-term coil intact)
    # Volatility asymmetry improving (rising), preferably near 50
    daily_release_from_high = (
        df["sq_d_just_release"].fillna(False)
        & df["sq_d_was_high_75"].fillna(False)
    )
    daily_release_from_high_strict = (
        df["sq_d_just_release"].fillna(False)
        & df["sq_d_was_high_90"].fillna(False)
    )
    weekly_still_squeezing_high = (
        df["sq_w_squeezing"].fillna(False)
        & df["sq_w_was_high_75"].fillna(False)
    )
    weekly_still_squeezing_high_strict = (
        df["sq_w_squeezing"].fillna(False)
        & df["sq_w_was_high_90"].fillna(False)
    )
    asym_improving_near_50 = (
        df["asym_now"].fillna(0).between(40, 60) & df["asym_rising"].fillna(False)
    ) | df["asym_just_crossed_up"].fillna(False) | df["asym_w_rising"].fillna(False) | df["asym_w_just_crossed_up"].fillna(False)

    df["breakout_squeeze"] = (
        daily_release_from_high
        & weekly_still_squeezing_high
        & asym_improving_near_50
    )
    # Strict variant: 90th percentile on both
    df["breakout_squeeze_strict"] = (
        daily_release_from_high_strict
        & weekly_still_squeezing_high_strict
        & asym_improving_near_50
    )
    # Looser: daily released recently (last 5 bars) and weekly squeezing
    df["breakout_squeeze_loose"] = (
        df["sq_d_releasing"].fillna(False)
        & (df["sq_d_was_high_75"].fillna(False) | df["sq_d_was_high_90"].fillna(False))
        & df["sq_w_squeezing"].fillna(False)
        & asym_improving_near_50
    )

    # Daily absolute-price volatility asymmetry bonus
    df["vol_asym_bonus"] = (
        (df["asym_now"].fillna(0).between(40, 60) & df["asym_rising"].fillna(False))
        | df["asym_just_crossed_up"].fillna(False)
        | df["asym_upper_signal"].fillna(False)
    )
    df["vol_asym_w_bonus"] = (
        (df["asym_w_now"].fillna(0).between(40, 60) & df["asym_w_rising"].fillna(False))
        | df["asym_w_just_crossed_up"].fillna(False)
    )

    top_1m = df.nlargest(args.top, "mom_1m")
    top_3m = df.nlargest(args.top, "mom_3m")
    top_6m = df.nlargest(args.top, "mom_6m")
    intersection = set(top_1m.index) & set(top_3m.index) & set(top_6m.index)
    union = set(top_1m.index) | set(top_3m.index) | set(top_6m.index)

    df["in_top_1m"] = df.index.isin(top_1m.index)
    df["in_top_3m"] = df.index.isin(top_3m.index)
    df["in_top_6m"] = df.index.isin(top_6m.index)
    df["in_all_three"] = df.index.isin(intersection)
    df["in_any"] = df.index.isin(union)

    # --- Relative-to-SPY momentum ranks ---------------------------------
    if "rel_return_6m_pct" in df.columns:
        df["rel_rank_3m"] = df["rel_return_3m_pct"].rank(ascending=False)
        df["rel_rank_6m"] = df["rel_return_6m_pct"].rank(ascending=False)
        rel_top_6m = df.nsmallest(args.top, "rel_rank_6m").index
        rel_top_3m = df.nsmallest(args.top, "rel_rank_3m").index
        df["in_rel_top_6m"] = df.index.isin(rel_top_6m)
        df["in_rel_top_3m"] = df.index.isin(rel_top_3m)
    else:
        df["rel_rank_3m"] = None
        df["rel_rank_6m"] = None
        df["in_rel_top_6m"] = False
        df["in_rel_top_3m"] = False

    # Q's "buy off bases, not extended" filter — WEEKLY-bar logic.
    # All thresholds reflect what a true multi-week consolidation looks like
    # rather than a single-week pullback in an aggressive uptrend.
    #
    #   EXTENDED_W       : dist_wma30 > 40%  OR  dist_wma10 > 18%
    #                       (stock has run too far past its weekly trend MAs)
    #   NEAR_10WMA       : within +/- 7% of the 10-week MA
    #   TIGHT_BASE_W     : 4-week range < 12%  OR  8-week range < 18%
    #                       (real consolidation on weekly bars, not a 1w dip)
    #   PULLBACK_W       : 4-8 week weekly pullback between -3% and -15%
    #   CONSOLIDATION    : at least 2 weeks since the last 8-week high made
    #                       (so it has actually paused, not still extending)
    #   VOL_DRYING       : last 4-week avg vol < prior 13-week avg vol
    #                       (smart-money accumulation phase looks quiet)
    #   UPTREND_W        : 10wma > 30wma (Q insists on rising structure)
    #   BASE_READY       : leader + UPTREND_W + NOT EXTENDED_W +
    #                       NEAR_10WMA + (TIGHT_BASE_W or PULLBACK_W) +
    #                       CONSOLIDATION + VOL_DRYING
    df["extended_w"] = (df["dist_wma30_pct"] > 40) | (df["dist_wma10_pct"] > 18)
    df["near_10wma"] = df["dist_wma10_pct"].abs() < 7
    df["tight_base_w"] = (df["range_4w_w_pct"] < 12) | (df["range_8w_w_pct"] < 18)
    df["pullback_w"] = (
        ((df["pullback_4w_w_pct"] > -15) & (df["pullback_4w_w_pct"] < -3))
        | ((df["pullback_8w_w_pct"] > -18) & (df["pullback_8w_w_pct"] < -3))
    )
    df["consolidating"] = df["weeks_since_8w_high"] >= 2
    df["vol_drying"] = df["vol_drying_ratio"].notna() & (df["vol_drying_ratio"] < 1.0)
    df["uptrend_w"] = df["wma_trend_up"].fillna(False)

    is_leader = df["in_top_1m"] | df["in_top_3m"] | df["in_top_6m"]
    df["base_ready"] = (
        is_leader
        & df["uptrend_w"]
        & (~df["extended_w"])
        & df["near_10wma"]
        & (df["tight_base_w"] | df["pullback_w"])
        & df["consolidating"]
        & df["vol_drying"]
    )
    # Softer "still forming" - missing only one of vol_drying or tight_base
    df["base_forming"] = (
        is_leader
        & df["uptrend_w"]
        & (~df["extended_w"])
        & df["near_10wma"]
        & (df["tight_base_w"] | df["pullback_w"])
        & df["consolidating"]
        & (~df["base_ready"])
    )

    df["q_score"] = (
        df["rank_avg"]
        + df["extended_w"].astype(int) * 500
        + (~df["uptrend_w"]).astype(int) * 200
        - df["near_10wma"].astype(int) * 30
        - df["tight_base_w"].astype(int) * 30
        - df["pullback_w"].astype(int) * 15
        - df["vol_drying"].astype(int) * 20
        - df["consolidating"].astype(int) * 10
    )

    # --- Roque score: count of bullish criteria passed (0..12) ----------
    def b(col):
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col].fillna(False).astype(bool)

    not_extended_w = df["dist_wma30_pct"].between(-5, 40) & df["dist_wma10_pct"].between(-10, 18)
    above_wma40 = df["dist_wma40_pct"].notna() & (df["dist_wma40_pct"] > 0)
    dma200_up = df["dma200_slope_pct"].notna() & (df["dma200_slope_pct"] > 0)
    macd_bull_abs = b("macd_above_signal") & b("macd_hist_rising")
    rel_not_extended = df.get("rel_dist_wma30_pct", pd.Series(False, index=df.index)).between(-5, 40)
    rel_macd_bull = b("rel_macd_above_signal") & b("rel_macd_hist_rising")
    base_or_consol = (df["tight_base_w"] | df["pullback_w"]) & df["consolidating"]
    is_leader = df["in_top_1m"] | df["in_top_3m"] | df["in_top_6m"]
    is_rel_leader = df["in_rel_top_3m"] | df["in_rel_top_6m"]

    df["roque_abs_trend"] = b("uptrend_w")
    df["roque_abs_above_40wma"] = above_wma40
    df["roque_abs_dma200_up"] = dma200_up
    df["roque_abs_not_extended"] = not_extended_w
    df["roque_abs_macd_bull"] = macd_bull_abs
    df["roque_abs_base"] = base_or_consol
    df["roque_rel_trend"] = b("rel_trend_up")
    df["roque_rel_not_extended"] = rel_not_extended
    df["roque_rel_macd_bull"] = rel_macd_bull
    df["roque_abs_leader"] = is_leader
    df["roque_rel_leader"] = is_rel_leader
    df["roque_vol_drying"] = b("vol_drying")

    roque_cols = ["roque_abs_trend", "roque_abs_above_40wma", "roque_abs_dma200_up",
                  "roque_abs_not_extended", "roque_abs_macd_bull", "roque_abs_base",
                  "roque_rel_trend", "roque_rel_not_extended", "roque_rel_macd_bull",
                  "roque_abs_leader", "roque_rel_leader", "roque_vol_drying"]
    df["roque_score"] = df[roque_cols].sum(axis=1)

    # PRE-BREAKOUT WEEKLY: setup is built but the breakout has not fired.
    # A real Q setup is NOT the current "top 30 momentum" cohort - those
    # are by definition already extended. Look instead for stocks that:
    #   - have had a prior advance (mom_6m > 1.10 = up 10%+ in 6 months)
    #   - are outperforming SPY (rel_return_6m > 0)
    #   - are now trending and basing
    #   - have NOT yet expanded (no recent breakout move in 4 weeks)
    soft_leader = (
        df["mom_6m"].fillna(0).gt(1.10)
        & df.get("rel_return_6m_pct", pd.Series(0, index=df.index)).fillna(0).gt(0)
    )
    df["soft_leader"] = soft_leader

    not_expanded_yet = (df["range_4w_w_pct"] < 12) & (df["pullback_4w_w_pct"] > -10)
    df["prebreakout_w"] = (
        df["roque_abs_trend"]
        & df["roque_rel_trend"]
        & df["roque_abs_not_extended"]
        & df["roque_rel_not_extended"]
        & df["consolidating"]
        & df["vol_drying"]
        & (df["tight_base_w"] | df["pullback_w"])
        & not_expanded_yet
        & soft_leader
    )

    # --- Darvas-box tags + Qullamaggie-style consolidation setups -------
    box_len = pd.to_numeric(df["box_length_weeks"], errors="coerce")
    box_height = pd.to_numeric(df["box_height_pct"], errors="coerce")
    dist_top = pd.to_numeric(df["dist_from_box_top_pct"], errors="coerce")
    pos_box = pd.to_numeric(df["pos_in_box_pct"], errors="coerce")

    df["darvas_tight"] = box_len.ge(4) & box_height.lt(15)
    df["long_base"] = box_len.ge(12) & box_height.lt(25)
    df["very_long_base"] = box_len.ge(26) & box_height.lt(30)
    df["base_on_base"] = df["inner_height_pct"].notna() & pd.to_numeric(df["inner_height_pct"], errors="coerce").lt(box_height * 0.6)
    df["near_box_top"] = dist_top.between(-3, 0)
    df["box_breakout"] = dist_top.gt(0) & dist_top.lt(5)  # just broke out, not yet extended

    # Qullamaggie Setup 3 (Consolidation Breakout): had a real prior move,
    # tight box, near top / just broken out, vol drying, relative trend up.
    big_prior_move = (
        df["mom_3m"].fillna(0).ge(1.20)
        | df["mom_6m"].fillna(0).ge(1.30)
    )
    df["big_prior_move"] = big_prior_move
    # Strict (Q's "big mover") vs loose (any prior advance)
    df["qulla_consol_setup"] = (
        big_prior_move
        & df["darvas_tight"]
        & (df["near_box_top"] | df["box_breakout"])
        & df["vol_drying"]
        & df["roque_rel_trend"].fillna(False)
    )
    # Looser variant: same structure but only mom_6m > 1.10 (had some advance)
    soft_prior = df["mom_6m"].fillna(0).gt(1.10)
    df["qulla_consol_soft"] = (
        soft_prior
        & df["darvas_tight"]
        & (df["near_box_top"] | df["box_breakout"])
        & df["vol_drying"]
        & df["roque_rel_trend"].fillna(False)
    )

    # Roque BIG BASE (multi-month consolidation breakout candidate).
    # Requires real price action: positive 6m momentum AND outperforming SPY,
    # else we get SPACs/CEFs trading in tight ranges by nature.
    real_movement = (
        df["mom_6m"].fillna(0).gt(1.05)
        & df.get("rel_return_6m_pct", pd.Series(-1, index=df.index)).fillna(-1).gt(0)
    )
    df["roque_big_base"] = (
        df["long_base"]
        & df["vol_drying"]
        & df["monthly_uptrend"].fillna(False)
        & (df["near_box_top"] | df["box_breakout"])
        & real_movement
    )

    # Save anything that is in the strict top-30 union OR passes a weekly
    # setup gate. This way Q-style "was-a-leader-now-basing" names that
    # do not currently rank top 30 still make it into the CSV for review.
    save_mask = (
        df["in_any"]
        | df["prebreakout_w"].fillna(False)
        | df["base_ready"].fillna(False)
        | df["base_forming"].fillna(False)
        | df["qulla_consol_setup"].fillna(False)
        | df["qulla_consol_soft"].fillna(False)
        | df["roque_big_base"].fillna(False)
        | df["long_base"].fillna(False)
        | df["q_method_pass"].fillna(False)
        | df["q_method_pass_weekly"].fillna(False)
        | df["q_method_pass_monthly_strong"].fillna(False)
        | df["breakout_squeeze"].fillna(False)
        | df["breakout_squeeze_loose"].fillna(False)
        | df["harmonic_bullish_w_or_m"].fillna(False)
        | df["harmonic_bullish_consonance"].fillna(False)
        | df["td_bullish_exhaustion"].fillna(False)
        | (df["roque_score"] >= 8)
    )
    flagged = df[save_mask].sort_values("roque_score", ascending=False)

    out_path = args.out or f"momentum_rank_{args.universe}_{pd.Timestamp.today():%Y%m%d}.csv"
    flagged.to_csv(out_path)
    print(f"Saved {len(flagged)} flagged tickers to {out_path}")

    show_cols = ["name", "sector", "last_close", "mom_3m", "mom_6m", "rel_return_6m_pct",
                 "dist_wma10_pct", "dist_wma30_pct", "dist_wma40_pct",
                 "dist_mma6_pct", "dist_mma12_pct", "months_since_6m_high",
                 "rel_dist_wma30_pct",
                 "box_top", "box_bottom", "box_height_pct", "box_length_weeks",
                 "pos_in_box_pct", "dist_from_box_top_pct",
                 "vol_drying_ratio",
                 "macd_above_signal", "rel_macd_above_signal",
                 "darvas_tight", "long_base", "very_long_base", "near_box_top", "box_breakout",
                 "qulla_consol_setup", "roque_big_base",
                 "prebreakout_w", "base_ready", "roque_score"]
    show_cols = [c for c in show_cols if c in flagged.columns]

    qulla = df[df["qulla_consol_setup"]].sort_values("box_length_weeks", ascending=False)
    qulla_soft = df[df["qulla_consol_soft"] & (~df["qulla_consol_setup"])].sort_values("box_length_weeks", ascending=False)
    q_method = df[df["q_method_pass"]].sort_values("rs_rank_max", ascending=False)
    q_method_weekly = df[df["q_method_pass_weekly"]].sort_values("rs_rank_max", ascending=False)
    q_method_both = df[df["q_method_pass"] & df["q_method_pass_weekly"]].sort_values("rs_rank_max", ascending=False)
    q_method_monthly = df[df["q_method_pass_monthly_strong"]].sort_values("rs_rank_max", ascending=False)
    breakout_sq = df[df["breakout_squeeze"]].sort_values("rs_rank_max", ascending=False)
    breakout_sq_strict = df[df["breakout_squeeze_strict"]].sort_values("rs_rank_max", ascending=False)
    breakout_sq_loose = df[df["breakout_squeeze_loose"] & (~df["breakout_squeeze"])].sort_values("rs_rank_max", ascending=False)
    harm_bull_cons = df[df["harmonic_bullish_consonance"]].sort_values("harmonic_score", ascending=False)
    harm_bull_wm = df[df["harmonic_bullish_w_or_m"] & (~df["harmonic_bullish_consonance"])].sort_values("harmonic_score", ascending=False)
    td_bull_strong = df[df["td_bullish_exhaustion_strong"]].sort_values("td_exhaustion_score", ascending=False)
    td_bull = df[df["td_bullish_exhaustion"] & (~df["td_bullish_exhaustion_strong"])].sort_values("td_exhaustion_score", ascending=False)
    td_most_asymmetric_bull = df.sort_values("td_mtf_composite", ascending=False).head(args.top)
    td_most_asymmetric_bear = df.sort_values("td_mtf_composite", ascending=True).head(args.top)
    big_base = df[df["roque_big_base"]].sort_values("box_length_weeks", ascending=False)
    long_bases = df[df["long_base"]].sort_values("box_length_weeks", ascending=False)
    very_long = df[df["very_long_base"]].sort_values("box_length_weeks", ascending=False)
    prebreakout = df[df["prebreakout_w"]].sort_values("roque_score", ascending=False)
    base_ready = df[df["base_ready"]].sort_values("q_score")
    base_forming = df[df["base_forming"]].sort_values("q_score")

    q_method_show = ["name", "sector", "last_close",
                     "rs_rank_max", "rs_rank_1w", "rs_rank_1m", "rs_rank_3m", "rs_rank_6m",
                     "atr_rs", "range_20d_pos_pct", "weekly_range_pos_pct",
                     "stacked_ma", "weekly_stacked_ma",
                     "rel_asym_now", "rel_asym_w_now", "rel_asym_m_now",
                     "rel_asym_d_signal", "rel_asym_w_signal", "rel_asym_m_signal",
                     "rel_asym_score",
                     "vol_asym_bonus", "vol_asym_w_bonus",
                     "q_method_pass", "q_method_pass_weekly", "q_method_pass_monthly_strong",
                     "box_length_weeks", "box_height_pct", "roque_score"]
    q_method_show = [c for c in q_method_show if c in flagged.columns]

    with pd.option_context("display.max_columns", None, "display.width", 300, "display.float_format", "{:.2f}".format):
        sq_cols = ["name", "sector", "last_close", "rs_rank_max",
                   "sq_d_value", "sq_d_pct_of_max", "sq_d_just_release", "sq_d_was_high_75",
                   "sq_w_value", "sq_w_pct_of_max", "sq_w_squeezing", "sq_w_was_high_75", "sq_w_hyper",
                   "sq_m_value", "sq_m_squeezing", "sq_m_was_high_75",
                   "asym_now", "asym_w_now", "asym_m_now", "asym_rising",
                   "vol_drying_ratio", "box_length_weeks", "box_height_pct", "roque_score"]
        sq_cols = [c for c in sq_cols if c in flagged.columns]

        print(f"\n=== BREAKOUT_SQUEEZE STRICT (daily just-release from >=90th-pct squeeze + weekly still squeezing in >=90th pct + asym improving) ({len(breakout_sq_strict)}) ===")
        if len(breakout_sq_strict):
            print(breakout_sq_strict[sq_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== BREAKOUT_SQUEEZE (daily just-release from >=75th pct + weekly still squeezing >=75th pct + asym improving) ({len(breakout_sq)}) ===")
        if len(breakout_sq):
            print(breakout_sq[sq_cols].head(args.top).to_string())
        else:
            print("(none)")

        harm_cols = ["name", "sector", "last_close", "rs_rank_max",
                     "h_d_pattern", "h_d_direction", "h_d_dist_from_d_pct", "h_d_bars_since_d",
                     "h_w_pattern", "h_w_direction", "h_w_dist_from_d_pct", "h_w_bars_since_d",
                     "h_m_pattern", "h_m_direction", "h_m_dist_from_d_pct", "h_m_bars_since_d",
                     "harmonic_consonance", "harmonic_score", "roque_score"]
        harm_cols = [c for c in harm_cols if c in flagged.columns]
        print(f"\n=== HARMONIC BULLISH CONSONANCE (>=2 timeframes bullish) ({len(harm_bull_cons)}) ===")
        if len(harm_bull_cons):
            print(harm_bull_cons[harm_cols].head(args.top).to_string())
        else:
            print("(none)")
        print(f"\n=== HARMONIC BULLISH W or M (weekly OR monthly bullish, less consonant) ({len(harm_bull_wm)}) ===")
        if len(harm_bull_wm):
            print(harm_bull_wm[harm_cols].head(args.top).to_string())
        else:
            print("(none)")

        td_cols = ["name", "sector", "last_close", "rs_rank_max",
                   "td_w_buy_setup", "td_w_buy_cd", "td_w_buy_perfect",
                   "td_w_stealth_buy", "td_w_triple_buy",
                   "td_m_buy_setup", "td_m_buy_cd", "td_m_buy_perfect",
                   "td_m_stealth_buy", "td_m_triple_buy",
                   "td_w_net_setup", "td_w_net_cd", "td_w_net_perfect",
                   "td_w_net_stealth", "td_w_net_triple",
                   "td_m_net_setup", "td_m_net_cd", "td_m_net_perfect",
                   "td_m_net_stealth", "td_m_net_triple",
                   "td_w_rel_net_setup", "td_w_rel_net_perfect",
                   "td_m_rel_net_setup", "td_m_rel_net_perfect",
                   "td_exhaustion_score", "roque_score"]
        td_cols = [c for c in td_cols if c in flagged.columns]
        print(f"\n=== TD EXHAUSTION BULLISH STRONG (td_exhaustion_score >= 10) ({len(td_bull_strong)}) ===")
        if len(td_bull_strong):
            print(td_bull_strong[td_cols].head(args.top).to_string())
        else:
            print("(none)")
        print(f"\n=== TD EXHAUSTION BULLISH (td_exhaustion_score >= 5, not strong) ({len(td_bull)}) ===")
        if len(td_bull):
            print(td_bull[td_cols].head(args.top).to_string())
        else:
            print("(none)")

        asym_cols = ["name", "sector", "last_close", "rs_rank_max",
                     "td_mtf_net_setup", "td_mtf_net_cd", "td_mtf_net_perfect",
                     "td_mtf_net_stealth", "td_mtf_net_triple",
                     "td_mtf_composite", "td_mtf_asymmetry",
                     "td_w_buy_setup", "td_w_sell_setup",
                     "td_m_buy_setup", "td_m_sell_setup",
                     "td_w_buy_cd", "td_w_sell_cd",
                     "td_m_buy_cd", "td_m_sell_cd",
                     "roque_score"]
        asym_cols = [c for c in asym_cols if c in flagged.columns]
        print(f"\n=== MOST ASYMMETRIC BULLISH (top {args.top} by td_mtf_composite, equal W=M weights) ===")
        print(td_most_asymmetric_bull[asym_cols].to_string())
        print(f"\n=== MOST ASYMMETRIC BEARISH (top {args.top} by -td_mtf_composite) ===")
        print(td_most_asymmetric_bear[asym_cols].to_string())

        print(f"\n=== BREAKOUT_SQUEEZE LOOSE (daily releasing + weekly squeezing + asym improving) ({len(breakout_sq_loose)}) ===")
        if len(breakout_sq_loose):
            print(breakout_sq_loose[sq_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== Q_METHOD_MONTHLY_STRONG (rel asym up on MONTHLY) ({len(q_method_monthly)}) ===")
        if len(q_method_monthly):
            print(q_method_monthly[q_method_show].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== Q_METHOD_PASS_BOTH (daily AND weekly criteria pass) ({len(q_method_both)}) ===")
        if len(q_method_both):
            print(q_method_both[q_method_show].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== Q_METHOD_PASS (RS>=70 + w/m rel-asym up + stacked MA + ATR_RS>=50 + range top half) ({len(q_method)}) ===")
        if len(q_method):
            print(q_method[q_method_show].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== Q_METHOD_PASS_WEEKLY (RS>=70 + weekly rel-asym up + weekly stacked MA + weekly range top half) ({len(q_method_weekly)}) ===")
        if len(q_method_weekly):
            print(q_method_weekly[q_method_show].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== QULLA_CONSOL_SETUP (Q big prior move + tight Darvas + near top + vol dry + rel up) ({len(qulla)}) ===")
        if len(qulla):
            print(qulla[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== QULLA_CONSOL_SOFT (any positive 6m advance + tight Darvas + near top + vol dry + rel up) ({len(qulla_soft)}) ===")
        if len(qulla_soft):
            print(qulla_soft[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== ROQUE_BIG_BASE (long box >=12w + monthly uptrend + vol dry + near/at box top) ({len(big_base)}) ===")
        if len(big_base):
            print(big_base[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== LONG_BASE (>=12 weeks, height < 25%) ({len(long_bases)}) ===")
        if len(long_bases):
            print(long_bases[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== VERY_LONG_BASE (>=26 weeks, height < 30%) ({len(very_long)}) ===")
        if len(very_long):
            print(very_long[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== PREBREAKOUT_W (Roque + relative-SPY, breakout not fired yet) ({len(prebreakout)}) ===")
        if len(prebreakout):
            print(prebreakout[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== Top by roque_score (count of 12 bullish criteria) ===")
        top_roque = df.sort_values(["roque_score", "rank_avg"], ascending=[False, True]).head(args.top)
        print(top_roque[show_cols].to_string())

        print(f"\n=== BASE_READY (weekly) ({len(base_ready)}) ===")
        if len(base_ready):
            print(base_ready[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== BASE_FORMING ({len(base_forming)}) ===")
        if len(base_forming):
            print(base_forming[show_cols].head(args.top).to_string())
        else:
            print("(none)")

        print(f"\n=== INTERSECTION: top {args.top} on ALL three timeframes ({len(intersection)}) ===")
        if intersection:
            print(df.loc[list(intersection)].sort_values("rank_max")[show_cols].to_string())
        else:
            print("(none)")

        print(f"\n=== Top {args.top} by 1-month momentum (c/avgc25) ===")
        print(df.loc[top_1m.index][show_cols].to_string())

        print(f"\n=== Top {args.top} by 3-month momentum (c/avgc66) ===")
        print(df.loc[top_3m.index][show_cols].to_string())

        print(f"\n=== Top {args.top} by 6-month momentum (c/avgc126) ===")
        print(df.loc[top_6m.index][show_cols].to_string())


if __name__ == "__main__":
    main()
