"""Transparent BPT-style opportunity score (Bigger Picture Trading, reconstructed).

Rather than clone the proprietary black-box +10 Trend Score, this measures each
BPT layer SEPARATELY and auditable, per the reconstructed intellectual core:

    Opportunity = Leadership x Acceleration x Compression x Context

  LEADERSHIP   multi-horizon RS (1W/1M/3M, 0-100 cross-sectional rank) + sector RS
  ACCELERATION RS acceleration (1W >> 3M = emerging leadership) + fundamental
               acceleration (rev/EPS 2nd-derivative, FMP) + estimate revisions
  COMPRESSION  base duration + volatility contraction + D50 ATR-elasticity RESET
               (high-RS name pulled back near D50 = unused elasticity) + squeeze
  CONTEXT      market regime (breadth + market elasticity) + catalyst + HTF
               structure (power-trend MA alignment, above D50, D50>D200)

Plus BPT's distinctive elasticity read: individual ATR-elasticity = (P-SMA50)/ATR,
with a momentum "sweet spot" ~1.5-4 ATR and an oversold ~-3; ADR%>~5 for
tradability. The prized setup is HIGH RS + RS ACCELERATION + reset/low elasticity
+ HTF compression + fundamental acceleration -> a defined trigger.

Market regime (breadth ladder <50/50-60/60-70/70+ and SPY/QQQ elasticity zones)
is computed once and applied as the Context overlay.

Inputs: /tmp/fmp_daily (daily, incl _SPY/_QQQ), /tmp/fmp_bars (weekly),
/tmp/fmp_panel.csv (FMP fundamentals), /tmp/vwap_features.csv, /tmp/fmp_catalyst.csv
(optional), /tmp/fmp_bulk/profile.csv (sector).

Run: python bpt_score.py [--top 40]
"""
import glob, os, sys, json
import numpy as np
import pandas as pd

DAILY = "/tmp/fmp_daily"
WEEKLY = "/tmp/fmp_bars"
PANEL = "/tmp/fmp_panel.csv"
VWAP = "/tmp/vwap_features.csv"
CATALYST = "/tmp/fmp_catalyst.csv"
PROFILE = "/tmp/fmp_bulk/profile.csv"
INFO = "/home/user/cyclepapa/data/ticker_info_cache.json"
MASTER = "/tmp/master_full_universe.csv"
DELIVER = "/home/user/cyclepapa/data/monster/bpt_score.csv"


def ema(s, n): return s.ewm(span=n, adjust=False, min_periods=n).mean()
def sma(s, n): return s.rolling(n).mean()


def atr(df, n=14):
    h, l, c = df.High, df.Low, df.Close
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def market_regime():
    """Breadth (% of universe above D50/D200) + SPY/QQQ ATR-elasticity -> regime."""
    files = [f for f in glob.glob(os.path.join(DAILY, "*.csv")) if not os.path.basename(f).startswith("_")]
    above50 = above200 = tot = 0
    for f in files:
        try:
            b = pd.read_csv(f, index_col=0, parse_dates=True).dropna(subset=["Close"])
        except Exception:
            continue
        if len(b) < 210:
            continue
        c = b.Close
        tot += 1
        if c.iloc[-1] > c.rolling(50).mean().iloc[-1]:
            above50 += 1
        if c.iloc[-1] > c.rolling(200).mean().iloc[-1]:
            above200 += 1
    breadth50 = 100 * above50 / tot if tot else np.nan
    breadth200 = 100 * above200 / tot if tot else np.nan
    elos = {}
    for sym in ("_SPY", "_QQQ"):
        p = os.path.join(DAILY, sym + ".csv")
        if os.path.exists(p):
            b = pd.read_csv(p, index_col=0, parse_dates=True)
            e = (b.Close.iloc[-1] - sma(b.Close, 50).iloc[-1]) / atr(b).iloc[-1]
            elos[sym[1:]] = float(e)
    mkt_elast = np.nanmean(list(elos.values())) if elos else np.nan
    # regime score 0-1 from breadth ladder, tempered by elasticity extension
    if breadth50 >= 70: base = 0.90
    elif breadth50 >= 60: base = 0.72
    elif breadth50 >= 50: base = 0.55
    elif breadth50 >= 40: base = 0.38
    else: base = 0.25
    # penalise late/euphoric extension (SPY elasticity toward +7..+10), reward reset
    if np.isfinite(mkt_elast):
        if mkt_elast >= 7: base *= 0.80
        elif mkt_elast <= -3: base *= 0.9   # oversold — asymmetric but risky
    return {"breadth50": breadth50, "breadth200": breadth200,
            "mkt_elasticity": mkt_elast, "regime_score": round(base, 3),
            "spy_qqq_elast": elos}


def daily_features(b):
    if len(b) < 130:
        return None
    c, h, l = b.Close, b.High, b.Low
    r = {}
    r["ret_1w"] = c.iloc[-1] / c.iloc[-6] - 1 if len(c) > 6 else np.nan
    r["ret_1m"] = c.iloc[-1] / c.iloc[-22] - 1 if len(c) > 22 else np.nan
    r["ret_3m"] = c.iloc[-1] / c.iloc[-64] - 1 if len(c) > 64 else np.nan
    s50 = sma(c, 50); s200 = sma(c, 200) if len(c) >= 200 else sma(c, min(len(c) - 1, 150))
    a = atr(b, 14)
    r["elasticity"] = float((c.iloc[-1] - s50.iloc[-1]) / a.iloc[-1]) if a.iloc[-1] else np.nan
    r["adr_pct"] = float(((h - l) / c).iloc[-20:].mean() * 100)
    # power-trend MA alignment 8>21>34>50 (EMA)
    e8, e21, e34, e50 = ema(c, 8), ema(c, 21), ema(c, 34), ema(c, 50)
    al = [e8.iloc[-1] > e21.iloc[-1], e21.iloc[-1] > e34.iloc[-1], e34.iloc[-1] > e50.iloc[-1]]
    r["ma_align"] = float(np.mean(al))
    r["above_d50"] = int(c.iloc[-1] > s50.iloc[-1])
    r["d50_over_d200"] = int(s50.iloc[-1] > s200.iloc[-1])
    # squeeze proxy: Bollinger(20) width in bottom third of last 6mo = compression
    bbw = (c.rolling(20).std() * 4) / c
    if bbw.notna().sum() > 130:
        r["bbw_pctile"] = float((bbw.iloc[-1] <= bbw.iloc[-130:]).mean())  # low = compressed
    else:
        r["bbw_pctile"] = np.nan
    return r


def weekly_base(t):
    p = os.path.join(WEEKLY, t.replace("/", "__") + ".csv")
    if not os.path.exists(p):
        return {"base_len": 0, "contraction": np.nan}
    try:
        b = pd.read_csv(p, index_col=0, parse_dates=True).dropna(subset=["Close"])
    except Exception:
        return {"base_len": 0, "contraction": np.nan}
    if len(b) < 40:
        return {"base_len": 0, "contraction": np.nan}
    c, h, l = b.Close, b.High, b.Low
    px = float(c.iloc[-1])
    base_len = 0
    for W in (26, 39, 52, 65, 78, 104, 130):
        if len(b) < W + 4:
            break
        if (float(h.iloc[-W:].max()) - float(l.iloc[-W:].min())) / px <= 0.55:
            base_len = W
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    contraction = float(tr.iloc[-max(4, base_len or 26):].mean() / max(tr.iloc[-10:].mean(), 1e-9))
    return {"base_len": base_len, "contraction": contraction}


def main():
    top = 40
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])

    reg = market_regime()
    print("=== MARKET REGIME ===")
    print(f"  breadth>50D: {reg['breadth50']:.1f}%  breadth>200D: {reg['breadth200']:.1f}%  "
          f"| mkt elasticity(SPY/QQQ): {reg['mkt_elasticity']:.2f}  {reg['spy_qqq_elast']}")
    ladder = ("70+ broad" if reg['breadth50'] >= 70 else "60-70 healthy" if reg['breadth50'] >= 60
              else "50-60 constructive/selective" if reg['breadth50'] >= 50
              else "<50 narrowing/defensive")
    print(f"  regime: {ladder}  -> regime_score={reg['regime_score']}")

    rows = []
    for f in glob.glob(os.path.join(DAILY, "*.csv")):
        base = os.path.basename(f)
        if base.startswith("_"):
            continue
        t = base[:-4].replace("__", "/")
        try:
            b = pd.read_csv(f, index_col=0, parse_dates=True).dropna(subset=["Close"])
        except Exception:
            continue
        d = daily_features(b)
        if d is None:
            continue
        d["ticker"] = t
        rows.append(d)
    df = pd.DataFrame(rows)
    if df.empty:
        print("no daily features"); return

    # RS = cross-sectional 0-100 rank of trailing returns
    df["rs_1w"] = (df.ret_1w.rank(pct=True) * 100).round(1)
    df["rs_1m"] = (df.ret_1m.rank(pct=True) * 100).round(1)
    df["rs_3m"] = (df.ret_3m.rank(pct=True) * 100).round(1)
    df["rs_accel"] = (df.rs_1w - df.rs_3m).round(1)          # short RS outrunning long = emerging

    # weekly base/contraction
    wb = pd.DataFrame([{"ticker": t, **weekly_base(t)} for t in df.ticker])
    df = df.merge(wb, on="ticker", how="left")

    # sector (theme) breadth
    try:
        prof = pd.read_csv(PROFILE)[["symbol", "sector"]].dropna()
        df = df.merge(prof.rename(columns={"symbol": "ticker"}), on="ticker", how="left")
    except Exception:
        df["sector"] = ""
    sec = df.groupby("sector").agg(sector_rs=("rs_3m", "mean"),
                                   sector_coils=("bbw_pctile", lambda s: float((s <= 0.2).mean())),
                                   sector_n=("ticker", "count")).reset_index()
    df = df.merge(sec, on="sector", how="left")

    # fundamentals (FMP panel) + vwap + catalyst
    try:
        pan = pd.read_csv(PANEL)[["ticker", "F", "I", "f_rev_accel", "f_eps_accel",
                                  "rev_ttm_g", "i_pos_streak"]]
        df = df.merge(pan, on="ticker", how="left")
    except Exception:
        pass
    try:
        vw = pd.read_csv(VWAP)[["ticker", "vwap_cross_score", "vwap_consol_score",
                                "w_cross_up", "near_avwap_ytd", "above_avwap_ytd", "vol_spike_recent"]]
        df = df.merge(vw, on="ticker", how="left")
    except Exception:
        pass
    try:
        cat = pd.read_csv(CATALYST)[["ticker", "catalyst_magnitude", "catalyst_verified"]]
        df = df.merge(cat, on="ticker", how="left")
    except Exception:
        df["catalyst_magnitude"] = np.nan

    def z01(s): return s.rank(pct=True)

    # ---- four transparent BPT layers (each 0-1) ----
    LEAD = (0.45 * df.rs_3m / 100 + 0.25 * df.rs_1m / 100
            + 0.30 * z01(df.sector_rs)).clip(0, 1)
    # acceleration: RS 1w>>3m + fundamental 2nd-derivative
    rs_acc01 = ((df.rs_accel + 100) / 200).clip(0, 1)
    ACCEL = (0.5 * rs_acc01 + 0.3 * df.get("F", pd.Series(0.5, index=df.index)).fillna(0.5)
             + 0.2 * z01(df.get("f_rev_accel", pd.Series(np.nan, index=df.index)))).clip(0, 1)
    # elasticity reset score: best when near/just above D50 (unused elasticity),
    # penalise >5 ATR extended and <-3 broken
    el = df.elasticity
    elast_reset = np.where(el.between(-1, 2), 1.0,
                   np.where(el.between(2, 4), 0.7,
                   np.where(el.between(-3, -1), 0.5,
                   np.where(el > 5, 0.2, np.where(el < -3, 0.15, 0.4)))))
    base01 = (df.base_len / 104).clip(0, 1)
    squeeze01 = (1 - df.bbw_pctile).clip(0, 1).fillna(0)   # low BBW pctile -> compressed
    COMPRESS = (0.35 * base01 + 0.30 * pd.Series(elast_reset, index=df.index)
                + 0.20 * squeeze01 + 0.15 * df.get("vwap_consol_score", pd.Series(0, index=df.index)).fillna(0)).clip(0, 1)
    # context: market regime (overlay) + catalyst + HTF structure
    htf = (0.5 * df.ma_align + 0.25 * df.above_d50 + 0.25 * df.d50_over_d200)
    cat01 = df.get("catalyst_magnitude", pd.Series(np.nan, index=df.index)).fillna(0.0)
    CONTEXT = (0.55 * reg["regime_score"] + 0.25 * htf + 0.20 * cat01).clip(0, 1)

    df["LEAD"], df["ACCEL"], df["COMPRESS"], df["CONTEXT"] = (LEAD.round(3), ACCEL.round(3),
                                                             COMPRESS.round(3), CONTEXT.round(3))
    # weighted-geometric composite (offsets keep one weak leg from zeroing it)
    df["bpt_score"] = (100 * (0.15 + LEAD) ** 0.35 * (0.15 + ACCEL) ** 0.28
                       * (0.15 + COMPRESS) ** 0.22 * (0.15 + CONTEXT) ** 0.15
                       / (1.15 ** (0.35 + 0.28 + 0.22 + 0.15))).round(2)
    # the prized BPT setup flag: high RS + RS accel + reset elasticity + compression
    df["bpt_prime"] = ((df.rs_3m >= 60) & (df.rs_accel >= 10) &
                       (df.elasticity.between(-1.5, 4)) & (df.base_len >= 39)).astype(int)

    # liquidity + names
    try:
        mst = pd.read_csv(MASTER, low_memory=False)[["ticker", "adv_usd"]]
        df = df.merge(mst, on="ticker", how="left"); df["adv_usd_M"] = (df.adv_usd / 1e6).round(2)
    except Exception:
        pass
    try:
        info = json.load(open(INFO)); df["name"] = df.ticker.map(lambda t: info.get(t, {}).get("name", ""))
    except Exception:
        pass

    df = df.sort_values("bpt_score", ascending=False)
    cols = ["ticker", "name", "sector", "bpt_score", "bpt_prime", "LEAD", "ACCEL", "COMPRESS",
            "CONTEXT", "rs_1w", "rs_1m", "rs_3m", "rs_accel", "elasticity", "adr_pct", "base_len",
            "sector_rs", "F", "rev_ttm_g", "w_cross_up", "near_avwap_ytd", "catalyst_magnitude", "adv_usd_M"]
    cols = [c for c in cols if c in df.columns]
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    df[cols].round(3).to_csv(DELIVER, index=False)

    liq = df[df.adv_usd_M >= 3] if "adv_usd_M" in df else df
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(f"\n=== TOP {top} BPT-SCORE (liquid >=$3M ADV) ===")
        print(liq[cols].head(top).to_string(index=False))
        prime = liq[liq.bpt_prime == 1]
        print(f"\n=== BPT PRIME setups (RS>=60 + RS accel>=10 + reset elasticity + long base): {len(prime)} ===")
        print(prime[cols].head(top).to_string(index=False))


if __name__ == "__main__":
    main()
