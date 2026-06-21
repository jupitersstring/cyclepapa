# Process improvements — meta-survey of special-situations practice

Synthesised from a deep-research sweep of canonical books, fund letters,
practitioner blogs, and academic finance papers (June 2026). Focused
explicitly on **sourcing** (where to find ideas the framework doesn't
yet poll) and **diligence depth** (how to pressure-test theses beyond
what the YAMLs already require).

Each recommendation cites its source, states the technique concretely,
and slots into a specific file or process in this repo.

---

## SOURCING — new signal streams to add

### 1. CourtListener RECAP — federal court & bankruptcy docket alerts

**Source:** CourtListener's RECAP Archive ([help docs](https://www.courtlistener.com/help/alerts/)).
The non-profit Free Law Project mirrors PACER filings; alerts can fire
"within seconds of a new filing" on active cases. Free tier gives 5
docket alerts (15 with their browser extension); paid membership is
unlimited; corporate API rates available.

**Why it matters for us:** the framework's pollers cover regulatory
filings (EDGAR/NSM/SEDAR+/TDnet) but miss the *judicial* leg of
distress. The richest signal in a Chapter 11 is the docket — DIP
financing motions, plan-support agreements, claim trades, examiner
reports, 2019 statements (ad-hoc committee membership), retention
applications (which advisors are mandated), Section 363 sale orders.
Hedge funds appointed to Unsecured Creditors' Committees are
"30 percent more likely to have high portfolio turnover" — they get
MNPI legally and trade on it (see [Oxford Law Blog](https://blogs.law.ox.ac.uk/oblb/blog-post/2024/06/do-hedge-funds-exploit-material-nonpublic-information-bankrupt-companies)
and [Columbia CLS Blue Sky Blog](https://clsbluesky.law.columbia.edu/2023/12/20/do-hedge-funds-exploit-material-nonpublic-information-from-bankrupt-companies/)).
About 40% of Chapter 11s have at least one hedge fund on the UCC. We
can't get on UCCs but we can monitor *which funds did*, which is itself
a revealed-preference signal.

**Slot:** new `src/pacer_poll.py`. Subscribe to docket alerts on every
Chapter 11 above $1bn in liabilities. Parse 2019 statements (Rule 2019)
to identify ad-hoc committee members — that's the cap-stack alignment
revealed-preference data the framework's Leg 3 triangulation has been
flagging as "partial" on many YAMLs.

### 2. Korean DART + KRX KIND — fully open XBRL disclosure API

**Source:** [DART English portal](https://englishdart.fss.or.kr/) +
[XBRL.org coverage](https://www.xbrl.org/news/south-korea-expands-english-disclosure-system-to-boost-foreign-investment/).
The FSS expanded DART's English API in 2023; "83 types of disclosure data"
now exposed with "an API for real-time data transmission." Already
machine-readable XBRL. KRX KIND added Papago AI translation for the
exchange-side filings.

**Why it matters:** Korea is where the framework already has its single
highest conviction reform thesis (Korean Commercial Act 3rd amendment
March 2026, treasury-share cancellation deadlines; we trade Doosan
Bobcat 241560 on this). But we have *no* Korea poller — DSK
disclosures, large-shareholding reports (5%), tender offers, and the
Value-Up programme filings all sit in DART/KIND. That's the most
egregious geographic gap.

**Slot:** `src/krx_poll.py` (new). API key registration is free, no
session bypass needed. Pull periodically by `corp_code` for: 주요사항보고
(major business reports — Korea's 8-K equivalent), 지분공시 (5%+ holding
disclosures), 합병/분할 (merger/split filings), 공개매수 (TOB
announcements), 자기주식 (treasury share activity).

### 3. Brazilian CVM IPE + B3 — Resolution 44 material-fact feed

**Source:** [CVM Resolution 44/2021](https://www.gov.br/cvm/en/foreign-investors/regulation-files/CVMRESOLUTION175OFDECEMBER232022ENGLISH1.pdf)
mandates real-time disclosure of material facts and significant
shareholdings. Filed through B3's IPE (Informações Periódicas e
Eventuais) and CVM's portal.

**Why it matters:** Latin America's currently four of the top eight
on our universe risk-reward ranking (TGS, EDN, GGAL, PAM — all
Argentine). Brazil is a structural gap — Petrobras governance episodes,
Eletrobras post-privatisation, the JBS-Mariana cycle, all special-
situations playbooks we've missed. Adding Brazil + Argentina + Mexico
disclosure feeds would let the LatAm cluster cap actually bind in the
portfolio.

**Slot:** `src/lat_am_poll.py`. Three sub-fetchers (Brazil CVM, Mexico
BMV, Argentina CNV). Material-fact filings are the canonical event
trigger; significant-shareholding disclosures (Brazil's resolution-44
equivalent of 13D) are the cluster-buys analogue.

### 4. Lobbying disclosure (LDA + STOCK Act) — policy-anchor early warning

**Source:** [House Lobbying Disclosure](https://lobbyingdisclosure.house.gov/)
+ [Senate LDA reports](https://www.senate.gov/legislative/Public_Disclosure/LDA_reports.htm)
+ [OpenSecrets](https://www.opensecrets.org/federal-lobbying/methodology).
LD-1/LD-2 filings since 1999 are bulk-downloadable. STOCK Act requires
Congressional disclosure of personal trades >$1k within 45 days.

**Why it matters:** the framework's A2 archetype (sovereign industrial
policy) depends on policy-anchor timing — DOE ATVM loans for LAC,
CHIPS Act for MP/UREE/TMQ, EU IAA for SZG/TKA. Lobbying disclosures
*precede* the policy decisions by 1-3 quarters. When the lobbying
registration shows a target issuer hiring a former DOE Loan Programs
Office director, that's a hard pre-anchor signal six months before the
loan term sheet. Same for FCC spectrum auctions and FDA AdComm timing.

**Slot:** new `src/policy_anchor_poll.py`. Pull bulk LD-2 quarterly
filings; cross-reference issuer names against the universe.md tickers;
surface any new lobbying engagement on issues like "ATVM loan
application," "CHIPS Act eligibility," "Defense Production Act
allocation." Output goes to `data/inbox/<date>/policy_anchor/` and
inbox_promote.py promotes it under a new `rev_pref.lobbying` label.

### 5. Expert-network transcript libraries (AlphaSense/Tegus)

**Source:** [Top expert network buyer's guide](https://iqnetwork.co/best-expert-networks-2026/);
the AlphaSense-Tegus merger now offers what the industry calls "the
most comprehensive transcript library" of former-executive calls.

**Why it matters:** the YAMLs have a Leg 3 (revealed preference) gap
on most names because we can't observe insider conversations. Expert
transcripts are the institutional substitute. The cost (~$25k-100k/yr
for individual subscriptions) is non-trivial but a single avoided
mistake on a $1m position pays for years.

**Slot:** this is an external service, not a script. But: add a
`expert_network_followup` field to the scorecard for each Tier-1 YAML
that records the date+topic of the last expert call. The audit script
should flag any Tier-1 YAML whose expert-call timestamp is >90 days
stale.

### 6. Workforce signal — Glassdoor/LinkedIn turnover + hiring patterns

**Source:** [ExtractAlpha alt-data catalogue](https://extractalpha.com/2025/07/07/5-best-alternative-data-sources-for-hedge-funds/)
claims workforce analytics "improved earnings prediction accuracy by 18%."
Not a verified causal claim but the directionality is well-documented
in academic finance (Glassdoor sentiment predicts earnings surprises
out 1-2 quarters; LinkedIn hiring velocity predicts revenue 2-3
quarters ahead).

**Why it matters:** for the H archetype (governance reset, e.g.,
Doosan Bobcat 241560), the discriminating signal between "restructuring
will execute" vs "restructuring is theatre" is usually whether the new
board+management actually hire builders. We can observe this for free
via LinkedIn employee count + senior-hire announcements.

**Slot:** `src/workforce_signal.py`. Per ticker in `data/candidates/`,
scrape monthly LinkedIn headcount + top-3 most senior hires.
Add a new scorecard dimension `d22_workforce_velocity` capturing the
hiring trajectory. Free LinkedIn data via public profile pages is the
honest legal path.

### 7. T+2 large-trade detection from exchange tapes

**Source:** less-discussed in fund letters but heavily used by event-
driven desks. NYSE TAQ, LSE Order Book, JPX tick data all show large
block prints — often the first signal of a forming activist position
or an exiting strategic seller weeks before the SC 13D requirement
kicks in.

**Why it matters:** the framework's revealed-preference leg often
lags the actual cap-stack action by 10+ business days because we rely
on SC 13D filing (10-day window after crossing 5%). Exchange tape
shows the block prints in real time.

**Slot:** not free; defer to v3. Documented here as a known gap.

---

## DILIGENCE DEPTH — additions to the memo/scorecard discipline

### A. Klarman's 10-rule checklist (Margin of Safety)

**Source:** consolidated from [Compounding Quality's distillation](https://www.compoundingquality.net/p/10-rules-from-seth-klarman)
of Klarman's *Margin of Safety* (1991).

Three of the ten that aren't yet in our YAML scorecard:

- **"Don't follow the crowd."** Add a `crowd_check` field: count of
  sell-side analysts covering vs. peer median. Tier 1 names should
  preferentially be under-covered.
- **"Wall Street is not your friend."** Add `sellside_conflict_flag`:
  is the issuer's lead underwriter on a recent capital raise also
  publishing initiated-with-buy research? That's a structural conflict
  that contaminates the consensus EBITDA target our `d11` field uses.
- **"Estimate intrinsic value in wide ranges, not points."** Our
  `d11_consensus_ebitda_cagr` is a point estimate. Add `_lo` and `_hi`
  bands. The proxy reward/risk in `universe_risk_reward.py` already
  treats a range; the YAML scorecard should too.

**Slot:** extend `scorecard:` block schema in YAMLs + add validation
in `src/score.py`. `src/yaml_skeleton.py` already auto-populates with
sensible defaults so existing YAMLs degrade gracefully.

### B. Howard Marks "what's not in the price?" framing

**Source:** Marks' *The Most Important Thing* + the [Oaktree memo
collection](https://www.oaktreecapital.com/docs/default-source/memos/the-complete-collection.pdf).
Marks' canonical first question: "If I'm right, how much do I make?
If I'm wrong, how much do I lose? What does the market need to believe
for current price to be fair?"

The first two are in our waterfall. The third — "what does the market
need to believe" — is the framing that's missing from most of our
pre-mortems.

**Slot:** add `consensus_pricing:` block to YAML schema. For each
Tier 1 name, explicit fields: `consensus_implied_ebitda`,
`consensus_implied_multiple`, `gap_to_our_base` (in %). The pre-mortem
then asks: "what would the market need to learn to converge to our
base?" — a direct, falsifiable framing.

### C. Moyer's indenture analysis & big-boy letter discipline

**Source:** [*Distressed Debt Analysis* by Stephen Moyer](https://www.amazon.com/Distressed-Debt-Analysis-Strategies-Speculative/dp/B00SQD8OPG)
— the canonical textbook. Heavy on indenture reading. Includes
"big-boy letters" (the bilateral acknowledgment that a counterparty has
material non-public information and is buying anyway).

**Specific techniques the framework doesn't yet require:**

- **MFN clause check.** Most modern restructurings include MFN
  ("most-favoured-nation") clauses that retroactively reprice earlier
  paper if a later tranche prices better. If our anchor took its
  position at par and a subsequent placement priced at 30¢, MFN means
  we sit *above* the anchor in some respects. The framework's red-flag
  checklist has nothing on this.
- **Fiduciary-out clause interrogation.** Most takeover circulars
  include the target's right to terminate for a "Superior Proposal,"
  but the definition is heavily negotiated. Tight definitions (e.g.,
  "must be a fully financed cash offer of at least 110% of the
  existing offer") effectively block topping bids. Loose definitions
  invite shoots. Our anchor/triangulation discussion currently treats
  the offer as binary.
- **Springing lien / springing covenant detection.** Already partially
  in our checklist (`springing_maturity_inside_24m`). Extend to
  springing covenants and springing liens in side-letters or
  collateral packages.

**Slot:** extend `red_flags:` checklist in YAML schema with three new
booleans: `mfn_below_us`, `fiduciary_out_overly_tight`,
`springing_covenant`. Add a `_watchlist` entry pattern.

### D. Voss Capital's multi-catalyst thesis structure

**Source:** [Voss Q4 2025 letter](https://vosscapital.substack.com/p/voss-capital-q4-2025-quarterly-letter).
Their Choice Hotels (CHH) thesis explicitly stacked four independent
catalysts (portfolio rebalancing + ~$700M capital unlock + demographic
tailwind + activist potential at 26% SI/40% insider ownership). Each
catalyst sized separately for probability and re-rate magnitude.

**Why it matters:** our YAMLs sometimes list 2-3 catalysts but only
*one* tends to be load-bearing. Voss's discipline of *multiple
independent triggers* is what produces convex outcomes — any one
catalyst firing is sufficient for the thesis to work.

**Slot:** add `catalyst_independence_score:` to YAMLs — for each pair
of catalysts, score whether they share a common dependency (0=fully
independent, 1=same dependency). Sum gives an independence count.
Tier 1 promotion requires independence ≥ 2.

### E. Andrew Walker's "weird capital structure" filter

**Source:** [Yet Another Value Blog](https://www.yetanothervalueblog.com/about);
Walker's stated thesis bias is "weird capital structures, busted
compounders, and occasional macro setups." His sourcing is *post-event
debris* — companies where a recap, spinoff, or scheme has just
completed and the standard screens haven't refreshed yet.

The framework already has the bucket/archetype taxonomy for this; the
gap is in the *post-completion clock*. We don't have a field for
"days-since-restructuring-completion," and a name 60 days after a
Companies Act Part 26 scheme is often where the maximum information
asymmetry sits.

**Slot:** in `src/score.py` derive `days_since_recap` from
`deal.date`. Surface in the workbook. Anything 30-180 days post-
restructuring gets a +1 to the universe-screener score (heuristic for
the index-rebalance lag).

### F. Ad-hoc committee / Rule 2019 statement parsing

**Source:** academic literature on UCC committee membership cited above
+ practitioner discussions on bankruptcy claims trading. Rule 2019
requires any entity holding multiple claims in a bankruptcy to disclose
holdings and acquisition prices.

**Why it matters:** this is the cleanest revealed-preference data
anywhere in finance — actual dollars paid for actual claims by named
funds. Currently we infer revealed preference from secondary signals
(SC 13D, anchor stake announcements). Rule 2019 statements give us the
ledger.

**Slot:** `src/pacer_poll.py` (same script as #1 in sourcing) should
specifically parse Rule 2019 filings and surface the holdings + prices
as records under `data/inbox/<date>/rule_2019/`. Feed into
`triangulation.leg3_revealed_pref` validation.

### G. Expert-network channel-check protocol

**Source:** [Best expert networks 2026 guide](https://iqnetwork.co/best-expert-networks-2026/)
+ standard buy-side practice. Top funds run 5-10 expert calls per Tier
1 thesis before sizing up.

**Slot:** add `expert_calls:` block to YAML schema — list of `{date,
expert_role, key_takeaways, contradicts_thesis_yn}`. Audit script
flags any Tier 1 YAML with `state: core` but `expert_calls` list of
length < 3.

### H. STOCK Act personal-trade cross-reference

**Source:** [Senate STOCK Act disclosures](https://www.senate.gov/legislative/lobbyingdisc.htm);
all Member trades $1k+ disclosed within 45 days. Now machine-readable
via Quiver Quantitative and similar.

**Why it matters:** when a Member who sits on the committee of
jurisdiction for an issuer's industry buys the stock, that's a hard
revealed-preference signal that policy is moving in the issuer's
favour. Doesn't help with bear cases but adds noise-free positive
signal for the A2 archetype.

**Slot:** `src/policy_anchor_poll.py` (combined with #4 above) cross-
references STOCK Act trades against universe.md tickers.

---

## What to implement THIS WEEK

Sequenced by ratio of (signal added) ÷ (engineering effort):

1. **Korean DART poller** (`src/krx_poll.py`) — closes our single
   largest geographic gap, on a fully open machine-readable API.
   ~1 day of work.
2. **PACER docket alerts** (`src/pacer_poll.py`) — 5 free alerts at
   the CourtListener tier covers our top US distressed positions.
   ~½ day of work for the alert subscriber; ~1 day for the parser to
   normalize docket entries into inbox records.
3. **YAML schema additions for diligence depth** — Klarman three
   missing checks (crowd, sellside-conflict, range bands), Marks
   consensus_pricing block, Voss catalyst-independence score, Moyer
   three new red flags (MFN, fiduciary-out, springing covenant).
   ~½ day of schema work, then back-fill the 21 Tier-1+2 YAMLs.
4. **Brazil CVM poller** (`src/lat_am_poll.py`) — second-largest
   geographic gap. Latam already dominates our universe top 8 via
   YPF + the four Argentine A1s.
5. **Lobbying-disclosure poller** (`src/policy_anchor_poll.py`) — A2
   archetype pre-anchor signal. STOCK Act cross-reference included
   for free.

Items 1+2+4+5 together add four new pollers to the chain and remove
the framework's largest blind spots (Korea, US courts, LatAm, US
policy). Item 3 closes the diligence-depth gap on already-built YAMLs
without breaking back-compat (additive fields only).

---

## What to defer

- **Satellite imagery, transaction data, web-traffic signals** — the
  ExtractAlpha catalogue lists them but the cost (up to $1m/yr for
  premium transaction data) doesn't fit a research-grade framework.
  These are quant-shop tools, not special-situations tools.
- **Expert network subscriptions** — defer until the framework has a
  P&L track record to justify the $25-100k/yr cost. In the interim,
  log every public-domain expert call (industry conferences, podcast
  appearances by named experts) in the new `expert_calls:` YAML block.
- **Real-time exchange-tape T+2 large-trade detection** — requires
  paid tape access. Defer to v3.
- **Bramson/Sherborne-style activist sourcing** — the literature is
  heavy on rhetoric, light on technique; Edward Bramson's track record
  doesn't justify mining the writeups. Skip.

---

## Sources

Primary:
- [CourtListener RECAP Archive help](https://www.courtlistener.com/help/alerts/)
- [DART Korea English portal](https://englishdart.fss.or.kr/)
- [XBRL.org — South Korea English disclosure expansion](https://www.xbrl.org/news/south-korea-expands-english-disclosure-system-to-boost-foreign-investment/)
- [CVM Brazil Resolution 175/2022 English](https://www.gov.br/cvm/en/foreign-investors/regulation-files/CVMRESOLUTION175OFDECEMBER232022ENGLISH1.pdf)
- [House Lobbying Disclosure search](https://lobbyingdisclosure.house.gov/)
- [Senate LDA reports](https://www.senate.gov/legislative/Public_Disclosure/LDA_reports.htm)
- [Voss Capital Q4 2025 letter](https://vosscapital.substack.com/p/voss-capital-q4-2025-quarterly-letter)
- [Oaktree memo Complete Collection (Marks)](https://www.oaktreecapital.com/docs/default-source/memos/the-complete-collection.pdf)
- [Compounding Quality — Klarman 10 rules](https://www.compoundingquality.net/p/10-rules-from-seth-klarman)
- [Yet Another Value Blog (Andrew Walker)](https://www.yetanothervalueblog.com/about)
- [Distressed Debt Analysis (Stephen Moyer)](https://www.amazon.com/Distressed-Debt-Analysis-Strategies-Speculative/dp/B00SQD8OPG)

Academic / verification:
- [Oxford Law Blogs — Hedge funds & MNPI from bankrupt cos](https://blogs.law.ox.ac.uk/oblb/blog-post/2024/06/do-hedge-funds-exploit-material-nonpublic-information-bankrupt-companies)
- [Columbia CLS Blue Sky Blog — same paper](https://clsbluesky.law.columbia.edu/2023/12/20/do-hedge-funds-exploit-material-nonpublic-information-from-bankrupt-companies/)
- [Georgetown Law — Bankruptcy Claims Trading](https://scholarship.law.georgetown.edu/cgi/viewcontent.cgi?article=1181&context=facpub)

Industry catalogues:
- [ExtractAlpha — 5 alt-data sources for hedge funds](https://extractalpha.com/2025/07/07/5-best-alternative-data-sources-for-hedge-funds/)
- [iqnetwork.co — Top expert networks 2026](https://iqnetwork.co/best-expert-networks-2026/)
- [NYU Stern — Investing in Distressed Securities course outline (Edward Altman / Moyer reading)](https://w4.stern.nyu.edu/finance/docs/pdfs/Outlines/2018-1/1801-b403176-Brown.pdf)
