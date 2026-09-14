"""Corporate-action re-rate catalysts -- spin-offs, separations, asset
sales, sale-of-company, strategic reviews.

The cleanest re-rates are mechanical: a spin-off collapses a conglomerate
discount (sum-of-the-parts is realised), an asset sale monetises a hidden
or non-core piece and de-levers, a sale of the company delivers a takeover
premium, a strategic review puts the whole thing in play. This module
unifies every place the framework already sees such an action and crosses
it with the payoff-geometry re-rate ROOM, so the output is: names where a
structural corporate action could drive a re-rate, ranked by catalyst
strength x how much upside the geometry says is on offer.

Catalyst evidence, by source hardness:
  * PSU-INCENTIVISED (proxy_scan cond_cats) -- management is PAID to
    achieve spin_separation / asset_sale_named / merger_acquisition_close.
    Skin in the game; the hardest signal.
  * ACTIVE TENDER (tender_scan role TARGET / self-tender) -- a live bid.
  * NARRATIVE INTENT (mda_scan phrases) -- management SAYS it in the MD&A
    (pursue a spin-off, planned separation, sale of the company, exit
    non-core, sum-of-the-parts, review of strategic alternatives).

A catalyst named by TWO independent sources (e.g. incentive + narrative)
is triangulated and scores a convergence bonus. Multiple distinct catalyst
types on one name (e.g. strategic review + sum-of-parts) is the in-play
configuration.

Output: rerate_catalysts.json keyed by ticker.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "rerate_catalysts.json"

# MD&A phrase -> catalyst bucket (narrative source).
MDA_MAP = {
    "pursue a spin-off": "SPINOFF",
    "separation into two": "SPINOFF",
    "planned separation": "SEPARATION",
    "sale of the company": "SALE_OF_COMPANY",
    "exit non-core": "ASSET_SALE",
    "monetize non-core": "ASSET_SALE",
    "portfolio optimization": "ASSET_SALE",
    "monetization of": "ASSET_SALE",
    "sum-of-the-parts": "STRATEGIC_REVIEW",
    "review of strategic alternatives": "STRATEGIC_REVIEW",
    "exploring strategic alternatives": "STRATEGIC_REVIEW",
    "unlock shareholder value": "STRATEGIC_REVIEW",
    "unlock the value": "STRATEGIC_REVIEW",
}
# proxy cond_cat -> bucket (PSU-incentivised source).
PROXY_MAP = {
    "spin_separation": "SPINOFF",
    "asset_sale_named": "ASSET_SALE",
    "merger_acquisition_close": "SALE_OF_COMPANY",
}
# per-source base weight by hardness. CALIBRATED to the historical event
# study (rerate_backtest.py, 2024-01..2025-06, 113 events): on the median
# every catalyst UNDERPERFORMED SPY, so raw catalyst is not broadly bullish
# -- the payoff is a right tail (15% of events > +50% / 12m). SPIN-OFFS
# produced the most tail winners and were reliable in large-caps (+4% median,
# 57% hit); STRATEGIC_REVIEW had the worst median (-10%, -27% excess) -- most
# reviews fizzle -- so it is down-weighted to pure optionality; an ALREADY-
# ANNOUNCED sale (tender TARGET) has little forward juice (deal already
# priced), so it is down-weighted vs an emerging catalyst.
W_INCENTIVE = {"SPINOFF": 11, "ASSET_SALE": 9, "SALE_OF_COMPANY": 7,
               "SEPARATION": 11, "STRATEGIC_REVIEW": 4}
W_TENDER = 7                  # active bid, but deal largely priced already
W_NARRATIVE = {"SPINOFF": 7, "SEPARATION": 7, "SALE_OF_COMPANY": 5,
               "ASSET_SALE": 5, "STRATEGIC_REVIEW": 3}
# 8-K primary-filing announcement: harder than MD&A narrative (an actual
# announced action, dated), softer than a PSU forward-vesting condition.
# Covers the full corporate-action set, not just spins/sales.
W_EVENT = {"SPINOFF": 10, "SEPARATION": 10, "SALE_OF_COMPANY": 7,
           "ASSET_SALE": 7, "STRATEGIC_REVIEW": 5,
           "CH11_EMERGENCE": 10, "GOING_PRIVATE": 9, "CAPITAL_RETURN": 6,
           "UPLISTING": 7, "BUYBACK_AUTH": 5}
TRIANGULATION_BONUS = 5       # a bucket named by 2+ independent sources
MULTI_TYPE_BONUS = 4         # 2+ distinct catalyst types


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _load(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def load_proxy():
    proxy = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try:
            d = json.load(open(fn))
        except Exception:
            continue
        for r in (d if isinstance(d, list) else d.values()):
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if tk not in proxy or r.get("filing_date", "") > proxy[tk].get("filing_date", ""):
                    proxy[tk] = r
    return proxy


def main() -> int:
    proxy = load_proxy()
    tender = _load("tender_scan.json")
    mda = _load("mda_scan.json")
    geo = _load("payoff_geometry.json")
    yf = _load("yfinance_quick.json")

    per: dict[str, dict] = {}

    def rec(tk):
        return per.setdefault(tk, {
            "ticker": tk, "buckets": {}, "sources": {}, "catalyst_score": 0.0})

    def add(tk, bucket, source, weight, evidence):
        r = rec(tk)
        r["buckets"].setdefault(bucket, set()).add(source)
        r["sources"].setdefault(bucket, []).append({source: evidence})
        # keep the max single-source weight per bucket; extra sources add via
        # the triangulation bonus, not raw stacking.
        r.setdefault("_bw", {})
        r["_bw"][bucket] = max(r["_bw"].get(bucket, 0), weight)

    # 1) PSU-incentivised corporate actions -- ONLY when the category is a
    #    genuine FORWARD-directed vesting condition, not change-of-control
    #    boilerplate. cond_cats keeps every category the comp section merely
    #    MENTIONS ("awards vest upon a merger or spin-off"), which is near-
    #    universal CIC language; a real incentive requires n_fwd_cond > 0 AND
    #    the category's keyword to appear in the forward-condition snippets.
    #    (Audit: without this gate, 122/122 spin and 79/80 merger cond_cats
    #    were boilerplate -- e.g. SENS flagged spin+merger with n_fwd_cond=0.)
    import re as _re
    _CAT_KW = {"spin_separation": r"spin|separat",
               "asset_sale_named": r"sale|divest|sell|dispos",
               "merger_acquisition_close": r"merger|acquisi|combinat|take.?private|sale of the company"}
    for tk, p in proxy.items():
        if not p.get("n_fwd_cond"):
            continue
        snip = " ".join(p.get("fwd_snippets") or []).lower()
        for cat in (p.get("cond_cats") or []):
            b = PROXY_MAP.get(cat)
            if b and _re.search(_CAT_KW.get(cat, cat), snip):
                add(tk, b, "incentive", W_INCENTIVE[b], cat)

    # 1b) live 8-K corporate-action announcements (rerate_events_8k.py).
    events8k = _load("rerate_events_8k.json")
    for tk, buckets in events8k.items():
        if not isinstance(buckets, dict):
            continue
        for b, info in buckets.items():
            if b in W_EVENT:
                add(tk, b, "event", W_EVENT[b],
                    (info or {}).get("phrase", "8-K"))

    # 2) active tenders (live bids).
    for tk, t in tender.items():
        if not isinstance(t, dict):
            continue
        if t.get("role") == "TARGET":
            add(tk, "SALE_OF_COMPANY", "tender", W_TENDER, "tender TARGET")

    # 3) MD&A narrative intent.
    for tk, v in mda.items():
        if not isinstance(v, dict):
            continue
        for ph in (v.get("phrases") or []):
            b = MDA_MAP.get(ph)
            if b:
                add(tk, b, "narrative", W_NARRATIVE[b], ph)

    # 4) assemble scores + cross with payoff geometry.
    out = {}
    for tk, r in per.items():
        bw = r.pop("_bw", {})
        score = sum(bw.values())
        for b, srcs in r["buckets"].items():
            if len(srcs) >= 2:
                score += TRIANGULATION_BONUS
        if len(r["buckets"]) >= 2:
            score += MULTI_TYPE_BONUS
        g = geo.get(tk) or {}
        upside = g.get("upside_pct") or 0.0
        # a catalyst is worth more when the geometry says there is room to
        # re-rate; scale modestly (up to +50% for >=300% upside room).
        room_mult = 1.0 + min(upside, 3.0) / 3.0 * 0.5
        rerate_score = round(score * room_mult, 1)
        y = yf.get(tk) or {}
        out[tk] = {
            "ticker": tk,
            "catalyst_types": sorted(r["buckets"].keys()),
            "n_types": len(r["buckets"]),
            "sources_by_bucket": {b: sorted(s) for b, s in r["buckets"].items()},
            "evidence": r["sources"],
            "catalyst_score": round(score, 1),
            "geometry_ratio": g.get("ratio"),
            "upside_pct": g.get("upside_pct"),
            "downside_pct": g.get("downside_pct"),
            "floor_source": g.get("floor_source"),
            "mcap": y.get("mcap"),
            "sector": y.get("sector") or (g.get("sector")),
            "rerate_score": rerate_score,
        }

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: -r["rerate_score"])
    from collections import Counter
    bc = Counter(b for r in out.values() for b in r["catalyst_types"])
    print(f"wrote {OUT} ({len(out)} names with a corporate-action catalyst)")
    for b, n in bc.most_common():
        print(f"  {b:<18} {n}")
    print(f"\n{'TKR':<7}{'RSCORE':>7}{'TYPES':>6}{'RATIO':>7}{'UP%':>6}  CATALYSTS (sources)")
    for r in ranked[:30]:
        room = f"{(r['upside_pct'] or 0)*100:.0f}%"
        rat = f"{r['geometry_ratio']:.1f}" if r.get("geometry_ratio") else "-"
        cats = ", ".join(f"{b}[{'/'.join(r['sources_by_bucket'][b])}]"
                         for b in r["catalyst_types"])
        print(f"{r['ticker']:<7}{r['rerate_score']:>7.1f}{r['n_types']:>6}"
              f"{rat:>7}{room:>6}  {cats[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
