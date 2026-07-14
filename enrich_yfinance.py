"""Enrich the universe with yfinance mcap, drawdown, and valuation
fundamentals. Resumable: skips tickers already present.

Builds the canonical valuation overlay used by unified_composite.py.
Conservative rate-limiting (0.25s/ticker) and rolling JSON checkpoint
every 25 tickers so a crash mid-run loses at most a small batch."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "yfinance_quick.json"


def fetch_one(yf, tk: str) -> dict | None:
    try:
        info = yf.Ticker(tk).info or {}
    except Exception as e:
        return {"_error": str(e)[:120]}
    if not info or not info.get("marketCap"):
        return None
    return {
        "name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "mcap": info.get("marketCap"),
        "price": info.get("currentPrice") or info.get("previousClose"),
        "fwk_low": info.get("fiftyTwoWeekLow"),
        "fwk_high": info.get("fiftyTwoWeekHigh"),
        "p_b": info.get("priceToBook"),
        "p_s": info.get("priceToSalesTrailing12Months"),
        "p_e_trailing": info.get("trailingPE"),
        "p_e_forward": info.get("forwardPE"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "ev_revenue": info.get("enterpriseToRevenue"),
        "enterprise_value": info.get("enterpriseValue"),
        "peg_ratio": info.get("trailingPegRatio") or info.get("pegRatio"),
        "profit_margin": info.get("profitMargins"),
        "roa": info.get("returnOnAssets"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "fcf": info.get("freeCashflow"),
        "op_cf": info.get("operatingCashflow"),
        "short_pct": info.get("shortPercentOfFloat"),
        "inst_pct": info.get("heldPercentInstitutions"),
        "insider_pct": info.get("heldPercentInsiders"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="unified_composite.csv",
                    help="Source CSV whose 'ticker' column drives the universe.")
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--checkpoint-every", type=int, default=25)
    args = ap.parse_args()

    try:
        import yfinance as yf  # noqa: F401
    except ImportError:
        print("yfinance not installed; pip install yfinance", file=sys.stderr)
        return 1
    import yfinance as yf

    src = ROOT / args.source
    tickers = [r["ticker"] for r in csv.DictReader(open(src))]
    print(f"Source {args.source}: {len(tickers)} tickers", file=sys.stderr)

    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    print(f"Existing yfinance_quick.json: {len(existing)} tickers",
          file=sys.stderr)

    n_added = 0
    n_failed = 0
    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        if tk in existing:
            continue
        try:
            row = fetch_one(yf, tk)
        except Exception as e:
            row = {"_error": str(e)[:120]}
        # BUGFIX (silent-drop audit): persisting _error rows made
        # `if tk in existing: continue` permanently skip a ticker after
        # one transient fetch failure (rate-limit/TLS), so it never
        # retried. Count the failure but do NOT persist it -> retried
        # next run.
        if row and "_error" not in row:
            existing[tk] = row
            n_added += 1
        else:
            n_failed += 1
        time.sleep(args.sleep)
        if i % args.checkpoint_every == 0:
            tmp = OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing, indent=2, default=str))
            tmp.replace(OUT)
            print(f"  [{i}/{len(tickers)}] added={n_added} failed={n_failed}",
                  file=sys.stderr, flush=True)

    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2, default=str))
    tmp.replace(OUT)
    print(f"\nWrote {OUT} (total {len(existing)} tickers; "
          f"added {n_added}, failed {n_failed})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
