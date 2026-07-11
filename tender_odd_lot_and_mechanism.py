"""Two additive tender-leg enhancements in one module:

1. Odd-lot tender priority detector (Tauraitis/Walker 17/17 archetype)
   For every tender in tender_scan.json with role in (SELF_TENDER,
   TARGET, BIDDER), fetch the primary SC TO HTML via cache_store and
   regex for:
     - "fewer than 100 shares"
     - "less than 100 shares"
     - "odd lot[s]?"
     - "not subject to proration"
     - "odd lot holders"

2. Comment-Jarrell tender mechanism classifier
   Classify each tender as one of: FIXED_PRICE / DUTCH_AUCTION /
   OPEN_MARKET / EXCHANGE_OFFER / UNKNOWN. Per Comment-Jarrell (JF
   1991), fixed-price self-tender announcement CAR ~11%, Dutch ~8%,
   open-market ~2% -- monotonic in commitment intensity.

Both outputs are additive overlays on the existing tender_scan layer.
The existing tender_scan.json file is NOT modified.

Outputs:
  tender_odd_lot.json
    {ticker: {has_odd_lot_priority: bool, snippet: str,
              accession: str, score: float}}
  tender_mechanism.json
    {ticker: {mechanism: str, multiplier: float, score_delta: float}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_ODD = ROOT / "tender_odd_lot.json"
OUT_MECH = ROOT / "tender_mechanism.json"


ODD_LOT_RX = re.compile(
    r"(?:fewer than 100 shares|less than 100 shares|"
    r"odd[\s\-]?lot(?:s|\sholders?)?|"
    r"holders of fewer than 100|"
    r"holders of less than 100)",
    re.I,
)
NOT_PRORATED_RX = re.compile(
    r"(?:not\s+subject\s+to\s+proration|"
    r"without\s+proration|"
    r"in\s+full\s+without\s+proration)",
    re.I,
)


# Mechanism patterns (most distinctive first)
DUTCH_RX = re.compile(
    r"(?:modified\s+dutch\s+auction|dutch[\s\-]+auction|"
    r"auction\s+tender|range\s+of\s+prices|"
    r"price\s+per\s+share\s+(?:within|in)\s+a\s+range)",
    re.I,
)
FIXED_PRICE_RX = re.compile(
    r"(?:fixed\s+price\s+(?:per\s+share|tender|offer)|"
    r"at\s+a\s+(?:single\s+)?(?:cash\s+)?price\s+per\s+share|"
    r"purchase\s+price\s+of\s+\$[\d,.]+\s+per\s+share)",
    re.I,
)
EXCHANGE_OFFER_RX = re.compile(
    r"(?:exchange\s+offer|in\s+exchange\s+for|exchange\s+ratio)",
    re.I,
)
OPEN_MARKET_RX = re.compile(
    r"(?:open[\s\-]+market\s+(?:repurchases?|purchases?)|"
    r"open[\s\-]+market\s+from\s+time\s+to\s+time)",
    re.I,
)

# Comment-Jarrell relative weights vs fixed-price = 1.0
# UNKNOWN = 1.0 = neutral (we don't penalize what we can't classify)
MECHANISM_MULTIPLIER = {
    "FIXED_PRICE":     1.0,
    "DUTCH_AUCTION":   0.73,   # 8% CAR / 11% CAR
    "EXCHANGE_OFFER":  0.85,
    "OPEN_MARKET":     0.18,   # 2% CAR / 11% CAR
    "UNKNOWN":         1.0,
}


def classify_mechanism(text: str) -> str:
    if not text:
        return "UNKNOWN"
    # order matters: dutch is most distinctive, then fixed-price
    if DUTCH_RX.search(text):
        return "DUTCH_AUCTION"
    if FIXED_PRICE_RX.search(text):
        return "FIXED_PRICE"
    if EXCHANGE_OFFER_RX.search(text):
        return "EXCHANGE_OFFER"
    if OPEN_MARKET_RX.search(text):
        return "OPEN_MARKET"
    return "UNKNOWN"


def extract_snippet(text: str, rx: re.Pattern, window: int = 120) -> str:
    m = rx.search(text)
    if not m:
        return ""
    start = max(0, m.start() - window // 2)
    end = min(len(text), m.end() + window // 2)
    snip = text[start:end].replace("\n", " ").strip()
    # squeeze whitespace
    snip = re.sub(r"\s+", " ", snip)
    return snip[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=10000,
                    help="cap on number of tender filings processed")
    ap.add_argument("--skip-missing-cache", action="store_true", default=True,
                    help="skip filings not present in HTML cache")
    args = ap.parse_args()

    try:
        from cache_store import read_html
    except ImportError as e:
        print(f"need cache_store.py: {e}", file=sys.stderr)
        return 1
    # Direct EDGAR fallback when cache misses
    try:
        from edgar import _get, SEC_WWW
    except ImportError:
        _get = None
        SEC_WWW = "https://www.sec.gov"

    def fetch_via_edgar(cik: str, accession: str,
                         primary_doc: str) -> str:
        if not (cik and accession and primary_doc and _get):
            return ""
        acc_no = accession.replace("-", "")
        url = f"{SEC_WWW}/Archives/edgar/data/{int(cik)}/{acc_no}/{primary_doc}"
        try:
            r = _get(url)
            return r.text or ""
        except Exception:
            return ""

    tender = json.loads((ROOT / "tender_scan.json").read_text())
    print(f"loaded tender_scan: {len(tender)} tickers", file=sys.stderr)

    relevant = []
    for tk, t in tender.items():
        if not isinstance(t, dict):
            continue
        role = t.get("role")
        if role in ("SELF_TENDER", "TARGET", "BIDDER") or t.get("has_13e3"):
            relevant.append((tk, t))
    print(f"  relevant tenders: {len(relevant)}", file=sys.stderr)

    odd_lot_out = {}
    mech_out = {}
    n_parsed = 0
    n_cached = 0

    for i, (tk, t) in enumerate(relevant[:args.limit], 1):
        # Accession is in filings[0] (most recent first by scan convention)
        filings_list = t.get("filings") or []
        accession = None
        primary_doc = None
        cik = None
        for fil in filings_list:
            if isinstance(fil, dict) and fil.get("accession"):
                accession = fil["accession"]
                primary_doc = fil.get("primary_doc")
                cik = fil.get("cik")
                break
        terms = t.get("terms") or {}
        dutch_hint = (terms.get("dutch_low") is not None
                      and terms.get("dutch_high") is not None)
        # Try cache first, then direct EDGAR fetch as fallback
        text = ""
        if accession:
            html = ""
            try:
                html = read_html(accession) or ""
            except Exception:
                pass
            if html:
                n_cached += 1
            elif cik and primary_doc:
                html = fetch_via_edgar(cik, accession, primary_doc)
            if html:
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"&nbsp;", " ", text)
                text = re.sub(r"\s+", " ", text)

        n_parsed += 1

        # 1. odd-lot
        has_odd_lot = bool(ODD_LOT_RX.search(text))
        has_prorate = bool(NOT_PRORATED_RX.search(text))
        # Score: real edge requires BOTH odd-lot language AND
        # not-subject-to-proration clause
        if has_odd_lot and has_prorate:
            odd_score = 25
            snippet = extract_snippet(text, NOT_PRORATED_RX)
        elif has_odd_lot:
            odd_score = 10
            snippet = extract_snippet(text, ODD_LOT_RX)
        else:
            odd_score = 0
            snippet = ""

        # METHODOLOGY FIX (audit finding A5): the odd-lot edge only
        # exists while the tender is LIVE. LEN scored the full edge on
        # a 198-day-old completed exchange (past-tense results 8-K).
        # Liveness gate on the latest filing's age: <=60d full score,
        # 61-120d half, older -> 0 (flagged stale).
        days_ago = None
        for fil in filings_list:
            if isinstance(fil, dict) and fil.get("days_ago") is not None:
                days_ago = fil["days_ago"]
                break
        liveness = "LIVE"
        if days_ago is None or days_ago > 120:
            if odd_score:
                liveness = "STALE_OR_COMPLETED"
            odd_score = 0
        elif days_ago > 60:
            odd_score = round(odd_score * 0.5, 1)
            liveness = "AGING"

        odd_lot_out[tk] = {
            "has_odd_lot_language": has_odd_lot,
            "has_not_prorated_clause": has_prorate,
            "snippet": snippet,
            "accession": accession,
            "latest_filing_days_ago": days_ago,
            "liveness": liveness,
            "score": odd_score,
        }

        # 2. mechanism -- prefer terms.dutch_low/high if present;
        # else regex on HTML; else UNKNOWN
        if dutch_hint:
            mech = "DUTCH_AUCTION"
        elif text:
            mech = classify_mechanism(text)
        else:
            mech = "UNKNOWN"
        mult = MECHANISM_MULTIPLIER[mech]
        # bb_points proxy: existing tender_scan layer scores by role
        # (SELF_TENDER=25, TARGET=22, BIDDER=5, +15 for 13E-3)
        role = t.get("role")
        role_pts = {"SELF_TENDER": 25, "TARGET": 22,
                    "BIDDER": 5}.get(role, 0)
        if t.get("has_13e3"):
            role_pts += 15
        score_delta = round(role_pts * (mult - 1.0), 1)
        mech_out[tk] = {
            "mechanism": mech,
            "multiplier": mult,
            "score_delta": score_delta,
        }

        time.sleep(args.sleep)
        if i % 25 == 0:
            print(f"  [{i}/{len(relevant)}] cached={n_cached} parsed={n_parsed}",
                  file=sys.stderr, flush=True)

    OUT_ODD.write_text(json.dumps(odd_lot_out, indent=2))
    OUT_MECH.write_text(json.dumps(mech_out, indent=2))
    print(f"\nwrote {OUT_ODD} ({len(odd_lot_out)})")
    print(f"wrote {OUT_MECH} ({len(mech_out)})")

    # summary
    n_odd_full = sum(1 for v in odd_lot_out.values()
                     if v["has_odd_lot_language"] and v["has_not_prorated_clause"])
    n_odd_partial = sum(1 for v in odd_lot_out.values()
                         if v["has_odd_lot_language"]
                         and not v["has_not_prorated_clause"])
    print(f"\nOdd-lot priority (full edge):    {n_odd_full}")
    print(f"Odd-lot language only (partial): {n_odd_partial}")

    from collections import Counter
    mech_dist = Counter(v["mechanism"] for v in mech_out.values())
    print(f"\nMechanism distribution:")
    for m, n in mech_dist.most_common():
        print(f"  {m:<18} {n}")

    print(f"\n=== Odd-lot priority FULL EDGE (top 20) ===")
    for tk, v in list(odd_lot_out.items())[:30]:
        if v["score"] >= 25:
            print(f"  {tk:<8} {(v['snippet'] or '')[:100]}")

    print(f"\n=== Top tender mechanism score-ups (FIXED_PRICE) ===")
    for tk, v in sorted(mech_out.items(),
                          key=lambda x: -x[1]["score_delta"])[:15]:
        print(f"  {tk:<8} mechanism={v['mechanism']:<16} "
              f"delta={v['score_delta']:+.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
