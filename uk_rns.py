"""UK RNS announcement scrape — keyword overlay for UK names.

LSE has no clean JSON API for RNS announcements; their site renders
results client-side via XHR but the underlying endpoint changes. The
robust fallback is the company's own news page at
  https://www.londonstockexchange.com/stock/<TICKER>/<COMPANY>/news
served as HTML. Even simpler is to query Yahoo Finance UK news via
yfinance.Ticker(ticker).news -- which proxies LSE/RNS feeds.

This module pulls news headlines per UK ticker and scans for the
keyword bank below. Output: an overlay JSON keyed by ticker.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import yfinance as yf

from uk_universe import UK_UNIVERSE


# ---------------------------------------------------------------------------
# Keyword bank (UK comp + governance + special-sit equivalents)
# ---------------------------------------------------------------------------

UK_KEYWORDS = {
    # Comp / PSU equivalents
    "ltip":               re.compile(r"\b(LTIP|long[- ]term incentive plan|"
                                     r"performance share plan|PSP)\b", re.I),
    "performance_share":  re.compile(r"\bperformance shares?\b|\bperformance "
                                     r"share units?\b|\bPSU\b", re.I),
    "remuneration":       re.compile(r"\b(remuneration (report|policy|"
                                     r"committee))\b", re.I),
    "options":            re.compile(r"\b(option grant|share option scheme|"
                                     r"executive option)\b", re.I),
    # Takeover Panel / governance machinery
    "rule_2_4":           re.compile(r"\bRule 2\.[47]\b", re.I),
    "possible_offer":     re.compile(r"\b(possible offer|formal sale process|"
                                     r"strategic review)\b", re.I),
    "scheme":             re.compile(r"\b(scheme of arrangement|takeover "
                                     r"scheme)\b", re.I),
    "tender":             re.compile(r"\btender offer\b", re.I),
    # Activist / cooperation
    "activist":           re.compile(r"\b(activist|requisition|cooperation "
                                     r"agreement|board representation)\b", re.I),
    "13d_uk":             re.compile(r"\b(major shareholding|disclosure "
                                     r"of major holding|TR-1)\b", re.I),
    # Capital allocation
    "buyback":            re.compile(r"\b(share buy[- ]?back|repurchase "
                                     r"programme|return of capital|"
                                     r"tender offer)\b", re.I),
    "dividend_change":    re.compile(r"\b(special dividend|dividend "
                                     r"increase|dividend cut)\b", re.I),
    # Distress / restructuring
    "going_concern_uk":   re.compile(r"\b(going concern|material "
                                     r"uncertainty|covenant breach|"
                                     r"refinancing)\b", re.I),
    "spinoff_uk":         re.compile(r"\b(demerger|spin[- ]off|separation|"
                                     r"distribution in specie)\b", re.I),
    # CEO change
    "ceo_change":         re.compile(r"\b(new (CEO|Chief Executive)|CEO "
                                     r"resign|appointment of (a )?Chief "
                                     r"Executive|board change)\b", re.I),
}


def fetch_news(ticker: str, max_items: int = 20) -> list[str]:
    """Return a list of recent news titles for a UK ticker via yfinance.
    yfinance proxies the underlying news feed; UK tickers (.L) generally
    return the LSE RNS feed."""
    try:
        t = yf.Ticker(ticker)
        items = t.news or []
    except Exception:
        return []
    titles: list[str] = []
    for item in items[:max_items]:
        # yfinance changed schema -- handle both old (title at top) and new
        # (title under content) shapes.
        title = (item.get("title")
                 or (item.get("content") or {}).get("title"))
        if title:
            titles.append(str(title))
    return titles


def score_titles(titles: list[str]) -> dict:
    """Return per-keyword hit counts + a master count + matched titles."""
    body = "\n".join(titles)
    out: dict = {"news_titles": titles}
    total = 0
    for key, pat in UK_KEYWORDS.items():
        n = len(pat.findall(body))
        out[key] = n
        total += n
    out["rns_signal_count"] = total
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="uk_rns_overlay.json")
    p.add_argument("--sleep", type=float, default=0.40)
    p.add_argument("--max-items", type=int, default=25)
    args = p.parse_args()

    overlay: dict[str, dict] = {}
    out_path = Path(args.out)
    if out_path.exists():
        try:
            overlay = json.loads(out_path.read_text())
        except Exception:
            overlay = {}

    items = list(UK_UNIVERSE.items())
    print(f"Scanning RNS news for {len(items)} UK tickers...", file=sys.stderr)
    for i, (tk, meta) in enumerate(items, 1):
        if tk in overlay:
            continue
        titles = fetch_news(tk, max_items=args.max_items)
        scored = score_titles(titles)
        overlay[tk] = {"name": meta.get("name"), **scored}
        if i % 25 == 0:
            print(f"  [{i}/{len(items)}] processed", file=sys.stderr,
                  flush=True)
            out_path.write_text(json.dumps(overlay, indent=2, default=str))
        time.sleep(args.sleep)

    out_path.write_text(json.dumps(overlay, indent=2, default=str))

    # Surface top hits.
    ranked = [
        (tk, d) for tk, d in overlay.items()
        if d.get("rns_signal_count", 0) > 0
    ]
    ranked.sort(key=lambda x: x[1].get("rns_signal_count", 0), reverse=True)
    print(f"\nWrote {args.out} ({len(overlay)} tickers; "
          f"{len(ranked)} with at least one keyword hit).", file=sys.stderr)
    print(f"\n=== TOP RNS-SIGNAL UK NAMES ===")
    for tk, d in ranked[:20]:
        hits = []
        for key in UK_KEYWORDS:
            v = d.get(key, 0)
            if v:
                hits.append(f"{key}={v}")
        print(f"{tk:<10} {d.get('name','')[:40]:<42} count={d['rns_signal_count']:>2}  {' '.join(hits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
