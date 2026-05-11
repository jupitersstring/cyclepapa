# Capital-Structure Screening for Long Conviction

A practical playbook for finding the next multibagger inside ugly recaps.
Four hard problems to solve, in order:

1. **Discovery.** Surface the right deals out of the thousand
   restructurings, rights issues, exchange offers, and UCC filings that hit
   the wires every week.
2. **Alignment.** Tell — fast — whether the deal rescues *legacy common* or
   is a creditor takeover dressed up as one.
3. **Seat selection.** Identify the right tranche (old common, rights,
   nil-paid rights, fulcrum debt, post-emergence common, warrants, CVRs)
   before sizing the trade.
4. **Timing.** Act at the right stage of the deal calendar — most of the
   alpha lives in narrow windows (nil-paid rights, rump auction, when-issued
   common).

---

## 1. Discovery pipeline (RSS + form filters + keyword regex)

The goal is a daily inbox of 5–20 candidates pulled automatically from
primary sources, not a weekly trawl through PitchBook or Bloomberg headlines.

### 1.1 Primary regulatory feeds (free, RSS/Atom/JSON)

| Jurisdiction | Source | Feed | What to pull |
|---|---|---|---|
| US | SEC EDGAR current | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom` | 8-K, 6-K, S-3/424B, 13D/G, T-3, 15-12B, NT-10 |
| US | SEC EDGAR full-text | `https://efts.sec.gov/LATEST/search-index?q=...&forms=...` (JSON) | Keyword + form-type slice |
| Canada | SEDAR+ | Per-issuer Atom on `sedarplus.ca` | Material change reports, rights offering circulars |
| UK | LSE RNS | `londonstockexchange.com/news?tab=news-explorer` (RSS per ticker) | Rights issues, scheme circulars, restructuring plan notices |
| EU | OAM hubs (AMF, BaFin, AFM, FINMA, ESMA) | Per-regulator RSS | Prospectuses, ad-hoc disclosures, StaRUG/WHOA notices |
| Australia | ASX Announcements | `asx.com.au/asx/v2/statistics/announcements.do?timeframe=D` | Capital raisings, voluntary administration |
| India | BSE/NSE corp announcements | `bseindia.com/corporates/ann.html` (HTML) + NSE API | Rights issues, QIP, FPO |
| Singapore | SGXNet | Per-issuer RSS | Rights issues, scheme of arrangement |
| Court dockets | CourtListener (RECAP) | RSS per case + bankruptcy keyword alerts | First-day declarations, DIP motions, plan/disclosure statements |
| UCC | State SoS portals + UCCDirect / Wolters Kluwer | Per-debtor saved search | New/amended/terminated UCC-1 |

Most state SoS sites don't expose RSS. Practical workaround: twice-weekly
scrape of saved-debtor searches for the watchlist (200–500 tickers), or a
paid feed (UCCDirect, Lien Solutions, CSC).

### 1.2 Form-type and item filters

Cast a wide net by form, then narrow by item code:

- **8-K Item 1.01** — entry into material definitive agreement (credit
  agreements, indentures, backstop agreements)
- **8-K Item 1.03** — bankruptcy or receivership
- **8-K Item 2.03 / 2.04** — creation of / triggering events under direct
  financial obligations
- **8-K Item 3.02 / 3.03** — unregistered equity sales; modification of
  rights of security holders
- **8-K Item 5.07** — vote results (restructuring approvals)
- **6-K** — foreign private issuers (Petra/Viaplay/Brait window)
- **13D + amendments** — anchor investor disclosure, group formation
- **S-3 / 424B5** — prospectus supplements at the moment of pricing
- **T-3** — new indenture qualification (often signals exchange mechanics)
- **DEF 14A** — restructuring votes, MIP approvals
- **NT-10** — late filer (precursor to distress)

### 1.3 Keyword regex (run against feed titles + first page of filing)

Tier these so the inbox is sorted by signal strength.

```
TIER_S = r"\b(tender offer|exchange offer|consent solicitation|" \
         r"rights (offering|issue)|backstop(ped)? (commit|agreement)|" \
         r"debt[- ]for[- ]equity|loan[- ]to[- ]equity|" \
         r"capped call|convertible (senior )?notes|" \
         r"maturity extension|amend(ed)? and extend|" \
         r"scheme of arrangement|StaRUG|WHOA|restructuring plan|" \
         r"prepackaged plan|plan of reorganization|" \
         r"UCC termination|lien release|" \
         r"DIP financing|exit financing)\b"

TIER_A = r"\b(upsized revolver|repriced term loan|" \
         r"refinanc(e|ing)|early redemption|call notice|" \
         r"capital raise|primary offering|" \
         r"strategic investor|anchor investor|" \
         r"private placement|PIPE)\b"

TIER_B = r"\b(secured (term )?loan|second[- ]lien|" \
         r"warrants? (attached|issued)|" \
         r"PIK toggle|payment in kind)\b"

RED_FLAGS = r"\b(going concern|substantial doubt|covenant waiver|" \
            r"forbearance agreement|payment default|" \
            r"missed (coupon|interest)|" \
            r"strategic alternatives|hire(d)? (financial )?advisor)\b"
```

`RED_FLAGS` matched *before* a `TIER_S` event is the highest-value early-
warning lane — 3–9 month leading indicators of the deal that matters.

### 1.4 Concrete EDGAR full-text queries

EDGAR's full-text endpoint accepts JSON queries with form-type filters.
A starter daily script:

```python
import requests, datetime as dt, urllib.parse as up

EDGAR = "https://efts.sec.gov/LATEST/search-index"
HEADERS = {"User-Agent": "screener you@example.com"}
TODAY = dt.date.today().isoformat()

QUERIES = {
    "rights_offering":      '"rights offering" OR "rights issue"',
    "backstop_agreement":   '"backstop agreement" OR "backstop commitment"',
    "exchange_offer":       '"exchange offer"',
    "consent_solicitation": '"consent solicitation"',
    "lien_release":         '"UCC termination" OR "lien release"',
    "going_concern":        '"substantial doubt" AND "going concern"',
    "scheme":               '"scheme of arrangement" OR "restructuring plan"',
}
FORMS = "8-K,6-K,S-1,S-3,424B5,T-3,SC 13D,DEF 14A"

for label, q in QUERIES.items():
    params = {
        "q": q, "forms": FORMS,
        "dateRange": "custom", "startdt": TODAY, "enddt": TODAY,
    }
    r = requests.get(EDGAR, params=params, headers=HEADERS, timeout=30)
    for hit in r.json().get("hits", {}).get("hits", []):
        src = hit["_source"]
        yield {
            "tier": label,
            "cik": src["ciks"][0],
            "ticker": src.get("tickers", [None])[0],
            "form": src["form"],
            "accession": src["adsh"],
            "filed": src["file_date"],
            "url": f"https://www.sec.gov/Archives/edgar/data/{int(src['ciks'][0])}/{src['adsh'].replace('-','')}",
        }
```

Adapt the same pattern for: SEDAR+ Atom, LSE RNS HTML scrape, ASX
announcements JSON, BSE/NSE announcements HTML. Each issuer hit becomes a
row in the triage queue with `tier`, `ticker`, `form`, `accession`, `url`.

### 1.5 Secondary feeds (commentary, distress press)

- Reuters tag feeds (`/business/restructuring/`, `/markets/deals/`)
- FT Alphaville RSS
- Bloomberg Terminal `NSE BANKRUPTCY` / `NSE RECAPITALIZATION` (paid)
- *Petition* (Substack RSS) — weekly distress digest
- Reorg / Debtwire / 9fin (paid; trial APIs)
- Trustee / agent press releases: Kroll Restructuring Administration, Epiq,
  Stretto, Prime Clerk, DF King
- Court docket trackers: Stretto, Kroll, BMC Group public docket pages

### 1.6 Triage cadence

- **Daily (15 min).** Sort overnight feed by tier; tag candidates; queue
  filings for deep read.
- **Weekly (60 min).** Run watchlist UCC search; reconcile against bond
  trustee notices; refresh maturity wall for every name on the list.
- **Monthly.** Prune candidates that have not progressed (no Item 1.01, no
  anchor backstop disclosed, no maturity extension filed).

Binary discipline: a name either advances along the deal pipeline or falls
out. No "interesting, watching" purgatory.

---

## 2. Alignment scorecard

Most restructurings rescue the enterprise. Only a subset rescue *legacy
common*. Score each candidate 0–2 on each dimension; ≥18 of 28 is investable,
<13 is a "creditors-only" deal.

| # | Dimension | 0 (bad for common) | 1 (mixed) | 2 (good for common) |
|---|---|---|---|---|
| 1 | **Who funds the new money?** | Creditors via debt-for-equity, or new PE sponsor at a court-set price | New strategic with no prior position | Pro-rata rights; insiders/promoter writing a real cheque |
| 2 | **Issue price vs. market** | At a forced/court price or deep discount + backstop fees + warrants | Market-discount rights (20–40% TERP) but pro-rata access | At or near market; old common can defend pro-rata |
| 3 | **Backstop terms** | Backstoppers take rump + fees + warrants + board seats | Fee-only backstop | Backstop by largest existing holder at cost; no warrant kicker |
| 4 | **Dilution to old common** | >80% (e.g., Atos 90.8% to creditors) | 40–80% | <40% post-money |
| 5 | **Maturity wall removed** | <18 months runway (Spirit) | 18–36 months | 36+ months clean, no springing maturities |
| 6 | **Post-deal cap stack** | PIK toggles, multiple secured layers, springing liens | One messy layer to clean up | Single tranche, long maturity, covenant-lite |
| 7 | **UCC / lien movement** | New priming liens stacked on top of old | Mixed (new + terminations) | UCC-1 terminations dominate |
| 8 | **Management equity plan** | Cash retention bonuses only | MIP at pre-deal price | MIP at recap price; CEO writes personal cheque |
| 9 | **Sponsor/anchor identity** | Distressed fund known for loan-to-own | Generalist credit fund | Strategic operator, sovereign, or long-term shareholder |
| 10 | **Warrants / CVRs** | All to creditors | Token OTM warrants to old common | Real CVRs tied to litigation/asset/upside hurdle |
| 11 | **Operating catalyst** | None — pure financial restructuring | Cyclical reversion plausible | Identified product/cycle/contract catalyst within 24m |
| 12 | **Governance reset** | Untouched or stacked with creditor designees | Mixed slate | Clean board with sector pedigree |
| 13 | **Second-restructuring risk** | History of prior recap + no operating fix | Single prior recap, partial fix | First recap, operating model defensible |
| 14 | **Liquidity post-deal** | <6 months opex | 6–18 months | >18 months + revolver headroom |

### 2.1 Quantitative tests (run on filing day; re-run at close)

Each dimension has a defensible quantitative anchor:

| Dim | Quantitative test | Threshold (2 / 1 / 0) |
|---|---|---|
| 2 | Issue price discount to pre-announcement close | <30% / 30–50% / >50% |
| 3 | Backstop fee + warrant value as % of raise | <2% / 2–5% / >5% |
| 4 | New shares ÷ pre-deal shares | <0.67 / 0.67–4 / >4 |
| 5 | Δ weighted-average debt maturity | +24m / +12 to +24m / <+12m |
| 6 | Count of debt tranches post-deal | 1 / 2–3 / 4+ |
| 7 | UCC-1 terminations within ±30 days of close | ≥3 / 1–2 / 0 |
| 8 | MIP strike ÷ recap price | ≤1.0 / 1.0–1.5 / >1.5 |
| 9 | Anchor's cost basis premium to recap price | <0% / 0–25% / >25% |
| 11 | Consensus 24-month EBITDA CAGR | ≥30% / 10–30% / <10% |
| 13 | Pro-forma Altman Z-score | >2.9 / 1.8–2.9 / <1.8 |
| 14 | Liquidity ÷ quarterly opex | >6 / 2–6 / <2 |

Dimensions without a clean number (1, 10, 12) stay qualitative.

### 2.2 Decision tree (faster than scoring on the fly)

```
1. Did legacy common get pro-rata rights at a defendable price?
   NO  → likely creditor-economics deal; default skip unless #11 is extreme
   YES → continue
2. Is the maturity wall pushed >36 months with no springing maturities?
   NO  → bridge deal; pass unless catalyst <12 months
   YES → continue
3. Is dilution to old common <40%?
   NO  → re-underwrite at the post-money share count
   YES → continue
4. Is there a real anchor (insider, sponsor, sovereign) with cost basis at
   or near the recap price?
   NO  → no alignment; pass
   YES → buy candidate
5. Is the operating catalyst identifiable and dated within 24 months?
   NO  → option, size accordingly
   YES → core position
```

### 2.3 Red flags (any one is a pass by default)

- New money priced below the rights price via a parallel PIPE
- Multiple classes of new equity with asymmetric voting
- Backstop warrants struck at a fraction of TERP
- DIP-to-exit conversion where the DIP lender becomes controlling shareholder
- Springing maturities or PIK-toggle defaults inside 24 months
- "Stub equity" carve-out to old common at <10% post-money with no warrants
- Indemnity / release language that protects insiders from claw-back
- Equity-pledged backstop fees (cash fee + warrants + stock)
- Change-of-control puts that *trigger on* the rights issue itself
- Super-voting share class created for backstoppers (Atos-style)
- Forced consent solicitations that strip dissenting common rights
- Tax-driven structure locks legacy holders into illiquid stub at non-listed parent
- "Springing" maturity tied to a customer-contract event the company can't control
- MAC carve-outs in backstop agreements that let anchors walk before close
- Insider releases / indemnities that survive the recap (no clawback later)
- Forward / block-purchase agreements with backstoppers below TERP

### 2.4 Green flags (any two is a strong signal)

- Existing largest shareholder backstops the entire rights issue at TERP
  with no fee or warrant kicker
- UCC-1 terminations filed at close (real lien release, not rolled)
- Management MIP struck at recap price with 3–5 year vesting
- Sovereign or strategic operator buys primary shares at market
- CVR tied to specific asset sale or litigation outcome
- Cap stack collapses from 4+ tranches to 1–2
- Pro-forma net debt/EBITDA <3.5x with explicit deleveraging path
- Rights price set by formula (e.g., 5-day VWAP minus fixed %) — anchors
  can't game timing
- Insiders refuse backstop fees and warrants
- Top-tier-bank independent fairness opinion
- Public anchor commitment to hold 12+ months
- §382 NOL / tax attributes preserved
- Litigation or insurance-recovery trust assigned to legacy common only
- Mandatory deleveraging from FCF baked into new credit agreement
- Existing covenant package loosened (not tightened) — signal that lenders
  trust the new equity base

---

## 3. Signal taxonomy (UCC, Tier-S/A/B)

**UCC filings.** A UCC-1 is public notice of a security interest in a
borrower's assets — "someone now has a lien on the stuff." New UCC-1s mean
new secured debt or fresh collateral; terminations mean liens released
(usually post-repayment). A cluster of UCC events around a transaction is a
flag to scrutinize: it tells you who controls the asset base is changing.

**Tier-S events** (radically change the equity payoff):

- **Tender offers / debt buybacks** — pulls debt forward, smooths
  maturities, improves equity convexity.
- **Refinancing upgrades** — maturity extension, lower spreads, or moving
  from secured to unsecured. Petra extended bank debt 2026 → 2029 and notes
  2026 → 2030 alongside a rights issue.
- **Lien releases in refinancing** — UCC terminations bundled with new debt
  is a strong de-leveraging signal.
- **Equity-friendly convertibles** — high premium, capped calls, modest
  coupons. Nvidia's 2013 $1.3B at ~30% premium funded buybacks; equity
  multibagged because conversion only triggered at much higher prices.
- **Exchange offers / liability consents** — swap near-term bonds for
  longer paper, sometimes with warrants. Equity-friendly if cash interest
  drops and new paper isn't structurally senior to stub equity.

**Tier-A** (bullish but not transformational): upsized revolvers, repeated
paydowns, repricings, repeat issuance at tighter spreads.

**Tier-B** (mixed; depends on terms): new general loans, attached warrants,
second-lien add-ons, PIPEs without alignment.

---

## 4. Fulcrum security & instrument selection

The most leveraged analytical task in a Tier-S deal isn't "is this a good
company?" — it's identifying the *fulcrum security* and picking which seat
at the cap-table table you want.

### 4.1 Fulcrum math

The fulcrum is the most senior tranche that does *not* receive full
recovery in restructuring. It typically converts to majority post-emergence
equity.

**Step 1.** Estimate post-deal enterprise value in three scenarios:

- **Bear:** recent trough EBITDA × peer trough multiple, or liquidation
  value.
- **Base:** mid-cycle EBITDA × mid-cycle multiple.
- **Bull:** recovery-case EBITDA × peer normalized multiple.

**Step 2.** Walk the cap stack in priority order:

```
remaining_EV = scenario_EV
for tranche in priority_order:
    claim = face × (1 + accrued_to_petition)
    recovery_pct = min(remaining_EV, claim) / claim
    implied_value = recovery_pct × claim
    remaining_EV -= implied_value
```

**Step 3.** The tranche where `remaining_EV` first goes negative — the
partial-recovery tranche — is the fulcrum.

**Step 4.** Compare market prices to implied recoveries. If 2L trades at
60 but base-case recovery is 100, the market is pricing the bear. If you
believe the base case, the 2L offers ~67% upside *plus* the option on new
equity if restructured.

### 4.2 Worked fulcrum example (Petra-style hypothetical)

```
EV bear / base / bull = $600m / $900m / $1,400m

Tranche       Face    Mkt    Bear rec  Base rec  Bull rec
1L TL         $300m   98     100%      100%      100%
2L Notes      $400m   55     75%       100%      100% (+ equity)
Unsec         $150m   20     0%        67%       100%
Equity (mc)   $80m    —      0%        $0        ~$250m
```

Pick: 2L at 55. Bear: $40 loss. Base: $100 + new equity stub. Bull: $100 +
significant equity. Asymmetry is on the 2L, not the listed common.

### 4.3 Instrument-selection matrix

| Scenario | Best seat | Why |
|---|---|---|
| Pro-rata rights, anchor takes pro-rata, no fee | Subscribe rights | Cleanest alignment; no kicker to backstoppers |
| Pro-rata rights, backstop takes rump | Rights + bid the rump auction | Rump can clear cheap on weak take-up |
| Distressed exchange, equity preserved | Common (+ maybe new converts) | Old common is the fulcrum if exchange works |
| Distressed exchange, debt-to-equity heavy | New post-exchange common, not legacy | Legacy diluted past relevance |
| Pre-petition, fulcrum identified in 2L | 2L at distress price | Inherit new equity through plan |
| Post-emergence with WI common trading | When-issued common if ERO oversubscribed | Plan participants did the work |
| Convert with capped call | Equity, not the convert | Issuer set the hedge; equity has upside |
| State/strategic recap (Ørsted-style) | Common via rights | State alignment caps downside |
| Loan-to-equity by controlling shareholder | Pass | Control transfer; both old and new equity dilute |
| Nil-paid rights trading <TERP value | Nil-paid rights | Small illiquid market often 5–15% cheap |

The most under-traded instrument in this list is **nil-paid rights** — a
small, illiquid window between ex-rights date and subscription deadline
where most institutional holders auto-take or auto-sell at TERP. Patient
bids 5–15% below TERP-implied value frequently fill.

---

## 5. Event-timeline playbook

A Tier-S deal has eight observable stages. Price action and the optimal
action differ at each. Most alpha lives in the narrow windows (T = 0
shock, ex-rights nil-paid, rump auction).

| Stage | Signal | Typical price action | Optimal action |
|---|---|---|---|
| **T-9 to T-6m** | RX advisor hired, NT-10, going-concern language | Drift -20 to -50% | Watchlist; research traded debt |
| **T-3 to T-1m** | 8-K Item 1.01 agreement in principle | Whipsaw; rallies on relief, sells on dilution math | Score scenarios; pre-position fulcrum debt |
| **T = 0** | Formal launch; S-1 / prospectus / scheme circular | -10 to -40% on dilution shock | If score ≥ 18, take rights; if fulcrum is debt, buy in distress |
| **T+1 → record date** | Cum-rights trading | Drifts toward TERP | Buy cum-rights for the discount; sell stub |
| **Ex-rights date** | Nil-paid rights start trading | Common drops by TERP discount mechanically | Nil-paid rights often cheapest seat |
| **Subscription period** | Take-up updates | If take-up weak, common sells off | Bid the rump auction if held |
| **Settlement / close** | New shares list; UCC/lien filings hit | Relief rally if oversubscribed | Re-score post-deal; confirm ≥ 18 |
| **First earnings post-deal** | Cap structure visible in 10-Q / half-year | Re-rate up or down | Add on confirmed catalyst; trim on covenant slip |

---

## 6. Jurisdictional cheat sheet (where legacy common survives)

Same restructuring mechanism, different jurisdiction, very different
outcomes for old common. Adjust scorecard dimension #1 weight by venue.

| Jurisdiction | Mechanism | Legacy common survives | Notes |
|---|---|---|---|
| US | Ch.11 plan | ~10% of cases | Cancellation default unless ERO with shareholder allocation |
| US | Out-of-court exchange | ~70% | Common usually survives but dilutes |
| UK | Rights issue (Listing Rules) | ~95% | Pro-rata by rule; backstops common |
| UK | Scheme of arrangement (Pt 26) | ~30% | Can bind dissenting shareholders; can wipe |
| UK | Restructuring plan (Pt 26A) | ~20% | Cross-class cramdown (since 2020) — used to wipe |
| Netherlands | WHOA | ~25% | Dutch cramdown; recent cases have wiped common |
| Germany | StaRUG | ~20% | Used in Varta — shareholder reconstitution standard |
| France | Sauvegarde / sauvegarde accélérée | ~40% | Atos used this; creditors took ~90% |
| Sweden | Företagsrekonstruktion | ~40% | Intrum allowed common to keep economics |
| Australia | DOCA | ~50% | Variable; often paired with rights |
| HK / China | Scheme + Chapter 15 | ~15% | Country Garden — control transfers common |
| India | IBC / NCLT plan | ~5% | Promoter cram-down standard since 2016; rights pre-IBC is the trade |

Practical takeaway: a UK rights issue under Listing Rules is structurally
the most common-friendly path. US Chapter 11 is the least.

---

## 7. Macro filter (when is the universe rich?)

Run the discovery pipeline always, but expect candidate density to follow
the distress cycle. Sizing should scale with backdrop, not narrative.

| Indicator | Benign | Mid-cycle | Late-cycle | Peak distress |
|---|---|---|---|---|
| HY OAS | <300 bps | 300–500 | 500–800 | >800 |
| CCC spread | <600 | 600–900 | 900–1,400 | >1,400 |
| LSTA loan price index | >97 | 95–97 | 90–95 | <90 |
| Trailing 12m HY default rate | <2% | 2–3% | 3–5% | >5% |
| Maturity wall (BB+B next 24m) | <$300bn | $300–500bn | $500–800bn | >$800bn |
| Expected viable Tier-S candidates / mo | 1–2 | 2–4 | 5–8 | 8–15 |

In benign markets resist forcing trades; in stress, expand the watchlist
and accept lower-quality alignment scores if the macro tailwind is
generous (banking-cycle, commodity-cycle, rate-cut tailwind).

---

## 8. Case studies — scorecard verdicts

Each case is annotated with a scorecard read (S = score / 28). Directional,
not precise.

- **Yes Bank (India, 2020) — S ≈ 22/28.** RBI-forced rescue: SBI/private
  banks injected ~₹10,000 cr at ₹10/share; July 2020 FPO at floor ₹12
  raised another ₹15,000 cr. Common ran ~80x off the FPO floor.
- **Indian Bank (India, 2024) — S ≈ 20/28.** ₹5,000 cr equity + ₹7,000 cr
  debt. Stock roughly doubled within a year.
- **Goodman Group (ASX, 2009) — S ≈ 21/28.** 1-for-1 rights at A$0.40,
  CIC as cornerstone. ~60x including dividends by 2021. Wins: pro-rata
  access, sovereign anchor at same price, simple post-deal cap stack,
  e-commerce/logistics secular catalyst.
- **Nvidia (US, 2013) — S ≈ 21/28.** $1.3B 5-year converts at 30% premium,
  1% coupon, capped calls; proceeds funded buybacks. Equity multibagged.
- **Charter Communications (US, 2009 Ch.11)** — legacy stub S ≈ 2/28; new
  common S ≈ 19/28. Eliminated ~$8B of debt + $1.6B rights as part of the
  plan; old common cancelled, new common compounded into hundreds. The
  *multibagger seat* was the new common allocated to plan participants —
  not the listed equity. Same lesson as Arch Coal / Valaris / Core
  Scientific.
- **Tenneco (US, early 2000s)** — equity S ≈ 14/28; debt seat S ≈ 22/28.
  Munger bought the debt at deep discounts plus a small equity stub; equity
  ran from ~$1.50–2.00 to ~$15 as EBITDA recovered to $300–400m and debt
  was paid down. The *debt* was the higher-IRR seat — Munger captured par
  recovery and the equity option.
- **Coinbase (US, 2025) — S ≈ 16/28.** $2B converts, ~30–35% premium,
  capped calls. Good structure, no dated operating catalyst. Optionality,
  not core.
- **Petra Diamonds (UK, 2025) — S ≈ 14/28.** £18.8m fully underwritten
  rights, RCF extended to Dec 2029, notes to Mar 2030, cash-or-equity
  interest option. Default cliff gone; hinges on diamond prices.
- **Baxter (US, 2025) — S ≈ 13/28.** Cash tenders for 2026/2027 bonds
  funded by new unsecured debt. Marginally equity-positive.
- **Arch Coal → Core Natural Resources (US, post-Ch.11) — S ≈ 18/28 (new
  common).** Old cancelled; post-reorg shares multibagged.
- **Provident Financial (LSE, 2018) — S ≈ 8/28 in hindsight.** ~£330m
  fully-underwritten rescue rights; shares spiked +87.6% intraday. Long
  term, the home-credit franchise decayed (later refocused to Vanquis
  Banking Group). The canonical *rescue ≠ recovery* warning: rights fixed
  the capital ratio but not the franchise. Dim. #11 (operating catalyst)
  and #13 (second-restructuring risk) were both weak even though the
  headline raise looked clean.
- **Canopy Growth (Canada, 2026) — S ≈ 7/28.** New $162m TL to 2031; C$96m
  of 2029 converts exchanged for C$55m new converts + C$10.5m cash + ~9.5m
  new shares + 12.7m warrants. Creditors took the upside.
- **Country Garden (China, 2025) — S ≈ 4/28.** Controlling shareholder
  converted $1.14B of loans to equity at HK$0.60. Effective control
  transfer; legacy common almost entirely impaired.

### Two meta-lessons

1. **Seat selection.** Tenneco and Charter show the multibagger tranche in
   a recap is often the *debt* (bought sub-par, paid at par + equity stub)
   or the *new* post-emergence common — not the legacy listed equity.
   Always price all three seats before sizing.
2. **Rescue ≠ recovery.** Provident, Meyer Burger, Spirit all had clean
   rescue rights issues at face value but the operating franchise never
   re-rated. Scorecard dimensions #11 and #13 act as veto gates — a perfect
   12/12 on financial dimensions with 0 on operating catalyst is *still a
   pass*.

---

## 9. Current analogues — re-ranked by scorecard

| Rank | Situation | Mechanism | S (est.) | Key swing factor |
|---|---|---|---|---|
| 1 | **Calfrac (Canada)** | C$35m rights, director-backstopped + C$120m TL, 2L cleanup | 19/28 | NA frac cycle margins; backstoppers' cost basis = aligned |
| 2 | **Viaplay (Sweden)** | SEK 4bn equity + SEK 2bn write-down + SEK 0.5bn debt-to-equity + SEK 14.6bn A&E | 18/28 | Nordic refocus producing durable EBIT |
| 3 | **Brait (South Africa)** | R1.5bn rights + bond extension to Dec 2027 + convert reset to R2.21 | 17/28 | Virgin Active monetization; NAV-discount close |
| 4 | **Worldline (France)** | ~€500m raise, 121% subscribed, French banks anchored | 17/28 | Client retention; 2027 FCF credibility |
| 5 | **Ørsted (Denmark)** | DKK60bn rights, 99.3% subscribed, Danish state 50.1% | 16/28 | Offshore-wind IRR trough confirmed |
| 5= | **Eutelsat (France)** | ~€670m fully underwritten rights at €1.35; sovereign + strategic anchors funding LEO pivot | 16/28 | LEO execution vs. Starlink; OneWeb integration |
| 6 | **Petra Diamonds (UK)** | £18.8m rights + maturity push to 2029/2030 | 15/28 | Diamond price recovery |
| 7 | **SBB (Sweden)** | 95% participation in bond exchange, €2.78bn debt retired below par | 15/28 | Property valuations stabilizing |
| 8 | **Fossil (US)** | "Stapled Exchange" — UK plan + $32.5m new money, legacy equity preserved | 14/28 | Brand/licensing cash flows; cost cuts |
| 9 | **ams-OSRAM (Austria/CH)** | €2.25bn package incl. ~€800m rights | 14/28 | Auto/industrial cycle; debt-stack absorption |
| 10 | **Intrum (Sweden)** | Ch.11 + Swedish reorg, 10% discount on reinstated notes | 13/28 | Capital-light shift; Cerberus monetization |
| 11 | **Core Scientific (US)** | Plan with oversubscribed ERO; old holders ~60% incl. warrants | 13/28 | AI/HPC datacenter pivot |
| 12 | **Exicom (India)** | ~₹259 cr rights, ₹120 cr from promoter; debt-reduction use of proceeds | 13/28 | Tritium integration; EV charger margins |
| 13 | **OXE Marine (Sweden)** | MSEK 78 rights + MSEK 155 debt-to-equity + EIB warrant swap | 11/28 | Product traction; liquidity tail |
| 14 | **Ebusco (Netherlands)** | €36m rights at €0.8209, 64.3% take-up, shareholder loans converted | 10/28 | Production normalization |
| 14= | **mm2 Asia (Singapore)** | SGD15m private placement + SGD10m fully-underwritten rights | 10/28 | Post-pandemic media demand; no visible strategic anchor |
| 15 | **Ascot Resources (Canada)** | C$14.87m rights at C$0.01 + creditor settlement | 9/28 | Mine restart math; post-consolidation dilution |
| 16 | **Star Entertainment (Australia)** | A$300m, Bally's/Mathieson ~56% post-conversion | 8/28 | Control transfer reduces alignment |

### False friends (pass by default)

- **Atos (France)** — €2.9bn debt equitization; creditors ~90.8%. S ≈ 4.
- **Varta (Germany)** — StaRUG with shareholder reconstitution. S ≈ 5.
- **Beyond Meat (US)** — 2025 exchange could issue up to 326m new shares
  to retire >$800m debt. S ≈ 5.
- **Meyer Burger (Switzerland)** — CHF 200m 2024 rights didn't fix the
  business; subsequent bondholder talks confirm bridge-to-next-RX. S ≈ 4.
- **Spirit Airlines (US)** — Emerged March 2025, refiled August 2025. The
  canonical balance-sheet fix without operating fix. S ≈ 3.

### Shortlist by archetype

- **Pro-rata rights with insider/anchor backstop:** Calfrac, Brait, Petra,
  Exicom.
- **Discounted-debt-retirement / NAV convexity:** SBB.
- **State / strategic-anchor mega recap:** Ørsted, Worldline, Eutelsat.
- **Legal-structure preserves listed common:** Fossil, Viaplay.
- **Post-court recap where common kept real economics:** Core Scientific,
  Intrum.

---

## 10. Worked example: Calfrac Well Services

The highest-scoring current candidate, walked end-to-end.

**Stage 1 — Discovery.** SEDAR+ Atom feed surfaces the press release on
the day the financing announces. Form filter: rights offering circular.
Regex matches: `rights (offering|issue)`, `backstop`, `term loan`,
`second[- ]lien`. The hit lands in the Tier-S lane.

**Stage 2 — Scorecard (qualitative + quantitative):**

| Dim | Read | Score |
|---|---|---|
| 1 | Directors/insiders backstop pro-rata rights | 2 |
| 2 | Rights priced at modest discount (<30% to pre-announce) | 2 |
| 3 | Directors take rump at same price, modest fee (<2%) | 1 |
| 4 | New shares / pre-deal ≈ 0.35 → <0.67 | 2 |
| 5 | TL extended to 2028; 2L cleaned up; >24m extension | 2 |
| 6 | Cap stack simplifies to TL + revolver (2 tranches) | 1 |
| 7 | 2L lien terminated alongside redemption → UCC events | 2 |
| 8 | Existing MIP; no fresh strike | 1 |
| 9 | Insider directors as anchor; cost basis at recap price | 1 |
| 10 | No material warrants/CVRs | 1 |
| 11 | NA frac-cycle inflection identifiable within 24m | 2 |
| 12 | Board largely unchanged | 1 |
| 13 | First recap; manageable pro-forma leverage | 1 |
| 14 | >18m liquidity post-deal | 2 |

**Total: 22/28.** Above the 18 core threshold.

**Stage 3 — Seat selection.**

- *Old common:* trades near rights offer; dilution-adjusted upside ~3x in
  base case.
- *Rights:* same terms as backstoppers, no kicker — clean seat.
- *Nil-paid rights:* small market; check for sub-TERP fill.
- *Traded debt:* 2L being retired in the deal; nothing left to buy at
  distress.
- *Best seat:* subscribe rights cum-cum; supplement via nil-paid in the
  ex-rights window if it clears below TERP.

**Stage 4 — Event timeline.**

- *Pre-record date:* cum-rights common drifts toward TERP — accumulate
  half size.
- *Ex-rights:* monitor nil-paid; bid 5–10% below TERP for top-up.
- *Subscription:* watch take-up updates; if weak, bid rump auction.
- *Post-close:* confirm UCC terminations on 2L; re-score scorecard.

**Stage 5 — Kill criteria (set on day one).**

- Frac utilization <60% for two consecutive quarters → trim.
- New UCC-1 lien filed within 12 months → exit.
- Going-concern language returns → exit.
- Cap-stack re-leverages above 3.5x net debt/EBITDA → trim.
- Director anchor exits / sells → reassess fully.

**Stage 6 — Sizing.**

- 22/28 = core position.
- Macro backdrop (HY OAS mid-cycle, NA energy spending stabilizing) →
  full size.
- Currency hedge if non-CAD base currency.

---

## 11. Workflow summary

1. **Ingest.** RSS + EDGAR/SEDAR+/RNS form filters + UCC saved searches +
   court dockets feed a single triage inbox (§1).
2. **Tier.** Regex sorts hits into Tier-S / Tier-A / Tier-B / Red-Flag
   lanes (§1.3).
3. **Score.** 14-dimension alignment score on first read; quantitative
   tests on filing day; re-run at close (§2, §2.1).
4. **Decision tree.** Five gates: pro-rata → maturity → dilution → anchor
   → catalyst. Drop fast on first failure (§2.2).
5. **Fulcrum & seat selection.** Identify EV scenarios, walk cap stack,
   pick the seat with the cleanest payoff (§4). Listed common is the
   default but rarely the best risk-adjusted seat in Charter- or
   Tenneco-style situations.
6. **Time the entry.** Watch the eight-stage event timeline; most alpha
   lives in T = 0 dilution shock, nil-paid rights, and rump auction (§5).
7. **Adjust for jurisdiction.** Reweight dimension #1 by venue's legacy-
   common survival rate (§6).
8. **Macro-size.** Scale watchlist and tolerance with the distress cycle
   (§7). Don't force trades in benign regimes.
9. **Position.** Score ≥ 18 = core; 13–17 = option; <13 = pass or short
   the stub. Re-score on every amendment.
10. **Monitor.** UCC and 8-K Item 1.01/2.04 alerts on every active name;
    auto-drop if a second restructuring becomes visible (NT filings,
    going-concern language, RX advisor hires).

The point of the system is not to find every restructuring — it's to make
the alignment question (*rescue for whom?*) the first thing you answer,
the seat-selection question (*which tranche?*) the second, and the timing
question (*which window?*) the third — before any narrative gets in the
way.
