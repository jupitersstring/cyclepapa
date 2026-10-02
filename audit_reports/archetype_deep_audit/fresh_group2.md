# Fresh top-of-book quality review — Group 2 (27 archetypes)

Fresh-eyes assessment of the **TOP 10** firers (ranked by `entry_today_asymmetry` in the diligence dump) against each archetype's stated thesis + legs in `archetype_tags.py`. Question asked of each: *would a practitioner recognise these as good examples of the idea, and is the gate a faithful translation?* Traders judged on price-action spirit only. Already-guarded invariants NOT re-flagged. No code edited. `$` = USD; Asian display `market_cap` is local currency (gate uses USD `mcap` — not a bug).

**Cross-cutting notes (apply to several below):**
- **ETA-ranked books surface cheapness, not the archetype signal.** Only 7 archetypes have a score in `ARCH_SORT_OVERRIDES`; the 3 momentum traders and the whole Wolf family sort by `entry_today_asymmetry`. For momentum/breakout theses that ranking is *antithetical* — it floats flat, cheap, deep-value names ahead of the actual price leaders. `oneil_score`/`weinstein_score`/`kullamagie_score` are computed but unused for ranking.
- **Distressed neg-EV Chinese micro-ADRs** (JFU, STG, VIOT, HERE, IH…) top several cheapness-ranked *quality* screens: cash > mcap makes ETA love them, positive-but-trivial operating economics clear the profit gates, and non-US names report ~0 SBC so "clean accounting" degenerates to "not US-listed."
- **Cross-listing double-counts** at top-of-book: Dundee (DC-A.TO/DDEJF), Galapagos (0JXZ.IL/GLPGF), Trulieve (TCNNF/TRLV).

---

## NEEDS-WORK

### `arch_wolf_turnaround` — top-of-book is profitable established earners, not turnarounds
Thesis: a loss-maker *crossing into the black* while still growing. **Top-10 reality (exact op_margin / roce):** Dongwoo +5.3% / **19.7%**, Kokusai +12.9% / **22.7%**, Muramoto +7.0% / **35.3%**, Austem +7.8% / **39.5%**, Mandom +5.0% / 6.4%. Only 1900.HK (op −4.6%) is a genuine near-turnaround. A business earning 35–40% on capital is not "crossing into black."
**Methodology:** the `op_margin < 0.15` upper cap was meant to exclude established earners but instead admits every structurally-low-margin *healthy* business (distributors, machinery, food); a soft inflection flag (`cfo_inflection>0`, `ebitda_first_pos`…) then fires on any routine CFO tick. **Fix:** require evidence of a *prior* loss / sign-flip this period (e.g. prior-year op or NI < 0, or `ni_first_pos`/`ebitda_first_pos` as a hard requirement rather than one of many OR-legs), and cap ROCE (a real turnaround isn't already earning 35%).

### `arch_low_sbc_quality` — a "quality" screen topped by melting neg-EV micro-ADRs
Thesis: clean-accounting, genuinely profitable compounders. **Top-10 reality:** JFU (roce **0.3%**, ev/sales −165, mom −48%, −73% off high), STG/VIOT/HERE/FEDU (all neg-EV, down **56–74%**, roce 0.3–1.6%), KPLT (US lease-to-own, gross margin 18%, ebitda-margin 74% artifact). These are distressed, sub-scale, near-zero-return names — the opposite of quality.
**Methodology:** `sbc_pct_revenue < 2%` is a non-signal outside the US (missing→0), so the "clean accounting" leg collapses to "non-US"; `_roce_now_ok` only rejects *negative* roce, so 0.3%-return names pass; and ETA rewards the neg-EV cheapness. **Fix:** require SBC actually *present* for the clean-accounting claim, add a real returns floor (roce ≥ ~8–10%, not just ≥0), and a not-collapsing / scale guard.

### `arch_financials_value` — top-10 is preferreds + an investment holdco, not banks/insurers
Thesis: banks/insurers on book (P/B 0.15–1.0, ROE ≥ 10%), REITs and fund vehicles excluded. **Top-10 reality:** DC-A.TO **+** DDEJF = Dundee Corp (an investment holding co, sector-misclassified "Consumer Staples/Household Products", $9M revenue, P/S 35–49 — the exact fund-vehicle class the screen tries to drop) ×2; **GWO-PI.TO, GWO-PQ.TO, SLF-PC.TO = Canadian preferred share lines** of Great-West Lifeco / Sun Life. Only ~4 genuine banks/insurers (Heungkuk, Sawada, CSC, OP Bancorp).
**Methodology:** the preferred scrub `^[A-Z]{1,5}-P[A-Z]?$` is anchored `$`, so an exchange suffix (`.TO`, `.V`) slips every Canadian preferred straight through — these same lines also leak into `weinstein_stage2` and `lynch_pegy`. Dundee is caught by `is_financial` (name/industry keyword) but missed by `_fin_fund_vehicle` because its name says "Corporation," not Fund/Trust. **Fix:** extend the preferred pattern to tolerate a trailing `.<exch>` suffix; broaden `_fin_fund_vehicle` to catch merchant-bank/holding vehicles by revenue-to-mcap or P/S sanity.

---

## MINOR

### `arch_bab_low_beta` / `arch_bab_multibagger` — the "quality" half admits operating loss-makers
Mostly genuine low-beta quality (CeoTronics, Perdoceo, KWS SAAT, Westell, Innoviva, Harmony). But `bab_quality` keys on `ebitda_margin ≥ 0.10` + (`roce ≥ 0.10` **OR** `cash_conversion ≥ 0.60`) with **no op_margin floor**, so D&A-heavy loss-makers pass: **GENL.L (op −46.6%, roce −1.6%, ebitda +64.5%)** tops both; GAIA (roce −7.4%, −68% off high) rides multibagger. Onex (PE firm) leaks via sector-NaN `is_operating`. **Fix:** add `op_margin > 0` (or `roce ≥ 0`) alongside the cash-conversion leg; tighten `is_operating` for sector-NaN asset managers.

### `arch_fastest_segment` — melting floor too low; collapsing-consolidated names admitted
Thesis: hidden growth engine the consolidated number masks. Membership admits **VISN (consolidated rev −84%)**, TLIH (−87% / −93% off high), **YOUL (op +0.4%, ebitda-margin 1%, −91% off high)**, STG (neg-EV distressed). `_not_melting` only fails a name that is *both* op-loss and FCF-burner (or roce < −5%), so near-zero-margin 90%-drawdown names squeak through. Mitigant: the real book ranks this one by `seg_inflect_confirmed`, not ETA, so ordering differs from this dump. **Fix:** raise the melting floor to a real margin/return level and add a consolidated-not-collapsing or drawdown sanity.

### `arch_tax_efficient` — legs correct, but ETA fills it with distressed neg-EV ADRs
`etr 3–15% + pretax>0 + op_margin>0` is a faithful translation, but the top is STG/VIOT/IH (neg-EV Chinese ADRs, down 55–63%, shrinking). IH passes op_margin>0 with roce −27%; MKTW with roce −76%. **Fix:** add `_roce_now_ok` / not-melting and a not-shrinking guard so "legitimate structure" reads on durable operators, not melting cheapness.

### `arch_kullamagie_breakout` — ranked by cheapness, so top-of-book is flat value not breakouts
Judged on price spirit, the gate (percentile leader + ≥30% prior impulse + tight base + near highs) is a reasonable no-intraday proxy. But because the book sorts by ETA, the top is MXD (mom −0.8%, **24.6% off high** — the far edge of `_kk_near`), Value Convergence (mom 0, roce −1.08, distressed broker), Dhoot (mom +8.5%) — not explosive breakout leaders. **Fix:** add `kullamagie_score` to `ARCH_SORT_OVERRIDES`.

### `arch_wolf_trifecta` — mostly on-thesis; one op-loss name slips the melting floor
Cheap Asian growers with 15–40% revenue growth, operating leverage, positive CFO — good Wolf trifecta shape. **WITHTECH (op −26.2%, ebitda +24.4%)** slips because `_not_melting` is ebitda/roce-based, not op-based, contradicting the "improving margins" spirit the comment claims. **Fix:** add `op_margin > 0` (the sibling `wolf_compounder` already carries it).

### `arch_bab_becoming` — "de-risking toward safe" admits still-unsafe op-loss names
Reasonable de-risking proxies, but WITHTECH (op −26%) and Kaizen (op −5%, roe −1.8%) fire on a single margin-inflection tick while still deeply unprofitable; several toppers also carry −25% to −46% 12m momentum. `_roce_now_ok` floor is lenient. **Fix:** add an op_margin floor so "becoming boring-safe" excludes −26%-margin businesses.

### `arch_sustainable_scaler` — the self-funding OR-leg lets negative-FCF names in
Mostly real small-cap compounders (Medialink, Daejung, Kokusai, IDIS). But `_self_funding = fcf_per_share_yoy>0 | fcf_margin>0.03 | roic≥0.10` — the first leg passes names with *negative* FCF off a low base: Chen Hsong (fcf_yield −16%), Amuse (fcf −7%, op −1.8%). **Fix:** require `fcf_margin>0` or `roic≥0.10` as the real self-funding evidence; drop the per-share-YoY-only path.

### `arch_capital_light_pivot` — sound; two capital-intensive miners sit oddly
Reasonable capital-light compounders (Harmony, Climb, Pegasystems, Optex) — the asset-grows-slower-than-revenue leg is the right signal. SSR Mining and Hallador (coal) are capital-*intensive* by nature; they pass the asset/revenue ratio in an up year but read oddly in a "capital-light" list. Minor; no fix required beyond awareness.

### `arch_geographic_global` — sound; one levered anomaly leaks
Real global operators (AvePoint, USANA, Criteo, Pegasystems, Climb). AMTD Idea (op −336%, net-cash −5.5 = heavily levered, sector-NaN) leaks via `is_operating`. Otherwise faithful.

### `arch_balance_sheet_return` — thesis-valid but top overlaps the cash-return family
Top-10 is deep-net-cash / neg-EV names (Dongwoo, Brook Crompton, Medialink, Michang) — legitimately the "cash-rich runoff" leg, but nearly identical to `capital_returner` / `net_cash_returner` top-of-book. The distinctive *uncovered-payer* (paying dividends they don't earn) cases are buried. Consider surfacing the `_uncovered` leg separately.

### `arch_cundill_deep_value` — faithful six-point checklist; two soft edges
Cheap (P/B<1, low P/E), near-lows, dividend-paying, mostly profitable global value — good Cundill shape. Central China New Life carries a **35.5% "dividend yield"** (stale-price / return-of-capital artifact) and op −2.8% (passes criterion-4 via roce>0). **Fix:** sanity-cap `dividend_yield` (a 35% print is not income) and firm up criterion-4 to real operating profit.

### `arch_oneil_canslim` — price spirit OK; ETA drags in value, two names lack momentum
Names are near 52w highs with positive prior_run (legit N + L). But ETA ranking favours cheap near-high value (Thai/Korean P/E-5 names, Dundee holdco) over true growth leaders, and Foxconn Tech / AvePoint have *negative* 12m momentum (qualify on 6m percentile only) — thin for O'Neil leadership. **Fix:** rank by `oneil_score`.

### `arch_wolf_value_catalyst` — sound fortress-BS grower, but no actual "catalyst"
Cash-rich (net-cash 75–194%), growing, cheap microcaps — good shape, `_not_melting` holding. But the "value **+ catalyst**" thesis has no catalyst leg (it's cheap+cash+growth); and it overlaps the cash-return family heavily. Minor.

### `arch_wolf_emerging` — definition sound, coverage near-zero
Only **2 firers = 1 company** (Trulieve, double-counted TCNNF/TRLV). The HASH-lesson positive-CFO + clean-SBC gate is a faithful translation, but the cannabis/hemp keyword universe is tiny here. **Fix:** dedupe cross-listings; accept that this is a structurally thin archetype (or widen the emerging-sector keyword set if more coverage is wanted).

### `arch_diversified_segments` — structural tag faithful; no quality overlay
Correctly computes 4+ segments / HHI≤0.40. As a *neutral structural* tag it's fine, but ETA-ranked top surfaces distressed/levered names (TUSK op −40%, AMTD & Arena levered, Cemtrex −98%). If ever used as a buy list, add a light quality/leverage overlay; as a descriptor, sound.

---

## SOUND

- **`arch_capital_returner`** — textbook FCF-covered high-shareholder-yield value (5–10% yields, low P/E, operating). Thesis embodied.
- **`arch_net_cash_returner`** — deep-net-cash (72%+ of mcap) active returners. On-thesis. (Heavy overlap with the other two cash-return archetypes — a portfolio-level redundancy, not a defect.)
- **`arch_strong_coverage`** — net-cash / trivially-serviceable-debt operators, EBITDA-positive. On-thesis (ranked by the net-cash leg more than the interest-coverage leg, but genuinely low burden).
- **`arch_concentrated_segments`** — a NEGATIVE flag by design; correctly surfaces concentrated, often-risky names (TTEC, STG). Inverted judgement: they *should* look risky, and they do.
- **`arch_weinstein_stage2`** — near-52w-high uptrends with positive momentum (Daishin at the high +53% mom is textbook). Good price-action spirit; fundamentals correctly irrelevant.
- **`arch_lynch_pegy`** — classic GARP: low P/E (5–10) + growth + dividend yield. Financials correctly allowed (P/E valid for banks).
- **`arch_lynch_evgy`** — cheap EV/EBITDA-relative-to-growth; the `is_operating` fix holds (no insurer leakage), EBITDA-positive enforced. Marginal op-loss but EBITDA-positive names (China ITS) acceptable for an EV/EBITDA screen.
- **`arch_biotech_deep_value`** — now genuinely clinical developers trading near/below net cash (KROS, Galapagos, Zealand, SCYNEXIS, 4D Molecular) — the `_is_clinical_biotech` gate + 0.5–3.0 net-cash band is working well. Minor: Galapagos dual-listed (0JXZ.IL/GLPGF, and GLPGF mislabelled "Lakefront Biotherapeutics") — a dedupe/label cleanup, not a thesis defect.
