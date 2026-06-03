"""
Print top 50 per single measure from a unified momentum_rank/volume CSV.

Each section shows the top names by exactly one criterion, so you can
sort the universe by the lens you care about (momentum, base length,
compression, vol step-up, relative strength, etc.).
"""

import sys
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 260)
pd.set_option("display.float_format", "{:.2f}".format)

mom_path = sys.argv[1]
vol_path = sys.argv[2] if len(sys.argv) > 2 else None

mom = pd.read_csv(mom_path, index_col=0)
print(f"Loaded {len(mom)} rows from {mom_path}")
if vol_path:
    vol = pd.read_csv(vol_path, index_col=0)
    overlap = [c for c in vol.columns if c in mom.columns]
    if overlap:
        mom = mom.drop(columns=overlap)
    mom = mom.join(vol, how="left")
    print(f"  joined volume_screen tags from {vol_path}")

short_cols = ["name", "sector", "_cap", "last_close",
              "mom_3m", "mom_6m", "rel_return_6m_pct",
              "box_length_weeks", "box_height_pct", "pos_in_box_pct",
              "vol_drying_ratio", "atr_compression", "bb_compression",
              "vol_stepup_2w", "tags", "roque_score",
              "td_mtf_composite", "td_mtf_asymmetry", "rs_rank_max"]
short_cols = [c for c in short_cols if c in mom.columns]

def show(title, df, n=50, sort_col=None, asc=False, filter_mask=None):
    sub = df if filter_mask is None else df[filter_mask]
    if sort_col:
        sub = sub.sort_values(sort_col, ascending=asc)
    print(f"\n{'=' * 8} {title} (showing {min(n, len(sub))} of {len(sub)}) {'=' * 8}")
    print(sub[short_cols].head(n).to_string())

# --- Momentum measures ---
show("TOP 50 by 1-month momentum (mom_1m)", mom, sort_col="mom_1m")
show("TOP 50 by 3-month momentum (mom_3m)", mom, sort_col="mom_3m")
show("TOP 50 by 6-month momentum (mom_6m)", mom, sort_col="mom_6m")
show("TOP 50 by 6-month RELATIVE to SPY (rel_return_6m_pct)", mom, sort_col="rel_return_6m_pct")
show("TOP 50 by 3-month RELATIVE to SPY (rel_return_3m_pct)", mom, sort_col="rel_return_3m_pct")

# --- Base / consolidation ---
show("TOP 50 by longest box (box_length_weeks)", mom, sort_col="box_length_weeks",
     filter_mask=mom["box_length_weeks"].notna())
show("TOP 50 tightest boxes (box_height_pct asc, box>=12w)", mom, sort_col="box_height_pct", asc=True,
     filter_mask=mom["box_length_weeks"].fillna(0) >= 12)
show("TOP 50 by Roque score", mom, sort_col="roque_score")

# --- Compression / Volume ---
if "atr_compression" in mom.columns:
    show("TOP 50 most compressed (atr_compression asc)", mom, sort_col="atr_compression", asc=True,
         filter_mask=mom["atr_compression"].notna())
if "bb_compression" in mom.columns:
    show("TOP 50 most squeezed (bb_compression asc)", mom, sort_col="bb_compression", asc=True,
         filter_mask=mom["bb_compression"].notna())
if "vol_stepup_2w" in mom.columns:
    show("TOP 50 highest 2-week vol step-up", mom, sort_col="vol_stepup_2w",
         filter_mask=mom["vol_stepup_2w"].notna())
    show("TOP 50 highest 4-week vol step-up", mom, sort_col="vol_stepup_4w",
         filter_mask=mom["vol_stepup_4w"].notna() if "vol_stepup_4w" in mom.columns else None)
if "vol_drying_ratio" in mom.columns:
    show("TOP 50 most vol drying (lowest ratio, recent < prior)", mom, sort_col="vol_drying_ratio", asc=True,
         filter_mask=(mom["vol_drying_ratio"].notna()) & (mom["vol_drying_ratio"] < 1))

# --- Tag-based (binary filters) ---
for tag in ["prebreakout_w", "qulla_consol_setup", "qulla_consol_soft",
            "roque_big_base", "long_base", "very_long_base", "base_on_base",
            "darvas_tight", "near_box_top", "box_breakout",
            "base_ready", "base_forming"]:
    if tag in mom.columns:
        sub = mom[mom[tag].fillna(False)]
        if len(sub):
            show(f"ALL {tag.upper()} (sorted by box_length desc)", sub, n=50,
                 sort_col="box_length_weeks" if "box_length_weeks" in sub.columns else None)

# --- AQR-style time-series momentum (vol-normalised, tanh-summed) ---
for col, label in [
    ("aqr_trend_score", "AQR trend score (1m+3m+6m+12m vol-normalised)"),
    ("aqr_trend_1m",    "AQR 1m sub-signal"),
    ("aqr_trend_3m",    "AQR 3m sub-signal"),
    ("aqr_trend_6m",    "AQR 6m sub-signal"),
    ("aqr_trend_12m",   "AQR 12m sub-signal"),
]:
    if col in mom.columns:
        show(f"TOP 50 BULL by {label}", mom, sort_col=col,
             filter_mask=mom[col].notna())
        show(f"TOP 50 BEAR by {label}", mom, sort_col=col, asc=True,
             filter_mask=mom[col].notna())

# --- TD Sequential MTF (5 nets + composite + per-TF) ---
td_pairs = [
    ("td_mtf_net_setup",   "TD MTF net SETUP"),
    ("td_mtf_net_cd",      "TD MTF net COUNTDOWN"),
    ("td_mtf_net_perfect", "TD MTF net PERFECT"),
    ("td_mtf_net_stealth", "TD MTF net STEALTH"),
    ("td_mtf_net_triple",  "TD MTF net TRIPLE"),
    ("td_mtf_composite",   "TD MTF composite (sum of 5 nets)"),
]
for col, label in td_pairs:
    if col in mom.columns:
        show(f"TOP 50 BULLISH by {label}", mom, sort_col=col,
             filter_mask=mom[col].notna())
        show(f"TOP 50 BEARISH by {label}", mom, sort_col=col, asc=True,
             filter_mask=mom[col].notna())

# TD per-timeframe (weekly + monthly absolute and relative-to-SPY)
for tf in ["w", "m", "w_rel", "m_rel"]:
    for net in ["setup", "cd", "perfect", "stealth", "triple"]:
        col = f"td_{tf}_net_{net}"
        if col in mom.columns:
            show(f"TOP 30 BULL by {col}", mom, n=30, sort_col=col,
                 filter_mask=mom[col].notna())
            show(f"TOP 30 BEAR by {col}", mom, n=30, sort_col=col, asc=True,
                 filter_mask=mom[col].notna())

# TD intraday timeframes
for tf in ["1m", "5m", "15m", "1h", "4h"]:
    col = f"td_{tf}_net_setup"
    if col in mom.columns and mom[col].notna().any():
        for net in ["setup", "cd", "perfect", "stealth", "triple"]:
            c = f"td_{tf}_net_{net}"
            if c in mom.columns:
                show(f"TOP 30 BULL by {c}", mom, n=30, sort_col=c,
                     filter_mask=mom[c].notna())
                show(f"TOP 30 BEAR by {c}", mom, n=30, sort_col=c, asc=True,
                     filter_mask=mom[c].notna())

# --- Harmonic patterns ---
for tf in ["d", "w", "m"]:
    q = f"h_{tf}_quality"
    if q in mom.columns:
        show(f"TOP 30 highest harmonic quality on {tf}", mom, n=30,
             sort_col=q, filter_mask=mom[q].notna())

if "harmonic_score" in mom.columns:
    show("TOP 30 by harmonic_score", mom, n=30, sort_col="harmonic_score",
         filter_mask=mom["harmonic_score"].notna())
if "harmonic_consonance" in mom.columns:
    show("TOP 30 by harmonic_consonance (multi-TF agreement)", mom, n=30,
         sort_col="harmonic_consonance",
         filter_mask=mom["harmonic_consonance"].notna())

# --- Volatility asymmetry (D / W / M) ---
for tf, label in [("", "daily"), ("_w", "weekly"), ("_m", "monthly")]:
    col = f"asym{tf}_now"
    if col in mom.columns:
        show(f"TOP 30 by {label} asym_now", mom, n=30, sort_col=col,
             filter_mask=mom[col].notna())

# Relative-to-SPY asymmetry
if "rel_asym_score" in mom.columns:
    show("TOP 30 by rel_asym_score (D+W+M relative-to-SPY asym)", mom, n=30,
         sort_col="rel_asym_score", filter_mask=mom["rel_asym_score"].notna())

# --- Squeeze (compression release) ---
for tf, label in [("d", "daily"), ("w", "weekly"), ("m", "monthly")]:
    col = f"sq_{tf}_value"
    if col in mom.columns:
        show(f"TOP 30 most {label} SQUEEZED (sq_value asc)", mom, n=30,
             sort_col=col, asc=True, filter_mask=mom[col].notna())
    rel = f"sq_{tf}_pct_of_max"
    if rel in mom.columns:
        show(f"TOP 30 lowest {label} sq_pct_of_max", mom, n=30,
             sort_col=rel, asc=True, filter_mask=mom[rel].notna())

# --- TD exhaustion score (composite of bullish vs bearish flags) ---
if "td_exhaustion_score" in mom.columns:
    show("TOP 30 BULL td_exhaustion_score", mom, n=30,
         sort_col="td_exhaustion_score", filter_mask=mom["td_exhaustion_score"].notna())
    show("TOP 30 BEAR td_exhaustion_score", mom, n=30,
         sort_col="td_exhaustion_score", asc=True,
         filter_mask=mom["td_exhaustion_score"].notna())

# --- Relative-strength / momentum measures already in mom ---
for col in ["rs_rank_max", "atr_rs", "dma200_slope_pct", "days_since_52w_high",
            "macd_hist_w"]:
    if col in mom.columns:
        ascv = col in ("days_since_52w_high",)
        show(f"TOP 30 by {col}", mom, n=30, sort_col=col, asc=ascv,
             filter_mask=mom[col].notna())

# --- Boolean flags as filters ---
for flag in ["td_bullish_exhaustion", "td_bullish_exhaustion_strong",
             "td_bearish_exhaustion", "td_bearish_exhaustion_strong",
             "breakout_squeeze", "breakout_squeeze_strict",
             "q_method_pass", "q_method_pass_monthly_strong",
             "harmonic_bullish_w_or_m"]:
    if flag in mom.columns:
        sub = mom[mom[flag].fillna(False)]
        if len(sub):
            sort_c = "td_mtf_composite" if "td_mtf_composite" in sub.columns else "roque_score"
            show(f"ALL {flag.upper()} ({len(sub)}) sorted by {sort_c}", sub,
                 n=50, sort_col=sort_c)

# --- Volume_screen tag-based (counts of substrings) ---
if "tags" in mom.columns:
    tags_str = mom["tags"].fillna("")
    for substr in ["COILED_TIGHT", "COILED", "BREAKOUT_FIRING", "STRONG_VOLUME",
                    "NEAR_POC_13w", "AT_VALUE_13w"]:
        mask = tags_str.str.contains(substr)
        if mask.any():
            sub = mom[mask].copy()
            sort_c = "vol_stepup_2w" if "vol_stepup_2w" in sub.columns else None
            show(f"ALL {substr} (sorted by vol_stepup_2w desc)", sub, n=50, sort_col=sort_c)
