"""
SECTOR-SPECIFIC astro signature test.

Hypothesis (from traditional mundane astrology):
  Neptune rules: oil/gas, pharma, shipping, film, cannabis, chemicals, spirits
  Uranus rules:  technology, electricity, aviation, innovation, crypto
  Pluto  rules:  biotech, mining, nuclear, insurance, dark/transformative
  Saturn rules:  real-estate, agriculture, traditional industrials, banks (stability)
  Jupiter rules: financials/brokerage, religion, publishing, law, travel/luxury
  Mercury rules: telecom/communications, transport, retail, data/media
  Venus  rules:  luxury goods, cosmetics, entertainment, restaurants

Question: at parabolic bottoms/peaks within each sector, is the
ruling-planet transit closer to natal points than non-ruling planets?

Test:
  - Bucket 152 cases by sector
  - Within each bucket, rank outer planets by mean orb to closest natal point
    at bottom vs peak
  - Does the ruler's mean orb rank first for the sector?
"""
import statistics as st
from bti_test import compute_natal, transits_at
from parabolic_corpus import PARABOLIC_BOTTOMS
from three_phase_scrutiny import snapshot, midpoint, orb, closest_hard, OUTERS, NATAL_PTS

# Sector assignments (manual, based on actual business at time of parabolic move).
# Where a ticker had multiple runs, use _XX suffix.
SECTOR = {
    # TECH — Uranus
    "AAPL":"TECH","MSFT":"TECH","GOOG":"TECH","NVDA":"TECH","NVDA16":"TECH",
    "AMD16":"TECH","INTC":"TECH","CSCO":"TECH","ORCL":"TECH","DELL":"TECH",
    "MU16":"TECH","SMCI":"TECH","JDSU":"TECH","SUNW":"TECH","YHOO":"TECH",
    "AOL":"TECH","EBAY99":"TECH","PCLN":"TECH","RIMM":"TECH","META":"TECH",
    "SHOP":"TECH","CRWD":"TECH","DDOG":"TECH","NET":"TECH","SNOW":"TECH",
    "FSLY":"TECH","DOCU":"TECH","TWLO":"TECH","PLTR":"TECH","APP":"TECH",
    "SOUN":"TECH","DDD":"TECH","IONQ":"TECH","QBTS":"TECH","RGTI":"TECH",
    "ZM":"TECH","BIDU":"TECH","PDD":"TECH","SE":"TECH","FUTU":"TECH","TIGR":"TECH",
    "OZON":"TECH","XNET":"TECH","TME":"TECH","LK":"TECH","DRCT":"TECH",
    "BIOS":"TECH","DJT":"TECH","AMZN":"TECH","AMZN22":"TECH","AMZN99":"TECH",
    # BIOTECH / PHARMA — Pluto + Neptune
    "MRNA":"BIOPHARM","BNTX":"BIOPHARM","VKTX":"BIOPHARM","NVAX":"BIOPHARM",
    "ATOS":"BIOPHARM","ACRS":"BIOPHARM","HIMS":"BIOPHARM","SAVA":"BIOPHARM",
    "PROG":"BIOPHARM",
    # ENERGY / OIL / URANIUM — Neptune + Pluto
    "CCJ":"ENERGY","CEG":"ENERGY","VST":"ENERGY","TLN":"ENERGY","SMR":"ENERGY",
    "NNE":"ENERGY","OKLO":"ENERGY","FSLR":"ENERGY","PLUG":"ENERGY","PLUG14":"ENERGY",
    "BLNK":"ENERGY","FCEL14":"ENERGY","GEV":"ENERGY",
    # MINING / METALS — Pluto + Saturn
    "NEM":"METALS","AEM":"METALS","FCX":"METALS",
    # EV / AUTO — Uranus + Mercury
    "TSLA12":"EV","TSLA19":"EV","RIVN":"EV","LCID":"EV","NIO":"EV","XPEV":"EV",
    "LI":"EV","CCIV":"EV","NKLA":"EV","RIDE":"EV","HYLN":"EV","GOEV":"EV",
    "FFIE":"EV","MULN":"EV","WKHS":"EV","SPCE":"EV",
    # FINANCE / FINTECH — Jupiter + Mercury
    "BAC":"FINANCE","SOFI":"FINANCE","HOOD":"FINANCE","UPST":"FINANCE",
    "AFRM":"FINANCE","COIN":"FINANCE",
    # CANNABIS — Neptune (intoxicants)
    "ACB":"CANNABIS","CGC":"CANNABIS","CRON":"CANNABIS","TLRY":"CANNABIS",
    "TLRY18":"CANNABIS","SNDL":"CANNABIS",
    # CRYPTO MINERS & CRYPTO — Uranus + Neptune
    "MARA":"CRYPTO","RIOT":"CRYPTO","CAN":"CRYPTO","EBON":"CRYPTO","HUT":"CRYPTO",
    "CLSK":"CRYPTO","SOS":"CRYPTO","XRP":"CRYPTO","ETH":"CRYPTO","MSTR":"CRYPTO",
    # RETAIL / CONSUMER — Venus + Mercury
    "GME":"RETAIL","GME2":"RETAIL","AMC":"RETAIL","BBBY":"RETAIL","KOSS":"RETAIL",
    "EXPR":"RETAIL","NAKD":"RETAIL","ATER":"RETAIL","BBIG":"RETAIL","MMAT":"RETAIL",
    "LULU":"RETAIL","CROX":"RETAIL","CROX08":"RETAIL","DECK":"RETAIL","DKNG":"RETAIL",
    "PTON":"RETAIL","WMT":"RETAIL","HD":"RETAIL","MCD74":"RETAIL","SBUX":"RETAIL",
    "CMG":"RETAIL","CELH":"RETAIL","GMCR":"RETAIL","MO":"RETAIL","SEZL":"RETAIL",
    "WYNN":"RETAIL","LVS":"RETAIL","F":"RETAIL",
    # MEDIA / COMMUNICATIONS / STREAMING — Mercury + Neptune
    "NFLX":"MEDIA","NFLX12":"MEDIA","TWTR":"MEDIA","FUBO":"MEDIA",
    # SPACS / MEME NO-SECTOR — mixed
    "HKD":"MEME","DWAC":"MEME","IRNT":"MEME","OPAD":"MEME","CLOV":"MEME",
    "CFVI":"MEME","QS":"MEME",
    # HARDWARE / NETWORKING / SEMIS — Uranus (overlap tech)
    "QCOM":"TECH",
}

def main():
    cases = []
    for tk, ipo, bot, top, mult, speed, note in PARABOLIC_BOTTOMS:
        sec = SECTOR.get(tk, "UNK")
        try:
            natal = compute_natal(ipo)
            b = snapshot(natal, bot)
            p = snapshot(natal, top)
            mid = midpoint(bot, top)
            m = snapshot(natal, mid)
            cases.append({"tk": tk, "sec": sec, "mult": mult, "speed": speed,
                          "bot": b, "mid": m, "peak": p})
        except:
            continue

    # Sector sizes
    from collections import Counter
    sizes = Counter(c["sec"] for c in cases)
    print(f"Corpus sectorised ({len(cases)} cases):")
    for s, n in sorted(sizes.items(), key=lambda x:-x[1]):
        print(f"  {s:<10s} {n:3d}")

    def min_orb(snap, outer):
        return min(snap["per_point"][outer].values())

    sectors_to_test = [s for s, n in sizes.items() if n >= 5 and s != "UNK"]

    # --- Part 1: per-sector mean outer-planet min-orb at BOTTOM ---
    print("\n" + "="*95)
    print(" MEAN MIN-ORB (to nearest natal Sun/Moon/ASC/MC) by sector at BOTTOM")
    print("="*95)
    print(f"  {'Sector':<10s} {'n':>3s} | {'Jup':>6s} {'Sat':>6s} {'Ura':>6s} {'Nep':>6s} {'Plu':>6s}   tightest -> 2nd")
    sector_bot_ranks = {}
    for sec in sectors_to_test:
        sub = [c for c in cases if c["sec"] == sec]
        means = {o: st.mean(min_orb(c["bot"], o) for c in sub) for o in OUTERS}
        rank = sorted(means.items(), key=lambda x: x[1])
        sector_bot_ranks[sec] = rank
        print(f"  {sec:<10s} {len(sub):3d} | "
              f"{means['Jupiter']:6.2f} {means['Saturn']:6.2f} {means['Uranus']:6.2f} "
              f"{means['Neptune']:6.2f} {means['Pluto']:6.2f}   "
              f"{rank[0][0]}({rank[0][1]:.1f}) -> {rank[1][0]}({rank[1][1]:.1f})")

    # --- Part 2: per-sector mean outer-planet min-orb at PEAK ---
    print("\n" + "="*95)
    print(" MEAN MIN-ORB by sector at PEAK")
    print("="*95)
    print(f"  {'Sector':<10s} {'n':>3s} | {'Jup':>6s} {'Sat':>6s} {'Ura':>6s} {'Nep':>6s} {'Plu':>6s}   tightest -> 2nd")
    sector_peak_ranks = {}
    for sec in sectors_to_test:
        sub = [c for c in cases if c["sec"] == sec]
        means = {o: st.mean(min_orb(c["peak"], o) for c in sub) for o in OUTERS}
        rank = sorted(means.items(), key=lambda x: x[1])
        sector_peak_ranks[sec] = rank
        print(f"  {sec:<10s} {len(sub):3d} | "
              f"{means['Jupiter']:6.2f} {means['Saturn']:6.2f} {means['Uranus']:6.2f} "
              f"{means['Neptune']:6.2f} {means['Pluto']:6.2f}   "
              f"{rank[0][0]}({rank[0][1]:.1f}) -> {rank[1][0]}({rank[1][1]:.1f})")

    # --- Part 3: classical hypothesis test ---
    print("\n" + "="*95)
    print(" HYPOTHESIS TEST: does the traditional ruler of each sector have the")
    print(" tightest orb at parabolic BOTTOM? (Rank 1 = tightest)")
    print("="*95)
    RULER = {
        "TECH":"Uranus","CRYPTO":"Uranus","EV":"Uranus",
        "BIOPHARM":"Pluto","METALS":"Pluto",
        "ENERGY":"Neptune","CANNABIS":"Neptune","MEDIA":"Neptune",
        "FINANCE":"Jupiter",
        "RETAIL":"Venus",  # not in outers, will check Jupiter as secondary luxury
    }
    print(f"  {'Sector':<10s} {'Ruler':<9s} {'BotRank':>8s} {'PeakRank':>9s}   {'Bot μ':>6s} {'Peak μ':>7s}   Verdict")
    for sec, ruler in RULER.items():
        if sec not in sector_bot_ranks: continue
        if ruler not in ("Jupiter","Saturn","Uranus","Neptune","Pluto"): continue
        bot_rank = [r[0] for r in sector_bot_ranks[sec]].index(ruler) + 1
        peak_rank = [r[0] for r in sector_peak_ranks[sec]].index(ruler) + 1
        bot_mean = dict(sector_bot_ranks[sec])[ruler]
        peak_mean = dict(sector_peak_ranks[sec])[ruler]
        v = "✓ ruler tightest at bottom" if bot_rank == 1 else ("~ ruler top-2 at bottom" if bot_rank <= 2 else "✗")
        print(f"  {sec:<10s} {ruler:<9s} {bot_rank:>8d} {peak_rank:>9d}   {bot_mean:>6.2f} {peak_mean:>7.2f}   {v}")

    # --- Part 4: % of sector with ruler ≤5° at bottom (vs baseline) ---
    print("\n" + "="*95)
    print(" % of sector cases with each outer ≤5° to any natal at BOTTOM (ruler-test)")
    print("="*95)
    print(f"  {'Sector':<10s} {'n':>3s} | {'Jup≤5°':>6s} {'Sat≤5°':>6s} {'Ura≤5°':>6s} {'Nep≤5°':>6s} {'Plu≤5°':>6s}   Ruler-hit rate")
    for sec in sectors_to_test:
        sub = [c for c in cases if c["sec"] == sec]
        if not sub: continue
        pcts = {o: 100*sum(1 for c in sub if min_orb(c["bot"], o) <= 5)/len(sub) for o in OUTERS}
        ruler = RULER.get(sec, "")
        r_pct = pcts.get(ruler) if ruler in OUTERS else None
        # baseline: 4 points * 3 aspects = 12 aspect-points across 360°, ≤5° window
        # raw baseline ≈ 24/360 = 6.7% per planet, but with 4 targets we effectively
        # have several attempts. Empirically ~25% single-planet. Use overall bottom rate.
        overall = 100*sum(1 for c in cases if min_orb(c["bot"], ruler) <= 5)/len(cases) if ruler in OUTERS else 0
        hit_note = f"{r_pct:.0f}% vs corpus {overall:.0f}%" if r_pct is not None else "N/A"
        print(f"  {sec:<10s} {len(sub):3d} | "
              f"{pcts['Jupiter']:5.0f}% {pcts['Saturn']:5.0f}% {pcts['Uranus']:5.0f}% "
              f"{pcts['Neptune']:5.0f}% {pcts['Pluto']:5.0f}%   {hit_note}")

    # --- Part 5: which sector has the most LIFT of its ruler vs other planets ---
    print("\n" + "="*95)
    print(" SECTOR ASYMMETRY: is the ruler's ≤5° rate ABOVE all other planets?")
    print("="*95)
    print(f"  {'Sector':<10s} {'Ruler':<9s} {'R%':>4s} {'Others μ':>8s} {'Lift':>6s}  Verdict")
    for sec in sectors_to_test:
        ruler = RULER.get(sec, "")
        if ruler not in OUTERS: continue
        sub = [c for c in cases if c["sec"] == sec]
        if not sub: continue
        pcts = {o: 100*sum(1 for c in sub if min_orb(c["bot"], o) <= 5)/len(sub) for o in OUTERS}
        r_pct = pcts[ruler]
        others_mu = st.mean(v for k, v in pcts.items() if k != ruler)
        lift = r_pct - others_mu
        v = "✓ ruler leads" if lift > 5 else ("~ ruler tied" if lift > 0 else "✗ other planet leads")
        print(f"  {sec:<10s} {ruler:<9s} {r_pct:4.0f} {others_mu:8.1f} {lift:>+6.1f}  {v}")

    # --- Part 6: same for PEAK ---
    print("\n" + "="*95)
    print(" SECTOR at PEAK — does ruler get TIGHTER (lift up) or LOOSER (lift down)?")
    print("="*95)
    print(f"  {'Sector':<10s} {'Ruler':<9s} {'BotR%':>6s} {'PkR%':>6s}  Δ    {'bot μ':>7s} {'pk μ':>7s}")
    for sec in sectors_to_test:
        ruler = RULER.get(sec, "")
        if ruler not in OUTERS: continue
        sub = [c for c in cases if c["sec"] == sec]
        bot_pct = 100*sum(1 for c in sub if min_orb(c["bot"], ruler) <= 5)/len(sub)
        pk_pct = 100*sum(1 for c in sub if min_orb(c["peak"], ruler) <= 5)/len(sub)
        bot_mu = st.mean(min_orb(c["bot"], ruler) for c in sub)
        pk_mu = st.mean(min_orb(c["peak"], ruler) for c in sub)
        print(f"  {sec:<10s} {ruler:<9s} {bot_pct:>5.0f}% {pk_pct:>5.0f}%  {pk_pct-bot_pct:+5.0f}  {bot_mu:7.2f} {pk_mu:7.2f}")

if __name__ == "__main__":
    main()
