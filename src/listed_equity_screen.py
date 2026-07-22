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
from datetime import date
from pathlib import Path

from src.postreorg_score import (
    collect_postreorg, chapter22_ciks, ebit_yield, _norm, _xbrl, dollar_adv,
    _price,
)


def _liquidity_tier(adv: float | None) -> str:
    """Dollar-ADV tradability band. Post-reorgs are often thin, so this is a
    FLAG, not a gate — a name is never dropped for illiquidity, only marked
    so position sizing can account for it."""
    if adv is None:
        return "?"
    if adv >= 5e6:
        return "deep"       # >$5M/day — institutionally tradable
    if adv >= 1e6:
        return "ok"         # $1-5M/day
    if adv >= 1e5:
        return "thin"       # $100k-1M/day — sizing-constrained
    return "micro"          # <$100k/day — retail-only / expert-market
from src.postreorg_verify import verify, load_cache, save_cache

# Forced-seller overhang / abnormal-return window. Eberhart, Altman &
# Aggarwal (1999, J.Finance) show post-emergence abnormal returns are
# concentrated in the first ~200 TRADING days (~9-10 months); the edge is
# front-loaded, and Jiang-Wang-Yang (2023) find the residual edge lives only
# while unnatural owners still dominate the register. So the live window is
# ~10 months, not the 24 we used — beyond it the name is a genuine post-reorg
# but the overhang has cleared. (See docs/ACADEMIC_FINDINGS.md.)
OVERHANG_MONTHS = 10


def _months_since(emergence_date: str | None) -> float | None:
    """Approximate months since an emergence-date string ('September 30,
    2014' or a bare '2021'). Returns None if unparseable."""
    if not emergence_date:
        return None
    today = date.today()
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", emergence_date)
    if m:
        months = {"january": 1, "february": 2, "march": 3, "april": 4,
                  "may": 5, "june": 6, "july": 7, "august": 8,
                  "september": 9, "october": 10, "november": 11,
                  "december": 12}.get(m.group(1).lower())
        if months:
            try:
                d = date(int(m.group(3)), months, min(int(m.group(2)), 28))
                return (today - d).days / 30.4
            except ValueError:
                pass
    ym = re.search(r"(19|20)\d{2}", emergence_date)
    if ym:
        return (today - date(int(ym.group(0)), 6, 30)).days / 30.4
    return None

REPO = Path(__file__).resolve().parent.parent
OUT_MD = REPO / "output" / "listed_equity_watchlist.md"
UNIVERSE_MD = REPO / "universe.md"

# Exchange-prefix → Yahoo suffix, so OTC and FOREIGN post-reorgs (which the
# EDGAR emergence poller can't see because the issuer deregistered / trades
# off-SEC) can still be priced and captured. OTC/US venues need no suffix.
EXCH_YAHOO = {
    "OTC": "", "OTCMKTS": "", "NYSE": "", "NASDAQ": "", "NYSEAMERICAN": "",
    "AMEX": "", "B3": ".SA", "BVMF": ".SA", "KRX": ".KS", "KOSDAQ": ".KQ",
    "OSL": ".OL", "EPA": ".PA", "XETR": ".DE", "ETR": ".DE", "FRA": ".F",
    "ST": ".ST", "STO": ".ST", "LSE": ".L", "HK": ".HK", "HKG": ".HK",
    "IDX": ".JK", "KLSE": ".KL", "SGX": ".SI", "PSE": ".PS", "NSE": ".NS",
    "BSE": ".BO", "DFM": ".AE", "TSX": ".TO", "TSXV": ".V", "ASX": ".AX",
    "TSE": ".T", "JPX": ".T", "BIT": ".MI", "BME": ".MC", "AMS": ".AS",
    "SWX": ".SW", "CSE": ".CO", "NSE(K)": ".NR",
}


_SM = None
_CIK_RESOLVE_CACHE: dict[str, str] = {}


def _resolve_cik(ticker: str) -> str:
    """Ticker → SEC CIK via the security master (US filers only). Lets a
    hand-curated US post-reorg (Peabody BTU, Warrior HCC) be scored FULLY on
    SEC financials instead of the partial OTC path. '' if not a US filer."""
    global _SM
    stem = re.sub(r"[^A-Za-z0-9]", "", (ticker or "").split(":")[-1]).upper()
    if not stem:
        return ""
    if stem in _CIK_RESOLVE_CACHE:
        return _CIK_RESOLVE_CACHE[stem]
    cik = ""
    try:
        if _SM is None:
            from src.security_master import SecurityMaster
            _SM = SecurityMaster()
        cik = _SM.cik_for_ticker(stem) or ""
    except Exception:
        cik = ""
    _CIK_RESOLVE_CACHE[stem] = cik
    return cik


def _yahoo_ticker(ticker: str) -> str:
    """Map an 'EXCHANGE:SYMBOL' ticker to a Yahoo symbol (adds the venue
    suffix for foreign listings; OTC/US pass through)."""
    if not ticker:
        return ""
    if ":" in ticker:
        exch, sym = ticker.split(":", 1)
        return sym.strip() + EXCH_YAHOO.get(exch.strip().upper(), "")
    return ticker.strip()


def universe_supplement(existing_names: set[str],
                        existing_tickers: set[str]) -> list[dict]:
    """Hand-curated post-reorgs from universe.md tagged Bucket C / C→B
    (legacy cancelled, new common = a post-reorg equity) that the EDGAR
    emergence poller cannot see because the issuer DEREGISTERED after
    emergence and trades OTC / on a foreign venue (McDermott/MCDIF, LATAM,
    OI Brazil, HMM…). Without this bridge these core names are invisible to
    an EDGAR-only funnel. Skips ones already in the EDGAR cohort and rows
    whose 'ticker' is a placeholder ('(gone)', '(private)', '—')."""
    if not UNIVERSE_MD.exists():
        return []
    out, in_table, seen = [], False, set()
    placeholder = re.compile(r"^\(|^—$|^-$|^\?+$|gone|private|delisted|"
                             r"acquired|merged|state|admin|liquidat", re.I)
    for line in UNIVERSE_MD.read_text().splitlines():
        st = line.strip()
        if set(st) <= set("-:| ") and "|" in st:
            in_table = True
            continue
        if not st.startswith("|"):
            in_table = False
            continue
        if not in_table:
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() in ("name", ""):
            continue
        name, ticker = cells[0], cells[1]
        is_c = any(c.replace(" ", "").upper().replace("->", "→").replace(
            "⇒", "→") in ("C", "C→B", "C→A", "C→") for c in cells[1:])
        if not is_c or placeholder.match(ticker) or ":" not in ticker \
                and not re.match(r"^[A-Z0-9.]{1,6}$", ticker):
            continue
        tstem = re.sub(r"[^A-Za-z0-9]", "", ticker.split(":")[-1]).upper()
        nstem = _norm(name)
        if not tstem or tstem in seen:
            continue
        if tstem in existing_tickers or nstem in existing_names:
            continue          # already caught by the EDGAR cohort
        seen.add(tstem)
        out.append({"name": name, "ticker": ticker, "bucket": "C",
                    "hand_curated": True,
                    "query_label": "tier_s.post_reorg_emerged"})
    return out


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
                  bs: dict, sig: dict, in_pacer: bool, vinfo: dict) -> dict:
    """Score the six-question listed-equity screen. Q1 is a hard gate
    (must be listed common with a live price). `in_pacer` = the filer
    appears in the PACER Chapter 11 poller, which CORROBORATES that the
    filer itself reorganized. `vinfo` is the postreorg_verify verdict
    ({filer_emerged, emergence_date, ...}) that confirms the FILER — not
    an incidentally-referenced third party — emerged, and when. Returns
    per-question marks, a 0-6 fitness score, archetype tags, and a
    confidence flag."""
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
    # This fires only for a VERIFIED filer-emergence (postreorg_verify
    # confirmed the filer itself emerged, not an incidental third-party
    # mention) that is still inside the forced-seller window. A genuine but
    # ancient emergence (Centrus, 2014) is a real post-reorg but the
    # overhang has long cleared, so it does NOT get the point.
    months = _months_since(vinfo.get("emergence_date"))
    overhang_live = (bool(vinfo.get("filer_emerged")) and months is not None
                     and months <= OVERHANG_MONTHS)
    q["unnatural"] = (overhang_live or sig["secondary_clearing"])
    if overhang_live:
        reasons.append(f"filer emerged {vinfo.get('emergence_date')} "
                       f"(~{months:.0f}mo ago) — live forced-seller overhang")
    elif vinfo.get("filer_emerged") and months is not None:
        reasons.append(f"filer emerged {vinfo.get('emergence_date')} "
                       f"(~{months:.0f}mo ago) — overhang likely cleared")
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
    # > 20%).
    tier = ey.get("tier") or ""
    y = ey.get("ebit_yield")
    quality = False
    if y is not None and y > 0:
        quality = True
        reasons.append(f"EBIT/EV {y*100:.0f}% ({tier})")
    elif ebit is not None and ebit > 0:
        quality = True
        reasons.append("positive EBIT")
    q["quality"] = quality

    # --- archetype tags (document's ranked order) ---
    arche = []
    if overhang_live or sig["unnatural_owners"]:
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
    # confidence: the filing was read and the FILER's own emergence
    # confirmed (postreorg_verify) or the filer is in the PACER Chapter 11
    # poller = hard-confirmed. A filing we couldn't fetch stays unverified.
    if vinfo.get("filer_emerged") or in_pacer:
        confidence = "confirmed"
    else:
        confidence = "unverified"
    return {"listed": True, "score": soft, "fitness": round(fitness, 1),
            "archetypes": arche, "reasons": reasons, "marks": q,
            "confidence": confidence,
            "emergence_date": vinfo.get("emergence_date")}


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
        # A Q-suffix ticker means the security is STILL IN Chapter 11
        # (pending emergence) — not yet a tradable post-reorg common.
        if rec.get("pre_emergence"):
            return False
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

    # Bridge in hand-curated OTC / foreign post-reorgs from universe.md that
    # the EDGAR poller can't see (deregistered issuers like McDermott/MCDIF).
    have_names = {_norm(r.get("name", "")) for _, r in items}
    have_tks = {re.sub(r"[^A-Za-z0-9]", "", (r.get("ticker") or "").split(":")[-1]
                       ).upper() for _, r in items}
    supplement = universe_supplement(have_names, have_tks)
    for j, rec in enumerate(supplement):
        items.append((f"UNIV{j}", rec))    # synthetic key; cik resolved later
    print(f"  + {len(supplement)} hand-curated OTC/foreign post-reorgs from "
          f"universe.md (Bucket C, EDGAR-invisible)")

    vcache = load_cache()
    scored = []
    incidental = []   # filing referenced ANOTHER issuer's emergence — dropped
    for i, (cik, rec) in enumerate(items):
        ticker = rec.get("ticker") or ""
        in_pacer = _norm(rec.get("name", "")) in ch22

        # --- hand-curated post-reorg from universe.md ---
        if rec.get("hand_curated"):
            # If it's a US filer with a resolvable CIK (Peabody BTU, Warrior
            # HCC…), score it FULLY on SEC financials — it was only missing
            # because its emergence is old and absent from recent filings.
            rc = _resolve_cik(ticker)
            if rc:
                cik = rc
                vinfo = {"filer_emerged": True, "emergence_date": None,
                         "context": ""}
                # fall through to the normal EDGAR scoring path below
            else:
                # Genuinely OTC / foreign / deregistered (MCDIF, OI, LATAM):
                # price via Yahoo, liquidity read, flag SEC-data-unavailable.
                yt = _yahoo_ticker(ticker)
                price = _price(yt)
                adv = dollar_adv(yt)
                marks = {"listed": price is not None, "unnatural": False,
                         "repaired": False, "overstated": False,
                         "catalyst": False, "quality": False}
                scored.append({
                    "cik": "", "ticker": ticker, "name": rec.get("name", ""),
                    "listed": price is not None, "score": 0, "fitness": 0.0,
                    "archetypes": ["hand-curated post-reorg"],
                    "reasons": ["universe.md Bucket C (OTC/foreign; SEC "
                                "financials unavailable — verify manually)"],
                    "marks": marks, "confidence": "hand-curated",
                    "emergence_date": None, "adv_dollar": adv,
                    "liquidity": _liquidity_tier(adv),
                    "tier": "no SEC data (OTC/deregistered)",
                    "ebit_yield": None})
                time.sleep(0.1)
                continue

        # Verify the FILER itself emerged (not an incidental third-party
        # mention). PACER-corroborated + resolved hand-curated names are
        # already confirmed, so skip the fetch for them.
        if rec.get("hand_curated") or in_pacer:
            vinfo = {"filer_emerged": True, "emergence_date": None,
                     "context": ""}
        else:
            vinfo = verify(int(cik), rec.get("accession", ""), vcache,
                           filer_name=rec.get("name", ""))
        if vinfo.get("filer_emerged") is False:
            # Could not confirm the FILER's own emergence: the only
            # bankruptcy reference is a third-party/subsidiary possessive.
            # This is usually an incidental mention (Eastman→Solutia) but
            # can be a genuine parent/sub emergence (PG&E Corp → the
            # Utility), so it is set aside for verification, NOT scored and
            # NOT silently dropped — every name is listed with its context.
            incidental.append({"ticker": ticker, "name": rec.get("name", ""),
                               "context": vinfo.get("context", "")})
            continue
        ey = ebit_yield(int(cik), ticker)
        # skip the mega-cap / sub-scale precision-gate false positives
        if ey["tier"] in ("not-postreorg (mega-cap)", "sub-scale (<$100M)"):
            continue
        bs = balance_sheet(int(cik))
        sig = _detect(rec.get("query_note", "") + " " + rec.get("form", "") +
                      " " + rec.get("query_label", ""))
        res = six_questions(rec, int(cik), ticker, ey, bs, sig, in_pacer, vinfo)
        adv = dollar_adv(ticker)   # cached from the ebit_yield price fetch
        scored.append({"cik": cik, "ticker": ticker,
                       "name": rec.get("name", ""), **res,
                       "adv_dollar": adv, "liquidity": _liquidity_tier(adv),
                       "tier": ey.get("tier"), "ebit_yield": ey.get("ebit_yield")})
        time.sleep(0.15)
        if (i + 1) % 10 == 0:
            print(f"  screened {i+1}/{len(items)}...")
    save_cache(vcache)
    print(f"  dropped {len(incidental)} incidental third-party emergence "
          f"references (filer itself did not emerge)")

    listed = [s for s in scored if s["listed"]]
    # rank by fitness, then hard-confirmed (PACER) above text-matched, then score
    listed.sort(key=lambda s: (s["fitness"], s.get("confidence") == "confirmed",
                               s["score"]), reverse=True)
    prime = [s for s in listed if s["fitness"] >= 3]
    confirmed = [s for s in listed if s.get("confidence") == "confirmed"]

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
        f"passed): **{len(listed)}**  ·  prime (fitness ≥ 3): **{len(prime)}**  "
        f"·  filer-emergence confirmed: **{len(confirmed)}**  ·  set aside "
        f"for verification (filer's own emergence unconfirmed): "
        f"**{len(incidental)}**",
        "",
        "Six questions: **L**isted · **U**nnatural owners (live forced-seller "
        "overhang) · **R**epaired balance sheet · **O**verstated count/debt · "
        "**C**atalyst · **Q**uality (EBIT-yield). **Conf** `✓` = the filing "
        "was read and the FILER's own emergence confirmed (first-person or "
        "Successor/Predecessor fresh-start reporting), or PACER-corroborated; "
        "`~` = kept but unverified (emergence note not found in the fetched "
        "filing — kept, never dropped). Names whose only bankruptcy reference "
        "is a non-filer possessive are set aside for verification at the "
        "bottom (not scored, not dropped).",
        "",
        "| Name | Ticker | Conf | Emerged | Fit | Liq | U | R | O | C | Q | Archetypes | Why |",
        "|---|---|:--:|---|---:|:--:|:-:|:-:|:-:|:-:|:-:|---|---|",
    ]
    def mk(s, k):
        return "●" if s["marks"].get(k) else "·"
    for s in listed:
        arch = ", ".join(s["archetypes"][:3]) or "—"
        why = "; ".join(s["reasons"][:3])
        conf = "✓" if s.get("confidence") == "confirmed" else "~"
        emd = s.get("emergence_date") or "—"
        lines.append(
            f"| {s['name'][:30]} | {s['ticker']} | {conf} | {emd} | "
            f"{s['fitness']} | {s.get('liquidity','?')} | "
            f"{mk(s,'unnatural')} | {mk(s,'repaired')} | {mk(s,'overstated')} | "
            f"{mk(s,'catalyst')} | {mk(s,'quality')} | {arch} | {why[:64]} |")

    lines += ["", "## Prime setups (fitness ≥ 3)", ""]
    if prime:
        for s in prime:
            conf = ("✓ filer-emergence confirmed"
                    if s.get("confidence") == "confirmed"
                    else "~ unverified (filing not fetched)")
            lines.append(f"- **{s['name'][:40]}** ({s['ticker']}) — "
                         f"fitness {s['fitness']} · {conf}; "
                         f"{', '.join(s['archetypes']) or '—'}"
                         f"  ·  {'; '.join(s['reasons'][:4])}")
    else:
        lines.append("_None cleared fitness ≥ 3 this run — the listed-common "
                     "gate plus the six-question bar is deliberately strict._")

    # Transparency: never drop silently. Show every name removed because its
    # filing referenced ANOTHER issuer's bankruptcy, with the evidence.
    if incidental:
        lines += ["", "## Set aside — filer's own emergence unconfirmed", "",
                  "The emergence full-text match here is a third-party or "
                  "subsidiary possessive, so the screen could not confirm "
                  "the FILER itself reorganized. Usually incidental (e.g. "
                  "Eastman Chemical referencing acquired Solutia's Chapter "
                  "11), but occasionally a genuine parent/subsidiary "
                  "emergence (e.g. PG&E Corp → Pacific Gas & Electric). "
                  "Not scored, not dropped — listed for manual verification.",
                  "", "| Name | Ticker | Filing context |", "|---|---|---|"]
        for e in incidental:
            ctx = (e.get("context") or "").replace("|", "/")[:80] or \
                "(bankruptcy reference is a non-filer possessive)"
            lines.append(f"| {e['name'][:30]} | {e['ticker']} | {ctx} |")

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
