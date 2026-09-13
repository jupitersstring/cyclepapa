# Rank 5–20 qualitative audit — LYNCH-SCREEN, SEGMENT, CONTRARIAN, MOMENTUM

Scope: names ranked 5–20 by `entry_today_asymmetry` in each archetype leg. Rules verified against
`/home/user/cyclepapa/archetype_tags.py`. Verdicts below are per-leg, worst-first within each family.
"Wrong of 16" = names that do not embody the leg's thesis.

---

## SEGMENT family

**`arch_fastest_segment` (AG "hidden growth engine") — ~10 of 16 wrong. WORST IN AUDIT.**
Rule (line 853): `segment_count>=2 & seg_inflect_any & _seg_any_growth>=0.10`, with `seg_inflect_any`
including a whole-company corroboration leg `_adv_breadth>=3` (line 845). There is **no `is_operating`
gate and no profitability floor**, and the corroboration leg lets the tag fire with *no real segment
data at all*. Result: six financials leak in — NOAH (EV/EBITDA −32.8, a wealth manager), CCB Coastal
Financial (bank, rev −10.7%), AAME (insurer, FCF −26, ROCE −6.6%), MYFW (bank), WDH (insurer), COHN
(FCF −1.82, CFO −60) — none of which have GAAP "segments" in the operating sense. Add KANP Kaanapali
(rev_yoy **+1006%**, a one-off land-parcel sale, not a growth engine), TUSK Mammoth (EBITDA −32,
ROCE −27%, whole company unprofitable), AIRO (momentum −73.5%), VISN (rev **−84%**). The "fastest
segment" is either an immaterial/one-off slice or sits inside a loss-making or financial entity.
**Fix:** add `& is_operating` to the leg, require the segment growth to come from a *present* segment
column (drop the `_adv_breadth>=3` whole-co corroboration path, or gate it behind `segment_count>=2`
having real `fastest_seg_*` data), and add a whole-company survivability guard
(`(ebitda_ttm>0)|(fcf_ttm>0)`), plus clamp `_seg_any_growth` to reject >300% one-off spikes.

**`arch_geographic_global` (AF) — ~7 of 16 wrong.**
Rule (line 815): `geographic_region_count>=4` — a *pure structural* count with no quality, size,
profitability, or `is_operating` gate. It therefore fires on dying nano-caps and collapsing names:
WIMI ($22M, momentum −68%, EBITDA −4.8, melting), BANL CBL ($19M oil trader, gross margin 0.008,
EBITDA −2), VISN (rev −84%, FCF −669, burning), UEIC (FCF/EBITDA negative), AMTD (net debt 5.5×
mcap, distressed holdco), plus financials TIGR / FINV / BNT where "geographic diversification" is a
book of foreign brokerage/lending, not operating currency diversification. **Fix:** gate with
`& is_operating & (mcap>=50e6) & ((ebitda_ttm>0)|(fcf_ttm>0))` so the diversification claim attaches
to a solvent operating business.

**`arch_diversified_segments` (AD) — ~6 of 16 wrong.**
Rule (line 800): `segment_count>=4 & segment_hhi<=0.40` — structural only, no profitability/`is_operating`
gate. Misfits are unprofitable or distressed: CETX Cemtrex ($4.3M, momentum −97%, EBITDA margin −5%,
FCF yield −131%, dying), AREN Arena Group (momentum −81%, net debt 5.4×, effectively insolvent), AMTD
(net debt −5.5× mcap), LNC Lincoln National (insurer, ROCE −8.6%, EBITDA null — financial), plus NUS
(FCF −73, rev −14%), KFY (FCF −1036, CFO −971 this period), AZTA (EBITDA −116, ROCE −14%). "Diversified
revenue lowers risk" is meaningless when the consolidated entity is losing money. **Fix:** add
`& is_operating & ((fcf_ttm>0)|(ebitda_ttm>0)) & (mcap>=50e6)`.

**`arch_kpi_threshold` (G11) — ~4 of 16 wrong.**
Rule (line 526): `first_pos_print & (margin_confirming | roce_today>=0.05) & mcap>=50e6`. The $50M
size floor holds (no penny names here — smallest is Herald at $50.9M). But `roce_today>=0.05` alone
substitutes for margin confirmation and `first_pos_print` can be a single lucky print, so it admits
holdcos/negative-cash names: DC-A.TO Dundee (P/S **48.9**, EV/Sales 31.4 — a holding company whose
"revenue" is immaterial vs mcap; no operating KPI), Amuse 4301 (FCF **−1992**), TCID (CFO **−25,112**),
Tianjin Development (FCF −33, EV/EBITDA 32). **Fix:** require `margin_confirming` (drop the bare
`roce_today` OR-branch, or require it *alongside* a positive cash measure `(cfo_ttm>0)|(fcf_ttm>0)`),
and add a P/S sanity clamp to exclude investment holdcos.

**`arch_concentrated_segments` (AE) — clean (descriptive negative tag).**
Rule (line 808): `(segment_hhi>=0.70 | largest_segment_share>=0.70) & segment_count>=2`. Fires
intentionally as a *negative* concentration-risk flag; every rank-5–20 name (GNE, USANA, XNET, TRS,
JRVR, etc.) genuinely has one dominant segment, so the leg does what it says. Only cosmetic note: it
also lacks `is_operating`, so insurers (JRVR, WDH) appear — harmless for a transparency tag but worth
the same guard for consistency.

---

## CONTRARIAN family

**`arch_blindspot` (G12) — near-noise, effectively 16 of 16 carry no thesis. WORST DISCRIMINATOR.**
Rule (line 536): `country in BLINDSPOT_COUNTRIES & 0<mcap<4e8 & (adv absent | adv<5e5)`. This is
**geography + microcap size + low liquidity and nothing else** — no value, quality, inflection, or
survivability signal. It therefore fires on essentially *every* small-cap in ~24 countries (KR, TH,
ID, PL, HU, IN…), which is a huge fraction of the universe with no real discriminator: ENEFI.BD ($6.3M,
gross margin −0.179, EBITDA margin null), NPK.BK ($3.9M), Korean Drug ($24.8M, rev −14%), IGAR ($24M),
Austem, WITHTECH, etc. — a bucket, not a thesis. **Fix:** blindspot should be a *modifier*, not a
standalone screen: intersect it with an actual signal already computed here — e.g.
`& (arch_narrative_lag | arch_qarp | arch_lynch_evgy | inflection_print) & ((fcf_ttm>0)|(ebitda_ttm>0))`
— so "neglected geography" only surfaces names that also clear a business/value bar.

**`arch_analyst_awakening` — ~7 of 16 wrong (falling knives).**
Rule (line 2507): `(_nan_>=3) & _rating_present & _conviction & _not_extended & lr_live_tape`, where
`_conviction` (line 2496) fires on `analyst_target_upside_pct>=0.25`. Target upside is **mechanically
huge after a price collapse**, and `_not_extended` (`roc_12m<=0.50`) admits everything that is falling.
So the leg fires on names near 52-week *lows* — the opposite of "re-rating just begun": FUBO
(momentum −75%, −78% off high), TIGR (−53% / −55% off), Maoyan 1896 (−33% / −45% off), SAIC (−35%),
Momo (−23%), Yadea (−21%), NOAH (−14%). The "awakening" score's fresh-52w-high leg is a bonus, not a
gate, so it never vetoes a knife. **Fix:** make the tape a *gate*, not a reward — require
`(high_52w_abs | high_52w_rel | pct_off_52w_high>=-0.15)` so "re-rating started" means the price has
actually turned, and require the conviction to rest on the *rating* (`_rec<=2.2`) rather than
price-collapse-inflated target upside alone.

**`arch_asleep_at_wheel` — ~6 of 16 wrong.**
Rule (line 2098): fires on chronic estimate beats **OR** `eps_yoy_positive_share>=0.75 &
eps_yoy_growth_streak_q>=3`. The second leg has *nothing to do with analysts underestimating* the
business — it is pure EPS growth — so names with **no analyst coverage at all** get the "analysts asleep"
label: Formosan Rubber (TW), Coral India Finance, JR.BK, Thakkers (IN/TH microcaps with no sell-side).
It also admits GAAP-loss names that "beat" a low bar — GDYN (P/E **268**, ROCE −2.9%), PERF (ROCE −37%),
VISN (rev −84%, CFO negative). **Fix:** the EPS-streak OR-branch should still require real coverage
(`_nan_>=3`) and positive returns on capital (`roce>0`), so "the market underestimates them" is about
an under-followed *profitable* grower, not any EPS print.

**`arch_liger_neglected_survivor` — ~4 of 16 wrong.**
Rule (line 2760): survivability gate is `((net_cash_pct_c>=0.15) | (ebitda_ttm>0 & nde<=1.5)) &
((fcf_margin_w>=0.0) | (op_margin_v>=-0.02))`. The comment claims "WATT is intentionally rejected by
the near-breakeven gate," but the OR-structure lets a cash-rich cash-*burner* through on the net-cash
leg: MKTW MarketWise (ROCE **−75%**, FCF_ttm **−15.5**, shares_yoy **+23%** dilution — exactly the
WATT profile the rule says it excludes), ILINK.BK (EBITDA **−105**, ROCE −18.5%, rev −38.5%), Eolus
Vind (EBITDA **−256**, ROCE −30%, rev +201% one-off), Genie Music (ROCE −22%). **Fix:** require
survivability on *both* legs — replace the loose OR with `((fcf_margin_w>=0.0)|(op_margin_v>=-0.02)) &
(fcf_ttm>=0 | ebitda_ttm>0)` and add a no-dilution guard (`shares_yoy<=0.05`), so net cash cannot
launder a burner.

**`arch_dead_option` (F10) — ~3 of 16 wrong.**
Rule (line 502): `beaten_down_any(0.40) & _cash_yield_any & ebitda_margin>0 & nde<=3.0`. Two problems:
(1) `ebitda_margin>0` + a cash yield does **not** distinguish "cheap with optionality" from "cheap and
genuinely dead" — TTEC ($68M, ROCE **−9.7%**, rev −3%, momentum −60%, NCAV −5.8, net-debt/EBITDA −93.7
artifact) is a melting ice cube with no optionality, yet passes on FCF yield 0.37; Chorokbaem Media
(rev **−30.4%**) similarly. (2) `beaten_down_any(0.40)` fired on Fulu 2101 (ranked #1) whose only
drawdown lenses are pct_off_52w_high −29% and momentum −7.6% — neither is 40% — so a 5-year-range lens
is admitting names not actually beaten down. **Fix:** add a "not structurally dead" guard —
`(rev_yoy>-0.10) & (roce>0 | ebitda_inflection>0)` — so the option is on a stabilising, not collapsing,
business; and tighten `beaten_down_any` to require the primary 52w lens when present.

**`arch_narrative_lag` (Cluster A) — ~4 of 16 wrong.**
Rule (line 423): `_lag_tape & (_adv_breadth>=2) & is_operating & mcap>=50e6 & (fcf>0|ebitda>0|first_pos)
& ((0<pb<3)|fcf_yield>=0.03)`. `is_operating` and the $50M floor help, but `_adv_breadth>=2` counts
noisy `interval_inflect_any` margin-delta lenses, so **declining-revenue** names get labelled "business
advancing while price lags": TTEC (rev −3%, ROCE **−9.7%**, momentum −60% — advancing nothing), Time
Watch 2033 (rev −10.3%), Oriental Press 0018 (rev −13.3%, momentum −34%), Tianjin Development
(rev −4.9%). A price that "lags" a *contracting* business is just a value trap. **Fix:** require the
advance to include a top-line or profit-durability leg (`rev_yoy>0` OR a genuine first-positive), i.e.
exclude names whose only "advance" is a single positive margin-delta while revenue is falling.

---

## LYNCH-SCREEN family

**`arch_lynch_evgy` — ~4 of 16 wrong (no scale / operating floor).**
Rule (line 1123): `((evgy<=0.6 & ebitda_ttm>0) | (evgy missing & ebitda_ttm>0 & ev_sales>=0.05 &
(psg<=0.06 | evsg<=0.05)))`. There is **no size floor and no `is_operating` gate**, and the sales
(psg/evsg) fallback lets pure *revenue* growth stand in for the EBITDA-growth denominator. So it fires
on sub-scale and thin/negative-margin names: ENEFI.BD ($6.3M, gross margin −0.179, EBITDA margin null),
Zenith Fibres ($2.2M nano), Takamatsu 6155 (EBITDA margin **2.8%**, ROCE −0.008 — barely profitable),
TPP.BK ($14.7M). EV-GY is meant to isolate a genuine growth-at-reasonable-EV compounder; these are
denominator/coverage artifacts. **Fix:** add `& is_operating & (mcap>=50e6)` and, on the sales-fallback
branch, require a real margin (`ebitda_margin>=0.05`) so revenue growth is not silently relabelled as
EBITDA growth.

**`arch_evsales_derating` — ~3–4 of 16 wrong (one-off growth + weak-growth fallback).**
Rule (line 2270): `mcap>=50e6 & ((rev_yoy_c>=0.20)|(rev_growth_score>=0.6)) & derate_any & 0.10<ev_sales<=6.0
& (gross_margin>=0.20|ebitda>0|fcf>0) & ~(ebitda<0 & fcf<0) & is_operating`. Two leaks: (1) `rev_yoy`
is only clamped to 10×, so **one-off launch spikes** qualify as "rapid sales growth" — BioArctic B9A.F
(rev_yoy **+345%** from the Leqembi royalty, P/E **307**) is a royalty windfall, not a coiled-spring
compounder; Dong A Eltek (rev +234%). (2) the `rev_growth_score>=0.6` fallback admits names growing
<20% whose stock merely fell — TCID (rev +15.7%, CFO **−25,112**, P/E 98), YHEKF (rev +7.2%, momentum
−55%). **Fix:** cap `rev_yoy_c` contribution (e.g. reject >1.5× as a one-off unless `revenue_3y_cagr`
corroborates) and require the derate to pair *sustained* growth (`revenue_3y_cagr>=0.15` or two growth
bases) with positive operating cash (`cfo_ttm>0`).

**`arch_lynch_pegy` — ~2–3 clear + structural (no operating/scale gate).**
Rule (line 1113): `pegy>0 & pegy<=1.0` — a bare ratio test with **no `is_operating`, size, or liquidity
gate**. PEGY (P/E ÷ [EPS-growth% + yield%]) is undefined/misleading for financials, yet S23.SI
Singapura Finance (Consumer Finance, `p_e` **null** yet tagged) and BUI.BK (insurer, $20M) pass; and the
whole list is sub-$300M Asian nano/microcaps (Herald $51M, Toyo Drilube $41M, Taiyo Kisokogyo $32M)
where the earnings-growth denominator is thin and unreliable. The danger the task names — a near-zero
positive growth denominator manufacturing a sub-1 ratio on a barely-growing name — is exactly what an
ungated PEGY invites. **Fix:** add `& is_operating & (mcap>=50e6) & (adv<5e5 → require liquidity)` and
require the earnings-growth denominator to be a *positive real* growth print (guard against
`p_e` null / near-zero growth) before the ratio is trusted.

**`arch_lynch_reward` — ~2 of 16 wrong (stale-tape / cash artifacts).**
Rule (line 2401): multi-leg progress + stagnation + coil + release, with `lr_live_tape` and `lr_unpaid`
guards. Two data-artifact leaks survive: 2YO.F Press Kogyo (momentum_12m **−0.887**, `pct_off_52w_high`
**0.0** — a stale/contradictory tape claiming "at the high" while down 89%; net_cash_pct_mcap **35.6**,
a 35×-mcap cash artifact) and 900920.SS Shanghai Diesel (`p_e` **0.79**, net_cash_pct_mcap **7.7**, a
negative-EV cash-shell artifact). Both are data glitches masquerading as "years of progress about to be
rewarded." **Fix:** strengthen `lr_live_tape` to reject rows where `pct_off_52w_high==0 &
momentum_12m<-0.30` (internally contradictory tape), and clamp/reject `net_cash_pct_mcap>3` shell
artifacts in the progress gate.

**`arch_qarp` (U) — 1 of 16 wrong. Cleanest Lynch leg.**
Rule (line 936): `roiic_lindy>=0.15 & _qarp_cheap & n_yrs_roic_pos>=4 & shares_growth_3y<=0.02`. The
multi-year ROIIC + 4-year positive-ROIC history is genuinely restrictive and most names are real quality
(HRMY ROCE 43%, TDC 60%, MOH 40%, CRCT 136%, DAC, ESEA). The one misfit is MHH Mastech Digital (EBITDA
margin **1.7%**, rev −3.8%, P/E **43.8**, ROCE 0) — it clears `_qarp_cheap` only via the EV/FCF branch
and its ROIIC-lindy is a stale legacy print; a shrinking, near-zero-margin IT-staffing name is not
"quality at a reasonable price." **Fix:** add a current-profitability sanity check to `_qarp_cheap`
users (`ebitda_margin_sane>=0.05 & rev_yoy>-0.02`) so a decayed business can't ride an old ROIIC.

---

## MOMENTUM family (judged on tape: momentum_12m, pct_off_52w_high)

**`arch_oneil_canslim` — ~5 of 16 not actually strong.**
Rule (line 1547): `_on_C & _on_A & _on_N & _on_L`, where `_on_L` (the RS-leader leg) uses
`_leader_pr = max(pctrank(roc_6m), pctrank(roc_12m)) >= 80` (line 1546). Because it takes the **max of
6- and 12-month** percentiles, a 6-month bounce qualifies a name that is flat-to-down over 12 months —
so genuine non-leaders get the CAN SLIM stamp: Foxconn Tech 2354.TW (momentum_12m **−5.7%**), AVPT
(**−4.5%**), FWD.AX (+3.1%), PRIMAPLA (+4.6%), LEAT (+8.1%). O'Neil's "L" is a *market leader*, not a
6-month rebound off a 12-month decline. **Fix:** require the 12-month tape to be positive and strong on
the leader leg — `(_pr12>=80) & (momentum_12m>0)` — rather than allowing a lone 6-month percentile to
carry it.

**`arch_kullamagie_breakout` — ~4–5 of 16 wrong.**
Rule (line 1506): `_kk_leader & _kk_impulse & _kk_tight & _kk_near`, with `_kk_leader = pr6>=95 | pr12>=95`
and `_kk_impulse = max(roc_6m,mom12)>=0.30`. The 6-month OR-paths and the "near 52w high" gate admit
round-tripped, flat, or unprofitable names that are not breaking out of a real impulse leg: 0821.HK
Value Convergence (momentum_12m **0.0**, EBITDA −53, ROCE −27.5%), DTW1.F Shearwater (momentum_12m
**−4.4%**), DHOOTIN.BO (momentum +8.5%, FCF −441, CFO negative), FDMT 4D Molecular (clinical biotech,
rev_yoy **+2302×** artifact, EBITDA −152 — a biotech data spike, not a Kullamagi breakout), 2146.HK
(off-high −0.25, boundary). A Kullamagi setup needs a *big prior advance* and a leader tape; a name flat
or down over 12 months has neither. **Fix:** require `momentum_12m>0` on `_kk_leader`, compute
`_kk_impulse` from a genuine multi-month advance (not `max` with a 6m pop), and exclude
`is_clinical_biotech==1` and negative-EBITDA rows whose rev_yoy is an artifact.

**`arch_weinstein_stage2` — cleanest momentum leg (~1 borderline).**
Rule (line 1525): `_st2_trend (mom12>0 & price5y>=0.55) & _st2_rs & _st2_overhead (off_high>=-0.10 |
is_52w) & _not_st4`. Because it *requires* positive 12m momentum, upper-5y-range price, strong relative
strength, AND proximity to the 52-week high, every rank-5–20 name is genuinely in an uptrend near highs
(Futaba +18.8%, Masaru +32%, Eidai +35.5%, Imasen +31%). The one borderline is 6912.KL Pasdec
(momentum_12m only **+7.1%**, and its rev +232% is a one-off real-estate print) — weakly positive but
still near its high, so setup-consistent. No rule change needed; optionally lift the `_st2_trend`
momentum floor above 0 (e.g. `>=0.05`) to drop the weakest edges. Effectively clean.

---

## Top-5 highest-impact fixes

1. **`arch_blindspot` — convert from standalone screen to a modifier.** It is the single worst
   discriminator: geography + microcap + low ADV fires on a huge fraction of the universe with zero
   business signal. Intersect it with an existing value/inflection tag and a survivability floor so
   "neglected geography" only surfaces names that also clear a real bar. (Removes the largest block of
   thesis-free names in the whole framework.)

2. **Add `& is_operating` (+ a survivability/scale floor) to all four segment archetypes
   (`fastest_segment`, `geographic_global`, `diversified_segments`, `concentrated_segments`) and to
   `lynch_pegy` / `lynch_evgy`.** A missing `is_operating` gate is the most common single defect found —
   it leaks banks, insurers and brokerages (NOAH, CCB, AAME, MYFW, WDH, LNC, S23.SI, BUI.BK) into
   operating-business theses, and the missing scale floor admits $2–22M nano-caps (Zenith $2.2M, CETX
   $4M, ENEFI $6.3M, BANL $19M, WIMI $22M).

3. **Gate `arch_analyst_awakening` on a turned tape, not price-collapse-inflated target upside.**
   "Re-rating just begun" currently fires on falling knives near 52-week lows (FUBO −75%, TIGR −55%,
   Maoyan −45%) because target-upside is mechanically large after a crash. Make
   `(high_52w_abs | high_52w_rel | pct_off_52w_high>=-0.15)` a gate and rest conviction on the consensus
   rating.

4. **Fix the RS-leader leg shared by the momentum setups (`oneil_canslim`, `kullamagie_breakout`):
   require positive 12-month momentum, don't let a 6-month percentile pop alone qualify a "leader."**
   This removes names that are flat or *down* over 12 months yet stamped as breakout/leadership
   (Foxconn −5.7%, AVPT −4.5%, 0821.HK 0.0, DTW1.F −4.4%), plus exclude clinical-biotech rev artifacts
   (FDMT) from Kullamagi.

5. **Tighten "advance/survivor" OR-gates so a declining or cash-burning business can't qualify:**
   `narrative_lag`/`dead_option` should require the advance to include a non-falling top line
   (`rev_yoy>0`, and `roce>0|inflection` for dead_option) — evicting TTEC-type melting ice cubes; and
   `liger_neglected_survivor` should demand survivability on *both* legs plus a no-dilution guard so a
   cash-rich burner (MKTW: ROCE −75%, FCF −15.5, +23% dilution) can't launder through the net-cash leg.
   Also add a one-off-growth clamp to `evsales_derating`/`kpi_threshold` (BioArctic +345%, KANP +1006%,
   Dundee P/S 48).
