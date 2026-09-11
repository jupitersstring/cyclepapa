"""Business-specific PSU conditionalities + insider buying overlay.

For each top fresh-PSU-adopter candidate (from psu_step_change.csv), pull
the underlying DEF 14A / 8-K text and extract NON-GENERIC, business-
specific vesting conditions. Most PSU plans are "TSR vs S&P" boilerplate;
the alpha lives in the rare cases where vesting is tied to:

  - Spin-off / separation completion
  - M&A close ("upon closing of the Acquisition")
  - Regulatory milestones (FDA PDUFA / Phase 3 / approval)
  - Debt-reduction targets ("net leverage <= 3.0x")
  - Asset sales ("sale of [segment]")
  - Refinancing / capital structure events
  - Specific dollar EBITDA / revenue / FCF thresholds (not just growth %)
  - Customer / subscriber / ARR / margin targets
  - Backlog / book-to-bill
  - Litigation settlement
  - Restructuring milestones
  - IPO of a subsidiary

These are EVENT-CONTINGENT triggers -- the insider has been told exactly
what they need to do to monetise. That's the highest-quality signal in
all of executive comp.

Output (PERMANENT cache):
  - psu_conditionalities.json  -- full per-ticker extracted detail
  - psu_conditionalities.csv   -- ranked summary
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

CACHE_DOCS = Path("/home/user/cyclepapa/.cache/docs")
OUT_JSON = Path("/home/user/cyclepapa/psu_conditionalities.json")
OUT_CSV = Path("/home/user/cyclepapa/psu_conditionalities.csv")


# ---------------------------------------------------------------------------
# Business-specific conditionality patterns
# ---------------------------------------------------------------------------

CONDITIONALITY_PATTERNS = {
    "spin_separation": [
        re.compile(r"\b(?:upon|subject\s+to|following|conditioned\s+on|"
                   r"contingent\s+(?:on|upon))\s+(?:the\s+)?"
                   r"(?:completion|consummation|effective(?:ness)?\s+of\s+the)\s+"
                   r"(?:Separation|Spin[- ]?Off|Distribution)", re.I),
        re.compile(r"\bvest(?:s|ing)?[^.\n]{0,80}?(?:Separation|Spin[- ]?Off|"
                   r"Distribution\s+Date)", re.I),
    ],
    "merger_close": [
        re.compile(r"\b(?:upon|subject\s+to|conditioned\s+on)\s+(?:the\s+)?"
                   r"(?:closing|consummation|completion)\s+of\s+the\s+"
                   r"(?:Merger|Acquisition|Transaction|Combination|Business\s+Combination)", re.I),
        re.compile(r"\bvest(?:s|ing)?[^.\n]{0,60}?(?:closing|Effective\s+Time)\s+of\s+the\s+"
                   r"(?:Merger|Acquisition|Transaction)", re.I),
    ],
    "regulatory_milestone": [
        re.compile(r"\b(?:upon|subject\s+to|conditioned\s+on)\s+(?:the\s+)?"
                   r"(?:FDA\s+approval|regulatory\s+approval|marketing\s+authorization|"
                   r"BLA\s+approval|NDA\s+approval|EMA\s+approval|"
                   r"CE\s+mark|510\(k\)\s+clearance|De\s+Novo\s+clearance)", re.I),
        re.compile(r"\b(?:PDUFA\s+date|Phase\s+(?:2b|3|III|IIb)\s+(?:read[- ]?out|"
                   r"data|results|completion|trial|study))[^.\n]{0,80}?"
                   r"(?:vest|earn|trigger|condition|milestone)", re.I),
        re.compile(r"\b(?:vest|earn|trigger)[^.\n]{0,80}?"
                   r"(?:FDA\s+approval|PDUFA|Phase\s+3|Phase\s+III|BLA|NDA)", re.I),
    ],
    "debt_reduction_target": [
        re.compile(r"\b(?:net\s+)?(?:debt|leverage)[^.\n]{0,40}?"
                   r"(?:below|less\s+than|<=?|reduced\s+to|reduce\s+to|"
                   r"reach(?:ing)?)[^.\n]{0,20}?"
                   r"(?:\$[\d,.]+\s*(?:million|billion|B|M)|\d+(?:\.\d+)?\s*x)", re.I),
        re.compile(r"\b(?:repay|pay\s+down|retire|extinguish)[^.\n]{0,50}?"
                   r"(?:\$[\d,.]+\s*(?:million|billion))[^.\n]{0,50}?"
                   r"(?:debt|notes|loan|facility)", re.I),
    ],
    "asset_sale": [
        re.compile(r"\b(?:upon|subject\s+to|following)\s+(?:the\s+)?"
                   r"(?:sale|divestiture|disposition)\s+of\s+(?:the\s+)?"
                   r"(?:[A-Z][a-zA-Z]+\s+(?:business|segment|division|operations|assets|"
                   r"portfolio|subsidiary))", re.I),
        re.compile(r"\bvest(?:s|ing)?[^.\n]{0,60}?"
                   r"(?:divestiture|asset\s+sale|sale\s+of\s+(?:the\s+)?"
                   r"(?:business|segment|operations))", re.I),
    ],
    "refinancing": [
        re.compile(r"\b(?:upon|subject\s+to)\s+(?:the\s+)?"
                   r"(?:refinanc(?:ing|e)|recapitalization|debt\s+exchange|"
                   r"out[- ]of[- ]court\s+restructuring|chapter\s+11\s+emergence|"
                   r"plan\s+of\s+reorganization)", re.I),
    ],
    "ebitda_target_dollar": [
        re.compile(r"\b(?:Adjusted\s+)?EBITDA\s+(?:of|reaching|reaches|equal\s+to\s+or\s+"
                   r"greater\s+than|>=?|at\s+least)\s+"
                   r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|B|M)", re.I),
    ],
    "revenue_target_dollar": [
        re.compile(r"\b(?:Adjusted\s+)?(?:net\s+)?revenue\s+(?:of|reaching|reaches|"
                   r"equal\s+to\s+or\s+greater\s+than|>=?|at\s+least)\s+"
                   r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|B|M)", re.I),
    ],
    "fcf_target_dollar": [
        re.compile(r"\b(?:free\s+cash\s+flow|FCF)\s+(?:of|reaching|reaches|"
                   r"equal\s+to\s+or\s+greater\s+than|>=?|at\s+least)\s+"
                   r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|B|M)", re.I),
    ],
    "subscriber_arr_target": [
        re.compile(r"\b(?:ARR|annual\s+recurring\s+revenue|subscribers?|active\s+users?|"
                   r"monthly\s+active\s+users?|MAUs?|DAUs?|customer\s+count)\s+"
                   r"(?:of|reaching|reaches|>=?|at\s+least)\s+"
                   r"(?:\$\s*)?([\d,]+(?:\.\d+)?)\s*(million|billion|thousand|M|K|B)?", re.I),
    ],
    "margin_target": [
        re.compile(r"\b(?:gross|operating|EBITDA|EBIT)\s+margin\s+"
                   r"(?:of|reaching|reaches|>=?|at\s+least)\s+"
                   r"([\d.]+)\s*%", re.I),
    ],
    "backlog_book_to_bill": [
        re.compile(r"\b(?:backlog|book[- ]to[- ]bill|order\s+book)[^.\n]{0,40}?"
                   r"(?:of|reaches|>=?|at\s+least)[^.\n]{0,30}?"
                   r"(?:\$[\d,.]+\s*(?:million|billion)|[\d.]+x)", re.I),
    ],
    "ipo_subsidiary": [
        re.compile(r"\b(?:upon|subject\s+to)\s+(?:the\s+)?"
                   r"(?:initial\s+public\s+offering|IPO|listing)\s+of\s+"
                   r"(?:a\s+|the\s+)?(?:subsidiary|affiliate)", re.I),
    ],
    "going_concern_emerge": [
        re.compile(r"\b(?:upon|subject\s+to)\s+(?:emergence\s+from\s+chapter\s+11|"
                   r"resolution\s+of\s+going\s+concern|removal\s+of\s+going\s+concern\s+qualification)",
                   re.I),
    ],
    "restructuring_milestone": [
        re.compile(r"\b(?:vest|earn|payable)[^.\n]{0,80}?"
                   r"(?:cost[- ]savings?\s+target|synergy\s+target|"
                   r"restructuring\s+target|operational\s+turnaround|"
                   r"transformation\s+milestone)", re.I),
    ],
    "share_count_reduction": [
        re.compile(r"\b(?:reduce|reduction\s+(?:in|of))\s+(?:diluted\s+)?"
                   r"shares?\s+outstanding[^.\n]{0,40}?"
                   r"(?:by\s+)?(?:at\s+least\s+)?([\d.]+)\s*(?:%|percent)", re.I),
    ],
    "litigation_resolution": [
        re.compile(r"\b(?:upon|subject\s+to)\s+(?:the\s+)?"
                   r"(?:resolution|settlement|dismissal)\s+of\s+"
                   r"(?:the\s+)?(?:litigation|lawsuit|action|investigation)", re.I),
    ],
    "stock_price_sustained": [
        re.compile(r"\b(?:\d{2,3}|sixty|ninety|one\s+hundred\s+twenty)\s*"
                   r"(?:consecutive\s+)?trading\s+days?\s+"
                   r"(?:closing|price|VWAP)[^.\n]{0,30}?"
                   r"(?:at\s+or\s+above|exceeds?|equal\s+to\s+or\s+greater\s+than)\s*"
                   r"\$\s*([\d.]+)", re.I),
    ],
    "control_breakdown": [
        re.compile(r"\b(?:upon|subject\s+to)\s+(?:a\s+)?"
                   r"(?:Change\s+of\s+Control|sale\s+of\s+the\s+Company|"
                   r"qualifying\s+liquidity\s+event)[^.\n]{0,80}?"
                   r"(?:price\s+per\s+share|consideration|implied\s+value)\s+"
                   r"(?:of|at\s+least|exceeding)\s+\$\s*([\d.]+)", re.I),
    ],
}


def detect_conditionalities(text: str, max_snippet_chars: int = 200) -> dict:
    """Returns {category: [snippet, ...]}."""
    out: dict[str, list[str]] = {}
    if not text:
        return out
    for category, patterns in CONDITIONALITY_PATTERNS.items():
        hits = []
        for p in patterns:
            for m in p.finditer(text):
                start = max(0, m.start() - 60)
                end = min(len(text), m.end() + 60)
                snip = text[start:end].strip()
                snip = re.sub(r"\s+", " ", snip)[:max_snippet_chars]
                if snip not in hits:
                    hits.append(snip)
                if len(hits) >= 3:
                    break
            if len(hits) >= 3:
                break
        if hits:
            out[category] = hits
    return out


CONDITIONALITY_WEIGHTS = {
    "spin_separation":         18,
    "merger_close":            16,
    "regulatory_milestone":    20,
    "debt_reduction_target":   14,
    "asset_sale":              14,
    "refinancing":             12,
    "ebitda_target_dollar":    10,
    "revenue_target_dollar":    8,
    "fcf_target_dollar":       12,
    "subscriber_arr_target":    8,
    "margin_target":            6,
    "backlog_book_to_bill":     6,
    "ipo_subsidiary":          14,
    "going_concern_emerge":    18,
    "restructuring_milestone": 10,
    "share_count_reduction":    8,
    "litigation_resolution":   10,
    "stock_price_sustained":    5,
    "control_breakdown":        8,
}


def conditionality_score(detected: dict) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    for cat, hits in detected.items():
        w = CONDITIONALITY_WEIGHTS.get(cat, 4)
        bonus = w if len(hits) == 1 else w * 1.4
        score += bonus
        reasons.append(f"{cat} (x{len(hits)})")
    return min(100.0, score), reasons


# ---------------------------------------------------------------------------
# Filing text loading
# ---------------------------------------------------------------------------

def acc_from_url(url: str) -> Optional[str]:
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


def load_cached_text(accession: str) -> Optional[str]:
    p = CACHE_DOCS / f"{accession}.html"
    if not p.exists():
        return None
    try:
        raw = p.read_text(errors="ignore")
    except Exception:
        return None
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain)
    return plain


def fetch_and_cache(url: str) -> tuple[Optional[str], Optional[str]]:
    if not url:
        return None, None
    try:
        from edgar import _get
        raw = _get(url).text
    except Exception as e:
        print(f"  fetch fail: {e}", file=sys.stderr)
        return None, None
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain)
    acc = acc_from_url(url)
    if acc:
        CACHE_DOCS.mkdir(parents=True, exist_ok=True)
        p = CACHE_DOCS / f"{acc}.html"
        try:
            p.write_text(raw, errors="ignore")
        except Exception:
            pass
    return plain, acc


# ---------------------------------------------------------------------------
# Insider buying overlay
# ---------------------------------------------------------------------------

def days_ago(date_str: str | None) -> Optional[int]:
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - d).days)
    except Exception:
        return None


def load_form4() -> dict:
    p = Path("/home/user/cyclepapa/form4_buys.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def insider_signal(tk: str, f4: dict) -> dict:
    rec = f4.get(tk) or {}
    filings = rec.get("filings") or []
    n = len(filings)
    total = rec.get("total_dollar") or sum((x.get("dollar") or 0) for x in filings)
    buyers = rec.get("buyer_set") or []
    n_buyers = len({b.split("|")[0].strip() for b in buyers}) if buyers else 0
    # Recency tiers
    by_age = [days_ago(x.get("date")) for x in filings]
    n_30 = sum(1 for d in by_age if d is not None and d <= 30)
    n_90 = sum(1 for d in by_age if d is not None and d <= 90)
    n_180 = sum(1 for d in by_age if d is not None and d <= 180)
    return {
        "n_filings": n,
        "total_dollar": total,
        "n_unique_buyers": n_buyers,
        "n_buys_30d": n_30,
        "n_buys_90d": n_90,
        "n_buys_180d": n_180,
        "buyers": buyers[:10],
    }


def insider_score(sig: dict, mcap: float | None) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []
    n_30 = sig.get("n_buys_30d", 0)
    n_90 = sig.get("n_buys_90d", 0)
    n_180 = sig.get("n_buys_180d", 0)
    total = sig.get("total_dollar", 0) or 0
    n_buyers = sig.get("n_unique_buyers", 0)
    if n_30 >= 5:
        score += 25; reasons.append(f"{n_30} P-buys in 30d (cluster)")
    elif n_30 >= 3:
        score += 15; reasons.append(f"{n_30} P-buys in 30d")
    elif n_30 >= 1:
        score += 6; reasons.append(f"{n_30} P-buy(s) in 30d")
    if n_90 >= 8 and n_30 < 5:
        score += 12; reasons.append(f"{n_90} P-buys in 90d (sustained)")
    if n_buyers >= 4:
        score += 15; reasons.append(f"{n_buyers} distinct buyers (cluster)")
    elif n_buyers >= 2:
        score += 6
    if mcap and mcap > 0:
        pct = total / mcap * 100
        if pct >= 1.0:
            score += 20; reasons.append(f"${total/1e6:.1f}M buys = {pct:.2f}% mcap")
        elif pct >= 0.3:
            score += 10; reasons.append(f"${total/1e6:.1f}M buys = {pct:.2f}% mcap")
        elif pct >= 0.05:
            score += 4
    elif total >= 5_000_000:
        score += 10
    elif total >= 1_000_000:
        score += 4
    return min(60.0, score), reasons


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def load_step_change(path: str = "psu_step_change.csv") -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return list(csv.DictReader(open(p)))


def build_detail_index() -> dict[str, list[dict]]:
    """Ticker -> [{acc, url, date, source}, ...] across all detail JSONs."""
    sources = [
        "v2_detail.json", "wide180_detail.json", "wide365_detail.json",
        "induce_detail.json", "restruct_v10.json", "missing_v10.json",
        "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json",
        "spinoffs_detail.json",
    ]
    idx: dict[str, list[dict]] = {}
    for fn in sources:
        p = Path(f"/home/user/cyclepapa/{fn}")
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        for r in data:
            if r.get("error"):
                continue
            tk = (r.get("ticker") or "").upper()
            url = r.get("filing_url")
            if not tk or not url:
                continue
            acc = acc_from_url(url)
            idx.setdefault(tk, []).append({
                "acc": acc, "url": url,
                "date": r.get("filing_date"),
                "source": fn,
                "has_psu_program": r.get("has_psu_program"),
            })
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="psu_step_change.csv")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--sleep", type=float, default=0.20)
    ap.add_argument("--csv", default=str(OUT_CSV))
    ap.add_argument("--json", default=str(OUT_JSON))
    ap.add_argument("--no-fetch", action="store_true",
                    help="Only use already-cached docs.")
    args = ap.parse_args()

    src = load_step_change(args.source)
    if not src:
        print(f"Source not found: {args.source}", file=sys.stderr)
        return 1
    src = src[: args.top]
    print(f"Loaded {len(src)} candidates from {args.source}", flush=True)

    detail_idx = build_detail_index()
    f4 = load_form4()

    # Resume from existing JSON if present (permanent cache)
    out_json: dict = {}
    if Path(args.json).exists():
        try:
            out_json = json.loads(Path(args.json).read_text())
        except Exception:
            out_json = {}

    rows_out = []
    for i, sr in enumerate(src, 1):
        tk = (sr.get("ticker") or "").upper()
        if not tk:
            continue
        mcap = float(sr.get("market_cap_musd") or 0) * 1e6
        px = float(sr.get("current_price") or 0)
        company = sr.get("company") or ""

        # Skip text-fetch if already cached in out_json
        already = out_json.get(tk)
        if already and already.get("conditionalities") is not None:
            cond = already["conditionalities"]
            acc_used = already.get("accession")
        else:
            # Find filings for this ticker
            candidates = detail_idx.get(tk, [])
            candidates.sort(key=lambda c: c.get("date") or "", reverse=True)
            text = None
            acc_used = None
            for c in candidates[:3]:
                if not c.get("acc"):
                    continue
                t = load_cached_text(c["acc"])
                if t:
                    text = t
                    acc_used = c["acc"]
                    break
            # Fallback: fetch the most recent (step_change filing_url)
            if not text and not args.no_fetch:
                url = sr.get("filing_url") or (candidates[0]["url"] if candidates else None)
                if url:
                    text, acc_used = fetch_and_cache(url)
                    time.sleep(args.sleep)
            if not text:
                print(f"  [{i}/{len(src)}] {tk}: NO TEXT", file=sys.stderr, flush=True)
                cond = {}
            else:
                cond = detect_conditionalities(text)

        cond_score, cond_reasons = conditionality_score(cond)
        sig = insider_signal(tk, f4)
        ins_score, ins_reasons = insider_score(sig, mcap)

        # Step-change score from psu_step_change.csv
        try:
            base_step = float(sr.get("step_score") or 0)
        except ValueError:
            base_step = 0.0

        # Combined: 50% base step + 25% conditionality + 25% insider
        combined = 0.50 * base_step + 0.25 * cond_score + 0.25 * ins_score

        out_json[tk] = {
            "ticker": tk,
            "company": company,
            "market_cap": mcap,
            "current_price": px,
            "filing_date": sr.get("filing_date"),
            "filing_url": sr.get("filing_url"),
            "accession": acc_used,
            "step_score": base_step,
            "conditionalities": cond,
            "conditionality_score": cond_score,
            "insider_signal": sig,
            "insider_score": ins_score,
            "combined_score": combined,
            "reasons": cond_reasons + ins_reasons,
            "_last_run": datetime.now(timezone.utc).isoformat(),
        }

        rows_out.append({
            "ticker": tk,
            "company": company[:50],
            "current_price": px,
            "market_cap_musd": round(mcap / 1e6, 1),
            "filing_date": sr.get("filing_date"),
            "step_score": round(base_step, 1),
            "conditionality_score": round(cond_score, 1),
            "insider_score": round(ins_score, 1),
            "combined_score": round(combined, 1),
            "conditionalities": ";".join(cond.keys()),
            "insider_buys_30d": sig.get("n_buys_30d"),
            "insider_buys_90d": sig.get("n_buys_90d"),
            "insider_unique_buyers": sig.get("n_unique_buyers"),
            "insider_total_musd": round((sig.get("total_dollar") or 0) / 1e6, 2),
            "accession": acc_used,
            "filing_url": sr.get("filing_url"),
            "cond_reasons": " | ".join(cond_reasons),
            "ins_reasons": " | ".join(ins_reasons),
        })

        # Persist after every fetch (permanent)
        Path(args.json).write_text(json.dumps(out_json, indent=2, default=str))

        if i % 5 == 0:
            print(f"  [{i}/{len(src)}] processed (cond_cats={len(cond)}, "
                  f"ins_buys30={sig.get('n_buys_30d')})", flush=True)

    rows_out.sort(key=lambda r: r["combined_score"], reverse=True)

    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "filing_date", "step_score", "conditionality_score",
              "insider_score", "combined_score",
              "conditionalities",
              "insider_buys_30d", "insider_buys_90d",
              "insider_unique_buyers", "insider_total_musd",
              "accession", "filing_url",
              "cond_reasons", "ins_reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows_out, 1):
            r["rank"] = i
            w.writerow(r)

    Path(args.json).write_text(json.dumps(out_json, indent=2, default=str))

    print(f"\nWrote {args.csv} + {args.json} (permanent cache)\n")
    print(f"=== TOP {min(50, len(rows_out))} -- PSU + CONDITIONALITY + INSIDER ===")
    print(f"{'#':<3}{'TKR':<10}{'MCAP':>9}{'PX':>9}"
          f"{'STP':>5}{'COND':>5}{'INS':>5}{'CMB':>5}  CONDITIONS / INSIDER")
    print("-" * 170)
    for i, r in enumerate(rows_out[:50], 1):
        cond_short = r["conditionalities"][:55] or "-"
        ins_short = (r["ins_reasons"] or "")[:55]
        print(f"{i:<3}{r['ticker']:<10}{r['market_cap_musd']:>8.0f}M"
              f"{r['current_price']:>9.2f}{r['step_score']:>5.0f}"
              f"{r['conditionality_score']:>5.0f}{r['insider_score']:>5.0f}"
              f"{r['combined_score']:>5.0f}  {cond_short:<55}  {ins_short}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
