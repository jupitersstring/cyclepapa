"""Finviz quote scraper.

Finviz publishes a fundamental snapshot per ticker as a single HTML
page -- no API key, no auth, no rate-limit advertised (but we throttle
to ~1 req/sec to be polite). One page yields ~70 fields:

  Market Cap, P/E, EPS, ROE, ROA, Short Float, Short Interest, Insider
  Ownership, Insider Trans, Inst Own, Inst Trans, Beta, ATR, RSI(14),
  SMA20/50/200 distance, Earnings, Target Price, EPS surprises,
  Recommendation, Float, Shs Outstanding, Avg Volume...

For the social-arb pipeline the highest-signal subset is:

  * **Short Float**          -- crowded shorts = squeeze candidate
  * **Insider Trans**         -- insiders accumulating
  * **EPS Surprise**          -- recent beat / miss magnitude
  * **Earnings**              -- date of next catalyst
  * **Market Cap**             -- proper size filter (vs price proxy)
  * **Float / Shs Outstanding** -- structural squeeze risk

Returns a dict per ticker (failures return empty dict, not exception).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd
import requests

log = logging.getLogger(__name__)

FINVIZ_URL = "https://finviz.com/quote.ashx"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 social-arb/0.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _parse_pct(s: str) -> float | None:
    if not s or s == "-":
        return None
    try:
        return float(s.replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _parse_mcap(s: str) -> float | None:
    """'13.45B' / '985.20M' / '2.10T' -> float dollars."""
    if not s or s == "-":
        return None
    s = s.replace(",", "").strip()
    mult = 1.0
    if s.endswith("B"):
        mult = 1e9
        s = s[:-1]
    elif s.endswith("M"):
        mult = 1e6
        s = s[:-1]
    elif s.endswith("K"):
        mult = 1e3
        s = s[:-1]
    elif s.endswith("T"):
        mult = 1e12
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _parse_float(s: str) -> float | None:
    if not s or s == "-":
        return None
    try:
        return float(s.replace(",", "").strip())
    except ValueError:
        return None


def fetch_finviz_snapshot(
    ticker: str,
    *,
    timeout: float = 15.0,
    user_agent: str | None = None,
) -> dict:
    """Parse Finviz's `quote.ashx` page for a single ticker."""
    headers = dict(DEFAULT_HEADERS)
    if user_agent:
        headers["User-Agent"] = user_agent
    try:
        r = requests.get(FINVIZ_URL, params={"t": ticker}, headers=headers, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.debug("finviz %s failed: %s", ticker, exc)
        return {}

    html = r.text
    if not html or "Quote not found" in html:
        return {}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed; finviz collector disabled")
        return {}

    soup = BeautifulSoup(html, "html.parser")
    # Finviz puts the snapshot in a table with class snapshot-table2
    table = soup.find("table", class_=re.compile(r"snapshot-table2|js-snapshot-table"))
    if table is None:
        return {}
    cells = table.find_all("td")
    # Cells come in label, value, label, value, ...
    out: dict[str, str] = {}
    for i in range(0, len(cells) - 1, 2):
        key = cells[i].get_text(strip=True)
        val = cells[i + 1].get_text(strip=True)
        if key:
            out[key] = val
    if not out:
        return {}

    # Sector / industry / country live in a separate row above the table.
    sec_links = soup.select("a.tab-link")
    sector = industry = country = None
    if len(sec_links) >= 3:
        sector = sec_links[0].get_text(strip=True)
        industry = sec_links[1].get_text(strip=True)
        country = sec_links[2].get_text(strip=True)

    # Parse a curated subset that the pipeline actually uses.
    return {
        "ticker": ticker.upper(),
        "market_cap": _parse_mcap(out.get("Market Cap", "")),
        "pe": _parse_float(out.get("P/E", "")),
        "forward_pe": _parse_float(out.get("Forward P/E", "")),
        "eps_ttm": _parse_float(out.get("EPS (ttm)", "")),
        "eps_yoy": _parse_pct(out.get("EPS Q/Q", "")),
        "sales_yoy": _parse_pct(out.get("Sales Q/Q", "")),
        "short_float_pct": _parse_pct(out.get("Short Float", "")),
        "short_ratio": _parse_float(out.get("Short Ratio", "")),
        "insider_own_pct": _parse_pct(out.get("Insider Own", "")),
        "insider_trans_pct": _parse_pct(out.get("Insider Trans", "")),
        "inst_own_pct": _parse_pct(out.get("Inst Own", "")),
        "inst_trans_pct": _parse_pct(out.get("Inst Trans", "")),
        "perf_week_pct": _parse_pct(out.get("Perf Week", "")),
        "perf_month_pct": _parse_pct(out.get("Perf Month", "")),
        "perf_quarter_pct": _parse_pct(out.get("Perf Quarter", "")),
        "perf_year_pct": _parse_pct(out.get("Perf Year", "")),
        "high_52w_pct": _parse_pct(out.get("52W High", "")),
        "low_52w_pct": _parse_pct(out.get("52W Low", "")),
        "beta": _parse_float(out.get("Beta", "")),
        "atr": _parse_float(out.get("ATR (14)", "")),
        "rsi_14": _parse_float(out.get("RSI (14)", "")),
        "avg_volume": _parse_float(out.get("Avg Volume", "").replace("M", "").replace("K", "")),
        "shs_float": _parse_mcap(out.get("Shs Float", "")),
        "shs_outstanding": _parse_mcap(out.get("Shs Outstand", "")),
        "earnings_date": out.get("Earnings", "") or None,
        "target_price": _parse_float(out.get("Target Price", "")),
        "recommendation": _parse_float(out.get("Recom", "")),
        "sector": sector,
        "industry": industry,
        "country": country,
        "fetched_at": datetime.now(timezone.utc),
    }


def collect_finviz_batch(
    tickers: list[str],
    *,
    sleep_between: float = 0.7,
) -> pd.DataFrame:
    """Iterate a list of tickers serially and return a tidy DataFrame.

    Throttled to ~1.5 req/sec by default to stay polite with Finviz.
    """
    rows: list[dict] = []
    for i, t in enumerate(tickers):
        snap = fetch_finviz_snapshot(t)
        if snap:
            rows.append(snap)
        if (i + 1) % 25 == 0:
            log.info("finviz: %d/%d (kept %d)", i + 1, len(tickers), len(rows))
        time.sleep(sleep_between)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
