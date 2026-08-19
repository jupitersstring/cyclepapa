"""UK RNS revealed-preference / capital-events monitor.

Extends the revealed-preference (own-shares buyback, premium placing),
distressed-stub and hidden-asset engines to the UK. The spec stresses
jurisdiction-specific vocabulary: the UK's "Transaction in Own Shares"
is the invaluable own-shares marker; "placing"/"subscription" the
issuance marker; "scheme of arrangement" / "Part 26A restructuring plan"
/ "CVA" the distressed markers.

SOURCE REALITY (honest): the UK has no free EFTS-equivalent full-text
search. The LSE retired its public RSS; Companies House and its charges
API (the structured lien-release / MR04-MR05 signal) need a free API key.
What is freely reachable is investegate's server-rendered RECENT
announcements listing -- so this is a recent-events MONITOR, not a
historical sweep. It classifies by the RNS headline (carried in the
announcement URL slug), filters the investment-trust NAV-buyback noise
(mechanical, low-signal per the spec), scores per the revealed-preference
/ distressed logic, and fetches bodies for the high-signal operating-
company events to extract premium / amount / finality.

UK names live in their OWN universe/output (like foreign_markets) -- they
do NOT enter the US consensus, preserving the clean-universe discipline.

Optional depth: set CH_API_KEY to enable the Companies House charges
endpoint (satisfaction/release of charges = the distressed lien-release
signal). Without it, that layer is skipped gracefully.

Output: uk_rns_events.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "uk_rns_events.json"
BASE = "https://www.investegate.co.uk"
ANN_RX = re.compile(r'/announcement/(rns|prn)/(.+?)--([a-z0-9.]+)/([^/]+)/(\d+)')

# UK headline -> (family, class, points). The headline slug is the RNS
# title lower-cased and hyphenated.
HEADLINE_MAP = [
    # --- own-shares revealed preference ---
    ("tender-offer", "own_shares", "tender_offer", 12),
    ("return-of-capital", "own_shares", "return_of_capital", 9),
    ("b-share", "own_shares", "b_share_scheme", 8),
    ("odd-lot", "own_shares", "odd_lot", 8),
    ("purchase-of-own-shares", "own_shares", "purchase_own_shares", 6),
    ("transaction-in-own-shares", "own_shares", "transaction_own_shares", 4),
    # --- issuance / premium injection ---
    ("placing-and-subscription", "issuance", "placing_subscription", 8),
    ("subscription", "issuance", "subscription", 7),
    ("placing", "issuance", "placing", 6),
    ("strategic-investment", "issuance", "strategic_investment", 12),
    ("issue-of-equity", "issuance", "issue_of_equity", 4),
    # --- distressed-stub progress ---
    ("scheme-of-arrangement", "distressed", "scheme_of_arrangement", 10),
    ("restructuring-plan", "distressed", "part26a_plan", 12),
    ("restructuring", "distressed", "restructuring", 8),
    ("company-voluntary-arrangement", "distressed", "cva", 10),
    ("refinancing", "distressed", "refinancing", 7),
    ("debt-restructuring", "distressed", "debt_restructuring", 10),
    ("completion-of-disposal", "distressed", "disposal_completion", 8),
    ("disposal", "distressed", "disposal", 5),
    ("capital-reorganisation", "distressed", "capital_reorg", 7),
    ("restoration", "distressed", "listing_restored", 6),
    ("restoration-of-listing", "distressed", "listing_restored", 8),
    # --- strategic / catalyst ---
    ("strategic-review", "catalyst", "strategic_review", 6),
    ("offer-for", "catalyst", "takeover_offer", 9),
    ("recommended-offer", "catalyst", "recommended_offer", 10),
    ("possible-offer", "catalyst", "possible_offer", 6),
]

# Investment-trust / fund names -- mechanical NAV buybacks, low signal.
# URL slugs truncate the company name, so also match on the major UK
# trust SPONSOR brands (a name carrying one is almost always a fund) and
# common trust-name fragments that survive truncation.
FUND_RX = re.compile(
    r"(\btrust\b|\binvestment\b|\bfund\b|\bicvc\b|\bvct\b|\boeic\b|sicav|"
    r"smaller-co|smaller companies|growth-in|emerging-market|"
    r"special-s|income-(?:ltd|plc|limited|trust)|witan|alliance-witan|"
    r"jpmorgan|fidelity|blackrock|schroder|aberdeen|abrdn|henderson|"
    r"baillie|invesco|janus|polar-capital|montanaro|foresight|"
    r"pershing|pacific-hor|greencoat|gresham-house|ruffer|"
    r"personal-assets|scottish-mortgage|city-of-london|edinburgh|"
    r"bankers|mercantile|law-debenture|finsbury|troy|f-c-)", re.I)

PREMIUM_RX = re.compile(r"premium of (?:approximately )?(\d{1,3}(?:\.\d+)?)\s*%|"
                        r"(\d{1,3}(?:\.\d+)?)\s*%\s+premium", re.I)
DISCOUNT_RX = re.compile(r"discount of (?:approximately )?(\d{1,3}(?:\.\d+)?)\s*%", re.I)
FROM_HOLDER_RX = re.compile(r"repurchase[^.\n]{0,60}?\bfrom\b[^.\n]{0,40}?"
                            r"(fund|partners|capital|holdings|founder|shareholder)", re.I)
FINALITY_RX = re.compile(r"\b(completed|effective|sanctioned|approved|"
                         r"cancelled|discharged|repaid|settled)\b", re.I)


def _get(url):
    from recent import _get as g
    for _ in range(3):
        try:
            return g(url).text
        except Exception:
            time.sleep(1.5)
    return ""


def classify(headline_slug):
    for needle, family, cls, pts in HEADLINE_MAP:
        if needle in headline_slug:
            return family, cls, pts
    return None, None, 0


def collect_listings(pages):
    """Server-rendered recent announcements from the homepage + archive."""
    seen = {}
    urls = [BASE + "/"] + [f"{BASE}/announcement-archive?page={p}" for p in range(1, pages + 1)]
    for u in urls:
        html = _get(u)
        for m in ANN_RX.finditer(html):
            feed, name, tk, slug, aid = m.groups()
            seen.setdefault(aid, {"ticker": tk.upper() + ".L", "name": name,
                                  "headline": slug, "id": aid,
                                  "url": BASE + m.group(0)})
        time.sleep(0.2)
    return list(seen.values())


def companies_house_charges(name):
    """Optional: satisfied/released charges (lien-release distressed
    signal) via Companies House. Requires CH_API_KEY; skipped otherwise."""
    key = os.environ.get("CH_API_KEY")
    if not key:
        return None
    import base64
    from recent import _get_raw  # not always present; guard below
    try:
        import requests
        auth = base64.b64encode(f"{key}:".encode()).decode()
        r = requests.get(
            f"https://api.company-information.service.gov.uk/search/companies?q={name}",
            headers={"Authorization": f"Basic {auth}"}, timeout=20)
        items = r.json().get("items", [])
        if not items:
            return None
        cno = items[0]["company_number"]
        rc = requests.get(
            f"https://api.company-information.service.gov.uk/company/{cno}/charges",
            headers={"Authorization": f"Basic {auth}"}, timeout=20)
        charges = rc.json().get("items", [])
        satisfied = sum(1 for c in charges if c.get("status") in ("satisfied", "part-satisfied"))
        return {"total_charges": len(charges), "satisfied": satisfied}
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=12,
                    help="archive pages to poll (5 announcements each)")
    ap.add_argument("--verify-top", type=int, default=25)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    print(f"UK RNS monitor: polling homepage + {args.pages} archive pages",
          file=sys.stderr)
    listings = collect_listings(args.pages)
    print(f"  {len(listings)} recent announcements", file=sys.stderr)

    scored = {}
    for a in listings:
        family, cls, pts = classify(a["headline"])
        if not family:
            continue
        is_fund = bool(FUND_RX.search(a["name"]))
        # mechanical trust "transaction in own shares" is near-noise
        if is_fund and cls in ("transaction_own_shares", "purchase_own_shares",
                               "issue_of_equity"):
            continue
        score = float(pts)
        if is_fund:
            score *= 0.5
        rec = scored.get(a["ticker"])
        if not rec or score > rec["score"]:
            scored[a["ticker"]] = {"ticker": a["ticker"], "name": a["name"],
                                   "family": family, "class": cls,
                                   "score": score, "is_fund": is_fund,
                                   "headline": a["headline"], "url": a["url"],
                                   "premium_pct": None, "vs_market": None}

    # verify high-signal operating-company events (premium / finality)
    ranked = sorted(scored.values(), key=lambda r: -r["score"])
    for rec in ranked[:args.verify_top]:
        if rec["is_fund"]:
            continue
        html = _get(rec["url"])
        time.sleep(args.sleep)
        if not html:
            continue
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))[:120000]
        mp = PREMIUM_RX.search(txt)
        if mp:
            rec["premium_pct"] = float(mp.group(1) or mp.group(2))
            rec["vs_market"] = "premium"; rec["score"] += 8
        elif DISCOUNT_RX.search(txt):
            rec["vs_market"] = "discount"
        if FROM_HOLDER_RX.search(txt):
            rec["score"] += 5; rec["from_holder"] = True
        if rec["family"] == "distressed" and FINALITY_RX.search(txt):
            rec["score"] += 4; rec["finality"] = True
        ch = companies_house_charges(rec["name"])
        if ch and ch["satisfied"] > 0:
            rec["score"] += 4; rec["charges_satisfied"] = ch["satisfied"]

    out = {tk: r for tk, r in scored.items() if r["score"] > 0}
    for r in out.values():
        r["score"] = round(r["score"], 1)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT} ({len(out)} UK events)")
    print("\n=== TOP UK RNS EVENTS (recent) ===")
    print(f"{'TICKER':<9}{'SCR':>5} {'FAMILY':<11}{'CLASS':<24}NAME")
    for r in sorted(out.values(), key=lambda x: -x["score"])[:22]:
        f = "[fund]" if r["is_fund"] else ""
        print(f"{r['ticker']:<9}{r['score']:>5.0f} {r['family']:<11}{r['class']:<24}{r['name'][:24]}{f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
