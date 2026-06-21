#!/usr/bin/env python3
"""
pacer_poll.py — daily US bankruptcy-court docket poller via CourtListener.

Implements recommendation #1+#6 from output/process_improvements.md.

CourtListener's RECAP archive mirrors PACER docket entries from federal
courts. The v4 REST API at api.courtlistener.com is free and requires
no authentication for read access — same posture as EDGAR.

We poll the seven most-active US commercial bankruptcy courts (handles
~95% of large-cap Chapter 11s by deal value):
  deb   - Delaware Bankruptcy
  nysb  - SDNY Bankruptcy
  txsb  - SD Texas Bankruptcy
  cacb  - C.D. California Bankruptcy
  ilnb  - N.D. Illinois Bankruptcy
  gasb  - S.D. Georgia Bankruptcy (Houston used to be Atlanta-friendly)
  mab   - Massachusetts Bankruptcy

Daily window of new Chapter 11 cases filtered for company-name patterns
(corp / inc / llc / holdings / plc / co / lp). Output goes to
data/inbox/<date>/tier_s/pacer_<docket_id>.json so inbox_promote.py
picks it up under tier_s.bankruptcy_11.

Future extensions (deferred):
- Per-docket alerts via /api/rest/v4/alerts/ (requires CourtListener
  account; 5 free, 15 with browser extension).
- Rule 2019 statement parsing (ad-hoc-committee membership signals,
  recommendation #6 from the synthesis).
- Plan-support agreement / 363 sale motion detection (full RECAP doc
  parse).

Usage:
    python -m src.pacer_poll                  # poll today
    python -m src.pacer_poll --days-back 7    # last week
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

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
API = "https://www.courtlistener.com/api/rest/v4/search/"

USER_AGENT = os.environ.get(
    "PACER_USER_AGENT",
    "cyclepapa-screener research@example.com",
)

# The seven bankruptcy courts that account for the vast majority of
# large-cap commercial Chapter 11s. SDNY + Delaware alone are 60%+ of
# the $100M+ cases by deal value.
COMMERCIAL_BANKR_COURTS = [
    ("deb",  "Delaware"),
    ("nysb", "SDNY"),
    ("txsb", "SD Texas"),
    ("cacb", "C.D. California"),
    ("ilnb", "N.D. Illinois"),
    ("gasb", "S.D. Georgia"),
    ("mab",  "Massachusetts"),
]

# Case-name patterns that suggest a commercial debtor (vs individual).
# Liberal pattern — false positives get filtered downstream by the
# verify-primary-doc review step. Single-letter words excluded.
_COMMERCIAL_TOKENS = re.compile(
    r"\b(corp|corporation|inc|incorporated|llc|l\.l\.c\.?|"
    r"holdings|holding|group|plc|co\.?|company|"
    r"ltd|limited|lp|l\.p\.?|llp|"
    r"partners|partnership|enterprises|industries|systems|"
    r"resources|capital|energy|media|networks|telecom|pharmaceuticals)\b",
    re.I,
)


def is_commercial(case_name: str) -> bool:
    """Filter individual bankruptcies (which dominate filing volume) from
    commercial ones (which are the special-situations universe)."""
    if not case_name:
        return False
    # Individual-filer name patterns to drop:
    #   "Last, First [Middle]"
    #   "First Last and Spouse Name"
    #   "First M. Last, Suffix" (Mecom III)
    if "," in case_name and len(case_name) < 60:
        return False
    if " and " in case_name.lower() and len(case_name) < 70:
        return False
    return bool(_COMMERCIAL_TOKENS.search(case_name))


def collapse_joint_filings(records: list[dict]) -> list[dict]:
    """Joint Chapter 11s file each subsidiary as its own docket. Collapse
    them to the parent's filing by grouping on (court_id, filed_date,
    root_name) where root_name strips trailing corporate-form tokens.
    Keeps the longest-name member as the representative so e.g.
    'GVO Holdings Group LLC' wins over 'GVO Topco LLC'."""
    def root(name: str) -> str:
        # Take first 1-3 distinctive words; strip the corporate-form tail
        n = re.sub(r"\s+(LLC|L\.L\.C\.?|Inc\.?|Corp\.?|Holdings?|Group|"
                   r"Ltd|Limited|Co\.?|P\.?C\.?|LP|L\.P\.?)\b.*$",
                   "", name, flags=re.I).strip()
        parts = n.split()
        return " ".join(parts[:3]).upper() if parts else name.upper()

    groups: dict[tuple[str, str, str], list[dict]] = {}
    for r in records:
        key = (r.get("court_id", ""), r.get("filed", ""),
               root(r.get("name", "")))
        groups.setdefault(key, []).append(r)
    out: list[dict] = []
    for key, members in groups.items():
        # Pick the longest-name member (usually the parent)
        rep = max(members, key=lambda x: len(x.get("name", "")))
        if len(members) > 1:
            rep["query_note"] = (
                f"{rep['query_note']}; joint filing of "
                f"{len(members)} affiliated debtors: " +
                ", ".join(m["name"][:50] for m in members[:5]) +
                ("..." if len(members) > 5 else "")
            )
        out.append(rep)
    return out


def fetch_court_page(court_id: str, page: int = 1,
                     retries: int = 3) -> dict:
    """One page of search results from a given bankruptcy court."""
    params = {
        "type":        "r",            # RECAP
        "court":       court_id,
        "order_by":    "dateFiled desc",
        "page":        str(page),
        "page_size":   "50",
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, headers=headers, timeout=30)
            if r.status_code == 429:
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! CourtListener {court_id} failed after "
                      f"{retries} attempts: {exc}", file=sys.stderr)
                return {}
            time.sleep(delay); delay *= 2
    return {}


def normalize_hit(hit: dict, court_label: str, fetched_at: str) -> dict:
    """Map CourtListener search-hit JSON → inbox-record shape."""
    docket_id = hit.get("docket_id") or ""
    return {
        "tier":        "tier_s",
        "query_label": "tier_s.bankruptcy_11",
        "query_note":  (f"New Chapter {hit.get('chapter','?')} filing in "
                        f"{court_label}; verify whether DIP / plan / 363 "
                        "trajectory makes equity worth analyzing"),
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "name":        hit.get("caseName") or hit.get("case_name_full") or "",
        "form":        f"Chapter {hit.get('chapter','?')} filing",
        "form_code":   f"CH{hit.get('chapter','?')}",
        "accession":   f"docket-{docket_id}",
        "filed":       hit.get("dateFiled") or "",
        "jurisdiction": "US",
        "court_id":    hit.get("court_id") or "",
        "docket_no":   hit.get("docketNumber") or "",
        "assigned_to": hit.get("assignedTo") or "",
        "debtor_firm": hit.get("firm") or "",
        "url":         (f"https://www.courtlistener.com"
                        f"{hit.get('docket_absolute_url','')}"
                        if hit.get("docket_absolute_url") else ""),
        "source":      "CourtListener-RECAP",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"pacer_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str,
                                   ensure_ascii=False))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(cutoff: date) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    all_records: list[dict] = []
    print(f"Polling CourtListener for filings >= {cutoff.isoformat()}...")
    for court_id, court_label in COMMERCIAL_BANKR_COURTS:
        page = 1
        court_kept = 0
        while True:
            resp = fetch_court_page(court_id, page=page)
            hits = resp.get("results") or []
            if not hits:
                break
            stop = False
            for h in hits:
                filed = (h.get("dateFiled") or "")[:10]
                try:
                    filed_d = date.fromisoformat(filed) if filed else None
                except ValueError:
                    filed_d = None
                if filed_d and filed_d < cutoff:
                    stop = True
                    break
                # Chapter 11 (corporate reorg) and 15 (cross-border) only.
                ch = str(h.get("chapter") or "")
                if ch not in ("11", "15"):
                    continue
                # Even Ch 11 has occasional individuals (Mecom III, etc).
                # is_commercial() drops those without losing real corps.
                name = h.get("caseName") or ""
                if not is_commercial(name):
                    continue
                all_records.append(
                    normalize_hit(h, court_label, fetched_at))
                court_kept += 1
            # v4 API caps page_size at 20 regardless of what we request,
            # so iterate by page until we hit the cutoff or run dry.
            if stop or len(hits) < 20:
                break
            page += 1
            if page > 50:        # safety cap (1000 records / court)
                break
            time.sleep(0.20)
        print(f"  {court_id:5s} ({court_label[:20]:20s})  {court_kept:3d} commercial 11/15 filings kept")
        time.sleep(0.20)

    if all_records:
        # Collapse joint Chapter 11s of multi-debtor filings (e.g.
        # GVO Holdings + Topco + Partners + Still Waters + Urban +
        # Sweetgrass — all one case, one universe entry).
        n_raw = len(all_records)
        all_records = collapse_joint_filings(all_records)
        if len(all_records) < n_raw:
            print(f"\nCollapsed {n_raw} raw filings to {len(all_records)} "
                  f"unique cases (joint Ch 11 dedup)")
        counts = write_inbox(all_records)
        print(f"Wrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    else:
        print("\nNo commercial Chapter 11/15 hits in window.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date",
                    type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=date.today())
    ap.add_argument("--days-back", type=int, default=1,
                    help="Window size in days (default 1 = today only)")
    args = ap.parse_args()

    cutoff = args.date - timedelta(days=args.days_back)
    total = poll(cutoff)
    print(f"\nDone. {total} records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
