"""Thin, hardened FMP (Financial Modeling Prep) client for the *stable* API.

Scope: this module only fetches and caches. No analytical logic lives here.
The mapping from FMP fields onto our schema lives in ``fmp_enrich.py`` so the
provenance boundary (FMP is a secondary, tagged, DQ-gated source that never
overwrites an EDGAR-primary value) stays in one auditable place.

Security
  * The API key is read from ``FMP_API_KEY`` ONLY. It is never written to a
    tracked file, a cache path, or a log line, and a missing key raises so a
    run fails loudly instead of shipping half-populated columns.
  * Legacy ``/api/v3`` is retired for post-2025-08-31 keys, so we speak only
    to ``/stable``.

Caching (the part that has to be world class)
  The cache is the durable, re-runnable substrate for tens of thousands of
  per-symbol calls on a disk we do not have much of, so it is built for
  integrity, thrift, and self-limiting size:

    * Envelope + integrity: every entry is a JSON envelope carrying meta
      (endpoint, fetched_at, status, sdk version) plus the payload. Writes
      are atomic (unique tmp + ``os.replace``) and corruption or a schema
      bump is treated as a miss, never a crash.
    * Compression: entries are gzipped on disk (``.json.gz``). FMP payloads
      are highly compressible JSON; this typically cuts footprint ~4-8x,
      which is decisive when free disk is measured in hundreds of MB.
    * Negative caching: a 404 or an empty body is cached (with a shorter
      TTL) so thousands of symbols FMP does not cover are not re-hammered on
      every run. This is where most of the wasted calls would otherwise go.
    * Sharding: keys are hashed into 256 sub-directories so no single
      directory holds tens of thousands of files.
    * Per-type TTL: prices are stale in a day, executive comp and
      fundamentals in a week+; callers pass the right ``TTL_*`` constant.
    * Bounded size (LRU): ``cache_gc(max_bytes)`` evicts oldest-by-access
      until the cache is under budget, so it can never fill the disk.
    * Observability: hit/miss/write/evict counters via ``cache_stats()``.
    * Connection reuse: a single pooled ``requests.Session`` with a
      transport-level retry for connect/read errors; 429 and FMP's
      200-with-"Limit Reach" body are handled explicitly with backoff,
      because a status-based retry cannot see a limit error dressed as 200.

Bulk CSV endpoints are *streamed* row-by-row into a callback and never
materialised whole; their filtered output (a small CSV) is its own cache.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import threading
import time
from typing import Callable, Iterable

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 ships with requests; Retry path differs across versions
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None

STABLE = "https://financialmodelingprep.com/stable"
CACHE_DIR = os.environ.get("FMP_CACHE_DIR", "fmp_cache")
_SCHEMA = 2  # bump to invalidate every existing entry on an envelope change

# Per-type TTLs (seconds). Callers pick the one that matches the data's
# half-life instead of a single global guess.
TTL_PRICE = 12 * 3600           # intraday-ish figures
TTL_ESTIMATE = 3 * 24 * 3600    # analyst estimates / surprises
TTL_FUNDAMENTAL = 7 * 24 * 3600 # statements, ratios, key metrics
TTL_SLOW = 30 * 24 * 3600       # executive comp, historical insider filings
TTL_NEGATIVE = 3 * 24 * 3600    # 404 / empty — re-probe occasionally, not daily
_DEFAULT_TTL = TTL_FUNDAMENTAL

_stats = {"hit": 0, "miss": 0, "write": 0, "neg_hit": 0, "evict": 0, "net": 0}
_stats_lock = threading.Lock()
_session: requests.Session | None = None
_session_lock = threading.Lock()


class FMPError(RuntimeError):
    pass


def _bump(counter: str, n: int = 1) -> None:
    with _stats_lock:
        _stats[counter] += n


def cache_stats() -> dict:
    """Snapshot of cache counters plus on-disk size and entry count."""
    with _stats_lock:
        snap = dict(_stats)
    total = req = _stats["hit"] + _stats["neg_hit"] + _stats["miss"]
    snap["hit_rate"] = round((snap["hit"] + snap["neg_hit"]) / total, 4) if total else None
    nbytes = nfiles = 0
    if os.path.isdir(CACHE_DIR):
        for root, _dirs, files in os.walk(CACHE_DIR):
            for f in files:
                if f.endswith(".json.gz"):
                    try:
                        nbytes += os.path.getsize(os.path.join(root, f)); nfiles += 1
                    except OSError:
                        pass
    snap["disk_bytes"] = nbytes
    snap["disk_mb"] = round(nbytes / 1_048_576, 1)
    snap["entries"] = nfiles
    return snap


def _key() -> str:
    k = os.environ.get("FMP_API_KEY", "").strip()
    if not k:
        raise FMPError(
            "FMP_API_KEY is not set. Export it from the untracked env file "
            "before running FMP enrichment; the key must never be committed."
        )
    return k


def _session_get(url: str, **kw) -> requests.Response:
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                s = requests.Session()
                retry = None
                if Retry is not None:
                    # Transport-level retry for connect/read only. Status
                    # codes (429/5xx) are handled by us with FMP-aware
                    # backoff, so status_forcelist stays empty here.
                    retry = Retry(total=3, connect=3, read=3, backoff_factor=0.5,
                                  status_forcelist=[], allowed_methods=["GET"])
                adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=retry)
                s.mount("https://", adapter)
                s.headers.update({"Accept-Encoding": "gzip"})
                _session = s
    return _session.get(url, **kw)


def _cache_path(cache_key: str) -> str:
    h = hashlib.sha1(f"v{_SCHEMA}:{cache_key}".encode()).hexdigest()
    return os.path.join(CACHE_DIR, h[:2], h + ".json.gz")


def _cache_read(cpath: str, ttl: float, neg_ttl: float):
    """Return (found, payload). Honours TTL and negative-entry TTL.

    A corrupt, truncated, or schema-mismatched entry counts as not found so
    a bad file self-heals on the next fetch instead of poisoning a run.
    """
    try:
        with gzip.open(cpath, "rt", encoding="utf-8") as fh:
            env = json.load(fh)
    except (OSError, EOFError, json.JSONDecodeError):
        return False, None
    if not isinstance(env, dict) or env.get("_v") != _SCHEMA:
        return False, None
    age = time.time() - env.get("fetched_at", 0)
    is_neg = env.get("status") == 404 or env.get("empty") is True
    if age >= (neg_ttl if is_neg else ttl):
        return False, None
    # refresh atime for LRU eviction ordering (best effort)
    try:
        os.utime(cpath, None)
    except OSError:
        pass
    return True, env.get("data")


def _cache_write(cpath: str, endpoint: str, data, status: int) -> None:
    env = {
        "_v": _SCHEMA,
        "endpoint": endpoint,
        "fetched_at": time.time(),
        "status": status,
        "empty": (data == [] or data is None),
        "data": data,
    }
    os.makedirs(os.path.dirname(cpath), exist_ok=True)
    tmp = f"{cpath}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(env, fh, separators=(",", ":"))
        os.replace(tmp, cpath)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    _bump("write")


def get_json(
    endpoint: str,
    params: dict | None = None,
    *,
    cache_key: str | None = None,
    ttl: float = _DEFAULT_TTL,
    neg_ttl: float = TTL_NEGATIVE,
    max_attempts: int = 5,
    cache: bool = True,
) -> list | dict | None:
    """GET a *stable* JSON endpoint, cached (positive AND negative).

    ``endpoint`` is the path after ``/stable/`` (e.g. ``"profile"``).
    Returns parsed JSON (usually a list), or ``None`` for a cached/live 404.
    ``cache=False`` neither reads nor writes the disk cache — for bulky
    payloads (daily price history) the caller reduces immediately and stores
    its own compact form instead.
    """
    params = dict(params or {})
    ck = cache_key or (endpoint + "?" + "&".join(f"{x}={params[x]}" for x in sorted(params)))
    cpath = _cache_path(ck)
    found, payload = _cache_read(cpath, ttl, neg_ttl) if cache else (False, None)
    if found:
        _bump("neg_hit" if (payload is None or payload == []) else "hit")
        return payload

    params["apikey"] = _key()
    url = f"{STABLE}/{endpoint}"
    delay = 2.0
    for attempt in range(1, max_attempts + 1):
        try:
            r = _session_get(url, params=params, timeout=40)
        except requests.RequestException as exc:
            _bump("net")
            if attempt == max_attempts:
                raise FMPError(f"{endpoint}: network error after {attempt} tries: {exc}")
            time.sleep(delay); delay *= 2; continue
        if r.status_code == 404:
            if cache:
                _cache_write(cpath, endpoint, None, 404)
            _bump("miss")
            return None
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == max_attempts:
                raise FMPError(f"{endpoint}: HTTP {r.status_code} after {attempt} tries")
            time.sleep(delay); delay *= 2; continue
        if r.status_code != 200:
            raise FMPError(f"{endpoint}: HTTP {r.status_code}: {r.text[:160]}")
        try:
            data = r.json()
        except ValueError as exc:
            raise FMPError(f"{endpoint}: non-JSON body: {exc}")
        if isinstance(data, dict) and "Error Message" in data:
            msg = str(data["Error Message"])
            if "Limit Reach" in msg and attempt < max_attempts:
                time.sleep(delay); delay *= 2; continue
            raise FMPError(f"{endpoint}: {msg[:160]}")
        if cache:
            _cache_write(cpath, endpoint, data, 200)
        _bump("miss")
        return data
    return None


def cache_gc(max_bytes: int, *, reserve: float = 0.9) -> dict:
    """Evict least-recently-used entries until under ``max_bytes``.

    Ordering is by file mtime, which ``_cache_read`` refreshes on every hit,
    so hot symbols survive and cold ones are shed first. ``reserve`` sweeps
    a little below the cap so the GC is not re-triggered on the next write.
    Returns a small report.
    """
    if not os.path.isdir(CACHE_DIR):
        return {"evicted": 0, "freed_bytes": 0, "final_bytes": 0}
    entries = []
    total = 0
    for root, _dirs, files in os.walk(CACHE_DIR):
        for f in files:
            if not f.endswith(".json.gz"):
                continue
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, p)); total += st.st_size
    if total <= max_bytes:
        return {"evicted": 0, "freed_bytes": 0, "final_bytes": total}
    target = int(max_bytes * reserve)
    entries.sort()  # oldest access first
    freed = evicted = 0
    for _mtime, size, p in entries:
        if total - freed <= target:
            break
        try:
            os.remove(p); freed += size; evicted += 1
        except OSError:
            pass
    _bump("evict", evicted)
    return {"evicted": evicted, "freed_bytes": freed, "final_bytes": total - freed}


def stream_bulk_csv(
    endpoint: str,
    row_cb: Callable[[dict], None],
    *,
    params: dict | None = None,
    max_attempts: int = 4,
) -> int:
    """Stream a *bulk* CSV endpoint row-by-row into ``row_cb``.

    The payload (tens of MB) is parsed incrementally and never stored whole;
    the caller's filtered output is its own (small, durable) cache. Returns
    the number of data rows seen.
    """
    params = dict(params or {})
    params["apikey"] = _key()
    url = f"{STABLE}/{endpoint}"
    delay = 3.0
    for attempt in range(1, max_attempts + 1):
        try:
            with _session_get(url, params=params, stream=True, timeout=180) as r:
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt == max_attempts:
                        raise FMPError(f"{endpoint}: HTTP {r.status_code} after {attempt} tries")
                    time.sleep(delay); delay *= 2; continue
                if r.status_code != 200:
                    raise FMPError(f"{endpoint}: HTTP {r.status_code}: {r.text[:160]}")
                r.encoding = "utf-8"
                lines = r.iter_lines(decode_unicode=True)
                header_line = next(lines, None)
                if not header_line:
                    return 0
                if header_line.lstrip().startswith("{"):
                    raise FMPError(f"{endpoint}: expected CSV, got JSON: {header_line[:160]}")
                header = next(csv.reader(io.StringIO(header_line)))
                n = 0
                for line in lines:
                    if not line:
                        continue
                    row = next(csv.reader(io.StringIO(line)), None)
                    if row is None or len(row) != len(header):
                        continue
                    row_cb(dict(zip(header, row)))
                    n += 1
                return n
        except requests.RequestException as exc:
            if attempt == max_attempts:
                raise FMPError(f"{endpoint}: stream error after {attempt} tries: {exc}")
            time.sleep(delay); delay *= 2
    return 0


def get_many(
    endpoint_for: Callable[[str], tuple[str, dict]],
    symbols: Iterable[str],
    *,
    ttl: float = _DEFAULT_TTL,
    pace: float = 0.05,
    progress_every: int = 500,
    gc_every: int = 2000,
    gc_max_bytes: int | None = None,
) -> dict[str, list | dict | None]:
    """Fetch a per-symbol endpoint for many symbols: cached, paced, bounded.

    ``gc_max_bytes`` (if set) caps the on-disk cache; the LRU GC runs every
    ``gc_every`` symbols so a very large sweep can never exhaust the disk.
    """
    out: dict[str, list | dict | None] = {}
    syms = list(dict.fromkeys(symbols))
    for i, sym in enumerate(syms, 1):
        endpoint, params = endpoint_for(sym)
        try:
            out[sym] = get_json(endpoint, params, ttl=ttl)
        except FMPError as exc:
            out[sym] = None
            if "Limit Reach" in str(exc) or "429" in str(exc):
                raise
        if pace:
            time.sleep(pace)
        if progress_every and i % progress_every == 0:
            st = cache_stats()
            print(f"  fmp get_many: {i}/{len(syms)} | hit_rate={st['hit_rate']} "
                  f"| cache {st['disk_mb']}MB/{st['entries']}", flush=True)
        if gc_max_bytes and gc_every and i % gc_every == 0:
            cache_gc(gc_max_bytes)
    return out
