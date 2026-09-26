"""Market-perception layer (analyst sentiment) -> fmp_sentiment.csv.

For every name, a snapshot of how the sell side sees it NOW and how that view
is MOVING — the perception half of the "growth not rewarded" archetypes:

  sent_n_analysts        ratings on file (latest month, grades-historical)
  sent_buy_share         (strong buy + buy) / all ratings
  sent_buy_share_d12     change in buy share vs 12 months ago (+ = warming)
  sent_n_analysts_d12    change in coverage vs 12 months ago (+ = discovery)
  sent_upgrades_12m      upgrade actions in the last 12 months (grades)
  sent_downgrades_12m
  sent_initiations_12m   new coverage in the last 12 months
  sent_months_since_up   months since the last upgrade (60 = none in 5y)
  sent_pt_rev_q          last-quarter average price target / last-year average - 1
                         (target revision momentum; + = targets being raised)
  sent_pt_count_q        targets published last quarter (attention)

Endpoints and parameters are identical to event_study_pit.fetch, so the cache
serves both the event study and this snapshot (one-off cost).
"""
from __future__ import annotations

import datetime as dt
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_sentiment.csv"
TODAY = pd.Timestamp(dt.date.today())


def _get(ep, params):
    for attempt in range(12):
        try:
            return fc.get_json(ep, params, ttl=fc.TTL_SLOW) or []
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                time.sleep(30 * (attempt + 1))
                continue
            return []
    return []


def enrich_symbol(sym: str) -> dict:
    rec = {"symbol": sym}
    gh = pd.DataFrame(_get("grades-historical", {"symbol": sym, "limit": 500}))
    if len(gh):
        gh["date"] = pd.to_datetime(gh["date"], errors="coerce")
        cols = ["analystRatingsStrongBuy", "analystRatingsBuy", "analystRatingsHold",
                "analystRatingsSell", "analystRatingsStrongSell"]
        for c in cols:
            gh[c] = pd.to_numeric(gh.get(c), errors="coerce").fillna(0)
        gh["n"] = gh[cols].sum(axis=1)
        gh = gh.sort_values("date")
        last = gh.iloc[-1]
        if (TODAY - last["date"]).days <= 92 and last["n"] > 0:
            rec["sent_n_analysts"] = float(last["n"])
            rec["sent_buy_share"] = float((last["analystRatingsStrongBuy"] + last["analystRatingsBuy"]) / last["n"])
            ya = gh[gh["date"] <= last["date"] - pd.Timedelta(days=365)]
            if len(ya) and ya.iloc[-1]["n"] > 0:
                y = ya.iloc[-1]
                rec["sent_buy_share_d12"] = rec["sent_buy_share"] - float(
                    (y["analystRatingsStrongBuy"] + y["analystRatingsBuy"]) / y["n"])
                rec["sent_n_analysts_d12"] = float(last["n"] - y["n"])
    gr = pd.DataFrame(_get("grades", {"symbol": sym, "limit": 2000}))
    if len(gr) and "date" in gr.columns:
        gr["date"] = pd.to_datetime(gr["date"], errors="coerce")
        a = gr.get("action", pd.Series("", index=gr.index)).astype(str).str.lower()
        w = gr["date"] > TODAY - pd.Timedelta(days=365)
        rec["sent_upgrades_12m"] = float(((a == "upgrade") & w).sum())
        rec["sent_downgrades_12m"] = float(((a == "downgrade") & w).sum())
        rec["sent_initiations_12m"] = float((a.isin(["initialise", "initiate", "init"]) & w).sum())
        ups = gr.loc[a == "upgrade", "date"]
        rec["sent_months_since_up"] = (min(60.0, (TODAY - ups.max()).days / 30.4) if len(ups) else 60.0)
    pts = _get("price-target-summary", {"symbol": sym})
    if pts:
        p = pts[0] if isinstance(pts, list) else pts
        q, y = p.get("lastQuarterAvgPriceTarget"), p.get("lastYearAvgPriceTarget")
        try:
            if q and y and float(y) > 0 and float(p.get("lastQuarterCount") or 0) > 0:
                rec["sent_pt_rev_q"] = float(q) / float(y) - 1
            rec["sent_pt_count_q"] = float(p.get("lastQuarterCount") or 0)
        except (TypeError, ValueError):
            pass
    return rec


def main(workers: int = 3) -> None:
    t = pd.read_csv("archetype_tags.csv", usecols=["symbol", "archetype_count"], low_memory=False)
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "n_analysts"], low_memory=False)
    t = t.merge(g.drop_duplicates("symbol"), on="symbol", how="left")
    syms = t.sort_values("archetype_count", ascending=False)["symbol"].astype(str).tolist()
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    print(f"sentiment: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    step = 1000
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), step):
            recs = list(ex.map(enrich_symbol, todo[i:i + step]))
            pd.DataFrame(recs).to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
            s = fc.cache_stats()
            print(f"  sentiment {min(i + step, len(todo))}/{len(todo)} | hit_rate={s['hit_rate']}", flush=True)


if __name__ == "__main__":
    main()
