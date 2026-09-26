"""Subgroup discovery: the SPECIFIC, detailed pre-conditions with the largest
out-of-sample uplift in the odds of multibagging -> MULTIBAGGER_RULES.md.

Building blocks (~230 binary conditions): every story feature LOW (bottom
quintile within its month and local market) or HIGH (top quintile), every
interpretable state (st_*), and the data-missing flags.

Beam search over conjunctions of 2-4 conditions, discovered ONLY on the fit
period (<= 2017), then required to hold in TWO separate out-of-sample windows
(2018-2020 and 2021+). Rules are ranked by their WORST lift across the three
periods (a rule that worked once cannot rank), subject to minimum support
(>= 0.05% of weighted month-ends and >= 25 events in each period). Near-
duplicate rules (>= 70% overlap of covered month-ends) collapse to the best.
Every surviving rule is reported with lift, support, speed to 3x, 5x / 10x
rates, the blow-up rate (worst close -50% or worse within 24 months), and
real examples. A gradient-boosted model (fit <= 2017) cross-checks whether
structure is left beyond the rules.

Outcomes: t3_24 (3x within 24 months), t3_12 (within 12), t10_60 (a held 10x
within 60 months, from fwd_mult_60).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc

MD = "MULTIBAGGER_RULES.md"
FIT_END = pd.Timestamp("2017-12-31")
T1_END = pd.Timestamp("2020-12-31")
MIN_SHARE = 0.0005
MIN_EVENTS = 25
BEAM = 80


def conditions(d: pd.DataFrame):
    feats = mc.feats_all(d)
    R = mc.ranked(d, feats)
    C, names = [], []
    for f in feats:
        r = R[f].to_numpy()
        C.append(r <= 0.2); names.append(f"{f} LOW")
        C.append(r >= 0.8); names.append(f"{f} HIGH")
    for s in [c for c in d.columns if c.startswith("st_")]:
        C.append(d[s].to_numpy() == 1); names.append(s[3:])
    for k in mc.MISS:
        C.append(R[k].to_numpy() == 1); names.append(k)
    M = np.vstack([np.nan_to_num(c, nan=0).astype(bool) for c in C])
    return M, names


class Scorer:
    def __init__(self, d, label):
        self.y = d[label].to_numpy(float)
        ok = ~np.isnan(self.y)
        wk = d["week"].to_numpy()
        self.w = d["w_cc"].to_numpy(float) * ok
        self.y = np.nan_to_num(self.y)
        self.periods = {"fit": ok & (wk <= np.datetime64(FIT_END)),
                        "t1": ok & (wk > np.datetime64(FIT_END)) & (wk <= np.datetime64(T1_END)),
                        "t2": ok & (wk > np.datetime64(T1_END))}
        self.base = {k: (self.w[m] * self.y[m]).sum() / self.w[m].sum() for k, m in self.periods.items()}
        self.tot = {k: self.w[m].sum() for k, m in self.periods.items()}

    def score(self, mask, periods=("fit",)):
        out = {}
        for k in periods:
            m = mask & self.periods[k]
            ww = self.w[m]
            s = ww.sum()
            ev = int((self.y[m] > 0).sum())
            if s <= 0 or s / self.tot[k] < MIN_SHARE or ev < MIN_EVENTS:
                return None
            out[k] = ((ww * self.y[m]).sum() / s / self.base[k], s / self.tot[k], ev)
        return out


def search(d, M, names, label, max_depth=4):
    sc = Scorer(d, label)
    cand = []
    for i in range(len(names)):
        r = sc.score(M[i])
        if r:
            cand.append(((i,), r["fit"][0]))
    cand.sort(key=lambda x: -x[1])
    beam = cand[:BEAM]
    allrules = list(cand)
    singles = [c[0][0] for c in cand]
    for depth in range(2, max_depth + 1):
        nxt = {}
        for rule, _ in beam:
            base_mask = np.logical_and.reduce([M[i] for i in rule])
            for j in singles:
                if j in rule:
                    continue
                key = tuple(sorted(rule + (j,)))
                if key in nxt:
                    continue
                r = sc.score(base_mask & M[j])
                if r:
                    nxt[key] = r["fit"][0]
        lst = sorted(nxt.items(), key=lambda x: -x[1])
        allrules += lst
        beam = lst[:BEAM]
    # out-of-sample on the fit-best rules
    allrules.sort(key=lambda x: -x[1])
    rows = []
    seen = []
    for rule, fl in allrules[:3000]:
        mask = np.logical_and.reduce([M[i] for i in rule])
        r = sc.score(mask, ("fit", "t1", "t2"))
        if not r:
            continue
        rows.append({"rule": " & ".join(names[i] for i in rule), "n_conditions": len(rule),
                     "fit_lift": r["fit"][0], "t1_lift": r["t1"][0], "t2_lift": r["t2"][0],
                     "min_lift": min(r["fit"][0], r["t1"][0], r["t2"][0]),
                     "fit_share": r["fit"][1], "t1_share": r["t1"][1], "t2_share": r["t2"][1],
                     "events_fit": r["fit"][2], "events_t1": r["t1"][2], "events_t2": r["t2"][2],
                     "_mask": mask})
    out = pd.DataFrame(rows).sort_values("min_lift", ascending=False)
    # collapse near-duplicates (>= 70% overlap of covered month-ends)
    keep = []
    for _, r in out.iterrows():
        m = r["_mask"]
        if any((m & k).sum() >= 0.7 * min(m.sum(), k.sum()) for k in seen):
            continue
        seen.append(m)
        keep.append(r)
        if len(keep) >= 40:
            break
    res = pd.DataFrame(keep)
    return res, sc


def describe(d, res, sc, label):
    rows = []
    for _, r in res.iterrows():
        m = r["_mask"] & (sc.w > 0)
        sub = d.loc[m]
        rec = {"rule": r["rule"]}
        hits = sub[sub[label] == 1]
        rec["median_months_to_3x"] = float(hits["months_to_3x"].median()) if "months_to_3x" in sub and len(hits) else np.nan
        for lab in ("t3_12", "t5_60"):
            v = sub[lab].dropna()
            rec[f"{lab}_rate"] = float(v.mean()) if len(v) >= 30 else np.nan
        fm = sub["fwd_mult_60"].dropna() if "fwd_mult_60" in sub else pd.Series(dtype=float)
        rec["t10_60_rate"] = float((fm >= 10).mean()) if len(fm) >= 30 else np.nan
        fmin = sub["fwd_min_24"].dropna()
        rec["p_blowup_50"] = float((fmin <= -0.5).mean()) if len(fmin) >= 30 else np.nan
        fr = sub["fwd_ret_24"].dropna()
        rec["median_fwd_24m"] = float(fr.median()) if len(fr) >= 30 else np.nan
        ex = hits.sort_values("fwd_ret_24", ascending=False).drop_duplicates("symbol").head(6)
        rec["examples"] = "; ".join(f"{a} {b:%Y-%m}" for a, b in zip(ex["symbol"], ex["week"]))
        rows.append(rec)
    return pd.DataFrame(rows)


def gbm_check(d, label):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    feats = mc.feats_all(d)
    X = mc.ranked(d, feats)
    y = d[label]
    ok = y.notna()
    fit = ok & (d["week"] <= FIT_END)
    test = ok & (d["week"] > FIT_END)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         min_samples_leaf=200, random_state=7)
    clf.fit(X[fit], y[fit], sample_weight=d.loc[fit, "w_cc"])
    p = pd.Series(clf.predict_proba(X[test])[:, 1], index=X[test].index)
    auc = roc_auc_score(y[test], p, sample_weight=d.loc[test, "w_cc"])
    base = np.average(y[test], weights=d.loc[test, "w_cc"])
    out = {"auc_test": auc, "base_test": base}
    m = d.loc[test, "week"].dt.to_period("M")
    for q in (0.005, 0.01, 0.05):
        top = p.groupby(m).transform(lambda s: s >= s.quantile(1 - q))
        sel = top[top].index
        out[f"lift_top_{q:.1%}"] = np.average(y[sel], weights=d.loc[sel, "w_cc"]) / base
    return out


def main():
    d = mc.load()
    d = d[~d["bio"]].reset_index(drop=True)
    if "fwd_mult_60" in d.columns:
        d["t10_60"] = (d["fwd_mult_60"] >= 10).astype(float).where(d["fwd_mult_60"].notna())
    M, names = conditions(d)
    L = ["# The specific pre-conditions with the largest out-of-sample uplift\n",
         f"{d['symbol'].nunique():,} symbols, {len(d):,} liquid month-ends (non-biotech; unit-break symbols "
         "excluded). Rules are DISCOVERED on 2012-2017 only and must hold separately in 2018-2020 (t1) and "
         "2021+ (t2); ranked by the WORST of the three lifts. LOW / HIGH = bottom / top quintile of the feature "
         "within its month and local market. Support floor: >= 0.05% of month-ends and >= 25 events per "
         "period; near-duplicates (>= 70% overlap) collapsed.\n"]
    for label, title in (("t3_24", "3x within 24 months"), ("t3_12", "3x within 12 months (fast)"),
                         ("t10_60", "10x within 60 months")):
        if label not in d.columns or d[label].notna().sum() < 1000:
            continue
        res, sc = search(d, M, names, label)
        if not len(res):
            L.append(f"\n## {title}\n\nno rule met the support floor in all three periods\n")
            continue
        desc = describe(d, res, sc, label)
        tab = res.drop(columns=["_mask"]).merge(desc, on="rule", how="left")
        tab.to_csv(f"mb_rules_{label}.csv", index=False)
        L.append(f"\n## {title}  (base rate: fit {sc.base['fit']:.2%}, 2018-20 {sc.base['t1']:.2%}, "
                 f"2021+ {sc.base['t2']:.2%})\n")
        cols = ["rule", "min_lift", "fit_lift", "t1_lift", "t2_lift", "t2_share", "events_t2",
                "median_months_to_3x", "t10_60_rate", "p_blowup_50", "median_fwd_24m", "examples"]
        L.append(tab[[c for c in cols if c in tab.columns]].head(25).round(3).to_markdown(index=False))
        try:
            g = gbm_check(d, label)
            L.append(f"\nGradient-boosted cross-check (fit <= 2017, all 2018+): AUC {g['auc_test']:.3f}; lift of "
                     f"the top 0.5% / 1% / 5% each month: {g['lift_top_0.5%']:.2f}x / {g['lift_top_1.0%']:.2f}x / "
                     f"{g['lift_top_5.0%']:.2f}x\n")
        except Exception as exc:          # the cross-check must not sink the rules
            L.append(f"\n(gradient-boosted cross-check failed: {exc})\n")
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
