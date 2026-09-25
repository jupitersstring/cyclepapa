# Second read of all three books: questions, limitations, design (2026-09-24)

I read the rebuilt outputs a second time, this time as a user rather than as a
data checker: what is unclear, inconsistent, missing or badly laid out? I also
audited every ticker tab for empty columns, tied scores, duplicate companies
and sort order. ✔ = fixed in this pass.

## 1. The biggest design problems (all books)

1. **There is no "one name, one page".** A company's story is scattered across
   up to seven tabs with nothing linking them. Comtech (CMTL), for example, sits
   on MD&A Intent, Mechanism Gates, Governance Discount, Re-Rate Catalysts,
   Distressed Stub, Recent 30d and Turnaround.
   ✔ Name Financials now lists each name once, most-cited first, with an
   "Appears on" column. The next step is a per-name tear sheet: thesis, floor /
   upside, financials, catalysts with dates, management intent, insider and
   governance signals, and flags.

2. **The shortlist disagrees with the book's own emphasis.** The names cited on
   the most tabs are not on "Most Asymmetric":
   - Comtech (CMTL): 7 tabs, 0.16× book, net debt 515% of market cap;
   - Lamb Weston (LW): 6 tabs;
   - LAB: 6 tabs, net cash 157% of market cap.

   The shortlist is driven by PSU / governance layer counts, while the thesis
   tabs point elsewhere. A reader can't tell which view to act on.

3. **Every tab has its own "Score", on its own undeclared scale.** There's no
   legend: Governance 34, Mechanism 64, Assembly 62, Timing 15, Tail p 30,
   Act prob 0.6, Edge est. −1.9. Scores can't be compared across tabs and
   aren't calibrated to anything a reader cares about (expected return, hit
   rate). Recommendation: express every tab's ranking as a percentile, plus
   (where validated) a hit rate / expected-return column with its source.

4. **The same word means different things.**

   | Word | Meaning in one place | Meaning elsewhere |
   |---|---|---|
   | "Tier" | Liquidity band (A/B/C) in the OTC book | Signal strength (ACTION LIKELY / BUILDING / ACT SIGNALLED) in the main book |
   | "Tier" / "Bucket" | Build depth in the cross book | Screener bucket in the cross book |
   | "Ratio" | Upside ÷ downside in Payoff Geometry | Something different in Re-Rate Catalysts |
   | "Read" | FOLLOW / FADE in Insider Filing-Time | The financial one-liner in "FMP financial read" |

5. **Abbreviations without a legend.** PSU core, Gov, Fam., Mech, Orph, Insdr,
   Catl, Inflx, Cap, Inner, DD%, N/8, cond_cat. Every tab needs a one-line key
   under its header.

6. **Tabs are ordered by build order, not by how a reader works.** The main
   book's 33 tabs mix actionable lists, thesis screens, evidence and plumbing.
   Suggested grouping:
   1. **Decide:** Cover, Shortlist, Name Financials / tear sheets.
   2. **Theses:** Governance Discount, Mechanism Gates, Payoff Geometry,
      Re-Rate Catalysts, Distressed, Hidden Asset, Structured Distressed,
      Turnaround, Call Intent.
   3. **Signals:** Insiders, Filing-Time, MD&A, Incentive Improvers, Recent 30d,
      Political.
   4. **Evidence:** Re-Rate Backtest, Tail Odds, Winners Study, the
      out-of-sample test.
   5. **Plumbing:** Layer Correlation, Coverage, Methodology.

   Contents should say which group each tab is in. ✔ Name Financials added to
   Contents.

7. **The financial read sits in the far-right column.** On wide tabs it's
   off-screen. Better: 3–4 key numbers (P/B, EV/EBITDA, net debt / mcap,
   52-week position) next to the name, with the full line at the right.

## 2. Low-resolution and dead columns (from the audit)

| Tab | Finding | Meaning |
|---|---|---|
| Payoff Geometry | Down% is 0 in 47 of the top 50; 9-way score tie | The tab shows only the saturated tail (net-cash micro-caps); ranking inside it is arbitrary. Show floor types separately and add liquidity |
| Insider Filing-Time | 35 of 50 rows tied at 15 | No size weighting: a $10k buy equals a $13.5M buy |
| Distressed Stub Progress | 33 of 45 tied at 4; Counter-signals empty 44/45 | Too coarse to rank |
| Asymmetry Assembly | "Cap" empty 28/28; "Catl" 25/28; "Inflx" 24/28 | Dead or near-dead components |
| Turnaround Signal | Grant / Talent / Role empty in 39–40 of 40 | The talent-matching half of the signal isn't firing |
| Hidden Asset Realisation | Thesis empty 39/40; 14-way tie | No thesis text, low resolution |
| Foreign Markets | 18 rows tied at 8 | Low resolution |
| Most Asymmetric | Catalyst empty 18/20 | The shortlist has no catalysts |
| NOL Shells (OTC) | "Now OTC" empty 57/60 | Column adds nothing |

## 3. Sorting and duplicates

- **Not sorted by their visible score:** MD&A Intent (by family count),
  Governance Discount (by tier, then score), Political Trades (by buyer count),
  Single-Measure Best, OTC Intent (by tier / cheapness). Legitimate, but the
  sort key isn't stated. ✔ The cross book's Executive Summary now shows its
  sort key (the composite) and the review flag. Before, a 2.9× row ranking above
  15× rows looked arbitrary.
- **Duplicate share classes:** AGNC (+ preferred lines L/M/N) on Incentive
  Improvers; Old National (common + preferred) on Call Intent; Liberty Global
  classes; Bank of Utica (BKUT / BKUTK) on OTC Deep Value; TEPCO / Grupo de
  Inversiones / LEG Immobilien twice on Foreign OTC. Needs one issuer-level
  dedupe helper applied to every tab.
- **Tail Odds** repeats names across its "confirmed" and "monster" sections by
  design, but doesn't say so.

## 4. Cross book specifics

- ✔ The micro-cap liquidity penalty compared HKD market caps with a USD
  threshold, so Hong Kong micro-caps (RSUN, CNT) took #3–#4. Now converted to
  USD.
- Every FMP row shows "Score / Bucket / Archetype" as 0.52 · A · F: placeholders
  from the screener. These should be blank or relabelled for FMP rows.
- The "Signal conviction" lens still lists bankrupt or untradeable names
  (GoHealth, Inotiv, TruBridge, LivePerson). The lenses don't apply the review
  flags.
- Six sheets have no subtitle (All names, Universe, Waterfall matrix, Catalyst
  timeline, Portfolio sizing, Methodology). The "PSU x-feed" note says
  "31 layers" (there are 45).
- Only 10 of the 21 hand-built names have a detail sheet.
- The REAL premium (+0.12 composite) puts every hand-built name near the top
  regardless of its numbers (Solocal #1 with score 0.00, bucket C, archetype
  Unknown).

## 5. Questions the books still can't answer

1. **Does the main ranking make money?** Not so far: see MAIN_BOOK_REVIEW.md,
   finding 1. Keep the monthly out-of-sample check running.
2. **What should I own, and how much?** The main book's sizing labels are
   descriptive, and its "portfolio math" is hand-typed. The cross book sizes
   everyone at the same capped weight. Neither book produces a portfolio with
   position sizes tied to payoff, liquidity and correlation.
3. **When is each thesis wrong?** No exit or review triggers, and few dated
   catalysts.
4. **How much is priced in?** No momentum / trend, short interest, borrow cost
   or crowding. Many shortlist names sit at 52-week lows.
5. **How do the two books relate?** Different universes (US governance/PSU vs
   global recapitalisations), different score scales and almost no overlap, and
   nothing reconciles them.
6. **Is the data fresh?** Most thesis tabs don't show a signal date or an
   as-of date.
