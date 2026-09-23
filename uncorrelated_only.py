"""Rebuild ONLY the uncorrelated_30 basket (the one network-dependent
basket). Exits 2 if the price fetch is rate-limited so a shell loop can
rotate processes.
"""

import sys
import warnings

import pandas as pd

sys.path.insert(0, "/home/user/cyclepapa")
from build_baskets import uncorrelated_basket, name_lookup, OUT

warnings.filterwarnings("ignore")


def main():
    full = pd.read_csv('/tmp/master_full_universe.csv', low_memory=False)
    full['adv_usd_M'] = (full.adv_usd / 1e6).round(2)
    pool = full[full.adv_usd >= 5e6].sort_values('master', ascending=False).head(200)
    b, diag = uncorrelated_basket(pool, n_target=30, eps=0.5)
    if len(b) == 0:
        print("ABORT: uncorrelated fetch produced nothing (rate limited)",
              file=sys.stderr)
        sys.exit(2)

    sectors = name_lookup(b.ticker.tolist())
    b = b.sort_values('master', ascending=False).copy()
    b['name'] = b.ticker.map(lambda t: sectors.get(t, {}).get('name', ''))
    b['sector'] = b.ticker.map(lambda t: sectors.get(t, {}).get('sector', ''))
    b['industry'] = b.ticker.map(lambda t: sectors.get(t, {}).get('industry', ''))
    b['mcap_usd_M'] = b.ticker.map(lambda t: sectors.get(t, {}).get('mcap_usd_M', 0))

    cols = ['ticker', 'name', 'sector', 'industry', 'region', 'mcap_usd_M',
            'adv_usd_M', 'master', 'M', 'E', 'DSR', 'ADV_play_now',
            'best_rank', 'combined_score', 'has_psar']
    cols = [c for c in cols if c in b.columns]
    b[cols].to_csv(OUT / 'uncorrelated_30.csv', index=False)
    pd.DataFrame([diag]).to_csv(OUT / 'uncorrelated_30_diagnostics.csv', index=False)
    print(f"uncorrelated_30: {len(b)} rows  diag={diag}")


if __name__ == "__main__":
    main()
