"""Quarterly balance-sheet + cash-flow + employee history for the multibagger latent-
cluster study sample (the 10,160 symbols of the base-breakout case-control
sample: every symbol with a base explosion + 8,000 random controls, weighted
w_cc to the population). Cached on disk by fmp_client; the study reads the
same calls back as cache hits. Income statements, grades, earnings, targets,
insider statistics and 13D/G are already cached by event_study_pit.fetch.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

import fmp_client as fc


def _get(ep, params):
    for attempt in range(12):
        try:
            return fc.get_json(ep, params, ttl=fc.TTL_SLOW) or []
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                time.sleep(30 * (attempt + 1))
                continue
            return []
    return []


def fetch_bs_cf(sym: str) -> dict:
    return {"symbol": sym,
            "bs": _get("balance-sheet-statement", {"symbol": sym, "period": "quarter", "limit": 80}),
            "cf": _get("cash-flow-statement", {"symbol": sym, "period": "quarter", "limit": 80}),
            # SEC filers: employees per 10-K / 10-Q, filing-dated (point-in-time)
            "emp": _get("historical-employee-count", {"symbol": sym, "limit": 100}),
            # FMP's own period-end multiples / ratios (currency-consistent with
            # the statements): valuation at a later month-end = the period-end
            # multiple rolled forward by the price move since the period end
            "km": _get("key-metrics", {"symbol": sym, "period": "quarter", "limit": 80}),
            "ra": _get("ratios", {"symbol": sym, "period": "quarter", "limit": 80})}


def main(workers: int = 6) -> None:
    syms = (pd.read_parquet("base_panel_pit.parquet", columns=["symbol"])["symbol"]
            .drop_duplicates().tolist())
    print(f"bs/cf: {len(syms)} symbols", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, _ in enumerate(ex.map(fetch_bs_cf, syms), 1):
            if i % 1000 == 0:
                print(f"  {i}/{len(syms)} | hit_rate={fc.cache_stats()['hit_rate']}", flush=True)
    print("MB_FETCH_DONE", flush=True)


if __name__ == "__main__":
    main()
