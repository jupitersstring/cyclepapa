"""Arquitos subsidiary-stake anchor (Arquitos Capital Q1 2025).

The signal: when a parent company sells a minority stake in a
subsidiary at a price that implies the subsidiary alone is worth
more than the parent's market cap, buy the parent. The market is
pricing the parent below its already-disclosed sub valuation.
(Arquitos cited ENDI sold 25% of CrossingBridge for $26M, implying
sub value > parent market cap.)

This module:
  1. Scans EDGAR for 8-K Item 1.01 / 2.01 disclosing minority equity
     sale of subsidiaries (keywords: "sold a minority interest",
     "acquired a minority interest", "purchase of equity in
     subsidiary", "implied valuation").
  2. Parses the transaction value in dollars.
  3. Cross-references with the parent's current mcap from yfinance.
  4. Flags tickers where (implied_sub_value / parent_mcap) > 0.8.

Output: arquitos_subsidiary_anchor.json
  {ticker: {filing_date, accession, deal_value, implied_sub_value,
            parent_mcap, ratio, score, reasons}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "arquitos_subsidiary_anchor.json"


# Money patterns
DOLLAR_RX = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|m\b|bn?\b)?",
    re.I,
)
PCT_RX = re.compile(
    r"(\d{1,2}(?:\.\d+)?)\s*%\s+(?:of\s+|equity\s+|stake\s+)",
    re.I,
)
IMPLIED_RX = re.compile(
    r"implied\s+(?:valuation|enterprise\s+value)\s+of\s+\$?\s*([\d,.]+)\s*(?:million|billion)?",
    re.I,
)


def parse_dollar(text: str, near_phrase_pattern: str = None) -> float | None:
    if near_phrase_pattern:
        # BUGFIX (silent-drop audit): callers pass literal phrases like
        # "for $" -- the bare $ was interpreted as a regex end-anchor,
        # so the deal-value extractor never matched. Escape the literal,
        # then append the dollar-amount pattern.
        m = re.search(re.escape(near_phrase_pattern) + r"[^.]{0,300}?" +
                       r"\$?\s*([\d,.]+)\s*(million|billion|m\b|bn?\b)?",
                       text, re.I)
        if not m:
            return None
        amt_str, unit = m.group(1), (m.group(2) or "").lower()
    else:
        m = DOLLAR_RX.search(text)
        if not m:
            return None
        amt_str, unit = m.group(1), (m.group(2) or "").lower()
    try:
        val = float(amt_str.replace(",", ""))
    except Exception:
        return None
    if "billion" in unit or "bn" in unit or unit == "b":
        val *= 1e9
    elif "million" in unit or unit == "m":
        val *= 1e6
    elif val < 1000:  # bare number < 1000 likely millions
        val *= 1e6
    return val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    try:
        from recent import EFTS, _get, requests_quote, _cik_to_ticker_map
        from cache_store import read_html
    except ImportError as e:
        print(f"need recent.py + cache_store.py: {e}", file=sys.stderr)
        return 1
    try:
        from edgar import _get as edgar_get, SEC_WWW
    except ImportError:
        edgar_get = None

    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    cik_to_ticker = _cik_to_ticker_map()

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
             - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Scanning 8-K subsidiary-stake disclosures {start}..{end}",
          file=sys.stderr, flush=True)

    queries = [
        '"minority interest" "subsidiary" "purchase"',
        '"sold" "interest in" "subsidiary"',
        '"implied valuation" "subsidiary"',
        '"strategic investment" "subsidiary" "$"',
        '"acquired" "minority" "in" "subsidiary"',
    ]

    found = {}
    for q in queries:
        offset = 0
        while len(found) < args.limit and offset < 600:
            url = (f"{EFTS}?forms=8-K&dateRange=custom"
                   f"&startdt={start}&enddt={end}"
                   f"&from={offset}&q={requests_quote(q)}")
            try:
                data = _get(url).json()
            except Exception:
                break
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                src = h.get("_source", {}) or {}
                ciks = src.get("ciks") or []
                cik = f"{int(ciks[0]):010d}" if ciks else None
                if not cik or cik in found:
                    continue
                tickers = src.get("tickers") or []
                ticker = tickers[0] if tickers else cik_to_ticker.get(cik)
                if not ticker:
                    continue
                file_date = src.get("file_date", "")
                id_parts = (h.get("_id") or "").split(":")
                if len(id_parts) != 2:
                    continue
                accession, primary_doc = id_parts
                found[cik] = (ticker, file_date, accession, primary_doc, q)
            offset += 100
            time.sleep(args.sleep)
        print(f"  query \"{q[:35]}...\" -> {len(found)} cumulative",
              file=sys.stderr, flush=True)

    # For each hit, fetch the 8-K body and extract dollar amounts
    out = {}
    n_parsed = 0
    for cik, (tk, fd, acc, pd, q) in found.items():
        text = ""
        try:
            html = read_html(acc) or ""
            if not html and edgar_get and pd:
                acc_no = acc.replace("-", "")
                url = f"{SEC_WWW}/Archives/edgar/data/{int(cik)}/{acc_no}/{pd}"
                try:
                    r = edgar_get(url)
                    html = r.text or ""
                except Exception:
                    pass
            if html:
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"&nbsp;", " ", text)
                text = re.sub(r"\s+", " ", text)
        except Exception:
            pass
        n_parsed += 1

        if not text:
            continue

        # Try to extract implied valuation
        implied = None
        m = IMPLIED_RX.search(text)
        if m:
            try:
                implied = float(m.group(1).replace(",", ""))
                if "billion" in m.group(0).lower():
                    implied *= 1e9
                elif "million" in m.group(0).lower():
                    implied *= 1e6
                elif implied < 1000:
                    implied *= 1e6
            except Exception:
                pass

        # If no implied valuation, try to extract deal_value × (1/pct)
        deal_value = None
        pct = None
        if not implied:
            # Find first percentage near "interest" or "stake"
            m_pct = PCT_RX.search(text)
            if m_pct:
                try:
                    pct = float(m_pct.group(1)) / 100.0
                except Exception:
                    pass
            # Find deal value near "for $" or "paid $"
            for keyword in ("for $", "purchase price", "paid", "consideration",
                             "investment of"):
                deal_value = parse_dollar(text, near_phrase_pattern=keyword)
                if deal_value:
                    break
            if pct and deal_value and 0.01 < pct < 0.99:
                implied = deal_value / pct

        if not implied:
            continue

        y = yf.get(tk, {}) or {}
        try:
            mcap = float(y.get("mcap") or 0)
        except Exception:
            mcap = 0
        if not mcap:
            continue

        ratio = implied / mcap

        score = 0.0
        reasons = []
        if ratio >= 2.0:
            score += 35; reasons.append(f"implied sub value {ratio:.1f}x parent mcap (LARGE)")
        elif ratio >= 1.0:
            score += 25; reasons.append(f"implied sub value {ratio:.1f}x parent mcap")
        elif ratio >= 0.6:
            score += 12; reasons.append(f"implied sub value {ratio:.1f}x parent mcap")
        elif ratio >= 0.3:
            score += 4
        else:
            continue   # too small to flag

        out[tk] = {
            "filing_date": fd,
            "accession": acc,
            "implied_sub_value_usd": implied,
            "parent_mcap_usd": mcap,
            "ratio": round(ratio, 3),
            "deal_value_usd": deal_value,
            "pct_sold": pct,
            "query_match": q,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)} flagged; {n_parsed} parsed)")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 15 by subsidiary-stake anchor ===")
    for tk, v in ranked[:15]:
        print(f"  {tk:<7} score={v['score']:<5} "
              f"implied=${v['implied_sub_value_usd']/1e6:.0f}M "
              f"mcap=${v['parent_mcap_usd']/1e6:.0f}M "
              f"ratio={v['ratio']:.2f}x  {v['filing_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
