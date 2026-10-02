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
            'ipoDate': 'ipo_date', 'fullTimeEmployees': 'fmp_employees',
            'marketCap': 'fmp_market_cap', 'currency': 'fmp_currency',
            'isEtf': 'is_etf', 'isFund': 'is_fund', 'companyName': 'fmp_company_name'}
    p = p[['symbol'] + [c for c in keep if c in p.columns]].rename(columns=keep)
    # the bulk parquet comes back Arrow-backed (large_string); fillna rejects
    # those arrays, so work in plain object dtype
    p = p.astype(object)
    for c in p.columns:
        if c != 'symbol':
            p[c] = p[c].replace('', np.nan)
    # the bulk parquet stores every field as text
    if 'fmp_market_cap' in p.columns:
        p['fmp_market_cap'] = pd.to_numeric(p['fmp_market_cap'], errors='coerce')
    # the profile's country is ISO-2; the master's is the full name (Yahoo /
    # pew). Fill in the master's own vocabulary so one column keeps one coding;
    # the ISO code is kept beside it as domicile_iso2 for every name.
    if 'country' in p.columns:
        p['domicile_iso2'] = p['country'].astype(str).str.upper().where(p['country'].notna())
        p['country'] = p['domicile_iso2'].map(_ISO2_NAME).fillna(p['country'])
    m = df[['symbol']].merge(p, on='symbol', how='left', suffixes=('', '_fmp'))
    m.index = df.index
    filled = {}
    for c in ('country', 'industry', 'sector'):
        if c in df.columns and c in m.columns:
            before = df[c].isna().sum()
            df[c] = df[c].fillna(m[c])
            filled[c] = int(before - df[c].isna().sum())
        elif c in m.columns:
            df[c] = m[c]
    for c in ('isin', 'cik', 'fmp_exchange', 'is_actively_trading', 'is_adr', 'ipo_date', 'fmp_employees',
              'domicile_iso2', 'is_etf', 'is_fund', 'fmp_company_name', 'fmp_currency'):
        if c in m.columns:
            df[c] = m[c] if c not in df.columns else df[c].fillna(m[c])
    # MARKET CAP: the profile's marketCap is in the LISTING currency (audit
    # 2026-10: median ratio to the master's local market cap 0.95-1.01 in every
    # currency incl. pence-quoted London). Fill a NaN local market cap only
    # where the two currencies agree (parent unit), convert with the row's
    # own fx_to_usd, and tag the provenance. A name with no price on our side
    # otherwise carries NaN mcap -> every mcap-denominated leg reads 0.
    if 'fmp_market_cap' in m.columns and 'market_cap' in df.columns:
        _sub = {'GBp': 'GBP', 'GBX': 'GBP', 'ZAc': 'ZAR', 'ZAC': 'ZAR', 'ILA': 'ILS', 'ILa': 'ILS', 'KWf': 'KWD'}
        _own = df['currency'].astype(str).map(lambda c: _sub.get(c, c)) if 'currency' in df.columns \
            else pd.Series(np.nan, index=df.index)
        _prof = m['fmp_currency'].astype(str).map(lambda c: _sub.get(c, c)) if 'fmp_currency' in m.columns \
            else pd.Series(np.nan, index=df.index)
        _mc = pd.to_numeric(df['market_cap'], errors='coerce')
        _fill = _mc.isna() & (m['fmp_market_cap'].values > 0) & (_own.values == _prof.values)
        if 'market_cap_src' not in df.columns:
            df['market_cap_src'] = pd.Series(np.where(_mc.notna(), 'pipeline', None), index=df.index, dtype=object)
        df.loc[_fill, 'market_cap'] = m.loc[_fill, 'fmp_market_cap'].values
        df.loc[_fill, 'market_cap_src'] = 'fmp_profile'
        if 'fx_to_usd' in df.columns and 'market_cap_usd' in df.columns:
            df.loc[_fill, 'market_cap_usd'] = (m.loc[_fill, 'fmp_market_cap'].values
                                               * pd.to_numeric(df.loc[_fill, 'fx_to_usd'], errors='coerce').fillna(1.0).values)
        filled['market_cap'] = int(_fill.sum())
    print(f'  fmp profile fills: {filled}', file=sys.stderr)
    return df


# ISO-2 -> the master's own country naming (Yahoo / pew vocabulary).
_ISO2_NAME = {
    'US': 'United States', 'CN': 'China', 'IN': 'India', 'JP': 'Japan', 'KR': 'South Korea',
    'TW': 'Taiwan', 'HK': 'Hong Kong', 'TH': 'Thailand', 'GB': 'United Kingdom', 'UK': 'United Kingdom',
    'AU': 'Australia', 'CA': 'Canada', 'ID': 'Indonesia', 'SE': 'Sweden', 'DE': 'Germany',
    'BR': 'Brazil', 'SG': 'Singapore', 'FR': 'France', 'TR': 'Turkey', 'IT': 'Italy',
    'CH': 'Switzerland', 'NO': 'Norway', 'SA': 'Saudi Arabia', 'FI': 'Finland', 'CL': 'Chile',
    'DK': 'Denmark', 'ES': 'Spain', 'IL': 'Israel', 'MX': 'Mexico', 'GR': 'Greece', 'BE': 'Belgium',
    'NZ': 'New Zealand', 'NL': 'Netherlands', 'AR': 'Argentina', 'IE': 'Ireland', 'MY': 'Malaysia',
    'ZA': 'South Africa', 'AT': 'Austria', 'BM': 'Bermuda', 'PT': 'Portugal', 'PL': 'Poland',
    'LT': 'Lithuania', 'EE': 'Estonia', 'HU': 'Hungary', 'KY': 'Cayman Islands', 'IS': 'Iceland',
    'CZ': 'Czech Republic', 'MC': 'Monaco', 'LU': 'Luxembourg', 'LV': 'Latvia', 'MO': 'Macau',
    'CY': 'Cyprus', 'AE': 'United Arab Emirates', 'GI': 'Gibraltar', 'CO': 'Colombia', 'UY': 'Uruguay',
    'AI': 'Anguilla', 'JO': 'Jordan', 'PH': 'Philippines', 'VI': 'U.S. Virgin Islands', 'RU': 'Russia',
    'VN': 'Vietnam', 'PE': 'Peru', 'RO': 'Romania', 'MT': 'Malta', 'KW': 'Kuwait', 'QA': 'Qatar',
    'EG': 'Egypt', 'NG': 'Nigeria', 'KE': 'Kenya', 'PK': 'Pakistan', 'BD': 'Bangladesh', 'LK': 'Sri Lanka',
    'VG': 'British Virgin Islands', 'JE': 'Jersey', 'GG': 'Guernsey', 'IM': 'Isle of Man', 'PR': 'Puerto Rico',
}
# the master's venue codes that differ from ISO-2
_SRC_TO_ISO2 = {'UK': 'GB'}


def add_company_map(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical company map: one key per COMPANY across its listings (ADR,
    OTC line, dual listing, NVDR wrapper), so a book can tell a second line of
    the same business from a second business. Key = ISIN where the profile
    has one, else the SEC CIK, else the normalised name + domicile. The
    PRIMARY listing is the home-market line (venue == domicile), then the
    most traded (pew dollar volume), then the largest USD cap; every other
    line is marked is_secondary_listing=1 with primary_listing naming the
    canonical symbol. Informational: nothing here drops rows — is_price_ghost
    (archetype_tags) keeps handling the corrupt-price duplicates."""
    sym = df['symbol'].astype(str)
    isin = df['isin'].astype(str).str.strip().str.upper() if 'isin' in df.columns else pd.Series('', index=df.index)
    isin_ok = isin.str.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]').fillna(False)
    cik = pd.to_numeric(df['cik'], errors='coerce') if 'cik' in df.columns else pd.Series(np.nan, index=df.index)
    cik = cik.where(np.isfinite(cik))
    cik_str = cik.fillna(0).round().astype('int64').astype(str)
    nm = (df['name'].fillna('').astype(str).str.lower()
          .str.replace(r'[^a-z0-9 ]', '', regex=True)
          .str.replace(r'\b(corp|corporation|inc|incorporated|company|co|ltd|limited|plc|holdings?|group|'
                       r'sa|ag|nv|se|the|adr|sponsored|ordinary|shares?|class [a-z]|cl [a-z]|tbk|pt|bhd|'
                       r'berhad|public|kk|kabushiki kaisha|spa|srl|asa|ab|oyj|as|a s)\b', '', regex=True)
          .str.replace(r'\s+', ' ', regex=True).str.strip()) if 'name' in df.columns else pd.Series('', index=df.index)
    dom = df['domicile_iso2'].astype(str).str.upper() if 'domicile_iso2' in df.columns else pd.Series('', index=df.index)
    dom = dom.where(dom.ne('NAN') & dom.ne('NONE'), '')
    key = pd.Series(np.where(isin_ok, 'isin:' + isin,
                    np.where(cik.fillna(0) > 0, 'cik:' + cik_str,
                    np.where(nm != '', 'nm:' + nm + ':' + dom, 'sym:' + sym))), index=df.index)
    key = key.astype(object).where(key.notna() & (key.astype(str) != 'nan'), 'sym:' + sym)
    df['company_key'] = key
    df['n_listings'] = key.map(key.value_counts()).fillna(1).astype(int)
    venue = df['src'].astype(str).str.upper().map(lambda s: _SRC_TO_ISO2.get(s, s)) if 'src' in df.columns \
        else pd.Series('', index=df.index)
    home = (venue == dom) & (dom != '')
    dv = pd.to_numeric(df.get('pew_avg_dollar_volume'), errors='coerce') if 'pew_avg_dollar_volume' in df.columns \
        else pd.Series(np.nan, index=df.index)
    mc = pd.to_numeric(df.get('market_cap_usd'), errors='coerce') if 'market_cap_usd' in df.columns \
        else pd.Series(np.nan, index=df.index)
    adr = df['is_adr'].astype(str).str.lower().eq('true') if 'is_adr' in df.columns else pd.Series(False, index=df.index)
    order = pd.DataFrame({'k': key, 'home': home.astype(int), 'adr': (~adr).astype(int),
                          'dv': dv.fillna(-1), 'mc': mc.fillna(-1), 'sym': sym, 'i': np.arange(len(df))})
    order = order.sort_values(['k', 'home', 'adr', 'dv', 'mc', 'sym'],
                              ascending=[True, False, False, False, False, True])
    primary = order.drop_duplicates('k').set_index('k')['sym']
    df['primary_listing'] = key.map(primary).values
    df['is_secondary_listing'] = ((df['n_listings'] > 1) & (df['primary_listing'] != sym)).astype(int)
    print(f"  company map: {df['company_key'].nunique():,} companies for {len(df):,} lines; "
          f"{int(df['is_secondary_listing'].sum()):,} secondary listings "
          f"(isin-keyed {int(isin_ok.sum()):,}, cik-keyed {int((~isin_ok & (cik.fillna(0) > 0)).sum()):,})",
          file=sys.stderr)
    return df


def add_freshness_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Freshness of what the row is built on. fundamentals_age_days = days from
    the balance-sheet date (the latest statement the ratios rest on) to
    today; stale_fundamentals = older than 15 months (455 days: a company
    that has not filed in five quarters — the ranker's own --max-bs-age-days
    is 540); fundamentals_undated where no statement date reached the master.
    price_age_days = the live tape's last-bar age (lynch panel) else the
    Yahoo chart fill's fetch age; stale_price = older than 30 days or the
    tape flagged stale. Flags only — nothing is dropped here."""
    today = pd.Timestamp(date.today())
    if 'balance_sheet_date' in df.columns:
        bsd = pd.to_datetime(df['balance_sheet_date'], errors='coerce')
        age = (today - bsd).dt.days
        df['fundamentals_age_days'] = age
        df['stale_fundamentals'] = (age > 455).fillna(False).astype(int)
        df['fundamentals_undated'] = age.isna().astype(int)
    page = pd.Series(np.nan, index=df.index)
    stale_tape = pd.Series(0, index=df.index)
    if os.path.exists('lynch_reward_signals.csv'):
        try:
            _lm = pd.read_csv('lynch_reward_signals.csv',
                              usecols=['symbol', 'stale_tape', 'last_bar_age_days']).drop_duplicates('symbol')
            _lm = df[['symbol']].merge(_lm, on='symbol', how='left')
            page = pd.to_numeric(_lm['last_bar_age_days'], errors='coerce').values
            page = pd.Series(page, index=df.index)
            stale_tape = pd.Series(pd.to_numeric(_lm['stale_tape'], errors='coerce').fillna(0).values, index=df.index)
        except Exception as e:
            print(f'  freshness: lynch tape unavailable ({e})', file=sys.stderr)
    if os.path.exists('yahoo_chart_fill.csv'):
        try:
            _y = pd.read_csv('yahoo_chart_fill.csv', usecols=['symbol', 'fetched_at']).drop_duplicates('symbol')
            _y = df[['symbol']].merge(_y, on='symbol', how='left')
            _fa = pd.to_numeric(_y['fetched_at'], errors='coerce')
            _yage = (today.timestamp() - _fa) / 86400.0
            page = page.fillna(pd.Series(_yage.values, index=df.index))
        except Exception as e:
            print(f'  freshness: yahoo fill unavailable ({e})', file=sys.stderr)
    df['price_age_days'] = page.round(1)
    df['stale_price'] = ((page > 30) | (stale_tape == 1)).fillna(False).astype(int)
    print(f"  freshness: fundamentals stale {int(df.get('stale_fundamentals', pd.Series(0)).sum()):,} / "
          f"undated {int(df.get('fundamentals_undated', pd.Series(0)).sum()):,}; "
          f"price age known {int(page.notna().sum()):,}, stale {int(df['stale_price'].sum()):,}",
          file=sys.stderr)
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
    df = add_company_map(df)
    df = add_freshness_flags(df)

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
