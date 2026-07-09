"""MTF PSAR Trend Change Composite — port of malikmck's Pine script.

Settings (matching the screenshot):
  PSAR start=0.02, increment=0.02, maximum=0.2
  Timeframes & lookbacks:
    TF1: 30m,  lookback 50
    TF2: 3M (quarterly), lookback 8
    TF3: 240m (4h),      lookback 50
    TF4: 60m,            lookback 50
    TF5: W,              lookback 20
    TF6: D,              lookback 50
    TF7: M,              lookback 20
  MA: SMA(10)
  Benchmark: ^GSPC (SP:SPX)

yfinance intraday granularity is limited (30m -> 60d, 60m -> 730d).
When intraday data is unavailable for a ticker, that TF is silently
skipped; the composite then averages only the active (returned) TFs,
matching the Pine indicator's "Use TFx" toggle behaviour.

Recency model: per the user spec, ranking = current_value *
(1 + 0.5 * tanh(5-bar slope / 30-bar std)). Freshly-ascending names
get a moderate boost; stable high-level names still rank if value
is high.

Output: ranks the universe by:
  - Asset Net MA (now)
  - Relative Net MA (now)
  - Asset Net MA composite (current * recency)
  - Relative Net MA composite (current * recency)
"""

import sys
import glob
import time
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc

PSAR_START     = 0.02
PSAR_INCREMENT = 0.02
PSAR_MAXIMUM   = 0.2
MA_LEN         = 10
BENCHMARK      = "^GSPC"

# (tf_label, yf_interval, resample_rule, lookback)
TF_CONFIG = [
    ("TF1_30m",   "30m", None,   50),
    ("TF2_3M",    "1mo", "3MS",  8),
    ("TF3_240m",  "60m", "4h",   50),
    ("TF4_60m",   "60m", None,   50),
    ("TF5_W",     "1wk", None,   20),
    ("TF6_D",     "1d",  None,   50),
    ("TF7_M",     "1mo", None,   20),
]

# Period to fetch per interval
PERIOD_BY_INTERVAL = {
    "30m":  "60d",
    "60m":  "729d",
    "1d":   "10y",
    "1wk":  "10y",
    "1mo":  "max",
}


# ─────────────────────────────────────────────────────────────────
# PSAR (Wilder) — matches Pine ta.sar(start, inc, max)
# ─────────────────────────────────────────────────────────────────

def psar(high, low,
         af0=PSAR_START, af_step=PSAR_INCREMENT, af_max=PSAR_MAXIMUM):
    n = len(high)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    h = np.asarray(high, dtype=float)
    l = np.asarray(low,  dtype=float)
    bull = True
    af = af0
    hp = h[0]
    lp = l[0]
    out[0] = l[0]
    for i in range(1, n):
        out[i] = out[i-1] + af * ((hp if bull else lp) - out[i-1])
        reverse = False
        if bull:
            if l[i] < out[i]:
                bull = False
                reverse = True
                out[i] = hp
                lp = l[i]
                af = af0
        else:
            if h[i] > out[i]:
                bull = True
                reverse = True
                out[i] = lp
                hp = h[i]
                af = af0
        if not reverse:
            if bull:
                if h[i] > hp:
                    hp = h[i]
                    af = min(af + af_step, af_max)
                if l[i-1] < out[i]:
                    out[i] = l[i-1]
                if i >= 2 and l[i-2] < out[i]:
                    out[i] = l[i-2]
            else:
                if l[i] < lp:
                    lp = l[i]
                    af = min(af + af_step, af_max)
                if h[i-1] > out[i]:
                    out[i] = h[i-1]
                if i >= 2 and h[i-2] > out[i]:
                    out[i] = h[i-2]
    return out


# ─────────────────────────────────────────────────────────────────
# Trend & signal series
# ─────────────────────────────────────────────────────────────────

def asset_trend(bars: pd.DataFrame):
    if bars is None or len(bars) < 5:
        return None
    sar = psar(bars["High"].values, bars["Low"].values)
    trend = np.where(sar < bars["Close"].values, 1, -1)
    return pd.Series(trend, index=bars.index)


def relative_trend(asset_close: pd.Series, bench_close: pd.Series):
    if asset_close is None or bench_close is None:
        return None
    common = asset_close.index.intersection(bench_close.index)
    if len(common) < 6:
        return None
    a = asset_close.reindex(common)
    b = bench_close.reindex(common).replace(0, np.nan)
    r = (a / b).dropna()
    if len(r) < 6:
        return None
    trend = np.where(r > r.shift(4), 1, -1)
    return pd.Series(trend, index=r.index)


def buy_sell_counts(trend: pd.Series, lookback: int):
    prev = trend.shift(1)
    buy  = ((trend == 1)  & (prev == -1)).astype(int)
    sell = ((trend == -1) & (prev ==  1)).astype(int)
    return (buy.rolling(lookback,  min_periods=1).sum(),
            sell.rolling(lookback, min_periods=1).sum())


def resample_ohlc(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    return bars.resample(rule).agg({
        "Open":  "first",
        "High":  "max",
        "Low":   "min",
        "Close": "last",
    }).dropna()


# ─────────────────────────────────────────────────────────────────
# Per-ticker composite
# ─────────────────────────────────────────────────────────────────

def composites_for_ticker(ticker: str,
                          per_interval_bars: dict,
                          per_interval_bench: dict):
    """Build the daily-aligned Asset Net MA and Relative Net MA series.

    per_interval_bars[interval][ticker] -> ticker OHLC DataFrame at that interval.
    per_interval_bench[interval] -> benchmark OHLC at that interval.

    Returns (asset_net_ma_series, rel_net_ma_series). Either may be None
    if no TF returned usable data.
    """
    asset_buys, asset_sells = [], []
    rel_buys,   rel_sells   = [], []
    used = []
    for label, interval, resample_rule, lb in TF_CONFIG:
        raw_t = per_interval_bars.get(interval, {}).get(ticker)
        raw_b = per_interval_bench.get(interval)
        if raw_t is None or raw_b is None or len(raw_t) < 10:
            continue
        if resample_rule:
            try:
                bars  = resample_ohlc(raw_t, resample_rule)
                bench = raw_b["Close"].resample(resample_rule).last().dropna()
            except Exception:
                continue
        else:
            bars  = raw_t
            bench = raw_b["Close"]
        if len(bars) < lb + 5:
            continue
        at = asset_trend(bars)
        rt = relative_trend(bars["Close"], bench)
        if at is None or rt is None:
            continue
        ab, as_ = buy_sell_counts(at, lb)
        rb, rs  = buy_sell_counts(rt, lb)
        asset_buys.append(ab)
        asset_sells.append(as_)
        rel_buys.append(rb)
        rel_sells.append(rs)
        used.append(label)
    if not used:
        return None, None, []

    # Build daily-aligned index: union of all TF date ranges, downsampled to daily.
    all_dates = pd.DatetimeIndex(sorted(set().union(*[s.index for s in asset_buys])))
    if all_dates.tz is not None:
        all_dates = all_dates.tz_localize(None)
    common = pd.date_range(all_dates.min().normalize(),
                            all_dates.max().normalize(), freq="D")

    def _ffill_align(s):
        # Strip timezone so reindex doesn't error.
        if s.index.tz is not None:
            s = s.copy()
            s.index = s.index.tz_localize(None)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        return s.reindex(common, method="ffill")

    a_buy_mean  = pd.concat([_ffill_align(s) for s in asset_buys],  axis=1).mean(axis=1)
    a_sell_mean = pd.concat([_ffill_align(s) for s in asset_sells], axis=1).mean(axis=1)
    r_buy_mean  = pd.concat([_ffill_align(s) for s in rel_buys],    axis=1).mean(axis=1)
    r_sell_mean = pd.concat([_ffill_align(s) for s in rel_sells],   axis=1).mean(axis=1)

    asset_net    = a_buy_mean - a_sell_mean
    rel_net      = r_buy_mean - r_sell_mean
    asset_net_ma = asset_net.rolling(MA_LEN).mean()
    rel_net_ma   = rel_net.rolling(MA_LEN).mean()
    return asset_net_ma, rel_net_ma, used


def current_and_slope(series: pd.Series):
    """Return (current, normalized_5d_slope, composite_score). composite =
    current * (1 + 0.5 * tanh(slope))."""
    if series is None:
        return None
    s = series.dropna()
    if len(s) < 10:
        return None
    current = float(s.iloc[-1])
    five    = float(s.iloc[-5])
    std30   = float(s.iloc[-30:].std()) if len(s) >= 30 else float(s.std())
    if not np.isfinite(std30) or std30 < 1e-6:
        std30 = 1.0
    slope = (current - five) / std30
    score = current * (1 + 0.5 * np.tanh(slope))
    return current, slope, score


# ─────────────────────────────────────────────────────────────────
# Data fetching layer
# ─────────────────────────────────────────────────────────────────

def fetch_interval_bulk(tickers, interval, chunk=50,
                         retries=3, pause=1.0, include_volume=False):
    """Bulk fetch tickers at a given yfinance interval. Returns dict
    {ticker: DataFrame[Open,High,Low,Close(,Volume)]}. Missing tickers absent."""
    period = PERIOD_BY_INTERVAL[interval]
    print(f"Fetching {len(tickers)} tickers @ {interval} (period={period})...", file=sys.stderr)
    out = {}
    remaining = list(tickers)
    while remaining:
        batch = remaining[:chunk]
        remaining = remaining[chunk:]
        for attempt in range(retries):
            try:
                df = yf.download(
                    batch, interval=interval, period=period,
                    auto_adjust=True, progress=False,
                    threads=True, group_by="column",
                )
                if df is None or df.empty:
                    time.sleep(pause * (attempt + 1))
                    continue
                if isinstance(df.columns, pd.MultiIndex):
                    has_vol = "Volume" in df.columns.get_level_values(0)
                    for t in batch:
                        try:
                            cols = {
                                "Open":  df["Open"][t],
                                "High":  df["High"][t],
                                "Low":   df["Low"][t],
                                "Close": df["Close"][t],
                            }
                            if include_volume and has_vol:
                                cols["Volume"] = df["Volume"][t]
                            sub = pd.DataFrame(cols).dropna(subset=["Close"])
                            if not sub.empty:
                                if sub.index.tz is not None:
                                    sub.index = sub.index.tz_localize(None)
                                out[t] = sub
                        except (KeyError, ValueError):
                            pass
                else:
                    # Single ticker path
                    t = batch[0]
                    sub = df[["Open","High","Low","Close"]].dropna(subset=["Close"])
                    if not sub.empty:
                        if sub.index.tz is not None:
                            sub.index = sub.index.tz_localize(None)
                        out[t] = sub
                break
            except Exception:
                time.sleep(pause * (attempt + 1))
        time.sleep(pause)
    print(f"  {interval}: got {len(out)}/{len(tickers)} tickers", file=sys.stderr)
    return out


def fetch_benchmark_bulk(intervals):
    """Fetch BENCHMARK at each interval. Returns dict interval->DataFrame."""
    out = {}
    for iv in intervals:
        period = PERIOD_BY_INTERVAL[iv]
        try:
            df = yf.download(BENCHMARK, interval=iv, period=period,
                             auto_adjust=True, progress=False, threads=False)
            if df is None or df.empty:
                print(f"  benchmark {iv}: empty", file=sys.stderr)
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open","High","Low","Close"]].dropna(subset=["Close"])
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            out[iv] = df
            print(f"  benchmark {iv}: {len(df)} bars", file=sys.stderr)
        except Exception as e:
            print(f"  benchmark {iv}: {e}", file=sys.stderr)
    return out


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def load_universe(include_rejected=False):
    """Load the not-all-rejected pool from /tmp/stars_aligned_*.csv."""
    rows = []
    for p in sorted(glob.glob("/tmp/stars_aligned_*.csv")):
        region = p.split("stars_aligned_")[-1].replace(".csv", "")
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        df["region"] = region
        if not include_rejected:
            mask = (
                (df.daily_label   != "Reject") |
                (df.weekly_label  != "Reject") |
                (df.monthly_label != "Reject")
            )
            df = df[mask]
        rows.append(df)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def is_native(t):
    if not isinstance(t, str):
        return False
    if "." not in t:
        # 5-letter tickers ending in F (foreign ordinary) or Y (unsponsored
        # ADR) are OTC pink-sheet wrappers of foreign primaries — thin books
        # whose stale prints flip PSAR constantly. The real listing carries
        # its own exchange suffix, so dropping these loses nothing.
        if len(t) == 5 and t[-1] in ("F", "Y"):
            return False
        return True
    suf = "." + t.rsplit(".", 1)[1]
    return suf in {
        ".L",".PA",".AS",".BR",".LS",".IR",".MI",".MC",".SW",".VI",
        ".DE",".ST",".OL",".CO",".HE",".AT",
        ".T",".JP",".HK",".SI",".KS",".KQ",".TW",".NS",".BO",
        ".SS",".SZ",".AX",".NZ",
    }


def main(tickers_override=None, skip_intraday=False, native_only=False):
    if tickers_override is not None:
        tickers = list(tickers_override)
        meta = pd.DataFrame({"ticker": tickers, "region": "test"})
    else:
        big = load_universe()
        if native_only:
            big = big[big.ticker.apply(is_native)].copy()
        big["best_rank"] = big[["daily_rank","weekly_rank","monthly_rank"]].max(axis=1)
        big = big.drop_duplicates(subset=["ticker"], keep="first")
        tickers = big.ticker.astype(str).tolist()
        meta = big[["ticker","region","best_rank"]].copy()
    print(f"Universe: {len(tickers)} tickers", file=sys.stderr)

    intervals = list({iv for _, iv, _, _ in TF_CONFIG})
    if skip_intraday:
        intervals = [iv for iv in intervals if iv not in {"30m", "60m"}]
        print("Skipping intraday TFs (30m, 60m)", file=sys.stderr)
    print(f"Intervals to fetch: {intervals}", file=sys.stderr)

    bench = fetch_benchmark_bulk(intervals)

    per_interval_bars = {}
    for iv in intervals:
        per_interval_bars[iv] = fetch_interval_bulk(tickers, iv)

    rows = []
    for i, t in enumerate(tickers):
        try:
            asset_ma, rel_ma, used_tfs = composites_for_ticker(t, per_interval_bars, bench)
            a = current_and_slope(asset_ma)
            r = current_and_slope(rel_ma)
            if a is None and r is None:
                continue
            row = {
                "ticker":           t,
                "n_active_tfs":     len(used_tfs),
                "used_tfs":         ",".join(used_tfs),
            }
            if a is not None:
                row["asset_net_ma"]       = a[0]
                row["asset_slope_norm"]   = a[1]
                row["asset_score"]        = a[2]
            if r is not None:
                row["rel_net_ma"]         = r[0]
                row["rel_slope_norm"]     = r[1]
                row["rel_score"]          = r[2]
            rows.append(row)
        except Exception as e:
            pass
        if (i + 1) % 250 == 0:
            print(f"  scored {i+1}/{len(tickers)}", file=sys.stderr)

    out = pd.DataFrame(rows)
    if out.empty:
        print("No results.")
        return out
    out = out.merge(meta, on="ticker", how="left")

    # Combined ranking
    out["combined_score"] = out.get("asset_score", 0).fillna(0) + out.get("rel_score", 0).fillna(0)

    out.to_csv("/tmp/mtf_psar_rank.csv", index=False)
    print(f"Wrote /tmp/mtf_psar_rank.csv ({len(out)} rows)", file=sys.stderr)

    cols_show = ["ticker", "region", "n_active_tfs",
                 "asset_net_ma", "asset_slope_norm", "asset_score",
                 "rel_net_ma", "rel_slope_norm", "rel_score",
                 "combined_score"]
    cols_show = [c for c in cols_show if c in out.columns]

    print("\n=== TOP 30 BY ASSET NET MA SCORE ===")
    top_a = out.sort_values("asset_score", ascending=False).head(30)
    print(top_a[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print("\n=== TOP 30 BY RELATIVE NET MA SCORE ===")
    top_r = out.sort_values("rel_score", ascending=False).head(30)
    print(top_r[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print("\n=== TOP 30 BY COMBINED ===")
    top_c = out.sort_values("combined_score", ascending=False).head(30)
    print(top_c[cols_show].to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    return out


def main_expanded(batch_size=1500, out_path="/tmp/mtf_psar_rank_full.csv"):
    """Expanded scan: the FULL native universe (all rows, including
    six-school rejects), deduped to one listing per company by native
    exchange suffix. Processes in ticker batches so memory stays bounded
    (~600MB vs 2GB+ monolithic) and appends results incrementally so an
    interrupted run resumes where it left off."""
    import gc
    import os

    big = load_universe(include_rejected=True)
    big = big[big.ticker.apply(is_native)].copy()
    big["best_rank"] = big[["daily_rank", "weekly_rank", "monthly_rank"]].max(axis=1)
    big = big.drop_duplicates(subset=["ticker"], keep="first")
    meta = big[["ticker", "region", "best_rank"]].copy()
    tickers = big.ticker.astype(str).tolist()

    done = set()
    if os.path.exists(out_path):
        try:
            done = set(pd.read_csv(out_path).ticker.astype(str))
        except Exception:
            pass
    todo = [t for t in tickers if t not in done]
    print(f"Expanded universe: {len(tickers)} native tickers "
          f"({len(done)} already done, {len(todo)} to go)", file=sys.stderr)

    intervals = list({iv for _, iv, _, _ in TF_CONFIG})
    bench = fetch_benchmark_bulk(intervals)

    meta_map = meta.set_index("ticker")
    n_batches = (len(todo) + batch_size - 1) // batch_size
    for bi in range(n_batches):
        batch = todo[bi * batch_size:(bi + 1) * batch_size]
        print(f"--- batch {bi+1}/{n_batches} ({len(batch)} tickers) ---", file=sys.stderr)
        per_interval = {}
        for iv in intervals:
            per_interval[iv] = fetch_interval_bulk(batch, iv)

        rows = []
        for t in batch:
            try:
                asset_ma, rel_ma, used_tfs = composites_for_ticker(t, per_interval, bench)
                a = current_and_slope(asset_ma)
                r = current_and_slope(rel_ma)
                if a is None and r is None:
                    continue
                row = {"ticker": t, "n_active_tfs": len(used_tfs)}
                if a is not None:
                    row.update(asset_net_ma=a[0], asset_slope_norm=a[1], asset_score=a[2])
                if r is not None:
                    row.update(rel_net_ma=r[0], rel_slope_norm=r[1], rel_score=r[2])
                if t in meta_map.index:
                    row["region"] = meta_map.loc[t, "region"]
                    row["best_rank"] = meta_map.loc[t, "best_rank"]
                row["combined_score"] = (row.get("asset_score") or 0) + (row.get("rel_score") or 0)
                rows.append(row)
            except Exception:
                pass

        if rows:
            chunk_df = pd.DataFrame(rows)
            header = not os.path.exists(out_path)
            chunk_df.to_csv(out_path, mode="a", header=header, index=False)
            print(f"  appended {len(rows)} rows -> {out_path}", file=sys.stderr)
        del per_interval
        gc.collect()

    print(f"Expanded scan complete -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--test":
        # Quick sanity check on a small ticker set
        TEST = ["AAPL", "NVDA", "META", "HST", "PSMT", "MAC", "LSTR", "IHG.L", "TSLA", "MSFT"]
        main(tickers_override=TEST)
    elif args and args[0] == "--no-intraday":
        main(skip_intraday=True)
    elif args and args[0] == "--expanded":
        main_expanded()
    else:
        main()
