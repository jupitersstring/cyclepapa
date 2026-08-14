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

# Commit accumulated enrichment so it survives container re-clones. The
# output files are tracked (removed from .gitignore) precisely so a
# mid-flight restart resumes from committed progress rather than zero.
commit_progress() {
  git add fdb_expansion_yartseva.csv fdb_deep_attempts.json 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -q -m "Deep enrichment progress: $(tail -n +2 fdb_expansion_yartseva.csv 2>/dev/null | wc -l | tr -d ' ') names" 2>>"$LOG"
    for i in 1 2 3 4; do
      git push -q origin claude/yartseva-multibagger-database-lZS4a 2>>"$LOG" && break
      sleep $((2**i))
    done
  fi
}

ATT=0
while true; do
  ATT=$((ATT+1))
  echo "$(ts) deep chunk #$ATT" >> "$LOG"
  # Bounded chunk so we commit every few minutes; caps data-loss on a
  # restart to one chunk. --limit slices the todo list per invocation.
  "$PY" ticker_yf_deep.py --rate 2.5 --limit 400 >> deep_enrich.log 2>&1
  commit_progress
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
# "remaining" = names neither enriched nor retired. MUST match the
# enricher's --max-attempts (default 2) or names stuck at the cap are
# counted as remaining forever and the driver never reaches exhaust.
MAX_ATTEMPTS = 2
print(len([s for s in u if s not in done and att.get(s, 0) < MAX_ATTEMPTS]))
PYEOF
)
  echo "$(ts) remaining=$REMAIN" >> "$LOG"
  [ "${REMAIN:-1}" -le "$EXHAUST" ] && { echo "$(ts) exhausted" >> "$LOG"; break; }
  sleep 5
done

echo "$(ts) merging + re-rendering" >> "$LOG"
"$PY" fill_asymmetry_gaps.py        >> "$LOG" 2>&1
"$PY" derive_missing_columns.py     >> "$LOG" 2>&1
"$PY" rebuild_scores.py            >> "$LOG" 2>&1   # FX+dedup+rescore (audit fix)
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" archetype_tags.py             >> "$LOG" 2>&1
"$PY" enrich_asymmetry_global.py    >> "$LOG" 2>&1
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import pandas as pd, numpy as np
d = pd.read_csv("asymmetry_global.csv", low_memory=False)
d = d.replace([np.inf, -np.inf], np.nan)
# Plausibility clamp: nano/micro-caps with near-zero market cap produce
# absurd ratios (e.g. fcf_yield of 190,000x) that would spuriously inflate
# composite scores. Null values outside sane bands rather than clamp-to-edge
# so they create no fake signal. (~138 fcf_yield outliers observed.)
BANDS = {
    'fcf_yield': (-2.0, 2.0), 'dividend_yield': (0.0, 1.0),
    'owner_earnings_yield': (-2.0, 2.0), 'cfo_yield': (-2.0, 3.0),
    'earnings_yield': (-2.0, 2.0), 'robust_cash_yield': (-2.0, 2.0),
    'ev_ebitda': (-1000, 1000), 'ev_ebit': (-1000, 1000),
    'ev_sales': (-500, 500), 'p_e': (-1000, 1000), 'p_s': (0, 1000),
    'p_b': (-500, 500), 'pb': (-500, 500),
}
for col, (lo, hi) in BANDS.items():
    if col in d.columns:
        bad = d[col].notna() & ((d[col] < lo) | (d[col] > hi))
        if bad.any():
            print(f"  clamp: nulled {int(bad.sum())} out-of-band {col}", flush=True)
            d.loc[bad, col] = np.nan
d.to_csv("asymmetry_global.csv", index=False)
PYEOF

for cmd in \
  "build_segment_detail_book.py" "build_archetype_book.py" "build_harvard_workbook.py" \
  "build_country_workbook.py" "build_nms_book.py" "build_nms_candidates_book.py" \
  "build_country_archetype_book.py --n 30" \
  "build_otc_archetype_book.py --n 30" \
  "top_n_by_country.py --n 30 --out-csv top_n_by_country.csv --out-xlsx top_n_by_country.xlsx" \
  "top_n_by_country.py --n 30 --sort-by inflection --out-csv top_n_by_country_inflection.csv --out-xlsx top_n_by_country_inflection.xlsx" ; do
  echo "$(ts)  $cmd" >> "$LOG"
  $PY $cmd >> "$LOG" 2>&1
done

date > "$SENTINEL"

# Commit + push the merged master + regenerated workbooks so the final
# result survives a container re-clone.
git add asymmetry_global.csv archetype_tags.csv \
  fdb_expansion_yartseva.csv fdb_deep_attempts.json \
  asymmetry_country_workbook.xlsx asymmetry_harvard_workbook.xlsx asymmetry_nms_book.xlsx \
  top_by_archetype_book.xlsx nms_multibagger_candidates.xlsx segment_detail_book.xlsx \
  top_n_by_country.xlsx top_n_by_country_inflection.xlsx country_archetype_book.xlsx otc_archetype_book.xlsx \
  top_n_by_country.csv top_n_by_country_inflection.csv 2>/dev/null
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "Deep enrichment complete: merge + regenerate all workbooks" 2>>"$LOG"
  for i in 1 2 3 4; do
    git push -q origin claude/yartseva-multibagger-database-lZS4a 2>>"$LOG" && break
    sleep $((2**i))
  done
fi
echo "$(ts) DONE" >> "$LOG"
