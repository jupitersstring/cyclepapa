#!/usr/bin/env bash
# Driver for the Lynch "years of progress rewarded in a year" price-series
# enrichment (Squeeze & Release + Volatility Asymmetry on W/M/Q bars, plus
# 3.5y/10y ROC and ROC-of-ROC). One 10y-weekly chart request per name.
# SOLE Yahoo hitter — the rest deep drive is complete (.rest_rendered) and the
# price-refresh enrichers must stay paused while this runs. Priority order:
# fundamentally-advancing long-term laggards first (the Lynch population).
set -uo pipefail
cd "$(dirname "$0")"
LOG=lynch_driver.log
SENTINEL=.lynch_done
PY=python3
BRANCH=claude/yartseva-multibagger-database-lZS4a
ts() { date '+%Y-%m-%d %H:%M:%S'; }

[ -f "$SENTINEL" ] && { echo "$(ts) already done — exit" >> "$LOG"; exit 0; }

commit_progress() {
  git add lynch_reward_signals.csv lynch_attempts.json 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -q -m "Lynch reward signals progress: $(tail -n +2 lynch_reward_signals.csv 2>/dev/null | wc -l | tr -d ' ') names

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pk8K7QpC1m36MYjRwkTznS" 2>>"$LOG"
    for i in 1 2 3 4; do git push -q origin "$BRANCH" 2>>"$LOG" && break; sleep $((2**i)); done
  fi
}

ATT=0
while true; do
  ATT=$((ATT+1))
  echo "$(ts) lynch chunk #$ATT" >> "$LOG"
  "$PY" lynch_reward_enrich.py --rate 2.5 --limit 800 >> lynch_enrich.log 2>&1
  commit_progress
  REMAIN=$("$PY" - <<'PYEOF'
import pandas as pd, os, json
u = pd.read_csv("lynch_universe.csv")["symbol"].dropna().drop_duplicates()
done = set()
if os.path.exists("lynch_reward_signals.csv"):
    try: done = set(pd.read_csv("lynch_reward_signals.csv", usecols=["symbol"])["symbol"].dropna())
    except Exception: pass
att = {}
if os.path.exists("lynch_attempts.json"):
    try: att = json.load(open("lynch_attempts.json"))
    except Exception: att = {}
print(len([s for s in u if s not in done and att.get(s, 0) < 2]))
PYEOF
)
  echo "$(ts) remaining=$REMAIN" >> "$LOG"
  [ "${REMAIN:-1}" -le 50 ] && { echo "$(ts) exhausted" >> "$LOG"; break; }
  sleep 5
done
date > "$SENTINEL"
echo "$(ts) DONE" >> "$LOG"
