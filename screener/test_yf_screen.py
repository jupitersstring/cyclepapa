"""Offline validation of yf_screen's computational core against
synthetic frames shaped exactly like yfinance output (rows = CamelCase
statement labels, columns = period-end Timestamps, capex/buybacks negative).
"""
import numpy as np
import pandas as pd
import yf_screen as m

def dates(n, freq='YE'):
    return pd.date_range('2021-12-31', periods=n, freq=freq)

fails = 0
def check(name, cond):
    global fails
    status = 'PASS' if cond else 'FAIL'
    if not cond: fails += 1
    print(f"  [{status}] {name}")

# --- 1. pick(): fuzzy label matching across yfinance variants -----------
df_a = pd.DataFrame([[1, 2]], index=['Operating Cash Flow'], columns=dates(2))
df_b = pd.DataFrame([[3, 4]], index=['OperatingCashFlow'], columns=dates(2))
df_c = pd.DataFrame([[5, 6]], index=['Total Cash From Operating Activities'], columns=dates(2))
check('pick matches spaced label',    m.pick(df_a, *m.ALIAS['ocf']) is not None)
check('pick matches camelcase label', m.pick(df_b, *m.ALIAS['ocf']) is not None)
check('pick matches legacy label',    m.pick(df_c, *m.ALIAS['ocf']) is not None)
check('pick returns None on miss',    m.pick(df_a, 'EBITDA') is None)

# --- 2. 200-week-low distance ------------------------------------------
idx = pd.date_range('2021-07-01', periods=260, freq='W')
px = pd.Series(np.linspace(100, 40, 260), index=idx)   # falls to 40 = the low
check('at-the-low -> dist 0.0', abs(m.pct_above_200w_low(px) - 0.0) < 1e-9)
px2 = pd.Series(100.0, index=idx); px2.iloc[-50] = 40.0; px2.iloc[-1] = 46.0
check('15% above low', abs(m.pct_above_200w_low(px2) - 0.15) < 1e-6)
short = px.tail(100)
check('history < min_weeks -> None', m.pct_above_200w_low(short) is None)

# --- 3. FCF from cashflow: direct row preferred, else OCF+capex --------
cols = dates(5)
cf = pd.DataFrame(
    [[60, 70, 80, 90, 100],          # FreeCashFlow, oldest->newest
     [80, 90, 100, 110, 120],        # Operating Cash Flow
     [-30, -30, -30, -30, -30]],     # Capital Expenditure (negative)
    index=['Free Cash Flow', 'Operating Cash Flow', 'Capital Expenditure'],
    columns=cols)
got = m.fcf_series_from_cashflow(cf)
check('direct FCF row preferred, newest first', got[:2] == [100.0, 90.0])

cf2 = cf.drop(index='Free Cash Flow')
got2 = m.fcf_series_from_cashflow(cf2)
check('OCF+capex fallback (120-30=90)', got2[0] == 90.0 and len(got2) == 5)

# --- 4. TTM buyback: negatives only, abs, last 4 quarters --------------
qcols = pd.date_range('2025-06-30', periods=6, freq='QE')
qcf = pd.DataFrame(
    [[-999, -999, -250, -250, -250, -250],   # buybacks; oldest 2 ignored
     [500, 500, 50, 0, 30, 0]],              # issuance; oldest 2 ignored
    index=['Repurchase Of Capital Stock', 'Issuance Of Capital Stock'],
    columns=qcols)
bb = m.ttm_flow(qcf, m.ALIAS['buyback'], 'neg')
iss = m.ttm_flow(qcf, m.ALIAS['issuance'], 'pos')
check('TTM buyback = 1000 (last 4q, abs)', bb == 1000.0)
check('TTM issuance = 80 (positives only)', iss == 80.0)

# --- 5. Net debt: TotalDebt preferred; LT+ST fallback; cash netted -----
bcols = dates(2)
bs1 = pd.DataFrame([[500, 480], [120, 100]],
                   index=['Total Debt', 'Cash And Cash Equivalents'], columns=bcols)
check('net debt = 500-120 (newest col)', m.net_debt_from_bs(bs1) == 380.0)
bs2 = pd.DataFrame([[400, 380], [80, 70], [90, 60]],
                   index=['Long Term Debt', 'Current Debt',
                          'Cash Cash Equivalents And Short Term Investments'],
                   columns=bcols)
check('LT+ST fallback = 400+80-90', m.net_debt_from_bs(bs2) == 390.0)

# --- 6. EBITDA 5y average ----------------------------------------------
inc = pd.DataFrame([[200, 180, 160, 140, 120]], index=['EBITDA'], columns=dates(5))
check('EBITDA 5y avg = 160', m.ebitda_5y_avg(inc) == 160.0)

# --- 7. End-to-end scoring math on a synthetic passer ------------------
row = m.score_row(dist=0.08, norm_y=0.11, ttm_y=0.02, bb_y=0.05,
                  net_bb_y=0.043, nd_e=2.1, mcap=4.2e9,
                  meta={'ticker': 'TEST', 'name': 'Testco', 'sector': 'X',
                        'exchange': 'NYSE'})
check('score_row fields', row['norm_fcf_yield_5y_pct'] == 11.0
      and row['pct_above_200w_low'] == 8.0
      and row['market_cap_usd_m'] == 4200)

print(f"\n{'ALL TESTS PASSED' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(fails)
