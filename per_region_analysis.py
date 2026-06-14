"""Per-region equity analysis built on the corrected consolidated dataset.

For each region (US, EU, UK, JP, CN, KR, TW, IN, OCEANIA, LATAM, MENA,
AFRICA, AMER/CA), produces:

  - Region summary (n, sector breadth, breadth stats, rotation map)
  - Pre-Run top 30: high-conviction setups not yet extended
  - Bow-Tie + 3w-Tight fresh emergence
  - True VCP (count >= 3) with USD ADV >= region's institutional floor
  - Bottoming with recovery evidence (TD bull + AQR bear + structure)
  - Sell strength (rs >= 90 + TD bear + extended)
  - Intra-region intra-sector pair candidates
  - Sector x country pivot inside the region

Operates only on common-equity rows (security_type == 'common'), uses
USD-normalised ADV, and the corrected VCP scores.
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np


# ============================================================
# Region mapping
# ============================================================
REGION_MAP = {
    "us-all":      ("US", "USD", 20),       # institutional floor in USD millions
    "uk-all":      ("UK", "GBP", 5),
    "wiki-r1k":    ("US", "USD", 20),
    "wiki-aim100": ("UK", "GBP", 1),
    # EU continental
    "de-all":  ("EU/DE",  "EUR", 10),
    "fr-all":  ("EU/FR",  "EUR", 10),
    "ch-all":  ("EU/CH",  "CHF", 5),
    "it-all":  ("EU/IT",  "EUR", 5),
    "es-all":  ("EU/ES",  "EUR", 5),
    "nl-all":  ("EU/NL",  "EUR", 5),
    "se-all":  ("EU/SE",  "SEK", 5),
    "be-all":  ("EU/BE",  "EUR", 3),
    "no-all":  ("EU/NO",  "NOK", 3),
    "dk-all":  ("EU/DK",  "DKK", 3),
    "fi-all":  ("EU/FI",  "EUR", 3),
    "ie-all":  ("EU/IE",  "EUR", 3),
    "pt-all":  ("EU/PT",  "EUR", 3),
    "at-all":  ("EU/AT",  "EUR", 3),
    "gr-all":  ("EU/GR",  "EUR", 3),
    "eu-smid": ("EU/SMID","EUR", 5),
    "eu-large":("EU/LRG", "EUR", 20),
    "eu-micro":("EU/MIC", "EUR", 1),
    "eu-nano": ("EU/NANO","EUR", 1),
    # Asia-Pacific
    "jp-all":  ("ASIA/JP", "JPY", 10),
    "cn-all":  ("ASIA/CN", "CNY", 10),
    "kr-all":  ("ASIA/KR", "KRW", 10),
    "tw-all":  ("ASIA/TW", "TWD", 10),
    "hk-all":  ("ASIA/HK", "HKD", 10),
    "in-all":  ("ASIA/IN", "INR", 5),
    "sg-all":  ("ASIA/SG", "SGD", 5),
    "th-all":  ("ASIA/TH", "THB", 5),
    "id-all":  ("ASIA/ID", "IDR", 5),
    "il-all":  ("ASIA/IL", "ILS", 5),
    "sa-all":  ("ASIA/SA", "SAR", 5),
    "tr-all":  ("ASIA/TR", "TRY", 5),
    # Oceania
    "au-all":  ("OCEANIA", "AUD", 10),
    "nz-all":  ("OCEANIA", "NZD", 3),
    # Latam
    "br-all":  ("LATAM", "BRL", 10),
    "mx-all":  ("LATAM", "MXN", 5),
    "ar-all":  ("LATAM", "ARS", 3),
    "cl-all":  ("LATAM", "CLP", 3),
    # Africa
    "za-all":  ("AFRICA", "ZAR", 5),
    # Americas
    "ca-all":  ("AMER/CA", "CAD", 5),
}

# Roll up sub-regions to broader bands for the master Pre-Run tables
SUPER_REGION = {
    "US": "US",
    "UK": "UK",
}
def super_region(r):
    if r in ("US", "UK"):
        return r
    if r.startswith("EU/"): return "EU"
    if r.startswith("ASIA/"): return "ASIA"
    return r  # OCEANIA, LATAM, AFRICA, AMER/CA already broad


# ============================================================
# Load + sanitise
# ============================================================
def load_and_prep(path="global_equities_consolidated.csv"):
    df = pd.read_csv(path, index_col=0, low_memory=False)
    bools = ['mv_setup_premium','mv_setup_clean','mv_power_trend','mv_3w_tight',
             'mv_bow_tie','mv_high_tight_flag','mv_vcp_with_volume',
             'mv_buyable_gap_up','mv_at_ath','mv_in_buy_zone','mv_at_pivot',
             'mv_pocket_pivot','mv_stage2_pass','mv_stage4_pass',
             'mv_climax_top_warning','q_method_pass','base_ready','prebreakout_w',
             'long_base','darvas_tight','asym_w_above_ma','sq_w_just_release',
             'sq_m_just_release','harmonic_bullish_w_or_m','macd_above_signal',
             'extended_w','base_forming','very_long_base','base_on_base',
             'near_box_top','box_breakout','consolidating','vol_drying','uptrend_w']
    for c in bools:
        if c in df.columns:
            df[c] = df[c].astype(str).str.lower().isin(["true","1","yes"])
    skip = {"name","sector","_universe","security_type","_ccy","fb_lists","tags",
            "adv_tier","_cap","h_d_pattern","h_d_direction","h_w_pattern",
            "h_w_direction","h_m_pattern","h_m_direction"}
    for c in df.columns:
        if c not in skip and c not in bools and df[c].dtype == "object":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # Dedupe per ticker, keep highest mv_composite
    df = df.sort_values("mv_composite_score", ascending=False, na_position="last")
    df = df[~df.index.duplicated(keep="first")]
    # Equity-only
    if "security_type" in df.columns:
        df = df[df["security_type"] == "common"].copy()
    # Use USD-normalised ADV as the default for cross-region comparison
    if "adv_20d_usd_millions" in df.columns:
        df["adv_local_millions"] = df.get("adv_20d_millions")
        df["adv"] = df["adv_20d_usd_millions"]
    else:
        df["adv"] = df.get("adv_20d_millions", np.nan)
    # Tag region + super-region
    df["region"] = df["_universe"].map(lambda u: REGION_MAP.get(u, ("OTHER","-",0))[0])
    df["super_region"] = df["region"].map(super_region)
    df["region_floor_usd_m"] = df["_universe"].map(lambda u: REGION_MAP.get(u, ("OTHER","-",0))[2])
    return df


# ============================================================
# Scoring helpers
# ============================================================
def add_scores(df):
    def safe(c, d=0): return df[c].fillna(d) if c in df.columns else d
    def b(c): return df[c].fillna(False) if c in df.columns else pd.Series(False, index=df.index)

    df["setup_quality"] = (
        b("mv_setup_premium").astype(int)*4
        + b("mv_power_trend").astype(int)*3
        + b("mv_3w_tight").astype(int)*3
        + b("mv_bow_tie").astype(int)*4
        + b("mv_vcp_with_volume").astype(int)*3
        + b("mv_high_tight_flag").astype(int)*4
        + b("base_ready").astype(int)*3
        + b("base_forming").astype(int)*2
        + b("prebreakout_w").astype(int)*3
        + b("long_base").astype(int)*2
        + b("very_long_base").astype(int)*2
        + b("darvas_tight").astype(int)*2
        + (b("sq_w_just_release").astype(bool) | b("sq_m_just_release").astype(bool)).astype(int)*3
        + b("q_method_pass").astype(int)*2
        + (safe("roque_score") >= 7).astype(int)*2
        + b("asym_w_above_ma").astype(int)*1
        + (safe("mv_stage2_count") >= 8).astype(int)*2
    )
    df["early_stage"] = (
        safe("rs_rank_max").apply(lambda x: 6 if x <= 30 else 5 if x <= 50 else 4 if x <= 70 else 3 if x <= 80 else 2 if x <= 90 else 1 if x <= 95 else 0)
        + safe("mom_6m").apply(lambda x: 4 if 0.95 <= x <= 1.10 else 3 if x <= 1.20 else 2 if x <= 1.30 else 1 if x <= 1.50 else 0)
        + safe("dist_sma50_pct").apply(lambda x: 3 if -2 <= x <= 5 else 2 if -5 <= x <= 10 else 1 if x <= 15 else 0)
        + (~b("mv_at_ath")).astype(int)*2
        + (~b("extended_w")).astype(int)*2
        + (~b("mv_climax_top_warning")).astype(int)*1
        + safe("mv_dist_from_ath_pct").apply(lambda x: 2 if 5 <= x <= 25 else 1 if 0 < x < 5 else 0)
    )
    # Liquidity tier uses USD ADV (which now is comparable across regions)
    df["liquidity_building"] = (
        df["adv"].fillna(0).apply(lambda x: 4 if x >= 500 else 3 if x >= 100 else 2 if x >= 50 else 1 if x >= 20 else 0)
        + safe("adv_slope_pct_wk").apply(lambda x: 3 if x >= 5 else 2 if x >= 2 else 1 if x > 0 else 0)
        + safe("adv_accel").apply(lambda x: 2 if x >= 5 else 1 if x > 0 else 0)
        + safe("adv_20_over_60").apply(lambda x: 2 if x >= 1.2 else 1 if x >= 1.05 else 0)
        + safe("aqr_trend_score").apply(lambda x: 2 if 0.5 <= x <= 2.0 else 1 if 0 < x < 0.5 else 0)
        + safe("td_mtf_composite").apply(lambda x: 2 if x >= 0.3 else 1 if x >= 0 else 0)
    )
    df["pre_run_score"] = df["setup_quality"] + df["early_stage"] + df["liquidity_building"]
    df["bull_score"] = (
        (safe("aqr_trend_score") >= 1.0).astype(int)*2
        + (safe("td_mtf_composite") >= 0.5).astype(int)
        + (safe("roque_score") >= 7).astype(int)
        + b("q_method_pass").astype(int)
        + b("base_ready").astype(int)
        + b("prebreakout_w").astype(int)
        + b("long_base").astype(int)
        + b("darvas_tight").astype(int)
        + (b("sq_w_just_release").astype(bool) | b("sq_m_just_release").astype(bool)).astype(int)
        + b("asym_w_above_ma").astype(int)
        + b("mv_setup_premium").astype(int)
        + b("mv_power_trend").astype(int)
        + b("mv_3w_tight").astype(int)
        + b("mv_bow_tie").astype(int)
        + b("base_forming").astype(int)
    )
    return df


# ============================================================
# Per-region cuts
# ============================================================
COLS_BULL = ["name","_universe","_ccy","sector","last_close","rs_rank_max",
             "mom_3m","mom_6m","dist_sma50_pct","mv_dist_from_ath_pct",
             "aqr_trend_score","td_mtf_composite","mv_composite_score",
             "mv_stage2_count","mv_vcp_count","mv_power_trend","mv_3w_tight",
             "mv_bow_tie","mv_at_ath","base_ready","prebreakout_w",
             "adv","adv_local_millions","adv_slope_pct_wk","adv_20_over_60",
             "setup_quality","early_stage","liquidity_building","pre_run_score","bull_score"]
COLS_BEAR = ["name","_universe","_ccy","sector","last_close","rs_rank_max",
             "mom_3m","mom_6m","mv_dist_from_ath_pct",
             "td_mtf_composite","td_w_sell_setup","td_w_sell_cd",
             "td_m_sell_setup","td_m_sell_cd","aqr_trend_score","extended_w",
             "mv_climax_top_warning","mv_stage4_count","mv_stage4_pass",
             "adv","adv_slope_pct_wk"]


def per_region_sheets(df, region):
    """Build the sheets for one super-region."""
    rdf = df[df["super_region"] == region].copy()
    if len(rdf) == 0:
        return {}
    sheets = {}

    # 1. Pre-Run top 30 (regional)
    s1 = rdf.sort_values("pre_run_score", ascending=False).head(30)
    sheets[f"{region} Pre-Run Top 30"] = s1[[c for c in COLS_BULL if c in s1.columns]]

    # 2. Multi-Framework Bull (bull_score >= 7)
    mfb = rdf[rdf["bull_score"] >= 7].sort_values("bull_score", ascending=False).head(30)
    if len(mfb):
        sheets[f"{region} Multi-Framework Bull"] = mfb[[c for c in COLS_BULL if c in mfb.columns]]

    # 3. True VCP (count >= 3) with USD ADV >= 20M (institutional)
    vcp = rdf[(rdf["mv_vcp_count"].fillna(0) >= 3) & (rdf["adv"].fillna(0) >= 20)] \
            .sort_values("mv_composite_score", ascending=False).head(30)
    if len(vcp):
        sheets[f"{region} True VCP"] = vcp[[c for c in COLS_BULL if c in vcp.columns]]

    # 4. Bow Tie fresh emergence
    bt = rdf[rdf["mv_bow_tie"]].sort_values("mv_composite_score", ascending=False).head(30)
    if len(bt):
        sheets[f"{region} Bow Tie"] = bt[[c for c in COLS_BULL if c in bt.columns]]

    # 5. Bottoming with recovery evidence (TD bull + AQR bear + structure rebuilding)
    bot_mask = (rdf["aqr_trend_score"].fillna(0) <= -1.0) & (rdf["td_mtf_composite"].fillna(0) >= 0.3)
    bot = rdf[bot_mask].copy()
    if "macd_above_signal" in bot.columns:
        bot["recovery"] = (
            bot["base_ready"].fillna(False).astype(int)
            + bot["base_forming"].fillna(False).astype(int)
            + bot["vol_drying"].fillna(False).astype(int)
            + bot["macd_above_signal"].fillna(False).astype(int)
            + bot["near_box_top"].fillna(False).astype(int)
            + bot["asym_w_above_ma"].fillna(False).astype(int)
            + (bot["dist_sma50_pct"].fillna(-99) > 0).astype(int)
            + (bot["adv_slope_pct_wk"].fillna(-99) > 0).astype(int)
        )
        bot = bot[bot["recovery"] >= 4].sort_values(["recovery","td_mtf_composite"], ascending=False).head(30)
        if len(bot):
            cols = [c for c in COLS_BULL if c in bot.columns] + ["recovery"]
            sheets[f"{region} Bottoming + Recovery"] = bot[cols]

    # 6. Sell Strength (rs >= 90 + TD bear + extended)
    ss = rdf[((rdf["rs_rank_max"].fillna(0) >= 90)
              & (rdf["td_mtf_composite"].fillna(0) <= -1.0)
              & (rdf["aqr_trend_score"].fillna(0) >= 1.5))
             | rdf["mv_climax_top_warning"].fillna(False)] \
           .sort_values("td_mtf_composite").head(30)
    if len(ss):
        sheets[f"{region} Sell Strength"] = ss[[c for c in COLS_BEAR if c in ss.columns]]

    # 7. Sector rotation table for this region
    sec = rdf.groupby("sector").agg(
        n=("last_close","count"),
        aqr=("aqr_trend_score","mean"),
        td=("td_mtf_composite","mean"),
        mv=("mv_composite_score","mean"),
        bot_pct=("td_mtf_composite", lambda s: 100*((s>=0.3) & (rdf.loc[s.index, "aqr_trend_score"]<=-1.0)).mean()),
        ext_pct=("td_mtf_composite", lambda s: 100*((s<=-0.3) & (rdf.loc[s.index, "aqr_trend_score"]>=1.0)).mean()),
        pct_premium=("mv_setup_premium", lambda s: 100*s.mean()),
        pct_at_ath=("mv_at_ath", lambda s: 100*s.mean()),
        pct_stage4=("mv_stage4_pass", lambda s: 100*s.mean()),
    ).reset_index()
    sec["net_rot"] = sec["bot_pct"] - sec["ext_pct"]
    sec = sec[sec["n"] >= 10].sort_values("net_rot", ascending=False).round(2)
    if len(sec):
        sheets[f"{region} Sector Rotation"] = sec

    # 8. Intra-region intra-sector pairs
    pair_rows = []
    for s in rdf["sector"].dropna().unique():
        in_sec = rdf[rdf["sector"] == s]
        longs = in_sec[(in_sec["td_mtf_composite"].fillna(0) >= 0.5)
                        & (in_sec["adv"].fillna(0) >= 20)
                        & (in_sec["rs_rank_max"].fillna(100) <= 75)]
        shorts = in_sec[(in_sec["td_mtf_composite"].fillna(0) <= -1.0)
                         & (in_sec["adv"].fillna(0) >= 20)
                         & (in_sec["rs_rank_max"].fillna(0) >= 90)]
        if not len(longs) or not len(shorts): continue
        lt = longs.sort_values("td_mtf_composite", ascending=False).head(2)
        st = shorts.sort_values("td_mtf_composite").head(2)
        for li, lr in lt.iterrows():
            for si, sr in st.iterrows():
                pair_rows.append({
                    "sector": s,
                    "long_tkr": li, "long_name": lr.get("name",""), "long_uni": lr["_universe"],
                    "long_rs": lr["rs_rank_max"], "long_td": lr["td_mtf_composite"],
                    "long_aqr": lr["aqr_trend_score"], "long_adv_USDM": lr["adv"],
                    "short_tkr": si, "short_name": sr.get("name",""), "short_uni": sr["_universe"],
                    "short_rs": sr["rs_rank_max"], "short_td": sr["td_mtf_composite"],
                    "short_aqr": sr["aqr_trend_score"], "short_adv_USDM": sr["adv"],
                    "rs_spread": sr["rs_rank_max"] - lr["rs_rank_max"],
                    "td_spread": lr["td_mtf_composite"] - sr["td_mtf_composite"],
                })
    if pair_rows:
        sheets[f"{region} Sector-Neutral Pairs"] = pd.DataFrame(pair_rows).sort_values("td_spread", ascending=False)

    return sheets


# ============================================================
# Summary
# ============================================================
def build_summary(df):
    """Region-level master summary."""
    rows = []
    for r in sorted(df["super_region"].unique()):
        rdf = df[df["super_region"] == r]
        bot = ((rdf["aqr_trend_score"].fillna(0) <= -1.0)
               & (rdf["td_mtf_composite"].fillna(0) >= 0.3)).sum()
        ext = ((rdf["aqr_trend_score"].fillna(0) >= 1.0)
               & (rdf["td_mtf_composite"].fillna(0) <= -0.3)).sum()
        rows.append({
            "region": r,
            "n": len(rdf),
            "aqr_mean": round(rdf["aqr_trend_score"].mean(), 2),
            "td_mean": round(rdf["td_mtf_composite"].mean(), 2),
            "mv_mean": round(rdf["mv_composite_score"].mean(), 2),
            "premium_n": int(rdf["mv_setup_premium"].sum()),
            "power_trend_n": int(rdf["mv_power_trend"].sum()),
            "true_vcp_n": int((rdf["mv_vcp_count"].fillna(0) >= 3).sum()),
            "bow_tie_n": int(rdf["mv_bow_tie"].sum()),
            "at_ath_n": int(rdf["mv_at_ath"].sum()),
            "stage4_n": int(rdf["mv_stage4_pass"].sum()),
            "bottoming_n": int(bot),
            "exhausting_n": int(ext),
            "net_rotation_pp": round(100*(bot-ext)/max(len(rdf),1), 2),
            "median_adv_usd_M": round(rdf["adv"].median(), 2),
            "p90_adv_usd_M": round(rdf["adv"].quantile(0.9), 2),
        })
    return pd.DataFrame(rows).sort_values("net_rotation_pp", ascending=False)


# ============================================================
# Driver
# ============================================================
def main():
    df = load_and_prep()
    print(f"Loaded {len(df)} common-equity rows across {df['super_region'].nunique()} super-regions")
    df = add_scores(df)

    sheets = {"Region Summary": build_summary(df)}

    # Walk super regions in priority order
    for region in ["US", "EU", "UK", "ASIA", "LATAM", "OCEANIA", "AMER/CA", "AFRICA"]:
        sheets.update(per_region_sheets(df, region))

    # Write xlsx with formatting
    out_path = "per_region_analysis.xlsx"
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        for name, sheet_df in sheets.items():
            # Excel disallows / \ : * ? [ ] in sheet names
            safe_name = name.replace("/", "-").replace("\\", "-").replace(":", "-")[:31]
            if sheet_df.index.name is None and "Pairs" not in name and "Summary" not in name and "Rotation" not in name:
                sheet_df = sheet_df.copy()
                sheet_df.index.name = "Ticker"
                sheet_df = sheet_df.reset_index()
            sheet_df.to_excel(writer, sheet_name=safe_name, index=False)
            ws = writer.sheets[safe_name]
            wb = writer.book
            header_fmt = wb.add_format({"bold": True, "bg_color": "#1F4E78",
                                         "font_color": "white", "border": 1})
            ws.set_row(0, None, header_fmt)
            ws.freeze_panes(1, 1)
            for ci, col in enumerate(sheet_df.columns):
                ml = max(len(str(col)),
                          *(min(len(str(v)), 50) for v in sheet_df[col].head(40).fillna(""))) + 2
                ws.set_column(ci, ci, min(ml, 28))
            for sc in ["pre_run_score", "mv_composite_score", "aqr_trend_score",
                       "td_mtf_composite", "bull_score", "net_rot", "net_rotation_pp"]:
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

    print(f"\nWrote {out_path}")
    print("Sheets:")
    for k in sheets:
        print(f"  - {k} ({len(sheets[k])} rows)")


if __name__ == "__main__":
    main()
