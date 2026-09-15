# Deep Two-Sided Methodology Audit — GROUP 4

Technical/behavioral & event-driven special situations. Reviewed against `archetype_tags.py`
gate logic; firers ranked by `entry_today_asymmetry` from `asymmetry_global.csv` / `archetype_tags.csv`.
Data snapshot 2026-09-10. Fire counts in parentheses.

Legend: CLEAN / PROMOTES-JUNK / EXCLUDES-GOOD / BOTH. Bias throughout: prefer DOWNRANK over DROP
(system edge is breadth); confirm a name is OPERATING before flagging melt.

---

## 1. fixed_cost_demand_shock (2722) — CLEAN
Heavy-asset sector + rev accel + rev_yoy>0 + `_not_melting` + leverage cap (KNOWN 6–90x zombies excluded)
+ capped margin-shock leg. Firers are recovering industrials/materials/KR-micro with net cash and a
margin inflection off a low base (e.g. 348350.KQ op -26% but fcf_yield +9.8% → passes `_not_melting`
legitimately; the margin SHOCK from a low base is the thesis). rev_yoy>0 correctly blocks
still-declining top lines. No defect — the operating-leverage-from-a-shock thesis is faithfully encoded.

## 2. capital_discipline (2399) — CLEAN
Strict stack: is_operating + owner-aligned (buyback/shrink OR insider+return) + `_cd_returns_floor`
+ `_roce_now_ok` + op_margin>0 + nde<=1.5 + sane ebitda margin + price_yoy<=0.30 + yart_score>=0.45.
The prior "value-destroyer bought back stock" hole is closed (returns floor + op>0 on every path).
Top firers (088910.KQ op 5% roce 20%, LSIP.JK op 28% roce 32%) are genuine net-cash disciplined
compounders. No defect.

## 3. regime_cyclical (1166) — CLEAN
Heavy-asset + beaten_down(0.20) + rev_yoy>0 + `_not_melting` + leverage cap + EBITDA
inflection/first-positive/capped-margin-shock + not_priced_in>0.20. Firers are beaten-down cyclicals
inflecting off a trough with rising revenue (7722.T, NPK.BK, WHLM). By-design and well-guarded.

## 4. blindspot (3214) — CLEAN (deliberately broad, do not tighten)
Pure geography+size+liquidity discovery gate (BLINDSPOT_COUNTRIES & mcap<4e8 & ADV<5e5/absent).
No fundamental floor by design. A melter such as ENEFI.BD (op -288% artifact) appears purely because
it is a neglected-geography nano — this is the intended discovery breadth, not a defect. Left as-is
per audit guidance.

## 5. bab_low_beta (95) — CLEAN
beta_present & raw>=0.20 & shrunk<=0.85 & `bab_quality` (is_operating, fcf_margin>0, ebitda_margin>=0.10,
op_margin>0, nde<=2.5, roce>=0.10|cash_conv>=0.60) & real liquidity floor (ADV>=1e5, missing FAILS).
Careful beta handling (raw present + shrinkage guard against illiquid-nano laundering). Firers
(PRDO op 25%/roce 25%, KWS op 43%/roce 65%, TDC roce 60%) are genuine low-beta quality. No defect.

## 6. bab_becoming (1824) — CLEAN (minor note)
Transitional "de-risking toward safety" bucket: is_operating + rev>=20M + fcf_margin>-0.05 +
`_roce_now_ok` + rev_yoy>-0.05 + moderate beta (0.85–1.15) + margin/cash inflection + nde<=3.
Intentionally has NO op_margin>0 floor (the name is still becoming safe). A few negative-op names slip
through on the fcf/roce floors (348350.KQ op -26% roce 6.5%, 4170.T op -5%) — defensible as the
"becoming" (not "is") bucket, and they rank low. Not worth a fix.

## 7. bab_multibagger (162) — CLEAN
Same `bab_quality` + liquidity gate as bab_low_beta, plus (multibagger inflection OR cheap leg).
Firers (ONEXF op 75%, HRMY op 25%/roce 43%, INVA op 41%) are real quality with an embedded
compounding/cheapness leg. No defect.

## 8. kullamagie_breakout (1162) — CLEAN (pure technical, by design)
Setup-detection ONLY (documented lines 1700–1740): live tape + momentum leader (pctile>=95) + prior
run>=30% + tight base + within 25% of high. No fundamental gate is INTENDED — it is a breakout screen,
sector-agnostic. Melters/financials in the asymmetry-ranked top (0821.HK op -133%, 2546.TW roce -90%)
appear only because I sorted by `entry_today_asymmetry`, not `kullamagie_score`. Faithful to Kullamagi's
methodology; flagging fundamentals here would be a category error. No defect.

## 9. oneil_canslim (372) — PROMOTES-JUNK (mild)
DEFECT: The "A" pillar (`_on_A = roce>=0.15 & (eps_pos>=0.75 | rev>=0.10)`) can be satisfied by a
ONE-OFF-inflated roce while op_margin is deeply negative, admitting loss-makers that violate CANSLIM's
core **C (strong CURRENT earnings)** pillar. `_roce_oneoff_suspect` and `_profit_present` are NOT
applied here, and `_on_C` accepts rev>=20% growth alone (true even for a cash-burner). 12/372 fire with
op_margin<0; 6 are deep loss-makers:
- **DDEJF** op -125%, roce 0.334 (roce off a tiny/one-off base; no current earnings)
- **KURA** op -350%, roce 0.586 (pre-commercial biotech, roce artifact)
- **CFOO** op -143%, roce 0.268; **MDX.BK** op -78% (RE revaluation roce); **ASMB** op -47%
These have "earnings growth" only off a negative/one-off base — the opposite of O'Neil's "C".
FIX: add `& (op_margin > 0)` (a real earnings leader is profitable) and/or apply `~_roce_oneoff_suspect`
to the roce leg of `_on_A`. ~1.6% of firers; DOWNRANK-grade but a clean, thesis-aligned tightening.

## 10. asleep_at_wheel (3118) — CLEAN (no quality floor by design)
Explicit design (lines 2422–2430): no quality FLOOR; quality is upweighted 60% in `asleep_score`.
Validity guards on the EPS branch (is_operating, rev_yoy>=0, rev>=20M) are present and correct. Melters
in the asymmetry-ranked top (MDX.BK op -78%, SSBI op -45%) are by design and rank low in the archetype's
own score. Per audit calibration, not a defect.

## 11. analyst_awakening (2023) — CLEAN (minor)
n_analysts>=3 + real reasonable rating + conviction (>=half of rating/upside/breadth lenses)
+ `_not_extended` (roc_12m<=0.50) + `_not_freefall` + live tape. Well-guarded against the
crash-inflated-target-upside falling-knife trap. No operating-quality floor, so 47 fire with rev<5M
(pre-revenue biotechs on analyst conviction) — defensible since the thesis IS the coverage+price signal,
not fundamentals. No priority fix.

## 12. analyst_rerating_confirmed (370) — CLEAN (minor)
Same conviction stack + ACTUAL fresh 52w-high (abs or rel-to-index) + blow-off guard. The 52w-high
requirement makes it the "re-rating begun AND price agrees" cut. 9 fire with rev<5M (INMB rev $50k,
AMLX, VIR — pre-revenue biotechs at a high with coverage). Minor: an optional small revenue floor
(e.g. rev>=5M unless clinical-biotech) would drop pure pre-revenue shells, but biotech re-ratings are
legitimate here. Low priority.

## 13. biotech_deep_value (117) — CLEAN
Per calibration, burn / negative op margin IS the thesis (cash-rich clinical developers below net cash).
`_is_clinical_biotech` + FX-clamped net-cash band (0.5–3.0) + runway>=1.0 + dilution guard
(shares_yoy<=50%). Firers (KROS, GLPGF, ZEAL.CO) are exactly the intended binary-option-below-cash
names. The net-cash-band clamp correctly neutralizes FX corruption (Kalbe/Sundrug). No defect — do NOT
flag burn here.

## 14. bottleneck (1635) — CLEAN
is_operating + `_not_melting` + rev>=5M + gross_margin>=0.40 + non-eroding GM + (roce>=0.15 &
~oneoff_suspect | roic_lindy>=0.15) + op_margin>0.05 + capital-light (~capex_intensity>0.10). The
`_roce_oneoff_suspect` guard IS applied. JAMESWARREN.BO (roce 100%) passes only because op_margin 22.5%
>=20% genuinely corroborates the return — a real high-margin nano, not the low-margin artifact the code
comment warned of (margins have since risen). Firers are genuine fat-margin high-roce chokepoint proxies.
No defect.

## 15. flyover (2345) — CLEAN (thesis correctly preserved)
VERIFIED: correctly KEEPS zero-coverage names (n_analysts NaN passes `~(n_analysts>5)` — "undiscovered")
and does NOT require coverage. Thesis intact: is_operating + low/no coverage + insider>=0.20 +
(roce>=0.15 & ~oneoff | roic_lindy>=0.15) + strong/durable FCF + op_margin>0 + `_not_melting` + nde<=2.0.
No heavy-coverage names leak (the gate FAILS n_analysts>5). Firers are neglected owner-controlled quality
compounders across KR/HK/TH/JP. The insider>=0.20 requirement drops names with MISSING insider data, but
that is definitional to the Wenning owner-control thesis, not a coarse cut. No defect.

## 16. insider_conviction (384) — CLEAN (minor)
Form-4 open-market cluster/10pct/officer buy + net-buyer + `_not_melting` + value price, with the
correct **financials/REITs → pb<1.0** carve-out (banks no longer pass on a trivial pb<2.5). Bank firers
(GBLI 0.66x, QNTO 0.72x, FUSB, BCML) are all genuine sub-book insider buys. Minor: permissive-NaN
`_not_melting` lets an unknown-fundamentals collapsing shell through (ONCO down 98.8% YoY, op/fcf NaN;
GPMT mortgage-REIT op -29% but fcf+11%) — but these ARE costly insider buys at deep discounts (the
revealed-preference thesis), and op_margin is meaningless for the REIT. Breadth-by-design; no priority fix.

## 17. spinoff (3) — CLEAN (one marginal name)
`(spin_flag==1) & is_operating & _not_melting & op_margin>-0.05 & _excellent_value`. VGNT (op 8.8%,
fcf 18.8%, ev/ebit 8.0, roce 32%) and VSNT (op 26%, fcf 30%, ev/ebit 6.4) are clean cheap spun operators.
MINOR: **NVRI** net_debt_ebitda **46x**, roce -4.8% (just above the -5% melt line), op 1.8% — spinoff has
NO leverage cap (post_reorg has nde<=3, nol_shell/special_sit rely on other guards). Spinco over-leverage
is a canonical Greenblatt feature, and only 3 names fire, so this is a low-priority note rather than a
fix: consider a soft `nde<=6` cap to exclude 46x zombies while keeping normal spin leverage.

## 18. post_reorg (0) — CLEAN (honest zero; fix verified correct)
Fires 0 — HONEST (the reorg XBRL concept marks only ~13 distressed names, none operationally cheap).
Do NOT force names in. VERIFIED the discharge-gain fix reads correctly: `_reorg_value = ((_ebit_yield
>= 0.10) | (fcf_yield >= 0.08))` and `arch_post_reorg` gates on `_reorg_value` — it does NOT use the
`_earn_yield` (1/p_e) leg from `_excellent_value`. A fresh-start company's discharge-gain-inflated p_e
(e.g. WW p_e 1.56) therefore cannot buy its way in on fake earnings yield. Correct.

## 19. special_situation (83) — PROMOTES-JUNK (mild / measurement mismatch)
`((merger|tender|going_private)==1) & mcap>0 & _not_melting & _excellent_value`. DEFECT: unlike every
other event archetype (spinoff/post_reorg/nol_shell all gate `is_operating`), special_situation has **NO
is_operating gate**, so **36/83 (43%) are Financials** — overwhelmingly closed-end funds with tender/
merger flags (BGY, BOE, VTN, BDJ, AEF, SWZ...). For a closed-end fund the relevant cheapness is
**discount-to-NAV**, but `_excellent_value` measures fcf/earnings/ebit yield — the wrong lens, which
these funds pass on their pass-through "op_margin"/earnings. The tenders themselves are legitimate
special-sits, so this is a measurement mismatch (right event, wrong value test) rather than pure junk.
FIX (DOWNRANK-grade): either add `is_operating` to restrict to the operating-company special-sit thesis,
or route financials through a discount-to-NAV / pb<1.0 value leg instead of the yield-based
`_excellent_value`. Operating firers (SSTK fcf 11%, PAYO, ZTO) are clean.

## 20. nol_shell (47) — PROMOTES-JUNK (highest-priority G4 defect)
`is_operating & mcap>0 & NOL/mcap in [0.5,20] & (net_cash>=0.10 | value | cash>ev) & op_margin>-0.30 &
_not_melting`. DEFECT: the "survivable, not a >100%-mcap/yr burner" guard is proxied by **op_margin>-0.30**,
but op margin does NOT capture cash burn. A name with a positive/artifact op margin while FCF torches the
balance sheet passes. **11/47 (23%) fire with fcf_yield < -0.25** (burning >25% of mcap/yr); 4 burn >50%:
- **CNTY** fcf_yield **-1.19** (burning 119% of mcap/yr!), op +9.2% (positive → passes op gate), roce 34%
- **NEON** fcf_yield **-0.80**, op_margin +3.55 (355% artifact masks the burn entirely)
- **CNDT** fcf -0.75, op +3.5%; **MODD** fcf < -0.50
This is EXACTLY the ">100%-mcap/yr burner (ONCO/ASTC)" the docstring claims to exclude — the op_margin
proxy simply fails to catch FCF-torching shells. An NOL is worthless without a going concern to use it.
FIX: add an FCF-burn floor to the survivability gate, e.g. `& ~(fcf_yield < -0.25)` (missing stays
permissive, consistent with biotech_deep_value's runway logic). Removes CNTY/NEON/CNDT/MODD and the other
7 hard burners while keeping cash-generative NOL holders (SIRI, GETY).

---

## TOP 3 PRIORITY FIXES (Group 4)

1. **nol_shell — add an FCF-burn floor.** `& ~(fcf_yield < -0.25)`. Its op_margin>-0.30 survivability
   proxy misses FCF-torching shells; 11/47 (23%) burn >25% mcap/yr, 4 burn >50% (CNTY -119%, NEON -80%,
   CNDT -75%, MODD). An NOL on a dying balance sheet is un-monetizable — the exact case the docstring
   already intends to exclude. Highest-impact, cleanest fix.

2. **special_situation — add `is_operating` (or a NAV-based value leg for financials).** 43% of firers are
   closed-end funds whose tender/merger flags are validated on the wrong cheapness lens (yield instead of
   discount-to-NAV). It is the only event archetype lacking the is_operating gate its siblings all carry.

3. **oneil_canslim — add `& (op_margin > 0)` (and/or `~_roce_oneoff_suspect` on the roce leg).** The "A"
   pillar admits deep loss-makers (DDEJF op -125%, KURA op -350%, CFOO -143%) on a one-off-inflated roce +
   revenue-growth-off-a-negative-base, violating CANSLIM's defining "strong CURRENT earnings" (C) pillar.

Note: post_reorg discharge-gain fix VERIFIED correct (gates EV/EBIT & FCF yield, not 1/p_e). All quality/
technical archetypes (bab_*, bottleneck, flyover, capital_discipline, biotech_deep_value) are CLEAN; the
deliberately-broad (blindspot) and floor-free-by-design (asleep_at_wheel, kullamagie) archetypes were left
untouched per calibration.
