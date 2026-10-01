#!/bin/bash
# Best-coverage FMP cache, in value order, resumable (every step is cache-aware):
#  1. standard bulk set (profile parts, ratios/key-metrics TTM, scores, peers, targets, statement list, latest statements, EOD)
#  2. statement bulk: 3 statements x (FY 2018-2025 + quarters 2023Q1-2026Q2)  (~66 calls, 429-paced)
#  3. per-symbol fills for every live name, highest-value sets first
# Usage: set -a; . <env with FMP_API_KEY>; set +a; nohup bash fmp_cache_programme.sh > cache_programme.log 2>&1 &
set -u
cd "$(dirname "$0")"
echo "=== 1/3 standard bulk set $(date -u +%FT%TZ)"
python fmp_bulk.py --what profile,ratios,keymetrics,scores,peers,targets,statements_list,latest_statements,eod
echo "=== 2/3 statement bulk $(date -u +%FT%TZ)"
python - <<'EOF'
import fmp_bulk as fb
periods = [(y, "FY") for y in range(2018, 2026)] + [(y, q) for y in (2023, 2024, 2025, 2026) for q in ("Q1", "Q2", "Q3", "Q4")
                                                   if not (y == 2026 and q in ("Q3", "Q4"))]
for ep in ("income-statement-bulk", "balance-sheet-statement-bulk", "cash-flow-statement-bulk"):
    for y, p in periods:
        try:
            d = fb.get_bulk_frame(ep, {"year": y, "period": p}, ttl=fb.TTL_MONTH)
            print(f"{ep} {y} {p}: {len(d):,}", flush=True)
        except Exception as exc:
            print(f"{ep} {y} {p}: FAILED {str(exc)[:120]}", flush=True)
EOF
echo "=== 3/3 per-symbol fills $(date -u +%FT%TZ)"
python fmp_fill_cache.py --workers 6 --sets estimates,keymetrics,ratios,growth,dividends,pt_news,grades_hist,earnings,ev_quarter,owner_earnings,seg_product,seg_geo,float,employees,exec_comp,insider_stats,splits,pt_summary,grades,ev_annual
echo "=== done $(date -u +%FT%TZ)"
