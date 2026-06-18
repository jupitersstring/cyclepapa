"""
Multi-timeframe sweep: run the headline strategies on 4h, 1d, and 1w
data to identify the best TF per strategy family. Includes the new
Volasym / S&R variants from the Pine S&R+VolAsym indicator.

Each row tags (symbol, strategy, timeframe) with full-period metrics
+ split-half walk-forward + bootstrap DD CI vs the TF-appropriate
buy-and-hold baseline.
"""

from __future__ import annotations

import time

import pandas as pd

from crypto_universe import (
    revolut_universe, top_yf_cryptos_by_mcap, top_yf_cryptos_by_volume,
)
from run_universe import fetch_universe_mtf
from backtest_engine import (
    run_backtest, buy_and_hold, split_half, bootstrap_dd_ci,
)
from strategies import (
    strat_4band_agreement, strat_market_mode_gated,
    strat_volasym_attractive, strat_volasym_event,
    strat_sr_release, strat_release_after_squeeze,
    strat_va_sr_combined, strat_4band_va_filter,
)


TX_COST_BPS = 25.0
N_BOOT = 300
N_MCAP = 200
N_VOLUME = 200

TIMEFRAMES_TO_TEST = [
    ("4h",  "4h"),
    ("1d",  "1d"),
    ("1w",  "1wk"),
]

# Min bars per TF — bandpasses and volasym need warm-up.
MIN_BARS_PER_TF = {"4h": 1500, "1d": 500, "1w": 200}


BAND_SETS = {
    "long":    [(60, 90), (300, 450), (900, 1350), (1500, 3000)],
    "default": [(40, 60), (200, 300), (600, 900), (1200, 2400)],
}


VARIANTS = [
    # Cycle baseline
    ("5_4band_long_min4",   strat_4band_agreement, {"bands": BAND_SETS["long"], "min_agree": 4}),
    ("5_4band_default_min4", strat_4band_agreement, {"bands": BAND_SETS["default"], "min_agree": 4}),
    # Volasym
    ("10a_volasym_attractive", strat_volasym_attractive, {}),
    ("10b_volasym_event_h10",  strat_volasym_event, {"max_hold": 10}),
    ("10b_volasym_event_h20",  strat_volasym_event, {"max_hold": 20}),
    # Squeeze & Release
    ("10c_sr_release_h10",          strat_sr_release, {"max_hold": 10}),
    ("10c_sr_release_h20",          strat_sr_release, {"max_hold": 20}),
    ("10d_release_after_sq_h20",    strat_release_after_squeeze, {"max_hold": 20}),
    ("10d_release_after_sq_h40",    strat_release_after_squeeze, {"max_hold": 40}),
    # Combined / filtered
    ("10e_va_sr_combined_h15",      strat_va_sr_combined, {"max_hold": 15}),
    ("11_4band_long_va_filter",     strat_4band_va_filter, {"bands": BAND_SETS["long"], "min_agree": 4}),
    # Reference market-mode
    ("4_mode_thresh20",   strat_market_mode_gated, {"trend_thresh": 0.20, "use_mmi": False}),
]


def _build_universe() -> list[str]:
    seen, out = set(), []
    for src in (revolut_universe(),
                 top_yf_cryptos_by_mcap(N_MCAP),
                 top_yf_cryptos_by_volume(N_VOLUME)):
        for s in src:
            if s not in seen:
                seen.add(s); out.append(s)
    if "BTC-USD" not in out:
        out.insert(0, "BTC-USD")
    return out


def main() -> None:
    syms = _build_universe()
    print(f"Universe: {len(syms)} symbols, "
          f"{len(VARIANTS)} variants × {len(TIMEFRAMES_TO_TEST)} TFs")
    per_tf = fetch_universe_mtf(syms, TIMEFRAMES_TO_TEST)

    rows = []
    t0 = time.time()
    for tf_label, _ in TIMEFRAMES_TO_TEST:
        tf_data = per_tf.get(tf_label, {})
        min_bars = MIN_BARS_PER_TF.get(tf_label, 200)
        print(f"\n--- timeframe {tf_label}: {len(tf_data)} symbols with data, min_bars={min_bars} ---")
        usable = {s: d for s, d in tf_data.items() if len(d) >= min_bars}
        print(f"  {len(usable)} symbols meet min_bars threshold")
        for i, sym in enumerate(usable, 1):
            df = usable[sym]
            bh = buy_and_hold(df, tx_cost_bps=TX_COST_BPS)
            for name, fn, kwargs in VARIANTS:
                try:
                    pos = fn(df, **kwargs)
                    m, _, _ = run_backtest(df, pos, tx_cost_bps=TX_COST_BPS)
                    m1, m2 = split_half(df, fn, tx_cost_bps=TX_COST_BPS, **kwargs)
                    dd_p05, dd_p50, dd_p95 = bootstrap_dd_ci(
                        df, pos, n_boot=N_BOOT, tx_cost_bps=TX_COST_BPS)
                    rows.append({
                        "symbol": sym, "tf": tf_label, "variant": name,
                        "bh_cagr": bh.cagr, "bh_sharpe": bh.sharpe,
                        "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_dd,
                        "pf": m.profit_factor, "win_rate": m.win_rate,
                        "n_trades": m.n_trades, "exposure": m.exposure,
                        "h1_sharpe": m1.sharpe, "h2_sharpe": m2.sharpe,
                        "stable_sign": int((m1.sharpe > 0) == (m2.sharpe > 0)),
                        "boot_dd_p05": dd_p05, "boot_dd_p95": dd_p95,
                        "bars": len(df),
                    })
                except Exception as e:
                    rows.append({"symbol": sym, "tf": tf_label, "variant": name,
                                  "error": f"{type(e).__name__}: {e}"})
            if i % 50 == 0:
                print(f"    [{i}/{len(usable)}] {sym}  ({time.time()-t0:.0f}s)")

    df_out = pd.DataFrame(rows)
    df_out.to_csv("backtest_mtf_sweep.csv", index=False)
    print(f"\nWrote backtest_mtf_sweep.csv ({len(df_out)} rows)")

    ok = df_out[df_out["cagr"].notna() & df_out["cagr"].between(-2, 5)].copy()
    agg = ok.groupby(["tf", "variant"]).agg(
        n=("symbol", "count"),
        med_sharpe=("sharpe", "median"),
        med_cagr=("cagr", "median"),
        med_dd=("max_dd", "median"),
        med_h1=("h1_sharpe", "median"),
        med_h2=("h2_sharpe", "median"),
        stable=("stable_sign", "mean"),
        med_trades=("n_trades", "median"),
        med_exposure=("exposure", "median"),
    )
    # Beat-both rate per (tf, variant)
    beats = {}
    for (tf, v), grp in ok.groupby(["tf", "variant"]):
        if len(grp) == 0:
            beats[(tf, v)] = (float("nan"), float("nan")); continue
        beat_cagr = float((grp["cagr"] > grp["bh_cagr"]).mean())
        beat_both = float(((grp["cagr"] > grp["bh_cagr"])
                            & (grp["sharpe"] > grp["bh_sharpe"])).mean())
        beats[(tf, v)] = (beat_cagr, beat_both)
    agg["pct_beat_cagr"] = [beats[k][0] for k in agg.index]
    agg["pct_beat_both"] = [beats[k][1] for k in agg.index]
    agg = agg.sort_values("pct_beat_both", ascending=False)
    agg.to_csv("backtest_mtf_summary.csv")

    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", None)
    print("\n=== Multi-TF sweep summary (sorted by pct_beat_both) ===")
    print(agg.to_string(float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
