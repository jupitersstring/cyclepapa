"""Deeper PSU forensics: depth-of-alignment factors that go beyond
binary detection.

For each top candidate, re-reads the cached DEF 14A from .cache/docs
and extracts the structural details that distinguish a deeply-aligned
PSU plan from boilerplate:

  - Vesting period (3y, 4y, 5y -- longer = better alignment)
  - Post-vest holding requirement (1y / 2y / 5y / until termination)
  - Single-trigger vs double-trigger CIC (double = cleaner)
  - Section 280G analysis presence (golden-parachute mechanics live)
  - PSU weight in LTI mix (% of grant value)
  - Number of distinct performance metrics
  - NEO unvested PSU dollar value at target / max (skin in game)
  - Founder / 10% holder presence
  - Comp philosophy statements (ROIIC / per-share / alignment)
  - Pay-vs-performance disclosure presence (PVP table)
  - Holding requirement extending past vesting
  - Mandatory stock ownership multiples (CEO 6x salary etc)
  - Clawback policy (DTRR-compliant?)
  - Anti-hedging / anti-pledging policies

Output: psu_forensics.csv with the depth-of-alignment score per name.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Pattern bank
# ---------------------------------------------------------------------------

VESTING_PERIOD = re.compile(
    r"(?:performance period|vesting period|measurement period|"
    r"performance (?:cycle|window))[^.\n]{0,80}?"
    r"(\d+)[- ]?(?:year|yr|yrs|annum|years)",
    re.I,
)
VEST_RATABLY = re.compile(
    r"vest(?:s|ing)?\s+(?:ratably|in (?:equal )?(?:annual )?installments)\s+over\s+(\d+)[- ]?(?:year|yr|yrs)",
    re.I,
)
THREE_TO_FIVE_YEAR = re.compile(
    r"\b(three|four|five)[- ]?year\s+(?:performance|vesting|measurement)",
    re.I,
)
NUMBER_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}

HOLDING_REQ = re.compile(
    r"(?:holding|hold(?:ing)?\s+requirement|post[- ]?vest(?:ing)?\s+hold(?:ing)?|"
    r"mandatory\s+hold(?:ing)?)[^.\n]{0,100}?(\d+)[- ]?(?:year|yr|yrs)",
    re.I,
)
HOLD_UNTIL_TERM = re.compile(
    r"(?:hold(?:ing)?\s+until|hold\s+(?:through|to)\s+(?:termination|retirement)|"
    r"until\s+(?:separation|retirement)\s+of\s+service)",
    re.I,
)

DOUBLE_TRIGGER = re.compile(
    r"\b(?:double[- ]trigger|two[- ]trigger|"
    r"qualifying\s+termination[^.\n]{0,40}?(?:change|in)\s+control|"
    r"requires\s+(?:both|two))\b",
    re.I,
)
SINGLE_TRIGGER = re.compile(
    r"\b(?:single[- ]trigger|one[- ]trigger|"
    r"automatic\s+accelerat\w+\s+upon\s+(?:change|in)\s+control)\b",
    re.I,
)
# Negation context for single-trigger (INCENTIVE_AUDIT.md R2): proxies
# overwhelmingly mention "single-trigger" in the NEGATIVE ("we do not
# provide single-trigger acceleration", the "what we don't do" table).
# The old bare search fired on 34% of PSU names -- penalizing companies
# for bragging about NOT having the feature. A mention only counts when
# no negation token appears in the preceding ~60 chars.
_SINGLE_TRIGGER_NEG = re.compile(
    r"\b(?:no|not|n't|never|without|none|eliminat\w*|remov\w*|"
    r"prohibit\w*|do(?:es)?\s+not|avoid\w*)\b",
    re.I,
)


def _single_trigger_present(text: str) -> bool:
    """True only if at least one single-trigger mention is NOT negated."""
    for m in SINGLE_TRIGGER.finditer(text):
        lookback = text[max(0, m.start() - 60):m.start()]
        if not _SINGLE_TRIGGER_NEG.search(lookback):
            return True
    return False
SECTION_280G = re.compile(r"\bSection\s*280G\b|\b280G\s+(?:cutback|gross[- ]up|analysis)", re.I)

# PSU weight in LTI mix: catches "PSUs (50%)" / "50% PSU" / "weighted 50%"
PSU_WEIGHT = re.compile(
    r"(?:performance\s+(?:share|stock)\s+units?|PSU[s]?)[^.\n]{0,60}?"
    r"\((\d{1,3})%\)|"
    r"(\d{1,3})%\s+(?:performance\s+(?:share|stock)|PSU)",
    re.I,
)

# Ownership multiples: "CEO must hold 6x base salary"
OWNERSHIP_MULTIPLE = re.compile(
    r"(?:CEO|Chief\s+Executive|executive\s+officers?)[^.\n]{0,80}?"
    r"(?:must\s+(?:hold|own|maintain)|ownership\s+(?:requirement|guideline|policy))"
    r"[^.\n]{0,80}?(\d+)\s*(?:x|times)\s*(?:base\s+)?salary",
    re.I,
)
CEO_OWNERSHIP_PCT = re.compile(
    r"(?:CEO|Chief\s+Executive)[^.\n]{0,60}?"
    r"(?:beneficially\s+owns?|owns\s+approximately|holds)"
    r"[^.\n]{0,40}?(\d{1,2}(?:\.\d+)?)\s*%\s*of",
    re.I,
)

# Clawback policy (DTRR Rule 10D-1 compliant since 2023)
CLAWBACK = re.compile(
    r"\b(?:clawback\s+policy|recovery\s+policy|recoupment\s+policy|"
    r"DTRR|Dodd[- ]?Frank.{0,30}?clawback|"
    r"Rule\s*10D[- ]?1|listing\s+standard\s+clawback)\b",
    re.I,
)
ANTI_HEDGING = re.compile(
    r"\banti[- ]hedg(?:ing)?\b|\bprohibit(?:s|ed)?\s+hedg(?:ing)?\b|"
    r"\bno\s+(?:hedging|short\s+selling)\b",
    re.I,
)
ANTI_PLEDGING = re.compile(
    r"\banti[- ]pledg(?:ing)?\b|\bprohibit(?:s|ed)?\s+pledg(?:ing)?\b|"
    r"\bno\s+(?:pledging|margin\s+account)\b",
    re.I,
)

PVP_TABLE = re.compile(
    r"\bpay[- ]versus[- ]performance\b|\bPay\s+v\.\s+Performance\b|"
    r"\bCompensation\s+actually\s+paid\b|\bCAP\s+vs\.?\s+TSR\b",
    re.I,
)

# Comp-philosophy alignment statements
COMP_PHILOSOPHY = re.compile(
    r"(?:long[- ]term\s+shareholder\s+value|align(?:ed|ment)?\s+with\s+(?:long[- ]term\s+)?"
    r"(?:shareholders?|stockholders?)|pay[- ]for[- ]performance\s+philosophy|"
    r"capital\s+(?:allocation\s+)?discipline|incremental\s+return)",
    re.I,
)

# NEO unvested PSU value at target ($X NEO value)
NEO_UNVESTED_VALUE = re.compile(
    r"(?:unvested|outstanding)\s+(?:performance|PSU|equity)\s+(?:award|grant)[^.\n]{0,80}?"
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:million|m|,000)?",
    re.I,
)

# Founder presence
FOUNDER_TITLE = re.compile(
    r"(?:founder\s+(?:and\s+)?(?:CEO|chief\s+executive|chairman)|"
    r"co[- ]founder)",
    re.I,
)


# ---------------------------------------------------------------------------
# Forensic extraction
# ---------------------------------------------------------------------------

def find_max_vest_period(text: str) -> Optional[int]:
    """Return the longest vesting period mentioned (years)."""
    years = []
    for m in VESTING_PERIOD.finditer(text):
        try:
            y = int(m.group(1))
            if 1 <= y <= 10:
                years.append(y)
        except ValueError:
            pass
    for m in VEST_RATABLY.finditer(text):
        try:
            y = int(m.group(1))
            if 1 <= y <= 10:
                years.append(y)
        except ValueError:
            pass
    for m in THREE_TO_FIVE_YEAR.finditer(text):
        w = m.group(1).lower()
        if w in NUMBER_WORDS:
            years.append(NUMBER_WORDS[w])
    return max(years) if years else None


def extract_forensics(text: str) -> dict:
    """Extract per-PSU plan structure forensics from proxy text."""
    out = {}
    out["vesting_period_yrs"] = find_max_vest_period(text)

    # Holding requirement
    hold_yrs = []
    for m in HOLDING_REQ.finditer(text):
        try:
            y = int(m.group(1))
            if 1 <= y <= 10:
                hold_yrs.append(y)
        except ValueError:
            pass
    if hold_yrs:
        out["post_vest_holding_yrs"] = max(hold_yrs)
    out["hold_until_termination"] = bool(HOLD_UNTIL_TERM.search(text))

    # Trigger type
    out["double_trigger"] = bool(DOUBLE_TRIGGER.search(text))
    out["single_trigger"] = _single_trigger_present(text)
    out["section_280g"] = bool(SECTION_280G.search(text))

    # PSU weighting
    psu_weights = []
    for m in PSU_WEIGHT.finditer(text):
        for grp in (1, 2):
            v = m.group(grp)
            if v:
                try:
                    pct = int(v)
                    if 10 <= pct <= 90:
                        psu_weights.append(pct)
                except ValueError:
                    pass
                break
    if psu_weights:
        out["psu_weight_pct"] = max(psu_weights)  # take max (PSU emphasis)

    # Ownership multiples
    ownership_x = []
    for m in OWNERSHIP_MULTIPLE.finditer(text):
        try:
            x = int(m.group(1))
            if 1 <= x <= 20:
                ownership_x.append(x)
        except ValueError:
            pass
    if ownership_x:
        out["ceo_ownership_multiple"] = max(ownership_x)

    # CEO direct ownership %
    ceo_owner_pcts = []
    for m in CEO_OWNERSHIP_PCT.finditer(text):
        try:
            pct = float(m.group(1))
            if 0.1 <= pct <= 95:
                ceo_owner_pcts.append(pct)
        except ValueError:
            pass
    if ceo_owner_pcts:
        out["ceo_direct_ownership_pct"] = max(ceo_owner_pcts)

    # Governance policies
    out["clawback_policy"] = bool(CLAWBACK.search(text))
    out["anti_hedging"] = bool(ANTI_HEDGING.search(text))
    out["anti_pledging"] = bool(ANTI_PLEDGING.search(text))
    out["pvp_disclosure"] = bool(PVP_TABLE.search(text))

    # Comp philosophy
    out["alignment_philosophy_hits"] = len(COMP_PHILOSOPHY.findall(text))

    # NEO unvested PSU dollar value
    neo_values = []
    for m in NEO_UNVESTED_VALUE.finditer(text):
        try:
            val_str = m.group(1).replace(",", "")
            val = float(val_str)
            if 100_000 <= val <= 1_000_000_000:
                neo_values.append(val)
        except ValueError:
            pass
    if neo_values:
        out["max_neo_unvested_psu_usd"] = max(neo_values)

    # Founder presence
    out["founder_cited"] = bool(FOUNDER_TITLE.search(text))

    return out


# ---------------------------------------------------------------------------
# Depth-of-alignment score
# ---------------------------------------------------------------------------

def alignment_score(f: dict) -> tuple[float, list[str]]:
    """0-100. Higher = deeper alignment with shareholders."""
    score = 0.0
    reasons = []

    # Vesting period (>=3y is industry standard; 4-5y is best)
    vp = f.get("vesting_period_yrs")
    if vp:
        if vp >= 5:
            score += 18; reasons.append(f"Long vest ({vp}y)")
        elif vp >= 4:
            score += 14; reasons.append(f"4-year vest")
        elif vp == 3:
            score += 10; reasons.append(f"3-year vest")
        else:
            score += 3

    # Post-vest holding requirement (extends alignment horizon)
    h = f.get("post_vest_holding_yrs")
    if f.get("hold_until_termination"):
        score += 12; reasons.append("Hold until termination/retirement")
    elif h and h >= 2:
        score += 8; reasons.append(f"{h}y post-vest hold")
    elif h:
        score += 4

    # Trigger type: double = aligned, single = misaligned
    if f.get("double_trigger") and not f.get("single_trigger"):
        score += 10; reasons.append("Pure double-trigger CIC")
    elif f.get("double_trigger") and f.get("single_trigger"):
        score += 6; reasons.append("Mixed trigger")
    elif f.get("single_trigger"):
        score -= 6; reasons.append("Single-trigger (gameable)")

    # 280G presence (mechanics live, mgmt knows the maths)
    if f.get("section_280g"):
        score += 4

    # PSU weight in LTI mix
    pw = f.get("psu_weight_pct")
    if pw:
        if pw >= 60:
            score += 14; reasons.append(f"PSU weight {pw}% (heavy)")
        elif pw >= 40:
            score += 10; reasons.append(f"PSU weight {pw}%")
        elif pw >= 20:
            score += 5

    # CEO ownership multiple
    om = f.get("ceo_ownership_multiple")
    if om:
        if om >= 6:
            score += 8; reasons.append(f"CEO own {om}x salary")
        elif om >= 4:
            score += 5
        elif om >= 2:
            score += 3

    # CEO direct ownership %
    ceo_pct = f.get("ceo_direct_ownership_pct")
    if ceo_pct:
        if ceo_pct >= 10:
            score += 14; reasons.append(f"CEO owns {ceo_pct:.1f}% directly")
        elif ceo_pct >= 5:
            score += 9; reasons.append(f"CEO owns {ceo_pct:.1f}%")
        elif ceo_pct >= 1:
            score += 4

    # Founder
    if f.get("founder_cited"):
        score += 6; reasons.append("Founder-led")

    # Governance hygiene
    if f.get("clawback_policy"):
        score += 3
    if f.get("anti_hedging"):
        score += 2
    if f.get("anti_pledging"):
        score += 2
    if f.get("pvp_disclosure"):
        score += 2

    # Alignment philosophy citations
    aph = f.get("alignment_philosophy_hits", 0)
    if aph >= 5:
        score += 4
    elif aph >= 2:
        score += 2

    # NEO unvested PSU $ skin in game
    neo_v = f.get("max_neo_unvested_psu_usd")
    if neo_v:
        if neo_v >= 50_000_000:
            score += 10; reasons.append(f"NEO unvested PSU $50M+")
        elif neo_v >= 10_000_000:
            score += 6; reasons.append(f"NEO unvested PSU $10M+")
        elif neo_v >= 2_000_000:
            score += 3

    return max(0.0, min(100.0, score)), reasons


# ---------------------------------------------------------------------------
# Main: run forensics on top candidates
# ---------------------------------------------------------------------------

def load_cached_doc(accession: str) -> Optional[str]:
    """Find cached HTML for an accession; return the plain-text version."""
    p = Path(f"/home/user/cyclepapa/.cache/docs/{accession}.html")
    if not p.exists():
        return None
    try:
        text = p.read_text(errors="ignore")
    except Exception:
        return None
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain)
    return plain


def fetch_from_url(url: str) -> Optional[str]:
    """Fetch a filing URL directly, return plain text."""
    if not url:
        return None
    try:
        from edgar import _get
        text = _get(url).text
    except Exception:
        return None
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = re.sub(r"\s+", " ", plain)
    return plain


def cache_doc(accession: str, html: str) -> None:
    """Persist raw HTML to local cache for subsequent re-runs."""
    if not accession or not html:
        return
    Path("/home/user/cyclepapa/.cache/docs").mkdir(parents=True, exist_ok=True)
    p = Path(f"/home/user/cyclepapa/.cache/docs/{accession}.html")
    if not p.exists():
        try:
            p.write_text(html, errors="ignore")
        except Exception:
            pass


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="unified_asymmetry.csv",
                   help="CSV of top candidates with 'ticker' + 'filing_url'")
    p.add_argument("--top", type=int, default=50,
                   help="Process top-N rows from source.")
    p.add_argument("--out", default="psu_forensics.csv")
    p.add_argument("--min-score", type=float, default=0.0)
    args = p.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"Source CSV not found: {src_path}", flush=True)
        return 1

    rows_src = list(csv.DictReader(open(src_path)))[: args.top]
    print(f"Running forensics on top {len(rows_src)} candidates from {src_path}")

    # Build accession -> ticker map from existing JSONs to resolve
    # filing_url -> accession
    detail_index = {}
    for fn in ("v2_detail.json", "wide180_detail.json", "wide365_detail.json",
               "induce_detail.json", "restruct_v10.json", "missing_v10.json",
               "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json"):
        p = Path(f"/home/user/cyclepapa/{fn}")
        if not p.exists(): continue
        try:
            for r in json.loads(p.read_text()):
                if r.get("error"): continue
                tk = r.get("ticker")
                url = r.get("filing_url") or ""
                if tk and url:
                    # Find accession from URL
                    m = re.search(r"/(\d{10})/(\d{18})/", url)
                    if not m:
                        m = re.search(r"/(\d{10})/(\d{10}-\d{2}-\d{6})/", url)
                    acc = None
                    parts = url.split("/")
                    for part in parts:
                        if re.match(r"^\d{18}$", part):
                            # Convert to dashed form: NNNNNNNNNN-NN-NNNNNN
                            acc = f"{part[:10]}-{part[10:12]}-{part[12:]}"
                            break
                        if re.match(r"^\d{10}-\d{2}-\d{6}$", part):
                            acc = part
                            break
                    if acc:
                        detail_index.setdefault(tk, []).append((acc, r))
        except Exception:
            pass

    rows_out = []
    for sr in rows_src:
        tk = (sr.get("ticker") or "").upper()
        if not tk:
            continue
        # Find most relevant cached doc
        candidates = detail_index.get(tk, [])
        text = None
        chosen_acc = None
        for acc, row in candidates:
            t = load_cached_doc(acc)
            if t and ("performance share" in t.lower() or "PSU" in t or "performance stock" in t.lower()):
                text = t
                chosen_acc = acc
                break
        if not text and candidates:
            text = load_cached_doc(candidates[0][0])
            chosen_acc = candidates[0][0] if text else None
        # Fallback: fetch directly from filing_url
        if not text:
            url = sr.get("filing_url")
            if not url and candidates:
                url = candidates[0][1].get("filing_url")
            if url:
                from edgar import _get
                try:
                    raw = _get(url).text
                    text = re.sub(r"<[^>]+>", " ", raw)
                    text = re.sub(r"\s+", " ", text)
                    # Cache it
                    m = re.search(r"/(\d{18})/", url)
                    if m:
                        acc_raw = m.group(1)
                        acc_dashed = f"{acc_raw[:10]}-{acc_raw[10:12]}-{acc_raw[12:]}"
                        cache_doc(acc_dashed, raw)
                        chosen_acc = acc_dashed
                except Exception:
                    pass
        if not text:
            print(f"  {tk}: no source available", flush=True)
            continue

        f = extract_forensics(text)
        align_score, reasons = alignment_score(f)
        if align_score < args.min_score:
            continue

        rows_out.append({
            "ticker": tk,
            "company": sr.get("company") or "",
            "alignment_score": round(align_score, 1),
            "source_master": sr.get("master") or sr.get("composite"),
            "vesting_period_yrs": f.get("vesting_period_yrs"),
            "post_vest_holding_yrs": f.get("post_vest_holding_yrs"),
            "hold_until_termination": f.get("hold_until_termination"),
            "double_trigger": f.get("double_trigger"),
            "single_trigger": f.get("single_trigger"),
            "section_280g": f.get("section_280g"),
            "psu_weight_pct": f.get("psu_weight_pct"),
            "ceo_ownership_multiple": f.get("ceo_ownership_multiple"),
            "ceo_direct_ownership_pct": f.get("ceo_direct_ownership_pct"),
            "founder_cited": f.get("founder_cited"),
            "clawback_policy": f.get("clawback_policy"),
            "anti_hedging": f.get("anti_hedging"),
            "anti_pledging": f.get("anti_pledging"),
            "pvp_disclosure": f.get("pvp_disclosure"),
            "alignment_philosophy_hits": f.get("alignment_philosophy_hits"),
            "max_neo_unvested_psu_usd": f.get("max_neo_unvested_psu_usd"),
            "reasons": " | ".join(reasons),
            "accession": chosen_acc,
        })

    rows_out.sort(key=lambda r: r["alignment_score"], reverse=True)

    fields = ["rank", "ticker", "company", "alignment_score", "source_master",
              "vesting_period_yrs", "post_vest_holding_yrs",
              "hold_until_termination", "double_trigger", "single_trigger",
              "section_280g", "psu_weight_pct", "ceo_ownership_multiple",
              "ceo_direct_ownership_pct", "founder_cited",
              "clawback_policy", "anti_hedging", "anti_pledging",
              "pvp_disclosure", "alignment_philosophy_hits",
              "max_neo_unvested_psu_usd", "reasons", "accession"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows_out, 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nWrote {args.out} ({len(rows_out)} candidates with forensics)\n")
    print(f"{'#':<3}{'TKR':<10}{'SCR':>4}{'VEST':>5}{'HOLD':>5}{'TRIG':>5}{'PSU%':>5}{'CEOX':>5}{'NEO$':>9}  REASONS")
    print("-" * 145)
    for i, r in enumerate(rows_out[:40], 1):
        vp = r.get("vesting_period_yrs") or "-"
        hd = r.get("post_vest_holding_yrs") or ("T" if r.get("hold_until_termination") else "-")
        if r.get("double_trigger") and not r.get("single_trigger"):
            tr = "2x"
        elif r.get("single_trigger"):
            tr = "1x"
        else:
            tr = "-"
        pw = r.get("psu_weight_pct") or "-"
        cm = r.get("ceo_ownership_multiple") or "-"
        nv = r.get("max_neo_unvested_psu_usd")
        nv_s = f"${nv/1e6:.0f}M" if nv else "-"
        print(f"{i:<3}{r['ticker']:<10}{r['alignment_score']:>4.0f}{str(vp):>5}"
              f"{str(hd):>5}{tr:>5}{str(pw):>5}{str(cm):>5}{nv_s:>9}  "
              f"{r['reasons'][:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
