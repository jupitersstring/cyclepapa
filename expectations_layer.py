"""Expectations layer: what is already priced in.

Per US name in the books:
  analysts (FMP)   coverage (neglect), consensus / high / low price target and
                   the upside it implies, the target trend (last quarter vs last
                   year), rating mix, upgrades vs downgrades in 90 days, forward
                   EPS / revenue and the forward P/E they imply
  short interest   FINRA consolidated short interest (latest settlement): shares
                   short, % of float (FMP float), days to cover, change vs the
                   prior settlement

Read-out per name, e.g. "2 analysts (neglected) · target $3.00 (+68%), trend down ·
fwd P/E 4.1 · short 12% of float, 6.2 days to cover (+18%)".

What these have meant for returns is tested in expectations_validate (rating
changes: event study; short interest: cross-section over past settlements) --
EXPECTATIONS_VALIDATION.md. Until then they are context, not ranking inputs.

Outputs: expectations.json; FINRA files cached in fmp_cache/finra_si/.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
CACHE = ROOT / "fmp_cache" / "expect"
SI = ROOT / "fmp_cache" / "finra_si"
OUT = ROOT / "expectations.json"
FINRA = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def _cached(sym, key, fn, ttl_days=3):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{sym.replace('/', '_')}__{key}.json"
    if p.exists() and time.time() - p.stat().st_mtime < ttl_days * 86400:
        return json.loads(p.read_text())
    try:
        d = fn()
    except Exception:
        d = []
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    tmp.replace(p)
    return d


# ------------------------------------------------------------------ FINRA short interest
def finra_date(d: str) -> list:
    """All consolidated short-interest rows for one settlement date (cached)."""
    SI.mkdir(parents=True, exist_ok=True)
    p = SI / f"{d}.json"
    if p.exists():
        return json.loads(p.read_text())
    rows, off = [], 0
    while True:
        body = {"limit": 5000, "offset": off,
                "compareFilters": [{"fieldName": "settlementDate", "fieldValue": d, "compareType": "EQUAL"}]}
        for i in range(4):
            try:
                r = requests.post(FINRA, json=body, headers={"Accept": "application/json",
                                                             "User-Agent": "cyclepapa research"}, timeout=90)
                if r.status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(3 * (i + 1))
        else:
            break
        chunk = r.json() if r.text.strip() else []
        rows += chunk
        if len(chunk) < 5000:
            break
        off += 5000
    keep = [{"s": x["symbolCode"], "si": x.get("currentShortPositionQuantity"), "prev": x.get("previousShortPositionQuantity"),
             "adv": x.get("averageDailyVolumeQuantity"), "dtc": x.get("daysToCoverQuantity"), "mkt": x.get("marketClassCode")}
            for x in rows if x.get("symbolCode")]
    if keep:
        p.write_text(json.dumps(keep))
    return keep


def settlement_dates(start: str, end: str | None = None):
    """FINRA settles mid-month and at month end; probe the business days around the 15th and the last day."""
    end_d = date.fromisoformat(end) if end else date.today()
    d = date.fromisoformat(start).replace(day=1)
    out = []
    while d <= end_d:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        for anchor in (d.replace(day=15), nxt - timedelta(days=1)):
            for back in range(0, 5):
                c = anchor - timedelta(days=back)
                if c.weekday() < 5 and c <= end_d:
                    out.append(c.isoformat())
                    break
        d = nxt
    return out


def latest_si():
    for d in sorted(settlement_dates((date.today() - timedelta(days=45)).isoformat()), reverse=True):
        rows = finra_date(d)
        if rows:
            return d, {x["s"]: x for x in rows}
        # a date with no rows may simply be a non-settlement day: try the one before
    return None, {}


# ------------------------------------------------------------------ FMP analysts
def fetch(sym):
    ptc = _cached(sym, "ptc", lambda: fmp.get_json("price-target-consensus", symbol=sym))
    pts = _cached(sym, "pts", lambda: fmp.get_json("price-target-summary", symbol=sym))
    gc = _cached(sym, "gcons", lambda: fmp.get_json("grades-consensus", symbol=sym))
    gr = _cached(sym, "grades", lambda: fmp.get_json("grades", symbol=sym, limit=200))
    est = _cached(sym, "est", lambda: fmp.get_json("analyst-estimates", symbol=sym, period="annual", page=0, limit=6))
    flt = _cached(sym, "float", lambda: fmp.get_json("shares-float", symbol=sym))
    one = lambda x: (x[0] if isinstance(x, list) and x else x if isinstance(x, dict) else {}) or {}
    return sym, one(ptc), one(pts), one(gc), gr or [], est or [], one(flt)


def analyse(sym, ptc, pts, gc, gr, est, flt, f, si, today):
    price = f.get("price")
    usd = (f.get("currency") or "USD") == "USD"
    r = {}
    fy = [e for e in est if (e.get("date") or "") >= today.isoformat()]
    nxt = sorted(fy, key=lambda e: e["date"])[0] if fy else None
    n_an = max([nxt.get("numAnalystsEps") or 0, nxt.get("numAnalystsRevenue") or 0] if nxt else [0])
    n_rat = sum(gc.get(k) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
    # analysts behind the CURRENT forward estimate; the ratings tally is all-time, so only a fallback
    r["n_analysts"] = n_an if n_an else min(n_rat, 3)
    tc = ptc.get("targetConsensus") or ptc.get("targetMedian")
    if tc and price and usd:
        r["pt"] = tc
        r["pt_upside"] = tc / price - 1
        if ptc.get("targetHigh") and ptc.get("targetLow"):
            r["pt_low_high"] = (ptc["targetLow"], ptc["targetHigh"])
    lq, ly = pts.get("lastQuarterAvgPriceTarget") or 0, pts.get("lastYearAvgPriceTarget") or 0
    if lq and ly:
        r["pt_trend"] = lq / ly - 1
    if n_rat:
        r["ratings"] = {k: gc.get(k) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
        r["rating_consensus"] = gc.get("consensus")
    cut = (today - timedelta(days=90)).isoformat()
    ups = sum(1 for g in gr if (g.get("date") or "") >= cut and g.get("action") == "upgrade")
    downs = sum(1 for g in gr if (g.get("date") or "") >= cut and g.get("action") == "downgrade")
    r["upgrades_90d"], r["downgrades_90d"] = ups, downs
    if nxt and nxt.get("epsAvg") and price and usd:
        r["fwd_eps"], r["fwd_fy"] = nxt["epsAvg"], nxt["date"][:4]
        r["fwd_pe"] = price / nxt["epsAvg"] if nxt["epsAvg"] > 0 else None
    if nxt and nxt.get("revenueAvg"):
        r["fwd_rev"] = nxt["revenueAvg"]
    s = si.get(sym)
    if s and s.get("si") is not None:
        r["short_shares"] = s["si"]
        r["days_to_cover"] = s.get("dtc")
        if s.get("prev"):
            r["short_change"] = s["si"] / s["prev"] - 1 if s["prev"] else None
        fl = flt.get("floatShares")
        if fl:
            r["short_pct_float"] = s["si"] / fl
    # sanity: a target set before a reverse split, or a float count from before an issuance / split,
    # produces absurd ratios -- blank them rather than show them
    if r.get("pt_upside") is not None and not (-0.9 < r["pt_upside"] < 5):
        r.pop("pt", None); r.pop("pt_upside", None); r.pop("pt_low_high", None)
        r["flag"] = "price target stale (pre-split?)"
    if r.get("short_pct_float") is not None and r["short_pct_float"] > 1.0:
        r.pop("short_pct_float")
        r["flag"] = (r.get("flag", "") + "; " if r.get("flag") else "") + "float count stale"
    if r.get("fwd_pe") is not None and r["fwd_pe"] < 1:
        r.pop("fwd_pe")
    r["summary"] = summary(r)
    return r


def summary(r):
    b = []
    n = r.get("n_analysts") or 0
    b.append("no analyst coverage (orphan)" if n == 0 else f"{n} analyst{'s' if n > 1 else ''}" + (" (neglected)" if n <= 2 else ""))
    if r.get("pt"):
        b.append(f"target ${r['pt']:,.2f} ({r['pt_upside']:+.0%})"
                 + (f", trend {'up' if r['pt_trend'] > 0 else 'down'} {abs(r['pt_trend']):.0%}" if r.get("pt_trend") and abs(r["pt_trend"]) >= 0.1 else ""))
    if r.get("upgrades_90d") or r.get("downgrades_90d"):
        b.append(f"{r['upgrades_90d']} up / {r['downgrades_90d']} down 90d")
    if r.get("fwd_pe"):
        b.append(f"fwd P/E {r['fwd_pe']:.1f} (FY{r['fwd_fy']})")
    elif r.get("fwd_eps") is not None and r["fwd_eps"] <= 0:
        b.append(f"loss expected FY{r['fwd_fy']}")
    if r.get("short_pct_float") is not None and r["short_pct_float"] >= 0.03:
        b.append(f"short {r['short_pct_float']:.0%} of float" + (f", {r['days_to_cover']:.1f} days to cover" if r.get("days_to_cover") else "")
                 + (f" ({r['short_change']:+.0%})" if r.get("short_change") is not None and abs(r["short_change"]) >= 0.1 else ""))
    return " · ".join(b)


def main() -> int:
    import sys
    import ownership_layer
    syms = sys.argv[1:] or ownership_layer.universe()
    fin = json.loads((ROOT / "name_financials.json").read_text())
    d, si = latest_si()
    print(f"expectations: {len(syms)} names; FINRA short interest settlement {d} ({len(si)} securities)")
    today = date.today()
    out = {}
    with ThreadPoolExecutor(8) as ex:
        for i, (sym, ptc, pts, gc, gr, est, flt) in enumerate(ex.map(fetch, syms), 1):
            out[sym] = analyse(sym, ptc, pts, gc, gr, est, flt, fin.get(sym) or {}, si, today)
            if i % 300 == 0:
                print(f"  {i}/{len(syms)}", flush=True)
    OUT.write_text(json.dumps({"_si_date": d, **out}, indent=1))
    orphan = sum(1 for k, r in out.items() if (r.get("n_analysts") or 0) == 0)
    hs = sum(1 for r in out.values() if (r.get("short_pct_float") or 0) >= 0.15)
    print(f"wrote {OUT.name}: {len(out)} names; no coverage {orphan}; short >= 15% of float {hs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
