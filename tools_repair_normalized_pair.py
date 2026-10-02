#!/usr/bin/env python3
"""Repair normalized_ebit/normalized_ebitda for names whose 5yr averages
inverted (EBIT avg > EBITDA avg — impossible in any filing).

ROOT CAUSE (verified live, RNO.PA/Renault): the build aliases mixed BASES —
"EBITDA" (unusual items INCLUDED) with fallback "Normalized EBITDA"
(EXCLUDED), against "EBIT" (INCLUDED) with fallback "Operating Income"
(EXCLUDED) — and NaN years misaligned the two averages' year sets.

REPAIR: one self-consistent basis per year from the fundamentals-timeseries:
  ebitda_yr = annualEBITDA where present and >= annualEBIT (coherent),
              else annualEBIT + annualReconciledDepreciation (definitional,
              same-source within the filing year).
  Averages taken over the SAME year set for both measures (up to 5 years,
  >= 2 required).
"""
import json
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from ticker_yf import YahooSession

AFF = "/tmp/claude-0/-home-user-cyclepapa/1f6dce31-0b8c-5a05-99c8-0e4aa6117e8d/scratchpad/norm_ebit_affected.csv"
OUT = "/tmp/claude-0/-home-user-cyclepapa/1f6dce31-0b8c-5a05-99c8-0e4aa6117e8d/scratchpad/norm_pair_repaired.csv"
TYPES = "annualEBITDA,annualEBIT,annualReconciledDepreciation"

def fetch_one(sess, sym):
    p2 = int(time.time()); p1 = p2 - 6 * 365 * 86400
    url = (f"https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/"
           f"finance/timeseries/{urllib.parse.quote(sym)}"
           f"?type={TYPES}&period1={p1}&period2={p2}&merge=false")
    try:
        d = json.loads(sess.opener.open(url, timeout=15).read())
    except Exception:
        return None
    series = {}
    for res in (d.get("timeseries", {}).get("result") or []):
        for k in ("annualEBITDA", "annualEBIT", "annualReconciledDepreciation"):
            vals = res.get(k)
            if not vals:
                continue
            for v in vals:
                raw = (v.get("reportedValue") or {}).get("raw")
                dt = v.get("asOfDate")
                if raw is not None and dt:
                    series.setdefault(k, {})[dt] = raw
    if "annualEBIT" not in series:
        return None
    df = pd.DataFrame(series).sort_index(ascending=False)  # newest first
    ebit = df.get("annualEBIT")
    ebd = df.get("annualEBITDA")
    da = df.get("annualReconciledDepreciation")
    if ebit is None:
        return None
    # self-consistent per-year EBITDA
    if ebd is None:
        ebd = pd.Series(index=df.index, dtype=float)
    coherent = ebd.notna() & ebit.notna() & (ebd >= ebit)
    rebuilt = pd.Series(index=df.index, dtype=float)
    if da is not None:
        rebuilt = (ebit + da).where(ebit.notna() & da.notna() & (da >= 0))
    ebd_fixed = ebd.where(coherent)
    ebd_fixed = ebd_fixed.where(ebd_fixed.notna(), rebuilt)
    both = ebit.notna() & ebd_fixed.notna()
    e5 = ebit[both].iloc[:5]
    b5 = ebd_fixed[both].iloc[:5]
    if len(e5) < 2:
        return None
    ne, nb = float(e5.mean()), float(b5.mean())
    if ne > nb:      # still impossible after same-basis rebuild — refuse
        return None
    return {"symbol": sym, "normalized_ebit": ne, "normalized_ebitda": nb,
            "norm_years": int(len(e5))}

def main():
    aff = pd.read_csv(AFF)["symbol"].dropna().unique().tolist()
    print(f"{len(aff)} names to repair", flush=True)
    sess = YahooSession()
    rows, done = [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(lambda s: fetch_one(sess, s), aff):
            done += 1
            if r:
                rows.append(r)
            if done % 250 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(aff)} ({rate:.1f}/s, repaired {len(rows)}, "
                      f"ETA {(len(aff)-done)/rate/60:.1f}m)", flush=True)
                pd.DataFrame(rows).to_csv(OUT, index=False)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"DONE: repaired {len(rows)}/{len(aff)} -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
