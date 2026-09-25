"""Winners forensics -- reverse-engineer the fingerprint of names that
actually re-rated, to inform the payoff-geometry weights.

The honest ideal is: take stocks that did 3x, look at their filings BEFORE
the move, and derive the pre-move fingerprint. That needs point-in-time
fundamentals + multi-year price history, which are not available here
(price_history.json is empty; the frames store is current-only). So this is
a BOUNDED version, and its limits are stated in the output:

  * WINNER (realized, 1-year proxy) = a name whose 52-week range is large
    (high/low >= RANGE_MIN) AND which currently sits in the top of that
    range (>= HOLD_MIN of the way from low to high) -- i.e. it moved up a
    lot and the move stuck, not just intraday noise.
  * For winners vs the full priced universe, compute the PRESENCE RATE of
    each feature/signal and the LIFT (winner-rate / base-rate). Features
    over-represented among winners (lift > 1) are the fingerprint.

CAVEAT (printed): the balance-sheet features are CURRENT, i.e. post-move,
so a winner may look less cheap now than at entry -- lift on valuation
features is therefore a conservative lower bound. Event-signal layers
(insider buying, MD&A intent, forced-selling, buyback, hidden-asset) are
closer to point-in-time and more trustworthy. The lifts are REPORTED to
inform GEOMETRY_WEIGHTS by hand; they are not auto-applied (a one-year
survivorship sample must not silently overwrite the engine).

Output: winners_forensics.json {summary:{feature_lifts,...}, winners:[...]}.
"""

from __future__ import annotations

import json
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "winners_forensics.json"

RANGE_MIN = 2.5      # 52wk high/low multiple to count as a big mover
HOLD_MIN = 0.70      # fraction of the low->high range the price still holds
RANGE_MAX = 50.0     # guard: above this is a penny-stock / data artifact
BIG_MULT = 4.0       # "big winner" threshold


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
    yf = _load("yfinance_quick.json")
    geo = _load("payoff_geometry.json")
    mda = _load("mda_scan.json")
    f4 = _load("form4_buys.json")
    net_bb = _load("net_buyback.json")
    nport = _load("nport_forced_selling.json")
    credit = _load("credit_agreement_mine.json")
    ftime = _load("form4_timing.json").get("scores", {})

    # sector median P/B for a cheapness feature.
    from statistics import median
    secpb: dict[str, list] = {}
    for tk, y in yf.items():
        pb = _num(y.get("p_b")); sec = y.get("sector") or "Unknown"
        if pb and pb > 0:
            secpb.setdefault(sec, []).append(pb)
    secpb = {s: median(v) for s, v in secpb.items() if v}

    def features(tk, y):
        """Boolean feature vector observable for a name."""
        pb = _num(y.get("p_b")); mcap = _num(y.get("mcap")) or 0
        sec = y.get("sector") or "Unknown"
        g = geo.get(tk) or {}
        smpb = secpb.get(sec)
        return {
            "hard_floor": g.get("floor_source") in ("net-cash", "NCAV"),
            "high_geom_ratio": (g.get("ratio") or 0) >= 5,
            "deep_value_pb": bool(smpb and pb and 0 < pb < 0.6 * smpb),
            "small_cap": 0 < mcap < 2e9,
            "micro_cap": 0 < mcap < 3e8,
            "mda_intent": tk in mda,
            "insider_buying": tk in f4,
            "net_buyback": (_num((net_bb.get(tk) or {}).get("score")) or 0) > 0,
            "forced_seller": (_num((nport.get(tk) or {}).get("score")) or 0) > 0
                             if isinstance(nport.get(tk), dict) else False,
            "hidden_asset": (_num((credit.get(tk) or {}).get("score")) or 0) > 0
                            if isinstance(credit.get(tk), dict) else False,
            "offhours_insider": (_num((ftime.get(tk) or {}).get("score")) or 0) > 0,
        }

    priced, winners = [], []
    for tk, y in yf.items():
        lo, hi, px = _num(y.get("fwk_low")), _num(y.get("fwk_high")), _num(y.get("price"))
        if not (lo and hi and px) or lo <= 0 or px < 1:
            continue
        rng = hi / lo
        if rng > RANGE_MAX:
            continue
        pos = (px - lo) / (hi - lo) if hi > lo else 0.0   # 0=low, 1=high
        rec = {"ticker": tk, "range_mult": round(rng, 2),
               "pos_in_range": round(pos, 2), "feat": features(tk, y),
               "sector": y.get("sector") or "Unknown"}
        priced.append(rec)
        if rng >= RANGE_MIN and pos >= HOLD_MIN:
            rec["big_winner"] = rng >= BIG_MULT
            winners.append(rec)

    n_base = len(priced)
    n_win = len(winners)
    feat_names = list(priced[0]["feat"].keys()) if priced else []

    def rate(pop, f):
        return (sum(1 for r in pop if r["feat"].get(f)) / len(pop)) if pop else 0.0

    lifts = {}
    for f in feat_names:
        base = rate(priced, f); win = rate(winners, f)
        lifts[f] = {"winner_rate": round(win, 3), "base_rate": round(base, 3),
                    "lift": round(win / base, 2) if base > 0 else None}

    # sector concentration of winners vs base
    from collections import Counter
    sec_win = Counter(r["sector"] for r in winners)
    sec_base = Counter(r["sector"] for r in priced)
    sector_lift = {}
    for s, n in sec_win.most_common():
        wr = n / n_win if n_win else 0
        br = sec_base[s] / n_base if n_base else 0
        sector_lift[s] = {"winner_share": round(wr, 3),
                          "lift": round(wr / br, 2) if br > 0 else None}

    summary = {
        "definition": f"52wk high/low >= {RANGE_MIN} AND price in top "
                      f"{int((1-HOLD_MIN)*100)}% of range",
        "n_universe_priced": n_base, "n_winners": n_win,
        "n_big_winners": sum(1 for r in winners if r.get("big_winner")),
        "feature_lifts": dict(sorted(lifts.items(),
                                     key=lambda kv: -(kv[1]["lift"] or 0))),
        "sector_lifts": sector_lift,
        "caveat": "Balance-sheet features are CURRENT (post-move); valuation "
                  "lifts are a conservative lower bound. Event-signal lifts "
                  "(insider/MD&A/forced-seller/buyback/hidden-asset) are "
                  "closer to point-in-time. One-year survivorship sample; "
                  "lifts inform GEOMETRY_WEIGHTS by hand, not auto-applied.",
    }
    io_util.write_json(OUT, {"summary": summary,
                             "winners": sorted(winners,
                                               key=lambda r: -r["range_mult"])})

    print(f"winners {n_win}/{n_base} priced "
          f"({summary['n_big_winners']} big, >= {BIG_MULT}x range)")
    print(f"\n{'FEATURE':<20}{'WIN%':>7}{'BASE%':>7}{'LIFT':>7}")
    for f, v in summary["feature_lifts"].items():
        lift = v["lift"]
        print(f"{f:<20}{v['winner_rate']*100:>6.0f}%{v['base_rate']*100:>6.0f}%"
              f"{(f'{lift:.2f}' if lift else '  n/a'):>7}")
    print(f"\nTop winner-concentrated sectors (lift):")
    for s, v in sorted(sector_lift.items(),
                       key=lambda kv: -(kv[1]['lift'] or 0))[:5]:
        print(f"  {s:<24}{v['winner_share']*100:>5.0f}%  lift {v['lift']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
