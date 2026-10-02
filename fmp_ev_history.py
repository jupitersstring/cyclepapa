"""Dated enterprise-value series from FMP `enterprise-values` (quarterly) -> fmp_ev_history.csv (evh_*).

The engine has inferred multiple compression as "sales growth minus price
return"; this reads the multiple itself, dated. Each quarter-end EV (FMP:
market cap - cash + debt, listing currency) is paired with the TTM revenue and
TTM operating income ending at that date from the cached quarterly panel
(reporting currency). The LEVEL of EV/Sales therefore carries the currency
mix of an ADR or a GBp line; the CHANGE over time does not, and the change is
what the derating / re-rating archetypes read.

  evh_ev_date, evh_ev_now, evh_mcap_now, evh_ev_mcap_ratio   (sanity: EV / mcap)
  evh_ev_sales_now, evh_ev_sales_1y, evh_ev_sales_2y, evh_ev_sales_3y
  evh_evs_log_chg_1y / 2y / 3y     log(EV/Sales now / then): negative = the multiple compressed
  evh_ev_ebit_now, evh_ev_ebit_1y, evh_ev_ebit_log_chg_1y   (both EBIT > 0 only)
  evh_evs_med_3y                   median EV/Sales over the quarters on file (own-history frame)
  evh_evs_vs_med_3y                log(now / median)
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

OUT = "fmp_ev_history.csv"
PANEL = "fmp_quarterly_panel.parquet"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _ttm_at(q: pd.DataFrame, d: pd.Timestamp, col: str):
    """Sum of the last four quarterly values ending within (d-400d, d+20d]."""
    w = q[(q["date"] <= d + pd.Timedelta(days=20)) & (q["date"] > d - pd.Timedelta(days=400))]
    w = w.tail(4)
    if len(w) < 4:
        return np.nan
    v = pd.to_numeric(w[col], errors="coerce")
    return float(v.sum()) if v.notna().all() else np.nan


def pack(ev_rows: list, q: pd.DataFrame | None) -> dict:
    rec: dict = {}
    if not ev_rows or q is None or not len(q):
        return rec
    e = pd.DataFrame(ev_rows)
    e["date"] = pd.to_datetime(e.get("date"), errors="coerce")
    e["ev"] = pd.to_numeric(e.get("enterpriseValue"), errors="coerce")
    e["mcap"] = pd.to_numeric(e.get("marketCapitalization"), errors="coerce")
    e = e.dropna(subset=["date", "ev"]).sort_values("date")
    if not len(e):
        return rec
    e["rev_ttm"] = [_ttm_at(q, d, "revenue") for d in e["date"]]
    e["ebit_ttm"] = [_ttm_at(q, d, "opinc") for d in e["date"]]
    e["evs"] = np.where((e["ev"] > 0) & (e["rev_ttm"] > 0), e["ev"] / e["rev_ttm"], np.nan)
    e["eve"] = np.where((e["ev"] > 0) & (e["ebit_ttm"] > 0), e["ev"] / e["ebit_ttm"], np.nan)
    now = e.iloc[-1]
    rec["evh_ev_date"] = now["date"].date().isoformat()
    rec["evh_ev_now"] = _f(now["ev"]); rec["evh_mcap_now"] = _f(now["mcap"])
    if np.isfinite(rec["evh_mcap_now"]) and rec["evh_mcap_now"] > 0:
        rec["evh_ev_mcap_ratio"] = rec["evh_ev_now"] / rec["evh_mcap_now"]
    rec["evh_ev_sales_now"] = _f(now["evs"]); rec["evh_ev_ebit_now"] = _f(now["eve"])

    def _at(years):
        target = now["date"] - pd.DateOffset(years=years)
        w = e[(e["date"] >= target - pd.Timedelta(days=60)) & (e["date"] <= target + pd.Timedelta(days=60))]
        if not len(w):
            return None
        return w.iloc[(w["date"] - target).abs().argsort().iloc[0]]

    for y in (1, 2, 3):
        then = _at(y)
        if then is None:
            continue
        rec[f"evh_ev_sales_{y}y"] = _f(then["evs"])
        if np.isfinite(rec["evh_ev_sales_now"]) and np.isfinite(_f(then["evs"])) and then["evs"] > 0:
            rec[f"evh_evs_log_chg_{y}y"] = math.log(rec["evh_ev_sales_now"] / then["evs"])
        if y == 1:
            rec["evh_ev_ebit_1y"] = _f(then["eve"])
            if np.isfinite(rec["evh_ev_ebit_now"]) and np.isfinite(_f(then["eve"])) and then["eve"] > 0:
                rec["evh_ev_ebit_log_chg_1y"] = math.log(rec["evh_ev_ebit_now"] / then["eve"])
    evs = pd.to_numeric(e["evs"], errors="coerce").dropna()
    if len(evs) >= 6:
        med = float(evs.median()); rec["evh_evs_med_3y"] = med
        if np.isfinite(rec["evh_ev_sales_now"]) and med > 0:
            rec["evh_evs_vs_med_3y"] = math.log(rec["evh_ev_sales_now"] / med)
    return rec


def enrich_symbol(sym: str, q: pd.DataFrame | None) -> dict:
    rows = fc.get_json("enterprise-values", {"symbol": sym, "period": "quarter", "limit": 13},
                       ttl=fc.TTL_FUNDAMENTAL)
    rec = {"symbol": sym}
    rec.update(pack(rows or [], q))
    return rec


def _flush(rows):
    if not rows:
        return
    new = pd.DataFrame(rows)
    if os.path.exists(OUT):
        old = pd.read_csv(OUT, low_memory=False)
        new = pd.concat([old, new], ignore_index=True).drop_duplicates("symbol", keep="last")
    tmp = OUT + ".tmp"; new.to_csv(tmp, index=False, float_format="%.6g"); os.replace(tmp, OUT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--min-mcap", type=float, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--checkpoint-every", type=int, default=250)
    ap.add_argument("--gc-max-mb", type=int, default=3500)
    args = ap.parse_args()
    t = pd.read_csv("archetype_tags.csv", usecols=["symbol", "archetype_count"], low_memory=False)
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "market_cap_usd"], low_memory=False)
    m = t.merge(g, on="symbol", how="left")
    if args.min_mcap > 0:   # 0 = every name, incl. those with no market cap yet
        m = m[pd.to_numeric(m["market_cap_usd"], errors="coerce") >= args.min_mcap]
    syms = m.sort_values("archetype_count", ascending=False)["symbol"].astype(str).tolist()
    if args.max:
        syms = syms[: args.max]
    panel = pd.read_parquet(PANEL, columns=["symbol", "date", "period", "revenue", "opinc"])
    panel = panel[panel["symbol"].isin(set(syms))]
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    q_by = {k: v.dropna(subset=["date"]).sort_values("date") for k, v in panel.groupby("symbol")}
    del panel
    syms = [s for s in syms if s in q_by]          # no quarterly revenue = no ratio to date
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    print(f"ev-history: {len(syms)} symbols with a quarterly panel, {len(done)} done, {len(todo)} to fetch", flush=True)

    def _one(sym):
        for attempt in range(12):
            try:
                return enrich_symbol(sym, q_by.get(sym))
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
            print(f"  evh {b0 + len(batch)}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb and (b0 // step) % 20 == 0:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    _flush(recs)
    n = len(pd.read_csv(OUT, usecols=["symbol"])) if os.path.exists(OUT) else 0
    print(f"wrote {OUT}: {n} rows", flush=True)


if __name__ == "__main__":
    main()
