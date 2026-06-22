# Sourcing calendars — index reconstitutions, CFIUS, ITC, sovereign events

Static reference dates for low-frequency event windows that don't
justify a full poller. Maintained manually; cross-reference from
`output/universe_screened.md` against the upcoming-window column.

Implements keepers #10 (index reconstitution), #12 (CFIUS), #13
(ITC Section 337) from `output/process_improvements_keepers.md`.

---

## Index reconstitution calendar

Forced-flow windows from index inclusions / deletions. Bennett-Stulz-
Wang 2020 finding: 4-6% abnormal returns around inclusion / deletion.
Names being deleted from a major index face forced selling regardless
of underlying value — that's the entry window for distressed restructurings
that just lost listing eligibility.

### Russell — quarterly reconstitution, mostly June

| Event | Preliminary list | Effective date |
|---|---|---|
| Russell Q2 2026 rebal | mid-May 2026 | June 26, 2026 |
| Russell Q3 2026 rebal | mid-Aug 2026 | Sep 19, 2026 |
| Russell Q4 2026 rebal | mid-Nov 2026 | Dec 19, 2026 |
| Russell 2027 annual rebal | early-May 2027 | June 25, 2027 |

Russell publishes preliminary additions / deletions ~5 weeks before
the effective date at indices.research.ftse.com. The framework
should pull each preliminary list and cross-reference against
universe.md for both potential inclusions (positive flow) and
deletions (forced-selling entry window).

### MSCI — semi-annual

| Event | Effective date |
|---|---|
| MSCI Nov 2026 SAIR | Nov 25, 2026 (close) |
| MSCI Feb 2027 QIR | Feb 28, 2027 |
| MSCI May 2027 SAIR | May 30, 2027 |
| MSCI Aug 2027 QIR | Aug 29, 2027 |

MSCI Semi-Annual Index Reviews (SAIR) in May/Nov are the bigger
events; Quarterly Index Reviews (QIR) in Feb/Aug are smaller.

### S&P — ad-hoc committee decisions

S&P Dow Jones Indices announces changes 5-7 trading days before
effective date. No regular calendar. Watch spglobal.com/spdji
announcements feed.

---

## CFIUS calendar — cross-border anchor risk

CFIUS (Committee on Foreign Investment in the United States)
reviews foreign acquisitions of US businesses with national-
security implications. The 2025 pendulum showed CFIUS can be
re-opened mid-process — Nippon Steel / U.S. Steel reversal in
Q1 2025.

### Relevant 2026 universe.md names with cross-border anchors

| Universe ticker | Cross-border anchor | CFIUS exposure |
|---|---|---|
| FLG | foreign capital allocation pending | Banking review-eligible |
| LAC | DOE ATVM (federal) + GM (US) | None (both US) |
| TKA | Kretinsky / EPCG (Czech) | EU Commission only, no CFIUS |
| SZG | KfW (German state bank) | EU Commission only, no CFIUS |
| ETL | French state | Not CFIUS-reviewable |
| 241560 | Doosan Group (Korean) | Only if US-asset acquisition |
| GTCO | Nigerian, listed NYSE secondary | LSE secondary not CFIUS |

Practical rule: when a Tier-1+2 candidate has a foreign anchor
acquiring US assets above the $107m + 50% threshold, flag
`cfius_status: review_pending` in the YAML. Otherwise N/A.

Source: Treasury CFIUS Annual Report (calendar-year), released
~Aug of the following year. Cross-reference manually.

---

## ITC Section 337 investigations — IP-driven going-private trigger

US International Trade Commission investigations under Section 337
of the Tariff Act of 1930 address patent / trade-secret infringement
in imports. A losing respondent faces an exclusion order — and
public companies in that position frequently respond with a strategic
sale or going-private transaction within 6-12 months.

### Known recent 337 actions affecting universe-relevant names

| Year | Complainant | Respondent | Outcome / window |
|---|---|---|---|
| 2024 | Sonos | Google (Pixel speakers) | Settled 2024-Q4 |
| 2024 | GoPro | Insta360 | Pending |
| 2025 | Apple | Various Asia OEMs | Multiple instances |

Per the keepers doc this poller is secondary — narrower applicability,
slower cadence than the equity-event pollers. Manual review of the
ITC EDIS feed at edis.usitc.gov suffices for now.

---

## Sovereign restructuring equity-recovery calendar

Cross-reference for universe.md names headquartered in the 9 default
jurisdictions covered by Lazard's 2020-2025 paper:

| Country | Default year | Status as of 2026-Q2 | YPF-like equity recovery? |
|---|---|---|---|
| Argentina | 2020 | post-Milei recovery underway | YPF ✓ (in basket); TGS/EDN/GGAL/PAM unbuilt |
| Belize | 2020-21 | completed | Limited equity universe |
| Ecuador | 2020 | completed | TGS-style names worth surveying |
| Suriname | 2020 | completed (VRI used) | Niche |
| Ghana | 2022-23 | DDR + EDR completed | Local banks emerging |
| Sri Lanka | 2022-23 | DDR + EDR completed; SCDI used | Aitken Spence, John Keells emerging |
| Lebanon | ongoing | not yet restructured | Banking sector frozen |
| Zambia | 2020-23 | completed (SCDI used) | Mining names re-rating |
| Russia | 2022 | not restructured (sanctions-blocked) | OFAC General License windows |

The pattern: 12-36 months post-completion, local equity re-rates as
liquidity normalises and import-input costs settle. Our LatAm-heavy
universe-wide top 10 (YPF + TGS + EDN + GGAL + PAM) is exactly this
trade.

Source: [Lazard 2020-2025 Sovereign Debt Crisis paper](https://www.lazard.com/research-insights/the-2020-2025-sovereign-debt-crisis-what-have-we-learnt-and-what-lies-ahead).

---

## Maintenance

This file is static; refresh quarterly. The implementation
priority for the related pollers (Russell preliminary-list scraper,
CFIUS annual-report parser, ITC EDIS poller) is documented in
`output/process_improvements_keepers.md` as "medium tier" —
build them when daily cadence is required, not before.
