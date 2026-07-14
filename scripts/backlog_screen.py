#!/usr/bin/env python3
"""Backlog-inflection screener.

Pulls remaining performance obligations / deferred revenue / order backlog
series (quarterly) from SEC EDGAR and detects inflections — when backlog
growth is accelerating after a flat/declining period. These are LEADING
indicators of future revenue inflections.

Backlog concept tags tried (in order):
  • us-gaap:RemainingPerformanceObligation  (most common, post-ASC 606)
  • us-gaap:RevenueRemainingPerformanceObligation
  • us-gaap:ContractWithCustomerLiability      (deferred revenue under ASC 606)
  • us-gaap:ContractWithCustomerLiabilityCurrent
  • us-gaap:DeferredRevenue                    (pre-ASC 606)
  • us-gaap:DeferredRevenueCurrent
  • us-gaap:OrderOrProductionBacklog

Outputs per ticker:
  • backlog_concept_used (which tag)
  • backlog_latest, backlog_latest_date
  • backlog_yoy_pct, backlog_qoq_pct
  • backlog_growth_4q_mean (last 4 quarters' YoY)
  • backlog_growth_8q_mean (8 quarters)
  • backlog_inflection_pp = recent_growth − prior_growth (positive = accelerating)
  • backlog_inflection_flag = inflection_pp >= 10pp AND recent_growth > 0
  • backlog_to_rev_ratio (if revenue available — book-to-bill proxy)
"""
import argparse, sys, time, threading, warnings, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import requests

warnings.filterwarnings('ignore')

UA = "cyclepapa research cm2whv9sg2@privaterelay.appleid.com"
BACKLOG_TAGS = [
    'RemainingPerformanceObligation',
    'RevenueRemainingPerformanceObligation',
    'ContractWithCustomerLiability',
    'ContractWithCustomerLiabilityCurrent',
    'DeferredRevenue',
    'DeferredRevenueCurrent',
    'OrderOrProductionBacklog',
]


class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.next_ok = 0.0
    def wait(self):
        with self.lock:
            now = time.time()
            if now < self.next_ok:
                time.sleep(self.next_ok - now); now = time.time()
            self.next_ok = now + self.interval


def get_ticker_to_cik(path='/tmp/sec_tickers.json'):
    if not os.path.exists(path):
        r = requests.get('https://www.sec.gov/files/company_tickers.json',
                         headers={'User-Agent': UA}, timeout=30)
        r.raise_for_status()
        open(path, 'w').write(r.text)
    with open(path) as f:
        d = json.load(f)
    return {v['ticker'].upper(): int(v['cik_str']) for v in d.values()}


def fetch_concept(cik, tag, session, limiter, max_retries=3):
    """Pull one XBRL concept time series for a given CIK."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"
    for attempt in range(max_retries):
        limiter.wait()
        try:
            r = session.get(url, headers={'User-Agent': UA}, timeout=30)
            if r.status_code == 404: return None          # genuine: no such concept for this filer
            if r.status_code == 429:
                time.sleep(2 ** attempt * 3); continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt); continue
            return 'ERROR'                                 # transient: retries exhausted, do NOT mark done
    return 'ERROR'                                         # 429 loop exhausted


def extract_quarterly_series(concept_json, unit='USD'):
    """From a concept JSON, build a quarterly point-in-time time series.
    Returns sorted list of (date, value) by date asc.
    """
    if not concept_json: return []
    units = concept_json.get('units', {})
    data = units.get(unit) or next(iter(units.values()), [])
    # Take instant point-in-time values (balance-sheet-like) from 10-Q or 10-K
    series = {}
    for d in data:
        form = d.get('form', '')
        # Include 6-K: foreign private issuers file interim RPO/deferred-rev data there.
        if form not in ('10-K','10-Q','10-K/A','10-Q/A','20-F','40-F','20-F/A','40-F/A','6-K'): continue
        end = d.get('end', '')
        val = d.get('val')
        if val is None: continue
        # Prefer latest filing for each end date
        if end not in series or d.get('filed','') > series[end][1]:
            series[end] = (float(val), d.get('filed',''))
    return [(e, v[0]) for e, v in sorted(series.items())]


def compute_inflection(series):
    """Given list of (date, value) sorted asc, compute QoQ/YoY growth +
    inflection signal."""
    if not series or len(series) < 5: return {}
    df = pd.DataFrame(series, columns=['date','val'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    out = {
        'backlog_latest': float(df['val'].iloc[-1]),
        'backlog_latest_date': df['date'].iloc[-1].strftime('%Y-%m-%d'),
        'backlog_quarters_history': len(df),
    }
    # QoQ
    if len(df) >= 2 and df['val'].iloc[-2] > 0:
        out['backlog_qoq_pct'] = (df['val'].iloc[-1] / df['val'].iloc[-2] - 1) * 100
    # YoY
    if len(df) >= 5 and df['val'].iloc[-5] > 0:
        out['backlog_yoy_pct'] = (df['val'].iloc[-1] / df['val'].iloc[-5] - 1) * 100
    # Rolling 4q/8q YoY growth (mean of last N YoY values)
    yoy_series = []
    for i in range(4, len(df)):
        prev = df['val'].iloc[i-4]
        if prev > 0:
            yoy_series.append((df['val'].iloc[i] / prev - 1) * 100)
    if len(yoy_series) >= 1:
        out['backlog_growth_latest_yoy'] = yoy_series[-1]
    if len(yoy_series) >= 4:
        out['backlog_growth_4q_mean'] = float(np.mean(yoy_series[-4:]))
    if len(yoy_series) >= 8:
        out['backlog_growth_8q_mean'] = float(np.mean(yoy_series[-8:]))

    # Inflection: latest 2-quarter avg YoY growth vs prior 4q avg
    if len(yoy_series) >= 6:
        recent = float(np.mean(yoy_series[-2:]))
        prior  = float(np.mean(yoy_series[-6:-2]))
        out['backlog_inflection_pp'] = recent - prior
        out['backlog_inflection_flag'] = bool((recent - prior) >= 10 and recent > 0)
    return out


def fetch_one(ticker, cik, session, limiter, rev_lookup=None):
    """Try each backlog concept until one returns data."""
    result = {'ticker': ticker, 'cik': cik, 'backlog_concept_used': None}
    any_error = False
    for tag in BACKLOG_TAGS:
        cj = fetch_concept(cik, tag, session, limiter)
        if cj == 'ERROR':
            any_error = True; continue      # transient failure — don't treat as "no data"
        if cj is None: continue              # genuine 404: this filer lacks this concept
        series = extract_quarterly_series(cj)
        if len(series) < 5: continue  # need at least 5 quarters
        m = compute_inflection(series)
        if m:
            result.update(m)
            result['backlog_concept_used'] = tag
            break
    if result.get('backlog_concept_used') is None:
        # If we found nothing AND some request errored transiently, signal a retry
        # (return None) so the ticker is NOT written as a done no-backlog row.
        if any_error:
            return None
        return result  # genuinely no backlog data (all 404s)

    # Book-to-bill / backlog-to-revenue
    if rev_lookup and ticker in rev_lookup:
        rev = rev_lookup[ticker]
        if rev and rev > 0:
            result['backlog_to_rev_ratio'] = result['backlog_latest'] / rev
    return result


ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--workers', type=int, default=8)
ap.add_argument('--rate', type=float, default=8.0)
ap.add_argument('--checkpoint', type=int, default=200)
ap.add_argument('--resume', action='store_true')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).str.upper().unique().tolist()

t2c = get_ticker_to_cik()
todo = [(s, t2c[s]) for s in syms if s in t2c]
print(f"[backlog] {len(todo)} tickers have CIK", file=sys.stderr)

# Build revenue lookup from edgar combined file
rev_lookup = {}
edgar_path = 'data/research/roic_edgar_combined.csv'
if os.path.exists(edgar_path):
    e = pd.read_csv(edgar_path)
    if 'rev_latest' in e.columns and 'ticker' in e.columns:
        rev_lookup = dict(zip(e['ticker'].str.upper(), e['rev_latest']))
    print(f"[backlog] revenue lookup: {len(rev_lookup)} tickers", file=sys.stderr)

already = set(); existing = []
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 10:
    try:
        prev = pd.read_csv(args.out)
        already = set(prev['ticker'].dropna().astype(str).tolist())
        existing = prev.to_dict('records')
        print(f"[backlog] resume: {len(already)} done", file=sys.stderr)
    except Exception: pass

todo = [(s, c) for s, c in todo if s not in already]
print(f"[backlog] todo: {len(todo)} · {args.workers}w @ {args.rate}/s · ETA ~{len(todo)*len(BACKLOG_TAGS)/args.rate/60:.0f}m (max if all tags tried)", file=sys.stderr)

session = requests.Session()
session.verify = '/root/.ccr/ca-bundle.crt' if os.path.exists('/root/.ccr/ca-bundle.crt') else True
limiter = RateLimiter(args.rate)
rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

def task(item):
    t, c = item
    r = fetch_one(t, c, session, limiter, rev_lookup=rev_lookup)
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            elapsed = time.time() - start; rate = done[0] / max(elapsed, 0.1)
            eta = (len(todo) - done[0]) / max(rate, 0.01) / 60
            print(f"[backlog] {done[0]}/{len(todo)} kept {len(rows)-len(existing)} rate {rate:.2f}/s ETA {eta:.1f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = [ex.submit(task, x) for x in todo]
    for _ in as_completed(futures): pass

pd.DataFrame(rows).to_csv(args.out, index=False)
df = pd.DataFrame(rows)
if len(df):
    print(f"[backlog] DONE: {len(df)} rows", file=sys.stderr)
    has_data = df[df['backlog_concept_used'].notna()] if 'backlog_concept_used' in df.columns else df
    print(f"  with backlog data: {len(has_data)}", file=sys.stderr)
    if 'backlog_inflection_flag' in has_data.columns:
        print(f"  INFLECTING: {int(has_data['backlog_inflection_flag'].fillna(False).sum())}", file=sys.stderr)
    if 'backlog_concept_used' in has_data.columns:
        print(f"  concepts used: {has_data['backlog_concept_used'].value_counts().to_dict()}", file=sys.stderr)
