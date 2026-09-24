"""What EXACTLY is happening in each corporate-action / governance event.

The event feeds (rerate_events_8k.json, governance_events_8k.json) record
only that a phrase appeared in an 8-K on a date. This module goes back to the
filing -- the 8-K on/near that date and its EX-99 press release (edgar_doc) --
and extracts, per event type:

  ASSET_SALE        what is being sold, to whom, for how much, when it closes
  SALE_OF_COMPANY / GOING_PRIVATE   acquirer, price per share / total value,
                    premium, expected close
  TENDER_OFFER      price or price range, size (shares / $), expiry
  BUYBACK_AUTH / CAPITAL_RETURN     programme size, special dividend per share
  SPINOFF / SEPARATION              what is being separated, timing
  STRATEGIC_REVIEW / VALUE_COMMITTEE  advisers, scope
  ACTIVIST_SETTLEMENT               investor, board seats, standstill
  CEO_CHANGE        who, from where
  EXCHANGE_OFFER / CH11_EMERGENCE / others   the key sentence

plus consideration as % of market cap, a verbatim excerpt (the sentences
around the event) and the filing link. A one-line "what" summary is built
from the parsed fields; when a field can't be parsed, the excerpt still shows
the words.

Output: event_detail.json {ticker: [event, ...]} newest first.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import edgar_doc

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "event_detail.json"

MULT = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mm": 1e6, "thousand": 1e3}
MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|bn|mm|thousand)?", re.I)
PER_SHARE = re.compile(r"\$\s?(\d+(?:\.\d+)?)\s+(?:per share|per common share|in cash per share|a share)", re.I)
RANGE_PS = re.compile(r"(?:price|prices)[^.]{0,40}?\$\s?(\d+(?:\.\d+)?)\s+(?:to|and)\s+\$\s?(\d+(?:\.\d+)?)\s+per share", re.I)
UPTO_SH = re.compile(r"up to\s+([\d,]+(?:\.\d+)?)\s*(million\s+)?shares", re.I)
CLOSE = re.compile(r"expected to (?:close|be completed|be consummated)\s+(?:in|by|during|within|on or before|at the end of)?\s*(?:the\s+)?([^.;,()]{3,45})", re.I)
ADVISOR = re.compile(r"([A-Z][A-Za-z&.,'’\- ]{2,50}?)\s+(?:is|are|has been|have been)?\s*(?:serving|acting|retained|engaged)\s+as\s+(?:the\s+Company['’]s\s+|its\s+|exclusive\s+|lead\s+)*financial advis[eo]r", re.I)
PREMIUM = re.compile(r"(?:represents|representing)\s+(?:a\s+)?(?:premium of\s+)?(?:approximately\s+)?(\d+(?:\.\d+)?)%\s+(?:premium)?", re.I)
PROPER = r"([A-Z][A-Za-z0-9&.'’\-]+(?:\s+(?:[A-Z][A-Za-z0-9&.'’\-]+|of|and|&|de|du|la)){0,6})"
BUYER = re.compile(r"(?:to be acquired by|acquired by|agreement to sell [^.]{0,160}? to|sale of [^.]{0,160}? to|merge with|merger with|acquisition by|to sell [^.]{0,160}? to|agreed to sell [^.]{0,160}? to|sold [^.]{0,160}? to)\s+(?:a (?:joint venture|subsidiary|affiliate) (?:established|formed|owned|controlled) by\s+)?(?:an affiliate of\s+|affiliates of\s+)?" + PROPER)
ASSET = re.compile(r"(?:sale of|sell|sold|divest(?:iture of)?|dispose of|disposition of)\s+(?:all of\s+|substantially all of\s+|most of\s+)?(?:its|the|our|certain|\d+%\s+of\s+the\s+[^,.;]{0,40}?\s+in)\s+([^,.;]{3,90}?(?:business|segment|division|unit|operations|portfolio|assets|subsidiary|brand|stake|interest|facility|properties|property|platform|hospitals?|stores|plants?|mines?|exchange))", re.I)
SEPARATE = [
    re.compile(r"one (?:generally )?comprising (?:its|the)\s+(?:current\s+)?(?:Company['’]s\s+)?([^,.;]{3,60}?) and the other (?:generally )?comprising (?:its|the)\s+(?:current\s+)?(?:Company['’]s\s+)?([^,.;]{3,60}?)(?:\s+to\b|,|\.|;|\()", re.I),
    re.compile(r"separat\w*\s+(?:\([^)]*\)\s+)?of\s+(?:its|the|our)\s+([^,.;]{3,90}?)\s+into\s+(two|three)\s+independent", re.I),
    re.compile(r"separat\w*\s+into\s+([A-Z][^,.;]{2,50}?)\s+and\s+([A-Z][^,.;]{2,50}?)(?:,|\.|;|\s+which)", re.I),
    re.compile(r"spin[- ]?off\s+of\s+(?:its\s+|the\s+|[A-Z][\w’']*\s+former\s+|its\s+former\s+)?([^,.;]{3,80}?(?:business|segment|division|unit|operations|[A-Z]\w+))(?:\s+into|\s+and\b|,|\.|;)", re.I),
    re.compile(r"(?:spin[- ]off|separation|separate)\s+(?:of\s+)?(?:its|the|our)\s+([^,.;]{3,80}?(?:business|segment|division|unit|operations))", re.I),
]

ACTIVIST = re.compile(r"(?:(?:cooperation|nomination|standstill|settlement)\s+agreement\s+(?:\([^)]*\)\s+)?(?:with|by and (?:between|among) the Company,?\s+and)\s+|by and (?:between|among) the Company,?\s+(?:and\s+)?)" + PROPER)
SEATS = re.compile(r"(?:appoint|add|nominate)\w*\s+(\w+)\s+(?:new\s+)?(?:independent\s+)?directors?", re.I)
NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# ---------------------------------------------------------------- wider context
# the excerpt is one or two sentences; consideration / counterparty are usually in
# the 8-K's Item 1.01 / 2.01 paragraph or the press-release lede, so fields are
# searched in the excerpt FIRST and then in those paragraphs.
_ITEM = re.compile(r"Item\s+(?:1\.01|2\.01|8\.01|5\.02|3\.03)\b[^.]{0,120}?\.\s", re.I)


def wide_context(doc, n=3500):
    flat = " ".join((doc or "").split())
    parts = []
    for m in list(_ITEM.finditer(flat))[:2]:
        parts.append(flat[m.end():m.end() + n])
    i = flat.find("EX-99")
    parts.append(flat[i:i + n] if i >= 0 else flat[:n])
    return " || ".join(parts)


_CORP = r"(?:,?\s+(?:Inc|Corp|Corporation|Co|Ltd|Limited|LLC|L\.L\.C|L\.?P|plc|PLC|N\.V|S\.A|AG|SE|Holdings?|Group|Partners|Fund|Trust)\.?)*"
ENTITY = r"((?!(?:Section|Item|Exhibit|The Company|This|Such|Each)\b)[A-Z0-9][A-Za-z0-9&.'’\-]*(?:\s+(?:[A-Z0-9&][A-Za-z0-9&.'’\-]*|of|de|du|la|the|for)){0,7}" + _CORP + r")"
_STOP = re.compile(r"\s*(?:\(|,\s*(?:a|an)\s|,\s*(?:and|together)\b|\s+(?:to|for|pursuant|under|in|on|which|that|who|as|at|whereby|On|The)\b|"
                   r"\s+[A-Z]{5,}\b|[.;:](?!\w)|$)")
_VEHICLE = re.compile(r"Merger Sub|Acquisition Sub|\bSub(?:,)? (?:Inc|LLC|Corp)|Newco|BidCo|MergeCo|HoldCo Sub|^\d{5,}|Purchaser|Buyer|Offeror", re.I)
_DEFINED = re.compile(r"^(?:the\s+)?(?:Buyer|Purchaser|Seller|Company|Parent|Merger Sub|Offeror|Investor|Acquiror|Sponsor|Stockholder|Holder|Lender|We|It|Our|Such|This|That|Each|Any|All)s?\b", re.I)
CP_PATTERNS = {
    "deal": [
        r"(?:to be acquired by|will be acquired by|agreed to be acquired by|acquired by|acquisition (?:of the Company )?by)\s+",
        r"(?:merger agreement|agreement and plan of merger|merger)\s+(?:\([^)]{0,80}\)\s+)?(?:,?\s*dated[^,]{0,40},\s*)?(?:with|by and (?:between|among) [^.]{0,160}? and)\s+",
        r"(?:entered into|executed|signed)\s+(?:an?\s+|the\s+)?(?:definitive\s+|binding\s+)?(?:[A-Z][\w\-’']*\s+){0,6}(?:Agreement|Purchase Agreement)\s*(?:\([^)]{0,80}\)\s*)?,?\s*(?:dated[^,]{0,40},\s*)?(?:by and (?:between|among) [^.]{0,160}? and|with)\s+",
        r"(?:agreement to sell|agreed to sell|to sell|sale of|sold|divest\w*|completed the sale of)\s+[^;]{0,160}?\bto\s+",
        r"(?:combine|combination|merge)\s+[^;]{0,120}?\bwith\s+",
        r"(?:agreements?|transaction)\s+with\s+",
        r"(?:separation|spin-?off|distribution)\s+(?:of [^;]{0,80}?\s+)?(?:from|by)\s+",
    ],
    "activist": [
        r"(?:cooperation|nomination|standstill|settlement|support|director appointment|director nomination|letter)\s+agreement\s*(?:\([^)]{0,80}\)\s*)?,?\s*(?:dated[^,]{0,40},\s*)?(?:with|by and (?:between|among) the Company,?\s+and)\s+",
        r"(?:agreement|engagement|discussions)\s+with\s+(?=[A-Z][^.]{0,40}(?:Management|Capital|Partners|Fund|Advisors|Investment|Group|LLC|L\.P))",
    ],
    "tender": [
        r"(?:tender offer|exchange offer|offer)\s+(?:\([^)]{0,80}\)\s+)?by\s+", r"(?:unsolicited|revised)\s+(?:proposal|offer)\s+from\s+",
    ],
}


def counterparty(fam, texts, self_names=()):
    kinds = {"ASSET_SALE": ["deal"], "SALE_OF_COMPANY": ["deal", "tender"], "GOING_PRIVATE": ["deal", "tender"],
             "TENDER_OFFER": ["tender", "deal"], "EXCHANGE_OFFER": ["tender", "deal"],
             "ACTIVIST_SETTLEMENT": ["activist"], "BOARD_REFRESH": ["activist"], "VALUE_COMMITTEE": ["activist"],
             "SPINOFF": ["deal"], "SEPARATION": ["deal"]}.get(fam)
    if not kinds:                                   # mis-tagged family: a deal named in the excerpt itself
        kinds, texts = ["deal", "tender", "activist"], texts[:1]
    for t in texts:
        for k in kinds:
            for pre in CP_PATTERNS[k]:
                for m in re.finditer("(?i:" + pre + r")(?:an? (?:affiliate|subsidiary|entity|fund|vehicle)s? (?:of|sponsored by|managed by|controlled by)\s+|affiliates of\s+|funds (?:managed|advised) by\s+)?" + ENTITY, t):
                    name = _STOP.split(m.group(1))[0].strip(" ,")
                    name = re.sub(r"^(?:The|the)\s+(?=[A-Z])", "", name) if len(name.split()) > 1 else name
                    if len(name) < 3 or _DEFINED.match(name) or name.lower().startswith(("its ", "our ")) or \
                            (self_names and any(n and n in name.lower() for n in self_names)) or name.lower() in ("the", "section"):
                        continue
                    tail = t[m.end(1):m.end(1) + 200]
                    aff = re.match(r"(?:[^.;]{0,120}?)(?:,|\)|and)\s*(?:an?|the)?\s*(?:(?:wholly[- ]owned|indirect|direct)\s+)?(?:affiliate|subsidiary|portfolio company)\s+of\s+" + ENTITY, tail)
                    if aff:
                        name = _STOP.split(aff.group(1))[0].strip(" ,")
                    elif _VEHICLE.search(name):
                        continue                               # a deal vehicle: keep looking for the real party
                    return name
    return None


MONEY2 = re.compile(r"(?:US\$|\$|USD\s?)\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|bn|mm|m|thousand)?\b", re.I)
_CONS_PRE = re.compile(r"(?:up to|for|purchase price|sale price|price of|aggregate|consideration|valued at|value of|proceeds of|"
                       r"totaling|total of|in cash of|amount of|enterprise value|equity value|transaction value|increase[sd]? (?:it )?to|"
                       r"additional|new|a|an)\s+(?:of\s+)?(?:approximately\s+|about\s+|roughly\s+|up to\s+)?$", re.I)
_CONS_POST = re.compile(r"^\s*(?:in (?:cash|total)\s+)?(?:\w+\s+){0,2}(?:share repurchase|stock repurchase|repurchase|buyback|"
                        r"special (?:cash )?dividend|all-cash|cash transaction|transaction|deal|tender offer|purchase price|"
                        r"in cash|capital return)", re.I)
_NOISE = re.compile(r"cash (?:and cash equivalents )?(?:of|balance)|revenue|ebitda|net income|income of|operating|cash flow|sales|"
                    r"debt of|liquidity|total assets|backlog|charge|impairment|loss|gain|fees?|costs?|expenses?|"
                    r"market cap|net proceeds of approximately", re.I)


def consideration(fam, texts, mcap=None):
    """(amount, strong): the consideration / programme size. Priority: a figure
    labelled purchase price / consideration / aggregate; else the first amount in
    a consideration position; searched in the excerpt, then the wider context."""
    for ti, t in enumerate(texts):
        best = None
        for m in MONEY2.finditer(t):
            v = float(m.group(1).replace(",", "")) * {"billion": 1e9, "bn": 1e9, "million": 1e6, "mm": 1e6,
                                                     "m": 1e6, "thousand": 1e3}.get((m.group(2) or "").lower(), 1.0)
            if v < 1e5:
                continue
            pre, post = t[max(0, m.start() - 60):m.start()], t[m.end():m.end() + 60]
            if _NOISE.search(pre[-35:]) or re.match(r"\s*(?:per|a) share", post, re.I):
                continue
            if re.search(r"aggregate principal amount|principal amount", post[:40], re.I) and fam not in ("TENDER_OFFER", "EXCHANGE_OFFER"):
                continue
            strong = bool(re.search(r"(?:gross |aggregate |total |base )?(?:purchase price|consideration|sale price|enterprise value|"
                                    r"equity value|transaction value)(?: of)?\s+(?:approximately\s+|up to\s+)?$", pre, re.I))
            weak = re.search(r"(?:\ba|\ban|new|additional)\s+(?:approximately\s+)?$", pre, re.I)
            if strong or (_CONS_PRE.search(pre) and (ti == 0 or not weak)) or (ti == 0 and _CONS_POST.search(post)):
                if fam in ("BUYBACK_AUTH", "CAPITAL_RETURN", "CAPITAL_RETURN_POLICY") and mcap and v > 3 * mcap:
                    continue
                if strong:
                    return v
                best = best or v
        if best:
            return best
    return None


PS2 = re.compile(r"(€|US\$|\$)\s?(\d+(?:\.\d+)?)\s*(?:\(the “?[^)]{0,30}\)\s*)?(?:in cash\s+|cash\s+|net\s+)?(?:per|a|for each)\s+(?:outstanding\s+|issued\s+)?"
                 r"(?:share|(?:Class [A-C]\s+)?(?:common|ordinary)\s+(?:share|stock)|Common Share|ordinary share|ADS|unit)|"
                 r"(€|US\$|\$)\s?(\d+(?:\.\d+)?)\s*/\s*sh(?:are)?\b", re.I)
_PS_BAD = re.compile(r"EPS|earnings|income|NII|book value|NAV|net asset|FFO|closing (?:sale )?price|stock price|trad|par value|"
                     r"offering price|exercise price|conversion price|strike|high|low|per share was|diluted|basic", re.I)


def per_share(fam, texts):
    want = {"CAPITAL_RETURN": r"special|dividend", "CAPITAL_RETURN_POLICY": r"dividend|special",
            "TENDER_OFFER": r"tender|offer|purchase", "SALE_OF_COMPANY": r"acquire|merger|receive|consideration|offer",
            "GOING_PRIVATE": r"acquire|merger|receive|consideration|offer"}.get(fam, r"acquire|merger|tender|offer|dividend|consideration")
    for t in texts:
        cands = []
        for m in PS2.finditer(t):
            v = float(m.group(2) or m.group(4))
            pre = t[max(0, m.start() - 60):m.start()]
            if v < 0.02 or _PS_BAD.search(pre[-40:]):
                continue
            sc = 2 * bool(re.search(want, t[max(0, m.start() - 120):m.end() + 60], re.I))
            sc += 2 * bool(re.search(r"special", pre, re.I)) if fam.startswith("CAPITAL_RETURN") else 0
            sc -= 3 * bool(re.search(r"regular|quarterly", pre[-50:], re.I)) if fam == "CAPITAL_RETURN" and re.search(r"special", t, re.I) else 0
            cands.append((sc, -m.start(), v))
        if cands:
            return max(cands)[2]
    return None


PHRASE_HINT = {
    "ASSET_SALE": r"sell|sale of|divest|dispos",
    "SALE_OF_COMPANY": r"acquired by|merger|acquire",
    "GOING_PRIVATE": r"private|acquire|merger",
    "TENDER_OFFER": r"tender offer|dutch auction",
    "BUYBACK_AUTH": r"repurchase|buyback",
    "CAPITAL_RETURN": r"dividend|return",
    "CAPITAL_RETURN_POLICY": r"return|dividend|repurchase",
    "SPINOFF": r"spin|separat",
    "SEPARATION": r"separat|spin",
    "STRATEGIC_REVIEW": r"strategic alternatives|strategic review",
    "VALUE_COMMITTEE": r"committee",
    "ACTIVIST_SETTLEMENT": r"agreement with|cooperation|nomination|standstill",
    "CEO_CHANGE": r"chief executive officer",
    "EXCHANGE_OFFER": r"exchange offer",
    "CH11_EMERGENCE": r"emerge|reorganization",
}


def _amt(m):
    return float(m.group(1).replace(",", "")) * MULT.get((m.group(2) or "").lower(), 1.0)


BOILER = re.compile(r"forward-looking|risks and uncertainties|risk factors|include, but are not limited to|could cause actual|"
                    r"no assurance|such statements|emerging growth company|check mark|incorporated by reference|"
                    r"shall not be deemed|pursuant to the requirements|/s/|signature|participants|table of contents|"
                    r"exhibit 99\.1 to this current report|is furnished as exhibit|contacts?:|investor relations:|"
                    r"telephone number|address of principal|employer identification|former name", re.I)
ACTION_VERB = re.compile(r"today announced|announced (?:that|today|it has|the)|entered into|has signed|signed a definitive|"
                         r"approved|authorized|declared|completed|agreed to|will separate|intends to|"
                         r"appointed|named|has commenced|commenced|launched", re.I)


def _is_list_like(s):
    words = s.split()
    caps = sum(1 for w in words if w[:1].isupper())
    verbs = len(re.findall(r"\b(?:is|are|was|were|has|have|will|announced|entered|approved|agreed|sell|acquire)\b", s, re.I))
    digits = sum(ch.isdigit() for ch in s)
    return (len(words) > 25 and caps / len(words) > 0.6 and verbs < 2) or digits > 0.2 * len(s) or s.count("|") > 3


def sentences_around(t, phrase, hint, n=2):
    """The BEST sentence about the event (scored, not first-match) + the next
    one: it must mention the event, should carry an announcement verb, and
    must not be boilerplate, a list or a table."""
    flat = " ".join(t.split())
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", flat)
    best, best_s = None, -1e9
    for i, s in enumerate(sents):
        if len(s) < 40 or len(s) > 1500:
            continue
        hit_p = bool(phrase) and re.search(re.escape(phrase), s, re.I)
        hit_h = bool(hint) and re.search(hint, s, re.I)
        if not (hit_p or hit_h):
            continue
        sc = 3 * bool(hit_p) + 2 * bool(hit_h) + 3 * bool(ACTION_VERB.search(s))
        sc -= 10 * bool(BOILER.search(s)) + 8 * _is_list_like(s)
        if len(s) > 350 and not ACTION_VERB.search(s):
            sc -= 6                                    # a long run with no verb is a table / list
        sc += 1 if i < 40 else 0                     # the press release lede comes first
        if sc > best_s:
            best, best_s = i, sc
    if best is None or best_s < -2:
        return ""
    return " ".join(sents[best:best + n])[:1400]


# governance actions are done when signed / appointed (payouts and deals are done when paid / closed)
ONE_STEP = {"ACTIVIST_SETTLEMENT", "BOARD_REFRESH", "CHAIR_CEO_SPLIT", "DECLASSIFY"}
PRICED = {"ASSET_SALE", "SALE_OF_COMPANY", "GOING_PRIVATE", "TENDER_OFFER", "EXCHANGE_OFFER", "BUYBACK_AUTH",
          "CAPITAL_RETURN", "CAPITAL_RETURN_POLICY"}


def parse(fam, exc, mcap, doc="", self_names=()):
    f = {}
    if not exc:
        return f
    wide = wide_context(doc)
    texts = [exc, wide]
    v = per_share(fam, texts)
    if v:
        f["per_share"] = v
    v = consideration(fam, texts, mcap) if fam in PRICED else None
    if v:
        f["amount_usd"] = v
        if mcap:
            f["pct_mcap"] = v / mcap
    low = exc.lower()
    if re.search(r"\b(?:has |have )?(?:completed|finali[sz]ed|consummated|closed)\s+(?:the|its|on)\b|transaction closed|was completed", low) \
            and not re.search(r"expected to (?:close|be completed)|will be completed", low):
        f["status"] = "COMPLETED"
    elif re.search(r"expected to close|subject to|pending|targeted for|anticipated to", low):
        f["status"] = "PENDING"
    else:
        f["status"] = "ANNOUNCED"
    if fam in ONE_STEP and f["status"] != "COMPLETED" and re.search(
            r"\b(?:entered into|appointed|named|elected|declared|approved|authorized|adopted|amended|terminated|"
            r"formed|established|increased|expanded|added)\b", exc, re.I) and not re.search(r"\bwill (?:enter|appoint|name|declare|form)|intends? to|plans? to", exc, re.I):
        f["status"] = "COMPLETED"
    m = CLOSE.search(exc)
    if m:
        f["timing"] = m.group(1).strip()
    m = ADVISOR.search(exc)
    if m:
        f["advisor"] = m.group(1).strip()
    if fam in ("ASSET_SALE",):
        m = ASSET.search(exc)
        if m:
            f["asset"] = m.group(1).strip()
    if fam in ("SALE_OF_COMPANY", "GOING_PRIVATE"):
        # "Pizza Hut ... will be acquired by X" is a BUSINESS being sold, not the company
        m = re.search(r"\(“([^”]{3,60})”\)\s*,?\s+(?:will be|to be|is to be)\s+acquired by", exc) or \
            re.search(r"([A-Z][\w&’'\- ]{2,50}?)(?:\s*\([^)]*\))?,?\s+(?:will be|to be|is to be)\s+acquired by", exc)
        if m and not re.match(r"(?:the\s+)?Company|We\b|It\b", m.group(1).strip()):
            f["asset"] = m.group(1).strip()
    cp = counterparty(fam, texts, self_names)
    if cp:
        f["counterparty"] = cp
    if fam in ("ASSET_SALE", "SALE_OF_COMPANY", "GOING_PRIVATE"):
        m = PREMIUM.search(exc)
        if m:
            f["premium_pct"] = float(m.group(1))
    if fam in ("CAPITAL_RETURN", "CAPITAL_RETURN_POLICY"):
        mdiv = re.search(r"dividend", exc, re.I)
        div_s = exc[max(0, mdiv.start() - 100):mdiv.end() + 60] if mdiv else ""
        if div_s and not re.search(r"special", div_s, re.I) and re.search(
                r"quarterly|semi-?annual|regular|interim|annual (?:cash )?dividend|dividend policy", div_s, re.I):
            f["subtype"] = "regular dividend"
    ctx = exc + " " + (doc or "")[:20000]
    if fam == "TENDER_OFFER" and re.search(r"tender offer[^.]{0,200}(?:notes|debentures|senior secured|senior unsecured|bonds)|(?:notes|debentures)[^.]{0,200}tender offer", ctx, re.I) \
            and not re.search(r"tender offer[^.]{0,120}(?:shares of (?:its|our) common stock|common shares)", ctx, re.I):
        f["subtype"] = "debt tender"
    if fam == "PILL_REMOVED" and re.search(r"adopt\w*[^.]{0,80}rights (?:plan|agreement)|rights (?:plan|agreement)[^.]{0,80}adopt|"
                                          r"may redeem the Rights|Final Expiration Time|Acquiring Person", ctx[:6000], re.I) \
            and not re.search(r"(?:terminat|redeem|expire|amend)\w*[^.]{0,60}(?:rights (?:plan|agreement)|the Rights)[^.]{0,80}(?:effective|today|early)", exc, re.I):
        f["subtype"] = "rights plan ADOPTED (not removed)"
    if fam == "ACTIVIST_SETTLEMENT" and re.search(r"non-disclosure|confidentiality", exc, re.I) and \
            not re.search(r"cooperation agreement|nomination agreement|settlement agreement", exc, re.I):
        f["subtype"] = "merger NDA standstill (not activism)"
    if fam == "CEO_CHANGE":
        try:
            import turnaround_executive_leg as te
            ap = te.parse_appointment("Item 5.02 " + exc)
            if not ap.get("role"):
                ap = te.parse_appointment(doc or exc)
        except Exception:
            ap = {}
        is_ceo = bool(ap.get("role") and re.search(r"chief executive|ceo", ap["role"], re.I))
        if is_ceo:
            f["person"], f["role"] = ap["person"], ap["role"]
            f["subtype"] = "interim CEO" if ap.get("interim") else None
            if ap.get("background"):
                f["background"] = ap["background"][:300]
        elif re.search(r"step(?:ping|ped)? down|resign|retire|depart|terminat", exc, re.I):
            f["subtype"] = "CEO departure"
        else:
            f["subtype"] = "no appointment found"
    if fam == "TENDER_OFFER":
        m = RANGE_PS.search(exc)
        if m:
            f["price_range"] = f"${m.group(1)}–${m.group(2)}"
        m = UPTO_SH.search(exc)
        if m:
            f["shares"] = float(m.group(1).replace(",", "")) * (1e6 if m.group(2) else 1)
    if fam in ("SPINOFF", "SEPARATION"):
        for rx in SEPARATE:
            m = rx.search(exc)
            if m:
                g = [x.strip() for x in m.groups() if x]
                if len(g) == 2 and g[1].lower() in ("two", "three"):
                    f["asset"] = f"{g[0]} (into {g[1]} companies)"
                elif len(g) == 2:
                    f["asset"] = f"{g[0]} / {g[1]}"
                else:
                    f["asset"] = g[0]
                break
    if fam == "ACTIVIST_SETTLEMENT":
        m = SEATS.search(exc)
        if m:
            f["seats"] = NUMWORD.get(m.group(1).lower(), m.group(1))
        f["standstill"] = bool(re.search(r"standstill", exc, re.I))
    if fam == "CEO_CHANGE":
        try:
            import turnaround_executive_leg as te
            ap = te.parse_appointment(exc)
            if ap.get("person"):
                f["person"], f["role"] = ap["person"], ap["role"]
        except Exception:
            pass
    return f


# phrase-scanner false positives: the words matched but no such corporate event happened
NOT_EVENT = [
    ("GOING_PRIVATE|SALE_OF_COMPANY", r"private placement (?:units|shares)|closing of the IPO|trust account|the Sponsor",
     "SPAC IPO private placement, not a going-private deal"),
    ("CAPITAL_RETURN|CAPITAL_RETURN_POLICY", r"dividend (?:was )?received from|dividend income|received from the FHLB|dividend equivalents",
     "a dividend RECEIVED / accounting item, not a distribution to shareholders"),
    ("VALUE_COMMITTEE|STRATEGIC_REVIEW", r"appointed to the Company['’]s [^.]{0,80}Committee|member of the [^.]{0,60}Committee",
     "a director joining a standing committee, not a strategic review"),
    ("SPINOFF|SEPARATION|CAPITAL_RETURN_POLICY|STRATEGIC_REVIEW", r"non-GAAP adjustment|Represents the (?:one|two|three) components?|All references are to",
     "a footnote / slide, not an announcement"),
]


# generic phantom classes (any family), from the reviewed filings: the words matched,
# but the text is a recital / footnote / bio / cost line, not a new corporate action
GENERIC_NOT_EVENT = [
    (r"\b(?:non-GAAP|we exclude|excluding the (?:effect|impact)|adjusted (?:net )?income|adjusted EBITDA|reconciliation|"
     r"basis of presentation|discontinued operations|have been restated|prior period (?:results|disclosures)|"
     r"tax (?:adjustment|benefit)|notes to (?:the )?consolidated|equity method of accounting|Note \d+\b)",
     "a financial-statement / non-GAAP footnote, not an announcement"),
    (r"(?:costs?|expenses?|charges?|items?|fees)\s+(?:related to|associated with|in connection with|arising (?:out of|from))\s+(?:the\s+)?"
     r"(?:planned |proposed |pending )?(?:separation|spin|transaction|strategic review|divestiture|sale)|"
     r"(?:separation|spin-off|transaction|transformation)[- ](?:related )?(?:costs|expenses|charges|items|initiatives)",
     "a cost line about a transaction, not a new action"),
    (r"^\W*about [A-Z][^.]{0,60}\b(?:is|was) (?:a|an|the) (?:global |leading |premier )",
     "company boilerplate ('About X')"),
    (r"\b(?:served|serves|has served) as\b[^.]{0,120}\b(?:before|prior to|until)\b|prior to joining|his career|her career|"
     r"\bbiograph", "an executive biography, not a change"),
    (r"over-?allotment|underwritten (?:public )?offering|public offering price|(?:registered direct|at-the-market) offering|"
     r"use of (?:the )?(?:net )?proceeds|intends to use the (?:net )?proceeds",
     "a capital raise / offering, not this event"),
    (r"^\W*(?:these|such) (?:risks|factors)|(?:risks|uncertainties)[^.]{0,40}include|in the event (?:that )?the [^.]{0,60}"
     r"(?:is|are) not (?:consummated|completed)",
     "risk-factor / conditional language"),
    (r"\bwill serve on the [^.]{0,80}Committee|\bserves? on (?:the|its) [^.]{0,60}Committee|chairs? (?:the|its) [^.]{0,60}Committee",
     "a director's committee seat, not a strategic action"),
]
_MON = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE = re.compile(rf"\b({_MON})\s+(?:(\d{{1,2}}),?\s+)?(20\d\d)\b|\b(?:first|second|third|fourth) quarter of (20\d\d)\b|\bin (20\d\d)\b")


def _historical(exc, filed):
    """A recital of an old event: every date in the lead sentence is > 150 days before
    the filing and nothing says 'today' / 'this week'."""
    if not filed:
        return False
    try:
        fd = datetime.strptime(filed[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    lead = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", exc)[0] if exc else ""
    if re.search(r"\btoday\b|this week|\bnow\b|will be|expected to|\bintends?\b|amend|terminat|waive|extend|"
                 r"continu|ongoing|remains?|is (?:conducting|exploring|evaluating|pursuing)|process|confirm|pending", lead, re.I):
        return False                                     # a NEW step on an older deal is still news
    ds = []
    for m in _DATE.finditer(lead):
        try:
            if m.group(1):
                ds.append(date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2) or 28)))
            else:
                ds.append(date(int(m.group(4) or m.group(5)), 12, 31))
        except ValueError:
            pass
    if re.search(r"as previously (?:disclosed|reported|announced)|previously completed", lead, re.I) and \
            (not ds or (fd - max(ds)).days > 45):
        return True
    return bool(ds) and (fd - max(ds)).days > 150


MONTHS = {m: i + 1 for i, m in enumerate(_MON.split("|"))}


def validate(fam, exc, doc="", filed=None, f=None):
    for fams, rx, why in NOT_EVENT:
        if re.search(fams, fam) and re.search(rx, exc, re.I):
            return "NOT AN EVENT", why
    lead = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", exc)[0] if exc else ""
    announce = re.search(r"today announced|announced today|\bannounces?\b|has entered into|entered into a definitive|"
                         r"board of directors (?:has )?(?:approved|authorized|declared)|\b(?:formed|established|created)\b", lead, re.I)
    if not announce:
        for rx, why in GENERIC_NOT_EVENT:                   # judged on the LEAD sentence only
            if re.search(rx, lead, re.I | re.M):
                return "NOT AN EVENT", why
    if _historical(exc, filed):
        return "NOT AN EVENT", "a recital of an earlier event (the dates in the text are months before this filing)"
    try:
        import event_classifier
        r = event_classifier.p_real(fam, exc, (doc or "")[:800], filed)
    except Exception:
        r = None
    if r and r[0] < r[1]:
        return "NOT AN EVENT", f"reads as a recital / footnote, not a new action (model P(real) {r[0]:.2f})"
    return "REAL", ""


def summary(fam, f, exc):
    """One line a reader can act on."""
    def money(x):
        return f"${x / 1e9:.2f}bn" if x >= 1e9 else f"${x / 1e6:.0f}M" if x >= 1e6 else f"${x:,.0f}"
    amt = money(f["amount_usd"]) if f.get("amount_usd") else None
    pct = f" ({f['pct_mcap'] * 100:.0f}% of mcap)" if f.get("pct_mcap") and f["pct_mcap"] < 20 else ""
    when = f"; close {f['timing']}" if f.get("timing") else ""
    if fam == "ASSET_SALE":
        s = "Selling " + (f.get("asset") or "assets") + (f" to {f['counterparty']}" if f.get("counterparty") else "") \
            + (f" for {amt}{pct}" if amt else "") + when
    elif fam in ("SALE_OF_COMPANY", "GOING_PRIVATE"):
        s = (f"{f['asset']} (a business) to be acquired" if f.get("asset") else "Company to be acquired") + (f" by {f['counterparty']}" if f.get("counterparty") else "") \
            + (f" at ${f['per_share']:.2f}/sh" if f.get("per_share") else "") \
            + (f" ({f['premium_pct']:.0f}% premium)" if f.get("premium_pct") else "") \
            + (f", {amt} total" if amt else "") + when
    elif fam == "TENDER_OFFER":
        s = "Tender offer" + (f" at {f['price_range']}/sh" if f.get("price_range") else
                              f" at ${f['per_share']:.2f}/sh" if f.get("per_share") else "") \
            + (f" for up to {f['shares']:,.0f} shares" if f.get("shares") else "") \
            + (f" (up to {amt}{pct})" if amt else "")
    elif fam in ("BUYBACK_AUTH", "CAPITAL_RETURN", "CAPITAL_RETURN_POLICY"):
        s = ("Special dividend" if re.search(r"special (?:cash )?dividend", exc, re.I) else "Capital return / buyback") \
            + (f" of ${f['per_share']:.2f}/sh" if f.get("per_share") else "") + (f", {amt}{pct}" if amt else "")
    elif fam in ("SPINOFF", "SEPARATION"):
        m = re.search(r"targeted for ([^.,;]{3,30})", exc)
        s = ("Completed separation of " if f.get("status") == "COMPLETED" else "Separating ") \
            + (f.get("asset") or "a business") + when + (f"; targeted {m.group(1)}" if m and not when else "")
    elif fam == "ACTIVIST_SETTLEMENT":
        s = "Settlement" + (f" with {f['counterparty']}" if f.get("counterparty") else "") \
            + (f": {f['seats']} board seat(s)" if f.get("seats") else "") + ("; standstill" if f.get("standstill") else "")
    elif fam == "CEO_CHANGE":
        s = "New CEO" + (f": {f['person']}" if f.get("person") else "") + (
            f" — {f['background'][:140]}" if f.get("background") else "")
    elif fam in ("STRATEGIC_REVIEW", "VALUE_COMMITTEE"):
        s = "Strategic review / committee" + (f"; adviser {f['advisor']}" if f.get("advisor") else "")
    else:
        s = fam.replace("_", " ").title() + (f": {amt}{pct}" if amt else "")
    if f.get("subtype") == "regular dividend":
        s = "Regular dividend (not a special return)" + (f" ${f['per_share']:.2f}/sh" if f.get("per_share") else "")
    elif f.get("subtype") == "debt tender":
        s = "Debt tender offer (for notes, not shares)" + (f": {amt}" if amt else "")
    elif f.get("subtype") == "merger NDA standstill (not activism)":
        s = "Standstill inside a merger NDA — not an activist settlement"
    elif f.get("subtype") == "rights plan ADOPTED (not removed)":
        s = "Rights plan (poison pill) ADOPTED — the opposite of a removal"
    elif f.get("subtype") == "CEO departure":
        s = "CEO departure (no successor named in this filing)"
    elif f.get("subtype") == "interim CEO":
        s = "Interim CEO" + (f": {f['person']}" if f.get("person") else "")
    elif f.get("subtype") == "no appointment found":
        s = "CEO-related filing — no new CEO appointment in the text"
    if f.get("status") and fam not in ("SPINOFF", "SEPARATION"):
        s = f"[{f['status'].lower()}] " + s
    return s


_YQ = {}


def self_names(tk):
    """The issuer's own ticker / name stem: never its own counterparty."""
    if not _YQ:
        try:
            _YQ.update(json.loads((ROOT / "yfinance_quick.json").read_text()))
        except Exception:
            pass
    nm = str((_YQ.get(tk) or {}).get("name") or "").lower()
    stem = re.sub(r"[^a-z0-9 ]", " ", nm).split()
    return tuple(x for x in (tk.lower() if len(tk) > 2 else "", stem[0] if stem and len(stem[0]) > 3 else "") if x)


def process(fam, phrase, cik, acc, filed, mcap, t=None, tk=""):
    """Excerpt + parse + validate one filing. None when the event is not in it."""
    if t is None:
        try:
            t = edgar_doc.text(cik, acc, want=("ex99", "primary"))
        except Exception:
            t = ""
    exc = sentences_around(t, phrase, PHRASE_HINT.get(fam))
    if not exc:
        return None
    f = parse(fam, exc, mcap, t, self_names(tk) if tk else ())
    verdict, why = validate(fam, exc, t, filed, f)
    what = summary(fam, f, exc)
    if verdict != "REAL":
        what = f"⚠ not a real event — {why}"
    return {"filed": filed, "url": edgar_doc.url(cik, acc), "excerpt": exc,
            **{k: v for k, v in f.items()}, "what": what, "verdict": verdict, "verdict_reason": why}


def reparse(rec, mcap=None, tk=""):
    """Re-run the CURRENT parser over the filing an earlier run located (for the scorecard)."""
    m = re.search(r"/data/(\d+)/(\d{18})/", rec.get("url") or "")
    if not m:
        return rec
    acc = f"{m.group(2)[:10]}-{m.group(2)[10:12]}-{m.group(2)[12:]}"
    out = process(rec["family"], rec.get("phrase") or "", m.group(1), acc, rec.get("filed"), mcap, tk=tk)
    return {"family": rec["family"], "date": rec.get("date"), "phrase": rec.get("phrase"), **(out or {})}


def work(args):
    tk, cik, fam, info, mcap = args
    date, phrase = info.get("date"), info.get("phrase") or ""
    rec = {"family": fam, "date": date, "phrase": phrase}
    if not cik or not date:
        return tk, rec
    try:
        hits = edgar_doc.find_filing(cik, date, days=4)
    except Exception:
        hits = []
    for acc, d in hits[:3]:
        out = process(fam, phrase, cik, acc, d, mcap, tk=tk)
        if out:
            rec.update(out)
            break
    return tk, rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    yq = json.loads((ROOT / "yfinance_quick.json").read_text())
    jobs = []
    for fn in ("rerate_events_8k.json", "governance_events_8k.json"):
        p = ROOT / fn
        if not p.exists():
            continue
        for tk, fams in json.loads(p.read_text()).items():
            y = yq.get(tk) or {}
            for fam, info in fams.items():
                jobs.append((tk, y.get("cik"), fam, info, y.get("mcap")))
    if a.limit:
        jobs = jobs[: a.limit]
    print(f"event detail: {len(jobs)} events")
    out = {}
    with ThreadPoolExecutor(a.workers) as ex:
        for i, (tk, rec) in enumerate(ex.map(work, jobs), 1):
            out.setdefault(tk, []).append(rec)
            if i % 200 == 0:
                print(f"  {i}/{len(jobs)}", flush=True)
    for tk in out:
        out[tk].sort(key=lambda r: r.get("date") or "", reverse=True)
    OUT.write_text(json.dumps(out, indent=1))
    n = sum(len(v) for v in out.values())
    got = sum(1 for v in out.values() for r in v if r.get("excerpt"))
    parsed = sum(1 for v in out.values() for r in v if r.get("what") and any(
        r.get(k) for k in ("amount_usd", "counterparty", "asset", "per_share", "person", "price_range")))
    print(f"wrote {OUT.name}: {n} events; {got} with the filing text located; {parsed} with parsed specifics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
