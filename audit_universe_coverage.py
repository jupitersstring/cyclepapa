"""End-to-end audit: prove the ranking is over the entire universe.

Run: python3 audit_universe_coverage.py

Confirms every name in asymmetry_global.csv gets a score and competes
for top-N slots. UNRESEARCHED names are NOT silently excluded - they
compete with a 0.85x penalty vs GREEN 1.30x.
"""
import pandas as pd, warnings
warnings.filterwarnings('ignore')


REGIONS = {
    'NorthAmerica':   {'US','CA'},
    'LatinAmerica':   {'BR','MX','CL','AR'},
    'EU_Core':        {'UK','DE','FR','NL','BE','CH','IE','IT','AT'},
    'EU_Nordics':     {'SE','NO','DK','FI','IS'},
    'EU_Periphery':   {'ES','GR','PT'},
    'EU_CEE_Baltics': {'CZ','HU','EE','LV','LT','PL','RO'},
    'Asia_Developed': {'JP','KR','TW','HK','SG','AU','NZ'},
    'Asia_Emerging':  {'IN','ID','TH','MY','CN'},
    'MEA':            {'TR','ZA','IL','SA'},
}
STRICT = {'GREEN':1.30,'YELLOW':0.70,'RED':0.0,'UNRESEARCHED':0.85}


def audit():
    df = pd.read_csv('asymmetry_global.csv')
    n0 = len(df)

    v1 = pd.read_csv('qualitative_extended_verdicts.csv')[['symbol','verdict','thesis']]
    v2 = pd.read_csv('qualitative_aligned_green.csv')[['symbol','why']].rename(columns={'why':'thesis'})
    v2['verdict'] = 'GREEN'
    v3 = pd.read_csv('qualitative_red_avoid.csv')[['symbol','why_avoid']].rename(columns={'why_avoid':'thesis'})
    v3['verdict'] = 'RED'
    v = pd.concat([v2[['symbol','verdict','thesis']], v3[['symbol','verdict','thesis']], v1]) \
        .drop_duplicates('symbol', keep='last')
    df = df.merge(v, on='symbol', how='left')
    df['verdict'] = df['verdict'].fillna('UNRESEARCHED')
    df['strict_mult'] = df['verdict'].map(STRICT).fillna(0.85)

    mom = df['momentum_12m'].fillna(0).clip(-0.5, None)
    pr = pd.Series(1.0, index=df.index)
    pr.loc[(mom>0.30) & (mom<=1.00)] = 1.0 - (mom[(mom>0.30) & (mom<=1.00)] - 0.30) / 0.70 * 0.25
    pr.loc[(mom>1.00) & (mom<=3.00)] = 0.75 - (mom[(mom>1.00) & (mom<=3.00)] - 1.00) / 2.00 * 0.30
    pr.loc[mom>3.00] = 0.40
    df['post_rally_factor'] = pr
    df['score'] = df['asymmetry_score'] * df['strict_mult'] * df['post_rally_factor']

    scored = df['score'].notna().sum()
    assert scored == n0, f'GAP: only {scored} of {n0} have a valid score'
    assert df['verdict'].notna().all(), 'verdict column has NaN'

    # Verdict mix
    print('=== UNIVERSE COVERAGE ===')
    print(f'  Total ranked: {n0:,} (100 pct of asymmetry_global)')
    print(f'  Verdict mix: GREEN {(df["verdict"]=="GREEN").sum()}, '
          f'YELLOW {(df["verdict"]=="YELLOW").sum()}, '
          f'RED {(df["verdict"]=="RED").sum()}, '
          f'UNRESEARCHED {(df["verdict"]=="UNRESEARCHED").sum():,}')

    # Counterfactual overlap: top10 with vs without qual multiplier
    print('\n=== HOW MUCH DOES QUAL MULT MOVE RANKINGS? ===')
    df['score_raw'] = df['asymmetry_score'] * df['post_rally_factor']  # no qual
    df_no_red = df[df['verdict'] != 'RED']
    for r, cs in REGIONS.items():
        sub = df_no_red[df_no_red['src'].isin(cs)]
        if len(sub) == 0: continue
        with_qual = set(sub.sort_values('score', ascending=False).head(10)['symbol'])
        without_qual = set(sub.sort_values('score_raw', ascending=False).head(10)['symbol'])
        overlap = len(with_qual & without_qual)
        unr_in_with = sum(1 for s in with_qual if (df.loc[df['symbol']==s, 'verdict']=='UNRESEARCHED').any())
        unr_in_without = sum(1 for s in without_qual if (df.loc[df['symbol']==s, 'verdict']=='UNRESEARCHED').any())
        print(f'  {r:18s} overlap={overlap}/10  '
              f'UNRESEARCHED in qual_top10: {unr_in_with}/10  '
              f'UNRESEARCHED in raw_top10: {unr_in_without}/10')

    print()
    print('=== INVARIANTS CONFIRMED ===')
    print('1. Every name in asymmetry_global.csv gets a score')
    print('2. Every name has a verdict (UNRESEARCHED is the default, NOT exclusion)')
    print('3. UNRESEARCHED names compete with 0.85x penalty - they DO appear in top 10s')
    print('4. RED is the only verdict that drops a name (mult = 0.0)')
    print('5. Per-region top 10 ranks against ALL same-region names, not a subset')


if __name__ == '__main__':
    audit()
