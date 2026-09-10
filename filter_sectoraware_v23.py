"""Post-filter v23 output: apply tradeable allowlist, then show top-by-sector."""
import csv, re
from filter_tradeable_v22 import CURATED_ACTIVE, BAD_NAME, BAD_TICKER

def keep(r):
    nm, tk, src = r["name"], r["ticker"], r["source"]
    if not nm or not tk: return False
    if BAD_NAME.search(nm): return False
    if BAD_TICKER.search(tk): return False
    if len(tk) > 5: return False
    return src == "SP500" or tk in CURATED_ACTIVE

rows = []
with open("/home/user/cyclepapa/data/universe_sectoraware_v23.csv") as f:
    for r in csv.DictReader(f):
        if keep(r): rows.append(r)

rows.sort(key=lambda r: -float(r["asymmetry"]))

with open("/home/user/cyclepapa/data/tradeable_sectoraware_v23.csv","w",newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        w.writerow(r)

print(f"{len(rows)} tradeable survivors\n")

# Overall top 40
print(f"{'='*155}")
print(f"TOP 40 SECTOR-AWARE ASYMMETRIC — bottom signal upweighted by empirical sector ruler")
print(f"{'='*155}")
print(f"{'Rk':>3s} {'Tkr':<6s} {'Sec':<10s} {'IPO':<11s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'PkMo':<8s} {'Run':>3s} {'BubPk':>5s} {'Asym':>6s}  Name")
for i, r in enumerate(rows[:40], 1):
    nm = (r["name"] or "")[:30]
    print(f"{i:3d} {r['ticker']:<6s} {r['sector']:<10s} {r['ipo']:<11s} {int(r['age']):>3d} "
          f"{float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
          f"{r['improvement']:>5s} {r['peak_month']:<8s} {int(r['runway_mo']):>3d} "
          f"{float(r['bubblish_peak']):5.2f} {float(r['asymmetry']):6.2f}  {nm}")

# Top 10 per sector
sectors_order = ["TECH","EV","BIOPHARM","ENERGY","FINANCE","CRYPTO","RETAIL",
                 "MEDIA","HEALTH","REIT","INDUSTRIAL","METALS","UTILS","MEME","CANNABIS"]
for sec in sectors_order:
    sub = [r for r in rows if r["sector"] == sec][:10]
    if not sub: continue
    print(f"\n{'-'*155}")
    print(f"{sec}  — top {len(sub)} by sector-aware asymmetry")
    print(f"{'-'*155}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'IPO':<11s} {'Age':>3s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'PkMo':<8s} {'Run':>3s} {'BubPk':>5s} {'Asym':>6s}  Name")
    for i, r in enumerate(sub, 1):
        nm = (r["name"] or "")[:30]
        print(f"{i:3d} {r['ticker']:<6s} {r['ipo']:<11s} {int(r['age']):>3d} "
              f"{float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
              f"{r['improvement']:>5s} {r['peak_month']:<8s} {int(r['runway_mo']):>3d} "
              f"{float(r['bubblish_peak']):5.2f} {float(r['asymmetry']):6.2f}  {nm}")
