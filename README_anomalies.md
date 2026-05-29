# S&P MidCap 400 — Weekly Seasonal Anomaly Scanner

`midcap_weekly_anomalies.py` scans the S&P 400 MidCap universe for **weekly
seasonal anomalies**. Instead of only asking *"does this name go up in this
calendar week?"*, it asks *"does this name historically enter an unusually
favourable (or unfavourable) **tradable state** in this week-of-year?"*

## What it computes

For every asset, weekly bars are grouped by **week-of-year** (one observation
per year). For each bucket it computes the **full measure catalog** (58 columns
in the CSV):

| Category          | Measures |
|-------------------|---------|
| Return quality    | mean, median, std, Sharpe, Sortino, robust Sharpe (median/MAD), t-stat, win rate, positive-median, downside deviation |
| Payoff asymmetry  | gain-to-pain, tail ratio, expected-shortfall ratio, skew, kurtosis, worst, best, max drawdown |
| Volume confirm    | rel-volume (in/out), vol-z mean, vol-elevated rate, return×vol, accumulation, distribution, net accumulation, VA gain-to-pain, volume-confirmed Sharpe, up/down-volume ratio, volume concentration |
| Volatility state  | realized-vol anomaly, upside/downside vol, vol asymmetry, semivariance delta, cross-sectional compression score |
| Liquidity         | median dollar volume, liquidity-adjusted return, cross-sectional percentile |
| Forward / persist | forward 1/2/4/8-week drift, persistence correlation, trend-continuation rate |
| Reliability       | sample size, sample-size penalty √(n/(n+20)), sub-period sign stability, reliability blend z(t)+z(win)+z(GPR)−z(maxDD) |

Each bucket is penalised for small samples (`sqrt(n/(n+20))`) and for
instability across sub-periods, then components are **z-scored
cross-sectionally** and blended:

```
composite = 0.30·z(tradable_sharpe) + 0.25·z(vol_adj_gain_to_pain)
          + 0.20·z(net_accumulation) + 0.15·z(persistence) + 0.10·z(liquidity)
```

A separate short composite flips the return-linked components. The reported
`score` is the better of the two, with a `LONG`/`SHORT` direction label.

## Data sources

- **Universe:** S&P 400 MidCap constituents from Wikipedia (static fallback if
  the fetch fails). `financedatabase` can be swapped in but pulls a heavy dep
  tree (`odfpy`) that fails to build in some environments, so Wikipedia is the
  default.
- **Prices:** `yfinance` weekly bars, cached to `.cache/` as pickle so reruns
  are instant.

## Usage

```bash
pip install -r requirements-anomalies.txt

python3 midcap_weekly_anomalies.py                 # current week, full 400
python3 midcap_weekly_anomalies.py --limit 50      # quick subset
python3 midcap_weekly_anomalies.py --target-week 22 --top 30 --csv out.csv
```

Key flags: `--years` (history, default 20), `--min-years` (min obs per bucket,
default 8), `--target-week` (ISO week, default = current), `--refresh`
(ignore cache).

## Caveat

Seasonal/calendar anomalies are fragile and prone to overfitting. The
sample-size and stability penalties reduce — but do not eliminate — the risk of
mining noise. Treat the output as a hypothesis generator, not a trade signal.
