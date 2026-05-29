"""
Filter the bandpass output to symbols showing BULLISH ABOVE-ZERO INFLECTIONS
on at least one band — i.e., a band that just crossed the zero line upward
(so it is, by definition, currently above 0 and newly bullish).

Reads bandpass_inflections.csv produced by check_bandpass.py.

Rank by:
  1. bull_inflect_total  — number of bands across (price, volume) × (1d, 90m)
     that just crossed zero up within the recency window.
  2. bands_above_0_total — total count of bands currently above 0.
  3. bandpass_net        — original composite net score.
"""

from __future__ import annotations

import sys

import pandas as pd


CROSS_COLS = [
    "1d_price_bull_cross", "1d_vol_bull_cross",
    "90m_price_bull_cross", "90m_vol_bull_cross",
]
ABOVE_COLS = [
    "1d_price_above", "1d_vol_above",
    "90m_price_above", "90m_vol_above",
]
BAND_COLS = [
    "1d_price_bull_bands", "1d_vol_bull_bands",
    "90m_price_bull_bands", "90m_vol_bull_bands",
]


def main(in_path: str = "bandpass_inflections.csv",
         out_path: str = "bandpass_bullish_inflections.csv") -> None:
    df = pd.read_csv(in_path)
    for c in CROSS_COLS + ABOVE_COLS:
        if c not in df.columns:
            df[c] = 0
    df["bull_inflect_total"] = df[CROSS_COLS].fillna(0).sum(axis=1)
    df["bands_above_0_total"] = df[ABOVE_COLS].fillna(0).sum(axis=1)

    hit = df[df["bull_inflect_total"] > 0].copy()
    hit = hit.sort_values(
        ["bull_inflect_total", "bands_above_0_total", "bandpass_net"],
        ascending=False,
    )

    show = (["symbol", "bull_inflect_total", "bands_above_0_total", "bandpass_net"]
            + CROSS_COLS + ABOVE_COLS + BAND_COLS)
    show = [c for c in show if c in hit.columns]

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", None)
    print(f"=== {len(hit)} symbols with bullish above-0 bandpass inflections ===\n")
    print(hit.head(40)[show].to_string(index=False))

    hit.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(hit)} symbols)")


if __name__ == "__main__":
    main(*sys.argv[1:])
