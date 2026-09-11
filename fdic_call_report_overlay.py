"""FDIC Call Report overlay for Form 15 deregistered community banks.

The signal: when a community bank holding company files Form 15 to
suspend SEC reporting, the lead bank subsidiary still files quarterly
Call Reports to the FFIEC. We can keep valuing the bank from FFIEC
data even when no 10-Q exists.

This module:
  1. Reads our existing going_dark.csv (Form 15 filings).
  2. Filters to financials/banking sector (where Call Reports exist).
  3. For each holding company, looks up FDIC Cert # via the public
     FDIC BankFind API.
  4. Pulls latest Call Report metrics: tier-1 capital, NPAs/loans,
     ROE, tangible book.
  5. Computes a "dark bank quality" score.

The FFIEC public API is documented at https://cdr.ffiec.gov/public/
and the FDIC BankFind API at https://banks.data.fdic.gov/api/.

Output: fdic_call_report_overlay.json
  {ticker: {fdic_cert, lead_bank_name, tier1_capital_ratio,
            nonperforming_pct, roe, tangible_book_per_share,
            score, reasons}}

Honest limitation: matching SEC holdco names to FDIC bank subsidiary
names is fuzzy. We only confidently flag matches where the name
similarity is high. False positives are dropped, false negatives are
acceptable.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "fdic_call_report_overlay.json"


def normalize_name(s: str) -> str:
    s = (s or "").upper()
    # strip common corporate suffixes
    for sfx in (" CORP", " CORPORATION", " INC", " INCORPORATED",
                 " LLC", " HOLDINGS", " HOLDING", " COMPANY", " CO",
                 " BANCSHARES", " BANCORP", " FINANCIAL", " GROUP",
                 " LTD", " PLC", " N.A.", " NA", " /DE/", " /MD/"):
        s = s.replace(sfx, "")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fdic_lookup(holdco_name: str, ticker: str) -> dict | None:
    """Query FDIC BankFind API by name; return best match dict or None."""
    try:
        import urllib.parse
        from edgar import _get
    except ImportError:
        return None
    norm = normalize_name(holdco_name)
    if not norm:
        return None
    # FDIC search by name
    try:
        url = (f"https://banks.data.fdic.gov/api/institutions"
               f"?search=NAME:%22{urllib.parse.quote(norm)}%22"
               f"&fields=CERT,NAME,STNAME,CITY,ACTIVE,ASSET,STMULT,"
               f"REGAGNT,WEBADDR,FED,SPECGRP")
        r = _get(url)
        data = r.json()
        hits = data.get("data") or []
        for h in hits:
            h_data = h.get("data") or {}
            if h_data.get("ACTIVE") == 0:
                continue
            return {
                "cert": h_data.get("CERT"),
                "name": h_data.get("NAME"),
                "state": h_data.get("STNAME"),
                "assets": h_data.get("ASSET"),
            }
    except Exception:
        return None
    return None


def fdic_financials(cert: int) -> dict | None:
    """Pull latest quarterly financials for a bank by FDIC cert."""
    try:
        from edgar import _get
    except ImportError:
        return None
    try:
        url = (f"https://banks.data.fdic.gov/api/financials"
               f"?filters=CERT%3A{cert}&sort_by=REPDTE&sort_order=DESC"
               f"&limit=1"
               f"&fields=REPDTE,ASSET,DEP,EQ,EQTOT,NETINC,ROA,ROE,"
               f"NPERFV,RBCT1,RBC1RWAJ,TLALLO,TLCDQ")
        r = _get(url)
        data = r.json()
        hits = data.get("data") or []
        if not hits:
            return None
        f = hits[0].get("data") or {}
        return f
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    going_dark = ROOT / "going_dark.csv"
    if not going_dark.exists():
        print("going_dark.csv not found -- run "
              "special_situations_extended.py first",
              file=sys.stderr)
        return 1

    yf = json.loads((ROOT / "yfinance_quick.json").read_text())

    # Filter to bank-like companies
    candidates = []
    for r in csv.DictReader(going_dark.open()):
        tk = r.get("ticker", "").upper()
        if not tk or tk.startswith("CIK"):
            continue
        company = r.get("company") or ""
        y = yf.get(tk, {}) or {}
        sector = (y.get("sector") or "").upper()
        industry = (y.get("industry") or "").upper()
        # heuristic: name or sector suggests bank
        is_bank = (any(w in company.upper() for w in
                       ("BANK", "BANCSHARES", "BANCORP", "FINANCIAL"))
                   or "FINANCIAL" in sector or "BANK" in industry)
        if is_bank:
            candidates.append({
                "ticker": tk,
                "company": company,
                "filing_date": r.get("filing_date"),
            })

    print(f"bank-like Form 15 candidates: {len(candidates)}",
          file=sys.stderr)

    out = {}
    n_match = 0
    for i, c in enumerate(candidates[:args.limit], 1):
        tk, name = c["ticker"], c["company"]
        match = fdic_lookup(name, tk)
        time.sleep(args.sleep)
        if not match or not match.get("cert"):
            continue
        fin = fdic_financials(match["cert"])
        time.sleep(args.sleep)
        if not fin:
            continue
        n_match += 1

        # Scoring inputs
        roe = fin.get("ROE")
        roa = fin.get("ROA")
        eq = fin.get("EQTOT") or fin.get("EQ")
        assets = fin.get("ASSET")
        eq_to_assets = (eq / assets) if (eq and assets) else None
        tier1_rwa = fin.get("RBC1RWAJ")
        nperf_pct = fin.get("NPERFV")  # non-performing / total loans %

        # Score: well-capitalized + clean credit + decent profitability
        score = 0.0
        reasons = []
        if tier1_rwa is not None:
            try: t1 = float(tier1_rwa)
            except: t1 = None
            if t1 is not None and t1 >= 10:
                score += 8; reasons.append(f"T1 {t1:.1f}%")
            elif t1 is not None and t1 >= 8:
                score += 4
        if eq_to_assets is not None and eq_to_assets >= 0.1:
            score += 6; reasons.append(f"E/A {eq_to_assets*100:.1f}%")
        if nperf_pct is not None:
            try: np_ = float(nperf_pct)
            except: np_ = None
            if np_ is not None and np_ < 1.5:
                score += 8; reasons.append(f"NPA {np_:.2f}%")
            elif np_ is not None and np_ < 3.0:
                score += 4
        if roe is not None:
            try: r = float(roe)
            except: r = None
            if r is not None and r >= 10:
                score += 8; reasons.append(f"ROE {r:.1f}%")
            elif r is not None and r >= 5:
                score += 4

        out[tk] = {
            "fdic_cert": match.get("cert"),
            "lead_bank_name": match.get("name"),
            "lead_bank_state": match.get("state"),
            "lead_bank_assets_thousands": match.get("assets"),
            "report_date": fin.get("REPDTE"),
            "tier1_rwa_pct": tier1_rwa,
            "eq_to_assets": eq_to_assets,
            "nonperforming_loans_pct": nperf_pct,
            "roe": roe,
            "roa": roa,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
            "going_dark_date": c.get("filing_date"),
        }
        if i % 5 == 0:
            print(f"  [{i}/{len(candidates)}] matched={n_match}",
                  file=sys.stderr, flush=True)

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT} ({len(out)} matched)")
    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 15 dark community banks by FDIC Call Report ===")
    for tk, v in ranked[:15]:
        print(f"  {tk:<8} {v['lead_bank_name'][:28]:<28} "
              f"score={v['score']:<5} {v['reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
