# Deep-Tail Audit (ranks 50-100) — Group 3 (27 archetypes)

Spirit review of the **deep tail** (ranks 50-100 by `entry_today_asymmetry`) for my 27
archetypes. Question per firer: does the business EMBODY the investment thesis, or merely
pass the boolean? `[C]` = confirmed structural bug, `[T]` = tuning. Legs cited from
`archetype_tags.py`. Already-guarded invariants (financials/REIT/utility leakage on
operating archetypes, net-cash levered stubs, sub-$20M-rev growth, declining-rev
inflections, data corruption, preferreds, sub-$2M shells, clinical biotech in *fundamental*
archetypes) are NOT re-flagged — this is what REMAINS. All figures from `asymmetry_global.csv`.
No code was edited.

---

## WORST TIER

### arch_oak_nav_discount (line 1973) — securities/brokers + ERODING-NAV BDCs; rank1050 fix never landed [C]
The whole deep tail is off-thesis. Spirit = a NAV **vehicle** (closed-end fund / trust /
holdco) at a discount to a **stable** NAV with a **covered** yield. The rank1050 report
spec'd two fixes that were never implemented:
- **Operating broker-dealers leak** via the `capital market` token: **003547/003545.KS**
  Daishin Securities, **030610.KS** Kyobo Securities — their book is a trading/lending
  book, not realizable NAV. (`_nav_vehicle` excludes bank/insur but not `securities|broker`.)
- **Eroding-NAV credit BDCs** pass the `p/tb<0.7 + yield>=0.05` legs while their NAV is
  melting: **MLCI** Mount Logan roce **−0.84**, fcf_yield **−0.57**; **BBXIA/BBXIB** BBX
  Capital op −0.19, roce −0.16, fcf_yield **−0.92**; **OCCI** OFS Credit fcf_yield −0.50;
  **CCAP** Crescent BDC roce −0.06; **CGBD** fcf_yield −0.26. A discount to an eroding NAV
  is a value trap, not a discount to realizable value.
Root-cause legs: `_nav_vehicle` (no `securities|broker` exclusion) + the value/yield legs
(no not-eroding-NAV gate). FIX: add `securities|broker` to the `_nav_vehicle` exclusion
regex; require `roe>0` (or `_ptb`-of-a-rising-NAV) so credit/trading losses can't read as a
discount.

### arch_asleep_at_wheel (line 2293) — chronic-beats branch has NO quality floor [C]
Spirit = the market UNDER-estimates a **good** business that beats estimates. Only the
`_asleep_eps_branch` fallback carries the quality gate (`is_operating & rev_yoy>=0 &
op_margin>0 & rev_usd>=20M`). The primary `((beat_rate>=0.75)&(_beat_legs>=2))` branch has
**no** profitability / not-declining gate, so collapsing or lossmaking names that beat a
low-balled estimate fire "a good business the market under-estimates":
- **MED** Medifast rev **−0.43**, op −0.025, p_e **240**, net_debt_ebitda 84.9 (revenue
  halving).
- **AMTD** Amtd Idea op_margin **−3.36** (−336%; a known data/one-off artifact, gm=1.0).
- **WORK.BK** Workpoint op **−0.070**, rev −0.176 (loss-making, shrinking).
- **DOYU** Douyu op 0.001, fcf_yield −0.054, ev_sales −3.8 (near-zero-margin melter).
Root-cause leg: the chronic-beats branch. FIX: apply the same light quality floor the EPS
branch already has to the beats branch — `& is_operating & (rev_yoy >= -0.10) &
((op_margin>0)|(ebitda_ttm>0))` — so a beat on a collapsing/lossmaking base doesn't fire.

### arch_insider_conviction (line 2154) — "value" leg admits distressed cash-burners [C]
Spirit = insider open-market buying at a **value-oriented** price. The value leg
`((ev_ebitda<=15)|(pb<pb_cap)|(fcf_yield>=0.03)|cheap_any)` treats a **distressed low P/B**
or `cheap_any` as "value," so a small insider buy in a melting shell qualifies as conviction
value:
- **SNES** SenesTech op **−2.42**, fcf_yield **−0.685** (burning 69% of mcap).
- **AVX** Avax One op **−13.2**, roce −0.40 (shell; rev +171x base artifact).
- **QTRX** Quanterix op **−1.08**, roce −0.57, fcf_yield −0.49.
- **BOLD** fcf_yield −1.41, **BNKK** roce −0.85 / fcf_yield −1.52, **ACON** fcf_yield −0.95,
  **BWMX** fcf_yield −1.14 — all pass on a bare low-P/B or `cheap_any`.
Root-cause leg: the bare `pb<pb_cap` / `cheap_any` value branch (no survivability). FIX: gate
the value leg with a cash-burn floor, e.g. require `(fcf_yield > -0.20) & (op_margin > -0.25)`
alongside the pb/cheap legs (the `ev_ebitda<=15` and `fcf_yield>=0.03` legs already imply it;
the pb/cheap legs are the hole). (Note: banks near/below book are on-thesis here via `pb_cap`.)

### arch_oak_order_conversion (line 1993) — no op-margin/roce floor + no backlog anchor [C]
Spirit = **backlog → revenue** conversion with **margin expansion** (the MPAC pattern),
industrials/capital-equipment. The `is_operating + ebitda_ttm>0 + cash + rev_accel + oper_lev
+ ebitda_inflection` gate still admits deeply-negative-operating-margin names (EBITDA-positive
via D&A) with no order book:
- **DDEJF** Dundee Corp op **−1.25** — an investment **holdco** misclassified "Consumer
  Staples / Household Products," ev_sales 17.8 (see data note below).
- **PRISMX.BO** op **−4.07**, gross_margin **−0.11** (selling below cost).
- **SHERVANI.BO** op **−0.65**, **9625.T** Cerespo op −0.21, **208350.KQ** Jiransecurity op −0.19.
- Non-backlog businesses dominate the band: breweries (San Miguel HK), restaurants (Ajisen),
  education (China Yuhua, Sunlands), music (Genie Music), modeling (Wilhelmina).
Root-cause legs: `oper_lev_any + (ebitda_inflection|ebitda_yoy>0)` with **no absolute
returns floor**. FIX: add `(op_margin>0) & (gross_margin>0)` (drops DDEJF/PRISMX/Shervani/
Jiransecurity/Cerespo); if feasible, anchor to industrials/capital-goods where a backlog exists.

---

## MIDDLE TIER

### arch_asymmetric_assembly (line 2099) — strict PSIX admits collapsing/distressed stubs [C/T]
The deliberately-strict conjunction still lets **collapsing** names satisfy `strong_op_
improvement` (a turn off a terrible base) while the FX-EV `heavy_debt` path (ev/mcap≥1.75)
bypasses the nde≤30 cap:
- **ITD.BK** Italian-Thai Development gross_margin **−0.075**, rev **−0.48**, nde 5.7 (building
  below cost).
- **XCF.SI** KTMG rev **−0.44**, op −0.097, roce −0.058, net_debt_ebitda **84.7**.
- **LOYALTEX.BO** rev −0.49, op −0.08; **001520.KS** Tongyang rev −0.20, op −0.07.
"Substantially improving unit economics" cannot coexist with a negative gross margin or a
−44%/−49% top line and 85x leverage. FIX: add an absolute floor to the improving-base leg —
`(gross_margin>0) & (roce > -0.10)` — and cap distress on the EV path (`nde_real<=15` when the
`ev_over_mcap` corroborator fires, so nde 84.7 can't read as a convex stub).

### arch_liger_asset_backed (1869) & arch_liger_neglected_survivor (1901) — near-breakeven OR-leg melts [T]
The `net_cash_pct_c` / `_netcash_not_contradicted` fix landed. What remains is the
**survivability** leg: `((op_margin>=-0.05)|(ebitda_margin>=0.0))` (asset_backed) and
`((fcf_margin>=0.0)|(op_margin>=-0.02))` / `(ebitda_ttm>0 & nde<=1.5)` (survivor). The
EBITDA/fcf-margin OR-branch admits floor-melters with catastrophic returns:
- **TUSK** Mammoth op **−0.40**, roce **−0.27** (passes on positive ebitda_margin) — recurs in
  both, and in exceptional_evsg.
- **IZEA** op −0.045, roce **−0.72**, fcf_yield −0.12, rev −0.17.
- **ENJU3.SA** op −0.21, fcf_yield −0.10; **NGRD3.SA** op −0.14, roce −0.01.
FIX: tighten the survivability leg to a real cash/return floor — `(op_margin>=-0.05) &
((fcf_yield>-0.05)|(roce>-0.05))` — dropping the bare `ebitda_margin>=0` escape (TUSK/IZEA/ENJU).

### arch_tenbagger_credible (line 2418) — negative-gross-margin / base-effect names in the STRICT cut [T]
`viable_econ = (gross_margin>=0.20)|(ebitda_ttm>0)|(op_margin>0)` — the `ebitda_ttm>0`
fallback admits names whose terminal-margin arithmetic (10-22%) is fantasy:
- **SPOFF** EarthLabs gross_margin **−0.17**, rev **+5.3x** (base-effect explosion) — a
  negative-gross-margin "credible 10-bagger."
- **FORA** op **−0.51**, net_debt_ebitda 13.9; **2546.TW** Kedge roce **−0.90**.
Credible's reality gates check cash/dilution, not returns, so these slip. FIX: add
`(gross_margin>0) & (roce > -0.10)` to `viable_econ` (or to the credible cut specifically).

### arch_exceptional_evsg (2199) & arch_evsales_derating (2465) — quality gate's EBITDA fallback + no FCF-burn floor [T]
Both use a light quality gate with an `ebitda_ttm>0` OR-leg and no FCF-burn / gross-margin
floor, so deeply-lossmaking or cash-torching "growers" fire:
- **FORA** op **−0.51**, nde 13.9 (evsg + evsales_derating + tenbagger_credible).
- **FUBO** FuboTV fcf_yield **−0.53** (burning 53% of mcap), rev +1.8x base.
- **GJS.BK** G J Steel gross_margin **−0.019**, roce −0.095, nde 7.4 (evsales_derating —
  its `~((ebitda<0)&(fcf<0))` guard only blocks BOTH-negative).
- **TUSK** op −0.40, roce −0.27 (evsg).
FIX: replace the `ebitda_ttm>0` escape with `(op_margin>-0.15)`, add `(gross_margin>0)` and a
burn floor `(fcf_yield>-0.20)` (evsales_derating: change the cash-sanity to
`~((ebitda_ttm<0)|(fcf_yield<-0.20))`).

### arch_weschler_levered_equity (line 2058) — cash-yield artifact + non-deleveraging names [T]
The FX-EV / net-cash-veto fixes hold (firers are genuinely net-levered). Two holes remain:
- **No op-margin floor** + `robust_cash_yield` artifact: **AMTD** op **−3.36** passes on a
  spurious fcf_yield +0.19 / robust cash yield (garbage near-zero-mcap cash), p_e 1.6 — a
  −336%-operating-margin "levered equity servicing debt from cash flow."
- The `(ebitda_yoy>=0)|oper_lev_any` leg permits **flat/shrinking-EBITDA** names that are NOT
  deleveraging: **PLE.BK** Power Line rev **−0.54**, nde **12.0**; **0819.HK** Tianneng rev
  **−0.30**; **EEZY.HE** rev −0.22, nde 4.4. Falling EBITDA raises debt/EBITDA — the opposite of
  the Valassis thesis.
FIX: add `(op_margin>0)` (drops AMTD/Roots) and tighten the trajectory leg to `(ebitda_yoy>0)
| (ebitda_inflection>0)` with `rev_yoy>=-0.15` so a −54% top line can't count as deleveraging.

### arch_lynch_reward (line 2596) — progress gate is HISTORICAL-only; currently-collapsing names pass [T]
`lr_profit_durable` reads only backward lenses (`n_yrs_opinc_pos>=4`, `op_margin_lindy`,
`roiic_lindy`), so a business that advanced for years and is now **collapsing** still fires
"years of progress about to be rewarded":
- **EDUC** Educational Development op **−0.57**, rev **−0.50** (roce/fcf still positive, so
  not a shell — but the current trajectory is decline, not unpaid progress).
Also **no `is_operating`** → financials/REITs leak: **JUP.L** Jupiter FM (pb 92), **NHMAF**
Nihon M&A, **RVSB/AUBN** banks, **MTRE3/LPSB3/SPALI.BK** property developers (Supalai rev −22%,
nde 4.9). FIX: add a current-trajectory floor `(rev_yoy > -0.20) & (op_margin > -0.05)` to
`lr_progress_gate`; add `is_operating` (Fannie-type financials are better served by the
analyst screens).

### arch_templeton_pessimism (line 2307) — no is_operating; RE/financial/utility leakage [T]
The `pct_off_52w_high<=-0.15` gate correctly killed the "recovered name" problem. What remains
is the missing `is_operating`: of 2,237 firers, **63 Financials, 73 Real Estate, 51 Utilities**.
Deep tail examples: **1853.HK** Jilin Chuncheng **Heating** (utility), **2146.HK** Roiserv
(RE services). EV/normalized-EBITDA is meaningless for a lending book or a
revaluation-EBITDA developer. FIX: add `& is_operating` (matches the other mid-cycle screens).

---

## NEAR-CLEAN / soft (listed for completeness)
- **arch_oak_deep_value** (1950) — `is_operating` landed. Soft: the `cfo_ttm>0` survivability
  OR-leg admits FCF-negative, deeply-negative-return names (**GLFGF** roce −0.45/fy −0.08,
  **6580.T** op −0.48). A `roce>-0.10` floor would tidy it. [T]
- **arch_oak_asset_floor** (1982) / **arch_negative_ev_value** (2227) — cash/NCAV floors are
  genuine; negative-op names have a real parachute. Only real leak is **DDEJF** (holdco
  misclassified — see data note). No structural fix. [T]
- **arch_oak_deleveraging** (1936) — on-thesis; tail is nde 2-3 cyclicals (in band) with
  op_margin>0/roce floors holding. The `oper_lev_any` fallback lets a few declining-rev
  cyclicals (HAFN −16%, AAD.DE −19%) pass, but that is arguably deliberate cyclical breadth.
- **arch_cheap_sales_scaler** (2176) — well-gated. Soft: `near_profit`'s `ebitda_ttm>0` OR-leg
  lets a handful below the −15% op floor slip (**7353.T** KIYO op −0.20). Minor.
- **arch_liger_lagging_inflect** (1884) — `_roce_now_ok + _clean_bs + rev_yoy>0` hold; tail
  hits are high-pb (not in thesis) not returns violations. Clean.
- **arch_analyst_awakening** (2708) / **arch_analyst_rerating_confirmed** (2748) — analyst-driven
  and sector/margin-neutral by design; financials and high-pb quality-at-highs are on-thesis.
  Only soft note: awakening has no biotech guard, so pre-revenue clinical names (**ABEO** op
  −1.20) fire on target-upside — acceptable for an analyst screen, but worth a display flag.

## CLEAN (no change needed)
- **arch_wolf_compounder** — `op_margin>0` + low-dilution + `cfo/fcf>0` + rev 0.25-1.5 hold; tail
  is genuine cheap compounders.
- **arch_growth_algo** — `fcf_ttm>0` + `fcf_yoy>=0.20` compounding gate keeps the tail real cash.
- **arch_wolf_seal** — inflection + momentum + cheap + `is_operating`; tail is on-thesis (op &
  fcf positive). No returns floor, but no material violators surfaced.
- **arch_oak_resource_leverage** — only ~18 firers (no deep tail); net-cash + cost-curve gates hold.

---

## Data note (recurring, non-code)
**DDEJF Dundee Corporation** — a Canadian investment **holding company** — is sector-tagged
"Consumer Staples / Household Products," so `is_operating` cannot exclude it. It leaks into
**oak_order_conversion, oak_asset_floor, negative_ev_value** with op_margin −1.25 and ev_sales
17.8. A sector-classification correction (→ Financials/holdco) fixes all three at once.

## Highest-impact fixes (worst-first)
1. **oak_nav_discount**: add `securities|broker` to the `_nav_vehicle` exclusion and a
   not-eroding-NAV `roe>0` gate (MLCI/OCCI/BBXIA + Daishin/Kyobo Securities). rank1050-spec'd,
   never landed.
2. **asleep_at_wheel**: mirror the EPS-branch quality gate (`is_operating & rev_yoy>=-0.10 &
   (op_margin>0|ebitda>0)`) onto the chronic-beats branch (MED/AMTD/WORK.BK/DOYU).
3. **insider_conviction**: add a cash-burn floor to the bare `pb`/`cheap_any` value leg
   (SNES/AVX/QTRX/BOLD burning 50-150% of mcap).
4. **oak_order_conversion**: add `(op_margin>0)&(gross_margin>0)` (DDEJF/PRISMX/Shervani).
5. **asymmetric_assembly** + **liger** survivability legs + **tenbagger_credible/evsg/
   evsales_derating**: replace the `ebitda>0`/`ebitda_margin>=0` survivability escapes with an
   op-margin + gross-margin + FCF-burn floor (TUSK/FORA/FUBO/SPOFF/ITD.BK/KTMG).
6. **weschler / lynch_reward / templeton**: add `is_operating`/current-trajectory floors
   (AMTD/PLE.BK; EDUC; Jilin heating utility).
