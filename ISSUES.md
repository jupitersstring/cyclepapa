# Known Issues & Engineering Audit

Status of the issues raised in the May-2026 pipeline audit. ✅ fixed · 🟡 partial · ⬜ open · ❌ won't-do (by request)

## A. Could change conclusions
| # | Issue | Status |
|---|-------|--------|
| 1 | UK pence/GBP units | ✅ **Not a bug** — empirically verified `marketCap`/`EV`/FCF are all GBP (`financialCurrency`); price is pence but only used as a ratio. PAGE.L 22% is a real normalised-FCF effect. Added a currency-field guard + median 5y FCF (robust to M&A spikes). |
| 2 | `pass_bb` logic (`>=4% \| >0` made threshold a no-op) | ✅ Fixed — strict `>= min_buyback`; `--active-ok` to relax. |
| 3 | Direction semantics (RVOL/raw VOL up-cross mislabeled bullish) | ✅ Fixed — breadth now counts **directional** dims only (PRICE/PARTIC/SHARPE/ASYM); VOLUME & VOLAT are context, not summed. |
| 4 | Partial **weekly** bar included | ✅ Fixed — `drop_incomplete_last` drops the in-progress bar for all timeframes. |
| 5 | Stale, never-refreshing caches; mixed as-of dates | 🟡 Write-time sanitize + tombstones added; **refresh-existing-by-date path still open**. |
| 6 | CEFs/BDCs/preferreds leaking into "quality" | ✅ FCF screen excludes banks/insurers/REITs/CEFs/BDCs/non-equity via `quoteType`/sector/industry. (MCI was a CEF — strike it.) |
| 7 | UK insider = coverage gap reported as "no buying" | 🟡 Documented (yfinance has no UK director-dealing); correct phrasing is "unknown". Needs RNS source. |
| 8 | Survivorship bias in seasonal stats | ⬜ Open (acknowledged; needs point-in-time universe). |
| 9 | Stale market-cap buckets | 🟡 FCF screen now reports `computed_cap` from live mktcap; universe selection still uses fd tag. |

## B. Methodology
| # | Issue | Status |
|---|-------|--------|
| 10 | No multiplicity control / null on seasonal | ❌ (permutation/FDR) — out of scope by request |
| 11 | VA-GPR saturates at 10 | ⬜ Open |
| 12 | No out-of-sample validation | ❌ backtest — out of scope by request |
| 13 | Bandpass on raw price | ✅ Fixed — log price everywhere. |
| 14 | No hysteresis; 3 divergent crossing impls | ✅ Fixed — single `signals.latest_crossing` with hysteresis; covered by tests. |
| 15 | No sector/market neutralization | ❌ out of scope by request |
| 16 | `settled` guard dropped in breadth | ✅ Fixed — breadth respects `settled`. |
| 17 | Insider scan not size-norm/plan-aware | 🟡 Manual offering-vs-conviction check done; not yet systematic. |

## C. Engineering
| # | Issue | Status |
|---|-------|--------|
| 18 | Cache contamination patched at read-time | ✅ Write-time sanitize; one-time clean run removed ~1.6M NaN rows from weekly cache. |
| 19 | No failure tombstones | ✅ `dead_<interval>.json` — dead tickers never re-attempted. |
| 20 | DRY violations / magic numbers | 🟡 Crossing logic unified in `signals.py`; thresholds still scattered. |
| 21 | Stale hardcoded `--today` | ✅ Fixed — derives week from data's latest bar. |
| 22 | No tests/CI | 🟡 `tests/test_signals.py` (Pine parity, hysteresis, bar-drop). Metrics edge-case tests still open. |
| 23 | Outputs not reproducible | 🟡 `results/` + `run_scan.py` orchestrator added; reports now committable. |
| 24 | Fragile background jobs | ⬜ Open (use managed runner only). |
| 25 | Single-vendor fundamentals | ⬜ Open (yfinance only; load-bearing picks hand-verified). |

## Conclusions to downgrade pending open items
- **MCI** — it's a closed-end fund; **strike from longs**.
- UK "no insider buying" statements → **"unknown"** (data gap, not negative).
- Any **seasonal-only** name without corroboration from the other screens.
- Most robust (multi-screen + hand-verified fundamentals): **HCC, CRL, URBN, BOC, SMPL, MPAA/ULBI/OSUR** clusters — though signal *weights* remain unvalidated (P5/P6 declined).
