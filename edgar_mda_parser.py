"""SEC EDGAR MD&A backlog parser — quarterly backlog series for US filers
(and dual-listed Canadians who file 40-F / 6-K with the SEC).

Pipeline:
  1. Resolve ticker -> CIK via SEC's company_tickers.json.
  2. Pull submission history from data.sec.gov/submissions/CIK########.json.
  3. Filter to 10-Q / 10-K / 40-F / 6-K filings, take the most recent N.
  4. Fetch the primary document (HTML usually) for each filing.
  5. Extract every sentence mentioning backlog / order book / bookings
     and parse the adjacent dollar value.
  6. Emit a per-period series so you can see if backlog is genuinely
     accelerating.

EDGAR's public API has no bot protection but enforces a polite-User-Agent
requirement (must include contact info). We set that automatically.

Usage:
    python edgar_mda_parser.py --ticker NCR --n 6
    python edgar_mda_parser.py --cik 0001702780 --n 6 --out backlog.csv
"""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
import requests


# SEC requires a User-Agent identifying the requestor + contact info.
HEADERS = {
    "User-Agent": "multibagger-research opensource@multibagger.dev",
    "Accept": "application/json, text/html, */*",
    "Host": "www.sec.gov",
}
DATA_HEADERS = {**HEADERS, "Host": "data.sec.gov"}

EDGAR_BASE = "https://www.sec.gov"
EDGAR_DATA = "https://data.sec.gov"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# Forms we want to inspect for backlog discussion
RELEVANT_FORMS = {
    "10-Q", "10-K", "10-K/A", "10-Q/A",
    "40-F", "40-F/A",                  # Canadian large filers
    "20-F", "20-F/A",                  # foreign private issuers
    "6-K",                             # Canadian / foreign current-event filings
    "8-K",                             # US current-event filings
}

BACKLOG_SENTENCE_RE = re.compile(
    r"([^.!?\n]{0,250}?"
    r"(?:backlog|order\s+book|order\s+intake|bookings|unfilled\s+orders|book[-\s]to[-\s]bill)"
    r"[^.!?\n]{0,250}[.!?])",
    re.IGNORECASE,
)

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
    accession: str
    filing_date: str
    period_end: str
    form: str
    primary_doc: str
    snippet: str
    value: Optional[float] = None
    unit_str: str = ""


_TICKER_MAP_CACHE: dict[str, str] | None = None


def get_cik_for_ticker(ticker: str) -> Optional[str]:
    """Resolve a ticker symbol to its CIK via SEC's company_tickers map.

    Accepts plain US tickers ('NCR', 'AAPL') or yfinance-style suffix
    forms ('NCR.O'). Strips exchange suffixes for matching.
    """
    global _TICKER_MAP_CACHE
    if _TICKER_MAP_CACHE is None:
        try:
            r = requests.get(f"{EDGAR_BASE}/files/company_tickers.json",
                             headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            _TICKER_MAP_CACHE = {
                v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                for v in data.values()
            }
            print(f"  loaded {len(_TICKER_MAP_CACHE):,} ticker mappings", file=sys.stderr)
        except Exception as e:
            print(f"  ticker map fetch failed: {e}", file=sys.stderr)
            return None

    t = ticker.split(".")[0].upper()
    return _TICKER_MAP_CACHE.get(t)


def list_filings(cik: str, forms: set[str] = RELEVANT_FORMS, n: int = 8) -> list[dict]:
    """List the issuer's most recent filings of the requested forms."""
    cik_padded = cik.zfill(10)
    url = f"{EDGAR_DATA}/submissions/CIK{cik_padded}.json"
    try:
        r = requests.get(url, headers=DATA_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  submissions fetch failed: {e}", file=sys.stderr)
        return []

    recent = data.get("filings", {}).get("recent", {}) or {}
    rows = []
    for i in range(len(recent.get("accessionNumber", []))):
        form = recent["form"][i]
        if form not in forms:
            continue
        rows.append({
            "accession": recent["accessionNumber"][i],
            "filing_date": recent["filingDate"][i],
            "form": form,
            "primary_doc": recent["primaryDocument"][i],
            "period_end": recent.get("reportDate", [""])[i] if i < len(recent.get("reportDate", [])) else "",
        })
        if len(rows) >= n:
            break
    return rows


def fetch_document(cik: str, accession: str, primary_doc: str) -> str:
    """Download the primary document HTML/text for a filing."""
    acc_clean = accession.replace("-", "")
    url = f"{ARCHIVES_BASE}/{int(cik)}/{acc_clean}/{primary_doc}"
    try:
        time.sleep(0.15)  # SEC rate limit: 10 req/sec max
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Quick HTML->text conversion without bringing in BeautifulSoup."""
    # Drop scripts / styles
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    # Strip tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">")
                .replace("&#160;", " ").replace("\xa0", " "))
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def find_backlog_readings(text: str) -> list[tuple[str, Optional[float], str]]:
    out: list[tuple[str, Optional[float], str]] = []
    for m in BACKLOG_SENTENCE_RE.finditer(text):
        snippet = " ".join(m.group(1).split())
        v_match = VALUE_RE.search(snippet)
        if v_match:
            value = _to_value(v_match.group(1), v_match.group(2))
            unit_str = (v_match.group(0) or "").strip()
        else:
            value = None
            unit_str = ""
        out.append((snippet[:500], value, unit_str))
    return out


def assess(cik: str, n: int = 6) -> list[BacklogReading]:
    filings = list_filings(cik, n=n)
    if not filings:
        print(f"  no relevant filings for CIK {cik}", file=sys.stderr)
        return []

    print(f"  fetching {len(filings)} filings...", file=sys.stderr)
    readings: list[BacklogReading] = []
    for f in filings:
        html = fetch_document(cik, f["accession"], f["primary_doc"])
        if not html:
            print(f"    [{f['filing_date']}] {f['form']:6s} {f['accession']}  - fetch failed",
                  file=sys.stderr)
            continue
        text = _strip_html(html)
        backlog_readings = find_backlog_readings(text)
        print(f"    [{f['filing_date']}] {f['form']:6s} {f['accession']:25s}  "
              f"{len(backlog_readings)} mentions", file=sys.stderr)
        for snippet, value, unit_str in backlog_readings:
            readings.append(BacklogReading(
                accession=f["accession"],
                filing_date=f["filing_date"],
                period_end=f["period_end"] or "",
                form=f["form"],
                primary_doc=f["primary_doc"],
                snippet=snippet,
                value=value,
                unit_str=unit_str,
            ))
    return readings


def _summarise(df: pd.DataFrame):
    """Print backlog series + YoY delta if extractable."""
    print("\n=== BACKLOG READINGS (latest first) ===")
    for _, r in df.iterrows():
        val = f"${r.value/1e6:.1f}M" if pd.notna(r.value) else "?"
        period = r.period_end or r.filing_date
        print(f"  {period}  {r.form:6s}  {val:>10s}  {r.snippet[:180]}")

    # Per-period max value (assume biggest dollar mention is the backlog total)
    valid = df.dropna(subset=["value"]).copy()
    if valid.empty:
        return
    valid = valid[(valid.value >= 1e6) & (valid.value <= 1e12)]
    if valid.empty:
        return
    per_period = valid.groupby("period_end")["value"].max().sort_index(ascending=False)
    if len(per_period) < 2:
        return
    print(f"\n=== IMPLIED BACKLOG SERIES (max $ per period) ===")
    prev = None
    for period, val in per_period.items():
        delta = ((val - prev) / prev) if prev else None
        delta_str = f"  {delta:+.1%} vs prior" if delta is not None else ""
        print(f"  {period}  ${val/1e6:>8.1f}M{delta_str}")
        prev = val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="US ticker (or dual-listed CA on US exchange)")
    ap.add_argument("--cik", help="SEC CIK (10-digit, leading zeros optional)")
    ap.add_argument("--n", type=int, default=6, help="how many recent filings to inspect")
    ap.add_argument("--out", default="edgar_mda_readings.csv")
    args = ap.parse_args()

    if not args.ticker and not args.cik:
        print("pass --ticker or --cik", file=sys.stderr)
        sys.exit(1)

    if args.cik:
        cik = args.cik.zfill(10).lstrip("0").zfill(10)
        print(f"=== CIK {cik} ===", file=sys.stderr)
    else:
        cik = get_cik_for_ticker(args.ticker)
        if not cik:
            print(f"ticker {args.ticker} not found in SEC company_tickers.json — "
                  f"may not be a US filer", file=sys.stderr)
            sys.exit(1)
        print(f"=== {args.ticker.upper()} -> CIK {cik} ===", file=sys.stderr)

    readings = assess(cik, n=args.n)
    if not readings:
        print(f"\nno backlog mentions extracted", file=sys.stderr)
        sys.exit(0)

    df = pd.DataFrame([asdict(r) for r in readings])
    df = df.sort_values(["period_end", "filing_date"], ascending=False)
    df.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}: {len(df)} readings", file=sys.stderr)

    _summarise(df)


if __name__ == "__main__":
    main()
