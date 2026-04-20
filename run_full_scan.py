"""
Full scan: BTI v4 on every SP500 constituent at Apr 2026.
Also a large Ritter sample (all post-1990 IPOs).
"""
from __future__ import annotations
import csv
import sys
import time
import statistics as st
from collections import defaultdict
from pathlib import Path
from bti_test import compute_natal
from bti_v4 import compute_bti_v4, bti_window_v4, yx

EVAL_Y, EVAL_M = 2026, 4

def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))

def scan(rows, label, eval_y=EVAL_Y, eval_m=EVAL_M, use_window=True):
    results = []
    t0 = time.time()
    errs = 0
    for i, row in enumerate(rows):
        tk = row["ticker"]
        name = row["name"]
        sector = row.get("sector", "")
        ipo = row["ipo_date"]
        source = row.get("source", "")
        try:
            natal = compute_natal(ipo)
            if use_window:
                rep = bti_window_v4(natal, eval_y, eval_m, half=3)
            else:
                rep = compute_bti_v4(natal, eval_y, eval_m)
                rep["window_offset"] = 0
            results.append((tk, name, sector, ipo, source, rep))
        except Exception as e:
            errs += 1
        if (i+1) % 100 == 0:
            print(f"  {label}: {i+1}/{len(rows)} in {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  {label}: done {len(results)}/{len(rows)}  errors={errs}  in {time.time()-t0:.0f}s", file=sys.stderr)
    return results

def report(results, label, n_show=40):
    results = sorted(results, key=lambda r: -r[5]["bti"])
    print(f"\n{'='*160}")
    print(f"TOP {n_show}  — {label}  ({len(results)} ranked)")
    print(f"{'='*160}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'Sec':<20s} {'Name':<30s} {'IPO':<11s} {'BTIw':>6s} {'+/-':>3s} {'Pmax':>5s} {'rp':>4s} {'dP3':>5s} {'Rnow':>5s} {'I':>4s} {'Gs':>4s} {'Ge':>4s} {'src':<10s}")
    for i, (tk, name, sec, ipo, src, rep) in enumerate(results[:n_show], 1):
        print(f"{i:3d} {tk:<6s} {sec[:20]:<20s} {name[:30]:<30s} {ipo:<11s} {rep['bti']:6.2f} {rep['window_offset']:+3d} {rep['P_max_18']:5.1f} {rep['rp']:4.2f} {rep['dP3']:+5.2f} {rep['R_now']:5.1f} {rep['I_90d']:4.1f} {rep['Gs']:4.2f} {rep['Ge']:4.2f} {src:<10s}")
    # Distribution
    btis = [r[5]["bti"] for r in results]
    print(f"\nDISTRIBUTION: n={len(btis)}  mean={st.mean(btis):.2f}  median={st.median(btis):.2f}  max={max(btis):.2f}")
    bands = [(0,1),(1,2),(2,3),(3,5),(5,10),(10,20),(20,999)]
    for lo,hi in bands:
        n = sum(1 for b in btis if lo <= b < hi)
        pct = 100*n/len(btis)
        bar = "█" * int(pct/2)
        print(f"  BTI [{lo:>4.1f}, {hi:>4.1f}):  {n:4d}  ({pct:4.1f}%)  {bar}")
    # Sector breakdown
    by_sec = defaultdict(list)
    for r in results: by_sec[r[2]].append(r[5]["bti"])
    if len(by_sec) > 1:
        print(f"\nSECTOR MEDIANS:")
        for sec, vals in sorted(by_sec.items(), key=lambda kv: -st.median(kv[1])):
            n_hi = sum(1 for v in vals if v > 5)
            print(f"  {sec[:25]:<25s}  n={len(vals):3d}  median={st.median(vals):5.2f}  max={max(vals):5.2f}  above_5={n_hi}")

def main():
    # SP500 full scan
    sp500 = load_csv("/home/user/cyclepapa/data/sp500_ipo_dates.csv")
    print(f"Loaded {len(sp500)} SP500 constituents", file=sys.stderr)
    print(f"Scanning SP500 at {EVAL_Y}-{EVAL_M:02d}...", file=sys.stderr)
    sp500_results = scan(sp500, "SP500")
    report(sp500_results, f"SP500 @ {EVAL_Y}-{EVAL_M:02d} (window ±3mo)", n_show=40)

    # Export SP500 results
    outpath = Path("/home/user/cyclepapa/data/sp500_bti_apr2026.csv")
    with outpath.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","sector","ipo_date","source","bti","window_off",
                    "P_max_18","p_ratio","R_now","I_90d","Gs","Ge","thin","ben","rise","dP3","E"])
        for (tk,nm,sec,ipo,src,rep) in sorted(sp500_results, key=lambda r:-r[5]["bti"]):
            w.writerow([tk,nm,sec,ipo,src,
                        f"{rep['bti']:.3f}", rep["window_offset"],
                        f"{rep['P_max_18']:.2f}", f"{rep['p_ratio']:.2f}",
                        f"{rep['R_now']:.2f}", f"{rep['I_90d']:.2f}",
                        f"{rep['Gs']:.2f}", f"{rep['Ge']:.2f}",
                        f"{rep['thin']:.2f}", f"{rep['ben']:.2f}", f"{rep['rise']:.2f}",
                        f"{rep['dP3']:.2f}", f"{rep['E']:.2f}"])
    print(f"\nExported SP500 BTI ranking to {outpath}", file=sys.stderr)

    # Ritter full scan (post-1990 to control compute)
    print(f"\nLoading Ritter dataset...", file=sys.stderr)
    import openpyxl
    wb = openpyxl.load_workbook("/home/user/cyclepapa/data/IPO-age.xlsx", data_only=True)
    ws = wb["1975-2025"]
    ritter_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        od, nm, tk, cusip, adr, vc, dual, shares, internet, crsp, fnd, roll = row[:12]
        if not od: continue
        try:
            d = int(od)
            y, m, dd = d//10000, (d//100)%100, d%100
            if y < 1990: continue  # post-1990 only
            iso = f"{y:04d}-{m:02d}-{dd:02d}"
        except: continue
        # Filter: need a ticker, not an ADR, not a rollup
        if not tk or str(tk).strip() in ("", "."): continue
        if adr == 2: continue
        if roll == 1: continue
        ritter_rows.append({
            "ticker": str(tk).strip().upper(),
            "name": nm or "",
            "sector": "Ritter",
            "ipo_date": iso,
            "source": "ritter"
        })
    print(f"Loaded {len(ritter_rows)} Ritter IPOs (post-1990, non-ADR, non-rollup)", file=sys.stderr)
    ritter_results = scan(ritter_rows, "Ritter")
    report(ritter_results, f"Ritter post-1990 IPOs @ {EVAL_Y}-{EVAL_M:02d}", n_show=50)

    # Export top Ritter
    outpath2 = Path("/home/user/cyclepapa/data/ritter_bti_apr2026.csv")
    with outpath2.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","ipo_date","bti","window_off","P_max_18","R_now","I_90d","Gs","Ge"])
        for (tk,nm,sec,ipo,src,rep) in sorted(ritter_results, key=lambda r:-r[5]["bti"]):
            w.writerow([tk,nm,ipo,
                        f"{rep['bti']:.3f}", rep["window_offset"],
                        f"{rep['P_max_18']:.2f}", f"{rep['R_now']:.2f}",
                        f"{rep['I_90d']:.2f}", f"{rep['Gs']:.2f}", f"{rep['Ge']:.2f}"])
    print(f"Exported Ritter BTI ranking to {outpath2}", file=sys.stderr)

if __name__ == "__main__":
    main()
