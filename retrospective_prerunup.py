"""
Retrospective analysis: for stocks that ran hard in 2023-2025, find the
astrological signature at their 52-week low / pre-runup bottom.

Method:
  1. Known ticker/IPO/low_date pairs for recent big winners
  2. Compute v16 pre-bubble features at the low date
  3. Extract common pre-runup patterns
  4. Cross-reference with current v16 SP500/Ritter picks to see which
     stocks today look most like these historical pre-runup lows
"""
import csv, sys
from collections import defaultdict
import statistics as st
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from bti_v16_prebubble import score_v16_pre_bubble
from eclipse_database import build_eclipse_database

# Historical pre-runup lows for 2023-2025 winners
# Format: (ticker, IPO_date, low_y, low_m, peak_mult_since_low, name)
RECENT_RUNUPS = [
    ("NVDA",  "1999-01-22", 2022, 10, 13,   "Nvidia"),
    ("PLTR",  "2020-09-30", 2022, 12, 13,   "Palantir"),
    ("APP",   "2021-04-15", 2022, 12, 40,   "AppLovin"),
    ("SMCI",  "2007-03-29", 2022, 10, 17,   "Super Micro"),
    ("CVNA",  "2017-04-28", 2022, 12, 75,   "Carvana"),
    ("MSTR",  "1998-06-11", 2022, 12, 4,    "MicroStrategy"),
    ("COIN",  "2021-04-14", 2023, 1,  10,   "Coinbase"),
    ("HIMS",  "2021-01-21", 2023, 5,  12,   "Hims & Hers"),
    ("IONQ",  "2021-10-01", 2023, 5,  16,   "IonQ"),
    ("RKLB",  "2021-08-25", 2023, 2,  7,    "Rocket Lab"),
    ("VST",   "2016-10-10", 2023, 1,  9,    "Vistra"),
    ("CEG",   "2022-02-02", 2022, 9,  4,    "Constellation Energy"),
    ("RDDT",  "2024-03-21", 2024, 8,  7,    "Reddit (post-IPO bottom)"),
    ("HOOD",  "2021-07-29", 2022, 6,  10,   "Robinhood"),
    ("SOFI",  "2021-06-01", 2022, 12, 5,    "SoFi"),
    ("AXON",  "2001-06-07", 2022, 5,  5,    "Axon Enterprise"),
    ("DUOL",  "2021-07-28", 2022, 11, 5,    "Duolingo"),
    ("CELH",  "2006-07-18", 2020, 3,  100,  "Celsius Holdings"),
    ("VKTX",  "2015-09-29", 2023, 10, 10,   "Viking Therapeutics"),
    ("ALAB",  "2024-03-20", 2024, 8,  4,    "Astera Labs"),
    ("ARM",   "2023-09-14", 2024, 4,  4,    "Arm Holdings"),
    ("SOUN",  "2022-04-28", 2023, 5,  15,   "SoundHound AI"),
    ("RGTI",  "2022-03-02", 2022, 12, 30,   "Rigetti Computing"),
    ("QBTS",  "2022-08-08", 2022, 12, 20,   "D-Wave Quantum"),
    ("NBIS",  "2024-10-21", 2024, 12, 3,    "Nebius Group"),
    ("SMR",   "2022-05-03", 2023, 8,  15,   "NuScale Power"),
    ("OKLO",  "2024-05-10", 2024, 9,  4,    "Oklo"),
    ("NNE",   "2024-05-01", 2024, 5,  6,    "Nano Nuclear"),
    ("TLN",   "2023-05-22", 2023, 10, 3,    "Talen Energy"),
    ("CRWV",  "2025-03-28", 2025, 4,  3,    "CoreWeave"),
    ("CRDO",  "2022-01-27", 2023, 1,  15,   "Credo Technology"),
    ("MRX",   "2024-04-25", 2024, 8,  2.5,  "Marex Group"),
]

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)
    print(f"  {len(db)} eclipses", file=sys.stderr)

    rows = []
    print(f"\n{'='*180}")
    print(f"RETROSPECTIVE: v16 PRE-BUBBLE features AT THE 52-WEEK LOW / PRE-RUNUP DATE")
    print(f"{'='*180}")
    print(f"{'Tkr':<7s} {'IPO':<11s} {'Low':<8s} {'Mult':>5s} {'Age':>3s} {'Score':>5s} {'JN°':>4s} {'Act':>3s} {'Pop':>3s} {'Tag':<17s} {'Key triggers at low'}")

    for tk, ipo, ly, lm, mult, name in RECENT_RUNUPS:
        try:
            natal = compute_natal(ipo)
            r = score_v16_pre_bubble(natal, ly, lm, ipo, name, db)
            rows.append((tk, name, ipo, ly, lm, mult, r))
            act = r["bubble_activation_mo"] if r["bubble_activation_mo"] is not None else "-"
            pop = r["saturn_pop_mo"] if r["saturn_pop_mo"] is not None else "-"
            triggers = " | ".join((r["p2_detail"] + r["p3_detail"] + r["p4_detail"][:2])[:3])[:75]
            print(f"{tk:<7s} {ipo:<11s} {ly}-{lm:02d}  {mult:>4d}× {r['age']:>3d} {r['pre_bubble']:5.2f} {r['jn_orb']:4.1f} {act!s:>3s} {pop!s:>3s} {r['tag']:<17s} {triggers}")
        except Exception as e:
            print(f"{tk}: ERR {e}")

    # Aggregate patterns
    print(f"\n{'='*100}")
    print(f"AGGREGATE SIGNATURE AT PRE-RUNUP LOWS (n={len(rows)})")
    print(f"{'='*100}")
    scores = [r[6]["pre_bubble"] for r in rows]
    jn_orbs = [r[6]["jn_orb"] for r in rows if r[6]["jn_orb"] < 30]
    ages = [r[6]["age"] for r in rows]
    print(f"  Mean pre-bubble score: {st.mean(scores):.2f}  median={st.median(scores):.2f}  max={max(scores):.2f}")
    print(f"  Charts with natal JN < 6°:  {100*sum(1 for jn in jn_orbs if jn < 6)/len(rows):.0f}%")
    print(f"  Charts with natal JN < 3°:  {100*sum(1 for jn in jn_orbs if jn < 3)/len(rows):.0f}%")
    print(f"  Mean chart age at low: {st.mean(ages):.1f}y  median={st.median(ages):.0f}y")
    # Tag distribution
    tags = defaultdict(int)
    for r in rows: tags[r[6]["tag"]] += 1
    print(f"\n  Tag distribution at low:")
    for t, n in sorted(tags.items(), key=lambda x:-x[1]):
        print(f"    {t:<20s} {n:2d} ({100*n/len(rows):.0f}%)")

    # Component sums
    p_sums = defaultdict(list)
    for (_, _, _, _, _, _, r) in rows:
        p_sums["p1_natal_JN"].append(r["p1_natal_JN"])
        p_sums["p2_tr_Jup"].append(r["p2_tr_Jup"])
        p_sums["p3_tr_Nep"].append(r["p3_tr_Nep"])
        p_sums["p4_eclipse"].append(r["p4_eclipse"])
        p_sums["p5_saturn_penalty"].append(r["p5_saturn_penalty"])
        p_sums["p7_mutable"].append(r["p7_mutable"])
    print(f"\n  Component contribution at lows:")
    for k, vs in p_sums.items():
        print(f"    {k:<20s} mean={st.mean(vs):.2f}  >0: {100*sum(1 for v in vs if v>0)/len(vs):.0f}%")

    # Eclipse-recency analysis: at the low, how many had eclipse within last 6 months?
    recent_eclipse = 0
    very_recent = 0
    for (_, _, _, _, _, _, r) in rows:
        if r["p4_eclipse"] > 1.0: recent_eclipse += 1
        if r["p4_eclipse"] > 2.0: very_recent += 1
    print(f"\n  Charts with p4_eclipse > 1.0: {100*recent_eclipse/len(rows):.0f}%")
    print(f"  Charts with p4_eclipse > 2.0: {100*very_recent/len(rows):.0f}%")

    # Bubble activation timing — how far AHEAD did Jupiter reach natal target?
    act_months = [r[6]["bubble_activation_mo"] for r in rows if r[6]["bubble_activation_mo"] is not None]
    if act_months:
        print(f"\n  Charts with Jupiter activation ahead (at time of low):")
        print(f"    % with activation pending: {100*len(act_months)/len(rows):.0f}%")
        print(f"    Months until activation: median={st.median(act_months):.0f}  mean={st.mean(act_months):.1f}")
        # distribution
        d = defaultdict(int)
        for m in act_months:
            if m <= 3: d["0-3mo"] += 1
            elif m <= 6: d["4-6mo"] += 1
            elif m <= 12: d["7-12mo"] += 1
            else: d["13-18mo"] += 1
        print(f"    Bucket: {dict(d)}")

    # Most striking individual signatures
    print(f"\n{'='*100}")
    print(f"HIGHLIGHT — tightest natal JN in runup corpus")
    print(f"{'='*100}")
    tight = sorted(rows, key=lambda r: r[6]["jn_orb"])[:12]
    for tk, name, ipo, ly, lm, mult, r in tight:
        print(f"  {tk:<7s} {name[:25]:<25s} IPO={ipo}  low={ly}-{lm:02d}  mult={mult}×  natal JN={r['jn_orb']:.2f}°  score={r['pre_bubble']:.2f}  tag={r['tag']}")

    # Cross-reference: which current SP500 PRE_BUBBLE picks look most like these pre-runup lows?
    print(f"\n{'='*100}")
    print(f"CURRENT SP500 PICKS MOST LIKE HISTORICAL PRE-RUNUP LOWS")
    print(f"Match criteria: natal JN in bottom quartile of runup corpus + current score ≥ 5 + inflation ahead")
    print(f"{'='*100}")
    jn_p25 = sorted(jn_orbs)[len(jn_orbs)//4]
    print(f"  Historical pre-runup JN p25: {jn_p25:.2f}°  (median: {st.median(jn_orbs):.2f}°)")

    # Load v16 SP500 output
    try:
        sp_v16 = []
        with open("/home/user/cyclepapa/data/sp500_pre_bubble_v16.csv") as f:
            for row in csv.DictReader(f):
                if float(row["jn_orb"]) <= jn_p25 and float(row["pre_bubble"]) >= 5 and row["bubble_activation_mo"]:
                    sp_v16.append(row)
        sp_v16.sort(key=lambda r: -float(r["pre_bubble"]))
        print(f"\n  SP500 matching historical pre-runup profile:")
        for row in sp_v16[:20]:
            print(f"    {row['ticker']:<6s} {row['name'][:28]:<28s} JN={float(row['jn_orb']):.2f}° score={float(row['pre_bubble']):.2f} act={row['bubble_activation_mo']}mo tag={row['tag']}")
    except Exception as e:
        print(f"  Could not load v16 output: {e}")

    # Same for Ritter
    try:
        r_v16 = []
        with open("/home/user/cyclepapa/data/ritter_pre_bubble_v16.csv") as f:
            for row in csv.DictReader(f):
                if float(row["jn_orb"]) <= jn_p25 and float(row["pre_bubble"]) >= 8 and row["bubble_activation_mo"]:
                    if int(row["age"]) <= 10:
                        r_v16.append(row)
        r_v16.sort(key=lambda r: -float(r["pre_bubble"]))
        print(f"\n  Ritter (age ≤ 10yr, fresh) matching historical pre-runup profile:")
        for row in r_v16[:20]:
            print(f"    {row['ticker']:<7s} {row['name'][:36]:<36s} IPO={row['ipo']} age={row['age']}  JN={float(row['jn_orb']):.2f}° score={float(row['pre_bubble']):.2f}")
    except Exception as e:
        print(f"  Could not load ritter v16: {e}")

    # Export
    with open("/home/user/cyclepapa/data/retrospective_prerunup.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo","low_y","low_m","mult","age","pre_bubble","tag",
                    "jn_orb","bubble_activation_mo","saturn_pop_mo","p1","p2","p3","p4","p5",
                    "prog_phase","mut_count","p2_detail","p3_detail","p4_detail"])
        for tk, name, ipo, ly, lm, mult, r in rows:
            w.writerow([tk,name,ipo,ly,lm,mult,r["age"],
                        f"{r['pre_bubble']:.2f}",r["tag"],f"{r['jn_orb']:.2f}",
                        r["bubble_activation_mo"] or "", r["saturn_pop_mo"] or "",
                        f"{r['p1_natal_JN']:.2f}",f"{r['p2_tr_Jup']:.2f}",
                        f"{r['p3_tr_Nep']:.2f}",f"{r['p4_eclipse']:.2f}",
                        f"{r['p5_saturn_penalty']:.2f}",r["prog_phase"],r["mut_count"],
                        " | ".join(r["p2_detail"]),
                        " | ".join(r["p3_detail"]),
                        " | ".join(r["p4_detail"][:3])])
    print(f"\nExported: data/retrospective_prerunup.csv")

if __name__ == "__main__":
    main()
