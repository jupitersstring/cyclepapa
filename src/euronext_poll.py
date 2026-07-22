#!/usr/bin/env python3
"""
euronext_poll.py — Euronext Paris special-situations poller (French OAM).

Catches French/Euronext issuers in insolvency-adjacent proceedings —
sauvegarde (safeguard), redressement judiciaire (judicial reorganisation),
conciliation, restructuration, and reprise de cotation (RESUMPTION OF
LISTING, the post-reorg trade). live.euronext.com is antibot-blocked to
plain curl, so we use the FRENCH OAM (officially appointed mechanism) open-
data feed at info-financiere.gouv.fr — an Opendatasoft API, validated free
(no auth/key), full-text queryable over 500k+ regulated-information records.

Output: data/inbox/<filed>/tier_s/euronext_<id>.json.

Usage:
    python -m src.euronext_poll --days-back 180
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
ENDPOINT = ("https://www.info-financiere.gouv.fr/api/explore/v2.1/catalog/"
            "datasets/flux-amf-new-prod/records")
HEADERS = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}

# French insolvency / resumption vocabulary → (sub-label, note).
TERMS: dict[str, tuple[str, str]] = {
    "reprise de cotation": ("resumption", "Euronext reprise de cotation — "
                            "RESUMPTION of listing, typically post-"
                            "restructuring: the French post-reorg event."),
    "sortie de sauvegarde": ("emerged", "Sortie de sauvegarde — EXIT from "
                             "the safeguard procedure (emergence)."),
    "plan de sauvegarde": ("scheme", "Plan de sauvegarde — safeguard "
                           "reorganisation plan (court-supervised recap)."),
    "sauvegarde": ("scheme", "Procédure de sauvegarde — French safeguard "
                   "(debtor-in-possession reorganisation)."),
    "redressement judiciaire": ("restructuring", "Redressement judiciaire — "
                                "judicial reorganisation (deeper distress "
                                "than sauvegarde)."),
    "restructuration": ("restructuring", "Restructuration financière — "
                        "balance-sheet restructuring."),
    "conciliation": ("scheme", "Conciliation — confidential pre-insolvency "
                     "workout."),
}
FIELDS_TITLE = ("informationdeposee_inf_tit_inf", "inf_tit_inf", "title")
FIELDS_NAME = ("identificationsociete_iso_lib_emt", "iso_lib_emt",
               "emetteur", "issuer")
FIELDS_ISIN = ("identificationsociete_iso_cd_isi", "iso_cd_isi", "isin")
FIELDS_DATE = ("informationdeposee_inf_dat_emt", "inf_dat_emt", "date")


def _first(rec: dict, keys) -> str:
    for k in keys:
        if rec.get(k):
            return str(rec[k])
    return ""


def fetch(term: str, since: str, retries: int = 3) -> list[dict]:
    params = {
        "where": f'"{term}"',
        "order_by": "informationdeposee_inf_dat_emt DESC",
        "limit": 100,
    }
    url = f"{ENDPOINT}?{urlencode(params)}"
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2; continue
            r.raise_for_status()
            return r.json().get("results") or []
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries - 1:
                print(f"  ! Euronext '{term}' failed: {exc}", file=sys.stderr)
                return []
            time.sleep(delay); delay *= 2
    return []


def normalize(rec: dict, sub: str, note: str, term: str,
              fetched_at: str) -> dict:
    title = _first(rec, FIELDS_TITLE)
    name = _first(rec, FIELDS_NAME) or title[:60]
    isin = _first(rec, FIELDS_ISIN)
    d = _first(rec, FIELDS_DATE)[:10] or date.today().isoformat()
    rid = str(rec.get("recordid") or rec.get("id") or (isin + d))
    return {
        "tier": "tier_s",
        "query_label": "tier_s.post_reorg_emerged" if sub == "emerged"
        else f"tier_s.{sub}",
        "query_note": note + f"  [matched: {term}]",
        "cik": "",
        "ticker": f"EPA:{isin}" if isin else "",
        "isin": isin or None,
        "name": name.strip(),
        "form": title[:160],
        "form_code": "OAM-AMF",
        "accession": rid,
        "filed": d,
        "jurisdiction": "FR",
        "url": "https://www.info-financiere.gouv.fr/",
        "source": "OAM-AMF",
        "fetched_at": fetched_at,
    }


def write_inbox(records: list[dict]) -> int:
    for r in records:
        d = INBOX / r["filed"][:10] / r["tier"]
        d.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]", "_", r["accession"] or "no-id")[:60]
        (d / f"euronext_{slug}.json").write_text(
            json.dumps(r, indent=2, sort_keys=True, default=str))
    return len(records)


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    since = (date.today() - timedelta(days=days_back)).isoformat()
    print(f"Polling French OAM (Euronext) since {since}...")
    seen, records = set(), []
    for term, (sub, note) in TERMS.items():
        rows = fetch(term, since)
        kept = 0
        for rec in rows:
            r = normalize(rec, sub, note, term, fetched_at)
            if r["filed"] < since:
                continue
            k = r["accession"]
            if k in seen:
                continue
            seen.add(k)
            records.append(r)
            kept += 1
        print(f"  {term:26s} {kept:>4d} in window")
        time.sleep(0.3)
    if records:
        write_inbox(records)
        print(f"\nWrote {len(records)} OAM records")
    else:
        print("\nNo French insolvency/resumption records in window.")
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
