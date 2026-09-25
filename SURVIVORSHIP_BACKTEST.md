# Survivorship-free backtest (2026-09-25)

8 six-month windows (2024-05-20 to 2026-08-20), US-exchange common stocks as they stood on each formation date — including every name that later failed, delisted or was acquired (FMP end-of-day bulk files + statements filed before the date). Return = 6-month total return minus SPY. 'Survivors only' drops the names that delisted in the window: the gap between the two columns is the survivorship bias earlier tests carried.

| Bucket | n | Mean (everyone) | Median | Hit | t vs all | Mean (survivors only) | Bias | Delisted in window | Mean if no-price names = -100% |
|---|---|---|---|---|---|---|---|---|---|
| all | 40229 | -1.6% | -7.2% | 37% | — | -1.6% | -0.0% | 4.2% | -1.6% |
| > 3x book | 12447 | -4.2% | -9.2% | 37% | -4.1 | -4.3% | -0.1% | 3.4% | -4.2% |
| 1-3x book | 14595 | -0.7% | -6.2% | 38% | 1.7 | -0.7% | -0.1% | 3.8% | -0.7% |
| 0.7-1.0x book | 4239 | +2.5% | -3.8% | 42% | 4.1 | +2.4% | -0.1% | 4.8% | +2.5% |
| deep value 0.1-0.7x book | 5518 | +2.5% | -6.9% | 33% | 3.8 | +2.0% | -0.5% | 4.6% | +2.5% |
| deep value, no red flag | 4647 | +2.5% | -6.3% | 33% | 3.9 | +2.0% | -0.5% | 3.7% | +2.5% |
| deep value + red flag | 871 | +2.6% | -16.1% | 32% | 1.1 | +2.5% | -0.1% | 9.2% | +2.6% |
| deep value + reverse split | 232 | -14.4% | -30.7% | 24% | -1.9 | -11.8% | +2.6% | 9.9% | -14.4% |
| deep value + delisting notice | 546 | +11.5% | -15.6% | 35% | 2.4 | +10.2% | -1.4% | 9.7% | +11.5% |
| deep value + late filing | 367 | -3.4% | -15.1% | 32% | -0.4 | -3.9% | -0.5% | 8.7% | -3.4% |
| deep value + non-reliance | 93 | -10.1% | -9.2% | 41% | -1.7 | -5.9% | +4.2% | 9.7% | -10.1% |
| P/B < 0.1 (data or wipe-out) | 268 | -10.7% | -11.1% | 15% | -2.5 | -9.7% | +0.9% | 11.6% | -10.7% |
| negative equity | 3162 | -7.4% | -15.1% | 33% | -4.2 | -6.4% | +1.0% | 6.8% | -7.4% |

**Reading it.** Means are skewed by a minority of large winners (medians are negative almost everywhere in a market that SPY led). Windows overlap and the same names recur, so t-stats overstate precision somewhat -- treat |t| < 3 as suggestive. Delisted names nearly all have a last traded price in FMP (acquired or faded before delisting), which is why the survivorship bias here is small; bankruptcies where trading stopped abruptly would show in the '-100%' column.

Windows: 2024-05-20→2024-11-18: 4879 names, 171 delisted (last price used), 0 with no price; 2024-08-19→2025-02-18: 5125 names, 204 delisted (last price used), 0 with no price; 2024-11-19→2025-05-20: 5111 names, 206 delisted (last price used), 0 with no price; 2025-02-19→2025-08-20: 5128 names, 225 delisted (last price used), 0 with no price; 2025-05-20→2025-11-18: 5021 names, 185 delisted (last price used), 0 with no price; 2025-08-19→2026-02-17: 5033 names, 212 delisted (last price used), 0 with no price; 2025-11-19→2026-05-20: 5028 names, 233 delisted (last price used), 0 with no price; 2026-02-19→2026-08-20: 4908 names, 238 delisted (last price used), 0 with no price
