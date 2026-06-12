# Capital-Structure Screening for Long Conviction

A practical playbook for finding the next multibagger inside ugly recaps.
Five hard problems to solve, in order:

1. **Discovery.** Surface the right deals out of the thousand
   restructurings, rights issues, exchange offers, and UCC filings that hit
   the wires every week.
2. **Alignment.** Tell — fast — whether the deal rescues *legacy common* or
   is a creditor takeover dressed up as one.
3. **Asymmetry.** Confirm the setup is priced like the Tenneco/Munger
   condition — triangulate pro-forma cap structure & through-cycle
   valuation, cap-stack game theory, and insider / institutional revealed
   preference. All three must say "yes."
4. **Seat selection.** Identify the right tranche (old common, rights,
   nil-paid rights, fulcrum debt, post-emergence common, warrants, CVRs)
   before sizing the trade.
5. **Timing.** Act at the right stage of the deal calendar — most of the
   alpha lives in narrow windows (nil-paid rights, rump auction,
   when-issued common).

---

## 1. Discovery pipeline (RSS + databases + form filters + keyword regex)

The goal is a daily inbox of 5–20 candidates pulled automatically from
primary sources, not a weekly trawl through PitchBook or Bloomberg
headlines. The pipeline runs eleven independent data streams:

1. **Primary regulatory filings** by jurisdiction (§1.1)
2. **Form-type / item-code** filters (§1.2)
3. **Bond, credit & distressed** feeds — trustee notices, TRACE, paid services (§1.3)
4. **UCC, lien & collateral** aggregators worldwide (§1.4)
5. **Insider & institutional** positioning — Form 4, 13D/G/F, SEDI, PDMR, SAST (§1.5)
6. **Macro & cycle** data — HY OAS, default rates, loan-price indices (§1.6)
7. **Keyword regex** tiered Tier-S / Tier-A / Tier-B / Red-flag (§1.7)
8. **EDGAR full-text** programmatic recipe (§1.8)
9. **Secondary commentary** — paid distress press, sell-side desks, short reports (§1.9)
10. **Data architecture** — joining the feeds into one ticker-keyed table (§1.10)
11. **Triage cadence** — daily / weekly / monthly disciplines (§1.11)

### 1.1 Primary regulatory feeds — ~40 jurisdictions

Free RSS / Atom / JSON wherever available. Where no RSS exists, scrape the
issuer-search HTML on a saved query basis.

**Americas**

| Country | Regulator / exchange | Feed | What to pull |
|---|---|---|---|
| US | SEC EDGAR — current | `sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom` | 8-K, 6-K, S-3/424B, 13D/G, T-3, 15-12B, NT-10 |
| US | SEC EDGAR — full-text | `efts.sec.gov/LATEST/search-index` (JSON) | Keyword + form-type slice |
| US | SEC EDGAR — Form D | Reg D private placement filings (Atom) | Anchor / strategic-investor disclosure |
| US | NYSE listing-qualifications notices | `nyse.com/regulation/notices` | Delisting threats, going-concern letters |
| US | Nasdaq listing-qualifications | `listingcenter.nasdaq.com` notices | Compliance / delisting |
| Canada | SEDAR+ | Per-issuer Atom on `sedarplus.ca` | Material change reports, rights offering circulars |
| Canada | TSX Venture / CSE bulletins | Exchange RSS | Cease-trade orders, halts |
| Brazil | CVM | `cvm.gov.br/dados-publicos` | Material facts (FRE/IPE) |
| Brazil | B3 | `b3.com.br` corporate actions | Capital raises, debenture issues |
| Mexico | CNBV | `cnbv.gob.mx` | Eventos relevantes |
| Mexico | BMV | `bmv.com.mx` | Corporate disclosures |
| Argentina | CNV | `cnv.gov.ar/sitioweb/hechosrelevantes` | Hechos relevantes |
| Chile | CMF | `cmfchile.cl` | Hechos esenciales |
| Peru | SMV | `smv.gob.pe` | Hechos de importancia |
| Colombia | SuperFinanciera | `superfinanciera.gov.co` | Información relevante |

**Europe**

| Country | Regulator / exchange | Feed | What to pull |
|---|---|---|---|
| UK | LSE RNS | `londonstockexchange.com/news?tab=news-explorer` (RSS) | Rights, scheme of arrangement, Pt 26A restructuring plan |
| UK | FCA NSM | `data.fca.org.uk/artefacts/NSM/` | National Storage Mechanism filings |
| UK | Companies House | `find-and-update.company-information.service.gov.uk` | Charges, PSC changes, accounts |
| UK | Insolvency Service | `gov.uk/government/organisations/insolvency-service` | Administration / liquidation notices |
| Ireland | Euronext Dublin + ISE | `euronext.com/en/markets/dublin` | Capital raises, scheme circulars |
| France | AMF + Euronext Paris | `amf-france.org` info financière | Prospectus + ad-hoc |
| Germany | BaFin + Bundesanzeiger + Frankfurt | `bundesanzeiger.de` | Ad-hoc, StaRUG notices |
| Netherlands | AFM + Euronext Amsterdam | `afm.nl` register | WHOA notices, prospectuses |
| Switzerland | FINMA + SIX | `six-exchange-regulation.com` | Ad-hoc, capital raises |
| Italy | Consob + Borsa Italiana | `consob.it` + `borsaitaliana.it` | Comunicati / OPA |
| Spain | CNMV + BME | `cnmv.es/portal/HR/` | Hechos relevantes |
| Sweden | FI + Nasdaq Stockholm | `fi.se` + `nasdaqomxnordic.com` | Prospectuses, A&E announcements |
| Norway | Oslo Børs + FT | `newsweb.oslobors.no` | Børsmeldinger |
| Denmark | Finanstilsynet + Nasdaq Copenhagen | `finanstilsynet.dk` | Selskabsmeddelelser |
| Finland | FIN-FSA + Nasdaq Helsinki | `finanssivalvonta.fi` | Pörssitiedotteet |
| Austria | FMA + Wiener Börse | `wienerborse.at` | Ad-hoc |
| Belgium | FSMA + Euronext Brussels | `fsma.be` | Prospectuses |
| Poland | KNF + GPW | `gpw.pl` ESPI/EBI | Raporty bieżące |

**Middle East & Africa**

| Country | Regulator / exchange | Feed | What to pull |
|---|---|---|---|
| Israel | TASE / MAYA | `maya.tase.co.il` | Material events |
| UAE | ADX + DFM | `adx.ae` + `dfm.ae` | Disclosures |
| Saudi | Tadawul | `saudiexchange.sa` | Tadawul announcements |
| Qatar | QSE | `qe.com.qa` | Disclosures |
| Turkey | KAP | `kap.org.tr` (multilingual) | Public Disclosure Platform |
| South Africa | JSE SENS | `jse.co.za/sens` | Stock Exchange News Service |
| Egypt | EGX + FRA | `egx.com.eg` | Disclosures |
| Nigeria | NGX | `ngxgroup.com` | Corporate announcements |

**Asia-Pacific**

| Country | Regulator / exchange | Feed | What to pull |
|---|---|---|---|
| Japan | EDINET (FSA) | `disclosure.edinet-fsa.go.jp` | Securities filings |
| Japan | TDnet (TSE) | `tse.or.jp/announcement` | Timely disclosure |
| Korea | DART (FSS) | `dart.fss.or.kr` | Major reports, capital raises |
| Hong Kong | HKEXnews | `hkexnews.hk` | Listed-issuer disclosures |
| China | SSE + SZSE | `sse.com.cn` + `szse.cn` | Periodic + interim (CN/EN) |
| Taiwan | MOPS | `mops.twse.com.tw` | Material info |
| Singapore | SGXNet | `sgx.com/securities/company-announcements` | Per-issuer RSS |
| Malaysia | Bursa Malaysia | `bursamalaysia.com/market_information/announcements` | Listed-issuer announcements |
| Thailand | SET | `set.or.th/en/company/listed/announcements` | Listed-company news |
| Indonesia | IDX | `idx.co.id` | Pengumuman emiten |
| Philippines | PSE EDGE | `edge.pse.com.ph` | Disclosures |
| Vietnam | HOSE + HNX | `hsx.vn` + `hnx.vn` | Corporate disclosures |
| Australia | ASX + ASIC | `asx.com.au/asx/v2/statistics/announcements.do?timeframe=D` + ASIC company extracts | Capital raises, VA notices |
| New Zealand | NZX | `nzx.com/announcements` | Announcements |
| India | BSE + NSE + SEBI | `bseindia.com/corporates/ann.html`, NSE corporate API, `sebi.gov.in` | Rights, QIP, FPO, takeover |
| Pakistan | PSX + SECP | `psx.com.pk` + `secp.gov.pk` | Material info |
| Sri Lanka | CSE | `cse.lk/pages/announcement` | Disclosures |
| Bangladesh | DSE | `dsebd.org` | Price-sensitive info |

**Court & insolvency dockets**

| Country | Source | Feed |
|---|---|---|
| US | PACER + CourtListener (RECAP) | RSS per case + bankruptcy keyword alerts |
| US | Stretto, Kroll, Epiq, Prime Clerk, BMC Group | Public docket pages per case |
| UK | Insolvency Service notices | Gazette + Insolvency Service site |
| UK | BAILII case feeds | `bailii.org/recent-decisions.html` |
| Canada | Provincial court registries + Insolvency Insider | Per-court HTML scrape |
| Australia | Federal Court eFiling + state Supreme Courts | Daily-judgments page |
| Singapore | SUPCT eLitigation | Daily-cause-list HTML |
| Hong Kong | Judiciary Daily Cause List | `judiciary.hk` |
| Germany | InsO register (Bundesanzeiger) | Insolvenzbekanntmachungen |
| Netherlands | Centraal Insolventieregister | `insolventies.rechtspraak.nl` |

### 1.2 Form-type & item-code filters (cross-jurisdictional)

| Filter | US equivalent | UK | EU (Transparency / MAR) | Canada | Australia | India |
|---|---|---|---|---|---|---|
| Material agreement | 8-K Item 1.01 | RNS "Notification of major holdings" + LR 13 | MAR Art. 17 ad-hoc | Material change report | ASX 3A.1 / 3A.2 | SEBI LODR Reg 30 |
| Bankruptcy / insolvency | 8-K Item 1.03 | LSE Notice of Liquidation | Per-country code | Filing under CCAA / BIA | ASX VA notice / Appendix 3X | NCLT order |
| Debt obligation | 8-K Item 2.03 / 2.04 | RNS debt issuance | MAR ad-hoc | Material change report | ASX 3D | LODR Reg 30 |
| Unregistered equity | 8-K Item 3.02 / 3.03 | RNS placing / open offer | Prospectus Reg | Form 45-106F1 | ASX placement notice | Preferential allotment |
| Vote results | 8-K Item 5.07 | RNS results of GM | Per-country | Form 51-102 | ASX 3G | LODR Reg 44 |
| FPI window | 6-K | n/a | n/a | n/a | n/a | n/a |
| Anchor disclosure | SC 13D/G + amendments | TR-1 substantial shareholder | Transparency Directive | Early Warning Report | Substantial holder notice 5%+ | SAST Reg 29 |
| New equity pricing | S-3 / 424B5 | Prospectus + final terms | EU Prospectus | Short-form prospectus | ASX cleansing notice | DRHP / addendum |
| New indenture | T-3 | Trust deed RNS | Per-country | Trust indenture | n/a | Information memorandum |
| Restructuring vote | DEF 14A | Circular under LR | Per-country | Mgmt info circular | Scheme booklet | NCLT scheme circular |
| Late filer | NT-10 | RNS "Delay in publication" | Per-country | Cease trade order | Suspension notice | LODR Reg 33 non-compliance |
| Insider transaction | Form 4 | RNS PDMR notification | MAR Art. 19 | SEDI | ASX Appendix 3Y | SEBI insider Reg 7(2) |

### 1.3 Bond, credit & distressed feeds

**Free**

- **FINRA TRACE** (US corporate bonds) — `finra.org/finra-data/fixed-income`
- **MSRB EMMA** (US municipal) — `emma.msrb.org`
- **DTC LENS notices** — `dtcc.com/notices/lens-notices` (corporate-action and default notices)
- **Euroclear / Clearstream** public notices — corporate-action announcements
- **SEC EDGAR ABS-15G** — securitization disclosures
- **Bond-trustee public-notice pages** (default and consent solicitations):
  - BNY Mellon Corporate Trust — `bnymellon.com/us/en/who-we-are/corporate-trust.html`
  - U.S. Bank Global Corporate Trust — `usbank.com/corporate-and-commercial-banking/global-corporate-trust-services.html`
  - Deutsche Bank Trust Company Americas
  - Citibank N.A. (Agency & Trust)
  - Computershare Corporate Trust
  - Wilmington Trust — `wilmingtontrust.com`
  - GLAS Trustees (London) — `glas.agency`

**Paid (premium distress)**

- **Octus** (formerly Reorg Research) — `octus.com`
- **9fin** — `9fin.com`
- **Debtwire / Mergermarket** — `iongroup.com/markets/debtwire/`
- **CreditSights**
- **S&P LCD News** (LSTA loan market) — `lcdcomps.com`
- **Xtract Research** (covenant database)
- **BondCliQ** (intraday corp-bond pricing)
- **MarketAxess** (bond liquidity / pricing)
- **Bloomberg ALLQ** + Bloomberg Terminal `NSE BANKRUPTCY` / `NSE RECAPITALIZATION` / `NSE TENDER OFFER`

### 1.4 UCC, lien & collateral aggregators (worldwide)

**United States — state-by-state**

- Per-state Secretary of State UCC search (DE, NY, CA, TX, IL most common)
- **UCCDirect** — `uccdirect.com`
- **Wolters Kluwer Lien Solutions** — `liensolutions.com`
- **CSC Global** — `cscglobal.com`
- **Capitol Services** — `capitolservices.com`
- **Parasec** — `parasec.com`
- **iLien** (CT Corp / Wolters Kluwer)

**Outside the US**

| Country | Registry | Feed |
|---|---|---|
| UK | Companies House — charges | `find-and-update.company-information.service.gov.uk` |
| Canada | Provincial PPRs (Ontario, BC, Alberta, etc.) | Per-province search; commercial: TLOxp, Dye & Durham |
| Australia | ASIC PPSR | `ppsr.gov.au` |
| New Zealand | PPSR | `ppsr.govt.nz` |
| India | CERSAI + MCA charges | `cersai.org.in` + `mca.gov.in` |
| Mexico | RUG | `rug.gob.mx` |
| Brazil | Junta Comercial (state-level) | Per-state JUCESP, JUCERJA, etc. |
| Singapore | ACRA Bizfile | `bizfile.gov.sg` |
| Hong Kong | Companies Registry charges | `cr.gov.hk` |
| Germany | Schuldnerverzeichnis (debtor register) | `vollstreckungsportal.de` |
| France | Greffes des tribunaux de commerce — privilèges | `infogreffe.fr` |
| Netherlands | Kadaster + Kamer van Koophandel | `kvk.nl` |

UCC/lien changes around a Tier-S filing date are the single highest-value
post-deal verification signal. A clean Bucket A deal *should* show
terminations of old liens on the same day or within 30 days.

### 1.5 Insider & institutional positioning feeds (revealed preference, triangulation Leg 3)

**Insider transactions**

| Country | Source | Feed |
|---|---|---|
| US | SEC EDGAR Form 4 / 4-A | `sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<CIK>&type=4&output=atom` |
| US | OpenInsider (free aggregator) | `openinsider.com` |
| US | SECForm4.com / InsiderSentiment.com / WhaleWisdom | Free + paid |
| UK | PDMR (Persons Discharging Managerial Responsibility) | RNS notifications per ticker |
| UK | Companies House confirmation statements + PSC | `find-and-update.company-information.service.gov.uk` |
| Canada | SEDI | `sedi.ca` — daily download |
| Canada | Canadian Insider | `canadianinsider.com` |
| Australia | ASX Appendix 3Y (change in director's interest) | ASX RSS per ticker |
| Australia | ASIC Form 605 | Substantial holder notices |
| India | BSE / NSE bulk + block deals | Daily HTML downloads |
| India | SEBI Reg 7(2) insider disclosures | BSE / NSE company pages |
| India | TrendlyneInsider, Tijori Finance | Aggregators |
| Japan | EDINET large-shareholding reports | `disclosure.edinet-fsa.go.jp` |
| Korea | DART executive shareholding | `dart.fss.or.kr` |
| Hong Kong | HKEX Disclosures of Interest | `sdinotice.hkex.com.hk` |
| Singapore | SGXNet directors' transactions | `sgx.com/securities/company-announcements` |
| EU | MAR Art. 19 manager transactions | Per-OAM hub |

**Institutional positioning**

| Source | What it shows | Feed |
|---|---|---|
| SEC 13F-HR (quarterly, 45-day lag) | US institutional holdings >$100m AUM | EDGAR Atom + WhaleWisdom |
| SEC 13D / 13G / 13G-A | 5%+ positions + activist intent | EDGAR Atom per CIK |
| SEC NPORT-P | Mutual-fund holdings | EDGAR Atom |
| Form ADV (RIA filings) | Adviser AUM + strategy changes | EDGAR |
| UK TR-1 | Substantial shareholder notifications | RNS per issuer |
| EU Transparency Directive | 5%+ shareholder notifications | Per-OAM hub |
| Canada Early Warning Reports | 10%+ shareholder | SEDAR+ |
| Australia substantial holder notices | 5%+ shareholder | ASX RSS |
| India SAST Reg 29 + 31 | Substantial Acquisition of Shares & Takeovers | BSE / NSE |
| WhaleWisdom | 13F aggregator with delta tracking | Paid web |
| FactSet Stock Surveillance / Ownership | Institutional ownership database | Paid |
| Refinitiv eMaxx | Bond-fund holdings database | Paid |
| Morningstar Direct / Lipper | Mutual fund holdings + flows | Paid |
| Ortex / S3 Partners | Short interest + borrow rates | Paid |
| FINRA short interest reports | Bi-weekly US short interest | Free |

**Tracking watch-list for known recap-/value-fund 13F entries**

Maintain a list of CIKs / fund identifiers and watch each filing for new
positions in distressed names. Useful clusters:

- *Distressed credit & recap funds:* Oaktree, Apollo, Cerberus, Centerbridge,
  Silver Point, Anchorage, GoldenTree, Mudrick, Brigade, King Street,
  Marathon, Sound Point, Owl Creek, Solus, Strategic Value Partners
- *Value funds known for restructuring exposure:* Baupost, Markel, Akre,
  Ariel, FPA, Pzena, Yacktman, Longleaf, Wedgewood, Causeway
- *Activist / anchor:* ValueAct, Trian, Elliott, Starboard, Engine No. 1
- *Sovereign / strategic:* GIC, Temasek, ADIA, PIF, NBIM, CDP, Bpifrance

### 1.6 Macro & cycle data feeds

| Indicator | Source | Feed / series ID |
|---|---|---|
| HY OAS (ICE BofA US HY index) | FRED | `BAMLH0A0HYM2` |
| HY effective yield | FRED | `BAMLH0A0HYM2EY` |
| BBB OAS | FRED | `BAMLC0A4CBBB` |
| CCC OAS | FRED | `BAMLH0A3HYC` |
| HY default rate (Moody's) | FRED + Moody's Analytics | `BAMLH0A3HYCEY` proxy |
| Investment-grade vs HY spread | FRED arithmetic | `BAMLH0A0HYM2 - BAMLC0A1CAAA` |
| LSTA US Leveraged Loan price index | S&P/LCD | `lcdcomps.com` (paid) |
| ICE BofA HY rebound index | ICE Data Services | Paid |
| EPFR HY ETF flows | EPFR | Paid |
| ICI weekly mutual fund flows | ICI | Free |
| Moody's Default & Recovery DB | Moody's | Paid |
| S&P Default & Rating Transitions | S&P Global | Paid |
| Trepp CRE delinquency | Trepp | Paid |
| RCA commercial real estate | RCA | Paid |

Read the macro filter (§7) against these series to size the watchlist
appropriately: candidate density should scale with HY OAS / default-rate
backdrop, not narrative.

### 1.7 Keyword regex (run against feed titles + first page of filing)

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

REVEALED_PREF = r"\b(director (purchase|acquisition)|" \
                r"promoter (subscribed|purchased)|" \
                r"insider (buy|purchase)|" \
                r"13D filing|substantial shareholder)\b"
```

`RED_FLAGS` matched *before* a `TIER_S` event is the highest-value early-
warning lane — 3–9 month leading indicators of the deal that matters.

`REVEALED_PREF` matched *after* a `TIER_S` event within 30 days is the
Leg 3 confirmation signal for triangulation (§8.3).

### 1.8 Concrete EDGAR full-text recipe

EDGAR's full-text endpoint accepts JSON queries with form-type filters.
A starter daily script:

```python
import requests, datetime as dt

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
    "insider_buy":          '"director purchase" OR "Section 16 acquisition"',
}
FORMS = "8-K,6-K,S-1,S-3,424B5,T-3,SC 13D,SC 13G,DEF 14A,4"

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
announcements JSON, BSE/NSE announcements HTML, EDINET JSON, DART REST API.
Each issuer hit becomes a row in the triage queue with `tier`, `ticker`,
`form`, `accession`, `url`.

### 1.9 Secondary commentary feeds

- **Reuters** tag feeds — `/business/restructuring/`, `/markets/deals/`
- **FT Alphaville** RSS
- **Bloomberg Terminal** `NSE` codes (paid)
- **Petition** (Substack) — weekly distress digest
- **Distressed Hub** / **Reorg-Research** highlights
- **Octus / 9fin / Debtwire** headlines (paid trial APIs available)
- **Trustee / agent press release pages** — Kroll Restructuring Administration,
  Epiq, Stretto, Prime Clerk, DF King, Computershare
- **Sell-side credit research** — BAML High Yield Weekly, JPM Distressed
  Watch, Morgan Stanley HY, Goldman Distressed (Bloomberg / direct)
- **Specialty primary-market press** — GlobalCapital, IFR (International
  Financing Review), Euroweek
- **M&A / capital-markets newsflow** — DealReporter, Mergermarket capital
  markets, Mlex (regulatory)
- **Short-seller research** — Hindenburg, Citron, Spruce Point, Muddy
  Waters, Wolfpack, Bonitas, Iceberg, Viceroy (short reports frequently
  precede restructurings; Marc Cohodes is the canonical follow on Twitter/X)
- **Specialty newsletters** — Kuppy's Event Driven, Off Wall Street, MOI
  Global, ValueWalk

### 1.10 Data architecture (joining the feeds)

The pipeline outputs one ticker-keyed `candidates` table per day. Schema:

```
candidates(
    ticker, isin, cik_or_equivalent, jurisdiction, sector,
    last_tier_s_signal, last_red_flag, last_insider_buy,
    last_13d_change, last_ucc_event,
    pf_net_debt, ebitda_p25, ebitda_p50, ebitda_p75,
    fulcrum_tranche_price, listed_equity_mc,
    score_total, bucket, triangulation_legs,
    next_event_date,  -- record date / sub period / earnings
    state            -- watch | option | core | drop
)
```

Cross-feed joins to perform daily:

1. **Ticker ↔ CIK / ISIN / LEI** map. Use OpenFIGI for ISIN ↔ FIGI, EDGAR
   tickers.json, LSE SEDOL lookup.
2. **Issuer ↔ trustee / debt-tranche** map. Maintain a hand-curated
   dictionary of each watchlist issuer's outstanding tranches + their
   trustee + their CUSIP / ISIN. New trustee notices auto-attach.
3. **Issuer ↔ UCC debtor name** map. Legal entity name (per Secretary of
   State) often differs from listed-issuer name. Build aliases.
4. **Insider name ↔ issuer** map. Form 4 filers come keyed by CIK of the
   reporting person, not the issuer; join via the `subject CIK` field.
5. **Fund manager ↔ position delta** map. 13F-HR quarterly delta vs prior
   filing per ticker → flag on watchlist names.

Output the joined `candidates` table to Postgres / SQLite / DuckDB nightly
for triage. Snapshot per day to track score drift through the deal cycle.

### 1.11 Triage cadence

- **Daily (15 min).** Sort overnight feed by tier; tag candidates; queue
  filings for deep read. Review Form 4 / PDMR / SEDI hits against the
  watchlist (Leg 3 signal).
- **Weekly (60 min).** Run watchlist UCC / lien-registry search; reconcile
  against bond-trustee notices; refresh maturity wall and triangulation
  read for every active name; check fulcrum-debt price moves.
- **Quarterly (post-13F due date).** Reconcile institutional positioning
  against watchlist — new entries by recap-fund cluster, exits by
  long-only value managers.
- **Monthly.** Prune candidates that have not progressed (no Item 1.01, no
  anchor backstop disclosed, no maturity extension filed). Re-score
  macro filter; resize watchlist if HY OAS regime shifted.

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
| 9 | **Alignment-gap ratio** = anchor entry price ÷ current market | ≥2.0× / 1.2–2.0× / <1.2× |
| 9b | Anchor's cost basis premium to recap price | <0% / 0–25% / >25% |
| 9c | **Strategic premium-to-VWAP placement** (anchor pays *above* 30-day VWAP) | ≥10% premium / 0–10% / discount |
| 9d | **Implied liquidation recovery** (per plan or scheme disclosure) | ≥30% / 10–30% / <10% |
| 11 | Consensus 24-month EBITDA CAGR | ≥30% / 10–30% / <10% |
| 13 | Pro-forma Altman Z-score | >2.9 / 1.8–2.9 / <1.8 |
| 14 | Liquidity ÷ quarterly opex | >6 / 2–6 / <2 |

**Dimension 9c — premium-to-VWAP placement.** A separate, *inverse-shaped*
signal to 9 (alignment-gap). When a strategic willingly pays *above* market
in a bear cycle for the underlying asset, the resource is being repriced
versus EV/resource peers. The cleanest 2024–2026 example is **Patriot
Battery Metals (PMET)** where VW PowerCo subscribed C$69m at **C$4.42 — a
65% premium to 30-day VWAP and 35% to 90-day VWAP** for 9.9% plus a 10-year
binding 100ktpa SC5.5 offtake. Worldline's anchors paying €2.75 at a 10%
VWAP premium is the same shape at a much larger scale. This is a stronger
signal than a deep-discount rights issue at the same EV, because the
strategic could have demanded market price and chose not to.

**Dimension 9d — liquidation recovery floor.** Part 26A / WHOA / StaRUG /
recovery-judicial schemes disclose implied liquidation recoveries to
unsecured creditors. The Chinese property cascade ran at **4–10% implied
recovery** (Kaisa, Country Garden, Sunac, CIFI) — meaning surviving
equity is a *genuine residual claim*, not merely diluted. Below 10% the
listed-equity option is structurally option-shaped (binary outcomes); at
10–30% the recap looks more like a true rescue; above 30% the deal is
closer to a routine refinancing.

**The alignment-gap ratio is the highest-information single metric.** When
a sovereign or strategic anchor pays a reserved-capital-increase price
multiple times the parallel rights price (and multiple times current
market), they have stamped a hard valuation floor against which the
listed equity is visibly mispriced.

Worked examples:

- **Eutelsat (Nov–Dec 2025):** anchors (French State, Bharti, UK Gov,
  CMA CGM) paid €4.00/share in the reserved increase; parallel rights
  cleared at €1.35; stock now near rights. **Gap = 4.00 / ~1.40 ≈ 2.9×.**
- **Worldline (Mar 2026):** anchors (Bpifrance, Crédit Agricole, BNP)
  paid €2.75 (a 10% premium to 30-day VWAP); parallel rights cleared at
  €0.202; stock ~€0.40. **Gap = 2.75 / 0.40 ≈ 6.9×.**
- **Star Entertainment (Jun 2025):** Bally's + Mathieson convertible
  strike A$0.08; stock A$0.10–0.13. **Gap = 0.08 / 0.12 ≈ 0.67×** — no
  alignment gap, anchor accepted current market.
- **Calfrac (per the Tenneco worked example):** director rights price ≈
  current market. **Gap ≈ 1.0×** — alignment is in the act of
  participating, not the price gap.

A high alignment gap (≥2×) does *not* by itself guarantee upside — it
must combine with operational catalyst (Condition 7, §2.2) and a
non-creditor-controlled cap stack. But it is the single hardest signal
that *informed parties think today's price is wrong*.

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
   or above the recap price?
   NO  → no alignment; pass
   YES → continue
5. Alignment-gap ratio ≥ 2× (anchor entry / current market)?
   NO  → option-sized only
   YES → strong asymmetry signal; continue
6. Is the operating catalyst (Condition 7) identifiable and dated within
   24 months — i.e. is there a visible inflection that will force the
   market to re-rate from "rescue" pricing to "recovery" pricing?
   NO  → balance-sheet repair without operating fix; pass (Provident /
         Spirit / Meyer Burger risk)
   YES → core position
```

**The Condition-7 gate is what separates Tier 1 from Tier 2.** A clean
recap with no operational catalyst on the horizon is a *better* equity
than before the deal, but not yet a multibagger setup. The investable
opportunity sits in the time gap between *balance-sheet repair done* and
*operational inflection visible* — exactly the structural mispricing
that defined Rolls-Royce 2020, ArcelorMittal 2016, and 3i 2009 in their
respective cycles, and Eutelsat / Worldline / Vodafone Idea / Sunac in
the current vintage.

Prior-cycle textbook winners have already played through Condition 7 and
re-rated past the entry: Greek banks, Hanwha Ocean, Thai Airways,
Patanjali Foods, Saipem, Banca Monte dei Paschi. These belong on the
*completed arc* list, not the live shortlist.

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
- **Excessive new-money creditor IRR (>50%, court-reversal risk).** UK
  Court of Appeal set aside the Petrofac Part 26A sanction on 1 Jul 2025
  on the basis that new-money creditor IRRs of ~211% were "disproportionate
  value transfer." Plans that look investable on paper can be unwound on
  appeal if new-money economics are too rich. Read the scheme document for
  the new-money IRR; if it materially exceeds peer DIP/exit financing
  yields, factor reversal risk.
- **Insider net seller during the restructuring.** Founders or promoters
  *selling* listed equity during the recap window (Bui Thanh Nhon family
  selling NVL shares to fund the Novaland restructuring; Cazoo founders
  selling pre-rights) is alignment in reverse.
- **Implied liquidation recovery <10% with no operational catalyst.**
  When the scheme math implies the equity is a tail-only option but no
  Condition 7 inflection is dated, you have a lottery ticket, not an
  asymmetric trade.
- **State backstop revoked or made conditional.** Vanke's Nov 2025
  Shenzhen Metro collateral demand and onshore-bond extension request
  signal that previously-extended state support has become conditional —
  a previously-met scorecard dimension can turn 0 over a single
  announcement.
- **Second restructuring filed within 12 months of emergence.** Spirit
  Airlines (emerged 12 Mar 2025; refiled 29 Aug 2025; ceased operations
  May 2026) is the canonical case — when a name re-files inside a year,
  the operational franchise is impaired, not just the balance sheet.

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

### 3.1 Archetype taxonomy (orthogonal to Bucket A/B/C)

The **Bucket** (§8) answers *which seat captures the upside*. The
**Archetype** (this section) answers *what kind of deal mechanic produced
it*. Both axes are needed: archetype tells you which historical playbook
applies; bucket tells you which security to buy.

| Code | Archetype | Mechanic | Historical examples | Current vintage |
|---|---|---|---|---|
| **A1** | Sovereign-strategic dual-tier raise | Reserved capital increase to anchors at a premium price *plus* parallel rights at deep discount. Creates a hard valuation floor multiples above current market | Lufthansa 2020, ING 2009 | **Eutelsat, Worldline, Hawaiian Electric, Star, Synlait, Americanas, Light SA** |
| **A2** | Sovereign industrial-policy anchor | Government provides price floor + multi-year offtake + sub-commercial financing (DoD, DoE, EIB, Canada Enterprise Emergency Funding Corp) creating hard downside protection on the underlying commodity. Not an equity injection per se — the anchor is the *floor* | n/a (this is a 2024–2026 vintage innovation) | **MP Materials (DoD $110/kg NdPr floor + offtake), Lithium Americas ($2.26bn 0%-spread 24y DOE ATVM), Algoma Steel (CEEFC + warrants), Lynas (likely next), Vulcan Energy (EIB)** |
| **B** | Convertible / strategic-instrument backed | Convertible notes (often with capped calls), warrants, or convertible loan stock with strategic anchor; equity participates via conversion economics | Nvidia 2013, Sirius XM 2009 | **Coinbase, Sibanye-Stillwater, Borr Drilling, Hycroft, Calumet, Patriot Battery (VW PowerCo 65% premium)** |
| **C** | Out-of-court liability management | Bond exchange / consent solicitation pushing maturities; legacy equity untouched but creditor classes converted | Carvana 2023, Lloyds 2009 | **Lumen, iHeartMedia, Aston Martin, Hertz, WW International, Sigma Lithium** |
| **D** | Strategic customer / parent recap | Capital injected by an industrial partner with deep operational alignment (customer, parent, supplier) | Daimler / Mercedes-Benz in 2009 | **Synlait (Bright Dairy + a2 Milk), NIO (Hefei 2020)** |
| **E** | National bankruptcy framework (court-supervised survival) | PN17 (Malaysia), CCAA (Canada), recovery judicial (Brazil), StaRUG (Germany), Thai rehabilitation, French sauvegarde accélérée — sovereign procedure that preserves listed common while restructuring debt | GM 2009 (failed for legacy), Drake & Scull 2024 | **Capital A, Drake & Scull, Light SA, Americanas, Sapura, Thai Airways, Aeromexico, Garuda, Solocal, emeis, Casino, Pierre & Vacances** |
| **F** | Post-bankruptcy / spin orphan / MCB cascade | Ch.11 emergence with negotiated legacy retention; or sponsor-backed spin off; or strategic anchor receives material new equity; or Chinese property MCB cascade where founder takes material MCB alongside creditors | Charter 2009, Valaris 2021, Core Scientific 2024 | **Wolfspeed (Renesas 38.7%), Sunac (founder 23% MCBs), Sino-Ocean (state insurers 53.8%), Kaisa (Kwok + 6yr lock), CIFI (Lin family), Shimao (Hui family), Country Garden, Sunrise, Embracer/Fellowship, Endo/Mallinckrodt, Japan Display, GOL, Vroom, Diebold Nixdorf** |
| **G** | Regulator-forced sector recap | Regulatory mandate (capital floor, AGR settlement, MREL, central-bank stress test) drives recapitalisation across an entire sector | Greek banks 2010s, BoI 2011, Yes Bank 2020 | **Vodafone Idea (GoI 49%), Metro Bank (MREL + Gilinski), Nigerian banks (CBN ₦500bn floor), Attica/Crediabank** |
| **H** | Governance reset / state exit | The catalyst is a change in who governs: strategic privatization (H1), regulatory-forced float (H2), state-exit overhang removal (H3), mandated value-up regime (H4), regulator-forced board reset (H5), parent-child unwind (H6). The discount being closed is a *governance* discount, not a solvency discount. See `psu_governance.md` for the full module, scorecard dims 15–19, and feeds | NatWest state exit 2025, HFSF Greek exits, Serco 2015 reset, Yes Bank board reset (H5+G) | **IDBI Bank (H1 — live reserve-cut decision), Indian PSB MPS basket (H2 — Aug 1 2026 deadline), ABN AMRO / Permanent TSB (H3), Korea value-up tax-penalty laggards + Japan parent-child takeouts (H4/H6)** |

Same name can carry two codes (e.g., Eutelsat A + F because the recap is
also a partial reorganization). The most valuable signal is the *current
vintage column*: the May 2026 universe is dominated by Archetypes A, F,
G — French sovereign-strategic playbook (A), Chinese property post-RX
(F), and emerging-market regulatory recaps (G).

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

## 8. Triangulation: PF cap structure × game theory × revealed preference

The scorecard tells you a deal is *well-aligned*. Triangulation tells you
the deal is also *asymmetrically priced* — the Tenneco–Munger condition.
Three independent reads; all three must say "yes" for a core position. The
discriminating power comes from requiring **independence** between legs —
a single high-conviction signal in one leg with silence in the other two
is not a setup, it's confirmation bias.

### 8.1 Leg 1 — Pro-forma cap structure & through-cycle valuation

Build the post-deal cap stack and value it three ways. For cyclicals,
percentile-based EBITDA is more honest than trailing EBITDA — peers earn
peak when the market pays peak.

```
Bear EBITDA  = 25th percentile of trailing 10-year EBITDA
Base EBITDA  = median of trailing 10-year EBITDA
Bull EBITDA  = 75th percentile of trailing 10-year EBITDA

For each scenario:
  EV         = EBITDA × peer-cohort multiple at that cycle point
  Equity Val = EV − PF net debt − minorities + surplus cash
  Fair price = Equity Val ÷ PF diluted share count
```

Track the EBITDA percentile and the multiple percentile separately so you
don't double-count optimism (e.g., bull-case EBITDA × peak multiple is a
14-bagger fantasy in most cyclicals).

**Management input — adjusted.** Read the post-deal guidance, then:

- Haircut revenue by 20–30% (execution risk; Provident-style decay).
- Haircut margin by 200–400 bps (cost inflation, customer churn).
- Re-run: does the haircut number clear your bear-case? If not, the deal
  needs cycle *recovery* to clear management's own plan — you've now
  identified the operating risk explicitly.

**The asymmetric condition.** The setup is Tenneco-grade when:

- Current price ≈ bear-case fair value (downside ≈ 0–30%)
- Base-case fair value ≈ 2–3× current
- Bull-case fair value ≈ 5–10× current
- The catalyst from scorecard dimension #11 is identifiable and dated

This is the Tenneco math literally: at $1.50–2.00 the equity was at bear-
case fair value; at $15 it was at base-case fair value; the cycle did the
rest. Munger's edge was *not* timing — it was buying when bear ≈ current.

### 8.2 Leg 2 — Game-theoretic read of the cap stack

Each tranche has a rational want. Identify the dominant strategy of each
before you score the deal — the structure of incentives often predicts
the outcome better than the headline mechanics.

| Tranche | Rational want | Sign of alignment with old common | Sign of misalignment |
|---|---|---|---|
| 1L secured (RCF / TL) | Par recovery, no equity (don't want operating risk) | Relationship bank extends maturity, tightens covenants | Distressed fund holding 1L with conversion option |
| 2L / fulcrum | Equity if recovery <100% | Pushes for *backstopped rights* (gets new equity via subscription) | Pushes for cramdown plan with full equitization |
| Unsec / sub | Litigation rights, MFN, warrants | Active UCC negotiating warrant package | Silent unsec (already written off) |
| Old equity | Survival; pro-rata participation | Pro-rata rights with anchor backstop at TERP | Loan-to-equity by control shareholder; PIPE alongside rights |
| Management | MIP + jobs | MIP strikes at recap price; CEO writes cheque | Cash retention bonuses only |
| Strategic / sovereign anchor | Long-term value, optional toehold | Buys primary common at market with no kicker | Asks for warrants + board seats + ROFR |

**Veto signals** (any one → likely Bucket B/C even if the deal looks Bucket A):

- DIP lender with conversion-to-equity option at plan value
- Activist creditor with public loan-to-own history leading the unsecured
  committee (Elliott, Apollo Hybrid Value, Cerberus distressed, Mudrick,
  Silver Point, Anchorage, GoldenTree in certain mandates)
- Issuer actively elects a cross-class-cramdown venue (UK Pt 26A, Dutch
  WHOA, German StaRUG) when an out-of-court path was available
- DIP financing from a non-relationship lender (signal of forced sale)
- "Stalking horse" auction process announced before plan

**Confirm signals** (any two → Bucket A increasingly likely):

- Existing relationship bank as lead arranger
- Long-term shareholder (PE family, founding family, sovereign, pension
  fund) as backstop
- Friendly creditor committee already in support
- No DIP needed (or DIP from existing lenders)
- Out-of-court exchange instead of plan

### 8.3 Leg 3 — Revealed preference (insider + institutional activity)

The cleanest signal of an asymmetric setup is *people with the most
information voting with their wallets*. Three streams to track.

**Insider buying (Form 4 / equivalent):**

- CEO / CFO / Chair open-market purchases at or near recap price
- Director purchases *during the subscription window* — clean signal because
  pre-deal trading was MNPI-restricted, so post-record-date buying is the
  first opportunity to express the view
- Promoter / controlling-family purchases (especially in EM contexts)
- Insider option exercises with hold (not exercise-and-sell)
- Section 16 buys above the rights price (above pro-rata-required level)

EDGAR feed: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<CIK>&type=4&output=atom`
LSE / ASX / NSE equivalents available per regulator.

**Institutional positioning (13D / 13G / 13F):**

- New 13D/G positions by long-term value investors (Markel, Akre, Baupost,
  Ariel, FPA, Pzena, Yacktman, Longleaf, Wedgewood)
- 13F new positions at the recap close by recap-focused funds (Oaktree,
  Apollo Hybrid Value, GoldenTree, Mudrick, Silver Point, Anchorage) —
  *strongest* signal for Bucket B trades, because these funds usually
  know the fulcrum seat
- Bond-fund position growth in the fulcrum tranche (TRACE / FINRA / NIC)
- Schedule 13G accumulation by quiet long-only managers
- Pension / sovereign first-time positions (LP letters, 13F-HR)

WhaleWisdom + EDGAR Atom for 13D/G/13F-HR changes; FINRA TRACE for bond
holdings; LSEG/Lipper for fund-level position changes.

**Compensation & repurchase signals (DEF 14A / 8-K Item 5.02):**

- MIP grants struck at recap price → alignment with new public shareholder
- Pre-existing management options now far underwater but *not* repriced →
  signals they expect recovery without a sweetener
- Repurchase authorization post-deal (rare; cleanest "management thinks
  equity is cheap" signal)
- Insider loans repaid to issuer post-deal (rare; very strong)

**Negative revealed preference (any one shifts to "pass"):**

- Insider selling immediately after lock-up
- Backstop investor sells rump shares within 90 days
- Sponsor or PE owner reduces stake post-close
- Management resigns or announces "personal reasons" departure
- MIP grants repriced lower within 12 months of the deal

### 8.4 Triangulation rule

| Legs voting "yes" | Action |
|---|---|
| 3 of 3 | Core position; this is the Tenneco / Munger condition |
| 2 of 3 | Option-sized; identify which leg is missing and the catalyst that would flip it |
| 1 of 3 | Watchlist; do not size |
| 0 or contradicting | Pass |

### 8.5 Applying triangulation to current names

| Name | Leg 1: PF/through-cycle asymmetry | Leg 2: Cap-stack game theory | Leg 3: Insider / insti revealed preference | Verdict |
|---|---|---|---|---|
| **Calfrac** | ✓ NA frac-cycle: bear ≈ current; base ≈ 2–3× | ✓ Director backstop = relationship anchor; no DIP needed | ✓ Directors put fresh cash in alongside rights | **3/3 — core (Tenneco-grade)** |
| **Exicom** | ✓ Promoter underwriting at deleveraging price | ✓ Promoter cheque ≈ alignment; no creditor wipe | ✓ Promoter took ₹120 cr of ₹259 cr | **3/3 — core** |
| **Petra** | ✓ Diamond cycle near trough; mid-cycle EV/EBITDA ≈ 4× equity | ~ Refinancing friendly; no named external anchor | ? Insider rights take-up but no aggressive open-market buys | **2/3 — option** |
| **Worldline** | ✓ Payments multiple 5–10× off peak; mid-cycle ~50% on multiple alone | ✓ French banks anchored = strategic alignment | ? Need confirmation of board / insider participation | **2/3 — option** |
| **Ørsted** | ~ Offshore-wind IRR repair plausible; multiple uncertain | ✓ State at 50.1% = sovereign anchor | ✓ State held pro-rata through entire raise | **2/3 — option** |
| **Eutelsat** | ~ LEO unit economics unproven | ✓ Sovereign + strategic anchors | ✓ Anchors participated pro-rata | **2/3 — option** |
| **Brait** | ✓ NAV discount triangulation | ~ Convert restructuring complicates game theory | ? Insider patterns less clear | **1–2 / 3 — watchlist** |
| **Fossil** | ~ Brand value uncertain through-cycle | ✓ Stapled-exchange preserves listed common | ? Need confirmation of insider activity post-deal | **1 / 3 — watchlist** |
| **Atos** | ✗ Creditors at 90.8% destroys PF math for old common | ✗ Cramdown jurisdiction used | ✗ No insider buying at recap price | **0 / 3 — pass** |

**Calfrac and Exicom are currently the cleanest triangulations** — the
two names that match the Tenneco / Munger / Goodman pattern of all three
legs lit at the same time. Worldline, Ørsted, Eutelsat, and Petra are
two-leg options where the missing leg is identifiable and watchable.

### 8.6 Screening for the next Tenneco

Run these intersections weekly to surface fresh three-leg candidates:

- **Form 4 buys ∩ Tier-S regex** — names where an insider Form 4
  purchase lands within 30 days of a Tier-S filing.
- **13D new-entry ∩ distressed pricing** — names where a known
  value/recap fund files a first-time 13D below 50% of 5-year high.
- **Director purchases through rights** — DEF 14A / 8-K disclosures of
  director take-up *above* pro-rata share.
- **Fulcrum-debt ∩ listed-equity discount** — fulcrum debt at 50–70 and
  listed equity at <10% of 5-year peak (the Tenneco-shaped chart).
- **Cyclical EBITDA-decile screen** — trailing EBITDA at the 10th–25th
  percentile of 10-year history; current EV / median-EBITDA <6×; a
  Tier-S signal in the last 90 days.

The intersection — Tier-S signal + insider buy + fulcrum distress +
cyclical EBITDA trough — is where the *next* Tenneco lives.

---

## 9. Case studies — grouped by mechanism

The deal mechanism dictates *which security captures the upside*. Bucket
determination precedes scoring: the scorecard tells you "is this a good
deal?", but the bucket tells you "which seat captures it?"

- **Bucket A — listed common is the trade.** Old common participates
  pro-rata at a defendable price. The listed share is the right instrument.
  Quality within the bucket varies; score separates winners (Goodman, 3i,
  Yes Bank) from losers (Provident, Atos).
- **Bucket B — anchor instrument is the trade.** Listed common may
  participate, but the real economics live with the anchor or fulcrum
  tranche. Trade only if you can access the anchor's paper (PIPE,
  oversubscribed ERO, distressed fulcrum debt, when-issued post-emergence
  common). If you can't buy what they bought, you can't play.
- **Bucket C — legacy cancelled; new common is a separate trade.** Old
  listed equity is wiped. The post-emergence common may multibag, but only
  plan participants get it at the plan price. The trade is the *new*
  security on day-one of trading or via fulcrum-debt allocation — never the
  legacy stub.

### Bucket A — Listed common is the trade

| Year | Case | Mechanism | S | Why it worked / didn't |
|---|---|---|---|---|
| 2009 | **3i Group (LSE)** | 9-for-7 rights at TERP −39.8%, ~£700m net | 22/28 | NAV/debt panic; pro-rata repair preserved IG access; almost a perfect template |
| 2009 | **Informa (LSE)** | 2-for-5 fully underwritten rights, ~£242m net | 21/28 | Quality info-media asset normalized balance sheet mid-panic |
| 2009 | **Taylor Wimpey (LSE)** | £533m raise + refi against ~£1.57bn debt | 18/28 | Housing-cycle template; land bank survived to the recovery |
| 2009 | **National Express (LSE)** | £360m fully underwritten rights vs ~£1.1bn debt | 15/28 | Transport concessions mispriced by covenant fear; largest shareholder *initially opposed* hurt dim. #9 |
| 2009 | **Goodman Group (ASX)** | 1-for-1 rights at A$0.40, CIC cornerstone | 21/28 | ~60x with divs by 2021; e-commerce/logistics secular catalyst |
| 2009 | **ING (Euronext)** | €7.5bn 6-for-7 rights at €4.24, TERP −37.3% | 20/28 | Bank recap removed Dutch-state-capital overhang and restored strategic freedom |
| 2009 | **Lloyds (LSE)** | Rights issue + LME exchange offers to avoid GAPS | 19/28 | The *combination* of fresh equity + debt exchange let it dodge a punitive state framework |
| 2011 | **Bank of Ireland (ISE/LSE)** | Rights + exchange offers + consent + contingent capital + outside investment | 17/28 | One of the great bank-recap-at-trough cases; partial Bucket B for outside-investor terms |
| 2013 | **Nvidia (Nasdaq)** | $1.3B 5-yr converts at 30% premium, 1% coupon, capped calls | 21/28 | "Dilution on our terms"; equity multibagged because conversion only triggered higher |
| 2014 | **Premier Foods (LSE)** | £353m rights as part of ~£1.1bn refi (new bonds + RCF) | 17/28 | Removed financing stranglehold so operating improvement could matter |
| 2015 | **Serco (LSE)** | ~£555m underwritten rights + refi; ~£450m to gross debt | 19/28 | Governance/contracting reset; brand impaired but customer contracts intact |
| 2018 | **Provident Financial (LSE)** | ~£330m fully-underwritten rescue rights | 8 (hindsight) | Headline rights clean; home-credit franchise decayed; canonical *rescue ≠ recovery* |
| 2020 | **Yes Bank (NSE)** | ~₹25,000 cr total (SBI-led rescue + FPO at floor ₹12) | 22/28 | Regulated rescue removed insolvency risk; common ran ~80x off FPO floor |
| 2024 | **Indian Bank (NSE)** | ₹5,000 cr equity + ₹7,000 cr debt | 20/28 | Bank recap; stock roughly doubled within a year |
| 2025 | **Petra Diamonds (LSE)** | £18.8m fully underwritten rights + maturity push to 2029/30 | 14/28 | Default cliff gone; awaits diamond price recovery |
| 2025 | **Coinbase (Nasdaq)** | $2B converts at ~30–35% premium, capped calls | 16/28 | Structure clean; no dated operating catalyst |
| 2025 | **Baxter (NYSE)** | Cash tender for 2026/2027 bonds, new unsecured to fund | 13/28 | Marginally equity-positive; not transformational |

### Bucket B — Anchor instrument is the trade

| Year | Case | Mechanism | Best seat | Why |
|---|---|---|---|---|
| Early 2000s | **Tenneco (NYSE)** | Operational restructure + debt paydown | Distressed 2L debt at ~$0.30–0.50 | Munger bought debt sub-par; got par + equity option. Equity ran ~10x; the *debt's* risk-adjusted IRR was higher. Listed equity was Bucket A but the alpha lived in the debt seat |
| 2020 | **NIO (NYSE)** | Hefei consortium injects RMB7bn into NIO China for 24.1% of the sub; NIO Inc retained 75.9% + RMB4.26bn cash | Listed common (and Hefei sub if accessible) | Public couldn't buy Hefei terms but the listed shares ran 20x+ once the deal restored liquidity at the exact EV-cycle inflection. Partial Bucket B because the anchor's terms were materially better |
| 2024 | **Core Scientific (Nasdaq, post-Ch.11)** | Confirmed plan with oversubscribed ERO; old holders kept ~60% via warrants + ERO subscription | ERO at the plan price; warrants if held through | Atypically friendly Ch.11 for old holders. Trade was being in the ERO at the offered price; AI/HPC datacenter optionality became visible after emergence |

### Bucket C — Legacy cancelled; new common is a separate trade

| Year | Case | Mechanism | Legacy outcome | New common (Bucket B-style trade) |
|---|---|---|---|---|
| 2009 | **Charter Communications (Ch.11)** | ~$8B debt cut + ~$1.6B underwritten rights as part of the plan | Cancelled | New common compounded ×100+ to mid-2010s — accessible only to plan participants and day-one secondary buyers |
| Early 2000s | **Hynix / SK Hynix (Korea)** | KRW 1.9tn debt-for-equity swap, 21:1 capital write-down, maturity extensions, asset sales; creditors ~67% | Heavily impaired | Cleaned-up memory franchise became one of the great Asia-tech compounders — the trade was the post-restructuring listed common, not the legacy stub |
| 2020 | **McDermott International** | Ch.11; ~$4.6bn of funded debt eliminated | Cancelled | MCDIF (new common) re-emerged as a leaner offshore-EPC name — a clean Bucket C → post-emergence trade |
| 2021 | **Valaris (NYSE)** | Ch.11; $7.1bn debt eliminated + $520m capital injection | Cancelled (token warrants to former holders) | New VAL traded on NYSE; offshore-drilling cycle drove material upside — Bucket C with optional Bucket B warrants for prior holders |
| 2025 | **Country Garden (HK)** | Controlling shareholder converted $1.14B of loans to equity at HK$0.60 | Massively diluted; control transferred | Equity functionally Bucket C for non-participating common; participants got token economics |
| 2025 | **Canopy Growth (Toronto)** | New $162m TL to 2031 + C$96m converts exchanged for C$55m new converts + C$10.5m cash + ~9.5m shares + 12.7m warrants | Heavily diluted | Creditors absorbed the upside; legacy common a thin option |
| 2025 | **Spirit Airlines (NYSE)** | Mar-2025 Ch.11 plan equitized ~$795m + $350m equity inj.; refiled Aug-2025 | Cancelled twice in <12m | Even the *new* post-March-2025 common returned to Ch.11 — the canonical "balance-sheet fix without operating fix" |

### Pattern recognition across the three buckets

- **Best Bucket A setups share:** pro-rata access, anchor cost basis at the
  recap price (Goodman/CIC; Yes Bank/SBI; Indian Bank/promoter), a clean
  post-deal cap stack, and an identifiable operating catalyst within 24
  months. Scores cluster 18–22.
- **Best Bucket B setups share:** either a fulcrum tranche trading at deep
  distress (Tenneco 2L; pre-petition unsec), or a Ch.11 plan with an
  oversubscribed ERO accessible at the plan price (Core Scientific). The
  trade requires *access* — if you can't buy what the anchor bought, you
  can't play.
- **Best Bucket C setups share:** large debt reduction (>50% of funded
  debt), a single consolidated cap stack post-emergence, and a cyclical or
  secular catalyst the legacy business model couldn't capture (offshore
  drilling for Valaris; memory cycle for Hynix; cable for Charter). The
  trade is always the *new* common — never legacy stub.

### Three meta-lessons

1. **Bucket determination precedes scoring.** A 22/28 Bucket A is buy-able
   on the listed common. A 22/28 Bucket B is only buy-able if you can
   access the anchor instrument. A 22/28 Bucket C means the *new common*
   is buy-able — the legacy listed equity is still zero.
2. **Seat selection happens *within* bucket.** Within Bucket A you may
   still prefer rights over common, or nil-paid rights over rights, or
   fulcrum debt over either. The bucket says "this name's listed equity
   is the trade"; seat selection says "now find the best instrument."
3. **Rescue ≠ recovery (Bucket A's main failure mode).** Provident, Meyer
   Burger, Spirit all show that a textbook Bucket A rescue can fail if
   dimensions #11 (operating catalyst) and #13 (second-restructuring
   risk) are weak. Treat those two as veto gates: 0 on either = pass,
   regardless of the financial dimensions.

---

## 10. Current analogues — grouped by bucket

Same names as before, but now organized by the bucket framework. Within
each bucket, ranked by score.

### Bucket A — Listed common is the trade

The cleanest current setups: pro-rata rights with insider/anchor support
or sub-par debt retirement at the listed-equity level.

| Rank | Situation | Mechanism | S | Key swing factor |
|---|---|---|---|---|
| A1 | **Calfrac (Canada, TSX)** | C$35m rights, director-backstopped + C$120m TL, 2L-note cleanup | 19/28 | NA frac-cycle margins; backstoppers' cost basis at recap = aligned |
| A2 | **Viaplay (Sweden, ST)** | SEK 4bn equity + SEK 2bn write-down + SEK 0.5bn debt-to-equity + SEK 14.6bn A&E | 18/28 | Nordic refocus producing durable EBIT |
| A3 | **Brait (South Africa, JSE)** | R1.5bn rights + bond extension to Dec 2027 + convert reset to R2.21 | 17/28 | Virgin Active monetization; NAV-discount close |
| A4 | **Worldline (France, EPA)** | ~€392m rights (121% subscribed) as final tranche of ~€500m raise; Bpifrance, Crédit Agricole, BNP, Crédit Mutuel anchored | 17/28 | Client retention; 2027 FCF credibility; ~97% drawdown from 2021 peak before raise |
| A5 | **Ørsted (Denmark, CSE)** | DKK60bn rights, 99.3% subscribed; Danish state held 50.1% | 16/28 | Offshore-wind IRR trough confirmed; no further write-downs |
| A5= | **Eutelsat (France, EPA)** | ~€670m fully underwritten rights at €1.35; sovereign + strategic anchors funding LEO pivot | 16/28 | LEO execution vs. Starlink; OneWeb integration |
| A6 | **Petra Diamonds (UK, LSE)** | £18.8m rights + RCF to Dec-29, notes to Mar-30 + cash-or-equity interest | 15/28 | Diamond price recovery |
| A7 | **SBB (Sweden, ST)** | 95% participation in bond exchange; €2.78bn debt retired below par | 15/28 | Property valuations stabilizing; continued sub-par retirement |
| A8 | **Fossil (US, OTC)** | "Stapled Exchange" — UK Pt 26A plan + $32.5m new money; legacy equity explicitly preserved | 14/28 | Brand/licensing cash flows; cost cuts |
| A9 | **ams-OSRAM (Austria/CH)** | €2.25bn package incl. ~€800m rights + senior unsec + asset-level financing | 14/28 | Auto/industrial cycle; whether new debt stack absorbs the upside |
| A10 | **Exicom (India, NSE)** | ~₹259 cr oversubscribed rights; promoter took ~₹120 cr; deleveraging use of proceeds | 13/28 | Tritium integration; EV charger margins |
| A11 | **OXE Marine (Sweden, ST)** | MSEK 78 rights + MSEK 155 debt-to-equity + EIB warrant swap; residual debt written off after 7 yrs | 11/28 | Product traction; liquidity tail |
| A12 | **Ebusco (Netherlands, AMS)** | €36m rights at €0.8209, 64.3% take-up; shareholder loans converted; Gotion in settlement | 10/28 | Production normalization; customer confidence |
| A12= | **mm2 Asia (Singapore, SGX)** | SGD15m private placement + SGD10m fully-underwritten rights | 10/28 | Post-pandemic media demand; no visible strategic anchor |
| A13 | **Ascot Resources (Canada, TSX/OTCID: AOTVF)** | C$14.87m rights at C$0.01 (~48.5% to insiders) + 50:1 consolidation + Premier Gold Mine restart | 9/28 | Dilution after consolidation/PP; secured-creditor control; mine restart capital |

**Bucket A low-quality / "false friend" tier** — listed common still trades
but pro-rata participation is the only way to retain economics; non-
participants effectively wiped. Pass by default unless catalyst is
exceptional.

- **Atos (EPA)** — €2.9bn debt equitization; creditors ~90.8%. S ≈ 4.
- **Varta (Germany, ETR)** — StaRUG with shareholder reconstitution. S ≈ 5.
- **Beyond Meat (Nasdaq)** — 2025 exchange could issue up to 326m new
  shares to retire >$800m debt. S ≈ 5.
- **Meyer Burger (Switzerland, SWX)** — CHF 200m 2024 rights didn't fix
  the business; subsequent bondholder talks confirm bridge-to-next-RX.
  S ≈ 4.

### Bucket B — Anchor instrument is the trade

Listed common participates but the real economics live elsewhere. Only
playable if you can access the anchor's paper.

| Rank | Situation | Mechanism | Best seat | Score on best seat |
|---|---|---|---|---|
| B1 | **Core Scientific (Nasdaq)** | Post-Ch.11 common already trading after oversubscribed ERO; old holders kept ~60% via warrants/ERO | Post-emergence common (CORZ) or warrants | 13/28 |
| B2 | **Intrum (Sweden, ST)** | Ch.11 + Swedish reorg; 10% discount on reinstated notes; new financing; capital-light pivot | Post-emergence common or reinstated notes | 13/28 |
| B3 | **Star Entertainment (Australia, ASX)** | A$300m rescue led by Bally's + Mathieson via convertible / sub debt; up to ~56% post-conversion | Bally's/Mathieson-aligned instrument (typically inaccessible) → so practically a *pass for public investors*; if listed common, position-size as tail option | 8/28 listed; ~16/28 anchor seat |

### Bucket C — Legacy cancelled; new common is a separate trade

Already-cancelled or about-to-be-cancelled legacy stub. Trade only the new
security; never the old line.

- **Spirit Airlines (US)** — Emerged March 2025; refiled August 2025. Even
  the *new* post-March-2025 common returned to Ch.11. S ≈ 3 on both
  vintages. Pass.
- **McDermott / MCDIF (US OTC)** — Post-Ch.11 (2020) common; offshore EPC
  cycle is the catalyst. Watch as a Bucket C → Bucket B-style trade if
  offshore capex recovers.
- **Country Garden (HK)** — Controlling-shareholder loan-to-equity at
  HK$0.60; control effectively transferred. Practically Bucket C for any
  non-participating common. S ≈ 4.
- **Canopy Growth (Toronto)** — Heavily diluted; creditors absorbed the
  upside. Functionally Bucket B/C hybrid; pass for legacy listed equity.
  S ≈ 7.

### Shortlist by archetype (now bucket-tagged)

- **Bucket A · Pro-rata rights with insider/anchor backstop:** Calfrac,
  Brait, Petra, Exicom.
- **Bucket A · Discounted-debt-retirement / NAV convexity:** SBB.
- **Bucket A · State / strategic-anchor mega recap:** Ørsted, Worldline,
  Eutelsat.
- **Bucket A · Legal-structure preserves listed common:** Fossil, Viaplay.
- **Bucket B · Post-court recap where common kept real economics
  (anchor-instrument trade):** Core Scientific, Intrum.
- **Bucket C · Post-Ch.11 new common (separate trade):** McDermott/MCDIF.

### Best current matches to the historical multibagger pattern

By bucket, the names closest to the historical templates:

- **Like 3i / Goodman / Yes Bank (Bucket A pro-rata rescue):** Calfrac,
  Petra, Worldline, Exicom.
- **Like ING / Lloyds 2009 (Bucket A bank/national-champion recap):**
  Ørsted, Worldline, Eutelsat.
- **Like Charter / Valaris / Hynix (Bucket C → new common):** McDermott
  (MCDIF) if offshore cycle inflects; Core Scientific as the recent
  template.
- **Like Tenneco (Bucket B debt at distress):** none cleanly accessible
  today in the public watchlist — most Bucket B trades require allocation
  to the ERO or PIPE.

---

## 11. Worked example: Calfrac Well Services

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

**Stage 3 — Triangulation (Tenneco / Munger condition).**

*Leg 1 — PF cap structure & through-cycle valuation.*
- PF net debt ≈ C$120m TL drawn − C$35m equity in − 2L retired.
- Trailing 10-year EBITDA percentiles ≈ C$35m / C$120m / C$240m
  (bear / base / bull).
- Peer cohort (Liberty, ProPetro, NCS) EV/EBITDA: trough 3.5×, mid-cycle
  5.5×, peak 7.0×.
- Bear: EV ≈ C$120m → equity ≈ 0 (current price already there).
- Base: EV ≈ C$660m → equity ≈ C$500m ≈ 2–3× current.
- Bull: EV ≈ C$1.6bn → equity ≈ C$1.4bn ≈ 6–8× current.
- Asymmetric condition satisfied. ✓

*Leg 2 — Cap-stack game theory.*
- 1L: relationship banks; extended TL = friendly. ✓
- 2L: retired with rights proceeds = fulcrum eliminated. ✓
- Equity: pro-rata rights for all; insiders backstop. ✓
- Management: pre-existing options underwater, not repriced.
- No DIP; no cramdown venue. No veto signals present. ✓

*Leg 3 — Revealed preference.*
- Multiple director / insider Form 4 buys at the rights price during
  subscription window. ✓
- No backstop fee / warrant kicker; directors put cash in on same terms
  as public. ✓
- No insider selling in 90 days post-close.
- Need to monitor: 13D / 13F changes at next quarter-end for new
  long-only value-fund entries.

**Triangulation verdict: 3/3 — Tenneco-grade.** All three legs align;
this is the structural setup the framework is built to find.

**Stage 4 — Seat selection.**

- *Old common:* trades near rights offer; dilution-adjusted upside ~3x in
  base case.
- *Rights:* same terms as backstoppers, no kicker — clean seat.
- *Nil-paid rights:* small market; check for sub-TERP fill.
- *Traded debt:* 2L being retired in the deal; nothing left to buy at
  distress.
- *Best seat:* subscribe rights cum-cum; supplement via nil-paid in the
  ex-rights window if it clears below TERP.

**Stage 5 — Event timeline.**

- *Pre-record date:* cum-rights common drifts toward TERP — accumulate
  half size.
- *Ex-rights:* monitor nil-paid; bid 5–10% below TERP for top-up.
- *Subscription:* watch take-up updates; if weak, bid rump auction.
- *Post-close:* confirm UCC terminations on 2L; re-score scorecard.

**Stage 6 — Kill criteria (set on day one).**

- Frac utilization <60% for two consecutive quarters → trim.
- New UCC-1 lien filed within 12 months → exit.
- Going-concern language returns → exit.
- Cap-stack re-leverages above 3.5x net debt/EBITDA → trim.
- Director anchor exits / sells → reassess fully.

**Stage 7 — Sizing.**

- 22/28 = core position.
- Macro backdrop (HY OAS mid-cycle, NA energy spending stabilizing) →
  full size.
- Currency hedge if non-CAD base currency.

---

## 12. Workflow summary

1. **Ingest.** RSS + EDGAR/SEDAR+/RNS form filters + UCC saved searches +
   court dockets feed a single triage inbox (§1).
2. **Tier.** Regex sorts hits into Tier-S / Tier-A / Tier-B / Red-Flag
   lanes (§1.3).
3. **Bucket.** Determine the mechanism bucket *before* scoring (§9 intro):
   Bucket A (listed common is the trade), Bucket B (anchor instrument),
   Bucket C (legacy cancelled; new common only). The bucket sets which
   security you'd be sizing.
4. **Score.** 14-dimension alignment score on first read; quantitative
   tests on filing day; re-run at close (§2, §2.1).
5. **Decision tree.** Five gates: pro-rata → maturity → dilution → anchor
   → catalyst. Drop fast on first failure (§2.2).
6. **Triangulate.** Confirm independent "yes" on all three legs — PF
   cap-structure / through-cycle valuation, cap-stack game theory,
   insider/insti revealed preference (§8). 3/3 = core (Tenneco grade);
   2/3 = option; <2/3 = watchlist or pass.
7. **Fulcrum & seat selection.** Within the bucket, identify EV scenarios,
   walk the cap stack, pick the seat with the cleanest payoff (§4).
   Listed common is the default but rarely the best risk-adjusted seat in
   Charter- or Tenneco-style situations.
8. **Time the entry.** Watch the eight-stage event timeline; most alpha
   lives in T = 0 dilution shock, nil-paid rights, and rump auction (§5).
9. **Adjust for jurisdiction.** Reweight dimension #1 by venue's legacy-
   common survival rate (§6).
10. **Macro-size.** Scale watchlist and tolerance with the distress cycle
    (§7). Don't force trades in benign regimes.
11. **Position.** Score ≥ 18 + triangulation 3/3 = core; score ≥ 18 +
    triangulation 2/3 = option; otherwise pass or short the stub.
    Re-score on every amendment.
12. **Monitor.** UCC and 8-K Item 1.01/2.04 alerts on every active name;
    Form 4 / 13D / 13F changes per quarter for revealed-preference drift;
    auto-drop if a second restructuring becomes visible (NT filings,
    going-concern language, RX advisor hires).

The point of the system is to answer four questions in order, before any
narrative gets in the way:

1. *Rescue for whom?* (bucket — §9)
2. *How good a deal is it?* (scorecard — §2)
3. *Is it asymmetrically priced?* (triangulation — §8)
4. *Which tranche, in which window?* (fulcrum + timing — §4, §5)

Three "yes" answers and a clean fourth identify the next Tenneco. Anything
less is an option at best, and most often a pass.
