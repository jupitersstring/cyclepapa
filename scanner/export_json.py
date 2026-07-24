"""Export the full scan as JSON for the HTML instrument-panel dashboard."""

from __future__ import annotations

import json
import sys

from . import app as _app
from . import tearsheet as TS
from . import anomalies as AN
from . import kalecki_levy as KL
from . import strategic_analysis as SA


def _balances(iso: str) -> dict:
    """The three sectoral balances that sum to zero, %GDP (live-preferred).

    Identity: private + government + foreign = 0, where foreign net lending
    to the domestic economy = -(current account). So:
        government = fiscal balance      (neg = deficit)
        foreign    = -current_account
        private    = current_account - fiscal   (the residual)
    """
    vals = SA._inputs(iso)
    if vals is None:
        return {}
    fiscal, ca = vals
    return {"private": round(ca - fiscal, 1),
            "government": round(fiscal, 1),
            "foreign": round(-ca, 1)}


def build() -> dict:
    s = _app.build_scored()
    comps = KL.components_df()
    countries = []
    for iso in s.index:
        r = s.loc[iso]
        c = comps.loc[iso] if iso in comps.index else None
        ts = TS.tearsheet(iso)
        countries.append({
            "iso": iso,
            "country": r["country"],
            "archetype": r["archetype"],
            "etf": (r.get("etf") if isinstance(r.get("etf"), str) else None),
            "regime": r["regime"],
            "opportunity": round(float(r["opportunity"]), 3),
            "clock": round(float(r.get("stage_position") or 0), 0),
            "fine_stage": r.get("fine_stage"),
            "tobin_q": round(float(r.get("tobin_q") or 0), 2),
            "profit_fuel": round(float(r["profit_fuel"]), 2),
            "credit": round(float(r["credit_impulse"]), 2),
            "carry": round(float(r["carry_cushion"]), 2),
            "crowding": round(float(r["crowding"]), 2),
            "fragility": round(float(r.get("minsky_fragility") or 0), 2),
            "minsky_regime": r.get("minsky_regime"),
            "data_confidence": r.get("data_confidence"),
            "verdict": ts["verdict"].split(")", 1)[-1].strip(" ").split("!!")[0].strip(),
            "hazards": [h.split(" -- ")[0] for h in ts["hazards"]],
            "hazards_full": ts["hazards"],
            "kl": {k: round(float(c[k]), 2) for k in (
                "investment", "govt_deficit", "net_exports",
                "dividends", "household_saving")} if c is not None else {},
            "balances": _balances(iso),
            "note": r.get("note", ""),
        })
    return {
        "headline": TS.system_headline(),
        "breadth": AN.private_surplus_breadth(),
        "regime_counts": {k: int(v) for k, v in s["regime"].value_counts().items()},
        "countries": countries,
        "archetypes": {
            "A": "Reserve absorber", "B": "Anglo-mimic deficit",
            "C": "Mercantilist saver", "D": "Entrepot / MNC-distorted",
            "E": "EMU constraint trap", "F": "Directed-credit",
            "G": "Commodity rent", "H": "Convergence importer",
            "I": "Frontier dollar-dependent", "X": "Sanctioned / closed",
        },
    }


if __name__ == "__main__":
    out = build()
    path = sys.argv[1] if len(sys.argv) > 1 else "scanner/scan_data.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {path}: {len(out['countries'])} countries")
