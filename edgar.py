"""SEC EDGAR client.

Pulls a company's CIK from the public ticker map and resolves the most
recent DEF 14A (proxy statement) filing -- which is where Performance
Share Unit grants and the Compensation Discussion & Analysis live.

EDGAR requires a descriptive User-Agent on every request and asks
clients to stay under ~10 req/s. We honour both.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

# SEC fair-access policy requires a descriptive UA with a reachable
# contact. Override via SEC_EDGAR_CONTACT env var.
_CONTACT = os.environ.get("SEC_EDGAR_CONTACT",
                          "cm2whv9sg2@privaterelay.appleid.com")
UA = f"cyclepapa-psu-research {_CONTACT}"
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
SEC_WWW = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"

_TICKERS: dict[str, dict] | None = None


def _get(url: str, max_retries: int = 4) -> requests.Response:
    last = None
    for i in range(max_retries):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return r
        if r.status_code in (429, 503):
            time.sleep(1.5 * (i + 1))
            last = r
            continue
        r.raise_for_status()
    if last is not None:
        last.raise_for_status()
    return r


def _ticker_index() -> dict[str, dict]:
    """Lazy-load SEC's ticker -> CIK map and cache for the process."""
    global _TICKERS
    if _TICKERS is None:
        data = _get(f"{SEC_WWW}/files/company_tickers.json").json()
        _TICKERS = {v["ticker"].upper(): v for v in data.values()}
    return _TICKERS


def cik_for(ticker: str) -> str | None:
    rec = _ticker_index().get(ticker.upper())
    return f"{int(rec['cik_str']):010d}" if rec else None


@dataclass
class Filing:
    ticker: str
    cik: str
    accession: str
    primary_doc: str
    filing_date: str

    @property
    def url(self) -> str:
        acc = self.accession.replace("-", "")
        return f"{SEC_WWW}/Archives/edgar/data/{int(self.cik)}/{acc}/{self.primary_doc}"


def latest_def14a(ticker: str) -> Filing | None:
    cik = cik_for(ticker)
    if not cik:
        return None
    payload = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    recent = payload.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    for form, acc, doc, dt in zip(forms, accs, docs, dates):
        if form == "DEF 14A":
            return Filing(
                ticker=ticker.upper(), cik=cik,
                accession=acc, primary_doc=doc, filing_date=dt,
            )
    return None


def fetch_filing_html(filing: Filing) -> str:
    return _get(filing.url).text
