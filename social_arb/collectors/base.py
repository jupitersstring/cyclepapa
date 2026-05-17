"""Shared HTTP / DataFrame helpers for collectors."""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests

from ..config import Config
from ..storage import REQUIRED_COLUMNS

log = logging.getLogger(__name__)


class CollectorError(RuntimeError):
    pass


def http_get_json(
    url: str,
    cfg: Config,
    params: dict[str, Any] | None = None,
    *,
    retries: int = 3,
    backoff: float = 1.5,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    """GET a JSON endpoint with simple exponential backoff."""
    headers = {"User-Agent": cfg.user_agent, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    last_err: Exception | None = None
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=cfg.http_timeout)
            if r.status_code == 429:
                # Rate limited - honor Retry-After if provided.
                wait = float(r.headers.get("Retry-After", delay))
                log.warning("429 from %s; sleeping %.1fs", url, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            last_err = exc
            log.warning("HTTP attempt %d/%d failed for %s: %s", attempt + 1, retries, url, exc)
            time.sleep(delay)
            delay *= backoff
    raise CollectorError(f"GET {url} failed after {retries} attempts: {last_err}")


def normalized_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Force a list of raw dicts into the canonical mention schema."""
    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    df = pd.DataFrame(rows)
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[REQUIRED_COLUMNS]
