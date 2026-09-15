"""Eberhart-Altman post-Chapter-11 fresh-start equity leg.

Eberhart-Altman-Aggarwal (JF 54(5), 1999): firms emerging from
Chapter 11 deliver +24.6% to +138.8% CAR over 200 days post-
emergence (n=131). The signal is the fresh-start CUSIP + 8-K
emergence disclosure, before index funds and analysts re-pick up
coverage.

This module:
  1. Scans EDGAR full-text for 8-Ks containing "Plan of
     Reorganization" + "effective date" + "emergence" within
     trailing 540 days.
  2. Cross-references against any cancel_10b5_1 ticker (universe
     filter) and yfinance overlay.

Output: post_ch11_emergence.json
  {ticker: {emergence_date, accession, score, reasons}}
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "post_ch11_emergence.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--sleep", type=float, default=0.18)
    args = ap.parse_args()

    try:
        from recent import EFTS, _get, requests_quote, _cik_to_ticker_map
    except ImportError as e:
        print(f"need recent.py: {e}", file=sys.stderr)
        return 1

    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    cik_to_ticker = _cik_to_ticker_map()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Scanning Ch11 emergence 8-Ks {start}..{end}",
          file=sys.stderr, flush=True)

    # Every query must anchor to actual bankruptcy context. The old
    # first query ('"plan of reorganization" "effective date"') matched
    # Section 368(a)(1)(F) tax-reorg language in reincorporation Plans
    # of Conversion (e.g. GPGI's Nevada conversion) -- corporate
    # "reorganization" is not Chapter 11 emergence.
    queries = [
        '"plan of reorganization" "Chapter 11"',
        '"plan became effective" "Chapter 11"',
        '"emergence from Chapter 11"',
        '"emerged from Chapter 11"',
        '"fresh start accounting"',
        '"plan of reorganization confirmed"',
    ]

    found = {}  # cik -> (ticker, filing_date, accession, query_match)
    for q in queries:
        offset = 0
        while len(found) < args.limit and offset < 1000:
            url = (f"{EFTS}?forms=8-K&dateRange=custom"
                   f"&startdt={start}&enddt={end}"
                   f"&from={offset}&q={requests_quote(q)}")
            try:
                data = _get(url).json()
            except Exception:
                break
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                src = h.get("_source", {}) or {}
                ciks = src.get("ciks") or []
                cik = f"{int(ciks[0]):010d}" if ciks else None
                if not cik or cik in found:
                    continue
                tickers = src.get("tickers") or []
                ticker = tickers[0] if tickers else cik_to_ticker.get(cik)
                if not ticker:
                    continue
                file_date = src.get("file_date", "")
                id_parts = (h.get("_id") or "").split(":")
                if len(id_parts) != 2:
                    continue
                accession = id_parts[0]
                found[cik] = (ticker, file_date, accession, q)
            offset += 100
            time.sleep(args.sleep)
        print(f"  query \"{q[:40]}...\" -> {len(found)} cumulative",
              file=sys.stderr, flush=True)

    out = {}
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    for cik, (tk, fd, acc, q) in found.items():
        # parse filing date
        try:
            fdt = datetime.strptime(fd[:10], "%Y-%m-%d")
            days_ago = (today - fdt).days
        except Exception:
            days_ago = None
        # Score: recency + presence of multiple emergence-language hits
        score = 0.0
        reasons = []
        if days_ago is not None:
            if days_ago <= 60: score += 25; reasons.append(f"{days_ago}d ago (very recent)")
            elif days_ago <= 200: score += 20; reasons.append(f"{days_ago}d ago (in 200d alpha window)")
            elif days_ago <= 365: score += 12; reasons.append(f"{days_ago}d ago")
            elif days_ago <= 540: score += 6
        # value overlay
        y = yf.get(tk, {}) or {}
        try: pb = float(y.get("p_b")) if y.get("p_b") is not None else None
        except: pb = None
        if pb and 0 < pb < 0.7:
            score += 10; reasons.append(f"P/B {pb:.2f}")
        elif pb and 0 < pb < 1.0:
            score += 5

        out[tk] = {
            "emergence_filing_date": fd,
            "days_since_emergence": days_ago,
            "accession": acc,
            "query_match": q,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)})")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 post-Ch11 emergence ===")
    for tk, v in ranked[:20]:
        print(f"  {tk:<8} score={v['score']:<5} "
              f"days={v.get('days_since_emergence')} "
              f"date={v['emergence_filing_date']} {v['reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
