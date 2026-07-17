# RCA / Assembly-Theory Audit of the Reverse-Arch Pipeline

Method: the system was decomposed into its assembly chain — each layer only
trusted after its sub-assemblies verified — and probed with 53 empirical
checks (`rca_audit.py`). Layers:

```
L1 primitives (orb, midpoint, aspects, DST, percentile)
  -> L2 chart assembly (planets, angles, syzygy, flags)
    -> L3 natal scoring (robust/semi/spec/era)
L4 event builder (eclipses, conjunctions, ingresses, stations)
    -> L5 forward scoring incl. Silas overlay
      -> L6 classification / normalization / asymmetry
        -> L7 downstream scripts + data integrity
```

Result before fixes: **46 PASS / 7 FAIL / 6 WARN** (one FAIL was a probe
defect, not code). After fixes: 51 PASS at code level; the two remaining
FAILs were staleness of the pre-fix v3 CSV, cleared by the v4 regeneration.

## Ground-truth anchors that PASSED (what we now know is right)

- DST handling: winter opens 14:30 UT, summer 13:30 UT (zoneinfo correct).
- Planetary longitudes vs independent recomputation; Sun lon 2000-01-03
  = 282.5 (catalog ~282).
- **External cross-validation against Kate Silas's own published chart
  data**: our GME 2002-02-12 chart gives Mars 17.85° Aries (she publishes
  "18 degrees Aries"); our AAPL 1980-12-12 chart gives Uranus 27.4° Scorpio
  (she publishes the 2022 lunar eclipse at ~25° Scorpio conjunct natal
  Uranus, orb ~2°). Two independent practitioners' ephemerides agree.
- All 12 spot-checked eclipses 2026-2035 match the public catalog by date
  and class; the 2026-08-12 eclipse longitude equals the Sun's longitude
  independently recomputed (140.04 vs 140.05).
- Saturn-Neptune conjunction found at 2026-02-20, 0.75° Aries — and matches
  the hardcoded `SAT_NEP_DEG = 0.75` constant used in natal scoring.
- Station events bracket a real speed sign-flip (Neptune Rx 2026 verified).
- Pre-natal syzygy within one lunation behind natal Sun; equinox flags fire
  on 0° Aries; Sun sits above the eastern horizon in 9:30 charts.
- score_forward is deterministic, produces no duplicate hits, and the
  eclipse-Sun M&A flags are all ≤1° as specified.

## Confirmed defects and fixes

| ID | Layer | Defect | Root cause | Fix |
|---|---|---|---|---|
| F1 | L4 | 2031-11-14 hybrid (annular-total) eclipse typed bare `solar`, base 5 instead of 10 | builder tested `ECL_TOTAL`/`ECL_ANNULAR` bits only; hybrids return `ECL_ANNULAR_TOTAL` | builder treats hybrid as total; events regenerated |
| F2 | L5 | `position_by` anchored to ANY ≥3-pt hit — in practice the 2026-01-26 Neptune ingress, making 288 rows share one date | Silas's 6-week rule is an *eclipse* rule; ingress events dominated the earliest-hit slot | anchor restricted to eclipse hits |
| F3 | L7 | Ticker-recycling collisions: **Snowball.com (2000)** and **Intrawest (2014)** excluded as "Snowflake"; **Converted Organics (2007)** as "Coinbase"; **NuPathe (2010)** as "UiPath"; **Shopping.com (2004)** as "Shopify"; **Fortress (2007)** as "Figma" | `DEFAULT_ALREADY` matches on bare ticker; tickers are reused across decades | `ALREADY_MIN_DATE` era gate + `is_already_cult(ticker, date)`; 5 wrongly-dropped companies re-enter the universe |
| F4 | L5/L7 | As-of leakage: solar-arc and progressed-Moon scans hardcode 2026-2036 and ignored the as-of cutoff, so time-shifted runs (delta/inflect t1) counted **past** hits in peak/conc/window | `score_forward` had no as-of concept; downstream scripts filtered only the events dict | `score_forward(..., as_of=)` filters all hits incl. progressed; scripts pass their cutoff |
| F5 | L7 | Stale `T0 = date(2026, 5, 4)` in delta/inflect — 10 weeks behind today | constant baked in at first run | `RA_ASOF` env, default `date.today()` |
| F6 | L7 | 1,185 of 1,635 `position_by` dates already in the past; 2 eclipses already past counted in "current" rankings | consequence of F2+F4+no as-of in main run | main run now passes `as_of` (env `RA_ASOF`, default today); v4 regenerated |
| F7 | L7 | Universe silently collapsed to the 7 hardcoded extras when `/home/claude/ritter_full.csv` vanished on container reset — run "succeeded" with Universe=7 | `load_ipos` treats missing paths as empty, no minimum-size guard | `main()` aborts loudly when universe <100 or the eclipse stack is empty |

One audit FAIL was a probe defect: the EARLY label reachability grid missed
the narrow qualifying region; production CSVs contain all three labels, and
the check now reads them empirically.

## Known design quirks retained (WARN, deliberate)

1. `MP MoPl=Moon` midpoint check only fires when Moon is within ~3° of
   Pluto — duplicates the MoonPlu conjunction score (inherited from the
   original draft; harmless double-count of a rare configuration).
2. 30% step discontinuity in eclipse points at exactly 1.0° orb (the TIGHT
   kicker). Monotonicity across the boundary verified — a 0.99° hit always
   outscores a 1.01° hit — but the jump is a modeling choice.
3. Eclipse-to-ASC/MC hits use the assumed 9:30 chart time (documented; Silas
   would require a verified first-trade time before trusting angle hits).
4. Neptune-return window hardcodes 2026-2036 in `compute_chart` (natal-side
   flavor flag; low impact).
5. `sweep_theoretical_dates` iterates weekday calendar days, including
   exchange holidays (theoretical dates only; nearest-match tolerates it).
6. BARBAULT table (2024-2030 RISING) vs Silas/McWhirter mid-2026 bearish
   node-cycle bottom — a documented modeling disagreement, not a bug.
7. GREAT/ALDEBARAN amplifier keys: `GREAT` never occurs in generated event
   types (dead branch retained for hand-tagged event files).

## Coverage gaps (missing, not broken)

- Universe: 2000-2021 only (public Ritter mirror). Pre-2000 and 2022-2026
  IPOs absent — and the sweep says 2025 is the second-strongest year since
  1980, exactly in the gap.
- No realized-outcome backtest (sandbox blocks all price sources).
- Same-day IPOs share charts; differentiation needs non-chart features.
- Multi-pass transit modeling (Silas F6 from SILAS_METHOD_NOTES) not yet
  implemented; single-date events only.
- `sector_resonance.csv` regenerates from the inflect output; rerun after
  any rescoring for consistency.

## Verification loop

`python3 rca_audit.py` re-runs all 53 checks; keep it green after any
scoring change. Regeneration order: `build_forward_events.py` →
`reverse_arch_v8_1_asymmetry.py` (RA_ASOF=today) → `asym_delta_18m.py` →
`asym_curve_inflect.py` → `sector_resonance.py`.
