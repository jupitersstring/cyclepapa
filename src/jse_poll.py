#!/usr/bin/env python3
"""
jse_poll.py — Johannesburg Stock Exchange (JSE) SENS special-situations poller.

Catches JSE-listed business-rescue / scheme / restructuring / suspension /
resumption events. The official JSE SENS feed (sens.jse.co.za) is behind a
subscriber login, so we use Sharenet's free SENS mirror (validated: plain
GET HTML, no auth / paywall / geo-block).

Limitation: the feed returns ~the last 2 trading days regardless of the
`days` param, so this must run REGULARLY (daily) and dedup on (tdate, seq).

Output: data/inbox/<filed>/tier_s/jse_<tdate>_<seq>.json.

Usage:
    python -m src.jse_poll
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
LIST_URL = "https://www.sharenet.co.za/v3/sens.php"
HEADERS = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}

# Headline keyword → (sub-label, note). Business rescue is the SA Chapter-11
# analogue; reinstatement/resumption after suspension is the post-reorg trade.
KEYWORDS: list[tuple[str, str, str]] = [
    (r"business rescue", "restructuring",
     "JSE Business Rescue — South African Chapter-11 analogue "
     "(Companies Act ch.6): supervised reorganisation."),
    (r"reinstate|resumption of (?:trade|listing)|lifting of (?:the )?"
     r"suspension", "resumption",
     "JSE Reinstatement / Resumption of listing — trading resumes, "
     "typically post-restructuring: the SA post-reorg event."),
    (r"scheme of arrangement", "scheme",
     "JSE Scheme of Arrangement — court-supervised compromise."),
    (r"restructur|recapitalis", "restructuring",
     "JSE restructuring / recapitalisation."),
    (r"suspension of (?:listing|trade)", "suspension",
     "JSE Suspension of listing — pre-event distress signal."),
    (r"liquidation|winding[- ]up|delisting", "liquidation",
     "JSE Liquidation / winding-up / delisting."),
]

_ANCHOR = re.compile(
    r'sens_display\.php\?tdate=(\d+)&(?:amp;)?seq=(\d+)[^>]*>(.*?)</a>',
    re.I | re.S)


def fetch(retries: int = 4) -> str:
    import time
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(LIST_URL, headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! JSE SENS failed: {exc}", file=sys.stderr)
                return ""
            time.sleep(delay); delay *= 2
    return ""


def _classify(title: str):
    t = title.lower()
    for pat, sub, note in KEYWORDS:
        if re.search(pat, t):
            return sub, note
    return None


def normalize(tdate: str, seq: str, title: str, sub: str, note: str,
              fetched_at: str) -> dict:
    title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title))
                   ).strip()
    # "COMPANY NAME - Announcement title"
    name, _, headline = title.partition(" - ")
    try:
        filed = datetime.strptime(tdate[:8], "%Y%m%d").date().isoformat()
    except ValueError:
        filed = date.today().isoformat()
    return {
        "tier": "tier_s",
        "query_label": f"tier_s.{sub}",
        "query_note": note,
        "cik": "",
        "ticker": "",           # SENS headline carries no clean code
        "isin": None,
        "name": name.strip()[:80],
        "form": (headline or title)[:160],
        "form_code": "JSE-SENS",
        "accession": f"{tdate}_{seq}",
        "filed": filed,
        "jurisdiction": "ZA",
        "url": (f"https://www.sharenet.co.za/v3/sens_display.php?"
                f"tdate={tdate}&seq={seq}&scode="),
        "source": "JSE-SENS",
        "fetched_at": fetched_at,
    }


def write_inbox(records: list[dict]) -> int:
    for r in records:
        d = INBOX / r["filed"][:10] / r["tier"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"jse_{r['accession']}.json").write_text(
            json.dumps(r, indent=2, sort_keys=True, default=str))
    return len(records)


def poll() -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print("Polling JSE SENS (Sharenet mirror)...")
    page = fetch()
    anchors = _ANCHOR.findall(page)
    print(f"  {len(anchors)} SENS headlines (last ~2 trading days)")
    records, seen, counts = [], set(), {}
    for tdate, seq, title in anchors:
        cls = _classify(re.sub(r"<[^>]+>", "", title))
        if not cls:
            continue
        sub, note = cls
        key = f"{tdate}_{seq}"
        if key in seen:
            continue
        seen.add(key)
        records.append(normalize(tdate, seq, title, sub, note, fetched_at))
        counts[sub] = counts.get(sub, 0) + 1
    if records:
        write_inbox(records)
        print(f"  kept {len(records)} special-situation SENS items: "
              f"{', '.join(f'{k}={v}' for k, v in counts.items())}")
    else:
        print("  no special-situation SENS items in window")
    return len(records)


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    total = poll()
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
