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
import squeeze_asym

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "price_history.json"
OUT = ROOT / "lynch_reawakening.json"


def _ohlc(rec, tf):
    """Pull (high, low, close) arrays for a timeframe from a record.
    New schema stores {tf}_high/_low/_close; falls back to a close-only
    array ({tf}) with H=L=C so ROC still works if OHLC is absent."""
    h = rec.get(f"{tf}_high"); l = rec.get(f"{tf}_low"); c = rec.get(f"{tf}_close")
    if c:
        return (h or c), (l or c), c
    c = rec.get(tf)                        # old close-only schema
    if c:
        return c, c, c
    return None, None, None


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



def score_ticker(rec: dict) -> dict:
    """Score the Lynch reawakening using the precise Squeeze & Release +
    Volatility Asymmetry methodology (squeeze_asym) on monthly / quarterly
    / weekly bars, combined with the long-term ROC dormancy-and-
    concentration test that defines "years of progress rewarded in one"."""
    mh, ml, mc = _ohlc(rec, "monthly")
    qh, ql, qc = _ohlc(rec, "quarterly")
    wh, wl, wc = _ohlc(rec, "weekly")
    out = {"n_monthly": len(mc or []), "score": 0.0, "flags": []}
    if not mc or len(mc) < 30:
        return out

    # ---- long-term ROC context (the "years rewarded in a year" core) ----
    roc_1m, roc_3m, roc_12m = roc(mc, 1), roc(mc, 3), roc(mc, 12)
    roc_3_5y, roc_10y = roc(mc, 42), roc(mc, 120)
    roc_before = (mc[-13] / mc[-43] - 1) if len(mc) > 43 and mc[-43] else None
    roc_prev_3m = roc(mc[:-1], 3)
    roc_of_roc = (roc_3m - roc_prev_3m) if (roc_3m is not None
                                            and roc_prev_3m is not None) else None

    # ---- precise squeeze & asymmetry on each timeframe ----
    m_sig = squeeze_asym.compute(mh, ml, mc)
    q_sig = squeeze_asym.compute(qh, ql, qc) if qc and len(qc) >= 30 else None
    w_sig = squeeze_asym.compute(wh, wl, wc) if wc and len(wc) >= 30 else None

    out.update({"roc_3m": roc_3m, "roc_12m": roc_12m, "roc_before_30m": roc_before,
                "roc_3_5y": roc_3_5y, "roc_10y": roc_10y,
                "roc_of_roc_3m": roc_of_roc,
                "monthly": m_sig, "quarterly": q_sig, "weekly": w_sig})

    s = 0.0; fl = []
    # 1. DORMANCY (flat 30mo pre-surge) + CONCENTRATION (recent year did
    #    most of the multi-year move) -- the Fannie-Mae signature.
    dormant = roc_before is not None and -0.25 <= roc_before <= 0.35
    if dormant:
        s += 8; fl.append(f"dormant pre-window ({roc_before*100:+.0f}%/30mo)")
    if roc_12m is not None and roc_12m > 0.25:
        s += 6; fl.append(f"12m ROC +{roc_12m*100:.0f}%")
        if dormant and roc_12m > abs(roc_before or 0) + 0.20:
            s += 12; fl.append("years-of-progress concentrated in one year")
    if roc_of_roc is not None and roc_of_roc > 0:
        s += 6; fl.append("ROC accelerating")

    # 2. SQUEEZE RELEASE after a long squeeze (monthly, precise) -- recent
    #    release + prior coil = the long-term release the spec asks for.
    if m_sig:
        if m_sig["release_event"] or (m_sig["state"] == "release"
                and (m_sig["bars_since_release"] or 99) <= 3
                and m_sig["prior_squeeze_len"] >= 4):
            s += 14
            fl.append(f"squeeze RELEASE ({m_sig['prior_squeeze_len']}mo coil, "
                      f"{m_sig['bars_since_release']}mo into release)")
        elif m_sig["state"] == "squeeze" and m_sig["hyper_squeeze"]:
            s += 4; fl.append("hyper-squeeze coiling (watch for release)")
        elif m_sig["state"] == "squeeze":
            s += 2; fl.append("in squeeze")

    # 3. VOLATILITY ASYMMETRY -- positive ROC near/above 50 (upside vol
    #    dominating) on monthly and/or quarterly.
    def asym_pts(sig, label):
        p = 0.0; f = []
        if not sig:
            return p, f
        if sig["upper_asymmetry"]:
            p += 10; f.append(f"{label} upper vol-asymmetry (upside accel)")
        elif sig["asymmetry"] >= 50 and sig["asymmetry_rising"]:
            p += 5; f.append(f"{label} asym {sig['asymmetry']:.0f} rising >50")
        if sig["lower_asymmetry"]:
            p -= 6; f.append(f"{label} LOWER vol-asymmetry (downside accel)")
        return p, f
    for sig, lbl in ((m_sig, "monthly"), (q_sig, "quarterly")):
        p, f = asym_pts(sig, lbl); s += p; fl += f

    # 4. WEEKLY tactical timing -- fresh weekly release or upside asymmetry.
    if w_sig and (w_sig["release_event"] or w_sig["upper_asymmetry"]):
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
