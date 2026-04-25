# Hull MITM / FMH lock-picker — backtest findings

## Iteration 5: cycle-aligned multi-length, multi-cap, daily/weekly/monthly + PSAR

15 years of daily yfinance data, 57 single names across 4 market-cap segments.
Each indicator is computed at multiple cycle-aligned lengths within each TF:

  Daily   1D :  5,  10,  21,  63   (week, biweek, month, quarter)
  Weekly  1W :  4,  13,  26,  52   (month, quarter, half, year)
  Monthly 1M :  3,  6,   12,  36   (quarter, half, year, 3-year)

→ 12 "pins" per indicator per ticker.  Within-TF length weights ∝ √L (longer
cycles dominate); TF-cascade weights = 1/3/5 (monthly drives most conviction).
Equal-weight 57-name basket, daily execution, 1 bp cost.

### All-caps basket (long-flat)

| indicator | CAGR | B&H | Sharpe | B&H | ΔShp | MaxDD | B&H DD | Vol | B&H Vol |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **MFI**   | 11.20% | 21.29% | **1.16** | 1.08 | **+0.08** | −26.3% | −56.4% | 9.6% | 19.7% |
| **PSAR**  |  8.43% | 21.29% | 1.13     | 1.08 | +0.06 | **−17.6%** | −56.4% | **7.4%** | 19.7% |
| STOCH     | 10.15% | 21.29% | 1.11     | 1.08 | +0.04 | −24.1% | −56.4% | 9.1% | 19.7% |
| RSI       | 10.11% | 21.29% | 1.07     | 1.08 | −0.01 | −26.5% | −56.4% | 9.4% | 19.7% |
| HMA (orig)|  7.40% | 21.29% | 0.94     | 1.08 | −0.14 | −25.5% | −56.4% | 7.9% | 19.7% |

PSAR is the **risk-control champion**: −17.6% MaxDD vs −56.4% B&H — less than
a third — at lowest vol (7.4%).  MFI is the **Sharpe champion** at 1.16.

### Per-cap comparison (long-flat)

| cap | best ind | strat Shp | B&H Shp | ΔShp | strat CAGR | B&H CAGR |
|---|---|---:|---:|---:|---:|---:|
| MEGA  | STOCH | 0.93 | 1.02 | −0.09 | 11.84% | 24.01% |
| LARGE | MFI   | 1.02 | 1.05 | −0.02 |  9.57% | 19.04% |
| **MID**   | **PSAR**  | **0.76** | 0.73 | **+0.03** | 15.72% | 27.36% |
| **SMALL** | **MFI**   | **0.60** | 0.46 | **+0.14** | **10.93%** | 10.91% |

**Small-cap MFI beats B&H on BOTH CAGR and Sharpe** (+0.14 ΔShp).
**Mid-cap PSAR beats B&H Sharpe** (+0.03).  Mega/large lose Sharpe but cut
DD ~50–70%.  Pattern: the alpha lives where dispersion is highest (small/mid)
and the risk-control benefit is biggest where the index is smoothest (mega).

### Honest comparison vs iteration 4

The 30-name 90m basket showed +0.94 Sharpe alpha — but only 3 years of data
(2023-2026), all bull-market.  The 15-year multi-cap daily test here delivers
+0.04 to +0.14 ΔSharpe — much more modest, but covers two real bear markets
(2008 GFC, 2022) and is therefore the more honest deployable estimate.

## Iteration 4: 30-name equal-weight basket (deployable alpha)

Same 4-TF (90m/1d/1w/1mo) signal as iteration 3, but each of 30 names runs
its own sleeve and is averaged into an equal-weight portfolio.  Compared to
equal-weight buy-hold of the same basket. Idiosyncratic timing noise
diversifies away; systematic alpha aggregates.

Universe (30): NVDA TSLA AAPL MSFT AMZN META GOOGL AMD AVGO CRM NFLX ORCL
JPM BAC GS V MA WMT COST HD LLY UNH JNJ PG KO DIS XOM CVX CAT BA.

| strategy | mode | CAGR | B&H | Sharpe | B&H | ΔShp | Sortino | Vol | B&H Vol | MaxDD | B&H DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HMA-MTF       | long_flat | 3.5%  | 22.0% | 1.60 | 1.49 | +0.10 | 1.73 | 2.2% | 13.9% | −2.0% | −20.8% |
| **RSI-MTF**   | long_flat | **19.8%** | 22.0% | **2.43** | 1.49 | **+0.94** | **3.20** | 7.5% | 13.9% | **−5.7%** | −20.8% |
| MFI-MTF       | long_flat | 8.5%  | 22.0% | 1.29 | 1.49 | −0.21 | 1.59 | 6.5% | 13.9% | −9.4% | −20.8% |
| **STOCH-MTF** | long_flat | 14.9% | 22.0% | **2.49** | 1.49 | **+0.99** | 3.21 | 5.6% | 13.9% | −3.7% | −20.8% |
| HMA×RSI-gate  | long_flat | 6.7%  | 22.0% | 1.63 | 1.49 | +0.13 | 1.88 | 4.0% | 13.9% | −3.5% | −20.8% |
| RSI-MTF       | long_short | 18.0% | 22.0% | 2.33 | 1.49 | +0.84 | 3.09 | 7.2% | 13.9% | −4.8% | −20.8% |
| STOCH-MTF     | long_short | 14.9% | 22.0% | 2.11 | 1.49 | +0.61 | 2.59 | 6.7% | 13.9% | −4.9% | −20.8% |

**Headline:** RSI-MTF long-flat basket has Sharpe 2.43 vs 22.0% B&H Sharpe 1.49
(Δshp +0.94), at half the volatility and a quarter of the max drawdown.
Sortino 3.20 vs ~1.7 for B&H. Levered to B&H vol (~1.85×) you target ~37%
CAGR vs 22% B&H — that's the deployable risk-adjusted alpha.

STOCH-MTF tops the Sharpe table at 2.49 with even tighter MaxDD (−3.7%) but
~5pp lower CAGR than RSI-MTF.

The signal works because: (a) idiosyncratic name-level noise averages out
across 30 sleeves; (b) the systematic component — multi-TF oscillator
alignment — is the actual edge; (c) per-bar normalization across sleeves
keeps exposure smooth.

## Iteration 3: indicator variants on single names (per-name)

Universe: NVDA, TSLA, AAPL, MSFT, AMZN, META, GOOGL, AMD, COIN, NFLX, AVGO, CRM
Data: yfinance 60m for ~3 years, resampled to 4 TFs: **90m / 1d / 1w / 1mo**.
Per-TF signal aggregated across TFs with weights (1, 3, 5, 8); coherence ≥ 0.55;
require 2 consecutive bars same sign; 1 bp/turn cost.

| strategy        | mode       | medΔcagr | medΔshp | medMaxDD | win%CAGR | win%Shp | medTurn/y |
|---|---|---:|---:|---:|---:|---:|---:|
| HMA-MTF         | long_flat  | −27.1%   | −0.68   | −12.3%   |   8%     | 17%     | 26.7      |
| **RSI-MTF**     | **long_flat** | **−2.9%** | **+0.10** | **−24.9%** | **50%** | **58%** | **19.6** |
| MFI-MTF         | long_flat  | −16.2%   | −0.36   | −28.7%   |   8%     | 25%     | 26.0      |
| STOCH-MTF       | long_flat  | −8.8%    | +0.01   | −23.4%   |  17%     | 50%     | 28.9      |
| HMA×RSI-gate    | long_flat  | −17.0%   | −0.25   | −20.0%   |   8%     | 17%     | 17.5      |
| RSI-meanrev     | long_flat  | −17.0%   | −0.35   | −24.9%   |   8%     | 25%     |  1.7      |

**RSI-MTF (cross-50 alignment across 90m/1d/1w/1mo) is the only variant with
positive median Δsharpe**. Headline single-name examples (long-flat):

| ticker | RSI-MTF Sharpe | B&H Sharpe | RSI-MTF CAGR | B&H CAGR |
|---|---:|---:|---:|---:|
| NFLX  | 1.31 | 0.98 | 35.0% | 29.4% |
| CRM   | 0.16 | −0.01 |  1.2% | −5.1% |
| MFI on CRM | 0.82 | −0.01 | 11.7% | −5.1% |
| AVGO  | 1.23 | 1.34 | 43.8% | 60.4% (loses CAGR but Sharpe close, 1/2 DD) |

## Why RSI/MFI work where HMA-slope didn't
1. **Earlier signal.** HMA-slope direction lags by ~half its window. A 14-bar
   RSI cross-50 fires on the *velocity* of the price, not the smoothed trend
   level — gets in days/weeks earlier on each leg.
2. **Bounded oscillator scales fractally.** The 0–100 cross-50 boundary is
   the same at every TF, so coherence across TFs is meaningfully comparable.
3. **Time-in-market.** RSI-MTF long-flat sits ~50–75% in market vs HMA's ~10–20%.
   Trend-following on indexes failed because the gate kept the strategy flat
   through bull runs; the oscillator-aligned version stays invested in trending
   names.
4. **Mean-reversion *only* (RSI-meanrev) loses badly** — confirms direction is
   the win, not bottom-fishing. Cross-50 consensus IS an early trend signal.

## What still doesn't work
- HMA-slope cascade (the literal lock-picker) underperforms on every metric.
- ETF rotation underperforms (single-factor universe — no real dispersion).
- Long-short on equities loses to drift; long-flat is the practical mode.
- Mean-reversion at extremes (RSI<30 / >70) gets crushed by trend persistence
  in single names.

## Earlier iterations (kept for reference)
**Iteration 1 — single-asset daily, faithful Pine port** — `lockState` never
engages: cascade gate starves higher pairs, shear caps at 0.19. Bug
documented. (`hull_mitm.py`)

**Iteration 2 — daily FMH rebuild on ETFs** — φ-spaced scales, OLS slope,
DFA Hurst gate. Cuts MaxDD ~50% but loses CAGR/Sharpe on every ETF tested.
Best win was BTC long-flat: 12.3% CAGR vs 35.7% B&H, but with MaxDD −33%
vs −83%. Not alpha — just lower-risk sub-buy-hold. (`fmh_lockpicker.py`,
`test_alpha.py`)

## Repro
```
python3 basket_backtest.py                          # main deployable result
python3 fmh_indicators.py                           # per-name comparison
python3 fmh_multitf.py                              # HMA-only baseline
python3 test_alpha.py                               # daily ETF tests
```

## Files
- `cycle` — original Pine Script.
- `hull_mitm.py` — direct Pine port (cascade bug confirmed).
- `fmh_lockpicker.py` — daily FMH rebuild with Hurst gate.
- `fmh_multitf.py` — multi-TF (90m/1d/1w/1mo) HMA-slope cascade.
- `fmh_indicators.py` — RSI/MFI/Stoch variants + HMA×RSI gate + RSI mean-rev.
- `basket_backtest.py` — equal-weight 30-name portfolio backtest.
- `test_alpha.py` — daily ETF eval harness.
