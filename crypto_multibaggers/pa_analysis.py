"""Evaluate the Schabacker / Japanese / Dalton factors and the trend-following rules.

    python -m crypto_multibaggers.pa_analysis

Four tests, each fixed on 2017-21 and scored on 2022+ where a choice is made:
  P1  before re-ratings: event vs matched placebo (AUC; prevalence for patterns)
  P2  once a coin pops: 3x rate of triggers with vs without each factor
  P3  as a standalone screen: 3x hits against the same-date base rate
  P4  as trading rules: trade statistics and an equal-weight portfolio per rule
  P5  how many 3x+ runs each rule got into, and what it kept
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import analysis as A
from . import pa_study, panel, study
from .config import ANALYSIS_DIR, DATA_DIR
from .priceaction import PA_DAY0, PA_FEATURES

warnings.filterwarnings("ignore", category=RuntimeWarning)
CUT = pd.Timestamp("2022-01-01")
PA_KEYS, D0_KEYS = list(PA_FEATURES), list(PA_DAY0)
META = {**PA_FEATURES, **PA_DAY0}
LABEL = {k: v[0] for k, v in META.items()}
SCHOOL = {k: v[1] for k, v in META.items()}
KEY_RULES = ["donchian55", "don+candles+sanyaku", "don+candles", "don+sanyaku", "don+all3", "trigger_top", "sch_any_bo"]


def _is_binary(x: pd.Series) -> bool:
    u = pd.unique(x.dropna())
    return len(u) <= 2 and set(np.round(u, 6)).issubset({0.0, 1.0})


def load():
    ev, pl, scr, live = study.load()
    pe, pp, ps, plv, tr = pa_study.load()
    drop = set(ev.loc[ev.symbol.isin(panel.COMMODITY_BACKED), "event_id"])
    ev = ev[~ev.symbol.isin(panel.COMMODITY_BACKED)].join(pe)
    pl = pl[~pl.symbol.isin(panel.COMMODITY_BACKED) & ~pl.event_id.isin(drop)].join(pp)
    scr = scr[~scr.symbol.isin(panel.COMMODITY_BACKED)].join(ps)
    live = live[~live.symbol.isin(panel.COMMODITY_BACKED)].join(plv)
    for df in (ev, pl, scr, live):
        if "date" in df:
            df["date"] = pd.to_datetime(df["date"])
        num = df.select_dtypes("number").columns
        df[num] = df[num].replace([np.inf, -np.inf], np.nan)
    tr = tr[~tr.symbol.isin(panel.COMMODITY_BACKED)]
    return ev, pl, scr, live, tr


def usable(df: pd.DataFrame, keys) -> list[str]:
    """Drop factors that almost never fire (gaps in a 24/7 market)."""
    out = []
    for k in keys:
        x = df[k]
        if _is_binary(x) and x.mean() < 0.002:
            continue
        out.append(k)
    return out


# ------------------------------------------------------------------------ P1
def p1_grid(ev, pl, fam_keys=("all", "10x+", "5-10x", "3-5x", "<2x")):
    fam = A.families(ev)
    keys = usable(pl, PA_KEYS)
    rows = []
    for f in keys:
        binary = _is_binary(pl[f])
        for k in fam_keys:
            m = fam[k]
            ids = set(ev.loc[m, "event_id"])
            a, b = ev.loc[m, f], pl.loc[pl.event_id.isin(ids), f]
            auc, p = A.auc_p(a, b)
            rows.append({"feature": f, "label": LABEL[f], "group": SCHOOL[f], "family": k, "auc": auc, "p": p,
                         "ma": float(a.mean()) if binary else A.med(a), "mb": float(b.mean()) if binary else A.med(b),
                         "binary": binary, "n": int(a.notna().sum())})
    g = pd.DataFrame(rows)
    g["q"] = A.bh(g["p"].to_numpy())
    return g


# ------------------------------------------------------------------------ P2
def p2_follow_through(ev, q=0.8, min_n=40):
    e = ev[ev["complete"]].copy()
    y = (e["mult_180"] >= 3).to_numpy()
    tr = (e["date"] < CUT).to_numpy()
    te = ~tr
    base_tr, base_te = y[tr].mean(), y[te].mean()
    rows = []
    for f in usable(e, PA_KEYS + D0_KEYS):
        x = e[f].to_numpy(float)
        if _is_binary(e[f]):
            on = x == 1
            n_tr, n_te = int((on & tr).sum()), int((on & te).sum())
            if n_tr < min_n or n_te < min_n:
                continue
            h_tr, h_te = y[on & tr].mean(), y[on & te].mean()
            rows.append({"feature": f, "label": LABEL[f], "group": SCHOOL[f], "kind": "pattern", "direction": 1,
                         "n_train": n_tr, "n_test": n_te, "hit_train": h_tr, "hit_test": h_te,
                         "lift_train": h_tr / base_tr, "lift_test": h_te / base_te,
                         "hit_off_test": y[~on & te].mean()})
        else:
            ok_tr, ok_te = tr & ~np.isnan(x), te & ~np.isnan(x)
            if ok_tr.sum() < 300 or ok_te.sum() < 300:
                continue
            a = roc_auc_score(y[ok_tr], x[ok_tr])
            d = 1 if a >= 0.5 else -1
            xt, xr = d * x[ok_te], d * x[ok_tr]
            top_te, top_tr = xt >= np.quantile(xt, q), xr >= np.quantile(xr, q)
            rows.append({"feature": f, "label": LABEL[f], "group": SCHOOL[f], "kind": "level", "direction": d,
                         "n_train": int(top_tr.sum()), "n_test": int(top_te.sum()),
                         "hit_train": y[ok_tr][top_tr].mean(), "hit_test": y[ok_te][top_te].mean(),
                         "lift_train": y[ok_tr][top_tr].mean() / base_tr, "lift_test": y[ok_te][top_te].mean() / base_te,
                         "hit_off_test": y[ok_te][~top_te].mean()})
    out = pd.DataFrame(rows)
    out["consistent"] = np.sign(out["lift_train"] - 1) == np.sign(out["lift_test"] - 1)
    return out.sort_values("lift_test", ascending=False), {"base_train": float(base_tr), "base_test": float(base_te)}


# ------------------------------------------------------------------------ P3
def p3_screen(scr, top=0.9):
    """Observed / expected 3x hits, with expected hits from each date's base rate."""
    s = scr[scr["complete"]].copy()
    s["y"] = (s["mult_180"] >= 3).astype(float)
    s["base"] = s.groupby("date")["y"].transform("mean")
    s["period"] = np.where(s["date"] < CUT, "train", "test")
    rows = []
    for f in usable(s, PA_KEYS):
        x = s[f]
        res = {}
        if _is_binary(x):
            flag = x == 1
            direction = 1
        else:
            tr = s["period"] == "train"
            ok = tr & x.notna()
            direction = 1 if roc_auc_score(s.loc[ok, "y"], x[ok]) >= 0.5 else -1
            r = (direction * x).groupby(s["date"]).rank(pct=True)
            flag = r >= top
        for per, d in s.groupby("period"):
            fl = flag.loc[d.index]
            obs, exp = d.loc[fl, "y"].sum(), d.loc[fl, "base"].sum()
            res[per] = (obs / exp if exp > 0 else np.nan, int(fl.sum()), d.loc[fl, "y"].mean())
        rows.append({"feature": f, "label": LABEL[f], "group": SCHOOL[f], "direction": direction,
                     "kind": "pattern" if _is_binary(x) else "top decile",
                     "lift_train": res["train"][0], "n_train": res["train"][1], "lift_test": res["test"][0],
                     "n_test": res["test"][1], "hit_test": res["test"][2]})
    return pd.DataFrame(rows).sort_values("lift_test", ascending=False)


# ------------------------------------------------------------------------ P4
def trade_stats(t: pd.DataFrame) -> dict:
    r = t["ret"].to_numpy()
    if len(r) == 0:
        return {"n": 0}
    wins, losses = r[r > 0], r[r <= 0]
    return {"n": int(len(r)), "win": float((r > 0).mean()), "mean": float(r.mean()), "median": float(np.median(r)),
            "mean_log": float(np.log1p(r).mean()),
            "pf": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else np.nan,
            "payoff": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else np.nan,
            "p2x": float((r >= 1.0).mean()), "p3x": float((r >= 2.0).mean()), "hold": float(t["hold"].mean())}


def p4_trades(tr: pd.DataFrame) -> pd.DataFrame:
    t = tr[~tr["open"]].copy()
    t["period"] = np.where(t["entry"] < CUT, "train", "test")
    rows = []
    for (rule, ex), g in t.groupby(["rule", "exit"]):
        row = {"rule": rule, "label": pa_study.ENTRY_LABELS.get(rule, rule), "exit": pa_study.EXITS[ex]}
        for per in ("train", "test"):
            for k, v in trade_stats(g[g["period"] == per]).items():
                row[f"{k}_{per}"] = v
        rows.append(row)
    return pd.DataFrame(rows)


def portfolio(tr: pd.DataFrame, closes: pd.DataFrame, rules, exit_kind=0, frac=0.01) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fixed-fraction trend-following book per rule: each entry gets `frac` of
    the previous close's equity (or the cash that is left), positions are
    never rebalanced and run until the rule's exit, costs are paid at entry and
    exit, and exit proceeds are available the same day. Train (2017-21) and
    test (2022+) are separate books starting from 1."""
    C = closes.to_numpy()
    dates = closes.index
    col = {s: i for i, s in enumerate(closes.columns)}
    di = pd.Series(np.arange(len(dates)), index=dates)
    navs, stats = {}, []
    periods = {"train": (pd.Timestamp(pa_study.START), CUT - pd.Timedelta(days=1)), "test": (CUT, dates[-1])}
    for rule in rules:
        t = tr[(tr["rule"] == rule) & (tr["exit"] == exit_kind)]
        if t.empty:
            continue
        nav_full = pd.Series(np.nan, index=dates)
        for per, (lo, hi) in periods.items():
            tp = t[(t["entry"] >= lo) & (t["entry"] <= hi)]
            a0, a1 = di[lo], di[hi]
            L = a1 - a0 + 1
            posval, credit, npos = np.zeros(L), np.zeros(L), np.zeros(L)
            equity = np.ones(L)
            cash = 1.0
            by_day: dict[int, list] = {}
            for row in tp.itertuples():
                by_day.setdefault(di[row.entry] - a0, []).append(row)
            for d in range(L):
                cash += credit[d]
                eq_prev = equity[d - 1] if d else 1.0
                for row in by_day.get(d, []):
                    alloc = min(frac * eq_prev, cash)
                    if alloc <= 1e-4 * eq_prev:
                        continue
                    j = col[row.symbol]
                    e = di[row.entry]
                    x_true = di[row.exit_date]
                    x = min(x_true, a1)
                    cost = pa_study.COST + (pa_study.COST_THIN if row.dv30 < 1e6 else 0.0)
                    path = pd.Series(C[e:x + 1, j] / C[e, j]).ffill().to_numpy()
                    units = alloc / (1 + cost)
                    cash -= alloc
                    end = d + len(path) - 1
                    if x_true <= a1:                         # closed inside the book: back to cash on the exit day
                        posval[d:end] += units * path[:-1]
                        npos[d:end] += 1
                        credit[end] += units * path[-1] * (1 - cost)
                    else:                                    # still open at the end: marked to market
                        posval[d:end + 1] += units * path
                        npos[d:end + 1] += 1
                equity[d] = cash + posval[d]
            eq = pd.Series(equity, index=dates[a0:a1 + 1])
            nav_full.loc[eq.index] = eq.to_numpy()
            d_ret = eq.pct_change().fillna(0)
            yrs = len(eq) / 365
            vol = d_ret.std() * np.sqrt(365)
            stats.append({"rule": rule, "label": pa_study.ENTRY_LABELS.get(rule, rule), "period": per,
                          "cagr": eq.iloc[-1] ** (1 / yrs) - 1, "vol": vol,
                          "sharpe": d_ret.mean() * 365 / vol if vol > 0 else np.nan,
                          "max_dd": float((eq / eq.cummax() - 1).min()), "final": float(eq.iloc[-1]),
                          "avg_positions": float(npos.mean()), "trades": int(len(tp))})
        navs[rule] = nav_full
    return pd.DataFrame(navs), pd.DataFrame(stats)


# ------------------------------------------------------------------------ P5
def p5_capture(ev: pd.DataFrame, tr: pd.DataFrame, exit_kind=0) -> pd.DataFrame:
    big = ev[ev["complete"] & (ev["mult_180"] >= 3)][["symbol", "date", "mult_180"]]
    t = tr[tr["exit"] == exit_kind]
    rows = []
    for rule, g in t.groupby("rule"):
        m = big.merge(g[["symbol", "entry", "ret", "peak_mult"]], on="symbol")
        m = m[(m["entry"] >= m["date"] - pd.Timedelta(days=5)) & (m["entry"] <= m["date"] + pd.Timedelta(days=10))]
        m = m.sort_values("entry").drop_duplicates(["symbol", "date"])
        rows.append({"rule": rule, "label": pa_study.ENTRY_LABELS.get(rule, rule), "caught": len(m) / len(big),
                     "kept_median": float(m["ret"].median()) if len(m) else np.nan,
                     "peak_median": float(m["peak_mult"].median()) if len(m) else np.nan,
                     "n_trades": int(len(g))})
    return pd.DataFrame(rows).sort_values("caught", ascending=False)


def run():
    ev, pl, scr, live, tr = load()
    out: dict = {}
    g = p1_grid(ev, pl)
    g.to_csv(ANALYSIS_DIR / "pa_events_vs_placebo.csv", index=False)
    out["grid"] = {"families": [{"key": k, "label": A.fam_label(k)} for k in ("all", "10x+", "5-10x", "3-5x", "<2x")],
                   "rows": g.to_dict("records")}
    ft, fti = p2_follow_through(ev)
    ft.to_csv(ANALYSIS_DIR / "pa_follow_through.csv", index=False)
    out["follow"], out["follow_info"] = ft.to_dict("records"), fti
    sc = p3_screen(scr)
    sc.to_csv(ANALYSIS_DIR / "pa_screen.csv", index=False)
    out["screen"] = sc.to_dict("records")
    ts = p4_trades(tr)
    ts.to_csv(ANALYSIS_DIR / "pa_trade_stats.csv", index=False)
    out["trades"] = ts.to_dict("records")
    p, meta, mkt = panel.load()
    rules = [r for r in pa_study.ENTRY_LABELS if r in set(tr["rule"])]
    navs, ps = portfolio(tr, p["close"], rules, 0)
    ps.to_csv(ANALYSIS_DIR / "pa_portfolios.csv", index=False)
    out["portfolio"] = ps.to_dict("records")
    # out-of-sample books (2022+, each starting at 1) against BTC bought on the same day
    btc = p["close"]["BTCUSD"].loc[CUT:]
    nav_week = navs.loc[CUT:].resample("W").last()
    nav_week["BTC buy and hold"] = (btc / btc.iloc[0]).resample("W").last()
    nav_week.to_csv(ANALYSIS_DIR / "pa_portfolio_nav_weekly_2022.csv")
    keep = [r for r in ["don+candles+sanyaku", "don+sanyaku", "donchian55", "trigger_top"] if r in nav_week] \
        + ["BTC buy and hold"]
    out["nav"] = {"dates": [d.strftime("%Y-%m-%d") for d in nav_week.index],
                  "series": {k: [None if not np.isfinite(v) else round(float(v), 4) for v in nav_week[k]] for k in keep},
                  "labels": {k: pa_study.ENTRY_LABELS.get(k, k) for k in keep}}
    live_path = ANALYSIS_DIR / "pa_live_checklist.csv"
    if live_path.exists():
        lv = pd.read_csv(live_path)
        out["live"] = {"n": int(len(lv)), "n_breakout": int(lv["breakout_55"].sum()),
                       "n_fired": int(lv["best_rule_fired"].sum()), "asof": str(lv["last_date"].max()),
                       "fired": lv[lv["best_rule_fired"]].head(30).to_dict("records")}
    cap = p5_capture(ev, tr)
    cap.to_csv(ANALYSIS_DIR / "pa_capture.csv", index=False)
    out["capture"] = cap.to_dict("records")
    (DATA_DIR / "pa_atlas.json").write_text(json.dumps(out, default=A._json_default))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)
    print(ft.head(20)[["label", "group", "kind", "n_test", "hit_test", "lift_train", "lift_test"]].round(3).to_string())
    print(sc.head(15)[["label", "group", "kind", "lift_train", "lift_test", "n_test"]].round(3).to_string())
    print(ps.pivot_table(index="label", columns="period", values=["cagr", "sharpe", "max_dd"]).round(3).to_string())
    print(cap.head(12).round(3).to_string())
    return out


if __name__ == "__main__":
    run()
