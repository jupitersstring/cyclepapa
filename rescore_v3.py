"""Re-score the cancel_10b5_1.json against v3 logic in-memory.

For each ticker, re-run detect_actions on cached HTML, apply
cross-quarter dedupe, re-classify. Faster than the rescore-only
CLI because it sequentially processes only the tickers with
non-zero scores or events (~400 of 1995)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cancel_10b5_1 import (  # noqa: E402
    detect_actions, dedupe_cross_quarter, score_events,
    load_cached, atomic_write_json,
)


def main() -> int:
    path = Path("/home/user/cyclepapa/cancel_10b5_1.json")
    out = json.loads(path.read_text())
    n_changed = 0
    rescored = 0
    for tk, v in list(out.items()):
        if not v.get("_complete"):
            continue
        quarters = v.get("quarters_scanned") or []
        if not quarters:
            # Just mark data_available
            v["data_available"] = False
            v["_cache_version"] = "v3-dedup-foreign-aware"
            n_changed += 1
            continue
        # Re-extract from cache
        new_events = []
        for q in quarters:
            acc = q.get("accession")
            text = load_cached(acc) if acc else ""
            if not text:
                continue
            evs = detect_actions(text)
            for e in evs:
                e["accession"] = acc
                e["filing_date"] = q.get("filing_date")
                new_events.append(e)
        new_events = dedupe_cross_quarter(new_events)
        old_score = v.get("score", 0)
        old_event_count = len(v.get("events") or [])
        sc, reasons, counts = score_events(new_events)
        v["events"] = new_events
        v["score"] = sc
        v["reasons"] = reasons
        v["counts"] = counts
        v["data_available"] = True
        v["_cache_version"] = "v3-dedup-foreign-aware"
        if sc != old_score or len(new_events) != old_event_count:
            n_changed += 1
        rescored += 1
        if rescored % 100 == 0:
            print(f"  Rescored {rescored} tickers (changed: {n_changed})",
                  flush=True)
            atomic_write_json(path, out)
    atomic_write_json(path, out)
    print(f"\nDone. Rescored: {rescored}, changed: {n_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
