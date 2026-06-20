"""Top-50 per individual measure across the clean common-equity dataset.

Produces one xlsx where each sheet ranks names by ONE specific measure
(not the composites). Operates only on common-equity rows, uses USD
ADV, and the corrected VCP scores. Adds a region tag column to every
sheet so the reader sees regional distribution.

Measures covered:
  MA-respect: d50/d200/w10 strategy_ir, respect_ratio, slope_pct_wk,
              spring_k, vol_asym_near, days_above
  Roque: roque_score >= 9, roque_score, individual sub-flags
  Q-method: q_method_pass, q_method_pass_monthly_strong, q_method_pass_weekly
  Volatility asymmetry: rel_asym_score, asym_w_above_ma, just_crossed_up
  Squeeze: sq_w_pct_of_max, sq_w_just_release, sq_w_hyper
  TD per-TF: highest weekly buy_setup, monthly buy_cd completion (=13),
             relative-to-SPY weekly + monthly TD signals
  Darvas: tightest box (box>=12w), longest box, near_box_top + breakout
  Harmonic: highest h_w_quality, h_m_quality, harmonic_score, consonance
  Failed-bearish: fb_hit_count when populated
  Momentum: mom_1m/3m/6m extremes
  RS / ATR_RS / 200dma slope leaders
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np


# ============================================================
# Load + sanitise (mirrors per_region_analysis)
# ============================================================
df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
bools = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
         'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume','mv_buyable_gap_up',
         'mv_at_ath','mv_in_buy_zone','mv_at_pivot','mv_pocket_pivot',
         'mv_stage2_pass','mv_stage4_pass','mv_climax_top_warning',
         'q_method_pass','q_method_pass_monthly_strong','q_method_pass_weekly',
         'base_ready','prebreakout_w','long_base','darvas_tight','asym_w_above_ma',
         'asym_w_just_crossed_up','asym_above_ma','asym_just_crossed_up',
         'asym_rising','asym_w_rising','asym_m_above_ma','asym_m_just_crossed_up',
         'rel_asym_above_ma','rel_asym_just_crossed_up','rel_asym_w_above_ma',
         'rel_asym_w_just_crossed_up','rel_asym_m_above_ma','rel_asym_m_just_crossed_up',
         'sq_d_squeezing','sq_d_releasing','sq_d_just_release','sq_d_was_high_75',
         'sq_d_was_high_90','sq_w_squeezing','sq_w_just_release','sq_w_was_high_75',
         'sq_w_was_high_90','sq_w_hyper','sq_m_squeezing','sq_m_just_release',
         'harmonic_bullish_w_or_m','harmonic_bullish_consonance','harmonic_bearish_consonance',
         'macd_above_signal','macd_hist_rising','extended_w','base_forming',
         'tight_base_w','vol_drying','uptrend_w','very_long_base','base_on_base',
         'near_box_top','box_breakout','consolidating','pullback_w',
         'td_bullish_exhaustion','td_bullish_exhaustion_strong',
         'td_bearish_exhaustion','td_bearish_exhaustion_strong',
         'breakout_squeeze','breakout_squeeze_strict','wma_trend_up',
         'monthly_uptrend','rel_trend_up','rel_macd_above_signal','rel_macd_hist_rising']
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
# Use USD ADV
if "adv_20d_usd_millions" in df.columns:
    df["adv"] = df["adv_20d_usd_millions"]
else:
    df["adv"] = df.get("adv_20d_millions")

# region tag
REGION_MAP = {
    "us-all":"US","wiki-r1k":"US","wiki-spx500":"US","wiki-ndx":"US","wiki-djia":"US",
    "uk-all":"UK","wiki-aim100":"UK","wiki-ftse100":"UK","wiki-ftse250":"UK",
}
EU = {"de-all","fr-all","ch-all","it-all","es-all","nl-all","se-all","be-all",
      "no-all","dk-all","fi-all","ie-all","pt-all","at-all","gr-all","eu-smid",
      "eu-large","eu-micro","eu-nano"}
ASIA = {"jp-all","cn-all","kr-all","tw-all","hk-all","in-all","sg-all","th-all",
        "id-all","il-all","sa-all","tr-all"}
LATAM = {"br-all","mx-all","ar-all","cl-all"}
def region(u):
    if u in REGION_MAP: return REGION_MAP[u]
    if u in EU: return "EU"
    if u in ASIA: return "ASIA"
    if u in LATAM: return "LATAM"
    if u in ("au-all","nz-all"): return "OCEANIA"
    if u == "za-all": return "AFRICA"
    if u == "ca-all": return "CA"
    if u == "wiki-union": return "WIKI"
    return "OTHER"
df["region"] = df["_universe"].apply(region)


# ============================================================
# Helpers
# ============================================================
BASE_COLS = ["name","_universe","region","sector","last_close","rs_rank_max",
             "mom_3m","mom_6m","adv","adv_slope_pct_wk",
             "aqr_trend_score","td_mtf_composite","mv_composite_score"]


def topn(extra_cols, sort_col, mask=None, asc=False, n=50):
    sub = df if mask is None else df[mask]
    sub = sub[sub[sort_col].notna()] if sort_col in sub.columns else sub
    cols = BASE_COLS + [c for c in extra_cols if c in sub.columns and c not in BASE_COLS]
    cols = [c for c in cols if c in sub.columns]
    return sub.sort_values(sort_col, ascending=asc).head(n)[cols]


sheets = {}


# ============================================================
# 1. MA-RESPECT (the actual tweet thesis)
# ============================================================
for label, ma in [("50d", "d50"), ("200d", "d200"), ("10w", "w10")]:
    ir = f"ma_{ma}_strategy_ir"
    if ir in df.columns:
        sheets[f"MA{label} Strategy IR"] = topn(
            [f"ma_{ma}_strategy_ir", f"ma_{ma}_respect_ratio",
             f"ma_{ma}_slope_pct_wk", f"ma_{ma}_days_above",
             f"ma_{ma}_vol_asym_near", f"ma_{ma}_spring_k"],
            ir, mask=df[ir].notna(), n=50)
    rr = f"ma_{ma}_respect_ratio"
    if rr in df.columns:
        sheets[f"MA{label} Respect Ratio"] = topn(
            [rr, f"ma_{ma}_slope_pct_wk", f"ma_{ma}_strategy_ir",
             f"ma_{ma}_vol_asym_near", f"ma_{ma}_days_above"],
            rr, mask=(df[rr].notna()) & (df[f"ma_{ma}_slope_pct_wk"].fillna(-1) > 0), n=50)
    va = f"ma_{ma}_vol_asym_near"
    if va in df.columns:
        sheets[f"MA{label} Vol-Asym Near"] = topn(
            [va, f"ma_{ma}_respect_ratio", f"ma_{ma}_strategy_ir"],
            va, mask=df[va].notna(), n=50)


# ============================================================
# 2. ROQUE
# ============================================================
if "roque_score" in df.columns:
    sheets["Roque Score Leaders"] = topn(
        ["roque_score","roque_abs_trend","roque_abs_base","roque_rel_trend",
         "roque_rel_leader","roque_vol_drying","mv_setup_premium"],
        "roque_score", mask=df["roque_score"].notna(), n=50)
    sheets["Roque >= 9"] = topn(
        ["roque_score","roque_abs_trend","roque_abs_base","roque_abs_leader",
         "roque_rel_leader","roque_vol_drying","mv_composite_score","mv_setup_premium"],
        "roque_score", mask=df["roque_score"].fillna(0) >= 9, n=100)


# ============================================================
# 3. Q-METHOD (Qullamaggie)
# ============================================================
if "q_method_pass" in df.columns:
    sheets["Q Method Pass"] = topn(
        ["q_method_pass","q_method_pass_monthly_strong","q_method_pass_weekly",
         "atr_rs","stacked_ma_any","price_range_top_half","weekly_range_top_half"],
        "rs_rank_max", mask=df["q_method_pass"], n=100)
    sheets["Q Method Monthly Strong"] = topn(
        ["q_method_pass_monthly_strong","atr_rs","mom_3m","mom_6m"],
        "rs_rank_max", mask=df["q_method_pass_monthly_strong"], n=50)
if "q_score" in df.columns:
    sheets["Q Score Best (low=best)"] = topn(
        ["q_score","range_4w_w_pct","pullback_4w_w_pct","vol_drying_ratio","base_ready"],
        "q_score", asc=True, mask=df["q_score"].notna(), n=50)


# ============================================================
# 4. VOLATILITY ASYMMETRY
# ============================================================
if "rel_asym_score" in df.columns:
    sheets["Rel Asym Score Leaders"] = topn(
        ["rel_asym_score","rel_asym_d_signal","rel_asym_w_signal","rel_asym_m_signal",
         "rel_asym_now","rel_asym_above_ma","rel_asym_just_crossed_up"],
        "rel_asym_score", mask=df["rel_asym_score"].fillna(0) >= 4, n=50)
if "asym_w_above_ma" in df.columns:
    sheets["Weekly Asym Above MA"] = topn(
        ["asym_w_above_ma","asym_w_just_crossed_up","asym_w_rising","rel_asym_score"],
        "rs_rank_max",
        mask=df["asym_w_above_ma"] & df["asym_w_just_crossed_up"].fillna(False), n=50)
if "asym_just_crossed_up" in df.columns:
    sheets["Daily Asym Just Crossed Up"] = topn(
        ["asym_now","asym_just_crossed_up","asym_above_ma","rel_asym_score"],
        "rs_rank_max", mask=df["asym_just_crossed_up"], n=50)


# ============================================================
# 5. SQUEEZE / COMPRESSION RELEASE
# ============================================================
if "sq_w_just_release" in df.columns:
    sheets["Weekly Squeeze Just Release"] = topn(
        ["sq_w_just_release","sq_w_was_high_90","sq_w_hyper","sq_w_pct_of_max",
         "sq_m_just_release","asym_w_above_ma"],
        "rs_rank_max", mask=df["sq_w_just_release"], n=80)
if "sq_m_just_release" in df.columns:
    sheets["Monthly Squeeze Just Release"] = topn(
        ["sq_m_just_release","sq_w_just_release","asym_w_above_ma","rel_asym_score"],
        "rs_rank_max", mask=df["sq_m_just_release"], n=50)
if "breakout_squeeze" in df.columns:
    sheets["Breakout Squeeze (strict)"] = topn(
        ["breakout_squeeze","breakout_squeeze_strict","mv_composite_score","aqr_trend_score"],
        "rs_rank_max", mask=df["breakout_squeeze_strict"].fillna(False), n=50)


# ============================================================
# 6. TD PER-TIMEFRAME COMPLETIONS
# ============================================================
# Weekly TD9 buy_setup completion
if "td_w_buy_setup" in df.columns:
    sheets["Weekly TD9 Buy Setup"] = topn(
        ["td_w_buy_setup","td_w_buy_cd","td_w_buy_perfect","td_m_buy_setup",
         "td_mtf_composite","aqr_trend_score"],
        "td_w_buy_setup", mask=df["td_w_buy_setup"].fillna(0) >= 9, n=80)
# Monthly TD13 buy_cd completion (the rarest exhaustion signal)
if "td_m_buy_cd" in df.columns:
    sheets["Monthly TD13 Buy CD Complete"] = topn(
        ["td_m_buy_cd","td_m_buy_setup","td_w_buy_cd","td_m_sell_setup",
         "td_mtf_composite","td_bullish_exhaustion_strong"],
        "td_m_buy_cd", mask=df["td_m_buy_cd"].fillna(0) >= 13, n=80)
# Monthly TD13 sell_cd completion
if "td_m_sell_cd" in df.columns:
    sheets["Monthly TD13 Sell CD Complete"] = topn(
        ["td_m_sell_cd","td_m_sell_setup","td_w_sell_cd","td_mtf_composite",
         "td_bearish_exhaustion_strong","aqr_trend_score"],
        "td_m_sell_cd", mask=df["td_m_sell_cd"].fillna(0) >= 13, n=80)
# Relative-to-SPY weekly buy setup
if "td_w_rel_net_setup" in df.columns:
    sheets["Rel-SPY Weekly TD Net Setup"] = topn(
        ["td_w_rel_net_setup","td_w_rel_net_cd","td_w_rel_net_perfect",
         "td_m_rel_net_setup","td_m_rel_net_cd","rel_return_6m_pct"],
        "td_w_rel_net_setup", mask=df["td_w_rel_net_setup"].notna(), n=50)
# Net asymmetry composite
if "td_mtf_asymmetry" in df.columns:
    sheets["TD MTF Asymmetry"] = topn(
        ["td_mtf_asymmetry","td_mtf_composite","td_mtf_net_setup","td_mtf_net_cd",
         "td_mtf_net_perfect","td_mtf_net_triple"],
        "td_mtf_asymmetry", mask=df["td_mtf_asymmetry"].notna(), n=80)
# Exhaustion score
if "td_exhaustion_score" in df.columns:
    sheets["TD Exhaustion Bull"] = topn(
        ["td_exhaustion_score","td_bullish_exhaustion","td_bullish_exhaustion_strong",
         "td_mtf_composite","mv_dist_from_ath_pct"],
        "td_exhaustion_score", mask=df["td_exhaustion_score"].fillna(0) > 0, n=50)
    sheets["TD Exhaustion Bear"] = topn(
        ["td_exhaustion_score","td_bearish_exhaustion","td_bearish_exhaustion_strong",
         "td_mtf_composite","rs_rank_max"],
        "td_exhaustion_score", asc=True, mask=df["td_exhaustion_score"].fillna(0) < 0, n=50)


# ============================================================
# 7. DARVAS BOX
# ============================================================
if "box_length_weeks" in df.columns:
    sheets["Longest Darvas Box"] = topn(
        ["box_length_weeks","box_height_pct","pos_in_box_pct","dist_from_box_top_pct",
         "darvas_tight","near_box_top","box_breakout"],
        "box_length_weeks", mask=df["box_length_weeks"].fillna(0) >= 20, n=50)
if "darvas_tight" in df.columns:
    sheets["Darvas Tight Bases"] = topn(
        ["darvas_tight","box_length_weeks","box_height_pct","near_box_top",
         "pos_in_box_pct","mv_composite_score"],
        "box_length_weeks", mask=df["darvas_tight"] & (df["box_length_weeks"].fillna(0) >= 12), n=80)
if "near_box_top" in df.columns:
    sheets["Near Box Top (pre-breakout)"] = topn(
        ["near_box_top","box_breakout","dist_from_box_top_pct","box_length_weeks",
         "darvas_tight","mv_composite_score"],
        "box_length_weeks", mask=df["near_box_top"] & ~df["box_breakout"].fillna(False), n=50)


# ============================================================
# 8. HARMONIC PATTERNS
# ============================================================
for tf, lab in [("d","Daily"), ("w","Weekly"), ("m","Monthly")]:
    qcol = f"h_{tf}_quality"
    if qcol in df.columns:
        sheets[f"Harmonic {lab} Quality"] = topn(
            [qcol, f"h_{tf}_pattern", f"h_{tf}_direction", f"h_{tf}_dist_from_d_pct",
             f"h_{tf}_score", "harmonic_score","harmonic_consonance"],
            qcol, mask=df[qcol].fillna(0) > 0.5, n=50)
if "harmonic_consonance" in df.columns:
    sheets["Harmonic Multi-TF Consonance"] = topn(
        ["harmonic_consonance","harmonic_bullish_consonance","harmonic_bearish_consonance",
         "harmonic_score","h_w_pattern","h_m_pattern"],
        "harmonic_consonance", mask=df["harmonic_consonance"].notna(), n=50)
if "harmonic_bullish_w_or_m" in df.columns:
    sheets["Harmonic Bullish W or M"] = topn(
        ["harmonic_bullish_w_or_m","h_w_pattern","h_w_quality","h_m_pattern","h_m_quality"],
        "harmonic_score",
        mask=df["harmonic_bullish_w_or_m"] & df["harmonic_score"].notna(), n=80)


# ============================================================
# 9. RELATIVE-TO-SPY MOMENTUM
# ============================================================
if "rel_return_6m_pct" in df.columns:
    sheets["Rel-SPY 6m Outperformers"] = topn(
        ["rel_return_6m_pct","rel_return_3m_pct","rel_trend_up",
         "rel_macd_above_signal","rel_asym_score"],
        "rel_return_6m_pct", mask=df["rel_return_6m_pct"].notna(), n=80)
    sheets["Rel-SPY 6m Underperformers"] = topn(
        ["rel_return_6m_pct","rel_return_3m_pct","td_mtf_composite","mv_dist_from_ath_pct"],
        "rel_return_6m_pct", asc=True, mask=df["rel_return_6m_pct"].notna(), n=80)
if "rel_dist_wma30_pct" in df.columns:
    sheets["Rel-SPY Far Above 30wma"] = topn(
        ["rel_dist_wma30_pct","rel_dist_wma10_pct","rel_return_6m_pct","rel_trend_up"],
        "rel_dist_wma30_pct", mask=df["rel_dist_wma30_pct"].notna(), n=50)


# ============================================================
# 10. MOMENTUM EXTREMES (raw price)
# ============================================================
for tf in ["mom_1m","mom_3m","mom_6m"]:
    if tf in df.columns:
        sheets[f"Top {tf}"] = topn(
            [tf, "rs_rank_max", "mv_composite_score", "td_mtf_composite", "adv"],
            tf, mask=df[tf].notna(), n=80)


# ============================================================
# 11. RS / ATR_RS / 200dma slope
# ============================================================
if "rs_rank_max" in df.columns:
    sheets["RS Rank Max Leaders"] = topn(
        ["rs_rank_max","atr_rs","rs_strong","rs_rank_6m","mv_composite_score"],
        "rs_rank_max", mask=df["rs_rank_max"].notna(), n=80)
if "atr_rs" in df.columns:
    sheets["ATR_RS Leaders"] = topn(
        ["atr_rs","atr_rs_above_50","rs_rank_max","mom_3m","mom_6m"],
        "atr_rs", mask=df["atr_rs"].notna(), n=50)
if "dma200_slope_pct" in df.columns:
    sheets["200dma Slope Leaders"] = topn(
        ["dma200_slope_pct","dist_dma200_pct","days_since_52w_high",
         "mv_stage2_200_rising","mv_sma200_acceleration"],
        "dma200_slope_pct", mask=df["dma200_slope_pct"].notna(), n=80)


# ============================================================
# 12. Volume-drying + base setups
# ============================================================
if "vol_drying_ratio" in df.columns:
    sheets["Vol Drying (lowest ratio)"] = topn(
        ["vol_drying_ratio","range_4w_w_pct","pullback_4w_w_pct","base_ready",
         "darvas_tight","mv_composite_score"],
        "vol_drying_ratio", asc=True,
        mask=(df["vol_drying_ratio"].notna()) & (df["vol_drying_ratio"] < 0.8), n=80)


# ============================================================
# Write xlsx
# ============================================================
out_path = "all_measures.xlsx"
with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
    for name, sheet_df in sheets.items():
        safe = name.replace("/","-").replace("\\","-").replace(":","-")[:31]
        # Always promote the index to a 'Ticker' column so it appears in xlsx
        sheet_df = sheet_df.copy()
        if sheet_df.index.name is None:
            sheet_df.index.name = "Ticker"
        else:
            sheet_df.index.name = "Ticker"  # force the name
        sheet_df = sheet_df.reset_index()
        sheet_df.to_excel(writer, sheet_name=safe, index=False)
        ws = writer.sheets[safe]
        wb = writer.book
        hdr = wb.add_format({"bold": True, "bg_color": "#1F4E78",
                              "font_color": "white", "border": 1})
        ws.set_row(0, None, hdr)
        ws.freeze_panes(1, 1)
        for ci, col in enumerate(sheet_df.columns):
            ml = max(len(str(col)),
                      *(min(len(str(v)), 50) for v in sheet_df[col].head(40).fillna(""))) + 2
            ws.set_column(ci, ci, min(ml, 28))
        for sc in ["mv_composite_score","aqr_trend_score","td_mtf_composite",
                   "rs_rank_max","roque_score","rel_asym_score",
                   "ma_d50_strategy_ir","ma_d200_strategy_ir","ma_w10_strategy_ir",
                   "td_mtf_asymmetry","mom_6m","rel_return_6m_pct"]:
            if sc in sheet_df.columns:
                ci = sheet_df.columns.get_loc(sc)
                ws.conditional_format(1, ci, len(sheet_df), ci,
                                       {"type": "3_color_scale",
                                        "min_color": "#F8696B",
                                        "mid_color": "#FFEB84",
                                        "max_color": "#63BE7B"})
        if "adv" in sheet_df.columns:
            ci = sheet_df.columns.get_loc("adv")
            ws.conditional_format(1, ci, len(sheet_df), ci,
                                   {"type": "3_color_scale",
                                    "min_color": "#FFFFFF",
                                    "mid_color": "#A6D5FA",
                                    "max_color": "#4472C4"})

print(f"Wrote {out_path}")
print(f"Sheets ({len(sheets)}):")
for k in sheets:
    print(f"  - {k} ({len(sheets[k])} rows)")
