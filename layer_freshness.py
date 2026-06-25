"""Per-layer freshness tracking + age-decay multiplier.

S2.3 from AUDIT.md: some layers are 6 weeks old, others ran today.
Consensus weights them equally. A stale tender_scan misses live
tenders that have started since.

This module:
  1. Reads file mtime of every layer's primary output JSON/CSV.
  2. Computes age in days.
  3. Computes a decay multiplier:
       <=14 days  -> 1.0  (full weight)
       <=30 days  -> 0.85
       <=60 days  -> 0.6
       <=120 days -> 0.4
       > 120 days -> 0.25
  4. Writes layer_freshness.json with per-layer age, mtime, decay.
  5. CAN be applied to consensus by separate module (we do not auto-
     decay yet -- this is opt-in to avoid disrupting existing scoring).

This is purely informational right now. The decay is reported in the
output and surfaced in the xlsx Coverage tab, but NOT auto-applied
to consensus_score. To switch to decayed scoring requires adding a
single multiplier in full_universe_consensus.py. We leave that
opt-in.

NOTHING IS REMOVED. Existing layer JSON files are not modified.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "layer_freshness.json"


# Per-layer source files (the primary output of each scoring module)
LAYER_FILES = {
    "psu": "proxy_scan.json",
    "valuation": "yfinance_quick.json",
    "buyback": "buyback_verify.json",
    "tender": "tender_scan.json",
    "c10b51": "cancel_10b5_1.json",
    "f4_buys": "form4_buys.json",
    "f144": "form144_scan.json",
    "recent_incentive": "recent_incentive_asymmetry_120d.csv",
    "special_situations": "special_situations_unified.csv",
    "turnaround": "turnaround_signal.csv",
    # Tier 1
    "opportunistic_insiders": "opportunistic_insiders.json",
    "buyback_insider_overlay": "buyback_insider_overlay.json",
    "odd_lot_tender": "tender_odd_lot.json",
    "tender_mechanism": "tender_mechanism.json",
    # Tier 2
    "voss_cic": "voss_cic_triangulation.json",
    "post_ch11": "post_ch11_emergence.json",
    "internalization": "external_manager_internalization.json",
    "bumpitrage": "bumpitrage_tender_decline.json",
    "spinoff_volume": "spinoff_volume_timer.json",
    # Tier 3
    "arquitos": "arquitos_subsidiary_anchor.json",
    "coval_stafford": "coval_stafford_proxy.json",
    "backstopped_rights": "backstopped_rights.json",
    "fdic_call_report": "fdic_call_report_overlay.json",
    # NCAV + activist
    "net_net_ncav": "net_net_ncav.json",
    "activist_letter": "activist_letter_feed.json",
}


def decay_for_age(age_days: float) -> float:
    if age_days <= 14:  return 1.00
    if age_days <= 30:  return 0.85
    if age_days <= 60:  return 0.60
    if age_days <= 120: return 0.40
    return 0.25


def main() -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    out = {}
    print(f"Layer freshness audit (now = {now.strftime('%Y-%m-%d %H:%M UTC')})")
    print(f"{'LAYER':<26}{'FILE':<42}{'AGE':<8}{'DECAY':<7}")
    print("-" * 90)
    for layer, fn in LAYER_FILES.items():
        p = ROOT / fn
        if not p.exists():
            out[layer] = {
                "file": fn,
                "exists": False,
                "age_days": None,
                "decay": 0.0,
                "last_refreshed": None,
            }
            print(f"  {layer:<24}{fn:<42}{'MISSING':<8}{'-':<7}")
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)\
                .replace(tzinfo=None)
        age = (now - mtime).total_seconds() / 86400
        decay = decay_for_age(age)
        out[layer] = {
            "file": fn,
            "exists": True,
            "age_days": round(age, 1),
            "decay": decay,
            "last_refreshed": mtime.isoformat(timespec="seconds"),
            "size_bytes": p.stat().st_size,
        }
        flag = ""
        if age > 60:
            flag = "  STALE"
        elif age > 30:
            flag = "  aging"
        print(f"  {layer:<24}{fn:<42}{age:<7.1f}d {decay:<5.2f}{flag}")

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT}")

    # Summary
    fresh = sum(1 for v in out.values() if v.get("decay") == 1.0)
    stale = sum(1 for v in out.values() if v.get("decay", 0) < 0.6)
    missing = sum(1 for v in out.values() if not v.get("exists"))
    print(f"\nLayer freshness summary:")
    print(f"  Fresh (<=14d):  {fresh}")
    print(f"  Stale (>60d):   {stale}")
    print(f"  Missing:        {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
