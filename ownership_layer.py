"""Ownership layer: who else is in the stock, and what are they doing.

Three FMP feeds, per US name in the books (cached in fmp_cache/own/):
  * 13D / 13G filings (acquisition-of-beneficial-ownership) -- 5%+ holders:
      new 13D (an active holder appears), 13G -> 13D switch (a passive holder
      turns active: the strongest version), stake built or cut, known activists
  * 13F summary + top holders (institutional-ownership) -- holder count and
      ownership change, new / closed positions, value investors holding or
      adding, the price the big holders paid vs today
  * every Form 4 transaction (insider-trading/search), SALES included --
      open-market buys vs sells over the last 12 months, C-suite buying,
      and 'talks buybacks while insiders sell'

Nothing here moves a ranking until it passes the event study in
ownership_validate.py (OWNERSHIP_VALIDATION.md) -- same rule as every layer.

Output: ownership.json
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
CACHE = ROOT / "fmp_cache" / "own"
OUT = ROOT / "ownership.json"

ACTIVISTS = re.compile(
    r"elliott|starboard|trian|valueact|jana partners|icahn|pershing square|engaged capital|land & buildings|"
    r"ancora|legion partners|irenic|anson|politan|mantle ridge|sachem head|corvex|third point|cannell|"
    r"blackwells|barington|driver management|palliser|east 72|kerrisdale|mangrove|dendur|impactive|"
    r"jcp investment|carronade|garden investment|22nw|stilwell|bulldog|saba capital|boaz weinstein|"
    r"starboard value|harbert|d\. e\. shaw|macellum|cas investment|scopia|hudson executive|land and buildings|"
    r"ortelius|voss capital|engine capital|gamco|gabelli|oasis management|browning west|alta fox|"
    r"politan|clearway|nelson peltz|freshford|ides capital|breach inlet|converium|lioneye|raging capital|"
    r"greenwood investors|house of wilson|chip wilson|pale fire|tang capital|biotechnology value fund|"
    r"cove street|legion|p\. schoenfeld|ortelius|kent lake|standard general|atlas merchant|rubric capital",
    re.I)
VALUE = re.compile(
    r"paulson|greenlight|baupost|scion|pabrai|berkshire hathaway|markel|fairfax|tweedy|southeastern asset|"
    r"horizon kinetics|private capital management|gate city|cooperman|omega advisors|appaloosa|abrams|"
    r"cannell|ruane|first eagle|royce|kahn brothers|aegis|hotchkis|donald smith|dorsey|bireme|"
    r"punch card|wedgewood|arnhold|yacktman|miller value|longleaf|chou|polen|lyrical|allan mecham|"
    r"akre|nomad|fairholme|burry|klarman|glenview|lone pine|elm ridge|river road|diamond hill|"
    r"moerus|cove street|towle|minerva|harris associates|oakmark|tarsadia|praesidium|legion",
    re.I)
CSUITE = re.compile(r"\b(?:ceo|chief executive|cfo|chief financial|president|chair(?:man)?)\b", re.I)


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


def latest_13f_quarter(today=None):
    """13F is due 45 days after quarter end: the latest COMPLETE quarter."""
    t = today or date.today()
    q_end = [(t.year, 3, 31), (t.year, 6, 30), (t.year, 9, 30), (t.year, 12, 31),
             (t.year - 1, 12, 31), (t.year - 1, 9, 30)]
    for y, m, d in sorted(q_end, reverse=True):
        if date(y, m, d) + timedelta(days=50) <= t:
            return y, (m - 1) // 3 + 1
    return t.year - 1, 4


def fetch(sym):
    y, q = latest_13f_quarter()
    bo = _cached(sym, "13dg", lambda: fmp.get_json("acquisition-of-beneficial-ownership", symbol=sym))
    summ = _cached(sym, f"13f_{y}Q{q}", lambda: fmp.get_json(
        "institutional-ownership/symbol-positions-summary", symbol=sym, year=y, quarter=q))
    hold = _cached(sym, f"holders_{y}Q{q}", lambda: fmp.get_json(
        "institutional-ownership/extract-analytics/holder", symbol=sym, year=y, quarter=q, page=0, limit=40))
    ins = _cached(sym, "f4", lambda: fmp.get_json("insider-trading/search", symbol=sym, page=0, limit=500))
    return sym, bo or [], (summ[0] if isinstance(summ, list) and summ else summ or {}), hold or [], ins or []


def _pct(x):
    try:
        return float(str(x).replace("%", ""))
    except (TypeError, ValueError):
        return None


def kind_13(url):
    u = (url or "").upper()
    return "13D" if "13D" in u else "13G" if "13G" in u else "?"


def analyse_13dg(bo, today):
    """Per reporting person: latest filing, previous filing, kind switch."""
    by = {}
    for f in sorted(bo, key=lambda f: f.get("filingDate") or ""):
        nm = (f.get("nameOfReportingPerson") or "").strip()
        if not nm:
            continue
        by.setdefault(nm, []).append({"date": (f.get("filingDate") or "")[:10], "kind": kind_13(f.get("url")),
                                      "pct": _pct(f.get("percentOfClass")), "url": f.get("url")})
    events, holders = [], []
    cut = (today - timedelta(days=365)).isoformat()
    for nm, fs in by.items():
        last = fs[-1]
        prev = fs[-2] if len(fs) > 1 else None
        act = bool(ACTIVISTS.search(nm))
        holders.append({"name": nm, "kind": last["kind"], "pct": last["pct"], "date": last["date"], "activist": act})
        for i, f in enumerate(fs):
            p = fs[i - 1] if i else None
            if f["kind"] != "13D":
                continue
            if p is None or p["kind"] == "13G":
                ev = "13G->13D switch (passive holder turned active)" if p else "new 13D (active 5%+ holder)"
                events.append({"date": f["date"], "type": "switch" if p else "new_13d", "holder": nm, "pct": f["pct"],
                               "activist": act, "what": ev, "url": f["url"]})
            elif f["pct"] is not None and p["pct"] is not None and f["pct"] - p["pct"] >= 1.0:
                events.append({"date": f["date"], "type": "13d_add", "holder": nm, "pct": f["pct"], "activist": act,
                               "what": f"13D stake up {p['pct']:.1f}% -> {f['pct']:.1f}%", "url": f["url"]})
            elif f["pct"] is not None and p["pct"] is not None and p["pct"] - f["pct"] >= 1.0:
                events.append({"date": f["date"], "type": "13d_cut", "holder": nm, "pct": f["pct"], "activist": act,
                               "what": f"13D stake cut {p['pct']:.1f}% -> {f['pct']:.1f}%", "url": f["url"]})
    seen, ded = set(), []
    for e in sorted(events, key=lambda e: (e["date"], -len(e["holder"]))):
        k = (e["date"], e["type"], e["pct"])
        if k in seen:
            continue                              # joint filers (fund + GP + manager) file the same stake
        seen.add(k)
        ded.append(e)
    events = ded
    recent = [e for e in events if e["date"] >= cut]
    active = [h for h in holders if h["kind"] == "13D" and (h["pct"] or 0) >= 5 and h["date"] >= (today - timedelta(days=730)).isoformat()]
    return events, recent, active


def analyse_insiders(ins, today, days=365):
    cut = (today - timedelta(days=days)).isoformat()
    buys = sells = 0.0
    buyers, sellers, csuite_buy = set(), set(), False
    rows = []
    for t in ins:
        d = (t.get("transactionDate") or t.get("filingDate") or "")[:10]
        tt = t.get("transactionType") or ""
        if d < cut or not (tt.startswith("P-") or tt.startswith("S-")):
            continue
        v = (t.get("securitiesTransacted") or 0) * (t.get("price") or 0)
        who = t.get("reportingName") or "?"
        if tt.startswith("P-"):
            buys += v; buyers.add(who)
            if CSUITE.search(t.get("typeOfOwner") or ""):
                csuite_buy = True
        else:
            sells += v; sellers.add(who)
        rows.append((d, tt[:1], who, v, t.get("price")))
    return {"buy_usd": round(buys), "sell_usd": round(sells), "n_buyers": len(buyers), "n_sellers": len(sellers),
            "csuite_buy": csuite_buy, "net_usd": round(buys - sells),
            "last": sorted(rows, reverse=True)[:3]}


def analyse_holders(hold, price):
    value, new_big, under = [], [], []
    for h in hold:
        nm = h.get("investorName") or ""
        own = h.get("ownership") or 0
        if VALUE.search(nm) and own >= 0.5:
            chg = h.get("changeInSharesNumberPercentage") or 0
            value.append(f"{nm.title()[:28]} {own:.1f}%" + (f" (+{chg:.0f}%)" if chg >= 5 else f" ({chg:.0f}%)" if chg <= -5 else ""))
        if h.get("isNew") and own >= 1.0:
            new_big.append(f"{nm.title()[:28]} new {own:.1f}%")
        app = h.get("avgPricePaid")
        if app and price and own >= 2.0 and price < 0.8 * app:
            under.append((own, f"{nm.title()[:24]} {own:.0f}% paid ~${app:.2f} ({price / app - 1:+.0%})"))
    return value[:4], new_big[:4], [x for _, x in sorted(under, reverse=True)[:3]]


def build(symbols, workers=8):
    fin = json.loads((ROOT / "name_financials.json").read_text())
    today = date.today()
    out = {}
    with ThreadPoolExecutor(workers) as ex:
        data = list(ex.map(fetch, symbols))
    # a manager 'new' in > 3% of all names is a first-time 13F filer (or a restructured
    # filer), not a fresh conviction position -- drop it from the 'new holder' signal
    from collections import Counter
    newc = Counter(h.get("investorName") for _, _, _, hold, _ in data for h in hold if h.get("isNew"))
    first_time = {n for n, c in newc.items() if c > max(8, 0.03 * len(data))}
    if True:
        for i, (sym, bo, summ, hold, ins) in enumerate(data, 1):
            hold = [h for h in hold if not (h.get("isNew") and h.get("investorName") in first_time)]
            f = fin.get(sym) or {}
            events, recent, active = analyse_13dg(bo, today)
            insd = analyse_insiders(ins, today)
            value, new_big, under = analyse_holders(hold, f.get("price"))
            s13 = {k: summ.get(k) for k in ("date", "investorsHolding", "investorsHoldingChange", "ownershipPercent",
                                             "ownershipPercentChange", "newPositions", "closedPositions",
                                             "putCallRatio")} if summ else {}
            rec = {"events_13d": events, "recent_13d": recent,
                   "active_13d": sorted(active, key=lambda h: -(h["pct"] or 0))[:4],
                   "inst": s13, "value_holders": value, "new_big_holders": new_big, "underwater_holders": under,
                   "insiders": insd}
            rec["summary"] = summary(rec, f)
            out[sym] = rec
            if i % 200 == 0:
                print(f"  {i}/{len(symbols)}", flush=True)
    return out


def summary(r, f):
    bits = []
    for e in sorted(r["recent_13d"], key=lambda e: e["date"], reverse=True)[:2]:
        bits.append(("ACTIVIST " if e["activist"] else "") + f"{e['holder'].title()[:30]}: {e['what']}"
                    + (f" ({e['pct']:.1f}%)" if e.get("pct") and "->" not in e["what"] else "") + f" [{e['date']}]")
    if not r["recent_13d"] and r["active_13d"]:
        h = r["active_13d"][0]
        bits.append(("activist " if h["activist"] else "") + f"13D holder {h['name'].title()[:30]} {h['pct']:.1f}%")
    s = r["inst"]
    if s.get("investorsHoldingChange") is not None and s.get("investorsHolding"):
        ch = s["investorsHoldingChange"] / max(1, s["investorsHolding"] - s["investorsHoldingChange"])
        if abs(ch) >= 0.10 and abs(s["investorsHoldingChange"]) >= 5:
            bits.append(f"13F holders {s['investorsHoldingChange']:+d} ({ch:+.0%}) to {s['investorsHolding']}")
    if r["value_holders"]:
        bits.append("value holders: " + "; ".join(r["value_holders"][:2]))
    if r["new_big_holders"]:
        bits.append("; ".join(r["new_big_holders"][:2]))
    i = r["insiders"]
    if i["buy_usd"] >= 100_000 or i["sell_usd"] >= 1_000_000:
        bits.append(f"insiders 12m: bought ${i['buy_usd'] / 1e6:.1f}M ({i['n_buyers']}), sold ${i['sell_usd'] / 1e6:.1f}M ({i['n_sellers']})"
                    + (" · C-suite buying" if i["csuite_buy"] else ""))
    if r["underwater_holders"]:
        bits.append("big holders under water: " + r["underwater_holders"][0])
    return " · ".join(bits)


def universe():
    fin = json.loads((ROOT / "name_financials.json").read_text())
    import openpyxl
    tk = set()
    for b in ("MOST_ASYMMETRIC.xlsx", "OTC_BOOK.xlsx"):
        try:
            wb = openpyxl.load_workbook(ROOT / b, read_only=True)
        except Exception:
            continue
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                for v in (r or ())[:3]:
                    if isinstance(v, str):
                        t = v.replace("●", "").strip()
                        if t in fin and (fin[t].get("country") or "US") == "US" and not fin[t].get("not_common"):
                            tk.add(t)
    for fn in ("governance_discount.json", "call_intent.json", "event_detail.json", "psu_detail.json"):
        p = ROOT / fn
        if p.exists():
            tk |= {t for t in json.loads(p.read_text()) if t in fin and (fin[t].get("country") or "US") == "US"
                   and not fin[t].get("not_common")}
    return sorted(tk)


def main() -> int:
    import sys
    syms = sys.argv[1:] or universe()
    print(f"ownership layer: {len(syms)} US names")
    out = build(syms)
    OUT.write_text(json.dumps(out, indent=1))
    n13 = sum(1 for r in out.values() if r["recent_13d"])
    nact = sum(1 for r in out.values() if any(e["activist"] for e in r["recent_13d"]))
    nsw = sum(1 for r in out.values() if any(e["type"] == "switch" for e in r["recent_13d"]))
    nb = sum(1 for r in out.values() if r["insiders"]["buy_usd"] >= 100_000)
    print(f"wrote {OUT.name}: {len(out)} names; 13D activity 12m {n13} (activist {nact}, 13G->13D {nsw}); "
          f"insider buying >= $100k: {nb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
