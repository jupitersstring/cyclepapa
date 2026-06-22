#!/bin/bash
# Wait for widen_chain.sh + queue_wider_markets.sh to fully finish, then run
# the US/UK/EU expansion pipeline and rebuild rankings + workbook.
cd /home/user/cyclepapa

while true; do
    a=$(pgrep -f 'widen_chain\.sh' | wc -l)
    b=$(pgrep -f 'queue_wider_markets\.sh' | wc -l)
    if [ "$a" -eq 0 ] && [ "$b" -eq 0 ]; then break; fi
    sleep 120
done
echo "[followon] widen_chain finished — launching expansion pipeline"
bash scripts/run_expansion_pipeline.sh > /tmp/log_expansion.txt 2>&1

echo "[followon] expansion done — rebuilding rankings + workbook"
python3 scripts/master_synthesis_v2.py 2>&1 | tail -5
python3 scripts/full_universe_rank_all.py 2>&1 | tail -5
python3 scripts/build_workbook_full.py 2>&1 | tail -3

echo "[followon] DONE all"
