# earnings_model — earnings inflection, valuation-gap & pre-breakout toolkit

A headless **library + CLI** that builds an equity universe from
[`financedatabase`](https://github.com/JerBouma/FinanceDatabase), pulls
fundamentals from [`yfinance`](https://github.com/ranaroussi/yfinance), and
monitors **revenue / EBITDA / earnings growth, acceleration and inflection**
by **region**, **industry** and **market-cap size bucket** (nano → mega). It then:

- **clusters** names by growth/acceleration behaviour (K-means);
- flags **industries (and names) where earnings are inflecting while the
  valuation/price has not responded**; and
- scores the **pre-breakout** setup — *dead money for 1–2 years while the
  business quietly improves* — the coiled spring before a re-rating.

Ships with **UK (LSE/GBP)** and **US small-cap** presets (`uk`, `us-small`,
`uk+us-small`); the universe is just a `financedatabase` query, so any
country/exchange works. Analysis ranks **within each region** (a P/E only means
something against comparable peers in the same market).

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
# 1. Build the universe. Default is UK LSE/GBP; use a preset for more:
python -m earnings_model build-universe --preset uk+us-small   # UK + US small caps

# 2. Fetch fundamentals (cached, resumable). Start small to sanity-check;
#    --sample N grabs a random spread; --refresh forces a refetch (e.g. to pick
#    up the multi-year price history).
python -m earnings_model fetch --sample 300
python -m earnings_model fetch                                 # the whole universe

# 3. Score + aggregate + find inflecting-but-unloved + pre-breakout setups
python -m earnings_model analyze

# 4. Cluster by growth/acceleration behaviour (k auto-picked via silhouette)
python -m earnings_model cluster

# Named screens (operating-only, region-aware, artifact-guardrailed):
python -m earnings_model screen yoy-unpriced -n 30          # YoY accel/inflection, not priced
python -m earnings_model screen divergence -n 30            # max behaviour change, min price reaction
python -m earnings_model screen forensic -n 30 --region EU  # margin-expanding, no lumps (strictest)
python -m earnings_model screen asymmetry --region UK -n 20

# Inspect any cached output:
python -m earnings_model show inflecting_lagging -n 20
python -m earnings_model show prebreakout -n 30      # dead-money + improving + cheap
python -m earnings_model show case_studies -n 20     # historical base->breakout shapes

# Or run the whole pipeline at once:
python -m earnings_model run --preset uk+us-small --sample 800
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
| `prebreakout.csv` | **names** ranked by `prebreakout_score` (improving + dormant + cheap) |
| `case_studies.csv` | names whose price history shows the *long base → breakout* shape |
| `clusters.csv` / `cluster_profile.csv` | K-means assignments + cluster behaviour profiles |

### Durable snapshots (surviving a container rollback)

`cache/` is gitignored and **ephemeral** — on a hosted/remote runner it can be
rolled back, wiping the assembled tables (and reverting fetched surprise data)
even though the code is safe in git. `scripts/snapshot.py` keeps a compact copy
of the universe + assembled `fundamentals`/`scored` tables under `data/` (which
**is** tracked), so the analysis can always be rehydrated:

```bash
python scripts/snapshot.py rebuild   # cache/raw -> fundamentals + scored (NO network)
python scripts/snapshot.py save      # cache/*.parquet -> data/   ; then: git add data && commit
python scripts/snapshot.py restore   # data/*.parquet -> cache/   (after a rollback)
python scripts/snapshot.py status    # row + coverage counts on both sides
```

`rebuild` re-derives every metric column straight from the already-fetched
`cache/raw/*.json` with no Yahoo calls; the only thing it can't recover offline
is *new* EPS-surprise coverage, which `scripts/backfill_surprises.py` tops up
(resumable, US/UK/EU/CA/ANZ only — the regions Yahoo actually carries).

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

- **Pre-breakout** — `prebreakout_score = 0.45·inflection_score + 0.30·dormancy
  + 0.25·cheapness`, **gated** on `inflection_score ≥ 0.5` (a cheap, dormant
  stock whose business is *not* improving is a value trap, heavily discounted).
  `dormancy` (dead money 1–2y) = flat/down vs peers over 24m + flat 2y trend +
  sitting near the base. Context: `basing_tightness` (low realised vol = coiled),
  `breaking_out` (dormant + improving, price just lifting). `case_studies()`
  scans the cached monthly series for the historical *long flat base → explosive
  move* archetype to characterise the price shape empirically.

**Named screens** (`earnings_model/screens.py`, via `screen <name>`). All run on
operating companies only, rank within region, and apply artifact guardrails (no
nano-caps, require a sane **positive** multiple, de-dupe cross-listings, drop
ratio blow-ups off a near-zero base). QoQ is only ~40% populated so it enters as
a *bonus*, never equal-weighted with annual (YoY).
- **yoy-unpriced** — annual growth accel/inflection × cheap × price-dormant.
- **accel-unpriced** — yoy-unpriced + a 20% quarterly bonus.
- **asymmetry** — operating inflection + cheap + dormant.
- **inflecting-positive** — sales or EBITDA growth crossing from ≤0 to >0.
- **divergence** — biggest *behaviour* change (accel + swing + inflection breadth)
  vs least *price* reaction (3/12/24m return); cheapness-independent.
- **forensic** — strictest: from the multi-year series, revenue rising ≥2/3 yrs,
  **EBITDA positive throughout, margin expanding, no one-off lump** — removes
  sign-flip "turnarounds" and licensing/M&A blips that headline growth rewards.

**Forensic trajectory metrics** (`metrics.forensic_block`, on the raw annual
series): `rev_up_frac`, `ebitda_margin`, `margin_delta3` (last-3-yr margin
change, all-positive), `ebitda_all_pos`, `ebitda_lump`.

**Multi-year price features.** From 5y of monthly closes: trailing returns to
36m, `max_drawdown`, `range_position` (place in the 3y range), annualised 2y
`trend_slope`, and `realized_vol`.

**Peer group.** With one region, ranks default to the **whole universe**; with
several (e.g. `uk+us-small`) ranking is **within each region** automatically,
since valuations aren't comparable across markets. Override with `--group-cols`
(`industry`, `industry,size_bucket`, …).

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
  universe.py      # financedatabase universe + size buckets + region/presets
  fundamentals.py  # cached yfinance fetch (retry/backoff/curl_cffi), 5y price features
  metrics.py       # pure growth / acceleration / inflection math
  valuation.py     # inflection_score, valuation_richness, gap_score
  aggregate.py     # industry & industry×size aggregation, inflecting_lagging (per region)
  cluster.py       # K-means + cluster profiling
  prebreakout.py   # pre-breakout score (improving×dormant×cheap) + case studies
  pipeline.py      # orchestration
  cli.py           # `python -m earnings_model ...`
scripts/selftest.py          # offline end-to-end analytics test (no network)
scripts/snapshot.py          # durable data/ snapshot: rebuild / save / restore / status
scripts/backfill_surprises.py# resumable EPS-surprise back-fill (developed markets)
scripts/screen_excel.py      # multi-sheet cross-screen workbook
data/                        # committed snapshot (universe + fundamentals + scored)
```

Run the offline self-test (no network needed):

```bash
PYTHONPATH=. python scripts/selftest.py
```
