"""
Python port + backtest of the Hull MITM "lock-picking" multi-timeframe indicator.

Faithful translation of the Pine Script semantics:
  - HMA(close, L) per TF
  - trendDiff = HMA[t] - HMA[t-2]  -> direction sign
  - 6 cascade pairs (TF1->TF2 ... TF6->TF7) each with unlock/confirm-within-K logic
  - Cascade flag (s-suffix) requires the previous pair confirmed
  - Shear (weighted signed cascade) + Tension (pending unlocks)
  - Deadbolt (top TF agree) + follow-through bars -> MAKE/BREAK lockState
  - lockState drives long(+1) / short(-1) positions

We test on liquid daily tickers; the original script's 1m..240m ratios are
preserved as 1d, 3d, 5d, 15d, 30d, 60d, 240d so the cascade structure is
identical in spirit but uses many years of history.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from dataclasses import dataclass


# ───────────────────────────────────────────── helpers ──
def wma(x: pd.Series, n: int) -> pd.Series:
    n = max(int(n), 1)
    w = np.arange(1, n + 1, dtype=float)
    w /= w.sum()
    return x.rolling(n).apply(lambda v: np.dot(v, w), raw=True)


def hma(x: pd.Series, n: int) -> pd.Series:
    n = max(int(n), 2)
    half = max(int(n / 2), 1)
    sqn = max(int(round(np.sqrt(n))), 1)
    return wma(2 * wma(x, half) - wma(x, n), sqn)


def trend_dir(close: pd.Series, n: int) -> pd.Series:
    h = hma(close, n)
    diff = h - h.shift(2)
    return np.sign(diff).fillna(0).astype(int)


def resample_close(df_base: pd.DataFrame, freq: str) -> pd.Series:
    """Resample base-TF closes to a coarser TF, then forward-fill back."""
    coarse = df_base["Close"].resample(freq).last().dropna()
    return coarse


# ───────────────────────────────────────────── core MITM ──
@dataclass
class Params:
    K: int = 30           # confirm window in lower-TF bars
    weights: tuple = (1, 2, 3, 5, 8, 13)   # w12..w67 (Fibonacci-ish)
    deadbolt: bool = True
    follow_through: int = 2
    use_strength_gate: bool = True
    atr_len: int = 14
    min_strength: float = 0.10
    pick_thresh: float = 0.80
    break_thresh: float = 0.50
    sticky_bars: int = 1   # 1 = no stickiness


def compute_atr(high, low, close, n=14):
    pc = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - pc).abs(), (low - pc).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(n).mean()


def build_signals(df: pd.DataFrame, tf_freqs, hull_lens, params: Params):
    """
    df: daily OHLC indexed by date (the "TF1" base bar)
    tf_freqs: list of 7 pandas resample rules e.g. ['1D','3D','5D','15D','30D','60D','240D']
    hull_lens: list of 7 ints for HMA lengths per TF
    """
    base_idx = df.index
    close = df["Close"]
    high, low = df["High"], df["Low"]

    dirs = []
    sts = []  # |slope|/ATR per TF, evaluated on base index via ffill
    hmas = []
    for freq, L in zip(tf_freqs, hull_lens):
        # build coarse close, compute HMA & slope on coarse, then ffill to base
        coarse_close = close.resample(freq).last().dropna()
        coarse_high = high.resample(freq).max().dropna()
        coarse_low = low.resample(freq).min().dropna()
        h = hma(coarse_close, L)
        d = np.sign(h - h.shift(2)).fillna(0).astype(int)
        atr = compute_atr(coarse_high, coarse_low, coarse_close, params.atr_len)
        st = (h - h.shift(2)).abs() / atr.replace(0, np.nan)
        st = st.fillna(0)
        dirs.append(d.reindex(base_idx, method="ffill").fillna(0).astype(int))
        sts.append(st.reindex(base_idx, method="ffill").fillna(0))
        hmas.append(h.reindex(base_idx, method="ffill"))

    d1, d2, d3, d4, d5, d6, d7 = dirs
    st1, st2, st3, st4, st5, st6, st7 = sts

    if params.use_strength_gate:
        gate = lambda d, s: d.where(s >= params.min_strength, 0).astype(int)
    else:
        gate = lambda d, s: d
    g1, g2, g3, g4, g5, g6, g7 = (gate(d, s) for d, s in zip(dirs, sts))

    # unlock = sign change from previous bar (and not zero)
    def unlock(d):
        return ((d != 0) & (d != d.shift(1).fillna(0))).astype(bool)

    un = [unlock(d) for d in [d1, d2, d3, d4, d5, d6, d7]]
    # We use un[0]..un[5] as un12..un67 (lower-TF triggers the pair)

    n = len(base_idx)
    # cascade-flavor state per pair (we only need the cascade flavor for trading)
    K = params.K

    # For each of 6 pairs: track u (unlock bar idx), s (sign at unlock), c (confirmed)
    pairs = 6
    u = [-1] * pairs       # bar index of last unlock; -1 = none
    s = [0] * pairs        # latched sign
    c = [False] * pairs    # confirmed flag

    confirmed = np.zeros((n, pairs), dtype=bool)
    sign_at = np.zeros((n, pairs), dtype=int)
    pending = np.zeros((n, pairs), dtype=bool)  # "Tension" pin

    lower_dirs = [d1, d2, d3, d4, d5, d6]
    upper_dirs = [d2, d3, d4, d5, d6, d7]
    unlocks = un[:6]

    # use array views for speed
    LD = np.array([d.values for d in lower_dirs])
    UD = np.array([d.values for d in upper_dirs])
    UN = np.array([u_.values for u_ in unlocks])

    for i in range(n):
        # cascade gate g_{p} = c[p-1] from previous bar (after-update) — we use current
        # Pair 0 (1->2) has no gate.
        gate_flags = [True]
        for p in range(1, pairs):
            gate_flags.append(c[p - 1])

        for p in range(pairs):
            if UN[p, i]:
                if gate_flags[p]:
                    u[p] = i
                    s[p] = int(LD[p, i])
                    c[p] = False
            if u[p] >= 0 and not c[p]:
                if (i - u[p]) <= K and UD[p, i] == s[p] and s[p] != 0:
                    c[p] = True
                elif (i - u[p]) > K:
                    u[p] = -1
                    s[p] = 0

            confirmed[i, p] = c[p]
            sign_at[i, p] = s[p]
            pending[i, p] = (u[p] >= 0) and (not c[p])

    confirmed_df = pd.DataFrame(confirmed, index=base_idx,
                                columns=[f"c{p+1}{p+2}" for p in range(pairs)])
    sign_df = pd.DataFrame(sign_at, index=base_idx,
                           columns=[f"s{p+1}{p+2}" for p in range(pairs)])
    pending_df = pd.DataFrame(pending, index=base_idx,
                              columns=[f"t{p+1}{p+2}" for p in range(pairs)])

    # Shear / Tension
    W = np.array(params.weights, dtype=float)
    Wsum = W.sum()
    shear_raw = (confirmed * sign_at * W).sum(axis=1)
    shear = shear_raw / Wsum if Wsum > 0 else shear_raw
    tension_raw = (pending * W).sum(axis=1)
    tension = tension_raw / Wsum if Wsum > 0 else tension_raw

    shear_s = pd.Series(shear, index=base_idx)
    tension_s = pd.Series(tension, index=base_idx)

    # Deadbolt + follow-through MAKE/BREAK -> lockState path
    pick_up = (shear_s >= params.pick_thresh)
    pick_dn = (shear_s <= -params.pick_thresh)
    if params.deadbolt:
        pick_up = pick_up & (g7 == 1)
        pick_dn = pick_dn & (g7 == -1)

    def streak(cond: pd.Series) -> pd.Series:
        # consecutive True count
        out = np.zeros(len(cond), dtype=int)
        run = 0
        cv = cond.values
        for i, x in enumerate(cv):
            run = run + 1 if x else 0
            out[i] = run
        return pd.Series(out, index=cond.index)

    ft = params.follow_through
    pick_up_ft = streak(pick_up) >= ft
    pick_dn_ft = streak(pick_dn) >= ft

    brk_up = (shear_s >= params.break_thresh) & (g7 == 1 if params.deadbolt else True)
    brk_dn = (shear_s <= -params.break_thresh) & (g7 == -1 if params.deadbolt else True)
    brk_up_ft = streak(brk_up) >= ft
    brk_dn_ft = streak(brk_dn) >= ft

    lock = np.zeros(n, dtype=int)
    state = 0
    for i in range(n):
        if state == 0:
            if pick_up_ft.iat[i]:
                state = 1
            elif pick_dn_ft.iat[i]:
                state = -1
        elif state == 1 and brk_dn_ft.iat[i]:
            state = -1
        elif state == -1 and brk_up_ft.iat[i]:
            state = 1
        lock[i] = state

    return dict(
        shear=shear_s,
        tension=tension_s,
        lock=pd.Series(lock, index=base_idx),
        confirmed=confirmed_df,
        sign=sign_df,
        pending=pending_df,
        d7=g7,
    )


# ───────────────────────────────────────────── backtest ──
def backtest(df: pd.DataFrame, lock: pd.Series, mode="long_short", cost_bps=1.0):
    """
    Trade next-bar open on signal change. Return equity curves + stats.
    mode: 'long_short' or 'long_flat'
    cost_bps: round-trip cost in basis points per change.
    """
    px = df["Close"].astype(float)
    ret = px.pct_change().fillna(0)

    pos = lock.copy()
    if mode == "long_flat":
        pos = pos.clip(lower=0)
    pos_lag = pos.shift(1).fillna(0)  # apply position from next bar

    turn = (pos_lag.diff().abs().fillna(pos_lag.abs()))  # |Δposition|
    cost = turn * (cost_bps / 1e4)

    strat_ret = pos_lag * ret - cost
    bh_ret = ret

    eq_s = (1 + strat_ret).cumprod()
    eq_b = (1 + bh_ret).cumprod()

    def stats(r: pd.Series, eq: pd.Series, ann=252):
        r = r.dropna()
        if r.std() == 0 or len(r) < 5:
            return dict(CAGR=0, Sharpe=0, MaxDD=0, Hit=0, Turnover=0)
        cagr = eq.iloc[-1] ** (ann / len(r)) - 1
        sharpe = r.mean() / r.std() * np.sqrt(ann)
        dd = (eq / eq.cummax() - 1).min()
        hit = (r > 0).mean()
        return dict(CAGR=cagr, Sharpe=sharpe, MaxDD=dd, Hit=hit)

    out = {
        "strategy": stats(strat_ret, eq_s),
        "buy_hold": stats(bh_ret, eq_b),
    }
    out["strategy"]["Turnover"] = turn.sum() / (len(turn) / 252)
    out["alpha_CAGR"] = out["strategy"]["CAGR"] - out["buy_hold"]["CAGR"]
    out["eq_strategy"] = eq_s
    out["eq_buyhold"] = eq_b
    out["positions"] = pos_lag
    return out


def run_one(ticker: str, period="15y", params: Params = None,
            tf_days=(1, 3, 5, 15, 30, 60, 240),
            hull_len=55, mode="long_short", cost_bps=1.0):
    params = params or Params()
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    tf_freqs = [f"{d}D" for d in tf_days]
    hull_lens = [hull_len] * 7
    sig = build_signals(df, tf_freqs, hull_lens, params)
    bt = backtest(df, sig["lock"], mode=mode, cost_bps=cost_bps)
    bt["lock"] = sig["lock"]
    bt["shear"] = sig["shear"]
    bt["tension"] = sig["tension"]
    bt["df"] = df
    return bt


def fmt(d):
    return ", ".join(
        f"{k}={v:.2%}" if k in ("CAGR", "MaxDD", "Hit", "alpha_CAGR")
        else f"{k}={v:.2f}"
        for k, v in d.items()
    )


if __name__ == "__main__":
    import sys
    tickers = sys.argv[1:] or ["SPY", "QQQ", "IWM", "GLD", "TLT", "BTC-USD"]
    print(f"{'ticker':8s}  {'years':>5s}  {'mode':10s}  "
          f"{'CAGR':>7s}  {'B&H':>7s}  {'Alpha':>7s}  "
          f"{'Sharpe':>6s}  {'MaxDD':>7s}  {'Hit':>5s}  {'Turn/y':>7s}")
    for t in tickers:
        for mode in ("long_short", "long_flat"):
            try:
                r = run_one(t, period="15y", mode=mode)
                s, b = r["strategy"], r["buy_hold"]
                yrs = len(r["df"]) / 252
                print(f"{t:8s}  {yrs:5.1f}  {mode:10s}  "
                      f"{s['CAGR']:>7.2%}  {b['CAGR']:>7.2%}  {r['alpha_CAGR']:>7.2%}  "
                      f"{s['Sharpe']:>6.2f}  {s['MaxDD']:>7.2%}  {s['Hit']:>5.2%}  "
                      f"{s['Turnover']:>7.2f}")
            except Exception as e:
                print(f"{t}: error: {e}")
