"""Comprehensive data-quality diagnostic — catalog EVERY class of level/ratio
error across the universe, categorised by likely CAUSE, so root fixes are
evidence-driven (not suppositional). Read-only; writes a report.

Causes catalogued:
  A. STALE VINTAGE   — master balance-sheet date older than current EDGAR
  B. IDENTITY BREAK  — hard accounting identities violated (a level is wrong)
  C. CROSS-SOURCE    — EDGAR vs Yahoo disagree beyond tolerance (which to trust)
  D. RATIO<>LEVELS   — a ratio disagrees with its own components (internal)

Output: audit_reports/data_quality_report.txt
"""
import os
import numpy as np
import pandas as pd

OUT = 'audit_reports/data_quality_report.txt'


def _n(df, c):
    return pd.to_numeric(df.get(c), errors='coerce')


def main():
    a = pd.read_csv('asymmetry_global.csv', low_memory=False).drop_duplicates('symbol')
    ef = (pd.read_csv('edgar_universe_facts.csv', low_memory=False)
          .drop_duplicates('symbol').set_index('symbol')) if os.path.exists('edgar_universe_facts.csv') else pd.DataFrame()
    yf = (pd.read_csv('ticker_yf.csv', low_memory=False)
          .drop_duplicates('symbol').set_index('symbol')) if os.path.exists('ticker_yf.csv') else pd.DataFrame()

    lines = []
    def out(s=''):
        lines.append(s)

    N = len(a)
    out(f"DATA-QUALITY AUDIT — {N:,} symbols")
    out("=" * 70)

    # ---- A. STALE VINTAGE (US filers vs current EDGAR) ----
    out("\nA. STALE VINTAGE (master balance-sheet older than current EDGAR)")
    if len(ef):
        us = a[a['src'].astype(str).str.upper() == 'US']
        us = us[us['symbol'].isin(ef.index)]
        mbd = pd.to_datetime(us['balance_sheet_date'], errors='coerce').values
        ebd = pd.to_datetime(pd.Series(ef['assets_end'].reindex(us['symbol']).values), errors='coerce').values
        stale = pd.Series((ebd > mbd), index=us.index).fillna(False)
        out(f"   US filers checked: {len(us):,}")
        out(f"   master vintage OLDER than current EDGAR: {int(stale.sum()):,}")
        for lvl in ['assets', 'equity', 'revenue_ttm', 'cash', 'total_debt']:
            if lvl in us.columns and lvl in ef.columns:
                mv = _n(us, lvl).values
                ev = pd.to_numeric(ef[lvl].reindex(us['symbol']).values, errors='coerce')
                div = pd.Series((np.abs(mv / np.where(ev != 0, ev, np.nan) - 1) > 0.20), index=us.index).fillna(False)
                out(f"     {lvl:12s} diverge >20% vs current EDGAR: {int(div.sum()):,}")

    # ---- B. IDENTITY BREAKS ----
    out("\nB. IDENTITY BREAKS (a level is internally impossible)")
    eq, ast, teq = _n(a, 'equity'), _n(a, 'assets'), _n(a, 'tangible_equity')
    cash, rev, eb = _n(a, 'cash'), _n(a, 'revenue_ttm'), _n(a, 'ebitda_ttm')
    checks = [
        ('equity > assets', (eq > ast * 1.02) & eq.notna() & ast.notna()),
        ('tangible_equity > equity (eq>0)', (teq > eq * 1.02) & (eq > 0)),
        ('cash > assets', (cash > ast * 1.02) & cash.notna() & ast.notna()),
        ('ebitda > 2x revenue', (eb > rev * 2.0) & (rev > 0)),
    ]
    for name, mask in checks:
        m = mask.fillna(False)
        us_n = int((m & (a['src'].astype(str).str.upper() == 'US')).sum())
        out(f"   {name:34s}: {int(m.sum()):4d}  (US: {us_n}, non-US: {int(m.sum())-us_n})")

    # ---- C. CROSS-SOURCE (EDGAR vs Yahoo) ----
    out("\nC. CROSS-SOURCE DISAGREEMENT (EDGAR vs Yahoo, US filers)")
    if len(ef) and len(yf):
        us = a[a['src'].astype(str).str.upper() == 'US']
        idx = us['symbol']
        pairs = [
            ('revenue_ttm', 'yf_revenue'),
            ('ebitda_ttm', 'yf_ebitda'),
            ('cash', 'yf_cash'),
            ('total_debt', 'yf_total_debt'),
        ]
        for elvl, ylvl in pairs:
            if elvl in ef.columns and ylvl in yf.columns:
                ev = pd.to_numeric(ef[elvl].reindex(idx).values, errors='coerce')
                yv = pd.to_numeric(yf[ylvl].reindex(idx).values, errors='coerce')
                ok = (~np.isnan(ev)) & (~np.isnan(yv)) & (ev != 0)
                disagree = np.abs(yv[ok] / ev[ok] - 1) > 0.25
                out(f"   {elvl:12s} vs {ylvl:16s}: {int(disagree.sum()):4d} disagree >25%  "
                    f"({100*disagree.mean():.0f}% of {int(ok.sum())})")

    # ---- D. RATIO vs its own COMPONENTS ----
    out("\nD. RATIO <> LEVELS (ratio disagrees with its own components)")
    mc = _n(a, 'market_cap')
    pb = _n(a, 'pb')
    ev = _n(a, 'enterprise_value')
    debt = _n(a, 'total_debt')
    pb_impl = (mc / eq.where(eq > 0))
    ev_impl = (mc + debt - cash)
    for name, cur, impl in [('pb vs mcap/equity', pb, pb_impl),
                            ('EV vs mcap+debt-cash', ev, ev_impl)]:
        d = (np.abs(cur / impl.where(impl != 0) - 1) > 0.25) & cur.notna() & impl.notna()
        out(f"   {name:26s}: {int(d.fillna(False).sum()):,}")

    os.makedirs('audit_reports', exist_ok=True)
    with open(OUT, 'w') as fh:
        fh.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print(f"\nwrote {OUT}")


if __name__ == '__main__':
    main()
