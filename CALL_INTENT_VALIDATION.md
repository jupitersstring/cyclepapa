# Earnings-call intent -- out-of-time validation

Generated 2026-09-24 by `call_intent_model.py`. Calls analysed: 15317 (1935 names). Labelled: 8160; train < 2025-06-01: 4079, test >= 2025-06-01: 4081. Test base rate (ACTED): 31.2%.

ACTED = share count down >= 2% or dividends up >= 25%/initiated over the next two fiscal quarters, or a dated action 8-K within 183 days of the call.

## Does the language predict action? (test set, AUC)

| model | AUC |
|---|---|
| interpretable rule score (no fitting) | 0.642 |
| logistic, language features only | 0.655 |
| baseline: past behaviour only (share-count + dividend trend) | 0.596 |
| baseline + language v1 (families, novelty, Q&A) | 0.650 |
| baseline + language v2 (+ CEO/CFO, scripted vs Q&A, firming, action size, discount) | 0.655 |
| v2, DEEP-DISCOUNT calls only (P/B <= 0.8 at the call; n=1047, base 0.293) | 0.644 |
| rule score, companies NOT already shrinking share count | 0.599 |

Top decile hit-rate (test): rule 53.7% vs base 31.2% (lift 1.72x); baseline+language 58.8% (lift 1.88x).

## Lift by linguistic family (calls with family score >= 0.8, all labelled)

| family | calls | lift vs base |
|---|---|---|
| DIVIDEND_RETURN | 955 | 1.59x |
| BUYBACK | 2779 | 1.57x |
| GOVERNANCE | 164 | 1.51x |
| TENDER | 40 | 1.48x |
| VALUE_GAP | 674 | 1.40x |
| novelty | 1908 | 1.23x |
| MONETIZE | 1819 | 1.15x |
| STRATEGIC_REVIEW | 279 | 1.07x |
| ANTICIPATION | 2355 | 1.06x |
| COST | 2139 | 1.03x |
| DELEVER | 1031 | 1.00x |

## Out of time: model probability quintile -> what happened next (test set)

| quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 850 | 17% | -1.3% | -6.2% |
| Q2 | 850 | 19% | -7.4% | -8.0% |
| Q3 | 851 | 22% | +14.4% | -7.9% |
| Q4 | 850 | 34% | -4.6% | -3.9% |
| Q5 (highest) | 851 | 47% | -3.9% | -4.6% |

## The thesis test: deep-discount calls (P/B <= 0.8 at the call), test set

| model quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 212 | 14% | +2.1% | -7.3% |
| Q2 | 213 | 20% | +0.6% | -4.5% |
| Q3 | 212 | 21% | +4.9% | -2.1% |
| Q4 | 213 | 32% | +1.8% | -1.3% |
| Q5 (highest) | 213 | 46% | -0.4% | -4.7% |

## Pre-specified return hypotheses, deep-discount calls (all periods, no fitting)

| hypothesis | n (6m) | mean 6m | median 6m | n (12m) | mean 12m | median 12m |
|---|---|---|---|---|---|---|
| all deep-discount calls | 2140 | +0.0% | -5.9% | 1449 | -1.0% | -11.5% |
| H1 NEW shareholder-action family | 214 | +1.8% | -5.0% | 131 | +2.9% | -6.9% |
| H2 commitment firming across calls | 551 | -1.1% | -6.7% | 364 | -4.7% | -11.0% |
| H3 value-gap + committed action | 232 | -0.6% | -6.5% | 143 | +5.5% | -13.6% |
| H4 CEO and CFO both commit | 261 | +3.5% | -3.1% | 169 | +0.3% | -7.8% |
| contrast: no shareholder-action language | 485 | +1.4% | -6.2% | 345 | +4.1% | -12.2% |

Reading: none of the intent patterns beats deep-discount calls with NO shareholder language by more than noise. Management language predicts WHETHER a company acts (AUC above); it does not, by itself, predict the re-rating -- the market prices stated intent quickly. Use it to confirm a set-up, not as a return signal.

## Stated action size (buyback / tender as % of market cap at the call), all calls

| size | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| <2% of mcap | 494 | 0.282 | -4.9% | -5.9% |
| 2-5% | 380 | 0.446 | -4.7% | -6.7% |
| 5-10% | 403 | 0.492 | -5.0% | -5.4% |
| >=10% | 695 | 0.538 | -7.5% | -9.0% |

Companies that ACTED returned -0.066 vs 0.016 for those that did not (mean 6-month excess vs SPY): in this sample the action itself did not re-rate value names on its own. The language is a strong predictor of ACTION and a weak stand-alone predictor of returns -- use it to corroborate a discount/governance set-up (does management intend to act?), not as a return signal by itself.

## Forward 6-month excess return vs SPY by rule-score quintile (all calls)

| quintile | calls | mean | median | share > +25% |
|---|---|---|---|---|
| Q1 | 1666 | +15.1% | -10.3% | 11.2% |
| Q2 | 1666 | -5.7% | -9.1% | 11.8% |
| Q3 | 1666 | -4.6% | -7.0% | 10.7% |
| Q4 | 1666 | -4.9% | -6.9% | 10.3% |
| Q5 (highest) | 1666 | -5.0% | -7.5% | 10.7% |

## Fitted weights (standardised, baseline + language, all labelled data)

| feature | weight |
|---|---|
| BUYBACK | +0.375 |
| DIVIDEND_RETURN | +0.167 |
| prep_act | +0.119 |
| deep | -0.112 |
| size_pct | +0.105 |
| past_div_up | -0.096 |
| ceo_act | -0.095 |
| press_ratio | +0.085 |
| VALUE_GAP | +0.079 |
| escalation | -0.074 |
| MONETIZE | +0.066 |
| both_act | +0.050 |
| ANTICIPATION | +0.048 |
| cfo_act | +0.044 |
| STRATEGIC_REVIEW | +0.044 |
| past_sh_chg | +0.040 |
| firming | -0.040 |
| GOVERNANCE | +0.027 |
| DELEVER | -0.026 |
| neg_total | -0.019 |
| COST | -0.017 |
| novelty | -0.017 |
| deep_x_act | +0.014 |
| qa_act | +0.011 |
| a_evade | +0.010 |
| deep_x_gap | -0.006 |
| TENDER | +0.003 |
| a_commit | +0.002 |
