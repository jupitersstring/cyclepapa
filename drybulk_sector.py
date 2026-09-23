"""
DRY BULK — SECTOR-LEVEL STUDY (the cycle is common to all bulkers, so
single-chart timing is the wrong unit; see drybulk_study.py result).

1. Sector index = chained MEDIAN weekly log-return across core bulkers
   (robust to one name's dilution drift). Cycle turns on the index:
     bottom = lowest within +/-26 wks and >= 1.6x within the next 104 wks
     peak   = highest within +/-26 wks and <= 0.6x within the next 104 wks
   (thresholds fixed before looking at the result; index is less volatile
   than single names, hence 1.6x/0.6x rather than 2x/0.5x)
2. TEST A — sector charts: DRY_BULK key-in-lock percentile at the index
   turns for the Baltic Dry Index chart (1999-11-01) and the Baltic
   Freight Index chart (1985-01-04), both 13:00 London. Significance by
   permutation against 300 random charts (same turns, same rulers).
3. TEST B — one pre-specified mundane hypothesis from the compendium's
   rulers (Moon/Neptune = the sea): Jupiter in a WATER sign (Cancer,
   Scorpio, Pisces) -> dry bulk equities outperform. Monthly returns,
   significance by circular-shift permutation (keeps autocorrelation).
4. Where we are now + forward windows; name table with the small-cap
   lens (cult tags, beta to the sector, dilution flag).
"""
import math, random, statistics as st
from datetime import datetime
import swisseph as swe
from bti_test import compute_natal, jd_of
from bti_v19_empirical import closest_hard
from eclipse_database import build_eclipse_database
from keylock_screener import sector_loading, keylock_score, hard_orb, c_orb, SLOW
from rulership_compendium import sector_rulers_for
from silas_rules import eclipse_reactivations, eclipse_exit_flag

INDEX_NAMES = ["DSX","SBLK","SB","SHIP","GLBS","GNK","PANL","EDRY","CTRM","USEA","HSHP","ICON"]
NAMES = [  # ticker, chart date (Yahoo firstTradeDate), segment/note
    ("SBLK","2007-12-03","large-cap, Capesize-heavy; absorbed Eagle Bulk 2024"),
    ("GNK", "2014-07-15","mid-cap; post-restructuring relisting chart"),
    ("DSX", "2005-03-23","Diana; time-charter model"),
    ("SB",  "2008-05-30","Safe Bulkers"),
    ("PANL","2013-12-19","Pangaea; logistics/ice-class"),
    ("HSHP","2023-03-31","Himalaya; pure Newcastlemax, index-linked"),
    ("NMM", "2007-11-13","Navios Partners; mixed fleet"),
    ("CMRE","2010-11-04","Costamare; containers + dry bulk"),
    ("CMBT","2015-01-26","CMB.TECH; owns Golden Ocean since 2025"),
    ("EDRY","2018-06-01","EuroDry; small-cap"),
    ("SHIP","2008-01-30","Seanergy; Capesize small-cap"),
    ("USEA","2022-07-06","United Maritime; micro-cap"),
    ("GLBS","2008-03-11","Globus; micro-cap"),
    ("CTRM","2019-02-11","Castor; micro-cap holding co"),
    ("ICON","2024-07-12","Icon Energy; micro-cap"),
    ("CISS","2023-06-14","C3is; micro-cap, dry bulk + tanker"),
    ("IMPP","2021-12-06","Imperial Petroleum; tankers + bulkers"),
    ("PXS", "2015-11-04","Pyxis; tankers + dry bulk"),
    ("BDRY","2018-03-22","Breakwave ETF; freight futures (BDI proxy)"),
]
PLANETS = ["Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto"]
WATER = {3, 7, 11}
SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

def load(tk):
    out = {}
    for line in open(f"data/drybulk/{tk}.csv").readlines()[1:]:
        d, c = line.strip().split(",")
        c = float(c)
        if c > 0: out[d] = c
    return out

def london_chart(date, hr=13.0):
    n = compute_natal(date, hr=hr)
    _, ascmc = swe.houses(n["_jd"], 51.5136, -0.0813, b'P')
    n["ASC"] = {"lon": ascmc[0] % 360, "sign": int((ascmc[0] % 360)//30)}
    n["MC"] = {"lon": ascmc[1] % 360, "sign": int((ascmc[1] % 360)//30)}
    return n

_LON = {}
def slow_lons(y, m):
    if (y, m) not in _LON:
        jd = jd_of(y, m, 15, 12.0)
        _LON[(y, m)] = {p: swe.calc_ut(jd, pid)[0][0] % 360 for p, pid in SLOW.items()}
    return _LON[(y, m)]

def month_key(natal, rulers, loaded, y, m):
    s = 0.0
    for tp, tl in slow_lons(y, m).items():
        for rp in rulers:
            o = hard_orb(tl, natal[rp]["lon"])
            if o <= 2.5:
                s += (2.0 if loaded.get(rp, 0) >= 1.0 else 1.5) * (1 - o/2.5)
    return s

def pct_at(natal, rulers, loaded, y0, m0):
    sc = []
    for off in range(-24, 25):
        y = y0 + (m0 - 1 + off)//12; m = (m0 - 1 + off) % 12 + 1
        sc.append(month_key(natal, rulers, loaded, y, m))
    b = sc[24]
    return 100*(sum(1 for s in sc if s < b) + 0.5*sum(1 for s in sc if s == b))/len(sc)

def a_orb(a, b, t):
    d = (a - b) % 360
    return min(abs(d - t), abs(d - (360 - t)))

def cult_tags(natal, age, edb):
    sun, nep, ura, plu = (natal[p]["lon"] for p in ("Sun","Neptune","Uranus","Pluto"))
    moon = natal["Moon"]["lon"]
    tags, sc = [], 0.0
    def add(t, w): tags.append(t); return w
    if a_orb(ura, plu, 51.43) <= 3: sc += add("UrPl-sept", 2.0)
    if a_orb(ura, plu, 60.0) <= 3:  sc += add("UrPl-sxt", 1.5)
    if a_orb(nep, plu, 60.0) <= 3:  sc += add("NePl-sxt", 1.5)
    if c_orb(sun, nep) <= 5:        sc += add("AVIS", 2.0)
    if min(closest_hard(natal[p]["lon"], 267.0) for p in ("Jupiter","Saturn","Uranus","Neptune","Pluto")) <= 3:
        sc += add("GC", 1.5)
    pos = [natal[p]["lon"] for p in ("Sun","Moon","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto")]
    if max(sum(1 for q in pos if c_orb(q, p0) <= 15) for p0 in pos) >= 4: sc += add("Stell", 1.0)
    now = slow_lons(2026, 9)
    jd = jd_of(2026, 9, 15, 12.0)
    tplu = swe.calc_ut(jd, swe.PLUTO)[0][0] % 360
    tnep = swe.calc_ut(jd, swe.NEPTUNE)[0][0] % 360
    if min(closest_hard(tplu, sun), closest_hard(tplu, moon)) <= 3: sc += add("tPlu-light", 2.0)
    if min(closest_hard(tnep, sun), closest_hard(tnep, moon)) <= 3: sc += add("tNep-light", 2.0)
    jups = []
    for k in range(7):
        y = 2026 + (8 + k)//12; m = (8 + k) % 12 + 1
        jups.append(slow_lons(y, m)["Jupiter"])
    if min(c_orb(j, nep) for j in jups) <= 3: sc += add("Gidel-JupNep", 2.0)
    if age <= 5: sc += add("young", 1.0)
    for k in range(7):
        y = 2026 + (8 + k)//12; m = (8 + k) % 12 + 1
        if any(r["transiter"] == "Jupiter" for r in eclipse_reactivations(natal, edb, y, m)):
            sc += add("Silas-JupReact", 1.5); break
    return sc, tags

def main():
    random.seed(11)
    edb = build_eclipse_database(1999, 2029)
    rulers = [p for p, t, w, s in sector_rulers_for("DRY_BULK", "modern")]

    # ---------------- 1. sector index ----------------
    series = {tk: load(tk) for tk in INDEX_NAMES}
    dates = sorted(set(d for s in series.values() for d in s))
    idx, level, idx_dates = [], 100.0, []
    for d0, d1 in zip(dates, dates[1:]):
        rets = [math.log(s[d1]/s[d0]) for s in series.values() if d0 in s and d1 in s]
        if len(rets) < 3:
            continue
        level *= math.exp(st.median(rets))
        idx.append(level); idx_dates.append(d1)
    turns = []
    n = len(idx)
    for i in range(26, n - 1):
        win = idx[max(0, i-26): i+27]; fut = idx[i+1: i+105]
        if not fut: continue
        if idx[i] == min(win) and max(fut) >= 1.6*idx[i]: turns.append(("bottom", idx_dates[i]))
        elif idx[i] == max(win) and min(fut) <= 0.6*idx[i]: turns.append(("peak", idx_dates[i]))
    print("=" * 108)
    print(f"1. DRY BULK SECTOR INDEX (median weekly log-return of {len(INDEX_NAMES)} bulkers), {idx_dates[0]} -> {idx_dates[-1]}")
    print("=" * 108)
    for k, d in turns:
        i = idx_dates.index(d)
        print(f"   {d}  {k:<6s} index {idx[i]:8.1f}")
    last = idx[-1]
    i52 = max(0, n - 53)
    hi104 = max(idx[-105:]); lo104 = min(idx[-105:])
    print(f"   NOW {idx_dates[-1]}: 12mo {100*(last/idx[i52]-1):+.0f}% | position in 2-yr range "
          f"{100*(last-lo104)/(hi104-lo104):.0f}% | vs last cycle peak {100*(last/max(idx[-260:])-1):+.0f}%")

    # ---------------- 2. TEST A: sector charts ----------------
    print("\n" + "=" * 108)
    print("2. TEST A — do the Baltic index charts time the sector's cycle turns? (key-in-lock percentile, chance 50%)")
    print("=" * 108)
    tmonths = [(k, int(d[:4]), int(d[5:7])) for k, d in turns]
    def mean_pct(chart):
        _, loaded, _ = sector_loading(chart, "DRY_BULK")
        return st.mean(pct_at(chart, rulers, loaded, y, m) for _, y, m in tmonths), loaded
    rand = []
    for _ in range(300):
        y = random.randint(1950, 2015); doy = random.randint(0, 364)
        d = datetime.fromordinal(datetime(y, 1, 1).toordinal() + doy).strftime("%Y-%m-%d")
        rand.append(mean_pct(london_chart(d))[0])
    charts = {}
    for label, date in [("BDI (1999-11-01)", "1999-11-01"), ("BFI (1985-01-04)", "1985-01-04")]:
        ch = london_chart(date); charts[label] = ch
        mp, loaded = mean_pct(ch)
        _, _, det = sector_loading(ch, "DRY_BULK")
        p = (1 + sum(1 for r in rand if r >= mp)) / (1 + len(rand))
        per = ", ".join(f"{k[0].upper()}{y}-{m:02d}:{pct_at(ch, rulers, loaded, y, m):.0f}" for k, y, m in tmonths)
        print(f"   {label}: mean {mp:5.1f}%  permutation p={p:.3f}  (random charts: mean {st.mean(rand):.1f}%, "
              f"95th pct {sorted(rand)[int(0.95*len(rand))]:.1f}%)")
        print(f"      lock: {'; '.join(det) or '-'}")
        print(f"      per turn: {per}")

    # ---------------- 3. TEST B: Jupiter in water signs ----------------
    print("\n" + "=" * 108)
    print("3. TEST B — Jupiter in a WATER sign (Cancer/Scorpio/Pisces) -> dry bulk outperforms? (monthly)")
    print("=" * 108)
    month_end = {}
    for d, v in zip(idx_dates, idx):
        month_end[d[:7]] = v
    months = sorted(month_end)
    rets, jsign = [], []
    for m0, m1 in zip(months, months[1:]):
        rets.append(math.log(month_end[m1]/month_end[m0]))
        y, m = int(m1[:4]), int(m1[5:7])
        jsign.append(int(slow_lons(y, m)["Jupiter"]//30))
    N = len(rets)
    def diff(r):
        w = [x for x, s in zip(r, jsign) if s in WATER]
        o = [x for x, s in zip(r, jsign) if s not in WATER]
        return st.mean(w) - st.mean(o), len(w), len(o)
    obs, nw, no = diff(rets)
    shifts = [diff(rets[k:] + rets[:k])[0] for k in range(12, N - 12)]
    p = (1 + sum(1 for s in shifts if s >= obs)) / (1 + len(shifts))
    print(f"   months: water {nw}, other {no} | mean monthly return water {100*(obs + st.mean([x for x,s in zip(rets,jsign) if s not in WATER])):+.2f}% "
          f"vs other {100*st.mean([x for x,s in zip(rets,jsign) if s not in WATER]):+.2f}%")
    print(f"   difference {100*obs:+.2f}%/month  circular-shift permutation p={p:.3f} (one-sided, {len(shifts)} shifts)")
    print("   by Jupiter sign (descriptive only):")
    for s in range(12):
        xs = [x for x, j in zip(rets, jsign) if j == s]
        if xs:
            print(f"     {SIGNS[s]}: n={len(xs):3d}  mean {100*st.mean(xs):+6.2f}%/mo  cum {100*(math.exp(sum(xs))-1):+7.0f}%")
    print("   Jupiter ingresses ahead:")
    prev = None
    for k in range(0, 60):
        y = 2026 + (8 + k)//12; m = (8 + k) % 12 + 1
        s = int(slow_lons(y, m)["Jupiter"]//30)
        if s != prev:
            print(f"     {y}-{m:02d}: Jupiter in {SIGNS[s]}{'  <- WATER' if s in WATER else ''}")
            prev = s

    # ---------------- 4. forward: sector charts ----------------
    print("\n" + "=" * 108)
    print("4. FORWARD — sector charts from Sep 2026")
    print("=" * 108)
    for label, ch in charts.items():
        ks, peak, hits = keylock_score(ch, "DRY_BULK", edb, 2026, 9)
        ex, rj, rs = [], [], []
        for k in range(0, 13):
            y = 2026 + (8 + k)//12; m = (8 + k) % 12 + 1
            if eclipse_exit_flag(ch, edb, y, m): ex.append(f"{y}-{m:02d}")
            for r in eclipse_reactivations(ch, edb, y, m):
                if r["transiter"] == "Jupiter": rj.append(f"{y}-{m:02d}")
                if r["transiter"] == "Saturn": rs.append(f"{y}-{m:02d}")
        print(f"   {label}: key window {peak} (score {ks:.1f}) hits {', '.join(hits[:6]) or '-'}")
        print(f"      eclipse exit flags {sorted(set(ex)) or '-'} | Jupiter react {sorted(set(rj)) or '-'} | Saturn react {sorted(set(rs)) or '-'}")

    # ---------------- 5. names: small-cap lens ----------------
    print("\n" + "=" * 108)
    print("5. NAMES — lock/key window, cult tags, beta to sector (104 wks), dilution flag")
    print("=" * 108)
    idx_map = dict(zip(idx_dates, idx))
    rows = []
    for tk, date, note in NAMES:
        s = load(tk)
        natal = compute_natal(date)
        ld, _, det = sector_loading(natal, "DRY_BULK")
        ks, peak, hits = keylock_score(natal, "DRY_BULK", edb, 2026, 9)
        cs, tags = cult_tags(natal, 2026 - int(date[:4]), edb)
        ds = sorted(d for d in s if d in idx_map)[-105:]
        xs = [math.log(idx_map[b]/idx_map[a]) for a, b in zip(ds, ds[1:])]
        ys = [math.log(s[b]/s[a]) for a, b in zip(ds, ds[1:])]
        beta = None
        if len(xs) > 30:
            mx, my = st.mean(xs), st.mean(ys)
            vx = sum((x-mx)**2 for x in xs)
            beta = sum((x-mx)*(y-my) for x, y in zip(xs, ys))/vx if vx else None
        dts = sorted(s); lastp = s[dts[-1]]
        yr = [d for d in dts if d >= "2025-09-22"]
        chg12 = 100*(lastp/s[yr[0]]-1) if yr else None
        q = [d for d in dts if d >= "2026-06-22"]
        chg13w = 100*(lastp/s[q[0]]-1) if q else None
        fhi = 100*(lastp/max(s.values())-1)
        dil = "CHRONIC DILUTER" if fhi <= -95 else ""
        ex = []
        for k in range(0, 7):
            y = 2026 + (8 + k)//12; m = (8 + k) % 12 + 1
            if eclipse_exit_flag(natal, edb, y, m): ex.append(f"{y}-{m:02d}")
        rows.append(dict(tk=tk, note=note, last=lastp, chg12=chg12, chg13w=chg13w, fhi=fhi, dil=dil,
                         beta=beta, load=ld, det=det, key=ks, peak=peak, cult=cs, tags=tags, ex=sorted(set(ex))))
    rows.sort(key=lambda r: -(r["key"] + 0.6*r["load"] + 0.5*r["cult"]))
    print(f"   {'Tkr':<5s} {'last':>7s} {'12mo':>6s} {'13wk':>6s} {'fromHi':>7s} {'beta':>5s} {'lock':>5s} {'key':>5s} {'window':<8s} {'cult':>4s}  tags | eclipse exits | flags")
    for r in rows:
        f = lambda v: f"{v:+.0f}%" if v is not None else "n/a"
        b = f"{r['beta']:.2f}" if r["beta"] is not None else "n/a"
        print(f"   {r['tk']:<5s} {r['last']:7.2f} {f(r['chg12']):>6s} {f(r['chg13w']):>6s} {r['fhi']:+6.0f}% {b:>5s} "
              f"{r['load']:5.1f} {r['key']:5.1f} {r['peak']:<8s} {r['cult']:4.1f}  {','.join(r['tags']) or '-'} | "
              f"{','.join(r['ex']) or '-'} | {r['dil']}")
    with open("data/drybulk_names.csv", "w") as fo:
        fo.write("ticker,note,last,chg12,chg13w,from_high,beta,lock,key,key_window,cult,tags,eclipse_exits,dilution_flag\n")
        for r in rows:
            fo.write(f"{r['tk']},{r['note'].replace(',',';')},{r['last']:.2f},{r['chg12'] or ''},{r['chg13w'] or ''},"
                     f"{r['fhi']:.1f},{r['beta'] or ''},{r['load']:.2f},{r['key']:.2f},{r['peak']},{r['cult']:.1f},"
                     f"{'|'.join(r['tags'])},{'|'.join(r['ex'])},{r['dil']}\n")
    print("\n   exported -> data/drybulk_names.csv")

if __name__ == "__main__":
    main()
