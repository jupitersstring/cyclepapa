#!/usr/bin/env python3
"""
cluster_sells.py — Form 4 cluster-SELL detector (Wirecard / SVB red flag).

Implements keeper #3 from output/process_improvements_keepers.md.

Sibling to cluster_buys.py — same EDGAR Form 4 mechanic but flipped.
Wirecard insiders sold heavily in late 2019 before the June 2020
collapse; SVB CEO sold $3.6m on Feb 27 2023, 10 days before the run.
Clusters of S-code (open-market sale) Form 4 filings within a short
window are the canonical insider-disclosed-bad-news pattern.

This file is additive to cluster_buys.py — it does NOT modify the
existing buy-side detector. The two run independently:
- cluster_buys.py: P-code (purchase) detector → tier_s.cluster_buys
- cluster_sells.py: S-code (open-market sale) → red_flag.cluster_sells

Post-Feb 2023 Rule 10b5-1 changes: Form 4 reports must check a box
if the trade was made under a 10b5-1 plan. Unplanned sells within 60
days of a material event are the highest-signal cluster pattern.

Output: data/inbox/<filing-date>/red_flag/cluster_sells_<cik>_<window>.json.

Usage:
    python -m src.cluster_sells                       # 30-day lookback
    python -m src.cluster_sells --days-back 60        # wider lookback
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)
try:
    import yaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
CANDIDATES = REPO / "data" / "candidates"
INBOX = REPO / "data" / "inbox"

EDGAR_FTS = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"

USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT",
    "cyclepapa-cluster-sells research@example.com",
)
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
HEADERS_XML = {"User-Agent": USER_AGENT, "Accept": "application/xml"}

# Cluster thresholds — same Lakonishok-Lee-style filter as cluster_buys.
DEFAULT_MIN_INSIDERS = 2     # sells: lower bar than buys (any 2 insiders)
DEFAULT_CLUSTER_WINDOW_DAYS = 7
DEFAULT_MIN_USD_PER_TRADE = 50_000   # exclude tax-withholding noise
DEFAULT_LOOKBACK_DAYS = 60


@dataclass
class Form4Sale:
    cik: str
    issuer: str
    accession: str
    insider_name: str
    insider_role: str
    filed: str
    transaction_value_usd: float
    code: str
    is_10b5_1: bool


@dataclass
class SellCluster:
    issuer: str
    cik: str
    window_start: str
    window_end: str
    n_unique_insiders: int
    total_usd: float
    sales: list[Form4Sale]
    n_unplanned: int          # sells without 10b5-1 affirmative-defence cover


def fetch_form4_filings(cik: str, lookback_days: int) -> list[dict]:
    """List Form 4 filings for one CIK over the lookback window."""
    end = date.today()
    start = end - timedelta(days=lookback_days)
    params = {
        "forms": "4",
        "ciks": cik.zfill(10),
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
    }
    url = f"{EDGAR_FTS}?{urlencode(params)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json().get("hits", {}).get("hits", [])
    except requests.RequestException:
        return []


def fetch_form4_xml(cik: str, accession: str) -> str:
    """Fetch the primary Form 4 XML document for a filing."""
    acc_clean = accession.replace("-", "")
    # Form 4 primary doc is usually named "form4.xml" or "wf-form4_<n>.xml"
    # or "ownership.xml". Try the JSON index first to locate it.
    idx_url = f"{EDGAR_ARCHIVE}/{int(cik):d}/{acc_clean}/index.json"
    try:
        r = requests.get(idx_url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return ""
        idx = r.json()
        for item in (idx.get("directory") or {}).get("item", []):
            name = item.get("name", "")
            if name.endswith(".xml") and "form4" in name.lower():
                xml_url = f"{EDGAR_ARCHIVE}/{int(cik):d}/{acc_clean}/{name}"
                rx = requests.get(xml_url, headers=HEADERS_XML, timeout=20)
                if rx.status_code == 200:
                    return rx.text
        # Fall back: try ownership.xml
        for name in ("ownership.xml", "primary_doc.xml"):
            xml_url = f"{EDGAR_ARCHIVE}/{int(cik):d}/{acc_clean}/{name}"
            rx = requests.get(xml_url, headers=HEADERS_XML, timeout=20)
            if rx.status_code == 200:
                return rx.text
    except requests.RequestException:
        return ""
    return ""


_RX_TRANSACTION_CODE = re.compile(
    r"<transactionCode>([A-Z])</transactionCode>")
_RX_TRANSACTION_AMT = re.compile(
    r"<transactionShares>.*?<value>([\d.]+)</value>", re.DOTALL)
_RX_TRANSACTION_PRICE = re.compile(
    r"<transactionPricePerShare>.*?<value>([\d.]+)</value>", re.DOTALL)
_RX_RPT_OWNER_NAME = re.compile(
    r"<rptOwnerName>([^<]+)</rptOwnerName>")
_RX_IS_DIRECTOR = re.compile(r"<isDirector>(?:1|true)</isDirector>")
_RX_IS_OFFICER = re.compile(r"<isOfficer>(?:1|true)</isOfficer>")
_RX_OFFICER_TITLE = re.compile(r"<officerTitle>([^<]+)</officerTitle>")
_RX_10B5_1 = re.compile(
    r"<aff10b5One>(?:1|true)</aff10b5One>|"
    r"\baffirmativeDefenseDate\b", re.I)


def parse_form4_sale(xml: str, issuer_cik: str, issuer_name: str,
                     accession: str, filed: str) -> Form4Sale | None:
    """Parse the Form 4 XML and return a Form4Sale record IF the
    transaction is an open-market sale (S-code) above threshold."""
    if not xml:
        return None
    codes = _RX_TRANSACTION_CODE.findall(xml)
    if "S" not in codes:
        return None  # not a sale
    shares_m = _RX_TRANSACTION_AMT.search(xml)
    price_m = _RX_TRANSACTION_PRICE.search(xml)
    value_usd = 0.0
    if shares_m and price_m:
        try:
            value_usd = float(shares_m.group(1)) * float(price_m.group(1))
        except ValueError:
            value_usd = 0.0
    name_m = _RX_RPT_OWNER_NAME.search(xml)
    insider = name_m.group(1).strip() if name_m else "Unknown"
    title_m = _RX_OFFICER_TITLE.search(xml)
    role = title_m.group(1).strip() if title_m else (
        "Director" if _RX_IS_DIRECTOR.search(xml) else
        "Officer" if _RX_IS_OFFICER.search(xml) else "Insider")
    is_10b5_1 = bool(_RX_10B5_1.search(xml))
    return Form4Sale(
        cik=issuer_cik,
        issuer=issuer_name,
        accession=accession,
        insider_name=insider,
        insider_role=role,
        filed=filed,
        transaction_value_usd=value_usd,
        code="S",
        is_10b5_1=is_10b5_1,
    )


def candidate_ciks() -> list[tuple[str, str, str]]:
    """Pull (ticker, cik, name) from Tier-1+2 YAMLs that expose a CIK."""
    out = []
    for path in CANDIDATES.glob("*.yaml"):
        with path.open() as f:
            d = yaml.safe_load(f) or {}
        ticker = d.get("ticker")
        name = d.get("name", ticker)
        cik = (d.get("deal", {}) or {}).get("cik") or d.get("cik")
        if not cik and ticker:
            cik = resolve_ticker_to_cik(ticker)
        if cik:
            out.append((ticker, str(cik), name))
    return out


_TICKER_CIK_CACHE: dict[str, str] | None = None


def resolve_ticker_to_cik(ticker: str) -> str | None:
    global _TICKER_CIK_CACHE
    if _TICKER_CIK_CACHE is None:
        try:
            r = requests.get("https://www.sec.gov/files/company_tickers.json",
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            _TICKER_CIK_CACHE = {v["ticker"].upper(): str(v["cik_str"])
                                 for v in data.values()}
        except requests.RequestException:
            _TICKER_CIK_CACHE = {}
    return _TICKER_CIK_CACHE.get(ticker.upper())


def detect_clusters(sales: list[Form4Sale],
                    min_insiders: int = DEFAULT_MIN_INSIDERS,
                    window_days: int = DEFAULT_CLUSTER_WINDOW_DAYS,
                    min_usd: float = DEFAULT_MIN_USD_PER_TRADE,
                    ) -> list[SellCluster]:
    """Group sells by issuer + time window; flag clusters meeting bar."""
    sales = [s for s in sales if s.transaction_value_usd >= min_usd]
    by_issuer: dict[str, list[Form4Sale]] = defaultdict(list)
    for s in sales:
        by_issuer[s.cik].append(s)
    clusters: list[SellCluster] = []
    for cik, issuer_sales in by_issuer.items():
        issuer_sales.sort(key=lambda s: s.filed)
        for i, anchor in enumerate(issuer_sales):
            window = [anchor]
            try:
                anchor_d = date.fromisoformat(anchor.filed)
            except ValueError:
                continue
            for s in issuer_sales[i + 1:]:
                try:
                    sd = date.fromisoformat(s.filed)
                except ValueError:
                    continue
                if (sd - anchor_d).days <= window_days:
                    window.append(s)
                else:
                    break
            uniq = {s.insider_name for s in window
                    if s.insider_name and s.insider_name != "Unknown"}
            if len(uniq) >= min_insiders:
                clusters.append(SellCluster(
                    issuer=anchor.issuer,
                    cik=cik,
                    window_start=anchor.filed,
                    window_end=window[-1].filed,
                    n_unique_insiders=len(uniq),
                    total_usd=sum(s.transaction_value_usd for s in window),
                    sales=window,
                    n_unplanned=sum(1 for s in window if not s.is_10b5_1),
                ))
    # Deduplicate overlapping windows: keep the longest / highest-$ per issuer
    by_issuer_clusters: dict[str, SellCluster] = {}
    for c in clusters:
        if (c.cik not in by_issuer_clusters or
                c.total_usd > by_issuer_clusters[c.cik].total_usd):
            by_issuer_clusters[c.cik] = c
    return list(by_issuer_clusters.values())


def write_inbox(clusters: list[SellCluster], fetched_at: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in clusters:
        filed = c.window_end[:10] or date.today().isoformat()
        tier_dir = INBOX / filed / "red_flag"
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{c.cik}_{c.window_start}_{c.window_end}".replace("-", "")
        record = {
            "tier":        "red_flag",
            "query_label": "red_flag.cluster_sells",
            "query_note":  (f"Cluster sells: {c.n_unique_insiders} insiders "
                            f"sold ${c.total_usd:,.0f} between "
                            f"{c.window_start} and {c.window_end}; "
                            f"{c.n_unplanned} of {len(c.sales)} were NOT "
                            f"covered by 10b5-1 affirmative defence "
                            f"(post-Feb 2023 cooling-off rule)"),
            "cik":         c.cik,
            "ticker":      None,
            "isin":        None,
            "name":        c.issuer,
            "form":        "Cluster of Form 4 sells (S-code)",
            "form_code":   "FORM4_CLUSTER",
            "accession":   f"cluster-{slug}",
            "filed":       filed,
            "jurisdiction": "US",
            "url":         "",
            "n_unique_insiders": c.n_unique_insiders,
            "n_unplanned_10b5_1": c.n_unplanned,
            "total_usd":   c.total_usd,
            "sales":       [{"insider": s.insider_name,
                            "role": s.insider_role,
                            "value_usd": s.transaction_value_usd,
                            "is_10b5_1": s.is_10b5_1,
                            "filed": s.filed} for s in c.sales],
            "source":      "EDGAR-Form4-cluster-sells",
            "fetched_at":  fetched_at,
        }
        path = tier_dir / f"cluster_sells_{slug}.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str))
        key = f"{filed}/red_flag"
        counts[key] = counts.get(key, 0) + 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days-back", type=int, default=DEFAULT_LOOKBACK_DAYS)
    ap.add_argument("--min-insiders", type=int, default=DEFAULT_MIN_INSIDERS)
    ap.add_argument("--min-usd", type=float, default=DEFAULT_MIN_USD_PER_TRADE)
    ap.add_argument("--max-candidates", type=int, default=30,
                    help="Cap on number of Tier-1+2 candidates to scan "
                         "(EDGAR rate-limits apply)")
    args = ap.parse_args()

    fetched_at = datetime.utcnow().isoformat() + "Z"
    cands = candidate_ciks()[:args.max_candidates]
    print(f"Scanning {len(cands)} candidates for cluster-sells "
          f"(lookback {args.days_back}d)...")
    all_sales: list[Form4Sale] = []
    for ticker, cik, name in cands:
        filings = fetch_form4_filings(cik, args.days_back)
        n_sells = 0
        for f in filings:
            src = f.get("_source", {})
            acc = src.get("adsh", "")
            filed = src.get("file_date", "")
            xml = fetch_form4_xml(cik, acc)
            sale = parse_form4_sale(xml, cik, name, acc, filed)
            if sale:
                all_sales.append(sale)
                n_sells += 1
            time.sleep(0.10)   # EDGAR rate limit
        if n_sells:
            print(f"  {ticker:8s} {name[:25]:25s} "
                  f"sales: {n_sells:3d}")
        time.sleep(0.10)

    clusters = detect_clusters(all_sales, args.min_insiders,
                               DEFAULT_CLUSTER_WINDOW_DAYS, args.min_usd)
    print(f"\n  {len(clusters)} cluster-sell signals detected")
    for c in clusters:
        unplanned = (" ⚠ UNPLANNED" if c.n_unplanned >= 2 else "")
        print(f"    {c.issuer[:30]:30s}  "
              f"{c.n_unique_insiders} insiders, ${c.total_usd:>10,.0f}, "
              f"window {c.window_start}..{c.window_end}{unplanned}")
    if clusters:
        counts = write_inbox(clusters, fetched_at)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    print(f"\nDone. {len(clusters)} cluster records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
