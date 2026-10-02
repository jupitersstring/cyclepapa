#!/usr/bin/env python3
"""Targeted update: re-fetch ONLY ReorganizationValue for every CIK in
edgar_event_signals.csv and recompute reorg_flag/reorg_date under the wider
5-year window (Verdad cheap-emerger cohort). Leaves all other columns intact.
Much cheaper than a full 3-concept re-scrape."""
import gzip, json, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

CSV = "edgar_event_signals.csv"
UA = {"User-Agent": "multibagger-research opensource@multibagger.dev",
      "Accept-Encoding": "gzip, deflate"}
URL = ("https://data.sec.gov/api/xbrl/companyconcept/"
       "CIK{cik:010d}/us-gaap/ReorganizationValue.json")
WIN = 1825
_lock = threading.Lock(); _last = [0.0]

def _throttle(g=0.11):
    with _lock:
        dt = time.time() - _last[0]
        if dt < g:
            time.sleep(g - dt)
        _last[0] = time.time()

def latest(cik):
    _throttle()
    try:
        r = urllib.request.urlopen(urllib.request.Request(URL.format(cik=cik), headers=UA), timeout=30)
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        pts = json.loads(raw).get("units", {}).get("USD")
        if not pts:
            return None
        pts = sorted(pts, key=lambda p: p.get("end", ""))
        return pts[-1].get("end", "")
    except Exception:
        return None

def main():
    df = pd.read_csv(CSV, low_memory=False)
    ciks = sorted(set(pd.to_numeric(df["cik"], errors="coerce").dropna().astype(int)))
    cut = (pd.Timestamp.now() - pd.Timedelta(days=WIN)).strftime("%Y-%m-%d")
    print(f"{len(ciks)} CIKs; reorg cutoff {cut}", file=sys.stderr)
    flag, date = {}, {}
    start = time.time(); n = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(latest, c): c for c in ciks}
        for fut in as_completed(futs):
            c = futs[fut]; end = fut.result()
            if end and end >= cut:
                flag[c] = 1; date[c] = end
            n += 1
            if n % 500 == 0:
                print(f"  {n}/{len(ciks)} ({n/max(1,time.time()-start):.1f}/s)", file=sys.stderr)
    _ci = pd.to_numeric(df["cik"], errors="coerce")
    df["reorg_flag"] = _ci.map(flag).fillna(0).astype(int)
    df["reorg_date"] = _ci.map(date).fillna("")
    df.to_csv(CSV, index=False)
    print(f"done: {sum(flag.values())} reorg flags (5yr window)", file=sys.stderr)

if __name__ == "__main__":
    main()
