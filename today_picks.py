"""Today's forensic risk/reward ranker.

Reads the merged universe from governance_psu_overlap, applies the new
nuance layer (confidence + adviser tier + hurdle quality + catalyst
hardness 0-5), and surfaces the best risk/reward setups TODAY.

Ranking metric:
    today_score = overlap * (0.5 + confidence/200) * recency_factor

  - overlap          geometric mean of psu_leg + gov_leg (existing screen)
  - confidence       0-100 from confidence_scoring
  - recency_factor   1.10 if filing <30d, 1.00 <90d, 0.85 <180d, 0.70 older

For each top-N row prints:
  - Catalyst hardness 0-5
  - Single best signal
  - Why-now (recency + freshness)
  - Verification questions for the analyst
  - Best/worst case payoff math at the parsed hurdle ladder
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from universe_filter import is_excluded
from confidence_scoring import (
    adviser_tier, hurdle_quality, filing_recency_days,
    confidence_score, catalyst_hardness,
)
from governance_psu_overlap import (
    load_all, merge_by_ticker, apply_enrichment,
    psu_leg, gov_leg, plausible_hurdles,
)


def recency_factor(days: int | None) -> float:
    if days is None:
        return 0.85
    if days <= 30:
        return 1.10
    if days <= 90:
        return 1.00
    if days <= 180:
        return 0.85
    return 0.70


def best_worst_case(r: dict) -> tuple[float, float, float] | None:
    """Return (downside_pct, base_pct, top_pct) using plausible hurdles
    as proxy targets. Best case = top hurdle. Base case = median
    plausible hurdle. Downside = -50% draw (back to recent low if known)."""
    h = plausible_hurdles(r)
    px = r.get("current_price") or 0
    if not h or not px:
        return None
    h_sorted = sorted(h)
    median = h_sorted[len(h_sorted) // 2]
    best = max(h_sorted)
    base_pct = (median - px) / px * 100
    top_pct = (best - px) / px * 100
    # Downside heuristic: -50% from current (or back to 52w low if much lower)
    downside_pct = -50.0
    return (downside_pct, base_pct, top_pct)


def verification_questions(r: dict) -> list[str]:
    qs: list[str] = []
    h = plausible_hurdles(r)
    px = r.get("current_price") or 0
    if h and px:
        top = max(h)
        qs.append(f"Confirm the ${top:.2f} hurdle is a vest-condition (not a "
                  "fee table or share-count): read the proxy paragraph "
                  "around the hurdle.")
    if r.get("activists_named"):
        a = r.get("activists_named")[0]
        qs.append(f"Verify {a} stake size and 13D filing date; confirm "
                  "intent (active vs passive disclosure).")
    if (r.get("sc13d_filings_1y") or 0) > 0 and not r.get("activists_named"):
        qs.append("13D detected but no named activist matched -- look up the "
                 "filer to confirm activist intent vs strategic acquirer.")
    if r.get("active_bid"):
        qs.append("Confirm the active bid is a real third-party offer, not "
                 "boilerplate change-in-control language in the comp table.")
    if r.get("has_special_committee"):
        qs.append("Verify the committee is for the deal (not audit/comp); "
                 "check 8-K date of formation.")
    if r.get("has_debt_event"):
        qs.append("Compare debt-reduced amount to current market cap "
                 "(>1.5x = BBGI-style stub convexity).")
    if (r.get("insider_form4_count_90d") or 0) >= 5:
        qs.append("Spot-check 5 of the Form 4s -- are they purchases (code P) "
                 "or sales/awards (code S/A)? Insider tape only counts if P.")
    if not qs:
        qs.append("No structural triggers detected; treat as fundamentals-only "
                  "candidate.")
    return qs


def main() -> int:
    p = argparse.ArgumentParser(description="Today's best risk/reward")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--min-psu", type=float, default=15.0)
    p.add_argument("--min-gov", type=float, default=20.0)
    p.add_argument("--min-price", type=float, default=0.50)
    p.add_argument("--min-mcap-musd", type=float, default=50.0)
    p.add_argument("--max-mcap-musd", type=float, default=None,
                   help="Optional cap on market cap in $M (default none).")
    p.add_argument("--min-confidence", type=int, default=0,
                   help="Optional confidence floor (default 0 = no filter).")
    p.add_argument("--region", choices=["US", "UK", "ALL"], default="ALL",
                   help="Filter by listing region (UK = .L suffix).")
    args = p.parse_args()

    rows = load_all()
    merged = merge_by_ticker(rows)
    apply_enrichment(merged)

    candidates = []
    for tk, r in merged.items():
        bad, _ = is_excluded(tk, r.get("company"))
        if bad:
            continue
        # Region filter
        is_uk = tk.endswith(".L") or tk.endswith(".AX") or tk.endswith(".T")
        if args.region == "US" and is_uk:
            continue
        if args.region == "UK" and not tk.endswith(".L"):
            continue
        px = r.get("current_price") or 0
        mc = (r.get("market_cap") or 0) / 1e6
        if px and px < args.min_price:
            continue
        if mc and mc < args.min_mcap_musd:
            continue
        if args.max_mcap_musd and mc and mc > args.max_mcap_musd:
            continue
        psu = psu_leg(r)
        gov = gov_leg(r)
        if psu < args.min_psu or gov < args.min_gov:
            continue
        overlap = math.sqrt(psu * gov)
        conf, conf_reasons = confidence_score(r)
        if conf < args.min_confidence:
            continue
        days = filing_recency_days(r.get("filing_date"))
        rec = recency_factor(days)
        today_score = overlap * (0.5 + conf / 200.0) * rec
        r["_psu_leg"] = round(psu, 1)
        r["_gov_leg"] = round(gov, 1)
        r["_overlap"] = round(overlap, 1)
        r["_confidence"] = conf
        r["_conf_reasons"] = conf_reasons
        r["_recency_days"] = days
        r["_recency_factor"] = rec
        r["_today_score"] = round(today_score, 1)
        r["_adviser_tier"] = adviser_tier(r.get("advisers_named"))
        r["_hurdle_quality"] = hurdle_quality(r.get("stock_price_hurdles"),
                                              r.get("current_price"))
        r["_catalyst_hardness"] = catalyst_hardness(r)
        candidates.append(r)

    candidates.sort(key=lambda x: x["_today_score"], reverse=True)

    print(f"Universe: {len(merged)} tickers; eligible {len(candidates)}.\n")
    print(f"=== TODAY'S BEST RISK/REWARD (top {args.top}) ===\n")

    for i, r in enumerate(candidates[: args.top], 1):
        tk = r["ticker"]
        co = (r.get("company") or "")[:48]
        px = r.get("current_price") or 0
        mc = (r.get("market_cap") or 0) / 1e6
        mc_s = f"${mc:.0f}M" if mc else "-"
        h = plausible_hurdles(r)

        print(f"#{i:<2} {tk:<10} {co}")
        print(f"    spot ${px:.2f}  mcap {mc_s}  filing {r.get('filing_date','?')} "
              f"({r.get('_recency_days','?')}d ago)")
        print(f"    today_score={r['_today_score']}  overlap={r['_overlap']}  "
              f"confidence={r['_confidence']}  catalyst_hardness={r['_catalyst_hardness']}/5")
        print(f"    hurdle_quality={r.get('_hurdle_quality','-')}  "
              f"adviser_tier={r.get('_adviser_tier','-')}")

        # Hurdles
        if h:
            top_h = max(h); med_h = sorted(h)[len(h)//2]
            print(f"    hurdles plausible: ${min(h):.2f} .. ${top_h:.2f} "
                  f"(median ${med_h:.2f})")

        # Best/worst
        bw = best_worst_case(r)
        if bw:
            d, b, t = bw
            print(f"    payoff: downside ~{d:+.0f}% | base (median hurdle) "
                  f"{b:+.0f}% | top hurdle {t:+.0f}%")

        # Single best headline
        sigs = []
        if r.get("transformation_signal"):
            sigs.append("PSU TRANSFORM")
        if r.get("active_bid"):
            sigs.append("ACTIVE BID")
        if r.get("has_special_committee"):
            sigs.append("SPECIAL CMTE")
        if r.get("activists_named"):
            sigs.append(f"ACTIVIST({(r.get('activists_named') or [''])[0]})")
        if (r.get("insider_form4_count_90d") or 0) >= 5:
            sigs.append(f"INSIDER-BUY({r['insider_form4_count_90d']})")
        if (r.get("distressed_stub_score") or 0) >= 50:
            sigs.append("DISTRESSED-STUB")
        if r.get("has_spinoff"):
            sigs.append("SPIN-OFF")
        if r.get("rns_signal_count"):
            kws = ",".join(list((r.get("rns_keywords") or {}).keys())[:3])
            sigs.append(f"RNS({kws})")
        if sigs:
            print(f"    signals: {' | '.join(sigs)}")

        # New yfinance enrichment columns
        ext = []
        if r.get("short_pct_float") is not None:
            ext.append(f"short={r['short_pct_float']*100:.1f}%")
        if r.get("short_ratio"):
            ext.append(f"days_to_cover={r['short_ratio']:.1f}")
        if r.get("earnings_date_days") is not None:
            ed = r['earnings_date_days']
            if -7 <= ed <= 60:
                ext.append(f"earnings_in={ed}d")
        if r.get("analyst_count") is not None:
            ext.append(f"analysts={int(r['analyst_count'])}")
        if r.get("target_mean_pct") is not None:
            ext.append(f"target={r['target_mean_pct']:+.0f}%")
        if r.get("drawdown_pct") is not None:
            ext.append(f"52w_pos={r['drawdown_pct']:.0f}%")
        if r.get("p_b") is not None:
            ext.append(f"P/B={r['p_b']:.2f}")
        if r.get("fcf_yield"):
            ext.append(f"FCF_yld={r['fcf_yield']*100:.1f}%")
        if r.get("div_yield"):
            ext.append(f"div={r['div_yield']*100:.1f}%")
        if r.get("sector"):
            ext.append(f"sector={r['sector']}")
        if ext:
            print(f"    fundamentals: {' | '.join(ext)}")

        # Reasons
        rr = r.get("_conf_reasons") or []
        for reason in rr[:6]:
            print(f"    + {reason}")

        # Verification
        for q in verification_questions(r):
            print(f"    ? {q}")

        if r.get("filing_url"):
            print(f"    url: {r['filing_url']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
