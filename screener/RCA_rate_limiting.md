# RCA: Yahoo rate limiting on wide-universe screens

## Symptom

On the 7,223-ticker US+global run, whole stage-1 chunks came back
`YFRateLimitError` (153/200, then 195/200 tickers lost per chunk) and
stage 1 ended with 1,277 tickers unpriced. Stage 2 hit intermittent
429s/`Invalid Crumb` on fundamentals endpoints.

## Root cause analysis (5 whys)

1. **Why did requests fail?** Yahoo returned 429: the client exceeded its
   per-IP/session request budget.
2. **Why was the budget exceeded?** Burst concurrency (chunks of 200 with
   `threads=True` → up to 200 simultaneous chart calls) on top of a large
   sustained volume (~7.2k chart calls in stage 1, ~5 statement calls per
   survivor in stage 2).
3. **Why was the volume so large relative to the data actually needed?**
   The pipeline repeated identical fetches across passes: stage 2
   checkpointed only *passing* rows, so every evaluated-but-failing name
   was re-fetched (5 calls each) on every `--resume`; delisted tickers
   were re-queried every pass despite failing deterministically;
   (pre-fix) stage 1 re-downloaded legitimately-filtered names each pass.
4. **Why were fetches repeated?** Checkpoints recorded terminal successes
   only — not every *evaluated outcome* — so the scheduler had no memory
   of dead branches.
5. **Why did the limiter window keep extending?** Pacing was non-adaptive:
   a fixed (originally zero) backoff meant the client kept hammering
   inside the penalty window, resetting it.

## Framing: assembly theory

Treat the finished dataset as an assembled object. Its **assembly index**
is the minimum number of HTTP requests that could produce it (one price
history per live ticker, one statement set per survivor). The failure
mode was a realized assembly path far above that minimum: a high **copy
number** of identical requests (re-fetched failures, guaranteed-404
delistings, re-downloaded filtered names) plus burst re-assembly inside
the rate-limit penalty window. The fix is to make the realized path
converge on the assembly index: memoize every assembled intermediate,
prune branches proven dead, and pace construction to the provider's
budget.

## Fixes (mapped to causes)

| Cause | Fix |
|---|---|
| Re-fetched stage-2 failures (why 3/4) | Checkpoint **every evaluated ticker** with a `passed` flag; resume skips all of them. Old passers-only checkpoints are upgraded in place. |
| Guaranteed-dead re-fetches (why 3) | Stage-1 fails ledger (`.ckpt_prices_fails.parquet`): a ticker missing from `--max-fails` (default 3) otherwise-healthy chunks is marked dead and skipped. Misses inside rate-limited chunks are censored observations and are **not** counted. |
| Burst concurrency (why 2) | `--chunk-size` default 200 → 100; `--threads` bounds yfinance download concurrency (default 8). |
| Non-adaptive pacing (why 5) | Stage 1: exponential backoff 90 → 180 → 360 → 600 s (cap) on rate-limited chunks, reset on a healthy chunk. Stage 2: 60 s doubling to 600 s cap, retrying the *same* ticker (it was never fetched), giving up after 8 consecutive hits so a pass always terminates. |

## Residual risk

Yahoo's budget is finite and opaque; a very wide first pass will still
brush the limiter. But each `--resume` pass now assembles only blocks
that are genuinely missing, so successive passes shrink geometrically
instead of re-paying the full request cost.
