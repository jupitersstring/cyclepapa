#!/bin/bash
# Disconnect-proof harvest finalizer.
#   • Ensures the segment harvest + backlog screener are running (resumes if dead)
#   • Waits for both to complete
#   • Rebuilds the full synthesis + archetypes workbook with the final data
#   • Commits & pushes
# Idempotent and safe to relaunch from the SessionStart bootstrap.
set -e
cd "$(dirname "$0")/.."

export EDGAR_IDENTITY="cyclepapa research cm2whv9sg2@privaterelay.appleid.com"
export REQUESTS_CA_BUNDLE=/root/.ccr/ca-bundle.crt
export SSL_CERT_FILE=/root/.ccr/ca-bundle.crt

SEG_UNI=data/universes/seg_priority.csv
SEG_OUT=data/research/segments_us.csv
BL_UNI=data/universes/sec_all.csv
BL_OUT=data/research/backlog_us.csv

ensure_segment() {
    if pgrep -f "segment_harvest.py" >/dev/null 2>&1; then return; fi
    [ -f "$SEG_UNI" ] || return
    # done? (rows >= 95% of universe)
    if [ -f "$SEG_OUT" ]; then
        rows=$(($(wc -l < "$SEG_OUT") - 1)); uni=$(($(wc -l < "$SEG_UNI") - 1))
        [ "$rows" -ge $((uni * 95 / 100)) ] && return
    fi
    nohup python3 scripts/segment_harvest.py --universe "$SEG_UNI" --out "$SEG_OUT" \
        --workers 8 --checkpoint 25 --resume > /tmp/log_segments.txt 2>&1 &
    disown
    echo "[finalizer] (re)started segment harvest"
}

ensure_backlog() {
    if pgrep -f "backlog_screen.py" >/dev/null 2>&1; then return; fi
    [ -f "$BL_UNI" ] || return
    if [ -f "$BL_OUT" ]; then
        rows=$(($(wc -l < "$BL_OUT") - 1)); uni=$(($(wc -l < "$BL_UNI") - 1))
        [ "$rows" -ge $((uni * 95 / 100)) ] && return
    fi
    nohup python3 scripts/backlog_screen.py --universe "$BL_UNI" --out "$BL_OUT" \
        --workers 6 --rate 7 --checkpoint 200 --resume > /tmp/log_backlog.txt 2>&1 &
    disown
    echo "[finalizer] (re)started backlog screener"
}

# Keep both alive until complete
while true; do
    ensure_segment
    ensure_backlog
    seg_done=0; bl_done=0
    if [ -f "$SEG_OUT" ]; then
        r=$(($(wc -l < "$SEG_OUT") - 1)); u=$(($(wc -l < "$SEG_UNI") - 1))
        [ "$r" -ge $((u * 95 / 100)) ] && ! pgrep -f segment_harvest.py >/dev/null && seg_done=1
    fi
    if [ -f "$BL_OUT" ]; then
        r=$(($(wc -l < "$BL_OUT") - 1)); u=$(($(wc -l < "$BL_UNI") - 1))
        [ "$r" -ge $((u * 95 / 100)) ] && ! pgrep -f backlog_screen.py >/dev/null && bl_done=1
    fi
    [ "$seg_done" -eq 1 ] && [ "$bl_done" -eq 1 ] && break
    sleep 120
done

echo "[finalizer] harvests complete — rebuilding synthesis + workbook"
python3 scripts/master_synthesis_v2.py        2>&1 | tail -3
python3 scripts/full_universe_rank_all.py      2>&1 | tail -2
python3 scripts/integrate_q_into_ranking.py    2>&1 | tail -1
python3 scripts/rank_compounders.py            2>&1 | tail -2
python3 scripts/integrate_compounders.py       2>&1 | tail -2
python3 scripts/build_archetypes.py            2>&1 | tail -2
python3 scripts/build_workbook_full.py         2>&1 | tail -2

# Commit final outputs
git add data/ 2>/dev/null || true
git commit -m "finalizer: complete segment + backlog harvest, rebuilt workbook" -q 2>&1 | tail -1 || true
delay=2
for a in 1 2 3 4; do
    git push -u origin "$(git rev-parse --abbrev-ref HEAD)" >/dev/null 2>&1 && break
    sleep $delay; delay=$((delay*2))
done
echo "[finalizer] DONE — full build pushed"
