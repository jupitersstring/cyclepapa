"""Reviewed extraction first, regex parsers as the fallback.

Every filing currently in the books has a reviewed record (reviewed/*.json:
a reader's structured extraction with a verbatim evidence quote). Those records
override the regex parse field by field and are marked source="reviewed"; a
filing that arrives later, with no reviewed record yet, keeps its regex parse
(source="parsed"), whose accuracy PARSER_EVAL.md publishes.

  events        event_detail.json   verdict / type / what / amount / counterparty /
                                    per-share / status / timing / person
  psu           psu_detail.json     metrics + weights, period, payout range,
                                    rTSR target, modifier, negative-TSR cap, history
  appointments  turnaround_signal.csv  event type, person, role, salary, prior roles

Event verdicts after the overlay:
  REAL          the reviewer confirms an event of the kind the scanner tagged
  RETYPED       a real event, but of another kind (e.g. a rights plan ADOPTED under
                'pill removed', the company ACQUIRING under 'sale of company') --
                shown with the reviewer's type, and not scored as the tagged kind
  NOT AN EVENT  a recital / footnote / boilerplate -- not scored

Run standalone to apply the overlay to the current outputs in place.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
REV = ROOT / "reviewed"

# scanner family -> reviewed event types that ARE that family
FAMILY_MAP = {
    "ASSET_SALE": {"ASSET_SALE"},
    "SALE_OF_COMPANY": {"SALE_OF_COMPANY", "GOING_PRIVATE", "MERGER_OF_EQUALS", "TENDER_OFFER_EQUITY"},
    "GOING_PRIVATE": {"GOING_PRIVATE", "SALE_OF_COMPANY", "TENDER_OFFER_EQUITY"},
    "TENDER_OFFER": {"TENDER_OFFER_EQUITY", "TENDER_OFFER_DEBT", "SALE_OF_COMPANY", "GOING_PRIVATE"},
    "BUYBACK_AUTH": {"BUYBACK_AUTH", "CAPITAL_RETURN_POLICY"},
    "CAPITAL_RETURN": {"SPECIAL_DIVIDEND", "REGULAR_DIVIDEND", "CAPITAL_RETURN_POLICY", "BUYBACK_AUTH"},
    "CAPITAL_RETURN_POLICY": {"CAPITAL_RETURN_POLICY", "BUYBACK_AUTH", "SPECIAL_DIVIDEND", "REGULAR_DIVIDEND"},
    "SPINOFF": {"SPINOFF", "SEPARATION"}, "SEPARATION": {"SEPARATION", "SPINOFF"},
    "STRATEGIC_REVIEW": {"STRATEGIC_REVIEW_STARTED", "STRATEGIC_REVIEW_CONCLUDED"},
    # a value / review committee whose process ended in a sale is the signal playing out
    "VALUE_COMMITTEE": {"VALUE_COMMITTEE", "STRATEGIC_REVIEW_STARTED", "STRATEGIC_REVIEW_CONCLUDED",
                        "SALE_OF_COMPANY", "GOING_PRIVATE"},
    "ACTIVIST_SETTLEMENT": {"ACTIVIST_SETTLEMENT", "BOARD_REFRESH"},
    "CEO_CHANGE": {"CEO_APPOINTED", "INTERIM_CEO", "CEO_DEPARTURE"},
    "BOARD_REFRESH": {"BOARD_REFRESH", "ACTIVIST_SETTLEMENT"},
    "CHAIR_CEO_SPLIT": {"CHAIR_CEO_SPLIT"}, "DECLASSIFY": {"DECLASSIFY"},
    "PILL_REMOVED": {"PILL_REMOVED"}, "CH11_EMERGENCE": {"CH11_EMERGENCE"}, "UPLISTING": {"UPLISTING"},
    "EXCHANGE_OFFER": {"EXCHANGE_OFFER_DEBT"},
}

TYPE_LABEL = {
    "ACQUISITION_BY_COMPANY": "the company is the ACQUIRER", "PILL_ADOPTED": "rights plan ADOPTED",
    "TENDER_OFFER_DEBT": "debt tender (notes, not shares)", "REGULAR_DIVIDEND": "regular dividend",
    "OTHER": "another kind of event",
}

# reviewed PSU metric names -> the parser's names (grade() keys on these)
PSU_NAME = {"rTSR": "relative TSR", "TSR": "absolute TSR", "EPS": "EPS", "Revenue": "revenue", "EBITDA": "EBITDA",
            "Operating income": "operating income / margin", "Free cash flow": "free cash flow",
            "Cash flow": "cash flow", "ROIC": "ROIC", "ROE": "ROE", "ROA": "ROA", "ROCE": "ROCE", "Margin": "margin",
            "FFO": "FFO", "AFFO": "AFFO", "NAV": "NAV", "Book value": "book value / share",
            "Production": "production", "Reserves": "reserves", "Stock price": "stock-price hurdle",
            "Strategic": "strategic / ESG", "ESG": "strategic / ESG", "Other": "other"}

APPT_TYPE = {"NEW_HIRE": "NEW HIRE", "PROMOTION": "PROMOTION", "INTERIM": "NEW HIRE", "DEPARTURE": "DEPARTURE",
             "PAY_CHANGE": "PAY AMENDMENT", "EQUITY_AWARD": "EQUITY AWARD", "INDUCEMENT_PLAN": "INDUCEMENT PLAN",
             "DIRECTOR_ONLY": "DIRECTOR ONLY", "OTHER": "OTHER 5.02"}


def _load(name):
    p = REV / name
    return json.loads(p.read_text()) if p.exists() else []


def _money(x):
    return f"${x / 1e9:.2f}bn" if x >= 1e9 else f"${x / 1e6:.0f}M" if x >= 1e6 else f"${x:,.0f}"


# ------------------------------------------------------------------ events
def apply_events(ev: dict, mcaps: dict | None = None) -> int:
    gold = {g["id"]: g for g in _load("events.json")}
    n = 0
    for tk, lst in ev.items():
        for e in lst:
            g = gold.get(f"{tk}|{e['family']}|{e.get('date')}")
            if not g:
                e.setdefault("source", "parsed")
                continue
            n += 1
            e["source"] = "reviewed"
            e["reviewed_type"] = g.get("event_type")
            for k in ("status", "asset", "counterparty", "amount_usd", "per_share", "premium_pct", "timing",
                      "person", "advisor"):
                if g.get(k) not in (None, "", "UNCLEAR"):
                    e[k] = g[k]
                elif k in ("amount_usd", "per_share", "counterparty") and k in e:
                    e.pop(k)                                   # the reviewer found none: drop the regex guess
            if g.get("evidence"):
                e["evidence"] = g["evidence"]
            mc = (mcaps or {}).get(tk)
            if e.get("amount_usd") and mc:
                e["pct_mcap"] = e["amount_usd"] / mc
            if not g.get("is_event"):
                e["verdict"], e["verdict_reason"] = "NOT AN EVENT", "reviewed: " + (g.get("what") or "")[:160]
                e["what"] = "⚠ not a real event — " + (g.get("what") or "")
            elif g.get("event_type") not in FAMILY_MAP.get(e["family"], {e["family"]}):
                lab = TYPE_LABEL.get(g["event_type"], g["event_type"].replace("_", " ").lower())
                e["verdict"], e["verdict_reason"] = "RETYPED", f"reviewed: {lab}, not {e['family'].replace('_', ' ').lower()}"
                e["what"] = f"↻ {lab}: " + (g.get("what") or "")
            else:
                e["verdict"], e["verdict_reason"] = "REAL", ""
                st = f"[{g['status'].lower()}] " if g.get("status") in ("ANNOUNCED", "PENDING", "COMPLETED", "TERMINATED") else ""
                e["what"] = st + (g.get("what") or e.get("what") or "")
    return n


# ------------------------------------------------------------------ PSU
def apply_psu(psu: dict) -> int:
    gold = {g["ticker"]: g for g in _load("psu.json")}
    n = 0
    for tk, r in psu.items():
        g = gold.get(tk)
        if not g or not g.get("has_psu") or not g.get("metrics"):
            r.setdefault("source", "parsed")
            continue
        n += 1
        r["source"] = "reviewed"
        mets = {}
        for k, v in g["metrics"].items():
            nm = PSU_NAME.get(k, str(k).lower())
            mets[nm] = (mets.get(nm) or 0) + v if v is not None else mets.get(nm)
        r["metrics"] = mets
        r["weights_verified"] = all(v is not None for v in mets.values())
        r.pop("metrics_partial", None)
        r.pop("other_metrics", None)
        for gk, rk in (("period_years", "period_years"), ("payout_min", "payout_min"), ("payout_max", "payout_max"),
                       ("rtsr_target_percentile", "rtsr_target_pct")):
            if g.get(gk) is not None:
                r[rk] = g[gk]
            else:
                r.pop(rk, None)
        if g.get("modifier"):
            r["modifier"] = g["modifier"]
        r["negative_tsr_cap"] = bool(g.get("negative_tsr_cap"))
        hist = [(str(k), float(v)) for k, v in (g.get("history") or {}).items() if v is not None]
        if hist:
            r["history"] = hist[:6]
        else:
            r.pop("history", None)
        if g.get("evidence"):
            r["design_excerpt"] = g["evidence"]
    return n


# ------------------------------------------------------------------ appointments
def appointment(tk: str, acc: str):
    if not hasattr(appointment, "_g"):
        g = {x["id"]: dict(x) for x in _load("appointments.json")}
        for a in _load("appointments_adjudicated.json"):
            if a["id"] in g:
                g[a["id"]][a["field"]] = a["to"]
                g[a["id"]]["person"] = g[a["id"]].get("person") or a.get("person")
                g[a["id"]]["role"] = g[a["id"]].get("role") or a.get("role")
        appointment._g = g
    return appointment._g.get(f"{tk}|{acc}")


def apply_appointment(row: dict) -> bool:
    g = appointment(row.get("ticker", ""), row.get("accession", ""))
    if not g:
        row.setdefault("source", "parsed")
        return False
    row["source"] = "reviewed"
    row["event_type"] = APPT_TYPE.get(g.get("event_type"), g.get("event_type") or "")
    row["interim"] = "yes" if g.get("event_type") == "INTERIM" or "interim" in str(g.get("role") or "").lower() else ""
    for k in ("person", "role"):
        row[k] = g.get(k) or ""
    # the reviewer's blanks win too: a salary / grant the reviewer did not find is not shown
    row["base_salary_usd"] = g.get("base_salary_usd") or ""
    if g.get("inducement_or_signon_usd"):
        row["grant_value_usd"] = g["inducement_or_signon_usd"]
    else:
        try:
            if float(row.get("grant_value_usd") or 0) < 50_000:
                row["grant_value_usd"] = ""
        except ValueError:
            row["grant_value_usd"] = ""
    if g.get("prior_roles"):
        row["background"] = g["prior_roles"]
    if g.get("departing_person"):
        row["departure"] = g["departing_person"]
    if g.get("evidence"):
        row["excerpt"] = g["evidence"]
    return True


def apply_turnaround_csv(path=ROOT / "turnaround_signal.csv") -> int:
    if not path.exists():
        return 0
    rows = list(csv.DictReader(path.open()))
    if not rows:
        return 0
    n = 0
    for r in rows:
        was_hire = r.get("event_type") in ("NEW HIRE", "PROMOTION", "")
        if apply_appointment(r):
            n += 1
            now_hire = r["event_type"] in ("NEW HIRE", "PROMOTION")
            try:
                s = float(r.get("score") or 0)
                if was_hire and not now_hire:
                    r["score"] = round(s * 0.3, 1)          # not a hire: ranked well below hires
                elif now_hire and not was_hire:
                    r["score"] = round(s / 0.3, 1)
            except ValueError:
                pass
    fields = list(rows[0].keys())
    if "source" not in fields:
        fields.append("source")
    rows.sort(key=lambda r: -float(r.get("score") or 0))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return n


def main() -> int:
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    mc = {k: (v or {}).get("mcap") for k, v in yq.items()}
    p = ROOT / "event_detail.json"
    if p.exists():
        ev = json.loads(p.read_text())
        n = apply_events(ev, mc)
        p.write_text(json.dumps(ev, indent=1))
        from collections import Counter
        c = Counter(e.get("verdict") for l in ev.values() for e in l if e.get("excerpt"))
        print(f"events: {n} reviewed records applied; verdicts {dict(c)}")
    p = ROOT / "psu_detail.json"
    if p.exists():
        psu = json.loads(p.read_text())
        n = apply_psu(psu)
        import psu_detail as pdl
        proxy = pdl.latest_proxy()
        for tk, r in psu.items():
            if r.get("source") == "reviewed":
                g, pts, why = pdl.grade(r, proxy.get(tk), (yq.get(tk) or {}).get("price"))
                r.update({"grade": g, "grade_pts": pts, "why": why, "summary": pdl.summary_line(r, proxy.get(tk))})
        p.write_text(json.dumps(psu, indent=1))
        print(f"psu: {n} reviewed plans applied")
    n = apply_turnaround_csv()
    print(f"turnaround: {n} reviewed appointments applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
