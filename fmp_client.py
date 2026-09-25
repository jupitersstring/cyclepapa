"""Financial Modeling Prep (FMP) client -- shared by every FMP-backed module.

Key handling: the API key is read from the FMP_API_KEY environment variable
(set it in the cloud environment's settings), falling back to ~/.fmp_key.
It is NEVER written to the repo, and error messages are sanitised so the
key (which rides in the query string) can't leak into logs or outputs.

Uses the /stable/ API (legacy /api/v3 is closed to new subscriptions).
Bulk endpoints return CSV and are rate-limited per part (~1/min), so
get_bulk_csv() retries on HTTP 429 and caches the raw file under
fmp_cache/ (gitignored, rebuildable).
"""

from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path

import requests

ROOT = Path("/home/user/cyclepapa")
BASE = "https://financialmodelingprep.com/stable"
CACHE = ROOT / "fmp_cache"


def api_key() -> str:
    k = os.environ.get("FMP_API_KEY", "").strip()
    if not k:
        p = Path.home() / ".fmp_key"
        if p.exists():
            k = p.read_text().strip()
    if not k:
        raise RuntimeError("FMP key missing: set FMP_API_KEY (environment "
                           "settings) or create ~/.fmp_key")
    return k


def _get(path: str, params: dict, timeout: int = 120, retries: int = 6):
    q = dict(params or {})
    q["apikey"] = api_key()
    last = None
    for i in range(retries):
        try:
            r = requests.get(f"{BASE}/{path}", params=q, timeout=timeout)
        except requests.RequestException as e:
            # never echo the exception (its message contains the full URL)
            last = f"{type(e).__name__} on {path}"
            time.sleep(3 * (i + 1)); continue
        if r.status_code == 200:
            return r
        if r.status_code == 429:                 # bulk / rate limit window
            last = f"429 on {path}"
            time.sleep(20 + 10 * i); continue
        last = f"HTTP {r.status_code} on {path}"
        if r.status_code in (400, 401, 402, 403, 404):
            break
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"FMP request failed: {last}")


def get_json(path: str, **params):
    return _get(path, params).json()


def get_bulk_csv(path: str, cache_name: str | None = None,
                 max_age_hours: float = 20.0, **params) -> list[dict]:
    """Fetch a bulk CSV endpoint -> list of row dicts, with an on-disk cache
    so re-runs inside the freshness window don't burn the rate limit."""
    CACHE.mkdir(exist_ok=True)
    cf = CACHE / (cache_name or (path.replace("/", "_") + ".csv"))
    if cf.exists() and (time.time() - cf.stat().st_mtime) < max_age_hours * 3600:
        text = cf.read_text(encoding="utf-8", errors="ignore")
    else:
        text = _get(path, params, timeout=300).text
        cf.write_text(text, encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def daily_adjusted(symbol: str, start: str, end: str | None = None):
    """Dividend- and split-adjusted daily bars, ascending:
    [(date, open, high, low, close, volume)]. [] if the symbol is unknown."""
    params = {"symbol": symbol, "from": start}
    if end:
        params["to"] = end
    rows = get_json("historical-price-eod/dividend-adjusted", **params) or []
    out = []
    for r in rows:
        c = num(r.get("adjClose"))
        if c is None or c <= 0:
            continue
        out.append((r["date"], num(r.get("adjOpen")) or c, num(r.get("adjHigh")) or c,
                    num(r.get("adjLow")) or c, c, num(r.get("volume")) or 0.0))
    out.sort(key=lambda t: t[0])
    return out


def resample(daily, period: str):
    """Collapse daily bars to 'W' (ISO week), 'M' (month) or 'Q' (quarter):
    [(period_start_date, high, low, close)] -- close = last close in period."""
    import datetime as _dt
    buckets: dict = {}
    order = []
    for d, _o, h, l, c, _v in daily:
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        if period == "M":
            key, start = (y, m), f"{y:04d}-{m:02d}-01"
        elif period == "Q":
            q = (m - 1) // 3
            key, start = (y, q), f"{y:04d}-{q*3+1:02d}-01"
        else:
            iy, iw, _ = _dt.date(y, m, dd).isocalendar()
            key = (iy, iw)
            start = _dt.date.fromisocalendar(iy, iw, 1).isoformat()
        if key not in buckets:
            buckets[key] = [start, h, l, c]
            order.append(key)
        else:
            b = buckets[key]
            b[1] = max(b[1], h); b[2] = min(b[2], l); b[3] = c
    return [tuple(buckets[k]) for k in order]


def num(x):
    try:
        v = float(x)
        return v if v == v else None          # drop NaN
    except (TypeError, ValueError):
        return None
