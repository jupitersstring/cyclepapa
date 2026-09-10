"""
v23 — SECTOR-AWARE asymmetric forward scanner.

Each ticker gets a SECTOR label (from SP500 GICS, manual map, or inferred).
Sector-conditional WEIGHT MULTIPLIERS scale v19 single-planet bucket weights:
the empirically-dominant planet at bottom for each sector gets upweighted,
the weakest gets downweighted.

Empirical sector-planet strength at BOTTOM (from sector_astro.py on 152 cases):
  TECH       Saturn 1.6, Pluto 1.4, Jupiter 1.0, Uranus 0.9, Neptune 0.9
  BIOPHARM   Pluto 2.0,  Saturn 1.3, Jupiter 1.3, Uranus 0.8, Neptune 0.6
  EV         Uranus 2.0, Saturn 1.2, Jupiter 1.0, Neptune 1.0, Pluto 0.8
  ENERGY     Jupiter 1.6,Pluto 1.3,  Saturn 1.3, Uranus 0.8, Neptune 0.9
  FINANCE    Pluto 2.0,  Neptune 1.4,Jupiter 1.3,Uranus 0.7, Saturn 0.7
  MEME       Pluto 2.3,  Saturn 1.7, Jupiter 0.6,Uranus 0.9, Neptune 1.0
  CRYPTO     Jupiter 1.5,Uranus 1.3, Neptune 1.0,Saturn 0.9, Pluto 0.8
  CANNABIS   Pluto 1.8,  Uranus 1.6, Jupiter 1.1,Saturn 0.6, Neptune 0.4
  RETAIL     Jupiter 1.5,Pluto 1.4,  Uranus 1.2, Saturn 0.8, Neptune 0.7
  METALS     Pluto 1.6,  Saturn 1.4, Jupiter 1.0,Uranus 0.9, Neptune 0.8
  REIT       Saturn 1.6, Jupiter 1.3,Pluto 1.0,  Uranus 0.8, Neptune 0.8
  UTILS      Saturn 1.6, Jupiter 1.2,Neptune 1.0,Pluto 1.0,  Uranus 0.8
  HEALTH     Pluto 1.6,  Jupiter 1.3,Saturn 1.2, Uranus 0.9, Neptune 0.9
  INDUSTRIAL Saturn 1.3, Jupiter 1.2,Pluto 1.1,  Uranus 1.0, Neptune 0.9
  UNK        all 1.0     (neutral)
"""
import math, csv, sys, time, re
from bti_test import compute_natal, transits_at, jd_of
from bti_v4 import yx
from eclipse_database import build_eclipse_database, eclipse_hits_natal
from bti_v19_empirical import SINGLE_PLANET_WEIGHTS, COMPOUND_RULES, bucket_weight, closest_hard, orb
from bti_v21_forward import saturn_pop_month
from sector_astro import SECTOR as CORPUS_SECTOR  # parabolic corpus manual sectors

START_Y, START_M = 2026, 4
MONTHS = 24

SECTOR_WEIGHTS = {
    "TECH":     {"Jupiter":1.0,"Saturn":1.6,"Uranus":0.9,"Neptune":0.9,"Pluto":1.4},
    "BIOPHARM": {"Jupiter":1.3,"Saturn":1.3,"Uranus":0.8,"Neptune":0.6,"Pluto":2.0},
    "EV":       {"Jupiter":1.0,"Saturn":1.2,"Uranus":2.0,"Neptune":1.0,"Pluto":0.8},
    "ENERGY":   {"Jupiter":1.6,"Saturn":1.3,"Uranus":0.8,"Neptune":0.9,"Pluto":1.3},
    "FINANCE":  {"Jupiter":1.3,"Saturn":0.7,"Uranus":0.7,"Neptune":1.4,"Pluto":2.0},
    "MEME":     {"Jupiter":0.6,"Saturn":1.7,"Uranus":0.9,"Neptune":1.0,"Pluto":2.3},
    "CRYPTO":   {"Jupiter":1.5,"Saturn":0.9,"Uranus":1.3,"Neptune":1.0,"Pluto":0.8},
    "CANNABIS": {"Jupiter":1.1,"Saturn":0.6,"Uranus":1.6,"Neptune":0.4,"Pluto":1.8},
    "RETAIL":   {"Jupiter":1.5,"Saturn":0.8,"Uranus":1.2,"Neptune":0.7,"Pluto":1.4},
    "METALS":   {"Jupiter":1.0,"Saturn":1.4,"Uranus":0.9,"Neptune":0.8,"Pluto":1.6},
    "REIT":     {"Jupiter":1.3,"Saturn":1.6,"Uranus":0.8,"Neptune":0.8,"Pluto":1.0},
    "UTILS":    {"Jupiter":1.2,"Saturn":1.6,"Uranus":0.8,"Neptune":1.0,"Pluto":1.0},
    "HEALTH":   {"Jupiter":1.3,"Saturn":1.2,"Uranus":0.9,"Neptune":0.9,"Pluto":1.6},
    "INDUSTRIAL":{"Jupiter":1.2,"Saturn":1.3,"Uranus":1.0,"Neptune":0.9,"Pluto":1.1},
    "MEDIA":    {"Jupiter":1.2,"Saturn":1.0,"Uranus":1.0,"Neptune":1.4,"Pluto":1.1},
    "UNK":      {"Jupiter":1.0,"Saturn":1.0,"Uranus":1.0,"Neptune":1.0,"Pluto":1.0},
}

# GICS -> internal sector
GICS = {
    "Information Technology": "TECH",
    "Communication Services": "MEDIA",
    "Consumer Discretionary": "RETAIL",
    "Consumer Staples":       "RETAIL",
    "Energy":                 "ENERGY",
    "Financials":             "FINANCE",
    "Health Care":            "HEALTH",
    "Industrials":            "INDUSTRIAL",
    "Materials":              "METALS",
    "Real Estate":            "REIT",
    "Utilities":              "UTILS",
}

# Sub-industry keyword overrides (finer than GICS sector)
SUBIND_RULES = [
    (r"Biotech|Pharmaceutical", "BIOPHARM"),
    (r"Automobile Manufacturer|Auto Manufacturer|Electric Vehicle", "EV"),
    (r"Semiconductor|Software|Systems Software|Application Software|Internet", "TECH"),
    (r"Oil|Gas|Coal|Petroleum|Uranium", "ENERGY"),
    (r"Investment Bank|Asset Management|Capital Markets|Diversified Banks|Regional Banks|Consumer Finance|Insurance", "FINANCE"),
    (r"Homebuilding|Building Products|Aerospace|Construction|Electrical", "INDUSTRIAL"),
    (r"Apparel Retail|Broadline Retail|Restaurants|Casinos|Leisure|Hotel|Resorts|Apparel|Footwear|Luxury|Household|Personal Care|Cosmetics", "RETAIL"),
    (r"Interactive Media|Entertainment|Movie|Broadcasting|Publishing|Cable", "MEDIA"),
    (r"Gold|Silver|Copper|Mining|Metals", "METALS"),
    (r"Electric Utilit|Multi-Utilit|Water Utilit|Gas Utilit|Nuclear|Independent Power", "UTILS"),
    (r"REIT|Real Estate", "REIT"),
]

def load_sp500_sectors():
    """Return dict ticker -> (sector_internal, gics_sub)"""
    out = {}
    try:
        with open("/home/user/cyclepapa/data/sp500.csv") as f:
            rr = csv.DictReader(f)
            for r in rr:
                tk = r["Symbol"].strip().upper()
                gsec = (r.get("GICS Sector") or "").strip()
                gsub = (r.get("GICS Sub-Industry") or "").strip()
                # Sub-industry override wins
                sec = None
                for pat, s in SUBIND_RULES:
                    if re.search(pat, gsub, re.I):
                        sec = s; break
                if not sec:
                    sec = GICS.get(gsec, "UNK")
                out[tk] = (sec, gsub)
    except Exception as e:
        print(f"sp500 load fail: {e}", file=sys.stderr)
    return out

SP500_SEC = load_sp500_sectors()

# Additional manual map for tickers I know that aren't in SP500
MANUAL_EXTRA = {
    "RBRK":"TECH","OS":"TECH","INGM":"TECH","ARM":"TECH","KVYO":"TECH",
    "RDDT":"MEDIA","ALAB":"TECH","NBIS":"TECH","CRWV":"TECH",
    "TEAM":"TECH","ZS":"TECH","CRWD":"TECH","DDOG":"TECH","NET":"TECH",
    "SNOW":"TECH","FSLY":"TECH","DOCU":"TECH","TWLO":"TECH","OKTA":"TECH",
    "MDB":"TECH","DT":"TECH","ANET":"TECH","NOW":"TECH","PANW":"TECH",
    "SHOP":"TECH","PLTR":"TECH","APP":"TECH","SOUN":"TECH","IONQ":"TECH",
    "QBTS":"TECH","RGTI":"TECH","RKLB":"TECH","MSTR":"CRYPTO","COIN":"CRYPTO",
    "HOOD":"FINANCE","SOFI":"FINANCE","UPST":"FINANCE","AFRM":"FINANCE","HIMS":"BIOPHARM",
    "DUOL":"TECH","PTON":"RETAIL","ABNB":"RETAIL","DASH":"RETAIL","UBER":"INDUSTRIAL",
    "DKNG":"RETAIL","ROKU":"MEDIA","SNAP":"MEDIA","PINS":"MEDIA","FIVE":"RETAIL",
    "ETSY":"RETAIL","W":"RETAIL","VKTX":"BIOPHARM","MRNA":"BIOPHARM","BNTX":"BIOPHARM",
    "RIVN":"EV","LCID":"EV","NIO":"EV","XPEV":"EV","LI":"EV",
    "OKLO":"ENERGY","NNE":"ENERGY","SMR":"ENERGY","CEG":"ENERGY","VST":"ENERGY",
    "URA":"ENERGY","CCJ":"ENERGY","NXE":"ENERGY","GEV":"ENERGY","TPL":"ENERGY",
    "AMC":"RETAIL","GME":"RETAIL","KSS":"RETAIL","BBBY":"RETAIL",
    "ABR":"REIT","LPSN":"TECH","SGMO":"BIOPHARM","NVDA":"TECH","TSLA":"EV",
    "META":"MEDIA","NFLX":"MEDIA","GOOG":"MEDIA","GOOGL":"MEDIA",
    "AMZN":"RETAIL","AAPL":"TECH","MSFT":"TECH","AVGO":"TECH","CRM":"TECH",
    "SMCI":"TECH","BX":"FINANCE","KKR":"FINANCE","IBKR":"FINANCE","IVZ":"FINANCE",
    "HBAN":"FINANCE","GS":"FINANCE","JPM":"FINANCE","BAC":"FINANCE","CVNA":"RETAIL",
    "CHWY":"RETAIL","LULU":"RETAIL","ULTA":"RETAIL","ELF":"RETAIL","CMG":"RETAIL",
    "DECK":"RETAIL","DKS":"RETAIL","WYNN":"RETAIL","CROX":"RETAIL","BLDR":"INDUSTRIAL",
    "TPG":"FINANCE","KVYO":"TECH","SRBK":"FINANCE","CE":"MATERIALS","WM":"INDUSTRIAL",
    "PARA":"MEDIA","TTD":"MEDIA","FI":"FINANCE","FICO":"FINANCE","KDP":"RETAIL",
    "DVN":"ENERGY","INCY":"BIOPHARM","TER":"TECH","HON":"INDUSTRIAL","CHRW":"INDUSTRIAL",
}

def get_sector(tk, fallback_src=""):
    tk_u = tk.upper()
    # Check parabolic corpus manual (most authoritative for studied names)
    if tk_u in CORPUS_SECTOR:
        return CORPUS_SECTOR[tk_u]
    if tk_u in MANUAL_EXTRA:
        return MANUAL_EXTRA[tk_u]
    if tk_u in SP500_SEC:
        return SP500_SEC[tk_u][0]
    return "UNK"

def sector_bucket_weight(planet, orb_deg, sector):
    base = bucket_weight(planet, orb_deg)
    mult = SECTOR_WEIGHTS.get(sector, SECTOR_WEIGHTS["UNK"])[planet]
    return base * mult

def score_snapshot_sec(natal, y, m, db, sector):
    trans = transits_at(y, m)
    targets = {p: natal[p]["lon"] for p in ("Sun","Moon","ASC","MC") if p in natal}
    outer_orbs = {}
    for outer in ("Jupiter","Saturn","Uranus","Neptune","Pluto"):
        best = 99
        for tlon in targets.values():
            o = closest_hard(trans[outer]["lon"], tlon)
            if o < best: best = o
        outer_orbs[outer] = best
    # Sector-weighted single
    single_score = sum(sector_bucket_weight(p, o, sector) for p, o in outer_orbs.items())
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
    composite = single_score + compound * 1.5 + eclipse * 1.3 + bubblish * 1.2
    return {"composite": composite, "single": single_score, "compound": compound,
            "eclipse": eclipse, "bubblish": bubblish,
            "jup_natNep": jup_natNep, "nep_sun": nep_sun, "nep_mc": nep_mc,
            "outer_orbs": outer_orbs}

def forward_sec(natal, sy, sm, db, sector, months=24):
    traj = []
    for k in range(0, months+1):
        y, m = yx(sy, sm, k)
        traj.append({"k":k,"y":y,"m":m,**score_snapshot_sec(natal,y,m,db,sector)})
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

    # Load universe
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
    seen=set(); unique=[]
    for s in seeds:
        k=(s["tk"],s["ipo"])
        if k in seen: continue
        seen.add(k); unique.append(s)
    print(f"Universe: {len(unique)}", file=sys.stderr)

    t0=time.time()
    rows=[]
    sec_counts={}
    for i, s in enumerate(unique):
        if i and i%1000==0:
            print(f"  {i}/{len(unique)}  {time.time()-t0:.0f}s", file=sys.stderr)
        sector = get_sector(s["tk"], s["src"])
        sec_counts[sector] = sec_counts.get(sector,0)+1
        try:
            natal = compute_natal(s["ipo"])
            fa = forward_sec(natal, START_Y, START_M, db, sector, MONTHS)
            now = fa["cur"]["composite"]
            peak = fa["peak"]["composite"]
            imp = fa["imp"]
            bpk = fa["bpk"]["bubblish"]
            if fa["runway"]<1: continue
            if imp<4.0: continue
            if bpk<2.0: continue
            if now>=18.0: continue
            if not fa["safe"]: continue
            run = fa["runway"]
            rb = 1.0 if 3<=run<=12 else 0.7
            asym = (imp**0.9)*(bpk**1.0)*rb/((now+3)**0.5)
            pk_d = fa["peak"]; bb_d = fa["bpk"]
            rows.append({"tk":s["tk"],"name":s["name"],"src":s["src"],
                         "sector":sector,"ipo":s["ipo"],"age":s["age"],
                         "now":now,"peak":peak,"imp":imp,
                         "peak_mo":f"{pk_d['y']}-{pk_d['m']:02d}",
                         "runway":run,"sat_pop":fa["sat_pop"],
                         "bub_now":fa["cur"]["bubblish"],"bub_peak":bpk,
                         "bub_mo":f"{bb_d['y']}-{bb_d['m']:02d}",
                         "asym":asym,
                         "jup_natNep":pk_d["jup_natNep"],
                         "nep_sun":pk_d["nep_sun"],"nep_mc":pk_d["nep_mc"]})
        except: continue

    print(f"Scan done: {time.time()-t0:.0f}s, kept {len(rows)}", file=sys.stderr)
    print(f"Sector distribution:", file=sys.stderr)
    for s, n in sorted(sec_counts.items(), key=lambda x:-x[1]):
        print(f"  {s:<11s} {n:5d}", file=sys.stderr)

    rows.sort(key=lambda r:-r["asym"])

    # Export
    out="/home/user/cyclepapa/data/universe_sectoraware_v23.csv"
    with open(out,"w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["rank","ticker","name","sector","source","ipo","age",
                    "asymmetry","score_now","score_peak","improvement",
                    "peak_month","runway_mo","saturn_pop","bubblish_now",
                    "bubblish_peak","bubblish_month",
                    "peak_jup_natNep","peak_nep_sun","peak_nep_mc"])
        for i,r in enumerate(rows,1):
            w.writerow([i,r["tk"],r["name"],r["sector"],r["src"],r["ipo"],r["age"],
                        f"{r['asym']:.3f}",f"{r['now']:.2f}",f"{r['peak']:.2f}",
                        f"{r['imp']:+.2f}",r["peak_mo"],r["runway"],
                        r["sat_pop"] if r["sat_pop"] is not None else "",
                        f"{r['bub_now']:.2f}",f"{r['bub_peak']:.2f}",r["bub_mo"],
                        f"{r['jup_natNep']:.2f}",f"{r['nep_sun']:.2f}",f"{r['nep_mc']:.2f}"])
    print(f"Exported {len(rows)} -> {out}")

if __name__ == "__main__":
    main()
