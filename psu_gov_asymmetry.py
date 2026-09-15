"""PSU x Governance asymmetry ranking over the FULL universe.

The thesis ranking: lead with incentive-structure quality (proxy_scan's
psu_core + gov_score over every DEF 14A in the 6,164-name universe),
then demand behavioural confirmation before a name can rank top-tier.

  THESIS  = psu_core (0-100, freshness-weighted structure quality)
          + gov_score (-10..30 governance hygiene)
          + 8 * forward-conditionality count

  CONFIRM = signed sum of behaviour legs, each individually capped:
          10b5-1 (+/-15) . Form 144 (-10) . buyback verify (+/-10)
          tender (+15)   . insider cluster (+12) . 13D (+5)

  VALUE   = drawdown / P/B tilt (0..15)

  TOTAL   = THESIS * 0.55 + CONFIRM + VALUE

A name with a beautiful plan but bearish behaviour (the LAZ pattern)
gets dragged down; a mediocre plan can't buy its way up on behaviour
alone because THESIS dominates the upside.

Reads proxy_scan.json + proxy_scan.shard_*.json (merging live partials
so the ranking improves as the scan progresses).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def load_proxy() -> dict:
    merged = {}
    for p in [ROOT / "proxy_scan.json"] + sorted(ROOT.glob("proxy_scan.shard_*.json")):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        for tk, v in d.items():
            if v.get("_complete") and (tk not in merged
                                       or v.get("has_psu_program")):
                merged[tk] = v
    return merged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "psu_gov_asymmetry.csv"))
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    proxy = load_proxy()
    cxl = json.loads((ROOT / "cancel_10b5_1.json").read_text())
    f144 = json.loads((ROOT / "form144_scan.json").read_text())
    bb = json.loads((ROOT / "buyback_verify.json").read_text())
    tender = json.loads((ROOT / "tender_scan.json").read_text())
    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    sc13d_p = ROOT / "sc13d_recent.json"
    sc13d = set(json.loads(sc13d_p.read_text()).keys()) if sc13d_p.exists() else set()

    from unified_composite import insider_pack, insider_score, NOISE_BLACKLIST

    rows = []
    n_scanned = sum(1 for v in proxy.values() if v.get("_complete"))
    for tk, p in proxy.items():
        if tk in NOISE_BLACKLIST or not p.get("has_psu_program"):
            continue
        thesis = ((p.get("psu_core") or 0)
                  + (p.get("gov_score") or 0)
                  + 8 * (p.get("n_fwd_cond") or 0))
        if thesis < 30:
            continue

        confirm = 0.0
        notes = []
        cs = float((cxl.get(tk) or {}).get("score") or 0)
        if cs:
            c = max(-15, min(15, cs * 0.6))
            confirm += c; notes.append(f"10b5-1 {c:+.0f}")
        fs = float((f144.get(tk) or {}).get("score") or 0)
        if fs < 0:
            c = max(-10, fs * 0.5)
            confirm += c; notes.append(f"144 {c:+.0f}")
        b = bb.get(tk) or {}
        if b.get("points"):
            c = max(-10, min(10, b["points"]))
            confirm += c; notes.append(f"bb {b.get('status','')[:9]}")
        t = tender.get(tk) or {}
        ts = float(t.get("score") or 0)
        if ts > 0 and t.get("role") != "BIDDER" \
                and "DEBT" not in (t.get("role") or ""):
            c = min(15, ts * 0.75)
            confirm += c; notes.append(f"tender +{c:.0f}")
        ins = insider_pack(tk, f4)
        isc, _ = insider_score(ins)
        if isc:
            c = min(12, isc * 0.4)
            confirm += c; notes.append(f"ins +{c:.0f}")
        if tk in sc13d:
            confirm += 5; notes.append("13D")

        q = yq.get(tk) or {}
        value = 0.0
        px, lo, hi, pb = (q.get("price"), q.get("fwk_low"),
                          q.get("fwk_high"), q.get("p_b"))
        if px and lo and hi and hi > lo:
            dd = (px - lo) / (hi - lo) * 100
            if dd <= 15: value += 10
            elif dd <= 30: value += 6
        if pb and 0 < pb <= 1.2:
            value += 5

        total = thesis * 0.55 + confirm + value
        rows.append({
            "ticker": tk,
            "total": round(total, 1),
            "thesis": round(thesis, 1),
            "confirm": round(confirm, 1),
            "value": round(value, 1),
            "psu_core": p.get("psu_core"),
            "gov": p.get("gov_score"),
            "fwd": p.get("n_fwd_cond"),
            "psu_pct": p.get("psu_pct_lti"),
            "metrics": ",".join(p.get("per_share_metrics") or [])[:24],
            "mcap_musd": round((q.get("mcap") or 0) / 1e6, 0) or None,
            "price": q.get("price"),
            "filing_date": p.get("filing_date"),
            "notes": " | ".join(notes)[:60],
            "fwd_snippet": (p.get("fwd_snippets") or [""])[0][:120],
            "gov_reasons": "; ".join(p.get("gov_reasons") or [])[:60],
        })

    rows.sort(key=lambda r: -r["total"])
    with open(args.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)

    print(f"Proxy coverage: {n_scanned} scanned; "
          f"{len(rows)} qualify (thesis >= 30)\n")
    print(f"{'#':<3}{'TKR':<7}{'MCAP':>9}{'THS':>5}{'CNF':>5}{'VAL':>4}"
          f"{'TOT':>6}{'GOV':>4}{'FWD':>4}  {'CONFIRMS':<40} FWD-CONDITION / GOV")
    print("-" * 185)
    for i, r in enumerate(rows[:args.top], 1):
        mc = f"{r['mcap_musd']:>8.0f}M" if r["mcap_musd"] else "       ?M"
        info = r["fwd_snippet"] or r["gov_reasons"]
        print(f"{i:<3}{r['ticker']:<7}{mc}{r['thesis']:>5.0f}"
              f"{r['confirm']:>+5.0f}{r['value']:>4.0f}{r['total']:>6.0f}"
              f"{r['gov'] if r['gov'] is not None else 0:>4.0f}{r['fwd']:>4}"
              f"  {r['notes']:<40} {info[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
