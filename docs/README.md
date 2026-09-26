# Documentation index

## FMP (Financial Modeling Prep) enrichment analysis

Two analysis documents cover how FMP's endpoints enrich the archetype
framework. Both are committed here.

- **[FMP_ENRICHMENT_MAP.md](FMP_ENRICHMENT_MAP.md)** — leverage table (which
  recurring coverage gap unblocks which whole theme), a per-archetype map for
  all ~160 screens, and 14 nuanced second-order enrichments (income quality as
  an accrual signal, R&D intensity vs SG&A waste, capex/depreciation regime,
  DuPont burdens, estimate dispersion, institutional accumulation, true revenue
  geography, dividend-cut detection, and more).

- **[FMP_DEEP_EXAMINATION.md](FMP_DEEP_EXAMINATION.md)** — every measure's
  spirit → FMP mapping, synthesized from four theme analyses (dynamic;
  value + capital-allocation; quality + analyst; forensic + segment + events),
  with the honest three-tier forensic fillability verdict (footnote items —
  LIFO, pension, DTA, NOL, RPO, equity-method fair value, segment margin —
  stay EDGAR-only).

### Central conclusion
The biggest remaining win is consuming FMP's multi-period statement endpoints
(income / balance / cash-flow / growth / enterprise-values / dividends),
verified-available but not yet fully wired, to replace the US-only EDGAR
streaks and lindy metrics, the noisy Yahoo quarterly-sequential engine, the
~4-5%-covered capital-return snapshots, and the synthetic EV/sales
reconstruction — extending ~40 quality and forensic archetypes to the ~29k
non-US names. `fmp_dynamics.py` already pioneers that spine for the dynamic
(evolution / step-change / inflection / streak / unrerated) archetypes.

### Implementation modules
- `fmp_client.py` — hardened FMP `/stable` client with a compressed, negative-
  caching, size-capped disk cache.
- `fmp_enrich.py` — universe-wide bulk + per-symbol enrichment → `fmp_enrichment.csv`.
- `fmp_dynamics.py` — per-symbol multi-period trajectory pack → `fmp_dynamics.csv`.

All FMP signals are secondary, source-tagged (`fmp_`-prefixed), surfaced as
confirming/disqualifying flags — never hard vetoes, and never overwriting an
EDGAR-primary value.
