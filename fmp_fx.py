"""Spot FX table from FMP -> fmp_fx_usd.csv (currency, usd_per_unit).

Used by archetype_tags to convert FMP statement levels (reporting currency)
into the master's listing currency with a TRUE exchange rate, instead of a
revenue ratio that mixes currency with period growth. One API call
(batch-forex-quotes returns every pair).
"""
from __future__ import annotations

import pandas as pd

import fmp_client as fc

OUT = "fmp_fx_usd.csv"


def build() -> pd.DataFrame:
    rows = fc.get_json("batch-forex-quotes", {}, ttl=6 * 3600) or []
    usd = {"USD": 1.0}
    for r in rows:
        sym, px = str(r.get("symbol", "")), r.get("price")
        try:
            px = float(px)
        except (TypeError, ValueError):
            continue
        if px <= 0 or len(sym) != 6:
            continue
        a, b = sym[:3], sym[3:]
        if b == "USD":
            usd.setdefault(a, px)            # AAAUSD: USD per 1 AAA
        elif a == "USD":
            usd.setdefault(b, 1.0 / px)      # USDBBB: BBB per 1 USD
    # minor units some filers report in (pence, cents)
    if "GBP" in usd:
        usd.setdefault("GBp", usd["GBP"] / 100.0)
        usd.setdefault("GBX", usd["GBP"] / 100.0)
    if "ZAR" in usd:
        usd.setdefault("ZAc", usd["ZAR"] / 100.0)
    if "ILS" in usd:
        usd.setdefault("ILA", usd["ILS"] / 100.0)
    df = pd.DataFrame(sorted(usd.items()), columns=["currency", "usd_per_unit"])
    df.to_csv(OUT, index=False)
    return df


if __name__ == "__main__":
    d = build()
    print(f"wrote {OUT}: {len(d)} currencies")
    print(d[d.currency.isin(["EUR", "JPY", "GBP", "CNY", "HKD", "KRW", "INR", "CHF"])].to_string(index=False))
