"""Graham quality-adjusted Net-Net Working Capital (NNWC) from the EDGAR cache.

Naive NCAV counts every current asset at 100%. Graham's NNWC haircuts them by
liquidation reliability — cash 100%, receivables 85%, inventory 50%, other
current assets 0% — then subtracts ALL liabilities (+ preferred + minority).
This is what separates a safe CASH net-net from an INVENTORY net-net, and it
naturally deflates a finance-company "net-net" whose current assets are a
subprime loan book (receivables) rather than cash.

  NNWC = cash + 0.85*receivables + 0.50*inventory - total_liabilities
         - preferred - minority_interest

Reads edgar_cache/*.json.gz (offline). Output: nnwc.csv (symbol-keyed):
  nnwc, nnwc_cash, nnwc_receivables, nnwc_inventory, nnwc_total_liab,
  nnwc_asset_mix (cash share of the haircut assets — higher = safer)
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
CUR_ASSETS = ["AssetsCurrent", "CurrentAssets"]
TOT_LIAB = ["Liabilities"]
CUR_LIAB = ["LiabilitiesCurrent", "CurrentLiabilities"]
PREF = ["PreferredStockValue", "PreferredStockValueOutstanding", "TemporaryEquityCarryingAmountAttributableToParent"]
NCI = ["MinorityInterest"]


def _latest(g, concepts, unit="USD"):
    for c in concepts:
        obs = (g.get(c, {}) or {}).get("units", {}).get(unit, [])
        if obs:
            best = None
            for o in obs:
                if o.get("end") and o.get("val") is not None:
                    if best is None or o["end"] > best["end"]:
                        best = o
            if best is not None:
                return best["val"]
    return None


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
        cash = _latest(g, CASH)
        recv = _latest(g, RECV)
        inv = _latest(g, INV)
        tliab = _latest(g, TOT_LIAB)
        if tliab is None:
            cl = _latest(g, CUR_LIAB)          # fall back to current liabilities
            tliab = cl
        if cash is None and recv is None and inv is None:
            continue
        pref = _latest(g, PREF) or 0
        nci = _latest(g, NCI) or 0
        c = cash or 0
        r = recv or 0
        iv = inv or 0
        haircut_assets = c + 0.85 * r + 0.50 * iv
        nnwc = haircut_assets - (tliab or 0) - pref - nci
        mix = (c / haircut_assets) if haircut_assets > 0 else None
        base = {
            "nnwc": nnwc, "nnwc_cash": cash, "nnwc_receivables": recv,
            "nnwc_inventory": inv, "nnwc_total_liab": tliab,
            "nnwc_asset_mix": round(mix, 3) if mix is not None else None,
        }
        for sym in syms:
            rows.append({"symbol": sym, **base})

    out = pd.DataFrame(rows).drop_duplicates("symbol")
    out.to_csv("nnwc.csv", index=False)
    print(f"symbols with NNWC: {len(out)} | positive NNWC: {int((out['nnwc'] > 0).sum())}", file=sys.stderr)


if __name__ == "__main__":
    main()
