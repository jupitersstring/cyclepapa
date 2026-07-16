# Kate Silas — public-record dossier & single-equity nuances

Compiled 2026-07-03 from publicly accessible sources (her website, book
listings, podcast pages, LinkedIn/X references, third-party mentions).
Everything below is tagged **[V]** verified from a public page, **[P]**
paraphrased from marketing/book descriptions, or **[I]** inference.

## Who she is
- Melbourne-based financial astrologer and trader; "15+ yrs financial
  astrology & trading experience, Wall Street trained." [V — profitwiththeplanets.com/financial-astrology]
- Ex-Wall Street; survived the 2008 crisis; integrated astrology into her
  trading after the 2011 Japanese tsunami market disruption. [V — Jessica
  Adams "The Astrology Show" Apr 2020 page]
- Claims a Diploma of Share Trading (2010) and Global Macro Financial
  Studies certification (2017, "London School of Economics and Finance").
  [P — site bio; institution name as claimed, not independently verified]

## Core method (as publicly stated)
1. **Chart basis: IPO / first-trade chart.** Vol 1 explicitly teaches
   "distinguishing IPO charts from incorporation charts"; her books also
   cover "non-IPO companies" (incorporation fallback), currencies and
   crypto. [V — self-study-books page]
2. **Chart-provenance awareness.** She "has a database of New York Stock
   Exchange 'birth' dates favoured by astrologers from Bill Meridian, to
   Sepharial, to Henry Weingarten" — i.e. she treats the choice of
   first-trade chart as a live methodological problem, not a given.
   [V — Jessica Adams, "Wall St Astrology," Oct 2022]
3. **Slow movers + eclipses only for markets.** "Slow outer moving planets
   and eclipses" are her market drivers; fast planets are de-emphasised.
   [V — financial-astrology page]
4. **Eclipse doctrine (her signature edge).** Vol 2 Part 2 (78pp) is
   billed as "the only detailed written book available about how to use
   eclipses in the markets to individual assets — how to use them using
   time, how to enter AND exit trades, and how to be prepared knowing when
   astrology transits come," from "10+ years of studying, charting and
   watching eclipses." Headline claim: "WHEN YOU SEE THE BIG MOVES OF
   ASSETS IN THE MARKETS — THAT IS OFTEN DUE TO AN ECLIPSE TO THE IPO
   CHART," citing moves of 300–500%. [V — self-study-books page + search
   snippets]
   - Nuance A: eclipses time **exits as well as entries**.
   - Nuance B: "be prepared knowing when astrology transits come" = the
     classical **eclipse-degree reactivation** doctrine — the eclipse
     degree stays sensitive and fires when a later transit crosses it.
   - Nuance C: exact orb NOT published. Community range for
     eclipse-to-natal is 1–5°; our engine's ≤3° sits inside it.
5. **Outer planets (Vol 2 Part 1, 90pp).** Slow movers identify "large
   price events"; explicitly teaches **trading direct AND retrograde
   planets** and **"transit importance weighting"** — a hierarchy of
   transits, not flat scoring. [V — self-study-books page]
6. **Degrees, not vibes.** "Planetary movements at specific degrees rather
   than intuition"; a "time and price" framing. [V — financial-astrology page]
7. **Vol 1 single-equity toolkit:** "best and worst trading aspects…with
   equities"; "short-term and long-term triggers that move equities";
   assessing **growth-stock potential from the IPO chart setup itself**
   ("The Magic Formula in stock market IPO charts"); eclipse impact on
   price; **personal-chart-to-company synastry** (the trader's own natal
   chart against the stock's chart); and **predicting mergers &
   acquisitions "with specific astrology."** [V — self-study-books page]
8. **Stated preference:** "I like it best for individual company shares so
   I can sit back and let the planets do their work." [V — Jessica Adams
   Apr 2020]
9. **Astrology + technical analysis together** — astrology supplies timing
   ("proprietary indicator"); TA confirms. [V — Apr 2020 podcast page]

## Worked examples (publicly referenced)
- **Tesla** — dedicated "Tesla Financial Astrology for Students Case Study
  Manual" (2020): "IPO setup, transits, degrees, and eclipses" applied to
  TSLA. [V — search snippets of site copy]. A ~2022 LinkedIn post claims
  her May forecast flagged "something major to do with competitors…against
  Tesla," retro-fitted to Bill Gates news [V — LinkedIn; vague, no degrees].
- **Eclipse case set in Vol 2:** GameStop, AMC, NIO, Blackberry, Zoom,
  Bitcoin, US Dollar — assets whose "big moves" she attributes to eclipses
  hitting their IPO/natal charts. [V — self-study-books page]
- **Crypto:** a "Beginners Crypto IPO Astrology Class" covers Bitcoin,
  Ethereum, Binance, Solana — including "best crypto trading planets by
  aspect" and "how to backtest a chart." [V — zoom-mini-classes page]
  **This corrects the compendium's claim that she does not teach crypto.**
  (No evidence she covers commodities — that part stands.)

## What is NOT public
- Exact orbs, houses, or aspect set; the "Magic Formula" contents; the
  transit-importance hierarchy; documented, dated, out-of-sample track
  record (testimonials are anecdotal). Treat all as practitioner-grade,
  self-attested. [I]

## Reconciliation with our engine
| Silas nuance | Our status |
|---|---|
| IPO first-trade chart | ✓ implemented (Ritter dates) — but her NYSE-date-database point warns our known misdated charts matter more than we treated them |
| Eclipse-to-natal drives big moves | ✓ v16/eclipse layer (≤3°, 18mo back/3mo fwd); our 152-corpus found ~100% eclipse pre-seeding at bottoms |
| Eclipse times EXITS too | ✗ we only used eclipses as entry/bottom evidence — add exit flag |
| Eclipse-degree reactivation by later transit | ✗ NOT implemented — now in silas_rules.py |
| Transit importance weighting | ✓ analogous (v19 empirical orb-bucket weights) |
| Direct vs retrograde trading | ✓ partial — our mid-rally retrograde findings (Nep-Rx 54% at mid) empirically support her distinction |
| Growth-stock DNA in the IPO chart | ✓ analogous (natal signatures: UraPlu septile/sextile, AVIS-DNA, GC) |
| Trader-chart synastry | ✗ out of scope (needs user's natal data) |
| M&A signature | ✗ not implemented (compendium: Pluto + 8th house) |

Sources: profitwiththeplanets.com (financial-astrology, self-study-books,
testimonials, zoom-mini-classes pages), jessicaadams.com (Apr 2020 The
Astrology Show; Oct 2022 Wall St Astrology), LinkedIn posts (kate-silas-a13022a),
X @kates_9999 (referenced, not fetchable).
