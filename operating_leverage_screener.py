"""Operating-leverage screener.

Finds names with:
  1. Real sales growth (LTM YoY > threshold) -- top line is expanding
  2. EBITDA margin in the "leverage window" -- near zero or just turned
     profitable (-5% to +15%), so fixed-cost absorption is just kicking in
  3. Low P/S relative to sales growth (PSG analogue: P/S divided by
     sales growth rate -- lower = more growth per dollar of sales multiple)

The thesis: when a high-growth business crosses from loss to small profit,
each incremental dollar of sales flows through to EBITDA at a much higher
incremental rate than the current average margin. Margin compression
during the growth phase has kept the current margin low, but the runway
to "normal" margins (15-25%) means EBITDA can grow much faster than
sales for several years.

Per ticker:
  rev_now    = LTM revenue
  rev_y_ago  = LTM revenue 4Q earlier
  sales_g    = (rev_now / rev_y_ago - 1)
  ebitda_now = LTM EBITDA
  ebitda_margin_now = ebitda_now / rev_now
  ps_now     = P/S from yfinance.info
  psg        = ps_now / (sales_g * 100)   -- PEG-style, lower = better
  ev_sales   = info.enterpriseToRevenue
  ev_sales_per_g = ev_sales / (sales_g * 100)

  -- "leverage potential" score (higher = more upside):
     leverage_score = sales_g_pct / max(0.5, ebitda_margin_now*100)
     -- high sales growth + low margin = huge potential

Default filter:
  market_cap > $200M
  sales_g > 15%
  ebitda_margin in [-5%, +15%]
  EBITDA growth > 0 (margin trending up, not collapsing)
  PSG < 0.3 (i.e., P/S 0.3 with 100% sales growth, or P/S 3 with 1000% growth)

Output: results_operating_leverage/screener.csv
"""
from __future__ import annotations
import argparse, json, gzip
from pathlib import Path
from typing import Optional
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
OUTDIR = Path('results_operating_leverage'); OUTDIR.mkdir(exist_ok=True)


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


def load_edgar_metrics(cik: int) -> dict[str, pd.Series]:
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return {}
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception: return {}

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

    return {
        'revenue':   get(['RevenueFromContractWithCustomerExcludingAssessedTax',
                          'Revenues','SalesRevenueNet']),
        'op_income': get(['OperatingIncomeLoss']),
        'd_and_a':   get(['DepreciationDepletionAndAmortization',
                          'DepreciationAndAmortization']),
        'gross':     get(['GrossProfit']),
    }


def get_series(ticker: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (revenue_series_quarterly, ebitda_series_quarterly, gross_series_quarterly)."""
    cik = cik_for(ticker)
    if cik is not None:
        m = load_edgar_metrics(cik)
        rev = m.get('revenue', pd.Series(dtype=float))
        op = m.get('op_income', pd.Series(dtype=float))
        da = m.get('d_and_a', pd.Series(dtype=float))
        gross = m.get('gross', pd.Series(dtype=float))
        if not op.empty and not da.empty:
            idx = op.index.union(da.index)
            ebitda = op.reindex(idx).add(da.reindex(idx).abs(), fill_value=np.nan).dropna()
        else:
            ebitda = pd.Series(dtype=float)
        if not rev.empty or not ebitda.empty:
            return rev, ebitda, gross

    # Fallback: yfinance income (shallow, schema-aware)
    p = CACHE / f'{_safe(ticker)}__income.parquet'
    if not p.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)
    try:
        inc = pd.read_parquet(p)
    except Exception:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)
    if inc.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    items_in_index = (
        pd.api.types.is_datetime64_any_dtype(inc.columns)
        or any(isinstance(c, pd.Timestamp) for c in inc.columns[:3])
    )
    def _series(cands):
        for tag in cands:
            if items_in_index:
                matches = [ix for ix in inc.index if str(ix) == tag or str(ix).startswith(tag[:10])]
                if matches:
                    s = pd.to_numeric(inc.loc[matches[0]], errors='coerce').dropna()
                    if not s.empty: return s.sort_index()
            else:
                if tag in inc.columns:
                    s = pd.to_numeric(inc[tag], errors='coerce').dropna()
                    if not s.empty: return s.sort_index()
        return pd.Series(dtype=float)

    rev = _series(['Total Revenue','Operating Revenue','Revenue'])
    ebitda = _series(['EBITDA','Normalized EBITDA'])
    gross = _series(['Gross Profit'])
    return rev, ebitda, gross


def analyze(ticker: str) -> Optional[dict]:
    rev, ebitda, gross = get_series(ticker)
    if rev.empty or len(rev) < 8: return None

    info = load_info(ticker)
    rev_sorted = rev.sort_index()
    rev_ltm = rev_sorted.rolling(4).sum().dropna()
    if len(rev_ltm) < 5: return None
    rev_now = float(rev_ltm.iloc[-1])
    rev_y_ago = float(rev_ltm.iloc[-5])
    if rev_now <= 0 or rev_y_ago <= 0: return None
    sales_g_pct = (rev_now - rev_y_ago) / rev_y_ago * 100

    # EBITDA LTM
    if ebitda.empty or len(ebitda) < 4:
        return None
    eb_sorted = ebitda.sort_index()
    eb_ltm = eb_sorted.rolling(4).sum().dropna()
    eb_now = float(eb_ltm.iloc[-1])
    eb_margin_now = eb_now / rev_now * 100
    eb_y_ago = float(eb_ltm.iloc[-5]) if len(eb_ltm) >= 5 else float('nan')
    if pd.notna(eb_y_ago) and abs(eb_y_ago) > 0:
        eb_growth_pct = (eb_now - eb_y_ago) / abs(eb_y_ago) * 100
        eb_margin_y_ago = eb_y_ago / rev_y_ago * 100
        margin_expansion_pp = eb_margin_now - eb_margin_y_ago
    else:
        eb_growth_pct = float('nan')
        eb_margin_y_ago = float('nan')
        margin_expansion_pp = float('nan')

    rec = {
        'ticker': ticker,
        'rev_now_M':       rev_now / 1e6,
        'sales_growth_pct': sales_g_pct,
        'ebitda_now_M':    eb_now / 1e6,
        'ebitda_margin_now_pct': eb_margin_now,
        'ebitda_margin_y_ago_pct': eb_margin_y_ago,
        'margin_expansion_pp': margin_expansion_pp,
        'ebitda_growth_pct': eb_growth_pct,
    }

    # Valuation
    ps = info.get('priceToSalesTrailing12Months')
    try: ps = float(ps) if ps is not None else float('nan')
    except (TypeError, ValueError): ps = float('nan')
    ev_sales = info.get('enterpriseToRevenue')
    try: ev_sales = float(ev_sales) if ev_sales is not None else float('nan')
    except (TypeError, ValueError): ev_sales = float('nan')
    ev_ebitda = info.get('enterpriseToEbitda')
    try: ev_ebitda = float(ev_ebitda) if ev_ebitda is not None else float('nan')
    except (TypeError, ValueError): ev_ebitda = float('nan')

    rec['ps_now'] = ps
    rec['ev_sales_now'] = ev_sales
    rec['ev_ebitda_now'] = ev_ebitda

    # PSG: P/S divided by sales growth rate. < 0.3 = cheap on growth.
    if pd.notna(ps) and sales_g_pct > 1:
        rec['psg'] = ps / sales_g_pct
    if pd.notna(ev_sales) and sales_g_pct > 1:
        rec['ev_sales_per_growth'] = ev_sales / sales_g_pct

    # Gross margin LTM expansion (additional leg — structural vs OpEx-only leverage)
    gross_margin_now = float('nan'); gross_margin_y_ago = float('nan')
    gross_margin_chg_pp = float('nan')
    if gross is not None and not gross.empty:
        g_sorted = gross.sort_index()
        g_ltm = g_sorted.rolling(4).sum().dropna()
        if len(g_ltm) >= 5:
            g_now = float(g_ltm.iloc[-1]); g_y = float(g_ltm.iloc[-5])
            if rev_now > 0 and rev_y_ago > 0:
                gross_margin_now = g_now / rev_now * 100
                gross_margin_y_ago = g_y / rev_y_ago * 100
                gross_margin_chg_pp = gross_margin_now - gross_margin_y_ago
    rec['gross_margin_now_pct'] = gross_margin_now
    rec['gross_margin_chg_pp']  = gross_margin_chg_pp
    rec['structural_op_lev']    = (
        'Y' if pd.notna(gross_margin_chg_pp) and gross_margin_chg_pp > 0
              and pd.notna(margin_expansion_pp) and margin_expansion_pp > 0
        else ('N' if pd.notna(gross_margin_chg_pp) and gross_margin_chg_pp < 0
                     and pd.notna(margin_expansion_pp) and margin_expansion_pp > 0
              else '')
    )

    # Leverage potential score: sales growth × margin runway / current margin
    rec['margin_runway_pp'] = max(0.0, 20.0 - eb_margin_now)
    base_score = sales_g_pct * rec['margin_runway_pp'] / max(0.5, abs(eb_margin_now))
    # Bonus for structural operating leverage (gross AND EBITDA both expanding);
    # penalty when gross margin is contracting (OpEx-only fake leverage)
    gross_bonus = 1.0
    if pd.notna(gross_margin_chg_pp):
        if gross_margin_chg_pp > 1.0: gross_bonus = 1.30
        elif gross_margin_chg_pp > 0: gross_bonus = 1.10
        elif gross_margin_chg_pp < -2.0: gross_bonus = 0.70  # contracting gross = OpEx-only fake
        elif gross_margin_chg_pp < 0: gross_bonus = 0.85
    rec['leverage_score'] = base_score * gross_bonus
    rec['gross_bonus_factor'] = gross_bonus

    rec['market_cap'] = info.get('marketCap')
    rec['pb_now'] = info.get('priceToBook')
    rec['sector'] = info.get('sector')
    rec['industry'] = info.get('industry')
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--min-sales-growth', type=float, default=15.0)
    ap.add_argument('--margin-floor', type=float, default=-5.0, help='min EBITDA margin (pct)')
    ap.add_argument('--margin-ceiling', type=float, default=15.0, help='max EBITDA margin (pct)')
    ap.add_argument('--max-psg', type=float, default=0.5, help='max P/S / sales-growth ratio')
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
    print(f"\nWith data: {len(df)} tickers")

    f = df[
        (df['market_cap'].fillna(0) > args.min_mcap)
        & (df['sales_growth_pct'] > args.min_sales_growth)
        & (df['ebitda_margin_now_pct'].between(args.margin_floor, args.margin_ceiling))
        & (df['ebitda_growth_pct'].fillna(-999) > 0)        # margin trending UP
        & (df['psg'].fillna(99) < args.max_psg)
    ].copy()
    f = f.sort_values('leverage_score', ascending=False)
    f.to_csv(OUTDIR / 'screener.csv')

    pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
    print(f"\n=== OPERATING-LEVERAGE SETUP ===")
    print(f"Filter: cap >${args.min_mcap/1e6:.0f}M, sales growth >{args.min_sales_growth}%, "
          f"EBITDA margin in [{args.margin_floor}%, {args.margin_ceiling}%], "
          f"EBITDA growth >0, PSG < {args.max_psg}")
    print(f"Count: {len(f)}\n")

    cols = ['sales_growth_pct','ebitda_margin_now_pct','margin_expansion_pp',
            'ebitda_growth_pct','rev_now_M','ebitda_now_M',
            'ps_now','psg','ev_sales_now','ev_ebitda_now',
            'leverage_score','market_cap','sector']
    show = f.head(40)[cols].copy()
    show['market_cap'] = (pd.to_numeric(show['market_cap'],errors='coerce')/1e9).round(2)
    for c in ('rev_now_M','ebitda_now_M','ps_now','psg','ev_sales_now','ev_ebitda_now',
              'leverage_score','sales_growth_pct','ebitda_margin_now_pct',
              'margin_expansion_pp','ebitda_growth_pct'):
        if c in show: show[c] = pd.to_numeric(show[c],errors='coerce').round(2)
    if 'sector' in show:
        show['sector'] = show['sector'].apply(lambda x: x[:18] if isinstance(x,str) else x)
    print(show.to_string())


if __name__ == '__main__':
    main()
