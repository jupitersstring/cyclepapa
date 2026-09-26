"""Through-cycle durability columns from the CACHED FMP annual statements
(the same income / cash-flow calls fmp_statements.py makes: limit 8) ->
fmp_throughcycle.csv (tc_*). No new API calls for names already cached.

Why: the lindy / quality archetypes counted "4 of 5 good years", which FMP
fills turned into the base rate of profitable firms worldwide. Through-cycle
MINIMA (the worst year) and 7-of-8 durability describe what the docstrings
promise — durable, high, non-eroding — rather than "usually positive".

  tc_years               fiscal years available (<= 8)
  tc_fcf_pos / tc_opinc_pos   years with FCF > 0 / operating income > 0
  tc_min_opm, tc_med_opm operating margin: worst year / median
  tc_min_gm              gross margin, worst year (non-eroding pricing power)
  tc_min_ic              EBIT / interest expense, worst year with interest > 0
  tc_fcf_margin_avg      mean FCF / revenue
  tc_uncov_payout_3y     of the last 3 FYs, years where dividends + buybacks > FCF
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_throughcycle.csv"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def one(sym: str) -> dict:
    rec = {"symbol": sym}
    try:
        isr = fc.get_json("income-statement", {"symbol": sym, "period": "annual", "limit": 8},
                          ttl=fc.TTL_FUNDAMENTAL) or []
        cf = fc.get_json("cash-flow-statement", {"symbol": sym, "period": "annual", "limit": 8},
                         ttl=fc.TTL_FUNDAMENTAL) or []
    except fc.FMPError:
        return rec
    if not isr:
        return rec
    ccy = isr[0].get("reportedCurrency")
    I = {str(r.get("fiscalYear") or str(r.get("date"))[:4]): r for r in isr if r.get("reportedCurrency") == ccy}
    C = {str(r.get("fiscalYear") or str(r.get("date"))[:4]): r for r in cf if r.get("reportedCurrency") == ccy}
    yrs = sorted(I, reverse=True)
    rev = np.array([_f(I[y].get("revenue")) for y in yrs])
    op = np.array([_f(I[y].get("operatingIncome")) for y in yrs])
    gp = np.array([_f(I[y].get("grossProfit")) for y in yrs])
    ie = np.array([_f(I[y].get("interestExpense")) for y in yrs])
    fcf = np.array([_f((C.get(y) or {}).get("freeCashFlow")) for y in yrs])
    # an all-zero cash-flow year is FMP's placeholder, not a real zero
    blank = np.array([all(_f((C.get(y) or {}).get(k)) in (0.0,) or not math.isfinite(_f((C.get(y) or {}).get(k)))
                          for k in ("operatingCashFlow", "capitalExpenditure")) for y in yrs])
    fcf = np.where(blank, np.nan, fcf)
    pay = np.array([abs(_f((C.get(y) or {}).get("commonDividendsPaid")) or 0)
                    + abs(_f((C.get(y) or {}).get("commonStockRepurchased")) or 0) for y in yrs])
    ok = np.isfinite(rev) & (rev > 0)
    rec["tc_years"] = float(ok.sum())
    if ok.sum() < 3:
        return rec
    rec["tc_fcf_pos"] = float(np.nansum(fcf[ok] > 0))
    rec["tc_fcf_years"] = float(np.isfinite(fcf[ok]).sum())
    rec["tc_opinc_pos"] = float(np.nansum(op[ok] > 0))
    opm = op[ok] / rev[ok]
    opm = opm[np.isfinite(opm) & (np.abs(opm) <= 1.0)]
    if len(opm) >= 3:
        rec["tc_min_opm"], rec["tc_med_opm"] = float(opm.min()), float(np.median(opm))
    gm = gp[ok] / rev[ok]
    gm = gm[np.isfinite(gm) & (gm > 0) & (gm < 0.98)]          # 0 / ~100% = missing COGS
    if len(gm) >= 3:
        rec["tc_min_gm"] = float(gm.min())
    icv = op / ie
    icv = icv[np.isfinite(icv) & (ie > 0)]
    if len(icv) >= 3:
        rec["tc_min_ic"] = float(icv.min())
    fm = fcf[ok] / rev[ok]
    fm = fm[np.isfinite(fm)]
    if len(fm) >= 3:
        rec["tc_fcf_margin_avg"] = float(np.clip(fm, -1, 1).mean())
    last3 = [(p_, f_) for p_, f_ in zip(pay[:3], fcf[:3]) if math.isfinite(f_)]
    if len(last3) >= 2:
        rec["tc_uncov_payout_3y"] = float(sum(1 for p_, f_ in last3 if p_ > max(f_, 0) and p_ > 0))
    return rec


def main(workers: int = 8) -> None:
    syms = pd.read_csv("archetype_tags.csv", usecols=["symbol"], low_memory=False)["symbol"].astype(str).tolist()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(one, syms))
    d = pd.DataFrame(rows)
    d.to_csv(OUT, index=False, float_format="%.6g")
    print(f"wrote {OUT}: {len(d)} rows; with >=5 FYs: {int((d['tc_years'] >= 5).sum())}", flush=True)


if __name__ == "__main__":
    main()
