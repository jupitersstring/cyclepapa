# Crypto multibagger tape study

The crypto counterpart of the equity special-situations tape study. It asks
what the tape and the chain looked like before a coin re-rated, and which of
those signatures preceded 3x and 10x runs rather than faded pops.

## Pipeline

```
python -m crypto_multibaggers.panel      # FMP bars -> cleaned daily panel + crypto market index
python -m crypto_multibaggers.study      # triggers, outcomes, matched placebos, screen panel, features
python -m crypto_multibaggers.analysis   # exhibits -> data/crypto_multibaggers/analysis/*.csv, atlas.json
python -m crypto_multibaggers.report     # REPORT.md, events_master.csv.gz, atlas.html (with narrative)
```

On-chain and sector layers are pulled once and cached:

```python
from crypto_multibaggers import onchain, sectors, panel
p, meta, mkt = panel.load()
onchain.build_coinmetrics(set(meta.index))          # CoinMetrics community (no key)
onchain.build_llama(meta, set(meta.index))           # DefiLlama TVL + fees (no key)
sectors.build(meta[meta.exclusion == ""])            # CoinGecko category lists (no key)
```

Environment: `FMP_API_KEY` (required, universe + daily bars). `onchain.Etherscan`
and `onchain.transfer_activity` are an Etherscan V2 client for ERC-20 transfer
data; they read `ETHERSCAN_API_KEY` and are not yet called by the pipeline,
because Etherscan refuses keyless calls and no key was available.

## Design

| Piece | Choice |
|---|---|
| Universe | FMP `cryptocurrency-list` (4,793 USD pairs, including coins that later died) |
| Bars | FMP `historical-price-eod/full`; `volume` is USD volume |
| Cleaning | frozen quotes, pre-listing placeholders and ticker reuse (>5x persistent jumps, >20x drops out of no-volume quotes), isolated bad prints, flip-flop windows; stablecoins, wrapped / staked claims, pegged and duplicate listings excluded |
| Market | liquidity-weighted index of coins trading > $1M/day, 20% cap per coin |
| Day 0 | market-model abnormal return >= 3 baseline sigmas and >= +15% raw, no such day in the prior 60 days, day -1 close consistent with the week before, day-0 move below +400% |
| Baseline | days -180..-61 (>= 60 quotes), median USD volume >= $20k |
| Outcome | best 5-day median close within 180 days over the day -1 close (tiers 2x / 3x / 5x / 10x) |
| Placebo | 2 per event: same calendar day, other coin with no trigger within +/-60 days, nearest in baseline USD volume, volatility and age |
| Screen panel | every eligible coin every 14 days, labelled with its forward 180-day multiple |

Features (`features.py`) follow the equity study: abnormal, idiosyncratic and
unexplained volume, CUSUM build-up, BVC order imbalance, VPIN, Chaikin money
flow, OBV, CARs, volatility and liquidity ratios (Amihud, Kyle lambda), spikes,
plus crypto-specific drawdown from the high, age, BTC-relative strength and the
toxic overlays (toxic breakout, momentum, trend, OBV, accumulation, squeeze,
capitulation).
