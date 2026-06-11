# Wind-down / NAV-discount screener

Screens UK closed-end funds (and a global tail of CEFs / BDCs /
holding companies) for the setup illustrated in the project brief:
**weekly volume spike near the volume-profile POC, MFI(18) optional,
on a managed-wind-down or NAV-discount workout candidate**.

The goal is to surface the chart **before** the discount closes —
"accumulation before news is announced / value is crystallised."

## Pipeline (v3)

```
universe.csv  (catalyst + NAV-quality + ISIN per ticker)
        │
        ▼
metadata.py  (loader, validates, rejects duplicate tickers)
        │
        ▼
price_store.py  (per-ticker weekly OHLCV parquet, 24h TTL)
aic_scraper.py  (theaic.co.uk live discount feed, 305 UK CEFs)
yahoo_nav_scraper.py  (Yahoo bookValue proxy for non-UK)
signals.py  (Google News -> director dealings / advisor / wind-down)
        │
        ▼
screen_core.py
  · base detection (IQR-based, drift-aware)
  · POC over base only
  · windowed directional volume (8-bar signed sum)
  · phase classifier (BASE_ABSORBING / CAPITULATION / …)
  · recovery × IRR upside math (params.py)
  · investability gates (params.INVESTABILITY_GATES)
        │
        ▼
screen_v3.py  -> results_YYYYMMDD.csv
```

## What's encoded

- **Upside = (recovery / (1 − discount) − 1) × catalyst probability**.
  Recovery rate per NAV class (LISTED 0.97, PROPERTY 0.80, PE 0.70,
  DISTRESSED 0.40) — embeds the market's NAV-write-down forecast in
  the upside, not in the setup score.
- **IRR**, not total return — catalyst-duration table normalises a
  30-month wind-down against a 9-month activist tender.
- **Setup score = pure technicals**: phase × POC × base length.
  Catalyst and NAV multiply once at the end via expected_irr.
- **Phases**:
  `BASE_ABSORBING` (vol building across 8 bars, positive directional
  bias) ▪ `BASE_BREAKOUT` (above base high on volume) ▪
  `CAPITULATION` (selloff + vol spike + washed MFI — the CHRY
  archetype) ▪ `BASE_QUIET` ▪ `BASE_DECLINING` ▪ `RECENT_SELLOFF`
  ▪ `POST_RERATING` (tapered) ▪ `DOWNTREND` ▪ `NO_BASE`.
- **Signal layer** (Google News, 120-day lookback, 30-day half-life):
  director dealings (with direction + £ amount parsing),
  advisor-hired, strategic-review, wind-down, buyback. Each headline
  assigned to its strongest single category (no double-count).
  Per-ticker exclusion lists kill known noise (PSUS for PSH.L,
  Conduit Holdings for OCI.L, etc.).
- **Investability gates**: market cap ≥ £50m, daily value ≥ £0.25m,
  net gearing ≤ 150%, ongoing charge ≤ 3.5%. Gate-failing names get
  composite_score = 0 (but are still reported for awareness).

## Quickstart

```bash
pip install -r requirements.txt
python3 -m pytest tests/                 # 49 tests
python3 screen_v3.py                     # full universe (438 tickers)
python3 screen_v3.py --signals           # also scrape news signals
python3 screen_v3.py --tickers SEIT.L    # one name
```

Outputs:

- `results_YYYYMMDD.csv` — full ranked table.
- `signals_history.csv` — daily signal snapshot per ticker
  (for week-on-week rising-signal detection).
- `data/prices/<ticker>.parquet` — cached OHLCV.

## Top picks (commit d5c9aae, smoke run on 9 names)

| Ticker | Phase | Discount | NAV class | Recovery | Total return | Duration | Prob | **IRR** |
|---|---|---|---|---|---|---|---|---|
| SYNC.L | BASE_ABSORBING | 44% | LISTED_CLEAN | 0.97 | 72% | 36m | 0.20 | **4.6%** |
| SEIT.L | BASE_QUIET | 48% | RENEWABLES_DCF | 0.80 | 55% | 30m | 0.80 | **15.8%** |
| NESF.L | BASE_QUIET | 37% | RENEWABLES_DCF | 0.80 | 27% | 15m | 0.50 | **10.8%** |
| GCP.L | BASE_QUIET | 22% | DEBT_AMORTISING | 0.95 | 22% | 15m | 0.50 | **8.7%** |
| CHRY.L | BASE_DECLINING | 43% | PRIVATE_EQUITY | 0.70 | 22% | 18m | 0.70 | **10.1%** |

Run `screen_v3.py --signals` to apply news-driven probability
adjustment (cuts SBO.L/RESI.L probability for quiet catalysts;
boosts SEIT.L/CHRY.L where insider buying is visible).

## Known limitations / next steps

1. **Probabilities still hand-tuned.** A historical event study
   over RSE / AERI / RMII / USF / HEIT / ADIG / HGEN / THRG (all in
   our 5y data window) would calibrate the params.CATALYST_PROB_BASE
   numbers and the signal multiplier. See "next session" below.
2. **Yahoo bookValue is a noisy proxy** for non-UK CEFs (overstates
   discount on European holdcos that hold listed subsidiaries at
   historical cost). Per-sponsor scrapers would be cleaner.
3. **Streamlit page (`cycle`) still calls v1 logic** via
   `nav_discount_finder.render_nav_discount_finder`. Refactor to
   call `screen_v3.main()` programmatically and render the CSV.
4. **TR-1 filings (stake-building disclosures) and PDMR feeds via
   Investegate** are higher-grade signal than Google News and not
   yet captured.

## Layout

```
universe.csv             metadata (ticker, isin, catalyst, nav, …)
params.py                recovery rates, probabilities, durations, gates
metadata.py              universe loader (with validation)
aic_scraper.py           theaic.co.uk daily discount feed
yahoo_nav_scraper.py     Yahoo bookValue NAV proxy
price_store.py           OHLCV parquet cache
signals.py               qualitative news-signal scraper (v2)
screen_core.py           pure-function screening primitives
screen_v3.py             main runner -> results CSV
tests/                   pytest suite
nav_discount_finder.py   legacy Streamlit page (v1 logic)
qualitative_signals.py   legacy signal scraper (kept for reference)
screen_v2.py             legacy screener (kept for diff)
run_screen.py            legacy v1 CLI runner
cycle                    legacy cycle-analysis Streamlit entry
```
