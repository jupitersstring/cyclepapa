"""Google Trends collector via pytrends (archived but still installs).

Two query forms per ticker yield orthogonal signals:

  * **cashtag** -- `$CELH` style; the financial-search audience
  * **stock keyword** -- e.g. `Celsius Holdings stock`; the retail-research
    audience

We also support a free-form *brand query* (e.g. `Stanley tumbler`) for the
Camillo-style consumer-attention layer that doesn't require investors to
have heard of the company yet.

Each call returns a daily time series of search interest (Google's 0-100
relative index, *not* absolute counts). We store one mention row per day
where interest > 0, with `mentions` set to the index value so the same
EWMA/z-score machinery downstream works without modification.

Google rate-limits pytrends aggressively from datacenter IPs; in
production this almost always needs a residential proxy or session
rotation. We retry a couple of times then degrade quietly.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)


def _trends_client(geo: str = "US", hl: str = "en-US"):
    """Lazy-import pytrends (or pytrends-modern) so the dep is optional.

    `pytrends` (legacy) has a known urllib3 incompatibility on Python 3.11+
    (`method_whitelist` was renamed `allowed_methods`). The
    `pytrends-modern` fork addresses that and adds Camoufox / Selenium
    fallback for browser-style requests. We try modern first, fall back
    to legacy.

    NOTE: Google aggressively rate-limits trends from datacenter IPs.
    From a typical cloud runner this collector will mostly fail with
    429 errors regardless of which client; production deployments need
    residential proxies (Webshare / IPRoyal ~$15/GB) or session
    rotation. The collector returns an empty frame in that case rather
    than raising.
    """
    TrendReq = None
    try:
        from pytrends_modern import TrendReq as _Tm  # type: ignore
        TrendReq = _Tm
    except ImportError:
        try:
            from pytrends.request import TrendReq as _Tl  # type: ignore
            TrendReq = _Tl
        except ImportError:
            log.warning("neither pytrends-modern nor pytrends installed; google_trends disabled")
            return None
    try:
        return TrendReq(hl=hl, tz=300, retries=2, backoff_factor=0.5, timeout=(10, 25))
    except TypeError:
        # pytrends-modern signature differs slightly.
        try:
            return TrendReq(hl=hl, tz=300)
        except Exception as exc:  # noqa: BLE001
            log.warning("pytrends client init failed: %s", exc)
            return None
    except Exception as exc:  # noqa: BLE001
        log.warning("pytrends client init failed: %s", exc)
        return None


def fetch_trends_series(
    queries: list[str],
    *,
    timeframe: str = "today 12-m",
    geo: str = "US",
) -> pd.DataFrame:
    """Fetch the Google Trends interest-over-time DataFrame.

    `queries` may be up to 5 terms in a single call. `timeframe` accepts
    Google's spec: 'now 1-d', 'now 7-d', 'today 3-m', 'today 12-m',
    'today 5-y', 'all', or an explicit 'YYYY-MM-DD YYYY-MM-DD' range.
    """
    if not queries:
        return pd.DataFrame()
    pt = _trends_client()
    if pt is None:
        return pd.DataFrame()
    try:
        pt.build_payload(queries[:5], cat=0, timeframe=timeframe, geo=geo, gprop="")
        df = pt.interest_over_time()
    except Exception as exc:  # noqa: BLE001
        log.warning("pytrends fetch failed (%s); often rate-limited from datacenter IPs", exc)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])
    df.index = pd.to_datetime(df.index)
    return df


def collect_google_trends(
    cfg: Config,
    *,
    ticker: str,
    company_name: str | None = None,
    brand_query: str | None = None,
    timeframe: str = "today 12-m",
    sleep_between: float = 1.5,
) -> pd.DataFrame:
    """Pull Google Trends for cashtag + 'TICKER stock' + optional brand query.

    Emits mention rows where `mentions` is the Trends interest index (0-100)
    on each day; that way the downstream EWMA/z/momentum stack treats high
    relative search interest as high attention without modification.
    """
    queries: list[str] = [f"${ticker.upper()}", f"{ticker.upper()} stock"]
    if company_name and len(company_name) >= 3 and company_name.lower() not in {q.lower() for q in queries}:
        queries.append(f"{company_name} stock")
    if brand_query:
        queries.append(brand_query)
    queries = queries[:5]

    df = fetch_trends_series(queries, timeframe=timeframe)
    time.sleep(sleep_between)
    if df.empty:
        return normalized_dataframe([])

    rows: list[dict] = []
    for col in df.columns:
        series = df[col].astype(float)
        for ts, val in series.items():
            if pd.isna(val) or val <= 0:
                continue
            ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
            sid = f"gtrend:{col}:{ts.date().isoformat()}:{ticker.upper()}"
            via = (
                "cashtag" if col.startswith("$") else
                "stock_keyword" if col.lower().endswith(" stock") else
                "brand_query"
            )
            text = f"google_trends({col})={int(val)} on {ts.date().isoformat()}"
            # Emit `int(val/10)` rows so the mention z-score reads a sane
            # number while preserving the relative-attention shape; minimum 1
            # so the day is still observed.
            n_proxy = max(1, int(val / 10))
            for i in range(n_proxy):
                rows.append({
                    "timestamp": ts_utc,
                    "source": "google_trends",
                    "source_id": f"{sid}:{i}",
                    "ticker": ticker.upper(),
                    "alias": col.lower(),
                    "confidence": 0.85,
                    "via": via,
                    "text": text,
                    "sentiment": 0.0,
                    "sentiment_label": "neutral",
                    "url": "https://trends.google.com/trends/explore",
                    "author": None,
                })
    return normalized_dataframe(rows)
