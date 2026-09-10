"""Acquisition-at-premium screen: Silas's 'eclipsed out of existence' doctrine.

M&A signature = an upcoming eclipse conjunct or opposite the natal SUN
(the company 'eclipsed'), corroborated by heavy outers on the Sun in the
same period:
  T.Pluto hard Sun  x1.6  (absorbed by larger power -- compendium: Pluto = M&A)
  T.Saturn hard Sun x1.25 (structure ends)
  T.Neptune hard Sun x1.15 (dissolution)
Eclipse base: total_solar 10 / annular 8 / partial_solar 5 / total_lunar 4 /
partial_lunar 3 / penumbral 2; conj x1.1 (absorbed/power) vs opp x1.0
(removed); orb <=0.75 x1.4. Sum over eclipses TODAY..2028-03.

Runs BOTH universes: US Ritter (NYSE 9:30) and the curated UK/EU list
(ipos_eu.csv, LOCAL exchange opens and coordinates -- LSE 08:00 London,
Euronext/XETRA 09:00 CET etc).

Validator context (qualitative): the consensus lists kept surfacing later
premium takeouts (KITE $11.9B, PRVL, CPHD $4B, TSRO $5.1B, PFPT $12.3B,
MODN, IMGN $10B); a historical eclipse backtest would need pre-2026 events
(not in forward_events.json) -- flagged, not done.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe

from reverse_arch_v8_1_asymmetry import SIGNS, exchange_open_jd, hard_asp, load_ipos, orb

TODAY = date.fromisoformat(os.environ.get("RA_ASOF", "2026-09-10"))
HORIZON = "2028-03-31"

NAT = [("Sun", swe.SUN), ("Moon", swe.MOON), ("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
       ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN),
       ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)]

ECL_BASE = {"total_solar": 10.0, "annular_solar": 8.0, "partial_solar": 5.0,
            "solar": 5.0, "total_lunar": 4.0, "partial_lunar": 3.0, "penumbral_lunar": 2.0}


def natal_us(date_str):
    jd, _, _ = exchange_open_jd(date_str)
    return {nm: swe.calc_ut(jd, pid)[0][0] % 360 for nm, pid in NAT}


def natal_local(date_str, tz, hh, mm):
    d = date.fromisoformat(date_str)
    local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo(tz))
    utc = local.astimezone(timezone.utc)
    jd = swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60.0)
    return {nm: swe.calc_ut(jd, pid)[0][0] % 360 for nm, pid in NAT}


def outer_on_sun(sun_lon, ecl_date):
    """Corroborating slow-outer hard aspects to natal Sun within +/-6mo of eclipse."""
    mult = 1.0
    tags = []
    ed = date.fromisoformat(ecl_date)
    for off in (-180, -90, 0, 90, 180):
        dd = ed + timedelta(days=off)
        jd = swe.julday(dd.year, dd.month, dd.day, 12)
        for nm, pid, m in (("Pluto", swe.PLUTO, 1.6), ("Saturn", swe.SATURN, 1.25), ("Neptune", swe.NEPTUNE, 1.15)):
            l = swe.calc_ut(jd, pid)[0][0] % 360
            r = hard_asp(l, sun_lon, 1.5)
            if r and f"{nm}" not in [t.split(":")[0] for t in tags]:
                mult *= m
                tags.append(f"{nm}:{r[0]}{r[1]:.1f}")
    return mult, tags


def score_chart(n, eclipses):
    total = 0.0
    hits = []
    for e in eclipses:
        r = hard_asp(e["lon"], n["Sun"], 1.5)
        if not r or r[0] == "sq":
            continue
        asp, o = r
        base = next((v for k, v in ECL_BASE.items() if e["type"].startswith(k)), 3.0)
        pts = base * (1.5 - o) / 1.5 * (1.1 if asp == "conj" else 1.0)
        if o <= 0.75:
            pts *= 1.4
        mult, tags = outer_on_sun(n["Sun"], e["date"])
        pts *= mult
        total += pts
        hits.append(f"{e['date']} {e['type'][:13]} {asp}Sun {o:.2f}" + (f" [{'/'.join(tags)}]" if tags else ""))
    return total, hits


def main():
    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    ecl = [e for e in events["eclipses"] if TODAY.isoformat() < e["date"] <= HORIZON]
    print(f"as_of={TODAY} eclipses in horizon={len(ecl)}")

    rows = []
    # US universe
    ipos = load_ipos(None, "/home/claude/ritter_full.csv", [])
    for ipo in ipos:
        try:
            n = natal_us(ipo["date"])
        except Exception:
            continue
        s, hits = score_chart(n, ecl)
        if s > 0:
            yr = int(ipo["date"][:4])
            rows.append({"ticker": ipo["ticker"], "name": ipo.get("name", "").strip('"'),
                         "date": ipo["date"], "mkt": "US",
                         "era": "2017+" if yr >= 2017 else ("2010-16" if yr >= 2010 else "old"),
                         "acq_score": round(s, 2), "signals": "; ".join(hits)})
    # EU universe
    for r in csv.DictReader(open("ipos_eu.csv")):
        try:
            n = natal_local(r["date"], r["tz"], int(r["open_h"]), int(r["open_m"]))
        except Exception as e:
            print(f"  EU skip {r['ticker']}: {e}")
            continue
        s, hits = score_chart(n, ecl)
        if s > 0:
            rows.append({"ticker": r["ticker"], "name": r["name"], "date": r["date"],
                         "mkt": r["exchange"], "era": f"conf:{r['confidence']}",
                         "acq_score": round(s, 2), "signals": "; ".join(hits)})

    rows.sort(key=lambda x: -x["acq_score"])
    out = Path("/mnt/user-data/outputs/acq_screen.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"Wrote {out} rows={len(rows)}")

    print("\n=== TOP ACQUISITION-AT-PREMIUM CANDIDATES (US 2017+ & all EU), unique charts ===")
    seen = set(); k = 0
    for r in rows:
        if r["mkt"] == "US" and r["era"] not in ("2017+",):
            continue
        if r["date"] in seen:
            continue
        seen.add(r["date"]); k += 1
        if k > 25:
            break
        print(f"  {r['ticker']:<8s}{r['name'][:26]:<26s}{r['date']} [{r['mkt'][:12]:<12s}|{r['era']:<9s}] score={r['acq_score']:6.1f}")
        print(f"           {r['signals'][:150]}")

    print("\n=== TOP any-era US (context incl. dead tickers) ===")
    seen = set(); k = 0
    for r in rows:
        if r["mkt"] != "US" or r["date"] in seen:
            continue
        seen.add(r["date"]); k += 1
        if k > 8:
            break
        print(f"  {r['ticker']:<8s}{r['name'][:26]:<26s}{r['date']} score={r['acq_score']:6.1f}  {r['signals'][:110]}")


if __name__ == "__main__":
    main()
