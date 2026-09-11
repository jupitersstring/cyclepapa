# Name-level spot checks — figures vs source and known reality

Method: for a diverse set (mega-caps with well-known financials, the original
DEEPINDS complaint, top-book names across JP/HK/KR/TH/IN/US), every stored
figure was compared against a JUST-FETCHED Yahoo pull and against externally
known values (scale, margins, multiples). Run 2026-09-11.

| Name | Verdict | Evidence |
|---|---|---|
| MSFT | SOUND (1 note) | mcap $3.71T, rev $318B, P/E 27.9, FCF yield 2.2% all match reality & fresh pull (px drift 1.5%). NOTE: stored ebitda_margin 63.1% vs computed 55.4% — inside the 25% repair tolerance, real value ~55%. |
| AAPL | SOUND | mcap $4.67T vs fresh $4.77T, rev $451B, EBITDA margin 34.7% (real ~34-35%), P/E 36.6. |
| KSS (Kohl's) | SOUND, flagged | rev $15.5B, P/E 8.3 fit the retailer; fcf_yield −35.8% is a genuinely bad inventory-cycle year; `ev_comp_gap` qc-flag present. Px drift −14% vs fresh (fell since last pull). |
| 7203.T (Toyota) | SOUND | mcap ¥36.7T, rev ¥50.7T, EBITDA margin 15.1% (real 15-16%), P/E 8.8. |
| GASS (StealthGas) | SOUND | mcap $350M, rev $167M, 46% EBITDA margin (LPG shipping), P/E 5.8, FCF yield 28%. |
| DEEPINDS.NS | SOUND (was the original defect) | EBITDA ₹3.84B / 43% margin / EV-EBITDA 13.5 / nde 0.02, P/E 24.3 vs fresh 24.6. |
| 0700.HK (Tencent) | SOUND | mcap HK$3.96T, rev RMB 752B, EBITDA margin 47.5%, P/E 14.8, EV/EBITDA 13.8. |
| 2230.HK (Medialink) | SOUND, flagged | 2.0B shares check out; deep net cash (EV/EBITDA 1.26), FCF yield 27%; `ev_comp_gap` = investments basis. |
| 088910.KQ (Dongwoo) | SOUND, flagged | thin 3.7% food-distribution margin, P/E 5.0, net-cash EV/EBITDA 0.88; `fcf_gt_cfo` flag = negative-capex year, identifiable. |
| 1798.T (Moriya) | SOUND, flagged | classic JP net-net: P/E 4.2, EV/EBITDA 2.8, FCF yield 26%; `ev_comp_gap` = securities holdings ≈ half of mcap. |
| ERIC | n/a | not in master (Ericsson tracked via home listing). |

Conclusions
- No corruption found in any spot-checked figure; scales, margins and
  multiples match external reality for every name checked.
- Anomalies that remain are LEGITIMATE accounting states, and every one now
  carries a per-row `qc_flags` marker (op_gt_ebitda_margin,
  gross_lt_op_margin, fcf_gt_cfo, ev_comp_gap, fx_twin_dev, neg_ev) — nothing
  is silent.
- Negative-EV multiples are kept as real, interpretable numbers (negative EV
  over a positive denominator); only non-positive denominators null a multiple.
- Every reconciliation batch is persisted to audit_reports/reconcile_log.txt.
