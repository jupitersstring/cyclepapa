"""Apply pipeline fixes raised in the audit:

1. FX conversion: every market_cap / revenue_ttm / ebitda_ttm / fcf_ttm
   is local currency. Add a `market_cap_usd` column to asymmetry_global.csv
   so all cross-country comparisons happen in USD.

2. Dedup: NVDR -R.BK wrappers and .BO/.NS dual listings should not
   double-count. Prefer the parent (.BK over -R.BK; .NS over .BO).

3. Verdict conflicts: HBR.L, TUSK, TYGO had two verdicts in the CSV.
   Resolve to the strictest (most recent diligence wins, which is the
   downgrade in each case): HBR.L -> RED, TUSK -> YELLOW, TYGO -> YELLOW.

4. Data anomalies: clip ROCE to [-1, 5]; reject EV/EBIT <= 0 as data
   error; reject ev_ebit < 2 as likely unit / scaling mistake.

5. KPIThreshold tightening: this is done in archetype_tags.py.

6. Alta Fox sector neutral on EXCLUDED: 0.0 -> 0.5 (no claim, not bad).
   Done in alta_fox_score.py.

Outputs:
  asymmetry_global.csv (rewritten with mcap_usd col, dedup applied)
  qualitative_extended_verdicts.csv (conflicts resolved, dated stamps)
  fx_rates_usd.json (already produced)
"""
from __future__ import annotations
import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd


FX_PATH = 'fx_rates_usd.json'


def load_fx() -> dict:
    with open(FX_PATH) as f:
        return json.load(f)


def _country_to_currency(country: str) -> str:
    """Map asymmetry src code to a yartseva-side currency, used as fallback
    when the yartseva file's `currency` column is missing.
    """
    M = {
        'US': 'USD', 'CA': 'CAD',
        'UK': 'GBP', 'IE': 'EUR',
        'DE': 'EUR', 'FR': 'EUR', 'IT': 'EUR', 'NL': 'EUR', 'BE': 'EUR',
        'AT': 'EUR', 'ES': 'EUR', 'PT': 'EUR', 'GR': 'EUR', 'FI': 'EUR',
        'LV': 'EUR', 'LT': 'EUR', 'EE': 'EUR', 'LU': 'EUR', 'MT': 'EUR',
        'CH': 'CHF', 'SE': 'SEK', 'NO': 'NOK', 'DK': 'DKK', 'IS': 'ISK',
        'CZ': 'CZK', 'HU': 'HUF', 'PL': 'PLN', 'RO': 'RON',
        'JP': 'JPY', 'KR': 'KRW', 'HK': 'HKD', 'CN': 'CNY', 'TW': 'TWD',
        'SG': 'SGD', 'TH': 'THB', 'IN': 'INR', 'ID': 'IDR',
        'AU': 'AUD', 'NZ': 'NZD',
        'BR': 'BRL', 'MX': 'MXN', 'CL': 'CLP', 'AR': 'ARS',
        'TR': 'TRY', 'IL': 'ILS', 'ZA': 'ZAR', 'SA': 'SAR', 'MY': 'MYR',
    }
    return M.get((country or '').upper(), 'USD')


def _canonical_symbol(sym: str) -> str:
    """Map listing variants to a canonical symbol used for dedup.
    NVDR Thai -R.BK -> .BK; Indian .BO -> .NS (prefer NSE primary).
    """
    if not isinstance(sym, str):
        return sym
    if sym.endswith('-R.BK'):
        return sym[:-5] + '.BK'
    if sym.endswith('.BO'):
        # prefer NSE if .NS twin exists; otherwise keep .BO as canonical
        return sym  # we'll dedup with a pair-aware step below
    return sym


def dedup_dual_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Remove NVDR wrappers, Indian .BO duals, AND plain same-symbol duplicates.

    The same ticker can appear in multiple per-country yartseva files
    (e.g. FPIP.ST appears in both se_yartseva.csv and se_largecap_yartseva.csv
    because it sits on the Small/Mid Cap boundary; XTB.WA in pl_yartseva +
    pl_largecap + pl_unc; etc.). asymmetry_rank.py concatenates rather than
    dedupes, so without this step downstream rankings double-count.

    Strategy: 1) drop NVDR -R.BK wrappers when parent .BK exists; 2) drop .BO
    when .NS twin exists; 3) drop plain same-symbol rows keeping the one
    with the highest asymmetry_score (most informative measurement).
    """
    n_before = len(df)
    syms = set(df['symbol'].dropna())

    # Thai NVDR: drop -R.BK when .BK exists.
    nvdr_drop = [s for s in syms
                 if isinstance(s, str) and s.endswith('-R.BK')
                 and (s[:-5] + '.BK') in syms]

    # Indian: drop .BO when .NS twin exists.
    bo_drop = [s for s in syms
               if isinstance(s, str) and s.endswith('.BO')
               and (s[:-3] + '.NS') in syms]

    df = df[~df['symbol'].isin(nvdr_drop + bo_drop)].copy()

    # Plain dup dedup: keep the row with the highest asymmetry_score.
    if 'asymmetry_score' in df.columns:
        df = df.sort_values('asymmetry_score', ascending=False) \
               .drop_duplicates('symbol', keep='first')
    else:
        df = df.drop_duplicates('symbol', keep='first')

    print(f'  dedup dropped {len(nvdr_drop)} NVDR -R.BK wrappers '
          f'+ {len(bo_drop)} .BO duals + {n_before - len(df) - len(nvdr_drop) - len(bo_drop)} plain dupes '
          f'= {n_before - len(df)} rows total',
          file=sys.stderr)
    return df


def reject_data_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Clip ROCE and EV/EBIT to plausible ranges.

    ROCE > 500% is almost certainly a unit error or a negative-equity company.
    EV/EBIT < 0 means negative EBIT (allowed but not informative as 'cheap').
    """
    n_before = len(df)

    # Don't drop rows - just nan-out the anomalous values so downstream
    # filters skip them rather than treating bad numbers as good signal.
    if 'roce' in df.columns:
        bad_roce = (df['roce'] > 5.0) | (df['roce'] < -1.0)
        n_roce = int(bad_roce.sum())
        df.loc[bad_roce, 'roce'] = float('nan')
        print(f'  nan-out {n_roce} bad ROCE values (outside [-100 pct, +500 pct])', file=sys.stderr)

    if 'ev_ebit' in df.columns:
        bad_ev = (df['ev_ebit'] < 2.0) & (df['ev_ebit'] >= 0)
        bad_ev_neg = (df['ev_ebit'] < 0)
        n_low = int(bad_ev.sum())
        n_neg = int(bad_ev_neg.sum())
        df.loc[bad_ev, 'ev_ebit'] = float('nan')
        df.loc[bad_ev_neg, 'ev_ebit'] = float('nan')
        print(f'  nan-out {n_low} EV/EBIT in (0, 2) + {n_neg} negative = unit/scaling artifacts',
              file=sys.stderr)

    print(f'  rows preserved: {len(df)} (anomaly cleanup is value-level, not row-level)',
          file=sys.stderr)
    return df


def fx_convert(df: pd.DataFrame, fx: dict) -> pd.DataFrame:
    """Add market_cap_usd, revenue_ttm_usd, ebitda_ttm_usd, fcf_ttm_usd cols.

    Uses the yartseva-side 'currency' column when available; falls back to
    country-code-implied currency from asymmetry's src.
    """
    if 'currency' not in df.columns:
        # Fall back to src-implied currency
        df['currency'] = df.get('src', pd.Series('USD', index=df.index)).map(_country_to_currency)
    else:
        df['currency'] = df['currency'].fillna(
            df.get('src', pd.Series('USD', index=df.index)).map(_country_to_currency)
        )

    # Sub-currency units (London pence, Israeli agora, SA cents, Kuwaiti fils)
    # label the PRICE quote only: the aggregates converted here (market cap,
    # revenue, EBITDA, FCF, EV, net cash, NCAV) are stored in the parent unit.
    # Audit 2026-10: for all 108 names still labelled GBp/ZAC/ILA the local
    # market cap matched FMP's profile market cap (in rand / shekels / pounds)
    # within 10%, and dividing by 100 had crushed Sasol, Sanlam, MTN,
    # AngloGold, Naspers, Standard Bank and Schroders to "micro-caps" in the
    # books. Convert at the parent rate; never divide the aggregates.
    SUBUNIT = {'GBp': 'GBP', 'GBX': 'GBP', 'ZAc': 'ZAR', 'ZAC': 'ZAR',
               'ILA': 'ILS', 'ILa': 'ILS', 'KWf': 'KWD'}

    def _rate(ccy):
        return fx.get(SUBUNIT.get(ccy, ccy), np.nan)

    df['fx_to_usd'] = df['currency'].map(_rate).fillna(1.0)

    for col in ('market_cap', 'revenue_ttm', 'ebitda_ttm', 'fcf_ttm',
                'enterprise_value', 'net_cash', 'ncav'):
        if col in df.columns:
            df[col + '_usd'] = df[col] * df['fx_to_usd']

    return df


def apply_fmp_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Fill identity gaps from the cached FMP profile-bulk frames (fmp_bulk.py):
    country (missing for 49% of the universe, 2026-10 audit), industry (14%;
    62% of Korea and India), sector; add isin / cik / fmp_exchange /
    is_actively_trading / is_adr. Existing values are kept; only NaNs fill.
    No-op when the bulk files are absent."""
    import glob as _glob
    files = sorted(_glob.glob(os.path.join('fmp_cache', 'bulk', 'profile-bulk__part-*.parquet')))
    if not files:
        return df
    try:
        p = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    except Exception:
        return df
    p = p[p.symbol.notna()].drop_duplicates('symbol')
    keep = {'country': 'country', 'industry': 'industry', 'sector': 'sector', 'isin': 'isin', 'cik': 'cik',
            'exchange': 'fmp_exchange', 'isActivelyTrading': 'is_actively_trading', 'isAdr': 'is_adr',
            'ipoDate': 'ipo_date', 'fullTimeEmployees': 'fmp_employees'}
    p = p[['symbol'] + [c for c in keep if c in p.columns]].rename(columns=keep)
    for c in p.columns:
        if c != 'symbol':
            p[c] = p[c].replace('', np.nan)
    m = df[['symbol']].merge(p, on='symbol', how='left', suffixes=('', '_fmp'))
    filled = {}
    for c in ('country', 'industry', 'sector'):
        if c in df.columns and c in m.columns:
            before = df[c].isna().sum()
            df[c] = df[c].fillna(m[c].values)
            filled[c] = int(before - df[c].isna().sum())
        elif c in m.columns:
            df[c] = m[c].values
    for c in ('isin', 'cik', 'fmp_exchange', 'is_actively_trading', 'is_adr', 'ipo_date', 'fmp_employees'):
        if c in m.columns:
            df[c] = m[c].values if c not in df.columns else df[c].fillna(m[c].values)
    print(f'  fmp profile fills: {filled}', file=sys.stderr)
    return df


def fix_asymmetry_global(in_path: str = 'asymmetry_global.csv',
                          out_path: str = 'asymmetry_global.csv'):
    print(f'\n=== Fixing {in_path} ===', file=sys.stderr)
    fx = load_fx()
    df = pd.read_csv(in_path)
    print(f'  loaded: {len(df)} rows', file=sys.stderr)

    # Need currency from a yartseva file - look it up
    import glob
    # Collect ALL candidate currencies per symbol. 620 symbols carry
    # CONFLICTING labels across the country files (mostly GBp vs GBP, ZAc
    # vs ZAR) — the old first-alphabetical-file-wins rule picked pence for
    # names whose master fundamentals are stored in the MAJOR unit,
    # 100x-crushing their USD caps (HMSO.L: $23.7M instead of ~$2.2B).
    # On a pence-vs-major conflict prefer the MAJOR unit — the pence-mint
    # methodology check catches the opposite error loudly, while a wrong
    # /100 destroys the name silently.
    _PENCE = {'GBp', 'GBX', 'ZAc', 'ZAC', 'ILA', 'ILa', 'KWf'}
    _cands: dict = {}
    for f in sorted({p for g in ['*_yartseva.csv'] for p in glob.glob(g)}):
        try:
            d = pd.read_csv(f, usecols=['symbol', 'currency'])
            for sym, ccy in zip(d['symbol'], d['currency']):
                if isinstance(sym, str) and isinstance(ccy, str):
                    _cands.setdefault(sym, set()).add(ccy)
        except Exception:
            continue
    ccy_map = {}
    for sym, cands in _cands.items():
        if len(cands) == 1:
            ccy_map[sym] = next(iter(cands))
        else:
            major = [c for c in cands if c not in _PENCE]
            ccy_map[sym] = (sorted(major)[0] if major
                            else sorted(cands)[0])
    df['currency'] = df['symbol'].map(ccy_map)

    df = fx_convert(df, fx)
    df = reject_data_anomalies(df)
    df = dedup_dual_listings(df)
    df = apply_fmp_profile(df)

    # Add an as_of stamp
    df['as_of'] = date.today().isoformat()

    from master_versions import versioned_replace
    df.to_csv(out_path + '.tmp', index=False)
    versioned_replace(out_path + '.tmp', out_path)   # atomic + pre-image snapshot
    print(f'  wrote {out_path}: {len(df)} rows', file=sys.stderr)
    return df


def fix_verdicts(path: str = 'qualitative_extended_verdicts.csv'):
    """Resolve the 3 known verdict conflicts.

    HBR.L: had YELLOW + RED. Diligence said 23 pct CAGR was entirely
           Wintershall M&A with BASF/Potomac dumping. RED is correct.
    TUSK:  had GREEN + YELLOW. Auditor change Deloitte->Carr Riggs is a
           legitimate caution. YELLOW is correct.
    TYGO:  had GREEN + YELLOW. Going-concern flag + FEOC/OBBB Act risk.
           YELLOW is correct.
    """
    print(f'\n=== Resolving verdict conflicts in {path} ===', file=sys.stderr)
    df = pd.read_csv(path)
    before = len(df)
    # Conflict resolution policy: drop earlier entries for these symbols
    # so the most-recent (downgrade) verdict is the only row.
    DOWNGRADES = {
        'HBR.L': 'RED',
        'TUSK': 'YELLOW',
        'TYGO': 'YELLOW',
    }
    keep_rows = []
    for sym, grp in df.groupby('symbol'):
        if sym in DOWNGRADES:
            # Keep only the row with the downgrade verdict
            chosen = grp[grp['verdict'] == DOWNGRADES[sym]]
            if len(chosen):
                keep_rows.append(chosen.iloc[-1:])
            else:
                keep_rows.append(grp.iloc[-1:])
        else:
            keep_rows.append(grp.iloc[-1:])  # keep last per symbol
    out = pd.concat(keep_rows, ignore_index=True)
    print(f'  collapsed {before} -> {len(out)} rows; resolved {len(DOWNGRADES)} conflicts', file=sys.stderr)
    out.to_csv(path, index=False)
    return out


if __name__ == '__main__':
    fix_asymmetry_global()
    fix_verdicts()
