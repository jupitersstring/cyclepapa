"""Governance-catalysed deep discount -- well below book, and the board has
recently changed in a way that implies it will ACT on the discount.

The setup (the US analogue of Japan's PBR<1 / "Value-Up" reforms): a stock
trading well below book value is usually a value trap -- UNLESS governance
has shifted so that closing the gap becomes the board's job. The strongest
tell is a RECENT, DATED change: an activist settles for board seats, a new
CEO arrives, a strategic-review or capital-allocation committee is formed,
the chair/CEO roles are split, the board is declassified, a poison pill is
dropped, a capital-return policy / buyback / tender is adopted. Softer but
real: the latest proxy redesigned pay "in response to shareholders", ties
pay to TSR / ROE / per-share value, or survived a say-on-pay revolt.

Gate:
  1. DEEP DISCOUNT -- 0.10 <= P/B <= 0.70 (validated FMP book, fmp_book.py;
     deep tier <= 0.50),
     market cap >= $10M, positive book.
  2. RECENT GOVERNANCE CHANGE -- at least one HARD family (activist
     settlement / 13D, value committee or strategic review, capital-return
     policy / tender, CEO change, turnaround executive, or management
     committing to a shareholder action on the latest earnings call) OR two+ families
     scoring >= 8 combined. Each signal is recency-weighted: <=6 months x1.0,
     6-12 months x0.8, 12-18 months x0.5, older ignored.
Score = discount depth + recency-weighted family points + convergence
bonus + a return-capacity bonus when net cash >= 30% of market cap (the board
has capital to hand back). Tier: ACTION LIKELY (hard event <= 9 months and
2+ families) or BUILDING.

Output: governance_discount.json keyed by ticker.
"""

from __future__ import annotations

import csv
import glob
import json
from datetime import date, datetime
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "governance_discount.json"
TODAY = date.today()

# family -> (points, hard?)
FAMILY = {
    "ACTIVIST_SETTLEMENT": (10, True),   # board conceded seats / terms
    "ACTIVIST_13D":        (10, True),   # activist on the register / letter
    "VALUE_COMMITTEE":     (9, True),    # strategic-review / capital-alloc committee
    "STRATEGIC_REVIEW":    (8, True),    # review of strategic alternatives
    "CAPITAL_RETURN_POLICY": (8, True),  # return-capital policy / Dutch auction
    "TENDER_OFFER":        (7, True),
    "CEO_CHANGE":          (6, True),
    "TURNAROUND_EXEC":     (6, True),    # turnaround talent with equity-heavy pay
    "BUYBACK_AUTH":        (5, False),
    "ASSET_SALE":          (5, False),
    "CHAIR_CEO_SPLIT":     (6, False),
    "DECLASSIFY":          (6, False),
    "BOARD_REFRESH":       (5, False),
    "PILL_REMOVED":        (5, False),
    "PROXY_RESPONSIVE":    (4, False),   # pay redesigned in response to holders
    "PAY_ON_VALUE":        (2, False),   # PSU on TSR / ROE / ROIC / per-share
    "SOP_DISSENT":         (4, False),   # say-on-pay < 80% -> board under pressure
    "CIC_PREP":            (3, False),   # change-in-control terms amended
    "MDA_GOVERNANCE":      (3, False),   # MD&A governance-action language
    "MDA_CAPITAL":         (3, False),   # MD&A capital-policy language
    "MDA_UNLOCK":          (4, False),   # MD&A value-unlock language
    # earnings-call language (call_intent*.py; out-of-time AUC ~0.67 for
    # predicting buybacks / dividend step-ups / action 8-Ks, top decile ~1.9x)
    "CALL_COMMIT":         (7, True),    # top-decile act probability + committed/new
                                         # shareholder action stated on the call
    "CALL_INTENT":         (4, False),   # top-quartile act probability
    "CALL_VALUE_GAP":      (3, False),   # management says the stock is undervalued
}
# Near-universal families (PAY_ON_VALUE is in 63% of proxies) are CONTEXT:
# they add a little score but are not evidence of a governance CHANGE, so they
# don't count toward convergence, the gate, or the ACTION LIKELY tier.
CONTEXT = {"PAY_ON_VALUE"}
RERATE_FAM = {"STRATEGIC_REVIEW", "CAPITAL_RETURN", "TENDER_OFFER",
              "BUYBACK_AUTH", "ASSET_SALE"}


def _load(n):
    p = ROOT / n
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def recency(d):
    """Weight by age; None/undated -> 0.6 (still recent-source but unanchored)."""
    if not d:
        return 0.6
    try:
        age = (TODAY - datetime.strptime(str(d)[:10], "%Y-%m-%d").date()).days
    except ValueError:
        return 0.6
    if age < 0:
        return 1.0
    if age <= 183:
        return 1.0
    if age <= 365:
        return 0.8
    if age <= 548:
        return 0.5
    return 0.0


def latest_proxy():
    out = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.load(open(fn))
        except Exception:
            continue
        for r in (d if isinstance(d, list) else d.values()):
            if isinstance(r, dict) and r.get("ticker"):
                t = r["ticker"]
                if t not in out or r.get("filing_date", "") > out[t].get("filing_date", ""):
                    out[t] = r
    return out


def main() -> int:
    yq = _load("yfinance_quick.json")
    g8k = _load("governance_events_8k.json")
    act = _load("activist_letter_feed.json")
    ev8k = _load("rerate_events_8k.json")
    mda = _load("mda_scan.json")
    calls = _load("call_intent.json")
    voss = _load("voss_cic_triangulation.json")
    geo = _load("payoff_geometry.json")
    proxy = latest_proxy()
    turn = {}
    tf = ROOT / "turnaround_signal.csv"
    if tf.exists():
        for r in csv.DictReader(open(tf)):
            if (_num(r.get("score")) or 0) > 0:
                turn[r["ticker"]] = r.get("filing_date")

    # collect dated signals per ticker: fam -> (date, source, detail)
    sig: dict[str, dict] = {}

    # events the filing-level check found NOT to be real (rights-plan boilerplate
    # read as a pill removal, SPAC placements read as going-private, ...)
    phantom = set()
    for tk_, evs in _load("event_detail.json").items():
        for e in evs:
            if e.get("verdict") == "NOT AN EVENT":
                f_ = "CAPITAL_RETURN_POLICY" if e.get("family") == "CAPITAL_RETURN" else e.get("family")
                phantom.add((tk_, f_))

    def add(tk, fam, d, src, detail):
        if src == "8-K" and (tk, fam) in phantom:
            return
        cur = sig.setdefault(tk, {}).get(fam)
        if not cur or str(d or "") > str(cur[0] or ""):
            sig[tk][fam] = (d, src, detail)

    for tk, fams in g8k.items():
        for fam, info in fams.items():
            add(tk, fam, info.get("date"), "8-K", info.get("phrase"))
    for tk, a in act.items():
        if isinstance(a, dict):
            add(tk, "ACTIVIST_13D", a.get("filing_date"), a.get("source", "13D"),
                a.get("activist_match"))
    for tk, fams in ev8k.items():
        for fam, info in fams.items():
            if fam in RERATE_FAM:
                f2 = "CAPITAL_RETURN_POLICY" if fam == "CAPITAL_RETURN" else fam
                add(tk, f2, info.get("date"), "8-K", info.get("phrase"))
    for tk, v in mda.items():
        cats = (v or {}).get("categories") or {}
        dates = [h.get("date") for h in ((v or {}).get("hits") or {}).values() if h.get("date")]
        d = max(dates) if dates else None
        if "governance_action" in cats:
            add(tk, "MDA_GOVERNANCE", d, "MD&A", "governance-action language")
        if "capital_policy" in cats:
            add(tk, "MDA_CAPITAL", d, "MD&A", "capital-policy language")
        if "value_unlock" in cats:
            add(tk, "MDA_UNLOCK", d, "MD&A", "value-unlock language")
    for tk, p in proxy.items():
        d = p.get("filing_date")
        deltas = set(p.get("plan_deltas") or [])
        if deltas & {"responsive_to_shareholders", "ownership_requirement_added",
                     "psu_weight_increased", "new_metric_added"}:
            add(tk, "PROXY_RESPONSIVE", d, "DEF 14A", ", ".join(sorted(deltas))[:60])
        psm = set(p.get("per_share_metrics") or [])
        if psm & {"tsr", "roe", "roic", "book_value", "bvps", "other_per_share"}:
            add(tk, "PAY_ON_VALUE", d, "DEF 14A", "PSU on " + ", ".join(sorted(psm))[:40])
        sop = _num(p.get("say_on_pay_pct"))
        if sop is not None and sop < 80:
            add(tk, "SOP_DISSENT", d, "DEF 14A", f"say-on-pay {sop:.0f}%")
    for tk, c in calls.items():
        if not isinstance(c, dict):
            continue
        ev = c.get("evidence") or {}
        def quote(fams):
            for f in fams:
                if ev.get(f):
                    return f"“{ev[f][0]['q'][:90]}”"
            return None
        acts = [f for f in (c.get("new_families") or []) + sorted(c.get("families") or {},
                key=lambda k: -(c["families"][k])) if f in
                ("TENDER", "BUYBACK", "DIVIDEND_RETURN", "STRATEGIC_REVIEW", "MONETIZE")]
        if c.get("tier") == "ACT SIGNALLED":
            add(tk, "CALL_COMMIT", c.get("date"), "earnings call", quote(acts))
        elif c.get("tier") == "BUILDING":
            add(tk, "CALL_INTENT", c.get("date"), "earnings call", quote(acts))
        if (c.get("families") or {}).get("VALUE_GAP", 0) >= 0.8:
            add(tk, "CALL_VALUE_GAP", c.get("date"), "earnings call", quote(["VALUE_GAP"]))
    for tk, d in turn.items():
        add(tk, "TURNAROUND_EXEC", d, "8-K/proxy", "turnaround executive hired")
    for tk, v in voss.items():
        if isinstance(v, dict) and (_num(v.get("score")) or 0) > 0 and v.get("has_cic_lang"):
            add(tk, "CIC_PREP", None, "DEF 14A", "change-in-control terms")

    out = {}
    from universe_filter import is_excluded
    for tk, fams in sig.items():
        if is_excluded(tk, (yq.get(tk) or {}).get("name"))[0]:
            continue                                   # notes, preferreds, units, funds
        y = yq.get(tk) or {}
        pb, mcap = _num(y.get("p_b")), _num(y.get("mcap"))
        if pb is None or not (0.10 <= pb <= 0.70) or not mcap or mcap < 1e7:
            continue
        pts, hard, hard_recent, detail = 0.0, 0, False, {}
        for fam, (d, src, det) in fams.items():
            base, is_hard = FAMILY.get(fam, (0, False))
            w = recency(d)
            if w <= 0 or base <= 0:
                continue
            p = base * w
            pts += p
            if is_hard:
                hard += 1
                if w >= 0.8 and d:
                    try:
                        if (TODAY - datetime.strptime(str(d)[:10], "%Y-%m-%d").date()).days <= 275:
                            hard_recent = True
                    except ValueError:
                        pass
            detail[fam] = {"pts": round(p, 1), "date": d, "source": src, "detail": det}
        if not detail:
            continue
        # one earnings call is ONE source: its commitment + value-gap remarks
        # count once toward convergence / corroboration
        real = {("CALL" if f.startswith("CALL_") else f) for f in detail if f not in CONTEXT}
        n_real = len(real)
        real_pts = sum(v["pts"] for f, v in detail.items() if f not in CONTEXT)
        if not (hard >= 1 or (n_real >= 2 and real_pts >= 8)):
            continue
        disc = 10 if pb <= 0.40 else 7 if pb <= 0.55 else 4
        conv = 5 if n_real >= 3 else 2 if n_real == 2 else 0
        g = geo.get(tk) or {}
        cash = 3 if (g.get("net_cash_frac") or 0) >= 0.30 else 0
        score = disc + pts + conv + cash
        tier = "ACTION LIKELY" if (hard_recent and n_real >= 2) else "BUILDING"
        out[tk] = {
            "ticker": tk, "name": y.get("name", tk), "sector": y.get("sector"),
            "p_b": round(pb, 3), "mcap": mcap, "deep": pb <= 0.50,
            "net_cash_frac": g.get("net_cash_frac"),
            "n_families": n_real, "n_hard": hard, "tier": tier,
            "families": detail, "score": round(score, 1),
        }

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: (r["tier"] != "ACTION LIKELY", -r["score"]))
    from collections import Counter
    t = Counter(r["tier"] for r in out.values())
    print(f"wrote {OUT} ({len(out)} below-book names with a governance catalyst; {dict(t)})")
    print(f"{'TKR':<7}{'SCORE':>6}{'P/B':>6}{'FAM':>4}  {'TIER':<14} FAMILIES")
    for r in ranked[:30]:
        print(f"{r['ticker']:<7}{r['score']:>6.1f}{r['p_b']:>6.2f}{r['n_families']:>4}  "
              f"{r['tier']:<14} {', '.join(sorted(r['families']))[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
