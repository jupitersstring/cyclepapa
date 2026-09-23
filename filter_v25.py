"""Filter v25 output through tradeable allowlist; report top picks."""
import csv
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def keep(r):
    nm, tk, src = r["name"], r["ticker"], r["source"]
    if not nm or not tk: return False
    if BAD_NAME.search(nm): return False
    if BAD_TICKER.search(tk): return False
    if len(tk) > 5: return False
    return src == "SP500" or tk in CURATED_ACTIVE

rows_all = []
with open("/home/user/cyclepapa/data/universe_v25.csv") as f:
    for r in csv.DictReader(f):
        rows_all.append(r)

rows = [r for r in rows_all if keep(r)]
rows.sort(key=lambda r: -float(r["asymmetry"]))
with open("/home/user/cyclepapa/data/tradeable_v25.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        w.writerow(r)

print(f"{len(rows_all)} total (unfiltered); {len(rows)} tradeable survivors\n")

# ============ TOP 40 OVERALL ============
print("="*185)
print(f"TOP 40 SP500+Ritter ASYMMETRIC (v25 — profection + GC + stations + helio + exit-penalty)")
print("="*185)
print(f"{'#':>3s} {'Tkr':<6s} {'ModSec':<14s} {'Src':<7s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} "
      f"{'Δ':>5s} {'Bub':>4s} {'GC':>4s} {'PkMo':<8s} {'Run':>3s} {'mPk':>4s} {'+Prof':>5s} "
      f"{'+Jst':>5s} {'-Exit':>5s} {'Asym':>5s}  Name")
for i, r in enumerate(rows[:40], 1):
    nm = (r["name"] or "")[:24]
    print(f"{i:3d} {r['ticker']:<6s} {r['modern_sector']:<14s} {r['source']:<7s} "
          f"{int(r['age']):>3d} {float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
          f"{r['improvement']:>5s} {float(r['bubblish_peak']):4.2f} "
          f"{float(r['gc_amplifier']):4.2f} "
          f"{r['peak_month']:<8s} {int(r['runway_mo']):>3d} {float(r['macro_peak']):4.2f} "
          f"{float(r['prof_bonus_now']):5.2f} {float(r['jstn_bonus_now']):5.2f} "
          f"{float(r['exit_penalty']):5.2f} {float(r['asymmetry']):5.2f}  {nm}")

# ============ TOP 20 WITH GC ============
gc_rows = [r for r in rows if float(r["gc_amplifier"]) > 1.0][:20]
print(f"\n{'='*185}")
print(f"TOP 20 WITH NATAL GALACTIC CENTER ≤3° (magnitude-amplified, +40% composite)")
print(f"{'='*185}")
print(f"{'Rk':>3s} {'Tkr':<6s} {'ModSec':<14s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'Bub':>4s} "
      f"{'PkMo':<8s} {'Run':>3s} {'Asym':>5s}  Name")
for i, r in enumerate(gc_rows, 1):
    nm = (r["name"] or "")[:35]
    print(f"{i:3d} {r['ticker']:<6s} {r['modern_sector']:<14s} "
          f"{float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
          f"{r['improvement']:>5s} {float(r['bubblish_peak']):4.2f} "
          f"{r['peak_month']:<8s} {int(r['runway_mo']):>3d} "
          f"{float(r['asymmetry']):5.2f}  {nm}")

# ============ IMMINENT + STRONG ENTRIES ============
imm = [r for r in rows if int(r['runway_mo']) <= 5
       and float(r['bubblish_peak']) >= 3.0
       and float(r['improvement']) >= 10
       and float(r['exit_penalty']) < 1.0][:30]
print(f"\n{'='*185}")
print(f"IMMINENT + STRONG + LOW EXIT-PENALTY (runway≤5, bub≥3, Δ≥10, exit_penalty<1)")
print(f"{'='*185}")
print(f"{'Tkr':<6s} {'ModSec':<14s} {'Src':<7s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} "
      f"{'Δ':>5s} {'Bub':>4s} {'PkMo':<8s} {'Run':>3s} {'mPk':>4s} {'Asym':>5s}  Name")
for r in imm:
    nm = (r["name"] or "")[:30]
    print(f"{r['ticker']:<6s} {r['modern_sector']:<14s} {r['source']:<7s} "
          f"{int(r['age']):>3d} {float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
          f"{r['improvement']:>5s} {float(r['bubblish_peak']):4.2f} "
          f"{r['peak_month']:<8s} {int(r['runway_mo']):>3d} {float(r['macro_peak']):4.2f} "
          f"{float(r['asymmetry']):5.2f}  {nm}")

# ============ HIGH EXIT-PENALTY WARNINGS ============
high_exit = sorted([r for r in rows if float(r["exit_penalty"]) >= 2.0],
                    key=lambda r: -float(r["exit_penalty"]))[:20]
print(f"\n{'='*185}")
print(f"HIGH EXIT-PENALTY WARNINGS (helio Jup-Sat, Saturn station, or node ingress near peak)")
print(f"{'='*185}")
print(f"{'Tkr':<6s} {'ModSec':<14s} {'Peak':>5s} {'Bub':>4s} {'PkMo':<8s} {'hjs':>4s} {'sstn':>4s} {'nod':>4s} {'Exit':>4s}  Name")
for r in high_exit:
    nm = (r["name"] or "")[:35]
    print(f"{r['ticker']:<6s} {r['modern_sector']:<14s} {float(r['score_peak']):5.1f} "
          f"{float(r['bubblish_peak']):4.2f} {r['peak_month']:<8s} "
          f"{float(r['hjs_peak']):4.2f} {float(r['sstn_peak']):4.2f} "
          f"{float(r['nod_peak']):4.2f} {float(r['exit_penalty']):4.2f}  {nm}")

# ============ PER-SECTOR CHAMPIONS ============
from collections import defaultdict
by_ms = defaultdict(list)
for r in rows: by_ms[r["modern_sector"]].append(r)

HIGH_CONV = ["SEMIS","AI_QUANTUM","CYBERSEC","NUCLEAR","URANIUM","DEFENSE",
             "AEROSPACE","SPACE","BIOTECH","EV","AUTONOMOUS","HOMEBUILDER",
             "FOOD_BEV","STREAMING","ENTERTAINMENT","LUXURY","PRECIOUS_METALS","METALS","HOSPITALITY","REIT","CRYPTO"]
for ms in HIGH_CONV:
    sub = by_ms.get(ms, [])[:6]
    if not sub: continue
    print(f"\n--- {ms} ({len(sub)} of {len(by_ms[ms])} tradeable) ---")
    for r in sub:
        nm = (r["name"] or "")[:30]
        print(f"  {r['ticker']:<6s} Age{int(r['age']):>3d} "
              f"{float(r['score_now']):5.1f}→{float(r['score_peak']):5.1f} "
              f"{r['improvement']:>+5s} Bub{float(r['bubblish_peak']):4.2f} "
              f"Pk{r['peak_month']} ({int(r['runway_mo'])}mo) "
              f"Asym{float(r['asymmetry']):5.2f}  {nm}")
