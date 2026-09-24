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
    ("relative TSR", r"relative (?:total (?:shareholder|stockholder) return|TSR)|\brTSR\b|\bRTSR\b|TSR relative to|TSR (?:percentile )?rank\w*|TSR performance percentile|TSR[^.,;]{0,25}?percentile rank\w*|(?:total (?:shareholder|stockholder) return|TSR)[^.;]{0,60}?(?:relative to|compared to|versus|against) (?:the )?(?:S&P|Russell|peer|our|a|its|NASDAQ|companies)"),
    ("absolute TSR", r"absolute (?:total (?:shareholder|stockholder) return|TSR)"),
    ("stock-price hurdle", r"stock price (?:hurdle|target|goal)s?|share price (?:hurdle|target|goal)s?|price hurdles?|(?:average |VWAP |closing )(?:stock |share )?price[^.]{0,60}?(?:equals or exceeds|of at least|reach)|\bVWAP\b|market capitalization (?:goal|target|hurdle)s?"),
    ("EPS", r"(?:adjusted |diluted |core )?(?:earnings per share|\bEPS\b)"),
    ("FCF per share", r"free cash flow per share|FCF per share"),
    ("free cash flow", r"(?:adjusted )?free cash flow|\bFCF\b"),
    ("ROIC", r"return on (?:average )?invested capital|\bROIC\b|\bCROIC\b|cash return on invested capital|return on (?:total )?capital\b(?! employed)"),
    ("ROCE", r"return on (?:average )?capital employed|\bROCE\b|\bROACE\b"),
    ("ROE", r"return on (?:average )?(?:tangible )?(?:common )?(?:shareholders['’] |stockholders['’] )?equity|\bROTCE\b|\bROATCE\b|\bROE\b|\bROACE\b"),
    ("ROA", r"return on (?:average )?(?:net )?assets|\bROAA\b|\bROA\b|\bRONA\b"),
    ("book value / share", r"(?:tangible )?book value(?: per share)?|\bT?BVPS\b|\bDBVPS\b"),
    ("FFO", r"(?<!A)\bFFO\b|funds from operations"),
    ("AFFO", r"\bAFFO\b|adjusted funds from operations"),
    ("revenue", r"(?:organic |net |total |core )?revenues?(?: growth)?|net sales|sales growth|\bbookings\b"),
    ("margin", r"(?:EBITDA|operating|gross|pre-tax|adjusted) margin"),
    ("EBITDA", r"(?:adjusted )?\bEBITDA\b(?! margin)"),
    ("operating income / margin", r"operating (?:income|profit)|\bEBIT\b"),
    ("net income", r"net income|pre-tax (?:net )?income"),
    ("cash flow", r"operating cash flow|cash flow from operations"),
    ("economic profit", r"economic profit|economic value added|\bEVA\b"),
    ("production", r"production (?:growth|volume|per share)"),
    ("reserves", r"reserves? (?:growth|replacement|additions)"),
    ("leverage / debt", r"leverage ratio|debt reduction|net debt"),
    ("strategic / ESG", r"strategic (?:objectives|goals|milestones|priorities)|\bESG\b|sustainability|energy transition|emissions|safety"),
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


_PCTW = r"(\d{1,3}(?:\.\d+)?)\s?%"


def _rx(n):
    return dict(METRICS)[n]


def _clause_weights(s_, names):
    """{metric: weight} pairs stated in ONE sentence / table run. Weight cues:
    'X (40%)', 'X, weighted 40%', 'X (67% weight)', '50% on X', '50% based on X',
    'X ... accounts for 50% of', table 'X 75%', 'equally weighted', 'half of ... X'."""
    sw = {}
    if re.search(r"(?:equally[- ]weighted|weighted equally|equal weight(?:ing)?|each (?:weighted|with a weight(?:ing)? of) (?:at )?(?:one-half|one-third|50|33))", s_, re.I) and len(names) >= 2:
        return {n: round(100.0 / len(names), 1) for n in names}
    m = re.search(r"each\s+(?:with\s+(?:a\s+)?(?:weight(?:ing)? of\s+)?|weighted\s+(?:at\s+)?|at\s+|representing\s+|accounting for\s+|comprising\s+)" + _PCTW
                  + r"|\(?(?:weighted\s+)?" + _PCTW + r"\s+each\)?", s_, re.I)
    if m and len(names) >= 2:
        return {n: float(m.group(1) or m.group(2)) for n in names}
    if len(names) == 2 and (len(re.findall(r"\b(?:one-half|half)\b", s_, re.I)) >= 2 or re.search(r"50/50", s_)):
        return {n: 50.0 for n in names}
    for n in names:
        rx = _rx(n)
        cues = [
            r"(?:" + rx + r")[^%.;()]{0,60}?\(\s*(?:weighted\s+|weight(?:ing)?\s+(?:of\s+)?)?(?:approximately\s+)?" + _PCTW + r"(?:\s*(?:weight(?:ing|ed)?|of (?:the )?(?:award|PSUs?|total)[^)]{0,30}))?\s*\)",
            r"(?:" + rx + r")[^%.;]{0,40}?,?\s*weight(?:ed|ing)?\s*(?:of|at)?\s*(?:approximately\s+)?" + _PCTW,
            _PCTW + r"\s+(?:weight(?:ed|ing)?\s+)?(?:on|to|for)\s+(?:the\s+)?(?:(?:achievement|attainment) of\s+)?(?:(?:a|our|the Company['’]s)\s+)?(?:three-year\s+|3-year\s+|cumulative\s+|average\s+|adjusted\s+)*(?:" + rx + r")",
            _PCTW + r"\s+(?:of\s+(?:the\s+)?(?:PSUs?|PRSUs?|PSAs?|award|target\s+\w+|performance (?:shares|units))\s+)?(?:is\s+|are\s+|will be\s+)?(?:based on|tied to|linked to|dependent on|measured (?:on|by|against))\s+(?:the\s+)?(?:three-year\s+|3-year\s+)?(?:company['’]s\s+|our\s+)?(?:achievement of\s+)?(?:\w+\s+){0,3}?(?:" + rx + r")",
            r"(?:" + rx + r")[^%.;]{0,80}?(?:accounts? for|represents?|comprises?|makes? up)\s+" + _PCTW,
            r"(?:" + rx + r")(?:\s+(?:growth|goals?|performance|ranking|percentile|modifier))?\s*(?:\(\d\)\s*)?(?:\||:|–|—|-)?\s*\(?" + _PCTW + r"(?!\s*(?:of target|payout|percentile|CAGR|growth|annual|of (?:the )?(?:peer|companies)))",
            r"(?:^|[•—–|;,(]|\band\b)\s*" + _PCTW + r"\s+(?:(?:of\s+(?:the\s+)?PSUs?\s+)?(?:for|on)\s+)?(?:[A-Za-z\-]+\s+){0,4}?(?:" + rx + r")",
        ]
        for c_ in cues:
            mm = re.search(c_, s_, re.I)
            if mm and not re.search(r"growth of|CAGR|target of|goal of|at least|per year|of target|payout|percentile|threshold|maximum", mm.group(0)[-40:], re.I):
                v = float(mm.group(mm.lastindex))
                if 5 <= v <= 100:
                    sw[n] = v
                    break
    if len(names) >= 2 and not (85 <= sum(sw.values()) <= 110):
        # table / list runs: 'CROIC 40% Relative TSR 60%' (metric then %) or
        # '40% Adjusted EBITDA 40% ROIC 20% rTSR' (% then metric) -- take the reading that adds up
        after, before = {}, {}
        for n in names:
            for mm in re.finditer(r"(?:" + _rx(n) + r")", s_, re.I):
                a_ = re.match(r"\s*(?:\([^)]{0,40}\)\s*)?(?:\(\d\)\s*)?[|:–—-]?\s*\(?" + _PCTW + r"(?!\s*(?:of target|payout|CAGR|growth))", s_[mm.end():mm.end() + 60])
                if a_ and n not in after:
                    after[n] = float(a_.group(1))
                b_ = re.search(_PCTW + r"\s+(?:(?:of\s+(?:the\s+)?PSUs?\s+)?(?:for|on|in)\s+)?(?:[A-Za-z\-]+\s+){0,4}$", s_[max(0, mm.start() - 60):mm.start()])
                if b_ and n not in before:
                    before[n] = float(b_.group(1))
        best = sw
        for cand in (after, before, {**after, **sw}, {**before, **sw}):
            if cand and all(5 <= v <= 100 for v in cand.values()) and abs(sum(cand.values()) - 100) < abs(sum(best.values()) - 100):
                best = cand
        sw = best
    m = re.search(r"\b(?:half|one-half)\s+of\s+(?:the\s+)?(?:PSUs?|PRSUs?|award|performance)", s_, re.I)
    if m and names and not sw:
        sw = {names[0]: 50.0}
    return sw


def _solely(s_):
    """'earned solely based on X' / '100% based on X' / 'X is the sole metric'."""
    m = re.search(r"(?:solely|exclusively|entirely)\s+(?:based\s+)?(?:on|upon|by)\s+(?:the\s+)?(?:\w+\s+){0,6}?", s_, re.I)
    if m:
        names = _metrics_in(s_[m.end():m.end() + 160])
        if names:
            return {names[0]: 100.0}
    m = re.search(r"(?:sole|only|single)\s+(?:performance\s+)?(?:metric|measure)", s_, re.I)
    if m:
        names = _metrics_in(s_)
        if len(names) == 1:
            return {names[0]: 100.0}
    return {}


def extract(text):
    t = " ".join(text.split())
    wins = psu_windows(t)
    w = " ".join(wins)
    sents = [x for x in re.split(r"(?<=[.;])\s+", w) if 30 < len(x) < 900]
    r = {}
    # ---- performance period: every statement in a PSU sentence; the most common wins
    psu_s = [x for x in sents if PSU_WORDS.search(x) and not re.search(
        r"annual (?:cash )?(?:incentive|bonus)|\bAIP\b|short-term incentive", x, re.I)]
    NUMW = r"(one|two|three|four|five|[1-5])"
    per = []
    for x in psu_s:
        for rx_ in (NUMW + r"[- ](?:fiscal[- ])?years?[- ](?:cumulative\s+|relative\s+|average\s+|forward[- ]looking\s+)?(?:performance|measurement)\s+(?:period|cycle)",
                    r"(?:performance|measurement)\s+(?:period|cycle)\s+of\s+" + NUMW + r"\s+(?:fiscal\s+|consecutive\s+)?years?",
                    r"over\s+(?:a|the)\s+" + NUMW + r"[- ]year\s+(?:period|cycle)",
                    NUMW + r"[- ]year\s+(?:cumulative|average|relative|total)\b"):
            for m in re.finditer(rx_, x, re.I):
                per.append(_WORDNUM[m.group(1).lower()])
        for m in re.finditer(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+(20\d\d)\s*(?:to|through|-|–|and ending(?: on)?)\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+(20\d\d)", x):
            d = int(m.group(2)) - int(m.group(1))
            if 0 <= d <= 4:
                per.append(d + 1 if d == 0 or "December 31" in m.group(0) and "January 1" in m.group(0) else max(1, d))
    if per:
        from collections import Counter as _C
        r["period_years"] = _C(per).most_common(1)[0][0]
    m = re.search(r"(?:fiscal\s+)?(20\d\d)\s*(?:[-–—]|through|to)\s*(?:fiscal\s+)?(20\d\d)\s+performance\s+(?:period|cycle)", w, re.I)
    if m and 0 < int(m.group(2)) - int(m.group(1)) < 6:
        r["cycle"] = f"{m.group(1)}–{m.group(2)}"
        r.setdefault("period_years", int(m.group(2)) - int(m.group(1)) + 1)
    if re.search(r"(?:annual|one-year|1-year)\s+(?:performance\s+)?(?:period|goals?|targets?)[^.]{0,100}(?:three|3)-year", w, re.I):
        r["annual_goals_3y_vest"] = True
    # ---- metrics and weights: ONLY sentences about the PSUs (not the annual
    # bonus), and a % counts as a WEIGHT only with an explicit weighting cue --
    # "6% EPS CAGR" or "revenue growth of 5%" are goals, not weights
    mets, per_sentence = {}, []
    bonus = re.compile(r"annual (?:cash )?(?:incentive|bonus)|\bAIP\b|\bSTI\b|short-term incentive|cash bonus|\bMIP\b|annual plan", re.I)
    modifier = re.compile(r"modifier|governor|modif(?:y|ies|ied)\b|(?:cap(?:ped)?|limit(?:ed)?)[^.]{0,40}negative", re.I)
    past = re.compile(r"(?:granted|awarded) in (?:fiscal (?:year )?)?20(?:1\d|2[0-3])\b|20(?:1\d|2[0-2])\s*[-–]\s*20(?:2[0-4])\b|paid out|were earned|vested at", re.I)
    import datetime as _dt
    prev_names, near_psu, tsr_mod, recent = [], 0, 0, []
    for s_ in sents:
        names = _metrics_in(s_)
        if PSU_WORDS.search(s_):
            near_psu = 3                                 # a PSU mention covers the next few sentences / table rows
        else:
            near_psu -= 1
        if not names and prev_names and re.search(r"each\s+(?:with\s+(?:a\s+)?)?" + PCT, s_, re.I):
            names = prev_names
        if names:
            prev_names = names
        if near_psu <= 0 or bonus.search(s_) or not names:
            continue
        # a metric that only MODIFIES the payout (rTSR modifier / TSR governor) is not a weighted metric
        core = [n for n in names if not (n in ("relative TSR", "absolute TSR") and modifier.search(s_) and len(names) > 1)]
        if re.search(r"(?:relative )?(?:TSR|total shareholder return)\s+(?:performance\s+)?(?:modifier|multiplier|governor)", s_, re.I):
            tsr_mod += 1
        if not past.search(s_):
            for n in core:
                mets[n] = mets.get(n, 0) + 1
        sw = _solely(s_) or _clause_weights(s_, core)
        if sw and not past.search(s_):
            per_sentence.append(sw)
            recent.append(bool(re.search(r"\b(?:%d|%d)\b" % (_dt.date.today().year, _dt.date.today().year - 1), s_)))
    # sets that span a sentence pair / table run: merge neighbours until they add up
    merged = []
    for i, sw in enumerate(per_sentence):
        acc = dict(sw)
        for nxt in per_sentence[i + 1:i + 4]:
            if 90 <= sum(acc.values()) <= 110:
                break
            if set(nxt) & set(acc):
                break
            acc.update(nxt)
        merged.append(acc)
    full = [x for x, _r in sorted(zip(merged, recent), key=lambda z: not z[1]) if 90 <= sum(x.values()) <= 110.5]
    if tsr_mod:
        r["modifier"] = "relative TSR modifier"
        weighted_tsr = any("relative TSR" in x for x in full)
        if not weighted_tsr:
            mets.pop("relative TSR", None)
    if full:
        best = full[0]                      # proxies state the CURRENT design first
        r["metrics"] = best
        r["weights_verified"] = True
        r["other_metrics"] = [k for k in mets if k not in best]
    elif mets:
        # no stated weights: the metrics named most often in the PSU text (drops one-off mentions)
        top = max(mets.values())
        keep = [k for k, c in mets.items() if c >= max(2, top * 0.5)] or [max(mets, key=mets.get)]
        part = max(merged, key=lambda x: sum(x.values())) if merged else {}
        if part and sum(part.values()) <= 110:
            r["metrics_partial"] = part                     # stated weights that don't add to 100%
        r["metrics"] = {k: None for k in keep}
        if len(keep) == 1:                                  # one metric dominates the PSU text
            r["metrics"] = {keep[0]: 100.0}
            r["weights_verified"] = False
        r["other_metrics"] = [k for k in mets if k not in keep]
    else:
        r["metrics"] = {}
    # ---- payout range: every candidate in a PSU context; the most common value wins
    bonus_rx = re.compile(r"annual (?:cash )?(?:incentive|bonus)|\bAIP\b|\bSTI\b|short-term incentive|cash bonus|\bMIP\b|bonus opportunit", re.I)
    ctx_rx = re.compile(PSU_WORDS.pattern + r"|performance[- ]based RSUs?|performance units?|performance-vesting|\bLTPP\b|\bLTIP\b|PSP|target number of (?:shares|units)|shares earned|units earned", re.I)
    maxes, mins = [], []
    for s_ in sents:
        if not ctx_rx.search(s_):
            continue
        for m in re.finditer(r"(?:from|between)?\s*" + PCT + r"\s*(?:to|and|-|–)\s*" + PCT, s_):
            lo, hi = float(m.group(1)), float(m.group(2))
            pre = s_[max(0, m.start() - 90):m.start()]
            if 100 <= hi <= 400 and lo < hi and lo <= 50 and not bonus_rx.search(pre):
                maxes.append(hi); mins.append(lo)
        for m in re.finditer(r"(?:maximum|max\.?|capped at|cap of|up to|highest level|not (?:to )?exceed|no more than)\s*(?:(?:payout|award|opportunity|level|performance|vesting)\s+){0,2}(?:\(|\||:)?\s*(?:of\s+|is\s+|equal to\s+|at\s+|was\s+)?" + PCT, s_, re.I):
            v = float(m.group(1)); pre = s_[max(0, m.start() - 40):m.start()]
            if 100 < v <= 400 and not bonus_rx.search(pre) and not re.search(r"negative", s_[m.start():m.end() + 30], re.I):
                maxes.append(v)
        for m in re.finditer(PCT + r"\s+for\s+(?:PSUs|PRSUs|performance (?:shares|units|awards))", s_, re.I):
            v = float(m.group(1))
            if 100 < v <= 400:
                maxes += [v, v]                                 # explicitly the PSU cap
    if maxes:
        from collections import Counter as _C
        c = _C(maxes).most_common()
        r["payout_max"] = max(v for v, n in c if n == c[0][1])
        if mins and r["payout_max"] in maxes:
            r["payout_min"] = min(mins)
    # ---- relative TSR scale: the percentile that earns 100% of target
    pcts = sorted({int(x) for x in re.findall(r"(\d{2})(?:\.\d+)?\s?(?:th|st|nd|rd)?[- ]percentile", w) if 10 <= int(x) <= 95})
    if pcts:
        r["rtsr_percentiles"] = pcts
    tc = []
    for s_ in sents:
        if not re.search(r"TSR|total (?:shareholder|stockholder) return|percentile", s_, re.I):
            continue
        for rx_ in (r"(\d{2})\s?(?:th|st|nd|rd)?[- ]percentile[^.%]{0,50}?\b100\s?%",
                    r"\b100\s?%[^.%]{0,40}?(\d{2})\s?(?:th|st|nd|rd)?[- ]percentile",
                    r"[Tt]arget\b[^.%\d]{0,40}?(\d{2})\s?(?:th|st|nd|rd)?[- ]percentile",
                    r"(\d{2})\s?(?:th|st|nd|rd)?[- ]percentile[^.%\d]{0,30}?\b[Tt]arget\b"):
            for m in re.finditer(rx_, s_, re.I):
                v = int(m.group(1))
                if 25 <= v <= 80:
                    tc.append(v)
        if re.search(r"target[^.]{0,60}\bmedian\b|\bmedian\b[^.]{0,40}(?:100\s?%|target)", s_, re.I) and not re.search(r"above[- ]median", s_, re.I):
            tc.append(50)
    if tc:
        from collections import Counter as _C
        r["rtsr_target_pct"] = _C(tc).most_common(1)[0][0]
    m = re.search(r"(?:TSR|total shareholder return)\s+modifier[^.]{0,140}?(?:\+/-|±|plus or minus|up to|by)\s*" + PCT, w, re.I)
    if m:
        r["tsr_modifier"] = float(m.group(1))
    if re.search(r"(?:TSR|total shareholder return)\s+(?:is\s+)?negative[^.]{0,140}(?:capped|cap|limited|not exceed|no more than|cannot (?:exceed|earn more))[^.]{0,60}(?:100\s?%|target)", w, re.I) or \
       re.search(r"(?:capped|limited)\s+at\s+(?:target|100\s?%)[^.]{0,60}if\s+(?:absolute\s+)?(?:TSR|total shareholder return)\s+is\s+negative", w, re.I):
        r["negative_tsr_cap"] = True
    # ---- goal table rows
    goals = re.findall(r"[^.]{0,80}Threshold[^.]{0,240}Target[^.]{0,240}Maximum[^.]{0,200}", w, re.I)
    if goals:
        r["goals_excerpt"] = goals[0][:500]
    # ---- what past cycles actually PAID: a payout phrase + a cycle anchor in the same sentence
    from datetime import date as _d
    this_year = _d.today().year
    PAY = re.compile(r"(?:paid out at|paying out at|pay out at|earned at|vested (?:in|at)|(?:final |total |overall )?payout (?:factor |percentage |level )?(?:of|at|was|equal to)|"
                     r"vesting (?:percentage|level|factor) of|earned percentage of|were earned at|was earned at|were|was|equal (?:t\s?o)|"
                     r"resulted in(?: a (?:total |final |overall )?(?:payout|vesting) of)?|earned|certified (?:a payout of|at)?|"
                     r"funded at|settled at|achieved|attained)\s+(?:approximately\s+|a\s+)?" + PCT +
                     r"(?!\s*(?:of (?:the )?(?:total|LTI|long-term|target (?:LTI|value|grant value|award value)|base salary)|weight))", re.I)
    PAY2 = re.compile(PCT + r"\s+(?:total\s+)?(?:payout|vesting of the award|of (?:the )?target(?: (?:number of )?(?:shares|units|PSUs|PRSUs|performance[- ]based RSUs))?|of their (?:target )?(?:PSUs|PRSUs|\d{4} PSUs))", re.I)
    ANCH = [(re.compile(r"\bFY\s?'?(\d{2})\s*[-–—]\s*FY\s?'?(\d{2})\b"), "fy"),
            (re.compile(r"(?:fiscal\s+(?:year\s+)?)?(20\d\d)\s*(?:[-–—]|through|to)\s*(?:fiscal\s+(?:year\s+)?)?(20\d\d)"), "range"),
            (re.compile(r"(?:granted|awarded|issued|made|grants?)(?: to [^.]{0,30}?)? (?:in )?(?:(?:January|February|March|April|May|June|July|August|September|October|November|December) )?(?:fiscal (?:year )?)?(20\d\d)", re.I), "grant"),
            (re.compile(r"(?:fiscal (?:year )?)?(20\d\d)\s+(?:PSUs?|PRSUs?|PSAs?|performance[- ](?:share|stock|based)|PSU award|LTPP|LTIP|grant|awards?)", re.I), "grant")]
    hist = []
    for s_ in re.split(r"(?<=[.;])\s+|\s[•▪◦]\s", t):
        if len(s_) > 2500 or not ctx_rx.search(s_):
            continue
        anchors = []
        for rx_, kind in ANCH:
            for am in rx_.finditer(s_):
                key = None
                if kind == "fy":
                    a1, a2 = 2000 + int(am.group(1)), 2000 + int(am.group(2))
                    key = f"{a1}–{a2}" if 0 < a2 - a1 < 6 and a2 <= this_year else None
                elif kind == "range":
                    a1, a2 = int(am.group(1)), int(am.group(2))
                    key = f"{a1}–{a2}" if 0 < a2 - a1 < 6 and a2 <= this_year else None
                else:
                    y = int(am.group(1))
                    key = f"{y} grant" if y <= this_year - 3 else None
                anchors.append((am.start(), am.end(), key))
        if not anchors:
            continue
        for m in list(PAY.finditer(s_)) + list(PAY2.finditer(s_)):
            v = float(m.group(1))
            pre = s_[max(0, m.start() - 80):m.start()]
            if not 0 <= v <= 300 or bonus_rx.search(pre) or re.search(r"weight|of (?:total|the) (?:LTI|mix)|salary", s_[m.end():m.end() + 25], re.I):
                continue
            near = min(anchors, key=lambda a_: min(abs(a_[0] - m.start()), abs(a_[1] - m.start())))
            if min(abs(near[0] - m.start()), abs(near[1] - m.start())) <= 300 and near[2]:
                hist.append((near[2], v))
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


TEXT_CACHE = ROOT / "fmp_cache" / "psu_text"


def proxy_text(t, proxy=None, yq=None):
    """Flattened proxy text (cached separately so the scorecard can re-extract fast)."""
    import gzip
    p = TEXT_CACHE / f"{t}.txt.gz"
    if p.exists():
        return gzip.open(p, "rt", encoding="utf-8").read()
    proxy = proxy or latest_proxy()
    if t not in proxy:
        return ""
    cik = ((yq or {}).get(t) or {}).get("cik")
    if not cik:
        try:
            import edgar
            cik = edgar.cik_for(t)
        except Exception:
            cik = None
    if not cik:
        return ""
    txt = " ".join(edgar_doc.text(cik, proxy[t]["accession"], want=("primary",), max_chars=3_000_000).split())
    if txt:
        TEXT_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            f.write(txt)
        tmp.replace(p)
    return txt


def _reextract_one(t):
    txt = proxy_text(t)
    return t, (extract(txt) if txt else None)


def reextract(tickers, workers=8):
    """Current parser over cached proxy text (for parser_eval)."""
    from multiprocessing import Pool
    with Pool(workers) as pool:
        return dict(pool.map(_reextract_one, tickers, chunksize=8))


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
