"""Tail odds -- rank today's candidates by their empirically-estimated
probability of landing in the right tail.

tail_discriminators.py measured, on the historical event set, how much each
observable feature (catalyst type, sector, size, drawdown-from-high, range
position) lifts the probability of a >= +50% / 12m outcome. This module
applies those measured LIFTS to the current candidate set -- every name
carrying an archetype (mechanism_gates) or a corporate-action catalyst
(rerate_catalysts) -- to estimate each name's tail odds and rank them.

est_tail_prob = base_rate x PRODUCT(feature lift for the bin the name is in),
each lift clamped to [0.3, 3.0] and the product to a sane ceiling, over the
SCREENABLE features only. It is a naive-independence estimate on a modest
sample -- directional, not a calibrated probability -- but it does exactly
what was asked: tilt the shortlist toward the feature combinations that
actually produced tails.

Output: tail_odds.json keyed by ticker.
"""

from __future__ import annotations

import json
from pathlib import Path

import io_util
import tail_discriminators as td

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "tail_odds.json"

LIFT_CLAMP = (0.3, 3.0)
PROB_CEIL = 0.75
SHRINK = 0.45          # dampen naive-independence overcounting (features
                       # co-occur: small + beaten-down + right-sector cluster)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _load(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def main() -> int:
    disc = _load("tail_discriminators.json")
    if not disc:
        print("run tail_discriminators.py first"); io_util.write_json(OUT, {}); return 0
    base = disc.get("base_tail_rate", 0.15)
    feats = disc.get("features", {})
    screenable = disc.get("screenable", [])

    yf = _load("yfinance_quick.json")
    rer = _load("rerate_catalysts.json")
    mech = _load("mechanism_gates.json")
    geo = _load("payoff_geometry.json")

    def lift(feature, b):
        v = (feats.get(feature, {}) or {}).get(b)
        if not v or v.get("lift") is None:
            return 1.0
        return max(LIFT_CLAMP[0], min(LIFT_CLAMP[1], v["lift"]))

    candidates = set(rer) | set(mech)
    out = {}
    for tk in candidates:
        y = yf.get(tk) or {}
        price = _num(y.get("price")); lo = _num(y.get("fwk_low"))
        hi = _num(y.get("fwk_high")); mcap = _num(y.get("mcap"))
        sector = y.get("sector") or "Unknown"

        bins, lifts = {}, {}
        # catalyst: best-lift catalyst among the name's types.
        cats = (rer.get(tk) or {}).get("catalyst_types") or []
        if cats and "catalyst" in screenable:
            best = max(cats, key=lambda c: lift("catalyst", c))
            bins["catalyst"] = best; lifts["catalyst"] = lift("catalyst", best)
        if "sector" in screenable:
            bins["sector"] = sector; lifts["sector"] = lift("sector", sector)
        if "size" in screenable and mcap:
            sb = td.size_bin(mcap); bins["size"] = sb; lifts["size"] = lift("size", sb)
        if "drawdown_12m" in screenable and price and hi and hi > 0:
            dd = price / hi - 1.0
            b = td.dd_bin(dd); bins["drawdown_12m"] = b
            lifts["drawdown_12m"] = lift("drawdown_12m", b)
        if "range_pos" in screenable and price and lo is not None and hi and hi > lo:
            rp = (price - lo) / (hi - lo)
            b = td.pos_bin(rp); bins["range_pos"] = b
            lifts["range_pos"] = lift("range_pos", b)

        # combine in shrunk log-odds space so correlated lifts don't saturate.
        import math
        mult = 1.0
        for v in lifts.values():
            mult *= v
        base_odds = base / (1 - base) if base < 1 else 9.0
        log_odds = math.log(base_odds) + SHRINK * sum(math.log(v) for v in lifts.values())
        est = min(PROB_CEIL, 1.0 / (1.0 + math.exp(-log_odds)))

        archetypes = (mech.get(tk) or {}).get("archetypes") or []
        g = geo.get(tk) or {}
        out[tk] = {
            "ticker": tk,
            "est_tail_prob": round(est, 3),
            "tail_multiple": round(mult, 2),
            "base_rate": base,
            "feature_bins": bins,
            "feature_lifts": {k: round(v, 2) for k, v in lifts.items()},
            "catalyst_types": cats,
            "archetypes": archetypes,
            "geometry_ratio": g.get("ratio"),
            "upside_pct": g.get("upside_pct"),
            "rerate_score": (rer.get(tk) or {}).get("rerate_score"),
            "sector": sector,
            "mcap": mcap,
        }

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: -r["est_tail_prob"])
    print(f"base tail rate {base*100:.0f}%  |  {len(out)} candidates scored\n")
    print(f"{'TKR':<7}{'TAILp':>7}{'xMult':>7}{'RATIO':>7}  DRIVERS")
    for r in ranked[:30]:
        drivers = ", ".join(f"{k}={r['feature_bins'][k]}({r['feature_lifts'][k]})"
                            for k in r["feature_lifts"]
                            if r["feature_lifts"][k] > 1.05)
        rat = f"{r['geometry_ratio']:.1f}" if r.get("geometry_ratio") else "-"
        print(f"{r['ticker']:<7}{r['est_tail_prob']*100:>6.0f}%{r['tail_multiple']:>6.2f}x"
              f"{rat:>7}  {drivers[:58]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
