"""EV/EBITDA + Sales multiple-compression screener.

Same intuition as multiple_compression_screener.py but anchored on
enterprise-level multiples (EV/EBITDA, EV/Sales) and on sales growth.
The setup: SALES or EBITDA growing AND the multiple has CONTRACTED --
stock cheaper now than a year ago even though the operating base
expanded.

Per ticker (using EDGAR XBRL when available, falls back to yfinance):
  rev_now    = LTM revenue (last 4Q sum)
  rev_y_ago  = LTM revenue 4Q earlier (non-overlapping)
  sales_g    = (rev_now - rev_y_ago) / |rev_y_ago|

  ebitda_now / ebitda_y_ago / ebitda_g  (computed from EDGAR OpInc + D&A)

  price_now, price_y_ago (from cached daily close)
  price_chg  = price_now/price_y_ago - 1

  ev_ebitda_now    = info.enterpriseToEbitda
  ev_ebitda_y_ago  = approximation:
                       EV_y_ago = EV_now * price_y/price_now  (debt approx constant)
                       EBITDA_y_ago = (above)
                       EV/EBITDA_y_ago = EV_y_ago / EBITDA_y_ago

  ps_now           = info.priceToSalesTrailing12Months
  ps_y_ago_implied = ps_now * (price_y/price_now) * (sales_now/sales_y_ago)
                       (per-share approx; assumes shares roughly constant)

  sma_200w         = mean of last 200 weekly closes
  below_200w       = price_now < sma_200w

Default filter:
  market_cap > 500M
  AND (sales_g > 0.05 OR ebitda_g > 0.05)         # actually growing
  AND (ev_ebitda_change_pct < -10 OR ps_change_pct < -10
       OR price_chg < sales_g - 0.10)              # multiple compressed 10pp+

Output: results_ev_compression/{all.csv, screener.csv}
"""
from __future__ import annotations
import argparse, json, gzip, re
from pathlib import Path
from typing import Optional
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_ev_compression'); OUTDIR.mkdir(exist_ok=True)


def _safe(t: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def load_price(ticker: str) -> Optional[pd.Series]:
    p = CACHE / f'{_safe(ticker)}__price.parquet'
    if not p.exists(): return None
    try:
        df = pd.read_parquet(p)
        if df.empty or 'Close' not in df.columns: return None
        s = pd.to_numeric(df['Close'], errors='coerce').dropna()
        if getattr(s.index, 'tz', None) is not None:
            s.index = s.index.tz_localize(None)
        return s.sort_index()
    except Exception:
        return None


def load_info(ticker: str) -> dict:
    p = CACHE / f'{_safe(ticker)}__info_metrics.parquet'
    if not p.exists(): return {}
    try:
        d = pd.read_parquet(p)
        return d.iloc[0].to_dict() if not d.empty else {}
    except Exception:
        return {}


def load_yf_income_cashflow(ticker: str) -> dict:
    """Cached yfinance income/cashflow (shallow, 5-7 quarters)."""
    out = {}
    for kind in ('income', 'cashflow'):
        p = CACHE / f'{_safe(ticker)}__{kind}.parquet'
        if not p.exists(): continue
        try:
            df = pd.read_parquet(p)
            if not df.empty:
                out[kind] = df
        except Exception: pass
    return out


def load_edgar_metrics(cik: int) -> dict[str, pd.Series]:
    """Pull revenue, op_income, d_and_a quarterly series from EDGAR cache."""
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return {}
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception:
        return {}

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

    out = {
        'revenue':   get(['RevenueFromContractWithCustomerExcludingAssessedTax',
                          'Revenues','SalesRevenueNet']),
        'op_income': get(['OperatingIncomeLoss']),
        'd_and_a':   get(['DepreciationDepletionAndAmortization',
                          'DepreciationAndAmortization']),
    }
    return out


# Build CIK→ticker map once
_CIK_MAP = None
def cik_for(ticker: str) -> Optional[int]:
    global _CIK_MAP
    if _CIK_MAP is None:
        try:
            with open(EDGAR / 'company_tickers.json') as f:
                raw = json.load(f)
            _CIK_MAP = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}
        except Exception:
            _CIK_MAP = {}
    return _CIK_MAP.get(ticker.upper())


def get_rev_ebitda_series(ticker: str) -> tuple[pd.Series, pd.Series]:
    """Return (revenue_series, ebitda_series) — prefers EDGAR, falls back to yfinance."""
    cik = cik_for(ticker)
    if cik is not None:
        m = load_edgar_metrics(cik)
        rev = m.get('revenue', pd.Series(dtype=float))
        op = m.get('op_income', pd.Series(dtype=float))
        da = m.get('d_and_a', pd.Series(dtype=float))
        if not op.empty and not da.empty:
            idx = op.index.union(da.index)
            ebitda = op.reindex(idx).add(da.reindex(idx).abs(), fill_value=np.nan).dropna()
        else:
            ebitda = pd.Series(dtype=float)
        if not rev.empty or not ebitda.empty:
            return rev, ebitda
    # Fallback: yfinance income (shallow)
    funds = load_yf_income_cashflow(ticker)
    inc = funds.get('income', pd.DataFrame())
    rev = pd.Series(dtype=float); ebitda = pd.Series(dtype=float)
    if not inc.empty:
        for tag in ('Total Revenue','Operating Revenue','Revenue'):
            if tag in inc.index:
                rev = pd.to_numeric(inc.loc[tag], errors='coerce').dropna()
                rev.index = pd.to_datetime(rev.index, errors='coerce')
                rev = rev[~rev.index.isna()].sort_index()
                break
        for tag in ('EBITDA','Normalized EBITDA'):
            if tag in inc.index:
                ebitda = pd.to_numeric(inc.loc[tag], errors='coerce').dropna()
                ebitda.index = pd.to_datetime(ebitda.index, errors='coerce')
                ebitda = ebitda[~ebitda.index.isna()].sort_index()
                break
    return rev, ebitda


def analyze(ticker: str) -> Optional[dict]:
    price = load_price(ticker)
    if price is None or len(price) < 260: return None

    rev, ebitda = get_rev_ebitda_series(ticker)
    if rev.empty and ebitda.empty: return None

    info = load_info(ticker)
    rec = {'ticker': ticker}

    # Build LTM series for revenue and EBITDA
    def ltm_yoy(series):
        if series is None or series.empty or len(series) < 8: return None
        ltm = series.rolling(4).sum().dropna()
        if len(ltm) < 5: return None
        return float(ltm.iloc[-1]), float(ltm.iloc[-5])

    rev_pair = ltm_yoy(rev)
    if rev_pair:
        rev_now, rev_y_ago = rev_pair
        rec['rev_now_ltm'] = rev_now
        rec['rev_y_ago_ltm'] = rev_y_ago
        rec['sales_growth_pct'] = (rev_now - rev_y_ago)/abs(rev_y_ago)*100 if rev_y_ago != 0 else float('nan')

    eb_pair = ltm_yoy(ebitda)
    if eb_pair:
        eb_now, eb_y_ago = eb_pair
        rec['ebitda_now_ltm'] = eb_now
        rec['ebitda_y_ago_ltm'] = eb_y_ago
        rec['ebitda_growth_pct'] = (eb_now - eb_y_ago)/abs(eb_y_ago)*100 if eb_y_ago != 0 else float('nan')

    # Price now vs ~12 mo ago
    price_now = float(price.iloc[-1])
    target = price.index[-1] - pd.Timedelta(days=365)
    prev = price[price.index <= target]
    if prev.empty: return None
    price_y_ago = float(prev.iloc[-1])
    rec['price_now'] = price_now
    rec['price_y_ago'] = price_y_ago
    rec['price_chg_pct'] = (price_now/price_y_ago - 1) * 100 if price_y_ago>0 else float('nan')

    # EV/EBITDA now and approximated year ago
    ev_ebitda_now = info.get('enterpriseToEbitda')
    try: ev_ebitda_now = float(ev_ebitda_now)
    except (TypeError, ValueError): ev_ebitda_now = float('nan')
    rec['ev_ebitda_now'] = ev_ebitda_now

    if pd.notna(ev_ebitda_now) and 'ebitda_y_ago_ltm' in rec and rec['ebitda_y_ago_ltm'] > 0:
        ev_now = info.get('enterpriseValue')
        try: ev_now = float(ev_now)
        except (TypeError, ValueError): ev_now = float('nan')
        if pd.notna(ev_now) and ev_now > 0 and price_y_ago > 0:
            # Approximate: EV moves roughly with market cap (debt assumed stable)
            mcap_now = info.get('marketCap')
            try: mcap_now = float(mcap_now)
            except (TypeError, ValueError): mcap_now = float('nan')
            if pd.notna(mcap_now) and mcap_now > 0:
                mcap_y_ago = mcap_now * (price_y_ago / price_now)
                ev_y_ago = ev_now - mcap_now + mcap_y_ago  # debt unchanged
                ev_ebitda_y_ago = ev_y_ago / rec['ebitda_y_ago_ltm']
                rec['ev_ebitda_y_ago'] = ev_ebitda_y_ago
                rec['ev_ebitda_change_pct'] = (ev_ebitda_now - ev_ebitda_y_ago)/ev_ebitda_y_ago*100

    # P/S now and approximated year ago
    ps_now = info.get('priceToSalesTrailing12Months')
    try: ps_now = float(ps_now)
    except (TypeError, ValueError): ps_now = float('nan')
    rec['ps_now'] = ps_now
    if pd.notna(ps_now) and 'rev_y_ago_ltm' in rec and rec['rev_y_ago_ltm'] > 0:
        ps_y_ago_implied = ps_now * (price_y_ago/price_now) * (rec['rev_now_ltm']/rec['rev_y_ago_ltm'])
        rec['ps_y_ago_implied'] = ps_y_ago_implied
        if ps_y_ago_implied > 0:
            rec['ps_change_pct'] = (ps_now - ps_y_ago_implied)/ps_y_ago_implied*100

    # Multiple compression on sales: price_chg - sales_growth
    if 'sales_growth_pct' in rec and pd.notna(rec.get('price_chg_pct')):
        rec['compression_vs_sales_pct'] = rec['price_chg_pct'] - rec['sales_growth_pct']
    if 'ebitda_growth_pct' in rec and pd.notna(rec.get('price_chg_pct')):
        rec['compression_vs_ebitda_pct'] = rec['price_chg_pct'] - rec['ebitda_growth_pct']

    # 200-week SMA
    weekly = price.resample('W').last().dropna()
    if len(weekly) >= 50:
        sma_window = min(200, len(weekly))
        sma = float(weekly.tail(sma_window).mean())
        rec['sma_200w'] = sma
        rec['below_200w'] = price_now < sma
        rec['pct_off_sma_200w'] = (price_now/sma - 1) * 100

    rec['market_cap'] = info.get('marketCap')
    rec['pb_now']     = info.get('priceToBook')
    return rec


def main():
    ap = argparse.ArgumentParser()
    # RELAXED for global coverage. Lowered mcap floor, lowered growth bars,
    # lowered compression bar so more EM/Asia names with modest growth + real
    # compression surface.
    ap.add_argument('--min-mcap', type=float, default=200e6)            # RELAXED 500 -> 200
    ap.add_argument('--min-sales-growth', type=float, default=3.0,      # RELAXED 5 -> 3
                    help='min sales LTM YoY (pct)')
    ap.add_argument('--min-ebitda-growth', type=float, default=3.0)     # RELAXED 5 -> 3
    ap.add_argument('--min-compression', type=float, default=5.0,       # RELAXED 10 -> 5
                    help='min absolute compression in pp (price lagged by this much)')
    args = ap.parse_args()

    # Universe = all tickers with cached prices
    tickers = sorted({f.name.split('__')[0] for f in CACHE.glob('*__price.parquet')})
    print(f"Candidate tickers with prices: {len(tickers)}")
    rows = []
    for i, tk in enumerate(tickers):
        yfticker = tk.replace('_','^') if tk.startswith('_') else tk
        r = analyze(yfticker)
        if r is not None: rows.append(r)
        if (i+1) % 500 == 0:
            print(f"  {i+1}/{len(tickers)}  rows={len(rows)}")
    print(f"Computed for {len(rows)} tickers")
    if not rows:
        print("No rows survived filters; nothing to write."); return
    df = pd.DataFrame(rows).set_index('ticker')
    df.to_csv(OUTDIR / 'all.csv')

    # Filter: real cap + sales OR EBITDA growth + compression
    f = df[df['market_cap'].fillna(0) > args.min_mcap].copy()
    growing = (
        (f.get('sales_growth_pct', 0).fillna(-999) > args.min_sales_growth)
        | (f.get('ebitda_growth_pct', 0).fillna(-999) > args.min_ebitda_growth)
    )
    compressed = (
        (f.get('ev_ebitda_change_pct', 0).fillna(0) < -args.min_compression)
        | (f.get('ps_change_pct', 0).fillna(0) < -args.min_compression)
        | (f.get('compression_vs_sales_pct', 0).fillna(0) < -args.min_compression)
        | (f.get('compression_vs_ebitda_pct', 0).fillna(0) < -args.min_compression)
    )
    f = f[growing & compressed]
    f = f.sort_values('compression_vs_ebitda_pct')
    f.to_csv(OUTDIR / 'screener.csv')

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print(f"\n=== SALES OR EBITDA GROWING + EV/EBITDA OR P/S CHEAPER ===")
    print(f"Count: {len(f)} names\n")

    cols = ['sales_growth_pct','ebitda_growth_pct','price_chg_pct',
            'compression_vs_sales_pct','compression_vs_ebitda_pct',
            'ev_ebitda_now','ev_ebitda_y_ago','ev_ebitda_change_pct',
            'ps_now','ps_change_pct','market_cap','pb_now',
            'pct_off_sma_200w','below_200w']
    cols = [c for c in cols if c in f.columns]
    show = f.head(40)[cols].copy()
    if 'market_cap' in show:
        show['market_cap'] = (pd.to_numeric(show['market_cap'], errors='coerce')/1e9).round(2)
    for c in cols:
        if c in show and c != 'market_cap' and c != 'below_200w':
            show[c] = pd.to_numeric(show[c], errors='coerce').round(1)
    print(show.to_string())

    print()
    print("=== BELOW 200-WEEK SMA SUBSET ===")
    bs = f[f.get('below_200w', False) == True].head(25)
    print(f"Count: {len(bs)}\n")
    show2 = bs[cols].copy()
    if 'market_cap' in show2:
        show2['market_cap'] = (pd.to_numeric(show2['market_cap'], errors='coerce')/1e9).round(2)
    for c in cols:
        if c in show2 and c != 'market_cap' and c != 'below_200w':
            show2[c] = pd.to_numeric(show2[c], errors='coerce').round(1)
    print(show2.to_string())


if __name__ == '__main__':
    main()
