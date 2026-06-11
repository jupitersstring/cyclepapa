"""Build multi-sheet xlsx report from global_equities_consolidated.

Sheets:
  - Pre-Run Top 100        (global top by pre_run_score)
  - Pre-Run US Top 50
  - Pre-Run EU Top 50
  - Pre-Run Asia Top 50
  - Pre-Run Other Top 30
  - Minervini Premium      (all premium setups, sorted by composite)
  - Power Trend + 3w Tight (Minervini canon overlap)
  - Bow Tie + Fresh S2     (fresh emergence)
  - Multi-Framework Bull   (bull_score >= 7)
  - Mega-Liquid Bull       (ADV >= $500M + bull_score >= 5)
  - Already Run            (high quality but extended - avoid)
  - Sell Strength          (TD bearish at extreme RS)
  - Contrarian Bottom      (TD bullish at extreme RS low)
  - Sector x Region        (AQR + TD + MV pivots)
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from datetime import datetime

# ============================================================
# Load + cast
# ============================================================
df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
bool_cols = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
             'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume',
             'mv_buyable_gap_up','mv_at_ath','mv_in_buy_zone','mv_at_pivot',
             'mv_pocket_pivot','mv_stage2_pass','mv_stage4_pass',
             'mv_climax_top_warning','q_method_pass','base_ready','prebreakout_w',
             'long_base','darvas_tight','asym_w_above_ma','sq_w_just_release',
             'sq_m_just_release','harmonic_bullish_w_or_m','macd_above_signal',
             'extended_w','base_forming','tight_base_w','pullback_w',
             'consolidating','vol_drying','uptrend_w','very_long_base',
             'base_on_base','near_box_top','box_breakout']
for c in bool_cols:
    if c in df.columns:
        df[c] = df[c].astype(str).str.lower().isin(["true","1","yes"])
num_cols = [c for c in df.columns if c not in (
    "name","sector","_universe","fb_lists","tags","adv_tier",
    "h_d_pattern","h_d_direction","h_w_pattern","h_w_direction",
    "h_m_pattern","h_m_direction","_cap") and c not in bool_cols]
for c in num_cols:
    if df[c].dtype == "object":
        df[c] = pd.to_numeric(df[c], errors="coerce")

# Drop duplicates on (ticker) keeping the row with highest mv_composite_score
df = df.sort_values("mv_composite_score", ascending=False, na_position="last")
df = df[~df.index.duplicated(keep="first")]
print(f"Unique tickers after dedupe: {len(df)}")

# ============================================================
# Compute pre_run score (same logic as pre_run_probability.py)
# ============================================================
def safe(c, default=0):
    return df[c].fillna(default) if c in df.columns else default
def bsafe(c, default=False):
    return df[c].fillna(default) if c in df.columns else default

df["setup_quality"] = (
    bsafe("mv_setup_premium").astype(int) * 4
    + bsafe("mv_power_trend").astype(int) * 3
    + bsafe("mv_3w_tight").astype(int) * 3
    + bsafe("mv_bow_tie").astype(int) * 4
    + bsafe("mv_vcp_with_volume").astype(int) * 3
    + bsafe("mv_high_tight_flag").astype(int) * 4
    + bsafe("base_ready").astype(int) * 3
    + bsafe("base_forming").astype(int) * 2
    + bsafe("prebreakout_w").astype(int) * 3
    + bsafe("long_base").astype(int) * 2
    + bsafe("very_long_base").astype(int) * 2
    + bsafe("darvas_tight").astype(int) * 2
    + bsafe("tight_base_w").astype(int) * 2
    + bsafe("vol_drying").astype(int) * 2
    + bsafe("base_on_base").astype(int) * 2
    + (bsafe("sq_w_just_release").astype(bool) | bsafe("sq_m_just_release").astype(bool)).astype(int) * 3
    + bsafe("harmonic_bullish_w_or_m").astype(int) * 1
    + bsafe("q_method_pass").astype(int) * 2
    + (safe("roque_score") >= 7).astype(int) * 2
    + (safe("roque_score") >= 9).astype(int) * 2
    + bsafe("asym_w_above_ma").astype(int) * 1
    + bsafe("macd_above_signal").astype(int) * 1
    + (safe("mv_stage2_count") >= 8).astype(int) * 2
)
df["early_stage"] = (
    safe("rs_rank_max").apply(lambda x: 6 if x <= 30 else 5 if x <= 50 else 4 if x <= 70 else 3 if x <= 80 else 2 if x <= 90 else 1 if x <= 95 else 0)
    + safe("mom_6m").apply(lambda x: 4 if 0.95 <= x <= 1.10 else 3 if x <= 1.20 else 2 if x <= 1.30 else 1 if x <= 1.50 else 0)
    + safe("dist_sma50_pct").apply(lambda x: 3 if -2 <= x <= 5 else 2 if -5 <= x <= 10 else 1 if x <= 15 else 0)
    + (~bsafe("mv_at_ath")).astype(int) * 2
    + (~bsafe("extended_w")).astype(int) * 2
    + (~bsafe("mv_climax_top_warning")).astype(int) * 1
    + safe("mv_dist_from_ath_pct").apply(lambda x: 2 if 5 <= x <= 25 else 1 if 0 < x < 5 else 0)
)
df["liquidity_building"] = (
    safe("adv_20d_millions").apply(lambda x: 4 if x >= 500 else 3 if x >= 100 else 2 if x >= 50 else 1 if x >= 20 else 0)
    + safe("adv_slope_pct_wk").apply(lambda x: 3 if x >= 5 else 2 if x >= 2 else 1 if x > 0 else 0)
    + safe("adv_accel").apply(lambda x: 2 if x >= 5 else 1 if x > 0 else 0)
    + safe("adv_20_over_60").apply(lambda x: 2 if x >= 1.2 else 1 if x >= 1.05 else 0)
    + safe("aqr_trend_score").apply(lambda x: 2 if 0.5 <= x <= 2.0 else 1 if 0 < x < 0.5 else 0)
    + safe("td_mtf_composite").apply(lambda x: 2 if x >= 0.3 else 1 if x >= 0 else 0)
)
df["pre_run_score"] = df["setup_quality"] + df["early_stage"] + df["liquidity_building"]

# Multi-framework conviction
df["bull_score"] = (
    (safe("aqr_trend_score") >= 1.0).astype(int) * 2
    + (safe("td_mtf_composite") >= 0.5).astype(int)
    + (safe("roque_score") >= 7).astype(int)
    + bsafe("q_method_pass").astype(int)
    + bsafe("base_ready").astype(int)
    + bsafe("prebreakout_w").astype(int)
    + bsafe("long_base").astype(int)
    + bsafe("darvas_tight").astype(int)
    + (bsafe("sq_w_just_release").astype(bool) | bsafe("sq_m_just_release").astype(bool)).astype(int)
    + bsafe("asym_w_above_ma").astype(int)
    + bsafe("mv_setup_premium").astype(int)
    + bsafe("mv_power_trend").astype(int)
    + bsafe("mv_3w_tight").astype(int)
    + bsafe("mv_bow_tie").astype(int)
    + bsafe("base_forming").astype(int)
)

# ADV tier label
def adv_tier(v):
    if pd.isna(v): return "n/a"
    if v >= 1000: return "mega ($1B+)"
    if v >= 200: return "large ($200M-1B)"
    if v >= 50:  return "good ($50-200M)"
    if v >= 20:  return "ok ($20-50M)"
    if v >= 5:   return "small ($5-20M)"
    return "illiquid (<$5M)"
df["adv_tier_lbl"] = df["adv_20d_millions"].apply(adv_tier)

# ============================================================
# Region tagging
# ============================================================
EU_UNIS = {"uk-all","de-all","fr-all","it-all","ch-all","es-all","nl-all","se-all",
           "be-all","no-all","dk-all","fi-all","ie-all","pt-all","at-all","gr-all",
           "eu-smid","eu-large","eu-micro","eu-nano"}
ASIA_UNIS = {"jp-all","cn-all","kr-all","tw-all","hk-all","in-all","sg-all",
             "il-all","th-all","id-all","tr-all","sa-all"}  # EM/frontier in Asia/MENA
LATAM_UNIS = {"br-all","mx-all","ar-all","cl-all"}
OCEANIA_UNIS = {"au-all","nz-all"}
def region_of(u):
    if u == "us-all": return "US"
    if u in EU_UNIS:  return "EU"
    if u in ASIA_UNIS: return "ASIA"
    if u in LATAM_UNIS: return "LATAM"
    if u in OCEANIA_UNIS: return "OCEANIA"
    if u == "za-all": return "AFRICA"
    if u == "ca-all": return "AMER/CA"
    return "OTHER"
df["region"] = df["_universe"].apply(region_of)

# ============================================================
# Standard column orders per sheet
# ============================================================
PRE_RUN_COLS = ["name","_universe","region","sector","last_close",
                "rs_rank_max","mom_3m","mom_6m","dist_sma50_pct","mv_dist_from_ath_pct",
                "adv_20d_millions","adv_slope_pct_wk","adv_20_over_60","adv_accel",
                "adv_tier_lbl","mv_composite_score","mv_stage2_count",
                "mv_power_trend","mv_3w_tight","mv_bow_tie","mv_at_ath","base_ready",
                "prebreakout_w","aqr_trend_score","td_mtf_composite","roque_score",
                "setup_quality","early_stage","liquidity_building","pre_run_score","bull_score"]
PRE_RUN_COLS = [c for c in PRE_RUN_COLS if c in df.columns]

MV_COLS = ["name","_universe","region","sector","last_close",
           "mv_composite_score","mv_stage2_count","mv_vcp_count",
           "mv_power_trend","mv_3w_tight","mv_bow_tie","mv_vcp_with_volume",
           "mv_high_tight_flag","mv_at_ath","mv_in_buy_zone","mv_pocket_pivot",
           "mv_dist_from_ath_pct","aqr_trend_score","td_mtf_composite","rs_rank_max",
           "adv_20d_millions","adv_slope_pct_wk","adv_tier_lbl",
           "ma_d50_strategy_ir","ma_w10_strategy_ir","pre_run_score"]
MV_COLS = [c for c in MV_COLS if c in df.columns]

BEAR_COLS = ["name","_universe","region","sector","last_close",
             "rs_rank_max","mom_3m","mom_6m","mv_dist_from_ath_pct",
             "td_mtf_composite","td_w_sell_setup","td_w_sell_cd",
             "td_m_sell_setup","td_m_sell_cd","aqr_trend_score","extended_w",
             "mv_climax_top_warning","mv_stage4_count","mv_stage4_pass",
             "adv_20d_millions","adv_slope_pct_wk","adv_tier_lbl"]
BEAR_COLS = [c for c in BEAR_COLS if c in df.columns]

BULL_COLS = ["name","_universe","region","sector","last_close","rs_rank_max",
             "td_mtf_composite","td_w_buy_setup","td_w_buy_cd","td_m_buy_setup",
             "td_m_buy_cd","aqr_trend_score","mv_composite_score","roque_score",
             "adv_20d_millions","adv_slope_pct_wk","adv_tier_lbl","bull_score",
             "pre_run_score"]
BULL_COLS = [c for c in BULL_COLS if c in df.columns]

# ============================================================
# Sheets
# ============================================================
# Exclude non-equity contaminants (preferreds, baby bonds, CEFs, warrants, BDRs)
# from the equity-focused sheets. We keep them in the master df so they appear
# in the Non-Equity Quarantine sheet for review.
if "security_type" not in df.columns:
    print("WARNING: security_type column not found - run security_type.py first")
    df["security_type"] = "common"
is_equity = df["security_type"] == "common"

# Prefer USD-normalised ADV where available
if "adv_20d_usd_millions" in df.columns:
    df["adv_20d_millions_local"] = df["adv_20d_millions"]
    df["adv_20d_millions"] = df["adv_20d_usd_millions"]
    print("Using USD-normalised ADV (adv_20d_millions = adv_20d_usd_millions)")

sheets = {}

# Non-equity quarantine — surfaced for review but never blended into bull screens
non_eq = df[~is_equity].copy()
if len(non_eq):
    qcols = [c for c in ["name","_universe","sector","security_type","last_close",
                          "mv_composite_score","td_mtf_composite","aqr_trend_score",
                          "adv_20d_millions","_ccy"] if c in non_eq.columns]
    sheets["Non-Equity Quarantine"] = non_eq[qcols].sort_values("security_type")

# Restrict the main df to equity-only for all equity sheets below
df = df[is_equity].copy()
print(f"After equity-only filter: {len(df)} rows (removed {(~is_equity).sum()} non-equity)")


# Named-index dedicated views (Russell 1000 + FTSE AIM 100)
r1k_mask = df["_universe"] == "wiki-r1k"
aim_mask = df["_universe"] == "wiki-aim100"
sheets["Russell 1000 (US large)"] = df[r1k_mask].sort_values("mv_composite_score", ascending=False).head(80)[MV_COLS] if r1k_mask.any() else pd.DataFrame()
sheets["FTSE AIM 100 (UK alt)"]   = df[aim_mask].sort_values("mv_composite_score", ascending=False).head(80)[MV_COLS] if aim_mask.any() else pd.DataFrame()

# Pre-Run global top 100
sheets["Pre-Run Top 100"] = df.sort_values("pre_run_score", ascending=False).head(100)[PRE_RUN_COLS]

# Per-region
sheets["Pre-Run US Top 50"]    = df[df["region"]=="US"].sort_values("pre_run_score", ascending=False).head(50)[PRE_RUN_COLS]
sheets["Pre-Run EU Top 50"]    = df[df["region"]=="EU"].sort_values("pre_run_score", ascending=False).head(50)[PRE_RUN_COLS]
sheets["Pre-Run Asia Top 50"]  = df[df["region"]=="ASIA"].sort_values("pre_run_score", ascending=False).head(50)[PRE_RUN_COLS]
sheets["Pre-Run Other Top 30"] = df[df["region"]=="OTHER"].sort_values("pre_run_score", ascending=False).head(30)[PRE_RUN_COLS]

# Minervini Premium
prem = df[df["mv_setup_premium"]].sort_values("mv_composite_score", ascending=False)
sheets["Minervini Premium"] = prem.head(150)[MV_COLS]

# Power Trend + 3w Tight
pt3w = df[df["mv_power_trend"] & df["mv_3w_tight"]].sort_values("mv_composite_score", ascending=False)
sheets["Power Trend + 3w Tight"] = pt3w.head(100)[MV_COLS]

# Bow Tie (fresh Stage 2 emergence)
bt = df[df["mv_bow_tie"]].sort_values("mv_composite_score", ascending=False)
sheets["Bow Tie Fresh Stage 2"] = bt[MV_COLS]

# Multi-framework bull
mfb = df[df["bull_score"] >= 7].sort_values(["bull_score","mv_composite_score"], ascending=[False, False])
sheets["Multi-Framework Bull"] = mfb.head(100)[BULL_COLS]

# Mega-liquid + bullish
ml = df[(df["adv_20d_millions"].fillna(0) >= 500) & (df["bull_score"] >= 5)].sort_values("adv_20d_millions", ascending=False)
sheets["Mega-Liquid Bull"] = ml[BULL_COLS]

# Already Run (avoid chasing) - high setup_quality + low early_stage + high rs/mom
sq_p90 = df["setup_quality"].quantile(0.9)
es_p33 = df["early_stage"].quantile(0.33)
ar_mask = (df["setup_quality"] >= sq_p90) & (df["early_stage"] <= es_p33)
sheets["Already Run (Avoid)"] = df[ar_mask].sort_values("setup_quality", ascending=False).head(60)[PRE_RUN_COLS]

# Sell Strength
aqr_p90 = df["aqr_trend_score"].quantile(0.9)
ss_mask = ((df["rs_rank_max"] >= 95) & (df["aqr_trend_score"] >= aqr_p90) & (df["td_mtf_composite"] <= -1.0)) | df["mv_climax_top_warning"]
sheets["Sell Strength"] = df[ss_mask].sort_values("td_mtf_composite").head(50)[BEAR_COLS]

# Contrarian Bottom
cb_mask = (df["td_mtf_composite"] >= 1.0) & (df["aqr_trend_score"] <= -1.0) & (df["rs_rank_max"] <= 30)
sheets["Contrarian Bottom"] = df[cb_mask].sort_values("td_mtf_composite", ascending=False).head(50)[BULL_COLS]

# ============================================================
# ROTATION SHEETS — aligned with sector net-rotation signal
# ============================================================
ROT_IN_SECS = {"Consumer Staples","Health Care","Consumer Discretionary","Communication Services"}
ROT_OUT_SECS = {"Information Technology","Financials","Energy"}

# Rotation-aligned longs: rotating-in sectors + TD bullish + not run + liquid + structure rebuilding
df["aqr_n"] = df["aqr_trend_score"].fillna(0)
df["td_n"]  = df["td_mtf_composite"].fillna(0)
df["rs_n"]  = df["rs_rank_max"].fillna(100)
df["mom6_n"] = df["mom_6m"].fillna(2)
df["adv_n"] = df["adv_20d_millions"].fillna(0)
df["s2_n"]  = df["mv_stage2_count"].fillna(0)

mask_rot_long = (
    df["sector"].isin(ROT_IN_SECS)
    & (df["td_n"] >= 0.3)
    & (df["rs_n"] <= 75)
    & (df["mom6_n"] <= 1.25)
    & (df["adv_n"] >= 50)
    & (df["s2_n"] >= 5)
)
mask_rot_short = (
    df["sector"].isin(ROT_OUT_SECS)
    & (df["aqr_n"] >= 2.0)
    & (df["td_n"] <= -0.8)
    & (df["rs_n"] >= 90)
    & (df["adv_n"] >= 100)
)

ROT_COLS = ["name","_universe","region","sector","last_close","rs_rank_max",
            "mom_3m","mom_6m","dist_sma50_pct","mv_dist_from_ath_pct",
            "aqr_trend_score","td_mtf_composite","mv_composite_score",
            "mv_stage2_count","adv_20d_millions","adv_slope_pct_wk","adv_tier_lbl",
            "roque_score","pre_run_score","bull_score"]
ROT_COLS = [c for c in ROT_COLS if c in df.columns]

sheets["Rotation Longs"] = df[mask_rot_long].sort_values("td_mtf_composite", ascending=False).head(80)[ROT_COLS]
sheets["Rotation Shorts"] = df[mask_rot_short].sort_values("td_mtf_composite").head(80)[ROT_COLS]

# Intra-sector pair candidates
pair_rows = []
for sec in ["Information Technology","Industrials","Materials","Financials",
            "Consumer Discretionary","Health Care","Consumer Staples"]:
    longs = df[(df["sector"]==sec) & (df["td_n"]>=0.6) & (df["adv_n"]>=100) & (df["rs_n"]<=75)]
    shorts = df[(df["sector"]==sec) & (df["td_n"]<=-1.0) & (df["adv_n"]>=100) & (df["rs_n"]>=90)]
    if not len(longs) or not len(shorts): continue
    lt = longs.sort_values("td_mtf_composite", ascending=False).head(3)
    st = shorts.sort_values("td_mtf_composite").head(3)
    for li, lr in lt.iterrows():
        for si, sr in st.iterrows():
            pair_rows.append({
                "sector": sec,
                "long_tkr": li,
                "long_name": lr.get("name",""),
                "long_region": lr["region"],
                "long_rs": lr["rs_rank_max"],
                "long_td": lr["td_mtf_composite"],
                "long_aqr": lr["aqr_trend_score"],
                "long_adv_M": lr["adv_20d_millions"],
                "short_tkr": si,
                "short_name": sr.get("name",""),
                "short_region": sr["region"],
                "short_rs": sr["rs_rank_max"],
                "short_td": sr["td_mtf_composite"],
                "short_aqr": sr["aqr_trend_score"],
                "short_adv_M": sr["adv_20d_millions"],
                "rs_spread": sr["rs_rank_max"] - lr["rs_rank_max"],
                "td_spread": lr["td_mtf_composite"] - sr["td_mtf_composite"],
            })
sheets["Intra-Sector Pairs"] = pd.DataFrame(pair_rows).sort_values("td_spread", ascending=False)

# Sector x Region pivot
sec_agg = df.groupby(["sector","region"]).agg(
    n=("last_close","count"),
    aqr=("aqr_trend_score","mean"),
    td=("td_mtf_composite","mean"),
    mv=("mv_composite_score","mean"),
    pre_run=("pre_run_score","mean"),
    pct_premium=("mv_setup_premium", lambda s: 100*s.mean()),
    pct_power_trend=("mv_power_trend", lambda s: 100*s.mean()),
    pct_at_ath=("mv_at_ath", lambda s: 100*s.mean()),
    pct_stage4=("mv_stage4_pass", lambda s: 100*s.mean()),
).reset_index()
sec_agg = sec_agg[sec_agg["n"] >= 15].round(2).sort_values("pre_run", ascending=False)
sheets["Sector x Region"] = sec_agg

# Fundamentals shortlist intersect
try:
    fund = pd.read_csv("fundamentals_special_situations.csv")
    fund_tickers = list(fund["Ticker"])
    fund_df = df.loc[df.index.intersection(fund_tickers)].copy()
    fund_lookup = fund.set_index("Ticker")
    for c in ["tier","transience","cap_reset","fcf_yield_pct","buyback_status","catalyst_clock"]:
        fund_df[f"fund_{c}"] = fund_df.index.map(lambda t: fund_lookup.loc[t, c] if t in fund_lookup.index else None)
    fund_cols = (["name","_universe","sector","last_close",
                  "fund_tier","fund_transience","fund_cap_reset","fund_fcf_yield_pct",
                  "fund_buyback_status","fund_catalyst_clock"]
                 + PRE_RUN_COLS[5:])
    fund_cols = [c for c in fund_cols if c in fund_df.columns]
    sheets["Fundamentals Shortlist"] = fund_df[fund_cols]
except Exception as e:
    print(f"Fundamentals overlay skipped: {e}")

# Summary stats sheet
summary_data = {
    "Generated": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    "Total flagged rows": [len(df)],
    "Universes contributing": [df["_universe"].nunique()],
    "With Minervini composite": [int(df["mv_composite_score"].notna().sum())],
    "Premium setups": [int(df["mv_setup_premium"].sum())],
    "Power trend setups": [int(df["mv_power_trend"].sum())],
    "At ATH": [int(df["mv_at_ath"].sum())],
    "Stage 4 (downtrend)": [int(df["mv_stage4_pass"].sum())],
    "Bow Tie": [int(df["mv_bow_tie"].sum())],
    "High Tight Flag": [int(df["mv_high_tight_flag"].sum())],
    "Climax Top Warning": [int(df["mv_climax_top_warning"].sum())],
}
summary_df = pd.DataFrame.from_dict(summary_data, orient="index", columns=["Value"])
sheets = {"Summary": summary_df, **sheets}

# ============================================================
# Write xlsx with formatting
# ============================================================
import xlsxwriter
out_path = "global_equity_screen.xlsx"
with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
    for name, sheet_df in sheets.items():
        # Reset index so ticker is a column
        if sheet_df.index.name == "Ticker" or sheet_df.index.name is None and name != "Summary":
            sheet_df = sheet_df.copy()
            sheet_df.index.name = "Ticker"
            sheet_df = sheet_df.reset_index()
        sheet_df.to_excel(writer, sheet_name=name[:31], index=False)
        ws = writer.sheets[name[:31]]
        wb = writer.book
        header_fmt = wb.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white", "border": 1})
        pct_fmt = wb.add_format({"num_format": "0.00"})
        # Format header + freeze
        ws.set_row(0, None, header_fmt)
        ws.freeze_panes(1, 1)
        # Auto-size columns approximately
        for col_i, col in enumerate(sheet_df.columns):
            max_len = max(len(str(col)),
                          *(len(str(v))[:50] if False else min(len(str(v)), 60) for v in sheet_df[col].head(50).fillna(""))) + 2
            ws.set_column(col_i, col_i, min(max_len, 30))
        # Conditional fill on pre_run_score / mv_composite_score columns
        if "pre_run_score" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("pre_run_score")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                  {"type": "3_color_scale",
                                   "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})
        if "mv_composite_score" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("mv_composite_score")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                  {"type": "3_color_scale",
                                   "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})
        if "aqr_trend_score" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("aqr_trend_score")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                  {"type": "3_color_scale",
                                   "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})
        if "td_mtf_composite" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("td_mtf_composite")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                  {"type": "3_color_scale",
                                   "min_color": "#F8696B", "mid_color": "#FFEB84", "max_color": "#63BE7B"})
        if "adv_20d_millions" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("adv_20d_millions")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                  {"type": "3_color_scale",
                                   "min_color": "#FFFFFF", "mid_color": "#A6D5FA", "max_color": "#4472C4"})

print(f"Wrote {out_path}")
print("Sheets:")
for k in sheets.keys():
    print(f"  - {k} ({len(sheets[k])} rows)")
