#!/usr/bin/env bash
# Resilient driver for deep multi-year Tier-B enrichment of "the rest" — the
# main-universe names that still lack the deep schema (margin deltas, share
# counts, buybacks, normalized earnings, earnings-surprise streaks, 5-year
# price band). OTC has already been filled; this covers the ~26.6k investable
# main-universe names, enriched HIGHEST-ASYMMETRY FIRST so the most promising
# names get the deep fields early even though the full pass runs for a while.
#
# ticker_yf_deep is the SINGLE Yahoo hitter; no other enricher may run
# alongside it (three concurrent hitters starve each other on the shared-IP
# throttle — the failure that repeatedly killed OTC before the sole-hitter
# invariant was enforced).
#
# Phase 1: loop ticker_yf_deep over rest_expansion_universe.csv until exhausted.
# Phase 2: merge rest_expansion_yartseva.csv into the master (fill_gaps globs
#          *_yartseva.csv), re-derive, re-score, re-tag, regenerate all books.
# Sentinel-guarded, idempotent, commits progress each chunk.
set -uo pipefail
cd "$(dirname "$0")"

LOG=rest_driver.log
SENTINEL=.rest_rendered
PY=python3
EXHAUST=100
BRANCH=claude/yartseva-multibagger-database-lZS4a
ts() { date '+%Y-%m-%d %H:%M:%S'; }

[ -f "$SENTINEL" ] && { echo "$(ts) already rendered — exit" >> "$LOG"; exit 0; }

commit_progress() {
  git add rest_expansion_yartseva.csv rest_deep_attempts.json 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -q -m "Rest deep enrichment progress: $(tail -n +2 rest_expansion_yartseva.csv 2>/dev/null | wc -l | tr -d ' ') names" 2>>"$LOG"
    for i in 1 2 3 4; do
      git push -q origin "$BRANCH" 2>>"$LOG" && break
      sleep $((2**i))
    done
  fi
}

ATT=0
while true; do
  ATT=$((ATT+1))
  echo "$(ts) rest deep chunk #$ATT" >> "$LOG"
  "$PY" ticker_yf_deep.py --symbols-from rest_expansion_universe.csv \
        --out rest_expansion_yartseva.csv --attempts rest_deep_attempts.json \
        --rate 4 --limit 600 >> rest_enrich.log 2>&1
  commit_progress
  REMAIN=$("$PY" - <<'PYEOF'
import pandas as pd, os, json
u = pd.read_csv("rest_expansion_universe.csv")["symbol"].dropna().drop_duplicates()
done = set()
if os.path.exists("rest_expansion_yartseva.csv"):
    try: done = set(pd.read_csv("rest_expansion_yartseva.csv", usecols=["symbol"])["symbol"].dropna())
    except Exception: pass
att = {}
if os.path.exists("rest_deep_attempts.json"):
    try: att = json.load(open("rest_deep_attempts.json"))
    except Exception: att = {}
print(len([s for s in u if s not in done and att.get(s, 0) < 2]))
PYEOF
)
  echo "$(ts) remaining=$REMAIN" >> "$LOG"
  [ "${REMAIN:-1}" -le "$EXHAUST" ] && { echo "$(ts) exhausted" >> "$LOG"; break; }
  sleep 5
done

echo "$(ts) merging + re-rendering" >> "$LOG"
"$PY" fill_asymmetry_gaps.py        >> "$LOG" 2>&1
"$PY" derive_missing_columns.py     >> "$LOG" 2>&1
"$PY" rebuild_scores.py             >> "$LOG" 2>&1
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" sec_insider_buys.py 2>/dev/null || true; "$PY" archetype_tags.py >> "$LOG" 2>&1
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import pandas as pd, numpy as np
d = pd.read_csv("asymmetry_global.csv", low_memory=False).replace([np.inf,-np.inf], np.nan)
BANDS = {'fcf_yield':(-2,2),'dividend_yield':(0,1),'ev_ebitda':(-1000,1000),'ev_ebit':(-1000,1000),
         'ev_sales':(-500,500),'p_e':(-1000,1000),'p_s':(0,1000),'pb':(-500,500),'p_b':(-500,500),
         'owner_earnings_yield':(-2,2),'cfo_yield':(-2,3),'earnings_yield':(-2,2),'robust_cash_yield':(-2,2)}
for col,(lo,hi) in BANDS.items():
    if col in d.columns:
        bad = d[col].notna() & ((d[col] < lo) | (d[col] > hi))
        if bad.any(): d.loc[bad, col] = np.nan
d.to_csv("asymmetry_global.csv", index=False)
PYEOF

for cmd in \
  "build_segment_detail_book.py" "build_archetype_book.py" "build_harvard_workbook.py" \
  "build_country_workbook.py" "build_nms_book.py" "build_nms_candidates_book.py" \
  "build_country_archetype_book.py --n 30" "build_otc_archetype_book.py --n 30" \
  "top_n_by_country.py --n 30 --out-csv top_n_by_country.csv --out-xlsx top_n_by_country.xlsx" \
  "top_n_by_country.py --n 30 --sort-by inflection --out-csv top_n_by_country_inflection.csv --out-xlsx top_n_by_country_inflection.xlsx" ; do
  echo "$(ts)  $cmd" >> "$LOG"
  $PY $cmd >> "$LOG" 2>&1
done

date > "$SENTINEL"
git add asymmetry_global.csv archetype_tags.csv rest_expansion_yartseva.csv rest_deep_attempts.json \
  *.xlsx top_n_by_country.csv top_n_by_country_inflection.csv 2>/dev/null
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "Rest deep enrichment complete: merge + regenerate all books" 2>>"$LOG"
  for i in 1 2 3 4; do
    git push -q origin "$BRANCH" 2>>"$LOG" && break
    sleep $((2**i))
  done
fi
echo "$(ts) DONE" >> "$LOG"
