# reverse_arch_v8_1_asymmetry — Ritter run

## Run setup

- Universe: 4,485 US IPOs from a public mirror of Jay Ritter's `IPO-age` dataset
  (`mborhi/IPO-Underpricing/data/IPO-age-clean.csv`, covering Jan 2000 – Dec 2021),
  plus the seven extras hardcoded in the script. After dropping shells and
  chart-compute failures: 4,379 effective.
- Forward events: generated from swisseph at runtime — 50 eclipses, 17
  outer-pair conjunctions/ingresses, 86 outer-planet stations across 2026-2036
  (saved to `/home/claude/forward_events.json`).
- Gate-passed: 1,635 IPOs.

## Distribution observations

- `asym_label`:
  - `ENDURING_HIGH_MAGNITUDE_ASYMMETRY`: 1,573
  - `BALANCED_ASYMMETRY`: 62
  - `EARLY_IMMINENT_ASYMMETRY`: 0
- `window`: IMMINENT 1,210 / SOONER 401 / MEDIUM 24
- `pre_cult`: LONGDATED 1,600 / IMMINENT 20 / 12M 14 / YEARS 1
- `rally_type`: SUSTAINED 551 / SPIKE 230 / TERMINAL_SPIKE 214 / MODERATE 548 / SUSTAINED_MOD 92

`EARLY_IMMINENT_ASYMMETRY` is empty by construction: the enduring engine has
`env=1.0 (RISING)` and `endurance=1.15 (waxing, age<150)` multipliers stacked,
while early gets the same `wax_bonus=1.0` cap. Whenever a chart is strong
enough to be IMMINENT, it is also strong enough that enduring×1.15×1.0 ≥
early×1.0×1.0, so the `if early >= enduring*1.15` branch never fires. To get
real `EARLY_IMMINENT` hits the script needs either `env<1` for waxing (it
doesn't, by design) or a stronger early-side multiplier when timing is in 2026.
This is a structural finding, not a data issue.

## Best risk/reward asymmetry — ENDURING / HIGH MAGNITUDE

### Pre-cult IMMINENT (DNA ≥ 22, window IMMINENT, peak ≥ 7 or conc ≥ 22)

| Ticker | Name | IPO date | asym | DNA | peak | conc | rally | archetype |
|---|---|---|---|---|---|---|---|---|
| AKBA | Akebia Therapeutics | 2014-03-20 | 91.0 | 22.6 | 12.6 | 46.9 | SUSTAINED | Saturnine |
| MDWD | MediWound | 2014-03-20 | 91.0 | 22.6 | 12.6 | 46.9 | SUSTAINED | Saturnine |
| QTWO | Q2 Holdings | 2014-03-20 | 91.0 | 22.6 | 12.6 | 46.9 | SUSTAINED | Saturnine |
| RTGN | Ruthigen | 2014-03-20 | 91.0 | 22.6 | 12.6 | 46.9 | SUSTAINED | Saturnine |
| PSIT | PSi Technologies | 2000-03-16 | 79.7 | 23.7 | 9.5 | 38.3 | SUSTAINED | Dionysian |
| UAXS | Universal Access | 2000-03-16 | 79.7 | 23.7 | 9.5 | 38.3 | SUSTAINED | Dionysian |
| CQP | Cheniere Energy Partners | 2007-03-20 | 70.6 | 26.3 | 10.7 | 43.4 | SUSTAINED_MOD | Orphic/Saturnine/Solar |
| IMGN | ImmunoGen | 1989-11-16 | 69.8 | 30.0 | 11.6 | 39.2 | SUSTAINED | Dionysian |
| NRGN | Neurogen | 1989-10-03 | 61.0 | 22.8 | 12.6 | 36.3 | SUSTAINED_MOD | Dionysian |
| AKRO | Akero Therapeutics | 2019-06-20 | 60.1 | 26.1 | 8.5 | 34.1 | SUSTAINED_MOD | Dionysian/Solar |
| GO | Grocery Outlet | 2019-06-20 | 60.1 | 26.1 | 8.5 | 34.1 | SUSTAINED_MOD | Dionysian/Solar |
| PRVL | Prevail Therapeutics | 2019-06-20 | 60.1 | 26.1 | 8.5 | 34.1 | SUSTAINED_MOD | Dionysian/Solar |
| AONE | A123 Systems | 2009-09-23 | 52.4 | 23.6 | 12.9 | 42.9 | MODERATE | Hermetic/Orphic |
| ARI | Apollo Coml RE Fin | 2009-09-23 | 52.4 | 23.6 | 12.9 | 42.9 | MODERATE | Hermetic/Orphic |
| CLNY | Colony Financial | 2009-09-23 | 52.4 | 23.6 | 12.9 | 42.9 | MODERATE | Hermetic/Orphic |

### Pre-cult 12M (DNA ≥ 20, window IMMINENT/SOONER, peak ≥ 6 or conc ≥ 18)

| Ticker | Name | IPO date | asym | DNA | rally |
|---|---|---|---|---|---|
| AVIV | Aviv REIT | 2013-03-20 | 85.9 | 21.1 | SUSTAINED |
| ENTA | Enanta Pharmaceuticals | 2013-03-20 | 85.9 | 21.1 | SUSTAINED |
| EXA | Exa Corp | 2012-06-28 | 81.2 | 20.2 | SUSTAINED |
| RUBI | Rubicon Project | 2014-04-02 | 72.9 | 22.1 | SUSTAINED |
| SLTN | Solectron | 1989-11-15 | 69.9 | 30.2 | SUSTAINED |
| NEXT | Nextest Systems | 2006-03-21 | 66.2 | 21.8 | SUSTAINED_MOD |
| TIGR | Up Fintech (Tiger Brokers) | 2019-03-20 | 60.5 | 20.5 | SUSTAINED_MOD |

### Notable real-world validators in the long-dated tail

The following all listed on dates the scorer flagged as high-asym, even though
their `pre_cult` is `LONGDATED`. They went on to become real cult / multi-bagger
or major-acquisition outcomes — useful as a sanity check on the chart logic:

| Ticker | Name | IPO date | asym | Outcome |
|---|---|---|---|---|
| NRG | NRG Energy | 2000-05-30 | 84.9 | S&P 500 utility, multi-bagger |
| ALGN | Align Technology (Invisalign) | 2001-01-26 | 72.6 | ~100x from IPO |
| ACL | Alcon | 2002-03-20 | 82.7 | Mega-cap eye-care |
| TAP | Travelers Property Casualty | 2002-03-21 | 77.0 | Became TRV, S&P 500 top insurer |
| CPHD | Cepheid | 2000-06-21 | 73.0 | Acquired by Danaher 2016, $4B |
| TSRO | Tesaro | 2012-06-27 | 76.5 | Acquired by GSK 2018, $5.1B |
| PFPT | Proofpoint | 2012-04-19 | 74.8 | Acquired by Thoma Bravo 2021, $12.3B |
| GOGO | Gogo Inc | 2013-06-20 | 72.0 | In-flight wifi, multi-cycle stock |

## Date-level read

The strongest asymmetry dates cluster on equinoxes/solstices because the
script awards a +2 equinox/solstice bonus and a Sun-on-Aries-Point bonus, and
because waxing JuNep ages 90-150 (rising synodic phase) get the highest base
multiplier:

| Date | Tickers that listed | DNA | asym |
|---|---|---|---|
| 2014-03-20 | AKBA, MDWD, QTWO, RTGN | 22.6 | 91.0 |
| 2013-03-20 | AVIV, ENTA | 21.1 | 85.9 |
| 2000-05-30 | NRG | 15.0 | 84.9 |
| 2010-06-21 | VRNG | 18.8 | 83.3 |
| 2002-03-20 | ACL | 16.1 | 82.7 |
| 2012-06-28 | EXA | 20.2 | 81.2 |
| 2000-03-16 | PSIT, UAXS | 23.7 | 79.7 |
| 2014-03-21 | AMBR, ATEN, BRDR, TSLX, VSAR | 13.7 | 77.4 |
| 2012-06-27 | TSRO | 15.7 | 76.5 |

## Caveats

1. Same-day IPOs share the same chart, so they tie on every chart-derived
   field. Differentiation between same-day tickers in this framework requires
   adding non-chart features (sector, size, listing-time intra-day).
2. The Ritter mirror covers 2000-2021 only. Pre-2000 and post-2021 must come
   from a different source.
3. Forward events were generated from swisseph here (no curated star/eclipse
   tags). If the operator has a hand-tagged `forward_events.json` (e.g. with
   "ALGOL_TOTAL_SOLAR" or "GREAT_AMERICAN" labels) it will produce different
   amplification on a small subset of charts.
4. The `EARLY_IMMINENT_ASYMMETRY` bucket is structurally unreachable in the
   current weighting; see distribution note above. If the operator wants
   non-empty early-imminent output, the `asymmetry_scores` early branch needs
   a multiplier bump or the enduring branch's `endurance=1.15` should be
   gated on `not IMMINENT`.

## Output files

- `/mnt/user-data/outputs/reverse_arch_v8_1_asymmetry.csv` — full ranking,
  1,635 rows × 34 columns
