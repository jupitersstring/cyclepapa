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
              "vol_stepup_2w", "tags", "roque_score"]
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
