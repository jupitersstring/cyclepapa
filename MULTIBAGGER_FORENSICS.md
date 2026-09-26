# The multibaggers under the microscope — a forensic examination

Entries examined: 5,791 multibagger episodes (3x held 4 weeks within 24 months; non-biotech); matched lookalikes: 21,569 (same month, market, size and drawdown quintile, did NOT triple).

## 1. Hygiene — artifacts removed before anything else

- flagged as artifacts: 555 of 5,791 (9.6%): penny 492, spike-and-reverse 27, unit break 27, stale tape 35
- examples: 000517.SZ 2013-05; 000547.SZ 2012-10; 000564.SZ 2021-02; 000586.SZ 2013-06; 000607.SZ 2013-05; 000631.SZ 2013-12; 000633.SZ 2013-06; 000659.SZ 2024-06; 000668.SZ 2013-06; 000751.SZ 2012-08; 000793.SZ 2024-05; 000816.SZ 2020-02

## 2. Anatomy — what produced the runs

| run_type      |   share |
|:--------------|--------:|
| re-rating-led |   0.468 |
| undetermined  |   0.183 |
| mixed         |   0.183 |
| margin-led    |   0.112 |
| growth-led    |   0.053 |

Median contribution to the log return (entry -> +24m):

| run_type      |   log_return |   sales_ps |   margin |   multiple |
|:--------------|-------------:|-----------:|---------:|-----------:|
| growth-led    |        1.036 |      0.933 |    0.076 |     -0.002 |
| margin-led    |        1.128 |      0.182 |    1.189 |     -0.257 |
| mixed         |        1.17  |      0.359 |    0.408 |      0.501 |
| re-rating-led |        1.197 |      0.05  |   -0.063 |      1.177 |
| undetermined  |        1.179 |     -0.154 |   -0.169 |     -0.108 |

The state at ENTRY by run type (narrative axes; 0.5 = typical for its month and market):

|                      |   growth-led |   margin-led |   mixed |   re-rating-led |   undetermined |
|:---------------------|-------------:|-------------:|--------:|----------------:|---------------:|
| growth               |        0.519 |        0.44  |   0.539 |           0.484 |          0.443 |
| accelerating         |        0.522 |        0.49  |   0.511 |           0.486 |          0.485 |
| margin_trajectory    |        0.454 |        0.44  |   0.5   |           0.488 |          0.494 |
| profitability        |        0.401 |        0.353 |   0.524 |           0.453 |          0.37  |
| below_own_cycle      |        0.586 |        0.575 |   0.489 |           0.507 |          0.506 |
| cheapness            |        0.374 |        0.52  |   0.521 |           0.543 |          0.522 |
| cheap_vs_own_history |        0.484 |        0.614 |   0.533 |           0.61  |          0.632 |
| balance_sheet        |        0.549 |        0.461 |   0.532 |           0.494 |          0.513 |
| deleveraging         |        0.458 |        0.498 |   0.48  |           0.509 |          0.521 |
| capital_discipline   |        0.421 |        0.505 |   0.487 |           0.49  |          0.467 |
| fallen               |        0.594 |        0.657 |   0.554 |           0.631 |          0.631 |
| ignition             |        0.435 |        0.394 |   0.45  |           0.383 |          0.412 |
| volatility           |        0.654 |        0.603 |   0.604 |           0.62  |          0.687 |
| neglect              |        0.562 |        0.56  |   0.524 |           0.548 |          0.616 |
| size                 |        0.415 |        0.39  |   0.425 |           0.38  |          0.333 |
| sentiment_warming    |        0.51  |        0.487 |   0.49  |           0.488 |          0.497 |
| insider_activist     |        0.527 |        0.533 |   0.541 |           0.533 |          0.509 |
| reinvesting          |        0.537 |        0.51  |   0.517 |           0.522 |          0.525 |
| headcount_growth     |        0.526 |        0.456 |   0.594 |           0.481 |          0.396 |

## 3. Trajectory — which parts of the story LEAD the run

Gap = multibagger minus matched lookalike (narrative-axis score). LEADS = the gap is open 6 months BEFORE the entry month, in the same direction as at entry.

| axis                 |   gap_t-12 |   gap_t-6 |   gap_t0 |   gap_t+6 |   gap_t+12 | opens_before   | role         |
|:---------------------|-----------:|----------:|---------:|----------:|-----------:|:---------------|:-------------|
| volatility           |      0.048 |     0.045 |    0.057 |     0.087 |      0.128 | True           | LEADS        |
| size                 |     -0.026 |    -0.017 |   -0.055 |    -0.02  |      0.017 | False          | at t0 / weak |
| ignition             |      0.011 |     0.018 |   -0.039 |     0.131 |      0.158 | False          | FOLLOWS      |
| headcount_growth     |      0.059 |     0.045 |    0.029 |     0.041 |      0.029 | True           | LEADS        |
| cheap_vs_own_history |     -0.012 |    -0.032 |    0.016 |    -0.071 |     -0.168 | False          | FOLLOWS      |
| growth               |      0.019 |     0.012 |    0.016 |     0.024 |      0.059 | False          | at t0 / weak |
| reinvesting          |      0.017 |     0.016 |    0.015 |     0.012 |      0.007 | False          | at t0 / weak |
| below_own_cycle      |     -0.026 |    -0.028 |   -0.014 |    -0.02  |     -0.059 | False          | at t0 / weak |
| profitability        |     -0.011 |    -0.005 |   -0.013 |    -0.011 |      0.014 | False          | at t0 / weak |
| insider_activist     |      0.005 |     0.007 |    0.011 |     0.018 |      0.004 | False          | at t0 / weak |
| cheapness            |      0.002 |    -0.005 |    0.009 |    -0.026 |     -0.052 | False          | at t0 / weak |
| deleveraging         |      0.006 |    -0.001 |   -0.008 |    -0.004 |      0.005 | False          | at t0 / weak |
| neglect              |     -0.008 |    -0.019 |    0.008 |    -0.013 |     -0.066 | False          | at t0 / weak |
| fallen               |     -0.013 |    -0.024 |    0.005 |    -0.057 |     -0.121 | False          | FOLLOWS      |
| balance_sheet        |      0.005 |     0.003 |    0.005 |     0.005 |      0.007 | False          | at t0 / weak |
| sentiment_warming    |      0.011 |     0.008 |   -0.004 |     0.012 |      0.028 | False          | at t0 / weak |
| accelerating         |     -0.007 |    -0.002 |    0.002 |     0.015 |      0.027 | False          | at t0 / weak |
| capital_discipline   |      0.001 |     0.003 |   -0.002 |    -0.005 |     -0.013 | False          | at t0 / weak |
| margin_trajectory    |      0.015 |     0.011 |   -0.001 |     0.003 |      0.04  | False          | at t0 / weak |

## 4. Sequence — the order in which the signs appear (months relative to entry)

|                                |   share_of_runs_with_sign |   median_first_seen_m |   q25 |   q75 |
|:-------------------------------|--------------------------:|----------------------:|------:|------:|
| first upgrade / initiation     |                       0.1 |                   -24 |   -24 |   -10 |
| new 13D holder                 |                       0.1 |                   -19 |   -24 |    -2 |
| insider buying (2+ quarters)   |                       0.1 |                   -14 |   -24 |     0 |
| revenue accelerates            |                       0.7 |                   -12 |   -24 |     0 |
| margin inflects (+3pp y/y)     |                       0.6 |                   -12 |   -24 |     0 |
| EBIT / NI / FCF turns positive |                       0.6 |                   -11 |   -22 |     0 |
| share count shrinking          |                       0.5 |                   -10 |   -21 |     0 |
| new 52-week high (>= 98%)      |                       0.5 |                    -3 |   -16 |     7 |
| volume change point (z >= 1.5) |                       0.7 |                    -2 |   -17 |     6 |

## 5. The dogs that did not bark — winners vs lookalikes from the same state

Mean paired difference in within-month-market rank (or state prevalence) with a bootstrap 90% interval; significant rows only, largest first.

| feature             |   winner_minus_lookalike |   ci90_lo |   ci90_hi |   coverage | significant   |
|:--------------------|-------------------------:|----------:|----------:|-----------:|:--------------|
| r13                 |                   -0.101 |    -0.107 |    -0.094 |      1     | True          |
| above_ma30          |                   -0.093 |    -0.1   |    -0.087 |      1     | True          |
| dist_hi52           |                   -0.067 |    -0.072 |    -0.062 |      1     | True          |
| last_react          |                   -0.062 |    -0.078 |    -0.044 |      0.197 | True          |
| r26                 |                   -0.058 |    -0.064 |    -0.051 |      1     | True          |
| rs26                |                   -0.058 |    -0.064 |    -0.051 |      1     | True          |
| vol52               |                    0.054 |     0.048 |     0.06  |      1     | True          |
| mcap_usd_log        |                   -0.054 |    -0.06  |    -0.048 |      0.894 | True          |
| st_flat_base        |                   -0.048 |    -0.057 |    -0.038 |      1     | True          |
| range104            |                    0.044 |     0.037 |     0.049 |      1     | True          |
| up_lo52             |                   -0.039 |    -0.048 |    -0.031 |      1     | True          |
| st_near_highs       |                   -0.036 |    -0.042 |    -0.031 |      1     | True          |
| pos104              |                   -0.035 |    -0.041 |    -0.031 |      1     | True          |
| st_deep_value       |                    0.035 |     0.025 |     0.046 |      1     | True          |
| ps                  |                   -0.033 |    -0.041 |    -0.024 |      0.806 | True          |
| slope_brk           |                   -0.031 |    -0.039 |    -0.024 |      1     | True          |
| rd_rev              |                    0.029 |     0.023 |     0.037 |      0.815 | True          |
| gm                  |                   -0.027 |    -0.036 |    -0.019 |      0.815 | True          |
| ev_sales            |                   -0.026 |    -0.034 |    -0.018 |      0.806 | True          |
| emp_g1              |                    0.026 |     0.005 |     0.05  |      0.137 | True          |
| ps_vs_own           |                   -0.024 |    -0.032 |    -0.017 |      0.778 | True          |
| opm                 |                   -0.024 |    -0.032 |    -0.017 |      0.815 | True          |
| st_accelerating     |                    0.024 |     0.012 |     0.036 |      1     | True          |
| div_yield           |                   -0.022 |    -0.031 |    -0.014 |      0.765 | True          |
| fcf_margin          |                   -0.022 |    -0.03  |    -0.015 |      0.759 | True          |
| npm                 |                   -0.021 |    -0.029 |    -0.014 |      0.815 | True          |
| ins_buy_quarters_4q |                    0.021 |     0.001 |     0.04  |      0.122 | True          |
| dvol_z13            |                    0.021 |     0.013 |     0.03  |      0.946 | True          |
| rev_q_yoy           |                    0.021 |     0.011 |     0.03  |      0.801 | True          |
| r52                 |                   -0.02  |    -0.027 |    -0.014 |      1     | True          |
| rev_g2              |                    0.018 |     0.009 |     0.026 |      0.759 | True          |
| ebit_g1             |                    0.018 |     0.008 |     0.029 |      0.458 | True          |
| updown26            |                   -0.016 |    -0.025 |    -0.009 |      1     | True          |
| bo_increasing_12m   |                    0.016 |     0.005 |     0.027 |      0.19  | True          |
| eps_g1              |                    0.016 |     0.005 |     0.027 |      0.408 | True          |
| st_fallen_angel     |                    0.016 |     0.009 |     0.021 |      1     | True          |
| inv_rev_d1          |                    0.014 |     0.004 |     0.024 |      0.766 | True          |
| opm_vs_5y           |                    0.014 |     0.005 |     0.022 |      0.775 | True          |
| dist_hi260          |                   -0.013 |    -0.016 |    -0.011 |      1     | True          |
| sga_rev             |                   -0.013 |    -0.022 |    -0.004 |      0.815 | True          |

## 6. 10x vs 3-5x (within 60 months; n = 299 vs 2473)

|                     |   ten_bagger_rank |   three_to_five_rank |   diff |
|:--------------------|------------------:|---------------------:|-------:|
| bo_new_holders_12m  |             0.64  |                0.551 |  0.089 |
| emp_g1              |             0.552 |                0.478 |  0.075 |
| mcap_usd_log        |             0.31  |                0.385 | -0.074 |
| beats_4q            |             0.395 |                0.463 | -0.068 |
| vol52               |             0.679 |                0.616 |  0.063 |
| months_since_up     |             0.624 |                0.562 |  0.062 |
| ps                  |             0.376 |                0.436 | -0.06  |
| ev_sales            |             0.4   |                0.454 | -0.054 |
| range104            |             0.673 |                0.62  |  0.053 |
| maxdd104            |             0.331 |                0.384 | -0.053 |
| fcf_margin          |             0.421 |                0.473 | -0.051 |
| ignored_beats_2y    |             0.456 |                0.506 | -0.05  |
| ps_vs_own           |             0.354 |                0.402 | -0.048 |
| n_analysts          |             0.495 |                0.449 |  0.046 |
| asset_turn_d1       |             0.55  |                0.504 |  0.046 |
| rev_per_emp_g1      |             0.44  |                0.486 | -0.046 |
| inc_margin          |             0.454 |                0.498 | -0.045 |
| opm_vs_5y           |             0.456 |                0.499 | -0.043 |
| dist_hi260          |             0.308 |                0.352 | -0.043 |
| downgrades_12m      |             0.454 |                0.497 | -0.043 |
| dvol_usd_log        |             0.399 |                0.441 | -0.041 |
| r260                |             0.358 |                0.399 | -0.041 |
| buy_share_d12       |             0.458 |                0.496 | -0.039 |
| npm                 |             0.394 |                0.432 | -0.039 |
| ins_buy_quarters_4q |             0.56  |                0.521 |  0.039 |