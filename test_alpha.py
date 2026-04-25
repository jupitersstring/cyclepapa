"""
Honest alpha evaluation of the FMH lock-picker concept.

Three tests:
  1. Single-asset timing (long-flat)         -- typical hard regime
  2. Single-asset timing (long-short)        -- crypto / range-bound
  3. Cross-sectional rotation                -- where multi-scale signals
                                                tend to actually pay off
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from fmh_lockpicker import build_fmh, FMHParams, backtest


def fetch(ticker: str, period: str = "15y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def vol_match_lever(strat_ret: pd.Series, target_vol_series: pd.Series) -> pd.Series:
    """Lever strategy returns to match the volatility of the benchmark."""
    sv = strat_ret.rolling(60).std()
    bv = target_vol_series.rolling(60).std()
    lev = (bv / sv.replace(0, np.nan)).clip(0, 4).fillna(0).shift(1).fillna(0)
    return strat_ret * lev


def stats(ret: pd.Series, ann: int = 252):
    ret = ret.dropna()
    if len(ret) < 30 or ret.std() == 0:
        return dict(CAGR=0.0, Sharpe=0.0, MaxDD=0.0)
    eq = (1 + ret).cumprod()
    cagr = eq.iloc[-1] ** (ann / len(ret)) - 1
    shp = ret.mean() / ret.std() * np.sqrt(ann)
    dd = (eq / eq.cummax() - 1).min()
    return dict(CAGR=cagr, Sharpe=shp, MaxDD=dd)


# ────────────── Test 1 & 2: single-asset timing ──────────────
def single_asset(ticker: str, mode: str, p: FMHParams, period: str = "15y"):
    df = fetch(ticker, period)
    sig = build_fmh(df, p)
    pos = sig["binary_position"].astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    bt = backtest(df, pos)
    yrs = len(df) / 252
    return dict(ticker=ticker, mode=mode, yrs=yrs,
                strat=bt["strategy"], bh=bt["buy_hold"],
                tim=(pos != 0).mean(),
                turn=bt["turnover_per_year"],
                ret_strat=bt["eq_strategy"].pct_change().fillna(0),
                ret_bh=bt["eq_buyhold"].pct_change().fillna(0))


# ────────────── Test 3: cross-sectional rotation ──────────────
def cross_section(tickers: list[str], p: FMHParams, period: str = "15y",
                  top_n: int = 1, hold_bars: int = 5, cost_bps: float = 1.0):
    """
    Each `hold_bars` days, hold an equal-weight basket of the top-N tickers
    ranked by  signed_alignment * coherence * (Hurst > 0.5).
    Compare to equal-weight buy & hold of the universe.
    """
    panels = {}
    for t in tickers:
        df = fetch(t, period)
        sig = build_fmh(df, p)
        score = sig["align"] * sig["coherence"]
        if p.use_hurst_gate and sig["hurst"] is not None:
            score = score.where(sig["hurst"].fillna(0) >= p.hurst_min, 0)
        panels[t] = pd.DataFrame({
            "close": df["Close"],
            "ret": df["Close"].pct_change().fillna(0),
            "score": score,
        })

    # align all on common index
    idx = panels[tickers[0]].index
    for t in tickers[1:]:
        idx = idx.intersection(panels[t].index)
    rets = pd.DataFrame({t: panels[t].loc[idx, "ret"] for t in tickers})
    scores = pd.DataFrame({t: panels[t].loc[idx, "score"] for t in tickers})

    # rebalance every hold_bars
    rebal_mask = (np.arange(len(idx)) % hold_bars) == 0
    weights = pd.DataFrame(0.0, index=idx, columns=tickers)
    cur_w = pd.Series(0.0, index=tickers)
    for i, ts in enumerate(idx):
        if rebal_mask[i]:
            s = scores.iloc[i]
            ranked = s.sort_values(ascending=False)
            chosen = ranked.head(top_n).index
            chosen = [c for c in chosen if s[c] > 0]
            if chosen:
                cur_w = pd.Series(0.0, index=tickers)
                cur_w.loc[chosen] = 1.0 / len(chosen)
            else:
                cur_w = pd.Series(0.0, index=tickers)
        weights.iloc[i] = cur_w.values

    weights_lag = weights.shift(1).fillna(0)
    turn = (weights_lag.diff().abs().sum(axis=1)).fillna(0)
    cost = turn * (cost_bps / 1e4)
    strat_ret = (weights_lag * rets).sum(axis=1) - cost

    # benchmark = equal-weight buy & hold
    bh_ret = rets.mean(axis=1)

    s_strat = stats(strat_ret)
    s_bh = stats(bh_ret)
    return dict(ticker=f"ROT[{','.join(tickers)}]top{top_n}/{hold_bars}d",
                yrs=len(idx) / 252, strat=s_strat, bh=s_bh,
                tim=(weights_lag.sum(axis=1) > 0).mean(),
                turn=turn.sum() / (len(turn) / 252),
                ret_strat=strat_ret, ret_bh=bh_ret)


def fmt_row(r):
    s, b = r["strat"], r["bh"]
    alpha = s["CAGR"] - b["CAGR"]
    shp_alpha = s["Sharpe"] - b["Sharpe"]
    name = f"{r['ticker']}/{r.get('mode','')}".strip("/")
    return (f"{name:38s} {r['yrs']:5.1f}  "
            f"{s['CAGR']:>7.2%}  {b['CAGR']:>7.2%}  {alpha:>+7.2%}  "
            f"{s['Sharpe']:>5.2f}  {b['Sharpe']:>5.2f}  {shp_alpha:>+5.2f}  "
            f"{s['MaxDD']:>7.2%}  {b['MaxDD']:>7.2%}  "
            f"{r['tim']:>5.2%}  {r['turn']:>5.1f}")


HEADER = (f"{'name':38s} {'yrs':>5s}  "
          f"{'CAGR':>7s}  {'B&H':>7s}  {'Δcagr':>7s}  "
          f"{'Shp':>5s}  {'B&H':>5s}  {'Δshp':>5s}  "
          f"{'MaxDD':>7s}  {'B&H':>7s}  "
          f"{'TiM':>5s}  {'Turn':>5s}")


if __name__ == "__main__":
    p_balanced = FMHParams(
        scales=(5, 8, 13, 21, 34, 55, 89),
        coherence_tau=0.55,
        smooth_bars=3,
        r2_min=0.05,
        hurst_min=0.50,
        use_hurst_gate=True,
        vol_target=0.0,
    )

    print("Configuration: φ-spaced scales (5,8,13,21,34,55,89); "
          "coherence≥0.55; Hurst≥0.5; smoothing=3 bars; cost=1 bp")
    print()
    print(HEADER)

    # Test 1: long-flat single asset
    print("\n--- Long-flat single-asset timing ---")
    for t in ["SPY", "QQQ", "IWM", "GLD", "TLT", "BTC-USD"]:
        try:
            r = single_asset(t, "long_flat", p_balanced)
            print(fmt_row(r))
        except Exception as e:
            print(f"{t}: {e}")

    # Test 2: long-short single asset
    print("\n--- Long-short single-asset timing ---")
    for t in ["SPY", "QQQ", "BTC-USD", "GLD", "TLT"]:
        try:
            r = single_asset(t, "long_short", p_balanced)
            print(fmt_row(r))
        except Exception as e:
            print(f"{t}: {e}")

    # Test 3: cross-sectional rotation
    print("\n--- Cross-sectional rotation (top-1 every 5d, no leverage, no shorting) ---")
    universe = ["SPY", "QQQ", "IWM", "EFA", "EEM", "GLD", "TLT", "HYG", "VNQ"]
    for top_n in (1, 2, 3):
        try:
            r = cross_section(universe, p_balanced, period="15y",
                              top_n=top_n, hold_bars=5)
            print(fmt_row(r))
        except Exception as e:
            print(f"rotation top{top_n}: {e}")

    print("\n--- Cross-sectional rotation, weekly rebalance, top-2 ---")
    for hb in (5, 10, 20):
        try:
            r = cross_section(universe, p_balanced, period="15y",
                              top_n=2, hold_bars=hb)
            print(fmt_row(r))
        except Exception as e:
            print(f"rotation hb={hb}: {e}")
