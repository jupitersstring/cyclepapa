"""Derive multi-bagger archetypes from the harvested segment-level XBRL.

Reads edgar_segments.csv (produced by edgar_segments_extract.py) and
computes per-filer signals that aren't visible in companyfacts JSON:

  segment_count                  number of distinct business segments
  segment_revenue_hhi            Herfindahl index of segment revenue mix
                                  (0 = perfectly diversified, 1 = single segment)
  largest_segment_share          % of revenue from the biggest segment
  geographic_region_count        number of geographic regions reporting
  largest_region_share           % of revenue from the biggest region
  segment_growth_dispersion      stdev of YoY growth across segments
  fastest_segment_yoy            max YoY growth across segments
  customer_concentration_flag    1 if any Major Customer concept fires

Output: edgar_segment_signals.csv (symbol-keyed, can merge into
asymmetry_global like the EDGAR layer).
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd


SEGMENT_AXIS = "us-gaap:StatementBusinessSegmentsAxis"
GEOGRAPHIC_AXES = {
    "us-gaap:StatementGeographicalAxis",
    "srt:StatementGeographicalAxis",
}
PRODUCT_AXIS = "srt:ProductOrServiceAxis"
PRODUCT_AXIS_ALT = "us-gaap:ProductOrServiceAxis"
CUSTOMER_AXIS = "us-gaap:MajorCustomersAxis"
CUSTOMER_RISK_AXIS = "us-gaap:CustomerConcentrationRiskAxis"

REVENUE_CONCEPTS = {
    "us-gaap:Revenues",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap:SalesRevenueNet",
}


def _latest_period_per_symbol(df: pd.DataFrame) -> pd.DataFrame:
    """Pick the latest period_end per symbol; segment facts use the
    most recent fiscal year to avoid mixing FY and Q periods."""
    df = df[df.period_end.notna()].copy()
    df["period_end_dt"] = pd.to_datetime(df.period_end, errors="coerce")
    df = df.dropna(subset=["period_end_dt"])
    # Use latest FY where available, else latest period_end
    fy = df[df.fiscal_period == "FY"]
    if not fy.empty:
        latest_fy = fy.groupby("symbol")["period_end_dt"].max().reset_index()
        latest_fy.columns = ["symbol", "latest_fy_end"]
        df = df.merge(latest_fy, on="symbol", how="left")
        return df[df.period_end_dt == df.latest_fy_end].drop(columns=["latest_fy_end"])
    else:
        latest = df.groupby("symbol")["period_end_dt"].max().reset_index()
        latest.columns = ["symbol", "latest_end"]
        df = df.merge(latest, on="symbol", how="left")
        return df[df.period_end_dt == df.latest_end].drop(columns=["latest_end"])


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Per-filer aggregate signals."""
    if df.empty:
        return pd.DataFrame()

    rows = []
    for sym, g in df.groupby("symbol"):
        # Filter to revenue-concept facts (HHI etc. only meaningful on revenue)
        rev = g[g.concept.isin(REVENUE_CONCEPTS)]

        # Latest-period segment revenue mix
        seg_rev = rev[rev.axis == SEGMENT_AXIS]
        seg_n = seg_rev.member.nunique() if not seg_rev.empty else 0
        if not seg_rev.empty:
            mix = seg_rev.groupby("member")["value"].sum()
            total = mix[mix > 0].sum()
            if total and total > 0:
                shares = (mix[mix > 0] / total)
                hhi = float((shares ** 2).sum())
                largest_share = float(shares.max())
            else:
                hhi = largest_share = None
        else:
            hhi = largest_share = None

        # Geographic mix
        geo_rev = rev[rev.axis.isin(GEOGRAPHIC_AXES)]
        geo_n = geo_rev.member.nunique() if not geo_rev.empty else 0
        if not geo_rev.empty:
            mix = geo_rev.groupby("member")["value"].sum()
            total = mix[mix > 0].sum()
            if total and total > 0:
                geo_largest = float((mix[mix > 0] / total).max())
            else:
                geo_largest = None
        else:
            geo_largest = None

        # Product / service mix
        prod_rev = rev[rev.axis.isin([PRODUCT_AXIS, PRODUCT_AXIS_ALT])]
        prod_n = prod_rev.member.nunique() if not prod_rev.empty else 0

        # Customer concentration — presence of any axis is a flag
        cust_flag = int(
            (g.axis == CUSTOMER_AXIS).any()
            or (g.axis == CUSTOMER_RISK_AXIS).any()
        )

        # Segment growth dispersion — needs two periods
        seg_growth_dispersion = None
        fastest_seg = None
        if not seg_rev.empty:
            two_period = seg_rev.copy()
            two_period["period_end_dt"] = pd.to_datetime(
                two_period.period_end, errors="coerce")
            two_period = two_period.dropna(subset=["period_end_dt"])
            # Pivot member × period
            pivot = (two_period.pivot_table(
                index="member", columns="period_end_dt",
                values="value", aggfunc="sum"
            ))
            if pivot.shape[1] >= 2:
                pivot = pivot.sort_index(axis=1)
                latest = pivot.iloc[:, -1]
                prior = pivot.iloc[:, -2]
                yoy = (latest - prior) / prior.replace({0: np.nan})
                yoy = yoy[yoy.between(-1, 5)]  # sanity clip
                if not yoy.empty:
                    seg_growth_dispersion = float(yoy.std())
                    fastest_seg = float(yoy.max())

        rows.append({
            "symbol": sym,
            "segment_count": seg_n,
            "segment_revenue_hhi": hhi,
            "largest_segment_share": largest_share,
            "geographic_region_count": geo_n,
            "largest_region_share": geo_largest,
            "product_line_count": prod_n,
            "customer_concentration_flag": cust_flag,
            "segment_growth_dispersion": seg_growth_dispersion,
            "fastest_segment_yoy": fastest_seg,
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="edgar_segments.csv")
    ap.add_argument("--out", default="edgar_segment_signals.csv")
    args = ap.parse_args()

    print(f"loading {args.segments}...", file=sys.stderr)
    df = pd.read_csv(args.segments)
    print(f"  {len(df):,} fact rows, {df.symbol.nunique():,} filers",
          file=sys.stderr)

    # Use latest period per filer for the snapshot signals
    df_latest = _latest_period_per_symbol(df)
    print(f"  latest-period rows: {len(df_latest):,}", file=sys.stderr)

    out = derive(df)
    out.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}: {len(out):,} filers", file=sys.stderr)
    print(f"\nCoverage by field:", file=sys.stderr)
    for c in out.columns:
        if c == "symbol":
            continue
        non_null = out[c].notna().sum() if out[c].dtype != bool else (out[c] != 0).sum()
        print(f"  {c:30s} {non_null:5d} / {len(out):,}", file=sys.stderr)
    # Sample
    print(f"\nSample (top 10 by segment count):", file=sys.stderr)
    print(out.sort_values("segment_count", ascending=False).head(10).to_string(index=False),
          file=sys.stderr)


if __name__ == "__main__":
    main()
