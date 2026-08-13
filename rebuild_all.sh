#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# rebuild_all.sh — one-command regeneration of every derived deliverable.
#
# Runs the pipeline in dependency order. Stages are gated by flags:
#
#   ./rebuild_all.sh            # derived-only: re-rank + rebuild workbooks
#   ./rebuild_all.sh --scans    # + refresh the medium EDGAR/yfinance legs
#   ./rebuild_all.sh --base     # + re-run the HEAVY foundational scans too
#   ./rebuild_all.sh --freshness  # just print per-layer data age
#
# Derived-only never hits the network and takes under a minute.
# --scans refreshes the ~15 medium legs (minutes each, rate-limited).
# --base additionally re-runs the foundational scanners (proxy_scan,
#   tender_scan, cancel_10b5_1, buyback_verify, form4/144) -- these are
#   HOURS-long, resumable, and rarely need a full refresh. Included so
#   NO prior-session workflow is silently omitted from the runner.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")"

run() { echo; echo "=== $* ==="; "$@"; }

DO_SCANS=0
DO_BASE=0
case "${1:-}" in
  --scans)     DO_SCANS=1 ;;
  --base)      DO_SCANS=1; DO_BASE=1 ;;
  --freshness) python3 layer_freshness.py; exit 0 ;;
  "")          ;;
  *) echo "usage: $0 [--scans|--base|--freshness]"; exit 1 ;;
esac

if [ "$DO_BASE" = "1" ]; then
  echo "### HEAVY foundational scans (hours; resumable) ###"
  # PSU forensics across the DEF 14A universe -- the largest single job.
  run python3 proxy_scan.py                 || true
  run python3 tender_scan.py                || true
  run python3 cancel_10b5_1.py              || true
  run python3 buyback_verify.py             || true
  run python3 form144_scan.py               || true
  # yfinance overlay refresh drives valuation for every downstream leg.
  run python3 enrich_yfinance.py            || true
fi

if [ "$DO_SCANS" = "1" ]; then
  echo "### Medium network legs (rate-limited; minutes each) ###"
  # Each is independently resumable; failures don't abort the rest.
  # -- Valuation / balance-sheet
  run python3 quarterly_10q_parse.py        --limit 200 || true
  run python3 net_net_ncav.py               --max-pb 1.5 || true
  run python3 financial_primary_screen.py   || true
  # -- Governance / M&A / activism
  run python3 voss_cic_triangulation.py     || true
  run python3 form_13f_delta.py             --limit-filers 12 || true
  run python3 activist_letter_feed.py       --days 90 || true
  # -- Forced-selling / flow
  run python3 nport_forced_selling.py       --limit-funds 15 || true
  # -- Special-situations family (all methodology-fixed legs)
  run python3 special_situations_extended.py || true
  run python3 recent_incentive_asymmetry.py --window-days 120 || true
  run python3 recent_incentive_asymmetry.py --window-days 30  || true
  run python3 turnaround_executive_leg.py   || true
  run python3 tender_odd_lot_and_mechanism.py || true
  run python3 bumpitrage_tender_decline.py  || true
  run python3 spinoff_volume_timer.py       --days 150 || true
  run python3 arquitos_subsidiary_anchor.py || true
  run python3 backstopped_rights_offering.py || true
  run python3 post_ch11_emergence.py        || true
  run python3 external_manager_internalization.py || true
  run python3 coval_stafford_proxy.py       || true
  # -- Non-US
  run python3 foreign_markets.py            || true
  run python3 biotech_pdufa_calendar.py     --days 365 --limit 300 || true
fi

echo "### Derived re-ranking (no network) ###"
run python3 layer_freshness.py             || true
# Archetype + governance scorers (pure-compute from proxy_scan) --
# these feed consensus_meta_ranker + systematic_rankings, so they
# run BEFORE the consensus stage.
run python3 psu_gov_asymmetry.py           || true
run python3 psu_archetypes_full.py         || true
# Reconstructed generators for the three formerly-frozen scorer CSVs
# (bastian_forcing, psu_valcreate, psu_asymmetric_full) -- also feed
# the consensus, so likewise BEFORE it.
run python3 gen_orphan_scorers.py          || true
# Form 4-derived insider scorers (pure-compute from form4_buys.json) --
# they write the JSONs consensus ingests, so run BEFORE it. Previously
# these were run by hand and their outputs frozen; wiring them here keeps
# the insider layers reachable and refreshed each build.
run python3 opportunistic_insiders.py      || true
run python3 discretionary_insider_conviction.py || true
run python3 buyback_insider_overlay.py     || true
# Emergence cross-feed from the pollers subsystem (skips gracefully if
# emergence_master_snapshot.json is absent; refresh the snapshot by
# copying data/emergence_master.json from the capital-structure branch).
run python3 emergence_crossfeed.py         || true
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
