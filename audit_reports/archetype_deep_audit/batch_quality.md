# Quality / Compounder / Capital-Return Family Archetype Audit

Counts verified vs archetype_tags.csv × asymmetry_global.csv (46,526) + EDGAR ROIC.
Worst-first.

### 1. arch_strong_coverage — 8,856 firers (WORST / highest count)
Spirit: debt trivially serviceable (interest coverage). Rule: `ic>=8 OR nde<=0 OR
net_cash_pct>=0.20`, guarded ebitda>0. FP: only **777 (8.8%)** have real ic>=8;
**7,872 (89%)** pass on net-cash proxy. Admits (a) **892 neg-EV shells** (net_cash>1:
Cocoon 5.5x); (b) **916 Financials/RE/Utilities** (nde meaningless); (c) **151 with
EBITDA margin >100%** (MDX.BK 168%, Kamanwala 293% — one-off asset-sale EBITDA). Fix:
coverage leg requires real ic>=8; net-cash leg cap net_cash_pct<=1.0; ebitda_margin
in (0,0.6); mcap>$50M; exclude Financials/RE/Utilities.

### 2. arch_capital_discipline — 3,667 firers
Spirit: founder/insider-aligned capital-ALLOCATION discipline. FP: **3,355/3,667
(91.5%)** pass via `insider>=0.20` ALONE (no buyback/share evidence); high insider
ownership is ubiquitous in family-controlled Asia/Europe, not discipline. No ROIC
filter; 472 have negative FCF yet "disciplined" (Chen Hsong fcf −16%, insider 72%).
Fix: require an ACTION leg (shares_growth<=-0.01 or buyback_yield>=0.02), or pair
insider with roic>=0.10 or (fcf>0 & n_yrs_fcf>=3); clamp ebitda_margin<0.6.

### 3. arch_durable_reinvestment (504) + arch_cash_reinvest (633) — HIGH
Spirit: Mauboussin durable compounder (sustained high incremental ROIC). Rule:
`roiic_lindy>0.15 & asset_3y_cagr>0.05`. FP: ROIIC explodes on tiny denominator, NO
guard that absolute ROIC is positive. **141/504 (28%) have roic_lindy<0** (34% incl
NaN); cash_reinvest **284/633 (45%)**. Capital-DESTROYING biotechs tagged durable:
Olema OLMA (roiic 2076%, roic −40%), ASP Isotopes ASPI (roiic 1441%, roic −110%),
Warby Parker (roiic 1275%, roic −64%), Deep Fission (asset_3y_cagr 6,999% shell).
Fix: `roic_lindy>=0.10 & n_yrs_positive_roic>=4` first; cap roiic_lindy in [0.15,1.0];
asset_3y_cagr<2.0.

### 4. arch_capital_returner — 4,119 firers
Spirit: Greenblatt total yield (div+buyback) funded by FCF. FP: **3,670 (89%)** clear
on dividend alone (buyback<1%) — a high-div screen. 30% cap too loose: **176 yield
>15%** (Sheh Kai 29.6%, stale-price/special). **1,468 (36%) Financials/RE** (REIT/BDC
mandatory payouts). FCF guard is sound. Fix: yield ceiling ~15%; require buyback leg
to contribute or flag dividend-only; split REIT/BDC out.

### 5. arch_tax_efficient — 649 firers
Spirit: structural tax efficiency, not loss-driven. FP: pretax>0 guard blocks losers
but not one-offs — **106 ETR<1%** (NOL release/credit); **115 REITs** near-zero-tax by
pass-through. Fix: etr>=0.03 lower bound; multi-year mean ETR; exclude Real Estate.

### 6. arch_cash_quality — 405 (moderate)
Better guarded (roic_lindy>0) but ratio blowup: **33/405 cash_roic>100%** (PaySign 248%
vs roic 1.1%). Fix: cap cash_roic_lindy<=1.0; bounded gap.

### 7. arch_buyback_compounder — 273 (moderate)
Well-gated but shrink leg can't tell buyback from reverse split — **18 with >30% 5y
drops** (Wetouch −59%, J.Jill −65%/5y but +23%/3y). Fix: require buyback_yield>0
corroboration or reject shares_growth<-0.30 as split artifact.

### 8. arch_large_cap_quality — 890 (mostly clean)
94 Financials/RE (nde/margin don't translate: APO nde −31); 11 EBITDA margin >100%
(Futu 134%, HKEX 115%). Fix: clamp ebitda_margin<1.0; exclude financials from
margin/leverage gates.

### 9. lindy_fcf (1,126), lindy_margin (1,002), lindy_growth (274), no_dilution (814)
Mostly clean (multi-year counts). Systemic caveat: median years_of_history only **6.0**
— "durable/multi-cycle" rests on a post-2018 bull window. lindy_fcf admits 65 shrinking
cos (rev_5y_cagr<0); no_dilution catches 16 reverse-split drops (IMPP −72%, BRLT −85%).
Fix: require years_of_history>=5 on lindy_fcf; non-shrinking guard (rev_5y_cagr>-0.05);
reject split-scale drops in no_dilution.

### 10. arch_insider_conviction — 919 (clean-ish)
Sound (open-market Form-4 cluster + value gate). Soft: value gate nearly always true;
37% Financials/RE (routine bank/BDC insider buys near book). Leave largely as-is.

### Clean
arch_wolf_compounder (367, only 17 low-base rev_yoy>300%), arch_owner_operator (115),
arch_quiet_compounder (27), arch_low_sbc_quality (1,558, US-biased coverage only).

## Top-5 highest-impact
1. strong_coverage: require real interest_coverage>=8 for the coverage claim; cap
   net_cash<=1.0; clamp ebitda_margin<0.6; exclude Financials/RE/Utilities (~89% of 8,856).
2. durable_reinvestment/cash_reinvest: roic_lindy>=0.10 & n_yrs_positive_roic>=4 floor,
   cap roiic_lindy<=1.0 (removes 28%/45% capital-destroying firers).
3. capital_discipline: require an action signal or pair insider with ROIC/FCF gate
   (dissolves 3,355/3,667).
4. capital_returner: yield ceiling ~15%; split REIT/BDC mandatory payouts out.
5. UNIVERSAL: `0<ebitda_margin<0.6` one-off guard + drop Financials/RE/Utilities from
   every margin/ROIC/coverage archetype.
