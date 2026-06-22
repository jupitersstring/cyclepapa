#!/bin/bash
# Master orchestration: runs widen_chain → run_expansion → gap-fill → synth.
# Idempotent — safe to relaunch. Each phase checks completion.
set -e
cd "$(dirname "$0")/.."

echo "[master] === phase 1: widen_chain (new markets ex-India) ==="
bash scripts/widen_chain.sh

echo "[master] === phase 2: expansion pipeline (US/UK/EU broader) ==="
bash scripts/run_expansion_pipeline.sh

echo "[master] === phase 3: fundamental gap-fill (compute EV multiples from statements) ==="
python3 scripts/fill_fund_gaps.py 2>&1
for gapfile in data/universes/fund_gaps/uni_*_gap.csv; do
    [ -f "$gapfile" ] || continue
    mkt=$(basename "$gapfile" | sed 's/uni_\(.*\)_gap.csv/\1/')
    target="data/fundamentals/fund_${mkt}.csv"
    out_fill="data/fundamentals/fund_${mkt}_gapfill.csv"
    [ -f "$out_fill" ] && [ "$(stat -c%s "$out_fill" 2>/dev/null)" -gt 1000 ] && continue
    echo "[gapfill] $mkt — $(($(wc -l < "$gapfile") - 1)) tickers"
    python3 scripts/pull_fundamentals_v3.py \
        --universe "$gapfile" --out "$out_fill" \
        --workers 4 --rate 0.5 --checkpoint 50 --resume \
        > "/tmp/log_gapfill_${mkt}.txt" 2>&1 || true
    # Merge back: take v3 rows where ev_ebit OR ev_ebitda is now populated; replace in target
    python3 - << PY
import pandas as pd, os
target = '$target'
fill   = '$out_fill'
if not (os.path.exists(target) and os.path.exists(fill)): exit(0)
try:
    a = pd.read_csv(target); b = pd.read_csv(fill)
except Exception: exit(0)
# Keep b rows that have NEW EV data, replace matching tickers in a
b_useful = b[(b['ev_ebit'].notna()) | (b['ev_ebitda'].notna())]
if len(b_useful) == 0:
    print(f"  no new EV data recovered for $mkt"); exit(0)
# Drop overlapping cols in a, replace with b_useful
a = a[~a['ticker'].isin(b_useful['ticker'])]
# Align columns
for c in a.columns:
    if c not in b_useful.columns: b_useful[c] = None
b_useful = b_useful[a.columns.tolist() + [c for c in b_useful.columns if c not in a.columns]]
merged = pd.concat([a, b_useful], ignore_index=True, sort=False).drop_duplicates(subset='ticker', keep='last')
merged.to_csv(target, index=False)
print(f"  $mkt merged: +{len(b_useful)} new EV rows -> {len(merged)} total")
PY
    sleep 20
done

echo "[master] === phase 4: rebuild full rankings + workbook ==="
python3 scripts/master_synthesis_v2.py 2>&1 | tail -5
python3 scripts/full_universe_rank_all.py 2>&1 | tail -5
python3 scripts/build_workbook_full.py 2>&1 | tail -3

echo "[master] DONE"
