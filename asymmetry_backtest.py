"""Point-in-time validation of the asymmetry-assembly engine.

The test that matters for the PSIX recipe is not whether the engine
flags PSIX today (after a ~20x move) but whether it would have fired in
MAY 2024, at ~$2.15, when the inflection was just beginning. This
harness reconstructs PSIX's May-2024 inputs -- live XBRL for the quarter
ending 2024-03-31 (as reported 7 May 2024), the documented capital
structure, and the curated Weichai/Gagnon revealed-preference events --
and runs them through the SAME score_components() + assemble() functions
the live engine uses. No scoring logic is duplicated: if it flags PSIX
here, the live engine's logic flags the pattern.

Run: python3 asymmetry_backtest.py
"""

from __future__ import annotations

import json
from pathlib import Path

from financials_inflection import analyze
from asymmetry_assembly import score_components, assemble

ROOT = Path("/home/user/cyclepapa")
PSIX_CIK = "0001137091"
AS_OF = "2024-05-15"


def build_may2024_inputs():
    """Documented May-2024 PSIX snapshot (essay + 10-Q). ~22.97M shares,
    $2.15, $140.2M debt, $33.1M cash -> ~$49M cap, ~$107M net debt."""
    shares = 22_970_000
    price = 2.15
    mcap = shares * price                       # ~$49.4M
    net_debt = 140_200_000 - 33_100_000         # ~$107.1M
    yf = {"PSIX": {"price": price, "mcap": mcap,
                   "p_b": None,                 # residual stub, not a low-P/B name
                   "fwk_high": 4.5, "inst_pct": 0.10, "short_pct": 0.0,
                   "name": "Power Solutions International"}}
    # balance-sheet fragility (demandable bank line, tiny equity beneath big debt)
    q10 = {"PSIX": {"equity": 49_000_000, "long_term_debt": 140_200_000,
                    "net_cash": -net_debt, "current_ratio": 1.05,
                    "ncav_per_share": None}}
    coval = {"PSIX": {"drawdown_pct": 52.0}}     # OTC, deep prior drawdown
    # Gagnon open-market $2 buys -> the C4 revealed-insider tell
    f4 = {"PSIX": {"buyer_set": ["Gagnon Neil | 10% owner"],
                   "total_dollar": 155236.0, "filings": [
                       {"person": "Gagnon Neil", "date": "2024-04-30",
                        "dollar": 155236.0, "shares": 77618}]}}
    disc = {}                                    # conviction leg not run for 2024
    # OTC->Nasdaq relisting was the pending recognition catalyst
    p11 = {}; tender = {}; t13f = {}; emc = {}
    return yf, q10, coval, f4, disc, p11, tender, t13f, emc


def main() -> int:
    yf, q10, coval, f4, disc, p11, tender, t13f, emc = build_may2024_inputs()
    fin_rec = analyze(PSIX_CIK, as_of=AS_OF)
    if not fin_rec:
        print("could not pull PSIX XBRL as-of", AS_OF)
        return 1
    fin = {"PSIX": fin_rec}
    events = json.loads((ROOT / "asymmetry_events.json").read_text())

    C, dd = score_components("PSIX", yf, q10, disc, f4, coval, p11, tender,
                             t13f, emc, fin, events)
    res = assemble(C)

    print("=" * 66)
    print(f"  PSIX asymmetry-assembly backtest as of {AS_OF} (@ $2.15)")
    print("=" * 66)
    print("\nXBRL for the quarter ending", fin_rec["period_end"], "(reported 7 May 2024):")
    for k in ("revenue_yoy", "gp_yoy", "gross_margin_delta_pp",
              "interest_exp_yoy", "capex_to_rev", "opinc", "opinc_to_ppe"):
        if k in fin_rec:
            print(f"    {k:24} {fin_rec[k]}")

    print("\nComponent ledger:")
    labels = {
        "C1_low_expectations": "low expectations (cheap)",
        "C2_leveraged_survivor": "leveraged survivor (torque+fragility)",
        "C3_orphaned_drawdown": "orphaned / deep drawdown",
        "C4_revealed_insider": "revealed insider buy (Gagnon)",
        "C5_recognition_catalyst": "recognition catalyst",
        "C6_operating_inflection": "operating inflection (mix shift)",
        "C7_deleveraging": "deleveraging engine",
        "C8_underused_capacity": "underused capacity (high marginal ROIC)",
    }
    for k, lab in labels.items():
        c = C[k]
        mark = "[x]" if c["present"] else "[ ]"
        print(f"    {mark} {lab:42} {c.get('evidence','')}")
    pro = C["C9_revealed_events"]["pro"]
    print(f"    [{'x' if pro else ' '}] curated pro-actions: "
          + "; ".join(e["type"] for e in pro))
    counter = C["C9_revealed_events"]["counter"]
    if counter:
        print(f"    [!] counter-signals: " + "; ".join(e["type"] for e in counter))

    print("\nResult:")
    print(f"    spine_met       : {res['spine_met']}")
    print(f"    components fired: {res['n_present']}/8")
    print(f"    assembly score  : {res['score']}")
    print(f"    reasons         : {res['reasons']}")

    ok = res["spine_met"] and res["n_present"] >= 6 and res["score"] >= 60
    print("\n" + ("PASS -- the engine flags May-2024 PSIX as a full assembly."
                  if ok else "FAIL -- engine did not flag PSIX; investigate."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
