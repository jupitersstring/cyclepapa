"""Rank the ENTIRE common-equity universe by measure-family pass count.

Methodologically correct alternative to global_best.py.

Instead of "did this ticker appear in the top-N of measure X's ranking
sheet", we apply a per-row pass/fail test for every measure to every
one of the 9,598 common-equity rows. A ticker is counted as passing a
measure if either:
  - the underlying boolean flag is True, or
  - the underlying continuous score meets an absolute threshold, or
  - it falls in a top percentile globally for that measure.

This way no ticker is invisible just because it ranked #51 on a measure
that only surfaces the top 50.

Output: global_best_full.xlsx with:
  - Pass-count distribution
  - Top 200 globally by category count
  - Tradeable / Institutional / Mega-Liquid cuts
  - Per-region cuts
  - Balanced (multi-cat + not extended + liquid)
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np


# ============================================================
# 1. Load + clean
# ============================================================
df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
bools = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
         'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume',
         'mv_buyable_gap_up','mv_at_ath','mv_in_buy_zone','mv_at_pivot',
         'mv_pocket_pivot','mv_stage2_pass','mv_stage4_pass',
         'mv_climax_top_warning','q_method_pass','q_method_pass_monthly_strong',
         'q_method_pass_weekly','base_ready','prebreakout_w','long_base',
         'darvas_tight','asym_w_above_ma','asym_w_just_crossed_up',
         'asym_just_crossed_up','rel_asym_above_ma','rel_asym_w_above_ma',
         'rel_asym_m_above_ma','sq_w_just_release','sq_m_just_release',
         'sq_d_just_release','sq_w_hyper','harmonic_bullish_w_or_m',
         'harmonic_bullish_consonance','macd_above_signal','extended_w',
         'base_forming','very_long_base','base_on_base','near_box_top',
         'box_breakout','consolidating','vol_drying','uptrend_w','tight_base_w',
         'td_bullish_exhaustion','td_bullish_exhaustion_strong',
         'breakout_squeeze','breakout_squeeze_strict','wma_trend_up',
         'monthly_uptrend','rel_trend_up','rel_macd_above_signal']
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

# Region tag
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

print(f"Universe loaded: {len(df)} common-equity rows")

# ============================================================
# 2. Define per-row PASS conditions for each measure category
#    (evaluated on all 9,598 rows)
# ============================================================
def col(c, default=np.nan):
    return df[c] if c in df.columns else pd.Series(default, index=df.index)
def bcol(c, default=False):
    return df[c].fillna(default) if c in df.columns else pd.Series(default, index=df.index)

# Pass conditions per CATEGORY (each = one independent family)
# We require the BULLISH side only (this is a long-side screen).
passes = pd.DataFrame(index=df.index)

# --- MA-RESPECT ---
# A name "respects" its 50d or 10w MA when the strategy IR is strong OR
# respect ratio is high AND slope is positive.
ma_d50_ir = col("ma_d50_strategy_ir").fillna(-99)
ma_w10_ir = col("ma_w10_strategy_ir").fillna(-99)
ma_d50_rr = col("ma_d50_respect_ratio").fillna(0)
ma_d50_slope = col("ma_d50_slope_pct_wk").fillna(-99)
passes["MA-respect"] = (
    (ma_d50_ir >= 1.0) | (ma_w10_ir >= 1.0)
    | ((ma_d50_rr >= 0.6) & (ma_d50_slope > 0))
)

# --- Roque ---
passes["Roque"] = col("roque_score").fillna(0) >= 7

# --- Q-method ---
passes["Q-method"] = bcol("q_method_pass") | bcol("q_method_pass_monthly_strong") | bcol("q_method_pass_weekly")

# --- Vol-asymmetry ---
passes["Vol-asymmetry"] = (
    (col("rel_asym_score").fillna(0) >= 4)
    | bcol("asym_w_above_ma") & bcol("asym_w_just_crossed_up")
    | bcol("rel_asym_above_ma") & bcol("rel_asym_m_above_ma")
)

# --- Squeeze release (bullish only) ---
passes["Squeeze-release"] = (
    bcol("sq_w_just_release") | bcol("sq_m_just_release")
    | bcol("breakout_squeeze_strict")
)

# --- TD Sequential bullish exhaustion / setup ---
passes["TD-Sequential"] = (
    (col("td_w_buy_setup").fillna(0) >= 9)
    | (col("td_m_buy_cd").fillna(0) >= 13)
    | (col("td_w_buy_cd").fillna(0) >= 13)
    | (col("td_m_buy_setup").fillna(0) >= 9)
    | (col("td_mtf_composite").fillna(-99) >= 0.5)
    | bcol("td_bullish_exhaustion_strong")
)

# --- Darvas ---
# Tight base of >= 12 weeks, near top, not yet broken
passes["Darvas"] = (
    (bcol("darvas_tight") & (col("box_length_weeks").fillna(0) >= 12))
    | bcol("near_box_top")
    | bcol("box_breakout")
    | (col("box_length_weeks").fillna(0) >= 20)
)

# --- Harmonic ---
passes["Harmonic"] = (
    bcol("harmonic_bullish_w_or_m")
    | bcol("harmonic_bullish_consonance")
    | (col("harmonic_score").fillna(0) >= 3.0)
)

# --- Minervini setup ---
# Premium OR power trend OR 3w tight OR bow tie OR VCP-with-volume
passes["Minervini-setup"] = (
    bcol("mv_setup_premium") | bcol("mv_power_trend") | bcol("mv_3w_tight")
    | bcol("mv_bow_tie") | bcol("mv_vcp_with_volume")
    | bcol("mv_high_tight_flag") | bcol("mv_pocket_pivot")
    | bcol("mv_buyable_gap_up")
)

# --- Minervini Stage 2 trend ---
passes["Stage-2"] = bcol("mv_stage2_pass")

# --- Base detection (Roque + Q + Darvas + Minervini base flags) ---
passes["Base"] = (
    bcol("base_ready") | bcol("base_forming") | bcol("prebreakout_w")
    | bcol("long_base") | bcol("very_long_base") | bcol("base_on_base")
    | bcol("tight_base_w")
)

# --- Vol-drying ---
passes["Vol-drying"] = (
    bcol("vol_drying") | (col("vol_drying_ratio").fillna(99) < 0.8)
)

# --- AQR trend ---
# Top-quartile trend
aqr_p75 = df["aqr_trend_score"].quantile(0.75) if "aqr_trend_score" in df.columns else 1.0
passes["AQR-trend"] = col("aqr_trend_score").fillna(-99) >= max(aqr_p75, 0.5)

# --- RS leader ---
# Top-quartile (rs_rank_max >= 75 typically)
passes["RS-leader"] = col("rs_rank_max").fillna(0) >= 75

# --- ADV-building (institutional flow building) ---
passes["ADV-building"] = (
    (col("adv_slope_pct_wk").fillna(-99) > 0)
    & (col("adv_20_over_60").fillna(0) >= 1.0)
    & (df["adv_usd_M"].fillna(0) >= 5)
)

# --- Rel-SPY momentum bull ---
passes["Rel-SPY-bull"] = (
    (col("rel_return_6m_pct").fillna(-99) > 0)
    | bcol("rel_trend_up") | bcol("rel_macd_above_signal")
)

# --- MACD bull ---
passes["MACD-bull"] = (
    bcol("macd_above_signal") & bcol("wma_trend_up")
)

# ============================================================
# 3. Total category pass count + names of passing categories
# ============================================================
df["n_cats_passed"] = passes.sum(axis=1)
df["cats_passed"] = passes.apply(
    lambda row: ", ".join(c for c, v in row.items() if v), axis=1)
total_cats = len(passes.columns)
print(f"Evaluated {total_cats} measure categories per row")
print()
print("Distribution of pass counts across the FULL universe:")
for k, v in df["n_cats_passed"].value_counts().sort_index().items():
    print(f"  {k:>2d} categories passed: {v:>5d} tickers ({100*v/len(df):.1f}%)")
print()
print(f"Max categories passed: {df['n_cats_passed'].max()} of {total_cats}")
print()

# ============================================================
# 4. Build pre_run + bull scores (for tie-breaking)
# ============================================================
def safe(c, d=0): return df[c].fillna(d) if c in df.columns else d

df["pre_run_score"] = (
    bcol("mv_setup_premium").astype(int)*4 + bcol("mv_power_trend").astype(int)*3
    + bcol("mv_3w_tight").astype(int)*3 + bcol("mv_bow_tie").astype(int)*4
    + bcol("base_ready").astype(int)*3 + bcol("prebreakout_w").astype(int)*3
    + bcol("long_base").astype(int)*2 + bcol("darvas_tight").astype(int)*2
    + (bcol("sq_w_just_release") | bcol("sq_m_just_release")).astype(int)*3
    + bcol("q_method_pass").astype(int)*2
    + (safe("roque_score") >= 7).astype(int)*2
    + (safe("roque_score") >= 9).astype(int)*2
    + (safe("mv_stage2_count") >= 8).astype(int)*2
    + safe("rs_rank_max").apply(lambda x: 6 if x<=30 else 5 if x<=50 else 4 if x<=70 else 3 if x<=80 else 2 if x<=90 else 1 if x<=95 else 0)
    + safe("mom_6m").apply(lambda x: 4 if 0.95<=x<=1.10 else 3 if x<=1.20 else 2 if x<=1.30 else 1 if x<=1.50 else 0)
    + (~bcol("mv_at_ath")).astype(int)*2 + (~bcol("extended_w")).astype(int)*2
    + (~bcol("mv_climax_top_warning")).astype(int)
    + df["adv_usd_M"].fillna(0).apply(lambda x: 4 if x>=500 else 3 if x>=100 else 2 if x>=50 else 1 if x>=20 else 0)
    + safe("adv_slope_pct_wk").apply(lambda x: 3 if x>=5 else 2 if x>=2 else 1 if x>0 else 0)
    + safe("td_mtf_composite").apply(lambda x: 2 if x>=0.3 else 1 if x>=0 else 0)
)

# ============================================================
# 5. Output sheets
# ============================================================
COLS = ["name","_universe","region","_ccy","sector","last_close","rs_rank_max",
        "mom_3m","mom_6m","mv_dist_from_ath_pct",
        "aqr_trend_score","td_mtf_composite","mv_composite_score",
        "mv_stage2_count","mv_vcp_count","mv_power_trend","mv_3w_tight",
        "mv_bow_tie","mv_at_ath","adv_usd_M","adv_slope_pct_wk",
        "n_cats_passed","pre_run_score","cats_passed"]
COLS = [c for c in COLS if c in df.columns]

sheets = {}

# 1. True best overall — sorted by n_cats then pre_run then mv
sheets["True Best (full universe)"] = df.sort_values(
    ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False).head(200)[COLS]

# 2. Tradeable ($20M USD ADV) — top 100
sheets["Tradeable ($20M+ ADV)"] = df[df["adv_usd_M"].fillna(0) >= 20].sort_values(
    ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False).head(100)[COLS]

# 3. Institutional ($100M+)
sheets["Institutional ($100M+ ADV)"] = df[df["adv_usd_M"].fillna(0) >= 100].sort_values(
    ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False).head(80)[COLS]

# 4. Mega-Liquid ($500M+)
sheets["Mega-Liquid ($500M+ ADV)"] = df[df["adv_usd_M"].fillna(0) >= 500].sort_values(
    ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False).head(60)[COLS]

# 5. BALANCED BEST: multi-cat + not extended + TD not warning + liquid
balanced = df[
    (df["n_cats_passed"] >= 5)
    & (df["adv_usd_M"].fillna(0) >= 20)
    & (df["aqr_trend_score"].fillna(0) >= 0)
    & (df["td_mtf_composite"].fillna(0) >= -0.3)
    & (df["rs_rank_max"].fillna(100) <= 85)
    & (df["mom_6m"].fillna(2) <= 1.30)
    & (df["mv_dist_from_ath_pct"].fillna(0) <= 30)
]
sheets["Balanced Best (5+cats, not run, liquid)"] = balanced.sort_values(
    ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False).head(80)[COLS]

# 6. Per region
for r, floor in [("US",20),("UK",20),("EU",10),("ASIA",5),
                 ("LATAM",1),("OCEANIA",5),("CA",5),("AFRICA",1)]:
    sub = df[(df["region"] == r) & (df["adv_usd_M"].fillna(0) >= floor)]
    if len(sub) < 10:
        sub = df[df["region"] == r]
    sub = sub.sort_values(
        ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False)
    sheets[f"Best {r} (ADV>=${floor}M)"] = sub.head(40)[COLS]

# 7. The 7+ category cluster — strongest possible measure agreement
sheets["7+ Categories Passed"] = df[df["n_cats_passed"] >= 7].sort_values(
    ["n_cats_passed","pre_run_score","mv_composite_score"], ascending=False).head(80)[COLS]

# 8. Distribution stats sheet
dist = pd.DataFrame({
    "n_cats_passed": list(range(0, total_cats+1)),
    "n_tickers": [int((df["n_cats_passed"] == i).sum()) for i in range(0, total_cats+1)],
    "pct_universe": [round(100*(df["n_cats_passed"] == i).sum()/len(df), 2)
                     for i in range(0, total_cats+1)],
})
sheets["Distribution"] = dist

# ============================================================
# 6. Write xlsx
# ============================================================
out_path = "global_best_full.xlsx"
with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
    for name, sheet_df in sheets.items():
        safe_n = name.replace("/","-").replace(":","-").replace("$","").replace("(","").replace(")","")[:31]
        if sheet_df.index.name is None and name != "Distribution":
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
        for ci, col_ in enumerate(sheet_df.columns):
            ml = max(len(str(col_)),
                      *(min(len(str(v)), 70) for v in sheet_df[col_].head(40).fillna(""))) + 2
            ws.set_column(ci, ci, min(ml, 35))
        for sc in ["n_cats_passed","pre_run_score","mv_composite_score",
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
