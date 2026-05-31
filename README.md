# earnings_model — UK earnings inflection & valuation-gap toolkit

A headless **library + CLI** that builds an equity universe from
[`financedatabase`](https://github.com/JerBouma/FinanceDatabase), pulls
fundamentals from [`yfinance`](https://github.com/ranaroussi/yfinance), and
monitors **revenue / EBITDA / earnings growth, acceleration and inflection**
by **industry** and **market-cap size bucket** (nano → mega). It then:

- **clusters** names by growth/acceleration behaviour (K-means), and
- flags the setup you actually care about: **industries (and names) where
  earnings are inflecting while the valuation/price has not responded.**

Starts with the **UK equities complex** (LSE, GBP) but the universe is just a
`financedatabase` query, so any country/exchange works.

> Heavy fetching is cached to disk (`cache/`) so the analytics layer runs fast
> and offline. Yahoo rate-limits cloud IPs hard (HTTP 429); the fetcher uses a
> `curl_cffi` browser session + exponential backoff to get through, but for a
> full universe scan run the `fetch` step from a machine with clean access.

## Install

```bash
pip install -r requirements.txt
pip install --no-deps financedatabase   # see requirements.txt for why --no-deps
```

Requires Python 3.10+. Tested on pandas 3.0 / numpy 2.x.

## Quickstart

```bash
# 1. Build the universe (UK LSE/GBP by default): industry + size bucket
python -m earnings_model build-universe

# 2. Fetch fundamentals (cached, resumable). Start small to sanity-check:
python -m earnings_model fetch --limit 100
#    ...then widen. Re-runs reuse the cache; --refresh forces a refetch.
python -m earnings_model fetch

# 3. Score + aggregate + find the inflecting-but-unloved names/industries
python -m earnings_model analyze

# 4. Cluster by growth/acceleration behaviour (k auto-picked via silhouette)
python -m earnings_model cluster

# Inspect any output:
python -m earnings_model show inflecting_lagging -n 20
python -m earnings_model show valuation_gap -n 30
python -m earnings_model show cluster_profile

# Or run the whole pipeline at once:
python -m earnings_model run --limit 300
```

You can also drive it as a library:

```python
from earnings_model import pipeline, valuation, cluster
funda = pipeline.step_fetch(limit=200)
scored = valuation.add_all_scores(funda)            # global (cross-sectional)
shortlist = valuation.valuation_gap_table(scored)   # ranked names
res = cluster.run_kmeans(scored)                    # res["labeled"], res["profile"]
```

## Outputs (written to `cache/`)

| File | What it is |
|---|---|
| `universe.parquet` | the investable universe + `industry`, `size_bucket` |
| `fundamentals.parquet` | per-name growth/accel/inflection metrics + valuation + returns |
| `scored.parquet` | the above + `inflection_score`, `valuation_richness`, `gap_score` |
| `industry.csv` | per-industry medians, % inflecting, median multiples/returns |
| `industry_size.csv` | the same, split by size bucket (nano → mega) |
| `inflecting_lagging.csv` | **industries** ranked: inflecting but cheap & quiet (`cell_gap`) |
| `valuation_gap.csv` | **names** ranked by `gap_score` |
| `clusters.csv` / `cluster_profile.csv` | K-means assignments + cluster behaviour profiles |

## Methodology

Histories are ordered oldest → newest; annual statements are the primary
signal (~4 fiscal years from yfinance), with latest **quarterly YoY** as a
timeliness overlay.

- **Growth** — YoY ratio growth `vₜ/vₜ₋₁ − 1`, defined only when the prior
  value is positive (a negative-base P/E or loss makes ratio growth
  meaningless).
- **Acceleration** — change in growth rate (`*_accel`). Because loss-makers
  break ratio growth, we also compute `*_accel_abs` (acceleration of the
  *absolute* level change), which still detects a trough turning up.
- **Inflection flags** — hard turns: loss → profit (`*_turned_positive`), an
  absolute trough turning up (`*_trough_up`), or positive growth that is
  accelerating. `broad_inflection` = ≥2 of revenue/EBITDA/earnings inflecting.
- **`inflection_score`** (0–1) — 70 % peer-ranked acceleration signals + 30 %
  hard inflection flags.
- **`valuation_richness`** (0–1) — peer rank of forward P/E, trailing P/E,
  EV/EBITDA, P/S, P/B (non-positive multiples masked). Higher = dearer.
- **`gap_score`** = `0.5·inflection_score + 0.3·cheapness + 0.2·price_quiet`,
  where `cheapness = 1 − valuation_richness` and `price_quiet = 1 − price_response`
  (peer rank of trailing 12m return). **High = earnings inflecting, multiple
  cheap, price hasn't moved.**

**Peer group.** Ranks default to the **whole universe** (cross-sectional) — the
right lens for "which industries are inflecting while valuations lag". Pass
`--group-cols industry` (or `industry,size_bucket`) for sector-relative ranking.

**Industry ranking** (`inflecting_lagging`) compares industries on **absolute**
median multiples (a within-industry percentile would be ~0.5 everywhere):
`cell_gap = industry_inflection − industry_richness + ¼·(industry_quiet − ½)`.

**Size buckets.** Taken from the `financedatabase` `market_cap` label
(Nano → Mega). ~70 % of UK domestics carry no label, so `fetch` backfills
`Unclassified` names from live market cap (USD-equivalent thresholds); disable
with `--no-backfill-size`.

**Clustering.** Standardised growth+acceleration feature vector, median-imputed,
`k` chosen by silhouette over 3–10 (override with `--k`). Each cluster gets a
behaviour label (e.g. *Accelerating leaders*, *Inflecting up (low base)*,
*High growth, slowing*, *Lagging / contracting*).

## Caveats

- **yfinance depth & quality** — typically ~4 annual + ~5 quarterly periods,
  occasionally with gaps; growth is point-in-time as-reported, not
  restatement-adjusted. Treat as a screen, not gospel.
- **Cross-industry valuation** is naive by construction (banks look "cheap",
  software "dear"); use `--group-cols industry` when you want sector-relative.
- **LSE prices are in pence** — irrelevant here (we use ratios), but mind it if
  you extend with absolute price logic.

## Package layout

```
earnings_model/
  universe.py      # financedatabase universe + size buckets
  fundamentals.py  # cached yfinance fetch (retry/backoff/curl_cffi)
  metrics.py       # pure growth / acceleration / inflection math
  valuation.py     # inflection_score, valuation_richness, gap_score
  aggregate.py     # industry & industry×size aggregation, inflecting_lagging
  cluster.py       # K-means + cluster profiling
  pipeline.py      # orchestration
  cli.py           # `python -m earnings_model ...`
scripts/selftest.py  # offline end-to-end analytics test (no network)
```

Run the offline self-test (no network needed):

```bash
PYTHONPATH=. python scripts/selftest.py
```
