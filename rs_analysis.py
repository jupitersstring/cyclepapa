"""
Relative-strength (vs SPX) low analysis.

Part A: For 30 historical parabolic rally predecessors, find the actual
  RS-low date and compute astro signature using signals 1/2/3 only
  (eclipse preseed + age + Neptune). Validates the canonical bottom
  signature against real relative-price lows.

Part B: For current SP500 + top Ritter picks, fetch price history,
  compute current RS-vs-SPX status (pct from 52-wk low/high),
  and cross-reference with astro signature. Identifies stocks
  currently at RS-lows matching the historical GME/CVNA signature.
"""
import json, csv, sys, time, subprocess
from datetime import datetime, timezone
from collections import defaultdict
import statistics as st
from bti_test import compute_natal, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database
from bti_v17_bottomcatch import score_v17_bottom_catch
from yf_fetcher import fetch_prices, rs_series, ticker_52wk_low_date, compute_current_rs_status

# ============================================================
# Part A: Historical parabolic rally predecessors
# (ticker, IPO_date, approx_RS_low_Ymd, peak_multiple, notes)
# ============================================================
HISTORICAL_RS_LOWS = [
    # Squeeze / meme parabolics
    ("GME",   "2002-02-13", "2020-04", 160, "Apr 2020 RS low → Jan 2021 160x"),
    ("AMC",   "2013-12-18", "2020-11", 31,  "Nov 2020 → Jun 2021 31x"),
    ("BBBY",  "1992-06-04", "2022-06", 5,   "Jun 2022 → Aug 2022 5x"),
    ("TLRY",  "2018-07-19", "2018-07", 18,  "IPO Jul 2018 → Sep 2018 18x"),
    ("CVNA",  "2017-04-28", "2022-12", 75,  "Dec 2022 → Nov 2024 75x"),
    ("CELH",  "2006-07-18", "2020-03", 100, "Mar 2020 → Mar 2022 100x"),
    # AI / 2022 cohort
    ("NVDA",  "1999-01-22", "2022-10", 13,  "Oct 2022 → Jun 2024 13x"),
    ("SMCI",  "2007-03-29", "2022-10", 17,  "Oct 2022 → Mar 2024 17x"),
    ("APP",   "2021-04-15", "2022-12", 40,  "Dec 2022 → Nov 2024 40x"),
    ("PLTR",  "2020-09-30", "2022-12", 13,  "Dec 2022 → Dec 2024 13x"),
    ("MSTR",  "1998-06-11", "2022-12", 4,   "Dec 2022 → Nov 2024 4x"),
    ("COIN",  "2021-04-14", "2023-01", 10,  "Jan 2023 → Dec 2024 10x"),
    ("HIMS",  "2021-01-21", "2023-05", 12,  "May 2023 → Feb 2025 12x"),
    ("IONQ",  "2021-10-01", "2023-05", 16,  "May 2023 → Feb 2025 16x"),
    ("RKLB",  "2021-08-25", "2023-02", 7,   "Feb 2023 → Nov 2024 7x"),
    ("VST",   "2016-10-10", "2023-01", 9,   "Jan 2023 → Oct 2024 9x"),
    ("CEG",   "2022-02-02", "2022-09", 4,   "Sep 2022 → May 2024 4x"),
    ("RDDT",  "2024-03-21", "2024-08", 7,   "Aug 2024 → Feb 2025 7x"),
    ("SOUN",  "2022-04-28", "2023-05", 15,  "May 2023 → Mar 2024 15x"),
    ("RGTI",  "2022-03-02", "2022-12", 30,  "Dec 2022 → Jan 2025 30x"),
    ("QBTS",  "2022-08-08", "2022-12", 20,  "Dec 2022 → Jan 2025 20x"),
    ("ALAB",  "2024-03-20", "2024-08", 4,   "Aug 2024 → Feb 2025 4x"),
    ("VKTX",  "2015-09-29", "2023-10", 10,  "Oct 2023 → Feb 2024 10x"),
    # Defense/energy
    ("SMR",   "2022-05-03", "2023-08", 15,  "Aug 2023 → Dec 2024 15x"),
    ("OKLO",  "2024-05-10", "2024-09", 4,   "Sep 2024 → Jan 2025 4x"),
    ("NNE",   "2024-05-01", "2024-05", 6,   "IPO May 2024 → Dec 2024 6x"),
    ("TLN",   "2023-05-22", "2023-10", 3,   "Oct 2023 → Aug 2024 3x"),
]

# Part B: Current candidates — pulled from v16 prime picks + Ritter fresh
CURRENT_CANDIDATES = [
    # SP500 v16 PRE_BUBBLE_PRIME
    ("NVR","2019-09-26"), ("ULTA","2007-10-24"), ("KO","1919-09-05"),
    ("PH","1964-07-01"), ("CMS","1927-01-01"), ("ITW","1965-01-01"),
    ("ZTS","2013-01-31"), ("EQIX","2000-08-10"), ("CMI","1964-12-01"),
    ("AIG","1969-05-01"), ("EOG","1989-10-04"), ("CF","2005-08-10"),
    ("TSN","2005-08-10"), ("PGR","1971-04-15"), ("IBM","1915-09-01"),
    # SP500 broader PRE_BUBBLE
    ("OMC","1986-08-01"), ("OKE","2010-03-15"), ("J","2007-10-26"),
    ("DDOG","2019-09-19"), ("BG","2001-08-02"), ("CVX","2001-10-09"),
    ("NTRS","1998-01-30"), ("ELV","2002-07-25"), ("TDG","2006-03-14"),
    ("SYF","2014-07-31"), ("LULU","2007-07-27"), ("EQT","2022-10-03"),
    ("DVA","2008-07-31"), ("CDNS","2017-09-18"),
    ("IR","2020-03-03"), ("MNST","2012-06-28"), ("GWW","1967-04-14"),
    ("CPT","1993-07-22"), ("LLY","1952-04-15"), ("RL","1995-07-26"),
    ("VICI","2018-02-01"), ("VRSN","1998-01-29"), ("BKNG","2009-11-06"),
    ("TER","2020-09-21"), ("D","1909-01-01"), ("NOW","2012-06-28"),
    ("VLTO","2023-10-02"), ("GE","1892-04-15"), ("NEE","1950-05-01"),
    ("PEP","1919-03-01"), ("MRNA","2018-12-07"), ("GOOG","2004-08-19"),
    ("ALGN","2001-01-26"), ("HUBB","2023-10-18"), ("XEL","1993-08-04"),
    ("CPAY","2018-06-20"), ("PFE","1942-06-23"), ("ZBRA","1991-08-15"),
    # SATURN_POP_NEAR (to check if Type B bottoms)
    ("GOOGL","2006-04-03"), ("KDP","2022-06-21"), ("APO","2011-03-29"),
    ("TROW","1986-04-02"), ("FICO","2023-03-20"), ("GEV","2024-04-02"),
    ("GDDY","2015-04-01"), ("EW","2011-04-01"), ("CPRT","1982-04-02"),
    ("CEG","2022-02-02"), ("PM","2008-03-31"),
    # Current runners to confirm are NOT at RS-lows
    ("NVDA","1999-01-22"), ("PLTR","2020-09-30"), ("APP","2021-04-15"),
    ("MSTR","1998-06-11"), ("HOOD","2021-07-29"),
    # Ritter fresh high scorers
    ("SONO","2018-08-02"), ("DT","2019-08-01"), ("KVYO","2023-09-20"),
    ("RBRK","2024-04-25"), ("OS","2024-07-24"), ("INGM","2024-10-24"),
    ("ARM","2023-09-14"), ("ALAB","2024-03-20"), ("HNGE","2025-05-22"),
    ("VITL","2020-07-31"), ("CXM","2021-06-23"), ("FA","2021-06-23"),
    ("CWK","2018-08-02"), ("AMAL","2018-08-09"), ("DUOL","2021-07-28"),
    ("PTON","2019-09-26"), ("SOFI","2021-06-01"), ("RDDT","2024-03-21"),
]

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses", file=sys.stderr)

    # Fetch SPX once
    print("Fetching SPY (baseline)...", file=sys.stderr)
    spx = fetch_prices("SPY", 2018)
    if not spx:
        print("ERROR: no SPY data", file=sys.stderr); return
    print(f"  SPY {len(spx)} days", file=sys.stderr)

    # =====================================================
    # PART A: Historical RS-low validation
    # =====================================================
    print(f"\n{'='*170}")
    print(f"PART A: ASTROLOGICAL SIGNATURE AT HISTORICAL RS-LOWS (pre-parabolic)")
    print(f"{'='*170}")
    print(f"{'Tkr':<6s} {'IPO':<11s} {'ExpLow':<8s} {'ActualRS_Low':<12s} {'PxLow':<12s} {'Mult':>4s} {'BtmScr':>6s} {'Ecl':>4s} {'Tight':>5s} {'Age_b':>5s} {'Nep':>4s} {'Tag':<20s}")
    sig_scores = []
    for tk, ipo, exp_low, mult, notes in HISTORICAL_RS_LOWS:
        stock = fetch_prices(tk, 2018)
        time.sleep(0.1)
        if not stock:
            print(f"  {tk:<6s} NO DATA")
            continue
        # Compute RS vs SPX
        rs = rs_series(stock, spx)
        if not rs:
            print(f"  {tk:<6s} NO RS DATA")
            continue
        # Find actual RS-low date (minimum RS in 2019-2025 window)
        rs_filtered = [(d, r) for (d, r) in rs if "2019-01-01" <= d <= "2025-12-31"]
        if not rs_filtered:
            print(f"  {tk:<6s} NO RS in window"); continue
        min_rs = min(r for (d, r) in rs_filtered)
        rs_low_date = [d for (d, r) in rs_filtered if r == min_rs][0]
        low_y, low_m = int(rs_low_date[:4]), int(rs_low_date[5:7])
        # Price low
        min_px = min(c for (d, c) in stock if "2019-01-01" <= d <= "2025-12-31")
        px_low_date = [d for (d, c) in stock if c == min_px and "2019-01-01" <= d <= "2025-12-31"][0]
        # Astro signature at RS-low
        try:
            natal = compute_natal(ipo)
            r = score_v17_bottom_catch(natal, low_y, low_m, ipo, db)
            sig_scores.append(r["bottom_score"])
            print(f"{tk:<6s} {ipo:<11s} {exp_low:<8s} {rs_low_date:<12s} {px_low_date:<12s} {mult:>3d}× {r['bottom_score']:6.2f} {r['p1_eclipse']:4.1f} {r['p1_tight_hits']:>5d} {r['p2_age']:5.1f} {r['p3_neptune']:4.1f} {r['tag']:<20s}")
        except Exception as e:
            print(f"  {tk} ERR {e}")
    print(f"\n  Historical RS-low signature stats (n={len(sig_scores)}):")
    if sig_scores:
        print(f"    Mean={st.mean(sig_scores):.2f}  Median={st.median(sig_scores):.2f}")
        print(f"    %≥5 (BOTTOM_CATCH+): {100*sum(1 for s in sig_scores if s>=5)/len(sig_scores):.0f}%")
        print(f"    %≥3 (POSSIBLE+):     {100*sum(1 for s in sig_scores if s>=3)/len(sig_scores):.0f}%")

    # =====================================================
    # PART B: Current candidates — find RS status + astro
    # =====================================================
    print(f"\n{'='*170}")
    print(f"PART B: CURRENT RS STATUS (Apr 2026) vs ASTRO SIGNATURE for candidate lists")
    print(f"{'='*170}")
    print(f"{'Tkr':<7s} {'IPO':<11s} {'RSrank':>6s} {'%fromLo':>7s} {'%fromHi':>7s} {'52wkLow':<12s} {'CurBtm':>6s} {'Ecl':>4s} {'Age':>3s} {'Nep':>4s} {'Tag':<20s} {'Note'}")
    current_results = []
    for tk, ipo in CURRENT_CANDIDATES:
        stock = fetch_prices(tk, 2020)
        time.sleep(0.1)
        if not stock: continue
        rs = rs_series(stock, spx)
        if not rs: continue
        status = compute_current_rs_status(rs)
        if not status: continue
        px_status = ticker_52wk_low_date(stock)
        # Astro at TODAY
        try:
            natal = compute_natal(ipo)
            r = score_v17_bottom_catch(natal, 2026, 4, ipo, db)
            current_results.append({
                "ticker": tk, "ipo": ipo,
                "rs_rank": status["pct_rank"],
                "pct_from_low": status["pct_from_low"],
                "pct_from_high": status["pct_from_high"],
                "days_since_low": status["days_since_low"],
                "px_low_date": px_status["low_date"] if px_status else "",
                "px_pct_from_low": px_status["pct_from_low"] if px_status else 0,
                "astro": r,
            })
            note = ""
            if status["pct_rank"] <= 15 and r["bottom_score"] >= 5:
                note = "★★ RS-LOW + STRONG ASTRO"
            elif status["pct_rank"] <= 25 and r["bottom_score"] >= 3:
                note = "★ RS-low + astro"
            elif status["pct_rank"] >= 80:
                note = "RS-high (already run)"
            print(f"{tk:<7s} {ipo:<11s} {status['pct_rank']:5.0f}% {status['pct_from_low']:+6.0f}% {status['pct_from_high']:+6.0f}% {px_status['low_date'] if px_status else '':<12s} {r['bottom_score']:6.2f} {r['p1_eclipse']:4.1f} {r['age']:>3d} {r['p3_neptune']:4.1f} {r['tag']:<20s} {note}")
        except Exception as e:
            pass

    # Final shortlist: currently at RS-low (rank ≤ 25) + bottom_score ≥ 3
    print(f"\n{'='*170}")
    print(f"SHORTLIST — AT RELATIVE-STRENGTH-LOW NOW + ASTRO SIGNATURE PRESENT")
    print(f"{'='*170}")
    shortlist = [r for r in current_results if r["rs_rank"] <= 25 and r["astro"]["bottom_score"] >= 3]
    shortlist.sort(key=lambda r: (r["rs_rank"], -r["astro"]["bottom_score"]))
    print(f"{'Tkr':<7s} {'IPO':<11s} {'RSrank':>6s} {'%fromHi':>7s} {'Age':>3s} {'Btm':>5s} {'Ecl':>4s} {'Tight':>5s} {'Nep':>4s} {'Eclipses'}")
    for r in shortlist[:30]:
        a = r["astro"]
        ecl_d = " | ".join(a["p1_detail"][:2])[:55]
        print(f"{r['ticker']:<7s} {r['ipo']:<11s} {r['rs_rank']:5.0f}% {r['pct_from_high']:+6.0f}% {a['age']:>3d} {a['bottom_score']:5.2f} {a['p1_eclipse']:4.1f} {a['p1_tight_hits']:>5d} {a['p3_neptune']:4.1f} {ecl_d}")

    # Export
    with open("/home/user/cyclepapa/data/rs_analysis.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","ipo","rs_rank_pct","pct_from_low","pct_from_high","days_since_low",
                    "px_low_date","bottom_score","eclipse","tight_hits","age","neptune","tag"])
        for r in current_results:
            a = r["astro"]
            w.writerow([r["ticker"], r["ipo"],
                        f"{r['rs_rank']:.1f}", f"{r['pct_from_low']:.1f}",
                        f"{r['pct_from_high']:.1f}", r["days_since_low"],
                        r["px_low_date"], f"{a['bottom_score']:.2f}",
                        f"{a['p1_eclipse']:.2f}", a["p1_tight_hits"],
                        a["age"], f"{a['p3_neptune']:.2f}", a["tag"]])
    print(f"\nExported: data/rs_analysis.csv")

if __name__ == "__main__":
    main()
