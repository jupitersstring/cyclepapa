#!/usr/bin/env python3
"""SEC EDGAR-based compounder research — bypasses yfinance entirely.

Pulls companyfacts JSON from data.sec.gov for each ticker, extracts annual
financial-statement series from XBRL tags, and computes the same Lindy
multi-method ROIC + ROIIC + cash-on-cash framework as pull_compounder_research_v2.

Advantages over yfinance:
  • Free, no API key
  • No "Too Many Requests" — SEC allows 10 req/sec with proper User-Agent
  • Cleaner data (XBRL filings direct from companies)
  • Longer history (5-10 years vs yf's 4)
  • All tagged values are timestamped and auditable

Constraints:
  • US-listed only (foreign issuers covered if filed 20-F)
  • Requires ticker → CIK lookup (from sec.gov/files/company_tickers.json)
"""
import argparse, sys, time, threading, warnings, os, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import requests

warnings.filterwarnings('ignore')

UA = "cyclepapa research cm2whv9sg2@privaterelay.appleid.com"


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
    """Download (or load cached) SEC ticker→CIK map."""
    if not os.path.exists(path):
        r = requests.get('https://www.sec.gov/files/company_tickers.json',
                         headers={'User-Agent': UA}, timeout=30)
        r.raise_for_status()
        open(path, 'w').write(r.text)
    with open(path) as f:
        d = json.load(f)
    return {v['ticker']: int(v['cik_str']) for v in d.values()}


def fetch_companyfacts(cik, session, limiter, max_retries=3):
    """Pull companyfacts JSON for a given CIK (10-digit zero-padded)."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    for attempt in range(max_retries):
        limiter.wait()
        try:
            r = session.get(url, headers={'User-Agent': UA}, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                time.sleep(2 ** attempt * 3); continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt); continue
            return None
    return None


def extract_annual_series(facts, tags, unit='USD'):
    """Extract annual (FY) values for any of the given XBRL tags.
    Returns dict: {fiscal_year_end_date: value}, most-recent first.
    """
    if not facts: return {}
    us_gaap = facts.get('facts', {}).get('us-gaap', {})
    ifrs    = facts.get('facts', {}).get('ifrs-full', {})
    for src in [us_gaap, ifrs]:
        for tag in tags:
            entry = src.get(tag)
            if not entry: continue
            units_dict = entry.get('units', {})
            data = units_dict.get(unit) or next(iter(units_dict.values()), [])
            # Keep only annual (form 10-K) values, last 6 years
            annual = {}
            for d in data:
                form = d.get('form', '')
                fp = d.get('fp', '')
                fy = d.get('fy')
                end = d.get('end', '')
                val = d.get('val')
                # Annual full-year values from 10-K
                if form in ('10-K', '20-F', '40-F') and fp == 'FY' and val is not None:
                    annual[end] = float(val)
            if annual:
                # Return sorted by date desc
                return dict(sorted(annual.items(), key=lambda x: x[0], reverse=True))
    return {}


def compute_metrics_for_ticker(ticker, cik, session, limiter):
    facts = fetch_companyfacts(cik, session, limiter)
    if facts is None: return None

    # Pull each line item (try multiple tag variants for resilience)
    rev_s     = extract_annual_series(facts, ['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax'])
    opinc_s   = extract_annual_series(facts, ['OperatingIncomeLoss'])
    pretax_s  = extract_annual_series(facts, ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest','IncomeLossBeforeIncomeTaxes'])
    tax_s     = extract_annual_series(facts, ['IncomeTaxExpenseBenefit','TaxesIncome'])
    equity_s  = extract_annual_series(facts, ['StockholdersEquity','StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'])
    ltd_s     = extract_annual_series(facts, ['LongTermDebt','LongTermDebtNoncurrent'])
    std_s     = extract_annual_series(facts, ['ShortTermBorrowings','LongTermDebtCurrent','DebtCurrent'])
    cash_s    = extract_annual_series(facts, ['CashAndCashEquivalentsAtCarryingValue','CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'])
    assets_s  = extract_annual_series(facts, ['Assets'])
    cur_ass_s = extract_annual_series(facts, ['AssetsCurrent'])
    cur_lib_s = extract_annual_series(facts, ['LiabilitiesCurrent'])
    ppe_s     = extract_annual_series(facts, ['PropertyPlantAndEquipmentNet'])
    capex_s   = extract_annual_series(facts, ['PaymentsToAcquirePropertyPlantAndEquipment'])
    ocf_s     = extract_annual_series(facts, ['NetCashProvidedByUsedInOperatingActivities'])
    da_s      = extract_annual_series(facts, ['DepreciationDepletionAndAmortization','DepreciationAndAmortization','Depreciation'])

    if not opinc_s or not equity_s:
        return {'ticker': ticker, 'cik': cik, 'has_history': False, 'name': facts.get('entityName')}

    # Common dates (intersection of must-haves)
    common = sorted(set(opinc_s) & set(equity_s), reverse=True)[:5]
    if len(common) < 2:
        return {'ticker': ticker, 'cik': cik, 'has_history': False, 'name': facts.get('entityName')}

    rows = []
    for d in common:
        oi = opinc_s.get(d)
        rv = rev_s.get(d)
        eq = equity_s.get(d)
        ltd = ltd_s.get(d, 0) or 0
        std = std_s.get(d, 0) or 0
        debt = ltd + std
        ch = cash_s.get(d, 0) or 0
        ta = assets_s.get(d)
        ca = cur_ass_s.get(d); cl = cur_lib_s.get(d)
        pp = ppe_s.get(d)
        fcf_calc = None
        if ocf_s.get(d) is not None and capex_s.get(d) is not None:
            # capex is reported as positive number in SEC; subtract
            fcf_calc = ocf_s[d] - abs(capex_s[d])
        ocf = ocf_s.get(d)
        da_val = da_s.get(d)

        # ETR
        if pretax_s.get(d) and tax_s.get(d) and pretax_s[d] > 0:
            etr = tax_s[d] / pretax_s[d]
        else: etr = 0.21
        etr = min(max(etr, 0), 0.5)

        nopat = oi * (1 - etr) if oi is not None else None
        ic_op = (eq + debt - ch) if eq is not None else None
        ic_bv = (eq + debt) if eq is not None else None
        nwc = (ca - cl) if (ca is not None and cl is not None) else None
        tang = (nwc + pp) if (nwc is not None and pp is not None) else None

        method_res = {}
        if nopat is not None and ic_op and ic_op > 0:
            method_res['roic_mauboussin'] = nopat / ic_op
        if nopat is not None and ic_bv and ic_bv > 0:
            method_res['roic_damodaran'] = nopat / ic_bv
        if oi is not None and tang and tang > 0:
            method_res['roic_greenblatt'] = oi / tang
        if fcf_calc is not None and ic_op and ic_op > 0:
            method_res['roic_croic'] = fcf_calc / ic_op
        if oi is not None and rv and ta and rv > 0 and ta > 0:
            method_res['roic_dupont'] = (oi/rv) * (rv/ta) * (1 - etr)

        cleaned = {k: v for k, v in method_res.items() if v is not None and -2 < v < 5}
        roic_med = float(np.median(list(cleaned.values()))) if cleaned else None
        roic_std = float(np.std(list(cleaned.values()))) if len(cleaned) >= 2 else None
        agree = (1 - roic_std/abs(roic_med)) if (roic_std and roic_med) else None

        rows.append({
            'date': d, 'op_inc': oi, 'rev': rv, 'etr': etr, 'nopat': nopat,
            'equity': eq, 'debt': debt, 'cash': ch, 'ic_op': ic_op, 'ic_bv': ic_bv,
            'total_assets': ta, 'tangible_cap': tang,
            'fcf': fcf_calc, 'op_cf': ocf, 'da': da_val,
            'roic_median_5m': roic_med, 'roic_method_agreement': agree,
            **method_res,
        })
    yearly = pd.DataFrame(rows).sort_values('date', ascending=False).reset_index(drop=True)

    # Aggregates
    roic_meds = yearly['roic_median_5m'].dropna()
    roic_mean = float(roic_meds.mean()) if len(roic_meds) else None
    roic_min  = float(roic_meds.min())  if len(roic_meds) else None
    roic_max  = float(roic_meds.max())  if len(roic_meds) else None
    roic_std  = float(roic_meds.std())  if len(roic_meds) >= 2 else None
    agree_mean= float(yearly['roic_method_agreement'].dropna().mean()) if yearly['roic_method_agreement'].notna().any() else None

    # ROIIC + inflection (accrual)
    n_arr = yearly['nopat'].values; ic_arr = yearly['ic_op'].values
    roiic = {}
    for w, lab in [(1,'roiic_1y'),(2,'roiic_2y'),(3,'roiic_3y')]:
        if len(n_arr) > w and n_arr[0] is not None and n_arr[w] is not None and ic_arr[0] is not None and ic_arr[w] is not None:
            d_n = n_arr[0] - n_arr[w]; d_ic = ic_arr[0] - ic_arr[w]
            if d_ic > 0: roiic[lab] = d_n / d_ic
            elif d_ic <= 0 and d_n > 0: roiic[lab] = 2.0
            else: roiic[lab] = None
        else: roiic[lab] = None
    r1 = roiic.get('roiic_1y'); r3 = roiic.get('roiic_3y')
    if r1 is not None and r3 is not None:
        roiic['roiic_acceleration'] = r1 - r3
        roiic['roiic_inflection'] = bool((r1 - r3) >= 0.05 and r1 > 0.10)
    else:
        roiic['roiic_acceleration'] = None; roiic['roiic_inflection'] = False

    # Cash-on-cash
    fcf_arr = yearly['fcf'].values; ocf_arr = yearly['op_cf'].values; rev_arr = yearly['rev'].values
    cc_fcf = [fcf_arr[i]/ic_arr[i] for i in range(len(yearly)) if fcf_arr[i] is not None and ic_arr[i] and ic_arr[i] > 0]
    cc_ocf = [ocf_arr[i]/ic_arr[i] for i in range(len(yearly)) if ocf_arr[i] is not None and ic_arr[i] and ic_arr[i] > 0]
    cash_block = {}
    if cc_fcf:
        cash_block['cc_roic_fcf_latest']  = cc_fcf[0]
        cash_block['cc_roic_fcf_mean_4y'] = float(np.mean(cc_fcf))
        cash_block['cc_roic_fcf_min_4y']  = float(np.min(cc_fcf))
        cash_block['cc_roic_fcf_std_4y']  = float(np.std(cc_fcf)) if len(cc_fcf) >= 2 else None
    if cc_ocf:
        cash_block['cc_roic_ocf_latest']  = cc_ocf[0]
        cash_block['cc_roic_ocf_mean_4y'] = float(np.mean(cc_ocf))
    for w, lab in [(1,'cc_roiic_1y'),(2,'cc_roiic_2y'),(3,'cc_roiic_3y')]:
        if len(fcf_arr) > w and fcf_arr[0] is not None and fcf_arr[w] is not None and ic_arr[0] is not None and ic_arr[w] is not None:
            d_f = fcf_arr[0] - fcf_arr[w]; d_ic = ic_arr[0] - ic_arr[w]
            if d_ic > 0: cash_block[lab] = d_f / d_ic
            elif d_ic <= 0 and d_f > 0: cash_block[lab] = 2.0
            else: cash_block[lab] = None
        else: cash_block[lab] = None
    cr1 = cash_block.get('cc_roiic_1y'); cr3 = cash_block.get('cc_roiic_3y')
    if cr1 is not None and cr3 is not None:
        cash_block['cc_roiic_acceleration'] = cr1 - cr3
        cash_block['cc_roiic_inflection'] = bool((cr1 - cr3) >= 0.05 and cr1 > 0.08)
    else:
        cash_block['cc_roiic_acceleration'] = None; cash_block['cc_roiic_inflection'] = False

    if fcf_arr[0] is not None and rev_arr[0] and rev_arr[0] > 0:
        cash_block['fcf_margin_latest'] = fcf_arr[0] / rev_arr[0]
    margins = [fcf_arr[i]/rev_arr[i] for i in range(len(yearly)) if fcf_arr[i] is not None and rev_arr[i] and rev_arr[i] > 0]
    if margins: cash_block['fcf_margin_mean_4y'] = float(np.mean(margins))
    conv = [fcf_arr[i]/yearly['nopat'].iloc[i] for i in range(len(yearly))
            if fcf_arr[i] is not None and yearly['nopat'].iloc[i] and yearly['nopat'].iloc[i] > 0]
    if conv:
        cash_block['cash_conversion_mean_4y'] = float(np.mean(conv))
        cash_block['cash_conversion_min_4y']  = float(np.min(conv))

    enduring_strict = (len(roic_meds) >= 3 and roic_min is not None and roic_min >= 0.15
                       and roic_std is not None and roic_std <= 0.08
                       and (agree_mean is None or agree_mean >= 0.5))
    enduring_loose  = (len(roic_meds) >= 3 and roic_min is not None and roic_min >= 0.10
                       and roic_std is not None and roic_std <= 0.12)

    out = {
        'ticker': ticker, 'cik': cik,
        'name': facts.get('entityName'),
        'roic_latest_med': roic_meds.iloc[0] if len(roic_meds) else None,
        'roic_mean_4y_med': roic_mean,
        'roic_min_4y_med': roic_min,
        'roic_max_4y_med': roic_max,
        'roic_std_4y_med': roic_std,
        'roic_method_agreement': agree_mean,
        'roic_years': len(roic_meds),
        'has_history': True,
        'enduring_strict': enduring_strict,
        'enduring_loose': enduring_loose,
        **{k: yearly.iloc[0].get(k) for k in ['roic_mauboussin','roic_damodaran','roic_greenblatt','roic_croic','roic_dupont']},
        **roiic, **cash_block,
    }
    # Source data sample
    out['nopat_latest'] = yearly['nopat'].iloc[0] if len(yearly) else None
    out['ic_latest']    = yearly['ic_op'].iloc[0] if len(yearly) else None
    out['rev_latest']   = yearly['rev'].iloc[0] if len(yearly) else None
    return out


ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--workers', type=int, default=8)
ap.add_argument('--rate', type=float, default=8.0, help='SEC allows ~10 req/sec with proper UA')
ap.add_argument('--checkpoint', type=int, default=100)
ap.add_argument('--resume', action='store_true')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).str.upper().unique().tolist()

# Build ticker → CIK map; drop tickers not in SEC (foreign listings won't be)
print("Loading SEC ticker→CIK map...", file=sys.stderr)
t2c = get_ticker_to_cik()
syms_with_cik = [(s, t2c[s]) for s in syms if s in t2c]
missing = len(syms) - len(syms_with_cik)
print(f"  {len(syms_with_cik)} have SEC CIK, {missing} not found (foreign/OTC/delisted)", file=sys.stderr)

already = set(); existing = []
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 10:
    try:
        prev = pd.read_csv(args.out)
        already = set(prev['ticker'].dropna().astype(str).tolist())
        existing = prev.to_dict('records')
        print(f"[edgar] resume: {len(already)} done", file=sys.stderr)
    except Exception: pass

todo = [(s, c) for s, c in syms_with_cik if s not in already]
print(f"[edgar] {len(todo)} tickers · {args.workers} workers · {args.rate} req/s · ETA ~{len(todo)/args.rate/60:.0f}m", file=sys.stderr)

session = requests.Session()
session.verify = '/root/.ccr/ca-bundle.crt' if os.path.exists('/root/.ccr/ca-bundle.crt') else True
limiter = RateLimiter(args.rate)
rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

def task(item):
    t, c = item
    r = compute_metrics_for_ticker(t, c, session, limiter)
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            elapsed = time.time() - start; rate = done[0] / max(elapsed, 0.1)
            eta = (len(todo) - done[0]) / max(rate, 0.01) / 60
            print(f"[edgar] {done[0]}/{len(todo)}  kept {len(rows)-len(existing)}  rate {rate:.2f}/s  ETA {eta:.1f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = [ex.submit(task, x) for x in todo]
    for _ in as_completed(futures): pass

pd.DataFrame(rows).to_csv(args.out, index=False)
df = pd.DataFrame(rows)
if len(df):
    print(f"[edgar] DONE: {len(df)} rows", file=sys.stderr)
    h = df.get('has_history', pd.Series(dtype=bool)).fillna(False)
    print(f"  with history: {int(h.sum())}", file=sys.stderr)
    print(f"  enduring strict: {int(df.get('enduring_strict', pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
    print(f"  enduring loose:  {int(df.get('enduring_loose',  pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
    print(f"  ROIIC inflecting: {int(df.get('roiic_inflection', pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
    print(f"  CC-ROIIC inflecting: {int(df.get('cc_roiic_inflection', pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
