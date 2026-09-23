"""
DEEPER SECTOR WORK — four extensions to sector_astro.py:

  (1) PEAK signatures per sector — not just bottoms. Which planet tightens
      at the peak of each sector's parabolic moves? Combined with bottom
      work, gives bottom-ruler vs peak-ruler per sector (signals EXIT timing).

  (2) SUB-INDUSTRY splits within big sectors (TECH, ENERGY, RETAIL).
      Does quantum computing look different from SaaS?  Does uranium/nuclear
      differ from oil?  Different sub-industry rulerships matter.

  (3) PER-SECTOR COMPOUND rules — which 2-planet bucket combos fire most
      at the bottom within each sector? v19 global rules may mislead per
      sector.

  (4) WHICH NATAL POINT each sector's ruler hits most often. For BIOPHARM
      the Pluto might primarily aspect MC (fame transform) or Sun (identity
      transform) — the point matters for interpretation AND for screening.

Sub-industry labels (manual — based on actual business at time of move):
  TECH subs: SEMIS, SAAS, INTERNET, HARDWARE, AI_QUANTUM
  ENERGY subs: NUCLEAR_URANIUM, OIL_GAS, CLEAN_ALT, POWER_UTIL
  RETAIL subs: APPAREL, RESTAURANTS, CONSUMER_BRAND, ECOMMERCE, LEISURE
"""
import statistics as st
from collections import defaultdict, Counter
from bti_test import compute_natal, transits_at
from parabolic_corpus import PARABOLIC_BOTTOMS
from three_phase_scrutiny import snapshot, midpoint, closest_hard, OUTERS, NATAL_PTS
from bti_v19_empirical import COMPOUND_RULES
from sector_astro import SECTOR

# Sub-industry overlay on the sectorised parabolic corpus
SUBIND = {
    # TECH - SEMIS (physical silicon)
    "NVDA":"SEMIS","NVDA16":"SEMIS","AMD16":"SEMIS","INTC":"SEMIS","MU16":"SEMIS",
    "SMCI":"SEMIS","QCOM":"SEMIS","JDSU":"SEMIS","SUNW":"SEMIS",
    # TECH - SAAS / enterprise software
    "CRWD":"SAAS","DDOG":"SAAS","NET":"SAAS","SNOW":"SAAS","FSLY":"SAAS",
    "DOCU":"SAAS","TWLO":"SAAS","ZM":"SAAS","NOW":"SAAS","ORCL":"SAAS",
    "SHOP":"SAAS","CSCO":"SAAS","MSFT":"SAAS",
    # TECH - INTERNET / platforms
    "META":"INTERNET","GOOG":"INTERNET","AMZN":"INTERNET","AMZN99":"INTERNET",
    "AMZN22":"INTERNET","YHOO":"INTERNET","AOL":"INTERNET","EBAY99":"INTERNET",
    "PCLN":"INTERNET","BIDU":"INTERNET","PDD":"INTERNET","SE":"INTERNET",
    "FUTU":"INTERNET","TIGR":"INTERNET","OZON":"INTERNET","XNET":"INTERNET",
    "TME":"INTERNET","LK":"INTERNET","BIOS":"INTERNET","DRCT":"INTERNET",
    "DJT":"INTERNET",
    # TECH - HARDWARE / devices
    "AAPL":"HARDWARE","DELL":"HARDWARE","RIMM":"HARDWARE",
    # TECH - AI / QUANTUM
    "PLTR":"AI_QUANTUM","APP":"AI_QUANTUM","SOUN":"AI_QUANTUM",
    "DDD":"AI_QUANTUM","IONQ":"AI_QUANTUM","QBTS":"AI_QUANTUM","RGTI":"AI_QUANTUM",

    # ENERGY subs
    "CCJ":"NUCLEAR","CEG":"NUCLEAR","VST":"NUCLEAR","TLN":"NUCLEAR","SMR":"NUCLEAR",
    "NNE":"NUCLEAR","OKLO":"NUCLEAR",
    "PLUG":"CLEAN","PLUG14":"CLEAN","BLNK":"CLEAN","FCEL14":"CLEAN","FSLR":"CLEAN",
    "GEV":"CLEAN",

    # RETAIL subs
    "LULU":"APPAREL","CROX":"APPAREL","CROX08":"APPAREL","DECK":"APPAREL",
    "CMG":"RESTAURANT","CELH":"RESTAURANT","GMCR":"RESTAURANT","MCD74":"RESTAURANT",
    "SBUX":"RESTAURANT",
    "WMT":"BROAD","HD":"BROAD","F":"BROAD",
    "GME":"SPEC","GME2":"SPEC","AMC":"SPEC","BBBY":"SPEC","KOSS":"SPEC",
    "EXPR":"SPEC","NAKD":"SPEC","ATER":"SPEC","BBIG":"SPEC","MMAT":"SPEC",
    "DKNG":"LEISURE","PTON":"LEISURE","WYNN":"LEISURE","LVS":"LEISURE",
    "MO":"CONSUMER_BRAND","SEZL":"CONSUMER_BRAND",
}

def min_orb(snap, outer):
    return min(snap["per_point"][outer].values())

def orb_by_point(snap, outer):
    """Return dict point -> orb, for aggregating which point the ruler hits."""
    return dict(snap["per_point"][outer])

def load_cases():
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        sec = SECTOR.get(tk, "UNK")
        sub = SUBIND.get(tk, None)
        try:
            natal = compute_natal(ipo)
            b = snapshot(natal, bot)
            p = snapshot(natal, top)
            m = snapshot(natal, midpoint(bot, top))
            cases.append({"tk":tk,"sec":sec,"sub":sub,"mult":mult,"speed":speed,
                          "bot":b,"mid":m,"peak":p})
        except:
            continue
    return cases

def section(title):
    print(f"\n{'='*100}\n {title}\n{'='*100}")

# ---------------- (1) PEAK signatures per sector --------------------
def analyse_peaks(cases):
    section("(1) PEAK-ruler per sector — which planet tightens at the TOP")
    from collections import Counter
    sizes = Counter(c["sec"] for c in cases)
    print(f"  {'Sector':<10s} {'n':>3s} | {'Jup':>6s} {'Sat':>6s} {'Ura':>6s} {'Nep':>6s} {'Plu':>6s}   tightest(peak)  vs bottom ruler")
    for sec in sorted([s for s,n in sizes.items() if n>=5 and s!="UNK"]):
        sub = [c for c in cases if c["sec"]==sec]
        pk = {o: st.mean(min_orb(c["peak"], o) for c in sub) for o in OUTERS}
        bot = {o: st.mean(min_orb(c["bot"], o) for c in sub) for o in OUTERS}
        rp = min(pk, key=pk.get)
        rb = min(bot, key=bot.get)
        flip = "" if rp==rb else f"  FLIP bot={rb}({bot[rb]:.1f}) -> peak={rp}({pk[rp]:.1f})"
        print(f"  {sec:<10s} {len(sub):3d} | "
              f"{pk['Jupiter']:6.2f} {pk['Saturn']:6.2f} {pk['Uranus']:6.2f} "
              f"{pk['Neptune']:6.2f} {pk['Pluto']:6.2f}   {rp}({pk[rp]:.2f}){flip}")

    # Peak-ruler %≤5° and lift vs others, per sector
    section("(1b) PEAK: %-cases with each outer ≤5° at PEAK per sector")
    print(f"  {'Sector':<10s} {'n':>3s} | {'Jup':>6s} {'Sat':>6s} {'Ura':>6s} {'Nep':>6s} {'Plu':>6s}   Winner")
    for sec in sorted([s for s,n in sizes.items() if n>=5 and s!="UNK"]):
        sub = [c for c in cases if c["sec"]==sec]
        pcts = {o: 100*sum(1 for c in sub if min_orb(c["peak"],o)<=5)/len(sub) for o in OUTERS}
        w = max(pcts, key=pcts.get)
        print(f"  {sec:<10s} {len(sub):3d} | "
              f"{pcts['Jupiter']:5.0f}% {pcts['Saturn']:5.0f}% {pcts['Uranus']:5.0f}% "
              f"{pcts['Neptune']:5.0f}% {pcts['Pluto']:5.0f}%   {w} ({pcts[w]:.0f}%)")

# ---------------- (2) sub-industry splits ---------------------------
def analyse_subindustry(cases):
    section("(2) SUB-INDUSTRY splits — TECH / ENERGY / RETAIL")
    from collections import Counter
    sub_cases = [c for c in cases if c["sub"]]
    sizes = Counter(c["sub"] for c in sub_cases)
    print(f"  Sub-industry sizes:")
    for s, n in sorted(sizes.items(), key=lambda x:-x[1]):
        print(f"    {s:<14s} {n:3d}")

    print(f"\n  Mean-orb at BOTTOM per sub-industry (n≥4):")
    print(f"  {'Sub-industry':<14s} {'n':>3s} | {'Jup':>6s} {'Sat':>6s} {'Ura':>6s} {'Nep':>6s} {'Plu':>6s}   bot-ruler -> peak-ruler")
    for sub in sorted([s for s,n in sizes.items() if n>=4]):
        grp = [c for c in sub_cases if c["sub"]==sub]
        bm = {o: st.mean(min_orb(c["bot"], o) for c in grp) for o in OUTERS}
        pm = {o: st.mean(min_orb(c["peak"], o) for c in grp) for o in OUTERS}
        rb = min(bm, key=bm.get); rp = min(pm, key=pm.get)
        flip_mark = " FLIP" if rb != rp else ""
        print(f"  {sub:<14s} {len(grp):3d} | "
              f"{bm['Jupiter']:6.2f} {bm['Saturn']:6.2f} {bm['Uranus']:6.2f} "
              f"{bm['Neptune']:6.2f} {bm['Pluto']:6.2f}   "
              f"{rb}({bm[rb]:.1f}) -> {rp}({pm[rp]:.1f}){flip_mark}")

    # Hit rate ≤5°
    print(f"\n  % cases with outer ≤5° at BOTTOM per sub-industry (n≥4):")
    print(f"  {'Sub-industry':<14s} {'n':>3s} | {'Jup':>5s} {'Sat':>5s} {'Ura':>5s} {'Nep':>5s} {'Plu':>5s}   Winner")
    for sub in sorted([s for s,n in sizes.items() if n>=4]):
        grp = [c for c in sub_cases if c["sub"]==sub]
        pcts = {o: 100*sum(1 for c in grp if min_orb(c["bot"],o)<=5)/len(grp) for o in OUTERS}
        w = max(pcts, key=pcts.get)
        print(f"  {sub:<14s} {len(grp):3d} | "
              f"{pcts['Jupiter']:4.0f}% {pcts['Saturn']:4.0f}% {pcts['Uranus']:4.0f}% "
              f"{pcts['Neptune']:4.0f}% {pcts['Pluto']:4.0f}%   {w}({pcts[w]:.0f}%)")

# ---------------- (3) per-sector compound rules ---------------------
def analyse_compound(cases):
    section("(3) PER-SECTOR compound rule fire-rate at BOTTOM")
    from collections import Counter
    sizes = Counter(c["sec"] for c in cases)
    rules = [(lbl, fn) for lbl, fn, _ in COMPOUND_RULES]
    rule_names = [l for l,_ in rules]
    # Build per-sector rule fire rate
    secs_show = [s for s,n in sizes.items() if n>=5 and s!="UNK"]
    baseline = {}
    for lbl, fn in rules:
        # Build outer_orbs dict (what COMPOUND_RULES expects) from snapshot
        hits = 0
        for c in cases:
            orbs = {o: min_orb(c["bot"], o) for o in OUTERS}
            if fn(orbs): hits += 1
        baseline[lbl] = 100*hits/len(cases)
    print(f"  {'Rule':<28s} | " + " ".join(f"{s[:7]:>7s}" for s in secs_show) + f"   {'Base':>5s}")
    for lbl, fn in rules:
        row = [f"{baseline[lbl]:5.0f}%"]
        cells = []
        for sec in secs_show:
            grp = [c for c in cases if c["sec"]==sec]
            hits = sum(1 for c in grp if fn({o: min_orb(c["bot"], o) for o in OUTERS}))
            rate = 100*hits/len(grp) if grp else 0
            lift = rate - baseline[lbl]
            marker = "▲" if lift > 10 else ("▼" if lift < -10 else " ")
            cells.append(f"{rate:5.0f}%{marker}")
        print(f"  {lbl:<28s} | " + " ".join(f"{c:>7s}" for c in cells) + f"   {baseline[lbl]:4.0f}%")

# ---------------- (4) which natal point per sector ------------------
def analyse_natal_point(cases):
    section("(4) SECTOR-RULER → which natal point (Sun/Moon/ASC/MC)?")
    RULER_BOT = {"TECH":"Saturn","BIOPHARM":"Pluto","EV":"Uranus","ENERGY":"Jupiter",
                 "FINANCE":"Pluto","MEME":"Pluto","CRYPTO":"Jupiter","CANNABIS":"Pluto",
                 "RETAIL":"Jupiter","METALS":"Pluto","MEDIA":"Neptune"}
    from collections import Counter
    sizes = Counter(c["sec"] for c in cases)
    for sec in sorted([s for s,n in sizes.items() if n>=5 and s!="UNK"]):
        ruler = RULER_BOT.get(sec)
        if not ruler: continue
        sub = [c for c in cases if c["sec"]==sec]
        # Which point is tightest for this ruler at bottom?
        pt_closest = {pt:0 for pt in NATAL_PTS}
        pt_hit5 = {pt:0 for pt in NATAL_PTS}
        for c in sub:
            orbs = c["bot"]["per_point"][ruler]
            best_pt = min(orbs, key=orbs.get)
            pt_closest[best_pt] += 1
            for pt, o in orbs.items():
                if o <= 5: pt_hit5[pt] += 1
        n = len(sub)
        print(f"\n  {sec:<10s} (n={n}) ruler={ruler} — which natal point attracts most?")
        print(f"    Point attributed as tightest:")
        for pt in NATAL_PTS:
            print(f"      {pt:<5s}: {pt_closest[pt]:2d}/{n} ({100*pt_closest[pt]/n:3.0f}%)   ≤5° hit-rate: {100*pt_hit5[pt]/n:3.0f}%")

# ---------------- (5) sector + speed/magnitude cross -----------------
def analyse_speed_magnitude(cases):
    section("(5) SECTOR × SPEED × MAGNITUDE")
    from collections import Counter
    grouped = defaultdict(list)
    for c in cases:
        grouped[(c["sec"], c["speed"])].append(c)
    print(f"  {'Sector':<10s} {'Speed':<5s} {'n':>3s} | {'mean_mult':>10s} {'med':>6s} {'max':>6s}  {'>=25x':>6s} {'>=100x':>6s}")
    # By sector only (aggregate speeds)
    for sec in sorted(set(c["sec"] for c in cases if c["sec"]!="UNK")):
        sub = [c for c in cases if c["sec"]==sec]
        if len(sub) < 4: continue
        mm = [c["mult"] for c in sub]
        p25 = 100*sum(1 for m in mm if m>=25)/len(mm)
        p100 = 100*sum(1 for m in mm if m>=100)/len(mm)
        print(f"  {sec:<10s} {'ALL':<5s} {len(sub):3d} | "
              f"{st.mean(mm):10.1f} {st.median(mm):6.1f} {max(mm):6.0f}  {p25:5.0f}% {p100:5.0f}%")

# ---------------- MAIN ----------------
def main():
    cases = load_cases()
    print(f"Loaded {len(cases)} cases")
    analyse_peaks(cases)
    analyse_subindustry(cases)
    analyse_compound(cases)
    analyse_natal_point(cases)
    analyse_speed_magnitude(cases)

if __name__ == "__main__":
    main()
