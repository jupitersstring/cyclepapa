# Audit Response

The earlier audit identified 21 issues across the analysis and pipeline.
This document tracks each, the fix applied, and how it can be verified.

## Score-distorting bugs (8 of 8 fixed)

| # | Issue | Fix | Verified by |
|---|---|---|---|
| 3 | Cross-quarter dedupe — same termination scored 3-4× | `dedupe_cross_quarter()` keyed on (action, NEO, role, shares, plan_type), keeps oldest | `test_cross_quarter_dedupe_keeps_oldest`, `MA 60→18`, `LCUT 40→10`, `BB 33→5`, sat ±80 dropped 15→13 |
| 6 | Corporate ASR / repurchase counted as insider conviction | `is_corporate` flag in `extract_context` discards passages with `accelerated share repurchase`, `ASR Agreement`, `share repurchase program`, `Company entered into`, etc. | `test_e2e_corporate_buyback_excluded` — TKO's 3.16M ASR no longer scores |
| 5 | Forward vs retrospective conditionalities not distinguished | `classify_direction()` returns forward / retro / ambiguous; scoring multiplies by 1.0 / 0.5 / 0.7 | `test_direction_*` — CCI "we achieved" → retro, HFFG "must have achieved" → forward |
| 4 | Hurdle ladder polluted by comp/ownership tables ($900 hurdle on $48 stock) | `psu_step_change.py` caps each hurdle at 8× current price, lists filtered count in reasons | `test_plausibility_gate_*` — EYE $26-$900 ladder filters down to real 3-tranche |
| 10 | NEO "Huang President", "Vice President" extracted as names | `neo_passes_sanity()` rejects names where last token is a role word (`president`, `chair`, `officer`, etc.) | `test_neo_sanity_rejects_role_tokens` |
| 11 | "No director adopted" boilerplate counted as event | `is_negative_boilerplate()` scans full paragraph; full-window check in `add_event` | `test_e2e_no_activity_disclosure`, `test_negative_boilerplate_filter` |
| 1 | Q4 events from 10-Ks completely missing | `scan_10k_extend.py` ran on all 1995 tickers, added 690 new events; v3.2 `recent_10q_for` now requests 10-Q + 10-K + 20-F + 6-K | CRM dropped #1→#36 because 10-K surfaced offsetting prior Benioff/Tallapragada adoptions invisible in 10-Q-only data |
| 2 | "No data" scored identically to "no activity" | `data_available` flag per ticker; `KNOWN_FPI` block in `unified_composite.py`; 203 FPIs now properly distinguished | AGBK, SRAD, ODTX, ONON, NXG all show `data_available=False` and `n_quarters=0` |

## Engineering (7 of 9 fixed)

| # | Issue | Fix |
|---|---|---|
| 7 | Four overlapping composite scorers | `unified_composite.py` with `SCHEMA_VERSION="v4-unified"`, single `insider_pack()`, single `NOISE_BLACKLIST` |
| 9 | yfinance enrichment covered only 40 tickers | `enrich_yfinance.py` resumable, source-driven; 428 tickers now have mcap/P/B/drawdown |
| 12 | Zero regression tests | 28 tests across `test_cancel_10b5_1.py` and `test_psu_pipeline.py`; `tests/run_all.sh` |
| 18 | Non-atomic JSON writes can corrupt on crash | `atomic_write_json()` via temp + rename |
| 19 | Extraction+scoring entangled (had to hand-strip `_complete` to re-score) | `--rescore-only` CLI flag + `rescore_v3.py` re-runs extraction in-memory from cached HTML |
| 20 | Untracked one-off bash heredocs | `unified_composite.py` and `finalize_universe_10b5_1.py` are committed scripts; key analysis is reproducible |
| 8 | Backtest of signal vs benchmark | `backtest_10b5_1.py` (SPY-relative) + `backtest_stratified.py` (role × size × age) |
| 13 | Atomic state on SQLite (deferred) | JSON works at 1995 entries; SQLite would help at 10× scale |
| 17 | 2.2 GB cache in git (now 26 GB after 10-K extension) | Cache batched-pushed in chunks ≤2 GB each. Long-term should move to LFS or object store |

## Caveats remaining (audit items #14, #15, #16)

- **Universe is selection-biased** (#14) — the 1995 tickers are the union of prior screens, not the full US listed market.
- **Form 4 data is one-sided** (#15) — we have P-buys but no open-market sells; "insider behaviour" is half a picture, partly patched by the 10b5-1 leg.
- **SEC rate-limit + UA** (#16) — `psu-alpha-research contact@example.com` is still the User-Agent. Should be a real contact per SEC fair-access policy. No 403s observed during the 4-shard scan, but the risk exists.

## Verification commands

```bash
cd /home/user/cyclepapa
./tests/run_all.sh                        # 28 unit tests
python3 unified_composite.py --min-score 15  # current rankings
python3 backtest_stratified.py --limit 50    # smoke test
```

## Backtest summary (v3.2 dataset, 500 events vs SPY at 180d)

| Bucket | n | mean excess | median excess | beat-SPY |
|---|---|---|---|---|
| **term_sell** (bullish) | 85 | **+17.6%** | **+7.0%** | 54% |
| **term_buy** (bearish) | 16 | **−30.3%** | **−30.5%** | 13% |
| **adopt_sell** (bearish) | 386 | +6.1% | **−12.2%** | 38% |
| adopt_buy | 13 | +17.9% | -9.0% | 39% |

## Stratified backtest (full 1,308 events, 180d horizon)

### By plan size — STRONGEST stratifier

| Size tier | Bucket | n | Mean excess | Median excess | Beat-SPY |
|---|---|---|---|---|---|
| **≥250K shares** | **term_sell** | 17 | **+62.1%** | **+27.2%** | **71%** |
| ≥250K shares | adopt_sell | 86 | +24.2% | −8.8% | 41% |
| 50K-250K | term_sell | 15 | +11.3% | −1.2% | 47% |
| 50K-250K | adopt_sell | 128 | +5.1% | −13.1% | 39% |
| <50K | term_sell | 25 | +22.1% | +21.4% | 72% |
| <50K | adopt_sell | 177 | +4.6% | −12.6% | 35% |

### By role tier

| Role | Bucket | n | Mean excess | Median excess | Beat-SPY |
|---|---|---|---|---|---|
| CEO/Chair | term_sell | 13 | +26.7% | −15.9% | 46% |
| **CFO** | **term_sell** | 10 | **+26.2%** | **+23.0%** | **60%** |
| Other | term_sell | 77 | +15.1% | +7.5% | 57% |
| CEO/Chair | adopt_sell | 92 | +11.3% | −11.6% | 38% |
| **CFO** | **adopt_sell** | 51 | **−8.0%** | **−21.3%** | **29%** |
| Other | adopt_sell | 303 | +11.6% | −11.1% | 40% |

### By time period — signal stability check

| Period | Bucket | n | Mean excess | Median excess | Beat-SPY |
|---|---|---|---|---|---|
| 2025 H1 | term_sell | 74 | +16.8% | +6.1% | 53% |
| 2025 H1 | adopt_sell | 331 | +7.5% | −12.6% | 37% |
| 2025 H2 | term_sell | 26 | +20.5% | +16.8% | 65% |
| 2025 H2 | adopt_sell | 114 | +14.3% | −11.6% | 43% |

Signal direction stable across both half-years; not a one-period artifact.

### Honest takeaways

1. **Plan size is the strongest stratifier, not role.** ≥250K-share
   sell-plan terminations show 71% beat-SPY rate and median excess
   +27% — the cleanest single bucket in the data.
2. **CEO/Chair termination is NOISIER than expected** (n=13, median
   excess −16% but mean +27%). Heavily right-skewed; some big wins
   dragged by losers. Contradicts the simple "founder cancellation = alpha"
   thesis.
3. **CFO termination IS predictive** (n=10, median +23% excess, 60%
   beat-SPY). Small sample but clean.
4. **CFO adoption is the strongest bearish signal** (n=51, median
   excess −21%, only 29% beat SPY). When a CFO commits to sell,
   underperformance is the most reliable.
5. **adopt_sell broadly bearish in median terms** across all role
   tiers and time periods — between −11% and −21% median excess at
   180d.

### What this DOESN'T tell us

- 2026 H1 events lack 180d forward data (return window not yet
  elapsed) so the most-recent signal can't be backtested directly.
- The 17 large-size term_sell events span ~5 tickers; not independent.
  Concentration risk in the alpha estimate.
- No transaction-cost, liquidity, or position-sizing model.
- Bull-market regime — bear-market behavior unverified.
- Universe is the union of prior screens, not full US market.
