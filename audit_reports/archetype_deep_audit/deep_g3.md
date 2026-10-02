# Deep two-sided methodology audit — GROUP 3 (deep value, contrarian & asset-based)

Auditor pass over 17 archetypes in `archetype_tags.py`. Data: `asymmetry_global.csv` × `archetype_tags.csv`.
Method: read gate logic + helpers, pull top-15 firers by `entry_today_asymmetry`, judge PROMOTES-JUNK and EXCLUDES-GOOD.
Calibration applied: op_margin/fcf ignored for financials/REITs/holdcos; pb/p_e treated as currency-neutral (foreign cheap nanos KEPT); melting flagged only for confirmed **operating** loss-makers (op<0 & fcf<0, or roce<-5%).

## Headline (systematic finding)
A whole family of Group-3 cheap-on-cash / cheap-on-book gates **omit the current-returns floor** (`_not_melting` / `_roce_now_ok`) that their better-guarded siblings already carry. The floor demonstrably works:
- `geographic_global` (has `_roce_now_ok`): **3** operating melters of 487 fired.
- `diversified_segments` (no floor, otherwise identical survivability leg): **14** of 192.
- The unguarded cheap-cash gates carry **178–795** confirmed operating burners each (op<0&fcf<0 or roce<-5%), including textbook value traps (CHGG, WISH, FOM, Wishpond).

`_not_melting` is the correct, already-calibrated fix: it fails a name ONLY when it is a confirmed operating loss-maker AND cash-burner, or roce<-5% — it does NOT touch cheap foreign nanos with positive op/fcf. Adding it to the seven gates below is one edit repeated.

---

## Verdicts

### discounted_vehicle:554 — PROMOTES-JUNK
Gate: `is_operating & pb∈(0,0.85) & (cash>ev | net_cash>20%) & ~known-net-debt & mcap<2e9`. No returns/melting floor at all.
- **300 of 1,125** firers are operating melters; **214** have roce<-5%. The net-cash requirement does not stop an operating melter that happens to sit on cash.
- Examples: **CHGG** (Chegg, op -23%, roce -95%, roe -56%, pb 0.80 — classic melting-ice trap; fcf_yield +88% is a one-off working-capital print that defeats any cash leg), **WISH.V** (Wishpond, op -89%, fcf -24%, roce -87%, roe -94%), **FOM.CO** (op -55%, fcf -69%, roce -98%). All are genuine value traps, not FX artifacts.
- Fix: add `& _not_melting` (sibling `dead_option` already carries a returns floor via `_roce_now_ok` + `op>0`). Drops ~300 confirmed burners; keeps every cheap net-cash operator.

### dead_option:625 — CLEAN
`is_operating & mcap≥10M & beaten_down(0.40) & cash_yield_any & ebitda_margin>0 & op_margin>0 & _roce_now_ok & nde≤3`. Requires positive op margin AND non-negative roce — top-15 are all positive-margin, positive-roce, net-cash cash cows. No defect.

### tangible_value:770 — BOTH
Gate: `is_operating & mcap≥10M & p_tb∈(0,0.7) & tangible_equity_pct>0.50 & (fcf>0|cfo>0) & ~(fcf_yield<-15%) & nde≤4`.
- **PROMOTES-JUNK:** no net-cash sanity clamp. Two of the 7 firers are >100%-of-mcap cash operating shells that are RED-verdict Chinese reverse-split ADR pumps where pb≈0.1 is a serial-dilution artifact: **HOLO** (net_cash 677% of mcap, pb 0.106, roce 0.3%, roe -2.3%, verdict RED), **MLGO** (net_cash 366%, pb 0.14, roe... verdict RED). Fix: add the `net_cash_pct_sane` clamp (`net_cash_pct ≤ 1.0` for operating) that `discounted_vehicle`/`negative_ev_value` already use.
- **EXCLUDES-GOOD (coverage):** `p_tb` (=price/tangible book) is only computed where `tangible_equity` exists — **11.9% of the universe** (mostly US EDGAR filers). Only 48 operating names have p_tb∈(0,0.7) at all, so the gate fires just 7 times and is **blind to every cheap foreign tangible-asset name** whose intangibles/goodwill aren't populated (where pb≈p_tb). Fix: fall back to `pb` when goodwill+intangibles are ~0/NaN, so a home-listed hard-asset name at 0.5x book is not silently dropped.

### diversified_segments:956 — PROMOTES-JUNK
Gate: `is_operating & segment_count≥4 & hhi≤0.40 & (fcf>0 | ebitda_margin>5%)`. Survivability leg identical to sibling `geographic_global` **but missing `_roce_now_ok`**.
- 14 of 192 firers are operating melters vs only 3/487 for the guarded sibling.
- Examples: **TUSK** (Mammoth Energy, op -40%, roce -27%, roe -22%, p_e 174 — positive one-off fcf +18% lets it pass), **ASH** (roce -19%, roe -31%), **SLP** (roce -59%, op -76%). Diversification is a *resilience* label; a name whose diversification plainly failed to protect it shouldn't wear it.
- Fix: add `& _roce_now_ok` (one word — brings it into line with `geographic_global`).

### concentrated_segments:971 — CLEAN
This fires as an explicit **NEGATIVE / risk** signal (HHI≥0.70 or top-segment≥70%), kept for transparency; admitting weak names (TTEC roe -101%) is the intended behaviour, not a buy thesis. No fix.

### geographic_global:979 — CLEAN (minor cross-cutting note)
`is_operating & _roce_now_ok & geo≥4 & (fcf>0|ebitda>5%)` — the returns floor keeps it to 3 melters. Top-15 are quality global operators. Only leak is **AMTD** (op -336%, net_cash -555%) — a financial holdco misclassified as operating because sector AND industry are NaN and the name misses the financial regex. That is a shared `is_operating` classification gap (also surfaces in `diversified_segments`); consider adding `AMTD` to `_known_holdco`. Not a `geographic_global` gate defect.

### financials_value:1657 — CLEAN
`is_financial & ~is_reit & ~fund_vehicle & mcap≥50M & pb∈[0.15,1.0) & roe≥10% & (0<p_e≤15 | p_e NaN)`. Correctly targets banks/insurers on BOOK+ROE; the `_known_holdco` exclusion was (correctly) reversed — DDEJF/DC-A.TO (Dundee, roe 55%, pb 0.86) are legitimate discounted financial holdcos here; their -125% "op margin" is holdco noise, per calibration. Cheap Asian banks/insurers at 0.2–0.9x book with roe 10–25% and p_e 2–8 are genuine. Minor watch-items (not fixes): the `pb≥0.15` floor and `mcap≥50M` floor could each nick a genuine sub-0.15x home-listed bank or a nano-financial, but both are defensible anti-artifact guards.

### net_cash_returner:1674 — PROMOTES-JUNK
`is_operating & net_cash≥30% & _returning(div/buyback/shrink)`. No melting floor.
- 290 of 2,033 firers are operating melters. Examples: **YXT** (op -41%, roce -97%, roe -105%), **DCGO** (op -29%, roce -95%, roe -98%). A company returning cash while destroying capital is the opposite of the thesis.
- Fix: add `& _not_melting`.

### cundill_deep_value:1823 — CLEAN
Strict multi-criteria Cundill gate (pb<1 & near-low & p_e≤min(10,1/bond) & profitable-no-deficit & dividend & judicious-debt). Only 181 fire; top-15 all cheap, profitable, dividend-paying (pb 0.18–0.9, p_e 2–10, positive roce). The `_c4` no-deficit + `_c5` dividend legs already screen out melters. Working as designed.

### negative_ev_value:2367 — PROMOTES-JUNK
`is_operating & mcap<5e9 & (neg/low EV | pb<0.7) & (fcf>0 | ebitda>0 | net_cash≥50%)`.
- The `ebitda>0`-alone survivability leg is too weak: **463** firers have roce<-5% (795 melters total). Examples: **FOM.CO** (op -55%, roce -98%, roe -53%), **WLN.PA** (roce -99%, roe -78%).
- NOTE: the ">100%-cash" names here are NOT a defect — cash exceeding EV IS the thesis; the defect is only the melting-operating subset.
- Fix: add `& _not_melting` (leaves the negative-EV cash-floor thesis intact, removes the burners).

### templeton_pessimism:2470 — PROMOTES-JUNK (mild)
`is_operating & cheap-vs-normalized-EBITDA & near-5y-low & off-52w-high & (fcf>0|ebitda>0|net_cash≥30%)`.
- 157 firers have roce<-5%. BUT Templeton deliberately buys trough cyclicals, so a *negative op margin at trough* is the thesis, not junk — do not over-tighten. The genuine violators are the terminal decliners: **DCGO** (op -29%, roce -95%, roe -98%), **1V5.F** (roce -5.9%, roe -8.7%). (Names like JUSTDIAL op +25%/roce -98% are negative-capital-base artifacts, not melters — keep.)
- Fix: add `& _roce_now_ok` (mild — does NOT fail a positive-op trough cyclical; only fails known-negative current roce). Prefer this over the stricter `_not_melting` here.

### oak_resource_leverage:2040 — CLEAN
`sector∈{Materials,Energy} & ev_ebitda<8 & clean_bs & net_cash≥20% & ebitda_margin≥25% & cash_yield≥8% & beaten_down`. Only 18 fire; all high-margin (36–63%), high-roce (25–82%) net-cash miners. Tight and correct. (DRDGF fcf_yield -64% passes on robust/owner-earnings yield — legitimate gold-miner capex year, roce 23%.) No defect.

### oak_deleveraging:2054 — CLEAN
`is_operating & _roce_now_ok & op>0 & yield≥10% & ebitda>0 & nde∈[1,3] & ebitda-rising & (div≥6%|capret≥6%) & int_cov>2`. Already carries the returns floor + positive-op requirement. Top-15 are levered cash generators paying 6%+ yields with positive roce. No defect.

### oak_deep_value:2068 — PROMOTES-JUNK
`is_operating & beaten_down(0.50) & (pb<0.7 | ncav≥0.5 | cheap_score≥0.5) & cash_pct_mcap≥0.20 & ebitda>0 & (fcf>0|cfo>0) & int_cov>1.5`. The comment says the FCF/CFO>0 leg is the "Belluscura gate" against burners — but a one-off positive fcf/ebitda defeats it.
- **115 of 1,025** firers are operating melters; 74 have roce<-5%. Examples: **RFT.AX** (op -55%, roce -24%, roe -35%, one-off fcf +64% carries it through), **UBI.PA** (op -149%, roce -69%, roe -95%), **RENT** (op -21%, roce -51%). Sibling `oak_order_conversion` already carries `_not_melting`; this one doesn't.
- Fix: add `& _not_melting`.

### oak_nav_discount:2102 — CLEAN
`Financials & nav_vehicle & nav_not_eroding(roe≥0) & (pb<0.7 | p_tb<0.7) & (div≥5%|capret≥6%)`. Correctly narrowed to real NAV vehicles (closed-end funds / trusts / holdcos / asset managers), operating brokers/banks excluded. op_margin/fcf here are meaningless (fund vehicles) per calibration — 1104.HK's -54% "op margin" (roe +53%) and COHN's -182% fcf (roe +46%) are portfolio noise, not defects. The `_nav_not_eroding` roe≥0 guard already blocks melting BDCs. No fix.

### oak_asset_floor:2111 — PROMOTES-JUNK (moderate)
`is_operating & mcap<500M & (net_cash≥40% | ncav≥80%) & pb∈(0,1.5) & (fcf>0|cfo>0)`. Strong Graham cash floor, but no melting guard.
- 178 of 1,269 firers are operating melters (142 roce<-5%). Examples: **DCGO** (op -29%, roce -95%, roe -98%), **0738.HK** (op -23%, roce -70%, roe -13%). (SOGP roce -96% but op +7%/roe +75% is a denominator artifact — kept by `_not_melting`, correctly.) The cash floor protects the balance sheet but not against operations eating it.
- Fix: add `& _not_melting` (consistent with oak siblings).

### oak_order_conversion:2122 — CLEAN
`is_operating & mcap<1e9 & ebitda>0 & (cfo>0|fcf>0) & _not_melting & (rev_accel>0|rev_yoy>5%) & oper_lev_any & ebitda-rising`. Already carries `_not_melting` + operating-leverage + acceleration legs. Broad (3,796) by design (lagging backlog proxy) but every survivability leg is present. No defect.

---

## Three highest-priority fixes

1. **Add `& _not_melting` to the four highest-breadth unguarded cheap-cash gates: `discounted_vehicle` (554), `net_cash_returner` (1674), `negative_ev_value` (2367), `oak_deep_value` (2068), and `oak_asset_floor` (2111).** These carry 178–795 confirmed operating value-traps each (CHGG, WISH, FOM, RFT.AX, DCGO, YXT) that a one-off positive FCF/EBITDA print sneaks past the cash legs. `_not_melting` is the already-calibrated, currency-neutral helper their guarded siblings (`dead_option`, `geographic_global`, `oak_order_conversion`, `oak_deleveraging`) use; it removes confirmed burners without touching a single cheap foreign nano. One line, five gates — the single biggest junk-reduction in the group.

2. **`diversified_segments` (956): add `& _roce_now_ok`; `templeton_pessimism` (2470): add `& _roce_now_ok`.** `diversified_segments` is byte-for-byte its guarded sibling `geographic_global` minus the floor (14 melters vs 3). For `templeton_pessimism` use the milder `_roce_now_ok` (not `_not_melting`) so genuine trough cyclicals with a negative spot op margin — the actual thesis — are preserved while terminal decliners (DCGO, 1V5.F) are cut.

3. **`tangible_value` (770): (a) add the `net_cash_pct_sane` (≤1.0) clamp** to drop the >100%-cash RED-verdict ADR shells (HOLO 677%, MLGO 366%) that pb≈0.1 corruption lets through; **(b) EXCLUDES-GOOD — broaden coverage** by falling back to `pb` when goodwill+intangibles are ~0/NaN, so the gate stops firing only on the 11.9% of names with EDGAR `tangible_equity` and can see cheap foreign hard-asset discounts (currently just 7 firers, all US).

## Clean (no change)
dead_option, concentrated_segments (risk-flag by design), financials_value, cundill_deep_value, oak_resource_leverage, oak_deleveraging, oak_nav_discount, oak_order_conversion, geographic_global.

Cross-cutting: **AMTD** leaks into operating screens (sector+industry NaN, name misses the financial regex) — add to `_known_holdco`.
