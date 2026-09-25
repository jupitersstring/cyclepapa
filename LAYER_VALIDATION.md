# Ownership and distress layers — event study (2026-09-25)

Excess return vs SPY over the next 63 / 126 trading days, from the first close after the filing date; events 2021-01-01 to 200 days ago; 2577 current US book names. Control = the same names on random dates. t = difference vs control / standard error. **Survivorship caveat:** today's names only — delisted / bankrupt companies are missing, so distress returns are flattered.

| Event | n | 63d mean | 126d mean | 126d median | 126d hit | 126d vs control | t | Verdict |
|---|---|---|---|---|---|---|---|---|
| insider selling >= $1M in 30d | 5901 | -3.1% | -6.6% | -8.7% | 36% | -1.5% | -1.6 | no measured edge |
| insider cluster buy | 2291 | -1.3% | -5.2% | -8.3% | 37% | -0.2% | -0.1 | no measured edge |
| 8-K 3.01 delisting notice | 1868 | -0.3% | -8.4% | -30.9% | 28% | -3.4% | -1.3 | no measured edge |
| new 13D | 1762 | -2.6% | -6.0% | -14.0% | 33% | -1.0% | -0.6 | no measured edge |
| late filing (NT 10-K/10-Q) | 1550 | -5.9% | -9.2% | -22.4% | 28% | -4.2% | -1.8 | no measured edge |
| CEO/CFO open-market buy >= $100k | 1272 | +0.5% | -4.2% | -8.3% | 38% | +0.8% | 0.6 | no measured edge |
| 13D stake cut | 935 | +1.9% | -0.2% | -7.5% | 41% | +4.8% | 2.1 | weak positive (not adopted: multiple testing) |
| 13D stake added | 518 | -4.4% | -6.3% | -12.8% | 35% | -1.3% | -0.5 | no measured edge |
| reverse split | 455 | -13.9% | -25.7% | -45.7% | 21% | -20.7% | -4.8 | NEGATIVE (caution signal) |
| 8-K 4.02 non-reliance | 324 | -5.5% | -11.5% | -15.5% | 31% | -6.5% | -2.1 | NEGATIVE (caution signal) |
| 13G -> 13D switch | 257 | -2.7% | -9.8% | -13.9% | 32% | -4.8% | -1.5 | no measured edge |
| activist new 13D / switch | 135 | -1.9% | -4.4% | -11.2% | 38% | +0.6% | 0.2 | no measured edge |
| 8-K 2.06 impairment | 124 | +0.1% | +1.1% | -7.5% | 32% | +6.1% | 0.9 | no measured edge |
| 8-K 1.03 bankruptcy | 21 | +24.4% | +36.3% | +0.7% | 52% | +41.3% | 1.8 | too few events |

Control (random dates, same names): 126d mean -5.0%, median -8.6%, hit 36% (n=3562).

**How the books use this:** a POSITIVE edge (t >= 3, because ~14 event types are tested at once) may support a position; a NEGATIVE one (t <= -2 -- a caution is cheap to act on) becomes a caution flag and a sizing cut; everything else is shown for information only (like congressional trades). Bankruptcy and auditor going-concern doubt cut sizing and remove book floors on prudence, not on a measured edge (bankrupt names that delisted are missing from this sample, which is why the bankruptcy row looks positive).

**Read-across:** in this universe (heavy in small, cheap, stressed names -- the control itself is -5% vs SPY over 126 days) ownership filings alone do not predict returns. They are context for a thesis -- who can force the value out, who is under water -- not a signal by themselves.
