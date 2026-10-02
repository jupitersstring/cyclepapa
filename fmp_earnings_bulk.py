"""Universe-wide EPS surprise history from FMP `earnings-surprises-bulk` -> fmp_earnings_bulk.csv (esb_*).

One bulk CSV per year (2014 .. today) replaces the ~30k per-symbol `earnings`
calls: 68k rows a year across US, .L, .NS, .BO, .TO, .T, .SS/.SZ, .TW, .DE,
.ST and the rest. The raw rows are kept per year under fmp_cache/bulk/ (only
the current and prior year are refetched on a rerun); the per-symbol beat
record and its price reactions (weekly total-return panel) are written for
every symbol in archetype_tags.csv.

  esb_n_reports           dated reports with both actual and estimate
  esb_beats_8q, esb_beat_share_8q, esb_beat_share_4q
  esb_surprise_4q         mean (actual - estimate) / |estimate|, last 4, clipped +-2
  esb_median_surprise_8q  median surprise, last 8
  esb_beat_streak         consecutive beats ending at the latest report
  esb_last_report_days    days since the latest report
  esb_react_last          price reaction to the latest report (prior week close ->
                          first weekly close after report day + 1)
  esb_pead_4w             drift over the 4 weeks after that
  esb_react_beats_4q      mean reaction to beats among the last 4 reports
  esb_ignored_beats_2y    beats in the last 2 years the price did not reward (<= 0)

The engine (archetype_tags.py) reads these as the universe-wide fallback for
the per-symbol evt_* event fields and for the master's earnings_beat_rate /
avg_earnings_surprise / earnings_beat_streak fills.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_earnings_bulk.csv"
RAW = "fmp_earnings_bulk.parquet"
BULK_DIR = os.path.join(fc.CACHE_DIR, "bulk")
TODAY = pd.Timestamp(dt.date.today())
FIRST_YEAR = 2014


def _year_frame(year: int, refresh: bool) -> pd.DataFrame:
    os.makedirs(BULK_DIR, exist_ok=True)
    p = os.path.join(BULK_DIR, f"esb_{year}.parquet")
    if os.path.exists(p) and not refresh:
        return pd.read_parquet(p)
    rows: list[dict] = []
    n = fc.stream_bulk_csv("earnings-surprises-bulk", rows.append, params={"year": year})
    f = pd.DataFrame(rows, columns=["symbol", "date", "epsActual", "epsEstimated", "lastUpdated"])
    f["date"] = pd.to_datetime(f["date"], errors="coerce")
    f["epsActual"] = pd.to_numeric(f["epsActual"], errors="coerce")
    f["epsEstimated"] = pd.to_numeric(f["epsEstimated"], errors="coerce")
    f = f.dropna(subset=["symbol", "date"])
    f.to_parquet(p, index=False)
    print(f"  esb {year}: {n} rows", flush=True)
    return f


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


def _stats(er: pd.DataFrame, px: pd.DataFrame | None) -> dict:
    rec: dict = {}
    er = er.dropna(subset=["epsActual", "epsEstimated"]).sort_values("date")
    er = er[er["date"] <= TODAY].drop_duplicates("date", keep="last")
    if not len(er):
        return rec
    a = er["epsActual"].to_numpy(float); e = er["epsEstimated"].to_numpy(float)
    beat = a > e
    rec["esb_n_reports"] = float(len(er))
    l8 = beat[-8:]; l4 = beat[-4:]
    rec["esb_beats_8q"] = float(l8.sum()); rec["esb_beat_share_8q"] = float(l8.mean())
    rec["esb_beat_share_4q"] = float(l4.mean())
    den = np.abs(e); den = np.where(den > 0.01, den, np.nan)
    surp = np.clip((a - e) / den, -2, 2)
    s4 = surp[-4:]; s8 = surp[-8:]
    if np.isfinite(s4).any():
        rec["esb_surprise_4q"] = float(np.nanmean(s4))
    if np.isfinite(s8).any():
        rec["esb_median_surprise_8q"] = float(np.nanmedian(s8))
    streak = 0
    for b in beat[::-1]:
        if b:
            streak += 1
        else:
            break
    rec["esb_beat_streak"] = float(streak)
    dates = er["date"].to_numpy()
    rec["esb_last_report_days"] = float((TODAY - pd.Timestamp(dates[-1])).days)
    if px is not None and len(px):
        rx = [_react(px, pd.Timestamp(d)) for d in dates[-8:]]
        react = np.array([r for r, _ in rx], float); drift = np.array([dr for _, dr in rx], float)
        b8 = beat[-8:]; d8 = dates[-8:]
        rec["esb_react_last"] = float(react[-1]); rec["esb_pead_4w"] = float(drift[-1])
        m4 = b8[-4:] & np.isfinite(react[-4:])
        if m4.any():
            rec["esb_react_beats_4q"] = float(react[-4:][m4].mean())
        w2 = (pd.to_datetime(d8) > TODAY - pd.Timedelta(weeks=104)) & b8 & np.isfinite(react)
        rec["esb_ignored_beats_2y"] = float((react[w2] <= 0).sum())
    return rec


def main() -> None:
    refresh_years = {TODAY.year, TODAY.year - 1}
    frames = []
    for y in range(FIRST_YEAR, TODAY.year + 1):
        try:
            frames.append(_year_frame(y, refresh=y in refresh_years))
        except fc.FMPError as exc:
            print(f"  esb {y}: {exc}", flush=True)
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not len(raw):
        sys.exit("no bulk rows")
    raw.to_parquet(RAW, index=False)
    t = pd.read_csv("archetype_tags.csv", usecols=["symbol"], low_memory=False)
    universe = set(t["symbol"].astype(str))
    raw = raw[raw["symbol"].isin(universe)]
    print(f"esb: {len(raw)} rows for {raw['symbol'].nunique()} universe symbols", flush=True)
    px = pd.read_parquet("fmp_weekly_prices.parquet", columns=["symbol", "week", "close"])
    px = px[(px["week"] >= "2013-01-01") & px["symbol"].isin(set(raw["symbol"]))]
    px["week"] = pd.to_datetime(px["week"])
    px_by = {k: g.sort_values("week") for k, g in px.groupby("symbol")}
    del px
    recs = []
    for i, (sym, g) in enumerate(raw.groupby("symbol"), 1):
        r = {"symbol": sym}; r.update(_stats(g, px_by.get(sym))); recs.append(r)
        if i % 5000 == 0:
            print(f"  esb stats {i}", flush=True)
    out = pd.DataFrame(recs)
    tmp = OUT + ".tmp"
    out.to_csv(tmp, index=False, float_format="%.6g"); os.replace(tmp, OUT)
    print(f"wrote {OUT}: {len(out)} rows, {len(out.columns)} cols", flush=True)


if __name__ == "__main__":
    main()
