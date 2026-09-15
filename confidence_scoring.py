"""Confidence scoring + adviser tier + hurdle plausibility.

Adds a NUANCE layer on top of the binary detectors -- the screen
remains as inclusive as before, but each row now carries:

  - adviser_tier    BB (bulge bracket: GS/MS/JPM/Citi/BofA)
                    EB (elite boutique: Centerview/Lazard/Evercore/PJT)
                    BR (boutique restructuring: Houlihan/PJT/Moelis)
                    OT (other)
  - hurdle_quality  CLEAN_LADDER (3+ plausible tranches)
                    CLEAN_MULTI  (2 plausible)
                    SINGLE_POINT (one plausible, no noise)
                    MIXED        (some plausible, some borderline)
                    SUSPECT      (mostly fee-table-style outliers)
  - filing_recency  DAYS_AGO from the most recent contributing filing
  - confidence      0-100 composite of all the above

Activist credibility intentionally NOT tiered -- presence alone is
the signal; ranking activists by name introduces survivorship bias.
"""

from __future__ import annotations

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Tier rosters
# ---------------------------------------------------------------------------

BULGE_BRACKET = {
    "goldman sachs", "morgan stanley", "jpmorgan", "j.p. morgan",
    "j. p. morgan", "bank of america", "bofa securities",
    "citi", "citigroup", "barclays",
}
ELITE_BOUTIQUES = {
    "lazard", "centerview", "evercore", "pjt partners", "perella weinberg",
    "guggenheim", "qatalyst partners", "moelis",
}
BOUTIQUE_RESTRUCTURING = {
    "houlihan lokey", "pjt partners", "moelis", "ducera partners",
    "rothschild", "lincoln international", "solomon partners",
}


def adviser_tier(advisers_named: list[str] | None) -> str:
    if not advisers_named:
        return ""
    lowered = {a.lower().strip() for a in advisers_named}
    has_bb = any(t in n for n in lowered for t in BULGE_BRACKET)
    has_eb = any(t in n for n in lowered for t in ELITE_BOUTIQUES)
    has_br = any(t in n for n in lowered for t in BOUTIQUE_RESTRUCTURING)
    if has_bb and (has_eb or has_br):
        return "BB+EB"
    if has_bb:
        return "BB"
    if has_eb:
        return "EB"
    if has_br:
        return "BR"
    return "OT"


def hurdle_quality(hurdles: list[float] | None, current_price: float | None) -> str:
    if not hurdles or not current_price or current_price <= 0:
        return ""
    plausible = [h for h in hurdles if 1.0 < h / current_price <= 30.0]
    suspect = [h for h in hurdles if h / current_price > 30.0]
    if len(suspect) > 0 and len(plausible) <= 1:
        return "SUSPECT"
    if len(plausible) >= 3:
        return "CLEAN_LADDER"
    if len(plausible) >= 2:
        return "CLEAN_MULTI"
    if len(plausible) == 1 and not suspect:
        return "SINGLE_POINT"
    return "MIXED"


def filing_recency_days(filing_date: str | None) -> int | None:
    if not filing_date:
        return None
    try:
        # filing_date is "YYYY-MM-DD"
        d = datetime.strptime(filing_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - d).days
        return max(0, delta)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Composite confidence
# ---------------------------------------------------------------------------

def confidence_score(r: dict) -> tuple[int, list[str]]:
    """Return (0-100 confidence, reasons list)."""
    reasons: list[str] = []
    score = 50.0  # neutral start

    # Activist presence (no credibility tier -- presence alone is the signal)
    activists = r.get("activists_named") or []
    if activists:
        score += 14
        reasons.append(f"Activist named: {', '.join(activists[:3])}")
    if (r.get("sc13d_filings_1y") or 0) > 0:
        score += 8
        reasons.append(f"SC 13D primary-source ({r['sc13d_filings_1y']})")

    # Adviser tier
    av = adviser_tier(r.get("advisers_named"))
    if "BB" in av and ("BR" in av or "EB" in av):
        score += 12; reasons.append(f"BB+boutique advisers")
    elif av == "BB":
        score += 8; reasons.append("BB adviser")
    elif av in ("EB", "BR"):
        score += 6; reasons.append(f"{av} adviser")
    elif av == "OT":
        score += 2

    # Hurdle quality
    hq = hurdle_quality(r.get("stock_price_hurdles"), r.get("current_price"))
    if hq == "CLEAN_LADDER":
        score += 12; reasons.append("Clean PSU ladder (3+ tranches plausible)")
    elif hq == "CLEAN_MULTI":
        score += 8; reasons.append("PSU ladder (2 plausible)")
    elif hq == "SINGLE_POINT":
        score += 3; reasons.append("Single hurdle point (verify)")
    elif hq == "SUSPECT":
        score -= 10; reasons.append("Hurdle range looks fee-table noisy")

    # Insider tape
    ic = r.get("insider_form4_count_90d") or 0
    if ic >= 10:
        score += 10; reasons.append(f"Heavy insider tape ({ic} Form 4 in 90d)")
    elif ic >= 5:
        score += 5; reasons.append(f"Moderate insider tape ({ic})")

    # Catalyst hardness
    if r.get("active_bid"):
        score += 5; reasons.append("Active-bid language")
    if r.get("has_special_committee"):
        score += 5; reasons.append("Special committee disclosed")
    if r.get("majority_of_minority"):
        score += 6; reasons.append("MoM protection")
    if r.get("has_debt_event"):
        if (r.get("participation_pct") or 0) >= 75:
            score += 8; reasons.append(f"Debt event {r.get('participation_pct'):.0f}% participated")
        else:
            score += 3
    if r.get("creditor_board_control"):
        score += 8; reasons.append("Creditor-controlled board")
    if r.get("transformation_signal"):
        score += 5; reasons.append("PSU TRANSFORM flag")

    # Filing recency
    days = filing_recency_days(r.get("filing_date"))
    if days is not None:
        if days <= 30:
            score += 8; reasons.append(f"Recent filing ({days}d ago)")
        elif days <= 90:
            score += 4
        elif days >= 365:
            score -= 5; reasons.append(f"Stale filing ({days}d ago)")

    # Cross-validation: row appears in multiple source files
    sources = r.get("_sources") or []
    if isinstance(sources, list) and len(sources) >= 3:
        score += 6; reasons.append(f"Cross-source ({len(sources)} sweeps)")
    elif isinstance(sources, list) and len(sources) == 2:
        score += 3

    score = max(0.0, min(100.0, score))
    return int(round(score)), reasons


def catalyst_hardness(r: dict) -> int:
    """0-5 scale per Bastian rubric.
       0 vague language
       1 management says exploring
       2 board committee / advisers hired
       3 signed LOI / RSA / TSA
       4 filed exchange / tender / merger agreement
       5 closed or near-closed (>75% participation / bid agreed)
    """
    if r.get("active_bid") and (
        (r.get("participation_pct") or 0) >= 75
        or r.get("majority_of_minority")
    ):
        return 5
    if r.get("active_bid") and r.get("offer_price"):
        return 4
    if r.get("has_debt_event") and (r.get("participation_pct") or 0) >= 50:
        return 4
    if r.get("has_special_committee") and (r.get("advisers_named") or []):
        return 3
    if r.get("has_special_committee") or r.get("engaged_adviser"):
        return 2
    if r.get("strategic_alts_language") or r.get("has_spinoff"):
        return 1
    return 0
