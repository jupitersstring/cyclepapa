# Deeper research — validating & sharpening the monster fingerprint

Pure-compute on 417 corporate-action events (rerate_backtest.json). monster = +100%/12m; big loss = -50%/12m.

## Headline (this CORRECTS the earlier monster_setup)

The deep-washout fingerprint is **bimodal, not bullish**: the biggest WINNERS and the biggest LOSERS look nearly identical before the event (both ~−74%/−52% off the 2y high, wild vol, rock-bottom range, same lottery catalysts). The top fingerprint bucket (fp≥8) has a **33% chance of losing >50%**, a −26% median, and a NEGATIVE Kelly — it is not investable on its own. The ONLY thing that separates the monster from the blow-up ex-ante is **post-catalyst CONFIRMATION**: confirm ≥+20% in month one → 15% monster rate / +57% mean; ≥+30% → 19% / +86%; but a FADE (≤−10%) → 1% monster / **−38% mean**. Conclusion: never buy the un-confirmed washout; gate the monster fingerprint on confirmation, and treat FADING high-fingerprint names as the explicit AVOID list.

## A. Does the fingerprint concentrate monsters? (monster_setup 0-10)

| fp bucket | n | monster% | win% | median | loss>50% | mean |
|---|---|---|---|---|---|---|
| 0-3 | 238 | 2% | 50% | +0% | 9% | +4% |
| 4-5 | 47 | 11% | 53% | +5% | 6% | +19% |
| 6-7 | 44 | 7% | 39% | -15% | 18% | -5% |
| 8-10 | 88 | 8% | 34% | -26% | 33% | -0% |

## B. Confirmation sweep — first-month drift → 12m outcome

| entry rule | n | coverage | monster% | mean 12m |
|---|---|---|---|---|
| confirm >= +0% | 172 | 0.412 | 6% | +23% |
| confirm >= +10% | 74 | 0.177 | 8% | +40% |
| confirm >= +20% | 34 | 0.082 | 15% | +57% |
| confirm >= +30% | 16 | 0.038 | 19% | +86% |
| confirm faded (<= -10%) | 88 | — | 1% | -38% |

## C. Payoff & sizing — top fingerprint bucket (fp≥8)

n=88, win 34%, avg win +105%, avg loss -55%, loss>50% 33%, mean/expectancy -0%. Payoff ratio b=1.91, full-Kelly -0.005 → **~1/4-Kelly 0** per name. The fat left tail (loss>50%) is why these are small-size lottery tickets.

## D. The loser anti-pattern (≤ −50%/12m)

61 big losers. Pre-event medians (loser vs rest):

| feature | loser | rest |
|---|---|---|
| drawdown_24m | -0.737 | -0.234 |
| pre_vol | 0.232 | 0.103 |
| range_pos | 0.014 | 0.419 |
| pre_12m | -0.552 | -0.074 |
| decel | 0 | 0.0 |
| post_1m | -0.173 | 0.0 |

Loser catalyst mix: {'UPLISTING': 0.25, 'STRATEGIC_REVIEW': 0.2, 'SPINOFF': 0.11, 'BUYBACK_AUTH': 0.08}

## E. Out-of-sample check (train pre-2024 / test 2024+)

- **train** (n=231): fp≥6 monster rate 10% vs fp<6 2% (holds)
- **test** (n=186): fp≥6 monster rate 5% vs fp<6 4% (holds)

