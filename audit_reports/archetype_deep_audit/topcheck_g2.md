# Top-Check Sweep G2 — 29 archetypes, TOP-10 vs stated MEASURES

Data: freshly regenerated `archetype_tags.csv` + `asymmetry_global.csv` (post event-sleeve / ghost-removal passes).
Method: `scratch_diligence_dump.py` (ETA-ranked) per archetype; the three trader setups additionally re-ranked by their own
`oneil_score` / `weinstein_score` / `kullamagie_score`. Known-intentional / invariant-guarded classes not re-flagged unless leaking.

## Verdict table

| # | Archetype | Firers | Verdict | One-line |
|---|-----------|-------:|---------|----------|
| 1 | arch_balance_sheet_return | 3553 | PASS | Top 10 all cash>EV / self-liquidating operating names (net cash 72–160% mcap) |
| 2 | arch_financials_value | 262 | **FLAG** | Dundee holdco tops ranks 1–2 — not a bank/insurer; + common/pref double line |
| 3 | arch_net_cash_returner | 2033 | PASS | Net cash 50–277% + real dividends/buybacks throughout (042420.KQ ghost at #8) |
| 4 | arch_sustainable_scaler | 926 | PASS | Durable 15–30% growers, flat share counts, cheap on EV/S (042420.KQ ghost at #2) |
| 5 | arch_oneil_canslim | 372 | **FLAG** | #1 HUNT.OL is a corrupt tape (+1289% mom, price above its own recorded 52w high, $15M rev shell) |
| 6 | arch_weinstein_stage2 | 4353 | **FLAG** | Score-top owned by thin OTC/ADR mirror lines with pct_off=0.0 fills and corrupt momenta (EYGPF +4200%) |
| 7 | arch_kullamagie_breakout | 1162 | **FLAG** | #1 BFNH is a defunct shell with an impossible print (price 3.2x its recorded 52w high, $17.8K revenue) |
| 8 | arch_cundill_deep_value | 181 | PASS | All six Cundill legs verified in top 10 (pb<1, pe<10, dividend, near lows) |
| 9 | arch_biotech_deep_value | 117 | PASS | Below-cash clinical developers; Galapagos double-counted at ranks 2–3 (0JXZ.IL + GLPGF) |
| 10 | arch_low_sbc_quality | 698 | PASS | Clean-SBC profitable names; EDUC (#6) carries a contradictory ratio pair (see notes) |
| 11 | arch_tax_efficient | 210 | PASS | All tops have positive op margin + pretax income with low ETR |
| 12 | arch_strong_coverage | 5880 | PASS | Top 10 all outright net cash with positive sane EBITDA margins |
| 13 | arch_diversified_segments | 208 | **FLAG** | AMTD Idea (#4) — investment bank leaking as "operating" via NULL sector+industry |
| 14 | arch_concentrated_segments | 406 | PASS | Negative-signal tag; tops genuinely single-segment-dominant |
| 15 | arch_geographic_global | 487 | **FLAG** | AMTD again (#8); VISN (#3) rev −84% is not "a real diversified operator" |
| 16 | arch_fastest_segment | 609 | **FLAG** | VISN (#3): consolidated revenue −84% yet tagged "hidden growth engine" |
| 17 | arch_bab_low_beta | 95 | PASS | Boring profitable low-vol names; BRDCY row is a mixed-currency line (gates read the sane side) |
| 18 | arch_bab_becoming | 1824 | PASS | De-risking shape honoured; #1 is the 042420.KQ ghost row (cross-cutting, see below) |
| 19 | arch_bab_multibagger | 162 | **FLAG** | ONEXF (#2) — Onex, a private-equity holdco, leaks via NULL sector+industry |
| 20 | arch_lynch_pegy | 4832 | PASS | Spot-checked pegy 0.07–0.49 in top 10; growth+income genuinely unpaid-for |
| 21 | arch_lynch_evgy | 7425 | PASS | Spot-checked evgy 0.008–0.09; EBITDA positive on the ratio path |
| 22 | arch_wolf_trifecta | 714 | PASS | 15–39% growers, CFO+, EV/S<3, cheap entry throughout |
| 23 | arch_wolf_turnaround | 731 | PASS | Low-margin names crossing to black, all inside the op-margin band |
| 24 | arch_wolf_value_catalyst | 490 | PASS | Net cash 50–159% + growth + CFO+ + cheap FCF |
| 25 | arch_wolf_emerging | 2 | PASS | Both firers are the SAME company (TRLV + TCNNF = Trulieve twice) — spirit fine, 100% dupe |
| 26 | arch_wolf_seal | 2326 | PASS | Inflection + mom ≥10% + multiple caps all honoured |
| 27 | arch_wolf_compounder | 196 | PASS | 25–51% accelerating growers at 1–5x EV/EBITDA, low dilution |
| 28 | arch_liger_asset_backed | 218 | **FLAG** | TTEC (#3): total_debt=0.0 corrupt row manufactures 74% "net cash" on a levered company |
| 29 | arch_liger_lagging_inflect | 724 | **FLAG** | MANO.L (#6): net_cash 118% of mcap directly contradicted by nde +7.2 and pb 37.7 |

**19 PASS / 10 FLAG.** The trader trio's flags are tape-quality, not thesis-logic; the fundamental flags cluster on two legs:
the NULL-sector+industry classification hole and net-cash legs that skip the contradiction guard.

---

## FLAG details

### 2. arch_financials_value — Dundee Corporation at ranks 1–2
`DC-A.TO` / `DDEJF` (same company, both lines): sector "Consumer Staples / Household Products", revenue $9.0M vs $493M cap
(p_s 48.9), roe 0.55 from investment gains, pe 2.26. The measure's own comment says **banks/insurers ONLY** — NAV vehicles
belong in oak_nav_discount. Dundee is deliberately forced into `is_financial` via the `_known_holdco` set
(archetype_tags.py ~line 280) to keep it out of operating screens, but the archetype's fund-vehicle exclusion
`_fin_fund_vehicle` (line 1627) only regexes the *industry string* ("Household Products" doesn't match), so the holdco
lands as the #1 "cheap bank". **Responsible leg:** `~_fin_fund_vehicle` — it should also exclude the `_known_holdco` set.
Secondary: `000540.KS` + `000545.KS` (Heungkuk Fire & Marine common + preferred line) both in the top 7 — a
preferred-line double count leaking into a P/B screen.

### 5. arch_oneil_canslim — corrupt tape at #1 (score-ranked)
`HUNT.OL` Hunter Group ASA: oneil_score 0.988, momentum_12m +1289%, price 13.62 **above** its own recorded
price_52w_high (10.90), roce 149%, rev_yoy +249% on $15M revenue. An internally inconsistent (likely unadjusted
corporate-action) tape, not a CAN SLIM leader. Ranks 2–10 (TIMEX.BO, HALO, SAF1R.RG, MRX…) are genuinely near highs with
real growth — spirit otherwise honoured. Note: Aya Gold & Silver appears twice (`AYA.TO` + `AYA`, the latter mis-sectored
"Diversified Telecommunication Services") — cross-listing double count inside the top 12.
**Responsible leg:** `_live_tape`/price-sanity — nothing rejects a price print that exceeds the stored 52w high.

### 6. arch_weinstein_stage2 — score-top owned by OTC mirror ghosts
Top-50 by weinstein_score: **41/50 have pct_off_52w_high exactly 0.0**, 29/50 are US OTC ADR mirror tickers, 14/50 carry
momentum_12m > 300% (`EYGPF` +4200% — a stable Thai utility; `BBAJF` +1180%; `H1FC34.SA` is a BDR of HollyFrontier,
a company that ceased to exist in 2022). Worse, 5 of the exact-0.0 rows are actually 20–50% below their own stored
`price_52w_high` (NWWCF −20%, CTXAF −37%, SEKEF −38%, DSECF −50%, GNGYF −25%) — the 0.0 is a fill artifact, not a
measurement. Since `_st2_overhead` and the 0.25-weight `pct52` ramp both max out at off-high = 0, the fill artifact is
what the sort rewards. **Responsible legs:** the `pct_off_52w_high` fill (0.0 sentinel on thin tapes) + `_live_tape`
(stale_tape misses low-print OTC mirrors); the `_ramp(_mom12,…)` leg is capped so the corrupt momenta don't add score,
but they do pass `_st2_trend`.

### 7. arch_kullamagie_breakout — shell prints at the score top
`BFNH` (#1, score 0.990): BioForce Nanosciences — revenue_ttm **$17,775**, all fundamentals NaN, price 6.10 = **3.2x its
own recorded 52w high** (1.90), momentum +663%, "mcap" $204M. A defunct OTC shell print, not a breakout leader.
`GLITTEKG.BO` (#4): revenue $468K, rev_yoy −97.7%, +628% momentum — pump shape. `1753.HK` (#3) sits at **1.2% of its 5y
range** — a 52w-high breakout at the bottom of a multi-year collapse, against the "near *rising* highs" spirit.
`HUNT.OL` (#2) is the same corrupt tape as O'Neil. **Responsible legs:** no liquidity/price-sanity gate on `_kk_near`
(price vs stored 52w high never cross-checked) and no 5y-range floor on the "rising highs" claim.

### 13/15. arch_diversified_segments + arch_geographic_global — AMTD Idea Group
`AMTD` (#4 diversified, #8 geographic): AMTD IDEA is a HK **investment bank / capital-markets group**; its row has sector
NaN + industry NaN + country "France" (wrong), so `is_operating` passes — the `_name_is_financial` NULL-both backstop
regex doesn't match "Amtd Idea Group". op_margin −3.36, net debt 5.6x mcap. An actually-leaking financial.
**Responsible leg:** `_name_is_financial` name-regex (no match for AMTD) → `is_operating` true.
Additionally `VISN` (#3 geographic): rev_yoy **−84%** with fcf<0 — passes the "real diversified operator" guard only via
`ebitda_margin > 0.05` on stale-period margins.

### 16. arch_fastest_segment — VISN as a "hidden growth engine"
`VISN` (#3): consolidated revenue −84% YoY; whatever segment lens fired is from a stale FY snapshot that predates the
collapse. `_not_melting` (line 320) only checks op-margin&FCF signs, so a revenue implosion with positive stale margins
passes. **Responsible leg:** `_not_melting` — no revenue-trend component; segment-signal vintage not reconciled against
TTM revenue. (STG at #1 — declining consolidated top line — is within the multi-lens design; noted, not flagged.)

### 19. arch_bab_multibagger — ONEXF
`ONEXF` (#2): Onex Corporation, a private-equity/asset-management holdco — sector NaN + industry NaN, name doesn't match
the financial regex, so it reaches `bab_quality` on portfolio accounting (op_margin 0.75, ev_sales 8.5). Same NULL-both
hole as AMTD. **Responsible leg:** `_name_is_financial` regex (add asset-manager/PE holdco names or route ONEXF like
Dundee's `_known_holdco`).

### 28. arch_liger_asset_backed — TTEC's fabricated net cash
`TTEC` (#3): row has **total_debt = 0.0** (TTEC carries ~$1B of real debt), which manufactures net_cash 74% of mcap and
nde −93.7; roe −1.01. The `_netcash_not_contradicted` guard can't fire because the corrupt debt also corrupts nde in the
same direction. **Responsible leg:** upstream debt ingest for TTEC (corrupt row) — the archetype's guard is right but is
blind when both fields corrupt together; a `total_debt==0 & large-cap-revenue` sanity check would catch it.

### 29. arch_liger_lagging_inflect — MANO.L contradiction
`MANO.L` (#6): net_cash_pct_mcap **+1.18** (118% of mcap) while net_debt_ebitda **+7.19** and total_debt £12.7M on a
£16M cap — direct in-row contradiction; pb 37.7 is also corrupt (real ≈0.4). It enters through `_clean_bs(1.5)`
(line ~1799), whose net-cash leg `net_cash_pct_c >= 0.20` does **not** carry the `_netcash_not_contradicted` check that
the sibling `liger_asset_backed` gate has. **Responsible leg:** `_clean_bs` — add the contradiction guard to its
net-cash arm.

---

## Cross-cutting residuals seen in the tops (not per-archetype flags)

1. **`042420.KQ` "Z Holdings Corporation" — identity-corrupt row.** Korean KOSDAQ ticker, currency KRW, src JP, carrying
   Yahoo-Japan-scale fundamentals (revenue 449B) and self-contradicting cash fields (net_cash_pct 2.77 with positive EV
   yet cash_gt_ev_flag=1). It appears in the top 10 of **seven** archetypes (net_cash_returner #8, sustainable_scaler #2,
   strong_coverage #3, bab_becoming #1, lynch_evgy #7, wolf_trifecta #2, wolf_turnaround #2, wolf_value_catalyst #5).
   One bad merge line polluting many books — highest-value single fix.
2. **Cross-listing double counts inside tops:** Dundee (DC-A.TO + DDEJF, financials_value 1–2), Galapagos (0JXZ.IL +
   GLPGF — the GLPGF line even carries a different name, "Lakefront Biotherapeutics" — biotech_deep_value 2–3), Trulieve
   (TRLV + TCNNF = the *entire* wolf_emerging archetype), Aya Gold & Silver (AYA + AYA.TO, oneil top 12), Heungkuk
   common+pref (financials_value 4/7).
3. **Corrupt-ratio rows surfacing in tops:** BRDCY (JPY debt vs USD mcap → net_cash_pct −3.72 next to nde 0.13,
   bab_low_beta #7); EDUC (ebitda_margin +0.37 vs op_margin −0.57 and rev −50%, low_sbc_quality #6 /
   concentrated_segments #7); VISN (roce +33% against rev −84%); FPIP.ST roce 0.72 implausible for Formpipe.
4. **Trader-family tape quality is the systemic theme:** the three trader archetypes now sort by their own scores as
   intended, and the *shape* of the scores is right — but the score tops are exactly where thin-OTC fill artifacts
   (pct_off=0.0), unadjusted corporate actions (HUNT.OL, BFNH) and dead-listing mirrors (H1FC34.SA) concentrate,
   because "at the high with huge momentum" is what a broken tape looks like. A price-vs-stored-52w-high consistency
   check (|price/price_52w_high − 1 − pct_off| tolerance) would sweep most of them in one pass.
