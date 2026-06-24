#!/usr/bin/env python3
"""Whole-universe short-squeeze screen — runs where it HAS network (e.g. GitHub
Actions), since the bulk feeds aren't reachable from every sandbox.

It fetches IBKR's public shortable file (every ~5,600 currently-shortable US name:
borrow fee + availability, free, no account), enriches the highest-fee tail with
yfinance (short interest %, float, price, volume, institutional ownership), scores
everything with short_squeeze.assess, and writes a ranked report + CSV.

    python run_screen.py [--top-enrich N] [--country usa] [--out screen_output]

Robust to yfinance failures (common from datacenter IPs): a name that can't be
enriched is still scored on its IBKR borrow fee alone.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from short_squeeze import (
    SqueezeClass,
    SqueezeMetrics,
    fetch_ibkr_shortable_text,
    from_yfinance,
    parse_ibkr_shortable_text,
    rank_candidates,
    report,
    to_csv,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Whole-universe short-squeeze screen.")
    ap.add_argument("--top-enrich", type=int, default=150,
                    help="enrich the N highest-fee names with yfinance (SI/float/price)")
    ap.add_argument("--country", default="usa")
    ap.add_argument("--out", default="screen_output")
    args = ap.parse_args()

    print(f"[screen] fetching IBKR shortable file ({args.country}) ...", flush=True)
    rows = parse_ibkr_shortable_text(fetch_ibkr_shortable_text(args.country))
    print(f"[screen] {len(rows)} shortable names parsed.", flush=True)
    if not rows:
        print("[screen] no rows — aborting.", flush=True)
        return 1

    by_fee = sorted(rows.values(), key=lambda r: (r.fee_rate_pct or 0.0), reverse=True)
    enrich = {r.symbol for r in by_fee[: args.top_enrich]}
    print(f"[screen] enriching top {len(enrich)} by fee with yfinance ...", flush=True)

    metrics, ok, fail = [], 0, 0
    for r in by_fee:
        if r.symbol in enrich:
            try:
                m = from_yfinance(r.symbol, borrow_fee_pct=r.fee_rate_pct)
                m.shortable_shares_available = r.available
                m.as_of = r.as_of
                metrics.append(m)
                ok += 1
                time.sleep(0.15)
                continue
            except Exception as e:  # yfinance is flaky from cloud IPs — best effort
                fail += 1
                print(f"[warn] yfinance {r.symbol}: {type(e).__name__}", flush=True)
        metrics.append(SqueezeMetrics(
            ticker=r.symbol, borrow_fee_pct=r.fee_rate_pct,
            shortable_shares_available=r.available, as_of=r.as_of, source="ibkr_file"))

    print(f"[screen] enriched ok={ok} fail={fail}; scoring {len(metrics)} names ...", flush=True)
    ranked = rank_candidates(metrics)

    os.makedirs(args.out, exist_ok=True)
    rep = report(ranked, top=50)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(rep + "\n")
    with open(os.path.join(args.out, "candidates.csv"), "w", encoding="utf-8") as f:
        f.write(to_csv(ranked))

    print(rep, flush=True)
    fuel = [a.ticker for a in ranked if a.classification == SqueezeClass.SQUEEZE_FUEL]
    coiled = [a.ticker for a in ranked if a.coiled_spring is not None and a.coiled_spring.triggered]
    print(f"\n[screen] universe={len(ranked)}  SQUEEZE_FUEL={len(fuel)}: {fuel[:25]}", flush=True)
    print(f"[screen] COILED (good R/R)={len(coiled)}: {coiled[:25]}", flush=True)
    print(f"[screen] wrote {args.out}/report.txt and {args.out}/candidates.csv", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
