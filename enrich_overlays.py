"""Batch primary-source enrichment.

Walks every ticker that's appeared in any cached *_detail.json sweep and
adds two overlays:

  - SC 13D / 13D/A filings in the past 365 days  -> activist holders
    declared as primary fact (replaces text-mention heuristic)
  - Form 4 / 4/A filings in the past 90 days     -> insider transaction
    tape (count is a directional signal; transaction code P vs S
    requires per-XML parse, deferred)

Updates the in-memory rows AND writes a merged enrichment file
(`enrichment_overlay.json`) keyed by ticker. The
`governance_psu_overlap` script reads the overlay and blends it into
its scoring so re-running the screener picks up every primary-source
hit on every name without a full pipeline rerun.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from recent import company_13d_filers, company_insider_buys
from universe_filter import is_excluded


def collect_tickers() -> set[str]:
    sources = [
        "v2_detail.json", "wide180_detail.json",
        "induce_detail.json", "restruct_v7.json",
        "targets_v4.json", "missing_v8.json",
    ]
    tickers: set[str] = set()
    for fn in sources:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            for r in json.loads(p.read_text()):
                if r.get("error"):
                    continue
                tk = (r.get("ticker") or "").upper()
                if tk:
                    tickers.add(tk)
        except Exception:
            pass
    return tickers


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="enrichment_overlay.json")
    p.add_argument("--sleep", type=float, default=0.20)
    p.add_argument("--skip-excluded", action="store_true",
                   help="Skip SPAC warrants / preferreds before enriching.")
    p.add_argument("--limit", type=int, default=10000)
    args = p.parse_args()

    tickers = sorted(collect_tickers())
    print(f"Collected {len(tickers)} unique tickers from cached sweeps.",
          file=sys.stderr)

    overlay: dict[str, dict] = {}
    n_processed = 0
    n_with_13d = 0
    n_with_form4 = 0

    # Resume support: load existing overlay if present and skip rows we
    # already have.
    out_path = Path(args.out)
    if out_path.exists():
        try:
            overlay = json.loads(out_path.read_text())
            print(f"Resuming -- overlay already has {len(overlay)} tickers.",
                  file=sys.stderr)
        except Exception:
            overlay = {}

    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        if tk in overlay:
            continue
        if args.skip_excluded:
            bad, _ = is_excluded(tk)
            if bad:
                continue
        try:
            sc13 = company_13d_filers(tk, days=365)
        except Exception:
            sc13 = []
        try:
            f4 = company_insider_buys(tk, days=90)
        except Exception:
            f4 = []

        overlay[tk] = {
            "sc13d_filings_1y": len(sc13),
            "sc13d_dates": [f["date"] for f in sc13[:8]],
            "insider_form4_count_90d": len(f4),
            "insider_form4_dates": [f["date"] for f in f4[:8]],
            "insider_buying_evidence": len(f4) >= 3,
        }
        n_processed += 1
        if sc13:
            n_with_13d += 1
        if len(f4) >= 3:
            n_with_form4 += 1

        if i % 25 == 0:
            print(f"  [{i}/{len(tickers)}] processed; "
                  f"13D-hit={n_with_13d}, Form4-hit={n_with_form4}",
                  file=sys.stderr, flush=True)
            # Periodic checkpoint so a crash mid-run doesn't lose work.
            out_path.write_text(json.dumps(overlay, indent=2, default=str))

        time.sleep(args.sleep)

    out_path.write_text(json.dumps(overlay, indent=2, default=str))
    print(f"\nWrote {args.out} ({len(overlay)} tickers).", file=sys.stderr)
    print(f"  with SC 13D in past 1y     : {n_with_13d}", file=sys.stderr)
    print(f"  with 3+ Form 4s in past 90d: {n_with_form4}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
