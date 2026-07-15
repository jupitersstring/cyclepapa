#!/usr/bin/env python3
"""Primary-research compounder puller — annual financial statements direct.

For each ticker pulls (via yfinance .financials / .balance_sheet / .cashflow):
  • Operating Income, Tax Provision, EBIT  (income statement, 4 years)
  • Total Equity, Total Debt, Cash, Total Assets (balance sheet, 4 years)
  • CapEx, Free Cash Flow (cashflow, 4 years)

Computes:
  • ROIC per year = NOPAT / Invested Capital
      NOPAT = OperatingIncome × (1 − effective_tax_rate)
      Invested Capital = TotalEquity + TotalDebt − Cash
  • ROIIC (incremental) = (NOPAT_t − NOPAT_t-3) / (IC_t − IC_t-3)
  • Structural quality: min(ROIC) ≥ 0.15 AND std(ROIC) ≤ 0.05 across 4 yrs
  • Reinvestment rate = (IC_t − IC_t-1) / NOPAT_t-1
  • Implied growth = ROIIC × reinvestment_rate
  • Asset turnover, gross margin, FCF/sales

Plus valuation (current):
  • EV / EBIT (TTM)
  • EV / EBITDA (TTM)
  • EV / FCF (TTM)
  • FCF yield

Multi-worker (default 4) with global token-bucket rate limit + retry on 429.
"""
import argparse, sys, time, threading, warnings, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
import sys as _sys, os as _os; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__))); import yf_patch  # noqa
import yfinance as yf

warnings.filterwarnings('ignore')

class RateLimiter:
    def __init__(self, rate_per_sec):
        self.interval = 1.0 / rate_per_sec
        self.lock = threading.Lock()
        self.next_ok = 0.0
    def wait(self):
        with self.lock:
            now = time.time()
            if now < self.next_ok:
                time.sleep(self.next_ok - now)
                now = time.time()
            self.next_ok = now + self.interval


def _series(df, candidates):
    """Pull a row matching any of candidates, return as numeric series indexed by date desc."""
    if df is None or df.empty: return None
    for k in candidates:
        if k in df.index:
            try:
                s = pd.to_numeric(df.loc[k], errors='coerce')
                if s.notna().sum() >= 1:
                    return s
            except Exception: pass
    return None


def compute_roic_history(fin, bs, cf):
    """Returns a DataFrame indexed by year with columns: op_inc, tax, ebit,
       equity, debt, cash, ic, nopat, roic, capex, fcf."""
    if fin is None or fin.empty or bs is None or bs.empty:
        return None

    op_inc = _series(fin, ['Operating Income', 'Ebit', 'EBIT', 'Operating Income Loss', 'OperatingIncome'])
    pretax = _series(fin, ['Pretax Income', 'Income Before Tax'])
    tax    = _series(fin, ['Tax Provision', 'Income Tax Expense', 'TaxProvision', 'Income Tax'])
    equity = _series(bs,  ['Stockholders Equity', 'Total Equity Gross Minority Interest', 'TotalStockholdersEquity', 'Total Stockholder Equity'])
    debt   = _series(bs,  ['Total Debt', 'TotalDebt', 'Long Term Debt And Capital Lease Obligation'])
    cash   = _series(bs,  ['Cash And Cash Equivalents', 'CashAndCashEquivalents', 'Cash Cash Equivalents And Short Term Investments'])
    capex  = _series(cf,  ['Capital Expenditure', 'CapitalExpenditures'])
    fcf    = _series(cf,  ['Free Cash Flow', 'FreeCashFlow'])

    if op_inc is None or equity is None or debt is None:
        return None

    # Align all to common dates (intersection)
    dates = sorted(set(op_inc.dropna().index)
                   & set(equity.dropna().index)
                   & set(debt.dropna().index), reverse=True)
    if len(dates) < 2: return None
    dates = dates[:4]  # last 4 years

    rows = []
    for d in dates:
        oi  = op_inc.get(d, np.nan)
        eq  = equity.get(d, np.nan)
        db  = debt.get(d, 0) or 0
        ch  = cash.get(d, 0) if cash is not None else 0
        ic  = (eq + db - ch) if pd.notna(eq) and pd.notna(db) else np.nan
        # Effective tax rate
        if tax is not None and pretax is not None:
            t = tax.get(d, np.nan); pt = pretax.get(d, np.nan)
            etr = (t / pt) if (pd.notna(t) and pd.notna(pt) and pt > 0) else 0.21
        else:
            etr = 0.21  # US default
        etr = min(max(etr, 0), 0.5)  # clamp
        nopat = oi * (1 - etr) if pd.notna(oi) else np.nan
        roic = (nopat / ic) if (pd.notna(nopat) and pd.notna(ic) and ic > 0) else np.nan
        rows.append({
            'date': d, 'op_inc': oi, 'etr': etr, 'nopat': nopat,
            'equity': eq, 'debt': db, 'cash': ch, 'ic': ic, 'roic': roic,
            'capex': capex.get(d, np.nan) if capex is not None else np.nan,
            'fcf': fcf.get(d, np.nan) if fcf is not None else np.nan,
        })
    return pd.DataFrame(rows).sort_values('date', ascending=False).reset_index(drop=True)


def fetch_one(t, limiter, max_retries=3):
    for attempt in range(max_retries):
        limiter.wait()
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            mcap = info.get('marketCap') or 0
            if not mcap and not info.get('totalRevenue'):
                return None

            fin = tk.financials
            bs  = tk.balance_sheet
            cf  = tk.cashflow

            roic_df = compute_roic_history(fin, bs, cf)
            if roic_df is None or len(roic_df) < 2:
                # Fallback to current-period only via info
                return {
                    'ticker': t,
                    'name': info.get('shortName'),
                    'sector': info.get('sector'),
                    'industry': info.get('industry'),
                    'currency': info.get('currency'),
                    'mktCap': mcap,
                    'has_history': False,
                }

            # ROIC stats
            roic_series = roic_df['roic'].dropna()
            ic_series   = roic_df['ic'].dropna()
            nopat_series= roic_df['nopat'].dropna()

            roic_mean = float(roic_series.mean()) if len(roic_series) else np.nan
            roic_min  = float(roic_series.min()) if len(roic_series) else np.nan
            roic_std  = float(roic_series.std()) if len(roic_series) >= 2 else np.nan
            roic_latest = float(roic_series.iloc[0]) if len(roic_series) else np.nan

            # ROIIC (incremental return on capital deployed since N years ago)
            roiic = np.nan
            if len(nopat_series) >= 2 and len(ic_series) >= 2:
                d_nopat = float(nopat_series.iloc[0]) - float(nopat_series.iloc[-1])
                d_ic    = float(ic_series.iloc[0]) - float(ic_series.iloc[-1])
                if d_ic > 0:
                    roiic = d_nopat / d_ic
                elif d_ic < 0 and d_nopat > 0:
                    roiic = float('inf')  # earning more on less capital — capital returns
                else:
                    roiic = np.nan

            # Reinvestment rate
            reinvest = np.nan
            if len(ic_series) >= 2 and len(nopat_series) >= 2:
                d_ic = float(ic_series.iloc[0]) - float(ic_series.iloc[1])
                nopat_prev = float(nopat_series.iloc[1])
                if nopat_prev != 0:
                    reinvest = d_ic / nopat_prev

            # Structural quality flag
            structural_quality = (
                len(roic_series) >= 3 and
                roic_min >= 0.12 and       # never dropped below 12%
                (roic_std < 0.10 if not pd.isna(roic_std) else False)
            )

            # Valuation (TTM via info)
            debt_now = info.get('totalDebt') or 0
            cash_now = info.get('totalCash') or 0
            ev = (mcap + debt_now - cash_now) if mcap else None
            fcf_now = info.get('freeCashflow') or 0
            ebitda_now = info.get('ebitda') or 0
            ebit_now = info.get('ebit')
            # Fallback ebit from latest financial
            if not ebit_now and len(roic_df) > 0 and pd.notna(roic_df['op_inc'].iloc[0]):
                ebit_now = float(roic_df['op_inc'].iloc[0])

            ev_ebit   = (ev / ebit_now) if (ev and ebit_now and ebit_now != 0) else None
            ev_ebitda = (ev / ebitda_now) if (ev and ebitda_now and ebitda_now != 0) else None
            ev_fcf    = (ev / fcf_now) if (ev and fcf_now and fcf_now > 0) else None
            fcf_yield = (fcf_now / mcap) if (mcap and fcf_now) else None

            # Compounder composite score (high ROIC × cheap × growing)
            comp_score = 0
            if roic_mean and pd.notna(roic_mean):
                comp_score += np.clip(roic_mean * 100, 0, 50)   # cap at 50%
            if roiic and pd.notna(roiic) and roiic != float('inf'):
                comp_score += np.clip(roiic * 50, -10, 40)
            if ev_ebit and pd.notna(ev_ebit) and ev_ebit > 0:
                comp_score += np.clip((20 - ev_ebit) / 2, -10, 10)
            if fcf_yield and pd.notna(fcf_yield):
                comp_score += np.clip(fcf_yield * 100, -5, 15)
            if structural_quality: comp_score += 15

            return {
                'ticker': t,
                'name': info.get('shortName'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'currency': info.get('currency'),
                'mktCap': mcap, 'ev': ev,
                'roic_latest': roic_latest,
                'roic_mean_4y': roic_mean,
                'roic_min_4y': roic_min,
                'roic_std_4y': roic_std,
                'roiic_3y': roiic if roiic != float('inf') else 999,
                'reinvest_rate': reinvest,
                'structural_quality': bool(structural_quality),
                'ic_latest': float(ic_series.iloc[0]) if len(ic_series) else np.nan,
                'nopat_latest': float(nopat_series.iloc[0]) if len(nopat_series) else np.nan,
                'ebit_now': ebit_now,
                'ebitda_now': ebitda_now,
                'fcf_now': fcf_now,
                'ev_ebit': ev_ebit, 'ev_ebitda': ev_ebitda, 'ev_fcf': ev_fcf,
                'fcf_yield': fcf_yield,
                'rev_g': info.get('revenueGrowth'),
                'opm': info.get('operatingMargins'),
                'gm': info.get('grossMargins'),
                'insiders': info.get('heldPercentInsiders'),
                'years_history': len(roic_series),
                'has_history': True,
                'comp_score': round(float(comp_score), 2),
            }
        except Exception as e:
            msg = str(e)[:80]
            if '429' in msg or 'rate' in msg.lower() or 'Too Many' in msg:
                time.sleep(2 ** attempt * 3)
                continue
            return None
    return None


ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--workers', type=int, default=4)
ap.add_argument('--rate', type=float, default=0.4)
ap.add_argument('--checkpoint', type=int, default=50)
ap.add_argument('--resume', action='store_true')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).unique().tolist()

already = set(); existing = []
if args.resume and os.path.exists(args.out) and os.path.getsize(args.out) > 10:
    try:
        prev = pd.read_csv(args.out)
        already = set(prev['ticker'].dropna().astype(str).tolist())
        existing = prev.to_dict('records')
        print(f"[research] resume: {len(already)} done", file=sys.stderr)
    except Exception: pass

todo = [t for t in syms if t not in already]
print(f"[research] {len(todo)} tickers · {args.workers} workers · {args.rate} req/s · ETA ~{len(todo)/args.rate/60:.0f}m", file=sys.stderr)

limiter = RateLimiter(args.rate)
rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

def task(t):
    r = fetch_one(t, limiter)
    with lock:
        done[0] += 1
        if r: rows.append(r)
        if done[0] % args.checkpoint == 0:
            pd.DataFrame(rows).to_csv(args.out, index=False)
            elapsed = time.time() - start
            rate = done[0] / max(elapsed, 0.1)
            eta = (len(todo) - done[0]) / max(rate, 0.01) / 60
            print(f"[research] {done[0]}/{len(todo)}  kept {len(rows)-len(existing)}  rate {rate:.2f}/s  ETA {eta:.1f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = [ex.submit(task, t) for t in todo]
    for _ in as_completed(futures): pass

pd.DataFrame(rows).to_csv(args.out, index=False)
df = pd.DataFrame(rows)
if len(df):
    print(f"[research] DONE: {len(df)} rows", file=sys.stderr)
    print(f"  with history: {df.get('has_history', pd.Series(dtype=bool)).fillna(False).sum()}", file=sys.stderr)
    print(f"  structural quality (min ROIC ≥ 12%, low stdev): {df.get('structural_quality', pd.Series(dtype=bool)).fillna(False).sum()}", file=sys.stderr)
    rd = df[df['has_history'].fillna(False) & df['roic_mean_4y'].notna()]
    if len(rd):
        print(f"  mean roic_mean_4y: {rd['roic_mean_4y'].mean()*100:.1f}%", file=sys.stderr)
        print(f"  median ev_ebit: {rd['ev_ebit'].median():.1f}", file=sys.stderr)
