"""
Parameter sweep + walk-forward + bootstrap DD for the most promising
Ehlers strategies.

Sweeps:
  - Strategy #5 (4-band agreement) at min_agree ∈ {2, 3, 4}
    × {default, shorter, longer} band sets
  - Strategy #4 (Market-Mode gate) at trend_thresh ∈ {5%, 10%, 15%, 20%}
    × {with MMI, no MMI}

For each (symbol, variant):
  - full-period metrics
  - first-half metrics  (in-sample reference)
  - second-half metrics (out-of-sample stability)
  - bootstrap max-DD p5 / p95 from per-bar returns (n_boot=300)
"""

from __future__ import annotations

import time

import pandas as pd

from crypto_universe import revolut_universe, top_yf_cryptos_by_mcap
from run_universe import fetch_universe_mtf, DEFAULT_TIMEFRAMES
from backtest_engine import (
    run_backtest, buy_and_hold, split_half, bootstrap_dd_ci,
)
from strategies import strat_4band_agreement, strat_market_mode_gated


TX_COST_BPS = 25.0
PRIMARY_TF = "1d"
N_BOOT = 300


# Band sets to sweep on #5. Default = original (40/60 → 1200/2400).
BAND_SETS = {
    "default": [(40, 60), (200, 300), (600, 900), (1200, 2400)],
    "short":   [(20, 30), (100, 150), (400, 600), (800, 1200)],
    "long":    [(60, 90), (300, 450), (900, 1350), (1500, 3000)],
}

VARIANTS = []

# Strategy #5 sweep
for band_name, bands in BAND_SETS.items():
    for min_agree in (2, 3, 4):
        VARIANTS.append((
            f"5_4band_{band_name}_min{min_agree}",
            strat_4band_agreement,
            {"bands": bands, "min_agree": min_agree},
        ))

# Strategy #4 sweep
for thresh in (0.05, 0.10, 0.15, 0.20):
    for use_mmi in (False, True):
        suffix = "_mmi" if use_mmi else ""
        VARIANTS.append((
            f"4_mode_thresh{int(thresh*100):02d}{suffix}",
            strat_market_mode_gated,
            {"trend_thresh": thresh, "use_mmi": use_mmi},
        ))


def _build_universe() -> list[str]:
    seen, out = set(), []
    for src in (revolut_universe(), top_yf_cryptos_by_mcap(100)):
        for s in src:
            if s not in seen:
                seen.add(s); out.append(s)
    if "BTC-USD" not in out:
        out.insert(0, "BTC-USD")
    return out


def main() -> None:
    syms = _build_universe()
    print(f"Universe: {len(syms)} symbols, {len(VARIANTS)} variants")
    per_tf = fetch_universe_mtf(syms, DEFAULT_TIMEFRAMES)
    daily = per_tf.get(PRIMARY_TF, {})
    print(f"Symbols with {PRIMARY_TF} data: {len(daily)}")

    rows = []
    t0 = time.time()
    for i, sym in enumerate(syms, 1):
        df = daily.get(sym)
        if df is None or len(df) < 500:    # need plenty of history for split-half
            continue
        bh = buy_and_hold(df, tx_cost_bps=TX_COST_BPS)

        for name, fn, kwargs in VARIANTS:
            try:
                pos = fn(df, **kwargs)
                m, _, _ = run_backtest(df, pos, tx_cost_bps=TX_COST_BPS)
                m1, m2 = split_half(df, fn, tx_cost_bps=TX_COST_BPS, **kwargs)
                dd_p05, dd_p50, dd_p95 = bootstrap_dd_ci(df, pos,
                                                           n_boot=N_BOOT,
                                                           tx_cost_bps=TX_COST_BPS)
                rows.append({
                    "symbol": sym, "variant": name,
                    "bh_cagr": bh.cagr, "bh_sharpe": bh.sharpe,
                    "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_dd,
                    "pf": m.profit_factor, "win_rate": m.win_rate,
                    "n_trades": m.n_trades, "exposure": m.exposure,
                    "h1_sharpe": m1.sharpe, "h1_cagr": m1.cagr,
                    "h2_sharpe": m2.sharpe, "h2_cagr": m2.cagr,
                    "stable_sharpe_sign": int(
                        (m1.sharpe > 0) == (m2.sharpe > 0)
                    ),
                    "boot_dd_p05": dd_p05, "boot_dd_p50": dd_p50, "boot_dd_p95": dd_p95,
                    "bars": len(df),
                })
            except Exception as e:
                rows.append({"symbol": sym, "variant": name,
                              "error": f"{type(e).__name__}: {e}"})
        if i % 25 == 0 or i == len(syms):
            print(f"  [{i}/{len(syms)}] {sym}  ({time.time()-t0:.0f}s)")

    df_out = pd.DataFrame(rows)
    df_out.to_csv("backtest_sweep.csv", index=False)
    print(f"\nWrote backtest_sweep.csv ({len(df_out)} rows)")

    ok = df_out[df_out["cagr"].notna() & df_out["cagr"].between(-2, 5)].copy()

    # Universe medians per variant
    agg = ok.groupby("variant").agg(
        n=("symbol", "count"),
        med_cagr=("cagr", "median"),
        med_sharpe=("sharpe", "median"),
        med_dd=("max_dd", "median"),
        med_h1_sharpe=("h1_sharpe", "median"),
        med_h2_sharpe=("h2_sharpe", "median"),
        med_stable=("stable_sharpe_sign", "mean"),
        med_dd_p05=("boot_dd_p05", "median"),
        med_dd_p95=("boot_dd_p95", "median"),
        med_trades=("n_trades", "median"),
        med_exposure=("exposure", "median"),
    )
    # Beat-B&H rates
    beat_cagr = {}
    beat_both = {}
    for v in agg.index:
        sub = ok[ok["variant"] == v]
        if len(sub) == 0:
            beat_cagr[v] = float("nan"); beat_both[v] = float("nan"); continue
        beat_cagr[v] = float((sub["cagr"] > sub["bh_cagr"]).mean())
        beat_both[v] = float(((sub["cagr"] > sub["bh_cagr"])
                                & (sub["sharpe"] > sub["bh_sharpe"])).mean())
    agg["pct_beat_cagr"] = agg.index.map(beat_cagr)
    agg["pct_beat_both"] = agg.index.map(beat_both)
    agg = agg.sort_values("pct_beat_both", ascending=False)
    agg.to_csv("backtest_sweep_summary.csv")

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", None)
    print("\n=== Variant sweep summary (sorted by pct_beat_both) ===")
    print(agg.to_string(float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
