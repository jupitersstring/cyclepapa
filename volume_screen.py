"""
Volume step-up + price-compression screen for failed-bearish-setup candidates.

The intuition: stealth accumulation. Volume rises against the immediately
prior, NON-OVERLAPPING period (recent N vs prior N) while price stays
compressed (tight range, low ATR%, narrow Bollinger bands). When the
squeeze releases, breakout tends to follow the accumulation.

Multiple lookbacks are run in parallel so we catch both fresh (last 2-4
weeks) and matured (last 8 weeks) accumulation:

  N=2   - last 2 weeks vs prior 2 weeks       (fast / fresh)
  N=3   - last 3 weeks vs prior 3 weeks
  N=4   - last 4 weeks vs prior 4 weeks       (intermediate)
  N=8   - last 8 weeks vs prior 8 weeks       (matured, conviction)

For each N we compute:
  vol_stepup_Nw        mean(last N) / mean(prior N)
  bars_above_Nw        count of last N bars where vol > mean(prior N)
  range_pct_Nw         (max(high)-min(low))/mean(close) over last N bars
  price_return_Nw      (last close / close at -N) - 1, in pct

Shared (lookback-independent) compression:
  atr_pct              ATR(14) / last close, in pct
  atr_compression      atr_pct / median atr_pct over 52 bars      (<1 tight)
  bb_compression       BB(20) width now / median BB width 52      (<1 tight)

Tags are emitted per lookback so you can see which timeframe triggered:

  COILED@Nw          - vol_stepup >= 1.1, >50% bars above prior,
                        2+ of {range, atr, bb} compressed, price flat (+/-10%)
  COILED_TIGHT@Nw    - stricter: vol_stepup >= 1.3, range tight for N,
                        ATR or BB strongly compressed, price within +/-5%
  BREAKOUT_FIRING@Nw - vol_stepup >= 1.3 AND price up > 8% over the lookback
  STRONG_VOLUME@Nw   - vol_stepup >= 1.8 AND >=75% bars above prior
"""

import argparse
import os
import pickle
import time

import numpy as np
import pandas as pd
import yfinance as yf


PICKLE_TMPL = "/tmp/cyclepapa_dl_{universe}_{timeframe}_{years}y.pkl"
LOOKBACKS = (2, 3, 4, 8)
# Range thresholds scale with lookback length
RANGE_LOOSE = {2: 6, 3: 8, 4: 10, 8: 18}
RANGE_TIGHT = {2: 4, 3: 6, 4: 7, 8: 12}


def load_pickle_frames(universe, timeframe, years):
    path = PICKLE_TMPL.format(universe=universe, timeframe=timeframe, years=years)
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        state = pickle.load(f)
    return state.get("frames", {})


def download_frames(tickers, timeframe, years=2, chunk_size=50, batch_sleep=15):
    interval = "1wk" if timeframe == "weekly" else "1mo"
    frames = {}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        try:
            data = yf.download(
                chunk, period=f"{years}y", interval=interval,
                group_by="ticker", threads=True, progress=False, auto_adjust=True,
            )
        except Exception as e:
            print(f"  batch {i // chunk_size + 1} failed: {e}")
            data = None
        if data is not None and not data.empty:
            for t in chunk:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        sub = data[t].dropna(how="all")
                    else:
                        sub = data.dropna(how="all")
                    if "Volume" in sub.columns and len(sub) >= 60:
                        frames[t] = sub
                except Exception:
                    continue
        if i + chunk_size < len(tickers):
            time.sleep(batch_sleep)
    return frames


def true_range(high, low, close_prev):
    return np.maximum(
        high - low,
        np.maximum(np.abs(high - close_prev), np.abs(low - close_prev)),
    )


def compute_poc(df, lookback=52, bins=50):
    """Volume profile over last `lookback` bars; returns POC price and
    current close distance to it. Each bar's volume is distributed across
    its high-low range in proportion to overlap with each price bin."""
    if len(df) < lookback:
        return None
    sub = df.iloc[-lookback:]
    high = pd.to_numeric(sub["High"], errors="coerce").astype(float).values
    low = pd.to_numeric(sub["Low"], errors="coerce").astype(float).values
    close = pd.to_numeric(sub["Close"], errors="coerce").astype(float).values
    vol = pd.to_numeric(sub["Volume"], errors="coerce").astype(float).values
    if np.any(np.isnan(high)) or np.any(np.isnan(vol)):
        return None
    lo, hi = low.min(), high.max()
    if hi <= lo:
        return None
    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    bin_vol = np.zeros(bins)
    bar_range = high - low
    for b in range(bins):
        e_lo, e_hi = edges[b], edges[b + 1]
        overlap_lo = np.maximum(low, e_lo)
        overlap_hi = np.minimum(high, e_hi)
        overlap = np.clip(overlap_hi - overlap_lo, 0, None)
        # avoid divide-by-zero on zero-range bars
        frac = np.where(bar_range > 0, overlap / np.where(bar_range > 0, bar_range, 1), 0)
        # zero-range bars dump full volume in the bin containing the close
        zero_mask = bar_range == 0
        if zero_mask.any():
            in_bin = (close[zero_mask] >= e_lo) & (close[zero_mask] < e_hi)
            frac = np.where(zero_mask, in_bin.astype(float), frac)
        bin_vol[b] += np.sum(vol * frac)
    poc_idx = int(np.argmax(bin_vol))
    poc_price = float(centers[poc_idx])
    current = float(close[-1])
    return {
        "poc": poc_price,
        "poc_distance_pct": (current - poc_price) / poc_price * 100,
        "poc_volume_share": float(bin_vol[poc_idx] / bin_vol.sum()) if bin_vol.sum() > 0 else 0.0,
    }


def compute_metrics(df, lookbacks=LOOKBACKS, atr_period=14, bb_period=20, hist_window=52):
    needed = max(max(lookbacks) * 2, atr_period + hist_window + 1, bb_period + hist_window)
    if len(df) < needed:
        return None
    high = pd.to_numeric(df["High"], errors="coerce").astype(float).values
    low = pd.to_numeric(df["Low"], errors="coerce").astype(float).values
    close = pd.to_numeric(df["Close"], errors="coerce").astype(float).values
    vol = pd.to_numeric(df["Volume"], errors="coerce").astype(float).values
    if np.any(np.isnan(close[-needed:])) or np.any(np.isnan(vol[-needed:])):
        return None

    # Shared compression metrics
    tr = true_range(high[1:], low[1:], close[:-1])
    atr_series = pd.Series(tr).rolling(atr_period).mean().values
    atr_pct_series = atr_series / close[1:] * 100
    atr_pct_now = atr_pct_series[-1]
    atr_pct_median = np.nanmedian(atr_pct_series[-hist_window:])
    atr_compression = atr_pct_now / atr_pct_median if atr_pct_median and not np.isnan(atr_pct_median) else None

    close_s = pd.Series(close)
    bb_mean = close_s.rolling(bb_period).mean()
    bb_std = close_s.rolling(bb_period).std()
    bb_width_pct = (4 * bb_std / bb_mean) * 100
    bb_now = bb_width_pct.iloc[-1]
    bb_median = bb_width_pct.iloc[-hist_window:].median()
    bb_compression = (bb_now / bb_median) if bb_median and not np.isnan(bb_median) else None

    out = {
        "atr_pct": float(atr_pct_now),
        "atr_compression": float(atr_compression) if atr_compression is not None else None,
        "bb_compression": float(bb_compression) if bb_compression is not None else None,
        "last_close": float(close[-1]),
    }

    for N in lookbacks:
        recent_vol = vol[-N:]
        prior_vol = vol[-(2 * N):-N]
        if recent_vol.mean() == 0 or prior_vol.mean() == 0:
            continue
        recent_high = high[-N:].max()
        recent_low = low[-N:].min()
        recent_mean_close = close[-N:].mean()
        out[f"vol_stepup_{N}w"] = float(recent_vol.mean() / prior_vol.mean())
        out[f"bars_above_{N}w"] = int((recent_vol > prior_vol.mean()).sum())
        out[f"range_pct_{N}w"] = float((recent_high - recent_low) / recent_mean_close * 100)
        out[f"price_return_{N}w"] = float((close[-1] / close[-N] - 1) * 100)

    poc = compute_poc(df, lookback=52, bins=50)
    if poc:
        out["poc"] = poc["poc"]
        out["poc_distance_pct"] = poc["poc_distance_pct"]
        out["poc_volume_share"] = poc["poc_volume_share"]

    return out


def classify(m, lookbacks=LOOKBACKS):
    tags = []
    atr_c = m.get("atr_compression")
    bb_c = m.get("bb_compression")
    for N in lookbacks:
        vol_stepup = m.get(f"vol_stepup_{N}w")
        bars_above = m.get(f"bars_above_{N}w")
        range_pct = m.get(f"range_pct_{N}w")
        price_return = m.get(f"price_return_{N}w")
        if vol_stepup is None:
            continue
        bars_threshold = (N + 1) // 2  # >=50% of bars above prior mean
        compression_score = sum([
            range_pct < RANGE_LOOSE[N],
            atr_c is not None and atr_c < 0.85,
            bb_c is not None and bb_c < 0.85,
        ])
        tight_compression = (
            range_pct < RANGE_TIGHT[N]
            and ((atr_c is not None and atr_c < 0.80) or (bb_c is not None and bb_c < 0.70))
        )
        vol_step_soft = vol_stepup >= 1.1 and bars_above >= bars_threshold
        vol_step_strong = vol_stepup >= 1.3 and bars_above >= bars_threshold
        flat_loose = -10.0 < price_return < 10.0
        flat_tight = -5.0 < price_return < 5.0

        if vol_step_soft and compression_score >= 2 and flat_loose:
            tags.append(f"COILED@{N}w")
        if vol_step_strong and tight_compression and flat_tight:
            tags.append(f"COILED_TIGHT@{N}w")
        if vol_step_strong and price_return > 8:
            tags.append(f"BREAKOUT_FIRING@{N}w")
        if vol_stepup >= 1.8 and bars_above >= max(2, int(0.75 * N)):
            tags.append(f"STRONG_VOLUME@{N}w")
    poc_dist = m.get("poc_distance_pct")
    if poc_dist is not None and abs(poc_dist) < 3:
        tags.append("NEAR_POC")
    return tags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv")
    parser.add_argument("--universe", default=None,
                        help="Universe key for checkpoint pickle (e.g. de-all, us-midlarge).")
    parser.add_argument("--timeframe", default="weekly")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv, index_col=0)
    tickers = df.index.tolist()
    print(f"Loaded {len(tickers)} candidates from {args.input_csv}")

    frames = {}
    if args.universe:
        frames = load_pickle_frames(args.universe, args.timeframe, args.years)
        in_pickle = [t for t in tickers if t in frames]
        print(f"  {len(in_pickle)}/{len(tickers)} found in checkpoint pickle")
    missing = [t for t in tickers if t not in frames]
    if missing:
        print(f"  downloading {len(missing)} missing ({args.timeframe}, 2y)...")
        frames.update(download_frames(missing, args.timeframe))

    rows = []
    for t in tickers:
        f = frames.get(t)
        if f is None:
            continue
        m = compute_metrics(f)
        if m is None:
            continue
        tags = classify(m)
        m["Ticker"] = t
        m["tags"] = ",".join(tags) if tags else ""
        rows.append(m)

    if not rows:
        print("No volume metrics computed.")
        return

    vol_df = pd.DataFrame(rows).set_index("Ticker")
    # avoid column collisions if the input CSV already has some of these
    overlap = [c for c in vol_df.columns if c in df.columns]
    if overlap:
        df = df.drop(columns=overlap)
    merged = df.join(vol_df, how="left")
    out_path = args.out or args.input_csv.replace(".csv", "_volume.csv")
    merged.to_csv(out_path)
    print(f"Saved: {out_path}")

    def show_tag(prefix):
        sub = merged[merged["tags"].fillna("").str.contains(prefix, regex=False)]
        if len(sub) == 0:
            print(f"\n=== {prefix} (0) ===\n(none)")
            return
        cols = ["shortName", "sector", "priceToBook", "returnOnEquity",
                "atr_compression", "bb_compression"]
        # add the lookback-specific columns that triggered
        for N in LOOKBACKS:
            for col in (f"vol_stepup_{N}w", f"range_pct_{N}w", f"price_return_{N}w"):
                if col in sub.columns:
                    cols.append(col)
        cols += ["failure_date", "pct_from_failure", "score", "tags"]
        cols = [c for c in cols if c in sub.columns]
        print(f"\n=== {prefix} ({len(sub)}) ===")
        sort_col = "score" if "score" in sub.columns else "vol_stepup_2w"
        print(sub.sort_values(sort_col, ascending=False)[cols].to_string())

    with pd.option_context("display.max_columns", None, "display.width", 260, "display.float_format", "{:.2f}".format):
        show_tag("COILED_TIGHT")
        show_tag("COILED@")  # excludes COILED_TIGHT
        show_tag("BREAKOUT_FIRING")
        show_tag("STRONG_VOLUME")


if __name__ == "__main__":
    main()
