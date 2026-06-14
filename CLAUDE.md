# FIP Screener — Persistence and Recovery

This repo's remote sandbox can wipe `/tmp` and any gitignored file between
sessions. Anything not committed is lost forever. The setup below makes
that recoverable.

## What survives a sandbox reset

| Artifact | Stored as | Survives? | Reason |
|---|---|---|---|
| Screener code (`frog_in_pan_screener.py`) | git-tracked | ✅ | normal commit |
| Result CSVs (`leading_*.csv`, `asymmetric_*.csv`, `fip_*.csv`, etc.) | git-tracked | ✅ | `.gitignore` allows them through; stop hook auto-commits |
| Python venv (`/tmp/venv`) | ephemeral | ❌ — but auto-rebuilt | `session-start.sh` reinstalls packages on every start |
| OHLC cache (`.ohlc_cache.pkl`, 80–100 MB) | gitignored | ❌ — but rebuildable | too large for git; rebuilt from `financedatabase` + `yfinance` on next run |

## Hooks

- **SessionStart** (`.claude/hooks/session-start.sh`)
  - Creates `/tmp/venv`, installs `financedatabase yfinance pandas numpy`
  - `git pull --rebase --autostash origin <branch>` so the session always
    sees the most recent committed CSVs and code
- **Stop** (`.claude/hooks/stop.sh`)
  - At the end of each session, stages `*.csv`, `*.py`, `CLAUDE.md`,
    `.claude/` and commits with `auto-checkpoint: session results <UTC>`
  - Pushes with up to 4 retries; never blocks the session

## Restoring from a cold sandbox

1. New session boots → SessionStart pulls latest CSVs and re-installs
   the venv.
2. The screener reads any `leading_*.csv` already in the repo for
   fundamentals; only the OHLC cache needs to be rebuilt.
3. To rebuild the OHLC cache: run any `python frog_in_pan_screener.py
   --mode qulla --leading ...` command. It will repopulate `.ohlc_cache.pkl`
   over ~5–20 min depending on universe size.

## Manual checkpoint

If you want to commit and push results mid-session without waiting for the
Stop hook:

```bash
git add -A -- '*.csv' '*.py' 'CLAUDE.md' '.claude/'
git commit -m "checkpoint: <reason>"
git push origin "$(git rev-parse --abbrev-ref HEAD)"
```

## What the screener writes

Result files (all preserved in git going forward):
- `leading_<region>.csv` — fundamentals + RS metrics from `--mode qulla --leading`
- `fip_today_*.csv` — deep-FIP-today screens
- `asymmetric_fip*.csv` — composite asymmetry screens (v1 and v2)
- `rs_*.csv` — RS-FIP flip screens
- `early_*.csv` — early-stage FIP screens
- `triple_inflection_us.csv`, `smoothness_velocity_us.csv`, etc.

These are the *expensive* outputs (hours of rate-limited yfinance calls)
and are now durable.
