# What precedes multibagging — latent clusters of pre-conditions

Sample: 9,809 symbols (case-control, weighted to the population), 1,251,695 liquid month-ends (>= $250k/week USD), 2012-06 to 2026-09. Every feature is point-in-time (statements on filing date). A multibagger = a 3x reached AND held for 4 weeks; the ENTRY is the first month of each episode (the state before the run). Clusters are fit on entries up to 2017 and judged on 2018+ month-ends they never saw.


## Main: 3x within 24 months (non-biotech)

- entries (fit period): 2,224; base rate fit 3.77%, test 3.95%
- k chosen = 3 (silhouette, split-half stability >= 0.6):

|   k |   silhouette |   stability_ari |
|----:|-------------:|----------------:|
|   3 |        0.131 |           0.866 |
|   4 |        0.116 |           0.81  |
|   5 |        0.116 |           0.592 |
|   6 |        0.12  |           0.472 |
|   7 |        0.114 |           0.623 |
|   8 |        0.103 |           0.448 |
|   9 |        0.101 |           0.392 |
|  10 |        0.104 |           0.444 |
|  11 |        0.104 |           0.329 |
|  12 |        0.1   |           0.431 |

|   cluster |   share_of_fit_multibaggers |   share_of_test_multibaggers |   fit_share_of_month_ends |   fit_lift |   test_lift |   test_rate |   test_t3_12_rate |   test_t5_60_rate |   test_median_months_to_3x |   test_median_fwd_24m |   test_p_blowup_50 |   test_n_events |
|----------:|----------------------------:|-----------------------------:|--------------------------:|-----------:|------------:|------------:|------------------:|------------------:|---------------------------:|----------------------:|-------------------:|----------------:|
|         2 |                       0.373 |                        0.468 |                     0.199 |      1.405 |       1.499 |       0.059 |             0.017 |             0.083 |                     15.88  |                 0.091 |              0.145 |            5081 |
|         0 |                       0.41  |                        0.384 |                     0.318 |      1.133 |       1.128 |       0.044 |             0.01  |             0.063 |                     16.571 |                 0.068 |              0.121 |            5621 |
|         1 |                       0.216 |                        0.148 |                     0.171 |      0.763 |       0.667 |       0.026 |             0.006 |             0.04  |                     16.571 |                 0.056 |              0.161 |            1893 |


### Cluster 0

- NARRATIVE AXES vs all month-ends (+ = more): below_own_cycle -0.18, margin_trajectory +0.12, growth +0.12, size -0.11, headcount_growth +0.10, neglect +0.09, profitability +0.09, volatility +0.07, insider_activist +0.06, balance_sheet +0.05
- distinguishing features (mean within-month rank minus 0.5; + = high): opm_vs_5y +0.18, opm_d1 +0.17, ebit_g1 +0.16, opm_d2 +0.16, roic_d1 +0.15, eps_g1 +0.13, inc_margin +0.12, roic +0.12, mcap_usd_log -0.11, dvol_usd_log -0.09, last_react -0.07, ev_ebit -0.07, pe -0.05, dist_hi52 -0.05
- states (share of entries, lift vs all month-ends): margin_inflect_derated 10% (3.3x), hypergrowth 15% (2.3x), diluting_burner 12% (2.2x), turnaround 29% (1.9x), compounder 8% (1.9x), accelerating 46% (1.6x), deep_value 22% (1.4x), cheap_netcash 9% (1.3x)
- data present: fund 93%, val 100%, perc 0%, emp 6%, bs 99%
- medians at entry: rev growth 1y 12%; rev accel (pp) -0%; op margin 9%; op margin chg 1y 1%; FCF margin 0%; P/S 1.22; EV/EBIT 14.84; P/B 1.90; net cash / mcap 2%; net debt / EBITDA -0.18; share count chg 1y 0%; ROIC 9%; price / 5y high 60%; return 1y -1%; return 2y 4%; volatility 40%; mcap (log10 $) 8.51; analysts –; headcount growth 7%
- examples (entry month, months to 3x, 24m return): VIPS 2012-06 (7.13m, 2992%); INKP.JK 2016-05 (14.04m, 2075%); AMKBF 2012-06 (5.29m, 949%); 8890.T 2012-06 (6.67m, 777%); COGN3.SA 2012-06 (7.83m, 710%); 2497.T 2012-06 (11.74m, 700%); SASA.IS 2016-11 (6.21m, 685%); NXST 2012-06 (10.13m, 660%); 000720.SZ 2013-06 (21.40m, 633%); 2138.T 2012-06 (10.36m, 628%)

### Cluster 1

- NARRATIVE AXES vs all month-ends (+ = more): size -0.22, volatility +0.18, neglect +0.17, accelerating +0.15, headcount_growth -0.15, fallen +0.12, profitability -0.12, cheap_vs_own_history +0.07, capital_discipline -0.05, ignition -0.05
- distinguishing features (mean within-month rank minus 0.5; + = high): sbc_rev +0.38, ins_net_buy_4q +0.23, rev_accel +0.20, vol52 +0.18, range104 +0.17, rev_q_accel +0.15, downgrades_12m +0.14, upgrades_12m +0.11, ev_sales -0.35, ev_ebit -0.34, evs_chg_1y -0.32, mcap_usd_log -0.21, fcf_margin_d1 -0.18, dist_hi52 -0.17
- states (share of entries, lift vs all month-ends): fallen_angel 28% (2.4x), net_net 2% (1.8x), neglected 100% (1.0x), deep_value 14% (0.8x), accumulation 11% (0.8x), cheap_netcash 3% (0.5x), flat_base 10% (0.4x), near_highs 10% (0.3x)
- data present: fund 4%, val 4%, perc 0%, emp 1%, bs 41%
- medians at entry: rev growth 1y 12%; rev accel (pp) 18%; op margin 10%; op margin chg 1y -4%; FCF margin 0%; P/S 0.85; EV/EBIT 1.36; P/B 1.25; net cash / mcap -1%; net debt / EBITDA -0.24; share count chg 1y 0%; ROIC 1%; price / 5y high 53%; return 1y -5%; return 2y 1%; volatility 46%; mcap (log10 $) 8.27; analysts –; headcount growth -5%
- examples (entry month, months to 3x, 24m return): Y.TO 2012-06 (6.44m, 52371%); IBCD 2013-07 (1.15m, 26715%); LOOK.L 2017-04 (23.94m, 7641%); OIL 2016-05 (23.25m, 1488%); 2852.KL 2012-09 (18.41m, 1280%); 3323.T 2016-01 (23.48m, 755%); SMI 2017-07 (23.48m, 743%); JIN.AX 2017-06 (15.65m, 731%); 8462.T 2014-06 (7.83m, 720%); 1371.HK 2012-06 (17.26m, 718%)

### Cluster 2

- NARRATIVE AXES vs all month-ends (+ = more): fallen +0.26, below_own_cycle +0.21, profitability -0.18, cheap_vs_own_history +0.17, size -0.17, ignition -0.17, margin_trajectory -0.14, growth -0.13, volatility +0.12, neglect +0.10
- distinguishing features (mean within-month rank minus 0.5; + = high): range104 +0.14, vol52 +0.12, months_since_up +0.10, bo_new_holders_12m +0.09, ins_net_buy_4q +0.07, ev_ebit +0.06, sga_rev_d1 +0.05, rd_rev +0.05, dist_hi260 -0.28, pos104 -0.27, r260 -0.26, r104 -0.26, above_ma30 -0.25, dist_hi52 -0.24
- states (share of entries, lift vs all month-ends): fallen_angel 53% (4.5x), cyclical_trough 13% (2.7x), net_net 3% (2.2x), deep_value 35% (2.1x), diluting_burner 10% (2.0x), overlevered_stressed 16% (1.6x), cannibal 14% (1.6x), expensive 20% (1.4x)
- data present: fund 97%, val 100%, perc 0%, emp 17%, bs 100%
- medians at entry: rev growth 1y -0%; rev accel (pp) -6%; op margin 2%; op margin chg 1y -3%; FCF margin -2%; P/S 0.79; EV/EBIT 19.87; P/B 1.26; net cash / mcap -13%; net debt / EBITDA 1.23; share count chg 1y 0%; ROIC 2%; price / 5y high 37%; return 1y -27%; return 2y -39%; volatility 41%; mcap (log10 $) 8.43; analysts –; headcount growth 2%
- examples (entry month, months to 3x, 24m return): 300296.SZ 2013-04 (5.75m, 39335%); 6871.T 2012-06 (17.49m, 2041%); 8925.T 2012-11 (4.60m, 1860%); ROCK-A.CO 2015-05 (2.99m, 1386%); 004990.KS 2014-05 (23.71m, 1264%); 3778.T 2014-01 (23.25m, 1080%); AC.TO 2012-06 (9.67m, 869%); EVEREADY.NS 2013-12 (10.59m, 767%); GFINBURO.MX 2012-06 (16.80m, 764%); VWS.CO 2012-06 (13.35m, 724%)

## Fast: 3x within 12 months (non-biotech)

- entries (fit period): 1,036; base rate fit 0.93%, test 1.07%
- k chosen = 3 (silhouette, split-half stability >= 0.6):

|   k |   silhouette |   stability_ari |
|----:|-------------:|----------------:|
|   3 |        0.125 |           0.859 |
|   4 |        0.115 |           0.435 |
|   5 |        0.109 |           0.429 |
|   6 |        0.106 |           0.417 |
|   7 |        0.104 |           0.448 |
|   8 |        0.099 |           0.394 |
|   9 |        0.102 |           0.363 |
|  10 |        0.103 |           0.36  |
|  11 |        0.102 |           0.366 |
|  12 |        0.105 |           0.337 |

|   cluster |   share_of_fit_multibaggers |   share_of_test_multibaggers |   fit_share_of_month_ends |   fit_lift |   test_lift |   test_rate |   test_t3_12_rate |   test_t5_60_rate |   test_median_months_to_3x |   test_median_fwd_24m |   test_p_blowup_50 |   test_n_events |
|----------:|----------------------------:|-----------------------------:|--------------------------:|-----------:|------------:|------------:|------------------:|------------------:|---------------------------:|----------------------:|-------------------:|----------------:|
|         1 |                       0.396 |                        0.477 |                     0.188 |      1.429 |       1.689 |       0.018 |             0.018 |             0.086 |                      8.976 |                 0.085 |              0.15  |            1587 |
|         0 |                       0.401 |                        0.396 |                     0.313 |      1.027 |       1.071 |       0.011 |             0.011 |             0.064 |                      9.206 |                 0.072 |              0.118 |            1635 |
|         2 |                       0.203 |                        0.127 |                     0.161 |      0.944 |       0.665 |       0.007 |             0.007 |             0.042 |                      8.746 |                 0.058 |              0.165 |             532 |


### Cluster 0

- NARRATIVE AXES vs all month-ends (+ = more): below_own_cycle -0.15, size -0.12, margin_trajectory +0.11, growth +0.11, headcount_growth +0.10, neglect +0.10, volatility +0.09, profitability +0.08, balance_sheet +0.07, insider_activist +0.05
- distinguishing features (mean within-month rank minus 0.5; + = high): rev_per_emp_g1 +0.16, opm_vs_5y +0.15, opm_d1 +0.15, opm_d2 +0.14, ebit_g1 +0.13, roic_d1 +0.13, roic +0.12, rev_q_yoy +0.12, mcap_usd_log -0.12, dvol_usd_log -0.09, nd_ebitda -0.07, ev_ebit -0.06, react_beats_mean -0.06, pe -0.04
- states (share of entries, lift vs all month-ends): hypergrowth 17% (2.6x), margin_inflect_derated 7% (2.4x), diluting_burner 10% (2.0x), accelerating 56% (2.0x), turnaround 28% (1.9x), net_net 2% (1.7x), cheap_netcash 12% (1.6x), cannibal 14% (1.6x)
- data present: fund 94%, val 100%, perc 0%, emp 3%, bs 99%
- medians at entry: rev growth 1y 13%; rev accel (pp) 4%; op margin 10%; op margin chg 1y 1%; FCF margin 0%; P/S 1.54; EV/EBIT 16.15; P/B 1.99; net cash / mcap 2%; net debt / EBITDA -0.24; share count chg 1y 0%; ROIC 8%; price / 5y high 62%; return 1y 19%; return 2y 15%; volatility 41%; mcap (log10 $) 8.55; analysts –; headcount growth 6%
- examples (entry month, months to 3x, 24m return): 300296.SZ 2013-04 (5.75m, 39335%); VIPS 2012-06 (7.13m, 2992%); INKP.JK 2016-09 (11.51m, 1695%); 2852.KL 2013-03 (11.97m, 1455%); 002496.SZ 2013-03 (1.15m, 1387%); SMBR.JK 2015-08 (11.51m, 1089%); AMKBF 2012-06 (5.29m, 949%); 002373.SZ 2013-03 (10.82m, 845%); 8890.T 2012-06 (6.67m, 777%); 7575.T 2015-07 (10.13m, 774%)

### Cluster 1

- NARRATIVE AXES vs all month-ends (+ = more): fallen +0.24, profitability -0.22, below_own_cycle +0.21, size -0.20, margin_trajectory -0.15, volatility +0.14, cheap_vs_own_history +0.13, growth -0.13, ignition -0.13, neglect +0.12
- distinguishing features (mean within-month rank minus 0.5; + = high): ev_ebit +0.14, vol52 +0.14, months_since_up +0.12, nd_ebitda +0.11, bo_new_holders_12m +0.10, range104 +0.09, ins_net_buy_4q +0.09, pe +0.08, r260 -0.30, dist_hi260 -0.27, inc_margin -0.25, roic -0.25, ebit_g1 -0.24, roe -0.24
- states (share of entries, lift vs all month-ends): fallen_angel 49% (4.2x), cyclical_trough 19% (4.0x), overlevered_stressed 25% (2.5x), net_net 3% (2.5x), diluting_burner 12% (2.4x), deep_value 33% (2.0x), expensive 28% (1.9x), cannibal 14% (1.6x)
- data present: fund 95%, val 100%, perc 0%, emp 13%, bs 100%
- medians at entry: rev growth 1y 1%; rev accel (pp) 0%; op margin 1%; op margin chg 1y -3%; FCF margin -3%; P/S 0.91; EV/EBIT 32.62; P/B 1.34; net cash / mcap -21%; net debt / EBITDA 2.22; share count chg 1y 0%; ROIC 1%; price / 5y high 40%; return 1y -10%; return 2y -23%; volatility 43%; mcap (log10 $) 8.45; analysts –; headcount growth 1%
- examples (entry month, months to 3x, 24m return): 2930.T 2016-05 (11.51m, 1954%); 8925.T 2012-11 (4.60m, 1860%); ROCK-A.CO 2015-05 (2.99m, 1386%); RAIN.NS 2016-03 (11.97m, 1219%); 6871.T 2012-12 (11.51m, 1208%); 300033.SZ 2013-12 (11.74m, 1110%); 004990.KS 2015-05 (11.74m, 1028%); 7575.T 2014-05 (11.74m, 986%); VWS.CO 2012-07 (11.74m, 941%); AC.TO 2012-06 (9.67m, 869%)

### Cluster 2

- NARRATIVE AXES vs all month-ends (+ = more): size -0.24, profitability -0.23, volatility +0.20, neglect +0.18, fallen +0.17, cheap_vs_own_history +0.17, accelerating +0.11, cheapness +0.09, headcount_growth -0.08, growth +0.05
- distinguishing features (mean within-month rank minus 0.5; + = high): months_since_up +0.42, ins_buy_quarters_4q +0.41, ins_net_buy_4q +0.35, sbc_rev +0.32, vol52 +0.20, share_g3 +0.20, range104 +0.17, fcf_margin +0.16, ps -0.46, ev_sales -0.45, eps_g1 -0.44, inc_margin -0.32, gm_d1 -0.30, roic -0.30
- states (share of entries, lift vs all month-ends): fallen_angel 37% (3.1x), net_net 3% (2.5x), neglected 100% (1.0x), deep_value 15% (0.9x), accumulation 13% (0.9x), cheap_netcash 5% (0.7x), flat_base 11% (0.5x), overlevered_delevering 0% (0.3x)
- data present: fund 4%, val 1%, perc 0%, emp 2%, bs 42%
- medians at entry: rev growth 1y 2%; rev accel (pp) 26%; op margin 5%; op margin chg 1y -4%; FCF margin 1%; P/S 0.12; EV/EBIT –; P/B 0.94; net cash / mcap -8%; net debt / EBITDA -1.08; share count chg 1y 1%; ROIC 0%; price / 5y high 44%; return 1y -6%; return 2y 2%; volatility 49%; mcap (log10 $) 8.26; analysts –; headcount growth 4%
- examples (entry month, months to 3x, 24m return): Y.TO 2012-06 (6.44m, 52371%); IBCD 2013-07 (1.15m, 26715%); 0412.HK 2013-06 (6.90m, 4014%); HINDPETRO.NS 2015-04 (11.51m, 1383%); 1060.HK 2013-04 (11.28m, 1173%); 0607.HK 2014-06 (11.28m, 1087%); OIL 2017-05 (11.28m, 1034%); 1579.HK 2017-03 (11.28m, 960%); NOR.OL 2015-07 (10.59m, 796%); NBCC.NS 2013-07 (11.97m, 745%)

## Cross-check: 3x within 24 months, all ~100 ranked features (non-biotech)

- entries (fit period): 2,224; base rate fit 3.77%, test 3.95%
- k chosen = 5 (silhouette, split-half stability >= 0.6):

|   k |   silhouette |   stability_ari |
|----:|-------------:|----------------:|
|   3 |        0.054 |           0.47  |
|   4 |        0.039 |           0.609 |
|   5 |        0.043 |           0.602 |
|   6 |       -0.015 |           0.402 |
|   7 |       -0.008 |           0.371 |
|   8 |       -0.002 |           0.276 |
|   9 |       -0.011 |           0.406 |
|  10 |        0.002 |           0.488 |
|  11 |       -0.021 |           0.381 |
|  12 |       -0.013 |           0.409 |

|   cluster |   share_of_fit_multibaggers |   share_of_test_multibaggers |   fit_share_of_month_ends |   fit_lift |   test_lift |   test_rate |   test_t3_12_rate |   test_t5_60_rate |   test_median_months_to_3x |   test_median_fwd_24m |   test_p_blowup_50 |   test_n_events |
|----------:|----------------------------:|-----------------------------:|--------------------------:|-----------:|------------:|------------:|------------------:|------------------:|---------------------------:|----------------------:|-------------------:|----------------:|
|         0 |                       0.22  |                        0.323 |                     0.081 |      1.679 |       2.035 |       0.08  |             0.024 |             0.101 |                     15.65  |                 0.125 |              0.173 |            2967 |
|         3 |                       0.17  |                        0.172 |                     0.102 |      1.375 |       1.028 |       0.041 |             0.009 |             0.059 |                     16.801 |                 0.055 |              0.124 |            1902 |
|         1 |                       0.252 |                        0.174 |                     0.233 |      1.093 |       0.986 |       0.039 |             0.01  |             0.048 |                     16.11  |                 0.055 |              0.13  |            3456 |
|         2 |                       0.201 |                        0.219 |                     0.132 |      0.98  |       0.914 |       0.036 |             0.007 |             0.061 |                     17.261 |                 0.083 |              0.107 |            2041 |
|         4 |                       0.157 |                        0.112 |                     0.109 |      0.788 |       0.685 |       0.027 |             0.006 |             0.043 |                     16.801 |                 0.061 |              0.179 |            1128 |


### Cluster 0

- distinguishing features (mean within-month rank minus 0.5; + = high): nd_ebitda +0.21, range104 +0.20, months_since_up +0.16, vol52 +0.14, ins_net_buy_4q +0.13, cfo_ni +0.08, ev_ebit +0.06, div_yield +0.06, pos104 -0.35, dist_hi260 -0.35, r260 -0.34, r104 -0.34, r52 -0.33, above_ma30 -0.33
- states (share of entries, lift vs all month-ends): fallen_angel 73% (6.2x), deep_value 53% (3.2x), overlevered_stressed 26% (2.6x), cyclical_trough 11% (2.2x), margin_inflect_derated 6% (2.0x), overlevered_delevering 3% (1.8x), diluting_burner 9% (1.8x), net_net 2% (1.6x)
- data present: fund 95%, val 96%, perc 0%, emp 18%, bs 99%
- medians at entry: rev growth 1y -2%; rev accel (pp) -6%; op margin 1%; op margin chg 1y -2%; FCF margin -1%; P/S 0.41; EV/EBIT 20.51; P/B 0.95; net cash / mcap -55%; net debt / EBITDA 3.39; share count chg 1y 0%; ROIC 1%; price / 5y high 31%; return 1y -33%; return 2y -50%; volatility 42%; mcap (log10 $) 8.44; analysts –; headcount growth -1%
- examples (entry month, months to 3x, 24m return): 6871.T 2012-06 (17.49m, 2041%); 8925.T 2012-11 (4.60m, 1860%); ROCK-A.CO 2015-05 (2.99m, 1386%); 004990.KS 2014-05 (23.71m, 1264%); 3778.T 2014-01 (23.25m, 1080%); AC.TO 2012-06 (9.67m, 869%); VWS.CO 2012-06 (13.35m, 724%); NXST 2012-06 (10.13m, 660%); 006060.KS 2013-08 (23.25m, 647%); RAIL3.SA 2016-01 (6.44m, 641%)

### Cluster 1

- distinguishing features (mean within-month rank minus 0.5; + = high): r26 +0.30, rs26 +0.30, ma30_slope13 +0.30, up_lo52 +0.30, r52 +0.28, dvol_trend +0.26, above_ma30 +0.26, dvol_z13 +0.26, dvol_usd_log -0.16, mcap_usd_log -0.14, months_since_up -0.13, div_yield -0.07, ignored_beats_2y -0.06, emp_g1 -0.05
- states (share of entries, lift vs all month-ends): accumulation 28% (2.0x), diluting_burner 10% (1.8x), hypergrowth 8% (1.3x), compounder 5% (1.3x), turnaround 19% (1.3x), accelerating 34% (1.2x), expensive 17% (1.2x), deep_value 18% (1.1x)
- data present: fund 74%, val 80%, perc 0%, emp 5%, bs 88%
- medians at entry: rev growth 1y 8%; rev accel (pp) -3%; op margin 6%; op margin chg 1y 1%; FCF margin 0%; P/S 1.22; EV/EBIT 17.93; P/B 2.02; net cash / mcap -2%; net debt / EBITDA 0.23; share count chg 1y 0%; ROIC 7%; price / 5y high 73%; return 1y 29%; return 2y 39%; volatility 40%; mcap (log10 $) 8.42; analysts –; headcount growth 0%
- examples (entry month, months to 3x, 24m return): VIPS 2012-06 (7.13m, 2992%); 2852.KL 2012-09 (18.41m, 1280%); AMKBF 2012-06 (5.29m, 949%); 8890.T 2012-06 (6.67m, 777%); EVEREADY.NS 2013-12 (10.59m, 767%); GFINBURO.MX 2012-06 (16.80m, 764%); JIN.AX 2017-06 (15.65m, 731%); 8462.T 2014-06 (7.83m, 720%); SASA.IS 2016-11 (6.21m, 685%); 000720.SZ 2013-06 (21.40m, 633%)

### Cluster 2

- distinguishing features (mean within-month rank minus 0.5; + = high): earn_yield +0.23, ebit_g1 +0.19, opm_d2 +0.19, opm_vs_5y +0.19, roe +0.18, roic +0.18, emp_g1 +0.18, opm_d1 +0.18, above_ma30 -0.21, ev_ebit -0.20, rs26 -0.19, r26 -0.19, r13 -0.19, pe -0.19
- states (share of entries, lift vs all month-ends): margin_inflect_derated 16% (5.1x), hypergrowth 20% (3.0x), compounder 9% (2.2x), turnaround 32% (2.1x), cheap_netcash 15% (2.1x), net_net 3% (2.1x), deep_value 30% (1.8x), accelerating 49% (1.7x)
- data present: fund 96%, val 99%, perc 0%, emp 8%, bs 99%
- medians at entry: rev growth 1y 14%; rev accel (pp) 2%; op margin 11%; op margin chg 1y 1%; FCF margin 1%; P/S 1.11; EV/EBIT 11.12; P/B 1.56; net cash / mcap 3%; net debt / EBITDA -0.26; share count chg 1y 0%; ROIC 11%; price / 5y high 53%; return 1y -10%; return 2y -8%; volatility 38%; mcap (log10 $) 8.51; analysts –; headcount growth 9%
- examples (entry month, months to 3x, 24m return): 300296.SZ 2013-04 (5.75m, 39335%); INKP.JK 2016-05 (14.04m, 2075%); 2497.T 2012-06 (11.74m, 700%); 2138.T 2012-06 (10.36m, 628%); 000565.SZ 2013-06 (22.32m, 552%); 002245.SZ 2013-04 (22.55m, 527%); 300341.SZ 2013-04 (23.25m, 494%); S.BK 2012-07 (23.71m, 476%); 600556.SS 2013-05 (19.10m, 475%); 300243.SZ 2013-05 (23.25m, 468%)

### Cluster 3

- distinguishing features (mean within-month rank minus 0.5; + = high): sbc_rev +0.30, equity_assets +0.20, current_ratio +0.20, netcash_mcap +0.20, ncav_mcap +0.19, emp_g1 +0.18, sga_rev +0.17, ps +0.16, inc_margin -0.23, ebit_g1 -0.22, pos104 -0.22, above_ma30 -0.22, dist_hi260 -0.21, dist_hi52 -0.20
- states (share of entries, lift vs all month-ends): diluting_burner 15% (2.9x), fallen_angel 34% (2.9x), cyclical_trough 12% (2.5x), expensive 33% (2.2x), net_net 2% (2.0x), headcount_growth 6% (1.9x), cannibal 14% (1.6x), cheap_netcash 10% (1.4x)
- data present: fund 93%, val 100%, perc 0%, emp 13%, bs 99%
- medians at entry: rev growth 1y 3%; rev accel (pp) -7%; op margin 6%; op margin chg 1y -4%; FCF margin -4%; P/S 2.75; EV/EBIT 25.95; P/B 1.95; net cash / mcap 11%; net debt / EBITDA -2.04; share count chg 1y 0%; ROIC 5%; price / 5y high 44%; return 1y -20%; return 2y -28%; volatility 42%; mcap (log10 $) 8.47; analysts –; headcount growth 13%
- examples (entry month, months to 3x, 24m return): COGN3.SA 2012-06 (7.83m, 710%); BLFS 2016-10 (11.51m, 674%); TSLA 2012-06 (11.51m, 663%); 300163.SZ 2013-05 (23.01m, 662%); 2337.T 2012-06 (8.75m, 637%); 600576.SS 2013-05 (23.48m, 633%); 045390.KQ 2016-05 (23.71m, 626%); 601519.SS 2013-02 (23.94m, 617%); AXDX 2012-08 (12.43m, 603%); 2120.T 2012-06 (12.89m, 587%)

### Cluster 4

- distinguishing features (mean within-month rank minus 0.5; + = high): downgrades_12m +0.28, upgrades_12m +0.24, sga_rev_d1 +0.21, vol52 +0.18, ins_net_buy_4q +0.16, sbc_rev +0.16, debt_chg1 +0.16, range104 +0.14, dist_hi52 -0.26, above_ma30 -0.25, dist_hi260 -0.25, pos104 -0.24, ev_sales -0.21, rev_g2 -0.21
- states (share of entries, lift vs all month-ends): fallen_angel 30% (2.5x), net_net 2% (1.6x), neglected 100% (1.0x), deep_value 11% (0.6x), cheap_netcash 4% (0.6x), flat_base 11% (0.4x), diluting_burner 2% (0.3x), overlevered_stressed 3% (0.3x)
- data present: fund 5%, val 9%, perc 0%, emp 1%, bs 38%
- medians at entry: rev growth 1y 1%; rev accel (pp) 4%; op margin 9%; op margin chg 1y -3%; FCF margin 0%; P/S 0.78; EV/EBIT 12.26; P/B 1.21; net cash / mcap -0%; net debt / EBITDA 1.47; share count chg 1y 0%; ROIC 6%; price / 5y high 46%; return 1y -19%; return 2y -15%; volatility 44%; mcap (log10 $) 8.24; analysts –; headcount growth -5%
- examples (entry month, months to 3x, 24m return): Y.TO 2012-06 (6.44m, 52371%); IBCD 2013-07 (1.15m, 26715%); LOOK.L 2017-04 (23.94m, 7641%); OIL 2016-05 (23.25m, 1488%); 3323.T 2016-01 (23.48m, 755%); SMI 2017-07 (23.48m, 743%); 1371.HK 2012-06 (17.26m, 718%); III.L 2012-06 (18.18m, 706%); 0412.HK 2012-08 (23.48m, 669%); 0095.HK 2013-02 (8.75m, 647%)

## Conjunctions of states (pairs / triples) — robust = strong in BOTH periods

| combo                                                |   n |   fit_share |   fit_lift |   fit_p_blowup |   fit_median_fwd_24m |   test_share |   test_lift |   test_p_blowup |   test_median_fwd_24m |   min_lift |
|:-----------------------------------------------------|----:|------------:|-----------:|---------------:|---------------------:|-------------:|------------:|----------------:|----------------------:|-----------:|
| deep_value + fallen_angel + overlevered_stressed     |   3 |       0.005 |      3.206 |          0.203 |                0.248 |        0.01  |       3.706 |           0.259 |                 0.194 |      3.206 |
| accelerating + deep_value + fallen_angel             |   3 |       0.009 |      2.982 |          0.193 |                0.188 |        0.017 |       3.271 |           0.218 |                 0.173 |      2.982 |
| deep_value + fallen_angel + turnaround               |   3 |       0.007 |      2.733 |          0.197 |                0.19  |        0.012 |       3.597 |           0.254 |                 0.199 |      2.733 |
| overlevered_stressed + fallen_angel                  |   2 |       0.014 |      3.093 |          0.207 |                0.165 |        0.023 |       2.669 |           0.241 |                 0.108 |      2.669 |
| fallen_angel + overlevered_stressed + turnaround     |   3 |       0.004 |      3.556 |          0.197 |                0.197 |        0.006 |       2.583 |           0.238 |                 0.1   |      2.583 |
| fallen_angel + deep_value                            |   2 |       0.03  |      2.49  |          0.207 |                0.172 |        0.051 |       3.366 |           0.236 |                 0.198 |      2.49  |
| deep_value + fallen_angel + neglected                |   3 |       0.03  |      2.49  |          0.207 |                0.172 |        0.038 |       2.879 |           0.214 |                 0.173 |      2.49  |
| accelerating + fallen_angel + overlevered_stressed   |   3 |       0.006 |      3.461 |          0.202 |                0.145 |        0.01  |       2.429 |           0.218 |                 0.066 |      2.429 |
| cheap_netcash + deep_value + fallen_angel            |   3 |       0.006 |      2.329 |          0.172 |                0.119 |        0.009 |       2.728 |           0.164 |                 0.217 |      2.329 |
| fallen_angel + neglected + overlevered_stressed      |   3 |       0.014 |      3.093 |          0.207 |                0.165 |        0.017 |       2.306 |           0.217 |                 0.077 |      2.306 |
| fallen_angel + accumulation                          |   2 |       0.004 |      2.74  |          0.205 |                0.061 |        0.008 |       2.287 |           0.182 |                -0.004 |      2.287 |
| expensive + fallen_angel + overlevered_stressed      |   3 |       0.004 |      2.253 |          0.211 |                0.112 |        0.006 |       2.304 |           0.169 |                 0.087 |      2.253 |
| overlevered_delevering + fallen_angel                |   2 |       0.003 |      2.545 |          0.219 |                0.136 |        0.006 |       2.222 |           0.214 |                 0.088 |      2.222 |
| fallen_angel + cyclical_trough                       |   2 |       0.011 |      2.782 |          0.249 |                0.048 |        0.018 |       2.186 |           0.207 |                 0.1   |      2.186 |
| cheap_netcash + fallen_angel                         |   2 |       0.009 |      2.183 |          0.169 |                0.11  |        0.014 |       2.281 |           0.156 |                 0.164 |      2.183 |
| fallen_angel + turnaround                            |   2 |       0.021 |      2.652 |          0.201 |                0.095 |        0.038 |       2.182 |           0.183 |                 0.116 |      2.182 |
| accelerating + cyclical_trough + fallen_angel        |   3 |       0.009 |      3.082 |          0.247 |                0.03  |        0.014 |       2.162 |           0.212 |                 0.086 |      2.162 |
| fallen_angel + insider_buying                        |   2 |       0.004 |      2.161 |          0.266 |                0.065 |        0.007 |       4.314 |           0.342 |                 0.276 |      2.161 |
| cheap_netcash + fallen_angel + neglected             |   3 |       0.009 |      2.183 |          0.169 |                0.11  |        0.012 |       2.124 |           0.151 |                 0.155 |      2.124 |
| fallen_angel + margin_inflect_derated                |   2 |       0.008 |      2.242 |          0.259 |               -0.014 |        0.017 |       2.089 |           0.225 |                 0.069 |      2.089 |
| accelerating + cyclical_trough + deep_value          |   3 |       0.004 |      2.212 |          0.178 |                0.142 |        0.007 |       2.083 |           0.141 |                 0.26  |      2.083 |
| accumulation + fallen_angel + neglected              |   3 |       0.004 |      2.74  |          0.205 |                0.061 |        0.007 |       2.05  |           0.174 |                -0.015 |      2.05  |
| fallen_angel + accelerating                          |   2 |       0.037 |      2.673 |          0.209 |                0.053 |        0.067 |       2.034 |           0.176 |                 0.089 |      2.034 |
| fallen_angel + cannibal                              |   2 |       0.011 |      2.553 |          0.173 |                0.139 |        0.022 |       2.027 |           0.147 |                 0.126 |      2.027 |
| accelerating + fallen_angel + turnaround             |   3 |       0.011 |      2.813 |          0.217 |                0.065 |        0.019 |       2.004 |           0.181 |                 0.08  |      2.004 |
| accelerating + fallen_angel + margin_inflect_derated |   3 |       0.005 |      2.284 |          0.272 |               -0.058 |        0.011 |       1.995 |           0.226 |                 0.043 |      1.995 |
| accelerating + cheap_netcash + fallen_angel          |   3 |       0.003 |      2.614 |          0.15  |                0.128 |        0.005 |       1.982 |           0.153 |                 0.14  |      1.982 |
| fallen_angel + margin_inflect_derated + turnaround   |   3 |       0.004 |      2.512 |          0.241 |                0.021 |        0.009 |       1.964 |           0.203 |                 0.052 |      1.964 |
| cyclical_trough + deep_value                         |   2 |       0.006 |      1.95  |          0.176 |                0.139 |        0.01  |       1.96  |           0.149 |                 0.252 |      1.95  |
| fallen_angel + neglected + turnaround                |   3 |       0.021 |      2.652 |          0.201 |                0.095 |        0.031 |       1.944 |           0.163 |                 0.108 |      1.944 |
| fallen_angel + margin_inflect_derated + neglected    |   3 |       0.008 |      2.242 |          0.259 |               -0.014 |        0.014 |       1.919 |           0.197 |                 0.06  |      1.919 |
| diluting_burner + fallen_angel                       |   2 |       0.009 |      2.573 |          0.275 |                0     |        0.012 |       1.897 |           0.293 |                 0     |      1.897 |
| fallen_angel + neglected                             |   2 |       0.106 |      2.359 |          0.207 |                0.072 |        0.14  |       1.848 |           0.181 |                 0.083 |      1.848 |
| cyclical_trough + fallen_angel + neglected           |   3 |       0.011 |      2.782 |          0.249 |                0.048 |        0.014 |       1.824 |           0.192 |                 0.08  |      1.824 |
| fallen_angel + new_activist                          |   2 |       0.007 |      1.814 |          0.269 |                0.086 |        0.012 |       3.659 |           0.375 |                 0.165 |      1.814 |
| fallen_angel + neglected + new_activist              |   3 |       0.007 |      1.814 |          0.269 |                0.086 |        0.005 |       2.83  |           0.448 |                -0.04  |      1.814 |
| accelerating + diluting_burner + fallen_angel        |   3 |       0.005 |      2.62  |          0.294 |               -0.071 |        0.007 |       1.793 |           0.299 |                -0.024 |      1.793 |
| fallen_angel + expensive                             |   2 |       0.018 |      2.03  |          0.236 |               -0.046 |        0.029 |       1.787 |           0.158 |                 0.086 |      1.787 |
| fallen_angel + neglected + overlevered_delevering    |   3 |       0.003 |      2.545 |          0.219 |                0.136 |        0.004 |       1.781 |           0.2   |                 0.063 |      1.781 |
| accelerating + fallen_angel + neglected              |   3 |       0.037 |      2.673 |          0.209 |                0.053 |        0.056 |       1.771 |           0.159 |                 0.08  |      1.771 |

## Decision-tree recipes on the narrative axes (fit <= 2017, lift re-measured 2018+)

|   leaf | recipe                                                                                |   fit_share |   fit_lift |   fit_p_blowup |   test_share |   test_lift |   test_p_blowup |
|-------:|:--------------------------------------------------------------------------------------|------------:|-----------:|---------------:|-------------:|------------:|----------------:|
|      6 | size <= 0.31 & insider_activist <= 0.50 & fallen > 0.81                               |       0.008 |      2.089 |          0.296 |        0.007 |       4.13  |           0.379 |
|     13 | size <= 0.31 & insider_activist > 0.50 & insider_activist > 0.50 & volatility > 0.88  |       0.01  |      1.993 |          0.281 |        0.01  |       3.877 |           0.432 |
|     25 | size > 0.31 & volatility > 0.63 & miss_emp <= 0.50 & volatility > 0.84                |       0.015 |      1.066 |          0.196 |        0.017 |       1.984 |           0.328 |
|      9 | size <= 0.31 & insider_activist > 0.50 & insider_activist <= 0.50 & size <= 0.12      |       0.077 |      2.826 |          0.134 |        0.081 |       1.947 |           0.154 |
|     28 | size > 0.31 & volatility > 0.63 & miss_emp > 0.50 & volatility > 0.90                 |       0.049 |      1.829 |          0.265 |        0.044 |       1.621 |           0.287 |
|      5 | size <= 0.31 & insider_activist <= 0.50 & fallen <= 0.81 & volatility > 0.55          |       0.014 |      0.573 |          0.146 |        0.011 |       1.351 |           0.263 |
|     10 | size <= 0.31 & insider_activist > 0.50 & insider_activist <= 0.50 & size > 0.12       |       0.119 |      1.705 |          0.121 |        0.126 |       1.301 |           0.142 |
|     27 | size > 0.31 & volatility > 0.63 & miss_emp > 0.50 & volatility <= 0.90                |       0.134 |      1.143 |          0.168 |        0.135 |       1.278 |           0.183 |
|     24 | size > 0.31 & volatility > 0.63 & miss_emp <= 0.50 & volatility <= 0.84               |       0.029 |      0.413 |          0.118 |        0.032 |       0.812 |           0.223 |
|     12 | size <= 0.31 & insider_activist > 0.50 & insider_activist > 0.50 & volatility <= 0.88 |       0.032 |      0.522 |          0.079 |        0.035 |       0.773 |           0.152 |
|     20 | size > 0.31 & volatility <= 0.63 & insider_activist > 0.50 & size <= 0.77             |       0.27  |      0.734 |          0.074 |        0.262 |       0.669 |           0.096 |
|     21 | size > 0.31 & volatility <= 0.63 & insider_activist > 0.50 & size > 0.77              |       0.141 |      0.326 |          0.063 |        0.149 |       0.494 |           0.082 |
|     18 | size > 0.31 & volatility <= 0.63 & insider_activist <= 0.50 & volatility > 0.44       |       0.025 |      0.125 |          0.069 |        0.021 |       0.312 |           0.177 |
|      4 | size <= 0.31 & insider_activist <= 0.50 & fallen <= 0.81 & volatility <= 0.55         |       0.018 |      0.113 |          0.021 |        0.019 |       0.2   |           0.096 |
|     17 | size > 0.31 & volatility <= 0.63 & insider_activist <= 0.50 & volatility <= 0.44      |       0.06  |      0.009 |          0.021 |        0.05  |       0.078 |           0.077 |

## Interpretable states — univariate lift on the 3x-in-24m outcome

| state                     |   fit_prevalence |   fit_lift |   fit_p_blowup |   test_prevalence |   test_lift |   test_p_blowup |
|:--------------------------|-----------------:|-----------:|---------------:|------------------:|------------:|----------------:|
| st_fallen_angel           |            0.106 |      2.357 |          0.207 |             0.171 |       2.099 |           0.199 |
| st_net_net                |            0.013 |      1.393 |          0.064 |             0.019 |       2.074 |           0.096 |
| st_deep_value             |            0.163 |      1.271 |          0.086 |             0.205 |       1.618 |           0.13  |
| st_hypergrowth            |            0.063 |      1.58  |          0.176 |             0.08  |       1.415 |           0.198 |
| st_turnaround             |            0.139 |      1.44  |          0.144 |             0.151 |       1.402 |           0.163 |
| st_margin_inflect_derated |            0.029 |      1.451 |          0.184 |             0.054 |       1.304 |           0.174 |
| st_accumulation           |            0.137 |      1.058 |          0.114 |             0.116 |       1.279 |           0.151 |
| st_diluting_burner        |            0.048 |      1.789 |          0.215 |             0.034 |       1.277 |           0.247 |
| st_compounder             |            0.042 |      0.941 |          0.086 |             0.066 |       1.22  |           0.124 |
| st_cyclical_trough        |            0.047 |      1.71  |          0.166 |             0.053 |       1.205 |           0.17  |
| st_overlevered_delevering |            0.017 |      1.111 |          0.127 |             0.018 |       1.189 |           0.186 |
| st_overlevered_stressed   |            0.097 |      1.124 |          0.113 |             0.102 |       1.184 |           0.188 |
| st_accelerating           |            0.27  |      1.429 |          0.139 |             0.338 |       1.184 |           0.147 |
| st_headcount_growth       |            0.034 |      0.63  |          0.122 |             0.031 |       1.142 |           0.254 |
| st_expensive              |            0.136 |      1.373 |          0.191 |             0.13  |       1.074 |           0.18  |
| st_cannibal               |            0.088 |      1.289 |          0.107 |             0.094 |       1.061 |           0.142 |
| st_insider_buying         |            0.05  |      0.478 |          0.085 |             0.051 |       1.055 |           0.175 |
| st_cheap_netcash          |            0.071 |      0.975 |          0.059 |             0.08  |       1.012 |           0.075 |
| st_new_activist           |            0.086 |      0.639 |          0.107 |             0.078 |       1.01  |           0.217 |
| st_neglected              |            0.999 |      1.001 |          0.108 |             0.789 |       0.989 |           0.141 |
| st_productivity_gain      |            0.026 |      0.53  |          0.122 |             0.04  |       0.876 |           0.204 |
| st_near_highs             |            0.398 |      0.513 |          0.061 |             0.284 |       0.576 |           0.102 |
| st_flat_base              |            0.258 |      0.593 |          0.058 |             0.275 |       0.434 |           0.098 |

## Drug developers (separate)

- base rate fit 6.62%, test 4.09%; k = 5

|   cluster |   share_of_fit_multibaggers |   fit_lift |   test_lift |   test_median_fwd_24m |   test_p_blowup_50 |
|----------:|----------------------------:|-----------:|------------:|----------------------:|-------------------:|
|         0 |                       0.218 |      0.782 |       0.998 |                -0.004 |              0.167 |
|         1 |                       0.115 |      2.628 |       2.296 |                -0.071 |              0.304 |
|         2 |                       0.234 |      1.087 |       0.983 |                -0.02  |              0.218 |
|         3 |                       0.111 |      2.632 |       3.574 |                -0.071 |              0.436 |
|         4 |                       0.322 |      0.898 |       1.024 |                 0.066 |              0.107 |

## Caveats

- Case-control sample of 10,160 symbols weighted to the population; delisted names are included where FMP serves their prices (delisting is an observed outcome, not a gap).
- Valuation = FMP's period-end market cap / EV rolled forward by the price move since the period end (currency-consistent with the statements); a mcap/revenue outside 0.01-200x is treated as a currency mismatch and dropped.
- Perception data start 2017-2019 and cover a minority of names; their absence is a feature (miss_perc), not an error.
- Clusters describe where multibaggers CAME FROM; the region lift says whether being in that state raises the odds for everyone in it.