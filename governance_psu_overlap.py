"""Governance special-situations + PSU overlap screen.

Surfaces names where BOTH legs fire:
  - PSU asymmetry: deep-OTM hurdle ladder, per-share metrics,
    transformation_signal, or upside_kicker >= 50
  AND
  - Governance / process signal: special committee, named activist
    holder, advisers engaged, active bid, controller-bid setup,
    distressed stub, board refresh / cooperation agreement, or
    spin-off in flight

Pulls from every cached *_detail.json sweep, dedups by ticker, applies
the universe filter (no SPACs / preferred / penny shells), and ranks
by a strict overlap score where the geometric mean of the two legs is
the master metric -- a name only ranks high when BOTH the PSU and the
governance sides are non-trivial.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from universe_filter import is_excluded


def load_all() -> list[dict]:
    sources = [
        "v2_detail.json", "wide180_detail.json",
        "induce_detail.json",
        "restruct_v10.json", "restruct_v7.json",  # v10 first; merge prefers max
        "targets_v4.json", "missing_v8.json", "missing_v10.json",
        "uk_v2_detail.json", "uk_detail.json",
    ]
    rows: list[dict] = []
    for fn in sources:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            for r in data:
                r["_source"] = fn
            rows.extend(data)
        except Exception:
            pass
    return rows


def load_enrichment_overlay() -> dict[str, dict]:
    """SC 13D + Form 4 batch overlay (US)."""
    p = Path("enrichment_overlay.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_rns_overlay() -> dict[str, dict]:
    """UK RNS keyword overlay."""
    p = Path("uk_rns_overlay.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def apply_enrichment(merged: dict[str, dict]) -> None:
    """Patch in 13D / Form 4 / RNS overlays. Called after merge_by_ticker."""
    enr = load_enrichment_overlay()
    rns = load_rns_overlay()
    for tk, r in merged.items():
        e = enr.get(tk)
        if e:
            for key in ("sc13d_filings_1y", "sc13d_dates",
                        "insider_form4_count_90d", "insider_form4_dates",
                        "insider_buying_evidence"):
                if e.get(key) is not None:
                    cur = r.get(key)
                    if cur in (None, 0, False, []) or (
                        isinstance(cur, (int, float))
                            and (e.get(key) or 0) > cur):
                        r[key] = e[key]
        n = rns.get(tk)
        if n:
            r["rns_signal_count"] = n.get("rns_signal_count", 0)
            r["rns_keywords"] = {k: v for k, v in n.items()
                                 if isinstance(v, int) and v > 0
                                 and k != "rns_signal_count"}
            r["news_titles"] = n.get("news_titles") or []


def merge_by_ticker(rows: list[dict]) -> dict[str, dict]:
    """Merge by ticker -- keep the row with the highest psu+gov composite,
    but pull the union of signal flags from ALL filings for the ticker
    (since governance signals may live in a different filing than PSU)."""
    by_ticker: dict[str, dict] = {}
    for r in rows:
        if r.get("error"):
            continue
        tk = (r.get("ticker") or "").upper()
        if not tk:
            continue
        if tk not in by_ticker:
            by_ticker[tk] = dict(r)
            by_ticker[tk]["_sources"] = [r.get("_source")] if r.get("_source") else []
        else:
            # Union flags: keep True if either filing had it.
            cur = by_ticker[tk]
            for key in ("has_special_committee", "strategic_alts_language",
                        "engaged_adviser", "active_bid",
                        "majority_of_minority", "has_debt_event",
                        "has_spinoff", "go_private_language",
                        "governance_reset", "insider_buying_language",
                        "transformation_signal", "creditor_board_control",
                        "going_concern", "insider_buying_evidence"):
                cur[key] = cur.get(key) or r.get(key)
            # Union list fields
            for key in ("activists_named", "advisers_named",
                        "stock_price_hurdles", "compound_screens"):
                a = cur.get(key) or []
                b = r.get(key) or []
                cur[key] = list(dict.fromkeys(a + b))
            # Take max numeric
            for key in ("asymmetry", "alignment", "upside_kicker",
                        "process_quality", "strategic_review",
                        "change_of_control", "buyback_score",
                        "controller_score", "activist_score",
                        "board_score", "financing_score",
                        "special_situations_score", "distressed_stub_score",
                        "munger_composite", "balance_sheet_convexity",
                        "common_preservation", "catalyst_hardness",
                        "buyback_authorisation_musd", "debt_reduced_musd",
                        "participation_pct", "largest_owner_pct",
                        "insiders_group_pct", "sc13d_filings_1y",
                        "insider_form4_count_90d"):
                a = cur.get(key) or 0
                b = r.get(key) or 0
                if (b or 0) > (a or 0):
                    cur[key] = b
            # Keep the most recent filing_date and prefer non-empty company
            if (r.get("filing_date") or "") > (cur.get("filing_date") or ""):
                cur["filing_date"] = r.get("filing_date")
                cur["filing_url"] = r.get("filing_url")
            if not cur.get("company") and r.get("company"):
                cur["company"] = r.get("company")
            if not cur.get("current_price") and r.get("current_price"):
                cur["current_price"] = r.get("current_price")
            if not cur.get("market_cap") and r.get("market_cap"):
                cur["market_cap"] = r.get("market_cap")
    return by_ticker


def psu_leg(r: dict) -> float:
    """0-100. Strongest of: PSU asymmetry, OTM-ladder kicker, transformation.

    Filters: hurdle values producing >50x moneyness are treated as
    parser noise (fee tables, aggregate share amounts), not vest hurdles."""
    asym = r.get("asymmetry") or 0
    kick = r.get("upside_kicker") or 0
    bonus = 15 if r.get("transformation_signal") else 0
    h = r.get("stock_price_hurdles") or []
    px = r.get("current_price") or 0
    ladder_kicker = 0
    plausible = [v for v in h if px > 0 and 1.0 < v / px <= 30.0]
    if plausible and px > 0:
        moneyness = max(plausible) / px
        if moneyness >= 1.5:
            ladder_kicker = min(100, (moneyness - 1.0) * 50.0)
    return min(100.0, max(asym, kick, ladder_kicker) + bonus)


def plausible_hurdles(r: dict) -> list[float]:
    h = r.get("stock_price_hurdles") or []
    px = r.get("current_price") or 0
    if not px:
        return h
    return [v for v in h if 1.0 <= v / px <= 30.0]


def gov_leg(r: dict) -> float:
    """0-100. Strongest governance/process signal across all detectors.

    Includes UK RNS keyword overlay AND a synthetic process score
    rebuilt from the merged flag set -- so a name whose Jan filing has
    a committee, March filing has activists, and a separate filing has
    advisers all get credited together rather than capped by each
    filing's individual process_quality score."""
    pq = r.get("process_quality") or 0
    ds = r.get("distressed_stub_score") or 0
    sr = r.get("strategic_review") or 0
    ac = r.get("activist_score") or 0
    cc = r.get("change_of_control") or 0

    # Synthetic process score from merged flag union.
    syn = 0.0
    if r.get("has_special_committee"):
        syn += 35
    if r.get("strategic_alts_language"):
        syn += 15
    if r.get("engaged_adviser") or (r.get("advisers_named") or []):
        syn += 15
    if r.get("activists_named") or (r.get("sc13d_filings_1y") or 0) > 0:
        syn += 25
    if r.get("active_bid"):
        syn += 15
    if r.get("has_debt_event"):
        syn += 10
    if r.get("has_spinoff"):
        syn += 10
    if r.get("go_private_language"):
        syn += 15
    if r.get("governance_reset"):
        syn += 10
    if r.get("majority_of_minority"):
        syn += 10
    if (r.get("buyback_authorisation_musd") or 0) > 0:
        syn += 5
    syn = min(100.0, syn)

    # UK RNS overlay -- treat each keyword hit as ~15 base points up to 60.
    rns_count = r.get("rns_signal_count") or 0
    rns_score = min(60.0, rns_count * 15.0) if rns_count > 0 else 0

    # Bonuses for primary-source signals
    bonus = 0
    if (r.get("sc13d_filings_1y") or 0) > 0:
        bonus += 15
    if r.get("insider_buying_evidence"):
        bonus += 10
    if r.get("creditor_board_control"):
        bonus += 10
    if r.get("active_bid") and r.get("majority_of_minority"):
        bonus += 10
    return min(100.0, max(pq, ds, sr, ac, cc, syn, rns_score) + bonus)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--min-psu", type=float, default=15.0,
                   help="Floor on PSU leg (default 15).")
    p.add_argument("--min-gov", type=float, default=20.0,
                   help="Floor on governance leg (default 20).")
    p.add_argument("--min-price", type=float, default=0.50)
    p.add_argument("--min-mcap-musd", type=float, default=20.0)
    args = p.parse_args()

    rows = load_all()
    print(f"Loaded {len(rows)} filings across sources.")
    merged = merge_by_ticker(rows)
    print(f"Merged: {len(merged)} unique tickers.")
    apply_enrichment(merged)
    enr_hits = sum(1 for r in merged.values() if r.get("sc13d_filings_1y") or r.get("insider_buying_evidence"))
    rns_hits = sum(1 for r in merged.values() if r.get("rns_signal_count"))
    print(f"Enriched: {enr_hits} tickers got 13D/Form4 overlay; "
          f"{rns_hits} got UK RNS overlay.")

    candidates = []
    for tk, r in merged.items():
        bad, _ = is_excluded(tk, r.get("company"))
        if bad:
            continue
        px = r.get("current_price") or 0
        mc = (r.get("market_cap") or 0) / 1e6
        if px and px < args.min_price:
            continue
        if mc and mc < args.min_mcap_musd:
            continue
        psu = psu_leg(r)
        gov = gov_leg(r)
        if psu < args.min_psu or gov < args.min_gov:
            continue
        # Geometric mean -- a name only scores high when BOTH legs do.
        overlap = math.sqrt(psu * gov)
        r["_psu_leg"] = round(psu, 1)
        r["_gov_leg"] = round(gov, 1)
        r["_overlap"] = round(overlap, 1)
        candidates.append(r)

    candidates.sort(key=lambda r: r["_overlap"], reverse=True)

    print(f"\nEligible (PSU>={args.min_psu}, GOV>={args.min_gov}, "
          f"px>=${args.min_price}, mcap>=${args.min_mcap_musd}M): "
          f"{len(candidates)}\n")

    print(f"=== TOP {args.top} GOVERNANCE x PSU OVERLAP ===\n")
    for i, r in enumerate(candidates[: args.top], 1):
        tk = r["ticker"]
        co = (r.get("company") or "")[:42]
        px = r.get("current_price") or 0
        mc = (r.get("market_cap") or 0) / 1e6
        mc_s = f"${mc:.0f}M" if mc else "-"
        print(f"#{i:<2} {tk:<10} {co:<42} ${px:>7.2f}  {mc_s:>8}  "
              f"overlap={r['_overlap']:>5.1f}  psu={r['_psu_leg']:>5.1f}  "
              f"gov={r['_gov_leg']:>5.1f}")

        # Signals
        sig = []
        if r.get("transformation_signal"):
            sig.append("TRANSFORM")
        h = plausible_hurdles(r)
        if h and px > 0 and max(h) / px >= 1.5:
            sig.append(f"OTM {max(h)/px:.1f}x (${min(h):.2f}-${max(h):.2f})")
        if r.get("active_bid"):
            sig.append("BID")
        if r.get("has_special_committee"):
            sig.append("CMTE")
        if r.get("engaged_adviser") or (r.get("advisers_named") or []):
            ads = (r.get("advisers_named") or [])[:2]
            sig.append(f"ADV({','.join(ads)})" if ads else "ADV")
        if r.get("activists_named"):
            an = (r.get("activists_named") or [])[:2]
            sig.append(f"ACTIVIST({','.join(an)})")
        if (r.get("sc13d_filings_1y") or 0) > 0:
            sig.append(f"13D({r['sc13d_filings_1y']})")
        if r.get("insider_buying_evidence"):
            sig.append(f"INSIDER-BUY({r.get('insider_form4_count_90d')})")
        if (r.get("distressed_stub_score") or 0) >= 50:
            sig.append("DISTRESSED-STUB")
        if r.get("has_spinoff"):
            sig.append("SPIN-OFF")
        if r.get("go_private_language"):
            sig.append("GO-PRIVATE")
        if r.get("governance_reset"):
            sig.append("GOV-RESET")
        if (r.get("buyback_authorisation_musd") or 0) > 0:
            sig.append(f"BUYBACK(${r['buyback_authorisation_musd']:.0f}M)")
        if r.get("largest_owner_pct"):
            sig.append(f"CTRL({r['largest_owner_pct']:.0f}%)")
        if sig:
            print(f"      sigs : {' | '.join(sig)}")

        # Compound screens
        cs = r.get("compound_screens") or []
        for s in cs[:3]:
            print(f"      cmpnd: {s}")
        if r.get("filing_url"):
            print(f"      filing: {r['filing_url']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
