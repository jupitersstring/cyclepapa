"""Global best across the universe — counts independent MEASURE confirmations only.

Only counts sheets from all_measures.xlsx which represent distinct
measure families (MA-respect, Roque, Q-method, Squeeze, TD per-TF,
Darvas, Harmonic, Vol Drying, etc.). Excludes derivative/nested
screens like 'Pre-Run Top 100' which inherit from the underlying
regional cuts.

Outputs:
  global_best.xlsx
    - True Global Best (any ADV)       top N by independent measure count
    - Tradeable Global ($20M USD ADV)  same, USD-ADV filtered
    - Institutional Global ($100M+)    higher ADV floor
    - Best US/UK/EU/ASIA/LATAM/CA/OCEANIA/AFRICA  per-region with USD ADV
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from collections import defaultdict


# Sheets in all_measures.xlsx that ARE INDEPENDENT measures
# (each represents a different technical family)
INDEPENDENT_MEASURE_SHEETS = [
    "MA50d Strategy IR", "MA50d Respect Ratio", "MA50d Vol-Asym Near",
    "MA200d Strategy IR", "MA200d Respect Ratio", "MA200d Vol-Asym Near",
    "MA10w Strategy IR", "MA10w Respect Ratio", "MA10w Vol-Asym Near",
    "Roque Score Leaders", "Roque >= 9",
    "Q Method Pass", "Q Method Monthly Strong", "Q Score Best (low=best)",
    "Rel Asym Score Leaders", "Weekly Asym Above MA", "Daily Asym Just Crossed Up",
    "Weekly Squeeze Just Release", "Monthly Squeeze Just Release",
    "Breakout Squeeze (strict)",
    "Weekly TD9 Buy Setup", "Monthly TD13 Buy CD Complete",
    "Rel-SPY Weekly TD Net Setup", "TD MTF Asymmetry", "TD Exhaustion Bull",
    "Longest Darvas Box", "Darvas Tight Bases", "Near Box Top (pre-breakout)",
    "Harmonic Daily Quality", "Harmonic Weekly Quality", "Harmonic Monthly Quality",
    "Harmonic Multi-TF Consonance", "Harmonic Bullish W or M",
    "Rel-SPY 6m Outperformers", "Rel-SPY Far Above 30wma",
    "RS Rank Max Leaders", "ATR_RS Leaders", "200dma Slope Leaders",
    "Vol Drying (lowest ratio)",
]

# ============================================================
# 1. Tally measure appearances
# ============================================================
ticker_to_measures = defaultdict(set)
ticker_to_categories = defaultdict(set)  # broader family category

def categorize(sheet):
    s = sheet
    if s.startswith("MA"): return "MA-respect"
    if s.startswith("Roque"): return "Roque"
    if s.startswith("Q "): return "Q-method"
    if "Asym" in s: return "Vol-asymmetry"
    if "Squeeze" in s: return "Squeeze"
    if "TD" in s or "Rel-SPY Weekly TD" in s: return "TD-Sequential"
    if "Darvas" in s or "Box Top" in s: return "Darvas"
    if "Harmonic" in s: return "Harmonic"
    if "Rel-SPY" in s: return "Relative-to-SPY"
    if "RS Rank" in s or "ATR_RS" in s or "200dma" in s: return "RS/Trend"
    if "Vol Drying" in s: return "Vol-Drying"
    return "Other"

xls = pd.ExcelFile("all_measures.xlsx")
for sh in INDEPENDENT_MEASURE_SHEETS:
    if sh not in xls.sheet_names:
        continue
    df = pd.read_excel("all_measures.xlsx", sheet_name=sh)
    tcol = "Ticker" if "Ticker" in df.columns else df.columns[0]
    for tkr in df[tcol].dropna().astype(str):
        if not tkr or tkr.lower() == "nan":
            continue
        ticker_to_measures[tkr].add(sh)
        ticker_to_categories[tkr].add(categorize(sh))

print(f"Tallied {len(ticker_to_measures)} unique tickers across "
       f"{sum(1 for s in INDEPENDENT_MEASURE_SHEETS if s in xls.sheet_names)} independent measure sheets")

n_measures = {t: len(s) for t, s in ticker_to_measures.items()}
n_categories = {t: len(c) for t, c in ticker_to_categories.items()}
measure_list = {t: "; ".join(sorted(s)) for t, s in ticker_to_measures.items()}
category_list = {t: ", ".join(sorted(c)) for t, c in ticker_to_categories.items()}


# ============================================================
# 2. Join with consolidated CSV
# ============================================================
df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
bools = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
         'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume',
         'mv_buyable_gap_up','mv_at_ath','mv_in_buy_zone','mv_at_pivot',
         'mv_pocket_pivot','mv_stage2_pass','mv_stage4_pass',
         'mv_climax_top_warning','q_method_pass','base_ready','prebreakout_w',
         'long_base','darvas_tight','asym_w_above_ma','sq_w_just_release',
         'sq_m_just_release','harmonic_bullish_w_or_m','macd_above_signal',
         'extended_w','base_forming','very_long_base','base_on_base',
         'near_box_top','box_breakout','consolidating','vol_drying','uptrend_w',
         'tight_base_w']
for c in bools:
    if c in df.columns:
        df[c] = df[c].astype(str).str.lower().isin(["true","1","yes"])
skip = {"name","sector","_universe","security_type","_ccy","fb_lists","tags",
        "adv_tier","_cap","h_d_pattern","h_d_direction","h_w_pattern",
        "h_w_direction","h_m_pattern","h_m_direction"}
for c in df.columns:
    if c not in skip and c not in bools and df[c].dtype == "object":
        df[c] = pd.to_numeric(df[c], errors="coerce")
df = df.sort_values("mv_composite_score", ascending=False, na_position="last")
df = df[~df.index.duplicated(keep="first")]
if "security_type" in df.columns:
    df = df[df["security_type"] == "common"].copy()
if "adv_20d_usd_millions" in df.columns:
    df["adv_usd_M"] = df["adv_20d_usd_millions"]
else:
    df["adv_usd_M"] = df.get("adv_20d_millions")

EU_UNI = {"de-all","fr-all","ch-all","it-all","es-all","nl-all","se-all","be-all",
          "no-all","dk-all","fi-all","ie-all","pt-all","at-all","gr-all","eu-smid",
          "eu-large","eu-micro","eu-nano"}
ASIA_UNI = {"jp-all","cn-all","kr-all","tw-all","hk-all","in-all","sg-all",
            "th-all","id-all","il-all","sa-all","tr-all"}
LATAM_UNI = {"br-all","mx-all","ar-all","cl-all"}
def region(u):
    if u == "us-all" or u == "wiki-r1k": return "US"
    if u == "uk-all" or u == "wiki-aim100": return "UK"
    if u in EU_UNI: return "EU"
    if u in ASIA_UNI: return "ASIA"
    if u in LATAM_UNI: return "LATAM"
    if u in ("au-all","nz-all"): return "OCEANIA"
    if u == "za-all": return "AFRICA"
    if u == "ca-all": return "CA"
    return "OTHER"
df["region"] = df["_universe"].apply(region)

df["n_measures"] = df.index.map(lambda t: n_measures.get(t, 0))
df["n_categories"] = df.index.map(lambda t: n_categories.get(t, 0))
df["categories"] = df.index.map(lambda t: category_list.get(t, ""))
df["measure_sheets"] = df.index.map(lambda t: measure_list.get(t, ""))

# ============================================================
# 3. Distribution summary
# ============================================================
print()
print(f"Common-equity rows in consolidated: {len(df)}")
print(f"With ADV USD >= $20M:               {(df['adv_usd_M'].fillna(0) >= 20).sum()}")
print(f"With ADV USD >= $100M:              {(df['adv_usd_M'].fillna(0) >= 100).sum()}")
print(f"With ADV USD >= $500M:              {(df['adv_usd_M'].fillna(0) >= 500).sum()}")
print()
print(f"Max independent measures any one ticker hits: {df['n_measures'].max()}")
print(f"n_measures distribution:")
for k, v in df["n_measures"].value_counts().sort_index().items():
    if k >= 1:
        print(f"  {k:>2d} measures: {v:>5d} tickers")
print()
print(f"Max distinct categories (families): {df['n_categories'].max()}")
print(f"n_categories distribution:")
for k, v in df["n_categories"].value_counts().sort_index().items():
    if k >= 1:
        print(f"  {k:>2d} categories: {v:>5d} tickers")


# ============================================================
# 4. Outputs
# ============================================================
COLS = ["name","_universe","region","_ccy","sector","last_close","rs_rank_max",
        "mom_3m","mom_6m","mv_dist_from_ath_pct",
        "aqr_trend_score","td_mtf_composite","mv_composite_score",
        "mv_stage2_count","mv_vcp_count","mv_power_trend","mv_3w_tight",
        "mv_bow_tie","mv_at_ath","adv_usd_M","adv_slope_pct_wk",
        "n_categories","n_measures","categories","measure_sheets"]
COLS = [c for c in COLS if c in df.columns]

sheets = {}

# 1. True global best — most distinct families
sheets["True Global Best (any ADV)"] = df[df["n_measures"] >= 2] \
    .sort_values(["n_categories","n_measures","mv_composite_score"],
                  ascending=False).head(100)[COLS]

# 2. Tradeable cut
sheets["Tradeable ($20M USD ADV)"] = df[(df["n_measures"] >= 2) & (df["adv_usd_M"].fillna(0) >= 20)] \
    .sort_values(["n_categories","n_measures","mv_composite_score"],
                  ascending=False).head(60)[COLS]

# 3. Institutional cut
sheets["Institutional ($100M USD ADV)"] = df[(df["n_measures"] >= 1) & (df["adv_usd_M"].fillna(0) >= 100)] \
    .sort_values(["n_categories","n_measures","mv_composite_score"],
                  ascending=False).head(50)[COLS]

# 4. Mega-liquid
sheets["Mega-Liquid ($500M+ USD ADV)"] = df[df["adv_usd_M"].fillna(0) >= 500] \
    .sort_values(["n_categories","n_measures","mv_composite_score"],
                  ascending=False).head(40)[COLS]

# 5. Per-region with regional ADV floor (lower for thin markets)
for r, floor in [("US",20),("UK",20),("EU",10),("ASIA",5),
                 ("LATAM",1),("OCEANIA",5),("CA",5),("AFRICA",1)]:
    sub = df[(df["region"] == r) & (df["adv_usd_M"].fillna(0) >= floor)]
    if len(sub) < 5:
        sub = df[df["region"] == r]
    sub = sub.sort_values(["n_categories","n_measures","mv_composite_score"], ascending=False)
    sheets[f"Best {r} (ADV>=${floor}M)"] = sub.head(30)[COLS]

# 6. Cross-category "rare" sheets
# Names confirmed by 4+ independent categories (very rare)
rare = df[df["n_categories"] >= 4].sort_values(
    ["n_categories","n_measures","mv_composite_score"], ascending=False)
sheets["Rarest (4+ categories)"] = rare.head(50)[COLS]

# 7. BALANCED BEST: multi-measure confirmed AND not extended AND TD not warning AND liquid
# This is the most actionable single sheet — cross-validated by multiple measure
# families WITHOUT the momentum-extreme bias.
balanced = df[
    (df["n_categories"] >= 2)                          # multi-family confirmed
    & (df["adv_usd_M"].fillna(0) >= 20)                # institutional sizing
    & (df["aqr_trend_score"].fillna(0) >= 0)           # trend not collapsed
    & (df["td_mtf_composite"].fillna(0) >= -0.3)       # TD not warning bearish
    & (df["rs_rank_max"].fillna(100) <= 85)            # RS has room
    & (df["mom_6m"].fillna(2) <= 1.30)                 # mom moderate (<=30% 6m)
    & (df["mv_dist_from_ath_pct"].fillna(0) <= 30)     # within 30% of ATH (not broken)
]
balanced = balanced.sort_values(
    ["n_categories","n_measures","mv_composite_score"], ascending=False)
sheets["Balanced Best (multi-measure + not extended + liquid)"] = balanced.head(60)[COLS]

# 8. MEGA-TRENDING (informational): the extreme momentum names with TD warning
# These are EXHAUSTING trends — sell-side candidates or late longs only
extreme = df[
    (df["n_categories"] >= 3)
    & (df["adv_usd_M"].fillna(0) >= 100)
    & (df["rs_rank_max"].fillna(0) >= 95)
    & (df["aqr_trend_score"].fillna(0) >= 2.5)
    & (df["td_mtf_composite"].fillna(0) <= -0.5)
]
extreme = extreme.sort_values(
    ["aqr_trend_score","mv_composite_score"], ascending=False)
sheets["Mega-Trending Exhausting (sell-side)"] = extreme.head(40)[COLS]

# 9. PRE-RUN MULTI-MEASURE: low RS + many measures + liquid
# Names with multiple-measure confirmation that haven't moved yet
pre_run_multi = df[
    (df["n_categories"] >= 2)
    & (df["adv_usd_M"].fillna(0) >= 20)
    & (df["rs_rank_max"].fillna(100) <= 65)
    & (df["mom_6m"].fillna(2) <= 1.15)
    & (df["aqr_trend_score"].fillna(-99) >= 0)
]
pre_run_multi = pre_run_multi.sort_values(
    ["n_categories","n_measures","mv_composite_score"], ascending=False)
sheets["Pre-Run Multi-Measure (RS<=65)"] = pre_run_multi.head(40)[COLS]


# ============================================================
# Write
# ============================================================
out_path = "global_best.xlsx"
with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
    for name, sheet_df in sheets.items():
        safe_n = name.replace("/","-").replace(":","-")[:31]
        if sheet_df.index.name is None:
            sheet_df = sheet_df.copy()
            sheet_df.index.name = "Ticker"
            sheet_df = sheet_df.reset_index()
        sheet_df.to_excel(writer, sheet_name=safe_n, index=False)
        ws = writer.sheets[safe_n]
        wb = writer.book
        hdr = wb.add_format({"bold": True, "bg_color": "#1F4E78",
                              "font_color": "white", "border": 1})
        ws.set_row(0, None, hdr)
        ws.freeze_panes(1, 1)
        for ci, col in enumerate(sheet_df.columns):
            ml = max(len(str(col)),
                      *(min(len(str(v)), 70) for v in sheet_df[col].head(40).fillna(""))) + 2
            ws.set_column(ci, ci, min(ml, 35))
        for sc in ["n_measures","n_categories","mv_composite_score",
                   "aqr_trend_score","td_mtf_composite"]:
            if sc in sheet_df.columns:
                ci = sheet_df.columns.get_loc(sc)
                ws.conditional_format(1, ci, len(sheet_df), ci,
                                       {"type": "3_color_scale",
                                        "min_color": "#F8696B",
                                        "mid_color": "#FFEB84",
                                        "max_color": "#63BE7B"})
        if "adv_usd_M" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("adv_usd_M")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                   {"type": "3_color_scale",
                                    "min_color": "#FFFFFF",
                                    "mid_color": "#A6D5FA",
                                    "max_color": "#4472C4"})

print(f"\nWrote {out_path}")
for k in sheets:
    print(f"  - {k} ({len(sheets[k])} rows)")
