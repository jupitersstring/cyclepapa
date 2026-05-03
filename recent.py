"""Pull the most recently filed DEF 14A proxies from EDGAR.

Use the public Atom feed of "current events" filtered to form DEF 14A.
Returns a list of (cik, ticker_or_name, filing_date, filing_url) tuples
ordered most-recent first, ready to feed into the PSU scoring pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from edgar import _get, SEC_WWW, SEC_DATA, _ticker_index


@dataclass
class RecentFiling:
    cik: str
    company: str
    ticker: str | None
    filing_date: str
    accession: str
    primary_doc: str

    @property
    def url(self) -> str:
        acc = self.accession.replace("-", "")
        return f"{SEC_WWW}/Archives/edgar/data/{int(self.cik)}/{acc}/{self.primary_doc}"


def _cik_to_ticker_map() -> dict[str, str]:
    return {f"{int(v['cik_str']):010d}": v["ticker"]
            for v in _ticker_index().values()}


_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)
_TITLE = re.compile(r"<title>([^<]+)</title>")
_UPDATED = re.compile(r"<updated>([^<]+)</updated>")
_CIK = re.compile(r"\((\d{6,10})\)")


EFTS = "https://efts.sec.gov/LATEST/search-index"


def recent_def14a_range(
    start_date: str,
    end_date: str,
    limit: int = 300,
) -> list[RecentFiling]:
    """Pull every DEF 14A filed between start_date and end_date (YYYY-MM-DD).

    Uses the full-text search index so we can paginate beyond what
    /cgi-bin/browse-edgar?action=getcurrent returns. Deduplicates by CIK
    so each filer surfaces only once even if they amended."""
    out: list[RecentFiling] = []
    seen_cik: set[str] = set()
    cik_to_ticker = _cik_to_ticker_map()
    page_size = 100
    offset = 0
    while len(out) < limit and offset < 1000:  # EFTS hard caps at 10k anyway
        url = (
            f"{EFTS}?forms=DEF+14A&dateRange=custom"
            f"&startdt={start_date}&enddt={end_date}"
            f"&from={offset}"
        )
        try:
            data = _get(url).json()
        except Exception:
            break
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h.get("_source", {}) or {}
            ciks = src.get("ciks") or []
            cik = f"{int(ciks[0]):010d}" if ciks else None
            if not cik or cik in seen_cik:
                continue
            seen_cik.add(cik)

            tickers = src.get("tickers") or []
            ticker = tickers[0] if tickers else cik_to_ticker.get(cik)
            display = (src.get("display_names") or ["?"])[0]
            company = display.split(" (")[0]
            file_date = src.get("file_date", "")

            id_parts = (h.get("_id") or "").split(":")
            if len(id_parts) != 2:
                continue
            accession, primary_doc = id_parts

            out.append(RecentFiling(
                cik=cik,
                company=company,
                ticker=ticker,
                filing_date=file_date,
                accession=accession,
                primary_doc=primary_doc,
            ))
            if len(out) >= limit:
                break
        offset += page_size
    return out


def recent_8k_inducement_range(
    start_date: str,
    end_date: str,
    limit: int = 300,
) -> list[RecentFiling]:
    """Pull 8-Ks reporting executive inducement / hire grants.

    EDGAR full-text search for 8-Ks containing 'inducement' AND
    'performance share'. This catches new-CEO PSU inducement awards
    that don't yet live in any annual proxy. Results are deduped by
    CIK so each issuer surfaces at most once."""
    out: list[RecentFiling] = []
    seen_cik: set[str] = set()
    cik_to_ticker = _cik_to_ticker_map()

    # Broader query set: many new-CEO PSU grants don't use the word
    # "inducement". They live in Item 5.02 with phrases like "appointment"
    # / "named Chief Executive" / "stock price hurdle" / "performance
    # share units" / "performance-based RSU". Casting a wide net here.
    queries = [
        '"inducement" "performance share"',
        '"inducement award" "stock price"',
        '"Item 5.02" "stock price hurdle"',
        '"Item 5.02" "performance share units"',
        '"Item 5.02" "performance-based" "stock price"',
        '"appointment" "Chief Executive" "performance share"',
        '"named" "Chief Executive Officer" "stock price"',
        '"appointed" "performance stock units"',
        '"new Chief Executive" "performance share"',
        '"hire" "performance share units" "vest"',
        '"sign-on" "performance share"',
    ]

    page_size = 100
    for q in queries:
        offset = 0
        while len(out) < limit and offset < 1000:
            url = (
                f"{EFTS}?forms=8-K&dateRange=custom"
                f"&startdt={start_date}&enddt={end_date}"
                f"&from={offset}"
                f"&q={requests_quote(q)}"
            )
            try:
                data = _get(url).json()
            except Exception:
                break
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                src = h.get("_source", {}) or {}
                ciks = src.get("ciks") or []
                cik = f"{int(ciks[0]):010d}" if ciks else None
                if not cik or cik in seen_cik:
                    continue
                # 8-K can also report director departures with PSU mentions; we
                # accept any 8-K matching the query and let the scorer decide.
                seen_cik.add(cik)
                tickers = src.get("tickers") or []
                ticker = tickers[0] if tickers else cik_to_ticker.get(cik)
                display = (src.get("display_names") or ["?"])[0]
                company = display.split(" (")[0]
                file_date = src.get("file_date", "")
                id_parts = (h.get("_id") or "").split(":")
                if len(id_parts) != 2:
                    continue
                accession, primary_doc = id_parts
                out.append(RecentFiling(
                    cik=cik, company=company, ticker=ticker,
                    filing_date=file_date,
                    accession=accession, primary_doc=primary_doc,
                ))
                if len(out) >= limit:
                    return out
            offset += page_size
    return out


def requests_quote(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s)


def company_filings(
    ticker: str,
    forms: tuple[str, ...] = ("DEF 14A", "8-K", "10-K", "S-8"),
    limit_per_form: int = 5,
    days: int | None = 365,
) -> list[RecentFiling]:
    """Pull recent filings for a single company directly from its
    submissions JSON. Bypasses the full-text-search guesswork --
    ideal for verifying a specific ticker the user has in mind.

    Returns up to `limit_per_form` of each form type, sorted most-recent
    first. Constrained to filings within the past `days` days when set."""
    from edgar import cik_for, _get, SEC_DATA
    cik = cik_for(ticker)
    if not cik:
        return []
    try:
        sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    except Exception:
        return []
    recent = sub.get("filings", {}).get("recent", {})
    forms_list = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    company = sub.get("name", ticker.upper())

    cutoff = None
    if days:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    out: list[RecentFiling] = []
    counts: dict[str, int] = {f: 0 for f in forms}
    for form, acc, doc, dt in zip(forms_list, accs, docs, dates):
        if form not in forms:
            continue
        if cutoff and dt < cutoff:
            continue
        if counts[form] >= limit_per_form:
            continue
        counts[form] += 1
        out.append(RecentFiling(
            cik=cik, company=company, ticker=ticker.upper(),
            filing_date=dt, accession=acc, primary_doc=doc,
        ))
    return out


def recent_def14a(n: int = 25) -> list[RecentFiling]:
    """Walk the EDGAR 'getcurrent' atom feed for DEF 14A filings."""
    n = max(1, min(int(n), 100))
    feed_url = (
        f"{SEC_WWW}/cgi-bin/browse-edgar"
        f"?action=getcurrent&type=DEF+14A&owner=include&count={n}&output=atom"
    )
    xml = _get(feed_url).text
    cik_to_ticker = _cik_to_ticker_map()

    out: list[RecentFiling] = []
    seen_cik: set[str] = set()
    for blob in _ENTRY.findall(xml):
        t = _TITLE.search(blob)
        u = _UPDATED.search(blob)
        if not t or not u:
            continue
        title = t.group(1)
        if "DEF 14A" not in title:
            continue
        m = _CIK.search(title)
        if not m:
            continue
        cik = f"{int(m.group(1)):010d}"
        if cik in seen_cik:
            continue
        seen_cik.add(cik)

        # Resolve the primary document via the submissions JSON. Avoids
        # parsing the per-filing HTML index page.
        try:
            sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
        except Exception:
            continue
        recent = sub.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        dates = recent.get("filingDate", [])
        for form, acc, doc, dt in zip(forms, accs, docs, dates):
            if form == "DEF 14A":
                company = title.split(" - ", 1)[-1].rsplit("(", 1)[0].strip()
                out.append(RecentFiling(
                    cik=cik,
                    company=company,
                    ticker=cik_to_ticker.get(cik),
                    filing_date=dt,
                    accession=acc,
                    primary_doc=doc,
                ))
                break
        if len(out) >= n:
            break
    return out
