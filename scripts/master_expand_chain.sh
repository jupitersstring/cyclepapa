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

echo "[master] === phase 4: Qullamaggie + Episodic Pivot screens ==="
bash scripts/run_q_screens.sh

echo "[master] === phase 5: enduring compounder research (US + UK + EU small caps) ==="
for path in data/universes/us_nms.csv data/universes/uni_uk.csv \
            data/universes/uni_germany.csv data/universes/uni_france.csv \
            data/universes/uni_italy.csv data/universes/uni_spain.csv \
            data/universes/uni_japan.csv data/universes/uni_canada.csv \
            data/universes/uni_australia.csv; do
    [ -f "$path" ] || continue
    name=$(basename "$path" .csv | sed 's/uni_//; s/us_nms/us_nms/')
    out="data/research/roic_${name}.csv"
    n=$(($(wc -l < "$path") - 1))
    [ "$n" -lt 50 ] && continue
    # Skip if already done (file > 1MB or rows >= 80% of universe)
    if [ -f "$out" ] && [ "$(stat -c%s "$out" 2>/dev/null)" -gt 500000 ]; then
        rows=$(($(wc -l < "$out") - 1))
        if [ "$rows" -gt $((n * 70 / 100)) ]; then echo "[research] $name done, skipping"; continue; fi
    fi
    echo "[research] $name ($n tickers)"
    python3 scripts/pull_compounder_research.py --universe "$path" --out "$out" \
        --workers 10 --rate 1.4 --checkpoint 100 --resume \
        > "/tmp/log_research_${name}.txt" 2>&1 || true
done

echo "[master] === phase 6: rebuild rankings + workbook ==="
python3 scripts/master_synthesis_v2.py 2>&1 | tail -5
python3 scripts/full_universe_rank_all.py 2>&1 | tail -5
python3 scripts/integrate_q_into_ranking.py 2>&1 | tail -5
python3 scripts/rank_compounders.py 2>&1 | tail -10
python3 scripts/integrate_compounders.py 2>&1 | tail -5
python3 scripts/build_workbook_full.py 2>&1 | tail -3

echo "[master] DONE"
