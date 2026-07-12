#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# rebuild_all.sh — one-command regeneration of every derived deliverable.
#
# Runs the pipeline in dependency order. Each stage is OPTIONAL via flags so
# you can refresh just the cheap derived artifacts (default) or force the
# expensive network scans (--scans).
#
#   ./rebuild_all.sh            # derived-only: re-rank + rebuild workbooks
#   ./rebuild_all.sh --scans    # also refresh the slow EDGAR/yfinance scans
#   ./rebuild_all.sh --freshness  # just print per-layer data age
#
# Derived-only is safe to run anytime; it never hits the network and takes
# under a minute. Network scans are rate-limited and can take many minutes.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")"

run() { echo; echo "=== $* ==="; "$@"; }

DO_SCANS=0
case "${1:-}" in
  --scans)     DO_SCANS=1 ;;
  --freshness) python3 layer_freshness.py; exit 0 ;;
  "")          ;;
  *) echo "usage: $0 [--scans|--freshness]"; exit 1 ;;
esac

if [ "$DO_SCANS" = "1" ]; then
  echo "### Network scans (rate-limited; may take many minutes) ###"
  # Each is independently resumable; failures don't abort the rest.
  run python3 quarterly_10q_parse.py        --limit 200 || true
  run python3 net_net_ncav.py               --max-pb 1.5 || true
  run python3 voss_cic_triangulation.py     || true
  run python3 financial_primary_screen.py   || true
  run python3 form_13f_delta.py             --limit-filers 12 || true
  run python3 nport_forced_selling.py       --limit-funds 15 || true
  run python3 foreign_markets.py            || true
  run python3 biotech_pdufa_calendar.py     --days 365 --limit 300 || true
  run python3 activist_letter_feed.py       --days 90 || true
fi

echo "### Derived re-ranking (no network) ###"
run python3 layer_freshness.py             || true
run python3 full_universe_consensus.py     || true
run python3 full_universe_consensus_noval.py || true
run python3 grand_unified_ranker.py        || true
run python3 consensus_meta_ranker.py       || true
run python3 psu_universe_rank.py           || true
run python3 layer_correlation.py           || true
run python3 systematic_rankings.py         || true

echo "### Workbook regeneration ###"
run python3 build_most_asymmetric_xlsx.py  || true

echo
echo "=== rebuild complete ==="
echo "Artifacts:"
ls -la MOST_ASYMMETRIC.xlsx SYSTEMATIC_RANKINGS.md 2>/dev/null
