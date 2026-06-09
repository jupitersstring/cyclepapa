"""Forensic asymmetry analyzer v2 -- methodical, multi-section.

v1 was too strict: it isolated only the first PSU anchor and missed
the CD&A 'Performance Highlights' / 'Annual Incentive Plan' sections
that contain the real dollar metric targets. v2 fixes:

  1. MULTI-ANCHOR SECTION. Locate every occurrence of any of:
     PSU/PRSU/"Performance Share"/"performance-based"/"Compensation
     Discussion and Analysis"/"Performance Highlights"/"Annual
     Incentive Plan"/"Long-Term Incentive"/"Performance Goals". Take
     the union of windows around them.
  2. BROADER VESTING-INTENT ANCHORS. A "vesting verb" now includes
     "for purposes of the [LIP/AIP/LTIP/incentive plan]", "achievement
     of", "performance goal", "earned ... under", "payable upon", etc.
  3. ATTRIBUTED EXTRACTION. Each hit records its sub-section header
     (when locatable) so the analyst can audit which part of the
     filing it came from.
  4. PSU ARCHETYPE LABEL. Each filing is bucketed into:
       A) Per-share-return-heavy (ROIC/ROIIC/EPS/FCF/share dominant)
       B) Multi-tranche stock-price ladder (>=3 distinct $ hurdles)
       C) Relative TSR (peer-group or index)
       D) Dollar metric target (named EBITDA/Revenue/FCF $)
       E) Event-triggered (M&A close / spin / regulatory milestone)
     A ticker can have multiple archetypes.
  5. HURDLE LADDER TABLE. Threshold/target/maximum tuples extracted
     from the PSU section with the metric attribution attempted.
  6. ROLE-WEIGHTED INSIDER + CLUSTER DETECTION as in v1.

Output: forensic_asymmetry.{json,csv}, ASYMMETRIC_FORENSIC_REPORT.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CACHE = Path("/home/user/cyclepapa/.cache/docs")
ROOT = Path("/home/user/cyclepapa")


# ---------------------------------------------------------------------------
# Multi-anchor section windowing
# ---------------------------------------------------------------------------

ANCHORS = [
    re.compile(r"performance[- ]?share\s+units?", re.I),
    re.compile(r"performance[- ]?stock\s+units?", re.I),
    re.compile(r"\bPRSUs?\b"),
    re.compile(r"\bPSUs?\b"),
    re.compile(r"compensation\s+discussion\s+and\s+analysis", re.I),
    re.compile(r"performance[- ]?based\s+(?:restricted\s+)?(?:stock|share)\s+units?", re.I),
    re.compile(r"performance\s+highlights", re.I),
    re.compile(r"annual\s+incentive\s+plan", re.I),
    re.compile(r"long[- ]term\s+incentive\s+plan", re.I),
    re.compile(r"performance\s+(?:goals?|objectives?|metrics?|criteria)", re.I),
    re.compile(r"executive\s+compensation\s+program", re.I),
]


def relevant_section(text: str, half_window: int = 6000) -> tuple[str, list[tuple[int, int]]]:
    """Return concatenated relevant sections + list of (start, end) spans."""
    if not text:
        return "", []
    spans: list[list[int]] = []
    for a in ANCHORS:
        for m in a.finditer(text):
            spans.append([max(0, m.start() - 800), min(len(text), m.start() + half_window)])
    if not spans:
        return "", []
    spans.sort()
    # Merge overlapping
    merged = [spans[0]]
    for s in spans[1:]:
        if s[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], s[1])
        else:
            merged.append(s)
    # Cap total length to avoid full-doc scanning
    out_chunks = []
    out_spans = []
    total = 0
    for s in merged:
        chunk = text[s[0]:s[1]]
        if total + len(chunk) > 80_000:
            chunk = chunk[: 80_000 - total]
        out_chunks.append(chunk)
        out_spans.append((s[0], s[0] + len(chunk)))
        total += len(chunk)
        if total >= 80_000:
            break
    return "\n||SECT_BREAK||\n".join(out_chunks), out_spans


def find_subsection_header(section: str, idx: int) -> str:
    """Climb backwards from `idx` to find the nearest plausible
    subsection header (short uppercase or title-case heading)."""
    window = section[max(0, idx - 600): idx]
    # Look for short heading-like phrases (Title Case ending without period)
    cand = re.findall(r"(?:^|\.\s+|\n)([A-Z][A-Za-z][^.\n]{2,80}?[A-Za-z])(?=\s*[\n:]|\s+[A-Z])",
                      window)
    if cand:
        h = cand[-1].strip()
        if 5 <= len(h) <= 80:
            return h
    return ""


# ---------------------------------------------------------------------------
# Conditionality patterns -- broader vesting-intent anchors
# ---------------------------------------------------------------------------

# What constitutes "this is tied to incentive compensation":
INCENTIVE_ANCHOR = (
    r"(?:vest(?:s|ed|ing)?|earn(?:s|ed|ing)?|payable|payout|"
    r"subject\s+to|conditioned\s+(?:on|upon)|contingent\s+(?:on|upon)|"
    r"trigger(?:s|ed)?|become[ds]?\s+(?:eligible|exercisable)|"
    r"for\s+purposes\s+of|achievement\s+of|"
    r"performance\s+(?:goal|target|objective)|"
    r"target\s+performance|under\s+the\s+(?:LIP|AIP|LTIP|incentive\s+plan|"
    r"\w+\s+plan)|incentive\s+plan|weighted\s+factor)"
)


def build_proxy_pattern(trigger: str, max_dist: int = 220) -> re.Pattern:
    """Compile a bidirectional proximity regex."""
    return re.compile(
        rf"({INCENTIVE_ANCHOR}[^.\n]{{0,{max_dist}}}?{trigger}"
        rf"|{trigger}[^.\n]{{0,{max_dist}}}?{INCENTIVE_ANCHOR})",
        re.I,
    )


PATTERNS = {
    # spin_separation must reference unambiguous CORPORATE spin language:
    # Distribution Date, Spin-Off, Form 10, "Separation and Distribution
    # Agreement", "newly independent company", "RemainCo / SpinCo". Plain
    # "separation" alone matches too much employment-termination boilerplate.
    "spin_separation": build_proxy_pattern(
        r"(?:Spin[- ]?Off|Distribution\s+Date|"
        r"Separation\s+and\s+Distribution\s+Agreement|"
        r"newly[- ]?independent\s+(?:company|public\s+company)|"
        r"RemainCo|SpinCo|Form\s+10[- ]?12B|"
        r"distribution\s+(?:of|to)\s+(?:shareholders|stockholders)\s+of)"
    ),
    "merger_acquisition_close": build_proxy_pattern(
        r"(?:closing|consummation|completion|Effective\s+Time)\s+of\s+the\s+"
        r"(?:Merger|Acquisition|Transaction|Business\s+Combination)"
    ),
    "fda_phase_milestone": build_proxy_pattern(
        r"(?:FDA\s+approval|PDUFA|Phase\s+(?:2b|3|III|IIb)|BLA\s+approval|"
        r"NDA\s+approval|EMA\s+approval|CE\s+mark|510\(k\)\s+clearance|"
        r"De\s+Novo\s+clearance|marketing\s+authorization)"
    ),
    "debt_leverage_target": build_proxy_pattern(
        r"(?:net\s+)?(?:debt|leverage)[^.\n]{0,40}?"
        r"(?:below|less\s+than|<=?|reduced\s+to|reach(?:ing|es)?)\s*"
        r"(?:\$[\d,.]+\s*(?:million|billion|B|M)|\d+(?:\.\d+)?\s*x)"
    ),
    "asset_sale_named": build_proxy_pattern(
        r"(?:sale|divestiture|disposition)\s+of\s+(?:the\s+)?"
        r"(?:[A-Z][a-zA-Z]+\s+(?:business|segment|division|operations|portfolio|subsidiary))"
    ),
    "ebitda_dollar_target": build_proxy_pattern(
        r"(?:Adjusted\s+)?EBITDA[^.\n]{0,30}?"
        r"(?:>=?|at\s+least|of|reach(?:ing|es)?|equal\s+to\s+or\s+greater\s+than)\s*"
        r"\$\s*[\d,]+(?:\.\d+)?\s*(?:million|billion|B|M)"
    ),
    "revenue_dollar_target": build_proxy_pattern(
        r"(?:Adjusted\s+)?(?:net\s+)?revenue[^.\n]{0,30}?"
        r"(?:>=?|at\s+least|of|reach(?:ing|es)?|equal\s+to\s+or\s+greater\s+than)\s*"
        r"\$\s*[\d,]+(?:\.\d+)?\s*(?:million|billion|B|M)"
    ),
    "fcf_dollar_target": build_proxy_pattern(
        r"(?:free\s+cash\s+flow|FCF)[^.\n]{0,30}?"
        r"(?:>=?|at\s+least|of|reach(?:ing|es)?|equal\s+to\s+or\s+greater\s+than)\s*"
        r"\$\s*[\d,]+(?:\.\d+)?\s*(?:million|billion|B|M)"
    ),
    "operating_margin_target": build_proxy_pattern(
        r"(?:gross|operating|EBITDA|EBIT)\s+margin[^.\n]{0,30}?"
        r"(?:>=?|at\s+least|of|reach(?:ing|es)?)\s*\d{1,3}(?:\.\d+)?\s*%"
    ),
    "share_count_reduction": build_proxy_pattern(
        r"(?:reduce|reduction\s+(?:in|of))\s+"
        r"(?:diluted\s+)?shares?\s+outstanding[^.\n]{0,40}?\d+(?:\.\d+)?\s*%"
    ),
    "subscriber_arr_target": build_proxy_pattern(
        r"(?:ARR|annual\s+recurring\s+revenue|subscribers?|MAU|DAU)[^.\n]{0,30}?"
        r"(?:>=?|at\s+least|reach(?:ing|es)?)\s*"
        r"(?:\$\s*)?[\d,]+(?:\.\d+)?\s*(?:million|billion|thousand|M|K|B)?"
    ),
    "backlog_target": build_proxy_pattern(
        r"(?:backlog|book[- ]to[- ]bill|order\s+book)[^.\n]{0,40}?"
        r"(?:\$[\d,]+(?:\.\d+)?\s*(?:million|billion)|[\d.]+\s*x)"
    ),
    "ipo_subsidiary": build_proxy_pattern(
        r"(?:initial\s+public\s+offering|IPO|listing)\s+of\s+"
        r"(?:a\s+|the\s+)?(?:subsidiary|affiliate)"
    ),
    "chapter11_emergence": build_proxy_pattern(
        r"(?:emergence\s+from\s+chapter\s+11|plan\s+of\s+reorganization|"
        r"removal\s+of\s+going\s+concern\s+qualification)"
    ),
    "stock_price_sustained": re.compile(
        r"((?:20|30|45|60|90|120|180)\s*(?:consecutive\s+)?trading\s+days?\s+"
        r"(?:closing|VWAP|price)[^.\n]{0,40}?"
        r"(?:at\s+or\s+above|exceeds?|equal\s+to\s+or\s+greater\s+than)\s*"
        r"\$\s*\d+(?:\.\d+)?)",
        re.I,
    ),
    "coc_price_threshold": build_proxy_pattern(
        r"Change\s+of\s+Control[^.\n]{0,180}?"
        r"(?:price\s+per\s+share|consideration|implied\s+value)[^.\n]{0,40}?"
        r"\$\s*\d+(?:\.\d+)?"
    ),
    "restructuring_milestone": build_proxy_pattern(
        r"(?:cost[- ]savings?\s+target|synergy\s+target|"
        r"restructuring\s+milestone|operational\s+turnaround)"
    ),
}


# Boilerplate to subtract (death/disability/retirement/employment RSU
# language). These are individual-employment terminations -- not the
# corporate separation/spin-off that we're trying to detect.
BOILERPLATE_FILTERS = [
    re.compile(r"separation\s+from\s+service", re.I),
    re.compile(r"in\s+the\s+event\s+of\s+death", re.I),
    re.compile(r"in\s+the\s+event\s+of\s+disability", re.I),
    re.compile(r"upon\s+retirement", re.I),
    re.compile(r"each\s+director(?:'s)?\s+annual\s+RSU\s+award", re.I),
    re.compile(r"general\s+release\s+of\s+claims", re.I),
    re.compile(r"non[- ]compete", re.I),
    re.compile(r"his\s+(?:annual\s+)?base\s+salary", re.I),
    re.compile(r"her\s+(?:annual\s+)?base\s+salary", re.I),
    re.compile(r"post[- ]employment", re.I),
    re.compile(r"after\s+(?:his|her|their)\s+separation", re.I),
    re.compile(r"forfeited\s+(?:bonus|equity)\s+upon\s+separation", re.I),
    # WRB-style insurance peer language that triggered FDA pattern
    re.compile(r"insurance\s+market", re.I),
    re.compile(r"insurance\s+peer", re.I),
    re.compile(r"insurance\s+industry", re.I),
    # Generic "calendar year" prorate language
    re.compile(r"calendar\s+year\s+following\s+the\s+year\s+the\s+award", re.I),
]


# Category-specific extra filters
EXTRA_FILTERS_BY_CATEGORY = {
    "fda_phase_milestone": [
        re.compile(r"insurance", re.I),
        re.compile(r"underwriting", re.I),
        re.compile(r"reinsurance", re.I),
    ],
    "spin_separation": [
        # Employment-context "Separation Date" not corporate spin
        re.compile(r"(his|her|their)\s+Separation\s+Date", re.I),
        re.compile(r"Mr\.|Ms\.|Mrs\.", re.I),  # Name-attributed = personnel
    ],
}


def is_boilerplate(snippet: str, category: str = "") -> bool:
    if any(p.search(snippet) for p in BOILERPLATE_FILTERS):
        return True
    extras = EXTRA_FILTERS_BY_CATEGORY.get(category, [])
    if extras and any(p.search(snippet) for p in extras):
        # Only treat as boilerplate if the snippet doesn't also reference
        # an actual corporate transaction
        if not re.search(r"(?:Distribution\s+Date|Spin[- ]?Off|"
                         r"Effective\s+Time\s+of\s+the\s+Separation|"
                         r"Separation\s+and\s+Distribution\s+Agreement|"
                         r"Form\s+10[- ]?12B)", snippet, re.I):
            return True
    return False


CATEGORY_WEIGHT = {
    "spin_separation":          18,
    "merger_acquisition_close": 18,
    "fda_phase_milestone":      20,
    "debt_leverage_target":     14,
    "asset_sale_named":         14,
    "ebitda_dollar_target":     12,
    "revenue_dollar_target":    10,
    "fcf_dollar_target":        14,
    "operating_margin_target":   8,
    "share_count_reduction":    10,
    "subscriber_arr_target":     8,
    "backlog_target":            6,
    "ipo_subsidiary":           14,
    "chapter11_emergence":      18,
    "stock_price_sustained":     8,
    "coc_price_threshold":       8,
    "restructuring_milestone":  10,
}


# Tokens that mark a passage as RETROSPECTIVE (we already achieved X,
# we paid out at Y%) rather than FORWARD (must achieve X to vest).
# Forward triggers are the genuine asymmetric signal; retrospective
# disclosures describe historic comp outcomes and don't tell you
# anything about future vesting structure.
RETROSPECTIVE_TOKENS = re.compile(
    r"\b(?:we\s+achieved|achieved\s+(?:adjusted\s+)?(?:EBITDA|revenue|FCF)|"
    r"actual\s+performance|resulted\s+in\s+a\s+payout|earned\s+at|"
    r"paid\s+out\s+at|payout\s+was|delivered\s+(?:adjusted\s+)?(?:EBITDA|revenue)|"
    r"performance\s+highlights|target\s+performance\.|"
    r"compensation\s+outcomes|recent\s+compensation\s+outcomes|"
    r"as\s+a\s+result\s+of\s+our\s+performance|exceeded\s+target|"
    r"in\s+\d{4}\s*,?\s+(?:we|the\s+Company)\s+(?:delivered|generated|achieved))",
    re.I,
)

# Forward / conditional language tokens. Strong forward signals.
FORWARD_TOKENS = re.compile(
    r"\b(?:must\s+(?:have\s+)?achieve|in\s+order\s+to\s+vest|"
    r"vesting\s+(?:is\s+)?subject\s+to|will\s+vest\s+(?:if|upon|when)|"
    r"vests\s+(?:if|upon|when)|earns?\s+(?:upon|if)|payable\s+if|"
    r"required\s+to\s+achieve|conditioned\s+(?:on|upon)\s+achievement)",
    re.I,
)


def classify_direction(context: str) -> str:
    """Return 'forward', 'retrospective', or 'ambiguous'."""
    has_fwd = bool(FORWARD_TOKENS.search(context))
    has_retro = bool(RETROSPECTIVE_TOKENS.search(context))
    if has_fwd and not has_retro:
        return "forward"
    if has_retro and not has_fwd:
        return "retrospective"
    if has_fwd and has_retro:
        return "ambiguous"  # mixed -- treat as half-credit
    return "ambiguous"


def extract_conditionalities(section: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for cat, pat in PATTERNS.items():
        hits = []
        for m in pat.finditer(section):
            snip = re.sub(r"\s+", " ", m.group(0)).strip()[:320]
            if is_boilerplate(snip, cat):
                continue
            ctx_start = max(0, m.start() - 250)
            ctx_end = min(len(section), m.end() + 150)
            full_ctx = re.sub(r"\s+", " ", section[ctx_start:ctx_end]).strip()
            ctx = re.sub(r"\s+", " ",
                         section[ctx_start:m.start()]).strip()[-180:]
            header = find_subsection_header(section, m.start())
            direction = classify_direction(full_ctx)
            entry = {
                "snippet": snip,
                "context_before": ctx[-120:],
                "subsection": header,
                "direction": direction,
            }
            # Dedupe by snippet
            if not any(h["snippet"] == snip for h in hits):
                hits.append(entry)
            if len(hits) >= 3:
                break
        if hits:
            out[cat] = hits
    return out


# ---------------------------------------------------------------------------
# Plan-evolution markers
# ---------------------------------------------------------------------------

PLAN_DELTA_PATTERNS = {
    "new_metric_added": re.compile(
        r"(?:beginning|effective|starting|for\s+(?:fiscal\s+)?\d{4})[^.\n]{0,80}?"
        r"(?:added|introduced|incorporated|will\s+(?:include|incorporate))\s+"
        r"(?:a\s+|the\s+)?(?:ROIC|ROIIC|TSR|EPS|FCF|free\s+cash\s+flow|"
        r"revenue|EBITDA|operating\s+margin)", re.I),
    "metric_eliminated": re.compile(
        r"(?:eliminated|removed|discontinued)\s+(?:the\s+)?"
        r"(?:ROIC|TSR|EPS|FCF|revenue|EBITDA)\s+(?:metric|component|measure)", re.I),
    "psu_weight_increased": re.compile(
        r"(?:increased|raised|expanded)\s+(?:the\s+)?(?:PSU|performance[- ]based|"
        r"performance[- ]share)\s+(?:weight(?:ing)?|allocation|portion|mix)", re.I),
    "performance_period_extended": re.compile(
        r"(?:extended|increased|lengthened)\s+(?:the\s+)?performance\s+period\s+"
        r"(?:from\s+)?\d+\s*(?:to|-)\s*\d+\s*(?:year|yr)", re.I),
    "ownership_requirement_added": re.compile(
        r"(?:new|enhanced|increased)\s+(?:stock\s+)?ownership\s+"
        r"(?:requirements?|guidelines?|multiple)", re.I),
    "responsive_to_shareholders": re.compile(
        r"in\s+response\s+to\s+(?:our\s+)?(?:shareholder|stockholder)\s+(?:feedback|engagement)", re.I),
    "front_load_grant": re.compile(
        r"(?:front[- ]?loaded|one[- ]?time\s+transformation|new[- ]?hire\s+inducement)", re.I),
    "clawback_strengthened": re.compile(
        r"(?:adopted|expanded|enhanced)[^.\n]{0,80}?clawback", re.I),
    "anti_hedge_pledge_added": re.compile(
        r"(?:adopted|prohibited)[^.\n]{0,40}?(?:hedging|pledging)", re.I),
}


def extract_plan_deltas(section: str) -> dict[str, str]:
    out = {}
    for k, pat in PLAN_DELTA_PATTERNS.items():
        m = pat.search(section)
        if m:
            out[k] = re.sub(r"\s+", " ", m.group(0)).strip()[:240]
    return out


# ---------------------------------------------------------------------------
# Hurdle ladder
# ---------------------------------------------------------------------------

THRESHOLD_LADDER = re.compile(
    r"(threshold|target|maximum|stretch|minimum)[^.\n]{0,40}?"
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|B|M)?",
    re.I,
)
PCT_LADDER = re.compile(
    r"(threshold|target|maximum|stretch|minimum)[^.\n]{0,40}?"
    r"(\d{1,3}(?:\.\d+)?)\s*%",
    re.I,
)
STOCK_PRICE_HURDLE = re.compile(
    r"(?:closing|VWAP|stock\s+price|share\s+price)[^.\n]{0,80}?"
    r"\$\s*(\d{1,4}(?:\.\d{1,2})?)",
    re.I,
)


def extract_ladder(section: str) -> dict:
    out: dict = {}
    tiers: dict[str, list[float]] = {}
    for m in THRESHOLD_LADDER.finditer(section):
        tier = m.group(1).lower()
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(3) or "").lower()
        if unit.startswith("b"):
            v *= 1000.0
        if 1 <= v <= 1_000_000:
            tiers.setdefault(tier, []).append(v)
    if tiers:
        out["dollar_ladder"] = {k: sorted(set(round(x, 1) for x in v)) for k, v in tiers.items()}

    pct_tiers: dict[str, list[float]] = {}
    for m in PCT_LADDER.finditer(section):
        tier = m.group(1).lower()
        try:
            v = float(m.group(2))
        except ValueError:
            continue
        if 0.5 <= v <= 200:
            pct_tiers.setdefault(tier, []).append(v)
    if pct_tiers:
        out["pct_ladder"] = {k: sorted(set(round(x, 2) for x in v)) for k, v in pct_tiers.items()}

    px_hurdles = sorted(set(
        float(m.group(1)) for m in STOCK_PRICE_HURDLE.finditer(section)
        if 0.5 <= float(m.group(1)) <= 2000
    ))
    if px_hurdles:
        out["stock_price_hurdles"] = px_hurdles[:30]
    return out


# ---------------------------------------------------------------------------
# Archetype labeling
# ---------------------------------------------------------------------------

def archetype_labels(detail: dict, ladder: dict) -> list[str]:
    labels = []
    metrics = set((detail.get("performance_metrics") or []))
    metrics_lower = {m.lower() for m in metrics}

    # A) Per-share return heavy
    per_share_count = sum(1 for m in metrics if m in ("TSR", "EPS", "ROIC", "FCF/share"))
    if per_share_count >= 3 or {"roic", "roiic", "fcf/share"} & metrics_lower:
        labels.append("A_per_share_return")

    # B) Multi-tranche price ladder
    px = ladder.get("stock_price_hurdles") or []
    if len(set(px)) >= 3:
        labels.append("B_price_ladder")

    # C) Relative TSR
    if "tsr" in metrics_lower:
        labels.append("C_relative_TSR")

    # D) Dollar metric target
    dl = ladder.get("dollar_ladder") or {}
    if any(dl.values()):
        labels.append("D_dollar_metric_target")

    return labels


# ---------------------------------------------------------------------------
# Insider buying (role-weighted, cluster-detected)
# ---------------------------------------------------------------------------

ROLE_WEIGHTS = {
    "ceo": 1.50, "chief executive officer": 1.50, "executive chairman": 1.40,
    "president and ceo": 1.50, "president & ceo": 1.50,
    "cfo": 1.20, "chief financial officer": 1.20,
    "coo": 1.15, "chief operating officer": 1.15, "president": 1.10,
    "chairman": 1.10, "chair": 1.05, "lead director": 1.00,
    "director": 0.85,
    "cto": 1.00, "chief technology officer": 1.00,
    "general counsel": 0.95, "cco": 0.90, "cao": 0.90,
    "10%": 1.05, "beneficial owner": 1.05,
}


def role_weight(title: str | None) -> float:
    if not title:
        return 0.80
    t = title.lower()
    for key, w in ROLE_WEIGHTS.items():
        if key in t:
            return w
    return 0.80


def assess_insider_buying(f4_rec: dict, mcap: float) -> dict:
    if not f4_rec:
        return {"score": 0.0, "reasons": [], "filings_enriched": []}
    filings = f4_rec.get("filings") or []
    if not filings:
        return {"score": 0.0, "reasons": [], "filings_enriched": []}

    now = datetime.now(timezone.utc)
    title_lookup = {}
    for b in f4_rec.get("buyer_set") or []:
        parts = b.split("|")
        if len(parts) >= 2:
            title_lookup[parts[0].strip()] = parts[1].strip()

    enriched = []
    for fl in filings:
        dt = None
        days = 9999
        try:
            dt = datetime.strptime((fl.get("date") or "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days = max(0, (now - dt).days)
        except Exception:
            pass
        title = fl.get("title") or title_lookup.get((fl.get("person") or "").strip())
        enriched.append({
            "date": fl.get("date"),
            "days_ago": days,
            "person": fl.get("person"),
            "title": title,
            "dollar": float(fl.get("dollar") or 0),
            "shares": float(fl.get("shares") or 0),
            "role_w": role_weight(title),
        })

    # Cluster: max distinct persons buying within any 14-day window
    es = sorted(enriched, key=lambda x: x.get("date") or "")
    best = 0
    best_window = None
    for i, fi in enumerate(es):
        if not fi.get("date"):
            continue
        try:
            di = datetime.strptime(fi["date"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        cluster = {fi["person"]}
        for fj in es[i + 1:]:
            try:
                dj = datetime.strptime((fj.get("date") or "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if (dj - di).days <= 14:
                cluster.add(fj["person"])
            else:
                break
        if len(cluster) > best:
            best = len(cluster)
            best_window = (fi["date"], sorted(cluster))

    total_raw = sum(fi["dollar"] for fi in enriched)
    total_w = sum(fi["dollar"] * fi["role_w"] for fi in enriched)
    n_30 = sum(1 for fi in enriched if fi["days_ago"] <= 30)
    n_90 = sum(1 for fi in enriched if fi["days_ago"] <= 90)
    n_180 = sum(1 for fi in enriched if fi["days_ago"] <= 180)

    titles_recent = {(fi["title"] or "").lower() for fi in enriched if fi["days_ago"] <= 180}
    has_ceo = any(("ceo" in t or "chief executive" in t) for t in titles_recent)
    has_cfo = any(("cfo" in t or "chief financial" in t) for t in titles_recent)
    has_chair = any(("chair" in t and "vice" not in t) for t in titles_recent)
    ceo_cfo = has_ceo and has_cfo

    score = 0.0
    reasons = []
    if best >= 4:
        score += 30; reasons.append(f"{best}-buyer cluster in 14d window")
    elif best >= 3:
        score += 22; reasons.append(f"{best}-buyer cluster in 14d window")
    elif best >= 2:
        score += 12; reasons.append(f"{best}-buyer cluster in 14d window")
    if ceo_cfo:
        score += 16; reasons.append("CEO + CFO both bought")
    elif has_ceo:
        score += 8; reasons.append("CEO bought")
    elif has_chair:
        score += 5; reasons.append("Chairman bought")
    if n_30 >= 3:
        score += 12; reasons.append(f"{n_30} P-buys in past 30d")
    elif n_30 >= 1:
        score += 5
    if mcap and mcap > 0:
        pct_mcap = total_raw / mcap * 100
        if pct_mcap >= 1.0:
            score += 22; reasons.append(f"buys = {pct_mcap:.2f}% of mcap")
        elif pct_mcap >= 0.3:
            score += 12; reasons.append(f"buys = {pct_mcap:.2f}% of mcap")
        elif pct_mcap >= 0.05:
            score += 5

    return {
        "score": min(85.0, score),
        "reasons": reasons,
        "filings_enriched": enriched,
        "cluster_size": best,
        "cluster_window": best_window,
        "total_raw_dollar": total_raw,
        "total_weighted_dollar": total_w,
        "ceo_and_cfo_bought": ceo_cfo,
        "has_ceo_buy": has_ceo,
        "has_chair_buy": has_chair,
        "n_buys_30d": n_30,
        "n_buys_90d": n_90,
        "n_buys_180d": n_180,
        "title_lookup": title_lookup,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def acc_from_url(url: str | None) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/(\d{18})/", url)
    if m:
        raw = m.group(1)
        return f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"
    m = re.search(r"(\d{10}-\d{2}-\d{6})", url)
    if m:
        return m.group(1)
    return None


def load_text(accession: str) -> str:
    p = CACHE / f"{accession}.html"
    if not p.exists():
        return ""
    try:
        raw = p.read_text(errors="ignore")
    except Exception:
        return ""
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain)
    return plain


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="psu_step_change.csv")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--csv", default="forensic_asymmetry.csv")
    ap.add_argument("--json", default="forensic_asymmetry.json")
    args = ap.parse_args()

    src = list(csv.DictReader(open(args.source)))[: args.top]
    print(f"Forensic analysis on {len(src)} candidates", flush=True)

    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    fz = json.loads((ROOT / "psu_forensics_v2.json").read_text())

    out_json: dict = {}
    rows = []

    for sr in src:
        tk = (sr.get("ticker") or "").upper()
        url = sr.get("filing_url")
        acc = acc_from_url(url)
        if not acc:
            continue
        text = load_text(acc)
        if not text:
            continue
        section, spans = relevant_section(text)
        if not section:
            continue

        cond = extract_conditionalities(section)
        deltas = extract_plan_deltas(section)
        ladder = extract_ladder(section)

        # Score with direction weighting: forward triggers full weight,
        # retrospective half-weight (they describe paid-out comp, not
        # vesting conditions), ambiguous gets 0.7x. The FACT that the
        # regex fired still tells you the company has dollar-named
        # metrics in its plan, so we keep some credit even for retro.
        DIRECTION_MULTIPLIER = {
            "forward": 1.0, "ambiguous": 0.7, "retrospective": 0.5,
        }
        cond_score = 0.0
        n_forward = 0
        n_retro = 0
        for cat, hits in cond.items():
            w = CATEGORY_WEIGHT.get(cat, 4)
            mult = 1.0 if len(hits) == 1 else (1.3 if len(hits) == 2 else 1.5)
            # Use the best (most-forward) direction among the hits for
            # this category -- one genuine forward trigger should beat
            # several retro references to the same metric.
            best_dir = "retrospective"
            for h in hits:
                d = h.get("direction", "ambiguous")
                if d == "forward":
                    best_dir = "forward"; break
                if d == "ambiguous" and best_dir == "retrospective":
                    best_dir = "ambiguous"
            dir_mult = DIRECTION_MULTIPLIER.get(best_dir, 0.7)
            if best_dir == "forward":
                n_forward += 1
            elif best_dir == "retrospective":
                n_retro += 1
            cond_score += w * mult * dir_mult
        cond_score = min(100.0, cond_score)

        delta_score = min(20.0, 4 * len(deltas))

        mcap = float(sr.get("market_cap_musd") or 0) * 1e6
        ins = assess_insider_buying(f4.get(tk) or {}, mcap)

        step_score = float(sr.get("step_score") or 0)
        pattern_match = float(sr.get("pattern_match") or 0)

        forensics = (fz.get(tk) or {}).get("forensics") or {}
        archetypes = archetype_labels(forensics, ladder)

        forensic_score = (
            0.32 * pattern_match +
            0.27 * cond_score +
            0.10 * delta_score +
            0.26 * ins["score"] +
            0.05 * step_score
        )

        out_json[tk] = {
            "ticker": tk,
            "company": sr.get("company"),
            "current_price": float(sr.get("current_price") or 0),
            "market_cap_musd": float(sr.get("market_cap_musd") or 0),
            "filing_date": sr.get("filing_date"),
            "filing_url": url,
            "accession": acc,
            "section_spans": spans,
            "archetypes": archetypes,
            "pattern_match": pattern_match,
            "step_score": step_score,
            "conditionality_score": cond_score,
            "delta_score": delta_score,
            "insider_score": ins["score"],
            "forensic_score": forensic_score,
            "conditionalities": cond,
            "plan_deltas": deltas,
            "hurdle_ladder": ladder,
            "insider_detail": ins,
            "psu_pct_of_lti": (forensics.get("lti_mix") or {}).get("psu_pct"),
            "performance_metrics": forensics.get("performance_metrics"),
            "say_on_pay_pct": forensics.get("say_on_pay_pct"),
            "_run_at": datetime.now(timezone.utc).isoformat(),
        }

        rows.append({
            "ticker": tk,
            "company": (sr.get("company") or "")[:48],
            "current_price": float(sr.get("current_price") or 0),
            "market_cap_musd": round(mcap / 1e6, 1),
            "filing_date": sr.get("filing_date"),
            "pattern_match": round(pattern_match, 1),
            "conditionality": round(cond_score, 1),
            "delta": round(delta_score, 1),
            "insider": round(ins["score"], 1),
            "forensic_score": round(forensic_score, 1),
            "psu_pct_lti": (forensics.get("lti_mix") or {}).get("psu_pct"),
            "metrics": ",".join(forensics.get("performance_metrics") or []),
            "archetypes": ",".join(archetypes),
            "n_cond": len(cond),
            "n_cond_forward": n_forward,
            "n_cond_retro": n_retro,
            "cond_cats": ";".join(cond.keys()),
            "n_deltas": len(deltas),
            "delta_keys": ";".join(deltas.keys()),
            "cluster_size": ins.get("cluster_size", 0),
            "ceo_cfo": ins.get("ceo_and_cfo_bought", False),
            "n_buys_30d": ins.get("n_buys_30d", 0),
            "total_insider_kusd": round((ins.get("total_raw_dollar") or 0) / 1e3, 1),
            "ins_reasons": " | ".join(ins["reasons"]),
            "filing_url": url,
        })

        Path(args.json).write_text(json.dumps(out_json, indent=2, default=str))

    rows.sort(key=lambda r: r["forensic_score"], reverse=True)

    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "filing_date", "archetypes",
              "pattern_match", "conditionality", "delta", "insider", "forensic_score",
              "psu_pct_lti", "metrics",
              "n_cond", "n_cond_forward", "n_cond_retro",
              "cond_cats", "n_deltas", "delta_keys",
              "cluster_size", "ceo_cfo", "n_buys_30d", "total_insider_kusd",
              "ins_reasons", "filing_url"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nWrote {args.csv} + {args.json}\n")
    print(f"{'#':<3}{'TKR':<7}{'MCAP':>9}{'PX':>8}"
          f"{'PTM':>4}{'CND':>4}{'DLT':>4}{'INS':>4}{'FRS':>5}"
          f"{'CLU':>4}{'CC':>3}{'PSU%':>5}  ARCHETYPES  CATEGORIES / DELTAS")
    print("-" * 200)
    for i, r in enumerate(rows[:40], 1):
        cc = "Y" if r.get("ceo_cfo") else " "
        psu = r.get("psu_pct_lti") or "-"
        cats = (r["cond_cats"] or "-")[:50]
        deltas = (r["delta_keys"] or "")[:35]
        arch = (r["archetypes"] or "-")[:30]
        print(f"{i:<3}{r['ticker']:<7}{r['market_cap_musd']:>8.0f}M"
              f"{r['current_price']:>8.2f}{r['pattern_match']:>4.0f}"
              f"{r['conditionality']:>4.0f}{r['delta']:>4.0f}"
              f"{r['insider']:>4.0f}{r['forensic_score']:>5.0f}"
              f"{r['cluster_size']:>4}{cc:>3}{str(psu):>5}  "
              f"{arch:<30}  {cats} | {deltas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
