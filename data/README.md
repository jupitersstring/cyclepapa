# Persisted analysis artifacts

Everything under `data/` is durable output from the screen + augment +
PSAR + master pipeline. Snapshotted via `persist_results.py`. Raw OHLC is
deliberately NOT versioned — it is multi-GB and refetched from yfinance.

## Layout

```
data/
  stars_aligned/      18 region CSVs, ~5,900 non-rejected tickers + augmented
                      legs (W/Q/D/DA/R schools + M + E + DSR + ADV)
  psar/               MTF PSAR composite ranks
                        mtf_psar_rank_5916.csv      first scan, non-rejected only
                        mtf_psar_rank_full.csv      expanded 15,016-ticker scan
                        mtf_psar_rank_full_clean.csv same, OTC pink-sheet wrappers removed
  master/             Cross-system merged scoring
                        master_cross_system.csv     all tickers with both PSAR + legs
                        final_master_liquid.csv     filtered to >=$2M/day USD
                        final_master_named.csv      top 25 with company names + sectors
                        final_coiled_springs.csv    coiled-springs watchlist
                        final_coiled_named.csv      coiled springs, named
  picks/              Top-N output lists
                        best_per_leg.csv            top 10 per leg (15 legs)
                        cross_leg_conviction.csv    tickers ranked by # of legs they top
                        master_top10_named.csv      named master top 10
                        mtf_psar_top*_named.csv     ranked + named PSAR slices
                        mtf_psar_institutional*.csv institutional-grade subsets
                        mtf_psar_top_curated.csv    deduped to primary listings
                        pre_mega_adv_wide.csv       ADV signature of mega-winners pre-launch
                        minervini_metric_eval.csv   t-test results on Minervini measures
                        cross_region_top_uncorrelated.csv  greedy max-IS portfolio
  universe/           iShares ETF holdings CSV caches (EWUS, IEUS, IJR, ...)
  stars_aligned_top_picks.xlsx   The deliverable Excel workbook
```

## Refreshing

Every analysis script writes to `/tmp/*`. To persist:

```
python persist_results.py            # copy + commit + push
python persist_results.py --dry-run  # show what would copy
python persist_results.py --no-push  # commit locally only
```

Run this after any expensive scan/augment, before the session ends.
