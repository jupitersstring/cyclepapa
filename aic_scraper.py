"""AIC (theaic.co.uk) discount-data scraper.

The AIC find-compare-investment-companies page embeds the entire
investment-company database as JSON inside a `drupalSettings` script
tag. This module fetches that page, extracts the JSON, and exposes
a tidy dict of LSE EPIC code -> dict of fields (discount, NAV,
market cap, sector, etc.).

Public method: fetch_aic_discounts() -> dict[str, dict]

Cache: results are pickled to /tmp/aic_cache.pkl with TTL 24h to
avoid re-scraping during a session.
"""

from __future__ import annotations

import json
import os
import pickle
import re
import time
import urllib.request
from datetime import datetime
from typing import Any


AIC_URL = "https://www.theaic.co.uk/aic/find-compare-investment-companies"
CACHE_PATH = "/tmp/aic_cache.pkl"
CACHE_TTL_SECONDS = 24 * 3600

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


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


def fetch_aic_raw(use_cache: bool = True) -> dict[str, dict[str, Any]]:
    """Fetch and parse the AIC find-compare page; return EPIC->record dict.

    Each record contains the full set of fields the AIC publishes:
      DiscFairCum (current discount, negative=discount, percent),
      Disc1YAvgCF / Disc3YAvgCF / Disc5YAvgCF (historical avgs),
      OneyrHighCumFairDiscount / OneyrLowCumFairDiscount (52w range),
      MarketCap, ClosingPrice, NAVFAIRCUM, AICSECTOR, plus performance
      and liquidity columns.
    """
    if use_cache:
        cached = _read_cache()
        if cached is not None:
            return cached

    req = urllib.request.Request(AIC_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    m = re.search(
        r'data-drupal-selector="drupal-settings-json"[^>]*>([^<]+)</',
        html,
    )
    if not m:
        raise RuntimeError("AIC: drupal-settings-json block not found")

    data = json.loads(m.group(1))
    aic = data.get("aic", {})
    funds = aic.get("basic", [])

    by_epic: dict[str, dict[str, Any]] = {}
    for fund in funds:
        epic = (fund.get("EPICCode") or "").strip().upper()
        if not epic:
            continue
        by_epic[epic] = fund

    _write_cache(by_epic)
    return by_epic


def fetch_aic_discounts(use_cache: bool = True) -> dict[str, float]:
    """Convenience: return EPIC.L -> current discount (positive number,
    so 0.20 = 20% discount). Maps NAV premium to negative.

    AIC reports DiscFairCum as a signed percent where negative = discount
    (price below NAV). We invert the sign so positive = discount and
    return a fraction (so -13.94% AIC = 0.1394 here).
    """
    raw = fetch_aic_raw(use_cache=use_cache)
    out: dict[str, float] = {}
    for epic, rec in raw.items():
        d = rec.get("DiscFairCum")
        if d is None:
            continue
        try:
            disc_fraction = -float(d) / 100.0
        except (TypeError, ValueError):
            continue
        out[f"{epic}.L"] = disc_fraction
    return out


def fetch_aic_summary(use_cache: bool = True) -> dict[str, dict[str, float | str | None]]:
    """Richer dict per EPIC.L symbol — discount, 1y avg discount, 52w
    discount range, NAV, market cap, sector, liquidity proxy."""
    raw = fetch_aic_raw(use_cache=use_cache)
    out: dict[str, dict[str, float | str | None]] = {}
    for epic, rec in raw.items():
        sym = f"{epic}.L"

        def _num(k: str) -> float | None:
            v = rec.get(k)
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        def _disc(v: float | None) -> float | None:
            return -v / 100.0 if v is not None else None

        out[sym] = {
            "discount": _disc(_num("DiscFairCum")),
            "discount_1y_avg": _disc(_num("Disc1YAvgCF")),
            "discount_3y_avg": _disc(_num("Disc3YAvgCF")),
            "discount_5y_avg": _disc(_num("Disc5YAvgCF")),
            "discount_52w_high": _disc(_num("OneyrHighCumFairDiscount")),
            "discount_52w_low": _disc(_num("OneyrLowCumFairDiscount")),
            "nav": _num("NAVFAIRCUM"),
            "price": _num("ClosingPrice"),
            "market_cap_gbp_m": _num("MarketCap"),
            "ongoing_charge": _num("OngoingCharge"),
            "net_gearing": _num("NetGearCum"),
            "sector": rec.get("AICSECTOR"),
            "name": rec.get("Name"),
            "avg_value_traded_1m_gbp_m": _num("AvgValTrd1M"),
            "avg_value_traded_1y_gbp_m": _num("AvgValTrd1Y"),
            "data_as_at": rec.get("OngoingChargeDate"),
        }
    return out


if __name__ == "__main__":
    summary = fetch_aic_summary(use_cache=False)
    print(f"Fetched {len(summary)} UK CEFs from AIC")
    print(f"Cache written to {CACHE_PATH}")
    # Print top 10 widest discounts
    rows = []
    for sym, rec in summary.items():
        d = rec.get("discount")
        if d is not None and d > 0:
            rows.append((sym, d, rec.get("sector"), rec.get("name"),
                         rec.get("market_cap_gbp_m")))
    rows.sort(key=lambda r: -r[1])
    print(f"\n{'Ticker':<10} {'Disc%':>6}  {'Sector':<6}  {'MCap£m':>8}  Name")
    for sym, d, sect, nm, mc in rows[:20]:
        print(f"{sym:<10} {d*100:>6.2f}  {str(sect or '?'):<6}  "
              f"{(mc or 0):>8.1f}  {nm or '?'}")
