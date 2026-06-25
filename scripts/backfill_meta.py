#!/usr/bin/env python3
"""Fill gaps in v2_universe_ranked_full_q.csv from all available metadata sources.

Sources:
  • data/universes/uni_*.csv  +  data/universes/expanded/uni_*_x.csv  (name, sector, industry, market_cap, exchange)
  • /tmp/sec_tickers.json (ticker → official SEC company title — covers US EDGAR-only)
  • data/research/segments_us.csv (segment specifics — fastest/slowest/largest names + values)
  • data/research/backlog_us.csv (backlog specifics — concept, dates, growth)

Also fixes the `roic_mean_4y_med` → `roic_mean` rename so downstream archetype scripts work.
"""
import os, sys, json, glob
import pandas as pd
import numpy as np

src = 'data/synthesis/v2_universe_ranked_full_q.csv'
if not os.path.exists(src):
    src = 'data/synthesis/v2_universe_ranked_full.csv'
df = pd.read_csv(src)
print(f"Loaded {len(df)} rows from {src}", file=sys.stderr)
print(f"  gaps before: name {df['name'].isna().sum()}  sector {df.get('sector', pd.Series(dtype=str)).isna().sum()}  mktCap {df.get('mktCap', pd.Series(dtype=float)).isna().sum()}", file=sys.stderr)

# ─── 1. Build master metadata dict from all universe files ───
meta_rows = []
for u in sorted(glob.glob('data/universes/uni_*.csv') + glob.glob('data/universes/expanded/uni_*_x.csv')):
    try:
        d = pd.read_csv(u, low_memory=False)
        d.columns = [c.lower() for c in d.columns]
        cols = {'ticker','name','sector','industry','market_cap','exchange','country'}
        d = d[[c for c in cols if c in d.columns]].copy()
        if 'ticker' not in d.columns: continue
        d['ticker'] = d['ticker'].astype(str).str.strip().str.upper()
        if 'market_cap' in d.columns:
            d['market_cap'] = pd.to_numeric(d['market_cap'], errors='coerce')
        meta_rows.append(d)
    except Exception as e:
        print(f"  skip {u}: {e}", file=sys.stderr)
meta = pd.concat(meta_rows, ignore_index=True) if meta_rows else pd.DataFrame()
# Per-ticker: prefer non-null + largest market_cap
if len(meta):
    meta = (meta.sort_values('market_cap', ascending=False, na_position='last')
                .drop_duplicates('ticker', keep='first'))
    print(f"  meta dict built: {len(meta)} unique tickers from universe files", file=sys.stderr)

# ─── 2. SEC ticker titles as a name fallback ───
sec_name = {}
if os.path.exists('/tmp/sec_tickers.json'):
    with open('/tmp/sec_tickers.json') as f:
        sec_raw = json.load(f)
    for v in sec_raw.values():
        t = str(v.get('ticker','')).upper().strip()
        ttl = str(v.get('title','')).strip()
        if t and ttl: sec_name[t] = ttl
    print(f"  SEC titles: {len(sec_name)}", file=sys.stderr)

# ─── 3. Backfill name / sector / industry / mktCap / exchange ───
df['ticker'] = df['ticker'].astype(str).str.strip().str.upper()

# Build the lookup dict from meta
meta_idx = meta.set_index('ticker') if len(meta) else pd.DataFrame()

def fill(row, col):
    if col in row and pd.notna(row[col]) and str(row[col]).strip() not in ('', 'nan', 'None'):
        return row[col]
    t = row['ticker']
    if len(meta_idx) and t in meta_idx.index and col in meta_idx.columns:
        v = meta_idx.loc[t, col]
        if pd.notna(v): return v
    return row.get(col, np.nan)

# Vectorized backfill (much faster than apply)
for col in ['name', 'sector', 'industry', 'exchange', 'country']:
    if col not in df.columns:
        df[col] = np.nan
    if col in meta_idx.columns:
        fill_map = meta_idx[col].dropna().to_dict()
        df[col] = df[col].where(df[col].notna() & (df[col].astype(str).str.strip().isin(['','nan','None']) == False),
                                df['ticker'].map(fill_map))

# Market cap fill (universe column is `market_cap`, ours is `mktCap`)
if 'mktCap' not in df.columns:
    df['mktCap'] = np.nan
if 'market_cap' in meta_idx.columns:
    cap_map = meta_idx['market_cap'].dropna().to_dict()
    df['mktCap'] = df['mktCap'].where(df['mktCap'].notna(), df['ticker'].map(cap_map))

# Final fallback for name: SEC EDGAR title
if sec_name:
    df['name'] = df['name'].where(df['name'].notna() & (df['name'].astype(str).str.strip() != ''),
                                  df['ticker'].map(sec_name))

# Re-derive mktCap_M
df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6

# ─── 4. Cap tier from filled mktCap (only where unknown) ───
def cap_tier(mc):
    if pd.isna(mc): return 'unknown'
    if mc >= 200e9:  return 'mega'
    if mc >= 10e9:   return 'large'
    if mc >= 2e9:    return 'mid'
    if mc >= 300e6:  return 'small'
    if mc > 0:       return 'micro'
    return 'unknown'
mask = df['cap_tier'].isin(['unknown', '', np.nan]) | df['cap_tier'].isna()
df.loc[mask, 'cap_tier'] = df.loc[mask, 'mktCap'].apply(cap_tier)

# ─── 5. Fix the roic_mean_4y_med → roic_mean rename ───
# Older archetype script references roic_mean_4y_med but compounders_ranked now exports roic_mean.
if 'roic_mean' in df.columns and 'roic_mean_4y_med' not in df.columns:
    df['roic_mean_4y_med'] = df['roic_mean']
if 'roic_min' in df.columns and 'roic_min_4y_med' not in df.columns:
    df['roic_min_4y_med'] = df['roic_min']
if 'roic_std' in df.columns and 'roic_std_4y_med' not in df.columns:
    df['roic_std_4y_med'] = df['roic_std']
# has_history = roic_years >= 3 (or roe_history for financials)
if 'has_history' not in df.columns:
    yrs = pd.to_numeric(df.get('roic_years', pd.Series(np.nan, index=df.index)), errors='coerce')
    roe_yrs = pd.to_numeric(df.get('roe_min_4y', pd.Series(np.nan, index=df.index)), errors='coerce').notna().astype(int) * 3
    df['has_history'] = ((yrs.fillna(0) >= 3) | (roe_yrs >= 3)).fillna(False).astype(bool)

# ─── 6. Merge segment specifics with full names ───
seg_path = 'data/research/segments_us.csv'
if os.path.exists(seg_path):
    s = pd.read_csv(seg_path)
    keep = ['ticker','has_segments','n_segments','largest_segment','largest_segment_pct',
            'seg_rev_growth_fastest','seg_fastest_name','seg_rev_growth_slowest',
            'seg_slowest_name','seg_growth_dispersion','seg_mix_shift_pp',
            'seg_mix_gainer','seg_inflection_flag','seg_margin_best',
            'seg_margin_best_name','seg_margin_worst','seg_high_margin_growing']
    s = s[[c for c in keep if c in s.columns]]
    s['ticker'] = s['ticker'].astype(str).str.upper().str.strip()
    # Drop existing segment cols from df before merge
    for c in [x for x in s.columns if x != 'ticker' and x in df.columns]:
        df = df.drop(columns=[c])
    df = df.merge(s, on='ticker', how='left')
    n_seg = int(df.get('has_segments', pd.Series(False, index=df.index)).fillna(False).sum())
    print(f"  merged segments: {len(s)} rows  ({n_seg} with segment data)", file=sys.stderr)

# ─── 7. Merge backlog specifics ───
bl_path = 'data/research/backlog_us.csv'
if os.path.exists(bl_path):
    b = pd.read_csv(bl_path)
    keep = ['ticker','backlog_concept_used','backlog_latest','backlog_latest_date',
            'backlog_qoq_pct','backlog_yoy_pct','backlog_growth_4q_mean',
            'backlog_growth_8q_mean','backlog_inflection_pp','backlog_inflection_flag',
            'backlog_to_rev_ratio','backlog_quarters_history']
    b = b[[c for c in keep if c in b.columns]]
    b['ticker'] = b['ticker'].astype(str).str.upper().str.strip()
    for c in [x for x in b.columns if x != 'ticker' and x in df.columns]:
        df = df.drop(columns=[c])
    df = df.merge(b, on='ticker', how='left')
    n_bl = int(df.get('backlog_latest', pd.Series(np.nan, index=df.index)).notna().sum())
    print(f"  merged backlog: {len(b)} rows  ({n_bl} with backlog data)", file=sys.stderr)

# ─── 8. Pull ALL useful fundamentals cols (master_synthesis only kept 8) ───
# data/fundamentals/fund_*.csv has 28 cols — we were only using 8 of them.
fund_frames = []
for fp in sorted(glob.glob('data/fundamentals/fund_*.csv')):
    try:
        fd = pd.read_csv(fp, low_memory=False)
        keep = ['ticker','pb','pe','fpe','ps','roe','roa','gm','opm','earn_g','ebitda','ev',
                'ev_ebitda','ev_ebit','fcf','fcf_yield','rev','rev_g','net_debt','nd_ebitda',
                'div_yield','insiders','beta','mktCap','price','currency']
        fd = fd[[c for c in keep if c in fd.columns]]
        if 'ticker' in fd.columns:
            fd['ticker'] = fd['ticker'].astype(str).str.upper().str.strip()
            fund_frames.append(fd)
    except Exception: pass
if fund_frames:
    fall = (pd.concat(fund_frames, ignore_index=True)
              .drop_duplicates('ticker', keep='first')
              .set_index('ticker'))
    # Add all columns that don't exist; for columns that DO exist, fill only nulls
    new_cols = ['fpe','ps','opm','ev_ebitda','net_debt','nd_ebitda','div_yield','insiders',
                'beta','currency','fcf']
    fill_cols = ['pb','pe','roe','roa','gm','earn_g','ebitda','ev','rev','fcf_yield','rev_g','mktCap','price']
    for col in new_cols:
        if col in fall.columns and col not in df.columns:
            df[col] = df['ticker'].map(fall[col].dropna().to_dict())
    for col in fill_cols:
        if col not in fall.columns: continue
        m = fall[col].dropna().to_dict()
        if col in df.columns:
            df[col] = df[col].where(df[col].notna(), df['ticker'].map(m))
        else:
            df[col] = df['ticker'].map(m)
    # Re-derive mktCap_M after mktCap fill
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6
    print(f"  pulled {len(fall):,} fundamentals rows; added/filled {len(new_cols)+len(fill_cols)} cols", file=sys.stderr)

# ─── 8b. SEC-direct derived PB/PE/EV/EBITDA (Yahoo-block bypass) ───
deriv = 'data/research/derived_us_pb_pe.csv'
if os.path.exists(deriv):
    d = pd.read_csv(deriv)
    d['ticker'] = d['ticker'].astype(str).str.upper().str.strip()
    d = d.drop_duplicates('ticker', keep='first').set_index('ticker')
    fills = 0
    pairs = [('pb','derived_pb'), ('pe','derived_pe'), ('mktCap','derived_mktCap'),
             ('ev_ebitda','derived_ev_ebitda'), ('ps','derived_ps')]
    for target, src_col in pairs:
        if src_col not in d.columns: continue
        m = d[src_col].dropna().to_dict()
        if target in df.columns:
            before = df[target].notna().sum()
            df[target] = df[target].where(df[target].notna(), df['ticker'].map(m))
            fills += df[target].notna().sum() - before
        else:
            df[target] = df['ticker'].map(m)
            fills += df[target].notna().sum()
    # Also derive ev_valuation fallback from ev_ebitda
    if 'ev_valuation' in df.columns and 'ev_ebitda' in df.columns:
        df['ev_valuation'] = df['ev_valuation'].where(df['ev_valuation'].notna(),
                                                      df['ev_ebitda'])
    df['mktCap_M'] = pd.to_numeric(df['mktCap'], errors='coerce') / 1e6
    print(f"  merged SEC-derived: {len(d):,} rows · added {fills:,} cell fills", file=sys.stderr)

# ─── 9. Sanity flags on extreme values (flag, don't cap) ───
def flag_extreme(s, lo, hi):
    v = pd.to_numeric(s, errors='coerce')
    return ((v < lo) | (v > hi)).fillna(False)

if 'fcf_yield' in df.columns:
    df['fcf_yield_extreme'] = flag_extreme(df['fcf_yield'], -1.0, 0.5)
if 'rev_g' in df.columns:
    df['rev_g_extreme'] = flag_extreme(df['rev_g'], -1.0, 10.0)
if 'price' in df.columns:
    df['price_extreme'] = flag_extreme(df['price'], 0, 100_000)
if 'mktCap' in df.columns:
    df['mktCap_extreme'] = flag_extreme(df['mktCap'], 0, 5e12)
if 'ev_valuation' in df.columns:
    df['ev_valuation_extreme'] = flag_extreme(df['ev_valuation'], -200, 500)
if 'roiic_1y' in df.columns:
    df['roiic_extreme'] = flag_extreme(df['roiic_1y'], -5.0, 5.0)

# ─── 10. Write back ───
df.to_csv(src, index=False)
print(f"  gaps after:  name {df['name'].isna().sum()}  sector {df['sector'].isna().sum()}  mktCap {df['mktCap'].isna().sum()}", file=sys.stderr)
print(f"Wrote {src} ({len(df)} rows, {len(df.columns)} cols)", file=sys.stderr)
