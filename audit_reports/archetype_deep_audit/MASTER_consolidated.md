# Archetype Robustness — Consolidated Master (all 72 archetypes, 4 batches)

The 72 rules fail in a **small number of shared ways**. Fixing the shared root
causes with reusable guards cleans thousands of firers across many archetypes at
once. Ranked by impact. Every count verified against real firers.

---

## ROOT-CAUSE GUARDS (each a reusable helper fixing many archetypes)

### G1 — Sector exclusion (Financials / REITs / Utilities) from EV / net-cash / NCAV / margin / ROIC / coverage legs
Banks/insurers have EV massively negative (deposits/float), "net cash" = investment
portfolio, and margin/ROIC/coverage aren't comparable. **Highest single leverage.**
Cleans: negative_ev_value ~980, balance_sheet_return ~1,209 (Bank Central Asia EV
−93T reading as cash-rich), strong_coverage ~916, capital_returner ~1,468 (REIT/BDC
mandatory payouts), oak_asset_floor 459, liger_asset_backed 484, discounted_vehicle
309, tangible_value 94, large_cap_quality 94, tax_efficient 115, tenbagger_path 525,
wolf_seal 520, growth_algo 171. **~7,000+ firer-slots.**
→ helper `is_operating(sector)`; consider routing REIT NAV/payout into their own
archetypes rather than dropping.

### G2 — Denominator-sanity clamps
Tiny/negative denominators blow ratios up. Add: `net_cash_pct_mcap ≤ 1.0`;
`ebitda_margin ∈ (0, 0.6)`; ROIIC / cash-ROIC bands `[floor, 1.0]`.
Cleans one-off-EBITDA>100% (strong_coverage 151, large_cap_quality 11, cash_quality
33, fixed_cost_demand_shock 230 e.g. BMKS3.SA 740%), net-cash shells (strong_coverage
892), ROIIC blow-ups (below).

### G3 — Absolute-return floor BEFORE a ratio-of-changes counts
ROIIC = ΔNOPAT/ΔInvestedCapital is meaningless without positive base ROIC. Require
`roic_lindy ≥ 0.10 & n_yrs_positive_roic ≥ 4` before ROIIC qualifies.
Cleans: durable_reinvestment 141/504 (28%), cash_reinvest 284/633 (45%),
double_inflect 24% — capital-DESTROYING biotechs tagged durable compounders (Olema
ROIIC 2076%/ROIC −40%, ASP Isotopes 1441%/−110%).

### G4 — Revenue base floor + base-effect-resistant growth
Huge rev_yoy off a sub-$20M base (PADAMCO.BO +13,500×) is not scaling. Require
`revenue_ttm ≥ $20M` for growth-scaling archetypes and lean on 3y CAGR / per-share.
Cleans: tenbagger_path 712 (>100% yoy, 19% rev<$20M), cheap_sales_scaler 209,
exceptional_evsg 382, oak_order_conversion 846. Also fix PSG/EVSG denominators (the
base-effect artifact actively PASSES the cheap-vs-growth gate).

### G5 — Fix defaults that ADMIT
`n_analysts` NaN→0 = "maximally neglected" (liger_lagging_inflect: 75% of firers,
incl. Alphabet/Tencent/SAP); `notna()` guards that pass on literal 0.0 stale tape
(narrative_lag 518). Treat missing as "unknown → fails the gate."

### G6 — Restore guards the comments promise but the code dropped
- kpi_threshold: comment says "investable scale", NO mcap gate → 851 firers <$10M,
  1,051 lossmaking penny shells (SECI $30). Add `mcap ≥ $50M`.
- strong_coverage: only 8.8% have real coverage; require `interest_coverage ≥ 8` for
  the coverage claim (not net-cash proxy). 89% of 8,856.
- capital_discipline: 91.5% pass on `insider ≥ 0.20` alone → require an ACTION leg
  (buyback/negative shares) or pair insider with ROIC/FCF. 3,355/3,667.
- analyst_awakening: 1,551 (38%) fire with NO consensus rating on price-target
  optimism alone (speculative biotech). Require a real rating.
- evsales_derating: "not a trap" passes on gross_margin≥0.20 alone → 393 cash-burners;
  add size floor + FCF/EBITDA sanity.
- dead_option: no optionality signal at all — just a cheap FCF cow. Add a real
  optionality/catalyst signal or fold in.
- oak_asset_floor: no survivability gate → 737 double-burners melting the "floor"
  cash. Add `fcf>0 | cfo>0`.
- liger_lagging_inflect: no mcap ceiling → add `20e6–400e6` (siblings have it).

### G7 — BAB beta repair
Raw `yf_beta ≤ 0` (illiquid/stale) laundered by shrinkage into 0.40 → passes "low-beta
quality". bab_low_beta 628, bab_multibagger 623 (incl. clinical biotech, BioArctic
beta −0.69). Require `yf_beta ≥ 0.20` raw + a liquidity floor.

### G8 — Operating-leverage tautology + demand-shock sign
`oper_lev_any` is a near-tautology; a 20pp one-off margin swing isn't operating
leverage; 24–33% of fixed_cost_demand_shock / regime_cyclical firers have NEGATIVE
rev_yoy (declining, not a demand shock). Replace `oper_lev_any` with
`oper_lev_score ≥ 0.3`; require positive rev_yoy for demand-shock.
fixed_cost_demand_shock is the WORST growth rule (N=4,549).

### G9 — Near-noise value screens
narrative_lag fires on 29.3% of the universe (flat_or_down alone = 43.5%); lynch_evgy
23.5% (sales fallback admits negative-EBITDA: IKGR.MI −0.7%; 2,024 near-zero-EV
denominator). Tighten both toward their spirit (real lag/coverage signal; drop the
sales fallback for negative-EBITDA; guard the EV denominator).

### G10 — Reverse-split guard
`shares_growth < −0.30` in one period is a split/restructuring, not a buyback.
no_dilution 16 (IMPP −72%, BRLT −85%), buyback_compounder 18. Require buyback_yield
corroboration or reject.

---

## VERIFIED CLEAN (no change)
ev_ebitda sign-fix (0 artifacts anywhere — this session's fix confirmed working),
templeton_pessimism, oak_deep_value, oak_nav_discount (Financials-only by design),
oak_deleveraging, asymmetric_assembly, oak_resource_leverage, wolf_emerging,
wolf_compounder, owner_operator, quiet_compounder, low_sbc_quality, insider_conviction
(core sound), concentrated_segments, diversified_segments, lynch_reward, qarp,
bab_becoming, midcap_garp, levered_inflection.

## Suggested implementation order (each measurable + gets a methodology check)
1. **G1 sector guard** + **G2 clamps** — two reusable helpers, biggest cleanup.
2. **G3 ROIC floor** for the ROIIC compounder rules.
3. **G6 restored guards** (size floors, real coverage, action legs) — many archetypes.
4. **G4 growth base floor** + PSG/EVSG denominator fix.
5. **G5 defaults**, **G7 beta**, **G8 oper-lev**, **G9 near-noise**, **G10 split** — remaining.
