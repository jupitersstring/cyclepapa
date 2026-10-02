# Raising the lift — a second forensic investigation

1,175,853 liquid month-ends, 9,213 symbols (non-biotech). Base rate of a 3x within 24 months: 4.26%. Each archetype is applied exactly as defined on the point-in-time panel; 'lift vs archetype' is the sub-group's rate over the archetype's own rate.

## The nine archetypes on the panel

| archetype                 |     n |   events |   rate |   lift |   t10_60_rate |   p_blowup_50 |   median_fwd_24m |
|:--------------------------|------:|---------:|-------:|-------:|--------------:|--------------:|-----------------:|
| left_for_dead_value       | 35405 |     4274 |  0.121 |  2.847 |         0.041 |         0.22  |            0.185 |
| fallen_insider_conviction |  3734 |      615 |  0.167 |  3.917 |         0.045 |         0.315 |            0.257 |
| fallen_ignored_believers  |  5574 |      558 |  0.089 |  2.079 |         0.013 |         0.27  |            0.086 |
| smart_money_wreckage      |  6101 |     1220 |  0.2   |  4.689 |         0.061 |         0.325 |            0.357 |
| fallen_below_cycle        | 76582 |     7230 |  0.092 |  2.153 |         0.018 |         0.18  |            0.132 |
| margin_inflect_weak_tape  | 44546 |     2355 |  0.049 |  1.143 |         0.014 |         0.165 |            0.075 |
| tree_recipe               | 21770 |     3107 |  0.144 |  3.384 |         0.042 |         0.274 |            0.093 |
| tree_recipe_10x           | 26849 |     3377 |  0.126 |  2.967 |         0.042 |         0.225 |            0.119 |
| sequence_preignition      | 87787 |     6153 |  0.064 |  1.5   |         0.016 |         0.159 |            0.084 |

## left_for_dead_value  (rate 12.14%, lift 2.85x, blow-up 22%)

### 1. Refinements that RAISE the odds inside the archetype

| condition              |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| tr_fcfm_streak LOW     |  929 |      215 |  0.25  |               2.06  |         0.131 |
| bo_increasing_12m HIGH | 1153 |      280 |  0.242 |               1.991 |         0.279 |
| buy_share_d12 LOW      |  896 |      215 |  0.234 |               1.929 |         0.229 |
| headcount_growth       |  820 |      180 |  0.228 |               1.877 |         0.388 |
| emp_g1 HIGH            |  932 |      208 |  0.225 |               1.855 |         0.372 |
| gap_perc_buyshare LOW  |  606 |      134 |  0.223 |               1.837 |         0.248 |
| gap_perc_buyshare HIGH |  565 |      122 |  0.214 |               1.767 |         0.171 |
| insider_buying         | 1949 |      406 |  0.21  |               1.729 |         0.302 |
| ins_net_buy_4q HIGH    | 2122 |      415 |  0.2   |               1.646 |         0.318 |
| rev_per_emp_g1 LOW     | 2057 |      392 |  0.197 |               1.623 |         0.339 |
| buy_share_d12 HIGH     |  558 |      107 |  0.197 |               1.619 |         0.255 |
| months_since_up HIGH   | 1968 |      387 |  0.195 |               1.605 |         0.295 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                                   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:--------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| kr_researchAndDevelopementToRevenue_own LOW | 1791 |       86 |  0.047 |               0.39  |         0.095 |
| kr_researchAndDevelopementToRevenue LOW     | 2176 |      113 |  0.049 |               0.404 |         0.125 |
| kr_priceToSalesRatio HIGH                   | 1973 |      113 |  0.052 |               0.43  |         0.21  |
| flat_base                                   | 2647 |      177 |  0.054 |               0.443 |         0.132 |
| r260 HIGH                                   |  828 |       51 |  0.06  |               0.493 |         0.168 |
| ev_sales HIGH                               | 1784 |      126 |  0.064 |               0.524 |         0.177 |
| kr_evToSales HIGH                           | 3002 |      210 |  0.064 |               0.529 |         0.213 |
| npm HIGH                                    | 2509 |      173 |  0.064 |               0.531 |         0.194 |
| ps HIGH                                     | 1002 |       76 |  0.064 |               0.531 |         0.18  |
| gm HIGH                                     | 4056 |      273 |  0.065 |               0.536 |         0.175 |
| kr_grossProfitMargin HIGH                   | 4887 |      325 |  0.065 |               0.538 |         0.206 |
| rd_rev LOW                                  | 3605 |      248 |  0.068 |               0.562 |         0.104 |

### 2. Timing inside the bottoming process


*low_age*

| low_age   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| <2m       | 10637 |     1577 |  0.149 |               1.226 |         0.263 |         0.047 |
| 2-6m      |  6417 |      853 |  0.136 |               1.12  |         0.222 |         0.047 |
| 6-12m     |  4399 |      582 |  0.131 |               1.076 |         0.188 |         0.046 |
| 1-2y      |  4191 |      413 |  0.094 |               0.777 |         0.2   |         0.027 |
| >2y       |  9761 |      849 |  0.087 |               0.719 |         0.192 |         0.029 |

*dd_time*

| dd_time   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| >80%      | 24290 |     3086 |  0.128 |               1.056 |         0.217 |         0.042 |
| 50-80%    |  7490 |      762 |  0.103 |               0.848 |         0.236 |         0.037 |
| <50%      |  2136 |      198 |  0.091 |               0.747 |         0.267 |         0.042 |

*r13_sign*

| r13_sign   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:-----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| 13w up     | 10321 |     1261 |  0.124 |               1.026 |         0.191 |         0.044 |
| 13w down   | 25084 |     3013 |  0.12  |               0.99  |         0.232 |         0.04  |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|------:|---------:|-------:|--------------------:|--------------:|
| bear (<-15%) |  4142 |      805 |  0.209 |               1.724 |         0.096 |
| bull (>+15%) |  3091 |      505 |  0.168 |               1.387 |         0.176 |
| weak         |  8339 |      946 |  0.115 |               0.95  |         0.202 |
| flat         | 11827 |     1214 |  0.099 |               0.82  |         0.261 |
| firm         |  8006 |      804 |  0.097 |               0.799 |         0.256 |

|   year |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|-----:|---------:|-------:|--------------------:|--------------:|
|   2012 | 1173 |      185 |  0.163 |               1.342 |         0.072 |
|   2013 | 1650 |      231 |  0.126 |               1.037 |         0.143 |
|   2014 | 1459 |      132 |  0.069 |               0.572 |         0.324 |
|   2015 | 1860 |      166 |  0.084 |               0.69  |         0.266 |
|   2016 | 2105 |      206 |  0.1   |               0.828 |         0.104 |
|   2017 | 1510 |       33 |  0.021 |               0.173 |         0.252 |
|   2018 | 2513 |       88 |  0.036 |               0.294 |         0.423 |
|   2019 | 3588 |      400 |  0.117 |               0.961 |         0.419 |
|   2020 | 6479 |     1584 |  0.262 |               2.159 |         0.076 |
|   2021 | 2565 |      217 |  0.082 |               0.673 |         0.213 |
|   2022 | 3924 |      305 |  0.076 |               0.629 |         0.213 |
|   2023 | 3352 |      225 |  0.064 |               0.527 |         0.24  |
|   2024 | 2843 |      340 |  0.107 |               0.884 |         0.213 |
|   2025 |  348 |      156 |  0.41  |               3.374 |         0.284 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| Energy                 | 1912 |      342 |  0.197 |               1.623 |         0.316 |
| Materials              | 5038 |      817 |  0.163 |               1.34  |         0.221 |
| Information Technology | 3070 |      414 |  0.134 |               1.105 |         0.135 |
| Industrials            | 6966 |      766 |  0.114 |               0.942 |         0.182 |
| Financials             | 2663 |      290 |  0.108 |               0.887 |         0.195 |
| Communication Services | 1616 |      172 |  0.105 |               0.865 |         0.223 |
| Consumer Discretionary | 5082 |      521 |  0.1   |               0.827 |         0.217 |
| Utilities              |  415 |       37 |  0.084 |               0.691 |         0.108 |
| Consumer Staples       | 1256 |      104 |  0.074 |               0.608 |         0.173 |
| Health Care            |  227 |       12 |  0.04  |               0.326 |         0.399 |
| Real Estate            | 2286 |      103 |  0.038 |               0.314 |         0.266 |

*market*

| market   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|-----:|---------:|-------:|--------------------:|--------------:|
| NS       | 1326 |      388 |  0.284 |               2.338 |         0.194 |
| TO       | 1376 |      312 |  0.225 |               1.855 |         0.395 |
| MC       |  250 |       50 |  0.185 |               1.524 |         0.065 |
| US       | 8073 |     1461 |  0.183 |               1.504 |         0.291 |
| DE       |  437 |       62 |  0.142 |               1.173 |         0.163 |
| AX       |  706 |      100 |  0.133 |               1.095 |         0.381 |
| SA       |  502 |       67 |  0.131 |               1.08  |         0.247 |
| JO       |  226 |       35 |  0.121 |               0.998 |         0.383 |
| BK       |  383 |       44 |  0.111 |               0.911 |         0.317 |
| SR       |  319 |       33 |  0.109 |               0.898 |         0.127 |
| L        | 1136 |      125 |  0.105 |               0.865 |         0.267 |
| KQ       |  478 |       48 |  0.097 |               0.802 |         0.178 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition                    |    n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:-----------------------------|-----:|-------:|--------------------:|--------------:|----------------:|
| maxdd104 HIGH                |  292 |  0.131 |               1.076 |         0.035 |          -0.185 |
| gap_own_fcfps LOW            |  809 |  0.152 |               1.253 |         0.12  |          -0.1   |
| tr_fcfm_streak LOW           |  929 |  0.25  |               2.06  |         0.131 |          -0.089 |
| rd_rev HIGH                  | 4207 |  0.123 |               1.015 |         0.153 |          -0.067 |
| gap_trend_opm LOW            | 2978 |  0.133 |               1.096 |         0.154 |          -0.066 |
| gap_trend_roic LOW           | 2525 |  0.134 |               1.107 |         0.158 |          -0.062 |
| accumulation                 | 1135 |  0.149 |               1.23  |         0.16  |          -0.059 |
| tr_roic_streak LOW           |  757 |  0.163 |               1.345 |         0.169 |          -0.051 |
| kr_netIncomePerShare_g4 HIGH | 2479 |  0.124 |               1.023 |         0.169 |          -0.051 |
| gap_perc_buyshare HIGH       |  565 |  0.214 |               1.767 |         0.171 |          -0.048 |

*Among the archetype's 3x winners, P(10x within 5y) = 22.1%; conditions that raise it:*

| condition                       |   n |   p_10x_given_3x |
|:--------------------------------|----:|-----------------:|
| tr_fcfm_streak LOW              | 205 |            0.395 |
| n_analysts LOW                  | 198 |            0.343 |
| tr_opm_streak LOW               |  70 |            0.343 |
| tr_fcfm_consist HIGH            | 339 |            0.342 |
| kr_operatingReturnOnAssets HIGH | 193 |            0.337 |
| gap_perc_buyshare HIGH          |  78 |            0.333 |
| gap_trend_opm LOW               | 282 |            0.333 |
| roic_d1 HIGH                    | 454 |            0.333 |
| kr_freeCashFlowPerShare_g4 LOW  | 341 |            0.326 |
| ignored_beats_2y LOW            | 356 |            0.32  |

## fallen_insider_conviction  (rate 16.70%, lift 3.92x, blow-up 32%)

### 1. Refinements that RAISE the odds inside the archetype

| condition                                 |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| buyback_yield HIGH                        |  669 |      184 |  0.291 |               1.742 |         0.251 |
| capex_rev HIGH                            |  782 |      204 |  0.273 |               1.633 |         0.361 |
| sga_rev LOW                               |  356 |       93 |  0.267 |               1.599 |         0.255 |
| buy_share_d12 LOW                         |  325 |       85 |  0.262 |               1.572 |         0.284 |
| kr_freeCashFlowOperatingCashFlowRatio LOW |  657 |      163 |  0.26  |               1.557 |         0.334 |
| kr_capexToRevenue HIGH                    |  755 |      183 |  0.252 |               1.507 |         0.333 |
| kr_capexToOperatingCashFlow HIGH          |  830 |      202 |  0.252 |               1.507 |         0.326 |
| kr_debtServiceCoverageRatio HIGH          |  386 |       94 |  0.251 |               1.502 |         0.255 |
| tr_debt_slope8 HIGH                       |  756 |      181 |  0.248 |               1.486 |         0.378 |
| deep_value                                | 1739 |      419 |  0.246 |               1.471 |         0.308 |
| kr_debtToEquityRatio_own HIGH             | 1246 |      297 |  0.242 |               1.446 |         0.36  |
| tr_debt_consist HIGH                      |  593 |      138 |  0.239 |               1.431 |         0.342 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                        |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| kr_debtToAssetsRatio LOW         | 380 |       31 |  0.065 |               0.389 |         0.237 |
| kr_capexToRevenue LOW            | 442 |       33 |  0.071 |               0.425 |         0.207 |
| kr_grossProfitMargin HIGH        | 347 |       25 |  0.072 |               0.43  |         0.325 |
| kr_debtToCapitalRatio LOW        | 500 |       45 |  0.075 |               0.448 |         0.249 |
| kr_assetTurnover LOW             | 414 |       34 |  0.087 |               0.521 |         0.153 |
| equity_assets HIGH               | 598 |       57 |  0.088 |               0.524 |         0.23  |
| kr_debtToEquityRatio LOW         | 623 |       63 |  0.09  |               0.539 |         0.381 |
| kr_capexToDepreciation LOW       | 424 |       37 |  0.092 |               0.549 |         0.202 |
| kr_currentRatio HIGH             | 664 |       65 |  0.092 |               0.551 |         0.285 |
| kr_currentRatio_d4 HIGH          | 635 |       64 |  0.093 |               0.557 |         0.38  |
| current_ratio HIGH               | 692 |       68 |  0.093 |               0.559 |         0.292 |
| kr_priceToFreeCashFlowRatio HIGH | 338 |       32 |  0.094 |               0.565 |         0.385 |

### 2. Timing inside the bottoming process


*low_age*

| low_age   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| <2m       | 1151 |      244 |  0.214 |               1.284 |         0.326 |         0.075 |
| 2-6m      |  923 |      186 |  0.205 |               1.225 |         0.297 |         0.052 |
| 6-12m     |  562 |       91 |  0.166 |               0.993 |         0.311 |         0.021 |
| >2y       |  773 |       80 |  0.102 |               0.612 |         0.3   |         0.017 |
| 1-2y      |  325 |       14 |  0.037 |               0.219 |         0.372 |         0     |

*dd_time*

| dd_time   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| 50-80%    |  963 |      178 |  0.183 |               1.094 |         0.295 |         0.067 |
| >80%      | 2124 |      361 |  0.173 |               1.038 |         0.327 |         0.046 |
| <50%      |  418 |       47 |  0.117 |               0.701 |         0.354 |         0.015 |

*r13_sign*

| r13_sign   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:-----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| 13w down   | 2326 |      385 |  0.168 |               1.005 |         0.328 |         0.052 |
| 13w up     | 1408 |      230 |  0.166 |               0.991 |         0.294 |         0.034 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|-----:|---------:|-------:|--------------------:|--------------:|
| bear (<-15%) |  326 |      137 |  0.43  |               2.575 |         0.113 |
| weak         |  561 |      122 |  0.226 |               1.353 |         0.232 |
| bull (>+15%) |  431 |       87 |  0.205 |               1.227 |         0.256 |
| firm         | 1046 |      126 |  0.118 |               0.707 |         0.37  |
| flat         | 1370 |      143 |  0.104 |               0.622 |         0.377 |

|   year |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|----:|---------:|-------:|--------------------:|--------------:|
|   2015 | 202 |       11 |  0.039 |               0.231 |         0.356 |
|   2016 | 312 |       43 |  0.147 |               0.881 |         0.12  |
|   2017 | 196 |        8 |  0.027 |               0.159 |         0.328 |
|   2018 | 208 |        2 |  0.011 |               0.064 |         0.575 |
|   2019 | 302 |       53 |  0.174 |               1.041 |         0.677 |
|   2020 | 806 |      361 |  0.461 |               2.762 |         0.144 |
|   2021 | 284 |       11 |  0.04  |               0.241 |         0.416 |
|   2022 | 425 |       37 |  0.09  |               0.54  |         0.333 |
|   2023 | 415 |       25 |  0.054 |               0.323 |         0.324 |
|   2024 | 324 |       28 |  0.082 |               0.489 |         0.332 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|----:|---------:|-------:|--------------------:|--------------:|
| Materials              | 229 |       75 |  0.332 |               1.989 |         0.285 |
| Consumer Discretionary | 536 |      126 |  0.236 |               1.413 |         0.412 |
| Energy                 | 359 |       79 |  0.235 |               1.406 |         0.226 |
| Industrials            | 279 |       60 |  0.219 |               1.313 |         0.272 |
| Communication Services | 300 |       55 |  0.181 |               1.081 |         0.521 |
| Information Technology | 349 |       47 |  0.143 |               0.853 |         0.245 |
| Financials             | 361 |       25 |  0.066 |               0.395 |         0.21  |
| Consumer Staples       | 173 |        7 |  0.026 |               0.155 |         0.473 |

*market*

| market   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|-----:|---------:|-------:|--------------------:|--------------:|
| US       | 3734 |      615 |  0.167 |                   1 |         0.315 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition                                     |   n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:----------------------------------------------|----:|-------:|--------------------:|--------------:|----------------:|
| n_analysts HIGH                               | 325 |  0.238 |               1.425 |         0.183 |          -0.132 |
| dvol_usd_log HIGH                             | 446 |  0.23  |               1.38  |         0.197 |          -0.119 |
| kr_fixedAssetTurnover LOW                     | 481 |  0.172 |               1.031 |         0.205 |          -0.11  |
| kr_operatingCashFlowSalesRatio HIGH           | 439 |  0.189 |               1.13  |         0.207 |          -0.108 |
| kr_capitalExpenditureCoverageRatio HIGH       | 527 |  0.174 |               1.041 |         0.213 |          -0.103 |
| months_since_up LOW                           | 447 |  0.189 |               1.13  |         0.215 |          -0.1   |
| kr_dividendPaidAndCapexCoverageRatio HIGH     | 749 |  0.167 |               1.002 |         0.217 |          -0.098 |
| kr_dividendPaidAndCapexCoverageRatio_own HIGH | 781 |  0.21  |               1.255 |         0.226 |          -0.09  |
| kr_solvencyRatio HIGH                         | 249 |  0.169 |               1.011 |         0.237 |          -0.078 |
| tr_fcfm_consist HIGH                          | 336 |  0.237 |               1.418 |         0.239 |          -0.077 |

*Among the archetype's 3x winners, P(10x within 5y) = 19.0%; conditions that raise it:*

| condition                                 |   n |   p_10x_given_3x |
|:------------------------------------------|----:|-----------------:|
| kr_quickRatio LOW                         | 119 |            0.328 |
| gap_fcfps_1y HIGH                         |  68 |            0.324 |
| kr_capitalExpenditureCoverageRatio_d4 LOW | 110 |            0.318 |
| kr_evToOperatingCashFlow_own LOW          |  77 |            0.312 |
| kr_fixedAssetTurnover_own HIGH            |  71 |            0.31  |
| n_analysts LOW                            |  68 |            0.309 |
| intang_assets LOW                         | 141 |            0.298 |
| gm_d1 HIGH                                |  74 |            0.297 |
| kr_operatingCashFlowPerShare_own HIGH     |  64 |            0.297 |
| bo_increasing_12m HIGH                    |  88 |            0.295 |

## fallen_ignored_believers  (rate 8.86%, lift 2.08x, blow-up 27%)

### 1. Refinements that RAISE the odds inside the archetype

| condition               |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| n_analysts LOW          |  442 |      123 |  0.265 |               2.989 |         0.334 |
| accumulation            |  213 |       48 |  0.205 |               2.313 |         0.24  |
| gap_perc_buyshare LOW   |  416 |       73 |  0.173 |               1.951 |         0.437 |
| capex_rev HIGH          |  881 |      153 |  0.154 |               1.742 |         0.301 |
| rev_g1 HIGH             |  753 |      117 |  0.153 |               1.729 |         0.303 |
| pt_prem_12m HIGH        |  228 |       41 |  0.152 |               1.719 |         0.328 |
| ev_ebit LOW             |  411 |       72 |  0.151 |               1.706 |         0.126 |
| kr_incomeQuality_d4 LOW | 1030 |      162 |  0.15  |               1.693 |         0.242 |
| buyback_yield LOW       |  963 |      156 |  0.148 |               1.674 |         0.404 |
| roic_d1 HIGH            | 1022 |      167 |  0.147 |               1.659 |         0.204 |
| cyclical_trough         |  626 |       94 |  0.145 |               1.641 |         0.227 |
| tr_revg_consist HIGH    |  843 |      109 |  0.143 |               1.613 |         0.219 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                             |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:--------------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| kr_daysOfInventoryOutstanding_own LOW | 628 |       29 |  0.035 |               0.398 |         0.167 |
| kr_capexToOperatingCashFlow_own LOW   | 868 |       47 |  0.043 |               0.487 |         0.265 |
| rd_rev LOW                            | 450 |       26 |  0.047 |               0.53  |         0.176 |
| kr_daysOfInventoryOutstanding LOW     | 557 |       37 |  0.048 |               0.541 |         0.15  |
| dvol_usd_log HIGH                     | 380 |       25 |  0.049 |               0.548 |         0.23  |
| kr_currentRatio LOW                   | 787 |       42 |  0.05  |               0.56  |         0.21  |
| kr_grossProfitMargin HIGH             | 754 |       47 |  0.05  |               0.567 |         0.185 |
| kr_capexToDepreciation LOW            | 841 |       57 |  0.051 |               0.579 |         0.259 |
| gap_sales_3y LOW                      | 759 |       51 |  0.052 |               0.587 |         0.278 |
| kr_daysOfPayablesOutstanding LOW      | 664 |       38 |  0.053 |               0.603 |         0.125 |
| pb HIGH                               | 702 |       46 |  0.054 |               0.611 |         0.23  |
| kr_financialLeverageRatio HIGH        | 783 |       43 |  0.055 |               0.625 |         0.345 |

### 2. Timing inside the bottoming process


*low_age*

| low_age   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| 2-6m      |  696 |       83 |  0.103 |               1.166 |         0.312 |         0.024 |
| <2m       | 1060 |      117 |  0.1   |               1.128 |         0.371 |         0.03  |
| 1-2y      |  856 |       98 |  0.093 |               1.049 |         0.283 |         0.002 |
| 6-12m     |  599 |       54 |  0.082 |               0.93  |         0.298 |         0.011 |
| >2y       | 2363 |      206 |  0.078 |               0.885 |         0.195 |         0     |

*dd_time*

| dd_time   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| >80%      | 4122 |      439 |  0.095 |               1.066 |         0.252 |         0.018 |
| 50-80%    | 1183 |      109 |  0.082 |               0.923 |         0.317 |         0.005 |
| <50%      |  249 |       10 |  0.04  |               0.456 |         0.338 |         0     |

*r13_sign*

| r13_sign   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:-----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| 13w up     | 1767 |      199 |  0.1   |               1.125 |         0.254 |         0.019 |
| 13w down   | 3807 |      359 |  0.083 |               0.941 |         0.277 |         0.01  |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|-----:|---------:|-------:|--------------------:|--------------:|
| bull (>+15%) |  379 |       62 |  0.16  |               1.808 |         0.368 |
| bear (<-15%) |  553 |       82 |  0.131 |               1.48  |         0.133 |
| firm         | 1235 |      128 |  0.089 |               1.004 |         0.279 |
| weak         | 1259 |      112 |  0.082 |               0.92  |         0.222 |
| flat         | 2148 |      174 |  0.069 |               0.778 |         0.308 |

|   year |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|-----:|---------:|-------:|--------------------:|--------------:|
|   2020 |  103 |       31 |  0.323 |               3.641 |         0.163 |
|   2021 |  752 |       59 |  0.077 |               0.874 |         0.354 |
|   2022 | 1045 |       68 |  0.066 |               0.743 |         0.31  |
|   2023 | 1751 |       59 |  0.03  |               0.343 |         0.287 |
|   2024 | 1690 |      197 |  0.094 |               1.059 |         0.191 |
|   2025 |  179 |      131 |  0.664 |               7.496 |         0.108 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| Materials              |  627 |      120 |  0.175 |               1.972 |         0.195 |
| Information Technology | 1034 |      153 |  0.13  |               1.463 |         0.256 |
| Industrials            |  885 |      100 |  0.104 |               1.172 |         0.221 |
| Financials             |  240 |       28 |  0.086 |               0.971 |         0.112 |
| Consumer Discretionary |  843 |       59 |  0.069 |               0.774 |         0.304 |
| Communication Services |  379 |       24 |  0.062 |               0.701 |         0.241 |
| Health Care            |  195 |       12 |  0.058 |               0.649 |         0.219 |
| Real Estate            |  196 |       10 |  0.029 |               0.329 |         0.483 |
| Consumer Staples       |  295 |       10 |  0.025 |               0.287 |         0.254 |

*market*

| market   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|-----:|---------:|-------:|--------------------:|--------------:|
| KS       |  161 |       17 |  0.122 |               1.375 |         0.057 |
| US       | 2272 |      265 |  0.114 |               1.286 |         0.386 |
| SS       |  540 |       42 |  0.074 |               0.83  |         0.148 |
| AX       |  168 |       16 |  0.068 |               0.772 |         0.167 |
| L        |  201 |       12 |  0.055 |               0.618 |         0.257 |
| SZ       | 1120 |       81 |  0.05  |               0.559 |         0.132 |
| T        |  234 |       14 |  0.049 |               0.555 |         0.029 |
| HK       |  265 |        7 |  0.02  |               0.227 |         0.44  |

### 6. The tail — cutting the blow-up while keeping the lift

| condition                              |   n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:---------------------------------------|----:|-------:|--------------------:|--------------:|----------------:|
| kr_debtServiceCoverageRatio HIGH       | 605 |  0.095 |               1.068 |         0.114 |          -0.156 |
| kr_netIncomePerShare_g4 HIGH           | 308 |  0.107 |               1.206 |         0.115 |          -0.155 |
| ev_ebit LOW                            | 411 |  0.151 |               1.706 |         0.126 |          -0.144 |
| kr_returnOnAssets HIGH                 | 488 |  0.095 |               1.077 |         0.137 |          -0.133 |
| kr_solvencyRatio HIGH                  | 677 |  0.098 |               1.1   |         0.139 |          -0.131 |
| kr_operatingCashFlowCoverageRatio HIGH | 845 |  0.101 |               1.142 |         0.143 |          -0.127 |
| kr_returnOnTangibleAssets HIGH         | 496 |  0.09  |               1.013 |         0.152 |          -0.118 |
| cfo_ni HIGH                            | 433 |  0.104 |               1.177 |         0.152 |          -0.118 |
| kr_pretaxProfitMargin HIGH             | 447 |  0.091 |               1.029 |         0.16  |          -0.11  |
| wks_since_lo260 HIGH                   | 573 |  0.089 |               1.006 |         0.166 |          -0.104 |

## smart_money_wreckage  (rate 19.99%, lift 4.69x, blow-up 33%)

### 1. Refinements that RAISE the odds inside the archetype

| condition                         |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:----------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| n_analysts LOW                    |  867 |      231 |  0.27  |               1.349 |         0.231 |
| capex_rev HIGH                    | 1316 |      336 |  0.265 |               1.324 |         0.359 |
| buy_share HIGH                    |  774 |      211 |  0.264 |               1.321 |         0.333 |
| n_analysts HIGH                   |  454 |      121 |  0.263 |               1.314 |         0.297 |
| kr_priceToBookRatio_d4 HIGH       |  474 |      122 |  0.26  |               1.299 |         0.402 |
| tr_debt_slope8 HIGH               | 1262 |      316 |  0.257 |               1.286 |         0.389 |
| kr_financialLeverageRatio_d4 HIGH | 1876 |      484 |  0.255 |               1.277 |         0.397 |
| kr_debtToEquityRatio_own HIGH     | 1996 |      509 |  0.254 |               1.268 |         0.344 |
| pt_prem_12m HIGH                  |  287 |       73 |  0.251 |               1.257 |         0.333 |
| fund_price_divergence             | 1799 |      450 |  0.25  |               1.248 |         0.331 |
| tr_gm_consist HIGH                |  733 |      180 |  0.248 |               1.242 |         0.388 |
| kr_debtToCapitalRatio_d4 HIGH     | 2019 |      499 |  0.248 |               1.24  |         0.397 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                           |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| kr_priceToSalesRatio_d4 HIGH        |  334 |       30 |  0.085 |               0.425 |         0.243 |
| inc_margin HIGH                     |  391 |       36 |  0.093 |               0.465 |         0.325 |
| roe HIGH                            |  321 |       31 |  0.098 |               0.492 |         0.337 |
| gap_sales_3y LOW                    |  332 |       33 |  0.105 |               0.524 |         0.409 |
| kr_intangiblesToTotalAssets_own LOW |  911 |       97 |  0.109 |               0.547 |         0.356 |
| kr_assetTurnover LOW                |  642 |       73 |  0.113 |               0.567 |         0.171 |
| ps_vs_own HIGH                      |  243 |       28 |  0.114 |               0.571 |         0.367 |
| kr_grossProfitMargin HIGH           |  514 |       58 |  0.116 |               0.58  |         0.389 |
| cfo_ni LOW                          |  575 |       72 |  0.116 |               0.581 |         0.302 |
| kr_priceToSalesRatio_own HIGH       |  261 |       32 |  0.116 |               0.581 |         0.261 |
| npm HIGH                            |  417 |       45 |  0.118 |               0.59  |         0.295 |
| ncav_mcap HIGH                      | 1576 |      209 |  0.12  |               0.6   |         0.226 |

### 2. Timing inside the bottoming process


*low_age*

| low_age   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| <2m       | 2033 |      549 |  0.269 |               1.346 |         0.353 |         0.086 |
| 2-6m      | 1227 |      293 |  0.239 |               1.194 |         0.302 |         0.069 |
| 6-12m     |  794 |      164 |  0.207 |               1.033 |         0.244 |         0.049 |
| 1-2y      |  693 |       78 |  0.108 |               0.542 |         0.305 |         0.013 |
| >2y       | 1354 |      136 |  0.102 |               0.508 |         0.363 |         0.032 |

*dd_time*

| dd_time   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| >80%      | 3993 |      852 |  0.214 |               1.07  |         0.323 |         0.066 |
| 50-80%    | 1287 |      231 |  0.178 |               0.888 |         0.366 |         0.07  |
| <50%      |  537 |       90 |  0.166 |               0.83  |         0.305 |         0.037 |

*r13_sign*

| r13_sign   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:-----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| 13w down   | 4184 |      844 |  0.202 |               1.012 |         0.344 |         0.063 |
| 13w up     | 1917 |      376 |  0.195 |               0.975 |         0.283 |         0.056 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|-----:|---------:|-------:|--------------------:|--------------:|
| bear (<-15%) |  640 |      282 |  0.451 |               2.258 |         0.099 |
| bull (>+15%) |  567 |      144 |  0.258 |               1.289 |         0.225 |
| weak         |  893 |      193 |  0.221 |               1.104 |         0.269 |
| firm         | 1761 |      278 |  0.151 |               0.755 |         0.374 |
| flat         | 2240 |      323 |  0.142 |               0.71  |         0.404 |

|   year |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|-----:|---------:|-------:|--------------------:|--------------:|
|   2012 |  135 |       35 |  0.287 |               1.434 |         0.052 |
|   2013 |  104 |       16 |  0.156 |               0.783 |         0.239 |
|   2014 |  118 |        1 |  0.01  |               0.051 |         0.471 |
|   2015 |  232 |       12 |  0.051 |               0.256 |         0.408 |
|   2016 |  391 |       42 |  0.108 |               0.538 |         0.145 |
|   2017 |  285 |       12 |  0.033 |               0.165 |         0.244 |
|   2018 |  368 |       17 |  0.048 |               0.239 |         0.61  |
|   2019 |  588 |      132 |  0.213 |               1.066 |         0.69  |
|   2020 | 1289 |      626 |  0.497 |               2.486 |         0.121 |
|   2021 |  398 |       40 |  0.104 |               0.522 |         0.302 |
|   2022 |  733 |       57 |  0.08  |               0.398 |         0.309 |
|   2023 |  726 |       67 |  0.087 |               0.433 |         0.351 |
|   2024 |  567 |      104 |  0.16  |               0.801 |         0.41  |
|   2025 |  151 |       56 |  0.343 |               1.715 |         0.411 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|----:|---------:|-------:|--------------------:|--------------:|
| Materials              | 302 |      119 |  0.385 |               1.927 |         0.375 |
| Communication Services | 475 |      122 |  0.242 |               1.212 |         0.352 |
| Information Technology | 589 |      135 |  0.234 |               1.169 |         0.273 |
| Industrials            | 513 |      112 |  0.226 |               1.131 |         0.32  |
| Energy                 | 673 |      133 |  0.211 |               1.054 |         0.305 |
| Consumer Discretionary | 873 |      160 |  0.183 |               0.915 |         0.391 |
| Real Estate            | 193 |       22 |  0.114 |               0.572 |         0.111 |
| Financials             | 487 |       44 |  0.087 |               0.436 |         0.235 |

*market*

| market   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|-----:|---------:|-------:|--------------------:|--------------:|
| US       | 6101 |     1220 |    0.2 |                   1 |         0.325 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition                 |    n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:--------------------------|-----:|-------:|--------------------:|--------------:|----------------:|
| wks_since_hi52 LOW        |  195 |  0.241 |               1.203 |         0.184 |          -0.141 |
| kr_payablesTurnover HIGH  | 1313 |  0.204 |               1.021 |         0.215 |          -0.11  |
| updown26 HIGH             |  676 |  0.225 |               1.127 |         0.219 |          -0.106 |
| gap_perc_buyshare HIGH    |  364 |  0.234 |               1.172 |         0.22  |          -0.105 |
| n_analysts LOW            |  867 |  0.27  |               1.349 |         0.231 |          -0.094 |
| dvol_usd_log HIGH         |  459 |  0.218 |               1.089 |         0.243 |          -0.083 |
| tr_gm_consist LOW         | 1268 |  0.219 |               1.096 |         0.246 |          -0.079 |
| dvol_z13 HIGH             |  388 |  0.215 |               1.073 |         0.246 |          -0.079 |
| gap_trend_roic LOW        |  479 |  0.211 |               1.054 |         0.248 |          -0.077 |
| kr_capexToRevenue_own LOW | 1423 |  0.205 |               1.027 |         0.25  |          -0.075 |

*Among the archetype's 3x winners, P(10x within 5y) = 25.0%; conditions that raise it:*

| condition                                  |   n |   p_10x_given_3x |
|:-------------------------------------------|----:|-----------------:|
| fcf_margin HIGH                            |  73 |            0.452 |
| kr_freeCashFlowPerShare_g4 LOW             | 108 |            0.417 |
| kr_capitalExpenditureCoverageRatio_d4 LOW  | 218 |            0.399 |
| months_since_up HIGH                       | 187 |            0.396 |
| roic_d1 HIGH                               | 161 |            0.391 |
| kr_quickRatio LOW                          | 175 |            0.389 |
| kr_capitalExpenditureCoverageRatio_own LOW | 171 |            0.386 |
| tr_debt_slope8 LOW                         | 184 |            0.386 |
| kr_ebitdaMargin HIGH                       | 121 |            0.372 |
| kr_capexToOperatingCashFlow_own LOW        | 122 |            0.369 |

## fallen_below_cycle  (rate 9.18%, lift 2.15x, blow-up 18%)

### 1. Refinements that RAISE the odds inside the archetype

| condition              |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| buy_share_d12 LOW      | 1463 |      315 |  0.21  |               2.291 |         0.236 |
| gap_perc_buyshare LOW  | 1348 |      220 |  0.153 |               1.664 |         0.239 |
| buy_share LOW          | 2609 |      393 |  0.152 |               1.655 |         0.261 |
| gap_perc_buyshare HIGH |  635 |      100 |  0.152 |               1.653 |         0.17  |
| n_analysts LOW         | 2128 |      337 |  0.151 |               1.647 |         0.247 |
| ins_net_buy_4q HIGH    | 3525 |      507 |  0.146 |               1.589 |         0.294 |
| insider_buying         | 3511 |      505 |  0.145 |               1.583 |         0.274 |
| net_net                | 1966 |      311 |  0.144 |               1.574 |         0.133 |
| buy_share HIGH         | 2282 |      327 |  0.14  |               1.524 |         0.249 |
| buy_share_d12 HIGH     | 1005 |      140 |  0.135 |               1.475 |         0.264 |
| tr_fcfm_streak LOW     | 2184 |      280 |  0.133 |               1.452 |         0.106 |
| rev_per_emp_g1 LOW     | 4437 |      574 |  0.133 |               1.444 |         0.321 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                                   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:--------------------------------------------|------:|---------:|-------:|--------------------:|--------------:|
| kr_researchAndDevelopementToRevenue LOW     |  6812 |      374 |  0.052 |               0.567 |         0.16  |
| maxdd104 HIGH                               |  1529 |       89 |  0.054 |               0.59  |         0.116 |
| tr_opm_streak LOW                           |  1716 |       96 |  0.055 |               0.596 |         0.207 |
| kr_researchAndDevelopementToRevenue_own LOW |  7245 |      443 |  0.057 |               0.62  |         0.134 |
| vol52 LOW                                   |  9289 |      638 |  0.058 |               0.629 |         0.075 |
| range104 LOW                                |  6338 |      467 |  0.059 |               0.646 |         0.088 |
| roic HIGH                                   |  5394 |      345 |  0.06  |               0.656 |         0.135 |
| kr_grossProfitMargin HIGH                   | 12625 |      835 |  0.061 |               0.661 |         0.155 |
| kr_daysOfInventoryOutstanding LOW           | 12037 |      767 |  0.061 |               0.665 |         0.158 |
| gm HIGH                                     | 13124 |      889 |  0.062 |               0.68  |         0.149 |
| opm HIGH                                    |  6537 |      484 |  0.063 |               0.681 |         0.115 |
| wks_since_lo260 HIGH                        |  8404 |      567 |  0.063 |               0.682 |         0.173 |

### 2. Timing inside the bottoming process


*low_age*

| low_age   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| 6-12m     |  9993 |     1256 |  0.119 |               1.298 |         0.15  |         0.021 |
| <2m       | 17210 |     2092 |  0.118 |               1.29  |         0.196 |         0.024 |
| 2-6m      | 14319 |     1677 |  0.115 |               1.248 |         0.163 |         0.022 |
| 1-2y      |  7847 |      616 |  0.071 |               0.774 |         0.165 |         0.011 |
| >2y       | 27213 |     1589 |  0.056 |               0.613 |         0.195 |         0.01  |

*dd_time*

| dd_time   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| >80%      | 46705 |     4832 |  0.102 |               1.112 |         0.177 |         0.019 |
| 50-80%    | 19229 |     1541 |  0.079 |               0.865 |         0.205 |         0.014 |
| <50%      |  5442 |      324 |  0.056 |               0.613 |         0.192 |         0.017 |

*r13_sign*

| r13_sign   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:-----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| 13w down   | 50637 |     4776 |  0.092 |               1.002 |         0.184 |         0.018 |
| 13w up     | 25945 |     2454 |  0.091 |               0.996 |         0.172 |         0.017 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|------:|---------:|-------:|--------------------:|--------------:|
| bull (>+15%) |  6326 |      767 |  0.122 |               1.333 |         0.162 |
| bear (<-15%) |  9684 |     1102 |  0.122 |               1.332 |         0.09  |
| weak         | 18161 |     1673 |  0.091 |               0.989 |         0.152 |
| flat         | 26446 |     2395 |  0.084 |               0.914 |         0.212 |
| firm         | 15965 |     1293 |  0.076 |               0.831 |         0.217 |

|   year |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|------:|---------:|-------:|--------------------:|--------------:|
|   2012 |  2555 |      265 |  0.103 |               1.118 |         0.062 |
|   2013 |  4347 |      983 |  0.212 |               2.313 |         0.108 |
|   2014 |  3203 |      528 |  0.145 |               1.578 |         0.213 |
|   2015 |  3195 |      176 |  0.052 |               0.564 |         0.235 |
|   2016 |  5391 |      315 |  0.057 |               0.624 |         0.168 |
|   2017 |  4805 |       73 |  0.013 |               0.139 |         0.318 |
|   2018 |  5938 |      246 |  0.043 |               0.467 |         0.289 |
|   2019 |  7926 |      658 |  0.084 |               0.919 |         0.251 |
|   2020 | 10600 |     1700 |  0.168 |               1.831 |         0.071 |
|   2021 |  5597 |      324 |  0.052 |               0.568 |         0.134 |
|   2022 |  7510 |      340 |  0.046 |               0.498 |         0.174 |
|   2023 |  7747 |      230 |  0.03  |               0.33  |         0.201 |
|   2024 |  6990 |      932 |  0.125 |               1.365 |         0.15  |
|   2025 |   723 |      445 |  0.59  |               6.423 |         0.37  |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|------:|---------:|-------:|--------------------:|--------------:|
| Energy                 |  2458 |      367 |  0.16  |               1.742 |         0.266 |
| Materials              | 11759 |     1401 |  0.117 |               1.274 |         0.157 |
| Information Technology | 10599 |     1225 |  0.113 |               1.226 |         0.171 |
| Industrials            | 15670 |     1468 |  0.091 |               0.989 |         0.147 |
| Real Estate            |  3003 |      261 |  0.081 |               0.883 |         0.217 |
| Consumer Discretionary | 10670 |      893 |  0.078 |               0.847 |         0.173 |
| Financials             |  4312 |      339 |  0.073 |               0.793 |         0.165 |
| Health Care            |  1513 |      111 |  0.066 |               0.718 |         0.255 |
| Communication Services |  3878 |      243 |  0.064 |               0.702 |         0.22  |
| Consumer Staples       |  4337 |      200 |  0.045 |               0.492 |         0.166 |
| Utilities              |  1629 |       53 |  0.031 |               0.337 |         0.106 |

*market*

| market   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|------:|---------:|-------:|--------------------:|--------------:|
| IS       |   267 |       83 |  0.336 |               3.656 |         0.059 |
| TWO      |   474 |       65 |  0.167 |               1.819 |         0.1   |
| NS       |  1561 |      275 |  0.162 |               1.769 |         0.19  |
| TO       |  1968 |      276 |  0.138 |               1.502 |         0.374 |
| OL       |   214 |       26 |  0.127 |               1.388 |         0.189 |
| US       | 14881 |     1774 |  0.118 |               1.28  |         0.28  |
| TW       |  2600 |      248 |  0.097 |               1.055 |         0.15  |
| DE       |   900 |       79 |  0.093 |               1.013 |         0.146 |
| SZ       | 21067 |     2005 |  0.09  |               0.978 |         0.126 |
| SI       |   347 |       28 |  0.084 |               0.916 |         0.193 |
| CO       |   161 |       13 |  0.081 |               0.88  |         0.093 |
| SS       | 13719 |     1121 |  0.08  |               0.867 |         0.105 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition             |     n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:----------------------|------:|-------:|--------------------:|--------------:|----------------:|
| tr_fcfm_streak LOW    |  2184 |  0.133 |               1.452 |         0.106 |          -0.074 |
| gap_own_fcfps LOW     |  2705 |  0.103 |               1.119 |         0.123 |          -0.057 |
| net_net               |  1966 |  0.144 |               1.574 |         0.133 |          -0.047 |
| dvol_usd_log LOW      | 18457 |  0.111 |               1.206 |         0.138 |          -0.042 |
| tr_shares_consist LOW | 13439 |  0.102 |               1.106 |         0.14  |          -0.039 |
| accumulation          |  2399 |  0.109 |               1.182 |         0.147 |          -0.033 |
| eps_g1 HIGH           |  3278 |  0.101 |               1.095 |         0.151 |          -0.029 |
| ebit_g1 HIGH          |  2813 |  0.099 |               1.082 |         0.155 |          -0.025 |
| cannibal              | 12918 |  0.095 |               1.035 |         0.159 |          -0.021 |
| tr_roic_consist HIGH  |  2875 |  0.099 |               1.077 |         0.16  |          -0.02  |

*Among the archetype's 3x winners, P(10x within 5y) = 10.9%; conditions that raise it:*

| condition              |   n |   p_10x_given_3x |
|:-----------------------|----:|-----------------:|
| months_since_up HIGH   | 294 |            0.252 |
| tr_opm_streak LOW      |  66 |            0.242 |
| react_beats_mean HIGH  | 435 |            0.241 |
| ignored_beats_2y LOW   | 427 |            0.241 |
| tr_roic_streak LOW     | 139 |            0.23  |
| bo_increasing_12m HIGH | 253 |            0.225 |
| emp_g1 LOW             | 417 |            0.223 |
| n_analysts LOW         | 194 |            0.216 |
| beats_4q LOW           | 757 |            0.21  |
| surprise_4q LOW        | 957 |            0.204 |

## margin_inflect_weak_tape  (rate 4.87%, lift 1.14x, blow-up 17%)

### 1. Refinements that RAISE the odds inside the archetype

| condition                      |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------|------:|---------:|-------:|--------------------:|--------------:|
| tr_gm_streak LOW               |   501 |       52 |  0.096 |               1.97  |         0.127 |
| evs_chg_1y HIGH                |  1143 |       92 |  0.084 |               1.727 |         0.126 |
| earn_yield LOW                 |  6373 |      551 |  0.082 |               1.682 |         0.272 |
| npm LOW                        |  6666 |      563 |  0.081 |               1.661 |         0.252 |
| opm LOW                        |  5823 |      486 |  0.079 |               1.622 |         0.241 |
| kr_operatingProfitMargin LOW   |  6890 |      554 |  0.079 |               1.622 |         0.23  |
| mcap_usd_log LOW               |  9428 |      770 |  0.078 |               1.593 |         0.195 |
| roic LOW                       |  5680 |      463 |  0.077 |               1.58  |         0.256 |
| fallen_angel                   | 12127 |      951 |  0.077 |               1.576 |         0.208 |
| kr_bottomLineProfitMargin LOW  |  7752 |      605 |  0.077 |               1.572 |         0.24  |
| fund_price_divergence          |  7813 |      635 |  0.076 |               1.56  |         0.183 |
| kr_operatingReturnOnAssets LOW |  6547 |      508 |  0.076 |               1.56  |         0.224 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                                  |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| sbc_rev LOW                                | 2772 |       64 |  0.02  |               0.41  |         0.193 |
| upgrades_12m HIGH                          | 2045 |       55 |  0.023 |               0.468 |         0.242 |
| kr_stockBasedCompensationToRevenue_own LOW | 2971 |       81 |  0.027 |               0.559 |         0.215 |
| downgrades_12m HIGH                        | 1964 |       61 |  0.028 |               0.566 |         0.238 |
| flat_base                                  | 9923 |      368 |  0.028 |               0.567 |         0.129 |
| months_since_up LOW                        | 1724 |       53 |  0.029 |               0.603 |         0.248 |
| vol52 LOW                                  | 4790 |      187 |  0.032 |               0.661 |         0.072 |
| mcap_usd_log HIGH                          | 8232 |      314 |  0.032 |               0.666 |         0.139 |
| kr_freeCashFlowPerShare_g4 HIGH            | 4056 |      152 |  0.033 |               0.679 |         0.167 |
| kr_stockBasedCompensationToRevenue LOW     | 2875 |      100 |  0.034 |               0.688 |         0.191 |
| ignored_beats_2y LOW                       | 2648 |      108 |  0.035 |               0.724 |         0.242 |
| ins_net_buy_4q LOW                         | 1775 |       65 |  0.036 |               0.733 |         0.184 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|------:|---------:|-------:|--------------------:|--------------:|
| bull (>+15%) |  1591 |      161 |  0.095 |               1.948 |         0.187 |
| bear (<-15%) |  7544 |      467 |  0.063 |               1.295 |         0.081 |
| weak         | 13002 |      662 |  0.047 |               0.962 |         0.151 |
| firm         |  7374 |      377 |  0.046 |               0.934 |         0.18  |
| flat         | 15035 |      688 |  0.04  |               0.828 |         0.207 |

|   year |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|-----:|---------:|-------:|--------------------:|--------------:|
|   2012 | 1219 |       63 |  0.055 |               1.126 |         0.043 |
|   2013 |  866 |      181 |  0.18  |               3.688 |         0.074 |
|   2014 | 1298 |      119 |  0.073 |               1.496 |         0.221 |
|   2015 | 2095 |       67 |  0.03  |               0.62  |         0.156 |
|   2016 | 2579 |       79 |  0.029 |               0.604 |         0.112 |
|   2017 | 2824 |       35 |  0.014 |               0.288 |         0.303 |
|   2018 | 6963 |      215 |  0.032 |               0.65  |         0.262 |
|   2019 | 3742 |      292 |  0.071 |               1.461 |         0.281 |
|   2020 | 2688 |      341 |  0.127 |               2.612 |         0.055 |
|   2021 | 2932 |      117 |  0.038 |               0.776 |         0.141 |
|   2022 | 9448 |      290 |  0.027 |               0.561 |         0.112 |
|   2023 | 5031 |      153 |  0.026 |               0.526 |         0.149 |
|   2024 | 2624 |      262 |  0.087 |               1.776 |         0.1   |
|   2025 |  215 |      130 |  0.544 |              11.161 |         0.085 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| Health Care            |  966 |       88 |  0.079 |               1.621 |         0.185 |
| Information Technology | 6360 |      498 |  0.074 |               1.51  |         0.142 |
| Industrials            | 9436 |      503 |  0.051 |               1.043 |         0.111 |
| Utilities              |  700 |       50 |  0.05  |               1.016 |         0.077 |
| Materials              | 7262 |      360 |  0.049 |               1.005 |         0.158 |
| Consumer Discretionary | 6123 |      312 |  0.045 |               0.933 |         0.148 |
| Financials             | 2264 |      122 |  0.045 |               0.919 |         0.151 |
| Consumer Staples       | 2427 |      104 |  0.038 |               0.777 |         0.113 |
| Energy                 | 2012 |       64 |  0.029 |               0.603 |         0.429 |
| Communication Services | 1519 |       38 |  0.025 |               0.511 |         0.194 |
| Real Estate            | 1815 |       49 |  0.021 |               0.439 |         0.133 |

*market*

| market   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|-----:|---------:|-------:|--------------------:|--------------:|
| IS       |  300 |      112 |  0.381 |               7.808 |         0.067 |
| NS       | 1323 |      171 |  0.114 |               2.347 |         0.191 |
| KQ       |  570 |       70 |  0.113 |               2.327 |         0.216 |
| TWO      |  525 |       37 |  0.062 |               1.27  |         0.053 |
| TO       | 1194 |       70 |  0.059 |               1.206 |         0.348 |
| SZ       | 8213 |      481 |  0.056 |               1.157 |         0.157 |
| ST       |  645 |       40 |  0.056 |               1.149 |         0.127 |
| SR       |  433 |       30 |  0.055 |               1.129 |         0.111 |
| SS       | 5860 |      312 |  0.054 |               1.098 |         0.098 |
| TW       | 2229 |      124 |  0.052 |               1.057 |         0.085 |
| KS       | 2347 |      118 |  0.048 |               0.994 |         0.1   |
| DE       |  685 |       33 |  0.044 |               0.9   |         0.187 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition          |    n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:-------------------|-----:|-------:|--------------------:|--------------:|----------------:|
| dist_hi52 HIGH     | 1336 |  0.056 |               1.156 |         0.074 |          -0.091 |
| net_net            |  761 |  0.065 |               1.325 |         0.103 |          -0.062 |
| dist_hi260 HIGH    | 3021 |  0.059 |               1.211 |         0.107 |          -0.059 |
| gap_own_roic LOW   | 2419 |  0.051 |               1.049 |         0.117 |          -0.048 |
| netcash_mcap HIGH  | 8555 |  0.051 |               1.039 |         0.118 |          -0.047 |
| nd_ebitda LOW      | 6315 |  0.052 |               1.062 |         0.119 |          -0.046 |
| gap_own_gm LOW     | 3446 |  0.05  |               1.019 |         0.121 |          -0.045 |
| wks_since_hi52 LOW | 3267 |  0.059 |               1.207 |         0.126 |          -0.039 |
| evs_chg_1y HIGH    | 1143 |  0.084 |               1.727 |         0.126 |          -0.039 |
| tr_gm_streak LOW   |  501 |  0.096 |               1.97  |         0.127 |          -0.038 |

*Among the archetype's 3x winners, P(10x within 5y) = 14.3%; conditions that raise it:*

| condition                       |   n |   p_10x_given_3x |
|:--------------------------------|----:|-----------------:|
| asset_turn_d1 LOW               | 132 |            0.258 |
| deep_value                      | 457 |            0.254 |
| kr_assetTurnover_d4 LOW         | 203 |            0.251 |
| kr_freeCashFlowPerShare_g4 HIGH | 109 |            0.248 |
| tr_revg_slope8 LOW              | 151 |            0.238 |
| kr_cashConversionCycle_own HIGH | 260 |            0.223 |
| react_beats_mean LOW            | 126 |            0.222 |
| last_react LOW                  | 159 |            0.22  |
| slope_brk HIGH                  | 114 |            0.219 |
| react_beats_mean HIGH           | 105 |            0.219 |

## tree_recipe  (rate 14.43%, lift 3.38x, blow-up 27%)

### 1. Refinements that RAISE the odds inside the archetype

| condition              |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| tr_fcfm_streak LOW     |  326 |       86 |  0.272 |               1.888 |         0.18  |
| gap_perc_buyshare HIGH |  415 |      100 |  0.256 |               1.773 |         0.243 |
| n_analysts LOW         | 1818 |      450 |  0.244 |               1.688 |         0.385 |
| buy_share LOW          |  853 |      183 |  0.219 |               1.517 |         0.377 |
| ncav_mcap LOW          | 5651 |     1134 |  0.204 |               1.413 |         0.321 |
| sga_rev LOW            | 1983 |      394 |  0.2   |               1.388 |         0.296 |
| div_yield HIGH         | 2282 |      447 |  0.199 |               1.379 |         0.259 |
| buy_share HIGH         | 1749 |      356 |  0.199 |               1.378 |         0.387 |
| gap_perc_buyshare LOW  |  501 |       96 |  0.198 |               1.371 |         0.359 |
| netcash_mcap LOW       | 7085 |     1384 |  0.197 |               1.364 |         0.308 |
| fcf_yield HIGH         | 4023 |      781 |  0.192 |               1.331 |         0.249 |
| buy_share_d12 HIGH     |  493 |       91 |  0.191 |               1.325 |         0.389 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                               |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:----------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| tr_revg_streak LOW                      |  917 |       59 |  0.065 |               0.45  |         0.324 |
| flat_base                               | 1116 |       93 |  0.065 |               0.452 |         0.251 |
| wks_since_lo260 HIGH                    | 1265 |       82 |  0.068 |               0.469 |         0.212 |
| roe HIGH                                |  718 |       57 |  0.07  |               0.485 |         0.26  |
| gap_own_roic LOW                        |  513 |       44 |  0.078 |               0.539 |         0.173 |
| npm HIGH                                |  380 |       30 |  0.078 |               0.541 |         0.249 |
| cfo_ni LOW                              | 1528 |      131 |  0.08  |               0.555 |         0.269 |
| kr_researchAndDevelopementToRevenue LOW |  884 |       79 |  0.083 |               0.574 |         0.289 |
| eps_g1 HIGH                             | 1032 |       84 |  0.084 |               0.579 |         0.213 |
| gap_eps_1y LOW                          | 1734 |      138 |  0.084 |               0.579 |         0.208 |
| eps_g1 LOW                              | 2467 |      205 |  0.085 |               0.591 |         0.201 |
| ev_ebit HIGH                            | 3127 |      272 |  0.085 |               0.592 |         0.244 |

### 2. Timing inside the bottoming process


*low_age*

| low_age   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|-----:|---------:|-------:|--------------------:|--------------:|--------------:|
| <2m       | 4556 |      924 |  0.204 |               1.415 |         0.342 |         0.059 |
| 2-6m      | 3408 |      653 |  0.192 |               1.333 |         0.279 |         0.058 |
| 6-12m     | 2954 |      486 |  0.165 |               1.141 |         0.242 |         0.043 |
| 1-2y      | 3415 |      433 |  0.125 |               0.864 |         0.244 |         0.044 |
| >2y       | 7437 |      611 |  0.083 |               0.574 |         0.256 |         0.02  |

*dd_time*

| dd_time   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| >80%      | 15485 |     2327 |  0.153 |               1.061 |         0.278 |         0.04  |
| 50-80%    |  4295 |      514 |  0.119 |               0.824 |         0.277 |         0.046 |
| <50%      |  1007 |       93 |  0.093 |               0.644 |         0.309 |         0.057 |

*r13_sign*

| r13_sign   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |   t10_60_rate |
|:-----------|------:|---------:|-------:|--------------------:|--------------:|--------------:|
| 13w up     |  7791 |     1120 |  0.144 |                   1 |         0.25  |         0.041 |
| 13w down   | 13979 |     1987 |  0.144 |                   1 |         0.288 |         0.043 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|-----:|---------:|-------:|--------------------:|--------------:|
| bear (<-15%) | 1369 |      388 |  0.299 |               2.07  |         0.144 |
| bull (>+15%) | 2525 |      442 |  0.181 |               1.254 |         0.213 |
| weak         | 3395 |      547 |  0.168 |               1.163 |         0.235 |
| flat         | 7655 |      932 |  0.122 |               0.845 |         0.325 |
| firm         | 6826 |      798 |  0.114 |               0.789 |         0.285 |

|   year |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|-----:|---------:|-------:|--------------------:|--------------:|
|   2012 |  662 |      130 |  0.196 |               1.359 |         0.085 |
|   2013 | 1187 |      194 |  0.149 |               1.031 |         0.15  |
|   2014 | 1125 |       63 |  0.054 |               0.374 |         0.324 |
|   2015 | 1290 |      111 |  0.085 |               0.591 |         0.251 |
|   2016 | 1468 |      159 |  0.104 |               0.721 |         0.15  |
|   2017 | 1616 |       66 |  0.035 |               0.243 |         0.343 |
|   2018 | 1811 |      107 |  0.056 |               0.388 |         0.453 |
|   2019 | 2112 |      413 |  0.206 |               1.427 |         0.4   |
|   2020 | 2295 |      820 |  0.382 |               2.649 |         0.115 |
|   2021 | 2041 |      189 |  0.097 |               0.673 |         0.224 |
|   2022 | 1960 |      186 |  0.098 |               0.681 |         0.265 |
|   2023 | 1867 |      126 |  0.062 |               0.431 |         0.32  |
|   2024 | 1886 |      331 |  0.169 |               1.172 |         0.328 |
|   2025 |  397 |      202 |  0.502 |               3.476 |         0.484 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| Materials              | 1666 |      324 |  0.184 |               1.276 |         0.25  |
| Energy                 | 1024 |      182 |  0.178 |               1.233 |         0.316 |
| Information Technology | 4066 |      608 |  0.152 |               1.056 |         0.242 |
| Communication Services | 1445 |      211 |  0.152 |               1.056 |         0.34  |
| Industrials            | 4064 |      568 |  0.148 |               1.027 |         0.211 |
| Financials             |  893 |      118 |  0.141 |               0.977 |         0.286 |
| Consumer Staples       |  895 |      119 |  0.136 |               0.939 |         0.234 |
| Health Care            |  372 |       53 |  0.12  |               0.832 |         0.271 |
| Consumer Discretionary | 3401 |      394 |  0.118 |               0.816 |         0.27  |
| Real Estate            |  440 |       29 |  0.066 |               0.459 |         0.196 |

*market*

| market   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|-----:|---------:|-------:|--------------------:|--------------:|
| TO       |  515 |      133 |  0.253 |               1.753 |         0.46  |
| TWO      |  165 |       29 |  0.222 |               1.541 |         0.046 |
| SR       |  180 |       37 |  0.219 |               1.515 |         0.276 |
| NS       |  906 |      198 |  0.214 |               1.482 |         0.197 |
| MC       |  193 |       42 |  0.194 |               1.345 |         0.111 |
| SA       |  250 |       37 |  0.175 |               1.216 |         0.337 |
| ST       |  319 |       65 |  0.173 |               1.199 |         0.333 |
| SS       | 1048 |      160 |  0.165 |               1.14  |         0.203 |
| DE       |  300 |       46 |  0.164 |               1.134 |         0.028 |
| SZ       | 1496 |      224 |  0.155 |               1.073 |         0.18  |
| US       | 9544 |     1468 |  0.153 |               1.061 |         0.361 |
| TW       |  918 |      104 |  0.121 |               0.835 |         0.097 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition                               |    n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:----------------------------------------|-----:|-------:|--------------------:|--------------:|----------------:|
| gap_own_gm LOW                          |  384 |  0.148 |               1.024 |         0.137 |          -0.137 |
| pos104 HIGH                             |  194 |  0.148 |               1.027 |         0.157 |          -0.117 |
| net_net                                 | 1078 |  0.156 |               1.083 |         0.174 |          -0.1   |
| tr_fcfm_streak LOW                      |  326 |  0.272 |               1.888 |         0.18  |          -0.094 |
| kr_dividendPayoutRatio_d4 HIGH          | 2188 |  0.148 |               1.026 |         0.215 |          -0.06  |
| kr_capitalExpenditureCoverageRatio HIGH | 3181 |  0.151 |               1.049 |         0.215 |          -0.059 |
| wks_since_hi52 LOW                      | 1066 |  0.158 |               1.094 |         0.224 |          -0.05  |
| kr_dividendPayoutRatio_d4 LOW           | 2278 |  0.154 |               1.065 |         0.224 |          -0.05  |
| kr_earningsYield HIGH                   | 2350 |  0.156 |               1.084 |         0.229 |          -0.046 |
| gap_own_fcfps LOW                       |  399 |  0.155 |               1.076 |         0.234 |          -0.041 |

*Among the archetype's 3x winners, P(10x within 5y) = 19.8%; conditions that raise it:*

| condition                           |   n |   p_10x_given_3x |
|:------------------------------------|----:|-----------------:|
| gap_perc_buyshare HIGH              |  70 |            0.4   |
| ev_ebit LOW                         | 143 |            0.378 |
| sbc_rev LOW                         | 261 |            0.349 |
| buy_share LOW                       | 141 |            0.34  |
| react_beats_mean HIGH               | 375 |            0.328 |
| ignored_beats_2y LOW                | 395 |            0.327 |
| kr_workingCapitalTurnoverRatio HIGH | 470 |            0.323 |
| pe LOW                              | 177 |            0.322 |
| tr_fcfm_streak LOW                  |  69 |            0.319 |
| buy_share_d12 LOW                   |  77 |            0.299 |

## tree_recipe_10x  (rate 12.65%, lift 2.97x, blow-up 22%)

### 1. Refinements that RAISE the odds inside the archetype

| condition              |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| tr_fcfm_streak LOW     |  381 |       89 |  0.247 |               1.951 |         0.13  |
| gap_perc_buyshare HIGH |  535 |      122 |  0.232 |               1.831 |         0.203 |
| buy_share LOW          |  825 |      177 |  0.218 |               1.724 |         0.335 |
| n_analysts LOW         | 2034 |      425 |  0.208 |               1.646 |         0.293 |
| buy_share_d12 LOW      |  501 |       99 |  0.193 |               1.527 |         0.299 |
| ncav_mcap LOW          | 6465 |     1215 |  0.191 |               1.511 |         0.29  |
| fund_price_divergence  | 4089 |      776 |  0.188 |               1.49  |         0.28  |
| buy_share HIGH         | 1960 |      358 |  0.184 |               1.458 |         0.319 |
| gap_perc_buyshare LOW  |  510 |       89 |  0.184 |               1.457 |         0.307 |
| netcash_mcap LOW       | 9020 |     1585 |  0.178 |               1.409 |         0.275 |
| capex_rev HIGH         | 2709 |      482 |  0.176 |               1.395 |         0.279 |
| buy_share_d12 HIGH     |  548 |       88 |  0.173 |               1.37  |         0.319 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                               |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:----------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| dd_time_share_260 LOW                   |  399 |       25 |  0.055 |               0.431 |         0.203 |
| tr_revg_streak LOW                      | 1104 |       62 |  0.058 |               0.462 |         0.275 |
| flat_base                               | 1995 |      166 |  0.063 |               0.498 |         0.204 |
| kr_researchAndDevelopementToRevenue LOW |  900 |       72 |  0.067 |               0.527 |         0.205 |
| wks_since_lo260 HIGH                    | 2134 |      146 |  0.07  |               0.554 |         0.159 |
| equity_assets HIGH                      | 4094 |      312 |  0.071 |               0.562 |         0.209 |
| roe HIGH                                | 1490 |      108 |  0.072 |               0.572 |         0.19  |
| kr_debtToAssetsRatio LOW                | 3971 |      311 |  0.073 |               0.575 |         0.177 |
| kr_interestCoverageRatio HIGH           | 2504 |      197 |  0.074 |               0.583 |         0.212 |
| nd_ebitda LOW                           | 3538 |      276 |  0.074 |               0.584 |         0.14  |
| dist_hi260 HIGH                         |  594 |       44 |  0.079 |               0.625 |         0.194 |
| ins_net_buy_4q LOW                      |  629 |       52 |  0.081 |               0.642 |         0.241 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|-----:|---------:|-------:|--------------------:|--------------:|
| bear (<-15%) | 1652 |      382 |  0.246 |               1.945 |         0.118 |
| bull (>+15%) | 3306 |      479 |  0.149 |               1.177 |         0.179 |
| weak         | 4231 |      598 |  0.145 |               1.146 |         0.197 |
| flat         | 9281 |     1066 |  0.115 |               0.906 |         0.263 |
| firm         | 8379 |      852 |  0.099 |               0.783 |         0.234 |

|   year |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|-----:|---------:|-------:|--------------------:|--------------:|
|   2012 |  970 |      177 |  0.183 |               1.449 |         0.056 |
|   2013 | 1679 |      228 |  0.121 |               0.953 |         0.117 |
|   2014 | 1551 |       95 |  0.057 |               0.452 |         0.208 |
|   2015 | 1758 |      131 |  0.075 |               0.595 |         0.192 |
|   2016 | 1931 |      226 |  0.114 |               0.897 |         0.159 |
|   2017 | 2049 |       75 |  0.033 |               0.259 |         0.303 |
|   2018 | 2136 |       82 |  0.039 |               0.307 |         0.449 |
|   2019 | 2488 |      436 |  0.178 |               1.409 |         0.364 |
|   2020 | 2562 |      829 |  0.343 |               2.714 |         0.092 |
|   2021 | 2489 |      217 |  0.093 |               0.735 |         0.174 |
|   2022 | 2420 |      252 |  0.11  |               0.87  |         0.196 |
|   2023 | 2301 |      200 |  0.079 |               0.627 |         0.227 |
|   2024 | 2104 |      255 |  0.114 |               0.905 |         0.265 |
|   2025 |  351 |      163 |  0.47  |               3.719 |         0.324 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| Energy                 |  830 |      165 |  0.2   |               1.582 |         0.272 |
| Health Care            |  292 |       46 |  0.149 |               1.181 |         0.323 |
| Financials             |  732 |       97 |  0.143 |               1.13  |         0.259 |
| Materials              | 2799 |      392 |  0.138 |               1.09  |         0.217 |
| Communication Services | 1205 |      161 |  0.135 |               1.07  |         0.376 |
| Information Technology | 4312 |      577 |  0.135 |               1.07  |         0.18  |
| Industrials            | 5609 |      701 |  0.13  |               1.026 |         0.18  |
| Consumer Discretionary | 4702 |      545 |  0.116 |               0.915 |         0.211 |
| Consumer Staples       | 1723 |      169 |  0.097 |               0.77  |         0.179 |
| Real Estate            |  399 |       32 |  0.076 |               0.599 |         0.173 |

*market*

| market   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|------:|---------:|-------:|--------------------:|--------------:|
| IS       |   155 |       53 |  0.353 |               2.788 |         0.059 |
| JK       |   164 |       35 |  0.224 |               1.768 |         0.195 |
| TO       |   641 |      144 |  0.217 |               1.712 |         0.418 |
| NS       |  1795 |      369 |  0.207 |               1.638 |         0.198 |
| DE       |   346 |       53 |  0.152 |               1.198 |         0.02  |
| MI       |   161 |       21 |  0.151 |               1.194 |         0.135 |
| KQ       |   217 |       33 |  0.144 |               1.142 |         0.168 |
| MC       |   290 |       44 |  0.136 |               1.079 |         0.082 |
| US       | 10724 |     1443 |  0.133 |               1.048 |         0.302 |
| SA       |   398 |       45 |  0.126 |               0.997 |         0.313 |
| SI       |   276 |       31 |  0.124 |               0.983 |         0.173 |
| SS       |  1460 |      170 |  0.124 |               0.981 |         0.126 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition                               |     n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:----------------------------------------|------:|-------:|--------------------:|--------------:|----------------:|
| tr_fcfm_streak LOW                      |   381 |  0.247 |               1.951 |         0.13  |          -0.095 |
| net_net                                 |  1400 |  0.143 |               1.131 |         0.134 |          -0.091 |
| trend_r2_52 HIGH                        |  2497 |  0.13  |               1.026 |         0.162 |          -0.062 |
| kr_earningsYield HIGH                   |  4517 |  0.136 |               1.079 |         0.184 |          -0.04  |
| accumulation                            |  3185 |  0.127 |               1.001 |         0.185 |          -0.04  |
| gap_trend_opm LOW                       |  4261 |  0.13  |               1.029 |         0.189 |          -0.035 |
| kr_capitalExpenditureCoverageRatio HIGH |  4239 |  0.134 |               1.063 |         0.196 |          -0.029 |
| dvol_usd_log LOW                        | 13402 |  0.133 |               1.055 |         0.197 |          -0.028 |
| tr_debt_streak LOW                      |   517 |  0.169 |               1.336 |         0.201 |          -0.024 |
| gap_perc_buyshare HIGH                  |   535 |  0.232 |               1.831 |         0.203 |          -0.021 |

*Among the archetype's 3x winners, P(10x within 5y) = 21.2%; conditions that raise it:*

| condition                      |   n |   p_10x_given_3x |
|:-------------------------------|----:|-----------------:|
| gap_perc_buyshare HIGH         |  69 |            0.391 |
| buy_share LOW                  | 140 |            0.336 |
| buy_share_d12 LOW              |  72 |            0.319 |
| tr_gm_streak HIGH              | 382 |            0.317 |
| react_beats_mean HIGH          | 391 |            0.312 |
| tr_gm_consist HIGH             | 305 |            0.305 |
| buy_share HIGH                 | 220 |            0.305 |
| kr_freeCashFlowYield_own LOW   | 475 |            0.303 |
| sbc_rev LOW                    | 283 |            0.3   |
| kr_freeCashFlowPerShare_g4 LOW | 181 |            0.298 |

## sequence_preignition  (rate 6.39%, lift 1.50x, blow-up 16%)

### 1. Refinements that RAISE the odds inside the archetype

| condition                     |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:------------------------------|------:|---------:|-------:|--------------------:|--------------:|
| net_net                       |  1976 |      222 |  0.109 |               1.703 |         0.084 |
| mcap_usd_log LOW              | 23326 |     2312 |  0.095 |               1.482 |         0.168 |
| fund_price_divergence         | 16059 |     1566 |  0.091 |               1.423 |         0.163 |
| fallen_angel                  | 28859 |     2687 |  0.09  |               1.403 |         0.178 |
| gap_perc_buyshare LOW         |   778 |       86 |  0.089 |               1.399 |         0.171 |
| vol52 HIGH                    | 22645 |     2051 |  0.089 |               1.393 |         0.248 |
| opm LOW                       | 21472 |     1945 |  0.087 |               1.364 |         0.198 |
| npm LOW                       | 21385 |     1919 |  0.086 |               1.34  |         0.207 |
| kr_ebitdaMargin LOW           | 19210 |     1710 |  0.084 |               1.314 |         0.189 |
| tr_gm_streak LOW              |   937 |       84 |  0.084 |               1.307 |         0.163 |
| kr_pretaxProfitMargin LOW     | 21599 |     1891 |  0.083 |               1.304 |         0.207 |
| kr_bottomLineProfitMargin LOW | 22050 |     1915 |  0.083 |               1.303 |         0.206 |

### ...and conditions to AVOID (lowest conditional lift)

| condition                                  |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|------:|---------:|-------:|--------------------:|--------------:|
| kr_stockBasedCompensationToRevenue_own LOW |  5357 |      216 |  0.035 |               0.555 |         0.191 |
| upgrades_12m HIGH                          |  3387 |      130 |  0.036 |               0.557 |         0.202 |
| kr_stockBasedCompensationToRevenue LOW     |  5575 |      227 |  0.036 |               0.56  |         0.17  |
| months_since_up LOW                        |  2827 |      113 |  0.037 |               0.585 |         0.202 |
| tr_opm_streak LOW                          |  1818 |       75 |  0.039 |               0.614 |         0.161 |
| productivity_gain                          |  5823 |      253 |  0.04  |               0.62  |         0.227 |
| tr_shares_streak LOW                       |   878 |       34 |  0.04  |               0.624 |         0.158 |
| mcap_usd_log HIGH                          | 12540 |      633 |  0.042 |               0.656 |         0.123 |
| tr_revg_streak LOW                         |  3696 |      194 |  0.043 |               0.667 |         0.243 |
| rev_per_emp_g1 HIGH                        |  5337 |      250 |  0.043 |               0.673 |         0.228 |
| sbc_rev LOW                                |  5097 |      236 |  0.044 |               0.693 |         0.19  |
| flat_base                                  | 17677 |     1091 |  0.045 |               0.703 |         0.117 |

### 3. Regime at entry (the market's own 26-week return) and year

| regime       |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------|------:|---------:|-------:|--------------------:|--------------:|
| bull (>+15%) |  5225 |      497 |  0.088 |               1.382 |         0.161 |
| bear (<-15%) | 11219 |      811 |  0.073 |               1.146 |         0.097 |
| flat         | 31896 |     2325 |  0.064 |               1.008 |         0.18  |
| weak         | 21915 |     1424 |  0.06  |               0.932 |         0.149 |
| firm         | 17532 |     1096 |  0.056 |               0.868 |         0.169 |

|   year |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|-------:|------:|---------:|-------:|--------------------:|--------------:|
|   2012 |  2184 |      184 |  0.083 |               1.303 |         0.035 |
|   2013 |  3836 |      795 |  0.186 |               2.909 |         0.048 |
|   2014 |  4151 |      665 |  0.133 |               2.083 |         0.143 |
|   2015 |  3904 |      146 |  0.034 |               0.539 |         0.137 |
|   2016 |  6053 |      223 |  0.036 |               0.567 |         0.172 |
|   2017 |  6871 |      108 |  0.016 |               0.246 |         0.316 |
|   2018 |  8958 |      253 |  0.028 |               0.431 |         0.272 |
|   2019 |  6531 |      536 |  0.078 |               1.216 |         0.246 |
|   2020 |  6604 |      781 |  0.119 |               1.864 |         0.069 |
|   2021 |  8672 |      318 |  0.033 |               0.509 |         0.141 |
|   2022 | 13970 |      502 |  0.033 |               0.518 |         0.128 |
|   2023 |  9256 |      430 |  0.042 |               0.657 |         0.134 |
|   2024 |  6002 |      716 |  0.108 |               1.695 |         0.084 |
|   2025 |   731 |      478 |  0.591 |               9.241 |         0.163 |

### 4. Where the lift lives — sector and market


*sector*

| sector                 |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|------:|---------:|-------:|--------------------:|--------------:|
| Information Technology | 12144 |     1201 |  0.092 |               1.444 |         0.146 |
| Materials              | 12936 |      999 |  0.073 |               1.138 |         0.158 |
| Industrials            | 18980 |     1461 |  0.072 |               1.132 |         0.136 |
| Consumer Discretionary | 11792 |      838 |  0.064 |               0.997 |         0.149 |
| Health Care            |  1297 |       90 |  0.062 |               0.962 |         0.205 |
| Utilities              |  1620 |      112 |  0.058 |               0.915 |         0.071 |
| Energy                 |  3361 |      191 |  0.055 |               0.856 |         0.325 |
| Communication Services |  3075 |      178 |  0.053 |               0.822 |         0.188 |
| Consumer Staples       |  4607 |      233 |  0.046 |               0.723 |         0.136 |
| Financials             |  6319 |      325 |  0.043 |               0.676 |         0.113 |
| Real Estate            |  4398 |      191 |  0.038 |               0.593 |         0.132 |

*market*

| market   |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------|------:|---------:|-------:|--------------------:|--------------:|
| IS       |   435 |      161 |  0.368 |               5.748 |         0.07  |
| NS       |  2799 |      416 |  0.138 |               2.155 |         0.14  |
| KQ       |  1156 |      140 |  0.117 |               1.831 |         0.204 |
| TWO      |   885 |       86 |  0.1   |               1.566 |         0.082 |
| MC       |   300 |       26 |  0.088 |               1.379 |         0.097 |
| SZ       | 21443 |     1723 |  0.075 |               1.167 |         0.15  |
| ST       |   679 |       61 |  0.074 |               1.162 |         0.137 |
| L        |   173 |       17 |  0.073 |               1.136 |         0.16  |
| TO       |  2053 |      151 |  0.071 |               1.108 |         0.337 |
| TW       |  4604 |      338 |  0.068 |               1.057 |         0.076 |
| KS       |  4778 |      345 |  0.067 |               1.042 |         0.13  |
| KL       |   157 |       10 |  0.064 |               0.996 |         0.172 |

### 6. The tail — cutting the blow-up while keeping the lift

| condition             |     n |   rate |   lift_vs_archetype |   p_blowup_50 |   blowup_change |
|:----------------------|------:|-------:|--------------------:|--------------:|----------------:|
| cheap_netcash         |  7889 |  0.068 |               1.062 |         0.081 |          -0.077 |
| net_net               |  1976 |  0.109 |               1.703 |         0.084 |          -0.075 |
| tr_fcfm_streak LOW    |  1160 |  0.074 |               1.16  |         0.103 |          -0.055 |
| netcash_mcap HIGH     | 19032 |  0.065 |               1.014 |         0.114 |          -0.045 |
| tr_shares_consist LOW | 17445 |  0.067 |               1.045 |         0.119 |          -0.04  |
| gap_trend_opm LOW     | 10450 |  0.067 |               1.047 |         0.126 |          -0.033 |
| ncav_mcap HIGH        | 20535 |  0.069 |               1.08  |         0.127 |          -0.032 |
| kr_evToSales LOW      | 17362 |  0.077 |               1.199 |         0.127 |          -0.032 |
| buy_share_d12 LOW     |  1189 |  0.081 |               1.269 |         0.128 |          -0.031 |
| dvol_usd_log LOW      | 17981 |  0.082 |               1.279 |         0.132 |          -0.026 |

*Among the archetype's 3x winners, P(10x within 5y) = 11.6%; conditions that raise it:*

| condition               |   n |   p_10x_given_3x |
|:------------------------|----:|-----------------:|
| tr_debt_streak LOW      |  81 |            0.37  |
| buy_share HIGH          |  72 |            0.306 |
| headcount_growth        |  97 |            0.268 |
| tr_fcfm_streak LOW      |  63 |            0.254 |
| emp_g1 HIGH             | 108 |            0.241 |
| react_beats_mean LOW    | 222 |            0.234 |
| months_since_up HIGH    | 116 |            0.233 |
| n_analysts LOW          |  92 |            0.228 |
| buy_share LOW           |  60 |            0.217 |
| bo_new_holders_12m HIGH | 156 |            0.212 |

## 5. Intersections — does A and B beat either alone?

| A                         | B                         |     n |   events |   lift_A |   lift_B |   lift_AB |   p_blowup_AB |   t10_60_AB |
|:--------------------------|:--------------------------|------:|---------:|---------:|---------:|----------:|--------------:|------------:|
| fallen_insider_conviction | smart_money_wreckage      |  1739 |      419 |    3.917 |    4.689 |     5.76  |         0.308 |       0.079 |
| smart_money_wreckage      | fallen_below_cycle        |  2936 |      689 |    4.689 |    2.153 |     5.53  |         0.322 |       0.074 |
| left_for_dead_value       | fallen_insider_conviction |  1325 |      306 |    2.847 |    3.917 |     5.51  |         0.318 |       0.085 |
| smart_money_wreckage      | tree_recipe_10x           |  2410 |      567 |    4.689 |    2.967 |     5.394 |         0.358 |       0.085 |
| smart_money_wreckage      | tree_recipe               |  2605 |      598 |    4.689 |    3.384 |     5.263 |         0.354 |       0.082 |
| fallen_insider_conviction | tree_recipe_10x           |  1176 |      252 |    3.917 |    2.967 |     5.072 |         0.363 |       0.082 |
| fallen_insider_conviction | tree_recipe               |  1384 |      286 |    3.917 |    3.384 |     4.826 |         0.369 |       0.073 |
| fallen_insider_conviction | sequence_preignition      |   462 |       91 |    3.917 |    1.5   |     4.797 |         0.291 |       0.04  |
| fallen_insider_conviction | fallen_below_cycle        |  2070 |      410 |    3.917 |    2.153 |     4.75  |         0.308 |       0.056 |
| left_for_dead_value       | smart_money_wreckage      |  4556 |      893 |    2.847 |    4.689 |     4.595 |         0.318 |       0.064 |
| left_for_dead_value       | tree_recipe_10x           |  5442 |     1044 |    2.847 |    2.967 |     4.567 |         0.277 |       0.077 |
| left_for_dead_value       | tree_recipe               |  5819 |     1086 |    2.847 |    3.384 |     4.423 |         0.277 |       0.076 |
| fallen_ignored_believers  | smart_money_wreckage      |   581 |      103 |    2.079 |    4.689 |     4.033 |         0.341 |       0.058 |
| fallen_below_cycle        | tree_recipe_10x           |  6976 |     1131 |    2.153 |    2.967 |     3.888 |         0.299 |       0.049 |
| fallen_below_cycle        | tree_recipe               |  8698 |     1373 |    2.153 |    3.384 |     3.79  |         0.298 |       0.043 |
| smart_money_wreckage      | sequence_preignition      |  1126 |      173 |    4.689 |    1.5   |     3.627 |         0.319 |       0.047 |
| left_for_dead_value       | fallen_below_cycle        | 11718 |     1738 |    2.847 |    2.153 |     3.526 |         0.221 |       0.046 |
| tree_recipe               | tree_recipe_10x           | 15218 |     2267 |    3.384 |    2.967 |     3.516 |         0.278 |       0.054 |
| tree_recipe               | sequence_preignition      |  3833 |      548 |    3.384 |    1.5   |     3.359 |         0.254 |       0.037 |
| fallen_ignored_believers  | tree_recipe_10x           |  1032 |      146 |    2.079 |    2.967 |     3.309 |         0.412 |       0.039 |
| margin_inflect_weak_tape  | tree_recipe               |  1481 |      202 |    1.143 |    3.384 |     3.244 |         0.306 |       0.038 |
| left_for_dead_value       | fallen_ignored_believers  |  1319 |      195 |    2.847 |    2.079 |     3.192 |         0.301 |       0.042 |
| fallen_ignored_believers  | tree_recipe               |  1385 |      196 |    2.079 |    3.384 |     3.111 |         0.428 |       0.029 |
| tree_recipe_10x           | sequence_preignition      |  4237 |      543 |    2.967 |    1.5   |     3.041 |         0.22  |       0.038 |
| margin_inflect_weak_tape  | tree_recipe_10x           |  1657 |      207 |    1.143 |    2.967 |     2.942 |         0.259 |       0.035 |
| fallen_ignored_believers  | margin_inflect_weak_tape  |   464 |       62 |    2.079 |    1.143 |     2.869 |         0.242 |       0     |
| left_for_dead_value       | sequence_preignition      |  4804 |      587 |    2.847 |    1.5   |     2.81  |         0.218 |       0.047 |
| fallen_ignored_believers  | fallen_below_cycle        |  1710 |      202 |    2.079 |    2.153 |     2.662 |         0.28  |       0.036 |
| smart_money_wreckage      | margin_inflect_weak_tape  |   579 |       58 |    4.689 |    1.143 |     2.34  |         0.438 |       0.03  |
| fallen_insider_conviction | fallen_ignored_believers  |   350 |       35 |    3.917 |    2.079 |     2.229 |         0.4   |       0.063 |
| left_for_dead_value       | margin_inflect_weak_tape  |  2405 |      220 |    2.847 |    1.143 |     2.165 |         0.263 |       0.043 |
| fallen_ignored_believers  | sequence_preignition      |  1117 |      115 |    2.079 |    1.5   |     2.097 |         0.214 |       0     |
| fallen_below_cycle        | sequence_preignition      | 13506 |     1280 |    2.153 |    1.5   |     2.07  |         0.173 |       0.016 |
| fallen_below_cycle        | margin_inflect_weak_tape  |  1546 |      123 |    2.153 |    1.143 |     1.864 |         0.239 |       0.015 |
| margin_inflect_weak_tape  | sequence_preignition      | 18600 |     1148 |    1.143 |    1.5   |     1.342 |         0.187 |       0.014 |

## 7. The ceiling — a gradient-boosted model inside the fallen population

(ceiling model failed: window shape cannot be larger than input array shape)