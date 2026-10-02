# Multibaggers among profitable operators

The population the asset-based and pre-profit studies left: operating margin and FCF margin both non-negative, not an asset business, not a drug developer. Operator measures added (operating leverage, earnings quality, capital cycle, dilution-adjusted growth, path shape, value vs growth, sector-relative ranks, quality x price). Every feature ranked within month x market inside the population; sub-populations re-ranked inside themselves.

484,267 month-ends, 5,702 symbols; 3x-within-24m rate 3.76%, 10x-within-5y rate 0.93%; 31.7% of month-ends claimed by an implemented archetype, holding 44.9% of the multibagger month-ends.


# 1. Archetypes of the operator population


### k-means archetypes

1,633 multibagger starts; base rate 3.76% of month-ends.

|   k |   silhouette |   robustness_ari |
|----:|-------------:|-----------------:|
|   3 |        0.07  |            0.795 |
|   4 |        0.062 |            0.322 |
|   5 |        0.066 |            0.699 |
|   6 |        0.06  |            0.497 |
|   7 |        0.067 |            0.325 |
|   8 |        0.062 |            0.304 |
|   9 |        0.055 |            0.415 |
|  10 |        0.06  |            0.281 |

|   archetype |   n_multibaggers |   share_of_multibaggers |   share_of_all_month_ends |   lift |   rate |   t3_12_rate |   t5_60_rate |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 |
|------------:|-----------------:|------------------------:|--------------------------:|-------:|-------:|-------------:|-------------:|--------------:|----------------------:|-----------------:|--------------:|
|           0 |              542 |                   0.331 |                     0.139 |  1.158 |  0.044 |        0.011 |        0.071 |         0.013 |                16.571 |            0.159 |         0.114 |
|           1 |              613 |                   0.385 |                     0.382 |  0.978 |  0.037 |        0.008 |        0.057 |         0.008 |                16.571 |            0.137 |         0.085 |
|           2 |              478 |                   0.284 |                     0.19  |  0.934 |  0.035 |        0.008 |        0.06  |         0.008 |                16.341 |            0.106 |         0.093 |


**Archetype 0** — 33% of multibaggers, lift 1.16x, blow-up 11%
- axes (vs all month-ends, + = more): vs_market -0.30, industry_laggard +0.28, fallen +0.27, ignition -0.22, divergence +0.21, industry_cheap +0.21, size -0.20, cheapness +0.20, value_vs_growth +0.19, volatility +0.18
- most distinctive features (rank vs all): gap_sales_1y +0.27, gap_sales_2y +0.26, gap_sales_3y +0.25, fcf_yield +0.22, op_sec_fcfy +0.22, op_ind_fcfy +0.21, gap_own_fcfps +0.20, gap_own_roic +0.20, gap_own_opm +0.20, dd_time_share_260 +0.19, above_ma30 -0.33, dist_hi260 -0.32, op_vs_mkt_disthi -0.32, dist_hi52 -0.31, ps_vs_own -0.31, rs26 -0.30, op_vs_mkt_r26 -0.30, r26 -0.30
- states over-represented (share, x vs all): fund_price_divergence 35% (6.0x), fallen_angel 52% (5.0x), margin_inflect_derated 15% (3.1x), deep_value 55% (2.6x), headcount_growth 9% (2.3x), net_net 4% (2.2x), overlevered_stressed 15% (1.9x), hypergrowth 12% (1.9x)
- medians at the start: rev growth 1y 10%; rev accel (pp) -1%; op margin 9%; op margin chg 1y 0%; FCF margin 6%; P/S 0.50; EV/EBIT 9.18; P/B 1.01; net cash / mcap -11%; net debt / EBITDA 0.55; share count chg 1y 0%; ROIC 10%; price / 5y high 39%; return 1y -29%; return 2y -32%; volatility 44%; mcap (log10 $) 8.47; analysts 6.00; headcount growth 5%; op margin, own-history pct 55%; sales/share vs price 1y (log gap) 0.46; margin own-pct minus price own-pct 0.35; op-margin slope 8q 0.00; share of 5y in deep drawdown 77%; weeks since 5y low 85.00
- data present: fund 96%, val 100%, perc 41%, emp 29%, bs 99%
- examples (start, best multiple within 5y): ISCTR.IS 2020-05 (87.1x); MAVI.IS 2019-08 (64.3x); STRL 2021-09 (39.3x); 012450.KS 2020-09 (38.6x); CLS.TO 2020-03 (37.6x); CLS 2020-03 (36.5x); TURSG.IS 2018-12 (32.5x); SUZLON.NS 2019-09 (30.3x); AGHOL.IS 2020-08 (25.8x); MEG.TO 2020-03 (25.4x)

**Archetype 1** — 39% of multibaggers, lift 0.98x, blow-up 8%
- axes (vs all month-ends, + = more): headcount_growth +0.16, growth +0.12, volatility +0.12, below_own_cycle -0.12, vs_market +0.10, fallen -0.10, industry_growth +0.10, cheap_vs_own_history -0.09, industry_laggard -0.09, industry_quality +0.09
- most distinctive features (rank vs all): pt_rev_6m +0.25, r104 +0.18, emp_g1 +0.16, trend_r2_52 +0.15, r52 +0.15, op_vs_mkt_r52 +0.15, r260 +0.15, ma30_slope13 +0.14, kr_priceToBookRatio_own +0.14, as_pb_own +0.14, ins_net_buy_4q -0.12, gap_perc_targets -0.11, gap_sales_2y -0.10, ins_buy_quarters_4q -0.09, gap_sales_3y -0.09, op_base_age -0.08, wks_since_hi52 -0.08, r13 -0.07
- states over-represented (share, x vs all): compounder 22% (2.1x), margin_inflect_derated 10% (2.1x), hypergrowth 12% (1.9x), turnaround 27% (1.3x), accelerating 45% (1.3x), headcount_growth 4% (1.2x), net_net 2% (1.1x), fund_price_divergence 6% (1.1x)
- medians at the start: rev growth 1y 15%; rev accel (pp) 2%; op margin 13%; op margin chg 1y 1%; FCF margin 6%; P/S 1.67; EV/EBIT 14.58; P/B 2.52; net cash / mcap 4%; net debt / EBITDA -0.70; share count chg 1y 0%; ROIC 16%; price / 5y high 67%; return 1y 10%; return 2y 35%; volatility 39%; mcap (log10 $) 8.89; analysts 1.00; headcount growth 9%; op margin, own-history pct 64%; sales/share vs price 1y (log gap) 0.03; margin own-pct minus price own-pct 0.08; op-margin slope 8q 0.00; share of 5y in deep drawdown 60%; weeks since 5y low 191.00
- data present: fund 96%, val 100%, perc 32%, emp 13%, bs 99%
- examples (start, best multiple within 5y): 5803.T 2021-06 (117.8x); ALARK.IS 2018-10 (69.8x); 6920.T 2015-09 (36.7x); ASUZU.IS 2020-01 (28.0x); SMCI 2021-08 (27.2x); ASELS.IS 2021-01 (27.1x); PGSUS.IS 2020-07 (26.0x); TRIL.NS 2021-08 (26.0x); FNOX.ST 2016-05 (25.9x); 2930.T 2015-04 (24.8x)

**Archetype 2** — 28% of multibaggers, lift 0.93x, blow-up 9%
- axes (vs all month-ends, + = more): vs_market -0.24, industry_laggard +0.22, value_vs_growth -0.22, fallen +0.21, growth -0.20, industry_growth -0.19, below_own_cycle +0.18, profitability -0.18, quality_x_price -0.17, headcount_growth -0.16
- most distinctive features (rank vs all): op_evebit_vs_g +0.23, op_pe_vs_g +0.23, dd_time_share_260 +0.15, ev_ebit +0.14, op_sec_evebit +0.14, op_ind_evebit +0.14, op_base_age +0.13, wks_since_hi52 +0.13, gap_own_fcfps +0.13, gap_sales_2y +0.12, pos104 -0.25, inc_margin -0.25, op_vs_mkt_disthi -0.25, dist_hi260 -0.25, ebit_g1 -0.25, pos156 -0.25, op_sec_disthi -0.24, op_ind_disthi -0.23
- states over-represented (share, x vs all): fallen_angel 39% (3.8x), fund_price_divergence 19% (3.3x), net_net 3% (2.0x), expensive 26% (1.8x), overlevered_stressed 13% (1.7x), overlevered_delevering 3% (1.6x), cyclical_trough 6% (1.5x), turnaround 30% (1.4x)
- medians at the start: rev growth 1y -3%; rev accel (pp) -9%; op margin 5%; op margin chg 1y -1%; FCF margin 4%; P/S 0.97; EV/EBIT 20.71; P/B 1.31; net cash / mcap -1%; net debt / EBITDA 0.10; share count chg 1y 0%; ROIC 5%; price / 5y high 46%; return 1y -21%; return 2y -26%; volatility 39%; mcap (log10 $) 8.55; analysts 2.00; headcount growth -2%; op margin, own-history pct 27%; sales/share vs price 1y (log gap) 0.19; margin own-pct minus price own-pct 0.09; op-margin slope 8q -0.00; share of 5y in deep drawdown 80%; weeks since 5y low 153.00
- data present: fund 99%, val 100%, perc 33%, emp 17%, bs 100%
- examples (start, best multiple within 5y): 5803.T 2020-07 (45.4x); THYAO.IS 2020-03 (35.9x); GARAN.IS 2020-09 (24.3x); ANSGR.IS 2021-08 (19.9x); TAVHL.IS 2020-07 (17.0x); 600763.SS 2017-05 (16.1x); ABMD 2013-02 (15.6x); 065350.KS 2019-01 (15.5x); HTRO.ST 2019-07 (15.5x); 6104.TWO 2018-10 (14.4x)

### Gaussian-mixture archetypes

1,633 multibagger starts; base rate 3.76% of month-ends.

|   k |      bic |
|----:|---------:|
|   2 | 133694   |
|   3 |  74037.7 |
|   4 |  64349.3 |
|   5 |  61705.5 |
|   6 |  59330.4 |
|   7 |  52231.3 |
|   8 |  37831.9 |
|   9 |  51941.4 |
|  10 |  51070.6 |

|   archetype |   n_multibaggers |   share_of_multibaggers |   share_of_all_month_ends |   lift |   rate |   t3_12_rate |   t5_60_rate |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 |
|------------:|-----------------:|------------------------:|--------------------------:|-------:|-------:|-------------:|-------------:|--------------:|----------------------:|-----------------:|--------------:|
|           7 |               58 |                   0.038 |                     0.017 |  1.838 |  0.069 |        0.017 |        0.096 |         0.022 |                16.456 |            0.069 |         0.147 |
|           5 |              115 |                   0.081 |                     0.039 |  1.578 |  0.059 |        0.018 |        0.091 |         0.021 |                15.42  |            0.185 |         0.196 |
|           6 |                3 |                   0.001 |                     0     |  1.411 |  0.053 |        0.028 |        0.075 |         0.03  |                13.694 |            0.238 |         0.278 |
|           3 |              308 |                   0.182 |                     0.098 |  1.077 |  0.041 |        0.007 |        0.22  |         0.01  |                17.261 |            0.204 |         0.043 |
|           0 |              852 |                   0.5   |                     0.313 |  0.992 |  0.037 |        0.009 |        0.049 |         0.009 |                16.341 |            0.109 |         0.085 |
|           1 |               94 |                   0.061 |                     0.098 |  0.98  |  0.037 |        0.009 |        0.071 |         0.011 |                16.341 |            0.082 |         0.122 |
|           4 |               16 |                   0.011 |                     0.057 |  0.7   |  0.026 |        0.006 |        0.041 |         0.003 |                16.11  |            0.094 |         0.1   |
|           2 |              187 |                   0.126 |                     0.119 |  0.499 |  0.019 |        0.004 |        0.039 |         0.005 |                17.722 |            0.192 |         0.107 |


**Archetype 7** — 4% of multibaggers, lift 1.84x, blow-up 15%
- axes (vs all month-ends, + = more): headcount_growth +0.46, volatility +0.22, fallen +0.16, vs_market -0.16, industry_laggard +0.15, ignition -0.14, insider_activist +0.14, size -0.14, operating_leverage +0.13, industry_growth -0.13
- most distinctive features (rank vs all): roic_d1 +0.49, tr_roic_accel +0.49, emp_g1 +0.46, ins_net_buy_4q +0.31, bo_new_holders_12m +0.30, months_since_up +0.28, tr_fcfm_slope8 +0.28, vol52 +0.22, downgrades_12m +0.22, op_sec_vol +0.22, op_evebit_vs_g -0.46, inv_rev_d1 -0.40, evs_chg_1y -0.33, dso_d1 -0.32, upgrades_12m -0.30, ps_vs_own -0.25, dist_hi52 -0.24, ignored_beats_2y -0.24
- states over-represented (share, x vs all): net_net 5% (3.3x), fallen_angel 26% (2.5x), fund_price_divergence 14% (2.4x), overlevered_stressed 12% (1.6x), neglected 97% (1.2x), expensive 17% (1.2x), deep_value 22% (1.1x), cheap_netcash 9% (0.7x)
- medians at the start: rev growth 1y -2%; rev accel (pp) -13%; op margin 13%; op margin chg 1y -1%; FCF margin 6%; P/S 1.52; EV/EBIT 15.42; P/B 2.19; net cash / mcap 4%; net debt / EBITDA -0.60; share count chg 1y 1%; ROIC 15%; price / 5y high 50%; return 1y -23%; return 2y -10%; volatility 50%; mcap (log10 $) 8.18; analysts 0.00; headcount growth 36%; op margin, own-history pct 71%; sales/share vs price 1y (log gap) 0.25; margin own-pct minus price own-pct 0.47; op-margin slope 8q -0.00; share of 5y in deep drawdown 70%; weeks since 5y low 62.00
- data present: fund 12%, val 95%, perc 16%, emp 2%, bs 81%
- examples (start, best multiple within 5y): 2930.T 2015-04 (24.8x); INDIANB.NS 2020-03 (13.8x); BEL.NS 2020-04 (13.4x); GLOBUSSPR.NS 2019-07 (13.3x); BEML.NS 2020-03 (12.8x); HARVIA.HE 2018-10 (12.7x); TRIDENT.NS 2019-07 (12.0x); TATAELXSI.NS 2013-02 (10.2x); JMFINANCIL.NS 2013-02 (10.2x); MUTHOOTFIN.NS 2015-09 (8.4x)

**Archetype 5** — 8% of multibaggers, lift 1.58x, blow-up 20%
- axes (vs all month-ends, + = more): vs_market -0.45, industry_laggard +0.43, fallen +0.42, volatility +0.35, ignition -0.31, size -0.30, profitability -0.24, divergence +0.24, industry_cheap +0.23, industry_quality -0.22
- most distinctive features (rank vs all): gap_perc_targets +0.40, gap_sales_1y +0.38, range104 +0.38, gap_sales_2y +0.35, vol52 +0.35, gap_sales_3y +0.33, op_ind_vol +0.33, op_sec_vol +0.32, dd_time_share_260 +0.29, wks_since_hi52 +0.25, dist_hi260 -0.45, op_vs_mkt_disthi -0.45, op_vs_ind_r52 -0.44, dist_hi52 -0.44, r52 -0.44, op_vs_mkt_r52 -0.44, op_vs_ind_disthi -0.44, op_ind_disthi -0.44
- states over-represented (share, x vs all): fallen_angel 84% (8.1x), fund_price_divergence 32% (5.5x), headcount_growth 18% (4.9x), overlevered_stressed 34% (4.5x), new_activist 38% (4.2x), insider_buying 19% (3.5x), deep_value 64% (3.1x), cannibal 31% (2.6x)
- medians at the start: rev growth 1y 1%; rev accel (pp) -6%; op margin 5%; op margin chg 1y -1%; FCF margin 4%; P/S 0.30; EV/EBIT 13.04; P/B 0.76; net cash / mcap -116%; net debt / EBITDA 3.41; share count chg 1y -0%; ROIC 5%; price / 5y high 25%; return 1y -52%; return 2y -59%; volatility 58%; mcap (log10 $) 8.55; analysts 10.50; headcount growth 1%; op margin, own-history pct 27%; sales/share vs price 1y (log gap) 0.75; margin own-pct minus price own-pct 0.18; op-margin slope 8q -0.00; share of 5y in deep drawdown 73%; weeks since 5y low 1.50
- data present: fund 100%, val 100%, perc 68%, emp 100%, bs 100%
- examples (start, best multiple within 5y): CLS 2020-03 (36.5x); LMB 2019-10 (16.8x); EHTH 2016-10 (15.7x); BELFB 2020-04 (13.1x); BLDR 2018-12 (12.7x); NSP 2014-09 (10.6x); REVG 2020-03 (10.2x); HTHT 2015-03 (9.5x); DDS 2019-08 (8.7x); ABCD 2014-08 (8.7x)

**Archetype 6** — 0% of multibaggers, lift 1.41x, blow-up 28%
- axes (vs all month-ends, + = more): neglect -0.50, dilution_adjusted +0.49, margin_trajectory +0.49, fallen -0.49, reinvesting +0.49, industry_laggard -0.49, ignition +0.49, vs_market +0.49, market_wave +0.49, industry_wave +0.49
- most distinctive features (rank vs all): mkt_tape_disthi +0.49, mkt_tape_r52 +0.49, mkt_tape_r26 +0.49, dvol_usd_log +0.49, ind_tape_r26 +0.49, op_sec_gm +0.49, op_sec_opm +0.49, ind_breadth_up52 +0.49, op_cash_gap +0.49, op_wc_drift +0.49, op_capex_rolloff +0.48, gap_fcfps_1y +0.49, kr_freeCashFlowPerShare_g4 +0.49, kr_operatingCashFlowPerShare_g4 +0.49, inc_margin +0.49, op_pe_vs_g +0.49, as_capex_da +0.49, as_harvest +0.49
- states over-represented (share, x vs all): margin_inflect_derated 67% (14.2x), hypergrowth 67% (9.9x), fund_price_divergence 33% (5.8x), turnaround 67% (3.2x), fallen_angel 33% (3.2x), cheap_netcash 33% (2.9x), cannibal 33% (2.8x), accumulation 33% (2.3x)
- medians at the start: rev growth 1y 53%; rev accel (pp) 2%; op margin 16%; op margin chg 1y 6%; FCF margin 11%; P/S 0.55; EV/EBIT 10.01; P/B 1.18; net cash / mcap -170%; net debt / EBITDA 2.30; share count chg 1y -2%; ROIC 8%; price / 5y high 57%; return 1y 1%; return 2y -27%; volatility 32%; mcap (log10 $) 8.86; analysts 0.00; headcount growth –; op margin, own-history pct 100%; sales/share vs price 1y (log gap) 0.60; margin own-pct minus price own-pct 0.37; op-margin slope 8q -0.00; share of 5y in deep drawdown 54%; weeks since 5y low 52.00
- data present: fund 100%, val 100%, perc 33%, emp 0%, bs 100%
- examples (start, best multiple within 5y): COMI.CA 2022-06 (5.7x); 4IG.BD 2023-10 (4.9x); MYTIL.AT 2012-07 (4.0x)

**Archetype 3** — 18% of multibaggers, lift 1.08x, blow-up 4%
- axes (vs all month-ends, + = more): industry_laggard +0.10, vs_market -0.09, ignition -0.09, industry_cheap +0.08, volatility +0.08, fallen +0.07, cheapness +0.07, industry_growth -0.05, industry_quality -0.04, divergence +0.04
- most distinctive features (rank vs all): months_since_up +0.21, vol52 +0.08, range104 +0.07, op_sec_vol +0.07, gap_own_fcfps +0.06, op_ind_vol +0.06, op_ind_fcfy +0.06, gap_sales_2y +0.05, kr_financialLeverageRatio +0.05, gap_sales_1y +0.05, downgrades_12m -0.17, r13 -0.17, above_ma30 -0.17, upgrades_12m -0.16, dist_hi52 -0.15, op_sec_r26 -0.12, op_vs_ind_r26 -0.12, op_ind_r26 -0.12
- states over-represented (share, x vs all): net_net 4% (2.5x), fallen_angel 24% (2.4x), fund_price_divergence 12% (2.1x), deep_value 39% (1.9x), margin_inflect_derated 8% (1.8x), cheap_netcash 19% (1.6x), hypergrowth 9% (1.4x), accelerating 47% (1.3x)
- medians at the start: rev growth 1y 8%; rev accel (pp) -1%; op margin 9%; op margin chg 1y 0%; FCF margin 4%; P/S 0.95; EV/EBIT 12.80; P/B 1.29; net cash / mcap 3%; net debt / EBITDA -0.38; share count chg 1y 0%; ROIC 10%; price / 5y high 58%; return 1y -1%; return 2y 13%; volatility 35%; mcap (log10 $) 8.69; analysts 0.00; headcount growth –; op margin, own-history pct 45%; sales/share vs price 1y (log gap) 0.09; margin own-pct minus price own-pct 0.05; op-margin slope 8q 0.00; share of 5y in deep drawdown 78%; weeks since 5y low 180.00
- data present: fund 100%, val 100%, perc 100%, emp 0%, bs 100%
- examples (start, best multiple within 5y): CLS.TO 2020-03 (37.6x); TRIL.NS 2021-08 (26.0x); MEG.TO 2020-03 (25.4x); ANSGR.IS 2021-08 (19.9x); KARURVYSYA.NS 2021-08 (10.2x); UNS.TO 2020-03 (9.0x); 6632.T 2021-09 (8.7x); 8002.T 2021-08 (8.2x); 3026.TW 2024-05 (7.7x); 002281.SZ 2024-05 (7.0x)

**Archetype 0** — 50% of multibaggers, lift 0.99x, blow-up 8%
- axes (vs all month-ends, + = more): size -0.12, vs_market -0.10, industry_laggard +0.10, fallen +0.09, ignition -0.09, volatility +0.09, divergence +0.07, neglect +0.06, industry_cheap +0.04, cheap_vs_own_history +0.03
- most distinctive features (rank vs all): downgrades_12m +0.24, upgrades_12m +0.24, months_since_up +0.11, gap_own_roic +0.09, vol52 +0.09, dd_time_share_260 +0.09, gap_own_opm +0.08, gap_own_fcfps +0.08, gap_sales_1y +0.08, gap_sales_2y +0.08, above_ma30 -0.16, r13 -0.16, dist_hi52 -0.15, dist_hi260 -0.13, op_vs_mkt_disthi -0.13, pos104 -0.13, op_vs_ind_r26 -0.12, mcap_usd_log -0.12
- states over-represented (share, x vs all): fund_price_divergence 22% (3.7x), fallen_angel 30% (2.9x), margin_inflect_derated 10% (2.1x), turnaround 34% (1.6x), net_net 2% (1.6x), deep_value 30% (1.4x), hypergrowth 10% (1.4x), neglected 100% (1.3x)
- medians at the start: rev growth 1y 8%; rev accel (pp) -1%; op margin 9%; op margin chg 1y 0%; FCF margin 5%; P/S 1.05; EV/EBIT 14.23; P/B 1.64; net cash / mcap 3%; net debt / EBITDA -0.39; share count chg 1y 0%; ROIC 10%; price / 5y high 51%; return 1y -11%; return 2y -12%; volatility 39%; mcap (log10 $) 8.49; analysts nan; headcount growth –; op margin, own-history pct 55%; sales/share vs price 1y (log gap) 0.19; margin own-pct minus price own-pct 0.20; op-margin slope 8q 0.00; share of 5y in deep drawdown 74%; weeks since 5y low 146.00
- data present: fund 100%, val 100%, perc 0%, emp 0%, bs 100%
- examples (start, best multiple within 5y): 5803.T 2021-06 (117.8x); ISCTR.IS 2020-05 (87.1x); ALARK.IS 2018-10 (69.8x); MAVI.IS 2019-08 (64.3x); 012450.KS 2020-09 (38.6x); 6920.T 2015-09 (36.7x); THYAO.IS 2020-03 (35.9x); TURSG.IS 2018-12 (32.5x); SUZLON.NS 2019-09 (30.3x); ASUZU.IS 2020-01 (28.0x)

**Archetype 1** — 6% of multibaggers, lift 0.98x, blow-up 12%
- axes (vs all month-ends, + = more): volatility +0.22, vs_market -0.15, industry_laggard +0.15, ignition -0.14, neglect -0.12, divergence +0.11, fallen +0.09, quality_x_price +0.07, value_vs_growth +0.06, industry_cheap +0.05
- most distinctive features (rank vs all): pt_rev_6m +0.39, pt_prem_12m +0.35, vol52 +0.22, range104 +0.22, op_sec_vol +0.20, op_ind_vol +0.18, gap_sales_1y +0.18, op_v_shape +0.15, n_analysts +0.15, dvol_usd_log +0.13, gap_perc_targets -0.33, dist_hi52 -0.25, above_ma30 -0.24, r13 -0.22, r26 -0.22, rs26 -0.22, op_vs_mkt_r26 -0.22, op_vs_ind_r26 -0.20
- states over-represented (share, x vs all): fund_price_divergence 18% (3.1x), fallen_angel 30% (2.9x), margin_inflect_derated 11% (2.3x), hypergrowth 14% (2.1x), overlevered_stressed 15% (2.0x), deep_value 40% (2.0x), overlevered_delevering 3% (1.8x), cyclical_trough 5% (1.4x)
- medians at the start: rev growth 1y 6%; rev accel (pp) -3%; op margin 12%; op margin chg 1y -1%; FCF margin 6%; P/S 0.96; EV/EBIT 12.74; P/B 1.28; net cash / mcap 2%; net debt / EBITDA -0.26; share count chg 1y 0%; ROIC 10%; price / 5y high 57%; return 1y -15%; return 2y -1%; volatility 40%; mcap (log10 $) 9.08; analysts 8.00; headcount growth –; op margin, own-history pct 45%; sales/share vs price 1y (log gap) 0.28; margin own-pct minus price own-pct 0.17; op-margin slope 8q 0.00; share of 5y in deep drawdown 63%; weeks since 5y low 185.00
- data present: fund 100%, val 100%, perc 63%, emp 0%, bs 100%
- examples (start, best multiple within 5y): NGD.TO 2022-08 (17.0x); GENTERA.MX 2020-07 (10.3x); J&KBANK.NS 2021-09 (10.3x); AVGO 2012-12 (9.2x); ALPHA.AT 2020-10 (8.0x); NVMI.TA 2019-03 (6.9x); CCC.WA 2020-03 (6.8x); NVMI 2019-03 (6.7x); TNET 2016-02 (6.0x); AWX.SI 2024-05 (5.7x)

**Archetype 4** — 1% of multibaggers, lift 0.70x, blow-up 10%
- axes (vs all month-ends, + = more): value_vs_growth -0.32, quality_x_price -0.31, profitability -0.31, growth -0.26, below_own_cycle +0.26, efficiency_trend -0.24, best_in_own_history -0.23, sector_relative -0.23, industry_quality -0.23, industry_growth -0.21
- most distinctive features (rank vs all): op_evebit_vs_g +0.36, op_ind_evebit +0.35, ev_ebit +0.34, op_sec_evebit +0.33, kr_daysOfSalesOutstanding_d4 +0.28, kr_operatingCycle_d4 +0.25, op_wc_drift +0.25, dso_d1 +0.24, pe +0.23, kr_daysOfSalesOutstanding +0.22, opm -0.37, kr_operatingProfitMargin -0.34, op_ind_roic -0.33, tr_roic_consist -0.32, op_roic_x_fcfy -0.31, op_sec_opm -0.31, op_ind_opm -0.31, op_fcfy_plus_g -0.31
- states over-represented (share, x vs all): new_activist 44% (4.8x), expensive 44% (3.0x), headcount_growth 6% (1.7x), overlevered_stressed 12% (1.6x), cyclical_trough 6% (1.6x), cannibal 19% (1.6x), insider_buying 6% (1.2x), near_highs 38% (1.1x)
- medians at the start: rev growth 1y -7%; rev accel (pp) -7%; op margin 3%; op margin chg 1y -2%; FCF margin 4%; P/S 1.56; EV/EBIT 30.81; P/B 2.63; net cash / mcap -12%; net debt / EBITDA 1.55; share count chg 1y 0%; ROIC 4%; price / 5y high 77%; return 1y 12%; return 2y 15%; volatility 33%; mcap (log10 $) 9.18; analysts 10.00; headcount growth -2%; op margin, own-history pct 14%; sales/share vs price 1y (log gap) -0.15; margin own-pct minus price own-pct -0.35; op-margin slope 8q -0.00; share of 5y in deep drawdown 48%; weeks since 5y low 211.50
- data present: fund 100%, val 100%, perc 81%, emp 100%, bs 100%
- examples (start, best multiple within 5y): UFPT 2021-07 (5.4x); MSTR 2019-02 (5.2x); AVAV 2016-09 (4.9x); FLEX 2024-05 (4.6x); TRNS 2020-02 (4.3x); AEIS 2024-04 (4.1x); F 2020-03 (4.0x); COOP 2023-08 (3.8x); VIAV 2024-03 (3.8x); DAR 2019-03 (3.6x)

**Archetype 2** — 13% of multibaggers, lift 0.50x, blow-up 11%
- axes (vs all month-ends, + = more): volatility +0.24, vs_market -0.13, fallen +0.11, industry_laggard +0.10, size -0.10, value_vs_growth +0.10, ignition -0.09, headcount_growth +0.09, growth +0.09, quality_x_price +0.08
- most distinctive features (rank vs all): vol52 +0.24, range104 +0.21, op_sec_vol +0.19, op_v_shape +0.19, op_ind_vol +0.19, pt_prem_12m +0.16, dd_time_share_260 +0.15, gap_own_gm +0.12, gap_own_opm +0.12, rev_g2 +0.12, dist_hi52 -0.24, dist_hi260 -0.21, op_vs_mkt_disthi -0.21, r13 -0.20, maxdd104 -0.20, above_ma30 -0.20, op_coil -0.18, op_ind_disthi -0.17
- states over-represented (share, x vs all): headcount_growth 31% (8.4x), productivity_gain 21% (5.2x), new_activist 37% (4.1x), insider_buying 21% (4.0x), fund_price_divergence 19% (3.2x), margin_inflect_derated 12% (2.5x), cannibal 22% (1.8x), hypergrowth 11% (1.7x)
- medians at the start: rev growth 1y 11%; rev accel (pp) -2%; op margin 12%; op margin chg 1y 1%; FCF margin 10%; P/S 1.20; EV/EBIT 12.60; P/B 2.17; net cash / mcap 2%; net debt / EBITDA -0.39; share count chg 1y 0%; ROIC 15%; price / 5y high 58%; return 1y -9%; return 2y 6%; volatility 45%; mcap (log10 $) 9.20; analysts 13.00; headcount growth 6%; op margin, own-history pct 64%; sales/share vs price 1y (log gap) 0.19; margin own-pct minus price own-pct 0.17; op-margin slope 8q 0.00; share of 5y in deep drawdown 52%; weeks since 5y low 187.00
- data present: fund 100%, val 100%, perc 57%, emp 100%, bs 100%
- examples (start, best multiple within 5y): STRL 2021-09 (39.3x); SMCI 2021-08 (27.2x); BELFB 2021-06 (18.3x); MELI 2016-01 (17.2x); ABMD 2013-02 (15.6x); IESC 2020-03 (14.9x); NVDA 2014-08 (14.6x); GPI 2020-03 (10.0x); URI 2020-03 (9.5x); DECK 2020-03 (9.3x)

# 2. Patterns by lift, whole operator population


### 3x within 24 months

| pattern                                                                                             |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                                                                                               |
|:----------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|--------------:|----------------------:|-----------------:|--------------:|:-------------------------------------------------------------------------------------------------------------------------------------------------------|
| rd_rev HIGH & n_analysts HIGH & op_ind_vol HIGH & gap_sales_3y LOW                                  |            4 | 12.359 |                 0.001 |                      114 |         0.164 |                13.924 |            0.812 |         0.16  | NVDA 2019-08 (29.6x); TRIL.NS 2022-10 (11.2x); 5803.T 2023-02 (9.6x); 012450.KS 2023-07 (8.5x); 002281.SZ 2024-05 (7.0x); 6857.T 2024-08 (5.3x)        |
| vol52 HIGH & n_analysts HIGH & kr_fixedAssetTurnover_own HIGH & gap_sales_3y LOW                    |            4 | 12.006 |                 0.001 |                       88 |       nan     |                12.313 |            0.399 |         0.182 | 5803.T 2024-02 (14.3x); 000150.KS 2024-04 (11.3x); NVDA 2023-10 (4.6x); BPE.MI 2023-12 (4.4x); J&KBANK.NS 2023-03 (4.2x); BBD-B.TO 2024-03 (4.1x)      |
| vol52 HIGH & n_analysts HIGH & op_sec_accel HIGH & gap_sales_3y LOW                                 |            4 | 11.985 |                 0.001 |                      100 |       nan     |                11.853 |            0.224 |         0.2   | 5803.T 2023-10 (18.0x); CS.TO 2019-03 (11.1x); 012450.KS 2023-07 (8.5x); NGD.TO 2024-08 (4.4x); BPE.MI 2023-12 (4.4x); NVDA 2023-12 (3.8x)             |
| dvol_z13 HIGH & op_ind_vol HIGH & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                 |            4 | 11.929 |                 0.001 |                       97 |         0.187 |                15.42  |            0.944 |         0.064 | BELFB 2021-07 (20.3x); CLS 2023-12 (10.4x); CLS.TO 2023-09 (10.2x); GPI 2020-03 (10.0x); TRIL.NS 2023-05 (9.3x); TSLA 2020-05 (7.4x)                   |
| vol52 HIGH & opm_d1 HIGH & n_analysts HIGH & gap_sales_3y LOW                                       |            4 | 11.887 |                 0.001 |                      106 |       nan     |                11.162 |            0.56  |         0.18  | 5803.T 2023-10 (18.0x); NVDA 2019-01 (12.4x); CS.TO 2019-01 (11.8x); 012450.KS 2023-12 (7.2x); J&KBANK.NS 2023-02 (4.6x); NGD.TO 2024-08 (4.4x)        |
| n_analysts HIGH & op_sec_vol HIGH & op_vs_ind_disthi HIGH & gap_sales_3y LOW                        |            4 | 11.591 |                 0.001 |                       96 |       nan     |                13.809 |            0.527 |         0.14  | 5803.T 2023-10 (18.0x); 000150.KS 2024-04 (11.3x); TRIL.NS 2022-10 (11.2x); 012450.KS 2023-07 (8.5x); 002281.SZ 2024-05 (7.0x); 6857.T 2024-08 (5.3x)  |
| as_pb_own HIGH & op_coil LOW & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                    |            4 | 11.428 |                 0.001 |                       90 |         0.007 |                15.42  |            1.028 |         0.055 | CLS 2023-10 (13.3x); 5801.T 2024-09 (10.3x); CLS.TO 2023-09 (10.2x); TRIL.NS 2023-07 (8.1x); STRL 2024-05 (7.0x); POWL 2024-06 (5.9x)                  |
| n_analysts HIGH & op_sec_vol HIGH & op_sec_size HIGH & kr_currentRatio_d4 LOW                       |            4 | 11.261 |                 0.001 |                      106 |       nan     |                12.773 |            0.531 |         0.129 | NVDA 2022-10 (10.2x); 2059.TW 2024-07 (10.1x); 012450.KS 2023-07 (8.5x); 3653.TW 2022-12 (3.9x); 6857.T 2023-02 (3.6x); 300033.SZ 2024-06 (3.4x)       |
| vol52 HIGH & roe HIGH & n_analysts HIGH & gap_sales_3y LOW                                          |            4 | 11.098 |                 0.001 |                      116 |       nan     |                13.234 |            0.637 |         0.177 | NVDA 2019-08 (29.6x); 5803.T 2023-10 (18.0x); 2059.TW 2024-07 (10.1x); 012450.KS 2023-07 (8.5x); 6857.T 2024-08 (5.3x); TSLA 2022-12 (3.5x)            |
| n_analysts HIGH & op_ind_vol HIGH & kr_researchAndDevelopementToRevenue HIGH & gap_sales_2y LOW     |            4 | 10.987 |                 0.001 |                      102 |         0     |                15.19  |            0.65  |         0.135 | 5803.T 2023-10 (18.0x); 012450.KS 2023-07 (8.5x); TSLA 2020-05 (7.4x); 002281.SZ 2024-06 (5.9x); 6857.T 2024-08 (5.3x); NVDA 2023-10 (4.6x)            |
| n_analysts HIGH & op_sec_vol HIGH & kr_daysOfInventoryOutstanding HIGH & gap_sales_2y LOW           |            4 | 10.979 |                 0.001 |                       95 |       nan     |                16.341 |            0.771 |         0.096 | 012450.KS 2023-07 (8.5x); 2059.TW 2024-05 (6.3x); 002281.SZ 2024-06 (5.9x); 6857.T 2024-08 (5.3x); 7012.T 2024-02 (5.0x); BBD-B.TO 2024-03 (4.1x)      |
| dist_hi260 HIGH & vol52 HIGH & n_analysts HIGH & gap_sales_3y LOW                                   |            4 | 10.952 |                 0.001 |                       94 |       nan     |                14.384 |            0.516 |         0.117 | 5803.T 2024-02 (14.3x); 000150.KS 2024-04 (11.3x); TRIL.NS 2022-10 (11.2x); 012450.KS 2023-07 (8.5x); 002281.SZ 2024-05 (7.0x); 7012.T 2024-02 (5.0x)  |
| n_analysts HIGH & op_sec_vol HIGH & tr_shares_consist HIGH & gap_sales_3y LOW                       |            4 | 10.947 |                 0.001 |                       83 |       nan     |                13.119 |            0.419 |         0.145 | 5803.T 2023-10 (18.0x); 012450.KS 2023-07 (8.5x); 6857.T 2024-08 (5.3x); 7012.T 2024-02 (5.0x); J&KBANK.NS 2023-02 (4.6x); NGD.TO 2024-08 (4.4x)       |
| vol52 HIGH & n_analysts HIGH & kr_returnOnEquity_d4 HIGH & gap_sales_3y LOW                         |            4 | 10.925 |                 0.001 |                      107 |         0     |                13.809 |            0.395 |         0.12  | 5803.T 2024-06 (11.8x); 000150.KS 2024-04 (11.3x); 2059.TW 2024-07 (10.1x); 012450.KS 2023-07 (8.5x); 6857.T 2024-09 (4.7x); NVDA 2023-10 (4.6x)       |
| vol52 HIGH & n_analysts HIGH & op_coil LOW & op_sec_disthi HIGH                                     |            4 | 10.903 |                 0.001 |                       94 |       nan     |                12.543 |            0.406 |         0.128 | 5803.T 2024-02 (14.3x); 000150.KS 2024-04 (11.3x); TRIL.NS 2022-10 (11.2x); 012450.KS 2023-07 (8.5x); TSLA 2020-05 (7.4x); 6857.T 2024-08 (5.3x)       |
| vol52 HIGH & n_analysts HIGH & tr_opm_streak HIGH & gap_sales_3y LOW                                |            4 | 10.845 |                 0.001 |                       84 |       nan     |                10.472 |            0.287 |         0.2   | 5803.T 2023-10 (18.0x); 012450.KS 2024-03 (6.7x); J&KBANK.NS 2023-02 (4.6x); TSLA 2020-07 (4.3x); ISCTR.IS 2023-02 (4.2x); BBD-B.TO 2024-03 (4.1x)     |
| vol52 HIGH & op_coil LOW & kr_operatingCycle HIGH & gap_perc_buyshare HIGH                          |            4 | 10.742 |                 0.001 |                       90 |         0.089 |                12.198 |            0.481 |         0.129 | BGFV 2020-04 (32.7x); BELFB 2021-06 (18.3x); COOP 2020-03 (15.7x); CLS.TO 2023-09 (10.2x); 012450.KS 2023-07 (8.5x); TRIL.NS 2023-07 (8.1x)            |
| n_analysts HIGH & op_sec_vol HIGH & ind_tape_opm_d1 LOW & gap_sales_3y LOW                          |            4 | 10.739 |                 0.001 |                       91 |       nan     |                12.888 |            0.749 |         0.082 | NVDA 2019-08 (29.6x); 002281.SZ 2024-05 (7.0x); 5803.T 2024-09 (6.0x); 6857.T 2024-08 (5.3x); J&KBANK.NS 2023-02 (4.6x); BPE.MI 2023-12 (4.4x)         |
| up_lo52 HIGH & op_coil LOW & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH |            4 | 10.727 |                 0.001 |                       82 |         0.08  |                14.73  |            0.67  |         0.082 | CLS 2023-10 (13.3x); 000150.KS 2024-04 (11.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); POWL 2024-06 (5.9x); NGD.TO 2024-06 (5.6x)                 |
| maxdd104 LOW & vol52 HIGH & kr_operatingCycle HIGH & gap_perc_buyshare HIGH                         |            4 | 10.723 |                 0.001 |                       88 |         0.12  |                12.773 |            0.146 |         0.171 | BGFV 2020-04 (32.7x); BELFB 2021-07 (20.3x); COOP 2020-03 (15.7x); TPC 2024-04 (4.9x); SEAS 2020-03 (4.8x); GES 2020-03 (4.7x)                         |
| rev_g1 HIGH & n_analysts HIGH & op_sec_vol HIGH & gap_sales_3y LOW                                  |            4 | 10.723 |                 0.001 |                       89 |       nan     |                13.809 |            0.172 |         0.305 | NVDA 2019-04 (19.9x); 5803.T 2023-08 (12.4x); 000150.KS 2024-05 (9.7x); 012450.KS 2023-07 (8.5x); NGD.TO 2024-08 (4.4x); BPE.MI 2023-12 (4.4x)         |
| vol52 HIGH & n_analysts HIGH & kr_intangiblesToTotalAssets_own LOW & gap_sales_3y LOW               |            4 | 10.716 |                 0.001 |                       93 |         0.167 |                15.19  |            0.561 |         0.139 | NVDA 2019-08 (29.6x); CS.TO 2019-01 (11.8x); 012450.KS 2023-07 (8.5x); 002281.SZ 2024-05 (7.0x); MEG.TO 2021-02 (4.7x); J&KBANK.NS 2023-02 (4.6x)      |
| maxdd104 LOW & vol52 HIGH & n_analysts HIGH & gap_sales_3y LOW                                      |            4 | 10.663 |                 0.001 |                       77 |         0.191 |                13.349 |            0.56  |         0.16  | NVDA 2019-08 (29.6x); CS.TO 2019-01 (11.8x); MEG.TO 2021-02 (4.7x); J&KBANK.NS 2023-02 (4.6x); NGD.TO 2024-08 (4.4x); BBD-B.TO 2024-03 (4.1x)          |
| n_analysts HIGH & op_sec_vol HIGH & gap_sales_3y LOW & accumulation                                 |            4 | 10.628 |                 0.001 |                      104 |       nan     |                13.694 |            0.398 |         0.1   | 5803.T 2023-10 (18.0x); TRIL.NS 2022-10 (11.2x); 000150.KS 2024-05 (9.7x); 012450.KS 2023-07 (8.5x); J&KBANK.NS 2023-02 (4.6x); 2059.TW 2024-04 (4.6x) |
| vol52 HIGH & kr_operatingCycle HIGH & tr_opm_accel HIGH & gap_perc_buyshare HIGH                    |            4 | 10.558 |                 0.001 |                       94 |         0.058 |                12.658 |            0.167 |         0.206 | BELFB 2021-06 (18.3x); COOP 2020-03 (15.7x); TRIL.NS 2023-07 (8.1x); ASM.AS 2020-02 (7.1x); 012450.KS 2024-03 (6.7x); LSCC 2020-02 (5.0x)              |

### 10x within 5 years

| pattern                                                                                                         |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                                                                                                   |
|:----------------------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|--------------:|----------------------:|-----------------:|--------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| op_ind_growth LOW & op_vs_ind_growth LOW & kr_solvencyRatio_d4 LOW & tr_debt_streak LOW                         |            4 | 28.007 |                 0.001 |                       36 |         0.26  |                21.289 |            0.484 |         0.094 | ALARK.IS 2018-08 (51.1x); SUZLON.NS 2019-12 (38.9x); CLS.TO 2020-08 (24.3x); GARAN.IS 2021-02 (21.1x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x)     |
| kr_daysOfSalesOutstanding_d4 LOW & kr_operatingCycle_d4 LOW & kr_inventoryTurnover_d4 HIGH & tr_debt_streak LOW |            4 | 24.774 |                 0.001 |                       32 |         0.23  |                21.174 |            0.312 |         0.112 | TTRAK.IS 2020-03 (62.5x); ASUZU.IS 2020-03 (40.7x); AGHOL.IS 2020-10 (24.4x); CELH 2020-06 (22.5x); CS.TO 2019-05 (19.1x); ISMEN.IS 2020-03 (14.8x)        |
| r52 LOW & op_ind_growth LOW & tr_debt_streak LOW & neglected                                                    |            4 | 23.826 |                 0.001 |                       30 |         0.222 |                22.785 |            0.47  |         0.184 | SUZLON.NS 2019-12 (38.9x); GARAN.IS 2021-02 (21.1x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x); AKBNK.IS 2020-08 (16.7x); OTKAR.IS 2018-07 (16.7x)   |
| op_sec_size LOW & op_ind_size LOW & tr_debt_streak LOW & deep_value                                             |            4 | 22.895 |                 0.001 |                       40 |         0.213 |                21.174 |            0.583 |         0.139 | ISCTR.IS 2020-07 (89.8x); TURSG.IS 2020-03 (47.6x); ASUZU.IS 2020-03 (40.7x); SASA.IS 2015-10 (35.3x); LMB 2020-06 (34.2x); MAVI.IS 2020-03 (32.6x)        |
| ma30_slope13 LOW & kr_solvencyRatio_d4 LOW & tr_debt_streak LOW                                                 |            3 | 22.815 |                 0.001 |                       29 |         0.212 |                23.015 |            0.43  |         0.212 | ALARK.IS 2018-08 (51.1x); SUZLON.NS 2019-12 (38.9x); GARAN.IS 2020-08 (25.2x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x); OTKAR.IS 2018-07 (16.7x)   |
| op_ind_size LOW & kr_priceToSalesRatio LOW & tr_debt_streak LOW & neglected                                     |            4 | 22.421 |                 0.001 |                       38 |         0.209 |                20.829 |            0.504 |         0.087 | ISCTR.IS 2020-07 (89.8x); TURSG.IS 2020-03 (47.6x); ASUZU.IS 2020-03 (40.7x); SASA.IS 2015-10 (35.3x); MAVI.IS 2020-03 (32.6x); AC.TO 2012-08 (20.1x)      |
| ma30_slope13 LOW & op_ind_growth LOW & op_vs_ind_growth LOW & tr_debt_streak LOW                                |            4 | 22.236 |                 0.001 |                       30 |         0.207 |                23.82  |            0.461 |         0.185 | ALARK.IS 2018-08 (51.1x); SUZLON.NS 2019-12 (38.9x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x); GARAN.IS 2020-12 (17.7x); AKBNK.IS 2020-08 (16.7x)   |
| ps LOW & kr_payablesTurnover_d4 HIGH & tr_debt_streak LOW                                                       |            3 | 22.057 |                 0.001 |                       31 |         0.205 |                20.713 |            0.526 |         0.131 | ISCTR.IS 2020-10 (84.4x); TURSG.IS 2020-03 (47.6x); ASUZU.IS 2020-03 (40.7x); SUZLON.NS 2019-11 (33.0x); MAVI.IS 2020-04 (30.2x); AGHOL.IS 2020-10 (24.4x) |
| r52 LOW & op_sec_r52 LOW & kr_solvencyRatio_d4 LOW & tr_debt_streak LOW                                         |            4 | 21.702 |                 0.001 |                       27 |         0.202 |                21.404 |            0.527 |         0.175 | SUZLON.NS 2019-12 (38.9x); GARAN.IS 2020-07 (23.9x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x); CS.TO 2019-05 (19.1x); OTKAR.IS 2018-07 (16.7x)      |
| vol52 HIGH & op_sec_vol HIGH & tr_debt_streak LOW & deep_value                                                  |            4 | 21.687 |                 0.001 |                       33 |         0.202 |                21.864 |            0.489 |         0.218 | TURSG.IS 2020-03 (47.6x); LMB 2020-06 (34.2x); MAVI.IS 2020-03 (32.6x); ASUZU.IS 2020-05 (28.8x); CLS.TO 2020-08 (24.3x); AC.TO 2012-08 (20.1x)            |
| kr_taxBurden_own LOW & tr_debt_streak LOW & deep_value                                                          |            3 | 21.647 |                 0.001 |                       35 |         0.201 |                22.325 |            0.381 |         0.146 | ISCTR.IS 2020-10 (84.4x); TURSG.IS 2020-03 (47.6x); LMB 2020-06 (34.2x); MAVI.IS 2020-10 (31.6x); ALARK.IS 2020-08 (27.8x); AGHOL.IS 2020-10 (24.4x)       |
| kr_effectiveTaxRate HIGH & tr_debt_streak LOW & deep_value                                                      |            3 | 21.467 |                 0.001 |                       36 |         0.2   |                21.634 |            0.463 |         0.157 | ISCTR.IS 2020-10 (84.4x); TURSG.IS 2020-03 (47.6x); LMB 2020-06 (34.2x); ALARK.IS 2020-08 (27.8x); AGHOL.IS 2020-10 (24.4x); CLS.TO 2020-08 (24.3x)        |
| kr_returnOnAssets_d4 LOW & kr_returnOnTangibleAssets_d4 LOW & kr_priceToEarningsRatio LOW & tr_debt_streak LOW  |            4 | 21.308 |                 0.001 |                       30 |         0.198 |                21.174 |            0.294 |         0.24  | ALARK.IS 2018-08 (51.1x); SUZLON.NS 2019-12 (38.9x); CLS.TO 2020-08 (24.3x); MAVI.IS 2020-12 (22.9x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x)      |
| maxdd104 LOW & kr_daysOfInventoryOutstanding_d4 LOW & tr_debt_streak LOW                                        |            3 | 21.282 |                 0.001 |                       27 |         0.198 |                22.44  |            0.382 |         0.187 | TTRAK.IS 2020-03 (62.5x); SUZLON.NS 2019-12 (38.9x); MAVI.IS 2020-04 (30.2x); AGHOL.IS 2020-10 (24.4x); CS.TO 2019-05 (19.1x); AC.TO 2012-06 (17.5x)       |
| pos156 LOW & kr_solvencyRatio_d4 LOW & tr_debt_streak LOW                                                       |            3 | 21.021 |                 0.001 |                       26 |         0.196 |                21.519 |            0.456 |         0.21  | SUZLON.NS 2019-12 (38.9x); GARAN.IS 2020-08 (25.2x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x); CS.TO 2019-05 (19.1x); OTKAR.IS 2018-07 (16.7x)      |
| kr_solvencyRatio_d4 LOW & kr_revenuePerShare_own LOW & tr_debt_streak LOW                                       |            3 | 20.864 |                 0.001 |                       26 |         0.194 |                21.174 |            0.332 |         0.127 | SUZLON.NS 2019-12 (38.9x); CLS.TO 2020-08 (24.3x); TAVHL.IS 2020-10 (20.5x); CS.TO 2019-05 (19.1x); CLS 2020-06 (19.1x); OTKAR.IS 2018-07 (16.7x)          |
| tr_debt_streak LOW & accelerating & neglected & deep_value                                                      |            4 | 20.851 |                 0.001 |                       42 |         0.194 |                21.404 |            0.407 |         0.064 | ISCTR.IS 2020-10 (84.4x); TURSG.IS 2020-03 (47.6x); ASUZU.IS 2020-03 (40.7x); SASA.IS 2015-10 (35.3x); MAVI.IS 2020-10 (31.6x); GARAN.IS 2020-08 (25.2x)   |
| rev_g2 LOW & earn_yield LOW & tr_debt_streak LOW                                                                |            3 | 20.821 |                 0.001 |                       26 |         0.194 |                17.491 |            0.304 |         0.089 | TTRAK.IS 2020-03 (62.5x); SUZLON.NS 2019-12 (38.9x); CLS.TO 2020-08 (24.3x); ASUZU.IS 2020-09 (22.8x); CS.TO 2019-05 (19.1x); CLS 2020-06 (19.1x)          |
| ebit_g1 LOW & kr_priceToEarningsRatio LOW & tr_debt_streak LOW                                                  |            3 | 20.81  |                 0.001 |                       34 |         0.194 |                21.059 |            0.46  |         0.137 | ALARK.IS 2018-08 (51.1x); SUZLON.NS 2019-12 (38.9x); LMB 2020-06 (34.2x); MAVI.IS 2020-10 (31.6x); CLS.TO 2020-08 (24.3x); TAVHL.IS 2020-10 (20.5x)        |
| op_ind_vol HIGH & kr_returnOnAssets_d4 LOW & tr_debt_streak LOW                                                 |            3 | 20.76  |                 0.001 |                       27 |         0.193 |                20.483 |            0.461 |         0.261 | SUZLON.NS 2019-12 (38.9x); CLS.TO 2020-08 (24.3x); MAVI.IS 2020-12 (22.9x); CELH 2020-06 (22.5x); TAVHL.IS 2020-10 (20.5x); AC.TO 2012-08 (20.1x)          |
| rev_g2 LOW & tr_fcfm_streak HIGH & tr_debt_streak LOW                                                           |            3 | 20.721 |                 0.001 |                       28 |         0.193 |                17.261 |            0.154 |         0.154 | ISCTR.IS 2019-08 (78.4x); TTRAK.IS 2020-03 (62.5x); SUZLON.NS 2019-12 (38.9x); MSTR 2020-06 (33.4x); CLS.TO 2020-08 (24.3x); CLS 2020-06 (19.1x)           |
| maxdd104 LOW & kr_inventoryTurnover_d4 HIGH & tr_debt_streak LOW                                                |            3 | 20.712 |                 0.001 |                       27 |         0.193 |                21.059 |            0.361 |         0.194 | TTRAK.IS 2020-03 (62.5x); SUZLON.NS 2019-11 (33.0x); MAVI.IS 2020-06 (25.5x); AGHOL.IS 2020-10 (24.4x); AC.TO 2012-08 (20.1x); CS.TO 2019-05 (19.1x)       |
| r52 LOW & tr_revg_slope8 LOW & tr_debt_streak LOW                                                               |            3 | 20.661 |                 0.001 |                       26 |         0.192 |                22.325 |            0.478 |         0.242 | SUZLON.NS 2019-12 (38.9x); GARAN.IS 2021-02 (21.1x); CS.TO 2019-05 (19.1x); TAVHL.IS 2020-08 (17.9x); OTKAR.IS 2018-07 (16.7x); 4961.TW 2016-12 (12.2x)    |
| kr_operatingReturnOnAssets_d4 LOW & kr_priceToEarningsRatio LOW & tr_debt_streak LOW                            |            3 | 20.369 |                 0.001 |                       27 |         0.189 |                21.174 |            0.381 |         0.123 | SUZLON.NS 2019-12 (38.9x); MAVI.IS 2020-10 (31.6x); CLS.TO 2020-08 (24.3x); TAVHL.IS 2020-10 (20.5x); CS.TO 2019-05 (19.1x); CLS 2020-06 (19.1x)           |
| kr_freeCashFlowYield_own HIGH & kr_returnOnAssets_d4 LOW & tr_debt_streak LOW                                   |            3 | 20.306 |                 0.001 |                       26 |         0.189 |                20.713 |            0.386 |         0.191 | ALARK.IS 2018-08 (51.1x); SUZLON.NS 2019-11 (33.0x); CLS.TO 2020-08 (24.3x); MAVI.IS 2020-12 (22.9x); AC.TO 2012-08 (20.1x); CS.TO 2019-05 (19.1x)         |

# 6. Refining the operator archetypes with the new measures


## wave_neglected_value_accel: n=26,867, rate 4.93% (lift 1.31x), blow-up 7%, 10x/5y 1.5%

raises the rate most:

| condition                               |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:----------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| gap_perc_buyshare HIGH                  |  211 |       38 |  0.178 |               3.608 |         0.077 |
| buy_share HIGH                          |  682 |       81 |  0.114 |               2.314 |         0.084 |
| last_react HIGH                         | 1348 |      120 |  0.095 |               1.933 |         0.098 |
| tr_debt_streak LOW                      |  326 |       30 |  0.091 |               1.843 |         0.097 |
| pb HIGH                                 | 1274 |      126 |  0.086 |               1.736 |         0.091 |
| net_net                                 | 1517 |      166 |  0.085 |               1.715 |         0.041 |
| maxdd104 LOW                            | 5198 |      446 |  0.081 |               1.64  |         0.146 |
| up_lo52 HIGH                            | 4766 |      364 |  0.08  |               1.628 |         0.095 |
| vol52 HIGH                              | 5409 |      443 |  0.08  |               1.627 |         0.144 |
| op_v_shape HIGH                         | 5277 |      419 |  0.08  |               1.619 |         0.123 |
| kr_stockBasedCompensationToRevenue HIGH | 1640 |      155 |  0.08  |               1.616 |         0.097 |
| accumulation                            | 2759 |      215 |  0.079 |               1.602 |         0.059 |

lowers it most:

| condition                                  |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| dd_time_share_260 LOW                      | 3767 |       78 |  0.02  |               0.403 |         0.042 |
| op_ind_ps HIGH                             | 1491 |       40 |  0.02  |               0.407 |         0.053 |
| range104 LOW                               | 5451 |      162 |  0.022 |               0.439 |         0.035 |
| vol52 LOW                                  | 5519 |      160 |  0.022 |               0.44  |         0.031 |
| op_sec_vol LOW                             | 5883 |      200 |  0.026 |               0.532 |         0.033 |
| flat_base                                  | 8475 |      315 |  0.026 |               0.536 |         0.043 |
| op_ind_vol LOW                             | 6066 |      208 |  0.027 |               0.554 |         0.033 |
| maxdd104 HIGH                              | 4991 |      169 |  0.028 |               0.563 |         0.032 |
| kr_stockBasedCompensationToRevenue_own LOW |  964 |       29 |  0.028 |               0.574 |         0.133 |
| rd_rev LOW                                 | 4325 |      153 |  0.03  |               0.601 |         0.025 |
| op_ind_size HIGH                           | 3665 |      117 |  0.03  |               0.607 |         0.072 |
| kr_cashConversionCycle LOW                 | 5784 |      224 |  0.03  |               0.61  |         0.068 |

## leader_in_wave: n=783, rate 15.37% (lift 4.09x), blow-up 24%, 10x/5y 1.1%

raises the rate most:

| condition                                    |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------------------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| op_sec_disthi HIGH                           | 176 |       53 |  0.312 |               2.027 |         0.264 |
| kr_currentRatio_d4 LOW                       | 187 |       61 |  0.31  |               2.016 |         0.288 |
| kr_enterpriseValueMultiple_own HIGH          | 130 |       36 |  0.3   |               1.952 |         0.265 |
| kr_evToEBITDA_own HIGH                       | 130 |       36 |  0.3   |               1.952 |         0.265 |
| kr_quickRatio_d4 LOW                         | 185 |       58 |  0.295 |               1.922 |         0.291 |
| kr_researchAndDevelopementToRevenue_own HIGH | 172 |       46 |  0.294 |               1.909 |         0.209 |
| op_ind_disthi HIGH                           | 188 |       53 |  0.293 |               1.903 |         0.227 |
| kr_currentRatio_own LOW                      | 139 |       38 |  0.289 |               1.877 |         0.189 |
| kr_debtToCapitalRatio_d4 HIGH                | 135 |       37 |  0.285 |               1.856 |         0.371 |
| kr_cashRatio_d4 LOW                          | 174 |       50 |  0.284 |               1.847 |         0.294 |
| kr_workingCapitalTurnoverRatio_own HIGH      | 175 |       47 |  0.278 |               1.811 |         0.21  |
| pos156 HIGH                                  | 205 |       56 |  0.274 |               1.781 |         0.193 |

lowers it most:

| condition                                 |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:------------------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| rev_g2 HIGH                               | 439 |       39 |  0.084 |               0.546 |         0.277 |
| kr_daysOfSalesOutstanding LOW             | 246 |       25 |  0.086 |               0.562 |         0.348 |
| kr_capexToDepreciation_own HIGH           | 219 |       22 |  0.09  |               0.586 |         0.341 |
| kr_evToOperatingCashFlow_d4 HIGH          | 214 |       23 |  0.091 |               0.589 |         0.393 |
| as_book_growth HIGH                       | 378 |       37 |  0.092 |               0.598 |         0.286 |
| kr_bookValuePerShare_g4 HIGH              | 378 |       37 |  0.092 |               0.598 |         0.286 |
| expensive                                 | 219 |       21 |  0.098 |               0.635 |         0.385 |
| kr_operatingCashFlowCoverageRatio_d4 HIGH | 249 |       28 |  0.1   |               0.652 |         0.293 |
| kr_cashRatio_d4 HIGH                      | 238 |       25 |  0.101 |               0.655 |         0.28  |
| kr_interestCoverageRatio HIGH             | 227 |       25 |  0.103 |               0.672 |         0.255 |
| kr_operatingReturnOnAssets HIGH           | 313 |       36 |  0.104 |               0.675 |         0.242 |
| kr_assetTurnover HIGH                     | 217 |       21 |  0.104 |               0.677 |         0.362 |

## improving_unturned_sellside: n=41,341, rate 5.17% (lift 1.37x), blow-up 10%, 10x/5y 1.1%

raises the rate most:

| condition              |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|------:|---------:|-------:|--------------------:|--------------:|
| gap_perc_buyshare HIGH |  1728 |      255 |  0.142 |               2.752 |         0.06  |
| op_ind_gm HIGH         |   261 |       28 |  0.131 |               2.533 |         0.102 |
| fund_price_divergence  |   173 |       24 |  0.124 |               2.402 |         0.019 |
| hypergrowth            |  3298 |      334 |  0.108 |               2.088 |         0.161 |
| tr_debt_streak LOW     |   373 |       38 |  0.103 |               1.992 |         0.079 |
| margin_inflect_derated |  1392 |      131 |  0.1   |               1.933 |         0.141 |
| n_analysts HIGH        |  1616 |      152 |  0.098 |               1.887 |         0.043 |
| vol52 HIGH             | 10868 |      932 |  0.091 |               1.752 |         0.184 |
| div_yield LOW          |  7098 |      608 |  0.09  |               1.743 |         0.16  |
| rev_g1 LOW             |   590 |       54 |  0.09  |               1.741 |         0.069 |
| op_sec_vol HIGH        | 10418 |      885 |  0.09  |               1.732 |         0.178 |
| n_analysts LOW         |  1198 |      102 |  0.089 |               1.729 |         0.118 |

lowers it most:

| condition                                  |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| vol52 LOW                                  | 5769 |      115 |  0.016 |               0.315 |         0.037 |
| range104 LOW                               | 3976 |      112 |  0.02  |               0.388 |         0.047 |
| op_sec_vol LOW                             | 6347 |      155 |  0.021 |               0.408 |         0.038 |
| new_activist                               | 2437 |       54 |  0.022 |               0.433 |         0.117 |
| up_lo52 LOW                                | 2452 |       77 |  0.023 |               0.454 |         0.09  |
| kr_stockBasedCompensationToRevenue_own LOW | 3122 |       72 |  0.024 |               0.455 |         0.097 |
| ins_net_buy_4q LOW                         | 1616 |       47 |  0.024 |               0.461 |         0.074 |
| ins_buy_quarters_4q HIGH                   | 1145 |       28 |  0.024 |               0.462 |         0.117 |
| dd_time_share_260 LOW                      | 7974 |      224 |  0.026 |               0.496 |         0.056 |
| op_v_shape LOW                             | 6029 |      178 |  0.026 |               0.504 |         0.06  |
| op_ind_vol LOW                             | 6279 |      188 |  0.026 |               0.512 |         0.042 |
| kr_evToSales HIGH                          | 3581 |      101 |  0.027 |               0.513 |         0.158 |

## peer_worst_cheapest: n=512, rate 5.71% (lift 1.52x), blow-up 6%, 10x/5y 3.6%

raises the rate most:

| condition                |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------|----:|---------:|-------:|--------------------:|--------------:|
| kr_effectiveTaxRate HIGH | 127 |       22 |  0.153 |               2.673 |         0.037 |
| mcap_usd_log LOW         | 267 |       28 |  0.085 |               1.486 |         0.064 |
| op_sec_size LOW          | 273 |       28 |  0.082 |               1.444 |         0.064 |
| roe LOW                  | 295 |       30 |  0.081 |               1.421 |         0.08  |
| op_ind_size LOW          | 232 |       21 |  0.079 |               1.388 |         0.079 |
| kr_evToSales LOW         | 284 |       28 |  0.078 |               1.367 |         0.063 |
| kr_returnOnEquity LOW    | 234 |       23 |  0.078 |               1.358 |         0.054 |
| opm LOW                  | 243 |       24 |  0.077 |               1.343 |         0.056 |
| ev_sales LOW             | 297 |       28 |  0.075 |               1.306 |         0.064 |
| npm LOW                  | 235 |       22 |  0.073 |               1.281 |         0.069 |
| kr_priceToSalesRatio LOW | 242 |       21 |  0.071 |               1.251 |         0.024 |
| ncav_mcap HIGH           | 283 |       25 |  0.069 |               1.213 |         0.04  |

lowers it most:

| condition               |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:------------------------|----:|---------:|-------:|--------------------:|--------------:|
| op_ind_ps LOW           | 308 |       21 |  0.049 |               0.867 |         0.051 |
| op_ind_pb LOW           | 471 |       29 |  0.052 |               0.902 |         0.058 |
| neglected               | 488 |       32 |  0.053 |               0.934 |         0.055 |
| op_sec_roic LOW         | 342 |       23 |  0.054 |               0.95  |         0.076 |
| op_ind_opm LOW          | 338 |       22 |  0.055 |               0.96  |         0.058 |
| kr_priceToBookRatio LOW | 443 |       30 |  0.055 |               0.962 |         0.06  |
| op_ind_roic LOW         | 504 |       35 |  0.058 |               1.018 |         0.062 |
| op_sec_pb LOW           | 471 |       33 |  0.058 |               1.02  |         0.061 |
| deep_value              | 485 |       34 |  0.059 |               1.038 |         0.053 |
| roic LOW                | 340 |       25 |  0.061 |               1.07  |         0.061 |
| pb LOW                  | 447 |       33 |  0.062 |               1.087 |         0.063 |
| dvol_usd_log LOW        | 285 |       23 |  0.065 |               1.145 |         0.056 |

## margin_inflect_weak_tape: n=21,526, rate 4.46% (lift 1.19x), blow-up 13%, 10x/5y 1.4%

raises the rate most:

| condition          |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------|-----:|---------:|-------:|--------------------:|--------------:|
| evs_chg_1y HIGH    |  622 |       69 |  0.109 |               2.453 |         0.107 |
| pos156 HIGH        | 1080 |       86 |  0.08  |               1.802 |         0.119 |
| pos104 HIGH        |  916 |       73 |  0.079 |               1.778 |         0.129 |
| above_ma30 HIGH    |  382 |       31 |  0.077 |               1.737 |         0.12  |
| trend_r2_52 HIGH   | 1789 |      140 |  0.077 |               1.736 |         0.112 |
| wks_since_hi52 LOW | 1219 |       98 |  0.076 |               1.715 |         0.098 |
| op_base_age LOW    | 1219 |       98 |  0.076 |               1.715 |         0.098 |
| fallen_angel       | 4522 |      361 |  0.076 |               1.696 |         0.146 |
| gap_eps_1y LOW     |  754 |       64 |  0.075 |               1.692 |         0.104 |
| ma30_slope13 HIGH  | 2018 |      156 |  0.075 |               1.684 |         0.134 |
| r13 HIGH           |  272 |       22 |  0.075 |               1.683 |         0.106 |
| net_net            |  360 |       32 |  0.074 |               1.656 |         0.067 |

lowers it most:

| condition                                  |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| vol52 LOW                                  | 2287 |       49 |  0.017 |               0.385 |         0.072 |
| sbc_rev LOW                                | 1383 |       34 |  0.021 |               0.47  |         0.141 |
| op_sec_vol LOW                             | 2590 |       69 |  0.022 |               0.494 |         0.069 |
| kr_stockBasedCompensationToRevenue_own LOW | 1576 |       36 |  0.023 |               0.514 |         0.122 |
| insider_buying                             |  796 |       20 |  0.023 |               0.518 |         0.146 |
| new_activist                               | 1602 |       44 |  0.023 |               0.522 |         0.207 |
| bo_new_holders_12m HIGH                    |  948 |       28 |  0.024 |               0.54  |         0.19  |
| op_ind_vol LOW                             | 2747 |       83 |  0.025 |               0.552 |         0.068 |
| kr_stockBasedCompensationToRevenue LOW     | 1524 |       45 |  0.026 |               0.581 |         0.102 |
| flat_base                                  | 5528 |      196 |  0.027 |               0.603 |         0.105 |
| ignored_beats_2y LOW                       | 1484 |       53 |  0.029 |               0.641 |         0.173 |
| emp_g1 LOW                                 |  648 |       21 |  0.029 |               0.65  |         0.212 |

## sequence_preignition: n=39,489, rate 5.60% (lift 1.49x), blow-up 13%, 10x/5y 1.4%

raises the rate most:

| condition              |     n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|------:|---------:|-------:|--------------------:|--------------:|
| tr_debt_streak LOW     |   399 |       43 |  0.104 |               1.853 |         0.124 |
| net_net                |   763 |       90 |  0.098 |               1.756 |         0.05  |
| gap_perc_buyshare HIGH |  1115 |      124 |  0.091 |               1.622 |         0.117 |
| fund_price_divergence  |  6150 |      576 |  0.086 |               1.529 |         0.123 |
| n_analysts LOW         |  1675 |      160 |  0.082 |               1.472 |         0.134 |
| fallen_angel           | 10297 |      902 |  0.082 |               1.467 |         0.13  |
| up_lo52 HIGH           |  5024 |      408 |  0.08  |               1.431 |         0.18  |
| above_ma30 HIGH        |  2152 |      175 |  0.079 |               1.408 |         0.146 |
| op_sec_size LOW        | 10522 |      896 |  0.079 |               1.406 |         0.137 |
| vol52 HIGH             | 11095 |      903 |  0.079 |               1.402 |         0.202 |
| mcap_usd_log LOW       | 10724 |      908 |  0.078 |               1.395 |         0.138 |
| op_ind_size LOW        | 10546 |      875 |  0.077 |               1.369 |         0.135 |

lowers it most:

| condition                                  |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| kr_stockBasedCompensationToRevenue_own LOW | 2754 |       67 |  0.023 |               0.414 |         0.142 |
| productivity_gain                          | 2745 |       76 |  0.025 |               0.448 |         0.176 |
| buyback_yield LOW                          | 2543 |       75 |  0.026 |               0.473 |         0.183 |
| rev_per_emp_g1 HIGH                        | 2746 |       83 |  0.027 |               0.483 |         0.16  |
| kr_stockBasedCompensationToRevenue LOW     | 2852 |       92 |  0.028 |               0.499 |         0.12  |
| bo_increasing_12m HIGH                     | 1312 |       45 |  0.029 |               0.513 |         0.187 |
| emp_g1 LOW                                 | 2148 |       75 |  0.029 |               0.523 |         0.172 |
| downgrades_12m HIGH                        | 1914 |       64 |  0.03  |               0.536 |         0.183 |
| upgrades_12m HIGH                          | 1880 |       63 |  0.031 |               0.547 |         0.169 |
| range104 LOW                               | 5374 |      248 |  0.032 |               0.565 |         0.075 |
| new_activist                               | 3095 |      116 |  0.032 |               0.577 |         0.197 |
| bo_new_holders_12m HIGH                    | 1877 |       71 |  0.033 |               0.585 |         0.195 |

## tree_recipe: n=4,923, rate 11.61% (lift 3.09x), blow-up 21%, 10x/5y 4.1%

raises the rate most:

| condition                      |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| buy_share LOW                  | 146 |       59 |  0.388 |               3.346 |         0.218 |
| n_analysts LOW                 | 453 |      111 |  0.244 |               2.104 |         0.33  |
| op_roic_x_fcfy HIGH            | 690 |      152 |  0.226 |               1.945 |         0.245 |
| kr_capexToDepreciation_own LOW | 513 |      108 |  0.221 |               1.907 |         0.228 |
| op_capex_rolloff LOW           | 160 |       31 |  0.217 |               1.871 |         0.207 |
| fund_price_divergence          | 952 |      195 |  0.216 |               1.865 |         0.189 |
| tr_fcfm_streak LOW             | 126 |       25 |  0.212 |               1.83  |         0.133 |
| new_activist                   | 638 |      129 |  0.197 |               1.701 |         0.34  |
| emp_g1 LOW                     | 583 |      109 |  0.197 |               1.698 |         0.282 |
| sbc_rev LOW                    | 571 |      117 |  0.194 |               1.671 |         0.408 |
| overlevered_stressed           | 609 |      118 |  0.192 |               1.651 |         0.331 |
| bo_new_holders_12m HIGH        | 422 |       79 |  0.191 |               1.643 |         0.372 |

lowers it most:

| condition                        |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:---------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| op_ind_pb HIGH                   | 399 |       21 |  0.048 |               0.415 |         0.251 |
| kr_inventoryTurnover_own LOW     | 474 |       20 |  0.051 |               0.435 |         0.206 |
| pb HIGH                          | 409 |       23 |  0.051 |               0.438 |         0.259 |
| hypergrowth                      | 356 |       22 |  0.052 |               0.445 |         0.319 |
| tr_debt_consist HIGH             | 614 |       33 |  0.057 |               0.488 |         0.218 |
| kr_priceToFreeCashFlowRatio HIGH | 408 |       26 |  0.058 |               0.497 |         0.196 |
| op_coil HIGH                     | 307 |       22 |  0.059 |               0.506 |         0.153 |
| op_sec_fcfy LOW                  | 840 |       48 |  0.059 |               0.508 |         0.225 |
| op_sec_pb HIGH                   | 380 |       23 |  0.06  |               0.515 |         0.284 |
| eps_g1 HIGH                      | 621 |       37 |  0.062 |               0.532 |         0.192 |
| pp_gm_x_growth HIGH              | 660 |       44 |  0.062 |               0.535 |         0.275 |
| tr_shares_consist LOW            | 754 |       51 |  0.063 |               0.544 |         0.132 |

## left_for_dead_value: n=9,092, rate 10.44% (lift 2.77x), blow-up 15%, 10x/5y 4.2%

raises the rate most:

| condition                                  |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| bo_increasing_12m HIGH                     |  228 |       60 |  0.278 |               2.666 |         0.211 |
| n_analysts LOW                             |  416 |       96 |  0.216 |               2.071 |         0.204 |
| emp_g1 HIGH                                |  267 |       60 |  0.214 |               2.053 |         0.221 |
| headcount_growth                           |  228 |       46 |  0.203 |               1.949 |         0.255 |
| bo_new_holders_12m HIGH                    |  465 |       90 |  0.194 |               1.855 |         0.306 |
| n_analysts HIGH                            |  345 |       60 |  0.177 |               1.698 |         0.092 |
| buy_share LOW                              |  506 |       90 |  0.176 |               1.687 |         0.193 |
| sbc_rev LOW                                |  939 |      170 |  0.175 |               1.673 |         0.275 |
| gap_own_fcfps LOW                          |  239 |       36 |  0.171 |               1.638 |         0.087 |
| kr_incomeQuality_d4 LOW                    | 2120 |      347 |  0.171 |               1.638 |         0.188 |
| new_activist                               |  694 |      118 |  0.169 |               1.618 |         0.263 |
| kr_stockBasedCompensationToRevenue_own LOW |  672 |      109 |  0.165 |               1.585 |         0.225 |

lowers it most:

| condition                                   |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:--------------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| kr_researchAndDevelopementToRevenue LOW     |  624 |       25 |  0.033 |               0.321 |         0.046 |
| op_ind_size HIGH                            |  584 |       24 |  0.037 |               0.355 |         0.077 |
| roe HIGH                                    | 1056 |       45 |  0.038 |               0.361 |         0.169 |
| op_sec_opm HIGH                             | 1192 |       64 |  0.045 |               0.435 |         0.159 |
| op_sec_vol LOW                              |  766 |       43 |  0.046 |               0.437 |         0.037 |
| kr_researchAndDevelopementToRevenue_own LOW |  439 |       20 |  0.046 |               0.441 |         0.054 |
| npm HIGH                                    | 1055 |       58 |  0.048 |               0.463 |         0.129 |
| opm HIGH                                    | 1226 |       70 |  0.05  |               0.482 |         0.15  |
| op_cash_gap LOW                             | 1139 |       63 |  0.051 |               0.484 |         0.134 |
| inc_margin HIGH                             |  768 |       44 |  0.051 |               0.49  |         0.141 |
| kr_debtToAssetsRatio LOW                    | 1149 |       67 |  0.052 |               0.496 |         0.133 |
| as_debt_assets LOW                          | 1149 |       67 |  0.052 |               0.496 |         0.133 |

## smart_money_wreckage: n=1,537, rate 16.44% (lift 4.37x), blow-up 27%, 10x/5y 3.9%

raises the rate most:

| condition                             |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:--------------------------------------|----:|---------:|-------:|--------------------:|--------------:|
| n_analysts LOW                        | 284 |       91 |  0.309 |               1.878 |         0.213 |
| tr_gm_streak HIGH                     | 236 |       67 |  0.289 |               1.757 |         0.211 |
| kr_daysOfInventoryOutstanding HIGH    | 292 |       85 |  0.275 |               1.674 |         0.35  |
| capex_rev_d1 HIGH                     | 204 |       58 |  0.273 |               1.661 |         0.272 |
| kr_priceToBookRatio_d4 HIGH           | 151 |       36 |  0.249 |               1.515 |         0.329 |
| kr_cashRatio LOW                      | 237 |       63 |  0.248 |               1.506 |         0.253 |
| kr_assetTurnover_d4 LOW               | 456 |      114 |  0.239 |               1.455 |         0.303 |
| gap_sales_1y LOW                      | 160 |       39 |  0.239 |               1.453 |         0.207 |
| tr_roic_accel HIGH                    | 291 |       71 |  0.237 |               1.441 |         0.293 |
| kr_daysOfInventoryOutstanding_d4 HIGH | 331 |       81 |  0.235 |               1.427 |         0.311 |
| tr_roic_streak HIGH                   | 174 |       43 |  0.231 |               1.407 |         0.278 |
| updown26 HIGH                         | 190 |       46 |  0.231 |               1.406 |         0.154 |

lowers it most:

| condition                    |   n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------------|----:|---------:|-------:|--------------------:|--------------:|
| as_debt_assets LOW           | 264 |       20 |  0.058 |               0.354 |         0.188 |
| kr_debtToAssetsRatio LOW     | 264 |       20 |  0.058 |               0.354 |         0.188 |
| cfo_ni LOW                   | 218 |       22 |  0.076 |               0.46  |         0.179 |
| netcash_mcap HIGH            | 345 |       32 |  0.076 |               0.462 |         0.17  |
| kr_evToSales_d4 LOW          | 295 |       23 |  0.078 |               0.476 |         0.189 |
| fcf_margin_d1 LOW            | 264 |       20 |  0.079 |               0.481 |         0.22  |
| cheap_netcash                | 328 |       32 |  0.08  |               0.488 |         0.176 |
| as_book_growth HIGH          | 261 |       21 |  0.081 |               0.492 |         0.321 |
| kr_bookValuePerShare_g4 HIGH | 261 |       21 |  0.081 |               0.492 |         0.321 |
| opm_d2 HIGH                  | 385 |       32 |  0.084 |               0.511 |         0.364 |
| tr_fcfm_accel LOW            | 255 |       21 |  0.086 |               0.522 |         0.217 |
| op_cash_gap LOW              | 205 |       21 |  0.086 |               0.523 |         0.151 |

## fallen_below_cycle: n=20,272, rate 6.09% (lift 1.62x), blow-up 13%, 10x/5y 1.4%

raises the rate most:

| condition              |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:-----------------------|-----:|---------:|-------:|--------------------:|--------------:|
| gap_perc_buyshare HIGH |  143 |       22 |  0.16  |               2.623 |         0.149 |
| ps_vs_own HIGH         |  190 |       24 |  0.149 |               2.45  |         0.097 |
| net_net                |  475 |       70 |  0.136 |               2.224 |         0.105 |
| buy_share LOW          |  700 |       94 |  0.128 |               2.102 |         0.148 |
| n_analysts LOW         |  758 |       96 |  0.121 |               1.981 |         0.173 |
| buy_share_d12 LOW      |  428 |       47 |  0.117 |               1.921 |         0.159 |
| pos104 HIGH            |  225 |       22 |  0.102 |               1.674 |         0.09  |
| buy_share_d12 HIGH     |  292 |       31 |  0.1   |               1.636 |         0.124 |
| tr_debt_streak LOW     |  207 |       23 |  0.099 |               1.617 |         0.168 |
| up_lo52 HIGH           | 1830 |      170 |  0.095 |               1.564 |         0.18  |
| gap_perc_buyshare LOW  |  369 |       40 |  0.095 |               1.561 |         0.161 |
| overlevered_stressed   | 2235 |      225 |  0.094 |               1.534 |         0.181 |

lowers it most:

| condition                               |    n |   events |   rate |   lift_vs_archetype |   p_blowup_50 |
|:----------------------------------------|-----:|---------:|-------:|--------------------:|--------------:|
| op_ind_vol LOW                          | 2323 |       79 |  0.025 |               0.403 |         0.047 |
| kr_researchAndDevelopementToRevenue LOW | 1436 |       42 |  0.025 |               0.404 |         0.084 |
| vol52 LOW                               | 2271 |       90 |  0.026 |               0.43  |         0.04  |
| rd_rev LOW                              | 2229 |       69 |  0.026 |               0.434 |         0.092 |
| op_sec_vol LOW                          | 2311 |       89 |  0.028 |               0.454 |         0.054 |
| kr_cashConversionCycle LOW              | 3961 |      119 |  0.031 |               0.508 |         0.152 |
| tr_gm_streak LOW                        |  692 |       24 |  0.032 |               0.526 |         0.119 |
| range104 LOW                            | 1746 |       86 |  0.035 |               0.571 |         0.044 |
| kr_daysOfInventoryOutstanding LOW       | 3697 |      144 |  0.035 |               0.581 |         0.108 |
| ins_buy_quarters_4q HIGH                |  693 |       26 |  0.037 |               0.615 |         0.213 |
| dd_time_share_260 LOW                   | 1168 |       46 |  0.038 |               0.621 |         0.164 |
| tr_roic_consist HIGH                    |  630 |       28 |  0.038 |               0.622 |         0.152 |

# 7. Size and quality inside the operator archetypes


wave_neglected_value_accel by size_bucket:

| size_bucket   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| <50M          |  1679 |      166 |  0.088 |         0.06  |         0.04  |            0.141 |               1.777 |
| 50-300M       | 12199 |      787 |  0.056 |         0.068 |         0.014 |            0.188 |               1.145 |
| 300M-2B       |  8663 |      430 |  0.044 |         0.063 |         0.017 |            0.188 |               0.89  |
| >2B           |  4326 |      116 |  0.025 |         0.086 |         0.007 |            0.173 |               0.513 |

wave_neglected_value_accel by quality_tercile:

| quality_tercile   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| high ROIC         | 10498 |      590 |  0.052 |         0.071 |         0.017 |            0.158 |               1.059 |
| low ROIC          |  6125 |      383 |  0.052 |         0.072 |         0.018 |            0.201 |               1.055 |
| mid               |  8332 |      424 |  0.044 |         0.065 |         0.011 |            0.184 |               0.901 |

wave_neglected_value_accel by year:

|   year |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2012 |  309 |       34 |  0.096 |         0.017 |         0.004 |            0.755 |               1.94  |
|   2013 |  539 |       51 |  0.09  |         0.035 |         0.009 |            0.339 |               1.835 |
|   2024 | 1238 |      104 |  0.073 |         0.033 |       nan     |            0.263 |               1.479 |
|   2022 | 5351 |      347 |  0.058 |         0.036 |         0.005 |            0.338 |               1.174 |
|   2020 | 3168 |      190 |  0.054 |         0.024 |         0.021 |            0.204 |               1.101 |
|   2014 |  497 |       25 |  0.051 |         0.052 |         0.007 |            0.14  |               1.035 |
|   2016 | 2185 |      133 |  0.049 |         0.02  |         0.003 |            0.294 |               0.993 |
|   2021 | 3019 |      145 |  0.045 |         0.079 |         0.033 |            0.092 |               0.922 |
|   2023 | 2733 |      140 |  0.045 |         0.032 |         0     |            0.279 |               0.916 |
|   2019 | 2882 |      134 |  0.037 |         0.127 |         0.022 |            0.117 |               0.753 |
|   2015 |  890 |       36 |  0.03  |         0.049 |         0.011 |            0.225 |               0.6   |
|   2017 | 1109 |       23 |  0.02  |         0.104 |         0.001 |           -0.073 |               0.412 |
|   2018 | 2785 |       40 |  0.013 |         0.216 |         0.013 |           -0.076 |               0.264 |

wave_neglected_value_accel by market:

| market   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| IS       |   212 |       85 |  0.432 |         0.065 |         0.45  |            0.879 |               8.775 |
| NS       |  1251 |      256 |  0.179 |         0.127 |         0.085 |            0.584 |               3.633 |
| SA       |   214 |       26 |  0.113 |         0.074 |         0.011 |            0.282 |               2.283 |
| KQ       |   438 |       41 |  0.092 |         0.194 |         0     |            0.016 |               1.858 |
| MI       |   226 |       17 |  0.078 |         0.062 |         0.044 |            0.21  |               1.586 |
| TWO      |   852 |       65 |  0.076 |         0.038 |         0.036 |            0.232 |               1.545 |
| JK       |   406 |       32 |  0.072 |         0.158 |         0.032 |           -0.007 |               1.462 |
| SR       |   195 |       16 |  0.068 |         0.066 |         0     |            0.319 |               1.376 |
| TO       |   181 |       10 |  0.057 |         0.125 |         0.036 |            0.166 |               1.152 |
| TW       |  1704 |      103 |  0.056 |         0.043 |         0.021 |            0.234 |               1.141 |
| SI       |   166 |        9 |  0.055 |         0.119 |         0     |            0.168 |               1.115 |
| KS       |  2500 |      129 |  0.049 |         0.093 |         0.008 |           -0.004 |               0.997 |
| BK       |   451 |       23 |  0.049 |         0.072 |         0.02  |            0.164 |               0.992 |
| SS       |  1487 |       65 |  0.042 |         0.026 |         0.002 |            0.118 |               0.861 |
| DE       |   350 |       14 |  0.035 |         0.08  |         0.029 |            0.287 |               0.712 |
| SZ       |  1438 |       64 |  0.035 |         0.068 |         0.01  |            0.071 |               0.706 |
| T        | 10982 |      414 |  0.032 |         0.036 |         0.006 |            0.222 |               0.649 |
| US       |  2429 |       73 |  0.025 |         0.152 |         0.005 |            0.158 |               0.505 |
| MC       |   152 |        2 |  0.014 |         0.149 |         0     |            0.27  |               0.287 |
| VI       |   206 |        2 |  0.01  |         0.037 |         0     |            0.307 |               0.199 |
| HK       |   217 |        0 |  0     |         0.076 |         0     |            0.069 |               0     |

leader_in_wave by size_bucket:

| size_bucket   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| 300M-2B       | 202 |       40 |  0.191 |         0.238 |         0.007 |            0.058 |               1.245 |
| >2B           | 558 |       74 |  0.14  |         0.235 |         0.012 |            0.077 |               0.913 |

leader_in_wave by quality_tercile:

| quality_tercile   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| mid               | 181 |       27 |  0.166 |         0.155 |         0     |            0.005 |               1.082 |
| high ROIC         | 386 |       62 |  0.158 |         0.29  |         0.019 |            0.041 |               1.025 |
| low ROIC          | 174 |       26 |  0.154 |         0.205 |         0.006 |            0.225 |               1.005 |

leader_in_wave by year:

|   year |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2023 | 239 |       31 |  0.146 |         0.127 |       nan     |            0.547 |                0.95 |
|   2021 | 248 |        0 |  0     |         0.413 |         0.012 |           -0.19  |                0    |

leader_in_wave by market:

| market   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| US       | 447 |       40 |  0.095 |         0.299 |         0.013 |           -0.028 |               0.617 |

improving_unturned_sellside by size_bucket:

| size_bucket   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| <50M          |  1238 |       87 |  0.07  |         0.08  |         0.066 |            0.155 |               1.357 |
| 50-300M       | 11890 |      791 |  0.068 |         0.102 |         0.013 |            0.114 |               1.315 |
| 300M-2B       | 15613 |      901 |  0.055 |         0.118 |         0.013 |            0.108 |               1.065 |
| >2B           | 12564 |      393 |  0.032 |         0.089 |         0.001 |            0.127 |               0.617 |

improving_unturned_sellside by quality_tercile:

| quality_tercile   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| mid               | 14812 |      794 |  0.053 |         0.099 |         0.013 |            0.113 |               1.016 |
| high ROIC         | 13449 |      689 |  0.052 |         0.103 |         0.01  |            0.136 |               1.002 |
| low ROIC          | 11304 |      555 |  0.047 |         0.113 |         0.008 |            0.086 |               0.915 |

improving_unturned_sellside by year:

|   year |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2025 |  235 |      126 |  0.532 |         0     |         0     |          nan     |              10.285 |
|   2024 | 2861 |      347 |  0.121 |         0.043 |         0     |            0.282 |               2.34  |
|   2023 | 3668 |      362 |  0.099 |         0.042 |         0.011 |            0.272 |               1.906 |
|   2022 | 3689 |      301 |  0.085 |         0.077 |         0     |            0.157 |               1.653 |
|   2020 | 2350 |      148 |  0.064 |         0.077 |         0.027 |            0.121 |               1.228 |
|   2012 |  678 |       32 |  0.049 |         0.011 |         0.007 |            0.482 |               0.951 |
|   2013 | 2275 |      116 |  0.045 |         0.04  |         0.006 |            0.328 |               0.875 |
|   2016 | 3132 |      135 |  0.041 |         0.085 |         0.007 |            0.157 |               0.795 |
|   2021 | 4837 |      170 |  0.037 |         0.135 |         0.025 |           -0.03  |               0.713 |
|   2019 | 2363 |       88 |  0.034 |         0.157 |         0.015 |            0.267 |               0.66  |
|   2014 | 4099 |      139 |  0.031 |         0.087 |         0.006 |            0.126 |               0.6   |
|   2017 | 3918 |       91 |  0.023 |         0.123 |         0.007 |           -0.027 |               0.449 |
|   2015 | 3951 |       63 |  0.014 |         0.094 |         0.003 |            0.128 |               0.274 |
|   2018 | 3247 |       42 |  0.013 |         0.281 |         0.015 |           -0.141 |               0.25  |

improving_unturned_sellside by market:

| market   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| IS       |   739 |      237 |  0.344 |         0.055 |         0.379 |            0.874 |               6.664 |
| TWO      |   727 |       71 |  0.12  |         0.058 |         0.008 |            0.106 |               2.323 |
| TO       |   740 |       86 |  0.12  |         0.085 |         0.008 |            0.107 |               2.319 |
| KQ       |   358 |       35 |  0.114 |         0.224 |         0     |           -0.128 |               2.208 |
| NS       |  1650 |      187 |  0.107 |         0.09  |         0.018 |            0.273 |               2.075 |
| SI       |   195 |       22 |  0.102 |         0.133 |         0     |            0.109 |               1.974 |
| MI       |   246 |       22 |  0.083 |         0.069 |         0.006 |            0.248 |               1.614 |
| KS       |  1860 |      143 |  0.074 |         0.165 |         0.008 |           -0.077 |               1.437 |
| JK       |   318 |       21 |  0.068 |         0.088 |         0.006 |           -0.017 |               1.324 |
| DE       |   865 |       67 |  0.066 |         0.083 |         0.023 |            0.141 |               1.285 |
| TW       |  3030 |      200 |  0.066 |         0.072 |         0.024 |            0.146 |               1.27  |
| SZ       |  2995 |      191 |  0.065 |         0.168 |         0.003 |           -0.026 |               1.265 |
| MX       |   176 |       11 |  0.064 |         0.099 |         0     |            0.253 |               1.235 |
| SR       |   211 |        9 |  0.053 |         0.13  |         0     |            0.289 |               1.026 |
| SA       |   189 |       10 |  0.046 |         0.04  |         0.011 |            0.13  |               0.889 |
| SS       |  2294 |       97 |  0.046 |         0.109 |         0     |           -0.029 |               0.883 |
| CO       |   293 |       10 |  0.034 |         0.092 |         0     |            0.199 |               0.66  |
| T        | 11561 |      385 |  0.034 |         0.083 |         0.002 |            0.133 |               0.658 |
| US       |  9877 |      302 |  0.03  |         0.104 |         0.006 |            0.185 |               0.577 |
| BK       |  1176 |       30 |  0.028 |         0.169 |         0     |           -0.048 |               0.535 |
| TA       |   249 |       12 |  0.024 |         0.118 |         0     |            0.167 |               0.465 |
| ST       |   572 |        9 |  0.016 |         0.086 |         0     |            0.13  |               0.305 |
| HE       |   215 |        0 |  0     |         0.312 |         0     |           -0.226 |               0     |

peer_worst_cheapest by size_bucket:

| size_bucket   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| 50-300M       | 313 |       20 |  0.052 |         0.048 |         0.044 |            0.155 |               0.907 |

peer_worst_cheapest by quality_tercile:

| quality_tercile   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| low ROIC          | 455 |       31 |  0.057 |         0.064 |         0.041 |            0.173 |               1.004 |

peer_worst_cheapest by market:

| market   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| T        | 400 |       20 |  0.041 |         0.045 |         0.015 |            0.174 |               0.717 |

margin_inflect_weak_tape by size_bucket:

| size_bucket   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| <50M          |  921 |       74 |  0.078 |         0.134 |         0.036 |            0.017 |               1.756 |
| 50-300M       | 5548 |      425 |  0.069 |         0.108 |         0.018 |            0.14  |               1.544 |
| 300M-2B       | 8815 |      410 |  0.042 |         0.15  |         0.013 |            0.09  |               0.937 |
| >2B           | 6242 |      168 |  0.024 |         0.118 |         0.007 |            0.127 |               0.528 |

margin_inflect_weak_tape by quality_tercile:

| quality_tercile   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| mid               | 7032 |      367 |  0.048 |         0.114 |         0.016 |            0.116 |               1.083 |
| low ROIC          | 5779 |      302 |  0.046 |         0.157 |         0.011 |            0.104 |               1.028 |
| high ROIC         | 8524 |      389 |  0.04  |         0.124 |         0.014 |            0.106 |               0.895 |

margin_inflect_weak_tape by year:

|   year |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2013 |  261 |       49 |  0.142 |         0.077 |         0.009 |            0.26  |               3.186 |
|   2020 | 1497 |      153 |  0.095 |         0.036 |         0.024 |            0.262 |               2.134 |
|   2024 | 1570 |      114 |  0.061 |         0.095 |         0     |            0.167 |               1.366 |
|   2019 | 1607 |      112 |  0.06  |         0.187 |         0.02  |            0.176 |               1.343 |
|   2012 |  340 |       16 |  0.05  |         0.025 |         0.01  |            0.578 |               1.114 |
|   2021 | 1555 |       78 |  0.046 |         0.145 |         0.037 |            0.023 |               1.04  |
|   2018 | 2862 |       99 |  0.035 |         0.22  |         0.013 |           -0.003 |               0.795 |
|   2023 | 2343 |       87 |  0.031 |         0.123 |         0     |            0.054 |               0.706 |
|   2022 | 5113 |      185 |  0.031 |         0.096 |         0.004 |            0.144 |               0.703 |
|   2014 |  558 |       20 |  0.029 |         0.168 |         0.004 |            0.104 |               0.658 |
|   2016 | 1475 |       43 |  0.027 |         0.076 |         0.013 |            0.186 |               0.594 |
|   2015 | 1077 |       30 |  0.025 |         0.116 |         0.005 |            0.185 |               0.553 |
|   2017 | 1135 |       13 |  0.014 |         0.254 |         0.004 |           -0.172 |               0.306 |

margin_inflect_weak_tape by market:

| market   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| IS       |  165 |       55 |  0.349 |         0.044 |         0.481 |            1.021 |               7.823 |
| KQ       |  390 |       52 |  0.125 |         0.145 |         0.009 |            0.06  |               2.8   |
| NS       |  707 |       97 |  0.114 |         0.144 |         0.031 |            0.437 |               2.556 |
| TO       |  271 |       19 |  0.071 |         0.097 |         0.054 |            0.211 |               1.591 |
| SZ       | 2880 |      189 |  0.062 |         0.141 |         0.016 |            0.071 |               1.399 |
| TWO      |  358 |       26 |  0.062 |         0.027 |         0.009 |            0.222 |               1.39  |
| TW       | 1139 |       61 |  0.051 |         0.063 |         0.018 |            0.131 |               1.133 |
| KS       | 1154 |       67 |  0.048 |         0.083 |         0.019 |           -0.027 |               1.078 |
| SS       | 1963 |       84 |  0.045 |         0.088 |         0     |            0.042 |               1.007 |
| ST       |  391 |       18 |  0.044 |         0.065 |         0.012 |            0.346 |               0.986 |
| MI       |  173 |        7 |  0.043 |         0.159 |         0.01  |            0.057 |               0.967 |
| DE       |  425 |       17 |  0.035 |         0.136 |         0.011 |            0.01  |               0.781 |
| T        | 3927 |      146 |  0.033 |         0.098 |         0.007 |            0.126 |               0.739 |
| SA       |  201 |        7 |  0.03  |         0.072 |         0.011 |            0.132 |               0.675 |
| BK       |  513 |       17 |  0.027 |         0.313 |         0     |           -0.171 |               0.613 |
| US       | 5458 |      163 |  0.027 |         0.168 |         0.007 |            0.167 |               0.604 |
| JK       |  194 |        5 |  0.02  |         0.157 |         0.011 |           -0.089 |               0.445 |

sequence_preignition by size_bucket:

| size_bucket   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| <50M          |  1733 |      200 |  0.116 |         0.122 |         0.066 |            0.064 |               2.069 |
| 50-300M       | 10222 |      938 |  0.085 |         0.117 |         0.021 |            0.181 |               1.509 |
| 300M-2B       | 17833 |      986 |  0.049 |         0.151 |         0.01  |            0.079 |               0.867 |
| >2B           |  9626 |      331 |  0.03  |         0.116 |         0.006 |            0.12  |               0.537 |

sequence_preignition by quality_tercile:

| quality_tercile   |     n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|------:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| mid               | 11219 |      711 |  0.058 |         0.131 |         0.016 |            0.107 |               1.04  |
| low ROIC          | 16579 |     1064 |  0.057 |         0.145 |         0.014 |            0.109 |               1.021 |
| high ROIC         |  9481 |      569 |  0.053 |         0.12  |         0.011 |            0.111 |               0.945 |

sequence_preignition by year:

|   year |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2025 |  341 |      203 |  0.511 |         0.032 |         0     |          nan     |               9.128 |
|   2013 | 1324 |      239 |  0.152 |         0.053 |         0.014 |            0.529 |               2.708 |
|   2014 | 1709 |      187 |  0.092 |         0.117 |         0.007 |            0.169 |               1.641 |
|   2020 | 3336 |      303 |  0.085 |         0.055 |         0.026 |            0.241 |               1.515 |
|   2024 | 2880 |      260 |  0.079 |         0.077 |         0     |            0.218 |               1.408 |
|   2012 |  724 |       62 |  0.077 |         0.019 |         0.016 |            0.56  |               1.377 |
|   2019 | 3051 |      224 |  0.072 |         0.208 |         0.02  |            0.199 |               1.288 |
|   2023 | 4455 |      222 |  0.045 |         0.096 |         0     |            0.185 |               0.801 |
|   2022 | 6721 |      302 |  0.041 |         0.099 |         0.01  |            0.145 |               0.727 |
|   2016 | 2804 |       96 |  0.034 |         0.14  |         0.008 |           -0.017 |               0.599 |
|   2015 | 1770 |       62 |  0.033 |         0.105 |         0.007 |            0.132 |               0.59  |
|   2021 | 4355 |      155 |  0.031 |         0.159 |         0.021 |            0.009 |               0.553 |
|   2018 | 3532 |      101 |  0.028 |         0.237 |         0.015 |           -0.041 |               0.502 |
|   2017 | 2465 |       41 |  0.016 |         0.281 |         0.005 |           -0.212 |               0.294 |

sequence_preignition by market:

| market   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| IS       |  209 |       67 |  0.353 |         0.053 |         0.419 |            0.759 |               6.294 |
| NS       | 1569 |      240 |  0.135 |         0.132 |         0.057 |            0.309 |               2.402 |
| KQ       |  663 |       74 |  0.115 |         0.162 |         0.008 |            0.126 |               2.053 |
| TWO      |  514 |       47 |  0.109 |         0.097 |         0.061 |            0.156 |               1.948 |
| MC       |  172 |       15 |  0.088 |         0.079 |         0.004 |            0.234 |               1.565 |
| TW       | 2204 |      177 |  0.073 |         0.077 |         0.012 |            0.115 |               1.304 |
| SZ       | 7806 |      589 |  0.07  |         0.123 |         0.009 |            0.089 |               1.243 |
| SR       |  273 |       18 |  0.061 |         0.126 |         0.007 |            0.044 |               1.085 |
| ST       |  357 |       24 |  0.059 |         0.102 |         0.04  |            0.207 |               1.05  |
| DE       |  594 |       36 |  0.057 |         0.147 |         0.015 |            0.042 |               1.016 |
| MI       |  305 |       16 |  0.056 |         0.096 |         0.066 |            0.17  |               1.006 |
| KS       | 2212 |      149 |  0.056 |         0.124 |         0.013 |            0.041 |               0.999 |
| T        | 4065 |      246 |  0.053 |         0.081 |         0.015 |            0.145 |               0.949 |
| SS       | 5295 |      272 |  0.049 |         0.091 |         0.001 |            0.062 |               0.88  |
| TO       |  555 |       24 |  0.045 |         0.217 |         0.038 |            0.157 |               0.801 |
| JK       |  286 |       17 |  0.04  |         0.308 |         0     |           -0.119 |               0.722 |
| SA       |  349 |       13 |  0.038 |         0.117 |         0.015 |            0.173 |               0.675 |
| US       | 9413 |      305 |  0.029 |         0.169 |         0.008 |            0.168 |               0.523 |
| BK       |  801 |       24 |  0.026 |         0.257 |         0.005 |           -0.141 |               0.459 |
| HK       |  238 |        7 |  0.025 |         0.117 |         0     |            0.081 |               0.451 |

left_for_dead_value by size_bucket:

| size_bucket   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| 50-300M       | 4230 |      521 |  0.12  |         0.168 |         0.037 |            0.195 |               1.151 |
| <50M          | 1425 |      156 |  0.111 |         0.112 |         0.052 |            0.15  |               1.059 |
| 300M-2B       | 2528 |      227 |  0.086 |         0.167 |         0.052 |            0.229 |               0.821 |
| >2B           |  909 |       58 |  0.074 |         0.126 |         0.021 |            0.243 |               0.707 |

left_for_dead_value by quality_tercile:

| quality_tercile   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| low ROIC          | 4654 |      603 |  0.127 |         0.161 |         0.056 |            0.231 |               1.22  |
| mid               | 1876 |      190 |  0.101 |         0.163 |         0.038 |            0.172 |               0.964 |
| high ROIC         | 1904 |      110 |  0.06  |         0.132 |         0.017 |            0.145 |               0.577 |

left_for_dead_value by year:

|   year |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2020 | 1864 |      328 |  0.19  |         0.031 |         0.067 |            0.452 |               1.818 |
|   2013 |  260 |       47 |  0.179 |         0.083 |         0.074 |            0.473 |               1.711 |
|   2019 |  907 |      102 |  0.117 |         0.3   |         0.045 |            0.285 |               1.124 |
|   2022 | 1313 |      123 |  0.087 |         0.12  |         0.019 |            0.203 |               0.832 |
|   2023 |  967 |       84 |  0.085 |         0.167 |         0     |            0.072 |               0.816 |
|   2016 |  523 |       40 |  0.078 |         0.075 |         0.029 |            0.211 |               0.744 |
|   2021 |  729 |       63 |  0.076 |         0.13  |         0.03  |            0.113 |               0.732 |
|   2024 |  723 |       59 |  0.063 |         0.191 |         0     |            0.081 |               0.603 |
|   2014 |  256 |       14 |  0.045 |         0.283 |         0.005 |            0.057 |               0.431 |
|   2017 |  370 |       16 |  0.037 |         0.206 |         0.01  |           -0.149 |               0.354 |
|   2015 |  346 |       13 |  0.036 |         0.151 |         0.014 |            0.14  |               0.345 |
|   2018 |  618 |       12 |  0.015 |         0.404 |         0.039 |           -0.102 |               0.145 |

left_for_dead_value by market:

| market   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| NS       |  544 |      180 |  0.313 |         0.166 |         0.158 |            0.921 |               2.995 |
| TO       |  186 |       43 |  0.231 |         0.425 |         0.161 |            0.517 |               2.215 |
| US       | 2059 |      294 |  0.142 |         0.251 |         0.04  |            0.362 |               1.358 |
| KQ       |  179 |       21 |  0.111 |         0.194 |         0.017 |            0.097 |               1.063 |
| KS       | 1066 |       86 |  0.081 |         0.077 |         0.023 |            0.126 |               0.779 |
| JK       |  250 |       26 |  0.067 |         0.343 |         0     |           -0.037 |               0.639 |
| SZ       |  464 |       28 |  0.044 |         0.075 |         0.005 |            0.169 |               0.421 |
| SS       |  410 |       17 |  0.039 |         0     |         0     |            0.164 |               0.375 |
| T        | 2353 |       97 |  0.034 |         0.059 |         0.026 |            0.156 |               0.321 |
| TW       |  244 |        6 |  0.03  |         0.067 |         0.004 |            0.102 |               0.285 |

smart_money_wreckage by size_bucket:

| size_bucket   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:--------------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| <50M          | 156 |       37 |  0.224 |         0.429 |         0.13  |            0.208 |               1.365 |
| 50-300M       | 660 |      139 |  0.202 |         0.297 |         0.018 |            0.547 |               1.232 |
| 300M-2B       | 571 |       67 |  0.121 |         0.248 |         0.045 |            0.29  |               0.734 |
| >2B           | 150 |       15 |  0.103 |         0.076 |         0.016 |            0.369 |               0.627 |

smart_money_wreckage by quality_tercile:

| quality_tercile   |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:------------------|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| mid               | 292 |       74 |  0.257 |         0.259 |         0.067 |            0.535 |               1.563 |
| low ROIC          | 881 |      173 |  0.188 |         0.297 |         0.043 |            0.487 |               1.144 |
| high ROIC         | 204 |        8 |  0.041 |         0.298 |         0.007 |            0.084 |               0.251 |

smart_money_wreckage by year:

|   year |   n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|-------:|----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
|   2020 | 354 |      146 |  0.417 |         0.063 |         0.069 |            1.005 |               2.539 |
|   2023 | 201 |       20 |  0.094 |         0.248 |         0     |            0.423 |               0.57  |
|   2022 | 176 |        8 |  0.049 |         0.32  |         0     |            0.002 |               0.297 |

smart_money_wreckage by market:

| market   |    n |   events |   rate |   p_blowup_50 |   t10_60_rate |   median_fwd_24m |   lift_vs_archetype |
|:---------|-----:|---------:|-------:|--------------:|--------------:|-----------------:|--------------------:|
| US       | 1537 |      258 |  0.164 |          0.27 |         0.039 |            0.417 |                   1 |

# 8. Winners vs same-population lookalikes (paired rank differences, 90% intervals)

| feature                             |   winner_minus_lookalike |   ci90_lo |   ci90_hi |   coverage | significant   |
|:------------------------------------|-------------------------:|----------:|----------:|-----------:|:--------------|
| r13                                 |                   -0.105 |    -0.117 |    -0.093 |      1     | True          |
| above_ma30                          |                   -0.098 |    -0.11  |    -0.087 |      1     | True          |
| dist_hi52                           |                   -0.07  |    -0.079 |    -0.062 |      1     | True          |
| vol52                               |                    0.062 |     0.051 |     0.073 |      1     | True          |
| st_flat_base                        |                   -0.061 |    -0.076 |    -0.044 |      1     | True          |
| op_vs_ind_r26                       |                   -0.06  |    -0.072 |    -0.049 |      1     | True          |
| op_ind_r26                          |                   -0.059 |    -0.071 |    -0.048 |      1     | True          |
| op_sec_r26                          |                   -0.057 |    -0.071 |    -0.046 |      1     | True          |
| mcap_usd_log                        |                   -0.057 |    -0.065 |    -0.047 |      0.999 | True          |
| rs26                                |                   -0.056 |    -0.068 |    -0.045 |      1     | True          |
| op_vs_mkt_r26                       |                   -0.056 |    -0.068 |    -0.045 |      1     | True          |
| r26                                 |                   -0.056 |    -0.068 |    -0.045 |      1     | True          |
| react_beats_mean                    |                    0.051 |     0.026 |     0.076 |      0.307 | True          |
| rd_rev                              |                    0.048 |     0.036 |     0.06  |      1     | True          |
| op_sec_size                         |                   -0.048 |    -0.057 |    -0.039 |      0.999 | True          |
| range104                            |                    0.047 |     0.035 |     0.059 |      1     | True          |
| op_sec_ps                           |                   -0.046 |    -0.06  |    -0.033 |      0.999 | True          |
| op_ind_size                         |                   -0.045 |    -0.054 |    -0.035 |      0.999 | True          |
| st_near_highs                       |                   -0.044 |    -0.055 |    -0.034 |      1     | True          |
| op_ind_ps                           |                   -0.044 |    -0.059 |    -0.031 |      0.999 | True          |
| ps                                  |                   -0.044 |    -0.057 |    -0.031 |      0.999 | True          |
| kr_dividendPayoutRatio              |                   -0.043 |    -0.056 |    -0.032 |      1     | True          |
| kr_researchAndDevelopementToRevenue |                    0.04  |     0.029 |     0.051 |      1     | True          |
| as_pb_own                           |                    0.04  |     0.027 |     0.052 |      0.997 | True          |
| kr_priceToBookRatio_own             |                    0.04  |     0.027 |     0.052 |      0.997 | True          |
| op_sec_vol                          |                    0.04  |     0.027 |     0.051 |      1     | True          |
| kr_dividendPayoutRatio_own          |                   -0.038 |    -0.051 |    -0.026 |      0.997 | True          |
| kr_priceToSalesRatio_own            |                    0.038 |     0.027 |     0.05  |      0.997 | True          |
| op_ind_vol                          |                    0.038 |     0.026 |     0.049 |      1     | True          |
| opm                                 |                   -0.038 |    -0.05  |    -0.026 |      1     | True          |
| ev_sales                            |                   -0.038 |    -0.051 |    -0.025 |      0.999 | True          |
| last_react                          |                   -0.037 |    -0.064 |    -0.015 |      0.291 | True          |
| months_since_up                     |                    0.037 |     0.012 |     0.063 |      0.186 | True          |
| downgrades_12m                      |                   -0.036 |    -0.063 |    -0.01  |      0.186 | True          |
| gap_trend_opm                       |                    0.036 |     0.022 |     0.05  |      0.958 | True          |
| st_deep_value                       |                    0.036 |     0.016 |     0.057 |      1     | True          |
| npm                                 |                   -0.036 |    -0.048 |    -0.022 |      1     | True          |
| kr_pretaxProfitMargin               |                   -0.035 |    -0.048 |    -0.021 |      1     | True          |
| kr_assetTurnover                    |                    0.035 |     0.021 |     0.048 |      1     | True          |
| kr_evToSales_own                    |                    0.035 |     0.022 |     0.047 |      0.997 | True          |


the operator measures specifically:

| feature          |   winner_minus_lookalike |   ci90_lo |   ci90_hi |   coverage | significant   |
|:-----------------|-------------------------:|----------:|----------:|-----------:|:--------------|
| op_vs_ind_r26    |                   -0.06  |    -0.072 |    -0.049 |      1     | True          |
| op_ind_r26       |                   -0.059 |    -0.071 |    -0.048 |      1     | True          |
| op_sec_r26       |                   -0.057 |    -0.071 |    -0.046 |      1     | True          |
| op_vs_mkt_r26    |                   -0.056 |    -0.068 |    -0.045 |      1     | True          |
| op_sec_size      |                   -0.048 |    -0.057 |    -0.039 |      0.999 | True          |
| op_sec_ps        |                   -0.046 |    -0.06  |    -0.033 |      0.999 | True          |
| op_ind_size      |                   -0.045 |    -0.054 |    -0.035 |      0.999 | True          |
| op_ind_ps        |                   -0.044 |    -0.059 |    -0.031 |      0.999 | True          |
| op_sec_vol       |                    0.04  |     0.027 |     0.051 |      1     | True          |
| op_ind_vol       |                    0.038 |     0.026 |     0.049 |      1     | True          |
| op_fcfy_plus_g   |                    0.034 |     0.018 |     0.049 |      0.967 | True          |
| op_coil          |                   -0.032 |    -0.044 |    -0.019 |      1     | True          |
| op_sec_opm       |                   -0.028 |    -0.041 |    -0.015 |      1     | True          |
| op_ind_opm       |                   -0.025 |    -0.038 |    -0.012 |      1     | True          |
| op_sec_fcfy      |                    0.021 |     0.008 |     0.035 |      0.999 | True          |
| op_sec_growth    |                    0.018 |     0.001 |     0.032 |      0.968 | True          |
| op_ind_fcfy      |                    0.018 |     0.005 |     0.033 |      0.999 | True          |
| op_pe_vs_g       |                   -0.018 |    -0.04  |     0.002 |      0.363 | False         |
| op_ind_growth    |                    0.018 |    -0.001 |     0.031 |      0.968 | False         |
| op_dil_adj_g     |                    0.018 |     0     |     0.032 |      0.967 | True          |
| op_sec_pb        |                   -0.018 |    -0.033 |    -0.005 |      0.957 | True          |
| op_lev           |                    0.017 |     0     |     0.037 |      0.666 | True          |
| op_ind_gm        |                   -0.017 |    -0.03  |    -0.004 |      1     | True          |
| op_sec_gm        |                   -0.017 |    -0.03  |    -0.001 |      1     | True          |
| op_ind_r52       |                   -0.017 |    -0.03  |    -0.006 |      1     | True          |
| op_vs_ind_r52    |                   -0.016 |    -0.029 |    -0.005 |      1     | True          |
| op_ind_pb        |                   -0.016 |    -0.032 |    -0.005 |      0.957 | True          |
| op_vs_ind_growth |                    0.016 |    -0.002 |     0.029 |      0.968 | False         |
| op_sec_r52       |                   -0.016 |    -0.029 |    -0.005 |      1     | True          |
| op_base_age      |                   -0.015 |    -0.026 |    -0.002 |      1     | True          |
| op_roic_x_fcfy   |                    0.014 |    -0     |     0.028 |      0.901 | False         |
| op_sec_accel     |                   -0.012 |    -0.028 |     0     |      0.943 | False         |
| op_vs_mkt_disthi |                   -0.011 |    -0.017 |    -0.006 |      1     | True          |
| op_v_shape       |                    0.01  |    -0.003 |     0.024 |      1     | False         |
| op_ind_disthi    |                   -0.01  |    -0.017 |    -0.002 |      1     | True          |
| op_vs_mkt_r52    |                   -0.009 |    -0.022 |     0.001 |      1     | False         |
| op_ind_accel     |                   -0.008 |    -0.026 |     0.005 |      0.943 | False         |
| op_vs_ind_opm_d1 |                    0.008 |    -0.008 |     0.023 |      0.968 | False         |
| op_cash_gap      |                    0.008 |    -0.005 |     0.022 |      1     | False         |
| op_evebit_vs_g   |                   -0.007 |    -0.022 |     0.008 |      0.782 | False         |
| op_vs_ind_disthi |                   -0.006 |    -0.013 |     0.002 |      1     | False         |
| op_sh_yield      |                   -0.005 |    -0.018 |     0.009 |      1     | False         |
| op_capex_rolloff |                    0.004 |    -0.026 |     0.03  |      0.18  | False         |
| op_sec_roic      |                    0.004 |    -0.009 |     0.018 |      0.902 | False         |
| op_sec_evebit    |                   -0.003 |    -0.018 |     0.01  |      0.943 | False         |
| op_sec_disthi    |                   -0.002 |    -0.01  |     0.005 |      1     | False         |
| op_ind_evebit    |                   -0.002 |    -0.017 |     0.013 |      0.943 | False         |
| op_wc_drift      |                    0     |    -0.013 |     0.017 |      1     | False         |
| op_ind_roic      |                   -0     |    -0.015 |     0.012 |      0.902 | False         |

# 3. Not fallen: operators at >= 60% of their 5-year high


## Not fallen

329,395 month-ends, 5,390 symbols; 3x-within-24m rate 2.93%, 10x-within-5y rate 0.71% (features ranked within month x market inside this sub-population).


### k-means archetypes

671 multibagger starts; base rate 2.93% of month-ends.

|   k |   silhouette |   robustness_ari |
|----:|-------------:|-----------------:|
|   3 |        0.075 |            0.341 |
|   4 |        0.082 |            0.659 |
|   5 |        0.065 |            0.29  |
|   6 |        0.08  |            0.235 |
|   7 |        0.056 |            0.226 |
|   8 |        0.059 |            0.251 |

|   archetype |   n_multibaggers |   share_of_multibaggers |   share_of_all_month_ends |   lift |   rate |   t3_12_rate |   t5_60_rate |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 |
|------------:|-----------------:|------------------------:|--------------------------:|-------:|-------:|-------------:|-------------:|--------------:|----------------------:|-----------------:|--------------:|
|           3 |               14 |                   0.02  |                     0.008 |  2.08  |  0.061 |        0.019 |        0.08  |         0.013 |                15.075 |            0.174 |         0.081 |
|           0 |              257 |                   0.389 |                     0.194 |  1.248 |  0.037 |        0.009 |        0.058 |         0.009 |                16.571 |            0.156 |         0.078 |
|           1 |              151 |                   0.238 |                     0.235 |  1.117 |  0.033 |        0.007 |        0.053 |         0.007 |                16.801 |            0.141 |         0.092 |
|           2 |              249 |                   0.353 |                     0.233 |  0.804 |  0.024 |        0.005 |        0.041 |         0.006 |                16.801 |            0.125 |         0.068 |


**Archetype 3** — 2% of multibaggers, lift 2.08x, blow-up 8%
- axes (vs all month-ends, + = more): volatility +0.21, operating_leverage -0.18, cheap_vs_own_history -0.14, margin_trajectory +0.14, vs_market -0.14, deleveraging -0.13, industry_laggard +0.12, accelerating -0.12, earnings_quality +0.10, fallen +0.08
- most distinctive features (rank vs all): tr_roic_accel +0.46, roic_d1 +0.46, tr_roic_slope8 +0.45, tr_debt_accel +0.42, surprise_4q +0.28, beats_4q +0.26, kr_priceToFreeCashFlowRatio +0.22, intang_assets +0.22, vol52 +0.21, kr_capexToRevenue_own +0.20, tr_shares_accel -0.40, tr_roic_consist -0.36, maxdd104 -0.23, gap_trend_roic -0.20, dist_hi52 -0.19, dist_hi260 -0.18, op_vs_mkt_disthi -0.18, inc_margin -0.18
- states over-represented (share, x vs all): expensive 21% (1.7x), neglected 93% (1.2x), flat_base 29% (0.9x), accumulation 14% (0.8x), turnaround 7% (0.4x), deep_value 7% (0.4x), near_highs 7% (0.1x), overlevered_stressed 0% (0.0x)
- medians at the start: rev growth 1y nan%; rev accel (pp) nan%; op margin 11%; op margin chg 1y nan%; FCF margin 5%; P/S 2.10; EV/EBIT 20.02; P/B 2.58; net cash / mcap 6%; net debt / EBITDA -0.75; share count chg 1y -0%; ROIC 23%; price / 5y high 69%; return 1y 5%; return 2y 63%; volatility 32%; mcap (log10 $) 8.68; analysts 0.00; headcount growth –; op margin, own-history pct 82%; sales/share vs price 1y (log gap) -0.17; margin own-pct minus price own-pct 0.10; op-margin slope 8q nan; share of 5y in deep drawdown 52%; weeks since 5y low 210.00
- data present: fund 0%, val 100%, perc 36%, emp 0%, bs 86%
- examples (start, best multiple within 5y): GLOBUSSPR.NS 2019-09 (10.9x); TATAELXSI.NS 2013-02 (10.2x); TRIDENT.NS 2019-11 (9.8x); 082920.KQ 2024-04 (7.1x); ASHOKLEY.NS 2013-05 (6.9x); APOLLOHOSP.NS 2019-09 (5.0x); KIT.OL 2024-04 (3.9x); NAUKRI.NS 2019-09 (3.7x); 043150.KQ 2013-10 (3.6x); 084370.KQ 2024-06 (3.5x)

**Archetype 0** — 39% of multibaggers, lift 1.25x, blow-up 8%
- axes (vs all month-ends, + = more): value_vs_growth +0.25, cheapness +0.19, industry_cheap +0.17, volatility +0.17, size -0.16, growth +0.15, quality_x_price +0.14, sector_relative +0.12, vs_market -0.12, industry_growth +0.12
- most distinctive features (rank vs all): pt_rev_6m +0.34, pt_prem_12m +0.31, op_fcfy_plus_g +0.22, earn_yield +0.20, ebit_g1 +0.19, rev_g1 +0.18, op_dil_adj_g +0.18, gap_eps_1y +0.17, roic_d1 +0.17, vol52 +0.17, op_evebit_vs_g -0.28, op_pe_vs_g -0.23, dist_hi52 -0.22, ev_ebit -0.22, op_sec_evebit -0.22, ev_sales -0.21, pe -0.21, op_sec_ps -0.20
- states over-represented (share, x vs all): hypergrowth 20% (3.1x), margin_inflect_derated 8% (2.9x), net_net 4% (2.7x), deep_value 45% (2.5x), cheap_netcash 22% (1.9x), fund_price_divergence 2% (1.9x), compounder 23% (1.9x), turnaround 27% (1.6x)
- medians at the start: rev growth 1y 17%; rev accel (pp) 5%; op margin 10%; op margin chg 1y 2%; FCF margin 5%; P/S 0.72; EV/EBIT 8.46; P/B 1.40; net cash / mcap 3%; net debt / EBITDA -0.21; share count chg 1y 0%; ROIC 15%; price / 5y high 70%; return 1y 10%; return 2y 36%; volatility 36%; mcap (log10 $) 8.56; analysts 0.00; headcount growth 7%; op margin, own-history pct 73%; sales/share vs price 1y (log gap) 0.07; margin own-pct minus price own-pct 0.07; op-margin slope 8q 0.00; share of 5y in deep drawdown 60%; weeks since 5y low 187.00
- data present: fund 100%, val 100%, perc 38%, emp 14%, bs 100%
- examples (start, best multiple within 5y): ISCTR.IS 2020-05 (87.1x); ALARK.IS 2019-01 (55.9x); STRL 2021-09 (39.3x); 6920.T 2015-09 (36.7x); PGSUS.IS 2018-11 (33.6x); TURSG.IS 2021-08 (28.6x); ASUZU.IS 2020-01 (28.0x); AGHOL.IS 2020-09 (22.8x); TRIL.NS 2021-12 (20.6x); 2327.TW 2015-08 (19.2x)

**Archetype 1** — 24% of multibaggers, lift 1.12x, blow-up 9%
- axes (vs all month-ends, + = more): cheapness -0.23, volatility +0.22, headcount_growth +0.21, industry_cheap -0.21, industry_quality +0.17, profitability +0.14, neglect -0.13, growth +0.13, balance_sheet +0.12, reinvesting +0.12
- most distinctive features (rank vs all): pt_rev_6m +0.38, kr_priceToBookRatio +0.32, pb +0.31, op_ind_pb +0.29, op_sec_pb +0.29, kr_priceToSalesRatio +0.28, ps +0.27, op_sec_ps +0.26, r260 +0.26, op_ind_ps +0.25, gap_perc_targets -0.31, pt_prem_12m -0.19, earn_yield -0.19, op_coil -0.18, fcf_yield -0.18, kr_earningsYield -0.15, ins_net_buy_4q -0.15, kr_debtToCapitalRatio -0.13
- states over-represented (share, x vs all): headcount_growth 14% (3.3x), compounder 40% (3.3x), expensive 26% (2.1x), margin_inflect_derated 5% (1.6x), fund_price_divergence 1% (1.6x), hypergrowth 7% (1.2x), turnaround 19% (1.1x), accelerating 37% (1.1x)
- medians at the start: rev growth 1y 17%; rev accel (pp) -1%; op margin 17%; op margin chg 1y 1%; FCF margin 9%; P/S 3.44; EV/EBIT 21.17; P/B 5.12; net cash / mcap 4%; net debt / EBITDA -0.77; share count chg 1y 0%; ROIC 23%; price / 5y high 78%; return 1y 21%; return 2y 66%; volatility 36%; mcap (log10 $) 9.26; analysts 4.00; headcount growth 16%; op margin, own-history pct 64%; sales/share vs price 1y (log gap) -0.04; margin own-pct minus price own-pct -0.10; op-margin slope 8q 0.00; share of 5y in deep drawdown 32%; weeks since 5y low 219.00
- data present: fund 100%, val 100%, perc 35%, emp 25%, bs 100%
- examples (start, best multiple within 5y): ASELS.IS 2021-01 (27.1x); FNOX.ST 2016-05 (25.9x); ALARK.IS 2020-02 (24.5x); FROTO.IS 2019-02 (21.8x); NVDA 2019-03 (18.4x); MELI 2016-01 (17.2x); 3443.TW 2021-05 (13.7x); BIMAS.IS 2021-07 (13.5x); NEM.DE 2013-08 (11.8x); ASM.AS 2018-07 (9.4x)

**Archetype 2** — 35% of multibaggers, lift 0.80x, blow-up 7%
- axes (vs all month-ends, + = more): vs_market -0.20, industry_laggard +0.17, value_vs_growth -0.17, industry_growth -0.17, below_own_cycle +0.17, growth -0.16, fallen +0.16, profitability -0.14, margin_trajectory -0.13, industry_quality -0.12
- most distinctive features (rank vs all): op_pe_vs_g +0.18, op_evebit_vs_g +0.15, dd_time_share_260 +0.13, wks_since_hi52 +0.11, op_base_age +0.11, kr_salesGeneralAndAdministrativeToRevenue_d4 +0.10, sga_rev_d1 +0.10, gap_own_fcfps +0.09, vol52 +0.08, inv_rev_d1 +0.08, gap_perc_targets -0.33, dist_hi260 -0.24, op_vs_mkt_disthi -0.24, inc_margin -0.23, pt_prem_12m -0.22, pos156 -0.22, op_sec_disthi -0.21, pos104 -0.21
- states over-represented (share, x vs all): fund_price_divergence 3% (3.9x), net_net 2% (1.9x), turnaround 22% (1.3x), deep_value 22% (1.2x), expensive 14% (1.1x), overlevered_delevering 2% (1.1x), neglected 84% (1.1x), flat_base 34% (1.1x)
- medians at the start: rev growth 1y 1%; rev accel (pp) -8%; op margin 7%; op margin chg 1y -1%; FCF margin 3%; P/S 1.03; EV/EBIT 15.69; P/B 1.62; net cash / mcap -1%; net debt / EBITDA 0.07; share count chg 1y 0%; ROIC 9%; price / 5y high 69%; return 1y 2%; return 2y 18%; volatility 34%; mcap (log10 $) 8.71; analysts 1.00; headcount growth 3%; op margin, own-history pct 36%; sales/share vs price 1y (log gap) -0.06; margin own-pct minus price own-pct -0.14; op-margin slope 8q -0.00; share of 5y in deep drawdown 63%; weeks since 5y low 189.00
- data present: fund 100%, val 100%, perc 39%, emp 15%, bs 99%
- examples (start, best multiple within 5y): 065350.KS 2019-06 (34.5x); MAVI.IS 2020-08 (31.4x); SMCI 2021-08 (27.2x); THYAO.IS 2020-05 (25.2x); PGSUS.IS 2020-11 (20.2x); ANSGR.IS 2021-08 (19.9x); GARAN.IS 2021-01 (18.9x); DELTA.BK 2018-12 (16.5x); HTRO.ST 2019-08 (14.8x); ABMD 2013-03 (14.7x)

### Patterns ranked by lift — 3x within 24 months

| pattern                                                                                                              |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                                                                                           |   t10_60_rate |
|:---------------------------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|----------------------:|-----------------:|--------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------|--------------:|
| evs_chg_1y HIGH & op_sec_vol HIGH & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                                |            4 | 18.686 |                 0.001 |                       83 |                15.42  |            1.931 |         0.086 | CLS 2023-10 (13.3x); TRIL.NS 2023-05 (9.3x); CLS.TO 2023-07 (8.5x); TSLA 2020-05 (7.4x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x)                   |       nan     |
| as_pb_own HIGH & op_sec_vol HIGH & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                                 |            4 | 18.075 |                 0.001 |                       84 |                15.42  |            1.931 |         0.027 | CLS 2023-10 (13.3x); CLS.TO 2023-07 (8.5x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); POWL 2024-06 (5.9x); NGD.TO 2024-06 (5.6x)                    |         0.071 |
| vol52 HIGH & n_analysts HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & gap_sales_3y LOW                         |            4 | 18.036 |                 0.001 |                       93 |                13.119 |            0.77  |         0.153 | NVDA 2020-03 (22.0x); 5803.T 2023-10 (18.0x); 2059.TW 2024-07 (10.1x); 036930.KQ 2024-09 (7.8x); 012450.KS 2024-03 (6.7x); 6857.T 2024-09 (4.7x)   |       nan     |
| ps_vs_own HIGH & op_coil LOW & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH                |            4 | 17.847 |                 0.001 |                       72 |                14.96  |            1.258 |         0.054 | CLS 2023-10 (13.3x); 000150.KS 2024-04 (11.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); NGD.TO 2024-07 (5.4x); TPC 2024-04 (4.9x)              |       nan     |
| gm LOW & op_sec_vol HIGH & kr_priceToBookRatio_d4 HIGH & gap_perc_buyshare HIGH                                      |            4 | 17.835 |                 0.001 |                       78 |                15.42  |            0.914 |         0.065 | CLS 2023-10 (13.3x); CLS.TO 2023-07 (8.5x); TRIL.NS 2023-07 (8.1x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); POWL 2024-06 (5.9x)                   |       nan     |
| gm LOW & op_v_shape HIGH & gap_sales_3y LOW & gap_perc_buyshare HIGH                                                 |            4 | 17.586 |                 0.001 |                       80 |                15.305 |            0.771 |         0.094 | CLS 2023-10 (13.3x); TRIL.NS 2023-05 (9.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); LMB 2023-05 (6.0x); POWL 2024-06 (5.9x)                   |       nan     |
| n_analysts HIGH & kr_daysOfInventoryOutstanding HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & gap_sales_3y LOW |            4 | 17.313 |                 0.001 |                       76 |                16.801 |            1.175 |         0.023 | 012450.KS 2024-01 (9.2x); 036930.KQ 2024-09 (7.8x); 6857.T 2024-09 (4.7x); NVDA 2023-10 (4.6x); 5706.T 2024-09 (4.5x); SAAB-B.ST 2024-01 (4.3x)    |       nan     |
| rev_accel HIGH & n_analysts HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & gap_sales_3y LOW                     |            4 | 17.293 |                 0.001 |                       70 |                11.968 |            0.697 |         0.062 | 5803.T 2023-10 (18.0x); NVDA 2020-05 (15.6x); 012450.KS 2024-01 (9.2x); 036930.KQ 2024-09 (7.8x); 5706.T 2024-09 (4.5x); SAAB-B.ST 2024-01 (4.3x)  |       nan     |
| react_beats_mean HIGH & kr_grossProfitMargin LOW & gap_sales_3y LOW & gap_perc_buyshare HIGH                         |            4 | 17.241 |                 0.001 |                       75 |                15.65  |            1.329 |         0.075 | CLS 2023-10 (13.3x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); POWL 2024-06 (5.9x); TSLA 2020-07 (4.3x); REVG 2024-01 (4.2x)                        |       nan     |
| op_coil LOW & op_sec_vol HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH               |            4 | 17.095 |                 0.001 |                       68 |                14.269 |            0.67  |         0.116 | CLS 2023-10 (13.3x); 000150.KS 2024-04 (11.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); NGD.TO 2024-07 (5.4x); TPC 2024-04 (4.9x)              |       nan     |
| ps_vs_own HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_sales_1y LOW & gap_perc_buyshare HIGH           |            4 | 17.074 |                 0.001 |                       68 |                15.65  |            1.258 |         0.08  | CLS 2023-10 (13.3x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); NGD.TO 2024-07 (5.4x); TPC 2024-04 (4.9x)               |       nan     |
| n_analysts HIGH & op_sec_vol HIGH & kr_fixedAssetTurnover_own HIGH & gap_sales_3y LOW                                |            4 | 17.074 |                 0.001 |                       83 |                11.738 |            0.593 |         0.151 | 5803.T 2023-12 (17.7x); NVDA 2023-10 (4.6x); TSLA 2020-07 (4.3x); J&KBANK.NS 2023-03 (4.2x); BBD-B.TO 2024-03 (4.1x); BPE.MI 2024-02 (3.9x)        |       nan     |
| n_analysts HIGH & op_sec_vol HIGH & op_vs_ind_opm_d1 HIGH & kr_currentRatio_d4 LOW                                   |            4 | 17.046 |                 0.001 |                       74 |                11.623 |            0.62  |         0.108 | NGD.TO 2024-03 (6.6x); 2059.TW 2023-10 (5.4x); GARAN.IS 2023-03 (4.9x); AKBNK.IS 2023-02 (4.7x); NVDA 2023-10 (4.6x); ISCTR.IS 2023-02 (4.2x)      |       nan     |
| n_analysts HIGH & op_sec_vol HIGH & ind_tape_disthi LOW & gap_sales_2y LOW                                           |            4 | 17.034 |                 0.001 |                       76 |                12.198 |            0.52  |         0.098 | 5803.T 2023-10 (18.0x); 2059.TW 2024-06 (6.8x); TSLA 2020-06 (6.4x); 6857.T 2024-08 (5.3x); 3110.T 2024-08 (2.7x); 6632.T 2023-07 (2.7x)           |       nan     |
| r104 HIGH & vol52 HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH                      |            4 | 16.933 |                 0.001 |                       68 |                14.615 |            0.604 |         0.127 | CLS 2023-10 (13.3x); 000150.KS 2024-04 (11.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); NGD.TO 2024-07 (5.4x); TPC 2024-04 (4.9x)              |       nan     |
| op_ind_vol HIGH & kr_grossProfitMargin LOW & gap_sales_3y LOW & gap_perc_buyshare HIGH                               |            4 | 16.87  |                 0.001 |                       76 |                15.075 |            0.976 |         0.087 | CLS 2023-10 (13.3x); TRIL.NS 2023-05 (9.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); LMB 2023-05 (6.0x); POWL 2024-06 (5.9x)                   |       nan     |
| vol52 HIGH & n_analysts HIGH & op_sec_accel HIGH & gap_sales_3y LOW                                                  |            4 | 16.856 |                 0.001 |                       88 |                11.738 |            0.49  |         0.101 | 5803.T 2023-10 (18.0x); 012450.KS 2023-10 (10.8x); 036930.KQ 2024-09 (7.8x); NGD.TO 2024-08 (4.4x); BPE.MI 2024-02 (3.9x); NVDA 2023-12 (3.8x)     |       nan     |
| vol52 HIGH & gm LOW & kr_priceToSalesRatio_own HIGH & gap_perc_buyshare HIGH                                         |            4 | 16.815 |                 0.001 |                       84 |                15.42  |            1.093 |         0.058 | CLS 2023-10 (13.3x); CLS.TO 2023-05 (9.4x); TRIL.NS 2023-05 (9.3x); TSLA 2020-05 (7.4x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x)                   |         0.064 |
| n_analysts HIGH & op_sec_vol HIGH & kr_currentRatio_d4 LOW & gap_sales_2y LOW                                        |            4 | 16.723 |                 0.001 |                       70 |                13.464 |            0.625 |         0.064 | 2059.TW 2024-07 (10.1x); 012450.KS 2024-01 (9.2x); NGD.TO 2024-06 (5.6x); NVDA 2023-10 (4.6x); ISCTR.IS 2023-02 (4.2x); J&KBANK.NS 2023-06 (4.1x)  |       nan     |
| vol52 HIGH & trend_r2_52 HIGH & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                                    |            4 | 16.64  |                 0.001 |                       76 |                15.42  |            1.535 |         0.063 | CLS 2023-10 (13.3x); TRIL.NS 2023-05 (9.3x); TSLA 2020-05 (7.4x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); LMB 2023-05 (6.0x)                   |       nan     |
| vol52 HIGH & sbc_rev HIGH & n_analysts HIGH & gap_sales_3y LOW                                                       |            4 | 16.631 |                 0.001 |                       71 |                15.19  |            0.919 |         0.139 | NVDA 2019-07 (28.3x); 012450.KS 2023-10 (10.8x); 6857.T 2024-08 (5.3x); TSLA 2020-07 (4.3x); AVGO 2024-05 (3.4x); ETSY 2020-05 (3.2x)              |         0.215 |
| n_analysts HIGH & op_ind_vol HIGH & kr_researchAndDevelopementToRevenue HIGH & gap_sales_3y LOW                      |            4 | 16.55  |                 0.001 |                       94 |                13.809 |            0.754 |         0.127 | NVDA 2019-07 (28.3x); 5803.T 2023-10 (18.0x); 5706.T 2024-05 (10.6x); 012450.KS 2023-07 (8.5x); 036930.KQ 2024-09 (7.8x); 002281.SZ 2024-06 (5.9x) |         0.091 |
| evs_chg_1y HIGH & as_pb_own HIGH & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                                 |            4 | 16.422 |                 0.001 |                       81 |                15.65  |            1.655 |         0.04  | CLS 2023-10 (13.3x); CLS.TO 2023-07 (8.5x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); POWL 2024-06 (5.9x); NGD.TO 2024-06 (5.6x)                    |       nan     |
| op_sec_vol HIGH & op_vs_ind_r52 HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH        |            4 | 16.174 |                 0.001 |                       63 |                14.499 |            0.628 |         0.088 | CLS 2023-10 (13.3x); 000150.KS 2024-04 (11.3x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); NGD.TO 2024-07 (5.4x); TPC 2024-04 (4.9x)              |       nan     |
| vol52 HIGH & gm LOW & op_sec_opm LOW & gap_perc_buyshare HIGH                                                        |            4 | 16.113 |                 0.001 |                       69 |                14.73  |            1.3   |         0.051 | CLS 2023-10 (13.3x); CLS.TO 2023-05 (9.4x); TRIL.NS 2023-05 (9.3x); TSLA 2020-05 (7.4x); LMB 2023-05 (6.0x); NGD.TO 2024-06 (5.6x)                 |         0.023 |

### Patterns ranked by lift — 10x within 5 years

| pattern                                                                                                              |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                     |
|:---------------------------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|--------------:|----------------------:|-----------------:|--------------:|:-----------------------------------------------------------------------------|
| gm LOW & rd_rev HIGH & op_ind_ps HIGH & op_sec_gm LOW                                                                |            4 | 63.113 |                 0.001 |                       49 |         0.449 |                21.174 |            0.381 |         0.102 | FROTO.IS 2019-03 (28.5x); TSLA 2019-09 (21.3x)                               |
| nd_ebitda LOW & rd_rev HIGH & surprise_4q LOW & ins_buy_quarters_4q HIGH                                             |            4 | 60.662 |                 0.001 |                       44 |         0.431 |                16.801 |            0.92  |         0.035 | MSTR 2020-09 (27.7x); NVDA 2015-09 (21.2x); ABMD 2014-05 (17.9x)             |
| roe HIGH & op_ind_ps HIGH & op_sec_gm LOW & kr_researchAndDevelopementToRevenue HIGH                                 |            4 | 59.739 |                 0.001 |                       41 |         0.425 |                22.094 |            0.692 |         0.06  | FROTO.IS 2019-03 (28.5x)                                                     |
| roic HIGH & op_ind_gm HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & insider_buying                             |            4 | 57.718 |                 0.001 |                       39 |         0.411 |                18.642 |            1.091 |         0.084 | NVDA 2015-09 (21.2x)                                                         |
| roic HIGH & rd_rev HIGH & kr_fixedAssetTurnover_d4 HIGH & insider_buying                                             |            4 | 57.525 |                 0.001 |                       39 |         0.409 |                18.642 |            0.962 |         0.073 | NVDA 2015-09 (21.2x)                                                         |
| op_ind_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & kr_fixedAssetTurnover_d4 HIGH & insider_buying       |            4 | 56.97  |                 0.001 |                       39 |         0.405 |                18.642 |            0.854 |         0.041 | NVDA 2015-09 (21.2x)                                                         |
| dvol_usd_log HIGH & roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & insider_buying                          |            4 | 55.951 |                 0.001 |                       39 |         0.398 |                18.642 |            0.711 |         0.082 | NVDA 2015-09 (21.2x)                                                         |
| rd_rev HIGH & op_roic_x_fcfy HIGH & op_ind_gm HIGH & insider_buying                                                  |            4 | 53.845 |                 0.001 |                       36 |         0.383 |                18.067 |            0.907 |         0.011 | NVDA 2015-09 (21.2x)                                                         |
| nd_ebitda LOW & rd_rev HIGH & ins_buy_quarters_4q HIGH & op_sec_roic HIGH                                            |            4 | 53.669 |                 0.001 |                       38 |         0.382 |                17.261 |            0.634 |         0.083 | MSTR 2020-09 (27.7x); NVDA 2015-09 (21.2x)                                   |
| op_sec_gm LOW & kr_researchAndDevelopementToRevenue HIGH & kr_assetTurnover HIGH & compounder                        |            4 | 51.372 |                 0.001 |                       50 |         0.365 |                22.555 |            0.784 |         0.025 | FROTO.IS 2019-03 (28.5x); TTRAK.IS 2020-07 (22.7x); VESBE.IS 2020-04 (12.4x) |
| r260 HIGH & op_ind_ps HIGH & op_sec_gm LOW & kr_researchAndDevelopementToRevenue HIGH                                |            4 | 50.573 |                 0.001 |                       35 |         0.36  |                22.094 |            0.274 |         0.097 | FROTO.IS 2020-03 (28.2x)                                                     |
| op_sec_gm LOW & kr_researchAndDevelopementToRevenue HIGH & kr_taxBurden HIGH & compounder                            |            4 | 50.549 |                 0.001 |                       36 |         0.36  |                22.555 |            0.728 |         0.019 | FROTO.IS 2019-03 (28.5x); TTRAK.IS 2020-07 (22.7x); VESBE.IS 2020-04 (12.4x) |
| roic HIGH & rd_rev HIGH & kr_effectiveTaxRate LOW & insider_buying                                                   |            4 | 50.535 |                 0.001 |                       34 |         0.359 |                26.697 |            0.779 |         0.074 | NVDA 2013-09 (18.5x)                                                         |
| ins_net_buy_4q LOW & kr_researchAndDevelopementToRevenue_d4 LOW & kr_fixedAssetTurnover_d4 HIGH & insider_buying     |            4 | 49.609 |                 0.001 |                       34 |         0.353 |                17.261 |            0.824 |         0.021 | TSLA 2019-09 (21.3x); NVDA 2015-09 (21.2x)                                   |
| rd_rev HIGH & surprise_4q LOW & ins_buy_quarters_4q HIGH & near_highs                                                |            4 | 48.655 |                 0.001 |                       34 |         0.346 |                18.527 |            0.682 |         0.045 | NVDA 2015-09 (21.2x); ABMD 2013-12 (15.1x)                                   |
| rd_rev HIGH & op_ind_ps HIGH & op_sec_gm LOW & kr_taxBurden HIGH                                                     |            4 | 48.592 |                 0.001 |                       39 |         0.346 |                21.174 |            0.848 |         0.094 | FROTO.IS 2019-03 (28.5x); TSLA 2019-09 (21.3x)                               |
| rd_rev HIGH & op_sec_gm LOW & kr_workingCapitalTurnoverRatio HIGH & compounder                                       |            4 | 47.674 |                 0.001 |                       45 |         0.339 |                23.015 |            0.982 |         0.03  | FROTO.IS 2019-03 (28.5x); VESBE.IS 2018-03 (16.5x)                           |
| beats_4q LOW & ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & kr_fixedAssetTurnover_d4 HIGH |            4 | 47.225 |                 0.001 |                       36 |         0.336 |                15.65  |            0.263 |         0.047 | TSLA 2019-09 (21.3x); NVDA 2015-09 (21.2x)                                   |
| asset_turn_d1 HIGH & op_sec_gm LOW & kr_researchAndDevelopementToRevenue HIGH & compounder                           |            4 | 46.121 |                 0.001 |                       35 |         0.328 |                23.475 |            0.346 |         0.092 | FROTO.IS 2019-03 (28.5x); TTRAK.IS 2020-07 (22.7x); VESBE.IS 2020-04 (12.4x) |
| roic HIGH & rd_rev HIGH & ins_buy_quarters_4q HIGH & near_highs                                                      |            4 | 46.024 |                 0.001 |                       37 |         0.327 |                20.253 |            0.813 |         0.088 | NVDA 2015-09 (21.2x)                                                         |
| op_ind_ps HIGH & op_sec_gm LOW & op_ind_gm LOW & kr_researchAndDevelopementToRevenue HIGH                            |            4 | 45.778 |                 0.001 |                       36 |         0.326 |                21.634 |            0.3   |         0.077 | FROTO.IS 2019-08 (25.5x)                                                     |
| sbc_rev HIGH & upgrades_12m HIGH & ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue_d4 LOW             |            4 | 45.362 |                 0.001 |                       33 |         0.323 |                14.269 |            0.39  |         0.035 | TSLA 2019-09 (21.3x); NVDA 2015-09 (21.2x)                                   |
| rd_rev HIGH & op_sec_gm LOW & op_ind_pb HIGH & kr_payablesTurnover HIGH                                              |            4 | 45.332 |                 0.001 |                       45 |         0.322 |                22.094 |            0.54  |         0.05  | FROTO.IS 2019-08 (25.5x); TTRAK.IS 2020-07 (22.7x)                           |
| ncav_mcap HIGH & roic HIGH & ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue_d4 LOW                   |            4 | 45.178 |                 0.001 |                       32 |         0.321 |                14.269 |            0.912 |         0.062 | MSTR 2020-09 (27.7x); NVDA 2015-09 (21.2x)                                   |
| op_ind_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & kr_quickRatio HIGH & insider_buying                  |            4 | 44.977 |                 0.001 |                       34 |         0.32  |                20.713 |            0.671 |         0.029 | MSTR 2020-09 (27.7x); NVDA 2015-09 (21.2x)                                   |

# 4. Near highs: operators within 15% of the 52-week high


## Near highs

232,639 month-ends, 5,484 symbols; 3x-within-24m rate 2.65%, 10x-within-5y rate 0.62% (features ranked within month x market inside this sub-population).


### k-means archetypes

363 multibagger starts; base rate 2.65% of month-ends.

|   k |   silhouette |   robustness_ari |
|----:|-------------:|-----------------:|
|   3 |        0.073 |            0.225 |
|   4 |        0.059 |            0.28  |
|   5 |        0.059 |            0.169 |
|   6 |        0.065 |            0.236 |
|   7 |        0.062 |            0.303 |
|   8 |        0.059 |            0.256 |

|   archetype |   n_multibaggers |   share_of_multibaggers |   share_of_all_month_ends |   lift |   rate |   t3_12_rate |   t5_60_rate |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 |
|------------:|-----------------:|------------------------:|--------------------------:|-------:|-------:|-------------:|-------------:|--------------:|----------------------:|-----------------:|--------------:|
|           2 |              122 |                   0.361 |                     0.227 |  1.278 |  0.034 |        0.008 |        0.058 |         0.007 |                16.571 |            0.151 |         0.083 |
|           1 |              142 |                   0.369 |                     0.161 |  0.967 |  0.026 |        0.006 |        0.048 |         0.006 |                17.031 |            0.137 |         0.058 |
|           0 |               99 |                   0.269 |                     0.226 |  0.838 |  0.022 |        0.004 |        0.039 |         0.004 |                17.261 |            0.148 |         0.06  |


**Archetype 2** — 36% of multibaggers, lift 1.28x, blow-up 8%
- axes (vs all month-ends, + = more): growth +0.24, industry_growth +0.22, volatility +0.20, value_vs_growth +0.17, headcount_growth +0.14, below_own_cycle -0.14, margin_trajectory +0.14, operating_leverage +0.13, industry_quality +0.11, profitability +0.10
- most distinctive features (rank vs all): rev_g1 +0.29, op_sec_growth +0.28, op_ind_growth +0.28, ebit_g1 +0.26, rev_q_yoy +0.26, op_vs_ind_growth +0.26, op_dil_adj_g +0.26, op_fcfy_plus_g +0.26, pp_gm_x_growth +0.25, op_v_shape +0.24, ins_net_buy_4q -0.24, pt_prem_12m -0.21, dist_hi52 -0.14, op_pe_vs_g -0.12, slope_brk -0.12, ins_buy_quarters_4q -0.07, downgrades_12m -0.07, div_yield -0.07
- states over-represented (share, x vs all): margin_inflect_derated 10% (4.4x), hypergrowth 20% (3.5x), compounder 30% (2.8x), turnaround 30% (1.8x), accelerating 56% (1.7x), headcount_growth 6% (1.4x), expensive 17% (1.3x), deep_value 20% (1.1x)
- medians at the start: rev growth 1y 22%; rev accel (pp) 9%; op margin 15%; op margin chg 1y 2%; FCF margin 6%; P/S 1.79; EV/EBIT 15.47; P/B 3.22; net cash / mcap 3%; net debt / EBITDA -0.59; share count chg 1y 0%; ROIC 19%; price / 5y high 88%; return 1y 28%; return 2y 49%; volatility 33%; mcap (log10 $) 8.85; analysts 2.00; headcount growth 8%; op margin, own-history pct 72%; sales/share vs price 1y (log gap) -0.05; margin own-pct minus price own-pct -0.12; op-margin slope 8q 0.00; share of 5y in deep drawdown 47%; weeks since 5y low 191.00
- data present: fund 99%, val 100%, perc 28%, emp 12%, bs 100%
- examples (start, best multiple within 5y): ASELS.IS 2021-01 (27.1x); FNOX.ST 2016-05 (25.9x); 6027.T 2016-09 (18.1x); SASA.IS 2015-06 (17.3x); 6590.T 2019-10 (16.9x); FROTO.IS 2016-04 (12.1x); BIMAS.IS 2021-08 (12.0x); TAL 2015-05 (9.0x); 6857.T 2019-01 (8.9x); GENTERA.MX 2017-06 (8.5x)

**Archetype 1** — 37% of multibaggers, lift 0.97x, blow-up 6%
- axes (vs all month-ends, + = more): vs_market -0.22, fallen +0.21, industry_laggard +0.20, size -0.19, profitability -0.16, industry_cheap +0.16, industry_quality -0.16, cheapness +0.14, operating_leverage -0.14, neglect +0.13
- most distinctive features (rank vs all): dd_time_share_260 +0.20, pt_prem_12m +0.16, gap_own_roic +0.16, gap_own_fcfps +0.15, op_base_age +0.14, wks_since_hi52 +0.14, gap_own_opm +0.14, gap_sales_3y +0.13, op_capex_rolloff +0.12, gap_own_gm +0.11, dist_hi260 -0.29, op_vs_mkt_disthi -0.29, op_ind_disthi -0.28, op_sec_disthi -0.27, op_vs_ind_disthi -0.26, op_ind_ps -0.25, pos156 -0.25, pos104 -0.24
- states over-represented (share, x vs all): fund_price_divergence 6% (6.9x), net_net 6% (4.2x), fallen_angel 8% (3.8x), deep_value 33% (1.9x), turnaround 31% (1.8x), flat_base 40% (1.4x), neglected 86% (1.1x), accelerating 36% (1.1x)
- medians at the start: rev growth 1y 3%; rev accel (pp) -1%; op margin 6%; op margin chg 1y -0%; FCF margin 4%; P/S 0.74; EV/EBIT 13.51; P/B 1.30; net cash / mcap 1%; net debt / EBITDA -0.06; share count chg 1y -0%; ROIC 7%; price / 5y high 69%; return 1y 13%; return 2y 12%; volatility 29%; mcap (log10 $) 8.49; analysts 0.00; headcount growth 5%; op margin, own-history pct 55%; sales/share vs price 1y (log gap) -0.08; margin own-pct minus price own-pct -0.04; op-margin slope 8q -0.00; share of 5y in deep drawdown 80%; weeks since 5y low 157.00
- data present: fund 99%, val 100%, perc 37%, emp 15%, bs 99%
- examples (start, best multiple within 5y): SMCI 2021-08 (27.2x); AGHOL.IS 2020-09 (22.8x); EUZ.DE 2017-02 (22.1x); TRIL.NS 2021-12 (20.6x); 2327.TW 2013-02 (17.6x); HTRO.ST 2019-09 (13.8x); BEL.NS 2020-11 (12.1x); NEM.DE 2013-08 (11.8x); ARCLK.IS 2020-06 (11.1x); 6104.TWO 2019-08 (10.2x)

**Archetype 0** — 27% of multibaggers, lift 0.84x, blow-up 6%
- axes (vs all month-ends, + = more): volatility +0.15, value_vs_growth -0.14, cheap_vs_own_history -0.12, industry_growth -0.12, growth -0.12, divergence -0.12, capital_cycle -0.12, best_in_own_history -0.11, efficiency_trend -0.10, accelerating -0.10
- most distinctive features (rank vs all): op_pe_vs_g +0.19, vol52 +0.15, kr_priceToSalesRatio_own +0.15, op_v_shape +0.15, sbc_rev +0.13, kr_evToSales_own +0.13, r260 +0.13, kr_evToEBITDA_own +0.13, kr_enterpriseValueMultiple_own +0.13, current_ratio +0.12, tr_revg_slope8 -0.19, tr_roic_accel -0.19, roic_d1 -0.18, gap_own_roic -0.18, gap_own_opm -0.17, op_sec_accel -0.17, rev_accel -0.17, asset_turn_d1 -0.16
- states over-represented (share, x vs all): accumulation 30% (1.4x), expensive 17% (1.3x), accelerating 32% (1.0x), neglected 74% (1.0x), new_activist 9% (0.9x), compounder 9% (0.9x), turnaround 14% (0.8x), hypergrowth 4% (0.7x)
- medians at the start: rev growth 1y 3%; rev accel (pp) -9%; op margin 14%; op margin chg 1y -1%; FCF margin 7%; P/S 2.25; EV/EBIT 15.79; P/B 2.96; net cash / mcap 2%; net debt / EBITDA -0.39; share count chg 1y 0%; ROIC 15%; price / 5y high 88%; return 1y 31%; return 2y 45%; volatility 35%; mcap (log10 $) 9.09; analysts 1.50; headcount growth 0%; op margin, own-history pct 30%; sales/share vs price 1y (log gap) -0.28; margin own-pct minus price own-pct -0.50; op-margin slope 8q -0.00; share of 5y in deep drawdown 58%; weeks since 5y low 204.00
- data present: fund 99%, val 100%, perc 53%, emp 19%, bs 100%
- examples (start, best multiple within 5y): ASUZU.IS 2020-06 (24.9x); ALARK.IS 2020-02 (24.5x); FROTO.IS 2019-06 (24.0x); NVDA 2014-08 (14.6x); TIINDIA.NS 2019-05 (9.8x); 2345.TW 2014-07 (9.1x); NVMI.TA 2019-07 (8.6x); 300595.SZ 2018-06 (8.5x); AVGO 2013-01 (8.4x); SRT3.DE 2014-08 (8.2x)

### Patterns ranked by lift — 3x within 24 months

| pattern                                                                                                      |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                                                                                      |
|:-------------------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|----------------------:|-----------------:|--------------:|:----------------------------------------------------------------------------------------------------------------------------------------------|
| n_analysts HIGH & op_ind_vol HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & gap_sales_3y LOW            |            4 | 20.542 |                 0.001 |                       57 |                13.119 |            0.927 |         0.109 | NVDA 2020-02 (20.6x); 5803.T 2023-10 (18.0x); 2059.TW 2024-08 (9.7x); 012450.KS 2024-03 (6.7x); MEG.TO 2021-02 (4.7x); 6857.T 2024-09 (4.7x)  |
| n_analysts HIGH & op_ind_vol HIGH & kr_operatingReturnOnAssets_d4 HIGH & gap_sales_3y LOW                    |            4 | 18.918 |                 0.001 |                       57 |                14.039 |            0.643 |         0.093 | NVDA 2020-02 (20.6x); 5706.T 2024-05 (10.6x); 2059.TW 2024-08 (9.7x); 5803.T 2023-03 (7.6x); 012450.KS 2023-06 (7.3x); 6857.T 2024-09 (4.7x)  |
| r104 HIGH & vol52 HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH              |            4 | 18.72  |                 0.001 |                       48 |                15.88  |            0.971 |         0.092 | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); TPC 2024-04 (4.9x); 2345.TW 2024-05 (4.8x)         |
| evs_chg_1y HIGH & op_sec_vol HIGH & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH                        |            4 | 18.69  |                 0.001 |                       63 |                15.42  |            1.864 |         0.089 | CLS 2023-12 (10.4x); CLS.TO 2023-09 (10.2x); TRIL.NS 2023-05 (9.3x); 012450.KS 2024-02 (8.3x); TSLA 2020-05 (7.4x); STRL 2024-05 (7.0x)       |
| op_coil LOW & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_sales_1y LOW & gap_perc_buyshare HIGH      |            4 | 18.598 |                 0.001 |                       46 |                16.226 |            1.369 |         0.084 | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); TPC 2024-04 (4.9x); NVDA 2023-09 (4.1x)            |
| n_analysts HIGH & op_sec_accel HIGH & op_sec_vol HIGH & gap_sales_3y LOW                                     |            4 | 18.546 |                 0.001 |                       62 |                12.428 |            0.89  |         0.048 | 5803.T 2023-10 (18.0x); 012450.KS 2023-06 (7.3x); 5706.T 2024-09 (4.5x); NGD.TO 2024-08 (4.4x); BPE.MI 2024-01 (4.2x); NVDA 2023-11 (3.7x)    |
| n_analysts HIGH & op_ind_vol HIGH & kr_netIncomePerShare_g4 HIGH & gap_sales_3y LOW                          |            4 | 18.362 |                 0.001 |                       52 |                13.119 |            0.663 |         0.096 | NVDA 2020-02 (20.6x); 2059.TW 2024-08 (9.7x); 5803.T 2023-03 (7.6x); 012450.KS 2023-06 (7.3x); 6857.T 2024-09 (4.7x); 5706.T 2024-09 (4.5x)   |
| above_ma30 HIGH & gm LOW & kr_evToSales_own HIGH & gap_perc_buyshare HIGH                                    |            4 | 17.973 |                 0.001 |                       48 |                15.42  |            1.951 |         0.038 | CLS 2023-12 (10.4x); TRIL.NS 2023-05 (9.3x); CLS.TO 2024-02 (7.4x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); POWL 2024-05 (4.8x)              |
| r260 HIGH & gm LOW & op_sec_vol HIGH & gap_perc_buyshare HIGH                                                |            4 | 17.888 |                 0.001 |                       52 |                14.499 |            1.171 |         0.054 | CLS 2023-12 (10.4x); CLS.TO 2023-09 (10.2x); TRIL.NS 2023-05 (9.3x); TSLA 2020-05 (7.4x); STRL 2024-05 (7.0x); 064350.KS 2024-04 (6.1x)       |
| dvol_trend HIGH & ps_vs_own HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH    |            4 | 17.878 |                 0.001 |                       44 |                16.11  |            1.313 |         0.072 | CLS 2023-06 (10.5x); 000150.KS 2024-05 (9.7x); CLS.TO 2024-06 (6.1x); STRL 2024-02 (5.0x); TPC 2024-04 (4.9x); AVGO 2023-09 (4.1x)            |
| op_coil LOW & op_sec_vol HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH       |            4 | 17.672 |                 0.001 |                       45 |                15.42  |            0.724 |         0.09  | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); TPC 2024-04 (4.9x); 2345.TW 2024-05 (4.8x)         |
| as_pb_own HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_sales_1y LOW & gap_perc_buyshare HIGH   |            4 | 17.587 |                 0.001 |                       44 |                17.031 |            1.258 |         0.082 | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); TPC 2024-04 (4.9x); AVGO 2023-09 (4.1x)            |
| up_lo52 HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & tr_roic_consist HIGH & gap_perc_buyshare HIGH |            4 | 17.573 |                 0.001 |                       43 |                15.42  |            1.49  |         0.075 | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); AVGO 2023-09 (4.1x); HWM 2024-02 (3.9x)            |
| ps_vs_own HIGH & op_v_shape HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH    |            4 | 17.512 |                 0.001 |                       45 |                16.11  |            1.111 |         0.036 | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); AVGO 2023-09 (4.1x); NVDA 2023-09 (4.1x)           |
| n_analysts HIGH & op_ind_vol HIGH & kr_assetTurnover_d4 HIGH & gap_sales_3y LOW                              |            4 | 17.395 |                 0.001 |                       57 |                13.349 |            0.434 |         0.068 | NVDA 2020-02 (20.6x); 5706.T 2024-05 (10.6x); 2059.TW 2024-08 (9.7x); 5803.T 2023-03 (7.6x); 6857.T 2024-09 (4.7x); J&KBANK.NS 2023-05 (4.1x) |
| vol52 HIGH & n_analysts HIGH & kr_cashRatio_own HIGH & gap_sales_3y LOW                                      |            4 | 17.271 |                 0.001 |                       45 |                13.119 |            0.966 |         0.053 | NVDA 2019-11 (25.1x); 5803.T 2023-10 (18.0x); 5706.T 2024-05 (10.6x); 6871.T 2023-10 (3.5x); 7735.T 2022-05 (2.9x); 0992.HK 2024-10 (nanx)    |
| trend_r2_52 HIGH & gm LOW & op_sec_vol HIGH & gap_perc_buyshare HIGH                                         |            4 | 17.183 |                 0.001 |                       53 |                15.42  |            1.958 |         0.073 | CLS 2023-12 (10.4x); CLS.TO 2023-09 (10.2x); TRIL.NS 2023-05 (9.3x); TSLA 2020-05 (7.4x); LMB 2023-05 (6.0x); NGD.TO 2024-06 (5.6x)           |
| up_lo52 HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_sales_3y LOW & gap_perc_buyshare HIGH     |            4 | 17.004 |                 0.001 |                       44 |                17.031 |            1.365 |         0.034 | CLS 2023-12 (10.4x); 000150.KS 2024-05 (9.7x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); AVGO 2023-09 (4.1x); NVDA 2023-09 (4.1x)           |
| vol52 HIGH & n_analysts HIGH & op_ind_accel HIGH & gap_sales_3y LOW                                          |            4 | 16.913 |                 0.001 |                       55 |                12.888 |            0.764 |         0.1   | 5803.T 2023-10 (18.0x); 012450.KS 2023-06 (7.3x); 5706.T 2024-07 (6.8x); NGD.TO 2024-08 (4.4x); BPE.MI 2024-01 (4.2x); NVDA 2023-12 (3.8x)    |
| op_ind_vol HIGH & kr_grossProfitMargin LOW & gap_sales_3y LOW & gap_perc_buyshare HIGH                       |            4 | 16.906 |                 0.001 |                       58 |                15.42  |            0.929 |         0.156 | CLS 2023-12 (10.4x); CLS.TO 2023-09 (10.2x); TRIL.NS 2023-05 (9.3x); 012450.KS 2024-02 (8.3x); 000150.KS 2024-03 (7.9x); STRL 2024-05 (7.0x)  |
| n_analysts HIGH & as_pb_own HIGH & op_ind_vol HIGH & kr_researchAndDevelopementToRevenue_d4 LOW              |            4 | 16.795 |                 0.001 |                       47 |                11.968 |            0.45  |         0.132 | 5803.T 2023-10 (18.0x); 5801.T 2024-09 (10.3x); 2059.TW 2024-08 (9.7x); 012450.KS 2024-03 (6.7x); 5706.T 2024-09 (4.5x); NVDA 2023-09 (4.1x)  |
| evs_chg_1y HIGH & kr_dividendPayoutRatio LOW & kr_grossProfitMargin LOW & gap_perc_buyshare HIGH             |            4 | 16.721 |                 0.001 |                       46 |                16.456 |            1.48  |         0.055 | CLS 2023-12 (10.4x); CLS.TO 2023-09 (10.2x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); GHM 2023-10 (4.0x); UFPT 2022-07 (4.0x)                 |
| ps_vs_own HIGH & evs_chg_1y HIGH & kr_salesGeneralAndAdministrativeToRevenue LOW & gap_perc_buyshare HIGH    |            4 | 16.659 |                 0.001 |                       41 |                15.42  |            1.185 |         0.048 | CLS 2023-12 (10.4x); STRL 2024-05 (7.0x); CLS.TO 2024-06 (6.1x); AVGO 2023-09 (4.1x); NVDA 2023-09 (4.1x); TPC 2024-07 (3.3x)                 |
| ps_vs_own HIGH & kr_grossProfitMargin LOW & tr_fcfm_consist HIGH & gap_perc_buyshare HIGH                    |            4 | 16.635 |                 0.001 |                       53 |                15.42  |            1.773 |         0.037 | CLS 2023-06 (10.5x); CLS.TO 2023-09 (10.2x); TSLA 2020-05 (7.4x); STRL 2024-05 (7.0x); LMB 2023-05 (6.0x); HOT.DE 2024-05 (5.1x)              |
| rev_g1 HIGH & n_analysts HIGH & op_ind_vol HIGH & gap_sales_3y LOW                                           |            4 | 16.54  |                 0.001 |                       50 |                11.853 |            0.611 |         0.19  | 5803.T 2023-10 (18.0x); 012450.KS 2024-03 (6.7x); NGD.TO 2024-08 (4.4x); BPE.MI 2024-01 (4.2x); NVDA 2023-12 (3.8x); 6632.T 2023-03 (3.5x)    |

### Patterns ranked by lift — 10x within 5 years

| pattern                                                                                                      |   conditions |    lift |   share_of_month_ends |   multibagger_month_ends |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                         |
|:-------------------------------------------------------------------------------------------------------------|-------------:|--------:|----------------------:|-------------------------:|--------------:|----------------------:|-----------------:|--------------:|:-----------------------------------------------------------------|
| roic HIGH & rd_rev HIGH & upgrades_12m HIGH & beats_4q LOW                                                   |            4 | 108.492 |                 0.001 |                       48 |         0.676 |                17.952 |            1.122 |         0     | NVDA 2019-11 (25.1x)                                             |
| dvol_usd_log HIGH & roic HIGH & beats_4q LOW & kr_researchAndDevelopementToRevenue_d4 LOW                    |            4 | 103.105 |                 0.001 |                       48 |         0.642 |                18.182 |            0.705 |         0.04  | NVDA 2015-09 (21.2x)                                             |
| beats_4q LOW & op_ind_roic HIGH & op_ind_gm HIGH & kr_researchAndDevelopementToRevenue_d4 LOW                |            4 | 101.459 |                 0.001 |                       51 |         0.632 |                18.527 |            0.682 |         0.031 | 2059.TW 2021-08 (36.9x); NVDA 2015-09 (21.2x)                    |
| beats_4q LOW & op_ind_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & kr_quickRatio HIGH            |            4 |  96.819 |                 0.001 |                       44 |         0.603 |                21.519 |            0.332 |         0.076 | 2059.TW 2021-08 (36.9x); NVDA 2015-09 (21.2x)                    |
| ncav_mcap HIGH & upgrades_12m HIGH & beats_4q LOW & kr_researchAndDevelopementToRevenue HIGH                 |            4 |  94.386 |                 0.001 |                       41 |         0.588 |                15.88  |            1.414 |         0.014 | NVDA 2019-11 (25.1x); ETSY 2017-07 (17.8x)                       |
| sbc_rev HIGH & beats_4q LOW & op_ind_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW                  |            4 |  93.74  |                 0.001 |                       48 |         0.584 |                18.182 |            0.716 |         0.042 | NVDA 2015-09 (21.2x)                                             |
| beats_4q LOW & op_ind_gm HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & kr_fixedAssetTurnover_d4 HIGH   |            4 |  92.723 |                 0.001 |                       45 |         0.578 |                18.182 |            0.55  |         0.061 | NVDA 2015-09 (21.2x)                                             |
| beats_4q LOW & ins_net_buy_4q LOW & op_sec_size HIGH & kr_researchAndDevelopementToRevenue_d4 LOW            |            4 |  91.171 |                 0.001 |                       40 |         0.568 |                17.376 |            0.772 |         0.014 | NVDA 2015-09 (21.2x); TSLA 2019-10 (15.7x); AVGO 2020-10 (10.7x) |
| upgrades_12m HIGH & beats_4q LOW & kr_stockBasedCompensationToRevenue HIGH & kr_fixedAssetTurnover_d4 HIGH   |            4 |  90.301 |                 0.001 |                       43 |         0.563 |                17.376 |            0.715 |         0.066 | NVDA 2015-09 (21.2x); TSLA 2019-10 (15.7x)                       |
| ncav_mcap HIGH & upgrades_12m HIGH & beats_4q LOW & op_ind_gm HIGH                                           |            4 |  89.409 |                 0.001 |                       39 |         0.557 |                16.916 |            1.849 |         0     | NVDA 2019-11 (25.1x)                                             |
| rd_rev HIGH & op_roic_x_fcfy HIGH & kr_stockBasedCompensationToRevenue HIGH & insider_buying                 |            4 |  89.327 |                 0.001 |                       39 |         0.557 |                18.642 |            1.002 |         0.043 | MSTR 2020-08 (27.5x); NVDA 2015-09 (21.2x)                       |
| roic HIGH & dd_time_share_260 HIGH & kr_researchAndDevelopementToRevenue HIGH & insider_buying               |            4 |  88.328 |                 0.001 |                       39 |         0.55  |                18.642 |            1.454 |         0.014 | MSTR 2020-08 (27.5x); NVDA 2015-09 (21.2x)                       |
| upgrades_12m HIGH & downgrades_12m HIGH & beats_4q LOW & kr_researchAndDevelopementToRevenue_d4 LOW          |            4 |  87.187 |                 0.001 |                       42 |         0.543 |                16.916 |            0.715 |         0.066 | NVDA 2015-09 (21.2x); TSLA 2019-10 (15.7x)                       |
| op_roic_x_fcfy HIGH & op_ind_gm HIGH & kr_researchAndDevelopementToRevenue HIGH & insider_buying             |            4 |  86.053 |                 0.001 |                       37 |         0.536 |                18.642 |            1.002 |         0.043 | NVDA 2015-09 (21.2x)                                             |
| upgrades_12m HIGH & beats_4q LOW & op_sec_size HIGH & kr_fixedAssetTurnover_d4 HIGH                          |            4 |  86.048 |                 0.001 |                       41 |         0.536 |                16.916 |            0.502 |         0.04  | NVDA 2015-09 (21.2x); TSLA 2019-10 (15.7x)                       |
| sbc_rev HIGH & downgrades_12m HIGH & beats_4q LOW & kr_researchAndDevelopementToRevenue_d4 LOW               |            4 |  84.961 |                 0.001 |                       42 |         0.529 |                16.916 |            0.728 |         0.089 | NVDA 2015-09 (21.2x); TSLA 2019-10 (15.7x)                       |
| roic HIGH & op_ind_gm HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & insider_buying                     |            4 |  84.824 |                 0.001 |                       37 |         0.529 |                18.642 |            1.404 |         0.1   | NVDA 2015-09 (21.2x)                                             |
| roic HIGH & downgrades_12m HIGH & kr_researchAndDevelopementToRevenue HIGH & insider_buying                  |            4 |  84.824 |                 0.001 |                       37 |         0.529 |                18.642 |            0.937 |         0.071 | NVDA 2015-09 (21.2x)                                             |
| ncav_mcap HIGH & beats_4q LOW & op_sec_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW                |            4 |  84.44  |                 0.001 |                       37 |         0.526 |                14.96  |            0.704 |         0     | NVDA 2015-09 (21.2x)                                             |
| dvol_usd_log HIGH & sbc_rev HIGH & ncav_mcap HIGH & ins_buy_quarters_4q HIGH                                 |            4 |  83.365 |                 0.001 |                       40 |         0.519 |                22.209 |            0.851 |         0.026 | NVDA 2015-09 (21.2x)                                             |
| dvol_usd_log HIGH & roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & insider_buying                  |            4 |  82.468 |                 0.001 |                       37 |         0.514 |                18.642 |            0.886 |         0.097 | NVDA 2015-09 (21.2x)                                             |
| beats_4q LOW & op_ind_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW & kr_fixedAssetTurnover_d4 HIGH |            4 |  80.99  |                 0.001 |                       47 |         0.505 |                18.412 |            0.498 |         0.111 | NVDA 2015-09 (21.2x); TTRAK.IS 2020-12 (15.4x)                   |
| range104 HIGH & rd_rev HIGH & upgrades_12m HIGH & beats_4q LOW                                               |            4 |  80.324 |                 0.001 |                       35 |         0.501 |                14.614 |            0.385 |         0.044 | NVDA 2019-11 (25.1x); ETSY 2017-07 (17.8x); TSLA 2019-10 (15.7x) |
| evs_chg_1y HIGH & beats_4q LOW & op_ind_roic HIGH & kr_researchAndDevelopementToRevenue_d4 LOW               |            4 |  80.289 |                 0.001 |                       36 |         0.5   |                17.952 |            0.556 |         0.095 | NVDA 2020-02 (20.6x)                                             |
| upgrades_12m HIGH & downgrades_12m HIGH & beats_4q LOW & kr_fixedAssetTurnover_d4 HIGH                       |            4 |  79.307 |                 0.001 |                       40 |         0.494 |                16.916 |            0.66  |         0.063 | NVDA 2015-09 (21.2x); TSLA 2019-10 (15.7x)                       |

# 5. Uncovered: month-ends no implemented archetype claims


## Uncovered

330,694 month-ends, 5,612 symbols; 3x-within-24m rate 2.98%, 10x-within-5y rate 0.72% (features ranked within month x market inside this sub-population).


### k-means archetypes

917 multibagger starts; base rate 2.98% of month-ends.

|   k |   silhouette |   robustness_ari |
|----:|-------------:|-----------------:|
|   3 |        0.072 |            0.595 |
|   4 |        0.078 |            0.363 |
|   5 |        0.065 |            0.385 |
|   6 |        0.064 |            0.285 |
|   7 |        0.058 |            0.364 |
|   8 |        0.06  |            0.278 |

|   archetype |   n_multibaggers |   share_of_multibaggers |   share_of_all_month_ends |   lift |   rate |   t3_12_rate |   t5_60_rate |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 |
|------------:|-----------------:|------------------------:|--------------------------:|-------:|-------:|-------------:|-------------:|--------------:|----------------------:|-----------------:|--------------:|
|           0 |               44 |                   0.053 |                     0.02  |  2.061 |  0.061 |        0.014 |        0.081 |         0.015 |                16.571 |            0.059 |         0.149 |
|           1 |              378 |                   0.424 |                     0.351 |  1.012 |  0.03  |        0.007 |        0.048 |         0.006 |                16.801 |            0.135 |         0.083 |
|           2 |              495 |                   0.523 |                     0.277 |  0.958 |  0.029 |        0.006 |        0.048 |         0.007 |                17.031 |            0.126 |         0.087 |


**Archetype 0** — 5% of multibaggers, lift 2.06x, blow-up 15%
- axes (vs all month-ends, + = more): headcount_growth +0.46, below_own_cycle -0.37, volatility +0.22, vs_market -0.19, insider_activist +0.17, fallen +0.16, industry_laggard +0.16, divergence +0.15, size -0.14, ignition -0.13
- most distinctive features (rank vs all): emp_g1 +0.46, evs_chg_1y +0.41, opm_vs_5y +0.37, surprise_4q +0.31, beats_4q +0.31, bo_new_holders_12m +0.24, vol52 +0.22, gap_own_gm +0.19, pp_financing_dependence +0.19, op_ind_vol +0.19, ps_vs_own -0.42, dist_hi52 -0.25, maxdd104 -0.22, dist_hi260 -0.22, op_vs_mkt_disthi -0.22, pos104 -0.21, ignored_beats_2y -0.20, pos156 -0.19
- states over-represented (share, x vs all): fund_price_divergence 14% (3.7x), fallen_angel 14% (3.1x), net_net 2% (2.0x), overlevered_stressed 11% (1.5x), neglected 98% (1.3x), expensive 16% (1.1x), deep_value 16% (1.0x), cheap_netcash 9% (0.9x)
- medians at the start: rev growth 1y nan%; rev accel (pp) nan%; op margin 13%; op margin chg 1y nan%; FCF margin 5%; P/S 1.83; EV/EBIT 17.15; P/B 2.84; net cash / mcap 5%; net debt / EBITDA -0.66; share count chg 1y 1%; ROIC 17%; price / 5y high 56%; return 1y -12%; return 2y -3%; volatility 38%; mcap (log10 $) 8.23; analysts 0.00; headcount growth 36%; op margin, own-history pct 72%; sales/share vs price 1y (log gap) 0.11; margin own-pct minus price own-pct 0.47; op-margin slope 8q nan; share of 5y in deep drawdown 53%; weeks since 5y low 88.00
- data present: fund 0%, val 95%, perc 18%, emp 2%, bs 91%
- examples (start, best multiple within 5y): 2930.T 2015-04 (24.8x); BEL.NS 2020-04 (13.4x); HARVIA.HE 2018-10 (12.7x); TRIDENT.NS 2019-07 (12.0x); TATAELXSI.NS 2013-02 (10.2x); JMFINANCIL.NS 2013-02 (10.2x); 082920.KQ 2024-04 (7.1x); ASHOKLEY.NS 2013-03 (6.9x); 6072.T 2024-03 (6.7x); 8341.TW 2014-07 (6.1x)

**Archetype 1** — 42% of multibaggers, lift 1.01x, blow-up 8%
- axes (vs all month-ends, + = more): volatility +0.15, headcount_growth +0.15, growth +0.13, industry_growth +0.12, industry_quality +0.11, profitability +0.10, fallen -0.09, below_own_cycle -0.09, value_vs_growth +0.08, cheap_vs_own_history -0.08
- most distinctive features (rank vs all): pt_rev_6m +0.27, r260 +0.19, r104 +0.18, op_v_shape +0.17, pt_prem_12m +0.17, rev_g1 +0.16, op_sec_growth +0.16, op_ind_growth +0.16, op_dil_adj_g +0.15, op_vs_ind_growth +0.15, ins_net_buy_4q -0.11, ins_buy_quarters_4q -0.09, op_coil -0.09, gap_sales_2y -0.08, gap_sales_3y -0.08, gap_perc_targets -0.07, op_cash_gap -0.07, op_pe_vs_g -0.07
- states over-represented (share, x vs all): compounder 25% (2.6x), hypergrowth 12% (2.3x), margin_inflect_derated 3% (1.9x), headcount_growth 6% (1.5x), accelerating 35% (1.2x), turnaround 17% (1.2x), expensive 16% (1.1x), fund_price_divergence 4% (1.1x)
- medians at the start: rev growth 1y 15%; rev accel (pp) -2%; op margin 16%; op margin chg 1y 0%; FCF margin 7%; P/S 2.20; EV/EBIT 16.31; P/B 3.00; net cash / mcap 4%; net debt / EBITDA -0.81; share count chg 1y 0%; ROIC 17%; price / 5y high 73%; return 1y 13%; return 2y 38%; volatility 38%; mcap (log10 $) 9.01; analysts 3.00; headcount growth 9%; op margin, own-history pct 64%; sales/share vs price 1y (log gap) -0.00; margin own-pct minus price own-pct -0.02; op-margin slope 8q 0.00; share of 5y in deep drawdown 52%; weeks since 5y low 207.50
- data present: fund 100%, val 100%, perc 34%, emp 16%, bs 100%
- examples (start, best multiple within 5y): ALARK.IS 2019-01 (55.9x); 6920.T 2015-11 (34.5x); PGSUS.IS 2018-11 (33.6x); TURSG.IS 2021-08 (28.6x); ASELS.IS 2021-01 (27.1x); FNOX.ST 2016-05 (25.9x); 2327.TW 2015-08 (19.2x); 6027.T 2016-07 (18.6x); 0097.KL 2015-09 (18.2x); MELI 2016-01 (17.2x)

**Archetype 2** — 52% of multibaggers, lift 0.96x, blow-up 9%
- axes (vs all month-ends, + = more): vs_market -0.25, industry_laggard +0.24, fallen +0.22, ignition -0.16, size -0.16, divergence +0.12, profitability -0.12, industry_quality -0.12, industry_cheap +0.12, industry_growth -0.11
- most distinctive features (rank vs all): gap_sales_2y +0.18, dd_time_share_260 +0.16, gap_own_fcfps +0.15, gap_sales_1y +0.15, op_base_age +0.14, wks_since_hi52 +0.14, gap_own_roic +0.12, gap_own_opm +0.12, gap_own_gm +0.11, gap_sales_3y +0.11, dist_hi260 -0.27, op_vs_mkt_disthi -0.27, pos104 -0.26, pos156 -0.25, op_sec_disthi -0.25, above_ma30 -0.25, op_ind_disthi -0.25, op_sec_r52 -0.24
- states over-represented (share, x vs all): fund_price_divergence 20% (5.4x), fallen_angel 22% (5.0x), deep_value 30% (2.0x), net_net 2% (1.8x), turnaround 22% (1.6x), overlevered_delevering 2% (1.4x), overlevered_stressed 10% (1.3x), margin_inflect_derated 2% (1.2x)
- medians at the start: rev growth 1y 0%; rev accel (pp) -9%; op margin 7%; op margin chg 1y -1%; FCF margin 5%; P/S 0.82; EV/EBIT 13.76; P/B 1.30; net cash / mcap -2%; net debt / EBITDA 0.12; share count chg 1y 0%; ROIC 8%; price / 5y high 52%; return 1y -17%; return 2y -17%; volatility 36%; mcap (log10 $) 8.62; analysts 2.00; headcount growth 2%; op margin, own-history pct 36%; sales/share vs price 1y (log gap) 0.16; margin own-pct minus price own-pct 0.14; op-margin slope 8q -0.00; share of 5y in deep drawdown 74%; weeks since 5y low 159.50
- data present: fund 100%, val 100%, perc 34%, emp 19%, bs 99%
- examples (start, best multiple within 5y): ISCTR.IS 2020-05 (87.1x); SUZLON.NS 2019-12 (38.9x); THYAO.IS 2020-03 (35.9x); MAVI.IS 2020-09 (31.6x); GARAN.IS 2020-09 (24.3x); EUZ.DE 2017-02 (22.1x); STRL 2020-03 (20.2x); AGHOL.IS 2020-11 (20.1x); ANSGR.IS 2021-08 (19.9x); 2327.TW 2013-02 (17.6x)

### Patterns ranked by lift — 3x within 24 months

| pattern                                                                                              |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                                                                                           |   t10_60_rate |
|:-----------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|----------------------:|-----------------:|--------------:|:---------------------------------------------------------------------------------------------------------------------------------------------------|--------------:|
| vol52 HIGH & buy_share_d12 HIGH & tr_gm_consist HIGH & gap_sales_3y LOW                              |            4 | 14.42  |                 0.001 |                       65 |                12.198 |            0.478 |         0.188 | 2059.TW 2024-07 (10.1x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); ETSY 2020-03 (6.7x); STRL 2023-10 (5.3x)                |       nan     |
| range104 HIGH & roe HIGH & buy_share_d12 HIGH & gap_sales_3y LOW                                     |            4 | 13.705 |                 0.001 |                       73 |                12.658 |            0.128 |         0.147 | NVDA 2020-05 (15.6x); 2059.TW 2024-07 (10.1x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); SMCI 2023-02 (5.7x); 6857.T 2024-08 (5.3x)            |       nan     |
| vol52 HIGH & buy_share_d12 HIGH & tr_gm_streak HIGH & gap_sales_3y LOW                               |            4 | 13.684 |                 0.001 |                       63 |                11.968 |            0.311 |         0.194 | 2059.TW 2024-07 (10.1x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x); BELFB 2024-06 (4.8x)                 |       nan     |
| vol52 HIGH & buy_share_d12 HIGH & kr_returnOnCapitalEmployed HIGH & gap_sales_3y LOW                 |            4 | 13.524 |                 0.001 |                       67 |                12.428 |            0.128 |         0.137 | 2059.TW 2024-07 (10.1x); CLS.TO 2024-08 (6.1x); 5803.T 2024-09 (6.0x); CLS 2024-06 (5.9x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x)                |       nan     |
| n_analysts HIGH & op_ind_vol HIGH & kr_researchAndDevelopementToRevenue HIGH & gap_sales_3y LOW      |            4 | 13.454 |                 0.001 |                       60 |                15.535 |            0.917 |         0.05  | NVDA 2019-08 (29.6x); 5803.T 2024-04 (13.7x); 5706.T 2024-05 (10.6x); 012450.KS 2023-04 (8.2x); 036930.KQ 2024-09 (7.8x); 002281.SZ 2024-06 (5.9x) |         0.172 |
| range104 HIGH & gm LOW & buy_share_d12 HIGH & kr_evToSales_own HIGH                                  |            4 | 13.392 |                 0.001 |                       63 |                15.19  |            0.399 |         0.12  | AGX 2024-06 (10.6x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x); HOT.DE 2024-07 (4.4x)                    |         0.02  |
| vol52 HIGH & n_analysts HIGH & kr_stockBasedCompensationToRevenue HIGH & gap_sales_3y LOW            |            4 | 13.362 |                 0.001 |                       58 |                16.916 |            1.091 |         0.083 | NVDA 2019-08 (29.6x); 012450.KS 2023-04 (8.2x); 6857.T 2024-08 (5.3x); BPE.MI 2023-12 (4.4x); AVGO 2024-05 (3.4x); 0992.HK 2024-08 (3.3x)          |       nan     |
| vol52 HIGH & n_analysts HIGH & kr_returnOnTangibleAssets HIGH & gap_sales_3y LOW                     |            4 | 13.253 |                 0.001 |                       62 |                16.456 |            0.868 |         0.152 | NVDA 2019-08 (29.6x); 2059.TW 2024-07 (10.1x); 5803.T 2024-09 (6.0x); 6857.T 2024-08 (5.3x); J&KBANK.NS 2023-05 (4.1x); 6632.T 2023-03 (3.5x)      |       nan     |
| range104 HIGH & buy_share_d12 HIGH & kr_evToSales_own HIGH & kr_returnOnInvestedCapital HIGH         |            4 | 13.168 |                 0.001 |                       60 |                12.888 |            0.373 |         0.102 | NVDA 2020-05 (15.6x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x)                   |       nan     |
| buy_share_d12 HIGH & op_v_shape HIGH & kr_returnOnInvestedCapital HIGH & gap_sales_2y LOW            |            4 | 12.78  |                 0.001 |                       62 |                12.198 |            0.078 |         0.127 | 2059.TW 2024-07 (10.1x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); 5803.T 2024-09 (6.0x); STRL 2023-10 (5.3x); 6857.T 2024-08 (5.3x)              |       nan     |
| buy_share_d12 HIGH & op_coil LOW & op_ind_pb HIGH & gap_sales_3y LOW                                 |            4 | 12.75  |                 0.001 |                       63 |                13.809 |            0.111 |         0.176 | NVDA 2020-05 (15.6x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); ETSY 2020-03 (6.7x); STRL 2023-10 (5.3x); 6857.T 2024-08 (5.3x)                |       nan     |
| buy_share_d12 HIGH & op_v_shape HIGH & tr_gm_streak HIGH & gap_sales_2y LOW                          |            4 | 12.693 |                 0.001 |                       54 |                12.428 |            0.331 |         0.197 | 2059.TW 2024-07 (10.1x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); STRL 2023-10 (5.3x); BELFB 2024-06 (4.8x); GHM 2024-06 (4.3x)                  |       nan     |
| range104 HIGH & dvol_usd_log HIGH & buy_share_d12 HIGH & gap_sales_3y LOW                            |            4 | 12.655 |                 0.001 |                       65 |                13.809 |            0.282 |         0.07  | NVDA 2020-05 (15.6x); 2059.TW 2024-07 (10.1x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); 6857.T 2024-08 (5.3x)             |       nan     |
| range104 HIGH & buy_share_d12 HIGH & kr_grossProfitMargin LOW & kr_priceToBookRatio_d4 HIGH          |            4 | 12.563 |                 0.001 |                       60 |                13.694 |            0.275 |         0.07  | AGX 2024-06 (10.6x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x); HOT.DE 2024-07 (4.4x)                    |         0     |
| vol52 HIGH & roe HIGH & n_analysts HIGH & gap_sales_3y LOW                                           |            4 | 12.561 |                 0.001 |                       71 |                15.88  |            0.69  |         0.135 | NVDA 2019-08 (29.6x); 5803.T 2024-06 (11.8x); 2059.TW 2024-07 (10.1x); 6857.T 2024-08 (5.3x); 012450.KS 2024-06 (4.2x); 6632.T 2023-03 (3.5x)      |       nan     |
| vol52 HIGH & buy_share_d12 HIGH & as_pb_own HIGH & tr_gm_streak HIGH                                 |            4 | 12.552 |                 0.001 |                       56 |                11.853 |            0.519 |         0.118 | 2059.TW 2024-07 (10.1x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); GOGO 2020-07 (6.5x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x)                  |         0     |
| vol52 HIGH & buy_share_d12 HIGH & tr_roic_slope8 HIGH & gap_sales_3y LOW                             |            4 | 12.426 |                 0.001 |                       61 |                11.047 |            0.222 |         0.161 | CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x); BELFB 2024-06 (4.8x); GHM 2024-07 (3.2x)                      |         0     |
| range104 HIGH & buy_share_d12 HIGH & op_ind_roic HIGH & gap_sales_3y LOW                             |            4 | 12.419 |                 0.001 |                       63 |                13.119 |            0.091 |         0.23  | NVDA 2020-05 (15.6x); 2059.TW 2024-07 (10.1x); 5803.T 2024-09 (6.0x); STRL 2023-10 (5.3x); BELFB 2024-06 (4.8x); 6857.T 2024-09 (4.7x)             |       nan     |
| range104 HIGH & buy_share_d12 HIGH & kr_grossProfitMargin LOW & tr_roic_slope8 HIGH                  |            4 | 12.292 |                 0.001 |                       49 |                12.198 |            0.222 |         0.125 | CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x); GHM 2024-06 (4.3x); SAAB-B.ST 2023-09 (4.2x)                  |         0.017 |
| range104 HIGH & ebit_g1 HIGH & gm LOW & buy_share_d12 HIGH                                           |            4 | 12.29  |                 0.001 |                       54 |                12.083 |            0.35  |         0.132 | CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x); GHM 2024-06 (4.3x); EME 2023-10 (3.7x)                        |         0.019 |
| range104 HIGH & buy_share_d12 HIGH & kr_researchAndDevelopementToRevenue_own HIGH & gap_sales_3y LOW |            4 | 12.254 |                 0.001 |                       57 |                13.809 |            0.292 |         0.193 | NVDA 2020-05 (15.6x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); 5803.T 2024-09 (6.0x); BELFB 2024-06 (4.8x); SAAB-B.ST 2023-09 (4.2x)             |         0.08  |
| vol52 HIGH & buy_share_d12 HIGH & kr_priceToSalesRatio_d4 HIGH & gap_sales_2y LOW                    |            4 | 12.214 |                 0.001 |                       59 |                12.658 |            0.448 |         0.19  | 2059.TW 2024-07 (10.1x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); 6857.T 2024-08 (5.3x)              |       nan     |
| pb HIGH & n_analysts HIGH & op_ind_vol HIGH & gap_sales_3y LOW                                       |            4 | 12.205 |                 0.001 |                       66 |                14.96  |            0.491 |         0.12  | NVDA 2019-08 (29.6x); 5803.T 2024-04 (13.7x); 2059.TW 2024-07 (10.1x); 012450.KS 2023-04 (8.2x); 6857.T 2024-08 (5.3x); ETSY 2020-05 (3.2x)        |       nan     |
| r260 HIGH & buy_share_d12 HIGH & op_ind_pb HIGH & op_ind_vol HIGH                                    |            4 | 12.182 |                 0.001 |                       71 |                13.809 |            0.257 |         0.138 | 2059.TW 2024-07 (10.1x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); 3443.TW 2024-08 (5.6x); STRL 2023-10 (5.3x); 6857.T 2024-08 (5.3x)          |       nan     |
| vol52 HIGH & buy_share_d12 HIGH & as_pb_own HIGH & kr_returnOnInvestedCapital HIGH                   |            4 | 12.087 |                 0.001 |                       56 |                12.313 |            0.29  |         0.114 | 2059.TW 2024-07 (10.1x); 5803.T 2024-08 (7.8x); CLS.TO 2024-09 (7.5x); CLS 2024-09 (7.2x); SMCI 2023-02 (5.7x); STRL 2023-10 (5.3x)                |       nan     |

### Patterns ranked by lift — 10x within 5 years

| pattern                                                                                                                   |   conditions |   lift |   share_of_month_ends |   multibagger_month_ends |   t10_60_rate |   median_months_to_3x |   median_fwd_24m |   p_blowup_50 | examples                                                                               |
|:--------------------------------------------------------------------------------------------------------------------------|-------------:|-------:|----------------------:|-------------------------:|--------------:|----------------------:|-----------------:|--------------:|:---------------------------------------------------------------------------------------|
| rd_rev HIGH & kr_debtServiceCoverageRatio_d4 LOW & kr_fixedAssetTurnover_d4 HIGH & insider_buying                         |            4 | 60.073 |                 0.001 |                       41 |         0.43  |                18.872 |            0.828 |         0.01  | ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                                             |
| surprise_4q LOW & kr_researchAndDevelopementToRevenue HIGH & kr_fixedAssetTurnover_d4 HIGH & insider_buying               |            4 | 54.947 |                 0.001 |                       40 |         0.393 |                14.384 |            1.494 |         0.052 | MSTR 2020-09 (27.7x); TSLA 2019-08 (22.9x); NVDA 2015-09 (21.2x); ABMD 2014-05 (17.9x) |
| current_ratio HIGH & rd_rev HIGH & surprise_4q LOW & insider_buying                                                       |            4 | 54.048 |                 0.001 |                       37 |         0.387 |                19.563 |            0.808 |         0.042 | NVDA 2015-09 (21.2x); ABMD 2014-05 (17.9x)                                             |
| op_roic_x_fcfy HIGH & op_sec_roic HIGH & kr_researchAndDevelopementToRevenue HIGH & insider_buying                        |            4 | 53.306 |                 0.001 |                       38 |         0.381 |                19.102 |            0.907 |         0.08  | NVDA 2015-09 (21.2x)                                                                   |
| roic HIGH & kr_researchAndDevelopementToRevenue HIGH & kr_fixedAssetTurnover_d4 HIGH & insider_buying                     |            4 | 52.736 |                 0.001 |                       37 |         0.377 |                17.722 |            0.847 |         0.105 | MSTR 2020-09 (27.7x); NVDA 2015-09 (21.2x)                                             |
| roic HIGH & rd_rev HIGH & ins_buy_quarters_4q HIGH & near_highs                                                           |            4 | 51.129 |                 0.001 |                       37 |         0.366 |                22.555 |            0.853 |         0.089 | NVDA 2015-09 (21.2x)                                                                   |
| dvol_usd_log HIGH & rd_rev HIGH & op_roic_x_fcfy HIGH & insider_buying                                                    |            4 | 50.597 |                 0.001 |                       38 |         0.362 |                19.102 |            0.394 |         0.067 | NVDA 2015-09 (21.2x)                                                                   |
| rd_rev HIGH & op_sec_roic HIGH & op_ind_gm HIGH & insider_buying                                                          |            4 | 49.762 |                 0.001 |                       42 |         0.356 |                20.713 |            0.992 |         0.085 | NVDA 2015-09 (21.2x)                                                                   |
| dvol_usd_log HIGH & ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue HIGH & kr_quickRatio HIGH              |            4 | 48.865 |                 0.001 |                       36 |         0.35  |                24.051 |            0.699 |         0.029 | NVDA 2015-09 (21.2x)                                                                   |
| ncav_mcap HIGH & roic HIGH & ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue HIGH                          |            4 | 47.111 |                 0.001 |                       39 |         0.337 |                21.864 |            0.84  |         0.017 | NVDA 2015-09 (21.2x)                                                                   |
| ins_net_buy_4q LOW & kr_researchAndDevelopementToRevenue HIGH & kr_fixedAssetTurnover_d4 HIGH & insider_buying            |            4 | 46.54  |                 0.001 |                       37 |         0.333 |                14.499 |            0.948 |         0.009 | TSLA 2019-08 (22.9x); NVDA 2015-09 (21.2x); ABMD 2014-05 (17.9x)                       |
| current_ratio HIGH & rd_rev HIGH & kr_debtServiceCoverageRatio_d4 LOW & insider_buying                                    |            4 | 46.138 |                 0.001 |                       34 |         0.33  |                20.598 |            0.828 |         0.029 | ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                                             |
| dvol_usd_log HIGH & rd_rev HIGH & kr_fixedAssetTurnover_d4 HIGH & insider_buying                                          |            4 | 45.122 |                 0.001 |                       37 |         0.323 |                17.722 |            0.79  |         0.027 | TSLA 2019-08 (22.9x); NVDA 2015-09 (21.2x)                                             |
| rd_rev HIGH & op_ind_gm HIGH & dd_time_share_260 HIGH & insider_buying                                                    |            4 | 44.319 |                 0.001 |                       36 |         0.317 |                18.527 |            1.02  |         0.114 | NVDA 2015-09 (21.2x)                                                                   |
| rd_rev HIGH & ins_buy_quarters_4q HIGH & kr_fixedAssetTurnover_own HIGH & kr_quickRatio HIGH                              |            4 | 44.258 |                 0.001 |                       31 |         0.317 |                19.563 |            0.888 |         0.051 | ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                                             |
| ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue HIGH & kr_currentRatio HIGH & kr_payablesTurnover_own HIGH |            4 | 42.842 |                 0.001 |                       29 |         0.306 |                17.952 |            0.763 |         0.047 | ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                                             |
| sbc_rev HIGH & rd_rev HIGH & beats_4q LOW & insider_buying                                                                |            4 | 42.671 |                 0.001 |                       34 |         0.305 |                15.65  |            0.41  |         0.096 | TSLA 2019-08 (22.9x); NVDA 2015-09 (21.2x)                                             |
| sbc_rev HIGH & rd_rev HIGH & ins_buy_quarters_4q HIGH & kr_debtServiceCoverageRatio_d4 LOW                                |            4 | 42.669 |                 0.001 |                       36 |         0.305 |                19.217 |            0.672 |         0.041 | ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                                             |
| rd_rev HIGH & op_ind_roic HIGH & op_ind_size HIGH & insider_buying                                                        |            4 | 41.645 |                 0.001 |                       42 |         0.298 |                20.713 |            0.613 |         0.05  | NVDA 2015-09 (21.2x)                                                                   |
| roic HIGH & rd_rev HIGH & kr_debtServiceCoverageRatio HIGH & insider_buying                                               |            4 | 41.299 |                 0.001 |                       29 |         0.295 |                23.705 |            0.419 |         0.041 | NVDA 2013-10 (18.9x)                                                                   |
| surprise_4q LOW & ins_buy_quarters_4q HIGH & kr_researchAndDevelopementToRevenue HIGH & neglected                         |            4 | 41.26  |                 0.001 |                       41 |         0.295 |                18.642 |            0.628 |         0.119 | NVDA 2015-09 (21.2x); ABMD 2014-05 (17.9x)                                             |
| rd_rev HIGH & ins_buy_quarters_4q HIGH & kr_daysOfPayablesOutstanding_d4 LOW & kr_fixedAssetTurnover_d4 HIGH              |            4 | 40.769 |                 0.001 |                       35 |         0.292 |                18.642 |            0.668 |         0.086 | TSLA 2019-08 (22.9x); ABMD 2013-09 (21.8x); NVDA 2016-01 (18.3x)                       |
| rd_rev HIGH & beats_4q LOW & kr_researchAndDevelopementToRevenue_d4 LOW & insider_buying                                  |            4 | 40.767 |                 0.001 |                       33 |         0.292 |                14.499 |            0.157 |         0.119 | TSLA 2019-08 (22.9x); NVDA 2015-09 (21.2x)                                             |
| kr_researchAndDevelopementToRevenue HIGH & kr_fixedAssetTurnover_d4 HIGH & kr_solvencyRatio_d4 LOW & insider_buying       |            4 | 40.62  |                 0.001 |                       30 |         0.291 |                19.793 |            0.471 |         0.151 | MSTR 2020-09 (27.7x); ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                       |
| ncav_mcap HIGH & rd_rev HIGH & kr_debtServiceCoverageRatio_d4 LOW & insider_buying                                        |            4 | 40.58  |                 0.001 |                       29 |         0.29  |                18.412 |            0.719 |         0.03  | ABMD 2013-09 (21.8x); NVDA 2015-09 (21.2x)                                             |