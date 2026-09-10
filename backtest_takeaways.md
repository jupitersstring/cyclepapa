# Backtest takeaways — 2026-06-24

## Data

72 historical event-anchored observations from 2022 onward, drawn
from `data/investegate/*.json` (RNS-flagged wind-down, strategic
review, return-of-capital filings) joined to daily price parquets.

Three event classes:

| Catalyst class            | Events | Median 12m price return |
|---------------------------|-------:|------------------------:|
| `RETURN_OF_CAPITAL_LIVE`  | 46     | +0.5%                   |
| `STRATEGIC_REVIEW`        | 13     | +3.6%                   |
| `WIND_DOWN_COMMITTED`     | 13     | -62.2%                  |

## Why the wind-down number is misleading

A managed wind-down deliberately runs the share count to zero by
paying cash distributions back to shareholders. The share price
declines to nil by construction; the *total return* equals the
cumulative cash returns + residual NAV. Our title-based parser
recovered zero capital-return amounts because RNS titles for these
events generally say "Capital distribution by way of B-share scheme"
or "Confirmation of capital reduction" without the per-share amount.
A fuller backtest would parse the announcement BODIES (we already
fetch them for PDMR / TR-1) — adding that as a future iteration.

**Conclusion: do not use the -62% number to calibrate
WIND_DOWN_COMMITTED probabilities.** It captures only the price
denominator collapse, not the actual return to a holder.

## What we DID learn (qualitative)

### 1. Strategic review names work out better than RoC names on price
Strategic review has higher median 12m return (+3.6%) than
return-of-capital (+0.5%). This is consistent with the screener's
prior: STRATEGIC_REVIEW has lower base probability (0.50) and longer
duration (15m) than RoC (0.70 / 18m). A review *opens* the optionality;
a return-of-capital announcement often crystallises a fraction of it
immediately, so subsequent price movement is muted (the easy money has
been priced in).

### 2. Variance is enormous in all classes
The p25/p75 spread is much wider than the median for every class. The
priors are point estimates; reality is bimodal — successful workouts
and slow-grinder failures sit in the same bucket. A future version
should fit a distribution per class (mean + sigma) rather than a
single probability.

### 3. Recency bias on the sample
The 2022-2026 window includes the post-pandemic rate cycle and the
2024-2026 UK CEF activist wave. Calibrations from this period
overstate event probability vs the longer history. Backtest needs
extension to 2015-onward before it's a robust regime-average.

### 4. The signal value is in the differentials, not the averages
Even with the noisy data, names that scored high on resolution_score
at the event date subsequently outperformed peers in the same class.
That's the screener's actual edge: not the absolute prediction, but
the relative ranking within an event class.

## Parameter calibration

**No parameters were updated based on this backtest.** Per the brief,
the takeaways above are informational only.

If we were to calibrate, the indicative shifts would be:

- WIND_DOWN_COMMITTED: priors LOOK fine on the qualitative tape (Saba
  campaigns work) but the price-return number is too noisy to
  calibrate to. WAIT for the total-return parser before touching.
- STRATEGIC_REVIEW: priors look slightly conservative; +3.6% median
  is consistent with the existing 0.50 × discount expected return.
- RETURN_OF_CAPITAL_LIVE: priors look slightly OPTIMISTIC; +0.5%
  median suggests P=0.70 may be high for the residual return once a
  partial return-of-capital has been announced. Re-run with body
  parsing before adjusting.

## Recommended follow-ups

1. Parse RNS BODIES for capital-return amounts (already cached for
   PDMR / TR-1; same plumbing).
2. Extend window to 2015 for regime-average priors.
3. Cluster wind-down events by *NAV-quality* (PE wind-downs vs
   renewables wind-downs behave very differently); current
   single-bucket calibration averages too aggressively.
4. Add "did the catalyst actually crystallise" yes/no labels by hand
   to a sample of 30 events — converts the noisy continuous return
   into a binary outcome that's much cleaner to calibrate against.
