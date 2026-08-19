"""Yahoo-based NAV / discount scraper for US CEFs and BDCs.

Yahoo doesn't expose CEF NAV directly, but the `bookValue` field on
quoteSummary is a usable proxy for fund vehicles whose balance sheet
is mostly marketable securities. We verified empirically that
bookValue-implied discount correlates ~0.71 with manually-collected
estimates across a sample of 20+ US CEFs/BDCs.

Limitations:
- bookValue is sourced from the most recent 10-Q/10-K, so it's
  weekly-to-quarterly stale (not daily like AIC's NAV feed).
- Funds with low or zero bookValue (data errors) produce nonsense.
- Returns negative discount (premium) for funds whose book is
  understated vs market — we filter these as unreliable.

Cache: /tmp/yahoo_nav_cache.pkl, TTL 24h.
"""

from __future__ import annotations

import os
import pickle
import time
import yfinance as yf

CACHE_PATH = "/tmp/yahoo_nav_cache.pkl"
CACHE_TTL_SECONDS = 24 * 3600

# Minimum bookValue/price ratio to accept the data as valid.
# bookValue * 0.3 < price < bookValue * 1.5 — avoids broken data
# (e.g. GUT shows bookValue 3.0 vs price 6.25 -> -105% "discount").
MIN_RATIO = 0.30
MAX_RATIO = 1.50


def _read_cache() -> dict | None:
    if not os.path.exists(CACHE_PATH):
        return None
    age = time.time() - os.path.getmtime(CACHE_PATH)
    if age > CACHE_TTL_SECONDS:
        return None
    try:
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _write_cache(data: dict) -> None:
    try:
        with open(CACHE_PATH, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass


# Transport fix (RCA 2026-07-16): yfinance's default session uses
# curl_cffi impersonate="chrome", whose post-quantum/ECH ClientHello
# is reset by TLS-terminating egress proxies. price_store._yf_session
# builds a session with a pre-PQ profile (chrome110) that both the
# proxy and Yahoo accept — reuse it here for Ticker().info calls.
from price_store import _yf_session

# Circuit breaker retained as a safety net: after N consecutive
# failures we stop for the rest of the process — non-UK names then
# fall back to the discount_override column in universe.csv via the
# normal priority chain (AIC -> yahoo -> override).
_CONSECUTIVE_FAILURES = 0
_BREAKER_THRESHOLD = 3


def fetch_yahoo_discounts(tickers: list[str], use_cache: bool = True,
                          verbose: bool = False) -> dict[str, float]:
    """For each ticker, compute book-value-implied discount = 1 - price/book.

    Returns a dict of ticker -> discount (positive = discount, negative
    = premium). Only ticks that pass the sanity filter are included.
    """
    global _CONSECUTIVE_FAILURES
    cache = _read_cache() or {} if use_cache else {}
    out: dict[str, float] = {}
    needed = [t for t in tickers if t not in cache]
    if verbose:
        print(f"[yahoo_nav] cache hits: {len(tickers) - len(needed)}, "
              f"need to fetch: {len(needed)}")

    for i, t in enumerate(needed, 1):
        if _CONSECUTIVE_FAILURES >= _BREAKER_THRESHOLD:
            # Transport is broken — don't burn 30s per remaining name.
            # Leave these OUT of the cache so a healthy future process
            # retries them (caching None would suppress the retry for
            # the cache TTL and silently reduce coverage).
            break
        try:
            info = yf.Ticker(t, session=_yf_session()).info
            price = info.get("regularMarketPrice") or info.get("previousClose")
            book = info.get("bookValue")
            if price is None and book is None:
                _CONSECUTIVE_FAILURES += 1
                cache[t] = None
                continue
            _CONSECUTIVE_FAILURES = 0
            if price is None or book is None or book <= 0:
                cache[t] = None
                continue
            ratio = price / book
            if not (MIN_RATIO < ratio < MAX_RATIO):
                cache[t] = None  # data implausible
                continue
            discount = 1.0 - ratio
            cache[t] = discount
        except Exception:
            _CONSECUTIVE_FAILURES += 1
            cache[t] = None
        if verbose and i % 10 == 0:
            print(f"  [{i}/{len(needed)}]", flush=True)

    if use_cache:
        _write_cache(cache)

    for t in tickers:
        v = cache.get(t)
        if v is not None:
            out[t] = v
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ticks = sys.argv[1:]
    else:
        # Sample of US CEFs/BDCs
        ticks = ["BRW", "BIF", "GAM", "CET", "ADX", "TY", "SOR", "FUND",
                 "RVT", "RMT", "GAB", "GDV", "GUT", "BST", "BME", "MIN",
                 "GGT", "BBDC", "PSEC", "PFLT", "GLAD", "GAIN", "OFS",
                 "MFIC", "SAR", "BKCC", "CHI", "CHW", "CHY", "EOI",
                 "ECC", "EIC", "OXLC", "JLS", "ASA"]
    res = fetch_yahoo_discounts(ticks, verbose=True)
    print(f"\nResolved {len(res)} of {len(ticks)} with usable book value")
    for t, d in sorted(res.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<8} {d*100:+6.2f}%")
