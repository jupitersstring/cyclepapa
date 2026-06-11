"""Currency normalization for cross-market ADV comparisons.

The local ADV (close * volume) lives in whatever currency the exchange
quotes. LSE quotes in pence (1/100 GBP), TLV in agorot (1/100 ILS),
JNB in cents (1/100 ZAR), and most others in major-currency units.

We add adv_20d_usd / adv_60d_usd / adv_20d_usd_millions columns to the
consolidated CSV without touching the existing local-currency columns
(those remain valid for per-name slope/acceleration analysis).
"""

import os
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

# Map each universe to (currency_iso, units_per_unit_of_iso).
# units_per_unit_of_iso > 1 means the exchange quotes in a sub-unit
# (pence/agorot/cents): we divide adv_local by this to get major-unit.
UNIVERSE_CURRENCY = {
    # USA + US-listed indexes
    "us-all": ("USD", 1.0),
    "us-etfs": ("USD", 1.0),
    "wiki-spx500": ("USD", 1.0),
    "wiki-ndx": ("USD", 1.0),
    "wiki-djia": ("USD", 1.0),
    "wiki-r1k": ("USD", 1.0),
    # UK - LSE quotes in pence (1/100 GBP)
    "uk-all": ("GBP", 100.0),
    "uk-etfs": ("GBP", 100.0),
    "wiki-ftse100": ("GBP", 100.0),
    "wiki-ftse250": ("GBP", 100.0),
    "wiki-aim100": ("GBP", 100.0),
    # Continental Europe — EUR
    "de-all": ("EUR", 1.0), "de-etfs": ("EUR", 1.0),
    "fr-all": ("EUR", 1.0),
    "it-all": ("EUR", 1.0), "it-etfs": ("EUR", 1.0),
    "es-all": ("EUR", 1.0),
    "nl-all": ("EUR", 1.0),
    "be-all": ("EUR", 1.0),
    "ie-all": ("EUR", 1.0),
    "pt-all": ("EUR", 1.0),
    "at-all": ("EUR", 1.0),
    "gr-all": ("EUR", 1.0),
    "fi-all": ("EUR", 1.0),
    "eu-smid": ("EUR", 1.0), "eu-etfs": ("EUR", 1.0),
    "eu-large": ("EUR", 1.0), "eu-mid": ("EUR", 1.0),
    "eu-small": ("EUR", 1.0), "eu-micro": ("EUR", 1.0),
    "eu-nano": ("EUR", 1.0),
    "wiki-dax": ("EUR", 1.0), "wiki-mdax": ("EUR", 1.0),
    "wiki-cac40": ("EUR", 1.0), "wiki-mib": ("EUR", 1.0),
    "wiki-aex": ("EUR", 1.0), "wiki-stoxx50": ("EUR", 1.0),
    # Switzerland - CHF
    "ch-all": ("CHF", 1.0),
    # Nordic
    "se-all": ("SEK", 1.0), "wiki-omxs30": ("SEK", 1.0),
    "no-all": ("NOK", 1.0),
    "dk-all": ("DKK", 1.0),
    # Japan - JPY
    "jp-all": ("JPY", 1.0),
    # China - CNY (Shanghai SS / Shenzhen SZ)
    "cn-all": ("CNY", 1.0),
    # Hong Kong - HKD
    "hk-all": ("HKD", 1.0),
    # Korea - KRW
    "kr-all": ("KRW", 1.0),
    # Taiwan - TWD
    "tw-all": ("TWD", 1.0),
    # India - INR
    "in-all": ("INR", 1.0),
    # Singapore - SGD
    "sg-all": ("SGD", 1.0),
    # Oceania
    "au-all": ("AUD", 1.0),
    "nz-all": ("NZD", 1.0),
    # Americas
    "ca-all": ("CAD", 1.0),
    "br-all": ("BRL", 1.0),
    "mx-all": ("MXN", 1.0),
    "ar-all": ("ARS", 1.0),
    "cl-all": ("CLP", 1.0),
    # South Africa - JNB quotes in CENTS (1/100 ZAR)
    "za-all": ("ZAR", 100.0),
    # Israel - TLV quotes in AGOROT (1/100 ILS)
    "il-all": ("ILS", 100.0),
    # MENA, EM
    "tr-all": ("TRY", 1.0),
    "sa-all": ("SAR", 1.0),
    "th-all": ("THB", 1.0),
    "id-all": ("IDR", 1.0),
    # Wiki-union has mixed - handled by suffix below
    "wiki-union": None,
}

# yfinance ticker-suffix fallback for wiki-union and unclassified
SUFFIX_CURRENCY = {
    ".L": ("GBP", 100.0),  ".TA": ("ILS", 100.0), ".JO": ("ZAR", 100.0),
    ".DE": ("EUR", 1.0),   ".PA": ("EUR", 1.0),   ".MI": ("EUR", 1.0),
    ".MC": ("EUR", 1.0),   ".AS": ("EUR", 1.0),   ".BR": ("EUR", 1.0),
    ".LS": ("EUR", 1.0),   ".VI": ("EUR", 1.0),   ".HE": ("EUR", 1.0),
    ".IR": ("EUR", 1.0),   ".AT": ("EUR", 1.0),   ".SW": ("CHF", 1.0),
    ".ST": ("SEK", 1.0),   ".OL": ("NOK", 1.0),   ".CO": ("DKK", 1.0),
    ".T": ("JPY", 1.0),    ".HK": ("HKD", 1.0),   ".KS": ("KRW", 1.0),
    ".KQ": ("KRW", 1.0),   ".TW": ("TWD", 1.0),   ".TWO": ("TWD", 1.0),
    ".NS": ("INR", 1.0),   ".BO": ("INR", 1.0),   ".SS": ("CNY", 1.0),
    ".SZ": ("CNY", 1.0),   ".SI": ("SGD", 1.0),   ".AX": ("AUD", 1.0),
    ".NZ": ("NZD", 1.0),   ".TO": ("CAD", 1.0),   ".V": ("CAD", 1.0),
    ".CN": ("CAD", 1.0),   ".SA": ("BRL", 1.0),   ".MX": ("MXN", 1.0),
    ".BA": ("ARS", 1.0),   ".SN": ("CLP", 1.0),   ".BK": ("THB", 1.0),
    ".JK": ("IDR", 1.0),   ".IS": ("TRY", 1.0),   ".SR": ("SAR", 1.0),
}


def get_currency(universe, ticker):
    """Return (currency_iso, units_per_iso). Falls back to ticker suffix."""
    spec = UNIVERSE_CURRENCY.get(universe)
    if spec is not None:
        return spec
    # Try suffix
    for suffix, val in SUFFIX_CURRENCY.items():
        if ticker.endswith(suffix):
            return val
    # Default US
    return ("USD", 1.0)


def fetch_fx_rates(currencies):
    """Fetch FX rate to USD for each currency via yfinance ='{}USD=X'."""
    rates = {"USD": 1.0}
    for ccy in currencies:
        if ccy in rates:
            continue
        try:
            t = yf.Ticker(f"{ccy}USD=X")
            hist = t.history(period="5d", auto_adjust=True)
            if len(hist) and "Close" in hist.columns:
                rate = float(hist["Close"].dropna().iloc[-1])
                if rate > 0:
                    rates[ccy] = rate
                    print(f"  FX {ccy}USD: {rate:.6f}")
                    continue
        except Exception as e:
            pass
        # Fallback: try USDCCY=X and invert
        try:
            t = yf.Ticker(f"USD{ccy}=X")
            hist = t.history(period="5d", auto_adjust=True)
            if len(hist) and "Close" in hist.columns:
                inv = float(hist["Close"].dropna().iloc[-1])
                if inv > 0:
                    rates[ccy] = 1.0 / inv
                    print(f"  FX {ccy}USD (via USD{ccy}=X inverse): {1.0/inv:.6f}")
                    continue
        except Exception:
            pass
        print(f"  FX {ccy}USD: NOT FOUND, will skip")
    return rates


def main():
    csv_path = "global_equities_consolidated.csv"
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    df = pd.read_csv(csv_path, index_col=0, low_memory=False)
    print(f"Loaded {len(df)} rows from {csv_path}")

    # Build currency lookup
    df["_ccy"] = [get_currency(u, t)[0] for u, t in zip(df["_universe"], df.index)]
    df["_sub_unit_div"] = [get_currency(u, t)[1] for u, t in zip(df["_universe"], df.index)]
    print("Currencies present:")
    print(df["_ccy"].value_counts().to_string())

    # Fetch FX rates
    fx = fetch_fx_rates(sorted(df["_ccy"].unique()))

    # Compute USD-normalised ADV
    df["_fx_to_usd"] = df["_ccy"].map(fx).astype(float)
    for col in ["adv_20d_dollar", "adv_60d_dollar"]:
        if col not in df.columns:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
        usd_col = col.replace("_dollar", "_usd")
        df[usd_col] = df[col] / df["_sub_unit_div"] * df["_fx_to_usd"]
    df["adv_20d_usd_millions"] = df["adv_20d_usd"] / 1_000_000

    # Drop helper cols before writing
    drop_helpers = ["_ccy", "_sub_unit_div", "_fx_to_usd"]
    # ... actually KEEP _ccy and _fx_to_usd - they're useful diagnostics
    df.drop(columns=["_sub_unit_div"], inplace=True)

    df.to_csv(csv_path)
    print(f"\nWrote USD-normalised ADV columns to {csv_path}")
    print(f"  adv_20d_usd_millions stats: median={df['adv_20d_usd_millions'].median():.2f}M  "
          f"p90={df['adv_20d_usd_millions'].quantile(0.9):.2f}M  "
          f"max={df['adv_20d_usd_millions'].max():.2f}M")

    # Spot-check the cases that were wrong before
    print("\nSPOT CHECKS (compare to original local-units 'adv_20d_millions'):")
    for tkr in ["MU", "AAPL", "BEZ.L", "TSEM.TA", "6762.T", "000660.KS", "SAP.DE",
                "INGA.AS", "VTU.L", "POLR.L"]:
        rows = df[df.index == tkr]
        if len(rows) == 0:
            continue
        r = rows.iloc[0]
        local_M = r.get("adv_20d_millions", float("nan"))
        usd_M = r.get("adv_20d_usd_millions", float("nan"))
        ccy = r.get("_ccy", "?")
        print(f"  {tkr:12s} {ccy:4s}  local={local_M:>14.1f}M  USD-normalised={usd_M:>10.1f}M")


if __name__ == "__main__":
    main()
