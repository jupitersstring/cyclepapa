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

## arch_bab_low_beta (N=4,739) & arch_bab_multibagger (N=5,683)

**Spirit:** Frazzini-Pedersen BAB long side — genuinely low market-beta,
high-quality, boring-safe businesses whose cash flows can be safely levered.
**Rule gist:** `beta_present & beta_shrunk<=0.85 (low_beta) / <=1.0 (multibagger)
& bab_quality`, where `beta_shrunk = 0.6*clip(yf_beta,-0.5,4)+0.4` and
multibagger adds a loose leg `(yart_score>=0.60 | inflection_print | rev_accel>0.05)
| cheap_leg`.
**Worst false-positive pattern:** the shrinkage does not fix an
**illiquidity/non-synchronous-trading beta artifact** — it launders it.
**628 low_beta firers (13%) and 623 multibagger firers have raw yf_beta <= 0**;
another ~1,600 have 0<beta<0.3. A near-zero/negative raw beta on a thinly-traded
name is spurious (stale prices), not genuine defensiveness — yet beta_raw=0
shrinks to exactly 0.40 and sails under the 0.85 gate. These beta<=0 firers are
concentrated in the least-liquid markets: India BSE (100), Japan (46),
Indonesia (36), Taiwan (30), China (30). Examples: KCLINFRA.BO (India, beta
−0.37, mcap $1.9M), STELLAR.BO (beta −0.44, mcap $1.6M), LongiTech 1281.HK
(beta −1.01, mcap $17M), BioArctic B9A.F (clinical biotech, beta −0.69) — a
pre-commercial biotech is the antithesis of "boring safe low-beta quality."
median raw beta among low_beta firers is only 0.32.
**Robustness proposal:** (1) require a real liquidity floor (ADV or
`pew_avg_dollar_volume >= $100k/day`, or a minimum price and free float) before
trusting beta; (2) treat non-positive raw beta as UNUSABLE, not ultra-low —
gate on `yf_beta >= 0.20` (or require beta estimated over a minimum # of weekly
observations) so stale-price zeros are dropped rather than rewarded; (3) exclude
pre-revenue Health Care from a "quality" bucket; (4) tighten the multibagger
loose leg — `rev_accel>0.05` / a single interval inflection should not by itself
certify "embedded compounding," require `yart_score>=0.60` OR the genuine
cheap_leg.

## arch_bab_becoming (N=2,623) — mostly sound

Beta band is 0.85–1.15 (shrunk), so the beta<=0 artifact does NOT reach it
(0 firers with beta<=0). De-risking leg is loose (`ebitda_margin_delta>=0.01 |
interval_inflect_any`) but the archetype is explicitly a "trending toward"
signal and the nde<=3 + fcf/margin gate keeps quality. Minor: add the same
liquidity floor for consistency. Otherwise clean.

---

## arch_tenbagger_path (N=3,983)

**Spirit:** a small/mid business whose durable, operating-leverage-confirmed
growth makes a 10x total return arithmetically credible on a sane sales multiple.
**Rule gist:** `mcap<10e9 & 0<p_s<30 & g10>=0.15 (median of growth bases) &
(>=2 bases confirm) & op_lev_confirm & viable_econ & implied_10x>=10`.
**Worst false-positive pattern:** **base-effect growth + near-zero-P/S
artifacts.** 774 firers (19%) have rev<$20M and **712 (18%) have rev_yoy>100%**.
A shell restarting looks like the world's best compounder: PADAMCO.BO (rev
$6.5M, rev_yoy 13,497%), AVIVA.BO (rev_yoy 2,562%), MBO.V (1,630%), FLCX/flooidCX
(rev_yoy 1,679%, **p_s 0.002** — a near-zero-P/S artifact that makes implied_10x
explode), GXAI/Gaxos.AI (rev_yoy 922%, op_margin −249%). The g10 cap at 0.50 and
the `_g_confirmed` two-base rule do NOT help when both rev_yoy and rev_3y are
inflated by the same crushed base. **Sector contamination:** 525 Financials
fire a P/S-based 10x rule that is meaningless for banks/REITs/holdcos —
ARR/Armour Residential REIT fired with **negative revenue (−$128k)** and
rev_yoy 926%.
**Robustness proposal:** (1) revenue base floor `revenue_ttm >= 25e6`;
(2) organic-growth guard — cap the per-base growth used in g10 at e.g. 60% and
require rev_3y_cagr (multi-period, base-effect-resistant) itself >= 0.15 rather
than accepting a single explosive yoy; (3) raise the P/S lower bound to ~0.30
and require `ev_sales` corroboration to kill p_s=0.002 artifacts; (4) exclude
Financials/Real Estate (P/S non-comparable) and drop any name with
revenue_ttm<=0.

---

## arch_cheap_sales_scaler (N=3,193)

**Spirit:** an un-re-rated scaler — cheap on sales AND cheap relative to its
growth — with improving operating margins, at/near profitability.
**Rule gist:** `mcap<5e9 & 0.10<=p_s<=2.0 & rev_yoy>=0.10 & psg in [0.005,0.10]
(or evsg analog) & oper_lev_any & near_profit`.
**Worst false-positive pattern:** the **PSG gate is gamed by base effects** — a
crushed-base revenue explosion makes psg = P/S ÷ growth% tiny and thus "cheap
relative to growth," so the artifact actively passes the discriminating gate.
223 firers have rev<$10M; 209 have rev_yoy>100%: AVIVA.BO (rev_yoy 2,562%,
psg 0.024), MBO.V (1,630%, psg 0.008), CONSTRONICS.BO (1,159%, psg 0.011) —
all tiny Indian BSE / micro names. Separately, `near_profit` (op_margin>=−0.15
OR ebitda>0 OR just-crossed) still admits **275 firers with op_margin<−5%**
(e.g. KAMANWALA −58%, BioStem −145%, WITHTECH −26%) — "cheap because melting."
267 Financials also fire.
**Robustness proposal:** (1) revenue base floor `revenue_ttm >= 20e6`;
(2) compute the PSG denominator from a base-effect-resistant growth
(rev_3y_cagr, or capped rev_yoy) so a 2,500% print can't manufacture a 0.02 PSG;
(3) tighten near_profit to require actual proximity to breakeven
(`op_margin >= -0.05` OR a genuine first-positive print), not a −15% floor;
(4) exclude Financials.

---

## arch_exceptional_evsg (N=1,883)

**Spirit:** a fast grower priced at an exceptionally low EV/sales relative to its
growth (capital-structure-neutral PSG analog).
**Rule gist:** `mcap<20e9 & evsg in [0.002,0.05] (or psg analog) & rev_yoy>=0.20
& 0.15<=ev_sales<=4.0 & light quality`.
**Worst false-positive pattern:** identical EVSG base-effect gaming — 201 firers
have rev<$10M; 382 (20%) have rev_yoy>100%. PADAMCO.BO (rev_yoy 13,497%, evsg
0.0187), AVIVA.BO (2,562%, evsg 0.018), KAKTEX.BO (2,371%, evsg 0.015), FLCX
(1,679%, evsg 0.006) all sit inside the "exceptional" window BECAUSE growth is
astronomical. The "light quality gate" (`ebitda>0 | fcf>0 | op_margin>=−0.15`)
still lets **346 firers with op_margin<0** through, plus 194 Financials.
**Robustness proposal:** same as cheap_sales_scaler — revenue floor, cap the
growth feeding evsg / require rev_3y_cagr corroboration, tighten the quality
gate to positive EBITDA or a real profit inflection, exclude Financials.

---

## arch_growth_algo (N=823)

**Spirit:** the $DLO flywheel — gross-profit growth + operating leverage +
buybacks compounding into cheap-on-EV/FCF FCF/share growth.
**Rule gist:** `mcap<50e9 & rev_yoy>=0.15 & oper_lev_any & fcf>0 &
(fcf_yoy>=0.20 | fcf_ps_yoy>=0.20 | cfo_yoy fallback) & 2<=ev_fcf<=15 &
not_diluting`.
**Worst false-positive pattern:** the fcf>0 + ev_fcf gates make it tighter than
its siblings, but **171 firers (21%) are Financials** — banks/insurers where
"FCF" and "EV/FCF" are not economically meaningful: SiriusPoint (insurer, rev
$3B), Sawada Holdings, CITBA Financial, Alpha Astika. Also 100 firers rev_yoy>100%
(base effect) and 100 with op_margin<0.
**Robustness proposal:** (1) exclude Financials/Real Estate (FCF/EV-FCF
undefined); (2) base floor `revenue_ttm>=20e6` and cap the rev_yoy contribution;
(3) require the operating-leverage leg to be a genuine confirmed move
(`oper_lev_score >= 0.3`) rather than `oper_lev_any`.

---

## arch_regime_cyclical (N=2,638)

**Spirit:** a heavy-asset cyclical crossing a regime change (real margin/cash
inflection), beaten down, mispriced as dead.
**Rule gist:** `sector in HEAVY_ASSET_SECTORS & beaten_down_any(0.20) &
(ebitda_inflection|ebitda_first_pos|ebitda_margin_delta>=0.02|margin_shock_any) &
not_priced_in>0.20`.
**Worst false-positive pattern:** same margin-artifact problem as its C5 sibling —
**872 firers (33%) have rev_yoy<0** (declining, so any "regime change" is a dead-
cat margin blip, not a demand-driven turn) and **107 have ebitda_margin>60%**
(holdco/non-operating artifacts producing spurious >20pp margin swings: 555 firers
have |margin delta|>20pp). 568 firers have rev<$20M, 210 combine rev<$20M with
rev_yoy<0.
**Robustness proposal:** cap the margin leg to a plausible band
(`ebitda_margin_delta_yoy.between(0.02,0.20)` and `ebitda_margin<0.5`); require a
revenue base floor; require the inflection to be corroborated by rising (not
falling) revenue or a genuine first-positive cash print, not a single margin delta.

---

## arch_wolf_seal (N=3,153)

**Spirit:** an earnings inflection bought on a post-earnings dip (the "seal of
approval" fresh trigger), with valuation discipline.
**Rule gist:** `mcap<500e6 & inflection_print & mom12>=0.10 &
not_too_deep_any(0.50) & (ev_ebitda<15 | pe<25)`.
**Worst false-positive pattern:** `inflection_print` is the loose central
detector that fires on a single `rev_yoy>=0.10` or any margin/interval turn, so
**42% of firers (1,315) have NO hard profit-inflection or first-positive flag** —
they qualify on soft revenue/margin drift. Combined with `mom12>=0.10` the
archetype degenerates into "small-cap that is up ~10% and not too expensive."
520 firers (16%) are Financials (KINS, OptimumBank, Hennessy Advisors, Traders
Holdings) where the "earnings inflection" concept is being read off bank
metrics; 299 have op_margin<0; 341 have rev<$10M.
**Robustness proposal:** (1) require a HARD inflection leg — at least one of
{ebitda/cfo/fcf/ni/roce first-positive OR a true *_inflection flag}, not merely
rev_yoy>=0.10; (2) the "post-earnings dip" spirit implies a recent drawdown, but
`mom12>=0.10` demands the opposite (positive momentum) — reconcile: gate on a
recent pullback from a higher high rather than raw 12m momentum; (3) exclude
Financials; (4) add a revenue base floor.

---

