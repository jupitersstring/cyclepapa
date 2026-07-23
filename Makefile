.PHONY: score poll uk-poll ca-poll jp-poll us-bankr-poll br-poll au-poll sc13d-poll form15-poll cluster-sells ofac-poll lobbying-poll credit-spread-poll thirteenf-poll postreorg-poll eightk-items-poll edgar-forms-poll hkex-poll sgx-poll euronext-poll jse-poll distressed-13d-poll pacer-emergence-poll going-concern-poll equity-committee-poll nol-shells cohort-lens poll-all security-master source-health corroborate reconcile postreorg-score postreorg-verify emergence-master db listed-equity-screen waterfall validate portfolio audit clean help inbox-promote universe-rr workbook refresh

help:
	@echo "Targets:"
	@echo "  audit      — durability audit; fails on any high-severity finding"
	@echo "  score      — compile data/candidates/*.yaml → output/screen_generated.md"
	@echo "  poll       — run EDGAR full-text poller for today; writes data/inbox/"
	@echo "  uk-poll    — run FCA NSM (RNS) poller for UK special-situation events"
	@echo "  ca-poll    — run SEDAR+ poller for Canadian special-situation filings (run hourly)"
	@echo "  jp-poll    — run TDnet poller for Japanese TSE special-situation events"
	@echo "  us-bankr-poll — CourtListener RECAP poller for US Chapter 11/15 filings"
	@echo "  br-poll    — CVM IPE poller for Brazilian material-fact disclosures"
	@echo "  au-poll    — ASX announcements poller for Australian/NZ special-situation events"
	@echo "  sc13d-poll — SC 13D / 13D-A activist 5pct beneficial-owner filings"
	@echo "  form15-poll — Form 15 going-dark / Section 12 deregistration"
	@echo "  cluster-sells — Form 4 S-code cluster-sell detector (Wirecard/SVB red flag)"
	@echo "  ofac-poll  — OFAC recent-actions (sanctions GL + designations)"
	@echo "  lobbying-poll — Senate LDA lobbying-disclosure filings"
	@echo "  credit-spread-poll — FRED ICE BofA HY/IG/CCC OAS market-level monitor"
	@echo "  universe-rr  — rank reward/risk across the full universe (REAL where YAML, PROXY otherwise)"
	@echo "  workbook     — rebuild the Excel workbook from latest inputs"
	@echo "  refresh      — full chain: pollers → promote → screen → rank → workbook"
	@echo "  waterfall  — Monte Carlo across all candidates"
	@echo "  portfolio  — factor decomposition + correlation + risk-budgeted weights → output/portfolio.md"
	@echo "  inbox-promote — promote poller hits from data/inbox/ → universe.md (closes the loop)"
	@echo "  universe   — re-rank universe.md → output/universe_screened.md"
	@echo "  all        — full chain: poll → spinoff → cluster-buys → inbox-promote → universe → score → waterfall → portfolio → events"
	@echo "  validate   — schema check only (no output written)"
	@echo "  clean      — remove generated outputs"

audit:
	python3 src/audit.py

score: audit
	python3 src/score.py

poll: audit
	python3 -m src.edgar_poll

uk-poll: audit
	python3 -m src.uk_rns_poll --days-back 1

# SEDAR+ default view = 30 most-recent CSA filings (~last hour). For daily
# coverage this target should run hourly, not once-a-day.
ca-poll: audit
	python3 -m src.sedarplus_poll

jp-poll: audit
	python3 -m src.jpx_tdnet_poll

# US bankruptcy-court docket poller via CourtListener RECAP (free v4 API).
# Picks up new Chapter 11/15 filings from the 7 most-active commercial
# bankruptcy courts (Delaware, SDNY, SD Texas, etc.).
us-bankr-poll: audit
	python3 -m src.pacer_poll --days-back 1

# Brazilian CVM IPE (material-fact) disclosure poller via dados.cvm.gov.br.
# Free, weekly-refreshed ZIP archive. Closes the Brazil leg of the LatAm
# gap (Argentina via universe; Brazil otherwise absent).
br-poll: audit
	python3 -m src.cvm_poll --days-back 1

# Australian ASX announcements poller via the public Markit Digital JSON
# endpoint. Covers ASX-listed + dual-listed NZ issuers.
au-poll: audit
	python3 -m src.asx_poll --days-back 1

# SC 13D / SC 13D-A activist 5pct beneficial-owner filings via EDGAR
# Atom feed (browse-edgar getcurrent). 5-business-day window post-Feb 2024.
sc13d-poll: audit
	python3 -m src.sc13d_poll

# Form 15 (15-12B, 15-12G, 15-15D) Section 12 going-dark deregistration
# filings via EDGAR Atom feed.
form15-poll: audit
	python3 -m src.form15_poll

# Form 4 cluster SELLS detector — Wirecard / SVB red-flag pattern.
# Sibling to cluster_buys.py; same EDGAR Form 4 mechanic, S-code filtered.
cluster-sells: audit
	python3 -m src.cluster_sells --days-back 60

# OFAC Recent Actions poller — sanctions-restructuring calendar via the
# public ofac.treasury.gov/recent-actions feed.
ofac-poll: audit
	python3 -m src.ofac_poll --pages 4

# US Senate LDA lobbying-disclosure poller via lda.senate.gov/api/v1.
# Cross-references client names against universe.md + filters by
# special-situation-relevant general-issue codes (Energy/Nuclear,
# Banking, Bankruptcy, Foreign Relations, Defense, Pharmaceuticals,
# Telecom, Transportation, Mining, etc.).
lobbying-poll: audit
	python3 -m src.lobbying_poll --days-back 7

# FRED ICE BofA OAS monitor — bond spreads as equity-event leading
# indicator. HY/IG/CCC bands; flags 30-day moves >= per-band threshold.
credit-spread-poll: audit
	python3 -m src.credit_spread_poll

# 13F institutional-holdings mirror — diffs known special-sits funds'
# quarterly filings for NEW positions + material adds (smart-money signal).
thirteenf-poll: audit
	python3 -m src.thirteenf_poll --min-value-usd 10000000

# Post-reorganization / fresh-start equity poller — catches companies
# EMERGING from Chapter 11 (the payoff end PACER's entry-signal misses).
postreorg-poll: audit
	python3 -m src.postreorg_poll --days-back 90

# 8-K item-code poller — precise structured event triggers (item 1.03
# bankruptcy, 2.04 default, 3.01 delisting-deficiency, 4.02 restatement).
# Verifies each hit against EDGAR's structured `items` field.
eightk-items-poll: audit
	python3 -m src.eightk_items_poll --days-back 1

# Multi-form EDGAR poller — proxy contests (DFAN14A/DEFC14A), merger votes
# (DEFM14A/PREM14A), self-tenders (SC TO-I), delistings (25-NSE), and SEC
# comment letters (UPLOAD/CORRESP).
edgar-forms-poll: audit
	python3 -m src.edgar_forms_poll --count 100

# Fault-isolated orchestrator: runs every poller in its own subprocess so
# one failure can't abort the refresh chain. Report: output/poller_run.md.
poll-all: audit
	python3 -m src.run_pollers --timeout 600

# Security master — canonical entity crosswalk (CIK/ticker/CUSIP/ISIN/LEI).
# Warm the SEC crosswalk + batch-resolve inbox CUSIPs so corroboration
# resolves entities exactly across sources.
security-master: audit
	python3 -m src.security_master --warm
	python3 -m src.security_master --resolve-inbox-cusips --days-back 120

# Source-health observability — per-source freshness + volume-anomaly
# monitoring. Non-fatal (|| true) so a STALE source doesn't abort refresh.
source-health: audit
	-python3 -m src.source_health --days-back 30

# Cross-source corroboration — fuses all pollers; surfaces entities
# independently flagged by >= 2 distinct sources.
corroborate: audit
	python3 -m src.corroborate --days-back 14

# Pipeline completeness guard — traces every universe.md name to the
# ranking and flags any above-threshold name silently dropped.
reconcile: audit
	-python3 -m src.reconcile

# Post-reorg assembly scorecard — grades the fresh-start cohort on the
# Verdad EBIT-yield screen + Chapter-22 veto + assembly checklist.
# Network-bound (SEC XBRL + Yahoo); run standalone, not in refresh.
# No --max-names → scores the ENTIRE cohort (no silent truncation).
postreorg-score: audit
	python3 -m src.postreorg_score

# Inbox index — (re)build the queryable SQLite index over data/inbox/.
# Derived + fully rebuildable from the tracked JSON (the source of truth);
# committed only so the durability audit sees no untracked data.
db: audit
	python3 -m src.inbox_db --build

# Distressed-fund 13D control tracker — loan-to-own funds (Oaktree,
# Apollo, Centerbridge, Elliott, Silver Point...) filing 13D/13G on an
# equity = debt-to-equity control, the highest-signal post-reorg tell.
distressed-13d-poll: audit
	python3 -m src.distressed_13d_poll --days-back 730

# Court-side EMERGENCE poller — plan-confirmation orders + notices of
# effective date via CourtListener RECAP (the exact docket emergence).
pacer-emergence-poll: audit
	python3 -m src.pacer_emergence_poll --days-back 120

# Going-concern RECOVERY poller — filings where the auditor's substantial-
# doubt qualification was ALLEVIATED/RESOLVED (a turnaround the market is
# slow to re-rate). --include-flags also polls the distress side.
going-concern-poll: audit
	python3 -m src.going_concern_poll --days-back 120

# Equity-committee + plan-competition tracker (the Hertz preconditions:
# the ONLY conditions under which in-case OLD common is investable).
equity-committee-poll: audit
	python3 -m src.equity_committee_poll --days-back 365

# NOL-shell registry — WMIH->Mr Cooper playbook: post-reorgs whose tax
# attributes are a material fraction of market cap. Network-bound.
nol-shells: audit
	python3 -m src.nol_shell_scan

# Cohort / capacity-exit lens — industry restructuring waves + the
# second-vintage rule from our own inbox record. Network-bound (SIC).
cohort-lens: audit
	python3 -m src.cohort_lens

# HKEX (Hong Kong) special-situations poller — resumption-of-trading,
# scheme/restructuring, privatisation, suspension, liquidation via the free
# HKEXnews title-search JSON. Closes the Hong Kong geography the EDGAR-centric
# funnel is blind to.
hkex-poll: audit
	python3 -m src.hkex_poll --days-back 180

# SGX (Singapore) special-situations poller — scheme/restructuring/capital-
# reorganisation via the free legacy api3.sgx.com infofeed. Feed serves only
# "today", so run DAILY to accumulate coverage.
sgx-poll: audit
	python3 -m src.sgx_poll

# Euronext (Paris) special-situations poller — sauvegarde / redressement /
# reprise de cotation via the free French OAM (info-financiere.gouv.fr).
euronext-poll: audit
	python3 -m src.euronext_poll --days-back 180

# JSE (Johannesburg) SENS poller — business-rescue / scheme / resumption via
# the free Sharenet SENS mirror. Feed is ~2 trading days, so run DAILY.
jse-poll: audit
	python3 -m src.jse_poll

# Emergence master — fuse every Chapter 11 EMERGENCE signal in data/inbox/
# (emergence 8-K, fresh-start accounting, Form 25/15 delisting, Form 8-A
# relisting, PACER docket) into one confidence-scored event list, and run
# the completeness tripwire against data/emergence_ground_truth.json.
emergence-master: audit
	python3 -m src.emergence_master

# Filer-emergence verifier — reads each emergence filing to confirm the
# FILER itself emerged (not an incidental reference to another issuer's
# Chapter 11) and extracts the emergence date. Warms the shared cache the
# listed-equity screen consumes. Network-bound; standalone.
postreorg-verify: audit
	python3 -m src.postreorg_verify

# Listed-equity reorganization screen — the tradable slice (exchange-listed
# common only) graded on the six-question sweet-spot test + entry-archetype
# tags (forced-creditor overhang, excess cash, share-reserve, refinancing).
# Verifies filer-emergence and drops incidental third-party references.
# Network-bound; run standalone. Scores the entire cohort.
listed-equity-screen: audit
	python3 -m src.listed_equity_screen

waterfall: audit
	@for f in data/candidates/*.yaml; do \
		python3 src/waterfall.py $$f; \
	done

portfolio: audit
	python3 src/portfolio.py

spinoff: audit
	python3 -m src.spinoff_radar

cluster-buys: audit
	python3 -m src.cluster_buys

events: audit
	python3 src/events.py

universe: audit
	python3 src/universe_screen.py

# Apply quantitative reward/risk ranking across every universe row.
# Depends on `universe` so the screener output is fresh.
universe-rr: universe
	python3 -m src.universe_risk_reward
	-python3 -m src.reconcile

# Rebuild the Excel workbook from the latest universe-wide ranking,
# YAMLs, and portfolio output.
workbook: universe-rr portfolio
	python3 -m src.build_workbook

# Full screener/scraper → workbook refresh chain. Runs the four
# pollers, promotes their hits into universe.md, re-screens, re-ranks
# reward/risk, regenerates the portfolio file, and rebuilds the
# workbook. Run hourly during business hours for ca-poll to be useful;
# the others tolerate a daily cadence.
refresh: audit poll-all source-health security-master corroborate inbox-promote workbook
	@echo "Universe refreshed end-to-end. Open output/cyclepapa_risk_reward_workbook.xlsx"

inbox-promote: audit
	python3 -m src.inbox_promote --days-back 120

all: audit poll uk-poll ca-poll jp-poll spinoff cluster-buys inbox-promote universe score waterfall portfolio events
	@echo "All pipelines run."

validate:
	python3 -c "from src.score import load_candidates; \
	cs = load_candidates(); \
	[print(c.path.name, c.errors or 'ok') for c in cs]; \
	import sys; sys.exit(1 if any(c.errors for c in cs) else 0)"

clean:
	rm -f output/screen_generated.md output/portfolio.md
