"""
Volume + compression screen for failed-bearish-setup candidates.

The intuition: stealth accumulation. Buyers step in - so volume rises against
the immediately prior, NON-OVERLAPPING period - but they do not move price,
so the bar is compressed (tight range, low ATR%, narrow Bollinger bands).
When the squeeze releases, breakout tends to follow the accumulation.

Metrics (weekly bars unless --timeframe monthly):

  vol_stepup        = mean(last N) / mean(prior N)            (N=8 by default)
  bars_above_prior  = count of last N bars where vol > mean(prior N)
  range_pct         = (max(high)-min(low)) / mean(close) over last N bars
  atr_pct           = ATR(14) / last close, in pct
  atr_compression   = atr_pct / median atr_pct over last 52 bars   (<1 tight)
  bb_compression    = current BB(20) width / median BB width 52    (<1 tight)
  price_return_pct  = (last close / close at -N) - 1, in pct

Tags:
  COILED            - vol_stepup >= 1.3 AND bars_above_prior >= 5
                       AND any of (range_pct < 15, atr_compression < 0.85,
                                   bb_compression < 0.85)
                       AND price_return between -8% and +8%  (price compressed)
  COILED_TIGHT      - the strict version: vol_stepup >= 1.5, bars >= 6,
                       range_pct < 10, atr_compression < 0.75
  BREAKOUT_FIRING   - vol_stepup >= 1.5 AND bars_above_prior >= 5
                       AND price_return_pct > 8 (volume confirms a move
                       already in progress; not "early" but still actionable)
  STRONG_VOLUME     - vol_stepup >= 2.0 AND bars_above_prior >= 6
                       (heavy sustained volume, regardless of price action)
"""

import argparse
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd
import yfinance as yf


PICKLE_TMPL = "/tmp/cyclepapa_dl_{universe}_{timeframe}_{years}y.pkl"


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


def compute_metrics(df, recent_n=8, prior_n=8, atr_period=14, bb_period=20, hist_window=52):
    needed = max(recent_n + prior_n, atr_period + hist_window + 1, bb_period + hist_window)
    if len(df) < needed:
        return None
    high = pd.to_numeric(df["High"], errors="coerce").astype(float).values
    low = pd.to_numeric(df["Low"], errors="coerce").astype(float).values
    close = pd.to_numeric(df["Close"], errors="coerce").astype(float).values
    vol = pd.to_numeric(df["Volume"], errors="coerce").astype(float).values
    if np.any(np.isnan(close[-needed:])) or np.any(np.isnan(vol[-needed:])):
        return None

    # Volume step-up: non-overlapping windows
    recent_vol = vol[-recent_n:]
    prior_vol = vol[-(recent_n + prior_n):-recent_n]
    if recent_vol.mean() == 0 or prior_vol.mean() == 0:
        return None
    vol_stepup = recent_vol.mean() / prior_vol.mean()
    bars_above_prior = int((recent_vol > prior_vol.mean()).sum())

    # Range over last N bars
    recent_high = high[-recent_n:].max()
    recent_low = low[-recent_n:].min()
    recent_mean_close = close[-recent_n:].mean()
    range_pct = (recent_high - recent_low) / recent_mean_close * 100

    # ATR(14) series in pct of close
    tr = true_range(high[1:], low[1:], close[:-1])
    atr_series = pd.Series(tr).rolling(atr_period).mean().values
    atr_pct_series = atr_series / close[1:] * 100
    atr_pct_now = atr_pct_series[-1]
    atr_pct_window = atr_pct_series[-hist_window:]
    atr_pct_median = np.nanmedian(atr_pct_window)
    atr_compression = atr_pct_now / atr_pct_median if atr_pct_median and not np.isnan(atr_pct_median) else np.nan

    # Bollinger Band width
    close_s = pd.Series(close)
    bb_mean = close_s.rolling(bb_period).mean()
    bb_std = close_s.rolling(bb_period).std()
    bb_width_pct = (4 * bb_std / bb_mean) * 100  # +/-2 sigma band width as %
    bb_now = bb_width_pct.iloc[-1]
    bb_median = bb_width_pct.iloc[-hist_window:].median()
    bb_compression = (bb_now / bb_median) if bb_median and not np.isnan(bb_median) else np.nan

    price_return_pct = (close[-1] / close[-recent_n] - 1) * 100

    return {
        "vol_stepup": float(vol_stepup),
        "bars_above_prior": bars_above_prior,
        "range_pct": float(range_pct),
        "atr_pct": float(atr_pct_now),
        "atr_compression": float(atr_compression) if not np.isnan(atr_compression) else None,
        "bb_compression": float(bb_compression) if not np.isnan(bb_compression) else None,
        "price_return_pct": float(price_return_pct),
        "last_close": float(close[-1]),
    }


def classify(m):
    tags = []
    atr_c = m["atr_compression"]
    bb_c = m["bb_compression"]
    # Count compression hits across three dimensions
    compression_score = sum([
        m["range_pct"] < 18,
        atr_c is not None and atr_c < 0.85,
        bb_c is not None and bb_c < 0.85,
    ])
    # Tight version
    tight_compression = (
        m["range_pct"] < 12
        and ((atr_c is not None and atr_c < 0.80) or (bb_c is not None and bb_c < 0.70))
    )
    vol_step_soft = m["vol_stepup"] >= 1.1 and m["bars_above_prior"] >= 4
    vol_step_strong = m["vol_stepup"] >= 1.3 and m["bars_above_prior"] >= 5
    price_compressed_loose = -10.0 < m["price_return_pct"] < 10.0
    price_compressed_tight = -5.0 < m["price_return_pct"] < 5.0

    if vol_step_soft and compression_score >= 2 and price_compressed_loose:
        tags.append("COILED")
    if vol_step_strong and tight_compression and price_compressed_tight:
        tags.append("COILED_TIGHT")
    if vol_step_strong and m["price_return_pct"] > 8:
        tags.append("BREAKOUT_FIRING")
    if m["vol_stepup"] >= 1.8 and m["bars_above_prior"] >= 6:
        tags.append("STRONG_VOLUME")
    return tags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", help="Quality-filtered CSV from scan_failed_bearish.py")
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
    merged = df.join(vol_df, how="left")
    out_path = args.out or args.input_csv.replace(".csv", "_volume.csv")
    merged.to_csv(out_path)
    print(f"Saved: {out_path}")

    show_cols = [
        "shortName", "sector", "priceToBook", "enterpriseToEbitda",
        "returnOnEquity", "vol_stepup", "bars_above_prior",
        "range_pct", "atr_compression", "bb_compression",
        "price_return_pct", "failure_date", "pct_from_failure", "score",
    ]
    show_cols = [c for c in show_cols if c in merged.columns]

    def show(tag):
        sub = merged[merged["tags"].fillna("").str.contains(tag)]
        print(f"\n=== {tag} ({len(sub)}) ===")
        if len(sub):
            sort_col = "score" if "score" in sub.columns else "vol_stepup"
            print(sub.sort_values(sort_col, ascending=False)[show_cols].to_string())
        else:
            print("(none)")

    with pd.option_context("display.max_columns", None, "display.width", 240, "display.float_format", "{:.2f}".format):
        show("COILED_TIGHT")
        show("COILED")
        show("BREAKOUT_FIRING")
        show("STRONG_VOLUME")


if __name__ == "__main__":
    main()
