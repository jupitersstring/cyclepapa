#!/bin/bash
# Daily refresh: the fast-moving feeds — insider trades (every Form 4 code,
# via FMP), Congress trades, 13D/G stakes, 8-K catalysts, prices and
# valuations — then the scores, the four books and the snapshot. The books'
# "What Changed" sheet compares against the last committed snapshot, so commit
# after each delivered build. The quarterly 13F roll is rebuild_13f.sh (run it
# once the 13F deadline, 45 days after quarter end, has passed).
#
#   bash pipeline/refresh_daily.sh
#
# Any failing step stops the chain, so a half-built DB is never rendered or
# snapshotted.
set -eo pipefail
cd "$(dirname "$0")/.."
step() {
  echo "=== $1"; shift
  "$@" 2>&1 | { grep -av "rate-limited" || true; } | tail -"${TAILN:-8}"
}
step insider_fmp python3 pipeline/ingest_insider_fmp.py        # every Form 4 code; buys/sells the SEC scan missed
step congress python3 pipeline/ingest_congress.py              # STOCK Act disclosures
step 13d python3 pipeline/refresh_13d_efts.py                  # 13D/G stakes, rolling 21 months
step 8k python3 pipeline/ingest_8k_sharded.py 1500             # M&A / control / dilution / bankruptcy items
step map_pb_tickers python3 pipeline/map_pb_tickers.py         # board companies -> listings (people monitor)
step enrich_fmp python3 pipeline/enrich_fmp.py                 # prices, valuations, profiles
step price_stats python3 pipeline/build_price_stats.py
step cluster python3 pipeline/cluster_detector.py
step entry_intact python3 pipeline/entry_intact.py             # vs-entry on today's price (read by the score)
step unified_score python3 pipeline/unified_score.py
step revealed_pref python3 pipeline/revealed_preference.py
step conviction python3 pipeline/conviction.py
step styles_view python3 pipeline/styles_view.py
step broker_swap_radar python3 pipeline/broker_swap_radar.py
TAILN=45 step validate python3 pipeline/validate.py
step render_universe python3 pipeline/render_universe_sheet.py
step render_style python3 pipeline/render_style_workbook.py
step render_people python3 pipeline/render_people_monitor.py
step render_broadsheet python3 pipeline/render_broadsheet.py
step snapshot python3 pipeline/snapshot.py dump
echo "=== DAILY REFRESH OK"
