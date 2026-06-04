"""Consolidate equity universes into one global ranking.

Joins us-all + uk-all + de-all + it-all + br-all + eu-smid into a single
DataFrame, tags each row with its source universe, and surfaces the
most-asymmetric bullish and bearish names by td_mtf_composite across
the global equity universe.

ETF universes are intentionally excluded — they're macro context only.
"""

import glob
from pathlib import Path
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 280)
pd.set_option("display.float_format", "{:.2f}".format)


EQUITY_UNIVERSES = [
    # Original 6
    "us-all", "uk-all", "de-all", "it-all", "br-all", "eu-smid",
    # Widened additions (Wave 1-4)
    "fr-all", "ch-all", "es-all", "nl-all",
    "se-all", "be-all", "no-all", "dk-all", "fi-all",
    "ie-all", "pt-all", "at-all", "gr-all",
    "jp-all", "au-all", "ca-all", "mx-all", "za-all",
    "in-all", "hk-all", "cn-all", "kr-all", "tw-all", "sg-all",
]


def latest_csv(universe):
    files = sorted(glob.glob(f"momentum_rank_{universe}_*.csv"))
    return files[-1] if files else None


frames = []
for u in EQUITY_UNIVERSES:
    path = latest_csv(u)
    if not path:
        print(f"  {u}: no CSV found")
        continue
    df = pd.read_csv(path, index_col=0)
    df["_universe"] = u
    print(f"  {u}: {len(df)} rows from {path}")
    frames.append(df)

if not frames:
    raise SystemExit("no CSVs to merge")

all_eq = pd.concat(frames)
print(f"\nTotal global equity rows: {len(all_eq)}")
print(f"Unique tickers: {all_eq.index.nunique()}")

# Drop duplicate listings (same company listed on multiple exchanges, e.g.,
# 0NFS.L = Esprinet on London listing of PRT.MI). Keep the one with the
# strongest td_mtf_composite magnitude.
if "td_mtf_composite" in all_eq.columns:
    all_eq["_abs_comp"] = all_eq["td_mtf_composite"].abs()
    all_eq = all_eq.sort_values("_abs_comp", ascending=False)
    # Don't dedupe by index — same ticker on different exchanges might be
    # distinct rows; this is intentional. But surface bull/bear separately.

cols = ["name", "_universe", "sector", "last_close", "rs_rank_max",
        "td_mtf_composite", "td_mtf_net_setup", "td_mtf_net_cd",
        "td_mtf_net_perfect", "td_mtf_net_triple",
        "td_w_buy_setup", "td_w_sell_setup",
        "td_w_buy_cd", "td_w_sell_cd",
        "td_m_buy_setup", "td_m_sell_setup",
        "td_m_buy_cd", "td_m_sell_cd",
        "aqr_trend_score", "aqr_trend_1m", "aqr_trend_3m",
        "aqr_trend_6m", "aqr_trend_12m",
        "ma_d50_respect_ratio", "ma_d50_slope_pct_wk",
        "ma_d50_vol_asym_near", "ma_d50_spring_k",
        "ma_d50_days_above", "ma_d50_strategy_ir",
        "ma_w10_respect_ratio", "ma_w10_slope_pct_wk", "ma_w10_strategy_ir",
        "mv_stage2_count", "mv_stage2_pass", "mv_vcp_count", "mv_vcp_setup",
        "mv_tight_close_5d", "mv_closes_top_half_20d",
        "mv_dist_to_pivot_pct", "mv_at_pivot", "mv_pocket_pivot",
        "mv_composite_score", "mv_setup_clean",
        "roque_score", "mom_3m", "mom_6m",
        "box_length_weeks", "pos_in_box_pct"]
cols = [c for c in cols if c in all_eq.columns]

bull = all_eq[all_eq["td_mtf_composite"].notna()].sort_values(
    "td_mtf_composite", ascending=False).head(50)
bear = all_eq[all_eq["td_mtf_composite"].notna()].sort_values(
    "td_mtf_composite", ascending=True).head(50)

print(f"\n{'='*15} TOP 50 MOST ASYMMETRIC BULLISH EQUITIES (global) {'='*15}")
print(bull[cols].to_string())

print(f"\n{'='*15} TOP 50 MOST ASYMMETRIC BEARISH EQUITIES (global) {'='*15}")
print(bear[cols].to_string())

print(f"\n=== Universe distribution in top 50 each ===")
print("BULL:", bull["_universe"].value_counts().to_dict())
print("BEAR:", bear["_universe"].value_counts().to_dict())

# Sector tilts
print(f"\n=== Sector tilt in top 50 each ===")
if "sector" in bull.columns:
    print("BULL:", bull["sector"].value_counts().head(8).to_dict())
    print("BEAR:", bear["sector"].value_counts().head(8).to_dict())

# Save consolidated
out_path = "global_equities_consolidated.csv"
all_eq.drop(columns=["_abs_comp"], errors="ignore").to_csv(out_path)
print(f"\nGlobal consolidated equities CSV: {out_path} ({len(all_eq)} rows)")
