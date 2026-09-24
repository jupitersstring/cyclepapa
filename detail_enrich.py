"""Price-based enrichment of the filing-level detail -- the facts a reader
asks next.

1. EVENT REACTION (event_detail.json): return since the event date and the
   excess vs SPY, days since, and whether the market has already moved
   ("priced" if |excess| >= 20%) -- has the news been priced or not?
2. APPOINTMENT REACTION (turnaround_signal.csv): return since the 8-K.
3. PSU PAY-FOR-PERFORMANCE (psu_detail.json): for each past cycle with a
   stated payout, the stock's TSR over the same calendar years vs SPY.
   A plan that paid >= 100% of target while the stock lagged SPY by > 10pp is
   MISALIGNED (soft goals); one that paid < 100% while the stock lagged is
   ALIGNED. The grade is adjusted (-2 misaligned / +1 aligned) and the reason
   recorded.

Prices: FMP dividend-adjusted daily closes (cached in fmp_cache/px_long).
"""

from __future__ import annotations

import csv
import json
import re
import time
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
PX = ROOT / "fmp_cache" / "px_long"


def closes(sym, start="2017-12-01"):
    PX.mkdir(parents=True, exist_ok=True)
    f = PX / (sym.replace("/", "_") + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < 3 * 86400:
        return json.loads(f.read_text())
    try:
        rows = fmp.daily_adjusted(sym, start)
    except RuntimeError:
        rows = []
    d = [[r[0], r[4]] for r in rows]
    f.write_text(json.dumps(d))
    return d


def px_on_or_after(px, d):
    if not px:
        return None
    i = bisect_left([r[0] for r in px], d)
    return px[i][1] if i < len(px) else None


def px_on_or_before(px, d):
    if not px:
        return None
    i = bisect_right([r[0] for r in px], d)
    return px[i - 1][1] if i > 0 else None


def ret_between(px, a, b=None):
    p0 = px_on_or_after(px, a)
    p1 = px_on_or_before(px, b) if b else (px[-1][1] if px else None)
    return (p1 / p0 - 1) if p0 and p1 else None


def enrich_events(spy):
    p = ROOT / "event_detail.json"
    if not p.exists():
        return 0
    ev = json.loads(p.read_text())
    syms = [t for t, lst in ev.items() if any(e.get("date") for e in lst)]
    with ThreadPoolExecutor(8) as ex:
        px = dict(zip(syms, ex.map(closes, syms)))
    n = 0
    today = date.today()
    for t, lst in ev.items():
        for e in lst:
            d = e.get("date")
            if not d or not px.get(t):
                continue
            r = ret_between(px[t], d)
            m = ret_between(spy, d)
            if r is None:
                continue
            e["ret_since"] = round(r, 4)
            e["xret_since"] = round(r - (m or 0), 4)
            e["days_since"] = (today - date.fromisoformat(d)).days
            e["priced"] = "moved" if abs(r - (m or 0)) >= 0.20 else "not yet"
            n += 1
    p.write_text(json.dumps(ev, indent=1))
    return n


def enrich_turnaround(spy):
    p = ROOT / "turnaround_signal.csv"
    if not p.exists():
        return 0
    rows = list(csv.DictReader(open(p)))
    if not rows:
        return 0
    syms = sorted({r["ticker"] for r in rows})
    with ThreadPoolExecutor(8) as ex:
        px = dict(zip(syms, ex.map(closes, syms)))
    for r in rows:
        x = ret_between(px.get(r["ticker"]) or [], r["filing_date"]) if r.get("filing_date") else None
        m = ret_between(spy, r["filing_date"]) if r.get("filing_date") else None
        r["ret_since"] = "" if x is None else round(x, 4)
        r["xret_since"] = "" if x is None else round(x - (m or 0), 4)
    fields = list(rows[0].keys())
    for k in ("ret_since", "xret_since"):
        if k not in fields:
            fields.append(k)
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    return len(rows)


def enrich_psu(spy):
    p = ROOT / "psu_detail.json"
    if not p.exists():
        return 0
    psu = json.loads(p.read_text())
    syms = [t for t, r in psu.items() if r.get("history")]
    with ThreadPoolExecutor(8) as ex:
        px = dict(zip(syms, ex.map(closes, syms)))
    n = 0
    for t, r in psu.items():
        checks = []
        for k, v in r.get("history") or []:
            yrs = re.findall(r"20\d\d", k)
            if "grant" in k and yrs:
                a, b = int(yrs[0]), int(yrs[0]) + 2          # a grant covers a 3-year cycle
            elif len(yrs) == 2:
                a, b = int(yrs[0]), int(yrs[1])
            else:
                continue
            tsr = ret_between(px.get(t) or [], f"{a}-01-01", f"{b}-12-31")
            mkt = ret_between(spy, f"{a}-01-01", f"{b}-12-31")
            if tsr is None or mkt is None:
                continue
            rel = tsr - mkt
            verdict = ("MISALIGNED" if v >= 100 and rel < -0.10 else
                       "ALIGNED" if (v < 100 and rel < 0) or (v >= 100 and rel >= 0) else "MIXED")
            checks.append({"cycle": k, "payout": v, "tsr": round(tsr, 3), "vs_spy": round(rel, 3),
                           "verdict": verdict})
        if not checks:
            continue
        r["pay_for_performance"] = checks
        base = r.get("grade_pts_base", r.get("grade_pts", 0))
        r["grade_pts_base"] = base
        adj = -2 if any(c["verdict"] == "MISALIGNED" for c in checks) else \
            (1 if all(c["verdict"] == "ALIGNED" for c in checks) else 0)
        why = [w for w in r.get("why") or [] if not w.startswith("pay-for-performance")]
        c0 = checks[0]
        why.append(f"pay-for-performance: {c0['cycle']} paid {c0['payout']:.0f}% while TSR was "
                   f"{c0['tsr'] * 100:+.0f}% ({c0['vs_spy'] * 100:+.0f}pp vs SPY) — {c0['verdict'].lower()}")
        r["why"] = why
        r["grade_pts"] = base + adj
        pts = r["grade_pts"]
        r["grade"] = "A" if pts >= 7 else "B" if pts >= 4 else "C" if pts >= 1 else "D"
        n += 1
    p.write_text(json.dumps(psu, indent=1))
    return n


def main() -> int:
    spy = closes("SPY")
    a = enrich_events(spy)
    b = enrich_turnaround(spy)
    c = enrich_psu(spy)
    print(f"detail enrich: {a} events priced; {b} appointments priced; {c} PSU plans pay-for-performance checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
