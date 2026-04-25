"""
Equal-weight basket backtest of the RSI-MTF / MFI-MTF / Stoch-MTF / HMA-MTF
strategies on a wider single-name universe.

Each name runs its own 4-TF (90m/1d/1w/1mo) signal. Daily portfolio return
= mean(strategy_return_i) — equal weight, fully invested across N sleeves.
Compared to equal-weight buy-hold of the same N names.

Idiosyncratic noise averages out across the basket, which is the right
test for whether the per-name alpha aggregates into a deployable strategy.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from fmh_multitf import fetch_60m, MTFParams, build_signal as build_hma_signal
from fmh_indicators import (
    StratParams, strat_indicator_mtf, strat_hma_x_rsi, strat_rsi_meanrev,
)


# Diverse 30-name universe: tech/growth + financials + staples + energy +
# health + industrials + consumer.  All have ~3y of yfinance 60m coverage.
UNIVERSE = [
    # mega-cap tech / growth
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "AMD", "AVGO", "CRM", "NFLX", "ORCL",
    # financials
    "JPM", "BAC", "GS", "V", "MA",
    # staples / retail
    "WMT", "COST", "HD",
    # health
    "LLY", "UNH", "JNJ",
    # consumer
    "PG", "KO", "DIS",
    # energy / industrial
    "XOM", "CVX", "CAT", "BA",
]


def stats_of(ret: pd.Series, ann: int = 252 * 4):
    """ann = 252 trading days × ~4 90m bars/day."""
    ret = ret.dropna()
    if len(ret) < 30 or ret.std() == 0:
        return dict(CAGR=0.0, Sharpe=0.0, MaxDD=0.0, Vol=0.0)
    eq = (1 + ret).cumprod()
    cagr = eq.iloc[-1] ** (ann / len(ret)) - 1
    shp = ret.mean() / ret.std() * np.sqrt(ann)
    dd = (eq / eq.cummax() - 1).min()
    vol = ret.std() * np.sqrt(ann)
    return dict(CAGR=cagr, Sharpe=shp, MaxDD=dd, Vol=vol)


def per_name_returns(df60: pd.DataFrame, sp: StratParams, mode: str):
    """
    Build a dict {strategy_name: (strat_ret_series, bh_ret_series)} for one
    ticker, all on the 90m base index.
    """
    out = {}

    # 1. HMA-MTF baseline
    p = MTFParams(coherence_tau=sp.coherence_tau, smooth_bars=sp.smooth_bars)
    sig = build_hma_signal(df60, p)
    bc = sig["base_close"]
    bh = bc.pct_change().fillna(0)
    pos = sig["position"].astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    pos_lag = pos.shift(1).fillna(0)
    turnover = pos_lag.diff().abs().fillna(pos_lag.abs())
    cost = turnover * (1 / 1e4)
    strat = pos_lag * bh - cost
    out["HMA-MTF"] = (strat, bh, pos_lag)

    for kind in ("rsi", "mfi", "stoch"):
        bc, raw = strat_indicator_mtf(df60, kind, sp)
        bh = bc.pct_change().fillna(0)
        pos = raw.astype(float)
        if mode == "long_flat":
            pos = pos.clip(lower=0)
        pos_lag = pos.shift(1).fillna(0)
        turnover = pos_lag.diff().abs().fillna(pos_lag.abs())
        cost = turnover * (1 / 1e4)
        strat = pos_lag * bh - cost
        out[kind.upper() + "-MTF"] = (strat, bh, pos_lag)

    bc, raw = strat_hma_x_rsi(df60, sp)
    bh = bc.pct_change().fillna(0)
    pos = raw.astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    pos_lag = pos.shift(1).fillna(0)
    turnover = pos_lag.diff().abs().fillna(pos_lag.abs())
    cost = turnover * (1 / 1e4)
    strat = pos_lag * bh - cost
    out["HMA×RSI-gate"] = (strat, bh, pos_lag)

    return out


def basket_run(universe, sp: StratParams, mode: str):
    """Returns: dict[strategy] -> dict(strat_ret, bh_ret, position) all on
    the union 90m index, mean-aggregated across the universe."""
    per_name = {}
    for t in universe:
        try:
            df60 = fetch_60m(t)
            per_name[t] = per_name_returns(df60, sp, mode)
        except Exception as e:
            print(f"  skip {t}: {e}")
    # Union index across all tickers (90m)
    idx = None
    for t, d in per_name.items():
        for _, (s, _, _) in d.items():
            idx = s.index if idx is None else idx.union(s.index)

    strat_names = next(iter(per_name.values())).keys()
    out = {}
    for sname in strat_names:
        strat_mat = pd.DataFrame(index=idx)
        bh_mat = pd.DataFrame(index=idx)
        pos_mat = pd.DataFrame(index=idx)
        for t, d in per_name.items():
            s, b, p = d[sname]
            strat_mat[t] = s.reindex(idx)
            bh_mat[t] = b.reindex(idx)
            pos_mat[t] = p.reindex(idx)
        # equal weight across all available names per bar (NaN tickers
        # excluded from that bar, per-bar normalization)
        n_avail = strat_mat.notna().sum(axis=1).replace(0, np.nan)
        strat_ret = (strat_mat.fillna(0).sum(axis=1) / n_avail).fillna(0)
        bh_ret = (bh_mat.fillna(0).sum(axis=1) / n_avail).fillna(0)
        out[sname] = dict(
            strat_ret=strat_ret,
            bh_ret=bh_ret,
            tim=(pos_mat.abs().fillna(0) > 0).mean().mean(),
            n_names=len(per_name),
        )
    return out


HEADER = (f"{'strategy':14s}  "
          f"{'CAGR':>8s} {'B&H':>8s} {'Δ':>8s}  "
          f"{'Shp':>5s} {'B&H':>5s} {'Δ':>5s}  "
          f"{'Sortino':>7s}  "
          f"{'Vol':>6s} {'B&H':>6s}  "
          f"{'MaxDD':>7s} {'B&H':>7s}  "
          f"{'TiM':>5s}")


def fmt_basket(name, res):
    s = stats_of(res["strat_ret"])
    b = stats_of(res["bh_ret"])
    # sortino
    r = res["strat_ret"].dropna()
    dn = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(252 * 4) if dn > 0 else 0.0
    return (f"{name:14s}  "
            f"{s['CAGR']:>8.2%} {b['CAGR']:>8.2%} {s['CAGR']-b['CAGR']:>+8.2%}  "
            f"{s['Sharpe']:>5.2f} {b['Sharpe']:>5.2f} {s['Sharpe']-b['Sharpe']:>+5.2f}  "
            f"{sortino:>7.2f}  "
            f"{s['Vol']:>6.1%} {b['Vol']:>6.1%}  "
            f"{s['MaxDD']:>7.2%} {b['MaxDD']:>7.2%}  "
            f"{res['tim']:>5.2%}")


if __name__ == "__main__":
    sp = StratParams()
    print(f"Universe: {len(UNIVERSE)} single names — {UNIVERSE}")
    print(f"TFs={sp.tf_freqs}  weights={sp.weights}  coh≥{sp.coherence_tau}  "
          f"smooth={sp.smooth_bars}  deadband=±{sp.deadband}")

    for mode in ("long_short", "long_flat"):
        print(f"\n=== EQUAL-WEIGHT BASKET — mode={mode} ===")
        print(HEADER)
        out = basket_run(UNIVERSE, sp, mode)
        for name, res in out.items():
            print(fmt_basket(name, res))
