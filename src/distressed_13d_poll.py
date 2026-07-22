#!/usr/bin/env python3
"""
distressed_13d_poll.py — loan-to-own control-conversion tracker.

The highest-signal sourcing angle for post-reorg equity: when a DISTRESSED /
credit fund that specialises in fulcrum-debt loan-to-own (Oaktree, Apollo,
Centerbridge, Silver Point, Angelo Gordon, Cerberus, Elliott, Aurelius,
Monarch, Mudrick, Ares, Davidson Kempner, King Street, GoldenTree, …) files a
**Schedule 13D on an equity**, it usually means they converted debt to an
equity CONTROL stake through a restructuring. That names the best post-reorgs
by who now owns them — near-real-time, and independent of the emergence-
phrase funnel.

Mechanism: for each fund CIK we read its EDGAR submissions feed, keep recent
SC 13D / 13G filings, and recover the SUBJECT company (name + CIK) from the
filing's SGML header. 13D = active/control intent (strongest); 13G = passive
>5% stake (still a smart-money tell).

Output: data/inbox/<filed>/tier_s/distressed13d_<accession>.json,
sub-labels tier_s.distressed_13d / .distressed_13g.

Usage:
    python -m src.distressed_13d_poll --days-back 120
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
    print("Install requests", file=sys.stderr); sys.exit(1)

try:
    from src.edgar_util import resolve_cik_to_ticker
except Exception:                      # pragma: no cover
    def resolve_cik_to_ticker(_):
        return None

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
UA = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Loan-to-own / distressed-credit funds (CIK → name). Extend freely — the
# poller is CIK-driven. These specialise in fulcrum debt and debt-to-equity
# control through restructurings, so their 13D is the post-reorg control tell.
DISTRESSED_FUNDS: dict[str, str] = {
    "0001791786": "Elliott Investment Management",
    "0001169161": "Silver Point Capital",
    "0001403525": "Oaktree Capital",
    "0001735375": "Apollo Management",
    "0001719710": "Centerbridge Partners",
    "0000937789": "Angelo Gordon",
    "0002027951": "Cerberus Capital",
    "0001820727": "Mudrick Capital",
    "0001362948": "Aurelius Capital",
    "0001281084": "Monarch Alternative",
    "0001176948": "Ares Management",
    "0000937617": "Davidson Kempner",
    "0001048162": "King Street Capital",
    "0001278951": "GoldenTree Asset",
    "0001727012": "Diameter Capital",
    "0001695885": "Brigade Capital",
    "0001407737": "Solus Alternative",
    "0002007642": "Anchorage Capital",
    "0001525362": "HG Vora",
    "0001074034": "Canyon Capital",
    "0001040592": "Marathon Asset",
    "0001925309": "Sixth Street",
}

_SUBJECT = re.compile(
    r"SUBJECT COMPANY:.*?COMPANY CONFORMED NAME:\s*(.+?)\s*\n.*?"
    r"CENTRAL INDEX KEY:\s*(\d+)", re.S)


def _submissions(cik: int) -> dict:
    try:
        r = requests.get(SUBMISSIONS.format(cik=cik), headers=UA, timeout=20)
        if r.status_code != 200:
            return {}
        return r.json()
    except (requests.RequestException, ValueError):
        return {}


def _subject(cik: int, accession: str) -> tuple[str, str]:
    """(name, cik) of the 13D's subject company, from the SGML header."""
    accn = accession.replace("-", "")
    url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/"
           f"{accession}.txt")
    try:
        r = requests.get(url, headers=UA, timeout=20, stream=True)
        head = (r.raw.read(6000, decode_content=True) or b"").decode(
            "utf-8", errors="ignore")
    except (requests.RequestException, ValueError):
        return "", ""
    m = _SUBJECT.search(head)
    return (m.group(1).strip(), m.group(2)) if m else ("", "")


def poll(days_back: int) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    print(f"Scanning {len(DISTRESSED_FUNDS)} distressed funds for 13D/13G "
          f"since {cutoff}...")
    records: list[dict] = []
    for fcik, fname in DISTRESSED_FUNDS.items():
        j = _submissions(int(fcik))
        rec = j.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        accs = rec.get("accessionNumber", [])
        hits = 0
        for i, f in enumerate(forms):
            if not f.startswith(("SC 13D", "SC 13G")):
                continue
            if i >= len(dates) or dates[i] < cutoff:
                continue
            acc = accs[i]
            sname, scik = _subject(int(fcik), acc)
            if not sname:
                continue
            active = f.startswith("SC 13D")
            sub = "distressed_13d" if active else "distressed_13g"
            stake = "CONTROL (13D)" if active else "passive >5% (13G)"
            tk = resolve_cik_to_ticker(scik) if scik else None
            records.append({
                "tier": "tier_s",
                "query_label": f"tier_s.{sub}",
                "query_note": (
                    f"{fname} filed {f} on {sname} — a distressed/loan-to-own "
                    f"fund taking a {stake} equity stake. Classic debt-to-"
                    f"equity control signal: verify whether the stake came "
                    f"through a restructuring / post-reorg distribution."),
                "distressed_fund": fname,
                "form": f,
                "cik": scik,
                "ticker": (tk.upper() if tk else ""),
                "isin": None,
                "name": sname,
                "form_code": f,
                "accession": acc,
                "filed": dates[i],
                "jurisdiction": "US",
                "url": (f"https://www.sec.gov/cgi-bin/browse-edgar?action="
                        f"getcompany&CIK={scik}&type=SC+13D" if scik else ""),
                "source": "EDGAR-distressed13D",
                "fetched_at": fetched_at,
            })
            hits += 1
            time.sleep(0.1)
        if hits:
            print(f"  {fname:32s} {hits:>3d} recent 13D/13G")
        time.sleep(0.1)
    if records:
        for r in records:
            d = INBOX / r["filed"][:10] / r["tier"]
            d.mkdir(parents=True, exist_ok=True)
            slug = (r["accession"] or "no-id").replace("/", "_")
            (d / f"distressed13d_{slug}.json").write_text(
                json.dumps(r, indent=2, sort_keys=True, default=str))
        n13d = sum(1 for r in records if "13d" in r["query_label"])
        print(f"\nWrote {len(records)} records ({n13d} active 13D control "
              f"stakes, {len(records)-n13d} passive 13G)")
    else:
        print("\nNo distressed-fund 13D/13G filings in window.")
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # A loan-to-own control stake is a rare, DURABLE signal (it doesn't go
    # stale in a quarter), so the tracker looks back ~2 years by default.
    ap.add_argument("--days-back", type=int, default=730)
    args = ap.parse_args()
    total = poll(args.days_back)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
