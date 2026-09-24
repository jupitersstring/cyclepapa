"""What each company's PSU plan actually IS -- and whether it is a good one.

proxy_scan classifies plans (metric types, % of LTI, triggers, price hurdles)
but not the plan itself. This module re-reads the latest DEF 14A CD&A
(edgar_doc) and extracts:

  period        performance period length / cycle years (1-year cycles flagged)
  metrics       each metric and its weight (relative TSR, EPS, ROIC, FCF, ...)
  payout        payout range as % of target (threshold .. maximum)
  rtsr          relative-TSR percentile points (threshold / target / max)
  modifier      TSR modifier (+/- x%) and negative-absolute-TSR payout cap
  goals         threshold / target / maximum goal lines (verbatim table rows)
  history       what past PSU cycles actually PAID (% of target) -- the best
                evidence of how hard the targets are
  hurdles       stock-price hurdles vs today's price (from proxy_scan)

and grades the plan A-D with the reasons:
  + per-share / return / relative-TSR / price-hurdle metrics; 3-year periods;
    payout capped <= 200%; negative-TSR cap; PSUs >= 50-60% of LTI; history
    that pays BELOW target sometimes (rigorous goals); hurdles far above price
  - revenue / adjusted-EBITDA-only metrics; 1-year periods; >200% max; soft
    history (always >= 150%); repricing / discretion / front-loaded grants /
    single-trigger CIC (proxy_scan red flags)

Output: psu_detail.json {ticker: {...}}.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edgar_doc

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "psu_detail.json"

METRICS = [
    ("relative TSR", r"relative (?:total shareholder return|TSR)|\brTSR\b|TSR relative to|TSR (?:percentile )?rank\w*|TSR performance percentile|TSR[^.,;]{0,25}?percentile rank\w*|relative to (?:the )?(?:S&P|Russell|peer)"),
    ("absolute TSR", r"absolute (?:total shareholder return|TSR)"),
    ("stock-price hurdle", r"stock price (?:hurdle|target|goal)s?|share price (?:hurdle|target)s?"),
    ("EPS", r"(?:adjusted |diluted |core )?(?:earnings per share|\bEPS\b)"),
    ("FCF per share", r"free cash flow per share|FCF per share"),
    ("free cash flow", r"(?:adjusted )?free cash flow|\bFCF\b"),
    ("ROIC", r"return on invested capital|\bROIC\b"),
    ("ROE", r"return on (?:average )?(?:tangible )?(?:common )?equity|\bROTCE\b|\bROATCE\b|\bROE\b"),
    ("ROA", r"return on (?:average )?assets|\bROAA\b|\bROA\b"),
    ("book value / share", r"(?:tangible )?book value per share"),
    ("revenue", r"(?:organic |net |total )?revenue(?: growth)?|net sales|sales growth"),
    ("EBITDA", r"(?:adjusted )?\bEBITDA\b(?: margin)?"),
    ("operating income / margin", r"operating (?:income|margin|profit)"),
    ("net income", r"net income"),
    ("cash flow", r"operating cash flow|cash flow from operations"),
    ("economic profit", r"economic profit|economic value added|\bEVA\b"),
    ("leverage / debt", r"leverage ratio|debt reduction|net debt"),
    ("strategic / ESG", r"strategic (?:objectives|goals|milestones)|\bESG\b|sustainability"),
]
GOOD = {"relative TSR", "stock-price hurdle", "EPS", "FCF per share", "free cash flow", "ROIC", "ROE",
        "book value / share", "economic profit", "absolute TSR"}
SOFT = {"revenue", "EBITDA", "strategic / ESG"}
PSU_WORDS = re.compile(r"performance[- ](?:share|stock)\s+units?|performance[- ]based\s+(?:restricted\s+)?(?:stock\s+)?(?:units?|RSUs?|awards?|equity)|\bPSUs?\b|\bPRSUs?\b|\bPSAs?\b|performance shares|performance awards?", re.I)
PCT = r"(\d{1,3}(?:\.\d+)?)\s?%"


def psu_windows(t, width=600, cap=80):
    """Text windows around every PSU mention (whole proxy: the summary pages
    often state the design most clearly, the CD&A the goals and payouts)."""
    out, last = [], -10_000
    for m in PSU_WORDS.finditer(t):
        if m.start() - last < width:            # merge overlapping hits
            continue
        last = m.start()
        out.append(t[max(0, m.start() - width):m.end() + width])
        if len(out) >= cap:
            break
    return out


_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}


def _metrics_in(sentence):
    found = []
    for name, rx in METRICS:
        m = re.search(rx, sentence, re.I if name not in ("EPS",) else 0)
        if m:
            found.append((m.start(), name))
    return [n for _, n in sorted(found)]


def extract(text):
    t = " ".join(text.split())
    wins = psu_windows(t)
    w = " ".join(wins)
    sents = [x for x in re.split(r"(?<=[.;])\s+", w) if 30 < len(x) < 900]
    r = {}
    # ---- performance period
    psu_s = [x for x in sents if PSU_WORDS.search(x) and not re.search(
        r"annual (?:cash )?(?:incentive|bonus)|\bAIP\b|short-term incentive", x, re.I)]
    for x in psu_s:
        m = re.search(r"\b(one|two|three|four|five|[1-5])[- ]year\s+(?:cumulative\s+)?performance\s+(?:period|cycle)", x, re.I)
        if m:
            r["period_years"] = _WORDNUM[m.group(1).lower()]
            break
    m = re.search(r"(?:fiscal\s+)?(20\d\d)\s*(?:[-–—]|through|to)\s*(?:fiscal\s+)?(20\d\d)\s+performance\s+(?:period|cycle)", w, re.I)
    if m and 0 < int(m.group(2)) - int(m.group(1)) < 6:
        r["cycle"] = f"{m.group(1)}–{m.group(2)}"
        r["period_years"] = int(m.group(2)) - int(m.group(1)) + 1     # explicit years beat prose
    if re.search(r"(?:annual|one-year|1-year)\s+(?:performance\s+)?(?:period|goals?|targets?)[^.]{0,100}(?:three|3)-year", w, re.I):
        r["annual_goals_3y_vest"] = True
    # ---- metrics and weights: ONLY sentences about the PSUs (not the annual
    # bonus), and a % counts as a WEIGHT only with an explicit weighting cue --
    # "6% EPS CAGR" or "revenue growth of 5%" are goals, not weights
    mets, per_sentence = {}, []
    growth = re.compile(r"growth|CAGR|increase|improve|target of|goal of|margin of|at least|per year|annual", re.I)
    bonus = re.compile(r"annual (?:cash )?(?:incentive|bonus)|\bAIP\b|\bSTI\b|short-term incentive|cash bonus", re.I)
    prev_names = []
    for s_ in sents:
        names = _metrics_in(s_)
        # "... two PSU metrics, each with 50% weighting" often follows the
        # sentence that NAMES the metrics
        if not names and prev_names and re.search(r"each\s+(?:with\s+(?:a\s+)?)?" + PCT, s_, re.I):
            names = prev_names
        if names:
            prev_names = names
        if not PSU_WORDS.search(s_) or bonus.search(s_):
            continue
        if not names:
            continue
        for n in names:
            mets.setdefault(n, None)
        sw = {}
        m = re.search(r"each\s+(?:with\s+(?:a\s+)?|weighted\s+(?:at\s+)?|at\s+|representing\s+)" + PCT + r"\s*(?:weight(?:ing)?)?", s_, re.I)
        if m or re.search(r"equally\s+weighted", s_, re.I):
            v = float(m.group(1)) if m else round(100.0 / len(names), 1)
            sw = {n: v for n in names}
        else:
            for n in names:
                rx = dict(METRICS)[n]
                cues = [
                    r"(?:" + rx + r")\s*\(\s*" + PCT + r"\s*(?:weight(?:ing)?)?\s*\)",
                    r"(?:" + rx + r")[^.%;]{0,20}?weight(?:ed|ing)?\s*(?:of|at)?\s*" + PCT,
                    PCT + r"\s+weight(?:ed|ing)?\s+(?:on|to|for)\s+(?:the\s+)?(?:" + rx + r")",
                    PCT + r"\s+(?:of\s+(?:the\s+)?(?:PSUs?|PRSUs?|award|target\s+\w+)\s+)?(?:is\s+|are\s+)?(?:based on|tied to|linked to|dependent on)\s+(?:the\s+)?(?:three-year\s+)?(?:company['’]s\s+|our\s+)?(?:" + rx + r")",
                    r"(?:" + rx + r")\s*\|\s*" + PCT,
                ]
                for c_ in cues:
                    mm = re.search(c_, s_, re.I)
                    if mm and not growth.search(mm.group(0)):
                        v = float(mm.group(1))
                        if 5 <= v <= 100:
                            sw[n] = v
                        break
        if sw:
            per_sentence.append(sw)
    # the design is the sentence whose weights add up to ~100% (most metrics wins)
    full = [x for x in per_sentence if 90 <= sum(x.values()) <= 110]
    if full:
        best = full[0]                      # proxies state the CURRENT design first
        r["metrics"] = best
        r["weights_verified"] = True
        r["other_metrics"] = [k for k in mets if k not in best]
    else:
        r["metrics"] = {k: None for k in mets}
    # ---- payout range
    m = re.search(PCT + r"\s*(?:to|-|–|and)\s*" + PCT + r"\s+of\s+(?:the\s+)?(?:target|granted|the target number)", w, re.I)
    if m and float(m.group(2)) > float(m.group(1)):
        r["payout_min"], r["payout_max"] = float(m.group(1)), float(m.group(2))
    else:
        m = re.search(r"(?:maximum|up to|capped at)\s+(?:payout\s+|of\s+|opportunity\s+)?(?:of\s+|is\s+|equal to\s+)?" + PCT + r"\s+of\s+target", w, re.I)
        if m and float(m.group(1)) > 100:
            r["payout_max"] = float(m.group(1))
    # ---- relative TSR scale
    pcts = sorted({int(x) for x in re.findall(r"(\d{2})(?:th|st|nd|rd)?[- ]percentile", w) if 10 <= int(x) <= 95})
    if pcts:
        r["rtsr_percentiles"] = pcts
    m = re.search(r"target[^.]{0,80}?(\d{2})(?:th|st|nd|rd)?[- ]percentile|(\d{2})(?:th|st|nd|rd)?[- ]percentile[^.]{0,60}?(?:target|100\s?%)", w, re.I)
    if m:
        r["rtsr_target_pct"] = int(m.group(1) or m.group(2))
    m = re.search(r"(?:TSR|total shareholder return)\s+modifier[^.]{0,140}?(?:\+/-|±|plus or minus|up to|by)\s*" + PCT, w, re.I)
    if m:
        r["tsr_modifier"] = float(m.group(1))
    if re.search(r"(?:TSR|total shareholder return)\s+(?:is\s+)?negative[^.]{0,140}(?:capped|cap|limited|not exceed|no more than)[^.]{0,40}(?:100\s?%|target)", w, re.I) or \
       re.search(r"(?:capped|limited)\s+at\s+(?:target|100\s?%)[^.]{0,60}if\s+(?:absolute\s+)?(?:TSR|total shareholder return)\s+is\s+negative", w, re.I):
        r["negative_tsr_cap"] = True
    # ---- goal table rows
    goals = re.findall(r"[^.]{0,80}Threshold[^.]{0,240}Target[^.]{0,240}Maximum[^.]{0,200}", w, re.I)
    if goals:
        r["goals_excerpt"] = goals[0][:500]
    # ---- what past cycles actually PAID
    hist = []
    pats = [
        r"(?:fiscal\s+)?(20\d\d)\s*(?:[-–—]|through|to)\s*(?:fiscal\s+)?(20\d\d)[^.]{0,200}?(?:earned|paid out|paid|vested|certified|payout|achieved|resulting in|settled)[^.%]{0,80}?" + PCT,
        r"granted in (?:fiscal\s+(?:year\s+)?)?(20\d\d)[^.]{0,220}?(?:earned|paid out|paid|vested|certified|payout|achieved)[^.%]{0,60}?" + PCT + r"\s+of\s+target",
        r"(?:earned|paid out|vested|certified)\s+at\s+" + PCT + r"\s+of\s+target[^.]{0,100}?(?:fiscal\s+)?(20\d\d)\s*(?:[-–—]|through)\s*(20\d\d)",
    ]
    for i, pat in enumerate(pats):
        for mm in re.finditer(pat, t, re.I):
            g = mm.groups()
            if i == 0:
                k, v = f"{g[0]}–{g[1]}", g[2]
            elif i == 1:
                k, v = f"{g[0]} grant", g[1]
            else:
                k, v = f"{g[1]}–{g[2]}", g[0]
            try:
                v = float(v)
            except ValueError:
                continue
            from datetime import date as _d
            end = re.findall(r"20\d\d", k)
            if end and int(end[-1]) > _d.today().year - (0 if "grant" not in k else -2):
                continue                               # cycle not finished yet: not a payout
            if 0 <= v <= 300 and not re.search(r"salary|bonus|annual incentive|\bAIP\b|\bSTI\b|cash incentive", mm.group(0), re.I):
                hist.append((k, v))
    seen, h2 = set(), []
    for k, v in hist:
        if k not in seen:
            seen.add(k); h2.append((k, v))
    if h2:
        r["history"] = h2[:5]
    # ---- one verbatim design sentence
    for s_ in sents:
        if PSU_WORDS.search(s_) and _metrics_in(s_) and re.search(r"%|percentile|performance period|weight", s_) \
                and not re.search(r"Committee shall|Appendix|Section \d|hereunder|Participant", s_) and s_.count("|") < 4:
            r["design_excerpt"] = s_.strip()[:500]
            break
    return r


def grade(r, proxy, price):
    pts, why = 0, []
    mets = r.get("metrics") or {}
    names = set(mets)
    good, soft = names & GOOD, names & SOFT
    if good:
        pts += 2; why.append("per-share / return / TSR metrics: " + ", ".join(sorted(good)))
    if soft and not good:
        pts -= 2; why.append("only revenue / EBITDA / strategic metrics")
    elif soft:
        why.append("also " + ", ".join(sorted(soft)))
    py = r.get("period_years")
    if py and py >= 3:
        pts += 2; why.append(f"{py}-year performance period")
    elif py == 1 and not r.get("annual_goals_3y_vest"):
        pts -= 2; why.append("1-year performance period")
    elif r.get("annual_goals_3y_vest"):
        pts -= 1; why.append("annual goals inside a 3-year vest")
    mx = r.get("payout_max")
    if mx:
        if mx <= 200:
            pts += 1; why.append(f"payout capped at {mx:.0f}%")
        else:
            pts -= 1; why.append(f"max payout {mx:.0f}% (>200%)")
    if r.get("negative_tsr_cap"):
        pts += 1; why.append("payout capped at target if TSR negative")
    tp = r.get("rtsr_target_pct")
    if tp:
        if tp >= 55:
            pts += 1; why.append(f"target at {tp}th percentile (above median)")
        elif tp < 50:
            pts -= 1; why.append(f"target at {tp}th percentile (below median)")
    lti = (proxy or {}).get("psu_pct_lti")
    try:
        lti = float(lti) if lti is not None else None
    except (TypeError, ValueError):
        lti = None
    if lti is not None:
        if lti >= 60:
            pts += 2; why.append(f"PSUs {lti:.0f}% of LTI")
        elif lti >= 50:
            pts += 1; why.append(f"PSUs {lti:.0f}% of LTI")
        elif lti < 40:
            pts -= 1; why.append(f"PSUs only {lti:.0f}% of LTI")
    hist = [v for _, v in r.get("history") or []]
    if hist:
        avg = sum(hist) / len(hist)
        if min(hist) < 60:
            pts += 2; why.append(f"history pays below target (min {min(hist):.0f}%): rigorous goals")
        elif avg >= 150:
            pts -= 2; why.append(f"history always pays high (avg {avg:.0f}%): soft goals")
        else:
            pts += 1; why.append(f"history avg {avg:.0f}% of target")
    hur = [h for h in (proxy or {}).get("stock_price_hurdles") or [] if isinstance(h, (int, float))]
    if price:                                  # >5x today's price is a parse artefact, not a hurdle
        hur = [h for h in hur if price * 0.5 <= h <= price * 5]
    if hur and price:
        top = max(hur)
        r["hurdle_max_vs_price"] = top / price
        if top / price >= 2:
            pts += 2; why.append(f"price hurdles up to ${top:g} = {top / price:.1f}× today's ${price:g}")
        elif top / price >= 1.2:
            pts += 1; why.append(f"price hurdles up to {top / price:.1f}× today's price")
    for flag in (proxy or {}).get("gov_reasons") or []:
        fl = str(flag).lower()
        if any(k in fl for k in ("repric", "discretion", "front-load", "single-trigger", "retirement")):
            pts -= 1; why.append(f"red flag: {flag}")
    g = "A" if pts >= 7 else "B" if pts >= 4 else "C" if pts >= 1 else "D"
    return g, pts, why


def summary_line(r, proxy):
    bits = []
    lti = (proxy or {}).get("psu_pct_lti")
    if lti:
        bits.append(f"PSUs {float(lti):.0f}% of LTI")
    if r.get("period_years"):
        bits.append(f"{r['period_years']}-yr" + (f" ({r['cycle']})" if r.get("cycle") else ""))
    mets = r.get("metrics") or {}
    if mets:
        bits.append(", ".join(f"{k} {v:.0f}%" if v else k for k, v in sorted(mets.items(), key=lambda kv: -(kv[1] or 0)))
                    + ("" if r.get("weights_verified") else " (weights not stated)"))
    if r.get("payout_max"):
        bits.append(f"payout {r.get('payout_min', 0):.0f}–{r['payout_max']:.0f}%")
    if r.get("rtsr_target_pct"):
        bits.append(f"rTSR target {r['rtsr_target_pct']}th pct")
    if r.get("tsr_modifier"):
        bits.append(f"±{r['tsr_modifier']:.0f}% TSR modifier")
    if r.get("history"):
        bits.append("paid " + ", ".join(f"{k}: {v:.0f}%" for k, v in r["history"][:3]))
    return " · ".join(bits)


def latest_proxy():
    out = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.load(open(fn))
        except Exception:
            continue
        for r in (d if isinstance(d, list) else d.values()):
            if isinstance(r, dict) and r.get("ticker") and r.get("accession"):
                t = r["ticker"]
                if t not in out or r.get("filing_date", "") > out[t].get("filing_date", ""):
                    out[t] = r
    return out


def scope(proxy):
    names = set()
    nf = ROOT / "name_financials.json"
    # names shown in the books (tear sheets / Name Financials) ...
    import openpyxl
    for book in ("MOST_ASYMMETRIC.xlsx",):
        try:
            ws = openpyxl.load_workbook(ROOT / book, read_only=True)["Name Financials"]
            names |= {str(r[0]).strip() for r in ws.iter_rows(min_row=5, values_only=True) if r and r[0]}
        except Exception:
            pass
    # ... plus the strongest PSU programmes in the universe
    top = sorted((r for r in proxy.values() if r.get("has_psu_program")),
                 key=lambda r: -(float(r.get("psu_core") or 0)))[:300]
    names |= {r["ticker"] for r in top}
    return sorted(n for n in names if n in proxy)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    proxy = latest_proxy()
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    tks = a.tickers or scope(proxy)
    if a.limit:
        tks = tks[: a.limit]
    print(f"PSU detail: {len(tks)} proxies")

    def job(t):
        p = proxy[t]
        cik = (yq.get(t) or {}).get("cik")
        if not cik:
            try:
                import edgar
                cik = edgar.cik_for(t)
            except Exception:
                cik = None
        if not cik:
            return t, None
        txt = edgar_doc.text(cik, p["accession"], want=("primary",), max_chars=3_000_000)
        if not txt:
            return t, None
        r = extract(txt)
        price = (yq.get(t) or {}).get("price")
        g, pts, why = grade(r, p, price)
        r.update({"grade": g, "grade_pts": pts, "why": why, "summary": summary_line(r, p),
                  "filing_date": p.get("filing_date"), "url": edgar_doc.url(cik, p["accession"]),
                  "psu_pct_lti": p.get("psu_pct_lti"), "hurdles": p.get("stock_price_hurdles"),
                  "red_flags": p.get("gov_reasons")})
        return t, r

    out = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (t, r) in enumerate(ex.map(job, tks), 1):
            if r:
                out[t] = r
            if i % 100 == 0:
                print(f"  {i}/{len(tks)}", flush=True)
    old = json.loads(OUT.read_text()) if OUT.exists() and a.tickers else {}
    old.update(out)
    OUT.write_text(json.dumps(old, indent=1))
    from collections import Counter
    print(f"wrote {OUT.name}: {len(out)} plans; grades {dict(Counter(r['grade'] for r in out.values()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
