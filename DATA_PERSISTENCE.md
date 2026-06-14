# Data persistence policy

## The vulnerability we are closing

The Claude Code sandbox is **ephemeral**. The working directory persists
*within* a session but is wiped between sessions. Every hour of
rate-limited yfinance fetching, every Investegate RNS scrape, every
ranked screen output — if it isn't in git, it is gone the next time the
sandbox is recreated.

We previously had a `.gitignore` that excluded `data/`, `results_*.csv`,
`top30_*.csv` and `signals_history.csv` "because they're caches". They
are not caches. They are **outputs of expensive scrapes** that cannot
be regenerated in seconds. Treating them like Python bytecode was the
defect.

## What is now committed and durable

| Path | What | Why durable |
|---|---|---|
| `data/prices/*.parquet` | Weekly OHLCV (5y per ticker × 498 tickers) | yfinance is rate-limited; refetching takes ~10 min and may fail per-ticker |
| `data/prices_daily/*.parquet` | Daily OHLCV (6m per ticker) | Same — and needed for daily-spike phase |
| `data/investegate/*.json` | RNS announcement cache per EPIC | One HTTP per UK ticker; bandwidth + 24h TTL |
| `signals_history.csv` | Per-date signal snapshots | Week-on-week deltas; cannot be reconstructed retrospectively |
| `results_*.csv` | Every full screen output, dated | The audit trail; comparison week-to-week |
| `top30_*.csv` | Sleeve ranking snapshots | What we actually traded off |
| `universe.csv` | Tickers + catalyst + NAV-class metadata | The single source of truth |

## What is still ignored (and why that's safe)

| Path | Why ignored |
|---|---|
| `__pycache__/`, `*.pyc`, `*.pyo` | Python compile artefacts — rebuild in milliseconds |
| `.pytest_cache/` | Test runner cache — rebuilds on next run |

That's it. Everything else is in git.

## Enforcement

Three layers stop this from regressing silently:

1. **`.gitignore` is minimal.** If a future contributor adds something
   like `data/` back to the ignore list, it shows up in code review.
2. **Stop-hook** (`scripts/check_committed.sh`) refuses to let a
   session end with uncommitted runtime data. Wired into `~/.claude/`
   via the user's existing stop-hook setup.
3. **Pre-commit habit** — after any `screen_v3.py` run or any
   `signals.py` batch, the next action is `git add -A && git commit`.
   Documented in `README.md` quickstart.

## Recovery checklist (if you arrive in a fresh sandbox)

```bash
# 1. Pull the durable state from origin
git pull origin claude/nav-discount-finder-o7qM9

# 2. Install pinned deps
pip install -r requirements.txt

# 3. Verify tests pass and cached data loaded
python3 -m pytest tests/ -q
python3 -c "import metadata; print(len(metadata.load_universe()))"
ls data/prices/ | wc -l         # should be hundreds
ls data/investegate/ | wc -l    # should be ~260 UK names

# 4. Optional: refresh cached data
python3 screen_v3.py --refresh-prices    # forces yfinance refresh
```

If any of these steps fails, **stop and investigate before running a
new screen** — the durability has been violated again.

## Quantified cost of the previous regression

The session prior to this one was wiped. What was lost:

- Cached weekly OHLCV for 498 tickers
- Cached daily OHLCV for 498 tickers
- Cached Investegate RNS for ~260 UK EPICs
- 6 dated results CSVs (multi-MB total)
- ~530 rows of signals_history snapshots

Wall-clock cost to regenerate from scratch:
- yfinance refresh: ~30 min (rate-limited, sequential)
- Investegate scrape: ~25 min (one HTTP per EPIC)
- Combined re-run: ~1.5 hours

Wall-clock cost going forward to never lose it again:
- `git add -A && git push` — seconds.

That's the trade.
