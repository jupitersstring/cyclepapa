# Transformation-thesis cross-check + Bastian forcing-function screen

Two threads merged: (1) which of the pasted six (TENB / OXY / BAX / PRU /
KEY / UPS) survive our scoring stack, and (2) what the Bastian /
Kingdom debt-haircut / asset-liquidation / self-help archetype surfaces
when run against our 6,164-name universe.

---

## 1. The six transformation names vs our scoring stack

None of the six appears in `unified_composite.csv` -- that screen is
microcap- and forensic-signal-tilted (P/B < 1, cluster buys,
sub-$500M weighting), so mid- and large-cap institutional-accumulation
plays don't surface. Composite tells us nothing about them. The
question is whether our raw PSU / proxy / buyback layers light up.

| Ticker | mcap | P/B | PSU% | per-share metrics | cond_cat | buyback_verify | our verdict |
|---|---:|---:|---:|---|---|---|---|
| **TENB** | $3.0B | 12.4 | 50 | eps, tsr | -- | -- | basic LTI, no event trigger encoded |
| **OXY** | (no quote) | -- | 60 | tsr, **roce** | -- | -- | quality metric mix, no special-sit cond_cat |
| **BAX** | $10.8B | 1.78 | 57 | eps, tsr, **roic** | **asset_sale_named** | NO_AUTH 0.55% | **HIT** -- PSU encodes the Kidney Care spinoff |
| **PRU** | (no quote) | -- | -- | eps, tsr, roe, other_per_share | -- | TOKEN -1.31% | clean metric stack, weak event leg |
| **KEY** | (no quote) | -- | 60 | eps, tsr, roe, other_per_share | -- | -- | clean metric stack, no triggered event |
| **UPS** | (no quote) | -- | -- | eps, tsr, roic, roce, roe | -- | -- | deep per-share stack, no event |

**Only BAX scores through our structural framework.** It has the named
asset-sale `cond_cat` -- meaning the PSU plan explicitly references the
divestiture you described as the "post-Kidney-Care New Baxter" thesis.
That's the structural confirmation that management's compensation is
tied to executing exactly the transformation the institutional buyers
are underwriting.

TENB/OXY/UPS would need the insider-buy / Form-4 leg to fire to score
high in our composite -- but their mcap is too large for our typical
cluster-buy threshold to trigger. The signal you describe (3 insiders /
~$35M / Wellington & Capital World accumulation) is real but lives
upstream of our current weighting. To capture it, the composite would
need a separate "institutional-accumulation" leg, which we don't have.

## 2. Bastian forcing-function screen (`bastian_forcing.csv`)

Re-applying the BBGI / RGS / NLOP / UNFI playbook against the 6,164
universe -- microcaps (mcap <= $600M), P/B < 1.5, with at least one
forcing-function trigger present in our existing layers:

- post-Ch11 emergence PSU trigger (+30)
- debt-paydown / leverage-target PSU trigger (+25)
- restructuring-milestone PSU trigger (+25)
- named asset-sale PSU trigger (+20)
- M&A close trigger (+15)
- spin trigger (+15)
- issuer SELF_TENDER live (+25)
- TARGET 14D-9 live (+25)
- going-private 13E-3 (+20)
- verified EXECUTING / SHRINKING buyback (+10 / +8)
- P/B floor kicker (+15 / +10 / +5 at <0.5 / <0.7 / <1.0)

### Top 22 forcing-function microcaps

| # | TKR | scr | mcap | px | P/B | PSU/gov | thesis |
|--:|---|--:|--:|--:|--:|---|---|
| 1 | **BEEP** | 48 | $76M | 1.85 | 0.55 | 2/12 | M&A + spin triggers + organic -3.5% shrink |
| 2 | GNPX | 45 | $7M | 0.64 | 0.34 | 16/0 | M&A + spin triggers, deep book |
| 3 | LGL | 45 | $45M | 6.87 | 1.01 | 11/4 | **post-Ch11 emergence + spin** |
| 4 | **DXLG** | 40 | $38M | 0.69 | 0.37 | 18/15 | TARGET tender live + P/B 0.37 |
| 5 | **WW** | 40 | $185M | 18.55 | 0.58 | 22/3 | **post-Ch11 emergence + P/B 0.58** |
| 6 | OSUR | 40 | $288M | 4.18 | 0.86 | 2/-2 | restructuring milestone + EXECUTING -5.9% |
| 7 | KROS | 35 | $197M | 9.93 | 0.69 | 0/0 | issuer SELF_TENDER live |
| 8 | **GETY** | 35 | $299M | 0.71 | 0.55 | 6/4 | SELF_TENDER live + P/B 0.55 |
| 9 | NUS | 35 | $264M | 5.43 | 0.33 | 40/11 | named asset-sale PSU + P/B 0.33 |
| 10 | **GPUS** | 35 | $91M | 0.17 | 0.50 | 0/0 | SELF_TENDER live + P/B 0.50 |
| 11 | FUBO | 30 | $286M | 9.73 | 0.35 | 9/15 | M&A close trigger + P/B 0.35 |
| 12 | CLW | 30 | $267M | 16.55 | 0.33 | 38/4 | spin trigger + P/B 0.33 |
| 13 | **EXFY** | 30 | $121M | 1.25 | 0.87 | 0/0 | issuer SELF_TENDER live |
| 14 | PMCB | 30 | $8M | 0.78 | 0.22 | 2/0 | M&A close trigger + P/B 0.22 |
| 15 | JTAI | 30 | $10M | 6.75 | 0.12 | 0/0 | spin trigger + P/B 0.12 |
| 16 | **LE** | 30 | $381M | 12.41 | 0.76 | 51/15 | TARGET tender live + 86% PSU stack |
| 17 | AMS | 30 | $10M | 1.45 | 0.40 | 12/4 | spin trigger + P/B 0.40 |
| 18 | WKHS | 25 | $33M | 2.99 | 0.67 | 11/8 | M&A close trigger |
| 19 | FLGT | 25 | $531M | 18.68 | 0.51 | 14/0 | M&A close + P/B 0.51 |
| 20 | ARQ | 25 | $115M | 2.68 | 0.68 | 8/7 | spin trigger |
| 21 | AOUT | 25 | $129M | 10.23 | 0.77 | 0/4 | named asset-sale PSU |
| 22 | ALIT | 25 | $358M | 0.65 | 0.34 | 26/7 | EXECUTING -4.1% + P/B 0.34 |

### Sub-archetype split (Bastian taxonomy)

| Bastian bucket | Best representative |
|---|---|
| A. Debt-haircut equity stub (RGS analogue) | **LGL** (post-Ch11 stub trading at book) |
| B. Forced asset-liquidation stub (NLOP analogue) | **NUS** (named asset-sale PSU, P/B 0.33) |
| C. Operational self-help turnaround (UNFI analogue) | **WW** (post-Ch11, P/B 0.58, repair plan in PSU) |
| D. Narrative-flip / perception lag (WATT analogue) | **DXLG** (live TARGET 14D-9 + 11.6x price ladder at P/B 0.37) |
| E. Issuer-tender stub (BBGI-adjacent) | **GETY / GPUS / EXFY** (all live self-tender at half book) |

## 3. The gap your writeup exposes

Our existing data captures forward-conditional PSU triggers and tender
activity, but it doesn't yet scan 8-K filings for the *creditor-forced*
language that made BBGI the archetype: `exchange offer`,
`consent solicitation`, `PIK notes`, `springing maturity`,
`equity conversion`, `strategic alternatives committee`,
`asset sales sufficient to repay`, `transaction support agreement`.

These are the keywords that flag a debt-haircut equity stub *before*
the asset sale closes -- the BBGI window between exchange-offer
acceptance (Sep 2025) and forced asset-sale deadline (Sep 2027). Our
current screen would catch BBGI only via its strategic-alternatives
disclosure if it appeared in a DEF 14A; it would miss the second-lien
exchange and 95% equity-conversion feature entirely because those live
in 8-K and exchange-offer-circular text we don't parse.

This is the next leg to build: an 8-K keyword scanner with the BBGI
keyword set, sharded across the same 6,164 submissions feed we already
walk for the proxy and tender scans. The output would be the third
forcing-function source alongside `proxy_scan.json` (PSU triggers) and
`tender_scan.json` (tender mechanics): something like
`debt_haircut_scan.json` keyed by accession with parsed haircut /
maturity-extension / equity-conversion fields.

## 4. Recommendation ranked by Bastian-fit

For the six pasted names:

1. **BAX** -- only one our framework structurally confirms; PSU on
   named asset sale matches the Kidney Care thesis. *Operational
   self-help turnaround (Bastian C).*
2. **TENB** -- transformation thesis is real but lives outside our
   scoring; would need an institutional-accumulation leg we don't
   currently weight.
3. **OXY** -- transformation already substantially realized (per your
   note +58.8% YTD); asymmetry compressed.
4. PRU / KEY / UPS -- mid/large-cap balance-sheet repair stories;
   our microcap-forensic screen isn't the right lens.

For the Bastian / Kingdom archetype itself: **BEEP, LGL, WW, DXLG,
NUS, GETY, GPUS** are the cleanest forcing-function setups in our
current universe. All hit at least two of (microcap + sub-book +
explicit triggered event), and three of the seven (GETY, GPUS,
EXFY) sit inside live issuer self-tenders -- BBGI-adjacent
mechanics even though no PIK / springing-maturity language is yet
parsed.
