"""Fill the FMP per-symbol cache for every live name: threaded, resumable,
cache-aware, NO eviction (the LRU GC in the pull scripts is what emptied the
cache of profile / key-metrics / ratios / estimates / grades / dividends /
segments for all 46.5k names — audit 2026-10: every surviving entry was <= 4.5
days old).

    python fmp_fill_cache.py --sets estimates,keymetrics,ratios --workers 8
    python fmp_fill_cache.py --list            # the endpoint sets

A set = (endpoint, params-without-symbol, ttl). Symbols come from
asymmetry_global.csv (live = has price and market cap, unless --all). A symbol
already cached (positive OR negative, within ttl) costs nothing. 429 / "Limit
Reach" pauses the whole pool (exponential back-off from 60 s). Progress and the
per-set tally go to stderr; the run is resumable at any point.
"""
from __future__ import annotations

import argparse, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import fmp_client as fc

SETS = {
    # perception
    "estimates": ("analyst-estimates", {"period": "annual", "limit": 4}, fc.TTL_ESTIMATE),
    "grades_hist": ("grades-historical", {"limit": 500}, fc.TTL_ESTIMATE),
    "grades": ("grades", {"limit": 2000}, fc.TTL_ESTIMATE),
    "pt_news": ("price-target-news", {"limit": 1000}, fc.TTL_ESTIMATE),
    "pt_summary": ("price-target-summary", {}, fc.TTL_ESTIMATE),
    "earnings": ("earnings", {"limit": 100}, fc.TTL_ESTIMATE),
    # fundamentals (annual histories; TTM ratios come from the bulk files)
    "keymetrics": ("key-metrics", {"period": "annual", "limit": 8}, fc.TTL_FUNDAMENTAL),
    "ratios": ("ratios", {"period": "annual", "limit": 8}, fc.TTL_FUNDAMENTAL),
    "growth": ("financial-growth", {"period": "annual", "limit": 12}, fc.TTL_FUNDAMENTAL),
    "ev_annual": ("enterprise-values", {"period": "annual", "limit": 4}, fc.TTL_FUNDAMENTAL),
    "ev_quarter": ("enterprise-values", {"period": "quarter", "limit": 13}, fc.TTL_FUNDAMENTAL),
    "owner_earnings": ("owner-earnings", {"limit": 6}, fc.TTL_FUNDAMENTAL),
    "is_annual": ("income-statement", {"period": "annual", "limit": 8}, fc.TTL_FUNDAMENTAL),
    "bs_annual": ("balance-sheet-statement", {"period": "annual", "limit": 8}, fc.TTL_FUNDAMENTAL),
    "cf_annual": ("cash-flow-statement", {"period": "annual", "limit": 8}, fc.TTL_FUNDAMENTAL),
    "is_quarter": ("income-statement", {"period": "quarter", "limit": 13}, fc.TTL_FUNDAMENTAL),
    "bs_quarter": ("balance-sheet-statement", {"period": "quarter", "limit": 9}, fc.TTL_FUNDAMENTAL),
    "cf_quarter": ("cash-flow-statement", {"period": "quarter", "limit": 9}, fc.TTL_FUNDAMENTAL),
    # identity / events / ownership
    "profile": ("profile", {}, fc.TTL_SLOW),
    "dividends": ("dividends", {"limit": 200}, fc.TTL_FUNDAMENTAL),
    "seg_product": ("revenue-product-segmentation", {"period": "annual"}, fc.TTL_SLOW),
    "seg_geo": ("revenue-geographic-segmentation", {"period": "annual"}, fc.TTL_SLOW),
    "exec_comp": ("governance-executive-compensation", {}, fc.TTL_SLOW),
    "employees": ("historical-employee-count", {"limit": 100}, fc.TTL_SLOW),
    "insider_stats": ("insider-trading/statistics", {}, fc.TTL_SLOW),
    "float": ("shares-float", {}, fc.TTL_FUNDAMENTAL),
    "splits": ("splits", {"limit": 50}, fc.TTL_SLOW),
}
_pause = threading.Event()        # set while the pool is backing off
_lock = threading.Lock()


def _one(ep, params, sym, ttl, tally):
    while _pause.is_set():
        time.sleep(1.0)
    p = dict(params); p["symbol"] = sym
    try:
        r = fc.get_json(ep, p, ttl=ttl)
        with _lock:
            tally["neg" if (r is None or r == []) else "ok"] += 1
    except fc.FMPError as exc:
        msg = str(exc)
        if "429" in msg or "Limit Reach" in msg:
            with _lock:
                tally["429"] += 1
            if not _pause.is_set():
                _pause.set()
                delay = min(60.0 * (2 ** tally.get("backoffs", 0)), 900.0)
                tally["backoffs"] = tally.get("backoffs", 0) + 1
                print(f"  429 -> pausing {delay:.0f}s", file=sys.stderr, flush=True)
                time.sleep(delay)
                _pause.clear()
            return _one(ep, params, sym, ttl, tally)
        with _lock:
            tally["err"] += 1
    except Exception:
        with _lock:
            tally["err"] += 1


def run_set(name, symbols, workers):
    ep, params, ttl = SETS[name]
    tally = {"ok": 0, "neg": 0, "err": 0, "429": 0}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_one, ep, params, s, ttl, tally) for s in symbols]
        for i, _ in enumerate(as_completed(futs), 1):
            if i % 2000 == 0:
                st = fc.cache_stats()
                print(f"  {name}: {i}/{len(symbols)} ok={tally['ok']} neg={tally['neg']} err={tally['err']} "
                      f"net={st['net']} {time.time()-t0:.0f}s", file=sys.stderr, flush=True)
    print(f"{name}: done {len(symbols)} | ok={tally['ok']} neg={tally['neg']} err={tally['err']} 429s={tally['429']} "
          f"| {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="estimates,keymetrics,ratios")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--all", action="store_true", help="every symbol, not only live (price + market cap)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, (ep, p, ttl) in SETS.items():
            print(f"{k:16s} {ep} {p}")
        sys.exit(0)
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "price", "market_cap_usd"], low_memory=False)
    if not a.all:
        g = g[g.price.notna() & g.market_cap_usd.notna()]
    syms = g.symbol.astype(str).drop_duplicates().tolist()
    print(f"symbols: {len(syms)} | sets: {a.sets} | workers {a.workers}", flush=True)
    for name in a.sets.split(","):
        name = name.strip()
        if name not in SETS:
            print("unknown set:", name, file=sys.stderr); continue
        run_set(name, syms, a.workers)
