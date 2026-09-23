"""
v24 — MACRO-REGIME layer on top of v23 sector-aware scanner.

For each candidate, computes forward trajectory with TWO multipliers:
  1. Base v23 sector-aware score (single-planet × sector weights)
  2. Macro-regime multiplier for the ticker's MODERN_SECTOR classification
     based on current outer-planet signs, Jupiter window, Uranus-Pluto trine
     proximity, and lunar cycle.

The modern sub-sector map is tighter than GICS — it flags tickers like NVDA
as SEMIS (not just TECH), CCJ as URANIUM (not just ENERGY), LMT as DEFENSE
(not just INDUSTRIAL). This lets the macro-tilt dictionary target finely.

Additionally: dignity boost applied to each outer planet's contribution
based on its current sign.
"""
import math, csv, sys, time, re
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb
from bti_v21_forward import saturn_pop_month
from bti_v23_sector_aware import (SECTOR_WEIGHTS, get_sector, load_sp500_sectors,
                                    sector_bucket_weight)
from macro_regime import (macro_regime_multiplier, dignity_multiplier,
                            planet_positions, trine_bonus, lunar_modifier)

START_Y, START_M = 2026, 4
MONTHS = 24

# Modern sub-sector tagging for macro-tilt lookup. Prefer more specific.
# Ticker -> modern_sector tag (used for macro_regime_multiplier)
MODERN_SECTOR = {
    # SEMIS
    "NVDA":"SEMIS","AMD":"SEMIS","INTC":"SEMIS","MU":"SEMIS","TSM":"SEMIS",
    "ASML":"SEMIS","LRCX":"SEMIS","KLAC":"SEMIS","AMAT":"SEMIS","MRVL":"SEMIS",
    "AVGO":"SEMIS","QCOM":"SEMIS","MCHP":"SEMIS","ON":"SEMIS","NXPI":"SEMIS",
    "MPWR":"SEMIS","ARM":"SEMIS","SMCI":"SEMIS","ALAB":"SEMIS","TER":"SEMIS",
    "ADI":"SEMIS","ENTG":"SEMIS","WDC":"SEMIS","STX":"SEMIS","CRUS":"SEMIS",
    # AI_QUANTUM
    "PLTR":"AI_QUANTUM","AI":"AI_QUANTUM","SOUN":"AI_QUANTUM","APP":"AI_QUANTUM",
    "IONQ":"AI_QUANTUM","QBTS":"AI_QUANTUM","RGTI":"AI_QUANTUM","BBAI":"AI_QUANTUM",
    "CRWV":"AI_QUANTUM","MSFT":"AI_QUANTUM","GOOG":"AI_QUANTUM","GOOGL":"AI_QUANTUM",
    "AAPL":"TECH","META":"TECH","NVO":"BIOTECH",
    # CYBERSEC
    "CRWD":"CYBERSEC","PANW":"CYBERSEC","ZS":"CYBERSEC","FTNT":"CYBERSEC","S":"CYBERSEC",
    "OKTA":"CYBERSEC","CYBR":"CYBERSEC","RBRK":"CYBERSEC","NET":"CYBERSEC",
    # EV / AUTONOMOUS / EV-CLEAN
    "TSLA":"EV","RIVN":"EV","LCID":"EV","NIO":"EV","XPEV":"EV","LI":"EV",
    "ACHR":"AUTONOMOUS","JOBY":"AUTONOMOUS","UBER":"AUTONOMOUS",
    # SPACE / SATELLITES
    "RKLB":"SPACE","ASTS":"SATELLITES","IRDM":"SATELLITES","LUNR":"SPACE",
    "KTOS":"DRONES","AVAV":"DRONES",
    # URANIUM / NUCLEAR
    "CCJ":"URANIUM","NXE":"URANIUM","UUUU":"URANIUM","UEC":"URANIUM","URA":"URANIUM",
    "URNM":"URANIUM","DNN":"URANIUM","LEU":"URANIUM",
    "CEG":"NUCLEAR","VST":"NUCLEAR","SMR":"NUCLEAR","OKLO":"NUCLEAR","NNE":"NUCLEAR",
    "TLN":"NUCLEAR",
    # DEFENSE / AEROSPACE
    "LMT":"DEFENSE","RTX":"DEFENSE","NOC":"DEFENSE","GD":"DEFENSE","LHX":"DEFENSE",
    "HII":"DEFENSE","TDG":"AEROSPACE","BA":"AEROSPACE","HEI":"AEROSPACE",
    # BIOTECH / GENE-EDITING
    "MRNA":"BIOTECH","BNTX":"BIOTECH","VKTX":"BIOTECH","CRSP":"BIOTECH","NTLA":"BIOTECH",
    "BEAM":"BIOTECH","EDIT":"BIOTECH","RXRX":"BIOTECH","RECU":"BIOTECH","DNA":"BIOTECH",
    "SGMO":"BIOTECH","ARCT":"BIOTECH",
    # HOMEBUILDERS
    "DHI":"HOMEBUILDER","LEN":"HOMEBUILDER","NVR":"HOMEBUILDER","PHM":"HOMEBUILDER",
    "TOL":"HOMEBUILDER","TMHC":"HOMEBUILDER","KBH":"HOMEBUILDER","MTH":"HOMEBUILDER",
    "BLDR":"HOMEBUILDER",
    # RESIDENTIAL REITs / STORAGE
    "AMH":"REIT","INVH":"REIT","ESS":"REIT","AVB":"REIT","EQR":"REIT","UDR":"REIT",
    "MAA":"REIT","PSA":"REIT","EXR":"REIT","CUBE":"REIT","WELL":"REIT",
    # WATER UTILS
    "AWK":"WATER_UTIL","WTRG":"WATER_UTIL","ARTNA":"WATER_UTIL","CWT":"WATER_UTIL",
    "YORW":"WATER_UTIL","AWR":"WATER_UTIL",
    # FOOD / BEVERAGE / STAPLES
    "KO":"FOOD_BEV","PEP":"FOOD_BEV","GIS":"FOOD_BEV","K":"FOOD_BEV","CPB":"FOOD_BEV",
    "KHC":"FOOD_BEV","HSY":"FOOD_BEV","MDLZ":"FOOD_BEV","MKC":"FOOD_BEV","SJM":"FOOD_BEV",
    "TSN":"FOOD_BEV","HRL":"FOOD_BEV","KDP":"FOOD_BEV","STZ":"FOOD_BEV","TAP":"FOOD_BEV",
    "PG":"STAPLES","CL":"STAPLES","COST":"STAPLES","WMT":"STAPLES","KR":"STAPLES",
    # HOSPITALITY / LEISURE
    "MAR":"HOSPITALITY","HLT":"HOSPITALITY","H":"HOSPITALITY","CCL":"HOSPITALITY",
    "NCLH":"HOSPITALITY","RCL":"HOSPITALITY","WYNN":"HOSPITALITY","LVS":"HOSPITALITY",
    "MGM":"HOSPITALITY",
    # STREAMING / ENTERTAINMENT / CREATOR
    "NFLX":"STREAMING","DIS":"ENTERTAINMENT","SPOT":"STREAMING","RBLX":"CREATOR_ECONOMY",
    "PINS":"MEDIA","SNAP":"MEDIA","ROKU":"STREAMING","FUBO":"STREAMING","DKNG":"GAMBLING",
    "FLUT":"GAMBLING","PENN":"GAMBLING",
    # LUXURY
    "LVMUY":"LUXURY","RL":"LUXURY","TPR":"LUXURY","DECK":"LUXURY","BIRK":"LUXURY",
    "LULU":"LUXURY","CROX":"RETAIL","ULTA":"RETAIL","EL":"LUXURY",
    # GOLD / PRECIOUS METALS
    "GLD":"PRECIOUS_METALS","GDX":"PRECIOUS_METALS","NEM":"PRECIOUS_METALS","GOLD":"PRECIOUS_METALS",
    "AEM":"PRECIOUS_METALS","AU":"PRECIOUS_METALS","KGC":"PRECIOUS_METALS","SLV":"PRECIOUS_METALS",
    "FCX":"METALS","VALE":"METALS","X":"METALS","NUE":"METALS","STLD":"METALS",
    # FOSSIL FUEL (afflicted by Neptune-Aries)
    "XOM":"FOSSIL","CVX":"FOSSIL","SHEL":"FOSSIL","BP":"FOSSIL","COP":"FOSSIL",
    "EOG":"FOSSIL","PSX":"FOSSIL","VLO":"FOSSIL","MPC":"FOSSIL","OXY":"FOSSIL",
    "DVN":"FOSSIL","APA":"FOSSIL","HES":"FOSSIL","FANG":"FOSSIL",
    # CRYPTO
    "MSTR":"CRYPTO","COIN":"CRYPTO","MARA":"CRYPTO","RIOT":"CRYPTO","CLSK":"CRYPTO",
    "HUT":"CRYPTO",
    # MEME
    "GME":"MEME","AMC":"MEME","BBBY":"MEME","KOSS":"MEME",
    # FINANCE
    "JPM":"FINANCE","GS":"FINANCE","MS":"FINANCE","C":"FINANCE","BAC":"FINANCE",
    "WFC":"FINANCE","BX":"FINANCE","KKR":"FINANCE","IVZ":"FINANCE","IBKR":"FINANCE",
    "TPG":"FINANCE","HOOD":"FINANCE","SOFI":"FINANCE","UPST":"FINANCE","AFRM":"FINANCE",
    "COIN":"CRYPTO",
}

def modern_sector_of(ticker, sector_base):
    tk = ticker.upper()
    if tk in MODERN_SECTOR:
        return MODERN_SECTOR[tk]
    # Fall back from base sector to macro-regime key
    fallback = {"TECH":"TECH","FINANCE":"FINANCE","RETAIL":"RETAIL","ENERGY":"ENERGY",
                "EV":"EV","CRYPTO":"CRYPTO","MEME":"MEME","BIOPHARM":"BIOTECH",
                "METALS":"METALS","REIT":"REIT","UTILS":"UTILS",
                "HEALTH":"HEALTH","MEDIA":"MEDIA","INDUSTRIAL":"INDUSTRIAL",
                "MATERIALS":"METALS","CANNABIS":"CANNABIS"}
    return fallback.get(sector_base, "UNK")

def score_snapshot_v24(natal, y, m, db, sector_base, modern_sec):
    trans = transits_at(y, m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best
    # sector-aware bucket + dignity
    single_score = 0
    for p, o in outer_orbs.items():
        w = sector_bucket_weight(p, o, sector_base)
        dig = dignity_multiplier(p, trans[p]["lon"])
        single_score += w * dig
    compound = sum(w for label, fn, w in COMPOUND_RULES if fn(outer_orbs))
    jup_natNep = closest_hard(trans["Jupiter"]["lon"], natal["Neptune"]["lon"])
    nep_sun = closest_hard(trans["Neptune"]["lon"], natal["Sun"]["lon"])
    nep_mc = closest_hard(trans["Neptune"]["lon"], natal["MC"]["lon"]) if "MC" in natal else 99
    jd_c = jd_of(y, m, 15, 12.0)
    hits = eclipse_hits_natal(db, natal, jd_c, months_back=18, months_fwd=3, max_orb=3)
    eclipse = 0
    for h in hits:
        tw = 1.5 if "total" in h["eclipse_type"] else (1.0 if "partial" in h["eclipse_type"] or "annular" in h["eclipse_type"] else 0.5)
        eclipse += tw * (3 - h["orb"]) / 3
    bubblish = 0
    if jup_natNep <= 3:     bubblish += 2.5 * (3 - jup_natNep) / 3
    elif jup_natNep <= 6:   bubblish += 1.0 * (6 - jup_natNep) / 6
    if nep_sun <= 3:        bubblish += 2.0 * (3 - nep_sun) / 3
    if nep_mc <= 3:         bubblish += 1.5 * (3 - nep_mc) / 3
    n_close = sum(1 for o in outer_orbs.values() if o <= 5)
    if n_close >= 3:        bubblish += 1.0
    if 8 <= outer_orbs["Pluto"] < 12:   bubblish += 1.5
    if 3 <= outer_orbs["Uranus"] < 5:   bubblish += 1.2

    pre_macro = single_score + compound * 1.5 + eclipse * 1.3 + bubblish * 1.2
    macro_mult = macro_regime_multiplier(modern_sec, y, m)
    composite = pre_macro * macro_mult
    return {"composite": composite, "pre_macro": pre_macro, "macro_mult": macro_mult,
            "single": single_score, "compound": compound, "eclipse": eclipse,
            "bubblish": bubblish,
            "jup_natNep": jup_natNep, "nep_sun": nep_sun, "nep_mc": nep_mc,
            "outer_orbs": outer_orbs}

def forward_v24(natal, sy, sm, db, sector_base, modern_sec, months=24):
    traj = []
    for k in range(0, months+1):
        y, m = yx(sy, sm, k)
        traj.append({"k":k,"y":y,"m":m,**score_snapshot_v24(natal,y,m,db,sector_base,modern_sec)})
    peak = max(traj, key=lambda s:s["composite"])
    cur = traj[0]
    bpk = max(traj, key=lambda s:s["bubblish"])
    sat_pop = saturn_pop_month(natal, sy, sm, months)
    runway = peak["k"]
    safe = sat_pop is None or sat_pop > runway+2
    return {"cur":cur,"peak":peak,"bpk":bpk,"traj":traj,
            "runway":runway,"sat_pop":sat_pop,"safe":safe,
            "imp":peak["composite"]-cur["composite"],
            "bub_imp":bpk["bubblish"]-cur["bubblish"]}

def main():
    print("Building eclipse DB...", file=sys.stderr)
    db = build_eclipse_database(1970, 2035)

    seeds = []
    with open("/home/user/cyclepapa/data/universe_bti_v20.csv") as f:
        for r in csv.DictReader(f):
            tk = (r.get("ticker") or "").strip().upper()
            ipo = (r.get("ipo") or "").strip()
            name = (r.get("name") or "").strip()
            src = (r.get("source") or "").strip()
            if not tk or not ipo or len(ipo) < 10: continue
            try: y = int(ipo[:4])
            except: continue
            age = START_Y - y
            if not (1 <= age <= 40): continue
            seeds.append({"tk":tk,"ipo":ipo,"name":name,"src":src,"age":age})
    seen = set(); unique = []
    for s in seeds:
        k = (s["tk"], s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Universe: {len(unique)}", file=sys.stderr)

    t0 = time.time()
    rows = []
    for i, s in enumerate(unique):
        if i and i % 1000 == 0:
            print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s", file=sys.stderr)
        sec_base = get_sector(s["tk"], s["src"])
        mod_sec = modern_sector_of(s["tk"], sec_base)
        try:
            natal = compute_natal(s["ipo"])
            fa = forward_v24(natal, START_Y, START_M, db, sec_base, mod_sec, MONTHS)
            now = fa["cur"]["composite"]; peak = fa["peak"]["composite"]
            imp = fa["imp"]; bpk = fa["bpk"]["bubblish"]
            if fa["runway"] < 1: continue
            if imp < 5.0: continue
            if bpk < 2.0: continue
            if now >= 20.0: continue
            if not fa["safe"]: continue
            run = fa["runway"]
            rb = 1.0 if 3 <= run <= 12 else 0.7
            asym = (imp**0.9)*(bpk**1.0)*rb/((now+3)**0.5)
            pk_d = fa["peak"]; bb_d = fa["bpk"]
            rows.append({"tk":s["tk"],"name":s["name"],"src":s["src"],
                         "sector":sec_base,"modern":mod_sec,"ipo":s["ipo"],"age":s["age"],
                         "now":now,"peak":peak,"imp":imp,
                         "peak_mo":f"{pk_d['y']}-{pk_d['m']:02d}",
                         "runway":run,"sat_pop":fa["sat_pop"],
                         "bub_now":fa["cur"]["bubblish"],"bub_peak":bpk,
                         "macro_peak":pk_d["macro_mult"],
                         "macro_now":fa["cur"]["macro_mult"],
                         "asym":asym,
                         "jup_natNep":pk_d["jup_natNep"],
                         "nep_sun":pk_d["nep_sun"],"nep_mc":pk_d["nep_mc"]})
        except:
            continue
    print(f"Scan done: {time.time()-t0:.0f}s, kept {len(rows)}", file=sys.stderr)

    rows.sort(key=lambda r: -r["asym"])

    out = "/home/user/cyclepapa/data/universe_macro_v24.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank","ticker","name","sector","modern_sector","source","ipo","age",
                    "asymmetry","score_now","score_peak","improvement",
                    "peak_month","runway_mo","saturn_pop","bubblish_now","bubblish_peak",
                    "macro_now","macro_peak",
                    "peak_jup_natNep","peak_nep_sun","peak_nep_mc"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["tk"], r["name"], r["sector"], r["modern"], r["src"],
                        r["ipo"], r["age"],
                        f"{r['asym']:.3f}", f"{r['now']:.2f}", f"{r['peak']:.2f}",
                        f"{r['imp']:+.2f}", r["peak_mo"], r["runway"],
                        r["sat_pop"] if r["sat_pop"] is not None else "",
                        f"{r['bub_now']:.2f}", f"{r['bub_peak']:.2f}",
                        f"{r['macro_now']:.2f}", f"{r['macro_peak']:.2f}",
                        f"{r['jup_natNep']:.2f}", f"{r['nep_sun']:.2f}", f"{r['nep_mc']:.2f}"])
    print(f"Exported {len(rows)} -> {out}")

if __name__ == "__main__":
    main()
