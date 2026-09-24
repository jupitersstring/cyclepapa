"""Turnaround-executive asymmetry leg (the Bollenbach signal).

The thesis (Greenblatt, You Can Be a Stock Market Genius):
  A senior turnaround executive voluntarily joining a struggling
  company on an equity-heavy compensation package is one of the
  cleanest insider-information signals available. The exec is
  rationally jumping a "secured ship" into a "sinking lifeboat",
  so the equity-heavy package tells you they see a re-rate path
  the market doesn't.

Detection (no new EDGAR calls -- reuses existing inducement scan
output already cached in pipeline.db / 8-K Item 5.02 stream):
  1. Pull recent 8-K Item 5.02 appointments (`recent_8k_inducement
     _range`) for last N days.
  2. Fetch the primary document via cache_store and parse:
     - executive name + role + grant detail
     - equity grant value vs estimated base salary
     - presence of stock-price-hurdle PSU tranches
  3. Cross-score with:
     - hiring company's distress signal (drawdown, P/B, P/S,
       presence in special_situations_unified)
     - PE / activist sponsorship of the hire
     - if executive name appears in curated turnaround-talent list

Scoring boost is multiplicative: a heavy-equity package at a
distressed company with a known turnaround exec at the helm is the
target setup.

Output: turnaround_signal.csv

Curated turnaround-talent annotations are EDITORIAL OVERLAYS in
the TALENT_HINTS dict. They flag known turnaround names if they
appear in 8-K text, but membership in the output is DATA-DRIVEN
(presence of the 8-K filing), not editorial.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "turnaround_signal.csv"


# ----------------------------------------------------------------------
# Curated turnaround-talent annotations -- editorial overlay, not
# membership decision. Match against 8-K text with word-boundary regex
# AND role-proximity (see parse_8k_text). Keep entries UNAMBIGUOUS:
# unique surnames + multi-word PE/activist firm names. Common-word
# surnames removed to avoid false positives from boilerplate director
# bios mentioning past affiliations.
# ----------------------------------------------------------------------
TALENT_HINTS: dict[str, str] = {
    # Unambiguous classic-operator surnames
    "bollenbach":     "Architect of Hilton / Marriott / Host turnaround",
    "rales":          "Danaher founder (Danaher Business System)",
    "culp":           "Danaher CEO, then GE turnaround",
    "danaher business system": "DBS-trained operator",
    "former danaher": "Danaher-trained operator",
    "at danaher":     "Danaher-trained operator",
    "transdigm":      "TransDigm operating model",
    "roper technologies": "Roper operating model",
    "illinois tool works": "ITW 80/20 operator",
    "3g capital":     "3G zero-based-budgeting operator",
    "constellation software": "Constellation Software operator",
    "iacocca":        "Chrysler reset",
    "gerstner":       "IBM turnaround",
    "mulally":        "Boeing then Ford turnaround",
    "mulcahy":        "Xerox turnaround",
    "marchionne":     "Fiat / Chrysler reset",
    "khosrowshahi":   "Expedia / Uber operator",
    "rosenfeld":      "Mondelez / Kraft operator",
    "smisek":         "Continental / United operator",
    "gennette":       "Macy's restructure",
    "calhoun":        "Boeing restructure",
    "ghosn":          "Renault / Nissan reset",
    "schultz":        "Starbucks revival (twice)",

    # PE / activist firm phrases (multi-word, unambiguous)
    "apollo global":      "Apollo PE-installed operator",
    "cerberus capital":   "Cerberus PE-installed operator",
    "kkr & co":           "KKR PE-installed operator",
    "blackstone":         "Blackstone PE-installed operator",
    "bain capital":       "Bain PE-installed operator",
    "carlyle group":      "Carlyle PE-installed operator",
    "tpg capital":        "TPG PE-installed operator",
    "elliott management": "Elliott-installed operator",
    "elliott investment": "Elliott-installed operator",
    "starboard value":    "Starboard-installed operator",
    "mantle ridge":       "Mantle Ridge-installed operator",
    "engaged capital":    "Engaged Capital-installed operator",
    "valueact capital":   "ValueAct-installed operator",
    "trian fund":         "Trian-installed operator",
    "trian partners":     "Trian-installed operator",
    "jana partners":      "JANA-installed operator",
    "ancora advisors":    "Ancora-installed operator",
    "third point":        "Third Point-installed operator",
    "pershing square":    "Pershing Square-installed operator",
    "icahn enterprises":  "Icahn-installed operator",
    "carl icahn":         "Icahn-installed operator",
}


# ----------------------------------------------------------------------
# 8-K text parsing
# ----------------------------------------------------------------------

GRANT_VALUE_RX = re.compile(
    r"(?:grant|award)[^.]*?\$\s*([\d,]+(?:\.\d+)?)\s*(?:million|m)?", re.I,
)
STOCK_HURDLE_RX = re.compile(
    r"(?:stock price|share price|target price)[^.]*?\$\s*([\d,.]+)", re.I,
)
OPTION_COUNT_RX = re.compile(
    r"([\d,]+)\s*(?:stock options|options to purchase|RSU|restricted stock units|"
    r"performance share units|PSU)", re.I,
)
BASE_SALARY_RX = re.compile(
    r"(?:base salary|annual base)[^.]*?\$\s*([\d,]+)", re.I,
)
APPOINTMENT_RX = re.compile(
    r"(?:appointed|named|hired|elected) (?:as |to be )?"
    r"(?:our |the )?(Chief Executive Officer|CEO|President|"
    r"Chief Financial Officer|CFO|Chief Operating Officer|COO|"
    r"Chairman|Executive Chairman)",
    re.I,
)


_ROLE = (r"(?i:(?:(?:Interim|Acting|Co-|Group|Deputy|Global)\s+)?"
         r"(?:(?:Senior |Executive )?Vice President(?:,\s*|\s+-\s+|\s+and\s+)(?:[A-Z][\w&]+,?\s+){0,3}(?:and\s+)?)?"
         r"(?:President and |President, )?"
         r"(?:Chief Executive Officer|CEO|President(?:,\s+[A-Z][\w ]{2,30})?|Chief Financial Officer|CFO|"
         r"Chief Operating Officer|COO|Chief Accounting Officer|Principal Accounting Officer|"
         r"Chief Restructuring Officer|Chief Transformation Officer|Executive Chair(?:man|woman|person)?|"
         r"Chair(?:man|woman|person)? of the Board|Chief Commercial Officer|Chief Strategy Officer|"
         r"Chief Revenue Officer|Chief Legal Officer|General Counsel|Controller|Treasurer|"
         r"Chief Human Resources Officer|Chief People Officer|Chief [A-Z][a-z]+ Officer|"
         r"(?:Senior |Executive )Vice President(?:,\s+[A-Z][\w ]{3,30})?))")
_PERSON = (r"((?:Mr\.|Ms\.|Mrs\.|Dr\.)\s[A-ZÀ-Ý][\wÀ-ÿ'’\-]+(?=\s+(?:will|was|has|had|is|to)\b)|(?:Mr\.|Ms\.|Mrs\.|Dr\.)?\s?[A-ZÀ-Ý][\wÀ-ÿ'’\-]+(?:\s\([A-Z][a-z]+\))?(?:\s[A-Z]\.)?"
           r"(?:\s(?:(?:van|der|de|den|la|le|von|di|da|du|del|dos|bin|al)\s)*[A-ZÀ-Ý][\wÀ-ÿ'’\-]+){1,2}(?:,?\s+(?:Jr|Sr|III|II)\.?)?)")
# an aside between the name and the role -- never spanning a list of board appointees
_ASIDE = r"(?:,\s*(?:age\s+)?\d{2}\s*,|\s*\(age\s+\d{2}\)|,(?:(?!directors?\b|[Bb]oard\b|Class I)[^;]){0,220}?,)?"
_THE = r"(?:the\s+Company['’]s\s+|its\s+|our\s+|the\s+|[A-Z][\w’']+['’]s\s+)?(?:new\s+|next\s+)?"
APPT_PATTERNS = [
    re.compile(r"(?:Incoming|incoming|New|new)\s+(?:CEO|Chief Executive Officer)\s+" + _PERSON + r"\s+(?:said|stated|commented)[^.]{0,120}?appointed\s+(?:as\s+)?(" + _ROLE + r")"),
    re.compile(_PERSON + r"['’]s\s+(?:appointment|election|promotion)\s+(?:as|to\s+(?:the\s+)?(?:role|position|office)\s+of)\s+" + _THE + "(" + _ROLE + r")"),
    re.compile(r"(?:appointments?|elections?|promotions?|hiring)\s+of\s+" + _PERSON + _ASIDE + r"\s*(?:as|to\s+(?:the\s+)?(?:position|role|office)\s+of|to)\s+" + _THE + "(" + _ROLE + r")"),
    re.compile(r"(?:appointed|named|elected|promoted|appointing|hired|designated)\s+" + _PERSON + _ASIDE + r"\s*(?:as\s+|to\s+(?:the\s+(?:position|role)\s+of\s+)?|to\s+succeed\s+[^;]{0,90}?\s+as\s+)?" + _THE + "(" + _ROLE + r")"),
    re.compile(_PERSON + _ASIDE + r"\s*(?:will join|joined|has joined|will serve|to serve|accepted (?:his|her|the) (?:appointment|offer))\s+(?:the Company\s+|[A-Z][\w’']+\s+)?(?:as|to serve as)\s+" + _THE + "(" + _ROLE + r")"),
    re.compile(_PERSON + _ASIDE + r"\s*(?:will succeed|to succeed|succeeds|succeeded)\s+[^;]{0,90}?\s+as\s+" + _THE + "(" + _ROLE + r")"),
    re.compile(_PERSON + _ASIDE + r"\s*(?:was|has been|will be|is being|had been)\s+(?:appointed|named|elected|promoted)\s+(?:as\s+|to\s+)?" + _THE + "(" + _ROLE + r")"),
]
BACKGROUND_RX = re.compile(r"[^.]*(?:previously served|most recently served|prior to joining|served as|has served|was the|was previously)[^.]*\.", re.I)
DEPART_RX = re.compile(r"[^.]*(?:resign|retire|depart|step(?:ped)? down|terminat|separation from)[^.]*\.", re.I)


def parse_appointment(text: str) -> dict:
    """Who, what role, background, departures and the Item 5.02 excerpt."""
    t = " ".join((text or "").split())
    i = t.lower().find("item 5.02")
    sec = t[i:i + 6000] if i >= 0 else t[:6000]
    out = {"person": None, "role": None, "interim": False, "background": "", "departure": "",
           "excerpt": ""}
    NOT_NAME = re.compile(r"\b(?:Vice|President|Officer|Chief|Executive|Senior|Company|Board|Directors?|"
                          r"Inc|Corp|Corporation|Restaurants|Holdings|Group|LLC|Committee|Chair)\b")
    best = None
    for rx in APPT_PATTERNS:
        for m in rx.finditer(sec):
            person = re.sub(r"^(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s?", "", m.group(1)).strip()
            if NOT_NAME.search(person) or len(person) < 3:
                continue
            pre = sec[max(0, m.start() - 80):m.start()]
            if re.search(r"previously (?:reported|disclosed|announced)", pre, re.I):
                continue                                   # an old appointment being recited
            if re.search(r"(?:said|stated)\s*$", pre.strip()[-12:]) and not re.search(r"appoint|elect|name|promot", m.group(0), re.I):
                continue                                   # a quote attribution, not an appointment
            if best is None or m.start() < best[0]:
                best = (m.start(), person, m.group(2).strip(), m.group(0))
            break
    if best:
        _, out["person"], out["role"], whole = best
        out["interim"] = bool(re.search(r"interim|acting", whole, re.I))
    if out["person"]:
        last = out["person"].split()[-1]
        bg = [b.strip() for b in BACKGROUND_RX.findall(sec) if last in b or "Mr." in b or "Ms." in b]
        out["background"] = " ".join(bg[:2])[:600]
    dep = DEPART_RX.findall(sec)
    out["departure"] = dep[0].strip()[:300] if dep else ""
    body = re.sub(r"^.*?Item 5\.02[^.]*?\.\s*", "", sec, flags=re.I)
    out["excerpt"] = body[:900]
    # what KIND of 5.02 event this is -- only a real hire is the Bollenbach pattern
    low = sec.lower()
    if out["person"] and out["role"]:
        promo = re.search(r"(?:currently|previously) (?:serves|served) as [^.]{0,80}of the company|the company['’]s current|who (?:currently|presently) serves|promoted", low)
        out["event_type"] = "PROMOTION" if promo else "NEW HIRE"
    elif re.search(r"amend\w*[^.]{0,60}employment agreement|employment agreement[^.]{0,60}amend", low):
        out["event_type"] = "PAY AMENDMENT"
    elif "inducement plan" in low or "inducement equity" in low:
        out["event_type"] = "INDUCEMENT PLAN"
    elif out["departure"]:
        out["event_type"] = "DEPARTURE"
    elif re.search(r"grant|award", low):
        out["event_type"] = "EQUITY AWARD"
    else:
        out["event_type"] = "OTHER 5.02"
    return out


def parse_8k_text(text: str) -> dict:
    """Extract appointment-specific signals from 8-K body."""
    out: dict = {
        "role": None,
        "grant_value_usd": None,
        "base_salary_usd": None,
        "stock_hurdles": [],
        "option_counts": [],
        "talent_hits": [],
    }
    if not text:
        return out
    text = " ".join(text.split())          # filings break lines mid-phrase
    text_lc = text.lower()

    ap = parse_appointment(text)
    out.update({k: ap[k] for k in ("person", "interim", "background", "departure", "excerpt", "event_type")})
    out["role"] = ap["role"]
    if not out["role"]:
        m = APPOINTMENT_RX.search(text)
        if m:
            out["role"] = m.group(1).strip()

    m = GRANT_VALUE_RX.search(text)
    if m:
        try:
            v = float(m.group(1).replace(",", ""))
            # heuristic: number < 1000 is likely millions
            if v < 1000: v *= 1e6
            out["grant_value_usd"] = v
        except Exception: pass

    m = BASE_SALARY_RX.search(text)
    if m:
        try:
            out["base_salary_usd"] = float(m.group(1).replace(",", ""))
        except Exception: pass

    for m in STOCK_HURDLE_RX.finditer(text):
        try:
            v = float(m.group(1).replace(",", ""))
            if 0.5 < v < 10000:
                out["stock_hurdles"].append(v)
        except Exception: pass

    for m in OPTION_COUNT_RX.finditer(text):
        try:
            v = int(m.group(1).replace(",", ""))
            if v > 1000:
                out["option_counts"].append(v)
        except Exception: pass

    # Talent matching: require word boundary AND role-context proximity
    # (within ~120 chars of CEO/President/CFO/Chairman/Officer).
    role_window = re.compile(
        r"(chief executive|chief operating|chief financial|"
        r"president|chairman|chief executive officer|ceo\b|cfo\b|coo\b)",
        re.I,
    )
    role_positions = [m.start() for m in role_window.finditer(text)]
    for key, label in TALENT_HINTS.items():
        if len(key) < 4:
            continue  # skip ambiguous short names
        # Word-boundary search
        rx = re.compile(rf"\b{re.escape(key)}\b", re.I)
        m = rx.search(text)
        if not m:
            continue
        # Require role within 120 chars on either side
        pos = m.start()
        if any(abs(pos - rp) <= 120 for rp in role_positions):
            out["talent_hits"].append((key, label))

    return out


# ----------------------------------------------------------------------
# Distress + scoring
# ----------------------------------------------------------------------

def distress_signal(tk: str, yf: dict, proxy: dict,
                     special_sits: dict) -> tuple[float, list[str]]:
    s = 0.0
    reasons: list[str] = []
    y = yf.get(tk, {}) or {}
    px = y.get("price"); hi = y.get("fwk_high"); pb = y.get("p_b")
    try: pb = float(pb) if pb is not None else None
    except: pb = None
    try: px = float(px) if px is not None else None
    except: px = None
    try: hi = float(hi) if hi is not None else None
    except: hi = None

    if px and hi and hi > 0:
        dd = (1 - px / hi) * 100
        if dd > 70: s += 25; reasons.append(f"DD {dd:.0f}%")
        elif dd > 50: s += 15; reasons.append(f"DD {dd:.0f}%")
        elif dd > 30: s += 8

    if pb is not None and 0 < pb < 0.5:
        s += 18; reasons.append(f"P/B {pb:.2f}")
    elif pb is not None and 0 < pb < 1.0:
        s += 10; reasons.append(f"P/B {pb:.2f}")

    # In special_situations restructuring/spinoff stream?
    if tk in special_sits:
        s += 10; reasons.append(f"in special_situations ({special_sits[tk]})")

    # Proxy disclosed a forward-conditional cond_cat (restructuring,
    # asset_sale, Ch11, debt) -> high distress signal
    p = proxy.get(tk, {}) or {}
    high_distress_cats = {"chapter11_emergence", "restructuring_milestone",
                          "debt_leverage_target", "asset_sale_named"}
    for cat in (p.get("cond_cats") or []):
        if cat in high_distress_cats:
            s += 8; reasons.append(f"PSU.{cat}")

    return s, reasons


def grant_signal(parsed: dict) -> tuple[float, list[str]]:
    s = 0.0
    reasons: list[str] = []
    gv = parsed.get("grant_value_usd")
    bs = parsed.get("base_salary_usd")
    if gv:
        # heavy equity grant: > $5M is meaningful for non-mega-cap
        if gv >= 20e6: s += 20; reasons.append(f"grant ${gv/1e6:.0f}M (very heavy)")
        elif gv >= 5e6: s += 12; reasons.append(f"grant ${gv/1e6:.0f}M")
        elif gv >= 1e6: s += 6
        # heavy relative to base salary
        if bs and gv / bs >= 5:
            s += 10; reasons.append(f"grant {gv/bs:.1f}x base salary")

    hurdles = parsed.get("stock_hurdles") or []
    if len(hurdles) >= 3:
        s += 12; reasons.append(f"{len(hurdles)} stock-price tranches")
    elif len(hurdles) >= 1:
        s += 6
    if hurdles:
        # top hurdle as multiple of current price (computed downstream)
        reasons.append(f"hurdles up to ${max(hurdles):.2f}")

    return s, reasons


def talent_signal(parsed: dict) -> tuple[float, list[str]]:
    s = 0.0
    reasons: list[str] = []
    for key, label in parsed.get("talent_hits") or []:
        s += 12
        reasons.append(label)
    # cap
    return min(s, 30), reasons


# ----------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180,
                    help="lookback for 8-K Item 5.02 appointments")
    ap.add_argument("--limit", type=int, default=400,
                    help="EDGAR fetch cap per query")
    ap.add_argument("--sleep", type=float, default=0.18,
                    help="EDGAR sleep between fetches")
    ap.add_argument("--skip-html", action="store_true",
                    help="skip per-filing HTML parse (faster, fewer signals)")
    args = ap.parse_args()

    try:
        from recent import recent_8k_inducement_range
        from cache_store import read_html
    except ImportError as e:
        print(f"need recent.py + cache_store.py: {e}", file=sys.stderr)
        return 1

    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc)
              - timedelta(days=args.days)).strftime("%Y-%m-%d")
    print(f"Pulling 8-K Item 5.02 inducements {start}..{end}",
          file=sys.stderr, flush=True)
    feed = recent_8k_inducement_range(start, end, limit=args.limit)
    print(f"  got {len(feed)} inducement 8-Ks", file=sys.stderr)

    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
         if (ROOT / "yfinance_quick.json").exists() else {}
    proxy = {}
    import glob
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try: d = json.loads(open(fn).read())
        except: continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in proxy or
                    r.get("filing_date","") > proxy[tk].get("filing_date","")):
                    proxy[tk] = r

    special_sits = {}
    ss_path = ROOT / "special_situations_unified.csv"
    if ss_path.exists():
        for r in csv.DictReader(ss_path.open()):
            tk = r.get("ticker")
            if tk and tk not in special_sits:
                special_sits[tk] = r.get("kind", "?")

    rows = []
    n_parsed = 0
    for i, rf in enumerate(feed, 1):
        tk = (rf.ticker or "").upper() or f"CIK{rf.cik}"
        parsed = {"role": None, "grant_value_usd": None,
                   "base_salary_usd": None, "stock_hurdles": [],
                   "option_counts": [], "talent_hits": []}
        if not args.skip_html:
            try:
                html = read_html(rf.accession) or ""
                if not html:
                    # the local cache only holds old filings: fetch the 8-K and
                    # its press release from EDGAR (edgar_doc caches them)
                    import edgar_doc
                    html = edgar_doc.text(rf.cik, rf.accession, want=("primary", "ex99"))
                parsed = parse_8k_text(html)
                n_parsed += 1
            except Exception:
                pass

        d_s, d_r = distress_signal(tk, yf, proxy, special_sits)
        g_s, g_r = grant_signal(parsed)
        t_s, t_r = talent_signal(parsed)

        # Multiplicative-ish combination: a high-talent hire into a
        # high-distress company scores significantly above either alone
        base = d_s + g_s + t_s
        # not a hire (pay amendment, inducement plan, departure...): not the
        # turnaround-talent pattern -- keep it listed but rank it well below hires
        if parsed.get("event_type") not in ("NEW HIRE", "PROMOTION", None):
            base *= 0.3
        bonus = 0.0
        if d_s >= 15 and t_s >= 10:
            bonus = 20  # distressed company + known talent
            base += bonus

        rows.append({
            "ticker": tk,
            "filing_date": rf.filing_date,
            "company": rf.company,
            "accession": rf.accession,
            "role": parsed.get("role") or "",
            "event_type": parsed.get("event_type") or "",
            "person": parsed.get("person") or "",
            "interim": "yes" if parsed.get("interim") else "",
            "background": parsed.get("background") or "",
            "departure": parsed.get("departure") or "",
            "excerpt": parsed.get("excerpt") or "",
            "score": round(base, 1),
            "distress_pts": round(d_s, 1),
            "grant_pts": round(g_s, 1),
            "talent_pts": round(t_s, 1),
            "talent_hits": "; ".join(
                f"{k}: {v}" for k, v in (parsed.get("talent_hits") or [])),
            "grant_value_usd": parsed.get("grant_value_usd"),
            "base_salary_usd": parsed.get("base_salary_usd"),
            "stock_hurdles": ",".join(f"{h:.2f}"
                                       for h in (parsed.get("stock_hurdles") or [])),
            "reasons": "; ".join(d_r + g_r + t_r),
        })
        if i % 50 == 0:
            print(f"  [{i}/{len(feed)}] parsed={n_parsed}",
                  file=sys.stderr, flush=True)

    rows.sort(key=lambda r: -r["score"])
    fieldnames = list(rows[0].keys()) if rows else []
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT} ({len(rows)} rows, {n_parsed} html-parsed)")

    print(f"\n=== TOP 25 turnaround-signal ===")
    print(f"{'#':<3}{'TKR':<8}{'SCR':<5}{'D':<4}{'G':<4}{'T':<4}"
          f"{'DATE':<12}{'ROLE':<22}{'TALENT'}")
    for i, r in enumerate(rows[:25], 1):
        print(f"{i:<3}{r['ticker']:<8}{r['score']:<5}"
              f"{r['distress_pts']:<4.0f}{r['grant_pts']:<4.0f}{r['talent_pts']:<4.0f}"
              f"{r['filing_date']:<12}{(r['role'] or ''):<22}"
              f"{(r['talent_hits'] or '')[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
