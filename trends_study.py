"""Does Google search attention carry information about base breakouts?

Sample (case-control, US listings, drug developers excluded):
  CASES     symbols whose flat two-year base (base_panel.parquet) was followed by
            a doubling within 13 weeks (ev2x_13w)
  CONTROLS  an equal number of base symbols that never did
Query: the cleaned company name (suffixes like Inc / Corp / Holdings / Class A
removed), in two 5-year windows (weekly data): 2016-01-01..2020-12-31 and
2021-01-01..today. Google normalises every query to 0-100, so all features are
SCALE-FREE and computed inside one window.

Point-in-time features at base month t (weeks <= t only):
  srch_ratio13     mean(last 13w) / mean(the 91 weeks before)
  srch_z13         (mean last 13w - baseline mean) / baseline std
  srch_cusum_up    max one-sided CUSUM of standardised weekly values over the
                   last 26w (sustained upward shift, not a single spike)
  srch_slope_brk   OLS slope, last 26w minus slope of the 78w before (per std)
  srch_cp_up13     PELT change point (ruptures, rbf) in the last 13w with the
                   post-change mean above the pre-change mean
  srch_zero_share  share of zero weeks in the 104w window (sparsity guard: > 0.3
                   = too little search volume to read)
Evaluation: event rate by feature quintile (odds are unaffected by the
case-control design, so relative lift is valid), and whether the attention
features add discrimination beyond price/volume (logistic AUC with vs without).
Raw series are cached in trends_raw.parquet (resumable).
"""
from __future__ import annotations

import os
import random
import re
import time

import numpy as np
import pandas as pd

RAW = "trends_raw.parquet"
WINDOWS = [("2016-01-01", "2020-12-31"), ("2021-01-01", pd.Timestamp.today().strftime("%Y-%m-%d"))]
# "Holdings" / "Group" are KEPT: they disambiguate ("Celsius Holdings" vs the
# temperature unit). Common-word names remain a known source of noise.
_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|"
                     r"class [a-c]|common stock|ordinary shares|n\.?v|s\.?a|ag|se|the)\b\.?", re.I)


def clean_name(n: str) -> str:
    n = re.sub(r"[,\.]", " ", str(n))
    n = _SUFFIX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def sample(n_each: int = 300, seed: int = 5) -> pd.DataFrame:
    from event_study_analyse import bio_flags
    d = pd.read_parquet("base_panel.parquet", columns=["symbol", "week", "ev2x_13w"])
    d = d[~d["symbol"].str.contains(r"\.")]                   # US listings
    ev = d.groupby("symbol")["ev2x_13w"].max()
    bio = bio_flags(ev.index)
    ev = ev[~bio.reindex(ev.index).fillna(False).values]
    rng = np.random.default_rng(seed)
    cases = ev[ev == 1].index.tolist(); ctrls = ev[ev == 0].index.tolist()
    cases = list(rng.choice(cases, min(n_each, len(cases)), replace=False))
    ctrls = list(rng.choice(ctrls, min(n_each, len(ctrls)), replace=False))
    names = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "name"], low_memory=False) \
        .drop_duplicates("symbol").set_index("symbol")["name"]
    s = pd.DataFrame({"symbol": cases + ctrls, "case": [1] * len(cases) + [0] * len(ctrls)})
    s["query"] = s["symbol"].map(names).map(lambda x: clean_name(x) if isinstance(x, str) else None)
    return s[s["query"].str.len() >= 3]


def fetch(s: pd.DataFrame, pause=(6, 12)) -> None:
    from pytrends.request import TrendReq
    done = set()
    if os.path.exists(RAW):
        r = pd.read_parquet(RAW)
        done = set(zip(r["symbol"], r["window"]))
    py = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
    rows, n = [], 0
    for sym, q in zip(s["symbol"], s["query"]):
        for w0, w1 in WINDOWS:
            key = (sym, w0)
            if key in done:
                continue
            for attempt in range(5):
                try:
                    py.build_payload([q], timeframe=f"{w0} {w1}", geo="US")
                    df = py.interest_over_time()
                    break
                except Exception as exc:                      # 429 / transient
                    time.sleep(60 * (attempt + 1))
                    py = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
                    df = None
            if df is not None and len(df):
                rows.append(pd.DataFrame({"symbol": sym, "window": w0, "week": df.index,
                                          "value": df[q].astype(float).values}))
            else:
                rows.append(pd.DataFrame({"symbol": [sym], "window": [w0], "week": [pd.NaT], "value": [np.nan]}))
            n += 1
            time.sleep(random.uniform(*pause))
            if n % 20 == 0:
                _append(rows); rows = []
                print(f"  trends {n} queries", flush=True)
    _append(rows)


def _append(rows):
    if not rows:
        return
    new = pd.concat(rows, ignore_index=True)
    if os.path.exists(RAW):
        new = pd.concat([pd.read_parquet(RAW), new], ignore_index=True)
    new.to_parquet(RAW, index=False)


def _cusum_up(z: np.ndarray, k: float = 0.5) -> float:
    s, m = 0.0, 0.0
    for v in z:
        s = max(0.0, s + v - k)
        m = max(m, s)
    return m


def features(series: pd.Series, t: pd.Timestamp) -> dict:
    x = series[series.index <= t].tail(104)
    if len(x) < 90:
        return {}
    v = x.to_numpy(float)
    rec = {"srch_zero_share": float((v == 0).mean())}
    base, last = v[:-13], v[-13:]
    mu, sd = base.mean(), base.std()
    if mu > 0:
        rec["srch_ratio13"] = float(last.mean() / mu)
    if sd > 0:
        rec["srch_z13"] = float((last.mean() - mu) / sd)
        z = (v[-26:] - mu) / sd
        rec["srch_cusum_up"] = _cusum_up(z)
        t26 = np.arange(26); t78 = np.arange(78)
        rec["srch_slope_brk"] = float((np.polyfit(t26, v[-26:], 1)[0] - np.polyfit(t78, v[-104:-26], 1)[0]) / sd)
    try:
        import ruptures as rpt
        bk = rpt.Pelt(model="rbf", min_size=6).fit(v.reshape(-1, 1)).predict(pen=8)
        cps = [b for b in bk[:-1] if b >= len(v) - 13]
        if cps:
            c = cps[-1]
            rec["srch_cp_up13"] = float(v[c:].mean() > v[:c].mean())
        else:
            rec["srch_cp_up13"] = 0.0
    except Exception:
        pass
    return rec


def evaluate() -> str:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    raw = pd.read_parquet(RAW).dropna(subset=["week"])
    raw["week"] = pd.to_datetime(raw["week"])
    panel = pd.read_parquet("base_panel.parquet")
    panel = panel[panel["symbol"].isin(raw["symbol"].unique())]
    rows = []
    for (sym, w0), g in raw.groupby(["symbol", "window"]):
        ser = g.set_index("week")["value"].sort_index()
        lo, hi = ser.index.min() + pd.Timedelta(weeks=104), ser.index.max()
        for idx, r in panel[(panel["symbol"] == sym) & (panel["week"] >= lo) & (panel["week"] <= hi)].iterrows():
            f = features(ser, r["week"])
            if f:
                rows.append({"idx": idx, **f})
    F = pd.DataFrame(rows).drop_duplicates("idx").set_index("idx")
    d = panel.join(F, how="inner")
    d = d[d["srch_zero_share"] <= 0.30]                      # readable search volume only
    out = [f"# Google Trends attention vs base breakouts\n",
           f"- sample base-months with readable attention: {len(d):,} across {d['symbol'].nunique()} US symbols; "
           f"event months (2x in 13w): {int(d['ev2x_13w'].sum())}; sample event rate {d['ev2x_13w'].mean():.2%}\n",
           "| feature | Q1 rate | Q5 rate | Q5/Q1 | events Q5 |", "|---|---|---|---|---|"]
    feats = ["srch_ratio13", "srch_z13", "srch_cusum_up", "srch_slope_brk", "srch_cp_up13"]
    for f in feats:
        x = d[f].dropna()
        if x.nunique() < 3:
            if f in d:
                a, b = d.loc[d[f] == 0, "ev2x_13w"].mean(), d.loc[d[f] == 1, "ev2x_13w"].mean()
                out.append(f"| {f} (0 vs 1) | {a:.2%} | {b:.2%} | {b / a if a else np.nan:.2f} | "
                           f"{int(d.loc[d[f] == 1, 'ev2x_13w'].sum())} |")
            continue
        q = pd.qcut(x, 5, labels=False, duplicates="drop")
        r = d.loc[q.index].groupby(q)["ev2x_13w"].agg(["mean", "sum"])
        out.append(f"| {f} | {r['mean'].iloc[0]:.2%} | {r['mean'].iloc[-1]:.2%} | "
                   f"{r['mean'].iloc[-1] / r['mean'].iloc[0] if r['mean'].iloc[0] else np.nan:.2f} | "
                   f"{int(r['sum'].iloc[-1])} |")
    # incremental value over price / volume (split by symbol to avoid leakage)
    base_f = [c for c in ["dvol_trend", "updown_vol", "rs26", "r26", "prior_dd", "size_dvol", "vol_ratio"] if c in d]
    syms = d["symbol"].unique(); rng = np.random.default_rng(3); rng.shuffle(syms)
    tr = d["symbol"].isin(syms[: len(syms) // 2])
    def auc(cols):
        X = d[cols].rank(pct=True).fillna(0.5)
        m = LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced").fit(X[tr], d.loc[tr, "ev2x_13w"])
        return roc_auc_score(d.loc[~tr, "ev2x_13w"], m.predict_proba(X[~tr])[:, 1])
    if d["ev2x_13w"].sum() >= 20:
        a0, a1 = auc(base_f), auc(base_f + feats)
        out.append(f"\n- held-out AUC, price/volume only: {a0:.3f}; + attention features: {a1:.3f} "
                   f"(delta {a1 - a0:+.3f})")
    txt = "\n".join(out) + "\n"
    open("TRENDS_ATTENTION_STUDY.md", "w").write(txt)
    return txt


if __name__ == "__main__":
    import sys
    if "--evaluate" in sys.argv:
        print(evaluate())
    else:
        s = sample()
        s.to_csv("trends_sample.csv", index=False)
        print(f"trends sample: {int(s['case'].sum())} cases + {int((s['case'] == 0).sum())} controls", flush=True)
        fetch(s)
        print(evaluate())
