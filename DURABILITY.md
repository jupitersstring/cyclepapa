# Durability Guarantees

All screener outputs **must** survive sandbox/container resets. This file
documents the layered defenses.

## What's at risk

Sandbox resets wipe `/tmp`, kill all background processes, and discard any
uncommitted/untracked files in the working tree. We've already lost work to
this. Never again.

## Layer 1 — All output paths under tracked dirs

Screeners write to `data/{dalton,fundamentals,absorption,prebreakout,
compression,td_seq,synthesis,universes}/`. All of these are tracked by git.

`.gitignore` explicitly whitelists `!data/**`. Never add anything that would
re-shadow that.

## Layer 2 — auto-commit loop

`scripts/auto_commit_loop.sh` runs as a background process. Every 30 s, if
`git status data/` shows new/modified files, it commits and pushes to the
remote with exponential backoff retry.

If this process dies, the next layer catches it.

## Layer 3 — SessionStart hook

`.claude/settings.json` registers a `SessionStart` hook that runs
`scripts/durability_bootstrap.sh` every time a Claude session starts. The
bootstrap:

1. Commits any pending `data/` changes immediately.
2. Pushes to the remote (with retry).
3. Relaunches `auto_commit_loop.sh` if it isn't running.
4. Warns about any untracked files in `data/`.

## Layer 4 — Manual sanity check

Run `bash scripts/durability_bootstrap.sh` at any point to force a sync.

## Things that would break this

- Adding `data/` (or any sub-path) to `.gitignore`. Don't.
- Writing screener output to `/tmp` or `/var/tmp`. Don't — write under `data/`.
- Background processes spawning new files outside `data/`. Either redirect
  them under `data/`, or add their target dir to the auto-commit watch list.
- Killing `auto_commit_loop.sh` without restarting it. The SessionStart hook
  will bring it back, but only on next session.

## Pipeline scripts that write output

Verified to write under `data/`:

- `scripts/run_all_screens.sh`         → `data/{dalton,absorption,prebreakout,compression,fundamentals}/`
- `scripts/recovery_pass.sh`           → `data/{dalton,fundamentals}/<mkt>_recovery.csv`
- `scripts/final_pipeline.sh`          → `data/{dalton,absorption,prebreakout,compression,fundamentals}/<mkt>_lg.csv`
- `scripts/build_universes.py`         → `data/universes/uni_<mkt>.csv`
- `scripts/build_large_universes.py`   → `data/universes/large/uni_<mkt>_lg.csv`
- `scripts/build_recovery_universes.py`→ `data/universes/recovery/uni_<mkt>_missed.csv`
- `scripts/pull_fundamentals.py`       → `data/fundamentals/fund_<mkt>.csv`
- `scripts/master_synthesis_v2.py`     → `data/synthesis/v2_*.csv`
- `scripts/td_overlay_v2.py`           → `data/synthesis/v2_final_*.csv`
- `screeners/td_sequential_screen.py`  → `data/td_seq/td_<universe>.csv`
