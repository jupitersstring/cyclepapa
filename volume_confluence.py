#!/usr/bin/env python3
"""
Volume-bandpass <-> seasonal-return confluence + PB curve plots.

(a) Joins the volume bandpass crossings (vol_bandpass_full.csv) with the
    week-of-year seasonal scan (week22_full.csv): which names are inflecting
    volume UP *and* sit in a favourable seasonal LONG state (or DOWN + SHORT).
(b) Plots the 4-band Ehlers volume bandpass (daily) for a set of names, marking
    the zero line and the most recent zero crossing.
(c) Flags bar-0 ("inflected today") crossings.

Usage:
    python3 volume_confluence.py                 # tables + plots for confluence set
    python3 volume_confluence.py --plot P,AM,CPRI
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from volume_bandpass import ehlers_bandpass, BANDS, CACHE_DIR

VOL_CSV = os.path.join(CACHE_DIR, "vol_bandpass_full.csv")
SEAS_CSV = os.path.join(CACHE_DIR, "week22_full.csv")
DAILY_PKL = os.path.join(CACHE_DIR, "ohlcv_1d_20y_400.pkl")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts")


# --------------------------------------------------------------------------- #
# (a) confluence
# --------------------------------------------------------------------------- #
def confluence() -> pd.DataFrame:
    vol = pd.read_csv(VOL_CSV)
    seas = pd.read_csv(SEAS_CSV)

    fresh = vol[vol["fresh"]].copy()
    # net volume signal per symbol: +1 per UP cross, -1 per DOWN (weight by band rank)
    bw = {"B1": 1.0, "B2": 1.5, "B3": 2.0, "B4": 2.5}
    fresh["w"] = fresh["band"].map(bw) * np.where(fresh["direction"] == "UP", 1, -1)
    vsig = (fresh.groupby("symbol")
            .agg(vol_net=("w", "sum"),
                 vol_hits=("band", "count"),
                 vol_tfs=("tf", lambda s: "+".join(sorted(set(s)))),
                 vol_bands=("band", lambda s: ",".join(sorted(set(s)))))
            .reset_index())

    seas_s = seas[["symbol", "sector", "direction", "score",
                   "composite_long", "composite_short", "mean_ret",
                   "win_rate", "persistence", "n"]].rename(
        columns={"direction": "seas_dir", "score": "seas_score"})

    m = vsig.merge(seas_s, on="symbol", how="inner")
    m["vol_dir"] = np.where(m["vol_net"] > 0, "UP",
                            np.where(m["vol_net"] < 0, "DOWN", "MIXED"))

    # agreement: volume UP + seasonal LONG  -> bullish confluence
    #            volume DOWN + seasonal SHORT -> bearish confluence
    bull = m[(m["vol_dir"] == "UP") & (m["seas_dir"] == "LONG")].copy()
    bear = m[(m["vol_dir"] == "DOWN") & (m["seas_dir"] == "SHORT")].copy()
    bull["conf_score"] = bull["seas_score"] + bull["vol_net"].abs() * 0.5
    bear["conf_score"] = bear["seas_score"] + bear["vol_net"].abs() * 0.5
    return (bull.sort_values("conf_score", ascending=False),
            bear.sort_values("conf_score", ascending=False), m)


def _print_confluence(bull, bear):
    def block(title, t):
        print(f"\n{'='*100}\n{title}\n{'='*100}")
        print(f"{'Sym':<7}{'Sector':<22}{'Conf':>6}{'SeasScore':>10}{'VolNet':>8}"
              f"{'VolBands':>16}{'AvgRet':>8}{'Win%':>6}{'n':>4}")
        for _, r in t.head(20).iterrows():
            print(f"{r['symbol']:<7}{str(r['sector'])[:21]:<22}{r['conf_score']:>6.2f}"
                  f"{r['seas_score']:>10.2f}{r['vol_net']:>8.1f}"
                  f"{str(r['vol_bands']):>16}"
                  f"{r['mean_ret']*100:>+7.1f}%{r['win_rate']*100:>5.0f}%{int(r['n']):>4}")
    block("BULLISH confluence  (volume inflecting UP  +  seasonal LONG state)", bull)
    block("BEARISH confluence  (volume inflecting DOWN +  seasonal SHORT state)", bear)


# --------------------------------------------------------------------------- #
# (b) plots
# --------------------------------------------------------------------------- #
def plot_names(symbols: list[str], lookback: int = 500) -> list[str]:
    os.makedirs(OUT_DIR, exist_ok=True)
    panel = pd.read_pickle(DAILY_PKL)
    paths = []
    colors = {"B1": "#1f77b4", "B2": "#d62728", "B3": "#9467bd", "B4": "#000000"}
    # B4 (1200/2400) barely completes one cycle in 20yr of daily bars -> it is
    # dominated by warmup/secular drift, so it is excluded from the chart.
    plot_bands = [b for b in BANDS if b[0] != "B4"]
    for sym in symbols:
        if sym not in panel.columns.get_level_values(0):
            print(f"  [plot] {sym}: no data")
            continue
        sub = panel[sym].dropna(how="all")
        vol = sub["Volume"].astype(float)
        v = np.log1p(vol.to_numpy())
        idx = vol.index

        fig, ax = plt.subplots(figsize=(13, 6))
        ymax = 0.0
        for name, flen, slen in plot_bands:
            if len(v) < slen:
                continue
            pb = ehlers_bandpass(v, flen, slen)
            sd = np.std(pb[slen:]) or 1.0
            series = pd.Series(pb / sd, index=idx).iloc[-lookback:]
            ymax = max(ymax, float(np.nanpercentile(np.abs(series.values), 99)))
            ax.plot(series.index, series.values, color=colors[name],
                    linewidth=1.5, label=f"{name} {flen}/{slen}")
            # mark most recent zero crossing of this band within the window
            sgn = np.sign(series.values)
            xs = np.where(sgn[1:] != sgn[:-1])[0]
            if xs.size:
                ci = xs[-1] + 1
                ax.scatter(series.index[ci], series.values[ci], color=colors[name],
                           s=45, zorder=5, edgecolor="white", linewidth=0.8)
        ax.axhline(0, color="0.4", linewidth=1)
        if ymax > 0:
            ax.set_ylim(-ymax * 1.2, ymax * 1.2)
        ax.set_title(f"{sym} — Ehlers volume bandpass (daily, log-volume, normalized; dots = latest zero-cross)")
        ax.legend(loc="upper left", fontsize=8, ncol=3)
        ax.grid(alpha=0.25)
        p = os.path.join(OUT_DIR, f"vol_bandpass_{sym}.png")
        fig.tight_layout()
        fig.savefig(p, dpi=110)
        plt.close(fig)
        paths.append(p)
        print(f"  [plot] {sym} -> {p}")
    return paths


# --------------------------------------------------------------------------- #
# (c) today-only crossings
# --------------------------------------------------------------------------- #
def today_only():
    vol = pd.read_csv(VOL_CSV)
    t0 = vol[vol["bars_ago"] == 0]
    print(f"\n{'='*70}\nINFLECTED ON THE LATEST BAR (bars_ago == 0)\n{'='*70}")
    for tf in ["daily", "weekly"]:
        for d in ["UP", "DOWN"]:
            s = t0[(t0.tf == tf) & (t0.direction == d)]
            if s.empty:
                continue
            names = ", ".join(sorted(s["symbol"].unique()))
            print(f"  {tf:<7} {d:<5} ({len(s['symbol'].unique())}): {names}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plot", default=None, help="comma-separated symbols to plot")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    bull, bear, _ = confluence()
    _print_confluence(bull, bear)
    today_only()

    if not args.no_plot:
        if args.plot:
            names = [s.strip().upper() for s in args.plot.split(",")]
        else:
            names = ["P", "AM", "CPRI", "BBWI", "AAL", "DINO", "CHRD",
                     "WCC", "OC", "EXEL", "JAZZ"]
        print(f"\n[plots] generating {len(names)} charts ...")
        paths = plot_names(names)
        print("PLOTS:" + ";".join(paths))


if __name__ == "__main__":
    main()
