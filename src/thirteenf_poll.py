#!/usr/bin/env python3
"""
thirteenf_poll.py — 13F institutional-holdings mirror (smart-money sourcing).

Mirrors the revealed preference of known special-situations funds. Every
quarter, 13F-HR filers disclose their long US-equity book. Diffing a
practitioner fund's latest 13F against its prior one surfaces NEW
positions and MATERIAL ADDS — the institutional-level analogue of the
Form 4 (insider) and SC 13D (5pct activist) signals we already source.

When multiple special-sits funds independently open the same name in
the same quarter, that is among the highest-conviction open-source
signals available: it is revealed preference from the exact cohort of
managers whose playbook this framework encodes.

Watchlist = practitioner funds already named in event_taxonomy.md
(Elliott, Pershing, Third Point, Icahn, Trian, Starboard, JANA,
Sculptor, Silver Point, Corvex, Greenlight, Pentwater, Saba, Ancora,
Engine, Legion). Extend WATCHLIST freely — the poller is CIK-driven.

Output: data/inbox/<filing-date>/rev_pref/13f_<fund>_<cusip>.json,
sub-labels rev_pref.thirteenf_new_position / rev_pref.thirteenf_add.

Usage:
    python -m src.thirteenf_poll                 # diff latest vs prior 13F
    python -m src.thirteenf_poll --min-value-usd 5000000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
HEADERS_XML = {"User-Agent": USER_AGENT}

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"

# Practitioner special-situations funds — CIK → display name.
# Resolved from EDGAR company search (13F-HR filers). Extend as needed.
WATCHLIST: dict[str, str] = {
    "0001791786": "Elliott Investment Management",
    "0001336528": "Pershing Square Capital",
    "0001040273": "Third Point",
    "0000881188": "Icahn (High River / Icahn Enterprises)",
    "0001345472": "Trian Fund Management",
    "0001517137": "Starboard Value",
    "0001159159": "JANA Partners",
    "0001054587": "Sculptor Capital",
    "0001169161": "Silver Point Capital",
    "0001535472": "Corvex Management",
    "0001079114": "Greenlight Capital",
    "0001425851": "Pentwater Capital",
    "0001510281": "Saba Capital",
    "0001446114": "Ancora Advisors",
    "0001665590": "Engine Capital",
    "0001560207": "Legion Partners",
}

DEFAULT_MIN_VALUE_USD = 3_000_000    # 13F values are in USD (post-2023 rule)
# 13F <value> historically reported in $000s; post Jan-2023 amendments in
# whole dollars. We normalise heuristically below.


def get_recent_13f_filings(cik: str) -> list[dict]:
    """Return the two most-recent 13F-HR filings for a CIK, newest first."""
    url = SUBMISSIONS.format(cik=cik)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        d = r.json()
    except requests.RequestException:
        return []
    rec = (d.get("filings") or {}).get("recent") or {}
    forms = rec.get("form", [])
    accs = rec.get("accessionNumber", [])
    dates = rec.get("filingDate", [])
    out = []
    for i, f in enumerate(forms):
        if f == "13F-HR":
            out.append({"accession": accs[i], "filed": dates[i]})
        if len(out) >= 2:
            break
    return out


def fetch_infotable(cik: str, accession: str) -> list[dict]:
    """Parse the 13F information table into holdings records."""
    acc = accession.replace("-", "")
    base = ARCHIVE.format(cik=int(cik), acc=acc)
    try:
        idx = requests.get(base + "/index.json", headers=HEADERS,
                           timeout=25).json()
    except requests.RequestException:
        return []
    info_name = None
    for item in (idx.get("directory") or {}).get("item", []):
        n = item.get("name", "")
        low = n.lower()
        if "infotable" in low or (low.endswith(".xml")
                                  and "primary_doc" not in low
                                  and "form13" not in low):
            info_name = n
            break
    if not info_name:
        return []
    try:
        xml = requests.get(base + "/" + info_name, headers=HEADERS_XML,
                           timeout=25).text
    except requests.RequestException:
        return []
    holdings = []
    for m in re.finditer(r"<(?:\w+:)?infoTable>(.*?)</(?:\w+:)?infoTable>",
                         xml, re.DOTALL | re.I):
        block = m.group(1)
        issuer = _tag(block, "nameOfIssuer")
        cusip = _tag(block, "cusip")
        title = _tag(block, "titleOfClass")
        value = _tag(block, "value")
        shares = _tag(block, "sshPrnamt")
        if not cusip:
            continue
        try:
            value_num = float(value) if value else 0.0
        except ValueError:
            value_num = 0.0
        try:
            shares_num = float(shares) if shares else 0.0
        except ValueError:
            shares_num = 0.0
        holdings.append({
            "issuer": (issuer or "").strip(),
            "cusip": cusip.strip().upper(),
            "title": (title or "").strip(),
            "value": value_num,
            "shares": shares_num,
        })
    return holdings


def _tag(block: str, tag: str) -> str:
    m = re.search(rf"<(?:\w+:)?{tag}>(.*?)</(?:\w+:)?{tag}>", block,
                  re.DOTALL | re.I)
    return m.group(1).strip() if m else ""


def normalise_value(v: float) -> float:
    """13F <value> is in whole USD post-Jan-2023, $000s before. Heuristic:
    values under ~1e7 are almost certainly $000s (a $10B position would
    be 10,000,000 in thousands). We keep the raw figure but the threshold
    comparison uses the larger of (v, v*1000) to avoid missing real
    positions from older filings — conservative (over-includes)."""
    return v


# Exclude non-special-sits instruments: ETFs, index funds, options.
# Special-sits sourcing wants single-name equity positions.
_ETF_ISSUER = re.compile(
    r"\b(ETF|SPDR|ISHARES|INVESCO QQQ|VANGUARD|SER TR|SERIES TR|"
    r"EXCHANGE TRADED|INDEX|TRUST\b(?!.*HLDG)|SELECT SECTOR|"
    r"US NATURAL GAS|COPPER AND METALS)\b", re.I)
# Option holdings: 13F reports them with a title like "PUT"/"CALL" or an
# issuer string carrying an OCC option code (YYMMDD + P/C + 8-digit strike).
_OPTION_TITLE = re.compile(r"\b(PUT|CALL)\b", re.I)
_OPTION_ISSUER = re.compile(r"\d{6}[PC]\d{8}\b")


def is_single_name_equity(h: dict) -> bool:
    issuer = h.get("issuer", "")
    title = h.get("title", "")
    if _OPTION_TITLE.search(title) or _OPTION_ISSUER.search(issuer):
        return False
    if _ETF_ISSUER.search(issuer):
        return False
    return True


def diff_holdings(latest: list[dict], prior: list[dict]) -> dict:
    """Return {new: [...], adds: [...]} comparing latest vs prior by CUSIP.
    Restricted to single-name equity (no ETFs, index funds, options).
    Collapses multiple share-class / lot rows for the same CUSIP."""
    def collapse(holdings):
        by_cusip: dict[str, dict] = {}
        for h in holdings:
            if not is_single_name_equity(h):
                continue
            c = h["cusip"]
            if c in by_cusip:
                by_cusip[c]["shares"] += h["shares"]
                by_cusip[c]["value"] += h["value"]
            else:
                by_cusip[c] = dict(h)
        return by_cusip

    latest_by = collapse(latest)
    prior_by = collapse(prior)
    new_positions = []
    material_adds = []
    for cusip, h in latest_by.items():
        p = prior_by.get(cusip)
        if p is None:
            new_positions.append(h)
        elif p["shares"] > 0 and h["shares"] > p["shares"] * 1.25:
            h2 = dict(h)
            h2["prior_shares"] = p["shares"]
            h2["pct_increase"] = round(
                (h["shares"] / p["shares"] - 1) * 100, 1)
            material_adds.append(h2)
    return {"new": new_positions, "adds": material_adds}


_SPAC_ISSUER = re.compile(
    r"\b(ACQUISITION CORP|ACQUISITION CO\b|ACQ CORP|"
    r"ACQ CO\b|SPAC|BLANK CHECK)\b", re.I)


def normalize_hit(fund_cik: str, fund_name: str, filed: str,
                  holding: dict, kind: str, fetched_at: str) -> dict:
    is_new = kind == "new"
    is_spac = bool(_SPAC_ISSUER.search(holding.get("issuer", "")))
    # SPACs held by these funds are K4 trust-arb, not deep-value activism —
    # route to a distinct sub-label so the single-name equity consensus
    # signal (the high-conviction one) isn't drowned out.
    if is_spac:
        sub = "thirteenf_spac_arb"
    elif is_new:
        sub = "thirteenf_new_position"
    else:
        sub = "thirteenf_add"
    val = holding["value"]
    # Present value both ways (whole-$ and $000s) so downstream isn't misled
    val_str = (f"${val:,.0f} (or ${val * 1000:,.0f} if filed in $000s)")
    if is_new:
        note = (f"{fund_name} opened a NEW position in {holding['issuer']} "
                f"({holding['title']}); {val_str}; "
                f"{holding['shares']:,.0f} shares. Institutional revealed "
                f"preference from a named special-sits fund.")
    else:
        note = (f"{fund_name} ADDED to {holding['issuer']} "
                f"(+{holding.get('pct_increase','?')}% shares to "
                f"{holding['shares']:,.0f}); {val_str}.")
    return {
        "tier":        "rev_pref",
        "query_label": f"rev_pref.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      None,
        "isin":        None,
        "cusip":       holding["cusip"],
        "name":        holding["issuer"],
        "form":        f"13F-HR ({fund_name})",
        "form_code":   "13F-HR",
        "accession":   f"13f-{fund_cik}-{holding['cusip']}-{filed.replace('-','')}",
        "filed":       filed,
        "jurisdiction": "US",
        "url":         (f"https://www.sec.gov/cgi-bin/browse-edgar?"
                        f"action=getcompany&CIK={fund_cik}&type=13F-HR"),
        "fund_name":   fund_name,
        "fund_cik":    fund_cik,
        "position_value": val,
        "position_shares": holding["shares"],
        "source":      "EDGAR-13F",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")[:70]
        path = tier_dir / f"13f_{slug}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(min_value_usd: float) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print(f"Mirroring {len(WATCHLIST)} special-sits funds' 13F filings...")
    all_records: list[dict] = []
    # Track cross-fund overlap: cusip -> set of fund names opening it
    new_by_cusip: dict[str, list[str]] = defaultdict(list)

    for cik, fund_name in WATCHLIST.items():
        filings = get_recent_13f_filings(cik)
        if len(filings) < 2:
            print(f"  {fund_name[:30]:30s} (< 2 13F filings; skip)")
            time.sleep(0.15)
            continue
        latest = fetch_infotable(cik, filings[0]["accession"])
        prior = fetch_infotable(cik, filings[1]["accession"])
        if not latest:
            print(f"  {fund_name[:30]:30s} (no info table; skip)")
            time.sleep(0.15)
            continue
        diff = diff_holdings(latest, prior)
        # Filter by value threshold (accept if either interpretation clears)
        def clears(h):
            v = h["value"]
            return v >= min_value_usd or v * 1000 >= min_value_usd
        new_kept = [h for h in diff["new"] if clears(h)]
        adds_kept = [h for h in diff["adds"] if clears(h)]
        for h in new_kept:
            all_records.append(normalize_hit(cik, fund_name,
                               filings[0]["filed"], h, "new", fetched_at))
            new_by_cusip[h["cusip"]].append(fund_name)
        for h in adds_kept:
            all_records.append(normalize_hit(cik, fund_name,
                               filings[0]["filed"], h, "add", fetched_at))
        print(f"  {fund_name[:30]:30s} {len(new_kept):3d} new / "
              f"{len(adds_kept):3d} adds  "
              f"(filed {filings[0]['filed']})")
        time.sleep(0.20)

    # Flag cross-fund conviction: same CUSIP opened by >= 2 DISTINCT funds
    consensus = {c: sorted(set(funds)) for c, funds in new_by_cusip.items()
                 if len(set(funds)) >= 2}
    if consensus:
        print("\n  ⚑ CROSS-FUND CONSENSUS (>=2 distinct funds opened same name):")
        for cusip, funds in consensus.items():
            issuer = next((r["name"] for r in all_records
                          if r.get("cusip") == cusip), cusip)
            print(f"      {issuer[:35]:35s} {', '.join(funds)}")
            for r in all_records:
                if r.get("cusip") == cusip:
                    r["cross_fund_consensus"] = funds
                    if "CROSS-FUND CONSENSUS" not in r["query_note"]:
                        r["query_note"] = (f"[CROSS-FUND CONSENSUS: "
                                           f"{len(funds)} distinct funds: "
                                           f"{', '.join(funds)}] "
                                           + r["query_note"])

    if all_records:
        counts = write_inbox(all_records)
        print(f"\nWrote {len(all_records)} records across "
              f"{len(counts)} day/tier buckets")
    else:
        print("\nNo qualifying new positions or adds.")
    return len(all_records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-value-usd", type=float,
                    default=DEFAULT_MIN_VALUE_USD)
    args = ap.parse_args()
    total = poll(args.min_value_usd)
    print(f"\nDone. {total} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
