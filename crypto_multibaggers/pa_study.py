"""Price-action factors for the event database, and a trend-following backtest.

    python -m crypto_multibaggers.pa_study

Samples the Schabacker / Japanese / Dalton factors (priceaction.py) at every
event, placebo, screen and live row, and simulates long-only trades for a set
of entry rules: each pattern on its own, a plain 55-day Donchian breakout, and
the breakout filtered by qualitative confirmation. Every rule shares the same
exit (3 ATR chandelier trail on closes; Kijun-sen as an alternative), one open
trade per coin and rule, entry and exit at the daily close, 0.25% cost per
side (0.5% below $1M/day of volume), entries only when the prior 30-day
median volume is at least $250k.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from numba import njit

from . import panel, study
from . import priceaction as PA

STUDY_DIR = study.STUDY_DIR
COST, COST_THIN = 0.0025, 0.0025
MIN_DV = 250_000
MAX_HOLD = 365
START = "2017-06-01"

ENTRY_LABELS = {
    "donchian55": "55-day breakout (Donchian)",
    "sch_rect_bo": "Schabacker: rectangle breakout on volume",
    "sch_tri_bo": "Schabacker: triangle breakout",
    "sch_wedge_bo": "Schabacker: falling-wedge breakout",
    "sch_dbl_bo": "Schabacker: double-bottom breakout",
    "sch_ihs_bo": "Schabacker: inverse head-and-shoulders breakout",
    "sch_flag_bo": "Schabacker: flag breakout",
    "sch_dtl_bo": "Schabacker: downtrend-line break",
    "sch_res_bo": "Schabacker: six-month resistance break",
    "sch_any_bo": "Schabacker: any breakout",
    "ichi_kumo_sanyaku": "Ichimoku: cloud breakout with all signals bullish",
    "ichi_tk_cross": "Ichimoku: TK cross above the cloud",
    "tlb_turn": "Three-line break turns white",
    "ha_turn": "Heikin-Ashi turns bullish",
    "renko_turn": "Renko turns up",
    "dal_balance_bo": "Dalton: breakout from balance on volume",
    "dal_value_up": "Dalton: value moves higher with acceptance",
    "don+sanyaku": "55-day breakout + Ichimoku all bullish",
    "don+value": "55-day breakout + value migrating higher",
    "don+volume": "55-day breakout + volume 1.5x median",
    "don+candles": "55-day breakout + strong candle, no bearish patterns",
    "don+pattern": "55-day breakout + Schabacker pattern in the last 10 days",
    "don+all3": "55-day breakout + Ichimoku + value migration + volume",
    "don+candles+sanyaku": "55-day breakout + strong candle, no bearish patterns + Ichimoku all bullish",
    "trigger": "Re-rating trigger (study day 0)",
    "trigger_top": "Re-rating trigger, top-quintile follow-through score",
}
EXITS = {0: "3 ATR chandelier", 1: "Kijun-sen"}


@njit(cache=True)
def _simulate(c, atr, kij, sig, ok, kind, max_hold):
    n = c.shape[0]
    e_idx = np.empty(n, np.int64)
    x_idx = np.empty(n, np.int64)
    peak = np.empty(n)
    still_open = np.zeros(n, np.bool_)
    m = 0
    t = 0
    while t < n:
        if sig[t] and ok[t] and not np.isnan(c[t]):
            entry = t
            runmax = c[t]
            last_valid = t
            s = t + 1
            exit_at = -1
            gap = 0
            while s < n:
                cs = c[s]
                if np.isnan(cs):
                    gap += 1
                    if gap > 5:
                        exit_at = last_valid
                        break
                    s += 1
                    continue
                gap = 0
                last_valid = s
                if cs > runmax:
                    runmax = cs
                stop = False
                if kind == 0:
                    a = atr[s]
                    if not np.isnan(a) and cs < runmax - 3.0 * a:
                        stop = True
                else:
                    kk = kij[s]
                    if not np.isnan(kk) and cs < kk:
                        stop = True
                if stop or s - entry >= max_hold:
                    exit_at = s
                    break
                s += 1
            if exit_at == -1:
                exit_at = last_valid
                still_open[m] = True
            e_idx[m] = entry
            x_idx[m] = exit_at
            peak[m] = runmax
            m += 1
            t = exit_at + 1
        else:
            t += 1
    return e_idx[:m], x_idx[:m], peak[:m], still_open[:m]


def entry_signals(S: dict[str, np.ndarray], clv: np.ndarray) -> dict[str, np.ndarray]:
    eq = lambda k: S[k] == 1
    don = eq("donchian55")
    vol = S["vol_ratio"] >= 1.5
    sany = eq("ichi_sanyaku")
    mig = S["dal_migration"] > 0.5
    strong = eq("jp_marubozu") | (clv >= 0.75)
    nobear = S["jp_bear5"] == 0
    pat10 = pd.Series(S["sch_any_bo"]).rolling(10, min_periods=1).max().to_numpy() == 1
    hv = pd.Series(S["dal_higher_value"])
    value_up = (hv == 1) & (hv.shift(1) == 0) & (pd.Series(S["dal_accept"]) >= 2)
    sig = {k: eq(k) for k in ("sch_rect_bo", "sch_tri_bo", "sch_wedge_bo", "sch_dbl_bo", "sch_ihs_bo", "sch_flag_bo",
                               "sch_dtl_bo", "sch_res_bo", "sch_any_bo", "tlb_turn", "ha_turn", "renko_turn")}
    sig.update({
        "donchian55": don,
        "ichi_kumo_sanyaku": eq("ichi_kumo_bo") & sany,
        "ichi_tk_cross": eq("ichi_tk_cross") & (S["ichi_cloud"] == 1),
        "dal_balance_bo": eq("dal_balance_bo") & vol,
        "dal_value_up": value_up.to_numpy(),
        "don+sanyaku": don & sany,
        "don+value": don & mig,
        "don+volume": don & vol,
        "don+candles": don & strong & nobear,
        "don+pattern": don & pat10,
        "don+all3": don & sany & mig & vol,
        # the two filters that improved the plain breakout in both 2017-21 and 2022+
        "don+candles+sanyaku": don & strong & nobear & sany,
    })
    return sig


def build(start: str = START) -> None:
    t0 = time.time()
    ev, pl, scr, live = study.load()
    p, meta, mkt = panel.load()
    dates = p["close"].index
    T = len(dates)
    i0 = dates.get_loc(pd.Timestamp(start))
    dv30 = p["volume"].where(p["volume"] > 0).rolling(30, min_periods=20).median().shift(1)
    first = p["close"].notna().cummax().cumsum()
    elig_syms = set(meta.index[meta.exclusion == ""]) - set(panel.COMMODITY_BACKED)

    # study triggers as entries (with the follow-through score quintile)
    from . import opportunities as OPP
    evx, _, _ = OPP._load()
    spec, scores, composite, ref_comp, odds, base = OPP.follow_through_model(evx)
    evx["q"] = OPP._ecdf(ref_comp, composite(evx))
    trig = {s: g for s, g in evx.groupby("symbol")}

    frames = {"ev": [], "pl": [], "scr": [], "live": []}
    trades = []
    todo = sorted(set(ev.symbol) | set(pl.symbol) | set(scr.symbol) | set(live.symbol) | elig_syms)
    for n_, sym in enumerate(todo, 1):
        o, h, l, c, v = (p[f][sym].to_numpy() for f in ("open", "high", "low", "close", "volume"))
        S = PA.series(o, h, l, c, v)
        for key, df, d0 in (("ev", ev, True), ("pl", pl, False), ("scr", scr, False), ("live", live, False)):
            sub = df[df.symbol == sym]
            if len(sub):
                frames[key].append(pd.DataFrame(PA.sample(S, sub["t"].to_numpy(), day0=d0), index=sub.index))
        if sym not in elig_syms:
            continue
        # trading
        rng = h - l
        with np.errstate(invalid="ignore", divide="ignore"):
            clv = np.where(rng > 0, (c - l) / rng, np.nan)
        sigs = entry_signals(S, clv)
        tsig = np.zeros(T, bool)
        ttop = np.zeros(T, bool)
        if sym in trig:
            g = trig[sym]
            tsig[g["t"].to_numpy()] = True
            ttop[g.loc[g["q"] >= 0.8, "t"].to_numpy()] = True
        sigs["trigger"], sigs["trigger_top"] = tsig, ttop
        dvs = dv30[sym].to_numpy()
        age = first[sym].to_numpy()
        ok = (dvs >= MIN_DV) & (age >= 121)
        ok[:i0] = False
        atr, kij = S["atr20"], S["kijun"]
        for rule, sg in sigs.items():
            sg = np.nan_to_num(np.asarray(sg, float)).astype(bool)
            if not sg[i0:].any():
                continue
            for kind in (0, 1):
                e, x, pk, op = _simulate(c, atr, kij, sg, ok, kind, MAX_HOLD)
                if not len(e):
                    continue
                cost = np.where(dvs[e] < 1e6, COST + COST_THIN, COST)
                gross = c[x] / c[e]
                trades.append(pd.DataFrame({
                    "symbol": sym, "rule": rule, "exit": kind, "entry": dates[e], "exit_date": dates[x],
                    "ret": gross * (1 - cost) / (1 + cost) - 1, "hold": x - e, "peak_mult": pk / c[e],
                    "open": op, "dv30": dvs[e]}))
        if n_ % 250 == 0:
            print(f"  price action {n_}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    for key, fn in (("ev", "pa_events"), ("pl", "pa_placebos"), ("scr", "pa_screen"), ("live", "pa_live")):
        pd.concat(frames[key]).to_parquet(STUDY_DIR / f"{fn}.parquet")
    tr = pd.concat(trades, ignore_index=True)
    tr.to_parquet(STUDY_DIR / "pa_trades.parquet")
    print(f"saved price-action samples and {len(tr):,} trades ({time.time() - t0:.0f}s)", flush=True)


def load():
    return tuple(pd.read_parquet(STUDY_DIR / f"{fn}.parquet")
                 for fn in ("pa_events", "pa_placebos", "pa_screen", "pa_live", "pa_trades"))


if __name__ == "__main__":
    build()
