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
from .sources import quarterly as QT
from .archetypes import lookup, COUNTRIES


def _ts_z(s: pd.Series, min_periods: int = 24) -> pd.Series:
    m = s.expanding(min_periods=min_periods).mean()
    sd = s.expanding(min_periods=min_periods).std()
    return (s - m) / sd.replace(0, np.nan)


def real_money_growth(iso: str) -> pd.Series | None:
    """
    Monthly real broad-money YoY growth -- Godley's Process 3.

    Uses LOG differences (audit fix): real growth = Dlog(M) - Dlog(CPI) over 12
    months, the geometric form, which is exact rather than the first-order
    subtraction of percentage changes (matters at high inflation). Money is
    OECD broad money (M3-concept); note the US M3 was discontinued in 2006, so
    for a strictly-US operational series a Divisia/M2 aggregate is preferable.
    """
    import numpy as np
    f = MO.monthly_frame(iso)
    if f is None or len(f) < 40:
        return None
    m = f["money"].where(f["money"] > 0)
    c = f["cpi"].where(f["cpi"] > 0)
    money_log = 100 * (np.log(m) - np.log(m.shift(12)))
    cpi_log = 100 * (np.log(c) - np.log(c.shift(12)))
    return (money_log - cpi_log).dropna()


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


def excess_liquidity(iso: str) -> pd.Series | None:
    """
    VALUATION-EXPANSION fuel (monthly) -- money growing faster than the real
    economy needs, which spills into asset prices rather than goods.

    In Godley-Lavoie portfolio terms, when broad money is created beyond
    transaction needs, households allocate the surplus across assets (the
    Brainard-Tobin lambda matrix), lifting equity/bond prices and Tobin's q --
    i.e. MULTIPLE expansion rather than profit growth. The measure is the
    change in the Marshallian K (M / nominal GDP):

        excess_liquidity = nominal broad-money growth - nominal GDP growth

    Positive = liquidity accumulating faster than output = fuel for valuation
    expansion; negative = liquidity being absorbed by the real economy or
    withdrawn. This complements 'real money growth' (Process 3, the goods-side
    fuel) by isolating the ASSET-side fuel.
    """
    import numpy as np
    f = MO.monthly_frame(iso)
    if f is None or len(f) < 40:
        return None
    m = f["money"].where(f["money"] > 0)
    money_g = 100 * (np.log(m) - np.log(m.shift(12)))
    nom_g = _nominal_growth_q(iso, m.index)
    if nom_g is None:
        return None
    return (money_g - nom_g).dropna()


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


# ---------------------------------------------------------------------------
# QUARTERLY -- the middle rung: credit impulse (Biggs-Mayer) from BIS credit.
# Fills the 1-2 year window where the monthly money signal has faded and the
# annual sectoral score has not yet built.
# ---------------------------------------------------------------------------

def credit_impulse(iso: str) -> pd.DataFrame | None:
    """
    Quarterly credit measures from BIS private non-financial credit/GDP.

    Biggs-Mayer-Pick (2010) credit impulse is the change in the FLOW of new
    credit divided by the GDP LEVEL: CI = (dD_t - dD_{t-4}) / Y_t, the second
    derivative of the nominal credit stock over nominal GDP.

    AUDIT FIX -- we only hold the BIS credit/GDP RATIO C = D/Y, and naive
    differencing of the ratio, d(D/Y), is NOT dD/Y: they differ by the
    denominator term (D/Y)*(dY/Y). In a recession falling Y mechanically lifts
    C and manufactures a false positive impulse. We remove that bias with the
    identity dD/Y ~= d(D/Y) + (D/Y)*(nominal GDP growth), using nominal growth
    (real growth + CPI inflation) from the annual history:
        net_lending (Process 2) = 4q change in credit/GDP, denominator-adjusted
        credit_impulse           = the 4q change of that (Biggs-Mayer)
    """
    c = QT.credit_gdp(iso)
    if c is None or len(c) < 24:
        return None
    # nominal GDP growth (quarterly, forward-filled from annual real + CPI)
    nom_g = _nominal_growth_q(iso, c.index)
    dC = c.diff(4)
    # denominator correction: recover the credit-flow/GDP-level from the ratio
    flow = dC + (c * nom_g / 100.0) if nom_g is not None else dC
    impulse = flow.diff(4)
    df = pd.DataFrame(index=c.index)
    df["credit_gdp"] = c
    df["net_lending"] = flow          # Process 2, denominator-corrected
    df["credit_impulse"] = impulse    # Biggs-Mayer, denominator-corrected
    df["credit_impulse_raw"] = dC.diff(4)   # the uncorrected ratio version, for reference
    z = 0.4 * _ts_z(flow, 20) + 0.6 * _ts_z(impulse, 20)
    df["credit_signal"] = z.rolling(2, min_periods=1).mean()
    return df


def _nominal_growth_q(iso: str, index) -> "pd.Series | None":
    """Nominal GDP growth (%), quarterly, from annual real growth + CPI inflation."""
    from .sources import history
    rec = history.load().get(iso, {})
    g, cpi = rec.get("growth", {}), rec.get("cpi", {})
    if not g:
        return None
    yrs = {}
    for y in set(g) | set(cpi):
        rg = g.get(y)
        infl = None
        if str(int(y) - 1) in cpi and cpi.get(y) not in (None, 0):
            try:
                infl = (cpi[y] / cpi[str(int(y) - 1)] - 1) * 100
            except Exception:
                infl = None
        if rg is not None:
            yrs[int(y)] = rg + (infl if infl is not None else 2.0)
    if not yrs:
        return None
    out = pd.Series({pd.Timestamp(y, 12, 31): v for y, v in yrs.items()}).sort_index()
    return out.reindex(index, method="ffill")


def backtest_quarterly(horizons_q=(1, 2, 4, 8, 12)) -> dict:
    """Pooled IC of the quarterly credit impulse vs forward returns (in quarters)."""
    frames = []
    for c in COUNTRIES:
        df = credit_impulse(c.iso)
        px = PX.load().get(c.iso)
        if df is None or not px:
            continue
        p = pd.Series(px)
        p.index = pd.to_datetime(p.index + "-01")
        pq = p.sort_index().resample("QE").last()
        sig = df["credit_signal"].reindex(pq.index, method="ffill")
        rec = pd.DataFrame({"sig": sig, "px": pq})
        rec["iso"] = c.iso
        frames.append(rec)
    if not frames:
        return {}
    allrec = pd.concat(frames)
    out = {"n_countries": allrec["iso"].nunique()}
    for h in horizons_q:
        ics = []
        for iso, g in allrec.groupby("iso"):
            g = g.sort_index()
            fwd = g["px"].shift(-h) / g["px"] - 1.0
            ic = _spearman(g["sig"], fwd, min_n=20)
            if ic == ic:
                ics.append(ic)
        out[f"IC_{h*3}m"] = round(float(np.mean(ics)), 3) if ics else None
    return out


def term_structure() -> str:
    """Plain-language verdict on Godley's three legs across the horizon."""
    m = backtest((3, 6, 12, 24))
    q = backtest_quarterly((1, 2, 4, 8, 12))
    return (
        "GODLEY TERM STRUCTURE -- three legs, three horizons:\n"
        f"  FAST  real money growth (Process 3): peaks {m.get('IC_6m')} at 6m, "
        f"fades to {m.get('IC_24m')} by 2y.\n"
        f"  MID   credit impulse (Biggs-Mayer):  {q.get('IC_6m')} at 6m then "
        f"turns CONTRARIAN {q.get('IC_24m')} at 2y, {q.get('IC_36m')} at 3y "
        f"-- credit booms sow busts (Mian-Sufi).\n"
        "  SLOW  sectoral-balance score:         silent short-term, builds to "
        "+0.12 at 4y.\n"
        "Use money+credit for <1y momentum, flip credit as a 2-3y warning, and "
        "the sectoral score for the 3-4y direction.")


def panel() -> pd.DataFrame:
    """Current nowcast across all covered countries."""
    rows = [nowcast(c.iso) for c in COUNTRIES]
    rows = [r for r in rows if r]
    df = pd.DataFrame(rows).set_index("iso")
    df.insert(0, "country", [lookup(i).name for i in df.index])
    return df.sort_values("fast_fuel", ascending=False)
