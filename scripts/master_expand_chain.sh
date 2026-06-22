#!/bin/bash
# Master orchestration: runs widen_chain → run_expansion → final synthesis.
# Idempotent — safe to relaunch. Each phase checks completion.
set -e
cd "$(dirname "$0")/.."

echo "[master] === phase 1: widen_chain (new markets ex-India) ==="
bash scripts/widen_chain.sh

echo "[master] === phase 2: expansion pipeline (US/UK/EU broader) ==="
bash scripts/run_expansion_pipeline.sh

echo "[master] === phase 3: rebuild full rankings + workbook ==="
python3 scripts/master_synthesis_v2.py 2>&1 | tail -5
python3 scripts/full_universe_rank_all.py 2>&1 | tail -5
python3 scripts/build_workbook_full.py 2>&1 | tail -3

echo "[master] DONE"
