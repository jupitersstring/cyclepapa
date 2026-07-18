"""
Full accounting of a screening run: every universe ticker lands in exactly
one bucket, so throttling or bugs can't silently drop names.

Usage (from the directory holding the .ckpt_*.parquet files):
    python screener/audit_run.py screener/universe_global.csv [--max-fails 3]
"""
import argparse
from pathlib import Path

import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument('universe_file')
    p.add_argument('--max-fails', type=int, default=3)
    p.add_argument('--within-low-pct', type=float, default=15.0)
    args = p.parse_args()

    uni = set(pd.read_csv(args.universe_file)['ticker'])
    ck1, fk, ck2 = (Path('.ckpt_prices.parquet'),
                    Path('.ckpt_prices_fails.parquet'),
                    Path('.ckpt_fund.parquet'))

    done = pd.read_parquet(ck1) if ck1.exists() else pd.DataFrame(columns=['ticker', 'dist'])
    failsd = (pd.read_parquet(fk).set_index('ticker')['fails'].to_dict()
              if fk.exists() else {})
    dead = {t for t, n in failsd.items() if n >= args.max_fails}
    strikes = {t for t, n in failsd.items() if 0 < n < args.max_fails}

    priced = set(done['ticker'])
    surv = set(done[done['dist'] <= args.within_low_pct / 100]['ticker'])
    filtered = set(done[done['dist'].isna()]['ticker'])
    nonsurv = priced - surv - filtered
    pending1 = uni - priced - dead

    f2 = pd.read_parquet(ck2) if ck2.exists() else pd.DataFrame()
    if not f2.empty and 'passed' not in f2.columns:
        f2['passed'] = True
    evaluated = set(f2['ticker']) if not f2.empty else set()
    passed = set(f2[f2['passed'] == True]['ticker']) if not f2.empty else set()
    pending2 = surv - evaluated

    print(f"Universe:                 {len(uni):>7}")
    print(f"  priced, survivor:       {len(surv & uni):>7}")
    print(f"  priced, above cutoff:   {len(nonsurv & uni):>7}")
    print(f"  priced, filtered (NaN): {len(filtered & uni):>7}  (short history / penny)")
    print(f"  dead-listed:            {len(dead & uni):>7}  ({args.max_fails}+ non-throttle misses)")
    print(f"  PENDING stage 1:        {len(pending1):>7}  <- will retry on --resume/--converge")
    unacc = uni - priced - dead - pending1
    print(f"  unaccounted:            {len(unacc):>7}  (must be 0)")
    print()
    print(f"Survivors:                {len(surv):>7}")
    print(f"  evaluated, passing:     {len(passed & surv):>7}")
    print(f"  evaluated, failing:     {len((evaluated - passed) & surv):>7}")
    print(f"  PENDING stage 2:        {len(pending2):>7}  <- will retry on --resume/--converge")
    print()
    print(f"Death-strike watchlist (1-{args.max_fails - 1} strikes): {len(strikes)}")
    if unacc:
        print("\nWARNING: unaccounted tickers, e.g.:", sorted(unacc)[:10])


if __name__ == '__main__':
    main()
