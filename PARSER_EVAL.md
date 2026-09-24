# Parser scorecard — regex parsers vs reviewed extraction (2026-09-24)

**Gold set.** Every filing behind the books was read and extracted by a reviewer, with a verbatim evidence quote and a confidence for each record (`reviewed/`): 976 event filings (8-K + press release), 830 proxy PSU plans, and 400 Item 5.02 appointment filings.

**How the books use it.** The reviewed record is used whenever one exists (`reviewed_overlay.py`, marked *(reviewed)* on the tabs). The regex parsers are the fallback for filings that arrive after the review. This scorecard measures that fallback.

**Honesty.** The event and PSU gold sets are split in two. *dev* is the half the regexes were tuned on. *holdout* was never looked at while tuning, so the holdout column is the honest accuracy. The event-validity model trains on dev only when it is scored here. The appointment parser was tuned on all 400 filings, so its figures are in-sample. Eight reviewer errors there were adjudicated against the filing text (`reviewed/appointments_adjudicated.json`).

| Parser | Field | Before | Now | n |
|---|---|---|---|---|
| appointments | is a senior hire/promotion (precision) |  | 91% | 89 |
| appointments | is a senior hire/promotion (recall) | 44% | 93% | 87 |
| appointments | person name (on true hires) | 42% | 86% | 87 |
| appointments | role family (on true hires) | 57% | 94% | 87 |
| appointments | base salary exact |  | 94% | 50 |
| events/dev | real-event verdict (precision: flagged REAL that are real) |  | 100% | 368 |
| events/dev | real-event verdict (phantoms caught) | 14% | 99% | 98 |
| events/dev | real-event verdict (real events kept) |  | 94% | 390 |
| events/dev | event family matches |  | 78% | 390 |
| events/dev | amount exact (when the filing states one) | 45% | 73% | 100 |
| events/dev | amount invented where none stated |  | 43 | 390 |
| events/dev | counterparty | 23% | 57% | 159 |
| events/dev | counterparty invented where none stated |  | 12 | 390 |
| events/dev | per-share price | 61% | 91% | 57 |
| events/dev | status (completed vs not) | 82% | 86% | 379 |
| events/holdout | real-event verdict (precision: flagged REAL that are real) |  | 88% | 446 |
| events/holdout | real-event verdict (phantoms caught) | 6% | 27% | 71 |
| events/holdout | real-event verdict (real events kept) | 97% | 94% | 417 |
| events/holdout | event family matches |  | 79% | 417 |
| events/holdout | amount exact (when the filing states one) | 72% | 87% | 89 |
| events/holdout | amount invented where none stated |  | 18 | 417 |
| events/holdout | counterparty | 7% | 52% | 99 |
| events/holdout | counterparty invented where none stated |  | 8 | 417 |
| events/holdout | per-share price | 54% | 92% | 24 |
| events/holdout | status (completed vs not) | 50% | 65% | 400 |
| psu/dev | has a PSU plan (precision) |  | 97% | 307 |
| psu/dev | has a PSU plan (recall) |  | 96% | 312 |
| psu/dev | metric set (>=50% overlap) | 65% | 80% | 272 |
| psu/dev | metric weights exact | 7% | 57% | 212 |
| psu/dev | performance period | 77% | 85% | 258 |
| psu/dev | max payout | 36% | 62% | 158 |
| psu/dev | rTSR target percentile | 27% | 52% | 25 |
| psu/dev | payout history (a cycle matches) | 18% | 43% | 118 |
| psu/holdout | has a PSU plan (precision) |  | 96% | 292 |
| psu/holdout | has a PSU plan (recall) |  | 96% | 293 |
| psu/holdout | metric set (>=50% overlap) | 64% | 80% | 249 |
| psu/holdout | metric weights exact | 11% | 59% | 190 |
| psu/holdout | performance period | 79% | 86% | 243 |
| psu/holdout | max payout | 37% | 65% | 150 |
| psu/holdout | rTSR target percentile | 30% | 50% | 28 |
| psu/holdout | payout history (a cycle matches) | 24% | 52% | 124 |

## What changed

- **Events: phantom detection.** Rules for the phantom classes the review found: financial-statement and non-GAAP footnotes, transaction cost lines, 'About X' boilerplate, executive biographies, capital raises, risk-factor and conditional language, and committee seats. A date check flags recitals of events months before the filing. A learned classifier (`event_classifier.py`: TF-IDF of the excerpt and lede plus the rule signals, logistic regression) handles the long tail; its threshold keeps about 95% of real events.
- **Events: fields.** The consideration, counterparty and per-share price are searched in the excerpt first, then in the 8-K's Item 1.01 / 2.01 paragraph and the press-release lede.
  - **Counterparty:** legal-agreement patterns ('entered into a … Agreement with X, a Delaware corporation'). Deal vehicles (Merger Sub, BidCo) resolve to their parent ('an affiliate of Y'), and the issuer's own name is rejected.
  - **Consideration:** 'purchase price / aggregate / total consideration of' is preferred.
  - **Per-share price:** candidates are scored, and EPS / NAV / closing-price / par-value figures are rejected.
- **Events: types.** A rights plan *adopted* under 'pill removed' is relabelled. When the reviewer finds an event of another kind (the company *acquiring*, a debt tender), it is shown as '↻ other kind' and not scored as the tagged kind.
- **PSU plans:** clause-level weight reading ('X (40%)', 'weighted 40%', 'based 50% on X and 50% on Y', 'equally weighted', 'solely based on X', and table runs read in the direction that sums to 100%).
  - rTSR is treated as a modifier when the proxy says so.
  - Max payout is the most common PSU-context cap, and the rTSR target is the percentile that pays 100%.
  - Payout history pairs a payout phrase ('paid out at 118%', 'vested in 187% of target') with the nearest cycle anchor ('2023–2025', 'FY23-FY25', 'granted in 2023', '2023 PSUs'). Cycles that haven't finished are excluded.
- **Appointments:** the role and person patterns were broadened (titles, nicknames, particles, possessives, 'X's appointment to the role of', 'Incoming CEO X'). Previously reported appointments and quote attributions are rejected.

## Remaining weak spots (the reviewed record covers them for current names)

- **Phantom events on new filings:** about a quarter to a third are caught on the holdout. Recitals and slides take many forms, and the reviewed verdict is what the books use today.
- **Counterparty on new filings:** about half. Many deals name the buyer only through a defined term, or in a later paragraph.
- **PSU weights:** about 60% exact. Weights often sit in graphics or tables that the text rendering scrambles; the reviewed plan is used for all 830 current plans.

