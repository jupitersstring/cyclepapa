"""Form 4 XML sweep -- finds aggressive insider buying across the
entire SEC universe (broadens beyond our prior ticker roster).

Pulls Form 4 filings via EDGAR FTS in a date window, fetches each
XML, and extracts only transaction code P (open-market purchases).
Aggregates by issuer ticker: distinct buyers, total dollar volume,
recency.

Output: form4_buys.json keyed by ticker.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from edgar import _get, _ticker_index, SEC_WWW
from recent import EFTS, requests_quote
from universe_filter import is_excluded


def pull_form4_index(start_date: str, end_date: str, limit: int = 8000) -> list[dict]:
    """Walk EDGAR FTS for all Form 4 filings in the window."""
    out: list[dict] = []
    offset = 0
    while len(out) < limit and offset < 9900:
        url = (f"{EFTS}?forms=4&dateRange=custom"
               f"&startdt={start_date}&enddt={end_date}&from={offset}")
        try:
            data = _get(url).json()
        except Exception:
            break
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for h in hits:
            src = h.get("_source") or {}
            id_parts = (h.get("_id") or "").split(":")
            if len(id_parts) != 2:
                continue
            ciks = src.get("ciks") or []
            cik = f"{int(ciks[0]):010d}" if ciks else None
            tickers = src.get("tickers") or []
            ticker = tickers[0] if tickers else None
            out.append({
                "accession": id_parts[0],
                "primary_doc": id_parts[1],
                "cik": cik,
                "ticker": ticker,
                "file_date": src.get("file_date"),
            })
            if len(out) >= limit:
                return out
        offset += 100
    return out


def fetch_form4_xml(cik: str, accession: str, primary_doc: str) -> str | None:
    if not cik:
        return None
    acc = accession.replace("-", "")
    # Form 4 primary_doc often points to the XSL-rendered HTML view
    # (xslF345X06/<name>.xml). Strip the XSL prefix to get the raw XML.
    doc = primary_doc
    if "/" in doc:
        doc = doc.split("/")[-1]
    url = f"{SEC_WWW}/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
    try:
        return _get(url).text
    except Exception:
        return None


def _strip_ns(tag: str) -> str:
    """ElementTree returns tags as '{ns}localname'; strip namespace."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _findtext(elem, *path) -> str | None:
    cur = elem
    for p in path:
        if cur is None:
            return None
        found = None
        for ch in cur:
            if _strip_ns(ch.tag) == p:
                found = ch
                break
        cur = found
    return cur.text.strip() if cur is not None and cur.text else None


def _value(elem, *path) -> str | None:
    """Many Form 4 elements wrap their value in a <value> child."""
    cur = elem
    for p in path:
        if cur is None:
            return None
        for ch in cur:
            if _strip_ns(ch.tag) == p:
                cur = ch
                break
        else:
            return None
    if cur is None:
        return None
    for ch in cur:
        if _strip_ns(ch.tag) == "value":
            return ch.text.strip() if ch.text else None
    return cur.text.strip() if cur.text else None


def parse_form4(xml_text: str) -> dict | None:
    """Return {ticker, issuer_name, person, title, transactions: [...]}
    where transactions list only includes P (purchase) entries."""
    # Form 4 docs often arrive as HTML containers wrapping the XML; the
    # XML may also have leading XML processing instructions. Extract the
    # <ownershipDocument> block.
    m = re.search(r"(<\?xml[^>]*\?>)?\s*<ownershipDocument[^>]*>.*?</ownershipDocument>",
                  xml_text, re.DOTALL)
    if not m:
        return None
    blob = m.group(0)
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return None

    issuer_cik = _value(root, "issuer", "issuerCik")
    issuer_name = _value(root, "issuer", "issuerName")
    issuer_ticker = _value(root, "issuer", "issuerTradingSymbol")

    # Reporting owner info
    person = None
    title = None
    is_director = is_officer = is_10pct = False
    for child in root:
        if _strip_ns(child.tag) != "reportingOwner":
            continue
        person = _value(child, "reportingOwnerId", "rptOwnerName") or person
        for rel_child in child:
            if _strip_ns(rel_child.tag) == "reportingOwnerRelationship":
                d = _value(rel_child, "isDirector")
                o = _value(rel_child, "isOfficer")
                t = _value(rel_child, "isTenPercentOwner")
                if d in ("1", "true", "True"): is_director = True
                if o in ("1", "true", "True"): is_officer = True
                if t in ("1", "true", "True"): is_10pct = True
                title = _value(rel_child, "officerTitle") or title
        break  # take first reporting owner

    # Non-derivative transactions only
    txs = []
    for table in root:
        if _strip_ns(table.tag) != "nonDerivativeTable":
            continue
        for tx in table:
            if _strip_ns(tx.tag) != "nonDerivativeTransaction":
                continue
            code = _value(tx, "transactionCoding", "transactionCode")
            if code != "P":
                continue
            try:
                shares = float(_value(tx, "transactionAmounts", "transactionShares") or 0)
            except (TypeError, ValueError):
                shares = 0.0
            try:
                price = float(_value(tx, "transactionAmounts", "transactionPricePerShare") or 0)
            except (TypeError, ValueError):
                price = 0.0
            ad = _value(tx, "transactionAmounts", "transactionAcquiredDisposedCode")
            date = _value(tx, "transactionDate")
            try:
                post = float(_value(tx, "postTransactionAmounts", "sharesOwnedFollowingTransaction") or 0)
            except (TypeError, ValueError):
                post = 0.0
            if ad == "A" and shares > 0:  # Acquired (purchase)
                txs.append({
                    "date": date, "shares": shares,
                    "price": price, "dollar": shares * price,
                    "post_shares": post,
                })

    if not txs:
        return None
    return {
        "ticker": issuer_ticker,
        "issuer_name": issuer_name,
        "issuer_cik": issuer_cik,
        "person": person,
        "title": title,
        "is_director": is_director,
        "is_officer": is_officer,
        "is_10pct": is_10pct,
        "transactions": txs,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30,
                   help="Days back to sweep Form 4s.")
    p.add_argument("--limit", type=int, default=6000)
    p.add_argument("--sleep", type=float, default=0.15)
    p.add_argument("--out", default="form4_buys.json")
    args = p.parse_args()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Pulling Form 4 index {start} .. {end} (limit {args.limit})",
          file=sys.stderr)

    idx = pull_form4_index(start, end, limit=args.limit)
    print(f"Form 4 filings: {len(idx)}", file=sys.stderr)

    # Aggregate by ticker (skip if no ticker)
    by_ticker: dict[str, dict] = {}
    out_path = Path(args.out)
    if out_path.exists():
        try:
            by_ticker = json.loads(out_path.read_text())
        except Exception:
            by_ticker = {}

    seen_acc = set()
    for r in by_ticker.values():
        for f in (r.get("filings") or []):
            seen_acc.add(f.get("accession"))

    for i, f in enumerate(idx, 1):
        if f["accession"] in seen_acc:
            continue
        if i % 200 == 0:
            print(f"  [{i}/{len(idx)}] processed; "
                  f"issuers={len(by_ticker)}",
                  file=sys.stderr, flush=True)
            out_path.write_text(json.dumps(by_ticker, indent=2, default=str))
        xml = fetch_form4_xml(f["cik"], f["accession"], f["primary_doc"])
        if not xml:
            time.sleep(args.sleep)
            continue
        parsed = parse_form4(xml)
        time.sleep(args.sleep)
        if not parsed:
            continue
        tk = (parsed.get("ticker") or f.get("ticker") or "").upper()
        if not tk:
            continue
        bad, _ = is_excluded(tk)
        if bad:
            continue
        rec = by_ticker.setdefault(tk, {
            "ticker": tk,
            "issuer_name": parsed.get("issuer_name"),
            "issuer_cik": parsed.get("issuer_cik"),
            "buyer_set": [],
            "total_dollar": 0.0,
            "total_shares": 0.0,
            "filings": [],
        })
        person_label = (parsed.get("person") or "?") + " | " + (parsed.get("title") or
            ("Director" if parsed.get("is_director") else
             "10%" if parsed.get("is_10pct") else "?"))
        if person_label not in rec["buyer_set"]:
            rec["buyer_set"].append(person_label)
        for tx in parsed["transactions"]:
            rec["total_dollar"] += tx["dollar"]
            rec["total_shares"] += tx["shares"]
        rec["filings"].append({
            "accession": f["accession"],
            "date": f.get("file_date"),
            "person": parsed.get("person"),
            "title": parsed.get("title"),
            "dollar": sum(t["dollar"] for t in parsed["transactions"]),
            "shares": sum(t["shares"] for t in parsed["transactions"]),
        })

    out_path.write_text(json.dumps(by_ticker, indent=2, default=str))

    # Surface top
    ranked = sorted(by_ticker.values(),
                    key=lambda r: (len(r["buyer_set"]), r["total_dollar"]),
                    reverse=True)
    print(f"\nWrote {args.out} ({len(by_ticker)} issuers).", file=sys.stderr)
    print(f"\n=== TOP 30 BY DISTINCT BUYERS + $ VOLUME ===")
    print(f"{'TKR':<10}{'BUYERS':>7}{'TXNS':>6}{'TOTAL $':>14}  ISSUER")
    for r in ranked[:30]:
        n = len(r["buyer_set"])
        nt = len(r["filings"])
        tot = r["total_dollar"]
        iss = (r.get("issuer_name") or "")[:50]
        print(f"{r['ticker']:<10}{n:>7}{nt:>6}{tot:>14,.0f}  {iss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
