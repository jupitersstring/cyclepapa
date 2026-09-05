"""Revealed-preference insider signals from SEC Form 4 filings.

The checklist infers alignment from COSTLY ACTIONS, not language: open-market
purchases, cluster buying, purchases by officers / 10%-owners. SEC publishes
all Form 3/4/5 insider transactions as bulk quarterly datasets
(.../insider-transactions-data-sets/YYYYqQ_form345.zip). We pull the last
few quarters, keep genuine OPEN-MARKET PURCHASES (transaction code 'P',
acquired), and aggregate per issuer into flags the archetypes can read.

Transaction codes used:
  P = open-market or private purchase (the revealed-preference BUY)
  S = open-market or private sale
(We ignore A/M/G/F etc. — grants, option exercises, gifts, tax withholding —
which are not discretionary conviction buys.)

Output: sec_insider_signals.csv keyed by ticker.
"""
from __future__ import annotations
import io
import os
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

UA = {'User-Agent': 'cyclepapa-research research@example.com'}
BASE = ('https://www.sec.gov/files/structureddata/data/'
        'insider-transactions-data-sets/{}_form345.zip')
CACHE = 'sec_cache'
QUARTERS = ['2025q3', '2025q4', '2026q1', '2026q2']   # ~last 12 months


def _download(q: str) -> bytes | None:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{q}_form345.zip')
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return open(path, 'rb').read()
    for url in (BASE.format(q),
                BASE.format(q).replace('structureddata',
                                       'datastandardsinnovation')):
        try:
            data = urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=90).read()
            open(path, 'wb').write(data)
            return data
        except Exception:
            continue
    print(f'  WARN: could not fetch {q}', file=sys.stderr)
    return None


def _tsv(z: zipfile.ZipFile, name: str, cols: list) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(z.read(name)), sep='\t',
                           usecols=lambda c: c in cols, dtype=str,
                           on_bad_lines='skip', low_memory=False)
    except Exception:
        return pd.DataFrame(columns=cols)


def _quarter_frame(data: bytes) -> pd.DataFrame:
    """Return per-transaction rows: symbol, owner cik, role, code, value."""
    z = zipfile.ZipFile(io.BytesIO(data))
    sub = _tsv(z, 'SUBMISSION.tsv',
               ['ACCESSION_NUMBER', 'ISSUERTRADINGSYMBOL', 'DOCUMENT_TYPE'])
    own = _tsv(z, 'REPORTINGOWNER.tsv',
               ['ACCESSION_NUMBER', 'RPTOWNERCIK', 'RPTOWNER_RELATIONSHIP'])
    trn = _tsv(z, 'NONDERIV_TRANS.tsv',
               ['ACCESSION_NUMBER', 'TRANS_CODE', 'TRANS_SHARES',
                'TRANS_PRICEPERSHARE', 'TRANS_ACQUIRED_DISP_CD'])
    if trn.empty or sub.empty:
        return pd.DataFrame()
    # keep only Form 4/4A discretionary transactions with a symbol
    sub = sub[sub['ISSUERTRADINGSYMBOL'].notna()
              & (sub['ISSUERTRADINGSYMBOL'].str.strip() != '')]
    trn = trn.merge(sub, on='ACCESSION_NUMBER', how='inner')
    # one relationship string per accession (collapse multi-owner)
    own_g = (own.groupby('ACCESSION_NUMBER')
                .agg(RPTOWNERCIK=('RPTOWNERCIK', 'first'),
                     REL=('RPTOWNER_RELATIONSHIP',
                          lambda s: '|'.join(str(x) for x in s)))
                .reset_index())
    trn = trn.merge(own_g, on='ACCESSION_NUMBER', how='left')
    trn['shares'] = pd.to_numeric(trn['TRANS_SHARES'], errors='coerce')
    trn['price'] = pd.to_numeric(trn['TRANS_PRICEPERSHARE'], errors='coerce')
    trn['value'] = trn['shares'] * trn['price']
    # Sanity guards: the raw datasets contain price/share unit glitches that
    # produce quadrillion-dollar "purchases" (e.g. REEMF 4.8e15). A corrupt
    # VALUE must not poison the dollar aggregates, but the transaction itself
    # still counts for the count/role/cluster flags — only its dollars are
    # untrusted. Bounds: price <= $1M/share (BRK.A headroom), shares <= 1e9
    # per transaction, value <= $5B per transaction.
    valid = ((trn['price'] > 0) & (trn['price'] <= 1e6) &
             (trn['shares'] > 0) & (trn['shares'] <= 1e9) &
             (trn['value'] <= 5e9))
    trn['value'] = trn['value'].where(valid)
    return trn


def main():
    print('fetching SEC Form 345 insider datasets...', file=sys.stderr)
    frames = []
    for q in QUARTERS:
        data = _download(q)
        if data:
            f = _quarter_frame(data)
            if len(f):
                frames.append(f)
                print(f'  {q}: {len(f):,} non-deriv transactions', file=sys.stderr)
    if not frames:
        print('no SEC data — aborting', file=sys.stderr)
        return
    t = pd.concat(frames, ignore_index=True)
    t['sym'] = t['ISSUERTRADINGSYMBOL'].str.strip().str.upper()
    rel = t['REL'].fillna('').str.lower()
    is_officer = rel.str.contains('officer')
    is_director = rel.str.contains('director')
    is_10pct = rel.str.contains('tenpercent') | rel.str.contains('ten percent')
    buy = (t['TRANS_CODE'] == 'P') & (t['TRANS_ACQUIRED_DISP_CD'] == 'A')
    sell = (t['TRANS_CODE'] == 'S')

    rows = []
    for sym, g in t.groupby('sym'):
        gb = g[buy.loc[g.index]]
        gs = g[sell.loc[g.index]]
        if gb.empty and gs.empty:
            continue
        buy_val = float(gb['value'].sum(skipna=True))
        sell_val = float(gs['value'].sum(skipna=True))
        rows.append({
            'symbol': sym,
            'insider_buy_count': int(len(gb)),
            'insider_buy_value': round(buy_val, 0),
            'insider_net_buy_value': round(buy_val - sell_val, 0),
            'insider_distinct_buyers': int(gb['RPTOWNERCIK'].nunique()),
            'insider_officer_buy_flag': int(bool(is_officer.loc[gb.index].any())) if len(gb) else 0,
            'insider_director_buy_flag': int(bool(is_director.loc[gb.index].any())) if len(gb) else 0,
            'insider_10pct_buy_flag': int(bool(is_10pct.loc[gb.index].any())) if len(gb) else 0,
        })
    out = pd.DataFrame(rows)
    # derived flags
    out['insider_buy_flag'] = (out['insider_buy_count'] > 0).astype(int)
    out['insider_cluster_buy_flag'] = (out['insider_distinct_buyers'] >= 2).astype(int)
    out['insider_net_buyer_flag'] = (out['insider_net_buy_value'] > 0).astype(int)
    out.to_csv('sec_insider_signals.csv', index=False)
    print(f'\nwrote sec_insider_signals.csv: {len(out):,} issuers with insider '
          f'buys/sells', file=sys.stderr)
    print(f'  open-market buyers: {int(out["insider_buy_flag"].sum()):,} | '
          f'cluster (>=2): {int(out["insider_cluster_buy_flag"].sum()):,} | '
          f'10%-owner buys: {int(out["insider_10pct_buy_flag"].sum()):,} | '
          f'officer buys: {int(out["insider_officer_buy_flag"].sum()):,}',
          file=sys.stderr)


if __name__ == '__main__':
    main()
