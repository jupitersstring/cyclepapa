"""Export the per-country Godley analysis for the country-view page."""

from __future__ import annotations

import json
import sys

from . import configuration as CF
from . import godley_projection as GP
from . import strategic_analysis as SA
from . import kalecki_levy as KL
from . import app as _app
from .archetypes import COUNTRIES, ARCHETYPES


def build() -> dict:
    scored = _app.build_scored()
    out = {"countries": {}, "config_order": CF.CONFIG_ORDER,
           "config_blurb": CF.CONFIG_BLURB}
    comps = KL.components_df()
    for c in COUNTRIES:
        cfg = CF.configure(c.iso)
        path = CF.balance_path(c.iso)
        if cfg is None or path is None:
            continue
        rec = {
            "country": c.name, "archetype": c.primary,
            "archetype_name": ARCHETYPES[c.primary].name,
            "configuration": cfg["configuration"],
            "mechanism": cfg["mechanism"],
            "asof": cfg["asof"],
            "stance": cfg["stance"],
            "balances": {k: cfg[k] for k in ("private", "government", "foreign")},
            "norms": {"private": cfg["private_norm"], "government": cfg["government_norm"]},
            "gaps": {"private": cfg["private_gap"], "government": cfg["government_gap"]},
            "must_give": CF.what_must_give(c.iso),
            "path": {"years": [int(y) for y in path.index],
                     "private": [float(v) for v in path["private"]],
                     "government": [float(v) for v in path["government"]],
                     "foreign": [float(v) for v in path["foreign"]]},
        }
        # Godley medium-term projection (his 1999 Appendix-2 method)
        traj = GP.project(c.iso)
        if traj is not None and not traj.empty:
            rec["projection"] = {
                "start_niip": float(traj.attrs.get("niip_start", 0)),
                "year": [int(y) for y in traj["year"]],
                "niip": [round(float(v), 1) for v in traj["NIIP"]],
                "ca": [round(float(v), 1) for v in traj["CA"]],
                "nl_priv": [round(float(v), 1) for v in traj["NL_priv"]],
                "unsustainability": round(float(GP.unsustainability_score(c.iso)), 2),
            }
        # Strategic-Analysis scenario grid
        sc = SA.scenarios(c.iso)
        if sc is not None and not sc.empty:
            rec["scenarios"] = [
                {"scenario": r["scenario"], "govt": float(r["govt_balance"]),
                 "required_private": float(r["required_private_balance"]),
                 "implausible": bool(r["implausible"]), "direction": r["direction"]}
                for _, r in sc.iterrows()]
        # Kalecki-Levy profit sources
        if c.iso in comps.index:
            k = comps.loc[c.iso]
            rec["kalecki"] = {f: round(float(k[f]), 2) for f in
                              ("investment", "govt_deficit", "net_exports",
                               "dividends", "household_saving")}
        if c.iso in scored.index:
            rec["fine_stage"] = scored.loc[c.iso, "fine_stage"]
            rec["clock"] = int(scored.loc[c.iso, "stage_position"] or 0)
            rec["minsky"] = scored.loc[c.iso, "minsky_regime"]
        out["countries"][c.iso] = rec
    return out


if __name__ == "__main__":
    d = build()
    path = sys.argv[1] if len(sys.argv) > 1 else "scanner/country_data.json"
    with open(path, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    print(f"wrote {path}: {len(d['countries'])} countries")
