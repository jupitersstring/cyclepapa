"""Targeted Form 4 enrichment: per-ticker pull via SEC submissions JSON.

For each ticker in user_named_targets, walk its recent submissions and
fetch every Form 4 XML in the past N days, then aggregate into the
existing form4_buys.json.

This catches issuers that the wide EDGAR FTS sweep missed (because
their volume of routine S/A filings drowned out the few P buys).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from edgar import _get, cik_for, SEC_DATA, SEC_WWW
from form4_buys_sweep import parse_form4
from universe_filter import is_excluded


def pull_ticker_form4s(ticker: str, days: int = 60) -> list[dict]:
    cik = cik_for(ticker)
    if not cik:
        return []
    try:
        sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    except Exception:
        return []
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for form, acc, doc, dt in zip(forms, accs, docs, dates):
        if form not in ("4", "4/A"):
            continue
        if dt < cutoff:
            continue
        out.append({"cik": cik, "accession": acc, "primary_doc": doc, "date": dt})
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", required=True,
                   help="File with one ticker per line.")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--out", default="form4_buys.json")
    p.add_argument("--sleep", type=float, default=0.15)
    args = p.parse_args()

    tickers = [t.strip().upper() for t in Path(args.tickers).read_text().splitlines()
               if t.strip() and not t.strip().startswith("#")]

    out_path = Path(args.out)
    by_ticker: dict = {}
    if out_path.exists():
        try:
            by_ticker = json.loads(out_path.read_text())
        except Exception:
            by_ticker = {}

    print(f"Targeted Form 4 pull for {len(tickers)} tickers", file=sys.stderr)
    for tk in tickers:
        bad, _ = is_excluded(tk)
        if bad:
            continue
        index = pull_ticker_form4s(tk, days=args.days)
        if not index:
            print(f"  {tk}: no Form 4s in past {args.days}d", file=sys.stderr)
            time.sleep(args.sleep)
            continue
        rec = by_ticker.setdefault(tk, {
            "ticker": tk, "buyer_set": [],
            "total_dollar": 0.0, "total_shares": 0.0,
            "filings": [],
        })
        existing_accs = {f.get("accession") for f in rec.get("filings", [])}
        n_new = 0
        for f in index:
            if f["accession"] in existing_accs:
                continue
            acc_no_dash = f["accession"].replace("-", "")
            url = f"{SEC_WWW}/Archives/edgar/data/{int(f['cik'])}/{acc_no_dash}/{f['primary_doc']}"
            try:
                xml = _get(url).text
            except Exception:
                time.sleep(args.sleep); continue
            parsed = parse_form4(xml)
            time.sleep(args.sleep)
            if not parsed:
                continue
            person_label = (parsed.get("person") or "?") + " | " + (
                parsed.get("title") or
                ("Director" if parsed.get("is_director") else
                 "10%" if parsed.get("is_10pct") else "?"))
            if person_label not in rec["buyer_set"]:
                rec["buyer_set"].append(person_label)
            for tx in parsed["transactions"]:
                rec["total_dollar"] += tx["dollar"]
                rec["total_shares"] += tx["shares"]
            rec["filings"].append({
                "accession": f["accession"],
                "date": f.get("date"),
                "person": parsed.get("person"),
                "title": parsed.get("title"),
                "dollar": sum(t["dollar"] for t in parsed["transactions"]),
                "shares": sum(t["shares"] for t in parsed["transactions"]),
            })
            n_new += 1
        # Also pull issuer_name from existing record if missing
        if not rec.get("issuer_name"):
            try:
                cik = cik_for(tk)
                sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
                rec["issuer_name"] = sub.get("name") or ""
            except Exception:
                pass
        print(f"  {tk}: +{n_new} new P-trans (total {len(rec['filings'])} fl, "
              f"${rec['total_dollar']:,.0f}, {len(rec['buyer_set'])} buyers)",
              file=sys.stderr)
        out_path.write_text(json.dumps(by_ticker, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
