"""Full-universe DEF 14A PSU + governance analyzer.

THE GAP: every PSU/governance leg (psu_step_change, forensic_asymmetry,
psu_forensics_v2, psu_best) runs on the old 1,995-name screen-union's
cached filings. The 4,169 tickers added by build_universe.py have never
had their proxies read -- the core Munger-incentives thesis was still
running on a biased slice.

This module scans the ENTIRE universe: for each ticker, pull the most
recent DEF 14A from the submissions JSON, fetch it (CACHE_HTML honored),
and run the full hardened extraction stack accumulated over this
project:

  psu_scoring.extract_features      per-share vs aggregate metrics,
                                    price hurdles, anti-features
  psu_step_change.pattern_match_score
                                    archetype scoring with the 8x
                                    plausibility gate on hurdles
  psu_forensics.extract_forensics   double/single trigger, clawback,
                                    holding reqs, ownership multiples,
                                    PSU weight (governance hygiene)
  psu_forensics_v2.full_forensics   LTI mix, SOP %, payout history,
                                    plan-change markers
  forensic_asymmetry                forward/retro-tagged conditionali-
                                    ties + plan deltas + section windows

Output per ticker (proxy_scan.json, resumable; mirrored to pipeline.db):
  psu_core       0-100 structure quality (freshness-weighted)
  gov_score      0-30 governance hygiene
  fwd_cond       count of forward-direction business conditionalities

Composite ranking happens downstream in psu_gov_asymmetry.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path("/home/user/cyclepapa")
OUT_JSON = ROOT / "proxy_scan.json"
EXTRACT_VERSION = "proxy-v1"


def recent_def14a(ticker: str, days: int = 450) -> dict | None:
    """Most recent DEF 14A within the window, from submissions JSON."""
    from edgar import cik_for, _get, SEC_DATA
    cik = cik_for(ticker)
    if not cik:
        return None
    sub = _get(f"{SEC_DATA}/submissions/CIK{cik}.json").json()
    recent = sub.get("filings", {}).get("recent", {})
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=days)).strftime("%Y-%m-%d")
    for form, acc, doc, dt in zip(recent.get("form", []),
                                  recent.get("accessionNumber", []),
                                  recent.get("primaryDocument", []),
                                  recent.get("filingDate", [])):
        if form != "DEF 14A":
            continue
        if dt < cutoff:
            return None  # list is reverse-chron; first DEF 14A is newest
        return {"cik": cik, "accession": acc,
                "primary_doc": doc, "filing_date": dt}
    return None


def freshness_weight(filing_date: str) -> float:
    try:
        d = datetime.strptime(filing_date[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - d).days
    except Exception:
        return 0.5
    if days <= 60: return 1.0
    if days <= 120: return 0.9
    if days <= 240: return 0.75
    if days <= 365: return 0.6
    return 0.45


def analyze_proxy(ticker: str, text: str, filing_date: str,
                  price: float | None, mcap: float | None) -> dict:
    """Run the full extraction stack on one proxy's plain text."""
    from psu_scoring import extract_features
    from psu_step_change import pattern_match_score
    from psu_forensics import extract_forensics
    from psu_forensics_v2 import full_forensics
    from forensic_asymmetry import (relevant_section,
                                    extract_conditionalities,
                                    extract_plan_deltas, extract_ladder,
                                    archetype_labels)

    feats = extract_features(ticker, text)
    if not feats.has_psu_program:
        return {"has_psu_program": False}

    gov = extract_forensics(text)
    fz = full_forensics(text)

    section, _spans = relevant_section(text)
    cond = extract_conditionalities(section) if section else {}
    deltas = extract_plan_deltas(section) if section else {}
    ladder = extract_ladder(section) if section else {}

    n_fwd = sum(1 for hits in cond.values()
                if any(h.get("direction") == "forward" for h in hits))
    n_retro = sum(1 for hits in cond.values()
                  if all(h.get("direction") == "retrospective"
                         for h in hits))

    # Build the detail-row dict pattern_match_score expects
    row = {
        "per_share_metrics": feats.per_share_metrics,
        "aggregate_metrics": feats.aggregate_metrics,
        "stock_price_hurdles": feats.stock_price_hurdles,
        "discretionary_language": feats.discretionary_language,
        "retirement_language": feats.retirement_language,
        "repricing_language": feats.repricing_language,
        "front_loaded_language": feats.front_loaded_language,
        "transformation_signal": bool(deltas.get("front_load_grant")),
        "double_trigger": gov.get("double_trigger"),
        "single_trigger": gov.get("single_trigger"),
        "has_cic_table": gov.get("double_trigger") or gov.get("single_trigger"),
        "alignment": 0, "upside_kicker": 0,
        "current_price": price or 0,
        "market_cap": mcap or 0,
    }
    fz_wrap = {"forensics": fz}
    pattern, pattern_reasons = pattern_match_score(row, fz_wrap)

    # Governance hygiene score 0-30
    g = 0.0
    g_reasons = []
    if gov.get("double_trigger") and not gov.get("single_trigger"):
        g += 8; g_reasons.append("double-trigger only")
    elif gov.get("single_trigger"):
        g -= 6; g_reasons.append("single-trigger CIC")
    if (gov.get("post_vest_holding_yrs") or 0) >= 1 or gov.get("hold_until_termination"):
        g += 5; g_reasons.append("post-vest holding requirement")
    if (gov.get("ceo_ownership_multiple") or 0) >= 5:
        g += 4; g_reasons.append(f"{gov['ceo_ownership_multiple']}x ownership multiple")
    if (gov.get("vesting_period_yrs") or 0) >= 3:
        g += 4; g_reasons.append(f"{gov['vesting_period_yrs']}y vesting")
    if deltas.get("clawback_strengthened"):
        g += 3; g_reasons.append("clawback strengthened")
    if deltas.get("anti_hedge_pledge_added"):
        g += 3; g_reasons.append("anti-hedge/pledge")
    if deltas.get("responsive_to_shareholders"):
        g += 3; g_reasons.append("responsive to shareholders")
    sop = fz.get("say_on_pay_pct")
    if sop and sop < 70:
        g -= 8; g_reasons.append(f"SOP only {sop:.0f}%")
    g = max(-10.0, min(30.0, g))

    fw = freshness_weight(filing_date)
    psu_core = min(100.0, pattern * fw + 8 * n_fwd)

    return {
        "has_psu_program": True,
        "psu_core": round(psu_core, 1),
        "pattern_match": round(pattern, 1),
        "freshness": fw,
        "gov_score": round(g, 1),
        "gov_reasons": g_reasons,
        "pattern_reasons": pattern_reasons[:8],
        "n_fwd_cond": n_fwd,
        "n_retro_cond": n_retro,
        "cond_cats": list(cond.keys()),
        "fwd_snippets": [
            h["snippet"][:200]
            for hits in cond.values() for h in hits
            if h.get("direction") == "forward"][:4],
        "per_share_metrics": feats.per_share_metrics,
        "aggregate_metrics": feats.aggregate_metrics,
        "psu_pct_lti": (fz.get("lti_mix") or {}).get("psu_pct"),
        "say_on_pay_pct": fz.get("say_on_pay_pct"),
        "double_trigger": gov.get("double_trigger"),
        "single_trigger": gov.get("single_trigger"),
        "plan_deltas": list(deltas.keys()),
        "stock_price_hurdles": feats.stock_price_hurdles[:12],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-file", default=str(ROOT / "full_universe.txt"))
    ap.add_argument("--sleep", type=float, default=0.30)
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--json", default=str(OUT_JSON))
    args = ap.parse_args()

    tickers = [t.strip().upper() for t in
               Path(args.tickers_file).read_text().splitlines() if t.strip()]
    out_path = Path(args.json)
    out: dict = json.loads(out_path.read_text()) if out_path.exists() else {}

    yq_p = ROOT / "yfinance_quick.json"
    yq = json.loads(yq_p.read_text()) if yq_p.exists() else {}

    from cancel_10b5_1 import load_cached, fetch_and_cache_filing
    import state
    conn = state.connect()

    n_done = n_psu = 0
    for i, tk in enumerate(tickers, 1):
        if i > args.limit:
            break
        if tk in out and out[tk].get("_complete"):
            continue
        try:
            f = recent_def14a(tk)
        except Exception as e:
            out[tk] = {"_complete": True, "_error": str(e)[:120]}
            continue
        time.sleep(args.sleep)
        if not f:
            out[tk] = {"_complete": True, "no_def14a": True}
            n_done += 1
            continue

        text = load_cached(f["accession"])
        if not text:
            text = fetch_and_cache_filing(f["cik"], f["accession"],
                                          f["primary_doc"])
            time.sleep(args.sleep)
        if not text:
            out[tk] = {"_complete": True, "_error": "fetch_failed",
                       **f}
            n_done += 1
            continue

        q = yq.get(tk) or {}
        try:
            res = analyze_proxy(tk, text, f["filing_date"],
                                q.get("price"), q.get("mcap"))
        except Exception as e:
            res = {"_error": f"analyze: {e}"[:150]}
        out[tk] = {"ticker": tk, **f, **res,
                   "_complete": True, "_version": EXTRACT_VERSION}
        # cik not needed downstream; keep accession + date
        out[tk].pop("cik", None)
        out[tk].pop("primary_doc", None)

        with conn:
            state.record_filing(conn, tk, f["accession"],
                                "DEF 14A", f["filing_date"])
        n_done += 1
        if res.get("has_psu_program"):
            n_psu += 1
            if (res.get("psu_core") or 0) >= 45:
                print(f"  STRONG {tk}: core={res['psu_core']:.0f} "
                      f"gov={res['gov_score']:.0f} "
                      f"fwd={res['n_fwd_cond']} "
                      f"{'|'.join(res.get('per_share_metrics') or [])[:40]}",
                      flush=True)
        if n_done % 50 == 0:
            tmp = out_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=1, default=str))
            tmp.replace(out_path)
            print(f"  [{i}/{len(tickers)}] done={n_done} psu={n_psu}",
                  flush=True)

    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, default=str))
    tmp.replace(out_path)
    conn.close()
    print(f"\nDone. {n_done} processed, {n_psu} with PSU programs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
