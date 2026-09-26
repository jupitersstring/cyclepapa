"""Mining the multibaggers for the archetypes inherent in them -> MULTIBAGGER_ARCHETYPES.md

The whole dataset, every year: each multibagger episode (a held 3x within 24
months; also 3x within 12 / 36 months, 5x and 10x within 60) is taken at its
starting state, and the starting states are mined three ways:

  CLUSTERS on the narrative axes (every story feature ranked within its month
    and local market, combined into ~20 directed axes: growth, margin
    trajectory, best-in-own-history, cash quality, efficiency trend, cheapness,
    cheap vs own history, balance sheet, capital discipline, fallen,
    divergence of fundamentals from the tape, ignition, volatility, neglect,
    size, sentiment, insiders / activists, reinvestment, headcount)
      k-means (k by silhouette, cluster robustness by split-half agreement)
      Gaussian mixture (components by BIC)
      HDBSCAN (naturally dense groups; ambiguous starts left unassigned)
  PATTERNS: conjunctions of 2-4 conditions (every feature in its top / bottom
    fifth, every interpretable state) ranked by how much they multiply the
    odds, with a support floor; near-duplicates collapsed
  TREE recipes on the narrative axes

For every archetype: what it looks like (axes, the most distinctive features
across the full FMP ratio set / trend shapes / divergences / tape, the states
it over-represents, medians in plain units), how common it is among
multibaggers and among all stocks, how much it multiplies the odds, the speed
to 3x, the 5x / 10x rates, the median 24-month return, the blow-up rate
(worst close -50% or worse within 24 months), and real examples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc

MD = "MULTIBAGGER_ARCHETYPES.md"
READ = mc.READ + [("kr_operatingProfitMargin_own", "op margin, own-history pct", "pct"),
                  ("gap_sales_1y", "sales/share vs price 1y (log gap)", "x"),
                  ("gap_own_opm", "margin own-pct minus price own-pct", "x"),
                  ("tr_opm_slope8", "op-margin slope 8q", "x"),
                  ("dd_time_share_260", "share of 5y in deep drawdown", "pct"),
                  ("wks_since_lo260", "weeks since 5y low", "x")]


def outcome_cols(d):
    if "fwd_mult_60" in d.columns:
        d["t10_60"] = (d["fwd_mult_60"] >= 10).astype(float).where(d["fwd_mult_60"].notna())
    return d


def base_rate(d, label):
    ok = d[label].notna()
    return np.average(d.loc[ok, label], weights=d.loc[ok, "w_cc"])


def region_stats(d, inr, label):
    w = d["w_cc"]
    ok = d[label].notna()
    br = base_rate(d, label)
    m = ok & inr
    if m.sum() < 50:
        return {}
    rate = np.average(d.loc[m, label], weights=w[m])
    out = {"share_of_all_month_ends": float(w[m].sum() / w[ok].sum()), "rate": rate, "lift": rate / br,
           "multibagger_month_ends": int(d.loc[m, label].sum())}
    for lab in ("t3_12", "t3_36", "t5_60", "t10_60"):
        if lab in d.columns:
            mm = m & d[lab].notna()
            if mm.sum() >= 50:
                out[f"{lab}_rate"] = np.average(d.loc[mm, lab], weights=w[mm])
    hits = m & (d[label] == 1) & d["months_to_3x"].notna()
    if hits.any():
        out["median_months_to_3x"] = float(d.loc[hits, "months_to_3x"].median())
    fr = m & d["fwd_ret_24"].notna()
    if fr.sum() >= 50:
        out["median_fwd_24m"] = float(d.loc[fr, "fwd_ret_24"].median())
    fm = m & d["fwd_min_24"].notna()
    if fm.sum() >= 50:
        out["p_blowup_50"] = float(np.average(d.loc[fm, "fwd_min_24"] <= -0.5, weights=w[fm]))
    return out


def signature(d, R, S, idx, feats):
    pop_ax = S[list(mc.BLOCKS)].mean()
    axes = (S.loc[idx, list(mc.BLOCKS)].mean() - pop_ax).sort_values(key=lambda x: -x.abs())
    fr = R.loc[idx, feats].mean() - R[feats].mean()
    top = pd.concat([fr.sort_values(ascending=False).head(10), fr.sort_values().head(8)])
    stc = [c for c in d.columns if c.startswith("st_")]
    st_in = d.loc[idx, stc].mean()
    st_pop = d[stc].mean()
    st_l = (st_in / st_pop.where(st_pop > 0)).sort_values(ascending=False)
    med = {lab: d.loc[idx, col].median() for col, lab, _ in READ if col in d.columns}
    miss = R.loc[idx, list(mc.MISS)].mean()
    return {"axes": axes.round(3).to_dict(), "features": top.round(3).to_dict(),
            "states": {s: (round(float(st_in[s]), 3), round(float(st_l[s]), 2)) for s in st_l.index[:8]},
            "medians": med, "data_present": (1 - miss).round(2).to_dict()}


def examples(d, idx, n=10):
    e = d.loc[idx].copy()
    e["best"] = e["fwd_mult_60"].fillna(e["fwd_ret_24"] + 1) if "fwd_mult_60" in e.columns else e["fwd_ret_24"] + 1
    e = e.sort_values("best", ascending=False).drop_duplicates("symbol").head(n)
    return "; ".join(f"{r.symbol} {r.week:%Y-%m} ({r.best:.1f}x)" for r in e.itertuples())


def prepare(d):
    feats = mc.feats_all(d)
    R = mc.ranked(d, feats)
    S = mc.blocks(R)
    X = S.fillna(0.5).to_numpy(float)
    from sklearn.preprocessing import StandardScaler
    rng = np.random.default_rng(7)
    sub = rng.choice(len(d), size=min(250_000, len(d)), replace=False)
    sc = StandardScaler().fit(X[sub])
    Z = sc.transform(X)
    R = R.loc[:, ~R.columns.duplicated()]              # ranked() already carries the st_ flags
    return feats, R, S, Z


def cluster_entries(d, feats, R, S, Z, label, method, kmax=14):
    from sklearn.cluster import HDBSCAN, KMeans
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    from sklearn.mixture import GaussianMixture
    ent = mc.entries(d, label).to_numpy()
    ei = np.where(ent)[0]
    Ze = Z[ei]
    we = d["w_cc"].to_numpy()[ei]
    rng = np.random.default_rng(7)
    sel = []
    if method == "kmeans":
        for k in range(3, kmax + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(Ze, sample_weight=we)
            s = silhouette_score(Ze, km.labels_, sample_size=min(6000, len(Ze)), random_state=7)
            half = rng.random(len(Ze)) < 0.5
            a = KMeans(n_clusters=k, n_init=5, random_state=1).fit(Ze[half], sample_weight=we[half])
            b = KMeans(n_clusters=k, n_init=5, random_state=2).fit(Ze[~half], sample_weight=we[~half])
            sel.append({"k": k, "silhouette": s, "robustness_ari": adjusted_rand_score(a.predict(Ze), b.predict(Ze))})
        sel = pd.DataFrame(sel)
        good = sel[sel["robustness_ari"] >= 0.5]
        k = int((good if len(good) else sel).sort_values("silhouette", ascending=False)["k"].iloc[0])
        model = KMeans(n_clusters=k, n_init=20, random_state=7).fit(Ze, sample_weight=we)
        lab_e, centers = model.labels_, model.cluster_centers_
    elif method == "gmm":
        # resample by weight so the mixture sees the population-weighted entries
        p = we / we.sum()
        rs = rng.choice(len(Ze), size=len(Ze), replace=True, p=p)
        for k in range(2, kmax + 1):
            g = GaussianMixture(n_components=k, covariance_type="diag", random_state=7).fit(Ze[rs])
            sel.append({"k": k, "bic": g.bic(Ze[rs])})
        sel = pd.DataFrame(sel)
        k = int(sel.sort_values("bic")["k"].iloc[0])
        g = GaussianMixture(n_components=k, covariance_type="diag", random_state=7).fit(Ze[rs])
        lab_e = g.predict(Ze)
        centers = np.vstack([Ze[lab_e == c].mean(axis=0) if (lab_e == c).any() else g.means_[c] for c in range(k)])
    else:
        mcs = max(40, int(0.01 * len(Ze)))
        h = HDBSCAN(min_cluster_size=mcs, min_samples=10).fit(Ze)
        lab_e = h.labels_
        ks = sorted(set(lab_e) - {-1})
        remap = {c: i for i, c in enumerate(ks)}
        lab_e = np.array([remap.get(c, -1) for c in lab_e])
        k = len(ks)
        centers = np.vstack([Ze[lab_e == c].mean(axis=0) for c in range(k)]) if k else np.zeros((0, Ze.shape[1]))
        sel = pd.DataFrame([{"clusters": k, "unassigned_share": float((lab_e == -1).mean()),
                             "min_cluster_size": mcs}])
    # regions over ALL month-ends: nearest centre, within the 75th-pct radius
    # of that archetype's own members
    rows = []
    if len(centers):
        dist = np.stack([np.linalg.norm(Z - c, axis=1) for c in centers], axis=1)
        near = dist.argmin(axis=1)
        rad = np.array([np.quantile(np.linalg.norm(Ze[lab_e == c] - centers[c], axis=1), 0.75) for c in range(len(centers))])
        inr_all = dist[np.arange(len(d)), near] <= rad[near]
        for c in range(len(centers)):
            idx = d.index[ei[lab_e == c]]
            rec = {"archetype": c, "n_multibaggers": len(idx),
                   "share_of_multibaggers": float(we[lab_e == c].sum() / we.sum())}
            rec.update(region_stats(d, pd.Series((near == c) & inr_all, index=d.index), label))
            rec["_sig"] = signature(d, R, S, idx, feats)
            rec["_ex"] = examples(d, idx)
            rows.append(rec)
    return sel, pd.DataFrame(rows), int(len(ei))


def mine_patterns(d, R, label, max_depth=4, beam=80, min_share=0.0005, min_events=50):
    feats = [c for c in R.columns if not c.startswith("st_") and c not in mc.MISS]
    C, names = [], []
    for f in feats:
        r = R[f].to_numpy()
        C.append(r <= 0.2); names.append(f"{f} LOW")
        C.append(r >= 0.8); names.append(f"{f} HIGH")
    for s in [c for c in R.columns if c.startswith("st_")]:
        C.append(R[s].to_numpy() == 1); names.append(s[3:])
    M = np.vstack([np.nan_to_num(c, nan=0).astype(bool) for c in C])
    y = d[label].to_numpy(float)
    ok = ~np.isnan(y)
    w = d["w_cc"].to_numpy(float) * ok
    y = np.nan_to_num(y)
    tot, br = w.sum(), (w * y).sum() / w.sum()

    def score(mask):
        ww = w[mask]
        s = ww.sum()
        ev = int((y[mask] > 0).sum())
        if s / tot < min_share or ev < min_events:
            return None
        return (ww * y[mask]).sum() / s / br, s / tot, ev

    singles, cand = [], []
    for i in range(len(names)):
        r = score(M[i])
        if r:
            singles.append(i)
            cand.append(((i,), r))
    cand.sort(key=lambda x: -x[1][0])
    beam_ = cand[:beam]
    allr = list(cand)
    for _ in range(2, max_depth + 1):
        nxt = {}
        for rule, _r in beam_:
            bm = np.logical_and.reduce([M[i] for i in rule])
            for j in singles:
                if j in rule:
                    continue
                key = tuple(sorted(rule + (j,)))
                if key in nxt:
                    continue
                r = score(bm & M[j])
                if r:
                    nxt[key] = r
        lst = sorted(nxt.items(), key=lambda x: -x[1][0])
        allr += lst
        beam_ = lst[:beam]
    allr.sort(key=lambda x: -x[1][0])
    keep, seen = [], []
    for rule, (lift, share, ev) in allr:
        m = np.logical_and.reduce([M[i] for i in rule])
        if any((m & k).sum() >= 0.7 * min(m.sum(), k.sum()) for k in seen):
            continue
        seen.append(m)
        rec = {"pattern": " & ".join(names[i] for i in rule), "conditions": len(rule), "lift": lift,
               "share_of_month_ends": share, "multibagger_month_ends": ev}
        rec.update({k: v for k, v in region_stats(d, pd.Series(m, index=d.index), label).items()
                    if k in ("median_months_to_3x", "t10_60_rate", "p_blowup_50", "median_fwd_24m")})
        idx = d.index[m & (d[label] == 1).to_numpy()]
        rec["examples"] = examples(d, idx, 6)
        keep.append(rec)
        if len(keep) >= 40:
            break
    return pd.DataFrame(keep)


def tree_recipes(d, S, label, depth=4):
    from sklearn.tree import DecisionTreeClassifier
    ok = d[label].notna()
    X = S.fillna(0.5)
    clf = DecisionTreeClassifier(max_depth=depth, min_weight_fraction_leaf=0.005, class_weight="balanced",
                                 random_state=7).fit(X[ok], d.loc[ok, label], sample_weight=d.loc[ok, "w_cc"])
    leaf = pd.Series(clf.apply(X), index=d.index)
    tr, names, paths = clf.tree_, list(X.columns), {}

    def walk(node, conds):
        if tr.children_left[node] == -1:
            paths[node] = " & ".join(conds) or "all"
            return
        f, th = names[tr.feature[node]], tr.threshold[node]
        walk(tr.children_left[node], conds + [f"{f} <= {th:.2f}"])
        walk(tr.children_right[node], conds + [f"{f} > {th:.2f}"])
    walk(0, [])
    rows = []
    for lf, p in paths.items():
        rec = {"recipe": p}
        rec.update(region_stats(d, leaf == lf, label))
        if rec.get("lift"):
            rows.append(rec)
    return pd.DataFrame(rows).sort_values("lift", ascending=False)


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    return f"{v:.0%}" if kind == "pct" else f"{v:.2f}"


def describe(L, tab, title, sel, n_ent, br):
    L.append(f"\n### {title}\n")
    L.append(f"{n_ent:,} multibagger starts; base rate {br:.2%} of month-ends.\n")
    L.append(sel.round(3).to_markdown(index=False))
    if not len(tab):
        return
    cols = [c for c in ["archetype", "n_multibaggers", "share_of_multibaggers", "share_of_all_month_ends", "lift",
                        "rate", "t3_12_rate", "t5_60_rate", "t10_60_rate", "median_months_to_3x", "median_fwd_24m",
                        "p_blowup_50"] if c in tab.columns]
    L.append("\n" + tab.sort_values("lift", ascending=False)[cols].round(3).to_markdown(index=False) + "\n")
    for _, r in tab.sort_values("lift", ascending=False).iterrows():
        sg = r["_sig"]
        L.append(f"\n**Archetype {int(r['archetype'])}** — {r.get('share_of_multibaggers', 0):.0%} of multibaggers, "
                 f"lift {r.get('lift', np.nan):.2f}x, blow-up {r.get('p_blowup_50', np.nan):.0%}")
        L.append("- axes (vs all month-ends, + = more): " + ", ".join(f"{k} {v:+.2f}" for k, v in list(sg["axes"].items())[:10]))
        L.append("- most distinctive features (rank vs all): " + ", ".join(f"{k} {v:+.2f}" for k, v in sg["features"].items()))
        L.append("- states over-represented (share, x vs all): " + ", ".join(
            f"{k[3:]} {v[0]:.0%} ({v[1]:.1f}x)" for k, v in sg["states"].items()))
        L.append("- medians at the start: " + "; ".join(
            f"{lab} {_fmt(sg['medians'].get(lab), kind)}" for _, lab, kind in READ if lab in sg["medians"]))
        L.append("- data present: " + ", ".join(f"{k[5:]} {v:.0%}" for k, v in sg["data_present"].items()))
        L.append(f"- examples (start, best multiple within 5y): {r['_ex']}")


def main():
    d = mc.load()
    d = outcome_cols(d)
    bio = d[d["bio"]].copy()
    d = d[~d["bio"]].reset_index(drop=True)
    feats, R, S, Z = prepare(d)
    L = ["# The multibaggers, mined — archetypes inherent in the dataset\n",
         f"Every liquid month-end 2012-2026: {d['symbol'].nunique():,} symbols, {len(d):,} month-ends (non-biotech; "
         f"{d.attrs.get('unit_break_excluded', 0):,} unit-break symbols excluded). Each multibagger episode is taken "
         "at its starting state. Every feature is ranked within its month and local market; the narrative axes "
         "combine them. Lift = how many times more often month-ends in that archetype led to the multibagger than "
         "the average month-end.\n"]
    for label, title in (("t3_24", "3x within 24 months"), ("t3_12", "3x within 12 months"),
                         ("t3_36", "3x within 36 months"), ("t10_60", "10x within 5 years")):
        if label not in d.columns or (d[label] == 1).sum() < 200:
            continue
        br = base_rate(d, label)
        L.append(f"\n## {title}\n")
        methods = ("kmeans", "gmm", "hdbscan") if label in ("t3_24", "t10_60") else ("kmeans",)
        for mth in methods:
            sel, tab, n_ent = cluster_entries(d, feats, R, S, Z, label, mth)
            tab.drop(columns=[c for c in tab.columns if c.startswith("_")], errors="ignore").to_csv(
                f"mb_archetypes_{label}_{mth}.csv", index=False)
            describe(L, tab, {"kmeans": "k-means clusters", "gmm": "Gaussian-mixture clusters",
                              "hdbscan": "HDBSCAN dense groups"}[mth], sel, n_ent, br)
        pats = mine_patterns(d, R, label)
        pats.to_csv(f"mb_patterns_{label}.csv", index=False)
        L.append(f"\n### Patterns (2-4 conditions) ranked by lift — {title}\n")
        L.append(pats.round(3).to_markdown(index=False))
        tr = tree_recipes(d, S, label)
        L.append(f"\n### Tree recipes on the narrative axes — {title}\n")
        L.append(tr.round(3).head(20).to_markdown(index=False))
    if len(bio) and (bio["t3_24"] == 1).sum() >= 200:
        bio = bio.reset_index(drop=True)
        fb, Rb, Sb, Zb = prepare(bio)
        sel, tab, n_ent = cluster_entries(bio, fb, Rb, Sb, Zb, "t3_24", "kmeans", kmax=8)
        L.append("\n## Drug developers (separate mechanism)\n")
        describe(L, tab, "k-means clusters (3x within 24 months)", sel, n_ent, base_rate(bio, "t3_24"))
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
