"""Leledc exhaustion levels (InSilico "LeveLeledc", after Leledc Exhaustion Bar) on
WEEKLY and MONTHLY bars -> leledc_levels.csv (lel_w_*, lel_m_*).

A faithful port of the Pine v4 script (defaults: swing length 40, exhaustion
bar count 10):

    bindex += 1 when close > close[4]      (counts persist until a signal)
    sindex += 1 when close < close[4]
    SELL exhaustion (-1): bindex > bars and close < open and high >= highest(high, length)
                          -> bindex = 0
    else BUY exhaustion (+1): sindex > bars and close > open and low <= lowest(low, length)
                          -> sindex = 0
    resistance = high of the latest SELL-exhaustion bar (carried forward)
    support    = low  of the latest BUY-exhaustion bar  (carried forward)

highest / lowest include the current bar, as in Pine. Bars come from the
FMP weekly panel (split- and dividend-adjusted OHLC, W-FRI), with the Yahoo
weekly fill for names FMP lacks; monthly bars are built from the weekly ones
(open = first week's open, high = max, low = min, close = last week's close).
Levels are in the same adjusted price terms as the close, so the distances
below are exact.

Per timeframe (w = weekly, m = monthly):
  lel_{tf}_signal        last exhaustion signal: +1 buy (downside exhausted), -1 sell
  lel_{tf}_bars_since    bars since that signal
  lel_{tf}_resistance    latest resistance level (adjusted price)
  lel_{tf}_support       latest support level (adjusted price)
  lel_{tf}_res_dist      close / resistance - 1  (negative = below resistance)
  lel_{tf}_sup_dist      close / support - 1     (positive = above support)
  lel_{tf}_above_res     1 when the close is above the latest resistance (exhaustion high reclaimed)
  lel_{tf}_below_sup     1 when the close is below the latest support (exhaustion low lost)
  lel_{tf}_asof          date of the last bar used
"""
from __future__ import annotations

import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

OUT = "leledc_levels.csv"
LENGTH, BARS = 40, 10


def leledc(o, h, l, c, length=LENGTH, bars=BARS):
    n = len(c)
    sig = np.zeros(n, dtype=np.int8)
    res = np.full(n, np.nan); sup = np.full(n, np.nan)
    bi = si = 0
    r_prev = s_prev = np.nan
    for i in range(n):
        if i >= 4:
            if c[i] > c[i - 4]:
                bi += 1
            if c[i] < c[i - 4]:
                si += 1
        lo = max(0, i - length + 1)
        s = 0
        if bi > bars and c[i] < o[i] and h[i] >= h[lo:i + 1].max():
            bi = 0; s = -1
        elif si > bars and c[i] > o[i] and l[i] <= l[lo:i + 1].min():
            si = 0; s = 1
        sig[i] = s
        if s != 0 and c[i] < o[i]:
            r_prev = h[i]
        if s != 0 and c[i] > o[i]:
            s_prev = l[i]
        res[i] = r_prev; sup[i] = s_prev
    return sig, res, sup


def summarise(bars_df: pd.DataFrame, tf: str) -> dict:
    d = bars_df.dropna(subset=["open", "high", "low", "close"])
    d = d[(d["high"] > 0) & (d["low"] > 0) & (d["close"] > 0)]
    if len(d) < 8:
        return {}
    o, h, l, c = (d[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sig, res, sup = leledc(o, h, l, c)
    out = {f"lel_{tf}_asof": pd.Timestamp(d.index[-1]).date().isoformat()}
    nz = np.flatnonzero(sig)
    if len(nz):
        out[f"lel_{tf}_signal"] = float(sig[nz[-1]])
        out[f"lel_{tf}_bars_since"] = float(len(c) - 1 - nz[-1])
    r, s_, cl = res[-1], sup[-1], c[-1]
    if np.isfinite(r):
        out[f"lel_{tf}_resistance"] = r
        out[f"lel_{tf}_res_dist"] = cl / r - 1
        out[f"lel_{tf}_above_res"] = float(cl > r)
    if np.isfinite(s_):
        out[f"lel_{tf}_support"] = s_
        out[f"lel_{tf}_sup_dist"] = cl / s_ - 1
        out[f"lel_{tf}_below_sup"] = float(cl < s_)
    return out


def one(args):
    sym, g = args
    g = g.set_index("week").sort_index()
    rec = {"symbol": sym}
    rec.update(summarise(g, "w"))
    m = g.resample("ME").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    rec.update(summarise(m, "m"))
    return rec


def main(workers: int = 4) -> None:
    cols = ["symbol", "week", "open", "high", "low", "close"]
    px = pd.read_parquet("fmp_weekly_prices.parquet", columns=cols)
    if os.path.exists("yahoo_weekly_prices.parquet"):
        yh = pd.read_parquet("yahoo_weekly_prices.parquet", columns=cols)
        yh = yh[~yh["symbol"].isin(set(px["symbol"].unique()))]
        px = pd.concat([px, yh], ignore_index=True)
    px["week"] = pd.to_datetime(px["week"])
    groups = [(s, g[["week", "open", "high", "low", "close"]]) for s, g in px.groupby("symbol", sort=False)]
    del px
    print(f"leledc: {len(groups)} symbols", flush=True)
    with Pool(workers) as pool:
        recs = pool.map(one, groups, chunksize=200)
    out = pd.DataFrame(recs)
    tmp = OUT + ".tmp"
    out.to_csv(tmp, index=False, float_format="%.6g"); os.replace(tmp, OUT)
    print(f"wrote {OUT}: {len(out)} rows", flush=True)


if __name__ == "__main__":
    main()
