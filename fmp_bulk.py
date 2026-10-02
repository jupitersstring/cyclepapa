"""Cached FMP *bulk* frames (profile-bulk, ratios-ttm-bulk, key-metrics-ttm-bulk,
scores-bulk, peers-bulk, eod-bulk, *-statement-bulk ...) -> parquet under
fmp_cache/bulk/, one file per (endpoint, params).

Why: a bulk CSV answers for the whole market in one call where the per-symbol
route costs ~46k calls, but fmp_client.stream_bulk_csv is uncached and
profile-bulk rate-limits a second call within ~2 minutes (HTTP 429). This
module persists every bulk pull, honours a TTL, and backs off >= 60 s on 429.

    import fmp_bulk as fb
    prof = fb.get_bulk_frame("profile-bulk", {"part": 0}, ttl=fb.TTL_WEEK)
    parts = fb.profile_all()          # parts 0..N until an empty part

Run as a script to pull the standard set:  python fmp_bulk.py [--what profile,ratios,...]
"""
from __future__ import annotations

import argparse, os, sys, time
import pandas as pd

import fmp_client as fc

BULK_DIR = os.path.join(fc.CACHE_DIR, "bulk")
TTL_DAY, TTL_WEEK, TTL_MONTH = 86400.0, 7 * 86400.0, 30 * 86400.0
_LAST_CALL: dict[str, float] = {}           # endpoint -> epoch of the last live call
MIN_GAP = {"profile-bulk": 90.0}           # seconds between live calls per endpoint


def _path(endpoint: str, params: dict | None) -> str:
    tag = endpoint.replace("/", "_")
    if params:
        tag += "__" + "_".join(f"{k}-{params[k]}" for k in sorted(params))
    return os.path.join(BULK_DIR, tag + ".parquet")


def get_bulk_frame(endpoint: str, params: dict | None = None, *, ttl: float = TTL_WEEK,
                   max_attempts: int = 5, backoff: float = 60.0) -> pd.DataFrame:
    """The bulk CSV as a DataFrame, from parquet when younger than ``ttl``."""
    os.makedirs(BULK_DIR, exist_ok=True)
    p = _path(endpoint, params)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        return pd.read_parquet(p)
    gap = MIN_GAP.get(endpoint, 0.0)
    rows: list[dict] = []
    for attempt in range(max_attempts):
        wait = gap - (time.time() - _LAST_CALL.get(endpoint, 0.0))
        if wait > 0:
            time.sleep(wait)
        rows.clear()
        try:
            _LAST_CALL[endpoint] = time.time()
            n = fc.stream_bulk_csv(endpoint, rows.append, params=params, max_attempts=1)
            break
        except Exception as exc:                        # 429 / 5xx / transport
            if "HTTP 400" in str(exc) or "HTTP 404" in str(exc):   # no such part / period: an empty frame, not an outage
                df = pd.DataFrame()
                df.to_parquet(p, index=False)
                print(f"  bulk {endpoint} {params}: empty ({str(exc)[:60]})", file=sys.stderr, flush=True)
                return df
            if attempt == max_attempts - 1:
                raise
            delay = backoff * (2 ** attempt)
            print(f"  bulk {endpoint} {params}: {str(exc)[:80]} -> sleep {delay:.0f}s", file=sys.stderr, flush=True)
            time.sleep(delay)
    df = pd.DataFrame(rows)
    df.to_parquet(p, index=False)
    print(f"  bulk {endpoint} {params or ''}: {len(df):,} rows -> {os.path.basename(p)}", file=sys.stderr, flush=True)
    return df


def profile_all(ttl: float = TTL_WEEK, max_parts: int = 12) -> pd.DataFrame:
    """profile-bulk parts 0.. until a part comes back empty (rate-limited: 90 s apart)."""
    frames = []
    for part in range(max_parts):
        d = get_bulk_frame("profile-bulk", {"part": part}, ttl=ttl)
        if d.empty:
            break
        frames.append(d)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return out.drop_duplicates("symbol") if "symbol" in out else out


STANDARD = {
    "profile": lambda: profile_all(),
    "ratios": lambda: get_bulk_frame("ratios-ttm-bulk"),
    "keymetrics": lambda: get_bulk_frame("key-metrics-ttm-bulk"),
    "scores": lambda: get_bulk_frame("scores-bulk"),
    "peers": lambda: get_bulk_frame("peers-bulk", ttl=TTL_MONTH),
    "grades": lambda: get_bulk_frame("upgrades-downgrades-consensus-bulk"),
    "targets": lambda: get_bulk_frame("price-target-summary-bulk"),
    "statements_list": lambda: get_bulk_frame("financial-statement-symbol-list", ttl=TTL_MONTH),
    "latest_statements": lambda: get_bulk_frame("latest-financial-statements", ttl=TTL_DAY),
    "eod": lambda: get_bulk_frame("eod-bulk", {"date": pd.Timestamp.today().normalize().strftime("%Y-%m-%d")}, ttl=TTL_DAY),
}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", default=",".join(STANDARD), help="comma list of " + ",".join(STANDARD))
    a = ap.parse_args()
    for w in a.what.split(","):
        w = w.strip()
        if w not in STANDARD:
            print("unknown:", w, file=sys.stderr); continue
        try:
            d = STANDARD[w]()
            print(f"{w}: {len(d):,} rows, {d.shape[1]} cols", flush=True)
        except Exception as exc:
            print(f"{w}: FAILED {str(exc)[:160]}", flush=True)
