#!/usr/bin/env python3
"""Mutation test for methodology_audit.py — proves each check is LOAD-BEARING.

For every check we inject the exact violation it is supposed to catch into a
copy of the data, run the owning measure function, and assert the check flips
to FAIL. A check that stays PASS after its own violation is planted is a
false-green (not load-bearing) — the harness reports it as LEAK.

Also runs a NEGATIVE control: with the REAL (unmutated) data every targeted
check must be PASS, so we know the mutation — not a pre-existing failure —
caused the flip.
"""
import sys
import numpy as np
import pandas as pd
import importlib

MA = importlib.import_module("methodology_audit")

T = pd.read_csv("archetype_tags.csv", low_memory=False)
G = pd.read_csv("asymmetry_global.csv", low_memory=False).drop_duplicates("symbol")


def run(fn, t, g):
    """Run one measure fn on (t,g); return {check_name: status}."""
    MA.RESULTS.clear()
    try:
        fn(t, g)
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}
    return {name: status for (status, name, _detail) in MA.RESULTS}


def add_row(df, **over):
    """Append one row: all columns NaN except overrides."""
    row = {c: np.nan for c in df.columns}
    for k, v in over.items():
        if k in df.columns:
            row[k] = v
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


CASES = []  # (label, needle, fn, mutate) ; mutate(t,g)->(t,g)


def case(label, needle, fn):
    def deco(mut):
        CASES.append((label, needle, fn, mut))
        return mut
    return deco


# ---- zero-tolerance integrity gates: single planted row must trip them ----
@case("fcf_yield>1", "impossible FCF yields", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT1", fcf_yield=5.0)

@case("roce>1.5", "absurd ROCE", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT2", roce=2.0)

@case("ev_ebitda sign", "positive EV/EBITDA on negative EBITDA", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT3", ev_ebitda=5.0, ebitda_ttm=-10.0)

@case("gross_margin>1", "impossible margins", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT4", gross_margin=1.5)

@case("p_e<0.5", "impossible P/E", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT5", p_e=0.1)

@case("pb<0.05", "corrupt P/B", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT6", pb=0.01)

@case("mcap<=0", "zero/negative market cap", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT7", market_cap_usd=-1.0, price=1.0)

@case("dividend>0.40", "absurd dividend yields", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT8", dividend_yield=0.55)

@case("52w flag clash", "52w flags agree", MA._integrity)
def _m(t, g): return t, add_row(g, symbol="MUT9", high_52w_abs=1, pct_off_52w_high=-0.5)

@case("financials in neg_ev", "arch_negative_ev_value excludes Financials", MA._integrity)
def _m(t, g):
    t2 = add_row(t, symbol="MUTF", arch_negative_ev_value=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTF", sector="Financials")
    return t2, g2

@case("clinical biotech in fund arch", "no clinical biotech in fundamental", MA._integrity)
def _m(t, g):
    return add_row(t, symbol="MUTB", is_clinical_biotech=1,
                   arch_lindy_fcf=1, archetype_count=1), g

@case("micro-shell firing", "sub-$2M micro-shells", MA._integrity)
def _m(t, g):
    t2 = add_row(t, symbol="MUTS", archetype_count=1)
    g2 = add_row(g, symbol="MUTS", market_cap_usd=1.0e6)
    return t2, g2

@case("preferred firing", "preferred/warrant/unit lines", MA._integrity)
def _m(t, g):
    return add_row(t, symbol="ZZ-P", archetype_count=1), g

# ---- gating / ranges / density / high52 ----
@case("gating leak", "analyst_awakening_score is 0 outside", MA._gating)
def _m(t, g):
    return add_row(t, symbol="MUTG", arch_analyst_awakening=0,
                   analyst_awakening_score=0.5, archetype_count=0), g

@case("range violation", "range: quality_score", MA._ranges)
def _m(t, g):
    return add_row(t, symbol="MUTR", quality_score=2.0), g

@case("density>1", "archetype_count_pct <= 1", MA._density)
def _m(t, g):
    return t, add_row(g, symbol="MUTD", archetype_count_pct=1.5)

@case("52w both!=abs&rel", "both == abs AND rel", MA._high52)
def _m(t, g):
    return add_row(t, symbol="MUTH", high_52w_both=1, high_52w_abs=0, high_52w_rel=0), g

@case("units dividend scale", "dividend_yield is a fraction", MA._units)
def _m(t, g):
    g2 = g.copy(); g2["dividend_yield"] = 50.0
    return t, g2

# ---- tolerance-based archetype checks: corrupt ALL firers to prove failable ----
@case("tenbagger 10x", "implied 10x closes", MA._tenbagger)
def _m(t, g):
    t2 = t.copy()
    m = t2.get("arch_tenbagger_path", pd.Series(0, index=t2.index)) == 1
    t2.loc[m, "tenbagger_implied_return"] = 5.0
    return t2, g

@case("lynch already paid", "no firer already paid", MA._lynch)
def _m(t, g):
    # _lynch reads roc_12m from t (the firer frame f=t[...]); mutate t.
    t2 = t.copy()
    if "roc_12m" not in t2.columns:
        t2["roc_12m"] = np.nan
    t2.loc[t2.get("arch_lynch_reward", 0) == 1, "roc_12m"] = 0.9
    return t2, g

@case("derate expanding", "median firer gap is compressive", MA._derate)
def _m(t, g):
    t2 = t.copy()
    m = t2.get("arch_evsales_derating", 0) == 1
    t2.loc[m, "evsales_derate_gap"] = -0.5
    return t2, g

@case("coverage neg EBITDA", "every firer has positive EBITDA", MA._coverage)
def _m(t, g):
    fire = set(t.loc[t.get("arch_strong_coverage", 0) == 1, "symbol"])
    g2 = g.copy()
    g2.loc[g2["symbol"].isin(fire), "ebitda_ttm"] = -1.0e6
    return t, g2

@case("fastseg single-seg", "every firer is multi-segment", MA._fastseg)
def _m(t, g):
    # segment_count is persisted in t; mutate it there.
    t2 = t.copy()
    if "segment_count" not in t2.columns:
        t2["segment_count"] = 2.0
    t2.loc[t2.get("arch_fastest_segment", 0) == 1, "segment_count"] = 1
    return t2, g

@case("beaten-down contradicted", "no contradicted 'beaten down'", MA._beaten)
def _m(t, g):
    fire = set(t.loc[t.get("arch_dead_option", 0) == 1, "symbol"])
    g2 = g.copy()
    g2.loc[g2["symbol"].isin(fire), "pct_off_52w_high"] = 0.0
    return t, g2

# ---- regression guards (this session's fixes as invariants) ----
@case("R3 net-cash levered stub", "arch_weschler_levered_equity carries no net-cash", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTX", arch_weschler_levered_equity=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTX", net_cash_pct_mcap=0.5)
    return t2, g2

@case("R6 sub-scale revenue", "arch_tenbagger_path keeps a >=$5M", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTY", arch_tenbagger_path=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTY", revenue_ttm_usd=1.0e6)
    return t2, g2

@case("R5 declining-rev inflection", "arch_roic_inflect not firing on declining", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTZ", arch_roic_inflect=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTZ", rev_yoy=-0.2)
    return t2, g2

@case("rerating not-at-high", "arch_analyst_rerating_confirmed every firer at a 52w high", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTW", arch_analyst_rerating_confirmed=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTW", high_52w_abs=0, high_52w_rel=0)
    return t2, g2

@case("R1 financials in quality", "arch_durable_reinvestment excludes Financials", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTV", arch_durable_reinvestment=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTV", sector="Financials")
    return t2, g2

@case("tail financials in qarp", "arch_qarp excludes Financials", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTQ", arch_qarp=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTQ", sector="Financials")
    return t2, g2

@case("tail melter in inflection", "arch_micro_activist_inflect carries no deep operating loss-maker", MA._regression)
def _m(t, g):
    t2 = add_row(t, symbol="MUTN", arch_micro_activist_inflect=1, archetype_count=1)
    g2 = add_row(g, symbol="MUTN", roce=-0.5)
    return t2, g2

@case("price-ghost fires archetype", "price-ghost duplicates fire no archetypes", MA._regression)
def _m(t, g):
    return add_row(t, symbol="MUTGH", is_price_ghost=1, archetype_count=1), g


def main():
    # negative control: real data — every targeted check must currently PASS
    print("=" * 78)
    print("NEGATIVE CONTROL (real data): targeted checks should all be PASS")
    print("=" * 78)
    baseline = {}
    for fn in {c[2] for c in CASES}:
        baseline.update(run(fn, T.copy(), G.copy()))
    ctrl_bad = []
    for label, needle, fn, _mut in CASES:
        hits = [k for k in baseline if needle in k]
        st = baseline.get(hits[0]) if hits else "MISSING"
        if st != "PASS":
            ctrl_bad.append((label, needle, st, hits))
    if ctrl_bad:
        for label, needle, st, hits in ctrl_bad:
            print(f"  CONTROL-ISSUE  {label:28s} -> {st}  ({hits or 'no check named '+needle!r})")
    else:
        print("  all targeted checks PASS on real data (control OK)")

    print("\n" + "=" * 78)
    print("MUTATION TEST: inject each violation, the check MUST flip to FAIL")
    print("=" * 78)
    leaks = 0
    for label, needle, fn, mut in CASES:
        t2, g2 = mut(T.copy(), G.copy())
        res = run(fn, t2, g2)
        if "__error__" in res:
            print(f"  ERROR   {label:28s} {res['__error__']}")
            leaks += 1
            continue
        hits = [k for k in res if needle in k]
        statuses = {res[k] for k in hits}
        caught = bool(hits) and ("FAIL" in statuses)
        tag = "CAUGHT" if caught else "LEAK !!"
        print(f"  {tag:8s} {label:28s} -> "
              f"{('FAIL' if caught else (','.join(statuses) if hits else 'NO CHECK NAMED '+repr(needle)))}")
        if not caught:
            leaks += 1
    print("\n" + "=" * 78)
    print(f"RESULT: {len(CASES)} mutations, {leaks} LEAK(S)")
    print("=" * 78)
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
