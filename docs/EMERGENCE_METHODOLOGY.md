# Emergence coverage methodology

How the framework catches Chapter 11 **emergences** (the payoff end of the
distressed funnel) with full coverage and a measurable gap. This replaced a
single-source, three-phrase approach that was catching roughly a quarter of
what is filable.

## The problem it solves

An emergence is not one signal — it is an **event that throws off several
independent SEC filings at once**. Keying the whole funnel off three
full-text phrases in two form types (the old `postreorg_poll`) meant we
silently missed:

- every emergence phrased differently ("consummation of the Plan",
  "emergence from bankruptcy", "Plan Effective Date", …);
- every **foreign private issuer** (Seadrill, Valaris, Noble, Azul, GOL),
  which announces on **6-K / 20-F**, not 8-K / 10-K;
- everything past the **first 10 hits** per query (EDGAR full-text search
  paginates 10 at a time; the fetch read only page one).

## The three layers

### 1. High-recall, evidence-graded catch (`postreorg_poll.py`)

- **Two tiers** of phrases, graded by a live EDGAR precision/recall audit
  (`emergence-catch-audit` workflow): a **STRONG** tier (event-marking,
  trustworthy) and a **RECALL** tier (wide net; precision handled
  downstream). Audited-noise phrases (e.g. "the Plan became effective" =
  annual incentive plans) are excluded.
- **Broadened forms**: `8-K,10-K,10-Q,6-K,20-F,S-1,424B3,8-A12B,8-A12G` —
  6-K/20-F close the foreign-issuer blind spot; S-1/424B3 catch resale
  registration; 8-A12B the relisting of new common.
- **Full pagination** (`edgar_util.fts_search_all`) — all hits, not page one.
- Each record carries `emergence_tier`, `matched_phrase`, structured
  **`item_1_03`** (8-K Item 1.03 = the precision confirmer) and a
  **`pre_emergence`** flag (a Q-suffix ticker = still *in* Chapter 11).

Result: ~37 → **448** records per run.

### 2. Multi-source triangulation (`emergence_master.py`)

An emergence throws off up to five independent signals; catching **any**
catches the event, and how **many** corroborate sets confidence:

| # | Signal | Channel |
|---|--------|---------|
| 1 | Emergence 8-K / prose | `postreorg` emerged / plan-effective |
| 2 | Fresh-start accounting (ASC 852) in the next 10-K/Q | `postreorg` freshstart |
| 3 | Old shares delisted (Form 25-NSE / 15) | `edgar_forms` / `form15` |
| 4 | New shares registered / relisted (Form 8-A12B) | EDGAR |
| 5 | Court plan-confirmation docket | PACER |

Records are fused by entity (CIK, else a robust normalized name that folds
`S.A.`↔`SA`, strips parentheticals, and matches on Q-stripped ticker stems).
`item_1_03` counts as an independent corroboration. Q-suffix entities are
surfaced as **pending** (still in Chapter 11), not emerged.

### 3. Completeness tripwire (`emergence_master.py`, coverage gap)

A ground-truth list of known emergences (`data/emergence_ground_truth.json`,
seeded by the audit's research agents) is checked against the fused corpus.
Any known **listed-common** emergence not caught is reported as a coverage
gap — turning "we're missing so much" into a specific, diagnosable number.
Not-yet-effective entries (in-process / targeted) are skipped.

## Running it

```
make postreorg-poll        # high-recall catch → data/inbox/
make emergence-master      # fuse + run the coverage tripwire
make listed-equity-screen  # the tradable slice (verified, six-question)
```

## Known residual gaps (long tail)

The tripwire's remaining misses are genuine edge cases, not silent losses:

- **OTC post-reorgs that stop repeating emergence language** in recent
  filings (e.g. Audacy) — only the original emergence 8-K, now outside the
  poll window, carried it.
- **Foreign issuers with translated / non-standard phrasing** in 6-K
  exhibits (e.g. GOL) — 6-K/20-F are now searched, but the phrase set is
  English-idiom.
- **Emergers since acquired/merged** (e.g. Endo → Mallinckrodt) — no longer
  standalone listed common; a stale ground-truth entry, not a real miss.

Widening the poll window catches (1); the others are inherent to full-text
search over heterogeneous filers and are left visible in the tripwire rather
than hidden.
