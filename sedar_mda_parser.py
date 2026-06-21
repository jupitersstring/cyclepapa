"""SEDAR+ MD&A backlog parser - quarterly backlog series for Canadian filers.

STATUS: PARKED. SEDAR+ (sedarplus.ca) is fronted by ShieldSquare /
perfdrive.com bot-protection. Server-side `requests` calls are 302-bounced
to a CAPTCHA validator regardless of User-Agent, and the JSON endpoints
this script targets return 404 to non-browser clients.

For US filers (and dual-listed Canadians who file with the SEC on
40-F / 6-K / 20-F), use edgar_mda_parser.py instead — EDGAR has no bot
protection and works for any ticker.

Three remaining paths for pure-Canadian SEDAR+ access:
  1. Browser automation (Playwright / Selenium) from a permitted
     environment — out of scope for this sandbox.
  2. A paid mirror (e.g. Snowflake EDI feed, Refinitiv) — out of scope.
  3. Per-name press-release scraping via the issuer's own IR site, which
     is usually not bot-protected. See sedar_backlog_scraper.py for the
     yfinance-news + IR-page approach.

The code below is left intact as a v1 reference; if SEDAR+ relaxes its
bot-protection or you wire this through a browser-automation backend,
it will work as designed.
"""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
import time
import zipfile
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
import requests


SEDAR_BASE = "https://www.sedarplus.ca"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (compatible; multibagger-research/1.0)",
    "Accept-Language": "en-CA,en;q=0.9",
}

# Sentence-level backlog pattern: $X(.X)? (million|billion|m|b|k)? backlog | order book | unfilled orders
BACKLOG_SENTENCE_RE = re.compile(
    r"([^.!?\n]{0,200}?"
    r"(?:backlog|order\s+book|order\s+intake|bookings|unfilled\s+orders|book[-\s]to[-\s]bill)"
    r"[^.!?\n]{0,200}[.!?])",
    re.IGNORECASE,
)

# Dollar-value pattern (CAD / USD / plain $ / £ unlikely here)
VALUE_RE = re.compile(
    r"(?:[\$€£]|CAD|USD|C\$|US\$)\s?"
    r"(\d+(?:[,\s]\d{3})*(?:\.\d+)?)"
    r"\s?(million|billion|thousand|m\b|b\b|k\b)?",
    re.IGNORECASE,
)


def _to_value(num: str, unit: Optional[str]) -> Optional[float]:
    try:
        n = float(num.replace(",", "").replace(" ", ""))
    except Exception:
        return None
    unit = (unit or "").lower().strip()
    if unit in ("billion", "b"):
        n *= 1_000_000_000
    elif unit in ("million", "m"):
        n *= 1_000_000
    elif unit in ("thousand", "k"):
        n *= 1_000
    return n


@dataclass
class BacklogReading:
    filing_date: str
    period_end: str
    filing_type: str
    filing_url: str
    snippet: str
    value: Optional[float] = None
    unit_str: str = ""


# ---------- SEDAR+ search ----------
def find_issuer(name: str) -> Optional[dict]:
    """Search SEDAR+ public party listings for the issuer."""
    url = f"{SEDAR_BASE}/csa-party/service/searchPublicListPaged"
    params = {
        "name": name,
        "page": 0,
        "size": 10,
        "sortColumn": "partyName",
        "sortOrder": "asc",
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        print(f"  issuer search failed: {e}", file=sys.stderr)
        return None
    items = payload.get("content") or payload.get("data") or []
    if not items:
        return None
    # Take the closest name match
    name_low = name.lower()
    items.sort(key=lambda it: 0 if (it.get("partyName") or "").lower().startswith(name_low) else 1)
    return items[0]


def list_recent_filings(party_id: str, n: int = 8) -> list[dict]:
    """List the issuer's most recent filings of interest (MD&A + Financial
    Statements + Annual Information Form + Management Proxy Circular)."""
    url = f"{SEDAR_BASE}/csa-filings/service/searchPublicListPaged"
    # SEDAR+ document type categories of interest:
    #   "Financial statements/MD&A" : "FS"
    # Different SEDAR+ schemas use different keys; we just over-fetch and filter.
    params = {
        "partyId": party_id,
        "page": 0,
        "size": 50,
        "sortColumn": "filingDate",
        "sortOrder": "desc",
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        items = r.json().get("content") or []
    except Exception as e:
        print(f"  filings list failed: {e}", file=sys.stderr)
        return []
    keep_types = ("management's discussion", "mda", "md&a",
                  "financial statements", "annual information form",
                  "management information circular", "material change",
                  "annual report")
    out = []
    for it in items:
        type_str = (it.get("documentTypeDesc") or it.get("submissionType") or "").lower()
        if any(kw in type_str for kw in keep_types):
            out.append(it)
    return out[:n]


# ---------- PDF fetch + extract ----------
def fetch_filing_documents(filing_id: str) -> list[bytes]:
    """For a given filing, return the bytes of each contained PDF.

    SEDAR+ returns a 'document list' per filing; each entry has a URL
    pointing to the document. We attempt to download each PDF.
    """
    url = f"{SEDAR_BASE}/csa-filings/service/findDocumentList"
    try:
        r = requests.get(url, params={"filingId": filing_id}, headers=HEADERS, timeout=20)
        r.raise_for_status()
        docs = r.json() or []
    except Exception:
        return []

    pdfs = []
    for d in docs:
        doc_url = d.get("documentURL") or d.get("urlEn")
        if not doc_url:
            continue
        if not doc_url.startswith("http"):
            doc_url = SEDAR_BASE + doc_url
        try:
            time.sleep(0.5)
            dr = requests.get(doc_url, headers=HEADERS, timeout=60)
            if dr.status_code != 200:
                continue
            content = dr.content
            # Some are ZIP archives — extract embedded PDFs
            if content[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for n in zf.namelist():
                        if n.lower().endswith(".pdf"):
                            pdfs.append(zf.read(n))
            elif content[:4] == b"%PDF":
                pdfs.append(content)
        except Exception:
            continue
    return pdfs


def extract_text(pdf_bytes: bytes, max_pages: int = 60) -> str:
    """Extract text from a PDF (capped at max_pages for speed)."""
    try:
        import pdfplumber
    except ImportError:
        print("  pdfplumber not installed", file=sys.stderr)
        return ""

    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= max_pages:
                    break
                t = page.extract_text() or ""
                text_parts.append(t)
    except Exception as e:
        print(f"  pdf extract failed: {e}", file=sys.stderr)
    return "\n".join(text_parts)


def find_backlog_readings(text: str) -> list[tuple[str, Optional[float], str]]:
    """Pull every sentence-level backlog mention with a parsed dollar value."""
    out: list[tuple[str, Optional[float], str]] = []
    for m in BACKLOG_SENTENCE_RE.finditer(text):
        snippet = " ".join(m.group(1).split())  # collapse whitespace
        value_match = VALUE_RE.search(snippet)
        if value_match:
            value = _to_value(value_match.group(1), value_match.group(2))
            unit_str = (value_match.group(0) or "").strip()
        else:
            value = None
            unit_str = ""
        out.append((snippet[:400], value, unit_str))
    return out


# ---------- Orchestrator ----------
def assess_issuer(name: str, n: int = 6, max_pdfs_per_filing: int = 2) -> list[BacklogReading]:
    print(f"\n=== {name} ===", file=sys.stderr)
    issuer = find_issuer(name)
    if not issuer:
        print(f"  issuer not found on SEDAR+", file=sys.stderr)
        return []
    party_id = issuer.get("partyId") or issuer.get("id")
    print(f"  found: {issuer.get('partyName')} (id={party_id})", file=sys.stderr)

    filings = list_recent_filings(str(party_id), n=n)
    print(f"  found {len(filings)} relevant recent filings", file=sys.stderr)

    readings: list[BacklogReading] = []
    for f in filings:
        filing_id = str(f.get("filingId") or f.get("id"))
        filing_date = (f.get("filingDate") or "")[:10]
        period_end = (f.get("periodEndDate") or f.get("financialYearEnd") or "")[:10]
        filing_type = f.get("documentTypeDesc") or f.get("submissionType") or ""
        filing_url = f"{SEDAR_BASE}/csa-filings/service/findDocumentList?filingId={filing_id}"

        time.sleep(0.5)
        pdfs = fetch_filing_documents(filing_id)
        if not pdfs:
            print(f"    [{filing_date}] {filing_type} - no PDFs", file=sys.stderr)
            continue

        # Limit which PDFs we parse per filing (MD&As often bundled with financials)
        for pdf_bytes in pdfs[:max_pdfs_per_filing]:
            text = extract_text(pdf_bytes)
            if not text:
                continue
            backlog_readings = find_backlog_readings(text)
            print(f"    [{filing_date}] {filing_type[:40]:40s} {len(backlog_readings)} mentions", file=sys.stderr)
            for snippet, value, unit_str in backlog_readings:
                readings.append(BacklogReading(
                    filing_date=filing_date,
                    period_end=period_end,
                    filing_type=filing_type,
                    filing_url=filing_url,
                    snippet=snippet,
                    value=value,
                    unit_str=unit_str,
                ))
    return readings


def _name_from_ticker(symbol: str) -> str:
    """Best-effort: read name from asymmetry_global if available."""
    import os
    if not os.path.exists("asymmetry_global.csv"):
        return symbol
    df = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "name"])
    hit = df[df.symbol == symbol]
    if hit.empty:
        return symbol
    name = hit.iloc[0]["name"] or symbol
    # Strip suffixes that hurt SEDAR+ matching
    name = re.sub(r"\s+(Inc\.?|Corp\.?|Corporation|Limited|Ltd\.?|PLC|"
                  r"Holdings?|Group|Co\.?)$", "", name, flags=re.IGNORECASE).strip()
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="Canadian ticker (e.g. FTG.TO) - name resolved via asymmetry_global")
    ap.add_argument("--issuer-name", help="Override name used for SEDAR+ search")
    ap.add_argument("--n", type=int, default=6, help="how many recent filings to inspect")
    ap.add_argument("--max-pdfs-per-filing", type=int, default=2)
    ap.add_argument("--out", default="mda_backlog_readings.csv")
    args = ap.parse_args()

    name = args.issuer_name or (args.ticker and _name_from_ticker(args.ticker))
    if not name:
        print("pass --ticker or --issuer-name", file=sys.stderr)
        sys.exit(1)

    readings = assess_issuer(name, n=args.n, max_pdfs_per_filing=args.max_pdfs_per_filing)
    if not readings:
        print(f"\nno backlog mentions extracted for {name}", file=sys.stderr)
        sys.exit(0)

    df = pd.DataFrame([asdict(r) for r in readings])
    df = df.sort_values(["period_end", "filing_date"], ascending=False)
    df.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}: {len(df)} readings", file=sys.stderr)

    # Print compact summary
    print("\n=== BACKLOG READINGS (latest first) ===")
    for _, r in df.iterrows():
        val = f"${r.value/1e6:.1f}M" if pd.notna(r.value) else "?"
        period = r.period_end or r.filing_date
        print(f"  {period}  {val:>10s}  {r.snippet[:160]}")

    # If we have at least 2 distinct period_ends, show the implied YoY change
    if df["period_end"].nunique() >= 2 and df["value"].notna().any():
        agg = (df.dropna(subset=["value"])
                 .groupby("period_end")["value"].max()
                 .sort_index(ascending=False))
        if len(agg) >= 2:
            latest = agg.iloc[0]
            prior = agg.iloc[1]
            change = (latest - prior) / prior if prior else None
            print(f"\nlatest backlog: ${latest/1e6:.1f}M ({agg.index[0]})")
            print(f"prior reading:  ${prior/1e6:.1f}M ({agg.index[1]})")
            if change is not None:
                print(f"change:         {change:+.1%}")


if __name__ == "__main__":
    main()
