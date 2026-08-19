"""Portfolio builder — turns the ranked screen output into a model
position list with sizing and concentration caps.

Inputs:  results_YYYYMMDD.csv from screen_v3.py
Outputs: portfolio_YYYYMMDD.csv   — sized positions, ordered by entry priority
         portfolio_YYYYMMDD.md     — human-readable rationale

Sizing model:
  * Setup sleeve max position: 5% (top conviction with chart confirmation)
  * Fundamentals sleeve max:   4% (event catalyst, no chart yet)
  * MICRO sleeve max:          1% (illiquid, slow accumulation)
  * Activist watch max:        3% (resolution-signal-only)

Concentration caps:
  * Max 30% in any single catalyst class
  * Max 40% in any single nav_quality class
  * Max 25% in any single AIC sector
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


MAX_POSITION_BY_SLEEVE = {
    "setup":        0.05,
    "fundamentals": 0.04,
    "activist":     0.03,
    "micro":        0.01,
}

CONCENTRATION_CAPS = {
    "catalyst":     0.30,
    "nav_quality":  0.40,
    "aic_sector_code": 0.25,
}


def _kelly_fraction(irr: float, vol_estimate: float = 0.25) -> float:
    """Tiny Kelly proxy: weight = IRR / vol² capped at max_size. This is
    not real Kelly (no leverage, no covariance) — just a way to
    differentiate a 35% IRR from a 5% IRR when allocating between
    same-sleeve positions."""
    if irr <= 0:
        return 0.0
    return min(0.50, irr / (vol_estimate ** 2))


def build_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    """Take the full results frame, emit a sized position list."""
    keep = df[(df["error"].isna()) & (df["investable"] == True)].copy()
    keep = keep[keep["expected_irr"].fillna(0) > 0]
    out_rows = []
    for _, r in keep.iterrows():
        # Determine sleeve membership and corresponding cap
        if r.get("in_setup_sleeve") and r.get("composite_score", 0) > 0.01:
            sleeve = "setup"
        elif r.get("in_fundamentals_sleeve"):
            sleeve = "fundamentals"
        elif r.get("resolution_score", 0) >= 0.20:
            sleeve = "activist"
        elif r.get("in_micro_sleeve"):
            sleeve = "micro"
        else:
            continue
        max_pos = MAX_POSITION_BY_SLEEVE[sleeve]
        raw_weight = _kelly_fraction(float(r["expected_irr"]))
        weight = min(max_pos, raw_weight)
        out_rows.append({
            "ticker": r["ticker"],
            "name": r.get("name", ""),
            "sleeve": sleeve,
            "weight_raw": round(raw_weight, 4),
            "weight_capped": round(weight, 4),
            "catalyst": r.get("catalyst", ""),
            "nav_quality": r.get("nav_quality", ""),
            "aic_sector_code": r.get("aic_sector_code", ""),
            "expected_irr": round(float(r["expected_irr"]), 4),
            "resolution_score": round(float(r.get("resolution_score") or 0), 3),
            "phase": r.get("phase", ""),
            "discount": round(float(r.get("nav_discount_est") or 0), 3),
            "discount_vs_sector_pp": round(float(r.get("discount_vs_sector_pp") or 0), 2),
            "saba_ukit_member": bool(r.get("saba_ukit_member") or False),
        })
    out = pd.DataFrame(out_rows)
    if out.empty:
        return out
    # Apply concentration caps
    out = out.sort_values(["sleeve", "expected_irr"], ascending=[True, False])
    for cap_col, cap_pct in CONCENTRATION_CAPS.items():
        if cap_col not in out.columns:
            continue
        # Iteratively reduce overweight buckets until cap satisfied
        for _ in range(10):
            totals = out.groupby(cap_col)["weight_capped"].sum()
            over = totals[totals > cap_pct]
            if over.empty:
                break
            for bucket, total in over.items():
                factor = cap_pct / total
                mask = out[cap_col] == bucket
                out.loc[mask, "weight_capped"] = out.loc[mask, "weight_capped"] * factor
    # Normalise so portfolio sums to 1.0 (assuming cash is the residual)
    total = out["weight_capped"].sum()
    if total > 1.0:
        out["weight_capped"] = out["weight_capped"] / total
    out["weight_capped"] = out["weight_capped"].round(4)
    out = out.sort_values("weight_capped", ascending=False)
    return out


def render_markdown(portfolio: pd.DataFrame) -> str:
    """Human-readable model portfolio summary."""
    if portfolio.empty:
        return "# Model portfolio\n\nNo qualifying names."
    lines = [
        "# Model portfolio",
        f"\nGenerated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"\nTotal allocation: {portfolio['weight_capped'].sum() * 100:.1f}%  "
        f"({len(portfolio)} positions)",
        f"\nCash residual: {max(0, 1 - portfolio['weight_capped'].sum()) * 100:.1f}%",
        "",
        "## By sleeve",
    ]
    for sleeve, group in portfolio.groupby("sleeve"):
        lines.append(f"\n### {sleeve.upper()}  "
                     f"({len(group)} names, {group['weight_capped'].sum()*100:.1f}%)")
        lines.append("\n| Ticker | Name | Wt | IRR | Resolution | Disc | Catalyst |")
        lines.append("|---|---|---|---|---|---|---|")
        for _, r in group.iterrows():
            saba = " *" if r["saba_ukit_member"] else ""
            name = r.get("name", "")
            if not isinstance(name, str):
                name = ""
            lines.append(
                f"| {r['ticker']}{saba} | {name[:40]} | "
                f"{r['weight_capped']*100:.1f}% | "
                f"{r['expected_irr']*100:.1f}% | {r['resolution_score']:.2f} | "
                f"{r['discount']*100:.0f}% | {r['catalyst']} |"
            )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("results_csv", nargs="?",
                   help="Path to results_*.csv (defaults to latest)")
    p.add_argument("--out-csv", default=None)
    p.add_argument("--out-md", default=None)
    args = p.parse_args()
    here = Path(os.path.dirname(os.path.abspath(__file__)))
    if args.results_csv is None:
        candidates = sorted(here.glob("results_*.csv"))
        candidates = [c for c in candidates if "_top30" not in c.name
                      and "_sleeves" not in c.name]
        if not candidates:
            print("No results_*.csv found", file=sys.stderr)
            return 1
        args.results_csv = str(candidates[-1])
    df = pd.read_csv(args.results_csv)
    portfolio = build_portfolio(df)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    out_csv = args.out_csv or here / f"portfolio_{stamp}.csv"
    out_md = args.out_md or here / f"portfolio_{stamp}.md"
    portfolio.to_csv(out_csv, index=False)
    with open(out_md, "w") as f:
        f.write(render_markdown(portfolio))
    print(f"[portfolio] {len(portfolio)} positions, "
          f"{portfolio['weight_capped'].sum()*100:.1f}% allocated", file=sys.stderr)
    print(f"  csv: {out_csv}", file=sys.stderr)
    print(f"  md:  {out_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
