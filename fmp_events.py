"""Events & perception-in-price layer for the LIVE universe -> fmp_events.csv (ev_*).

Everything here is dated, so it measures what the market DID with information,
not just the information. Cache keys match event_study_pit (earnings limit 100,
price-target-news limit 1000), so the event study and this layer share calls.

  earnings reactions (FMP earnings dates x weekly total-return panel)
    ev_beats_8q, ev_beat_share_8q, ev_surprise_4q   beat record (EPS)
    ev_react_last          price reaction to the latest report (prior week close ->
                           close of the first week ending after report day + 1)
    ev_react_beats_4q      mean reaction to beats, last 4 reports
    ev_ignored_beats_2y    beats in 2 years that the price did not reward (reaction <= 0)
    ev_pead_4w             drift in the 4 weeks after the latest report
    ev_last_report_days    days since the latest report
  price targets (price-target-news, every dated target + price when posted)
    ev_pt_n_12m, ev_pt_prem_12m (median target / price at posting - 1)
    ev_pt_rev_90d          median target, last 90d vs the prior 90-270d
    ev_px_90d              price change over the same 90 days (weekly panel)
    ev_pt_lead_flag        targets up >= 10% over 90d while price moved < 5% (street leading)
    ev_pt_chase_flag       targets up only after price rose >= 20% (street chasing)
  dividends
    ev_div_raise_streak    consecutive fiscal years of higher total dividends per share
    ev_div_cut_2y          a year-on-year cut in the last 2 years
  index / deals / filings / float
    ev_sp500_member, ev_sp500_removed_12m, ev_sp500_added_12m
    ev_ma_target_date      date the name was announced as an M&A target (FMP feed)
    ev_spin_filing_date    latest Form 10-12B/10-12G (US spin-off registration)
    ev_sc13d_date   latest SC 13D (an ACTIVE >=5% holder: activist OR strategic; use only when recent)
    ev_tender_date         latest SC TO-T / SC 14D9 (tender offer)
    ev_merger_proxy_date   latest DEFM14A / PREM14A
    ev_free_float          free-float % (FMP shares-float)
"""
from __future__ import annotations

import datetime as dt
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_events.csv"
# FIXED schema for the per-symbol pass (see fmp_sentiment.COLS for why)
COLS = ["symbol", "ev_beats_8q", "ev_beat_share_8q", "ev_surprise_4q", "ev_react_last", "ev_pead_4w",
        "ev_last_report_days", "ev_react_beats_4q", "ev_ignored_beats_2y", "ev_pt_n_12m", "ev_pt_prem_12m",
        "ev_pt_rev_90d", "ev_px_90d", "ev_pt_lead_flag", "ev_pt_chase_flag", "ev_div_raise_streak",
        "ev_div_cut_2y", "ev_spin_filing_date", "ev_sc13d_date", "ev_tender_date", "ev_merger_proxy_date"]
TODAY = pd.Timestamp(dt.date.today())


def _get(ep, params, ttl=None):
    for attempt in range(12):
        try:
            return fc.get_json(ep, params, ttl=ttl or fc.TTL_SLOW) or []
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                time.sleep(30 * (attempt + 1))
                continue
            return []
    return []


def _react(px: pd.DataFrame | None, d: pd.Timestamp):
    if px is None or not len(px):
        return np.nan, np.nan
    wk = px["week"].to_numpy(); cl = px["close"].to_numpy(float)
    ia = np.searchsorted(wk, np.datetime64(d + pd.Timedelta(days=1)))
    ib = np.searchsorted(wk, np.datetime64(d)) - 1
    if not (0 <= ib < len(cl) and ia < len(cl) and cl[ib] > 0):
        return np.nan, np.nan
    r = cl[ia] / cl[ib] - 1
    drift = cl[min(ia + 4, len(cl) - 1)] / cl[ia] - 1 if ia + 4 < len(cl) else np.nan
    return r, drift


def _px_change(px, start, end):
    if px is None or not len(px):
        return np.nan
    s = px[px["week"] <= start].tail(1); e = px[px["week"] <= end].tail(1)
    return float(e["close"].iloc[0] / s["close"].iloc[0] - 1) if len(s) and len(e) else np.nan


def one(args) -> dict:
    sym, px, is_us = args
    rec = {"symbol": sym}
    # ---- earnings reactions ----
    er = pd.DataFrame(_get("earnings", {"symbol": sym, "limit": 100}))
    if len(er) and "date" in er.columns:
        er["date"] = pd.to_datetime(er["date"], errors="coerce")
        er["a"] = pd.to_numeric(er.get("epsActual"), errors="coerce")
        er["e"] = pd.to_numeric(er.get("epsEstimated"), errors="coerce")
        er = er.dropna(subset=["date", "a", "e"]).sort_values("date")
        er = er[er["date"] <= TODAY]
        if len(er):
            er["beat"] = er["a"] > er["e"]
            l8 = er.tail(8)
            rec["ev_beats_8q"] = float(l8["beat"].sum()); rec["ev_beat_share_8q"] = float(l8["beat"].mean())
            l4 = er.tail(4)
            den = l4["e"].abs().where(l4["e"].abs() > 0.01)
            rec["ev_surprise_4q"] = float(((l4["a"] - l4["e"]) / den).clip(-2, 2).mean())
            rx = [(*_react(px, d), b, d) for d, b in zip(er["date"], er["beat"])]
            rx = pd.DataFrame(rx, columns=["react", "drift", "beat", "date"])
            last = rx.iloc[-1]
            rec["ev_react_last"], rec["ev_pead_4w"] = last["react"], last["drift"]
            rec["ev_last_report_days"] = float((TODAY - last["date"]).days)
            b4 = rx.tail(4); b4 = b4[b4["beat"]]
            if len(b4):
                rec["ev_react_beats_4q"] = float(b4["react"].mean())
            w2 = rx[(rx["date"] > TODAY - pd.Timedelta(weeks=104)) & rx["beat"]]
            rec["ev_ignored_beats_2y"] = float((w2["react"] <= 0).sum())
    # ---- dated price targets ----
    pt = pd.DataFrame(_get("price-target-news", {"symbol": sym, "limit": 1000}))
    if len(pt) and "publishedDate" in pt.columns:
        pt["date"] = pd.to_datetime(pt["publishedDate"], errors="coerce", utc=True).dt.tz_localize(None)
        pt["tgt"] = pd.to_numeric(pt.get("adjPriceTarget", pt.get("priceTarget")), errors="coerce")
        pt["px"] = pd.to_numeric(pt.get("priceWhenPosted"), errors="coerce")
        pt = pt.dropna(subset=["date", "tgt"]); pt = pt[pt["tgt"] > 0]
        w12 = pt[pt["date"] > TODAY - pd.Timedelta(days=365)]
        rec["ev_pt_n_12m"] = float(len(w12))
        if len(w12):
            prem = (w12["tgt"] / w12["px"].where(w12["px"] > 0) - 1).dropna()
            if len(prem):
                rec["ev_pt_prem_12m"] = float(prem.clip(-0.9, 5).median())
        rec90 = pt[pt["date"] > TODAY - pd.Timedelta(days=90)]
        prev = pt[(pt["date"] <= TODAY - pd.Timedelta(days=90)) & (pt["date"] > TODAY - pd.Timedelta(days=270))]
        if len(rec90) and len(prev):
            rev = float(rec90["tgt"].median() / prev["tgt"].median() - 1)
            rec["ev_pt_rev_90d"] = rev
            pxc = _px_change(px, TODAY - pd.Timedelta(days=90), TODAY)
            pxb = _px_change(px, TODAY - pd.Timedelta(days=270), TODAY - pd.Timedelta(days=90))
            rec["ev_px_90d"] = pxc
            rec["ev_pt_lead_flag"] = float(rev >= 0.10 and np.isfinite(pxc) and pxc < 0.05)
            rec["ev_pt_chase_flag"] = float(rev >= 0.10 and np.isfinite(pxb) and pxb >= 0.20)
    # ---- dividends ----
    dv = pd.DataFrame(_get("dividends", {"symbol": sym, "limit": 200}))
    if len(dv) and "date" in dv.columns:
        dv["date"] = pd.to_datetime(dv["date"], errors="coerce")
        dv["amt"] = pd.to_numeric(dv.get("adjDividend", dv.get("dividend")), errors="coerce")
        yr = dv.dropna(subset=["date", "amt"]).groupby(dv["date"].dt.year)["amt"].sum()
        yr = yr[yr.index < TODAY.year]                      # complete years only
        if len(yr) >= 2:
            ch = yr.diff().dropna()
            streak = 0
            for v in ch[::-1]:
                if v > 1e-9:
                    streak += 1
                else:
                    break
            rec["ev_div_raise_streak"] = float(streak)
            rec["ev_div_cut_2y"] = float((ch.tail(2) < -1e-9).any())
    # ---- US filings: spin / activist / tender / merger proxy ----
    if is_us:
        fl = pd.DataFrame(_get("sec-filings-search/symbol",
                               {"symbol": sym, "from": (TODAY - pd.Timedelta(days=730)).date().isoformat(),
                                "to": TODAY.date().isoformat(), "limit": 1000}, ttl=fc.TTL_FUNDAMENTAL))
        if len(fl) and "formType" in fl.columns:
            fl["d"] = pd.to_datetime(fl.get("filingDate"), errors="coerce")
            ft = fl["formType"].astype(str).str.upper()
            for key, forms in (("ev_spin_filing_date", ("10-12B", "10-12G", "10-12B/A", "10-12G/A")),
                               ("ev_sc13d_date", ("SC 13D", "SC 13D/A")),
                               ("ev_tender_date", ("SC TO-T", "SC TO-T/A", "SC 14D9")),
                               ("ev_merger_proxy_date", ("DEFM14A", "PREM14A"))):
                m = fl.loc[ft.isin(forms), "d"]
                if len(m.dropna()):
                    rec[key] = m.max().date().isoformat()
    return rec


def main(workers: int = 4) -> None:
    t = pd.read_csv("archetype_tags.csv", usecols=["symbol", "archetype_count"], low_memory=False)
    syms = t.sort_values("archetype_count", ascending=False)["symbol"].astype(str).tolist()
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    px = pd.read_parquet("fmp_weekly_prices.parquet", columns=["symbol", "week", "close"])
    px = px[px["week"] >= "2017-01-01"]
    px_by = {k: g for k, g in px.groupby("symbol")}
    del px
    print(f"events: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    step = 1000
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), step):
            batch = todo[i:i + step]
            args = [(s, px_by.get(s), "." not in s) for s in batch]
            recs = list(ex.map(one, args))
            pd.DataFrame(recs).reindex(columns=COLS).to_csv(OUT, mode="a", header=not os.path.exists(OUT),
                                                            index=False)
            st = fc.cache_stats()
            print(f"  events {min(i + step, len(todo))}/{len(todo)} | hit_rate={st['hit_rate']}", flush=True)
    # one-call feeds: S&P 500 history, M&A targets, free float
    d = pd.read_csv(OUT, low_memory=False).drop_duplicates("symbol", keep="last")
    cur = {r.get("symbol") for r in _get("sp500-constituent", {})}
    hist = pd.DataFrame(_get("historical-sp500-constituent", {}))
    d["ev_sp500_member"] = d["symbol"].isin(cur).astype(float)
    if len(hist):
        hist["dt"] = pd.to_datetime(hist.get("date", hist.get("dateAdded")), errors="coerce")
        recent = hist[hist["dt"] > TODAY - pd.Timedelta(days=365)]
        d["ev_sp500_removed_12m"] = d["symbol"].isin(set(recent.get("removedTicker", []))).astype(float)
        d["ev_sp500_added_12m"] = d["symbol"].isin(set(recent.get("symbol", []))).astype(float)
    ma = []
    for page in range(0, 60):
        chunk = _get("mergers-acquisitions-latest", {"page": page, "limit": 100}, ttl=fc.TTL_FUNDAMENTAL)
        if not chunk:
            break
        ma.extend(chunk)
    if ma:
        m = pd.DataFrame(ma)
        m["dt"] = pd.to_datetime(m.get("transactionDate"), errors="coerce")
        tgt = m.dropna(subset=["dt"]).sort_values("dt").groupby("targetedSymbol")["dt"].max()
        d["ev_ma_target_date"] = d["symbol"].map(tgt).dt.date.astype("string")
    fl = []
    for page in range(0, 200):
        chunk = _get("shares-float-all", {"page": page, "limit": 1000}, ttl=fc.TTL_FUNDAMENTAL)
        if not chunk:
            break
        fl.extend(chunk)
    if fl:
        f = pd.DataFrame(fl).drop_duplicates("symbol").set_index("symbol")["freeFloat"]
        d["ev_free_float"] = d["symbol"].map(pd.to_numeric(f, errors="coerce"))
    d.to_csv(OUT, index=False, float_format="%.6g")
    print(f"wrote {OUT}: {len(d)} rows", flush=True)


if __name__ == "__main__":
    main()
