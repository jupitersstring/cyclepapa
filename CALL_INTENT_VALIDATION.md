# Earnings-call intent -- out-of-time validation

Generated 2026-09-24 by `call_intent_model.py`. Calls analysed: 17777 (2381 names). Labelled: 9541; train < 2025-06-01: 4588, test >= 2025-06-01: 4953. Test base rate (ACTED): 30.9%.

ACTED = share count down >= 2% or dividends up >= 25%/initiated over the next two fiscal quarters, or a dated action 8-K within 183 days of the call.

## Does the language predict action? (test set, AUC)

| model | AUC |
|---|---|
| interpretable rule score (no fitting) | 0.642 |
| logistic, language features only | 0.657 |
| baseline: past behaviour only (share-count + dividend trend) | 0.594 |
| baseline + language v1 (families, novelty, Q&A) | 0.652 |
| baseline + language v2 (+ CEO/CFO, scripted vs Q&A, firming, action size, discount) | 0.658 |
| v2, DEEP-DISCOUNT calls only (P/B <= 0.8 at the call; n=1079, base 0.291) | 0.643 |
| rule score, companies NOT already shrinking share count | 0.601 |

Top decile hit-rate (test): rule 52.7% vs base 30.9% (lift 1.71x); baseline+language 61.0% (lift 1.98x).

## Lift by linguistic family (calls with family score >= 0.8, all labelled)

| family | calls | lift vs base |
|---|---|---|
| DIVIDEND_RETURN | 1108 | 1.60x |
| GOVERNANCE | 199 | 1.59x |
| BUYBACK | 3181 | 1.58x |
| VALUE_GAP | 760 | 1.37x |
| TENDER | 53 | 1.33x |
| novelty | 2354 | 1.21x |
| MONETIZE | 2159 | 1.16x |
| ANTICIPATION | 2861 | 1.05x |
| COST | 2508 | 1.03x |
| STRATEGIC_REVIEW | 326 | 1.01x |
| DELEVER | 1180 | 1.00x |

## Out of time: model probability quintile -> what happened next (test set)

| quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 1029 | 17% | +7.2% | -6.0% |
| Q2 | 1029 | 16% | -4.4% | -8.6% |
| Q3 | 1029 | 21% | +13.7% | -7.5% |
| Q4 | 1029 | 34% | -3.3% | -3.3% |
| Q5 (highest) | 1030 | 48% | -2.7% | -4.2% |

## The thesis test: deep-discount calls (P/B <= 0.8 at the call), test set

| model quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 219 | 16% | +2.6% | -7.1% |
| Q2 | 219 | 16% | +3.2% | -5.2% |
| Q3 | 219 | 23% | +8.0% | -0.3% |
| Q4 | 219 | 33% | +1.7% | -1.1% |
| Q5 (highest) | 220 | 44% | +0.2% | -4.6% |

## Pre-specified return hypotheses, deep-discount calls (all periods, no fitting)

| hypothesis | n (6m) | mean 6m | median 6m | n (12m) | mean 12m | median 12m |
|---|---|---|---|---|---|---|
| all deep-discount calls | 2202 | +1.3% | -5.8% | 1493 | +7.6% | -11.5% |
| H1 NEW shareholder-action family | 220 | +2.5% | -5.0% | 133 | +3.3% | -6.9% |
| H2 commitment firming across calls | 560 | -1.0% | -6.7% | 367 | -4.7% | -11.0% |
| H3 value-gap + committed action | 237 | -0.0% | -6.5% | 147 | +8.3% | -9.9% |
| H4 CEO and CFO both commit | 268 | +4.7% | -2.1% | 175 | +5.6% | -4.7% |
| contrast: no shareholder-action language | 501 | +3.7% | -6.4% | 358 | +34.7% | -12.3% |

Reading: none of the intent patterns beats deep-discount calls with NO shareholder language by more than noise. Management language predicts WHETHER a company acts (AUC above); it does not, by itself, predict the re-rating -- the market prices stated intent quickly. Use it to confirm a set-up, not as a return signal.

## Stated action size (buyback / tender as % of market cap at the call), all calls

| size | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| <2% of mcap | 593 | 0.292 | -4.3% | -6.0% |
| 2-5% | 441 | 0.433 | -3.5% | -6.3% |
| 5-10% | 449 | 0.493 | -3.9% | -5.4% |
| >=10% | 778 | 0.547 | -5.6% | -8.1% |

Companies that ACTED returned -0.048 vs 0.037 for those that did not (mean 6-month excess vs SPY): in this sample the action itself did not re-rate value names on its own. The language is a strong predictor of ACTION and a weak stand-alone predictor of returns -- use it to corroborate a discount/governance set-up (does management intend to act?), not as a return signal by itself.

## Forward 6-month excess return vs SPY by rule-score quintile (all calls)

| quintile | calls | mean | median | share > +25% |
|---|---|---|---|---|
| Q1 | 1945 | +17.8% | -10.3% | 12.9% |
| Q2 | 1946 | -2.8% | -8.7% | 14.1% |
| Q3 | 1946 | -3.6% | -7.0% | 12.0% |
| Q4 | 1946 | -3.8% | -6.6% | 11.4% |
| Q5 (highest) | 1946 | -3.1% | -6.8% | 12.2% |

## Fitted weights (standardised, baseline + language, all labelled data)

| feature | weight |
|---|---|
| BUYBACK | +0.390 |
| DIVIDEND_RETURN | +0.166 |
| prep_act | +0.114 |
| deep | -0.104 |
| size_pct | +0.102 |
| press_ratio | +0.101 |
| ceo_act | -0.091 |
| MONETIZE | +0.087 |
| past_div_up | -0.083 |
| novelty | -0.074 |
| VALUE_GAP | +0.059 |
| GOVERNANCE | +0.054 |
| cfo_act | +0.051 |
| escalation | -0.048 |
| STRATEGIC_REVIEW | +0.036 |
| ANTICIPATION | +0.034 |
| firming | -0.031 |
| both_act | +0.028 |
| past_sh_chg | +0.026 |
| DELEVER | -0.020 |
| a_evade | +0.013 |
| a_commit | +0.012 |
| deep_x_gap | +0.006 |
| COST | -0.006 |
| deep_x_act | +0.005 |
| neg_total | -0.004 |
| qa_act | -0.003 |
| TENDER | -0.003 |
