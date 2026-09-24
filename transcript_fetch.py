"""Earnings-call transcript store (FMP), for call_intent.py.

Universe: every US-listed name in the quote store with mcap >= $30M and a
validated P/B <= 1.5 (where "will management act on the discount?" is the
question), plus every name in the governance-discount and mechanism layers.
For each, the last --n calls are cached gzip-compressed under
fmp_cache/transcripts/{SYMBOL}/{YEAR}Q{Q}.json.gz (gitignored). Calls already
cached are never re-fetched; only the dates index is refreshed (weekly).

Usage: python3 transcript_fetch.py [--n 10] [--workers 8] [--limit N]
"""

from __future__ import annotations

import argparse
import gzip
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
STORE = ROOT / "fmp_cache" / "transcripts"


def universe() -> list[str]:
    def load(n):
        p = ROOT / n
        return json.loads(p.read_text()) if p.exists() else {}
    yq = load("yfinance_quick.json")
    names = {t for t, v in yq.items()
             if (v.get("mcap") or 0) >= 3e7 and v.get("p_b") and v["p_b"] <= 1.5}
    names |= set(load("governance_discount.json")) | set(load("mechanism_gates.json"))
    return sorted(t for t in names if t and "." not in t and "/" not in t)


def dates(sym):
    d = STORE / sym
    d.mkdir(parents=True, exist_ok=True)
    f = d / "_dates.json"
    if f.exists() and time.time() - f.stat().st_mtime < 7 * 86400:
        return json.loads(f.read_text())
    try:
        rows = fmp.get_json("earning-call-transcript-dates", symbol=sym) or []
    except RuntimeError:
        rows = []
    f.write_text(json.dumps(rows))
    return rows


def fetch_one(sym, n):
    rows = dates(sym)
    # dedupe by (fiscalYear, quarter), newest call date first
    seen, calls = set(), []
    for r in sorted(rows, key=lambda r: r.get("date") or "", reverse=True):
        k = (r.get("fiscalYear"), r.get("quarter"))
        if None in k or k in seen:
            continue
        seen.add(k); calls.append(k)
    got = 0
    for fy, q in calls[:n]:
        f = STORE / sym / f"{fy}Q{q}.json.gz"
        if f.exists():
            continue
        try:
            d = fmp.get_json("earning-call-transcript", symbol=sym, year=fy, quarter=q) or []
        except RuntimeError:
            d = []
        if d and d[0].get("content"):
            rec = {k: d[0].get(k) for k in ("symbol", "period", "year", "date", "content")}
            with gzip.open(f, "wt", encoding="utf-8") as fh:
                json.dump(rec, fh)
            got += 1
    return sym, len(calls), got


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="calls per name (newest first)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    syms = universe()
    if args.limit:
        syms = syms[: args.limit]
    print(f"transcripts: {len(syms)} names x up to {args.n} calls")
    tot_new = with_calls = 0
    with ThreadPoolExecutor(args.workers) as ex:
        futs = [ex.submit(fetch_one, s, args.n) for s in syms]
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                _s, n_calls, got = fu.result()
            except Exception:
                continue
            tot_new += got
            with_calls += n_calls > 0
            if i % 200 == 0:
                print(f"  {i}/{len(syms)} names, {tot_new} new transcripts", flush=True)
    n_files = sum(1 for _ in STORE.glob("*/*.json.gz"))
    print(f"done: {with_calls}/{len(syms)} names have calls; {tot_new} fetched; "
          f"{n_files} transcripts cached")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
