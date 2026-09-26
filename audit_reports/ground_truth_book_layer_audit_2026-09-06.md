# Ground-Truth & Book-Layer Audit — 2026-09-06 (audit #5)

Method: independent live refetch from Yahoo (no cache) for a stratified sample of
book-top names, compared cell-by-cell against master and rendered sheets; plus a
selection/dedup/formatting inspection of the rendered top-N book.
Harness after this audit: **41 checks, 0 FAIL, 0 WARN** (1 check added, 1 refined).

## Finding 1 (P0): stale 52w display — fresh flags beside a wrong percentage
Live refetch caught UTZ trading AT its 52-week high (−0.4%) while the books showed
−48%; EOLS at high shown −27%; JET2.L −3.8% shown −26%. Root cause: quote-time
`pct_off_52w_high` freezes while the Lynch drive owns the Yahoo budget, but the
Lynch tape itself is refetched per name (age 1 day) — the derived at-high FLAGS were
fresh while the displayed % was weeks stale, so a row could read "at 52w high ✓,
−48% off high".
**Fix:** final gate in enrich now overrides `pct_off_52w_high` with the live Lynch
`pct_52w_high − 1` wherever the tape is live (26,907 rows refreshed); tags gates use
the same coalesce; new methodology check asserts flags and percentage can never
disagree again. Post-fix values match live Yahoo to the third decimal.
Residual: the quote-time `price` column itself still lags (median ~5%, worst +84%)
until the price-refresh enrichers resume after the Lynch drive completes.

## Finding 2 (P1): preferred shares polluting ranked equity sheets
COF-PI ranked #2 and JXN-PA #11 in the US top-30 — preferred series scored as if
common equity (their "asymmetry" is a rate artifact; a preferred cannot 10x). The
master holds 449 preferred lines + 77 warrants/units/rights; name-dedup cannot
collapse them into the common (depositary-tail names). **Fix:** `dedupe_display`
now drops non-common security lines (symbol pattern + name pattern) from every
display book; master keeps the rows. US top-30 verified clean.

## Finding 3 (P1): audit's own pence-mint check over-flagged
Repeated "pence-minted .L mcap" nulls kept resurrecting because the check (and my
repairs) assumed every .L row with mcap==price×shares is pence-minted. False:
internationals quote .L lines in EUR/USD/GBP where that identity is CORRECT
(Compass, IHG, Glanbia, Bank of Ireland all verified against real-world caps).
Only mcap/revenue absurdity separates them: true mints run 170–340× revenue
(Celtic prefs at £21B, Investec at £644B), legitimate holdouts ≤21×.
**Fix:** check + enrich final gate now require mcap/revenue > 100× (or no revenue
at pence-scale price); the three true mints are nulled durably at the last writer
before the master lands. Several earlier blanket nulls of correct values are
restored by the next enrich from source.

## Finding 4 (P2): non-breaking spaces in 102 company names
Cosmetic in cells, and a latent dedup-key hazard. Scrubbed at the enrich gate.

## Verified clean
- Sheet ordering matches the claimed rank key (monotonic ETA descending, spot-checked).
- No duplicate businesses within any sampled sheet post-dedup.
- FX conversions, composite bounds, Lynch file schema: all green.
- Cross-book value consistency for sampled symbols.

## Not completed
An independent adversarial code review of all 10 book builders was launched but
died on a session rate limit; the empirical checks above cover the highest-risk
surfaces (selection, dedup, 52w display), but a full code-path review of the
builder variants (--otc-mode/--high-filter flags, cover-sheet legends) remains
open for a future pass.
