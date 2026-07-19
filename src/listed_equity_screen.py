#!/usr/bin/env python3
"""
listed_equity_screen.py — the listed-equity reorganization filter.

The post-reorg universe you can actually TRADE is narrower than the
assembly playbook implies. Private claims, DIP paper, non-transferable
rights, backstop allocations and creditor-only securities are all off the
table for a public-equity book. The usable set is exactly:

    exchange-listed common equity, buyable during or after a
    reorganization.

Within that set the document's sweet spot is a single sentence:

    "A newly listed common equity, distributed to unnatural owners, with a
     genuinely repaired balance sheet, an overstated share count or
     net-debt burden, and a dated catalyst that broadens the natural
     shareholder base."

This module turns that sentence into a six-question screen and tags each
name with the highest-ranked, automatable entry archetypes:

  Q1 LISTED       is it exchange-listed common you can buy?         (gate)
  Q2 UNNATURAL    distributed to creditors → forced-seller overhang
  Q3 REPAIRED     balance sheet genuinely de-levered (net cash / low ND)
  Q4 OVERSTATED   share count (reserve to cancel) or net-debt overstated
  Q5 CATALYST     dated event that broadens the natural shareholder base
  Q6 QUALITY      clears the Verdad EBIT-yield / positive-EBIT quality bar

Archetypes detected (document's ranked order, top five first):
  A1 forced-creditor-distribution overhang   (Q2)  — the #1 setup
  A2 post-secondary clearing                 (Q2)  — supply exhaustion
  A3 excess-emergence-cash                    (Q3/Q4) — net-cash mispricing
  A4 share-reserve cancellation               (Q4)  — share-count overstate
  A5 refinancing convexity                    (Q3)  — debt-market lead
  + lighter tags: buyback-after-forced-selling, uplisting/index catalyst,
    NOL-driven FCF, strategic-sale-ready, first-clean-quarter.

Reuses the fresh-start cohort collector and the SEC-XBRL / Yahoo helpers
from postreorg_score so the two scorers stay consistent.

Output: output/listed_equity_watchlist.md — ranked by the six-question
fitness score, listed-common gate applied.

Usage:
    python -m src.listed_equity_screen
    python -m src.listed_equity_screen --max-names 80
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from src.postreorg_score import (
    collect_postreorg, chapter22_ciks, ebit_yield, _norm, _xbrl,
)

REPO = Path(__file__).resolve().parent.parent
OUT_MD = REPO / "output" / "listed_equity_watchlist.md"


# --- archetype / question text signals ------------------------------------
# Detected off the emergence filing text + query note. Quantitative
# questions (repaired B/S, overstated net-debt, quality) are computed from
# XBRL, not text.

_SIG = {
    # Q2 — distributed to unnatural owners (the forced-seller setup)
    "unnatural_owners": (
        r"distribut\w+ .{0,30}(creditor|holders? of (?:allowed )?claims|"
        r"noteholder|lender)|creditors? received|in exchange for .{0,20}claims|"
        r"new common stock .{0,30}(to|for) .{0,20}(creditor|claim)|"
        r"equitiz\w+|debt[- ]for[- ]equity|converted .{0,20}into .{0,20}equity"),
    # A2 — post-secondary clearing: a registered resale/secondary that,
    # once printed, removes the mechanical overhang.
    "secondary_clearing": (
        r"resale|secondary offering|selling stockholders?|registration rights|"
        r"S-1 .{0,20}resale|shelf .{0,20}(resale|selling)"),
    # A4 — reserved/authorized share overhang that later cancels
    "share_reserve": (
        r"reserved for issuance|management incentive plan|\bMIP\b|"
        r"equity incentive plan|shares? .{0,20}reserved|"
        r"warrant\w* .{0,30}(exercis|expir)|authoriz\w+ but unissued"),
    # A5 — refinancing convexity (debt-market lead signal)
    "refinancing": (
        r"refinanc|repric\w+|amend .{0,20}extend|maturity .{0,20}(extend|wall)|"
        r"new .{0,20}(term loan|revolver|notes)|redeem\w* .{0,20}notes"),
    # Q5 — catalyst that broadens the natural shareholder base
    "uplisting": (
        r"uplist|list\w* on .{0,10}(nyse|nasdaq)|transfer .{0,20}listing|"
        r"index inclusion|russell|s&p .{0,10}(smallcap|midcap)|"
        r"resume\w* trading|relist"),
    "buyback": (
        r"repurchase program|buyback|share repurchase|tender .{0,10}offer|"
        r"return\w* .{0,20}capital|special dividend|initiat\w+ .{0,10}dividend"),
    "nol_fcf": r"\bNOL\b|net operating loss|section 382|§?\s?382|tax attribute",
    "strategic_sale": (
        r"strategic .{0,20}(alternativ|review)|explor\w+ .{0,20}sale|"
        r"sale process|dual[- ]track|evaluat\w+ .{0,20}strategic"),
    "first_clean_quarter": (
        r"first .{0,20}(full )?quarter .{0,20}(since|after|following) emergence|"
        r"post[- ]emergence .{0,20}(results|quarter)"),
}


def _detect(text: str) -> dict[str, bool]:
    t = (text or "").lower()
    return {k: bool(re.search(p, t)) for k, p in _SIG.items()}


# --- quantitative building blocks -----------------------------------------

def balance_sheet(cik: int) -> dict:
    """Cash / debt / net-debt facts for the repaired-B/S and overstated
    net-debt questions. All from SEC XBRL (annual)."""
    cash = (_xbrl(cik, "CashAndCashEquivalentsAtCarryingValue") or
            _xbrl(cik, "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"))
    debt = (_xbrl(cik, "LongTermDebtNoncurrent") or
            _xbrl(cik, "LongTermDebt") or
            _xbrl(cik, "DebtCurrent"))
    total_debt = 0.0
    for c in ("LongTermDebtNoncurrent", "DebtCurrent", "LongTermDebtCurrent"):
        v = _xbrl(cik, c)
        if v:
            total_debt += v
    total_debt = total_debt or (debt or 0.0)
    return {"cash": cash, "total_debt": total_debt,
            "net_debt": (total_debt or 0.0) - (cash or 0.0)}


def six_questions(rec: dict, cik: int, ticker: str, ey: dict,
                  bs: dict, sig: dict, is_ch22: bool) -> dict:
    """Score the six-question listed-equity screen. Q1 is a hard gate
    (must be listed common with a live price). Returns per-question marks,
    a 0-6 fitness score, and archetype tags."""
    q = {}
    reasons = []

    # Q1 LISTED — hard gate. Real ticker + a live Yahoo price = tradable
    # exchange-listed common (not a claim, right, or creditor security).
    price = ey.get("price")
    listed = bool(ticker) and price is not None
    q["listed"] = listed
    if not listed:
        return {"listed": False, "score": 0, "fitness": 0.0,
                "archetypes": [], "reasons": ["not listed common (no live price)"],
                "marks": q}

    # Q2 UNNATURAL — distributed to creditors → structural forced sellers.
    q["unnatural"] = sig["unnatural_owners"] or sig["secondary_clearing"]
    if sig["unnatural_owners"]:
        reasons.append("distributed to creditors (forced-seller overhang)")
    elif sig["secondary_clearing"]:
        reasons.append("registered resale (secondary clearing)")

    # Q3 REPAIRED — genuinely de-levered. Net cash, or net-debt < 1× a rough
    # EBIT proxy (positive EBIT and ND/EBIT <= 3 counts as repaired).
    net_debt = bs.get("net_debt")
    ebit = ey.get("ebit")
    repaired = False
    if net_debt is not None:
        if net_debt <= 0:
            repaired = True
            reasons.append("net cash balance sheet")
        elif ebit and ebit > 0 and net_debt <= 3 * ebit:
            repaired = True
            reasons.append(f"low leverage (ND/EBIT {net_debt/ebit:.1f}×)")
    q["repaired"] = repaired

    # Q4 OVERSTATED — reported share count or net-debt overstates the true
    # economic burden. Two automatable proxies:
    #   (a) a reserved-share / MIP / warrant overhang in the filing text
    #   (b) net cash that is a large fraction of market cap (the market is
    #       pricing gross, not net — classic excess-emergence-cash setup)
    overstated = False
    mkt_cap = ey.get("mkt_cap")
    if sig["share_reserve"]:
        overstated = True
        reasons.append("reserved-share / MIP overhang (share count overstated)")
    if mkt_cap and net_debt is not None and net_debt < 0:
        net_cash = -net_debt
        if net_cash >= 0.30 * mkt_cap:
            overstated = True
            reasons.append(f"net cash = {net_cash/mkt_cap*100:.0f}% of mkt cap "
                           f"(net-debt burden overstated)")
    q["overstated"] = overstated

    # Q5 CATALYST — a dated event that broadens the natural shareholder base.
    catalyst = (sig["uplisting"] or sig["buyback"] or sig["strategic_sale"] or
                sig["first_clean_quarter"])
    q["catalyst"] = catalyst
    for k, lbl in (("uplisting", "uplisting/index inclusion"),
                   ("buyback", "buyback / capital return"),
                   ("strategic_sale", "strategic-sale review"),
                   ("first_clean_quarter", "first clean post-emergence quarter")):
        if sig[k]:
            reasons.append(lbl)

    # Q6 QUALITY — clears the Verdad quality bar (EBIT-yield > 0, ideally
    # > 20%). Chapter-22 re-filers fail quality by definition.
    tier = ey.get("tier") or ""
    y = ey.get("ebit_yield")
    quality = False
    if is_ch22:
        reasons.append("CHAPTER 22 re-filer → quality FAIL")
    elif y is not None and y > 0:
        quality = True
        reasons.append(f"EBIT/EV {y*100:.0f}% ({tier})")
    elif ebit is not None and ebit > 0:
        quality = True
        reasons.append("positive EBIT")
    q["quality"] = quality

    # --- archetype tags (document's ranked order) ---
    arche = []
    if sig["unnatural_owners"]:
        arche.append("forced-creditor overhang")           # A1 (#1)
    if sig["secondary_clearing"]:
        arche.append("post-secondary clearing")            # A2
    if q["overstated"] and mkt_cap and net_debt is not None and net_debt < 0:
        arche.append("excess-emergence-cash")              # A3
    if sig["share_reserve"]:
        arche.append("share-reserve cancellation")         # A4
    if sig["refinancing"]:
        arche.append("refinancing convexity")              # A5
    if sig["buyback"] and sig["unnatural_owners"]:
        arche.append("buyback-after-forced-selling")
    if sig["uplisting"]:
        arche.append("orphan-to-institutional")
    if sig["nol_fcf"]:
        arche.append("NOL-driven FCF")
    if sig["strategic_sale"]:
        arche.append("strategic-sale-ready")

    # fitness = the five soft questions (Q1 already gated true), + a half
    # point of conviction for each stacked archetype beyond the first.
    soft = sum(bool(q[k]) for k in
               ("unnatural", "repaired", "overstated", "catalyst", "quality"))
    fitness = soft + 0.5 * max(0, len(arche) - 1)
    if is_ch22:
        fitness = min(fitness, 1.0)   # re-filer can't rank
    return {"listed": True, "score": soft, "fitness": round(fitness, 1),
            "archetypes": arche, "reasons": reasons, "marks": q,
            "ch22": is_ch22}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # 0 (default) = screen the ENTIRE cohort. See postreorg_score for the
    # rationale — no silent truncation.
    ap.add_argument("--max-names", type=int, default=0)
    args = ap.parse_args()

    cohort = collect_postreorg()
    ch22 = chapter22_ciks()      # PACER Chapter 11 filers, normalized-name keyed
    print(f"Post-reorg cohort (fresh-start/emerged SEC filers): {len(cohort)}")

    # Definitional gate: keep only GENUINE post-reorgs. Fresh-start and
    # "emerged" language are definitional. The `plan_effective` label alone
    # is noisy — "Effective Date of the Plan" also matches employee stock /
    # benefit plans (GoDaddy, Skyworks, Federated Hermes were pure false
    # positives) — so a plan_effective-only name is admitted ONLY if it is
    # corroborated by an actual Chapter 11 filing in the PACER poller.
    def _genuine(rec) -> bool:
        lbl = rec.get("query_label", "")
        if "freshstart" in lbl or "emerged" in lbl:
            return True
        return _norm(rec.get("name", "")) in ch22
    dropped_incidental = [r for _, r in cohort.items() if not _genuine(r)]
    cohort = {k: r for k, r in cohort.items() if _genuine(r)}
    print(f"  genuine post-reorgs after definitional gate: {len(cohort)} "
          f"(dropped {len(dropped_incidental)} plan-effective-only incidental "
          f"matches — benefit-plan false positives)")

    def _prio(item):
        lbl = item[1].get("query_label", "")
        rank = (0 if "freshstart" in lbl else 1 if "emerged" in lbl else 2)
        return (rank, int(item[0]))
    items = sorted(cohort.items(), key=_prio)
    if args.max_names and args.max_names < len(items):
        dropped = len(items) - args.max_names
        print(f"  ** --max-names={args.max_names} TRUNCATES the cohort: "
              f"{dropped} lower-precision names not screened this run **")
        items = items[:args.max_names]

    scored = []
    for i, (cik, rec) in enumerate(items):
        ticker = rec.get("ticker") or ""
        is_ch22 = _norm(rec.get("name", "")) in ch22
        ey = ebit_yield(int(cik), ticker)
        # skip the mega-cap / sub-scale precision-gate false positives
        if ey["tier"] in ("not-postreorg (mega-cap)", "sub-scale (<$100M)"):
            continue
        bs = balance_sheet(int(cik))
        sig = _detect(rec.get("query_note", "") + " " + rec.get("form", "") +
                      " " + rec.get("query_label", ""))
        res = six_questions(rec, int(cik), ticker, ey, bs, sig, is_ch22)
        scored.append({"cik": cik, "ticker": ticker,
                       "name": rec.get("name", ""), **res,
                       "tier": ey.get("tier"), "ebit_yield": ey.get("ebit_yield")})
        time.sleep(0.15)
        if (i + 1) % 10 == 0:
            print(f"  screened {i+1}/{len(items)}...")

    listed = [s for s in scored if s["listed"]]
    listed.sort(key=lambda s: (s["fitness"], s["score"]), reverse=True)
    prime = [s for s in listed if s["fitness"] >= 3 and not s.get("ch22")]

    lines = [
        "# Listed-equity reorganization watchlist",
        "",
        "The tradable slice of the post-reorg universe: **exchange-listed "
        "common equity only** — no private claims, DIP paper, "
        "non-transferable rights, backstop allocations or creditor-only "
        "securities. Each name is scored on the six-question sweet-spot "
        "screen and tagged with the highest-ranked entry archetypes.",
        "",
        "> **The sweet spot:** a newly listed common equity, distributed to "
        "unnatural owners, with a genuinely repaired balance sheet, an "
        "overstated share count or net-debt burden, and a dated catalyst "
        "that broadens the natural shareholder base.",
        "",
        f"- cohort screened: **{len(scored)}**  ·  listed common (Q1 gate "
        f"passed): **{len(listed)}**  ·  prime (fitness ≥ 3): **{len(prime)}**",
        "",
        "Six questions: **L**isted · **U**nnatural owners · **R**epaired "
        "balance sheet · **O**verstated count/debt · **C**atalyst · "
        "**Q**uality (EBIT-yield).",
        "",
        "| Name | Ticker | Fit | U | R | O | C | Q | Archetypes | Why |",
        "|---|---|---:|:-:|:-:|:-:|:-:|:-:|---|---|",
    ]
    def mk(s, k):
        return "●" if s["marks"].get(k) else "·"
    for s in listed:
        arch = ", ".join(s["archetypes"][:3]) or "—"
        why = "; ".join(s["reasons"][:3])
        lines.append(
            f"| {s['name'][:30]} | {s['ticker']} | {s['fitness']} | "
            f"{mk(s,'unnatural')} | {mk(s,'repaired')} | {mk(s,'overstated')} | "
            f"{mk(s,'catalyst')} | {mk(s,'quality')} | {arch} | {why[:64]} |")

    lines += ["", "## Prime setups (fitness ≥ 3)", ""]
    if prime:
        for s in prime:
            lines.append(f"- **{s['name'][:40]}** ({s['ticker']}) — "
                         f"fitness {s['fitness']}; {', '.join(s['archetypes']) or '—'}"
                         f"  ·  {'; '.join(s['reasons'][:4])}")
    else:
        lines.append("_None cleared fitness ≥ 3 this run — the listed-common "
                     "gate plus the six-question bar is deliberately strict._")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_MD}")
    print(f"\nPrime listed-equity setups (fitness ≥ 3):")
    for s in prime[:12]:
        print(f"  {s['ticker']:8} {s['name'][:28]:28} fit {s['fitness']:>3}  "
              f"{', '.join(s['archetypes'][:2])}")
    if not prime:
        print("  (none cleared the six-question bar this run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
