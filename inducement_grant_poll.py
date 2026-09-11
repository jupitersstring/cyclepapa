"""8-K inducement / price-hurdle PSU grant poller (audit S1).

Between proxy seasons the DEF 14A scan is blind to freshly-adopted
incentive structures disclosed in 8-Ks: new-hire inducement grants and
transformation awards -- the PLBY / Penguin Solutions archetype, often
carrying deep multi-tranche stock-price ladders. This poller sweeps
recent 8-Ks for those grants and emits detail records in the same shape
the step-change layer consumes, so the freshest adoptions re-enter the
pipeline (also giving psu_step_change a LIVE generator, audit S3).

Output: induce_live_detail.json (list of detail records).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "induce_live_detail.json"

INDUCEMENT_PHRASES = [
    "inducement grant", "inducement award", "material inducement",
    "new employee inducement", "inducement restricted stock units",
    "employment inducement award",
]
_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _valid(tk):
    return bool(tk and _TK.match(tk) and tk not in {"NONE", "N/A"})


def efts(phrase, start, end, cap=50):
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
        for d in docs[:3]:
            txt += re.sub(r"<[^>]+>", " ",
                          _get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{d}").text)
        return re.sub(r"\s+", " ", txt)
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    from datetime import datetime, timezone, timedelta
    from psu_scoring import extract_features, score
    from universe_filter import is_excluded

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Inducement-grant 8-K sweep {start}..{end}", file=sys.stderr)

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}

    cand = {}
    for phrase in INDUCEMENT_PHRASES:
        for h in efts(phrase, start, end):
            tk = (h["ticker"] or "").upper()
            if not _valid(tk):
                continue
            try:
                if is_excluded(tk)[0]:
                    continue
            except Exception:
                pass
            cand.setdefault((tk, h["accession"]), h)
        time.sleep(args.sleep)
    print(f"  {len(cand)} inducement 8-Ks; extracting price-hurdle grants",
          file=sys.stderr)

    records = []
    for (tk, acc), h in cand.items():
        txt = fetch_text(h["cik"], acc)
        time.sleep(args.sleep)
        if not txt:
            continue
        feats = extract_features(tk, txt)
        if not feats.has_psu_program or not feats.stock_price_hurdles:
            continue                       # keep only real price-hurdle grants
        px = (yf.get(tk, {}) or {}).get("price")
        mc = (yf.get(tk, {}) or {}).get("mcap")
        sc = score(feats, px)
        records.append({
            "ticker": tk, "accession": acc, "filing_date": h["date"],
            "has_psu_program": True,
            "per_share_metrics": feats.per_share_metrics,
            "aggregate_metrics": feats.aggregate_metrics,
            "stock_price_hurdles": feats.stock_price_hurdles,
            "appreciation_pcts": feats.appreciation_pcts,
            "discretionary_language": feats.discretionary_language,
            "retirement_language": feats.retirement_language,
            "repricing_language": feats.repricing_language,
            "front_loaded_language": feats.front_loaded_language,
            "transformation_signal": sc.transformation_signal,
            "alignment": sc.alignment, "upside_kicker": sc.upside_kicker,
            "current_price": px or 0, "market_cap": mc or 0,
            "_source": "induce_live_detail.json",
        })

    OUT.write_text(json.dumps(records, indent=2, default=str))
    print(f"wrote {OUT} ({len(records)} price-hurdle inducement grants)")
    for r in sorted(records, key=lambda x: -len(x["stock_price_hurdles"]))[:15]:
        hs = r["stock_price_hurdles"]
        print(f"  {r['ticker']:<7}{r['filing_date']}  {len(hs)} hurdles "
              f"${min(hs):.0f}-${max(hs):.0f}  transform={r['transformation_signal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
