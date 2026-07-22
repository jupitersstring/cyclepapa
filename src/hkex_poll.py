#!/usr/bin/env python3
"""
hkex_poll.py — Hong Kong (HKEX) special-situations announcement poller.

Closes a whole GEOGRAPHY the EDGAR-centric funnel can't see: a Hong Kong
company that restructures and resumes trading files nothing with the SEC, so
its post-reorg equity is invisible to us. HKEXnews exposes a free, keyless
JSON title-search behind its "Listed Company Information Advanced Search",
filterable by HKEX's own headline-category codes — validated live (plain
GET, no auth / paywall / JS-render).

Highest-signal categories for our thesis:
  17650  Resumption of Trading          → the HK post-reorg / re-listing event
  17450  Group Restructuring / Scheme of Arrangement
  17600  Privatisation / Withdrawal
  17850  Suspension of Trading          → the pre-event distress signal
  17900  Winding Up & Liquidation

Output: data/inbox/<filed>/tier_s/hkex_<news_id>.json, sub-labels
tier_s.resumption / .scheme / .privatisation / .suspension / .liquidation,
so inbox_promote + emergence_master pick them up like any other source.

Usage:
    python -m src.hkex_poll                 # last 180 days
    python -m src.hkex_poll --days-back 365
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
ENDPOINT = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
HEADERS = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com"),
    "Accept": "application/json"}

# t2code → (sub-label, note). All under t2Gcode=7 (Announcements & Notices).
CATEGORIES: dict[str, tuple[str, str]] = {
    "17650": ("resumption",
              "HKEX Resumption of Trading — trading resumes after a "
              "suspension, typically on completion of a restructuring / "
              "scheme: the Hong Kong post-reorg / re-listing event."),
    "17450": ("scheme",
              "HKEX Group Restructuring or Scheme of Arrangement — the "
              "court-supervised recapitalisation itself."),
    "17600": ("privatisation",
              "HKEX Privatisation / Withdrawal of Listing — take-private / "
              "delisting event."),
    "17850": ("suspension",
              "HKEX Suspension of Trading — the pre-event distress signal "
              "(long suspensions precede restructuring or delisting)."),
    "17900": ("liquidation",
              "HKEX Winding Up & Liquidation — terminal distress."),
}
BASE = {"sortDir": 0, "sortByOptions": "DateTime", "category": 0,
        "market": "SEHK", "searchType": 1, "t1code": 10000,
        "stockId": -1, "rowRange": 1000, "lang": "en"}


def _fetch(t2code: str, start: date, end: date, retries: int = 4) -> list[dict]:
    """One category over a window → list of announcement rows. HKEXnews
    returns an envelope whose `result` is a STRINGIFIED JSON array, so parse
    the body then parse result again."""
    params = dict(BASE, t2Gcode=7, t2code=t2code,
                  fromDate=start.strftime("%Y%m%d"),
                  endDate=end.strftime("%Y%m%d"),
                  toDate=end.strftime("%Y%m%d"))
    url = f"{ENDPOINT}?{urlencode(params)}"
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2; continue
            r.raise_for_status()
            env = r.json()
            raw = env.get("result")
            if isinstance(raw, str):
                return json.loads(raw or "[]")
            return raw or []
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries - 1:
                print(f"  ! HKEX {t2code} failed: {exc}", file=sys.stderr)
                return []
            time.sleep(delay); delay *= 2
    return []


def _fmt_date(dt: str) -> str:
    """'dd/mm/yyyy hh:mm' → 'YYYY-MM-DD'."""
    try:
        return datetime.strptime(dt.split()[0], "%d/%m/%Y").date().isoformat()
    except (ValueError, IndexError):
        return date.today().isoformat()


def normalize(row: dict, sub: str, note: str, fetched_at: str) -> dict:
    code = str(row.get("STOCK_CODE") or "").strip().zfill(5)
    ticker = f"{code}.HK" if code and code != "00000" else ""
    news_id = str(row.get("NEWS_ID") or "")
    link = row.get("FILE_LINK") or ""
    return {
        "tier": "tier_s",
        "query_label": f"tier_s.{sub}",
        "query_note": note,
        "cik": "",
        "ticker": f"HKEX:{ticker}" if ticker else "",
        "isin": None,
        "name": (row.get("STOCK_NAME") or "").strip(),
        "form": (row.get("TITLE") or "")[:160],
        "form_code": "HKEX-announcement",
        "accession": news_id,
        "filed": _fmt_date(row.get("DATE_TIME") or ""),
        "jurisdiction": "HK",
        "url": ("https://www1.hkexnews.hk" + link) if link else "",
        "source": "HKEXnews",
        "fetched_at": fetched_at,
    }


# keyword catch for items mis-filed under a generic category
_KW = ("RESUMPTION", "RESTRUCTUR", "SCHEME OF ARRANGEMENT", "WINDING UP",
       "PRIVATIS", "LIQUIDAT")


def write_inbox(records: list[dict]) -> int:
    for r in records:
        d = INBOX / r["filed"][:10] / r["tier"]
        d.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        (d / f"hkex_{slug}.json").write_text(
            json.dumps(r, indent=2, sort_keys=True, default=str))
    return len(records)


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    end = date.today()
    start = end - timedelta(days=days_back)
    print(f"Polling HKEXnews ({start.isoformat()}..{end.isoformat()})...")
    seen: set[str] = set()
    records: list[dict] = []
    for t2code, (sub, note) in CATEGORIES.items():
        # chunk into <=12-month windows (category search allows history)
        rows: list[dict] = []
        w_end = end
        while w_end > start:
            w_start = max(start, w_end - timedelta(days=365))
            rows += _fetch(t2code, w_start, w_end)
            w_end = w_start - timedelta(days=1)
            time.sleep(0.2)
        kept = 0
        for row in rows:
            nid = str(row.get("NEWS_ID") or "")
            if not nid or nid in seen:
                continue
            seen.add(nid)
            records.append(normalize(row, sub, note, fetched_at))
            kept += 1
        print(f"  {sub:14s} (t2={t2code}) {kept:>4d} announcements")
    if records:
        n = write_inbox(records)
        print(f"\nWrote {n} HKEX announcements across "
              f"{len({r['filed'][:10] for r in records})} days")
    else:
        print("\nNo HKEX special-situation announcements in window.")
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=180)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
