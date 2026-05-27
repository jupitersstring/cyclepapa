"""
Identify the best Qullamaggie pre-breakout setups in the screened universe.

Pre-breakout = the *structure* of a Qullamaggie breakout setup is fully in
place, but the actual 20-bar breakout trigger has NOT fired yet. Per
Qullamaggie:

  - Leadership: top % returns over 1m / 3m / 6m (proxy: ret_1m >= 30%,
    ret_3m >= 50%, ret_6m >= 100%).
  - Structure: close above the rising 10 / 20 / 50 SMA; price "surfing"
    (within 1 ADR of the 10 or 20 SMA); ATR contracting and range tight
    over the last 20 bars (consolidation).
  - Volatility: attractive volasym (above MA, rising, in [45, 70] band,
    release within last 10 bars of a hyper-squeeze).

Reuses the disk-cached OHLCV from run_universe.py (no re-download).
"""

from __future__ import annotations

import pandas as pd

from crypto_universe import revolut_universe, top_yf_cryptos_by_mcap
from run_universe import DEFAULT_TIMEFRAMES, fetch_universe_mtf
from trend_engine import trend_score, make_relative


PRE_BREAKOUT_THRESHOLD = 35.0     # min daily pre-breakout quality score (0..70)
CONFIRM_MIN_TFS = 1                # confirmation on >= N other timeframes


def _components_per_tf(df):
    s = trend_score(df)
    c = s.components
    leadership = c["long.leader_1m"] + c["long.leader_3m"] + c["long.leader_6m"]
    structure  = (c["long.above_10sma"] + c["long.above_20sma"] + c["long.above_50sma"]
                  + c["long.sma_rising_stack"] + c["long.surfing_10_20"] + c["long.consolidating"])
    volasym    = (c["long.volasym_above_ma"] + c["long.volasym_rising"]
                  + c["long.volasym_in_band"] + c["long.release_post_squeeze"])
    triggered  = bool(s.flags.get("breakout_20") or s.flags.get("ep_signal"))
    return {
        "leadership": leadership,
        "structure": structure,
        "volasym": volasym,
        "quality": leadership + structure + volasym,        # 0..70
        "triggered": triggered,
        "above_10": bool(s.qm["above_10sma"]), "above_20": bool(s.qm["above_20sma"]),
        "above_50": bool(s.qm["above_50sma"]),
        "consolidating": bool(s.qm["consolidating"]),
        "ret_1m": s.qm["ret_1m"], "ret_3m": s.qm["ret_3m"], "ret_6m": s.qm["ret_6m"],
        "adr_pct": s.qm["adr_pct"],
        "bull_inflect": bool(s.flags.get("inflection_bull")),
    }


def main():
    seen, syms = set(), []
    for src in (revolut_universe(), top_yf_cryptos_by_mcap(100)):
        for s in src:
            if s not in seen:
                seen.add(s); syms.append(s)
    if "BTC-USD" not in syms:
        syms.insert(0, "BTC-USD")
    print(f"Universe: {len(syms)} symbols")

    per_tf = fetch_universe_mtf(syms, DEFAULT_TIMEFRAMES)
    btc_per_tf = {tf: per_tf[tf]["BTC-USD"] for tf in per_tf if "BTC-USD" in per_tf[tf]}

    rows = []
    for sym in syms:
        sym_tfs = {tf: per_tf[tf][sym] for tf in per_tf if sym in per_tf[tf] and len(per_tf[tf][sym]) >= 60}
        # Qullamaggie methodology is fundamentally daily-chart based —
        # require the daily TF.
        if "1d" not in sym_tfs:
            continue

        # Primary = daily. Other TFs = confirmation.
        daily = _components_per_tf(sym_tfs["1d"])
        # Pre-breakout = structure / volasym in place, trigger NOT fired on
        # the daily.
        if daily["triggered"]:
            continue

        other_tfs = [tf for tf in sym_tfs if tf != "1d"]
        confirm = {tf: _components_per_tf(sym_tfs[tf]) for tf in other_tfs}
        confirm_above_all = sum(1 for c in confirm.values() if c["above_10"] and c["above_20"] and c["above_50"])
        confirm_volasym = sum(1 for c in confirm.values() if c["volasym"] >= 18)  # >=3/4 volasym criteria

        # Relative-to-BTC daily structure (alpha vs BTC).
        rel_quality_daily = None
        if sym != "BTC-USD" and "1d" in btc_per_tf:
            rel = make_relative(sym_tfs["1d"], btc_per_tf["1d"])
            if rel is not None:
                rel_quality_daily = _components_per_tf(rel)["quality"]

        rows.append({
            "symbol": sym,
            "daily_quality": daily["quality"],
            "rel_daily_quality": rel_quality_daily,
            "d_leadership": daily["leadership"],
            "d_structure": daily["structure"],
            "d_volasym": daily["volasym"],
            "d_above_all_smas": daily["above_10"] and daily["above_20"] and daily["above_50"],
            "d_consolidating": daily["consolidating"],
            "d_bull_inflect": daily["bull_inflect"],
            "d_ret_1m_pct": daily["ret_1m"] * 100,
            "d_ret_3m_pct": daily["ret_3m"] * 100,
            "d_ret_6m_pct": daily["ret_6m"] * 100,
            "d_adr_pct": daily["adr_pct"],
            "confirm_above_all_smas": confirm_above_all,
            "confirm_volasym": confirm_volasym,
            "n_confirm_tfs": len(confirm),
        })

    df = pd.DataFrame(rows)
    df = df[df["daily_quality"] >= PRE_BREAKOUT_THRESHOLD]
    df = df[(df["confirm_above_all_smas"] >= CONFIRM_MIN_TFS) | (df["confirm_volasym"] >= CONFIRM_MIN_TFS)]
    df = df.sort_values("daily_quality", ascending=False)

    cols = ["symbol", "daily_quality", "rel_daily_quality",
            "d_leadership", "d_structure", "d_volasym",
            "d_above_all_smas", "d_consolidating", "d_bull_inflect",
            "d_ret_1m_pct", "d_ret_3m_pct", "d_ret_6m_pct", "d_adr_pct",
            "confirm_above_all_smas", "confirm_volasym", "n_confirm_tfs"]

    out = "pre_breakout_setups.csv"
    df.to_csv(out, index=False)
    print(f"\nWrote {out}  ({len(df)} pre-breakout candidates)")
    print("\n=== Top 25 pre-breakout setups (daily TF) ===")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", None)
    print(df.head(25)[cols].to_string(index=False,
                                       float_format=lambda x: f"{x:.1f}"))


if __name__ == "__main__":
    main()
