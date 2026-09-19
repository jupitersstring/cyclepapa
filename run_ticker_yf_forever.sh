#!/usr/bin/env bash
# Resilient driver for the Yahoo fundamentals enrichment + auto re-render.
#
# 1. Runs ticker_yf.py (resumable) until it reports "nothing to do" —
#    i.e. every universe ticker has been attempted. Restarts on any
#    crash (the IP throttle / container reaping can kill it mid-run);
#    each restart resumes from ticker_yf.csv with no data loss.
# 2. Once the enrichment list is exhausted, runs the apply + re-render
#    pipeline ONCE: merge authoritative Yahoo valuations into the
#    master, re-enrich, refresh archetypes, rebuild all workbooks.
# 3. Writes a sentinel so the heavy rebuild doesn't re-fire every session.
#
# Idempotent + restart-safe: apply_ticker_yf is gap-fill/overwrite and
# safe to re-run; if a rebuild is interrupted, the next session re-runs
# it (ticker_yf returns immediately, apply re-applies, rebuild redoes).
#
# Launch (done by the session-start hook):
#   setsid nohup ./run_ticker_yf_forever.sh > ticker_yf_driver.log 2>&1 &

set -uo pipefail
cd "$(dirname "$0")"

DRIVER_LOG=ticker_yf_driver.log
SENTINEL=.ticker_yf_rendered
PYTHON=python3
# Stragglers that keep 429-ing are not worth blocking the render on.
# Once <= this many remain (≈99.6% coverage) we proceed to render.
EXHAUST_THRESHOLD=150
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# Already rendered? Don't re-loop on a restart — the render is done.
if [ -f "$SENTINEL" ]; then
    echo "$(ts) driver: sentinel present, already rendered — exiting" >> "$DRIVER_LOG"
    exit 0
fi

# ---- Phase 1: enrich until the list is exhausted ----
ATTEMPT=0
while true; do
    ATTEMPT=$((ATTEMPT + 1))
    echo "$(ts) driver: ticker_yf run #$ATTEMPT" >> "$DRIVER_LOG"
    "$PYTHON" ticker_yf.py --rate 3 >> ticker_yf.log 2>&1
    RC=$?
    # ticker_yf exits 0 both on "nothing to do" and on a completed run.
    # Detect true exhaustion by asking it (dry): if todo == 0 it prints
    # "nothing to do" and exits 0 immediately.
    REMAINING=$("$PYTHON" - <<'PYEOF'
import pandas as pd, os
uni = pd.read_csv("asymmetry_global.csv")["symbol"].dropna().drop_duplicates()
done = set()
if os.path.exists("ticker_yf.csv"):
    try: done = set(pd.read_csv("ticker_yf.csv")["symbol"].dropna())
    except Exception: pass
print(len([s for s in uni if s not in done]))
PYEOF
)
    echo "$(ts) driver: rc=$RC remaining=$REMAINING" >> "$DRIVER_LOG"
    if [ "${REMAINING:-1}" -le "$EXHAUST_THRESHOLD" ]; then
        echo "$(ts) driver: enrichment exhausted (<=$EXHAUST_THRESHOLD remaining)" >> "$DRIVER_LOG"
        break
    fi
    # Crashed/throttled with work left — back off and resume
    sleep 15
done

# ---- Phase 2: apply + re-render (once) ----
# (audit #10) STAGED BUILD WITH FAIL-FAST. The old driver ignored every exit
# code, downgraded a methodology-audit FAILURE to a log line, kept rendering
# after a build failed, then `git add -A` + pushed whatever was on disk —
# i.e. it could PUBLISH PARTIAL OR BROKEN OUTPUT. Now every step's exit code
# is tracked; a failed audit or a failed build marks the run FAILED, and the
# commit/push at the end runs ONLY when every step succeeded.
set -o pipefail
FAILED=0
run_step() {   # run_step <label> <cmd...>  — logs, tracks failure, never aborts mid-run
    local label="$1"; shift
    echo "$(ts) driver: $label" >> "$DRIVER_LOG"
    if ! "$@" >> "$DRIVER_LOG" 2>&1; then
        echo "$(ts) driver: STEP FAILED — $label" >> "$DRIVER_LOG"
        FAILED=1
    fi
}
echo "$(ts) driver: applying Yahoo fundamentals + re-rendering" >> "$DRIVER_LOG"
run_step "apply_ticker_yf"        "$PYTHON" apply_ticker_yf.py
run_step "fill_asymmetry_gaps"    "$PYTHON" fill_asymmetry_gaps.py
run_step "derive_missing_columns" "$PYTHON" derive_missing_columns.py
run_step "rebuild_scores"         "$PYTHON" rebuild_scores.py   # FX+dedup+rescore
run_step "enrich (pre-tags)"      "$PYTHON" enrich_asymmetry_global.py
"$PYTHON" sec_insider_buys.py >> "$DRIVER_LOG" 2>&1 || true      # best-effort feed
run_step "archetype_tags"         "$PYTHON" archetype_tags.py
run_step "enrich (post-tags)"     "$PYTHON" enrich_asymmetry_global.py
# The methodology audit is a HARD GATE on the master the books will read.
run_step "methodology_audit (HARD GATE)" "$PYTHON" methodology_audit.py

echo "$(ts) driver: rebuilding workbooks" >> "$DRIVER_LOG"
for cmd in \
    "build_segment_detail_book.py" \
    "build_archetype_book.py" \
    "build_harvard_workbook.py" \
    "build_country_workbook.py" \
    "build_nms_book.py" \
    "build_nms_candidates_book.py" \
    "build_country_archetype_book.py --n 30" "build_country_archetype_inflection_book.py --n 30" \
    "build_otc_archetype_book.py --n 30" \
    "top_n_by_country.py --n 30 --out-csv top_n_by_country.csv --out-xlsx top_n_by_country.xlsx" \
    "top_n_by_country.py --n 30 --sort-by inflection --out-csv top_n_by_country_inflection.csv --out-xlsx top_n_by_country_inflection.xlsx" \
    "build_country_archetype_book.py --otc-mode otc --out country_archetype_book_otc.xlsx" \
    "build_country_archetype_book.py --n 30 --high-filter any --out country_archetype_52w_high.xlsx" \
    "build_country_archetype_inflection_book.py --otc-mode otc --out country_archetype_inflection_otc.xlsx" \
    "build_country_archetype_book.py --min-mcap 2e9 --min-names 10 --out country_archetype_midcap_plus.xlsx" \
    "build_country_archetype_inflection_book.py --min-mcap 2e9 --min-names 10 --out country_archetype_inflection_midcap_plus.xlsx" \
    "top_n_by_country.py --n 30 --otc-mode otc --out-csv top_n_otc.csv --out-xlsx top_n_otc.xlsx" \
    "top_n_by_country.py --n 30 --high-filter any --out-csv top_n_52w_high.csv --out-xlsx top_n_52w_high.xlsx" ; do
    run_step "build: $cmd" $PYTHON $cmd
done

if [ "$FAILED" -ne 0 ]; then
  # (audit #10) never publish a partial/broken render: no sentinel, no commit,
  # no push. Leave a FAILED marker so the next session sees it.
  date > "${SENTINEL}.FAILED"
  echo "$(ts) driver: RUN FAILED — one or more steps failed; NOT committing or pushing" >> "$DRIVER_LOG"
  exit 1
fi
rm -f "${SENTINEL}.FAILED"
date > "$SENTINEL"
echo "$(ts) driver: DONE — all steps succeeded; sentinel written" >> "$DRIVER_LOG"

# Persist the rendered outputs — this driver previously never committed,
# so a container reclaim silently discarded every re-rendered artifact.
# Reached ONLY when the audit passed and every build succeeded.
git add -A 2>/dev/null
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "Ticker-yf refresh: regenerate workbooks

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pk8K7QpC1m36MYjRwkTznS"
  for i in 1 2 3 4; do
    git push -q origin claude/yartseva-multibagger-database-lZS4a && break
    sleep $((2**i))
  done
fi
