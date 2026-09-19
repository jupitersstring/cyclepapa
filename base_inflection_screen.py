"""MU-style screen: a long QUARTERLY CONSOLIDATION base (extended contained
range, like MU before its breakout) + a FUNDAMENTAL INFLECTION (earnings/revenue/
growth tone turning up in recent quarters).

Base (from weekly bars, /tmp/fmp_bars): the length of the current contained
range, whether price is now pressing the top of it (breakout beginning), and
volatility contraction. Longer + tighter + near-top = more MU-like.

Inflection (from FMP panel, /tmp/fmp_panel.csv): F (rev/EPS/GP/EBIT accel +
margin), I (SUE/surprise + revenue confirmation), growth stability and the
positive-surprise streak — the "tone and tenor" of the fundamentals improving.

mu_like = base_score x fundamental inflection  (both required).

Run: python base_inflection_screen.py [--min-base 26] [--top 40]
"""
import sys, glob, os, json
import numpy as np
import pandas as pd

BARS = "/tmp/fmp_bars"
PANEL = "/tmp/fmp_panel.csv"
INFO = "/home/user/cyclepapa/data/ticker_info_cache.json"
MASTER = "/tmp/master_full_universe.csv"
DELIVER = "/home/user/cyclepapa/data/monster/mu_like_base_inflection.csv"

WINDOWS = [26, 39, 52, 65, 78, 104, 130]   # candidate base lengths (weeks)
BAND = 0.55                                 # contained range: (Hmax-Lmin)/close


def base_metrics(b):
    """Current consolidation base at the latest bar (no future data used)."""
    if len(b) < 60:
        return None
    c, h, l = b.Close, b.High, b.Low
    px = float(c.iloc[-1])
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    # longest contained window ending now
    base_len = 0; base_hi = np.nan; base_lo = np.nan
    for W in WINDOWS:
        if len(b) < W + 4:
            break
        hi = float(h.iloc[-W:].max()); lo = float(l.iloc[-W:].min())
        if lo > 0 and (hi - lo) / px <= BAND:
            base_len, base_hi, base_lo = W, hi, lo
    if base_len == 0:
        return None
    rng = (base_hi - base_lo) / px
    near_high = px / base_hi                        # ~1.0 = pressing/breaking the top
    pos_in_base = (px - base_lo) / (base_hi - base_lo) if base_hi > base_lo else np.nan
    atr_recent = float(tr.iloc[-10:].mean() / px)
    atr_base = float(tr.iloc[-base_len:].mean() / px)
    contraction = atr_base / atr_recent if atr_recent > 0 else np.nan   # >1 = tightening now
    above_40w = px > float(c.iloc[-40:].mean())
    # drawup over the base (MU rose gently through a long base — reward mild, not parabolic)
    base_drift = px / float(c.iloc[-base_len]) - 1
    return {"base_len": base_len, "base_range": rng, "near_high": near_high,
            "pos_in_base": pos_in_base, "contraction": contraction,
            "above_40w": bool(above_40w), "base_drift": base_drift}


def main():
    min_base = 26; top = 40
    if "--min-base" in sys.argv:
        min_base = int(sys.argv[sys.argv.index("--min-base") + 1])
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])

    rows = []
    for f in glob.glob(os.path.join(BARS, "*.csv")):
        t = os.path.basename(f)[:-4].replace("__", "/")
        try:
            b = pd.read_csv(f, index_col=0, parse_dates=True).dropna(subset=["Close"])
        except Exception:
            continue
        m = base_metrics(b)
        if m:
            m["ticker"] = t
            rows.append(m)
    base = pd.DataFrame(rows)
    if base.empty:
        print("no bases yet — fetch weekly bars first (fmp_bars.py)"); return

    panel = pd.read_csv(PANEL)
    df = base.merge(panel, on="ticker", how="inner")

    def pc(col):
        return df[col].rank(pct=True) if col in df else pd.Series(0.5, index=df.index)

    # fundamental inflection (tone/tenor of recent quarters turning up)
    infl = (0.28 * df["F"].clip(0, 1).fillna(0) + 0.22 * df["I"].clip(0, 1).fillna(0)
            + 0.18 * pc("f_rev_accel") + 0.12 * pc("f_eps_accel")
            + 0.10 * pc("growth_stability") + 0.10 * (pc("i_pos_streak")))
    df["inflection"] = infl.round(3)

    # MULTIPLE DE-RATING THROUGH THE BASE: revenue/earnings grew while price sat
    # in the consolidation -> the multiple compressed (stored energy for a
    # re-rating on breakout). base_drift is price change across the base window.
    rev_g = df["rev_ttm_g"]
    ni_g = df.get("ni_ttm_g", pd.Series(np.nan, index=df.index))
    # P/S compression: 1 - (1+priceChg)/(1+revGrowth); +ve = multiple fell while growing
    df["ps_compression"] = np.where(rev_g > 0.05,
                                    1 - (1 + df["base_drift"]) / (1 + rev_g), np.nan)
    df["pe_compression"] = np.where(ni_g > 0.05,
                                    1 - (1 + df["base_drift"]) / (1 + ni_g), np.nan)
    # derating score: reward compression only when growth is genuine (rev_g>0)
    comp = df[["ps_compression", "pe_compression"]].max(axis=1)
    df["derate_score"] = (comp.clip(0, 0.5) / 0.5).fillna(0).round(3)

    # base score: long + near the top + contracting + healthy (above 40w, mild drift)
    length = (df["base_len"] / 104).clip(0, 1)
    near = ((df["near_high"] - 0.85) / 0.17).clip(0, 1)              # 0.85->0, ~1.02->1
    contract = ((df["contraction"] - 0.8) / 0.8).clip(0, 1)
    healthy = df["above_40w"].astype(float) * (df["base_drift"].between(-0.15, 1.5)).astype(float)
    df["base_score"] = (0.45 * length + 0.30 * near + 0.15 * contract + 0.10 * healthy).round(3)

    # fundamental side = EITHER acceleration/inflection OR multiple-derating-with-
    # growth through the base (two valid MU-like paths, per the user).
    df["fund_side"] = (0.55 * df["inflection"] + 0.45 * df["derate_score"]).round(3)

    # require a genuine long base + real fundamentals + at least one fundamental
    # path present (inflecting OR derating-while-growing)
    ok = (df["base_len"] >= min_base) & df["rev_ttm_g"].notna() & \
         ((df["inflection"] > 0.35) | (df["derate_score"] > 0.2))
    df["mu_like"] = np.where(ok, (100 * df["base_score"] * (0.4 + df["fund_side"])), np.nan)
    df = df.sort_values("mu_like", ascending=False)

    # names + liquidity
    try:
        info = json.load(open(INFO))
        df["name"] = df.ticker.map(lambda t: info.get(t, {}).get("name", ""))
    except Exception:
        pass
    try:
        mst = pd.read_csv(MASTER, low_memory=False)[["ticker", "adv_usd"]]
        df = df.merge(mst, on="ticker", how="left")
        df["adv_usd_M"] = (df["adv_usd"] / 1e6).round(2)
    except Exception:
        pass

    cols = ["ticker", "name", "mu_like", "base_len", "base_range", "near_high",
            "contraction", "fund_side", "inflection", "derate_score", "ps_compression",
            "rev_ttm_g", "base_drift", "F", "I", "f_rev_accel", "i_pos_streak", "adv_usd_M"]
    cols = [c for c in cols if c in df.columns]
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    df[cols].round(3).to_csv(DELIVER, index=False)

    live = df[df.mu_like.notna()]
    print(f"MU-like candidates: {len(live)} (of {len(df)} with base+fundamentals; "
          f"{len(base)} bases scanned)")
    with pd.option_context("display.width", 240, "display.max_columns", 30):
        print(f"\n=== TOP {top} MU-LIKE (long base + fundamental inflection) ===")
        print(live[cols].head(top).to_string(index=False))


if __name__ == "__main__":
    main()
