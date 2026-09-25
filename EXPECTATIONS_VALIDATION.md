# Expectations layer — validation (2026-09-25)

## 1. Analyst rating changes — event study

Excess return vs SPY from the first close after the rating change; control = the same names on random dates; current names only (survivorship caveat). Positive edge needs t >= 3 (several tests at once); a caution needs t <= -2.

| Event | n | 63d mean | 126d mean | 126d median | 126d hit | 126d vs control | t | Verdict |
|---|---|---|---|---|---|---|---|---|
| analyst downgrade | 8233 | -2.6% | -4.5% | -7.1% | 37% | -0.8% | -0.9 | no measured edge |
| analyst upgrade | 7294 | -1.2% | -3.0% | -5.4% | 40% | +0.7% | 0.9 | no measured edge |
| downgrade to sell | 1616 | -1.7% | -2.6% | -6.3% | 39% | +1.1% | 0.8 | no measured edge |
| upgrade from sell | 1385 | -0.3% | -3.6% | -5.7% | 40% | +0.1% | 0.1 | no measured edge |

## 2. Short interest — survivorship-free cross-section

Every liquid (>= $250k/day) US-exchange stock with FINRA short interest on each formation date, incl. names that later delisted (last price used). 6-month return minus SPY; t vs the whole liquid shorted universe.

| Bucket | n | Mean | Median | Hit | vs all | t |
|---|---|---|---|---|---|---|
| all (liquid, shorted) | 37075 | -4.7% | -8.3% | 37% | — | — |
| short interest up >= 50% (and >= 3 days) | 262 | -6.2% | -6.9% | 36% | -1.5% | -0.5 |
| short covering: down >= 33% | 80 | -14.3% | -11.4% | 38% | -9.6% | -1.6 |
| top decile days-to-cover | 3714 | +0.0% | -7.9% | 40% | +4.8% | 4.2 |
| days-to-cover >= 10 | 2571 | -0.1% | -8.8% | 39% | +4.6% | 3.1 |

## Read-across

- Analyst rating changes have not predicted returns here in either direction (|t| < 1): coverage and targets are shown as context -- how neglected a name is and what the street already assumes -- not scored.
- Heavily shorted stocks (top decile days-to-cover) OUT-performed the liquid universe over 2024-26 (t above 3). That is the opposite of the long-run academic evidence (high short interest predicts LOW returns) and most likely reflects a squeeze-prone regime; it is reported, not scored, and it is a risk flag for anyone short -- not a reason to buy.
- Everything here is shown on the 'Priced In' tab and next to each name; none of it changes a rank or a size until it earns it on a longer, regime-spanning sample.
