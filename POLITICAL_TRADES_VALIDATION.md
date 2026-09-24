# Congressional trades -- event study

Generated 2026-09-24 by `political_trades.py`. 21496 equity PTR trades (Senate + House) in 1888 listed names disclosed since 2022-01-01; 18757 with a full 126-trading-day forward window.

Return = excess vs SPY over 126 trading days from the first close AFTER the disclosure date (when the trade becomes public). `shrunk` = mean x n/(n+60), the weight used for scoring. Market-cap buckets use today's cap (a survivorship caveat).

## direction, from TRANSACTION date (member's own timing, not tradeable)

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| buy | 9022 | -1.9% | -3.6% | 42% | -1.89% |
| sell | 10293 | -1.5% | -3.7% | 42% | -1.46% |

## direction

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| buy | 8743 | -1.9% | -3.5% | 43% | -1.88% |
| sell | 10014 | -1.3% | -3.8% | 42% | -1.34% |

## buy size band

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| 15-50k | 1417 | -1.7% | -3.0% | 43% | -1.60% |
| 50-250k | 571 | +0.1% | -0.7% | 50% | +0.09% |
| <15k | 6685 | -2.1% | -3.6% | 42% | -2.07% |
| >250k | 70 | -3.5% | -3.9% | 46% | -1.88% |

## buy market cap (at disclosure)

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| ? | 4 | +52.2% | +64.0% | 100% | +3.26% |
| large | 7477 | -1.5% | -3.3% | 43% | -1.52% |
| micro<300m | 31 | -34.1% | -21.8% | 26% | -11.61% |
| mid<10b | 1010 | -4.4% | -4.5% | 41% | -4.15% |
| small<2b | 221 | +1.1% | -4.2% | 42% | +0.90% |

## buy owner

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| Dependent | 147 | -4.6% | -5.4% | 37% | -3.25% |
| Joint | 1377 | -1.0% | -2.0% | 46% | -0.97% |
| Self | 4480 | -2.2% | -3.8% | 42% | -2.15% |
| Spouse | 2739 | -1.7% | -3.5% | 43% | -1.68% |

## buy asset

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| option | 101 | -0.2% | -1.7% | 45% | -0.15% |
| stock | 8642 | -1.9% | -3.5% | 43% | -1.90% |

## buy clustered

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| cluster>=2 members | 4300 | -0.5% | -2.4% | 45% | -0.48% |
| single member | 4443 | -3.2% | -4.4% | 41% | -3.20% |

## buy disclosure lag

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| 16-45d | 5842 | -2.4% | -4.1% | 42% | -2.33% |
| <=15d | 1679 | -1.4% | -3.0% | 44% | -1.39% |
| >45d (late) | 1222 | -0.3% | -1.1% | 48% | -0.27% |

## buy member track record (OOS)

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| no record | 4227 | -1.1% | -3.0% | 44% | -1.05% |
| skilled (>+2%) | 1056 | -2.8% | -4.6% | 41% | -2.64% |
| unskilled | 3460 | -2.6% | -3.8% | 42% | -2.58% |

## sell size band

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| 15-50k | 1834 | -1.6% | -3.4% | 43% | -1.54% |
| 50-250k | 842 | -2.0% | -3.2% | 44% | -1.84% |
| <15k | 7230 | -1.2% | -4.1% | 42% | -1.17% |
| >250k | 108 | -3.9% | -0.6% | 49% | -2.50% |

## sell market cap

| slice | n | mean | median | hit rate | shrunk |
|---|---|---|---|---|---|
| ? | 10 | -9.7% | -15.8% | 20% | -1.39% |
| large | 8368 | -1.1% | -3.5% | 43% | -1.05% |
| micro<300m | 35 | -23.2% | -33.4% | 20% | -8.54% |
| mid<10b | 1315 | -3.8% | -6.6% | 37% | -3.60% |
| small<2b | 286 | +4.1% | -1.4% | 48% | +3.38% |

## Top current names (last 180 days of disclosures)

| ticker | score | buys | sells | buying members | last |
|---|---|---|---|---|---|
| TKNO | +103.8 | 1 | 29 | Richard Blumenthal | 2026-09-01 |
| PHR | +8.9 | 0 | 3 |  | 2026-09-11 |
| FMC | +2.7 | 0 | 1 |  | 2026-07-20 |
| TCNNF | +2.7 | 0 | 2 |  | 2026-06-29 |
| CBZ | +2.7 | 1 | 2 | Josh S. Gottheimer | 2026-07-03 |
| HURN | +2.2 | 1 | 1 | Michael T. McCaul | 2026-07-13 |
| EFC | +1.3 | 1 | 1 | Virginia Ann Foxx | 2026-07-13 |
| WTSHF | +1.2 | 0 | 1 |  | 2026-05-19 |
| FIP | +1.2 | 0 | 1 |  | 2026-05-19 |
| CODI | +1.2 | 0 | 1 |  | 2026-05-19 |
| CTS | +0.9 | 0 | 1 |  | 2026-05-11 |
| LZB | +0.9 | 0 | 1 |  | 2026-04-09 |
| SNDA | +0.9 | 0 | 1 |  | 2026-04-16 |
| CBRL | +0.8 | 0 | 1 |  | 2026-04-29 |
| PRGS | +0.7 | 0 | 1 |  | 2026-04-06 |
| LGIH | +0.7 | 0 | 1 |  | 2026-04-29 |
| RDSMY | +0.5 | 1 | 0 | Alan Armstrong | 2026-07-21 |
| SMA | +0.5 | 0 | 1 |  | 2026-04-06 |
| LYV | +0.4 | 0 | 8 |  | 2026-09-10 |
| AER | +0.4 | 0 | 5 |  | 2026-07-13 |
| HWM | +0.4 | 0 | 2 |  | 2026-09-16 |
| FWRG | +0.3 | 1 | 1 | Josh S. Gottheimer | 2026-05-20 |
| INTA | +0.3 | 1 | 1 | Josh S. Gottheimer | 2026-05-20 |
| WWD | +0.3 | 0 | 6 |  | 2026-07-13 |
| PRU | +0.3 | 0 | 3 |  | 2026-08-10 |
