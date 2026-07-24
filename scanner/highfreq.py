"""
High-frequency Godley measures -- the fast legs of the framework.

The annual sectoral-balance score (backtest.py) is a 3-4 year direction signal.
This module adds the parts of Godley's framework that move MONTHLY, so the
scanner can register near-term inflections between the slow annual readings.

The measures, straight from the Seven Unsustainable Processes:

  P3  real money-stock growth  = money YoY% - CPI YoY%          (monthly)
  money impulse (P2/P3 accel)  = 6m change in real money growth (the monthly
                                 analog of the credit impulse -- a 2nd
                                 derivative, which leads at higher frequency)

Fast Godley fuel = z(real_money_growth) + z(money_impulse), z-scored against
each country's own monthly history (no look-ahead), then smoothed.

Because prices are monthly we can finally test SHORT horizons (3/6/12 months)
where the annual score had no power -- the whole point of a faster measure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .sources import monthly as MO
from .sources import prices as PX
from .archetypes import lookup, COUNTRIES


def _ts_z(s: pd.Series, min_periods: int = 24) -> pd.Series:
    m = s.expanding(min_periods=min_periods).mean()
    sd = s.expanding(min_periods=min_periods).std()
    return (s - m) / sd.replace(0, np.nan)


def real_money_growth(iso: str) -> pd.Series | None:
    """Monthly real broad-money YoY growth -- Godley's Process 3."""
    f = MO.monthly_frame(iso)
    if f is None or len(f) < 40:
        return None
    money_yoy = f["money"].pct_change(12) * 100
    cpi_yoy = f["cpi"].pct_change(12) * 100
    return (money_yoy - cpi_yoy).dropna()


def fast_fuel(iso: str) -> pd.DataFrame | None:
    """The monthly high-frequency Godley fuel signal + its components."""
    rmg = real_money_growth(iso)
    if rmg is None or len(rmg) < 30:
        return None
    impulse = rmg.diff(6)                      # 6m acceleration = the fast lead
    df = pd.DataFrame(index=rmg.index)
    df["real_money_growth"] = rmg
    df["money_impulse"] = impulse
    z = 0.5 * _ts_z(rmg) + 0.5 * _ts_z(impulse)
    df["fast_fuel"] = z
    df["fast_fuel_smooth"] = z.rolling(3, min_periods=1).mean()
    return df


def nowcast(iso: str) -> dict | None:
    """Latest monthly reading -- the current high-frequency Godley pulse."""
    df = fast_fuel(iso)
    if df is None:
        return None
    last = df.dropna(subset=["fast_fuel_smooth"]).iloc[-1]
    return {"iso": iso, "asof": df.index[-1].strftime("%Y-%m"),
            "real_money_growth": round(float(last["real_money_growth"]), 1),
            "money_impulse": round(float(last["money_impulse"]), 1),
            "fast_fuel": round(float(last["fast_fuel_smooth"]), 2)}


def _spearman(a: pd.Series, b: pd.Series, min_n: int = 12) -> float:
    m = a.notna() & b.notna()
    if m.sum() < min_n:
        return np.nan
    return float(a[m].rank().corr(b[m].rank()))


def backtest(horizons_m=(3, 6, 12, 24)) -> dict:
    """
    Pooled IC of the monthly fast-fuel signal vs forward price returns at
    monthly horizons -- across every country with monthly money + prices.
    """
    frames = []
    for c in COUNTRIES:
        df = fast_fuel(c.iso)
        px = PX.load().get(c.iso)
        if df is None or not px:
            continue
        p = pd.Series(px)
        p.index = pd.to_datetime(p.index + "-01")
        p = p.sort_index()
        sig = df["fast_fuel_smooth"].reindex(p.index, method="ffill")
        rec = pd.DataFrame({"sig": sig, "px": p})
        rec["iso"] = c.iso
        frames.append(rec)
    if not frames:
        return {}
    allrec = pd.concat(frames)
    out = {"n_countries": allrec["iso"].nunique()}
    for h in horizons_m:
        ics = []
        for iso, g in allrec.groupby("iso"):
            g = g.sort_index()
            fwd = g["px"].shift(-h) / g["px"] - 1.0
            ic = _spearman(g["sig"], fwd, min_n=24)
            if ic == ic:
                ics.append(ic)
        out[f"IC_{h}m"] = round(float(np.mean(ics)), 3) if ics else None
        out[f"n_{h}m"] = len(ics)
    return out


def panel() -> pd.DataFrame:
    """Current nowcast across all covered countries."""
    rows = [nowcast(c.iso) for c in COUNTRIES]
    rows = [r for r in rows if r]
    df = pd.DataFrame(rows).set_index("iso")
    df.insert(0, "country", [lookup(i).name for i in df.index])
    return df.sort_values("fast_fuel", ascending=False)
