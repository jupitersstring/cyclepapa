# Rank 5–20 Deep Audit — QUALITY / COMPOUNDER family

Method: for each archetype I read the actual names ranked 5–20 by `entry_today_asymmetry` (16 per
archetype) and judged whether each EMBODIES the thesis, then verified suspects against the boolean in
`archetype_tags.py` and re-queried `edgar_roic_roiic.csv` / `asymmetry_global.csv` for the multi-year
fields absent from the JSON (roic_lindy, roiic_lindy, n_yrs_positive_*, op/ebitda_margin_lindy,
revenue_5y_cagr, shares_growth_3y/5y, interest_coverage, effective_tax_rate, sbc_pct_revenue). A
recurring structural fact: the EDGAR fields exist ONLY for US filers + SEC-registered ADRs, and
`years_of_history` is 6 and `n_yrs_positive_*` caps at 5 for essentially every covered name, so the
"5+ year history" gates are no-ops for covered names and score 0 (silent skip) for the rest.

Worst-first.

---

## arch_strong_coverage — 16/16 fire on a net-cash PROXY, real coverage never binds (WORST)
Every one of the 16 ranked names (LSIP.JK, 120240.KQ, 7722.T, 035610.KQ, FPIP.ST, 2348.HK, 4629.T,
METCO.BK, 054800.KQ, 0114.HK, 0057.HK, TCID.JK, 052330.KQ, 348350.KQ, 3798.HK, SPG.BK) is a non-US
small cap with `interest_coverage = NA`. The titular "real coverage leg" (`interest_coverage >= 8.0`,
7% covered) therefore CANNOT fire for a single ranked name; all 16 pass purely on the balance-sheet
proxies `nde <= 0` / `net_cash_pct_sane >= 0.20`. So the archetype's ranked output is not measuring
interest coverage at all — it is a deep-net-cash screen wearing a coverage label, fully redundant with
the net-cash / cash-quality archetypes, and effectively US-only for its stated claim. Several are even
shrinking (SIAM.BK-adjacent 3798.HK revY −2.7%, 0114.HK −1.1%) — "trivially serviceable debt" is true
but uninformative. RULE LEG AT FAULT: the `(interest_coverage >= 8.0)` disjunct is unreachable outside
EDGAR while the two net-cash disjuncts carry 100% of firings. FIX: where `interest_coverage` is NA,
substitute a globally-available coverage proxy (`ebitda_ttm / interest_expense` from the source feed,
or require `nde <= 0` AND a positive real coverage figure where present); or rename/merge this into the
net-cash family and reserve "StrongCoverage" for names with an actual computed coverage ratio.

## arch_capital_discipline — 16/16 degrade to "insider-owned & FCF>0"; ROCE available but unused (WORST)
All 16 (1900.HK, IRC.BK, TPP.BK, ALGEV.PA, 042420.KQ, LSIP.JK, 035610.KQ, FPIP.ST, 2348.HK, NPK.BK,
SHRIDINE.BO, SIAM.BK, 014570.KQ, BENGALT.BO, 3798.HK, SPG.BK) are family-controlled Asian/EU micro caps
with insider 45–97% and `roic_after_sbc = NA`, `buyback_yield = NA`, `shares_growth_3y = NA`. The
`_action_leg` (buyback / share shrink) can't fire (all NA); `_insider_plus_return` reduces — because
`roic_after_sbc` is NA — to `insider>=0.20 & fcf_yield>0`, a trivial bar. So "capital discipline" here
means only "insider-controlled and FCF-positive," exactly the flagged failure mode. Some are outright
UNdisciplined/declining: SIAM.BK revY −29.3% roce 2.3%, 014570.KQ revY −14% pe NA, ALGEV.PA pe 49.7 on
roce 6.7%. RULE LEG AT FAULT: the intended "genuine return gate" `roic_after_sbc >= 0.10` is EDGAR-only
and silently collapses to `fcf_yield > 0` for non-US names. FIX: `roce` IS present for these names
(0.02–0.39) — swap the return gate to `(roic_after_sbc >= 0.10) | (roce >= 0.10)`, and require a real
capital-return proxy (dividend payout OR buyback) rather than bare `fcf_yield>0` when share/buyback data
is missing.

## arch_low_sbc_quality — ~7/16 financials or capital-destroyers; "low SBC" ≠ quality
"Clean accounting AND genuinely profitable." Misfits: GDOT (Green Dot, Financials, roce −0.064
NEGATIVE, pe 419); VISN (Vistance, revY −83.9% collapsing, roce 0.333 but melting); ACTG (Acacia —
patent-licensing holdco, roce 0.036 / roicS 0.01, intcov 1.34, revY +133% lumpy litigation income);
SLDE & GBLI (insurers — 52.7% / 10% "EBITDA margin" is an insurance-accounting artifact); LX & XYF
(Chinese lenders, Financials); KPLT (Katapult lease-to-own, ebm 0.738 and roce 1.05 are financing
artifacts). The only quality bar besides low SBC is `ebitda_margin > 0.05`, which financing/insurance
book economics clear trivially, and "low SBC" itself is mechanically true for non-US/financial names
that simply issue little stock — so it is not evidence of clean US-GAAP quality there. RULE LEG AT
FAULT: no `is_operating` gate and no returns floor; `ebitda_margin>0.05` is the sole quality test. FIX:
add `is_operating` and require `roce > 0` (or `roic_after_sbc > 0`) so a negative-ROCE bank (GDOT) and a
collapsing name (VISN) can't pass.

## arch_lindy_growth — ~6/16 financials or negative-margin names; no is_operating / margin floor
"Durable 5-yr grower." Misfits: KINS (Kingstone, insurer, roce −0.296, roic_lindy NaN, 0 yrs positive
ROIC); ACGLO (Arch Capital, insurer, roic_lindy NaN, 0 yrs positive ROIC, op_margin_lindy NaN); WBS
(Webster Financial, bank — "70% revenue growth" is rate-driven interest income); PRCH (Porch,
op_margin_lindy −0.438, roic_lindy −0.204, roiic_lindy −0.738 — deeply capital-destructive); OPRX
(op_margin_lindy −0.099, roic_lindy −0.057); QDMI (see below — $65M shell, roic_lindy 15.6 = 1560%
artifact, shares_growth_3y 173 i.e. +17,300%). The rule tests only top-line + asset growth with NO
profitability or operating filter. RULE LEG AT FAULT: `revenue_5y_cagr>=0.08 & revenue_accel_lindy>0 &
asset_5y_cagr>0.03` with no `is_operating` and no `op_margin_lindy>0`. FIX: add `is_operating &
(op_margin_lindy > 0 | roic_lindy > 0)` and cap `shares_growth_3y` to bar dilution-funded pseudo-growth.

## arch_cash_quality — ~4/16 SBC/dilution-inflated (the gap is gameable, opposite of quality)
Thesis: cash-ROIC materially above NOPAT-ROIC ("earnings hide the cash"). But that gap is exactly what
SBC add-back and share issuance PRODUCE, so the screen selects the SBC-heaviest names: PEGA (Pegasystems,
op_margin_lindy −0.011, roic_after_sbc 0.059, shares_growth_3y +125%, SBC 10% of revenue — its
cash-ROIC 0.86 vs NOPAT-ROIC 0.35 gap is the SBC add-back, not quality); CCLD (CareCloud, shares_growth_3y
+151%, roic_lindy 0.043); PERI (Perion, Financials, roce −0.025 / roicS −0.058 CURRENTLY unprofitable,
ebm 0.6%); plus LPRO/QFIN financials (no is_operating). RULE LEG AT FAULT: `(cash_roic_lindy −
roic_lindy) >= 0.05` with no dilution/SBC gate, no `is_operating`, no current-profit gate. FIX: require
`shares_growth_3y <= 0.05` (or `roic_after_sbc > 0`) and `is_operating`, so SBC-inflated dilutors are the
first thing excluded rather than selected.

## arch_lindy_margin — ~4/16 non-operating or one-year-wonder margins
"High op & EBITDA margin held 5+ years." The rule gates ONLY on margin level over the window, with no
positive-ROIC-years or `roic_lindy>0` durability check, so: INVA (Innoviva — op_margin_lindy 0.953 is a
GSK drug-ROYALTY / holdco income stream, ebmL 0.199, only 2 of 5 yrs positive ROIC — non-operating
margin); QDMI (op/ebm ~0.28 pass, but roic_lindy 15.6=1560% and roce 1.5=150% tiny-denominator
artifacts, only 1 of 5 yrs positive ROIC, shares +17,300% — a 1-year shell, not a durable margin);
SIRI (SiriusXM — opmL 0.195 passes but roic_lindy −0.004 NEGATIVE, 1 of 5 yrs positive ROIC, nde 4.47,
shares_growth_3y −0.911 = a Liberty reverse-split reclassification). MOMO is a softer flag (margins held
while revenue_5y_cagr −8.4% and assets −11% — a shrinking business). MXC's 58.7% EBITDA margin is
commodity/depletion accounting (energy). RULE LEG AT FAULT: `op_margin_lindy>=0.10 &
ebitda_margin_lindy>=0.12 & years_of_history>=5` — no `n_yrs_positive_roic>=4`, no `roic_lindy>0`, no
non-operating-income exclusion. FIX: add `roic_lindy > 0 & n_yrs_positive_roic >= 4` so margin
durability is backed by return durability, and exclude holdco/royalty non-operating margin.

## arch_tax_efficient — ~4/16 fire on non-operating (cash-pile interest) pre-tax income
"Real, not loss-driven: effective tax <15% AND positive PRE-tax income." Because the pre-tax test does
not require OPERATING profit, cash-shell interest income backs loss-makers in: WIMI (ebm −0.08,
roce −0.042, interest_coverage −50.9 — operating loss, positive pretax from cash); FENG (Phoenix New
Media, ebm −0.053, roce −0.08, net cash = 52× market cap — pretax is pure interest income on the hoard);
IH (iHuman, roce −0.27, roic_lindy NaN / 0 yrs positive ROIC); FEDU & AMTD are near-zero-margin shells
(ebm 5.1% / 0%). RULE LEG AT FAULT: `(effective_tax_rate>0) & (<0.15) & (pretax_income_ttm>0)` — pretax
income includes non-operating investment/interest income. FIX: add an operating-profit gate
(`ebitda_margin_sane > 0` or operating income > 0) so tax efficiency is judged on a business that
actually operates at a profit.

## arch_wolf_compounder — ~5/16 base-effect spikes or loss-makers, not "sustained accelerating streaks"
Thesis (comment): "a SUSTAINED, accelerating grower." But the gate tests only single-period
`rev_yoy >= 0.25 & rev_accel > 0`, so one-year base-effect explosions qualify with no multi-year streak:
088130.KQ Dong A Eltek (revY +235%, roce 1.38=138% artifact), BDU.SI Federal Intl (revY +190%, ebm
4.9%), 5OC.SI Koyo (revY +151%, ebm 4.4%), 311390.KQ Neo Cremar (revY +99%, momentum −67%). SOGP (Sound
Group) is an outright loss-maker (roce −0.956, ev_ebitda −19.2) riding a +53% revenue print. These are
Korean/JP/SG micros with no EDGAR multi-year data, so the durability half is unverifiable (US-only).
RULE LEG AT FAULT: `rev_yoy_c>=0.25 & rev_accel>0` with no upper cap and no multi-year/positive-return
floor. FIX: cap `rev_yoy` (e.g. `< 1.0`) to drop base-effect spikes, require `roce > 0`, and — where
available — require `rev_3y_cagr >= 0.15` to confirm the streak is multi-year rather than one quarter.

## arch_lindy_fcf — a 2-leg rule; catches shrinkers, financials, and 0-ROIC names
The entire rule is `n_yrs_positive_fcf>=4 & n_yrs_positive_opinc>=4` — no margin, no growth, no ROIC, no
`is_operating`. Trailing FCF/op-income consistency is real, but it also passes: TRS (revenue_5y_cagr
−27.4%, roiic_lindy −0.208 — melting), NOAH & QFIN & XYF (Financials — FCF not comparable), WETH
(roiic_lindy −0.751, reverse-split shares_growth_3y −0.68), GNE (rev_5y −20.4%), IH (roic_lindy NaN, 0 of
5 yrs positive ROIC — never earns its cost of capital). RULE LEG AT FAULT: the two consistency legs are
the whole rule; no `is_operating`, no `roic_lindy>0`, no rev-not-collapsing floor. FIX: add
`is_operating & roic_lindy > 0` and a `revenue_5y_cagr > -0.05` guard so self-liquidating cash cows and
financials are excluded.

## arch_no_dilution — trailing counts pass currently-collapsing businesses
"Clean compounder: flat shares + FCF 4/5 + ROIC 4/5." The n_yrs_positive_* counts are backward-looking,
so a name that was fine 4–5 yrs ago but is now in freefall still passes: MED (Medifast — revY −42.6%,
rev_3y −37.7%, ebm −0.5% NEGATIVE, roce −0.077, roiic_lindy −3.53, nde 84.9, pe 240); TRS (rev_5y
−27.4%, shrinking). MHH (roce 0, ebm 1.7%) and TLF (roce 0, roicS −0.012) are near-zero-return. RULE LEG
AT FAULT: `n_yrs_fcf_pos>=4 & n_yrs_roic_pos>=4` are stale trailing counts with no current-year floor.
FIX: add a current-state gate (`roce > 0` today AND `rev_yoy > -0.15`) so a collapsing business can't
inherit a "clean compounder" tag from its history. (Reverse-split guard already present and working.)

## arch_large_cap_quality — cyclicals + a ~0-ROCE holdco pass on dividend-alone; ROIC leg is US-only
"Durable large-cap franchise." The returns gate is a 4-way OR where `dividend_yield >= 0.015` alone
suffices and the two ROIC legs (`roic_after_sbc`/`roic_lindy`) are NA for every ranked non-US name — so
deep cyclicals and a holdco qualify as "durable franchises": BOIVF/BOL.PA (Bolloré — conglomerate
holdco, roce −0.01 / 0.019 ≈ ZERO, margin is non-operating stakes); CICOY/CICOF (COSCO Shipping, revY
−6.1%), AGPPF/ANGPY (Anglo Am Platinum — mining), 7270.T Subaru (auto OEM), B8O.F Yangzijiang
(shipbuilder). High `ebitda_margin` on a capital-intensive cyclical does not imply through-cycle
quality. (Also many dual-listings double-count: NTES/NETTF, WB/WEIBF, SBMFF/SBHMY.) RULE LEG AT FAULT:
`ebitda_margin_sane>=0.15 & (... | dividend_yield>=0.015 | roic_after_sbc>=0.15 | roic_lindy>=0.12)` —
dividend-only satisfies it and the ROIC legs never bind outside EDGAR. FIX: require a quality leg that
IS globally available (`roce >= 0.12`) rather than letting bare dividend yield pass, and exclude
holdcos with near-zero ROCE.

## arch_durable_reinvestment — ~4/16 cyclical shippers + an insurer (ROIIC at cycle peak)
Well-gated (roic_lindy>=0.10, n_yrs_positive_roic>=4, roiic_lindy 0.15–1.0, asset growth), but no
`is_operating` and no cyclical exclusion, so peak-cycle ROIIC reads as "durable reinvestment": ESEA,
DAC, GSL (container-ship lessors — high roiic_lindy is charter-rate cycle, ESEA has 0 of 5 yrs positive
FCF), and MOH (Molina — a managed-care INSURER; roic_lindy 0.79 is a float artifact against a 1.4%
EBITDA margin). RULE LEG AT FAULT: no `is_operating`; `asset_3y_cagr>0.05` is satisfied by cyclical
fleet/book expansion. FIX: add `is_operating` and, for asset-heavy cyclicals, require multi-year FCF
positivity (`n_yrs_positive_fcf>=4`) so cycle-peak ROIIC without cash generation is filtered.

## arch_cash_reinvest — WBS (bank) + shippers slip the missing is_operating gate
Same construction as durable_reinvestment on cash metrics. Cleanest misfit: WBS (Webster Financial — a
bank; cash_roic_lindy 0.144 is not operating reinvestment). GSL (shipping) and CWCO (regulated water
utility) are cycle/rate-base, not franchise reinvestment. RULE LEG AT FAULT: no `is_operating`. FIX: add
`is_operating` (excludes banks/insurers/utilities), consistent with the sibling capital-allocation
rules that already carry the (G1) gate.

## arch_buyback_compounder — mostly sound; "compounder" half weak for shrinking buyers
Real share shrink + roic_lindy>=0.08 + n_yrs_roic_pos>=4 + nde<=1.5 is a solid gate and most names
(SKY, HRMY, FHI, EPAM, MYRG, HGBL, OPXS) genuinely buy back with durable ROIC. Soft flags: MOMO
(rev_5y −8.4%) and TDC (Teradata, rev_5y −2.0%, roic_lindy 0.71 is a buyback-driven negative-equity
denominator artifact) and CRTO (rev_5y −1.3%, roiic_lindy 3.0 artifact) are shrinking — buying back
stock but not compounding the business. Mild circularity: buybacks shrink equity → inflate ROIC → clear
the ROIC gate. RULE LEG AT FAULT: `roic_lindy>=0.08` is vulnerable to negative-equity inflation; no
revenue-not-declining check. FIX (light): add `revenue_5y_cagr > -0.05` or use an asset-based rather
than equity-based ROIC to avoid the buyback-inflation loop. Not urgent.

## arch_owner_operator — mostly clean (1–2 soft)
insider>=0.20 + ROIC 4/5 + FCF 4/5 + low dilution is robust; TRAK, OPXS, GIC, CODA, UI, ELA, RCMT, BDL
are genuine owner-operators. Soft flags: TRS (insider 0.25 but rev_5y −27.4%, melting) and MHH (insider
0.71 but roce 0, ebm 1.7%). Same stale-trailing-count issue as no_dilution; would benefit from the same
current-year floor. No dedicated fix needed beyond the shared trailing-count remedy.

## arch_quiet_compounder — clean (1 artifact note)
roic_lindy>=0.15 + 4/5 positive-ROIC yrs + low momentum + insider>=0.10 + low dilution is a genuinely
tight quality gate; NOBH, HEI, IRMD, OFLX, PAYX, MCO, NEU, URBN, COLM, WFCF are real "boring
compounders." One artifact to note: NATH (Nathan's Famous) roic_lindy 4.28 = 428% is a
negative/thin-equity denominator artifact (franchise buybacks), and AFG is an insurer (no is_operating
gate) — both are still genuine-quality names, so no action beyond capping displayed ROIC.

## arch_wolf_seal — mostly clean (1 soft)
mcap<500M + inflection + momentum>=0.10 + valuation cap is coherent as a post-earnings-dip inflection
buy. One soft flag: SIAM.BK (revY −29.3%) firing as an "earnings inflection" suggests `inflection_print`
is admitting margin/first-positive prints on a shrinking top line; ALGEV.PA passes its valuation leg on
EV/EBITDA 4.0 despite pe 49.7. Minor; tighten `inflection_print` to exclude names with materially
negative revenue growth.

---

## TOP-5 HIGHEST-IMPACT FIXES

1. **Fix the EDGAR-only-gate degradation in capital_discipline AND strong_coverage (100% of ranked
   names affected).** Both rules' defining leg — `roic_after_sbc>=0.10` and `interest_coverage>=8.0` —
   is NA for every non-US ranked name, so each silently collapses to a trivial proxy (`fcf_yield>0`,
   `net cash`). Substitute the globally-available `roce` (present for these names): `roce>=0.10` in the
   capital_discipline return gate, and a computed `ebitda/interest` coverage proxy (or `roce`-backed net
   cash) in strong_coverage. Highest impact because the fix touches every ranked row and the substitute
   field already exists.

2. **Add `is_operating` to the entire EDGAR-lindy / compounder family** (lindy_fcf, lindy_growth,
   lindy_margin, no_dilution, cash_quality, cash_reinvest, durable_reinvestment, owner_operator,
   low_sbc_quality). These rules lack the (G1) gate the sibling AA/AB/AC rules already carry, so banks,
   insurers and Chinese lenders (WBS, KINS, ACGLO, GDOT, SLDE, GBLI, LX, XYF, NOAH, QFIN, LPRO, PERI)
   systematically pollute quality screens with float/financing-artifact "margins" and ROICs.

3. **Kill the SBC/dilution loophole in cash_quality.** The `cash_roic − nopat_roic >= 0.05` gap is
   mechanically produced by SBC add-back and share issuance, so the screen currently SELECTS the most
   dilutive names (PEGA +125% shares, CCLD +151%). Add `shares_growth_3y <= 0.05` and
   `roic_after_sbc > 0` so "quality of earnings" excludes rather than rewards SBC inflation.

4. **Add a current-state floor to the trailing-count rules (no_dilution, owner_operator, lindy_fcf).**
   `n_yrs_positive_fcf/roic/opinc` are backward-looking, letting collapsing businesses inherit a
   compounder tag (MED −43% rev / negative margin, TRS −27%, VISN −84%, IH 0 yrs positive ROIC). Gate on
   `roce > 0` today AND `rev_yoy > -0.15`.

5. **Cap base-effect spikes and add a returns floor in wolf_compounder (and a positive-ROIC-years gate
   in lindy_margin).** Single-period `rev_yoy>=0.25 & rev_accel>0` admits +235%/+190%/+151% one-year
   explosions and loss-makers (SOGP roce −0.96); lindy_margin admits 1-year shells (QDMI roic 1560%) and
   capital-destroyers (SIRI roic_lindy −0.004). Cap `rev_yoy < 1.0`, require `roce > 0`, and add
   `roic_lindy > 0 & n_yrs_positive_roic >= 4` to lindy_margin so a "durable/sustained" claim is backed
   by durable returns, not a single print.
