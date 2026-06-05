"""Pre-Run Probability score: high-conviction setups not yet extended.

Doesn't filter the universe - scores every name on three axes:

A. SETUP QUALITY (how good is the technical pattern?)
   Minervini premium, power_trend, 3w_tight, bow_tie, base_ready,
   prebreakout_w, base_forming, vcp_with_volume, squeeze just-released

B. EARLY-STAGE (how much room is left before exhaustion?)
   RS_rank low/mid, mom_6m moderate, dist_sma50 not extreme,
   not extended_w, not at_ATH, not climax_top, dist from ATH > 10%

C. LIQUIDITY BUILDING (is institutional money already flowing in?)
   ADV >= $20M floor, ADV slope > 0, ADV accel > 0, ADV building
   (20/60 ratio > 1), AQR positive but not top decile

Pre-run probability = A + B + C; high-conviction "haven't run yet but
likely to" candidates rank near the top. Existing rankings are
unchanged.
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 320)
pd.set_option("display.float_format", "{:.2f}".format)

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

def safe(c, default=0):
    return df[c].fillna(default) if c in df.columns else default

def bsafe(c, default=False):
    return df[c].fillna(default) if c in df.columns else default

# ============================================================
# A. SETUP QUALITY — out of ~25 pts
# ============================================================
df["setup_quality"] = (
    bsafe("mv_setup_premium").astype(int) * 4
    + bsafe("mv_power_trend").astype(int) * 3
    + bsafe("mv_3w_tight").astype(int) * 3
    + bsafe("mv_bow_tie").astype(int) * 4         # rare, very valuable
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

# ============================================================
# B. EARLY-STAGE — out of ~20 pts. More points = less extended.
# ============================================================
df["early_stage"] = (
    # RS rank: lower = earlier (more room). Mapped to 0-6 points.
    (safe("rs_rank_max").apply(lambda x: 6 if x <= 30 else 5 if x <= 50 else 4 if x <= 70 else 3 if x <= 80 else 2 if x <= 90 else 1 if x <= 95 else 0))
    # mom_6m: moderate = early. Top is < 1.10 (10% in 6 months).
    + (safe("mom_6m").apply(lambda x: 4 if 0.95 <= x <= 1.10 else 3 if x <= 1.20 else 2 if x <= 1.30 else 1 if x <= 1.50 else 0))
    # dist_sma50: small distance = early.
    + (safe("dist_sma50_pct").apply(lambda x: 3 if -2 <= x <= 5 else 2 if -5 <= x <= 10 else 1 if x <= 15 else 0))
    # Not at ATH (room to ATH = early)
    + (~bsafe("mv_at_ath")).astype(int) * 2
    # Not extended_w
    + (~bsafe("extended_w")).astype(int) * 2
    # Not climax top warning
    + (~bsafe("mv_climax_top_warning")).astype(int) * 1
    # Distance from ATH 5-25% off (sweet spot - basing but recoverable)
    + (safe("mv_dist_from_ath_pct").apply(lambda x: 2 if 5 <= x <= 25 else 1 if 0 < x < 5 else 0))
)

# ============================================================
# C. LIQUIDITY BUILDING — out of ~15 pts
# ============================================================
df["liquidity_building"] = (
    # ADV floor tiers
    (safe("adv_20d_millions").apply(lambda x: 4 if x >= 500 else 3 if x >= 100 else 2 if x >= 50 else 1 if x >= 20 else 0))
    # ADV slope positive (volume building)
    + (safe("adv_slope_pct_wk").apply(lambda x: 3 if x >= 5 else 2 if x >= 2 else 1 if x > 0 else 0))
    # ADV acceleration positive (ramp itself accelerating)
    + (safe("adv_accel").apply(lambda x: 2 if x >= 5 else 1 if x > 0 else 0))
    # 20/60 ratio > 1 (recent vol > longer-term)
    + (safe("adv_20_over_60").apply(lambda x: 2 if x >= 1.2 else 1 if x >= 1.05 else 0))
    # AQR positive but NOT top decile (signal of fresh trend, not extended)
    + (safe("aqr_trend_score").apply(lambda x: 2 if 0.5 <= x <= 2.0 else 1 if 0 < x < 0.5 else 0))
    # TD MTF positive (turning up, not extended down)
    + (safe("td_mtf_composite").apply(lambda x: 2 if x >= 0.3 else 1 if x >= 0 else 0))
)

# Composite pre-run probability
df["pre_run_score"] = df["setup_quality"] + df["early_stage"] + df["liquidity_building"]
# Component shares for transparency
df["pre_run_pct_setup"] = df["setup_quality"] / df["pre_run_score"].replace(0, np.nan) * 100
df["pre_run_pct_early"] = df["early_stage"] / df["pre_run_score"].replace(0, np.nan) * 100
df["pre_run_pct_liquid"] = df["liquidity_building"] / df["pre_run_score"].replace(0, np.nan) * 100

cols = ["name","_universe","sector","last_close","rs_rank_max",
        "mom_3m","mom_6m","dist_sma50_pct","mv_dist_from_ath_pct",
        "adv_20d_millions","adv_slope_pct_wk","adv_tier",
        "mv_composite_score","mv_power_trend","mv_3w_tight","mv_bow_tie",
        "mv_at_ath","base_ready","prebreakout_w","aqr_trend_score","td_mtf_composite",
        "setup_quality","early_stage","liquidity_building","pre_run_score"]
cols = [c for c in cols if c in df.columns]

print(f"Total flagged equities: {len(df)}")
print()
print("Score distributions:")
for c in ["setup_quality","early_stage","liquidity_building","pre_run_score"]:
    print(f"  {c:20s} mean={df[c].mean():.1f}  p50={df[c].median():.1f}  "
          f"p90={df[c].quantile(0.9):.1f}  p99={df[c].quantile(0.99):.1f}  max={df[c].max():.0f}")

print()
print("=" * 140)
print("TOP 30 PRE-RUN PROBABILITY — HIGHEST CONVICTION FOR SETUPS THAT HAVEN'T MOVED YET")
print("=" * 140)
top = df.sort_values("pre_run_score", ascending=False).head(30)
print(top[cols].to_string())

# Per-region top to ensure US/Europe/Asia are represented
print()
print("=" * 140)
print("TOP 10 PER REGION")
print("=" * 140)
EU_UNIS = {"uk-all","de-all","fr-all","it-all","ch-all","es-all","nl-all","se-all",
           "be-all","no-all","dk-all","fi-all","ie-all","pt-all","at-all","gr-all",
           "eu-smid","eu-large","eu-micro","eu-nano"}
ASIA_UNIS = {"jp-all","cn-all","kr-all","tw-all","hk-all","in-all","sg-all"}

for label, mask in [("US", df["_universe"] == "us-all"),
                     ("EU", df["_universe"].isin(EU_UNIS)),
                     ("ASIA", df["_universe"].isin(ASIA_UNIS)),
                     ("OTHER", ~(df["_universe"].isin(EU_UNIS | ASIA_UNIS | {"us-all"})))]:
    sub = df[mask].sort_values("pre_run_score", ascending=False).head(10)
    print(f"\n--- {label} ({mask.sum()} total) — TOP 10 ---")
    print(sub[cols].to_string())

# High setup_quality but LOW early_stage — names that already ran
print()
print("=" * 140)
print("ALREADY RUN — high setup_quality but bottom-third early_stage (avoid chasing)")
print("=" * 140)
mask_run = (df["setup_quality"] >= df["setup_quality"].quantile(0.9)) & (df["early_stage"] <= df["early_stage"].quantile(0.33))
print(df[mask_run].sort_values("setup_quality", ascending=False).head(15)[cols].to_string())

# High early_stage AND high liquidity_building — building but not yet moved
print()
print("=" * 140)
print("BUILDING — top early_stage + liquidity_building (room AND volume coming in)")
print("=" * 140)
df["build_score"] = df["early_stage"] + df["liquidity_building"]
mask_build = (df["build_score"] >= df["build_score"].quantile(0.95)) & (df["setup_quality"] >= df["setup_quality"].quantile(0.7))
print(df[mask_build].sort_values("build_score", ascending=False).head(20)[cols + ["build_score"]].to_string())
