"""Consolidated Godley report -- all corrections from the deep-reading audit applied."""

from __future__ import annotations

import textwrap

import pandas as pd

from . import configuration as CF
from . import inflation_accounting as IA
from . import minsky_fragility as MF
from . import assembly as AS
from . import lineage as LN
from . import strategic_analysis as SA
from .sources import sectors as SEC
from .archetypes import lookup


def _h(t, ch="="):
    print("\n" + ch * 78)
    print("  " + t)
    print(ch * 78)


def _w(t, indent="  "):
    print(textwrap.fill(t, 76, initial_indent=indent, subsequent_indent=indent))


def run() -> None:
    pd.set_option("display.width", 200)

    _h("THE GODLEY REPORT")
    _w("Sectoral-balance analysis after Wynne Godley and the Levy school, with "
       "the corrections from a deep reading of the primary texts: inflation "
       "accounting restored, the private balance disaggregated, Minsky measured "
       "on financing structure rather than valuation, and the world identity "
       "used as Godley used it -- as a redundant-equation diagnostic.")

    # ---------------------------------------------------------------- 1
    _h("1 · CONFIGURATIONS -- the constellation, not a ranking", "-")
    p = CF.panel()
    for cfg in CF.CONFIG_ORDER:
        m = p[p.configuration == cfg]
        if not len(m):
            continue
        print(f"\n  {cfg.upper().replace('-', ' ')} ({len(m)})")
        _w(CF.CONFIG_BLURB.get(cfg, ""), "     ")
        _w(", ".join(sorted(m.country)), "     · ")

    # ---------------------------------------------------------------- 2
    _h("2 · THE PRIVATE BALANCE DISAGGREGATED", "-")
    _w("Godley & Lavoie (2007, p.25) repudiated the single-private-sector "
       "aggregation -- 'households and production firms take entirely different "
       "decisions'. The same surplus is a different economy depending on who "
       "holds it.")
    rows = []
    for g in sorted(SEC.load()):
        d = CF.disaggregate(g)
        if d:
            rows.append(d)
    if rows:
        t = pd.DataFrame(rows).set_index("iso")
        print()
        print(t[["year", "households", "households_gap", "corporates",
                 "corporates_gap", "driver", "sub_configuration"]].to_string())
        print("\n  Mechanisms that the aggregate hides:")
        for r in rows:
            if r["sub_configuration"] in ("corporate-saving-glut",
                                          "household-deficit",
                                          "household-deficit-improving"):
                _w(f"{lookup(r['iso']).name}: {r['sub_note']}", "     · ")

    # ---------------------------------------------------------------- 3
    _h("3 · INFLATION ACCOUNTING -- the correction Godley insisted on", "-")
    _w("Under inflation part of a nominal deficit is not new demand but the flow "
       "required to hold real debt constant (Godley & Cripps 1983:245). The "
       "adjustment is symmetric and sums to zero, so the identity survives.")
    it = IA.panel()
    if len(it):
        print()
        print(it[["year", "pi", "debt", "gov_nom", "gov_adj", "priv_nom",
                  "priv_adj", "gain", "sign_flip"]].head(14).to_string())
        flips = list(it[it.sign_flip].index)
        print()
        _w(f"Sign flips -- nominal deficit is a REAL SURPLUS: "
           f"{', '.join(lookup(i).name for i in flips if lookup(i))}")

    # ---------------------------------------------------------------- 4
    _h("4 · FINANCING STRUCTURE -- Minsky measured, not asserted", "-")
    _w("Ponzi is a financing-structure claim (debt service exceeding cash flow), "
       "not a valuation claim. Measured from BIS private credit against its own "
       "5-year peak.")
    print()
    print(f"  {'':4} {'debt vs peak':>13} {'fragility':>10} {'regime':>13}"
          f" {'a':>2} {'assembly':>9}")
    for iso in ["CN", "HK", "KR", "BR", "US", "AU", "CA", "GB", "DE", "JP"]:
        inp = MF._INPUTS.get(iso)
        if not inp:
            continue
        dd = MF.debt_dynamics(iso)
        a = AS.assembly_index(iso)["assembly_index"]
        print(f"  {iso:4} {(f'{dd:+.1f}pp' if dd is not None else 'n/a'):>13}"
              f" {MF.fragility_index(iso):10.2f} {MF.regime_label(iso):>13}"
              f" {a:2} {AS.assembly_fragility(iso):9.3f}")
    print()
    _w("The Anglo bloc has DELEVERAGED 15-27pp from peak and is hedge-financed, "
       "matching Levy's Oct-2025 statement that 'we are not witnessing an "
       "increase in the net liabilities of the non-financial corporate sector'. "
       "China stays Ponzi -- stalled at peak leverage.")

    # ---------------------------------------------------------------- 5
    _h("5 · SYSTEMIC LOAD -- assembly index x copy number", "-")
    a = AS.assembly()
    print()
    for cfg, v in sorted(a["by_configuration"].items(),
                         key=lambda kv: -kv[1]["contribution"]):
        print(f"  {cfg:22} n={v['copy_number']:2}  a={v['mean_assembly_index']:.2f}"
              f"  contribution={v['contribution']:.3f}")
    print()
    _w(a["reading"])

    # ---------------------------------------------------------------- 6
    _h("6 · WORLD CONSISTENCY -- the redundant-equation check", "-")
    w = LN.world_ca_check()
    print()
    print(f"  implied world balance   ${w['implied_world_balance_usd_bn']:,.0f}bn")
    print(f"  measured discrepancy    ${w['world_discrepancy_benchmark_usd_bn']:,.0f}bn")
    print(f"  residual                ${w['residual_vs_benchmark_usd_bn']:,.0f}bn")
    print()
    _w(w["verdict"])
    _w(w["counterparty"] + " -- surpluses cannot be achieved everywhere at once.")

    # ---------------------------------------------------------------- 7
    _h("7 · FLOW-vs-STOCK RECONCILIATION -- no black holes", "-")
    _w("The external stock must equal cumulated flows plus revaluations. The gap "
       "isolates the revaluation channel the transactions account excludes -- and "
       "shows where a flow-only projection misleads.")
    pt = AS.pathway_panel()
    if len(pt):
        print()
        print(pt.head(6).to_string())
        print("  ...")
        print(pt.tail(4).to_string())
        print()
        _w("CAVEAT: the gap is revaluation plus a denominator effect (summing "
           "flows as %-of-each-year's-GDP against a current-year stock "
           "over-weights early flows where nominal GDP grew). Indicative of "
           "where revaluation matters, not a measured valuation loss.")

    # ---------------------------------------------------------------- 8
    _h("8 · WHAT MUST GIVE", "-")
    for iso in ["DE", "JP", "US", "GB", "CN", "KR"]:
        s = CF.what_must_give(iso)
        if s:
            print()
            _w(s, "  ")

    _h("COMPATIBILITY AUDIT")
    for k, v in AS.compatibility_audit().items():
        print(f"  {k.replace('_', ' ')}: {v['status']}")

    print("\n" + "=" * 78)
    _w("Balances from IMF actuals and Eurostat sector accounts; credit from BIS; "
       "conditional, not predictive -- it states what must happen if the "
       "configuration persists, not when.")
    print()


if __name__ == "__main__":
    run()
