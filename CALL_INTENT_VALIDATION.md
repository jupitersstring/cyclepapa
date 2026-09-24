# Earnings-call intent -- out-of-time validation

Generated 2026-09-24 by `call_intent_model.py`. Calls analysed: 12653 (1353 names). Labelled: 6938; train < 2025-06-01: 3553, test >= 2025-06-01: 3385. Test base rate (ACTED): 30.6%.

ACTED = share count down >= 2% or dividends up >= 25%/initiated over the next two fiscal quarters, or a dated action 8-K within 183 days of the call.

## Does the language predict action? (test set, AUC)

| model | AUC |
|---|---|
| interpretable rule score (no fitting) | 0.653 |
| logistic, language features only | 0.669 |
| baseline: past behaviour only (share-count + dividend trend) | 0.598 |
| baseline + language | 0.667 |
| rule score, companies NOT already shrinking share count | 0.601 |

Top decile hit-rate (test): rule 53.3% vs base 30.6% (lift 1.74x); baseline+language 56.2% (lift 1.84x).

## Lift by linguistic family (calls with family score >= 0.8, all labelled)

| family | calls | lift vs base |
|---|---|---|
| TENDER | 25 | 2.17x |
| DIVIDEND_RETURN | 875 | 1.61x |
| BUYBACK | 2553 | 1.60x |
| VALUE_GAP | 603 | 1.46x |
| GOVERNANCE | 138 | 1.39x |
| novelty | 1575 | 1.22x |
| MONETIZE | 1547 | 1.14x |
| STRATEGIC_REVIEW | 239 | 1.11x |
| DELEVER | 900 | 1.05x |
| ANTICIPATION | 1976 | 1.03x |
| COST | 1793 | 1.01x |

## Out of time: model probability quintile -> what happened next (test set)

| quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 680 | 15% | -4.4% | -7.8% |
| Q2 | 681 | 18% | -7.4% | -8.9% |
| Q3 | 680 | 21% | -5.4% | -5.9% |
| Q4 | 681 | 35% | -4.1% | -3.3% |
| Q5 (highest) | 681 | 50% | -3.3% | -4.0% |

Companies that ACTED returned -0.073 vs -0.058 for those that did not (mean 6-month excess vs SPY): in this sample the action itself did not re-rate value names on its own. The language is a strong predictor of ACTION and a weak stand-alone predictor of returns -- use it to corroborate a discount/governance set-up (does management intend to act?), not as a return signal by itself.

## Forward 6-month excess return vs SPY by rule-score quintile (all calls)

| quintile | calls | mean | median | share > +25% |
|---|---|---|---|---|
| Q1 | 1389 | -8.8% | -11.1% | 9.6% |
| Q2 | 1389 | -6.1% | -9.3% | 11.7% |
| Q3 | 1389 | -5.1% | -7.1% | 10.2% |
| Q4 | 1389 | -5.2% | -7.2% | 10.2% |
| Q5 (highest) | 1390 | -5.8% | -7.6% | 9.6% |

## Fitted weights (standardised, baseline + language, all labelled data)

| feature | weight |
|---|---|
| BUYBACK | +0.589 |
| DIVIDEND_RETURN | +0.182 |
| novelty | -0.129 |
| VALUE_GAP | +0.085 |
| press_ratio | +0.081 |
| MONETIZE | +0.076 |
| past_div_up | -0.072 |
| STRATEGIC_REVIEW | +0.065 |
| past_sh_chg | +0.056 |
| TENDER | +0.056 |
| ANTICIPATION | +0.030 |
| GOVERNANCE | +0.025 |
| COST | -0.024 |
| neg_total | -0.019 |
| DELEVER | +0.018 |
| a_evade | -0.014 |
| a_commit | -0.012 |
