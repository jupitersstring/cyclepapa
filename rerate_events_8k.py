"""Live 8-K corporate-action event discovery.

The MD&A narrative source (10-K/10-Q) misses corporate actions announced by
8-K and alternate phrasings, and the proxy cond_cats source was boilerplate-
contaminated (see rerate_catalysts.py). This scanner finds ACTUALLY-
ANNOUNCED spin-offs / separations / asset sales / sales-of-company /
strategic reviews from primary 8-K filings via EDGAR full-text search over a
recent window, with the announcement DATE (a clean confirmation anchor).

Each phrase is one EFTS exact-phrase query restricted to 8-K. Output is a
hard "event" source for rerate_catalysts.py -- an announced action from a
primary filing sits between PSU-incentive and MD&A-narrative in hardness.

Output: rerate_events_8k.json {ticker: {bucket: {date, phrase}}}  (most
recent per bucket).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "rerate_events_8k.json"

# (phrase, bucket). Announcement-style language so the hit dates the reveal.
PHRASES = [
    ("plan to separate", "SPINOFF"),
    ("intends to separate", "SPINOFF"),
    ("intend to spin off", "SPINOFF"),
    ("pursue a spin-off", "SPINOFF"),
    ("completed the spin-off", "SPINOFF"),
    ("completed the separation", "SPINOFF"),
    ("planned separation", "SEPARATION"),
    ("separate into two", "SEPARATION"),
    ("definitive agreement to sell", "ASSET_SALE"),
    ("completed the sale of", "ASSET_SALE"),
    ("agreement to divest", "ASSET_SALE"),
    ("agreement and plan of merger", "SALE_OF_COMPANY"),
    ("definitive agreement to be acquired", "SALE_OF_COMPANY"),
    ("to be acquired by", "SALE_OF_COMPANY"),
    ("review of strategic alternatives", "STRATEGIC_REVIEW"),
    ("exploring strategic alternatives", "STRATEGIC_REVIEW"),
    ("initiated a review of strategic", "STRATEGIC_REVIEW"),
    # --- broader corporate-action events (beyond spins/sales) ---
    ("emerged from chapter 11", "CH11_EMERGENCE"),
    ("emergence from chapter 11", "CH11_EMERGENCE"),
    ("plan of reorganization became effective", "CH11_EMERGENCE"),
    ("consummated the plan of reorganization", "CH11_EMERGENCE"),
    ("to be taken private", "GOING_PRIVATE"),
    ("go-private transaction", "GOING_PRIVATE"),
    ("going private transaction", "GOING_PRIVATE"),
    ("initiated a quarterly dividend", "CAPITAL_RETURN"),
    ("declared a special dividend", "CAPITAL_RETURN"),
    ("special cash dividend", "CAPITAL_RETURN"),
    ("reinstated its dividend", "CAPITAL_RETURN"),
    ("approved for listing on the nasdaq", "UPLISTING"),
    ("approved for listing on the new york stock exchange", "UPLISTING"),
    ("approved for listing on nyse", "UPLISTING"),
    ("authorized a share repurchase", "BUYBACK_AUTH"),
    ("approved a new share repurchase", "BUYBACK_AUTH"),
    ("increased its share repurchase", "BUYBACK_AUTH"),
    ("commenced a tender offer", "TENDER_OFFER"),
    ("tender offer to purchase", "TENDER_OFFER"),
    ("cash tender offer", "TENDER_OFFER"),
    ("modified dutch auction", "TENDER_OFFER"),
    ("commenced an exchange offer", "EXCHANGE_OFFER"),
    ("debt exchange offer", "EXCHANGE_OFFER"),
]

_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def efts(phrase, start, end, cap=80):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}"
           f"&forms={requests_quote('8-K')}")
    for _ in range(3):
        try:
            d = _get(url).json(); break
        except Exception:
            time.sleep(1.5); d = None
    if not d:
        return []
    out = []
    for h in (d.get("hits", {}).get("hits", []) or [])[:cap]:
        src = h.get("_source", {}) or {}
        tk = None
        for nm in (src.get("display_names") or []):
            m = _DT.search(nm)
            if m:
                tk = m.group(1); break
        if tk and _TK.match(tk):
            out.append({"ticker": tk, "date": src.get("file_date")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=270,
                    help="Look-back window for 8-K announcements.")
    ap.add_argument("--cap", type=int, default=80)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"8-K event discovery {start}..{end} ({len(PHRASES)} phrases)",
          file=sys.stderr)

    from universe_filter import is_excluded
    per: dict[str, dict] = {}
    for phrase, bucket in PHRASES:
        hits = efts(phrase, start, end, cap=args.cap)
        time.sleep(args.sleep)
        n = 0
        for h in hits:
            tk, dt = h["ticker"].upper(), h["date"]
            if not dt:
                continue
            bad, _ = is_excluded(tk)
            if bad:
                continue
            rec = per.setdefault(tk, {})
            cur = rec.get(bucket)
            # keep the most-recent announcement per bucket.
            if not cur or dt > cur["date"]:
                rec[bucket] = {"date": dt, "phrase": phrase}
            n += 1
        print(f"  {bucket:<16} '{phrase}': {len(hits)} 8-Ks", file=sys.stderr)

    io_util.write_json(OUT, per)
    from collections import Counter
    bc = Counter(b for r in per.values() for b in r)
    print(f"\nwrote {OUT} ({len(per)} names with an 8-K corporate-action event)",
          file=sys.stderr)
    for b, c in bc.most_common():
        print(f"  {b:<18} {c}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
