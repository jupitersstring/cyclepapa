"""
Crypto Ehlers 4-bandpass screener.

For every symbol in the universe (Revolut + top-100 by mcap), apply the
four Ehlers bandpass filters to BOTH price (close) AND volume on the
DAILY and 90-MINUTE timeframes. For each band, detect:

  - current sign (above or below the zero line),
  - any zero-line cross within the last `recency` bars (bullish or
    bearish "inflection"),

then composite a per-symbol score:

  bandpass_net = price_net_daily + price_net_90m + vol_net_daily + vol_net_90m

where each net = (#bands above 0 − #bands below 0) + (#bull crosses − #bear crosses).

Output is sorted by total inflection strength, with the sub-components
preserved for diagnosis.
"""

from __future__ import annotations

import pandas as pd

from crypto_universe import revolut_universe, top_yf_cryptos_by_mcap
from run_universe import fetch_universe_mtf
from bandpass import bandpass_score, DEFAULT_BANDS


BANDPASS_TIMEFRAMES = [
    ("1d",  "1d"),
    ("90m", "90m"),    # yfinance 90m interval — limited to 60d history
]


def _per_tf_row(label: str, score) -> dict:
    p, v = score.price, score.volume
    return {
        f"{label}_price_above": p.bands_above_zero,
        f"{label}_price_below": p.bands_below_zero,
        f"{label}_price_bull_cross": p.bull_cross_recent,
        f"{label}_price_bear_cross": p.bear_cross_recent,
        f"{label}_price_net": score.price_net,
        f"{label}_vol_above": v.bands_above_zero,
        f"{label}_vol_below": v.bands_below_zero,
        f"{label}_vol_bull_cross": v.bull_cross_recent,
        f"{label}_vol_bear_cross": v.bear_cross_recent,
        f"{label}_vol_net": score.volume_net,
        f"{label}_combined_net": score.combined_net,
        f"{label}_price_bull_bands": ",".join(map(str, p.bull_cross_bands)),
        f"{label}_price_bear_bands": ",".join(map(str, p.bear_cross_bands)),
        f"{label}_vol_bull_bands": ",".join(map(str, v.bull_cross_bands)),
        f"{label}_vol_bear_bands": ",".join(map(str, v.bear_cross_bands)),
    }


def main() -> None:
    seen, syms = set(), []
    for src in (revolut_universe(), top_yf_cryptos_by_mcap(100)):
        for s in src:
            if s not in seen:
                seen.add(s); syms.append(s)
    print(f"Universe: {len(syms)} symbols")

    per_tf = fetch_universe_mtf(syms, BANDPASS_TIMEFRAMES)

    rows = []
    for sym in syms:
        tf_results = {}
        for label, _ in BANDPASS_TIMEFRAMES:
            df = per_tf.get(label, {}).get(sym)
            if df is None or len(df) < 60:
                continue
            tf_results[label] = bandpass_score(df)
        if not tf_results:
            continue
        row = {"symbol": sym}
        total_net = 0
        for label, score in tf_results.items():
            row.update(_per_tf_row(label, score))
            total_net += score.combined_net
        row["bandpass_net"] = total_net
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        print("No symbols produced bandpass output.")
        return
    df = df.sort_values("bandpass_net", ascending=False)
    df.to_csv("bandpass_inflections.csv", index=False)
    print(f"\nWrote bandpass_inflections.csv  ({len(df)} symbols)")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)

    # Headline: top 20 by composite net
    keep = ["symbol", "bandpass_net",
            "1d_price_net", "1d_vol_net",
            "90m_price_net", "90m_vol_net",
            "1d_price_above", "1d_vol_above",
            "1d_price_bull_cross", "1d_price_bear_cross",
            "1d_vol_bull_cross", "1d_vol_bear_cross",
            "90m_price_bull_cross", "90m_price_bear_cross",
            "90m_vol_bull_cross", "90m_vol_bear_cross"]
    keep = [c for c in keep if c in df.columns]
    print("\n=== Top 20 by bandpass_net (bullish bandpass inflection) ===")
    print(df.head(20)[keep].to_string(index=False))

    print("\n=== Bottom 15 (bearish bandpass inflection) ===")
    print(df.tail(15)[keep].to_string(index=False))

    # Most recent bullish crosses on daily volume — early accumulation signal
    if "1d_vol_bull_cross" in df.columns:
        accum = df[df["1d_vol_bull_cross"] > 0].sort_values(
            ["1d_vol_bull_cross", "bandpass_net"], ascending=False
        ).head(20)
        if not accum.empty:
            print("\n=== Volume zero-line bull crosses on daily (accumulation candidates) ===")
            print(accum[keep].to_string(index=False))


if __name__ == "__main__":
    main()
