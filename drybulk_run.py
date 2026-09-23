"""Dry bulk sector run: sector-key loading + convergence + M&A signature.

Rulers for dry bulk (compendium: Shipping -> Neptune/Moon/9th, marine):
  Neptune  modern     marine/oceans
  Moon     classical  Ptolemy: sailors, waters, the public
  Mercury  modern     transport/commerce
  Saturn   contested  heavy cargo / commodities carriage
Cohort = Ritter dry-bulk IPOs + curated extras (confidence-tagged).
"""
import sys, json, os
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, ".")
import swisseph as swe
from reverse_arch_v8_1_asymmetry import SIGNS, hard_asp, orb
from sector_screener import natal, natal_sector_load

RULERS = [("Neptune","modern","marine"),("Moon","classical","sailors"),
          ("Mercury","modern","transport"),("Saturn","contested","cargo")]
COHORT = [
 ("DRYS","DryShips","2005-02-03","ritter","delisted 2019"),
 ("DSX","Diana Shipping","2005-03-17","ritter","listed"),
 ("EGLE","Eagle Bulk","2005-06-22","ritter","acq Star Bulk 2024"),
 ("QMAR","Quintana Maritime","2005-07-14","ritter","acq Excel 2008 premium"),
 ("GNK","Genco Shipping","2005-07-21","ritter","listed (post-2014 reorg)"),
 ("PRGN","Paragon Shipping","2007-08-09","ritter","dead"),
 ("NMM","Navios Partners","2007-11-12","ritter","listed"),
 ("SB","Safe Bulkers","2008-05-28","ritter","listed"),
 ("DWT","Britannia Bulk","2008-06-18","ritter","bankrupt 2008"),
 ("BALT","Baltic Trading","2010-03-09","ritter","merged into GNK 2015"),
 ("SBLK","Star Bulk","2007-12-03","extra-low","listed; serial acquirer"),
 ("SALT","Scorpio Bulkers","2013-12-12","extra-med","became Eneti/absorbed"),
 ("GRIN","Grindrod Shipping","2018-06-19","extra-med","Taylor Maritime tender 2022"),
 ("EDRY","EuroDry","2018-05-30","extra-low","listed micro"),
 ("CTRM","Castor Maritime","2019-02-11","extra-low","listed micro"),
 ("PANL","Pangaea Logistics","2014-10-01","extra-low","listed"),
 ("GOGL","Golden Ocean (US)","2015-04-01","extra-low","listed"),
 ("HSHP","Himalaya Shipping","2023-04-04","extra-med","listed"),
]
TODAY = date.fromisoformat(os.environ.get("RA_ASOF","2026-09-23"))
END = date(2028,9,30)
events = json.loads(Path("/home/claude/forward_events.json").read_text())
ecl = [e for e in events["eclipses"] if TODAY.isoformat() < e["date"] <= END.isoformat()]

samples=[]; d=TODAY
while d<=END:
    jd=swe.julday(d.year,d.month,d.day,13.5)
    samples.append((d,{n:swe.calc_ut(jd,p)[0][0]%360 for n,p in
      [("Pluto",swe.PLUTO),("Uranus",swe.URANUS),("Neptune",swe.NEPTUNE),
       ("Saturn",swe.SATURN),("Jupiter",swe.JUPITER)]}))
    d+=timedelta(days=10)

ECL_BASE={"total_solar":10,"annular_solar":8,"partial_solar":5,"solar":5,
          "total_lunar":4,"partial_lunar":3,"penumbral_lunar":2}
def acq(sun):
    tot=0; hits=[]
    for e in ecl:
        r=hard_asp(e["lon"],sun,1.5)
        if not r or r[0]=="sq": continue
        base=next((v for k,v in ECL_BASE.items() if e["type"].startswith(k)),3)
        pts=base*(1.5-r[1])/1.5*(1.1 if r[0]=="conj" else 1.0)
        if r[1]<=0.75: pts*=1.4
        ed=date.fromisoformat(e["date"])
        for nm,pid,m in (("Pluto",swe.PLUTO,1.6),("Saturn",swe.SATURN,1.25),("Neptune",swe.NEPTUNE,1.15)):
            jd=swe.julday(ed.year,ed.month,ed.day,12)
            if hard_asp(swe.calc_ut(jd,pid)[0][0]%360,sun,1.5): pts*=m
        tot+=pts; hits.append(f"{e['date']} {e['type'][:12]} {r[0]}Sun {r[1]:.2f}")
    return tot,hits

print(f"as_of={TODAY}  cohort={len(COHORT)}  eclipses={len(ecl)}")
rows=[]
for tk,nm,dt,src,status in COHORT:
    ch=natal(dt)
    load,detail,loaded=natal_sector_load(ch,RULERS)
    fuel=1+min(load,3)
    rulers=[p for p,_,_ in RULERS]
    tgt={t:ch[t]["lon"] for t in dict.fromkeys(["Sun","Venus","Jupiter"]+rulers)}
    def w(t): return 2.0 if t in loaded else (1.5 if t in rulers else 1.0)
    slow=[];fast=[]
    for _d,pos in samples:
        slow.append({f"{pn}>{t}" for pn in ("Pluto","Uranus","Neptune") for t,l in tgt.items() if pn!=t and hard_asp(pos[pn],l,1.5)})
        fast.append({f"Jup>{t}" for t,l in tgt.items() if hard_asp(pos["Jupiter"],l,1.2)})
    best=None; W=9
    for i in range(len(samples)-W+1):
        js=range(i,i+W)
        ss=set().union(*(slow[j] for j in js)); fs=set().union(*(fast[j] for j in js))
        if not ss or not fs: continue
        conv=sum(w(h.split(">")[1]) for h in ss)+sum(w(h.split(">")[1]) for h in fs)
        if best is None or conv>best[0]: best=(conv,samples[i+W//2][0],sorted(ss),sorted(fs))
    a,ahits=acq(ch["Sun"]["lon"])
    conv,center,ss,fs=(best if best else (0,None,[],[]))
    rows.append(dict(tk=tk,nm=nm,dt=dt,status=status,load=round(load,2),
      loaded="/".join(sorted(loaded)) or "-",
      setup=round((conv or 0)*fuel,1),
      peak=center.isoformat() if center else "-",
      pos_by=(center-timedelta(days=42)).isoformat() if center else "-",
      subst="/".join(ss)[:60], trig="/".join(fs)[:40],
      acq=round(a,1), acq_sig="; ".join(ahits)[:80],
      detail="; ".join(detail)[:90]))
rows.sort(key=lambda r:-r["setup"])
for r in rows:
    print(f"\n{r['tk']:<6s}{r['nm']:<20s}{r['dt']}  [{r['status']}]")
    print(f"   load={r['load']:<5} loaded={r['loaded']:<22s} SETUP={r['setup']:<6} peak={r['peak']} pos_by={r['pos_by']}")
    print(f"   {r['subst']} + {r['trig']}")
    print(f"   natal: {r['detail']}")
    if r['acq']>0: print(f"   ACQ={r['acq']}  {r['acq_sig']}")
