"""PSU asymmetry pipeline.

Usage:
    python psu_pipeline.py --tickers tickers.txt --out psu_scorecard.csv
    python psu_pipeline.py --tickers tickers.txt --json details.json --top 20

Pipeline:
    ticker -> latest DEF 14A (EDGAR) -> plain text
           -> compensation section
           -> PSU pattern features
           -> alignment / upside / asymmetry scores
           -> ranked CSV (+ optional JSON dump with raw snippets)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import yfinance as yf

import cache
from edgar import latest_def14a, fetch_filing_html, Filing
from proxy import html_to_text, extract_comp_section
from psu_scoring import extract_features, score
from recent import recent_def14a, recent_def14a_range, RecentFiling


def current_price(ticker: str) -> float | None:
    cached = cache.get_price(ticker)
    if cached is not None:
        return cached
    try:
        t = yf.Ticker(ticker)
        info = getattr(t, "fast_info", None)
        if info is not None:
            for k in ("last_price", "lastPrice", "regular_market_price"):
                v = info.get(k) if hasattr(info, "get") else getattr(info, k, None)
                if v:
                    cache.put_price(ticker, float(v))
                    return float(v)
        full = t.info or {}
        for k in ("currentPrice", "regularMarketPrice", "previousClose"):
            v = full.get(k)
            if v:
                cache.put_price(ticker, float(v))
                return float(v)
    except Exception:
        return None
    return None


def _fetch_url(url: str) -> str:
    from edgar import _get
    return _get(url).text


def _fetch_doc_cached(accession: str, url: str) -> str:
    """Return the filing's raw HTML, hitting disk cache first."""
    cached = cache.get_doc(accession)
    if cached is not None:
        return cached
    html = _fetch_url(url)
    cache.put_doc(accession, html)
    return html


def run_one(ticker: str) -> dict:
    out: dict = {"ticker": ticker.upper()}
    try:
        filing = latest_def14a(ticker)
    except Exception as e:
        out["error"] = f"edgar_lookup: {e}"
        return out
    if filing is None:
        out["error"] = "no DEF 14A found"
        return out
    return _process_filing(ticker, filing)


def _process_filing(ticker: str, filing, use_cache: bool = True) -> dict:
    """Common path: given a Filing or RecentFiling, score it."""
    accession = getattr(filing, "accession", None)
    if use_cache and accession:
        cached = cache.get_score(accession)
        if cached is not None:
            return cached

    out: dict = {"ticker": ticker.upper()}
    out["filing_date"] = filing.filing_date
    out["filing_url"] = filing.url
    try:
        if accession and use_cache:
            html = _fetch_doc_cached(accession, filing.url)
        else:
            html = fetch_filing_html(filing) if isinstance(filing, Filing) else _fetch_url(filing.url)
    except Exception as e:
        out["error"] = f"fetch: {e}"
        return out

    text = html_to_text(html)
    comp = extract_comp_section(text)
    feats = extract_features(ticker, comp)
    px = current_price(ticker)

    sc = score(feats, px)

    out.update(
        current_price=px,
        has_psu_program=feats.has_psu_program,
        aggregate_metrics=feats.aggregate_metrics,
        per_share_metrics=feats.per_share_metrics,
        stock_price_hurdles=feats.stock_price_hurdles,
        discretionary_language=feats.discretionary_language,
        retirement_language=feats.retirement_language,
        repricing_language=feats.repricing_language,
        front_loaded_language=feats.front_loaded_language,
        alignment=sc.alignment,
        upside_kicker=sc.upside_kicker,
        transformation_signal=sc.transformation_signal,
        asymmetry=sc.asymmetry,
        flags=sc.flags,
        snippet=feats.snippet[:1200],
    )
    if accession and use_cache:
        cache.put_score(accession, out)
    return out


def _fmt_list(v) -> str:
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return v if v is not None else ""


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "filing_date", "current_price",
        "asymmetry", "alignment", "upside_kicker", "transformation_signal",
        "has_psu_program",
        "per_share_metrics", "aggregate_metrics", "stock_price_hurdles",
        "discretionary_language", "retirement_language",
        "repricing_language", "front_loaded_language",
        "flags", "filing_url", "error",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = r.copy()
            for k in ("aggregate_metrics", "per_share_metrics",
                      "stock_price_hurdles", "flags"):
                if k in row:
                    row[k] = _fmt_list(row[k])
            w.writerow(row)


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Screen US-listed companies for asymmetric Performance Share "
            "Unit (PSU) setups. Reads the latest DEF 14A from SEC EDGAR, "
            "parses the compensation section, and scores each grant on "
            "alignment + OTM kicker + override/milking risk."
        )
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--tickers",
                     help="File with one ticker per line (# comments OK).")
    src.add_argument("--recent", type=int,
                     help="Pull the N most recently filed DEF 14A proxies "
                          "from EDGAR's getcurrent feed.")
    src.add_argument("--days", type=int,
                     help="Pull every DEF 14A filed in the past N days via "
                          "EDGAR full-text search.")
    p.add_argument("--limit", type=int, default=300,
                   help="Cap on filings for --days mode (default 300).")
    p.add_argument("--out", default="psu_scorecard.csv",
                   help="Ranked CSV output path.")
    p.add_argument("--json", default=None,
                   help="Optional JSON path with full per-ticker detail incl. snippets.")
    p.add_argument("--top", type=int, default=None,
                   help="If set, also print top-N ticker / score / setup to stdout.")
    p.add_argument("--sleep", type=float, default=0.25,
                   help="Sleep between EDGAR requests (default 0.25s).")
    p.add_argument("--no-cache", action="store_true",
                   help="Bypass on-disk cache; refetch and re-score everything.")
    args = p.parse_args()

    rows: list[dict] = []
    use_cache = not args.no_cache

    if args.recent or args.days:
        if args.recent:
            print(f"Pulling {args.recent} most-recent DEF 14A from EDGAR...",
                  file=sys.stderr, flush=True)
            feed = recent_def14a(args.recent)
        else:
            from datetime import datetime, timedelta, timezone
            end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
            print(f"Pulling DEF 14A filings {start} .. {end} (limit {args.limit})...",
                  file=sys.stderr, flush=True)
            feed = recent_def14a_range(start, end, limit=args.limit)
        print(f"Got {len(feed)} filings.", file=sys.stderr)

        for i, rf in enumerate(feed, 1):
            tk = rf.ticker or rf.cik
            cached = use_cache and cache.get_score(rf.accession) is not None
            tag = "[cache]" if cached else ""
            print(f"[{i}/{len(feed)}] {tk} {rf.filing_date} {rf.company} {tag}",
                  file=sys.stderr, flush=True)
            try:
                row = _process_filing(tk, rf, use_cache=use_cache)
                row["company"] = rf.company
            except Exception as e:
                row = {"ticker": tk, "company": rf.company,
                       "error": f"unhandled: {e}"}
            rows.append(row)
            if not cached:
                time.sleep(args.sleep)
    else:
        tickers = [
            t.strip().upper()
            for t in Path(args.tickers).read_text().splitlines()
            if t.strip() and not t.strip().startswith("#")
        ]
        if not tickers:
            print("No tickers found.", file=sys.stderr)
            return 1
        for tk in tickers:
            print(f"[{tk}] processing...", file=sys.stderr, flush=True)
            try:
                row = run_one(tk)
            except Exception as e:
                row = {"ticker": tk, "error": f"unhandled: {e}"}
            rows.append(row)
            time.sleep(args.sleep)

    rows.sort(key=lambda r: r.get("asymmetry", 0) or 0, reverse=True)
    write_csv(rows, Path(args.out))

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2, default=str))

    if args.top:
        print()
        print(f"{'TICKER':<8} {'ASYM':>6} {'ALIGN':>6} {'KICK':>6}  SETUP")
        print("-" * 64)
        for r in rows[: args.top]:
            tag = "TRANSFORM" if r.get("transformation_signal") else (
                "ERROR" if r.get("error") else ""
            )
            print(
                f"{r.get('ticker',''):<8} "
                f"{r.get('asymmetry',0) or 0:>6} "
                f"{r.get('alignment',0) or 0:>6} "
                f"{r.get('upside_kicker',0) or 0:>6}  "
                f"{tag}"
            )

    print(f"\nWrote {args.out} ({len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
