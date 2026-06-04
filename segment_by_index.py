"""Segment global_equities_consolidated by Wikipedia index membership.

Filters the cross-universe CSV against named-index ticker lists from
Wikipedia (S&P 500, NDX, FTSE 100/250, DAX/MDAX, CAC 40, MIB, AEX,
OMXS30, STOXX 50, ASX 50/200, NIFTY 50, KOSPI 200, HSI). Surfaces
coverage gaps (named index members missing from our cache) plus
per-index top setups by Minervini + AQR + TD.
"""

import sys, warnings
warnings.filterwarnings("ignore")

import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from scan_failed_bearish import get_universe, _WIKI_INDEX_SPEC

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 280)
pd.set_option("display.float_format", "{:.2f}".format)

df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
# Boolean casting
bool_cols = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
             'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume',
             'mv_buyable_gap_up','mv_at_ath','mv_in_buy_zone','mv_at_pivot',
             'mv_pocket_pivot','mv_stage2_pass','mv_stage4_pass',
             'mv_climax_top_warning']
for c in bool_cols:
    if c in df.columns:
        df[c] = df[c].astype(str).str.lower().isin(["true", "1", "yes"])
num_cols = [c for c in df.columns if c not in (
    "name","sector","_universe","fb_lists","tags",
    "h_d_pattern","h_d_direction","h_w_pattern","h_w_direction",
    "h_m_pattern","h_m_direction","_cap") and c not in bool_cols]
for c in num_cols:
    if df[c].dtype == "object":
        df[c] = pd.to_numeric(df[c], errors="coerce")

print(f"Total flagged global rows: {len(df)}")
print()
print(f"{'Index':14s} {'Members':>8s} {'In CSV':>8s} {'Gap %':>7s} {'Prem':>6s} {'Pwr':>6s} {'TightW':>7s} {'ATH':>5s}  Top 3 by mv_composite_score")
print("-" * 140)

results = []
for name in _WIKI_INDEX_SPEC.keys():
    try:
        idx = get_universe(name)
    except Exception:
        continue
    members = list(idx.index)
    n_members = len(members)
    if n_members == 0:
        continue
    sub = df.loc[df.index.intersection(members)]
    n_in = len(sub)
    gap_pct = (1 - n_in / n_members) * 100 if n_members else 0
    prem = int(sub.get("mv_setup_premium", pd.Series(dtype=bool)).sum()) if "mv_setup_premium" in sub.columns else 0
    pwr = int(sub.get("mv_power_trend", pd.Series(dtype=bool)).sum()) if "mv_power_trend" in sub.columns else 0
    tight = int(sub.get("mv_3w_tight", pd.Series(dtype=bool)).sum()) if "mv_3w_tight" in sub.columns else 0
    ath = int(sub.get("mv_at_ath", pd.Series(dtype=bool)).sum()) if "mv_at_ath" in sub.columns else 0
    if "mv_composite_score" in sub.columns and len(sub):
        top3 = sub.nlargest(3, "mv_composite_score").index.tolist()
    else:
        top3 = []
    print(f"{name:14s} {n_members:>8d} {n_in:>8d} {gap_pct:>6.1f}% {prem:>6d} {pwr:>6d} {tight:>7d} {ath:>5d}  {', '.join(top3)}")
    results.append({
        "index": name,
        "members": n_members,
        "in_csv": n_in,
        "gap_pct": gap_pct,
        "premium": prem,
        "power_trend": pwr,
        "tight": tight,
        "at_ath": ath,
    })

# Per-index details: top 10 each for the high-value indexes
detail_cols = ["name", "sector", "last_close", "mv_composite_score",
               "mv_power_trend", "mv_3w_tight", "mv_at_ath", "aqr_trend_score",
               "td_mtf_composite", "rs_rank_max", "ma_d50_strategy_ir"]
detail_cols = [c for c in detail_cols if c in df.columns]

for name in ["wiki-spx500", "wiki-ndx", "wiki-djia", "wiki-ftse100", "wiki-ftse250",
             "wiki-dax", "wiki-mdax", "wiki-cac40", "wiki-mib", "wiki-aex",
             "wiki-stoxx50"]:
    try:
        idx = get_universe(name)
    except Exception:
        continue
    sub = df.loc[df.index.intersection(idx.index)]
    if len(sub) == 0:
        continue
    print()
    print("=" * 78)
    print(f"{name.upper()} top 10 by Minervini composite (of {len(sub)})")
    print("=" * 78)
    if "mv_composite_score" in sub.columns:
        top = sub.nlargest(10, "mv_composite_score")
    else:
        top = sub.head(10)
    print(top[detail_cols].to_string())

# Save the per-index summary
pd.DataFrame(results).to_csv("wiki_index_coverage.csv", index=False)
print()
print("Wrote wiki_index_coverage.csv")
