"""
Analyse what v9 scores at:
  (1) secular bottoms (pre-multi-year-bull)
  (2) monthly/correction lows (not real secular)
  (3) mega-parabolic bottoms (GME, HKD, MARA, RIOT, DWAC)
  (4) post-peak fake bottoms (to test specificity)

Find: what distinguishes secular bottoms that produce 100x+ parabolic rallies
from ones that produce modest 3-10x rallies?
"""
import math
import statistics as st
from collections import defaultdict
from bti_test import compute_natal
from bti_v4 import yx
from bti_v9 import compute_bti_v9, bti_window_v9

# Split the 110-bottom corpus by rally magnitude
from secular_bottoms_corpus import SECULAR_BOTTOMS

MEGA_RALLIES = []      # 100x+
SECULAR_RALLIES = []   # 10x-99x
MODEST_RALLIES = []    # 3x-9x
for tk, ipo, bot, top, mult, note in SECULAR_BOTTOMS:
    if mult >= 100:
        MEGA_RALLIES.append((tk, ipo, bot, top, mult, note))
    elif mult >= 10:
        SECULAR_RALLIES.append((tk, ipo, bot, top, mult, note))
    else:
        MODEST_RALLIES.append((tk, ipo, bot, top, mult, note))

print(f"Corpus: {len(MEGA_RALLIES)} mega (100×+), {len(SECULAR_RALLIES)} secular (10-99×), {len(MODEST_RALLIES)} modest (3-9×)")

# Compute v9 scores at each bottom + top + quiet sample
def score_group(group, label):
    bot_scores = []
    top_scores = []
    quiet_scores = []
    for tk, ipo, bot, top, mult, note in group:
        try:
            natal = compute_natal(ipo)
            r_bot = compute_bti_v9(natal, bot[0], bot[1])
            bot_scores.append((tk, r_bot["bti"], r_bot["js_phase"], r_bot["almuten"], mult))
            r_top = compute_bti_v9(natal, top[0], top[1])
            top_scores.append((tk, r_top["bti"], mult))
            # Quiet = 24mo before bottom
            y, m = yx(bot[0], bot[1], -24)
            rq = compute_bti_v9(natal, y, m)
            quiet_scores.append(rq["bti"])
        except Exception:
            pass
    print(f"\n{'='*100}")
    print(f"{label} (n={len(group)})")
    print(f"{'='*100}")
    print(f"  Bottom BTI: mean={st.mean([s[1] for s in bot_scores]):.2f}  median={st.median([s[1] for s in bot_scores]):.2f}")
    print(f"  Top BTI:    mean={st.mean([s[1] for s in top_scores]):.2f}")
    print(f"  Quiet-24mo BTI: mean={st.mean(quiet_scores):.2f}")
    # JS phase distribution
    ph = defaultdict(int)
    alm = defaultdict(int)
    for tk, bti, phase, a, m in bot_scores:
        ph[phase] += 1; alm[a] += 1
    print(f"  JS phase at bottom: ", dict(ph))
    print(f"  Almuten at bottom:  ", dict(alm))
    # Detail
    print(f"\n  {'Tkr':<8s} {'Mult':>5s} {'BotBTI':>6s} {'JSphase':<14s} {'Almuten':<8s}")
    for tk, bti, phase, a, m in sorted(bot_scores, key=lambda x:-x[1]):
        print(f"  {tk:<8s} {m:5d} {bti:6.2f} {phase:<14s} {a:<8s}")
    return bot_scores

mega = score_group(MEGA_RALLIES, "MEGA RALLIES (100×+)")
sec = score_group(SECULAR_RALLIES, "SECULAR RALLIES (10-99×)")
mod = score_group(MODEST_RALLIES, "MODEST RALLIES (3-9×)")

# Are there natal features unique to MEGA rallies?
print(f"\n{'='*100}")
print(f"NATAL SIGNATURES — what distinguishes 100×+ from 3-9× rallies?")
print(f"{'='*100}")

def natal_features(ipo):
    natal = compute_natal(ipo)
    # Key features
    # 1. Sun-Uranus orb (explosive chart)
    sun_ur = min(abs((natal["Sun"]["lon"] - natal["Uranus"]["lon"]) % 360),
                 abs(360 - (natal["Sun"]["lon"] - natal["Uranus"]["lon"]) % 360),
                 abs((natal["Sun"]["lon"] - natal["Uranus"]["lon"] - 90) % 360),
                 abs((natal["Sun"]["lon"] - natal["Uranus"]["lon"] - 180) % 360))
    # 2. Sun-Pluto orb
    sun_pl = min(abs((natal["Sun"]["lon"] - natal["Pluto"]["lon"]) % 360),
                 abs(360 - (natal["Sun"]["lon"] - natal["Pluto"]["lon"]) % 360),
                 abs((natal["Sun"]["lon"] - natal["Pluto"]["lon"] - 90) % 360),
                 abs((natal["Sun"]["lon"] - natal["Pluto"]["lon"] - 180) % 360))
    # 3. Jupiter-Pluto orb
    ju_pl = min(abs((natal["Jupiter"]["lon"] - natal["Pluto"]["lon"]) % 360),
                abs(360 - (natal["Jupiter"]["lon"] - natal["Pluto"]["lon"]) % 360),
                abs((natal["Jupiter"]["lon"] - natal["Pluto"]["lon"] - 90) % 360),
                abs((natal["Jupiter"]["lon"] - natal["Pluto"]["lon"] - 180) % 360))
    return {
        "sun_ur": sun_ur, "sun_pl": sun_pl, "ju_pl": ju_pl,
        "sun_sign": natal["Sun"]["sign"],
    }

def summarise(group, label):
    feats = [natal_features(ipo) for _, ipo, *_ in group]
    if not feats: return
    print(f"\n{label} (n={len(feats)}):")
    print(f"  Sun-Uranus orb:  median={st.median(f['sun_ur'] for f in feats):5.1f}°  min={min(f['sun_ur'] for f in feats):.1f}°  %≤8°: {100*sum(1 for f in feats if f['sun_ur']<=8)/len(feats):.0f}%")
    print(f"  Sun-Pluto orb:   median={st.median(f['sun_pl'] for f in feats):5.1f}°  min={min(f['sun_pl'] for f in feats):.1f}°  %≤8°: {100*sum(1 for f in feats if f['sun_pl']<=8)/len(feats):.0f}%")
    print(f"  Jupiter-Pluto:   median={st.median(f['ju_pl'] for f in feats):5.1f}°  min={min(f['ju_pl'] for f in feats):.1f}°  %≤8°: {100*sum(1 for f in feats if f['ju_pl']<=8)/len(feats):.0f}%")
    SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]
    sun_c = defaultdict(int)
    for f in feats: sun_c[SIGNS[f['sun_sign']]] += 1
    print(f"  Sun sign distribution: {dict(sun_c)}")

summarise(MEGA_RALLIES, "MEGA (100×+)")
summarise(SECULAR_RALLIES, "SECULAR (10-99×)")
summarise(MODEST_RALLIES, "MODEST (3-9×)")
