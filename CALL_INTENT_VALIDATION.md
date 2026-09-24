# Earnings-call intent -- out-of-time validation

Generated 2026-09-24 by `call_intent_model.py`. Calls analysed: 12937 (1384 names). Labelled: 7095; train < 2025-06-01: 3636, test >= 2025-06-01: 3459. Test base rate (ACTED): 30.6%.

ACTED = share count down >= 2% or dividends up >= 25%/initiated over the next two fiscal quarters, or a dated action 8-K within 183 days of the call.

## Does the language predict action? (test set, AUC)

| model | AUC |
|---|---|
| interpretable rule score (no fitting) | 0.654 |
| logistic, language features only | 0.674 |
| baseline: past behaviour only (share-count + dividend trend) | 0.601 |
| baseline + language | 0.671 |
| rule score, companies NOT already shrinking share count | 0.603 |

Top decile hit-rate (test): rule 53.6% vs base 30.6% (lift 1.75x); baseline+language 57.4% (lift 1.88x).

## Lift by linguistic family (calls with family score >= 0.8, all labelled)

| family | calls | lift vs base |
|---|---|---|
| TENDER | 25 | 2.17x |
| DIVIDEND_RETURN | 913 | 1.60x |
| BUYBACK | 2609 | 1.60x |
| VALUE_GAP | 635 | 1.44x |
| GOVERNANCE | 139 | 1.38x |
| novelty | 1612 | 1.20x |
| STRATEGIC_REVIEW | 242 | 1.14x |
| MONETIZE | 1577 | 1.13x |
| ANTICIPATION | 2007 | 1.03x |
| DELEVER | 835 | 1.03x |
| COST | 1828 | 1.02x |

## Out of time: model probability quintile -> what happened next (test set)

| quintile | calls | ACTED rate | mean 6m excess | median 6m excess |
|---|---|---|---|---|
| Q1 | 697 | 15% | -3.6% | -7.2% |
| Q2 | 697 | 17% | -7.5% | -8.8% |
| Q3 | 697 | 21% | -5.6% | -6.3% |
| Q4 | 697 | 35% | -3.9% | -3.4% |
| Q5 (highest) | 698 | 50% | -3.2% | -4.2% |

Companies that ACTED returned -0.073 vs -0.057 for those that did not (mean 6-month excess vs SPY): in this sample the action itself did not re-rate value names on its own. The language is a strong predictor of ACTION and a weak stand-alone predictor of returns -- use it to corroborate a discount/governance set-up (does management intend to act?), not as a return signal by itself.

## Forward 6-month excess return vs SPY by rule-score quintile (all calls)

| quintile | calls | mean | median | share > +25% |
|---|---|---|---|---|
| Q1 | 1422 | -8.3% | -10.6% | 9.7% |
| Q2 | 1422 | -6.3% | -9.2% | 11.4% |
| Q3 | 1423 | -5.1% | -7.1% | 10.1% |
| Q4 | 1422 | -5.2% | -6.9% | 9.8% |
| Q5 (highest) | 1423 | -5.7% | -7.5% | 9.4% |

## Fitted weights (standardised, baseline + language, all labelled data)

| feature | weight |
|---|---|
| BUYBACK | +0.592 |
| DIVIDEND_RETURN | +0.188 |
| novelty | -0.142 |
| press_ratio | +0.084 |
| STRATEGIC_REVIEW | +0.081 |
| VALUE_GAP | +0.080 |
| past_div_up | -0.079 |
| MONETIZE | +0.069 |
| TENDER | +0.058 |
| past_sh_chg | +0.051 |
| ANTICIPATION | +0.031 |
| neg_total | -0.028 |
| GOVERNANCE | +0.022 |
| a_evade | -0.017 |
| COST | -0.009 |
| a_commit | -0.005 |
| DELEVER | -0.003 |
