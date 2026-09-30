# Crypto multibagger tape study

As of 2026-09-28. 12,829 crypto re-ratings (2017-2026) across 2,585 coins, 25,624 matched placebo windows, 180-day outcomes. Crypto counterpart of the equity special-situations tape study (same measures and placebo design).

## What the study found

- **19% of re-ratings reached 3x within 180 days and 3.3% reached 10x**, against 7.5% and 0.9% for matched placebo windows.
- In equities, abnormal volume builds for weeks before a re-rating. In crypto it does not: final-week volume sits at placebo levels (AUC 0.50), and before 10x runs the prior two months are quieter than ordinary tape (AUC 0.43). What moves first is volatility: final-week volatility against the coin's own baseline is the strongest single separator (AUC 0.66, 0.70 before 10x runs), with prior up-spikes and a high VPIN percentile close behind. Prices were falling into day 0: run-up -19% over 60 days.
- Once a coin pops, strength separates the multibaggers. The day-0 move itself is the best single tell, then money flow, a less negative 60-day trend and more days above the 20-day average. Younger, smaller coins that trade less with the market convert more often. Faded pops come out of steeper downtrends with persistent selling.
- Two different questions have two different answers. Which coins will 3x at some point? The washed-out ones: deep 60-day drawdowns, trading under their 50- and 200-day averages and lagging BTC (max drawdown inside 60d: 1.41x the base rate in 2022+). Which pops will follow through? The strong ones: the top fifth of 2022+ triggers by day-0 return reached 3x 23% of the time vs 15% for all triggers. The best archetype out of time was 'Toxic breakout + Trend continuation': fitted on 2017-21, it converted 22% of 2022+ triggers vs 15%. As standalone screens the toxic overlays do not beat their plain signals; their value is in the archetypes.

## Exhibit A: families

| Family | Events | Coins | Paid | Durable 60d | 3x+ | 10x+ | Median multiple | Run-up -60..-1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All re-ratings | 12,829 | 2,585 | 70% | 38% | 19% | 3.3% | 1.69x | -19% |
| 10x+ within 180 days | 401 | 349 | 77% | 91% | 100% | 100.0% | 15.13x | -22% |
| 5-10x | 711 | 576 | 77% | 87% | 100% | 0.0% | 6.43x | -16% |
| 3-5x | 1,244 | 893 | 76% | 78% | 100% | 0.0% | 3.66x | -18% |
| 2-3x (doublers) | 2,225 | 1,353 | 77% | 63% | 0% | 0.0% | 2.36x | -18% |
| Under 2x (faded pops) | 7,564 | 2,319 | 65% | 17% | 0% | 0.0% | 1.37x | -20% |
| Micro tape (< $250k/day) | 5,389 | 1,968 | 69% | 39% | 21% | 3.9% | 1.71x | -24% |
| Small tape ($250k-$5M/day) | 4,892 | 1,503 | 69% | 38% | 20% | 3.3% | 1.72x | -20% |
| Liquid (> $5M/day) | 2,548 | 579 | 74% | 36% | 14% | 2.1% | 1.58x | -11% |
| BTC above 200-day average | 7,462 | 2,208 | 72% | 38% | 22% | 4.1% | 1.71x | -17% |
| BTC below 200-day average | 5,367 | 2,165 | 67% | 38% | 16% | 2.1% | 1.65x | -23% |
| Matched placebo windows | 25,624 | | 5% | 15% | 8% | 0.9% | 1.19x | |

| Sector | Events | Coins | 3x+ | 10x+ | Durable 60d | Median multiple |
|---|---:|---:|---:|---:|---:|---:|
| Privacy | 72 | 11 | 26% | 9.7% | 50% | 1.84x |
| AI | 725 | 112 | 24% | 4.8% | 41% | 1.75x |
| Layer 1 | 807 | 115 | 22% | 3.7% | 43% | 1.75x |
| Infrastructure | 550 | 75 | 21% | 4.4% | 39% | 1.72x |
| Gaming / metaverse | 881 | 168 | 21% | 3.4% | 35% | 1.69x |
| Layer 2 / scaling | 235 | 35 | 20% | 3.8% | 40% | 1.75x |
| Memecoins | 300 | 80 | 20% | 5.0% | 35% | 1.64x |
| Exchange tokens | 204 | 37 | 19% | 4.9% | 39% | 1.77x |
| RWA | 133 | 24 | 18% | 6.0% | 38% | 1.71x |
| DeFi | 1,372 | 243 | 17% | 2.4% | 39% | 1.65x |

## Exhibit C: events vs matched placebo (AUC, top 20 by |AUC-0.5| across all re-ratings)

| Measure | All re-ratings | 10x+ within 180 days | 5-10x | 3-5x | 2-3x (doublers) | Under 2x (faded pops) | Micro tape (< $250k/day) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Volatility vs own baseline, last 5 days | 0.66 | 0.70 | 0.68 | 0.67 | 0.67 | 0.66 | 0.70 |
| Largest up-day (sd), days -20..-1 | 0.62 | 0.65 | 0.64 | 0.62 | 0.62 | 0.61 | 0.63 |
| Volatility vs own baseline, 60d | 0.61 | 0.62 | 0.63 | 0.61 | 0.61 | 0.61 | 0.64 |
| Bollinger bandwidth percentile (squeeze) | 0.61 | 0.59 | 0.62 | 0.62 | 0.61 | 0.61 | 0.64 |
| Down-spikes > 2 sd, 60d | 0.60 | 0.61 | 0.61 | 0.60 | 0.60 | 0.60 | 0.63 |
| Flow toxicity (VPIN percentile, 1y) | 0.59 | 0.59 | 0.62 | 0.60 | 0.59 | 0.59 | 0.60 |
| Up-spikes > 2 sd, 60d | 0.59 | 0.61 | 0.62 | 0.59 | 0.58 | 0.58 | 0.60 |
| Max drawdown inside 60d | 0.42 | 0.45 | 0.44 | 0.42 | 0.42 | 0.42 | 0.40 |
| Flow toxicity vs baseline, last 5 days | 0.58 | 0.57 | 0.60 | 0.59 | 0.58 | 0.57 | 0.58 |
| Return vs BTC, 90d | 0.43 | 0.41 | 0.43 | 0.42 | 0.42 | 0.43 | 0.41 |
| Distance from 200-day average | 0.43 | 0.42 | 0.44 | 0.44 | 0.43 | 0.44 | 0.42 |
| Abnormal return, 60d | 0.44 | 0.44 | 0.46 | 0.44 | 0.44 | 0.44 | 0.41 |
| Illiquidity (Amihud) vs baseline | 0.56 | 0.59 | 0.56 | 0.53 | 0.56 | 0.55 | 0.55 |
| Momentum, 90d | 0.44 | 0.43 | 0.46 | 0.45 | 0.44 | 0.45 | 0.42 |
| Abnormal return, days -60..-21 | 0.44 | 0.42 | 0.46 | 0.44 | 0.44 | 0.45 | 0.45 |
| Correlation with crypto market, 60d | 0.45 | 0.46 | 0.46 | 0.45 | 0.45 | 0.44 | 0.42 |
| Drawdown from all-time high | 0.45 | 0.44 | 0.43 | 0.45 | 0.44 | 0.46 | 0.45 |
| Close vs prior 90-day high | 0.45 | 0.47 | 0.48 | 0.46 | 0.45 | 0.45 | 0.43 |
| Share of days above 20-day average, 60d | 0.46 | 0.45 | 0.48 | 0.46 | 0.46 | 0.46 | 0.46 |
| Abnormal return, days -20..-6 | 0.46 | 0.49 | 0.48 | 0.47 | 0.47 | 0.45 | 0.45 |

## Exhibit D: 3x+ multibaggers (2,356) vs faded pops (3,718)

| Measure | AUC | Multibaggers (median) | Faded (median) | q |
|---|---:|---:|---:|---:|
| Day-0 return | 0.65 | 0.35 | 0.26 | 2.8e-86 |
| Chaikin money flow, 20d | 0.58 | -0.02 | -0.08 | 1.7e-23 |
| Token age (log days) | 0.43 | 6.60 | 6.76 | 9.4e-20 |
| Trend strength (t-stat of 60d slope) | 0.57 | -3.98 | -6.63 | 1.5e-18 |
| Day-0 abnormal return (sd) | 0.56 | 4.72 | 4.26 | 2.7e-15 |
| Days since all-time high (log) | 0.44 | 6.43 | 6.43 | 6.0e-14 |
| Share of days above 20-day average, 60d | 0.56 | 0.37 | 0.32 | 3.1e-13 |
| Distance from 50-day average | 0.56 | -0.03 | -0.10 | 7.9e-13 |
| Momentum, 30d | 0.56 | -0.03 | -0.11 | 2.9e-12 |
| Correlation with crypto market, 60d | 0.45 | 0.44 | 0.50 | 9.7e-11 |
| New 60-day highs, last 20 days | 0.55 | 0.00 | 0.00 | 4.2e-17 |
| Baseline dollar volume (log) | 0.45 | 12.67 | 13.02 | 2.4e-10 |
| Close location in 20-day range | 0.55 | 0.44 | 0.35 | 8.3e-10 |
| Toxic trend (days above 20d avg on toxic buy flow), 60d | 0.54 | 0.02 | 0.02 | 2.7e-08 |

## Exhibit F: pre-re-rating archetypes (GMM on the pre-event tape of 3x+ multibaggers)

k = 10 (BIC), mean adjusted Rand index across seeds 0.82, base conversion of all triggers to 3x 19%.

| Archetype | Multibaggers | Lift vs placebo | Placebo share | Conversion of triggers | Median multiple | 10x+ share |
|---|---:|---:|---:|---:|---:|---:|
| Lottery spikes / promotion + Washed out (deep drawdown from the high) + Liquidity drying up | 180 | 3.7x | 2.0% | 18% | 4.72x | 12% |
| Capitulation + Heavy volume on a falling base + Lottery spikes / promotion | 189 | 2.0x | 3.9% | 19% | 4.71x | 18% |
| Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | 287 | 1.9x | 6.3% | 27% | 4.99x | 17% |
| Toxic breakout + Trend continuation + Liquidity drying up | 94 | 1.6x | 2.5% | 23% | 5.48x | 26% |
| Informed drift (price and volume run-up, buying pressure) + Stealth accumulation (volume without price) + Lottery spikes / promotion | 342 | 1.1x | 12.6% | 19% | 4.79x | 14% |
| Lottery spikes / promotion + Liquidity drying up | 250 | 1.0x | 10.6% | 17% | 4.85x | 16% |
| Washed out (deep drawdown from the high) + Liquidity drying up | 222 | 0.9x | 10.3% | 18% | 4.79x | 18% |
| Lottery spikes / promotion | 301 | 0.9x | 14.2% | 21% | 5.03x | 20% |
| Heavy volume on a falling base + Stealth accumulation (volume without price) + Liquidity improving | 239 | 0.8x | 13.1% | 19% | 4.64x | 17% |
| Ordinary tape (information not in the tape) | 252 | 0.5x | 22.0% | 17% | 4.62x | 17% |

Out of time (fitted on 2017-21 multibaggers, applied to 2022+ triggers):

| Archetype (2017-21 fit) | Conversion 2017-21 | 2022+ triggers | Conversion 2022+ | Base 2022+ |
|---|---:|---:|---:|---:|
| Toxic breakout + Trend continuation | 35% | 540 | 22% | 15% |
| Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Stealth accumulation (volume without price) | 41% | 446 | 19% | 15% |
| Lottery spikes / promotion | 35% | 1,080 | 16% | 15% |
| Informed drift (price and volume run-up, buying pressure) + Lottery spikes / promotion + Trend continuation | 35% | 291 | 15% | 15% |
| Lottery spikes / promotion + Washed out (deep drawdown from the high) + Liquidity drying up | 37% | 1,003 | 15% | 15% |
| Lottery spikes / promotion | 30% | 1,169 | 14% | 15% |
| Capitulation + Stealth accumulation (volume without price) + Lottery spikes / promotion | 33% | 445 | 14% | 15% |
| Liquidity drying up | 30% | 2,119 | 14% | 15% |
| Heavy volume on a falling base + Stealth accumulation (volume without price) + Liquidity improving | 34% | 922 | 13% | 15% |
| Lottery spikes / promotion + Liquidity drying up | 28% | 841 | 13% | 15% |

## Exhibit G: what works best

Unconditional screen: every eligible coin every 14 days (203,130 coin-dates), label 3x within 180 days (base 10.7% over 2017-26). Direction fixed on 2017-21, scored on 2022+.

| Signal | Direction | AUC 2022+ | Top-decile 3x rate 2022+ | Base | Lift 2022+ | Lift 2017-21 |
|---|---|---:|---:|---:|---:|---:|
| Gradient-boosted screen (within-date ranks) | high | 0.54 | 8.7% | 7.3% | 1.19x | 1.63x |
| Gradient-boosted screen (feature levels) | high | 0.53 | 7.9% | 7.3% | 1.09x | 1.60x |
| Logistic screen (within-date ranks) | high | 0.51 | 7.7% | 7.3% | 1.05x | 1.02x |
| Max drawdown inside 60d | low | 0.57 | 10.2% | 7.3% | 1.41x | 1.16x |
| Distance from 50-day average | low | 0.53 | 9.7% | 7.3% | 1.34x | 1.11x |
| Distance from 200-day average | low | 0.55 | 9.7% | 7.3% | 1.34x | 1.15x |
| Close vs prior 90-day high | low | 0.56 | 9.7% | 7.3% | 1.33x | 1.13x |
| Return vs BTC, 90d | low | 0.54 | 9.7% | 7.3% | 1.33x | 1.16x |
| Momentum, 90d | low | 0.54 | 9.7% | 7.3% | 1.33x | 1.16x |
| Drawdown from all-time high | low | 0.56 | 9.6% | 7.3% | 1.32x | 1.00x |
| Momentum, 30d | low | 0.52 | 9.5% | 7.3% | 1.30x | 1.10x |
| Abnormal return, 60d | low | 0.52 | 9.3% | 7.3% | 1.27x | 1.14x |
| Abnormal return, last 5 days | low | 0.51 | 9.2% | 7.3% | 1.27x | 1.11x |
| Abnormal return, days -20..-6 | low | 0.51 | 8.9% | 7.3% | 1.22x | 1.12x |
| Abnormal return, days -60..-21 | low | 0.52 | 8.8% | 7.3% | 1.22x | 1.11x |
| Toxic momentum (return on toxic days), 60d | low | 0.51 | 8.7% | 7.3% | 1.20x | 1.10x |
| Peak abnormal volume, 60d | low | 0.51 | 8.1% | 7.3% | 1.11x | 1.10x |
| Illiquidity (Amihud) vs baseline | high | 0.50 | 8.0% | 7.3% | 1.10x | 1.09x |

Toxic overlays vs plain signals (same screen, 2022+):

| Signal | Plain AUC | Toxic AUC | Plain lift | Toxic lift |
|---|---:|---:|---:|---:|
| Breakout | 0.51 | 0.50 | 0.98x | 0.98x |
| Momentum 20-30d | 0.52 | 0.50 | 1.30x | 0.96x |
| Momentum 60d | 0.52 | 0.51 | 1.27x | 1.20x |
| Trend | 0.52 | 0.50 | 1.07x | 0.97x |
| OBV 60d | 0.52 | 0.51 | 1.06x | 0.99x |
| OBV 20d | 0.51 | 0.50 | 1.03x | 0.88x |
| Accumulation | 0.50 | 0.51 | 1.06x | 1.01x |
| Squeeze | 0.50 | 0.49 | 1.04x | 0.92x |

Best one-, two- and three-signal screens (top quintile on each; chosen on 2017-21):

| Screen | Lift 2017-21 | Coin-dates 2022+ | 3x rate 2022+ | Lift 2022+ |
|---|---:|---:|---:|---:|
| Close vs prior 90-day high | 1.14x | 31,162 | 9.1% | 1.24x |
| Momentum, 90d | 1.14x | 31,017 | 9.1% | 1.24x |
| Return vs BTC, 90d | 1.14x | 31,017 | 9.1% | 1.24x |
| Max drawdown inside 60d | 1.13x | 31,162 | 9.4% | 1.29x |
| Distance from 200-day average | 1.10x | 30,478 | 9.3% | 1.27x |
| Abnormal return, 60d | 1.10x | 31,034 | 8.9% | 1.22x |
| Abnormal return, days -20..-6 | 1.08x | 30,973 | 8.4% | 1.16x |
| Abnormal return, days -60..-21 | 1.08x | 30,942 | 8.6% | 1.18x |
| Max drawdown inside 60d + Peak abnormal volume, 60d | 1.24x | 7,553 | 10.8% | 1.48x |
| Abnormal return, days -20..-6 + Peak abnormal volume, 60d | 1.23x | 7,192 | 9.6% | 1.32x |
| Distance from 50-day average + Peak abnormal volume, 60d | 1.22x | 7,801 | 10.3% | 1.42x |
| Return vs BTC, 90d + Max drawdown inside 60d | 1.22x | 17,370 | 10.1% | 1.38x |
| Momentum, 90d + Max drawdown inside 60d | 1.22x | 17,370 | 10.1% | 1.38x |
| Close vs prior 90-day high + Peak abnormal volume, 60d | 1.21x | 9,271 | 9.8% | 1.35x |
| Momentum, 90d + Abnormal return, days -20..-6 | 1.21x | 12,828 | 9.9% | 1.36x |
| Return vs BTC, 90d + Abnormal return, days -20..-6 | 1.21x | 12,828 | 9.9% | 1.36x |
| Abnormal return, days -20..-6 + Abnormal return, last 5 days + Peak abnormal volume, 60d | 1.43x | 1,967 | 11.1% | 1.53x |
| Abnormal return, days -20..-6 + Distance from 50-day average + Peak abnormal volume, 60d | 1.33x | 4,389 | 10.5% | 1.44x |
| Abnormal return, days -20..-6 + Abnormal return, last 5 days + Illiquidity (Amihud) vs baseline | 1.33x | 2,437 | 11.0% | 1.50x |
| Abnormal return, days -20..-6 + Momentum, 30d + Peak abnormal volume, 60d | 1.31x | 4,209 | 10.5% | 1.44x |
| Distance from 50-day average + Abnormal return, last 5 days + Peak abnormal volume, 60d | 1.29x | 3,532 | 10.6% | 1.46x |
| Momentum, 30d + Peak abnormal volume, 60d + Illiquidity (Amihud) vs baseline | 1.29x | 4,176 | 10.7% | 1.47x |
| Max drawdown inside 60d + Abnormal return, days -20..-6 + Peak abnormal volume, 60d | 1.29x | 3,519 | 11.3% | 1.56x |
| Distance from 50-day average + Peak abnormal volume, 60d + Illiquidity (Amihud) vs baseline | 1.29x | 4,302 | 10.9% | 1.50x |

Once a coin pops (triggers only; direction from 2017-21, top fifth of 2022+ triggers):

| Measure | Direction | AUC 2022+ | 3x rate, top fifth | Base | Lift |
|---|---|---:|---:|---:|---:|
| Day-0 return | high | 0.59 | 22.8% | 14.9% | 1.53x |
| New 60-day highs, last 20 days | high | 0.53 | 18.7% | 14.9% | 1.26x |
| Max drawdown inside 60d | high | 0.53 | 18.6% | 14.9% | 1.25x |
| Day-0 abnormal return (sd) | high | 0.55 | 18.3% | 14.9% | 1.23x |
| Momentum, 30d | high | 0.53 | 18.2% | 14.9% | 1.22x |
| Distance from 50-day average | high | 0.54 | 17.9% | 14.9% | 1.20x |
| Correlation with crypto market, 60d | low | 0.58 | 17.8% | 14.9% | 1.20x |
| Baseline dollar volume (log) | low | 0.56 | 17.7% | 14.9% | 1.19x |
| Close location in 20-day range | high | 0.53 | 17.6% | 14.9% | 1.18x |
| Close vs prior 90-day high | high | 0.52 | 17.6% | 14.9% | 1.18x |
| Toxic momentum (return on toxic days), 60d | high | 0.53 | 17.5% | 14.9% | 1.18x |
| Abnormal return, last 5 days | high | 0.52 | 17.4% | 14.9% | 1.17x |
| Toxic momentum (return on toxic days), 20d | high | 0.53 | 17.4% | 14.9% | 1.17x |
| Trend strength (t-stat of 60d slope) | high | 0.53 | 17.3% | 14.9% | 1.16x |
| Toxic trend (days above 20d avg on toxic buy flow), 60d | high | 0.52 | 17.1% | 14.9% | 1.15x |

Classifiers:

| Sample | Model | Split | AUC | Caught at 10% FPR | n |
|---|---|---|---:|---:|---:|
| Re-rating (any) vs placebo, pre-event tape | gbm | symbol-grouped 5-fold | 0.73 | 37% | 38,453 |
| Re-rating (any) vs placebo, pre-event tape | gbm | train 2017-21, test 2022+ | 0.70 | 33% | 29,239 |
| Re-rating (any) vs placebo, pre-event tape | logit | symbol-grouped 5-fold | 0.71 | 34% | 38,453 |
| Re-rating (any) vs placebo, pre-event tape | logit | train 2017-21, test 2022+ | 0.71 | 34% | 29,239 |
| Multibagger (3x+) vs placebo, pre-event tape | gbm | symbol-grouped 5-fold | 0.77 | 44% | 26,616 |
| Multibagger (3x+) vs placebo, pre-event tape | gbm | train 2017-21, test 2022+ | 0.71 | 33% | 19,474 |
| Multibagger (3x+) vs placebo, pre-event tape | logit | symbol-grouped 5-fold | 0.74 | 37% | 26,616 |
| Multibagger (3x+) vs placebo, pre-event tape | logit | train 2017-21, test 2022+ | 0.71 | 34% | 19,474 |
| Multibagger vs faded pop, pre-event + day 0 | gbm | symbol-grouped 5-fold | 0.76 | 44% | 6,074 |
| Multibagger vs faded pop, pre-event + day 0 | gbm | train 2017-21, test 2022+ | 0.64 | 22% | 4,376 |
| Multibagger vs faded pop, pre-event + day 0 | logit | symbol-grouped 5-fold | 0.70 | 34% | 6,074 |
| Multibagger vs faded pop, pre-event + day 0 | logit | train 2017-21, test 2022+ | 0.61 | 21% | 4,376 |

## Exhibit P: price-action schools (Schabacker, Japanese, Dalton)

Qualitative confirmation works the way the old books describe, but only on top of a breakout. A plain 55-day breakout lost 12% a year from 2022; requiring a strong close without bearish candles and all four Ichimoku lines bullish made 19% a year with a 36% worst drawdown, and the same filters also improved 2017-21 (98% a year vs 93%). Reversal-style entries (Heikin-Ashi, Renko and three-line-break turns, trendline and head-and-shoulders breaks) lost heavily after 2021. Once a coin pops, Dalton's value migration and acceptance, a wide pop-day range and Ichimoku alignment raised the 3x odds by 1.2-1.3x in both periods.

Rulebook that held up in both periods: enter on a close at a new 55-day high when that day closes strong (white marubozu or top quarter of its range), no bearish candle pattern printed in the prior five days and all four Ichimoku lines agree; exit on a close below the highest close since entry minus 3 ATR (or below Kijun-sen); 1% of equity per trade, one position per coin.

Books: 1% of equity per entry, no rebalancing, 3 ATR chandelier exit, 0.25% cost per side (0.5% below $1M/day).

| Entry rule | Trades 2022+ | Return/yr 2017-21 | Sharpe 2017-21 | Return/yr 2022+ | Sharpe 2022+ | Max DD 2022+ | Profit factor 2022+ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 55-day breakout + strong candle, no bearish patterns + Ichimoku all bullish | 3,383 | 98% | 1.72 | 19% | 0.67 | -36% | 1.36 |
| 55-day breakout + strong candle, no bearish patterns | 4,197 | 103% | 1.72 | 15% | 0.58 | -41% | 1.31 |
| 55-day breakout + Ichimoku + value migration + volume | 5,476 | 86% | 1.49 | 15% | 0.55 | -60% | 1.36 |
| Re-rating trigger, top-quintile follow-through score | 770 | 39% | 1.33 | 11% | 0.54 | -29% | 1.43 |
| Schabacker: flag breakout | 550 | 26% | 1.10 | 6% | 0.42 | -23% | 1.33 |
| 55-day breakout + Ichimoku all bullish | 7,021 | 94% | 1.59 | 5% | 0.32 | -57% | 1.39 |
| Schabacker: six-month resistance break | 3,254 | 62% | 1.32 | 3% | 0.25 | -45% | 1.15 |
| 55-day breakout + Schabacker pattern in the last 10 days | 7,957 | 85% | 1.51 | -3% | 0.15 | -65% | 1.31 |
| Schabacker: triangle breakout | 748 | 41% | 1.67 | 1% | 0.14 | -29% | 1.08 |
| 55-day breakout + volume 1.5x median | 6,892 | 96% | 1.54 | -4% | 0.12 | -71% | 1.28 |
| Schabacker: rectangle breakout on volume | 4,196 | 79% | 1.62 | -7% | 0.01 | -68% | 1.06 |
| 55-day breakout + value migrating higher | 7,827 | 97% | 1.61 | -9% | 0.00 | -63% | 1.31 |
| Dalton: value moves higher with acceptance | 11,728 | 122% | 1.67 | -13% | -0.03 | -73% | 1.21 |
| 55-day breakout (Donchian) | 8,412 | 93% | 1.56 | -12% | -0.07 | -66% | 1.30 |
| Schabacker: double-bottom breakout | 4,713 | 97% | 1.79 | -10% | -0.10 | -72% | 1.25 |
| Schabacker: inverse head-and-shoulders breakout | 1,656 | 45% | 1.33 | -6% | -0.12 | -59% | 0.82 |
| Ichimoku: TK cross above the cloud | 4,833 | 66% | 1.36 | -14% | -0.24 | -68% | 1.08 |
| Dalton: breakout from balance on volume | 1,476 | 35% | 1.11 | -11% | -0.37 | -50% | 0.70 |
| Ichimoku: cloud breakout with all signals bullish | 5,829 | 71% | 1.39 | -20% | -0.38 | -75% | 1.08 |
| Schabacker: falling-wedge breakout | 2,476 | 43% | 1.42 | -17% | -0.53 | -74% | 0.94 |
| Three-line break turns white | 19,223 | 30% | 0.74 | -50% | -1.04 | -97% | 0.83 |
| Schabacker: any breakout | 22,431 | 79% | 1.25 | -50% | -1.15 | -97% | 0.91 |
| Heikin-Ashi turns bullish | 36,529 | 50% | 0.93 | -51% | -1.18 | -98% | 0.76 |
| Re-rating trigger (study day 0) | 4,662 | 43% | 0.98 | -47% | -1.21 | -96% | 0.68 |
| Schabacker: downtrend-line break | 20,832 | 75% | 1.23 | -53% | -1.34 | -98% | 0.90 |
| Renko turns up | 14,681 | 32% | 0.75 | -67% | -1.69 | -100% | 0.80 |

Once a coin pops (triggers only; base 3x rate 14.9% in 2022+), factors that lifted the rate in both periods:

| Factor | School | Triggers with it 2022+ | 3x rate with | without | Lift 2017-21 | Lift 2022+ |
|---|---|---:|---:|---:|---:|---:|
| Pop-day range vs 20-day average range | Dalton | 1,796 | 19.9% | 13.6% | 1.23x | 1.34x |
| Three white soldiers | Japanese | 525 | 19.2% | 14.6% | 1.09x | 1.29x |
| Higher, non-overlapping value | Dalton | 1,152 | 19.2% | 14.3% | 1.18x | 1.29x |
| Ichimoku: sanyaku kouten (all bullish) | Japanese | 1,486 | 18.8% | 14.1% | 1.16x | 1.26x |
| Falling-wedge breakout | Schabacker | 183 | 18.0% | 14.8% | 1.13x | 1.21x |
| Pop day breaks six-month resistance | Schabacker | 850 | 17.9% | 14.6% | 1.22x | 1.20x |
| Value migration: 5-day POC vs prior value | Dalton | 1,781 | 17.9% | 14.1% | 1.25x | 1.20x |
| Close vs 20-day value (0 = POC, +/-0.5 = VA edge) | Dalton | 1,785 | 17.8% | 14.2% | 1.20x | 1.20x |
| Ichimoku: future cloud bullish | Japanese | 2,482 | 17.6% | 13.8% | 1.09x | 1.19x |
| Renko turned up | Japanese | 1,712 | 17.6% | 14.2% | 1.16x | 1.18x |
| Acceptance: closes above prior value high, 5 days | Dalton | 2,042 | 17.5% | 14.1% | 1.20x | 1.17x |
| Ichimoku: distance above Kijun (ATR) | Japanese | 1,780 | 17.5% | 14.2% | 1.19x | 1.17x |
| Pop day closes with all Ichimoku signals bullish | Japanese | 2,862 | 17.4% | 13.7% | 1.14x | 1.17x |
| Up trend days, last 20 | Dalton | 2,736 | 17.4% | 13.8% | 1.05x | 1.17x |

As standalone screens (3x hits vs the same-day base rate) the best 2022+ factor reached 1.17x (Renko turned up); most factors flipped between periods.

Live (2026-09-30): 218 of 544 tradeable coins made a 55-day breakout in the last five days; the full rule fired on 28: SHX, CHEX, QNT, MNT, DIA, QUBIC, PAAL, ALPH, HBAR, JST, ORCA, CRO, KSM, AHT, BZZ, LINK, ONDO, ALGO, GRASS, RUNE, KAS, TRB, KAIA, CLOUD, FUN, HOT, DSYNC, CAKE.

Dalton's market profile is built from intraday time-price data; here it is adapted to daily bars (value area from a 20-day volume-weighted price distribution). Windows (gaps) barely exist in a 24/7 market, so gap patterns drop out.

## Exhibit O: on-chain layer (coverage-limited; indicative)

| Measure | Events covered | All re-ratings | 10x+ within 180 days | 5-10x | 3-5x | Under 2x (faded pops) |
|---|---:|---:|---:|---:|---:|---:|
| Active addresses, 30d vs prior 30d (days -90..-61) | 760 | 0.52 | 0.55 | 0.46 | 0.54 | 0.52 |
| Active addresses, last 7 days vs baseline | 749 | 0.54 | 0.49 | 0.46 | 0.58 | 0.55 |
| Activity growth minus price change, 30d | 758 | 0.51 | 0.61 | 0.50 | 0.52 | 0.52 |
| Fees, 30d vs prior 30d | 621 | 0.52 | – | 0.60 | 0.47 | 0.52 |
| Holder growth, 60d | 780 | 0.50 | 0.67 | 0.50 | 0.52 | 0.48 |
| Holder growth, 60d vs prior 60d | 780 | 0.53 | 0.63 | 0.49 | 0.52 | 0.53 |
| MVRV (market / realised value, log) | 762 | 0.46 | 0.40 | 0.54 | 0.49 | 0.44 |
| Market cap (log, CoinMetrics estimate) | 3,358 | 0.45 | 0.37 | 0.44 | 0.46 | 0.46 |
| Supply growth, 1y (dilution) | 775 | 0.50 | 0.56 | 0.43 | 0.50 | 0.51 |
| Supply growth, 60d | 814 | 0.50 | 0.55 | 0.46 | 0.49 | 0.51 |
| TVL / market cap (log) | 648 | 0.50 | 0.43 | 0.32 | 0.57 | 0.51 |
| TVL growth minus price change, 60d | 1,561 | 0.53 | 0.57 | 0.53 | 0.53 | 0.53 |
| TVL growth, 60d | 1,562 | 0.48 | 0.44 | 0.51 | 0.45 | 0.49 |
| Transactions, last 7 days vs baseline | 768 | 0.55 | 0.53 | 0.51 | 0.63 | 0.56 |
| Transfers, last 7 days vs baseline | 767 | 0.55 | 0.53 | 0.54 | 0.62 | 0.56 |

## Exhibit H: validation cases

| Case | Date | Trigger | Day-0 return | Best multiple 180d | Return 60d | Pre-event score pct |
|---|---|---|---:|---:|---:|---:|
| XRP: SEC sues Ripple Labs (S.D.N.Y.) | 2020-12-22 | no | -13.2% | 3.42x | +0% | 92% |
| XRP: SEC v. Ripple: programmatic sales not securities (S.D.N.Y.) | 2023-07-13 | yes | 73.6% | 1.65x | +1% | 43% |
| XRP: Post-election re-rating; SEC leadership change expected | 2024-11-12 | yes | 13.5% | 5.22x | +314% | 78% |
| TORN: OFAC sanctions Tornado Cash | 2022-08-08 | no | -26.6% | 0.93x | -79% | 94% |
| TORN: Van Loon v. Treasury (5th Cir.): Tornado sanctions unlawful | 2024-11-26 | yes | 301.1% | 5.25x | +372% | 91% |
| BTC: Grayscale v. SEC (D.C. Cir.): ETF denial vacated | 2023-08-29 | no | 6.2% | 2.00x | +31% | 34% |
| BTC: Spot bitcoin ETFs approved | 2024-01-10 | no | 1.2% | 1.55x | +50% | 97% |
| ETH: SEC signals spot ether ETF approval | 2024-05-20 | yes | 19.2% | 1.25x | +14% | 69% |
| BNB: SEC sues Binance | 2023-06-05 | no | -9.3% | 1.00x | -21% | 45% |
| FTT: FTX liquidity crisis / Binance walks away | 2022-11-08 | no | – | –x | – | 35% |
| LUNC: UST de-peg | 2022-05-09 | no | – | –x | – | 69% |
| DOGE: WallStreetBets / Musk tweets | 2021-01-28 | no | 355.5% | 85.06x | +622% | 52% |
| MANA: Facebook renames itself Meta | 2021-10-28 | yes | 22.5% | 6.81x | +396% | 72% |
| SAND: Facebook renames itself Meta | 2021-10-29 | yes | 22.9% | 7.43x | +525% | 76% |
| SHIB: October 2021 SHIB mania | 2021-10-04 | yes | 57.6% | 8.08x | +373% | 100% |
| AXS: Axie play-to-earn boom | 2021-07-06 | no | 35.7% | 19.00x | +922% | 98% |
| PEPE: Binance lists PEPE | 2023-05-05 | no | – | 1.34x | -13% | 16% |
| BONK: Binance lists BONK | 2023-12-14 | no | 81.6% | 2.79x | +1% | 79% |
| WIF: Binance lists WIF | 2024-03-05 | no | – | 2.87x | +128% | 16% |
| HBAR: BlackRock fund-tokenisation headline (misread) | 2024-04-23 | yes | 73.6% | 1.32x | -14% | 39% |
| LINK: Coinbase Pro lists LINK | 2019-06-27 | no | 0.6% | 1.57x | -10% | 99% |
| OM: MANTRA collapse | 2025-04-13 | no | – | –x | – | 16% |

## Exhibit L: live scan (2026-09-28, top 25 of 536 tradeable coins)

| Coin | Blend | Event-model pct | Screen pct | Archetype | $ volume 7d |
|---|---:|---:|---:|---|---:|
| ETN (Electroneum) | 0.97 | 99.9% | 95% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $0.3m |
| RONIN (Ronin) | 0.97 | 99.8% | 96% | Toxic breakout + Trend continuation + Liquidity drying up | $2.4m |
| SKY (Sky) | 0.95 | 98.6% | 99% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $33.4m |
| SAFE (SafeCoin) | 0.94 | 98.7% | 96% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $0.1m |
| ICX (ICON) | 0.94 | 99.7% | 92% | Capitulation + Heavy volume on a falling base + Lottery spikes / promotion | $2.6m |
| BRETT (Brett) | 0.93 | 97.4% | 100% | Toxic breakout + Trend continuation + Liquidity drying up | $5.2m |
| SYN (SynLev) | 0.90 | 96.6% | 95% | Capitulation + Heavy volume on a falling base + Lottery spikes / promotion | $22.8m |
| HIGH (Highstreet) | 0.90 | 99.7% | 83% | Informed drift (price and volume run-up, buying pressure) + Stealth accumulation (volume without price) + Lottery spikes / promotion | $16.5m |
| PAAL (PAAL AI) | 0.88 | 100.0% | 77% | Toxic breakout + Trend continuation + Liquidity drying up | $0.7m |
| SBD (Steem Dollars) | 0.88 | 97.1% | 90% | Toxic breakout + Trend continuation + Liquidity drying up | $0.7m |
| BSV (Bitcoin SV) | 0.87 | 93.5% | 96% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $33.4m |
| AVA (AVA) | 0.86 | 96.6% | 88% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $14.6m |
| TAIKO (Taiko) | 0.86 | 96.9% | 86% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $8.2m |
| CVC (Civic) | 0.86 | 97.5% | 84% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $15.5m |
| ADP (Adappter Token) | 0.85 | 92.8% | 94% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $0.7m |
| MPLX (Metaplex) | 0.84 | 99.1% | 75% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $11.3m |
| FIRO (Firo) | 0.84 | 97.8% | 81% | Toxic breakout + Trend continuation + Liquidity drying up | $0.2m |
| TOMO (TomoChain) | 0.84 | 99.3% | 73% | Lottery spikes / promotion + Washed out (deep drawdown from the high) + Liquidity drying up | $0.1m |
| BONK (Bonk) | 0.83 | 98.2% | 77% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $101.5m |
| AIXBT (aixbt) | 0.83 | 97.8% | 78% | Toxic breakout + Trend continuation + Liquidity drying up | $6.5m |
| ERG (Ergo) | 0.83 | 88.2% | 100% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $0.2m |
| DSYNC (Destra Network) | 0.83 | 99.8% | 68% | Toxic breakout + Trend continuation + Liquidity drying up | $1.2m |
| ABT (Arcblock) | 0.82 | 99.5% | 69% | Toxic breakout + Informed drift (price and volume run-up, buying pressure) + Trend continuation | $0.7m |
| RSS3 (RSS3) | 0.82 | 100.0% | 64% | Lottery spikes / promotion + Washed out (deep drawdown from the high) + Liquidity drying up | $1.1m |
| QAI (QuantixAI) | 0.81 | 98.4% | 72% | Ordinary tape (information not in the tape) | $1.2m |

## Using it

- **Watch.** Screen for washed-out coins whose volatility is waking up: a deep 60-day drawdown, below the 50- and 200-day averages, final-week volatility above the coin's own baseline and a high VPIN percentile. Volume does not have to lead; quiet tapes produce the biggest runs.
- **Confirm.** Act on the pop, not before it. A big day-0 move (in sigmas and in percent), new 60-day highs in the prior three weeks, positive toxic momentum and a toxic-breakout archetype are what separated multibaggers from faded pops out of time.
- **Avoid.** Pops out of steep downtrends with persistent selling (negative money flow), coins that move with the market, and busy, already-promoted tapes: heavy prior volume and volume build-ups precede faded pops more than 10x runs.

## Data and caveats

- Data: Financial Modeling Prep (universe of 4,762 crypto USD pairs and daily bars), CoinMetrics community API (network activity, holders, supply, MVRV, market cap), DefiLlama (TVL, fees), CoinGecko categories (sectors). As of 2026-09-28.
- Code and full outputs: crypto_multibaggers/ and data/crypto_multibaggers/ (REPORT.md, analysis/*.csv, events_master.csv.gz).
- Etherscan: a V2 client for ERC-20 transfer data (onchain.Etherscan, transfer_activity: daily transfers, unique senders and receivers, first-time receivers) is included but was not run, because Etherscan refuses keyless requests. With ETHERSCAN_API_KEY in the environment, the next step is to pull transfers for the ERC-20 event windows. The toxic breakout, momentum, trend and OBV overlays are defined here from their names (VPIN above the coin's baseline 80th percentile, with buy-side BVC imbalance); the attribution engine's own definitions were not available to this session.
- Coins younger than 121 days cannot have a baseline, so launch-week memecoin runs are out of scope. Aggregated crypto bars carry placeholder, ticker-reuse and bad-print artefacts; the cleaning rules drop those windows, which also removes some genuine crash days. Research only, not investment advice.

Method details: see crypto_multibaggers/README.md.
