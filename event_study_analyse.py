"""Stage C of the base-breakout event study: what, measured at the end of a
flat two-year base, preceded an explosion?

Input : base_panel_pit.parquet (stage A + B), base_premise.csv
Output: BACKTEST_BASE_BREAKOUT.md (+ base_breakout_lift.csv, base_breakout_clusters.csv)

Method (each step guards a specific way event studies fool themselves):
  1. PREMISE     of all liquid 13w doublers, what share came out of a base?
                 (if few do, the archetype chases a rare path)
  2. BASE RATE   P(event | base) — every lift is relative to this
  3. UNIVARIATE  event rate by feature quintile (cut points from the TRAIN
                 period only), split by period / size / region, with the
                 COST of non-events (median 52w return, P(52w drawdown <= -40%))
  4. EPISODES    overlapping month-ends of one breakout are one episode: counts
                 of distinct symbols and distinct episodes are reported so a
                 single stock repeated 6 times cannot pass as evidence
  5. MODEL       L2 logistic on train-period quintile ranks (+ missing flags),
                 fitted <= 2018, tested 2019+: AUC, precision / lift in the top
                 1% / 5%, per test year
  6. CLUSTERS    k-means on rank-transformed features, fitted on TRAIN base
                 months; event rate per cluster in TRAIN and TEST (a cluster is
                 only a candidate archetype if its lift holds out of sample),
                 plus a typology of the events themselves
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PANEL = "base_panel_pit.parquet"
SPLIT = pd.Timestamp("2019-01-01")
EVENTS = ["ev2x_13w", "ev3x_13w", "ev2x_26w"]
PRICE_F = ["vol_ratio", "range_ratio", "pos_in_range", "dist_high", "lows_slope", "r13", "r26",
           "updown_vol", "obv_div", "dvol_trend", "rs26", "prior_dd", "base_len_36", "size_dvol"]
FUND_F = ["rev_g_base", "ebit_g_base", "ebit_turned", "gm_delta_base", "rev_accel", "coil_rev", "coil_ebit"]
PERC_F = ["n_analysts", "buy_share", "buy_share_d12", "upgrades_12m", "downgrades_12m",
          "initiations_12m", "months_since_up", "beats_4q", "surprise_4q"]


def _q_edges(train: pd.Series, q=5):
    x = train.dropna()
    if x.nunique() < 3:
        return None
    return np.unique(np.quantile(x, np.linspace(0, 1, q + 1)))


def _bucket(x: pd.Series, edges):
    if edges is None or len(edges) < 3:
        return pd.Series(np.nan, index=x.index)
    return pd.Series(np.clip(np.searchsorted(edges[1:-1], x, side="right"), 0, len(edges) - 2),
                     index=x.index).where(x.notna())


def episodes(d: pd.DataFrame, ev: str) -> pd.Series:
    """Episode id: event month-ends of one symbol within 26 weeks of each other."""
    e = d[d[ev] == 1].sort_values(["symbol", "week"])
    new = (e["symbol"] != e["symbol"].shift()) | ((e["week"] - e["week"].shift()).dt.days > 182)
    return new.cumsum().reindex(d.index)


def lift_table(d, feats, ev="ev2x_13w"):
    tr = d["week"] < SPLIT
    base = d[ev].mean()
    rows = []
    for f in feats:
        if f not in d.columns or d[f].notna().mean() < 0.02:
            continue
        edges = _q_edges(d.loc[tr, f])
        b = _bucket(d[f], edges)
        for part, m in (("all", slice(None)), ("train", tr), ("test", ~tr)):
            dd = d[m] if not isinstance(m, slice) else d
            bb = b[m] if not isinstance(m, slice) else b
            for q in sorted(bb.dropna().unique()):
                s = dd[bb == q]
                if len(s) < 200:
                    continue
                rows.append({"feature": f, "part": part, "quintile": int(q) + 1, "n": len(s),
                             "events": int(s[ev].sum()), "symbols_w_event": s.loc[s[ev] == 1, "symbol"].nunique(),
                             "rate": s[ev].mean(), "lift": s[ev].mean() / base if base else np.nan,
                             "med_fwd52": s["fwd_52w"].median(), "p_dd40": (s["fwd_dd_52w"] <= -0.40).mean(),
                             "coverage": d[f].notna().mean()})
    return pd.DataFrame(rows)


def rank_matrix(d, feats, train_mask):
    X = pd.DataFrame(index=d.index)
    for f in feats:
        if f not in d.columns or d[f].notna().mean() < 0.02:
            continue
        edges = _q_edges(d.loc[train_mask, f], q=10)
        b = _bucket(d[f], edges)
        X[f] = (b / max(1, (len(edges) - 2) if edges is not None else 1)).fillna(0.5)
        # missing-ness is informative only where "absent" is a real state
        # (no analyst coverage, no filings yet). For PRICE features a NaN
        # means a zero-volume / gappy series — the model learned to bet on
        # that data artifact (+4 weight), so no flag is offered for them.
        if f not in PRICE_F:
            X[f + "_na"] = d[f].isna().astype(float)
    return X


def model(d, feats, ev="ev2x_13w"):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    tr = (d["week"] < SPLIT) & d[ev].notna()
    te = (d["week"] >= SPLIT) & d[ev].notna()
    X = rank_matrix(d, feats, tr)
    m = LogisticRegression(C=0.3, max_iter=2000, class_weight="balanced")
    m.fit(X[tr], d.loc[tr, ev])
    p = pd.Series(m.predict_proba(X)[:, 1], index=d.index)
    res = {"auc_train": roc_auc_score(d.loc[tr, ev], p[tr]) if d.loc[tr, ev].nunique() > 1 else np.nan,
           "auc_test": roc_auc_score(d.loc[te, ev], p[te]) if d.loc[te, ev].nunique() > 1 else np.nan,
           "base_test": d.loc[te, ev].mean()}
    for top in (0.01, 0.05, 0.10):
        # precision within each month's top slice (a deployable, cross-sectional rank)
        dt = d[te].assign(p=p[te])
        dt["rk"] = dt.groupby(dt["week"].dt.to_period("M"))["p"].rank(pct=True, ascending=False)
        sel = dt[dt["rk"] <= top]
        res[f"prec_top{int(top*100)}"] = sel[ev].mean()
        res[f"lift_top{int(top*100)}"] = sel[ev].mean() / res["base_test"] if res["base_test"] else np.nan
        res[f"n_top{int(top*100)}"] = len(sel)
        res[f"med_fwd52_top{int(top*100)}"] = sel["fwd_52w"].median()
    coef = pd.Series(m.coef_[0], index=X.columns).sort_values()
    return res, coef, p


def clusters(d, feats, ev="ev2x_13w", k=10):
    from sklearn.cluster import KMeans
    tr = d["week"] < SPLIT
    X = rank_matrix(d, feats, tr)
    X = X[[c for c in X.columns if not c.endswith("_na")]]
    km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(X[tr])
    lab = pd.Series(km.predict(X), index=d.index)
    base_tr, base_te = d.loc[tr, ev].mean(), d.loc[~tr, ev].mean()
    rows = []
    for c in range(k):
        m = lab == c
        cen = pd.Series(km.cluster_centers_[c], index=X.columns)
        top = cen.sub(0.5).abs().sort_values(ascending=False).head(5)
        rows.append({"cluster": c, "n": int(m.sum()),
                     "rate_train": d.loc[m & tr, ev].mean(), "lift_train": d.loc[m & tr, ev].mean() / base_tr,
                     "rate_test": d.loc[m & ~tr, ev].mean(), "lift_test": d.loc[m & ~tr, ev].mean() / base_te,
                     "events_test": int(d.loc[m & ~tr, ev].sum()),
                     "med_fwd52": d.loc[m, "fwd_52w"].median(),
                     "p_dd40": (d.loc[m, "fwd_dd_52w"] <= -0.40).mean(),
                     "signature": "; ".join(f"{f} {'HIGH' if cen[f] > 0.5 else 'LOW'} ({cen[f]:.2f})"
                                            for f in top.index)})
    # typology of the events themselves
    e = d[d[ev] == 1]
    Xe = X.loc[e.index]
    ke = min(6, max(2, len(e) // 150))
    kme = KMeans(n_clusters=ke, n_init=10, random_state=7).fit(Xe)
    typ = []
    for c in range(ke):
        cen = pd.Series(kme.cluster_centers_[c], index=X.columns)
        top = cen.sub(0.5).abs().sort_values(ascending=False).head(6)
        typ.append({"type": c, "events": int((kme.labels_ == c).sum()),
                    "symbols": e.loc[kme.labels_ == c, "symbol"].nunique(),
                    "signature": "; ".join(f"{f} {'HIGH' if cen[f] > 0.5 else 'LOW'} ({cen[f]:.2f})"
                                           for f in top.index)})
    return pd.DataFrame(rows).sort_values("lift_train", ascending=False), pd.DataFrame(typ)


def main():
    d = pd.read_parquet(PANEL)
    d = d[d["ev2x_13w"].notna()].copy()
    prem = pd.read_csv("base_premise.csv")
    feats = [f for f in PRICE_F + FUND_F + PERC_F if f in d.columns]
    L = []
    L.append("# Base-breakout event study — 'goes nowhere for 2 years, then triples in 3 months'\n")
    # 1 premise
    L.append("## 1. Premise: how often does an explosion come out of a flat base?\n")
    for a, b, lbl in (("ev2x", "ev2x_in_base", "2x in 13w, strict base"),
                      ("ev2x", "ev2x_in_loose_base", "2x in 13w, loose base (|r104|<=35%, range<=2.5x)"),
                      ("ev3x", "ev3x_in_base", "3x in 13w, strict base")):
        tot, inb = prem[a].sum(), prem[b].sum()
        L.append(f"- {lbl}: {inb:,} of {tot:,} liquid event month-ends ({inb / max(tot, 1):.1%})")
    L.append(f"- liquid month-ends overall: {prem['liquid_months'].sum():,}\n")
    # 2 base rates
    L.append("## 2. Base rates within flat bases\n")
    L.append(f"- base-months: {len(d):,}; symbols: {d['symbol'].nunique():,}; "
             f"{d['week'].min():%Y-%m} to {d['week'].max():%Y-%m}")
    for ev in EVENTS:
        sub = d[d[ev].notna()]
        ep = episodes(sub, ev)
        L.append(f"- {ev}: rate {sub[ev].mean():.4%}; event month-ends {int(sub[ev].sum()):,}; "
                 f"distinct episodes {int(ep.nunique()):,}; symbols {sub.loc[sub[ev] == 1, 'symbol'].nunique():,}")
    L.append(f"- cost of the typical base: median 52w fwd return {d['fwd_52w'].median():.1%}; "
             f"P(52w drawdown <= -40%) {(d['fwd_dd_52w'] <= -0.4).mean():.1%}\n")
    # 3 univariate
    lt = lift_table(d, feats)
    lt.to_csv("base_breakout_lift.csv", index=False)
    L.append("## 3. Univariate lift (ev2x_13w) — top vs bottom quintile, train vs test\n")
    L.append("| feature | coverage | Q1 lift train | Q5 lift train | Q1 lift test | Q5 lift test | "
             "Q5 events test (symbols) | Q5 med fwd52 | Q5 P(dd<=-40%) | monotone? |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    summ = []
    for f, g in lt.groupby("feature"):
        def val(part, q, col):
            s = g[(g["part"] == part) & (g["quintile"] == q)]
            return s[col].iloc[0] if len(s) else np.nan
        qmax = g["quintile"].max()
        tr_l = [val("train", q, "lift") for q in range(1, qmax + 1)]
        mono = ("up" if all(np.diff([x for x in tr_l if pd.notna(x)]) >= -0.15) else
                "down" if all(np.diff([x for x in tr_l if pd.notna(x)]) <= 0.15) else "no")
        spread = abs(val("test", qmax, "lift") - val("test", 1, "lift"))
        summ.append((spread, f"| {f} | {g['coverage'].iloc[0]:.0%} | {val('train', 1, 'lift'):.2f} | "
                             f"{val('train', qmax, 'lift'):.2f} | {val('test', 1, 'lift'):.2f} | "
                             f"{val('test', qmax, 'lift'):.2f} | {val('test', qmax, 'events'):.0f} "
                             f"({val('test', qmax, 'symbols_w_event'):.0f}) | {val('all', qmax, 'med_fwd52'):.1%} | "
                             f"{val('all', qmax, 'p_dd40'):.1%} | {mono} |"))
    for _, line in sorted(summ, key=lambda t: -(t[0] if pd.notna(t[0]) else -1)):
        L.append(line)
    # 5 model
    L.append("\n## 5. Walk-forward model (fit <= 2018, test 2019+)\n")
    for ev in ("ev2x_13w", "ev2x_26w"):
        res, coef, p = model(d, feats, ev)
        L.append(f"**{ev}**: AUC train {res['auc_train']:.3f} / test {res['auc_test']:.3f}; "
                 f"test base rate {res['base_test']:.3%}")
        for top in (1, 5, 10):
            L.append(f"- top {top}% each month: precision {res[f'prec_top{top}']:.2%} "
                     f"(lift {res[f'lift_top{top}']:.1f}x, n={res[f'n_top{top}']:,}); "
                     f"median 52w fwd {res[f'med_fwd52_top{top}']:.1%}")
        L.append("- strongest positive weights: " + ", ".join(f"{k} {v:+.2f}" for k, v in coef.tail(8)[::-1].items()))
        L.append("- strongest negative weights: " + ", ".join(f"{k} {v:+.2f}" for k, v in coef.head(6).items()) + "\n")
    # 6 clusters
    L.append("## 6. Clusters (k-means on rank features, fit on train)\n")
    for label, fs in (("price + fundamentals", [f for f in PRICE_F + FUND_F if f in d.columns]),
                      ("price + fundamentals + perception (2019+ coverage)", feats)):
        cl, typ = clusters(d, fs)
        cl.to_csv(f"base_breakout_clusters_{'pf' if len(fs) < len(feats) else 'all'}.csv", index=False)
        L.append(f"### {label}\n")
        L.append("| cluster | n | lift train | lift test | events test | med fwd52 | P(dd<=-40%) | signature |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in cl.itertuples():
            L.append(f"| {r.cluster} | {r.n:,} | {r.lift_train:.2f} | {r.lift_test:.2f} | {r.events_test} | "
                     f"{r.med_fwd52:.1%} | {r.p_dd40:.1%} | {r.signature} |")
        L.append("\n**Typology of the explosions themselves**\n")
        for r in typ.itertuples():
            L.append(f"- type {r.type}: {r.events} events / {r.symbols} symbols — {r.signature}")
        L.append("")
    L.append("## Caveats\n")
    L.append("- Survivorship: delisted names are included where FMP still serves their price history; "
             "coverage of delisted names is reported in fmp_price_universe.csv.")
    L.append("- Point-in-time: fundamentals keyed on filing date (75-day lag where none); perception "
             "series start 2017 (actions) / 2019 (monthly counts), so those features are tested on the "
             "later part of the sample only.")
    L.append("- Overlap: month-end observations inside one base overlap; episode and symbol counts are "
             "shown next to every event count.")
    L.append("- Archetype flags are today's snapshot (not point-in-time), so clusters are built from "
             "point-in-time INGREDIENTS of those archetypes, not the flags themselves.")
    open("BACKTEST_BASE_BREAKOUT.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
