"""Fetch a batch of N US tickers (or any region) for info_metrics and exit.

Short-lived so the supervisor wrapping it can restart freely. Saves what
it gets and exits 0; saves nothing and exits 1 if the batch is fully
throttled (so the supervisor can back off).
"""
from __future__ import annotations
import argparse, time, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf

CACHE = Path('.cache/yf')
CACHE.mkdir(parents=True, exist_ok=True)

KEEP = (
    'marketCap','currentPrice','sharesOutstanding','totalCash','totalDebt',
    'bookValue','trailingPE','forwardPE','priceToBook','priceToSalesTrailing12Months',
    'enterpriseToEbitda','enterpriseToRevenue','enterpriseValue',
    'trailingEps','freeCashflow','operatingCashflow','totalRevenue','ebitda',
    'debtToEquity','currentRatio','quickRatio',
    'returnOnEquity','returnOnAssets','grossMargins','operatingMargins','profitMargins',
    'revenueGrowth','earningsGrowth','earningsQuarterlyGrowth','ebitdaMargins',
    'dividendYield','payoutRatio','beta','heldPercentInsiders','heldPercentInstitutions',
    'sector','industry','country','longName','shortName','currency',
)


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def info_cached(tk, max_age_days=10):
    p = CACHE / f'{safe(tk)}__info_metrics.parquet'
    if not p.exists(): return False
    age = (time.time() - p.stat().st_mtime) / 86400
    return age < max_age_days


def fetch_one(tk, sleep_s=0.5):
    p = CACHE / f'{safe(tk)}__info_metrics.parquet'
    try:
        if sleep_s > 0: time.sleep(sleep_s)
        info = yf.Ticker(tk).info or {}
        if not info or (info.get('regularMarketPrice') is None
                        and info.get('currentPrice') is None
                        and info.get('marketCap') is None):
            return False
        rec = {k: info.get(k) for k in KEEP}
        rec['_fetched_at'] = int(time.time())
        rec['_ticker'] = tk
        pd.DataFrame([rec]).to_parquet(p, index=False)
        return True
    except Exception:
        return False


def priority_universe(region: str):
    """Return tickers ordered by cap tier (Mega -> Large -> Mid -> Small)
    so the most meaningful names get fetched first."""
    import financedatabase as fd
    e = fd.Equities()
    country_map = {
        'US': 'United States', 'JP': 'Japan', 'KR': 'South Korea',
        'HK': 'Hong Kong', 'AU': 'Australia', 'CA': 'Canada',
        'GB': 'United Kingdom', 'DE': 'Germany', 'FR': 'France', 'SE': 'Sweden',
    }
    suff_map = {
        'US': [None], 'JP': ['.T'], 'KR': ['.KS','.KQ'], 'HK': ['.HK'],
        'AU': ['.AX'], 'CA': ['.TO','.V'], 'GB': ['.L'], 'DE': ['.DE','.F'],
        'FR': ['.PA'], 'SE': ['.ST'],
    }
    country = country_map[region]
    suffs = suff_map[region]
    seen = set()
    ordered = []
    for cap in ('Mega Cap','Large Cap','Mid Cap','Small Cap'):
        try:
            df = e.select(country=country, market_cap=cap)
            if df is None or df.empty: continue
            for s in df.index.astype(str):
                s = s.upper()
                if region == 'US':
                    if '.' in s: continue
                    if s in seen: continue
                else:
                    if not s.endswith(tuple(suffs)): continue
                    if s in seen: continue
                seen.add(s); ordered.append(s)
        except Exception: pass
    return ordered


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--region', required=True)
    ap.add_argument('--batch', type=int, default=100)
    ap.add_argument('--workers', type=int, default=1)
    ap.add_argument('--sleep', type=float, default=0.6)
    args = ap.parse_args()

    # Cap-tier-ordered universe so the meaningful names come first.
    sys.path.insert(0, '.')
    full_uni = priority_universe(args.region)
    # Filter US junk via the same filter the screener uses (warrants, preferreds)
    if args.region == 'US':
        from per_region_rank import build_universe
        clean = set(build_universe('US', 100000))
        full_uni = [t for t in full_uni if t in clean]
    todo = [t for t in full_uni if not info_cached(t)]
    if not todo:
        print(f'[{args.region}] no new tickers to fetch')
        sys.exit(0)
    batch = todo[:args.batch]
    print(f'[{args.region}] {len(todo)} remaining; fetching batch of {len(batch)}')

    ok = fail = 0
    t0 = time.time()
    if args.workers <= 1:
        for tk in batch:
            if fetch_one(tk, args.sleep): ok += 1
            else: fail += 1
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for fut in as_completed({ex.submit(fetch_one, t, args.sleep): t for t in batch}):
                if fut.result(): ok += 1
                else: fail += 1
    el = time.time() - t0
    rate = ok / max(1, el)
    pct = ok / max(1, len(batch)) * 100
    print(f'[{args.region}] batch done: ok={ok} fail={fail} pct={pct:.0f}% rate={rate:.2f}/s in {el:.0f}s')
    # Exit 1 if fully throttled so the supervisor knows
    if ok == 0 and len(batch) >= 50:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
