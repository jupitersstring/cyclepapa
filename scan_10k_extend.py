"""Extend cancel_10b5_1 coverage to 10-Ks (and FPI 20-F/6-K).

For each ticker, fetches the company submissions JSON, identifies any
10-K / 20-F / 6-K filings not present in quarters_scanned, processes
each new filing, merges events, and re-runs dedupe + score.

Resumable: a per-ticker '_10k_extended' flag prevents reprocessing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cancel_10b5_1 import (
    detect_actions, dedupe_cross_quarter, score_events,
    load_cached, fetch_and_cache_filing, atomic_write_json,
)

ROOT = Path("/home/user/cyclepapa")


def submissions_filings(ticker: str, forms=("10-K", "20-F", "6-K"),
                       limit=4, days=540):
    """Pull recent filings of these forms for one ticker."""
    from recent import company_filings
    return company_filings(ticker, forms=forms,
                           limit_per_form=limit, days=days)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "cancel_10b5_1.json"))
    ap.add_argument("--sleep", type=float, default=0.20)
    ap.add_argument("--shard", type=str, default="",
                    help="Process only tickers in shard file (one per line).")
    ap.add_argument("--checkpoint-every", type=int, default=10)
    ap.add_argument("--limit", type=int, default=10_000)
    args = ap.parse_args()

    path = Path(args.json)
    out = json.loads(path.read_text())

    if args.shard:
        wanted = {t.strip().upper() for t in Path(args.shard).read_text().splitlines() if t.strip()}
        keys = [k for k in out if k in wanted]
    else:
        keys = list(out)

    n_processed = 0
    n_with_new_filings = 0
    n_new_events = 0

    for i, tk in enumerate(keys, 1):
        if i > args.limit:
            break
        v = out[tk]
        if v.get("_10k_extended"):
            continue
        n_processed += 1

        existing_accs = {q.get("accession")
                         for q in v.get("quarters_scanned") or []}
        try:
            new_filings = submissions_filings(tk)
        except Exception as e:
            print(f"  {tk}: filings fetch fail: {e}", file=sys.stderr)
            v["_10k_extended"] = True
            continue

        added = 0
        for fl in new_filings:
            if fl.accession in existing_accs:
                continue
            text = load_cached(fl.accession)
            if not text:
                text = fetch_and_cache_filing(fl.cik, fl.accession,
                                              fl.primary_doc)
                time.sleep(args.sleep)
            if not text:
                continue
            v.setdefault("quarters_scanned", []).append({
                "accession": fl.accession,
                "filing_date": fl.filing_date,
            })
            events = detect_actions(text)
            for e in events:
                e["accession"] = fl.accession
                e["filing_date"] = fl.filing_date
                v.setdefault("events", []).append(e)
                n_new_events += 1
            added += 1

        if added:
            n_with_new_filings += 1
            # Re-dedupe and re-score
            v["events"] = dedupe_cross_quarter(v["events"])
            v["data_available"] = len(v["quarters_scanned"]) > 0
            sc, reasons, counts = score_events(v["events"])
            v["score"] = sc
            v["reasons"] = reasons
            v["counts"] = counts

        v["_10k_extended"] = True

        if i % args.checkpoint_every == 0:
            atomic_write_json(path, out)
            print(f"  [{i}/{len(keys)}] processed={n_processed} "
                  f"with_new={n_with_new_filings} "
                  f"new_events={n_new_events}", flush=True)

    atomic_write_json(path, out)
    print(f"\nDone. Processed: {n_processed}, with new filings: "
          f"{n_with_new_filings}, new events: {n_new_events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
