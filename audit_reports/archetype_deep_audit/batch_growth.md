# Archetype Deep Audit — Growth / Inflection / Cyclical / BAB family

Auditor pass over 22 assigned archetypes. Firer counts from archetype_tags.csv;
fundamentals joined from asymmetry_global.csv (+ edgar_roic_roiic.csv for the
ROIIC family). Every claim below is from querying real firers.

Cross-cutting mechanical flaws found (each detailed under its archetype):
- **Base-effect gaming of "cheap-relative-to-growth" gates (PSG/EVSG).** A tiny
  revenue base producing rev_yoy of hundreds–thousands of percent makes
  psg = P/S ÷ growth% (and evsg) collapse into the "exceptional/cheap" window.
  The base-effect blow-up is not filtered — it is the thing that PASSES the gate.
  Hits cheap_sales_scaler, exceptional_evsg, tenbagger_path.
- **`oper_lev_any` is a near-tautology.** It fires if ANY of ~13 measures is
  merely >0 (incl. gross/op/ebitda/fcf margin delta, ttm-seq turns, raw-seq
  turns). "Operating leverage" as a gate carries little information; it is the
  loosest leg in wolf_trifecta/turnaround, cheap_sales_scaler, growth_algo,
  tenbagger_path, levered_inflection.
- **No sector guard.** Financials (banks/insurers/REITs/holdcos) and pre-revenue
  Health Care flow into P/S-, EV/Sales- and FCF-based growth rules where those
  measures are meaningless. ARR (a REIT) fired tenbagger with NEGATIVE revenue.
- **ebitda_margin data artifacts.** 200+ demand-shock firers have
  ebitda_margin > 60% (investment holdcos booking non-operating income as
  "EBITDA" on tiny revenue), producing >100pp "margin swings" read as leverage.

Note verified CLEAN: the ev_ebitda sign-fix holds — 0 firers anywhere have
ev_ebitda>0 while ebitda_ttm<0; the 562 genuinely-negative ev_ebitda names are
correctly excluded by the `>0` gates. Not a live problem.

---

## arch_fixed_cost_demand_shock  (N=4,549) — WORST OFFENDER

**Spirit:** a fixed-cost heavy-asset business hit by a demand shock whose volume
ramp flows through operating leverage into a shock-sized margin expansion.
**Rule gist:** `sector in HEAVY_ASSET_SECTORS & rev_accel>0 &
(ebitda_margin_delta_yoy>=0.02 | margin_shock_any)`.
**Worst false-positive pattern:** the growth leg is only `rev_accel>0`
(acceleration, not growth), so **1,086 firers (24%) have NEGATIVE rev_yoy** —
revenue is shrinking, merely decelerating its decline — the opposite of a demand
shock. Simultaneously the margin leg is gamed by data artifacts: **732 firers
have |ebitda_margin_delta_yoy| > 20pp and 230 have ebitda_margin > 60%**, which
are non-operating swings on tiny revenue, not leverage. Examples:
BMKS3.SA (Bicicletas Monark, rev $2.6M, ebitda_margin=740%, margin delta
+594pp, rev_yoy −11%), UMIYA.BO (rev $0.47M, margin delta +540pp), ENEFI.BD
(rev $1.1M, ebitda_margin 181%, rev_yoy −14%), LYK1.F / Parkmead (rev $4.7M,
ebitda_margin 267%, rev_yoy −29%), 0559.HK / DeTai New Energy (rev $4.3M,
ebitda_margin 110%, +324pp). 175 firers combine rev_yoy<0 AND rev<$20M.
**Robustness proposal:** (1) replace `rev_accel>0` with an actual growth floor
`rev_yoy >= 0.08` (a demand shock raises revenue); (2) add revenue base floor
`revenue_ttm >= 50e6` (fixed-cost leverage needs scale); (3) cap the margin leg
`ebitda_margin_delta_yoy.between(0.02, 0.20)` and require `0 < ebitda_margin <
0.5` so 100%+-margin holdco artifacts and one-off >20pp swings are excluded;
(4) require the margin move to coincide with rising revenue (leverage = margin
up *because* volume up), not falling revenue.

---
