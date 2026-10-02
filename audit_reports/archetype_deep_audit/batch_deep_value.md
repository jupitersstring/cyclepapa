# Deep-Value / Asset Family Archetype Audit

**Cross-cutting root causes:** (A) `n_analysts` missing filled with **0** → "maximally
neglected", so unscreened names pass every neglect gate; (B) `enterprise_value` and
`net_cash_pct_mcap` are **meaningless for banks/insurers** (deposits/float make EV
hugely negative and "net cash" enormous), yet no rule excludes Financials; (C)
several rules lost their size or survivability guardrail.

Ranked worst-first. All numbers from real firers (archetype_tags.csv × asymmetry_global.csv).

### 1. arch_liger_lagging_inflect — 5,172 firers (WORST)
Spirit: quiet inflection in a *neglected microcap* (RCMT/VTSI, ~$100-400M). Rule:
growth-accel + cash-conversion + clean b/s + n_analysts<=4 + non-mining/biotech +
beaten-down. FP: **NO market-cap ceiling** (siblings cap at $400M), and n_analysts
NaN→0 for **3,865/5,172 (75%)**, so blank-analyst names read as neglected. Result:
**424 firers >$5B, 160 >$20B** — Alphabet (GOOGM/GOOGN $584B), Tencent ($510B), Bank
of China ($280B), SAP ($248B). Fix: add `(mcap>=20e6)&(mcap<=400e6)`; require
n_analysts PRESENT and <=4 (NaN → fail neglect gate, not pass).

### 2. arch_balance_sheet_return — 5,906 firers
Spirit: cash-rich runoff / true negative-EV. Rule: `mcap>0 & (uncovered payout OR
neg_ev)`, neg_ev = ev<0 OR cash_gt_ev. FP: **1,209 Financials; 832 via neg_ev leg**
— banks/insurers have EV massively negative from deposits/float. Bank Central Asia
EV −93T IDR; Sumitomo Mitsui EV −55T JPY; Hanwha Life EV −84T. Fix: exclude
Financials/REITs from the neg_ev leg. (NOTE: I created this archetype this session —
the neg_ev leg needs the financials guard.)

### 3. arch_oak_order_conversion — 7,208 firers
Spirit: backlog→revenue conversion (MPAC industrial). Rule: `mcap<1e9 & (rev accel OR
rev_yoy>5%) & oper_lev & (ebitda inflection OR ebitda_yoy>0)`. FP: generic "small-cap
growth + oper leverage" net, **no cheapness anchor, no sector focus**. 427 firers at
EV/sales>15, 846>8 — Clene (497x sales), Brand Engagement Network (484x), Ribomic
(460x), firing via rev_accel off near-zero revenue with NEGATIVE rev_yoy. Fix: add
`ev_sales<=4` or `ev_ebitda<=15`, require `ebitda_ttm>0`, bias to Industrials.

### 4. arch_negative_ev_value — 7,048 firers
Spirit: paid to own the business (mcap ≤ net cash) OR deep sub-book + survivability.
FP: **980 Financials**; **1,298 firers report net cash >100% of mcap** (financial-
holdco artifact — "cash" is an investment portfolio). Cocoon Holdings net_cash 5.5x
mcap. Fix: exclude Financials from net-cash/EV legs; cap net_cash_pct ~1.0;
survivability → `fcf>0 OR cfo>0` not EBITDA-only.

### 5. arch_oak_asset_floor — 2,958 firers
Spirit: mcap at/below cash+hard assets (Graham floor). Rule: `mcap<500e6 &
(net_cash>=0.40 OR ncav>=0.80) & 0<pb<1.5`. FP: **NO survivability gate** — 737 (25%)
are double burners (fcf<0 AND ebitda<0) melting the "floor" cash (WEGE.JK NCAV 1.94x
but EBITDA −₹643B). 459 Financials. Fix: add `(fcf>0 | cfo>0)` (siblings have it);
exclude Financials.

### 6. arch_liger_asset_backed — 2,987 firers
`liger_sector_ok` excludes biotech/mining/crypto by string but **not Financials →
484 leak in**; inherits n_analysts NaN→0. Fix: add Financials/RE to exclusion;
n_analysts present.

### 7. arch_discounted_vehicle — 2,324 firers
309 Financials + **1,081 (47%) fcf<0**. Fix: exclude Financials; light survivability.

### 8. arch_liger_neglected_survivor — 3,940 firers
Better guarded (mcap cap + near-breakeven) but n_analysts NaN→0 + 278 Financials.

### 9. arch_tangible_value — 247 firers
**94/247 (38%) Financials**, 155 (63%) fcf<0. Fix: exclude Financials.

### 10. arch_weschler_levered_equity — 1,307 firers
Well-gated. Minor: 138 RE developers with lumpy land-sale FCF (PROUD.BK fcf_yield
134%). Minor fix.

### Clean
arch_templeton_pessimism (3,050), arch_oak_deep_value (1,254), arch_oak_nav_discount
(256, Financials-only by design), arch_oak_deleveraging (233), arch_asymmetric_assembly
(215), arch_oak_resource_leverage (32).

## Top-5 highest-impact
1. **Exclude Financials (and REITs) from every EV / net-cash / NCAV leg** — cleans
   ~980 + ~1,209 + 459 + 484 + 309 + 94 across six archetypes. Highest leverage.
2. **Fix n_analysts NaN→0** — treat missing as "unknown → fails neglect gate."
3. **Market-cap ceiling on liger_lagging_inflect** (20e6-400e6) — removes Alphabet etc.
4. **Cheapness anchor + ebitda_ttm>0 on oak_order_conversion.**
5. **Survivability gate on oak_asset_floor** (`fcf>0 | cfo>0`).
