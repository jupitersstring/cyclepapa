"""'Best of each archetype WITH good ADV' sheet.

For every archetype/screen we already produce, take the top names and
additionally surface their ADV signals so the reader can spot which
high-conviction ideas also have institutional liquidity behind them.

ADV is purely additive — it never filters out a name from the original
ranking. The cuts here are sorted/grouped by ADV characteristics to
help select tradeable ideas from each archetype.

Archetypes covered:
  1. MINERVINI PREMIUM (mv_setup_premium = True)
  2. POWER TREND + 3-WEEKS-TIGHT (Minervini canon)
  3. BOW TIE (fresh Stage 2 emergence)
  4. QUALITY CONTINUATION (power_trend + at_ath + AQR top decile)
  5. FRESH STAGE 2 EMERGING (bow_tie OR 3w_tight + S2 + not_ATH)
  6. CONTRARIAN BOTTOM (TD>=1 + AQR<=-1 + rs<=30)
  7. SELL STRENGTH (rs>=95 + AQR top decile + TD bearish)
  8. DOUBLE-CONFIRMED BULL (AQR>=1.5 AND TD>=0.5)
  9. EUROPEAN PREMIUM (eu universes + premium setup)
 10. US MEGA + LARGE PREMIUM (us-all + premium + large/mega cap)
 11. MULTI-FRAMEWORK CONVICTION (bull_score >= 7 of 17 indep signals)

For each archetype, three views:
  A. Top by archetype score (existing ranking) with ADV displayed
  B. Top by archetype score WITH ADV >= $20M (Minervini-floor)
  C. Top by ADV ramping signal (slope + accel) within the archetype
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 320)
pd.set_option("display.float_format", "{:.2f}".format)


df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)

# Cast booleans
bool_cols = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
             'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume',
             'mv_buyable_gap_up','mv_at_ath','mv_in_buy_zone','mv_at_pivot',
             'mv_pocket_pivot','mv_stage2_pass','mv_stage4_pass',
             'mv_climax_top_warning','q_method_pass','base_ready','prebreakout_w',
             'long_base','darvas_tight','asym_w_above_ma','sq_w_just_release',
             'sq_m_just_release','harmonic_bullish_w_or_m','macd_above_signal']
for c in bool_cols:
    if c in df.columns:
        df[c] = df[c].astype(str).str.lower().isin(["true","1","yes"])
num_cols = [c for c in df.columns if c not in (
    "name","sector","_universe","fb_lists","tags",
    "h_d_pattern","h_d_direction","h_w_pattern","h_w_direction",
    "h_m_pattern","h_m_direction","_cap") and c not in bool_cols]
for c in num_cols:
    if df[c].dtype == "object":
        df[c] = pd.to_numeric(df[c], errors="coerce")

# Build multi-framework conviction (mirrors the heatmap logic)
def safe(c, default=False):
    return df[c].fillna(default) if c in df.columns else default

bull_signals_count = (
    (safe("aqr_trend_score", 0) >= 1.0).astype(int) * 2
    + (safe("td_mtf_composite", 0) >= 0.5).astype(int)
    + (safe("roque_score", 0) >= 7).astype(int)
    + safe("q_method_pass").astype(int)
    + safe("base_ready").astype(int)
    + safe("prebreakout_w").astype(int)
    + safe("long_base").astype(int)
    + safe("darvas_tight").astype(int)
    + (safe("sq_w_just_release").astype(bool) | safe("sq_m_just_release").astype(bool)).astype(int)
    + safe("asym_w_above_ma").astype(int)
    + safe("mv_setup_premium").astype(int)
    + safe("mv_power_trend").astype(int)
    + safe("mv_3w_tight").astype(int)
    + safe("mv_bow_tie").astype(int)
)
df["bull_score"] = bull_signals_count

# ADV-tier classification (no filtering — just labels)
def adv_tier(v):
    if pd.isna(v): return "n/a"
    if v >= 1000: return "mega ($1B+)"
    if v >= 200: return "large ($200M-1B)"
    if v >= 50:  return "good ($50-200M)"
    if v >= 20:  return "ok ($20-50M)"
    if v >= 5:   return "small ($5-20M)"
    return "illiquid (<$5M)"
df["adv_tier"] = df["adv_20d_millions"].apply(adv_tier)

# ADV "quality" score = liquid floor + accelerating + ramping
# (used to sort WITHIN an archetype, never to exclude)
df["adv_quality"] = (
    (df["adv_20d_millions"].fillna(0) >= 20).astype(int)    # liquid floor
    + (df["adv_20d_millions"].fillna(0) >= 100).astype(int)  # institutional
    + (df["adv_20d_millions"].fillna(0) >= 500).astype(int)  # mega-cap level
    + (df["adv_slope_pct_wk"].fillna(0) > 0).astype(int)     # building
    + (df["adv_slope_pct_wk"].fillna(0) > 5).astype(int)     # rapidly building
    + (df["adv_20_over_60"].fillna(0) > 1.1).astype(int)     # recent > 60d
    + (df["adv_accel"].fillna(0) > 0).astype(int)            # ramp itself accelerating
)

cols = ["name","_universe","sector","last_close","adv_20d_millions",
        "adv_slope_pct_wk","adv_20_over_60","adv_accel","adv_tier","adv_quality",
        "mv_composite_score","mv_power_trend","mv_3w_tight","mv_at_ath",
        "aqr_trend_score","td_mtf_composite","rs_rank_max","bull_score"]
cols = [c for c in cols if c in df.columns]

def show_archetype(label, sub, sort_col, asc=False, n=15):
    """Show three views: by archetype score, by archetype score + ADV>=20M, by ADV-ramp."""
    if len(sub) == 0:
        print(f"  ({label}: no rows)")
        return
    print()
    print("=" * 130)
    print(f"{label}  ({len(sub)} names)")
    print("=" * 130)
    # A: top by archetype score
    a = sub.sort_values(sort_col, ascending=asc).head(n)
    print(f"\n-- A. Top {n} by {sort_col} (ADV shown but not filtered) --")
    print(a[cols].to_string())
    # B: top by archetype with ADV floor
    b = sub[sub["adv_20d_millions"].fillna(0) >= 20].sort_values(sort_col, ascending=asc).head(n)
    if len(b):
        print(f"\n-- B. Top {n} by {sort_col} AND ADV >= $20M (Minervini liquidity floor) --")
        print(b[cols].to_string())
    # C: top by ADV-ramp within archetype
    c = sub.sort_values(["adv_quality","adv_slope_pct_wk"], ascending=[False, False]).head(n)
    print(f"\n-- C. Top {n} by ADV quality + slope (find institutional inflow within archetype) --")
    print(c[cols].to_string())


# 1. MINERVINI PREMIUM
show_archetype("1. MINERVINI PREMIUM (mv_setup_premium = True)",
               df[df["mv_setup_premium"]], "mv_composite_score")

# 2. POWER TREND + 3-WEEKS-TIGHT
show_archetype("2. POWER TREND + 3-WEEKS-TIGHT (Minervini canon, rare)",
               df[df["mv_power_trend"] & df["mv_3w_tight"]], "mv_composite_score")

# 3. BOW TIE
show_archetype("3. BOW TIE (fresh Stage 2 emergence, 10ema+21ema cross above 50sma)",
               df[df["mv_bow_tie"]], "mv_composite_score")

# 4. QUALITY CONTINUATION (power_trend + at_ath + AQR top decile)
aqr_p90 = df["aqr_trend_score"].quantile(0.9)
mask_qc = df["mv_power_trend"] & df["mv_at_ath"] & (df["aqr_trend_score"] >= aqr_p90)
show_archetype("4. QUALITY CONTINUATION (power_trend AND at_ath AND AQR top decile)",
               df[mask_qc], "mv_composite_score")

# 5. FRESH STAGE 2
mask_fresh = df["mv_bow_tie"] | (df["mv_3w_tight"] & (df["mv_stage2_count"] >= 8) & ~df["mv_at_ath"])
show_archetype("5. FRESH STAGE 2 EMERGING (bow_tie OR 3w_tight + Stage2 8+ + not_ATH)",
               df[mask_fresh], "mv_composite_score")

# 6. CONTRARIAN BOTTOM
mask_c = (df["td_mtf_composite"] >= 1.0) & (df["aqr_trend_score"] <= -1.0) & (df["rs_rank_max"] <= 30)
show_archetype("6. CONTRARIAN BOTTOM (TD>=1.0 AND AQR<=-1.0 AND rs<=30)",
               df[mask_c], "td_mtf_composite")

# 7. SELL STRENGTH
mask_s = ((df["rs_rank_max"] >= 95) & (df["aqr_trend_score"] >= aqr_p90)
          & (df["td_mtf_composite"] <= -1.0)) | df["mv_climax_top_warning"]
show_archetype("7. SELL STRENGTH (rs>=95 + AQR top decile + TD bearish OR climax_top)",
               df[mask_s], "td_mtf_composite", asc=True)

# 8. DOUBLE-CONFIRMED BULL
mask_db = (df["aqr_trend_score"] >= 1.5) & (df["td_mtf_composite"] >= 0.5)
show_archetype("8. DOUBLE-CONFIRMED BULL (AQR>=1.5 AND TD>=0.5)",
               df[mask_db], "td_mtf_composite")

# 9. EUROPEAN PREMIUM
eu_universes = ["uk-all","de-all","fr-all","it-all","ch-all","es-all","nl-all",
                "se-all","be-all","no-all","dk-all","fi-all","ie-all","pt-all",
                "at-all","gr-all","eu-smid","eu-large","eu-micro","eu-nano"]
mask_eu = df["_universe"].isin(eu_universes) & df["mv_setup_premium"]
show_archetype("9. EUROPEAN PREMIUM (EU-universe + mv_setup_premium)",
               df[mask_eu], "mv_composite_score")

# 10. US PREMIUM
mask_us = (df["_universe"] == "us-all") & df["mv_setup_premium"]
show_archetype("10. US PREMIUM (us-all + mv_setup_premium)",
               df[mask_us], "mv_composite_score")

# 11. MULTI-FRAMEWORK CONVICTION
show_archetype("11. MULTI-FRAMEWORK CONVICTION (bull_score >= 7 of 17)",
               df[df["bull_score"] >= 7], "bull_score")

# 12. THE "ALL ROADS" SHORTLIST — premium AND double-bull AND high ADV
mask_allroads = df["mv_setup_premium"] & mask_db & (df["adv_20d_millions"].fillna(0) >= 50)
print()
print("=" * 130)
print("12. ALL-ROADS SHORTLIST  Mv_premium + DoubleBull (AQR>=1.5 + TD>=0.5) + ADV>=$50M")
print("=" * 130)
ar = df[mask_allroads].sort_values("mv_composite_score", ascending=False).head(25)
print(f"({len(ar)} names — the rarest stack)")
print(ar[cols].to_string())

# 13. ADV-LEADERS WHO ARE ALSO BULLISH (find names with mega ADV + multi-bull)
mask_megaliq = (df["adv_20d_millions"].fillna(0) >= 500) & (df["bull_score"] >= 5)
print()
print("=" * 130)
print("13. MEGA-LIQUID BULL (ADV >= $500M AND bull_score >= 5/17) — institutional-tradeable names")
print("=" * 130)
ml = df[mask_megaliq].sort_values("adv_20d_millions", ascending=False).head(30)
print(f"({len(ml)} names)")
print(ml[cols].to_string())
