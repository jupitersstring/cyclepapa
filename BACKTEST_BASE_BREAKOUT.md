# Base-breakout event study — 'goes nowhere for 2 years, then triples in 3 months'

_All sections below exclude drug developers (483 biotech / pharma symbols, 13,870 base-months), analysed separately in section 7._

## 1. Premise: how often does an explosion come out of a flat base?

- 2x in 13w, strict base: 1,287 of 42,291 liquid event month-ends (3.0%)
- 2x in 13w, loose base (|r104|<=35%, range<=2.5x): 3,712 of 42,291 liquid event month-ends (8.8%)
- 3x in 13w, strict base: 192 of 9,829 liquid event month-ends (2.0%)
- liquid month-ends overall: 3,218,862

## 2. Base rates within flat bases

- base-months: 323,320; symbols: 9,607; 2011-12 to 2026-06
- ev2x_13w: rate 0.1859%; event month-ends 1,172; distinct episodes 754; symbols 733
- ev3x_13w: rate 0.0268%; event month-ends 169; distinct episodes 111; symbols 110
- ev2x_26w: rate 0.7931%; event month-ends 4,883; distinct episodes 2,148; symbols 2,006
- cost of the typical base: median 52w fwd return 6.8%; P(52w drawdown <= -40%) 6.7%

## 3. Univariate lift (ev2x_13w) — top vs bottom quintile, train vs test

| feature | coverage | Q1 lift train | Q5 lift train | Q1 lift test | Q5 lift test | Q5 events test (symbols) | Q5 med fwd52 | Q5 P(dd<=-40%) | monotone? |
|---|---|---|---|---|---|---|---|---|---|
| prior_dd | 93% | 2.39 | 0.11 | 3.32 | 0.29 | 26 (19) | 7.6% | 4.9% | down |
| range_ratio | 100% | 0.40 | 0.89 | 0.41 | 1.88 | 305 (218) | 8.9% | 7.7% | up |
| dist_high | 100% | 0.83 | 0.38 | 1.86 | 0.46 | 57 (45) | 6.6% | 4.1% | no |
| rs26 | 100% | 0.82 | 1.10 | 1.00 | 2.01 | 273 (212) | 8.3% | 6.9% | no |
| n_analysts | 32% | nan | nan | 1.26 | 0.30 | 39 (27) | 5.0% | 14.4% | up |
| dvol_trend | 100% | 0.84 | 1.65 | 1.24 | 2.18 | 336 (235) | 7.6% | 6.7% | no |
| updown_vol | 100% | 0.37 | 1.35 | 0.77 | 1.68 | 213 (159) | 7.1% | 6.1% | up |
| lows_slope | 99% | 0.96 | 0.50 | 1.56 | 0.71 | 67 (51) | 5.3% | 6.3% | down |
| cp_dvol_z13 | 100% | 0.71 | 1.22 | 0.78 | 1.63 | 251 (174) | 7.7% | 6.5% | no |
| cp_vol_regime | 100% | 0.88 | 0.75 | 0.78 | 1.60 | 235 (181) | 8.7% | 7.3% | down |
| r26 | 100% | 0.46 | 1.72 | 1.12 | 1.86 | 249 (196) | 8.8% | 7.1% | up |
| pos_in_range | 100% | 0.61 | 0.57 | 1.27 | 0.54 | 66 (55) | 7.1% | 4.5% | no |
| cp_slope_brk | 100% | 0.24 | 1.11 | 0.66 | 1.37 | 198 (154) | 8.2% | 6.6% | up |
| vol_ratio | 100% | 0.66 | 0.63 | 0.83 | 1.48 | 234 (166) | 8.6% | 7.4% | no |
| beats_2y | 39% | 0.56 | 0.03 | 0.88 | 0.24 | 17 (14) | 10.2% | 9.5% | down |
| obv_div | 100% | 1.39 | 0.76 | 1.88 | 1.27 | 231 (163) | 5.1% | 6.9% | no |
| buy_share_d12 | 14% | nan | nan | 0.33 | 0.91 | 19 (11) | 9.8% | 4.2% | up |
| r13 | 100% | 0.53 | 1.32 | 1.23 | 1.79 | 259 (200) | 8.6% | 7.7% | no |
| buy_share | 21% | nan | nan | 0.28 | 0.83 | 94 (69) | 4.8% | 11.4% | up |
| cp_dvol_cusum | 100% | 0.74 | 1.26 | 1.19 | 1.69 | 268 (185) | 7.4% | 6.3% | no |
| beats_4q | 43% | 0.55 | 0.12 | 0.84 | 0.47 | 63 (42) | 8.8% | 8.3% | down |
| months_since_up | 20% | 0.00 | 0.11 | 0.05 | 0.37 | 19 (14) | 7.3% | 9.5% | no |
| surprise_4q | 43% | 0.54 | 0.18 | 1.13 | 0.84 | 64 (42) | 8.2% | 8.2% | down |
| rev_accel | 73% | 1.18 | 1.09 | 1.72 | 1.99 | 228 (146) | 6.6% | 8.1% | no |
| rev_g_base | 73% | 1.28 | 1.14 | 1.94 | 1.68 | 200 (130) | 6.7% | 9.6% | no |
| downgrades_12m | 20% | 0.12 | 0.00 | 0.28 | 0.04 | 1 (1) | 8.2% | 9.9% | up |
| ignored_beats_2y | 39% | 0.30 | 0.05 | 0.60 | 0.41 | 29 (21) | 8.9% | 9.1% | down |
| upgrades_12m | 20% | 0.08 | 0.00 | 0.31 | 0.15 | 3 (2) | 7.7% | 9.9% | up |
| bo_new_holders_12m | 28% | 0.09 | 0.00 | 0.23 | 0.38 | 20 (15) | 7.9% | 8.5% | up |
| coil_ebit | 64% | 1.17 | 0.93 | 1.67 | 1.53 | 145 (97) | 6.8% | 9.2% | no |
| ins_buys_8q | 23% | 0.15 | 0.00 | 0.18 | 0.32 | 10 (7) | 9.3% | 9.8% | down |
| ins_buy_quarters_4q | 23% | 0.11 | 0.00 | 0.17 | 0.30 | 12 (9) | 9.9% | 9.1% | up |
| ins_net_buy_4q | 23% | 0.12 | 0.00 | 0.24 | 0.33 | 11 (8) | 9.6% | 8.9% | up |
| size_dvol | 100% | 0.99 | 0.40 | 1.06 | 0.98 | 157 (103) | 7.9% | 8.7% | down |
| last_react | 35% | 0.13 | 0.37 | 0.46 | 0.53 | 31 (25) | 9.7% | 8.9% | up |
| ebit_g_base | 64% | 1.18 | 0.94 | 1.68 | 1.62 | 145 (92) | 6.9% | 8.8% | no |
| react_beats_mean | 37% | 0.17 | 0.17 | 0.55 | 0.49 | 29 (24) | 8.3% | 9.5% | up |
| coil_rev | 73% | 1.04 | 1.15 | 1.75 | 1.70 | 208 (142) | 7.0% | 10.1% | no |
| gm_delta_base | 73% | 1.29 | 1.13 | 1.73 | 1.70 | 167 (112) | 6.7% | 7.4% | no |

## 5. Walk-forward model (fit <= 2018, test 2019+)

**ev2x_13w**: AUC train 0.888 / test 0.796; test base rate 0.221%
- top 1% each month: precision 1.15% (lift 8.5x, n=1,872); median 52w fwd 0.0%
- top 5% each month: precision 1.16% (lift 8.7x, n=9,521); median 52w fwd 1.4%
- top 10% each month: precision 0.94% (lift 7.2x, n=19,086); median 52w fwd 2.3%
- strongest positive weights: pos_in_range +4.24, r26 +3.49, upgrades_12m +2.96, ignored_beats_2y +2.73, months_since_up +2.55, bo_increasing_12m_na +2.21, bo_new_holders_12m_na +2.21, ebit_g_base +1.73
- strongest negative weights: ins_buys_8q -6.37, downgrades_12m -5.33, bo_new_holders_12m -5.22, dist_high -5.20, beats_2y -4.83, ins_buy_quarters_4q -3.48

**ev2x_26w**: AUC train 0.871 / test 0.790; test base rate 0.870%
- top 1% each month: precision 4.72% (lift 8.8x, n=1,793); median 52w fwd 0.0%
- top 5% each month: precision 3.85% (lift 7.3x, n=9,154); median 52w fwd 2.6%
- top 10% each month: precision 3.32% (lift 6.4x, n=18,354); median 52w fwd 3.5%
- strongest positive weights: pos_in_range +4.71, cp_dvol_z13_na +2.51, cp_dvol_cusum_na +2.51, ignored_beats_2y +2.28, r26 +1.74, react_beats_mean +1.25, surprise_4q_na +0.99, range_ratio +0.96
- strongest negative weights: dist_high -5.73, beats_2y -2.76, prior_dd -2.58, rs26 -1.06, ins_buy_quarters_4q -0.88, coil_ebit -0.84

## 4. The archetypes, reconstructed point-in-time (weighted, fit <= 2018 / test 2019+)

| variant | base-months | share | lift train | lift test | 2x/13w rate test | 2x/26w rate test | events test (symbols) | median fwd52 | mean fwd52 | P(dd<=-40%) |
|---|---|---|---|---|---|---|---|---|---|---|
| all base-months | 323,320 | 100.0% | 1.00 | 1.00 | 0.22% | 0.87% | 824 (510) | 6.8% | 11.0% | 6.7% |
| coil only (>=1 coil leg) | 100,581 | 30.0% | 1.39 | 1.25 | 0.28% | 1.13% | 333 (216) | 7.2% | 12.5% | 8.2% |
| coil >= 2 legs | 41,056 | 12.1% | 1.89 | 1.47 | 0.33% | 1.27% | 160 (106) | 6.1% | 12.0% | 9.6% |
| Coiled Base (time+coil+perception) | 70,714 | 21.2% | 1.60 | 1.34 | 0.30% | 1.20% | 240 (163) | 8.1% | 13.7% | 7.4% |
| Base Ignition (coiled + >=2 ignition, >=1 volume) | 10,512 | 3.1% | 3.07 | 2.33 | 0.52% | 1.95% | 61 (52) | 8.5% | 16.4% | 7.0% |
| ignition only (>=2 incl volume, no coil) | 41,927 | 12.7% | 2.28 | 2.02 | 0.45% | 1.65% | 215 (161) | 7.7% | 14.1% | 6.0% |
| Coiled + fallen angel (prior_dd <= 0.6) | 15,273 | 4.0% | 5.30 | 3.73 | 0.82% | 3.01% | 142 (99) | 5.3% | 16.2% | 8.9% |
| Ignition + fallen angel | 2,538 | 0.6% | 8.98 | 5.62 | 1.24% | 4.06% | 35 (29) | 4.0% | 17.6% | 7.6% |

## 6. Clusters (k-means on rank features, fit on train)

### price + fundamentals

| cluster | n | lift train | lift test | events test | med fwd52 | P(dd<=-40%) | signature |
|---|---|---|---|---|---|---|---|
| 4 | 39,181 | 1.90 | 1.26 | 134 | 7.1% | 7.6% | lows_slope LOW (0.15); r26 HIGH (0.72); r13 HIGH (0.68); rs26 HIGH (0.68); dist_high LOW (0.32) |
| 6 | 25,926 | 1.87 | 1.43 | 103 | 8.5% | 7.9% | rev_g_base HIGH (0.86); ebit_g_base HIGH (0.82); coil_ebit HIGH (0.81); coil_rev HIGH (0.80); r26 HIGH (0.76) |
| 8 | 38,002 | 1.84 | 1.62 | 154 | 8.7% | 5.8% | r26 HIGH (0.91); rs26 HIGH (0.88); r13 HIGH (0.84); pos_in_range HIGH (0.84); dist_high HIGH (0.81) |
| 5 | 35,127 | 0.90 | 1.25 | 116 | 6.6% | 9.7% | pos_in_range LOW (0.11); r26 LOW (0.13); dist_high LOW (0.16); rs26 LOW (0.18); updown_vol LOW (0.24) |
| 9 | 30,026 | 0.89 | 1.18 | 95 | 5.8% | 10.5% | coil_rev HIGH (0.87); coil_ebit HIGH (0.84); dist_high LOW (0.17); rev_g_base HIGH (0.83); pos_in_range LOW (0.18) |
| 0 | 33,545 | 0.88 | 1.06 | 88 | 3.3% | 7.5% | dvol_trend LOW (0.20); vol_ratio LOW (0.24); range_ratio LOW (0.26); pos_in_range LOW (0.27); obv_div HIGH (0.72) |
| 2 | 32,562 | 0.82 | 0.94 | 82 | 8.2% | 5.4% | vol_ratio HIGH (0.80); range_ratio HIGH (0.73); obv_div LOW (0.38); dvol_trend HIGH (0.62); dist_high HIGH (0.58) |
| 1 | 23,425 | 0.59 | 0.36 | 20 | 8.0% | 7.0% | r26 LOW (0.12); r13 LOW (0.16); rs26 LOW (0.17); updown_vol LOW (0.20); lows_slope HIGH (0.80) |
| 7 | 35,770 | 0.41 | 0.22 | 19 | 6.2% | 3.2% | dist_high HIGH (0.88); pos_in_range HIGH (0.87); updown_vol HIGH (0.76); range_ratio LOW (0.24); vol_ratio LOW (0.25) |
| 3 | 29,756 | 0.35 | 0.20 | 13 | 6.1% | 3.9% | lows_slope HIGH (0.81); range_ratio LOW (0.20); prior_dd HIGH (0.71); dist_high HIGH (0.70); pos_in_range HIGH (0.69) |

**Typology of the explosions themselves**

- type 0: 228 events / 166 symbols — obv_div LOW (0.11); r26 HIGH (0.87); dvol_trend HIGH (0.84); rev_g_base LOW (0.18); rs26 HIGH (0.82); coil_rev LOW (0.19)
- type 1: 136 events / 107 symbols — coil_rev HIGH (0.88); rev_g_base HIGH (0.85); dist_high LOW (0.18); prior_dd LOW (0.19); coil_ebit HIGH (0.80); ebit_g_base HIGH (0.77)
- type 2: 193 events / 153 symbols — obv_div HIGH (0.79); r13 HIGH (0.75); updown_vol HIGH (0.74); prior_dd LOW (0.26); r26 HIGH (0.72); rs26 HIGH (0.68)
- type 3: 175 events / 133 symbols — prior_dd LOW (0.14); dist_high LOW (0.14); pos_in_range LOW (0.20); r26 LOW (0.22); rs26 LOW (0.23); obv_div HIGH (0.75)
- type 4: 246 events / 174 symbols — r26 HIGH (0.88); rs26 HIGH (0.86); obv_div LOW (0.15); dvol_trend HIGH (0.85); range_ratio HIGH (0.81); r13 HIGH (0.78)
- type 5: 194 events / 143 symbols — dist_high LOW (0.15); prior_dd LOW (0.16); obv_div LOW (0.19); pos_in_range LOW (0.21); range_ratio HIGH (0.79); vol_ratio HIGH (0.77)

### price + fundamentals + perception (2019+ coverage)

| cluster | n | lift train | lift test | events test | med fwd52 | P(dd<=-40%) | signature |
|---|---|---|---|---|---|---|---|
| 7 | 42,082 | 3.28 | 2.36 | 269 | 7.7% | 6.1% | dvol_trend HIGH (0.84); cp_slope_brk HIGH (0.84); cp_dvol_z13 HIGH (0.83); r26 HIGH (0.83); rs26 HIGH (0.82) |
| 9 | 43,860 | 1.52 | 1.25 | 149 | 7.2% | 8.6% | lows_slope LOW (0.18); cp_slope_brk HIGH (0.72); cp_dvol_z13 LOW (0.30); cp_dvol_cusum LOW (0.32); dist_high LOW (0.32) |
| 5 | 39,002 | 0.98 | 1.15 | 113 | 3.1% | 8.2% | dvol_trend LOW (0.20); vol_ratio LOW (0.21); cp_dvol_z13 LOW (0.21); cp_vol_regime LOW (0.22); cp_dvol_cusum LOW (0.23) |
| 4 | 24,407 | 0.85 | 0.46 | 27 | 7.3% | 4.0% | pos_in_range HIGH (0.86); dist_high HIGH (0.85); cp_dvol_z13 HIGH (0.80); dvol_trend HIGH (0.79); r26 HIGH (0.77) |
| 3 | 34,617 | 0.82 | 0.91 | 75 | 5.9% | 9.3% | r26 LOW (0.13); pos_in_range LOW (0.16); cp_slope_brk LOW (0.18); dist_high LOW (0.20); rs26 LOW (0.22) |
| 2 | 38,272 | 0.72 | 1.14 | 119 | 8.5% | 8.1% | r26 LOW (0.14); cp_slope_brk LOW (0.17); pos_in_range LOW (0.19); rs26 LOW (0.19); cp_dvol_z13 HIGH (0.79) |
| 6 | 28,160 | 0.61 | 0.38 | 24 | 6.2% | 4.4% | lows_slope HIGH (0.78); cp_slope_brk LOW (0.28); cp_dvol_z13 HIGH (0.71); cp_dvol_cusum HIGH (0.71); prior_dd HIGH (0.69) |
| 1 | 26,447 | 0.53 | 0.44 | 29 | 9.1% | 5.8% | r26 HIGH (0.88); cp_slope_brk HIGH (0.86); rs26 HIGH (0.85); pos_in_range HIGH (0.84); dist_high HIGH (0.82) |
| 8 | 28,518 | 0.27 | 0.23 | 16 | 5.3% | 3.4% | range_ratio LOW (0.17); dist_high HIGH (0.80); pos_in_range HIGH (0.79); vol_ratio LOW (0.23); cp_vol_regime LOW (0.26) |
| 0 | 17,955 | 0.00 | 0.06 | 3 | 9.3% | 7.9% | bo_increasing_12m LOW (0.10); beats_4q HIGH (0.88); size_dvol HIGH (0.87); bo_new_holders_12m LOW (0.18); ignored_beats_2y HIGH (0.80) |

**Typology of the explosions themselves**

- type 0: 208 events / 157 symbols — dist_high LOW (0.12); prior_dd LOW (0.14); pos_in_range LOW (0.18); r26 LOW (0.20); dvol_trend LOW (0.22); obv_div HIGH (0.78)
- type 1: 211 events / 161 symbols — r26 HIGH (0.92); rs26 HIGH (0.92); dvol_trend HIGH (0.91); cp_dvol_z13 HIGH (0.88); obv_div LOW (0.13); cp_slope_brk HIGH (0.86)
- type 2: 189 events / 145 symbols — prior_dd LOW (0.23); dvol_trend LOW (0.23); cp_dvol_z13 LOW (0.25); r13 HIGH (0.74); obv_div HIGH (0.74); lows_slope LOW (0.27)
- type 3: 180 events / 129 symbols — r26 HIGH (0.85); dvol_trend HIGH (0.85); rev_g_base HIGH (0.84); rs26 HIGH (0.82); coil_rev HIGH (0.82); obv_div LOW (0.18)
- type 4: 207 events / 152 symbols — dist_high LOW (0.17); prior_dd LOW (0.17); pos_in_range LOW (0.22); r26 LOW (0.23); range_ratio HIGH (0.77); vol_ratio HIGH (0.76)
- type 5: 177 events / 133 symbols — prior_dd LOW (0.22); coil_rev LOW (0.23); rev_g_base LOW (0.24); dvol_trend HIGH (0.74); r26 HIGH (0.71); updown_vol HIGH (0.69)

## 7. Drug developers (biotech / pharma), analysed separately

- ev2x_13w: biotech rate 0.446% vs non-biotech 0.186%
- ev3x_13w: biotech rate 0.089% vs non-biotech 0.027%
- ev2x_26w: biotech rate 1.521% vs non-biotech 0.793%
- median 52w fwd: biotech 5.4% vs 6.8%; P(dd<=-40%): 6.6% vs 6.7%

| variant (biotech only) | base-months | lift train | lift test | median fwd52 | P(dd<=-40%) |
|---|---|---|---|---|---|
| all base-months | 13,870 | 1.00 | 1.00 | 5.4% | 6.6% |
| coil only (>=1 coil leg) | 5,460 | 0.92 | 1.18 | 5.2% | 7.0% |
| coil >= 2 legs | 2,372 | 1.18 | 0.55 | 5.2% | 9.0% |
| Coiled Base (time+coil+perception) | 3,666 | 1.19 | 1.31 | 5.3% | 6.3% |
| Base Ignition (coiled + >=2 ignition, >=1 volume) | 559 | 3.96 | 1.45 | 3.5% | 5.7% |
| ignition only (>=2 incl volume, no coil) | 1,808 | 3.69 | 2.07 | 4.1% | 5.5% |
| Coiled + fallen angel (prior_dd <= 0.6) | 1,271 | 2.17 | 2.29 | 0.9% | 10.5% |
| Ignition + fallen angel | 210 | 12.72 | 1.70 | -1.2% | 11.8% |

## Caveats

- Survivorship: delisted names are included where FMP still serves their price history; coverage of delisted names is reported in fmp_price_universe.csv.
- Point-in-time: fundamentals keyed on filing date (75-day lag where none); perception series start 2017 (actions) / 2019 (monthly counts), so those features are tested on the later part of the sample only.
- Overlap: month-end observations inside one base overlap; episode and symbol counts are shown next to every event count.
- Archetype flags are today's snapshot (not point-in-time), so clusters are built from point-in-time INGREDIENTS of those archetypes, not the flags themselves.
