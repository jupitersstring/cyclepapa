"""Latent clusters of the conditions that PRECEDE multibagging.

Reads mb_panel.parquet (multibagger_story.py) and asks: among the stocks that
went on to triple, what DISTINCT pre-conditions did they start from — and
does each of those states actually raise the odds out of sample?

  1. Every continuous story feature is ranked WITHIN ITS MONTH across all
     stocks (percentile), so a bull or bear market cannot manufacture a
     cluster; missing blocks (no statements / no valuation / no analysts / no
     headcount) are explicit indicators — being uncovered is itself a state.
  2. ENTRIES: the first month-end of each multibagger episode (months that
     lead to a held 3x within 24 months; a new episode after a > 6-month gap),
     i.e. the stock's state BEFORE the run.
  3. The entries of the FIT period (<= 2017) are clustered (weighted k-means
     on PCA of the ranked story; k chosen by silhouette AND split-half
     stability, not fixed).
  4. Each cluster defines a REGION of feature space (within the 75th-
     percentile radius of its own entries). For ALL month-ends (population,
     case-control weighted) in the fit period and, crucially, the TEST period
     (2018+, never seen by the clustering): the 3x rate inside the region vs
     the population rate (lift), speed (3x within 12 months, months to 3x),
     5x-in-5y rate, median 24-month return and blow-up rate (worst close
     -50% or worse within 24 months).
  5. Signatures: the features and states that most distinguish each cluster's
     entries, their medians in plain units, and real examples.
Drug developers are analysed separately (binary-event mechanism).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PANEL = "mb_panel.parquet"
LABEL = "t3_24"
FIT_END = pd.Timestamp("2017-12-31")
TEST_END = {"t3_12": "2025-06-30", "t3_24": "2024-06-30", "t3_36": "2023-06-30", "t5_60": "2021-06-30"}
MD = "MULTIBAGGER_LATENT_CLUSTERS.md"

FEATS = [
    # tape
    "r13", "r26", "r52", "r104", "r260", "rs26", "dist_hi52", "dist_hi260", "up_lo52", "range104", "pos104",
    "maxdd104", "vol52", "vol_ratio", "dvol_usd_log", "dvol_trend", "dvol_z13", "updown26", "above_ma30",
    "ma30_slope13", "slope_brk", "trend_r2_52",
    # growth / margins / turning points
    "rev_g1", "rev_g2", "rev_accel", "rev_q_yoy", "rev_q_accel", "ebit_g1", "eps_g1", "gm", "gm_d1", "opm",
    "opm_d1", "opm_d2", "opm_vs_5y", "inc_margin", "npm",
    # cash
    "fcf_margin", "fcf_margin_d1", "cfo_ni", "capex_rev", "capex_rev_d1", "capex_da", "sbc_rev",
    # balance sheet
    "netcash_mcap", "nd_ebitda", "debt_chg1", "current_ratio", "equity_assets", "intang_assets", "ncav_mcap",
    # capital allocation
    "share_g1", "share_g3", "buyback_yield", "div_yield",
    # efficiency
    "roic", "roic_d1", "roe", "asset_turn_d1", "dso_d1", "inv_rev_d1", "rd_rev", "sga_rev", "sga_rev_d1",
    # valuation
    "ps", "ev_sales", "ev_ebit", "pe", "pb", "fcf_yield", "earn_yield", "ps_vs_own", "evs_chg_1y",
    "mcap_usd_log",
    # people
    "emp_g1", "rev_per_emp_g1",
    # perception
    "n_analysts", "buy_share", "buy_share_d12", "upgrades_12m", "downgrades_12m", "months_since_up",
    "beats_4q", "surprise_4q", "ignored_beats_2y", "react_beats_mean", "last_react", "pt_prem_12m",
    "pt_rev_6m", "ins_buy_quarters_4q", "ins_net_buy_4q", "bo_new_holders_12m", "bo_increasing_12m",
]
MISS = {"miss_fund": "rev_g1", "miss_val": "ps", "miss_perc": "n_analysts", "miss_emp": "emp_g1",
        "miss_bs": "netcash_mcap"}
# NARRATIVE AXES: each a composite of ranked features with a direction
# (+1 = higher rank means more of the axis). The clustering's primary space.
BLOCKS = {
    "growth": [("rev_g1", 1), ("rev_g2", 1), ("rev_q_yoy", 1), ("ebit_g1", 1), ("eps_g1", 1)],
    "accelerating": [("rev_accel", 1), ("rev_q_accel", 1)],
    "margin_trajectory": [("opm_d1", 1), ("opm_d2", 1), ("gm_d1", 1), ("fcf_margin_d1", 1), ("roic_d1", 1),
                          ("inc_margin", 1)],
    "profitability": [("opm", 1), ("fcf_margin", 1), ("roic", 1), ("roe", 1)],
    "below_own_cycle": [("opm_vs_5y", -1)],
    "cheapness": [("ps", -1), ("ev_sales", -1), ("ev_ebit", -1), ("pb", -1), ("fcf_yield", 1), ("earn_yield", 1)],
    "cheap_vs_own_history": [("ps_vs_own", -1), ("evs_chg_1y", -1)],
    "balance_sheet": [("netcash_mcap", 1), ("nd_ebitda", -1), ("current_ratio", 1), ("equity_assets", 1),
                      ("ncav_mcap", 1)],
    "deleveraging": [("debt_chg1", -1)],
    "capital_discipline": [("share_g1", -1), ("share_g3", -1), ("buyback_yield", 1), ("sbc_rev", -1)],
    "fallen": [("dist_hi260", -1), ("r104", -1), ("r260", -1), ("maxdd104", -1)],
    "ignition": [("r13", 1), ("rs26", 1), ("dvol_z13", 1), ("dvol_trend", 1), ("above_ma30", 1),
                 ("slope_brk", 1), ("updown26", 1)],
    "volatility": [("vol52", 1)],
    "neglect": [("n_analysts", -1), ("dvol_usd_log", -1)],
    "size": [("mcap_usd_log", 1)],
    "sentiment_warming": [("buy_share_d12", 1), ("upgrades_12m", 1), ("downgrades_12m", -1), ("pt_rev_6m", 1)],
    "insider_activist": [("ins_buy_quarters_4q", 1), ("bo_new_holders_12m", 1), ("bo_increasing_12m", 1)],
    "reinvesting": [("capex_rev", 1), ("capex_rev_d1", 1), ("rd_rev", 1)],
    "headcount_growth": [("emp_g1", 1)],
}


def blocks(R: pd.DataFrame) -> pd.DataFrame:
    """Axis score = mean of its available directed ranks (0.5 = typical);
    missing everywhere -> 0.5 (neutral) and the block-missing flags carry it."""
    B = pd.DataFrame(index=R.index)
    for name, parts in BLOCKS.items():
        cols = [(R[f] if s > 0 else 1 - R[f]) for f, s in parts if f in R.columns]
        B[name] = pd.concat(cols, axis=1).mean(axis=1) if cols else np.nan
    for k in MISS:
        B[k] = R[k]
    return B


READ = [("rev_g1", "rev growth 1y", "pct"), ("rev_accel", "rev accel (pp)", "pct"), ("opm", "op margin", "pct"),
        ("opm_d1", "op margin chg 1y", "pct"), ("fcf_margin", "FCF margin", "pct"), ("ps", "P/S", "x"),
        ("ev_ebit", "EV/EBIT", "x"), ("pb", "P/B", "x"), ("netcash_mcap", "net cash / mcap", "pct"),
        ("nd_ebitda", "net debt / EBITDA", "x"), ("share_g1", "share count chg 1y", "pct"),
        ("roic", "ROIC", "pct"), ("dist_hi260", "price / 5y high", "pct"), ("r52", "return 1y", "pct"),
        ("r104", "return 2y", "pct"), ("vol52", "volatility", "pct"), ("mcap_usd_log", "mcap (log10 $)", "x"),
        ("n_analysts", "analysts", "x"), ("emp_g1", "headcount growth", "pct")]


def _wq(x, w, q):
    o = np.argsort(x)
    cw = np.cumsum(w[o]) / w.sum()
    return float(x[o][np.searchsorted(cw, q)])


def load():
    d = pd.read_parquet(PANEL)
    d["week"] = pd.to_datetime(d["week"])
    d["w_cc"] = d["w_cc"].fillna(1.0)
    from event_study_analyse import bio_flags
    bio = bio_flags(d["symbol"].unique())
    d["bio"] = d["symbol"].map(bio).fillna(False).astype(bool)
    return d


def ranked(d: pd.DataFrame, feats) -> pd.DataFrame:
    """Percentile of each feature within its MONTH and LOCAL MARKET (a story is
    measured against its own market at that moment, so neither a global bull
    run nor one country's bubble can manufacture a cluster)."""
    m = d["week"].dt.to_period("M").astype(str) + "|" + d["market"].astype(str)
    R = pd.DataFrame(index=d.index)
    for f in feats:
        if f in d.columns:
            R[f] = d.groupby(m)[f].rank(pct=True)
    for k, src in MISS.items():
        R[k] = d[src].isna().astype(float) if src in d.columns else 1.0
    st = [c for c in d.columns if c.startswith("st_")]
    for c in st:
        R[c] = d[c].fillna(0)
    return R


def entries(d: pd.DataFrame, label: str) -> pd.Series:
    """First month of each episode of label == 1 (new episode after > 6 months)."""
    e = d.loc[d[label] == 1, ["symbol", "week"]].sort_values(["symbol", "week"])
    gap = e.groupby("symbol")["week"].diff().dt.days
    first = gap.isna() | (gap > 183)
    return pd.Series(first.values, index=e.index).reindex(d.index, fill_value=False)


def region_stats(d, inr, label, period_mask):
    w = d["w_cc"]
    base = d[label].where(period_mask)
    ok = base.notna()
    br = np.average(base[ok], weights=w[ok]) if ok.any() else np.nan
    m = ok & inr
    if m.sum() < 50:
        return {}
    rate = np.average(d.loc[m, label], weights=w[m])
    out = {"share_of_month_ends": float(w[m].sum() / w[ok].sum()), "rate": rate, "lift": rate / br,
           "n_rows": int(m.sum()), "n_events": int(d.loc[m, label].sum())}
    for lab in ("t3_12", "t5_60"):
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


def run(d: pd.DataFrame, label: str = LABEL, tag: str = "", kmax: int = 12, space: str = "blocks"):
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    from sklearn.preprocessing import StandardScaler
    feats = [f for f in FEATS if f in d.columns]
    R = ranked(d, feats)
    S = blocks(R) if space == "blocks" else R
    Xall = S.fillna(0.5).to_numpy(float)
    fit_pop = (d["week"] <= FIT_END).to_numpy()
    rng = np.random.default_rng(7)
    sub = rng.choice(np.where(fit_pop)[0], size=min(200_000, fit_pop.sum()), replace=False)
    sc = StandardScaler().fit(Xall[sub])
    pca = PCA(n_components=(0.999 if space == "blocks" else 0.90), random_state=7).fit(sc.transform(Xall[sub]))
    Z = pca.transform(sc.transform(Xall))
    ent = entries(d, label).to_numpy()
    fit_e = np.where(ent & fit_pop)[0]
    w_e = d["w_cc"].to_numpy()[fit_e]
    Ze = Z[fit_e]
    # choose k: silhouette on the entries + split-half stability (ARI)
    rows = []
    for k in range(3, kmax + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(Ze, sample_weight=w_e)
        s = silhouette_score(Ze, km.labels_, sample_size=min(5000, len(Ze)), random_state=7)
        half = rng.random(len(Ze)) < 0.5
        a = KMeans(n_clusters=k, n_init=5, random_state=1).fit(Ze[half], sample_weight=w_e[half])
        b = KMeans(n_clusters=k, n_init=5, random_state=2).fit(Ze[~half], sample_weight=w_e[~half])
        ari = adjusted_rand_score(a.predict(Ze), b.predict(Ze))
        rows.append({"k": k, "silhouette": s, "stability_ari": ari})
    ksel = pd.DataFrame(rows)
    good = ksel[ksel["stability_ari"] >= 0.60]
    k = int((good if len(good) else ksel).sort_values("silhouette", ascending=False)["k"].iloc[0])
    km = KMeans(n_clusters=k, n_init=20, random_state=7).fit(Ze, sample_weight=w_e)
    # regions
    dist = np.stack([np.linalg.norm(Z - ctr, axis=1) for ctr in km.cluster_centers_], axis=1)
    near = dist.argmin(axis=1)
    rad = np.array([_wq(dist[fit_e[km.labels_ == c], c], w_e[km.labels_ == c], 0.75) for c in range(k)])
    d = d.assign(_cl=near, _in=dist[np.arange(len(d)), near] <= rad[near])
    test_mask = (d["week"] > FIT_END) & (d["week"] <= pd.Timestamp(TEST_END[label]))
    fit_mask = d["week"] <= FIT_END
    ent_s = pd.Series(ent, index=d.index)
    summ, sigs, examples = [], [], []
    for c in range(k):
        inr = (d["_cl"] == c) & d["_in"]
        rec = {"cluster": c, "n_fit_entries": int((km.labels_ == c).sum()),
               "share_of_fit_multibaggers": float(w_e[km.labels_ == c].sum() / w_e.sum())}
        te = ent_s & test_mask
        if te.any():
            rec["share_of_test_multibaggers"] = float(((d["_cl"] == c) & te).sum() / te.sum())
        for nm, msk in (("fit", fit_mask), ("test", test_mask)):
            for key, v in region_stats(d, inr, label, msk).items():
                rec[f"{nm}_{key}"] = v
        summ.append(rec)
        # signature: mean within-month rank among the cluster's entries
        idx = d.index[fit_e[km.labels_ == c]]
        axes = (S.loc[idx, list(BLOCKS)].mean() - S.loc[fit_mask, list(BLOCKS)].mean()) if space == "blocks" else None
        mr = R.loc[idx, feats].mean() - 0.5
        top = pd.concat([mr.sort_values(ascending=False).head(8), mr.sort_values().head(6)])
        stc = [s for s in R.columns if s.startswith("st_")]
        st_in = R.loc[idx, stc].mean()
        st_pop = R.loc[fit_mask, stc].mean()
        st_l = (st_in / st_pop.where(st_pop > 0)).sort_values(ascending=False)
        miss = R.loc[idx, list(MISS)].mean()
        med = {lab: d.loc[idx, col].median() for col, lab, _ in READ if col in d.columns}
        sigs.append({"cluster": c, "top_features": top.round(3).to_dict(),
                     "axes": (axes.sort_values(key=lambda x: -x.abs()).round(3).to_dict() if axes is not None else {}),
                     "states": {s: (round(float(st_in[s]), 3), round(float(st_l[s]), 2)) for s in st_l.index[:8]},
                     "missing": miss.round(2).to_dict(), "medians": med})
        ex = d.loc[d.index[np.concatenate([fit_e[km.labels_ == c]])]].copy()
        ex = ex.assign(fwd=ex["fwd_ret_24"]).sort_values("fwd", ascending=False).head(10)
        examples.append((c, ex[["symbol", "week", "months_to_3x", "fwd_ret_24"]]))
    return {"k": k, "ksel": ksel, "summary": pd.DataFrame(summ), "sigs": sigs, "examples": examples,
            "n_fit_entries": len(fit_e), "tag": tag, "label": label,
            "base_fit": np.average(d.loc[fit_mask & d[label].notna(), label],
                                   weights=d.loc[fit_mask & d[label].notna(), "w_cc"]),
            "base_test": np.average(d.loc[test_mask & d[label].notna(), label],
                                    weights=d.loc[test_mask & d[label].notna(), "w_cc"])}


def state_lift(d: pd.DataFrame, label: str = LABEL) -> pd.DataFrame:
    """Univariate: how much each interpretable STATE multiplies the odds, fit vs test."""
    rows = []
    fit = d["week"] <= FIT_END
    test = (d["week"] > FIT_END) & (d["week"] <= pd.Timestamp(TEST_END[label]))
    for s in [c for c in d.columns if c.startswith("st_")]:
        rec = {"state": s}
        for nm, m in (("fit", fit), ("test", test)):
            ok = m & d[label].notna()
            w = d.loc[ok, "w_cc"]
            br = np.average(d.loc[ok, label], weights=w)
            on = ok & (d[s] == 1)
            if on.sum() >= 100:
                rec[f"{nm}_prevalence"] = float(d.loc[on, "w_cc"].sum() / w.sum())
                rec[f"{nm}_lift"] = float(np.average(d.loc[on, label], weights=d.loc[on, "w_cc"]) / br)
                fm = on & d["fwd_min_24"].notna()
                if fm.sum() >= 100:
                    rec[f"{nm}_p_blowup"] = float(np.average(d.loc[fm, "fwd_min_24"] <= -0.5,
                                                             weights=d.loc[fm, "w_cc"]))
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("test_lift", ascending=False)


def combos(d: pd.DataFrame, label: str = LABEL, min_share: float = 0.003, top: int = 40) -> pd.DataFrame:
    """Pairs and triples of interpretable states: which CONJUNCTIONS precede
    multibagging (fit <= 2017, judged 2018+). Triples extend the 25 best
    fit-period pairs. Minimum support: >= 0.3% of month-ends in both periods."""
    import itertools
    fit = (d["week"] <= FIT_END) & d[label].notna()
    test = (d["week"] > FIT_END) & (d["week"] <= pd.Timestamp(TEST_END[label])) & d[label].notna()
    w = d["w_cc"]
    y = d[label].fillna(0)
    br = {nm: np.average(y[m], weights=w[m]) for nm, m in (("fit", fit), ("test", test))}
    st = [c for c in d.columns if c.startswith("st_")]
    S = {c: (d[c] == 1) for c in st}

    def score(mask):
        rec = {}
        for nm, m in (("fit", fit), ("test", test)):
            on = m & mask
            share = w[on].sum() / w[m].sum()
            if share < min_share or on.sum() < 100:
                return None
            rec[f"{nm}_share"] = share
            rec[f"{nm}_lift"] = np.average(y[on], weights=w[on]) / br[nm]
            fm = on & d["fwd_min_24"].notna()
            rec[f"{nm}_p_blowup"] = np.average(d.loc[fm, "fwd_min_24"] <= -0.5, weights=w[fm]) if fm.sum() >= 50 else np.nan
            fr = on & d["fwd_ret_24"].notna()
            rec[f"{nm}_median_fwd_24m"] = d.loc[fr, "fwd_ret_24"].median() if fr.sum() >= 50 else np.nan
        return rec
    rows = []
    for a, b in itertools.combinations(st, 2):
        r = score(S[a] & S[b])
        if r:
            rows.append({"combo": f"{a[3:]} + {b[3:]}", "n": 2, **r})
    pairs = pd.DataFrame(rows)
    if len(pairs):
        best = pairs.sort_values("fit_lift", ascending=False).head(25)["combo"]
        for cmb in best:
            a, b = ["st_" + x for x in cmb.split(" + ")]
            for c in st:
                if c in (a, b):
                    continue
                r = score(S[a] & S[b] & S[c])
                if r:
                    rows.append({"combo": " + ".join(sorted([a[3:], b[3:], c[3:]])), "n": 3, **r})
    out = pd.DataFrame(rows).drop_duplicates("combo")
    # robust = strong in the fit period AND still strong out of sample
    out["min_lift"] = out[["fit_lift", "test_lift"]].min(axis=1)
    return out.sort_values("min_lift", ascending=False).head(top)


def tree_recipes(d: pd.DataFrame, label: str = LABEL, depth: int = 4) -> pd.DataFrame:
    """A shallow decision tree on the NARRATIVE AXES (fit <= 2017): each leaf
    is a readable recipe; its lift is re-measured on 2018+."""
    from sklearn.tree import DecisionTreeClassifier
    feats = [f for f in FEATS if f in d.columns]
    B = blocks(ranked(d, feats)).fillna(0.5)
    fit = (d["week"] <= FIT_END) & d[label].notna()
    test = (d["week"] > FIT_END) & (d["week"] <= pd.Timestamp(TEST_END[label])) & d[label].notna()
    w = d["w_cc"]
    clf = DecisionTreeClassifier(max_depth=depth, min_weight_fraction_leaf=0.01, class_weight="balanced",
                                 random_state=7)
    clf.fit(B[fit], d.loc[fit, label], sample_weight=w[fit])
    leaf = pd.Series(clf.apply(B), index=d.index)
    tr = clf.tree_
    names = list(B.columns)
    # path text per leaf
    paths = {}

    def walk(node, conds):
        if tr.children_left[node] == -1:
            paths[node] = " & ".join(conds) or "all"
            return
        f, th = names[tr.feature[node]], tr.threshold[node]
        walk(tr.children_left[node], conds + [f"{f} <= {th:.2f}"])
        walk(tr.children_right[node], conds + [f"{f} > {th:.2f}"])
    walk(0, [])
    y = d[label].fillna(0)
    br = {nm: np.average(y[m], weights=w[m]) for nm, m in (("fit", fit), ("test", test))}
    rows = []
    for lf, path in paths.items():
        rec = {"leaf": lf, "recipe": path}
        for nm, m in (("fit", fit), ("test", test)):
            on = m & (leaf == lf)
            if on.sum() < 50:
                continue
            rec[f"{nm}_share"] = w[on].sum() / w[m].sum()
            rec[f"{nm}_lift"] = np.average(y[on], weights=w[on]) / br[nm]
            fm = on & d["fwd_min_24"].notna()
            if fm.sum() >= 50:
                rec[f"{nm}_p_blowup"] = np.average(d.loc[fm, "fwd_min_24"] <= -0.5, weights=w[fm])
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("test_lift", ascending=False)


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    return f"{v:.0%}" if kind == "pct" else f"{v:.2f}"


def report(res_main, res_12, res_bio, sl, d, res_full=None, combos_df=None, tree_df=None):
    L = []
    L.append("# What precedes multibagging — latent clusters of pre-conditions\n")
    L.append(f"Sample: {d['symbol'].nunique():,} symbols (case-control, weighted to the population), "
             f"{len(d):,} liquid month-ends (>= $250k/week USD), {d['week'].min():%Y-%m} to {d['week'].max():%Y-%m}. "
             "Every feature is point-in-time (statements on filing date). A multibagger = a 3x reached AND held "
             "for 4 weeks; the ENTRY is the first month of each episode (the state before the run). Clusters are "
             "fit on entries up to 2017 and judged on 2018+ month-ends they never saw.\n")
    for res in (res_main, res_12, res_full):
        if res is None:
            continue
        lab = res["label"]
        L.append(f"\n## {res['tag']}\n")
        L.append(f"- entries (fit period): {res['n_fit_entries']:,}; base rate fit {res['base_fit']:.2%}, "
                 f"test {res['base_test']:.2%}")
        L.append(f"- k chosen = {res['k']} (silhouette, split-half stability >= 0.6):\n")
        L.append(res["ksel"].round(3).to_markdown(index=False))
        s = res["summary"]
        cols = [c for c in ["cluster", "share_of_fit_multibaggers", "share_of_test_multibaggers",
                            "fit_share_of_month_ends", "fit_lift", "test_lift", "test_rate", "test_t3_12_rate",
                            "test_t5_60_rate", "test_median_months_to_3x", "test_median_fwd_24m",
                            "test_p_blowup_50", "test_n_events"] if c in s.columns]
        L.append("\n" + s[cols].sort_values("test_lift", ascending=False).round(3).to_markdown(index=False) + "\n")
        for sg in res["sigs"]:
            c = sg["cluster"]
            L.append(f"\n### Cluster {c}\n")
            if sg.get("axes"):
                L.append("- NARRATIVE AXES vs all month-ends (+ = more): " +
                         ", ".join(f"{k} {v:+.2f}" for k, v in list(sg["axes"].items())[:10]))
            L.append("- distinguishing features (mean within-month rank minus 0.5; + = high): " +
                     ", ".join(f"{k} {v:+.2f}" for k, v in sg["top_features"].items()))
            L.append("- states (share of entries, lift vs all month-ends): " +
                     ", ".join(f"{k[3:]} {v[0]:.0%} ({v[1]:.1f}x)" for k, v in sg["states"].items()))
            L.append("- data present: " + ", ".join(f"{k[5:]} {1 - v:.0%}" for k, v in sg["missing"].items()))
            L.append("- medians at entry: " + "; ".join(
                f"{lab} {_fmt(sg['medians'].get(lab), kind)}" for _, lab, kind in READ if lab in sg["medians"]))
            ex = dict(res["examples"])[c]
            L.append("- examples (entry month, months to 3x, 24m return): " + "; ".join(
                f"{r.symbol} {r.week:%Y-%m} ({_fmt(r.months_to_3x, 'x')}m, {_fmt(r.fwd_ret_24, 'pct')})"
                for r in ex.itertuples()))
    if combos_df is not None and len(combos_df):
        L.append("\n## Conjunctions of states (pairs / triples) — robust = strong in BOTH periods\n")
        L.append(combos_df.round(3).to_markdown(index=False))
    if tree_df is not None and len(tree_df):
        L.append("\n## Decision-tree recipes on the narrative axes (fit <= 2017, lift re-measured 2018+)\n")
        L.append(tree_df.round(3).to_markdown(index=False))
    L.append("\n## Interpretable states — univariate lift on the 3x-in-24m outcome\n")
    L.append(sl.round(3).to_markdown(index=False))
    if res_bio is not None:
        L.append(f"\n## Drug developers (separate)\n\n- base rate fit {res_bio['base_fit']:.2%}, test "
                 f"{res_bio['base_test']:.2%}; k = {res_bio['k']}\n")
        s = res_bio["summary"]
        cols = [c for c in ["cluster", "share_of_fit_multibaggers", "fit_lift", "test_lift", "test_median_fwd_24m",
                            "test_p_blowup_50"] if c in s.columns]
        L.append(s[cols].round(3).to_markdown(index=False))
    L.append("\n## Caveats\n\n- Case-control sample of 10,160 symbols weighted to the population; delisted names "
             "are included where FMP serves their prices (delisting is an observed outcome, not a gap).\n"
             "- Valuation = FMP's period-end market cap / EV rolled forward by the price move since the period "
             "end (currency-consistent with the statements); a mcap/revenue outside 0.01-200x is treated as a "
             "currency mismatch and dropped.\n- Perception data start 2017-2019 and cover a minority of names; "
             "their absence is a feature (miss_perc), not an error.\n- Clusters describe where multibaggers CAME "
             "FROM; the region lift says whether being in that state raises the odds for everyone in it.")
    open(MD, "w").write("\n".join(L))


def main():
    d = load()
    nb = d[~d["bio"]].copy()
    res = run(nb, LABEL, "Main: 3x within 24 months (non-biotech)")
    res12 = run(nb, "t3_12", "Fast: 3x within 12 months (non-biotech)")
    resf = run(nb, LABEL, "Cross-check: 3x within 24 months, all ~100 ranked features (non-biotech)",
               space="full")
    resf["summary"].to_csv("mb_clusters_fullspace_summary.csv", index=False)
    bio = d[d["bio"]].copy()
    resb = run(bio, LABEL, "Biotech", kmax=6) if (bio[LABEL] == 1).sum() >= 200 else None
    sl = state_lift(nb)
    cb = combos(nb)
    cb.to_csv("mb_state_combos.csv", index=False)
    tr = tree_recipes(nb)
    tr.to_csv("mb_tree_recipes.csv", index=False)
    res["summary"].to_csv("mb_clusters_summary.csv", index=False)
    res12["summary"].to_csv("mb_clusters_fast_summary.csv", index=False)
    sl.to_csv("mb_state_lift.csv", index=False)
    report(res, res12, resb, sl, d, resf, cb, tr)
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
