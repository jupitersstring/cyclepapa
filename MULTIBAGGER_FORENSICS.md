# The multibaggers under the microscope — a forensic examination

Entries examined: 4,783 multibagger episodes (3x held 4 weeks within 24 months; non-biotech); matched lookalikes: 19,940 (same month, market, size and drawdown quintile, did NOT triple).

## 1. Hygiene — artifacts removed before anything else

- flagged as artifacts: 32 of 4,783 (0.7%); low-priced (< $0.20, reported, NOT excluded): 348; spike-and-reverse 10, unit break 1, stale tape 22
- examples: 000547.SZ 2012-10; 000586.SZ 2013-06; 000607.SZ 2013-05; 000633.SZ 2013-06; 000668.SZ 2013-06; 000751.SZ 2012-08; 000976.SZ 2013-06; 000995.SZ 2018-12; 001745.KS 2018-08; 002110.SZ 2016-01; 002180.SZ 2013-06; 002296.SZ 2012-11

## 2. Anatomy — what produced the runs

| run_type      |   share |
|:--------------|--------:|
| re-rating-led |   0.493 |
| mixed         |   0.185 |
| undetermined  |   0.153 |
| margin-led    |   0.118 |
| growth-led    |   0.051 |

Median contribution to the log return (entry -> +24m):

| run_type      |   log_return |   sales_ps |   margin |   multiple |
|:--------------|-------------:|-----------:|---------:|-----------:|
| growth-led    |        1.065 |      0.922 |    0.06  |     -0.002 |
| margin-led    |        1.128 |      0.181 |    1.198 |     -0.245 |
| mixed         |        1.168 |      0.355 |    0.4   |      0.511 |
| re-rating-led |        1.191 |      0.046 |   -0.073 |      1.192 |
| undetermined  |        1.164 |     -0.101 |   -0.455 |     -0.336 |

The state at ENTRY by run type (narrative axes; 0.5 = typical for its month and market):

|                      |   growth-led |   margin-led |   mixed |   re-rating-led |   undetermined |
|:---------------------|-------------:|-------------:|--------:|----------------:|---------------:|
| growth               |        0.509 |        0.442 |   0.525 |           0.482 |          0.469 |
| accelerating         |        0.52  |        0.481 |   0.511 |           0.485 |          0.491 |
| margin_trajectory    |        0.453 |        0.43  |   0.504 |           0.492 |          0.48  |
| divergence           |        0.573 |        0.609 |   0.567 |           0.6   |          0.595 |
| best_in_own_history  |        0.465 |        0.48  |   0.522 |           0.487 |          0.459 |
| cash_quality         |        0.506 |        0.506 |   0.499 |           0.492 |          0.494 |
| efficiency_trend     |        0.492 |        0.498 |   0.497 |           0.492 |          0.492 |
| profitability        |        0.397 |        0.35  |   0.517 |           0.455 |          0.37  |
| below_own_cycle      |        0.597 |        0.582 |   0.497 |           0.508 |          0.527 |
| cheapness            |        0.39  |        0.526 |   0.53  |           0.546 |          0.559 |
| cheap_vs_own_history |        0.487 |        0.558 |   0.51  |           0.552 |          0.568 |
| balance_sheet        |        0.552 |        0.457 |   0.525 |           0.49  |          0.504 |
| deleveraging         |        0.46  |        0.504 |   0.474 |           0.507 |          0.534 |
| capital_discipline   |        0.416 |        0.506 |   0.488 |           0.493 |          0.469 |
| fallen               |        0.623 |        0.67  |   0.567 |           0.635 |          0.655 |
| ignition             |        0.368 |        0.364 |   0.415 |           0.368 |          0.362 |
| volatility           |        0.653 |        0.601 |   0.602 |           0.616 |          0.687 |
| neglect              |        0.53  |        0.529 |   0.507 |           0.533 |          0.606 |
| size                 |        0.417 |        0.409 |   0.44  |           0.391 |          0.314 |
| sentiment_warming    |        0.519 |        0.485 |   0.493 |           0.488 |          0.494 |
| insider_activist     |        0.52  |        0.539 |   0.538 |           0.532 |          0.532 |
| reinvesting          |        0.53  |        0.515 |   0.518 |           0.523 |          0.499 |
| headcount_growth     |        0.515 |        0.46  |   0.591 |           0.492 |          0.371 |

## 3. Trajectory — which parts of the story LEAD the run

Gap = multibagger minus matched lookalike (narrative-axis score). LEADS = the gap is open 6 months BEFORE the entry month, in the same direction as at entry.

| axis                 |   gap_t-12 |   gap_t-6 |   gap_t0 |   gap_t+6 |   gap_t+12 | opens_before   | role         |
|:---------------------|-----------:|----------:|---------:|----------:|-----------:|:---------------|:-------------|
| ignition             |      0.007 |     0.021 |   -0.062 |     0.124 |      0.146 | False          | FOLLOWS      |
| size                 |     -0.03  |    -0.025 |   -0.05  |    -0.016 |      0.017 | False          | at t0 / weak |
| volatility           |      0.042 |     0.04  |    0.048 |     0.072 |      0.11  | True           | LEADS        |
| divergence           |      0.004 |    -0.011 |    0.029 |    -0.049 |     -0.103 | False          | at t0 / weak |
| headcount_growth     |      0.057 |     0.036 |    0.024 |     0.037 |      0.023 | True           | LEADS        |
| cheapness            |      0.009 |     0.003 |    0.018 |    -0.017 |     -0.04  | False          | at t0 / weak |
| growth               |      0.014 |     0.008 |    0.017 |     0.019 |      0.048 | False          | at t0 / weak |
| reinvesting          |      0.012 |     0.011 |    0.014 |     0.012 |      0.007 | False          | at t0 / weak |
| deleveraging         |      0.006 |     0.001 |   -0.012 |    -0.008 |      0     | False          | at t0 / weak |
| below_own_cycle      |     -0.023 |    -0.026 |   -0.011 |    -0.015 |     -0.051 | False          | at t0 / weak |
| profitability        |     -0.011 |    -0.007 |   -0.011 |    -0.011 |      0.009 | False          | at t0 / weak |
| insider_activist     |      0.008 |     0.008 |    0.008 |     0.016 |      0.006 | False          | at t0 / weak |
| fallen               |     -0.009 |    -0.02  |    0.008 |    -0.053 |     -0.114 | False          | FOLLOWS      |
| cash_quality         |      0.005 |    -0.002 |   -0.006 |     0.002 |      0.003 | False          | at t0 / weak |
| best_in_own_history  |      0.017 |     0.01  |    0.005 |     0.019 |      0.048 | False          | at t0 / weak |
| cheap_vs_own_history |     -0.004 |    -0.021 |   -0.005 |    -0.027 |     -0.088 | False          | at t0 / weak |
| balance_sheet        |     -0.002 |    -0.001 |   -0.004 |    -0.004 |     -0.001 | False          | at t0 / weak |
| neglect              |      0.003 |    -0.001 |    0.003 |    -0.01  |     -0.059 | False          | at t0 / weak |
| margin_trajectory    |      0.019 |     0.014 |    0.002 |    -0.001 |      0.03  | False          | at t0 / weak |
| capital_discipline   |     -0.001 |     0.002 |   -0.001 |    -0.004 |     -0.009 | False          | at t0 / weak |
| efficiency_trend     |      0.001 |    -0.002 |    0.001 |     0.007 |      0.018 | False          | at t0 / weak |
| sentiment_warming    |      0.008 |     0.01  |   -0.001 |     0.01  |      0.031 | False          | at t0 / weak |
| accelerating         |     -0.008 |    -0.003 |    0.001 |     0.01  |      0.021 | False          | at t0 / weak |

## 4. Sequence — the order in which the signs appear (months relative to entry)

|                                |   share_of_runs_with_sign |   median_first_seen_m |   q25 |   q75 |
|:-------------------------------|--------------------------:|----------------------:|------:|------:|
| first upgrade / initiation     |                       0.1 |                   -24 |   -24 |   -12 |
| new 13D holder                 |                       0.1 |                   -21 |   -24 |    -7 |
| insider buying (2+ quarters)   |                       0.1 |                   -16 |   -24 |    -2 |
| revenue accelerates            |                       0.7 |                   -14 |   -24 |    -3 |
| margin inflects (+3pp y/y)     |                       0.6 |                   -14 |   -24 |    -3 |
| EBIT / NI / FCF turns positive |                       0.6 |                   -12 |   -23 |    -2 |
| share count shrinking          |                       0.5 |                   -11 |   -21 |    -1 |
| new 52-week high (>= 98%)      |                       0.5 |                    -6 |   -18 |     6 |
| volume change point (z >= 1.5) |                       0.7 |                    -6 |   -18 |     6 |

## 5. The dogs that did not bark — winners vs lookalikes from the same state

Mean paired difference in within-month-market rank (or state prevalence) with a bootstrap 90% interval; significant rows only, largest first.

| feature                             |   winner_minus_lookalike |   ci90_lo |   ci90_hi |   coverage | significant   |
|:------------------------------------|-------------------------:|----------:|----------:|-----------:|:--------------|
| r13                                 |                   -0.122 |    -0.129 |    -0.115 |      1     | True          |
| above_ma30                          |                   -0.117 |    -0.124 |    -0.111 |      1     | True          |
| pt_rev_6m                           |                    0.1   |     0.015 |     0.206 |      0.003 | True          |
| rs26                                |                   -0.079 |    -0.086 |    -0.073 |      1     | True          |
| r26                                 |                   -0.079 |    -0.086 |    -0.073 |      1     | True          |
| last_react                          |                   -0.077 |    -0.093 |    -0.061 |      0.198 | True          |
| dist_hi52                           |                   -0.073 |    -0.077 |    -0.068 |      1     | True          |
| up_lo52                             |                   -0.059 |    -0.066 |    -0.052 |      1     | True          |
| st_deep_value                       |                    0.051 |     0.04  |     0.062 |      1     | True          |
| slope_brk                           |                   -0.05  |    -0.058 |    -0.043 |      1     | True          |
| mcap_usd_log                        |                   -0.05  |    -0.056 |    -0.046 |      0.911 | True          |
| vol52                               |                    0.046 |     0.04  |     0.053 |      1     | True          |
| gap_sales_1y                        |                    0.046 |     0.038 |     0.053 |      0.799 | True          |
| pos104                              |                   -0.044 |    -0.048 |    -0.04  |      1     | True          |
| ps                                  |                   -0.043 |    -0.051 |    -0.035 |      0.818 | True          |
| gap_trend_opm                       |                    0.042 |     0.033 |     0.051 |      0.788 | True          |
| st_flat_base                        |                   -0.042 |    -0.051 |    -0.034 |      1     | True          |
| st_near_highs                       |                   -0.041 |    -0.046 |    -0.035 |      1     | True          |
| gap_trend_roic                      |                    0.04  |     0.031 |     0.048 |      0.711 | True          |
| range104                            |                    0.036 |     0.03  |     0.042 |      1     | True          |
| ps_vs_own                           |                   -0.035 |    -0.042 |    -0.027 |      0.792 | True          |
| updown26                            |                   -0.034 |    -0.042 |    -0.026 |      1     | True          |
| kr_priceToBookRatio_own             |                    0.033 |     0.025 |     0.041 |      0.94  | True          |
| pos156                              |                   -0.032 |    -0.037 |    -0.028 |      1     | True          |
| kr_grossProfitMargin                |                   -0.032 |    -0.04  |    -0.024 |      0.947 | True          |
| ev_sales                            |                   -0.031 |    -0.039 |    -0.023 |      0.818 | True          |
| r52                                 |                   -0.031 |    -0.036 |    -0.024 |      1     | True          |
| gap_eps_1y                          |                    0.03  |     0.018 |     0.042 |      0.411 | True          |
| gm                                  |                   -0.03  |    -0.038 |    -0.02  |      0.826 | True          |
| emp_g1                              |                    0.028 |     0.006 |     0.05  |      0.132 | True          |
| kr_priceToSalesRatio                |                   -0.027 |    -0.034 |    -0.02  |      0.947 | True          |
| kr_assetTurnover                    |                    0.027 |     0.019 |     0.034 |      0.947 | True          |
| kr_researchAndDevelopementToRevenue |                    0.026 |     0.019 |     0.032 |      0.947 | True          |
| gap_fcfps_1y                        |                    0.026 |     0.005 |     0.047 |      0.1   | True          |
| rd_rev                              |                    0.025 |     0.018 |     0.033 |      0.826 | True          |
| kr_ebitdaMargin                     |                   -0.025 |    -0.033 |    -0.017 |      0.947 | True          |
| kr_priceToBookRatio_d4              |                    0.025 |     0.017 |     0.033 |      0.845 | True          |
| kr_pretaxProfitMargin               |                   -0.024 |    -0.032 |    -0.016 |      0.947 | True          |
| kr_operatingProfitMargin            |                   -0.024 |    -0.031 |    -0.016 |      0.947 | True          |
| st_accelerating                     |                    0.022 |     0.01  |     0.035 |      1     | True          |

## 6. 10x vs 3-5x (within 60 months; n = 281 vs 2279)

|                                               |   ten_bagger_rank |   three_to_five_rank |   diff |
|:----------------------------------------------|------------------:|---------------------:|-------:|
| bo_new_holders_12m                            |             0.655 |                0.548 |  0.106 |
| gap_sales_3y                                  |             0.676 |                0.583 |  0.093 |
| n_analysts                                    |             0.523 |                0.45  |  0.073 |
| emp_g1                                        |             0.553 |                0.483 |  0.07  |
| tr_debt_slope8                                |             0.555 |                0.497 |  0.057 |
| ins_net_buy_4q                                |             0.584 |                0.528 |  0.056 |
| ps                                            |             0.372 |                0.428 | -0.056 |
| maxdd104                                      |             0.325 |                0.38  | -0.055 |
| dd_time_share_260                             |             0.657 |                0.604 |  0.053 |
| kr_debtToAssetsRatio_d4                       |             0.562 |                0.511 |  0.051 |
| ps_vs_own                                     |             0.337 |                0.388 | -0.051 |
| kr_debtToCapitalRatio_d4                      |             0.565 |                0.516 |  0.049 |
| tr_fcfm_consist                               |             0.547 |                0.498 |  0.049 |
| gm_d1                                         |             0.532 |                0.484 |  0.048 |
| kr_priceToFreeCashFlowRatio_own               |             0.538 |                0.491 |  0.047 |
| dist_hi260                                    |             0.289 |                0.337 | -0.047 |
| kr_debtToAssetsRatio_own                      |             0.557 |                0.51  |  0.047 |
| kr_salesGeneralAndAdministrativeToRevenue_own |             0.557 |                0.51  |  0.047 |
| tr_fcfm_slope8                                |             0.544 |                0.497 |  0.047 |
| kr_priceToSalesRatio                          |             0.407 |                0.454 | -0.047 |
| ev_sales                                      |             0.4   |                0.447 | -0.047 |
| tr_opm_slope8                                 |             0.535 |                0.489 |  0.046 |
| gap_sales_2y                                  |             0.645 |                0.6   |  0.045 |
| asset_turn_d1                                 |             0.545 |                0.5   |  0.045 |
| kr_debtToCapitalRatio_own                     |             0.556 |                0.511 |  0.045 |