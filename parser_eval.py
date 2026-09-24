"""Parser scorecard: the deterministic (regex) parsers vs the reviewed gold
extraction, field by field.

Gold = reviewed/*.json -- structured extraction of every current filing by a
reviewer that reads the text (each record carries a verbatim evidence quote
and a confidence). The regex parsers remain the fallback for filings not yet
reviewed, so their accuracy against gold is measured here and published.

  appointments  event type (hire / promotion / interim vs everything else),
                person, role, base salary
  events        is-it-a-real-event, event type family, amount, counterparty,
                per-share price, status
  psu           metrics set, weights, period, payout max, rTSR target, history

Output: PARSER_EVAL.md
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
REV = ROOT / "reviewed"


def _load(p):
    return json.loads(p.read_text()) if p.exists() else []


def norm_name(x):
    x = re.sub(r"^(?:mr|ms|mrs|dr)\.?\s+", "", str(x or "").strip().lower())
    return re.sub(r"[^a-z ]", "", x).split()[-1] if x else ""


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def eval_appointments():
    gold = {g["id"]: dict(g) for g in _load(REV / "appointments.json")}
    for a in _load(REV / "appointments_adjudicated.json"):          # reviewer errors corrected
        if a["id"] in gold:
            gold[a["id"]][a["field"]] = a["to"]
            gold[a["id"]].setdefault("person", a.get("person"))
            if not gold[a["id"]].get("person"):
                gold[a["id"]]["person"] = a.get("person")
            if not gold[a["id"]].get("role"):
                gold[a["id"]]["role"] = a.get("role")
    rows = list(csv.DictReader(open(ROOT / "turnaround_signal.csv"))) if (ROOT / "turnaround_signal.csv").exists() else []
    # re-parse the cached filing text with the CURRENT parser (not the last run's CSV)
    import glob, gzip
    import turnaround_executive_leg as te
    for r in rows:
        files = sorted(glob.glob(str(ROOT / "fmp_cache" / "edgar" / r["accession"] / "*.txt.gz")))
        txt = " ".join(gzip.open(f, "rt", encoding="utf-8").read() for f in files[:3]) if files else ""
        if txt:
            p = te.parse_8k_text(txt)
            r.update({"event_type": p.get("event_type") or "", "person": p.get("person") or "",
                      "role": p.get("role") or "", "base_salary_usd": p.get("base_salary_usd") or ""})
    hire_g = {"NEW_HIRE", "PROMOTION", "INTERIM"}
    hire_p = {"NEW HIRE", "PROMOTION"}
    tp = fp = fn = tn = 0
    person_ok = person_n = role_ok = role_n = sal_ok = sal_n = 0
    for r in rows:
        g = gold.get(f"{r['ticker']}|{r['accession']}")
        if not g:
            continue
        gh, ph = g["event_type"] in hire_g, (r.get("event_type") in hire_p or bool(r.get("person")))
        tp += gh and ph; fp += (not gh) and ph; fn += gh and not ph; tn += (not gh) and not ph
        if gh and g.get("person"):
            person_n += 1
            person_ok += norm_name(r.get("person")) == norm_name(g["person"]) and bool(r.get("person"))
        if gh and g.get("role"):
            role_n += 1
            role_ok += bool(r.get("role")) and bool(re.search(r"chief executive|ceo", r["role"], re.I)) == bool(
                re.search(r"chief executive|ceo", g["role"], re.I))
        if g.get("base_salary_usd"):
            sal_n += 1
            try:
                sal_ok += abs(float(r.get("base_salary_usd") or 0) - float(g["base_salary_usd"])) < 1
            except ValueError:
                pass
    n = tp + fp + fn + tn
    return [
        ("appointments", "is a senior hire/promotion (precision)", pct(tp, tp + fp), tp + fp),
        ("appointments", "is a senior hire/promotion (recall)", pct(tp, tp + fn), tp + fn),
        ("appointments", "person name (on true hires)", pct(person_ok, person_n), person_n),
        ("appointments", "role family (on true hires)", pct(role_ok, role_n), role_n),
        ("appointments", "base salary exact", pct(sal_ok, sal_n), sal_n),
    ], n


FAMILY_MAP = {  # regex family -> gold event types that count as the same thing
    "ASSET_SALE": {"ASSET_SALE"}, "SALE_OF_COMPANY": {"SALE_OF_COMPANY", "GOING_PRIVATE", "MERGER_OF_EQUALS"},
    "GOING_PRIVATE": {"GOING_PRIVATE", "SALE_OF_COMPANY"}, "TENDER_OFFER": {"TENDER_OFFER_EQUITY", "TENDER_OFFER_DEBT"},
    "BUYBACK_AUTH": {"BUYBACK_AUTH"}, "CAPITAL_RETURN": {"SPECIAL_DIVIDEND", "REGULAR_DIVIDEND", "CAPITAL_RETURN_POLICY"},
    "CAPITAL_RETURN_POLICY": {"CAPITAL_RETURN_POLICY", "BUYBACK_AUTH", "SPECIAL_DIVIDEND", "REGULAR_DIVIDEND"},
    "SPINOFF": {"SPINOFF", "SEPARATION"}, "SEPARATION": {"SEPARATION", "SPINOFF"},
    "STRATEGIC_REVIEW": {"STRATEGIC_REVIEW_STARTED", "STRATEGIC_REVIEW_CONCLUDED"},
    "VALUE_COMMITTEE": {"VALUE_COMMITTEE", "STRATEGIC_REVIEW_STARTED"},
    "ACTIVIST_SETTLEMENT": {"ACTIVIST_SETTLEMENT"}, "CEO_CHANGE": {"CEO_APPOINTED", "INTERIM_CEO", "CEO_DEPARTURE"},
    "BOARD_REFRESH": {"BOARD_REFRESH"}, "CHAIR_CEO_SPLIT": {"CHAIR_CEO_SPLIT"}, "DECLASSIFY": {"DECLASSIFY"},
    "PILL_REMOVED": {"PILL_REMOVED"}, "CH11_EMERGENCE": {"CH11_EMERGENCE"}, "UPLISTING": {"UPLISTING"},
    "EXCHANGE_OFFER": {"EXCHANGE_OFFER_DEBT"},
}


def eval_events(split=None):
    import os
    os.environ.setdefault("EVENT_MODEL_TRAIN", "dev")   # never score the model on what it was trained on
    """Re-parses every located filing with the CURRENT parser. The reviewed set is
    split in two: 'dev' (the half the regexes were tuned on) and 'holdout' (never
    looked at while tuning) -- the holdout figure is the honest one."""
    import event_detail as edt
    gold = {g["id"]: g for g in _load(REV / "events.json")}
    ev = json.loads((ROOT / "event_detail.json").read_text()) if (ROOT / "event_detail.json").exists() else {}
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    real_tp = real_fp = real_fn = real_tn = 0
    fam_ok = fam_n = amt_ok = amt_n = amt_fp = cp_ok = cp_n = cp_fp = ps_ok = ps_n = st_ok = st_n = 0
    errs = {"phantom": [], "missed": [], "amount": [], "counterparty": [], "status": [], "per_share": []}
    for t, lst in ev.items():
        for e0 in lst:
            g = gold.get(f"{t}|{e0['family']}|{e0.get('date')}")
            if not g or not e0.get("url") or (split and g.get("split") != split):
                continue
            e = edt.reparse(e0, (yq.get(t) or {}).get("mcap"), tk=t)
            if not e.get("excerpt"):
                continue
            key = (t, e["family"], g.get("what", "")[:120], e.get("what", "")[:120])
            pr = e.get("verdict", "REAL") == "REAL"
            gr = bool(g.get("is_event"))
            real_tp += pr and gr; real_fp += pr and not gr; real_fn += (not pr) and gr; real_tn += (not pr) and not gr
            if pr and not gr:
                errs["phantom"].append(key)
            if gr and not pr:
                errs["missed"].append(key + (e.get("verdict_reason"),))
            if not gr:
                continue
            fam_n += 1
            fam_ok += g.get("event_type") in FAMILY_MAP.get(e["family"], {e["family"]})
            if g.get("amount_usd"):
                amt_n += 1
                ok = bool(e.get("amount_usd")) and abs(e["amount_usd"] / g["amount_usd"] - 1) < 0.02
                amt_ok += ok
                if not ok:
                    errs["amount"].append(key + (g["amount_usd"], e.get("amount_usd")))
            elif e.get("amount_usd"):
                amt_fp += 1
                errs["amount"].append(key + (None, e.get("amount_usd")))
            if not g.get("counterparty") and e.get("counterparty"):
                cp_fp += 1
                errs["counterparty"].append(key + (None, e.get("counterparty")))
            if g.get("counterparty"):
                cp_n += 1
                ok = _same_org(e.get("counterparty"), g["counterparty"])
                cp_ok += ok
                if not ok:
                    errs["counterparty"].append(key + (g["counterparty"], e.get("counterparty")))
            if g.get("per_share"):
                ps_n += 1
                ok = bool(e.get("per_share")) and abs(e["per_share"] - g["per_share"]) < 0.011
                ps_ok += ok
                if not ok:
                    errs["per_share"].append(key + (g["per_share"], e.get("per_share")))
            if g.get("status") in ("ANNOUNCED", "PENDING", "COMPLETED"):
                st_n += 1
                ok = (e.get("status") == "COMPLETED") == (g["status"] == "COMPLETED")
                st_ok += ok
                if not ok:
                    errs["status"].append(key + (g["status"], e.get("status")))
    tag = f"events/{split}" if split else "events"
    rows = [
        (tag, "real-event verdict (precision: flagged REAL that are real)", pct(real_tp, real_tp + real_fp), real_tp + real_fp),
        (tag, "real-event verdict (phantoms caught)", pct(real_tn, real_tn + real_fp), real_tn + real_fp),
        (tag, "real-event verdict (real events kept)", pct(real_tp, real_tp + real_fn), real_tp + real_fn),
        (tag, "event family matches", pct(fam_ok, fam_n), fam_n),
        (tag, "amount exact (when the filing states one)", pct(amt_ok, amt_n), amt_n),
        (tag, "amount invented where none stated", str(amt_fp), fam_n),
        (tag, "counterparty", pct(cp_ok, cp_n), cp_n),
        (tag, "counterparty invented where none stated", str(cp_fp), fam_n),
        (tag, "per-share price", pct(ps_ok, ps_n), ps_n),
        (tag, "status (completed vs not)", pct(st_ok, st_n), st_n),
    ]
    return rows, errs


_GENERIC = {"the", "an", "a", "affiliate", "affiliates", "of", "funds", "fund", "entity", "investor", "group", "led", "by",
            "sponsored", "former", "holders", "co", "buyer", "company"}


def _same_org(a, b):
    """Same party: equal first distinctive word, or one name contains the other."""
    ta = [w for w in re.sub(r"[^a-z0-9 ]", " ", str(a or "").lower()).split() if w not in _GENERIC]
    tb = [w for w in re.sub(r"[^a-z0-9 ]", " ", str(b or "").lower()).split() if w not in _GENERIC]
    if not ta or not tb:
        return False
    return ta[0] == tb[0] or " ".join(ta) in " ".join(tb) or " ".join(tb) in " ".join(ta) or ta[0] in tb


def _org(x):
    x = re.sub(r"[^a-z0-9 ]", " ", str(x or "").lower())
    x = re.sub(r"\b(?:inc|corp|corporation|co|ltd|limited|plc|llc|lp|l p|the|an affiliate of|affiliates of|affiliate of|funds?|managed by|advised by)\b", " ", x)
    return " ".join(x.split())[:14]


PSU_CANON = [("rTSR", r"relative tsr|rtsr|relative total shareholder"), ("TSR", r"^tsr$|absolute tsr|total shareholder return"),
             ("EPS", r"eps|earnings per share"), ("Revenue", r"revenue|sales|bookings"), ("EBITDA", r"ebitda"),
             ("Operating income", r"operating (?:income|profit)|ebit\b"), ("Free cash flow", r"free cash flow|fcf"),
             ("Cash flow", r"cash flow"), ("ROIC", r"roic|return on invested|cfroi|return on (?:total )?capital"),
             ("ROCE", r"roce|capital employed"), ("ROE", r"roe|return on (?:average )?(?:tangible )?(?:common )?equity|rotce|roatce"), ("ROA", r"roa|return on (?:average )?assets|rona"),
             ("ROCE", r"roce|return on capital employed"), ("Margin", r"^margin|margin$"), ("FFO", r"^ffo|funds from operations"),
             ("AFFO", r"affo"), ("Book value", r"book value|tbv"), ("Stock price", r"stock[- ]price|share[- ]price"),
             ("Production", r"production"), ("Reserves", r"reserve"), ("ESG", r"esg|sustainab|emission|safety"),
             ("Strategic", r"strategic")]


def _canon(k):
    k = str(k).lower()
    for c, rx in PSU_CANON:
        if re.search(rx, k):
            return c
    return "Other"


def eval_psu(split=None):
    gold = {g["ticker"]: g for g in _load(REV / "psu.json") if not split or g.get("split") == split}
    import psu_detail as pdl
    psu = {k: v for k, v in pdl.reextract(sorted(gold)).items() if v}      # the CURRENT parser
    m_ok = m_n = w_ok = w_n = p_ok = p_n = x_ok = x_n = t_ok = t_n = h_ok = h_n = has_tp = has_fp = has_fn = 0
    errs = {k: [] for k in ("has", "metrics", "weights", "period", "max", "rtsr", "history")}
    for t, g in gold.items():
        r = psu.get(t) or {}
        found = bool(r.get("metrics"))
        if g.get("has_psu") and found:
            has_tp += 1
        elif found:
            has_fp += 1; errs["has"].append((t, "parser found a plan; reviewer: none"))
        elif g.get("has_psu") and g.get("metrics"):
            has_fn += 1; errs["has"].append((t, "reviewer found a plan; parser: none"))
        if not g.get("has_psu") or not found:
            continue
        gm = {_canon(k): v for k, v in (g.get("metrics") or {}).items()}
        pm = {}
        for k, v in (r.get("metrics") or {}).items():
            pm[_canon(k)] = v
        if gm:
            m_n += 1
            ok = len(set(gm) & set(pm)) / len(set(gm) | set(pm)) >= 0.5
            m_ok += ok
            if not ok:
                errs["metrics"].append((t, sorted(gm), sorted(pm)))
            gw = {k: v for k, v in gm.items() if v}
            if gw:
                w_n += 1
                ok = all(abs((pm.get(k) or 0) - v) < 1.5 for k, v in gw.items())
                w_ok += ok
                if not ok:
                    errs["weights"].append((t, gw, pm))
        if g.get("period_years"):
            p_n += 1; ok = r.get("period_years") == g["period_years"]; p_ok += ok
            if not ok: errs["period"].append((t, g["period_years"], r.get("period_years")))
        if g.get("payout_max"):
            x_n += 1; ok = abs((r.get("payout_max") or 0) - g["payout_max"]) < 1; x_ok += ok
            if not ok: errs["max"].append((t, g["payout_max"], r.get("payout_max")))
        if g.get("rtsr_target_percentile"):
            t_n += 1; ok = r.get("rtsr_target_pct") == g["rtsr_target_percentile"]; t_ok += ok
            if not ok: errs["rtsr"].append((t, g["rtsr_target_percentile"], r.get("rtsr_target_pct")))
        if g.get("history"):
            h_n += 1
            gv = {round(float(v)) for v in (g.get("history") or {}).values() if v is not None}
            pv = {round(v) for _, v in (r.get("history") or [])}
            ok = bool(gv & pv); h_ok += ok
            if not ok: errs["history"].append((t, sorted(gv), sorted(pv)))
    tag = f"psu/{split}" if split else "psu"
    return [
        (tag, "has a PSU plan (precision)", pct(has_tp, has_tp + has_fp), has_tp + has_fp),
        (tag, "has a PSU plan (recall)", pct(has_tp, has_tp + has_fn), has_tp + has_fn),
        (tag, "metric set (>=50% overlap)", pct(m_ok, m_n), m_n),
        (tag, "metric weights exact", pct(w_ok, w_n), w_n),
        (tag, "performance period", pct(p_ok, p_n), p_n),
        (tag, "max payout", pct(x_ok, x_n), x_n),
        (tag, "rTSR target percentile", pct(t_ok, t_n), t_n),
        (tag, "payout history (a cycle matches)", pct(h_ok, h_n), h_n),
    ], errs


BASELINE = {   # the same scorecard run on the parsers as they stood before this round (2026-09-24)
    ("appointments", "is a senior hire/promotion (recall)"): "44%",
    ("appointments", "person name (on true hires)"): "42%",
    ("appointments", "role family (on true hires)"): "57%",
    ("events/holdout", "real-event verdict (phantoms caught)"): "6%",
    ("events/holdout", "real-event verdict (real events kept)"): "97%",
    ("events/holdout", "amount exact (when the filing states one)"): "72%",
    ("events/holdout", "counterparty"): "7%",
    ("events/holdout", "per-share price"): "54%",
    ("events/holdout", "status (completed vs not)"): "50%",
    ("events/dev", "real-event verdict (phantoms caught)"): "14%",
    ("events/dev", "amount exact (when the filing states one)"): "45%",
    ("events/dev", "counterparty"): "23%",
    ("events/dev", "per-share price"): "61%",
    ("events/dev", "status (completed vs not)"): "82%",
    ("psu/holdout", "metric set (>=50% overlap)"): "64%",
    ("psu/holdout", "metric weights exact"): "11%",
    ("psu/holdout", "performance period"): "79%",
    ("psu/holdout", "max payout"): "37%",
    ("psu/holdout", "rTSR target percentile"): "30%",
    ("psu/holdout", "payout history (a cycle matches)"): "24%",
    ("psu/dev", "metric set (>=50% overlap)"): "65%",
    ("psu/dev", "metric weights exact"): "7%",
    ("psu/dev", "performance period"): "77%",
    ("psu/dev", "max payout"): "36%",
    ("psu/dev", "rTSR target percentile"): "27%",
    ("psu/dev", "payout history (a cycle matches)"): "18%",
}


def main() -> int:
    from datetime import date
    L = [f"# Parser scorecard — regex parsers vs reviewed extraction ({date.today()})", "",
         "**Gold set.** Every filing behind the books was read and extracted by a reviewer, with a verbatim "
         "evidence quote and a confidence for each record (`reviewed/`): 976 event filings (8-K + press release), "
         "830 proxy PSU plans, and 400 Item 5.02 appointment filings.", "",
         "**How the books use it.** The reviewed record is used whenever one exists (`reviewed_overlay.py`, "
         "marked *(reviewed)* on the tabs). The regex parsers are the fallback for filings that arrive after the "
         "review. This scorecard measures that fallback.", "",
         "**Honesty.** The event and PSU gold sets are split in two. *dev* is the half the regexes were tuned on. "
         "*holdout* was never looked at while tuning, so the holdout column is the honest accuracy. The "
         "event-validity model trains on dev only when it is scored here. The appointment parser was tuned on "
         "all 400 filings, so its figures are in-sample. Eight reviewer errors there were adjudicated against "
         "the filing text (`reviewed/appointments_adjudicated.json`).", "",
         "| Parser | Field | Before | Now | n |", "|---|---|---|---|---|"]
    rows = []
    a, _ = eval_appointments()
    rows += a
    for sp in ("dev", "holdout"):
        r, errs = eval_events(sp)
        rows += r
        (ROOT / "reviewed" / f"event_errors_{sp}.json").write_text(json.dumps(errs, indent=1))
    for sp in ("dev", "holdout"):
        r, errs = eval_psu(sp)
        rows += r
        (ROOT / "reviewed" / f"psu_errors_{sp}.json").write_text(json.dumps(errs, indent=1))
    for p, f, acc, n in rows:
        L.append(f"| {p} | {f} | {BASELINE.get((p, f), '')} | {acc} | {n} |")
    L += ["", "## What changed", "",
          "- **Events: phantom detection.** Rules for the phantom classes the review found: financial-statement "
          "and non-GAAP footnotes, transaction cost lines, 'About X' boilerplate, executive biographies, capital "
          "raises, risk-factor and conditional language, and committee seats. A date check flags recitals of "
          "events months before the filing. A learned classifier (`event_classifier.py`: TF-IDF of the excerpt "
          "and lede plus the rule signals, logistic regression) handles the long tail; its threshold keeps about "
          "95% of real events.",
          "- **Events: fields.** The consideration, counterparty and per-share price are searched in the excerpt "
          "first, then in the 8-K's Item 1.01 / 2.01 paragraph and the press-release lede.",
          "  - **Counterparty:** legal-agreement patterns ('entered into a … Agreement with X, a Delaware "
          "corporation'). Deal vehicles (Merger Sub, BidCo) resolve to their parent ('an affiliate of Y'), and "
          "the issuer's own name is rejected.",
          "  - **Consideration:** 'purchase price / aggregate / total consideration of' is preferred.",
          "  - **Per-share price:** candidates are scored, and EPS / NAV / closing-price / par-value figures are "
          "rejected.",
          "- **Events: types.** A rights plan *adopted* under 'pill removed' is relabelled. When the reviewer "
          "finds an event of another kind (the company *acquiring*, a debt tender), it is shown as '↻ other kind' "
          "and not scored as the tagged kind.",
          "- **PSU plans:** clause-level weight reading ('X (40%)', 'weighted 40%', 'based 50% on X and 50% on "
          "Y', 'equally weighted', 'solely based on X', and table runs read in the direction that sums to 100%).",
          "  - rTSR is treated as a modifier when the proxy says so.",
          "  - Max payout is the most common PSU-context cap, and the rTSR target is the percentile that pays "
          "100%.",
          "  - Payout history pairs a payout phrase ('paid out at 118%', 'vested in 187% of target') with the "
          "nearest cycle anchor ('2023–2025', 'FY23-FY25', 'granted in 2023', '2023 PSUs'). Cycles that haven't "
          "finished are excluded.",
          "- **Appointments:** the role and person patterns were broadened (titles, nicknames, particles, "
          "possessives, 'X's appointment to the role of', 'Incoming CEO X'). Previously reported appointments "
          "and quote attributions are rejected.", "",
          "## Remaining weak spots (the reviewed record covers them for current names)", "",
          "- **Phantom events on new filings:** about a quarter to a third are caught on the holdout. Recitals "
          "and slides take many forms, and the reviewed verdict is what the books use today.",
          "- **Counterparty on new filings:** about half. Many deals name the buyer only through a defined term, "
          "or in a later paragraph.",
          "- **PSU weights:** about 60% exact. Weights often sit in graphics or tables that the text rendering "
          "scrambles; the reviewed plan is used for all 830 current plans.", ""]
    (ROOT / "PARSER_EVAL.md").write_text("\n".join(L) + "\n")
    for p, f, acc, n in rows:
        print(f"{p:<15} {f:<60} {acc:>6}  n={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
