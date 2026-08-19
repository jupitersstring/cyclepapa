"""Asymmetry-assembly conjunction engine (the PSIX recipe).

The framework is deliberately ADDITIVE -- every layer adds to the
composite, none modifies another. But the PSIX essay defines asymmetry
as something additivity cannot capture: an ASSEMBLED CAUSAL SYSTEM in
which improving unit economics, a survivable-but-levered structure,
underused capacity, low expectations, a recognition catalyst and a
revealed-preference alignment signal REINFORCE one another. "Remove one
critical component and the payoff distribution changes materially."

A name mediocre-on-many additive layers is NOT this. The magic is the
conjunction. So this module is a conjunction detector expressed as ONE
additive layer: it awards points only when a required SPINE of
components co-occurs, and rewards convergence beyond the spine. At the
consensus level it is still one additive layer (additive discipline
preserved); internally it is multiplicative/gated.

Components (each: present? + points + evidence):
  C1 LOW_EXPECTATIONS   cheap  p_b<1, ncav, deep discount           yfinance/10q
  C2 LEVERAGED_SURVIVOR cheap  net debt > equity, tight liquidity   quarterly_10q
  C3 ORPHANED_DRAWDOWN  cheap  >40% off high, low inst / high short yfinance/coval
  C4 REVEALED_INSIDER   cheap  open-market P-buys (the Gagnon tell) discretionary_conviction/f4
  C5 RECOGNITION_CAT    cheap  emergence/relisting/tender/activist  post_ch11/tender/13f
  C6 OPERATING_INFLECT  xbrl   GP up while revenue down; margin +   financials_inflection
  C7 DELEVERAGING       xbrl   interest expense / debt falling      financials_inflection
  C8 UNDERUSED_CAPACITY xbrl   low capex, high opinc/PP&E           financials_inflection
  C9 REVEALED_EVENTS    curated maturity extension / subordination  asymmetry_events

SPINE (all three legs required, else score 0 -- a candidate, not an
assembly):
  1. LOW_EXPECTATIONS (C1)                       -- priced as a residual
  2. an ENGINE: OPERATING_INFLECT (C6) OR LEVERAGED_SURVIVOR (C2)
  3. a COSTLY ACTION: REVEALED_INSIDER (C4) OR a pro curated event (C9)

COUNTER-signals (dilutive refinancing, hidden claim-count inflation,
backstop expiry) subtract and, when severe, disqualify -- this is why
NNBR (closest pattern, but diluted) must not score like May-2024 PSIX.

Outputs:
  asymmetry_assembly.json   {ticker: {score, spine_met, components,...}}
  asymmetry_shortlist.json  names passing the CHEAP spine, for the
                            financials_inflection XBRL enrichment pass.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "asymmetry_assembly.json"
SHORTLIST = ROOT / "asymmetry_shortlist.json"


def _load(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def score_components(tk, yf, q10, disc, f4, coval, p11, tender, t13f,
                     emc, fin, events, preminj=None):
    """Return the component ledger for one ticker."""
    C = {}
    y = yf.get(tk, {}) or {}
    pb = _num(y.get("p_b"))
    price = _num(y.get("price"))
    hi = _num(y.get("fwk_high"))
    inst = _num(y.get("inst_pct"))
    short = _num(y.get("short_pct"))
    q = q10.get(tk, {}) or {}

    # C1 LOW_EXPECTATIONS
    ev = []
    low_exp = False
    if pb is not None and 0 < pb < 0.6:
        low_exp = True; ev.append(f"P/B {pb:.2f} (deep)")
    elif pb is not None and 0 < pb < 1.0:
        low_exp = True; ev.append(f"P/B {pb:.2f}")
    ncav_ps = _num(q.get("ncav_per_share"))
    if ncav_ps and price and ncav_ps > 0 and price < ncav_ps:
        low_exp = True; ev.append("below NCAV")
    # Cheap-on-EARNINGS, not just book. PSIX was ~1.7x annualised
    # earnings at $2.15 but was NOT a low-P/B name -- a residual equity
    # can be priced as a distressed stub while trading above book. Use
    # the operating-earnings yield against enterprise value when the
    # XBRL engine has supplied quarterly operating income.
    fr0 = fin.get(tk, {}) or {}
    opinc_q = _num(fr0.get("opinc"))
    mcap = _num(y.get("mcap"))
    net_debt0 = None
    q0 = q10.get(tk, {}) or {}
    if _num(q0.get("net_cash")) is not None:
        net_debt0 = -_num(q0.get("net_cash"))
    if opinc_q and opinc_q > 0 and mcap:
        ev_val = mcap + (net_debt0 or 0)
        ev_ebit = ev_val / (opinc_q * 4)          # annualise the quarter
        if 0 < ev_ebit < 6:
            low_exp = True; ev.append(f"EV/annualised EBIT {ev_ebit:.1f}x")
    C["C1_low_expectations"] = {"present": low_exp, "evidence": "; ".join(ev)}

    # C2 LEVERAGED_SURVIVOR (torque + fragility)
    ev = []; lev = False
    equity = _num(q.get("equity"))
    ltd = _num(q.get("long_term_debt"))
    net_cash = _num(q.get("net_cash"))
    cr = _num(q.get("current_ratio"))
    mcap = _num(y.get("mcap"))
    if ltd and equity and equity > 0 and ltd > equity:
        lev = True; ev.append(f"LT debt {ltd/1e6:.0f}M > equity {equity/1e6:.0f}M")
    if net_cash is not None and net_cash < 0:
        lev = True; ev.append("net debt position")
    if cr is not None and cr < 1.2:
        lev = True; ev.append(f"current ratio {cr:.2f}")
    C["C2_leveraged_survivor"] = {"present": lev, "evidence": "; ".join(ev)}

    # C3 ORPHANED_DRAWDOWN
    ev = []; orph = False
    dd = None
    if price and hi and hi > 0:
        dd = (1 - price / hi) * 100
    cv = coval.get(tk, {}) or {}
    dd = dd if dd is not None else _num(cv.get("drawdown_pct"))
    if dd and dd > 40:
        orph = True; ev.append(f"{dd:.0f}% off high")
    if inst is not None and inst < 0.35 and (dd or 0) > 30:
        orph = True; ev.append(f"inst {inst*100:.0f}%")
    if short is not None and short > 0.10:
        ev.append(f"short {short*100:.0f}%")
    C["C3_orphaned_drawdown"] = {"present": orph, "evidence": "; ".join(ev)}

    # C4 REVEALED_INSIDER (the Gagnon open-market tell)
    ev = []; ins = False
    dc = disc.get(tk, {}) or {}
    if (dc.get("score") or 0) > 0:
        ins = True
        ev.append(f"conviction {dc.get('score')}: " + "; ".join(dc.get("flags") or [])[:60])
    elif (f4.get(tk, {}) or {}).get("buyer_set"):
        ins = True; ev.append(f"{len(f4[tk]['buyer_set'])} open-market buyer(s)")
    if preminj and (preminj.get(tk, {}) or {}).get("score", 0) > 0:
        ins = True
        pv = preminj[tk]
        ev.append(f"premium injection {pv.get('premium_pct')}% (revealed preference)")
    C["C4_revealed_insider"] = {"present": ins, "evidence": "; ".join(ev)}

    # C5 RECOGNITION_CATALYST
    ev = []; cat = False
    if (p11.get(tk, {}) or {}).get("score", 0) > 0:
        cat = True; ev.append("post-Ch11 emergence")
    if (emc.get(tk, {}) or {}).get("score", 0) > 0:
        cat = True; ev.append("emergence corroborated")
    tr = (tender.get(tk, {}) or {}).get("role")
    if tr in ("SELF_TENDER", "TARGET"):
        cat = True; ev.append(f"tender: {tr}")
    td = t13f.get(tk, {}) or {}
    if td.get("activist_added"):
        cat = True; ev.append("activist 13F add")
    C["C5_recognition_catalyst"] = {"present": cat, "evidence": "; ".join(ev)}

    # C6/C7/C8 -- XBRL inflection engines
    fr = fin.get(tk, {}) or {}
    rev_yoy = _num(fr.get("revenue_yoy"))
    gp_yoy = _num(fr.get("gp_yoy"))
    gm_d = _num(fr.get("gross_margin_delta_pp"))
    inflect = False; ev = []
    if gm_d is not None and gm_d >= 2.0:
        inflect = True; ev.append(f"gross margin +{gm_d:.1f}pp")
    if (gp_yoy is not None and rev_yoy is not None
            and gp_yoy > 0 and rev_yoy < gp_yoy - 0.05):
        inflect = True; ev.append(f"GP {gp_yoy*100:+.0f}% vs rev {rev_yoy*100:+.0f}% (mix shift)")
    C["C6_operating_inflection"] = {"present": inflect, "evidence": "; ".join(ev),
                                    "known": bool(fr)}

    delev = False; ev = []
    ie = _num(fr.get("interest_exp_yoy"))
    dd_q = _num(fr.get("debt_delta_qoq"))
    if ie is not None and ie < -0.05:
        delev = True; ev.append(f"interest exp {ie*100:+.0f}% YoY")
    if dd_q is not None and dd_q < 0:
        delev = True; ev.append("debt down QoQ")
    C["C7_deleveraging"] = {"present": delev, "evidence": "; ".join(ev), "known": bool(fr)}

    cap = False; ev = []
    cr2 = _num(fr.get("capex_to_rev"))
    op_ppe = _num(fr.get("opinc_to_ppe"))
    if cr2 is not None and cr2 < 0.03 and op_ppe is not None and op_ppe > 0.5:
        cap = True; ev.append(f"capex/rev {cr2*100:.1f}%, opinc/PP&E {op_ppe:.1f}x")
    C["C8_underused_capacity"] = {"present": cap, "evidence": "; ".join(ev), "known": bool(fr)}

    # C9 curated revealed-preference events
    pro = []; counter = []
    erec = events.get(tk, {}) or {}
    for e in (erec.get("events") or []):
        (pro if e.get("side") == "pro" else counter).append(e)
    C["C9_revealed_events"] = {"present": bool(pro), "pro": pro, "counter": counter,
                               "worked_example": bool(erec.get("_worked_example"))}
    return C, dd


# ---- weights ---------------------------------------------------------
_POINTS = {
    "C1_low_expectations": 8,
    "C2_leveraged_survivor": 7,
    "C3_orphaned_drawdown": 6,
    "C4_revealed_insider": 10,
    "C5_recognition_catalyst": 8,
    "C6_operating_inflection": 14,   # the rarest, highest-signal engine
    "C7_deleveraging": 10,
    "C8_underused_capacity": 6,
}
_STRENGTH = {"very_strong": 12, "strong": 8, "moderate": 5, "weak": 2}


def assemble(C) -> dict:
    # spine legs
    spine_cheap = (C["C1_low_expectations"]["present"]
                   and C["C2_leveraged_survivor"]["present"]
                   and C["C4_revealed_insider"]["present"])
    engine = (C["C6_operating_inflection"]["present"]
              or C["C2_leveraged_survivor"]["present"])
    costly = (C["C4_revealed_insider"]["present"]
              or bool(C["C9_revealed_events"]["pro"]))
    spine_met = C["C1_low_expectations"]["present"] and engine and costly

    missing = []
    if not C["C1_low_expectations"]["present"]:
        missing.append("low_expectations")
    if not engine:
        missing.append("engine (operating inflection or leverage torque)")
    if not costly:
        missing.append("costly-action alignment signal")

    score = 0.0
    reasons = []
    present = [k for k in _POINTS if C[k]["present"]]
    if spine_met:
        for k in present:
            score += _POINTS[k]
        # convergence bonus: convexity rises with the number of
        # reinforcing engines beyond the minimal spine
        n_present = len(present)
        if n_present >= 6:
            score += 18; reasons.append(f"{n_present}/8 components converge (full assembly)")
        elif n_present >= 5:
            score += 12; reasons.append(f"{n_present}/8 components converge")
        elif n_present >= 4:
            score += 6; reasons.append(f"{n_present}/8 components")
        # revealed-preference pro events
        for e in C["C9_revealed_events"]["pro"]:
            score += _STRENGTH.get(e.get("strength"), 3)
        if C["C9_revealed_events"]["pro"]:
            reasons.append(f"{len(C['C9_revealed_events']['pro'])} costly pro-action(s)")
    # counter-signals subtract regardless of spine
    counters = C["C9_revealed_events"]["counter"]
    for e in counters:
        pen = _STRENGTH.get(e.get("strength"), 3)
        score -= pen
        reasons.append(f"COUNTER: {e.get('type')} (-{pen})")
    # a strong dilution / hidden-claim-count counter disqualifies the
    # 'best skew' claim even when the pattern otherwise fits (the NNBR case)
    severe = any(e.get("type") in ("dilutive_refinancing", "hidden_claim_count_inflation")
                 and e.get("strength") in ("strong", "very_strong") for e in counters)
    if severe:
        score = min(score, 12.0)
        reasons.append("capped: severe dilution counter-signal")

    score = max(0.0, round(score, 1)) if spine_met or counters else 0.0
    if not spine_met:
        score = 0.0
    return {
        "score": score,
        "spine_met": spine_met,
        "missing_spine": missing,
        "present_components": present,
        "n_present": len(present),
        "reasons": reasons,
    }


def main() -> int:
    yf = _load("yfinance_quick.json")
    q10 = _load("quarterly_10q_data.json")
    disc = _load("discretionary_insider_conviction.json")
    f4 = _load("form4_buys.json")
    coval = _load("coval_stafford_proxy.json")
    p11 = _load("post_ch11_emergence.json")
    tender = _load("tender_scan.json")
    t13f = _load("form_13f_delta.json")
    emc = _load("emergence_crossfeed.json")
    fin = _load("financials_inflection.json")
    events = _load("asymmetry_events.json")
    preminj = _load("premium_injection_scan.json")

    universe = set(yf) | set(q10) | set(disc) | set(events)
    universe = {t for t in universe if isinstance(t, str) and not t.startswith("_")}

    out = {}
    for tk in universe:
        C, dd = score_components(tk, yf, q10, disc, f4, coval, p11, tender,
                                 t13f, emc, fin, events, preminj)
        res = assemble(C)
        # keep the ledger for auditability + workbook
        res["components"] = {k: {kk: vv for kk, vv in v.items()
                                 if kk != "pro" and kk != "counter"}
                             for k, v in C.items()}
        res["pro_events"] = C["C9_revealed_events"]["pro"]
        res["counter_events"] = C["C9_revealed_events"]["counter"]
        res["worked_example"] = C["C9_revealed_events"]["worked_example"]
        out[tk] = res

    OUT.write_text(json.dumps(out, indent=2))

    # shortlist for the XBRL enrichment pass: cheap names with a
    # costly-action alignment signal (the PSIX/Gagnon setup) whose
    # operating engine is not yet known. Deliberately does NOT require
    # C2 -- C2 depends on 10-Q coverage (164 names), and the whole point
    # of the XBRL pull is to discover the C6 operating inflection that
    # decides the engine leg. Cheap + insider is the right population to
    # spend the expensive pull on.
    shortlist = sorted(
        tk for tk, r in out.items()
        if r["components"]["C1_low_expectations"]["present"]
        and (r["components"]["C4_revealed_insider"]["present"]
             or r["pro_events"])
        and not r["components"]["C6_operating_inflection"].get("known"))
    SHORTLIST.write_text(json.dumps(shortlist, indent=2))

    scored = {tk: r for tk, r in out.items() if r["score"] > 0}
    print(f"wrote {OUT} ({len(out)} evaluated, {len(scored)} assemblies)")
    print(f"wrote {SHORTLIST} ({len(shortlist)} names need XBRL enrichment)")
    ranked = sorted(scored.items(), key=lambda x: -x[1]["score"])
    print("\n=== TOP ASSEMBLIES ===")
    print(f"{'TKR':<7}{'SCR':>6}{'N':>3}  COMPONENTS")
    for tk, r in ranked[:25]:
        tag = " [worked example]" if r["worked_example"] else ""
        comps = ",".join(c.split("_")[0] for c in r["present_components"])
        print(f"{tk:<7}{r['score']:>6.1f}{r['n_present']:>3}  {comps}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
