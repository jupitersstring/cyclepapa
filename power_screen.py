"""BULLISH POWER screen: three doctrinally-bullish lenses not yet run.

A. T.Pluto conj natal Sun, applying/multi-pass in horizon (Silas NVDA rule:
   'a big, big growth transit... the literal power the company has')
B. Solar eclipse CONJUNCT natal Sun (power for 6-12 months; conj polarity)
C. Jupiter return (T.Jupiter conj natal Jupiter) with natal Jupiter dignity
"""
import sys, json, os, csv
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0,".")
import swisseph as swe
from reverse_arch_v8_1_asymmetry import hard_asp, orb, load_ipos, DEFAULT_ALREADY, is_already_cult, is_shell, SIGNS
from sector_screener import natal
TODAY=date.fromisoformat(os.environ.get("RA_ASOF","2026-09-23")); END=date(2028,9,30)
ev=json.loads(Path("/home/claude/forward_events.json").read_text())
sol=[(e["date"],e["lon"],e["type"]) for e in ev["eclipses"]
     if "solar" in e["type"] and TODAY.isoformat()<e["date"]<=END.isoformat()]
# Pluto path (monthly)
plu=[]; d=TODAY
while d<=END:
    jd=swe.julday(d.year,d.month,d.day,12)
    plu.append((d,swe.calc_ut(jd,swe.PLUTO)[0][0]%360)); d+=timedelta(days=15)
jup=[]; d=TODAY
while d<=END:
    jd=swe.julday(d.year,d.month,d.day,12)
    jup.append((d,swe.calc_ut(jd,swe.JUPITER)[0][0]%360)); d+=timedelta(days=10)
DOM={"Jupiter":[8,11]}; EXA={"Jupiter":3}
rows=[]
ipos=load_ipos(None,"/home/claude/ritter_full.csv",[])
for ipo in ipos:
    if is_already_cult(ipo["ticker"],ipo["date"],DEFAULT_ALREADY) or is_shell(ipo.get("name","")): continue
    try: ch=natal(ipo["date"])
    except Exception: continue
    score=0; sig=[]
    # A: Pluto conj Sun passes
    passes=[d for d,pl in plu if orb(pl,ch["Sun"]["lon"])<=1.0]
    if passes:
        n=len(passes); score+=4.0+0.5*min(n,6)
        sig.append(f"PLUTO-conj-SUN {passes[0].isoformat()[:7]}..{passes[-1].isoformat()[:7]} ({n}x15d samples)")
    # B: solar eclipse conj Sun
    for ed,el,et in sol:
        r=hard_asp(el,ch["Sun"]["lon"],1.5)
        if r and r[0]=="conj":
            base=3.5 if "total" in et else (2.8 if "annular" in et else 2.0)
            score+=base*(1.5-r[1])/1.5*(1.4 if r[1]<=0.75 else 1.0)
            sig.append(f"SOLAR-ECL-conj-SUN {ed} {r[1]:.2f}")
    # C: Jupiter return with dignity
    jr=[d for d,jl in jup if orb(jl,ch["Jupiter"]["lon"])<=1.2]
    if jr:
        s=int(ch["Jupiter"]["lon"]//30)
        dig=1.6 if s in DOM["Jupiter"] else (1.4 if s==EXA["Jupiter"] else 1.0)
        score+=1.5*dig
        sig.append(f"JUP-RETURN {jr[0].isoformat()[:7]}{' DIGNIFIED('+SIGNS[s]+')' if dig>1 else ''}")
    if score<3.0 or len(sig)<1: continue
    yr=int(ipo["date"][:4])
    rows.append({"ticker":ipo["ticker"],"name":ipo.get("name","").strip('"'),"date":ipo["date"],
      "era":"2017+" if yr>=2017 else ("2010-16" if yr>=2010 else "old"),
      "power":round(score,2),"n_lenses":len(sig),"signals":" | ".join(sig)})
rows.sort(key=lambda r:(-r["n_lenses"],-r["power"]))
Path("/mnt/user-data/outputs").mkdir(parents=True,exist_ok=True)
with open("/mnt/user-data/outputs/power_screen.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"qualifying: {len(rows)}")
seen=set()
for r in rows:
    if r["date"] in seen: continue
    seen.add(r["date"])
    if len(seen)>24: break
    print(f"{r['ticker']:<7s}{r['name'][:24]:<24s}{r['date']} [{r['era']:<7s}] POWER={r['power']:<6} x{r['n_lenses']}  {r['signals'][:110]}")
