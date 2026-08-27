# Warrant Mispricing Detector — Process Log

This document traces how the `warrants` tool reached its current shape:
what we built, what we tried that didn't work, and the design decisions
along the way.

## 1. Problem framing

The starting question was simply: **how do I find mispriced warrants?**
We narrowed this through conversation into three concrete sub-questions:

1. Which warrants are trading at a meaningful discount to a defensible
   theoretical fair value?
2. Which warrants show unusual flow that may precede a price move?
3. Among the candidates, which are actually tradeable and which are
   theoretical-only?

The system that exists today answers all three via separate CLI
subcommands, each producing a ranked table.

## 2. Approach evolution

### 2a. Technical (relative-price) scanner

First pass treated `(common, warrant)` as a stat-arb pair:
  - Resample to weekly and monthly bars
  - Compute `ratio_z` = rolling z of `log(W/C)`
  - Compute `resid_z` = rolling z of residual from rolling OLS
    `log(W) ~ a + b·log(C)` (cointegration spread, handles non-1.0 delta)
  - `composite_z` = average of the two; inflections via `find_peaks` and
    zero-crossings

Added volume signals alongside: `warrant_vol_z`, `warrant_dollar_vol_z`,
`w2c_vol_z` (warrant-vs-common volume ratio z-score). `joint_z` then
amplifies the price signal in proportion to confirming volume.

This produced a per-pair report. Useful for inspection, but didn't scale
to screening — you'd have to know the pair already.

### 2b. Universe construction

The screening goal needed a universe. We worked through sources:

| Source | Result |
|---|---|
| Hand-curated SPAC list | Mostly stale (redeemed/expired by 2026) — abandoned |
| financedatabase | Install failure (`odfpy` build error) |
| **NASDAQ Trader symbol directory** | **460 warrants → 387 paired (strict) → 431 paired (with fuzzy+prefix fallback) → 369 active** |
| TSX/TSXV via Yahoo | Yahoo doesn't carry the `.WT.TO`/`.WT.V` warrant tickers — 0 hits across 3654 commons |
| OTC Markets | Gated (403/timeout) |
| Cboe BZX symbol directory | 1.3MB HTML, no embedded JSON/CSV |
| Yahoo symbol search | Cap of 7 hits per query |
| Yahoo screener REST | 401 (needs crumb auth) |
| nasdaq.com screener API | 503 (rate-limited) |
| stockanalysis.com warrants | 404 on all paths |
| **SEC company-tickers wide probe** | **2h runtime, 0 new pairs** — empirically confirms NASDAQ Trader is the practical limit |
| EDGAR 8-A12B (recent warrant registrations) | Mostly overlaps NASDAQ Trader |

NASDAQ Trader's `nasdaqlisted.txt` + `otherlisted.txt` gave the bulk of
the universe. Pairing warrants to their commons used three layers:

1. Strict issuer-key match (regex-normalized name, word-boundary
   suffix stripping)
2. Fuzzy fallback: token-set overlap (≥2 shared tokens, ≥66% coverage,
   unique winner)
3. Prefix-guess fallback: strip standard warrant suffixes from the
   warrant ticker (`XYZW → XYZ`) and use the result as the common

Active filter: at least one bar of warrant data within `max_stale_days`
(default 90). This is a yfinance batch call; one trip covers the whole
universe in ~10s.

### 2c. Model-based fair value (Black-Scholes)

For each `(common, warrant)`, compute:

```
sigma = clip( min(realized_1y, realized_3m), 0.30, 2.00 )
BS    = bs_call(S=common_px, K=strike, T=3.0, r=0.045, sigma)
theo  = dilution_factor (0.90) × ratio (1.0) × BS
gap   = (warrant_px − theo) / theo
asymm = theo / warrant_px            # the "upside multiple"
```

Filter rows where the gap can be **legitimately explained** by:
- Redemption-cap risk (SPAC warrants are forced-redeemed at $0.10 once
  common holds $18+ for 20/30 days). Drop names with moneyness ≥ 1.0
  or any ≥$18 print in the lookback window.
- Sigma outside the [0.30, 2.0] band — pre-deal SPACs (low) or
  post-crash skew (high).

What remains is a "discount that can't be explained by redemption-cap
risk" — the actionable shortlist.

### 2d. Strike resolution

The single biggest accuracy bug, fixed in two stages:

**Stage 1: split-adjustment.** Many SPAC warrants have their strike
adjusted by reverse splits on the common (1-for-10 RS takes $11.50 to
$115). `common_split_factor()` reads `yfinance.Ticker.splits` and the
strike divides by the cumulative factor. Confirmed errors fixed:

| Common | Reverse Split | Adjusted Strike |
|---|---|---|
| XBP | 1-for-10 | $115 |
| SEAT | 1-for-20 | $230 |
| PIII | 1-for-50 | $575 |
| PDYN | 1-for-6 | $69 |
| CLSK, GRRR | 1-for-10 | $115 |

Before this fix, the screen was flagging XBP and others as "deep
discounts" when in reality they're deeply OTM at the adjusted strike.

**Stage 2: EDGAR scrape.** For each common, pull the most recent
S-1/S-3/424B5/8-A12B/8-K filings, regex over 240-char windows around
mentions of "warrant" for `$X.XX` patterns, mode-vote across matches.

Tested on 15 names; resolved 10. Critical interaction with split
adjustment: filings often already show the post-RS strike (PDYN's
filing literally shows $69), so when EDGAR resolves a strike, we use
it AS-IS and **skip the split adjustment**. The output column
`strike_source` shows which path was used: `edgar` / `listing` /
`default+split_adj` / etc.

Notable EDGAR corrections vs. the default $11.50:
- ARBE: **$2.35** (Arbe Robotics — non-standard)
- ASPSW/Z: **$9.59** (Altisource scheme-of-arrangement)
- ODV: **$10.70** (Osisko Dev)
- XRX: **$8.00** (Xerox post-restructuring)
- CING: **$5.14** (Cingulate — unique)

### 2e. Business quality + recent inflection scoring

For each candidate, pull `yfinance.Ticker.info` and score:

- **rev_score**: revenue traction (size + YoY growth, capped)
- **margin_score**: gross margin × 2 + operating-margin gate
- **runway_score**: cash / quarterly burn → quarters of runway
- **inflection**: +EPS growth, +analyst coverage, **−0.5 if YoY rev
  growth is negative** (declining-business penalty)

Composite: `(−gap_pct) × (1 + quality) × max(0, 1 + inflection)`.

A name with deep discount + great biz + accelerating fundamentals gets
high composite; a deep discount on a declining biz with no positive
inflection collapses.

### 2f. Asymmetry column

`asymmetry = theoretical / warrant_px`: how many × your money if BS
is right. Complements `gap_pct` (which saturates near -100%): names
with gap_pct -98% can still differ by 50× vs 20× in upside multiple.

### 2g. Unusual-volume screens

Two complementary CLI subcommands beyond the BS pipeline:

**`flow`** — single-window unusual volume:
- `surge_5d`, `surge_1d`: recent vs 30-trading-day baseline
- `vol_z_1d`: log-volume z-score on the 30d distribution
- `w2c_surge`: today's warrant-vs-common-volume ratio ÷ 30d median
  — the cleanest "warrant-specific accumulation" signal

**`coil`** — pre-breakout pattern across three non-overlapping windows:
- `w0` = last 5 sessions
- `w1` = 5–10 sessions ago
- `w2` = 10–30 sessions ago
- Require: `vol_w0/vol_w2 ≥ 1.5`, `range_pct_10d ≤ 0.20`,
  `w2c_accel ≥ 1.2`
- `coil_score = vol_accel × (1/range_pct) × w2c_accel`
- Persistence flag = `vol_w0 > vol_w1 > vol_w2`

The screens layer cleanly. A name fired by **all three** (`opportunities`
+ `flow` + `coil`) is rare and high-conviction (e.g. DYNCW today).

### 2g-bis. Informed-flow screen (literature-grounded)

`flow`/`coil` measure *how much* the warrant traded. The microstructure
literature on informed trading in derivatives says raw volume is the weak
form; what predicts the underlying is **directional**, **leveraged** flow
that **leads** the stock. The `informed` screen builds a composite from:

- **Abnormal O/S** — Roll-Schwartz-Subrahmanyam (2010), Johnson-So (2012):
  log-abnormal warrant/common dollar-volume ratio vs the name's own median.
- **Signed order-flow imbalance** — Easley-O'Hara-Srinivas (1998),
  Pan-Poteshman (2006): direction matters, not turnover. Daily trades signed
  by close-location value (Bollen-Whaley proxy); net signed $-flow / gross.
- **Leverage tilt** — Black (1975): warrant elasticity `Ω = Δ·S/W` as a
  bounded multiplier; informed concentrate where leverage is greatest.
- **Relative price impact** — Kyle (1985) λ, Amihud (2002): warrant Amihud
  ÷ common Amihud, the stealth-accumulation footprint.
- **Lead-lag diagnostic** — corr(warrant flow_t, common ret_{t+1}).

The payoff is a distinction raw volume can't make: BBCQW topped `flow`/`coil`
(w2c 8.8, coil 399) but its signed imbalance is **negative** — the big
volume is *distribution*, not accumulation. TLSIW shows the cleanest
informed signature (ofi +0.58, lead_lag +0.31). Full grounding and
citations in `LIT.md`.

`conviction` now folds this in as a 4th screen with a twist: since
`w2c_surge`/`coil_score` are **unsigned**, the gross-flow reward is
*modulated* by `ofi` (`flow_dir_mult = clip(1+ofi, 0, 2)`), and the
informed screen only counts toward the breadth bonus on net accumulation
(`ofi ≥ 0.1`). So a warrant being sold into no longer floats to the top on
turnover alone — TLSIW (accumulation) overtakes BBCQW (distribution).

### 2h. Real-data gotchas patched along the way

- yfinance silently falls back to the parent ticker when a multi-word
  warrant ticker isn't carried (`GME WT` returns GME's prices). Added a
  sentinel-comparison guard.
- yfinance `Ticker(t).history()` chokes on some warrant tickers that
  the batch endpoint handles fine. All price fetches use the batch path.
- yfinance batch download forward-fills prior closes into the `Close`
  field on days with zero volume. Last-close can look tradeable when
  the warrant didn't actually trade. Added 5-day-volume context columns
  and an optional `--min-dvol` filter. Default is off — the user
  pointed out that yfinance volume is incomplete, so absence of prints
  doesn't equal absence of a market.
- yfinance `info.revenueGrowth` occasionally returns nonsense like
  23,775 (BZAI). Capped growth fields to `[-100%, +300%]` before
  scoring or display.
- 13F warrant-king cross-reference: filings show **near-zero current
  warrant holdings** (Mudrick has 3 positions total, Magnetar 1755/0
  warrants). Real reason: most SPAC arb funds hold the common for the
  trust-yield + redemption put, not the warrant. The warrant kings
  signal lives in 13G/13D filings, not 13F — a bigger project.
- Option-warrant parity: when listed-call bid/ask are both 0 (stale /
  illiquid), the code now flags `call_stale_quote: True` and refuses to
  print a "WARRANT CHEAP" verdict on garbage data.

## 3. The CLI surface today

```
warrants universe                      # build/refresh the active universe CSV
warrants pair COMMON WARRANT           # technical scan on one pair
warrants screen [--quality] [...]      # BS fair-value screen
warrants opportunities [--resolve-edgar]  # end-to-end ranked list
warrants flow [--sort surge_5d|...]    # suspicious volume
warrants coil                          # coiled-spring (pre-breakout)
warrants informed [--window 10]        # informed-flow rank (see LIT.md)
warrants parity COMMON W STRIKE EXPIRY # option-vs-warrant parity check
warrants edgar TICKER [--search]       # recent SEC filings
```

All produce ranked tables to stdout; `--out path.csv` writes the same.

## 4. What's in the repo

- `warrants` — single-file Python module (~1900 lines), CLI entry point
  is `python warrants <cmd>`. Pure functions for every signal; CLI is
  just a thin wrapper.
- `warrants_universe.csv` — active warrant pairs (regenerated by
  `warrants universe`).
- `requirements.txt` — minimal: pandas, numpy, scipy, yfinance, requests.
- `.gitignore` — excludes scan output CSVs.

Removed along the way: Streamlit (UI bloat for what's really a CLI tool),
plotly/matplotlib (unused), financedatabase/fredapi/pytz/statsmodels/
scikit-learn (none used by the pure functions).

## 5. Honest limitations

1. **Strike resolution is not 100%.** ~67% of the deepest-discount
   candidates resolve from EDGAR. For the rest we fall back to the
   $11.50 SPAC default + split adjustment. When the actual strike is
   non-standard ($9, $13, $115, etc.) and EDGAR doesn't resolve, the
   gap is wrong.
2. **Expiry assumed 3 years.** Some warrants have <1 year left;
   their BS fair value should be a fraction of what we report. Pulling
   actual expiry from EDGAR is the next accuracy upgrade.
3. **Sigma is realized, not implied.** Crashed names have inflated
   realized vol that overstates forward-expected vol — leading to
   overstated BS fair value for deeply-OTM warrants on crashed commons.
4. **Liquidity is mostly theoretical.** Many "top" names trade
   <$1K daily $-volume. yfinance bid/ask is unreliable for penny
   warrants. Real execution needs a broker feed.
5. **Universe ceiling is real.** Free sources are exhausted at ~370
   US-exchange-listed pairs. OTC/Canadian/international warrants
   require paid feeds (Polygon, OTC Markets API, FactSet).
6. **13F warrant-king tracking didn't pan out.** Real signal lives in
   13G/13D, not 13F. Untapped.

## 6. The screen output today (369-pair universe, EDGAR-resolved)

**Single most asymmetric setup on a real business**: CINGW (Cingulate) —
EDGAR-confirmed K=$5.14, moneyness 0.89, asymmetry 38.6×.

**Single most liquid near-the-money warrant**: NUCLW (NuScale Power) —
EDGAR K=$11.50, moneyness 0.92, $163K daily $-volume, asymmetry 5.1×.

**Single name lit up by all three screens** (`opportunities` + `flow` +
`coil`): DYNCW (Dynamix Corp) — moneyness 0.94, asymmetry 17.5×,
$5K daily $-volume, `coil`-scan persistence=True.

**Pre-breakout coil**: DNMXW — w2c volume ratio 11.5× baseline, price
range 13.4% (compressed), volume up 1.7× across windows.

**Best balanced risk/reward**: EVLVW (Evolv Tech) — moneyness 0.50,
asymmetry 12.6×, real biz ($160M rev, +45% YoY), quality 4.8.

**Pure lottery with real institutional flow**: PIIIW (P3 Health Partners)
— $433K daily $-volume on a $575 adjusted strike, asymmetry 39×. Don't
fool yourself it's a model arb; it's the speculative-flow lottery the
@CallsPuts1 thread highlighted.
