"""Bonaime-Ryngaert insider-direction overlay on buyback layer.

Bonaime-Ryngaert (JCF 22, SSRN 1361738): buybacks with concurrent net
insider BUYING preserve abnormal returns 3 years; buybacks with
concurrent net insider SELLING see abnormal returns disappear within
1 year. The direction of insider flow during the buyback window is
a multiplicative filter on buyback alpha.

This module joins:
  buyback_verify.json  -> EXECUTING / SHRINKING / NO_AUTH status
  form4_buys.json       -> insider P-buy dollars
  form144_scan.json     -> insider proposed sales

For each ticker with a verified buyback, the net insider direction
is classified as BUY (F4 > F144), SELL (F4 < F144), or NEUTRAL.
Output is an additive multiplier on the existing buyback score:
  BUY     -> 1.5x existing
  NEUTRAL -> 1.0x existing
  SELL    -> 0.2x existing (effective kill switch)

Output: buyback_insider_overlay.json
  per-ticker structure:
    {
      "bb_status": str,
      "f4_dollar": float,
      "f144_score": float,
      "net_direction": "BUY" | "SELL" | "NEUTRAL" | "NO_DATA",
      "multiplier": float,
      "score_delta": float  # bonus/penalty vs neutral
    }

ADDITIVE: does not modify any existing file. Wired as a separate
scoring contribution in full_universe_consensus.py that ADDS to
(does not replace) the existing buyback layer.
"""

from __future__ import annotations

import json
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "buyback_insider_overlay.json"


def main() -> int:
    bbv = json.loads((ROOT / "buyback_verify.json").read_text())
    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    f144 = json.loads((ROOT / "form144_scan.json").read_text())

    print(f"loaded: buyback={len(bbv)} f4={len(f4)} f144={len(f144)}")

    out = {}
    for tk, b in bbv.items():
        if not isinstance(b, dict):
            continue
        bb_status = b.get("status")
        # only relevant when buyback is meaningful
        if bb_status not in ("EXECUTING", "SHRINKING_NO_AUTH",
                              "TOKEN", "NO_AUTH"):
            continue
        bb_points = b.get("points") or 0

        f4_rec = f4.get(tk, {}) if isinstance(f4.get(tk), dict) else {}
        f4_dollar = (f4_rec.get("total_dollar") or 0) if f4_rec else 0

        f144_rec = f144.get(tk, {}) if isinstance(f144.get(tk), dict) else {}
        # form144 score field varies; use 'score' or 'points' (whichever exists)
        f144_score = 0.0
        for k in ("score", "points"):
            v = f144_rec.get(k) if f144_rec else None
            try:
                if v is not None:
                    f144_score = abs(float(v))
                    break
            except Exception:
                pass

        # Direction classification: compare F4 buys vs F144 proposed sales
        if f4_dollar == 0 and f144_score == 0:
            direction = "NO_DATA"
            multiplier = 1.0
        elif f4_dollar > 100_000 and f144_score < 5:
            direction = "BUY"
            multiplier = 1.5
        elif f144_score > 15 and f4_dollar < 100_000:
            direction = "SELL"
            multiplier = 0.2
        elif f4_dollar > 500_000 and f4_dollar > f144_score * 50_000:
            direction = "BUY"
            multiplier = 1.5
        elif f144_score > f4_dollar / 50_000:
            direction = "SELL"
            multiplier = 0.2
        else:
            direction = "NEUTRAL"
            multiplier = 1.0

        # Score delta = bonus/penalty applied to existing bb_points
        # (so this is purely additive on top of existing scoring)
        score_delta = round(bb_points * (multiplier - 1.0), 1)

        out[tk] = {
            "bb_status": bb_status,
            "bb_points": float(bb_points),
            "f4_dollar": float(f4_dollar),
            "f144_score": round(f144_score, 1),
            "net_direction": direction,
            "multiplier": multiplier,
            "score_delta": score_delta,
        }

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)} tickers)")

    # Direction distribution
    from collections import Counter
    dist = Counter(v["net_direction"] for v in out.values())
    print(f"\nDirection distribution:")
    for d, n in dist.most_common():
        print(f"  {d:<10} {n}")

    # Top positive deltas (BUY-confirmed buybacks)
    ranked = sorted(out.items(), key=lambda x: -x[1]["score_delta"])
    print(f"\n=== TOP 15 BUY-confirmed buybacks (positive delta) ===")
    for tk, v in ranked[:15]:
        print(f"  {tk:<8} bb={v['bb_status']:<22} delta={v['score_delta']:+.1f} "
              f"F4=${v['f4_dollar']/1e6:.1f}M F144={v['f144_score']:.0f}")

    # Bottom (SELL-killed buybacks)
    print(f"\n=== BOTTOM 15 SELL-killed buybacks (negative delta) ===")
    for tk, v in ranked[-15:]:
        print(f"  {tk:<8} bb={v['bb_status']:<22} delta={v['score_delta']:+.1f} "
              f"F4=${v['f4_dollar']/1e6:.1f}M F144={v['f144_score']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
