"""Second forensic investigation: how to raise the lift beyond the nine
archetypes -> MULTIBAGGER_LIFT2.md

On the full point-in-time panel (mb_panel.parquet), each archetype is applied
as the study defined it, then interrogated:

  1. REFINEMENT   inside each archetype's members, which further condition
                  (any feature top / bottom fifth, any state) raises the rate
                  most — and which lowers it (what to avoid). Conditional
                  lift = rate inside the sub-group / rate inside the archetype,
                  with a support floor and blow-up alongside.
  2. TIMING       within the fallen family: does the age of the low matter (a
                  fresh 5-year low vs one 3-12 months old), the share of the
                  last 5 years spent in drawdown, and the sign of the last 13
                  weeks — where in the bottoming process the odds peak.
  3. REGIME       the market's own 26-week return at entry (the month x market
                  median the panel already carries) — bear-market entries vs
                  bull-market entries; and lift by year, to see what only
                  worked in 2020.
  4. WHERE        lift by sector and by market inside each archetype: is the
                  archetype general, or a name for one country / sector wave?
  5. INTERSECTION pairwise co-membership: does A AND B beat either alone?
  6. THE TAIL     which conditions cut the blow-up rate while keeping the lift
                  (the shape of a better-loaded ticket), and which raise the
                  10x rate among the 3x winners (the magnitude question)
  7. THE CEILING  a gradient-boosted model on all features INSIDE the fallen
                  population: the lift of its top 1% / 5% each month — how
                  much is attainable beyond rules, and which features it leans
                  on; fit on 2012-2018, judged on 2019+ so the ceiling is real
Every table carries blow-up (worst close -50% within 24 months) beside the lift.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc

MD = "MULTIBAGGER_LIFT2.md"
LABEL = "t3_24"


def archetypes(d: pd.DataFrame) -> dict:
    g = lambda c: d[c] if c in d.columns else pd.Series(np.nan, index=d.index)
    fallen = g("dist_hi260") <= 0.40
    deep = ((g("ev_ebit").between(0, 6)) | (g("pb").between(0, 0.7, inclusive="right")) | (g("ps") <= 0.3))
    fcf_not_turned = ~(g("tr_fcfm_streak") > 1)
    ins2 = g("ins_buy_quarters_4q") >= 2
    operating = ~(g("ncav_mcap") >= 0.5)
    inconsistent = ~(g("tr_opm_consist") > 0.5)
    few = g("n_analysts").between(1, 5)
    believers = g("buy_share") >= 0.6
    noyield = ~(g("div_yield") > 0.02)
    smart = (ins2.astype(int) + (g("bo_new_holders_12m") >= 1).astype(int) + (g("emp_g1") >= 0.10).astype(int))
    weak_tape = (g("r13") < 0) & (g("dist_hi52") < 0.85)
    margin_up = ((g("tr_opm_slope8") > 0) & (g("tr_opm_consist") >= 0.6)) | (g("st_margin_inflect_derated") == 1)
    roic_up = g("tr_roic_slope8") > 0
    growing = (g("rev_accel") > 0) | (g("rev_g1") >= 0.10)
    cheap_own = (g("evs_chg_1y") < 0) | (g("ps_vs_own") < 1.0)
    m = d["week"].dt.to_period("M").astype(str) + "|" + d["market"].astype(str)
    rk = lambda x: x.groupby(m).rank(pct=True)
    r_vol, r_size = rk(g("vol52")), rk(g("mcap_usd_log"))
    r_fallen, r_prof = rk(1 - g("dist_hi260")), rk(g("opm"))
    r_cheap = rk(-g("ps").where(g("ps") > 0))
    signs = ((g("st_accelerating") == 1).astype(int) + (g("st_margin_inflect_derated") == 1).astype(int)
             + (g("st_turnaround") == 1).astype(int) + (g("share_g1") <= -0.02).astype(int))
    not_ignited = (g("dist_hi52") < 0.90) & ~(g("dvol_z13") >= 1.5) & ~(g("r13") > 0.15)
    return {
        "left_for_dead_value": fallen & deep & fcf_not_turned,
        "fallen_insider_conviction": fallen & ins2 & operating & inconsistent,
        "fallen_ignored_believers": fallen & few & believers & noyield,
        "smart_money_wreckage": fallen & deep & (smart >= 1),
        "fallen_below_cycle": (g("dist_hi260") <= 0.5) & (g("opm_vs_5y") <= -0.02) & cheap_own,
        "margin_inflect_weak_tape": growing & margin_up & roic_up & weak_tape & cheap_own,
        "tree_recipe": (r_vol >= 0.60) & (r_size <= 0.13) & (r_fallen >= 0.83) & (r_prof <= 0.46),
        "tree_recipe_10x": (r_vol >= 0.62) & (r_size <= 0.12) & (r_cheap >= 0.46) & (r_prof <= 0.45),
        "sequence_preignition": (signs >= 2) & not_ignited,
    }


def stats(d, mask, label=LABEL):
    w = d["w_cc"]
    ok = d[label].notna() & mask
    if ok.sum() < 40:
        return None
    rate = np.average(d.loc[ok, label], weights=w[ok])
    out = {"n": int(ok.sum()), "events": int(d.loc[ok, label].sum()), "rate": rate}
    fm = ok & d["fwd_min_24"].notna()
    out["p_blowup_50"] = float(np.average(d.loc[fm, "fwd_min_24"] <= -0.5, weights=w[fm])) if fm.sum() >= 40 else np.nan
    t10 = ok & d["t10_60"].notna()
    out["t10_60_rate"] = float(np.average(d.loc[t10, "t10_60"], weights=w[t10])) if t10.sum() >= 40 else np.nan
    fr = ok & d["fwd_ret_24"].notna()
    out["median_fwd_24m"] = float(d.loc[fr, "fwd_ret_24"].median()) if fr.sum() >= 40 else np.nan
    return out


def conditions(d, R):
    C, names = [], []
    feats = [c for c in R.columns if not c.startswith("st_") and c not in mc.MISS]
    for f in feats:
        r = R[f].to_numpy()
        C.append(r <= 0.2); names.append(f"{f} LOW")
        C.append(r >= 0.8); names.append(f"{f} HIGH")
    for s in [c for c in R.columns if c.startswith("st_")]:
        C.append(R[s].to_numpy() == 1); names.append(s[3:])
    return np.vstack([np.nan_to_num(c, nan=0).astype(bool) for c in C]), names


def refine(d, M, names, mask, base_rate, label=LABEL, min_n=150, min_events=25, top=12):
    y = d[label].to_numpy(float); ok = ~np.isnan(y) & mask.to_numpy()
    w = d["w_cc"].to_numpy(float) * ok; y = np.nan_to_num(y)
    fm = d["fwd_min_24"].to_numpy(float); blow = (fm <= -0.5).astype(float); okb = ~np.isnan(fm)
    rows = []
    for i, nm in enumerate(names):
        m = M[i] & ok
        n = int(m.sum()); ev = int((y[m] > 0).sum())
        if n < min_n or ev < min_events:
            continue
        rate = (w[m] * y[m]).sum() / w[m].sum()
        mb = m & okb
        pb = (w[mb] * blow[mb]).sum() / w[mb].sum() if mb.sum() >= 40 else np.nan
        rows.append({"condition": nm, "n": n, "events": ev, "rate": rate, "lift_vs_archetype": rate / base_rate,
                     "p_blowup_50": pb})
    r = pd.DataFrame(rows).sort_values("lift_vs_archetype", ascending=False)
    return r.head(top), r.tail(top).sort_values("lift_vs_archetype")


def by_group(d, mask, key, label=LABEL, min_n=200):
    w = d["w_cc"]; ok = d[label].notna() & mask
    br = np.average(d.loc[ok, label], weights=w[ok])
    rows = []
    for k, idx in d[ok].groupby(key).groups.items():
        if len(idx) < min_n:
            continue
        s = stats(d.loc[idx], pd.Series(True, index=idx), label)
        if s:
            rows.append({key: k, **s, "lift_vs_archetype": s["rate"] / br})
    return pd.DataFrame(rows).sort_values("lift_vs_archetype", ascending=False)


def ceiling(d, mask, label=LABEL):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    feats = mc.feats_all(d)
    X = mc.ranked(d, feats)
    X = X.loc[:, ~X.columns.duplicated()]
    y = d[label]
    ok = y.notna() & mask
    fit = ok & (d["week"] <= "2018-12-31"); test = ok & (d["week"] > "2018-12-31")
    # a feature constant (or all-missing) inside the fit rows breaks the
    # histogram binner (it needs >= 2 distinct values to place a threshold)
    X = X.loc[:, X[fit].nunique(dropna=True) > 1]
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=100,
                                         random_state=7)
    clf.fit(X[fit], y[fit], sample_weight=d.loc[fit, "w_cc"])
    p = pd.Series(clf.predict_proba(X[test])[:, 1], index=X[test].index)
    base = np.average(y[test], weights=d.loc[test, "w_cc"])
    out = {"auc_2019plus": float(roc_auc_score(y[test], p, sample_weight=d.loc[test, "w_cc"])), "base_2019plus": base}
    m = d.loc[test, "week"].dt.to_period("M")
    for q in (0.01, 0.05, 0.20):
        sel = p[p.groupby(m).transform(lambda s: s >= s.quantile(1 - q))].index
        out[f"lift_top_{int(q*100)}pct"] = float(np.average(y[sel], weights=d.loc[sel, "w_cc"]) / base)
        fm = d.loc[sel, "fwd_min_24"].dropna()
        out[f"blowup_top_{int(q*100)}pct"] = float((fm <= -0.5).mean()) if len(fm) else np.nan
    from sklearn.inspection import permutation_importance
    sub = test[test].index
    sub = np.random.default_rng(7).choice(sub, size=min(60000, len(sub)), replace=False)
    imp = permutation_importance(clf, X.loc[sub], y.loc[sub], n_repeats=3, random_state=7, scoring="roc_auc")
    out["top_features"] = pd.Series(imp.importances_mean, index=X.columns).sort_values(ascending=False).head(20)
    return out


def main():
    d = mc.load()
    d = d[~d["bio"]].reset_index(drop=True)
    if "fwd_mult_60" in d.columns:
        d["t10_60"] = (d["fwd_mult_60"] >= 10).astype(float).where(d["fwd_mult_60"].notna())
    d["market_r26"] = d["r26"] - d["rs26"]                 # the month x market median the panel carries
    d["year"] = d["week"].dt.year
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "sector"], low_memory=False).drop_duplicates("symbol")
    d = d.merge(g, on="symbol", how="left")
    A = archetypes(d)
    R = mc.ranked(d, mc.feats_all(d)); R = R.loc[:, ~R.columns.duplicated()]
    M, names = conditions(d, R)
    base_all = stats(d, pd.Series(True, index=d.index))["rate"]
    L = ["# Raising the lift — a second forensic investigation\n",
         f"{len(d):,} liquid month-ends, {d['symbol'].nunique():,} symbols (non-biotech). Base rate of a 3x within "
         f"24 months: {base_all:.2%}. Each archetype is applied exactly as defined on the point-in-time panel; "
         "'lift vs archetype' is the sub-group's rate over the archetype's own rate.\n"]
    summ = []
    for name, mask in A.items():
        s = stats(d, mask)
        if not s:
            continue
        s["archetype"] = name; s["lift"] = s["rate"] / base_all; summ.append(s)
    S = pd.DataFrame(summ)[["archetype", "n", "events", "rate", "lift", "t10_60_rate", "p_blowup_50", "median_fwd_24m"]]
    L.append("## The nine archetypes on the panel\n"); L.append(S.round(3).to_markdown(index=False))
    for name, mask in A.items():
        s = stats(d, mask)
        if not s or s["events"] < 100:
            continue
        L.append(f"\n## {name}  (rate {s['rate']:.2%}, lift {s['rate']/base_all:.2f}x, blow-up {s['p_blowup_50']:.0%})\n")
        up, down = refine(d, M, names, mask, s["rate"])
        L.append("### 1. Refinements that RAISE the odds inside the archetype\n")
        L.append(up.round(3).to_markdown(index=False))
        L.append("\n### ...and conditions to AVOID (lowest conditional lift)\n")
        L.append(down.round(3).to_markdown(index=False))
        # timing (fallen family)
        if name in ("left_for_dead_value", "fallen_insider_conviction", "fallen_ignored_believers",
                    "smart_money_wreckage", "fallen_below_cycle", "tree_recipe"):
            t = d.loc[mask].copy()
            t["low_age"] = pd.cut(t["wks_since_lo260"], [-1, 8, 26, 52, 104, 400],
                                  labels=["<2m", "2-6m", "6-12m", "1-2y", ">2y"])
            t["dd_time"] = pd.cut(t["dd_time_share_260"], [-0.01, 0.5, 0.8, 1.01], labels=["<50%", "50-80%", ">80%"])
            t["r13_sign"] = np.where(t["r13"] > 0, "13w up", "13w down")
            L.append("\n### 2. Timing inside the bottoming process\n")
            for key in ("low_age", "dd_time", "r13_sign"):
                bg = by_group(t, pd.Series(True, index=t.index), key)
                if len(bg):
                    L.append(f"\n*{key}*\n\n" + bg[[key, "n", "events", "rate", "lift_vs_archetype", "p_blowup_50",
                                                    "t10_60_rate"]].round(3).to_markdown(index=False))
        # regime and year
        t = d.loc[mask].copy()
        t["regime"] = pd.cut(t["market_r26"], [-1, -0.15, -0.05, 0.05, 0.15, 5],
                             labels=["bear (<-15%)", "weak", "flat", "firm", "bull (>+15%)"])
        L.append("\n### 3. Regime at entry (the market's own 26-week return) and year\n")
        bg = by_group(t, pd.Series(True, index=t.index), "regime")
        if len(bg):
            L.append(bg[["regime", "n", "events", "rate", "lift_vs_archetype", "p_blowup_50"]].round(3).to_markdown(index=False))
        by = by_group(t, pd.Series(True, index=t.index), "year", min_n=100)
        if len(by):
            L.append("\n" + by.sort_values("year")[["year", "n", "events", "rate", "lift_vs_archetype", "p_blowup_50"]]
                     .round(3).to_markdown(index=False))
        # where
        L.append("\n### 4. Where the lift lives — sector and market\n")
        for key in ("sector", "market"):
            bg = by_group(t, pd.Series(True, index=t.index), key, min_n=150)
            if len(bg):
                L.append(f"\n*{key}*\n\n" + bg.head(12)[[key, "n", "events", "rate", "lift_vs_archetype",
                                                          "p_blowup_50"]].round(3).to_markdown(index=False))
        # tail: conditions that cut blow-up while keeping lift; 10x among winners
        L.append("\n### 6. The tail — cutting the blow-up while keeping the lift\n")
        y = d[LABEL]; okm = mask & y.notna()
        fm = d["fwd_min_24"]
        rows = []
        for i, nm in enumerate(names):
            m = okm & M[i]
            if m.sum() < 150 or y[m].sum() < 25:
                continue
            rate = np.average(y[m], weights=d.loc[m, "w_cc"])
            mb = m & fm.notna()
            pb = float(np.average(fm[mb] <= -0.5, weights=d.loc[mb, "w_cc"]))
            rows.append({"condition": nm, "n": int(m.sum()), "rate": rate, "lift_vs_archetype": rate / s["rate"],
                         "p_blowup_50": pb, "blowup_change": pb - s["p_blowup_50"]})
        tail = pd.DataFrame(rows)
        if len(tail):
            good = tail[(tail["lift_vs_archetype"] >= 1.0)].sort_values("blowup_change").head(10)
            L.append(good.round(3).to_markdown(index=False))
        win = mask & (d[LABEL] == 1) & d["t10_60"].notna()
        if win.sum() >= 200:
            rows = []
            for i, nm in enumerate(names):
                m = win & M[i]
                if m.sum() < 60:
                    continue
                rows.append({"condition": nm, "n": int(m.sum()),
                             "p_10x_given_3x": float(d.loc[m, "t10_60"].mean())})
            tt = pd.DataFrame(rows)
            if len(tt):
                base10 = float(d.loc[win, "t10_60"].mean())
                L.append(f"\n*Among the archetype's 3x winners, P(10x within 5y) = {base10:.1%}; conditions that raise it:*\n")
                L.append(tt.sort_values("p_10x_given_3x", ascending=False).head(10).round(3).to_markdown(index=False))
    # intersections
    L.append("\n## 5. Intersections — does A and B beat either alone?\n")
    rows = []
    keys = list(A)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            both = A[keys[i]] & A[keys[j]]
            s = stats(d, both)
            if s and s["events"] >= 25:
                si, sj = stats(d, A[keys[i]]), stats(d, A[keys[j]])
                rows.append({"A": keys[i], "B": keys[j], "n": s["n"], "events": s["events"],
                             "lift_A": si["rate"] / base_all, "lift_B": sj["rate"] / base_all,
                             "lift_AB": s["rate"] / base_all, "p_blowup_AB": s["p_blowup_50"],
                             "t10_60_AB": s["t10_60_rate"]})
    if rows:
        L.append(pd.DataFrame(rows).sort_values("lift_AB", ascending=False).round(3).to_markdown(index=False))
    # ceiling
    L.append("\n## 7. The ceiling — a gradient-boosted model inside the fallen population\n")
    fallen_pop = d["dist_hi260"] <= 0.5
    try:
        c = ceiling(d, fallen_pop)
        L.append(f"Fit 2012-2018, judged 2019+ (base rate there {c['base_2019plus']:.2%}, AUC {c['auc_2019plus']:.3f}): "
                 f"lift of the top 1% / 5% / 20% each month = {c['lift_top_1pct']:.2f}x / {c['lift_top_5pct']:.2f}x / "
                 f"{c['lift_top_20pct']:.2f}x; blow-up there {c['blowup_top_1pct']:.0%} / {c['blowup_top_5pct']:.0%} / "
                 f"{c['blowup_top_20pct']:.0%}.\n")
        L.append("Features the model leans on (permutation importance):\n")
        L.append(c["top_features"].round(4).to_frame("importance").to_markdown())
    except Exception as exc:
        L.append(f"(ceiling model failed: {exc})")
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
