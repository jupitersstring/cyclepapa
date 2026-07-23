# The greatest post-reorg investments — case studies & process lessons

Primary-research study of the canonical post-reorganization / bankruptcy
equity wins (and the failures), plus the practitioner literature documenting
how the best investors actually worked — distilled into process improvements
for cyclepapa. Figures marked ✓ were verified against contemporary sources
this session; the rest are from the standard historical record and books
cited (verify before relying on any single number).

---

## 1. The canon — what actually happened

| Case | Instrument | Entry → outcome | The structural cause |
|---|---|---|---|
| **General Growth Properties** (2009-10) ✓ | OLD common held through Chapter 11 + DIP | Ackman: stock 34¢ → $31; "$60M into $1.6bn" (Bloomberg) | **Solvent but illiquid** — asset value > debt; bankruptcy was a maturity-wall/liquidity event, not insolvency. Ackman supplied the DIP and sat on the board |
| **LyondellBasell** (2009-10) ✓ | Fulcrum senior debt → new equity | Apollo: ~$2bn → ~$12bn (Forbes: "greatest deal in Wall St. history"; Bloomberg: $9.6bn profit) | Bought secured claims ~80¢ into the crisis; shale-gas feedstock advantage transformed normalized earnings post-emergence |
| **Hertz** (2020-21) ✓ | OLD common through a **plan auction** | Old holders got ~$8/share (cash + warrants ~20% of new co) after trading ~$1 | **Competing plan sponsors** (Knighthead/Certares vs Centerbridge/Warburg) bid the estate up; used-car cycle turned mid-case. An **official equity committee** existed |
| **WMIH → Mr. Cooper** (2012-18+) ✓ | Reorganized SHELL with NOLs | WaMu's shell (KKR-backed, ~24% voting) merged with Nationstar in a $3.8bn deal → COOP compounder | **NOL-shell playbook**: billions of tax attributes on a tiny shell, § 382-preserved, waiting for an acquisition to shelter |
| **Warrior Met Coal** (2016-17 → 2022) ✓ | New equity from Walter Energy's Ch 11 (Apollo/Blackstone/KKR/Franklin), IPO'd 2017 | ~400%+ 5-yr TSR; ~32% CAGR from IPO | **Cohort/capacity-exit**: the 2015-16 US coal bankruptcy wave removed supply and stripped legacy liabilities; met-coal price recovery hit a clean balance sheet |
| **Kmart** (2002-03) | Debt → control of reorg (ESL/Lampert) | New equity ~$15 → merged into Sears at ~$100+ (~10x, reported) | Real-estate value obscured by retail P&L; creditor control captured it |
| **Charter Communications** (2009 reorg) | New common post-Ch 11 | Decade-defining compounder from emergence | ~$8bn NOLs + cable-quality assets behind a scary leverage headline; no coverage at emergence |
| **Marvel** (1996-98 → 2009) | Post-reorg toy-co equity (Perelman/Icahn fight) | → Disney bought Marvel for $4bn (2009) | **Hidden asset**: the character IP library carried at ~nothing through the bankruptcy |
| **Texaco** (1987-88) | OLD common in a **solvent** Chapter 11 (Pennzoil judgment) | Icahn's biggest win to date (reported ~$500M+) | Litigation-driven filing of a solvent company — the case was about settling one claim, not insolvency |
| **Offshore drillers** (2021-23) | Fresh-start equities (Noble, Valaris, Seadrill '22, Tidewater '17) | Multiples on day-rate recovery | **Second-vintage** rule: the 2017-18 first restructurings were too early (Seadrill did Chapter 22); the 2020-21 vintage emerged at the supply-exit trough |
| **Tronox** (2011) | New common + retained litigation claim | Multi-bagger incl. the Anadarko environmental judgment (~$5bn to the trust) | Hidden litigation asset conveyed with the reorg |

## 2. Why the failures failed (the half that matters)

| Case | What went wrong | The observable-at-the-time flag |
|---|---|---|
| **Ultra Petroleum** (emerged 2017, refiled 2020) ✓ | Kept **~$2bn debt** through the first restructuring; gas prices stayed low | Residual leverage far above peers at emergence; commodity assumption baked into the plan |
| **Gymboree / Payless** (Chapter 22s, 2017→2019) ✓ | **Secular** decline (mall retail) — fixing the balance sheet fixed nothing; Gymboree's LBO left $1.2bn debt, interest expense 0.25M → 91M | Secular-demand industry + still-levered plan + sponsor-extraction history |
| **Seadrill** (2017 → 2021 Chapter 22) | First-vintage restructuring before industry supply had exited | Peers still adding/holding capacity; day rates still falling at emergence |
| **iHeart, Intelsat** | Emerged still heavily levered into secular pressure | Leverage retained + declining end-market |
| **Sears, BBBY, JCPenney old equity** | Retail held OLD shares hoping for a Hertz | **No equity committee, no plan competition, deeply insolvent estate** — the two Hertz preconditions absent |

The Hertz-vs-zero discriminator is mechanical: an **official equity
committee** (the court signaling possible solvency) and/or **competing plan
sponsors** bidding for the estate. Absent both, in-case old equity is a
donation.

## 3. The documented practitioner process (the books)

- **Greenblatt, *You Can Be a Stock Market Genius***: post-reorg equity is
  systematically mispriced because it is **distributed to creditors who never
  wanted it** and has **no coverage**; his method — read the plan of
  reorganization and disclosure statement, watch the new equity list, buy
  after the unnatural selling. (Our Q2/forced-seller thesis is his, formalized.)
- **Whitman, *Distress Investing***: "safe and cheap" via the capital
  structure — creditors control reorganizations, so understand WHO controls
  the plan and take the instrument they're paying themselves in.
- **Moyer, *Distressed Debt Analysis***: map the full capital structure,
  find the **fulcrum security**, value the enterprise through the waterfall —
  the analytical spine for any REAL waterfall we hand-build.
- **Klarman, *Margin of Safety***: three stages of a bankruptcy investment
  (post-filing chaos → negotiation → emergence); the cheapest, safest entries
  cluster in stage one and at emergence; beware businesses eroding while in
  chapter (professional fees + customer flight).
- **Rosenberg, *The Vulture Investors* / Wilbur Ross**: buy the industry's
  assets out of bankruptcy at the cycle bottom and **consolidate** (ISG: LTV +
  Bethlehem steel assets 2002 → sold to Mittal 2004-05, reported ~10-14x) —
  the cohort/capacity-exit play, executed with control.
- **Marks (Oaktree memos)**: the distressed **vintage** is everything — the
  rich vintages follow credit booms; "you can't predict, you can prepare."

## 4. Process improvements for cyclepapa (suggestions — not implemented)

### Sourcing (highest leverage, all free-data feasible)

| # | Improvement | Case evidence | How |
|---|---|---|---|
| S1 | **Equity-committee tracker** — flag Chapter 11s where an *official committee of equity security holders* is appointed | Hertz, GGP; absence = Sears/BBBY zeros | CourtListener docket search for "official committee of equity security holders" (extends `pacer_emergence_poll`) |
| S2 | **Plan-auction / competing-sponsor detector** — multiple competing plans = the estate is being bid up | Hertz ($1 → $8) | Docket phrases "competing plan", multiple plan-sponsor names in the same case |
| S3 | **NOL-shell registry** — reorganized shells whose tax attributes dwarf market cap | WMIH→COOP; Charter's $8bn | Our fresh-start cohort × XBRL deferred-tax/NOL disclosures ("net operating loss carryforwards of $") |
| S4 | **Solvent-debtor / litigation-Chapter-11 flag** — filing caused by a judgment or liquidity event, not operations | Texaco, USG, GGP | Filing-text classifier: judgment/appeal-bond/maturity-wall language vs operating-loss language |
| S5 | **DIP-provided-by-equity-holder signal** — an equity holder funding the DIP is betting the estate is solvent | Ackman/GGP | DIP-motion parties vs 13D/F holders cross-reference |
| S6 | **Post-reorg IPO/S-1 watch** — reorganized private companies IPO-ing (the Warrior Met path) | Warrior Met 2017 | S-1s whose text carries fresh-start/emergence language (extend the existing S-1 catch with issuer-age logic) |
| S7 | *(done this session)* Distressed-fund 13D control tracker | Every loan-to-own case above | `distressed_13d_poll` ✓ |

### Screening & analysis

| # | Improvement | Case evidence | How |
|---|---|---|---|
| A1 | **Cohort / capacity-exit lens** — count same-industry restructurings in our own inbox; a wave + supply exit marks the survivors' vintage as the buy | Coal '16, drillers '21, shipping, Ross/ISG | Group inbox bankruptcies by SIC/industry; flag emergences that follow ≥N same-industry filings |
| A2 | **Second-vintage rule** — an industry's *first* restructuring wave in a downcycle is often too early; flag re-restructured industries as the strong vintage | Seadrill 22 vs Noble/Valaris '21 | Same grouping, sequenced in time |
| A3 | **Normalized (mid-cycle) EBIT for cyclicals** — trough-EBIT/EV would have missed every driller winner; use 5-10yr median EBIT or EV/unit-capacity vs replacement cost | Drillers, coal | Longer XBRL history (we have `_xbrl_series`); flag "trough" explicitly rather than scoring it as bad |
| A4 | **Residual-leverage-at-emergence flag** — plan left debt near pre-petition levels = Chapter-22 precursor | Ultra, iHeart, Gymboree | Pre- vs post-petition liabilities from XBRL (flag only, no penalty — per house rule) |
| A5 | **Hidden-asset checklist** on YAML deep-dives — IP, real estate, litigation claims, tax attributes carried at ~zero | Marvel, Kmart, Tronox, WMIH | Manual checklist field in candidate YAMLs; not automatable |

### Timing, instrument, sizing, exit

| # | Improvement | Case evidence |
|---|---|---|
| T1 | **In-case old common only with S1/S2 present** (equity committee / plan auction); otherwise post-emergence new common only | Hertz vs Sears |
| T2 | **Entry window = the unnatural-selling window** (Greenblatt; our 13D/secondary-clearing signals time it) | Greenblatt's core rule |
| T3 | **Barbell sizing** — the category's return is right-tail-driven; many small positions beat few large ones *unless* you hold a control/information edge (Ackman had a board seat and the DIP) | Verdad data + GGP contrast |
| T4 | **Exit on natural-holder arrival** — coverage initiation, index inclusion, institutional uptake (matches Jiang-Wang-Yang academically) | Charter, Six Flags re-ratings |

## Sources (verified this session)
- Bloomberg via Crain's/creanalyst: Ackman GGP "$60M into $1.6bn"; stock 34¢→$31 ([creanalyst](https://www.creanalyst.com/insights/bill-ackmans-1.6-billion-ggp-win-a-masterclass-in-bankruptcy-investing), [Crain's](https://www.chicagobusiness.com/article/20140213/CRED03/140219851/general-growth-returns-not-enough-for-ackman-s-requirements))
- Forbes: ["The Greatest Deal Of All Time"](https://www.forbes.com/sites/nathanvardi/2014/07/30/the-greatest-deal-of-all-time/) (Apollo/LyondellBasell ~$2bn→$12bn); Bloomberg: [$9.6bn profit](https://www.bloomberg.com/news/articles/2013-06-25/apollo-fueled-by-9-6-billion-profit-on-debt-beats-peers)
- Hertz $8/share plan auction: [Bloomberg Law](https://news.bloomberglaw.com/bankruptcy-law/hertz-picks-knighthead-certares-bid-ending-bankruptcy-brawl-1), [Axios](https://www.axios.com/2021/05/13/hertz-shareholders-bankruptcy-investors-stock), [Auto Rental News](https://www.autorentalnews.com/news/stockholders-claim-victory-in-hertz-bankruptcy-auction)
- WMIH/Nationstar $3.8bn, KKR 24%: [HousingWire](https://www.housingwire.com/articles/46343-meet-the-mr-cooper-group-nationstar-completes-merger-with-washington-mutual-parent-wmih/), [BusinessWire](https://www.businesswire.com/news/home/20180213005465/en/WMIH-Corp.-Merge-Nationstar-Mortgage-Leading-Servicer)
- Warrior Met ~400% 5-yr TSR / 32% CAGR: [FinancialContent deep-dive](https://www.financialcontent.com/article/finterra-2026-3-25-deep-dive-warrior-met-coal-hcc-the-new-king-of-the-seaborne-steelmaking-market), [Paul Weiss](https://www.paulweiss.com/practices/transactional/restructuring/news/walter-energy-closes-sale-of-alabama-assets-to-warrior-met-coal?id=21694)
- Ultra Chapter 22 (~$2bn debt retained): [Bloomberg Law](https://news.bloomberglaw.com/bankruptcy-law/ultra-emerges-from-bankruptcy-after-completing-restructuring), [GlobeNewswire](https://www.globenewswire.com/news-release/2020/09/16/2094752/0/en/Ultra-Successfully-Completes-Financial-Restructuring-and-Emergence-from-Bankruptcy.html)
- Gymboree/Payless Chapter 22: [NY Law Journal](https://www.law.com/newyorklawjournal/2019/03/28/after-emerging-from-chapter-11-gymboree-payless-again-seek-bankruptcy-relief/), [Retail Dive](https://www.retaildive.com/news/payless-gymboree-and-the-road-to-chapter-22/548266/)
- Books: Greenblatt *You Can Be a Stock Market Genius*; Whitman & Diz *Distress Investing*; Moyer *Distressed Debt Analysis*; Klarman *Margin of Safety*; Rosenberg *The Vulture Investors*; Gilson *Creating Value Through Corporate Restructuring*; Oaktree memos. (Process points paraphrased from the books' well-documented arguments.)
