#!/usr/bin/env python3
"""
Provenance / coverage audit — proves the methodology ranks the ENTIRE live
universe from the cached data, with no reliance on remembered names.

Checks:
  1) COVERAGE  — of the targeted universe (mega->micro across all regions),
     what fraction of LIVE names (excluding tombstoned delistings) is in the
     ranked cache. Should be ~100%.
  2) NO PHANTOMS — every name surfaced in the latest breadth CSVs is a real
     ticker in universe∩cache (nothing invented / from memory).
  3) REPRODUCIBLE — recomputing a random sample's breadth net directly from the
     cache reproduces the committed CSV value bit-for-bit.

  python3 audit_coverage.py [YYYY-MM-DD]
"""
from __future__ import annotations

import glob
import json
import os
import random
import re
import sys
import warnings

import pandas as pd

from midcap_weekly_anomalies import REGIONS

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, ".cache")
RESULTS = os.path.join(ROOT, "results")
TARGET = {"Mega Cap", "Large Cap", "Mid Cap", "Small Cap", "Micro Cap"}  # exclude Nano


def targeted_universe() -> set[str]:
    import financedatabase as fd
    eq = fd.Equities()
    syms = set()
    for rc, (country, exch, ccy, suf) in REGIONS.items():
        df = eq.select(country=country)
        df = df[df["exchange"].isin(exch) & (df["currency"] == ccy)
                & (df["market_cap"].isin(TARGET))]
        pat = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$") if suf is None else \
            re.compile(rf"^[A-Z0-9]{{1,5}}(-[A-Z])?\.{suf}$")
        for t in df.index:
            ts = str(t).replace(".", "-") if suf is None else str(t)
            if pat.match(ts):
                syms.add(ts)
    return syms


def main(date=None):
    date = date or sorted(g.split("_daily_")[-1][:-4]
                          for g in glob.glob(os.path.join(RESULTS, "breadth_*_daily_*.csv")))[-1]
    uni = targeted_universe()
    dl = set(pd.read_pickle(os.path.join(CACHE, "ohlcvdict_1d_20y.pkl")).keys())
    dead_p = os.path.join(CACHE, "dead_1d.json")
    dead = set(json.load(open(dead_p))) if os.path.exists(dead_p) else set()
    live = uni - dead
    ranked = uni & dl

    print(f"=== 1) COVERAGE (targeted universe, mega->micro, {len(REGIONS)} regions) ===")
    print(f"  targeted={len(uni)}  ranked(in cache)={len(ranked)}  "
          f"delisted(tombstoned)={len(uni & dead)}  live-unfetched={len(live - dl)}")
    print(f"  coverage of LIVE targeted universe = {100*len(ranked)/max(len(live),1):.1f}%")

    surfaced = set()
    for f in glob.glob(os.path.join(RESULTS, f"breadth_*_daily_{date}.csv")):
        surfaced |= set(pd.read_csv(f)["symbol"])
    phantom = surfaced - uni
    print(f"\n=== 2) NO PHANTOMS ({date}) ===")
    print(f"  surfaced={len(surfaced)}  phantom(not in universe)={len(phantom)}  "
          f"not-in-cache={len(surfaced - dl)}  -> {'PASS' if not phantom and surfaced<=dl else 'FAIL'}")

    print(f"\n=== 3) REPRODUCIBLE (recompute net from cache vs committed CSV) ===")
    import measure_bandpass as mb
    files = glob.glob(os.path.join(RESULTS, f"breadth_us-midcap_daily_{date}.csv"))
    if files:
        csv = pd.read_csv(files[0]).set_index("symbol")
        cache = pd.read_pickle(os.path.join(CACHE, "ohlcvdict_1d_20y.pkl"))
        random.seed(7)
        ok = True
        for s in random.sample(list(csv.index), min(4, len(csv))):
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                r = mb.scan({s: cache[s]}, "daily", 5, 13, {s: "?"}, {s: "?"}, "B1", 999, 999)
            got = int(r["net"].iloc[0]) if len(r) else 0
            want = int(csv.loc[s, "net"])
            print(f"  {s}: recomputed={got} csv={want}  {'MATCH' if got==want else 'MISMATCH'}")
            ok &= got == want
        print(f"  -> {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
