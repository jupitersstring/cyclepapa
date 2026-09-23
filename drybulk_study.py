"""
DRY BULK STUDY — sector rulers, historical-turn validation, forward windows.

Universe: US-listed dry bulk (and bulk-heavy mixed) names with Yahoo
first-trade dates used as the chart date. Recycled tickers (GOGL, EGLE,
GRIN now point at unrelated ETFs) are excluded.

1. Historical turns from weekly closes since listing:
     bottom = lowest close within +/-26 weeks AND price >= 2.0x within the
              next 104 weeks
     peak   = highest close within +/-26 weeks AND price <= 0.5x within the
              next 104 weeks
2. Timing test: at each turn month, percentile of the DRY_BULK key-in-lock
   score within that chart's own +/-24-month timeline (chance = 50%).
   Placebo: the same test with 30 random 4-planet ruler sets per chart —
   is the dry-bulk key more specific than an arbitrary key?
3. Forward (from Sep 2026): best 3-month key window, eclipse exit flags,
   Saturn/Jupiter eclipse reactivations, price context.
"""
import os, random, statistics as st
from datetime import datetime
import swisseph as swe
from bti_test import compute_natal, jd_of
from eclipse_database import build_eclipse_database
from keylock_screener import sector_loading, keylock_score, hard_orb, SLOW
from rulership_compendium import sector_rulers_for
from silas_rules import eclipse_reactivations, eclipse_exit_flag

UNIVERSE = [
    # ticker, chart date (Yahoo firstTradeDate), note
    ("SBLK", "2007-12-03", "Star Bulk — largest US-listed bulker (absorbed Eagle Bulk 2024)"),
    ("GNK",  "2014-07-15", "Genco — post-restructuring NYSE relisting (orig. IPO 2005-07-22)"),
    ("DSX",  "2005-03-23", "Diana Shipping"),
    ("SB",   "2008-05-30", "Safe Bulkers"),
    ("PANL", "2013-12-19", "Pangaea Logistics"),
    ("SHIP", "2008-01-30", "Seanergy — Capesize"),
    ("CTRM", "2019-02-11", "Castor Maritime"),
    ("EDRY", "2018-06-01", "EuroDry"),
    ("GLBS", "2008-03-11", "Globus Maritime"),
    ("NMM",  "2007-11-13", "Navios Partners — mixed dry bulk/container/tanker"),
    ("CMRE", "2010-11-04", "Costamare — containers + dry bulk platform"),
    ("HSHP", "2023-03-31", "Himalaya Shipping — pure Newcastlemax"),
    ("USEA", "2022-07-06", "United Maritime"),
    ("CISS", "2023-06-14", "C3is — dry bulk + tanker"),
    ("ICON", "2024-07-12", "Icon Energy"),
    ("CMBT", "2015-01-26", "CMB.TECH — now owns Golden Ocean (NYSE chart = Euronav listing)"),
    ("BDRY", "2018-03-22", "Breakwave Dry Bulk ETF — freight-futures proxy for the BDI"),
]
PLANETS = ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"]

def load(tk):
    rows = []
    for line in open(f"data/drybulk/{tk}.csv").readlines()[1:]:
        d, c = line.strip().split(",")
        rows.append((d, float(c)))
    return rows

def turns(rows):
    out = []
    n = len(rows)
    for i in range(26, n - 1):
        c = rows[i][1]
        win = [r[1] for r in rows[max(0, i-26): min(n, i+27)]]
        fut = [r[1] for r in rows[i+1: min(n, i+105)]]
        if not fut: continue
        if c == min(win) and max(fut) >= 2.0 * c:
            out.append(("bottom", rows[i][0]))
        elif c == max(win) and min(fut) <= 0.5 * c:
            out.append(("peak", rows[i][0]))
    return out

def month_key(natal, rulers, loaded, y, m):
    jd = jd_of(y, m, 15, 12.0)
    s = 0.0
    for tp, pid in SLOW.items():
        tl = swe.calc_ut(jd, pid)[0][0] % 360
        for rp in rulers:
            if rp not in natal: continue
            o = hard_orb(tl, natal[rp]["lon"])
            if o <= 2.5:
                lm = 2.0 if loaded.get(rp, 0) >= 1.0 else 1.5
                s += lm * (1 - o/2.5)
    return s

def pct_at(natal, rulers, loaded, y0, m0):
    scores = []
    for off in range(-24, 25):
        y = y0 + (m0 - 1 + off) // 12
        m = (m0 - 1 + off) % 12 + 1
        scores.append(month_key(natal, rulers, loaded, y, m))
    b = scores[24]
    return 100 * (sum(1 for s in scores if s < b) + 0.5*sum(1 for s in scores if s == b)) / len(scores)

def main():
    random.seed(7)
    edb = build_eclipse_database(2004, 2028)
    db_rulers = [p for p, t, w, s in sector_rulers_for("DRY_BULK", "modern")]
    real = {"bottom": [], "peak": []}
    placebo = {"bottom": [], "peak": []}
    turn_log = []
    fwd = []
    for tk, date, note in UNIVERSE:
        natal = compute_natal(date)
        ld, loaded, detail = sector_loading(natal, "DRY_BULK")
        rows = load(tk)
        for kind, d in turns(rows):
            y, m = int(d[:4]), int(d[5:7])
            if y < int(date[:4]) + 1: continue  # skip listing-year noise
            p = pct_at(natal, db_rulers, loaded, y, m)
            real[kind].append(p)
            pl = []
            for _ in range(30):
                rs = random.sample(PLANETS, 4)
                pl.append(pct_at(natal, rs, {}, y, m))
            placebo[kind].append(st.mean(pl))
            turn_log.append((tk, kind, d, p))
        # forward
        ks, peak, hits = keylock_score(natal, "DRY_BULK", edb, 2026, 9)
        exits = []
        reacts_j, reacts_s = [], []
        for k in range(0, 7):
            y = 2026 + (8 + k) // 12; m = (8 + k) % 12 + 1
            if eclipse_exit_flag(natal, edb, y, m): exits.append(f"{y}-{m:02d}")
            for r in eclipse_reactivations(natal, edb, y, m):
                (reacts_j if r["transiter"] == "Jupiter" else reacts_s if r["transiter"] == "Saturn" else []).append(f"{y}-{m:02d}")
        last = rows[-1][1]
        yr = [c for d_, c in rows if d_ >= "2025-09-22"]
        chg12 = (last / yr[0] - 1) * 100 if yr else None
        hi = max(c for _, c in rows)
        fwd.append(dict(tk=tk, note=note, load=ld, detail=detail, key=ks, peak=peak,
                        hits=hits, exits=sorted(set(exits)), rj=sorted(set(reacts_j)),
                        rs=sorted(set(reacts_s)), last=last, chg12=chg12,
                        fhi=(last/hi-1)*100))

    print("=" * 110)
    print("1. HISTORICAL TURNS — DRY_BULK key-in-lock percentile at the turn month (chance = 50%)")
    print("=" * 110)
    for kind in ("bottom", "peak"):
        r, p = real[kind], placebo[kind]
        if len(r) < 3: continue
        se = st.stdev(r) / len(r)**0.5
        diff = [a - b for a, b in zip(r, p)]
        sed = st.stdev(diff) / len(diff)**0.5
        print(f"  {kind.upper():<7s} n={len(r):3d}  dry-bulk key {st.mean(r):5.1f}% (t vs 50 = {(st.mean(r)-50)/se:+.2f})"
              f"  | random-key placebo {st.mean(p):5.1f}%  | specificity {st.mean(diff):+5.1f}pp (t={st.mean(diff)/sed:+.2f})")
    print("\n  Turn log (ticker, type, week, key percentile):")
    for tk, kind, d, p in sorted(turn_log, key=lambda x: x[2]):
        print(f"    {d}  {tk:<5s} {kind:<6s} {p:5.1f}%")

    print("\n" + "=" * 110)
    print("2. FORWARD (from Sep 2026) — DRY_BULK lock, key window, Silas eclipse flags")
    print("=" * 110)
    fwd.sort(key=lambda r: -(r["key"] + 0.6*r["load"]))
    for r in fwd:
        c12 = f"{r['chg12']:+.0f}%" if r["chg12"] is not None else "n/a"
        print(f"  {r['tk']:<5s} last {r['last']:7.2f}  12mo {c12:>6s}  fromHi {r['fhi']:+5.0f}%  "
              f"lock {r['load']:.1f}  key {r['key']:5.1f}  peak-window {r['peak']}")
        print(f"        lock: {'; '.join(r['detail']) or '-'}")
        print(f"        window hits: {', '.join(r['hits'][:6]) or '-'}")
        print(f"        eclipse EXIT flags: {', '.join(r['exits']) or '-'} | Jupiter reactivation: "
              f"{', '.join(r['rj']) or '-'} | Saturn reactivation: {', '.join(r['rs']) or '-'}")
        print(f"        ({r['note']})")

if __name__ == "__main__":
    main()
