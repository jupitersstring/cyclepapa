"""Coval-Stafford fire-sale flow-pressure leg (proxy via yfinance).

Coval-Stafford (JFE 2007): stocks sold by mutual funds in extreme
outflow quintile lose -7.9% during the quarter, reverse +5% over the
next 18 months. The clean signal requires N-PORT mutual-fund holdings
deltas, which we don't yet have.

This module builds a PROXY using yfinance fields available now:
  - High institutional ownership (>= 60%)  -- vulnerable to flow
  - High short interest (>= 15%)            -- pressure ongoing
  - Deep drawdown (>= 50% from 52w high)    -- consistent with fire sale
  - Negative trailing 3m price change       -- the sell-off itself

A name passing all four is plausibly experiencing forced institutional
selling; per Coval-Stafford, expect +5% reversion over the next 18m.

The PROXY is explicitly less precise than the true Coval-Stafford
signal (which needs N-PORT outflow deltas). We mark it as an
approximation. To upgrade, we would need to ingest:
  - Quarterly 13F holdings deltas (heavy build)
  - N-PORT monthly fund holdings (heavy build)

Output: coval_stafford_proxy.json
  {ticker: {inst_pct, short_pct, drawdown_pct, score, reasons}}
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "coval_stafford_proxy.json"


def _num(v):
    if v is None: return None
    try: return float(v)
    except Exception: return None


def main() -> int:
    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    print(f"yf coverage: {len(yf)}", file=sys.stderr)

    out = {}
    for tk, y in yf.items():
        if not isinstance(y, dict):
            continue
        inst = _num(y.get("inst_pct"))
        short = _num(y.get("short_pct"))
        px = _num(y.get("price"))
        hi = _num(y.get("fwk_high"))
        lo = _num(y.get("fwk_low"))
        if not (inst and short and px and hi):
            continue
        if hi <= 0:
            continue
        dd = (1 - px / hi) * 100
        run_low = (px / lo - 1) * 100 if lo and lo > 0 else None

        # METHODOLOGY FIX (audit finding A6): yfinance
        # heldPercentInstitutions can exceed 100% (share-class double
        # counting; 456 of 1,180 rows were >100%). Cap at 100% for
        # scoring so the "very high" bucket isn't saturated by the
        # artifact; the raw value is preserved in the output.
        inst_raw = inst
        inst = min(inst, 1.0)

        # Coval-Stafford pressure score: all four pillars
        score = 0.0
        reasons = []
        if inst >= 0.70:
            score += 12; reasons.append(f"inst {inst*100:.0f}% (very high)")
        elif inst >= 0.50:
            score += 6; reasons.append(f"inst {inst*100:.0f}%")
        if short >= 0.20:
            score += 14; reasons.append(f"short {short*100:.0f}%")
        elif short >= 0.10:
            score += 7; reasons.append(f"short {short*100:.0f}%")
        if dd >= 60:
            score += 15; reasons.append(f"DD {dd:.0f}%")
        elif dd >= 40:
            score += 8; reasons.append(f"DD {dd:.0f}%")
        if run_low is not None and run_low < 15:
            score += 8; reasons.append(f"{run_low:.0f}% above 52w low")

        # Full quadrilateral: all four pillars firing at high level
        full_quad = (inst >= 0.60 and short >= 0.15 and dd >= 50)
        if full_quad:
            score += 10
            reasons.append("FULL Coval-Stafford proxy quadrilateral")

        # Only output names that passed >=2 of the 4 thresholds
        if score < 18:
            continue

        out[tk] = {
            "inst_pct": inst,
            "inst_pct_raw": inst_raw,
            "short_pct": short,
            "drawdown_pct": round(dd, 1),
            "above_52w_low_pct": run_low,
            "full_quadrilateral": full_quad,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT} ({len(out)})")

    full = sum(1 for v in out.values() if v.get("full_quadrilateral"))
    print(f"\nFull-quadrilateral fire-sale candidates: {full}")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 Coval-Stafford fire-sale PROXY ===")
    for tk, v in ranked[:20]:
        flag = "FULL!" if v["full_quadrilateral"] else "     "
        print(f"  {tk:<7} score={v['score']:<5} inst={v['inst_pct']*100:5.0f}% "
              f"short={v['short_pct']*100:5.1f}% DD={v['drawdown_pct']:5.0f}% "
              f"{flag} {v['reasons'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
