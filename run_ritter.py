"""Run Ritter dataset only (SP500 already done). Uses cached transits."""
import csv, sys, time, statistics as st
from collections import defaultdict
from pathlib import Path
import openpyxl
from bti_test import compute_natal
from bti_v4 import bti_window_v4

EVAL_Y, EVAL_M = 2026, 4

def load_ritter(post_year=1990):
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od); y, m, dd = d//10000, (d//100)%100, d%100
            if y < post_year: continue
            iso = f"{y:04d}-{m:02d}-{dd:02d}"
        except: continue
        if not tk or str(tk).strip() in ("", "."): continue
        if adr == 2: continue
        if roll == 1: continue
        rows.append({
            "ticker": str(tk).strip().upper(),
            "name": nm or "",
            "ipo_date": iso,
            "vc": vc, "founding": fnd, "dual": dual,
        })
    return rows

def main():
    rows = load_ritter(1990)
    print(f"Ritter post-1990 (non-ADR, non-rollup): {len(rows)}", file=sys.stderr)
    results = []
    t0 = time.time()
    for i, r in enumerate(rows):
        try:
            natal = compute_natal(r["ipo_date"])
            rep = bti_window_v4(natal, EVAL_Y, EVAL_M, half=3)
            results.append((r["ticker"], r["name"], r["ipo_date"], r["vc"], rep))
        except Exception:
            pass
        if (i+1) % 1000 == 0:
            print(f"  {i+1}/{len(rows)} in {time.time()-t0:.0f}s  cache growing", file=sys.stderr)
    print(f"  done {len(results)}/{len(rows)} in {time.time()-t0:.0f}s", file=sys.stderr)

    # Rank
    results.sort(key=lambda r: -r[4]["bti"])
    # Export
    outp = Path("/home/user/cyclepapa/data/ritter_bti_apr2026.csv")
    with outp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo_date","vc","bti","window_off","P_max","R_now","I_90d","Gs","Ge"])
        for (tk,nm,ipo,vc,rep) in results:
            w.writerow([tk,nm,ipo,vc,f"{rep['bti']:.3f}",rep["window_offset"],
                        f"{rep['P_max_18']:.2f}",f"{rep['R_now']:.2f}",
                        f"{rep['I_90d']:.2f}",f"{rep['Gs']:.2f}",f"{rep['Ge']:.2f}"])
    print(f"Exported to {outp}", file=sys.stderr)

    # Top 60
    print(f"\n{'='*150}")
    print(f"TOP 60 Ritter IPOs (post-1990) by BTI @ {EVAL_Y}-{EVAL_M:02d}")
    print(f"{'='*150}")
    print(f"{'Rk':>3s} {'Tkr':<7s} {'Name':<35s} {'IPO':<11s} {'VC':>2s} {'BTI':>6s} {'+/-':>3s} {'Pmx':>4s} {'Rnw':>4s} {'I':>4s} {'Gs':>4s} {'Ge':>4s}")
    for i,(tk,nm,ipo,vc,rep) in enumerate(results[:60],1):
        print(f"{i:3d} {tk:<7s} {nm[:35]:<35s} {ipo:<11s} {vc!s:>2s} {rep['bti']:6.2f} {rep['window_offset']:+3d} {rep['P_max_18']:4.1f} {rep['R_now']:4.1f} {rep['I_90d']:4.1f} {rep['Gs']:4.2f} {rep['Ge']:4.2f}")

    # Distribution
    btis = [r[4]["bti"] for r in results]
    print(f"\nDistribution: n={len(btis)}  mean={st.mean(btis):.2f}  median={st.median(btis):.2f}  max={max(btis):.2f}")
    bands = [(0,1),(1,3),(3,5),(5,10),(10,20),(20,50),(50,999)]
    for lo,hi in bands:
        n = sum(1 for b in btis if lo <= b < hi)
        pct = 100*n/len(btis)
        print(f"  [{lo:>3.0f}, {hi:>3.0f}):  {n:5d}  ({pct:4.1f}%)")

    # IPO-year profile
    by_year = defaultdict(list)
    for (tk,nm,ipo,vc,rep) in results:
        by_year[int(ipo[:4])].append(rep["bti"])
    print(f"\nMedian BTI by IPO year (top-scoring cohorts):")
    year_meds = sorted(by_year.items(), key=lambda kv: -st.median(kv[1]))
    for yr, vals in year_meds[:15]:
        n_hi = sum(1 for v in vals if v > 15)
        print(f"  IPO {yr}: n={len(vals):4d}  median={st.median(vals):5.2f}  max={max(vals):5.2f}  above_15={n_hi}")

if __name__ == "__main__":
    main()
