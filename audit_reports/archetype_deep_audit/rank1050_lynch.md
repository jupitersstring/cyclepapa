# Rank 1-10 / 30-50 Spirit Audit — Lynch / Contrarian / Momentum / KPI / Biotech (16 archetypes)

Ranks 1-10 AND 30-50 by `entry_today_asymmetry`, 16 arch cols. Each finding: offending
names + giveaway metric, root-cause leg, [C]onfirmed spirit-violation vs [T]uning, fix.
Landed fixes (analyst_awakening not-freefall; oneil leader>0; rerating 52w-high) NOT
re-flagged. Small-cap breadth intentional — not flagged. Worst-first.

---

## 1. [C] `arch_biotech_deep_value` — value traps with NO runway (violates its own stated spirit)
The definition's own docstring requires "enough runway not to face imminent dilution,"
but the runway gate was deliberately dropped ("no fragile runway gate"). Result: names
being consumed faster than 1x net cash/yr fire on the `ncav>=0.8` / `cash_gt_ev` legs,
whose "cushion" evaporates before the pipeline option pays.
- **MBIO** (Mustang Bio): `fcf_yield -1.15` — burning >100% of mcap/yr, rev 0, mcap $4.1M.
- **BIVI** (BioVie): `shares_yoy +2.27` (diluted 227% YoY), `fcf_yield -1.45`, rev 0.
- **CDIO** (Cardio Diagnostics): revenue $14.8K, `fcf_yield -1.34`, op_margin -410x.
- **BOT.AX** (Botanix): `fcf_yield -1.27`, `roe -0.96`. **TCRX**: `fcf_yield -1.86`.
- Root-cause leg: `((_bdv_ncash>=0.5)|(_bdv_cashev>0)|(_bdv_ncav>=0.8))` with the runway
  gate removed. `net_cash_pct>=0.5` + `fcf_yield ≈ -1.0` = <6 months runway.
- **Fix:** restore a soft runway floor using the already-computed column —
  `& (biotech_cash_runway_yrs >= 1.0)` (clips to 99 for non-burners, so cash-rich names
  are unaffected). Optionally also exclude hard active dilution (`shares_yoy <= ~0.25`).
  This directly encodes the docstring's "not facing imminent dilution."

## 2. [C] `arch_dead_option` — artifactual FCF-yield on negative-EV / near-cash ADR shells + REIT leakage
Thesis: beaten-down operator where you're PAID TO WAIT on real cash. The cash-yield leg
reads one-off / near-liquidation FCF spikes on sub-scale ADRs as durable optionality, and
there is no `is_operating` gate.
- **JFU** (9F Inc): `fcf_yield 0.96`, `ev_ebitda -896`, `ev_sales -165`, mcap $30M — net
  cash ≫ mcap; 96% FCF yield is an artifact, not a cash cow.
- **SOGP** (Sound Group): `fcf_yield 0.84`, `roe -0.96`, `ev_sales -1.39`, mcap $50M.
- **STG** (Sunlands): `fcf_yield 0.37`, `ev_ebitda -10.3`, `p_e 0.79`, rev declining.
- REITs via missing gate: **0169.HK Wanda Hotel**, **0873.HK Shimao Services** (`ev_ebitda -4.3`).
- Root-cause legs: `_cash_yield_any` keys off `fcf_yield>0.05` (uncorroborated, EV-blind) and
  no `is_operating`, no mcap floor.
- **Fix:** (a) add `& is_operating`; (b) require the cash yield be EV-consistent /
  corroborated — gate on `cash_return_ev>0.05` (needs positive EV) OR pair `fcf_yield` with
  `ebitda_margin>0 & net_debt_ebitda>=0`-style sanity so a one-off spike on a negative-EV
  shell can't alone qualify; (c) add a modest mcap floor (~$50M) as elsewhere.

## 3. [C] `arch_asleep_at_wheel` — EPS-streak branch fires on shrinking / lossmaking / nano shells
Thesis: market chronically UNDER-estimates a quality beater. The EPS-fallback branch
(`eps_yoy_positive_share>=0.75 & eps_yoy_growth_streak_q>=3`) has no revenue, scale,
margin, or operating guard, so EPS growth off one-offs / a collapsing base qualifies.
- **CORALFINAC.BO**: `rev_yoy -0.54` (revenue collapsing) yet fires.
- **MDX.BK**: `op_margin -0.78`, Real Estate. **ACTG**: `roe -0.029` (acquisition-driven EPS).
- Nano shells: **PHUN** (rev $2.5M, op_margin -446%), **MSAI** (rev $5.7M, `roe -0.46`).
- No `is_operating`: US community banks dominate 30-50 (FCCO/FSBC/SBFG/TCBX/SSBI/Cohen).
- Root-cause leg: the second OR-branch of `arch_asleep_at_wheel`.
- **Fix:** gate the EPS-streak branch with `& (rev_yoy >= 0)` (not declining) `&
  (op_margin > 0)` (genuinely profitable) `& (revenue_ttm >= 20e6)` (scale) `& is_operating`.
  The chronic-beat branch (`beat_rate>=0.75`) is more defensible; leave it.

## 4. [C] `arch_blindspot` — no quality/value discriminator at all (near-noise standalone)
Definition is purely `country ∈ BLINDSPOT & mcap<4e8 & (low/absent ADV)`. Every firer is
just "small illiquid stock in an under-covered country" — no cheapness, quality, or tape
leg. E.g. **INSURE.BK** (`ev_ebitda 74.8`, `roe 0.019`, mom -33%), **Incon** (`ev_ebitda -14`,
`roe NaN`). Previously noted (R520 "convert to modifier"); STILL unfixed in the code.
- **Fix:** demote to a *modifier* on other archetypes, OR add a real discriminator
  (e.g. a cheapness OR quality leg: `pb<2` OR `fcf_yield>=0.03` OR `roce>=0.08`) so
  "blind-spot" means an under-covered name that also *looks* mispriced.

## 5. [T] `arch_kpi_threshold` — no `is_operating`; financials/REITs read as "operating KPI inflection"
Scale floor ($50M) and first-positive-print legs hold, but no operating gate, so financials
and REITs whose margin/ROCE mean something structurally different leak in:
**MXD.F Min Xin (Insurance)**, **0169.HK Wanda Hotel**, **900940.SS Greattown (RE)**,
**089600.KQ Nasmedia** etc. The `margin_confirming | roce_today` (roce>=5% + ANY first-pos)
is also loose.
- Root-cause leg: `first_pos_print & (margin_confirming | roce_today) & (mcap>=50e6)` — no `is_operating`.
- **Fix:** add `& is_operating` (an "operating KPI" archetype should be operators only).

## 6. [T] `arch_qarp` — backward-looking ROIIC/streak, no current-state or tape floor; no `is_operating`
Mostly clean (183 firers, quality US names). But the multi-year gates
(`roiic_lindy>=0.15 & n_yrs_roic_pos>=4`) are backward-looking, so collapsed Chinese
financials whose returns *were* high re-qualify as "quality at a reasonable price":
- **XYF** (X Financial): `p_e 2.5`, `-54%` off high, mom -0.53, `ev_ebitda -1.5` (negative EV).
- **JFIN** (Jiayin): `p_e 2.4`, `-82%` off high, mom -0.82.
- **Fix:** add a current-state floor (R4-style: current `roce>0`) and drop the deepest
  distress (e.g. `pct_off_52w_high >= -0.6` OR `momentum_12m > -0.4`); add `& is_operating`.

## 7. [T] `arch_lynch_evgy` / `arch_lynch_pegy` — upstream guards hold; residual `is_operating` + margin-artifact edges
PEGY/EVGY denominators are well-guarded upstream (P/E>0, positive growth denom, ebitda>0,
`ev_sales>=0.05`), so the *core* is clean. Residual edge cases only:
- No `is_operating`: **S23.SI Singapura Finance**, **TETAA Teton Advisors** (financials).
- EVGY `ebitda_margin` artifact ceiling: **0559.HK DeTai** (`ebitda_margin 1.10`, op_margin
  -0.34, mcap $66M); distressed holdcos (**Dundee** op_margin -1.25).
- PEGY sub-liquidation multiple: **STG** `p_e 0.79` (one-off-inflated earnings).
- **Fix (minor):** add `& is_operating`; cap the EVGY margin path (`ebitda_margin <= ~0.6`);
  optional PEGY floor `p_e >= 3` to reject distress-priced one-offs.

## 8. [T] `arch_kullamagie_breakout` — no `is_operating`; value-destroyers pass as "leaders"
Momentum/impulse/near-high legs are actually satisfied (`_kk_impulse` requires a 30% prior
run, so this is NOT the R10 leader gap O'Neil had). But no operating gate lets value-
destroying financials fire a "leading stock breakout":
- **0821.HK Value Convergence** (`roce -1.08`, `roe -0.17`, mom 0.000), **MXD.F Min Xin**,
  **DHOOTIN.BO** (`fcf_yield -0.44`).
- **Fix (minor):** add `& is_operating` (and/or a soft quality floor `roce > 0`) so a
  breakout on a melting financial isn't a Kullamagi leader. `_kk_near` lower bound (-0.25 =
  24.6% off high) is loose for "breakout" but is a deliberate base allowance — leave.

## 9. [T] `arch_analyst_rerating_confirmed` — no operating/revenue floor; a pre-revenue biotech pop qualifies
52w-high fix landed and the list is otherwise clean (Jet2/NHN/MetLife/Bajaj/ASUSTeK). Lone
misfit: **INMB (INmune Bio)** — revenue $50K, `p_s 824`, `op_margin -616`, `roe -0.75`; a
binary-event biotech print at a 52w high with 4 analysts is a pop, not a fundamental re-rating.
- **Fix (minor):** add a light operating floor (`revenue_ttm >= 20e6` OR `ebitda_ttm > 0`)
  so a pre-revenue clinical name can't read as a "confirmed re-rating."

## 10. [T] `arch_evsales_derating` — largely clean; two artifact leaks
Well-guarded (is_operating, cash sanity, scale, room-left). Residual:
- Negative-EV cyclicals: **MGX.AX Mount Gibson** (`ev_ebitda -0.55`, op_margin -0.17).
- `rev_yoy` artifact: **SVMRF Magnora** (`rev_yoy 42.3` → clipped to 10x, still passes 0.20).
- **Fix (low):** tighten the rev_yoy clip band or require `revenue_3y_cagr` corroboration
  on the >5x-growth tail. Low priority.

---

## Shared root causes (fix once, many archetypes improve)
- **SR-A — missing `is_operating`** (the R1 gap, still unlanded for this family): dead_option,
  asleep_at_wheel, kpi_threshold, qarp, kullamagie_breakout, lynch_pegy/evgy. Adding the
  robust `is_operating` gate removes the financial/REIT leakage from all seven at once.
- **SR-B — artifact cash-yield on negative-EV near-cash ADR shells** (JFU/SOGP/STG/2YU…):
  worst in dead_option (a gating leg); elsewhere it's cosmetic noise. Guard `fcf_yield`
  with an EV-consistency / positive-EV requirement where it gates.
- **SR-C — backward-looking multi-year quality gate, no current-state floor** (R4): qarp.
- **SR-D — no revenue/scale floor on a growth/beat/pop leg**: asleep_at_wheel EPS branch,
  analyst_rerating (INMB), biotech ($2M mcap tail).

## CLEAN (honour spirit as-is — leave)
- **arch_lynch_reward** — heavily gated (progress + profit-durable + not-capacity-trap +
  unpaid + live-tape + coil + release/roc-setup); no new misfit.
- **arch_weinstein_stage2** — technical setup; near-52w-high + positive-momentum + upper-5y
  legs all satisfied by firers. Sector-agnostic by design.
- **arch_narrative_lag** — lag-tape + `_adv_breadth>=2` + `is_operating` + `mcap>=50e6` +
  cheapness anchor all present; firers are genuinely down-tape with advancing fundamentals.
- **arch_analyst_awakening** — post not-freefall fix; residual is only the generic
  negative-EV ADR noise (Momo/NOAH), not an awakening-specific bug.
- **arch_lynch_pegy / lynch_evgy core** — upstream denominator guards hold; only the minor
  `is_operating`/margin-artifact edges in §7 remain.
