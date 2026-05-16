"""Quick Q-tier breakdown of an existing momentum_rank CSV."""
import sys
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 240)
pd.set_option("display.float_format", "{:.2f}".format)

path = sys.argv[1]
df = pd.read_csv(path, index_col=0)

base_ready = df[df["base_ready"]]
base_forming = df[df["base_forming"]]
uptrend = df[df["uptrend_w"]]
not_extended = df[df["uptrend_w"] & (~df["extended_w"])]
extended = df[df["extended_w"]]

print(f"Universe rows: {len(df)}")
print(f"  in uptrend (10wma > 30wma):        {len(uptrend)}")
print(f"  in uptrend AND not extended_w:     {len(not_extended)}")
print(f"  extended_w (dist_wma30 > 40%):     {len(extended)}")
print(f"  BASE_READY (full criteria):        {len(base_ready)}")
print(f"  BASE_FORMING (almost ready):       {len(base_forming)}")

cols = ["name", "sector", "last_close", "mom_3m", "mom_6m",
        "dist_wma10_pct", "dist_wma30_pct",
        "range_4w_w_pct", "range_8w_w_pct",
        "pullback_4w_w_pct", "pullback_8w_w_pct",
        "weeks_since_8w_high", "vol_drying_ratio",
        "near_10wma", "tight_base_w", "pullback_w",
        "consolidating", "vol_drying", "base_ready", "base_forming", "q_score"]
cols = [c for c in cols if c in df.columns]

if len(base_ready):
    print("\n=== BASE_READY ===")
    print(base_ready[cols].sort_values("q_score").to_string())

if len(base_forming):
    print("\n=== BASE_FORMING ===")
    print(base_forming[cols].sort_values("q_score").to_string())

# Sort by q_score and show top 15 most-Q-friendly even if not BASE_READY yet
print("\n=== Top 15 by q_score (lower = more Q-like) ===")
print(df.sort_values("q_score")[cols].head(15).to_string())
