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
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd
import yfinance as yf

# Reuse the universe definitions from scan_failed_bearish.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_failed_bearish import get_universe  # noqa: E402


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
    for i in range(0, total, chunk_size):
        b = i // chunk_size + 1
        chunk = todo[i:i + chunk_size]
        print(f"  batch {b}/{n_batches}: {i + 1}-{min(i + chunk_size, total)} of {total} (kept: {len(frames)})")
        try:
            data = yf.download(
                chunk, period=f"{years}y", interval="1d",
                group_by="ticker", threads=True, progress=False, auto_adjust=True,
            )
        except Exception as e:
            print(f"    batch failed: {e}")
            data = None
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
        done.update(chunk)
        save_pickle(universe, years, frames, done)
        if b < n_batches:
            time.sleep(batch_sleep)
    return frames


SPY_PICKLE = "/tmp/cyclepapa_spy_daily.pkl"


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
    spy = pd.to_numeric(data["Close"], errors="coerce").dropna()
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


def compute_momentum(df, spy_close=None):
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(close) < 130:
        return None
    high = pd.to_numeric(df.loc[close.index, "High"], errors="coerce")
    low = pd.to_numeric(df.loc[close.index, "Low"], errors="coerce")
    volume = pd.to_numeric(df.loc[close.index, "Volume"], errors="coerce")
    last = float(close.iloc[-1])
    sma25 = float(close.tail(25).mean())
    sma66 = float(close.tail(66).mean())
    sma126 = float(close.tail(126).mean())
    if min(sma25, sma66, sma126) <= 0:
        return None

    # --- Daily metrics (kept for reference, used for momentum ranks) -------
    sma20 = float(close.tail(20).mean())
    sma50 = float(close.tail(50).mean())
    dist_sma20 = (last - sma20) / sma20 * 100
    dist_sma50 = (last - sma50) / sma50 * 100

    # --- Weekly metrics (the proper Q base/extension lens) -----------------
    df_ohlcv = pd.DataFrame({
        "Open": pd.to_numeric(df["Open"], errors="coerce") if "Open" in df.columns else close,
        "High": high, "Low": low, "Close": close, "Volume": volume,
    }).dropna()
    weekly = df_ohlcv.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()
    if len(weekly) < 30:
        return None

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

    # Days since 52-week high (calendar days), kept for reference
    try:
        days_since_52w_high = int((close.index[-1] - high.tail(252).idxmax()).days)
    except Exception:
        days_since_52w_high = None

    # Weekly MACD on absolute close
    macd_w, signal_w, hist_w = macd(wclose)
    macd_above = bool(macd_w.iloc[-1] > signal_w.iloc[-1])
    macd_hist_rising = bool(hist_w.iloc[-1] > hist_w.iloc[-2]) if len(hist_w) >= 2 else False

    # 200-day MA slope (Roque's "demand line")
    dma200_slope, dist_dma200 = dma200_slope_pct(close)

    out = {
        "last_close": last,
        "mom_1m": last / sma25,
        "mom_3m": last / sma66,
        "mom_6m": last / sma126,
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
                out.update({
                    "rel_dist_wma10_pct": float(rel_dist_wma10),
                    "rel_dist_wma30_pct": float(rel_dist_wma30),
                    "rel_trend_up": bool(rel_trend_up),
                    "rel_macd_above_signal": rel_macd_above,
                    "rel_macd_hist_rising": rel_hist_rising,
                    "rel_return_3m_pct": float(rel_ret_3m) if rel_ret_3m is not None else None,
                    "rel_return_6m_pct": float(rel_ret_6m) if rel_ret_6m is not None else None,
                })

    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True,
                        help="Universe key (e.g. us-smid, us-midlarge, us-micro, eu-smid).")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--min-price", type=float, default=5.0,
                        help="Drop tickers with last close below this (liquidity floor).")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print(f"Loading {args.universe} universe...")
    universe = get_universe(args.universe)
    tickers = [t for t in universe.index.tolist() if isinstance(t, str) and t]
    print(f"  {len(tickers)} tickers")

    spy_close = load_or_download_spy(years=max(args.years + 1, 3))

    print(f"Downloading daily bars ({args.years}y)...")
    frames = download_daily(args.universe, tickers, years=args.years)
    print(f"  {len(frames)} tickers with usable daily data")

    rows = []
    for t, f in frames.items():
        m = compute_momentum(f, spy_close=spy_close)
        if m is None:
            continue
        if m["last_close"] < args.min_price:
            continue
        m["Ticker"] = t
        name_col = "name" if "name" in universe.columns else "shortName"
        m["name"] = universe.loc[t, name_col] if t in universe.index else None
        m["sector"] = universe.loc[t, "sector"] if t in universe.index and "sector" in universe.columns else None
        rows.append(m)

    if not rows:
        print("No momentum metrics computed.")
        return

    df = pd.DataFrame(rows).set_index("Ticker")
    df["rank_1m"] = df["mom_1m"].rank(ascending=False).astype(int)
    df["rank_3m"] = df["mom_3m"].rank(ascending=False).astype(int)
    df["rank_6m"] = df["mom_6m"].rank(ascending=False).astype(int)
    df["rank_avg"] = (df["rank_1m"] + df["rank_3m"] + df["rank_6m"]) / 3
    df["rank_max"] = df[["rank_1m", "rank_3m", "rank_6m"]].max(axis=1)

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
    #   - Trend up (abs + rel)
    #   - Not extended (abs + rel)
    #   - Consolidating with vol drying
    #   - Price has NOT expanded recently (no breakout move yet)
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
        & is_leader
    )

    flagged = df[df["in_any"]].sort_values("rank_max")

    out_path = args.out or f"momentum_rank_{args.universe}_{pd.Timestamp.today():%Y%m%d}.csv"
    flagged.to_csv(out_path)
    print(f"Saved {len(flagged)} flagged tickers to {out_path}")

    show_cols = ["name", "sector", "last_close", "mom_3m", "mom_6m",
                 "rank_3m", "rank_6m", "rel_rank_6m",
                 "dist_wma10_pct", "dist_wma30_pct", "dist_wma40_pct",
                 "dist_dma200_pct", "dma200_slope_pct",
                 "rel_dist_wma30_pct", "rel_return_6m_pct",
                 "range_4w_w_pct", "range_8w_w_pct",
                 "pullback_4w_w_pct", "weeks_since_8w_high", "vol_drying_ratio",
                 "macd_above_signal", "macd_hist_rising",
                 "rel_macd_above_signal", "rel_macd_hist_rising",
                 "prebreakout_w", "base_ready", "base_forming",
                 "roque_score", "q_score"]
    show_cols = [c for c in show_cols if c in flagged.columns]

    prebreakout = df[df["prebreakout_w"]].sort_values("roque_score", ascending=False)
    base_ready = df[df["base_ready"]].sort_values("q_score")
    base_forming = df[df["base_forming"]].sort_values("q_score")

    with pd.option_context("display.max_columns", None, "display.width", 280, "display.float_format", "{:.2f}".format):
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
