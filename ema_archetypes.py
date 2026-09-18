"""Return archetypes from multi-timeframe weekly moving averages + volume.

For each (ticker, week) we compute a state vector from the 10/20/50/200-week
EMAs — their stack order (crosses), slopes (1st derivative), acceleration
(2nd derivative), compression, and price location — plus a weekly VOLUME
regime (RVOL spike tier + up/down accumulation). Each observation is labelled
with a rule-based ARCHETYPE, then joined to its realised FORWARD RETURNS
(+4/+13/+26/+52 weeks). Aggregating gives, per archetype (and per
archetype x volume regime): mean/median forward return, hit-rate, and a
downside percentile — i.e. which MA configurations, and which volume
conditions on top of them, actually pay forward.

Optionally uses Ehlers' Super Smoother in place of EMAs (--ehlers): a
2-pole low-lag filter (Ehlers 2004) that tracks trend with far less lag and
noise than an EMA of the same period.

Design notes:
  * Everything is point-in-time: features at t use only data <= t; returns
    use t+k. No look-ahead.
  * Fetch is resume-safe — each ticker's weekly OHLCV is cached under
    /tmp/ema_bars/ so a rate-limit/reset only costs the un-fetched names.
  * Slopes are normalised (%/week) so they compare across price levels;
    acceleration is the change in that normalised slope.

Usage:
  python ema_archetypes.py --fetch                 # fetch+cache weekly bars
  python ema_archetypes.py                         # build panel + report
  python ema_archetypes.py --ehlers                # Super Smoother instead of EMA
"""

import os
import sys
import json
import glob
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from mtf_psar_rank import fetch_interval_bulk

warnings.filterwarnings("ignore")

BARS_DIR = "/tmp/ema_bars"
PANEL = "/tmp/ema_panel.csv"
UNIVERSE = "/tmp/ema_universe.json"

MA_PERIODS = [10, 20, 50, 200]
SLOPE_WIN = 4          # weeks over which slope is measured
FWD = [4, 13, 26, 52]  # forward-return horizons (weeks)


# ───────────────────────── moving averages

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def super_smoother(s: pd.Series, n: int) -> pd.Series:
    """Ehlers 2-pole Super Smoother (low-lag trend filter)."""
    a = np.exp(-np.sqrt(2) * np.pi / n)
    b = 2 * a * np.cos(np.sqrt(2) * np.pi / n)
    c2, c3 = b, -a * a
    c1 = 1 - c2 - c3
    x = s.to_numpy(dtype=float)
    out = np.full_like(x, np.nan)
    for i in range(len(x)):
        if i < 2 or not np.isfinite(x[i]):
            out[i] = x[i]
            continue
        p1 = out[i - 1] if np.isfinite(out[i - 1]) else x[i - 1]
        p2 = out[i - 2] if np.isfinite(out[i - 2]) else x[i - 2]
        out[i] = c1 * (x[i] + x[i - 1]) / 2 + c2 * p1 + c3 * p2
    return pd.Series(out, index=s.index)


# ───────────────────────── feature panel per ticker

def features_for(bars: pd.DataFrame, use_ehlers: bool = False) -> pd.DataFrame:
    """Weekly feature + forward-return frame for one ticker (no look-ahead)."""
    if bars is None or "Close" not in bars or len(bars) < 220:
        return pd.DataFrame()
    b = bars.dropna(subset=["Close"]).copy()
    if len(b) < 220:
        return pd.DataFrame()
    c = b["Close"].astype(float)
    v = b["Volume"].astype(float) if "Volume" in b else pd.Series(np.nan, index=b.index)
    mafn = super_smoother if use_ehlers else ema

    ma = {n: mafn(c, n) for n in MA_PERIODS}
    df = pd.DataFrame(index=b.index)
    df["close"] = c
    for n in MA_PERIODS:
        df[f"ma{n}"] = ma[n]

    # slopes (%/week) and acceleration (Δslope) for each MA
    for n in MA_PERIODS:
        m = ma[n]
        slope = (m - m.shift(SLOPE_WIN)) / m.shift(SLOPE_WIN) / SLOPE_WIN
        df[f"slope{n}"] = slope
        df[f"accel{n}"] = slope - slope.shift(SLOPE_WIN)

    # stack: full bull = 10>20>50>200 ; full bear = reverse
    m10, m20, m50, m200 = ma[10], ma[20], ma[50], ma[200]
    df["bull_stack"] = (m10 > m20) & (m20 > m50) & (m50 > m200)
    df["bear_stack"] = (m10 < m20) & (m20 < m50) & (m50 < m200)
    df["above200"] = c > m200
    df["above50"] = c > m50

    # compression: MA spread relative to price (low = coiled)
    stack = pd.concat([m10, m20, m50, m200], axis=1)
    df["spread"] = (stack.max(axis=1) - stack.min(axis=1)) / c

    # cross events (recency windows)
    gc_10_50 = (m10 > m50) & (m10.shift() <= m50.shift())
    dc_10_50 = (m10 < m50) & (m10.shift() >= m50.shift())
    gc_50_200 = (m50 > m200) & (m50.shift() <= m200.shift())
    dc_50_200 = (m50 < m200) & (m50.shift() >= m200.shift())
    df["gc_10_50_8w"] = gc_10_50.rolling(8, min_periods=1).max().astype(bool)
    df["dc_10_50_8w"] = dc_10_50.rolling(8, min_periods=1).max().astype(bool)
    df["gc_50_200_26w"] = gc_50_200.rolling(26, min_periods=1).max().astype(bool)
    df["dc_50_200_26w"] = dc_50_200.rolling(26, min_periods=1).max().astype(bool)

    # ── volume regime (weekly) ──
    if v.notna().sum() > 40:
        vmed20 = v.shift(1).rolling(20).median()
        df["rvol"] = v / vmed20
        up = c.pct_change() > 0
        win = 10
        upv = (v.where(up, 0)).rolling(win).sum()
        dnv = (v.where(~up, 0)).rolling(win).sum()
        df["updown"] = upv / dnv.replace(0, np.nan)
    else:
        df["rvol"] = np.nan
        df["updown"] = np.nan

    # ── forward returns (t -> t+k), no look-ahead ──
    for k in FWD:
        df[f"fwd{k}"] = c.shift(-k) / c - 1.0

    return df


# ───────────────────────── archetype labelling

def label_archetypes(df: pd.DataFrame) -> pd.Series:
    """Rule-based archetype per row from the MA state (crosses/slopes/accel)."""
    s50, a50 = df["slope50"], df["accel50"]
    s200 = df["slope200"]
    bull, bear = df["bull_stack"], df["bear_stack"]
    lab = pd.Series("Neutral/chop", index=df.index)

    # order matters: most specific first
    coil = (df["spread"] < 0.08) & (s50.abs() < 0.001)
    lab = lab.mask(coil, "Coiled/compressed")

    death = df["dc_50_200_26w"] & (~bull)
    lab = lab.mask(death, "Fresh death cross")

    golden = df["gc_50_200_26w"] & df["above200"]
    lab = lab.mask(golden, "Fresh golden cross")

    recovery = (~bull) & df["above50"] & (s200 >= 0) & df["gc_10_50_8w"]
    lab = lab.mask(recovery, "Bottoming recovery")

    pullback = bull & (df["close"] < df["ma20"]) & (s50 > 0)
    lab = lab.mask(pullback, "Uptrend pullback")

    bull_acc = bull & (s50 > 0) & (a50 > 0)
    lab = lab.mask(bull_acc, "Bull stack accelerating")

    bull_dec = bull & (s50 > 0) & (a50 <= 0)
    lab = lab.mask(bull_dec, "Bull stack decelerating")

    bear_fall = bear & (s50 < 0) & (a50 <= 0)
    lab = lab.mask(bear_fall, "Bear stack falling")

    bear_turn = bear & (s50 < 0) & (a50 > 0)
    lab = lab.mask(bear_turn, "Bear stack turning up")

    return lab


def vol_regime(df: pd.DataFrame) -> pd.Series:
    """Compact weekly volume regime label."""
    rvol, ud = df["rvol"], df["updown"]
    reg = pd.Series("normal", index=df.index)
    reg = reg.mask(rvol.isna(), "unknown")
    quiet = (rvol < 0.8)
    reg = reg.mask(quiet & reg.eq("normal"), "quiet")
    spike = rvol >= 2.0
    reg = reg.mask(spike & (ud >= 1.0), "spike_accum")
    reg = reg.mask(spike & (ud < 1.0), "spike_distrib")
    return reg


# ───────────────────────── fetch (resume-safe)

def safe(t):
    return t.replace("/", "_").replace("\\", "_")


def do_fetch():
    os.makedirs(BARS_DIR, exist_ok=True)
    uni = json.load(open(UNIVERSE))
    have = {os.path.splitext(f)[0] for f in os.listdir(BARS_DIR)}
    todo = [t for t in uni if safe(t) not in have]
    print(f"Universe {len(uni)}; cached {len(have)}; to fetch {len(todo)}", file=sys.stderr)
    if not todo:
        print("fetch complete"); return
    CH = 60
    for i in range(0, len(todo), CH):
        chunk = todo[i:i + CH]
        got = fetch_interval_bulk(chunk, "1wk", include_volume=True)
        if len(got) < max(2, len(chunk) * 0.2):
            print(f"ABORT: {len(got)}/{len(chunk)} — rate limited; resume later", file=sys.stderr)
            sys.exit(2)
        for t, d in got.items():
            d.to_csv(os.path.join(BARS_DIR, safe(t) + ".csv"))
        print(f"  fetched {i+len(chunk)}/{len(todo)} (+{len(got)})", file=sys.stderr)
    print("fetch complete")


# ───────────────────────── build panel + report

def build_panel(use_ehlers: bool) -> pd.DataFrame:
    files = glob.glob(os.path.join(BARS_DIR, "*.csv"))
    rows = []
    for f in files:
        t = os.path.splitext(os.path.basename(f))[0]
        try:
            b = pd.read_csv(f, index_col=0, parse_dates=True)
        except Exception:
            continue
        d = features_for(b, use_ehlers)
        if d.empty:
            continue
        d["archetype"] = label_archetypes(d)
        d["vol_regime"] = vol_regime(d)
        d["ticker"] = t
        # keep only rows with at least the 13w forward return realised
        d = d[d["fwd13"].notna()]
        rows.append(d[["ticker", "archetype", "vol_regime", "rvol",
                       "spread", "slope50", "accel50"] + [f"fwd{k}" for k in FWD]])
    if not rows:
        return pd.DataFrame()
    panel = pd.concat(rows, ignore_index=True)
    panel.to_csv(PANEL, index=False)
    return panel


def report(panel: pd.DataFrame):
    def agg(g):
        return pd.Series({
            "n": len(g),
            "fwd13_mean%": 100 * g["fwd13"].mean(),
            "fwd13_med%": 100 * g["fwd13"].median(),
            "fwd13_hit%": 100 * (g["fwd13"] > 0).mean(),
            "fwd26_mean%": 100 * g["fwd26"].mean(),
            "fwd52_mean%": 100 * g["fwd52"].mean(),
            "fwd13_p05%": 100 * g["fwd13"].quantile(0.05),
        })

    base13 = 100 * panel["fwd13"].mean()
    print(f"\n=== BASELINE: mean +13w return across all obs = {base13:.2f}%  (n={len(panel):,}) ===")

    print("\n=== ARCHETYPES (sorted by mean +13w return) ===")
    a = panel.groupby("archetype").apply(agg).sort_values("fwd13_mean%", ascending=False)
    a["edge13%"] = a["fwd13_mean%"] - base13
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(a.round(2).to_string())

    print("\n=== ARCHETYPE x VOLUME REGIME (+13w mean %, edge vs baseline) ===")
    piv = panel.groupby(["archetype", "vol_regime"]).apply(
        lambda g: pd.Series({"n": len(g), "fwd13_mean%": 100 * g["fwd13"].mean()}))
    piv["edge%"] = piv["fwd13_mean%"] - base13
    piv = piv[piv["n"] >= 200]     # ignore thin cells
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(piv.round(2).to_string())

    # volume lift within each archetype
    print("\n=== VOLUME LIFT: spike_accum minus quiet, per archetype (+13w mean %) ===")
    lift = []
    for arch, g in panel.groupby("archetype"):
        sa = g.loc[g.vol_regime == "spike_accum", "fwd13"]
        q = g.loc[g.vol_regime == "quiet", "fwd13"]
        if len(sa) >= 100 and len(q) >= 100:
            lift.append((arch, 100 * sa.mean(), len(sa), 100 * q.mean(), len(q),
                         100 * (sa.mean() - q.mean())))
    lift = pd.DataFrame(lift, columns=["archetype", "spike_accum%", "n_sa",
                                       "quiet%", "n_q", "lift%"]).sort_values("lift%", ascending=False)
    print(lift.round(2).to_string(index=False))


def main():
    if "--fetch" in sys.argv:
        do_fetch()
        return
    use_ehlers = "--ehlers" in sys.argv
    print(f"Building panel ({'Ehlers Super Smoother' if use_ehlers else 'EMA'})...", file=sys.stderr)
    panel = build_panel(use_ehlers)
    if panel.empty:
        print("No panel — fetch bars first with --fetch", file=sys.stderr)
        sys.exit(1)
    print(f"Panel: {len(panel):,} obs across {panel.ticker.nunique()} tickers", file=sys.stderr)
    report(panel)


if __name__ == "__main__":
    main()
