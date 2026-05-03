"""Special-situations layer (Bastian / Kingdom Capital playbook +
Gabelli / Greenblatt / Greenbackd / academic extensions).

Detectors and scoring for situations where the catalyst is a corporate
event rather than a comp grant -- distressed equity stubs, spin-offs,
cash shells, going-concern resets, controller take-privates, asset
liquidations, activist-forced governance changes.

Generalised algorithm:
    Special Situations Score =
        25% Hard Catalyst Score
      + 20% Balance Sheet Convexity
      + 15% Common Equity Survival
      + 10% Float / Neglect
      + 10% Insider / Creditor / Activist Alignment
      + 10% Business Runway
      + 10% Post-Event Re-rating Potential

Scope: pure-text detectors over the same EDGAR documents the PSU
pipeline already pulls. Numeric inputs (debt principal reduced,
participation rate, market cap, net cash) come from the document text
where surfaceable; degrade gracefully when not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Pattern banks
# ---------------------------------------------------------------------------

# A. Distressed equity stub / debt-haircut event (BBGI / RGS pattern) -------
DEBT_EVENT = re.compile(
    r"\b(exchange offer|consent solicitation|tender offer|"
    r"transaction support agreement|restructuring support agreement|"
    r"forbearance agreement|waiver and amendment|"
    r"credit agreement amendment|debt exchange|notes exchanged|"
    r"accepted for exchange|principal amount reduced|"
    r"second[- ]lien notes|PIK notes|"
    r"springing maturity|equity conversion|"
    r"asset sales sufficient to (repay|redeem)|"
    r"binding agreements for asset sales|"
    r"maturity extension|debt repurchase|"
    r"lenders agreed|notes (will be|are being) (cancelled|repurchased)|"
    r"supporting holders|minimum participation condition)\b",
    re.I,
)
# Debt amount extraction: multiple word-orders. The principal can come
# before or after the action verb, and SEC filings use "principal amount
# of $X.X million was exchanged" / "exchanged $X.X million of notes" /
# "$X.X million of senior secured notes were repurchased" / etc.
DEBT_REDUCTION_AMOUNT = re.compile(
    r"(?:"
    # Forward: "$X million ... of notes ... exchanged/reduced/repurchased"
    r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)[^.\n]{0,120}?"
    r"(?:notes?|debt|principal)[^.\n]{0,80}?"
    r"(?:exchanged|repurchased|reduced|redeemed|cancelled|retired|tendered)"
    r"|"
    # Reverse: "exchanged/repurchased/etc $X million of notes"
    r"(?:exchanged|repurchased|reduced|redeemed|cancelled|retired|tendered|"
    r"purchased outstanding)[^.\n]{0,80}?"
    r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)"
    r"[^.\n]{0,80}?(?:notes?|debt|principal)?"
    r"|"
    # Standalone: "principal amount reduced by $X million"
    r"principal amount[^.\n]{0,40}?reduced[^.\n]{0,40}?\$\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)"
    r")",
    re.I,
)
PARTICIPATION_PCT = re.compile(
    r"(?:"
    # Forward: "99.5% of notes tendered"
    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%\s*(?:of (?:the )?(?:second[- ]lien |"
    r"first[- ]lien |outstanding |total |aggregate |senior secured )?"
    r"(?:notes|holders|noteholders|principal amount|aggregate principal)"
    r"\s*(?:were\s+|was\s+|have been\s+)?"
    r"(?:tendered|consented|accepted|supported|participated|exchanged))"
    r"|"
    # Reverse: "tendered/exchanged X% of notes"
    r"(?:tendered|consented|accepted|exchanged|received tenders for)"
    r"[^.\n]{0,50}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%"
    r"|"
    # "supporting holders representing X%"
    r"(?:supporting holders|consenting holders)[^.\n]{0,40}?"
    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%"
    r")",
    re.I,
)
GOING_CONCERN = re.compile(
    r"\b(going concern|substantial doubt about (the company.s )?ability to "
    r"continue|may not be able to continue as a going concern)\b",
    re.I,
)
CREDITOR_BOARD = re.compile(
    r"\b(board (designat(ed|ee)|appointed|seats?) by (the )?(noteholders?|"
    r"lenders?|creditors?)|noteholder[- ]designated director|"
    r"creditor[- ]appointed)\b",
    re.I,
)


# B. Spin-off / separation (Greenblatt) -------------------------------------
SPINOFF_EVENT = re.compile(
    r"\b(spin[- ]off|spinoff|spin[- ]out|"
    r"separation (agreement|transaction|of)|"
    r"distribution of (the )?shares of (common stock of )?(SpinCo|"
    r"the (Company|Subsidiary))|"
    r"Form 10(-12B)?|stand[- ]alone (public )?company|"
    r"separate (publicly[- ]traded )?company|tax[- ]free distribution|"
    r"reverse Morris Trust|Reverse Morris Trust)\b",
    re.I,
)
RIGHTS_OFFERING = re.compile(
    r"\b(rights offering|subscription rights|oversubscription privilege|"
    r"backstop(?:ped)? (rights|recapitalization))\b",
    re.I,
)


# C. Cash shell / net-net activist kicker -----------------------------------
NET_CASH_LANG = re.compile(
    r"\b(cash exceeds (the )?market cap|trading (at|below) (net )?cash|"
    r"net cash position|cash (and|&) (cash )?equivalents (greater|exceed))\b",
    re.I,
)


# D. Controller take-private / bump trades ----------------------------------
GO_PRIVATE = re.compile(
    r"\b(go[- ]private (transaction|proposal|offer)|"
    r"going[- ]private|"
    r"Schedule\s*13E-3|SC 13E-3|"
    r"controlling stockholder (proposal|offer)|"
    r"unsolicited (take[- ]private|controller) (proposal|bid))\b",
    re.I,
)


# E. Asset conversion / hidden assets ---------------------------------------
HIDDEN_ASSETS = re.compile(
    r"\b(NOLs?|net operating loss(es)?|"
    r"FCC license|spectrum (assets|holdings|auction)|"
    r"sale[- ]leaseback|tax assets?|"
    r"section 382|tax asset protection plan|"
    r"deferred tax asset|monetiz(e|ation) (of )?(real estate|land|spectrum))\b",
    re.I,
)


# F. Governance reset -------------------------------------------------------
GOVERNANCE_RESET = re.compile(
    r"\b(cooperation agreement|board refresh(ment)?|"
    r"chair (resign|stepping down|departure)|"
    r"value enhancement committee|finance and strategy committee|"
    r"strategic review committee)\b",
    re.I,
)


# Compound-screen helpers ---------------------------------------------------
INSIDER_BUYING = re.compile(
    r"\b(insiders? (purchas(ed|ing)|bought)|directors? and officers? "
    r"acquired|open[- ]market purchases? by (insiders?|directors?|"
    r"officers?)|recent Form 4 (purchases?|buys?))\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_musd(value: float, unit: str) -> float:
    u = unit.lower().strip()
    return value * 1000.0 if u in ("billion", "bn", "b") else value


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

@dataclass
class SpecialFeatures:
    ticker: str

    # A. Distressed stub
    has_debt_event: bool = False
    debt_event_phrases: list[str] = field(default_factory=list)
    debt_reduced_musd: float | None = None
    participation_pct: float | None = None
    going_concern: bool = False
    creditor_board_control: bool = False

    # B. Spin-off
    has_spinoff: bool = False
    has_rights_offering: bool = False

    # C. Cash shell
    cash_shell_language: bool = False

    # D. Take-private
    go_private_language: bool = False

    # E. Hidden assets
    hidden_assets: bool = False

    # F. Governance reset
    governance_reset: bool = False

    # Compound
    insider_buying_language: bool = False


def extract_special_features(ticker: str, text: str) -> SpecialFeatures:
    f = SpecialFeatures(ticker=ticker)

    # A.
    f.debt_event_phrases = sorted({
        m.group(0).lower() for m in DEBT_EVENT.finditer(text)
    })
    f.has_debt_event = bool(f.debt_event_phrases)
    drs = []
    for m in DEBT_REDUCTION_AMOUNT.finditer(text):
        # Three alternative groups; pick whichever matched.
        for amt_g, unit_g in ((1, 2), (3, 4), (5, 6)):
            amt = m.group(amt_g)
            unit = m.group(unit_g)
            if amt and unit:
                try:
                    drs.append(_to_musd(float(amt), unit))
                except ValueError:
                    pass
                break
    if drs:
        f.debt_reduced_musd = max(drs)
    pps = []
    for m in PARTICIPATION_PCT.finditer(text):
        for g in (1, 2, 3):
            v = m.group(g)
            if v is None:
                continue
            try:
                vv = float(v)
                if 50.0 <= vv <= 100.0:
                    pps.append(vv)
            except ValueError:
                pass
            break
    if pps:
        f.participation_pct = max(pps)
    f.going_concern = bool(GOING_CONCERN.search(text))
    f.creditor_board_control = bool(CREDITOR_BOARD.search(text))

    # B.
    f.has_spinoff = bool(SPINOFF_EVENT.search(text))
    f.has_rights_offering = bool(RIGHTS_OFFERING.search(text))

    # C.
    f.cash_shell_language = bool(NET_CASH_LANG.search(text))

    # D.
    f.go_private_language = bool(GO_PRIVATE.search(text))

    # E.
    f.hidden_assets = bool(HIDDEN_ASSETS.search(text))

    # F.
    f.governance_reset = bool(GOVERNANCE_RESET.search(text))

    # Compound
    f.insider_buying_language = bool(INSIDER_BUYING.search(text))

    return f


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class SpecialScore:
    catalyst_hardness: float           # 0-100
    balance_sheet_convexity: float     # 0-100
    common_preservation: float         # 0-100 (heuristic)
    distressed_stub: float             # 0-100 composite
    spinoff: float                     # 0-100
    cash_shell: float                  # 0-100
    take_private: float                # 0-100
    governance_reset: float            # 0-100
    special_situations_score: float    # 0-100 master
    taxonomy: str                      # A/B/C/D/E/F or none
    flags: list[str]


def score_specials(
    f: SpecialFeatures,
    market_cap_usd: float | None = None,
) -> SpecialScore:
    flags: list[str] = []

    # ---- Catalyst hardness (0-5 scale * 20) -------------------------------
    hardness = 0.0
    if f.has_debt_event:
        hardness = 60.0  # filed exchange/RSA = 3/5
    if f.participation_pct and f.participation_pct >= 75:
        hardness = 90.0  # near-closed = 4-5/5
        flags.append(f"Creditor participation {f.participation_pct:.1f}%")
    if f.creditor_board_control:
        hardness = max(hardness, 80.0)
        flags.append("Creditor-controlled board seats")
    if f.go_private_language:
        hardness = max(hardness, 70.0)
        flags.append("Take-private / 13E-3 language")
    if f.has_spinoff:
        hardness = max(hardness, 50.0)

    # ---- Balance-sheet convexity (debt reduced / market cap) -------------
    convex = 0.0
    if f.debt_reduced_musd and market_cap_usd and market_cap_usd > 0:
        ratio = (f.debt_reduced_musd * 1e6) / market_cap_usd
        flags.append(
            f"Debt reduced ${f.debt_reduced_musd:.0f}M = {ratio:.2f}x market cap"
        )
        # 1x mcap -> 50; 2x -> 80; 4x+ -> 100.
        convex = min(100.0, ratio * 25.0 + 30.0) if ratio > 0 else 0.0

    # ---- Common-equity preservation heuristic ----------------------------
    preserved = 50.0
    if f.has_debt_event and not f.creditor_board_control:
        preserved = 70.0
    if f.creditor_board_control:
        preserved = 30.0  # potential 95% conversion threat
        flags.append("Creditor board control => dilution risk to common")
    if f.going_concern:
        preserved = max(20.0, preserved - 20.0)
        flags.append("Going-concern language")

    # ---- Distressed-stub composite ---------------------------------------
    distress = 0.0
    if f.has_debt_event:
        distress = (
            0.40 * hardness
            + 0.35 * convex
            + 0.25 * preserved
        )

    # ---- Spin-off score --------------------------------------------------
    spin = 0.0
    if f.has_spinoff:
        spin = 60.0
        if f.has_rights_offering:
            spin += 20.0
            flags.append("Rights offering / oversubscription mechanic")
        if f.insider_buying_language:
            spin += 10.0
            flags.append("Insider buying language alongside spin-off")
        spin = min(100.0, spin)

    # ---- Cash shell ------------------------------------------------------
    shell = 0.0
    if f.cash_shell_language:
        shell = 50.0
    # Compound activist + cash shell would lift this further; left to the
    # cross-form merge step in the pipeline.

    # ---- Take-private ----------------------------------------------------
    tp = 0.0
    if f.go_private_language:
        tp = 70.0
        if f.cash_shell_language:
            tp += 10.0

    # ---- Governance reset ------------------------------------------------
    gov = 50.0 if f.governance_reset else 0.0

    # ---- Master special-situations score ---------------------------------
    # Weighted by which archetype fired hardest.
    raw = max(distress, spin, shell, tp, gov)
    if f.has_debt_event and f.has_spinoff:
        # Rare overlap; weight both
        raw = 0.6 * distress + 0.4 * spin

    # Penalise going-concern when the catalyst is weak.
    if f.going_concern and hardness < 60:
        raw *= 0.8

    # Taxonomy classification (single best fit).
    taxonomy = "none"
    if f.has_debt_event and (f.participation_pct or f.creditor_board_control):
        taxonomy = "A. Distressed equity stub"
    elif f.has_debt_event:
        taxonomy = "A. Debt event (early)"
    elif f.has_spinoff:
        taxonomy = "B. Spin-off"
    elif f.go_private_language:
        taxonomy = "D. Controller take-private"
    elif f.cash_shell_language:
        taxonomy = "C. Cash shell / net-net"
    elif f.governance_reset:
        taxonomy = "F. Governance reset"
    elif f.hidden_assets:
        taxonomy = "E. Asset conversion"

    return SpecialScore(
        catalyst_hardness=round(hardness, 1),
        balance_sheet_convexity=round(convex, 1),
        common_preservation=round(preserved, 1),
        distressed_stub=round(distress, 1),
        spinoff=round(spin, 1),
        cash_shell=round(shell, 1),
        take_private=round(tp, 1),
        governance_reset=round(gov, 1),
        special_situations_score=round(raw, 1),
        taxonomy=taxonomy,
        flags=flags,
    )
