#!/usr/bin/env python3
"""Compounder research v2 — Lindy/multi-method ROIC + ROIIC inflection detection.

Each year's ROIC is computed FIVE different ways. We report the median (so any
single method's failure doesn't poison the result) plus method agreement
(stdev across methods) — high agreement = high confidence the number is real.

Methods (Lindy = time-tested, each compensating others' shortcomings):
  1. Mauboussin: NOPAT / Invested Capital = OpInc(1-effTaxRate) / (Eq+Debt-Cash)
  2. Damodaran: NOPAT / BookValueIC (uses effective tax rate, BV of total capital)
  3. Greenblatt: EBIT / Tangible Capital = OpInc / (NetWorkingCap + NetPPE)
  4. CROIC: FCF / IC = FreeCashFlow / (Eq+Debt-Cash)
  5. DuPont: OpMargin × AssetTurnover × (1-effTaxRate) = OpInc/Rev × Rev/TotalAssets × (1-t)

Reported per year and aggregated:
  • roic_median_5m: median of the 5 methods per year
  • roic_method_agreement: 1 - (std/mean) across methods (higher = more agreement)
  • roic_mean_4y_mm: mean of yearly medians across 4 years
  • roic_min_4y_mm:  min of yearly medians
  • roic_std_4y_mm:  std of yearly medians

ROIIC inflection:
  • roiic_1y, roiic_2y, roiic_3y — incremental return over 1/2/3 year windows
  • roiic_inflection_flag: roiic_1y > max(roiic_2y, roiic_3y) by ≥5pp (improving)
  • roiic_acceleration: roiic_1y − roiic_3y (positive = improving)

Multi-worker with token bucket. Resumable.
"""
import argparse, sys, time, threading, warnings, os
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
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
                time.sleep(self.next_ok - now); now = time.time()
            self.next_ok = now + self.interval


def _series(df, candidates):
    if df is None or df.empty: return None
    for k in candidates:
        if k in df.index:
            try:
                s = pd.to_numeric(df.loc[k], errors='coerce')
                if s.notna().sum(): return s
            except Exception: pass
    return None


def compute_per_year_metrics(fin, bs, cf):
    """Returns DataFrame: per-year base measures + 5 ROIC methods + median + agreement."""
    if fin is None or fin.empty or bs is None or bs.empty:
        return None

    op_inc   = _series(fin, ['Operating Income','Ebit','EBIT','Operating Income Loss','OperatingIncome'])
    rev      = _series(fin, ['Total Revenue','Revenue','Total Revenues'])
    pretax   = _series(fin, ['Pretax Income','Income Before Tax','Income Pretax'])
    tax      = _series(fin, ['Tax Provision','Income Tax Expense','TaxProvision','Income Tax'])
    equity   = _series(bs,  ['Stockholders Equity','Total Equity Gross Minority Interest','TotalStockholdersEquity','Total Stockholder Equity'])
    debt     = _series(bs,  ['Total Debt','TotalDebt','Long Term Debt And Capital Lease Obligation'])
    cash     = _series(bs,  ['Cash And Cash Equivalents','CashAndCashEquivalents','Cash Cash Equivalents And Short Term Investments'])
    assets   = _series(bs,  ['Total Assets','TotalAssets'])
    cur_ass  = _series(bs,  ['Current Assets','Total Current Assets'])
    cur_lib  = _series(bs,  ['Current Liabilities','Total Current Liabilities'])
    ppe      = _series(bs,  ['Net PPE','Net Property Plant And Equipment','Property Plant Equipment Net','Total Plant Property Equipment Net'])
    fcf_s    = _series(cf,  ['Free Cash Flow','FreeCashFlow'])
    capex    = _series(cf,  ['Capital Expenditure','CapitalExpenditures'])
    op_cf    = _series(cf,  ['Operating Cash Flow','Cash Flow From Operating Activities','OperatingCashFlow'])

    if op_inc is None or equity is None or debt is None:
        return None

    dates = sorted(set(op_inc.dropna().index)
                   & set(equity.dropna().index)
                   & set(debt.dropna().index), reverse=True)[:5]
    if len(dates) < 2: return None

    rows = []
    for d in dates:
        oi = float(op_inc.get(d, np.nan)) if pd.notna(op_inc.get(d)) else np.nan
        rv = float(rev.get(d, np.nan)) if rev is not None and pd.notna(rev.get(d, np.nan)) else np.nan
        eq = float(equity.get(d, np.nan))
        db = float(debt.get(d, 0)) if pd.notna(debt.get(d, 0)) else 0
        ch = float(cash.get(d, 0)) if cash is not None and pd.notna(cash.get(d, 0)) else 0
        ta = float(assets.get(d, np.nan)) if assets is not None and pd.notna(assets.get(d, np.nan)) else np.nan
        ca = float(cur_ass.get(d, np.nan)) if cur_ass is not None and pd.notna(cur_ass.get(d, np.nan)) else np.nan
        cl = float(cur_lib.get(d, np.nan)) if cur_lib is not None and pd.notna(cur_lib.get(d, np.nan)) else np.nan
        pp = float(ppe.get(d, np.nan)) if ppe is not None and pd.notna(ppe.get(d, np.nan)) else np.nan
        fcf = float(fcf_s.get(d, np.nan)) if fcf_s is not None and pd.notna(fcf_s.get(d, np.nan)) else np.nan
        cx = float(capex.get(d, np.nan)) if capex is not None and pd.notna(capex.get(d, np.nan)) else np.nan
        ocf = float(op_cf.get(d, np.nan)) if op_cf is not None and pd.notna(op_cf.get(d, np.nan)) else np.nan

        # Effective tax rate (clamp 0-50%; default 21% if unknown)
        if pretax is not None and tax is not None:
            t = tax.get(d); pt = pretax.get(d)
            etr = (float(t)/float(pt)) if (pd.notna(t) and pd.notna(pt) and float(pt) > 0) else 0.21
        else:
            etr = 0.21
        etr = min(max(etr, 0), 0.5)

        nopat = oi * (1 - etr) if pd.notna(oi) else np.nan
        ic_op = (eq + db - ch) if (pd.notna(eq) and pd.notna(db)) else np.nan
        ic_bv = (eq + db)       if (pd.notna(eq) and pd.notna(db)) else np.nan
        nwc = (ca - cl) if (pd.notna(ca) and pd.notna(cl)) else np.nan
        tangible_cap = (nwc + pp) if (pd.notna(nwc) and pd.notna(pp)) else np.nan

        # ─── 5 methods ──────────────────────────────────────────────────
        method_results = {}
        # 1. Mauboussin
        if pd.notna(nopat) and pd.notna(ic_op) and ic_op > 0:
            method_results['roic_mauboussin'] = nopat / ic_op
        # 2. Damodaran (NOPAT / BV of capital — total invested capital)
        if pd.notna(nopat) and pd.notna(ic_bv) and ic_bv > 0:
            method_results['roic_damodaran'] = nopat / ic_bv
        # 3. Greenblatt (pre-tax, tangible)
        if pd.notna(oi) and pd.notna(tangible_cap) and tangible_cap > 0:
            method_results['roic_greenblatt'] = oi / tangible_cap
        # 4. CROIC (cash-based)
        if pd.notna(fcf) and pd.notna(ic_op) and ic_op > 0:
            method_results['roic_croic'] = fcf / ic_op
        # 5. DuPont
        if pd.notna(oi) and pd.notna(rv) and pd.notna(ta) and rv > 0 and ta > 0:
            opm = oi / rv; turnover = rv / ta
            method_results['roic_dupont'] = opm * turnover * (1 - etr)

        # Filter outliers (typical ROIC is between -2 and 5 = -200% to +500%)
        cleaned = {k: v for k, v in method_results.items()
                   if pd.notna(v) and -2 < v < 5}
        roic_median = np.median(list(cleaned.values())) if cleaned else np.nan
        roic_std    = np.std(list(cleaned.values()))    if len(cleaned) >= 2 else np.nan
        n_methods   = len(cleaned)
        agreement   = (1 - (roic_std / abs(roic_median))) if (pd.notna(roic_std) and pd.notna(roic_median) and roic_median != 0) else np.nan

        row = {
            'date': d, 'op_inc': oi, 'rev': rv, 'etr': etr, 'nopat': nopat,
            'equity': eq, 'debt': db, 'cash': ch, 'total_assets': ta,
            'ic_op': ic_op, 'ic_bv': ic_bv, 'tangible_cap': tangible_cap,
            'fcf': fcf, 'capex': cx, 'op_cf': ocf,
            'roic_median_5m': roic_median, 'roic_method_std': roic_std,
            'roic_method_agreement': agreement, 'roic_n_methods': n_methods,
        }
        row.update(method_results)
        rows.append(row)
    return pd.DataFrame(rows).sort_values('date', ascending=False).reset_index(drop=True)


def compute_roiic_with_inflection(yearly_df):
    """Compute 1y, 2y, 3y ROIIC + inflection flag (accrual NOPAT-based).

    ROIIC over N years = (NOPAT_now − NOPAT_N-ago) / (IC_now − IC_N-ago)
    """
    if yearly_df is None or len(yearly_df) < 2:
        return {}
    n = yearly_df['nopat'].values
    ic = yearly_df['ic_op'].values
    result = {}
    for window, label in [(1, 'roiic_1y'), (2, 'roiic_2y'), (3, 'roiic_3y')]:
        if len(n) > window and pd.notna(n[0]) and pd.notna(n[window]) and pd.notna(ic[0]) and pd.notna(ic[window]):
            d_n = n[0] - n[window]; d_ic = ic[0] - ic[window]
            if d_ic > 0: result[label] = d_n / d_ic
            elif d_ic <= 0 and d_n > 0: result[label] = 2.0
            else: result[label] = np.nan
        else:
            result[label] = np.nan
    r1 = result.get('roiic_1y'); r3 = result.get('roiic_3y')
    if pd.notna(r1) and pd.notna(r3):
        result['roiic_acceleration'] = r1 - r3
        result['roiic_inflection'] = bool((r1 - r3) >= 0.05 and r1 > 0.10)
    else:
        result['roiic_acceleration'] = np.nan
        result['roiic_inflection'] = False
    return result


def compute_cash_metrics(yearly_df):
    """Cash-on-cash ROIC + ROIIC variants (FCF-based, OCF-based).

    These bypass accrual accounting and measure pure cash returns:
      • cc_roic_fcf_latest   = FCF / IC_op    (most recent year)
      • cc_roic_ocf_latest   = OperatingCashFlow / IC_op
      • cc_roic_mean_4y      = mean of FCF/IC over 4 years
      • cc_roic_min_4y       = min of FCF/IC (consistency floor)
      • cc_roiic_1y/2y/3y    = ΔFCF / ΔIC over window
      • cc_roiic_inflection  = cc_roiic_1y > cc_roiic_3y by ≥5pp AND > 8%
      • fcf_margin_latest    = FCF / Rev
      • cash_conversion_4y   = mean(FCF / NOPAT) — earnings→cash conversion ratio
    """
    if yearly_df is None or len(yearly_df) < 2: return {}
    fcf = yearly_df['fcf'].values
    ocf = yearly_df['op_cf'].values
    ic  = yearly_df['ic_op'].values
    nopat = yearly_df['nopat'].values
    rev = yearly_df['rev'].values

    out = {}
    # Per-year cash-on-cash ROIC arrays
    cc_fcf_per_yr, cc_ocf_per_yr = [], []
    for i in range(len(yearly_df)):
        if pd.notna(fcf[i]) and pd.notna(ic[i]) and ic[i] > 0:
            cc_fcf_per_yr.append(fcf[i] / ic[i])
        if pd.notna(ocf[i]) and pd.notna(ic[i]) and ic[i] > 0:
            cc_ocf_per_yr.append(ocf[i] / ic[i])

    if cc_fcf_per_yr:
        out['cc_roic_fcf_latest'] = cc_fcf_per_yr[0]
        out['cc_roic_fcf_mean_4y'] = float(np.mean(cc_fcf_per_yr))
        out['cc_roic_fcf_min_4y']  = float(np.min(cc_fcf_per_yr))
        out['cc_roic_fcf_std_4y']  = float(np.std(cc_fcf_per_yr)) if len(cc_fcf_per_yr) >= 2 else np.nan
    if cc_ocf_per_yr:
        out['cc_roic_ocf_latest']  = cc_ocf_per_yr[0]
        out['cc_roic_ocf_mean_4y'] = float(np.mean(cc_ocf_per_yr))

    # Cash-on-cash ROIIC windows
    for window, label in [(1, 'cc_roiic_1y'), (2, 'cc_roiic_2y'), (3, 'cc_roiic_3y')]:
        if len(fcf) > window and pd.notna(fcf[0]) and pd.notna(fcf[window]) and pd.notna(ic[0]) and pd.notna(ic[window]):
            d_fcf = fcf[0] - fcf[window]; d_ic = ic[0] - ic[window]
            if d_ic > 0: out[label] = d_fcf / d_ic
            elif d_ic <= 0 and d_fcf > 0: out[label] = 2.0
            else: out[label] = np.nan
        else:
            out[label] = np.nan

    r1 = out.get('cc_roiic_1y'); r3 = out.get('cc_roiic_3y')
    if pd.notna(r1) and pd.notna(r3):
        out['cc_roiic_acceleration'] = r1 - r3
        out['cc_roiic_inflection'] = bool((r1 - r3) >= 0.05 and r1 > 0.08)
    else:
        out['cc_roiic_acceleration'] = np.nan
        out['cc_roiic_inflection'] = False

    # FCF margin (cash conversion quality)
    if pd.notna(fcf[0]) and pd.notna(rev[0]) and rev[0] > 0:
        out['fcf_margin_latest'] = fcf[0] / rev[0]
    margins = [fcf[i]/rev[i] for i in range(len(yearly_df))
               if pd.notna(fcf[i]) and pd.notna(rev[i]) and rev[i] > 0]
    if margins:
        out['fcf_margin_mean_4y'] = float(np.mean(margins))

    # Cash conversion ratio (FCF / NOPAT): how much of accounting income becomes cash
    conv = [fcf[i]/nopat[i] for i in range(len(yearly_df))
            if pd.notna(fcf[i]) and pd.notna(nopat[i]) and nopat[i] > 0]
    if conv:
        out['cash_conversion_mean_4y'] = float(np.mean(conv))
        out['cash_conversion_min_4y']  = float(np.min(conv))

    return out


def fetch_one(t, limiter, max_retries=3):
    for attempt in range(max_retries):
        limiter.wait()
        try:
            tk = yf.Ticker(t)
            info = tk.info or {}
            mcap = info.get('marketCap') or 0
            if not mcap and not info.get('totalRevenue'):
                return None

            yearly = compute_per_year_metrics(tk.financials, tk.balance_sheet, tk.cashflow)
            if yearly is None or len(yearly) < 2:
                return {'ticker': t, 'name': info.get('shortName'),
                        'mktCap': mcap, 'has_history': False}

            roic_medians = yearly['roic_median_5m'].dropna()
            roic_mean = float(roic_medians.mean()) if len(roic_medians) else np.nan
            roic_min  = float(roic_medians.min())  if len(roic_medians) else np.nan
            roic_max  = float(roic_medians.max())  if len(roic_medians) else np.nan
            roic_std  = float(roic_medians.std())  if len(roic_medians) >= 2 else np.nan
            roic_latest = float(roic_medians.iloc[0]) if len(roic_medians) else np.nan

            agreements = yearly['roic_method_agreement'].dropna()
            agreement_mean = float(agreements.mean()) if len(agreements) else np.nan

            roiic_block = compute_roiic_with_inflection(yearly)
            cash_block = compute_cash_metrics(yearly)

            # Per-method latest values
            latest = yearly.iloc[0] if len(yearly) else {}
            method_latest = {k: float(latest.get(k)) if pd.notna(latest.get(k, np.nan)) else None
                            for k in ['roic_mauboussin','roic_damodaran','roic_greenblatt','roic_croic','roic_dupont']}

            # Structural quality flags
            enduring_strict = (
                len(roic_medians) >= 3 and roic_min >= 0.15 and roic_std <= 0.08
                and agreement_mean >= 0.5
            )
            enduring_loose = (
                len(roic_medians) >= 3 and roic_min >= 0.10 and roic_std <= 0.12
            )

            # Valuation
            debt_now = info.get('totalDebt') or 0
            cash_now = info.get('totalCash') or 0
            ev = (mcap + debt_now - cash_now) if mcap else None
            fcf_now = info.get('freeCashflow') or 0
            ebitda_now = info.get('ebitda') or 0
            ebit_now = info.get('ebit') or (float(latest['op_inc']) if pd.notna(latest.get('op_inc', np.nan)) else None)

            ev_ebit   = (ev / ebit_now) if (ev and ebit_now and ebit_now != 0) else None
            ev_ebitda = (ev / ebitda_now) if (ev and ebitda_now and ebitda_now != 0) else None
            ev_fcf    = (ev / fcf_now) if (ev and fcf_now and fcf_now > 0) else None
            fcf_yield = (fcf_now / mcap) if (mcap and fcf_now) else None

            # Composite compounder score
            cs = 0
            if pd.notna(roic_mean) and roic_mean > 0: cs += min(roic_mean * 150, 35)
            r1 = roiic_block.get('roiic_1y'); r3 = roiic_block.get('roiic_3y')
            if pd.notna(r1) and r1 > 0: cs += min(r1 * 60, 25)
            if pd.notna(r3) and r3 > 0: cs += min(r3 * 30, 15)
            if roiic_block.get('roiic_inflection'): cs += 20
            # Cash-on-cash component (rewards real cash returns)
            cc_mean = cash_block.get('cc_roic_fcf_mean_4y')
            if pd.notna(cc_mean) and cc_mean > 0: cs += min(cc_mean * 100, 20)
            cc_r1 = cash_block.get('cc_roiic_1y')
            if pd.notna(cc_r1) and cc_r1 > 0: cs += min(cc_r1 * 40, 15)
            if cash_block.get('cc_roiic_inflection'): cs += 15
            cash_conv = cash_block.get('cash_conversion_mean_4y')
            if pd.notna(cash_conv) and cash_conv >= 0.8: cs += 5  # high earnings→cash conversion
            if pd.notna(ev_ebit) and ev_ebit > 0: cs += max(0, (15 - ev_ebit))
            if pd.notna(fcf_yield) and fcf_yield > -0.1: cs += min(fcf_yield * 100, 10)
            if enduring_strict: cs += 25
            elif enduring_loose: cs += 10
            if pd.notna(agreement_mean): cs += agreement_mean * 5

            out = {
                'ticker': t,
                'name': info.get('shortName'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'currency': info.get('currency'),
                'mktCap': mcap, 'ev': ev,

                'roic_latest_med': roic_latest,
                'roic_mean_4y_med': roic_mean,
                'roic_min_4y_med': roic_min,
                'roic_max_4y_med': roic_max,
                'roic_std_4y_med': roic_std,
                'roic_method_agreement': agreement_mean,
                'roic_years': len(roic_medians),

                # Per-method latest (for inspection / debugging)
                **method_latest,

                'roiic_1y': roiic_block.get('roiic_1y'),
                'roiic_2y': roiic_block.get('roiic_2y'),
                'roiic_3y': roiic_block.get('roiic_3y'),
                'roiic_acceleration': roiic_block.get('roiic_acceleration'),
                'roiic_inflection': roiic_block.get('roiic_inflection', False),

                # Cash-on-cash returns
                'cc_roic_fcf_latest':   cash_block.get('cc_roic_fcf_latest'),
                'cc_roic_fcf_mean_4y':  cash_block.get('cc_roic_fcf_mean_4y'),
                'cc_roic_fcf_min_4y':   cash_block.get('cc_roic_fcf_min_4y'),
                'cc_roic_fcf_std_4y':   cash_block.get('cc_roic_fcf_std_4y'),
                'cc_roic_ocf_latest':   cash_block.get('cc_roic_ocf_latest'),
                'cc_roic_ocf_mean_4y':  cash_block.get('cc_roic_ocf_mean_4y'),
                'cc_roiic_1y':          cash_block.get('cc_roiic_1y'),
                'cc_roiic_2y':          cash_block.get('cc_roiic_2y'),
                'cc_roiic_3y':          cash_block.get('cc_roiic_3y'),
                'cc_roiic_acceleration':cash_block.get('cc_roiic_acceleration'),
                'cc_roiic_inflection':  cash_block.get('cc_roiic_inflection', False),
                'fcf_margin_latest':    cash_block.get('fcf_margin_latest'),
                'fcf_margin_mean_4y':   cash_block.get('fcf_margin_mean_4y'),
                'cash_conversion_mean_4y': cash_block.get('cash_conversion_mean_4y'),
                'cash_conversion_min_4y':  cash_block.get('cash_conversion_min_4y'),

                'enduring_strict': enduring_strict,
                'enduring_loose': enduring_loose,

                'ebit_now': ebit_now, 'ebitda_now': ebitda_now, 'fcf_now': fcf_now,
                'ev_ebit': ev_ebit, 'ev_ebitda': ev_ebitda, 'ev_fcf': ev_fcf,
                'fcf_yield': fcf_yield,
                'rev_g': info.get('revenueGrowth'),
                'opm': info.get('operatingMargins'),
                'gm': info.get('grossMargins'),
                'insiders': info.get('heldPercentInsiders'),
                'has_history': True,
                'comp_score_v2': round(float(cs), 2),
            }
            return out
        except Exception as e:
            msg = str(e)[:80]
            if '429' in msg or 'rate' in msg.lower() or 'Too Many' in msg:
                time.sleep(2 ** attempt * 3); continue
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
        print(f"[v2] resume: {len(already)} done", file=sys.stderr)
    except Exception: pass

todo = [t for t in syms if t not in already]
print(f"[v2] {len(todo)} tickers · {args.workers} workers · {args.rate} req/s · ETA ~{len(todo)/args.rate/60:.0f}m", file=sys.stderr)

limiter = RateLimiter(args.rate); rows = list(existing); lock = threading.Lock(); done = [0]; start = time.time()

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
            print(f"[v2] {done[0]}/{len(todo)}  kept {len(rows)-len(existing)}  rate {rate:.2f}/s  ETA {eta:.1f}m", file=sys.stderr)

with ThreadPoolExecutor(max_workers=args.workers) as ex:
    futures = [ex.submit(task, t) for t in todo]
    for _ in as_completed(futures): pass

pd.DataFrame(rows).to_csv(args.out, index=False)
df = pd.DataFrame(rows)
if len(df):
    print(f"[v2] DONE: {len(df)} rows", file=sys.stderr)
    h = df['has_history'].fillna(False)
    print(f"  with history: {int(h.sum())}", file=sys.stderr)
    print(f"  enduring strict: {int(df.get('enduring_strict', pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
    print(f"  enduring loose:  {int(df.get('enduring_loose',  pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
    print(f"  ROIIC inflecting: {int(df.get('roiic_inflection', pd.Series(dtype=bool)).fillna(False).sum())}", file=sys.stderr)
