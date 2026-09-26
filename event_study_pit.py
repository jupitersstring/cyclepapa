"""Stage B of the base-breakout event study: point-in-time fundamentals and
market perception for every base-month in base_panel.parquet.

Everything is joined AS OF the base month t using only information that was
public by then:
  * fundamentals: quarterly income statements (FMP, up to 80 quarters) keyed on
    filingDate; where FMP carries no real filing date (filingDate == period end,
    common for older non-US rows) a conservative 75-day reporting lag is used
  * perception:  grades-historical (monthly analyst rating counts, 2019->),
    grades (every upgrade / downgrade / initiation, 2017->), earnings
    (reported vs estimated EPS per quarter)

Fetches are cached (one-off cost) and parallel; rate limits wait and retry.

Features added (NaN where the source does not reach back to t):
  fundamentals  rev_g_base     TTM revenue now / TTM revenue ~2y earlier - 1
                ebit_g_base    same for operating income (NaN if either <= 0)
                ebit_turned    1 if TTM EBIT was <= 0 two years ago and > 0 now
                gm_delta_base  TTM gross margin now - two years ago
                rev_accel      TTM revenue YoY now - TTM revenue YoY a year ago
                coil_rev       log(1+rev_g_base) - log(1+r104): fundamentals
                               compounding under a flat price (multiple coiling)
                coil_ebit      same with EBIT growth
  perception    n_analysts     rating count (latest month <= t)
                buy_share      (strong buy + buy) / all ratings
                buy_share_d12  change in buy share over 12 months
                upgrades_12m, downgrades_12m, initiations_12m
                months_since_up  months since the last upgrade (capped at 60)
                beats_4q       EPS beats in the last 4 reported quarters
                surprise_4q    mean (actual - estimate) / |estimate| over 4 quarters
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

PANEL = "base_panel.parquet"
OUT = "base_panel_pit.parquet"


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


def fetch(sym: str) -> dict:
    return {"symbol": sym,
            "is": _get("income-statement", {"symbol": sym, "period": "quarter", "limit": 80}),
            "gh": _get("grades-historical", {"symbol": sym, "limit": 500}),
            "gr": _get("grades", {"symbol": sym, "limit": 2000}),
            "er": _get("earnings", {"symbol": sym, "limit": 100})}


def _ttm_frame(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    if "date" not in d.columns:
        return pd.DataFrame()
    d["period_end"] = pd.to_datetime(d["date"], errors="coerce")
    fd = pd.to_datetime(d.get("filingDate"), errors="coerce")
    # no genuine filing date -> conservative 75-day lag after period end
    d["avail"] = fd.where(fd.notna() & (fd > d["period_end"]), d["period_end"] + pd.Timedelta(days=75))
    # single reporting currency (the latest one)
    if "reportedCurrency" in d.columns:
        d = d[d["reportedCurrency"] == d.sort_values("period_end")["reportedCurrency"].iloc[-1]]
    d = d.dropna(subset=["period_end"]).drop_duplicates("period_end").sort_values("period_end")
    for c in ("revenue", "grossProfit", "operatingIncome", "netIncome"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    # TTM = sum of 4 CONTIGUOUS quarters (gaps of 70-120 days)
    gaps = d["period_end"].diff().dt.days
    ok = gaps.between(70, 120)
    contig = ok.rolling(3).sum() == 3
    out = pd.DataFrame({"avail": d["avail"], "period_end": d["period_end"]})
    for c, k in (("revenue", "rev"), ("grossProfit", "gp"), ("operatingIncome", "ebit")):
        out[k] = d[c].rolling(4).sum().where(contig)
    return out.dropna(subset=["rev"]).sort_values("avail")


def _asof(frame: pd.DataFrame, t: pd.Timestamp):
    f = frame[frame["avail"] <= t]
    return f.iloc[-1] if len(f) else None


def features_for(sym: str, weeks: pd.Series, r104: pd.Series, raw: dict) -> pd.DataFrame:
    out = pd.DataFrame(index=weeks.index)
    ttm = _ttm_frame(raw["is"])
    gh = pd.DataFrame(raw["gh"])
    if len(gh):
        gh["date"] = pd.to_datetime(gh["date"], errors="coerce")
        cols = ["analystRatingsStrongBuy", "analystRatingsBuy", "analystRatingsHold",
                "analystRatingsSell", "analystRatingsStrongSell"]
        for c in cols:
            gh[c] = pd.to_numeric(gh.get(c), errors="coerce").fillna(0)
        gh["n"] = gh[cols].sum(axis=1)
        gh["buy"] = (gh["analystRatingsStrongBuy"] + gh["analystRatingsBuy"]) / gh["n"].where(gh["n"] > 0)
        gh = gh.sort_values("date")
    gr = pd.DataFrame(raw["gr"])
    if len(gr):
        gr["date"] = pd.to_datetime(gr["date"], errors="coerce")
        gr["action"] = gr.get("action", "").astype(str).str.lower()
    er = pd.DataFrame(raw["er"])
    if len(er):
        er["date"] = pd.to_datetime(er["date"], errors="coerce")
        er["a"] = pd.to_numeric(er.get("epsActual"), errors="coerce")
        er["e"] = pd.to_numeric(er.get("epsEstimated"), errors="coerce")
        er = er.dropna(subset=["a", "e"]).sort_values("date")
    rows = []
    for idx, t in weeks.items():
        rec = {}
        if len(ttm):
            now = _asof(ttm, t)
            then = _asof(ttm, t - pd.Timedelta(weeks=104))
            ya = _asof(ttm, t - pd.Timedelta(weeks=52))
            if now is not None and then is not None and then["rev"] > 0 and now["rev"] > 0:
                rec["rev_g_base"] = now["rev"] / then["rev"] - 1
                rec["coil_rev"] = np.log(now["rev"] / then["rev"]) - np.log1p(r104[idx])
                if pd.notna(now["gp"]) and pd.notna(then["gp"]):
                    rec["gm_delta_base"] = now["gp"] / now["rev"] - then["gp"] / then["rev"]
                if pd.notna(now["ebit"]) and pd.notna(then["ebit"]):
                    rec["ebit_turned"] = float(then["ebit"] <= 0 < now["ebit"])
                    if now["ebit"] > 0 and then["ebit"] > 0:
                        rec["ebit_g_base"] = now["ebit"] / then["ebit"] - 1
                        rec["coil_ebit"] = np.log(now["ebit"] / then["ebit"]) - np.log1p(r104[idx])
            if now is not None and ya is not None and then is not None and ya["rev"] > 0 and then["rev"] > 0:
                rec["rev_accel"] = (now["rev"] / ya["rev"]) - (ya["rev"] / then["rev"])
        if len(gh):
            g_now = gh[gh["date"] <= t]
            if len(g_now):
                last = g_now.iloc[-1]
                if (t - last["date"]).days <= 62:
                    rec["n_analysts"] = last["n"]
                    rec["buy_share"] = last["buy"]
                    g_ya = g_now[g_now["date"] <= t - pd.Timedelta(days=365)]
                    if len(g_ya) and pd.notna(g_ya.iloc[-1]["buy"]) and pd.notna(last["buy"]):
                        rec["buy_share_d12"] = last["buy"] - g_ya.iloc[-1]["buy"]
        if len(gr) and gr["date"].min() <= t - pd.Timedelta(days=365):
            w = gr[(gr["date"] <= t) & (gr["date"] > t - pd.Timedelta(days=365))]
            rec["upgrades_12m"] = float((w["action"] == "upgrade").sum())
            rec["downgrades_12m"] = float((w["action"] == "downgrade").sum())
            rec["initiations_12m"] = float(w["action"].isin(["initialise", "initiate", "init"]).sum())
            ups = gr[(gr["date"] <= t) & (gr["action"] == "upgrade")]
            rec["months_since_up"] = (min(60.0, (t - ups["date"].max()).days / 30.4)
                                      if len(ups) else 60.0)
        if len(er):
            q = er[er["date"] <= t].tail(4)
            if len(q) == 4:
                rec["beats_4q"] = float((q["a"] > q["e"]).sum())
                den = q["e"].abs().where(q["e"].abs() > 0.01)
                rec["surprise_4q"] = float(((q["a"] - q["e"]) / den).clip(-2, 2).mean())
        rows.append(rec)
    return pd.DataFrame(rows, index=weeks.index)


def main(workers: int = 6) -> None:
    d = pd.read_parquet(PANEL)
    syms = d["symbol"].unique().tolist()
    print(f"pit: {len(syms)} symbols, {len(d)} base-months", flush=True)
    feats = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, raw in enumerate(ex.map(fetch, syms), 1):
            g = d[d["symbol"] == raw["symbol"]]
            with np.errstate(divide="ignore", invalid="ignore"):
                feats.append(features_for(raw["symbol"], g["week"], g["r104"], raw))
            if i % 1000 == 0:
                s = fc.cache_stats()
                print(f"  pit {i}/{len(syms)} | hit_rate={s['hit_rate']}", flush=True)
    f = pd.concat(feats)
    out = d.join(f)
    out.to_parquet(OUT, index=False, compression="zstd")
    print(f"wrote {OUT}: {len(out)} rows; coverage:",
          {c: round(float(out[c].notna().mean()), 3) for c in f.columns}, flush=True)


if __name__ == "__main__":
    main()
