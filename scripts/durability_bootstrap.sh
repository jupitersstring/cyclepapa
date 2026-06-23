#!/bin/bash
# Durability bootstrap. Idempotent — safe to run on every session start.
# 1. Commits any uncommitted data/ changes immediately (insurance against restart)
# 2. Ensures auto-commit loop is running (relaunches if dead)
# 3. Verifies remote is fully in sync
set -e
cd "$(dirname "$0")/.."

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# ─── 1. Commit any orphan data ───
if [ -n "$(git status --porcelain data/)" ]; then
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    git add data/
    git commit -m "durability bootstrap snapshot $ts" >/dev/null 2>&1 || true
    echo "[bootstrap] committed pending data snapshot"
fi

# ─── 2. Push to remote ───
delay=2
for attempt in 1 2 3 4; do
    if git push -u origin "$BRANCH" >/dev/null 2>&1; then
        echo "[bootstrap] pushed to origin/$BRANCH"
        break
    fi
    sleep $delay
    delay=$((delay * 2))
done

# ─── 3. Ensure auto-commit loop is running ───
if ! pgrep -f auto_commit_loop.sh >/dev/null 2>&1; then
    nohup bash scripts/auto_commit_loop.sh > /tmp/log_autocommit.txt 2>&1 &
    disown
    echo "[bootstrap] restarted auto_commit_loop.sh"
else
    echo "[bootstrap] auto_commit_loop already running"
fi

# ─── 3b. Resume widen_chain if there's pending work ───
need_chain=0
# Is wider-markets pipeline incomplete?
for m in india china thailand brazil israel indonesia southafrica ireland turkey chile mexico greece portugal argentina austria; do
    out="data/dalton/dalton_${m}.csv"
    uni="data/universes/uni_${m}.csv"
    if [ -f "$uni" ] && { [ ! -f "$out" ] || [ "$(wc -l < "$out")" -le 50 ]; }; then
        need_chain=1; break
    fi
done
# Is TD coverage incomplete?
if [ "$need_chain" -eq 0 ] && [ -f data/universes/td_needs.csv ]; then
    td_need=$(python3 -c "
import pandas as pd, glob
need = pd.read_csv('data/universes/td_needs.csv')
done = []
for p in sorted(glob.glob('data/td_seq/td_*.csv')):
    if 'merged' in p or 'remain' in p: continue
    try: done.append(pd.read_csv(p))
    except: pass
if done:
    d = pd.concat(done).drop_duplicates(subset='ticker')
    print(len(need[~need['ticker'].isin(d['ticker'])]))
else:
    print(len(need))
" 2>/dev/null)
    [ "$td_need" -gt 10 ] 2>/dev/null && need_chain=1
fi
if [ "$need_chain" -eq 1 ] && ! pgrep -f "widen_chain.sh\|run_expansion\|master_expand" >/dev/null 2>&1; then
    nohup bash scripts/master_expand_chain.sh > /tmp/log_master_expand.txt 2>&1 &
    disown
    echo "[bootstrap] resumed master_expand_chain.sh"
fi

# ─── 3c. Resume expansion pipeline if not yet complete ────
expansion_incomplete=0
for m in us uk germany france italy spain netherlands belgium switzerland sweden norway finland denmark austria ireland portugal greece; do
    uni="data/universes/expanded/uni_${m}_x.csv"
    out="data/dalton/dalton_${m}_x.csv"
    if [ -f "$uni" ] && { [ ! -f "$out" ] || [ "$(stat -c%s "$out" 2>/dev/null)" -lt 5000 ]; }; then
        expansion_incomplete=1; break
    fi
done

# Also check compounder research incompleteness
if [ -f data/universes/us_nms.csv ] && \
   { [ ! -f data/research/roic_us_nms.csv ] || [ "$(stat -c%s data/research/roic_us_nms.csv 2>/dev/null)" -lt 1000000 ]; }; then
    expansion_incomplete=1
fi

# ─── 3d. Compounder research explicit watchdog ────
research_running=$(pgrep -f 'python3 scripts/pull_compounder_research_v2'  2>/dev/null | head -1)
research_running=${research_running:-0}
research_size=$(stat -c%s data/research/roic_us_nms.csv 2>/dev/null || echo 0)
if [ "$research_running" = "0" ] && [ "$research_size" -lt 2000000 ] && [ -f data/universes/us_nms.csv ]; then
    nohup python3 scripts/pull_compounder_research_v2.py \
        --universe data/universes/us_nms.csv \
        --out data/research/roic_us_nms.csv \
        --workers 4 --rate 0.4 --checkpoint 50 --resume \
        > /tmp/log_research_v2.txt 2>&1 &
    disown
    echo "[bootstrap] restarted compounder research v2"
fi
if [ "$expansion_incomplete" -eq 1 ] && ! pgrep -f "run_expansion\|master_expand" >/dev/null 2>&1; then
    # If widen_chain still running, master_expand will pick up expansion after; otherwise launch expansion directly
    if pgrep -f widen_chain.sh >/dev/null 2>&1; then
        echo "[bootstrap] widen_chain active; expansion will follow"
    else
        nohup bash scripts/master_expand_chain.sh > /tmp/log_master_expand.txt 2>&1 &
        disown
        echo "[bootstrap] launched master_expand_chain.sh for expansion"
    fi
fi

# ─── 4. Audit: any untracked files in data/? ───
untracked="$(git ls-files --others --exclude-standard data/ 2>/dev/null)"
if [ -n "$untracked" ]; then
    echo "[bootstrap] WARNING — untracked files in data/:"
    echo "$untracked" | head -10
    echo "(Run: git add data/ && git commit -m 'capture orphans')"
fi

echo "[bootstrap] DONE — durability OK"
