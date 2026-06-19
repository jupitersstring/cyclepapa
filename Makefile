.PHONY: score poll uk-poll waterfall validate portfolio audit clean help inbox-promote

help:
	@echo "Targets:"
	@echo "  audit      — durability audit; fails on any high-severity finding"
	@echo "  score      — compile data/candidates/*.yaml → output/screen_generated.md"
	@echo "  poll       — run EDGAR full-text poller for today; writes data/inbox/"
	@echo "  uk-poll    — run FCA NSM (RNS) poller for UK special-situation events"
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

inbox-promote: audit
	python3 -m src.inbox_promote --days-back 7

all: audit poll uk-poll spinoff cluster-buys inbox-promote universe score waterfall portfolio events
	@echo "All pipelines run."

validate:
	python3 -c "from src.score import load_candidates; \
	cs = load_candidates(); \
	[print(c.path.name, c.errors or 'ok') for c in cs]; \
	import sys; sys.exit(1 if any(c.errors for c in cs) else 0)"

clean:
	rm -f output/screen_generated.md output/portfolio.md
