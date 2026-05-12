"""Summarize the run outputs in a single report.

Reads from a results dir produced by earnings_price_analysis.py and prints:
  1. Universe coverage by region and signal type
  2. Underreaction->appreciation set (composite per-share preferred)
  3. FCF inflections (quarterly + TTM yearly)
  4. Negative-EV names
  5. Graham net-nets and strict net-nets
  6. Cheap (low P/B AND low P/S) + inflecting
  7. The intersection: deep-value AND fundamental-inflecting

Usage:
    python report.py [--results-dir results_expanded]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


VARIANTS = [
    "eps_return_absolute", "eps_return_vs_spx",
    "eps_sharpe_absolute", "eps_sharpe_vs_spx",
    "composite_return_absolute", "composite_return_vs_spx",
    "composite_sharpe_absolute", "composite_sharpe_vs_spx",
]


def _load(results_dir: Path, name: str) -> pd.DataFrame:
    p = results_dir / f"{name}.csv"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, index_col=0)


def _fmt(df: pd.DataFrame, max_rows: int = 20) -> str:
    pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)
    return df.head(max_rows).to_string()


def coverage(results_dir: Path) -> None:
    print("\n" + "=" * 90)
    print("COVERAGE")
    print("=" * 90)
    for v in VARIANTS:
        df = _load(results_dir, v).dropna(subset=["inflection_z"])
        if df.empty: continue
        print(f"  {v:<32}  {len(df):>5} valid tickers")
    for fname in ("composite_momentum", "fcf_inflections", "valuation_screen",
                  "deep_value_screen", "ranked"):
        df = _load(results_dir, fname) if fname != "fcf_inflections" else pd.read_csv(results_dir / "fcf_inflections.csv") if (results_dir / "fcf_inflections.csv").exists() else pd.DataFrame()
        if df.empty: continue
        print(f"  {fname + '.csv':<32}  {len(df):>5} rows")


def underreaction_to_appreciation(results_dir: Path) -> None:
    """Top names qualifying in N of 8 variants: positive growth, positive
    beta, inflection_z > 0.5. Prefer composite variants (per-share normalized)."""
    print("\n" + "=" * 90)
    print("UNDERREACTION -> APPRECIATION  (composite + EPS variants combined)")
    print("Filter: latest_growth > 0  AND  latest_beta > 0  AND  inflection_z > 0.5")
    print("=" * 90)
    agg: dict = {}
    for v in VARIANTS:
        df = _load(results_dir, v).dropna(subset=["inflection_z"])
        for tkr, row in df.iterrows():
            rec = agg.setdefault(tkr, {"n_qual": 0, "eps_qual": 0, "comp_qual": 0,
                                        "pct_sum": 0.0, "growth_sum": 0.0,
                                        "beta_sum": 0.0, "z_sum": 0.0, "count": 0})
            try:
                g = float(row["latest_growth"]); b = float(row["latest_beta"]); z = float(row["inflection_z"])
            except (TypeError, ValueError):
                continue
            rec["growth_sum"] += g; rec["beta_sum"] += b; rec["z_sum"] += z; rec["count"] += 1
            if g > 0 and b > 0 and z > 0.5:
                rec["n_qual"] += 1
                rec["pct_sum"] += float(row.get("inflection_z_pct", np.nan))
                if v.startswith("eps_"): rec["eps_qual"] += 1
                if v.startswith("composite_"): rec["comp_qual"] += 1
    if not agg: return
    df = pd.DataFrame(agg).T
    df["avg_growth"] = df["growth_sum"] / df["count"].replace(0, np.nan)
    df["avg_beta"]   = df["beta_sum"]   / df["count"].replace(0, np.nan)
    df["avg_z"]      = df["z_sum"]      / df["count"].replace(0, np.nan)
    df["avg_pct"]    = df["pct_sum"]    / df["n_qual"].replace(0, np.nan)
    df = df[df["n_qual"] >= 2].copy()
    df = df.sort_values(["n_qual", "avg_pct"], ascending=[False, False])

    cols = ["n_qual", "eps_qual", "comp_qual", "avg_growth", "avg_beta", "avg_z", "avg_pct"]
    sub = df.head(40)[cols].copy()
    for c in ("avg_growth", "avg_beta", "avg_z", "avg_pct"):
        sub[c] = sub[c].astype(float).round(2)
    for c in ("n_qual", "eps_qual", "comp_qual"):
        sub[c] = sub[c].astype(int)
    print(f"  qualifying in >= 2 of 8 variants: {len(df)}")
    print(f"  qualifying in >= 4 of 8 variants: {(df['n_qual'] >= 4).sum()}")
    print(f"  qualifying in >= 6 of 8 variants: {(df['n_qual'] >= 6).sum()}")
    print(f"\n  Top 40 by # qualifying variants, then by avg percentile:")
    print(_fmt(sub))


def fcf_inflections(results_dir: Path) -> None:
    p = results_dir / "fcf_inflections.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    print("\n" + "=" * 90)
    print("FCF NEGATIVE -> POSITIVE INFLECTIONS")
    print("=" * 90)
    for view in ("ttm_yoy", "quarterly_strict", "quarterly_loose", "ttm_shallow"):
        sub = df[(df["view"] == view) & (df["metric"] == "fcf_ps") & (df["is_flip"])]
        if sub.empty: continue
        sub = sub.sort_values("flip_magnitude", ascending=False).head(25)
        sub = sub[["ticker", "n_history", "prior_q_used", "recent_q_used",
                   "prior_mean", "recent_mean", "flip_magnitude", "latest_value"]].copy()
        for c in ("prior_mean", "recent_mean", "flip_magnitude", "latest_value"):
            sub[c] = sub[c].astype(float).round(3)
        for c in ("n_history", "prior_q_used", "recent_q_used"):
            sub[c] = sub[c].astype(int)
        print(f"\n  --- {view}  (FCF/share confirmed flips: {len(df[(df['view']==view) & (df['metric']=='fcf_ps') & (df['is_flip'])])}) ---")
        print(_fmt(sub.set_index("ticker")))


def negative_ev(results_dir: Path) -> None:
    p = results_dir / "deep_value_screen.csv"
    if not p.exists(): return
    df = pd.read_csv(p, index_col=0)
    neg = df[df["is_negative_ev"]].sort_values("enterprise_value")
    if neg.empty:
        print("\n[negative EV: 0 names]"); return
    print("\n" + "=" * 90)
    print(f"NEGATIVE ENTERPRISE VALUE  ({len(neg)} names)")
    print("=" * 90)
    cols = [c for c in ("enterprise_value", "market_cap", "ncav_per_share",
                         "price_to_ncav", "n_variants_inflected",
                         "is_value_plus_inflection") if c in neg.columns]
    sub = neg[cols].head(30).copy()
    for c in ("enterprise_value", "market_cap", "ncav_per_share"):
        if c in sub: sub[c] = pd.to_numeric(sub[c], errors="coerce").apply(
            lambda x: f"{x:.2e}" if pd.notna(x) else "nan")
    if "price_to_ncav" in sub:
        sub["price_to_ncav"] = pd.to_numeric(sub["price_to_ncav"], errors="coerce").round(2)
    if "n_variants_inflected" in sub:
        sub["n_variants_inflected"] = sub["n_variants_inflected"].astype(int)
    print(_fmt(sub))


def net_nets(results_dir: Path) -> None:
    p = results_dir / "deep_value_screen.csv"
    if not p.exists(): return
    df = pd.read_csv(p, index_col=0)
    nn = df[df["is_net_net"]].copy()
    if nn.empty:
        print("\n[net-nets: 0 names]"); return
    nn["price_to_ncav"] = pd.to_numeric(nn["price_to_ncav"], errors="coerce")
    nn = nn.sort_values("price_to_ncav")
    strict = nn[nn["is_strict_net_net"]]
    print("\n" + "=" * 90)
    print(f"GRAHAM NET-NETS  ({len(nn)} names; {len(strict)} STRICT P<2/3 NCAV)")
    print("=" * 90)
    cols = [c for c in ("price_to_ncav", "ncav_per_share", "market_cap",
                         "enterprise_value", "is_strict_net_net",
                         "n_variants_inflected", "is_value_plus_inflection")
            if c in nn.columns]
    sub = nn[cols].head(30).copy()
    for c in ("ncav_per_share", "market_cap", "enterprise_value"):
        if c in sub: sub[c] = pd.to_numeric(sub[c], errors="coerce").apply(
            lambda x: f"{x:.2e}" if pd.notna(x) else "nan")
    if "price_to_ncav" in sub:
        sub["price_to_ncav"] = sub["price_to_ncav"].round(2)
    if "n_variants_inflected" in sub:
        sub["n_variants_inflected"] = sub["n_variants_inflected"].astype(int)
    print(_fmt(sub))


def cheap_inflecting(results_dir: Path) -> None:
    p = results_dir / "valuation_screen.csv"
    if not p.exists(): return
    df = pd.read_csv(p, index_col=0)
    if "is_cheap_inflecting" not in df.columns: return
    hits = df[df["is_cheap_inflecting"]].sort_values(["pb_pct", "ps_pct"])
    if hits.empty:
        print("\n[cheap + inflecting: 0 names]"); return
    print("\n" + "=" * 90)
    print(f"CHEAP (P/B + P/S) AND INFLECTING  ({len(hits)} names)")
    print("=" * 90)
    cols = [c for c in ("info_priceToBook", "info_priceToSalesTrailing12Months",
                         "pb_pct", "ps_pct", "n_variants_inflected") if c in hits.columns]
    sub = hits[cols].head(30).copy()
    if "info_priceToBook" in sub:
        sub["info_priceToBook"] = pd.to_numeric(sub["info_priceToBook"], errors="coerce").round(2)
    if "info_priceToSalesTrailing12Months" in sub:
        sub["info_priceToSalesTrailing12Months"] = pd.to_numeric(
            sub["info_priceToSalesTrailing12Months"], errors="coerce").round(2)
    for c in ("pb_pct", "ps_pct"):
        if c in sub: sub[c] = pd.to_numeric(sub[c], errors="coerce").round(1)
    if "n_variants_inflected" in sub:
        sub["n_variants_inflected"] = sub["n_variants_inflected"].astype(int)
    print(_fmt(sub))


def deep_value_plus_inflection(results_dir: Path) -> None:
    p = results_dir / "deep_value_screen.csv"
    if not p.exists(): return
    df = pd.read_csv(p, index_col=0)
    combo = df[df["is_value_plus_inflection"]].copy()
    if combo.empty:
        print("\n[deep-value + inflection: 0 names]"); return
    combo["price_to_ncav"] = pd.to_numeric(combo["price_to_ncav"], errors="coerce")
    combo = combo.sort_values(["is_strict_net_net", "is_negative_ev",
                                "n_variants_inflected", "price_to_ncav"],
                               ascending=[False, False, False, True])
    print("\n" + "=" * 90)
    print(f"DEEP VALUE + INFLECTION  ({len(combo)} names)")
    print("(negative EV OR net-net) AND inflecting in >= 2 of 8 variants")
    print("=" * 90)
    cols = [c for c in ("is_negative_ev", "is_net_net", "is_strict_net_net",
                         "enterprise_value", "price_to_ncav",
                         "n_variants_inflected") if c in combo.columns]
    sub = combo[cols].head(30).copy()
    if "enterprise_value" in sub:
        sub["enterprise_value"] = pd.to_numeric(sub["enterprise_value"], errors="coerce").apply(
            lambda x: f"{x:.2e}" if pd.notna(x) else "nan")
    if "price_to_ncav" in sub:
        sub["price_to_ncav"] = sub["price_to_ncav"].round(2)
    if "n_variants_inflected" in sub:
        sub["n_variants_inflected"] = sub["n_variants_inflected"].astype(int)
    print(_fmt(sub))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", type=Path, default=Path("results_expanded"))
    args = p.parse_args(argv)
    if not args.results_dir.exists():
        print(f"results dir not found: {args.results_dir}")
        return 1
    coverage(args.results_dir)
    underreaction_to_appreciation(args.results_dir)
    fcf_inflections(args.results_dir)
    negative_ev(args.results_dir)
    net_nets(args.results_dir)
    cheap_inflecting(args.results_dir)
    deep_value_plus_inflection(args.results_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
