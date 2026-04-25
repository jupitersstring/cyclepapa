# Hull MITM / FMH lock-picker — backtest findings

## Setup
- Daily OHLC via yfinance, 15 years.
- Self-similar (Fibonacci-spaced) scales: 5, 8, 13, 21, 34, 55, 89.
- Per-scale: OLS slope of log price, R² as trendiness, sign as direction.
- Rolling DFA Hurst (1y window) as global persistence gate (FMH regime).
- Cross-scale **coherence** = |Σ wᵢ·signᵢ| / Σ wᵢ.
- Trade when coherence ≥ τ AND H ≥ 0.5; smoothed 3 bars; 1 bp/turn cost.

## Headline result — concept does **not** generate alpha as-is

| test                              | strat CAGR | B&H CAGR | strat Shp | B&H Shp | MaxDD strat | MaxDD B&H |
|---|---:|---:|---:|---:|---:|---:|
| SPY long-flat                     |   0.35%    | 13.85%   |  0.11     | 0.84    | −13.6%      | −33.7%    |
| QQQ long-flat                     |   0.47%    | 18.65%   |  0.12     | 0.93    | −13.0%      | −35.1%    |
| BTC-USD long-flat                 |  12.28%    | 35.70%   |  0.62     | 0.83    | −33.2%      | −83.4%    |
| GLD long-flat                     |   3.30%    |  7.49%   |  0.50     | 0.52    | −15.4%      | −45.6%    |
| 9-ETF rotation top-2 / 20 d hold  |   4.57%    |  9.09%   |  0.44     | 0.75    | −26.2%      | −25.6%    |

The only thing the strategy is good at is **drawdown reduction** — it gives up
most of the upside but cuts max drawdown roughly in half on equity ETFs and by
~60% on BTC. Sharpe is worse in every case, so the avoided drawdowns are bought
with so much idle time that risk-adjusted return suffers.

## Why it fails
1. **Late entries.** A trend has to align across 5+ scales before the lock
   "picks" — by then the move is already mature and forward 5-day signed return
   is +0.0% on SPY/QQQ. The signal trails, it does not lead.
2. **Hurst gate is too strict on equity indexes.** Daily SPY's 1-y rolling H
   sits around 0.50-0.55; the ≥0.5 floor only marginally helps and combined with
   coherence keeps the strategy flat 75-85% of the time on indexes.
3. **Trend-following on indexes loses to drift.** Long-short on SPY/QQQ was
   −0.9 / +0.3 % CAGR — short legs bleed during persistent uptrends.
4. **Cross-sectional rotation also fails** because every ETF in the universe is
   ultimately equity-correlated and shares the same factor (US growth), so
   rotation just adds noise vs. equal-weight.

## Where a working version probably lives
- **Volatility / mean-reversion regime overlay, not a momentum signal.** Use
  high coherence + falling Hurst as a *de-risk* signal on top of buy-hold,
  not as a directional trade.
- **Single-name dispersion universe** (e.g., S&P sector or single names),
  not ETF baskets that all load on the same factor.
- **Fade extreme alignment.** When all 7 scales agree at coherence=1.0 the
  next 5d return distribution should be checked — typical trend exhaustion.
- **Intraday TFs** (the script's native habitat). Daily bars give too few
  unlock events; the sub-hour cascade is where the lock metaphor adds info.
- **Move from Hull slope to actual scale-invariant features** — wavelet energy,
  multifractal spectrum width, lead-lag across scales — instead of ranking scales
  only by sign agreement.

## Files
- `cycle` — original Pine Script (untouched reference).
- `hull_mitm.py` — direct Python port with the original cascade logic. Confirmed
  the bug: cascade gating starves higher pairs; shear caps at 0.19, lock never
  engages. Kept for reference.
- `fmh_lockpicker.py` — FMH-flavored rebuild: φ-scales, OLS slope/R², DFA Hurst.
- `test_alpha.py` — single-asset and cross-sectional evaluation harness.

## Repro
```
python3 test_alpha.py
```
