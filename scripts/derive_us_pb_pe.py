#!/usr/bin/env python3
"""Derive P/B and P/E for US tickers from SEC EDGAR companyfacts (no Yahoo needed).

Pulls 3 facts per ticker — CommonStockSharesOutstanding, StockholdersEquity,
NetIncomeLoss — and combines with the price we already have to compute PB and PE.
SEC companyfacts is not rate-limited the way Yahoo is.

Output: data/research/derived_us_pb_pe.csv (ticker, shares, book_value, net_income,
        derived_pb, derived_pe, derived_mktCap, derived_eps)
"""
import os, sys, json, time, threading, argparse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

UA = ('cyclepapa research cm2whv9sg2@privaterelay.appleid.com (compatible; '
      'derive PB/PE script v1)')

os.environ.setdefault('REQUESTS_CA_BUNDLE', '/root/.ccr/ca-bundle.crt')
os.environ.setdefault('SSL_CERT_FILE', '/root/.ccr/ca-bundle.crt')


def fetch_companyfacts(cik):
    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    try:
        r = urllib.request.urlopen(req, timeout=15)
        data = r.read()
        if r.info().get('Content-Encoding') == 'gzip':
            import gzip
            data = gzip.decompress(data)
        return json.loads(data)
    except Exception:
        return None


def latest_annual(facts_dict, concept_keys, prefer_form='10-K'):
    """Find the latest annual value for a concept. Returns (value, period_end) or (None, None)."""
    if not facts_dict: return None, None
    us_gaap = facts_dict.get('facts', {}).get('us-gaap', {})
    dei = facts_dict.get('facts', {}).get('dei', {})
    for concept in concept_keys:
        for ns in (us_gaap, dei):
            if concept not in ns: continue
            units = ns[concept].get('units', {})
            for u in ('USD', 'shares', 'pure', 'USD/shares'):
                if u not in units: continue
                rows = units[u]
                # Prefer 10-K, then 10-K/A; FY filings
                annual = [r for r in rows if r.get('form','').startswith('10-K')
                          and r.get('fp','') in ('FY','')]
                if not annual:
                    annual = [r for r in rows if r.get('form','').startswith('20-F')]
                if not annual: continue
                annual.sort(key=lambda r: r.get('end',''), reverse=True)
                # Take the most recent one with a non-null val
                for r in annual:
                    v = r.get('val')
                    if v is not None and v != 0:
                        return float(v), r.get('end','')
    return None, None


def derive_one(ticker, cik, price):
    facts = fetch_companyfacts(cik)
    if facts is None:
        return None
    # Shares outstanding — try companyfacts CommonStockSharesOutstanding first, then dei.EntityCommonStockSharesOutstanding
    shares, sh_date = latest_annual(facts,
        ['CommonStockSharesOutstanding','CommonStockSharesIssued','EntityCommonStockSharesOutstanding'])
    # Book value (stockholders equity)
    equity, eq_date = latest_annual(facts,
        ['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'])
    # Net income (TTM-ish; latest annual)
    ni, ni_date = latest_annual(facts, ['NetIncomeLoss','ProfitLoss'])
    # EBITDA — derived if we have OpIncome + D&A
    op_inc, _ = latest_annual(facts, ['OperatingIncomeLoss'])
    da,     _ = latest_annual(facts, ['DepreciationDepletionAndAmortization',
                                       'DepreciationAndAmortization','Depreciation'])
    # Total debt & cash for EV
    debt_lt, _ = latest_annual(facts, ['LongTermDebt','LongTermDebtNoncurrent'])
    debt_st, _ = latest_annual(facts, ['ShortTermBorrowings','DebtCurrent'])
    cash, _    = latest_annual(facts, ['CashAndCashEquivalentsAtCarryingValue','Cash','CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'])
    # Revenue (for sanity / EV/Sales)
    rev, _ = latest_annual(facts, ['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax',
                                    'RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet'])

    out = {'ticker': ticker, 'shares': shares, 'book_value': equity, 'net_income': ni,
           'op_income': op_inc, 'da': da, 'debt_lt': debt_lt, 'debt_st': debt_st,
           'cash': cash, 'rev': rev,
           'shares_date': sh_date, 'equity_date': eq_date, 'ni_date': ni_date}

    if shares and price is not None and pd.notna(price) and price > 0:
        mkt = shares * float(price)
        out['derived_mktCap'] = mkt
        if equity and equity > 0:
            out['derived_pb'] = mkt / equity
        if ni and ni > 0:
            eps = ni / shares
            out['derived_eps'] = eps
            out['derived_pe'] = float(price) / eps
        ebitda = (op_inc + da) if (op_inc and da) else None
        if ebitda and ebitda > 0:
            net_debt = (debt_lt or 0) + (debt_st or 0) - (cash or 0)
            ev = mkt + net_debt
            out['derived_ev'] = ev
            out['derived_ev_ebitda'] = ev / ebitda
            if rev and rev > 0:
                out['derived_ps'] = mkt / rev
    return out


ap = argparse.ArgumentParser()
ap.add_argument('--workers', type=int, default=8)
ap.add_argument('--out', default='data/research/derived_us_pb_pe.csv')
ap.add_argument('--resume', action='store_true', default=True)
ap.add_argument('--limit', type=int, default=0)
args = ap.parse_args()

# Load SEC ticker → CIK map
sec_path = '/tmp/sec_tickers.json'
if not os.path.exists(sec_path):
    print(f"missing {sec_path} — fetch it first", file=sys.stderr); sys.exit(1)
with open(sec_path) as f:
    sec = json.load(f)
tk_cik = {v['ticker'].upper(): v['cik_str'] for v in sec.values()}

# Load synthesis to get the price and identify rows missing PB or PE
df = pd.read_csv('data/synthesis/v2_universe_ranked_full_q.csv', low_memory=False)
df['ticker'] = df['ticker'].astype(str).str.upper().str.strip()
# Target: US-region tickers with missing PB or PE that have a CIK and a price
us = df[(df['region'].isin(['us','us_x','us_nms']))
        & ((df['pb'].isna()) | (df['pe'].isna()) | (df['mktCap'].isna()))
        & (df['ticker'].isin(tk_cik.keys()))
        & (pd.to_numeric(df['price'], errors='coerce') > 0)]
print(f"US tickers needing PB/PE derivation: {len(us):,}", file=sys.stderr)

todo = us[['ticker','price']].drop_duplicates('ticker')
if args.limit: todo = todo.head(args.limit)

# Resume
existing = []; already = set()
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 100:
    prev = pd.read_csv(args.out)
    already = set(prev['ticker'].dropna().astype(str).tolist())
    existing = prev.to_dict('records')
    print(f"resume: {len(already):,} already done", file=sys.stderr)
todo = todo[~todo['ticker'].isin(already)]
print(f"todo: {len(todo):,} tickers · {args.workers} workers", file=sys.stderr)

rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

def task(row):
    r = derive_one(row['ticker'], tk_cik[row['ticker']], row['price'])
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % 100 == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            el = time.time() - start; rate = done[0]/max(el,0.1)
            eta = (len(todo)-done[0])/max(rate,0.001)/60
            print(f"[derive] {done[0]}/{len(todo)}  rate {rate:.1f}/s  ETA {eta:.0f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futs = [ex.submit(task, r) for _, r in todo.iterrows()]
    for _ in as_completed(futs): pass

pd.DataFrame(rows).to_csv(args.out, index=False)
out_df = pd.DataFrame(rows)
print(f"DONE: {len(out_df):,} rows", file=sys.stderr)
for c in ['derived_pb','derived_pe','derived_mktCap','derived_ev_ebitda']:
    if c in out_df.columns:
        print(f"  {c:20s} filled: {out_df[c].notna().sum():,}", file=sys.stderr)
