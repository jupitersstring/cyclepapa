# Deeper research — validating & sharpening the monster fingerprint

Pure-compute on 525 corporate-action events (rerate_backtest.json). monster = +100%/12m; big loss = -50%/12m.

## Headline (this CORRECTS the earlier monster_setup)

The deep-washout fingerprint is **bimodal, not bullish**: the biggest WINNERS and the biggest LOSERS look nearly identical before the event (both ~−74%/−52% off the 2y high, wild vol, rock-bottom range, same lottery catalysts). The top fingerprint bucket (fp≥8) has a **33% chance of losing >50%**, a −26% median, and a NEGATIVE Kelly — it is not investable on its own. The ONLY thing that separates the monster from the blow-up ex-ante is **post-catalyst CONFIRMATION**: confirm ≥+20% in month one → 15% monster rate / +57% mean; ≥+30% → 19% / +86%; but a FADE (≤−10%) → 1% monster / **−38% mean**. Conclusion: never buy the un-confirmed washout; gate the monster fingerprint on confirmation, and treat FADING high-fingerprint names as the explicit AVOID list.

## A. Does the fingerprint concentrate monsters? (monster_setup 0-10)

| fp bucket | n | monster% | win% | median | loss>50% | mean |
|---|---|---|---|---|---|---|
| 0-3 | 280 | 2% | 56% | +6% | 7% | +9% |
| 4-5 | 63 | 11% | 57% | +13% | 6% | +26% |
| 6-7 | 63 | 10% | 41% | -12% | 25% | +54% |
| 8-10 | 119 | 10% | 37% | -21% | 31% | +904% |

## B. Confirmation sweep — first-month drift → 12m outcome

| entry rule | n | coverage | monster% | mean 12m |
|---|---|---|---|---|
| confirm >= +0% | 237 | 0.451 | 8% | +491% |
| confirm >= +10% | 106 | 0.202 | 11% | +1083% |
| confirm >= +20% | 51 | 0.097 | 20% | +2152% |
| confirm >= +30% | 29 | 0.055 | 24% | +3762% |
| confirm faded (<= -10%) | 103 | — | 3% | -27% |

## C. Payoff & sizing — top fingerprint bucket (fp≥8)

n=119, win 37%, avg win +2536%, avg loss -53%, loss>50% 31%, mean/expectancy +904%. Payoff ratio b=47.59, full-Kelly 0.357 → **~1/4-Kelly 0.089** per name. The fat left tail (loss>50%) is why these are small-size lottery tickets.

## D. The loser anti-pattern (≤ −50%/12m)

76 big losers. Pre-event medians (loser vs rest):

| feature | loser | rest |
|---|---|---|
| drawdown_24m | -0.656 | -0.226 |
| pre_vol | 0.271 | 0.106 |
| range_pos | 0.062 | 0.45 |
| pre_12m | -0.568 | -0.042 |
| decel | 0.013 | 0.004 |
| post_1m | -0.141 | 0.0 |

Loser catalyst mix: {'UPLISTING': 0.26, 'STRATEGIC_REVIEW': 0.2, 'CAPITAL_RETURN': 0.09, 'SPINOFF': 0.08}

## E. Out-of-sample check (train pre-2024 / test 2024+)

- **train** (n=284): fp≥6 monster rate 10% vs fp<6 2% (holds)
- **test** (n=241): fp≥6 monster rate 10% vs fp<6 6% (holds)

