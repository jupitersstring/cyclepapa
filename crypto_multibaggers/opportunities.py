"""Today's candidates from the crypto re-rating study, each with the odds the
study measured out of time for its list.

1. Follow-through: coins that re-rated in the last `days` days, scored on the
   composite of the measures that separated 3x+ multibaggers from faded pops.
   Directions and the measure set are fixed on 2017-21 triggers; the odds are
   the 3x rate of 2022+ triggers in the same composite quintile. Each coin also
   gets its archetype from the 2017-21 fit and that archetype's 2022+ conversion.
2. Setups: today's tradeable coins in the top quintile of every signal of the
   best 2017-21 screen recipe (not yet popped), with that recipe's 2022+ 3x rate.

    python -m crypto_multibaggers.opportunities
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import analysis as A
from . import panel, study
from .config import ANALYSIS_DIR

CUT = pd.Timestamp("2022-01-01")
K = 8                      # measures in the follow-through composite


def _load():
    ev, pl, scr, live = study.load()
    drop = set(ev.loc[ev.symbol.isin(panel.COMMODITY_BACKED), "event_id"])
    ev = ev[~ev.symbol.isin(panel.COMMODITY_BACKED)].copy()
    pl = pl[~pl.symbol.isin(panel.COMMODITY_BACKED) & ~pl.event_id.isin(drop)].copy()
    live = live[~live.symbol.isin(panel.COMMODITY_BACKED)].copy()
    for df in (ev, pl, live):
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"])
        num = df.select_dtypes("number").columns
        df[num] = df[num].replace([np.inf, -np.inf], np.nan)
    return ev, pl, live


def _ecdf(ref: np.ndarray, x: np.ndarray) -> np.ndarray:
    ref = np.sort(ref[~np.isnan(ref)])
    out = np.searchsorted(ref, x, side="right") / max(len(ref), 1)
    return np.where(np.isnan(x), np.nan, out)


def follow_through_model(ev: pd.DataFrame):
    """Composite of the K measures that best split 2017-21 triggers into 3x+ vs
    not, each as a direction-adjusted percentile of its 2017-21 distribution."""
    e = ev[ev["complete"]]
    tr = e[e["date"] < CUT]
    y = (tr["mult_180"] >= 3).to_numpy()
    scores = {}
    for f in A.FEATS + A.D0:
        x = tr[f].to_numpy(float)
        ok = ~np.isnan(x)
        if ok.sum() >= 300:
            scores[f] = roc_auc_score(y[ok], x[ok])
    pick = sorted(scores, key=lambda f: -abs(scores[f] - 0.5))[:K]
    spec = [(f, 1 if scores[f] >= 0.5 else -1, tr[f].to_numpy(float)) for f in pick]

    def composite(df):
        cols = []
        for f, d, ref in spec:
            q = _ecdf(ref, df[f].to_numpy(float))
            cols.append(q if d > 0 else 1 - q)
        m = np.column_stack(cols)
        n = np.sum(~np.isnan(m), 1)
        return np.where(n >= K // 2, np.nanmean(m, 1), np.nan)

    ref_comp = composite(tr)
    te = e[e["date"] >= CUT].copy()
    te["q"] = _ecdf(ref_comp, composite(te))
    te["quintile"] = np.minimum((te["q"] * 5).fillna(-1).astype(int), 4) + 1
    te = te[te["q"].notna()]
    odds = te.groupby("quintile").agg(n=("symbol", "size"), p_3x=("mult_180", lambda m: float((m >= 3).mean())),
                                      p_10x=("mult_180", lambda m: float((m >= 10).mean())),
                                      mult_entry_med=("mult_180_entry", "median"))
    base = float((te["mult_180"] >= 3).mean())
    return spec, scores, composite, ref_comp, odds, base


def run(days: int = 10, top: int = 12) -> dict:
    ev, pl, live = _load()
    p, meta, mkt = panel.load()
    c, v = p["close"], p["volume"]
    last = c.index[-1]
    T = len(c.index)

    # ---- tradeability today (same rule as the live scan)
    v7 = v.iloc[-7:]
    trade = pd.DataFrame({"dv7": v7.mean(), "days7": (v7 > 0).sum(), "quoted": c.iloc[-3:].notna().any()})
    trade["tradeable"] = (trade["dv7"] >= 100_000) & (trade["days7"] >= 6) & trade["quoted"]

    # ---- 1. follow-through candidates
    spec, scores, composite, ref_comp, odds, base = follow_through_model(ev)
    arch, ainfo, gmm, qt, fill = A.exhibit_archetypes(
        ev[ev["date"] < CUT], pl[pl["date"] < CUT],
        (ev.loc[ev["date"] < CUT, "complete"] & (ev.loc[ev["date"] < CUT, "mult_180"] >= 3)).to_numpy())
    te = ev[(ev["date"] >= CUT) & ev["complete"]]
    pr = gmm.predict_proba(qt.transform(te[ainfo["cols"]].fillna(fill)))
    lab, core = pr.argmax(1), pr.max(1) >= 0.6
    y = (te["mult_180"] >= 3).to_numpy()
    arch_conv = {int(a): float(y[(lab == a) & core].mean()) for a in arch["id"] if ((lab == a) & core).sum() >= 15}
    arch_name = dict(zip(arch["id"].astype(int), arch["name"]))

    rec = ev[ev["date"] >= last - pd.Timedelta(days=days)].copy()
    rec["q"] = _ecdf(ref_comp, composite(rec))
    rec["quintile"] = np.minimum((rec["q"] * 5).fillna(-1).astype(int), 4) + 1
    rec["odds_3x"] = rec["quintile"].map(odds["p_3x"])
    rec["odds_10x"] = rec["quintile"].map(odds["p_10x"])
    prr = gmm.predict_proba(qt.transform(rec[ainfo["cols"]].fillna(fill)))
    rec["archetype"] = [arch_name[int(i)] if prr[j].max() >= 0.6 else "(none)" for j, i in enumerate(prr.argmax(1))]
    rec["archetype_conv"] = [arch_conv.get(int(i)) if prr[j].max() >= 0.6 else None for j, i in enumerate(prr.argmax(1))]
    ci = {s: i for i, s in enumerate(c.columns)}
    lc = np.log(c.to_numpy())
    now = np.array([np.nan if np.isnan(lc[-3:, ci[s]]).all() else lc[-3:, ci[s]][~np.isnan(lc[-3:, ci[s]])][-1]
                    for s in rec["symbol"]])
    rec["since_ref"] = now - np.array([lc[t - 1, ci[s]] for s, t in zip(rec["symbol"], rec["t"])])
    rec["since_d0"] = now - np.array([lc[t, ci[s]] for s, t in zip(rec["symbol"], rec["t"])])
    rec = rec.join(trade, on="symbol")
    rec = rec[rec["tradeable"].fillna(False)].sort_values(["q"], ascending=False)

    # ---- 2. setups: best 2017-21 three-signal recipe, applied to today's cross-section
    recipes = pd.read_csv(ANALYSIS_DIR / "screen_recipes.csv")
    recipes["signals"] = recipes["signals"].map(eval)
    best = recipes[recipes["k"] == 3].sort_values("lift_train", ascending=False).iloc[0]
    lb = pd.read_csv(ANALYSIS_DIR / "screen_leaderboard_3x.csv").set_index("feature")
    ok = pd.Series(True, index=live.index)
    for f in best["signals"]:
        x = live[f] * lb.at[f, "direction"]
        ok &= x.rank(pct=True) >= 0.8
    setups = live[ok].join(trade, on="symbol")
    setups = setups[setups["tradeable"].fillna(False)]
    scan = pd.read_csv(ANALYSIS_DIR / "live_scan.csv").set_index("symbol")
    setups = setups.join(scan[["score_pct", "archetype"]], on="symbol")
    setups = setups.sort_values("score_pct", ascending=False)

    out = {"last": last, "odds": odds, "base": base, "spec": [(f, d, scores[f]) for f, d, _ in spec],
           "recent": rec, "setups": setups, "recipe": best, "n_recent_all": int((ev["date"] >= last - pd.Timedelta(days=days)).sum())}
    keep_r = ["symbol", "name", "date", "d0_ret", "d0_z", "q", "quintile", "odds_3x", "odds_10x", "archetype",
              "archetype_conv", "since_ref", "since_d0", "dv7", "n_high60_S20", "mom_30", "toxic_mom_A"]
    rec[keep_r].to_csv(ANALYSIS_DIR / "opportunities_follow_through.csv", index=False)
    keep_s = ["symbol", "name", "score_pct", "archetype", "dv7", "max_dd_A", "car_M", "car_S", "av_peak_A",
              "vol_ratio_S", "vpin_cdf", "dd_ath"]
    setups[[k for k in keep_s if k in setups]].to_csv(ANALYSIS_DIR / "opportunities_setups.csv", index=False)
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)
    o = run()
    print("data through", o["last"].date(), "| recent triggers (all):", o["n_recent_all"], "| tradeable:", len(o["recent"]))
    print("composite:", [(A.LABEL[f], d, round(a, 3)) for f, d, a in o["spec"]])
    print("2022+ odds by composite quintile (base %.3f):" % o["base"])
    print(o["odds"].round(3).to_string())
    r = o["recent"]
    print(r[["symbol", "name", "date", "d0_ret", "q", "quintile", "odds_3x", "archetype", "archetype_conv", "since_ref",
             "since_d0", "dv7"]].head(20).round(3).to_string())
    print("recipe:", o["recipe"]["labels"], "train", round(o["recipe"]["lift_train"], 2), "test", round(o["recipe"]["lift_test"], 2),
          "hit", round(o["recipe"]["hit_test"], 3))
    s = o["setups"]
    print(len(s), "setups")
    print(s[["symbol", "name", "score_pct", "archetype", "dv7", "max_dd_A", "car_M", "car_S", "av_peak_A", "vol_ratio_S",
             "vpin_cdf", "dd_ath"]].head(20).round(3).to_string())
