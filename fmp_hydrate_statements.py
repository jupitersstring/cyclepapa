"""Hydrate the per-symbol statement cache from the statement-bulk frames.

The engines (fmp_quarterly, fmp_statements, fmp_throughcycle, the cycle
extractors) read per-symbol cache entries:
  income-statement / balance-sheet-statement / cash-flow-statement
  period=annual limit=8   and   period=quarter limit=13 (income) / 9 (balance, cash flow)
The bulk frames (fmp_cache/bulk/*-statement-bulk__period-P_year-Y.parquet, one
call per year x period for the whole market) carry the same rows with the same
field names. This writes, for every symbol that LACKS an entry (or for all with
--overwrite), the per-symbol list newest-first in the API's shape, through
fmp_client's own envelope, so nothing downstream changes.

    python fmp_hydrate_statements.py            # fill missing entries only
    python fmp_hydrate_statements.py --overwrite
"""
from __future__ import annotations

import argparse, glob, os, sys, time
import numpy as np, pandas as pd

import fmp_client as fc

BULK = os.path.join(fc.CACHE_DIR, "bulk")
EPS = {"income-statement": "income-statement-bulk", "balance-sheet-statement": "balance-sheet-statement-bulk",
       "cash-flow-statement": "cash-flow-statement-bulk"}
LIMITS = {("income-statement", "annual"): 8, ("income-statement", "quarter"): 13,
          ("balance-sheet-statement", "annual"): 8, ("balance-sheet-statement", "quarter"): 9,
          ("cash-flow-statement", "annual"): 8, ("cash-flow-statement", "quarter"): 9}
TEXT = {"date", "symbol", "reportedCurrency", "cik", "filingDate", "acceptedDate", "fiscalYear", "period"}


def load_bulk(bulk_ep: str, kind: str) -> pd.DataFrame:
    pat = f"{bulk_ep}__period-{'FY' if kind == 'annual' else 'Q*'}_year-*.parquet"
    files = sorted(glob.glob(os.path.join(BULK, pat)))
    if not files:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    d = d[d.symbol.notna() & d.date.notna()]
    for c in d.columns:
        if c not in TEXT:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["fiscalYear"] = d["fiscalYear"].astype(str)
    return d.drop_duplicates(["symbol", "date", "period"]).sort_values(["symbol", "date"], ascending=[True, False])


def rows_to_api(df: pd.DataFrame) -> list[dict]:
    out = []
    for rec in df.to_dict("records"):
        out.append({k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in rec.items()})
    return out


def main(overwrite: bool, only_symbols: set | None):
    written = skipped = 0
    for ep, bulk_ep in EPS.items():
        for kind in ("annual", "quarter"):
            t0 = time.time()
            d = load_bulk(bulk_ep, kind)
            if d.empty:
                print(f"{ep} {kind}: no bulk frames", flush=True); continue
            lim = LIMITS[(ep, kind)]
            n_w = n_s = 0
            for sym, g in d.groupby("symbol", sort=False):
                if only_symbols is not None and sym not in only_symbols:
                    continue
                params = {"symbol": sym, "period": kind, "limit": lim}
                ck = ep + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
                cpath = fc._cache_path(ck)
                if not overwrite and os.path.exists(cpath):
                    n_s += 1; continue
                data = rows_to_api(g.head(lim))
                fc._cache_write(cpath, ep, data, 200)
                n_w += 1
            written += n_w; skipped += n_s
            print(f"{ep} {kind}: bulk symbols {d.symbol.nunique():,} | written {n_w:,} | already cached {n_s:,} | {time.time()-t0:.0f}s", flush=True)
    print(f"total written {written:,} | skipped {skipped:,}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--universe-only", action="store_true", help="only symbols in asymmetry_global.csv")
    a = ap.parse_args()
    syms = None
    if a.universe_only:
        syms = set(pd.read_csv("asymmetry_global.csv", usecols=["symbol"], low_memory=False).symbol.astype(str))
    main(a.overwrite, syms)
