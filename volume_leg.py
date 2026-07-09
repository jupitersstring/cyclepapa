"""Dormeier weekly volume-breakout leg (V).

Three stages on WEEKLY bars:

  1. Pre-breakout supply dry-up
       DryUp  = median(V[t-4:t-1]) / median(V[t-20:t-5])   (lower better)
       UpDown = sum(V | up weeks) / sum(V | down weeks) over last 10 weeks
  2. Breakout week effort vs result
       RVOL   = V_t / median(V[t-20:t-1])
       CLV    = (2C - H - L) / (H - L)            (-1..+1, close location)
       RngExp = TR_t / median(TR[t-20:t-1])
       Churn rejection: RVOL >= 2 with RngExp < 1 and CLV < 0.2
  3. VPCI acceptance (Dormeier, weekly settings S=5, L=25)
       VPC  = VWMA_25(C) - SMA_25(C)
       VPR  = VWMA_5(C) / SMA_5(C)
       VM   = SMA_5(V) / SMA_25(V)
       VPCI = VPC * VPR * VM;  smoothed = 5-week VWMA of VPCI

Volume Breakout Score (0-100):
  25% breakout RVOL, 25% VPCI state, 20% dry-up, 20% effort-vs-result,
  10% up/down balance. Churn caps the total at 30.

Scanner buckets: Coiled / Triggered / Confirmed / Failed / None, using the
26-week resistance and weekly ATR(14).

All thresholds are the spec's starting values — the backtest harness
(volume_backtest.py, separate) is what will refit them.
"""

import numpy as np
import pandas as pd


# ───────────────────────────── building blocks

def _vwma(c: pd.Series, v: pd.Series, n: int) -> pd.Series:
    pv = (c * v).rolling(n).sum()
    vv = v.rolling(n).sum()
    return pv / vv.replace(0, np.nan)


def vpci(close: pd.Series, volume: pd.Series, s: int = 5, l: int = 25):
    """Dormeier's Volume Price Confirmation Indicator + its 5w VWMA smooth."""
    vpc = _vwma(close, volume, l) - close.rolling(l).mean()
    vpr = _vwma(close, volume, s) / close.rolling(s).mean()
    vm = volume.rolling(s).mean() / volume.rolling(l).mean()
    raw = vpc * vpr * vm
    smooth = _vwma(raw, volume, s)
    return raw, smooth


def _true_range(bars: pd.DataFrame) -> pd.Series:
    h, l, c = bars["High"], bars["Low"], bars["Close"]
    return pd.concat([h - l, (h - c.shift()).abs(),
                      (l - c.shift()).abs()], axis=1).max(axis=1)


def _interp(x, xp, fp):
    if not np.isfinite(x):
        return np.nan
    return float(np.interp(x, xp, fp))


# ───────────────────────────── the leg

def volume_breakout(bars: pd.DataFrame) -> dict:
    """Evaluate the Dormeier volume leg on weekly OHLCV bars.

    Returns V (0-100), all stage components, and the scanner bucket."""
    need = {"Open", "High", "Low", "Close", "Volume"}
    if bars is None or not need.issubset(bars.columns) or len(bars) < 30:
        return {}
    bars = bars.dropna(subset=["Close", "Volume"])
    if len(bars) < 30 or bars["Volume"].iloc[-20:].sum() <= 0:
        return {}
    o = bars["Open"]; h = bars["High"]; l = bars["Low"]
    c = bars["Close"]; v = bars["Volume"]

    # ---- Stage 1: supply dry-up
    recent = v.iloc[-4:]
    base = v.iloc[-20:-4]
    dryup = float(recent.median() / base.median()) if base.median() > 0 else np.nan

    rets = c.pct_change()
    win = slice(-10, None)
    up_v = float(v[win][rets[win] > 0].sum())
    dn_v = float(v[win][rets[win] < 0].sum())
    updown = up_v / dn_v if dn_v > 0 else (2.0 if up_v > 0 else np.nan)

    # ---- Stage 2: breakout week effort vs result
    v_now = float(v.iloc[-1])
    v_med = float(v.iloc[-21:-1].median())
    rvol = v_now / v_med if v_med > 0 else np.nan

    rng = float(h.iloc[-1] - l.iloc[-1])
    clv = float((2 * c.iloc[-1] - h.iloc[-1] - l.iloc[-1]) / rng) if rng > 0 else 0.0

    tr = _true_range(bars)
    tr_med = float(tr.iloc[-21:-1].median())
    rng_exp = float(tr.iloc[-1] / tr_med) if tr_med > 0 else np.nan

    churn = (np.isfinite(rvol) and rvol >= 2.0
             and np.isfinite(rng_exp) and rng_exp < 1.0 and clv < 0.2)

    # ---- Stage 3: VPCI
    vp_raw, vp_smooth = vpci(c, v)
    vp_now = float(vp_raw.iloc[-1]) if np.isfinite(vp_raw.iloc[-1]) else np.nan
    vp_sm = float(vp_smooth.iloc[-1]) if np.isfinite(vp_smooth.iloc[-1]) else np.nan
    vp_prev = float(vp_raw.iloc[-3]) if len(vp_raw) >= 3 and np.isfinite(vp_raw.iloc[-3]) else np.nan
    vp_rising = np.isfinite(vp_now) and np.isfinite(vp_prev) and vp_now > vp_prev
    vp_above = np.isfinite(vp_now) and np.isfinite(vp_sm) and vp_now > vp_sm

    # Price new high with VPCI falling materially = divergence penalty
    at_26w_high = float(c.iloc[-1]) >= float(h.iloc[-27:-1].max()) * 0.999 \
        if len(h) >= 27 else False
    vp_diverging = (at_26w_high and np.isfinite(vp_now) and np.isfinite(vp_prev)
                    and vp_now < vp_prev * 0.7 and vp_prev > 0)

    # ---- Component scores (spec starting values)
    s_rvol = _interp(rvol, [1.0, 1.25, 1.5, 2.0], [0.2, 0.5, 0.75, 1.0])

    if not np.isfinite(vp_now):
        s_vpci = np.nan
    elif vp_diverging:
        s_vpci = 0.2
    elif vp_now > 0 and vp_rising and vp_above:
        s_vpci = 1.0
    elif vp_now > 0 and vp_rising:
        s_vpci = 0.8
    elif vp_now > 0:
        s_vpci = 0.6
    elif vp_rising and vp_above:
        s_vpci = 0.55          # emerging confirmation from below zero
    elif vp_rising:
        s_vpci = 0.35
    else:
        s_vpci = 0.0

    s_dry = _interp(dryup, [0.6, 0.7, 0.9, 1.1, 1.3], [1.0, 0.9, 0.6, 0.3, 0.0])

    s_er = 0.5 * _interp(rng_exp, [0.8, 1.0, 1.3, 1.8], [0.0, 0.3, 0.7, 1.0]) \
         + 0.5 * _interp(clv, [-1.0, 0.2, 0.6, 0.8], [0.0, 0.3, 0.8, 1.0])
    if churn:
        s_er = 0.0

    s_bal = _interp(updown, [0.8, 1.0, 1.5, 2.0], [0.0, 0.4, 0.8, 1.0])

    parts = {'rvol': (0.25, s_rvol), 'vpci': (0.25, s_vpci),
             'dryup': (0.20, s_dry), 'effort': (0.20, s_er),
             'balance': (0.10, s_bal)}
    tot_w = sum(w for w, s in parts.values() if np.isfinite(s))
    if tot_w == 0:
        return {}
    V = 100.0 * sum(w * s for w, s in parts.values() if np.isfinite(s)) / tot_w
    if churn:
        V = min(V, 30.0)       # automatic rejection cap

    # ---- Scanner bucket
    bucket = "None"
    if len(h) >= 28:
        res26 = float(h.iloc[-27:-1].max())          # prior 26 completed weeks
        atr_w = float(tr.rolling(14).mean().iloc[-1])
        c_now = float(c.iloc[-1])
        c_prev = float(c.iloc[-2])
        res26_prev = float(h.iloc[-28:-2].max())
        above = c_now > res26
        crossed = above and c_prev <= res26_prev
        weeks_above = 0
        for i in range(2, min(6, len(c))):
            r_i = float(h.iloc[-(26 + i):-i].max())
            if float(c.iloc[-i]) > r_i:
                weeks_above += 1
            else:
                break
        if crossed and np.isfinite(rvol) and rvol >= 1.25 \
                and clv >= 0.2 and np.isfinite(rng_exp) and rng_exp >= 1.0:
            bucket = "Triggered"
        elif above and weeks_above >= 1:
            retest_ok = v_now < float(v.iloc[-1 - weeks_above]) if weeks_above < len(v) else True
            bucket = "Confirmed" if (s_vpci >= 0.55 or retest_ok) else "Holding"
        elif weeks_above >= 1 and not above:
            bucket = "Failed"
        elif (np.isfinite(atr_w) and (res26 - c_now) <= atr_w and c_now < res26
              and np.isfinite(dryup) and dryup < 0.9
              and np.isfinite(updown) and updown > 1.0):
            bucket = "Coiled"

    return {
        "V": float(V),
        "v_bucket": bucket,
        "v_rvol": rvol, "v_clv": clv, "v_range_exp": rng_exp,
        "v_dryup": dryup, "v_updown": updown,
        "v_vpci": vp_now, "v_vpci_smooth": vp_sm,
        "v_vpci_rising": bool(vp_rising), "v_churn": bool(churn),
        "v_s_rvol": s_rvol, "v_s_vpci": s_vpci, "v_s_dryup": s_dry,
        "v_s_effort": s_er, "v_s_balance": s_bal,
    }


if __name__ == "__main__":
    # Synthetic smoke tests
    rng_ = np.random.default_rng(3)
    n = 80

    def mk(closes, vols):
        closes = np.asarray(closes, dtype=float)
        vols = np.asarray(vols, dtype=float)
        o = closes * (1 + rng_.normal(0, .004, len(closes)))
        hi = np.maximum(o, closes) * 1.01
        lo = np.minimum(o, closes) * 0.99
        return pd.DataFrame({"Open": o, "High": hi, "Low": lo,
                             "Close": closes, "Volume": vols})

    # Case A: textbook — flat base with declining volume, then breakout on 1.8x vol closing high
    base = np.concatenate([np.linspace(90, 100, 40), np.full(39, 100) + rng_.normal(0, .5, 39)])
    vols = np.concatenate([np.full(40, 1e6), np.linspace(1e6, 5e5, 39)])
    closes = np.append(base, 106)          # breakout week
    vols = np.append(vols, 1.4e6)
    bars = mk(closes, vols)
    bars.loc[bars.index[-1], "High"] = 106.5
    bars.loc[bars.index[-1], "Low"] = 100.0
    r = volume_breakout(bars)
    print("A (textbook breakout):", {k: (round(vv, 2) if isinstance(vv, float) else vv)
                                     for k, vv in r.items() if not k.startswith("v_s")})

    # Case B: churn — huge volume, tiny range, weak close at resistance
    closes_b = np.append(base, 100.2)
    vols_b = np.append(vols[:-1], 3e6)
    bars_b = mk(closes_b, vols_b)
    bars_b.loc[bars_b.index[-1], "High"] = 100.6
    bars_b.loc[bars_b.index[-1], "Low"] = 99.9
    bars_b.loc[bars_b.index[-1], "Close"] = 100.0
    rb = volume_breakout(bars_b)
    print("B (churn):", {"V": round(rb["V"], 1), "churn": rb["v_churn"],
                          "bucket": rb["v_bucket"]})
    assert rb["v_churn"] and rb["V"] <= 30, "churn cap failed"
    print("churn rejection OK")
