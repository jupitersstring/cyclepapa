"""Step-change detector: discontinuities in PSU / incentive / governance /
capital-allocation that are *recent* and therefore likely not yet priced.

The premise: the market is slow to repronounce names where the rule of
the game just changed. The cleanest setups are:

  1. New CEO inducement grant in past 90 days (fresh deep-OTM PSU ladder)
  2. Fresh SC 13D filing in past 90 days (activist just arrived)
  3. Special committee formed in past 180 days (process just commenced)
  4. Buyback authorisation in past 180 days, especially first-ever or
     materially larger than prior program
  5. Cooperation/settlement agreement signed in past 180 days
  6. Strategic-alternatives announcement in past 180 days
  7. Spin-off declared (Form 10 / separation agreement filed)
  8. Dense recent insider buying tape (5+ F4 P-transactions in past 30 days)
  9. Material asset sale / take-private proposal in past 90 days

Each event carries a date; a step-change *freshness* multiplier is
applied: events <30d weight 1.0, <90d weight 0.7, <180d weight 0.4,
older = 0.1.

Composite is sum of weighted step-change components.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from universe_filter import is_excluded


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
        return 1.0
    if days <= 90:
        return 0.7
    if days <= 180:
        return 0.4
    if days <= 365:
        return 0.15
    return 0.0


def load_detail_jsons() -> dict[str, dict]:
    """Merge detail JSONs preserving filing dates."""
    by_tk: dict = {}
    sources = ["v2_detail.json", "wide180_detail.json", "wide365_detail.json",
               "induce_detail.json", "restruct_v10.json", "missing_v10.json",
               "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json",
               "spinoffs_detail.json"]
    for fn in sources:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            for r in data:
                if r.get("error"):
                    continue
                tk = (r.get("ticker") or "").upper()
                if not tk:
                    continue
                cur = by_tk.setdefault(tk, {
                    "ticker": tk,
                    "all_filings": [],
                })
                filing = {
                    "date": r.get("filing_date"),
                    "url": r.get("filing_url"),
                    "source": fn,
                    "has_special_committee": r.get("has_special_committee"),
                    "active_bid": r.get("active_bid"),
                    "engaged_adviser": r.get("engaged_adviser"),
                    "transformation_signal": r.get("transformation_signal"),
                    "has_debt_event": r.get("has_debt_event"),
                    "has_spinoff": r.get("has_spinoff"),
                    "go_private_language": r.get("go_private_language"),
                    "governance_reset": r.get("governance_reset"),
                    "strategic_alts_language": r.get("strategic_alts_language"),
                    "buyback_authorisation_musd": r.get("buyback_authorisation_musd"),
                    "activists_named": r.get("activists_named") or [],
                    "advisers_named": r.get("advisers_named") or [],
                    "stock_price_hurdles": r.get("stock_price_hurdles") or [],
                    "asymmetry": r.get("asymmetry") or 0,
                    "upside_kicker": r.get("upside_kicker") or 0,
                    "current_price": r.get("current_price"),
                    "market_cap": r.get("market_cap"),
                    "company": r.get("company"),
                }
                cur["all_filings"].append(filing)
                # Carry meta
                for k in ("current_price", "market_cap", "company"):
                    if filing.get(k) and not cur.get(k):
                        cur[k] = filing[k]
        except Exception:
            pass
    return by_tk


def load_form4_buys() -> dict:
    p = Path("form4_buys.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_enrichment() -> dict:
    p = Path("enrichment_overlay.json")
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


def step_change_score(r: dict, form4: dict, enr: dict,
                      yf_d: dict) -> tuple[float, list[str]]:
    """0-100, plus list of fresh signals.

    For each event class, find the most-recent occurrence and
    apply freshness weighting."""
    reasons: list[str] = []
    score = 0.0

    filings = r.get("all_filings") or []
    # Sort by date desc
    filings_sorted = sorted(
        [f for f in filings if f.get("date")],
        key=lambda f: f["date"], reverse=True,
    )

    def latest_with(field):
        for f in filings_sorted:
            if f.get(field):
                return f
        return None

    # 1. NEW CEO INDUCEMENT (8-K Item 5.02) -- transformation signal
    f = next((f for f in filings_sorted
              if f.get("source") == "induce_detail.json"
              and f.get("transformation_signal")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 25 * w
            score += pts
            reasons.append(f"New-CEO inducement (TRANSFORM, {d}d ago): +{pts:.0f}")

    # 1b. ANY inducement filing
    f = next((f for f in filings_sorted
              if f.get("source") == "induce_detail.json"
              and (f.get("stock_price_hurdles") or [])), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 12 * w
            score += pts
            reasons.append(f"Inducement w/ price hurdles ({d}d ago): +{pts:.0f}")

    # 2. FRESH 13D
    sc13d_dates = (enr or {}).get("sc13d_dates") or []
    if sc13d_dates:
        latest_13d = max(sc13d_dates)
        d = days_ago(latest_13d)
        w = freshness_weight(d)
        if w > 0:
            pts = 22 * w
            score += pts
            reasons.append(f"SC 13D filed {d}d ago: +{pts:.0f}")

    # 3. SPECIAL COMMITTEE / strategic review
    f = next((f for f in filings_sorted if f.get("has_special_committee")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 18 * w
            score += pts
            reasons.append(f"Special committee disclosed {d}d ago: +{pts:.0f}")

    # 4. ACTIVE BID
    f = next((f for f in filings_sorted if f.get("active_bid")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 20 * w
            score += pts
            reasons.append(f"Active-bid language {d}d ago: +{pts:.0f}")

    # 5. BUYBACK AUTHORISATION
    f = next((f for f in filings_sorted
              if (f.get("buyback_authorisation_musd") or 0) > 0), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        amt = f.get("buyback_authorisation_musd") or 0
        mc_m = (r.get("market_cap") or 0) / 1e6
        pct = (amt / mc_m * 100) if mc_m > 0 else 0
        if w > 0:
            # Larger buyback = bigger step change
            base = 8 if pct < 5 else (15 if pct < 10 else 25)
            pts = base * w
            score += pts
            reasons.append(f"Buyback ${amt:.0f}M ({pct:.0f}% mcap), {d}d ago: +{pts:.0f}")

    # 6. SPIN-OFF DECLARED
    f = next((f for f in filings_sorted if f.get("has_spinoff")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 15 * w
            score += pts
            reasons.append(f"Spin-off declared {d}d ago: +{pts:.0f}")

    # 7. GO-PRIVATE PROPOSAL
    f = next((f for f in filings_sorted if f.get("go_private_language")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 18 * w
            score += pts
            reasons.append(f"Go-private language {d}d ago: +{pts:.0f}")

    # 8. GOVERNANCE RESET (cooperation agreement, board refresh)
    f = next((f for f in filings_sorted if f.get("governance_reset")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0:
            pts = 16 * w
            score += pts
            reasons.append(f"Governance reset {d}d ago: +{pts:.0f}")

    # 9. STRATEGIC ALTERNATIVES LANGUAGE
    f = next((f for f in filings_sorted if f.get("strategic_alts_language")), None)
    if f:
        d = days_ago(f["date"])
        w = freshness_weight(d)
        if w > 0 and not (next((f for f in filings_sorted
                                 if f.get("has_special_committee")), None)):
            pts = 10 * w
            score += pts
            reasons.append(f"Strategic alts language {d}d ago: +{pts:.0f}")

    # 10. DENSE RECENT INSIDER F4 BUYING (past 30 days)
    f4_filings = (form4 or {}).get("filings") or []
    recent_30d = [t for t in f4_filings
                  if (days_ago(t.get("date")) or 999) <= 30]
    if len(recent_30d) >= 5:
        score += 20
        reasons.append(f"{len(recent_30d)} F4 P-buys in past 30d: +20")
    elif len(recent_30d) >= 3:
        score += 12
        reasons.append(f"{len(recent_30d)} F4 P-buys in past 30d: +12")
    elif len(recent_30d) >= 1:
        score += 5
        reasons.append(f"{len(recent_30d)} F4 P-buy(s) in past 30d: +5")

    return min(100.0, score), reasons


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--min-score", type=float, default=15.0)
    p.add_argument("--csv", default="step_change.csv")
    args = p.parse_args()

    by_tk = load_detail_jsons()
    form4 = load_form4_buys()
    enr = load_enrichment()
    yf_d = load_yf()
    print(f"Step-change analysis across {len(by_tk)} tickers", flush=True)

    rows = []
    for tk, r in by_tk.items():
        bad, _ = is_excluded(tk)
        if bad:
            continue
        ins = form4.get(tk) or {}
        e = enr.get(tk) or {}
        yd = yf_d.get(tk) or {}
        sc, reasons = step_change_score(r, ins, e, yd)
        if sc < args.min_score:
            continue
        mc = r.get("market_cap") or yd.get("market_cap") or 0
        px = r.get("current_price") or yd.get("price") or 0
        company = r.get("company") or yd.get("name") or ""
        rows.append({
            "ticker": tk,
            "company": company[:50],
            "current_price": float(px or 0),
            "market_cap_musd": round(mc / 1e6, 1),
            "step_change_score": round(sc, 1),
            "n_signals": len(reasons),
            "ret_90d_pct": yd.get("ret_90d_pct"),
            "drawdown_pct": yd.get("drawdown_pct"),
            "p_b": yd.get("p_b"),
            "reasons": " | ".join(reasons),
        })

    rows.sort(key=lambda r: r["step_change_score"], reverse=True)
    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "step_change_score", "n_signals",
              "ret_90d_pct", "drawdown_pct", "p_b", "reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nEligible: {len(rows)} | wrote {args.csv}\n")
    print(f"=== TOP {args.top} BY STEP-CHANGE SCORE ===")
    print(f"{'#':<3}{'TKR':<11}{'MCAP':>8}{'PX':>9}{'STP':>5}{'#':>3}  REASONS")
    print("-" * 160)
    for i, r in enumerate(rows[: args.top], 1):
        mc = r["market_cap_musd"]
        print(f"{i:<3}{r['ticker']:<11}{mc:>7.0f}M{r['current_price']:>9.2f}"
              f"{r['step_change_score']:>5.0f}{r['n_signals']:>3}  "
              f"{r['reasons'][:115]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
