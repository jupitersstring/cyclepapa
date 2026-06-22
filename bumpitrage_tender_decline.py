"""Bumpitrage tender-decline signal (Walker / YAVB).

The signal: an open tender offer where sequential SC TO amendments
disclose DECLINING tender acceptance percentages -- evidence holders
are refusing the bid, often because peers have outperformed since
announcement, or because of public agitation for a higher price.
Pairs with a known activist holder >10% for full conviction.

This module:
  1. For each tender in tender_scan.json with >=2 amendment filings,
     fetches the SC TO-I/A bodies in chronological order.
  2. Regex extracts tender-acceptance percentage or shares-tendered
     counts from each amendment.
  3. Flags series where acceptance % declines monotonically across
     >=2 amendments.

Output: bumpitrage_tender_decline.json
  {ticker: {n_amendments, acceptance_series, declining, score, reasons}}
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "bumpitrage_tender_decline.json"


ACCEPT_PCT_RX = re.compile(
    r"approximately\s+([\d.]+)\s*%\s+(?:of\s+(?:the\s+)?(?:outstanding|issued))",
    re.I,
)
ACCEPT_SHARES_RX = re.compile(
    r"approximately\s+([\d,]+)\s+shares?\s+have\s+been\s+(?:validly\s+)?tendered",
    re.I,
)


def fetch_amendment_text(cik, accession, primary_doc) -> str:
    try:
        from cache_store import read_html
        from edgar import _get, SEC_WWW
    except ImportError:
        return ""
    # Try cache
    try:
        html = read_html(accession) or ""
    except Exception:
        html = ""
    # EDGAR fallback
    if not html and cik and primary_doc:
        try:
            acc_no = accession.replace("-", "")
            url = f"{SEC_WWW}/Archives/edgar/data/{int(cik)}/{acc_no}/{primary_doc}"
            r = _get(url)
            html = r.text or ""
        except Exception:
            pass
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def parse_acceptance(text: str) -> tuple[float | None, int | None]:
    pct, shares = None, None
    m = ACCEPT_PCT_RX.search(text)
    if m:
        try: pct = float(m.group(1))
        except: pass
    m = ACCEPT_SHARES_RX.search(text)
    if m:
        try: shares = int(m.group(1).replace(",", ""))
        except: pass
    return pct, shares


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    tender = json.loads((ROOT / "tender_scan.json").read_text())
    print(f"tender_scan: {len(tender)} tickers", file=sys.stderr)

    out = {}
    n_processed = 0
    for tk, t in tender.items():
        if not isinstance(t, dict):
            continue
        role = t.get("role")
        if role not in ("SELF_TENDER", "TARGET", "BIDDER"):
            continue
        fils = t.get("filings") or []
        # Need >=2 amendment filings (SC TO-I/A or SC TO-T/A)
        amendments = [f for f in fils
                      if isinstance(f, dict)
                      and f.get("form", "").endswith("/A")]
        if len(amendments) < 2:
            continue

        # Sort by date ascending
        amendments.sort(key=lambda f: f.get("filing_date") or "")

        series = []
        for fil in amendments:
            text = fetch_amendment_text(fil.get("cik"),
                                          fil.get("accession"),
                                          fil.get("primary_doc"))
            if not text:
                continue
            pct, shares = parse_acceptance(text)
            series.append({
                "date": fil.get("filing_date"),
                "pct": pct,
                "shares": shares,
            })
            time.sleep(args.sleep)
        n_processed += 1

        # Did acceptance decline?
        pcts_with_dates = [(s["date"], s["pct"]) for s in series
                            if s["pct"] is not None]
        shares_with_dates = [(s["date"], s["shares"]) for s in series
                              if s["shares"] is not None]

        declining = False
        delta_str = ""
        if len(pcts_with_dates) >= 2:
            pcts = [p for _, p in pcts_with_dates]
            declining = all(pcts[i] >= pcts[i+1] for i in range(len(pcts)-1))
            if declining:
                delta_str = f"pct {pcts[0]:.1f} -> {pcts[-1]:.1f}"
        elif len(shares_with_dates) >= 2:
            sh = [s for _, s in shares_with_dates]
            declining = all(sh[i] >= sh[i+1] for i in range(len(sh)-1))
            if declining:
                delta_str = f"shares {sh[0]:,} -> {sh[-1]:,}"

        score = 0.0
        reasons = []
        if declining:
            score += 25
            reasons.append(f"declining acceptance ({delta_str})")
        if len(amendments) >= 3:
            score += 8
            reasons.append(f"{len(amendments)} amendments")
        elif len(amendments) >= 2:
            score += 3

        out[tk] = {
            "n_amendments": len(amendments),
            "acceptance_series": series,
            "declining": declining,
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

        if n_processed % 10 == 0:
            print(f"  processed {n_processed} tickers",
                  file=sys.stderr, flush=True)

    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {OUT} ({len(out)})")

    declining_names = [(tk, v) for tk, v in out.items() if v["declining"]]
    print(f"\nDeclining-acceptance tenders: {len(declining_names)}")
    for tk, v in sorted(declining_names,
                         key=lambda x: -x[1]["score"])[:15]:
        print(f"  {tk:<8} score={v['score']:<5} {v['reasons']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
