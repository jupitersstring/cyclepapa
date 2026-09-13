# Deep-tail audit (ranks 50–100) — Group 2 (27 archetypes)

Scope: firers ranked **50–100** by `entry_today_asymmetry` in each of my 27 archetypes, judged against the STATED SPIRIT + legs in `archetype_tags.py`. `$` = USD; `REV` figures converted via `revenue_ttm_usd`. Traders (oneil/weinstein/kullamagie) judged on price-action spirit only. Already-guarded invariants (financials/REIT/utility on *operating* archetypes, net-cash levered stubs, sub-$20M-rev *growth* firers, declining-rev inflections, data corruption, preferreds, sub-$2M shells, clinical biotech in fundamental screens) are NOT re-flagged. `[C]` = structural bug, `[T]` = tuning. Worst-first. **No code edited.**

---

## 1. [C] `financials_value` — the tail is closed-end funds + REITs, not banks/insurers
**Thesis:** banks/insurers screened on BOOK (`P/B` 0.15–1.0) with real returns (`ROE`≥10%) — "the home for the financials the operating value archetypes exclude."
**Offenders (50–100):**
- **Closed-end funds / BDCs / investment trusts:** TEI (Templeton EM Income), PGP (PIMCO StocksPLUS), EMD (WA EM Debt), WEA, CHW (Calamos), LGI (Lazard), ACP (Aberdeen), GAM (General American Investors), RITPF (RIT Capital), BDJ (BlackRock Enh. Eq. Div.), GDV (Gabelli), Senvest, APAC Resources, Helios Fairfax. Giveaway: industry `Capital Markets` + name `Fund/Trust`, `P/B` 0.87–1.0 (that's **discount-to-NAV**, not cheap book), `ROE` = the distribution rate, `net_cash_pct` ≈ 1.0 (all-portfolio).
- **REITs:** Arena REIT, Sabana REIT (SBBSF/M1GU), Turkish GYOs (Marti/Panora/Halk/Vakif). Giveaway: sector `Real Estate` — they enter because `_fin_ind_kw` contains **`'reit'`**, so `_ind_is_financial` fires. Book-value screening a REIT is the exact **IFRS-revaluation value trap** the framework warns about; `ROE`≥10% is fair-value-gain inflated.

**Root-cause leg (1546):** `is_financial & (_fpb 0.15–1.0) & (_froe≥0.10)` — `is_financial` is too broad: it swallows REITs (via the `'reit'` keyword) and fund vehicles (Capital Markets CEFs/BDCs).
**Fix:** `& ~is_reit` on `financials_value` (route REITs to a dedicated REIT-on-book tag or drop), and exclude fund vehicles — a CEF/BDC guard, e.g. `~name.str.contains(r'\b(fund|trust|closed[- ]end)\b')` (or a `is_fund` flag). Keep banks/insurers/consumer-finance.

---

## 2. [C] `wolf_turnaround` — no revenue floor and no lower bound on how deep in the red
**Thesis (1777):** a loss-maker *crossing into the black* while still growing; `op_margin<0.15` caps out established earners.
**Offenders (50–100):** **CTO.SI** Hong Lai Huat (rev **$2.8M**, op_margin **−65%**, rev_yoy **+2626%** base-effect), **0128.HK** ENM (rev **$2.5M**, op_margin **−46%**, `P/S` **40**), **1871.HK** China Oriented (op_margin −27%, roce −8.9%), plus SPOT.V/SPOFF (same co, EarthLabs = GoldSpot, double-count).
**Root cause:** the gate has **no `revenue_ttm_usd` floor** (siblings `wolf_trifecta`/`wolf_compounder` require ≥10e6) and `op_margin<0.15` has **no lower bound**, so names at −46%/−65% op margin — nowhere near "black" — pass on an inflection flag + a base-effect `rev_yoy`.
**Fix:** add `(_num('revenue_ttm_usd') >= 10e6)`, and lower-bound the margin so it is *approaching* black — e.g. `(op_margin > -0.20)` or `ebitda_margin_sane > 0` alongside the inflection legs.

---

## 3. [C] `bab_becoming` — still admits negative-ROCE loss-makers and declining-revenue names
**Thesis (1160):** a business *de-risking toward the boring-safe low-beta profile* (margins expanding, cash inflecting, deleveraging).
**Offenders (50–100):** **lastminute.com** (LSMNF/09B.F, roce **−24%**), **Ming Yuan Cloud** 0909.HK (op_margin **−14%**, rev_yoy **−10.5%**), **Water Oasis** 1161.HK (roce **−55.6%**), Ecocab (roce −7.3%), Shearwater DTW1.F (roce −7.8%, rev −15%), **TRIGYN.NS** (rev_yoy **−25%**), ONEXF (Onex PE-firm; NULL/NULL-financial hole).
**Root cause:** the rank-1050 prescription (`ebitda_margin>0`, `(rev_yoy>−0.05)|rev_accel>0`, live-state floor) was **only partially landed** — the code got `revenue_ttm_usd≥20M`, `fcf_margin>−0.05`, `nde≤3`, but **no current-ROCE floor and no not-shrinking gate**, so shrinking loss-makers still read as "becoming safe" (the antithesis).
**Fix:** add `_roce_now_ok` (or `ebitda_margin_sane > 0`) **and** `((rev_yoy_c > -0.05) | (rev_accel > 0))`.

---

## 4. [C] `fastest_segment` — no revenue/market-cap floor and no current-profitability guard
**Thesis (940):** a *hidden growth ENGINE the consolidated number masks* — a fast segment inside a real operator.
**Offenders (50–100):** **CKX** Lands (rev **$0.84M**, consolidated rev_yoy **−45%**), **BYAH** Park Ha Biological (mcap **$2M**, EBITDA margin **−952%**, mom **−99%**); softer: AZTA (roce −13.8%), HIVE (roce −16.4%).
**Root cause (940):** `is_operating & segment_count≥2 & seg_inflect_any & _seg_any_growth≥0.10` — **no `revenue_ttm_usd` floor, no mcap floor, no `_roce_now_ok`**, unlike the siblings (`geographic_global` carries `_roce_now_ok` + fcf/margin gate; `diversified` gates operating). A declining $0.84M land shell or a −952%-margin $2M shell is not a "growth engine." (This is the sub-scale hole that the growth-archetype floor does NOT reach, because the mutation test classes fastest_segment as a segment-inflection tag, not a growth firer.)
**Fix:** add `(_num('revenue_ttm_usd') >= 20e6)` and `_roce_now_ok`.

---

## 5. [C] `wolf_value_catalyst` — no current-profitability floor; "cash-generative" leg passes loss-makers
**Thesis (1799):** a *growing, cash-generative* microcap with a fortress balance sheet at a cheap FCF yield.
**Offenders (50–100):** **SOGP** Sound Group (roce **−95.6%**), **Denko** 8176.KL (op_margin −6.1%, roce −2.4%, EV/EBITDA −4.5), **KT** 2693.T (roce −3.8%), **AUDGF** Audinate (op_margin **−25.7%**), Yooshin (op_margin −0.5%).
**Root cause:** requires `cfo_ttm>0` but has **no `_roce_now_ok`/`op_margin>0`** — a working-capital-positive CFO with deeply negative operating economics passes as "cash-generative." SOGP/Denko are the same melting names guarded out of the quality book (`low_sbc_quality` cites "SOGP roce −0.96").
**Fix:** add `_roce_now_ok` (or `(s('op_margin')>0)`).

---

## 6. [C] `lynch_evgy` — an EV/EBITDA screen with NO `is_operating`; financials leak
**Thesis (1231):** EV/EBITDA-GY ≤ 0.6 (cheap relative to EBITDA growth + yield).
**Offenders (50–100):** **TUGU.JK** (insurer, EV/EBITDA −2.0), **OM2 Network** (Diversified Financial), **New Constructor's Network** (roce **−52%**), **Indara Insurance** (op_margin −9.6%), plus distressed **TTEC** (roe **−101%**).
**Root cause:** `lynch_evgy` has **no `is_operating`** — but it is EV/EBITDA-based, and the whole framework holds EV/EBITDA meaningless for financials (float distorts EV). Contrast **`lynch_pegy`**, which legitimately omits `is_operating` because it is P/E-based (P/E is valid for banks). So the P/E variant is fine; the EV variant is not.
**Fix:** add `& is_operating` to `lynch_evgy` only (leave `lynch_pegy` as-is).

---

## 7. [C/T] `biotech_deep_value` — FX-inflated `net_cash_pct` + profitable non-developer pharma read as "below cash"
**Thesis (2987):** a *drug developer trading at/below net cash* — downside is the balance sheet, not the trial. Pre-profit pipeline names.
**Offenders (50–100):** **Sundrug** SDGCF (a **drugstore RETAILER**, net_cash 6.8x, roce +17.8%), **Kalbe Farma** PTKFY (net_cash **2094x** — pure FX artifact), **Otsuka / Ono / Shionogi / Kissei** majors reading EV<0 (ev_ebitda −0.4 to −2.4, net_cash 7–22x) — profitable diversified pharma, the OPPOSITE of a below-cash special situation.
**Root cause:** the `_bdv_ncash >= 0.5` leg has **no upper sanity clamp** and `net_cash_pct_mcap` is FX-blind for weak-currency filers (cash local vs a denominator that mis-scales → 7×–2094×), plus `_is_drug_dev` is broad enough to catch pharma retail (Sundrug) and mature majors. `net_cash_pct` is NOT in the guarded data-corruption list, so these slip through.
**Fix:** clamp the net-cash leg to a sane band (e.g. `0.5 <= _bdv_ncash <= 3.0`) or require the below-cash reading be corroborated (a genuinely negative EV with consistent `nde`); and/or exclude solidly-profitable established pharma (`~(roce > 0.10 & op_margin > 0.10)`) so the tag keeps its pre-profit-pipeline spirit.

---

## 8. [T] `concentrated_segments` — no `is_operating`; financials dominate the tail
**Thesis (892):** concentration-risk flag (HHI≥0.70 or largest≥70%). Fires as a **negative** signal.
**Offenders (50–100):** ATLC, HCI, AGO, OSPN, BUSE, NRIM, COF, WSBC, ESNT, APO, WTM, AMCX, GABC — **14+ financials**.
**Root cause:** the **sibling `diversified_segments` carries `is_operating` with the explicit note "segment-revenue-HHI is the wrong lens for financials"** (884); `concentrated_segments` omits it. Lower severity (it's a negative flag), but the same rationale applies — a bank's reported "segments" don't carry the "one bad year sinks it" meaning.
**Fix:** add `is_operating &` for consistency with its sibling.

---

## 9. [T] `wolf_trifecta` — no current op-margin floor (sibling `wolf_compounder` has one)
**Thesis (1762):** double-digit growth + **improving margins** + operating leverage, cheap entry.
**Offenders (50–100):** 6580.T Writeup (op_margin **−48%**), 7043.T Alue (**−20%**), PERF Perfect Corp (roce **−37%**), 09B.F lastminute (roce −36%), 26Y.SG Yatra (roce −0.9%).
**Root cause:** `oper_lev_any` is EBITDA-momentum-based, so a name with positive EBITDA inflection but deeply negative *operating* margin passes an "improving margins" claim. The **sibling `wolf_compounder` requires `op_margin>0`** (1852); `wolf_trifecta` does not.
**Fix:** add `(s('op_margin') > 0)` (or `ebitda_margin_sane > 0`).

---

## Cross-cutting (known / note-only — not re-flagged as new)
- **NULL-sector AND NULL-industry financial hole (prior Finding 7) persists:** the name-backstop regex misses non-English/local entity tokens, so **TUGU.JK** ("Asuransi" = insurer) leaks operating into `balance_sheet_return`, `lynch_evgy`, and the `fastest_segment` corroboration leg; **ONEXF** (Onex, PE) into `bab_becoming`. Extend the backstop with `asuransi|assurance|reinsurance|life(co)?|sekuritas|kapital` etc.
- **Unclamped `net_cash_pct` (prior Finding 8):** `net_cash_returner` / `balance_sheet_return` still admit FX/holdco artifacts (Shanghai Diesel 767%, YEAHKA 478%, Secuve 141% while diluting **+389% shares**). Gate the ≥0.20/≥0.30 legs on `net_cash_pct_sane`.
- **ADR / dual-line / preferred duplicates** inflate every book (Advantest ADTTF/ATEYY/6857.T ×3 in oneil; Great-West GWO-PI/PQ/PT/PS ×4 preferreds in weinstein; Clinuvel ×4, Otsuka/Ono/Sysmex/Mayne dual-lines in biotech). Cosmetic, but a dedupe would clean the tails.

---

## CLEAN (honour thesis in ranks 50–100, given the fixes above)
- **`capital_light_pivot`** — quality capital-light growers; `is_operating`+`_roce_now_ok` already present.
- **`capital_returner`** — `is_operating` + FCF-covered + 5–30% band hold (per prior review).
- **`balance_sheet_return`** — deliberate home for cash-rich/uncovered/negative-EV runoff; negative-ops cash-rich names ARE the point (only TUGU NULL/NULL leak).
- **`sustainable_scaler`** — genuine small-cap compounders; one marginal (Forian, op_margin −51%).
- **`low_sbc_quality`** — profitable, SBC-clean operators; `_roce_now_ok` holds (only a NULL/NULL healthcare-REIT edge, HLTC).
- **`tax_efficient`** — `op_margin>0` + `pretax>0` guards do their job.
- **`strong_coverage`** — net-cash/coverage + positive-EBITDA gates hold.
- **`cundill_deep_value`** — deliberately includes financials/REITs on book; P/B<1 + dividend + cheap-to-lows all present.
- **`diversified_segments`** — large-cap operating multi-segment names, on-thesis.
- **`geographic_global`** — global operators; `_roce_now_ok` + fcf/margin gate hold.
- **`bab_low_beta` / `bab_multibagger`** — strong `bab_quality` gate (fcf_margin>0, ebitda≥10%, roce≥10%|cash-conv, nde≤2.5) holds.
- **`lynch_pegy`** — P/E-based; financials legitimate (the EV variant is the one needing `is_operating`).
- **`net_cash_returner`** — net-cash dividend-payers on-thesis (apart from the known unclamped-`net_cash_pct` item).
- **`oneil_canslim` / `weinstein_stage2` / `kullamagie_breakout`** — on price-action spirit (leaders/breakouts near 52w highs); fundamentals irrelevant by design.
- **`wolf_emerging`** — only 2 firers; cannabis + positive-CFO + clean-SBC + cheap gate intact.

## Highest-impact, worst-first
1. **`financials_value`**: exclude `is_reit` and fund vehicles (CEF/BDC) — the tail is NAV-priced funds and IFRS-revaluation REITs, not banks. (F1)
2. **Revenue/loss floors on `wolf_turnaround`** (rev_usd≥10M + op-margin lower bound) and **`fastest_segment`** (rev_usd≥20M + `_roce_now_ok`) — both admit sub-$3M shells at −46% to −952% margins. (F2, F4)
3. **Land the `bab_becoming` fix in full** (`_roce_now_ok` + not-shrinking) and add `_roce_now_ok`/`op_margin>0` to **`wolf_value_catalyst`** and **`wolf_trifecta`** — the melting-ice-cube leak (lastminute, SOGP, Denko, Ming Yuan, Writeup). (F3, F5, F9)
4. **`is_operating` on `lynch_evgy`** (EV/EBITDA screen) and **`concentrated_segments`** (match its sibling). (F6, F8)
5. **`net_cash_pct` sanity clamp** on `biotech_deep_value` (below-cash leg) + `net_cash_returner`/`balance_sheet_return`, and extend the NULL/NULL financial name-backstop (`asuransi|sekuritas|…`). (F7, cross-cutting)
