"""Biotech PDUFA / FDA milestone calendar (additive primary screen).

Per AUDIT.md S1.3: PSU forensics under-serves biotech / healthcare
(many small biotechs have stock-option-heavy not PSU-heavy
compensation). For these names the structural catalyst is the FDA
decision date.

PDUFA = Prescription Drug User Fee Act target action date. The FDA
must approve, reject, or extend on the assigned date. PDUFA dates
produce +/- 30-80% one-day moves and are the single biggest
event-driven biotech catalyst.

We can't pull PDUFA dates from FDA directly without API auth, but
they routinely appear in:
  - 8-K filings (Item 7.01 / 8.01 with "PDUFA" / "target action date")
  - 10-K and 10-Q "Pipeline" / "Clinical Development" sections
  - Press releases announcing NDA/BLA acceptance

This module scans EDGAR full-text for these and extracts the named
date.

ADDITIVE: separate output file. Existing layers untouched.

Output: biotech_pdufa_calendar.json
  {ticker: {pdufa_date_text, days_to_pdufa, drug_name, accession,
            score, reasons}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "biotech_pdufa_calendar.json"


PDUFA_RX = re.compile(
    r"(?:PDUFA\s+(?:date|action\s+date|goal\s+date)|"
    r"target\s+action\s+date|"
    r"PDUFA\s+target)[^.]{0,200}?"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)
DRUG_NAME_RX = re.compile(
    r"(?:our\s+(?:lead\s+)?(?:product\s+candidate|drug\s+candidate|"
    r"investigational\s+drug|investigational\s+(?:product|therapy))\s+"
    r"(?:is\s+)?)([A-Z][A-Z0-9\-]{2,20})",
    re.I,
)
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}


def parse_pdufa_date(text: str) -> tuple[str, datetime] | None:
    """METHODOLOGY FIX (audit finding A4): the day is now captured
    directly adjacent to the month inside PDUFA_RX (group 2) instead of
    scanning the whole matched block for the first digit -- which had
    grabbed "Phase 3" / "Q1" / "Cohort 1" digits as the day."""
    m = PDUFA_RX.search(text)
    if not m:
        return None
    month_name = m.group(1).title()
    day = int(m.group(2))
    year = int(m.group(3))
    try:
        dt = datetime(year, MONTHS[month_name], day)
        return m.group(0).strip(), dt
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    try:
        from recent import EFTS, _get, requests_quote, _cik_to_ticker_map
    except ImportError as e:
        print(f"need recent.py: {e}", file=sys.stderr)
        return 1

    try:
        from cache_store import read_html
    except ImportError:
        read_html = None
    try:
        from edgar import _get as edgar_get
    except ImportError:
        edgar_get = None

    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    cik_to_ticker = _cik_to_ticker_map()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Scanning PDUFA-related 8-Ks {start}..{end}", file=sys.stderr,
          flush=True)

    queries = [
        '"PDUFA"',
        '"PDUFA date"',
        '"PDUFA target action"',
        '"target action date" "FDA"',
        '"NDA accepted" "PDUFA"',
        '"BLA accepted" "PDUFA"',
    ]
    found = {}
    for q in queries:
        offset = 0
        while len(found) < args.limit and offset < 600:
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
                if not cik:
                    continue
                tickers = src.get("tickers") or []
                ticker = tickers[0] if tickers else cik_to_ticker.get(cik)
                if not ticker:
                    continue
                id_parts = (h.get("_id") or "").split(":")
                if len(id_parts) != 2:
                    continue
                accession, primary_doc = id_parts
                file_date = src.get("file_date", "")
                key = (ticker, accession)
                if key in found:
                    continue
                found[key] = {
                    "ticker": ticker, "cik": cik, "accession": accession,
                    "primary_doc": primary_doc, "filing_date": file_date,
                }
            offset += 100
            time.sleep(args.sleep)
        print(f"  query \"{q[:30]}\" -> {len(found)} cumulative",
              file=sys.stderr, flush=True)

    out = {}
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    for key, meta in found.items():
        tk = meta["ticker"]
        # Fetch HTML body
        text = ""
        if read_html:
            try:
                html = read_html(meta["accession"]) or ""
                if html:
                    text = re.sub(r"<[^>]+>", " ", html)
                    text = re.sub(r"&nbsp;|&#160;", " ", text)
                    text = re.sub(r"\s+", " ", text)
            except Exception:
                pass
        if not text and edgar_get:
            acc_no = meta["accession"].replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{int(meta['cik'])}/{acc_no}/{meta['primary_doc']}")
            try:
                html = edgar_get(url).text or ""
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"&nbsp;|&#160;", " ", text)
                text = re.sub(r"\s+", " ", text)
            except Exception:
                pass
            time.sleep(args.sleep)
        if not text:
            continue

        parsed = parse_pdufa_date(text)
        if not parsed:
            continue
        match_text, dt = parsed
        days_to = (dt - today).days

        # Drug name attempt
        drug = None
        dm = DRUG_NAME_RX.search(text)
        if dm:
            drug = dm.group(1)

        # Score: closer = higher (proximity to event), but also penalize
        # already-past dates unless within the last 60 days
        score = 0.0
        reasons = []
        if days_to is not None:
            if 0 < days_to <= 30:
                score += 30; reasons.append(f"PDUFA in {days_to}d (imminent)")
            elif 0 < days_to <= 90:
                score += 22; reasons.append(f"PDUFA in {days_to}d")
            elif 0 < days_to <= 180:
                score += 14; reasons.append(f"PDUFA in {days_to}d")
            elif 0 < days_to <= 365:
                score += 6
            elif -60 < days_to <= 0:
                score += 8; reasons.append(f"PDUFA {-days_to}d ago "
                                            "(post-decision)")

        # Keep best (most recent / nearest) per ticker
        if tk in out and out[tk].get("score", 0) >= score:
            continue
        y = yf.get(tk, {}) or {}
        out[tk] = {
            "pdufa_date_text": match_text[:150],
            "pdufa_date": dt.strftime("%Y-%m-%d"),
            "days_to_pdufa": days_to,
            "drug_name": drug,
            "filing_date": meta["filing_date"],
            "accession": meta["accession"],
            "sector": y.get("sector"),
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)})")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 by PDUFA proximity ===")
    for tk, v in ranked[:20]:
        print(f"  {tk:<7} score={v['score']:<5} d={v['days_to_pdufa']:<5} "
              f"date={v['pdufa_date']}  {v['reasons'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
