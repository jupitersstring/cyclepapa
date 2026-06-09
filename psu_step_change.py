"""PSU step-change detector: NEWLY ADOPTED PSU structures matching
the best archetypes in our set.

The premise: when a company freshly puts in place a high-quality PSU
plan (per-share metric stack, deep ladder, heavy PSU weight in LTI,
double-trigger CIC, transformation signal) the market often hasn't
re-priced incentive alignment. We rank ELIGIBILITY (pattern strength)
times FRESHNESS (how recently the plan was disclosed).

Archetypes mined from current top names:
  VRSK/WING       -> ROIIC / per-share-style return metric
  NNBR/UPWK       -> PSU >=60% of LTI + ladder
  PLBY/ALIT/OPEN  -> multi-tranche stock-price ladder + transformation
  FDP/DLTR/SOFI   -> double-trigger CIC, no single-trigger
  DVA/KDP/CRM     -> per-share metric stack (TSR+EPS+ROIC)
  HFFG            -> heavy front-loaded transform PSU

Score = pattern_match * freshness_weight, 0..100.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from universe_filter import is_excluded


DETAIL_SOURCES = [
    "v2_detail.json", "wide180_detail.json", "wide365_detail.json",
    "induce_detail.json", "restruct_v10.json", "missing_v10.json",
    "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json",
    "spinoffs_detail.json",
]


def days_ago(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except Exception:
        return None


def freshness_weight(days: int | None) -> float:
    if days is None:
        return 0.0
    if days <= 30:
        return 1.00
    if days <= 60:
        return 0.90
    if days <= 90:
        return 0.75
    if days <= 180:
        return 0.50
    if days <= 270:
        return 0.25
    return 0.0


def load_forensics_v2() -> dict:
    p = Path("psu_forensics_v2.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_yf() -> dict:
    p = Path("yfinance_enrichment.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def build_best_filings() -> dict[str, dict]:
    """For each ticker, pick the most recent filing that has a PSU program."""
    best: dict[str, dict] = {}
    for fn in DETAIL_SOURCES:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        for r in data:
            if r.get("error"):
                continue
            tk = (r.get("ticker") or "").upper()
            fd = r.get("filing_date")
            if not tk or not fd:
                continue
            if not r.get("has_psu_program"):
                # Allow inducement filings without explicit has_psu_program
                if fn != "induce_detail.json":
                    continue
                if not (r.get("stock_price_hurdles") or []):
                    continue
            existing = best.get(tk)
            if not existing or fd > (existing.get("filing_date") or ""):
                best[tk] = dict(r)
                best[tk]["_source"] = fn
    return best


def pattern_match_score(r: dict, fz: dict | None) -> tuple[float, list[str]]:
    """0..100 measuring how closely this filing matches the best-in-set
    PSU archetypes. Pre-freshness."""
    score = 0.0
    reasons: list[str] = []

    per_share = r.get("per_share_metrics") or []
    aggregate = r.get("aggregate_metrics") or []
    hurdles = r.get("stock_price_hurdles") or []
    discretionary = r.get("discretionary_language")
    retirement = r.get("retirement_language")
    repricing = r.get("repricing_language")
    front_loaded = r.get("front_loaded_language")
    transformation = r.get("transformation_signal")
    double_trigger = r.get("double_trigger")
    single_trigger = r.get("single_trigger")
    has_cic_table = r.get("has_cic_table")
    alignment = r.get("alignment") or 0
    upside_kicker = r.get("upside_kicker") or 0

    # 1. PER-SHARE METRIC STACK (the cleanest archetype)
    ps_set = set(per_share)
    n_ps = len(ps_set)
    if "roiic" in ps_set or "roic" in ps_set:
        score += 14
        which = "ROIIC" if "roiic" in ps_set else "ROIC"
        reasons.append(f"{which} metric (per-share return)")
    if "fcf_per_share" in ps_set:
        score += 10
        reasons.append("FCF/share metric")
    if "tsr" in ps_set:
        score += 6
    if "eps" in ps_set:
        score += 6
    if n_ps >= 3:
        score += 8
        reasons.append(f"{n_ps} per-share metrics (deep stack)")
    elif n_ps >= 2:
        score += 4

    # 2. AGGREGATE METRIC PENALTY
    n_agg = len(set(aggregate))
    if n_agg >= 2 and n_ps == 0:
        score -= 10
        reasons.append("aggregate-only metrics (no per-share)")
    elif n_agg >= 2:
        score -= 4

    # 3. STOCK PRICE HURDLE LADDER (plausibility-gated)
    #
    # PSU stock-price hurdles are economic vesting triggers and almost
    # always fall within ~5x the grant-date share price (think Tesla,
    # PLBY $20 hurdles vs $1.70 spot, NNBR multi-tranche).  Hurdles
    # >5x current usually came from comp/ownership tables ("$200K
    # ownership multiple", "$900 director fee") that pollute the regex.
    # Cap each captured hurdle at MAX_PLAUSIBLE_MULTIPLE * current_price
    # so the ladder credit reflects real economic stretch, not extraction
    # noise.
    MAX_PLAUSIBLE_MULTIPLE = 8.0
    px_now = r.get("current_price") or 0
    raw_distinct = sorted(set(h for h in hurdles if isinstance(h, (int, float))))
    if px_now and px_now > 0:
        distinct = [h for h in raw_distinct if h <= px_now * MAX_PLAUSIBLE_MULTIPLE]
        n_filtered = len(raw_distinct) - len(distinct)
        if n_filtered:
            reasons.append(f"filtered {n_filtered} implausible hurdles (>{MAX_PLAUSIBLE_MULTIPLE:.0f}x current)")
    else:
        distinct = raw_distinct
    if len(distinct) >= 5:
        score += 18
        reasons.append(f"{len(distinct)}-tranche price ladder ${distinct[0]:.0f}-${distinct[-1]:.0f}")
    elif len(distinct) >= 3:
        score += 12
        reasons.append(f"{len(distinct)}-tranche price ladder ${distinct[0]:.0f}-${distinct[-1]:.0f}")
    elif len(distinct) >= 1:
        score += 5

    # 4. UPSIDE KICKER (max hurdle vs current price) -- uses
    # plausibility-filtered ladder, so a $900 stray no longer scores
    # 12 points for a $48 stock.
    px = px_now
    if distinct and px and px > 0:
        top_h = distinct[-1]
        mult = top_h / px
        if mult >= 5:
            score += 12
            reasons.append(f"top hurdle ${top_h:.0f} = {mult:.1f}x current ${px:.2f}")
        elif mult >= 3:
            score += 8
            reasons.append(f"top hurdle ${top_h:.0f} = {mult:.1f}x current")
        elif mult >= 2:
            score += 4

    # 5. GOVERNANCE QUALITY (CIC, triggers)
    if double_trigger:
        score += 8
        reasons.append("double-trigger CIC")
    if single_trigger:
        score -= 8
        reasons.append("single-trigger CIC (penalty)")
    if has_cic_table and not single_trigger:
        score += 3

    # 6. CLEAN LANGUAGE (anti-gaming)
    if discretionary:
        score -= 10
        reasons.append("discretionary language (gameable)")
    if retirement:
        score -= 6
        reasons.append("retirement carveout")
    if repricing:
        score -= 8
        reasons.append("repricing language")

    # 7. TRANSFORMATION / FRONT-LOAD
    if transformation:
        score += 12
        reasons.append("transformation signal")
    elif front_loaded:
        score += 6
        reasons.append("front-loaded grant")

    # 8. FORENSICS OVERLAY (when available)
    if fz:
        f = fz.get("forensics") or {}
        psu_pct = (f.get("lti_mix") or {}).get("psu_pct")
        if psu_pct:
            if psu_pct >= 70:
                score += 14
                reasons.append(f"PSU {psu_pct}% of LTI (very heavy)")
            elif psu_pct >= 55:
                score += 10
                reasons.append(f"PSU {psu_pct}% of LTI (heavy)")
            elif psu_pct >= 40:
                score += 5
        pp = f.get("performance_periods_yrs") or []
        if pp and max(pp) >= 4:
            score += 6
            reasons.append(f"{max(pp)}-yr performance window")
        elif pp and max(pp) == 3:
            score += 3
        pc = f.get("plan_changes") or {}
        plan_change_kicker = 0
        for k in ("new_metric_added", "vest_period_extended",
                  "ownership_requirements_added", "single_trigger_reduced",
                  "shareholder_feedback_response", "plan_change_announced"):
            if pc.get(k):
                plan_change_kicker += 4
        if plan_change_kicker:
            score += min(12, plan_change_kicker)
            reasons.append(f"plan evolution: {'/'.join(k for k,v in pc.items() if v)}")
        sop = f.get("say_on_pay_pct")
        if sop and sop < 70:
            score -= 8
            reasons.append(f"SOP only {sop:.0f}% (concern)")
        # NEO skin
        award_vals = f.get("neo_award_values") or []
        max_nv = max((a.get("unvested_usd") or 0 for a in award_vals), default=0)
        mc = r.get("market_cap") or 0
        if max_nv and mc:
            pct_mc = max_nv / mc * 100
            if pct_mc >= 5:
                score += 8
                reasons.append(f"NEO unvested {pct_mc:.1f}% of mcap (skin)")
            elif pct_mc >= 2:
                score += 4

    # 9. UPSIDE-KICKER MEASURE FROM EXISTING SCORING
    if upside_kicker >= 200:
        score += 6
    elif upside_kicker >= 100:
        score += 3

    return max(0.0, min(100.0, score)), reasons


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-days", type=int, default=270,
                   help="Cap on filing age (default 270d)")
    p.add_argument("--min-score", type=float, default=20.0)
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--csv", default="psu_step_change.csv")
    args = p.parse_args()

    best = build_best_filings()
    fz_map = load_forensics_v2()
    yf_d = load_yf()
    print(f"Scanning {len(best)} tickers for fresh PSU adopters", flush=True)

    rows = []
    for tk, r in best.items():
        bad, _ = is_excluded(tk)
        if bad:
            continue
        d = days_ago(r.get("filing_date"))
        if d is None or d > args.max_days:
            continue
        w = freshness_weight(d)
        if w <= 0:
            continue
        match, reasons = pattern_match_score(r, fz_map.get(tk))
        if match < 15:
            continue
        step = match * w
        if step < args.min_score:
            continue
        yd = yf_d.get(tk) or {}
        mc = r.get("market_cap") or yd.get("market_cap") or 0
        px = r.get("current_price") or yd.get("price") or 0
        rows.append({
            "ticker": tk,
            "company": (yd.get("name") or r.get("company") or "")[:50],
            "current_price": float(px or 0),
            "market_cap_musd": round((mc or 0) / 1e6, 1),
            "filing_date": r.get("filing_date"),
            "days_ago": d,
            "freshness": round(w, 2),
            "pattern_match": round(match, 1),
            "step_score": round(step, 1),
            "per_share_metrics": ",".join(r.get("per_share_metrics") or []),
            "n_hurdles": len(set(r.get("stock_price_hurdles") or [])),
            "max_hurdle": (max(r.get("stock_price_hurdles") or [0]) if (r.get("stock_price_hurdles") or []) else None),
            "double_trigger": bool(r.get("double_trigger")),
            "transformation": bool(r.get("transformation_signal")),
            "psu_pct_lti": ((fz_map.get(tk) or {}).get("forensics") or {}).get("lti_mix", {}).get("psu_pct"),
            "drawdown_pct": yd.get("drawdown_pct"),
            "p_b": yd.get("p_b"),
            "source": r.get("_source"),
            "filing_url": r.get("filing_url"),
            "reasons": " | ".join(reasons),
        })

    rows.sort(key=lambda r: r["step_score"], reverse=True)

    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "filing_date", "days_ago", "freshness",
              "pattern_match", "step_score",
              "per_share_metrics", "n_hurdles", "max_hurdle",
              "double_trigger", "transformation",
              "psu_pct_lti", "drawdown_pct", "p_b",
              "source", "filing_url", "reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nEligible: {len(rows)} | wrote {args.csv}\n")
    print(f"=== TOP {args.top} FRESH PSU ADOPTERS (step-change) ===")
    print(f"{'#':<3}{'TKR':<10}{'MCAP':>9}{'PX':>9}{'DAY':>5}{'FRS':>5}"
          f"{'MTC':>5}{'STP':>5}  REASONS")
    print("-" * 170)
    for i, r in enumerate(rows[: args.top], 1):
        print(f"{i:<3}{r['ticker']:<10}{r['market_cap_musd']:>8.0f}M"
              f"{r['current_price']:>9.2f}{r['days_ago']:>5}"
              f"{r['freshness']:>5.2f}{r['pattern_match']:>5.0f}"
              f"{r['step_score']:>5.0f}  {r['reasons'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
