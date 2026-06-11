.PHONY: score poll waterfall validate clean help

help:
	@echo "Targets:"
	@echo "  score      — compile data/candidates/*.yaml → output/screen_generated.md"
	@echo "  poll       — run EDGAR full-text poller for today; writes data/inbox/"
	@echo "  waterfall  — Monte Carlo across all candidates"
	@echo "  validate   — schema check only (no output written)"
	@echo "  clean      — remove generated outputs"

score:
	python3 src/score.py

poll:
	python3 -m src.edgar_poll

waterfall:
	@for f in data/candidates/*.yaml; do \
		python3 src/waterfall.py $$f; \
	done

validate:
	python3 -c "from src.score import load_candidates; \
	cs = load_candidates(); \
	[print(c.path.name, c.errors or 'ok') for c in cs]; \
	import sys; sys.exit(1 if any(c.errors for c in cs) else 0)"

clean:
	rm -f output/screen_generated.md
