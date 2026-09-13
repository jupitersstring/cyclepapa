# Rank 1–10 / 30–50 deep audit — GROWTH / MULTIBAGGER / GARP / BAB / CAPITAL (16 archetypes)

Scope: names ranked 1–10 AND 30–50 by `entry_today_asymmetry` in each of the 16 family archetypes. Judged against the STATED SPIRIT + legs in `archetype_tags.py`. `$` = USD. `REV~`/`rev_usd` = FX-converted `revenue_ttm_usd`. Recent fixes (rev≥20M floor on cheap_sales_scaler/exceptional_evsg/growth_algo/tenbagger_path; midcap_garp EV-band + EV/EBITDA≥2; BAB missing-ADV fails liquidity) are NOT re-flagged as *new* — but see Finding 1, which shows one of them is inert. `[C]` = confirmed structural bug, `[T]` = tuning. Worst-first. No code edited.

---

## 1. [C] The `revenue_ttm >= 20e6` floor is FX-BLIND — the flagship fix does almost nothing outside USD

**Archetypes:** `cheap_sales_scaler`, `exceptional_evsg`, `growth_algo`, `tenbagger_path` (→`tenbagger_credible`), `sustainable_scaler`.

**Root cause (leg):** the floor compares **raw local-currency** revenue against a **USD** constant:
`(_num('revenue_ttm') >= 20e6)` — while `mcap` in the very same rules is correctly USD (`mcap = s('market_cap_usd')`, line 212). `revenue_ttm` is native currency, so an INR/KRW/JPY/IDR name with a trivially small USD business clears the floor because its local-currency revenue number is large.

**Evidence (firers whose `revenue_ttm_usd` < $20M that the floor was meant to exclude):**
| archetype | firers | leaking < $20M USD | worst example |
|---|---|---|---|
| tenbagger_path | 2686 | **303** | GOENKA.NS rev **$0.23M** |
| cheap_sales_scaler | 2580 | **233** | UMIYA.BO rev **$0.47M** |
| exceptional_evsg | 1422 | **196** | UMIYA.BO $0.47M; ZENIFIB.BO $2.2M; BENGALT.BO $6.4M (all in rank 1–10 band) |
| sustainable_scaler | 1018 | **57** | **SMMT.JK rev $5,361** (IDR ~16k/USD → 8.6e7 IDR passes `>=2e7`) |
| growth_algo | 536 | **45** | UMIYA.BO $0.47M |

BENGALT.BO (INR, `revenue_ttm` 5.30e8 = **$6.4M**, mcap $13M) and ZENIFIB.BO (INR, 4.33e8 = **$5.2M**, mcap $2.2M) still sit in the exceptional_evsg TOP-10 despite the "fix." An Indonesian **$5k-revenue** shell fires `sustainable_scaler`. The floor only bites USD / near-parity (EUR, GBP) filers; it is a no-op for every weak-currency market — which is where the sub-scale-nano problem actually lives.

**Fix (minimal, preserves intent):** feed the floor the FX-converted column that already exists in the data — `revenue_ttm_usd` (col 152 of asymmetry_global; mirrors the `market_cap_usd` treatment). Replace `_num('revenue_ttm') >= 20e6` with `_num('revenue_ttm_usd') >= 20e6` (or `revenue_ttm * fx_to_usd >= 20e6`) in all five rules. Over-inclusion only — no name is wrongly excluded — so this is pure precision gain (~830 firer-instances corrected).

---

## 2. [C] `insider_conviction` is a community-BANK screen — no `is_operating`, and `pb<2.5` is the leg banks pass by definition

**Rule (2059):** insider buy flag & net-buyer & mcap<20e9 & (`ev_ebitda<=15 | pb<2.5 | fcf_yield>=0.03 | cheap_any`). No operating gate. For a bank, EV/EBITDA and fcf_yield are meaningless and `pb<2.5` is nearly always true, so the "value-oriented" leg is free — the archetype degenerates into "an insider bought a bank near book," precisely the violation flagged in the brief.

**Offending firers (~18 of the 30 in ranks 1–10 / 30–50):** FXNC (bank, pb 1.48 — the textbook routine-bank-near-book buy), PCB, ECBK, EMYB, RVSB, BOTJ, FDSB, SRBK, HTBK, UWHR, FDBC (all community banks); GPMT (**mortgage REIT**, p_tb 97); OPAD (real estate iBuyer); HUIZ (China insurer, EV/EBITDA −44); LPRO, MDBH (financials); **PMO, IGR (closed-end funds** — "insider" buying in a CEF is meaningless). Only ~1/3 of the sheet is genuine operating-company insider conviction.

**Fix:** add `& is_operating` (financials already have `arch_financials_value`). If bank insider-buys are wanted, route them to a dedicated financial-insider tag that requires the STRONG legs (`insider_cluster_buy_flag | insider_10pct_buy_flag`, not a lone officer) AND real cheapness for a financial (`pb < 1.0`), not `pb<2.5`.

---

## 3. [C] `is_operating` is simply absent from six operating-only theses → financials / REITs / utilities leak

None of these gate on `is_operating`; all use EV/EBITDA, margins or ROIC that are meaningless for financials:

- **`midcap_garp`** (1273): ONEXF (PE/asset mgr), SLDE (insurer), **VNAA.F & VNA.F (residential REIT, listed twice)**, FHI (asset mgr), BOLSY (B3 exchange), ACGLO (Arch Capital insurer), AY3.F (utility yieldco). REIT low P/E is an IFRS revaluation-gain artifact — a value trap.
- **`wolf_trifecta`** (1698): 8699.T Sawada Holdings, HNNA Hennessy Advisors, GBX.BK Globlex — all securities/asset-management "revenue." (Siblings `wolf_turnaround`/`value_catalyst` carry `& is_operating`; this one still doesn't.)
- **`cheap_per_roiic`** (658): QNTO, WBS (banks), HGBL, AERT (financials), GNE (utility).
- **`capital_light_pivot`** (1037): XYF, COHN, OPY (financials); a mortgage/broker is not "capital-light."
- **`bab_becoming`** (1102): GDOT, FTK.DE, NOAH, VPGLF (financials), 6989.HK (RE).
- **`bab_low_beta` / `bab_multibagger`** (1091/1112): HGBL, RDN (mortgage insurer), ANIM.MI, AZM.MI (Azimut), PJT Partners.

**Fix:** append `& is_operating` to all six. Consistent with the rest of the framework; financials have their own book-value archetypes.

---

## 4. [C] Backward-looking ROIC gates with NO current-state floor → melting ice cubes

**`cheap_per_roiic`** (659: `cheap_per_roiic<=1.5 & roiic_lindy>0.10`) and **`capital_light_pivot`** (1040: `n_yrs_roic_pos>=3 & (roic_accel>0 | roic_lindy>0.10)`) qualify on a *trailing* ROIC window with no check that the business is still profitable or growing today. Result — names whose economics have since reversed:

- cheap_per_roiic: **TTEC** (ROCE −9.7%, ROE −101%, rev −3.2%, mom −60% — rank 1), **RMNI** (ROCE −73.6%, P/E 72), **CATO** (EBITDA margin **0.4%**, EV/EBITDA 134, nde 29), **SBC** (rev −15.5%), **NUS** (rev −14.3%, FCF yield −24.7%), **KPLT** (FCF yield −40.7% burn).
- capital_light_pivot: **HURC** (ROCE −6.1%, EBITDA margin −5.9%, rev −6.2% — pivot reversed), **ACTG** (ROCE −2.9%, "growth" is +133% M&A roll-up).

**Fix:** require a live floor alongside the lindy leg — `((roce>0) | (roic_after_sbc>0))` today AND `(rev_yoy>−0.05) | (rev_accel>0)`. (Same prescription as the rank-5–20 audit; not yet landed.)

---

## 5. [C] `wolf_trifecta` + `bab_becoming`: no revenue floor and de-risking legs too weak

- **`wolf_trifecta`**: no revenue floor at all → sub-scale nano **BENGALT.BO ($6.4M rev)** in rank 1–10. Add the (FX-fixed) `revenue_ttm_usd>=20e6` floor + `is_operating`.
- **`bab_becoming`** (worst BAB sheet): the de-risking conjunction `((ebitda_margin_delta>=0.01)|interval_inflect_any) & ((fcf_inflection>0)|(ebitda_inflection>0)|(fcf_margin_v>0.0))` lets a single positive `fcf_margin` on a shrinking loss-maker pass. Firers that are the *antithesis* of "de-risking toward boring-safe": **RFT.AX** (rev −38%, EBITDA margin −49%, ROCE −24%, mom −50%), **TTEC** (distressed, nde −93.7), **Chorokbaem 047820.KQ** (rev −30%), **Denko 8176.KL** (EV/EBITDA −4.5, lossmaker), **WSI.AX** (rev −32%), **DC-A.TO Dundee** (financial holdco mislabeled Consumer Staples, $9M rev, op margin −125%). **Fix:** require `ebitda_margin>0` (use `ebitda_margin_sane`), `is_operating`, revenue_ttm_usd floor, and `(rev_yoy>−0.05)|(rev_accel>0)`; drop the standalone `fcf_margin_v>0` OR-leg.

---

## 6. [C/T] `midcap_garp` residuals the EV-band fix doesn't cover

The EV/EBITDA≥2 + EV-sanity band correctly killed the Nitori/Galaxy near-zero-EV artifacts. Two residuals remain:
- **PAH3.DE Porsche Automobil Holding** — an investment **holding company** whose `ebitda_margin` reads **1.063 (106%)** because "EBITDA" is equity-method income from its VW stake; ROCE **−0.06%**, P/E 93, nde 18.2. It passes `_roiic_proxy` on `ebitda_margin>=0.18` (106%!) and `_val_good` on the EV/EBITDA yield. Not a GARP compounder. **Fix:** clamp the margin used by `_roiic_proxy`/val to `ebitda_margin_sane` (0–0.6 band already defined at line 264).
- **Duplicate cross-listings double-counting:** VNAA.F **and** VNA.F (Vonovia) at ranks 6–7; NETTF **and** NTES (Netease). **Fix:** ADR/dual-line dedupe on the book.

---

## 7. [T] NULL-sector **and** NULL-industry financials bypass the `is_operating` backstop

`is_operating`'s backstop (line 248–256) keys on the **industry** string when sector is null. When BOTH are null, an insurer/holdco slips through as "operating": **SLDE** (Slide Insurance Holdings — leaks into `exceptional_evsg` rank 48 and `midcap_garp`), **ONEXF** (Onex, PE — `midcap_garp`), **TUGU.JK** (PT Asuransi Tugu — see Finding 8). Adding `is_operating` (Finding 3) will NOT catch these. **Fix:** extend the backstop with a name-token check — `name` contains `insurance|assurance|bancorp|bank|holdings? .*financ|asuransi|capital` → non-operating.

---

## 8. [C] `net_cash_returner`: insurer float booked as "net cash"

Rule (1498) is otherwise on-thesis (net cash ≥30% mcap + actively returning + `is_operating`). Leak: **TUGU.JK** (PT Asuransi Tugu, an **insurer**; sector & industry both null → bypasses the backstop per Finding 7; EV/EBITDA −2.0, net_cash_pct 1.47 — the "net cash" is an investment/float portfolio). Minor secondary: raw unclamped `net_cash_pct` admits 150–280%-of-mcap holdco artifacts (Z Holdings 277%, Tianjin Dev 190%). **Fix:** Finding-7 name backstop; optionally gate the ≥30% leg on `net_cash_pct_sane` (≤1.0) with a separate deep-net-cash home above that.

---

## 9. [T] `capital_returner`: upper yield band loose; trailing-yield staleness (low priority — sheet is otherwise clean)

`is_operating` + FCF-covered + 5–30% band already exclude REIT/BDC mandatory payouts and >30% return-of-capital artifacts. Residual: a crashed price inflates the trailing yield — **EZZ.AX** shows div 10.5% on a price down 81% (mom −78%). All visible firers sit under 15%, so impact is small, but the 30% cap is generous. **Fix (optional):** tighten the upper bound to ~0.20, or damp names whose yield is a stale-price artifact (`pct_off_52w_high` very negative + price staleness).

---

## CLEAN (honour thesis in ranks 1–10 / 30–50, given the fixes above)

- **`sustainable_scaler`** — cleanest sheet; only defect is the FX-blind floor (Finding 1). With `revenue_ttm_usd`, on-thesis.
- **`growth_algo`** — clean apart from Finding 1.
- **`cheap_sales_scaler`** — `is_operating` + floor both present and working (0 financial leaks); only defect is Finding 1's currency blindness.
- **`tenbagger_path` / `tenbagger_credible`** — structurally sound (USD mcap, op-lev + owner-cash + stable-share reality gates); defects are Finding 1 (FX floor) and a minor lumpy-revenue residual (B9A.F BioArctic, a drug developer whose +345% is a one-off lecanemab licensing step — optional `is_drug_developer`/lumpy guard).
- **`net_cash_returner`** — on-thesis except TUGU.JK (Finding 8).
- **`capital_returner`** — on-thesis (Finding 9 is optional tuning).

---

## Highest-impact fixes, worst-first

1. **Make the revenue floor FX-aware** (`revenue_ttm_usd`) in cheap_sales_scaler / exceptional_evsg / growth_algo / tenbagger_path / sustainable_scaler. Corrects ~830 sub-$20M-USD firers; the current "fix" is a no-op outside USD. (Finding 1)
2. **`insider_conviction`: add `is_operating`** (or a strong-leg financial variant); today it is ~2/3 community-bank/REIT/CEF insider buys near book. (Finding 2)
3. **Add `& is_operating`** to midcap_garp, wolf_trifecta, cheap_per_roiic, capital_light_pivot, bab_becoming, bab_low_beta, bab_multibagger. (Finding 3)
4. **Add a live-state floor** (`roce>0`/`roic_after_sbc>0` today + `rev_yoy>−0.05|rev_accel>0`) to cheap_per_roiic, capital_light_pivot, and bab_becoming's de-risking legs. Kills the melting-ice-cube leak (TTEC, RMNI, CATO, NUS, HURC, ACTG…). (Findings 4–5)
5. **Name-token backstop for NULL-sector-AND-NULL-industry financials** (SLDE, ONEXF, TUGU); `ebitda_margin_sane` clamp + ADR dedupe on midcap_garp (PAH3.DE, Vonovia×2, Netease×2). (Findings 6–8)
