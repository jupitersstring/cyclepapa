"""Universe coverage diagnostic across every layer.

For each of the 6,164 universe tickers, mark which scoring layers
have data, then surface:
  - PSU-universe names lacking valuation data (must fill to rank)
  - Convergent-12 + close-runner-ups lacking PE/EV/EBITDA
  - High-PSU names lacking insider data (could elevate to convergent)

Output:
  full_coverage_matrix.csv
  high_priority_gap_fills.csv  -- names where filling 1 layer would
                                   most likely shift them to convergent
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def main() -> int:
    proxy = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try: d = json.load(open(fn))
        except: continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in proxy or
                    r.get("filing_date","") > proxy[tk].get("filing_date","")):
                    proxy[tk] = r

    yf = json.load(open(ROOT / "yfinance_quick.json"))
    bbv = json.load(open(ROOT / "buyback_verify.json"))
    tender = json.load(open(ROOT / "tender_scan.json"))
    c10 = json.load(open(ROOT / "cancel_10b5_1.json"))
    f4 = json.load(open(ROOT / "form4_buys.json"))
    f144 = json.load(open(ROOT / "form144_scan.json"))

    universe = set(proxy) | set(yf) | set(bbv) | set(tender) | set(c10) | set(f4)
    universe = {t for t in universe if not t.startswith("CIK")}

    rows = []
    for tk in universe:
        p = proxy.get(tk, {}) or {}
        y = yf.get(tk, {}) or {}
        b = bbv.get(tk, {}) or {}
        t = tender.get(tk, {}) or {}
        c = c10.get(tk, {}) or {}
        f = f4.get(tk, {}) or {}
        f1 = f144.get(tk, {}) or {}

        # Per-layer has-data flags
        has_proxy = bool(p)
        has_psu = bool(p.get("psu_core") or p.get("cond_cats"))
        has_yf = bool(y.get("price"))
        has_pe = bool(y.get("p_e_trailing"))
        has_evb = bool(y.get("ev_ebitda"))
        has_pb = bool(y.get("p_b"))
        has_sector = bool(y.get("sector"))
        has_bb = bool(b.get("status"))
        has_tender = bool(t.get("role") or t.get("has_13e3"))
        has_c10 = bool(c.get("score") is not None
                       or c.get("data_available"))
        has_f4 = bool(f.get("buyer_set") or f.get("total_dollar"))
        has_f144 = bool(f1.get("points") is not None
                        or f1.get("score") is not None)

        rows.append({
            "ticker": tk,
            "has_proxy": int(has_proxy),
            "has_psu_program": int(has_psu),
            "has_yfinance": int(has_yf),
            "has_pe": int(has_pe),
            "has_evbitda": int(has_evb),
            "has_pb": int(has_pb),
            "has_sector": int(has_sector),
            "has_buyback": int(has_bb),
            "has_tender": int(has_tender),
            "has_c10b51": int(has_c10),
            "has_f4_buys": int(has_f4),
            "has_f144": int(has_f144),
            "n_layers": sum([has_psu, has_yf, has_bb, has_tender,
                              has_c10, has_f4, has_f144]),
            "psu_core": p.get("psu_core"),
            "gov_score": p.get("gov_score"),
            "mcap_M": round((y.get("mcap") or 0) / 1e6, 0),
            "sector": y.get("sector"),
        })

    rows.sort(key=lambda r: -r["n_layers"])
    out = ROOT / "full_coverage_matrix.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")

    # Coverage rollup
    print(f"\n=== Universe size: {len(rows)} ===")
    for layer in ["has_proxy", "has_psu_program", "has_yfinance",
                  "has_pe", "has_evbitda", "has_pb", "has_sector",
                  "has_buyback", "has_tender", "has_c10b51",
                  "has_f4_buys", "has_f144"]:
        n = sum(r[layer] for r in rows)
        print(f"  {layer:<22} {n:>5} ({n/len(rows)*100:.0f}%)")

    # Gap-fill priority: PSU-scored names missing valuation
    psu_no_yf = [r for r in rows
                  if r["has_psu_program"] and not r["has_yfinance"]]
    psu_no_pe = [r for r in rows
                  if r["has_psu_program"] and r["has_yfinance"]
                  and not r["has_pe"]]
    psu_no_evb = [r for r in rows
                   if r["has_psu_program"] and r["has_yfinance"]
                   and not r["has_evbitda"]]
    print(f"\n=== Highest-priority gap-fills ===")
    print(f"  PSU-scored, no yfinance:    {len(psu_no_yf)}")
    print(f"  PSU-scored, no P/E:         {len(psu_no_pe)}")
    print(f"  PSU-scored, no EV/EBITDA:   {len(psu_no_evb)}")

    # High-PSU names that COULD become convergent if 1 more layer fired
    try:
        consensus_rows = list(csv.DictReader(
            open(ROOT / "consensus_ranking.csv")))
        nscreens = {r["ticker"]: int(r.get("n_screens") or 0)
                    for r in consensus_rows}
    except Exception:
        nscreens = {}

    high_psu = []
    for r in rows:
        if (r["psu_core"] and float(r["psu_core"]) >= 40
            and nscreens.get(r["ticker"], 0) == 2):
            high_psu.append(r)
    high_psu.sort(key=lambda r: -float(r["psu_core"] or 0))
    print(f"\n  High-PSU (>=40), at 2 screens (one signal from convergent): "
          f"{len(high_psu)}")
    for r in high_psu[:15]:
        miss = [k.replace("has_","") for k in (
            "has_yfinance","has_pe","has_evbitda","has_buyback","has_tender",
            "has_c10b51","has_f4_buys") if not r[k]]
        print(f"    {r['ticker']:<7} psu={r['psu_core']:<5} "
              f"missing={','.join(miss)[:60]}")

    # write the priority list
    priority = []
    for r in psu_no_yf + psu_no_pe + psu_no_evb:
        if r not in priority:
            priority.append(r)
    out2 = ROOT / "high_priority_gap_fills.csv"
    with out2.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(priority)
    print(f"\nwrote {out2} ({len(priority)} priority gap-fill rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
