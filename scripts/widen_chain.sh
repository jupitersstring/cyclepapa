#!/bin/bash
cd /home/user/cyclepapa
echo "[chain] resuming TD on remaining 813..."
python3 screeners/td_sequential_screen.py \
    --universe data/universes/td_needs_remaining.csv \
    --out data/td_seq/td_full_universe_part2.csv \
    --hourly-days 60 --sleep 0.6 --checkpoint 50 \
    > /tmp/log_td_full_p2.txt 2>&1

echo "[chain] merging TD outputs..."
python3 -c "
import pandas as pd, glob
frames = [pd.read_csv(p) for p in glob.glob('data/td_seq/td_*.csv')]
merged = pd.concat(frames, ignore_index=True).drop_duplicates(subset='ticker', keep='first')
merged.to_csv('data/td_seq/td_full_merged.csv', index=False)
print(f'Total TD rows: {len(merged)}')
"

echo "[chain] launching wider-markets pipeline..."
bash scripts/queue_wider_markets.sh > /tmp/log_wider_full.txt 2>&1
echo "[chain] DONE all"
