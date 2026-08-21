"""Selective / Own-Shares Revealed-Preference Scanner.

The second revealed-preference engine (spec §7-8). Mauboussin's test is
not "is the company buying back stock?" but "is management retiring shares
for materially less than intrinsic value?" So this does NOT reward
ordinary programme buybacks (already covered by buyback_verify) or
mechanical employee-offset repurchases. It isolates the SELECTIVE classes
that reveal management's valuation:

  D. Specific block repurchase from a named holder  (highest signal)
  C. Dutch auction / off-market / issuer tender
  B. Accelerated / privately-negotiated discretionary repurchase

A specific negotiated repurchase -- especially of a large block from a
founder/fund, potentially a forced seller -- alters control, float, EPS
and governance at once, and management chose to spend cash on its own
equity rather than anything else. Buying at/below market adds conviction
(opportunistic, not price-supporting).

Output: selective_buyback_scan.json {ticker: {class, score, ...}}.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "selective_buyback_scan.json"

# Selective-repurchase phrases (points ~ revealed-valuation signal).
SELECTIVE = [
    ("privately negotiated repurchase", "privately_negotiated", 10),
    ("privately negotiated purchase of", "privately_negotiated", 10),
    ("repurchase from", "block_from_holder", 12),
    ("modified dutch auction", "dutch_auction", 9),
    ("dutch auction tender", "dutch_auction", 9),
    ("off-market buyback", "off_market", 8),
    ("off-market repurchase", "off_market", 8),
    ("specific repurchase", "specific_repurchase", 9),
    ("selective buyback", "selective", 9),
    ("accelerated share repurchase", "asr", 3),
    ("stock repurchase agreement", "repurchase_agreement", 3),
    ("share repurchase agreement", "repurchase_agreement", 3),
]
# A named counterparty near "repurchase" => a block bought from a holder.
FROM_HOLDER_RX = re.compile(
    r"repurchase[^.\n]{0,60}?\bfrom\b[^.\n]{0,40}?"
    r"(fund|partners|capital|holdings|LLC|L\.P\.|LP|founder|"
    r"chairman|stockholder|shareholder|selling)", re.I)
# Price vs market: at/below market = opportunistic (Mauboussin).
BELOW_MARKET_RX = re.compile(
    r"(discount to[^.\n]{0,30}(market|closing price)|"
    r"below the (closing|market) price|at a discount)", re.I)
PREMIUM_MARKET_RX = re.compile(
    r"(premium to[^.\n]{0,30}(market|closing price)|above the (closing|market) price)", re.I)

_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and _TK.match(tk) and tk not in {"NONE", "N/A"})


def efts(phrase, start, end, cap=40):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?forms=8-K&dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}")
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
        ciks = src.get("ciks") or []
        tk = None
        for nm in (src.get("display_names") or []):
            m = _DT.search(nm)
            if m:
                tk = m.group(1); break
        out.append({"ticker": tk, "cik": f"{int(ciks[0]):010d}" if ciks else None,
                    "accession": src.get("adsh"), "date": src.get("file_date")})
    return out


def fetch_text(cik, acc):
    from recent import _get
    if not cik or not acc:
        return ""
    accn = acc.replace("-", "")
    try:
        idx = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/index.json").json()
        docs = [i["name"] for i in idx["directory"]["item"]
                if i["name"].endswith((".htm", ".html")) and "index" not in i["name"]
                and not i["name"].startswith("R")]
        txt = ""
        for d in docs[:2]:
            txt += re.sub(r"<[^>]+>", " ",
                          _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{d}").text)
        return re.sub(r"\s+", " ", txt)[:300000]
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--verify-top", type=int, default=25)
    args = ap.parse_args()
    from datetime import datetime, timezone, timedelta
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Selective-buyback sweep {start}..{end}", file=sys.stderr)

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}

    per: dict[str, dict] = {}
    for phrase, cls, pts in SELECTIVE:
        for h in efts(phrase, start, end):
            tk = (h["ticker"] or "").upper()
            if not _valid(tk):
                continue
            rec = per.setdefault(tk, {"ticker": tk, "cik": h["cik"],
                                      "classes": {}, "score": 0.0,
                                      "from_holder": None, "vs_market": None,
                                      "latest_accession": h["accession"],
                                      "date": h["date"]})
            if cls not in rec["classes"]:
                rec["classes"][cls] = pts
                rec["score"] += pts
            if (h["date"] or "") > (rec.get("date") or ""):
                rec["date"] = h["date"]; rec["latest_accession"] = h["accession"]
                rec["cik"] = h["cik"] or rec["cik"]
        time.sleep(args.sleep)
    print(f"  {len(per)} selective-buyback filers; verifying block-from-holder + price",
          file=sys.stderr)

    # verify block-from-holder + opportunistic pricing for the top names
    for rec in sorted(per.values(), key=lambda r: -r["score"])[:args.verify_top]:
        txt = fetch_text(rec["cik"], rec["latest_accession"])
        time.sleep(args.sleep)
        if not txt:
            continue
        if FROM_HOLDER_RX.search(txt):
            rec["from_holder"] = True
            rec["score"] += 6                     # negotiated block from a holder
        if BELOW_MARKET_RX.search(txt):
            rec["vs_market"] = "discount"
            rec["score"] += 5                     # opportunistic (buying cheap)
        elif PREMIUM_MARKET_RX.search(txt):
            rec["vs_market"] = "premium"
            rec["score"] -= 3                     # paying up is less revealing

    out = {}
    for tk, rec in per.items():
        rec["score"] = round(max(0.0, rec["score"]), 1)
        rec["classes"] = list(rec["classes"].keys())
        if rec["score"] > 0:
            out[tk] = rec
    io_util.write_json(OUT, out)
    print(f"wrote {OUT} ({len(out)} selective buybacks)")
    print("\n=== TOP SELECTIVE / REVEALED-VALUATION BUYBACKS ===")
    print(f"{'TKR':<7}{'SCR':>6} {'HOLDER':<7}{'PX':<9}CLASSES")
    for r in sorted(out.values(), key=lambda x: -x["score"])[:20]:
        hd = "yes" if r.get("from_holder") else "—"
        px = r.get("vs_market") or "—"
        print(f"{r['ticker']:<7}{r['score']:>6.0f} {hd:<7}{px:<9}{','.join(r['classes'])[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
