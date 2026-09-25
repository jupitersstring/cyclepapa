# Risk-reward (cross) book — hand review (2026-09-24)

This book is built by the engine on branch `claude/risk-reward-crossfeed`. It
is refreshed here by `refresh_risk_reward.sh`, which runs on a temporary copy
of that branch; the branch itself is never modified. I read every tab against
FMP prices and financials. ✔ = fixed in this pass, in the overlay, the patch
or the post-process on this branch.

## Errors found and fixed

| Area | What was wrong | Fix |
|---|---|---|
| Cover | "Risk-budgeted invested weight: **6002% of NAV** (−5902% cash)". Weights are stored in percent and multiplied by 100 again. "697 named candidates" was hard-coded (the book ranks 1,419) | ✔ `rr_engine_patch.py` |
| Ticker mapping | ~40 bare ASX tickers matched US companies with the same letters: ACF Acrow → AmeriCredit, AON Apollo Minerals → Aon, CMG Critical Minerals → Chipotle, JLL Jindalee → Jones Lang LaSalle, HAS Hastings → Hasbro, ARI Arika → Apollo REIT. Those rows showed another company's balance sheet | ✔ name-verified mapping; ASX / LSE / TSX suffixes tried; bare numeric JP / HK / KR codes mapped. Mapped rows 921 → 1,162 |
| Non-companies | 40 rows were not investable companies: OFAC / Treasury notice titles ("Russia-related Designations", "Counter Narcotics…"), press-release headlines ("Inventiva Announces…"), PIMCO / Venture Lending funds, warrants (VAL-WT). 13 of them sat in the Executive Summary top 100 | ✔ dropped (logged) |
| Bankrupt equity | GOCOQ, NOTVQ (Ch.11 "Q" tickers) ranked #2 and #5 with a ~36% bear case: the formula doesn't know the shares are likely cancelled | ✔ 95% bear case for Q tickers |
| Untradeable | TruBridge, LivePerson, First Foundation, Aenza and others ranked #2–#3 but FMP shows them not trading (take-privates / delistings). Brazilian rows with no ticker (Minerva, Irani, Bradesco Leasing: debenture issuers) ranked #10–#14 | ✔ flagged and demoted ×0.5 |
| Floors | The book-value floor was treated as hard: 0.35 × book at 0.2× P/B gave a floor above the share price, so Lotte, Nissan, VW pref, SBB and Aroundtown showed a 10% bear case | ✔ book floor capped at 60% of market cap; only cash or working capital can take the bear case below 40% |
| Equity stubs | Kaisa (net debt 270× market cap), Sunac, Vanke, Americanas, SBB kept a book floor although debt swamps the equity and interest isn't covered | ✔ no book floor when net debt > 2× market cap and interest cover < 1 (bear 90%) |
| Property NCAV | Developers' current assets are land bank / inventory, so their "NCAV" floor was meaningless | ✔ NCAV leg off for Real Estate |
| FMP data | ×1000 filings (INR cash $160bn), stale share counts (Horizon Quantum, Solocal), pence-quoted London lines, cross-currency P/B from the unreliable ratio feed | ✔ statement consistency checks, FX conversion, market-cap vs price × shares check, minor-unit normalisation (`fmp_book.py`) |
| Regions | Keros "MEA / Frontier", Canopy Growth "MEA / Frontier", 243 "Unspecified" | ✔ region from FMP country where mapped |

## Hand-built waterfalls (the 21 REAL names): stale

The YAMLs were all written in June 2026. They store return **multiples** with
no reference price or date, so every price move since then silently changes
what the multiples mean. The new **Review & data quality** sheet shows the
move since each YAML and the EV re-based to today's price.

| Name | Since YAML | Status |
|---|---|---|
| Sabadell (SAB) | +19% | **Catalyst already resolved:** BBVA's bid lapsed in Oct-2025 (~25% acceptance). The book still carries "BBVA bid resolution, p = 0.6, Jun–Dec 2026". Needs a rebuild |
| Doosan Bobcat (241560) | −12% | **Catalyst no longer exists:** the Bobcat / Robotics share swap was cancelled Dec-2024; "revised swap terms" is not a live event |
| USA Rare Earth ("UREE") | n/a | **Wrong ticker:** trades as USAR, so the waterfall has no price anchor |
| Eutelsat (ETL) | −42% | Multiples stale; re-base or rebuild |
| Lithium Americas (LAC) | −36% | Diluting 11%/yr, pre-revenue; check the DOE-stake economics are in the base case |
| Hawaiian Electric (HE) | −32% | New 12-month low (Sep-2026) |
| OHLA | −23% | Apollo take-out (p = 0.35) needs a status check |
| Sunac | −22% | Also flagged by the overlay as an equity stub (net debt ≈ 18× market cap) |
| thyssenkrupp (TKA) | +39% | Much of the base case may be realised; reward/risk from today is lower than shown |
| Solocal (LOCAL, #1 overall) | +1% | FMP share data inconsistent after the 2024 restructuring. The #1 rank (bear −15%, EV 4.0×) rests entirely on the YAML: verify price and share count by hand |
| Salzgitter (SZG) | −10% | FMP: operating margin −1%, FCF yield −20%, interest cover −0.5×. The 45% bear case looks light |
| Electrolux (ELUX-B) | −13% | FMP: net debt 329% of market cap, interest cover −0.5×. The 45% bear case looks light |

## What a reader still can't answer from the book

1. **Is the ranking right across sources?** The composite normalises
   reward/risk *within* each source (REAL / FMP / PROXY), so a 2.6× from the
   PROXY formula and a 2.6× from an FMP balance sheet don't mean the same thing.
2. **What does "Kelly" add?** Every name hits the 10% raw-Kelly cap and the 3%
   cluster cap, so sizing is equal-weight in practice.
3. **When?** Catalyst windows are mostly multi-year and sourced to "industry" or
   "company guidance"; few hard dates.
4. **What is management doing?** Now partly answered: the new **Call intent**
   sheet covers every name with transcripts (2,381 companies in the store).
5. **Are the micro-cap cash boxes investable?** Many top FMP rows (XNDU, OKUR,
   SEER, KROS) have net cash > market cap but burn 20–45% of market cap a year.
   Whether the cash reaches shareholders depends on control and dilution, which
   the book doesn't show.
6. **Auto makers and banks:** Nissan's and VW's net debt includes their captive
   finance arms, so the leverage view overstates risk for them. Banks are
   treated on book value only.

## Recommended upstream changes (engine branch: needs your go-ahead)

- Store absolute bear / base / bull **values per share plus an as-of price and
  date** in each YAML, and derive multiples from today's price.
- Add a resolved / broken status to catalysts (SAB, Doosan) and a staleness
  alarm when the price moves more than 20% since the YAML.
- Fix the ticker in UREE.yaml (→ USAR).
- Apply this overlay upstream so the engine carries FMP rows natively.
