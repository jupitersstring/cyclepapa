# Trend / Momentum Trader Archetypes — O'Neil, Weinstein, Kullamägi

Three new archetypes translate the published methodologies of William O'Neil
(CAN SLIM), Stan Weinstein (Stage Analysis) and Kristjan Kullamägi into
systematic **setup detectors**, following the hierarchy you specified:
hard gates → continuous quality score. Rules are labelled in the code:
**[C]** canonical (author-stated), **[P]** proxy (our formalization of a
qualitative rule), **[R]** research parameter (author gives no cutoff).

## The fidelity boundary (read this first)
These three traders run **technical/price-action** systems on **daily and
intraday** bars. This database persists **weekly-derived** price signals
(returns over 6/12m, 52-week-high proximity, relative-strength-line highs,
volatility-squeeze runs, base depth) plus **fundamentals** — the raw daily
OHLCV and volume were fetched transiently and **not stored**. Therefore:

- **Captured here (the screening layer):** leadership / relative strength,
  size of the prior advance, proximity to new highs, relative-strength-line
  new highs, consolidation tightness (volatility squeeze / base depth), and —
  for O'Neil — the CAN SLIM fundamentals.
- **NOT computable here (the execution layer), so deliberately omitted rather
  than faked:** ADR/ATR stops, RVOL / breakout volume, base-geometry range
  contraction & volume dry-up (VDU), MA-surfing (% closes near rising 10/20
  DMA), opening-range-high triggers, position sizing, and the exit
  state-machines. These need a live daily + intraday feed.

So each archetype flags a name whose **weekly structure and fundamentals match
the setup**; the precise trigger/stop/sizing/exit must be run downstream on
live bars. ~34,475 names carry a live enough tape to be screened.

## arch_oneil_canslim (390) — CAN SLIM leader
Hard gates: **C** strong/accelerating current earnings (EPS-growth streak ≥2
quarters [C], or revenue +20% YoY as the global proxy where EDGAR EPS is
absent); **A** durable annual quality — ROE/ROCE ≥ 15% [C, ~17% target] with
positive-earnings share; **N** new price high (within 15% of the 52-week high,
or at it) [C]; **L** relative-strength leader (RS percentile ≥ 80) [C]. Score
adds earnings-acceleration. **Not modelled:** I (institutional sponsorship
*quality/trend*), M (market follow-through regime), S (breakout *volume*) —
they need ownership, index-regime and volume feeds not present.

## arch_weinstein_stage2 (4,403) — Stage 2A / early Stage 2
Hard gates: price advancing above its long trend into an upper multi-year
range [P — the 30-week MA slope isn't available; proxied by 12m momentum > 0
and upper 5-year-range position]; strengthening relative strength via the
RS-line 52-week high [P for the Mansfield zero-line, which Weinstein himself
notes was proprietary]; **little overhead resistance** — near the 52-week/
all-time high [C concept]; and NOT Stage 4. Per the corrected reading, MRS>0
is **not** required (improving RS below zero is allowed) and no Stage-1 volume
dry-up is imposed (Weinstein explicitly rejects that). **Not modelled:** exact
30-week MA slope, breakout-volume confirmation (spike-or-buildup),
age-weighted overhead-supply profile, investor-vs-trader entry split.

## arch_kullamagie_breakout (1,163) — common breakout setup
Hard gates: **leader** across momentum scans (6- or 12-month return percentile
≥ 95) [P — his exact 1/3/6-month scans; horizons approximated]; **large prior
advance** ≥ 30% [C]; **orderly tightening** — a volatility squeeze or a
shallow/contained 12-month base [P concept, R thresholds]; **consolidating
just below highs** (2–25% off the 52-week high) [P]. Score weights leadership,
impulse magnitude (capped so a +1000% move doesn't dominate), tightness,
proximity to highs and relative strength. **Not modelled** (his execution
core): the opening-range-high trigger, low-of-day stop within 1 ADR, the 3–5
day partial + 10/20-day-MA trail, and the separate Episodic-Pivot and
Parabolic-Short setups (EP needs intraday gap + early-volume; Parabolic Short
is a different, mean-reversion family).

## Notes on the corrected reading (incorporated)
- Kullamägi's true ADR = mean(H/L)−1 — noted; not computable without daily H/L,
  so tightness uses the persisted volatility-squeeze signal instead.
- O'Neil annual earnings judged on **sequence + ROE**, not a lone CAGR.
- Weinstein: no mandatory Stage-1 volume contraction; RS *improving* (not >0)
  suffices; big prior advance is positive information, not just "extension."
- These are **not** blended into one 0-100 score with the other archetypes'
  measures — they stand as their own setup detectors, exactly because a high
  fundamental score must not override a failed technical gate (and vice versa).

## What a full implementation would need
A daily+intraday OHLCV store per name. With it, the execution layer (ADR/ATR,
RVOL, base contraction/VDU, MA-surfing, ORH triggers, stops, sizing, exit
FSMs) and the missing setup families (EP, Parabolic Short/Long, high-tight
flag, cup-with-handle/flat-base/double-bottom geometry, Weinstein
triple-confirmation) become buildable. That is a separate daily-data pipeline,
not a fundamentals-master screen.
