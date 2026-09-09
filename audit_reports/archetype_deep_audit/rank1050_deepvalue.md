# Rank 1-10 / 30-50 Deep Audit — Deep-Value / Asset / Oak / Liger family (16 archetypes)

Spirit review of ranks 1-10 AND 30-50 (by `entry_today_asymmetry`). Question per name:
does the business EMBODY the thesis, or merely pass the boolean? Worst-first. Recent
fixes (is_operating on many screens, net-debt leverage legs, FX-EV guards, revenue
floors, net_cash_pct_sane) are NOT re-flagged — this is what REMAINS after them.
`[C]` = confirmed bug, `[T]` = tuning. Legs cited from `archetype_tags.py`.

Several rank520 fixes were spec'd but never landed in code (see `IMPLEMENTATION_log.md`,
which only added `is_operating` to some of these). Those unimplemented items resurface
below and are the highest-value fixes.

---

## WORST TIER

### arch_tangible_value (line 664) — EBITDA-fallback floor leg still open [C]
Thesis: P/TB<0.7, tangible equity >50% of book, **survivable not melting the floor**.
Only `is_operating` landed (247→119); the survivability OR-leg and leverage gate the
rank520 report demanded were **not** implemented. Root-cause leg:
`((fcf_ttm>0)|(cfo_ttm>0)|(ebitda_ttm>0))` — the EBITDA fallback passes EBITDA-positive
but deeply FCF-/return-negative "floor melters":
- **KSS** Kohl's fcf_yield **−0.597**, roce 0.09 (passes on ebitda) — named in rank520, still here.
- **NUS** Nu Skin fcf_yield **−0.247**, rev −14%, mom −53% (secular MLM decline) — passes on ebitda.
- **TUSK** Mammoth op_margin **−0.40**, roce **−0.27**, p_e 174 — passes on ebitda 0.09.
- **UEIC** Universal Electronics op_margin −0.03, roce −0.10; **HURC** Hurco op_margin −0.05, ebitda_margin **−0.059** (passes via fcf print).
No leverage gate either. FIX: require `(fcf_ttm>0) & (cfo_ttm>0)` (drop the EBITDA leg), add
`((net_debt_ebitda<3)|(net_cash_pct_mcap>0))`, and a `roce>0` floor to drop TUSK/UEIC/HURC.

### arch_oak_deep_value (line 1867) — MISSING is_operating [C]
Rank520 said "add is_operating"; it was never added. No `is_operating` gate → Real
Estate and Financials leak into a "hard-asset-parachute operating deep value" screen:
- **9983.HK** Central China New Life — Real Estate, div "yield" **35.5%**, fcf_yield −0.011, mom −67% (melting China property services).
- **0873.HK** Shimao Services — Real Estate Mgmt, ev_ebitda −4.26, China property.
- **INVENTURE.NS** Inventure Growth & Securities — **Financials/Capital Markets** (broker), nde 3.8; its "cash" is operating float, not a parachute.
FIX: add `& is_operating` (the other oak siblings already carry it).

### arch_weschler_levered_equity (line 1972) — MISSING is_operating, Real-Estate developers dominate [C]
The FX-EV `heavy_debt` fix worked (firers now show genuine net debt). But there is **no
`is_operating` gate**, so the top ranks are **property developers**, whose leverage is
inventory/project financing and whose "FCF" is lumpy land sales — NOT the Valassis
fixed-debt-amortisation thesis:
- **900940.SS** Greattown (RE, rev **−46%**), **SAMCO.BK** Sammakorn (RE, nde 4.6), **PROUD.BK** Proud RE (nde 6.1), **BEST.JK** Bekasi Fajar (RE), **5280.T** Yoshicon (RE), **RICHY.BK** Richy Place (nde 20.7), **PSH.BK** Pruksa Holding (RE, nde 7.7).
- Financials also leak: **4SN.F** MCI Capital (PE holdco; nde 3.6 vs net_cash% +0.998 — contradictory fields still slip the veto), **GREENCREST.BO**.
FIX: add `& is_operating`. Optionally require `rev_yoy>=−0.10` so the "deleveraging"
business isn't actually shrinking.

### arch_liger_asset_backed (1789) & arch_liger_neglected_survivor (1819) — corrupt net-cash leg admits net-DEBT names [C]
`IMPLEMENTATION_log.md` explicitly **deferred** the `net_cash_pct_c` swap ("not swapped").
That field is FX-/stale-corrupt and disagrees with `net_debt_ebitda`, so the
`net_cash_pct_c >= 0.20/0.15` "survivability" leg admits genuinely **net-levered** names.
Verified in `asymmetry_global.csv` (ncash% vs nde): **TTEC** +0.744 / nde **−93.7**, roe −1.0;
**WINE.L** Naked Wines +0.509 / nde **9.4** / **pb 75.4**; **ACX.DE** +1.78 / nde **20.2**;
**CVN.AX** Carnarvon +0.769 / nde **37.0** (pre-rev oil); **FORA** +0.465 / nde **13.9**;
**CLIQ.DE** roce −0.45, op −0.40 / nde 6.0. Also **MKTW** (roce −0.75, rev −21%) and **PERF**
(roce −0.37) pass the weak near-breakeven leg.
Second defect: **"asset_backed" never tests an asset floor** — no book/NCAV/tangible gate — so
names at **pb 75** (WINE.L, SNX.L, GENL.L pb 61) and **FPIP.ST** (pb 1.85, ev_ebitda 17.7)
qualify as "asset-backed."
FIX: gate the net-cash leg on agreement with `net_debt_ebitda` (require nde<=1.0 OR a
sane net-cash field), i.e. drop the corrupt `net_cash_pct_c` sole reliance; add a genuine
asset floor (`p_tb<1.5` or `ncav_pct>0`) for `asset_backed`; strengthen the near-breakeven
gate to `roce > −0.02` (drops MKTW/PERF/CLIQ/FORA).

### arch_financials_value (line 1482) — preferred-share leakage + no pb floor [C]
Rank520 R7 (broaden non-common scrub) and the pb floor were **never implemented** (this
archetype isn't in the implementation log). Still ranking **fixed-claim preferreds on the
common's ROE/book**:
- **GWO-PI.TO / GWO-PQ.TO / GWO-PT.TO** (three Great-West Lifeco preferreds, all roe 0.362, ev_ebitda −16.5), **SLF-PC.TO** (Sun Life pref).
- No pb floor → artifact microcaps: **FDCT** FDCTech pb **0.108**, fcf_yield −1.66, mom −86% (distressed, not a value financial).
FIX: apply the `_is_noncommon` regex broadened for suffixed foreign preferreds
(`-P[A-Z]?\.`, `-PR`); add `pb >= 0.15` floor.

### arch_oak_order_conversion (line 1909) — no survivability / no backlog anchor [C]
Only `is_operating` landed; the survivability + positive-EBITDA gate rank520 asked for was
not added. With just `oper_lev_any + (ebitda_inflection|ebitda_yoy>0)` it admits
negative-EBITDA / negative-op-margin decliners, and there is no sector/backlog concept:
- **6986.T** Futaba ebitda_margin **−0.030**, op −0.065, rev **−10.7%** (passes on rev_accel + inflection).
- **0559.HK** DeTai op_margin **−0.34**, fcf_yield **−0.14**, ev_ebitda 52.8 (cash-burner).
- **TTEC** roe −1.0, rev −3%, mom −60% (distressed BPO); **DC-A.TO** Dundee (holdco, op −1.25, rev $9M).
- Non-backlog businesses: **LSIP.JK** (palm-oil plantation), James Warren Tea, Emperor Watch.
FIX: add `(ebitda_ttm>0) & ((fcf_ttm>0)|(cfo_ttm>0))`; if feasible anchor to
industrials/capital-equipment where a backlog exists.

---

## MIDDLE TIER

### arch_oak_nav_discount (line 1889) — "capital market" token admits operating broker-dealers [C/T]
The narrowing to `_nav_vehicle` helped, but the `capital market` / `diversified financ`
tokens still catch **operating financials whose book ≠ realizable NAV**:
- Operating broker-dealers / structured-product issuers: **LEON.SW** Leonteq (op_margin **−1.0**, roe −0.045, ev_ebitda 417), **OS9.F** Orient Securities, **003465/003460.KS** Yuhwa Securities, **0188.HK** Sunwah Kingsway, **001755/001750.KS** Hanyang Securities.
- Sector-**misclassified** operating cos via "Diversified Financial Services": **CABO** Cable One (levered cable co, nde 23.8, mom −83%), **CSTE** Caesarstone (countertop mfr, roce −0.28), **KRRYF** KLN Logistics.
- **NXDT** Nexpoint Diversified **Real Estate** Trust slips the `~mortgage/reinsur` exclusion via industry="Capital Markets".
FIX: restrict `_nav_vehicle` to closed-end fund / investment trust / holding / asset-manager
industries and **exclude broker-dealers/securities** (add `securities|broker` to the
exclusion); require a not-eroding NAV (`roe>0`) so credit/trading losses don't count as a
discount; add `real estate` to the exclusion.

### arch_discounted_vehicle (line 473) — survivability gate never added [T]
Rank520 asked for `(fcf_ttm>0)|(cfo_ttm>0)`; only `is_operating` + `net_cash_pct_sane`
landed. Net-cash melters still pass: **6986.T** Futaba (neg EBITDA, rev −11%), **0882.HK**
Tianjin Development (op −0.07, fcf_yield −0.014), **047820.KQ** Chorokbaem Media (rev −30%).
Plus **TUGU.JK** (Indonesian **insurer**) leaks via **both sector AND industry = NULL**, which
the industry-keyword is_operating backstop cannot see. FIX: add the survivability leg; treat
sector-AND-industry-both-NULL as non-operating for cash-floor screens.

### arch_oak_deleveraging (line 1854) — no returns/quality floor [T]
`is_operating` correctly dropped the REITs. Remaining: the `fcf_yield>=0.10` heavy-FCF leg
has no quality floor, so negative-operating-margin names fire a "deleveraging cash cow"
thesis: **270870.KQ** Newtree (op −0.001, roce −0.001, div_yield shows **−0.04** artifact),
**5742.T** NIC Autotec (op **−0.059**, p_e **169**), **BAP.AX** Bapcor (op −0.14, roe −0.14,
mom −65%), **0819.HK** Tianneng (rev −30%, fcf_yield 0.55 likely one-off). FIX: add
`(op_margin>0)|(roce>0)` and prefer a genuinely rising-EBITDA trajectory over the
`oper_lev_any` fallback for declining names.

### arch_templeton_pessimism (line 2203) — "below 5y avg" fires on recovering names; no is_operating [T]
The `price_vs_5y_avg<=0.85` OR-leg admits names that are **up strongly / near highs** — the
opposite of maximum pessimism: **0100.KL** ESCERAM (mom **+88%**), **WEBJF** Web Travel (off
−5.6%, roce 0.26), **SIAM.BK**. No `is_operating` → **9983.HK** (China real-estate services,
melting) recurs. Survivability EBITDA/net-cash fallback passes negative-EBITDA melters
(**CTTMF** Catena ebitda_margin −0.08). FIX: require the pessimism lens
(`price_pct_of_5y_range<=0.35`) for names with positive 12m momentum; add `is_operating`;
tighten survivability to a cash leg.

---

## NEAR-CLEAN / soft (minor tuning, listed for completeness)

- **arch_oak_resource_leverage** (1840) — net-cash fix landed well; all firers now net cash.
  Soft: the `{Materials,Energy}` gate + `ebitda_margin>=0.25` proxy admits energy-**services**/
  holdcos that aren't low-cost producers (**AKKVF** Akastor roce 0.02, **OMSE** OMS Energy). [T]
- **arch_negative_ev_value** (2132) — broadly net-cash on-thesis. Soft: the EBITDA-fallback
  survivability leg passes cash-burners with a big cash pile (**0559.HK** DeTai op −0.34,
  **RFT.AX** neg EBITDA). Same fix pattern as tangible_value. [T]
- **arch_oak_asset_floor** (1898) — near-clean; net-cash/NCAV floors are genuine. Soft:
  negative-op-margin net-cash names (**RFT.AX**, **2033.HK** Time Watch p_tb −0.59) qualify —
  cash floor is real, but a `roce`/rev-decline guard would tidy it. No structural error.
- **arch_cundill_deep_value** (1646) — well-built (strong dividend + no-deficit gate). Soft:
  the dividend criterion accepts likely one-off / stale-price yields (**9983.HK** 35.5%,
  **BSLI3.SA** 19.5%), and financials pass via the ebitda-leg + debt-exemption despite
  negative FCF/ROCE (**COHN** fcf_yield −1.82, **AAME** roce −0.066). No structural fix needed.
- **arch_balance_sheet_return** (779) — on-thesis by design (the deliberate home for net-cash
  runoff / negative-EV / uncovered payers). Only concern is heavy **duplication** with
  discounted_vehicle / negative_ev / oak_asset_floor (same ~15 names recur across all).

---

## CLEAN (no change needed)
- **arch_balance_sheet_return** — functions as the intended catch-all second leg.
- **arch_oak_asset_floor** — cash/NCAV floors are real; near-clean.
- **arch_cundill_deep_value** — six-point checklist incl. dividend gate holds up.

## Highest-impact fixes (worst-first)
1. **Add `& is_operating`** to `arch_oak_deep_value` and `arch_weschler_levered_equity`
   (both still lack it — Real Estate developers / brokers dominate). Rank520-spec'd, never landed.
2. **Fix the `net_cash_pct_c` net-cash leg** in both ligers to agree with `net_debt_ebitda`
   (net-DEBT names TTEC/WINE.L/ACX/CVN/FORA pass a net-cash gate); add a real asset floor to
   `asset_backed`. Explicitly deferred in the last pass.
3. **Replace the EBITDA-fallback survivability leg with cash legs** + add a leverage cap in
   `arch_tangible_value` (and echo to `negative_ev`, `discounted_vehicle`,
   `oak_order_conversion`): KSS/NUS/TUSK/Futaba/DeTai melt the "floor" on EBITDA alone.
4. **Apply the broadened `_is_noncommon` preferred scrub + `pb>=0.15` floor** to
   `arch_financials_value` (GWO-PI/PQ/PT, SLF-PC, FDCT). R7, never implemented here.
5. **Narrow `arch_oak_nav_discount`** to true NAV vehicles — exclude broker-dealers/securities
   and add a not-eroding-NAV (`roe>0`) guard; add survivability to `discounted_vehicle`.
