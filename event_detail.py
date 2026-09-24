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
BUYER = re.compile(r"(?:to be acquired by|acquired by|agreement to sell [^.]{0,120}? to|sale of [^.]{0,120}? to|merge with|merger with|acquisition by|to sell [^.]{0,120}? to|agreed to sell [^.]{0,120}? to)\s+" + PROPER)
ASSET = re.compile(r"(?:sale of|sell|divest(?:iture of)?|dispose of|disposition of)\s+(?:all of\s+|substantially all of\s+)?(?:its|the|our|certain)\s+([^,.;]{3,90}?(?:business|segment|division|unit|operations|portfolio|assets|subsidiary|brand|stake|interest|facility|properties|property|platform))", re.I)
SEPARATE = [
    re.compile(r"one comprising (?:its|the)\s+(?:current\s+)?([^,.;]{3,60}?) and the other comprising (?:its|the)\s+(?:current\s+)?([^,.;]{3,60}?)(?:\s+to\b|,|\.|;)", re.I),
    re.compile(r"separat\w*\s+(?:\([^)]*\)\s+)?of\s+(?:its|the|our)\s+([^,.;]{3,90}?)\s+into\s+(two|three)\s+independent", re.I),
    re.compile(r"separat\w*\s+into\s+([A-Z][^,.;]{2,50}?)\s+and\s+([A-Z][^,.;]{2,50}?)(?:,|\.|;|\s+which)", re.I),
    re.compile(r"spin[- ]?off\s+of\s+(?:its\s+|the\s+|[A-Z][\w’']*\s+former\s+|its\s+former\s+)?([^,.;]{3,80}?(?:business|segment|division|unit|operations|[A-Z]\w+))(?:\s+into|\s+and\b|,|\.|;)", re.I),
    re.compile(r"(?:spin[- ]off|separation|separate)\s+(?:of\s+)?(?:its|the|our)\s+([^,.;]{3,80}?(?:business|segment|division|unit|operations))", re.I),
]
BOILER = re.compile(r"forward-looking|risks and uncertainties|include, but are not limited to|could cause actual|no assurance", re.I)
ACTIVIST = re.compile(r"(?:cooperation|nomination|standstill|settlement)\s+agreement\s+(?:\(the\s+[^)]*\)\s+)?with\s+" + PROPER)
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


def sentences_around(t, phrase, hint, n=3):
    """The sentence containing the event phrase (or the family hint) + neighbours."""
    flat = " ".join(t.split())
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", flat)
    idx = None
    for rx in (re.escape(phrase or "~~"), hint):
        if not rx:
            continue
        for i, s in enumerate(sents):
            if re.search(rx, s, re.I) and len(s) > 40 and not BOILER.search(s):
                idx = i
                break
        if idx is not None:
            break
    if idx is None:
        return ""
    return " ".join(sents[idx:idx + n])[:1400]


def parse(fam, exc, mcap):
    f = {}
    if not exc:
        return f
    for ps in PER_SHARE.finditer(exc):
        v = float(ps.group(1))
        if v >= 0.01:                                  # "$0.00 per share" is a par value, not a price
            f["per_share"] = v
            break
    amts = [(_amt(m), m) for m in MONEY.finditer(exc) if (m.group(2) or float(m.group(1).replace(",", "")) >= 1e5)]
    if amts:
        f["amount_usd"] = max(a for a, _ in amts)
        if mcap:
            f["pct_mcap"] = f["amount_usd"] / mcap
    low = exc.lower()
    if re.search(r"\b(?:completed|finali[sz]ed|consummated|closed|effective as of|was completed)\b", low) \
            and not re.search(r"expected to (?:close|be completed)|will be completed|subject to", low):
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
    if fam in ("ASSET_SALE", "SALE_OF_COMPANY", "GOING_PRIVATE"):
        m = BUYER.search(exc)
        if m:
            f["counterparty"] = m.group(1).strip().rstrip(",")
        m = PREMIUM.search(exc)
        if m:
            f["premium_pct"] = float(m.group(1))
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
        s = "Company to be acquired" + (f" by {f['counterparty']}" if f.get("counterparty") else "") \
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
        s = "New CEO" + (f": {f['person']}" if f.get("person") else "")
    elif fam in ("STRATEGIC_REVIEW", "VALUE_COMMITTEE"):
        s = "Strategic review / committee" + (f"; adviser {f['advisor']}" if f.get("advisor") else "")
    else:
        s = fam.replace("_", " ").title() + (f": {amt}{pct}" if amt else "")
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
            f = parse(fam, exc, mcap)
            rec.update({"filed": d, "url": edgar_doc.url(cik, acc), "excerpt": exc,
                        **{k: v for k, v in f.items()}, "what": summary(fam, f, exc)})
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
