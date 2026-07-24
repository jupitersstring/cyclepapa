"""
Presentation layer -- Design-of-Everyday-Things redesign.

Don Norman's critique applied to the scanner's output: the raw tables are an
engineer's interface -- every internal exposed, nothing prioritised, all the
knowledge required 'in the head'. This module is the translation layer that
closes the GULF OF EVALUATION: it converts z-scores and module outputs into
plain-language verdicts, gauges, and hazard lights, ordered by the inverted
pyramid (system headline first, detail on demand).

Three exports:
    system_headline()   -- the one-sentence state of the world
    verdict(iso)        -- one plain-language line per country
    tearsheet(iso)      -- the full instrument panel (dict, renderer-agnostic)
"""

from __future__ import annotations

import pandas as pd

from . import app as _app
from . import minsky_fragility as MF
from . import kohler_cycle as KC
from . import distribution as DIST
from . import anomalies as AN
from . import seven_processes as SP
from . import kalecki_levy as KL


# --- plain-language translators (gulf-of-evaluation closers) ---------------

def _phrase_valuation(q: float | None) -> str:
    if q is None:
        return "valuation unknown"
    if q < 0.6:
        return f"deep value (q {q:.2f})"
    if q < 0.85:
        return f"cheap (q {q:.2f})"
    if q <= 1.15:
        return f"fairly priced (q {q:.2f})"
    if q <= 1.35:
        return f"expensive (q {q:.2f})"
    return f"priced for perfection (q {q:.2f})"


def _phrase_fuel(pf: float) -> str:
    if pf > 2.0:
        return "profit fuel surging"
    if pf > 0.5:
        return "profit fuel rising"
    if pf > -0.5:
        return "profit fuel flat"
    return "profit engine draining"


def _phrase_financing(regime: str, frag: float) -> str:
    return {"hedge": "income-financed (robust)",
            "speculative": "rollover-dependent",
            "ponzi": f"appreciation-financed (fragility {frag:.2f})"}.get(regime, "")


def _phrase_crowding(c: float) -> str:
    if c > 1.2:
        return "crowded consensus"
    if c < -0.8:
        return "under-owned"
    return ""


def hazards(iso: str, scored_row: pd.Series) -> list[str]:
    """The warning lights: every active hazard, plain language."""
    out = []
    if scored_row.get("minsky_regime") == "ponzi":
        out.append("PONZI FINANCING -- asset values validated by appreciation, not income")
    phase = KC.phase_of(iso)
    if phase == "late_boom":
        out.append("CARRY LATE-BOOM -- inflow phase has built the fragility it will detonate")
    elif phase == "reversal":
        out.append("CARRY REVERSAL -- inflows stalling into built FX mismatch")
    d = DIST.evaluate(iso)
    if d and d["mask_flag"]:
        out.append(f"TOP-HEAVY SAVING -- bottom-80% in deficit ({d['bottom80_balance']:+.1f}%GDP) behind a safe aggregate")
    from .lineage import INFLATION, martin_inflation_tax
    tax = martin_inflation_tax(iso)
    if tax is not None and tax > 8.0:
        out.append(f"INFLATION ILLUSION -- measured saving overstated by ~{tax:.0f}%GDP")
    if scored_row.get("data_confidence") == "low":
        out.append("LOW DATA CONFIDENCE -- treat every reading as provisional")
    if scored_row.get("nbfi_leverage", 0) >= 2.5:
        out.append("NBFI CONCENTRATION -- aggregate balances hide sub-sector leverage")
    return out


def verdict(iso: str, scored: pd.DataFrame | None = None) -> str:
    """One line, plain language: what would you tell a colleague in 10 seconds."""
    s = scored if scored is not None else _app.build_scored()
    if iso not in s.index:
        return f"{iso}: not in panel"
    r = s.loc[iso]
    bits = [_phrase_valuation(r.get("tobin_q")),
            _phrase_fuel(float(r.get("profit_fuel", 0.0))),
            f"{r.get('fine_stage','?').replace('_',' ')} (clock {r.get('stage_position',0):.0f}/100)",
            _phrase_financing(r.get("minsky_regime", ""), float(r.get("minsky_fragility") or 0))]
    crowd = _phrase_crowding(float(r.get("crowding", 0.0)))
    if crowd:
        bits.append(crowd)
    hz = hazards(iso, r)
    tail = ("  !! " + "; ".join(h.split(" -- ")[0] for h in hz)) if hz else ""
    return (f"{r['country'].upper():14s} {r['regime'].upper():7s} "
            f"({r['opportunity']:+.2f})  " + " | ".join(b for b in bits if b) + tail)


def system_headline() -> str:
    """The inverted-pyramid lead: one sentence for the whole panel."""
    b = AN.private_surplus_breadth()
    s = _app.build_scored()
    bulls = (s.regime == "bull").sum()
    bears = (s.regime == "bear").sum()
    return (f"{b['of_which_private_surplus']} of {b['deficit_archetype_countries']} "
            f"deficit-archetype economies now run PRIVATE SURPLUSES -- the paradox-of-"
            f"thrift configuration. No country needs implausible borrowing (the 2007 "
            f"signature is absent); the constraint is the savers' surplus. "
            f"{bulls} bulls (cheap, hedge-financed, early-cycle) vs {bears} bears "
            f"(expensive, appreciation-financed, late-cycle).")


def gauge(value: float, lo: float, hi: float, width: int = 10) -> str:
    """ASCII gauge with the scale IN the display (knowledge in the world)."""
    frac = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = round(frac * width)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {value:+.2f}"


def tearsheet(iso: str) -> dict:
    """Full instrument panel for one country, renderer-agnostic."""
    s = _app.build_scored()
    r = s.loc[iso]
    comps = KL.components_df().loc[iso]
    return {
        "country": r["country"], "iso": iso, "archetype": r["archetype"],
        "etf": r.get("etf"),
        "verdict": verdict(iso, s),
        "regime": r["regime"], "opportunity": float(r["opportunity"]),
        "clock": {"position": float(r.get("stage_position") or 0),
                  "fine_stage": r.get("fine_stage")},
        "gauges": {
            "profit_fuel": gauge(float(r["profit_fuel"]), -3, 3),
            "credit": gauge(float(r["credit_impulse"]), -3, 3),
            "valuation_q": gauge(float(r.get("tobin_q") or 1.0), 0.3, 1.7),
            "carry": gauge(float(r["carry_cushion"]), -3, 3),
            "crowding": gauge(float(r["crowding"]), -3, 3),
            "fragility": gauge(float(r.get("minsky_fragility") or 0), 0, 1),
        },
        "kalecki_levy": {k: float(comps[k]) for k in
                         ("investment", "govt_deficit", "net_exports",
                          "dividends", "household_saving")},
        "hazards": hazards(iso, r),
        "data_confidence": r.get("data_confidence"),
        "estimated": bool(r.get("estimated", True)),
        "note": r.get("note", ""),
    }
