"""Special Situations Pipeline Tracker.

Closes the biggest gap exposed by the Special-Sits Sourcing Playbook:
we already scored DEF 14A / Form 4 / SC TO / buyback verification,
but we had no unified pipeline output across every catalyst type.

This driver pulls fresh EDGAR full-text hits over a rolling window for:
  * Form 10 / 10-12B / 10-12G  (spinoff registrations -- Greenblatt classic)
  * 8-K restructuring / strategic-alternatives / debt-haircut keywords
    (exchange offer, PIK, springing maturity, strategic alternatives
    committee, going concern, going private, rights offering, etc.)

Each hit is joined with the existing scoring layers
(yfinance / proxy_scan / tender_scan / buyback_verify / form4_buys /
cancel_10b5_1 / informational_buys) so a single CSV becomes the
"deal tracking spreadsheet" the playbook prescribes: ticker, situation
type, catalyst, filing date, our existing signal stack, and a sortable
total score.

Output: special_situations_pipeline.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT_CSV = ROOT / "special_situations_pipeline.csv"


def load_overlays() -> dict:
    overlays: dict = {}
    yq = ROOT / "yfinance_quick.json"
    overlays["yf"] = json.loads(yq.read_text()) if yq.exists() else {}

    bb = ROOT / "buyback_verify.json"
    overlays["bb"] = json.loads(bb.read_text()) if bb.exists() else {}

    tender = ROOT / "tender_scan.json"
    overlays["tender"] = json.loads(tender.read_text()) if tender.exists() else {}

    c10 = ROOT / "cancel_10b5_1.json"
    overlays["c10"] = json.loads(c10.read_text()) if c10.exists() else {}

    f4 = ROOT / "form4_buys.json"
    overlays["f4"] = json.loads(f4.read_text()) if f4.exists() else {}

    # latest proxy row per ticker
    proxy: dict = {}
    for fn in sorted(ROOT.glob("proxy_scan*.json")):
        try:
            d = json.loads(fn.read_text())
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if not isinstance(r, dict):
                continue
            tk = r.get("ticker")
            if tk and (tk not in proxy
                       or r.get("filing_date", "") > proxy[tk].get("filing_date", "")):
                proxy[tk] = r
    overlays["proxy"] = proxy

    # composite + informational
    comp: dict = {}
    cp = ROOT / "unified_composite.csv"
    if cp.exists():
        for r in csv.DictReader(cp.open()):
            comp[r["ticker"]] = r
    overlays["comp"] = comp

    info: dict = {}
    ip = ROOT / "informational_buys.csv"
    if ip.exists():
        for r in csv.DictReader(ip.open()):
            info[r["ticker"]] = r
    overlays["info"] = info
    return overlays


def score_hit(tk: str, kind: str, ov: dict) -> tuple[float, list[str]]:
    """Stack signal scoring atop the EDGAR full-text hit."""
    score = 0.0
    reasons: list[str] = []

    if kind == "FORM_10_SPINOFF":
        score += 35
        reasons.append("Form 10-12B spinoff registration")
    elif kind == "RESTRUCT_8K":
        score += 15
        reasons.append("8-K restructuring/debt-haircut keyword hit")

    yf = ov["yf"].get(tk, {}) or {}
    mcap = yf.get("mcap")
    pb = yf.get("p_b")
    if mcap and mcap < 600e6:
        score += 5
        reasons.append(f"microcap ${mcap/1e6:.0f}M")
    if pb and 0 < pb < 0.5:
        score += 15
        reasons.append(f"P/B {pb:.2f}")
    elif pb and 0 < pb < 1.0:
        score += 8
        reasons.append(f"P/B {pb:.2f}")

    p = ov["proxy"].get(tk, {})
    if p:
        cc = p.get("cond_cats") or []
        for cat in cc:
            score += 8
            reasons.append(f"PSU.{cat}")
        if (p.get("psu_pct_lti") or 0) >= 70:
            score += 6
            reasons.append(f"PSU {p['psu_pct_lti']}%LTI")
        if (p.get("gov_score") or 0) >= 15:
            score += 5
            reasons.append(f"gov {p['gov_score']}")

    bb = ov["bb"].get(tk, {})
    if bb.get("status") == "EXECUTING":
        chg = (bb.get("share_change") or {}).get("change_pct", 0)
        score += 10
        reasons.append(f"buyback EXECUTING {chg:+.1f}%")
    elif bb.get("status") == "SHRINKING_NO_AUTH":
        chg = (bb.get("share_change") or {}).get("change_pct", 0)
        score += 6
        reasons.append(f"organic shrink {chg:+.1f}%")

    td = ov["tender"].get(tk, {})
    if isinstance(td, dict):
        role = td.get("role")
        if role == "SELF_TENDER":
            score += 25
            reasons.append("live SELF_TENDER")
        elif role == "TARGET":
            score += 25
            reasons.append("live TARGET 14D-9")
        if td.get("has_13e3"):
            score += 15
            reasons.append("13E-3 going-private")

    c10 = ov["c10"].get(tk, {})
    sgn = c10.get("signed_score") if isinstance(c10, dict) else None
    if sgn:
        score += min(abs(sgn), 25) * (1 if sgn > 0 else -0.6)
        reasons.append(f"10b5-1 signed {sgn:+.0f}")

    f4 = ov["f4"].get(tk, {})
    if isinstance(f4, dict):
        cluster = f4.get("max_cluster_size") or 0
        if cluster >= 3:
            score += min(cluster * 3, 25)
            reasons.append(f"F4 cluster {cluster}")

    ib = ov["info"].get(tk, {})
    try:
        fc = int(ib.get("firing_count") or 0)
        if fc >= 3:
            score += fc * 4
            reasons.append(f"info_buys firing {fc}/5")
    except Exception:
        pass

    return round(score, 1), reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spin-days", type=int, default=365,
                    help="lookback window for Form 10 / 10-12B")
    ap.add_argument("--restruct-days", type=int, default=180,
                    help="lookback window for 8-K restructuring keywords")
    ap.add_argument("--limit", type=int, default=300,
                    help="max filings per category")
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    try:
        from recent import (recent_form10_range,
                            recent_8k_restructuring_range)
    except ImportError as e:
        print(f"need recent.py available: {e}", file=sys.stderr)
        return 1

    ov = load_overlays()
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    spin_start = (datetime.now(timezone.utc)
                  - timedelta(days=args.spin_days)).strftime("%Y-%m-%d")
    print(f"Pulling Form 10/10-12B {spin_start}..{end} limit={args.limit}",
          file=sys.stderr, flush=True)
    spin = recent_form10_range(spin_start, end, limit=args.limit)
    print(f"  got {len(spin)} spinoff filings", file=sys.stderr)
    time.sleep(args.sleep)

    rs_start = (datetime.now(timezone.utc)
                - timedelta(days=args.restruct_days)).strftime("%Y-%m-%d")
    print(f"Pulling 8-K restructuring {rs_start}..{end} limit={args.limit}",
          file=sys.stderr, flush=True)
    rs = recent_8k_restructuring_range(rs_start, end, limit=args.limit)
    print(f"  got {len(rs)} restructuring 8-Ks", file=sys.stderr)

    rows = []
    for rf in spin:
        tk = (rf.ticker or "").upper() or f"CIK{rf.cik}"
        score, reasons = score_hit(tk, "FORM_10_SPINOFF", ov)
        yf = ov["yf"].get(tk, {}) or {}
        rows.append({
            "ticker": tk,
            "company": rf.company,
            "kind": "FORM_10_SPINOFF",
            "filing_date": rf.filing_date,
            "accession": rf.accession,
            "mcap_M": round((yf.get("mcap") or 0) / 1e6, 0),
            "px": yf.get("price"),
            "p_b": yf.get("p_b"),
            "score": score,
            "reasons": "; ".join(reasons),
        })
    for rf in rs:
        tk = (rf.ticker or "").upper() or f"CIK{rf.cik}"
        score, reasons = score_hit(tk, "RESTRUCT_8K", ov)
        yf = ov["yf"].get(tk, {}) or {}
        rows.append({
            "ticker": tk,
            "company": rf.company,
            "kind": "RESTRUCT_8K",
            "filing_date": rf.filing_date,
            "accession": rf.accession,
            "mcap_M": round((yf.get("mcap") or 0) / 1e6, 0),
            "px": yf.get("price"),
            "p_b": yf.get("p_b"),
            "score": score,
            "reasons": "; ".join(reasons),
        })

    rows.sort(key=lambda r: -(r["score"] or 0))
    fieldnames = ["ticker", "company", "kind", "filing_date", "accession",
                  "mcap_M", "px", "p_b", "score", "reasons"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\nwrote {OUT_CSV} ({len(rows)} rows)")
    print(f"\n=== TOP 25 by total signal-stack score ===")
    print(f"{'TKR':<8}{'KIND':<18}{'DATE':<12}{'SCR':<6}{'MCAP':<8}{'P/B':<6}REASONS")
    for r in rows[:25]:
        print(f"{r['ticker']:<8}{r['kind']:<18}{r['filing_date']:<12}"
              f"{r['score']:<6}{r['mcap_M']:<8}"
              f"{r['p_b'] or 0:<6.2f}{r['reasons'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
