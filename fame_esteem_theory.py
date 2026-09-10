"""
Astrological theory of RANK / ESTEEM / FAME — rises and falls.

CLASSICAL AND MUNDANE DOCTRINE:

Sun = kingship, fame, public standing (Ptolemy, Lilly, Manilius)
MC = career, public reputation, "place of action"
10th house = honors, rank, the crown
Royal Stars (Ptolemy) = inherent fame markers:
  Regulus 0° Vir — kingship (current epoch longitude after precession)
  Spica 24° Lib — brilliance, talent
  Antares 9° Sag — warrior-honor, intensity
  Aldebaran 10° Gem — honor through effort
Jupiter = benefic expansion; Sun's traditional "cousin" in dignity

RISE to fame/esteem — classical signatures:
  Transit Jupiter on natal Sun, MC, ASC (expansion of public self)
  Transit Uranus on natal Sun (sudden electrical rise — Musk type)
  Transit North Node on natal Sun/MC (becoming visible to the crowd)
  Natal Sun/MC/ASC on Royal Star (inherent fame, 'born for it')
  Progressed Sun entering cardinal sign or aspecting benefic
  Vedic: Jupiter or Rahu dasa periods = meteoric rise
  Solar arc MC to natal Jupiter/Venus

FALL from esteem / rise in notoriety:
  Transit Saturn conj/opp natal Sun/MC (public reckoning)
  Transit Pluto to natal Sun (transformation of identity; death of old role)
  Transit Neptune to natal Sun (dissolution, scandal, exposure)
  Transit Uranus opp natal Sun (shock reversal)
  Eclipse on natal Sun/MC (pivotal event, can go either way)
  Transit South Node on natal Sun/MC (loss of spotlight)
  Sade Sati (Vedic): Saturn through 12th-1st-2nd from natal Moon = 7.5y humbling
  Solar arc Saturn to natal Sun

HISTORICAL VALIDATORS:
  Elizabeth Holmes (peak 2014-15, fall 2015-18):
    Neptune on natal Sun 2014-15, Saturn square natal Sun 2015-18
  Sam Bankman-Fried (peak 2021, fall Nov 2022):
    Nov 8 2022 lunar eclipse at 16° Tau square his Mars-Saturn 13° Aqu
  Bernie Madoff (fall Dec 2008):
    Saturn conj natal Saturn; Saturn-Uranus opp to natal chart
  Lance Armstrong (stripped 2012):
    Pluto transformed natal Sun
  OJ Simpson (1994 arrest):
    Total solar eclipse May 10 1994 at 20° Taurus exact on his natal Uranus
  GameStop (Jan 2021 fame moment):
    Jupiter entering Aquarius conjunct natal Sun 25° Aqu (Gidel's 'massive misrep')
  DJT (March 2024):
    IPO peak coincided with Jupiter-Uranus conj Taurus on natal

THE STOCK-AS-ENTITY MAPPING:
  Stocks experience 'rank-rise' (mass retail discovery, memeing, Regulus-activation)
  and 'rank-fall' (reality check, Saturn exposure, Neptune dissolution of narrative).
  Parabolic meme = compressed celebrity rise. Post-squeeze collapse = compressed fall.
"""
import math, csv, sys, time, statistics as st
from collections import defaultdict
import swisseph as swe
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from classical_extensions import FIXED_STARS, secondary_progressions, progressed_lunation_phase

SIGNS = ["Ari","Tau","Gem","Can","Leo","Vir","Lib","Sco","Sag","Cap","Aqu","Pis"]

ROYAL_STARS = {
    "Regulus":    0.30,
    "Spica":      204.28,
    "Antares":    250.00,
    "Aldebaran":  70.15,
}

def orb(a, b):
    d = abs((a - b) % 360)
    return min(d, 360 - d)

def closest_hard(a, b, aspects=(0, 90, 180), max_orb=30):
    best = (None, 99)
    for asp in aspects:
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best[1]: best = (asp, o)
    return best

def closest_any(a, b, aspects=(0, 60, 90, 120, 180), max_orb=30):
    best = (None, 99)
    for asp in aspects:
        for sign in (+1, -1):
            o = orb(a, b + sign*asp)
            if o < best[1]: best = (asp, o)
    return best

def score_fame_potential(natal):
    """Inherent fame potential based on Royal Star contacts + Sun condition."""
    score = 0
    reasons = []
    # Royal Star conjunctions (within 2°)
    for p in ("Sun","Moon","Mercury","Venus","Mars","Jupiter","Saturn","ASC","MC"):
        if p not in natal: continue
        for star, slon in ROYAL_STARS.items():
            o = orb(natal[p]["lon"], slon)
            if o <= 2.0:
                w = 3.0 if p in ("Sun","MC","ASC") else 1.5
                pts = w * (2.0 - o) / 2.0
                score += pts
                reasons.append(f"{p}-{star} {o:.1f}°")
    # Sun angular (conj ASC or MC within 5°)
    sun_asc = orb(natal["Sun"]["lon"], natal["ASC"]["lon"])
    sun_mc = orb(natal["Sun"]["lon"], natal["MC"]["lon"])
    if sun_asc <= 5 or sun_mc <= 5:
        score += 1.5
        reasons.append(f"Sun angular (ASC:{sun_asc:.1f} MC:{sun_mc:.1f})")
    # Sun-Jupiter aspect (fame+expansion coupling)
    sj = closest_any(natal["Sun"]["lon"], natal["Jupiter"]["lon"])
    if sj[0] is not None and sj[1] <= 6:
        w = 1.5 if sj[0] in (0, 120) else 1.0 if sj[0] == 60 else 0.6
        score += w * (6 - sj[1]) / 6
        reasons.append(f"Sun-Jup {sj[0]}° {sj[1]:.1f}°")
    # Sun in Leo (own sign) — inherent kingship
    if natal["Sun"]["sign"] == 4:
        score += 1.0
        reasons.append("Sun in Leo")
    return score, reasons

def score_rise_triggers(natal, eval_y, eval_m):
    """Current transits producing RISE in rank/fame."""
    trans = transits_at(eval_y, eval_m)
    score = 0
    reasons = []
    # (1) Jupiter on natal Sun/MC/ASC — peak of expansion cycle
    for tgt in ("Sun","MC","ASC"):
        if tgt not in natal: continue
        r = closest_any(trans["Jupiter"]["lon"], natal[tgt]["lon"])
        if r[0] is not None and r[1] <= 3:
            w = 2.0 if r[0] == 0 else 1.5 if r[0] in (120,60) else 1.0
            pts = w * (3 - r[1]) / 3
            if tgt == "Sun": pts *= 1.3
            score += pts
            reasons.append(f"trJup {r[0]}° nat{tgt} {r[1]:.1f}°")
    # (2) Uranus on natal Sun/MC — sudden electrical rise
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        r = closest_hard(trans["Uranus"]["lon"], natal[tgt]["lon"])
        if r[0] is not None and r[1] <= 3:
            w = 2.2 if r[0] == 0 else 1.6
            pts = w * (3 - r[1]) / 3
            score += pts
            reasons.append(f"trUra {r[0]}° nat{tgt} {r[1]:.1f}°")
    # (3) North Node on natal Sun/MC — attention/crowd focus
    nn = trans["NN"]["lon"]
    for tgt in ("Sun","MC","ASC"):
        if tgt not in natal: continue
        o = orb(nn, natal[tgt]["lon"])
        if o <= 3:
            score += 1.5 * (3 - o) / 3
            reasons.append(f"trNN conj nat{tgt} {o:.1f}°")
    # (4) Transit Jupiter on a Royal Star
    for star, slon in ROYAL_STARS.items():
        o = orb(trans["Jupiter"]["lon"], slon)
        if o <= 2:
            score += 1.2 * (2 - o) / 2
            reasons.append(f"trJup on {star} {o:.1f}°")
    # (5) Progressed Sun to natal Jupiter (benefic expansion phase)
    return score, reasons

def score_fall_triggers(natal, eval_y, eval_m):
    """Current transits producing FALL from rank / notoriety."""
    trans = transits_at(eval_y, eval_m)
    score = 0
    reasons = []
    # (1) Saturn conj/opp natal Sun/MC — public reckoning
    for tgt in ("Sun","MC","ASC"):
        if tgt not in natal: continue
        r = closest_hard(trans["Saturn"]["lon"], natal[tgt]["lon"])
        if r[0] is not None and r[1] <= 3:
            w = 2.2 if r[0] == 0 else 1.8 if r[0] == 180 else 1.3
            pts = w * (3 - r[1]) / 3
            if tgt == "Sun": pts *= 1.3
            score += pts
            reasons.append(f"trSat {r[0]}° nat{tgt} {r[1]:.1f}°")
    # (2) Pluto on natal Sun — transformation/death of role
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        r = closest_hard(trans["Pluto"]["lon"], natal[tgt]["lon"])
        if r[0] is not None and r[1] <= 3:
            w = 2.0 if r[0] == 0 else 1.6
            pts = w * (3 - r[1]) / 3
            score += pts
            reasons.append(f"trPlu {r[0]}° nat{tgt} {r[1]:.1f}°")
    # (3) Neptune on natal Sun — dissolution/scandal
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        r = closest_hard(trans["Neptune"]["lon"], natal[tgt]["lon"])
        if r[0] is not None and r[1] <= 3:
            w = 1.8 if r[0] == 0 else 1.4
            pts = w * (3 - r[1]) / 3
            score += pts
            reasons.append(f"trNep {r[0]}° nat{tgt} {r[1]:.1f}°")
    # (4) South Node on natal Sun/MC — loss of spotlight
    sn = (trans["NN"]["lon"] + 180) % 360
    for tgt in ("Sun","MC"):
        if tgt not in natal: continue
        o = orb(sn, natal[tgt]["lon"])
        if o <= 3:
            score += 1.2 * (3 - o) / 3
            reasons.append(f"trSN conj nat{tgt} {o:.1f}°")
    # (5) Transit Saturn on Royal Star natal placement
    for p in ("Sun","MC","ASC"):
        if p not in natal: continue
        for star, slon in ROYAL_STARS.items():
            if orb(natal[p]["lon"], slon) <= 2:
                # Chart has natal on Royal Star; is transit Saturn aspecting that degree?
                r = closest_hard(trans["Saturn"]["lon"], slon)
                if r[1] <= 2:
                    score += 1.5 * (2 - r[1]) / 2
                    reasons.append(f"trSat hits nat{p}-on-{star}")
    return score, reasons

def validate_on_cases():
    """Test on known rise/fall historical cases."""
    cases = [
        # (label, natal_date, event_date, expected_type, description)
        ("SBF/FTX fall",       "1992-03-06", "2022-11", "fall",  "FTX collapse Nov 2022"),
        ("Holmes/Theranos",    "1984-02-03", "2015-10", "fall",  "Wall St Journal Theranos exposé"),
        ("Madoff fall",        "1938-04-29", "2008-12", "fall",  "Arrest Dec 11 2008"),
        ("OJ arrest",          "1947-07-09", "1994-06", "fall",  "Bronco chase June 1994"),
        ("Lance Armstrong",    "1971-09-18", "2012-08", "fall",  "Stripped Aug 2012"),
        ("Epstein arrest",     "1953-01-20", "2019-07", "fall",  "Arrest Jul 2019"),
        ("Obama election",     "1961-08-04", "2008-11", "rise",  "Nov 2008 elected"),
        ("Musk TSLA peak",     "1971-06-28", "2021-10", "rise",  "$1T valuation Oct 2021"),
        ("Taylor Swift Eras",  "1989-12-13", "2023-03", "rise",  "Eras tour peak"),
        ("Trump 2016 win",     "1946-06-14", "2016-11", "rise",  "Nov 2016 election"),
        ("DJT IPO peak",       "2024-03-26", "2024-03", "rise",  "IPO spike Mar 2024"),
        ("GME squeeze",        "2002-02-13", "2021-01", "rise",  "Jan 28 2021 $483"),
        ("AMC squeeze",        "2013-12-18", "2021-06", "rise",  "Jun 2021 peak"),
    ]
    print(f"\n{'='*140}")
    print(f"VALIDATION on known rise/fall events")
    print(f"{'='*140}")
    print(f"{'Case':<28s} {'Natal':<11s} {'Event':<8s} {'Expect':<5s} {'Rise':>5s} {'Fall':>5s} {'Net':>5s} {'Reasons (top)'}")
    for label, natal_date, event, expected, desc in cases:
        try:
            natal = compute_natal(natal_date)
            y, m = int(event[:4]), int(event[5:7])
            rise_s, rise_r = score_rise_triggers(natal, y, m)
            fall_s, fall_r = score_fall_triggers(natal, y, m)
            net = rise_s - fall_s
            dom_reasons = (rise_r + fall_r)[:2]
            key = " | ".join(dom_reasons)[:60]
            print(f"{label:<28s} {natal_date:<11s} {event:<8s} {expected:<5s} {rise_s:5.2f} {fall_s:5.2f} {net:+5.2f} {key}")
        except Exception as e:
            print(f"{label}: ERR {e}")

def main():
    validate_on_cases()

    # Score SP500 for current fame-rise / fame-fall triggers
    print(f"\n{'='*170}")
    print(f"SP500 @ 2026-04 — rank/esteem rise and fall triggers (with inherent fame potential)")
    print(f"{'='*170}")
    sp500 = []
    with open("/home/user/cyclepapa/data/sp500_ipo_dates.csv") as f:
        sp500 = list(csv.DictReader(f))
    t0 = time.time()
    results = []
    for row in sp500:
        try:
            natal = compute_natal(row["ipo_date"])
            fame_pot, fame_r = score_fame_potential(natal)
            rise_s, rise_r = score_rise_triggers(natal, 2026, 4)
            fall_s, fall_r = score_fall_triggers(natal, 2026, 4)
            results.append({
                "ticker": row["ticker"], "name": row["name"],
                "sector": row["sector"], "ipo": row["ipo_date"],
                "source": row.get("source",""),
                "fame_pot": fame_pot, "fame_r": fame_r,
                "rise": rise_s, "rise_r": rise_r,
                "fall": fall_s, "fall_r": fall_r,
                "net": rise_s - fall_s,
            })
        except: pass
    print(f"  Scanned {len(results)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Sort by rise - fall (net rise momentum)
    results.sort(key=lambda r: -r["net"])
    print(f"\nTOP 30 RANK-RISE (net=rise-fall)")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<26s} {'IPO':<11s} {'FamePt':>6s} {'Rise':>5s} {'Fall':>5s} {'Net':>5s} {'Rise triggers'}")
    for i, r in enumerate(results[:30], 1):
        key = " | ".join(r["rise_r"][:3])[:70]
        src = "*" if r["source"] == "sp500_added" else " "
        print(f"{i:3d} {r['ticker']:<6s} {r['name'][:26]:<26s} {r['ipo']:<11s} {r['fame_pot']:6.2f} {r['rise']:5.2f} {r['fall']:5.2f} {r['net']:+5.2f} {key}{src}")

    # Sort by fall - rise (net fall momentum)
    results.sort(key=lambda r: r["net"])
    print(f"\nTOP 30 RANK-FALL (net fall momentum)")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Name':<26s} {'IPO':<11s} {'FamePt':>6s} {'Rise':>5s} {'Fall':>5s} {'Net':>5s} {'Fall triggers'}")
    for i, r in enumerate(results[:30], 1):
        key = " | ".join(r["fall_r"][:3])[:70]
        src = "*" if r["source"] == "sp500_added" else " "
        print(f"{i:3d} {r['ticker']:<6s} {r['name'][:26]:<26s} {r['ipo']:<11s} {r['fame_pot']:6.2f} {r['rise']:5.2f} {r['fall']:5.2f} {r['net']:+5.2f} {key}{src}")

    # Charts with highest FAME POTENTIAL currently ACTIVATED for rise
    print(f"\n{'='*170}")
    print(f"HIGH FAME POTENTIAL + RISE ACTIVATION (inherent celebrity charts now rising)")
    print(f"{'='*170}")
    fame_rise = [r for r in results if r["fame_pot"] >= 1.5 and r["rise"] >= 2.0]
    fame_rise.sort(key=lambda r: -(r["fame_pot"] + r["rise"]))
    for r in fame_rise[:20]:
        fame_key = " | ".join(r["fame_r"][:2])[:40]
        rise_key = " | ".join(r["rise_r"][:2])[:50]
        src = "*" if r["source"] == "sp500_added" else " "
        print(f"  {r['ticker']:<6s} {r['name'][:26]:<26s} fame={r['fame_pot']:.1f} rise={r['rise']:.1f} fall={r['fall']:.1f}  [{fame_key}]  -->  [{rise_key}]{src}")

    # Charts with high FAME potential + FALL activation (celebrity-fall candidates)
    print(f"\n{'='*170}")
    print(f"HIGH FAME POTENTIAL + FALL ACTIVATION (celebrity-fall candidates)")
    print(f"{'='*170}")
    fame_fall = [r for r in results if r["fame_pot"] >= 1.5 and r["fall"] >= 2.0]
    fame_fall.sort(key=lambda r: -(r["fame_pot"] + r["fall"]))
    for r in fame_fall[:20]:
        fame_key = " | ".join(r["fame_r"][:2])[:40]
        fall_key = " | ".join(r["fall_r"][:2])[:50]
        src = "*" if r["source"] == "sp500_added" else " "
        print(f"  {r['ticker']:<6s} {r['name'][:26]:<26s} fame={r['fame_pot']:.1f} fall={r['fall']:.1f} rise={r['rise']:.1f}  [{fame_key}]  -->  [{fall_key}]{src}")

    # Export
    with open("/home/user/cyclepapa/data/sp500_fame_rise_fall.csv","w",newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","sector","ipo","source","fame_potential",
                    "rise_score","fall_score","net","fame_reasons","rise_reasons","fall_reasons"])
        for r in results:
            w.writerow([r["ticker"],r["name"],r["sector"],r["ipo"],r["source"],
                        f"{r['fame_pot']:.2f}",f"{r['rise']:.2f}",f"{r['fall']:.2f}",
                        f"{r['net']:+.2f}"," | ".join(r["fame_r"]),
                        " | ".join(r["rise_r"])," | ".join(r["fall_r"])])
    print(f"\nExported: data/sp500_fame_rise_fall.csv")

if __name__ == "__main__":
    main()
