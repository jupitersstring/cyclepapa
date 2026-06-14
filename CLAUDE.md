# Project rules for Claude (and future humans)

## The non-negotiable rule

**Every file that represents work — fetched data, analytical state,
cached results, screening output, candidate YAMLs, scripts, write-ups —
MUST be tracked by git, MUST be committed, and MUST be pushed before the
session ends.**

This rule exists because a prior session lost ~10,000 tickers' worth of
fundamentals, screener outputs, ranking CSVs, and Excel reports when the
sandbox was reset. The data lived in `.cache/` and `results_*.csv`
directories that were silently `.gitignore`'d. Only the source code
survived. **Do not let this happen here.**

## Concrete obligations on every change

1. **Before you write a file**, decide whether it represents work the
   user would lose if the sandbox is wiped. If yes, it lives in
   `data/`, `output/`, `src/`, or a tracked top-level path — never in
   `.cache/`, `/tmp/`, or any ephemeral location.

2. **Before you `.gitignore` anything**, ask yourself: would this
   pattern have caused the prior data loss? If the answer is yes or
   unclear, STOP and ask the user. The current `.gitignore` is
   deliberately narrow (only Python build artifacts, virtualenvs, and
   editor scratch files). Adding `data/`, `output/`, `cache/`, `*.csv`,
   `*.yaml`, or `*.json` is forbidden without explicit user approval.

3. **Before you end a session**, run `make audit`. It exits non-zero if
   any of the failure modes are present:
   - untracked files in `data/`, `output/`, or `src/`
   - unpushed commits on the current branch
   - uncommitted changes
   - dangerous `.gitignore` patterns
   - suspicious cache-y filenames in the working tree
   - source code writing to `.cache/` or similar ephemeral paths
   The Makefile chains `audit` into `score`, `poll`, `waterfall`, and
   `portfolio` so the failure mode cannot accumulate silently.

4. **Push after every meaningful commit.** The remote is the only
   durable store. Local commits in the sandbox count as transient.

## How the defences are wired

- **`.gitignore`** — narrow allowlist-style. Documents what is
  *deliberately* excluded and explicitly forbids adding analytical
  state to it.
- **`src/audit.py`** — durability audit. Run via `make audit`. Exits
  non-zero on any high-severity finding. Source of truth for what
  "durable" means in this repo.
- **`Makefile`** — every long-running target depends on `audit` so the
  pipeline refuses to run on a non-durable state.
- **`.claude/settings.json`** — `SessionStart` hook runs the audit and
  prints findings before any conversation begins. `Stop` hook warns
  if the session is ending with uncommitted or unpushed work.

## What this rule does NOT mean

- It does not mean commit every keystroke. Commits should still
  represent coherent units of work with descriptive messages.
- It does not mean every file goes in git. Editor scratch
  (`.swp`/`.idea`/`.vscode`), virtualenvs, and `__pycache__/` are
  legitimately excluded — the `.gitignore` enumerates these
  explicitly so adding new exclusions requires conscious choice.
- It does not mean run `audit` once and trust it forever. Run it at
  session start (automatic via hook), before any long operation
  (automatic via Makefile), and before ending the session
  (automatic via Stop hook).

## If you find yourself wanting to add to `.gitignore`

Stop. Ask: would excluding this pattern have caused the prior data
loss? Re-read the comment block at the top of `.gitignore`. If you
still believe the exclusion is appropriate, **ask the user
explicitly**. Do not add it on your own authority.

## Operating context

Working branch: `claude/capital-structure-screening-5YjnH`.
Push to: `origin/claude/capital-structure-screening-5YjnH`.
Never push to `main` without explicit user approval.
