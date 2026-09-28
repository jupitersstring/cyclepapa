"""Build the event database: triggers, outcomes, placebos, screen panel, features.

    python -m crypto_multibaggers.study
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import events as E
from . import features as F
from . import panel
from .config import DATA_DIR, POST

STUDY_DIR = DATA_DIR / "cache" / "study"
SCREEN_STEP = 14      # screen panel: one observation per token every 14 days


def _token_series(p, mkt, btc_lc, sym):
    return F.TokenSeries(p["open"][sym].to_numpy(), p["high"][sym].to_numpy(), p["low"][sym].to_numpy(),
                         p["close"][sym].to_numpy(), p["volume"][sym].to_numpy(),
                         mkt["mret"].to_numpy(), mkt["mlogvol"].to_numpy(), btc_lc)


def build(start: str = "2017-06-01") -> None:
    t0 = time.time()
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    p, meta, mkt = panel.load()
    syms = meta.index[meta.exclusion == ""].tolist()
    mkt = mkt.reindex(p["close"].index)
    dates = p["close"].index
    T = len(dates)
    btc_lc = np.log(p["close"]["BTCUSD"].to_numpy())
    bf = E.baseline_frames(p, mkt, syms)
    ev_mask, raw_any = E.detect_triggers(bf)
    ev_mask = ev_mask.loc[start:]
    st = ev_mask.stack()
    ev = st[st].reset_index()
    ev.columns = ["date", "symbol", "_"]
    ev = ev.drop(columns="_").sort_values(["date", "symbol"]).reset_index(drop=True)
    ev["t"] = dates.get_indexer(ev["date"])
    ev["event_id"] = np.arange(len(ev))
    print(f"triggers: {len(ev)} events on {ev.symbol.nunique()} tokens ({time.time()-t0:.0f}s)", flush=True)

    # car01 and sigma at the event
    ar, sig_e = bf["ar"], bf["sig_e"]
    col = {s: i for i, s in enumerate(syms)}
    ci = ev["symbol"].map(col).to_numpy()
    ti = ev["t"].to_numpy()
    arr = ar.to_numpy()
    ev["ar0"] = arr[ti, ci]
    ev["ar1"] = np.where(ti + 1 < T, arr[np.minimum(ti + 1, T - 1), ci], np.nan)
    ev["car01"] = ev["ar0"] + ev["ar1"].fillna(0)
    ev["sig_e"] = sig_e.to_numpy()[ti, ci]
    ev["paid"] = (ev["car01"] > 0) & (ev["car01"] > 2 * ev["sig_e"] * np.sqrt(2))

    # placebos
    pl = E.sample_placebos(ev, bf, raw_any)
    pl["t"] = dates.get_indexer(pl["date"])
    print(f"placebos: {len(pl)} ({time.time()-t0:.0f}s)", flush=True)

    # screen panel: every token-day on a 14-day grid (plus the live day T)
    grid = np.arange(dates.get_loc(pd.Timestamp(start)), T, SCREEN_STEP)
    el = bf["elig"].to_numpy()
    sc = [(syms[j], int(g)) for g in grid for j in np.where(el[g])[0]]
    scr = pd.DataFrame(sc, columns=["symbol", "t"])
    scr["date"] = dates[scr["t"]]
    # live: day 0 = tomorrow, eligible if eligible on the last day
    live_syms = [syms[j] for j in np.where(el[T - 1])[0]]
    live = pd.DataFrame({"symbol": live_syms, "t": T})
    print(f"screen rows: {len(scr)}, live: {len(live)} ({time.time()-t0:.0f}s)", flush=True)

    # features + outcomes, token by token
    ev_rows, pl_rows, sc_rows, lv_rows = [], [], [], []
    todo = sorted(set(ev.symbol) | set(pl.symbol) | set(scr.symbol) | set(live.symbol))
    for n, sym in enumerate(todo, 1):
        ts = _token_series(p, mkt, btc_lc, sym)
        c = ts.c
        for df, rows, day0, want_out in ((ev, ev_rows, True, True), (pl, pl_rows, False, True),
                                         (scr, sc_rows, False, True), (live, lv_rows, False, False)):
            sub = df[df.symbol == sym]
            if sub.empty:
                continue
            t = sub["t"].to_numpy()
            f = F.compute(ts, t, day0=day0)
            block = pd.DataFrame(f, index=sub.index)
            if want_out:
                o = E.outcomes(c, t) if t.max() < T else None
                if o is not None:
                    block = block.join(pd.DataFrame(o, index=sub.index))
            rows.append(block)
        if n % 250 == 0:
            print(f"  features {n}/{len(todo)} ({time.time()-t0:.0f}s)", flush=True)

    ev = ev.join(pd.concat(ev_rows))
    pl = pl.join(pd.concat(pl_rows))
    scr = scr.join(pd.concat(sc_rows))
    live = live.join(pd.concat(lv_rows))

    end = dates[-1]
    for df in (ev, pl, scr):
        df["complete"] = df["date"] <= end - pd.Timedelta(days=POST)
        df["tier"] = [E.tier(m) if ok else "pending" for m, ok in zip(df["mult_180"], df["complete"])]
    ev["durable"] = ev["r_60"] >= np.log(1.2)
    pl["durable"] = pl["r_60"] >= np.log(1.2)
    meta_cols = meta[["name"]]
    for df in (ev, pl, scr, live):
        df["name"] = df["symbol"].map(meta_cols["name"])
    # BTC regime at day 0 (BTC above its 200-day average on day -1)
    btc = p["close"]["BTCUSD"]
    reg = (btc > btc.rolling(200, min_periods=150).mean()).shift(1)
    for df in (ev, pl, scr):
        df["btc_bull"] = df["date"].map(reg).astype(float)

    ev.to_parquet(STUDY_DIR / "events.parquet")
    pl.to_parquet(STUDY_DIR / "placebos.parquet")
    scr.to_parquet(STUDY_DIR / "screen.parquet")
    live.to_parquet(STUDY_DIR / "live.parquet")
    print(f"saved. events={len(ev)} placebos={len(pl)} screen={len(scr)} live={len(live)} "
          f"({time.time()-t0:.0f}s)", flush=True)


def load():
    return (pd.read_parquet(STUDY_DIR / "events.parquet"), pd.read_parquet(STUDY_DIR / "placebos.parquet"),
            pd.read_parquet(STUDY_DIR / "screen.parquet"), pd.read_parquet(STUDY_DIR / "live.parquet"))


if __name__ == "__main__":
    build()
