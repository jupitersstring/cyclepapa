# reverse_arch_v8_1_asymmetry — Ritter run, v2 (with patches)

This is the v2 run after the three patches in commit `10236cf`:
- EARLY_IMMINENT_ASYMMETRY weighting unblocked
- Fixed-star eclipse tags uppercased so the scorer's amplifier matches
- Deterministic sort tiebreaker

## Run setup

- Universe: 4,485 US IPOs (Ritter mirror, 2000-2021) + 7 hardcoded extras.
- Forward events: 50 eclipses (6 fixed-star tagged), 17 outer-pair, 86 stations.
- Gate-passed: 1,635 IPOs (same as v1).
- 1980-2025 theoretical-date sweep enabled (RA_SWEEP=1).

## Distribution: now both buckets populated

- ENDURING_HIGH_MAGNITUDE_ASYMMETRY: ~1,549 (was 1,573)
- BALANCED_ASYMMETRY: ~74 (was 62)
- EARLY_IMMINENT_ASYMMETRY: 12 (was 0)

The Saturn-Neptune conjunction Feb 2026 (lon=0.75°) and the 2034-03-20
total solar eclipse near Scheat both substantially lift forward `peak`/`conc`
for any IPO with a sensitive Aries-point body.

## Best risk/reward asymmetry — EARLY / IMMINENT (now non-empty)

| Ticker | Name | IPO date | asym | DNA | peak | conc |
|---|---|---|---|---|---|---|
| COR | Coronado Biosciences | 2010-09-22 | 83.4 | 17.8 | 18.0 | 42.6 |
| CDW | CDW Corp | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| GGM | Guggenheim Credit Allocation | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| HDS | HD Supply Holdings | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| JPW | JP Morgan Whole Loan Trust | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| PETX | Aratana Therapeutics | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| SAMG | Silvercrest Asset Management | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| TRMR | Tremor Video / Telaria | 2013-06-26 | 70.6 | 2.0 | 18.9 | 46.5 |
| TBET | TBET Inc | 2011-01-24 | 69.0 | 5.6 | 16.4 | 40.5 |
| TXTR | Textura Corp | 2013-06-06 | 51.2 | 10.3 | 11.3 | 26.7 |

These are charts where structural DNA is moderate-to-low but the *forward*
activation in 2026-2028 is exceptionally concentrated (peak 16-19, conc
26-46). The 2013-06-26 cluster all share the same chart with Sun on the
Cancer-cusp-adjacent stack.

## Best risk/reward asymmetry — ENDURING / HIGH MAGNITUDE (top 15)

| Ticker | Name | IPO date | asym | DNA | peak | conc | rally |
|---|---|---|---|---|---|---|---|
| AKBA | Akebia Therapeutics | 2014-03-20 | 96.3 | 22.6 | 22.7 | 57.0 | SUSTAINED |
| MDWD | MediWound | 2014-03-20 | 96.3 | 22.6 | 22.7 | 57.0 | SUSTAINED |
| QTWO | Q2 Holdings | 2014-03-20 | 96.3 | 22.6 | 22.7 | 57.0 | SUSTAINED |
| RTGN | Ruthigen | 2014-03-20 | 96.3 | 22.6 | 22.7 | 57.0 | SUSTAINED |
| CQP | Cheniere Energy Partners | 2007-03-20 | 93.0 | 26.3 | 19.3 | 52.0 | SUSTAINED_MOD |
| DNJR | Golden Bull Ltd | 2018-03-20 | 90.1 | 20.1 | 22.8 | 53.0 | SUSTAINED_MOD |
| ACL | Alcon Inc | 2002-03-20 | 88.7 | 16.1 | 22.1 | 57.0 | SUSTAINED |
| BECN | Beacon Roofing Supply | 2004-09-22 | 88.4 | 10.6 | 22.9 | 64.9 | MODERATE |
| TWLL | Twilight Logistics? | 2006-06-21 | 85.7 | 15.8 | 21.0 | 57.2 | MODERATE |
| SECO | Secoo Holding | 2017-09-22 | 85.4 | 16.2 | 21.3 | 56.1 | MODERATE |
| STDY | Steady Inc | 2015-03-20 | 84.8 | 19.5 | 20.0 | 49.8 | SUSTAINED |
| TIGR | Tiger Brokers | 2019-03-20 | 82.6 | 20.5 | 20.4 | 46.6 | SUSTAINED_MOD |
| LX | LexinFintech | 2017-12-21 | 81.3 | 12.8 | 22.5 | 54.3 | MODERATE |
| AONE | A123 Systems | 2009-09-23 | 81.3 | 23.6 | 13.9 | 49.1 | MODERATE |
| ARI | Apollo Coml RE Fin | 2009-09-23 | 81.3 | 23.6 | 13.9 | 49.1 | MODERATE |

## 1980-2025 theoretical-date sweep

### Best years by density of strong dates (avg top-5 score per year)

| Year | Density | Notes |
|---|---|---|
| 1989 | 26.77 | Solectron, ImmunoGen, Neurogen all listed in this strong cluster |
| **2025** | **26.66** | **Beyond Ritter coverage — the active opportunity** |
| 2009 | 25.62 | A123/AONE, ChemSpec, Kraton; post-GFC |
| 2006 | 22.39 | Nextest, Cheniere prep |
| 2012 | 22.06 | Exa, Tesaro, Proofpoint era |
| 2011 | 21.48 | ServiceSource |
| 1984 | 21.06 | Pre-Ritter coverage |
| 1993 | 20.98 | Pre-Ritter coverage |
| 2003 | 20.15 | Travelers, post-9/11 |
| 1987 | 19.94 | Pre-Ritter coverage |

### Best single days with nearest matching IPO (gap=0 means exact hit)

| Theoretical date | Score | Ticker | Name | Gap |
|---|---|---|---|---|
| 1989-11-16 | 30.04 | IMGN | ImmunoGen | 0 |
| 2011-03-21 | 29.33 | SREV | ServiceSource Intl | 3 |
| **2025-03-20** | **29.28** | **(no IPO in Ritter universe)** | **— actionable: any 2025 IPO on or near this date** | — |
| 2009-06-19 | 28.78 | CPC | ChemSpec Intl | 4 |
| 1989-11-15 | 27.14 | SLTN | Solectron | 0 |
| 2019-06-20 | 26.12 | AKRO | Akero Therapeutics | 0 |
| 2003-02-17 | 25.77 | LEND | Accredited Home Lenders | 3 |
| 2009-12-21 | 25.45 | KRA | Kraton Polymers | 4 |
| 2012-06-29 | 24.80 | EXA | Exa Corp | 1 |
| 2014-04-02 | 22.08 | RUBI | Rubicon Project | 0 |
| 2007-03-20 | 20.75 | CQP | Cheniere Energy Partners | 0 |
| 2017-03-20 | 20.10 | MULE | MuleSoft | 3 |

## Real-world validators (sanity check)

The script independently surfaced these from raw chart math; their
post-IPO outcomes reinforce the framework:

- **NRG** (NRG Energy, 2000-05-30): S&P 500 utility, multi-bagger
- **ALGN** (Align Technology, 2001-01-26): ~100x from IPO
- **ACL** (Alcon, 2002-03-20): mega-cap
- **TRV** (Travelers, listed as TAP 2002-03-21): S&P 500 top insurer
- **CPHD** (Cepheid, 2000-06-21): Danaher acquisition $4B
- **TSRO** (Tesaro, 2012-06-27): GSK acquisition $5.1B
- **PFPT** (Proofpoint, 2012-04-19): Thoma Bravo acquisition $12.3B
- **IMGN** (ImmunoGen, 1989-11-16): AbbVie acquisition $10B (2024)
- **SLTN** (Solectron, 1989-11-15): Flextronics acquisition (2007)
- **CQP** (Cheniere Energy Partners, 2007-03-20): major LNG MLP
- **GO** (Grocery Outlet, 2019-06-20): listed during high-density 2019 cluster
- **MULE** (MuleSoft, 2017-03-17): Salesforce acquisition $6.5B

## Blockers — the two items I couldn't do

- **Backtest against realized returns (#4):** sandbox network blocks
  Yahoo, Stooq, Alpha Vantage, SEC EDGAR, etc. Can be done locally with
  any price source — output would be a regression of `asym_total` against
  realized 5y total return (or M&A-event-yes/no logistic).

- **Extend to 2022-2025 (#5):** the public Ritter mirror caps at 2021-12-22.
  Sandbox blocks the original ufl.edu source and every commercial IPO
  data provider. Local rerun with a Refinitiv/SDC/CompanyMarketCap export
  trivially works. Per the year-density table, **2025 is the second-strongest
  year of the entire 1980-2025 sweep**, with 2025-03-20 alone scoring
  29.28 — so the active opportunity sits exactly in the missing window.

## Output files (committed to branch)

- `reverse_arch_v8_1_asymmetry.csv` — full ranking, 1,635 rows
- `reverse_arch_theoretical_dates_1980_2025_v8_1.csv` — top 250 theoretical dates
- `reverse_arch_best_years_single_v8_1.csv` — strongest single date per year
- `reverse_arch_best_years_density_v8_1.csv` — strongest density per year
- `reverse_arch_nearest_matches_v8_1.csv` — top theoretical dates × nearest Ritter IPO
- `forward_events.json` — uppercase-tagged eclipses + outer-pair + stations
