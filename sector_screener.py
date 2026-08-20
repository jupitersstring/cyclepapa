"""General SECTOR-AWARE convergence screener (all sectors, correct sympathies).

RCA of why MRNA worked (see below) generalized to every sector:

  MRNA's pharma move worked because the pharma RULING PLANETS were loaded in
  the natal chart -- Neptune (pharma) in Pisces (its own domicile) conjunct
  Mars 0.01; Jupiter (big-pharma scale) in Sagittarius (domicile); Mercury
  (clinical) stationing; Pluto (transformation) angular. A generic bullish
  transit stack then expressed THROUGH that pharma-loaded channel as a pharma
  news catalyst. The generic screener missed it because it watched generic
  money points (Venus/Jupiter/Sun), not the SECTOR RULER.

Generalization: for each stock, use ITS sector's rulers (provenance-tiered,
from sector_rulerships.py) as
  (a) the natal-loading fuel  -- how dignified/angular/stationing/luminary-tied
      the sector's ruling planets are (the "relevant sympathies"), and
  (b) extra transit targets    -- outers & Jupiter & eclipses hitting the
      natal sector ruler, not only the generic money axis.

setup_score = convergence(slow substrate + fast trigger in one ~90d window)
              x sector_fuel(1 + natal sector loading).

Emits sector_screener.csv with per-stock sector, sector_load, which ruler is
loaded, and the peak convergence window + Silas position-by date.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import swisseph as swe

from reverse_arch_v8_1_asymmetry import SIGNS, exchange_open_jd, hard_asp, load_ipos, orb
from sector_rulerships import (
    SECTOR_RULERS, TIER_WEIGHT, classify_sector,
    DOMICILE, MODERN_DOMICILE, EXALTATION,
)

START = date(2026, 8, 19)
END = date(2028, 6, 1)
STEP_DAYS = 10
WINDOW_SAMPLES = 95 // STEP_DAYS
SLOW_ORB, FAST_ORB, ECL_ORB = 1.5, 1.2, 1.5

# Names that carry no sector keyword but are well-known (classifier gap fix).
SECTOR_OVERRIDE = {
    "MRNA": "pharma_biotech", "BNTX": "pharma_biotech", "NVAX": "pharma_biotech",
    "TSLA": "aerospace_aviation", "RIVN": "retail_consumer", "PLTR": "tech_software",
    "SNOW": "tech_software", "COIN": "crypto_digital", "HOOD": "banking_financial",
}
# Generic fallback rulers for unclassifiable names: identity/wealth/beauty core.
GENERIC_RULERS = [("Sun", "classical", "identity"), ("Jupiter", "contested", "wealth"),
                  ("Venus", "classical", "value")]

SLOW = [("Pluto", swe.PLUTO), ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE)]
NAT = [("Sun", swe.SUN), ("Moon", swe.MOON), ("Mercury", swe.MERCURY), ("Venus", swe.VENUS),
       ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN),
       ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE), ("Pluto", swe.PLUTO)]
GENERIC_TARGETS = ("Sun", "Venus", "Jupiter")   # money / growth / identity, always watched


def natal(date_str):
    jd, _, _ = exchange_open_jd(date_str)
    ch = {}
    for nm, pid in NAT:
        r = swe.calc_ut(jd, pid)
        ch[nm] = {"lon": r[0][0] % 360, "speed": r[0][3]}
    cusps, ascmc = swe.houses(jd, 40.7069, -74.0113, b"P")
    ch["ASC"] = {"lon": ascmc[0] % 360}
    ch["MC"] = {"lon": ascmc[1] % 360}
    # station flag reused from natal speeds (mean-speed thresholds)
    mean = {"Mercury": 1.2, "Venus": 1.0, "Mars": 0.5, "Jupiter": 0.08,
            "Saturn": 0.03, "Uranus": 0.01, "Neptune": 0.006, "Pluto": 0.004, "Sun": 1.0, "Moon": 13.0}
    for nm in mean:
        ch[nm]["station"] = abs(ch[nm]["speed"]) < mean[nm] * 0.2
    return ch


def natal_sector_load(ch, rulers):
    """How loaded the sector's ruling planets are in the natal chart."""
    load = 0.0
    detail = []
    for p, tier, _src in rulers:
        if p not in ch:
            continue
        lp = 0.0
        sign = int(ch[p]["lon"] // 30)
        why = []
        if sign in DOMICILE.get(p, []):
            lp += 1.0; why.append("domicile")
        elif sign in MODERN_DOMICILE.get(p, []):
            lp += 0.6; why.append("mod-dom")
        elif EXALTATION.get(p) == sign:
            lp += 0.6; why.append("exalt")
        ang = min(orb(ch[p]["lon"], ch["ASC"]["lon"]), orb(ch[p]["lon"], ch["MC"]["lon"]))
        if ang <= 8.0:
            lp += 1.0 * (8.0 - ang) / 8.0; why.append(f"ang{ang:.0f}")
        for lum in ("Sun", "Moon"):
            r = hard_asp(ch[p]["lon"], ch[lum]["lon"], 2.5)
            if r and p != lum:
                lp += 0.8 * (2.5 - r[1]) / 2.5; why.append(f"{r[0]}{lum}")
                break
        if ch[p].get("station"):
            lp += 0.5; why.append("station")
        contrib = lp * TIER_WEIGHT[tier]
        if contrib > 0.05:
            load += contrib
            detail.append(f"{p}({'+'.join(why)}){contrib:.1f}")
    return load, detail


def sky_samples():
    out = []
    d = START
    while d <= END:
        jd = swe.julday(d.year, d.month, d.day, 13.5)
        out.append((d, {nm: swe.calc_ut(jd, pid)[0][0] % 360 for nm, pid in SLOW + [("Jupiter", swe.JUPITER)]}))
        d += timedelta(days=STEP_DAYS)
    return out


def main():
    samples = sky_samples()
    events = json.loads(Path("/home/claude/forward_events.json").read_text())
    ecl = [(date.fromisoformat(e["date"]), e["lon"]) for e in events["eclipses"]
           if START.isoformat() < e["date"] <= END.isoformat()]
    print(f"samples={len(samples)} eclipses={len(ecl)}")

    ipos = load_ipos(None, "/home/claude/ritter_full.csv", [
        ("RUBI", "Rubicon Project", "2014-04-02"), ("EXA", "Exa Corp", "2012-06-28"),
        ("SLTN", "Solectron", "1989-11-15"), ("IMGN", "ImmunoGen", "1989-11-16"),
        ("CMLE", "Casual Male", "1988-09-20"), ("NRGN", "Neurogen", "1989-10-03"),
        ("LEND", "Accredited Home Lenders", "2003-02-14"),
    ])
    if len(ipos) < 100:
        raise SystemExit("ABORT universe collapsed")

    rows = []
    for ipo in ipos:
        try:
            ch = natal(ipo["date"])
        except Exception:
            continue
        sec = SECTOR_OVERRIDE.get(ipo["ticker"]) or classify_sector(ipo["name"])
        rulers = SECTOR_RULERS.get(sec, GENERIC_RULERS) if sec else GENERIC_RULERS
        sec_label = sec or "unclassified"

        load, load_detail = natal_sector_load(ch, rulers)
        fuel = 1.0 + min(load, 3.0)

        # targets = generic money axis + the sector's ruling planets (the sympathy channel)
        ruler_planets = [p for p, _, _ in rulers if p in ch]
        targets = list(dict.fromkeys(list(GENERIC_TARGETS) + ruler_planets))
        tgt_lons = {t: ch[t]["lon"] for t in targets}

        slow_active, fast_active = [], []
        for _d, pos in samples:
            s = set()
            for pn, _ in SLOW:
                for t, tl in tgt_lons.items():
                    if hard_asp(pos[pn], tl, SLOW_ORB):
                        s.add(f"{pn}>{t}")
            f = set()
            for t, tl in tgt_lons.items():
                if hard_asp(pos["Jupiter"], tl, FAST_ORB):
                    f.add(f"Jup>{t}")
            slow_active.append(s); fast_active.append(f)

        ecl_hits = defaultdict(list)
        for ed, elon in ecl:
            idx = min(range(len(samples)), key=lambda i: abs((samples[i][0] - ed).days))
            for t, tl in tgt_lons.items():
                r = hard_asp(elon, tl, ECL_ORB)
                if r:
                    ecl_hits[idx].append(f"{ed.isoformat()}:{r[0]}{t}")

        best = None
        for i in range(len(samples) - WINDOW_SAMPLES + 1):
            js = range(i, i + WINDOW_SAMPLES)
            ss = set().union(*(slow_active[j] for j in js))
            fs = set().union(*(fast_active[j] for j in js))
            es = [h for j in js for h in ecl_hits.get(j, [])]
            if not ss or not (fs or es):
                continue
            conv = len(ss) + len(fs) + len(es)
            score = conv * fuel
            if best is None or score > best[0]:
                center = samples[i + WINDOW_SAMPLES // 2][0]
                best = (score, conv, len(ss), len(fs) + len(es), center, "/".join(sorted(ss)),
                        "/".join(sorted(fs)), "/".join(es))
        if best is None:
            continue
        score, conv, n_slow, n_fast, center, ss, fs, es = best
        yr = int(ipo["date"][:4])
        rows.append({
            "ticker": ipo["ticker"], "name": ipo["name"].strip('"'), "date": ipo["date"],
            "sector": sec_label, "era": "2017+" if yr >= 2017 else ("2010-16" if yr >= 2010 else "pre-2010"),
            "setup_score": round(score, 2), "sector_load": round(load, 2), "fuel": round(fuel, 2),
            "convergence": conv, "n_slow": n_slow, "n_fast": n_fast,
            "peak_window": center.isoformat(),
            "position_by": (center - timedelta(days=42)).isoformat(),
            "loaded_rulers": "; ".join(load_detail),
            "slow_substrate": ss, "fast_trigger": fs, "eclipse_trigger": es,
        })

    rows.sort(key=lambda r: -r["setup_score"])
    out = Path("/mnt/user-data/outputs/sector_screener.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"Wrote {out} rows={len(rows)}")

    mi = next((i for i, r in enumerate(rows) if r["ticker"] == "MRNA"), None)
    if mi is not None:
        r = rows[mi]
        print(f"\nMRNA self-check: rank #{mi+1}/{len(rows)}  score={r['setup_score']} sector={r['sector']} "
              f"load={r['sector_load']} fuel={r['fuel']}  loaded: {r['loaded_rulers']}")

    print("\n=== TOP sector-loaded setups, 2017+ (tradeable), unique charts ===")
    seen = set(); n = 0
    for r in rows:
        if r["era"] != "2017+" or r["date"] in seen:
            continue
        seen.add(r["date"]); n += 1
        if n > 22:
            break
        print(f"  {r['ticker']:<7s}{r['name'][:22]:<22s}{r['date']} [{r['sector']:<18s}] score={r['setup_score']:5.1f} "
              f"load={r['sector_load']:.1f} peak={r['peak_window']} pos_by={r['position_by']}")
        print(f"          loaded: {r['loaded_rulers'] or '-'}  | {r['slow_substrate']} + {r['fast_trigger']}{'/ECL' if r['eclipse_trigger'] else ''}")

    # per-sector leaders
    print("\n=== Per-sector leader (any era) ===")
    bysec = {}
    for r in rows:
        if r["sector"] not in bysec:
            bysec[r["sector"]] = r
    for sec, r in sorted(bysec.items(), key=lambda kv: -kv[1]["setup_score"]):
        print(f"  {sec:<20s} {r['ticker']:<7s}{r['name'][:22]:<22s}{r['date']} score={r['setup_score']:5.1f} load={r['sector_load']:.1f} peak={r['peak_window']}")


if __name__ == "__main__":
    main()
