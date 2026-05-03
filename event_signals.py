"""Event-driven incentive signals on top of PSU comp analysis.

Implements the 12 techniques catalogued from the "Show me the incentives"
public archive synthesis:

  1. Incentive-stack mapping     -> emergent composite of the others
  2. Controller bid gap          -> only when an active bid exists
  3. Change-of-control pay       -> CIC payment scale + alignment
  4. Strategic-review read       -> committees, advisers, language
  5. Event-kicker over floor     -> already encoded in psu_scoring
  6. Buyback amplifier           -> authorisation $ vs market cap
  7. Board-composition signal    -> M&A/PE/restructuring backgrounds
  8. Financing-capacity check    -> cash + revolver references in proxy
  9. Majority-of-the-minority    -> only when an active bid exists
 10. Theme-plus-governance       -> categorical, downstream of governance
 11. Operating inflection        -> narrative; lightly detected here
 12. Cash-shell / net-net        -> stub mention + activist overlap

Scope here is what's tractable from the DEF 14A text alone (already
cached). Techniques 2 and 9 require an active offer and are scored
N/A unless that condition is detected. Methods that need 10-K-only
data (full revolver / cash) degrade gracefully when proxy text doesn't
surface the relevant lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Pattern bank
# ---------------------------------------------------------------------------

# 4. Strategic-review read-through ------------------------------------------
SPECIAL_COMMITTEE = re.compile(
    r"\b(special committee|value enhancement committee|"
    r"strategic alternatives? committee|strategic review committee|"
    r"transaction committee|finance and strategy committee)\b",
    re.I,
)
STRATEGIC_LANG = re.compile(
    r"\b(strategic alternatives?|maximi[sz]e (shareholder|stockholder) value|"
    r"explor(e|ing) (a )?(sale|merger|all|strategic)|"
    r"formal (review )?process|review of strategic options|"
    r"unsolicited (offer|proposal)|going[- ]private)\b",
    re.I,
)
ADVISERS = re.compile(
    r"\b(Goldman Sachs|Morgan Stanley|Lazard|Centerview|Evercore|"
    r"Moelis|Houlihan Lokey|Citi(group)?|J\.?P\.?\s*Morgan|"
    r"Bank of America|BofA Securities|Barclays|Jefferies|Rothschild|"
    r"PJT Partners|Guggenheim|Greenhill|UBS|William Blair|Raymond James|"
    r"Perella Weinberg|Wells Fargo Securities|Stifel|Piper Sandler|"
    r"Cantor Fitzgerald|Qatalyst Partners)\b",
    re.I,
)
ENGAGED_AS_ADVISER = re.compile(
    r"(engaged|retained|appointed) .{0,50}(financial advis|investment bank)",
    re.I,
)


# 7. Activist signals -------------------------------------------------------
ACTIVISTS = re.compile(
    r"\b("
    r"Elliott (Investment )?Management|Elliott Associates|"
    r"Starboard Value|"
    r"(Carl )?Icahn|Icahn (Enterprises|Capital)|"
    r"Pershing Square|Bill Ackman|"
    r"JANA Partners|"
    r"Engaged Capital|Engine Capital|"
    r"Politan Capital|"
    r"Voce Capital|"
    r"Donerail|"
    r"Ancora (Holdings|Advisors)?|"
    r"Trian (Fund Management|Partners)?|"
    r"Cevian Capital|"
    r"Sachem Head|"
    r"Land & Buildings|"
    r"Blackwells|"
    r"Sandell Asset|"
    r"Standard General|"
    r"Permian Investment|"
    r"Ides Capital|"
    r"Cruiser Capital|"
    r"Macellum|"
    r"Legion Partners|"
    r"Coliseum Capital|"
    r"Saba Capital"
    r")\b",
    re.I,
)


# 3. Change-of-control pay --------------------------------------------------
CIC_HEADER = re.compile(
    r"(potential payments?.{0,60}upon (termination|change[- ]in[- ]control)|"
    r"change[- ]in[- ]control (table|payments|benefits)|"
    r"golden parachute|severance and change[- ]in[- ]control)",
    re.I,
)
DOUBLE_TRIGGER = re.compile(r"\bdouble[- ]trigger\b", re.I)
SINGLE_TRIGGER = re.compile(r"\bsingle[- ]trigger\b", re.I)
SECTION_280G = re.compile(r"\bSection\s*280G\b", re.I)


# 6. Buyback amplifier ------------------------------------------------------
BUYBACK_AUTH_DOLLAR = re.compile(
    r"(?:repurchase program|stock repurchase|share repurchase|"
    r"buyback program).{0,160}?\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)",
    re.I,
)
BUYBACK_REMAINING = re.compile(
    r"(remaining|available).{0,40}\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)"
    r".{0,80}(repurchas|buyback)",
    re.I,
)


# Controller / founder concentration ----------------------------------------
# Looks for "X% beneficially owned" or "owns Y%" patterns in ownership table.
OWNER_PCT = re.compile(
    r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(of (the )?outstanding|of (the )?shares|"
    r"beneficially owned|beneficial ownership)",
    re.I,
)
ALL_DIRECTORS_OFFICERS = re.compile(
    r"all directors and (executive )?officers as a group.{0,200}?"
    r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
    re.I,
)


# 7. Board composition ------------------------------------------------------
BOARD_MA_KEYWORDS = re.compile(
    r"\b(M&A|mergers? (and|&) acquisitions|sale of (the )?company|"
    r"strategic transaction|take[- ]private|private equity|"
    r"restructuring|leveraged buyout|LBO|special situations|"
    r"buy[- ]side|sell[- ]side advisory|chief restructuring officer)\b",
    re.I,
)
PE_FIRM_AFFIL = re.compile(
    r"\b(KKR|Blackstone|Apollo|Carlyle|Thoma Bravo|Vista Equity|"
    r"Bain Capital|Silver Lake|TPG|Warburg Pincus|Hellman & Friedman|"
    r"Advent International|General Atlantic|Insight Partners|"
    r"Francisco Partners|GTCR|Madison Dearborn|Clayton Dubilier|"
    r"Berkshire Partners|Apax|EQT|CVC|Permira)\b",
    re.I,
)


# 8. Financing-capacity (best-effort) ---------------------------------------
REVOLVER = re.compile(
    r"(revolver|revolving credit|undrawn (revolver|capacity)|"
    r"availability under (the )?(revolving )?credit facility).{0,80}"
    r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)",
    re.I,
)
CASH_AND_EQUIV = re.compile(
    r"cash (and|&) (cash )?equivalents.{0,40}"
    r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(million|billion|m\b|bn\b)",
    re.I,
)


# 11. Operating inflection (lightweight) ------------------------------------
INFLECTION_LANG = re.compile(
    r"\b(inflection point|turning point|momentum|transformation|"
    r"new product launch|product[- ]market fit|"
    r"return to growth|reaccelerat)\b",
    re.I,
)


# Active-bid detection ------------------------------------------------------
ACTIVE_BID = re.compile(
    r"(received (an? )?(unsolicited )?(proposal|offer)|merger agreement|"
    r"definitive agreement|acquisition agreement|"
    r"go[- ]private (transaction|proposal)|tender offer|"
    r"agreed to be acquired|will be acquired)",
    re.I,
)
OFFER_PRICE = re.compile(
    r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*per share",
    re.I,
)
MAJORITY_OF_MINORITY = re.compile(
    r"\bmajority of (the )?(unaffiliated )?minority\b|"
    r"\bmajority[- ]of[- ](the[- ])?minority\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_usd_millions(value: float, unit: str) -> float:
    u = unit.lower().strip()
    if u in ("billion", "bn", "b"):
        return value * 1000.0
    return value  # assume million


def _largest_owner_pct(text: str) -> float | None:
    """Best-effort largest single owner % from the beneficial-ownership
    table. Looks at the first 8000 chars after a 'Security Ownership' header."""
    m = re.search(r"security ownership", text, re.I)
    region = text[m.start(): m.start() + 8000] if m else text[:8000]
    pcts = []
    for pm in OWNER_PCT.finditer(region):
        try:
            v = float(pm.group(1))
            if 1.0 <= v <= 95.0:
                pcts.append(v)
        except ValueError:
            pass
    if not pcts:
        return None
    pcts.sort(reverse=True)
    # Skip the top "all directors and officers as a group" if disproportionately
    # large; real controllers usually appear separately too.
    return pcts[0]


def _insiders_group_pct(text: str) -> float | None:
    m = ALL_DIRECTORS_OFFICERS.search(text)
    if not m:
        return None
    try:
        return float(m.group(2))
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

@dataclass
class EventFeatures:
    ticker: str

    # Strategic review
    has_special_committee: bool = False
    strategic_alts_language: bool = False
    advisers_named: list[str] = field(default_factory=list)
    engaged_adviser: bool = False

    # Activists
    activists_named: list[str] = field(default_factory=list)

    # CIC
    has_cic_table: bool = False
    double_trigger: bool = False
    single_trigger: bool = False
    section_280g: bool = False

    # Buyback
    buyback_authorisation_musd: float | None = None
    buyback_remaining_musd: float | None = None

    # Ownership / control
    largest_owner_pct: float | None = None
    insiders_group_pct: float | None = None

    # Board
    board_ma_keyword_count: int = 0
    pe_firm_count: int = 0

    # Financing
    revolver_capacity_musd: float | None = None
    cash_musd: float | None = None

    # Operating inflection
    inflection_language: bool = False

    # Active bid (rare; only when a deal is in flight)
    active_bid: bool = False
    offer_price: float | None = None
    majority_of_minority: bool = False


def extract_event_features(ticker: str, text: str) -> EventFeatures:
    f = EventFeatures(ticker=ticker)

    # Strategic review -----------------------------------------------------
    f.has_special_committee = bool(SPECIAL_COMMITTEE.search(text))
    f.strategic_alts_language = bool(STRATEGIC_LANG.search(text))
    f.advisers_named = sorted({m.group(0) for m in ADVISERS.finditer(text)})
    f.engaged_adviser = bool(ENGAGED_AS_ADVISER.search(text))

    # Activists ------------------------------------------------------------
    f.activists_named = sorted({m.group(0) for m in ACTIVISTS.finditer(text)})

    # CIC ------------------------------------------------------------------
    f.has_cic_table = bool(CIC_HEADER.search(text))
    f.double_trigger = bool(DOUBLE_TRIGGER.search(text))
    f.single_trigger = bool(SINGLE_TRIGGER.search(text))
    f.section_280g = bool(SECTION_280G.search(text))

    # Buyback --------------------------------------------------------------
    auths = []
    for m in BUYBACK_AUTH_DOLLAR.finditer(text):
        try:
            auths.append(_to_usd_millions(float(m.group(1)), m.group(2)))
        except ValueError:
            pass
    if auths:
        f.buyback_authorisation_musd = max(auths)
    rem = BUYBACK_REMAINING.search(text)
    if rem:
        try:
            f.buyback_remaining_musd = _to_usd_millions(float(rem.group(2)), rem.group(3))
        except ValueError:
            pass

    # Ownership ------------------------------------------------------------
    f.largest_owner_pct = _largest_owner_pct(text)
    f.insiders_group_pct = _insiders_group_pct(text)

    # Board composition ----------------------------------------------------
    f.board_ma_keyword_count = sum(1 for _ in BOARD_MA_KEYWORDS.finditer(text))
    f.pe_firm_count = len({m.group(0) for m in PE_FIRM_AFFIL.finditer(text)})

    # Financing capacity ---------------------------------------------------
    rv = REVOLVER.search(text)
    if rv:
        try:
            f.revolver_capacity_musd = _to_usd_millions(float(rv.group(5)), rv.group(6))
        except (ValueError, IndexError):
            pass
    cm = CASH_AND_EQUIV.search(text)
    if cm:
        try:
            f.cash_musd = _to_usd_millions(float(cm.group(3)), cm.group(4))
        except (ValueError, IndexError):
            pass

    # Operating inflection -------------------------------------------------
    f.inflection_language = bool(INFLECTION_LANG.search(text))

    # Active bid -----------------------------------------------------------
    f.active_bid = bool(ACTIVE_BID.search(text))
    if f.active_bid:
        prices = [float(m.group(1)) for m in OFFER_PRICE.finditer(text)
                  if 0.10 <= float(m.group(1)) <= 1000.0]
        if prices:
            # Most-quoted offer price = best guess.
            from collections import Counter
            f.offer_price = Counter(prices).most_common(1)[0][0]
        f.majority_of_minority = bool(MAJORITY_OF_MINORITY.search(text))

    return f


# ---------------------------------------------------------------------------
# Method scoring (each 0-100)
# ---------------------------------------------------------------------------

def score_strategic_review(f: EventFeatures) -> tuple[float, list[str]]:
    score = 0.0
    flags: list[str] = []
    if f.has_special_committee:
        score += 40
        flags.append("Special / strategic-alternatives committee disclosed")
    if f.engaged_adviser:
        score += 20
        flags.append("Financial adviser explicitly engaged")
    if f.advisers_named:
        score += min(15, 5 * len(f.advisers_named))
        flags.append(f"Advisers named: {', '.join(f.advisers_named[:3])}")
    if f.strategic_alts_language:
        score += 15
        flags.append("Strategic-alternatives language present")
    if f.active_bid:
        score += 10
        flags.append(f"Active bid detected"
                     + (f" at ${f.offer_price:.2f}/share" if f.offer_price else ""))
    return min(100.0, score), flags


def score_change_of_control(f: EventFeatures) -> tuple[float, list[str]]:
    score = 0.0
    flags: list[str] = []
    if f.has_cic_table:
        score += 40
    if f.double_trigger:
        score += 25
        flags.append("Double-trigger CIC vesting (shareholder-friendly)")
    if f.single_trigger:
        score += 15  # less aligned but still a clear deal incentive
        flags.append("Single-trigger CIC vesting (deal-friendly to mgmt)")
    if f.section_280g:
        score += 10
        flags.append("280G analysis present (golden-parachute mechanics live)")
    if f.has_cic_table and not (f.double_trigger or f.single_trigger):
        score += 10  # CIC payments at least exist
    return min(100.0, score), flags


def score_buyback(f: EventFeatures, market_cap_usd: float | None) -> tuple[float, list[str]]:
    if f.buyback_authorisation_musd is None:
        return 0.0, []
    flags: list[str] = []
    auth = f.buyback_authorisation_musd
    if market_cap_usd and market_cap_usd > 0:
        pct = (auth * 1e6) / market_cap_usd
        flags.append(f"Buyback authorisation ${auth:.0f}M = {pct*100:.1f}% of mcap")
        # 5% of mcap -> 50; 20%+ -> 100.
        score = float(min(100.0, max(0.0, pct * 500)))
    else:
        score = 30.0
        flags.append(f"Buyback authorisation ${auth:.0f}M (mcap unknown)")
    return score, flags


def score_controller(f: EventFeatures) -> tuple[float, list[str]]:
    flags: list[str] = []
    pct = f.largest_owner_pct or 0.0
    insiders = f.insiders_group_pct or 0.0
    if insiders > pct:
        pct = insiders
    if pct == 0:
        return 0.0, []
    # 10% -> 30; 30% -> 70; 50%+ -> 100. A controller stake creates pressure.
    score = float(min(100.0, pct * 2.0))
    if pct >= 50:
        flags.append(f"Majority controller present ({pct:.1f}%)")
    elif pct >= 20:
        flags.append(f"Concentrated holder ({pct:.1f}%)")
    elif pct >= 10:
        flags.append(f"Notable insider/institutional concentration ({pct:.1f}%)")
    return score, flags


def score_activist(f: EventFeatures) -> tuple[float, list[str]]:
    if not f.activists_named:
        return 0.0, []
    score = float(min(100.0, 35 + 20 * len(f.activists_named)))
    return score, [f"Activist holders cited: {', '.join(f.activists_named[:4])}"]


def score_board(f: EventFeatures) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 0.0
    if f.board_ma_keyword_count >= 5:
        score += 50
        flags.append(f"Board bios reference M&A/transaction keywords {f.board_ma_keyword_count}x")
    elif f.board_ma_keyword_count >= 2:
        score += 25
    if f.pe_firm_count >= 2:
        score += 30
        flags.append(f"Multiple PE-firm affiliations on board ({f.pe_firm_count})")
    elif f.pe_firm_count == 1:
        score += 15
    return min(100.0, score), flags


def score_financing(f: EventFeatures, market_cap_usd: float | None) -> tuple[float, list[str]]:
    if f.revolver_capacity_musd is None and f.cash_musd is None:
        return 0.0, []
    flags: list[str] = []
    headroom_m = (f.cash_musd or 0.0) + (f.revolver_capacity_musd or 0.0)
    if market_cap_usd and market_cap_usd > 0:
        ratio = (headroom_m * 1e6) / market_cap_usd
        flags.append(f"Cash + revolver headroom ${headroom_m:.0f}M = {ratio*100:.0f}% of mcap")
        score = float(min(100.0, ratio * 150))
    else:
        flags.append(f"Cash + revolver headroom ${headroom_m:.0f}M (mcap unknown)")
        score = 30.0
    return score, flags


def score_majority_of_minority(f: EventFeatures) -> tuple[float, list[str]]:
    if not f.active_bid:
        return 0.0, []
    if f.majority_of_minority:
        return 80.0, ["Majority-of-the-minority protection in place (bump leverage for minority)"]
    return 30.0, ["Active bid without explicit majority-of-the-minority protection"]


def score_inflection(f: EventFeatures) -> tuple[float, list[str]]:
    if f.inflection_language:
        return 50.0, ["Operating-inflection language present (narrative weight only)"]
    return 0.0, []


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

@dataclass
class StackScore:
    strategic_review: float
    change_of_control: float
    buyback: float
    controller: float
    activist: float
    board: float
    financing: float
    inflection: float
    majority_of_minority: float
    process_quality: float          # weighted composite
    flags: list[str]


def score_event_stack(f: EventFeatures, market_cap_usd: float | None) -> StackScore:
    sr, sr_flags = score_strategic_review(f)
    cc, cc_flags = score_change_of_control(f)
    bb, bb_flags = score_buyback(f, market_cap_usd)
    ct, ct_flags = score_controller(f)
    ac, ac_flags = score_activist(f)
    bd, bd_flags = score_board(f)
    fi, fi_flags = score_financing(f, market_cap_usd)
    inf, inf_flags = score_inflection(f)
    mm, mm_flags = score_majority_of_minority(f)

    # Process quality composite. The archive's emphasis is process > pure
    # economics, so committee + activist + CIC are weighted heavily.
    process_quality = (
        0.22 * sr
        + 0.18 * cc
        + 0.12 * bb
        + 0.13 * ct
        + 0.15 * ac
        + 0.08 * bd
        + 0.07 * fi
        + 0.05 * inf
    )

    flags = (sr_flags + cc_flags + bb_flags + ct_flags
             + ac_flags + bd_flags + fi_flags + inf_flags + mm_flags)
    return StackScore(
        strategic_review=round(sr, 1),
        change_of_control=round(cc, 1),
        buyback=round(bb, 1),
        controller=round(ct, 1),
        activist=round(ac, 1),
        board=round(bd, 1),
        financing=round(fi, 1),
        inflection=round(inf, 1),
        majority_of_minority=round(mm, 1),
        process_quality=round(process_quality, 1),
        flags=flags,
    )
