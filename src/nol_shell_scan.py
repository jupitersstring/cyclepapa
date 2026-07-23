#!/usr/bin/env python3
"""
nol_shell_scan.py — the WMIH→Mr. Cooper NOL-shell registry.

The case-study playbook: a reorganized company can carry NET OPERATING LOSS
carryforwards that dwarf its market cap (WaMu's shell carried billions of
NOLs against a tiny cap; KKR backed it; the Nationstar merger made Mr.
Cooper. Charter emerged with ~$8bn of NOLs behind a scary headline). The
market routinely prices these tax assets at ~zero because the shell has no
operations — until an acquirer arrives to shelter income.

This scans the post-reorg cohort's SEC XBRL for NOL carryforwards
(OperatingLossCarryforwards, else the deferred-tax-asset variant), compares
them to market cap, and reports every name whose NOLs are a material
fraction of its value. Missing data = skipped silently as unknown, never
penalized.

Output: output/nol_shells.md

Usage:
    python -m src.nol_shell_scan
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.postreorg_score import (
    collect_postreorg, _xbrl, _shares, _price, _norm, chapter22_ciks)

REPO = Path(__file__).resolve().parent.parent
OUT_MD = REPO / "output" / "nol_shells.md"


def nol_for(cik: int) -> float | None:
    return (_xbrl(cik, "OperatingLossCarryforwards") or
            _xbrl(cik, "DeferredTaxAssetsOperatingLossCarryforwards"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-ratio", type=float, default=0.5,
                    help="report names with NOL >= this fraction of mkt cap")
    args = ap.parse_args()

    cohort = collect_postreorg()
    ch22 = chapter22_ciks()
    genuine = {k: r for k, r in cohort.items()
               if "freshstart" in r.get("query_label", "")
               or "emerged" in r.get("query_label", "")
               or _norm(r.get("name", "")) in ch22}
    print(f"Scanning {len(genuine)} genuine post-reorgs for NOL shells...")

    rows = []
    for i, (cik, rec) in enumerate(sorted(genuine.items(), key=lambda x: x[0])):
        ticker = (rec.get("ticker") or "").split(":")[-1]
        nol = nol_for(int(cik))
        if not nol or nol <= 0:
            time.sleep(0.1)
            continue
        price = _price(ticker) if ticker else None
        shares = _shares(int(cik))
        mkt_cap = price * shares if (price and shares) else None
        ratio = (nol / mkt_cap) if mkt_cap else None
        rows.append({"name": rec.get("name", ""), "ticker": ticker,
                     "nol": nol, "mkt_cap": mkt_cap, "ratio": ratio})
        time.sleep(0.15)
        if (i + 1) % 25 == 0:
            print(f"  scanned {i+1}/{len(genuine)}...")

    flagged = sorted([r for r in rows if r["ratio"] and
                      r["ratio"] >= args.min_ratio],
                     key=lambda r: -r["ratio"])
    known_nol = sorted([r for r in rows if r["ratio"] is None],
                       key=lambda r: -r["nol"])

    lines = [
        "# NOL-shell registry — tax attributes vs market cap",
        "",
        "The WMIH→Mr. Cooper playbook: reorganized companies whose NOL "
        "carryforwards are a material fraction of (or larger than) their "
        "market cap. The market prices these tax assets near zero until an "
        "acquirer arrives to shelter income against them — §382 change-of-"
        "ownership rules preserved through the plan are the moat. Verify "
        "any §382 annual limitation before relying on the gross figure.",
        "",
        f"- post-reorgs scanned: **{len(genuine)}**  ·  with disclosed "
        f"NOLs: **{len(rows)}**  ·  NOL ≥ {args.min_ratio:.0%} of mkt cap: "
        f"**{len(flagged)}**",
        "",
        "| Name | Ticker | NOL | Mkt cap | NOL/cap |",
        "|---|---|---:|---:|---:|",
    ]
    for r in flagged:
        lines.append(
            f"| {str(r['name'])[:34]} | {r['ticker'] or '—'} | "
            f"${r['nol']/1e9:.2f}bn | ${r['mkt_cap']/1e9:.2f}bn | "
            f"**{r['ratio']:.1f}x** |")
    if known_nol:
        lines += ["", "## Disclosed NOLs, market cap unavailable (verify "
                  "manually — could be the deepest shells)", ""]
        for r in known_nol[:15]:
            lines.append(f"- {str(r['name'])[:40]} ({r['ticker'] or '—'}): "
                         f"${r['nol']/1e9:.2f}bn NOL")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_MD}")
    print(f"NOL-heavy names (≥{args.min_ratio:.0%} of cap): {len(flagged)}")
    for r in flagged[:10]:
        print(f"  {r['ticker'] or '—':8} {str(r['name'])[:30]:30} "
              f"NOL ${r['nol']/1e9:.1f}bn = {r['ratio']:.1f}x cap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
