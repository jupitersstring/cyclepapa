#!/usr/bin/env bash
# SECOND enricher for the rest drive — works a DISJOINT tail slice of the
# universe (rest_expansion_universe_b.csv) into its OWN output file
# (rest_expansion_b_yartseva.csv, still globbed by *_yartseva.csv on merge)
# and its OWN attempts file. Runs alongside the primary run_rest_deep.sh to
# roughly halve wall-clock on the remaining names.
#
# Two processes = two hitters on the shared IP, so each runs at a CONSERVATIVE
# rate (2/s cap, ~1/s actual latency-bound) → ~2/s aggregate, well under the
# threshold that bit the 3-hitter OTC run. Enrich-only: NO render here (the
# primary driver renders once at exhaustion). Commits its own progress.
set -uo pipefail
cd "$(dirname "$0")"
LOG=rest_driver_b.log
PY=python3
BRANCH=claude/yartseva-multibagger-database-lZS4a
ts() { date '+%Y-%m-%d %H:%M:%S'; }

commit_progress() {
  git add rest_expansion_b_yartseva.csv rest_deep_attempts_b.json 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -q -m "Rest deep enrichment (B) progress: $(tail -n +2 rest_expansion_b_yartseva.csv 2>/dev/null | wc -l | tr -d ' ') names" 2>>"$LOG"
    for i in 1 2 3 4; do git push -q origin "$BRANCH" 2>>"$LOG" && break; sleep $((2**i)); done
  fi
}

ATT=0
while true; do
  ATT=$((ATT+1))
  echo "$(ts) B chunk #$ATT" >> "$LOG"
  "$PY" ticker_yf_deep.py --symbols-from rest_expansion_universe_b.csv \
        --out rest_expansion_b_yartseva.csv --attempts rest_deep_attempts_b.json \
        --rate 2 --limit 400 >> rest_enrich_b.log 2>&1
  commit_progress
  REMAIN=$("$PY" - <<'PYEOF'
import pandas as pd, os, json
u = pd.read_csv("rest_expansion_universe_b.csv")["symbol"].dropna().drop_duplicates()
done = set()
if os.path.exists("rest_expansion_b_yartseva.csv"):
    try: done = set(pd.read_csv("rest_expansion_b_yartseva.csv", usecols=["symbol"])["symbol"].dropna())
    except Exception: pass
att = {}
if os.path.exists("rest_deep_attempts_b.json"):
    try: att = json.load(open("rest_deep_attempts_b.json"))
    except Exception: att = {}
print(len([s for s in u if s not in done and att.get(s, 0) < 2]))
PYEOF
)
  echo "$(ts) B remaining=$REMAIN" >> "$LOG"
  [ "${REMAIN:-1}" -le 20 ] && { echo "$(ts) B exhausted" >> "$LOG"; break; }
  sleep 5
done
echo "$(ts) B DONE" >> "$LOG"
