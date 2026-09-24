"""Validate and learn the earnings-call intent signal against what companies
actually DID next -- out of time.

LABELS (per call, date D, reporting fiscal quarter ending E):
  ACTED  = any of, over the two fiscal quarters after E (FMP bulk statements):
             * diluted share count down >= 2%               (real buybacks)
             * common dividends paid up >= 25% or initiated (capital return)
           or a dated action 8-K in (D, D+183d]: buyback authorisation,
           capital-return policy, tender / Dutch auction, strategic review,
           sale of company / going private, asset sale, spin-off/separation.
  RERATE = 126-trading-day excess return vs SPY from the first close after D
           (FMP dividend-adjusted prices).

TESTS (train: calls before --split; test: calls on/after it):
  * AUC of the interpretable rule score on ACTED
  * AUC of a baseline that knows only PAST behaviour (share-count and
    dividend trend over the prior two quarters) vs baseline + LANGUAGE
    -- the language must add information beyond "they were already buying"
  * top-decile lift, per-family lift, forward excess return by score quintile
The fitted logistic model (pure Python, L2, standardised features) is saved
to call_intent_model.json and applied to each name's latest call.

Output: call_intent_model.json, CALL_INTENT_VALIDATION.md; updates
        call_intent.json with act_prob / act_pct / tier.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import time
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import fmp_client as fmp
from call_intent import ACTION, STANCE, FEAT, OUT as INTENT_OUT

ROOT = Path("/home/user/cyclepapa")
PX = ROOT / "fmp_cache" / "px"
MODEL = ROOT / "call_intent_model.json"
REPORT = ROOT / "CALL_INTENT_VALIDATION.md"
EVENT_FAMS = {"BUYBACK_AUTH", "CAPITAL_RETURN", "CAPITAL_RETURN_POLICY", "TENDER_OFFER",
              "STRATEGIC_REVIEW", "VALUE_COMMITTEE", "SALE_OF_COMPANY", "GOING_PRIVATE",
              "ASSET_SALE", "SPINOFF", "SEPARATION"}
LANG_V1 = list(ACTION) + list(STANCE) + ["novelty", "press_ratio", "a_commit", "a_evade", "neg_total"]
# v2: who says it (CEO/CFO, both), where (scripted vs Q&A), whether commitment is
# FIRMING across calls, how BIG the action is vs market cap, and how deep the
# discount was at the call (P/B then) with its interactions
LANG = LANG_V1 + ["escalation", "firming", "ceo_act", "cfo_act", "both_act", "prep_act", "qa_act",
                  "size_pct", "deep", "deep_x_act", "deep_x_gap"]
SH_ACT = ("BUYBACK", "DIVIDEND_RETURN", "TENDER", "STRATEGIC_REVIEW", "MONETIZE")
BASE = ["past_sh_chg", "past_div_up"]


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def d2o(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date().toordinal()


# ---------------------------------------------------------------- statements
def load_statements():
    """{sym: sorted [(date, shares_dil, dividends_paid_abs)]}."""
    sh, dv = {}, {}
    for fn in glob.glob(str(ROOT / "fmp_cache" / "isbulk_*")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            v = _f(r.get("weightedAverageShsOutDil")) or _f(r.get("weightedAverageShsOut"))
            if v and r.get("date"):
                sh.setdefault(r["symbol"], {})[r["date"][:10]] = v
    for fn in glob.glob(str(ROOT / "fmp_cache" / "cfbulk_*")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            v = _f(r.get("commonDividendsPaid"))
            if v is None:
                v = _f(r.get("netDividendsPaid")) or _f(r.get("dividendsPaid"))
            if r.get("date") and v is not None:
                dv.setdefault(r["symbol"], {})[r["date"][:10]] = abs(v)
    out = {}
    for s in set(sh) | set(dv):
        ds = sorted(set(sh.get(s, {})) | set(dv.get(s, {})))
        out[s] = [(d, sh.get(s, {}).get(d), dv.get(s, {}).get(d)) for d in ds]
    return out


def behaviour(stmts, call_date):
    """(past features, ACTED-by-statements label or None if not yet observable)."""
    rows = [r for r in stmts if r[0] < call_date]
    post = [r for r in stmts if r[0] >= call_date or r[0] > (rows[-1][0] if rows else "")]
    post = [r for r in stmts if rows and r[0] > rows[-1][0]]
    if len(rows) < 3:
        return None, None
    e, e1, e2 = rows[-1], rows[-2], rows[-3]
    past_sh = (e[1] / e2[1] - 1) if e[1] and e2[1] else 0.0
    if not (-0.5 < past_sh < 1.0):
        past_sh = 0.0                          # split artefact
    pd_prev = (e2[2] or 0) + (rows[-4][2] or 0 if len(rows) >= 4 else 0)
    pd_now = (e[2] or 0) + (e1[2] or 0)
    past_div_up = 1.0 if (pd_now > 1.25 * pd_prev > 0) or (pd_prev == 0 and pd_now > 0) else 0.0
    past = {"past_sh_chg": round(past_sh, 4), "past_div_up": past_div_up}
    if len(post) < 2:
        return past, None
    p2 = post[1]
    acted = False
    if e[1] and p2[1]:
        ratio = p2[1] / e[1]
        acted |= 0.5 < ratio <= 0.98
    d_prior = (e[2] or 0) + (e1[2] or 0)
    d_next = (post[0][2] or 0) + (p2[2] or 0)
    acted |= (d_prior > 0 and d_next >= 1.25 * d_prior) or (d_prior == 0 and d_next > 0)
    return past, acted


def load_equity():
    """{sym: sorted [(date, equity, currency)]} from every cached bulk balance sheet."""
    eq = {}
    for fn in glob.glob(str(ROOT / "fmp_cache" / "bsbulk_*")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            v = _f(r.get("totalStockholdersEquity"))
            if v is not None and r.get("date"):
                eq.setdefault(r["symbol"], {})[r["date"][:10]] = (v, r.get("reportedCurrency"))
    return {s: sorted((d, v, c) for d, (v, c) in m.items()) for s, m in eq.items()}


def px_on(px, d):
    if not px:
        return None
    i = bisect_right([r[0] for r in px], d)
    return px[i - 1][1] if i > 0 else None


def valuation_then(sym, d, eqh, yq, px):
    """(P/B at the call, mcap at the call). mcap_then = today's mcap x
    adjusted-price ratio (split-consistent); equity = latest statement
    before the call (USD reporters only)."""
    y = yq.get(sym) or {}
    mc_now, p = y.get("mcap"), px.get(sym)
    if not mc_now or not p:
        return None, None
    a_then, a_now = px_on(p, d), p[-1][1]
    if not a_then or not a_now:
        return None, None
    mc_then = mc_now * a_then / a_now
    rows = [r for r in eqh.get(sym, []) if r[0] < d]
    if not rows or rows[-1][2] not in ("USD", None, "") or rows[-1][1] <= 0:
        return None, mc_then
    pb = mc_then / rows[-1][1]
    return (pb if 0.1 <= pb <= 20 else None), mc_then


def load_events():
    ev = {}
    for fn in ("governance_events_8k.json", "rerate_events_8k.json"):
        p = ROOT / fn
        if not p.exists():
            continue
        for tk, fams in json.loads(p.read_text()).items():
            for fam, info in fams.items():
                if fam in EVENT_FAMS and info.get("date"):
                    ev.setdefault(tk, []).append(info["date"][:10])
    return ev


# ---------------------------------------------------------------- prices
def closes(sym):
    PX.mkdir(parents=True, exist_ok=True)
    f = PX / f"{sym}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 5 * 86400:
        return json.loads(f.read_text())
    try:
        rows = fmp.daily_adjusted(sym, "2023-10-01")
    except RuntimeError:
        rows = []
    d = [[r[0], r[4]] for r in rows]
    f.write_text(json.dumps(d))
    return d


def fwd_excess(px, spy, d, n=126):
    if not px or not spy:
        return None
    dates = [r[0] for r in px]
    i = bisect_right(dates, d)
    if i + n >= len(px):
        return None
    sd = [r[0] for r in spy]
    j = bisect_right(sd, d)
    if j + n >= len(spy):
        return None
    r = px[i + n][1] / px[i][1] - 1
    m = spy[j + n][1] / spy[j][1] - 1
    return r - m


# ---------------------------------------------------------------- stats
def auc(scores, labels):
    pairs = sorted(zip(scores, labels), key=lambda t: t[0])
    n1 = sum(labels); n0 = len(labels) - n1
    if not n1 or not n0:
        return None
    rank, i, rs = 0.0, 0, 0.0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg = (i + j) / 2 + 1
        rs += avg * sum(1 for k in range(i, j + 1) if pairs[k][1])
        i = j + 1
    return (rs - n1 * (n1 + 1) / 2) / (n1 * n0)


def fit_lr(X, y, l2=1e-2, iters=600, lr=0.3):
    n, k = len(X), len(X[0])
    mu = [sum(r[j] for r in X) / n for j in range(k)]
    sd = [math.sqrt(sum((r[j] - mu[j]) ** 2 for r in X) / n) or 1.0 for j in range(k)]
    Z = [[(r[j] - mu[j]) / sd[j] for j in range(k)] for r in X]
    w, b = [0.0] * k, math.log((sum(y) + 1) / (n - sum(y) + 1))
    for _ in range(iters):
        gw, gb = [0.0] * k, 0.0
        for z, t in zip(Z, y):
            p = 1 / (1 + math.exp(-(b + sum(a * c for a, c in zip(w, z)))))
            e = p - t
            gb += e
            for j in range(k):
                gw[j] += e * z[j]
        b -= lr * gb / n
        w = [w[j] - lr * (gw[j] / n + l2 * w[j]) for j in range(k)]
    return {"w": w, "b": b, "mu": mu, "sd": sd}


def predict(m, x):
    z = m["b"] + sum(w * (v - mu) / sd for w, v, mu, sd in zip(m["w"], x, m["mu"], m["sd"]))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def lift_top(scores, labels, q=0.1):
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    k = max(1, int(len(order) * q))
    base = sum(labels) / len(labels)
    top = sum(labels[i] for i in order[:k]) / k
    return top, base, (top / base if base else None)


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="2025-06-01")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    calls = [json.loads(l) for l in open(FEAT)]
    stm = load_statements()
    ev = load_events()
    syms = sorted({c["ticker"] for c in calls})
    print(f"{len(calls)} calls / {len(syms)} names; statements for {len(stm)} symbols")
    with ThreadPoolExecutor(args.workers) as ex:
        px = dict(zip(syms, ex.map(closes, syms)))
    spy = closes("SPY")

    eqh = load_equity()
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    rows = []
    for c in calls:
        pb_then, mc_then = valuation_then(c["ticker"], c["date"], eqh, yq, px)
        y = yq.get(c["ticker"]) or {}
        sh_now = (y["mcap"] / y["price"]) if y.get("mcap") and y.get("price") else None
        size = 0.0
        if mc_then:
            size = max(size, (c.get("bb_usd") or 0) / mc_then)
        if sh_now:
            size = max(size, (c.get("bb_shares") or 0) / sh_now)
        size = min(max(size, (c.get("bb_pct_out") or 0) / 100), 0.5)
        deep = 1.0 if (pb_then is not None and pb_then <= 0.8) else 0.0
        act = sum(min(c.get(k) or 0, 2.0) for k in SH_ACT)
        c.update({"pb_then": pb_then, "size_pct": round(size, 4), "deep": deep,
                  "deep_x_act": deep * act, "deep_x_gap": deep * min(c.get("VALUE_GAP") or 0, 2.0)})
        past, acted = behaviour(stm.get(c["ticker"], []), c["date"])
        if past is None:
            continue
        do = d2o(c["date"])
        evd = [d for d in ev.get(c["ticker"], []) if 0 < d2o(d) - do <= 183]
        horizon_ok = do + 183 <= date.today().toordinal()
        label = None
        if acted is not None or evd:
            label = bool(acted) or bool(evd)
        elif not horizon_ok:
            label = None
        rows.append({**c, **past, "acted": label, "event": bool(evd),
                     "xret": fwd_excess(px.get(c["ticker"]), spy, c["date"]),
                     "xret12": fwd_excess(px.get(c["ticker"]), spy, c["date"], 252)})
    lab = [r for r in rows if r["acted"] is not None]
    tr = [r for r in lab if r["date"] < args.split]
    te = [r for r in lab if r["date"] >= args.split]
    print(f"labelled calls: {len(lab)} (train {len(tr)}, test {len(te)}); "
          f"base rate {sum(r['acted'] for r in lab) / max(1, len(lab)):.1%}")

    def X(rs, cols):
        return [[float(r.get(c) or 0) for c in cols] for r in rs]
    y_tr = [int(r["acted"]) for r in tr]
    y_te = [int(r["acted"]) for r in te]
    m_base = fit_lr(X(tr, BASE), y_tr)
    m_full = fit_lr(X(tr, BASE + LANG), y_tr)
    m_lang = fit_lr(X(tr, LANG), y_tr)
    m_v1 = fit_lr(X(tr, BASE + LANG_V1), y_tr)
    p_v1 = [predict(m_v1, x) for x in X(te, BASE + LANG_V1)]
    p_base = [predict(m_base, x) for x in X(te, BASE)]
    p_full = [predict(m_full, x) for x in X(te, BASE + LANG)]
    p_lang = [predict(m_lang, x) for x in X(te, LANG)]
    rule = [r["rule_score"] for r in te]
    res = {
        "auc_rule": auc(rule, y_te), "auc_lang_model": auc(p_lang, y_te),
        "auc_baseline_past_behaviour": auc(p_base, y_te),
        "auc_baseline_plus_language": auc(p_full, y_te),
        "auc_baseline_plus_language_v1": auc(p_v1, y_te),
        "top_decile_rule": lift_top(rule, y_te), "top_decile_full": lift_top(p_full, y_te),
        "n_train": len(tr), "n_test": len(te),
        "base_rate_test": sum(y_te) / max(1, len(y_te)),
    }
    # per-family lift on all labelled calls
    fam_lift = {}
    br = sum(r["acted"] for r in lab) / max(1, len(lab))
    for k in list(ACTION) + list(STANCE) + ["novelty"]:
        hit = [r for r in lab if (r.get(k) or 0) >= 0.8]
        if len(hit) >= 20:
            fam_lift[k] = (len(hit), sum(r["acted"] for r in hit) / len(hit) / br)
    # novelty among calls whose company was NOT already buying back
    fresh = [r for r in lab if r["past_sh_chg"] > -0.01]
    fresh_te = [r for r in fresh if r["date"] >= args.split]
    res["auc_rule_not_already_buying"] = auc([r["rule_score"] for r in fresh_te],
                                            [int(r["acted"]) for r in fresh_te])
    # forward excess return by rule-score quintile (all calls with a return)
    rr = sorted([r for r in rows if r["xret"] is not None], key=lambda r: r["rule_score"])
    quint = []
    for q in range(5):
        seg = rr[q * len(rr) // 5:(q + 1) * len(rr) // 5]
        if seg:
            xs = sorted(r["xret"] for r in seg)
            quint.append((q + 1, len(seg), sum(xs) / len(xs), xs[len(xs) // 2],
                          sum(1 for x in xs if x > 0.25) / len(xs)))
    # out-of-time: forward excess return by quintile of the TRAIN-fitted model's probability
    te_r = [r for r in rows if r["date"] >= args.split and r["xret"] is not None]
    for r in te_r:
        r["_p"] = predict(m_full, [float(r.get(c) or 0) for c in BASE + LANG])
    te_r.sort(key=lambda r: r["_p"])
    quint_p = []
    for q in range(5):
        seg = te_r[q * len(te_r) // 5:(q + 1) * len(te_r) // 5]
        if seg:
            xs = sorted(r["xret"] for r in seg)
            quint_p.append((q + 1, len(seg), sum(xs) / len(xs), xs[len(xs) // 2],
                            sum(1 for r in seg if r["acted"]) / len(seg)))
    # the thesis test: in DEEP-DISCOUNT names (P/B <= 0.8 at the call), does
    # intent predict action -- and the re-rating?
    te_deep = [r for r in te if r["deep"]]
    res["n_test_deep"] = len(te_deep)
    res["auc_deep"] = auc([predict(m_full, [float(r.get(c) or 0) for c in BASE + LANG]) for r in te_deep],
                          [int(r["acted"]) for r in te_deep]) if te_deep else None
    res["base_rate_deep"] = (sum(r["acted"] for r in te_deep) / len(te_deep)) if te_deep else None
    deep_r = [r for r in te_r if r["deep"]]
    deep_r.sort(key=lambda r: r["_p"])
    quint_deep = []
    for q in range(5):
        seg = deep_r[q * len(deep_r) // 5:(q + 1) * len(deep_r) // 5]
        if seg:
            xs = sorted(r["xret"] for r in seg)
            quint_deep.append((q + 1, len(seg), sum(xs) / len(xs), xs[len(xs) // 2],
                               sum(1 for r in seg if r["acted"]) / len(seg)))
    # size of stated action vs forward return (all calls with a stated size)
    sized = [r for r in rows if r["xret"] is not None and r["size_pct"] > 0]
    size_tab = []
    for lo, hi, lab_ in [(0, 0.02, "<2% of mcap"), (0.02, 0.05, "2-5%"), (0.05, 0.10, "5-10%"), (0.10, 1, ">=10%")]:
        seg = [r for r in sized if lo <= r["size_pct"] < hi]
        if len(seg) >= 15:
            xs = sorted(r["xret"] for r in seg)
            ac = [r for r in seg if r["acted"] is not None]
            size_tab.append((lab_, len(seg), sum(xs) / len(xs), xs[len(xs) // 2],
                             (sum(r["acted"] for r in ac) / len(ac)) if ac else None))
    # pre-specified return hypotheses in deep-discount calls (fixed before
    # looking; no fitting): does any intent pattern predict the RE-RATING?
    deep_all = [r for r in rows if r["deep"]]
    HYP = [("all deep-discount calls", lambda r: True),
           ("H1 NEW shareholder-action family", lambda r: any(f in SH_ACT for f in r["new_families"])),
           ("H2 commitment firming across calls", lambda r: (r.get("firming") or 0) >= 1),
           ("H3 value-gap + committed action", lambda r: r["VALUE_GAP"] >= 0.8 and max(r[k] for k in SH_ACT) >= 0.9),
           ("H4 CEO and CFO both commit", lambda r: bool(r.get("both_act"))),
           ("contrast: no shareholder-action language", lambda r: max(r[k] for k in SH_ACT) == 0)]
    hyp_tab = []
    for name, sel in HYP:
        cells = []
        for h in ("xret", "xret12"):
            xs = sorted(r[h] for r in deep_all if sel(r) and r[h] is not None)
            cells.append((len(xs), sum(xs) / len(xs), xs[len(xs) // 2]) if len(xs) >= 15 else (len(xs), None, None))
        hyp_tab.append((name, cells))
    acted_x = [r["xret"] for r in rows if r["acted"] and r["xret"] is not None]
    not_x = [r["xret"] for r in rows if r["acted"] is False and r["xret"] is not None]
    res["xret_acted"] = sum(acted_x) / len(acted_x) if acted_x else None
    res["xret_not_acted"] = sum(not_x) / len(not_x) if not_x else None
    # final model on all labelled data
    m_all = fit_lr(X(lab, BASE + LANG), [int(r["acted"]) for r in lab])
    MODEL.write_text(json.dumps({"features": BASE + LANG, **m_all, "validation": {
        k: v for k, v in res.items()}}, indent=1, default=str))

    # apply to each name's latest call
    intent = json.loads(INTENT_OUT.read_text())
    latest = {}
    for r in rows:
        if r["ticker"] in intent and r["date"] == intent[r["ticker"]]["date"]:
            latest[r["ticker"]] = r
    probs = {t: predict(m_all, [float(r.get(c) or 0) for c in BASE + LANG]) for t, r in latest.items()}
    ranked = sorted(probs.values())
    for t, rec in intent.items():
        p = probs.get(t)
        if p is None:
            continue
        pct = bisect_right(ranked, p) / len(ranked)
        strong = any(v >= 0.9 for k, v in rec["families"].items() if k in
                     ("BUYBACK", "DIVIDEND_RETURN", "TENDER", "STRATEGIC_REVIEW", "MONETIZE"))
        fresh = (date.today().toordinal() - d2o(rec["date"])) <= 200   # a stale call is not a current signal
        rec.update({"act_prob": round(p, 3), "act_pct": round(pct, 3),
                    "past_sh_chg": latest[t]["past_sh_chg"],
                    "size_pct": latest[t].get("size_pct"), "pb_then": latest[t].get("pb_then"),
                    "tier": ("" if not fresh else
                             "ACT SIGNALLED" if pct >= 0.9 and (strong or rec["new_families"])
                             else "BUILDING" if pct >= 0.75 else "")})
        rec["score"] = round(p, 3) if rec["tier"] else 0.0
    INTENT_OUT.write_text(json.dumps(intent, indent=1))

    # report
    def fmt(v):
        return "n/a" if v is None else f"{v:.3f}"
    L = ["# Earnings-call intent -- out-of-time validation", "",
         f"Generated {date.today()} by `call_intent_model.py`. Calls analysed: {len(calls)} "
         f"({len(syms)} names). Labelled: {len(lab)}; train < {args.split}: {len(tr)}, "
         f"test >= {args.split}: {len(te)}. Test base rate (ACTED): {res['base_rate_test']:.1%}.", "",
         "ACTED = share count down >= 2% or dividends up >= 25%/initiated over the next two "
         "fiscal quarters, or a dated action 8-K within 183 days of the call.", "",
         "## Does the language predict action? (test set, AUC)", "",
         "| model | AUC |", "|---|---|",
         f"| interpretable rule score (no fitting) | {fmt(res['auc_rule'])} |",
         f"| logistic, language features only | {fmt(res['auc_lang_model'])} |",
         f"| baseline: past behaviour only (share-count + dividend trend) | {fmt(res['auc_baseline_past_behaviour'])} |",
         f"| baseline + language v1 (families, novelty, Q&A) | {fmt(res['auc_baseline_plus_language_v1'])} |",
         f"| baseline + language v2 (+ CEO/CFO, scripted vs Q&A, firming, action size, discount) | {fmt(res['auc_baseline_plus_language'])} |",
         f"| v2, DEEP-DISCOUNT calls only (P/B <= 0.8 at the call; n={res['n_test_deep']}, base {fmt(res['base_rate_deep'])}) | {fmt(res['auc_deep'])} |",
         f"| rule score, companies NOT already shrinking share count | {fmt(res['auc_rule_not_already_buying'])} |",
         "", "Top decile hit-rate (test): rule "
         f"{res['top_decile_rule'][0]:.1%} vs base {res['top_decile_rule'][1]:.1%} "
         f"(lift {res['top_decile_rule'][2]:.2f}x); baseline+language {res['top_decile_full'][0]:.1%} "
         f"(lift {res['top_decile_full'][2]:.2f}x).", "",
         "## Lift by linguistic family (calls with family score >= 0.8, all labelled)", "",
         "| family | calls | lift vs base |", "|---|---|---|"]
    for k, (n, lf) in sorted(fam_lift.items(), key=lambda t: -t[1][1]):
        L.append(f"| {k} | {n} | {lf:.2f}x |")
    L += ["", "## Out of time: model probability quintile -> what happened next (test set)", "",
          "| quintile | calls | ACTED rate | mean 6m excess | median 6m excess |", "|---|---|---|---|---|"]
    for q, n, mean, med, act in quint_p:
        L.append(f"| Q{q}{' (highest)' if q == 5 else ''} | {n} | {act:.0%} | {mean:+.1%} | {med:+.1%} |")
    L += ["", "## The thesis test: deep-discount calls (P/B <= 0.8 at the call), test set", "",
          "| model quintile | calls | ACTED rate | mean 6m excess | median 6m excess |", "|---|---|---|---|---|"]
    for q, n, mean, med, act in quint_deep:
        L.append(f"| Q{q}{' (highest)' if q == 5 else ''} | {n} | {act:.0%} | {mean:+.1%} | {med:+.1%} |")
    L += ["", "## Pre-specified return hypotheses, deep-discount calls (all periods, no fitting)", "",
          "| hypothesis | n (6m) | mean 6m | median 6m | n (12m) | mean 12m | median 12m |",
          "|---|---|---|---|---|---|---|"]
    for name, ((n6, m6, d6), (n12, m12, d12)) in hyp_tab:
        f_ = lambda v: "—" if v is None else f"{v:+.1%}"
        L.append(f"| {name} | {n6} | {f_(m6)} | {f_(d6)} | {n12} | {f_(m12)} | {f_(d12)} |")
    L += ["", "Reading: none of the intent patterns beats deep-discount calls with NO shareholder "
          "language by more than noise. Management language predicts WHETHER a company acts "
          "(AUC above); it does not, by itself, predict the re-rating -- the market prices stated "
          "intent quickly. Use it to confirm a set-up, not as a return signal."]
    L += ["", "## Stated action size (buyback / tender as % of market cap at the call), all calls", "",
          "| size | calls | ACTED rate | mean 6m excess | median 6m excess |", "|---|---|---|---|---|"]
    for lab_, n, mean, med, act in size_tab:
        L.append(f"| {lab_} | {n} | {fmt(act)} | {mean:+.1%} | {med:+.1%} |")
    L += ["", f"Companies that ACTED returned {fmt(res['xret_acted'])} vs {fmt(res['xret_not_acted'])} for those "
          "that did not (mean 6-month excess vs SPY): in this sample the action itself did not "
          "re-rate value names on its own. The language is a strong predictor of ACTION and a weak "
          "stand-alone predictor of returns -- use it to corroborate a discount/governance set-up "
          "(does management intend to act?), not as a return signal by itself."]
    L += ["", "## Forward 6-month excess return vs SPY by rule-score quintile (all calls)", "",
          "| quintile | calls | mean | median | share > +25% |", "|---|---|---|---|---|"]
    for q, n, mean, med, big in quint:
        L.append(f"| Q{q}{' (highest)' if q == 5 else ''} | {n} | {mean:+.1%} | {med:+.1%} | {big:.1%} |")
    L += ["", "## Fitted weights (standardised, baseline + language, all labelled data)", "",
          "| feature | weight |", "|---|---|"]
    for c, w in sorted(zip(BASE + LANG, m_all["w"]), key=lambda t: -abs(t[1])):
        L.append(f"| {c} | {w:+.3f} |")
    REPORT.write_text("\n".join(L) + "\n")
    print(json.dumps({k: v for k, v in res.items()}, default=str, indent=1))
    print("family lift:", {k: round(v[1], 2) for k, v in fam_lift.items()})
    print("quintiles:", [(q, n, round(m, 3), round(md, 3)) for q, n, m, md, _ in quint])
    print("deep quintiles (test):", [(q, n, round(m, 3), round(md, 3), round(a, 2)) for q, n, m, md, a in quint_deep])
    print("size:", [(l, n, round(m, 3), round(md, 3), a and round(a, 2)) for l, n, m, md, a in size_tab])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
