"""Structured distressed value-injection -- the Cundill / Sibir Energy play.

Peter Cundill's Sibir trade: a hard-asset-backed company (≈1bn barrels of
reserves) whose EQUITY had collapsed in a MACRO washout (47p -> 10p on the
Russian crisis, not on any deterioration of the reserves), that was
capital-STARVED and raising money on investor-favourable terms via a SENIOR
/ CONVERTIBLE instrument -- a convertible debenture at a small premium, 12%
coupon, preferential over the common. The edge was structural: you buy the
INSTRUMENT, not the common, so the downside is floored by seniority + coupon
+ asset value while the convert keeps the equity upside. A built-in margin
of safety.

The rest of the engine sees the ingredients but scores the defining feature
BACKWARDS -- premium_injection penalises convertibles/preferred as "illusory
premium", distressed_stub penalises "new preferred". This module flips that
for the specific case: a STRUCTURED RAISE is the SIGNAL when it lands in a
DISTRESSED, ASSET-BACKED, WASHED-OUT name.

Gate (hard conjunction):
  1. STRUCTURED RAISE -- EDGAR 8-K / 424B for a convertible debenture,
     senior/secured convertible note, or convertible preferred / PIPE.
  2. ASSET FLOOR -- hidden-asset (credit-agreement sweep) OR NCAV OR a hard
     net-cash/NCAV geometry floor: asset value must back the downside.
  3. WASHOUT or DISTRESS -- deep drawdown from the 52-week high (macro/forced
     collapse) and/or a small, capital-starved cap.
Terms (coupon %, seniority, convert) are parsed from the filing for the
top candidates and add a margin-of-safety bonus.

Output: structured_distressed_injection.json keyed by ticker.
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
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "structured_distressed_injection.json"

# (phrase, raise_type). Senior/secured/convertible-debenture rank as the
# hardest margin-of-safety instruments.
PHRASES = [
    ("convertible debenture", "convertible_debenture"),
    ("senior secured convertible", "senior_secured_convertible"),
    ("senior convertible note", "senior_convertible"),
    ("convertible senior note", "senior_convertible"),
    ("convertible preferred", "convertible_preferred"),
    ("secured convertible note", "secured_convertible"),
    ("private placement of convertible", "convertible_pipe"),
]
RAISE_PTS = {"convertible_debenture": 4, "senior_secured_convertible": 5,
             "senior_convertible": 4, "secured_convertible": 4,
             "convertible_preferred": 3, "convertible_pipe": 3}

_DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")
_TK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")
COUPON_RX = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%\s*(?:senior|secured|convertible|coupon|notes?|debenture|per annum|interest)", re.I)
SENIOR_RX = re.compile(r"\b(senior|secured|preferential|first lien|priority)\b", re.I)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _load(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def efts(phrase, start, end, cap=60):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}"
           f"&forms={requests_quote('8-K,424B5,424B3,424B4')}")
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
        if tk and _TK.match(tk):
            out.append({"ticker": tk,
                        "cik": f"{int(ciks[0]):010d}" if ciks else None,
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
        return re.sub(r"\s+", " ", txt)[:400000]
    except Exception:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--cap", type=int, default=60)
    ap.add_argument("--verify-top", type=int, default=30)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Structured distressed injection sweep {start}..{end}", file=sys.stderr)

    yf = _load("yfinance_quick.json")
    credit = _load("credit_agreement_mine.json")     # hidden-asset / sweep
    ncav = _load("net_net_ncav.json")
    geo = _load("payoff_geometry.json")

    # 1) find the structured raises.
    per = {}
    for phrase, rtype in PHRASES:
        for h in efts(phrase, start, end, cap=args.cap):
            tk = h["ticker"].upper()
            bad, _ = is_excluded(tk)
            if bad:
                continue
            rec = per.setdefault(tk, {"ticker": tk, "raise_types": {},
                                      "date": h["date"], "cik": h["cik"],
                                      "accession": h["accession"]})
            rec["raise_types"][rtype] = phrase
            if h["date"] and h["date"] > rec["date"]:
                rec["date"] = h["date"]; rec["accession"] = h["accession"]; rec["cik"] = h["cik"]
        time.sleep(args.sleep)
    print(f"{len(per)} names with a structured raise", file=sys.stderr)

    # 2) hard-gate on asset floor + washout/distress; score.
    out = {}
    for tk, rec in per.items():
        y = yf.get(tk) or {}
        g = geo.get(tk) or {}
        price = _num(y.get("price")); hi = _num(y.get("fwk_high")); mcap = _num(y.get("mcap"))
        cr = credit.get(tk) or {}; nc = ncav.get(tk) or {}
        asset_floor = ((_num(cr.get("score")) or 0) > 0) \
            or (g.get("floor_source") in ("net-cash", "NCAV")) \
            or (_num(nc.get("ncav_per_share")) is not None and price
                and _num(nc.get("ncav_per_share")) >= 0.5 * price)
        drawdown = (price / hi - 1.0) if (price and hi and hi > 0) else None
        washout = drawdown is not None and drawdown <= -0.50
        small = mcap is not None and 0 < mcap < 2e9
        # require the Cundill combo: a structured raise is only THIS archetype
        # when it lands in an asset-backed, distressed/washed-out name.
        if not (asset_floor and (washout or small)):
            continue
        best_rt = max(rec["raise_types"], key=lambda r: RAISE_PTS.get(r, 0))
        s = 6.0 + RAISE_PTS.get(best_rt, 3)
        if asset_floor:
            s += 6
        if washout:
            s += 5
        if small:
            s += 3
        out[tk] = {
            "ticker": tk, "name": y.get("name", tk),
            "raise_types": sorted(rec["raise_types"]),
            "instrument": best_rt,
            "asset_floor": bool(asset_floor),
            "drawdown_from_high": round(drawdown, 3) if drawdown is not None else None,
            "washout": bool(washout), "small_cap": bool(small),
            "mcap": mcap, "date": rec["date"],
            "cik": rec["cik"], "accession": rec["accession"],
            "geometry_ratio": g.get("ratio"),
            "score": round(s, 1),
        }

    # 3) parse terms (coupon / seniority = margin of safety) for the top names.
    for rec in sorted(out.values(), key=lambda r: -r["score"])[:args.verify_top]:
        txt = fetch_text(rec.get("cik"), rec.get("accession"))
        time.sleep(args.sleep)
        rec["verified"] = True
        if not txt:
            continue
        m = COUPON_RX.search(txt)
        if m:
            try:
                rec["coupon_pct"] = float(m.group(1)); rec["score"] += 2
            except ValueError:
                pass
        if SENIOR_RX.search(txt):
            rec["senior_secured"] = True; rec["score"] += 2
        rec["score"] = round(rec["score"], 1)

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: -r["score"])
    print(f"\nwrote {OUT} ({len(out)} structured distressed injections)")
    print(f"{'TKR':<7}{'SCORE':>6}{'DD%':>6}{'COUP':>6}  INSTRUMENT / NAME")
    for r in ranked[:25]:
        dd = f"{r['drawdown_from_high']*100:.0f}" if r.get("drawdown_from_high") is not None else "-"
        cp = f"{r.get('coupon_pct','')}" if r.get("coupon_pct") else "-"
        print(f"{r['ticker']:<7}{r['score']:>6.1f}{dd:>6}{cp:>6}  "
              f"{r['instrument']:<24} {(r.get('name') or '')[:26]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
