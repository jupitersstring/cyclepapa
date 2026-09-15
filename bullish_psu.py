"""Find the most bullish, ungameable PSU setups.

"Ungameable" criteria (per-share-anchored, anti-dilution, anti-pop):
  - per_share_metrics present (EPS / FCF/share / TSR / ROIC / ROE)
  - aggregate_metrics absent or minimal (market_cap, absolute_ebitda,
    absolute_revenue without per-share qualifier are red flags)
  - stock_price_hurdles present, ideally multi-tranche
  - VWAP / trailing-average wording in the hurdle context (anti-pop)
  - discretionary_language / repricing_language / retirement_language
    all False
  - PSU has multi-year performance period

Then triangulates with insider Form 4, SC 13D, short interest, vol
spike, recent filing date, gov/PSU top-100 cross-confirmation, and
the new signals (institutional holder changes if available).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from universe_filter import is_excluded
from governance_psu_overlap import (
    load_all, merge_by_ticker, apply_enrichment, plausible_hurdles,
)


def ungameable_score(r: dict) -> tuple[int, list[str]]:
    """0-100. Higher = more shareholder-aligned PSU structure."""
    reasons = []
    s = 0

    # Per-share / return-on-capital metrics
    ps = r.get("per_share_metrics") or []
    if "tsr" in ps:
        s += 12; reasons.append("TSR metric")
    if "eps" in ps:
        s += 8; reasons.append("EPS metric")
    if "fcf_per_share" in ps:
        s += 8; reasons.append("FCF/share metric")
    if "roic" in ps:
        s += 6; reasons.append("ROIC metric")
    if "roce" in ps:
        s += 4; reasons.append("ROCE metric")
    if "roe" in ps:
        s += 4; reasons.append("ROE metric")
    if "other_per_share" in ps:
        s += 3

    # Aggregate metric penalty
    ag = r.get("aggregate_metrics") or []
    if "market_cap" in ag:
        s -= 12; reasons.append("** market_cap metric (gameable via dilution)")
    if "absolute_ebitda" in ag:
        s -= 10; reasons.append("** absolute EBITDA (gameable)")
    if "absolute_revenue" in ag:
        s -= 8; reasons.append("** absolute revenue")
    if "absolute_net_income" in ag:
        s -= 6; reasons.append("** absolute NI")
    if "absolute_op_income" in ag:
        s -= 6
    if "absolute_sales" in ag:
        s -= 6

    # Stock-price hurdles -- preference for multi-tranche ladders
    h = r.get("stock_price_hurdles") or []
    px = r.get("current_price") or 0
    plausible = [v for v in h if px > 0 and 1.0 < v / px <= 30.0]
    if len(plausible) >= 3:
        s += 22; reasons.append(f"Multi-tranche ladder ({len(plausible)} hurdles)")
    elif len(plausible) >= 2:
        s += 14; reasons.append(f"2-tranche ladder")
    elif len(plausible) == 1:
        s += 6; reasons.append("Single hurdle")
    if plausible:
        moneyness = max(plausible) / px
        if moneyness >= 3.0:
            s += 8; reasons.append(f"Top hurdle {moneyness:.1f}x current (deep OTM)")
        elif moneyness >= 1.5:
            s += 4; reasons.append(f"Top hurdle {moneyness:.1f}x current")

    # Anti-game: no discretionary, no repricing, no retirement language
    if r.get("discretionary_language"):
        s -= 18; reasons.append("** Discretionary committee override language")
    if r.get("repricing_language"):
        s -= 14; reasons.append("** Repricing / target reset language")
    if r.get("retirement_language"):
        s -= 8; reasons.append("** Retirement language (milking risk)")

    # Transformation signal (already a clean composite)
    if r.get("transformation_signal"):
        s += 12; reasons.append("PSU TRANSFORM signal")

    return max(0, min(100, int(round(s + 50)))), reasons


def triangulation_axes(r: dict) -> tuple[int, list[str]]:
    """0-100. External-corroboration tape."""
    reasons = []
    t = 0
    if (r.get("sc13d_filings_1y") or 0) >= 1:
        t += 18; reasons.append(f"13D ({r['sc13d_filings_1y']})")
    if r.get("activists_named"):
        t += 14; reasons.append(f"Activist: {(r['activists_named'] or [''])[0]}")
    if (r.get("insider_form4_count_90d") or 0) >= 10:
        t += 18; reasons.append(f"Heavy insider tape ({r['insider_form4_count_90d']})")
    elif (r.get("insider_form4_count_90d") or 0) >= 5:
        t += 12; reasons.append(f"Moderate insider tape ({r['insider_form4_count_90d']})")
    if r.get("short_pct_float") and r["short_pct_float"] >= 0.15:
        t += 10; reasons.append(f"Short {r['short_pct_float']*100:.0f}%")
    elif r.get("short_pct_float") and r["short_pct_float"] >= 0.08:
        t += 6
    if r.get("has_special_committee"):
        t += 12; reasons.append("Special committee")
    if r.get("active_bid"):
        t += 10; reasons.append("Active bid")
    if r.get("majority_of_minority"):
        t += 6; reasons.append("MoM protection")
    if r.get("has_debt_event"):
        t += 8; reasons.append("Debt event")
    if r.get("has_spinoff"):
        t += 6; reasons.append("Spin-off")
    if (r.get("buyback_authorisation_musd") or 0) > 0:
        t += 6; reasons.append(f"Buyback ${r['buyback_authorisation_musd']:.0f}M")
    if r.get("creditor_board_control"):
        t += 8; reasons.append("Creditor board control")
    if r.get("engaged_adviser") or (r.get("advisers_named") or []):
        t += 6; reasons.append("Banker engaged")
    return min(100, t), reasons


def load_accumulation() -> dict:
    p = Path("accumulation_scan.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--min-ungameable", type=int, default=50,
                   help="Floor on ungameable PSU score (default 50).")
    p.add_argument("--min-triangulation", type=int, default=20,
                   help="Floor on triangulation score (default 20).")
    p.add_argument("--require-hurdles", action="store_true",
                   help="Only keep names with at least one plausible hurdle.")
    p.add_argument("--csv", default="bullish_psu.csv")
    p.add_argument("--region", choices=["US", "UK", "INTL", "ALL"], default="ALL")
    p.add_argument("--min-mcap-musd", type=float, default=0.0,
                   help="Minimum market cap in $M (0 = no floor).")
    p.add_argument("--max-mcap-musd", type=float, default=None,
                   help="Maximum market cap in $M (None = no cap).")
    args = p.parse_args()

    rows_raw = load_all()
    merged = merge_by_ticker(rows_raw)
    apply_enrichment(merged)
    acc = load_accumulation()

    rows = []
    for tk, r in merged.items():
        bad, _ = is_excluded(tk, r.get("company"))
        if bad:
            continue
        is_uk = tk.endswith(".L")
        is_intl = any(tk.endswith(s) for s in (".AX", ".TO", ".V", ".HK", ".SI",
                                                ".T", ".DE", ".PA", ".MI", ".F"))
        is_us = "." not in tk
        if args.region == "US" and not is_us: continue
        if args.region == "UK" and not is_uk: continue
        if args.region == "INTL" and not is_intl: continue

        # Size band filter
        mc_musd = (r.get("market_cap") or 0) / 1e6
        if args.min_mcap_musd and mc_musd < args.min_mcap_musd:
            continue
        if args.max_mcap_musd and mc_musd > 0 and mc_musd > args.max_mcap_musd:
            continue

        u, u_reasons = ungameable_score(r)
        t, t_reasons = triangulation_axes(r)

        # Pull accumulation overlay
        a = acc.get(tk) or {}
        vol_spike = max(a.get("vol_spike", 0) or 0, a.get("max_4w_spike", 0) or 0)
        pos = a.get("pos_in_6m_range") if a.get("pos_in_6m_range") is not None else None
        acc_score = a.get("accumulation_score") or 0
        if vol_spike >= 3:
            t += 8; t_reasons.append(f"Vol spike {vol_spike:.1f}x")
        if pos is not None and pos <= 0.20:
            t += 8; t_reasons.append(f"At 6m low ({pos*100:.0f}%)")
        t = min(100, t)

        if u < args.min_ungameable:
            continue
        if t < args.min_triangulation:
            continue
        if args.require_hurdles:
            if not plausible_hurdles(r):
                continue

        composite = round((u * 0.55 + t * 0.45), 1)

        rows.append({
            "ticker": tk,
            "company": r.get("company") or "",
            "current_price": r.get("current_price"),
            "market_cap_musd": round((r.get("market_cap") or 0) / 1e6, 1),
            "ungameable_score": u,
            "triangulation_score": t,
            "composite": composite,
            "per_share_metrics": ", ".join(r.get("per_share_metrics") or []),
            "aggregate_metrics": ", ".join(r.get("aggregate_metrics") or []),
            "stock_price_hurdles_plausible": ", ".join(
                f"{x:.2f}" for x in plausible_hurdles(r)),
            "ladder_count": len(plausible_hurdles(r)),
            "ladder_top": max(plausible_hurdles(r)) if plausible_hurdles(r) else None,
            "ladder_top_x": (
                max(plausible_hurdles(r)) / r["current_price"]
                if plausible_hurdles(r) and r.get("current_price") else None),
            "transformation_signal": r.get("transformation_signal"),
            "discretionary_language": r.get("discretionary_language"),
            "repricing_language": r.get("repricing_language"),
            "retirement_language": r.get("retirement_language"),
            "activists_named": ", ".join(r.get("activists_named") or []),
            "advisers_named": ", ".join(r.get("advisers_named") or []),
            "has_special_committee": r.get("has_special_committee"),
            "active_bid": r.get("active_bid"),
            "majority_of_minority": r.get("majority_of_minority"),
            "has_debt_event": r.get("has_debt_event"),
            "has_spinoff": r.get("has_spinoff"),
            "buyback_authorisation_musd": r.get("buyback_authorisation_musd"),
            "sc13d_filings_1y": r.get("sc13d_filings_1y"),
            "insider_form4_count_90d": r.get("insider_form4_count_90d"),
            "short_pct_float": r.get("short_pct_float"),
            "earnings_in_days": r.get("earnings_date_days"),
            "drawdown_pct": r.get("drawdown_pct"),
            "vol_spike": vol_spike,
            "pos_in_6m_range": pos,
            "accumulation_score": acc_score,
            "filing_date": r.get("filing_date"),
            "filing_url": r.get("filing_url"),
            "ungameable_reasons": "; ".join(u_reasons),
            "triangulation_reasons": "; ".join(t_reasons),
        })

    rows.sort(key=lambda r: r["composite"], reverse=True)

    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "composite", "ungameable_score", "triangulation_score",
              "per_share_metrics", "aggregate_metrics",
              "stock_price_hurdles_plausible", "ladder_count", "ladder_top",
              "ladder_top_x",
              "transformation_signal", "discretionary_language",
              "repricing_language", "retirement_language",
              "activists_named", "advisers_named", "has_special_committee",
              "active_bid", "majority_of_minority", "has_debt_event",
              "has_spinoff", "buyback_authorisation_musd",
              "sc13d_filings_1y", "insider_form4_count_90d",
              "short_pct_float", "earnings_in_days", "drawdown_pct",
              "vol_spike", "pos_in_6m_range", "accumulation_score",
              "filing_date", "filing_url",
              "ungameable_reasons", "triangulation_reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"Bullish/ungameable PSU candidates: {len(rows)} qualifying.\n")
    print(f"{'#':<3}{'TKR':<11}{'PX':>9}{'MCAP':>7}{'CMP':>5}{'UG':>4}{'TR':>4}"
          f"{'PS':<22}  HURDLES (count, top, x)        SIGNALS")
    print("-" * 150)
    for i, r in enumerate(rows[: args.top], 1):
        ps = (r.get("per_share_metrics") or "-")[:20]
        h_cnt = r.get("ladder_count") or 0
        h_top = r.get("ladder_top") or 0
        h_x = r.get("ladder_top_x") or 0
        sigs = []
        if r.get("transformation_signal"): sigs.append("TR")
        if r.get("active_bid"): sigs.append("BID")
        if r.get("has_special_committee"): sigs.append("CMTE")
        if r.get("activists_named"): sigs.append("ACT")
        if (r.get("insider_form4_count_90d") or 0) >= 5:
            sigs.append(f"F4({r['insider_form4_count_90d']})")
        if r.get("short_pct_float") and r["short_pct_float"] >= 0.10:
            sigs.append(f"SH{r['short_pct_float']*100:.0f}%")
        if r.get("vol_spike") and r["vol_spike"] >= 3:
            sigs.append(f"VS{r['vol_spike']:.1f}x")
        sig_str = " ".join(sigs)[:50]
        px_n = r.get("current_price") or 0
        mc = r.get("market_cap_musd") or 0
        print(f"{i:<3}{r['ticker']:<11}{px_n:>9.2f}"
              f"{mc:>6.0f}M"
              f"{r['composite']:>5.0f}{r['ungameable_score']:>4}{r['triangulation_score']:>4} "
              f"{ps:<22}  "
              f"{h_cnt:>1} hurdles, top ${h_top:>7.2f} ({h_x:>4.1f}x)  "
              f"{sig_str}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
