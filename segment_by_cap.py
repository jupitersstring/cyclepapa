"""Segment momentum_rank CSVs by financedatabase market_cap classification.

US per-cap bands (us-nano, us-micro, us-small, us-mid, us-large, us-mega)
are already inside the cached us-all run. This script joins the
consolidated global CSV with financedatabase's market_cap column and
writes one CSV per cap band, plus prints top-N tables per band.

Equivalent for EU once eu-large/-micro/-nano caches complete.
"""

import sys
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import financedatabase as fd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 280)
pd.set_option("display.float_format", "{:.2f}".format)

eq = fd.Equities()
us_meta = eq.select(country="United States")[["market_cap", "exchange", "sector"]]
us_meta = us_meta[~us_meta.index.duplicated(keep="first")]

eu_countries = ["United Kingdom","Germany","France","Italy","Spain","Netherlands",
                "Switzerland","Sweden","Belgium","Norway","Denmark","Finland",
                "Ireland","Austria","Portugal","Greece","Poland","Czech Republic",
                "Hungary","Luxembourg"]
eu_frames = [eq.select(country=c)[["market_cap","exchange","sector"]] for c in eu_countries]
eu_meta = pd.concat(eu_frames)
eu_meta = eu_meta[~eu_meta.index.duplicated(keep="first")]
eu_meta["_country"] = "EU"

us_meta["_country"] = "US"
all_meta = pd.concat([us_meta, eu_meta])
all_meta = all_meta[~all_meta.index.duplicated(keep="first")]

df = pd.read_csv("global_equities_consolidated.csv", index_col=0, low_memory=False)
# Join market_cap from fd
df = df.join(all_meta[["market_cap"]].rename(columns={"market_cap": "_fd_cap"}))
print(f"After join: {len(df)} rows, market_cap populated for {df['_fd_cap'].notna().sum()}")
print()

CAP_GROUPS = {
    "us-nano":   {"_universe": ["us-all"], "caps": ["Nano Cap"]},
    "us-micro":  {"_universe": ["us-all"], "caps": ["Micro Cap"]},
    "us-small":  {"_universe": ["us-all"], "caps": ["Small Cap"]},
    "us-mid":    {"_universe": ["us-all"], "caps": ["Mid Cap"]},
    "us-large":  {"_universe": ["us-all"], "caps": ["Large Cap"]},
    "us-mega":   {"_universe": ["us-all"], "caps": ["Mega Cap"]},
    "eu-large":  {"_universe": ["eu-smid","de-all","fr-all","it-all","ch-all","es-all",
                                "nl-all","se-all","be-all","no-all","dk-all","fi-all",
                                "ie-all","pt-all","at-all","gr-all","uk-all"],
                  "caps": ["Large Cap","Mega Cap"]},
    "eu-mid":    {"_universe": ["eu-smid","de-all","fr-all","it-all","ch-all","es-all",
                                "nl-all","se-all","be-all","no-all","dk-all","fi-all",
                                "ie-all","pt-all","at-all","gr-all","uk-all"],
                  "caps": ["Mid Cap"]},
    "eu-small":  {"_universe": ["eu-smid","de-all","fr-all","it-all","ch-all","es-all",
                                "nl-all","se-all","be-all","no-all","dk-all","fi-all",
                                "ie-all","pt-all","at-all","gr-all","uk-all"],
                  "caps": ["Small Cap"]},
    "eu-micro":  {"_universe": ["eu-smid","de-all","fr-all","it-all","ch-all","es-all",
                                "nl-all","se-all","be-all","no-all","dk-all","fi-all",
                                "ie-all","pt-all","at-all","gr-all","uk-all"],
                  "caps": ["Micro Cap"]},
    "eu-nano":   {"_universe": ["eu-smid","de-all","fr-all","it-all","ch-all","es-all",
                                "nl-all","se-all","be-all","no-all","dk-all","fi-all",
                                "ie-all","pt-all","at-all","gr-all","uk-all"],
                  "caps": ["Nano Cap"]},
}

cols_summary = ["name","_universe","sector","_fd_cap","last_close",
                "mv_composite_score","mv_stage2_count","mv_power_trend",
                "mv_3w_tight","mv_at_ath","aqr_trend_score","td_mtf_composite",
                "rs_rank_max","ma_d50_strategy_ir"]
cols_summary = [c for c in cols_summary if c in df.columns]

print(f"{'Band':12s} {'Total':>8s} {'Premium':>8s} {'Stage2':>8s} {'AtATH':>8s}  Top names by mv_composite_score")
print("-" * 130)
for band, spec in CAP_GROUPS.items():
    sub = df[df["_universe"].isin(spec["_universe"]) & df["_fd_cap"].isin(spec["caps"])]
    n = len(sub)
    if "mv_setup_premium" in sub.columns:
        prem = sub["mv_setup_premium"].astype(str).str.lower().isin(["true","1"]).sum()
    else:
        prem = 0
    s2 = sub.get("mv_stage2_pass", pd.Series(dtype=bool)).astype(str).str.lower().isin(["true","1"]).sum()
    ath = sub.get("mv_at_ath", pd.Series(dtype=bool)).astype(str).str.lower().isin(["true","1"]).sum()
    if n == 0:
        continue
    sub["_mvc"] = pd.to_numeric(sub.get("mv_composite_score"), errors="coerce")
    top = sub.sort_values("_mvc", ascending=False).head(5)
    top_names = ", ".join([f"{i}" for i in top.index[:5]])
    print(f"{band:12s} {n:>8d} {prem:>8d} {s2:>8d} {ath:>8d}  {top_names}")

# Write per-band CSVs
for band, spec in CAP_GROUPS.items():
    sub = df[df["_universe"].isin(spec["_universe"]) & df["_fd_cap"].isin(spec["caps"])]
    if len(sub) == 0:
        continue
    out_path = f"momentum_rank_{band}_segmented.csv"
    sub.to_csv(out_path)
    print(f"  wrote {out_path} ({len(sub)} rows)")
