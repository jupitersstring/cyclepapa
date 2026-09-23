"""Dry-bulk BUBBLE screen: explosive-melt-up signature, not durable setups.

Bubble chemistry (engine + Silas + GME/DRYS precedents):
  NATAL  Jupiter-Neptune hard (mania fuel)   | Jupiter-Uranus hard (spec shock)
         Moon-Neptune hard (retail dream)    | tightness quadratic, <=0.5 doubled
  TRIGGER (next 24m, 60-day window): eclipse hard natal Jupiter or Uranus
         (Silas: 'eclipses can make stocks surge out of nowhere') and/or
         T.Jupiter hard natal Uranus / T.Uranus hard natal Jupiter -- the
         detonator pair -- plus T.Jupiter trine natal Neptune (one-day-wonder).
  bubble = natal_fuel x max 60d trigger stack
"""
import sys, json, os
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,".")
import swisseph as swe
from reverse_arch_v8_1_asymmetry import hard_asp, orb
from sector_screener import natal

COHORT=[("DRYS","2005-02-03","dead"),("DSX","2005-03-17","listed"),("EGLE","2005-06-22","acq'd"),
 ("QMAR","2005-07-14","acq'd"),("GNK","2005-07-21","listed"),("PRGN","2007-08-09","dead"),
 ("NMM","2007-11-12","listed"),("SB","2008-05-28","listed"),("DWT","2008-06-18","dead"),
 ("BALT","2010-03-09","merged"),("SBLK","2007-12-03","listed*"),("SALT","2013-12-12","absorbed"),
 ("GRIN","2018-06-19","tendered"),("EDRY","2018-05-30","listed"),("CTRM","2019-02-11","listed"),
 ("PANL","2014-10-01","listed*"),("GOGL","2015-04-01","listed*"),("HSHP","2023-04-04","listed")]
TODAY=date.fromisoformat(os.environ.get("RA_ASOF","2026-09-23")); END=date(2028,9,30)
ev=json.loads(Path("/home/claude/forward_events.json").read_text())
ecl=[e for e in ev["eclipses"] if TODAY.isoformat()<e["date"]<=END.isoformat()]

def tightf(o,mx): 
    v=((mx-o)/mx)**2
    return v*2 if o<=0.5 else v

rows=[]
for tk,dt,st in COHORT:
    ch=natal(dt)
    fuel=1.0; fu=[]
    for a,b,wgt,tag in (("Jupiter","Neptune",1.2,"JupNep"),("Jupiter","Uranus",1.0,"JupUra"),("Moon","Neptune",0.6,"MooNep")):
        r=hard_asp(ch[a]["lon"],ch[b]["lon"],3.0)
        if r: fuel+=wgt*tightf(r[1],3.0); fu.append(f"{tag}-{r[0]}{r[1]:.2f}")
    # 60-day rolling trigger stack
    best=(0,None,[])
    d=TODAY
    days=[]
    while d<=END:
        jd=swe.julday(d.year,d.month,d.day,12)
        tj=swe.calc_ut(jd,swe.JUPITER)[0][0]%360; tu=swe.calc_ut(jd,swe.URANUS)[0][0]%360
        s=[]
        r=hard_asp(tj,ch["Uranus"]["lon"],1.5)
        if r: s.append((2.0,f"T.Jup-{r[0]}-nUra{r[1]:.1f}"))
        r=hard_asp(tu,ch["Jupiter"]["lon"],1.5)
        if r: s.append((2.5,f"T.Ura-{r[0]}-nJup{r[1]:.1f}"))
        tri=abs(orb(tj,ch["Neptune"]["lon"])-120)
        if tri<=1.2: s.append((1.0,f"T.Jup-tri-nNep{tri:.1f}"))
        days.append((d,s))
        d+=timedelta(days=10)
    for ed_,el,et in [(date.fromisoformat(e["date"]),e["lon"],e["type"]) for e in ecl]:
        for tgt,wgt in (("Jupiter",2.5),("Uranus",2.5)):
            r=hard_asp(el,ch[tgt]["lon"],2.0)
            if r:
                i=min(range(len(days)),key=lambda k:abs((days[k][0]-ed_).days))
                days[i][1].append((wgt*(2.0-r[1])/2.0,f"ECL{ed_.isoformat()[:7]}-{r[0]}-n{tgt[:3]}{r[1]:.1f}"))
    W=6
    for i in range(len(days)-W+1):
        seen={}
        for j in range(i,i+W):
            for w,tag in days[j][1]: seen[tag.split("{")[0]]=max(seen.get(tag,0),w) if False else max(seen.get(tag,0),w)
        tot=sum(seen.values())
        if tot>best[0]: best=(tot,days[i+W//2][0],sorted(seen))
    bub=round(fuel*best[0],2)
    rows.append((bub,tk,dt,st,round(fuel,2),"/".join(fu) or "-",best))
rows.sort(key=lambda r:-r[0])
print(f"as_of={TODAY}")
for bub,tk,dt,st,fuel,fu,best in rows:
    tot,center,tags=best
    print(f"{tk:<6s}{dt} [{st:<8s}] BUBBLE={bub:<6} fuel={fuel:<5} natal[{fu}]")
    if center: print(f"       trigger-window ~{center.isoformat()}  stack={tot:.1f}  {tags}")
