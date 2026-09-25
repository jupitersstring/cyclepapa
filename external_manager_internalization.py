"""External-manager internalization signal (Clark Street Value
methodology, Braemar / Ashford archetype).

The signal: externally-managed REIT/BDC where the advisor contract
has a termination clause; recent board composition change suggests
the board is preparing to internalize management. Internalization
unlocks 15-30% NAV via removed fee drag.

This module:
  1. Scans EDGAR 8-K full-text for "external advisor" + "termination
     fee" + recent dating language.
  2. Cross-references with REIT/BDC sector tags from yfinance.

Output: external_manager_internalization.json
  {ticker: {has_internalization_lang, sector, score, reasons}}
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
OUT = ROOT / "external_manager_internalization.json"


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
    print(f"Scanning internalization 8-Ks/proxies {start}..{end}",
          file=sys.stderr, flush=True)

    queries = [
        '"internalization of management"',
        '"internalization transaction"',
        '"terminated the external" "manager"',
        '"termination fee" "advisor" "REIT"',
        '"buy out" "external manager"',
        '"internalize" "management" "agreement"',
        '"terminate the advisory agreement"',
    ]

    found = {}
    for q in queries:
        offset = 0
        while len(found) < args.limit and offset < 600:
            url = (f"{EFTS}?forms=8-K,DEF+14A,DEFM14A&dateRange=custom"
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
                form = src.get("form", "")
                found[cik] = (ticker, file_date, accession, q, form)
            offset += 100
            time.sleep(args.sleep)
        print(f"  query \"{q[:35]}...\" -> {len(found)} cumulative",
              file=sys.stderr, flush=True)

    out = {}
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    for cik, (tk, fd, acc, q, form) in found.items():
        try:
            fdt = datetime.strptime(fd[:10], "%Y-%m-%d")
            days_ago = (today - fdt).days
        except Exception:
            days_ago = None
        y = yf.get(tk, {}) or {}
        sector = y.get("sector") or ""
        industry = y.get("industry") or ""
        score = 0.0
        reasons = []
        # Sector match (REIT or BDC are the canonical targets)
        is_reit = "REIT" in industry.upper() or "Real Estate" in (sector or "")
        is_bdc = "BDC" in industry.upper() or "Capital Markets" in (industry or "")
        if is_reit or is_bdc:
            score += 12
            reasons.append("REIT/BDC structure")
        # Recency
        if days_ago is not None:
            if days_ago <= 60: score += 25; reasons.append(f"{days_ago}d ago")
            elif days_ago <= 180: score += 18
            elif days_ago <= 365: score += 10
            else: score += 4
        # Form type weight
        if form in ("DEF 14A", "DEFM14A"):
            score += 8; reasons.append("proxy vote pending")
        # P/B floor
        try: pb = float(y.get("p_b")) if y.get("p_b") is not None else None
        except: pb = None
        if pb and 0 < pb < 0.7:
            score += 8; reasons.append(f"P/B {pb:.2f}")

        out[tk] = {
            "internalization_filing_date": fd,
            "days_since": days_ago,
            "accession": acc,
            "form_type": form,
            "query_match": q,
            "sector": sector,
            "industry": industry,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)})")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 internalization signal ===")
    for tk, v in ranked[:20]:
        print(f"  {tk:<8} score={v['score']:<5} days={v['days_since']} "
              f"sector={v['sector'][:15]:<15} form={v['form_type']:<8} "
              f"{v['reasons'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
