"""Sector x region pivot heatmaps + factor screens on the consolidated CSV.

Produces:
  - Mean AQR, TD MTF, Minervini composite by (sector x region) cell
  - % of names with mv_setup_premium, mv_power_trend, mv_at_ath by cell
  - Factor screens combining frameworks:
      - "Quality continuation": power_trend + at_ath + AQR top decile
      - "Fresh emerging Stage 2": bow_tie OR (3w_tight + Stage 2 9/9 + not yet ATH)
      - "Contrarian bottom": TD high + AQR collapsed + rs<30
      - "Sell strength": rs>=95 + AQR top decile + TD bearish + climax_top OR extended_w
"""

import warnings; warnings.filterwarnings("ignore")
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 320)
pd.set_option("display.float_format", "{:.2f}".format)

df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
bool_cols = ["mv_setup_premium","mv_setup_clean","mv_power_trend","mv_3w_tight",
             "mv_bow_tie","mv_high_tight_flag","mv_vcp_with_volume",
             "mv_buyable_gap_up","mv_at_ath","mv_in_buy_zone","mv_at_pivot",
             "mv_pocket_pivot","mv_stage2_pass","mv_stage4_pass",
             "mv_climax_top_warning"]
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

print(f"Total rows: {len(df)}, with sector+region: {df['sector'].notna().sum()}")

# Map _universe to broader region
REGION_MAP = {
    "us-all": "US",
    "uk-all": "UK",
    "de-all": "EU/DE", "fr-all": "EU/FR", "it-all": "EU/IT", "es-all": "EU/ES",
    "nl-all": "EU/NL", "ch-all": "EU/CH", "se-all": "EU/SE", "be-all": "EU/BE",
    "no-all": "EU/NO", "dk-all": "EU/DK", "fi-all": "EU/FI", "ie-all": "EU/IE",
    "pt-all": "EU/PT", "at-all": "EU/AT", "gr-all": "EU/GR", "eu-smid": "EU/smid",
    "br-all": "LATAM", "mx-all": "LATAM", "za-all": "AFRICA",
    "jp-all": "ASIA/JP", "cn-all": "ASIA/CN", "kr-all": "ASIA/KR",
    "tw-all": "ASIA/TW", "in-all": "ASIA/IN", "hk-all": "ASIA/HK",
    "sg-all": "ASIA/SG", "au-all": "OCEANIA", "ca-all": "AMER/CA",
}
df["_region"] = df["_universe"].map(REGION_MAP).fillna(df["_universe"])

# Aggregate AQR + TD + MV composite by sector x region
print()
print("="*120)
print("SECTOR x REGION mean of (AQR_trend_score, TD_MTF_composite, MV_composite)  n>=20 cells")
print("="*120)
agg = df.groupby(["sector","_region"]).agg(
    n=("last_close","count"),
    aqr=("aqr_trend_score","mean"),
    td=("td_mtf_composite","mean"),
    mv=("mv_composite_score","mean"),
).reset_index()
agg = agg[agg["n"] >= 20]

# Pivot for readability
for metric, label in [("aqr","AQR"), ("td","TD"), ("mv","MV")]:
    print(f"\n--- {label} (sector x region) ---")
    p = agg.pivot(index="sector", columns="_region", values=metric).round(2)
    # Sort sectors
    p = p.reindex(sorted(p.index, key=lambda s: p.loc[s].mean() if pd.notna(p.loc[s].mean()) else 0, reverse=True))
    print(p.to_string())

# Percentage flagging key Minervini setups per (sector x region)
print()
print("="*120)
print("Per (sector x region) cell: %% power_trend, %% at_ath, %% setup_premium  (n>=20)")
print("="*120)
def cell_pct(g, col):
    return (g[col].sum() / len(g) * 100) if len(g) else 0

agg2 = df.groupby(["sector","_region"]).apply(lambda g: pd.Series({
    "n": len(g),
    "pct_power_trend": cell_pct(g,"mv_power_trend"),
    "pct_at_ath": cell_pct(g,"mv_at_ath"),
    "pct_premium": cell_pct(g,"mv_setup_premium"),
    "pct_stage4": cell_pct(g,"mv_stage4_pass"),
})).reset_index()
agg2 = agg2[agg2["n"] >= 20].sort_values("pct_premium", ascending=False).head(25)
print(agg2.to_string(index=False))

# Factor screens
print()
print("="*120)
print("FACTOR SCREENS")
print("="*120)
cols = ["name","_universe","sector","last_close","mv_composite_score",
        "mv_power_trend","mv_at_ath","mv_3w_tight","mv_bow_tie",
        "aqr_trend_score","td_mtf_composite","rs_rank_max",
        "ma_d50_strategy_ir","mv_dist_from_ath_pct"]
cols = [c for c in cols if c in df.columns]

# QUALITY CONTINUATION
print()
print("--- QUALITY CONTINUATION: power_trend AND at_ath AND AQR top decile ---")
q1 = df[df["mv_power_trend"] & df["mv_at_ath"] &
        (df["aqr_trend_score"] >= df["aqr_trend_score"].quantile(0.9))].sort_values(
            "mv_composite_score", ascending=False).head(25)
print(f"({len(q1)} names)")
print(q1[cols].to_string())

# FRESH EMERGING STAGE 2
print()
print("--- FRESH STAGE 2 EMERGING: bow_tie OR (3w_tight AND stage2 8+ AND not ATH) ---")
mask_fresh = df["mv_bow_tie"] | (df["mv_3w_tight"] & (df["mv_stage2_count"] >= 8) & ~df["mv_at_ath"])
q2 = df[mask_fresh].sort_values("mv_composite_score", ascending=False).head(25)
print(f"({len(q2)} names)")
print(q2[cols].to_string())

# CONTRARIAN BOTTOM
print()
print("--- CONTRARIAN BOTTOM: TD >= 1.0 AND AQR <= -1.0 AND rs<=30 ---")
q3 = df[(df["td_mtf_composite"] >= 1.0) & (df["aqr_trend_score"] <= -1.0) &
        (df["rs_rank_max"] <= 30)].sort_values("td_mtf_composite", ascending=False).head(25)
print(f"({len(q3)} names)")
print(q3[cols].to_string())

# SELL STRENGTH
print()
print("--- SELL STRENGTH: rs>=95 AND AQR top decile AND TD bearish OR climax_top ---")
mask_sell = ((df["rs_rank_max"] >= 95) &
             (df["aqr_trend_score"] >= df["aqr_trend_score"].quantile(0.9)) &
             (df["td_mtf_composite"] <= -1.0)) | df["mv_climax_top_warning"]
q4 = df[mask_sell].sort_values("td_mtf_composite").head(25)
print(f"({len(q4)} names)")
print(q4[cols].to_string())
