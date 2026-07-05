"""Widen the universe with FinanceDatabase names we don't cover yet.

FDB has ~151k equities vs our 25.6k universe. The raw "not in universe"
set (126k) is mostly noise though:

  - Cross-listings of companies we ALREADY have (a US company's Vienna
    /Frankfurt/OTC line shows up as a "new" symbol). Deduped by
    normalised company name against the existing universe.
  - Multiple new listings of the SAME new company (e.g. a Japanese name
    with .T + .F + OTC lines). Deduped by normalised name within the
    expansion set, preferring the primary listing (suffix matching the
    company's home country).
  - ~82k rows with no market-cap bucket — overwhelmingly dead/illiquid
    tickers. Excluded from the first wave.

Output:
  - fdb_expansion_universe.csv  (curated identity rows)
  - appends identity rows to asymmetry_global.csv (src = ISO2) so the
    existing enrichment stack (ticker_yf, yahoo_chart_fill, derive,
    enrich, archetypes) picks them up automatically — both enrichers
    read their symbol list from the master.
"""
from __future__ import annotations
import argparse
import re
import sys

import pandas as pd


# FDB country name -> ISO2 src code used in the master
COUNTRY_TO_ISO2 = {
    'United States': 'US', 'Canada': 'CA', 'United Kingdom': 'UK',
    'Germany': 'DE', 'France': 'FR', 'Netherlands': 'NL', 'Belgium': 'BE',
    'Switzerland': 'CH', 'Ireland': 'IE', 'Austria': 'AT', 'Italy': 'IT',
    'Spain': 'ES', 'Portugal': 'PT', 'Greece': 'GR',
    'Sweden': 'SE', 'Norway': 'NO', 'Denmark': 'DK', 'Finland': 'FI',
    'Iceland': 'IS', 'Poland': 'PL', 'Czech Republic': 'CZ', 'Czechia': 'CZ',
    'Hungary': 'HU', 'Estonia': 'EE', 'Latvia': 'LV', 'Lithuania': 'LT',
    'Romania': 'RO', 'Turkey': 'TR',
    'Japan': 'JP', 'South Korea': 'KR', 'Taiwan': 'TW', 'Hong Kong': 'HK',
    'Singapore': 'SG', 'Australia': 'AU', 'New Zealand': 'NZ',
    'China': 'CN', 'India': 'IN', 'Indonesia': 'ID', 'Thailand': 'TH',
    'Malaysia': 'MY', 'Philippines': 'PH', 'Vietnam': 'VN',
    'Brazil': 'BR', 'Mexico': 'MX', 'Chile': 'CL', 'Argentina': 'AR',
    'Colombia': 'CO', 'Peru': 'PE',
    'South Africa': 'ZA', 'Israel': 'IL', 'Saudi Arabia': 'SA',
    'United Arab Emirates': 'AE', 'Qatar': 'QA', 'Kuwait': 'KW',
    'Egypt': 'EG', 'Nigeria': 'NG', 'Kenya': 'KE',
}

# Yahoo suffix -> home market. Used to prefer the primary listing when a
# new company appears under several exchange lines.
SUFFIX_HOME = {
    '.T': 'JP', '.KS': 'KR', '.KQ': 'KR', '.TW': 'TW', '.TWO': 'TW',
    '.HK': 'HK', '.SI': 'SG', '.AX': 'AU', '.NZ': 'NZ',
    '.SS': 'CN', '.SZ': 'CN', '.NS': 'IN', '.BO': 'IN', '.JK': 'ID',
    '.BK': 'TH', '.KL': 'MY', '.PS': 'PH', '.VN': 'VN',
    '.L': 'UK', '.IL': 'UK', '.DE': 'DE', '.F': 'DE', '.SG': 'DE',
    '.MU': 'DE', '.DU': 'DE', '.HM': 'DE', '.BE': 'DE', '.HA': 'DE',
    '.PA': 'FR', '.AS': 'NL', '.BR': 'BE', '.SW': 'CH', '.IR': 'IE',
    '.VI': 'AT', '.MI': 'IT', '.MC': 'ES', '.LS': 'PT', '.AT': 'GR',
    '.ST': 'SE', '.OL': 'NO', '.CO': 'DK', '.HE': 'FI', '.IC': 'IS',
    '.WA': 'PL', '.PR': 'CZ', '.BD': 'HU', '.TL': 'EE', '.RG': 'LV',
    '.VS': 'LT', '.RO': 'RO', '.IS': 'TR',
    '.SA': 'BR', '.MX': 'MX', '.SN': 'CL', '.BA': 'AR', '.CN': 'CA',
    '.TO': 'CA', '.V': 'CA', '.JO': 'ZA', '.TA': 'IL', '.SR': 'SA',
    '.AD': 'AE', '.DU': 'AE', '.QA': 'QA', '.KW': 'KW', '.CA': 'EG',
}

_NAME_STOP = re.compile(
    r"\b(inc|incorporated|corp|corporation|ltd|limited|plc|sa|ag|nv|se|"
    r"ab|as|asa|oyj|spa|co|company|holdings?|group|the|and|&)\b|[^a-z0-9 ]")


def norm_name(n) -> str:
    if not isinstance(n, str):
        return ""
    n = n.lower()
    n = _NAME_STOP.sub(" ", n)
    return " ".join(n.split())


def suffix_of(sym: str) -> str:
    if '.' in sym:
        return '.' + sym.rsplit('.', 1)[1]
    return ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--master', default='asymmetry_global.csv')
    ap.add_argument('--out', default='fdb_expansion_universe.csv')
    ap.add_argument('--append-to-master', action='store_true',
                    help='append curated identity rows to the master CSV')
    ap.add_argument('--include-nan-mcap', action='store_true',
                    help='also include names FDB has no cap bucket for '
                         '(mostly dead tickers; excluded by default)')
    args = ap.parse_args()

    import financedatabase as fd
    print('loading FDB equities...', file=sys.stderr)
    eq = fd.Equities().select().reset_index().rename(columns={'index': 'symbol'})
    eq = eq[eq['symbol'].notna() & eq['name'].notna()]
    print(f'  {len(eq):,} rows with symbol+name', file=sys.stderr)

    master = pd.read_csv(args.master)
    uni_syms = set(master['symbol'].dropna())
    uni_names = {norm_name(n) for n in master['name'].dropna()}
    uni_names.discard("")

    new = eq[~eq['symbol'].isin(uni_syms)].copy()
    print(f'  {len(new):,} symbols not in universe', file=sys.stderr)

    # Drop cross-listings of companies we already cover (by name)
    new['_nname'] = new['name'].map(norm_name)
    new = new[new['_nname'] != ""]
    before = len(new)
    new = new[~new['_nname'].isin(uni_names)]
    print(f'  dropped {before - len(new):,} cross-listings of covered names '
          f'-> {len(new):,}', file=sys.stderr)

    # Cap-bucket filter (first wave: only names FDB sizes)
    if not args.include_nan_mcap:
        before = len(new)
        new = new[new['market_cap'].notna()]
        print(f'  dropped {before - len(new):,} no-cap-bucket rows '
              f'-> {len(new):,}', file=sys.stderr)

    # Within-expansion dedup: one listing per company, prefer the line
    # whose suffix matches the company's home market.
    new['_src'] = new['country'].map(COUNTRY_TO_ISO2)
    new['_sfx_home'] = new['symbol'].map(lambda s: SUFFIX_HOME.get(suffix_of(s)))
    new['_primary'] = (new['_sfx_home'] == new['_src']).astype(int)
    # US names: no suffix is the primary line
    us_no_sfx = (new['_src'] == 'US') & (~new['symbol'].str.contains(r'\.'))
    new.loc[us_no_sfx, '_primary'] = 1
    before = len(new)
    new = (new.sort_values(['_nname', '_primary'], ascending=[True, False])
              .drop_duplicates('_nname', keep='first'))
    print(f'  deduped {before - len(new):,} secondary listings '
          f'-> {len(new):,} unique new companies', file=sys.stderr)

    # Drop rows we can't assign a src country to (uncoded markets)
    coded = new[new['_src'].notna()].copy()
    print(f'  {len(coded):,} in coded markets '
          f'({len(new) - len(coded):,} in uncoded markets dropped)',
          file=sys.stderr)

    out = pd.DataFrame({
        'symbol': coded['symbol'],
        'name': coded['name'],
        'src': coded['_src'],
        'sector': coded['sector'],
        'industry': coded['industry'],
        'market_cap_bucket': coded['market_cap'],
        'country_full': coded['country'],
        'exchange': coded.get('exchange'),
    })
    out.to_csv(args.out, index=False)
    print(f'\nwrote {args.out}: {len(out):,} expansion names', file=sys.stderr)
    print('\nby market:', file=sys.stderr)
    print(out['src'].value_counts().head(20).to_string(), file=sys.stderr)
    print('\nby cap bucket:', file=sys.stderr)
    print(out['market_cap_bucket'].value_counts().to_string(), file=sys.stderr)

    if args.append_to_master:
        add = out[['symbol', 'name', 'src', 'sector', 'industry',
                   'market_cap_bucket']].copy()
        add['verdict'] = 'UNRESEARCHED'
        # Align to master schema; everything else stays NaN until enriched
        for c in master.columns:
            if c not in add.columns:
                add[c] = pd.NA
        add = add[master.columns]
        combined = pd.concat([master, add], ignore_index=True)
        combined = combined.drop_duplicates('symbol', keep='first')
        combined.to_csv(args.master, index=False)
        print(f'\nappended to {args.master}: {len(master):,} -> {len(combined):,} rows',
              file=sys.stderr)


if __name__ == '__main__':
    main()
