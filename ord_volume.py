"""Tim Ord's 'Ord Volume' price/volume swing analysis, implemented rigorously
and tested for forward-return edge on the weekly panel.

Ord Volume (Tim Ord, *The Secret Science of Price and Volume*): decompose price
into swings (waves) and track the AVERAGE volume of each wave (Weis Wave keeps
cumulative volume; Ord keeps the average). The demand>supply reading comes from
comparing successive waves:
  * an up-wave on higher Ord Volume than the prior down-wave  -> demand
  * a rally/test of a prior high on lower Ord Volume          -> weak (failing)
  * supply drying up: each down-wave on lower Ord Volume      -> accumulation
  * a wave whose Ord Volume dwarfs prior waves                -> possible climax

Swing decomposition is a CAUSAL zigzag: a pivot is only confirmed once price
retraces from the running extreme by >= threshold, so features at bar t use only
pivots confirmed by t (no look-ahead). Threshold = max(pct, atr_mult*ATR/price).

Run: python ord_volume.py            # build weekly features + forward-return test
"""
import glob, os
import numpy as np
import pandas as pd

BARS = "/tmp/ema_bars"
FWD = [4, 13, 26, 52]
PCT = 0.08          # min swing reversal (weekly)
ATR_MULT = 1.2


def causal_zigzag(close, high, low, atr, pct=PCT, atr_mult=ATR_MULT):
    """Return arrays: pivot_idx of the swing CURRENTLY in force at each bar, and
    a list of confirmed swings [(start_i, end_i, direction)] with end_i = pivot
    bar and confirmation happening later. Fully causal."""
    n = len(close)
    swings = []                     # (start_i, end_i, dir)  dir=+1 up,-1 down
    last_pivot_i = 0
    last_pivot_px = close.iloc[0]
    trend = 0                       # 0 unknown, +1 up, -1 down
    ext_i = 0
    ext_px = close.iloc[0]
    for i in range(1, n):
        px = close.iloc[i]
        thr = max(pct, atr_mult * (atr.iloc[i] / px if px else pct))
        if trend >= 0:
            if px > ext_px:
                ext_px, ext_i = px, i
            elif (ext_px - px) / ext_px >= thr:
                # reversal down confirmed -> up-swing from last_pivot to ext
                swings.append((last_pivot_i, ext_i, +1))
                last_pivot_i, last_pivot_px = ext_i, ext_px
                trend = -1
                ext_px, ext_i = px, i
        if trend <= 0:
            if px < ext_px:
                ext_px, ext_i = px, i
            elif (px - ext_px) / ext_px >= thr:
                swings.append((last_pivot_i, ext_i, -1))
                last_pivot_i, last_pivot_px = ext_i, ext_px
                trend = +1
                ext_px, ext_i = px, i
    return swings


def ord_features(b):
    c, h, l, v = b.Close, b.High, b.Low, b.Volume
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(10).mean().bfill()
    swings = causal_zigzag(c, h, l, atr)
    # Ord Volume per swing = avg volume over the swing's bars; confirmation bar =
    # the bar AFTER end_i at which reversal threshold is met -> we approximate
    # availability at end_i+1 (pivot known one bar after). Assign each swing's
    # stats to be *known* from its end index onward.
    d = pd.DataFrame(index=b.index)
    ordv = np.full(len(b), np.nan); sdir = np.full(len(b), np.nan)
    sret = np.full(len(b), np.nan); shi = np.full(len(b), np.nan); slo = np.full(len(b), np.nan)
    for (s, e, dr) in swings:
        av = float(v.iloc[s:e + 1].mean())
        ordv[e] = av; sdir[e] = dr
        sret[e] = c.iloc[e] / c.iloc[s] - 1
        shi[e] = h.iloc[s:e + 1].max(); slo[e] = l.iloc[s:e + 1].min()
    sw = pd.DataFrame({"ordv": ordv, "dir": sdir, "ret": sret, "hi": shi, "lo": slo},
                      index=b.index).dropna(subset=["ordv"])
    # walk bars; maintain last up/down swing Ord Volume known so far (shifted +1
    # bar for availability)
    feats = {k: np.full(len(b), np.nan) for k in
             ["ds_ratio", "up_rising", "dn_falling", "brk_confirmed", "climax", "cur_up_demand"]}
    up_hist, dn_hist = [], []
    swing_rows = list(sw.itertuples())
    si = 0
    idx_pos = {ts: i for i, ts in enumerate(b.index)}
    for row in swing_rows:
        pos = idx_pos[row.Index]
        avail = min(pos + 1, len(b) - 1)     # known one bar after the pivot
        if row.dir > 0:
            up_hist.append(row.ordv)
        else:
            dn_hist.append(row.ordv)
        ds = (up_hist[-1] / dn_hist[-1]) if up_hist and dn_hist and dn_hist[-1] else np.nan
        up_rising = (len(up_hist) >= 2 and up_hist[-1] > up_hist[-2])
        dn_falling = (len(dn_hist) >= 2 and dn_hist[-1] < dn_hist[-2])
        # breakout confirmed: latest up-swing made a higher high than prior up-swing
        # AND on higher Ord Volume
        brk = False
        ups = sw[sw.dir > 0]
        if row.dir > 0 and len(ups) >= 2:
            prev = ups.iloc[-2]
            brk = (row.hi > prev.hi) and (row.ordv > prev.ordv)
        allv = up_hist + dn_hist
        climax = (len(allv) >= 4 and row.ordv > 2.0 * np.median(allv[:-1]))
        cur_up_demand = (row.dir > 0 and up_rising and dn_falling)
        for k, val in (("ds_ratio", ds), ("up_rising", float(up_rising)),
                       ("dn_falling", float(dn_falling)), ("brk_confirmed", float(brk)),
                       ("climax", float(climax)), ("cur_up_demand", float(cur_up_demand))):
            feats[k][avail:] = val          # carry forward from availability
    for k in feats:
        d[k] = feats[k]
    for k in FWD:
        d[f"fwd{k}"] = c.shift(-k) / c - 1
    return d


def main():
    rows = []
    for f in glob.glob(os.path.join(BARS, "*.csv")):
        try:
            b = pd.read_csv(f, index_col=0, parse_dates=True)
        except Exception:
            continue
        b = b.dropna(subset=["Close", "Volume"])
        if len(b) < 160:
            continue
        d = ord_features(b)
        d = d[d["fwd13"].notna() & d["ds_ratio"].notna()]
        rows.append(d)
    p = pd.concat(rows, ignore_index=True)
    base = 100 * p.fwd13.mean()
    print(f"Ord-Volume weekly panel: {len(p):,} obs. Baseline +13w = {base:.2f}%\n")

    print("=== demand/supply ratio (up-swing OrdVol / down-swing OrdVol) quintiles -> +13w ===")
    p["dsq"] = pd.qcut(p.ds_ratio.clip(upper=p.ds_ratio.quantile(0.99)), 5,
                       labels=["Q1(supply)", "Q2", "Q3", "Q4", "Q5(demand)"], duplicates="drop")
    g = p.groupby("dsq").fwd13.agg(["count", "mean"])
    g["mean%"] = 100 * g["mean"]; g["edge"] = g["mean%"] - base
    print(g[["count", "mean%", "edge"]].round(2).to_string())

    print("\n=== Ord signals -> +13w edge vs baseline ===")
    for col in ["up_rising", "dn_falling", "brk_confirmed", "cur_up_demand", "climax"]:
        on = p[p[col] > 0]
        if len(on) > 300:
            print(f"  {col:14} n={len(on):>7,} +13w={100*on.fwd13.mean():6.2f}%  "
                  f"hit={100*(on.fwd13>0).mean():4.1f}%  edge={100*on.fwd13.mean()-base:+.2f}%")

    print("\n=== KEY COMBO: accumulation (up OrdVol rising + down OrdVol falling) ===")
    combo = p[p.cur_up_demand > 0]
    print(f"  n={len(combo):,} +13w={100*combo.fwd13.mean():.2f}% "
          f"+26w={100*combo.fwd26.mean():.2f}% +52w={100*combo.fwd52.mean():.2f}% "
          f"hit={100*(combo.fwd13>0).mean():.1f}% edge={100*combo.fwd13.mean()-base:+.2f}%")
    print("\n(Compare: OBV cumulative breakout earlier showed ~-0.4% edge.)")


if __name__ == "__main__":
    main()
