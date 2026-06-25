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


def _clean_member(m: str) -> str:
    """Strip XBRL prefixes + 'Member' suffix from a segment label so it
    reads as a human-friendly business name.

    Examples:
      met:GroupBenefitsSegmentMember     -> Group Benefits
      apo:RetirementServicesSegmentMember -> Retirement Services
      us-gaap:CorporateAndOtherMember     -> Corporate And Other
    """
    if not isinstance(m, str):
        return ""
    # Strip namespace prefix (anything before colon)
    if ":" in m:
        m = m.split(":", 1)[1]
    # Strip trailing 'Member' and 'Segment'
    for suf in ("Member", "Segment"):
        while m.endswith(suf):
            m = m[: -len(suf)]
    # CamelCase → spaced (insert space before any capital that follows a lower)
    import re
    m = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", m)
    m = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", m)
    return m.strip()


def _mix_table(rev_df: pd.DataFrame, top_n: int = 3):
    """Given member-keyed revenue facts, return (mix_dict, top_n_list,
    total_revenue) sorted descending by % share."""
    if rev_df.empty:
        return {}, [], None
    mix = rev_df.groupby("member")["value"].sum()
    mix = mix[mix > 0]
    if mix.empty:
        return {}, [], None
    total = float(mix.sum())
    shares = (mix / total).sort_values(ascending=False)
    top = [(m, float(shares[m])) for m in shares.head(top_n).index]
    return shares.to_dict(), top, total


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Per-filer aggregate signals + segment-level detail."""
    if df.empty:
        return pd.DataFrame()

    rows = []
    for sym, g in df.groupby("symbol"):
        # Filter to revenue-concept facts (HHI etc. only meaningful on revenue)
        rev = g[g.concept.isin(REVENUE_CONCEPTS)]

        # Latest-period segment revenue mix
        seg_rev = rev[rev.axis == SEGMENT_AXIS]
        seg_n = seg_rev.member.nunique() if not seg_rev.empty else 0
        seg_shares, seg_top, seg_total = _mix_table(seg_rev)
        if seg_shares:
            hhi = float(sum(v * v for v in seg_shares.values()))
            largest_share = max(seg_shares.values())
            largest_segment_name = _clean_member(seg_top[0][0]) if seg_top else None
            top_segments_str = "; ".join(
                f"{_clean_member(m)} {s*100:.0f}%" for m, s in seg_top
            )
        else:
            hhi = largest_share = None
            largest_segment_name = None
            top_segments_str = ""

        # Geographic mix
        geo_rev = rev[rev.axis.isin(GEOGRAPHIC_AXES)]
        geo_n = geo_rev.member.nunique() if not geo_rev.empty else 0
        geo_shares, geo_top, _ = _mix_table(geo_rev)
        if geo_shares:
            geo_largest = max(geo_shares.values())
            largest_region_name = _clean_member(geo_top[0][0]) if geo_top else None
            top_regions_str = "; ".join(
                f"{_clean_member(m)} {s*100:.0f}%" for m, s in geo_top
            )
        else:
            geo_largest = None
            largest_region_name = None
            top_regions_str = ""

        # Product / service mix
        prod_rev = rev[rev.axis.isin([PRODUCT_AXIS, PRODUCT_AXIS_ALT])]
        prod_n = prod_rev.member.nunique() if not prod_rev.empty else 0

        # Customer concentration — presence of any axis is a flag
        cust_flag = int(
            (g.axis == CUSTOMER_AXIS).any()
            or (g.axis == CUSTOMER_RISK_AXIS).any()
        )

        # Segment growth — by-member YoY + name of the fastest
        seg_growth_dispersion = None
        fastest_seg = None
        fastest_segment_name = None
        if not seg_rev.empty:
            two_period = seg_rev.copy()
            two_period["period_end_dt"] = pd.to_datetime(
                two_period.period_end, errors="coerce")
            two_period = two_period.dropna(subset=["period_end_dt"])
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
                    fastest_segment_name = _clean_member(yoy.idxmax())

        rows.append({
            "symbol": sym,
            "segment_count": seg_n,
            "segment_revenue_hhi": hhi,
            "largest_segment_share": largest_share,
            "largest_segment_name": largest_segment_name,
            "top_segments": top_segments_str,
            "segment_revenue_total": seg_total,
            "geographic_region_count": geo_n,
            "largest_region_share": geo_largest,
            "largest_region_name": largest_region_name,
            "top_regions": top_regions_str,
            "product_line_count": prod_n,
            "customer_concentration_flag": cust_flag,
            "segment_growth_dispersion": seg_growth_dispersion,
            "fastest_segment_yoy": fastest_seg,
            "fastest_segment_name": fastest_segment_name,
        })
    return pd.DataFrame(rows)


def derive_detail(df: pd.DataFrame) -> pd.DataFrame:
    """Long-form (symbol, segment_name, revenue_latest, share_latest, yoy_growth).

    One row per (symbol, member) with revenue level + % share + YoY
    growth, sorted within each symbol by share desc. Lets the workbook
    show the full segment table for any name we have data on.
    """
    if df.empty:
        return pd.DataFrame()
    rev = df[df.concept.isin(REVENUE_CONCEPTS)]
    seg_rev = rev[rev.axis == SEGMENT_AXIS].copy()
    if seg_rev.empty:
        return pd.DataFrame()
    seg_rev["period_end_dt"] = pd.to_datetime(seg_rev.period_end, errors="coerce")
    seg_rev = seg_rev.dropna(subset=["period_end_dt"])

    rows = []
    for sym, g in seg_rev.groupby("symbol"):
        pivot = g.pivot_table(index="member", columns="period_end_dt",
                              values="value", aggfunc="sum")
        if pivot.empty:
            continue
        pivot = pivot.sort_index(axis=1)
        latest_col = pivot.columns[-1]
        latest = pivot[latest_col]
        # Prior column for YoY if available
        prior = pivot.iloc[:, -2] if pivot.shape[1] >= 2 else None
        total_latest = latest[latest > 0].sum()
        if not total_latest or total_latest <= 0:
            continue
        for member in pivot.index:
            v_latest = latest.get(member)
            if pd.isna(v_latest) or v_latest <= 0:
                continue
            share = float(v_latest / total_latest)
            yoy = None
            if prior is not None:
                v_prior = prior.get(member)
                if pd.notna(v_prior) and v_prior > 0:
                    yoy = float((v_latest - v_prior) / v_prior)
                    if not -1 <= yoy <= 5:
                        yoy = None
            rows.append({
                "symbol": sym,
                "segment_name": _clean_member(member),
                "segment_member_raw": member,
                "revenue_latest": float(v_latest),
                "share_of_revenue": share,
                "yoy_growth": yoy,
                "period_end": str(pd.to_datetime(latest_col).date()),
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["symbol", "share_of_revenue"], ascending=[True, False])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="edgar_segments.csv")
    ap.add_argument("--out", default="edgar_segment_signals.csv")
    ap.add_argument("--detail-out", default="edgar_segment_detail.csv",
                    help="long-form per-segment-per-name table")
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

    detail = derive_detail(df)
    detail.to_csv(args.detail_out, index=False)
    print(f"wrote {args.detail_out}: {len(detail):,} rows "
          f"({detail.symbol.nunique() if not detail.empty else 0:,} filers, "
          f"{detail.segment_name.nunique() if not detail.empty else 0:,} distinct segment labels)",
          file=sys.stderr)
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
