#!/bin/bash
# Rebuild every FMP-derived layer from the FILLED disk cache, then the master
# table (in place) and the books.
#
#   bash rebuild_from_cache.sh                 # everything
#   ONLY_MASTER=1 bash rebuild_from_cache.sh   # skip the engines, rebuild the master + books
#
# Why each piece is the way it is:
#  * The engines are resumable (a name already in their output is skipped), so
#    each output is MOVED ASIDE first (kept under $LOG_DIR/prev) and the whole
#    universe is recomputed from the cache. A failed engine is retried once;
#    if its output is still missing, the previous file is restored so the
#    master never loses a layer.
#  * The client's cache GC is DISABLED for every engine (--gc-max-mb 0): the
#    filled cache is the asset being read, and the client's own GC evicts the
#    least-recently-used entries whenever the volume has < 20 GB free.
#  * Two engine streams run in parallel (4 cores): the statement-based ones
#    (statements -> through-cycle -> quarterly -> quarterly-ext -> dynamics)
#    and the rest.
#  * The master is rebuilt IN PLACE through the same steps as the Yahoo driver
#    (apply_ticker_yf -> fill gaps -> derive -> rebuild_scores [FX, dedup,
#    profile fill, company map, freshness] -> enrich -> archetype_tags ->
#    enrich), never through the from-scratch ranker, which would drop the
#    appended expansion names. The master chain is fail-fast; the audit gate
#    then decides whether the books are rebuilt.
set -u
cd "$(dirname "$0")"
LOG_DIR=${REBUILD_LOG_DIR:-/tmp/rebuild_from_cache}
mkdir -p "$LOG_DIR/prev"
if [ -n "${FMP_ENV:-}" ] && [ -f "$FMP_ENV" ]; then set -a; . "$FMP_ENV"; set +a; fi
export PYTHONWARNINGS=ignore
PY=${PYTHON:-python3}
ts() { date -u +%FT%TZ; }
run() {   # run <label> <cmd...>: logs to $LOG_DIR/<label>.log; returns the command's rc
    local label="$1"; shift
    echo "$(ts) >>> $label"
    if nice -n 5 "$@" > "$LOG_DIR/$label.log" 2>&1; then
        echo "$(ts) ok   $label | $(tail -1 "$LOG_DIR/$label.log" | cut -c1-140)"; return 0
    fi
    echo "$(ts) FAIL $label"; tail -3 "$LOG_DIR/$label.log"; return 1
}
aside() { for f in "$@"; do [ -f "$f" ] && mv -f "$f" "$LOG_DIR/prev/$f"; done; return 0; }
engine() {   # engine <label> <outputs...> -- <cmd...>: move outputs aside, run, retry once, restore on failure
    local label="$1"; shift
    local outs=()
    while [ "$1" != "--" ]; do outs+=("$1"); shift; done; shift
    aside "${outs[@]}"
    if ! run "$label" "$@"; then
        echo "$(ts) retry $label (resumes from its checkpoint)"
        run "${label}_retry" "$@" || true
    fi
    local missing=0
    for f in "${outs[@]}"; do [ -s "$f" ] || missing=1; done
    if [ "$missing" = 1 ]; then
        echo "$(ts) RESTORE previous outputs for $label"
        for f in "${outs[@]}"; do [ -f "$LOG_DIR/prev/$f" ] && [ ! -s "$f" ] && cp -f "$LOG_DIR/prev/$f" "$f"; done
        echo "ENGINE_FAILED $label" >> "$LOG_DIR/engine_failures.txt"
    fi
}
: > "$LOG_DIR/engine_failures.txt"
echo "$(ts) rebuild_from_cache start | free $(df -h / | tail -1 | awk '{print $4}')"

if [ -z "${ONLY_MASTER:-}" ]; then
    run hydrate "$PY" fmp_hydrate_statements.py || true
    (
        engine statements    fmp_statements.csv     -- "$PY" fmp_statements.py --workers 2 --gc-max-mb 0
        engine throughcycle  fmp_throughcycle.csv   -- "$PY" fmp_throughcycle.py
        engine quarterly     fmp_quarterly.csv      -- "$PY" fmp_quarterly.py --workers 2 --gc-max-mb 0
        engine quarterly_ext fmp_quarterly_ext.csv  -- "$PY" fmp_quarterly_ext.py
        engine dynamics      fmp_dynamics.csv       -- "$PY" fmp_dynamics.py --gc-max-mb 0
        echo "$(ts) STREAM_A_DONE"
    ) > "$LOG_DIR/stream_A.log" 2>&1 &
    (
        engine enrich        fmp_enrichment.csv     -- "$PY" fmp_enrich.py --gc-max-mb 0
        engine segments      fmp_segments.csv fmp_segments_detail.csv fmp_segments_qdetail.csv -- "$PY" fmp_segments.py --workers 2 --gc-max-mb 0
        engine sentiment     fmp_sentiment.csv      -- "$PY" fmp_sentiment.py
        engine events        fmp_events.csv         -- "$PY" fmp_events.py
        engine ev_history    fmp_ev_history.csv     -- "$PY" fmp_ev_history.py --workers 2 --gc-max-mb 0
        engine financial_growth fmp_financial_growth.csv -- "$PY" fmp_financial_growth.py --workers 2 --gc-max-mb 0
        engine institutional fmp_institutional.csv  -- "$PY" fmp_institutional.py --gc-max-mb 0
        engine us_filings    fmp_us_filings.csv     -- "$PY" fmp_us_filings.py
        echo "$(ts) STREAM_B_DONE"
    ) > "$LOG_DIR/stream_B.log" 2>&1 &
    wait
    cat "$LOG_DIR/stream_A.log" "$LOG_DIR/stream_B.log"
    run ts_snapshot "$PY" ts_snapshot.py || true
    echo "$(ts) engines done | failures: $(wc -l < "$LOG_DIR/engine_failures.txt") | free $(df -h / | tail -1 | awk '{print $4}')"
fi

# ---- master table, in place, fail-fast ----
for step in "apply_ticker_yf:apply_ticker_yf.py" "fill_asymmetry_gaps:fill_asymmetry_gaps.py" \
            "derive_missing_columns:derive_missing_columns.py" "rebuild_scores:rebuild_scores.py" \
            "enrich_pre:enrich_asymmetry_global.py" "archetype_tags:archetype_tags.py" \
            "enrich_post:enrich_asymmetry_global.py"; do
    label=${step%%:*}; script=${step#*:}
    if ! run "$label" "$PY" "$script"; then
        echo "$(ts) MASTER CHAIN FAILED at $label — books not rebuilt"; echo "REBUILD_EXIT 1"; exit 1
    fi
done

# ---- audit gate + books (regen_all_books.sh: FROM_AUDIT skips its own tags/enrich) ----
echo "$(ts) >>> audit gate + books"
if FROM_AUDIT=1 bash regen_all_books.sh > "$LOG_DIR/books.log" 2>&1; then
    echo "$(ts) ok   books | $(grep -E 'METHODOLOGY AUDIT' "$LOG_DIR/books.log" | tail -1)"
else
    echo "$(ts) FAIL books"; grep -E "AUDIT GATE FAILED|  FAIL|FAILED" "$LOG_DIR/books.log" | head -12
    echo "REBUILD_EXIT 2"; exit 2
fi
echo "$(ts) rebuild_from_cache done | engine failures: $(wc -l < "$LOG_DIR/engine_failures.txt") | free $(df -h / | tail -1 | awk '{print $4}')"
echo "REBUILD_EXIT 0"
