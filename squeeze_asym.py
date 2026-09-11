"""Faithful Python port of the Pine Script v5 indicator
"Squeeze & Release + Volatility Asymmetry" (© malikmck / MPL-2.0).

Ported exactly, bar-for-bar, so the Lynch reawakening layer uses THIS
methodology precisely rather than an approximation. Pine primitives are
reproduced with matching semantics:

  ta.ema(src, len)  : alpha=2/(len+1), seeded with the first source value
                      then recursive (Pine's exact seeding).
  ta.tr(true)       : first bar = high-low; else
                      max(high-low, |high-close[-1]|, |low-close[-1]|).
  ta.roc(src, n)    : 100*(src-src[-n])/src[-n]   (percent).
  ta.rising(src, n) : strictly increasing over the last n bars.
  crossover/under   : sign change of (a-b) between the last two bars.

Squeeze & Release
  atr        = ema(tr, P);   emaAtr = ema(atr, 2P)
  volInd     = emaAtr - atr           (high when volatility is compressing)
  hlDiff     = ema(high-low, 2P)
  squeezeVal = [ema(,S) of] volInd/hlDiff*100
  squeezeMA  = ema(squeezeVal, E)
  state      = 'squeeze' if squeezeVal>squeezeMA else 'release'
  release event = crossunder(squeezeVal, squeezeMA)   (volatility expands
                  after compression -- the breakout / release)
  squeeze event = crossover(squeezeVal, squeezeMA)
  hyper_squeeze = squeezeVal>0 and rising(squeezeVal, H)

Volatility Asymmetry
  up   = max(high-close[-1],0);   dn = max(close[-1]-low,0)
  upA  = ema(up,P);   dnA = ema(dn,P)
  ratio= upA/(upA+dnA+1e-4)
  asym = [ema(,S) of] ratio*100          (oscillates ~50; >50 = upside vol)
  asymMA = ema(asym, P)
  upChg = roc(upA, L);  dnChg = roc(dnA, L)
  upperAsymmetry = upChg>thr and (|dnChg|<thr/2 or dnChg<0)   (bullish)
  lowerAsymmetry = dnChg>thr and (|upChg|<thr/2 or upChg<0)   (bearish)
"""

from __future__ import annotations


def ema(xs, length):
    """Pine ta.ema: seed with first value, alpha=2/(len+1)."""
    if not xs:
        return []
    a = 2.0 / (length + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def true_range(high, low, close):
    """Pine ta.tr(true): first bar = high-low."""
    out = []
    for i in range(len(close)):
        if i == 0:
            out.append(high[i] - low[i])
        else:
            pc = close[i - 1]
            out.append(max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc)))
    return out


def roc(xs, n):
    """Pine ta.roc in percent; None where undefined."""
    out = [None] * len(xs)
    for i in range(n, len(xs)):
        base = xs[i - n]
        out[i] = 100.0 * (xs[i] - base) / base if base else None
    return out


def rising(xs, n, i):
    """Strictly increasing over the last n bars ending at index i."""
    if i < n:
        return False
    return all(xs[j] > xs[j - 1] for j in range(i - n + 1, i + 1))


def compute(high, low, close, *, P=14, S=7, E=14, H=5,
            asym_L=5, asym_thr=5.0, smooth=True):
    """Return the final-bar state dict (and the raw series for testing)."""
    n = len(close)
    if n < max(P * 2 + 2, 3):
        return None

    # --- Squeeze & Release ---
    tr = true_range(high, low, close)
    atr = ema(tr, P)
    ema_atr = ema(atr, P * 2)
    vol_ind = [ema_atr[i] - atr[i] for i in range(n)]
    hl = ema([high[i] - low[i] for i in range(n)], P * 2)
    raw_sq = [(vol_ind[i] / hl[i] * 100) if hl[i] else 0.0 for i in range(n)]
    squeeze_val = ema(raw_sq, S) if smooth else raw_sq
    squeeze_ma = ema(squeeze_val, E)

    state = "squeeze" if squeeze_val[-1] > squeeze_ma[-1] else "release"
    # crossunder on the last bar = fresh release; else count bars since one
    def crossunder(a, b, i):
        return i >= 1 and a[i - 1] >= b[i - 1] and a[i] < b[i]
    def crossover(a, b, i):
        return i >= 1 and a[i - 1] <= b[i - 1] and a[i] > b[i]

    release_event = crossunder(squeeze_val, squeeze_ma, n - 1)
    squeeze_event = crossover(squeeze_val, squeeze_ma, n - 1)
    bars_since_release = None
    for k in range(n - 1, 0, -1):
        if crossunder(squeeze_val, squeeze_ma, k):
            bars_since_release = (n - 1) - k
            break
    # length of the squeeze run immediately preceding the last release
    prior_squeeze_len = 0
    if bars_since_release is not None:
        rel_idx = (n - 1) - bars_since_release
        j = rel_idx - 1
        while j >= 0 and squeeze_val[j] > squeeze_ma[j]:
            prior_squeeze_len += 1
            j -= 1
    hyper = squeeze_val[-1] > 0 and rising(squeeze_val, H, n - 1)

    # --- Volatility Asymmetry ---
    up = [0.0] + [max(high[i] - close[i - 1], 0) for i in range(1, n)]
    dn = [0.0] + [max(close[i - 1] - low[i], 0) for i in range(1, n)]
    up_a = ema(up, P)
    dn_a = ema(dn, P)
    ratio = [up_a[i] / (up_a[i] + dn_a[i] + 1e-4) for i in range(n)]
    asym = ema([r * 100 for r in ratio], S) if smooth else [r * 100 for r in ratio]
    asym_ma = ema(asym, P)
    up_chg = roc(up_a, asym_L)
    dn_chg = roc(dn_a, asym_L)
    uc, dc = up_chg[-1], dn_chg[-1]
    upper_asym = (uc is not None and uc > asym_thr
                  and (dc is None or abs(dc) < asym_thr / 2 or dc < 0))
    lower_asym = (dc is not None and dc > asym_thr
                  and (uc is None or abs(uc) < asym_thr / 2 or uc < 0))

    return {
        "squeeze_value": round(squeeze_val[-1], 3),
        "squeeze_ma": round(squeeze_ma[-1], 3),
        "state": state,
        "release_event": release_event,
        "squeeze_event": squeeze_event,
        "bars_since_release": bars_since_release,
        "prior_squeeze_len": prior_squeeze_len,
        "hyper_squeeze": hyper,
        "asymmetry": round(asym[-1], 2),
        "asymmetry_ma": round(asym_ma[-1], 2),
        "asymmetry_rising": len(asym) >= 2 and asym[-1] > asym[-2],
        "upward_change": round(uc, 2) if uc is not None else None,
        "downward_change": round(dc, 2) if dc is not None else None,
        "upper_asymmetry": upper_asym,
        "lower_asymmetry": lower_asym,
    }
