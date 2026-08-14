#!/usr/bin/env bash
# Resilient driver for deep multi-year enrichment of the broad OTC universe
# (US Pink / OTCQX / OTCQB names not already in the master). Mirrors
# run_deep_forever.sh: loop ticker_yf_deep until the OTC list is exhausted,
# then merge + re-render all books (including the OTC archetype book).
#
# ticker_yf_deep is the single Yahoo hitter; the price-refresh enrichers
# should be paused while this runs (three concurrent hitters starve each
# other on the shared-IP throttle).
set -uo pipefail
cd "$(dirname "$0")"

LOG=otc_driver.log
SENTINEL=.otc_rendered
PY=python3
EXHAUST=100
BRANCH=claude/yartseva-multibagger-database-lZS4a
ts() { date '+%Y-%m-%d %H:%M:%S'; }

[ -f "$SENTINEL" ] && { echo "$(ts) already rendered — exit" >> "$LOG"; exit 0; }

commit_progress() {
  git add otc_expansion_yartseva.csv otc_deep_attempts.json 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -q -m "OTC deep enrichment progress: $(tail -n +2 otc_expansion_yartseva.csv 2>/dev/null | wc -l | tr -d ' ') names" 2>>"$LOG"
    for i in 1 2 3 4; do
      git push -q origin "$BRANCH" 2>>"$LOG" && break
      sleep $((2**i))
    done
  fi
}

ATT=0
while true; do
  ATT=$((ATT+1))
  echo "$(ts) otc deep chunk #$ATT" >> "$LOG"
  "$PY" ticker_yf_deep.py --symbols-from otc_expansion_universe.csv \
        --out otc_expansion_yartseva.csv --attempts otc_deep_attempts.json \
        --rate 2.5 --limit 400 >> otc_enrich.log 2>&1
  commit_progress
  REMAIN=$("$PY" - <<'PYEOF'
import pandas as pd, os, json
u = pd.read_csv("otc_expansion_universe.csv")["symbol"].dropna().drop_duplicates()
done = set()
if os.path.exists("otc_expansion_yartseva.csv"):
    try: done = set(pd.read_csv("otc_expansion_yartseva.csv", usecols=["symbol"])["symbol"].dropna())
    except Exception: pass
att = {}
if os.path.exists("otc_deep_attempts.json"):
    try: att = json.load(open("otc_deep_attempts.json"))
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
"$PY" archetype_tags.py             >> "$LOG" 2>&1
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import pandas as pd, numpy as np
d = pd.read_csv("asymmetry_global.csv", low_memory=False).replace([np.inf,-np.inf], np.nan)
BANDS = {'fcf_yield':(-2,2),'dividend_yield':(0,1),'ev_ebitda':(-1000,1000),'ev_ebit':(-1000,1000),
         'ev_sales':(-500,500),'p_e':(-1000,1000),'p_s':(0,1000),'pb':(-500,500),
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
git add asymmetry_global.csv archetype_tags.csv otc_expansion_yartseva.csv otc_deep_attempts.json \
  *.xlsx top_n_by_country.csv top_n_by_country_inflection.csv 2>/dev/null
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "OTC deep enrichment complete: merge + regenerate all books" 2>>"$LOG"
  for i in 1 2 3 4; do
    git push -q origin "$BRANCH" 2>>"$LOG" && break
    sleep $((2**i))
  done
fi
echo "$(ts) DONE" >> "$LOG"
