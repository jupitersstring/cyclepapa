"""Per-share compounding history from FMP `financial-growth` (annual) -> fmp_financial_growth.csv (fg_*).

Every fiscal-year row carries 3 / 5 / 10-year CUMULATIVE per-share growth of
revenue, net income, operating cash flow, shareholders' equity and dividends
per share, plus the diluted share-count growth. One call per symbol (annual,
limit 12), global. The per-share measure is the one Mayer / Tillinghast /
Lynch / O'Neil mean by "growth": a serial issuer growing revenue on issuance
does not compound per share.

Latest-FY levels (cumulative, and converted to CAGR):
  fg_fy_date, fg_ccy, fg_n_fy
  fg_rev_ps_3y / 5y / 10y, fg_ni_ps_3y / 5y / 10y, fg_ocf_ps_3y / 5y / 10y,
  fg_eq_ps_3y / 5y / 10y, fg_dps_5y                (cumulative)
  fg_rev_ps_5y_cagr, fg_ni_ps_3y_cagr, fg_ocf_ps_5y_cagr, fg_eq_ps_5y_cagr
  fg_shares_dil_g1, fg_bvps_g1, fg_eps_dil_g1, fg_rev_g1, fg_ocf_g1, fg_fcf_g1,
  fg_rd_g1, fg_sga_g1                              (latest FY vs prior)
Consistency across the last five FY rows (the A2 B.14 "held in every window" tier):
  fg_rev_ps_5y_min5       minimum of the 5-year per-share revenue growth over the last 5 FY rows
  fg_ocf_ps_5y_min5       same for operating cash flow per share
  fg_rev_ps_3y_pos_share5 share of the last 5 FY rows with 3-year per-share revenue growth > 0
  fg_bvps_up_share5       share of the last 5 FY rows with book value per share up
  fg_shares_dil_g_max3    maximum diluted share growth over the last 3 FY rows (dilution spikes)
"""
from __future__ import annotations

import argparse
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_financial_growth.csv"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _cagr(x, n):
    return (1.0 + x) ** (1.0 / n) - 1.0 if np.isfinite(x) and x > -1.0 else np.nan


def pack(rows: list) -> dict:
    rec: dict = {}
    if not rows:
        return rec
    r = sorted(rows, key=lambda z: z.get("date", ""), reverse=True)
    r = [z for z in r if str(z.get("period", "FY")).upper() in ("FY", "")]
    if not r:
        return rec
    z0 = r[0]
    rec["fg_fy_date"] = z0.get("date"); rec["fg_ccy"] = z0.get("reportedCurrency"); rec["fg_n_fy"] = float(len(r))
    m = {"rev": "RevenueGrowthPerShare", "ni": "NetIncomeGrowthPerShare", "ocf": "OperatingCFGrowthPerShare",
         "eq": "ShareholdersEquityGrowthPerShare"}
    for k, tag in m.items():
        for h, pre in (("3y", "threeY"), ("5y", "fiveY"), ("10y", "tenY")):
            rec[f"fg_{k}_ps_{h}"] = _f(z0.get(pre + tag))
    rec["fg_dps_5y"] = _f(z0.get("fiveYDividendperShareGrowthPerShare"))
    rec["fg_rev_ps_5y_cagr"] = _cagr(rec["fg_rev_ps_5y"], 5)
    rec["fg_ni_ps_3y_cagr"] = _cagr(rec["fg_ni_ps_3y"], 3)
    rec["fg_ocf_ps_5y_cagr"] = _cagr(rec["fg_ocf_ps_5y"], 5)
    rec["fg_eq_ps_5y_cagr"] = _cagr(rec["fg_eq_ps_5y"], 5)
    rec["fg_shares_dil_g1"] = _f(z0.get("weightedAverageSharesDilutedGrowth"))
    rec["fg_bvps_g1"] = _f(z0.get("bookValueperShareGrowth"))
    rec["fg_eps_dil_g1"] = _f(z0.get("epsdilutedGrowth"))
    rec["fg_rev_g1"] = _f(z0.get("revenueGrowth"))
    rec["fg_ocf_g1"] = _f(z0.get("operatingCashFlowGrowth"))
    rec["fg_fcf_g1"] = _f(z0.get("freeCashFlowGrowth"))
    rec["fg_rd_g1"] = _f(z0.get("rdexpenseGrowth"))
    rec["fg_sga_g1"] = _f(z0.get("sgaexpensesGrowth"))
    last5 = r[:5]
    rev5 = np.array([_f(z.get("fiveYRevenueGrowthPerShare")) for z in last5])
    ocf5 = np.array([_f(z.get("fiveYOperatingCFGrowthPerShare")) for z in last5])
    rev3 = np.array([_f(z.get("threeYRevenueGrowthPerShare")) for z in last5])
    bv = np.array([_f(z.get("bookValueperShareGrowth")) for z in last5])
    sh3 = np.array([_f(z.get("weightedAverageSharesDilutedGrowth")) for z in r[:3]])
    if np.isfinite(rev5).sum() >= 3:
        rec["fg_rev_ps_5y_min5"] = float(np.nanmin(rev5))
    if np.isfinite(ocf5).sum() >= 3:
        rec["fg_ocf_ps_5y_min5"] = float(np.nanmin(ocf5))
    if np.isfinite(rev3).sum() >= 3:
        rec["fg_rev_ps_3y_pos_share5"] = float(np.nanmean(rev3 > 0))
    if np.isfinite(bv).sum() >= 3:
        rec["fg_bvps_up_share5"] = float(np.nanmean(bv > 0))
    if np.isfinite(sh3).any():
        rec["fg_shares_dil_g_max3"] = float(np.nanmax(sh3))
    return rec


def enrich_symbol(sym: str) -> dict:
    rows = fc.get_json("financial-growth", {"symbol": sym, "period": "annual", "limit": 12},
                       ttl=fc.TTL_FUNDAMENTAL)
    rec = {"symbol": sym}
    rec.update(pack(rows or []))
    return rec


def _flush(rows):
    if not rows:
        return
    new = pd.DataFrame(rows)
    if os.path.exists(OUT):
        old = pd.read_csv(OUT, low_memory=False)
        new = pd.concat([old, new], ignore_index=True).drop_duplicates("symbol", keep="last")
    tmp = OUT + ".tmp"; new.to_csv(tmp, index=False, float_format="%.6g"); os.replace(tmp, OUT)


def universe(min_mcap: float) -> list[str]:
    t = pd.read_csv("archetype_tags.csv", usecols=["symbol", "archetype_count"], low_memory=False)
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "market_cap_usd"], low_memory=False)
    m = t.merge(g, on="symbol", how="left")
    m = m[pd.to_numeric(m["market_cap_usd"], errors="coerce") >= min_mcap]
    return m.sort_values("archetype_count", ascending=False)["symbol"].astype(str).tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--min-mcap", type=float, default=10e6)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--checkpoint-every", type=int, default=250)
    ap.add_argument("--gc-max-mb", type=int, default=3500)
    args = ap.parse_args()
    syms = universe(args.min_mcap)
    if args.max:
        syms = syms[: args.max]
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    print(f"financial-growth: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)

    def _one(sym):
        for attempt in range(12):
            try:
                return enrich_symbol(sym)
            except fc.FMPError as exc:
                if "Limit Reach" in str(exc) or "429" in str(exc):
                    time.sleep(30 * (attempt + 1)); continue
                return {"symbol": sym}
        raise fc.FMPError(f"{sym}: still rate limited after 12 waits")

    recs = []; step = args.checkpoint_every
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for b0 in range(0, len(todo), step):
            batch = todo[b0:b0 + step]
            try:
                recs.extend(ex.map(_one, batch))
            except fc.FMPError as exc:
                print(f"  rate limited near {b0}: {exc}; checkpointing", flush=True); break
            _flush(recs); recs = []
            st = fc.cache_stats()
            print(f"  fg {b0 + len(batch)}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb and (b0 // step) % 20 == 0:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    _flush(recs)
    n = len(pd.read_csv(OUT, usecols=["symbol"])) if os.path.exists(OUT) else 0
    print(f"wrote {OUT}: {n} rows", flush=True)


if __name__ == "__main__":
    main()
