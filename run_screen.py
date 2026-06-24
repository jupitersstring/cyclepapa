#!/usr/bin/env python3
"""Whole-universe short-squeeze screen — runs where it HAS network (e.g. GitHub
Actions), since the bulk feeds aren't reachable from every sandbox.

Primary path: IBKR's public shortable file over FTP (every ~5,600 currently-
shortable US name: borrow fee + availability, free, no account), with the
highest-fee tail enriched via yfinance.

Fallback: GitHub-hosted runners (and many clouds) BLOCK outbound FTP, so when the
IBKR FTP is unreachable the script screens a built-in most-shorted universe via
yfinance over HTTPS instead (short interest, float, price, volume, institutional
ownership) — fees absent, so it's the crowded-short / liquidity half of the model.

    python run_screen.py [--top-enrich N] [--country usa] [--out screen_output]
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

# Built-in most-shorted / high-fee universe (gathered from current screens) used
# when IBKR FTP is blocked. Extend freely — yfinance fills SI%/float/price/DTC.
FALLBACK_UNIVERSE = [
    "GRPN", "ELF", "CHWY", "NRDY", "NTLA", "RH", "LCID", "EVGO", "CLSK", "CSIQ",
    "ASAN", "AI", "IBRX", "SRPT", "UPST", "BEAM", "BTDR", "TRIP", "NVAX", "BYND",
    "RCKT", "PRME", "SVRA", "LYFT", "BIRD", "RXRX", "INDI", "BBAI", "MARA", "RNA",
    "RUM", "SNDX", "CORZ", "PCRX", "WULF", "RUN", "KOD", "ARRY", "ABCL", "MDGL",
    "CRMD", "ARCT", "PATH", "OCGN", "PLAY", "XRX", "PRAX", "TWST", "KRYS", "AEHL",
    "PCT", "FLWS", "HTZ", "SOUN", "SPRY", "FLNC", "SERV", "WGS", "EOSE", "SATS",
    "HIMS", "NFE", "IOVA", "RXT", "CRML", "PGY", "MPT", "ENVX", "TMDX", "KRUS",
]


def _ibkr_universe(country: str, top_enrich: int, min_fee: float) -> list:
    rows = parse_ibkr_shortable_text(fetch_ibkr_shortable_text(country, timeout=20))
    if not rows:
        raise RuntimeError("IBKR file parsed empty")
    by_fee = sorted(rows.values(), key=lambda r: (r.fee_rate_pct or 0.0), reverse=True)
    # Enrich the whole "special" set (fee >= min_fee), not just the absurd-fee
    # microcap tail — the real candidates live in the ~10-60% fee band.
    special = [r for r in by_fee if (r.fee_rate_pct or 0.0) >= min_fee][:top_enrich]
    enrich = {r.symbol for r in special}
    print(f"[screen] IBKR: {len(rows)} shortable names; enriching {len(enrich)} with "
          f"fee >= {min_fee}% via yfinance (the squeeze-relevant 'special' set)", flush=True)
    out = []
    for r in by_fee:
        if r.symbol in enrich:
            m = _try_yf(r.symbol, r.fee_rate_pct)
            if m is not None:
                m.shortable_shares_available = r.available
                m.as_of = r.as_of
                out.append(m)
                continue
        out.append(SqueezeMetrics(ticker=r.symbol, borrow_fee_pct=r.fee_rate_pct,
                                  shortable_shares_available=r.available, as_of=r.as_of, source="ibkr_file"))
    return out


def _try_yf(ticker: str, borrow_fee_pct=None):
    try:
        m = from_yfinance(ticker, borrow_fee_pct=borrow_fee_pct)
        time.sleep(0.15)
        return m
    except Exception as e:  # yfinance is flaky from datacenter IPs
        print(f"[warn] yfinance {ticker}: {type(e).__name__}", flush=True)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Whole-universe short-squeeze screen.")
    ap.add_argument("--top-enrich", type=int, default=1000,
                    help="cap on how many 'special' names to enrich with yfinance")
    ap.add_argument("--min-fee", type=float, default=5.0,
                    help="enrich names whose borrow fee >= this %% (the 'special' set)")
    ap.add_argument("--country", default="usa")
    ap.add_argument("--out", default="screen_output")
    args = ap.parse_args()

    source = ""
    try:
        print("[screen] trying IBKR shortable file (FTP) ...", flush=True)
        metrics = _ibkr_universe(args.country, args.top_enrich, args.min_fee)
        source = "IBKR full shortable universe (borrow fee + availability) + yfinance enrichment"
    except Exception as e:
        print(f"[warn] IBKR FTP unreachable ({type(e).__name__}: {e}); "
              f"falling back to yfinance over the built-in most-shorted universe (NO fees).", flush=True)
        metrics = [m for m in (_try_yf(t) for t in FALLBACK_UNIVERSE) if m is not None]
        source = "yfinance most-shorted universe (borrow fee ABSENT — crowded-short/liquidity half only)"

    print(f"[screen] scoring {len(metrics)} names ...", flush=True)
    ranked = rank_candidates(metrics)

    os.makedirs(args.out, exist_ok=True)
    header = f"# source: {source}\n# universe size: {len(ranked)}\n\n"
    rep = report(ranked, top=50)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write(header + rep + "\n")
    with open(os.path.join(args.out, "candidates.csv"), "w", encoding="utf-8") as f:
        f.write(to_csv(ranked))

    print("\n" + header + rep, flush=True)
    fuel = [a.ticker for a in ranked if a.classification == SqueezeClass.SQUEEZE_FUEL]
    coiled = [a.ticker for a in ranked if a.coiled_spring is not None and a.coiled_spring.triggered]
    print(f"\n[screen] universe={len(ranked)}  SQUEEZE_FUEL={len(fuel)}: {fuel[:25]}", flush=True)
    print(f"[screen] COILED (good R/R)={len(coiled)}: {coiled[:25]}", flush=True)
    if not ranked:
        print("[screen] WARNING: no names scored (all data sources failed from this runner).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
