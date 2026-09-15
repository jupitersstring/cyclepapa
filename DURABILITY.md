# Durability contract

Every byte of pipeline output that costs >1 second of compute or one
EDGAR/yfinance request to recreate is committed to git. A sandbox
reset takes only `__pycache__/` and transient logs with it.

## Verified durable artifacts (all tracked in git)

| Source | Tracked file | Size | Recreate cost if lost |
|---|---|---:|---|
| 6,164 ticker 10b5-1 sweep | `cancel_10b5_1.json` | 11 MB | ~6 h of SEC-rate-limited fetches |
| Per-shard partial state | `cancel_10b5_1.delta_*.json` | 6 MB | same |
| Form 144 universe scan | `form144_scan.json` | 7 MB | ~3 h |
| Tender / 13E-3 scan | `tender_scan.json` | 1 MB | ~1 h |
| DEF 14A PSU + governance scan | `proxy_scan.json` + `proxy_scan.shard_*.json` | varies | ~6 h |
| Buyback verification | `buyback_verify.json` | — | ~30 min (yfinance) |
| yfinance overlay | `yfinance_quick.json` | — | ~20 min |
| Insider P-buys (raw Form 4) | `form4_buys.json` | — | hours |
| Event-sourced state DB | `pipeline.db` | 9 MB | derivable from above |
| Composite outputs | `unified_composite.json/.csv`, `psu_*.csv` | — | seconds (re-run) |
| Pinned ranked artifacts | `top_asymmetric.*`, `MOST_ASYMMETRIC.md`, etc. | — | analysis output |

Audit command:

```sh
find . -type f -size +1M -not -path './.git/*' \
  | while read f; do git ls-files --error-unmatch "$f" >/dev/null 2>&1 \
    && echo "TRACKED $f" || echo "AT-RISK $f"; done
```

As of `git rev-parse HEAD`: every file >=1 MB is TRACKED.

## What `.gitignore` excludes -- and why each is safe

| Pattern | Risk if lost | Safe because |
|---|---|---|
| `__pycache__/`, `*.pyc`, `*.pyo` | none | regenerated on import |
| `*.log` | low | rolled forward; status is also in JSON checkpoints |
| `.env`, `.venv/` | secret-bearing | must NEVER be committed |
| `.DS_Store` | none | macOS noise |
| `pipeline.db-shm`, `-wal` | none | SQLite WAL sidecars, checkpointed into `pipeline.db` |

## Filing-cache architecture (`.cache/docs/`)

The 26 GB filing cache lives only in `.git` packfiles, not in the
working tree. `cache_store.py` reads through three tiers:

1. `.cache/docs/<accession>.html` on the filesystem (fast path)
2. `git cat-file -p <commit>:.cache/docs/<accession>.html` against
   commits pinned in `cache_archive_commits.txt`
3. Caller falls through to EDGAR fetch

This keeps the working tree small (no disk-bloat on every clone) while
guaranteeing recoverability: pin commits are ancestors of the branch
head, so the blobs are GC-protected.

`CACHE_HTML=0` env disables tier-1 writes for disk-tight backfills
without affecting durability -- events extracted from HTML are the
durable product (pipeline.db + JSON), and the HTML itself remains in
git packs.

## Guard

`scripts/durability_guard.sh` enumerates every on-disk file >= 100 KB
and exits non-zero if any is gitignored or untracked (with a small
whitelist for transient noise). Run it before any major commit or as
a pre-stop check.

```sh
./scripts/durability_guard.sh
```

Current status: returns 0 (clean).

## How the other sandbox failed

A separate project lost hours of cached fundamentals because:
- `.cache/` was in `.gitignore`
- `results_*.csv`, `best_*.csv`, `universe_*.csv` were all in
  `.gitignore`
- A sandbox reset wiped them and only the Python source remained

This repo's `.gitignore` is intentionally narrow (only build artifacts
and secrets) and is documented in-file:

```
# .cache/ is now PERMANENT -- contains the immutable EDGAR doc cache
# (filings never change once filed; re-fetching wastes time and risks
# the SEC rate-limiter). Also contains scored row JSONs keyed by
# accession version.
```

## Recovery path if the working tree is destroyed

```sh
git clone <remote>/cyclepapa
cd cyclepapa
git checkout claude/create-new-feature-Oopqq

# All JSON/CSV artifacts are immediately available.
# To re-hydrate cached filings on demand (only as needed):
python3 -c "from cache_store import read_html; print(read_html('0001108524-26-000127')[:200])"
# -> resolves through tier 2 (git cat-file) without re-fetching SEC.
```

Last verified: 2026-06-14 -- exit 0 from durability_guard.sh on HEAD.
