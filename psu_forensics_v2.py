"""Deeper PSU forensics v2.

Beyond the v1 binary structural detectors, this module extracts:
  - Per-NEO breakdown: named officer, title, unvested $ value, grant date
  - PSU mix percentages: PSU vs RSU vs option vs cash
  - Per-hurdle context: ladder $ + metric type + performance period
  - Say-on-pay history: most-recent vote % support
  - Compensation consultant + peer group
  - Pay-versus-performance disclosure quality
  - Plan-year evolution: same proxy vs prior year (when available)
  - Insider net direction (P-buys minus S-sells, per company)

Output: psu_forensics_v2.csv with the deeper breakdown.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Extended pattern bank
# ---------------------------------------------------------------------------

NEO_NAME_TITLE = re.compile(
    r"(?:^|\s|>)([A-Z][A-Za-z\.\-\']+\s+(?:[A-Z]\.?\s+)?[A-Z][A-Za-z\.\-\']+)\s*,?\s+"
    r"(?:our\s+|the\s+|former\s+)?"
    r"(?:Chief\s+Executive\s+Officer|CEO|Chief\s+Financial\s+Officer|CFO|"
    r"Chief\s+Operating\s+Officer|COO|President|Chair(?:man)?(?:\s+of\s+the\s+Board)?|"
    r"Chief\s+Accounting\s+Officer|CAO|Chief\s+Technology\s+Officer|CTO|"
    r"Chief\s+Commercial\s+Officer|CCO|"
    r"General\s+Counsel|"
    r"Senior\s+Vice\s+President|Executive\s+Vice\s+President|"
    r"founder)",
    re.I,
)

# \d{1,3}: the old \d{1,2} could never capture a 100% approval
# (INCENTIVE_AUDIT.md R5); values are range-checked to <=100 downstream.
# S2 (INCENTIVE_AUDIT.md): widened to lift coverage from ~39%. The
# trailing result group now also matches support / in favour (British) /
# endorsed / of the shares|votes voted, and the reverse pattern accepts
# 'support of X%' / 'X% support ... say-on-pay'.
SAYS_ON_PAY = re.compile(
    r"(?:say[- ]on[- ]pay|advisory\s+vote\s+on\s+(?:executive\s+)?compensation)"
    r"[^.\n]{0,200}?(\d{1,3}(?:\.\d+)?)\s*%\s+(?:approval|approved|in\s+favou?r|"
    r"support(?:ed|ing)?|endorsed|voted\s+(?:in\s+)?favou?r|"
    r"of\s+(?:the\s+)?(?:votes|shares)\s+(?:cast|voted))",
    re.I,
)
SAYS_ON_PAY_PCT = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%[^.\n]{0,90}?say[- ]on[- ]pay|"
    r"say[- ]on[- ]pay[^.\n]{0,120}?(?:support(?:ed)?\s+(?:by|of)|"
    r"received[^.\n]{0,20}?support\s+of)\s+(?:approximately\s+)?"
    r"(\d{1,3}(?:\.\d+)?)\s*%",
    re.I,
)
_NEAR_YEAR = re.compile(r"\b(20[12]\d)\b")

COMP_CONSULTANT = re.compile(
    r"\b(FW\s+Cook|F\.\s*W\.\s+Cook|Frederic\s+W\.?\s+Cook|"
    r"Pearl\s+Meyer|Pay\s+Governance|"
    r"Compensia|Semler\s+Brossy|Mercer|Aon\s+Hewitt|Willis\s+Towers\s+Watson|"
    r"ClearBridge\s+Compensation|Exequity|Meridian\s+Compensation|"
    r"Deloitte\s+Compensation|Korn\s+Ferry\s+Hay\s+Group|McLagan|"
    r"Lyons\s+Benenson|Veritas\s+Executive\s+Compensation)\b",
    re.I,
)

PEER_GROUP_HEADER = re.compile(
    r"(?:peer\s+group|compensation\s+peer\s+group|comparator\s+group|"
    r"benchmark(?:ing)?\s+peer\s+group)",
    re.I,
)

# PSU mix percentages
LTI_PSU_PCT = re.compile(
    r"(?:PSU|performance\s+(?:share|stock)\s+units?|performance[- ]based)[^.\n]{0,40}?"
    r"(\d{1,3})\s*%(?:\s+of\s+(?:the\s+)?(?:LTI|long[- ]term|target))?",
    re.I,
)
LTI_RSU_PCT = re.compile(
    r"(?:RSU|restricted\s+stock\s+units?|time[- ]based)[^.\n]{0,40}?"
    r"(\d{1,3})\s*%(?:\s+of\s+(?:the\s+)?(?:LTI|long[- ]term|target))?",
    re.I,
)
LTI_OPTION_PCT = re.compile(
    r"(?:stock\s+options?|option\s+grants?)[^.\n]{0,40}?"
    r"(\d{1,3})\s*%(?:\s+of\s+(?:the\s+)?(?:LTI|long[- ]term|target))?",
    re.I,
)

# Specific metric attribution
METRIC_TSR = re.compile(
    r"(?:relative\s+|absolute\s+)?total\s+shareholder\s+return|TSR[- ]based",
    re.I,
)
METRIC_EPS = re.compile(
    r"earnings\s+per\s+share|diluted\s+EPS|EPS[- ]based|adjusted\s+EPS",
    re.I,
)
METRIC_ROIC = re.compile(
    r"return\s+on\s+invested\s+capital|ROIC[- ]based",
    re.I,
)
METRIC_FCF_PER_SHARE = re.compile(
    r"(?:free\s+cash\s+flow|FCF)\s+per\s+share|FCF/share",
    re.I,
)
METRIC_REVENUE = re.compile(
    r"(?:adjusted\s+)?revenue\s+growth|revenue\s+target",
    re.I,
)
METRIC_EBITDA = re.compile(
    r"(?:adjusted\s+)?EBITDA(?!\s+per\s+share)|EBITDA[- ]based",
    re.I,
)

# Grant date detection (recent inducement grants)
GRANT_DATE = re.compile(
    r"(?:granted|awarded|issued)\s+(?:on\s+)?"
    r"(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)

# CEO and other NEO unvested PSU dollar values from "Outstanding Equity
# Awards" table
NEO_AWARD_VALUE = re.compile(
    r"([A-Z][A-Za-z\.\-\']+\s+(?:[A-Z]\.?\s+)?[A-Z][A-Za-z\.\-\']+)[^.\n]{0,200}?"
    r"unvested[^.\n]{0,80}?"
    r"\$\s*([\d,]+(?:\.\d+)?)",
    re.I,
)

# Equity grant compensation (NEO summary comp table)
NEO_TOTAL_COMP = re.compile(
    r"Total\s+Compensation[^.\n]{0,100}?\$\s*([\d,]+(?:\.\d+)?)",
    re.I,
)

# Performance period years explicit
PERFORMANCE_PERIOD = re.compile(
    r"(?:performance\s+period|measurement\s+period)\s+(?:of\s+)?"
    r"(?:approximately\s+)?(\d+)[- ]?(?:to\s+(\d+)[- ]?)?(?:year|yr)",
    re.I,
)

# Realized vs target payout
PAYOUT_PCT = re.compile(
    r"(?:earned\s+(?:at|approximately)?\s*|paid\s+out\s+at\s+|"
    r"resulted\s+in\s+a\s+payout\s+of\s+|achievement\s+of\s+)"
    r"(\d{1,3})\s*%(?:\s+of\s+target)?",
    re.I,
)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_neos(text: str, max_neos: int = 8) -> list[dict]:
    """Find NEO names and titles."""
    seen = set()
    neos = []
    for m in NEO_NAME_TITLE.finditer(text):
        name = m.group(1).strip()
        # Filter: must be a person name (two cap words)
        if name.count(" ") < 1:
            continue
        # Skip if obviously not a name
        if any(w.lower() in name.lower() for w in
               ("company", "board", "committee", "the", "our", "compensation")):
            continue
        if name in seen:
            continue
        seen.add(name)
        # Get the title from the full match
        full = m.group(0)
        title_m = re.search(
            r"(Chief\s+Executive\s+Officer|CEO|Chief\s+Financial\s+Officer|CFO|"
            r"Chief\s+Operating\s+Officer|COO|President|Chair(?:man)?|"
            r"Chief\s+Accounting\s+Officer|CAO|Chief\s+Technology\s+Officer|CTO|"
            r"Chief\s+Commercial\s+Officer|CCO|"
            r"General\s+Counsel|Senior\s+Vice\s+President|"
            r"Executive\s+Vice\s+President|founder)",
            full, re.I)
        title = title_m.group(0) if title_m else ""
        neos.append({"name": name, "title": title})
        if len(neos) >= max_neos:
            break
    return neos


def extract_say_on_pay(text: str) -> Optional[float]:
    """Most-recent say-on-pay approval %.

    The old max() across all mentions masked dissent: "received 78%
    this year, versus 92% in the prior year" reported 92
    (INCENTIVE_AUDIT.md R5). Now each candidate is tagged with any year
    within +/-80 chars; when years are present the value tied to the
    LATEST year wins, otherwise the MINIMUM is returned -- conservative
    in exactly the direction the dissent signals need."""
    cands: list[tuple[float, Optional[int]]] = []
    for rx in (SAYS_ON_PAY, SAYS_ON_PAY_PCT):
        for m in rx.finditer(text):
            # a pattern may have several capture groups (alternatives);
            # take the first that matched a number
            grp = next((i for i in range(1, (m.re.groups or 0) + 1)
                        if m.group(i)), None)
            if grp is None:
                continue
            try:
                pct = float(m.group(grp))
            except ValueError:
                continue
            if not (30 <= pct <= 100):
                continue
            ctx = text[max(0, m.start(grp) - 80):m.end(grp) + 80]
            years = [int(y) for y in _NEAR_YEAR.findall(ctx)]
            cands.append((pct, max(years) if years else None))
    if not cands:
        return None
    dated = [(pct, y) for pct, y in cands if y is not None]
    if dated:
        latest = max(y for _, y in dated)
        return min(pct for pct, y in dated if y == latest)
    return min(pct for pct, _ in cands)


def extract_lti_mix(text: str) -> dict:
    """PSU / RSU / option weights in LTI mix."""
    out = {}
    psu_pcts = []
    for m in LTI_PSU_PCT.finditer(text):
        try:
            v = int(m.group(1))
            if 10 <= v <= 90:
                psu_pcts.append(v)
        except ValueError:
            pass
    if psu_pcts:
        out["psu_pct"] = max(psu_pcts)

    rsu_pcts = []
    for m in LTI_RSU_PCT.finditer(text):
        try:
            v = int(m.group(1))
            if 10 <= v <= 80:
                rsu_pcts.append(v)
        except ValueError:
            pass
    if rsu_pcts:
        out["rsu_pct"] = max(rsu_pcts)

    opt_pcts = []
    for m in LTI_OPTION_PCT.finditer(text):
        try:
            v = int(m.group(1))
            if 5 <= v <= 60:
                opt_pcts.append(v)
        except ValueError:
            pass
    if opt_pcts:
        out["option_pct"] = max(opt_pcts)

    return out


def extract_metrics(text: str) -> list[str]:
    found = []
    if METRIC_TSR.search(text): found.append("TSR")
    if METRIC_EPS.search(text): found.append("EPS")
    if METRIC_ROIC.search(text): found.append("ROIC")
    if METRIC_FCF_PER_SHARE.search(text): found.append("FCF/share")
    if METRIC_REVENUE.search(text): found.append("Revenue")
    if METRIC_EBITDA.search(text): found.append("EBITDA")
    return found


def extract_grant_dates(text: str, max_dates: int = 5) -> list[str]:
    out = []
    for m in GRANT_DATE.finditer(text):
        date = f"{m.group(1)} {m.group(2)}, {m.group(3)}"
        if date not in out:
            out.append(date)
        if len(out) >= max_dates:
            break
    return out


def extract_neo_award_values(text: str, max_n: int = 10) -> list[dict]:
    """Per-NEO unvested award dollar values."""
    out = []
    seen = set()
    for m in NEO_AWARD_VALUE.finditer(text):
        name = m.group(1).strip()
        if any(w.lower() in name.lower() for w in
               ("company", "board", "compensation", "the", "our")):
            continue
        try:
            val = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        if not (10_000 <= val <= 500_000_000):
            continue
        key = (name, val)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "unvested_usd": val})
        if len(out) >= max_n:
            break
    return out


def extract_performance_periods(text: str) -> list[int]:
    out = []
    for m in PERFORMANCE_PERIOD.finditer(text):
        try:
            y = int(m.group(1))
            if 1 <= y <= 10:
                out.append(y)
        except ValueError:
            pass
        if m.group(2):
            try:
                y2 = int(m.group(2))
                if 1 <= y2 <= 10:
                    out.append(y2)
            except ValueError:
                pass
    return sorted(set(out))


def extract_payout_history(text: str, max_n: int = 10) -> list[int]:
    """Historical PSU payout percentages of target."""
    out = []
    for m in PAYOUT_PCT.finditer(text):
        try:
            pct = int(m.group(1))
            if 0 <= pct <= 200:
                out.append(pct)
        except ValueError:
            pass
        if len(out) >= max_n:
            break
    return out


def extract_compensation_consultant(text: str) -> Optional[str]:
    m = COMP_CONSULTANT.search(text)
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Plan-year evolution (one filing vs prior)
# ---------------------------------------------------------------------------

def detect_recent_changes(text: str) -> dict:
    """Look for change-from-prior-year language."""
    out = {}
    if re.search(r"\b(?:beginning|effective|starting)\s+(?:in\s+)?(?:fiscal\s+)?"
                 r"\d{4}[^.\n]{0,80}?(?:we\s+(?:will|now)\s+|change[ds]?\s+to\s+)",
                 text, re.I):
        out["plan_change_announced"] = True
    if re.search(r"in\s+response\s+to\s+(?:shareholder|stockholder)\s+feedback",
                 text, re.I):
        out["shareholder_feedback_response"] = True
    if re.search(r"(?:added|introduced|incorporated)\s+(?:ROIC|TSR|EPS|"
                 r"per[- ]share)\s+(?:metric|component)",
                 text, re.I):
        out["new_metric_added"] = True
    if re.search(r"(?:eliminated|removed|discontinued)\s+(?:ROIC|TSR|EPS|"
                 r"the\s+\w+)\s+metric",
                 text, re.I):
        out["metric_removed"] = True
    if re.search(r"(?:extended|increased)\s+(?:the\s+)?(?:vesting|performance)"
                 r"\s+period",
                 text, re.I):
        out["vest_period_extended"] = True
    if re.search(r"reduce[ds]?\s+(?:the\s+)?single[- ]trigger",
                 text, re.I):
        out["single_trigger_reduced"] = True
    if re.search(r"(?:new|enhanced)\s+(?:stock\s+)?ownership\s+(?:requirements?|"
                 r"guidelines?)",
                 text, re.I):
        out["ownership_requirements_added"] = True
    return out


# ---------------------------------------------------------------------------
# Combined forensic record
# ---------------------------------------------------------------------------

def full_forensics(text: str) -> dict:
    return {
        "neos": extract_neos(text),
        "say_on_pay_pct": extract_say_on_pay(text),
        "lti_mix": extract_lti_mix(text),
        "performance_metrics": extract_metrics(text),
        "performance_periods_yrs": extract_performance_periods(text),
        "comp_consultant": extract_compensation_consultant(text),
        "grant_dates": extract_grant_dates(text),
        "neo_award_values": extract_neo_award_values(text),
        "payout_history_pcts": extract_payout_history(text),
        "plan_changes": detect_recent_changes(text),
    }


def alignment_depth_score(f: dict) -> tuple[float, list[str]]:
    """0-100. Combines structural with NEO-specific dimensions."""
    score = 0.0
    reasons = []

    # NEO unvested skin in game
    max_neo_unvested = 0
    if f.get("neo_award_values"):
        max_neo_unvested = max((nv["unvested_usd"] for nv in f["neo_award_values"]), default=0)
    if max_neo_unvested >= 50_000_000:
        score += 18; reasons.append(f"NEO unvested $50M+ (${max_neo_unvested/1e6:.0f}M)")
    elif max_neo_unvested >= 20_000_000:
        score += 12; reasons.append(f"NEO unvested $20M+ (${max_neo_unvested/1e6:.0f}M)")
    elif max_neo_unvested >= 5_000_000:
        score += 6

    # PSU weight in LTI mix
    psu_pct = f.get("lti_mix", {}).get("psu_pct")
    if psu_pct:
        if psu_pct >= 60:
            score += 16; reasons.append(f"PSU {psu_pct}% of LTI (heavy)")
        elif psu_pct >= 40:
            score += 11; reasons.append(f"PSU {psu_pct}% of LTI")
        elif psu_pct >= 25:
            score += 6

    # Metric depth & quality
    metrics = f.get("performance_metrics") or []
    per_share_count = sum(1 for m in metrics if m in ("TSR", "EPS", "ROIC", "FCF/share"))
    aggregate_count = sum(1 for m in metrics if m in ("EBITDA", "Revenue"))
    if per_share_count >= 3:
        score += 12; reasons.append(f"{per_share_count} per-share metrics")
    elif per_share_count >= 2:
        score += 8
    elif per_share_count >= 1:
        score += 4
    if aggregate_count >= 2:
        score -= 6; reasons.append(f"{aggregate_count} aggregate metrics")
    elif aggregate_count >= 1:
        score -= 3

    # Performance period
    pp = f.get("performance_periods_yrs") or []
    if pp:
        max_pp = max(pp)
        if max_pp >= 4:
            score += 10; reasons.append(f"{max_pp}-year performance window")
        elif max_pp == 3:
            score += 6

    # Say-on-pay support
    sop = f.get("say_on_pay_pct")
    if sop:
        if sop >= 95:
            score += 8; reasons.append(f"SOP {sop:.0f}% (clean)")
        elif sop >= 90:
            score += 5
        elif sop < 70:
            score -= 8; reasons.append(f"SOP only {sop:.0f}% (shareholder concern)")

    # Plan evolution -- positive direction
    pc = f.get("plan_changes") or {}
    if pc.get("vest_period_extended"):
        score += 6; reasons.append("Vesting period extended")
    if pc.get("ownership_requirements_added"):
        score += 5; reasons.append("New ownership requirements")
    if pc.get("shareholder_feedback_response"):
        score += 4; reasons.append("Responded to shareholder feedback")
    if pc.get("new_metric_added"):
        score += 5; reasons.append("New per-share metric added")
    if pc.get("single_trigger_reduced"):
        score += 6; reasons.append("Reduced single-trigger")

    # Payout discipline (historic CAP-vs-target)
    payouts = f.get("payout_history_pcts") or []
    if payouts:
        avg = sum(payouts) / len(payouts)
        # Below 80% = strict; over 150% = lax
        if 80 <= avg <= 130:
            score += 4
        elif avg > 170:
            score -= 4; reasons.append(f"Avg payout {avg:.0f}% (lax)")

    # Comp consultant present
    if f.get("comp_consultant"):
        score += 2

    return max(0.0, min(100.0, score)), reasons


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def load_cached_doc(accession: str) -> Optional[str]:
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


def fetch_and_cache(url: str) -> tuple[Optional[str], Optional[str]]:
    if not url:
        return None, None
    try:
        from edgar import _get
        raw = _get(url).text
    except Exception:
        return None, None
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain)
    m = re.search(r"/(\d{18})/", url)
    if m:
        acc_raw = m.group(1)
        acc = f"{acc_raw[:10]}-{acc_raw[10:12]}-{acc_raw[12:]}"
        Path("/home/user/cyclepapa/.cache/docs").mkdir(parents=True, exist_ok=True)
        p = Path(f"/home/user/cyclepapa/.cache/docs/{acc}.html")
        if not p.exists():
            try:
                p.write_text(raw, errors="ignore")
            except Exception:
                pass
        return plain, acc
    return plain, None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="unified_asymmetry.csv")
    p.add_argument("--top", type=int, default=100)
    p.add_argument("--out", default="psu_forensics_v2.csv")
    p.add_argument("--out-json", default="psu_forensics_v2.json")
    args = p.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"Source not found: {src_path}")
        return 1

    rows_src = list(csv.DictReader(open(src_path)))[: args.top]
    print(f"Forensics v2 on top {len(rows_src)} candidates")

    # Build ticker -> filing URL map from cached detail JSONs
    detail_index: dict[str, list] = {}
    for fn in ("v2_detail.json", "wide180_detail.json", "wide365_detail.json",
               "induce_detail.json", "restruct_v10.json", "missing_v10.json",
               "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json"):
        p = Path(f"/home/user/cyclepapa/{fn}")
        if not p.exists(): continue
        try:
            for r in json.loads(p.read_text()):
                if r.get("error"): continue
                tk = r.get("ticker")
                url = r.get("filing_url")
                if tk and url:
                    parts = url.split("/")
                    acc = None
                    for part in parts:
                        if re.match(r"^\d{18}$", part):
                            acc = f"{part[:10]}-{part[10:12]}-{part[12:]}"
                            break
                        if re.match(r"^\d{10}-\d{2}-\d{6}$", part):
                            acc = part
                            break
                    if acc:
                        detail_index.setdefault(tk, []).append({
                            "acc": acc, "url": url, "date": r.get("filing_date")
                        })
        except Exception:
            pass

    rows_out = []
    full_out = {}
    for sr in rows_src:
        tk = (sr.get("ticker") or "").upper()
        if not tk:
            continue
        candidates = detail_index.get(tk, [])
        # Prefer most-recent + DEF 14A-style filing
        candidates.sort(key=lambda c: c.get("date") or "", reverse=True)
        text = None
        chosen_acc = None
        for c in candidates:
            t = load_cached_doc(c["acc"])
            if t and ("performance share" in t.lower() or "PSU" in t):
                text = t
                chosen_acc = c["acc"]
                break
        if not text and candidates:
            text, chosen_acc = fetch_and_cache(candidates[0]["url"])
        if not text:
            url = sr.get("filing_url")
            if url:
                text, chosen_acc = fetch_and_cache(url)
        if not text:
            continue

        f = full_forensics(text)
        score, reasons = alignment_depth_score(f)
        full_out[tk] = {"forensics": f, "score": score, "reasons": reasons,
                         "accession": chosen_acc}

        neos = f.get("neos") or []
        award_vals = f.get("neo_award_values") or []
        max_award = max((a["unvested_usd"] for a in award_vals), default=0)

        rows_out.append({
            "ticker": tk,
            "company": sr.get("company") or "",
            "depth_score": round(score, 1),
            "source_master": sr.get("master") or sr.get("composite"),
            "neo_count": len(neos),
            "neo_titles": ", ".join(f"{n['name']} ({n['title']})"
                                     for n in neos[:5]),
            "max_neo_unvested_usd": int(max_award) if max_award else None,
            "neo_with_max": next((a["name"] for a in award_vals
                                  if a["unvested_usd"] == max_award), None) if max_award else None,
            "psu_pct_of_lti": f.get("lti_mix", {}).get("psu_pct"),
            "rsu_pct_of_lti": f.get("lti_mix", {}).get("rsu_pct"),
            "option_pct_of_lti": f.get("lti_mix", {}).get("option_pct"),
            "performance_metrics": ", ".join(f.get("performance_metrics") or []),
            "performance_periods_yrs": ", ".join(str(y) for y in (f.get("performance_periods_yrs") or [])),
            "say_on_pay_pct": f.get("say_on_pay_pct"),
            "comp_consultant": f.get("comp_consultant"),
            "plan_changes": ", ".join(k for k, v in
                                       (f.get("plan_changes") or {}).items() if v),
            "payout_history_pcts": ", ".join(str(p)
                                              for p in (f.get("payout_history_pcts") or [])[:5]),
            "reasons": " | ".join(reasons),
            "accession": chosen_acc,
        })

    rows_out.sort(key=lambda r: r["depth_score"], reverse=True)

    fields = ["rank", "ticker", "company", "depth_score", "source_master",
              "neo_count", "neo_titles", "max_neo_unvested_usd",
              "neo_with_max",
              "psu_pct_of_lti", "rsu_pct_of_lti", "option_pct_of_lti",
              "performance_metrics", "performance_periods_yrs",
              "say_on_pay_pct", "comp_consultant", "plan_changes",
              "payout_history_pcts", "reasons", "accession"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows_out, 1):
            r["rank"] = i
            w.writerow(r)

    Path(args.out_json).write_text(json.dumps(full_out, indent=2, default=str))

    print(f"\nWrote {args.out} ({len(rows_out)} rows) + {args.out_json}\n")
    print(f"{'#':<3}{'TKR':<10}{'SCR':>4}{'PSU%':>5}{'PP':>4}{'MNV':>9}{'SOP':>5}  METRICS / NEO TOP")
    print("-" * 160)
    for i, r in enumerate(rows_out[:50], 1):
        psu = r.get("psu_pct_of_lti") or "-"
        pp_str = r.get("performance_periods_yrs") or "-"
        pp_short = pp_str.split(",")[0].strip() if pp_str != "-" else "-"
        mnv = r.get("max_neo_unvested_usd")
        mnv_s = f"${mnv/1e6:.0f}M" if mnv else "-"
        sop = r.get("say_on_pay_pct")
        sop_s = f"{sop:.0f}%" if sop else "-"
        mets = (r.get("performance_metrics") or "")[:30]
        top_neo = r.get("neo_with_max") or ""
        info = f"{mets}  | NEO: {top_neo[:24]}"
        print(f"{i:<3}{r['ticker']:<10}{r['depth_score']:>4.0f}"
              f"{str(psu):>5}{pp_short:>4}{mnv_s:>9}{sop_s:>5}  {info[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
