"""Job postings as a hiring-growth leading indicator -- free, no key.

The spec's lowest-risk free path: many companies expose their entire
careers page as JSON at well-known URL patterns:

  - Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
  - Lever:      https://api.lever.co/v0/postings/{slug}
  - Workday:    POST to https://{tenant}.wd5.myworkdayjobs.com/...

A jump in open requisitions (especially engineering for SaaS, store/
operations for retail, biology for biotech) often leads earnings by 1-2
quarters. We snapshot the count daily and surface deltas.

`ticker_to_board` is e.g. {"CELH": ("greenhouse", "celsius"),
                             "FTDR": ("greenhouse", "frontdoor"),
                             "CROX": ("greenhouse", "crocs")}.

No JobSpy dependency here; JobSpy is in a sibling module since it
needs heavier deps (selenium-style fallbacks).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)


def fetch_greenhouse(slug: str, timeout: float = 15.0) -> list[dict]:
    """Pull a company's Greenhouse postings."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "social-arb/0.1"})
        r.raise_for_status()
        return (r.json() or {}).get("jobs", []) or []
    except (requests.RequestException, ValueError) as exc:
        log.debug("greenhouse %s failed: %s", slug, exc)
        return []


def fetch_lever(slug: str, timeout: float = 15.0) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "social-arb/0.1"})
        r.raise_for_status()
        return r.json() or []
    except (requests.RequestException, ValueError) as exc:
        log.debug("lever %s failed: %s", slug, exc)
        return []


def collect_job_postings(
    cfg: Config,
    ticker_to_board: dict[str, tuple[str, str]],
) -> pd.DataFrame:
    """Snapshot each company's open requisitions.

    Each company-day produces ONE mention row with `mentions` =
    open requisition count (used as the attention proxy). Run daily;
    growth in the count is the actionable signal.
    """
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for ticker, (platform, slug) in ticker_to_board.items():
        if platform == "greenhouse":
            jobs = fetch_greenhouse(slug)
        elif platform == "lever":
            jobs = fetch_lever(slug)
        else:
            log.warning("unknown job platform %s", platform)
            continue
        n = len(jobs)
        text = (
            f"{platform} careers for {slug}: {n} open postings on {now.date().isoformat()}"
        )
        # Categorize departments / locations for richer context.
        departments = {}
        for j in jobs:
            if platform == "greenhouse":
                for d in j.get("departments", []) or []:
                    departments[d.get("name", "Other")] = departments.get(d.get("name", "Other"), 0) + 1
            elif platform == "lever":
                cat = (j.get("categories") or {}).get("department", "Other")
                departments[cat] = departments.get(cat, 0) + 1
        text += f" | departments: {dict(sorted(departments.items(), key=lambda x: -x[1])[:5])}"
        # Phase 2: ONE weighted row per ticker-day, weight = log1p(open
        # requisitions).
        import math
        rows.append({
            "timestamp": now,
            "source": "job_postings",
            "source_id": f"jobs:{platform}:{slug}:{now.date().isoformat()}",
            "ticker": ticker.upper(),
            "alias": slug,
            "confidence": 0.85,
            "via": platform,
            "text": text,
            "sentiment": 0.0,
            "sentiment_label": "neutral",
            "url": (
                f"https://boards.greenhouse.io/{slug}" if platform == "greenhouse"
                else f"https://jobs.lever.co/{slug}"
            ),
            "author": None,
            "weight": float(math.log1p(n) * 1.5),
        })
    return normalized_dataframe(rows)
