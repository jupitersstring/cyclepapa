"""Asymmetry ranker over the existing snapshots.

Combines every scoring layer we have into a single asymmetric-payoff view:

  Yartseva (multibagger / inflection) score
  Berezin (microcap deep value) score
  Cluster-signal count (7 inflection / cheapness flags)
  12-month momentum
  PEW signals (insider ownership, forgotten score, platform/SaaS hint)

into UPSIDE_SCORE, and a DOWNSIDE_FLOOR_SCORE built from:

  cash > EV / Graham net-net / sub-book / profitable / low debt /
  net cash / insider ownership.

Asymmetry = sqrt(upside * downside_floor) — geometric mean so both
legs must be present. PEW CSV is merged in by symbol so US/UK/DE
names that ran on the old yartseva schema still get insider /
forgotten / platform fields populated.

Usage:
    python asymmetry_rank.py \
        --csvs italian_yartseva.csv:IT us_nano_micro_small_yartseva.csv:US \
        --pew pew_global.csv \
        --out asymmetry_shortlist.csv \
        --min-mcap 10000000 \
        --top 60
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


def merge_pew_signals(df: pd.DataFrame, pew_csv: str) -> pd.DataFrame:
    """Bring PEW-specific signals (insider %, forgotten, platform hits, ncav
    etc.) into the main frame by symbol. Yartseva fields take priority when
    present (Italy has the latest schema); PEW backfills the rest."""
    try:
        p = pd.read_csv(pew_csv)
    except Exception as e:
        print(f"could not read PEW csv {pew_csv}: {e}", file=sys.stderr)
        return df
    keep_p = [
        "symbol", "insider_ownership_pct", "forgotten_score",
        "platform_hits", "has_platform_hint", "ncav_pct_mcap",
        "negative_ev_flag", "below_net_cash_flag",
        "rev_3y_cagr", "is_breakeven_or_profitable",
    ]
    keep_p = [c for c in keep_p if c in p.columns]
    p = p[keep_p].rename(columns={c: f"pew_{c}" for c in keep_p if c != "symbol"})
    df = df.merge(p, on="symbol", how="left")

    # Fill any missing yartseva-side fields with the PEW backfill so the
    # downside/upside legs can use them universally.
    for fld_y, fld_p in [
        ("insider_ownership_pct", "pew_insider_ownership_pct"),
        ("ncav_pct_mcap", "pew_ncav_pct_mcap"),
    ]:
        if fld_y in df.columns and fld_p in df.columns:
            df[fld_y] = df[fld_y].fillna(df[fld_p])
        elif fld_p in df.columns:
            df[fld_y] = df[fld_p]
    return df


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
        # PEW-derived (merged in)
        "pew_forgotten_score", "pew_platform_hits", "pew_has_platform_hint",
        "pew_negative_ev_flag", "pew_below_net_cash_flag",
        "pew_rev_3y_cagr", "pew_is_breakeven_or_profitable",
    ]
    for c in needed:
        if c not in df.columns:
            df[c] = np.nan

    # Helpful: when a name was breakeven-or-profitable per PEW but yartseva
    # didn't record ebitda_margin (sparse data on EU smid-caps), respect it.
    df["ebitda_positive_proxy"] = np.where(
        df["ebitda_margin"].fillna(-1) > 0.05, 1,
        np.where(df["pew_is_breakeven_or_profitable"].fillna(0).astype(int) == 1, 1, 0),
    )

    # 3y revenue CAGR from PEW (multi-year growth alternative to YoY)
    df["rev_3y_cagr"] = df.get("rev_3y_cagr", df.get("pew_rev_3y_cagr"))
    if "pew_rev_3y_cagr" in df.columns:
        df["rev_3y_cagr"] = df["rev_3y_cagr"].fillna(df["pew_rev_3y_cagr"]) if "rev_3y_cagr" in df.columns else df["pew_rev_3y_cagr"]

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
    df["u_3y_cagr"] = ((df["rev_3y_cagr"].fillna(-1) + 0.05) / 0.30).clip(0, 1)
    df["u_platform"] = df["pew_has_platform_hint"].fillna(0).clip(0, 1)

    # Renormalised: only the components that are present contribute. This
    # stops names with no Berezin / no PEW from being unfairly penalised
    # vs. names that have all signals.
    upside_components = {
        "u_yart":     ("yartseva_score",  0.22),
        "u_berez":    ("berezin_score",   0.14),
        "u_cluster":  (None,              0.22),   # always present
        "u_accel":    ("rev_accel",       0.10),
        "u_mom":      ("momentum_12m",    0.10),
        "u_3y_cagr":  ("rev_3y_cagr",     0.12),
        "u_platform": (None,              0.10),   # always 0/1 from PEW, default 0
    }
    df = _weighted_renormalised(df, upside_components, out_col="upside_score")

    # ----- DOWNSIDE FLOOR leg -----
    df["d_cash_ev"] = df["cash_gt_ev_flag"].fillna(0).astype(int)
    df["d_graham"] = df["graham_net_net_flag"].fillna(0).astype(int)
    df["d_sub_book"] = ((df["pb"].fillna(99) > 0) & (df["pb"].fillna(99) < 1.0)).astype(int)
    df["d_profitable"] = df["ebitda_positive_proxy"]
    df["d_low_debt"] = (
        (df["net_debt_ebitda"].fillna(99) < 1.5) | (df["debt_to_equity"].fillna(99) < 0.5)
    ).astype(int)
    df["d_net_cash"] = (df["net_cash_pct_mcap"].fillna(-1) > 0).astype(int)
    df["d_insider"] = (df["insider_ownership_pct"].fillna(0) >= 0.20).astype(int)
    df["d_forgotten"] = (df["pew_forgotten_score"].fillna(0) >= 0.50).astype(int)
    df["d_pew_negev"] = df["pew_negative_ev_flag"].fillna(0).astype(int)

    downside_components = {
        "d_cash_ev":    (None, 0.18),
        "d_graham":     (None, 0.14),
        "d_pew_negev":  (None, 0.10),
        "d_sub_book":   (None, 0.10),
        "d_profitable": (None, 0.12),
        "d_low_debt":   (None, 0.10),
        "d_net_cash":   (None, 0.10),
        "d_insider":    (None, 0.10),
        "d_forgotten":  (None, 0.06),
    }
    df = _weighted_renormalised(df, downside_components, out_col="downside_floor_score")

    df["asymmetry_score"] = np.sqrt(
        df["upside_score"].clip(0, 1) * df["downside_floor_score"].clip(0, 1)
    )
    return df


def _weighted_renormalised(df: pd.DataFrame, components: dict, out_col: str) -> pd.DataFrame:
    """For each row, only weights of components whose source field is present
    contribute (so missing-data names aren't unfairly penalised). When
    source_field is None, the score column is treated as always available."""
    score = np.zeros(len(df), dtype=float)
    weight_sum = np.zeros(len(df), dtype=float)
    for col, (source_field, w) in components.items():
        if col not in df.columns:
            continue
        if source_field is None:
            avail_mask = np.ones(len(df), dtype=bool)
        else:
            if source_field not in df.columns:
                continue
            avail_mask = df[source_field].notna().values
        vals = df[col].fillna(0.0).values
        score += np.where(avail_mask, w * vals, 0.0)
        weight_sum += np.where(avail_mask, w, 0.0)
    # Avoid divide-by-zero when all components missing
    df[out_col] = np.where(weight_sum > 0, score / weight_sum, np.nan)
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csvs", nargs="+", required=True,
                   help='input CSVs, optionally with :SRC tag (e.g. italian_yartseva.csv:IT)')
    p.add_argument("--pew", default=None,
                   help="PEW global CSV to merge in (insider, forgotten, platform hints)")
    p.add_argument("--out", default="asymmetry_shortlist.csv")
    p.add_argument("--min-mcap", type=float, default=10_000_000)
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--min-upside", type=float, default=0.35)
    p.add_argument("--min-downside-floor", type=float, default=0.20)
    p.add_argument("--buckets", default="",
                   help=("optional comma-separated whitelist of financedatabase "
                         "market_cap buckets to keep (e.g. 'Nano Cap,Micro Cap,Small Cap'). "
                         "Empty = keep all."))
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
    if args.buckets and "market_cap_bucket" in df.columns:
        keep_buckets = {b.strip() for b in args.buckets.split(",") if b.strip()}
        before = len(df)
        df = df[df["market_cap_bucket"].isin(keep_buckets)]
        print(f"bucket filter ({sorted(keep_buckets)}): {before} -> {len(df)}", file=sys.stderr)
    print(f"after filters: {len(df)}", file=sys.stderr)

    if args.pew:
        df = merge_pew_signals(df, args.pew)
        print(f"PEW signals merged from {args.pew}", file=sys.stderr)

    df = compute_asymmetry(df)

    keep = df[
        (df["upside_score"] >= args.min_upside)
        & (df["downside_floor_score"] >= args.min_downside_floor)
    ].sort_values("asymmetry_score", ascending=False)

    out_cols = [
        "symbol", "name", "src", "sector", "industry", "market_cap_bucket",
        "market_cap", "asymmetry_score", "upside_score", "downside_floor_score",
        "cluster_n", "yartseva_score", "berezin_score",
        "cash_gt_ev_flag", "graham_net_net_flag", "pew_negative_ev_flag",
        "pb", "ebitda_margin", "ebitda_positive_proxy", "net_debt_ebitda",
        "insider_ownership_pct", "pew_forgotten_score", "pew_has_platform_hint",
        "rev_3y_cagr", "momentum_12m", "notes",
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
