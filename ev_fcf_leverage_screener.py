"""EV/FCF operating-leverage screener.

Mirror of operating_leverage_screener.py but anchored on FCF (and FCF
margin) instead of EBITDA. Finds names where:

  1. Sales are growing meaningfully (>15% LTM YoY)
  2. FCF margin is in the "leverage window" -- just turned positive or
     low single-digits (-5% to +10%). Cash flow has crossed the
     breakeven point but margins are still depressed, so each
     incremental dollar of revenue should flow through to FCF at the
     incremental contribution margin, not the current low average.
  3. EV/FCF is reasonable on growth (EV/FCF / sales-growth low) -- the
     market hasn't yet capitalized the leverage runway.
  4. FCF growing YoY (direction confirmation -- not just a one-off
     positive print).

Per ticker:
  rev_now, rev_y_ago, sales_g     # LTM YoY
  fcf_now, fcf_y_ago, fcf_g       # LTM YoY
  fcf_margin_now = fcf_now / rev_now
  ev_now (from yfinance.info)
  ev_fcf_now = ev_now / fcf_now   (when fcf_now > 0)
  ev_fcf_per_growth = ev_fcf_now / sales_g_pct

  margin_runway_pp = max(0, 15 - fcf_margin*100)
  leverage_score = sales_g_pct * margin_runway_pp / max(0.5, |fcf_margin|)

Default filter:
  market_cap > $200M
  sales_g > 15%
  fcf_margin in [-5%, +10%]
  fcf_growth > 0
  ev_fcf_now in [0, 40] (cheap absolute)

Output: results_ev_fcf_leverage/screener.csv
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
from typing import Optional
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_ev_fcf_leverage'); OUTDIR.mkdir(exist_ok=True)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def load_info(ticker: str) -> dict:
    p = CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if not p.exists(): return {}
    try:
        d = pd.read_parquet(p)
        return d.iloc[0].to_dict() if not d.empty else {}
    except Exception: return {}


_CIK_MAP = None
def cik_for(ticker: str) -> Optional[int]:
    global _CIK_MAP
    if _CIK_MAP is None:
        try:
            with open(EDGAR / 'company_tickers.json') as f:
                raw = json.load(f)
            _CIK_MAP = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}
        except Exception: _CIK_MAP = {}
    return _CIK_MAP.get(ticker.upper())


def load_edgar_revfcf(cik: int) -> tuple[pd.Series, pd.Series]:
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return pd.Series(dtype=float), pd.Series(dtype=float)
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception:
        return pd.Series(dtype=float), pd.Series(dtype=float)

    import sys; sys.path.insert(0, '.')
    from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4

    def get(candidates):
        for tag in candidates:
            node = facts.get(tag)
            if not node: continue
            recs = node.get('units', {}).get('USD')
            if not recs: continue
            qs = _quarterly_records(recs)
            if not qs: continue
            q, a = _series_from_records(qs)
            return _derive_q4(q, a)
        return pd.Series(dtype=float)

    rev = get(['RevenueFromContractWithCustomerExcludingAssessedTax',
                'Revenues','SalesRevenueNet'])
    ocf = get(['NetCashProvidedByUsedInOperatingActivities',
                'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'])
    capex = get(['PaymentsToAcquirePropertyPlantAndEquipment',
                  'PaymentsToAcquireProductiveAssets'])
    if ocf.empty or capex.empty:
        return rev, pd.Series(dtype=float)
    idx = ocf.index.union(capex.index)
    fcf = (ocf.reindex(idx) - capex.reindex(idx).abs()).dropna()
    return rev, fcf


def get_rev_fcf(ticker: str) -> tuple[pd.Series, pd.Series]:
    cik = cik_for(ticker)
    if cik is not None:
        rev, fcf = load_edgar_revfcf(cik)
        if not rev.empty or not fcf.empty:
            return rev, fcf
    # Fallback: yfinance shallow
    p_inc = CACHE / f'{_safe(ticker)}__income.parquet'
    p_cf  = CACHE / f'{_safe(ticker)}__cashflow.parquet'
    rev = pd.Series(dtype=float); fcf = pd.Series(dtype=float)
    if p_inc.exists():
        try:
            inc = pd.read_parquet(p_inc)
            for tag in ('Total Revenue','Operating Revenue','Revenue'):
                if tag in inc.index:
                    rev = pd.to_numeric(inc.loc[tag], errors='coerce').dropna()
                    rev.index = pd.to_datetime(rev.index, errors='coerce')
                    rev = rev[~rev.index.isna()].sort_index()
                    break
        except Exception: pass
    if p_cf.exists():
        try:
            cf = pd.read_parquet(p_cf)
            for tag in ('Free Cash Flow',):
                if tag in cf.index:
                    fcf = pd.to_numeric(cf.loc[tag], errors='coerce').dropna()
                    fcf.index = pd.to_datetime(fcf.index, errors='coerce')
                    fcf = fcf[~fcf.index.isna()].sort_index()
                    break
            if fcf.empty:
                ocf = pd.Series(dtype=float); capex = pd.Series(dtype=float)
                for tag in ('Operating Cash Flow','Cash Flow From Continuing Operating Activities',
                            'Total Cash From Operating Activities'):
                    if tag in cf.index:
                        ocf = pd.to_numeric(cf.loc[tag], errors='coerce').dropna()
                        ocf.index = pd.to_datetime(ocf.index, errors='coerce'); ocf = ocf[~ocf.index.isna()].sort_index()
                        break
                for tag in ('Capital Expenditure','Capital Expenditures'):
                    if tag in cf.index:
                        capex = pd.to_numeric(cf.loc[tag], errors='coerce').dropna()
                        capex.index = pd.to_datetime(capex.index, errors='coerce'); capex = capex[~capex.index.isna()].sort_index()
                        break
                if not ocf.empty and not capex.empty:
                    idx = ocf.index.union(capex.index)
                    fcf = (ocf.reindex(idx) + capex.reindex(idx).fillna(0)).dropna()
        except Exception: pass
    return rev, fcf


def analyze(ticker: str) -> Optional[dict]:
    rev, fcf = get_rev_fcf(ticker)
    if rev.empty or fcf.empty: return None
    if len(rev) < 8 or len(fcf) < 8: return None

    rev_sorted = rev.sort_index().rolling(4).sum().dropna()
    fcf_sorted = fcf.sort_index().rolling(4).sum().dropna()
    if len(rev_sorted) < 5 or len(fcf_sorted) < 5: return None

    rev_now = float(rev_sorted.iloc[-1]); rev_y_ago = float(rev_sorted.iloc[-5])
    fcf_now = float(fcf_sorted.iloc[-1]); fcf_y_ago = float(fcf_sorted.iloc[-5])
    if rev_now <= 0 or rev_y_ago <= 0: return None

    sales_g_pct = (rev_now - rev_y_ago) / rev_y_ago * 100
    fcf_margin_now = fcf_now / rev_now * 100
    fcf_margin_y_ago = fcf_y_ago / rev_y_ago * 100 if rev_y_ago > 0 else float('nan')
    fcf_margin_change_pp = fcf_margin_now - fcf_margin_y_ago

    if abs(fcf_y_ago) > 0:
        fcf_growth_pct = (fcf_now - fcf_y_ago) / abs(fcf_y_ago) * 100
    else:
        fcf_growth_pct = float('nan')

    info = load_info(ticker)
    mcap = info.get('marketCap')
    ev = info.get('enterpriseValue')
    try: ev = float(ev) if ev is not None else float('nan')
    except (TypeError, ValueError): ev = float('nan')

    rec: dict = {
        'ticker': ticker,
        'rev_now_M':           rev_now / 1e6,
        'rev_y_ago_M':         rev_y_ago / 1e6,
        'sales_growth_pct':    sales_g_pct,
        'fcf_now_M':           fcf_now / 1e6,
        'fcf_y_ago_M':         fcf_y_ago / 1e6,
        'fcf_growth_pct':      fcf_growth_pct,
        'fcf_margin_now_pct':  fcf_margin_now,
        'fcf_margin_y_ago_pct': fcf_margin_y_ago,
        'margin_expansion_pp': fcf_margin_change_pp,
    }

    if pd.notna(ev) and ev > 0 and fcf_now > 0:
        rec['ev_fcf_now'] = ev / fcf_now
        if sales_g_pct > 1:
            rec['ev_fcf_per_growth'] = (ev / fcf_now) / sales_g_pct
    rec['ev_now'] = ev
    rec['market_cap'] = mcap
    rec['pb_now']   = info.get('priceToBook')
    rec['ps_now']   = info.get('priceToSalesTrailing12Months')
    rec['ev_ebitda_now'] = info.get('enterpriseToEbitda')
    rec['sector']   = info.get('sector')
    rec['industry'] = info.get('industry')

    rec['margin_runway_pp'] = max(0.0, 15.0 - fcf_margin_now)
    rec['leverage_score'] = sales_g_pct * rec['margin_runway_pp'] / max(0.5, abs(fcf_margin_now))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--min-sales-growth', type=float, default=15.0)
    ap.add_argument('--margin-floor', type=float, default=-5.0)
    ap.add_argument('--margin-ceiling', type=float, default=10.0)
    ap.add_argument('--max-ev-fcf', type=float, default=40.0)
    ap.add_argument('--require-fcf-growth', action='store_true', default=True)
    args = ap.parse_args()

    tickers = sorted({f.name.split('__')[0] for f in CACHE.glob('*__price.parquet')})
    print(f"Candidate tickers: {len(tickers)}")
    rows = []
    for i, tk in enumerate(tickers):
        yfticker = tk.replace('_','^') if tk.startswith('_') else tk
        r = analyze(yfticker)
        if r is not None: rows.append(r)
        if (i+1) % 500 == 0:
            print(f"  {i+1}/{len(tickers)}  rows={len(rows)}")
    if not rows:
        print("No rows survived filters; nothing to write."); return
    df = pd.DataFrame(rows).set_index(\'ticker\')
    df.to_csv(OUTDIR / 'all.csv')
    print(f"\nWith data: {len(df)}")

    f = df[
        (df['market_cap'].fillna(0) > args.min_mcap)
        & (df['sales_growth_pct'] > args.min_sales_growth)
        & (df['fcf_margin_now_pct'].between(args.margin_floor, args.margin_ceiling))
        & (df['fcf_growth_pct'].fillna(-999) > 0)
        & (df['ev_fcf_now'].between(0, args.max_ev_fcf))
    ].copy()
    f = f.sort_values('leverage_score', ascending=False)
    f.to_csv(OUTDIR / 'screener.csv')

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print(f"\n=== EV/FCF OPERATING-LEVERAGE SETUP ===")
    print(f"Filter: cap>${args.min_mcap/1e6:.0f}M, sales>{args.min_sales_growth}%, "
          f"FCF margin in [{args.margin_floor}, {args.margin_ceiling}]%, "
          f"FCF growing, EV/FCF<{args.max_ev_fcf}")
    print(f"Count: {len(f)}\n")
    cols = ['sales_growth_pct','fcf_margin_now_pct','margin_expansion_pp',
            'fcf_growth_pct','rev_now_M','fcf_now_M',
            'ev_fcf_now','ev_fcf_per_growth','ev_ebitda_now','ps_now',
            'leverage_score','market_cap','sector']
    show = f.head(40)[cols].copy()
    show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in cols:
        if c in show and c != 'market_cap' and c != 'sector':
            show[c] = pd.to_numeric(show[c],errors='coerce').round(2)
    if 'sector' in show:
        show['sector'] = show['sector'].apply(lambda x: x[:18] if isinstance(x,str) else x)
    print(show.to_string())

    # Also surface: high FCF leverage on EV/FCF basis with growth
    print()
    print("=== CHEAP ABSOLUTE EV/FCF (<15) with sales growing + FCF growing ===")
    cheap = df[
        (df['market_cap'].fillna(0) > args.min_mcap)
        & (df['sales_growth_pct'] > 5)
        & (df['fcf_growth_pct'].fillna(-999) > 0)
        & (df['ev_fcf_now'].between(0, 15))
    ].copy().sort_values('ev_fcf_now')
    print(f"Count: {len(cheap)}\n")
    show2 = cheap.head(30)[cols].copy()
    show2['market_cap'] = (pd.to_numeric(show2['market_cap'],errors='coerce')/1e9).round(2)
    for c in cols:
        if c in show2 and c != 'market_cap' and c != 'sector':
            show2[c] = pd.to_numeric(show2[c],errors='coerce').round(2)
    if 'sector' in show2:
        show2['sector'] = show2['sector'].apply(lambda x: x[:18] if isinstance(x,str) else x)
    print(show2.to_string())


if __name__ == '__main__':
    main()
