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
    neo = None
    role = None
    for w in (tight, window):
        m = NEO_NEAR.search(w)
        if m:
            neo = m.group(1).strip()
            role = m.group(2).strip()
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

    if act == "TERMINATE":
        if pt == "sell":
            base = 30 if is_ceo else (24 if is_cfo else 18)
            if shares >= 250_000: base += 8
            elif shares >= 50_000: base += 4
            return base, "BULLISH terminate sell"
        if pt == "buy":
            return -8, "BEARISH terminate buy"
        # Unknown plan type, but still meaningful for CEO/CFO
        return (10 if is_ceo else 5), "neutral terminate (type unknown)"
    if act == "ADOPT":
        if pt == "sell":
            # Size-conditional: tiny adoptions (<10K shares) are tax/RSU
            # liquidity, not meaningful bearish signal. Larger adoptions
            # are real conviction.
            if shares and shares < 10_000:
                return -3, "weak BEARISH adopt sell (small)"
            base = -20 if is_ceo else (-16 if is_cfo else -12)
            if shares >= 500_000: base -= 6
            elif shares >= 100_000: base -= 3
            elif shares and shares < 25_000: base = max(base, -8)
            return base, "BEARISH adopt sell"
        if pt == "buy":
            return 8, "BULLISH adopt buy"
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
    p = CACHE / acc_to_fname(acc)
    if not p.exists():
        return ""
    try:
        raw = p.read_text(errors="ignore")
    except Exception:
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
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / acc_to_fname(acc)
    if not p.exists():
        try:
            p.write_text(raw, errors="ignore")
        except Exception:
            pass
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))


def recent_10q_for(ticker: str, limit: int = 4, days: int = 540) -> list:
    """Pull recent 10-Q filings for a ticker via submissions JSON."""
    from recent import company_filings
    return company_filings(ticker, forms=("10-Q",), limit_per_form=limit,
                           days=days)


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
    args = ap.parse_args()

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
    if OUT_JSON.exists():
        try:
            out = json.loads(OUT_JSON.read_text())
        except Exception:
            out = {}

    rows = []
    for i, tk in enumerate(tickers, 1):
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
            }
            try:
                filings = recent_10q_for(tk, limit=args.quarters, days=args.days)
            except Exception as e:
                print(f"  {tk}: filings fetch fail: {e}", file=sys.stderr)
                filings = []
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
            sc, reasons, counts = score_events(cur["events"])
            cur["score"] = sc
            cur["reasons"] = reasons
            cur["counts"] = counts
            cur["_complete"] = True
            out[tk] = cur
            OUT_JSON.write_text(json.dumps(out, indent=2, default=str))

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
            "reasons": " | ".join(cur.get("reasons") or []),
        })

        if i % 5 == 0:
            print(f"  [{i}/{len(tickers)}] {tk} scanned ({n} cancellations)",
                  flush=True)

    rows.sort(key=lambda r: -r["score"])
    fields = ["rank", "ticker", "n_quarters_scanned", "n_events",
              "term_sell", "adopt_sell", "term_buy", "adopt_buy",
              "modify_pair", "score", "reasons"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nWrote {OUT_CSV} + {OUT_JSON}\n")
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
