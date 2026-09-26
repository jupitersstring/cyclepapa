"""Weekly time-series measures for every LIVE name -> ts_snapshot.csv (ts_*).

One pass over the weekly split+dividend-adjusted panel (fmp_weekly_prices.
parquet): total-return, point-in-time at the last complete W-FRI bar. These
replace the snapshot proxies (price_yoy / momentum_12m / pct_off_52w_high /
5y-range, Yahoo beta) with direct measurements, and add what no snapshot can
see (moving-average structure, relative-strength lines, drawdown history,
beta trend, volume spikes).

Benchmarks: FMP local index series (fmp_index_weekly.parquet, built here from
historical-price-eod/light) where one exists for the listing market; else an
equal-weight median-return pseudo-index of the market's own names (flagged
ts_bench='peer').

Columns
  ts_r4 .. ts_r260          close / close[t-k] - 1 (weeks)
  ts_ma10 / ma30 / ma40     weekly SMAs; ts_ma30_slope4 / _slope13 (fractional change)
  ts_above_ma30             close > 30w MA
  ts_dist_hi52 / lo52 / hi260   close / rolling high (low); ts_wks_since_hi52
  ts_mrs, ts_mrs_13ago      Mansfield RS: log(stock/index) minus its 52w mean
  ts_rs_at_hi               RS line within 2% (log) of its 52w high
  ts_rs_pct_mkt / _glob     IBD-style 0.4*r13+0.2*(r26+r39+r52), percentile
  ts_vol_spike / _spike4    last week / max of last 4 weeks volume vs 52w median
  ts_tight5                 (max-min of last 5 closes) / close
  ts_maxdd_5y / _10y        worst peak-to-trough; ts_uw_share_5y share of weeks >20% under water
  ts_beta_1y/2y/3y, ts_dbeta_3y, ts_down_capture_3y, ts_vol_1y/3y
  ts_dvol26_usd             median weekly USD dollar volume, 26w (quote-unit aware)
  ts_weinstein_stage        1 base / 2 advance / 3 top / 4 decline (30w MA + slope + MRS)
  ts_multi_year_high        close within 2% of its 5y high after a 2y flat base
  ts_mkt_breadth30          share of the market's names above their 30w MA (context)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import event_study_base as es
import fmp_client as fc

OUT = "ts_snapshot.csv"
INDEX_FILE = "fmp_index_weekly.parquet"
INDEX = {"US": "^GSPC", "T": "^N225", "L": "^FTSE", "HK": "^HSI", "NS": "^NSEI", "BO": "^BSESN",
         "KS": "^KS11", "TO": "^GSPTSE", "V": "^GSPTSE", "CN": "^GSPTSE", "NE": "^GSPTSE",
         "AX": "^AXJO", "DE": "^GDAXI", "F": "^GDAXI", "PA": "^FCHI", "TW": "^TWII", "TWO": "^TWII",
         "JK": "^JKSE", "BK": "^SET.BK", "SS": "000001.SS", "SI": "^STI", "KL": "^KLSE", "SA": "^BVSP",
         "MX": "^MXX", "ST": "^OMX", "SW": "^SSMI", "AS": "^AEX", "MI": "FTSEMIB.MI", "MC": "^IBEX",
         "NZ": "^NZ50", "IS": "XU100.IS", "WA": "WIG20.WA"}


def build_index_file() -> pd.DataFrame:
    rows = []
    for mkt, sym in sorted(set((v, v) for v in INDEX.values())):
        try:
            r = fc.get_json("historical-price-eod/light", {"symbol": sym, "from": "2010-01-01"},
                            ttl=fc.TTL_FUNDAMENTAL) or []
        except fc.FMPError:
            r = []
        if not r:
            continue
        d = pd.DataFrame(r)[["date", "price"]]
        d["date"] = pd.to_datetime(d["date"])
        w = d.set_index("date")["price"].resample("W-FRI").last().dropna().reset_index()
        w.columns = ["week", "index_close"]
        w.insert(0, "index", sym)
        rows.append(w)
    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(INDEX_FILE, index=False)
    return out


def _roll_max(a, w, mp):
    return pd.Series(a).rolling(w, min_periods=mp).max().to_numpy()


def _one(args):
    sym, d, bench = args
    d = d.sort_values("week")
    n = len(d)
    if n < 60:
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        cl = d["close"].to_numpy(float); hi = d["high"].to_numpy(float); lo = d["low"].to_numpy(float)
        vol = d["volume"].to_numpy(float); dv = d["dvol"].to_numpy(float) * float(d["usd"].iloc[0])
        lr = np.log(cl); ret = np.diff(lr, prepend=np.nan)
        b = bench.reindex(d["week"]).to_numpy(float)           # benchmark log level
        bret = np.diff(b, prepend=np.nan)
        s = pd.Series
        r = lambda k: cl[-1] / cl[-1 - k] - 1 if n > k else np.nan
        ma = lambda w: s(cl).rolling(w).mean().to_numpy()
        ma10, ma30, ma40 = ma(10), ma(30), ma(40)
        hi52 = _roll_max(hi, 52, 40); lo52 = -_roll_max(-lo, 52, 40); hi260 = _roll_max(hi, 260, 150)
        rs = lr - b
        rs_ma = s(rs).rolling(52, min_periods=40).mean().to_numpy()
        rs_hi = s(rs).rolling(52, min_periods=40).max().to_numpy()
        vmed = s(vol).rolling(52, min_periods=26).median().to_numpy()
        rec = {"symbol": sym, "ts_week": d["week"].iloc[-1], "ts_n": n,
               **{f"ts_r{k}": r(k) for k in (4, 13, 26, 39, 52, 104, 156, 260)},
               "ts_ma10": ma10[-1], "ts_ma30": ma30[-1], "ts_ma40": ma40[-1],
               "ts_ma30_slope4": ma30[-1] / ma30[-5] - 1 if n > 35 else np.nan,
               "ts_ma30_slope13": ma30[-1] / ma30[-14] - 1 if n > 44 else np.nan,
               "ts_above_ma30": float(cl[-1] > ma30[-1]) if np.isfinite(ma30[-1]) else np.nan,
               "ts_dist_hi52": cl[-1] / hi52[-1], "ts_dist_lo52": cl[-1] / lo52[-1],
               "ts_dist_hi260": cl[-1] / hi260[-1],
               "ts_wks_since_hi52": float(51 - int(np.nanargmax(hi[-52:]))) if n >= 52 else np.nan,
               "ts_mrs": rs[-1] - rs_ma[-1],
               "ts_mrs_13ago": rs[-14] - rs_ma[-14] if n > 70 else np.nan,
               "ts_rs_at_hi": float(rs[-1] >= rs_hi[-1] - 0.02) if np.isfinite(rs_hi[-1]) else np.nan,
               "ts_vol_spike": vol[-1] / vmed[-1] if vmed[-1] > 0 else np.nan,
               "ts_vol_spike4": vol[-4:].max() / vmed[-1] if vmed[-1] > 0 else np.nan,
               "ts_tight5": (cl[-5:].max() - cl[-5:].min()) / cl[-1],
               "ts_dvol26_usd": float(np.nanmedian(dv[-26:])) if n >= 26 else np.nan}
        for W, tag in ((260, "5y"), (520, "10y")):
            if n >= int(W * 0.8):
                seg = cl[-W:]; dd = seg / np.maximum.accumulate(seg) - 1
                rec[f"ts_maxdd_{tag}"] = float(dd.min()); rec[f"ts_uw_share_{tag}"] = float((dd < -0.20).mean())
        for W, tag in ((52, "1y"), (104, "2y"), (156, "3y")):
            a, m_ = ret[-W:], bret[-W:]
            ok = np.isfinite(a) & np.isfinite(m_)
            if ok.sum() >= int(W * 0.7) and np.var(m_[ok]) > 0:
                rec[f"ts_beta_{tag}"] = float(np.cov(a[ok], m_[ok])[0, 1] / np.var(m_[ok], ddof=1))
                rec[f"ts_vol_{tag}"] = float(np.std(a[ok]) * np.sqrt(52))
                dn = ok & (m_ < 0)
                if tag == "3y" and dn.sum() >= 15:
                    rec["ts_dbeta_3y"] = float(np.cov(a[dn], m_[dn])[0, 1] / np.var(m_[dn], ddof=1))
                    rec["ts_down_capture_3y"] = float(np.mean(a[dn]) / np.mean(m_[dn]))
        # Weinstein stage from the 30w MA, its slope and relative strength
        sl = rec["ts_ma30_slope4"]; above = rec["ts_above_ma30"]; mrs = rec["ts_mrs"]
        if np.isfinite(sl) and np.isfinite(above):
            if above == 1 and sl > 0.005:
                st = 2
            elif above == 0 and sl < -0.005:
                st = 4
            elif abs(sl) <= 0.005 and np.isfinite(mrs) and mrs < 0 and rec["ts_r26"] < 0:
                st = 3 if rec["ts_dist_hi52"] >= 0.85 else 1
            else:
                st = 1 if rec["ts_dist_hi52"] < 0.85 else 3
            rec["ts_weinstein_stage"] = float(st)
        # breakout from a long base: at a 5-year high after a flat 2 years
        r104_prev = cl[-14] / cl[-118] - 1 if n > 118 else np.nan
        rec["ts_multi_year_high"] = float(np.isfinite(r104_prev) and abs(r104_prev) <= 0.25
                                          and rec["ts_dist_hi260"] >= 0.98)
    return rec


def build(out: str = OUT) -> pd.DataFrame:
    from multiprocessing import Pool
    if not os.path.exists(INDEX_FILE):
        build_index_file()
    idx = pd.read_parquet(INDEX_FILE)
    p = pd.read_parquet(es.PRICES, columns=["symbol", "week", "high", "low", "close", "volume", "dvol"])
    p = p[p["week"] >= "2014-01-01"]
    last = p.groupby("symbol")["week"].transform("max")
    p = p[last >= p["week"].max() - pd.Timedelta(days=21)]
    p = es.attach_usd(p)
    p["mkt"] = p["symbol"].map(es._market)
    # benchmark log-levels per market: FMP index, else equal-weight peer median
    p["lr_ret"] = np.log(p["close"].astype(float)).groupby(p["symbol"]).diff()
    peer = p.groupby(["mkt", "week"])["lr_ret"].median().fillna(0).groupby(level=0).cumsum()
    idx_l = {k: np.log(g.set_index("week")["index_close"]) for k, g in idx.groupby("index")}
    bench, bsrc = {}, {}
    for mkt in p["mkt"].unique():
        isym = INDEX.get(mkt)
        if isym in idx_l:
            bench[mkt], bsrc[mkt] = idx_l[isym], "index"
        else:
            bench[mkt], bsrc[mkt] = peer.loc[mkt], "peer"
    jobs = [(sym, g, bench[g["mkt"].iloc[0]]) for sym, g in p.groupby("symbol", sort=False)]
    del p
    with Pool(4) as pool:
        rows = [r for r in pool.imap_unordered(_one, jobs, chunksize=64) if r is not None]
    o = pd.DataFrame(rows)
    o["mkt"] = o["symbol"].map(es._market)
    o["ts_bench"] = o["mkt"].map(bsrc)
    o["ts_rs_raw"] = 0.4 * o["ts_r13"] + 0.2 * (o["ts_r26"] + o["ts_r39"] + o["ts_r52"])
    o["ts_rs_pct_mkt"] = o.groupby("mkt")["ts_rs_raw"].rank(pct=True) * 100
    o["ts_rs_pct_glob"] = o["ts_rs_raw"].rank(pct=True) * 100
    o["ts_mkt_breadth30"] = o.groupby("mkt")["ts_above_ma30"].transform("mean")
    # beta RANK within market (levels differ by benchmark; ranks are comparable)
    for c in ("ts_beta_1y", "ts_beta_3y"):
        o[c + "_rk"] = o.groupby("mkt")[c].rank(pct=True)
    o = o.drop(columns=["mkt"])
    o.to_csv(out, index=False, float_format="%.6g")
    return o


if __name__ == "__main__":
    o = build()
    print(f"ts_snapshot: {len(o)} live names; benchmark index share "
          f"{(o['ts_bench'] == 'index').mean():.1%}")
