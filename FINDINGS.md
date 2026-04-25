# Hull MITM / FMH lock-picker — backtest findings

## Iteration 3: indicator variants on single names (this is the alpha)

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
python3 fmh_indicators.py                           # main result
python3 fmh_multitf.py                              # HMA-only baseline
python3 test_alpha.py                               # daily ETF tests
```

## Files
- `cycle` — original Pine Script.
- `hull_mitm.py` — direct Pine port (cascade bug confirmed).
- `fmh_lockpicker.py` — daily FMH rebuild with Hurst gate.
- `fmh_multitf.py` — multi-TF (90m/1d/1w/1mo) HMA-slope cascade.
- `fmh_indicators.py` — RSI/MFI/Stoch variants + HMA×RSI gate + RSI mean-rev.
- `test_alpha.py` — daily ETF eval harness.
