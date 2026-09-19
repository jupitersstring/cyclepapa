"""Test which cumulative volume-flow line best captures 'demand > supply' on a
weekly (larger) timeframe, and whether a cumulative-line BREAKOUT — especially
one that LEADS price — predicts forward returns.

Uses the 10y weekly OHLCV panel in /tmp/ema_bars (446 liquid global names).
Point-in-time: signals at week t, forward returns t+k. No look-ahead.

Lines tested:
  OBV  On-Balance Volume        : cum( sign(dClose) * V )                 (Granville)
  ADL  Accumulation/Distribution: cum( ((2C-H-L)/(H-L)) * V )            (Chaikin)
  VPT  Volume-Price Trend       : cum( V * pctChange(Close) )
  CMF  Chaikin Money Flow (20)  : rolling money-flow-volume / rolling volume

Signals per line (52-week window):
  *_brk   : line at a new 52w high (cumulative breakout = sustained net buying)
  divergence classes vs price 52w-high:
     LEAD    line new-high but price NOT new-high  (accumulation ahead of price)
     CONFIRM line new-high AND price new-high      (demand + price together)
     LAGGARD price new-high but line NOT new-high  (breakout on weak flow)
"""
import glob, os
import numpy as np
import pandas as pd

BARS = "/tmp/ema_bars"
FWD = [4, 13, 26, 52]
W = 52


def lines(b):
    c, h, l, v = b.Close, b.High, b.Low, b.Volume
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    rng = (h - l).replace(0, np.nan)
    mfm = ((2 * c - h - l) / rng).fillna(0)
    adl = (mfm * v).cumsum()
    vpt = (v * c.pct_change().fillna(0)).cumsum()
    mfv = mfm * v
    cmf = mfv.rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    return obv, adl, vpt, cmf


def newhigh(s, w):
    # True when s is >= its max over the PRIOR w bars (no look-ahead: shift 1)
    return s >= s.shift(1).rolling(w).max()


def panel():
    rows = []
    for f in glob.glob(os.path.join(BARS, "*.csv")):
        t = os.path.basename(f)[:-4]
        try:
            b = pd.read_csv(f, index_col=0, parse_dates=True)
        except Exception:
            continue
        b = b.dropna(subset=["Close", "Volume"])
        if len(b) < W + 60:
            continue
        obv, adl, vpt, cmf = lines(b)
        d = pd.DataFrame(index=b.index)
        d["obv_brk"] = newhigh(obv, W)
        d["adl_brk"] = newhigh(adl, W)
        d["vpt_brk"] = newhigh(vpt, W)
        d["cmf_pos"] = cmf > 0.05
        price_hi = newhigh(b.Close, W)
        d["price_hi"] = price_hi
        # OBV-vs-price divergence classes
        cls = pd.Series("none", index=b.index)
        cls = cls.mask(d.obv_brk & ~price_hi, "LEAD")
        cls = cls.mask(d.obv_brk & price_hi, "CONFIRM")
        cls = cls.mask(~d.obv_brk & price_hi, "LAGGARD")
        d["obv_div"] = cls
        for k in FWD:
            d[f"fwd{k}"] = b.Close.shift(-k) / b.Close - 1
        d = d[d["fwd13"].notna()]
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def stat(g):
    return pd.Series({"n": len(g), "fwd13_mean%": 100 * g.fwd13.mean(),
                      "fwd13_hit%": 100 * (g.fwd13 > 0).mean(),
                      "fwd26_mean%": 100 * g.fwd26.mean(),
                      "fwd52_mean%": 100 * g.fwd52.mean(),
                      "fwd13_p05%": 100 * g.fwd13.quantile(0.05)})


def main():
    p = panel()
    base = 100 * p.fwd13.mean()
    print(f"Weekly panel: {len(p):,} obs. Baseline +13w = {base:.2f}%\n")

    print("=== cumulative-line BREAKOUT (line at new 52w high) — +13w edge vs baseline ===")
    for col in ["obv_brk", "adl_brk", "vpt_brk", "cmf_pos", "price_hi"]:
        on = p[p[col]]; off = p[~p[col]]
        print(f"  {col:9} ON n={len(on):>7,} +13w={100*on.fwd13.mean():6.2f}% "
              f"hit={100*(on.fwd13>0).mean():4.1f}%  |  edge={100*on.fwd13.mean()-base:+.2f}%  "
              f"(OFF {100*off.fwd13.mean():.2f}%)")

    print("\n=== OBV-vs-PRICE divergence (does OBV LEADING price pay?) ===")
    dv = p.groupby("obv_div").apply(stat).reindex(["LEAD", "CONFIRM", "LAGGARD", "none"])
    dv["edge13%"] = dv["fwd13_mean%"] - base
    print(dv.round(2).to_string())

    print("\n=== ADL leading price (same test, Chaikin line) ===")
    p["adl_div"] = np.where(p.adl_brk & ~p.price_hi, "LEAD",
                     np.where(p.adl_brk & p.price_hi, "CONFIRM",
                     np.where(~p.adl_brk & p.price_hi, "LAGGARD", "none")))
    ad = p.groupby("adl_div").apply(stat).reindex(["LEAD", "CONFIRM", "LAGGARD", "none"])
    ad["edge13%"] = ad["fwd13_mean%"] - base
    print(ad.round(2).to_string())


if __name__ == "__main__":
    main()
