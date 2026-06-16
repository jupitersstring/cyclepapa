"""
Run all punch-list Ehlers strategies across the cached crypto universe and
report a ranked summary.

Default universe: Revolut + top-100 by mcap, daily TF (Ehlers' canonical
timeframe and the one with the most history for the longer bandpasses).
Outputs:
  - backtest_results.csv  (one row per symbol × strategy)
  - backtest_summary.csv  (per-strategy aggregates across the universe)
"""

from __future__ import annotations

import time
from typing import Dict

import pandas as pd

from crypto_universe import revolut_universe, top_yf_cryptos_by_mcap
from run_universe import fetch_universe_mtf, DEFAULT_TIMEFRAMES
from strategies import STRATEGIES
from backtest_engine import run_backtest, buy_and_hold


TX_COST_BPS = 25.0   # realistic crypto round-trip (Binance-tier spread + slippage)
PRIMARY_TF = "1d"     # Ehlers' canonical TF; Robot Wealth tested H1/H4/D1


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
    print(f"Universe: {len(syms)} symbols")
    per_tf = fetch_universe_mtf(syms, DEFAULT_TIMEFRAMES)
    daily = per_tf.get(PRIMARY_TF, {})
    print(f"Symbols with {PRIMARY_TF} data: {len(daily)}")

    rows = []
    t0 = time.time()
    for i, sym in enumerate(syms, 1):
        df = daily.get(sym)
        if df is None or len(df) < 250:
            continue
        bh = buy_and_hold(df, tx_cost_bps=TX_COST_BPS)
        bh_record = {
            "symbol": sym, "strategy": "0_buy_and_hold",
            "cagr": bh.cagr, "sharpe": bh.sharpe, "max_dd": bh.max_dd,
            "pf": bh.profit_factor, "win_rate": bh.win_rate,
            "n_trades": bh.n_trades, "avg_hold": bh.avg_hold_bars,
            "exposure": bh.exposure, "total_return": bh.total_return,
            "bars": len(df),
        }
        rows.append(bh_record)

        for name, (fn, kwargs) in STRATEGIES.items():
            try:
                pos = fn(df, **kwargs)
                m, _, _ = run_backtest(df, pos, tx_cost_bps=TX_COST_BPS)
                rows.append({
                    "symbol": sym, "strategy": name,
                    "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_dd,
                    "pf": m.profit_factor, "win_rate": m.win_rate,
                    "n_trades": m.n_trades, "avg_hold": m.avg_hold_bars,
                    "exposure": m.exposure, "total_return": m.total_return,
                    "bars": len(df),
                })
            except Exception as e:
                rows.append({
                    "symbol": sym, "strategy": name,
                    "error": f"{type(e).__name__}: {e}",
                })
        if i % 20 == 0 or i == len(syms):
            print(f"  [{i}/{len(syms)}] {sym}  ({time.time()-t0:.0f}s)")

    df_out = pd.DataFrame(rows)
    df_out.to_csv("backtest_results.csv", index=False)
    print(f"\nWrote backtest_results.csv ({len(df_out)} rows)")

    # Per-strategy aggregates (median is robust to crypto's fat tails).
    ok = df_out[df_out["cagr"].notna()].copy()
    agg = ok.groupby("strategy").agg(
        n=("symbol", "count"),
        median_cagr=("cagr", "median"),
        mean_cagr=("cagr", "mean"),
        median_sharpe=("sharpe", "median"),
        mean_sharpe=("sharpe", "mean"),
        median_pf=("pf", "median"),
        median_max_dd=("max_dd", "median"),
        median_win_rate=("win_rate", "median"),
        median_exposure=("exposure", "median"),
        median_trades=("n_trades", "median"),
        pct_beat_bh=("symbol", lambda g: 0.0),   # filled below
    )
    # Compute % of symbols where strategy CAGR > buy-and-hold CAGR
    bh_lookup = ok[ok["strategy"] == "0_buy_and_hold"].set_index("symbol")["cagr"]
    pct_beat = {}
    for strat in agg.index:
        if strat == "0_buy_and_hold":
            pct_beat[strat] = float("nan"); continue
        sub = ok[ok["strategy"] == strat].set_index("symbol")
        joined = sub["cagr"].to_frame("strat").join(bh_lookup.to_frame("bh"), how="inner")
        if len(joined) == 0:
            pct_beat[strat] = float("nan")
        else:
            pct_beat[strat] = float((joined["strat"] > joined["bh"]).mean())
    agg["pct_beat_bh"] = agg.index.map(pct_beat)
    agg = agg.sort_values("median_sharpe", ascending=False)
    agg.to_csv("backtest_summary.csv")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)
    print("\n=== Strategy summary across the universe ===")
    print(agg.to_string(float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
