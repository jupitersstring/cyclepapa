# Deep Archetype Audit — GROUP 5 (Wolf / Liger / Levered-equity families)

Two-sided methodology review. 12 archetypes: wolf x6, liger x3, weschler_levered_equity,
asymmetric_assembly, levered_inflection. Data: `asymmetry_global.csv` (mcap col = `market_cap_usd`)
merged onto `archetype_tags.csv`, ranked by `entry_today_asymmetry`.

Calibration applied: for the LEVERED family high `net_debt_ebitda` is the THESIS (convex equity
stub), never flagged per se; op_margin/fcf meaningless for financials/REITs; cheap foreign nanos
are not corrupt; prefer DOWNRANK/loosen-floor over tighten-coverage. A name is a genuine flag only
when it VIOLATES its archetype's thesis (still deeply melting in a "turned" archetype; not actually
neglected/surviving; levered with NO offsetting inflection quality).

Shared helpers read: `_not_melting` (fails only when op<0 AND fcf<0, OR roce<-5%; working-capital
positive FCF BYPASSES it), `is_operating`, `_excellent_value`, `wolf_cheap_entry`, `_clean_bs`,
`heavy_debt`/`_real_leverage`/`nde_real`, `beaten_down_any`, `n_analysts_v`
(= n_analysts.fillna(pew).fillna(0) → missing reads as 0 = maximally neglected).

**Verified the just-changed neglect gate reads correctly:** `~(n_analysts_v > 4)` (asset_backed,
lagging_inflect) and `~(n_analysts_v > 3)` (neglected_survivor). A name with NO coverage data →
n_analysts_v = 0 → `0 > 4` is False → `~False` = True → KEPT. The most-neglected (0/unknown analysts)
are correctly retained; only >4 (resp. >3) covered names are excluded. Reads correctly. All liger
top-15 firers carry NaN/1.0 analysts — no heavy-coverage violators leak in.

---

## 1. wolf_trifecta (:1875) — PROMOTES-JUNK (minor)
Thesis: double-digit growth + improving margins + operating leverage + cheap entry. The gate has NO
op-margin floor (comment at :1882 states the op>0 floor is "a sibling wolf_compounder carries"), and
`_not_melting` is bypassed whenever FCF is working-capital-positive.
- **Defect:** 6/714 firers have op_margin < -30% — a deep operating loss contradicts "improving
  margins." `9271.T` op -114%, roce 0.55, rev +33%, fcf_yield +6%; `6580.T` op -48%, roce 1.20
  (contradictory), rev +44%; `CTRM` op -52%, roce -4.4%. These pass on operating-leverage + cash-flow
  legs while the margin thesis is violated.
- **Fix:** add a mild floor `(op_margin > -0.30)` (same lower bound wolf_turnaround already uses).
  Keeps genuine pre-inflection operating-leverage names, trims the -50%/-114% burners. Small (6 names).

## 2. wolf_turnaround (:1891) — CLEAN
Gate is well-bounded: `(op_margin < 0.15) & (op_margin > -0.30)` caps established earners out AND
floors deep loss-makers out; requires an inflection print + growth + cheap entry + real revenue base.
0/731 firers have op_margin < -30%. Top firers are small-positive-margin names mid-turn (088910.KQ
op +5.3% fcf +41%, 1900.HK op -4.6% fcf +71%) — thesis-consistent "crossing to black." No leak.

## 3. wolf_value_catalyst (:1915) — PROMOTES-JUNK
Thesis: growing, cash-generative microcap with a fortress balance sheet at a cheap FCF yield. Gate
relies on `_not_melting` only (no op floor), which a working-capital-positive CFO defeats.
- **Defect:** 6/490 firers op_margin < -30%. Flagship: **`BENGALT.BO`** (Bengal Tea) op **-160%**,
  roce +23% (contradictory), fcf_yield +12.8%, pb 0.64, rev +32% — the CFO is a working-capital swing
  masking a deep operating loss. This is the exact name wolf_compounder's comment (:1969) cites as the
  reason IT added an op>0 floor; value_catalyst never got the same guard. Also `6580.T` op -48%,
  `NVI.V` op -31%, `CTRM` op -52%.
- **Fix:** add `(op_margin > -0.30)` (mirror the sibling floors). roce guard won't help — BENGALT's
  roce prints +0.23. The op line is the tell.

## 4. wolf_emerging (:1940) — CLEAN
n=2 (TRLV, TCNNF), both genuine cannabis names with positive op margin (+14%) and positive CFO. The
narrow sector regex + hard positive-CFO + low-SBC gate does exactly its HASH-lesson job. Nothing to fix.

## 5. wolf_seal (:1950) — PROMOTES-JUNK (moderate)
Thesis: an EARNINGS INFLECTION bought on a post-earnings dip (momentum + not-too-deep + cheap). The
gate has NO `_not_melting` / margin floor at all, so `inflection_print` (which can be a one-off EBITDA
print) admits confirmed floor-melters.
- **Defect:** **92/2326 firers are true melters (op_margin<0 AND fcf_ttm<0).** e.g. `0128.HK` op -46%
  fcf -$51M roce +5%; **`CTO.SI` op -65%, fcf -$4.8M, rev +2626%** (a base-effect shell — no real
  revenue floor); `8309.HK` op -3.5% fcf_yield -100%. An "inflection" archetype should not carry names
  that are both operating-loss AND cash-burning off a shell base.
- **Fix:** add `_not_melting` (and it would be consistent with every sibling). It trims ONLY confirmed
  op-loss + FCF-burn names, preserving genuine first-positive-print inflections. Trims ~92 melters.

## 6. wolf_compounder (:1964) — CLEAN
The strongest-gated wolf: `(op_margin > 0)` floor + `_roce_now_ok` + dilution cap
`~(shares_yoy > 0.20)` + rev accel + cheap entry + low SBC. 0/196 deep-op leaks. Top firers are real
accelerating profitable compounders (2230.HK rev +33% op +19% roce +19% pb 0.59 ev/ebitda 1.1). Model
gate — the other wolf screens should borrow its op floor.

---

## 7. liger_asset_backed (:1987) — CLEAN
Neglect gate reads correctly (missing coverage = kept). Genuine net-cash survivability enforced
(`net_cash_pct_c >= 0.20 & _netcash_not_contradicted`), real book anchor (`pb < 3.0`), sector filter
(no biotech/mining/crypto), near-breakeven floor. Top-15 firers all net-cash neglected microcaps
(088910.KQ net-cash 0.75 pb 0.24; 1900.HK net-cash 1.59). No heavy-coverage or distress violators.

## 8. liger_lagging_inflect (:2002) — CLEAN
`_roce_now_ok` + growth-present + cash-conversion/fcf-margin + `_clean_bs(1.5)` + neglect + sector +
drawdown. Survivability and neglect both enforced correctly. Marginal names (SHRIDINE op -7.9% but
roce +39%, nde 0.16) are survivable neglected inflections — thesis-consistent. No leak.

## 9. liger_neglected_survivor (:2019) — EXCLUDES-GOOD
Neglect/coverage logic is correct (`~(n_analysts_v > 3)` keeps 0/unknown). BUT:
- **Defect:** a `(mcap >= 20e6)` FLOOR. The floor is BINDING — the minimum firer mcap is exactly
  **$20.005M**. This cuts the sub-$20M nano cohort, which is the MOST-neglected population the thesis
  ("neglected survivor, 0 analysts ideally") explicitly targets (RCMT/VTSI were tiny). The floor is
  INCONSISTENT with both siblings: liger_asset_backed uses `mcap > 0` (138 firers under $10M),
  liger_lagging_inflect has no mcap floor (73 firers under $10M). ~179 lagging_inflect firers sit in
  the $5–20M band — a proxy for the genuine neglected survivors this archetype silently drops.
- **Fix:** lower the floor to `mcap >= 5e6` (keeps a shell/illiquidity guard while re-admitting the
  most-neglected nanos). Per the group brief: prefer loosening size gates that cut the neglected cohort,
  not tightening them.

---

## 10. weschler_levered_equity (:2191) — PROMOTES-JUNK (minor-moderate)
Leverage IS the thesis (correctly). Gate: robust cash yield + reported FCF yield + ebitda>0 +
heavy_debt + fcf>0 + stable/rising EBITDA. But it floors on CASH YIELD, not on the operating line, so
a deep operating loss with a positive (working-capital / one-off) cash-yield print sneaks in — leverage
WITHOUT the offsetting profitable-stub quality that lets a Valassis-type actually deleverage.
- **Defect:** 11/731 firers op_margin < -25%. `AMTD` op **-336%** (a financial holdco, sector=NaN, so
  it slipped `is_operating`); `SIHBY` op -228% roce +3%; `AROGRANITE.NS` op -46%, ev/ebitda **120**,
  nde 11; `F10.SI` op -38%, roce -16%. A -336%/-228% operating margin cannot service or amortise debt —
  it is a melting over-levered stub, the exact anti-thesis.
- **Fix:** add a floor `(op_margin > -0.20) | (roce >= 0)` so the levered stub is at least operationally
  viable. Also worth a data note: AMTD is a mis-classified financial (sector NaN → is_operating True).

## 11. asymmetric_assembly (:2232) — CLEAN
The tightest gate in the group (n=127): `rev_yoy <= 0.05` AND `oper_lev_any` AND `strong_op_improvement`
AND heavy_debt AND deleveraging (rising EBITDA) AND cheap AND beaten-down. The bad-headline +
substantial-improvement conjunction filters melters: only 1/127 has op < -25% (`PKNOF` op -391% —
a single leak worth noting but statistically negligible). Top firers are genuine convex levered stubs
with positive op margins on down revenue (BMTR.JK op +20% rev -4%; 071840.KS op +28% fcf +85%). The
strict PSIX conjunction is doing its job. No systematic leak.

## 12. levered_inflection (:2258) — PROMOTES-JUNK
The loosened, revenue-agnostic sibling of asymmetric_assembly. Same convex engine but WITHOUT the
`rev<=0.05` conjunction and WITHOUT `_not_melting` or any op floor. This is the leakiest levered gate.
- **Defect:** 7/341 firers op_margin < -25%, several genuinely melting:
  - **`LINK.JK`** op -47%, fcf_yield -3%, roce -9.4% — op<0 AND fcf<0 AND roce below -5%: a true
    melting-ice cube, NOT an inflection. It would fail `_not_melting` if that guard were present.
  - **`ARCHIES.NS`** op -49%, ev/ebitda **147**, rev -20% — deep loss, no genuine inflection quality.
  - **`AMTD`** op -336% (mis-classified financial, also in weschler).
  - `ALMER.PA` op -63% roce -36%; `TEAKCPO.MX` op -50% rev -44% nde 13.
  The "operating improvement" leg (`strong_op_improvement`) fires off a wrecked base while the equity is
  a stub under heavy debt — leverage with NO real inflection, the precise loophole the brief names.
- **Fix:** add `_not_melting & (op_margin > -0.25)`. `_not_melting` alone is insufficient (it misses
  names like ARCHIES whose FCF prints positive on working capital); the op floor closes it. Aligns this
  screen with asymmetric_assembly's effective strictness without re-imposing the rev conjunction.

---

## THREE HIGHEST-PRIORITY FIXES
1. **levered_inflection (:2258) + weschler_levered_equity (:2191): add an operating-viability floor**
   `_not_melting & (op_margin > -0.25)` (levered_inflection) and `(op_margin > -0.20)|(roce>=0)`
   (weschler). Closes the "melting over-levered stub" loophole — ~18 deep-loss names incl. LINK.JK
   (op-47%/fcf-/roce-9%), AMTD (op-336%), ARCHIES (op-49%/ev-ebitda-147), SIHBY (op-228%). Highest
   priority: these directly violate the deleveraging thesis (a -300% op margin cannot amortise debt).
2. **wolf_seal (:1950): add `_not_melting`.** 92/2326 firers are confirmed op-loss + FCF-burn names
   (0128.HK op-46%/fcf-, CTO.SI op-65%/rev+2626% shell). Trims only confirmed floor-melters; the
   inflection thesis is preserved. Largest count-impact fix.
3. **liger_neglected_survivor (:2019): lower `mcap >= 20e6` → `mcap >= 5e6`.** The only EXCLUDES-GOOD
   finding and the only liger with a size floor (binding at exactly $20.005M). It cuts the most-neglected
   sub-$20M nano cohort the archetype exists to capture, inconsistent with both siblings (~179 sub-$20M
   neglected inflections dropped).

Secondary (low priority, small counts): wolf_trifecta (:1875) and wolf_value_catalyst (:1915) each
leak ~6 deep-op names (BENGALT.BO op-160% in value_catalyst); add `(op_margin > -0.30)` to both,
matching the floor wolf_compounder/wolf_turnaround already carry.
