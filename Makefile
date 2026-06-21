.PHONY: score poll uk-poll ca-poll jp-poll us-bankr-poll br-poll waterfall validate portfolio audit clean help inbox-promote universe-rr workbook refresh

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

# Rebuild the Excel workbook from the latest universe-wide ranking,
# YAMLs, and portfolio output.
workbook: universe-rr portfolio
	python3 -m src.build_workbook

# Full screener/scraper → workbook refresh chain. Runs the four
# pollers, promotes their hits into universe.md, re-screens, re-ranks
# reward/risk, regenerates the portfolio file, and rebuilds the
# workbook. Run hourly during business hours for ca-poll to be useful;
# the others tolerate a daily cadence.
refresh: audit poll uk-poll ca-poll jp-poll us-bankr-poll br-poll spinoff cluster-buys inbox-promote workbook
	@echo "Universe refreshed end-to-end. Open output/cyclepapa_risk_reward_workbook.xlsx"

inbox-promote: audit
	python3 -m src.inbox_promote --days-back 7

all: audit poll uk-poll ca-poll jp-poll spinoff cluster-buys inbox-promote universe score waterfall portfolio events
	@echo "All pipelines run."

validate:
	python3 -c "from src.score import load_candidates; \
	cs = load_candidates(); \
	[print(c.path.name, c.errors or 'ok') for c in cs]; \
	import sys; sys.exit(1 if any(c.errors for c in cs) else 0)"

clean:
	rm -f output/screen_generated.md output/portfolio.md
