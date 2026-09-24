# Earnings-call intent -- out-of-time validation

Generated 2026-09-24 by `call_intent_model.py`. Calls analysed: 12667 (1356 names). Labelled: 6944; train < 2025-06-01: 3555, test >= 2025-06-01: 3389. Test base rate (ACTED): 30.6%.

ACTED = share count down >= 2% or dividends up >= 25%/initiated over the next two fiscal quarters, or a dated action 8-K within 183 days of the call.

## Does the language predict action? (test set, AUC)

| model | AUC |
|---|---|
| interpretable rule score (no fitting) | 0.653 |
| logistic, language features only | 0.670 |
| baseline: past behaviour only (share-count + dividend trend) | 0.598 |
| baseline + language v1 (families, novelty, Q&A) | 0.666 |
| baseline + language v2 (+ CEO/CFO, scripted vs Q&A, firming, action size, discount) | 0.669 |
| v2, DEEP-DISCOUNT calls only (P/B <= 0.8 at the call; n=1044, base 0.292) | 0.652 |
| rule score, companies NOT already shrinking share count | 0.601 |

Top decile hit-rate (test): rule 53.3% vs base 30.6% (lift 1.74x); baseline+language 57.7% (lift 1.89x).

## Lift by linguistic family (calls with family score >= 0.8, all labelled)

| family | calls | lift vs base |
|---|---|---|
| TENDER | 25 | 2.17x |
| DIVIDEND_RETURN | 875 | 1.62x |
| BUYBACK | 2557 | 1.60x |
| VALUE_GAP | 607 | 1.46x |
| GOVERNANCE | 138 | 1.39x |
| novelty | 1577 | 1.22x |
| MONETIZE | 1547 | 1.14x |
| STRATEGIC_REVIEW | 239 | 1.11x |
| DELEVER | 900 | 1.05x |
| ANTICIPATION | 1980 | 1.03x |
| COST | 1798 | 1.01x |

## Out of time: model probability quintile -> what happened next (test set)

| quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 681 | 14% | -2.0% | -6.9% |
| Q2 | 681 | 18% | -10.4% | -11.0% |
| Q3 | 682 | 22% | -5.1% | -5.0% |
| Q4 | 681 | 35% | -3.1% | -2.5% |
| Q5 (highest) | 682 | 49% | -4.2% | -4.4% |

## The thesis test: deep-discount calls (P/B <= 0.8 at the call), test set

| model quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 212 | 15% | +3.1% | -5.9% |
| Q2 | 212 | 17% | +1.0% | -5.7% |
| Q3 | 212 | 21% | +3.5% | -2.0% |
| Q4 | 212 | 33% | +1.9% | -1.6% |
| Q5 (highest) | 212 | 47% | -0.1% | -4.2% |

## Pre-specified return hypotheses, deep-discount calls (all periods, no fitting)

| hypothesis | n (6m) | mean 6m | median 6m | n (12m) | mean 12m | median 12m |
|---|---|---|---|---|---|---|
| all deep-discount calls | 2136 | +0.1% | -5.8% | 1447 | -1.0% | -11.3% |
| H1 NEW shareholder-action family | 212 | +1.9% | -5.0% | 131 | +2.9% | -6.9% |
| H2 commitment firming across calls | 552 | -1.1% | -6.6% | 367 | -4.8% | -11.0% |
| H3 value-gap + committed action | 232 | -0.6% | -6.5% | 143 | +5.5% | -13.6% |
| H4 CEO and CFO both commit | 261 | +3.5% | -3.1% | 169 | +0.3% | -7.8% |
| contrast: no shareholder-action language | 478 | +1.4% | -6.2% | 340 | +4.6% | -11.7% |

Reading: none of the intent patterns beats deep-discount calls with NO shareholder language by more than noise. Management language predicts WHETHER a company acts (AUC above); it does not, by itself, predict the re-rating -- the market prices stated intent quickly. Use it to confirm a set-up, not as a return signal.

## Stated action size (buyback / tender as % of market cap at the call), all calls

| size | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| <2% of mcap | 493 | 0.282 | -4.9% | -5.9% |
| 2-5% | 375 | 0.450 | -4.8% | -6.8% |
| 5-10% | 400 | 0.494 | -5.4% | -5.4% |
| >=10% | 692 | 0.539 | -7.5% | -9.0% |

Companies that ACTED returned -0.073 vs -0.058 for those that did not (mean 6-month excess vs SPY): in this sample the action itself did not re-rate value names on its own. The language is a strong predictor of ACTION and a weak stand-alone predictor of returns -- use it to corroborate a discount/governance set-up (does management intend to act?), not as a return signal by itself.

## Forward 6-month excess return vs SPY by rule-score quintile (all calls)

| quintile | calls | mean | median | share > +25% |
|---|---|---|---|---|
| Q1 | 1390 | -8.8% | -10.9% | 9.7% |
| Q2 | 1390 | -6.2% | -9.3% | 11.7% |
| Q3 | 1391 | -5.1% | -7.1% | 10.3% |
| Q4 | 1390 | -5.2% | -7.1% | 10.1% |
| Q5 (highest) | 1391 | -5.7% | -7.6% | 9.8% |

## Fitted weights (standardised, baseline + language, all labelled data)

| feature | weight |
|---|---|
| BUYBACK | +0.418 |
| DIVIDEND_RETURN | +0.174 |
| prep_act | +0.132 |
| size_pct | +0.126 |
| VALUE_GAP | +0.102 |
| press_ratio | +0.088 |
| ceo_act | -0.084 |
| novelty | -0.079 |
| past_div_up | -0.071 |
| STRATEGIC_REVIEW | +0.069 |
| past_sh_chg | +0.068 |
| both_act | +0.065 |
| cfo_act | +0.064 |
| escalation | -0.054 |
| MONETIZE | +0.053 |
| deep | -0.049 |
| firming | -0.048 |
| TENDER | +0.039 |
| COST | -0.036 |
| ANTICIPATION | +0.028 |
| neg_total | -0.022 |
| deep_x_gap | -0.021 |
| qa_act | +0.020 |
| GOVERNANCE | +0.015 |
| a_evade | -0.015 |
| DELEVER | +0.013 |
| a_commit | -0.007 |
| deep_x_act | -0.003 |
