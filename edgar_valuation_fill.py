"""Compute EV/EBITDA, P/E, EV/Sales, P/S, P/B from SEC EDGAR companyfacts
for any US ticker we have. Fills gaps in the yfinance info_metrics cache
where Yahoo returns empty (or our cached fetch missed).

Logic:
  EBITDA (LTM)    = OperatingIncomeLoss + DepreciationDepletionAndAmortization
                    (summed across last 4 quarterly periods)
  Revenue (LTM)   = Revenues / RevenueFromContractWithCustomer / SalesRevenueNet
                    summed across last 4 quarters
  Net Income (LTM)= NetIncomeLoss summed across last 4 quarters
  Net Debt (now)  = LongTermDebt + ShortTermBorrowings - CashAndCashEquivalents

Market data we DON'T have in EDGAR (need yfinance):
  Current price -> we use the cached price.parquet if available
  Shares outstanding -> EDGAR has WeightedAverageNumberOfDilutedSharesOutstanding

So Market Cap = current_price × shares_outstanding (both from our caches).
EV = Market Cap + Net Debt + Minority Interest.
EV/EBITDA = EV / EBITDA_LTM
P/E       = current_price / (NI_LTM / shares_outstanding)
P/B       = Market Cap / StockholdersEquity
P/S       = Market Cap / Revenue_LTM
EV/Sales  = EV / Revenue_LTM

For each US ticker with EDGAR data, we write a parquet with these computed
metrics. The workbook enrichment falls back to this when info_metrics has
empties.

Output: .cache/edgar_metrics/<ticker>__edgar_metrics.parquet
"""
from __future__ import annotations
import json, gzip, sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4

EDGAR_CACHE = Path('.cache/edgar')
YF_CACHE = Path('.cache/yf')
OUT_CACHE = Path('.cache/edgar_metrics'); OUT_CACHE.mkdir(parents=True, exist_ok=True)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _quarterly_sum_last4(facts: dict, tags: list) -> tuple[float | None, pd.Timestamp | None]:
    """Sum the most recent 4 quarterly values across tag fallbacks."""
    for tag in tags:
        node = facts.get(tag)
        if not node: continue
        recs = node.get('units', {}).get('USD')
        if not recs: continue
        qs = _quarterly_records(recs)
        if not qs: continue
        q, a = _series_from_records(qs)
        s = _derive_q4(q, a)
        if s.empty or len(s) < 4: continue
        last4 = s.tail(4)
        return float(last4.sum()), pd.Timestamp(last4.index[-1])
    return None, None


def _instant_latest(facts: dict, tags: list) -> float | None:
    """Latest instant value (point-in-time) across tag fallbacks."""
    for tag in tags:
        node = facts.get(tag)
        if not node: continue
        recs = node.get('units', {}).get('USD')
        if not recs: continue
        # Instant facts have 'end' but no 'start'
        inst = [r for r in recs if 'start' not in r and 'end' in r]
        if not inst: continue
        inst.sort(key=lambda r: (str(r.get('end','')), str(r.get('filed',''))))
        return float(inst[-1].get('val'))
    return None


def _shares_outstanding(facts: dict) -> float | None:
    """Most recent diluted shares from quarterly filings."""
    for tag in ('WeightedAverageNumberOfDilutedSharesOutstanding',
                'WeightedAverageNumberOfSharesOutstandingBasic',
                'CommonStockSharesOutstanding'):
        node = facts.get(tag)
        if not node: continue
        recs = node.get('units', {}).get('shares')
        if not recs: continue
        # Use latest 10-Q or 10-K value
        valid = [r for r in recs if str(r.get('form','')).startswith(('10-Q','10-K'))]
        if not valid: continue
        valid.sort(key=lambda r: (str(r.get('end','')), str(r.get('filed',''))))
        return float(valid[-1].get('val'))
    return None


def _price_now(ticker: str) -> float | None:
    """Latest close from the cached price parquet."""
    p = YF_CACHE / f'{_safe(ticker)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df.empty or 'Close' not in df.columns: return None
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        return float(s.iloc[-1]) if not s.empty else None
    except Exception:
        return None


def compute_metrics(ticker: str, facts: dict) -> dict:
    gaap = facts.get('us-gaap', {})
    # Operating income (LTM) + D&A (LTM) -> EBITDA
    op_inc_ltm, _ = _quarterly_sum_last4(gaap, ['OperatingIncomeLoss'])
    da_ltm, _ = _quarterly_sum_last4(gaap, [
        'DepreciationDepletionAndAmortization',
        'DepreciationAndAmortization',
        'Depreciation',
    ])
    ebitda_ltm = None
    if op_inc_ltm is not None and da_ltm is not None:
        ebitda_ltm = op_inc_ltm + abs(da_ltm)
    elif op_inc_ltm is not None:
        ebitda_ltm = op_inc_ltm
    revenue_ltm, _ = _quarterly_sum_last4(gaap, [
        'Revenues',
        'RevenueFromContractWithCustomerExcludingAssessedTax',
        'RevenueFromContractWithCustomerIncludingAssessedTax',
        'SalesRevenueNet',
    ])
    net_income_ltm, _ = _quarterly_sum_last4(gaap, ['NetIncomeLoss'])
    # Balance sheet (latest instant)
    cash_now = _instant_latest(gaap, [
        'CashAndCashEquivalentsAtCarryingValue',
        'Cash',
        'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
    ])
    longterm_debt = _instant_latest(gaap, [
        'LongTermDebtNoncurrent',
        'LongTermDebt',
        'LongTermDebtAndCapitalLeaseObligations',
    ])
    shortterm_debt = _instant_latest(gaap, [
        'ShortTermBorrowings',
        'CommercialPaper',
        'LongTermDebtCurrent',
    ])
    minority_interest = _instant_latest(gaap, [
        'MinorityInterest',
        'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
    ])
    stockholders_equity = _instant_latest(gaap, [
        'StockholdersEquity',
        'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
    ])
    shares = _shares_outstanding(gaap)
    price = _price_now(ticker)

    market_cap = price * shares if (price and shares) else None
    net_debt = None
    if longterm_debt is not None or shortterm_debt is not None:
        net_debt = ((longterm_debt or 0) + (shortterm_debt or 0)) - (cash_now or 0)
    ev = None
    if market_cap is not None and net_debt is not None:
        ev = market_cap + net_debt + (minority_interest or 0)

    out = {
        'ticker': ticker,
        'currentPrice_edgar': price,
        'sharesOutstanding_edgar': shares,
        'marketCap_edgar': market_cap,
        'enterpriseValue_edgar': ev,
        'totalRevenue_edgar_ltm': revenue_ltm,
        'ebitda_edgar_ltm': ebitda_ltm,
        'netIncome_edgar_ltm': net_income_ltm,
        'stockholdersEquity_edgar': stockholders_equity,
        'netDebt_edgar': net_debt,
        'cash_edgar': cash_now,
    }
    # Derived ratios. Allow negative-denominator values (yfinance does the
    # same — shows e.g. EV/EBITDA = -29.3 for biotechs burning cash) so the
    # ratio's sign is meaningful and screens that filter on loss-makers can
    # still see it.
    if ev is not None and ebitda_ltm is not None and ebitda_ltm != 0:
        out['enterpriseToEbitda_edgar'] = ev / ebitda_ltm
    if ev is not None and revenue_ltm and revenue_ltm > 0:
        out['enterpriseToRevenue_edgar'] = ev / revenue_ltm
    if market_cap and revenue_ltm and revenue_ltm > 0:
        out['priceToSalesTrailing12Months_edgar'] = market_cap / revenue_ltm
    if market_cap and stockholders_equity is not None and stockholders_equity != 0:
        out['priceToBook_edgar'] = market_cap / stockholders_equity
    if price and shares and net_income_ltm is not None and net_income_ltm != 0:
        eps_ltm = net_income_ltm / shares
        if eps_ltm != 0:
            out['trailingPE_edgar'] = price / eps_ltm
    return out


def main():
    # Get the SEC ticker map to translate CIK -> ticker
    with open(EDGAR_CACHE / 'company_tickers.json') as f:
        raw = json.load(f)
    cik_to_ticker = {int(r['cik_str']): r['ticker'].upper() for r in raw.values()}

    files = list(EDGAR_CACHE.glob('CF_*.json.gz'))
    print(f'Computing valuation metrics from {len(files):,} EDGAR files...')

    rows = []
    for i, f in enumerate(files):
        m = f.name.split('_')[1].split('.')[0]
        cik = int(m)
        ticker = cik_to_ticker.get(cik)
        if not ticker: continue
        try:
            with gzip.open(f, 'rt') as fp:
                facts = json.load(fp)['facts']
        except Exception:
            continue
        try:
            m = compute_metrics(ticker, facts)
            # Keep the row if we computed ANY useful metric (was: only kept
            # rows with at least one of EV/EBITDA, P/E, P/B; that dropped
            # loss-makers + thin-data tickers entirely instead of preserving
            # the underlying fundamentals we extracted).
            useful_keys = [k for k in m if k != 'ticker' and m.get(k) is not None]
            if useful_keys:
                rows.append(m)
        except Exception:
            continue
        if (i + 1) % 500 == 0:
            print(f'  {i+1:,}/{len(files):,}  computed={len(rows):,}')

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CACHE.parent.parent / 'results_peg' / 'edgar_valuation.csv', index=False)
    df.to_parquet(OUT_CACHE / 'all.parquet', compression='snappy')
    print(f'\nWrote {len(df):,} tickers with computed valuation metrics')
    if not df.empty:
        print('\nField coverage:')
        for c in ['enterpriseToEbitda_edgar','trailingPE_edgar','priceToBook_edgar',
                   'priceToSalesTrailing12Months_edgar','enterpriseToRevenue_edgar',
                   'marketCap_edgar','enterpriseValue_edgar']:
            if c in df.columns:
                n = df[c].notna().sum()
                print(f'  {c:<45} {n:>5,}  ({n*100/len(df):>4.0f}%)')


if __name__ == '__main__':
    main()
