"""Build six baskets from the bias-fixed master analysis.

Loads /tmp/master_full_universe.csv and constructs:

  1. MAX CONVICTION     — top 20 by master, capped to 1 per sector
  2. INSTITUTIONAL      — top 25 by master at >=$20M ADV (Minervini floor)
  3. UNCORRELATED 30    — greedy max-IS on weekly returns from the master pool
  4. PER-REGION         — top 1 from each of the 18 regions
  5. THEMATIC: AI/TECH  — Tech sector across regions, top 15 by master
  6. CONTRARIAN: REITS  — Real Estate sector, top 12 by master
  7. PER-SCHOOL         — top of each (Weinstein, Qullamaggie, DeMark, Darvas, Regime)
  8. COILED SPRINGS     — M>=70 + DSR>=70 + E<35 (structure ready, no trigger)

Each basket gets a single CSV under data/baskets/ with full leg detail.
The uncorrelated basket also reports diagnostics: mean/max pairwise corr,
effective bets, top eigenvalue share.
"""

import sys
import glob
import warnings
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from screen import fetch_ohlc, fetch_fx, currency_for_ticker, usd_close
import yfinance as yf

warnings.filterwarnings("ignore")

REPO = Path("/home/user/cyclepapa")
OUT = REPO / "data" / "baskets"


def name_lookup(tickers, fx=None):
    """Pull name + sector for each ticker via yfinance."""
    FX = {'JPY': 0.0065, 'INR': 0.0117, 'KRW': 0.00073, 'TWD': 0.031, 'HKD': 0.128,
          'CNY': 0.139, 'GBp': 0.0127, 'GBP': 1.27, 'EUR': 1.08, 'CHF': 1.12,
          'SEK': 0.095, 'NOK': 0.092, 'DKK': 0.145, 'AUD': 0.65, 'NZD': 0.60,
          'USD': 1.0, 'MXN': 0.055}
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info or {}
            cur = info.get('currency') or 'USD'
            out[t] = {
                'name': (info.get('longName') or info.get('shortName') or '')[:32],
                'sector': (info.get('sector') or '')[:14],
                'industry': (info.get('industry') or '')[:24],
                'mcap_usd_M': round((info.get('marketCap') or 0) * FX.get(cur, 1.0) / 1e6),
            }
        except Exception:
            out[t] = {'name': '', 'sector': '', 'industry': '', 'mcap_usd_M': 0}
    return out


def cap_per_sector(df, n_total, sectors_dict, cap=2):
    """Take rows in df, capped to `cap` per sector, up to n_total."""
    df = df.copy()
    df['sector'] = df.ticker.map(lambda t: sectors_dict.get(t, {}).get('sector', ''))
    out, counts = [], {}
    for _, row in df.iterrows():
        sec = row['sector'] or '_unknown'
        if counts.get(sec, 0) >= cap:
            continue
        out.append(row)
        counts[sec] = counts.get(sec, 0) + 1
        if len(out) >= n_total:
            break
    return pd.DataFrame(out)


def uncorrelated_basket(pool, n_target=30, eps=0.5):
    """Greedy max-IS: pick highest-master that doesn't exceed |corr|=eps
    with any already-picked name. Uses weekly USD-normalized returns."""
    tickers = pool.ticker.tolist()
    print(f"Fetching 24mo OHLC for {len(tickers)} candidates...", file=sys.stderr)
    daily = fetch_ohlc(tickers, period="24mo", chunk=40, retries=4,
                       pause_between_chunks=1.0)
    closes = daily.get("Close")
    if closes is None or closes.empty:
        return pool.head(0), {}
    have = [t for t in tickers if t in closes.columns]
    print(f"Got Close data for {len(have)}/{len(tickers)}", file=sys.stderr)
    ccys = {currency_for_ticker(t) for t in have}
    fx = fetch_fx(ccys, period="24mo") if any(c != "USD" for c in ccys) else {}
    usd = pd.DataFrame({t: usd_close(daily, t, fx) for t in have}).dropna(how="all")
    weekly = usd.resample("W-FRI").last().pct_change().dropna()
    keep = [t for t in weekly.columns if weekly[t].notna().sum() >= 40]
    weekly = weekly[keep]
    if weekly.shape[1] < 2:
        return pool.head(0), {}
    corr = weekly.corr().abs()
    pool_idx = pool.set_index("ticker")
    chosen = []
    for t in pool_idx.index:
        if t not in corr.columns:
            continue
        if all(corr.loc[t, c] <= eps for c in chosen):
            chosen.append(t)
        if len(chosen) >= n_target:
            break
    if not chosen:
        return pool.head(0), {}
    sub = weekly[chosen]
    cov = sub.cov().values
    eig = np.linalg.eigvalsh(cov)
    n_eff = (np.trace(cov) ** 2) / np.trace(cov @ cov) if cov.size else 0
    iu = np.triu_indices_from(corr.loc[chosen, chosen].values, k=1)
    vals = corr.loc[chosen, chosen].values
    diag = {
        'n': len(chosen),
        'mean_corr': float(np.mean(vals[iu])) if iu[0].size else 0,
        'max_corr': float(np.max(vals[iu])) if iu[0].size else 0,
        'n_eff': float(n_eff),
        'top_eig_share': float(eig.max() / eig.sum()) if eig.size else 0,
    }
    return pool[pool.ticker.isin(chosen)], diag


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading master + name lookups...", file=sys.stderr)
    full = pd.read_csv('/tmp/master_full_universe.csv')
    full['adv_usd_M'] = (full.adv_usd / 1e6).round(2)
    print(f"Master pool: {len(full)} tickers", file=sys.stderr)

    # Pre-fetch names+sectors for the top 200 by master (covers all baskets)
    seed = full.sort_values('master', ascending=False).head(200)
    sectors = name_lookup(seed.ticker.tolist())
    print(f"Looked up {len(sectors)} ticker names+sectors", file=sys.stderr)

    def attach(df):
        df = df.copy()
        df['name'] = df.ticker.map(lambda t: sectors.get(t, {}).get('name', ''))
        df['sector'] = df.ticker.map(lambda t: sectors.get(t, {}).get('sector', ''))
        df['industry'] = df.ticker.map(lambda t: sectors.get(t, {}).get('industry', ''))
        df['mcap_usd_M'] = df.ticker.map(lambda t: sectors.get(t, {}).get('mcap_usd_M', 0))
        return df

    cols = ['ticker', 'name', 'sector', 'industry', 'region', 'mcap_usd_M',
            'adv_usd_M', 'master', 'M', 'E', 'DSR', 'ADV_play_now',
            'best_rank', 'combined_score', 'has_psar']

    baskets = {}

    # 1. MAX CONVICTION: top 20 by master, 2-per-sector cap (no liquidity floor)
    pool = full.sort_values('master', ascending=False).head(80)
    pool = attach(pool)
    b1 = cap_per_sector(pool, n_total=20, sectors_dict=sectors, cap=2)
    baskets['max_conviction_top20'] = b1[cols]

    # 2. INSTITUTIONAL: top 25 at >= $20M ADV
    liq20 = attach(full[full.adv_usd >= 20e6].sort_values('master', ascending=False).head(60))
    b2 = cap_per_sector(liq20, n_total=25, sectors_dict=sectors, cap=3)
    baskets['institutional_top25'] = b2[cols]

    # 3. UNCORRELATED 30: greedy IS on top-200 by master with min $5M ADV
    pool3 = full[full.adv_usd >= 5e6].sort_values('master', ascending=False).head(200)
    b3, diag = uncorrelated_basket(pool3, n_target=30, eps=0.5)
    b3 = attach(b3.sort_values('master', ascending=False))
    baskets['uncorrelated_30'] = b3[cols]
    pd.DataFrame([diag]).to_csv(OUT / 'uncorrelated_30_diagnostics.csv', index=False)
    print(f"Uncorrelated diagnostics: {diag}", file=sys.stderr)

    # 4. PER-REGION: top 1 from each region
    per_region = (full[full.adv_usd >= 2e6]
                  .sort_values('master', ascending=False)
                  .groupby('region', as_index=False).head(1))
    # ensure full name lookup for any unseen tickers
    extras = [t for t in per_region.ticker if t not in sectors]
    if extras:
        sectors.update(name_lookup(extras))
    baskets['per_region_18'] = attach(per_region.sort_values('master', ascending=False))[cols]

    # 5. THEMATIC: TECH cluster (top 15 tech by master, $5M+)
    pool5 = full[full.adv_usd >= 5e6].sort_values('master', ascending=False).head(200)
    pool5 = attach(pool5)
    tech = pool5[pool5.sector == 'Technology'].head(15)
    baskets['tech_15'] = tech[cols]

    # 6. CONTRARIAN: REIT/Real Estate cluster
    reits = pool5[pool5.sector == 'Real Estate'].head(12)
    baskets['reits_12'] = reits[cols]

    # 7. PER-SCHOOL: best of each weekly school at $5M+
    schools = {'W_W': 'weinstein', 'Q_W': 'qullamaggie',
               'D_W': 'demark', 'DA_W': 'darvas', 'R_W': 'regime'}
    pool_school = full[full.adv_usd >= 5e6].copy()
    school_picks = []
    for col, name in schools.items():
        if col not in pool_school.columns:
            continue
        top10 = pool_school.dropna(subset=[col]).sort_values(col, ascending=False).head(10)
        top10 = top10.assign(school=name)
        school_picks.append(top10)
    per_school = pd.concat(school_picks, ignore_index=True)
    extras = [t for t in per_school.ticker if t not in sectors]
    if extras:
        sectors.update(name_lookup(extras))
    per_school = attach(per_school)
    baskets['per_school_50'] = per_school[cols + ['school']]

    # 8. COILED SPRINGS: M>=70 + DSR>=70 + E<35 + $5M+ ADV
    coiled = full[(full.M >= 70) & (full.DSR >= 70) & (full.E < 35) &
                   (full.adv_usd >= 5e6)].sort_values('M', ascending=False).head(20)
    extras = [t for t in coiled.ticker if t not in sectors]
    if extras:
        sectors.update(name_lookup(extras))
    baskets['coiled_springs_20'] = attach(coiled)[cols]

    # Save all baskets
    for name, df in baskets.items():
        path = OUT / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"  wrote {path} ({len(df)} rows)", file=sys.stderr)

    # Print compact summaries
    for name, df in baskets.items():
        print(f"\n=== BASKET: {name.upper()} ({len(df)}) ===")
        show_cols = ['ticker', 'name', 'sector', 'region', 'mcap_usd_M',
                     'adv_usd_M', 'master', 'M', 'E', 'DSR']
        if 'school' in df.columns:
            show_cols.insert(0, 'school')
        show_cols = [c for c in show_cols if c in df.columns]
        print(df[show_cols].to_string(index=False, float_format=lambda x: f"{x:.1f}"))


if __name__ == "__main__":
    main()
