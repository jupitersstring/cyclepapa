"""Hydrate sector / industry / country / market_cap_bucket in
asymmetry_global.csv from the FinanceDatabase library.

FinanceDatabase (https://github.com/JerBouma/FinanceDatabase) ships a
hand-curated catalogue covering ~150k equities, plus ETFs / Funds /
Indices / Cryptos. Each equity row carries sector, industry, country,
market_cap (categorical bucket), exchange, mic, currency, isin, etc.

Our master (asymmetry_global.csv) is built from a patchwork of
per-country yartseva CSVs and downstream enrichments. Sector / industry
ride along when the source had them, but a few thousand rows arrive
with those columns empty — and there is no country column at all
(only an upstream `src` country-of-listing code).

This script:
  1. Loads asymmetry_global.csv (the master).
  2. Loads the FinanceDatabase Equities table (Equities().select(
     exclude_delisted=False) — keeps delisted tickers, since the
     master is historical and includes some).
  3. Joins by ticker symbol (the index of FinanceDatabase's Equities
     table is the symbol with exchange suffix, e.g. '7203.T',
     '000002.SZ', 'AAPL', matching the master's `symbol` column).
  4. For sector / industry / market_cap_bucket: combine_first
     semantics — existing non-null master value WINS; fdb only fills
     nulls. Never overwrites.
  5. For country: adds the column if missing; only fills nulls
     (always-null on first run, so this is a pure add).
  6. Writes back to asymmetry_global.csv in place.
  7. Prints before / after coverage for sector, industry, country,
     market_cap_bucket.

The script never overwrites existing data — combine_first semantics
across the board. Smoke-test mode (--smoke) reads + joins + reports
deltas but does not write.

Usage:
  python fdb_sector_hydrate.py            # write in place
  python fdb_sector_hydrate.py --smoke    # dry run, no write
  python fdb_sector_hydrate.py --out out.csv  # write to different path
"""
from __future__ import annotations

import argparse
import sys

import pandas as pd


# FinanceDatabase column -> master column. The master already uses
# 'market_cap_bucket' for the categorical, while fdb calls it
# 'market_cap' (collision with the numeric market_cap we already have).
FDB_TO_MASTER = {
    'sector': 'sector',
    'industry': 'industry',
    'country': 'country',
    'market_cap': 'market_cap_bucket',
}


def load_fdb_equities() -> pd.DataFrame:
    """Pull the FinanceDatabase Equities catalogue. Keep delisted
    tickers in (master may include them). Returns a DataFrame indexed
    by symbol with our four columns of interest, renamed."""
    import financedatabase as fd  # local import: lets --help work without it
    eq = fd.Equities().select(exclude_delisted=False)
    # Keep only the columns we plan to fill from.
    keep = [c for c in FDB_TO_MASTER if c in eq.columns]
    eq = eq[keep].rename(columns=FDB_TO_MASTER)
    # The index is symbol; ensure no duplicate-symbol rows trip us up.
    # If duplicates exist, keep the row with the most non-null fields.
    if eq.index.duplicated().any():
        eq = eq.assign(_n=eq.notna().sum(axis=1))
        eq = (eq.sort_values('_n', ascending=False)
                .loc[~eq.index.duplicated(keep='first')]
                .drop(columns=['_n']))
    return eq


def coverage(df: pd.DataFrame, col: str) -> tuple[int, int]:
    """(filled, total) for a column. Missing column -> (0, total)."""
    n = len(df)
    if col not in df.columns:
        return 0, n
    return int(df[col].notna().sum()), n


def hydrate(master: pd.DataFrame, fdb: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """Fill nulls in master from fdb. Returns (new_master, before, after).
    before/after are {col: (filled, total)}."""
    target_cols = list(FDB_TO_MASTER.values())
    before = {c: coverage(master, c) for c in target_cols}

    m = master.set_index('symbol', drop=False)
    # Restrict fdb to symbols we actually have, to keep the join cheap.
    common = m.index.intersection(fdb.index)
    f = fdb.loc[common]

    for col in target_cols:
        if col not in f.columns:
            continue
        if col not in m.columns:
            # New column (country): add it as all-null first so we can
            # use combine_first uniformly.
            m[col] = pd.NA
        # Only fill where master is null AND fdb has a value.
        mask = m[col].isna() & m.index.isin(f.index)
        if not mask.any():
            continue
        sym_to_fill = m.index[mask].intersection(f.index)
        # Drop fdb rows that are themselves null for this column.
        fill_vals = f.loc[sym_to_fill, col].dropna()
        if fill_vals.empty:
            continue
        m.loc[fill_vals.index, col] = fill_vals.values

    # Restore positional 'symbol' column ordering: drop the index name
    # and reset.
    m = m.reset_index(drop=True)
    after = {c: coverage(m, c) for c in target_cols}
    return m, before, after


def print_coverage_table(before: dict, after: dict) -> None:
    cols = list(before.keys())
    print(f"\n{'column':22s}  {'before':>12s}  {'after':>12s}  {'+delta':>10s}  {'pct':>6s}",
          file=sys.stderr)
    print('-' * 70, file=sys.stderr)
    for c in cols:
        b_filled, total = before[c]
        a_filled, _ = after[c]
        delta = a_filled - b_filled
        pct = 100.0 * a_filled / total if total else 0.0
        print(f"{c:22s}  {b_filled:>6,} /{total:>5,}  "
              f"{a_filled:>6,} /{total:>5,}  {delta:>+10,}  {pct:>5.1f}%",
              file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--in', dest='in_path', default='asymmetry_global.csv',
                    help='input CSV (default: asymmetry_global.csv)')
    ap.add_argument('--out', default=None,
                    help='output CSV path (default: overwrite input in place)')
    ap.add_argument('--smoke', action='store_true',
                    help='dry run: report coverage deltas but do not write')
    args = ap.parse_args()
    out_path = args.out or args.in_path

    print(f'[fdb-hydrate] loading master {args.in_path}', file=sys.stderr)
    master = pd.read_csv(args.in_path)
    print(f'  {len(master):,} rows, {len(master.columns)} cols',
          file=sys.stderr)

    print('[fdb-hydrate] loading FinanceDatabase Equities catalogue',
          file=sys.stderr)
    try:
        fdb = load_fdb_equities()
    except Exception as e:
        print(f'[fdb-hydrate] ERROR loading FinanceDatabase: {e}',
              file=sys.stderr)
        return 2
    print(f'  {len(fdb):,} symbols with sector/industry/country tags',
          file=sys.stderr)

    matched = master['symbol'].isin(fdb.index).sum()
    print(f'  {matched:,} / {len(master):,} master symbols matched in fdb '
          f'({100*matched/len(master):.1f}%)', file=sys.stderr)

    new_master, before, after = hydrate(master, fdb)
    print_coverage_table(before, after)

    if args.smoke:
        print('\n[fdb-hydrate] --smoke: not writing.', file=sys.stderr)
        return 0

    # Preserve the original column order, with `country` appended (if newly
    # added) just after `industry` so it lives near its siblings.
    orig_cols = list(master.columns)
    new_cols = [c for c in new_master.columns if c not in orig_cols]
    if 'country' in new_cols:
        # Insert country right after industry for readability.
        if 'industry' in orig_cols:
            i = orig_cols.index('industry') + 1
            orig_cols = orig_cols[:i] + ['country'] + orig_cols[i:]
            new_cols.remove('country')
    final_cols = orig_cols + new_cols
    new_master = new_master[final_cols]

    new_master.to_csv(out_path, index=False)
    print(f'\n[fdb-hydrate] wrote {out_path}: {len(new_master):,} rows, '
          f'{len(new_master.columns)} cols', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
