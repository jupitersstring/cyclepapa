"""Equity-committee scanner -- the strongest stub-survival signal.

When a bankruptcy court appoints an OFFICIAL COMMITTEE OF EQUITY SECURITY
HOLDERS, it has made a judicial finding that existing equity is
reasonably likely to be in-the-money in the reorganisation -- the US
Trustee/court does not appoint one for a hopelessly underwater stub.
For a distressed equity, this is close to the strongest possible
survival/recovery signal, and it is rare (SOURCES_AND_ANALYSIS Part 1:
one of the strongest stub-survival signals that exists; previously owned
only by an unconsumed sibling poller).

Cross-feeds the capability into the 38-layer engine as an additive
layer. Reachable free via EFTS.

Output: equity_committee_scan.json {ticker: {score, ...}}.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "equity_committee_scan.json"

# Ordered strong -> weak; the exact official-committee phrase is decisive.
# Only bankruptcy-UNAMBIGUOUS phrases. A bare "equity committee" also
# names board compensation/equity committees at healthy companies
# (OKTA, PTON false positives), so it is excluded -- the official-
# committee-of-equity-security-holders language is Chapter 11 specific.
PHRASES = [
    ("official committee of equity security holders", "official_equity_committee", 22),
    ("appointment of an equity committee", "equity_committee_appointed", 20),
    ("equity holders committee", "equity_holders_committee", 18),
]
# A denial guts the signal (motions to appoint are routinely DENIED).
DENIAL_RX = re.compile(
    r"(denied|denying|deny)[^.\n]{0,60}?(equity committee|committee of equity)|"
    r"(equity committee|committee of equity)[^.\n]{0,60}?(denied|not appoint|"
    r"declined to appoint)", re.I)

_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and _TK.match(tk) and tk not in {"NONE", "N/A"})


def efts(phrase, start, end, cap=100):
    from recent import EFTS, _get, requests_quote
    out = []
    offset = 0
    while offset < cap:
        url = (f"{EFTS}?dateRange=custom&startdt={start}&enddt={end}"
               f"&q={requests_quote(chr(34) + phrase + chr(34))}&from={offset}")
        for _ in range(3):
            try:
                d = _get(url).json(); break
            except Exception:
                time.sleep(1.5); d = None
        if not d:
            break
        hits = d.get("hits", {}).get("hits", []) or []
        if not hits:
            break
        out.extend(hits)
        offset += 100
        time.sleep(0.15)
    return out


def _tk_cik(h, cik_map):
    src = h.get("_source", {}) or {}
    ciks = src.get("ciks") or []
    cik = f"{int(ciks[0]):010d}" if ciks else None
    tk = None
    for nm in (src.get("display_names") or []):
        m = _DT.search(nm)
        if m:
            tk = m.group(1); break
    if not tk and cik:
        tk = cik_map.get(cik)
    return (tk.upper() if tk else None), cik, src.get("adsh"), src.get("file_date")


def fetch_text(cik, acc):
    from recent import _get
    if not cik or not acc:
        return ""
    accn = acc.replace("-", "")
    try:
        idx = _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/index.json").json()
        docs = [i["name"] for i in idx["directory"]["item"]
                if i["name"].endswith((".htm", ".html", ".txt")) and "index" not in i["name"]]
        txt = ""
        for d in docs[:2]:
            txt += re.sub(r"<[^>]+>", " ",
                          _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{d}").text)
        return re.sub(r"\s+", " ", txt)[:200000]
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--verify-top", type=int, default=25)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()
    from datetime import datetime, timezone, timedelta
    from recent import _cik_to_ticker_map
    cik_map = _cik_to_ticker_map()
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Equity-committee sweep {start}..{end}", file=sys.stderr)

    per: dict[str, dict] = {}
    for phrase, cls, pts in PHRASES:
        for h in efts(phrase, start, end):
            tk, cik, acc, dt = _tk_cik(h, cik_map)
            if not _valid(tk):
                continue
            rec = per.setdefault(tk, {"ticker": tk, "cik": cik, "score": 0.0,
                                      "classes": {}, "latest_accession": acc,
                                      "date": dt})
            if cls not in rec["classes"]:
                rec["classes"][cls] = pts
                rec["score"] += pts
            if (dt or "") > (rec.get("date") or ""):
                rec["date"] = dt; rec["latest_accession"] = acc
                rec["cik"] = cik or rec["cik"]
        time.sleep(args.sleep)
    print(f"  {len(per)} filers with equity-committee language; checking denials",
          file=sys.stderr)

    # verify: a DENIED motion is a negative, not a positive
    for rec in sorted(per.values(), key=lambda r: -r["score"])[:args.verify_top]:
        txt = fetch_text(rec["cik"], rec["latest_accession"])
        time.sleep(args.sleep)
        if txt and DENIAL_RX.search(txt):
            rec["denied"] = True
            rec["score"] = round(rec["score"] * 0.2, 1)   # gut, don't zero (may re-file)
            rec["classes"]["denial_detected"] = 0

    out = {}
    for tk, rec in per.items():
        rec["score"] = round(rec["score"], 1)
        rec["classes"] = list(rec["classes"].keys())
        if rec["score"] > 0:
            out[tk] = rec
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT} ({len(out)} names)")
    for tk, v in sorted(out.items(), key=lambda x: -x[1]["score"])[:20]:
        d = " DENIED" if v.get("denied") else ""
        print(f"  {tk:<8}{v['score']:>6.0f}  {','.join(v['classes'])[:44]}{d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
