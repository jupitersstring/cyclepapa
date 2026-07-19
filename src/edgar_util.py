#!/usr/bin/env python3
"""
edgar_util.py — shared EDGAR full-text-search parsing helpers.

EDGAR's FTS `display_names` field embeds the ticker(s) and CIK in a
fixed format: "ISSUER NAME  (TICKER[, TICKER2])  (CIK 0000000000)".
The dedicated `tickers` field is frequently null, so the reliable way
to recover a clean issuer name + ticker is to parse display_names.

Centralising this here keeps every EDGAR-based poller (edgar_poll,
sc13d_poll, form15_poll, postreorg_poll, eightk_items_poll,
spinoff_radar) consistent, so downstream (inbox_promote, corroborate,
universe_screen) sees real tickers instead of "CIK:0000000000".
"""

from __future__ import annotations

import re
import time

# "NAME  (TICKER[, TICKER2 ...])  (CIK 0000000000)"
_DN_TICKER = re.compile(
    r"\(([A-Z][A-Z0-9.\-]{0,7}(?:,\s*[A-Z0-9.\-]{1,8})*)\)\s*\(CIK")
_DN_CIK = re.compile(r"\(CIK\s*(\d{6,10})\)")
# Strip the trailing "(TICKER) (CIK ...)" OR bare "(CIK ...)" suffix.
_DN_STRIP = re.compile(
    r"\s*(?:\((?:[A-Z0-9.,\-\s]+)?\)\s*)?\(CIK\s*\d+\).*$")


def parse_display_name(display_names) -> tuple[str, str | None, str | None]:
    """Return (clean_name, primary_ticker, cik) from an EDGAR display_names
    value (list or str). Ticker/cik are None when absent (e.g. an issuer
    with no listed common, or a fund/trust)."""
    if not display_names:
        return "", None, None
    if isinstance(display_names, (list, tuple)):
        dn = display_names[0] if display_names else ""
    else:
        dn = str(display_names)
    dn = dn.strip()
    tk_m = _DN_TICKER.search(dn)
    ticker = None
    if tk_m:
        # first ticker of a comma list; drop worthless placeholders
        first = tk_m.group(1).split(",")[0].strip().upper()
        if first and first not in ("NONE", "N/A", "-"):
            ticker = first
    cik_m = _DN_CIK.search(dn)
    cik = cik_m.group(1) if cik_m else None
    # Clean name = everything before the "(TICKER) (CIK ...)" suffix
    clean = _DN_STRIP.sub("", dn).strip()
    clean = re.sub(r"\s{2,}", " ", clean)
    if not clean:
        clean = dn
    return clean, ticker, cik


_CIK_TICKER_MAP: dict[str, str] | None = None
_CIK_TICKER_CACHE = None  # Path set lazily to avoid import cycle


def _cik_ticker_map() -> dict[str, str]:
    """Load SEC's CIK→ticker map (company_tickers.json), cached to disk so
    the screener works offline after the first fetch. Returns {} on any
    failure — resolution is best-effort."""
    global _CIK_TICKER_MAP
    if _CIK_TICKER_MAP is not None:
        return _CIK_TICKER_MAP
    _CIK_TICKER_MAP = {}
    import json
    import os
    from pathlib import Path
    cache = (Path(__file__).resolve().parent.parent
             / "data" / "cik_ticker_map.json")
    data = None
    if cache.exists():
        try:
            data = json.loads(cache.read_text())
        except (json.JSONDecodeError, OSError):
            data = None
    if data is None:
        try:
            import requests
            ua = os.environ.get("EDGAR_USER_AGENT",
                                "cyclepapa-screener research@example.com")
            r = requests.get("https://www.sec.gov/files/company_tickers.json",
                             headers={"User-Agent": ua}, timeout=30)
            r.raise_for_status()
            raw = r.json()
            data = {str(v["cik_str"]): v["ticker"] for v in raw.values()}
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, sort_keys=True))
        except Exception:
            data = {}
    # Normalise keys to un-padded string CIKs
    for k, v in (data or {}).items():
        _CIK_TICKER_MAP[str(int(k))] = v
    return _CIK_TICKER_MAP


def resolve_cik_to_ticker(cik: str | int | None) -> str | None:
    """Best-effort CIK → ticker. Accepts padded or unpadded CIK."""
    if not cik:
        return None
    try:
        key = str(int(str(cik).lstrip("0") or "0"))
    except ValueError:
        return None
    return _cik_ticker_map().get(key)


EDGAR_FTS = "https://efts.sec.gov/LATEST/search-index"


def fts_search_all(params: dict, headers: dict, *, retries: int = 4,
                   page_pause: float = 0.12, max_results: int = 10000,
                   log=None) -> list[dict]:
    """Return ALL EDGAR full-text-search hits for a query, paginating through
    the API's fixed 10-per-page window.

    Every EDGAR FTS poller that read only `hits.hits` from a single request
    was silently catching just the first 10 matches per query — the
    framework's cardinal under-catch. This helper is the one correct place
    to page: it walks `from` in steps of 10 until the result set is
    exhausted or EDGAR's 10,000-hit ceiling is reached, and (via `log`)
    reports when the ceiling truncates so the miss is never silent.

    `params` is the base query (q, forms, startdt, enddt, ...) WITHOUT
    `from`. Returns the concatenated list of raw hit dicts.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover
        return []
    from urllib.parse import urlencode

    out: list[dict] = []
    from_ = 0
    total = None
    while True:
        p = dict(params)
        if from_:
            p["from"] = from_
        url = f"{EDGAR_FTS}?{urlencode(p)}"
        delay = 1.0
        page = {}
        for attempt in range(retries):
            try:
                r = requests.get(url, headers=headers, timeout=30)
                if r.status_code == 429:
                    time.sleep(delay); delay *= 2
                    continue
                r.raise_for_status()
                page = r.json().get("hits", {}) or {}
                break
            except requests.RequestException:
                if attempt == retries - 1:
                    page = {}
                    break
                time.sleep(delay); delay *= 2
        hits = page.get("hits", []) or []
        if total is None:
            tv = page.get("total", {})
            total = tv.get("value") if isinstance(tv, dict) else None
        out.extend(hits)
        if len(hits) < 10:
            break
        from_ += 10
        ceiling = min(int(total), max_results) if total is not None else max_results
        if from_ >= ceiling:
            if total is not None and int(total) > max_results and log:
                log(f"    (EDGAR returned {total} hits; capped at "
                    f"{max_results} — narrow the date window to catch the tail)")
            break
        time.sleep(page_pause)
    return out


def issuer_fields(source: dict) -> dict:
    """Convenience: pull normalised {name, ticker, cik} from an EDGAR
    FTS _source dict, preferring parsed display_names over the flaky
    tickers field."""
    name, ticker, cik = parse_display_name(source.get("display_names"))
    if not ticker and source.get("tickers"):
        t = source["tickers"]
        ticker = (t[0] if isinstance(t, (list, tuple)) and t else
                  (t if isinstance(t, str) else None))
    if not cik:
        ciks = source.get("ciks") or []
        cik = ciks[0] if ciks else None
    if not name:
        name = source.get("name") or ""
    return {"name": name, "ticker": ticker, "cik": cik}
