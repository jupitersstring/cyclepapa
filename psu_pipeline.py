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
from event_signals import extract_event_features, score_event_stack
from special_situations import extract_special_features, score_specials
from compound_screens import run_screens
from recent import (
    recent_def14a, recent_def14a_range, recent_8k_inducement_range,
    recent_8k_restructuring_range, company_filings, RecentFiling,
)

CACHE_VERSION = "v6-bastian"


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
        if cached is not None and cached.get("_cache_version") == CACHE_VERSION:
            return cached

    out: dict = {"ticker": ticker.upper(), "_cache_version": CACHE_VERSION}
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

    # Event-driven incentive stack signals (run on the full proxy text,
    # since strategic-review / advisers / activists / ownership tables
    # often live outside the narrow comp section).
    ev = extract_event_features(ticker, text)
    market_cap = None
    try:
        import yfinance as yf  # already imported above; lazy-safe
        info = yf.Ticker(ticker).info or {}
        mc = info.get("marketCap")
        if mc:
            market_cap = float(mc)
    except Exception:
        market_cap = None
    stack = score_event_stack(ev, market_cap)

    # Bastian/Kingdom-style special-situations layer (distressed equity
    # stubs, spin-offs, cash shells, take-privates, governance resets).
    sf = extract_special_features(ticker, text)
    sp = score_specials(sf, market_cap)

    # Composite Munger score: incentive stack carries equal-or-greater
    # weight than PSU asymmetry. The archive synthesis emphasises that
    # process quality is the real edge, not just the comp structure.
    # When a hard special-situations catalyst fires, lift the composite.
    base_composite = 0.4 * (sc.asymmetry or 0) + 0.6 * stack.process_quality
    if sp.special_situations_score >= 60:
        # A strong special-sit signal can dominate; weight it 50/50 then.
        munger_composite = round(
            0.5 * base_composite + 0.5 * sp.special_situations_score, 1
        )
    else:
        munger_composite = round(
            base_composite + 0.2 * sp.special_situations_score, 1
        )

    out.update(
        current_price=px,
        market_cap=market_cap,
        # PSU comp -- preserved keys for backward-compat
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
        # Event stack
        strategic_review=stack.strategic_review,
        change_of_control=stack.change_of_control,
        buyback_score=stack.buyback,
        controller_score=stack.controller,
        activist_score=stack.activist,
        board_score=stack.board,
        financing_score=stack.financing,
        inflection_score=stack.inflection,
        majority_of_minority_score=stack.majority_of_minority,
        process_quality=stack.process_quality,
        munger_composite=munger_composite,
        # Selected event features for inspection
        has_special_committee=ev.has_special_committee,
        strategic_alts_language=ev.strategic_alts_language,
        advisers_named=ev.advisers_named,
        engaged_adviser=ev.engaged_adviser,
        activists_named=ev.activists_named,
        has_cic_table=ev.has_cic_table,
        double_trigger=ev.double_trigger,
        single_trigger=ev.single_trigger,
        buyback_authorisation_musd=ev.buyback_authorisation_musd,
        largest_owner_pct=ev.largest_owner_pct,
        insiders_group_pct=ev.insiders_group_pct,
        board_ma_keyword_count=ev.board_ma_keyword_count,
        pe_firm_count=ev.pe_firm_count,
        revolver_capacity_musd=ev.revolver_capacity_musd,
        cash_musd=ev.cash_musd,
        active_bid=ev.active_bid,
        offer_price=ev.offer_price,
        majority_of_minority=ev.majority_of_minority,
        # Bastian / Kingdom special-situations layer
        has_debt_event=sf.has_debt_event,
        debt_event_phrases=sf.debt_event_phrases,
        debt_reduced_musd=sf.debt_reduced_musd,
        participation_pct=sf.participation_pct,
        going_concern=sf.going_concern,
        creditor_board_control=sf.creditor_board_control,
        has_spinoff=sf.has_spinoff,
        has_rights_offering=sf.has_rights_offering,
        cash_shell_language=sf.cash_shell_language,
        go_private_language=sf.go_private_language,
        hidden_assets=sf.hidden_assets,
        governance_reset=sf.governance_reset,
        insider_buying_language=sf.insider_buying_language,
        catalyst_hardness=sp.catalyst_hardness,
        balance_sheet_convexity=sp.balance_sheet_convexity,
        common_preservation=sp.common_preservation,
        distressed_stub_score=sp.distressed_stub,
        spinoff_score=sp.spinoff,
        cash_shell_score=sp.cash_shell,
        take_private_score=sp.take_private,
        governance_reset_score=sp.governance_reset,
        special_situations_score=sp.special_situations_score,
        taxonomy=sp.taxonomy,
        snippet=feats.snippet[:1200],
        # Combined flags
        flags=sc.flags + stack.flags + sp.flags,
    )
    # Compound-screen overlap detection (InsideArbitrage tradition).
    out["compound_screens"] = run_screens(out)
    if accession and use_cache:
        cache.put_score(accession, out)
    return out


def _fmt_list(v) -> str:
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return v if v is not None else ""


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "ticker", "company", "filing_date", "current_price", "market_cap",
        "munger_composite", "process_quality", "asymmetry",
        "special_situations_score", "taxonomy", "compound_screens",
        "distressed_stub_score", "spinoff_score", "cash_shell_score",
        "take_private_score", "governance_reset_score",
        "catalyst_hardness", "balance_sheet_convexity", "common_preservation",
        "has_debt_event", "debt_reduced_musd", "participation_pct",
        "going_concern", "creditor_board_control",
        "has_spinoff", "has_rights_offering", "cash_shell_language",
        "go_private_language", "hidden_assets", "governance_reset",
        "insider_buying_language",
        "strategic_review", "change_of_control", "buyback_score",
        "controller_score", "activist_score", "board_score", "financing_score",
        "alignment", "upside_kicker", "transformation_signal",
        "has_special_committee", "strategic_alts_language", "engaged_adviser",
        "active_bid", "offer_price", "majority_of_minority",
        "advisers_named", "activists_named",
        "buyback_authorisation_musd", "largest_owner_pct", "insiders_group_pct",
        "revolver_capacity_musd", "cash_musd",
        "board_ma_keyword_count", "pe_firm_count",
        "has_psu_program", "per_share_metrics", "aggregate_metrics",
        "stock_price_hurdles", "discretionary_language", "retirement_language",
        "repricing_language", "front_loaded_language",
        "flags", "filing_url", "error",
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = r.copy()
            for k in ("aggregate_metrics", "per_share_metrics",
                      "stock_price_hurdles", "flags",
                      "advisers_named", "activists_named",
                      "debt_event_phrases", "compound_screens"):
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
    src.add_argument("--inducements", type=int, metavar="DAYS",
                     help="Pull 8-K Item 5.02 inducement-grant filings "
                          "from the past N days (catches new-CEO PSU "
                          "awards that aren't yet in any DEF 14A).")
    src.add_argument("--restructurings", type=int, metavar="DAYS",
                     help="Pull 8-Ks reporting debt events / "
                          "restructurings / strategic alternatives / "
                          "going-concern / spin-offs / take-privates "
                          "(Bastian / Kingdom Capital playbook universe).")
    src.add_argument("--deepdive", metavar="FILE_OR_TICKER",
                     help="Per-ticker deep-dive: pull ALL recent DEF 14A "
                          "/ 8-K / 10-K / S-8 filings for the given "
                          "ticker(s) directly via submissions JSON. "
                          "Pass a single ticker or a path to a tickers "
                          "file. No FTS guesswork -- you'll get every "
                          "fresh comp disclosure regardless of phrasing.")
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

    if args.deepdive:
        # Parse target ticker(s) from a file or single value.
        path = Path(args.deepdive)
        if path.exists():
            targets = [t.strip().upper() for t in path.read_text().splitlines()
                       if t.strip() and not t.strip().startswith("#")]
        else:
            targets = [args.deepdive.upper()]
        print(f"Deep-dive on {len(targets)} ticker(s): pulling DEF 14A / "
              f"8-K / 10-K / S-8...", file=sys.stderr, flush=True)
        feed: list[RecentFiling] = []
        for tk in targets:
            cf = company_filings(
                tk, forms=("DEF 14A", "8-K", "10-K", "S-8"),
                limit_per_form=8, days=540,
            )
            print(f"  {tk}: {len(cf)} filings", file=sys.stderr, flush=True)
            feed.extend(cf)
        for i, rf in enumerate(feed, 1):
            tk = rf.ticker or rf.cik
            cached = use_cache and cache.get_score(rf.accession) is not None
            tag = "[cache]" if cached else ""
            print(f"[{i}/{len(feed)}] {tk} {rf.filing_date} "
                  f"{rf.accession[:20]} {tag}",
                  file=sys.stderr, flush=True)
            try:
                row = _process_filing(tk, rf, use_cache=use_cache)
                row["company"] = rf.company
                row["accession"] = rf.accession
            except Exception as e:
                row = {"ticker": tk, "company": rf.company,
                       "accession": rf.accession,
                       "error": f"unhandled: {e}"}
            rows.append(row)
            if not cached:
                time.sleep(args.sleep)
    elif args.recent or args.days or args.inducements or args.restructurings:
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if args.recent:
            print(f"Pulling {args.recent} most-recent DEF 14A from EDGAR...",
                  file=sys.stderr, flush=True)
            feed = recent_def14a(args.recent)
        elif args.inducements:
            start = (datetime.now(timezone.utc) - timedelta(days=args.inducements)).strftime("%Y-%m-%d")
            print(f"Pulling 8-K inducement filings {start} .. {end} (limit {args.limit})...",
                  file=sys.stderr, flush=True)
            feed = recent_8k_inducement_range(start, end, limit=args.limit)
        elif args.restructurings:
            start = (datetime.now(timezone.utc) - timedelta(days=args.restructurings)).strftime("%Y-%m-%d")
            print(f"Pulling 8-K restructuring/strategic-alternatives filings "
                  f"{start} .. {end} (limit {args.limit})...",
                  file=sys.stderr, flush=True)
            feed = recent_8k_restructuring_range(start, end, limit=args.limit)
        else:
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

    rows.sort(key=lambda r: r.get("munger_composite") or r.get("asymmetry") or 0,
              reverse=True)
    write_csv(rows, Path(args.out))

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2, default=str))

    if args.top:
        print()
        hdr = (f"{'TICKER':<10} {'MUNGER':>6} {'PROC':>6} {'ASYM':>6} "
               f"{'STRAT':>5} {'CIC':>5} {'BUY':>5} {'CTRL':>5} {'ACT':>5} "
               f" SETUP")
        print(hdr)
        print("-" * len(hdr))
        for r in rows[: args.top]:
            tags = []
            if r.get("active_bid"): tags.append("BID")
            if r.get("has_special_committee"): tags.append("CMTE")
            if r.get("transformation_signal"): tags.append("TRANSFORM")
            if r.get("activists_named"): tags.append("ACTIVIST")
            tag = " ".join(tags) or ("ERROR" if r.get("error") else "")
            print(
                f"{r.get('ticker',''):<10} "
                f"{r.get('munger_composite',0) or 0:>6.1f} "
                f"{r.get('process_quality',0) or 0:>6.1f} "
                f"{r.get('asymmetry',0) or 0:>6.1f} "
                f"{r.get('strategic_review',0) or 0:>5.0f} "
                f"{r.get('change_of_control',0) or 0:>5.0f} "
                f"{r.get('buyback_score',0) or 0:>5.0f} "
                f"{r.get('controller_score',0) or 0:>5.0f} "
                f"{r.get('activist_score',0) or 0:>5.0f}  "
                f"{tag}"
            )

    print(f"\nWrote {args.out} ({len(rows)} rows)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
