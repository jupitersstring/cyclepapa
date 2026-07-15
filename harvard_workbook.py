"""Harvard-aesthetic workbook: Top N per region for every measure leg + composites.

For each measure category we have built, produce ONE sheet with the top
N names per region (US/UK/EU/ASIA/LATAM/OCEANIA/AMER-CA/AFRICA). Names
are sorted by the specific measure's primary score within each region.

Harvard aesthetic:
  - Harvard Crimson (#A51C30) header rows
  - Charcoal accent text
  - Generous column widths, frozen header row + first column
  - Thin neutral borders
  - Cambria headers + Calibri body
  - Region group bands in subtle parchment
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np


# ============================================================
# 1. Load full consolidated CSV (post all corrections)
# ============================================================
df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
bools = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
         'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume','mv_buyable_gap_up',
         'mv_at_ath','mv_in_buy_zone','mv_at_pivot','mv_pocket_pivot',
         'mv_stage2_pass','mv_stage4_pass','mv_climax_top_warning',
         'q_method_pass','q_method_pass_monthly_strong','q_method_pass_weekly',
         'base_ready','prebreakout_w','long_base','darvas_tight','asym_w_above_ma',
         'asym_w_just_crossed_up','asym_above_ma','asym_just_crossed_up',
         'rel_asym_above_ma','rel_asym_w_above_ma','rel_asym_m_above_ma',
         'sq_w_just_release','sq_m_just_release','sq_d_just_release','sq_w_hyper',
         'harmonic_bullish_w_or_m','harmonic_bullish_consonance',
         'macd_above_signal','extended_w','base_forming','very_long_base',
         'base_on_base','near_box_top','box_breakout','consolidating','vol_drying',
         'uptrend_w','tight_base_w','td_bullish_exhaustion','td_bullish_exhaustion_strong',
         'td_bearish_exhaustion','td_bearish_exhaustion_strong','breakout_squeeze',
         'breakout_squeeze_strict','rel_trend_up','rel_macd_above_signal',
         # Q-method canonical (bullish)
         'q_method_canonical','q_method_consolidating','stacked_ma_any','stacked_ma',
         'weekly_stacked_ma','surfing_10dma','surfing_20dma','surfing_10_or_20',
         'rs_canonical','adr_qualifies','prior_move_30pct','higher_lows_4w',
         # Bearish setup pattern family
         'bearish_setup_canonical','bearish_setup_consolidating','bearish_stage4_full',
         'bearish_climax_turning','stacked_ma_down','weekly_stacked_ma_down',
         'stacked_ma_down_any','rs_laggard','rs_laggard_strict','prior_decline_30pct',
         'surfing_10dma_below','surfing_20dma_below','surfing_below_10_or_20',
         'lower_highs_4w','harmonic_bearish_consonance',
         # Robust canonical Darvas (darvas2_*)
         'darvas2_tight','darvas2_breakout','darvas2_breakout_strong',
         'darvas2_tight_near_top','darvas2_base_on_base','darvas2_vol_expansion',
         'darvas2_ceiling_at_52w_high']
for c in bools:
    if c in df.columns:
        df[c] = df[c].astype(str).str.lower().isin(["true","1","yes"])
skip_cols = {"name","sector","_universe","security_type","_ccy","fb_lists","tags",
             "adv_tier","_cap","h_d_pattern","h_d_direction","h_w_pattern",
             "h_w_direction","h_m_pattern","h_m_direction"}
for c in df.columns:
    if c not in skip_cols and c not in bools and df[c].dtype == "object":
        df[c] = pd.to_numeric(df[c], errors="coerce")
# --- De-duplicate cross-listings WITHOUT silently dropping the named row ---
# The same ticker appears in several universes (e.g. PNC in us-all AND
# wiki-union). The wiki-union copy often has a blank name/sector and maps to
# region OTHER. Sorting by mv_composite_score alone let that blank copy win
# the dedup, so real companies showed up nameless and vanished from their
# region sheet. Prefer the most-informative row: has a name, is NOT the
# generic wiki-union feed, then highest composite.
df["_has_name"] = df["name"].notna() & (df["name"].astype(str).str.strip().ne(""))
df["_not_wiki"] = ~df["_universe"].isin(["wiki-union"])
df = df.sort_values(
    ["_has_name", "_not_wiki", "mv_composite_score"],
    ascending=[False, False, False], na_position="last")
df = df[~df.index.duplicated(keep="first")]
df = df.drop(columns=["_has_name", "_not_wiki"])
# security_type filter: treat UNCLASSIFIED (NaN) as common rather than
# silently dropping it — only quarantine rows explicitly flagged non-common.
if "security_type" in df.columns:
    st = df["security_type"].astype("string").str.lower()
    df = df[st.isna() | (st == "common")].copy()
if "adv_20d_usd_millions" in df.columns:
    df["adv"] = df["adv_20d_usd_millions"]
else:
    df["adv"] = df.get("adv_20d_millions")

EU_UNI = {"de-all","fr-all","ch-all","it-all","es-all","nl-all","se-all","be-all",
          "no-all","dk-all","fi-all","ie-all","pt-all","at-all","gr-all","eu-smid",
          "eu-large","eu-micro","eu-nano"}
ASIA_UNI = {"jp-all","cn-all","kr-all","tw-all","hk-all","in-all","sg-all",
            "th-all","id-all","il-all","sa-all","tr-all"}
LATAM_UNI = {"br-all","mx-all","ar-all","cl-all"}
# Exchange-suffix -> region, for tickers that only arrive via the generic
# wiki-union feed (no country-universe tag). Without this they fell to
# "OTHER" and were dropped from every per-region sheet.
SUFFIX_REGION = {
    "L":"UK",
    "DE":"EU","F":"EU","PA":"EU","MI":"EU","MC":"EU","AS":"EU","SW":"EU","ST":"EU",
    "BR":"EU","OL":"EU","CO":"EU","HE":"EU","VI":"EU","LS":"EU","IR":"EU","AT":"EU",
    "T":"ASIA","HK":"ASIA","KS":"ASIA","KQ":"ASIA","TW":"ASIA","TWO":"ASIA","NS":"ASIA",
    "BO":"ASIA","SI":"ASIA","SS":"ASIA","SZ":"ASIA","BK":"ASIA","JK":"ASIA","TA":"ASIA",
    "SR":"ASIA","IS":"ASIA",
    "AX":"OCEANIA","NZ":"OCEANIA",
    "TO":"CA","V":"CA","CN":"CA",
    "SA":"LATAM","MX":"LATAM","BA":"LATAM","SN":"LATAM",
    "JO":"AFRICA",
}
def region(u, tkr=None):
    if u == "us-all" or u == "wiki-r1k": return "US"
    if u == "uk-all" or u == "wiki-aim100": return "UK"
    if u in EU_UNI: return "EU"
    if u in ASIA_UNI: return "ASIA"
    if u in LATAM_UNI: return "LATAM"
    if u in ("au-all","nz-all"): return "OCEANIA"
    if u == "za-all": return "AFRICA"
    if u == "ca-all": return "CA"
    # Generic wiki-union / unknown: infer from the ticker's exchange suffix
    # so the name still lands in a real region instead of being dropped.
    if tkr is not None:
        s = str(tkr)
        if "." in s:
            suf = s.rsplit(".", 1)[-1].upper()
            if suf in SUFFIX_REGION:
                return SUFFIX_REGION[suf]
        else:
            return "US"  # bare tickers (no suffix) are US listings
    return "OTHER"
df["region"] = [region(u, t) for u, t in zip(df["_universe"], df.index)]

# OTHER is a real bucket now (catch-all) so nothing is silently excluded from
# the workbook even if a suffix is unmapped.
REGION_ORDER = ["US", "UK", "EU", "ASIA", "OCEANIA", "CA", "LATAM", "AFRICA", "OTHER"]
TOP_N_PER_REGION = 12

print(f"Universe: {len(df)} common-equity tickers, {df['region'].nunique()} regions")


# ============================================================
# 2. Define each MEASURE LEG: (display name, sort column, asc/desc,
#    optional filter mask, columns to show)
# ============================================================
def col(c, d=np.nan): return df[c] if c in df.columns else pd.Series(d, index=df.index)
def bcol(c, d=False): return df[c].fillna(d) if c in df.columns else pd.Series(d, index=df.index)

BASE_DISPLAY = ["region","name","sector","_universe","_ccy","last_close",
                "rs_rank_max","mom_6m","aqr_trend_score","td_mtf_composite",
                "mv_composite_score","adv","adv_slope_pct_wk"]

LEGS = [
    # (sheet_name, sort_col, ascending, filter_mask_fn, extra_cols, description)
    ("01. Composite – Minervini", "mv_composite_score", False,
     None,
     ["mv_stage2_count","mv_vcp_count","mv_power_trend","mv_3w_tight","mv_bow_tie","mv_at_ath"],
     "Minervini composite score (0-30+) — Stage 2 + VCP + 3w-tight + canon flags"),

    ("02. Composite – AQR Trend", "aqr_trend_score", False,
     lambda d: d["aqr_trend_score"].notna(),
     ["aqr_trend_1m","aqr_trend_3m","aqr_trend_6m","aqr_trend_12m"],
     "AQR-style vol-normalised TS-MOM across 1m/3m/6m/12m horizons, tanh-clipped, summed [-4..+4]"),

    ("03. Composite – TD MTF (bull)", "td_mtf_composite", False,
     lambda d: d["td_mtf_composite"].notna(),
     ["td_mtf_net_setup","td_mtf_net_cd","td_mtf_net_perfect","td_mtf_net_triple"],
     "TD Sequential MTF composite (sum of 5 nets across timeframes) — exhaustion of downtrend"),

    ("04. Composite – TD MTF (bear)", "td_mtf_composite", True,
     lambda d: d["td_mtf_composite"].notna() & (d["aqr_trend_score"].fillna(0) >= 1.5),
     ["td_mtf_net_setup","td_mtf_net_cd","td_mtf_net_perfect","td_mtf_net_triple"],
     "TD MTF bearish exhaustion at top-decile trend — sell-strength candidates"),

    ("05. Roque – 12-criterion", "roque_score", False,
     lambda d: d["roque_score"].notna(),
     ["roque_abs_leader","roque_rel_leader","roque_vol_drying","mv_power_trend"],
     "Roque score 0-12: weekly/monthly trend + MACD + 200dma slope + base + leader + vol drying"),

    ("06. Q-Method (lighter)", "rs_rank_max", False,
     lambda d: bcol("q_method_pass"),
     ["atr_rs","adr_pct_20d","q_method_pass_monthly_strong","q_method_pass_weekly","stacked_ma_any"],
     "Q-method lighter: RS≥70 + stacked MAs + ATR_RS≥50 + range-position top half"),

    ("06b. Q-Method CANONICAL", "rs_rank_max", False,
     lambda d: bcol("q_method_canonical"),
     ["adr_pct_20d","prior_move_3m_pct","surfing_10dma","surfing_20dma","stacked_ma_any","atr_rs"],
     "Canonical Qullamaggie: RS≥90 + ADR%≥5 + Stacked MAs + 30%+ prior 1-3m move + surfing 10/20DMA"),

    ("06c. Q Consolidating", "prior_move_3m_pct", False,
     lambda d: bcol("q_method_consolidating"),
     ["adr_pct_20d","range_4w_pct","higher_lows_4w","prior_move_1m_pct","surfing_10_or_20"],
     "Q breakout candidate: 30%+ prior 1-3m move + tight 4w range (≤15%) + higher lows + ADR≥5 + stacked"),

    ("07. MA-Respect 50d (Strategy IR)", "ma_d50_strategy_ir", False,
     lambda d: d["ma_d50_strategy_ir"].notna(),
     ["ma_d50_respect_ratio","ma_d50_slope_pct_wk","ma_d50_days_above","ma_d50_vol_asym_near"],
     "Sharpe of 'long while above 50DMA' rule — empirically validates MA-respect on the ticker"),

    ("08. MA-Respect 200d (Strategy IR)", "ma_d200_strategy_ir", False,
     lambda d: d["ma_d200_strategy_ir"].notna(),
     ["ma_d200_respect_ratio","ma_d200_slope_pct_wk","ma_d200_days_above"],
     "Same construct on 200DMA — long-term stage 2 respect"),

    ("09. MA-Respect 10wk", "ma_w10_strategy_ir", False,
     lambda d: d["ma_w10_strategy_ir"].notna(),
     ["ma_w10_respect_ratio","ma_w10_slope_pct_wk","ma_w10_days_above"],
     "Weekly 10-bar MA respect — Minervini's primary trend MA"),

    ("10. Darvas – Longest Box", "box_length_weeks", False,
     lambda d: d["box_length_weeks"].fillna(0) >= 12,
     ["box_height_pct","pos_in_box_pct","darvas_tight","near_box_top","box_breakout"],
     "Darvas box length — consolidation duration in weekly bars"),

    ("11. Darvas – Tight Bases", "box_height_pct", True,
     lambda d: bcol("darvas_tight") & (d["box_length_weeks"].fillna(0) >= 12),
     ["box_length_weeks","pos_in_box_pct","near_box_top","box_breakout"],
     "Tightest Darvas bases — lowest box height with ≥12-week duration"),

    ("11b. Darvas2 Breakout (longest box)", "darvas2_box_length_weeks", False,
     lambda d: bcol("darvas2_breakout") & (d["darvas2_box_length_weeks"].fillna(0) >= 6),
     ["darvas2_box_height_pct","darvas2_dist_from_top_pct","darvas2_breakout_freshness_w",
      "darvas2_breakout_strong","darvas2_vol_expansion","mv_composite_score"],
     "Robust Darvas: fresh CLOSE above a frozen ceiling (near 52w high, ≤10% extended, ≤4wk fresh), ranked by longest base"),

    ("11c. Darvas2 Tight Coil (pre-breakout)", "darvas2_box_length_weeks", False,
     lambda d: bcol("darvas2_tight_near_top"),
     ["darvas2_box_height_pct","darvas2_dist_from_top_pct","darvas2_base_on_base",
      "mv_composite_score","aqr_trend_score","adv"],
     "Robust Darvas coil: sitting in the top 3% of a tight (≤12%) mature box at 52w highs, not yet broken out — pre-breakout watchlist"),

    ("12. Harmonic – Weekly Quality", "h_w_quality", False,
     lambda d: d["h_w_quality"].notna(),
     ["h_w_pattern","h_w_direction","h_w_dist_from_d_pct","harmonic_score"],
     "Highest-quality harmonic pattern detection on weekly bars (Gartley/Bat/Butterfly/AB=CD)"),

    ("13. Harmonic – Monthly Quality", "h_m_quality", False,
     lambda d: d["h_m_quality"].notna(),
     ["h_m_pattern","h_m_direction","harmonic_score","harmonic_consonance"],
     "Monthly harmonic patterns — long-term turning points"),

    ("14. Harmonic – Multi-TF Consonance", "harmonic_consonance", False,
     lambda d: d["harmonic_consonance"].notna(),
     ["h_w_pattern","h_m_pattern","harmonic_score","harmonic_bullish_consonance"],
     "Rare: same harmonic pattern on multiple timeframes"),

    ("15. Vol-Asym – Rel-SPY Score", "rel_asym_score", False,
     lambda d: d["rel_asym_score"].notna(),
     ["rel_asym_d_signal","rel_asym_w_signal","rel_asym_m_signal","rel_asym_above_ma"],
     "Volatility asymmetry on RELATIVE-to-SPY series across D/W/M — leadership detection"),

    ("16. Vol-Asym – Weekly Above MA", "rs_rank_max", False,
     lambda d: bcol("asym_w_above_ma") & bcol("asym_w_just_crossed_up"),
     ["asym_w_now","asym_w_rising","rel_asym_score"],
     "Weekly absolute asymmetry above MA + just crossed up = freshly turning bullish"),

    ("17. Squeeze – Weekly Release", "sq_w_pct_of_max", True,
     lambda d: bcol("sq_w_just_release"),
     ["sq_w_was_high_90","sq_w_hyper","sq_m_just_release","asym_w_above_ma"],
     "Weekly Bollinger/Keltner squeeze JUST released — compression-to-breakout setup"),

    ("18. Squeeze – Monthly Release", "rs_rank_max", False,
     lambda d: bcol("sq_m_just_release"),
     ["sq_w_just_release","asym_w_above_ma","rel_asym_score"],
     "Monthly squeeze release — rare long-term compression breakout"),

    ("19. TD9 Weekly Buy Setup", "td_w_buy_setup", False,
     lambda d: d["td_w_buy_setup"].fillna(0) >= 9,
     ["td_w_buy_cd","td_w_buy_perfect","td_m_buy_setup","td_mtf_composite"],
     "Weekly TD9 buy setup completion — Demark exhaustion of downtrend"),

    ("20. TD13 Monthly Buy CD", "td_m_buy_cd", False,
     lambda d: d["td_m_buy_cd"].fillna(0) >= 13,
     ["td_m_buy_setup","td_w_buy_cd","td_mtf_composite","td_bullish_exhaustion_strong"],
     "Monthly TD13 buy countdown COMPLETE — strongest Demark long signal globally"),

    ("21. TD13 Monthly Sell CD", "td_m_sell_cd", False,
     lambda d: d["td_m_sell_cd"].fillna(0) >= 13,
     ["td_m_sell_setup","td_w_sell_cd","td_mtf_composite","td_bearish_exhaustion_strong"],
     "Monthly TD13 sell countdown COMPLETE — strongest Demark short/topping signal"),

    ("22. Rel-to-SPY 6m Outperform", "rel_return_6m_pct", False,
     lambda d: d["rel_return_6m_pct"].notna() & (d["rel_return_6m_pct"] < 10000),  # filter data artifacts
     ["rel_return_3m_pct","rel_trend_up","rel_asym_score","rel_macd_above_signal"],
     "Relative return vs SPY over last 6 months — pure RS leadership"),

    ("23. Vol Drying", "vol_drying_ratio", True,
     lambda d: d["vol_drying_ratio"].notna() & (d["vol_drying_ratio"] < 0.8),
     ["range_4w_w_pct","pullback_4w_w_pct","base_ready","darvas_tight"],
     "Recent volume drying — accumulation in silence (Wyckoff/Minervini)"),

    ("24. 200DMA Slope Leaders", "dma200_slope_pct", False,
     lambda d: d["dma200_slope_pct"].notna(),
     ["dist_dma200_pct","days_since_52w_high","mv_stage2_200_rising","mv_sma200_acceleration"],
     "Steepest 200-day MA upward slope — strongest sustained-trend evidence"),

    ("25. RS Rank Max", "rs_rank_max", False,
     lambda d: d["rs_rank_max"].notna(),
     ["atr_rs","rs_strong","rs_rank_6m","mv_composite_score"],
     "Maximum of RS rank across 1w/1m/3m/6m lookbacks — IBD-style RS leader"),

    ("26. ATR_RS Leaders", "atr_rs", False,
     lambda d: d["atr_rs"].notna(),
     ["atr_rs_above_50","rs_rank_max","mom_3m","mom_6m"],
     "ATR-normalised RS — risk-adjusted leadership metric"),

    ("27. Momentum 6m", "mom_6m", False,
     lambda d: d["mom_6m"].notna() & (d["mom_6m"] < 50),  # cap data artifacts
     ["mom_1m","mom_3m","rs_rank_max","td_mtf_composite"],
     "6-month price momentum (close / 126-day SMA)"),

    ("28. ADV Building (institutional flow)", "adv_slope_pct_wk", False,
     lambda d: d["adv_slope_pct_wk"].notna() & d["adv"].fillna(0).gt(5),
     ["adv","adv_20_over_60","adv_accel","aqr_trend_score"],
     "ADV slope %/wk — institutional money building in the name"),

    ("29. Minervini Power Trend + 3w-Tight", "mv_composite_score", False,
     lambda d: bcol("mv_power_trend") & bcol("mv_3w_tight"),
     ["mv_stage2_count","mv_vcp_count","mv_dist_from_ath_pct","aqr_trend_score"],
     "Minervini's strongest setup: Power Trend AND 3-Weeks-Tight"),

    ("30. Minervini Bow Tie", "mv_composite_score", False,
     lambda d: bcol("mv_bow_tie"),
     ["mv_stage2_count","mv_vcp_count","aqr_trend_score","td_mtf_composite"],
     "Fresh Stage 2 emergence: 10ema + 21ema crossed above 50sma"),

    ("31. Minervini High-Tight Flag", "mv_composite_score", False,
     lambda d: bcol("mv_high_tight_flag"),
     ["mv_dist_from_ath_pct","aqr_trend_score","mom_6m"],
     "100%+ pre-rally then 10-25% pullback then recovery — rare and powerful"),

    # ====================================================================
    # BEARISH SETUP PATTERN FAMILY — Stage 4 mark-down / topping / short
    # candidates. Mirror of the bullish Stage 2 / Q-method family above.
    # ====================================================================
    ("32. Bearish – Stage 4 Pass", "mv_stage4_count", False,
     lambda d: bcol("mv_stage4_pass"),
     ["mv_stage4_count","aqr_trend_score","rel_return_6m_pct","rs_rank_max",
      "td_mtf_composite"],
     "Minervini Stage 4 trend-template (mirror of Stage 2): price below MAs, MAs in death-cross, 200dma falling"),

    ("33. Bearish – Stage 4 + Rel Weak", "mv_stage4_count", False,
     lambda d: bcol("bearish_stage4_full"),
     ["rel_return_6m_pct","rel_trend_up","rel_macd_above_signal",
      "td_mtf_composite","mv_stage4_count"],
     "Stage 4 PLUS relative underperformance vs SPY — clean mark-down with no index-driven rescue"),

    ("34. Bearish – Canonical Setup", "rs_rank_max", True,
     lambda d: bcol("bearish_setup_canonical"),
     ["adr_pct_20d","prior_decline_3m_pct","surfing_10dma_below","surfing_20dma_below",
      "stacked_ma_down_any","atr_rs"],
     "Canonical short setup (mirror of Q-canonical): RS≤10 + ADR≥5 + stacked DOWN + 30%+ prior decline + surfing 10/20 from below"),

    ("35. Bearish – Bear-Flag Consolidating", "prior_decline_3m_pct", True,
     lambda d: bcol("prior_decline_30pct") & bcol("stacked_ma_down_any")
               & (bcol("lower_highs_4w") | (d["range_4w_pct"].fillna(99) <= 20)),
     ["bearish_setup_consolidating","adr_pct_20d","range_4w_pct","lower_highs_4w",
      "prior_decline_1m_pct","surfing_below_10_or_20"],
     "Bear-flag population: 30%+ prior decline + stacked DOWN + (lower highs or tight range). "
     "bearish_setup_consolidating column flags the strict full-criteria subset"),

    ("36. Bearish – Climax Turning", "td_mtf_composite", True,
     lambda d: bcol("bearish_climax_turning"),
     ["mv_climax_top_warning","rs_rank_max","mv_dist_from_ath_pct","extended_w",
      "td_bearish_exhaustion_strong","harmonic_bearish_consonance"],
     "Sell-strength: parabolic climax-top + RS≥90 + TD MTF turning bearish — well-loved names just rolling"),

    ("37. Bearish – TD13 Monthly Sell CD", "td_m_sell_cd", False,
     lambda d: d["td_m_sell_cd"].fillna(0) >= 13,
     ["td_m_sell_setup","td_w_sell_cd","td_mtf_composite",
      "td_bearish_exhaustion_strong","mv_stage4_pass"],
     "Monthly TD13 sell countdown complete — Demark's strongest topping signal"),

    ("38. Bearish – Harmonic Consonance", "harmonic_consonance", True,
     lambda d: pd.to_numeric(d["harmonic_consonance"], errors="coerce") <= -0.5,
     ["harmonic_bearish_consonance","h_w_pattern","h_m_pattern","harmonic_score",
      "h_w_direction","h_m_direction"],
     "Bearish-leaning harmonic patterns (consonance ≤ -0.5 = a bearish pattern on some "
     "timeframe, none bullish). harmonic_bearish_consonance flags the strict multi-TF (≤ -2) subset"),

    ("39. Bearish – ATH-Climax Extended", "mv_dist_from_ath_pct", True,
     lambda d: bcol("mv_at_ath") & bcol("extended_w") & bcol("mv_climax_top_warning"),
     ["rs_rank_max","mom_6m","aqr_trend_score","td_mtf_composite","extended_w"],
     "At ATH + weekly extended + climax-top warning — extreme late-stage exhaustion"),
]


# ============================================================
# 3. Aesthetics
# ============================================================
HARVARD_CRIMSON = "#A51C30"
HARVARD_DARK    = "#1A1A1A"
HARVARD_RULE    = "#999999"
PARCHMENT       = "#F4F1EA"
ROW_ALT         = "#FAFAFA"
REGION_BAND     = "#E8E4DA"

NUMERIC_FMT_2 = '#,##0.00;(#,##0.00);"-"'
NUMERIC_FMT_PCT = '0.00%;(0.00%);"-"'

writer = pd.ExcelWriter("harvard_workbook.xlsx", engine="xlsxwriter")
wb = writer.book

# Format library
fmt_header_top = wb.add_format({
    "bold": True, "font_name": "Cambria", "font_size": 11,
    "font_color": "white", "bg_color": HARVARD_CRIMSON,
    "align": "center", "valign": "vcenter", "border": 1, "border_color": HARVARD_DARK,
})
fmt_subhead = wb.add_format({
    "bold": True, "font_name": "Cambria", "font_size": 10,
    "italic": True, "font_color": HARVARD_DARK, "bg_color": PARCHMENT,
    "align": "left", "valign": "vcenter",
})
fmt_region_band = wb.add_format({
    "bold": True, "font_name": "Cambria", "font_size": 10,
    "font_color": HARVARD_CRIMSON, "bg_color": REGION_BAND,
    "align": "left", "valign": "vcenter", "top": 1, "bottom": 1, "border_color": HARVARD_DARK,
})
fmt_body_text = wb.add_format({
    "font_name": "Calibri", "font_size": 10, "font_color": HARVARD_DARK,
    "align": "left", "valign": "vcenter",
})
fmt_body_num = wb.add_format({
    "font_name": "Calibri", "font_size": 10, "font_color": HARVARD_DARK,
    "num_format": NUMERIC_FMT_2, "align": "right", "valign": "vcenter",
})
fmt_body_text_alt = wb.add_format({
    "font_name": "Calibri", "font_size": 10, "font_color": HARVARD_DARK,
    "align": "left", "valign": "vcenter", "bg_color": ROW_ALT,
})
fmt_body_num_alt = wb.add_format({
    "font_name": "Calibri", "font_size": 10, "font_color": HARVARD_DARK,
    "num_format": NUMERIC_FMT_2, "align": "right", "valign": "vcenter", "bg_color": ROW_ALT,
})
fmt_caption = wb.add_format({
    "font_name": "Cambria", "italic": True, "font_size": 10,
    "font_color": "#555555", "align": "left", "valign": "vcenter",
})


# ============================================================
# 4. Overview sheet
# ============================================================
ws = wb.add_worksheet("Overview")
writer.sheets["Overview"] = ws
ws.set_column(0, 0, 4)
ws.set_column(1, 1, 34)
ws.set_column(2, 2, 100)
ws.set_row(0, 32)
ws.merge_range("A1:C1", "Multi-Measure Equity Screening Workbook",
               wb.add_format({"bold": True, "font_name": "Cambria", "font_size": 18,
                              "font_color": "white", "bg_color": HARVARD_CRIMSON,
                              "align": "center", "valign": "vcenter"}))
ws.set_row(1, 22)
ws.merge_range("A2:C2",
               f"As of {pd.Timestamp.now().strftime('%B %d, %Y')} — {len(df):,} common-equity tickers across "
               f"{df['region'].nunique()} regions, {len(LEGS)} measure legs",
               fmt_caption)

ws.write(3, 0, "#", fmt_header_top)
ws.write(3, 1, "Measure leg", fmt_header_top)
ws.write(3, 2, "Description", fmt_header_top)
for i, (lname, sortc, asc, mask, extras, desc) in enumerate(LEGS):
    row = 4 + i
    even = i % 2 == 0
    f_text = fmt_body_text if even else fmt_body_text_alt
    ws.write(row, 0, i+1, f_text)
    ws.write(row, 1, lname, f_text)
    ws.write(row, 2, desc, f_text)
ws.freeze_panes(4, 0)


# ============================================================
# 5. One sheet per measure
# ============================================================
DISPLAY_COL_ORDER = [
    "Ticker","region","name","sector","_universe","last_close","rs_rank_max",
    "mom_3m","mom_6m","aqr_trend_score","td_mtf_composite","mv_composite_score",
    "adv","adv_slope_pct_wk"
]

for leg_idx, (lname, sortc, asc, mask_fn, extras, desc) in enumerate(LEGS):
    sheet_name = lname[:31]
    # If sort column doesn't exist in the consolidated CSV yet (e.g., new
    # signal pending a momentum_rank re-run), skip the leg gracefully.
    if sortc not in df.columns:
        print(f"  SKIP {lname}: sort column '{sortc}' missing from CSV")
        continue
    ws = wb.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = ws

    # Title rows
    ws.set_row(0, 28)
    title_fmt = wb.add_format({"bold": True, "font_name": "Cambria", "font_size": 14,
                                "font_color": "white", "bg_color": HARVARD_CRIMSON,
                                "align": "left", "valign": "vcenter", "indent": 1})
    ws.write(0, 0, lname, title_fmt)
    # Subtitle / caption
    ws.set_row(1, 24)
    ws.write(1, 0, desc, fmt_caption)

    # Determine columns to show (de-dupe)
    cols = list(DISPLAY_COL_ORDER)
    if sortc not in cols:
        cols.append(sortc)
    for e in extras:
        if e in df.columns and e not in cols:
            cols.append(e)
    cols = [c for c in cols if c in df.columns or c == "Ticker"]

    # Build the data: top N per region
    base = df.copy()
    if mask_fn is not None:
        try:
            base = base[mask_fn(base)]
        except KeyError as e:
            print(f"  SKIP {lname}: filter references missing column {e}")
            continue

    rows_out = []
    for r in REGION_ORDER:
        regsub = base[base["region"] == r]
        if not len(regsub): continue
        rsorted = regsub.sort_values(sortc, ascending=asc, na_position="last").head(TOP_N_PER_REGION)
        rsorted = rsorted.reset_index().rename(columns={"index": "Ticker"})
        rows_out.append((r, rsorted))

    # Header row (col 4 = where the table starts after title rows)
    header_row = 3
    for ci, c in enumerate(cols):
        ws.write(header_row, ci, c, fmt_header_top)
    ws.set_row(header_row, 22)

    # Set column widths
    width_map = {"Ticker": 14, "region": 8, "name": 36, "sector": 22, "_universe": 12,
                  "last_close": 12, "rs_rank_max": 8, "adv": 12,
                  "_ccy": 6}
    for ci, c in enumerate(cols):
        w = width_map.get(c, 13)
        ws.set_column(ci, ci, w)

    # Write region groups
    rr = header_row + 1
    for region_name, rsub in rows_out:
        # Region band row
        ws.merge_range(rr, 0, rr, len(cols)-1,
                        f"  {region_name}  (Top {len(rsub)} by {sortc})", fmt_region_band)
        ws.set_row(rr, 20)
        rr += 1
        for i, row in rsub.iterrows():
            even = i % 2 == 0
            for ci, c in enumerate(cols):
                v = row.get(c)
                # Choose text vs numeric format based on column type
                if c in ("Ticker","region","name","sector","_universe","_ccy") \
                    or (isinstance(v, str) and not pd.api.types.is_number(v)):
                    f = fmt_body_text if even else fmt_body_text_alt
                else:
                    f = fmt_body_num if even else fmt_body_num_alt
                if pd.isna(v):
                    ws.write(rr, ci, "", f)
                else:
                    ws.write(rr, ci, v, f)
            rr += 1
        rr += 1  # spacer

    ws.freeze_panes(header_row+1, 1)


# ============================================================
# 6. Final composite sheet: per-region best by overall conviction
# ============================================================
def safe(c, d=0): return df[c].fillna(d) if c in df.columns else d
def b(c): return df[c].fillna(False) if c in df.columns else pd.Series(False, index=df.index)

df["pre_run_score"] = (
    b("mv_setup_premium").astype(int)*4 + b("mv_power_trend").astype(int)*3
    + b("mv_3w_tight").astype(int)*3 + b("mv_bow_tie").astype(int)*4
    + b("base_ready").astype(int)*3 + b("prebreakout_w").astype(int)*3
    + b("long_base").astype(int)*2 + b("darvas_tight").astype(int)*2
    + (b("sq_w_just_release") | b("sq_m_just_release")).astype(int)*3
    + b("q_method_pass").astype(int)*2
    + (safe("roque_score") >= 7).astype(int)*2
    + (safe("roque_score") >= 9).astype(int)*2
    + (safe("mv_stage2_count") >= 8).astype(int)*2
    + safe("rs_rank_max").apply(lambda x: 6 if x<=30 else 5 if x<=50 else 4 if x<=70 else 3 if x<=80 else 2 if x<=90 else 1 if x<=95 else 0)
    + safe("mom_6m").apply(lambda x: 4 if 0.95<=x<=1.10 else 3 if x<=1.20 else 2 if x<=1.30 else 1 if x<=1.50 else 0)
    + (~b("mv_at_ath")).astype(int)*2 + (~b("extended_w")).astype(int)*2
    + (~b("mv_climax_top_warning")).astype(int)
    + df["adv"].fillna(0).apply(lambda x: 4 if x>=500 else 3 if x>=100 else 2 if x>=50 else 1 if x>=20 else 0)
    + safe("adv_slope_pct_wk").apply(lambda x: 3 if x>=5 else 2 if x>=2 else 1 if x>0 else 0)
    + safe("td_mtf_composite").apply(lambda x: 2 if x>=0.3 else 1 if x>=0 else 0)
)

ws = wb.add_worksheet("40. Composite – Pre-Run")
writer.sheets["40. Composite – Pre-Run"] = ws
ws.set_row(0, 28)
ws.write(0, 0, "Pre-Run Probability Composite", wb.add_format({
    "bold": True, "font_name": "Cambria", "font_size": 14,
    "font_color": "white", "bg_color": HARVARD_CRIMSON,
    "align": "left", "valign": "vcenter", "indent": 1}))
ws.set_row(1, 24)
ws.write(1, 0, "Setup quality + early stage + liquidity building combined into one score. Top N per region.",
         fmt_caption)

cols_final = ["Ticker","region","name","sector","_universe","last_close","rs_rank_max",
               "mom_6m","aqr_trend_score","td_mtf_composite","mv_composite_score",
               "adv","adv_slope_pct_wk","pre_run_score"]
cols_final = [c for c in cols_final if c in df.columns or c == "Ticker"]
header_row = 3
for ci, c in enumerate(cols_final):
    ws.write(header_row, ci, c, fmt_header_top)
ws.set_row(header_row, 22)
ws.set_column(0, 0, 14); ws.set_column(1, 1, 8); ws.set_column(2, 2, 36); ws.set_column(3, 3, 22)
ws.set_column(4, 4, 12)
for ci in range(5, len(cols_final)):
    ws.set_column(ci, ci, 13)

rr = header_row + 1
for region_name in REGION_ORDER:
    regsub = df[df["region"] == region_name]
    if not len(regsub): continue
    rsorted = regsub.sort_values("pre_run_score", ascending=False).head(15).reset_index()
    rsorted = rsorted.rename(columns={"index":"Ticker"})
    ws.merge_range(rr, 0, rr, len(cols_final)-1,
                    f"  {region_name}  (Top {len(rsorted)} by pre_run_score)", fmt_region_band)
    ws.set_row(rr, 20)
    rr += 1
    for i, row in rsorted.iterrows():
        even = i % 2 == 0
        for ci, c in enumerate(cols_final):
            v = row.get(c)
            if c in ("Ticker","region","name","sector","_universe","_ccy"):
                f = fmt_body_text if even else fmt_body_text_alt
            else:
                f = fmt_body_num if even else fmt_body_num_alt
            if pd.isna(v):
                ws.write(rr, ci, "", f)
            else:
                ws.write(rr, ci, v, f)
        rr += 1
    rr += 1
ws.freeze_panes(header_row+1, 1)


# ============================================================
# 7. Bearish composite sheet — top short candidates per region
# ============================================================
# The bearish_setup_score is computed inside momentum_rank's main(); if the
# consolidated CSV pre-dates that change, fall back to a Harvard-side build.
if "bearish_setup_score" not in df.columns:
    df["bearish_setup_score"] = (
        b("mv_stage4_pass").astype(int) * 4
        + b("bearish_setup_canonical").astype(int) * 4
        + b("bearish_setup_consolidating").astype(int) * 3
        + b("bearish_climax_turning").astype(int) * 3
        + b("mv_climax_top_warning").astype(int) * 2
        + b("td_bearish_exhaustion_strong").astype(int) * 3
        + b("td_bearish_exhaustion").astype(int) * 1
        + (safe("td_m_sell_cd") >= 13).astype(int) * 4
        + (safe("td_w_sell_cd") >= 13).astype(int) * 2
        + (safe("td_m_sell_setup") >= 9).astype(int) * 2
        + (safe("td_w_sell_setup") >= 9).astype(int) * 1
        + (safe("td_mtf_composite") <= -0.5).astype(int) * 3
        + (safe("td_mtf_composite") <= -0.3).astype(int) * 1
        + b("harmonic_bearish_consonance").astype(int) * 3
        + b("stacked_ma_down").astype(int) * 2
        + b("weekly_stacked_ma_down").astype(int) * 2
        + b("rs_laggard_strict").astype(int) * 2
        + b("rs_laggard").astype(int) * 1
        + b("prior_decline_30pct").astype(int) * 2
        + b("lower_highs_4w").astype(int) * 1
        + b("surfing_below_10_or_20").astype(int) * 1
    )

ws = wb.add_worksheet("41. Composite – Bearish Setup")
writer.sheets["41. Composite – Bearish Setup"] = ws
ws.set_row(0, 28)
ws.write(0, 0, "Bearish Setup Composite (Mark-Down / Short Candidates)",
         wb.add_format({"bold": True, "font_name": "Cambria", "font_size": 14,
                        "font_color": "white", "bg_color": HARVARD_CRIMSON,
                        "align": "left", "valign": "vcenter", "indent": 1}))
ws.set_row(1, 24)
ws.write(1, 0,
         "Mirror of Pre-Run: Stage 4 + bear-flag + climax-turning + TD bearish + harmonic bearish + RS laggard. Top N per region.",
         fmt_caption)

cols_bear = ["Ticker","region","name","sector","_universe","last_close","rs_rank_max",
             "mom_6m","aqr_trend_score","td_mtf_composite","mv_stage4_count",
             "rel_return_6m_pct","adv","adv_slope_pct_wk","bearish_setup_score"]
cols_bear = [c for c in cols_bear if c in df.columns or c == "Ticker"]
header_row = 3
for ci, c in enumerate(cols_bear):
    ws.write(header_row, ci, c, fmt_header_top)
ws.set_row(header_row, 22)
ws.set_column(0, 0, 14); ws.set_column(1, 1, 8); ws.set_column(2, 2, 36)
ws.set_column(3, 3, 22); ws.set_column(4, 4, 12)
for ci in range(5, len(cols_bear)):
    ws.set_column(ci, ci, 13)

rr = header_row + 1
for region_name in REGION_ORDER:
    regsub = df[df["region"] == region_name]
    if not len(regsub): continue
    rsorted = regsub.sort_values("bearish_setup_score", ascending=False).head(15).reset_index()
    rsorted = rsorted.rename(columns={"index":"Ticker"})
    ws.merge_range(rr, 0, rr, len(cols_bear)-1,
                    f"  {region_name}  (Top {len(rsorted)} by bearish_setup_score)",
                    fmt_region_band)
    ws.set_row(rr, 20)
    rr += 1
    for i, row in rsorted.iterrows():
        even = i % 2 == 0
        for ci, c in enumerate(cols_bear):
            v = row.get(c)
            if c in ("Ticker","region","name","sector","_universe","_ccy"):
                f = fmt_body_text if even else fmt_body_text_alt
            else:
                f = fmt_body_num if even else fmt_body_num_alt
            if pd.isna(v):
                ws.write(rr, ci, "", f)
            else:
                ws.write(rr, ci, v, f)
        rr += 1
    rr += 1
ws.freeze_panes(header_row+1, 1)


writer.close()
print(f"\nWrote harvard_workbook.xlsx")
print(f"  Overview sheet")
print(f"  + {len(LEGS)} measure-leg sheets")
print(f"  + 2 composite sheets (Pre-Run + Bearish Setup)")
print(f"  Total: {len(LEGS)+3} sheets, ~{TOP_N_PER_REGION*8} rows per leg")
