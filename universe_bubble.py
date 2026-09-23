"""Universe-wide BUBBLE screen: explosive melt-up chemistry, all tickers."""
import sys, json, os, csv
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,".")
import swisseph as swe
from reverse_arch_v8_1_asymmetry import hard_asp, orb, load_ipos, DEFAULT_ALREADY, is_already_cult, is_shell
from sector_screener import natal

TODAY=date.fromisoformat(os.environ.get("RA_ASOF","2026-09-23")); END=date(2028,9,30)
ev=json.loads(Path("/home/claude/forward_events.json").read_text())
ecl=[(date.fromisoformat(e["date"]),e["lon"],e["type"]) for e in ev["eclipses"] if TODAY.isoformat()<e["date"]<=END.isoformat()]
def tightf(o,mx):
    v=((mx-o)/mx)**2
    return v*2 if o<=0.5 else v
# precompute sky
sky=[]; d=TODAY
while d<=END:
    jd=swe.julday(d.year,d.month,d.day,12)
    sky.append((d,swe.calc_ut(jd,swe.JUPITER)[0][0]%360,swe.calc_ut(jd,swe.URANUS)[0][0]%360))
    d+=timedelta(days=10)

ipos=load_ipos(None,"/home/claude/ritter_full.csv",[])
if len(ipos)<100: raise SystemExit("universe collapsed")
rows=[]
for ipo in ipos:
    if is_already_cult(ipo["ticker"],ipo["date"],DEFAULT_ALREADY) or is_shell(ipo.get("name","")): continue
    try: ch=natal(ipo["date"])
    except Exception: continue
    fuel=1.0; fu=[]
    for a,b,w,tag in (("Jupiter","Neptune",1.2,"JupNep"),("Jupiter","Uranus",1.0,"JupUra"),("Moon","Neptune",0.6,"MooNep")):
        r=hard_asp(ch[a]["lon"],ch[b]["lon"],3.0)
        if r: fuel+=w*tightf(r[1],3.0); fu.append(f"{tag}{r[0][:1]}{r[1]:.2f}")
    if fuel<1.3: continue   # bubble needs natal mania fuel; skip unfueled
    # trigger days: distinct aspect types with best weight in 60d window
    days=[]
    for d,tj,tu in sky:
        s={}
        r=hard_asp(tj,ch["Uranus"]["lon"],1.5)
        if r: s["JU"]=2.0*(1.5-r[1])/1.5
        r=hard_asp(tu,ch["Jupiter"]["lon"],1.5)
        if r: s["UJ"]=2.5*(1.5-r[1])/1.5
        if abs(orb(tj,ch["Neptune"]["lon"])-120)<=1.2: s["JtN"]=1.0
        days.append([d,s])
    for ed,el,et in ecl:
        for tgt,w in (("Jupiter",2.5),("Uranus",2.5)):
            r=hard_asp(el,ch[tgt]["lon"],2.0)
            if r:
                i=min(range(len(days)),key=lambda k:abs((days[k][0]-ed).days))
                key=f"E{tgt[:1]}"
                days[i][1][key]=max(days[i][1].get(key,0),w*(2.0-r[1])/2.0*(1.6 if "total_solar" in et else 1.0))
    best=(0,None,{})
    W=6
    for i in range(len(days)-W+1):
        agg={}
        for j in range(i,i+W):
            for k,v in days[j][1].items(): agg[k]=max(agg.get(k,0),v)
        tot=sum(agg.values())
        if tot>best[0]: best=(tot,days[i+W//2][0],agg)
    if best[0]<=0: continue
    yr=int(ipo["date"][:4])
    rows.append({"ticker":ipo["ticker"],"name":ipo.get("name","").strip('"'),"date":ipo["date"],
      "era":"2017+" if yr>=2017 else ("2010-16" if yr>=2010 else "old"),
      "bubble":round(fuel*best[0],2),"fuel":round(fuel,2),"natal":"/".join(fu),
      "window":best[1].isoformat(),"pos_by":(best[1]-timedelta(days=42)).isoformat(),
      "trigger":"/".join(f"{k}:{v:.1f}" for k,v in sorted(best[2].items()))})
rows.sort(key=lambda r:-r["bubble"])
with open("/mnt/user-data/outputs/universe_bubble.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"fueled+triggered: {len(rows)}")
seen=set()
for r in rows:
    if r["date"] in seen: continue
    seen.add(r["date"])
    if len(seen)>22: break
    print(f"{r['ticker']:<7s}{r['name'][:24]:<24s}{r['date']} [{r['era']:<7s}] BUBBLE={r['bubble']:<6} fuel={r['fuel']:<5} [{r['natal']}] win={r['window']} pos_by={r['pos_by']} {r['trigger']}")
