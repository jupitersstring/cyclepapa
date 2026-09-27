"""The model archetype: a walk-forward gradient-boosted model over EVERY
feature of the point-in-time panel -> MULTIBAGGER_MODEL.md, mb_model_scores.csv

Why: 55% of profitable-operator multibaggers sat in no rule-based archetype,
and the two clusters that held them had lift ~1.0 — no single state
distinguished them. Rules are boxes; a model over ~550 features (the story
features, every FMP ratio and its trend, the divergences, the operator and
peer / industry / market frames, the states) can hold the interactions the
boxes cannot. The model is judged the only honest way: fit on the past,
scored on the future, year by year.

  1. WALK-FORWARD   for each year Y from 2016: fit on month-ends whose 24-month
                    outcome was KNOWN by the end of Y-1 (week <= Y-1 end minus
                    104 weeks — a row nearer the cutoff has only its wins
                    resolved), score every month-end of year Y. The score is
                    ranked within month x market; lift of the top 1% / 5% /
                    10%, blow-up, 10x rate, AUC — per year and pooled.
  2. COVERAGE       share of the multibagger month-ends the top decile holds,
                    alone and united with the rule archetypes; what the model
                    adds inside the uncovered population specifically.
  3. WHAT IT USES   permutation importance on the last fold; the top-decile
                    region described by a shallow tree (the interactions the
                    boxes missed, as candidate rules with their own lift).
  4. TODAY          the final model (fit on every resolved month-end) scores
                    today's cross-section — mb_today.parquet when the
                    universe build exists, else the panel's latest month-ends
                    — into mb_model_scores.csv (probability, rank within
                    market, percentile against the out-of-sample history) for
                    the engine's arch_mb_model_top.
Labels are USD (multibagger_usd_labels.py) unless MB_LOCAL=1.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

import multibagger_clusters as mc
import multibagger_lift2 as L2
import multibagger_mine as mm
import multibagger_operators as mo
import multibagger_segments as ms

MD = "MULTIBAGGER_MODEL.md"
SCORES = "mb_model_scores.csv"
LABEL = "t3_24"
FIRST_TEST_YEAR = 2016


def _gbm():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=500, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200,
                                          l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
                                          n_iter_no_change=30, random_state=7)


def features(d: pd.DataFrame):
    """The full feature set with the operator, peer, industry and market
    frames, ranked within month x market (the same space every study used)."""
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "sector", "industry"], low_memory=False).drop_duplicates("symbol")
    d = d.merge(g, on="symbol", how="left")
    d = ms.add_measures(d)
    d = mo.add_measures(d)
    mc.BLOCKS = {**mc.BLOCKS, **mo.OP_BLOCKS}
    mc.FEATS = mc.FEATS + [c for c in d.columns if c.startswith(("pp_", "as_", "op_", "ind_", "mkt_"))]
    feats = mc.feats_all(d)
    R = mc.ranked(d, feats)
    R = R.loc[:, ~R.columns.duplicated()]
    return d, R


def _lift_table(d, p, mask, w, label=LABEL):
    """Lift of the top q within month x market among `mask` rows."""
    m = d["week"].dt.to_period("M").astype(str) + "|" + d["market"].astype(str)
    y = d[label]
    ok = mask & y.notna() & p.notna()
    base = np.average(y[ok], weights=w[ok])
    rk = p[ok].groupby(m[ok]).rank(pct=True)
    out = {"n": int(ok.sum()), "base": base}
    for q in (0.01, 0.05, 0.10, 0.20):
        sel = ok.copy(); sel[ok] = rk >= 1 - q
        if sel.sum() < 50:
            continue
        out[f"lift_top{int(q*100)}"] = float(np.average(y[sel], weights=w[sel]) / base) if base > 0 else np.nan
        fm = d.loc[sel, "fwd_min_24"].dropna()
        out[f"blowup_top{int(q*100)}"] = float((fm <= -0.5).mean()) if len(fm) >= 40 else np.nan
        t10 = d.loc[sel, "t10_60"].dropna()
        out[f"t10_top{int(q*100)}"] = float(t10.mean()) if len(t10) >= 40 else np.nan
    return out


def walk_forward(d, R, y, w):
    """Out-of-sample score for every month-end from FIRST_TEST_YEAR on."""
    p = pd.Series(np.nan, index=d.index, dtype="float32")
    years = list(range(FIRST_TEST_YEAR, int(d["week"].dt.year.max()) + 1))
    rows, last = [], None
    for Y in years:
        cutoff = pd.Timestamp(f"{Y-1}-12-31") - pd.Timedelta(weeks=104)
        fit = (d["week"] <= cutoff) & y.notna()
        test = (d["week"].dt.year == Y) & y.notna()
        if fit.sum() < 20000 or test.sum() < 1000:
            continue
        X = R.loc[:, R[fit].nunique(dropna=True) > 1]
        clf = _gbm()
        clf.fit(X[fit], y[fit], sample_weight=w[fit])
        p[test] = clf.predict_proba(X[test])[:, 1].astype("float32")
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y[test], p[test], sample_weight=w[test])
        rows.append({"year": Y, "fit_rows": int(fit.sum()), "test_rows": int(test.sum()), "auc": auc,
                     "iterations": int(clf.n_iter_), **_lift_table(d, p, test, w)})
        print(f"  {Y}: fit {fit.sum():,} test {test.sum():,} auc {auc:.3f} top5 lift {rows[-1].get('lift_top5', np.nan):.2f}", flush=True)
        last = (clf, X.columns, test)
    return p, pd.DataFrame(rows), last


def region_rules(d, R, p, y, w, L):
    """The top-decile region explained by a shallow tree: each leaf that is
    mostly in-region is a candidate rule, scored on the whole population."""
    from sklearn.tree import DecisionTreeClassifier, export_text
    m = d["week"].dt.to_period("M").astype(str) + "|" + d["market"].astype(str)
    ok = p.notna() & y.notna()
    rk = p[ok].groupby(m[ok]).rank(pct=True)
    top = pd.Series(False, index=d.index); top[ok] = rk >= 0.9
    feats = [c for c in R.columns if c not in mc.MISS]
    rng = np.random.default_rng(7)
    sub = rng.choice(d.index[ok], size=min(300_000, int(ok.sum())), replace=False)
    Xs = R.loc[sub, feats].fillna(0.5)
    tree = DecisionTreeClassifier(max_depth=4, min_samples_leaf=3000, random_state=7).fit(Xs, top[sub])
    L.append("\n### The top-decile region as a tree (depth 4; ranks within month x market, 0-1)\n")
    L.append("```\n" + export_text(tree, feature_names=feats, max_depth=4, decimals=2) + "\n```\n")
    # each leaf -> rule; lift of the rule on the whole out-of-sample population
    leaf = tree.apply(R.loc[ok, feats].fillna(0.5))
    leaf_s = pd.Series(leaf, index=d.index[ok])
    base = np.average(y[ok], weights=w[ok])
    rows = []
    tr = tree.tree_
    for lf in np.unique(leaf):
        sel = leaf_s.index[leaf_s == lf]
        share_top = float(top[sel].mean())
        if len(sel) < 3000:
            continue
        rate = np.average(y[sel], weights=w[sel])
        fm = d.loc[sel, "fwd_min_24"].dropna()
        rows.append({"leaf": int(lf), "share_in_top_decile": share_top, "n": len(sel), "rate": rate,
                     "lift": rate / base, "p_blowup_50": float((fm <= -0.5).mean()) if len(fm) else np.nan})
    t = pd.DataFrame(rows).sort_values("lift", ascending=False)
    L.append("\nleaves ranked by lift on the whole out-of-sample population (a leaf mostly inside the top decile "
             "is a rule the boxes did not have):\n\n" + t.round(3).to_markdown(index=False))


def importance(last, d, y, w, L):
    from sklearn.inspection import permutation_importance
    clf, cols, test = last
    R = d.attrs["R"]
    idx = np.random.default_rng(7).choice(d.index[test], size=min(50_000, int(test.sum())), replace=False)
    imp = permutation_importance(clf, R.loc[idx, cols], y[idx], n_repeats=2, random_state=7, scoring="roc_auc",
                                 sample_weight=w[idx])
    s = pd.Series(imp.importances_mean, index=cols).sort_values(ascending=False)
    L.append("\n### What the last fold's model leans on (permutation importance, AUC loss)\n")
    L.append(s.head(40).round(4).to_frame("importance").to_markdown())
    return s


def score_today(d, R, y, w, L):
    """Fit on every resolved month-end; score today's cross-section."""
    last_week = d["week"].max()
    fit = (d["week"] <= last_week - pd.Timedelta(weeks=104)) & y.notna()
    X = R.loc[:, R[fit].nunique(dropna=True) > 1]
    clf = _gbm().fit(X[fit], y[fit], sample_weight=w[fit])
    cols = list(X.columns)
    if os.path.exists("mb_today.parquet"):
        t = pd.read_parquet("mb_today.parquet")
        t["week"] = pd.to_datetime(t["week"])
        t = t[t["week"] >= last_week - pd.Timedelta(weeks=8)]
        src = "mb_today.parquet (whole universe)"
        # rank today's names within market against TODAY'S cross-section
        t, Rt = features(t)
        Rt = Rt.reindex(columns=cols)
        pt = pd.Series(clf.predict_proba(Rt.fillna(0.5))[:, 1], index=t.index)
        t["mb_model_p"] = pt.values
    else:
        t = d[d["week"] >= last_week - pd.Timedelta(weeks=8)].copy()
        src = "the panel's latest month-ends (study sample only; build mb_today.parquet for the universe)"
        t["mb_model_p"] = clf.predict_proba(R.loc[t.index, cols])[:, 1]
    t = t.sort_values("week").drop_duplicates("symbol", keep="last")
    t["mb_model_rank_mkt"] = t.groupby("market")["mb_model_p"].rank(pct=True)
    t["mb_model_rank"] = t["mb_model_p"].rank(pct=True)
    hist = d.attrs["p_oos"].dropna().to_numpy()
    t["mb_model_pct_hist"] = np.searchsorted(np.sort(hist), t["mb_model_p"].to_numpy()) / max(len(hist), 1)
    out = t[["symbol", "week", "mb_model_p", "mb_model_rank_mkt", "mb_model_rank", "mb_model_pct_hist"]]
    out.to_csv(SCORES, index=False)
    L.append(f"\n# 4. Today\n\nScored {len(out):,} names from {src} as of {t['week'].max().date()}; "
             f"{int((out['mb_model_rank_mkt'] >= 0.95).sum()):,} in the top 5% of their market.\n")
    top = out.merge(d.drop_duplicates("symbol")[["symbol"]], on="symbol", how="left")
    L.append("Top 40 by probability:\n\n" + out.sort_values("mb_model_p", ascending=False).head(40).round(4).to_markdown(index=False))
    return out


def main():
    d = mc.load()
    d = mm.outcome_cols(d)
    d = d[~d["bio"]].reset_index(drop=True)
    d, R = features(d)
    y, w = d[LABEL], d["w_cc"]
    ind = d["industry"].fillna("").str.lower()
    d["asset"] = ((d["sector"].isin(["Energy", "Materials", "Real Estate", "Utilities"])
                   | ind.str.contains(ms.ASSET_IND, regex=True)) & ~d["bio"])
    d["preprofit"] = ((d["opm"] < 0) | (d["fcf_margin"] < 0)) & ~d["bio"] & ~d["asset"]
    A = L2.archetypes(d); A.update(mo.segment_archetypes(d)); A.update(mo.operator_archetypes(d))
    covered = pd.concat([m_.fillna(False) for m_ in A.values()], axis=1).any(axis=1)
    L = ["# The model archetype: a walk-forward model over every feature\n",
         f"{len(d):,} month-ends (non-biotech), {R.shape[1]} features ranked within month x market; labels "
         f"{d.attrs.get('labels', 'local')}; base 3x-within-24m rate {mm.base_rate(d, LABEL):.2%}.\n"]
    L.append("\n# 1. Walk-forward, year by year\n")
    p, tab, last = walk_forward(d, R, y, w)
    d.attrs["p_oos"] = p; d.attrs["R"] = R
    L.append(tab.round(3).to_markdown(index=False))
    oos = p.notna() & y.notna()
    pooled = _lift_table(d, p, oos, w)
    L.append(f"\nPooled {FIRST_TEST_YEAR}+: " + ", ".join(f"{k} {v:.3f}" for k, v in pooled.items() if k != "n") + "\n")
    # 2. coverage
    L.append("\n# 2. Coverage of the multibagger month-ends (out-of-sample years)\n")
    m = d["week"].dt.to_period("M").astype(str) + "|" + d["market"].astype(str)
    rk = p[oos].groupby(m[oos]).rank(pct=True)
    ev = oos & (y == 1)
    top10 = pd.Series(False, index=d.index); top10[oos] = rk >= 0.9
    top5 = pd.Series(False, index=d.index); top5[oos] = rk >= 0.95
    rows = []
    for name, mask in (("rule archetypes (any of the 22)", covered), ("model top 10%", top10), ("model top 5%", top5),
                       ("archetypes OR model top 10%", covered | top10)):
        sel = mask & oos
        rows.append({"selection": name, "share_of_month_ends": float(w[sel].sum() / w[oos].sum()),
                     "share_of_multibagger_month_ends": float(w[sel & ev].sum() / w[ev].sum()),
                     "rate": float(np.average(y[sel], weights=w[sel])) if sel.sum() else np.nan})
    L.append(pd.DataFrame(rows).round(3).to_markdown(index=False))
    unc = oos & ~covered
    L.append(f"\nInside the UNCOVERED population ({int(unc.sum()):,} month-ends, base {np.average(y[unc], weights=w[unc]):.2%}): "
             + ", ".join(f"{k} {v:.3f}" for k, v in _lift_table(d, p, unc, w).items() if k != "n") + "\n")
    for pop, mask in (("profitable operators", ((d['opm'] >= 0) & (d['fcf_margin'] >= 0)).fillna(False) & ~d['asset']),
                      ("fallen (<= 40% of 5y high)", (d["dist_hi260"] <= 0.4).fillna(False)),
                      ("not fallen (>= 60%)", (d["dist_hi260"] >= 0.6).fillna(False))):
        mm_ = oos & mask
        L.append(f"\n{pop}: " + ", ".join(f"{k} {v:.3f}" for k, v in _lift_table(d, p, mm_, w).items() if k != "n"))
    # 3. what it uses
    L.append("\n# 3. What the model uses\n")
    if last is not None:
        importance(last, d, y, w, L)
    region_rules(d, R, p, y, w, L)
    open(MD, "w").write("\n".join(L))
    # 4. today
    score_today(d, R, y, w, L)
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD} and {SCORES}", flush=True)


if __name__ == "__main__":
    main()
