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


def parse(fam, exc, mcap, doc=""):
    f = {}
    if not exc:
        return f
    for ps in PER_SHARE.finditer(exc):
        v = float(ps.group(1))
        pre = exc[max(0, ps.start() - 25):ps.start()].lower()
        if v >= 0.02 and "par value" not in pre:       # "$0.01 per share" par value is not a price
            f["per_share"] = v
            break
    # a dollar figure counts only when it is the CONSIDERATION / programme size
    CONS = re.compile(r"(?:up to|for|purchase price|aggregate|consideration|valued at|value of|proceeds of|"
                      r"totaling|total of|in cash of|amount of)\s+(?:approximately\s+|about\s+)?$", re.I)
    NOISE = re.compile(r"cash (?:and cash equivalents )?(?:of|balance)|revenue|ebitda|net income|operating|"
                       r"cash flow|sales|debt of|liquidity|total assets|backlog", re.I)
    amts = []
    for m in MONEY.finditer(exc):
        v = _amt(m)
        pre = exc[max(0, m.start() - 40):m.start()]
        if v < 1e5 and not m.group(2):
            continue
        if CONS.search(pre) and not NOISE.search(pre[-30:]):
            amts.append(v)
    if amts:
        f["amount_usd"] = max(amts)
        if mcap:
            f["pct_mcap"] = f["amount_usd"] / mcap
            if fam in ("BUYBACK_AUTH", "CAPITAL_RETURN", "CAPITAL_RETURN_POLICY") and f["pct_mcap"] > 3:
                f.pop("amount_usd"); f.pop("pct_mcap")
    low = exc.lower()
    if re.search(r"\b(?:has |have )?(?:completed|finali[sz]ed|consummated|closed)\s+(?:the|its|on)\b|transaction closed|was completed", low) \
            and not re.search(r"expected to (?:close|be completed)|will be completed", low):
        f["status"] = "COMPLETED"
    elif re.search(r"expected to close|subject to|pending|targeted for|anticipated to", low):
        f["status"] = "PENDING"
    else:
        f["status"] = "ANNOUNCED"
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
    if fam in ("ASSET_SALE", "SALE_OF_COMPANY", "GOING_PRIVATE"):
        m = BUYER.search(exc)
        if m:
            f["counterparty"] = m.group(1).strip().rstrip(",")
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
        m = ACTIVIST.search(exc)
        if m:
            f["counterparty"] = m.group(1).strip().rstrip(",")
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
    ("PILL_REMOVED", r"may redeem the Rights|Final Expiration Time|Acquiring Person",
     "rights-plan terms (adoption boilerplate), not a pill removal"),
]


def validate(fam, exc):
    for fams, rx, why in NOT_EVENT:
        if re.search(fams, fam) and re.search(rx, exc, re.I):
            return "NOT AN EVENT", why
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
    elif f.get("subtype") == "CEO departure":
        s = "CEO departure (no successor named in this filing)"
    elif f.get("subtype") == "interim CEO":
        s = "Interim CEO" + (f": {f['person']}" if f.get("person") else "")
    elif f.get("subtype") == "no appointment found":
        s = "CEO-related filing — no new CEO appointment in the text"
    if f.get("status") and fam not in ("SPINOFF", "SEPARATION"):
        s = f"[{f['status'].lower()}] " + s
    return s


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
        try:
            t = edgar_doc.text(cik, acc, want=("ex99", "primary"))
        except Exception:
            t = ""
        exc = sentences_around(t, phrase, PHRASE_HINT.get(fam))
        if exc:
            f = parse(fam, exc, mcap, t)
            verdict, why = validate(fam, exc)
            what = summary(fam, f, exc)
            if verdict != "REAL":
                what = f"⚠ not a real event — {why}"
            rec.update({"filed": d, "url": edgar_doc.url(cik, acc), "excerpt": exc,
                        **{k: v for k, v in f.items()}, "what": what, "verdict": verdict,
                        "verdict_reason": why})
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
