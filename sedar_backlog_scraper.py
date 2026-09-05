"""SEDAR / EDGAR scraper - verify the qualitative half of the
MicroActivistInflect archetype.

The quantitative half (microcap + cheap EV/EBITDA + clean BS +
profit inflection) is captured by archetype_tags.py. This scraper
confirms the two pieces that fundamentals can't tell us:

  1. Strong backlog growth - from quarterly MD&A
  2. Recently appointed board member with capital-allocation track
     record - from material change reports / management info circulars

Three data sources, increasing depth (v1 = news + SEDAR+ filings index;
deeper MD&A PDF parsing is stubbed for a follow-up build):

  A. yfinance Ticker.news - surfaces recent press releases that Yahoo
     ingested, often including "appoints to board" and "record backlog"
     headlines. Free, immediate, works for any ticker.
  B. SEDAR+ public search (https://www.sedarplus.ca/) for recent
     "Material Change Report" + "Management Information Circular" +
     "Press Release" filings. Returns filing dates, types and titles.
  C. (TODO) Quarterly MD&A PDF parsing - download the latest 4-8
     quarterly filings, extract the "Backlog" / "Order book" section,
     compute YoY change. Requires PDF parsing (pdfplumber).

Usage:
    python sedar_backlog_scraper.py --tickers BRM.V CWL.TO FTG.TO
    python sedar_backlog_scraper.py --from-archetype CA  # auto-pull from archetype_tags
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
import requests


# Keyword sets used to flag headlines / filings of interest
BACKLOG_KEYWORDS = re.compile(
    r"\b(backlog|order book|order intake|orders|bookings|contract\s+award|"
    r"awarded.*(?:contract|order)|record\s+(?:backlog|orders))\b",
    re.IGNORECASE,
)
BOARD_KEYWORDS = re.compile(
    r"\b(appoint(?:ed|ment|s)?\s+(?:to\s+)?(?:the\s+)?board|"
    r"appoint(?:ed|s)?\s+.*director|"
    r"new\s+(?:board\s+member|director|chair(?:man|person)?)|"
    r"elects?\s+.*director|"
    r"board\s+(?:nomination|appointment))\b",
    re.IGNORECASE,
)
ACTIVIST_KEYWORDS = re.compile(
    r"\b(activist|nominee|cooperation\s+agreement|standstill|"
    r"shareholder\s+rights\s+plan|special\s+meeting|requisition)\b",
    re.IGNORECASE,
)
CAPITAL_ALLOC_KEYWORDS = re.compile(
    r"\b(buyback|substantial\s+issuer\s+bid|normal\s+course\s+issuer\s+bid|"
    r"NCIB|return\s+of\s+capital|special\s+dividend|"
    r"capital\s+allocation|strategic\s+review)\b",
    re.IGNORECASE,
)


@dataclass
class TickerSignals:
    symbol: str
    name: str = ""
    n_news: int = 0
    backlog_hits: int = 0
    board_hits: int = 0
    activist_hits: int = 0
    capital_hits: int = 0
    most_recent_board_headline: str = ""
    most_recent_board_date: str = ""
    most_recent_backlog_headline: str = ""
    most_recent_backlog_date: str = ""
    sedar_filing_count: int = 0
    sedar_recent_filings: str = ""
    error: str = ""


# ---------- Source A: yfinance news ----------
def fetch_yfinance_news(symbol: str) -> list[dict]:
    """Returns list of recent news items: {title, link, providerPublishTime}.

    yfinance's .news endpoint is best-effort; retries once on rate-limit."""
    try:
        import yfinance as yf
    except ImportError:
        return []

    for attempt in range(2):
        try:
            t = yf.Ticker(symbol)
            news = t.news or []
            return news
        except Exception as e:
            if attempt == 0 and ("429" in str(e) or "Rate" in str(e)):
                time.sleep(3)
                continue
            return []
    return []


def _extract_news_fields(item: dict) -> tuple[str, str, str]:
    """yfinance news payloads differ between releases - try several shapes."""
    title = item.get("title") or item.get("Title") or ""
    # Newer yfinance wraps content under "content"
    if not title and isinstance(item.get("content"), dict):
        title = item["content"].get("title") or ""
    link = item.get("link") or ""
    if not link and isinstance(item.get("content"), dict):
        link = item["content"].get("canonicalUrl", {}).get("url", "")
    ts = item.get("providerPublishTime") or item.get("pubDate") or 0
    if isinstance(ts, str):
        date_str = ts[:10]
    elif isinstance(ts, (int, float)) and ts > 0:
        from datetime import datetime, timezone
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        date_str = ""
    return title, link, date_str


# ---------- Source B: SEDAR+ public filings index ----------
SEDAR_BASE = "https://www.sedarplus.ca"


def fetch_sedar_recent_filings(name: str, max_days: int = 365) -> list[dict]:
    """Best-effort SEDAR+ search by issuer name.

    SEDAR+ public search returns HTML; we just count + headline-extract.
    For deeper work (PDF download + parse) extend this to follow the
    'documentURL' field per filing.

    Returns a list of {date, type, title} dicts.
    """
    # The SEDAR+ public search endpoint accepts an issuer-name query.
    # As of 2026 it returns JSON when called with the right Accept header.
    url = f"{SEDAR_BASE}/csa-party/service/searchPublicListPaged"
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; multibagger-research/1.0)",
    }
    params = {
        "name": name,
        "documentTypeCategoryCode": "",
        "page": 0,
        "size": 25,
        "sortColumn": "filingDate",
        "sortOrder": "desc",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        payload = r.json()
    except Exception:
        return []

    out = []
    items = payload.get("content") or payload.get("data") or []
    for it in items[:25]:
        out.append({
            "date": (it.get("filingDate") or "")[:10],
            "type": it.get("submissionType") or it.get("documentTypeDesc") or "",
            "title": it.get("subject") or it.get("partyName") or "",
        })
    return out


def assess_ticker(symbol: str, name: str = "") -> TickerSignals:
    sig = TickerSignals(symbol=symbol, name=name)

    # Source A: news
    news = fetch_yfinance_news(symbol)
    sig.n_news = len(news)
    backlog_hits, board_hits, activist_hits, capital_hits = 0, 0, 0, 0
    most_recent_board = ("", "")
    most_recent_backlog = ("", "")
    for item in news:
        title, link, date_str = _extract_news_fields(item)
        if not title:
            continue
        is_backlog = bool(BACKLOG_KEYWORDS.search(title))
        is_board = bool(BOARD_KEYWORDS.search(title))
        is_activist = bool(ACTIVIST_KEYWORDS.search(title))
        is_capital = bool(CAPITAL_ALLOC_KEYWORDS.search(title))
        backlog_hits += int(is_backlog)
        board_hits += int(is_board)
        activist_hits += int(is_activist)
        capital_hits += int(is_capital)
        # Track most-recent headline by date; fall back to first-seen when
        # date is missing (still useful for surfacing the headline text).
        if is_board and (date_str > most_recent_board[1] or not most_recent_board[0]):
            most_recent_board = (title, date_str or "unknown")
        if is_backlog and (date_str > most_recent_backlog[1] or not most_recent_backlog[0]):
            most_recent_backlog = (title, date_str or "unknown")
    sig.backlog_hits = backlog_hits
    sig.board_hits = board_hits
    sig.activist_hits = activist_hits
    sig.capital_hits = capital_hits
    sig.most_recent_board_headline = most_recent_board[0][:160]
    sig.most_recent_board_date = most_recent_board[1]
    sig.most_recent_backlog_headline = most_recent_backlog[0][:160]
    sig.most_recent_backlog_date = most_recent_backlog[1]

    # Source B: SEDAR+ (Canadian listings only — .TO, .V, .CN)
    if name and (symbol.endswith(".TO") or symbol.endswith(".V") or symbol.endswith(".CN")):
        # Use the company name stem (drop "Inc.", "Corp.", etc.) for matching
        name_stem = re.sub(r"\s+(Inc\.?|Corp\.?|Corporation|Limited|Ltd\.?|"
                           r"PLC|Holdings?|Group|Co\.?)\b", "", name, flags=re.IGNORECASE).strip()
        try:
            filings = fetch_sedar_recent_filings(name_stem)
        except Exception as e:
            sig.error = f"sedar: {e}"
            filings = []
        sig.sedar_filing_count = len(filings)
        # Surface 3 most recent of interest
        interesting = [f for f in filings if any(
            kw in (f.get('type', '') + ' ' + f.get('title', '')).lower()
            for kw in ('material change', 'circular', 'information', 'press release',
                       'mcr', 'mic', 'mda', 'managements discussion'))]
        sig.sedar_recent_filings = "; ".join(
            f"{f['date']} {f['type']}: {f['title'][:60]}" for f in interesting[:3]
        )

    return sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tickers', nargs='*', default=[],
                    help='specific tickers to assess')
    ap.add_argument('--from-archetype', metavar='COUNTRY',
                    help='auto-pull names tagged arch_micro_activist_inflect for this country code (e.g. CA)')
    ap.add_argument('--out', default='archetype_qualitative_signals.csv')
    ap.add_argument('--max', type=int, default=25,
                    help='cap rows when using --from-archetype')
    args = ap.parse_args()

    targets: list[tuple[str, str]] = []  # (symbol, name)
    if args.tickers:
        for t in args.tickers:
            targets.append((t, ''))
    if args.from_archetype:
        try:
            asym = pd.read_csv('asymmetry_global.csv', usecols=['symbol', 'name', 'src'])
            arch = pd.read_csv('archetype_tags.csv', usecols=['symbol', 'arch_micro_activist_inflect'])
            df = asym.merge(arch, on='symbol')
            df = df[(df['arch_micro_activist_inflect'] == 1) & (df['src'] == args.from_archetype.upper())]
            print(f'loading {len(df)} candidates from archetype tags ({args.from_archetype})', file=sys.stderr)
            for _, r in df.head(args.max).iterrows():
                targets.append((r['symbol'], r['name'] or ''))
        except Exception as e:
            print(f'archetype load failed: {e}', file=sys.stderr)

    if not targets:
        print('no targets - pass --tickers or --from-archetype', file=sys.stderr)
        sys.exit(1)

    print(f'assessing {len(targets)} tickers...', file=sys.stderr)
    results = []
    for i, (sym, name) in enumerate(targets, start=1):
        print(f'  [{i}/{len(targets)}] {sym}  {name[:50]}', file=sys.stderr)
        sig = assess_ticker(sym, name)
        results.append(asdict(sig))
        time.sleep(0.5)  # be polite to SEDAR

    out = pd.DataFrame(results)
    out.to_csv(args.out, index=False)
    print(f'wrote {args.out}: {len(out)} rows', file=sys.stderr)

    # Print interest summary
    interesting = out[(out.backlog_hits > 0) | (out.board_hits > 0) | (out.activist_hits > 0)]
    if not interesting.empty:
        print(f'\n=== TICKERS WITH BACKLOG / BOARD / ACTIVIST HITS ({len(interesting)}) ===',
              file=sys.stderr)
        print(interesting[[
            'symbol', 'name', 'backlog_hits', 'board_hits', 'activist_hits',
            'most_recent_board_headline', 'most_recent_board_date',
        ]].to_string(index=False))


if __name__ == '__main__':
    main()
