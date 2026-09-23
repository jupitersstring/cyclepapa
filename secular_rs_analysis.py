"""
Secular RS-low analysis + RS-HIGH differentiator.

(A) SECULAR RS-LOW: for stocks that rallied hundreds of % against SPX,
    find the ALL-TIME (or multi-year) lowest RS-vs-SPX point in their
    history and compute astro signature at that point. Tests whether
    the canonical eclipse/age/Neptune signal holds at true generational
    lows (not just 52-week lows).

(B) RS-HIGH DIFFERENTIATOR: for stocks currently at RS-highs, distinguish
    CONTINUATION (more rally ahead) from TOPPING (peak reached).
    Signals:
      CONTINUATION: Jupiter still supportive; burn not maxed;
        progressed phase waxing; no Saturn approaching natal sensitive
      TOPPING: Saturn arriving at natal Sun/Nep; progressed full/gibbous;
        high burn; NN in peak_zone; Uranus hard aspect to natal forming
"""
import json, csv, sys, time, subprocess
from datetime import datetime, timezone
from collections import defaultdict
import statistics as st
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx, gamma_survive, gamma_era
from classical_archetype import classical_classify
from classical_extensions import secondary_progressions, progressed_lunation_phase
from eclipse_database import build_eclipse_database
from bti_v17_bottomcatch import score_v17_bottom_catch
from yf_fetcher import fetch_prices, rs_series

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, max_orb=10):
    best = None
    for asp in (0, 90, 180):
        for sign in (+1, -1):
            o = orb(a, b + sign * asp)
            if o <= max_orb and (best is None or o < best[1]):
                best = (asp, o)
    return best

# Big-multiple runup corpus (rallied hundreds-of-% vs SPX)
BIG_MULTIPLE_RUNUPS = [
    # ticker, IPO_date, approx mega-runup peak, multiple, note
    ("GME",    "2002-02-13", 2021,  160, "160x Jan 2021 squeeze"),
    ("AMC",    "2013-12-18", 2021,  31,  "31x Jun 2021"),
    ("BBBY",   "1992-06-04", 2022,  5,   "5x Aug 2022"),
    ("CVNA",   "2017-04-28", 2024,  75,  "75x 2022-24"),
    ("CELH",   "2006-07-18", 2022,  100, "100x 2020-22"),
    ("MARA",   "2017-08-18", 2021,  70,  "70x 2020-21"),
    ("RIOT",   "2003-12-01", 2021,  94,  "94x 2020-21"),
    ("PLUG",   "1999-09-29", 2021,  25,  "25x 2020-21"),
    ("NVDA",   "1999-01-22", 2024,  13,  "13x 2022-24"),
    ("PLTR",   "2020-09-30", 2024,  13,  "13x 2022-24"),
    ("APP",    "2021-04-15", 2024,  40,  "40x 2022-24"),
    ("SMCI",   "2007-03-29", 2024,  17,  "17x 2022-24"),
    ("MSTR",   "1998-06-11", 2024,  4,   "4x+BTC leverage"),
    ("COIN",   "2021-04-14", 2024,  10,  "10x 2023-24"),
    ("HIMS",   "2021-01-21", 2025,  12,  "12x 2023-25"),
    ("IONQ",   "2021-10-01", 2025,  16,  "16x 2023-25"),
    ("RKLB",   "2021-08-25", 2024,  7,   "7x 2023-24"),
    ("VST",    "2016-10-10", 2024,  9,   "9x 2023-24"),
    ("CEG",    "2022-02-02", 2024,  4,   "4x 2022-24"),
    ("SMR",    "2022-05-03", 2024,  15,  "15x 2023-24"),
    ("SOUN",   "2022-04-28", 2024,  15,  "15x 2023-24"),
    ("RGTI",   "2022-03-02", 2025,  30,  "30x 2022-25"),
    ("QBTS",   "2022-08-08", 2025,  20,  "20x 2022-25"),
    ("TLRY",   "2018-07-19", 2018,  18,  "18x at IPO"),
    ("RDDT",   "2024-03-21", 2025,  7,   "7x 2024-25"),
    ("HOOD",   "2021-07-29", 2025,  10,  "10x 2022-25"),
    ("DUOL",   "2021-07-28", 2024,  5,   "5x 2022-24 prior"),
    ("NNE",    "2024-05-01", 2024,  6,   "6x post-IPO"),
    ("DJT",    "2024-03-26", 2024,  2,   "IPO spike"),
    ("RDDT",   "2024-03-21", 2025,  7,   "duplicate — remove below"),
]

# Stocks currently at RS-HIGH (from Part B of prior run)
RS_HIGH_CURRENT = [
    ("NVDA","1999-01-22"), ("GOOG","2004-08-19"), ("GOOGL","2006-04-03"),
    ("EQIX","2000-08-10"), ("CMI","1964-12-01"), ("CF","2005-08-10"),
    ("BG","2001-08-02"), ("CVX","2001-10-09"), ("INGM","2024-10-24"),
    ("ALAB","2024-03-20"), ("ARM","2023-09-14"), ("NTRS","1998-01-30"),
    ("GEV","2024-04-02"), ("AMAL","2018-08-09"), ("HUBB","2023-10-18"),
    ("MRNA","2018-12-07"), ("PH","1964-07-01"), ("TER","2020-09-21"),
    ("RL","1995-07-26"), ("MA","2006-05-25"), ("COST","1985-12-05"),
    ("META","2012-05-18"), ("AVGO","2009-08-06"), ("NOW","2012-06-29"),
    ("CRWD","2019-06-12"), ("PANW","2012-07-19"), ("ANET","2014-06-06"),
    ("CRM","2004-06-23"),
]

def differentiate_rs_high(natal, eval_y, eval_m, ipo_date, spx):
    """For a stock at RS-high, is it CONTINUATION or TOPPING?"""
    trans = transits_at(eval_y, eval_m)
    cls = classical_classify(natal)
    ipo_y = int(ipo_date[:4])
    age = eval_y - ipo_y

    # (1) Jupiter concurrent support to natal
    jup_lon = trans["Jupiter"]["lon"]
    jup_supports = 0
    for target in ("Sun","Moon","Venus","ASC","MC","Jupiter"):
        if target not in natal: continue
        for asp in (0, 60, 120):
            for sign in (+1, -1):
                if orb(jup_lon, natal[target]["lon"] + sign*asp) <= 3:
                    jup_supports += 1; break

    # (2) Saturn approaching natal Sun/Moon/Nep within next 6mo
    sat_lon = trans["Saturn"]["lon"]
    saturn_approach = 0
    for target in ("Sun","Moon","Neptune","Venus","MC"):
        if target not in natal: continue
        o = min(orb(sat_lon, natal[target]["lon"]),
                orb(sat_lon, (natal[target]["lon"]+180)%360),
                orb(sat_lon, (natal[target]["lon"]+90)%360),
                orb(sat_lon, (natal[target]["lon"]-90)%360))
        if o <= 5: saturn_approach += (5-o)/5

    # (3) Uranus hard aspect to natal Sun/MC (shock/reversal)
    ura_lon = trans["Uranus"]["lon"]
    uranus_hard = 0
    for target in ("Sun","MC","Moon"):
        if target not in natal: continue
        r = closest_hard(ura_lon, natal[target]["lon"], 4)
        if r: uranus_hard += (4-r[1])/4

    # (4) Progressed lunation phase
    try:
        prog, age_yrs = secondary_progressions(ipo_date, f"{eval_y:04d}-{eval_m:02d}-15")
        prog_phase = progressed_lunation_phase(prog)
    except:
        prog_phase = "unknown"

    # (5) NN category
    nn_cat = cls["nn_category"]

    # Composite:
    #   CONTINUATION = jupiter_supports + waxing prog + nn non-peak
    #   TOPPING = saturn_approach + uranus_hard + prog full/gibbous + nn peak
    cont_score = jup_supports * 0.8
    if prog_phase in ("prog_new","prog_crescent","prog_first_q"):
        cont_score += 1.5
    elif prog_phase in ("prog_gibbous",):
        cont_score += 0.5
    if nn_cat in ("bottom_zone","setup_zone","launch_zone"):
        cont_score += 0.8

    top_score = saturn_approach * 1.2 + uranus_hard * 1.0
    if prog_phase in ("prog_full","prog_disseminating"):
        top_score += 1.5
    elif prog_phase == "prog_last_q":
        top_score += 0.8
    if nn_cat == "peak_zone":
        top_score += 1.0
    if age >= 25 and nn_cat != "setup_zone":
        top_score += 0.4

    net = cont_score - top_score
    if net >= 1.5: tag = "CONTINUATION"
    elif net >= 0.3: tag = "MILD_CONTINUATION"
    elif net >= -0.3: tag = "NEUTRAL_HIGH"
    elif net >= -1.5: tag = "MILD_TOPPING"
    else: tag = "TOPPING"

    return {
        "tag": tag, "continuation_score": cont_score, "topping_score": top_score,
        "net": net, "jup_supports": jup_supports, "saturn_approach": saturn_approach,
        "uranus_hard": uranus_hard, "prog_phase": prog_phase, "nn_cat": nn_cat,
    }

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses", file=sys.stderr)

    spx = fetch_prices("SPY", 1993)  # Go further back to capture older history
    print(f"  SPY {len(spx)} days from {spx[0][0]}", file=sys.stderr)

    # =====================================================
    # (A) SECULAR RS-LOW analysis
    # =====================================================
    print(f"\n{'='*180}")
    print(f"SECULAR RS-LOW — absolute lowest RS-vs-SPX point in each stock's history")
    print(f"{'='*180}")
    print(f"{'Tkr':<6s} {'IPO':<11s} {'PeakYr':>4s} {'Mult':>4s} {'RSlowDate':<12s} {'Drawdown':>8s} {'BtmScr':>6s} {'Ecl':>4s} {'Tight':>5s} {'Age_b':>5s} {'Nep':>4s} {'Tag':<20s}")
    secular_results = []
    seen = set()
    for tk, ipo, peak_yr, mult, note in BIG_MULTIPLE_RUNUPS:
        if tk in seen: continue
        seen.add(tk)
        stock = fetch_prices(tk, max(1993, int(ipo[:4])))
        time.sleep(0.1)
        if not stock or len(stock) < 100:
            print(f"  {tk:<6s} INSUFFICIENT_DATA")
            continue
        rs = rs_series(stock, spx)
        if not rs:
            print(f"  {tk:<6s} NO_RS")
            continue
        # ALL-TIME RS low up through 2025
        filt = [(d, r) for (d, r) in rs if d <= "2025-12-31"]
        if not filt: continue
        min_r = min(r for (d, r) in filt)
        low_date = [d for (d, r) in filt if r == min_r][0]
        # Drawdown: first RS value vs RS low
        first_r = rs[0][1]
        drawdown = (min_r / first_r - 1) * 100

        low_y, low_m = int(low_date[:4]), int(low_date[5:7])
        try:
            natal = compute_natal(ipo)
            r = score_v17_bottom_catch(natal, low_y, low_m, ipo, db)
            secular_results.append({
                "tk": tk, "ipo": ipo, "peak_yr": peak_yr, "mult": mult,
                "rs_low_date": low_date, "drawdown": drawdown,
                "astro": r,
            })
            print(f"{tk:<6s} {ipo:<11s} {peak_yr:>4d} {mult:>3d}× {low_date:<12s} {drawdown:+7.0f}% {r['bottom_score']:6.2f} {r['p1_eclipse']:4.1f} {r['p1_tight_hits']:>5d} {r['p2_age']:5.1f} {r['p3_neptune']:4.1f} {r['tag']:<20s}")
        except Exception as e:
            pass

    # Stats
    if secular_results:
        scores = [r["astro"]["bottom_score"] for r in secular_results]
        print(f"\n  Secular RS-low astro stats (n={len(secular_results)}):")
        print(f"    Mean={st.mean(scores):.2f}  Median={st.median(scores):.2f}")
        print(f"    %≥5: {100*sum(1 for s in scores if s>=5)/len(scores):.0f}%")
        print(f"    %≥3: {100*sum(1 for s in scores if s>=3)/len(scores):.0f}%")
        # Drawdown distribution
        dds = [r["drawdown"] for r in secular_results]
        print(f"    Drawdown distribution: median={st.median(dds):.0f}%  min={min(dds):.0f}%")
        # Eclipse hit rate
        ecl = sum(1 for r in secular_results if r["astro"]["p1_eclipse"] > 0)
        print(f"    Had ANY eclipse hit at secular low: {100*ecl/len(secular_results):.0f}%")
        tight = sum(1 for r in secular_results if r["astro"]["p1_tight_hits"] > 0)
        print(f"    Had TIGHT (<1°) eclipse hit: {100*tight/len(secular_results):.0f}%")

    # =====================================================
    # (B) RS-HIGH differentiator
    # =====================================================
    print(f"\n{'='*175}")
    print(f"RS-HIGH DIFFERENTIATOR — CONTINUATION vs TOPPING for stocks already at RS-highs")
    print(f"{'='*175}")
    print(f"{'Tkr':<7s} {'IPO':<11s} {'Age':>3s} {'RSrank':>6s} {'%fromHi':>7s} {'Tag':<20s} {'Net':>5s} {'Cont':>4s} {'Top':>4s} {'JupSup':>6s} {'SatApp':>6s} {'UraHrd':>6s} {'ProgPh':<14s} {'NN':<11s}")
    rs_high_results = []
    for tk, ipo in RS_HIGH_CURRENT:
        stock = fetch_prices(tk, 2018)
        time.sleep(0.1)
        if not stock: continue
        rs = rs_series(stock, spx)
        if not rs: continue
        from yf_fetcher import compute_current_rs_status
        status = compute_current_rs_status(rs)
        if not status: continue
        try:
            natal = compute_natal(ipo)
            diff = differentiate_rs_high(natal, 2026, 4, ipo, spx)
            rs_high_results.append((tk, ipo, status, diff))
            print(f"{tk:<7s} {ipo:<11s} {2026-int(ipo[:4]):>3d} {status['pct_rank']:5.0f}% {status['pct_from_high']:+6.0f}% {diff['tag']:<20s} {diff['net']:+5.2f} {diff['continuation_score']:4.2f} {diff['topping_score']:4.2f} {diff['jup_supports']:>6d} {diff['saturn_approach']:6.2f} {diff['uranus_hard']:6.2f} {diff['prog_phase']:<14s} {diff['nn_cat'][:11]:<11s}")
        except: pass

    # Summary of RS-HIGH differentiator
    print(f"\n{'='*100}")
    print(f"RS-HIGH CLASSIFICATION SUMMARY")
    print(f"{'='*100}")
    by_tag = defaultdict(list)
    for tk, ipo, status, diff in rs_high_results:
        by_tag[diff["tag"]].append(tk)
    for tag in ("CONTINUATION","MILD_CONTINUATION","NEUTRAL_HIGH","MILD_TOPPING","TOPPING"):
        names = by_tag.get(tag, [])
        print(f"  {tag:<20s}  n={len(names):2d}  {', '.join(names)}")

    # Export
    with open("/home/user/cyclepapa/data/secular_rs_lows.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","ipo","peak_yr","mult","rs_low_date","drawdown_pct",
                    "bottom_score","p1_eclipse","p1_tight_hits","age","p3_neptune","tag"])
        for r in secular_results:
            a = r["astro"]
            w.writerow([r["tk"],r["ipo"],r["peak_yr"],r["mult"],r["rs_low_date"],
                        f"{r['drawdown']:.0f}", f"{a['bottom_score']:.2f}",
                        f"{a['p1_eclipse']:.2f}", a["p1_tight_hits"], a["age"],
                        f"{a['p3_neptune']:.2f}", a["tag"]])
    with open("/home/user/cyclepapa/data/rs_high_differentiation.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","ipo","rs_rank","pct_from_high","tag","net","cont_score",
                    "top_score","jup_supports","saturn_approach","uranus_hard",
                    "prog_phase","nn_cat"])
        for tk, ipo, status, diff in rs_high_results:
            w.writerow([tk,ipo,f"{status['pct_rank']:.0f}", f"{status['pct_from_high']:.0f}",
                        diff["tag"], f"{diff['net']:+.2f}",
                        f"{diff['continuation_score']:.2f}", f"{diff['topping_score']:.2f}",
                        diff["jup_supports"], f"{diff['saturn_approach']:.2f}",
                        f"{diff['uranus_hard']:.2f}", diff["prog_phase"], diff["nn_cat"]])
    print(f"\nExported: data/secular_rs_lows.csv and data/rs_high_differentiation.csv")

if __name__ == "__main__":
    main()
