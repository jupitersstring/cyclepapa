"""
Variant studies layering RSI / MFI / Stochastic / Bollinger-z onto the
multi-TF FMH framework, to see whether momentum/mean-reversion indicators
lead the HMA-slope direction (and therefore fix the late-entry problem).

For each indicator we build a per-TF signal in [-1,0,+1], aggregate across
4 TFs (90m, 1d, 1w, 1mo) with weights (1,3,5,8), and trade on the 90m base.

Five strategies are compared head-to-head per ticker:
  1. HMA-MTF        (baseline from fmh_multitf.py)
  2. RSI-MTF        (RSI cross 50 alignment across TFs)
  3. MFI-MTF        (Money Flow Index cross 50 — volume-weighted RSI)
  4. STOCH-MTF      (Stochastic %K cross 50)
  5. HMA × RSI gate (HMA direction, only when same-side RSI confirms)
  6. RSI mean-rev   (long when RSI<30 then crosses up, flat at >70)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass

from fmh_multitf import (
    fetch_60m, MTFParams, build_signal as build_hma_signal,
    backtest_intraday,
)
from hull_mitm import hma


# ─── primitives ─────────────────────────────────────────────────────
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def mfi(high: pd.Series, low: pd.Series, close: pd.Series,
        volume: pd.Series, n: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    raw_mf = tp * volume
    direction = np.sign(tp.diff()).fillna(0)
    pos_mf = raw_mf.where(direction > 0, 0).rolling(n).sum()
    neg_mf = raw_mf.where(direction < 0, 0).rolling(n).sum()
    mr = pos_mf / neg_mf.replace(0, np.nan)
    return (100 - 100 / (1 + mr)).fillna(50)


def stoch_k(high: pd.Series, low: pd.Series, close: pd.Series,
            n: int = 14) -> pd.Series:
    ll = low.rolling(n).min()
    hh = high.rolling(n).max()
    return (100 * (close - ll) / (hh - ll).replace(0, np.nan)).fillna(50)


def psar(high: pd.Series, low: pd.Series,
         af_start: float = 0.02, af_step: float = 0.02,
         af_max: float = 0.20) -> tuple[pd.Series, pd.Series]:
    """
    Wilder's Parabolic SAR.  Returns (sar, trend) where trend is +1 (long) /
    -1 (short).  Direction = trend (already binary, no deadband needed).
    """
    h = high.to_numpy()
    l = low.to_numpy()
    n = len(h)
    sar = np.zeros(n)
    trend = np.zeros(n, dtype=int)
    if n < 2:
        return pd.Series(sar, index=high.index), pd.Series(trend, index=high.index)

    # init: assume long if first close-to-close goes up
    trend[0] = 1
    ep = h[0]
    af = af_start
    sar[0] = l[0]

    for i in range(1, n):
        prev_sar = sar[i - 1]
        prev_trend = trend[i - 1]
        prev_ep = ep
        prev_af = af

        sar_i = prev_sar + prev_af * (prev_ep - prev_sar)
        if prev_trend == 1:
            # SAR cannot be above last two lows
            sar_i = min(sar_i, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < sar_i:
                # flip to down
                trend[i] = -1
                sar[i] = prev_ep             # SAR resets to prior EP
                ep = l[i]
                af = af_start
                continue
            trend[i] = 1
            if h[i] > prev_ep:
                ep = h[i]
                af = min(prev_af + af_step, af_max)
            else:
                ep = prev_ep
                af = prev_af
            sar[i] = sar_i
        else:
            sar_i = max(sar_i, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > sar_i:
                trend[i] = 1
                sar[i] = prev_ep
                ep = h[i]
                af = af_start
                continue
            trend[i] = -1
            if l[i] < prev_ep:
                ep = l[i]
                af = min(prev_af + af_step, af_max)
            else:
                ep = prev_ep
                af = prev_af
            sar[i] = sar_i
    return pd.Series(sar, index=high.index), pd.Series(trend, index=high.index)


def per_tf_indicator_dir(df60: pd.DataFrame, freq: str, kind: str,
                         length: int = 14, deadband: float = 5) -> pd.Series:
    """
    Resample OHLCV to freq, compute indicator, return signal in [-1,0,+1]
    based on cross above/below 50 with a deadband.  PSAR returns its
    native +1/-1 trend (no deadband).
    """
    o = df60["Open"].resample(freq).first()
    h = df60["High"].resample(freq).max()
    l = df60["Low"].resample(freq).min()
    c = df60["Close"].resample(freq).last()
    v = df60["Volume"].resample(freq).sum()
    df = pd.DataFrame({"O": o, "H": h, "L": l, "C": c, "V": v}).dropna()

    if kind == "rsi":
        ind = rsi(df["C"], length)
    elif kind == "mfi":
        ind = mfi(df["H"], df["L"], df["C"], df["V"], length)
    elif kind == "stoch":
        ind = stoch_k(df["H"], df["L"], df["C"], length)
    elif kind == "psar":
        _, trend = psar(df["H"], df["L"])
        return trend.astype(int), trend
    else:
        raise ValueError(kind)

    sig = pd.Series(0, index=ind.index)
    sig[ind >= 50 + deadband] = 1
    sig[ind <= 50 - deadband] = -1
    return sig, ind


def aggregate_dirs(dirs: list[pd.Series], weights, base_idx) -> tuple[pd.Series, pd.Series]:
    W = np.array(weights, dtype=float)
    Wsum = W.sum()
    aligned = []
    pin_strength = []
    for d, w in zip(dirs, W):
        d = d.reindex(base_idx, method="ffill").fillna(0).astype(int)
        aligned.append(d * w)
        pin_strength.append(d.abs() * w)
    align = sum(aligned) / Wsum
    pin = sum(pin_strength) / Wsum
    coherence = (align.abs() / pin.replace(0, np.nan)).fillna(0)
    return align, coherence


def smooth_consec(raw_pos: pd.Series, n: int) -> pd.Series:
    if n <= 1:
        return raw_pos
    out, last, run = [], 0, 0
    for v in raw_pos.values:
        if v != 0 and v == last:
            run += 1
        elif v != 0 and v != last:
            run = 1
            last = v
        else:
            run = 0
            last = 0
        out.append(last if run >= n else 0)
    return pd.Series(out, index=raw_pos.index)


# ─── strategy implementations ──────────────────────────────────────
@dataclass
class StratParams:
    tf_freqs: tuple = ("90min", "1D", "1W", "1ME")
    weights: tuple = (1, 3, 5, 8)
    rsi_len: tuple = (14, 14, 14, 14)
    coherence_tau: float = 0.55
    smooth_bars: int = 2
    deadband: float = 5.0


def strat_indicator_mtf(df60, kind: str, sp: StratParams):
    """Per-TF indicator-cross-50 alignment, trade on 90m base."""
    base_close = df60["Close"].resample(sp.tf_freqs[0]).last().dropna()
    base_idx = base_close.index
    dirs = []
    for freq, n in zip(sp.tf_freqs, sp.rsi_len):
        sig, _ = per_tf_indicator_dir(df60, freq, kind, n, sp.deadband)
        dirs.append(sig)
    align, coh = aggregate_dirs(dirs, sp.weights, base_idx)
    direction = np.sign(align).astype(int)
    raw_pos = direction.where(coh >= sp.coherence_tau, 0).astype(int)
    raw_pos = smooth_consec(raw_pos, sp.smooth_bars)
    return base_close, raw_pos


def strat_hma_x_rsi(df60, sp: StratParams, hma_lens=(30, 21, 13, 8)):
    """HMA-direction MTF AND RSI-direction MTF must agree."""
    base_close = df60["Close"].resample(sp.tf_freqs[0]).last().dropna()
    base_idx = base_close.index
    # HMA dirs
    hma_dirs = []
    for freq, n in zip(sp.tf_freqs, hma_lens):
        c = df60["Close"].resample(freq).last().dropna()
        h = hma(c, n)
        d = np.sign(h - h.shift(2)).fillna(0).astype(int)
        hma_dirs.append(d)
    rsi_dirs = []
    for freq, n in zip(sp.tf_freqs, sp.rsi_len):
        sig, _ = per_tf_indicator_dir(df60, freq, "rsi", n, sp.deadband)
        rsi_dirs.append(sig)
    align_h, coh_h = aggregate_dirs(hma_dirs, sp.weights, base_idx)
    align_r, coh_r = aggregate_dirs(rsi_dirs, sp.weights, base_idx)
    dir_h = np.sign(align_h).astype(int)
    dir_r = np.sign(align_r).astype(int)
    agree = (dir_h == dir_r) & (dir_h != 0)
    raw_pos = dir_h.where(agree & (coh_h >= sp.coherence_tau)
                          & (coh_r >= sp.coherence_tau), 0).astype(int)
    raw_pos = smooth_consec(raw_pos, sp.smooth_bars)
    return base_close, raw_pos


def strat_rsi_meanrev(df60, sp: StratParams, lo=30, hi=70):
    """Classic mean-reversion: long when daily RSI crosses up from <lo, exit at >hi."""
    c_d = df60["Close"].resample("1D").last().dropna()
    rd = rsi(c_d, 14)
    # cross up from oversold
    long_entry = (rd.shift(1) < lo) & (rd >= lo)
    long_exit = rd > hi
    short_entry = (rd.shift(1) > hi) & (rd <= hi)
    short_exit = rd < lo
    state = pd.Series(0, index=rd.index)
    s = 0
    for i, ts in enumerate(rd.index):
        if s == 0:
            if long_entry.iloc[i]:
                s = 1
            elif short_entry.iloc[i]:
                s = -1
        elif s == 1 and long_exit.iloc[i]:
            s = 0
        elif s == -1 and short_exit.iloc[i]:
            s = 0
        state.iloc[i] = s
    base_close = df60["Close"].resample(sp.tf_freqs[0]).last().dropna()
    return base_close, state.reindex(base_close.index, method="ffill").fillna(0).astype(int)


def run_one(ticker: str, sp: StratParams, mode="long_short"):
    df60 = fetch_60m(ticker)
    rows = []

    # 1. HMA-MTF baseline
    p = MTFParams(coherence_tau=sp.coherence_tau, smooth_bars=sp.smooth_bars)
    sig = build_hma_signal(df60, p)
    pos = sig["position"].astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    rows.append(("HMA-MTF", sig["base_close"], pos))

    for kind in ("rsi", "mfi", "stoch"):
        bc, raw = strat_indicator_mtf(df60, kind, sp)
        pos = raw.astype(float)
        if mode == "long_flat":
            pos = pos.clip(lower=0)
        rows.append((kind.upper() + "-MTF", bc, pos))

    bc, raw = strat_hma_x_rsi(df60, sp)
    pos = raw.astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    rows.append(("HMA×RSI-gate", bc, pos))

    bc, raw = strat_rsi_meanrev(df60, sp)
    pos = raw.astype(float)
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    rows.append(("RSI-meanrev", bc, pos))

    out = []
    for name, bc, pos in rows:
        bt = backtest_intraday(bc, pos)
        out.append((name, bt))
    return out


HEADER = (f"{'strategy':14s} {'mode':10s}  "
          f"{'CAGR':>8s} {'B&H':>8s} {'Δ':>8s}  "
          f"{'Shp':>5s} {'B&H':>5s} {'Δ':>5s}  "
          f"{'MaxDD':>7s}  {'TiM':>5s} {'Turn/y':>6s}")


def fmt(name, mode, bt):
    s, b = bt["strategy"], bt["buy_hold"]
    return (f"{name:14s} {mode:10s}  "
            f"{s['CAGR']:>8.2%} {b['CAGR']:>8.2%} {s['CAGR']-b['CAGR']:>+8.2%}  "
            f"{s['Sharpe']:>5.2f} {b['Sharpe']:>5.2f} {s['Sharpe']-b['Sharpe']:>+5.2f}  "
            f"{s['MaxDD']:>7.2%}  {bt['time_in_market']:>5.2%} {bt['turnover_per_year']:>6.1f}")


if __name__ == "__main__":
    import sys
    universe = sys.argv[1:] or [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META",
        "GOOGL", "AMD", "COIN", "NFLX", "AVGO", "CRM",
    ]
    sp = StratParams()

    # collect across universe
    agg = {}  # (strategy, mode) -> list of bt dicts
    print(f"TFs={sp.tf_freqs}  weights={sp.weights}  coh≥{sp.coherence_tau}  smooth={sp.smooth_bars}  deadband=±{sp.deadband}")
    for t in universe:
        print(f"\n=== {t} ===")
        print(HEADER)
        for mode in ("long_short", "long_flat"):
            try:
                rows = run_one(t, sp, mode=mode)
                for name, bt in rows:
                    print(fmt(name, mode, bt))
                    agg.setdefault((name, mode), []).append(bt)
            except Exception as e:
                print(f"{t} {mode}: {e}")

    # aggregate medians per (strategy, mode)
    print("\n\n=== AGGREGATE: median across the universe ===")
    print(f"{'strategy':14s} {'mode':10s}  "
          f"{'medΔcagr':>9s}  {'medΔshp':>8s}  {'medMaxDD':>9s}  "
          f"{'win%CAGR':>8s} {'win%Shp':>7s}  {'medTurn':>7s}")
    for (name, mode), bts in agg.items():
        d_cagr = np.median([bt["strategy"]["CAGR"] - bt["buy_hold"]["CAGR"] for bt in bts])
        d_shp = np.median([bt["strategy"]["Sharpe"] - bt["buy_hold"]["Sharpe"] for bt in bts])
        d_dd = np.median([bt["strategy"]["MaxDD"] for bt in bts])
        win_cagr = np.mean([bt["strategy"]["CAGR"] > bt["buy_hold"]["CAGR"] for bt in bts])
        win_shp = np.mean([bt["strategy"]["Sharpe"] > bt["buy_hold"]["Sharpe"] for bt in bts])
        med_turn = np.median([bt["turnover_per_year"] for bt in bts])
        print(f"{name:14s} {mode:10s}  "
              f"{d_cagr:>+9.2%}  {d_shp:>+8.2f}  {d_dd:>9.2%}  "
              f"{win_cagr:>8.0%} {win_shp:>7.0%}  {med_turn:>7.1f}")
