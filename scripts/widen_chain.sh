#!/bin/bash
# Resumable chain: TD remaining + wider-markets pipeline + rebuild ranking.
# IDEMPOTENT — safe to relaunch after a container restart. Each step checks
# whether work is already complete via existing output files.
set -e
cd "$(dirname "$0")/.."

# ─── Step 1: TD on tickers still missing data ─────────────────────────────
python3 - << 'PY'
import pandas as pd, os, glob
need = pd.read_csv('data/universes/td_needs.csv')
done_frames = []
for p in sorted(glob.glob('data/td_seq/td_*.csv')):
    if 'merged' in p or 'remain' in p: continue
    try: done_frames.append(pd.read_csv(p))
    except: pass
done = (pd.concat(done_frames, ignore_index=True).drop_duplicates(subset='ticker')
        if done_frames else pd.DataFrame({'ticker':[]}))
remain = need[~need['ticker'].isin(done['ticker'])]
remain.to_csv('data/universes/td_remain_current.csv', index=False)
print(f'TD: {len(done)} done, {len(remain)} remaining')
PY

remain_n=$(($(wc -l < data/universes/td_remain_current.csv) - 1))
if [ "$remain_n" -gt 5 ]; then
    next=2
    while [ -f "data/td_seq/td_full_universe_part${next}.csv" ]; do next=$((next+1)); done
    out="data/td_seq/td_full_universe_part${next}.csv"
    echo "[chain] TD on $remain_n remaining → $out"
    python3 screeners/td_sequential_screen.py \
        --universe data/universes/td_remain_current.csv \
        --out "$out" \
        --hourly-days 60 --sleep 0.6 --checkpoint 50
fi

# Merge all TD parts
python3 - << 'PY'
import pandas as pd, glob
frames = []
for p in sorted(glob.glob('data/td_seq/td_*.csv')):
    if 'merged' in p or 'remain' in p: continue
    try: frames.append(pd.read_csv(p))
    except: pass
if frames:
    merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset='ticker', keep='first')
    merged.to_csv('data/td_seq/td_full_merged.csv', index=False)
    print(f'[chain] TD merged: {len(merged)} unique')
PY

# ─── Step 2: Wider-markets pipeline (has its own skip logic) ──────────────
echo "[chain] wider-markets pipeline"
bash scripts/queue_wider_markets.sh

# ─── Step 3: Rebuild full-universe ranking ────────────────────────────────
echo "[chain] rebuilding full-universe ranking"
python3 scripts/master_synthesis_v2.py 2>&1 | tail -5
python3 scripts/full_universe_rank.py 2>&1 | tail -5
python3 scripts/build_workbook.py 2>&1 | tail -3

echo "[chain] DONE all"
