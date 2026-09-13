# Rank 5-20 Deep Audit — Deep-Value & Capital-Return Archetypes

Qualitative review of ranks 5-20 (by `entry_today_asymmetry`) for 20 archetypes.
Question per name: does the business EMBODY the thesis, or does it merely pass the boolean?
Ordered worst-first within each file. Rule legs cited from `archetype_tags.py`.

---

## WORST TIER

### arch_tangible_value  (~12/16 misfits) — WORST
Thesis (comment line ~627): "Tangible-value floor: P/TB<0.7 with tangible equity >50% of book (real assets), **survivable, not melting the floor**." Rule: `is_operating & mcap>=50e6 & p_tb<0.7 & tangible_equity_pct>0.50 & ((fcf_ttm>0)|(cfo_ttm>0)|(ebitda_ttm>0))`.
The survivability leg is an **OR that includes EBITDA**, and EBITDA is exactly the line that hides capital destruction (pre-capex, pre-interest, pre-WC). So a wall of EBITDA-positive but deeply FCF- and CFO-negative names "melting the floor" pass on the EBITDA leg alone:
- **KSS Kohl's** fcf=-789, cfo=-375, ncav%=-4.26, net debt; **PYYX Pyxus** fcf=-384, cfo=-360, ncash%=-19.3, nde=7.53; **GCO Genesco** fcf=-356, cfo=-298, roce=-0.087; **SPWH Sportsman's** fcf=-221, cfo=-187, nde=51.7, roce=-0.175 (passed on ebitda=0.1); **LE Lands' End** fcf=-171, cfo=-133, roce=-0.054; **NUS Nu Skin** fcf=-73, cfo=-22, rev -14%, mom -53% (secular MLM decline); **MOS Mosaic** fcf=-1276, pe=160; **BATL Battalion Oil** fcf=-75, off52=-95%; **CWGL** fcf=-6, pe=147; **SGA** ebmgn=-0.045, roce=-0.034; **HURC** ebitda=-6.3, roce=-0.061.
- **LAND Gladstone Land** is a farmland **REIT** (sector=None slips the `is_operating` gate) — ncash%=-1.17, ev/ebitda 13.2, ps 4.79.
Rule legs at fault: (1) survivability OR-leg lets EBITDA-positive/cash-negative names through; (2) **no leverage gate** (SPWH nde 51.7, PYYX 7.53 pass); (3) `is_operating` leaks sector=None REITs.
FIX: require the CASH legs — `(fcf_ttm>0) & (cfo_ttm>0)` (or at least one, dropping the EBITDA fallback) — AND add `((net_debt_ebitda<3) | (net_cash_pct_mcap>0))`; treat sector=None as non-operating for this floor screen (or exclude REIT industries explicitly).

### arch_oak_nav_discount  (~12/16 misfits)
Thesis (comment ~1826): Oak Bloke "price/NAV<0.7 + covered-yield **trusts / investment vehicles / holdcos**" where book≈NAV. Rule: `sector in {'Financials'} & (pb<0.7 | p_tb<0.7) & (div_yield>=0.05 | capital_return_yield>=0.06)`.
`sector=='Financials'` is far too broad — it catches operating **banks** and **insurers**, whose book is not realizable NAV and whose "yield" is an ordinary bank dividend, not a covered NAV-vehicle distribution:
- Banks: **002839.SZ** Jiangsu RCB, **2356.HK** Dah Sing Banking, **DSFGY** Dah Sing Financial, **BPOPO** Popular, **SANB3/SANB4** Santander Brasil (2 lines) = 6 banks.
- Insurance **preferred shares**: **GWO-PI.TO**, **SLF-PC.TO** — ranked on the common company's P/B (artifact for a preferred).
- Consumer lenders (not trusts): **LX**, **XYF**, **IFS.BK** (IFS ncash%=-1.78 net debt).
Genuine NAV-discount vehicles are the minority: **4SN.F** MCI Capital (PE holdco, pb 0.161), **PIAC** Princeton Capital (BDC), **NOAH**, **AIRO**.
Rule legs at fault: sector gate too broad; no preferred-share exclusion.
FIX: restrict to actual investment-vehicle industries (Capital Markets / Diversified Financials / asset managers / closed-end funds / holdcos), **exclude Banks and Insurance**, and drop preferred-ticker rows (apply the existing `_is_noncommon` regex).

### arch_weschler_levered_equity  (~7-8/16 misfits) — VERIFIED DATA BUG
Thesis (~1859): cheap equity on its own robust cash flow that is a **small, high-torque claim on a HEAVILY-INDEBTED, deleveraging** business. `heavy_debt = (nde 3-30) | (ev_over_mcap 1.75-30)` where `ev_over_mcap = enterprise_value/market_cap`.
Multiple firers are **NET CASH** — the opposite of the thesis: **005990.KQ Maeil** (ncash%=+0.73, nde=-0.45), **007540.KS Sempio** (+0.64), **311390.KQ Neo Cremar** (+0.78), **NWL.MI Newlat** (+1.15), **009810.KS NK Mulsan** (+0.67), **037400.KQ Wooree** (+1.5), **LX** (+0.71, and a financial). Verified in `asymmetry_global.csv`: **KIROY** market_cap=4.96B, `enterprise_value`=9.67B → ev/mcap=1.95 flags "heavy debt", yet `net_cash_pct_mcap`=+2.14 and `ev_ebitda`=0.357. **Maeil** mcap=135B, EV=487B (ev/mcap 3.6) but net cash +73%. **NPV.F** is a Frankfurt (EUR) listing vs JPY financials — pure currency-mismatch artifact (ncash%=+18.4). **MANO.L** nde=7.19 while net cash +1.18, pb=37.7 — internally contradictory.
Root cause: the `enterprise_value` column is **not net-cash-consistent** (behaves like mcap+gross_debt without subtracting cash) and is corrupted by cross-listing FX, so `ev_over_mcap` mislabels net-cash names as heavily indebted.
FIX: gate `heavy_debt` on `net_cash_pct_mcap < 0` (require genuine net debt) before trusting `ev_over_mcap`; corroborate with `ev_ebitda` elevated; drop cross-listing duplicate rows / FX-mismatched EV. Add `is_operating` (excludes LX). This bug also poisons `arch_asymmetric_assembly` and `arch_levered_inflection`.

### arch_financials_value  (~6-7/16 misfits)
Thesis (~1421): banks/insurers cheap on **book** (P/B<1) with real returns (ROE>=10%). Rule: `is_financial & mcap>=50e6 & 0<pb<1 & roe>=0.10 & (pe<=15 | pe NaN)`.
Six of sixteen are **preferred-share listings** ranked on the common company's book and ROE — meaningless for a fixed-claim preferred: **GWO-PI/PQ/PT/PS.TO** (four Great-West Lifeco preferreds), **SLF-PC.TO** (Sun Life pref), **BPOPO** (Popular pref). Plus **pb-artifact** microcaps: **LX** pb=0.084, **FDCT** pb=0.108 with fcf=-41 and mom -86% (burning distressed microcap, not a value financial). **TGH.BK** roce=-0.13.
Rule legs at fault: no common-stock/preferred filter; no pb floor to reject sub-0.15 artifacts.
FIX: apply `_is_noncommon` regex to drop preferred/warrant tickers; add `pb>=0.15` floor; verify ROE is present and positive rather than allowing the `pe.isna()` bypass on names with no earnings basis.

---

## MIDDLE TIER

### arch_asymmetric_assembly  (~4-5/16)
Thesis (~1908): strict PSIX conjunction — bad headline concealing improving economics, **heavy-debt levered stub**, deleveraging, cheap, beaten down, survivable. The strict legs are good, but the shared broken `heavy_debt`/`ev_over_mcap` leg (see Weschler) admits **net-cash** names: **KIROY** (ncash +214%), **NPV.F** (FX artifact +1840%), **LX** (net-cash financial, no is_operating). These are not levered equity stubs. Remaining names (0658/CHSTY China High Speed, MK.BK, BMTR, 3856.T) are genuinely levered and fit.
FIX: same as Weschler (net-debt-consistent heavy_debt) + `is_operating`.

### arch_oak_deleveraging  (~3-4/16)
Thesis (~1794): heavy-FCF operating name, nde 1-3 being paid down, **material discretionary shareholder return**. Rule has **no `is_operating` gate**, so mandatory/structural payers slip in: **VINP** Vinci Partners (asset manager — Financials), **YEIS.MC** Elaia (Spanish **SOCIMI/REIT**, div "yield" 30.6%, ebmgn 1.06 — both artifacts of REIT accounting), **SRIPANWA.BK** (Thai hospitality **REIT**). Their "deleveraging" and payout are structural, not the thesis. QH.BK (ev/ebitda 42) and 5742.T (pe 169) are borderline on the "heavy FCF, cheap" spirit. Dividend gate (>=6%) is correctly enforced across the set.
FIX: add `is_operating` and exclude REIT industries; the dividend floor already works.

### arch_oak_resource_leverage  (~3-4/16)
Thesis (~1780): low-cost producer bought **NET-CASH** on weakness (Thungela pattern). Rule: `sector in {Materials,Energy} & ev_ebitda<8 & _clean_bs(1.5) & cash_pct_mcap>=0.20 & ebitda_margin>=0.25 & (fcf_yield|robust_cash_yield|owner_earnings_yield >=0.08) & beaten_down(0.20)`.
Two leg errors: (1) the "net-cash survivability" gate uses **`cash_pct_mcap` (gross cash)**, not net cash — so net-DEBT names pass: **UNEGF** ncash%=-1.29, **PMOIF** Harbour Energy ncash%=-1.11 (both levered oil, low nde only because EBITDA is huge). (2) the yield gate is an OR over robust/owner-earnings yields, admitting a heavy-capex **negative-reported-FCF** miner: **DRDGF** DRDGOLD fcf=-1140, fcfY=-0.638, pb=3.23. Also several firers are up strongly on 12m momentum (FCSUF +85%, THX +35%) — "bought on weakness" is being read only off the 52w-high lens.
FIX: use `net_cash_pct_mcap>=0.20` for the survivability gate; require reported `fcf_ttm>0` (not just a robust-yield surrogate).

### arch_oak_order_conversion  (~4-5 soft misfits)
Thesis (~1846): backlog->revenue conversion (MPAC capital-equipment pattern), a lagging proxy = accelerating revenue + margin expansion. With no survivability gate and no sector anchor it degenerates to "small-cap accelerating revenue + operating leverage," catching cash-burners and non-backlog businesses: **ZENIFIB** (fcf=-30, cfo=-26), **CTTMF** (ebitda=-4, rev -1%), **0057.HK Chen Hsong** (fcf=-170, cfo=-99), **TCID.JK Mandom** (cfo=-25k, pe 98), plus plantation/knitting/packaging names that have no order book.
FIX: add survivability `(fcf_ttm>0|cfo_ttm>0)` and a positive-EBITDA-level requirement; if feasible restrict to capital-equipment/industrials where a backlog concept exists.

### arch_insider_conviction  (~4-5/16)
Thesis (~1963): officers/10%-owners **buying common in the open market**, net buyer, **value-oriented** price. The community **banks** (FXNC, PCB, QNTO, ASRV, FUSB, BCML, FINW) are exactly the intended good fits. Misfits come from a weak value leg (`ev_ebitda<=15 | pb<2.5 | fcf_yield>=0.03 | cheap_any`) plus no `is_operating`/no pb floor: **GPMT** Granite Point (**mortgage REIT**, levered bond book), **ONCO** Onconetix (nanocap biotech, rev -68%, mom -98.8%, ebitda=-13 — a lottery ticket, passed on pb<2.5), **EHTH** (pb=0.057 artifact, ebitda=-53, net debt, mom -81%), **TUSK** Mammoth (ebitda=-32, roce=-0.27, pe 175).
FIX: add `is_operating` (drops GPMT); add `pb>=0.1` floor (drops EHTH artifact); add a light survivability/quality gate so deep loss-makers can't qualify on the insider-buy flag alone.

---

## NEAR-CLEAN TIER (1-3 soft misfits)

### arch_discounted_vehicle  (~2-3)
Rule (~450): `is_operating & 0<pb<0.85 & (cash_gt_ev>0 | net_cash_pct_sane>0.20) & 0<mcap<2e9`. Unlike its oak siblings it has **no cash-flow survivability gate**, so **ZENIFIB** (fcf=-30, cfo=-26) and **CTTMF** (ebitda=-4, secular affiliate decline, mom -69%) slip in. Rest are legit cheap net-cash Asian small caps. FIX: add `((fcf_ttm>0)|(cfo_ttm>0))`.

### arch_liger_asset_backed  (~2-3)
Rule (~1731): neglected microcap (<=4 analysts), net cash>=20%, near-breakeven, low SBC, sector-ok. The near-breakeven gate `(op_margin>=-0.05)|(ebitda_margin>=0)` is weak and there is no revenue-decline or positive-cash-flow guard: **ILINK.BK** (ebitda=-105, rev -38%, nde 13.2), **MKTW** (fcf=-15, cfo=-15, rev -21%) slip in. The "asset_backed" label is not actually tested (no book/NCAV floor). FIX: require `(fcf_ttm>0|cfo_ttm>0)` and a rev-decline cap; add a tangible-asset floor if the name is to claim "asset-backed."

### arch_negative_ev_value  (~2-3 soft)
Rule (~2044): `is_operating & mcap<5e9 & (neg_or_low_ev | pb<0.7) & (fcf>0|ebitda>0|net_cash_sane>=0.5)`. **FPIP.ST** qualifies via `net_cash_pct_sane>=0.75` yet shows ev/ebitda 17.7, ev/sales 3.3 (net-cash field disagrees with actual EV — same data-consistency issue). ZENIFIB/CTTMF pass survivability on the EBITDA/net-cash legs while FCF is negative. Mostly the same clean net-cash names as discounted_vehicle. FIX: cross-check the net_cash leg against ev_ebitda; drop the EBITDA fallback in favor of a cash leg.

### arch_templeton_pessimism  (~2-3 soft)
Rule (~2114): cheap vs mid-cycle EBIT/EBITDA, near 5y low OR below 5y avg, survivable. **MDX.BK** is up mom +49% and near highs (fcf=-201, cfo=-172) — the "below 5y avg" leg fires but the name embodies recovery, not "maximum pessimism." **9983.HK** (fcf=-4.5, div "yield" 35.5% suspect, China property services) and **CTTMF** (ebitda=-4) are melting. The cyclical-trough names (1V5.F Pulawy, 200570.SZ Changchai) are exactly right. FIX: require the pessimism lens (near 5y low) rather than allowing "below 5y avg" alone for names with positive 12m momentum; tighten survivability.

### arch_capital_returner  (~2-3)
Rule (~718): `is_operating & (cap_return 5-30% | div+buyback 5-30%) & FCF-covered`. Misfits: **YeaRimDang** (div yield 22.9%, rev -37%, roce -0.019, fcf>>ebitda — a return-of-capital / one-off distribution from a shrinking business, under the 30% cap), **6986.T Futaba** (ebitda=-1274 negative, paying 6.6% off a possibly one-off FCF print), **TUGU.JK** (Indonesian **insurer**, slips the is_operating gate via sector=None). FIX: the FCF-covered gate should exclude one-off-FCF-funded payouts (e.g. require FCF ≈ covered by recurring earnings, or EBITDA>0); treat sector=None as non-operating.

### arch_net_cash_returner  (~2-3 soft)
Rule (~1443): net cash>=30% & actively returning `(buyback>0 | div>1% | shares_3y<-1% | net_buyback>0)`. The `div>1%` bar is weak, so token-dividend melting hoards qualify: **ZENIFIB** (fcf negative), **CTTMF** (ebitda -4), **6155.T** (roce -0.008, 2% div, no buyback). Heavy overlap with balance_sheet_return. FIX: raise the "active return" bar (require a buyback or share shrink, or div>=3%) and/or require positive FCF so a burning hoard routes to balance_sheet_return instead.

### arch_cundill_deep_value  (~2 soft) — well built
Six-point checklist fully enforced incl. **dividend** gate — clean. Soft: **CORALFINAC.BO** (rev -54%, ps 8.99, a finance holdco), **6919.HK** (fcf=-46, cfo=-45). No structural rule error.

### arch_biotech_deep_value  (~1-2)
Rule (~2753): drug developer at/below net cash. **IVBXF** Innovent (pb=7.33, pe=187, mcap 22.8B, only positive-momentum name) qualifies on net-cash% alone — richly valued, not deep value. FIX: add a cheapness ceiling (e.g. `pb<2`). Otherwise the small below-cash burners are the intended targets.

### arch_oak_deep_value  (~1-2) — near clean
Rule (~1807) has proper `ebitda>0 & (fcf>0|cfo>0)` survivability, so it is the best-guarded oak. Misfit: **INSURE.BK** (Thai **insurer** — no `is_operating` gate, cash is float, ev/ebitda 74.8); **RFT.AX** borderline (cfo=-0.1, rev -38%). FIX: add `is_operating`.

### arch_balance_sheet_return  (~1-2 soft) — on-thesis by design
Rule (~740): distinct home for uncovered payers + negative-EV cash-rich names. Firers are the net-cash-> negative-EV crowd, which is exactly the intended second leg; even ZENIFIB/CTTMF (return cash not from ops) are on-thesis. Only concern: **FPIP.ST** qualifies via a possibly-bad `cash_gt_ev` flag (its real EV is large/positive), and the archetype is a near-duplicate of discounted_vehicle/negative_ev/net_cash_returner (same ~13 names recur). FIX: validate `cash_gt_ev` against ev_ebitda; consider de-duplicating the net-cash screen family.

### arch_oak_asset_floor  (~1 soft) — CLEAN
Rule (~1829): net cash>=40% OR NCAV>=80%, pb<1.5, survivable — genuinely net-cash-floor names. Only soft: **CTTMF** (ebitda -4, but cash floor 92.6% is real). No fix needed.

---

## TOP-5 HIGHEST-IMPACT FIXES

1. **Fix the corrupted `enterprise_value` / `ev_over_mcap` heavy-debt leg** (affects `weschler_levered_equity`, `asymmetric_assembly`, `levered_inflection`). VERIFIED: the EV column is not net-cash-consistent and is FX-corrupted on cross-listings, so **net-cash** companies (KIROY +214%, Maeil +73%, NPV.F, NWL) are flagged "heavily indebted." Gate `heavy_debt` on `net_cash_pct_mcap<0`, corroborate with elevated `ev_ebitda`, and drop FX-mismatched duplicate listings. This restores the entire levered-equity thesis family.

2. **Replace the EBITDA-fallback survivability leg with cash legs, and add a leverage cap, in `arch_tangible_value`** (and echo across discounted_vehicle, negative_ev, order_conversion). `(fcf>0|cfo>0|ebitda>0)` currently lets EBITDA-positive, deeply cash-negative retail/tobacco/MLM names (KSS -789, PYYX -384, GCO -356, SPWH nde 51.7) melt the "floor." Require `(fcf_ttm>0) & (cfo_ttm>0)` + `(net_debt_ebitda<3 | net_cash_pct_mcap>0)`.

3. **Apply the existing `_is_noncommon` (preferred/warrant) regex to the financial screens.** Removes 6 preferred-share artifacts from `financials_value` (4× GWO, SLF-PC, BPOPO) and 2 from `oak_nav_discount` that are ranked on the common company's book/ROE.

4. **Narrow `arch_oak_nav_discount` from `sector=='Financials'` to real NAV vehicles.** Restrict to Capital Markets / Diversified Financials / asset managers / closed-end funds / holdcos and **exclude Banks and Insurance** — the current proxy is dominated by operating banks, not price/NAV trusts (~12/16 wrong).

5. **Add `is_operating` and fix `sector=None` leakage on the screens that lack it:** `oak_deleveraging` (VINP asset mgr, YEIS/SRIPANWA REITs), `oak_deep_value` (INSURE.BK insurer), `insider_conviction` (GPMT mortgage REIT), `capital_returner`/`tangible_value` (TUGU insurer, LAND farmland REIT via None-sector). Financials'/REITs' leverage, "cash," and mandatory payouts are structural, not the thesis. Treat blank sector as non-operating for asset/cash-floor screens.
