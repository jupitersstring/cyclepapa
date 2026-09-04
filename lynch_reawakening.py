"""Lynch "reawakening" archetype -- years of progress rewarded in one.

Peter Lynch's Fannie Mae chapter: a company transforms fundamentally over
years (1982-88) while the stock goes nowhere, then in one year (1989) the
market re-rates it and "several years' worth of patience is rewarded in
one" ($16 -> $42). The setup is a CONJUNCTION of two things this framework
already half-sees:

  1. a FUNDAMENTAL ADVANCE (we detect via the assembly / frames inflection
     / emergence / distressed-progress legs -- "the business advanced
     significantly"); and
  2. a PRICE REAWAKENING now -- long dormancy giving way to acceleration.

This module supplies (2): the momentum / volatility-asymmetry / squeeze
signals, computed from a price-history store (price_history.json, keyed by
ticker with monthly + weekly close arrays). It scores:

  - ROC (rate of change) at monthly / quarterly / weekly horizons, plus
    the LONG-TERM 3.5y and 10y ROC, and ROC-of-ROC (acceleration);
  - RSI proximity to 50 turning UP -- momentum crossing the mid-line from
    below is the "reawakening" inflection (positive ROC near the 50 line);
  - a TTM squeeze: Bollinger Bands inside Keltner Channels = coiled; the
    RELEASE after a long squeeze is the tactical trigger, and we report
    how fresh the release is (state of release).

The archetype score rewards: long-term dormancy (flat 3.5y/10y) + recent
positive ROC + positive ROC-of-ROC + a fresh squeeze release + RSI
crossing up through 50. Degrades to 0 with no price history.

Compute-only; the puller (price_history_pull.py) fills the store.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "price_history.json"
OUT = ROOT / "lynch_reawakening.json"


def roc(series, n):
    """Rate of change over n periods (fraction). None if insufficient."""
    if not series or len(series) <= n or series[-n - 1] in (0, None):
        return None
    return series[-1] / series[-n - 1] - 1


def rsi(series, period=14):
    """Wilder RSI on the series' period-over-period changes."""
    if len(series) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    deltas = [series[i] - series[i - 1] for i in range(1, len(series))]
    seed = deltas[:period]
    up = sum(d for d in seed if d > 0) / period
    down = -sum(d for d in seed if d < 0) / period
    for d in deltas[period:]:
        up = (up * (period - 1) + (d if d > 0 else 0)) / period
        down = (down * (period - 1) + (-d if d < 0 else 0)) / period
    if down == 0:
        return 100.0
    rs = up / down
    return 100 - 100 / (1 + rs)


def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _std(xs, n):
    if len(xs) < n:
        return None
    m = _sma(xs, n)
    return math.sqrt(sum((x - m) ** 2 for x in xs[-n:]) / n)


def squeeze_state(close, high=None, low=None, n=20, bb_k=2.0, kc_k=1.5):
    """TTM-style squeeze on the close series. Returns (in_squeeze_now,
    periods_in_prior_squeeze, periods_since_release). Bollinger inside
    Keltner = coiled. Without true H/L, ATR is approximated from
    close-to-close abs moves (a conservative proxy)."""
    if len(close) < n + 2:
        return None, 0, None
    # per-period squeeze flag over the tail
    flags = []
    rng = range(n, len(close) + 1)
    # approximate true range with |close_i - close_{i-1}|
    tr = [abs(close[i] - close[i - 1]) for i in range(1, len(close))]
    for end in rng:
        c = close[:end]
        m = _sma(c, n); sd = _std(c, n)
        if m is None or sd is None:
            flags.append(False); continue
        atr = _sma(tr[:end - 1], n) if len(tr) >= n else None
        if atr is None:
            flags.append(False); continue
        bb_up, bb_dn = m + bb_k * sd, m - bb_k * sd
        kc_up, kc_dn = m + kc_k * atr, m - kc_k * atr
        flags.append(bb_up < kc_up and bb_dn > kc_dn)   # BB inside KC
    in_now = flags[-1]
    # count consecutive prior-squeeze periods before the most recent release
    since_release = None
    prior = 0
    if not in_now:
        # walk back to find last release, count squeeze run before it
        i = len(flags) - 1
        while i >= 0 and not flags[i]:
            i -= 1
        if i >= 0:
            since_release = (len(flags) - 1) - i
            j = i
            while j >= 0 and flags[j]:
                prior += 1; j -= 1
    else:
        j = len(flags) - 1
        while j >= 0 and flags[j]:
            prior += 1; j -= 1
    return in_now, prior, since_release


def score_ticker(rec: dict) -> dict:
    """rec = {'monthly': [...closes...], 'weekly': [...closes...]}."""
    m = [x for x in (rec.get("monthly") or []) if x]
    w = [x for x in (rec.get("weekly") or []) if x]
    out = {"n_monthly": len(m), "n_weekly": len(w), "score": 0.0, "flags": []}
    if len(m) < 24:
        return out

    roc_1m, roc_3m = roc(m, 1), roc(m, 3)
    roc_12m = roc(m, 12)
    roc_3_5y, roc_10y = roc(m, 42), roc(m, 120)
    # "dormant window" = the 30 months BEFORE the last 12 (the years of no
    # reward), measured independently of the recent surge.
    roc_before = (m[-13] / m[-43] - 1) if len(m) > 43 and m[-43] else None
    roc_prev_3m = roc(m[:-1], 3)                       # 3m ROC one period ago
    roc_of_roc = (roc_3m - roc_prev_3m) if (roc_3m is not None
                                            and roc_prev_3m is not None) else None
    rsi_m = rsi(m, 14)
    rsi_m_prev = rsi(m[:-1], 14)
    roc_1w = roc(w, 1) if w else None
    rsi_w = rsi(w, 14) if w else None
    in_sq, prior_sq, since_rel = squeeze_state(m)

    out.update({"roc_1m": roc_1m, "roc_3m": roc_3m, "roc_12m": roc_12m,
                "roc_before_30m": roc_before,
                "roc_3_5y": roc_3_5y, "roc_10y": roc_10y,
                "roc_of_roc_3m": roc_of_roc,
                "rsi_monthly": rsi_m, "rsi_weekly": rsi_w,
                "squeeze_now": in_sq, "prior_squeeze_len": prior_sq,
                "periods_since_release": since_rel})

    s = 0.0; fl = []
    # 1. DORMANCY: flat for the ~2.5 years before the recent year (Lynch's
    #    "years of no reward"), measured on the pre-surge window.
    dormant = roc_before is not None and -0.25 <= roc_before <= 0.35
    if dormant:
        s += 8; fl.append(f"dormant pre-window ({roc_before*100:+.0f}% / 30mo)")
    # 2. REAWAKENING: a big recent year AND most of the multi-year move is
    #    concentrated in it -- "several years' worth rewarded in one".
    if roc_12m is not None and roc_12m > 0.25:
        s += 8; fl.append(f"12m ROC +{roc_12m*100:.0f}%")
        if dormant and roc_12m > abs(roc_before or 0) + 0.20:
            s += 12; fl.append("years-of-progress concentrated in one year")
    # 3. ACCELERATION (ROC of ROC > 0)
    if roc_of_roc is not None and roc_of_roc > 0:
        s += 8; fl.append("ROC accelerating")
    # 4. RSI crossing up through 50 (the momentum reawakening) -- reward the
    #    cross / early-confirmed band, skip the exhausted >85 zone.
    if rsi_m is not None and rsi_m_prev is not None and rsi_m_prev < 50 <= rsi_m:
        s += 12; fl.append(f"monthly RSI crossed 50 up ({rsi_m:.0f})")
    elif rsi_m is not None and 50 <= rsi_m <= 78 and (roc_1m or 0) > 0:
        s += 6; fl.append(f"monthly RSI {rsi_m:.0f} (confirmed, not exhausted)")
    elif rsi_m is not None and rsi_m > 88:
        s -= 4; fl.append(f"RSI {rsi_m:.0f} (extended -- late)")
    # 5. Squeeze release after a long coil (tactical trigger)
    if in_sq is False and since_rel is not None and since_rel <= 3 \
            and prior_sq >= 4:
        s += 14; fl.append(f"fresh squeeze release ({prior_sq}mo coil, "
                           f"{since_rel}mo ago)")
    elif in_sq:
        s += 3; fl.append(f"coiling ({prior_sq}mo squeeze -- watch)")
    # 6. Weekly tactical confirmation
    if rsi_w is not None and 45 <= rsi_w <= 68 and (roc_1w or 0) > 0:
        s += 4; fl.append("weekly timing aligned")

    out["score"] = round(max(0.0, s), 1)
    out["flags"] = fl
    return out


def main() -> int:
    if not SRC.exists():
        print(f"no {SRC.name} yet -- run price_history_pull.py; writing empty")
        io_util.write_json(OUT, {})
        return 0
    data = json.loads(SRC.read_text())
    out = {}
    for tk, rec in data.items():
        if not isinstance(rec, dict):
            continue
        r = score_ticker(rec)
        if r["score"] > 0:
            out[tk] = r
    io_util.write_json(OUT, out)
    print(f"wrote {OUT} ({len(out)} reawakening setups of {len(data)} priced)")
    for tk, v in sorted(out.items(), key=lambda x: -x[1]["score"])[:20]:
        print(f"  {tk:<7}{v['score']:>6.1f}  {'; '.join(v['flags'])[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
