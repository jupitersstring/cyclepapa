"""
True multi-TF FMH lock-picker on intraday + daily + weekly + monthly.

Closer to the original Pine Script: each TF has its own native bar series
(resampled from 60m yfinance data to 90m / 1d / 1w / 1mo), an HMA-slope
direction is computed natively at that TF, then signals are reindexed back
to the 90m base bar for trading.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass
from fmh_lockpicker import hurst_dfa
from hull_mitm import hma


@dataclass
class MTFParams:
    # Resample rules from a 60m source.  Order = fastest → slowest.
    tf_freqs: tuple = ("90min", "1D", "1W", "1ME")
    # HMA length used inside each TF's own series.
    hma_lens: tuple = (30, 21, 13, 8)
    # Per-pair weight (fastest→slowest): how much each TF counts in coherence.
    weights: tuple = (1, 3, 5, 8)
    coherence_tau: float = 0.55
    smooth_bars: int = 2
    # Hurst gate computed on the base (90m) returns.
    use_hurst_gate: bool = True
    hurst_window: int = 500    # ~ a few months of 90m bars
    hurst_dfa_scales: tuple = (8, 16, 32, 64, 128)
    hurst_min: float = 0.50


def fetch_60m(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="730d", interval="60m",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def per_tf_dir(close: pd.Series, freq: str, n: int) -> pd.Series:
    """Resample close to freq, compute HMA(n) slope sign over 2 bars."""
    c = close.resample(freq).last().dropna()
    h = hma(c, n)
    d = np.sign(h - h.shift(2)).fillna(0).astype(int)
    return d


def build_signal(df60: pd.DataFrame, p: MTFParams):
    close = df60["Close"]
    base_close = close.resample(p.tf_freqs[0]).last().dropna()
    base_idx = base_close.index

    dirs = []
    for freq, n in zip(p.tf_freqs, p.hma_lens):
        d = per_tf_dir(close, freq, n)
        d = d.reindex(base_idx, method="ffill").fillna(0).astype(int)
        dirs.append(d)

    W = np.array(p.weights, dtype=float)
    Wsum = W.sum()
    align = sum(d * w for d, w in zip(dirs, W)) / Wsum         # in [-1,1]
    pin_strength = sum(d.abs() * w for d, w in zip(dirs, W)) / Wsum
    coherence = (align.abs() / pin_strength.replace(0, np.nan)).fillna(0)
    direction = np.sign(align).astype(int)

    # Hurst on base (90m) returns
    if p.use_hurst_gate:
        rets = base_close.pct_change().fillna(0)
        H = hurst_dfa(rets, p.hurst_window, p.hurst_dfa_scales)
    else:
        H = pd.Series(0.5, index=base_idx)

    trade_ok = coherence >= p.coherence_tau
    if p.use_hurst_gate:
        trade_ok = trade_ok & (H.fillna(0) >= p.hurst_min)

    raw_pos = direction.where(trade_ok, 0).astype(int)

    # require N consecutive bars same nonzero sign
    if p.smooth_bars > 1:
        out = []
        last = 0
        run = 0
        for v in raw_pos.values:
            if v != 0 and v == last:
                run += 1
            elif v != 0 and v != last:
                run = 1
                last = v
            else:
                run = 0
                last = 0
            out.append(last if run >= p.smooth_bars else 0)
        raw_pos = pd.Series(out, index=raw_pos.index)

    return dict(
        base_close=base_close,
        position=raw_pos,
        align=align,
        coherence=coherence,
        hurst=H,
        dirs=dirs,
    )


def backtest_intraday(base_close: pd.Series, position: pd.Series,
                      cost_bps: float = 1.0, bars_per_year: int = 252 * 4):
    ret = base_close.pct_change().fillna(0)
    pos = position.shift(1).fillna(0).astype(float)
    turn = pos.diff().abs().fillna(pos.abs())
    cost = turn * (cost_bps / 1e4)
    strat = pos * ret - cost
    eq_s = (1 + strat).cumprod()
    eq_b = (1 + ret).cumprod()

    def stats(r, eq):
        r = r.dropna()
        if len(r) < 30 or r.std() == 0:
            return dict(CAGR=0.0, Sharpe=0.0, MaxDD=0.0)
        cagr = eq.iloc[-1] ** (bars_per_year / len(r)) - 1
        shp = r.mean() / r.std() * np.sqrt(bars_per_year)
        dd = (eq / eq.cummax() - 1).min()
        return dict(CAGR=cagr, Sharpe=shp, MaxDD=dd)

    return dict(
        strategy=stats(strat, eq_s),
        buy_hold=stats(ret, eq_b),
        time_in_market=(pos.abs() > 0).mean(),
        turnover_per_year=turn.sum() / (len(turn) / bars_per_year),
        eq_strategy=eq_s,
        eq_buyhold=eq_b,
    )


def run(ticker: str, p: MTFParams = None, mode: str = "long_short",
        cost_bps: float = 1.0):
    p = p or MTFParams()
    df60 = fetch_60m(ticker)
    sig = build_signal(df60, p)
    pos = sig["position"].astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    bt = backtest_intraday(sig["base_close"], pos, cost_bps=cost_bps)
    bt.update(sig)
    bt["ticker"] = ticker
    bt["mode"] = mode
    return bt


HEADER = (f"{'name':14s} {'mode':10s} {'bars':>5s}  "
          f"{'CAGR':>8s} {'B&H':>8s} {'Δ':>8s}  "
          f"{'Shp':>5s} {'B&H':>5s} {'Δ':>5s}  "
          f"{'MaxDD':>7s} {'B&H':>7s}  "
          f"{'TiM':>5s} {'Turn/y':>6s}")


def fmt(t, mode, r):
    s, b = r["strategy"], r["buy_hold"]
    return (f"{t:14s} {mode:10s} {len(r['eq_strategy']):>5d}  "
            f"{s['CAGR']:>8.2%} {b['CAGR']:>8.2%} {s['CAGR']-b['CAGR']:>+8.2%}  "
            f"{s['Sharpe']:>5.2f} {b['Sharpe']:>5.2f} {s['Sharpe']-b['Sharpe']:>+5.2f}  "
            f"{s['MaxDD']:>7.2%} {b['MaxDD']:>7.2%}  "
            f"{r['time_in_market']:>5.2%} {r['turnover_per_year']:>6.1f}")


if __name__ == "__main__":
    import sys
    universe = sys.argv[1:] or [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
        "AMD", "COIN", "NFLX", "AVGO", "CRM",
    ]
    p = MTFParams()
    print(f"TFs={p.tf_freqs}  HMA={p.hma_lens}  weights={p.weights}  "
          f"coh≥{p.coherence_tau}  smooth={p.smooth_bars}  "
          f"H≥{p.hurst_min} (gate={p.use_hurst_gate})")
    print(HEADER)
    summary = []
    for t in universe:
        for mode in ("long_short", "long_flat"):
            try:
                r = run(t, p, mode=mode)
                print(fmt(t, mode, r))
                summary.append((t, mode, r))
            except Exception as e:
                print(f"{t} {mode}: {e}")

    # Aggregate
    print("\n--- aggregate medians ---")
    for mode in ("long_short", "long_flat"):
        rows = [r for (t, m, r) in summary if m == mode]
        if not rows:
            continue
        med_alpha = np.median([r["strategy"]["CAGR"] - r["buy_hold"]["CAGR"] for r in rows])
        med_dshp = np.median([r["strategy"]["Sharpe"] - r["buy_hold"]["Sharpe"] for r in rows])
        med_dd_strat = np.median([r["strategy"]["MaxDD"] for r in rows])
        med_dd_bh = np.median([r["buy_hold"]["MaxDD"] for r in rows])
        win_cagr = np.mean([r["strategy"]["CAGR"] > r["buy_hold"]["CAGR"] for r in rows])
        win_shp = np.mean([r["strategy"]["Sharpe"] > r["buy_hold"]["Sharpe"] for r in rows])
        print(f"{mode:10s}  median Δcagr={med_alpha:+.2%}  "
              f"median Δshp={med_dshp:+.2f}  "
              f"median MaxDD strat={med_dd_strat:.1%} vs B&H={med_dd_bh:.1%}  "
              f"win-rate CAGR={win_cagr:.0%}  Shp={win_shp:.0%}")
