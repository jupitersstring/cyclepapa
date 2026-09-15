"""Final ranking: merge every sweep, apply universe filter, surface top N.

Reads every available *_detail.json output from the cyclepapa/ root,
de-dups by ticker (keeping the row with the highest munger_composite),
drops SPAC warrants / preferreds / blank-check names, and prints a
concise top-N table with the dominant signal type per row.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from universe_filter import is_excluded


def load_detail(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--min-price", type=float, default=0.50)
    p.add_argument("--min-mcap-musd", type=float, default=20.0,
                   help="Minimum market cap in $M (when known).")
    p.add_argument("--sources", nargs="+", default=[
        "v2_detail.json",
        "wide180_detail.json",
        "induce_detail.json",
        "restruct_v7.json",
        "targets_v4.json",
        "v3_run.json",
    ])
    args = p.parse_args()

    rows: list[dict] = []
    for fn in args.sources:
        path = Path(fn)
        loaded = load_detail(path)
        for r in loaded:
            r["_source"] = fn
        rows.extend(loaded)
        if loaded:
            print(f"  loaded {len(loaded):>4} rows from {fn}")

    if not rows:
        print("No source files found.")
        return 1

    # Merge by ticker, keep the row with the highest composite.
    by_ticker: dict[str, dict] = {}
    for r in rows:
        if r.get("error"):
            continue
        tk = (r.get("ticker") or "").upper()
        if not tk:
            continue
        score = r.get("munger_composite") or r.get("asymmetry") or 0
        cur = by_ticker.get(tk)
        cur_score = (cur.get("munger_composite") if cur else 0) or 0
        if cur is None or score > cur_score:
            by_ticker[tk] = r

    # Apply universe filter.
    eligible = []
    excluded = 0
    for tk, r in by_ticker.items():
        bad, _why = is_excluded(tk, r.get("company"))
        if bad:
            excluded += 1
            continue
        px = r.get("current_price")
        if px is not None and px < args.min_price:
            excluded += 1
            continue
        mc = r.get("market_cap")
        if mc is not None and mc / 1e6 < args.min_mcap_musd:
            excluded += 1
            continue
        eligible.append(r)

    eligible.sort(key=lambda r: r.get("munger_composite") or 0, reverse=True)
    print(f"\nMerged: {len(by_ticker)} unique tickers across sources.")
    print(f"Excluded (SPAC/preferred/sub-${args.min_price}/sub-${args.min_mcap_musd}M): "
          f"{excluded}")
    print(f"Eligible: {len(eligible)}\n")

    print(f"=== TOP {args.top} OPPORTUNITIES ===\n")
    for i, r in enumerate(eligible[: args.top], 1):
        tk = r.get("ticker", "")
        co = (r.get("company") or "")[:40]
        px = r.get("current_price") or 0
        mc = (r.get("market_cap") or 0) / 1e6
        mcs = f"${mc:.0f}M" if mc else "-"
        comp = r.get("munger_composite") or 0
        asym = r.get("asymmetry") or 0
        proc = r.get("process_quality") or 0
        spc = r.get("special_situations_score") or 0
        tax = r.get("taxonomy") or ""
        # Pick the dominant signal
        signals = []
        if r.get("transformation_signal"):
            signals.append("PSU TRANSFORM")
        if (r.get("distressed_stub_score") or 0) >= 50:
            signals.append("DISTRESSED STUB")
        if r.get("active_bid"):
            signals.append("ACTIVE BID")
        if r.get("has_special_committee"):
            signals.append("SPECIAL CMTE")
        if r.get("activists_named"):
            a = (r.get("activists_named") or [])
            signals.append(f"ACTIVIST({a[0] if a else '?'})")
        if r.get("has_spinoff"):
            signals.append("SPIN-OFF")
        if r.get("go_private_language"):
            signals.append("GO-PRIVATE")
        if r.get("governance_reset"):
            signals.append("GOV RESET")
        h = r.get("stock_price_hurdles") or []
        if h and px > 0 and max(h) / px >= 2.0:
            signals.append(f"OTM LADDER {max(h)/px:.1f}x")

        print(f"#{i:<2} {tk:<8} {co:<40} ${px:>7.2f}  {mcs:>8}  "
              f"comp={comp:>5.1f}  psu={asym:>4.0f}  proc={proc:>4.0f}  "
              f"sp={spc:>4.0f}")
        print(f"      taxonomy: {tax}")
        if signals:
            print(f"      signals : {' | '.join(signals)}")
        cs = r.get("compound_screens") or []
        if cs:
            for screen in cs[:3]:
                print(f"      screen  : {screen}")
        # Key extracted facts
        facts = []
        if r.get("debt_reduced_musd"):
            facts.append(f"debt_reduced=${r['debt_reduced_musd']:.0f}M")
        if r.get("participation_pct"):
            facts.append(f"participation={r['participation_pct']:.0f}%")
        if r.get("buyback_authorisation_musd"):
            facts.append(f"buyback_auth=${r['buyback_authorisation_musd']:.0f}M")
        if r.get("largest_owner_pct"):
            facts.append(f"largest_owner={r['largest_owner_pct']:.0f}%")
        if r.get("offer_price"):
            facts.append(f"offer=${r['offer_price']:.2f}")
        if h:
            facts.append(f"hurdles={h}")
        if facts:
            print(f"      facts   : {'; '.join(facts)}")
        if r.get("filing_url"):
            print(f"      filing  : {r['filing_url']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
