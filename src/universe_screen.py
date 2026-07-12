#!/usr/bin/env python3
"""
universe_screen.py — apply the framework to the entire universe.md.

v2 improvements (June 2026):
- Massively expanded keyword sets covering Korea/Japan/Asia/EM-specific
  archetypes plus EU regulators (BPI, EIB, KfW, BNDES, JIC, CDP, GIC, etc).
- Vintage extraction: pulls year mentions from notes and section text;
  applies a 'completed-arc' decay for pre-2022 deals without 'ongoing'
  markers.
- Status detection extended: 'completed arc' (re-rated, multibagger,
  recovered, dividends resumed), 'court reversal', 'taken private',
  'refiled within 12m', 'equity wiped'.
- Multi-archetype tagging: names can match multiple codes (A1+G, F+A).
- Size-class multiplier: detects $/€/£/SEK/etc. amounts in notes and
  weights by deal size.
- Per-region tier discipline: top N per region surfaced explicitly
  so under-represented regions (Africa, LatAm, MEA) aren't drowned
  out by the dense US/UK clusters.
- 4 confidence-weighted scoring bands: T0 (>=0.80), T1 (0.55-0.80),
  T2 (0.35-0.55), T3 (0.20-0.35), pass (<0.20).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Support both `python3 src/universe_screen.py` and `python3 -m
# src.universe_screen` invocations.
try:
    from src.edgar_util import resolve_cik_to_ticker
except ModuleNotFoundError:  # invoked as a bare script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.edgar_util import resolve_cik_to_ticker

REPO = Path(__file__).resolve().parent.parent
UNIVERSE_MD = REPO / "universe.md"
OUT = REPO / "output" / "universe_screened.md"

# Archetype keyword classification — heavily expanded vs v1.
# Order matters; first match wins for the primary code, but secondary
# matches are recorded as multi-archetype tags.
ARCHETYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("A2", [
        # US sovereign industrial policy
        # NB: use UPPER-case agency acronyms only, matched via a
        # case-sensitive check below — 'doc'/'doe'/'saf' as lowercase
        # common words (e.g. "primary doc") must NOT match. These are
        # kept lowercase here but the note text is boilerplate-stripped
        # and event-mapped first, so agency matches only fire on genuine
        # agency mentions in descriptive rows.
        r"\bdod\b", r"\bdepartment of energy\b", r"\bdepartment of commerce\b",
        r"\bchips? act\b", r"\bpentagon\b",
        r"\batvm\b", r"\bceefc\b", r"\bdepartment of (defen[cs]e|energy|commerce)\b",
        r"\bcritical[ -]?mineral",
        r"\bsovereign.*?(anchor|stake|equity|floor|offtake)",
        r"\bgovernment\b.*?\b(stake|equity|loan|floor|offtake)\b",
        # European sovereign industrial policy
        r"\beib\b", r"\bbpifrance\b", r"\bkfw\b",
        r"\beuropean investment bank\b",
        r"\bindustrial accelerator act\b", r"\bcrma\b",
        # Other-jurisdiction sovereign anchors
        r"\bbndes\b", r"\bjic\b", r"\bjip\b", r"\bcdp\b",
        r"\bdanantara\b", r"\bjip\b", r"\bkhazanah\b", r"\bmubadala\b",
        r"\bgic\b", r"\btemasek\b", r"\badia\b", r"\bpif\b",
        r"\bnbim\b", r"\bniel state\b",
        # Mechanism markers
        r"\bsovereign[ -]industrial[ -]?policy\b",
        r"\bprice floor\b", r"\bbinding offtake\b",
        r"\bsub-?commercial\b", r"\bbelow.*?treasury rate\b",
    ]),
    ("A1", [
        # Sovereign-strategic dual-tier raise pattern
        r"\brights (issue|offering)\b",
        r"\bfully[ -]?underwritten\b", r"\bbackstop(p?ed)?\b",
        r"\bsovereign[ -]strategic\b",
        r"\breserved (capital )?increase\b",
        # Named anchors (state-development-bank / family-foundation flavor)
        r"\bwallenberg\b", r"\binvestor ab\b", r"\binvestor a\.b\.\b",
        r"\bcrédit agricole\b", r"\bbnp paribas\b", r"\bcrédit mutuel\b",
        r"\bdanish state\b", r"\bfrench state\b", r"\bgerman state\b",
        r"\bape \b", r"\bbpifrance\b",
        r"\b(uk |british )?government\b.*?\b(equity|stake|recap)\b",
        # Family / promoter / founding shareholder anchors
        r"\bpromoter\b.*?\b(subscrib|backstop|underwr)",
        r"\bfounding (family|shareholder)\b",
        r"\bcontrolling (shareholder|family)\b",
        # Mechanism markers
        r"\bdirector(s)? (backstop|sub|under)",
        r"\binsider (backstop|sub|under|participat)",
        r"\bcornerstone (investor|underwrit|backstop)",
        r"\bcic\b", r"\bcornerstone\b",
    ]),
    ("F", [
        # MCB cascade / post-emergence with equity preserved
        r"\bmcb\b", r"\bmandatory convert", r"\bdebt[ -]for[ -]equity\b",
        r"\bdebt[ -]to[ -]equity\b", r"\bfounder\b.*?\b(stake|equity|lock|mcb|participat)\b",
        r"\bemerged (from )?ch\.?\s?11", r"\bpost[ -]reorg",
        r"\bplan of reorgani[sz]ation\b", r"\bpre[ -]?pack\b",
        r"\bequity raise as part of\b", r"\bnew common\b",
        r"\bpost[ -]?bankruptcy\b", r"\bemerg(es|ed|ing)\b",
        # Asian property MCB cascade
        r"\boffshore (debt|restructuring)\b.*?\b(equit|mcb|convert)",
        r"\bpart 26a?\b.*?\bcramdown\b",
        r"\bonshore.*?\b(restructure|debt|equit)\b",
    ]),
    ("B", [
        # Convertible/strategic instrument
        r"\bconvertible (senior )?notes?\b",
        r"\bcapped call\b", r"\bconvert (premium|coupon)\b",
        r"\bexchangeable (bond|note)\b",
        r"\bconvert(ible)?\s+(loan|stock|preferred)\b",
        # Strategic premium-to-VWAP placement
        r"\bpremium to (30|60|90)[ -]?day vwap\b",
        r"\bpremium to vwap\b", r"\bpremium to market\b",
        r"\bstrategic (anchor|investor|partner)\b.*?\b(premium|above|stake)\b",
        # Convertible-backed strategic
        r"\bwarrants? (issued|attached).*?\b(strike|exercise|conversion)\b",
    ]),
    ("C", [
        # Out-of-court LME
        r"\bexchange offer\b", r"\bliability management\b", r"\bconsent solicitation\b",
        r"\btender offer\b", r"\bout[ -]of[ -]court\b", r"\bcovenant relief\b",
        r"\bextend(ed|s|ing)? maturit", r"\ba\&e\b", r"\bamend(ed)? and extend",
        r"\bsuper[ -]priority\b", r"\bup[ -]?tier(ing)?\b",
        r"\bdebt repurchase\b", r"\bopen[ -]market buyback\b",
        r"\bdistressed exchange\b",
    ]),
    ("D", [
        # Strategic customer / parent recap
        r"\bcustomer\b.*?\b(jv|partnership|anchor|invest)\b",
        r"\bsupplier\b.*?\b(jv|partnership|anchor|invest)\b",
        r"\bparent\b.*?\b(injection|backstop|support)\b",
        r"\bjoint venture\b.*?\b(anchor|strategic)\b",
        r"\bmidea\b", r"\bbright dairy\b", r"\ba2 milk\b",
        r"\bhefei\b", r"\bgotion\b", r"\bvw powerco\b",
        r"\bofftake\b.*?\b(anchor|backstop|prepay)",
    ]),
    ("E", [
        # National bankruptcy frameworks preserving listed common
        r"\bsauvegarde( accélérée)?\b", r"\bstarug\b", r"\bwhoa\b", r"\bpn17\b",
        r"\bccaa\b", r"\brecovery judicial\b", r"\bjudicial recovery\b",
        r"\brehab(ilitation)?\b", r"\bre-?ipo\b", r"\bscheme of arrangement\b",
        r"\bpart 26a?\b", r"\baccelerated safeguard\b",
        r"\bnclt\b", r"\bibc\b", r"\bcompany voluntary arrangement\b",
        r"\bdoca\b", r"\brj plan\b",
    ]),
    ("G", [
        # Regulator-forced sector recap
        r"\bregulator(y)? (forced|mandate|forced recap)\b",
        r"\bmrel\b",
        r"\bcentral bank\b.*?\b(recap|capital|stress|directed)\b",
        r"\bcbn\b.*?\b(floor|capital|recap)\b",
        r"\bsector[ -]wide\b.*?\brecap\b",
        r"\bbank recap\b", r"\bcapital floor\b",
        r"\bstress test\b.*?\b(recap|capital|fail|pass)\b",
        r"\bbasel\b.*?\b(capital|recap)\b",
        # Specific country regulators
        r"\bhfsf\b", r"\bnlfi\b", r"\bukgi\b", r"\bhm treasury\b",
        r"\bregulator[ -]forced\b", r"\bstate[ -]capital\b",
        r"\bagr\b", r"\bspectrum\b.*?\b(recap|capital)\b",
    ]),
    ("H", [
        # Governance reset / state exit / parent-child
        r"\bnlfi\b", r"\bukgi\b", r"\bhfsf\b", r"\bhcap\b",
        r"\bstate[ -]exit\b", r"\bsell[ -]down\b",
        r"\bvalue[ -]?up\b", r"\bparent[ -]child\b",
        r"\bmandatory tob\b", r"\bgovernance reset\b",
        r"\bsubsidiary takeout\b", r"\blisted subsidiary\b",
        r"\bdivestment pipeline\b", r"\bof[ -]?s\b",
        r"\bmps\b.*?\b(deadline|requirement|float)\b",
        r"\bfiea (amendment|threshold)\b",
        r"\btse (cost of capital|disclosure)\b",
        r"\bkrx value[ -]?up\b", r"\bsasac\b",
        r"\btake[ -]?private\b", r"\bmbo\b",
        r"\bboard reset\b", r"\bgovernance overhaul\b",
        r"\bactivist (board|investor)\b",
        r"\bspaldy\b", r"\bgilinski\b", r"\bkretinsky\b", r"\bniel\b",
    ]),
    # ---- KEDM event-driven archetypes (Kupperman / Praetorian Capital
    #      Event-Driven Monitor — extends the framework's restructuring-
    #      only taxonomy to non-distress event-driven setups that share
    #      the structural-asymmetry property.) ----
    ("K1", [   # de-SPAC redemption arb
        r"\bde[ -]?spac\b", r"\bbusiness combination agreement\b",
        r"\bredemption right\b", r"\btrust value\b",
        r"\bpre[ -]?merger arb\b",
    ]),
    ("K2", [   # post-IPO lockup expiry
        r"\block[ -]?up expir", r"\block[ -]?up release\b",
        r"\b180[ -]?day lock\b", r"\bunlock event\b",
        r"\bpost[ -]?ipo lock",
    ]),
    ("K3", [   # going-dark / Section 12 deregistration
        r"\bgoing dark\b", r"\bform 15\b", r"\b15-12[BGD]\b",
        r"\bsection 12 deregist", r"\bvoluntary delist",
        r"\bdark pink",
    ]),
    ("K4", [   # SPAC trust value-at-redemption arb
        r"\bspac trust\b", r"\btrust account redemption\b",
        r"\bredemption price\b.*?\bspac\b",
        r"\bsponsor warrant\b",
    ]),
    ("K5", [   # reverse-merger shell-company filings
        r"\breverse merger\b", r"\bshell company\b",
        r"\bbackdoor (?:listing|ipo)\b", r"\breverse[ -]?takeover\b",
    ]),
    ("K6", [   # NOL preserved tax-asset cases
        r"\bnol carryforward\b", r"\bnet operating loss\b.*?\bpreserv",
        r"\bnol shell\b", r"\bnol(s)? of \$",
        r"\bsection 382\b", r"\btax asset preservation\b",
    ]),
    ("K7", [   # litigation-settlement event arb
        r"\bsettlement agreement\b.*?\b(class|securities)\b",
        r"\bjudgment day\b", r"\bappeal pending\b",
        r"\binjunction (?:lifted|vacated)\b",
        r"\bfinal approval\b.*?\bsettlement\b",
        r"\b(?:multidistrict|mdl-\d+)\b",
    ]),
    ("K8", [   # commodity-cycle inflection with named supply-side deficit
        r"\bsupply deficit\b", r"\bproduction deficit\b",
        r"\babove[ -]?ground stockpile\b",
        r"\bsecondary supply (?:exhaust|depleted)",
        r"\bbreak[ -]?even.*?(?:>|above) \$",
    ]),
    # ---- F-archetype subcodes (process_improvements v3 §6, v4 §7) ----
    ("F2", [   # equity carve-out — parent IPOs subsidiary, retains control
        r"\bequity carve[ -]?out\b", r"\bipo of subsidiary\b",
        r"\bmajority[ -]retained spin", r"\bcarve[ -]?out.*?ipo\b",
    ]),
    ("F3", [   # butterfly / split-up (Section 355(e))
        r"\bbutterfly transaction\b", r"\bsplit[ -]?up\b",
        r"\bsection 355\(e\)\b", r"\breciprocal exchange\b",
        r"\bdivisive reorganization\b",
    ]),
    # ---- K9 SCDI / VRI / sovereign warrants (process_improvements v3 §17) ----
    ("K9", [
        r"\b(?:scdi|state[ -]contingent debt instrument)\b",
        r"\b(?:vri|value recovery instrument)\b",
        r"\bgdp warrant\b", r"\bcommodity[ -]linked sovereign\b",
        r"\bsovereign warrant\b",
    ]),
]

# Status patterns — extended with completed-arc + false-friend detectors
STATUS_PATTERNS: list[tuple[str, list[str]]] = [
    # Completed arc — re-rated past entry
    ("ARC_DONE", [
        r"\bcompleted arc\b", r"\bre[ -]?rated\b", r"\bmultibagger\b",
        r"\brecovered\b", r"\bdividend(s)? (resumed|restored|reinstat)",
        r"\bbenchmark.*?(deliver|delivered)\b",
        r"\b(\d+)x\b.*?(since|by|to)\b",
        r"\bsold up\b", r"\bre-?rate done\b", r"\bnow consolidator\b",
        r"\bat all[ -]time\b", r"\batH\b",
        r"\bpost[ -]2023 recover", r"\b2009 → 20\d\d\b",
    ]),
    # False friend / court reversal / private take-out
    ("PASS_FALSE_FRIEND", [
        r"\bcourt of appeal\b.*?\b(set aside|reverse|overturn)",
        r"\bsanction.*?(set aside|reverse)",
        r"\btaken private\b", r"\bgone private\b",
        r"\b(sidara|epcg|elliott).*?\bcash takeover\b",
        r"\bdelisted\b.*?\b(202[0-9]|gone)\b",
        r"\bequity (wiped|gone|cancelled|cram|zero)\b",
        r"\bch\.?\s?22\b", r"\brefiled\b", r"\bre[ -]ch\.?\s?11\b",
        r"\bsecond filing\b", r"\bre[ -]?filed\b",
        r"\bliquidat(ed|ion)\b", r"\bwound (up|down)\b",
        r"\bcreditor[ -]?cram\b",
    ]),
    # Acquired / closed
    ("ACQUIRED", [
        r"\bacquired\b.*?\(?\b20\d\d\b",
        r"\bclosed (20\d\d|2025|2026)",
        r"\b(merged|merger).*?\b(post|completed)\b",
        r"\(private[ ;]\s*\b20\d\d\b",       # "(private 2023)" / "(private; KKR)"
        r"\(private[ ;].*?\)",                # bare "(private; X)" tag
        r"\bgone private\b",
    ]),
    # Re-restructured
    ("REPEAT_RX", [
        r"\bch\.?\s?22\b", r"\bre[ -]ch\.?\s?11\b",
        r"\bre[ -]?file", r"\bsecond filing\b",
        r"\btwice through ch\.?\s?11\b",
        r"\brescue lapsed\b", r"\bsecond restructure\b",
    ]),
    # Yellow flag (conditional, ongoing risk)
    ("YELLOW", [
        r"\byellow flag\b",
        r"\bconditional\b.*?\b(state|backstop|support)\b",
        r"\bgone (conditional|away)\b",
        r"\bcollateral.*?\bdemand\b",
        r"\bbalance[ -]?sheet adapting\b",
    ]),
    # Pre-recap watch
    ("PRE_RECAP", [
        r"\bwatch\b.*?\bfor (refi|deal|round|recap)\b",
        r"\bpre[ -]recap\b",
        r"\b(honda|consortium|consortium).*?\btalks\b",
        r"\bstrategic alternatives\b",
        r"\bstrategic review\b",
        r"\bcontemplated\b",
    ]),
]

# Confidence tier mapping (from the universe.md ★/○/▲ tags)
CONF_SCORE = {"★": 3, "○": 2, "▲": 1, "": 1}

# Bucket weights — extended with the actual variations seen in universe.md
BUCKET_WEIGHT = {
    "A": 1.0, "A (low)": 0.4, "A (very low)": 0.2, "A (warn)": 0.6,
    "A→B": 0.7, "B": 0.9, "B → done": 0.5,
    "C → B": 0.8, "C → C": 0.0, "C → acquired": 0.0, "C → done": 0.5,
    "C": 0.2, "C/B": 0.6,
    "n/a": 0.5, "—": 0.4, "": 0.4,
}

# Archetype weights — bumped Unknown slightly since we can't always parse
ARCH_WEIGHT = {
    "A1": 1.0, "A2": 1.05, "B": 0.85, "C": 0.75, "D": 0.90,
    "E": 0.75, "F": 0.70, "G": 0.90, "H": 0.80,
    # KEDM event-driven archetypes — same asymmetry property as
    # restructuring archetypes but typically shorter-duration trades.
    "K1": 0.80, "K2": 0.70, "K3": 0.85, "K4": 0.75,
    "K5": 0.65, "K6": 0.95, "K7": 0.75, "K8": 1.00,
    "F2": 0.75, "F3": 0.80, "K9": 0.85,
    "Unknown": 0.50,
}

# Status multipliers
STATUS_PENALTY = {
    "OK": 1.0, "ARC_DONE": 0.20, "PASS_FALSE_FRIEND": 0.0,
    "ACQUIRED": 0.0, "PRE_RECAP": 0.70, "REPEAT_RX": 0.0,
    "YELLOW": 0.55, "PASS": 0.0,
}

# Region inference from section headers — ORDER MATTERS. More-specific
# regions (Latin America with country names) must come before
# catch-alls (MEA / Frontier) so "argentina" matches LatAm not MEA.
REGION_KEYWORDS = {
    "Latin America":   ["brazil", "brasil", "mexico", "latam", "latin america",
                        "argentina", "argentine", "milei", "chile", "colombia",
                        "peru", "venezuela", "vaca muerta"],
    "United Kingdom":  ["uk rights", "lse", "united kingdom", "uk —", "uk —",
                        "british"],
    "France":          ["french"],
    "Continental Europe": ["european recaps", "european reb", "european bank",
                          "nordic", "baltic", "iberia", "greece",
                          "central / eastern europe", "continental europe",
                          "italian", "spanish", "german", "swiss", "dutch",
                          "european industrial", "eu industrial",
                          "post-iaa", "eu sovereign", "iaa cohort",
                          "mittelstand", "green industrial-policy"],
    "Greater China / HK": ["china property", "china non-property",
                          "china non-prop", "hong kong", "hk listed",
                          "greater china"],
    "Japan":           ["japan", "tokyo", "tse"],
    "Korea":           ["korea", "kospi", "krx"],
    "SE Asia / Pacific": ["indonesia", "malaysia", "singapore", "thailand",
                         "philippines", "vietnam", "australia", "nz",
                         "new zealand", "sri lanka", "pakistan", "bangladesh"],
    "MEA / Frontier":  ["mea", "israel", "turkey", "egypt", "türkiye",
                       "gulf", "africa", "ukraine", "saudi", "uae",
                       "abu dhabi", "qatar", "bahrain", "kuwait", "oman",
                       "dubai", "iran", "iraq", "lebanon",
                       "ddep", "ghana", "nigeria", "nigerian", "south african",
                       "frontier", "post-default sovereign"],
    "United States/Canada": ["energy", "renewables", "ev / battery",
                            "healthcare", "retail", "real estate",
                            "banks", "telecom", "crypto", "auto parts",
                            "shipping", "north america", "us-listed",
                            "ing / lloyds"],
}

# Currency symbols → 'has size class' detector
SIZE_PATTERNS = [
    re.compile(r"[$€£][\s]?\d[\d,.]*\s?(bn|m|million|billion)", re.IGNORECASE),
    re.compile(r"\b\d[\d,.]*\s?(bn|m)\b", re.IGNORECASE),
    re.compile(r"\b(SEK|NOK|DKK|CHF|RMB|HK\$|CHF|JPY|AUD|NZD|CAD)\s*\d", re.IGNORECASE),
    re.compile(r"\bRmb\s*\d", re.IGNORECASE),
]
SIZE_LARGE_PATTERNS = [
    re.compile(r"[$€£]\s*\d[\d,.]*\s?bn", re.IGNORECASE),
    re.compile(r"\bbillion\b", re.IGNORECASE),
    re.compile(r"\bbn\b", re.IGNORECASE),
]

# Vintage / year detection
YEAR_PATTERN = re.compile(r"\b(20\d\d)\b")

# Patterns that indicate the deal is still active even if a prior year is referenced
STILL_ACTIVE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bwatch\b", r"\bpending\b", r"\bongoing\b", r"\bin progress\b",
        r"\blive\b", r"\bcurrent\b", r"\bnow\b", r"\binvest\b",
        r"\b202[5-9]\b", r"\b20[3-9]\d\b",
    ]
]


@dataclass
class Candidate:
    name: str
    ticker: str
    conf: str
    bucket: str
    notes: str
    section: str
    region: str
    archetype: str = "Unknown"
    secondary_archetypes: list[str] = field(default_factory=list)
    status: str = "OK"
    triage_score: float = 0.0
    vintage_year: int | None = None
    size_class: str = "?"  # small / mid / large
    flags: list[str] = field(default_factory=list)


def infer_region(section: str, top_section: str = "") -> str:
    s = (section + " " + top_section).lower()
    for region, keys in REGION_KEYWORDS.items():
        if any(k in s for k in keys):
            return region
    return "Unspecified"


# Region detection from row content — runs as a per-row override when the
# section header gave "Unspecified" (e.g. the auto-promoted-from-pollers
# section, which mixes hits across jurisdictions).
_RX_JAPANESE = re.compile(r"[぀-ヿ一-鿿]")
_RX_TICKER_JP = re.compile(r"^[0-9]{4}[A-Z0-9]?$")  # TSE 4-digit + check
_RX_PLC = re.compile(r"\bPLC\b", re.I)  # UK only (AU/NZ/IN use LIMITED)
_RX_NSM_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)
_RX_TICKER_CN_HK = re.compile(r"^\d{3,4}$|^HK[\s:]")
_RX_SEDAR_ID = re.compile(r"\b[0-9]{9}\b")
_RX_EDGAR_ACC = re.compile(r"\b\d{10}-\d{2}-\d{6}\b")
_RX_ASX_HINT = re.compile(r"\b(ASX|Australian|Australia|NZ\s|"
                          r"Appendix\s+3[XYZ]|substantial\s+holder|"
                          r"scheme\s+(?:booklet|implementation))\b", re.I)
_RX_CVM_HINT = re.compile(r"\b(CVM|IPE|Recupera|Fato\s+Relevante|"
                          r"Cisão|OPA|Cisao)\b", re.I)


# Accession-format fingerprints for each poller (handle existing rows
# whose notes don't carry an explicit [source] tag).
_RX_ACC_ASX = re.compile(r"\b\d{4}-\d{8}-\d?[A-Z]?\d{6,}\b")
_RX_ACC_TDNET = re.compile(r"\b1401\d{14,16}\b")            # 14-18 digit
_RX_ACC_CVM = re.compile(r"\b\d{6}IPE\d{6,}-\d{1,3}\b")
_RX_ACC_PACER = re.compile(r"\bdocket-\d{7,}\b")
_RX_ACC_SEDAR = re.compile(r"\b\d{6}_\d{1,2}_[A-Za-z]{3}_\d{4}_\d{4}_EDT\b|"
                           r"\b00005\d{4}\b")               # SEDAR issuer #


def infer_region_from_row(name: str, ticker: str, notes: str) -> str:
    """Per-row region inference for auto-promoted rows where the section
    header gave no signal. Explicit [source] tag wins; then accession-
    format fingerprints; then content keywords; finally PLC name suffix.
    Falls back to Unspecified."""
    combined = f"{name} {ticker} {notes}"
    # Japanese characters anywhere → Japan
    if _RX_JAPANESE.search(combined):
        return "Japan"
    if _RX_TICKER_JP.match(ticker.strip()):
        return "Japan"
    # Explicit [source] tag wins
    if "[ASX]" in notes:
        return "SE Asia / Pacific"
    if "[CVM-IPE]" in notes:
        return "Latin America"
    if "[SEDAR+]" in notes:
        return "United States/Canada"
    if "[CourtListener-RECAP]" in notes:
        return "United States/Canada"
    if "[NSM]" in notes:
        return "United Kingdom"
    if "[TDnet]" in notes:
        return "Japan"
    # Any [EDGAR-*] tagged source is US (EDGAR is SEC-only)
    if "[EDGAR-" in notes or "[OFAC]" in notes or "[LDA-Senate]" in notes:
        return "United States/Canada"
    if "[FRED-" in notes:
        return "United States/Canada"
    # Accession-format fingerprints (for legacy rows lacking the tag)
    if _RX_ACC_ASX.search(notes):
        return "SE Asia / Pacific"
    if _RX_ACC_TDNET.search(notes):
        return "Japan"
    if _RX_ACC_CVM.search(notes):
        return "Latin America"
    if _RX_ACC_PACER.search(notes):
        return "United States/Canada"
    if _RX_ACC_SEDAR.search(notes):
        return "United States/Canada"
    # Content-keyword hints
    if _RX_ASX_HINT.search(notes):
        return "SE Asia / Pacific"
    if _RX_CVM_HINT.search(notes):
        return "Latin America"
    if "sedarplus.ca" in notes.lower():
        return "United States/Canada"
    if _RX_EDGAR_ACC.search(notes):
        return "United States/Canada"
    if _RX_NSM_UUID.search(notes):
        return "United Kingdom"
    # PLC suffix → UK (strict: just PLC, not LIMITED).
    if _RX_PLC.search(name):
        return "United Kingdom"
    return "Unspecified"


# Auto-promoted-row event-type -> archetype. The archetype keyword
# classifier was built for richly-described hand-curated universe.md
# rows; auto-promoted rows carry a terse "[SOURCE] Auto-promoted from
# <form> (acc ...); <event note>" plus boilerplate. Map the poller
# event-type DIRECTLY to the correct archetype so these rows aren't
# left to fuzzy keyword matching (which mis-fired — e.g. "primary doc"
# matched the DOE/DOC A2 pattern and tagged everything A2).
POLLER_EVENT_ARCHETYPE: list[tuple[str, str, list[str]]] = [
    # (substring in note/label, primary, secondaries)
    ("fresh-start accounting",          "F", []),   # post-reorg emergence
    ("emerged from chapter 11",         "F", []),
    ("plan of reorganization",          "F", []),
    ("post-reorg",                      "F", []),
    ("going-dark",                      "K3", []),
    ("section 12(g) registration",      "K3", []),
    ("section 12(b)",                   "K3", []),
    ("removal from listing",            "K3", []),   # 25-NSE delisting
    ("delisting / continued-listing",   "K3", []),
    ("delisting-deficiency",            "K3", []),
    ("deficiency signal",               "K3", []),
    ("definitive merger proxy",         "C", []),    # merger vote / arb
    ("merger proxy",                    "C", []),
    ("self-tender",                     "C", []),
    ("dutch auction",                   "C", []),
    ("tender offer",                    "C", []),
    ("scheme of arrangement",           "E", []),
    ("plan of arrangement",             "E", []),
    ("recuperação judicial",            "E", []),
    ("judicial recovery",               "E", []),
    ("civil rehabilitation",            "E", []),
    ("voluntary administration",        "E", []),
    ("chapter 11",                      "E", []),
    ("proxy contest",                   "H", []),    # activist campaign
    ("activist proxy",                  "H", []),
    ("non-management soliciting",       "H", []),
    ("5pct beneficial-ownership",       "H", []),    # SC 13D
    ("material change to 5pct",         "H", []),
    ("major shareholder",               "H", []),
    ("controlling-shareholder",         "H", []),
    ("rights offering",                 "A1", []),
    ("rights issue",                    "A1", []),
    ("open offer",                      "A1", []),
    ("capital increase",                "A1", []),
    ("third-party share allocation",    "B", []),    # PIPE
    ("convertible",                     "B", []),
    ("exchange offer",                  "C", []),
    ("consent solicitation",            "C", []),
    ("liability management",            "C", []),
    ("restructuring plan",              "E", []),
    ("company voluntary arrangement",   "E", []),
    ("mbo",                             "H", []),
    ("management buyout",               "H", []),
    ("institutional revealed preference", "H", []),  # 13F smart-money
    ("13f",                             "H", []),
    ("cluster sells",                   "H", []),
    ("going concern",                   "E", []),
    ("restatement",                     "E", []),
    ("material fact",                   "C", []),
    ("ofac",                            "G", []),     # sanctions
    ("sanctions",                       "G", []),
]

# Boilerplate to strip before archetype keyword matching so framework
# annotations don't leak into classification.
_BOILERPLATE = re.compile(
    r"\[[^\]]+\]|auto-promoted from|\(acc [^)]*\)|"
    r"verify (?:primary )?doc(?:ument)? before scoring|"
    r"verify against primary docs?|filing \d{4}-\d{2}-\d{2}", re.I)


def classify_archetypes(notes: str, section: str = "") -> tuple[str, list[str]]:
    """Return (primary, [secondary]) archetype codes. For auto-promoted
    rows, map the poller event-type directly; otherwise run the keyword
    classifier on boilerplate-stripped text."""
    raw = f"{notes} {section}"
    low = raw.lower()
    # 1. Auto-promoted rows: event-type -> archetype (exact, not fuzzy)
    if "auto-promoted" in low or "[edgar-" in low or "[nsm]" in low \
            or "[tdnet]" in low or "[asx]" in low or "[cvm-ipe]" in low \
            or "[sedar+]" in low or "[courtlistener" in low \
            or "[ofac]" in low or "[lda-senate]" in low:
        for needle, prim, sec in POLLER_EVENT_ARCHETYPE:
            if needle in low:
                return prim, sec
    # 2. Keyword classifier on boilerplate-stripped text
    text = _BOILERPLATE.sub(" ", raw).lower()
    hits: list[str] = []
    for code, patterns in ARCHETYPE_PATTERNS:
        for p in patterns:
            if re.search(p, text):
                if code not in hits:
                    hits.append(code)
                break
    if hits:
        return hits[0], hits[1:]
    return classify_by_section_prior(section), []


# Section-context archetype priors: when the row's notes are too terse
# to trigger a keyword hit, infer from the section banner. These are
# the high-confidence section-to-archetype mappings used as defaults.
SECTION_PRIORS = [
    # H archetype dominant sections
    ("parent-child takeout",             "H"),
    ("h6 parent-child",                  "H"),
    ("value-up",                         "H"),
    ("h4 value-up",                      "H"),
    ("state-exit",                       "H"),
    ("governance reset",                 "H"),
    # G archetype dominant sections
    ("ddep",                             "G"),
    ("post-default",                     "G"),
    ("bank recap",                       "G"),
    ("forced sector recap",              "G"),
    ("regulator",                        "G"),
    ("nigerian banks",                   "G"),
    ("sovereign recovery",               "G"),
    # F archetype (post-ch.11 / MCB cascade)
    ("post-ch.11",                       "F"),
    ("post-bankruptcy",                  "F"),
    ("post-emerg",                       "F"),
    ("post-reorg",                       "F"),
    ("emerged",                          "F"),
    ("chapter 11",                       "F"),
    ("china property",                   "F"),
    ("mcb cascade",                      "F"),
    # E archetype (court-supervised survival)
    ("post-rehab",                       "E"),
    ("rehabilitation",                   "E"),
    ("recovery judicial",                "E"),
    ("starug",                           "E"),
    ("whoa",                             "E"),
    ("pn17",                             "E"),
    ("ccaa",                             "E"),
    # A2 (sovereign industrial-policy)
    ("sovereign-anchored critical mineral", "A2"),
    ("critical minerals",                "A2"),
    ("ddc + chips",                      "A2"),
    ("sovereign industrial policy",      "A2"),
    ("post-iaa cohort",                  "A2"),
    ("green industrial-policy",          "A2"),
    # A1 (sovereign-strategic + rights)
    ("rights-issue universe",            "A1"),
    ("rights issue",                     "A1"),
    ("ing / lloyds 2009 template",       "A1"),
    ("mittelstand & industrial recaps",  "A1"),
    ("sovereign-anchored",               "A1"),
    ("italian + spanish bank consolidation", "A1"),
    ("milei",                            "A1"),
    ("argentina + brazil",               "A1"),
    ("saudi/uae sovereign-anchored",     "A1"),
    # C (LME / exchange offers)
    ("exchange offer",                   "C"),
    ("convertible",                      "C"),
    ("liability management",             "C"),
    # B (cyclical / strategic instrument)
    ("oilfield",                         "B"),
    ("offshore drilling",                "B"),
    ("coal / metallur",                  "B"),
    ("e&p",                              "B"),
    ("shipping",                         "B"),
    ("crypto / mining",                  "B"),
    ("auto parts",                       "B"),
    ("renewables / ev / battery",        "B"),
    ("cyclical",                         "B"),
]


def classify_by_section_prior(section: str) -> str:
    s = section.lower()
    for keyword, code in SECTION_PRIORS:
        if keyword in s:
            return code
    return "Unknown"


def classify_status(notes: str, bucket: str) -> str:
    text = notes.lower()
    for code, patterns in STATUS_PATTERNS:
        for p in patterns:
            if re.search(p, text):
                return code
    if any(b in bucket.strip() for b in ("C → C", "C → acquired")):
        return "ACQUIRED"
    if bucket.strip() == "C":
        return "PASS"
    return "OK"


def detect_vintage(notes: str, section: str) -> int | None:
    text = notes + " " + section
    years = [int(y) for y in YEAR_PATTERN.findall(text)]
    if not years:
        return None
    # Pick the *latest* explicit year mention; assume it's the active reference
    return max(years)


def is_still_active(notes: str) -> bool:
    return any(p.search(notes) for p in STILL_ACTIVE_PATTERNS)


def detect_size_class(notes: str) -> str:
    if not notes:
        return "?"
    for p in SIZE_LARGE_PATTERNS:
        if p.search(notes):
            return "large"
    for p in SIZE_PATTERNS:
        if p.search(notes):
            return "mid"
    return "small"


def vintage_decay(year: int | None, still_active: bool) -> float:
    """Penalty for old deals. Pre-2022 deals decay unless 'still active'."""
    if year is None:
        return 1.0
    if still_active:
        return 1.0
    today_year = date.today().year
    age = today_year - year
    if age <= 2:
        return 1.0
    if age <= 4:
        return 0.85
    if age <= 8:
        return 0.50
    return 0.25  # completed-arc territory


def size_multiplier(size: str) -> float:
    return {"large": 1.10, "mid": 1.0, "small": 0.90, "?": 0.95}[size]


_CONF_CHARS = set("★○●◐▲△◆◇☆")
_BUCKET_RE = re.compile(
    r"^\s*(A|B|C|D)\b(?:\s*(?:→|->|/)\s*[A-D](?:\s*\(?\w+\)?)?)?\s*$"
    r"|^\s*[A-D]\s*\(", re.I)


def _classify_columns(rest: list[str]) -> tuple[str, str, str]:
    """From the cells AFTER (name, ticker), identify (conf, bucket, notes)
    by content so heterogeneous prior-session table layouts all parse.

    - conf: a cell that is purely confidence glyphs (★/○/▲/●/◐) or a
      fraction like "3/3" (triangulation, treated as high confidence).
    - bucket: a cell matching a bucket code (A, B, C, "C → B", "A (low)").
    - notes: the longest remaining cell (the descriptive column), else "".
    """
    conf = bucket = ""
    used = [False] * len(rest)
    # 1. confidence column: glyphs, or an N/M triangulation fraction
    for i, cell in enumerate(rest):
        s = cell.strip()
        if s and (all(ch in _CONF_CHARS or ch.isspace() for ch in s)
                  or re.fullmatch(r"\d\s*/\s*\d", s)):
            conf, used[i] = s, True
            break
    # 2. bucket column: a bucket code
    for i, cell in enumerate(rest):
        if used[i]:
            continue
        if _BUCKET_RE.match(cell.strip()):
            bucket, used[i] = cell.strip(), True
            break
    # 3. notes: JOIN all remaining descriptive cells so signal-bearing
    #    flags in extra columns (e.g. an "Emerged" post-reorg marker,
    #    a "Triangulation" cell) are preserved rather than discarded.
    remaining = [rest[i].strip() for i in range(len(rest))
                 if not used[i] and rest[i].strip()
                 and rest[i].strip().lower() not in ("n/a", "na", "-", "—")]
    notes = " · ".join(remaining)
    return conf, bucket, notes


# Cross-source corroboration map (data/corroboration.json), loaded once.
# entity_stem -> n_distinct_sources. Multi-source names get a triage boost.
_CORROBORATION: dict[str, int] | None = None


def _load_corroboration() -> dict[str, dict]:
    """entity_stem -> {n_sources, conviction_score, ...} from
    data/corroboration.json."""
    global _CORROBORATION
    if _CORROBORATION is None:
        _CORROBORATION = {}
        path = REPO / "data" / "corroboration.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for stem, e in data.items():
                    if isinstance(e, dict):
                        _CORROBORATION[stem.upper()] = e
            except (json.JSONDecodeError, OSError, ValueError):
                _CORROBORATION = {}
    return _CORROBORATION


def corroboration_boost(c: Candidate) -> float:
    """Multiplier for names flagged by multiple pollers, scaled by the
    weighted CONVICTION score (event-severity × source-reliability ×
    recency), not just a raw source count. A hard, reliable, recent
    corroboration (bankruptcy + delisting) boosts more than soft,
    stale, repeated signals. Capped at x1.50."""
    corrob = _load_corroboration()
    keys = set()
    if c.ticker:
        keys.add(re.sub(r"[^A-Za-z0-9]", "", c.ticker.split(":")[-1]).upper())
    if c.name:
        keys.add(re.sub(r"[^A-Za-z0-9]", "",
                        re.sub(r"\b(plc|ltd|limited|inc|corp|corporation|"
                               r"group|holdings?|sa|nv|ag|co|se)\b", "",
                               c.name, flags=re.I)).upper())
    best = None
    for k in keys:
        e = corrob.get(k)
        if e and (best is None or
                  e.get("conviction_score", 0) > best.get("conviction_score", 0)):
            best = e
    if not best:
        return 1.0
    conv = float(best.get("conviction_score", 0.0))
    n = int(best.get("n_sources", 0))
    if n < 2:
        return 1.0
    # Map conviction to a boost: ~1.0 conviction → +0.15, ~2.5 → +0.50.
    boost = 1.0 + min(0.50, 0.15 + 0.14 * conv)
    return round(min(1.50, boost), 3)


def triage_score(c: Candidate) -> float:
    bucket_clean = c.bucket.strip()
    bw = BUCKET_WEIGHT.get(bucket_clean, 0.5)
    aw = ARCH_WEIGHT.get(c.archetype, 0.5)
    # Secondary archetype bonus: name with multiple matching archetypes
    # is a richer story (A1+G, F+A etc).
    if c.secondary_archetypes:
        aw *= 1.0 + 0.10 * len(c.secondary_archetypes)
    sp = STATUS_PENALTY.get(c.status, 1.0)
    conf_w = CONF_SCORE.get(c.conf.strip(), 1) / 3.0
    note_w = min(1.25, 0.60 + len(c.notes) / 180.0)
    vintage_w = vintage_decay(c.vintage_year, is_still_active(c.notes))
    size_w = size_multiplier(c.size_class)
    corrob_w = corroboration_boost(c)
    return bw * aw * sp * conf_w * note_w * vintage_w * size_w * corrob_w


def parse() -> list[Candidate]:
    text = UNIVERSE_MD.read_text()
    section = ""
    top_section = ""
    region = "Unspecified"
    candidates: list[Candidate] = []

    in_table = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            section = line[4:].strip()
            region = infer_region(section, top_section)
            in_table = False
            continue
        if line.startswith("## "):
            top_section = line[3:].strip()
            region = infer_region(section, top_section)
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.match(r"^[-:\s]+$", c) for c in cells):
            in_table = True
            continue
        if not in_table:
            if "Name" in cells and "Ticker" in cells:
                pass
            continue
        if len(cells) < 4:
            continue
        name = cells[0]
        ticker = cells[1] if len(cells) > 1 else ""
        # Content-aware column detection. universe.md aggregates tables
        # from many prior sessions with heterogeneous layouts — e.g.
        # "| Name | Ticker | Conf | Bucket | Notes |" AND
        # "| Name | Ticker | Bucket | Triangulation | Status |". A fixed
        # positional read mangled the latter (McDermott, Calfrac, Ørsted,
        # Petra Diamonds — the prior-session core picks — scored ~0.05 and
        # were dropped). Identify each field by its CONTENT among the
        # remaining cells instead of assuming a position.
        rest = cells[2:]
        conf, bucket, notes = _classify_columns(rest)
        if name.lower() == "name" or ticker.lower() == "ticker":
            continue
        if not name or name.startswith("---"):
            continue

        # Parsing improvement: resolve CIK-only identifiers to real
        # tickers so CIK:NNNN rows rank + display by ticker. Also
        # collapse a multi-ticker cell ("OPIRQ, OPITQ") to the first.
        m_cik = re.match(r"CIK[:\s]*0*(\d+)", ticker, re.I)
        if m_cik:
            resolved = resolve_cik_to_ticker(m_cik.group(1))
            if resolved:
                ticker = resolved
        elif "," in ticker:
            ticker = ticker.split(",")[0].strip()

        row_region = region
        if row_region == "Unspecified":
            row_region = infer_region_from_row(name, ticker, notes)
        c = Candidate(name=name, ticker=ticker, conf=conf, bucket=bucket,
                      notes=notes, section=section, region=row_region)
        c.archetype, c.secondary_archetypes = classify_archetypes(notes, section)
        c.status = classify_status(notes, bucket)
        c.vintage_year = detect_vintage(notes, section)
        c.size_class = detect_size_class(notes)
        c.triage_score = triage_score(c)

        # Build flag list
        if c.vintage_year and c.vintage_year < 2022 and not is_still_active(notes):
            c.flags.append("vintage<2022")
        if c.size_class == "large":
            c.flags.append("large")
        if c.secondary_archetypes:
            c.flags.append(f"multi:{'+'.join([c.archetype] + c.secondary_archetypes)}")
        candidates.append(c)

    return candidates


def render(candidates: list[Candidate]) -> str:
    by_region: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_region[c.region].append(c)

    lines = [
        f"# Universe-wide screen v2 ({date.today().isoformat()})",
        "",
        "Auto-generated by `src/universe_screen.py` from `universe.md`.",
        "Do NOT hand-edit.",
        "",
        f"**Universe size: {len(candidates)} named candidates across "
        f"{len(by_region)} regions and {len(set(c.section for c in candidates))} sectors.**",
        "",
        "v2 (vs v1): massively expanded keyword sets (Korea/Japan/Asia/EM",
        "regulators), vintage extraction with completed-arc decay, false-friend",
        "and court-reversal status patterns, multi-archetype tagging,",
        "size-class proxy from currency-amount detection.",
        "",
        "## Score distribution",
        "",
    ]

    counts = Counter()
    for c in candidates:
        s = c.triage_score
        if s >= 0.80: counts["T0"] += 1
        elif s >= 0.55: counts["T1"] += 1
        elif s >= 0.35: counts["T2"] += 1
        elif s >= 0.20: counts["T3"] += 1
        else: counts["pass"] += 1
    lines.append("| Triage tier | Threshold | Count | Action |")
    lines.append("|---|---|---|---|")
    lines.append(f"| **T0** | ≥ 0.80 | {counts['T0']} | full YAML build + verify ASAP |")
    lines.append(f"| **T1** | 0.55–0.80 | {counts['T1']} | priority YAML build-out |")
    lines.append(f"| **T2** | 0.35–0.55 | {counts['T2']} | watch + light YAML |")
    lines.append(f"| **T3** | 0.20–0.35 | {counts['T3']} | sector-context only |")
    lines.append(f"| **pass** | < 0.20 | {counts['pass']} | universe ballast |")
    lines.append("")

    # Archetype mix
    primary_counts = Counter(c.archetype for c in candidates)
    multi_count = sum(1 for c in candidates if c.secondary_archetypes)
    lines.append("## Archetype classification (primary + multi-tag)")
    lines.append("")
    lines.append("| Archetype | Primary count |")
    lines.append("|---|---|")
    for a, n in primary_counts.most_common():
        lines.append(f"| {a} | {n} |")
    lines.append(f"\n*{multi_count} names carry secondary archetype tags (e.g. A1+G).*")
    lines.append("")

    # Status mix
    status_counts = Counter(c.status for c in candidates)
    lines.append("## Status classification")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|---|---|")
    for s, n in status_counts.most_common():
        lines.append(f"| {s} | {n} |")
    lines.append("")

    # Vintage mix
    vintage_counts = Counter()
    for c in candidates:
        if c.vintage_year is None:
            vintage_counts["unknown"] += 1
        elif c.vintage_year >= 2024:
            vintage_counts["2024+"] += 1
        elif c.vintage_year >= 2022:
            vintage_counts["2022-2023"] += 1
        elif c.vintage_year >= 2018:
            vintage_counts["2018-2021"] += 1
        else:
            vintage_counts["pre-2018"] += 1
    lines.append("## Vintage distribution (detected year)")
    lines.append("")
    lines.append("| Cohort | Count |")
    lines.append("|---|---|")
    for k in ["2024+", "2022-2023", "2018-2021", "pre-2018", "unknown"]:
        lines.append(f"| {k} | {vintage_counts[k]} |")
    lines.append("")

    # Region summary
    lines.append("## Region summary")
    lines.append("")
    lines.append("| Region | Names | T0+T1 | Mean score | Top score | Top name |")
    lines.append("|---|---|---|---|---|---|")
    for region in sorted(by_region):
        cs = sorted(by_region[region], key=lambda x: -x.triage_score)
        if not cs:
            continue
        mean = sum(c.triage_score for c in cs) / len(cs)
        t0t1 = sum(1 for c in cs if c.triage_score >= 0.55)
        top = cs[0]
        lines.append(f"| **{region}** | {len(cs)} | {t0t1} | {mean:.2f} | {top.triage_score:.2f} | {top.name} ({top.ticker}) |")
    lines.append("")

    # Top per region — show 40 per region so the downstream reward/risk
    # ranker (universe_risk_reward.py, which parses these tables) has a
    # deep enough candidate pool to build a genuine top-100 by asymmetry.
    for region in sorted(by_region):
        cs = sorted(by_region[region], key=lambda x: -x.triage_score)[:40]
        if not cs:
            continue
        lines.append(f"## {region} — top {len(cs)} by triage score")
        lines.append("")
        lines.append("| Score | Name | Ticker | Conf | Bucket | Archetype | Status | Vintage | Size |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for c in cs:
            arch = c.archetype + ("+" + ",".join(c.secondary_archetypes) if c.secondary_archetypes else "")
            v = c.vintage_year or "?"
            lines.append(
                f"| {c.triage_score:.2f} | {c.name} | {c.ticker} | {c.conf} | "
                f"{c.bucket} | {arch} | {c.status} | {v} | {c.size_class} |"
            )
        lines.append("")

    # Global top 75
    lines.append("## Global top 75 (triage-score ranked)")
    lines.append("")
    lines.append("| # | Score | Name | Ticker | Bucket | Archetype | Status | Region | Vintage |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(sorted(candidates, key=lambda x: -x.triage_score)[:75], 1):
        arch = c.archetype + ("+" + ",".join(c.secondary_archetypes) if c.secondary_archetypes else "")
        v = c.vintage_year or "?"
        lines.append(
            f"| {i} | {c.triage_score:.2f} | **{c.name}** | {c.ticker} | "
            f"{c.bucket} | {arch} | {c.status} | {c.region} | {v} |"
        )
    lines.append("")

    # Priority YAML build-out queue
    have_yamls = set()
    yaml_dir = REPO / "data" / "candidates"
    if yaml_dir.exists():
        for y in yaml_dir.glob("*.yaml"):
            have_yamls.add(y.stem.upper())
    lines.append("## Priority YAML build-out queue")
    lines.append("")
    lines.append("Names scored T0/T1 that DO NOT yet have a YAML in `data/candidates/`.")
    lines.append("These are the candidates the next research pass should verify against")
    lines.append("primary filings and promote.")
    lines.append("")
    # Build YAML-name lookup that also matches by name fragment (ELUX-B, MPVD)
    yaml_name_tokens = set()
    for y in have_yamls:
        yaml_name_tokens.add(y)
        # Also strip non-alphanumeric for fuzzier match
        yaml_name_tokens.add(re.sub(r"[^A-Z0-9]", "", y))

    needs_yaml = [c for c in candidates if c.triage_score >= 0.55 and c.status == "OK"]
    needs_yaml.sort(key=lambda x: -x.triage_score)
    seen_names = set()
    queue = []
    for c in needs_yaml:
        # Match ticker against YAML stems; consider both colon-suffixed and bare forms
        raw = c.ticker.upper()
        for sep in [":", "."]:
            if sep in raw:
                raw = raw.split(sep)[-1]
        ticker_key = re.sub(r"[^A-Z0-9-]", "", raw)
        ticker_key_clean = re.sub(r"[^A-Z0-9]", "", ticker_key)
        if ticker_key in yaml_name_tokens or ticker_key_clean in yaml_name_tokens:
            continue
        # Also match by name token
        name_token = re.sub(r"[^A-Za-z]", "", c.name.split()[0]).upper()
        if name_token and name_token in yaml_name_tokens:
            continue
        if c.name in seen_names:
            continue
        seen_names.add(c.name)
        queue.append(c)
    lines.append("| Score | Name | Ticker | Region | Bucket | Archetype | Vintage | Size |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in queue[:40]:
        arch = c.archetype + ("+" + ",".join(c.secondary_archetypes) if c.secondary_archetypes else "")
        v = c.vintage_year or "?"
        lines.append(
            f"| {c.triage_score:.2f} | **{c.name}** | {c.ticker} | "
            f"{c.region} | {c.bucket} | {arch} | {v} | {c.size_class} |"
        )
    lines.append("")
    lines.append(f"**{len(queue)} names need YAML build-out.** Top 40 shown.")
    lines.append("")

    # Flagged-out section: completed arcs and false friends that scored high
    lines.append("## Sanity check: high-scoring names auto-flagged as completed arc / false friend")
    lines.append("")
    flagged = [c for c in candidates if c.triage_score >= 0.30 and c.status in
               ("ARC_DONE", "PASS_FALSE_FRIEND", "REPEAT_RX")]
    flagged.sort(key=lambda x: -x.triage_score)
    if not flagged:
        lines.append("*No high-scoring names were auto-flagged. Review notes column for missed cases.*")
    else:
        lines.append("| Score | Name | Status | Why filtered |")
        lines.append("|---|---|---|---|")
        for c in flagged[:25]:
            lines.append(f"| {c.triage_score:.2f} | {c.name} | {c.status} | {c.notes[:80]} |")
    lines.append("")

    return "\n".join(lines) + "\n"


def write_full_candidate_csv(candidates: list["Candidate"]) -> None:
    """Emit EVERY scored candidate to a complete machine-readable CSV so
    the downstream reward/risk ranker sees the full universe, not just the
    lossy per-region top-40 display tables (which silently dropped 200+
    investable names below the display cutoff — Transocean, Peabody,
    Chesapeake, Valaris, the whole energy/coal/drilling restructuring
    universe)."""
    import csv as _csv
    out = REPO / "output" / "universe_full.csv"
    with out.open("w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["score", "name", "ticker", "conf", "bucket",
                    "archetype", "status", "vintage", "size", "region"])
        for c in sorted(candidates, key=lambda x: -x.triage_score):
            arch = c.archetype + ("+" + ",".join(c.secondary_archetypes)
                                  if c.secondary_archetypes else "")
            w.writerow([f"{c.triage_score:.2f}", c.name, c.ticker, c.conf,
                        c.bucket, arch, c.status,
                        c.vintage_year or "?", c.size_class, c.region])


def main():
    candidates = parse()
    OUT.write_text(render(candidates))
    write_full_candidate_csv(candidates)
    print(f"Wrote {OUT}")
    print(f"  {len(candidates)} candidates parsed (full set → output/universe_full.csv)")
    print(f"  T0 (>=0.80): {sum(1 for c in candidates if c.triage_score >= 0.80)}")
    print(f"  T1 (0.55-0.80): {sum(1 for c in candidates if 0.55 <= c.triage_score < 0.80)}")
    print(f"  T2 (0.35-0.55): {sum(1 for c in candidates if 0.35 <= c.triage_score < 0.55)}")
    print(f"  Unknown archetype: {sum(1 for c in candidates if c.archetype == 'Unknown')}")
    print(f"  Multi-archetype: {sum(1 for c in candidates if c.secondary_archetypes)}")


if __name__ == "__main__":
    main()
