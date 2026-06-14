# Durable cache

This directory holds **repo-tracked** copies of the expensive-to-recreate
working data so that hours of rate-limited yfinance fetching are not lost
when the sandbox / working tree is reset.

```
data/
  cache/   compressed daily + monthly + intraday OHLCV pickles (*.pkl.bz2)
  spy/     SPY benchmark pickles (*.pkl.bz2)
  wiki/    Wikipedia index constituent CSVs (kept uncompressed - small)
```

## After a sandbox reset / fresh clone

Run **once** before any other pipeline command:

```
python3 bootstrap_cache.py
```

This decompresses every `data/cache/*.pkl.bz2` into `/tmp/cyclepapa_dl_*.pkl`
and copies the wiki CSVs into `/tmp/cyclepapa_wiki/`. After it completes,
`momentum_rank.py`, `consolidate_global_equities.py`, etc. all find their
caches as before and run normally.

## How writes are persisted

`momentum_rank.py` writes to **both** `/tmp` (fast working copy) and
`data/cache/` (compressed durable copy) on every checkpoint save. So
running a fresh universe re-cache automatically updates the
repo-trackable durable copy — committing periodically locks the new
data in.

The Wikipedia index fetcher mirrors to `data/wiki/` the same way.

## What's still ephemeral (rebuildable cheaply from cache)

  - `momentum_rank_*_YYYYMMDD.csv`  (per-universe flagged outputs)
  - `global_equities_consolidated.csv`
  - `global_equity_screen.xlsx`
  - `/tmp/*.log`

If the working tree is wiped, these all rebuild in **minutes** by
re-running `momentum_rank.py --universe ...` on the durable caches
(no fresh yfinance downloads), then `consolidate_global_equities.py`
and `build_xlsx_report.py`.
