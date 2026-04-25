"""
Cycle-aligned multi-length, multi-TF, multi-indicator basket backtest.

For each ticker we compute direction signals at multiple lengths within each
of three TFs (daily / weekly / monthly), where lengths match observable
market cycles:

  Daily   (1D):  5,  10,  21,  63        # week, biweek, month, quarter
  Weekly  (1W):  4,  13,  26,  52        # month, quarter, half, year
  Monthly (1M):  3,  6,   12,  36        # quarter, half, year, 3-year

That's 12 "pins" per ticker per indicator.  Indicators tested:
  - HMA-slope                 (Hull MA direction)
  - RSI    cross-50           (momentum oscillator)
  - MFI    cross-50           (volume-weighted RSI)
  - Stoch  cross-50           (range-position)
  - PSAR                      (Wilder's parabolic, native ±1 trend)

Each pin votes ±1/0; pins are weighted within a TF (longer cycles get more
weight), and TFs are weighted across the cascade (monthly > weekly > daily).
A trade fires when the weighted coherence ≥ τ.  30-name basket, equal-weight
sleeves, 1 bp/turn cost.  Daily-bar execution; 15 years of yfinance daily
data so the result is statistically meaningful.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from hull_mitm import hma
from fmh_indicators import rsi, mfi, stoch_k, psar


# Multi-cap universe.  Names that lack history are auto-skipped.
UNIVERSE = {
    "MEGA": [   # >$200B
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "BRK-B",
        "LLY", "V", "JPM", "WMT", "MA",
    ],
    "LARGE": [  # $10-200B
        "TSLA", "AVGO", "NFLX", "CRM", "AMD", "COST", "JNJ", "UNH",
        "PG", "KO", "PEP", "BAC", "GS", "HD", "ORCL", "MCD", "NKE",
        "DIS", "XOM", "CVX",
    ],
    "MID": [    # $2-10B (some skew higher; intentional dispersion)
        "PINS", "ETSY", "ROKU", "SNAP", "U", "CHWY", "RBLX", "EXPE",
        "BBY", "ZM", "COIN", "PLTR", "MARA", "GME", "RIVN",
    ],
    "SMALL": [  # $300M-$2B
        "SOFI", "OPEN", "F", "NIO", "FUBO", "RIOT", "NKLA", "DKNG",
        "SPCE", "CLOV",
    ],
}
ALL_NAMES = sum(UNIVERSE.values(), [])


# Cycle palette: lengths ≈ observed market cycles
CYCLES = {
    "1D": (5, 10, 21, 63),     # week / biweek / month / quarter
    "1W": (4, 13, 26, 52),     # month / quarter / half / year
    "1ME": (3, 6, 12, 36),     # quarter / half / year / 3-year
}

# TF cascade weights (slower cycles drive more conviction)
TF_W = {"1D": 1.0, "1W": 3.0, "1ME": 5.0}


# ─── direction primitives ──────────────────────────────────────────
def dir_hma(close, n):
    h = hma(close, n)
    return np.sign(h - h.shift(2)).fillna(0).astype(int)


def dir_rsi(close, n, deadband=5):
    r = rsi(close, n)
    s = pd.Series(0, index=r.index, dtype=int)
    s[r >= 50 + deadband] = 1
    s[r <= 50 - deadband] = -1
    return s


def dir_mfi(high, low, close, vol, n, deadband=5):
    m = mfi(high, low, close, vol, n)
    s = pd.Series(0, index=m.index, dtype=int)
    s[m >= 50 + deadband] = 1
    s[m <= 50 - deadband] = -1
    return s


def dir_stoch(high, low, close, n, deadband=5):
    k = stoch_k(high, low, close, n)
    s = pd.Series(0, index=k.index, dtype=int)
    s[k >= 50 + deadband] = 1
    s[k <= 50 - deadband] = -1
    return s


def dir_psar(high, low):
    _, t = psar(high, low)
    return t.astype(int)


# ─── per-name pipeline ─────────────────────────────────────────────
def fetch_daily(ticker: str, period="max") -> pd.DataFrame:
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def cycle_signal(df_daily: pd.DataFrame, indicator: str,
                 cycles: dict = CYCLES, tf_w: dict = TF_W) -> pd.Series:
    """
    Compute weighted direction for a single ticker.  Returns a daily
    series of weighted alignment in [-1,+1].
    """
    base_idx = df_daily.index
    O, H, L, C, V = (df_daily["Open"], df_daily["High"], df_daily["Low"],
                     df_daily["Close"], df_daily["Volume"])

    pieces = []
    weights = []
    for tf, lens in cycles.items():
        # resample OHLCV
        o = O.resample(tf).first()
        h = H.resample(tf).max()
        l = L.resample(tf).min()
        c = C.resample(tf).last()
        v = V.resample(tf).sum()
        df_tf = pd.DataFrame(dict(O=o, H=h, L=l, C=c, V=v)).dropna()
        if len(df_tf) < max(lens) + 5:
            continue
        # length weights: sqrt(L) so longer cycles dominate within a TF
        len_w = np.array([np.sqrt(L_) for L_ in lens])
        len_w = len_w / len_w.sum()
        for L_, lw in zip(lens, len_w):
            if indicator == "hma":
                d = dir_hma(df_tf["C"], L_)
            elif indicator == "rsi":
                d = dir_rsi(df_tf["C"], L_)
            elif indicator == "mfi":
                d = dir_mfi(df_tf["H"], df_tf["L"], df_tf["C"], df_tf["V"], L_)
            elif indicator == "stoch":
                d = dir_stoch(df_tf["H"], df_tf["L"], df_tf["C"], L_)
            elif indicator == "psar":
                d = dir_psar(df_tf["H"], df_tf["L"])
            else:
                raise ValueError(indicator)
            d = d.reindex(base_idx, method="ffill").fillna(0).astype(int)
            pieces.append(d.astype(float) * (tf_w[tf] * lw))
            weights.append(tf_w[tf] * lw)

    if not pieces:
        return pd.Series(0.0, index=base_idx)
    Wsum = sum(weights)
    align = sum(pieces) / Wsum
    return align


def run_indicator_basket(universe: list[str], indicator: str,
                         coh_tau: float = 0.40, smooth: int = 3,
                         mode: str = "long_flat", cost_bps: float = 1.0,
                         period: str = "max"):
    """
    For each ticker: compute cycle-aligned signed-alignment;
    position = sign(align) * I(|align| >= coh_tau), smoothed N bars;
    Equal-weight aggregate across tickers.
    """
    sleeves = {}
    bh_sleeves = {}
    pos_sleeves = {}
    for t in universe:
        try:
            df = fetch_daily(t, period)
        except Exception as e:
            print(f"  skip {t}: {e}")
            continue
        if len(df) < 252:
            continue
        align = cycle_signal(df, indicator)
        coherence = align.abs()
        direction = np.sign(align).astype(int)
        raw = direction.where(coherence >= coh_tau, 0).astype(int)
        # smoothing: require N consecutive bars same nonzero sign
        if smooth > 1:
            out, last, run = [], 0, 0
            for v in raw.values:
                if v != 0 and v == last:
                    run += 1
                elif v != 0 and v != last:
                    run = 1
                    last = v
                else:
                    run, last = 0, 0
                out.append(last if run >= smooth else 0)
            raw = pd.Series(out, index=raw.index)
        if mode == "long_flat":
            raw = raw.clip(lower=0)
        pos = raw.astype(float)
        bh = df["Close"].pct_change().fillna(0)
        pos_lag = pos.shift(1).fillna(0)
        turn = pos_lag.diff().abs().fillna(pos_lag.abs())
        cost = turn * (cost_bps / 1e4)
        strat = pos_lag * bh - cost
        sleeves[t] = strat
        bh_sleeves[t] = bh
        pos_sleeves[t] = pos_lag

    # build aligned panel on the union daily index
    idx = sorted(set().union(*[s.index for s in sleeves.values()]))
    idx = pd.DatetimeIndex(idx)
    s_mat = pd.DataFrame({t: s.reindex(idx) for t, s in sleeves.items()})
    b_mat = pd.DataFrame({t: s.reindex(idx) for t, s in bh_sleeves.items()})
    p_mat = pd.DataFrame({t: s.reindex(idx) for t, s in pos_sleeves.items()})
    n_avail = s_mat.notna().sum(axis=1).replace(0, np.nan)
    strat_ret = (s_mat.fillna(0).sum(axis=1) / n_avail).fillna(0)
    bh_ret = (b_mat.fillna(0).sum(axis=1) / n_avail).fillna(0)
    tim = (p_mat.abs().fillna(0) > 0).mean().mean()
    return dict(strat_ret=strat_ret, bh_ret=bh_ret, tim=tim, n=len(sleeves),
                s_mat=s_mat, p_mat=p_mat)


def stats(ret: pd.Series, ann: int = 252):
    ret = ret.dropna()
    if len(ret) < 30 or ret.std() == 0:
        return dict(CAGR=0, Sharpe=0, Sortino=0, MaxDD=0, Vol=0)
    eq = (1 + ret).cumprod()
    cagr = eq.iloc[-1] ** (ann / len(ret)) - 1
    shp = ret.mean() / ret.std() * np.sqrt(ann)
    dn = ret[ret < 0].std()
    sortino = ret.mean() / dn * np.sqrt(ann) if dn > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    vol = ret.std() * np.sqrt(ann)
    return dict(CAGR=cagr, Sharpe=shp, Sortino=sortino, MaxDD=dd, Vol=vol)


HEADER = (f"{'indicator':10s} {'mode':10s} "
          f"{'CAGR':>7s} {'B&H':>7s} {'Δ':>7s}  "
          f"{'Shp':>5s} {'B&H':>5s} {'Δ':>5s}  "
          f"{'Sor':>5s}  "
          f"{'Vol':>6s} {'B&H':>6s}  "
          f"{'MaxDD':>7s} {'B&H':>7s}  "
          f"{'TiM':>5s}")


def fmt(name, mode, res):
    s = stats(res["strat_ret"])
    b = stats(res["bh_ret"])
    return (f"{name:10s} {mode:10s} "
            f"{s['CAGR']:>7.2%} {b['CAGR']:>7.2%} {s['CAGR']-b['CAGR']:>+7.2%}  "
            f"{s['Sharpe']:>5.2f} {b['Sharpe']:>5.2f} {s['Sharpe']-b['Sharpe']:>+5.2f}  "
            f"{s['Sortino']:>5.2f}  "
            f"{s['Vol']:>6.1%} {b['Vol']:>6.1%}  "
            f"{s['MaxDD']:>7.2%} {b['MaxDD']:>7.2%}  "
            f"{res['tim']:>5.2%}")


if __name__ == "__main__":
    print(f"Universe: {len(ALL_NAMES)} single names across "
          f"{len(UNIVERSE)} cap segments")
    for cap, names in UNIVERSE.items():
        print(f"  {cap:5s} ({len(names)}): {' '.join(names)}")
    print(f"Cycles per TF: {CYCLES}")
    print(f"TF weights:    {TF_W}")
    print(f"Daily history: max available per ticker")

    # 1.  Whole-universe basket
    for mode in ("long_flat", "long_short"):
        print(f"\n=== ALL CAPS basket — mode={mode}, coh≥0.40, smooth=3 ===")
        print(HEADER)
        for ind in ("hma", "rsi", "mfi", "stoch", "psar"):
            try:
                res = run_indicator_basket(ALL_NAMES, ind, mode=mode)
                print(fmt(ind.upper(), mode, res))
            except Exception as e:
                print(f"{ind}: {e}")

    # 2.  Per-cap basket comparison
    print(f"\n=== PER-CAP comparison (long_flat, coh≥0.40, smooth=3) ===")
    PCHDR = (f"{'cap':6s} {'ind':6s}  "
             f"{'CAGR':>7s} {'B&H':>7s} {'Δ':>7s}  "
             f"{'Shp':>5s} {'B&H':>5s} {'Δ':>5s}  "
             f"{'Sor':>5s}  {'Vol':>6s} {'B&H':>6s}  "
             f"{'MaxDD':>7s} {'B&H':>7s}  {'TiM':>5s}")
    print(PCHDR)
    for cap, names in UNIVERSE.items():
        for ind in ("rsi", "psar", "mfi", "stoch", "hma"):
            try:
                res = run_indicator_basket(names, ind, mode="long_flat")
                s = stats(res["strat_ret"])
                b = stats(res["bh_ret"])
                print(f"{cap:6s} {ind.upper():6s}  "
                      f"{s['CAGR']:>7.2%} {b['CAGR']:>7.2%} {s['CAGR']-b['CAGR']:>+7.2%}  "
                      f"{s['Sharpe']:>5.2f} {b['Sharpe']:>5.2f} {s['Sharpe']-b['Sharpe']:>+5.2f}  "
                      f"{s['Sortino']:>5.2f}  {s['Vol']:>6.1%} {b['Vol']:>6.1%}  "
                      f"{s['MaxDD']:>7.2%} {b['MaxDD']:>7.2%}  {res['tim']:>5.2%}")
            except Exception as e:
                print(f"{cap} {ind}: {e}")
