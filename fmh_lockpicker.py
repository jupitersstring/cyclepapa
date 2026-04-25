"""
FMH Lock-picker.

Fractal Market Hypothesis (Edgar Peters) reinterpretation of the Hull MITM
"lock picking" idea:

  - Markets are stable when investors of *many self-similar horizons* coexist.
  - Each horizon is a "pin" in the lock.  A pin is "set" when its scale is
    persistent (Hurst H_s > 0.5) AND the price drift at that scale has a sign.
  - The lock is "picked" (trade) when a quorum of self-similar scales agree
    in direction AND the global market shows fractal persistence (no horizon
    collapse).
  - Position sizing scales with cross-scale *coherence* (alignment quality)
    and is dampened when the fractal structure breaks down (H near 0.5 or
    falling) — the FMH signature of an unstable / about-to-crash market.

Scales are geometric (powers of phi or 2) so they are genuinely self-similar.

Signal pipeline:
  1. Per scale N_s:
        slope_s   = OLS slope of log(close) over the last N_s bars
        tstat_s   = slope * sqrt(N_s) / sigma(returns)          [strength]
        R2_s      = regression R^2                              [trendiness]
        H_s       = rolling Hurst (DFA) over a window ~ k*N_max [persistence]
  2. Pin signal:
        pin_s     = sign(slope_s)  if R2_s >= R2_min and H_s >= 0.5  else 0
  3. Composite:
        align     = sum_s w_s * pin_s              (signed in [-Wsum,+Wsum])
        coherence = |align| / sum_s w_s            (in [0,1])
        regime_ok = (median H_s) >= H_min           (no horizon collapse)
  4. Position:
        pos = sign(align) * I(coherence >= tau, regime_ok)
        size = coherence  (optional vol-targeting)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field


# ───────────────────────────────────────────── primitives ──
def rolling_ols_slope_r2(y: pd.Series, n: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Rolling OLS slope of y vs t-index over n bars: returns slope, t-stat, R^2."""
    n = int(n)
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    sxx = ((x - x_mean) ** 2).sum()

    def _calc(v):
        y_mean = v.mean()
        sxy = ((x - x_mean) * (v - y_mean)).sum()
        slope = sxy / sxx
        intercept = y_mean - slope * x_mean
        resid = v - (intercept + slope * x)
        sse = (resid ** 2).sum()
        sst = ((v - y_mean) ** 2).sum()
        r2 = 0.0 if sst == 0 else 1 - sse / sst
        sigma = np.sqrt(sse / max(n - 2, 1))
        tstat = 0.0 if sigma == 0 else slope * np.sqrt(sxx) / sigma
        return slope, tstat, r2

    out = y.rolling(n).apply(lambda v: _calc(v)[0], raw=True)
    tstat = y.rolling(n).apply(lambda v: _calc(v)[1], raw=True)
    r2 = y.rolling(n).apply(lambda v: _calc(v)[2], raw=True)
    return out, tstat, r2


def hurst_dfa(returns: pd.Series, window: int, scales=(4, 8, 16, 32, 64)) -> pd.Series:
    """
    Rolling DFA Hurst exponent on a returns series.

    For each rolling window of length `window`, integrate cumulative deviation
    from mean, partition into non-overlapping segments of size s for each s in
    `scales`, fit a quadratic detrend, and compute fluctuation F(s).
    H is the slope of log F(s) vs log s.
    """
    rets = returns.fillna(0).to_numpy()
    out = np.full(len(rets), np.nan)
    scales = [s for s in scales if s <= window // 4]
    if len(scales) < 2:
        return pd.Series(out, index=returns.index)
    log_s = np.log(scales)
    for i in range(window, len(rets)):
        seg = rets[i - window:i]
        # cumulative deviation
        y = np.cumsum(seg - seg.mean())
        F = []
        for s in scales:
            n_seg = window // s
            if n_seg < 2:
                F.append(np.nan)
                continue
            ys = y[:n_seg * s].reshape(n_seg, s)
            x = np.arange(s)
            # linear detrend each segment, then RMS
            x_mean = x.mean()
            sxx = ((x - x_mean) ** 2).sum()
            slopes = ((x - x_mean)[None, :] * (ys - ys.mean(axis=1, keepdims=True))).sum(axis=1) / sxx
            intercepts = ys.mean(axis=1) - slopes * x_mean
            resid = ys - (intercepts[:, None] + slopes[:, None] * x)
            F.append(np.sqrt((resid ** 2).mean()))
        F = np.array(F)
        if np.any(np.isnan(F)) or np.any(F <= 0):
            continue
        log_F = np.log(F)
        # OLS slope log_F vs log_s
        a = np.vstack([log_s, np.ones_like(log_s)]).T
        h, _ = np.linalg.lstsq(a, log_F, rcond=None)[0]
        out[i] = h
    return pd.Series(out, index=returns.index)


# ───────────────────────────────────────────── core signal ──
@dataclass
class FMHParams:
    # Self-similar scales (geometric).  Default ≈ φ-spaced for fractal flavor.
    scales: tuple = (5, 8, 13, 21, 34, 55, 89)         # Fibonacci, "phi-like"
    weights: tuple = None                              # auto: 1/sqrt(N) if None
    r2_min: float = 0.05                               # min trendiness per scale
    hurst_min: float = 0.50                            # FMH persistence floor
    coherence_tau: float = 0.40                        # required cross-scale alignment
    hurst_window: int = 252                            # 1 year rolling window for H
    hurst_dfa_scales: tuple = (4, 8, 16, 32, 64)
    use_hurst_gate: bool = True
    use_global_hurst: bool = True
    vol_target: float = 0.15                           # annualized vol target
    vol_lookback: int = 60
    # Position smoothing
    smooth_bars: int = 3                               # require N consecutive bars same sign


def build_fmh(df: pd.DataFrame, p: FMHParams):
    close = df["Close"].astype(float)
    log_p = np.log(close)
    rets = close.pct_change().fillna(0)

    scales = list(p.scales)
    weights = list(p.weights) if p.weights else [1.0 / np.sqrt(s) for s in scales]
    Wsum = sum(weights)

    pins = []        # signed direction signal per scale
    coh_terms = []   # contribution to coherence per scale
    diag = {}

    sigma = rets.rolling(p.vol_lookback).std() * np.sqrt(252)

    for N, w in zip(scales, weights):
        slope, tstat, r2 = rolling_ols_slope_r2(log_p, N)
        # Persistence proxy at this scale: combine R² and t-stat magnitude
        # (R² ≥ r2_min keeps weak/noise scales out of the "set" pin pool)
        valid = (r2 >= p.r2_min)
        sgn = np.sign(slope).fillna(0).astype(int)
        pin = sgn.where(valid, 0).astype(int)
        pins.append(pin * w)
        coh_terms.append(pin.abs() * w)
        diag[f"slope_{N}"] = slope
        diag[f"r2_{N}"] = r2

    align = sum(pins)                       # signed weighted sum
    pin_strength = sum(coh_terms)           # how many scales are "set" (weighted)
    # signed coherence: how unanimously the set pins agree
    # = |align| / pin_strength when any pin is set, else 0
    with np.errstate(divide="ignore", invalid="ignore"):
        coherence = (align.abs() / pin_strength.replace(0, np.nan)).fillna(0)
    direction = np.sign(align).astype(int)

    # Global Hurst regime gate
    H = hurst_dfa(rets, p.hurst_window, p.hurst_dfa_scales) if p.use_global_hurst else None

    # Trade gate
    trade_ok = coherence >= p.coherence_tau
    if p.use_hurst_gate and H is not None:
        trade_ok = trade_ok & (H.fillna(0) >= p.hurst_min)

    raw_pos = direction.where(trade_ok, 0).astype(int)

    # Smoothing: require N consecutive bars with the same nonzero sign before flipping
    if p.smooth_bars > 1:
        smoothed = raw_pos.copy()
        last = 0
        run = 0
        out = []
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
        smoothed = pd.Series(out, index=raw_pos.index)
        raw_pos = smoothed

    # Optional volatility targeting
    if p.vol_target and p.vol_target > 0:
        scale_factor = (p.vol_target / sigma.replace(0, np.nan)).clip(0, 3).fillna(0)
        size = raw_pos * scale_factor * coherence
    else:
        size = raw_pos * coherence

    return dict(
        align=align / Wsum,
        coherence=coherence,
        direction=direction,
        hurst=H,
        position=size,         # vol-targeted, signed continuous
        binary_position=raw_pos,
        pin_strength=pin_strength / Wsum,
        diag=diag,
    )


# ───────────────────────────────────────────── backtest ──
def backtest(df: pd.DataFrame, position: pd.Series,
             cost_bps: float = 1.0, ann: int = 252):
    px = df["Close"].astype(float)
    ret = px.pct_change().fillna(0)
    pos = position.shift(1).fillna(0)            # next-bar execution
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (cost_bps / 1e4)
    strat = pos * ret - cost
    eq_s = (1 + strat).cumprod()
    eq_b = (1 + ret).cumprod()

    def stats(r, eq):
        r = r.dropna()
        if r.std() == 0 or len(r) < 30:
            return dict(CAGR=0.0, Sharpe=0.0, Sortino=0.0, MaxDD=0.0, Hit=0.0)
        cagr = eq.iloc[-1] ** (ann / len(r)) - 1
        sharpe = r.mean() / r.std() * np.sqrt(ann)
        downside = r[r < 0].std()
        sortino = r.mean() / downside * np.sqrt(ann) if downside > 0 else 0.0
        dd = (eq / eq.cummax() - 1).min()
        hit = (r > 0).mean()
        return dict(CAGR=cagr, Sharpe=sharpe, Sortino=sortino, MaxDD=dd, Hit=hit)

    return dict(
        strategy=stats(strat, eq_s),
        buy_hold=stats(ret, eq_b),
        eq_strategy=eq_s,
        eq_buyhold=eq_b,
        position=pos,
        turnover_per_year=turnover.sum() / (len(turnover) / ann),
        alpha_CAGR=stats(strat, eq_s)["CAGR"] - stats(ret, eq_b)["CAGR"],
        time_in_market=(pos.abs() > 0).mean(),
    )


def run(ticker: str, period="15y", p: FMHParams | None = None,
        cost_bps: float = 1.0):
    p = p or FMHParams()
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    sig = build_fmh(df, p)
    bt = backtest(df, sig["position"], cost_bps=cost_bps)
    bt.update(sig)
    bt["df"] = df
    bt["ticker"] = ticker
    return bt


def print_row(t, r, yrs):
    s, b = r["strategy"], r["buy_hold"]
    print(f"{t:8s} {yrs:5.1f} "
          f" {s['CAGR']:>7.2%}  {b['CAGR']:>7.2%}  {r['alpha_CAGR']:>7.2%}  "
          f"{s['Sharpe']:>5.2f} {s['Sortino']:>5.2f} {s['MaxDD']:>7.2%} "
          f"{s['Hit']:>5.2%} {r['time_in_market']:>5.2%} {r['turnover_per_year']:>5.1f}")


HEADER = (f"{'ticker':8s} {'yrs':>5s}  "
          f"{'CAGR':>7s}  {'B&H':>7s}  {'Alpha':>7s}  "
          f"{'Shp':>5s} {'Sor':>5s} {'MaxDD':>7s} "
          f"{'Hit':>5s} {'TiM':>5s} {'Turn':>5s}")


if __name__ == "__main__":
    import sys
    tickers = sys.argv[1:] or ["SPY", "QQQ", "IWM", "GLD", "TLT", "BTC-USD", "EFA", "EEM"]
    p = FMHParams()
    print(HEADER)
    for t in tickers:
        try:
            r = run(t, period="15y", p=p)
            print_row(t, r, len(r["df"]) / 252)
        except Exception as e:
            print(f"{t}: {e}")
