"""Flatten the harvested edgar_segments_cache/ JSONs into a tidy
per-filer per-segment-period CSV.

Each filing's dimensional facts get unpacked: one row per
(symbol, accession, period_end, concept, axis, member, value).
Downstream we can pivot to compute things like:

  - segment_revenue_concentration_hhi
  - geographic_revenue_mix
  - fastest_growing_segment
  - product_line_margin_dispersion

Output:
  edgar_segments.csv         flat row-per-fact table
  edgar_segments_summary.csv per-filer aggregates
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import pandas as pd


CACHE_DIR = Path("edgar_segments_cache")


# Axes we care about for the multi-bagger framework. Anything not on
# this list is ignored to keep the output focused.
INTERESTING_AXES = {
    # Segment breakdowns
    "us-gaap:StatementBusinessSegmentsAxis",
    "us-gaap:SegmentAxis",
    "us-gaap:StatementGeographicalAxis",
    "us-gaap:ProductOrServiceAxis",
    "srt:ProductOrServiceAxis",
    "srt:GeographicalAxis",
    # Customer / channel concentration
    "us-gaap:MajorCustomersAxis",
    "us-gaap:CustomerConcentrationRiskAxis",
    # Subsidiary / legal entity
    "dei:LegalEntityAxis",
}

# Concepts that carry segment-relevant economic data
INTERESTING_CONCEPTS = {
    "us-gaap:Revenues",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap:SalesRevenueNet",
    "us-gaap:OperatingIncomeLoss",
    "us-gaap:GrossProfit",
    "us-gaap:Assets",
    "us-gaap:DepreciationDepletionAndAmortization",
    "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
}


def extract_facts(cache_path: Path) -> list[dict]:
    """Return flat per-fact rows from one cache JSON."""
    try:
        data = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    symbol = data.get("symbol")
    cik = data.get("cik")
    rows = []
    for accession, facts in (data.get("facts_by_filing") or {}).items():
        for f in facts or []:
            concept = f.get("concept")
            if not concept:
                continue
            value = f.get("value")
            if value is None:
                continue
            dims = f.get("dimensions") or {}
            if not dims:
                continue
            # Filter to interesting axes — if none of the dims hit, skip
            relevant_dims = {k: v for k, v in dims.items() if k in INTERESTING_AXES}
            if not relevant_dims:
                continue
            # Filter to interesting concepts (most segment data is on these)
            if concept not in INTERESTING_CONCEPTS:
                # Allow company-specific aa:* if matched on segment axis
                if not any(ax in relevant_dims
                           for ax in ("us-gaap:StatementBusinessSegmentsAxis",
                                       "us-gaap:StatementGeographicalAxis",
                                       "srt:ProductOrServiceAxis",
                                       "us-gaap:ProductOrServiceAxis")):
                    continue
            for axis, member in relevant_dims.items():
                rows.append({
                    "symbol": symbol,
                    "cik": cik,
                    "accession": accession,
                    "concept": concept,
                    "label": f.get("label"),
                    "period_start": f.get("period_start"),
                    "period_end": f.get("period_end"),
                    "fiscal_period": f.get("fiscal_period"),
                    "fiscal_year": f.get("fiscal_year"),
                    "axis": axis,
                    "member": member,
                    "value": value,
                    "unit": f.get("unit"),
                    "currency": f.get("currency"),
                    "statement_type": f.get("statement_type"),
                })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="edgar_segments.csv")
    ap.add_argument("--summary-out", default="edgar_segments_summary.csv")
    args = ap.parse_args()

    files = sorted(CACHE_DIR.glob("*.json"))
    if not files:
        print(f"No files in {CACHE_DIR}", file=sys.stderr)
        sys.exit(1)
    print(f"Processing {len(files):,} cache files...", file=sys.stderr)

    all_rows = []
    for i, p in enumerate(files):
        all_rows.extend(extract_facts(p))
        if (i + 1) % 500 == 0:
            print(f"  {i+1:,}/{len(files):,}", file=sys.stderr)
    df = pd.DataFrame(all_rows)
    print(f"Total fact rows: {len(df):,}", file=sys.stderr)
    if df.empty:
        print("No matching facts found", file=sys.stderr)
        return
    df.to_csv(args.out, index=False)
    print(f"wrote {args.out}", file=sys.stderr)

    # Summary per filer: distinct axes / members seen + top 3 segments
    print("\nBuilding per-filer summary...", file=sys.stderr)
    summary_rows = []
    for sym, g in df.groupby("symbol"):
        axes = g.axis.value_counts().head(3).to_dict()
        members = g.member.value_counts().head(5).index.tolist()
        # Latest-period revenue by segment
        rev = g[g.concept.str.contains("Revenue", case=False, na=False)]
        seg_rev = (rev[rev.axis == "us-gaap:StatementBusinessSegmentsAxis"]
                   .sort_values("period_end", ascending=False)
                   .head(20)) if not rev.empty else pd.DataFrame()
        top_segments = seg_rev.member.value_counts().head(3).index.tolist() if not seg_rev.empty else []
        summary_rows.append({
            "symbol": sym,
            "n_segment_facts": len(g),
            "n_distinct_axes": g.axis.nunique(),
            "n_distinct_members": g.member.nunique(),
            "top_axes": ", ".join(f"{k}:{v}" for k, v in axes.items())[:200],
            "top_members": "; ".join(members)[:200],
            "top_revenue_segments": "; ".join(top_segments)[:200],
        })
    summary_df = pd.DataFrame(summary_rows).sort_values("n_segment_facts", ascending=False)
    summary_df.to_csv(args.summary_out, index=False)
    print(f"wrote {args.summary_out}: {len(summary_df):,} filers with segment data",
          file=sys.stderr)
    print(f"\nTop 10 filers by segment-fact richness:", file=sys.stderr)
    print(summary_df.head(10)[["symbol", "n_segment_facts", "n_distinct_axes",
                               "top_revenue_segments"]].to_string(index=False),
          file=sys.stderr)


if __name__ == "__main__":
    main()
