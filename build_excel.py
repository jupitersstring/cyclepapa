"""Build an Excel workbook with top picks per tab + headline financials.

Reads /tmp/stars_aligned_*.csv. Defines several tabs (Global, Uncorrelated,
US, Europe, Japan, Asia, AU/NZ, Regime-Change, Cross-TF). For each pick
pulls market cap, P/E, P/B, profit margin, RoE, revenue growth, sector,
industry, country, and short business summary via yfinance.

Output: /tmp/stars_aligned_top_picks.xlsx
"""

import sys
import glob
import time
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

OUT_PATH = "/tmp/stars_aligned_top_picks.xlsx"
TOP_N_DEFAULT = 25


def is_native(t):
    if not isinstance(t, str):
        return False
    if "." not in t:
        return True
    suf = "." + t.rsplit(".", 1)[1]
    return suf in {
        ".L", ".PA", ".AS", ".BR", ".LS", ".IR", ".MI", ".MC", ".SW", ".VI",
        ".DE", ".ST", ".OL", ".CO", ".HE", ".AT",      # EU
        ".T", ".JP",                                    # Japan
        ".HK", ".SI", ".KS", ".KQ", ".TW", ".NS", ".BO",
        ".SS", ".SZ", ".AX", ".NZ",                     # Asia/Pac
    }


def load_all():
    rows = []
    for p in sorted(glob.glob("/tmp/stars_aligned_*.csv")):
        region = p.split("stars_aligned_")[-1].replace(".csv", "")
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        df["region"] = region
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


REGION_GROUPS = {
    "US":              ["us-small", "us-mid", "fd-us-micro", "fd-us-large", "fd-us-mega"],
    "Europe":          ["fd-eu-mega", "fd-eu-large", "fd-eu-mid",
                        "fd-eu-small", "fd-eu-micro", "fd-eu-nano"],
    "Japan":           ["fd-jp-large", "fd-jp-mid", "fd-jp-small", "fd-jp-micro"],
    "Asia_ex_Japan":   ["fd-asia-ex-jp", "fd-asia-small"],
    "Australia_NZ":    ["fd-au"],
}


def pick_top(df, n, rank_col="best_rank"):
    return (df.sort_values(rank_col, ascending=False)
              .drop_duplicates(subset=["ticker"], keep="first")
              .head(n))


def get_info(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        return {
            "longName":              info.get("longName") or info.get("shortName"),
            "country":               info.get("country"),
            "sector":                info.get("sector"),
            "industry":              info.get("industry"),
            "marketCap":             info.get("marketCap"),
            "currency":              info.get("currency"),
            "trailingPE":            info.get("trailingPE"),
            "forwardPE":             info.get("forwardPE"),
            "priceToBook":           info.get("priceToBook"),
            "profitMargins":         info.get("profitMargins"),
            "returnOnEquity":        info.get("returnOnEquity"),
            "revenueGrowth":         info.get("revenueGrowth"),
            "earningsGrowth":        info.get("earningsGrowth"),
            "debtToEquity":          info.get("debtToEquity"),
            "dividendYield":         info.get("dividendYield"),
            "summary":               (info.get("longBusinessSummary") or "")[:600],
            "website":               info.get("website"),
        }
    except Exception:
        return {}


def main():
    big = load_all()
    big = big[big.ticker.apply(is_native)].copy()
    big["best_rank"] = big[["daily_rank", "weekly_rank", "monthly_rank"]].max(axis=1)
    not_rejected = (
        (big.daily_label != "Reject") |
        (big.weekly_label != "Reject") |
        (big.monthly_label != "Reject")
    )
    big = big[not_rejected].copy()
    print(f"Pool: {len(big)} non-rejected native tickers", file=sys.stderr)

    # Build tab DataFrames
    tabs = {}

    # 1. Global Top 30
    tabs["Global_Top30"] = pick_top(big, 30)

    # 2. Per-region groups
    for label, regions in REGION_GROUPS.items():
        sub = big[big.region.isin(regions)]
        if len(sub) > 0:
            n = 30 if label in ("US", "Europe") else 20
            tabs[label] = pick_top(sub, n)

    # 3. Cross-TF confluence — best on all three TFs simultaneously
    cross_tf = big[
        (big.daily_rank > 50) & (big.weekly_rank > 50) & (big.monthly_rank > 50) &
        (big.daily_label != "Reject") & (big.weekly_label != "Reject") &
        (big.monthly_label != "Reject")
    ].copy()
    cross_tf["min_rank"] = cross_tf[["daily_rank", "weekly_rank", "monthly_rank"]].min(axis=1)
    tabs["Cross_TF_Confluence"] = (cross_tf.sort_values("min_rank", ascending=False)
                                            .drop_duplicates(subset=["ticker"])
                                            .head(25))

    # 4. Regime change leaders
    rc = big[(big.R_W >= 85) & (big.weekly_label != "Reject")].copy()
    rc = rc.sort_values("R_W", ascending=False).drop_duplicates(subset=["ticker"]).head(25)
    tabs["Regime_Change"] = rc

    # 5. Per-measure leaders on weekly TF (excluding rejected)
    weekly_ok = big[big.weekly_label != "Reject"].copy()
    for measure, col in [
        ("Top_Weinstein_W",    "W_W"),
        ("Top_Qullamaggie_W",  "Q_W"),
        ("Top_DeMark_W",       "D_W"),
        ("Top_Darvas_W",       "DA_W"),
        ("Top_Regime_W",       "R_W"),
    ]:
        tabs[measure] = (weekly_ok.sort_values(col, ascending=False)
                                    .drop_duplicates(subset=["ticker"])
                                    .head(25)
                                    .reset_index(drop=True))

    # 6. Per-measure leaders on monthly TF
    monthly_ok = big[big.monthly_label != "Reject"].copy()
    for measure, col in [
        ("Top_Weinstein_M",    "W_M"),
        ("Top_Qullamaggie_M",  "Q_M"),
        ("Top_DeMark_M",       "D_M"),
        ("Top_Darvas_M",       "DA_M"),
        ("Top_Regime_M",       "R_M"),
    ]:
        tabs[measure] = (monthly_ok.sort_values(col, ascending=False)
                                     .drop_duplicates(subset=["ticker"])
                                     .head(25)
                                     .reset_index(drop=True))

    # 7. All-schools confluence (every weekly school score >= 60)
    all_schools = big[
        (big.W_W >= 60) & (big.Q_W >= 60) & (big.D_W >= 55) & (big.DA_W >= 55) &
        (big.weekly_label != "Reject")
    ].copy()
    all_schools["mean_school"] = all_schools[["W_W","Q_W","D_W","DA_W"]].mean(axis=1)
    tabs["All_Schools_60plus"] = (all_schools.sort_values("mean_school", ascending=False)
                                              .drop_duplicates(subset=["ticker"])
                                              .head(30)
                                              .reset_index(drop=True))

    # 5. Uncorrelated portfolio
    try:
        unc = pd.read_csv("/tmp/cross_region_top_uncorrelated.csv")
        unc = unc.head(40)
        tabs["Uncorrelated_Top40"] = unc.reset_index().rename(columns={"index":"ticker"}) if "ticker" not in unc.columns else unc
    except FileNotFoundError:
        pass

    # Collect unique tickers across all tabs, fetch info once each.
    all_tickers = sorted({t for df in tabs.values() for t in df["ticker"]})
    print(f"Fetching yfinance info for {len(all_tickers)} unique tickers...", file=sys.stderr)
    info_cache = {}
    for i, t in enumerate(all_tickers):
        info_cache[t] = get_info(t)
        if (i + 1) % 25 == 0:
            print(f"  fetched {i+1}/{len(all_tickers)}", file=sys.stderr)
            time.sleep(0.5)
    info_df = pd.DataFrame.from_dict(info_cache, orient="index")
    info_df.index.name = "ticker"
    info_df = info_df.reset_index()

    # Write Excel
    score_cols = [
        "ticker", "region", "best_rank", "daily_rank", "weekly_rank", "monthly_rank",
        "daily_label", "weekly_label", "monthly_label",
        "W_W", "Q_W", "D_W", "DA_W", "R_W",
    ]
    info_cols = [
        "longName", "country", "sector", "industry", "marketCap", "currency",
        "trailingPE", "forwardPE", "priceToBook", "profitMargins", "returnOnEquity",
        "revenueGrowth", "earningsGrowth", "debtToEquity", "dividendYield",
        "summary", "website",
    ]
    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as writer:
        # Summary
        summary = pd.DataFrame([
            {"tab": k, "rows": len(v)} for k, v in tabs.items()
        ])
        summary.to_excel(writer, sheet_name="Summary", index=False)

        for tab, df in tabs.items():
            avail_score = [c for c in score_cols if c in df.columns]
            sub = df[avail_score].merge(info_df, on="ticker", how="left")
            sub.to_excel(writer, sheet_name=tab[:31], index=False)

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
