"""Graham quality-adjusted Net-Net Working Capital (NNWC) from the EDGAR cache.

Naive NCAV counts every current asset at 100%. Graham's NNWC haircuts them by
liquidation reliability — cash 100%, receivables 85%, inventory 50%, other
current assets 0% — then subtracts ALL liabilities (+ preferred + minority).
This is what separates a safe CASH net-net from an INVENTORY net-net, and it
naturally deflates a finance-company "net-net" whose current assets are a
subprime loan book (receivables) rather than cash.

  NNWC = cash + 0.85*receivables + 0.50*inventory - total_liabilities
         - preferred - minority_interest

(audit P0-4) ONE REPORTING PERIOD, TOTAL LIABILITIES ONLY.
  The old implementation let every component independently pick its own
  greatest `end` date (490 rows mixed cash and liabilities >100 days apart),
  and when total liabilities were missing it silently substituted CURRENT
  liabilities (636 rows; 213 of them then showed a positive "NNWC" against a
  workbook that promised "all liabilities"). Both are corrected here:
    * every component is read at ONE common balance-sheet date — the latest
      period end at which BOTH cash and TOTAL liabilities are reported;
    * if total liabilities are never reported, NNWC is NOT computed (null) —
      current liabilities are never a stand-in;
    * the period end and the liability basis are emitted as provenance.

Reads edgar_cache/*.json.gz (offline). Output: nnwc.csv (symbol-keyed):
  nnwc, nnwc_cash, nnwc_receivables, nnwc_inventory, nnwc_total_liab,
  nnwc_asset_mix (cash share of the haircut assets — higher = safer),
  nnwc_period_end (the common balance-sheet date), nnwc_liab_basis ('total')
"""
import glob
import gzip
import json
import os
import sys
from collections import defaultdict

import pandas as pd

CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash", "CashAndCashEquivalentsAtCarryingValueIncludingDiscontinuedOperations"]
RECV = ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsAndOtherReceivablesNetCurrent"]
INV = ["InventoryNet", "InventoryFinishedGoodsNetOfReserves"]
TOT_LIAB = ["Liabilities"]
PREF = ["PreferredStockValue", "PreferredStockValueOutstanding", "TemporaryEquityCarryingAmountAttributableToParent"]
NCI = ["MinorityInterest"]


def _by_end(g, concepts, unit="USD"):
    """{period_end: value} for the FIRST alias that has data, honouring the
    latest filing per period where `filed` provenance is present (a restated
    figure replaces the original); falls back to last-listed otherwise."""
    for c in concepts:
        obs = (g.get(c, {}) or {}).get("units", {}).get(unit, [])
        if not obs:
            continue
        out, filed_at = {}, {}
        for o in obs:
            end, val = o.get("end"), o.get("val")
            if not end or val is None:
                continue
            f = str(o.get("filed") or "")
            if end not in out or f >= filed_at.get(end, ""):
                out[end] = val
                filed_at[end] = f
        if out:
            return out
    return {}


def main():
    tickers_by_cik = defaultdict(list)
    if os.path.exists("edgar_universe_facts.csv"):
        ef = pd.read_csv("edgar_universe_facts.csv", low_memory=False)
        for _, r in ef.iterrows():
            try:
                tickers_by_cik[int(r["cik"])].append(r["symbol"])
            except Exception:
                pass

    rows = []
    n_no_total_liab = 0
    files = glob.glob("edgar_cache/*.json.gz")
    for i, f in enumerate(files):
        if i % 1500 == 0:
            print(f"  {i}/{len(files)}", file=sys.stderr)
        try:
            cik = int(os.path.basename(f).replace("CIK", "").replace(".json.gz", ""))
        except Exception:
            continue
        syms = tickers_by_cik.get(cik)
        if not syms:
            continue
        try:
            g = json.loads(gzip.open(f, "rt").read()).get("facts", {}).get("us-gaap", {})
        except Exception:
            continue
        cash_by, liab_by = _by_end(g, CASH), _by_end(g, TOT_LIAB)
        if not liab_by:
            n_no_total_liab += 1      # never substitute current liabilities
            continue
        # ONE common balance-sheet date: latest end reported for BOTH cash and
        # total liabilities (every other component is read at that same date).
        common = sorted(set(cash_by) & set(liab_by))
        if not common:
            continue
        end = common[-1]
        recv_by, inv_by = _by_end(g, RECV), _by_end(g, INV)
        pref_by, nci_by = _by_end(g, PREF), _by_end(g, NCI)
        c = cash_by[end]
        tliab = liab_by[end]
        r = recv_by.get(end)
        iv = inv_by.get(end)
        pref = pref_by.get(end, 0) or 0
        nci = nci_by.get(end, 0) or 0
        haircut_assets = c + 0.85 * (r or 0) + 0.50 * (iv or 0)
        nnwc = haircut_assets - tliab - pref - nci
        mix = (c / haircut_assets) if haircut_assets > 0 else None
        base = {
            "nnwc": nnwc, "nnwc_cash": c, "nnwc_receivables": r,
            "nnwc_inventory": iv, "nnwc_total_liab": tliab,
            "nnwc_asset_mix": round(mix, 3) if mix is not None else None,
            "nnwc_period_end": end, "nnwc_liab_basis": "total",
        }
        for sym in syms:
            rows.append({"symbol": sym, **base})

    out = pd.DataFrame(rows).drop_duplicates("symbol")
    out.to_csv("nnwc.csv", index=False)
    print(f"symbols with NNWC: {len(out)} | positive NNWC: {int((out['nnwc'] > 0).sum())} "
          f"| skipped (no total liabilities reported): {n_no_total_liab}", file=sys.stderr)


if __name__ == "__main__":
    main()
