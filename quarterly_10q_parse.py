"""Additive quarterly 10-Q balance sheet parser.

Per AUDIT.md S2.4: existing layers use annual data (DEF 14A, 10-K,
yfinance balance sheet ~annual). NCAV, Whitman Safe-and-Cheap, and
debt-paydown signals can be up to 12 months stale.

This module:
  1. For each ticker in cancel_10b5_1.json (the 6,164 universe),
     fetches the SEC submissions API.
  2. Filters to most recent 10-Q (and 10-Q/A) filings.
  3. For each, fetches the primary document HTML and parses balance
     sheet items via regex on the financial-statement structure.
  4. Extracts: total_current_assets, total_assets, total_current_liab,
     total_liabilities, cash, short_term_debt, long_term_debt,
     shareholders_equity, period_end_date.
  5. Computes derived metrics: ncav, ncav_per_share, current_ratio,
     net_cash, net_debt.

ADDITIVE: completely separate output file. Does not modify any
existing layer. Downstream consumers (net_net_ncav, whitman_safecheap)
can opt in to the quarterly file vs the existing annual snapshot.

Output: quarterly_10q_data.json
  {ticker: {
    period_end_date, filing_date, accession,
    current_assets, current_liab, total_liab,
    cash, total_debt, equity,
    ncav, ncav_per_share, current_ratio,
    net_cash, net_debt_to_equity,
    refresh_date,
  }}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "quarterly_10q_data.json"


# Balance-sheet regex patterns. 10-Qs typically use $ amounts in
# millions or thousands; we normalize to dollars.
# Order matters -- match the more specific pattern first.

PATTERNS = {
    "current_assets": re.compile(
        r"total\s+current\s+assets[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    "current_liab": re.compile(
        r"total\s+current\s+liabilit(?:ies|y)[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    "total_liab": re.compile(
        r"total\s+liabilit(?:ies|y)\s*[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    "total_assets": re.compile(
        r"total\s+assets\s*[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    "cash": re.compile(
        r"cash\s+and\s+cash\s+equivalents[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    "long_term_debt": re.compile(
        r"long[\-\s]+term\s+debt[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    # Audit finding A10: accept stockholders OR shareholders spelling
    # (old pattern captured equity on only 33/164 filings).
    "equity": re.compile(
        r"total\s+(?:stock|share)holders[\s'’]*\s*equity"
        r"[\s\.\-]*\$?\s*([\d,]+(?:\.\d+)?)",
        re.I),
    "shares_outstanding": re.compile(
        r"common\s+stock.*?outstanding\s+\(?(\d[\d,]*?\.?\d*)",
        re.I | re.S),
}

# Detect unit-of-measure context: "in thousands", "in millions"
UNIT_RX = re.compile(
    r"(?:dollar\s+amounts\s+in\s+(thousands|millions)|"
    r"\(in\s+(thousands|millions)(?:\s+of\s+dollars)?\)|"
    r"amounts?\s+in\s+(thousands|millions))",
    re.I,
)


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def detect_unit_multiplier(text: str) -> int:
    m = UNIT_RX.search(text)
    if not m:
        return 1
    unit = (m.group(1) or m.group(2) or m.group(3) or "").lower()
    if unit == "thousands": return 1000
    if unit == "millions":  return 1_000_000
    return 1


def parse_balance_sheet(text: str) -> dict:
    out = {}
    mult = detect_unit_multiplier(text[:5000])
    for field, rx in PATTERNS.items():
        m = rx.search(text)
        if not m:
            continue
        v = _num(m.group(1))
        if v is None:
            continue
        if field != "shares_outstanding":
            v *= mult
        out[field] = v
    return out


def fetch_latest_10q(cik: str) -> dict | None:
    """Return the most recent 10-Q filing metadata for a CIK."""
    try:
        from edgar import _get
    except ImportError:
        return None
    try:
        sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    except Exception:
        return None
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])
    periods = recent.get("reportDate", [])
    for form, acc, dt, doc, pd in zip(forms, accs, dates, docs, periods):
        if form in ("10-Q", "10-Q/A"):
            return {
                "accession": acc,
                "filing_date": dt,
                "primary_doc": doc,
                "period_end": pd,
                "cik": cik,
            }
    return None


def fetch_filing_html(cik: str, accession: str, primary_doc: str) -> str:
    try:
        from edgar import _get
    except ImportError:
        return ""
    acc_no = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{primary_doc}"
    try:
        return _get(url).text or ""
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400,
                    help="cap on number of tickers processed")
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--source", default="net_net_ncav.json",
                    help="prioritize tickers from this file (NCAV "
                         "candidates first); falls back to whole universe")
    args = ap.parse_args()

    # Universe selection: prioritize NCAV candidates (where we most
    # want quarterly precision), fall back to top of universe by
    # composite if NCAV file present.
    priority_tickers = []
    if args.source and (ROOT / args.source).exists():
        try:
            d = json.loads((ROOT / args.source).read_text())
            priority_tickers = list(d.keys())
            print(f"prioritized {len(priority_tickers)} tickers from "
                  f"{args.source}", file=sys.stderr)
        except Exception:
            pass

    # Build CIK lookup
    try:
        from edgar import _get
        from recent import _cik_to_ticker_map
    except ImportError as e:
        print(f"need edgar.py + recent.py: {e}", file=sys.stderr)
        return 1
    cik_map = _cik_to_ticker_map()
    ticker_to_cik = {tk: cik for cik, tk in cik_map.items()}

    # Existing partial results (resumable)
    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except Exception:
            existing = {}

    out = dict(existing)
    n_processed = 0
    n_parsed = 0
    n_skipped = 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for tk in priority_tickers:
        if tk in out:
            n_skipped += 1
            continue
        if n_processed >= args.limit:
            break
        cik = ticker_to_cik.get(tk)
        if not cik:
            continue
        meta = fetch_latest_10q(cik)
        time.sleep(args.sleep)
        if not meta:
            continue

        # Skip if filing is older than 270 days (no recent 10-Q)
        try:
            fdt = datetime.strptime(meta["filing_date"][:10], "%Y-%m-%d")
            if (now - fdt).days > 270:
                continue
        except Exception:
            pass

        html = fetch_filing_html(cik, meta["accession"], meta["primary_doc"])
        time.sleep(args.sleep)
        if not html:
            continue
        # Strip HTML
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"\s+", " ", text)

        bs = parse_balance_sheet(text)
        if not bs.get("current_assets") or not bs.get("total_liab"):
            continue

        ncav = bs["current_assets"] - bs["total_liab"]
        current_ratio = None
        if bs.get("current_liab") and bs["current_liab"] > 0:
            current_ratio = bs["current_assets"] / bs["current_liab"]

        net_cash = None
        if bs.get("cash") is not None and bs.get("long_term_debt") is not None:
            net_cash = bs["cash"] - bs["long_term_debt"]

        shares_out = bs.get("shares_outstanding")
        ncav_per_share = (ncav / shares_out) if (shares_out and shares_out > 0) else None

        out[tk] = {
            "period_end": meta["period_end"],
            "filing_date": meta["filing_date"],
            "accession": meta["accession"],
            "current_assets": bs.get("current_assets"),
            "current_liab": bs.get("current_liab"),
            "total_liab": bs.get("total_liab"),
            "total_assets": bs.get("total_assets"),
            "cash": bs.get("cash"),
            "long_term_debt": bs.get("long_term_debt"),
            "equity": bs.get("equity"),
            "shares_outstanding": shares_out,
            "ncav": ncav,
            "ncav_per_share": ncav_per_share,
            "current_ratio": current_ratio,
            "net_cash": net_cash,
            "refresh_date": now.isoformat(timespec="seconds"),
        }
        n_processed += 1
        n_parsed += 1
        if n_processed % 25 == 0:
            tmp = OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2, default=str))
            tmp.replace(OUT)
            print(f"  [{n_processed}/{args.limit}] parsed={n_parsed} skipped={n_skipped}",
                  file=sys.stderr, flush=True)

    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, default=str))
    tmp.replace(OUT)
    print(f"\nwrote {OUT} ({len(out)} tickers; processed={n_processed} parsed={n_parsed})")

    # Top by NCAV (lowest price/NCAV most attractive -- need P)
    print(f"\n=== Sample (top 10 by NCAV magnitude) ===")
    ranked = sorted(out.items(), key=lambda x: -(x[1].get("ncav") or 0))
    for tk, v in ranked[:10]:
        ncav_b = (v.get("ncav") or 0) / 1e6
        cr = v.get("current_ratio") or 0
        print(f"  {tk:<7} NCAV=${ncav_b:>8.0f}M  CR={cr:>5.2f}  period={v['period_end']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
