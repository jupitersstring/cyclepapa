"""
Re-fetch fundamentals (including EV/EBITDA) for an existing signals CSV
produced by scan_failed_bearish.py and emit cheapest-P/B and cheapest-
EV/EBITDA views. Avoids re-running the slow price-download step.
"""

import argparse
import sys
import time

import pandas as pd
import yfinance as yf

FIELDS = [
    "priceToBook",
    "trailingPE",
    "forwardPE",
    "enterpriseToEbitda",
    "enterpriseValue",
    "returnOnEquity",
    "debtToEquity",
    "profitMargins",
    "revenueGrowth",
    "marketCap",
    "sector",
    "industry",
]


def fetch_one(t, base_sleep, max_retries=4):
    for attempt in range(max_retries):
        try:
            info = yf.Ticker(t).info or {}
            return {f: info.get(f) for f in FIELDS} | {
                "shortName": info.get("shortName") or info.get("longName"),
            }
        except Exception as e:
            if any(s in str(e).lower() for s in ("rate", "too many", "429")):
                wait = base_sleep * (2 ** attempt) + 2
                print(f"    rate limited on {t}, waiting {wait:.0f}s")
                time.sleep(wait)
            else:
                break
    return {f: None for f in FIELDS} | {"shortName": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("signals_csv", help="signals-only CSV from scan_failed_bearish.py")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    sig = pd.read_csv(args.signals_csv, index_col=0)
    print(f"Loaded {len(sig)} signals from {args.signals_csv}")

    rows = []
    for i, t in enumerate(sig.index, 1):
        if i % 10 == 0:
            print(f"  {i}/{len(sig)}")
        rows.append({"Ticker": t, **fetch_one(t, args.sleep)})
        time.sleep(args.sleep)

    fund = pd.DataFrame(rows).set_index("Ticker")
    merged = sig.join(fund, how="left")

    if "failure_close" in merged.columns and "latest_close" in merged.columns:
        merged["pct_from_failure"] = (
            (merged["latest_close"] - merged["failure_close"]) / merged["failure_close"] * 100
        )

    out_path = args.out or args.signals_csv.replace("_signals_", "_enriched_")
    merged.to_csv(out_path)
    print(f"Saved: {out_path}")

    cols = [
        "shortName", "sector", "priceToBook", "enterpriseToEbitda",
        "returnOnEquity", "debtToEquity", "profitMargins", "revenueGrowth",
        "trailingPE", "failure_date", "pct_from_failure",
    ]
    cols = [c for c in cols if c in merged.columns]

    with pd.option_context("display.max_columns", None, "display.width", 220, "display.float_format", "{:.2f}".format):
        pb = pd.to_numeric(merged["priceToBook"], errors="coerce")
        by_pb = merged[pb > 0].sort_values("priceToBook", ascending=True)
        print(f"\n=== Top {args.top} cheapest by P/B ===")
        print(by_pb[cols].head(args.top).to_string())

        ev = pd.to_numeric(merged["enterpriseToEbitda"], errors="coerce")
        by_ev = merged[ev > 0].sort_values("enterpriseToEbitda", ascending=True)
        print(f"\n=== Top {args.top} cheapest by EV/EBITDA ===")
        print(by_ev[cols].head(args.top).to_string())


if __name__ == "__main__":
    main()
