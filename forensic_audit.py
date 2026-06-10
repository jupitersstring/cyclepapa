"""Forensic audit of asymmetric-equity candidates.

Layers explicit verification over the screener outputs:
  - Pulls EDGAR LTM data when available (matches screener methodology)
  - Adds independent yfinance Q-vs-Q4 single-quarter YoY for cross-check
  - Computes GROSS margin Δ (the screener didn't have this)
  - Cross-references against known deep-research findings (PRCH accounting
    recharacterization, AORT cyber-comp, AVNW revenue decline, etc.)
  - Issues a CONFIRMED / CAVEAT / FALSE_POSITIVE verdict per name

By default audits the curated KNOWN_FINDINGS keys plus the manual ★★★★★
list. With `--expand N`, also audits the top-N rows from
results_peg/best_undervalued.csv (Issue 19), so the verdict==PENDING
expansion covers the broader candidate population beyond the hand-curated
deep-research set. Stale/circular rows are filtered out before expansion.

Outputs:
  results_forensic/audit.csv          — curated names with deep-research verdict
  results_forensic/audit_expanded.csv — bulk expansion (PENDING by default)
"""
from __future__ import annotations
import argparse, json, gzip, sys
from pathlib import Path
import numpy as np, pandas as pd

CACHE = Path('.cache/yf')
EDGAR = Path('.cache/edgar')
PEG_DIR = Path('results_peg')
OUTDIR = Path('results_forensic'); OUTDIR.mkdir(exist_ok=True)


def safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def col(df, candidates):
    if df is None or df.empty: return None
    items_in_index = (
        pd.api.types.is_datetime64_any_dtype(df.columns)
        or any(isinstance(c, pd.Timestamp) for c in df.columns[:3])
    )
    for c in candidates:
        if items_in_index:
            matches = [ix for ix in df.index if str(ix) == c or str(ix).startswith(c[:10])]
            if matches:
                s = pd.to_numeric(df.loc[matches[0]], errors='coerce').dropna()
                if not s.empty: return s.sort_index()
        else:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors='coerce').dropna()
                if not s.empty: return s.sort_index()
    return None


def load(tk, slot):
    p = CACHE / f'{safe(tk)}__{slot}.parquet'
    if not p.exists(): return None
    try:
        d = pd.read_parquet(p)
        return d if not d.empty else None
    except Exception: return None


def info(tk):
    d = load(tk, 'info_metrics')
    return d.iloc[0].to_dict() if d is not None else {}


_CIK_MAP = None
def cik_for(ticker):
    global _CIK_MAP
    if _CIK_MAP is None:
        try:
            with open(EDGAR / 'company_tickers.json') as f:
                raw = json.load(f)
            _CIK_MAP = {r['ticker'].upper(): int(r['cik_str']) for r in raw.values()}
        except Exception: _CIK_MAP = {}
    return _CIK_MAP.get(ticker.upper())


def edgar_quarterly(tk):
    """Return dict with quarterly Revenue, OpIncome, D&A, Shares series from EDGAR."""
    cik = cik_for(tk)
    if cik is None: return {}
    p = EDGAR / f'CF_{cik:010d}.json.gz'
    if not p.exists(): return {}
    try:
        with gzip.open(p, 'rt') as f:
            facts = json.load(f)['facts'].get('us-gaap', {})
    except Exception: return {}
    import sys; sys.path.insert(0, '.')
    from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4
    def get(cands, unit='USD'):
        for tag in cands:
            node = facts.get(tag)
            if not node: continue
            recs = node.get('units', {}).get(unit)
            if not recs: continue
            qs = _quarterly_records(recs)
            if not qs: continue
            q, a = _series_from_records(qs)
            return _derive_q4(q, a)
        return pd.Series(dtype=float)
    return {
        'revenue': get(['Revenues','RevenueFromContractWithCustomerExcludingAssessedTax',
                         'RevenueFromContractWithCustomerIncludingAssessedTax','SalesRevenueNet']),
        'op_inc':  get(['OperatingIncomeLoss']),
        'd_and_a': get(['DepreciationAndAmortization','DepreciationDepletionAndAmortization',
                          'DepreciationAmortizationAndAccretionNet']),
        'gross':   get(['GrossProfit']),
    }


def ltm_yoy(series):
    """LTM (4-quarter rolling sum) latest vs 4Q ago. Returns (cur_ltm, prior_ltm, growth_pct)."""
    if series is None or series.empty: return None, None, None
    s = series.sort_index()
    ltm = s.rolling(4).sum().dropna()
    if len(ltm) < 5: return None, None, None
    cur = float(ltm.iloc[-1]); prv = float(ltm.iloc[-5])
    g = (cur/prv - 1) * 100 if prv != 0 else None
    return cur, prv, g


def yfin_q_yoy(tk, slot, field_candidates):
    """yfinance single-quarter YoY (Q vs Q-4) cross-check."""
    df = load(tk, slot)
    if df is None: return None
    s = col(df, field_candidates)
    if s is None or len(s) < 5: return None
    cur, prv = float(s.iloc[-1]), float(s.iloc[-5])
    return (cur/prv - 1) * 100 if prv > 0 else None


# Deep-research verdicts (qualitative layer)
KNOWN_FINDINGS = {
    'PRCH': ('FALSE_POSITIVE',
             'Margin expansion is HOA→PIRE Reciprocal accounting recharacterization, not operating leverage. '
             'Real revenue growth +15.6% not +42%. Texas 57% concentration with hurricane season ahead.'),
    'AORT': ('FALSE_POSITIVE',
             '+18% sales is cybersecurity-comp recovery (Q1 25 depressed by Nov 2024 cyber attack). '
             'Mgmt CUT guidance at Q1. Endospan added $135M debt without US revenue until 2027. '
             'Zero insider buying through 57% drawdown.'),
    'AVNW': ('CAVEAT',
             'Revenue actually declining (-11% Q-vs-Q-4 in yfinance). Gross margin -5.6pp. '
             'EBITDA expansion if any is purely OpEx-driven and not sustainable.'),
    'WEST': ('CAVEAT',
             'Gross margin -5.1pp despite +48% sales. Coffee commodity pass-through. '
             'EBITDA expansion narrow; quality of revenue growth is questionable.'),
    'ADUS': ('CAVEAT',
             'Gross margin -1.0pp — labor cost pressure on HR-intensive home-care business. '
             'EBITDA expansion driven by Gentiva integration synergies, not pricing.'),
    'IBEX': ('CAVEAT',
             'Gross margin -0.8pp + EBITDA margin essentially flat. CX outsourcing margin pressure. '
             'Sales growth real but operating leverage thesis not visible in margins.'),
    'TREE': ('CONFIRMED',
             'Sales +36.5% Q-vs-Q-4 confirmed in yfinance. EDGAR-based deep research showed EBITDA +71% '
             'on real volume + sticky 26% Insurance margin. CEO Lebda death Oct 2025 is the discount '
             'driver, not operating issues. Mgmt RAISED FY26 guide to $152-162M EBITDA. <0.5x P/S.'),
    'QNST': ('CONFIRMED_WITH_CAVEAT',
             'EDGAR LTM shows +28% sales but yfinance cache only has data through Q4 2025 '
             '(stale; shows +1.9% Q-vs-Q-4). HomeBuddy M&A drove half the Home segment growth. '
             'Q2 GAAP NI inflated by tax benefit. Core auto-insurance operating leverage real.'),
    'NRDS': ('CONFIRMED',
             'Sales +22.6% Q-vs-Q-4 (yfinance cache). Gross +3.1pp + EBITDA +6.4pp confirms '
             'structural operating leverage at NerdWallet. Stock -21% / P/S 0.6.'),
    'EVER': ('CONFIRMED_WITH_CAVEAT',
             'Sales +14.5% Q-vs-Q-4 confirms growth. Gross margin +1.0pp. yfinance shows EBITDA '
             'margin -2.3pp Q-vs-Q-4 but EDGAR LTM-vs-LTM shows expansion — methodology gap. '
             'Auto insurance ad budgets are cyclical.'),
    'LWAY': ('CONFIRMED',
             'Sales +18% confirmed (Q-vs-Q-4). Gross +2.4pp AND EBITDA +5.1pp — clean structural '
             'operating leverage from mix shift to higher-margin kefir/probiotic products. '
             'Small ($370M cap) Consumer Staples that nobody covers.'),
    'KRUS': ('CONFIRMED',
             'Sales +23%. Gross +1.1pp + EBITDA +3.8pp — real unit economics improving. Restaurant.'),
    'ROAD': ('CONFIRMED_WITH_CAVEAT',
             'Sales +35% from backlog conversion. Gross +0.4pp + EBITDA -0.2pp (yfinance). '
             'Operating leverage thesis weak in single-Q data; LTM may be cleaner.'),
    'ALHC': ('CONFIRMED',
             'Sales +33%; gross +0.3pp + EBITDA +1.6pp — modest margin expansion at scale. '
             'Medicare Advantage with real volume growth.'),
    'TRNS': ('CONFIRMED_WITH_CAVEAT',
             'Sales +25% strong; gross +0.6pp + EBITDA -3.0pp Q-vs-Q-4 — margin under pressure. '
             'Operating leverage thesis is in doubt.'),
    'BJRI': ('CONFIRMED',
             'Sales modest +3.2% Q-vs-Q-4 but Q1 26 comps +2.4% / traffic +2.2% reported by mgmt '
             '(best in casual dining). Gross +0.7pp + EBITDA +2.3pp. Activist Shaich/Act III at '
             '8.8%, fresh CEO Tick, $83M buyback runway. Story is governance-driven.'),
    'INBK': ('CONFIRMED',
             'Sales +20.4% Q-vs-Q-4. EBITDA margin +3.4pp (op margin flat). yfinance has no '
             'gross profit for bank. Founder Becker bought Oct 2025 at $18.60; 13D activist '
             'filer surfaced; trades sharp discount to $41.41 book.'),
    'GRWG': ('CAVEAT',
             'Sales only +7.5% Q-vs-Q-4 (not the screener number). Gross MARGIN -1.8pp + EBITDA '
             'margin -9.5pp (!) — both contracting. The thesis is purely the $46M cash balance '
             '= 38% of market cap + CEO Lampert open-market buy. Fundamentals are still working '
             'against them.'),
    'CFBK': ('CONFIRMED_WITH_CAVEAT',
             'No income statement data in cache (zero quarters). Bank — yfinance income depth '
             'is unusual. Director Hoeweler buy + 5% buyback through Aug 2026 are real. '
             'Quantitative signal cannot be reverified from cache for this name.'),
    'SMTI': ('FALSE_POSITIVE_DATA',
             'No income statement data in cache; P/E 384x; 1y -25%. Sanara MedTech is a '
             'speculative micro-cap; the screener signal cannot be substantiated.'),
    'AIOT': ('CAVEAT',
             'Sales only +6.6% Q-vs-Q-4 (not +47% from screener). Gross +0pp, EBITDA +20pp '
             'from very low base — large % swing on small absolute numbers. Story not as '
             'clean as the screener suggests.'),
    'AXTI': ('CAVEAT',
             '1y price perf +9143% is a yfinance data error (price scale corruption — '
             '$632M secondary at $64.25 likely confused the chart). Revenue declining. '
             'Should be excluded from screens until price data is rebased.'),
    'GNE': ('CAVEAT',
             'Gross margin -4.7pp; restatement overhang; Howard Jonas controls ~61% voting. '
             'Operating leverage if any is offset by accounting/governance noise.'),
}


CURATED_AUDIT_LIST = sorted(KNOWN_FINDINGS.keys()) + [
    'CFBK','BJRI','INBK','GRWG',  # ★★★★★ from-today
    'TREE','NRDS','QNST','EVER','LWAY','KRUS',  # confirmed structural op leverage
]
CURATED_AUDIT_LIST = sorted(set(CURATED_AUDIT_LIST))


def expansion_tickers(top_n=200, min_mcap=200e6, max_data_age_days=180,
                      max_rev_growth=300):
    """Pick the top-N tickers from best_undervalued for bulk auditing.

    Filters out the obvious data-error rows (rev growth >300%, ridiculous
    multiples) and stale rows (>180d if the column exists), then takes the
    top N by EV_GP_over_GPg_ltm (cheapest on gross-profit growth).
    """
    p = PEG_DIR / 'best_undervalued.csv'
    if not p.exists():
        return []
    df = pd.read_csv(p)
    # market cap filter
    if 'market_cap' in df.columns:
        df = df[pd.to_numeric(df['market_cap'], errors='coerce').fillna(0) >= min_mcap]
    # data freshness (only if peg_screener was run with Issue 6 columns)
    if 'data_age_days' in df.columns:
        df = df[pd.to_numeric(df['data_age_days'], errors='coerce').fillna(99999) <= max_data_age_days]
    if 'is_stale' in df.columns:
        df = df[~df['is_stale'].fillna(False).astype(bool)]
    if 'ebitda_is_circular' in df.columns:
        df = df[~df['ebitda_is_circular'].fillna(False).astype(bool)]
    # cap insane growth (obvious data error)
    if 'rev_growth_ltm_pct' in df.columns:
        rg = pd.to_numeric(df['rev_growth_ltm_pct'], errors='coerce')
        df = df[(rg.isna()) | ((rg >= 5) & (rg <= max_rev_growth))]
    # sort by EV_GP_over_GPg_ltm ascending (cheapest first)
    df = df.sort_values('EV_GP_over_GPg_ltm', na_position='last')
    return df['ticker'].astype(str).head(top_n).tolist()


def audit_one(tk):
    out = {'ticker': tk}
    i = info(tk)
    out['market_cap_B'] = (i.get('marketCap') or 0) / 1e9 if i.get('marketCap') else None
    out['ps_now'] = i.get('priceToSalesTrailing12Months')
    out['ev_ebitda'] = i.get('enterpriseToEbitda')

    # EDGAR LTM-based
    e = edgar_quarterly(tk)
    rev_ltm_now, rev_ltm_prv, sales_ltm_yoy = ltm_yoy(e.get('revenue'))
    out['edgar_sales_ltm_yoy_pct'] = sales_ltm_yoy

    # yfinance Q vs Q-4
    out['yf_sales_qyoy_pct'] = yfin_q_yoy(tk, 'income', ['Total Revenue','Revenue'])
    out['yf_gross_qyoy_pct'] = yfin_q_yoy(tk, 'income', ['Gross Profit'])
    # gross margin Δ
    inc = load(tk, 'income')
    rev = col(inc, ['Total Revenue','Revenue'])
    gross = col(inc, ['Gross Profit'])
    if rev is not None and gross is not None and len(rev) >= 5 and len(gross) >= 5:
        common = rev.index.intersection(gross.index)
        if len(common) >= 5:
            r = rev.reindex(common); g = gross.reindex(common)
            if r.iloc[-1] > 0 and r.iloc[-5] > 0:
                out['gross_margin_chg_pp'] = (float(g.iloc[-1])/float(r.iloc[-1]) - float(g.iloc[-5])/float(r.iloc[-5])) * 100

    # Verdict overlay
    verdict, notes = KNOWN_FINDINGS.get(tk, ('PENDING', 'No deep-research finding yet.'))
    out['verdict'] = verdict
    out['notes'] = notes
    return out


def _audit_batch(tickers, label):
    rows = []
    for i, t in enumerate(tickers):
        try:
            rows.append(audit_one(t))
        except Exception as exc:
            print(f'  {t}: {exc}', file=sys.stderr)
        if (i+1) % 50 == 0:
            print(f'  {label} {i+1}/{len(tickers)} processed', file=sys.stderr)
    return pd.DataFrame(rows).set_index('ticker') if rows else pd.DataFrame()


def _sort_by_verdict(df):
    order = {'CONFIRMED': 0, 'CONFIRMED_WITH_CAVEAT': 1, 'CAVEAT': 2,
             'FALSE_POSITIVE': 3, 'FALSE_POSITIVE_DATA': 4, 'PENDING': 5}
    df = df.copy()
    df['_v'] = df['verdict'].map(order).fillna(99)
    return df.sort_values('_v').drop(columns=['_v'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--expand', type=int, default=0,
                    help='Also audit top-N rows from best_undervalued.csv (Issue 19). 0 disables.')
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--max-data-age-days', type=int, default=180)
    args = ap.parse_args()

    # ---- Curated audit (existing behavior) ----
    print(f'Curated audit: {len(CURATED_AUDIT_LIST)} tickers...', file=sys.stderr)
    df = _audit_batch(CURATED_AUDIT_LIST, 'curated')
    if not df.empty:
        df = _sort_by_verdict(df)
        # Display
        disp = df.copy()
        for c in ('edgar_sales_ltm_yoy_pct','yf_sales_qyoy_pct','yf_gross_qyoy_pct',
                  'gross_margin_chg_pp','ps_now','ev_ebitda','market_cap_B'):
            if c in disp: disp[c] = pd.to_numeric(disp[c], errors='coerce').round(1)
        pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
        pd.set_option('display.max_colwidth', 110)
        print(disp[['verdict','market_cap_B','edgar_sales_ltm_yoy_pct','yf_sales_qyoy_pct',
                    'gross_margin_chg_pp','ps_now','ev_ebitda','notes']].to_string())
        df.to_csv(OUTDIR / 'audit.csv')
        print(f'\nWritten to {OUTDIR / "audit.csv"}', file=sys.stderr)

    # ---- Bulk expansion (Issue 19) ----
    if args.expand > 0:
        candidates = expansion_tickers(top_n=args.expand,
                                       min_mcap=args.min_mcap,
                                       max_data_age_days=args.max_data_age_days)
        # Avoid duplicating curated names
        curated = set(CURATED_AUDIT_LIST)
        expansion_list = [t for t in candidates if t not in curated]
        print(f'\nExpansion audit: {len(expansion_list)} additional tickers '
              f'(of top {args.expand} requested)...', file=sys.stderr)
        df_x = _audit_batch(expansion_list, 'expansion')
        if not df_x.empty:
            df_x = _sort_by_verdict(df_x)
            df_x.to_csv(OUTDIR / 'audit_expanded.csv')
            print(f'Written to {OUTDIR / "audit_expanded.csv"}', file=sys.stderr)
            # Summary
            counts = df_x['verdict'].value_counts()
            print(f'\nExpansion verdict distribution:', file=sys.stderr)
            for v, n in counts.items():
                print(f'  {v}: {n}', file=sys.stderr)


if __name__ == '__main__':
    main()
