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
echo "$(ts) driver: applying Yahoo fundamentals + re-rendering" >> "$DRIVER_LOG"
"$PYTHON" apply_ticker_yf.py >> "$DRIVER_LOG" 2>&1
"$PYTHON" fill_asymmetry_gaps.py >> "$DRIVER_LOG" 2>&1
"$PYTHON" derive_missing_columns.py >> "$DRIVER_LOG" 2>&1
"$PYTHON" rebuild_scores.py >> "$DRIVER_LOG" 2>&1   # FX+dedup+rescore (audit fix)
"$PYTHON" methodology_audit.py >> "$DRIVER_LOG" 2>&1 || echo "METHODOLOGY AUDIT FAILED — books may reflect broken measures" >> "$DRIVER_LOG"
"$PYTHON" enrich_asymmetry_global.py >> "$DRIVER_LOG" 2>&1
"$PYTHON" sec_insider_buys.py 2>/dev/null || true; "$PYTHON" archetype_tags.py >> "$DRIVER_LOG" 2>&1
"$PYTHON" enrich_asymmetry_global.py >> "$DRIVER_LOG" 2>&1

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
    "top_n_by_country.py --n 30 --otc-mode otc --out-csv top_n_otc.csv --out-xlsx top_n_otc.xlsx" \
    "top_n_by_country.py --n 30 --high-filter any --out-csv top_n_52w_high.csv --out-xlsx top_n_52w_high.xlsx" ; do
    echo "$(ts) driver:   $cmd" >> "$DRIVER_LOG"
    $PYTHON $cmd >> "$DRIVER_LOG" 2>&1
done

date > "$SENTINEL"
echo "$(ts) driver: DONE — sentinel written" >> "$DRIVER_LOG"

# Persist the rendered outputs — this driver previously never committed,
# so a container reclaim silently discarded every re-rendered artifact.
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
