#!/usr/bin/env bash
# Resilient driver for the deep multi-year enrichment of the FDB-expansion
# names, then merge + re-render.
#
# ticker_yf_deep is the SINGLE Yahoo hitter here (it fetches statements +
# quote + chart per name), so we don't run ticker_yf / yahoo_chart_fill
# alongside it — three concurrent hitters just starve each other on the
# shared-IP throttle.
#
# Phase 1: loop ticker_yf_deep until the expansion list is exhausted.
# Phase 2: merge fdb_expansion_yartseva.csv into the master (fill_gaps
#          globs *_yartseva.csv), re-derive, re-enrich, re-tag, regenerate
#          all workbooks. Sentinel-guarded, idempotent.
set -uo pipefail
cd "$(dirname "$0")"

LOG=deep_driver.log
SENTINEL=.deep_rendered
PY=python3
EXHAUST=100
ts() { date '+%Y-%m-%d %H:%M:%S'; }

[ -f "$SENTINEL" ] && { echo "$(ts) already rendered — exit" >> "$LOG"; exit 0; }

ATT=0
while true; do
  ATT=$((ATT+1))
  echo "$(ts) deep run #$ATT" >> "$LOG"
  "$PY" ticker_yf_deep.py --rate 2.5 >> deep_enrich.log 2>&1
  REMAIN=$("$PY" - <<'PYEOF'
import pandas as pd, os, json
u = pd.read_csv("fdb_expansion_universe.csv")["symbol"].dropna().drop_duplicates()
done = set()
if os.path.exists("fdb_expansion_yartseva.csv"):
    try: done = set(pd.read_csv("fdb_expansion_yartseva.csv", usecols=["symbol"])["symbol"].dropna())
    except Exception: pass
att = {}
if os.path.exists("fdb_deep_attempts.json"):
    try: att = json.load(open("fdb_deep_attempts.json"))
    except Exception: att = {}
# "remaining" = names neither enriched nor retired (attempts < 3)
print(len([s for s in u if s not in done and att.get(s, 0) < 3]))
PYEOF
)
  echo "$(ts) remaining=$REMAIN" >> "$LOG"
  [ "${REMAIN:-1}" -le "$EXHAUST" ] && { echo "$(ts) exhausted" >> "$LOG"; break; }
  sleep 15
done

echo "$(ts) merging + re-rendering" >> "$LOG"
"$PY" fill_asymmetry_gaps.py        >> "$LOG" 2>&1
"$PY" derive_missing_columns.py     >> "$LOG" 2>&1
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" archetype_tags.py             >> "$LOG" 2>&1
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import pandas as pd, numpy as np
d = pd.read_csv("asymmetry_global.csv")
d.replace([np.inf,-np.inf], np.nan).to_csv("asymmetry_global.csv", index=False)
PYEOF

for cmd in \
  "build_segment_detail_book.py" "build_archetype_book.py" "build_harvard_workbook.py" \
  "build_country_workbook.py" "build_nms_book.py" "build_nms_candidates_book.py" \
  "top_n_by_country.py --n 30 --out-csv top_n_by_country.csv --out-xlsx top_n_by_country.xlsx" \
  "top_n_by_country.py --n 30 --sort-by inflection --out-csv top_n_by_country_inflection.csv --out-xlsx top_n_by_country_inflection.xlsx" ; do
  echo "$(ts)  $cmd" >> "$LOG"
  $PY $cmd >> "$LOG" 2>&1
done

date > "$SENTINEL"
echo "$(ts) DONE" >> "$LOG"
