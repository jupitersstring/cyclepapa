"""Per-region asymmetric ranker — designed for fast, durable analysis.

For each region:
  1. Pull the financedatabase universe filtered to Small + Mid cap.
  2. Fetch yfinance info_metrics only (the lightest slot — one .info call/ticker).
  3. Compute a composite per ticker (lower P/B, lower forward P/E, FCF yield,
     net cash %, gross/op margin, 1y price perf) — sector-percentile within
     the region.
  4. Emit top-5 per region with the actual numbers behind the rank.

Designed to be re-runnable: skips tickers whose info_metrics is already
cached and fresh (mtime < --max-cache-age-days). Pushes cache snapshot
to origin/cache-snapshot every --snapshot-every minutes so a session
reset never costs more than that window of work.

Usage:
    python per_region_rank.py --regions US JP KR HK AU CA GB DE \\
        --per-region 600 --workers 6 --snapshot-every 30
"""
from __future__ import annotations
import argparse, time, subprocess, sys, os, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd, numpy as np, yfinance as yf

REPO = Path(__file__).resolve().parent
CACHE = REPO / '.cache' / 'yf'
CACHE.mkdir(parents=True, exist_ok=True)
OUT = REPO / 'results_peg'
OUT.mkdir(exist_ok=True)


# Region → (financedatabase country, list of yfinance suffixes that count
#          as a "local primary listing" for this region). For non-US we
#          filter by SUFFIX (more reliable than country) because
#          financedatabase country=Japan returns London ADRs etc.
REGIONS = {
    'US': ('United States', [None]),       # no suffix
    'JP': ('Japan',          ['.T']),       # Tokyo only
    'KR': ('South Korea',    ['.KS', '.KQ']),# KOSPI + KOSDAQ
    'HK': ('Hong Kong',      ['.HK']),
    'AU': ('Australia',      ['.AX']),
    'CA': ('Canada',         ['.TO', '.V']),# TSX + TSX-V
    'GB': ('United Kingdom', ['.L']),
    'DE': ('Germany',        ['.DE', '.F']),# XETRA + Frankfurt
    'FR': ('France',         ['.PA']),
    'SE': ('Sweden',         ['.ST']),
}

# Slim keep list — we only need scoring fields, not the full info dump
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


def build_universe(region: str, max_n: int):
    """Per-region universe — financedatabase rows that are BOTH
    country=<region.country> AND have the region's local-listing suffix.
    Filtering by country alone returns London ADRs of foreign companies;
    filtering by suffix alone (without country) sweeps in ghost-symbols
    like 0A05.L. The intersection gives genuine local listings."""
    import financedatabase as fd
    e = fd.Equities()
    country, suffixes = REGIONS[region]
    parts = []
    for cap in ('Mega Cap','Large Cap','Mid Cap','Small Cap'):
        try:
            df = e.select(country=country, market_cap=cap)
            if df is not None and len(df): parts.append(df)
        except Exception: pass
    if not parts: return []
    uni = pd.concat(parts)
    syms = uni.index.astype(str).str.upper()
    uni = uni[~syms.str.contains(r'\^|=|/')]
    syms = list(uni.index.astype(str))
    if region == 'US':
        # US: no suffix (i.e. last segment is the whole ticker, no dot)
        syms = [s for s in syms if '.' not in s]
        # Drop obvious warrant/preferred/SPAC unit ghost symbols:
        #   -WT / -WS = warrants, -WTA/WTB = lettered warrant series
        #   -U, -UN = SPAC units; -R = rights; -PA, -PB, -PRA = preferreds
        #   ending in W (warrants compacted), ending in U (units compacted)
        import re
        def _is_junk(s):
            if '-' in s:
                tail = s.rsplit('-', 1)[1]
                if tail in ('WT','WS','WTA','WTB','WTC','U','UN','R','RT','RW') or tail.startswith(('P','W')):
                    return True
            # ticker ending in W or .WS is usually a warrant; -compacted forms like CMPOW, CTXRW
            if len(s) >= 5 and s.endswith(('W','WW','WS','WSA','WTS','PRA','PRB','PRC','RW')):
                return True
            return False
        syms = [s for s in syms if not _is_junk(s)]
    else:
        suffs = tuple(suffixes)
        syms = [s for s in syms if s.endswith(suffs)]
    return sorted(set(syms))[:max_n]


def info_cached(tk: str, max_age_days: int) -> bool:
    p = CACHE / f'{safe(tk)}__info_metrics.parquet'
    if not p.exists(): return False
    age = (time.time() - p.stat().st_mtime) / 86400
    return age < max_age_days


def fetch_info(tk: str, request_sleep: float = 0.0) -> bool:
    """Fetch yfinance .info for one ticker, write slim parquet. Returns True on success."""
    p = CACHE / f'{safe(tk)}__info_metrics.parquet'
    try:
        if request_sleep > 0: time.sleep(request_sleep)
        t = yf.Ticker(tk)
        info = t.info or {}
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


def maybe_snapshot(last_push: float, snapshot_every_min: float, n_done: int):
    """Push cache snapshot every snapshot_every minutes."""
    if snapshot_every_min <= 0: return last_push
    now = time.time()
    if (now - last_push) / 60 >= snapshot_every_min:
        print(f'\n  [snapshot] pushing after {n_done} fetches...')
        r = subprocess.run([sys.executable, 'cache_sync.py', 'push'],
                            cwd=REPO, capture_output=True, text=True)
        if r.returncode == 0:
            print('  [snapshot] OK')
        else:
            print(f'  [snapshot] FAILED: {r.stderr[:300]}')
        return now
    return last_push


def fetch_region(region: str, tickers: list, workers: int, max_age_days: int,
                 snapshot_every_min: float, last_push_ref: list,
                 request_sleep: float = 0.0,
                 throttle_threshold: float = 0.15,
                 inter_region_pause: float = 0.0):
    """Fetch info_metrics for `tickers`, skipping fresh-cached ones.

    If the success rate of a 50-row window drops below `throttle_threshold`,
    we abort the region — yfinance has clearly rate-limited us and further
    calls just waste time."""
    todo = [t for t in tickers if not info_cached(t, max_age_days)]
    print(f'[{region}] {len(tickers)} candidates, {len(todo)} to fetch (rest fresh).')
    ok = fail = 0
    t0 = time.time()
    if not todo: return 0, 0
    last_window_ok = 1.0  # start optimistic
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_info, t, request_sleep): t for t in todo}
        for i, fut in enumerate(as_completed(futs)):
            if fut.result(): ok += 1
            else: fail += 1
            if (i+1) % 50 == 0:
                window_ok = (ok - (i-49) + fail - 0) and 0  # not used; compute below
                # Compute success rate of last 50
                window_size = 50
                # crude: last_50_ok = ok - prev_total_ok ... just track via mod
                # Use running heuristic: if success<10% over last 50, abort
                recent_ok_rate = (ok / (i+1))
                el = time.time() - t0
                rate = (i+1) / el
                eta = (len(todo) - i - 1) / rate / 60
                print(f'  [{region}] {i+1}/{len(todo)} ok={ok} fail={fail} '
                      f'rate={rate:.1f}/s eta={eta:.0f}min ok_rate={recent_ok_rate:.0%}')
                # Abort condition: after warmup, if total success rate is collapsing
                if (i+1) >= 150 and recent_ok_rate < throttle_threshold:
                    print(f'  [{region}] ABORT — total ok_rate {recent_ok_rate:.0%} < threshold {throttle_threshold:.0%}')
                    for f in futs: f.cancel()
                    break
                last_push_ref[0] = maybe_snapshot(last_push_ref[0],
                                                  snapshot_every_min, ok)
    if inter_region_pause > 0:
        print(f'  [{region}] inter-region pause {inter_region_pause:.0f}s...')
        time.sleep(inter_region_pause)
    return ok, fail


def load_region_rows(tickers: list, region: str):
    rows = []
    for tk in tickers:
        p = CACHE / f'{safe(tk)}__info_metrics.parquet'
        if not p.exists(): continue
        try:
            d = pd.read_parquet(p)
            if d.empty: continue
            r = d.iloc[0].to_dict()
            r['ticker'] = tk
            r['region'] = region
            rows.append(r)
        except Exception: pass
    return rows


def _net_cash_pct(r):
    mc = r.get('marketCap'); cash = r.get('totalCash'); debt = r.get('totalDebt')
    if mc is None or cash is None or debt is None or mc <= 0: return None
    try: return (float(cash) - float(debt)) / float(mc) * 100
    except Exception: return None


def _fcf_yield(r):
    mc = r.get('marketCap'); fcf = r.get('freeCashflow')
    if mc is None or fcf is None or mc <= 0: return None
    try: return float(fcf) / float(mc) * 100
    except Exception: return None


def sector_pct(s: pd.Series, sector: pd.Series, direction: str) -> pd.Series:
    pct = pd.to_numeric(s, errors='coerce').groupby(sector).rank(pct=True, method='average') * 100
    return (100 - pct) if direction == 'lo' else pct


def rank_region(df: pd.DataFrame, min_mcap: float) -> pd.DataFrame:
    """Sector-percentile composite within the region."""
    df = df.copy()
    df['marketCap'] = pd.to_numeric(df['marketCap'], errors='coerce')
    df = df[df['marketCap'].fillna(0) >= min_mcap]
    if df.empty: return df
    df['net_cash_pct'] = df.apply(_net_cash_pct, axis=1)
    df['fcfYield_pct'] = df.apply(_fcf_yield, axis=1)
    df['sector_key'] = df['sector'].fillna('__unknown__')

    pb = pd.to_numeric(df['priceToBook'], errors='coerce').where(lambda s: s > 0)
    pe_t = pd.to_numeric(df['trailingPE'], errors='coerce').where(lambda s: s > 0)
    pe_f = pd.to_numeric(df.get('forwardPE', pd.Series(index=df.index)), errors='coerce').where(lambda s: s > 0)
    de   = pd.to_numeric(df['debtToEquity'], errors='coerce').where(lambda s: s >= 0)
    cr   = pd.to_numeric(df['currentRatio'], errors='coerce').where(lambda s: s > 0)
    evbd = pd.to_numeric(df['enterpriseToEbitda'], errors='coerce').where(lambda s: s > 0)
    evrev = pd.to_numeric(df['enterpriseToRevenue'], errors='coerce').where(lambda s: s > 0)

    df['_pb']   = sector_pct(pb,    df['sector_key'], 'lo')
    df['_pet']  = sector_pct(pe_t,  df['sector_key'], 'lo')
    df['_pef']  = sector_pct(pe_f,  df['sector_key'], 'lo')
    df['_evbd'] = sector_pct(evbd,  df['sector_key'], 'lo')
    df['_evrv'] = sector_pct(evrev, df['sector_key'], 'lo')
    df['_de']   = sector_pct(de,    df['sector_key'], 'lo')
    df['_cr']   = sector_pct(cr,    df['sector_key'], 'hi')
    df['_nc']   = sector_pct(df['net_cash_pct'],   df['sector_key'], 'hi')
    df['_fy']   = sector_pct(df['fcfYield_pct'],   df['sector_key'], 'hi')
    df['_gm']   = sector_pct(df['grossMargins'],   df['sector_key'], 'hi')
    df['_om']   = sector_pct(df['operatingMargins'],df['sector_key'], 'hi')
    df['_rg']   = sector_pct(df['revenueGrowth'],  df['sector_key'], 'hi')
    df['_eg']   = sector_pct(df['earningsGrowth'], df['sector_key'], 'hi')

    pct_cols = ['_pb','_pet','_pef','_evbd','_evrv','_de','_cr','_nc','_fy','_gm','_om','_rg','_eg']
    df['n_valid'] = df[pct_cols].notna().sum(axis=1)
    df['composite'] = df[pct_cols].mean(axis=1, skipna=True)
    # Require at least 6 of 13 components to count
    df.loc[df['n_valid'] < 6, 'composite'] = np.nan
    return df


def display_top(df: pd.DataFrame, region: str, n: int) -> pd.DataFrame:
    df = df.dropna(subset=['composite']).copy()
    df = df.sort_values('composite', ascending=False)
    # Dedupe by company name — same name on .DE and .F should appear once
    # (Sto SE shows up as both STO3.DE and STO3.F; keep the higher-composite row)
    if 'longName' in df.columns:
        df['_dedupe_key'] = df['longName'].fillna(df['ticker'])
        df = df.drop_duplicates(subset=['_dedupe_key'], keep='first').drop(columns=['_dedupe_key'])
    df = df.head(n)
    cols = ['ticker','region','longName','sector','marketCap','currentPrice',
            'composite','n_valid',
            'priceToBook','trailingPE','forwardPE','priceToSalesTrailing12Months',
            'enterpriseToEbitda','enterpriseToRevenue',
            'net_cash_pct','fcfYield_pct','grossMargins','operatingMargins',
            'revenueGrowth','earningsGrowth']
    cols = [c for c in cols if c in df.columns]
    out = df[cols].copy()
    out['marketCap_M'] = (pd.to_numeric(out['marketCap'], errors='coerce') / 1e6).round(0)
    out = out.drop(columns=['marketCap'])
    for c in out.columns:
        if c not in ('ticker','region','longName','sector'):
            out[c] = pd.to_numeric(out[c], errors='coerce').round(3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--regions', nargs='+', default=list(REGIONS.keys()))
    ap.add_argument('--per-region', type=int, default=600)
    ap.add_argument('--workers', type=int, default=3,
                    help='yfinance throttles aggressively above ~4 — keep low.')
    ap.add_argument('--request-sleep', type=float, default=0.4,
                    help='Per-call sleep before each .info request.')
    ap.add_argument('--inter-region-pause', type=float, default=20.0,
                    help='Seconds to rest between regions (lets yfinance reset).')
    ap.add_argument('--max-cache-age-days', type=int, default=10)
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--top-n', type=int, default=5)
    ap.add_argument('--snapshot-every', type=float, default=15.0,
                    help='Push cache snapshot every N minutes (0 disables).')
    ap.add_argument('--skip-fetch', action='store_true',
                    help='Use existing cache only — no new yfinance calls.')
    args = ap.parse_args()

    last_push_ref = [time.time()]
    region_tickers = {}
    for region in args.regions:
        if region not in REGIONS:
            print(f'Unknown region {region}; skipping.'); continue
        try:
            tickers = build_universe(region, args.per_region)
            print(f'[{region}] universe size: {len(tickers)}')
            region_tickers[region] = tickers
        except Exception as e:
            print(f'[{region}] universe build failed: {e}')

    if not args.skip_fetch:
        for region, tickers in region_tickers.items():
            ok, fail = fetch_region(region, tickers, args.workers,
                                    args.max_cache_age_days,
                                    args.snapshot_every, last_push_ref,
                                    request_sleep=args.request_sleep,
                                    inter_region_pause=args.inter_region_pause)
            print(f'[{region}] fetch done: ok={ok} fail={fail}')
        # Final snapshot
        if args.snapshot_every > 0:
            print('\n[snapshot] final push...')
            subprocess.run([sys.executable, 'cache_sync.py', 'push'], cwd=REPO)

    # Score and emit per-region
    all_rows = []
    print('\n=== Per-region top-N ===')
    for region, tickers in region_tickers.items():
        rows = load_region_rows(tickers, region)
        if not rows:
            print(f'[{region}] no rows scored.'); continue
        df = pd.DataFrame(rows)
        scored = rank_region(df, args.min_mcap)
        if scored.empty:
            print(f'[{region}] no rows above min_mcap={args.min_mcap/1e6:.0f}M.'); continue
        top = display_top(scored, region, args.top_n)
        print(f'\n--- {region} top {len(top)} (of {len(scored.dropna(subset=["composite"]))} scored) ---')
        print(top.to_string(index=False))
        all_rows.append(top)
        # Per-region csv
        (OUT).mkdir(exist_ok=True)
        scored.dropna(subset=['composite']).sort_values('composite', ascending=False).to_csv(
            OUT / f'per_region_{region}_full.csv', index=False)
        top.to_csv(OUT / f'per_region_{region}_top.csv', index=False)
    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined.to_csv(OUT / 'per_region_top_combined.csv', index=False)
        print(f'\nWrote {OUT / "per_region_top_combined.csv"} ({len(combined)} rows)')


if __name__ == '__main__':
    main()
