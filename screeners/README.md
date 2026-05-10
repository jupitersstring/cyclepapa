# Screeners

Self-contained Python scripts that compute weekly/monthly technical signals across a list of tickers using `yfinance`. Each script takes a CSV universe (`--universe`) of `ticker` values, fetches OHLCV data, computes its signal set, and writes a results CSV (`--out`).

Usage pattern:

```
python3 screeners/<name>.py --universe path/to/universe.csv --out path/to/results.csv
```

A universe CSV needs at minimum a `ticker` column (yfinance-style symbols, e.g. `AAPL`, `7203.T`, `SDR.L`, `0001.HK`).

## Scripts

### `dalton_screen.py` — Mind Over Markets / Auction Market Theory (simpler version)

Implements weekly-bar approximations of James Dalton's Mind Over Markets framework. Computes 15 signals on the most recent week:

- Composite week classification (Buying / Selling / Neutral by open quartile)
- 3-to-I week (bull/bear) — the 94%-continuation pattern
- Neutral-Extreme week (outside week closing on extreme — 92% stat)
- One-timeframing status (consecutive-weeks higher-low / lower-high)
- One-timeframing break (earliest structural change signal)
- Balance-area detection + breakout above/below
- Failed auction → outside week (bracket-reversal trade)
- Spike detection + next-week resolution (continuation/acceptance/rejection)
- P-formation (short-cover rally, fade signal)
- b-formation (long-liquidation drop, fade signal)
- POC / VWAP migration across consecutive 4-week windows
- Value Area Rule trigger (open outside prior range, accept inside)
- Unsecured (poor) high / low detection
- Rotation factor (last 4 weeks)
- Volume vs trailing average

Output is one row per ticker with all signal columns. Apply your own filter — example, a "bull score" composite weighted by signal severity:

```python
score = (
    df['three_to_i_bull'].astype(int)*4 +
    df['neutral_extreme_bull'].astype(int)*3 +
    df['breakout_above_balance'].astype(int)*3 +
    df['failed_dn_outside_up'].astype(int)*3 +
    df['value_area_rule_bull'].astype(int)*2 +
    df['otf_dn_broke'].astype(int)*2 +
    (df['otf_higher_streak'] >= 4).astype(int)*1 +
    (df['rotation_factor_4w'].fillna(0) >= 3).astype(int)*1 +
    (df['poc_migration_pct'].fillna(0) > 0).astype(int)*1
)
```

Then narrow to setups with room left and volume confirmation:

```python
asymm = df[(df['bull_score'] >= 5) &
           (df['pct_below_52w_high'].between(2, 30)) &
           (df['vol_vs_avg'].fillna(0) >= 1.0)]
```

### `dalton_complete_screen.py` — Full Mind Over Markets + Markets in Profile

The comprehensive version. Adds everything the simpler `dalton_screen.py` omitted:

- **Proper Value Area** (70% volume around POC) computed empirically from daily bars within each weekly/monthly period — not approximated from H/L.
- **TPO Count** — daily closes above/below POC = selling/buying TPOs.
- **Day Type Classification** — Normal / Trend / Double-Distribution / Neutral / Nontrend / Normal Variation.
- **Opening Type** — Open-Drive / Open-Test-Drive / Open-Reject / Open-Auction.
- **Open vs Prior VA** — within / above-in-range / below-in-range / out-of-range up/down.
- **Initiative vs Responsive** — bar's location relative to prior period's value area.
- **Directional Performance Matrix** — attempted direction × volume × value placement; MIRAGE_BUY / FAILED_UP / CONFIRMED_UP&DN / LOW_VOL_RALLY.
- **Value Area Rule** — open outside, accept inside, traverse all the way.
- **Spike + 3 resolution rules** — continuation / acceptance / rejection.
- **Balance-area streak + breakout** with multi-bar overlap detection.
- **Failed Breakdown Reclaim** and **Failed Breakout Rejection** (bracket reversals).
- **P-formation** (short cover) and **B-formation** (long liquidation) detection over 5-bar window.
- **No-tail anomaly** — multi-bar streak of close-on-extreme without tails.
- **Gap behavior** — held vs filled with directional implication.
- **5-pillar macro framework**: long bracket quality (25 pts) + compression percentile (20 pts) + sponsorship/RS-at-13w-26w-high (25 pts) + breakout readiness (20 pts) + asymmetry ratio destination/risk (10 pts) = 100 max.
- **Per-bar score time series** — 1st and 2nd derivatives detect INFLECTION_UP / DECELERATION_UP / ACCELERATION_UP states.
- **Cross-timeframe hierarchy** — monthly bear vetoes conflicting weekly bull (Dalton's ruling reason).
- **Relative-to-benchmark series** — every signal also computed on ticker/benchmark ratio.

Computes ~80 columns of features per ticker on weekly + monthly + relative weekly + relative monthly. Heavy: ~1 min per 100 tickers due to Value Area calculation. Checkpoints every 250 tickers.

Output composite `final_rank` combines macro structural score × signal direction × velocity (1st derivative) + acceleration (2nd derivative), with monthly-bear veto penalty.

Typical use:

```bash
python3 screeners/dalton_complete_screen.py \
    --universe my_universe.csv \
    --out results.csv \
    --benchmark SPY    # or ^FTSE, FTSEMIB.MI, ^IBEX, URTH, etc.
```

Quality filter recommended:

```python
quality = df[
    (df['absW_macro'] >= 30) &                              # decent structural setup
    (df['absW_state'].str.endswith('_UP')) &                 # bullish state
    (~df['absM_state'].isin(['INFLECTION_DOWN','ACCELERATION_DOWN','TRENDING_DOWN'])) &
    (df['absW_pos_in_bracket'].between(40, 90)) &            # room left
    (df['absW_room'] >= 8)                                   # at least 8% to destination
].sort_values('final_rank', ascending=False)
```

Special-flag inspection:

```python
# Hidden bull: selling structure with higher value placement
mirages = df[df['absW_dp_signal'] == 'MIRAGE_BUY']

# Bottom forming: long-liquidation drop decelerating
b_form = df[df['absW_b_form'] == True]

# Bracket reversal: broke balance low, reclaimed
fail_bd = df[df['absW_failed_bd_reclaim'] == True]
```

### `breakout_weekly.py` / `breakout_monthly.py` — Top-of-range breakout

Original "top of multi-year range + MFI inflecting + ROC turning + volume profile air-pocket" screen. Outputs MFI, ROC, point-of-control distance, volume-above-POC ratio. Use for finding names already triggering breakouts.

### `compression_weekly.py` / `compression_monthly.py` — MFI higher-low + range compression + just-inflecting

The 3445.T-style pattern: stock is in a long base, MFI made a higher low (bullish divergence), ATR compressed during the recent low, MFI just turned up. Sitting near top of range with volume shelf below. Pre-trigger phase.

### `prebreakout_screen.py` — Weinstein / Qullamaggie / O'Neil

Late Stage 1 / handle / tight flag setup with prior leg required:

- Prior 6-month return ≥ 25% AND 12-month ≥ 30%
- Last 8 weeks: ATR < 3.5%, range < 15%
- Within 3–15% of 52-week high
- Above 30-week MA, MA flattening or just turning up
- Volume drying up during consolidation
- MFI in 40–65 neutral zone

### `absorption_screen.py` — Money out, price holding (Wyckoff accumulation)

MFI dropped ≥ 10 points but price moved < 7% (divergence ratio < 0.4) with low realized volatility — sellers exiting being absorbed. Bullish under-the-surface accumulation pattern.

## Building a universe

Use `financedatabase` to assemble tickers by country / exchange / market cap:

```python
import financedatabase as fd
import pandas as pd

eq = fd.Equities()

# Example: US small/mid cap
df = eq.select(country='United States')
df = df[df['exchange'].isin(['NMS','NYQ','NCM','ASE','NGM','PCX'])]
df = df[df['market_cap'].isin(['Small Cap','Mid Cap'])]
df.reset_index().rename(columns={'symbol':'ticker'}).to_csv('us_universe.csv', index=False)
```

Foreign developed-market ticker suffixes:
- `.T` Tokyo, `.HK` Hong Kong, `.L` London, `.PA` Paris, `.AS` Amsterdam
- `.AX` Australia, `.NZ` New Zealand, `.TO` Toronto, `.SI` Singapore
- `.KS` / `.KQ` Korea KOSPI / KOSDAQ, `.TW` / `.TWO` Taiwan, `.MI` Milan
- `.HE` Helsinki, `.OL` Oslo, `.ST` / `.STO` Stockholm, `.CO` Copenhagen
- `.BR` Brussels, `.SW` SIX Switzerland

## Cross-screen synthesis pattern

The screens look at different lifecycle stages and rarely overlap by design. Genuine multi-bucket hits are highest conviction:

- **Fundamental + Technical overlap** = cheap business with the technical trigger firing
- **Compression + Absorption** = forming the base AND quietly being accumulated
- **3-to-I + Balance breakout** = two Dalton signals firing in the same week (rare)

A name appearing on 3+ screens out of ~7-8 across fundamental/technical/absorption buckets is genuinely rare — typically <20 names from a 2,000-ticker universe.

## Notes

- All screens use weekly-bar approximations of intraday Market Profile / Auction Market Theory measures, since intraday tick data is not available via yfinance.
- yfinance rate-limits aggressively past ~3,000 single-ticker calls; `yf.download` bulk is more forgiving but still hits limits.
- Re-run with smaller batches and `time.sleep` between batches to recover from rate-limit failures.
- Several universes (Korean, foreign micro caps) have spotty Yahoo coverage; expect 60-75% capture rate on initial run.
