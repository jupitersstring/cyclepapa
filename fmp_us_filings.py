"""US-filer layer from FMP's SEC-derived endpoints -> fmp_us_filings.csv (usf_*).

  historical-employee-count   employees per 10-K / 10-Q, filing-dated
      usf_emp                 latest reported headcount
      usf_emp_g1              growth vs the report ~1 year earlier
      usf_emp_age_days        days since that filing (freshness)
  insider-trading/statistics  per calendar quarter, usable 15 days after quarter end
      usf_ins_buy_quarters_4q quarters (of the last 4) with open-market purchases
      usf_ins_net_buy_4q      purchases - sales, last 4 quarters (transactions)
      usf_ins_buys_8q         purchases, last 8 quarters

Both endpoints are SEC-only, so this covers US filers (symbols without an
exchange suffix); non-US names carry NaN, and the archetypes that read these
treat them as extra evidence, never a requirement. Resumable batches.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_us_filings.csv"
COLS = ["symbol", "usf_emp", "usf_emp_g1", "usf_emp_age_days", "usf_ins_buy_quarters_4q", "usf_ins_net_buy_4q",
        "usf_ins_buys_8q"]
TODAY = pd.Timestamp(dt.date.today())


def _get(ep, params):
    for attempt in range(10):
        try:
            return fc.get_json(ep, params, ttl=fc.TTL_SLOW) or []
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                time.sleep(20 * (attempt + 1))
                continue
            return []
    return []


def one(sym: str) -> dict:
    rec = {"symbol": sym}
    e = pd.DataFrame(_get("historical-employee-count", {"symbol": sym, "limit": 100}))
    if len(e) and "employeeCount" in e.columns:
        e["avail"] = pd.to_datetime(e.get("filingDate"), errors="coerce")
        e["period"] = pd.to_datetime(e.get("periodOfReport"), errors="coerce")
        e["emp"] = pd.to_numeric(e["employeeCount"], errors="coerce")
        e = e.dropna(subset=["avail", "period", "emp"]).sort_values("period").drop_duplicates("period", keep="last")
        e = e[(e["emp"] > 0) & (e["avail"] <= TODAY)]
        if len(e):
            last = e.iloc[-1]
            rec["usf_emp"] = float(last["emp"])
            rec["usf_emp_age_days"] = float((TODAY - last["avail"]).days)
            ya = e[(e["period"] <= last["period"] - pd.Timedelta(days=300))
                   & (e["period"] >= last["period"] - pd.Timedelta(days=430))]
            if len(ya):
                rec["usf_emp_g1"] = float(last["emp"] / ya.iloc[-1]["emp"] - 1)
    ins = pd.DataFrame(_get("insider-trading/statistics", {"symbol": sym}))
    if len(ins) and {"year", "quarter"}.issubset(ins.columns):
        ins["avail"] = (pd.PeriodIndex.from_fields(year=ins["year"].astype(int), quarter=ins["quarter"].astype(int),
                                                   freq="Q").end_time.normalize() + pd.Timedelta(days=15))
        for c in ("totalPurchases", "totalSales"):
            ins[c] = pd.to_numeric(ins.get(c), errors="coerce").fillna(0)
        ins = ins[ins["avail"] <= TODAY].sort_values("avail")
        w8 = ins[ins["avail"] > TODAY - pd.Timedelta(weeks=104)]
        w4 = w8[w8["avail"] > TODAY - pd.Timedelta(days=365)]
        rec["usf_ins_buys_8q"] = float(w8["totalPurchases"].sum())
        rec["usf_ins_buy_quarters_4q"] = float((w4["totalPurchases"] > 0).sum())
        rec["usf_ins_net_buy_4q"] = float(w4["totalPurchases"].sum() - w4["totalSales"].sum())
    return rec


def main(workers: int = 4) -> None:
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol"], low_memory=False)["symbol"].astype(str)
    syms = [s for s in g.drop_duplicates() if "." not in s and "-" not in s]
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    print(f"us filings: {len(syms)} US symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    step = 1000
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), step):
            recs = list(ex.map(one, todo[i:i + step]))
            pd.DataFrame(recs).reindex(columns=COLS).to_csv(OUT, mode="a", header=not os.path.exists(OUT),
                                                            index=False)
            print(f"  {min(i + step, len(todo))}/{len(todo)} | hit_rate={fc.cache_stats()['hit_rate']}", flush=True)
    print("USF_DONE", flush=True)


if __name__ == "__main__":
    main()
