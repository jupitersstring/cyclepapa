"""Event-study analyses on the crypto re-rating database.

    python -m crypto_multibaggers.analysis
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import adjusted_rand_score, roc_auc_score
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import QuantileTransformer

from . import features as F
from . import onchain as OC
from . import panel
from . import study
from .config import ANALYSIS_DIR, CACHE_DIR, DATA_DIR

warnings.filterwarnings("ignore", category=RuntimeWarning)

FEATS = list(F.FEATURES)
D0 = list(F.DAY0)
OCF = list(OC.ONCHAIN_FEATURES)
LABEL = {k: v[0] for k, v in {**F.FEATURES, **F.DAY0, **OC.ONCHAIN_FEATURES}.items()}
GROUP = {k: v[1] for k, v in {**F.FEATURES, **F.DAY0, **OC.ONCHAIN_FEATURES}.items()}

TIER_ORDER = ["10x+", "5-10x", "3-5x", "2-3x", "<2x"]
TIER_LABEL = {"10x+": "10x+ within 180 days", "5-10x": "5-10x", "3-5x": "3-5x", "2-3x": "2-3x (doublers)",
              "<2x": "Under 2x (faded pops)"}

# features used for archetypes and the multivariate score (one per idea, no composites)
CORE = ["av_mean_S", "av_mean_L", "cusum_av_120", "uv_mean_A", "iv_mean_S", "vpin_cdf", "oi_vw_L", "oi_vw_S",
        "cmf20", "tobv_A", "car_L", "car_S", "dd_ath", "vol_ratio_A", "vol_ratio_S", "bbw_pct", "n_up_jumps_A",
        "skew_A", "brk_90", "trend_t60", "amihud_ratio_A", "toxic_breakout_S20", "toxic_mom_A", "log_dv_base",
        "log_age", "corr_mkt_A", "rs_btc_90"]

# plain signal -> its toxic overlay (attribution-engine pairs)
TOXIC_PAIRS = [("n_high60_S20", "toxic_breakout_S20", "Breakout"), ("mom_30", "toxic_mom_S20", "Momentum 20-30d"),
               ("car_A", "toxic_mom_A", "Momentum 60d"), ("above_ma20_A", "toxic_trend_A", "Trend"),
               ("obv_A", "tobv_A", "OBV 60d"), ("obv_S20", "tobv_S20", "OBV 20d"),
               ("uv_mean_A", "toxic_accum_A", "Accumulation"), ("bbw_pct", "toxic_squeeze", "Squeeze")]


# ----------------------------------------------------------------------------- helpers
def auc_p(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) < 8 or len(b) < 8:
        return np.nan, np.nan
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    return u / (len(a) * len(b)), p


def bh(p):
    p = np.asarray(p, float)
    q = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    if ok.sum() == 0:
        return q
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * len(pv) / (np.arange(len(pv)) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(pv)
    out[order] = np.minimum(ranked, 1)
    q[ok] = out
    return q


def med(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    return float(np.median(x)) if len(x) else np.nan


def size_bucket(dv):
    return np.where(dv < 250e3, "micro", np.where(dv < 5e6, "small", "liquid"))


def families(ev: pd.DataFrame) -> dict[str, pd.Series]:
    """Boolean masks over events for each family."""
    fam = {"all": pd.Series(True, index=ev.index)}
    for t in TIER_ORDER:
        fam[t] = ev["tier"] == t
    sb = pd.Series(size_bucket(ev["_dv_base"].to_numpy()), index=ev.index)
    fam["micro"] = sb == "micro"
    fam["small"] = sb == "small"
    fam["liquid"] = sb == "liquid"
    fam["btc_bull"] = ev["btc_bull"] == 1
    fam["btc_bear"] = ev["btc_bull"] == 0
    if "sector" in ev:
        for s in ev["sector"].dropna().unique():
            if (ev["sector"] == s).sum() >= 60:
                fam[f"sector:{s}"] = ev["sector"] == s
    return fam


FAM_LABEL = {"all": "All re-ratings", "micro": "Micro tape (< $250k/day)", "small": "Small tape ($250k-$5M/day)",
             "liquid": "Liquid (> $5M/day)", "btc_bull": "BTC above 200-day average", "btc_bear": "BTC below 200-day average",
             **TIER_LABEL}


def fam_label(k):
    return FAM_LABEL.get(k, k.replace("sector:", ""))


# ----------------------------------------------------------------------------- exhibits
def exhibit_families(ev, pl):
    fam = families(ev)
    rows = []
    comp = ev["complete"]
    for k, m in fam.items():
        e = ev[m]
        ec = e[comp[m]]
        rows.append({
            "key": k, "label": fam_label(k), "events": int(len(e)), "tokens": int(e.symbol.nunique()),
            "micro_share": float((size_bucket(e["_dv_base"].to_numpy()) == "micro").mean()),
            "paid": float(e["paid"].mean()), "car01": med(e["car01"]), "runup": med(e["car_A"]),
            "complete": int(len(ec)), "durable": float(ec["durable"].mean()) if len(ec) else np.nan,
            "p_2x": float((ec["mult_180"] >= 2).mean()) if len(ec) else np.nan,
            "p_3x": float((ec["mult_180"] >= 3).mean()) if len(ec) else np.nan,
            "p_5x": float((ec["mult_180"] >= 5).mean()) if len(ec) else np.nan,
            "p_10x": float((ec["mult_180"] >= 10).mean()) if len(ec) else np.nan,
            "mult_med": med(ec["mult_180"]), "mult_entry_med": med(ec["mult_180_entry"]),
            "r180_med": med(ec["r_180"]), "days_to_peak_med": med(ec["days_to_peak"]),
        })
    fams = pd.DataFrame(rows)
    plc = pl[pl["complete"]]
    base = {"paid": float(((pl["r_1"] > 0) & (pl["r_1"] > 2 * pl["_sig_e"] * np.sqrt(2))).mean()),
            "durable": float(plc["durable"].mean()), "p_2x": float((plc["mult_180"] >= 2).mean()),
            "p_3x": float((plc["mult_180"] >= 3).mean()), "p_5x": float((plc["mult_180"] >= 5).mean()),
            "p_10x": float((plc["mult_180"] >= 10).mean()), "mult_med": med(plc["mult_180"])}
    return fams, base


def exhibit_grid(ev, pl, fam_keys, feats):
    fam = families(ev)
    rows = []
    for f in feats:
        for k in fam_keys:
            m = fam[k]
            ids = set(ev.loc[m, "event_id"])
            a = ev.loc[m, f].to_numpy()
            b = pl.loc[pl.event_id.isin(ids), f].to_numpy()
            auc, p = auc_p(a, b)
            rows.append({"feature": f, "label": LABEL[f], "group": GROUP[f], "family": k, "auc": auc, "p": p,
                         "ma": med(a), "mb": med(b), "n": int(np.sum(~np.isnan(a)))})
    g = pd.DataFrame(rows)
    g["q"] = bh(g["p"].to_numpy())
    return g


def exhibit_contrast(a_df, b_df, feats, name_a, name_b):
    rows = []
    for f in feats:
        auc, p = auc_p(a_df[f], b_df[f])
        rows.append({"feature": f, "label": LABEL[f], "group": GROUP[f], "auc": auc, "p": p,
                     f"m_{name_a}": med(a_df[f]), f"m_{name_b}": med(b_df[f])})
    d = pd.DataFrame(rows)
    d["q"] = bh(d["p"].to_numpy())
    d["strength"] = (d["auc"] - 0.5).abs()
    return d.sort_values("strength", ascending=False)


def compute_paths(ev, pl, lo=-60, hi=180, placebo_n=12000, seed=3):
    p, meta, mkt = panel.load()
    mkt = mkt.reindex(p["close"].index)
    btc_lc = np.log(p["close"]["BTCUSD"].to_numpy())
    pls = pl.sample(min(placebo_n, len(pl)), random_state=seed)
    W = hi - lo + 1
    out = {}
    for name, df in (("ev", ev), ("pl", pls)):
        av = np.full((len(df), W), np.nan, np.float32)
        car = np.full((len(df), W), np.nan, np.float32)
        pos = {ix: i for i, ix in enumerate(df.index)}
        for sym, sub in df.groupby("symbol"):
            ts = study._token_series(p, mkt, btc_lc, sym)
            a, c = F.paths(ts, sub["t"].to_numpy(), lo, hi)
            rows = [pos[i] for i in sub.index]
            av[rows], car[rows] = a, c
        out[name] = (df.index.to_numpy(), av, car)
    return out, np.arange(lo, hi + 1)


def path_summary(paths, rel, ev, fam_keys):
    idx_e, av_e, car_e = paths["ev"]
    idx_p, av_p, car_p = paths["pl"]
    keep = np.isin(idx_e, ev.index.to_numpy())      # events dropped after the paths were cached
    idx_e, av_e, car_e = idx_e[keep], av_e[keep], car_e[keep]
    fam = families(ev.loc[idx_e])
    series = []
    for k in fam_keys:
        m = fam[k].to_numpy()
        if m.sum() < 30:
            continue
        series.append({"key": k, "label": fam_label(k), "n": int(m.sum()),
                       "av": np.round(np.nanmean(av_e[m], 0), 3).tolist(),
                       "car": np.round(np.nanmedian(car_e[m], 0), 4).tolist()})
    plac = {"n": int(len(idx_p)), "av": np.round(np.nanmean(av_p, 0), 3).tolist(),
            "car": np.round(np.nanmedian(car_p, 0), 4).tolist()}
    return {"rel": rel.tolist(), "series": series, "placebo": plac}


# ----------------------------------------------------------------------------- archetypes
def _qt(ref: pd.DataFrame, cols):
    qt = QuantileTransformer(n_quantiles=500, output_distribution="normal", subsample=200000, random_state=0)
    qt.fit(ref[cols].fillna(ref[cols].median()))
    return qt


TRAITS = [  # (name, test on cluster-mean z vs placebo)
    ("Capitulation", lambda z: z["av_mean_S"] > 0.6 and z["car_S"] < -0.4 and z["oi_vw_S"] < -0.3),
    ("Toxic breakout", lambda z: z["toxic_breakout_S20"] > 0.5 and z["brk_90"] > 0.4),
    ("Informed drift (price and volume run-up, buying pressure)",
     lambda z: z["car_L"] + z["car_S"] > 0.5 and z["av_mean_L"] > 0.3 and z["oi_vw_L"] > 0.2),
    ("Heavy volume on a falling base", lambda z: z["av_mean_S"] > 0.4 and z["car_L"] < -0.3),
    ("Stealth accumulation (volume without price)", lambda z: z["uv_mean_A"] > 0.4 and abs(z["car_L"]) < 0.4),
    ("Lottery spikes / promotion", lambda z: z["n_up_jumps_A"] > 0.5 or z["skew_A"] > 0.5),
    ("Toxic squeeze (coiled range, rising toxicity)", lambda z: z["bbw_pct"] < -0.4 and z["vpin_cdf"] > 0.2),
    ("Washed out (deep drawdown from the high)", lambda z: z["dd_ath"] < -0.5),
    ("Trend continuation", lambda z: z["trend_t60"] > 0.5 and z["brk_90"] > 0.3),
    ("Liquidity drying up", lambda z: z["amihud_ratio_A"] > 0.4),
    ("Liquidity improving", lambda z: z["amihud_ratio_A"] < -0.4),
    ("Decoupled from the market", lambda z: z["corr_mkt_A"] < -0.5),
    ("Dormant tape", lambda z: z["av_mean_L"] < -0.4 and z["vol_ratio_A"] < -0.4),
]


def name_cluster(z: pd.Series) -> str:
    hits = []
    for name, test in TRAITS:
        try:
            if test(z):
                hits.append(name)
        except KeyError:
            pass
    return " + ".join(hits[:3]) if hits else "Ordinary tape (information not in the tape)"


def exhibit_archetypes(ev, pl, target_mask, k_range=range(4, 11), seeds=(0, 1, 2, 3, 4), core_p=0.6):
    cols = [c for c in CORE if c not in ("log_dv_base", "log_age")]
    qt = _qt(pl, cols)
    fill = pl[cols].median()
    tgt = ev[target_mask]
    X = qt.transform(tgt[cols].fillna(fill))
    Xp = qt.transform(pl[cols].fillna(fill))
    Xe = qt.transform(ev[cols].fillna(fill))
    best, bic = None, np.inf
    for k in k_range:
        g = GaussianMixture(k, covariance_type="diag", random_state=0, n_init=3, reg_covar=1e-3).fit(X)
        b = g.bic(X)
        if b < bic:
            best, bic = g, b
    k = best.n_components
    lab = best.predict(X)
    aris = []
    for s in seeds[1:]:
        g2 = GaussianMixture(k, covariance_type="diag", random_state=s, n_init=3, reg_covar=1e-3).fit(X)
        aris.append(adjusted_rand_score(lab, g2.predict(X)))
    pt, pp, pe = best.predict_proba(X), best.predict_proba(Xp), best.predict_proba(Xe)
    rows = []
    zmeans = pd.DataFrame(X, columns=cols).groupby(lab).mean()
    all_lab = pe.argmax(1)
    all_core = pe.max(1) >= core_p
    comp = ev["complete"].to_numpy()
    mb = (ev["mult_180"] >= 3).to_numpy()
    for c in range(k):
        in_t = (pt.argmax(1) == c) & (pt.max(1) >= core_p)
        in_p = (pp.argmax(1) == c) & (pp.max(1) >= core_p)
        ctl = in_p.mean()
        sub = tgt[lab == c]
        in_all = (all_lab == c) & all_core & comp
        conv = mb[in_all].mean() if in_all.sum() >= 20 else np.nan
        rows.append({"id": int(c), "name": name_cluster(zmeans.loc[c]), "n": int((lab == c).sum()),
                     "share": float((lab == c).mean()), "lift": float(in_t.mean() / ctl) if ctl > 0 else np.nan,
                     "ctl": float(ctl), "conversion": float(conv) if conv == conv else None,
                     "n_triggers": int(in_all.sum()),
                     "car01": med(sub["car01"]), "r_20": med(sub["r_20"]), "r_60": med(sub["r_60"]),
                     "mult_med": med(sub["mult_180"]), "p_10x": float((sub["mult_180"] >= 10).mean()),
                     "durable": float(sub["durable"].mean()),
                     "profile": {f: round(float(zmeans.loc[c, f]), 2) for f in cols},
                     "examples": [f"{s[:-3]} {d:%Y-%m-%d}" for s, d in
                                  sub.sort_values("mult_180", ascending=False)[["symbol", "date"]].head(5).values]})
    arch = pd.DataFrame(rows).sort_values("lift", ascending=False)
    base_conv = mb[comp].mean()
    return arch, {"k": int(k), "ari_mean": float(np.mean(aris)) if aris else np.nan, "base_conversion": float(base_conv),
                  "cols": cols}, best, qt, fill


# ----------------------------------------------------------------------------- scores / CV
def _model(kind):
    if kind == "gbm":
        return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                              min_samples_leaf=40, l2_regularization=1.0, random_state=0)
    return make_pipeline(QuantileTransformer(n_quantiles=500, output_distribution="normal", random_state=0),
                         LogisticRegression(C=0.2, max_iter=2000))


def _xy(df, cols):
    X = df[cols].astype(float)
    return X.fillna(X.median()) if True else X


def grouped_cv(pos, neg, cols, kind="gbm", folds=5):
    df = pd.concat([pos.assign(_y=1), neg.assign(_y=0)], ignore_index=True)
    X = df[cols].astype(float)
    if kind != "gbm":
        X = X.fillna(X.median())
    y, g = df["_y"].to_numpy(), df["symbol"].to_numpy()
    s = np.zeros(len(df))
    for tr, te in GroupKFold(folds).split(X, y, g):
        m = _model(kind).fit(X.iloc[tr], y[tr])
        s[te] = m.predict_proba(X.iloc[te])[:, 1]
    auc = roc_auc_score(y, s)
    thr = np.quantile(s[y == 0], 0.9)
    return {"auc": float(auc), "cap": float((s[y == 1] > thr).mean()), "n": int(len(df)),
            "n_pos": int(y.sum())}, s, df


def time_split(pos, neg, cols, cut="2022-01-01", kind="gbm"):
    df = pd.concat([pos.assign(_y=1), neg.assign(_y=0)], ignore_index=True)
    tr, te = df["date"] < cut, df["date"] >= cut
    X = df[cols].astype(float)
    if kind != "gbm":
        X = X.fillna(X[tr].median())
    m = _model(kind).fit(X[tr], df.loc[tr, "_y"])
    s = m.predict_proba(X[te])[:, 1]
    y = df.loc[te, "_y"].to_numpy()
    thr = np.quantile(s[y == 0], 0.9)
    return {"auc": float(roc_auc_score(y, s)), "cap": float((s[y == 1] > thr).mean()), "n": int(te.sum()),
            "n_pos": int(y.sum()), "train_until": cut}


def screen_leaderboard(scr, feats, label_col="mb3", min_pos_date=1):
    """Within-date AUC and top-decile lift of each feature for a forward label on
    the unconditional screen panel. Direction is set on 2017-2021 and scored on 2022+."""
    s = scr[scr["complete"]].copy()
    s["period"] = np.where(s["date"] < "2022-01-01", "train", "test")
    rows = []
    for f in feats:
        res = {}
        for per, d in s.groupby("period"):
            aucs, wts, top_hits, top_n, base_hits, base_n = [], [], 0, 0, 0, 0
            for _, g in d.groupby("date"):
                y = g[label_col].to_numpy()
                x = g[f].to_numpy()
                ok = ~np.isnan(x)
                y, x = y[ok], x[ok]
                if y.sum() < min_pos_date or y.sum() == len(y) or len(y) < 30:
                    continue
                aucs.append(roc_auc_score(y, x))
                wts.append(y.sum())
                res.setdefault("_dates", 0)
                q = np.quantile(x, [0.1, 0.9])
                res.setdefault("_hi", [0, 0])
                res.setdefault("_lo", [0, 0])
                res["_hi"][0] += y[x >= q[1]].sum()
                res["_hi"][1] += (x >= q[1]).sum()
                res["_lo"][0] += y[x <= q[0]].sum()
                res["_lo"][1] += (x <= q[0]).sum()
                base_hits += y.sum()
                base_n += len(y)
            auc = float(np.average(aucs, weights=wts)) if aucs else np.nan
            res[per] = {"auc": auc, "base": base_hits / base_n if base_n else np.nan,
                        "hi": res["_hi"][0] / max(res["_hi"][1], 1) if "_hi" in res else np.nan,
                        "lo": res["_lo"][0] / max(res["_lo"][1], 1) if "_lo" in res else np.nan}
            for k in ("_hi", "_lo"):
                res.pop(k, None)
        tr, te = res.get("train", {}), res.get("test", {})
        if not tr or not te:
            continue
        direction = 1 if tr["auc"] >= 0.5 else -1
        pick = "hi" if direction == 1 else "lo"
        rows.append({"feature": f, "label": LABEL.get(f, f), "group": GROUP.get(f, "model"),
                     "direction": direction, "auc_train": tr["auc"], "auc_test": te["auc"],
                     "auc_test_dir": te["auc"] if direction == 1 else 1 - te["auc"],
                     "hit_test": te[pick], "base_test": te["base"], "lift_test": te[pick] / te["base"],
                     "hit_train": tr[pick], "base_train": tr["base"], "lift_train": tr[pick] / tr["base"]})
    return pd.DataFrame(rows).sort_values("lift_test", ascending=False)


def exhibit_recipes(scr, lb, n_signals=14, q=0.8, min_support=150):
    """Two- and three-signal screens: every signal is ranked within its date (direction
    set on 2017-21); a coin passes a signal when it sits in that date's top quintile.
    Combinations are ranked on 2017-21 lift and scored on 2022+."""
    from itertools import combinations
    s = scr[scr["complete"]].copy()
    cand = lb.sort_values("lift_train", ascending=False)
    cand = cand[cand["group"] != "size"].head(n_signals)
    flags = {}
    for _, r in cand.iterrows():
        x = s[r.feature] * r.direction
        flags[r.feature] = (x.groupby(s["date"]).rank(pct=True) >= q).to_numpy()
    y = s["mb3"].to_numpy()
    tr = (s["date"] < "2022-01-01").to_numpy()
    te = ~tr
    base_tr, base_te = y[tr].mean(), y[te].mean()
    rows = []
    feats = list(flags)
    for k in (1, 2, 3):
        for combo in combinations(feats, k):
            m = np.logical_and.reduce([flags[f] for f in combo])
            n_tr, n_te = int((m & tr).sum()), int((m & te).sum())
            if n_tr < min_support or n_te < min_support // 2:
                continue
            rows.append({"signals": list(combo), "labels": [LABEL[f] for f in combo], "k": k,
                         "n_train": n_tr, "n_test": n_te,
                         "hit_train": float(y[m & tr].mean()), "hit_test": float(y[m & te].mean()),
                         "lift_train": float(y[m & tr].mean() / base_tr), "lift_test": float(y[m & te].mean() / base_te)})
    out = pd.DataFrame(rows)
    if out.empty:
        return out, {}
    best = pd.concat([out[out.k == k].sort_values("lift_train", ascending=False).head(8) for k in (1, 2, 3)])
    return best, {"base_train": float(base_tr), "base_test": float(base_te), "quantile": q,
                  "n_signals": len(feats)}


def screen_models(scr, cut="2022-01-01"):
    """Multivariate screens trained on 2017-21 coin-dates and scored on 2022+.
    'raw' uses feature levels; 'ranked' uses each feature's percentile within its
    date (a cross-sectional screen), both with equal total weight per date."""
    sc = scr[scr["complete"]].copy()
    R = sc.groupby("date")[FEATS].rank(pct=True)
    tr = (sc["date"] < cut).to_numpy()
    w = (1.0 / sc.groupby("date")["symbol"].transform("size")).to_numpy()
    out = {}
    for name, X in (("raw", sc[FEATS].astype(float)), ("ranked", R)):
        m = _model("gbm").fit(X[tr], sc["mb3"].to_numpy()[tr], sample_weight=w[tr] * tr.sum())
        sc[f"score_{name}"] = m.predict_proba(X)[:, 1]
        out[name] = m
    Rl = R.fillna(0.5)
    lg = LogisticRegression(C=0.2, max_iter=3000).fit(Rl[tr], sc["mb3"].to_numpy()[tr], sample_weight=w[tr] * tr.sum())
    sc["score_logit_ranked"] = lg.predict_proba(Rl)[:, 1]
    out["logit_ranked"] = lg
    return sc, out


def trigger_leaderboard(ev, feats, cut="2022-01-01", q=0.8):
    """Among triggers only: which measure (pre-event or day 0) best picks the pops
    that become 3x+. Direction from 2017-21 triggers; top quintile of 2022+ triggers."""
    e = ev[ev["complete"]].copy()
    y = (e["mult_180"] >= 3).to_numpy()
    tr = (e["date"] < cut).to_numpy()
    te = ~tr
    base = y[te].mean()
    rows = []
    for f in feats:
        x = e[f].to_numpy(dtype=float)
        ok_tr, ok_te = tr & ~np.isnan(x), te & ~np.isnan(x)
        if ok_tr.sum() < 200 or ok_te.sum() < 200:
            continue
        a_tr = roc_auc_score(y[ok_tr], x[ok_tr])
        d = 1 if a_tr >= 0.5 else -1
        xt = d * x[ok_te]
        thr = np.quantile(xt, q)
        top = xt >= thr
        rows.append({"feature": f, "label": LABEL.get(f, f), "group": GROUP.get(f, "model"), "direction": d,
                     "auc_train": a_tr if d > 0 else 1 - a_tr, "auc_test": roc_auc_score(y[ok_te], xt),
                     "hit_test": float(y[ok_te][top].mean()), "base_test": float(base),
                     "lift_test": float(y[ok_te][top].mean() / base), "n_test": int(ok_te.sum())})
    return pd.DataFrame(rows).sort_values("lift_test", ascending=False)


def archetypes_oos(ev, pl, cut="2022-01-01", core_p=0.6):
    """Archetypes fitted on 2017-21 multibaggers only, then used to sort 2022+ triggers."""
    tr_ev, tr_pl = ev[ev["date"] < cut], pl[pl["date"] < cut]
    arch, info, gmm, qt, fill = exhibit_archetypes(tr_ev, tr_pl, (tr_ev["complete"] & (tr_ev["mult_180"] >= 3)).to_numpy())
    te = ev[(ev["date"] >= cut) & ev["complete"]]
    te_pl = pl[pl["date"] >= cut]
    pr = gmm.predict_proba(qt.transform(te[info["cols"]].fillna(fill)))
    pp = gmm.predict_proba(qt.transform(te_pl[info["cols"]].fillna(fill)))
    lab, core = pr.argmax(1), pr.max(1) >= core_p
    y = (te["mult_180"] >= 3).to_numpy()
    base = y.mean()
    rows = []
    for _, a in arch.iterrows():
        m = (lab == a["id"]) & core
        mp = (pp.argmax(1) == a["id"]) & (pp.max(1) >= core_p)
        mb = m & y
        rows.append({"name": a["name"], "train_conversion": a["conversion"], "train_lift": a["lift"],
                     "n_test": int(m.sum()), "conversion_test": float(y[m].mean()) if m.sum() >= 15 else None,
                     "base_test": float(base), "lift_test": float((mb.sum() / max(y.sum(), 1)) / max(mp.mean(), 1e-9))})
    return pd.DataFrame(rows), info


# ----------------------------------------------------------------------------- validation cases
KNOWN = [
    ("XRPUSD", "2020-12-22", "SEC sues Ripple Labs (S.D.N.Y.)", -1),
    ("XRPUSD", "2023-07-13", "SEC v. Ripple: programmatic sales not securities (S.D.N.Y.)", 1),
    ("XRPUSD", "2024-11-12", "Post-election re-rating; SEC leadership change expected", 1),
    ("TORNUSD", "2022-08-08", "OFAC sanctions Tornado Cash", -1),
    ("TORNUSD", "2024-11-26", "Van Loon v. Treasury (5th Cir.): Tornado sanctions unlawful", 1),
    ("BTCUSD", "2023-08-29", "Grayscale v. SEC (D.C. Cir.): ETF denial vacated", 1),
    ("BTCUSD", "2024-01-10", "Spot bitcoin ETFs approved", 1),
    ("ETHUSD", "2024-05-20", "SEC signals spot ether ETF approval", 1),
    ("BNBUSD", "2023-06-05", "SEC sues Binance", -1),
    ("FTTUSD", "2022-11-08", "FTX liquidity crisis / Binance walks away", -1),
    ("LUNCUSD", "2022-05-09", "UST de-peg", -1),
    ("DOGEUSD", "2021-01-28", "WallStreetBets / Musk tweets", 1),
    ("MANAUSD", "2021-10-28", "Facebook renames itself Meta", 1),
    ("SANDUSD", "2021-10-29", "Facebook renames itself Meta", 1),
    ("SHIBUSD", "2021-10-04", "October 2021 SHIB mania", 1),
    ("AXSUSD", "2021-07-06", "Axie play-to-earn boom", 1),
    ("PEPEUSD", "2023-05-05", "Binance lists PEPE", 1),
    ("BONKUSD", "2023-12-14", "Binance lists BONK", 1),
    ("WIFUSD", "2024-03-05", "Binance lists WIF", 1),
    ("HBARUSD", "2024-04-23", "BlackRock fund-tokenisation headline (misread)", 1),
    ("LINKUSD", "2019-06-27", "Coinbase Pro lists LINK", 1),
    ("OMUSD", "2025-04-13", "MANTRA collapse", -1),
]


def exhibit_validation(ev, raw_lookup):
    rows = []
    for sym, d, desc, sign in KNOWN:
        d = pd.Timestamp(d)
        e = ev[(ev.symbol == sym) & (ev.date >= d - pd.Timedelta(days=2)) & (ev.date <= d + pd.Timedelta(days=5))]
        r = raw_lookup(sym, d)
        rows.append({"symbol": sym[:-3], "date": d.strftime("%Y-%m-%d"), "desc": desc, "sign": sign,
                     "trigger": bool(len(e)), **r})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- main
def run():
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    ev, pl, scr, live = study.load()
    # commodity-backed tokens (added to the panel exclusions after this build)
    drop_ids = set(ev.loc[ev.symbol.isin(panel.COMMODITY_BACKED), "event_id"])
    ev = ev[~ev.symbol.isin(panel.COMMODITY_BACKED)].copy()
    pl = pl[~pl.symbol.isin(panel.COMMODITY_BACKED) & ~pl.event_id.isin(drop_ids)].copy()
    scr = scr[~scr.symbol.isin(panel.COMMODITY_BACKED)].copy()
    live = live[~live.symbol.isin(panel.COMMODITY_BACKED)].copy()
    for df in (ev, pl, scr, live):
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"])
        num = df.select_dtypes("number").columns
        df[num] = df[num].replace([np.inf, -np.inf], np.nan)
    print(f"events {len(ev)}, placebos {len(pl)}, screen {len(scr)}, live {len(live)}", flush=True)
    p_, meta_, mkt_ = panel.load()
    dates = p_["close"].index
    atlas: dict = {"asof": str(dates[-1].date())}

    # on-chain enrichment + sector labels
    panels = OC.load_onchain_panels(dates)
    lc = np.log(p_["close"])
    for df in (ev, pl, scr, live):
        df[OCF] = OC.onchain_features(df, panels, lc).astype(float).replace([np.inf, -np.inf], np.nan)
    sec_path = CACHE_DIR / "sectors.csv"
    if sec_path.exists():
        sec = pd.read_csv(sec_path, index_col=0)["sector"]
        for df in (ev, pl, scr, live):
            df["sector"] = df["symbol"].map(sec)
    print("on-chain coverage (events):", {k: int(ev[k].notna().sum()) for k in OCF}, flush=True)

    # A. families
    fams, base = exhibit_families(ev, pl)
    fams.to_csv(ANALYSIS_DIR / "families.csv", index=False)
    atlas["families"], atlas["placebo_rates"] = fams.to_dict("records"), base
    print(fams[["label", "events", "tokens", "paid", "durable", "p_3x", "p_10x", "mult_med"]].to_string(), flush=True)

    # B. paths (cached: they only change when the event database does)
    pc = study.STUDY_DIR / "paths.npz"
    if pc.exists() and pc.stat().st_mtime > (study.STUDY_DIR / "events.parquet").stat().st_mtime:
        z = np.load(pc)
        paths, rel = {"ev": (z["ie"], z["ae"], z["ce"]), "pl": (z["ip"], z["ap"], z["cp"])}, z["rel"]
    else:
        paths, rel = compute_paths(ev, pl)
        np.savez(pc, ie=paths["ev"][0], ae=paths["ev"][1], ce=paths["ev"][2], ip=paths["pl"][0], ap=paths["pl"][1],
                 cp=paths["pl"][2], rel=rel)
    atlas["paths"] = path_summary(paths, rel, ev, ["all", "10x+", "5-10x", "3-5x", "2-3x", "<2x"])

    # C. grid (events vs matched placebo)
    grid_fams = ["all", "10x+", "5-10x", "3-5x", "2-3x", "<2x", "micro"]
    grid = exhibit_grid(ev, pl, grid_fams, FEATS)
    grid.to_csv(ANALYSIS_DIR / "auc_grid_events_vs_placebo.csv", index=False)
    atlas["grid"] = {"families": [{"key": k, "label": fam_label(k)} for k in grid_fams],
                     "rows": grid.to_dict("records")}

    # D. multibaggers vs faded pops (pre-event + day-0)
    comp = ev[ev["complete"]]
    win = comp[comp["mult_180"] >= 3]
    lose = comp[(comp["mult_180"] < 1.5) & (comp["r_60"] < 0)]
    wl = exhibit_contrast(win, lose, FEATS + D0, "w", "l")
    wl.to_csv(ANALYSIS_DIR / "multibaggers_vs_faded.csv", index=False)
    big = comp[comp["mult_180"] >= 10]
    small = comp[(comp["mult_180"] >= 3) & (comp["mult_180"] < 5)]
    tenx = exhibit_contrast(big, small, FEATS + D0, "10x", "3to5x")
    tenx.to_csv(ANALYSIS_DIR / "tenx_vs_3to5x.csv", index=False)
    atlas["winners"] = {"n_w": int(len(win)), "n_l": int(len(lose)), "rows": wl.head(14).to_dict("records"),
                        "tenx": {"n_a": int(len(big)), "n_b": int(len(small)), "rows": tenx.head(10).to_dict("records")}}

    # E. durable vs faded
    dur = comp[comp["r_60"] >= np.log(1.2)]
    fad = comp[comp["r_60"] < 0]
    df_ = exhibit_contrast(dur, fad, FEATS + D0, "d", "f")
    df_.to_csv(ANALYSIS_DIR / "durable_vs_faded.csv", index=False)
    atlas["durable"] = {"n_d": int(len(dur)), "n_f": int(len(fad)), "rows": df_.head(12).to_dict("records")}

    # O. on-chain layer (coverage-limited)
    oc_fams = ["all", "10x+", "5-10x", "3-5x", "<2x"]
    grid_oc = exhibit_grid(ev, pl, oc_fams, OCF)
    grid_oc.to_csv(ANALYSIS_DIR / "auc_grid_onchain.csv", index=False)
    wl_oc = exhibit_contrast(win, lose, OCF, "w", "l")
    wl_oc.to_csv(ANALYSIS_DIR / "onchain_multibaggers_vs_faded.csv", index=False)
    atlas["onchain"] = {"families": [{"key": k, "label": fam_label(k)} for k in oc_fams],
                        "rows": grid_oc.to_dict("records"), "winners": wl_oc.to_dict("records"),
                        "coverage": {k: int(ev[k].notna().sum()) for k in OCF},
                        "tokens": {k: int(ev.loc[ev[k].notna(), "symbol"].nunique()) for k in OCF}}
    if "sector" in ev:
        sec_rows = []
        for sct, e in ev[ev["complete"]].groupby("sector"):
            if len(e) < 40:
                continue
            sec_rows.append({"sector": sct, "events": int(len(e)), "tokens": int(e.symbol.nunique()),
                             "p_3x": float((e["mult_180"] >= 3).mean()), "p_10x": float((e["mult_180"] >= 10).mean()),
                             "durable": float(e["durable"].mean()), "mult_med": med(e["mult_180"]),
                             "car01": med(e["car01"])})
        sec_df = pd.DataFrame(sec_rows).sort_values("p_3x", ascending=False)
        sec_df.to_csv(ANALYSIS_DIR / "sectors.csv", index=False)
        atlas["sectors"] = sec_df.to_dict("records")

    # F. archetypes of pre-re-rating tape (multibaggers)
    arch, ainfo, gmm, qt, fill = exhibit_archetypes(ev, pl, (ev["complete"] & (ev["mult_180"] >= 3)).to_numpy())
    arch.to_csv(ANALYSIS_DIR / "archetypes.csv", index=False)
    atlas["archetypes"], atlas["arch_info"] = arch.to_dict("records"), ainfo
    print(arch[["name", "n", "lift", "conversion", "mult_med", "p_10x"]].to_string(), flush=True)

    # G. out-of-sample scores
    cv = []
    feats_pre = [f for f in FEATS]
    mb_ev = ev[ev["complete"] & (ev["mult_180"] >= 3)]
    pl_c = pl[pl["event_id"].isin(ev.loc[ev["complete"], "event_id"])]
    for name, pos, neg, cols in (
            ("Re-rating (any) vs placebo, pre-event tape", ev, pl, feats_pre),
            ("Multibagger (3x+) vs placebo, pre-event tape", mb_ev, pl_c, feats_pre),
            ("Multibagger vs faded pop, pre-event + day 0", win, lose, feats_pre + D0)):
        for kind in ("gbm", "logit"):
            r, _, _ = grouped_cv(pos, neg, cols, kind)
            r.update(sample=name, model=kind, split="symbol-grouped 5-fold")
            cv.append(r)
            t = time_split(pos, neg, cols, kind=kind)
            t.update(sample=name, model=kind, split="train 2017-21, test 2022+")
            cv.append(t)
            print(r, t, flush=True)
    cvdf = pd.DataFrame(cv)
    cvdf.to_csv(ANALYSIS_DIR / "cv.csv", index=False)
    atlas["cv"] = cv

    # W. what works best: unconditional screen for forward 3x / 10x
    scr = scr.copy()
    scr["mb3"] = (scr["mult_180"] >= 3).astype(int)
    scr["mb10"] = (scr["mult_180"] >= 10).astype(int)
    lb = screen_leaderboard(scr, FEATS)
    lb.to_csv(ANALYSIS_DIR / "screen_leaderboard_3x.csv", index=False)
    lb10 = screen_leaderboard(scr.assign(mb3=scr["mb10"]), FEATS)
    lb10.to_csv(ANALYSIS_DIR / "screen_leaderboard_10x.csv", index=False)
    pairs = []
    for plain, tox, nm in TOXIC_PAIRS:
        a = lb.set_index("feature")
        if plain in a.index and tox in a.index:
            pairs.append({"signal": nm, "plain": plain, "toxic": tox,
                          "plain_auc": a.at[plain, "auc_test_dir"], "toxic_auc": a.at[tox, "auc_test_dir"],
                          "plain_lift": a.at[plain, "lift_test"], "toxic_lift": a.at[tox, "lift_test"]})
    pairs = pd.DataFrame(pairs)
    pairs.to_csv(ANALYSIS_DIR / "toxic_vs_plain.csv", index=False)
    # multivariate screens, trained 2017-21, scored 2022+
    LABEL.update({"score_raw": "Gradient-boosted screen (feature levels)",
                  "score_ranked": "Gradient-boosted screen (within-date ranks)",
                  "score_logit_ranked": "Logistic screen (within-date ranks)"})
    sc_scored, screen_fit = screen_models(scr)
    lb_model = screen_leaderboard(sc_scored, ["score_raw", "score_ranked", "score_logit_ranked"])
    lb_model.to_csv(ANALYSIS_DIR / "screen_models.csv", index=False)
    print(lb_model[["label", "auc_test_dir", "lift_test", "lift_train"]].to_string(), flush=True)
    # conditional: among triggers, which measure picks the multibaggers
    tlb = trigger_leaderboard(ev, FEATS + D0)
    tlb.to_csv(ANALYSIS_DIR / "trigger_leaderboard.csv", index=False)
    atlas["trigger_lb"] = tlb.head(20).to_dict("records")
    print(tlb.head(15)[["label", "direction", "auc_test", "hit_test", "base_test", "lift_test"]].to_string(), flush=True)
    aoos, _ = archetypes_oos(ev, pl)
    aoos.to_csv(ANALYSIS_DIR / "archetypes_out_of_sample.csv", index=False)
    atlas["arch_oos"] = aoos.to_dict("records")
    print(aoos.to_string(), flush=True)
    sc = scr[scr["complete"]]
    rec, rinfo = exhibit_recipes(scr, lb)
    rec.to_csv(ANALYSIS_DIR / "screen_recipes.csv", index=False)
    atlas["recipes"], atlas["recipes_info"] = rec.to_dict("records"), rinfo
    print(rec[["labels", "n_train", "n_test", "lift_train", "lift_test"]].to_string(), flush=True)
    atlas["screen"] = {"leaderboard": lb.to_dict("records"), "leaderboard10": lb10.head(15).to_dict("records"),
                       "pairs": pairs.to_dict("records"), "model": lb_model.to_dict("records"),
                       "n": int(len(sc)), "base3": float(sc["mb3"].mean()), "base10": float(sc["mb10"].mean())}
    print(lb.head(15)[["label", "auc_test_dir", "lift_test", "lift_train"]].to_string(), flush=True)
    print(pairs.to_string(), flush=True)
    print(lb_model.to_string(), flush=True)

    # H. validation cases + L. live scan
    full_pos = mb_ev
    full_neg = pl_c
    final = _model("gbm").fit(pd.concat([full_pos, full_neg])[FEATS].astype(float),
                              np.r_[np.ones(len(full_pos)), np.zeros(len(full_neg))])
    ref = final.predict_proba(pl[FEATS].astype(float))[:, 1]

    def pct(x):
        return float((ref < x).mean())

    btc_lc = np.log(p_["close"]["BTCUSD"].to_numpy())
    mkt_ = mkt_.reindex(dates)

    def raw_lookup(sym, d):
        if sym not in p_["close"]:
            return {}
        ts = study._token_series(p_, mkt_, btc_lc, sym)
        t = int(dates.get_indexer([d], method="nearest")[0])
        f = F.compute(ts, np.array([t]), day0=True)
        from .events import outcomes
        o = outcomes(ts.c, np.array([t]))
        x = pd.DataFrame({k: v for k, v in f.items() if k in FEATS})
        sc_ = float(final.predict_proba(x[FEATS].astype(float))[:, 1][0])
        return {"d0_ret": float(f["d0_ret"][0]) if "d0_ret" in f else np.nan,
                "d0_z": float(f["d0_z"][0]), "car_pre": float(f["car_A"][0]), "av_S": float(f["av_mean_S"][0]),
                "mult_180": float(o["mult_180"][0]), "r_20": float(o["r_20"][0]), "r_60": float(o["r_60"][0]),
                "score_pct": pct(sc_)}

    val = exhibit_validation(ev, raw_lookup)
    val.to_csv(ANALYSIS_DIR / "validation_cases.csv", index=False)
    atlas["validation"] = val.to_dict("records")

    live = live.copy()
    live["score"] = final.predict_proba(live[FEATS].astype(float))[:, 1]
    live["score_pct"] = [pct(x) for x in live["score"]]
    # unconditional screen score (within-date ranks of today's eligible coins)
    Rlive = live[FEATS].rank(pct=True)
    live["screen_score"] = screen_fit["ranked"].predict_proba(Rlive)[:, 1]
    live["screen_pct"] = live["screen_score"].rank(pct=True)
    # tradeability today: the baseline screen ends 61 days back, so also require a live tape
    v7 = p_["volume"].iloc[-7:]
    live["dv7"] = live["symbol"].map(v7.mean())
    live["days_traded7"] = live["symbol"].map((v7 > 0).sum())
    live["last_quote"] = live["symbol"].map(p_["close"].iloc[-3:].notna().any())
    live["tradeable"] = (live["dv7"] >= 100_000) & (live["days_traded7"] >= 6) & live["last_quote"].fillna(False)
    atlas["live_excluded"] = int((~live["tradeable"]).sum())
    live = live[live["tradeable"]].copy()
    live["blend"] = (live["score"].rank(pct=True) + live["screen_pct"]) / 2
    Xl = qt.transform(live[ainfo["cols"]].fillna(fill))
    pr = gmm.predict_proba(Xl)
    live["archetype"] = [atlas["archetypes"][[a["id"] for a in atlas["archetypes"]].index(i)]["name"]
                         if pr[j].max() >= 0.6 else "(no archetype)" for j, i in enumerate(pr.argmax(1))]
    keep = ["symbol", "name", "blend", "score", "score_pct", "screen_pct", "archetype", "dv7", "_dv_base", "av_mean_S",
            "cusum_av_120", "vpin_cdf", "vol_ratio_S", "car_A", "dd_ath", "max_dd_A", "toxic_breakout_S20", "tobv_A",
            "brk_90", "bbw_pct", "sector"]
    keep = [k for k in keep if k in live]
    top = live.sort_values("blend", ascending=False)[keep]
    top.to_csv(ANALYSIS_DIR / "live_scan.csv", index=False)
    atlas["live"] = top.head(40).to_dict("records")
    atlas["live_n"] = int(len(live))

    # sizes
    atlas.update({"n_events": int(len(ev)), "n_tokens": int(ev.symbol.nunique()), "n_placebo": int(len(pl)),
                  "n_complete": int(ev["complete"].sum()), "n_mb3": int(len(mb_ev)),
                  "n_mb10": int((ev["complete"] & (ev["mult_180"] >= 10)).sum()),
                  "first": str(ev.date.min().year), "last": str(ev.date.max().year),
                  "n_universe": int(len(meta_)), "n_eligible": int((meta_.exclusion == "").sum())})
    (DATA_DIR / "atlas.json").write_text(json.dumps(atlas, default=_json_default))
    print("analysis done", flush=True)


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o.date())
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


if __name__ == "__main__":
    run()
