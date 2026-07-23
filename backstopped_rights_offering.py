"""Backstopped rights-offering arbitrage (Clark Street Value).

The signal: a company files a rights offering at a discount to
market, with an anchor (insider, controlling holder, well-known
investor like Malone/Pershing) signing a backstop commitment. The
oversubscription privilege lets pro-rata participants buy below
market when the offering is undersubscribed.

This module:
  1. Scans EDGAR S-1/F-1/424B and 8-K filings for "rights offering"
     + "backstop" or "standby" + "oversubscription"
  2. Flags subscription price vs current price gap

Output: backstopped_rights.json
  {ticker: {filing_date, accession, score, reasons}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "backstopped_rights.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--sleep", type=float, default=0.15)
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
    print(f"Scanning backstopped rights offerings {start}..{end}",
          file=sys.stderr, flush=True)

    queries = [
        '"rights offering" "backstop"',
        '"rights offering" "oversubscription"',
        '"rights offering" "standby" "commitment"',
        '"subscription rights" "backstop"',
        '"standby purchase agreement" "rights"',
    ]
    found = {}
    for q in queries:
        offset = 0
        while len(found) < args.limit and offset < 600:
            url = (f"{EFTS}?forms=8-K,S-1,F-1,424B3,424B4,424B5&"
                   f"dateRange=custom&startdt={start}&enddt={end}"
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
        score = 0.0
        reasons = []
        # Recency
        if days_ago is not None:
            if days_ago <= 60: score += 25; reasons.append(f"{days_ago}d ago (active)")
            elif days_ago <= 180: score += 15; reasons.append(f"{days_ago}d ago")
            elif days_ago <= 365: score += 8
            else: score += 3
        # Form weight: S-1/424B more committal than 8-K announcement
        if form.startswith("S-") or form.startswith("F-") or form.startswith("424"):
            score += 8; reasons.append(f"effective {form}")
        # Microcap (the typical universe)
        try:
            mcap = float(y.get("mcap") or 0)
        except Exception:
            mcap = 0
        if mcap and mcap < 500e6:
            score += 8; reasons.append(f"microcap ${mcap/1e6:.0f}M")
        # P/B floor
        try:
            pb = float(y.get("p_b") or 0)
        except Exception:
            pb = 0
        if pb and 0 < pb < 1.0:
            score += 8; reasons.append(f"P/B {pb:.2f}")

        out[tk] = {
            "filing_date": fd,
            "days_since": days_ago,
            "accession": acc,
            "form_type": form,
            "query_match": q,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT} ({len(out)})")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 backstopped rights offerings ===")
    for tk, v in ranked[:20]:
        print(f"  {tk:<8} score={v['score']:<5} days={v['days_since']} "
              f"form={v['form_type']:<8} {v['reasons'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
