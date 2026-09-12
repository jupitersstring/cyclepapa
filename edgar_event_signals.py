#!/usr/bin/env python3
"""EDGAR event-driven signal harvest — the Special-Situations sleeve.

For every US filer (symbol->CIK from edgar_roic_roiic.csv) pulls, from the SEC
data.sec.gov APIs:

  * submissions.json  -> recent FORM TYPES (last ~24 months):
        - spin_flag        Form 10 registration (10-12B / 10-12G)  [spin-off]
        - tender_flag      SC TO-I / SC TO-T / SC 14D9              [tender offer]
        - merger_flag      DEFM14A / PREM14A                        [merger vote]
        - going_private    SC 13E3                                  [squeeze-out]
        - distress_flag    NT 10-K / NT 10-Q                        [late filing]
  * companyconcept OperatingLossCarryforwards -> nol_usd            [NOL shell]
  * companyconcept ReorganizationValue        -> reorg_flag         [post-reorg / fresh-start]

Emits edgar_event_signals.csv (one row per symbol). RESUMABLE: existing rows are
kept and their CIKs skipped, so the scrape can be run in foreground chunks
(--limit) or restarted after an interruption.

Index events (Russell reconstitution) are NOT here — EDGAR carries no index
membership; that needs a separate index feed.

Usage:
    python3 edgar_event_signals.py --limit 2000     # process 2000 not-yet-done CIKs
    python3 edgar_event_signals.py                  # process all remaining
"""
from __future__ import annotations
import argparse, gzip, json, os, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

OUT = "edgar_event_signals.csv"
MAP = "edgar_roic_roiic.csv"
UA = {"User-Agent": "multibagger-research opensource@multibagger.dev",
      "Accept-Encoding": "gzip, deflate"}
BASE_SUB = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
BASE_CONCEPT = ("https://data.sec.gov/api/xbrl/companyconcept/"
                "CIK{cik:010d}/us-gaap/{tag}.json")

# recent-window: a filing older than this many days no longer counts as a "live"
# event signal (a 2016 spin is history, not a current setup).
WINDOW_DAYS = 730
# Reorg gets a wider window than the form flags: a post-reorg equity keeps
# re-rating well past Verdad's ~2yr alpha window, so a 2021-22 emergence
# (Gulfport, Bristow) is still a valid cheap-emerger — but a 2009 fresh-start
# (Pilgrim's Pride, Lear) is not. 5 years captures the live cohort, drops the
# ancient ones.
REORG_WINDOW_DAYS = 1825

SPIN = {"10-12B", "10-12G", "10-12B/A", "10-12G/A"}
TENDER = {"SC TO-I", "SC TO-T", "SC 14D9", "SC TO-I/A", "SC 14D9/A"}
MERGER = {"DEFM14A", "PREM14A"}
GOINGPRIV = {"SC 13E3", "SC 13E3/A"}
DISTRESS = {"NT 10-K", "NT 10-Q"}

_rate_lock = threading.Lock()
_last = [0.0]
def _throttle(min_gap=0.11):
    with _rate_lock:
        dt = time.time() - _last[0]
        if dt < min_gap:
            time.sleep(min_gap - dt)
        _last[0] = time.time()


def _get(url):
    _throttle()
    req = urllib.request.Request(url, headers=UA)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw), None
    except urllib.error.HTTPError as e:
        return None, ("404" if e.code == 404 else f"http{e.code}")
    except Exception as e:
        return None, type(e).__name__


def _concept_latest(cik, tag):
    """(latest USD value, latest end-date) for an xbrl concept, or (None, None).
    USD-ONLY — a foreign filer's NOL is reported in its home currency (RMB/JPY);
    taking the first non-USD unit and treating it as dollars (the old fallback)
    inflated nol_usd and let RMB-210M shells fire the NOL screen. If the filer
    has no USD unit for the concept we simply do not have a comparable figure."""
    d, err = _get(BASE_CONCEPT.format(cik=cik, tag=tag))
    if not d:
        return None, None
    pts = d.get("units", {}).get("USD")
    if not pts:
        return None, None
    try:
        pts = sorted(pts, key=lambda p: p.get("end", ""))
        return float(pts[-1].get("val")), pts[-1].get("end", "")
    except Exception:
        return None, None


def _recent_forms(cik):
    """Return the set of forms filed in the last WINDOW_DAYS + latest dates."""
    d, err = _get(BASE_SUB.format(cik=cik))
    if not d:
        return None, err
    rec = d.get("filings", {}).get("recent", {})
    forms = rec.get("form", []) or []
    dates = rec.get("filingDate", []) or []
    cutoff = (pd.Timestamp.now() - pd.Timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    hits = {}
    for f, dt in zip(forms, dates):
        if dt >= cutoff:
            hits.setdefault(f, dt)
    return hits, None


def process(cik):
    hits, err = _recent_forms(cik)
    row = {"cik": cik, "spin_flag": 0, "spin_date": "", "tender_flag": 0,
           "merger_flag": 0, "going_private_flag": 0, "distress_flag": 0,
           "nol_usd": "", "reorg_flag": 0, "reorg_date": "", "err": err or ""}
    if hits is not None:
        def any_form(s):
            got = [(f, hits[f]) for f in hits if f in s]
            return got
        sp = any_form(SPIN)
        if sp:
            row["spin_flag"] = 1
            row["spin_date"] = max(d for _, d in sp)
        row["tender_flag"] = int(bool(any_form(TENDER)))
        row["merger_flag"] = int(bool(any_form(MERGER)))
        row["going_private_flag"] = int(bool(any_form(GOINGPRIV)))
        row["distress_flag"] = int(bool(any_form(DISTRESS)))
    # NOL + reorg concepts (light; 404 for the vast majority)
    nol, _ = _concept_latest(cik, "OperatingLossCarryforwards")
    if nol is not None:
        row["nol_usd"] = nol
    # Post-reorg fresh-start: flag ONLY when the ReorganizationValue mark is
    # RECENT. Verdad's post-reorg alpha is in the first ~2 years after
    # emergence; a 2009 fresh-start value that lingers in company facts (PPC,
    # LEA) is not a live special situation. Window it like the form flags.
    # BROADENED (spot-check finding): keying only on ReorganizationValue missed
    # ~19 of 20 known recent emergers (Hertz, Chord/Whiting, Valaris) — most
    # fresh-start filers never tag that concept, or it ages out while the
    # company is still re-rating. ReorganizationItems (the P&L reorg line) is
    # reported through emergence and the comparative periods after, and catches
    # them. Flag on EITHER concept, recent; the downstream archetype's
    # operating/not-melting/leverage gates exclude any name still IN bankruptcy.
    _cut = (pd.Timestamp.now() - pd.Timedelta(days=REORG_WINDOW_DAYS)).strftime("%Y-%m-%d")
    _reorg_ends = []
    rv, rv_end = _concept_latest(cik, "ReorganizationValue")
    if rv is not None and rv_end and rv_end >= _cut:
        _reorg_ends.append(rv_end)
    for _tag in ("ReorganizationItems", "ReorganizationItemsNet"):
        _ri, _ri_end = _concept_latest(cik, _tag)
        if _ri is not None and _ri_end and _ri_end >= _cut:
            _reorg_ends.append(_ri_end)
    if _reorg_ends:
        row["reorg_flag"] = 1
        row["reorg_date"] = max(_reorg_ends)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max CIKs this run (0=all)")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    m = pd.read_csv(MAP, low_memory=False)[["symbol", "cik"]].dropna()
    m["cik"] = pd.to_numeric(m["cik"], errors="coerce")
    m = m.dropna(subset=["cik"]).astype({"cik": int})
    cik2syms = m.groupby("cik")["symbol"].apply(list).to_dict()
    all_ciks = sorted(cik2syms)

    done = set()
    if os.path.exists(OUT):
        try:
            prev = pd.read_csv(OUT)
            done = set(pd.to_numeric(prev["cik"], errors="coerce").dropna().astype(int))
        except Exception:
            pass
    todo = [c for c in all_ciks if c not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(all_ciks)} CIKs total, {len(done)} done, processing {len(todo)}",
          file=sys.stderr)

    header = not os.path.exists(OUT)
    fh = open(OUT, "a")
    cols = ["symbol", "cik", "spin_flag", "spin_date", "tender_flag", "merger_flag",
            "going_private_flag", "distress_flag", "nol_usd", "reorg_flag",
            "reorg_date", "err"]
    if header:
        fh.write(",".join(cols) + "\n")
    start = time.time()
    n = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process, c): c for c in todo}
        for fut in as_completed(futs):
            c = futs[fut]
            try:
                row = fut.result()
            except Exception as e:
                row = {"cik": c, "err": type(e).__name__}
            for sym in cik2syms[c]:
                r = dict(row); r["symbol"] = sym
                fh.write(",".join(str(r.get(k, "")) for k in cols) + "\n")
            n += 1
            if n % 200 == 0:
                fh.flush()
                rate = n / max(1.0, time.time() - start)
                eta = (len(todo) - n) / rate if rate else 0
                print(f"  {n}/{len(todo)}  ({rate:.1f}/s, ETA {eta/60:.1f}m)",
                      file=sys.stderr)
    fh.close()
    print(f"done {n} CIKs in {(time.time()-start)/60:.1f}m", file=sys.stderr)


if __name__ == "__main__":
    main()
