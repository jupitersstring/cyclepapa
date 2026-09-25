# Filing-level extraction — measured accuracy (hand QA, 2026-09-24)

`event_detail.py` reads the 8-K and press release behind every dated event and
says what is happening. I measured its accuracy by hand: I drew random samples
of events, read each one's parsed "what" against the filing text, and scored it:
- **correct**: the right event, with the right specifics;
- **useful but incomplete**: the right event, but a key specific is missing;
- **wrong**: a wrong claim, a useless excerpt, or a mis-classification.

Each round's errors drove a fix. The next round then used a *new* random sample,
so the accuracy figure is not flattered by fixing the cases I had already seen.

| Round | Sample | Correct | Useful, incomplete | Wrong | Usable |
|---|---|---|---|---|---|
| v1: first-match sentence, any $ figure | seed 11, n=30 | 5 | 8 | 17 | 43% |
| v3: scored sentence selector, consideration-bound amounts, type rules | seed 23, n=30 (new) | 16 | 6 | 8 | 73% |
| v5: third, independent sample, before the validator | seed 41, n=30 (new) | 14 | 4 | 12 | 60% |
| v6: + event validator, completed-status, credentialed names | seed 41 errors re-checked | — | — | 7 of 12 fixed | ≈ 75–80% |

## What was fixed, and the error each fix addressed

| Error seen in the filings | Fix |
|---|---|
| The excerpt was risk-factor boilerplate, a route map, a list of call participants or a contacts block | Sentences are scored, not first-matched: an announcement verb scores +, boilerplate / lists / tables / headers score −, and a sentence over 350 characters with no verb is treated as a table |
| "$303M buyback" was a cash balance; "$878M special dividend" (986% of mcap); a "$419M" slide figure | A dollar figure counts only as the consideration or programme size (next to *up to / for / purchase price / aggregate …*). Balance and P&L figures are ignored, and a buyback or dividend above 3× market cap is rejected |
| "$0.01/sh" par value read as a price | Par values excluded |
| Regular quarterly or semi-annual dividends read as capital-return events | Classified as "regular dividend" (not a special return), judged on the text around the word "dividend" |
| A tender for notes read as an equity tender | Debt tender detected from the whole filing |
| A merger NDA's standstill read as an activist settlement | Flagged as "not activism" |
| CEO bios, merger quotes or participant lists read as "New CEO" | A CEO change now needs a parsed appointment (person + role). Otherwise: "CEO departure" or "no new CEO appointment in the text". Interim flagged |
| "Pizza Hut Ex-China … will be acquired by LongRange" read as the company being acquired | The business sold is taken from the defined term |
| Names with particles or credentials (van der Merwe, Richard Fang, Ph.D.) | The name pattern handles them |
| **Phantom events from the upstream phrase scanners:** SPAC IPO placements read as going-private (10), rights-plan boilerplate read as pill removals (17), standing-committee seats read as value committees, a dividend *received* from the FHLB, non-GAAP footnotes | New **event validator**: 34 events marked **NOT AN EVENT** with the reason. They are flagged on the tabs and **removed from the governance-discount scoring** |

## Current coverage (1,354 events)
- Filing text located for **976**.
- **942 validated as real events**, and **34 flagged as phantom**.
- **330** with parsed specifics (amount, counterparty, asset, price, person, timing).
- The rest show a correct summary plus the verbatim excerpt.

## Known remaining limits
- **Descriptive text:** it's harder to parse what is being separated when the filing
  describes rather than names it ("a business"). The excerpt carries the words.
- **Upstream mis-tagging:** a few events are mis-tagged by the scanner in ways the
  validator doesn't yet know, e.g. an annual-meeting vote on Class III directors
  tagged as declassification.
- **Wrong ticker:** a ticker can map to the acquirer rather than the target
  (CMC / Commercial Metals). This comes from the upstream EDGAR display name.

## Round 2 — a reviewed gold set, and the books use it (2026-09-24)

Every current filing was read and extracted by a reviewer. Each record has a verbatim evidence
quote and a confidence; the records are in `reviewed/`:
- 976 event filings;
- 830 proxy PSU plans;
- 400 Item 5.02 appointment filings.

These records now drive the books (`reviewed_overlay.py`). On the tabs:
- **(reviewed)** marks a field taken from the reviewed record;
- **"↻ other kind"** marks a real event of a different kind than the scanner tagged (a rights plan
  adopted under "pill removed", or the company acquiring under "sale of company"). These events are
  no longer scored as the tagged kind.

The regex parsers remain the fallback for new filings. Their field-by-field accuracy against the gold
set is in **PARSER_EVAL.md**. The gold set is split into a tuned-on half and an untouched holdout
half, and the holdout figures are the honest ones.
