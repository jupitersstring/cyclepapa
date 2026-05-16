"""Asymmetry ranker over the existing snapshots.

Combines the Yartseva (multibagger / inflection) score, Berezin (microcap
deep value) score, cluster-signal count and 12-month momentum to compute an
UPSIDE_SCORE, alongside a DOWNSIDE_FLOOR_SCORE built from cash > EV /
Graham net-net / sub-book / profitability / low debt / net cash / insider
ownership.

Asymmetry = sqrt(upside * downside_floor) — geometric mean so both legs
must be present.

Usage:
    python asymmetry_rank.py \
        --csvs italian_yartseva.csv:IT us_nano_micro_small_yartseva.csv:US pew_global.csv:PEW \
        --out asymmetry_shortlist.csv \
        --min-mcap 10000000 \
        --top 60

Filters out pharma/biotech/healthcare and the obvious yfinance placeholder
junk ("one", "two", "three", NaN names).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def is_pharma_bio(row) -> bool:
    s = str(row.get("sector", "")); ind = str(row.get("industry", "")); nm = str(row.get("name", ""))
    if "health" in s.lower():
        return True
    for k in ["biotech", "pharma", "drug", "biolog", "medic", "therapeut", "diagnos"]:
        if k in ind.lower() or k in nm.lower():
            return True
    return False


def load_concat(csv_specs: list[str]) -> pd.DataFrame:
    frames = []
    for spec in csv_specs:
        if ":" in spec:
            path, src = spec.split(":", 1)
        else:
            path, src = spec, Path(spec).stem
        d = pd.read_csv(path)
        d["src"] = src
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def compute_asymmetry(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure all signal columns exist; missing ones become NaN.
    needed = [
        "cash_gt_ev_flag", "graham_net_net_flag",
        "berezin_score", "berezin_classic_flag",
        "net_cash_pct_mcap", "cash_pct_ev", "insider_ownership_pct",
        "pb", "p_s", "debt_to_equity", "gross_profit_to_mcap", "momentum_12m",
        "yartseva_score", "rev_accel",
        "fcf_first_positive", "ebitda_first_positive", "cfo_first_positive",
        "net_income_first_positive", "roce_inflection", "roce_first_positive",
        "fcf_projected_positive_in_n",
        "rev_inflection", "ebitda_inflection", "fcf_inflection",
        "cheapness_under_7x_flag", "not_priced_in_score",
        "ebitda_margin", "net_debt_ebitda",
    ]
    for c in needed:
        if c not in df.columns:
            df[c] = np.nan

    # ----- UPSIDE leg -----
    df["u_yart"] = df["yartseva_score"].fillna(0).clip(0, 1)
    df["u_berez"] = df["berezin_score"].fillna(0).clip(0, 1)

    sig = pd.DataFrame({
        "cheap_under_7x":  df["cheapness_under_7x_flag"].fillna(0).astype(int) == 1,
        "first_positive":  (
            (df["fcf_first_positive"] == 1) | (df["ebitda_first_positive"] == 1)
            | (df["cfo_first_positive"] == 1) | (df["net_income_first_positive"] == 1)
        ).fillna(False),
        "roce_inflect":    ((df["roce_inflection"] == 1) | (df["roce_first_positive"] == 1)).fillna(False),
        "fcf_eta_4q":      df["fcf_projected_positive_in_n"].fillna(0).astype(int) == 1,
        "growth_inflect":  (
            (df["rev_inflection"] == 1) | (df["ebitda_inflection"] == 1) | (df["fcf_inflection"] == 1)
        ).fillna(False),
        "accel_sales":     df["rev_accel"].fillna(-1) > 0.05,
        "not_priced_in":   df["not_priced_in_score"].fillna(-99) > 0.10,
    })
    df["cluster_n"] = sig.sum(axis=1).values
    df["u_cluster"] = (df["cluster_n"] / 7.0).clip(0, 1)
    df["u_accel"] = ((df["rev_accel"].fillna(-1) + 0.05) / 0.40).clip(0, 1)
    df["u_mom"] = ((df["momentum_12m"].fillna(-1) + 0.10) / 0.60).clip(0, 1)

    upside_weights = dict(u_yart=0.28, u_berez=0.18, u_cluster=0.26, u_accel=0.14, u_mom=0.14)
    df["upside_score"] = sum(upside_weights[k] * df[k] for k in upside_weights)

    # ----- DOWNSIDE FLOOR leg -----
    df["d_cash_ev"] = df["cash_gt_ev_flag"].fillna(0).astype(int)
    df["d_graham"] = df["graham_net_net_flag"].fillna(0).astype(int)
    df["d_sub_book"] = ((df["pb"].fillna(99) > 0) & (df["pb"].fillna(99) < 1.0)).astype(int)
    df["d_profitable"] = (df["ebitda_margin"].fillna(-1) > 0.05).astype(int)
    df["d_low_debt"] = (
        (df["net_debt_ebitda"].fillna(99) < 1.5) | (df["debt_to_equity"].fillna(99) < 0.5)
    ).astype(int)
    df["d_net_cash"] = (df["net_cash_pct_mcap"].fillna(-1) > 0).astype(int)
    df["d_insider"] = (df["insider_ownership_pct"].fillna(0) >= 0.20).astype(int)

    downside_weights = dict(
        d_cash_ev=0.22, d_graham=0.18, d_sub_book=0.12, d_profitable=0.12,
        d_low_debt=0.12, d_net_cash=0.10, d_insider=0.14,
    )
    df["downside_floor_score"] = sum(downside_weights[k] * df[k] for k in downside_weights)

    # Geometric mean penalises when either leg is weak
    df["asymmetry_score"] = np.sqrt(
        df["upside_score"].clip(0, 1) * df["downside_floor_score"].clip(0, 1)
    )
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csvs", nargs="+", required=True,
                   help='input CSVs, optionally with :SRC tag (e.g. italian_yartseva.csv:IT)')
    p.add_argument("--out", default="asymmetry_shortlist.csv")
    p.add_argument("--min-mcap", type=float, default=10_000_000)
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--min-upside", type=float, default=0.35)
    p.add_argument("--min-downside-floor", type=float, default=0.20)
    args = p.parse_args()

    df = load_concat(args.csvs)
    print(f"loaded: {len(df)}", file=sys.stderr)

    df["name_str"] = df["name"].astype(str).str.lower().str.strip()
    df = df[
        (df["name_str"] != "nan")
        & (~df["name_str"].isin(["one", "two", "three", "nan", ""]))
        & (df["name_str"].str.len() > 3)
        & (df["market_cap"].fillna(0) >= args.min_mcap)
    ]
    df = df[~df.apply(is_pharma_bio, axis=1)].copy()
    print(f"after filters: {len(df)}", file=sys.stderr)

    df = compute_asymmetry(df)

    keep = df[
        (df["upside_score"] >= args.min_upside)
        & (df["downside_floor_score"] >= args.min_downside_floor)
    ].sort_values("asymmetry_score", ascending=False)

    out_cols = [
        "symbol", "name", "src", "sector", "industry", "market_cap",
        "asymmetry_score", "upside_score", "downside_floor_score", "cluster_n",
        "yartseva_score", "berezin_score",
        "cash_gt_ev_flag", "graham_net_net_flag",
        "pb", "ebitda_margin", "net_debt_ebitda",
        "insider_ownership_pct", "momentum_12m", "notes",
    ]
    out_cols = [c for c in out_cols if c in keep.columns]
    keep[out_cols].to_csv(args.out, index=False)
    print(f"wrote {len(keep)} rows -> {args.out}", file=sys.stderr)

    pd.set_option("display.width", 280)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    pd.set_option("display.max_colwidth", 48)
    print(f"\n=== TOP {args.top} BY ASYMMETRY (sqrt(upside * downside_floor)) ===")
    print(keep.head(args.top)[out_cols].to_string(index=False))


if __name__ == "__main__":
    main()
