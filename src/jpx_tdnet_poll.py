#!/usr/bin/env python3
"""
jpx_tdnet_poll.py — daily TSE/JPX TDnet poller for Japanese special-situation events.

Closes the Japanese leg of comprehensive coverage. EDINET v2 (FSA's
electronic disclosure for securities filings) now requires a paid
subscription key (the v1 free endpoint 403s). TDnet — TSE's mandated
Timely Disclosure network — is the public, free, daily-paginated
disclosure index for all TSE-listed companies and is the canonical
source for the special-situation events we care about (tender
offers, MBOs, demergers, civil-rehabilitation, etc.).

TDnet index pages live at:
    https://www.release.tdnet.info/inbs/I_list_NNN_YYYYMMDD.html
where NNN is the 1-based page number (100 rows per page). The index
is plain HTML, UTF-8 encoded, with a fixed-column <table> layout —
no JavaScript, no bot detection, no auth.

Each row exposes: time (HH:MM), 5-character TSE code (4-digit ticker
+ check char), issuer name, headline, PDF link. The 4-character
ticker prefix is the TSE-listed code (the trailing 0 / A0 / etc.
is for internal numbering).

Output schema mirrors data/inbox/<date>/<tier>/<id>.json so
inbox_promote.py picks up Japanese hits the same way it handles
EDGAR/NSM/SEDAR+.

Usage:
    python -m src.jpx_tdnet_poll                       # poll today
    python -m src.jpx_tdnet_poll --date 2026-06-19     # specific day
    python -m src.jpx_tdnet_poll --days-back 7         # last week
"""

from __future__ import annotations

import argparse
import json
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
TDNET_BASE = "https://www.release.tdnet.info/inbs"

HEADERS = {
    "User-Agent": "cyclepapa-screener research@example.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
}

# Japanese headline regex → (tier, sub_query_label, note).
# Ordered by specificity: most-specific patterns first since first
# match wins. Native-language search is necessary because TDnet
# headlines are Japanese; the English glosses are for the framework.
HEADLINE_PATTERNS: list[tuple[str, str, str, str]] = [
    # ---- Tier-S: hard restructuring events (always promote) ----
    (r"公開買付",            "tier_s", "tob",
     "tender offer (TOB / 公開買付) — bid in progress"),
    (r"ＭＢＯ|MBO|ﾏﾈｼﾞﾒﾝﾄ",   "tier_s", "mbo",
     "management buyout (MBO)"),
    (r"株式交換契約",        "tier_s", "share_exchange",
     "share exchange contract (M&A by stock swap)"),
    (r"株式移転計画",        "tier_s", "share_transfer",
     "share transfer plan (holding co restructuring)"),
    (r"会社分割",            "tier_s", "demerger",
     "company split / demerger"),
    (r"吸収合併",            "tier_s", "merger_absorption",
     "merger by absorption"),
    (r"民事再生",            "tier_s", "civil_rehabilitation",
     "civil rehabilitation (Japan's Chapter 11 lite)"),
    (r"会社更生",            "tier_s", "corporate_reorganization",
     "corporate reorganisation (Japan's Chapter 11)"),
    (r"特別清算",            "tier_s", "special_liquidation",
     "special liquidation"),
    (r"上場廃止",            "tier_s", "delisting",
     "delisting"),
    (r"主要株主の?異動",      "tier_s", "major_shareholder_change",
     "change in major shareholders"),
    (r"支配株主",            "tier_s", "controlling_shareholder",
     "controlling shareholder transition"),
    (r"第三者割当",          "tier_s", "third_party_allotment",
     "third-party share allocation (private placement)"),
    (r"募集株式の発行",       "tier_s", "public_offering",
     "public share offering"),
    # ---- Revealed-preference / governance signals ----
    (r"自己株式の?取得",      "rev_pref", "buyback",
     "share buyback (自己株式取得) — Lakonishok-Lee analogue at the corp level"),
    (r"自己株式の?消却",      "rev_pref", "share_cancellation",
     "share cancellation (自己株式消却)"),
    (r"大量保有報告",         "rev_pref", "large_holding",
     "5pct large-holding report (EDINET-side; cross-reference)"),
    # ---- Red flags ----
    (r"継続企業の前提",       "red_flag", "going_concern",
     "going-concern doubt (継続企業の前提)"),
    (r"業績(?:予想|予測)?修正", "red_flag", "earnings_revision",
     "earnings forecast revision — verify whether downward"),
    (r"特別損失",            "red_flag", "extraordinary_loss",
     "extraordinary loss"),
]
HEADLINE_PATTERNS_COMPILED = [(re.compile(p), tier, sub, note)
                              for p, tier, sub, note in HEADLINE_PATTERNS]


def fetch_page(day: date, page: int, retries: int = 3) -> str | None:
    """Fetch one TDnet index page. Returns HTML on success, None if no
    such page exists (404 = past the last page)."""
    url = (f"{TDNET_BASE}/I_list_{page:03d}_"
           f"{day.strftime('%Y%m%d')}.html")
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                time.sleep(delay); delay *= 2
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! TDnet failed after {retries} attempts: {exc}",
                      file=sys.stderr)
                return None
            time.sleep(delay); delay *= 2
    return None


# Each result row: <tr> with <td>time</td><td>code</td><td>name</td>
# <td><a href="pdf">headline</a></td><td>XBRL link</td><td>update</td>
_ROW_RE = re.compile(
    r"<tr[^>]*>\s*"
    r"<td[^>]*>\s*(\d{2}:\d{2})\s*</td>\s*"
    r"<td[^>]*>\s*([A-Z0-9]{4,5})\s*</td>\s*"
    r"<td[^>]*>\s*([^<]+?)\s*</td>\s*"
    r"<td[^>]*>\s*<a\s+[^>]*href=\"([^\"]+)\"[^>]*>([^<]+?)</a>",
    re.DOTALL,
)


def parse_page(html: str, day: date) -> list[dict]:
    """Extract disclosure rows from one TDnet index page."""
    rows: list[dict] = []
    for m in _ROW_RE.finditer(html):
        hhmm, code, issuer, pdf_rel, headline = m.groups()
        ticker_4 = code[:4]
        pdf_url = (f"{TDNET_BASE}/{pdf_rel}"
                   if not pdf_rel.startswith("http") else pdf_rel)
        rows.append({
            "time": hhmm,
            "code": code,
            "ticker": ticker_4,
            "name": issuer.strip(),
            "headline": headline.strip(),
            "filed": day.isoformat(),
            "url": pdf_url,
        })
    return rows


def fetch_day(day: date) -> list[dict]:
    """Fetch all pages for one day."""
    out: list[dict] = []
    for page in range(1, 50):     # cap at 50 pages = 5000 rows
        html = fetch_page(day, page)
        if html is None:
            break
        rows = parse_page(html, day)
        if not rows:
            break
        out.extend(rows)
        # TDnet rate limit — be polite
        time.sleep(0.2)
    return out


def classify(rec: dict) -> tuple[str, str, str] | None:
    """Apply headline regex. Returns (tier, sub_query_label, note) or None."""
    h = rec.get("headline", "")
    if not h:
        return None
    for pat, tier, sub, note in HEADLINE_PATTERNS_COMPILED:
        if pat.search(h):
            return tier, sub, note
    return None


def normalize_hit(rec: dict, tier: str, sub: str, note: str,
                  fetched_at: str) -> dict:
    """Inbox-record shape (same fields as edgar/nsm/sedar hits)."""
    pdf_basename = rec["url"].rsplit("/", 1)[-1].split(".")[0]
    accession = (pdf_basename or
                 f"{rec['code']}_{rec['filed']}_{rec['time']}".replace(":", ""))
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      rec["ticker"],      # 4-digit TSE code
        "isin":        None,
        "name":        rec["name"],
        "form":        rec["headline"][:140],
        "form_code":   "",
        "accession":   accession,
        "filed":       rec["filed"],
        "jurisdiction": "JP",
        "url":         rec["url"],
        "source":      "TDnet",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        sub = r["query_label"].split(".")[-1]
        slug = (r["accession"] or "no-id").replace("/", "_")
        path = tier_dir / f"tdnet_{slug}_{sub}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str,
                                   ensure_ascii=False))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll_day(day: date) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print(f"\nPolling TDnet for {day.isoformat()}...")
    rows = fetch_day(day)
    print(f"  {len(rows)} disclosures retrieved across all pages")
    hits: list[dict] = []
    classified: dict[str, int] = {}
    for r in rows:
        cls = classify(r)
        if cls is None:
            continue
        tier, sub, note = cls
        classified[sub] = classified.get(sub, 0) + 1
        hits.append(normalize_hit(r, tier, sub, note, fetched_at))
    print(f"  {len(hits)} matched a special-situation pattern:")
    for sub, n in sorted(classified.items(), key=lambda x: -x[1]):
        print(f"    {sub:30s} {n}")
    if hits:
        counts = write_inbox(hits)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date",
                    type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
                    default=date.today())
    ap.add_argument("--days-back", type=int, default=0,
                    help="Poll a range of days ending at --date")
    args = ap.parse_args()
    total = 0
    if args.days_back > 0:
        for n in range(args.days_back, -1, -1):
            total += poll_day(args.date - timedelta(days=n))
    else:
        total += poll_day(args.date)
    print(f"\nDone. {total} records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
