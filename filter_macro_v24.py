"""Post-filter v24 (macro-regime) output: tradeable allowlist + per-modern-sector top."""
import csv
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def keep(r):
    nm, tk, src = r["name"], r["ticker"], r["source"]
    if not nm or not tk: return False
    if BAD_NAME.search(nm): return False
    if BAD_TICKER.search(tk): return False
    if len(tk) > 5: return False
    return src == "SP500" or tk in CURATED_ACTIVE

rows = []
with open("/home/user/cyclepapa/data/universe_macro_v24.csv") as f:
    for r in csv.DictReader(f):
        if keep(r): rows.append(r)

rows.sort(key=lambda r: -float(r["asymmetry"]))
with open("/home/user/cyclepapa/data/tradeable_macro_v24.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        w.writerow(r)
print(f"{len(rows)} tradeable survivors\n")

# Overall top 30
print(f"{'='*165}")
print(f"TOP 30 — MACRO-REGIME + SECTOR-AWARE ASYMMETRIC")
print(f"{'='*165}")
hdr = f"{'#':>3s} {'Tkr':<6s} {'ModSec':<14s} {'Sec':<10s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'Bub':>4s} {'PkMo':<8s} {'Run':>3s} {'mNow':>4s} {'mPk':>4s} {'Asym':>5s}  Name"
print(hdr)
for i, r in enumerate(rows[:30], 1):
    nm = (r["name"] or "")[:28]
    print(f"{i:3d} {r['ticker']:<6s} {r['modern_sector']:<14s} {r['sector']:<10s} "
          f"{int(r['age']):>3d} {float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
          f"{r['improvement']:>5s} {float(r['bubblish_peak']):4.2f} {r['peak_month']:<8s} "
          f"{int(r['runway_mo']):>3d} {float(r['macro_now']):4.2f} {float(r['macro_peak']):4.2f} "
          f"{float(r['asymmetry']):5.2f}  {nm}")

# Top per macro-regime-favored modern sectors
MACRO_PRIORITY = ["URANIUM","NUCLEAR","DEFENSE","AEROSPACE","SEMIS","AI_QUANTUM",
                  "SPACE","DRONES","SATELLITES","CYBERSEC","METALS","PRECIOUS_METALS",
                  "HOMEBUILDER","REIT","WATER_UTIL","FOOD_BEV","STAPLES",
                  "HOSPITALITY","STREAMING","ENTERTAINMENT","GAMBLING","LUXURY",
                  "BIOTECH","EV","AUTONOMOUS","TECH","FINANCE","FOSSIL","CRYPTO","MEME"]
for ms in MACRO_PRIORITY:
    sub = [r for r in rows if r["modern_sector"] == ms][:8]
    if not sub: continue
    print(f"\n{'-'*165}")
    print(f"{ms}  ({len(sub)} of {sum(1 for r in rows if r['modern_sector']==ms)} tradeable)")
    print(f"{'-'*165}")
    print(f"  {'Tkr':<6s} {'Sec':<10s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'Bub':>4s} {'PkMo':<8s} {'Run':>3s} {'mPk':>4s} {'Asym':>5s}  Name")
    for r in sub:
        nm = (r["name"] or "")[:32]
        print(f"  {r['ticker']:<6s} {r['sector']:<10s} {int(r['age']):>3d} "
              f"{float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
              f"{r['improvement']:>5s} {float(r['bubblish_peak']):4.2f} {r['peak_month']:<8s} "
              f"{int(r['runway_mo']):>3d} {float(r['macro_peak']):4.2f} "
              f"{float(r['asymmetry']):5.2f}  {nm}")
