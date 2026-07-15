"""Render weekly Darvas2 boxes + breakouts on real cached tickers for a visual
eye-check. Scans a universe's daily cache, resamples to weekly, runs the robust
detector, and plots a grid of breakouts and pre-breakout coils.

Usage: python3 eyecheck_darvas.py [universe] [out.png]
"""
import sys, pickle
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from momentum_rank import detect_darvas2_box

UNI = sys.argv[1] if len(sys.argv) > 1 else "us-all"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/eyecheck_darvas.png"

state = pickle.load(open(f"/tmp/cyclepapa_dl_{UNI}_daily_2y.pkl", "rb"))
frames = state.get("frames", {})

def weekly_of(dfd):
    dfd = dfd.copy()
    dfd.index = pd.to_datetime(dfd.index)
    w = dfd.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min",
                                   "Close":"last","Volume":"sum"}).dropna()
    return w

def tag(b, w):
    """Recompute the darvas2 booleans exactly as the pipeline does."""
    hgt = b["darvas2_box_height_pct"]; ln = b["darvas2_box_length_weeks"]
    dist = b["darvas2_dist_from_top_pct"]; fresh = b["darvas2_breakout_freshness_w"]
    at52 = b["darvas2_ceiling_at_52w_high"]
    breakout = (dist > 0 and dist <= 10 and fresh is not None and 0 <= fresh <= 4
                and at52 and 3 <= hgt <= 35)
    coil = (at52 and hgt <= 12 and ln >= 4 and -3 <= dist <= 0 and fresh is None)
    return breakout, coil

breakouts, coils = [], []
for t, dfd in frames.items():
    try:
        if "Close" not in dfd.columns or len(dfd) < 260:
            continue
        w = weekly_of(dfd)
        if len(w) < 30:
            continue
        b = detect_darvas2_box(w)
        if not b:
            continue
        bo, co = tag(b, w)
        if bo:
            breakouts.append((t, w, b))
        elif co:
            coils.append((t, w, b))
    except Exception:
        continue

# Prefer higher-priced, liquid names for a cleaner eye-check
def score(item):
    t, w, b = item
    return float(w["Close"].iloc[-1]) * float(w["Volume"].tail(20).mean())
breakouts.sort(key=score, reverse=True)
coils.sort(key=score, reverse=True)
print(f"{UNI}: {len(breakouts)} breakouts, {len(coils)} coils detected")

picks = [("BREAKOUT", x) for x in breakouts[:5]] + [("COIL", x) for x in coils[:5]]
if not picks:
    print("nothing to plot"); sys.exit(0)

fig, axes = plt.subplots(len(picks), 1, figsize=(13, 3.1*len(picks)))
if len(picks) == 1: axes = [axes]
for ax, (kind, (t, w, b)) in zip(axes, picks):
    close = w["Close"].values; x = np.arange(len(w))
    ax.plot(x, close, color="#1a1a1a", lw=1.1)
    ax.fill_between(x, w["Low"].values, w["High"].values, color="#cccccc", alpha=0.35, lw=0)
    top = b["darvas2_box_top"]; bot = b["darvas2_box_bottom"]
    ln = int(b["darvas2_box_length_weeks"]); ceil_bar = len(w)-1-ln
    # box rectangle from ceiling bar to now
    ax.add_patch(Rectangle((ceil_bar, bot), (len(w)-1-ceil_bar), top-bot,
                            fill=False, edgecolor="#A51C30", lw=1.6))
    ax.axhline(top, color="#A51C30", ls="--", lw=0.8, alpha=0.7)
    fresh = b["darvas2_breakout_freshness_w"]
    if fresh is not None:
        bx = len(w)-1-int(fresh)
        ax.scatter([bx],[close[bx]], marker="^", s=90, color="#0a7d34", zorder=5,
                   label=f"breakout {int(fresh)}w ago")
    ax.set_title(f"[{kind}] {t}  | box {ln}w  height {b['darvas2_box_height_pct']:.1f}%  "
                 f"dist_top {b['darvas2_dist_from_top_pct']:+.1f}%  "
                 f"fresh={fresh}  volexp={b['darvas2_vol_expansion']}",
                 fontsize=9, loc="left")
    ax.margins(x=0.01); ax.grid(alpha=0.2)
plt.tight_layout()
plt.savefig(OUT, dpi=95, bbox_inches="tight")
print("wrote", OUT)
