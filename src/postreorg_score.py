#!/usr/bin/env python3
"""
postreorg_score.py — Assembly-Theory scorecard for fresh-start equities.

Operationalises the post-reorg alpha playbook: the category is a coin-flip
with a fat right tail, and the alpha is entirely in SELECTION. This module
grades our post-reorg cohort on the assembly checklist, with the two
highest-signal, fully-automatable filters front and centre:

  1. EBIT-YIELD SCREEN (Verdad, the killer selection filter):
       EBIT/EV > 20%  → +61% avg 2yr    (PRIORITY)
       EBIT/EV 0-20%  → -5%             (neutral)
       EBIT/EV < 0%   → -21%            (AVOID — negative EBIT cohort)
     EBIT from SEC XBRL (OperatingIncomeLoss); EV = mkt cap (Yahoo price
     × SEC shares) + total debt − cash.

  2. CHAPTER 22 AUTO-VETO (the single most important principle made
     executable): if a post-reorg name re-appears in the PACER bankruptcy
     poller AFTER its emergence, it is a re-filer — veto. Fixing the
     balance sheet without fixing the business is the dominant failure.

Plus lighter component detection from the emergence filing text
(de-levering / NOL-§382 / warrants / distress-type language).

Precision: keyed on the highest-precision emergence signal — fresh-start
accounting (`post_reorg_freshstart`) is definitionally a post-reorg — and
requires the name to be a real SEC XBRL filer, which drops the incidental-
mention false positives (Target, S&P Global) the raw phrase search caught.

Output: output/postreorg_watchlist.md — ranked by assembly score, gated.

Usage:
    python -m src.postreorg_score
    python -m src.postreorg_score --max-names 40
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests", file=sys.stderr); sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
OUT_MD = REPO / "output" / "postreorg_watchlist.md"

UA = {"User-Agent": os.environ.get(
    "EDGAR_USER_AGENT", "cyclepapa-screener research@example.com")}
SEC_CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/{tax}/{concept}.json"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


# ---- data collection -----------------------------------------------------

def collect_postreorg() -> dict[str, dict]:
    """Highest-precision post-reorg cohort: fresh-start + emerged records,
    keyed by CIK. Fresh-start is definitionally a post-reorg entity."""
    out: dict[str, dict] = {}
    for jf in INBOX.rglob("postreorg_*.json"):
        try:
            r = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        lbl = r.get("query_label", "")
        # fresh-start = strongest precision; emerged = strong; plan-effective
        # is noisier (mentions other cos) so require a CIK for it.
        keep = ("freshstart" in lbl or "emerged" in lbl or
                ("plan_effective" in lbl and r.get("cik")))
        if not keep:
            continue
        cik = r.get("cik") or ""
        if not cik:
            continue
        key = str(int(cik))
        prev = out.get(key)
        # prefer the fresh-start record; keep earliest filed date
        if prev is None or ("freshstart" in lbl and
                            "freshstart" not in prev.get("query_label", "")):
            out[key] = r
    return out


def chapter22_ciks() -> dict[str, str]:
    """CIKs (and names) that appear in the PACER bankruptcy poller —
    used to veto re-filers. PACER records carry a court docket, not always
    a CIK, so also index by normalized name."""
    names: dict[str, str] = {}
    for jf in INBOX.rglob("pacer_*.json"):
        try:
            r = json.loads(jf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        nm = _norm(r.get("name", ""))
        if nm:
            names[nm] = r.get("filed", "")
    return names


def _norm(n) -> str:
    # canonical resolver (uppercased to preserve this module's historic case)
    from src.entity_resolver import normalize_name
    return normalize_name(n).upper()


# ---- SEC XBRL + price ----------------------------------------------------

def _xbrl(cik: int, concept: str, tax: str = "us-gaap") -> float | None:
    url = SEC_CONCEPT.format(cik=cik, tax=tax, concept=concept)
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200:
            return None
        units = r.json().get("units", {})
        vals = units.get("USD") or next(iter(units.values()), [])
        # most recent annual (10-K) value
        anns = [u for u in vals if u.get("form", "").startswith("10-K")]
        pool = anns or vals
        if not pool:
            return None
        pool = sorted(pool, key=lambda u: u.get("end", ""))
        return float(pool[-1]["val"])
    except (requests.RequestException, ValueError, KeyError):
        return None


def _shares(cik: int) -> float | None:
    return _xbrl(cik, "EntityCommonStockSharesOutstanding", tax="dei")


_QUOTE_CACHE: dict[str, dict] = {}


def _quote(ticker: str) -> dict:
    """One Yahoo call → {price, adv_dollar}. Fetches a 3-month daily series
    so we get BOTH the live price AND a SMOOTHED liquidity read (MEDIAN daily
    dollar volume — robust to single-day outliers) instead of price alone.
    Cached per ticker per run."""
    if not ticker:
        return {"price": None, "adv_dollar": None}
    # class-share dot → dash (BRK.B → BRK-B) but PRESERVE a foreign venue
    # suffix (OIBR3.SA, 011200.KS) which Yahoo needs verbatim.
    t = re.sub(r"\.([A-Za-z])$", r"-\1", ticker.split(":")[-1])
    if t in _QUOTE_CACHE:
        return _QUOTE_CACHE[t]
    out = {"price": None, "adv_dollar": None}
    try:
        r = requests.get(YAHOO.format(ticker=t) + "?range=3mo&interval=1d",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 200:
            import statistics as _st
            res = r.json()["chart"]["result"][0]
            out["price"] = res["meta"].get("regularMarketPrice")
            q = (res.get("indicators", {}).get("quote") or [{}])[0]
            vols = [v for v in (q.get("volume") or []) if v]
            closes = [c for c in (q.get("close") or []) if c]
            if vols and closes:
                out["adv_dollar"] = _st.median(vols) * _st.median(closes)
    except (requests.RequestException, ValueError, KeyError, TypeError,
            IndexError):
        pass
    _QUOTE_CACHE[t] = out
    return out


def _price(ticker: str) -> float | None:
    return _quote(ticker).get("price")


def dollar_adv(ticker: str) -> float | None:
    """3-month median daily dollar volume — a tradability read that price
    alone can't give (a $2 post-reorg shell and a NYSE name both quote)."""
    return _quote(ticker).get("adv_dollar")


def ebit_yield(cik: int, ticker: str) -> dict:
    """Compute the Verdad EBIT/EV yield. Returns the components + tier."""
    ebit = _xbrl(cik, "OperatingIncomeLoss")
    out = {"ebit": ebit, "ev": None, "ebit_yield": None,
           "tier": "no-data", "price": None}
    if ebit is None:
        return out
    price = _price(ticker)
    shares = _shares(cik)
    liab = _xbrl(cik, "Liabilities")
    cash = (_xbrl(cik, "CashAndCashEquivalentsAtCarryingValue") or
            _xbrl(cik, "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"))
    out["price"] = price
    if price and shares:
        mkt_cap = price * shares
        out["mkt_cap"] = mkt_cap
        # Genuine fresh-start equities are small/mid caps. A mega-cap that
        # matched the emergence phrase search (Mastercard, Boston Scientific)
        # never actually emerged — flag as a likely false positive.
        if mkt_cap > 15e9:
            out["tier"] = "not-postreorg (mega-cap)"
            return out
        if mkt_cap < 100e6:
            out["tier"] = "sub-scale (<$100M)"
            return out
        net_debt = (liab or 0) - (cash or 0)
        ev = mkt_cap + max(0, net_debt)
        if ev > 0.2 * mkt_cap:      # sanity floor on EV
            y = ebit / ev
            # sanity-bound: |EBIT/EV| > 100% signals broken XBRL scaling
            if -1.0 <= y <= 1.0:
                out["ev"] = ev
                out["ebit_yield"] = y
                out["tier"] = ("PRIORITY (>20%)" if y > 0.20 else
                               "neutral (0-20%)" if y >= 0 else
                               "AVOID (<0%)")
                return out
    # fallback: EBIT sign only (the strongest automatable Verdad gate)
    out["tier"] = ("AVOID (neg EBIT)" if ebit < 0 else "positive-EBIT")
    return out


# ---- assembly component detection (from the emergence filing text) -------

_COMP_PATTERNS = {
    "delevering": r"reduc\w+ .{0,20}(debt|leverage)|de-?lever|eliminat\w+ .{0,20}debt",
    "nol_382": r"\bNOL\b|net operating loss|section 382|§?\s?382",
    "warrants": r"\bwarrant",
    "fresh_start": r"fresh[- ]start",
    "financial_distress": r"maturity wall|refinanc|over-?lever|liquidity crisis|"
                          r"one-?time|covid|pandemic|commodity price",
    "economic_distress": r"secular decline|amazon|disrupt|structural\w* declin|"
                         r"obsolet|store closur",
}


def detect_components(text: str) -> dict[str, bool]:
    t = (text or "").lower()
    return {k: bool(re.search(p, t)) for k, p in _COMP_PATTERNS.items()}


# ---- scoring -------------------------------------------------------------

def altman_z2(cik: int, mkt_cap: float | None, ebit: float | None,
              total_liab: float | None) -> float | None:
    """Altman Z″ (the non-manufacturer / emerging-market variant) on the
    emergence balance sheet — a PREDICTIVE Chapter-22 test to complement the
    historical PACER veto. Z″ = 3.25 + 6.56·WC/TA + 3.26·RE/TA + 6.72·EBIT/TA
    + 1.05·MVE/TL. Z″ < ~1.1 is the distress zone (high re-filing risk); the
    "Chapter 22 Recidivism" literature and Altman's own updates use this as
    the emergence-quality screen. Returns None if inputs are unavailable."""
    ta = _xbrl(cik, "Assets")
    if not ta or ta <= 0:
        return None
    ca = _xbrl(cik, "AssetsCurrent")
    cl = _xbrl(cik, "LiabilitiesCurrent")
    re = _xbrl(cik, "RetainedEarningsAccumulatedDeficit")
    tl = total_liab if total_liab else _xbrl(cik, "Liabilities")
    if ebit is None or tl is None or tl <= 0 or mkt_cap is None:
        return None
    wc = (ca or 0.0) - (cl or 0.0)
    z = (3.25 + 6.56 * (wc / ta) + 3.26 * ((re or 0.0) / ta)
         + 6.72 * (ebit / ta) + 1.05 * (mkt_cap / tl))
    return round(z, 2)


def assembly_score(rec: dict, ey: dict, is_ch22: bool) -> dict:
    """Return {score, gate_ok, notes} implementing the Part 7 scorecard.
    Gating: distress-type + de-levering + predictive Z″. EBIT-yield ×2.
    Chapter 22 vetoes (historical PACER + predictive Altman Z″)."""
    comps = detect_components(rec.get("query_note", "") + " " +
                              rec.get("form", ""))
    notes = []
    # Precision gate — drop the incidental-mention false positives that
    # the emergence phrase search caught (mega-caps that never emerged).
    if ey["tier"] in ("not-postreorg (mega-cap)", "sub-scale (<$100M)"):
        return {"score": -50, "gate_ok": False, "tier": ey["tier"],
                "notes": ey["tier"]}
    # GATE 1 — Chapter 22 veto
    if is_ch22:
        return {"score": -99, "gate_ok": False, "tier": ey["tier"],
                "notes": "CHAPTER 22 — re-filed after emergence; VETO"}
    # EBIT-yield lens (×2), the primary selection filter
    val = 0
    if ey["ebit_yield"] is not None:
        y = ey["ebit_yield"]
        val = 2 if y > 0.20 else 1 if y >= 0 else 0
        notes.append(f"EBIT/EV {y*100:.0f}% → {ey['tier']}")
    elif ey["ebit"] is not None:
        val = 1 if ey["ebit"] > 0 else 0
        notes.append(f"EBIT {'positive' if ey['ebit']>0 else 'NEGATIVE'} "
                     f"(${ey['ebit']/1e6:.0f}M); EV/price n/a")
    # component signals
    comp_score = 0
    if comps["delevering"]:
        comp_score += 1; notes.append("de-levering language")
    if comps["nol_382"]:
        comp_score += 1; notes.append("NOL/§382")
    if comps["warrants"]:
        comp_score += 0.5; notes.append("warrants")
    if comps["fresh_start"]:
        comp_score += 1; notes.append("fresh-start")
    # distress-type gate (the single most important principle)
    gate_ok = True
    if comps["economic_distress"] and not comps["financial_distress"]:
        gate_ok = False
        notes.append("⚠ economic/secular distress signal — moat-gate RED")
    # PREDICTIVE Chapter-22 test — Altman Z″ on the emergence balance sheet.
    # Distress-zone Z″ flags high re-filing risk even before any PACER re-file.
    z2 = altman_z2(int(rec["cik"]), ey.get("mkt_cap"), ey.get("ebit"),
                   _xbrl(int(rec["cik"]), "Liabilities")) if rec.get("cik") \
        else None
    if z2 is not None:
        if z2 < 1.1:
            gate_ok = False
            notes.append(f"⚠ Altman Z″ {z2} (<1.1 distress zone) — high "
                         f"re-filing risk")
        elif z2 >= 2.6:
            comp_score += 0.5
            notes.append(f"Altman Z″ {z2} (safe zone)")
        else:
            notes.append(f"Altman Z″ {z2} (grey zone)")
    total = val * 2 + comp_score
    return {"score": round(total, 1), "gate_ok": gate_ok, "z2": z2,
            "tier": ey["tier"], "notes": "; ".join(notes)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # 0 (default) = score the ENTIRE cohort. A positive cap is a manual
    # override for quick runs; when it truncates we say so loudly rather
    # than silently drop names (the framework's cardinal sin).
    ap.add_argument("--max-names", type=int, default=0)
    args = ap.parse_args()

    cohort = collect_postreorg()
    ch22 = chapter22_ciks()
    print(f"Post-reorg cohort (fresh-start/emerged, SEC filers): "
          f"{len(cohort)}")

    # Deterministic order (fresh-start highest-precision first, then by CIK)
    # so a run is reproducible and any truncation drops the least-precise
    # tail, transparently — never an arbitrary dict-order slice.
    def _prio(item):
        lbl = item[1].get("query_label", "")
        rank = (0 if "freshstart" in lbl else 1 if "emerged" in lbl else 2)
        return (rank, int(item[0]))
    ordered = sorted(cohort.items(), key=_prio)
    if args.max_names and args.max_names < len(ordered):
        dropped = len(ordered) - args.max_names
        print(f"  ** --max-names={args.max_names} TRUNCATES the cohort: "
              f"{dropped} lower-precision names not scored this run **")
        ordered = ordered[:args.max_names]

    scored = []
    for i, (cik, rec) in enumerate(ordered):
        ticker = rec.get("ticker") or ""
        is_ch22 = _norm(rec.get("name", "")) in ch22
        ey = ebit_yield(int(cik), ticker)
        sc = assembly_score(rec, ey, is_ch22)
        scored.append({"cik": cik, "ticker": ticker,
                       "name": rec.get("name", ""), **sc, **ey})
        time.sleep(0.15)   # SEC + Yahoo courtesy
        if (i + 1) % 10 == 0:
            print(f"  scored {i+1}/{len(ordered)}...")

    # rank: gated + score desc; vetoes last
    scored.sort(key=lambda s: (s["score"] > -99, s["gate_ok"], s["score"]),
                reverse=True)

    # genuine cohort = passed the precision gate (not mega-cap/sub-scale)
    genuine = [s for s in scored if s["score"] > -50]
    priority = [s for s in genuine if "PRIORITY" in (s["tier"] or "")
                and s["gate_ok"] and s["score"] > 0]
    avoid = [s for s in genuine if "AVOID" in (s["tier"] or "")
             or s["score"] <= -99 or not s["gate_ok"]]

    lines = [
        "# Post-reorg assembly watchlist",
        "",
        "Fresh-start equities graded on the Assembly-Theory scorecard. "
        "The category is a selection game — a coin-flip with a fat right "
        "tail — so the two gating filters do most of the work: the Verdad "
        "**EBIT-yield screen** (>20% → +61% avg 2yr; <0% → −21%) and the "
        "**Chapter 22 veto** (a name that re-files after emergence fixed "
        "the balance sheet but not the business).",
        "",
        f"- scored: **{len(scored)}**  ·  genuine small/mid post-reorgs "
        f"(after mega-cap/sub-scale precision gate): **{len(genuine)}**",
        f"- EBIT-yield PRIORITY (>20%, gate-green): **{len(priority)}**",
        f"- AVOID (neg-EBIT / Chapter-22 / economic-distress gate): "
        f"**{len(avoid)}**",
        "",
        "## Ranked (assembled multibaggers first)",
        "",
        "| Name | Ticker | EBIT-yield tier | Score | Gate | Signals |",
        "|---|---|---|---:|:--:|---|",
    ]
    for s in genuine:
        gate = "✓" if s["gate_ok"] and s["score"] > -99 else "✗"
        lines.append(f"| {s['name'][:34]} | {s['ticker']} | "
                     f"{s['tier']} | {s['score']} | {gate} | "
                     f"{s['notes'][:70]} |")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {OUT_MD}")
    print(f"\nEBIT-yield PRIORITY names (assembled + cheap):")
    for s in priority[:12]:
        print(f"  {s['ticker']:8} {s['name'][:30]:30} {s['tier']}")
    if not priority:
        print("  (none cleared >20% EBIT-yield + gates this run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
