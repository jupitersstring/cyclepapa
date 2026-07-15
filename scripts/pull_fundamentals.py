#!/usr/bin/env python3
"""Pull yfinance .info fundamentals for a universe and dump CSV."""
import argparse, sys, time, warnings
import pandas as pd, yfinance as yf
warnings.filterwarnings('ignore')

ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--sleep', type=float, default=0.25)
ap.add_argument('--checkpoint', type=int, default=100)
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).unique().tolist()
print(f"Fundamentals: {len(syms)} tickers", file=sys.stderr)

rows = []
for i, t in enumerate(syms):
    try:
        info = yf.Ticker(t).info
        if not info.get('totalRevenue') and not info.get('marketCap'):
            continue
        mcap = info.get('marketCap') or 0
        debt = info.get('totalDebt') or 0
        cash = info.get('totalCash') or 0
        ev = (mcap + debt - cash) if mcap else None
        fcf = info.get('freeCashflow') or 0
        ebitda = info.get('ebitda') or 0
        ebit = info.get('ebit')
        rows.append({
            'ticker': t,
            'name': info.get('shortName'),
            'industry': info.get('industry'),
            'sector': info.get('sector'),
            'currency': info.get('currency'),
            'mktCap': mcap, 'ev': ev,
            'rev': info.get('totalRevenue'),
            'gm': info.get('grossMargins'),
            'opm': info.get('operatingMargins'),
            'roe': info.get('returnOnEquity'),
            'roa': info.get('returnOnAssets'),
            'rev_g': info.get('revenueGrowth'),
            'earn_g': info.get('earningsGrowth'),
            'fcf': fcf,
            'fcf_yield': (fcf / mcap) if (mcap and fcf) else None,
            'ebitda': ebitda,
            'ev_ebitda': (ev / ebitda) if (ebitda and ev) else None,
            'ev_ebit': (ev / ebit) if (ebit and ev) else None,
            'pe': info.get('trailingPE'),
            'fpe': info.get('forwardPE'),
            'pb': info.get('priceToBook'),
            'ps': info.get('priceToSalesTrailing12Months'),
            'net_debt': debt - cash,
            'nd_ebitda': ((debt - cash) / ebitda) if ebitda else None,
            'insiders': info.get('heldPercentInsiders'),
            'div_yield': info.get('dividendYield'),
            'beta': info.get('beta'),
        })
    except Exception:
        pass
    time.sleep(args.sleep)
    if (i+1) % args.checkpoint == 0:
        pd.DataFrame(rows).to_csv(args.out, index=False)
        print(f"  {i+1}/{len(syms)} | with-data {len(rows)}", file=sys.stderr)

pd.DataFrame(rows).to_csv(args.out, index=False)
print(f"DONE: {len(rows)} -> {args.out}", file=sys.stderr)
