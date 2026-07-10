"""Leledc Exhaustion (InSilico mod) — exact Pine port + risk/reward scoring.

Pine logic (per bar):
  bindex += 1 when close > close[4]
  sindex += 1 when close < close[4]
  Bearish exhaustion (-1): bindex > bars AND close < open AND
      high >= highest(high, len)   -> reset bindex, resistance = high
  else Bullish exhaustion (+1): sindex > bars AND close > open AND
      low <= lowest(low, len)      -> reset sindex, support = low
  (bearish checked first, mirroring the Pine if/else)

Defaults match the script: swing length 40, exhaustion bar count 10.

Risk/reward layer (ours):
  With the most recent exhaustion-derived support (S) and resistance (R)
  and current close C, when S < C < R:
      rr = (R - C) / (C - S)        reward per unit of risk
      position = (C - S) / (R - S)  0 = at support, 1 = at resistance
  LELE score per TF (0-100):
      55% rr (clipped at 5:1 = full credit)
    + 30% proximity to support (1 - position)
    + 15% recency of the last BULLISH exhaustion (fresh support bar)
  Combined: 0.6 * weekly + 0.4 * monthly.
"""

import numpy as np
import pandas as pd


def drop_partial_bar(bars: pd.DataFrame, freq: str,
                     now: pd.Timestamp = None) -> pd.DataFrame:
    """Drop a final weekly/monthly bar that belongs to the still-open
    period. Exhaustion counters must not run on 2-day 'months'."""
    if bars is None or len(bars) == 0:
        return bars
    if not isinstance(bars.index, pd.DatetimeIndex):
        return bars
    now = now or pd.Timestamp.utcnow().tz_localize(None)
    last = bars.index[-1]
    if getattr(last, "tz", None) is not None:
        last = last.tz_localize(None)
    if freq == "W":
        monday = (now - pd.Timedelta(days=now.weekday())).normalize()
        if last >= monday:
            return bars.iloc[:-1]
    elif freq == "M":
        if (last.year, last.month) == (now.year, now.month):
            return bars.iloc[:-1]
    return bars


def lelec_signals(bars: pd.DataFrame, swing_len: int = 40,
                  bar_count: int = 10) -> dict:
    """Run the Leledc state machine over OHLC bars (weekly or monthly).

    Returns the live support/resistance, last signals, and recency."""
    if bars is None or len(bars) < swing_len + 5:
        return {}
    o = bars["Open"].values.astype(float)
    h = bars["High"].values.astype(float)
    l = bars["Low"].values.astype(float)
    c = bars["Close"].values.astype(float)
    n = len(c)

    bindex = 0
    sindex = 0
    resistance = np.nan
    support = np.nan
    last_bull = -1   # index of last bullish exhaustion (support set)
    last_bear = -1   # index of last bearish exhaustion (resistance set)

    for i in range(n):
        if i >= 4:
            if c[i] > c[i - 4]:
                bindex += 1
            if c[i] < c[i - 4]:
                sindex += 1
        win_lo = max(0, i - swing_len + 1)
        hh = h[win_lo:i + 1].max()
        ll = l[win_lo:i + 1].min()
        if bindex > bar_count and c[i] < o[i] and h[i] >= hh:
            bindex = 0
            resistance = h[i]
            last_bear = i
        elif sindex > bar_count and c[i] > o[i] and l[i] <= ll:
            sindex = 0
            support = l[i]
            last_bull = i

    close_now = c[-1]
    out = {
        "close": close_now,
        "support": support,
        "resistance": resistance,
        "bars_since_bull": (n - 1 - last_bull) if last_bull >= 0 else np.nan,
        "bars_since_bear": (n - 1 - last_bear) if last_bear >= 0 else np.nan,
        "n_bars": n,
    }

    # Risk/reward when price sits between live support and resistance
    if (np.isfinite(support) and np.isfinite(resistance)
            and support < close_now < resistance):
        risk = close_now - support
        reward = resistance - close_now
        out["rr"] = reward / risk if risk > 0 else np.nan
        out["position"] = (close_now - support) / (resistance - support)
    else:
        out["rr"] = np.nan
        # position outside the band still informative
        if np.isfinite(support) and np.isfinite(resistance) and resistance > support:
            out["position"] = (close_now - support) / (resistance - support)
        else:
            out["position"] = np.nan
    return out


def lele_score(sig: dict) -> float:
    """0-100 risk/reward quality for one timeframe."""
    if not sig or not np.isfinite(sig.get("rr", np.nan)):
        return np.nan
    rr_part = min(sig["rr"] / 5.0, 1.0)                    # 5:1 caps
    pos_part = 1.0 - min(max(sig["position"], 0.0), 1.0)   # near support best
    bsb = sig.get("bars_since_bull", np.nan)
    if np.isfinite(bsb):
        rec_part = float(np.exp(-bsb / 26.0))              # ~half-year decay (weekly)
    else:
        rec_part = 0.0
    return 100.0 * (0.55 * rr_part + 0.30 * pos_part + 0.15 * rec_part)


def evaluate_ticker(weekly: pd.DataFrame, monthly: pd.DataFrame,
                    completed_bars_only: bool = True) -> dict:
    """Weekly + monthly Leledc evaluation with the combined LELE score."""
    if completed_bars_only:
        weekly = drop_partial_bar(weekly, "W")
        monthly = drop_partial_bar(monthly, "M")
    w = lelec_signals(weekly)
    m = lelec_signals(monthly)
    sw = lele_score(w)
    sm = lele_score(m)
    if np.isfinite(sw) and np.isfinite(sm):
        combined = 0.6 * sw + 0.4 * sm
    elif np.isfinite(sw):
        combined = sw
    elif np.isfinite(sm):
        combined = sm
    else:
        combined = np.nan
    out = {"LELE": combined, "LELE_W": sw, "LELE_M": sm}
    for k, v in w.items():
        out[f"w_{k}"] = v
    for k, v in m.items():
        out[f"m_{k}"] = v
    return out


if __name__ == "__main__":
    # Smoke test on a handful of names
    import sys, warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf
    for t in (sys.argv[1:] or ["AAPL", "NVDA", "6962.T"]):
        raw_w = yf.download(t, period="10y", interval="1wk",
                            auto_adjust=True, progress=False)
        raw_m = yf.download(t, period="max", interval="1mo",
                            auto_adjust=True, progress=False)
        for raw in (raw_w, raw_m):
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
        r = evaluate_ticker(raw_w, raw_m)
        print(t, {k: (round(v, 2) if isinstance(v, float) else v)
                  for k, v in r.items() if not k.startswith(("w_", "m_"))},
              "| W rr:", round(r.get("w_rr", float("nan")), 2),
              "M rr:", round(r.get("m_rr", float("nan")), 2))
