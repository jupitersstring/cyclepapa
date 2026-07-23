"""10b5-1 plan activity detector (terminations + adoptions + modifications).

Rule 10b5-1 plans are pre-arranged trading instructions that let
insiders trade despite possessing material non-public information.
Effective Feb 2023, the SEC requires public companies to disclose in
each 10-Q's Item 5 (Other Information) ALL 10b5-1 plan adoptions,
modifications, and TERMINATIONS during the quarter.

Two-way signal interpretation:
  TERMINATION of a SELL plan      = BULLISH (insider chose to keep stock)
  ADOPTION of a SELL plan         = BEARISH (insider committed to sell)
  MODIFICATION (terminate + re-adopt close in time) = NEUTRAL
  TERMINATION of a BUY plan       = BEARISH
  ADOPTION of a BUY plan          = BULLISH (rare)

This module:
  1. Pulls recent 10-Qs (and the most recent DEF 14A as a fallback) for
     each top asymmetric ticker.
  2. Isolates Item 5 / 'Trading Arrangements' section.
  3. Detects ALL three action types per NEO.
  4. Classifies sell vs buy; attributes the NEO + role + shares.
  5. Identifies modification (terminate + adopt by same person within
     45 days of each other).
  6. Caches the filing HTML permanently to .cache/docs/.
  7. Outputs cancel_10b5_1.json (resumable, incremental write).

Scoring (per action, signed):
  TERM SELL by CEO/Chair       +30 (size kicker +4 to +8)
  TERM SELL by CFO             +24
  TERM SELL other NEO          +18
  ADOPT SELL by CEO/Chair      -20 (size kicker)
  ADOPT SELL by CFO            -16
  ADOPT SELL other NEO         -12
  TERM BUY                      -8
  ADOPT BUY                     +8
  MODIFICATION (matched pair)   0 (overrides individual scores)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CACHE = Path("/home/user/cyclepapa/.cache/docs")
ROOT = Path("/home/user/cyclepapa")
OUT_JSON = ROOT / "cancel_10b5_1.json"
OUT_CSV = ROOT / "cancel_10b5_1.csv"


# ---------------------------------------------------------------------------
# 10-Q Item 5 isolation
# ---------------------------------------------------------------------------

ITEM5_ANCHORS = [
    re.compile(r"Item\s*5\.?\s*(?:Other\s+Information)?", re.I),
    re.compile(r"\bRule\s+10b5[- ]?1\s+(?:Trading\s+)?(?:Arrangement|Plan)s?", re.I),
    re.compile(r"\bTrading\s+(?:Arrangements?|Plans?)\b", re.I),
    re.compile(r"\b10b5[- ]?1\s+trading\s+(?:plan|arrangement)", re.I),
]


def isolate_trading_section(text: str, half_window: int = 8000) -> str:
    if not text:
        return ""
    spans = []
    for a in ITEM5_ANCHORS:
        for m in a.finditer(text):
            spans.append([max(0, m.start() - 500), min(len(text), m.start() + half_window)])
    if not spans:
        return ""
    spans.sort()
    merged = [spans[0]]
    for s in spans[1:]:
        if s[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], s[1])
        else:
            merged.append(s)
    out = []
    total = 0
    for s in merged:
        chunk = text[s[0]:s[1]]
        if total + len(chunk) > 60_000:
            chunk = chunk[: 60_000 - total]
        out.append(chunk)
        total += len(chunk)
        if total >= 60_000:
            break
    return "\n||SECT||\n".join(out)


# ---------------------------------------------------------------------------
# Termination patterns
# ---------------------------------------------------------------------------

# Termination triggers (intentional early cancellation)
TERMINATION_TRIGGERS = re.compile(
    r"(terminated|cancelled|canceled|rescinded)\s+"
    r"(?:his|her|their|the|a)?\s*"
    r"(?:Rule\s+10b5[- ]?1|10b5[- ]?1|"
    r"(?:trading|pre[- ]arranged)\s+(?:plan|arrangement|instructions))",
    re.I,
)
# Also: passive form ("...trading plan that was terminated...")
TERMINATION_TRIGGERS_PASSIVE = re.compile(
    r"(?:Rule\s+10b5[- ]?1|10b5[- ]?1)\s+(?:trading\s+)?(?:plan|arrangement)"
    r"[^.\n]{0,80}?(?:was|has\s+been)\s+(?:terminated|cancelled|canceled)",
    re.I,
)

# Adoption triggers
ADOPTION_TRIGGERS = re.compile(
    r"(adopted|entered\s+into)\s+(?:a\s+|the\s+)?"
    r"(?:trading\s+(?:plan|arrangement)|pre[- ]arranged\s+trading\s+plan|"
    r"Rule\s+10b5[- ]?1|10b5[- ]?1\s+(?:trading\s+)?(?:plan|arrangement))",
    re.I,
)

# Modification triggers (rare)
MODIFICATION_TRIGGERS = re.compile(
    r"(modified|amended)\s+(?:his|her|their|the|a)?\s*"
    r"(?:Rule\s+10b5[- ]?1|10b5[- ]?1|trading\s+(?:plan|arrangement))",
    re.I,
)

# Boilerplate "no insiders did anything" Item 5 statements
NEGATIVE_BOILERPLATE = [
    re.compile(r"none\s+of\s+(?:our|the\s+Company\'?s)\s+(?:directors|officers)"
               r"[^.\n]{0,200}?(?:adopted|terminated|modified)", re.I),
    re.compile(r"no\s+(?:Company\s+)?director\s+or\s+officer[^.\n]{0,150}?"
               r"(?:adopted|terminated|modified)", re.I),
    re.compile(r"no\s+Section\s+16\s+officer", re.I),
]

# Natural expiration (not a real termination)
EXPIRATION_BOILERPLATE = [
    re.compile(r"scheduled\s+to\s+terminate", re.I),
    re.compile(r"will\s+terminate\s+(?:upon|on)\s+the\s+earlier\s+of", re.I),
    re.compile(r"expir(?:e|ed|ation)\s+(?:in\s+accordance\s+with|of)\s+its\s+terms", re.I),
    re.compile(r"intended\s+to\s+terminate\s+on", re.I),
    re.compile(r"plan\s+(?:that\s+)?(?:will|shall)\s+terminate\s+(?:upon|on)", re.I),
    re.compile(r"expired\s+by\s+operation\s+of\s+its\s+terms", re.I),
]


def is_natural_expiration(snippet: str) -> bool:
    return any(p.search(snippet) for p in EXPIRATION_BOILERPLATE)


def is_negative_boilerplate(snippet: str) -> bool:
    return any(p.search(snippet) for p in NEGATIVE_BOILERPLATE)


# ---------------------------------------------------------------------------
# NEO + plan-type extraction near a termination hit
# ---------------------------------------------------------------------------

# NEO pattern: typical filing language is "On <date>, <First Last>,
# <title>, terminated a Rule 10b5-1...". Match First-Last directly
# (with optional middle name/initial) immediately preceding a comma
# followed by a title.
NEO_NEAR = re.compile(
    r"((?:Mr\.|Ms\.|Mrs\.|Dr\.)\s*[A-Z][a-zA-Z\.\-\']+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z\.\-\']+|"
    r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z\-\']+)"
    r"\s*,\s+"
    r"(?:our\s+|the\s+|former\s+)?"
    r"(Chief\s+(?:Executive|Financial|Operating|Legal|Accounting|Technology|"
    r"Commercial|Revenue|Product|People|Marketing)\s+Officer|"
    r"CEO|CFO|COO|"
    r"(?:Executive\s+|Vice\s+)?Chair(?:man|person)?(?:\s+(?:of\s+the\s+Board|and\s+\w+(?:\s+\w+){0,3}))?|"
    r"President(?:\s+and\s+\w+(?:\s+\w+){0,3})?|"
    r"General\s+Counsel|"
    r"(?:Senior\s+|Executive\s+)?Vice\s+President(?:\s+\w+)?|Director)",
    re.I,
)

# Words that, when they appear as the LAST token of a captured NEO
# name, indicate the regex straddled into the title. "Jensen Huang
# President" should be "Jensen Huang" with title "President" -- the
# NEO regex's flexible middle-name slot let "President" become a
# pseudo-surname. Same for "Vice President", "our officers", etc.
NEO_TAIL_BLACKLIST = {
    "president", "vice", "chair", "chairman", "chairperson",
    "ceo", "cfo", "coo", "officer", "counsel", "director", "officers",
    "executive", "senior", "co-founder", "founder",
}
NEO_HEAD_BLACKLIST = {"our", "the", "former", "to", "and", "by"}


def neo_passes_sanity(name: str) -> bool:
    if not name:
        return False
    parts = name.split()
    if not parts:
        return False
    if parts[0].lower() in NEO_HEAD_BLACKLIST:
        return False
    if parts[-1].lower() in NEO_TAIL_BLACKLIST:
        return False
    if len(parts) < 2:
        return False
    return True

# Fallback role-only search (used if NEO+role pair fails)
ROLE_NEAR = re.compile(
    r"(Chief\s+Executive\s+Officer|\bCEO\b|Chief\s+Financial\s+Officer|\bCFO\b|"
    r"Chief\s+Operating\s+Officer|\bCOO\b|"
    r"Chair(?:man|person)?(?:\s+(?:of\s+the\s+Board|and\s+\w+(?:\s+\w+){0,3}))?|"
    r"President(?:\s+and\s+\w+(?:\s+\w+){0,3})?|"
    r"General\s+Counsel|Chief\s+Legal\s+Officer|"
    r"Chief\s+(?:Technology|Accounting|Commercial|Revenue|Product|People|Marketing)\s+Officer|"
    r"Senior\s+Vice\s+President|Executive\s+Vice\s+President|Director)",
    re.I,
)

# Plan type
SELL_PLAN_KEYWORDS = re.compile(
    r"\b(?:sale|sell|dispose|disposition|disposing\s+of|sold|to\s+sell)\b", re.I,
)
BUY_PLAN_KEYWORDS = re.compile(
    r"\b(?:purchase|buy|acquir(?:e|ing)|acquisitions?\s+of\s+(?:shares|stock))\b", re.I,
)

# Shares covered
SHARES_NEAR = re.compile(
    r"(?:up\s+to\s+|aggregate\s+of\s+|maximum\s+of\s+|covering\s+)?([\d,]{3,12})\s+shares",
    re.I,
)
DATE_NEAR = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4})",
)


def extract_context(text: str, hit_start: int, hit_end: int,
                    radius: int = 1200) -> dict:
    ctx_lo = max(0, hit_start - radius)
    ctx_hi = min(len(text), hit_end + radius)
    window = text[ctx_lo:ctx_hi]

    # A tighter window for NEO+role: typically the named-officer + title
    # is within ~300 chars BEFORE the termination verb.
    tight_lo = max(0, hit_start - 400)
    tight_hi = min(len(text), hit_end + 100)
    tight = text[tight_lo:tight_hi]

    # CORPORATE BUYBACK / ASR EXCLUSION. The same Item 5 region
    # sometimes contains the company's own Rule 10b5-1 repurchase plan
    # (ASR / share repurchase program). These are not insider conviction
    # signals and should be filtered out at extraction time.
    corp_tokens = (
        "accelerated share repurchase", "asr agreement",
        "share repurchase program", "share buyback program",
        "the company entered into", "the company adopted",
        "the company's 10b5-1", "issuer trading plan",
        "company's trading plan",
    )
    tight_lower = tight.lower()
    is_corporate = any(t in tight_lower for t in corp_tokens)

    # RETROSPECTIVE PAYOUT vs FORWARD VESTING TRIGGER. Filings disclose
    # both "we achieved X" (backward-looking) and "vesting requires X"
    # (forward-looking). Mark events whose paragraph reads as
    # retrospective so the scorer can downweight them.
    retro_tokens = (
        "we achieved", "achieved adjusted ebitda of",
        "achieved revenue of", "actual performance",
        "resulted in a payout of", "earned at",
        "paid out at", "payout was", "delivered",
        "for purposes of the 2024 lip",
        "for purposes of the 2025 lip",
        "performance highlights",
    )
    is_retrospective = any(t in tight_lower for t in retro_tokens)

    # Plan type
    sell_count = len(SELL_PLAN_KEYWORDS.findall(window))
    buy_count = len(BUY_PLAN_KEYWORDS.findall(window))
    if sell_count > buy_count and sell_count >= 1:
        plan_type = "sell"
    elif buy_count > sell_count and buy_count >= 1:
        plan_type = "buy"
    else:
        plan_type = "unknown"

    # NEO + role (paired). Try tight window first, then wider.
    # Walk through every match in each window so we can skip ones whose
    # captured "name" is actually a role token (sanity blacklist).
    neo = None
    role = None
    for w in (tight, window):
        for m in NEO_NEAR.finditer(w):
            cand = m.group(1).strip()
            if neo_passes_sanity(cand):
                neo = cand
                role = m.group(2).strip()
                break
        if neo:
            break
    # Fallback: role-only search in tight window
    if not role:
        m = ROLE_NEAR.search(tight)
        if m:
            role = m.group(1).strip()

    # Shares -- search the TIGHT window first (within the actual
    # disclosure paragraph) to avoid pulling buyback-authorization
    # share counts from elsewhere.
    shares = None
    for w in (tight, window):
        m = SHARES_NEAR.search(w)
        if m:
            try:
                v = int(m.group(1).replace(",", ""))
                # Anything > 10M is almost certainly buyback or float, not
                # a 10b5-1 plan size.
                if 100 <= v <= 10_000_000:
                    shares = v
                    break
            except ValueError:
                pass

    # Adoption / termination dates
    dates = [d.group(1) for d in DATE_NEAR.finditer(window)][:4]

    return {
        "plan_type": plan_type,
        "neo": neo,
        "role": role,
        "shares": shares,
        "dates_near": dates,
        "is_corporate": is_corporate,
        "is_retrospective": is_retrospective,
        "snippet": re.sub(r"\s+", " ", window).strip()[:600],
    }


def detect_actions(text: str) -> list[dict]:
    """Detect all 10b5-1 plan actions in a filing: TERMINATE / ADOPT /
    MODIFY. Each event carries plan_type (sell/buy), NEO, role, shares,
    direction (bullish/bearish/neutral)."""
    section = isolate_trading_section(text)
    if not section:
        return []
    out = []
    seen_keys = set()

    def add_event(action: str, m: re.Match):
        snip = re.sub(r"\s+", " ", m.group(0)).strip()
        if is_negative_boilerplate(snip):
            return
        if action == "TERMINATE" and is_natural_expiration(snip):
            return
        # Check the FULL paragraph around the trigger for negative
        # boilerplate ("no director or officer adopted or terminated...").
        para = re.sub(r"\s+", " ",
                      section[max(0, m.start() - 400): m.end() + 400])
        if is_negative_boilerplate(para):
            return
        ctx = extract_context(section, m.start(), m.end())
        if action == "TERMINATE" and is_natural_expiration(ctx["snippet"]):
            return
        if is_negative_boilerplate(ctx["snippet"]):
            return
        # Corporate ASR / share repurchase plan -- not an insider signal
        if ctx.get("is_corporate"):
            return
        key = (action, ctx.get("neo") or "", ctx.get("shares") or 0, snip[:60])
        if key in seen_keys:
            return
        seen_keys.add(key)
        out.append({"action": action, "trigger": snip[:200], **ctx})

    for m in TERMINATION_TRIGGERS.finditer(section):
        add_event("TERMINATE", m)
    for m in TERMINATION_TRIGGERS_PASSIVE.finditer(section):
        add_event("TERMINATE", m)
    for m in ADOPTION_TRIGGERS.finditer(section):
        add_event("ADOPT", m)
    for m in MODIFICATION_TRIGGERS.finditer(section):
        add_event("MODIFY", m)

    # Dedupe near-identical events (same action + NEO + shares within 5 chars
    # of trigger; happens when both active/passive patterns match the same
    # underlying language).
    deduped = []
    seen_sig = set()
    for e in out:
        sig = (e["action"], (e.get("neo") or "").lower(),
               e.get("shares") or 0, e.get("filing_date"))
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        deduped.append(e)
    out = deduped

    # Pair terminate+adopt by same NEO when actions occur on or near the
    # same date (within 45 days). Treat same-filing-date matches as
    # automatic modification pairs.
    by_neo: dict[str, list] = {}
    for e in out:
        neo = (e.get("neo") or "").strip().lower()
        if neo:
            by_neo.setdefault(neo, []).append(e)
    for neo, events in by_neo.items():
        terms = [e for e in events if e["action"] == "TERMINATE"]
        adopts = [e for e in events if e["action"] == "ADOPT"]
        for t in terms:
            for a in adopts:
                # Same filing date = same 10-Q disclosure = same Item 5
                # entry = explicitly a modification
                if t.get("filing_date") == a.get("filing_date"):
                    t["modification_pair"] = True
                    a["modification_pair"] = True

    return out


def classify(e: dict) -> tuple[int, str]:
    """Return (signed_score, label) for one event."""
    role = (e.get("role") or "").lower()
    is_ceo = any(t in role for t in ("ceo", "chief executive", "chair",
                                       "executive chair", "president and ceo"))
    is_cfo = any(t in role for t in ("cfo", "chief financial"))
    shares = e.get("shares") or 0
    pt = e.get("plan_type")
    act = e.get("action")

    if e.get("modification_pair"):
        return 0, "modification_pair"

    # Retrospective payout disclosures (CD&A "we achieved X" language)
    # are not forward vesting conditions; they describe past payouts.
    # Heavily downweight rather than discard -- the regex was triggered
    # by 10b5-1-adjacent text, but the signal direction is unreliable.
    retro_mult = 0.3 if e.get("is_retrospective") else 1.0

    # ---------------- SCORING WEIGHTS (v3.3) ----------------
    # Weights blend academic priors and backtest signal direction;
    # they are NOT regression-fit to the backtest sample. Three
    # principled adjustments vs v3.2:
    #
    #  1. Plan SIZE is the strongest stratifier (>=250K terminations:
    #     71% beat-SPY, median excess +27% at 180d, n=17). The size
    #     kicker is structurally meaningful (250K shares ~= $20-100M
    #     of committed selling = real conviction, not tax planning).
    #     Boost from +8 to +12 at the >=250K tier and add a new
    #     +18 tier at >=1M shares for elephant terminations.
    #
    #  2. CFO modest bump (24 -> 26). Backtest shows CFO term_sell
    #     median excess +23% (n=10) and CFO adopt_sell median excess
    #     -21% (n=51). Role logic supports this: CFOs have privileged
    #     forward-cash-flow visibility. Small samples cap the bump.
    #
    #  3. CEO/Chair STAYS at 30. Backtest shows noisy CEO term_sell
    #     (n=13, median excess -16%) but mean +27% with right skew;
    #     too small to override prior. Founders/CEOs have material
    #     informational advantage (Cohen-Malloy-Pomorski etc.). Don't
    #     overfit to 13 events.
    # ---------------------------------------------------------

    if act == "TERMINATE":
        if pt == "sell":
            base = 30 if is_ceo else (26 if is_cfo else 18)
            # Plan-size kicker -- structurally meaningful AND empirically
            # the strongest stratifier in the backtest.
            if shares >= 1_000_000:   base += 18
            elif shares >= 250_000:   base += 12
            elif shares >= 100_000:   base += 8
            elif shares >= 50_000:    base += 4
            return int(base * retro_mult), "BULLISH terminate sell"
        if pt == "buy":
            return int(-8 * retro_mult), "BEARISH terminate buy"
        return int((10 if is_ceo else 5) * retro_mult), "neutral terminate (type unknown)"
    if act == "ADOPT":
        if pt == "sell":
            if shares and shares < 10_000:
                return int(-3 * retro_mult), "weak BEARISH adopt sell (small)"
            # CFO adoption is the strongest median bearish signal in
            # the backtest (n=51, median excess -21%, only 29% beat
            # SPY). Bump CFO bearish weight modestly.
            base = -20 if is_ceo else (-18 if is_cfo else -12)
            # Mirror the bullish-side size kicker -- a 1M+ share CEO
            # sell-plan adoption (FUBO's 3.4M, ADPT's 1.15M) signals
            # a different magnitude of commitment than a 50K plan.
            if shares >= 1_000_000:   base -= 10
            elif shares >= 500_000:   base -= 6
            elif shares >= 100_000:   base -= 3
            elif shares and shares < 25_000: base = max(base, -8)
            return int(base * retro_mult), "BEARISH adopt sell"
        if pt == "buy":
            return int(8 * retro_mult), "BULLISH adopt buy"
        return 0, "neutral adopt (type unknown)"
    if act == "MODIFY":
        return 0, "modify (direction unclear)"
    return 0, "unknown"


def score_events(events: list[dict]) -> tuple[float, list[str], dict]:
    """Aggregate signed scores across all 10b5-1 events."""
    score = 0.0
    reasons = []
    counts = {"term_sell": 0, "term_buy": 0, "adopt_sell": 0, "adopt_buy": 0,
              "modify_pair": 0, "neutral": 0}
    for e in events:
        s, label = classify(e)
        if e.get("modification_pair"):
            counts["modify_pair"] += 1
        elif e["action"] == "TERMINATE" and e.get("plan_type") == "sell":
            counts["term_sell"] += 1
        elif e["action"] == "TERMINATE" and e.get("plan_type") == "buy":
            counts["term_buy"] += 1
        elif e["action"] == "ADOPT" and e.get("plan_type") == "sell":
            counts["adopt_sell"] += 1
        elif e["action"] == "ADOPT" and e.get("plan_type") == "buy":
            counts["adopt_buy"] += 1
        else:
            counts["neutral"] += 1

        if s == 0:
            continue
        score += s
        neo = e.get("neo") or "an insider"
        role = e.get("role") or "?"
        sh = e.get("shares") or 0
        sh_str = f" {sh:,}sh" if sh else ""
        reasons.append(f"{label}: {neo} ({role[:30]}){sh_str} [{s:+d}]")
    return max(-80.0, min(80.0, score)), reasons, counts


# ---------------------------------------------------------------------------
# Filing fetch / cache
# ---------------------------------------------------------------------------

def acc_to_fname(acc: str) -> str:
    return f"{acc}.html"


def load_cached(acc: str) -> str:
    """Three-tier read: filesystem -> git archive commits -> miss.
    See cache_store.py for the disk-vs-git-packs rationale."""
    from cache_store import read_html
    raw = read_html(acc)
    if not raw:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))


def fetch_and_cache_filing(cik: str, acc: str, primary_doc: str) -> str:
    # Build canonical URL
    cik_n = str(int(cik))
    acc_clean = acc.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_n}/{acc_clean}/{primary_doc}"
    try:
        from edgar import _get
        raw = _get(url).text
    except Exception as e:
        print(f"  fetch fail: {e}", file=sys.stderr)
        return ""
    from cache_store import cache_html
    cache_html(acc, raw)  # honours CACHE_HTML=0 for disk-tight backfills
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))


def recent_10q_for(ticker: str, limit: int = 4, days: int = 540) -> list:
    """Pull recent 10-Q + 10-K (US filers) AND 20-F + 6-K (foreign
    private issuers). The 10-K's Part II Item 9B carries Q4 10b5-1
    disclosures that 10-Qs never cover. 20-F is the FPI annual report;
    6-K carries interim disclosures including some plan adoptions."""
    from recent import company_filings
    return company_filings(ticker,
                           forms=("10-Q", "10-K", "20-F", "6-K"),
                           limit_per_form=limit, days=days)


def is_foreign_filer(ticker: str) -> bool:
    """Detect whether a ticker is a foreign private issuer. Returns True
    if the company files 20-F (and no 10-K/10-Q) within the past 18 months."""
    from recent import company_filings
    try:
        us = company_filings(ticker, forms=("10-K", "10-Q"),
                             limit_per_form=1, days=540)
        if us:
            return False
        fpi = company_filings(ticker, forms=("20-F", "6-K"),
                              limit_per_form=1, days=540)
        return bool(fpi)
    except Exception:
        return False


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON via temp file + rename so a crash mid-write can't
    corrupt the resumable state."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


def dedupe_cross_quarter(events: list[dict]) -> list[dict]:
    """The SEC requires each 10b5-1 plan to be re-disclosed in every
    10-Q until the action is older than the reporting window. A single
    May termination shows up in May, Aug, and Nov filings. Without
    cross-quarter dedupe, one action scores 3x.

    Dedupe key: (action, neo_lower, role_lower, shares, plan_type).
    Keeps the EARLIEST filing_date (the original disclosure), drops
    re-disclosures."""
    by_sig: dict[tuple, dict] = {}
    for e in events:
        sig = (
            e.get("action") or "",
            (e.get("neo") or "").strip().lower(),
            (e.get("role") or "").strip().lower(),
            e.get("shares") or 0,
            e.get("plan_type") or "",
        )
        # Skip dedupe for events with no NEO and no shares -- they're
        # likely different events that happen to match
        if not sig[1] and not sig[3]:
            by_sig[(sig, e.get("filing_date") or "", e.get("accession") or "")] = e
            continue
        prev = by_sig.get(sig)
        if not prev or (e.get("filing_date") or "") < (prev.get("filing_date") or ""):
            by_sig[sig] = e
    return list(by_sig.values())


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def load_top_asymmetric() -> list[str]:
    p = ROOT / "top_asymmetric.csv"
    if not p.exists():
        return []
    return [r["ticker"] for r in csv.DictReader(open(p))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="",
                    help="Comma-separated tickers (overrides --top)")
    ap.add_argument("--tickers-file", default="",
                    help="Path to a file with one ticker per line")
    ap.add_argument("--top", type=int, default=60,
                    help="Top N from top_asymmetric.csv")
    ap.add_argument("--quarters", type=int, default=4,
                    help="Recent 10-Qs per ticker")
    ap.add_argument("--days", type=int, default=540)
    ap.add_argument("--sleep", type=float, default=0.20)
    ap.add_argument("--json", default=str(OUT_JSON),
                    help="Output JSON path (use per-shard for parallel runs)")
    ap.add_argument("--csv", default=str(OUT_CSV))
    ap.add_argument("--rescore-only", action="store_true",
                    help="Skip filings fetch; re-run extraction + scoring "
                         "on already-cached HTML for already-processed tickers.")
    args = ap.parse_args()
    out_json_path = Path(args.json)
    out_csv_path = Path(args.csv)

    if args.tickers_file:
        tickers = [t.strip().upper() for t in
                   Path(args.tickers_file).read_text().splitlines() if t.strip()]
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = load_top_asymmetric()[: args.top]

    print(f"Scanning {len(tickers)} tickers for 10b5-1 cancellations",
          flush=True)

    # Resume from existing
    out: dict = {}
    if out_json_path.exists():
        try:
            out = json.loads(out_json_path.read_text())
        except Exception:
            out = {}

    rows = []
    for i, tk in enumerate(tickers, 1):
        # Rescore-only: use the existing quarters_scanned list and
        # re-extract events from cached HTML; skip network entirely.
        if args.rescore_only and tk in out:
            prev = out[tk]
            quarters = prev.get("quarters_scanned") or []
            cur = {
                "ticker": tk,
                "quarters_scanned": quarters,
                "events": [],
                "score": 0.0,
                "reasons": [],
                "counts": {},
                "data_available": len(quarters) > 0,
                "_cache_version": "v3-dedup-foreign-aware",
            }
            for q in quarters:
                acc = q.get("accession")
                text = load_cached(acc) if acc else ""
                if not text:
                    continue
                events = detect_actions(text)
                for e in events:
                    e["accession"] = acc
                    e["filing_date"] = q.get("filing_date")
                    cur["events"].append(e)
            cur["events"] = dedupe_cross_quarter(cur["events"])
            sc, reasons, counts = score_events(cur["events"])
            cur["score"] = sc
            cur["reasons"] = reasons
            cur["counts"] = counts
            cur["_complete"] = True
            out[tk] = cur
            if i % 50 == 0:
                atomic_write_json(out_json_path, out)
            n = len(cur.get("events") or [])
            c = cur.get("counts") or {}
            rows.append({
                "ticker": tk,
                "n_quarters_scanned": len(cur.get("quarters_scanned") or []),
                "n_events": n,
                "term_sell": c.get("term_sell", 0),
                "adopt_sell": c.get("adopt_sell", 0),
                "term_buy": c.get("term_buy", 0),
                "adopt_buy": c.get("adopt_buy", 0),
                "modify_pair": c.get("modify_pair", 0),
                "score": round(cur.get("score", 0), 1),
                "data_available": cur.get("data_available"),
                "reasons": " | ".join(cur.get("reasons") or []),
            })
            continue
        # Skip if already processed
        if tk in out and out[tk].get("_complete"):
            cur = out[tk]
        else:
            cur = {
                "ticker": tk,
                "quarters_scanned": [],
                "events": [],
                "score": 0.0,
                "reasons": [],
                "counts": {},
                "data_available": None,  # True / False / None=untried
                "_cache_version": "v3-dedup-foreign-aware",
            }
            # BUGFIX (silent-drop audit): a transient filings-fetch
            # failure previously fell through to filings=[] and then
            # marked the record _complete with data_available=False, so
            # the ticker looked permanently like "no 10b5-1 data" and
            # never retried. Flag the failure and skip finalization so
            # the resume guard re-attempts it next run.
            _fetch_failed = False
            try:
                filings = recent_10q_for(tk, limit=args.quarters, days=args.days)
            except Exception as e:
                print(f"  {tk}: filings fetch fail: {e}", file=sys.stderr)
                filings = []
                _fetch_failed = True
            if _fetch_failed:
                cur["_fetch_error"] = True   # no _complete -> retried
                out[tk] = cur
                continue
            for fl in filings:
                acc = fl.accession
                text = load_cached(acc)
                if not text:
                    text = fetch_and_cache_filing(fl.cik, acc, fl.primary_doc)
                    time.sleep(args.sleep)
                if not text:
                    continue
                cur["quarters_scanned"].append({
                    "accession": acc, "filing_date": fl.filing_date,
                })
                events = detect_actions(text)
                for e in events:
                    e["accession"] = acc
                    e["filing_date"] = fl.filing_date
                    cur["events"].append(e)
            # data_available distinguishes "no 10b5-1 activity" from
            # "no 10-Q ever scanned" (foreign filers, IPO-only firms, etc.)
            cur["data_available"] = len(cur["quarters_scanned"]) > 0
            # Cross-quarter dedupe: same NEO+role+shares+action reported
            # in successive 10-Qs (each plan is repeated until it ages
            # out). Keep the oldest occurrence; drop the rest.
            cur["events"] = dedupe_cross_quarter(cur["events"])
            sc, reasons, counts = score_events(cur["events"])
            cur["score"] = sc
            cur["reasons"] = reasons
            cur["counts"] = counts
            cur["_complete"] = True
            out[tk] = cur
            atomic_write_json(out_json_path, out)

        n = len(cur.get("events") or [])
        c = cur.get("counts") or {}
        rows.append({
            "ticker": tk,
            "n_quarters_scanned": len(cur.get("quarters_scanned") or []),
            "n_events": n,
            "term_sell": c.get("term_sell", 0),
            "adopt_sell": c.get("adopt_sell", 0),
            "term_buy": c.get("term_buy", 0),
            "adopt_buy": c.get("adopt_buy", 0),
            "modify_pair": c.get("modify_pair", 0),
            "score": round(cur.get("score", 0), 1),
            "data_available": cur.get("data_available"),
            "reasons": " | ".join(cur.get("reasons") or []),
        })

        if i % 5 == 0:
            print(f"  [{i}/{len(tickers)}] {tk} scanned ({n} cancellations)",
                  flush=True)

    rows.sort(key=lambda r: -r["score"])
    fields = ["rank", "ticker", "data_available", "n_quarters_scanned",
              "n_events", "term_sell", "adopt_sell", "term_buy",
              "adopt_buy", "modify_pair", "score", "reasons"]
    with out_csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nWrote {out_csv_path} + {out_json_path}\n")
    nonzero = [r for r in rows if r["score"] != 0]
    print(f"=== {len(nonzero)} tickers with non-zero 10b5-1 signal "
          f"(bullish + bearish) ===")
    print(f"{'#':<3}{'TKR':<8}{'10Q':>4}{'EV':>4}{'TS':>4}{'AS':>4}"
          f"{'TB':>4}{'AB':>4}{'MP':>4}{'SCR':>5}  REASONS")
    print("-" * 200)
    for i, r in enumerate(nonzero[:40], 1):
        print(f"{i:<3}{r['ticker']:<8}{r['n_quarters_scanned']:>4}"
              f"{r['n_events']:>4}{r['term_sell']:>4}{r['adopt_sell']:>4}"
              f"{r['term_buy']:>4}{r['adopt_buy']:>4}{r['modify_pair']:>4}"
              f"{r['score']:>5.0f}  {r['reasons'][:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
