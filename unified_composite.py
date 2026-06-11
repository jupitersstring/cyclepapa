"""Unified asymmetry composite v4.

Consolidates the four prior overlapping scoring scripts (top_asymmetric,
asymmetric_integrated, asymmetric_full_universe, unified_asymmetry) into
one well-defined scorer. Reads from the canonical signal sources:

  cancel_10b5_1.json       10b5-1 plan termination/adoption (v3)
  form4_buys.json          Form 4 open-market purchases
  step_change.csv          event step-change (M&A, buyback, spin, 13D)
  forensic_asymmetry.json  PSU forensic depth
  psu_forensics_v2.json    PSU NEO breakdown + LTI mix
  sc13d_recent.json        13D activist filings
  yfinance_quick.json      valuation overlay (mcap, drawdown, P/B)

Output:
  unified_composite.{csv,json}

Score components (weights sum to 100 + bounded 10b5-1 leg):

  Insider cluster signal           up to 35
  Valuation tilt                   up to 25
  Step-change event stack          up to 25
  Forensic PSU quality             up to 15
  13D / activist                   up to  8
  10b5-1 directional signal        +/- 25

Engineering invariants:
  - Single source of insider_pack() function (no copy-paste).
  - Explicit data_available flag per ticker per signal layer.
  - Single noise blacklist (TSM, NONE, AXIA3, etc.) at the top.
  - Versioned schema in output JSON so downstream consumers can detect changes.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path("/home/user/cyclepapa")

SCHEMA_VERSION = "v5-144-buyback"

# Signal noise: programmatic employee-share programs (TSM), placeholder
# entries (NONE), non-tradeable identifiers (AXIA3 = futures token).
NOISE_BLACKLIST = {"TSM", "NONE", "AXIA3"}

# Foreign filers we know about (file 20-F not 10-Q). We surface
# data_available=false rather than scoring them as if they had no
# 10b5-1 activity.
KNOWN_FPI = {
    "AGBK", "SRAD", "ODTX", "ONON", "NXG",
}


def days_ago(date_str: str | None) -> Optional[int]:
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Insider cluster (single source of truth)
# ---------------------------------------------------------------------------

def insider_pack(tk: str, f4: dict) -> dict:
    """Compute the insider-buying cluster signal for ONE ticker. The
    canonical implementation -- prior versions were copy-pasted in
    top_asymmetric, asymmetric_integrated, asymmetric_full_universe."""
    rec = f4.get(tk) or {}
    filings = rec.get("filings") or []
    if not filings:
        return {
            "available": False,
            "cluster": 0, "ceo": False, "cfo": False, "chair": False,
            "tot": 0.0, "n30": 0, "n90": 0, "n180": 0,
            "window_days": None, "top_buyers": [],
        }
    titles = {}
    for b in rec.get("buyer_set") or []:
        parts = b.split("|")
        if len(parts) >= 2:
            titles[parts[0].strip()] = parts[1].strip()
    by_date: dict[str, set] = {}
    has_ceo = has_cfo = has_chair = False
    n30 = n90 = n180 = 0
    total = 0.0
    enriched = []
    for fl in filings:
        d = fl.get("date")
        if not d:
            continue
        title = fl.get("title") or titles.get(
            (fl.get("person") or "").strip(), "")
        tl = (title or "").lower()
        if "ceo" in tl or "chief executive" in tl:
            has_ceo = True
        if "cfo" in tl or "chief financial" in tl:
            has_cfo = True
        if "chair" in tl and "vice" not in tl:
            has_chair = True
        da = days_ago(d)
        if da is not None:
            if da <= 30: n30 += 1
            if da <= 90: n90 += 1
            if da <= 180: n180 += 1
        amt = float(fl.get("dollar") or 0)
        total += amt
        by_date.setdefault(d, set()).add(fl.get("person"))
        enriched.append((d, fl.get("person"), title, amt))
    # Max distinct buyers within a 14-day rolling window
    dates = sorted(by_date.keys())
    best = 0
    best_window = None
    for i, d1 in enumerate(dates):
        try:
            dt1 = datetime.strptime(d1[:10], "%Y-%m-%d")
        except Exception:
            continue
        cluster = set()
        for d2 in dates[i:]:
            try:
                dt2 = datetime.strptime(d2[:10], "%Y-%m-%d")
            except Exception:
                continue
            if (dt2 - dt1).days <= 14:
                cluster |= by_date[d2]
            else:
                break
        if len(cluster) > best:
            best = len(cluster)
            best_window = d1
    return {
        "available": True,
        "cluster": best,
        "ceo": has_ceo, "cfo": has_cfo, "chair": has_chair,
        "tot": total, "n30": n30, "n90": n90, "n180": n180,
        "window_days": days_ago(best_window),
        "top_buyers": sorted(enriched, key=lambda x: -x[3])[:5],
    }


def insider_score(ins: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    if not ins.get("available"):
        return 0.0, []
    clu = ins["cluster"]
    wd = ins.get("window_days")
    rec_mult = 1.0 if (wd is not None and wd <= 30) else (
        0.6 if wd is not None and wd <= 90 else 0.25)
    if clu >= 5:
        score += 25 * rec_mult
        reasons.append(f"{clu}-buyer cluster {wd}d ago")
    elif clu >= 4:
        score += 20 * rec_mult
        reasons.append(f"{clu}-buyer cluster {wd}d ago")
    elif clu >= 3:
        score += 14 * rec_mult
        reasons.append(f"{clu}-buyer cluster {wd}d ago")
    elif clu >= 2:
        score += 6 * rec_mult
    if ins["ceo"] and ins["cfo"]:
        score += 12
        reasons.append("CEO+CFO bought")
    elif ins["ceo"]:
        score += 6
        reasons.append("CEO bought")
    if ins["tot"] >= 5e6:
        score += 8
        reasons.append(f"${ins['tot']/1e6:.1f}M insider buys")
    elif ins["tot"] >= 1e6:
        score += 4
    return min(35.0, score), reasons


def valuation_score(q: dict) -> tuple[float, list[str]]:
    if not q:
        return 0.0, []
    score = 0.0
    reasons = []
    px = q.get("price")
    lo = q.get("fwk_low")
    hi = q.get("fwk_high")
    pb = q.get("p_b")
    if px and lo and hi and hi > lo:
        dd = (px - lo) / (hi - lo) * 100
        if dd <= 10:
            score += 18
            reasons.append(f"{dd:.0f}% above 52w low")
        elif dd <= 25:
            score += 12
            reasons.append(f"{dd:.0f}% above 52w low")
        elif dd <= 40:
            score += 6
    if pb is not None and 0 < pb <= 1.2:
        score += 6
        reasons.append(f"P/B {pb:.1f}")
    elif pb is not None and 0 < pb <= 2:
        score += 3
    return min(25.0, score), reasons


def step_change_score(step_row: dict) -> tuple[float, list[str]]:
    if not step_row:
        return 0.0, []
    try:
        sc = float(step_row.get("step_change_score") or 0)
    except (TypeError, ValueError):
        return 0.0, []
    if sc >= 50:
        return 22, [f"step-change {sc:.0f}"]
    if sc >= 30:
        return 12, [f"step-change {sc:.0f}"]
    if sc >= 15:
        return 5, []
    return 0, []


def psu_forensic_score(forensic_row: dict, fz_row: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    try:
        fs = float((forensic_row or {}).get("forensic_score") or 0)
        if fs >= 30:
            score += 12
            reasons.append(f"forensic-PSU {fs:.0f}")
        elif fs >= 20:
            score += 7
            reasons.append(f"forensic-PSU {fs:.0f}")
    except Exception:
        pass
    forensics = (fz_row or {}).get("forensics") or {}
    psu_pct = (forensics.get("lti_mix") or {}).get("psu_pct")
    if psu_pct and psu_pct >= 70:
        score += 3
        reasons.append(f"PSU {psu_pct}% LTI")
    return min(15.0, score), reasons


def cancel_10b5_1_score(cxl_row: dict) -> tuple[float, str, list[str]]:
    """Return (signed_score_capped, data_status, reasons).
    data_status: 'has_signal' | 'no_signal' | 'no_data'."""
    if not cxl_row:
        return 0.0, "no_data", []
    if cxl_row.get("data_available") is False:
        return 0.0, "no_data", []
    sc = float(cxl_row.get("score") or 0)
    capped = max(-25.0, min(25.0, sc))
    if sc == 0:
        return 0.0, "no_signal", []
    sign = "+" if capped > 0 else ""
    reasons = [f"10b5-1 leg {sign}{capped:.0f}"]
    return capped, "has_signal", reasons


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def form144_score(f144_row: dict) -> tuple[float, list[str]]:
    """Form 144 leg: bearish points for accelerating proposed-sale
    activity. Already capped at -20 inside form144_scan.score_144;
    re-cap here defensively."""
    if not f144_row:
        return 0.0, []
    sc = float(f144_row.get("score") or 0)
    if sc >= 0:
        return 0.0, []
    return max(-20.0, sc), list(f144_row.get("reasons") or [])


def buyback_verify_score(bb_row: dict) -> tuple[float, list[str]]:
    """Buyback-verification leg: rewards REAL share-count shrinkage,
    penalizes says-buyback-does-dilution divergence."""
    if not bb_row:
        return 0.0, []
    pts = float(bb_row.get("points") or 0)
    status = bb_row.get("status")
    if pts == 0:
        return 0.0, []
    chg = (bb_row.get("share_change") or {}).get("change_pct")
    chg_s = f" ({chg:+.1f}% shares)" if chg is not None else ""
    return pts, [f"buyback {status}{chg_s}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "unified_composite.csv"))
    ap.add_argument("--json", default=str(ROOT / "unified_composite.json"))
    ap.add_argument("--min-score", type=float, default=10.0)
    args = ap.parse_args()

    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    fz = json.loads((ROOT / "psu_forensics_v2.json").read_text())
    forensic = json.loads((ROOT / "forensic_asymmetry.json").read_text())
    cxl = json.loads((ROOT / "cancel_10b5_1.json").read_text())
    quick_p = ROOT / "yfinance_quick.json"
    quick = json.loads(quick_p.read_text()) if quick_p.exists() else {}
    step = {r["ticker"]: r for r in
            csv.DictReader(open(ROOT / "step_change.csv"))}
    sc13d_p = ROOT / "sc13d_recent.json"
    sc13d = json.loads(sc13d_p.read_text()) if sc13d_p.exists() else {}
    sc13d_set = set(sc13d.keys()) if isinstance(sc13d, dict) else set()
    f144_p = ROOT / "form144_scan.json"
    f144 = json.loads(f144_p.read_text()) if f144_p.exists() else {}
    bb_p = ROOT / "buyback_verify.json"
    bb = json.loads(bb_p.read_text()) if bb_p.exists() else {}

    all_tk = (set(f4.keys()) | set(fz.keys()) | set(forensic.keys())
              | set(step.keys()) | set(cxl.keys()) | sc13d_set
              | set(quick.keys()))
    all_tk -= NOISE_BLACKLIST

    rows = []
    for tk in sorted(all_tk):
        ins = insider_pack(tk, f4)
        ins_sc, ins_reasons = insider_score(ins)
        q = quick.get(tk) or {}
        val_sc, val_reasons = valuation_score(q)
        st_sc, st_reasons = step_change_score(step.get(tk) or {})
        psu_sc, psu_reasons = psu_forensic_score(
            forensic.get(tk) or {}, fz.get(tk) or {})
        cxl_sc, cxl_status, cxl_reasons = cancel_10b5_1_score(cxl.get(tk) or {})
        f144_sc, f144_reasons = form144_score(f144.get(tk) or {})
        bb_sc, bb_reasons = buyback_verify_score(bb.get(tk) or {})

        sc13d_sc = 6.0 if tk in sc13d_set else 0.0
        sc13d_reasons = ["13D filed"] if tk in sc13d_set else []

        is_fpi = tk in KNOWN_FPI or (
            cxl_status == "no_data" and (
                cxl.get(tk, {}).get("data_available") is False))

        # Composite. 10b5-1 / Form 144 / buyback-verify are signed;
        # everything else additive.
        composite = (ins_sc + val_sc + st_sc + psu_sc + sc13d_sc
                     + cxl_sc + f144_sc + bb_sc)

        if composite < args.min_score and cxl_sc == 0 and f144_sc == 0:
            continue

        # Format
        all_reasons = (
            ins_reasons + val_reasons + st_reasons +
            psu_reasons + sc13d_reasons + cxl_reasons +
            f144_reasons + bb_reasons
        )
        rows.append({
            "ticker": tk,
            "name": (q.get("name") or "")[:40],
            "sector": (q.get("sector") or "")[:15],
            "mcap_musd": round((q.get("mcap") or 0) / 1e6, 1) if q.get("mcap") else None,
            "price": q.get("price"),
            "drawdown_pct": round(
                (q.get("price") - q.get("fwk_low")) /
                (q.get("fwk_high") - q.get("fwk_low")) * 100, 1
            ) if (q.get("price") and q.get("fwk_low") and q.get("fwk_high")
                  and q.get("fwk_high") > q.get("fwk_low")) else None,
            "p_b": q.get("p_b"),
            "score": round(composite, 1),
            "insider_score": round(ins_sc, 1),
            "valuation_score": round(val_sc, 1),
            "step_change_score": round(st_sc, 1),
            "psu_forensic_score": round(psu_sc, 1),
            "sc13d_score": round(sc13d_sc, 1),
            "cancel_10b5_1_score": round(cxl_sc, 1),
            "form144_score": round(f144_sc, 1),
            "buyback_verify_score": round(bb_sc, 1),
            "cluster_size": ins.get("cluster", 0),
            "ceo_bought": ins.get("ceo"),
            "cfo_bought": ins.get("cfo"),
            "tot_insider_musd": round(ins.get("tot", 0) / 1e6, 2),
            "10b5_1_status": cxl_status,
            "is_foreign_filer": is_fpi,
            "reasons": " | ".join(all_reasons)[:300],
            "_schema": SCHEMA_VERSION,
        })

    rows.sort(key=lambda r: -r["score"])

    out_csv = Path(args.csv)
    out_json = Path(args.json)
    fields = list(rows[0].keys()) if rows else []
    fields = ["rank"] + fields
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            w.writerow(r)
    out_json.write_text(json.dumps(rows, indent=2, default=str))

    print(f"Wrote {out_csv} + {out_json} ({len(rows)} rows)\n")
    n_data_full = sum(1 for r in rows if r["10b5_1_status"] != "no_data")
    n_fpi = sum(1 for r in rows if r["is_foreign_filer"])
    print(f"Coverage: {n_data_full} with 10b5-1 data, {n_fpi} flagged FPI\n")
    print(f"=== TOP 30 BY UNIFIED COMPOSITE ===")
    print(f"{'#':<3}{'TKR':<7}{'MCAP':>9}{'PX':>8}{'DD%':>5}"
          f"{'INS':>4}{'VAL':>4}{'STP':>4}{'PSU':>4}"
          f"{'10B5':>5}{'TOT':>5}  REASONS")
    print("-" * 200)
    for i, r in enumerate(rows[:30], 1):
        mc = r.get("mcap_musd")
        mc_s = f"{mc:>8.0f}M" if mc else "       ?M"
        px = r.get("price")
        px_s = f"{px:>8.2f}" if px else "       ?"
        dd = r.get("drawdown_pct")
        dd_s = f"{dd:>4.0f}%" if dd is not None else "   ?"
        print(f"{i:<3}{r['ticker']:<7}{mc_s}{px_s}{dd_s}"
              f"{r['insider_score']:>4.0f}{r['valuation_score']:>4.0f}"
              f"{r['step_change_score']:>4.0f}{r['psu_forensic_score']:>4.0f}"
              f"{r['cancel_10b5_1_score']:>+5.0f}{r['score']:>5.0f}  "
              f"{r['reasons'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
