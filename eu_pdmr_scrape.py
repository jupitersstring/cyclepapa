"""European PDMR insider-buying scrape (yfinance news + multi-language
keyword detection). Resumable; output keyed by ticker.

Yfinance's .news property proxies the underlying RNS / DGAP / AMF /
Finansinspektionen / AFM / Consob / CMVM news feeds for European
tickers. Items get tagged with the issuer's CIK-equivalent. We pull
the news titles per ticker and run the multi-language PDMR keyword
bank from eu_pdmr_keywords.

Two complementary signals per ticker:
  - PDMR / Directors' dealings count (insider-side)
  - Buyback execution count (firm-side)

Both feed the EU equivalent of Bonaimé-Ryngaert: same-direction
agreement on buy events = real undervaluation signal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yfinance as yf

from eu_pdmr_keywords import score_titles
from eu_buyback_detect import load_european_universe
from universe_filter import is_excluded


def fetch_news_titles(ticker: str, max_items: int = 30) -> list[str]:
    try:
        t = yf.Ticker(ticker)
        items = t.news or []
    except Exception:
        return []
    titles = []
    for it in items[:max_items]:
        # yfinance changed schema once -- handle both shapes
        title = (it.get("title") or
                 (it.get("content") or {}).get("title"))
        if title:
            titles.append(str(title))
    return titles


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="eu_pdmr.json")
    p.add_argument("--sleep", type=float, default=0.30)
    p.add_argument("--max-items", type=int, default=30)
    p.add_argument("--limit", type=int, default=10000)
    p.add_argument("--region", choices=["UK", "EU", "INTL", "ALL"], default="ALL")
    args = p.parse_args()

    universe = load_european_universe()
    if args.region == "UK":
        universe = [t for t in universe if t.endswith(".L")]
    elif args.region == "EU":
        eu_suffixes = (".DE", ".PA", ".MI", ".AS", ".BR", ".VI", ".HE", ".ST",
                       ".CO", ".SW", ".OL", ".MC", ".LS", ".AT", ".WA", ".F")
        universe = [t for t in universe if any(t.endswith(s) for s in eu_suffixes)]

    universe = [t for t in universe if not is_excluded(t)[0]]
    print(f"PDMR scrape across {len(universe)} European tickers", file=sys.stderr)

    out_path = Path(args.out)
    results: dict = {}
    if out_path.exists():
        try:
            results = json.loads(out_path.read_text())
        except Exception:
            results = {}

    n_signal = 0
    for i, tk in enumerate(universe, 1):
        if i > args.limit:
            break
        if tk in results:
            continue
        titles = fetch_news_titles(tk, max_items=args.max_items)
        s = score_titles(titles)
        results[tk] = {"ticker": tk, **s, "titles": titles[:30]}
        if s["total_signal_count"] > 0:
            n_signal += 1
        if i % 25 == 0:
            print(f"  [{i}/{len(universe)}] {tk}  pdmr={s['pdmr_count']} "
                  f"buyback={s['buyback_count']} (cumulative signal={n_signal})",
                  file=sys.stderr, flush=True)
            out_path.write_text(json.dumps(results, indent=2, default=str))
        time.sleep(args.sleep)

    out_path.write_text(json.dumps(results, indent=2, default=str))

    # Rank by total_signal_count
    ranked = sorted(
        ((tk, d) for tk, d in results.items() if d.get("total_signal_count", 0) > 0),
        key=lambda kv: kv[1]["total_signal_count"], reverse=True,
    )
    print(f"\nDone. {n_signal} tickers with at least one PDMR/buyback signal\n",
          file=sys.stderr)
    print(f"{'#':<3}{'TKR':<11}{'PDMR':>5}{'DIR':>5}{'BB':>5}{'TOT':>5}  EXAMPLE HEADLINE")
    print("-" * 130)
    for i, (tk, d) in enumerate(ranked[:50], 1):
        ex = (d.get("hits") or [""])[0][:80]
        print(f"{i:<3}{tk:<11}{d.get('pdmr_count', 0):>5}"
              f"{d.get('buy_directional_count', 0):>5}"
              f"{d.get('buyback_count', 0):>5}"
              f"{d.get('total_signal_count', 0):>5}  {ex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
