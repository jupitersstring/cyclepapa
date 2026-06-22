#!/bin/bash
cd /home/user/cyclepapa
# Wait for widen_chain to finish
while pgrep -f "widen_chain\.sh\|queue_wider_markets" >/dev/null 2>&1; do
    sleep 120
done
echo "[followon] widen_chain done — running expansion pipeline"
bash scripts/run_expansion_pipeline.sh > /tmp/log_expansion.txt 2>&1
echo "[followon] expansion done — rebuilding rankings + workbook"
python3 scripts/master_synthesis_v2.py 2>&1 | tail -5
python3 scripts/full_universe_rank_all.py 2>&1 | tail -5
python3 scripts/build_workbook_full.py 2>&1 | tail -3
echo "[followon] DONE all"
