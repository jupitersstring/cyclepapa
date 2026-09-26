"""Event study: "goes nowhere for two years, then triples in three months".

Stage A (this module, price-only) builds a month-end panel from the weekly
price history (fmp_weekly_prices.parquet):

  BASE month t  = the prior 104 weeks went NOWHERE:
                  |return over 104w| <= 25%  AND  104w high / low <= 2.0
                  AND tradeable (median weekly dollar volume over 26w >= $250k)
  EVENT labels  = forward, from the close at t:
                  ev2x_13w : max close in the next 13 weeks >= 2.0x
                  ev3x_13w : max close in the next 13 weeks >= 3.0x   (the "triple")
                  ev2x_26w : max close in the next 26 weeks >= 2.0x
                  plus fwd_13w / fwd_52w returns and fwd_dd_52w (worst close in
                  52w / close) so the COST of the non-events is measured too
  FEATURES      = measured ONLY from data at or before t:
    compression   vol_ratio      std(weekly log ret, 26w) / std(104w)
                  range_ratio    26w high/low range / 104w range (log)
    structure     pos_in_range   (close - 104w low) / (104w high - 104w low)
                  dist_high      close / 104w high
                  lows_slope     slope of 13w rolling lows over the base (log, per yr)
                  r13, r26       return within the base
    accumulation  updown_vol     volume on up weeks / down weeks, 26w
                  obv_slope      on-balance-volume trend over 26w vs price trend
                  dvol_trend     median dollar volume 13w / 104w
    context       rs26           26w return minus the median of same-market peers
                  prior_dd       104w-base close vs the 5y high before the base
                  base_len_36    1 if the 156w window was also a base (longer coil)
                  size_dvol      log median weekly dollar volume (size / liquidity)

Stage B (attach_pit) joins point-in-time fundamentals + perception; stage C
(analyse) computes lift tables and the walk-forward model. See
BACKTEST_BASE_BREAKOUT.md for results and caveats.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PRICES = "fmp_weekly_prices.parquet"
PANEL = "base_panel.parquet"

BASE_W = 104
MAX_ABS_RET = 0.25
MAX_RANGE = 2.0
MIN_WEEKLY_DVOL = 250_000


# exchange suffix -> listing currency (fallback for names not in the master,
# i.e. delisted); minor units (pence / cents / agorot) as the FMP fx table names them
_SUFFIX_CCY = {"US": "USD", "L": "GBp", "T": "JPY", "HK": "HKD", "TO": "CAD", "V": "CAD", "CN": "CAD",
               "NE": "CAD", "AX": "AUD", "NZ": "NZD", "DE": "EUR", "F": "EUR", "PA": "EUR", "AS": "EUR",
               "BR": "EUR", "MI": "EUR", "MC": "EUR", "LS": "EUR", "VI": "EUR", "HE": "EUR", "IR": "EUR",
               "AT": "EUR", "ST": "SEK", "OL": "NOK", "CO": "DKK", "SW": "CHF", "WA": "PLN", "PR": "CZK",
               "BD": "HUF", "IS": "TRY", "TA": "ILA", "JO": "ZAc", "NS": "INR", "BO": "INR", "KS": "KRW",
               "KQ": "KRW", "TW": "TWD", "TWO": "TWD", "SS": "CNY", "SZ": "CNY", "SI": "SGD", "KL": "MYR",
               "BK": "THB", "JK": "IDR", "SA": "BRL", "MX": "MXN", "SN": "CLP", "BA": "ARS", "SR": "SAR",
               "QA": "QAR", "KW": "KWD", "AE": "AED", "CA": "EGP", "PS": "PHP", "VN": "VND"}


def attach_usd(p: pd.DataFrame) -> pd.DataFrame:
    """Add `usd`: USD per unit of the weekly panel's price, per symbol.

    The panel is in the LISTING currency, and FMP quotes London / Johannesburg
    / Tel Aviv lines in MINOR units (pence, cents, agorot) — so a raw dollar-
    volume floor of $250k/week meant Y250k for a Tokyo line and 250k PENCE for
    London. Currency = the master's listing-currency label, else the exchange
    suffix; a GBP / ZAR / ILS label on a .L / .JO / .TA line is the minor unit
    (the master's own price is in pence there while its market cap is in
    pounds, so it cannot be used as a bridge). Converted with the FMP spot table."""
    import os
    usd_unit = {}
    if os.path.exists("fmp_fx_usd.csv"):
        usd_unit = pd.read_csv("fmp_fx_usd.csv").set_index("currency")["usd_per_unit"].to_dict()
    syms = pd.Series(p["symbol"].unique())
    ccy = pd.Series(np.nan, index=syms.values, dtype=object)
    if os.path.exists("asymmetry_global.csv"):
        cols = pd.read_csv("asymmetry_global.csv", nrows=0).columns
        if "currency" in cols:
            m = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "currency"],
                            low_memory=False).drop_duplicates("symbol").set_index("symbol")["currency"]
            ccy = m.reindex(syms.values)
    suf = syms.map(_market).values
    ccy = ccy.where(ccy.notna(), pd.Series([_SUFFIX_CCY.get(x) for x in suf], index=syms.values))
    minor = {"L": ("GBP", "GBp"), "JO": ("ZAR", "ZAc"), "TA": ("ILS", "ILA")}
    fixed = [minor[sf][1] if (sf in minor and c == minor[sf][0]) else c for sf, c in zip(suf, ccy.values)]
    fac = pd.Series([usd_unit.get(c, np.nan) if isinstance(c, str) else np.nan for c in fixed],
                    index=syms.values)
    return p.assign(usd=p["symbol"].map(fac).astype(float))


def _market(sym: str) -> str:
    return sym.rsplit(".", 1)[1] if "." in sym else "US"


def _roll_slope(y: np.ndarray, win: int) -> np.ndarray:
    """OLS slope of y over the trailing `win` points (per point)."""
    n = len(y)
    out = np.full(n, np.nan)
    if n < win:
        return out
    x = np.arange(win, dtype=float)
    xm = x.mean()
    denom = ((x - xm) ** 2).sum()
    for i in range(win - 1, n):
        seg = y[i - win + 1:i + 1]
        if np.isnan(seg).any():
            continue
        out[i] = ((x - xm) * (seg - seg.mean())).sum() / denom
    return out


def symbol_panel(g: pd.DataFrame):
    with np.errstate(divide="ignore", invalid="ignore"):
        return _symbol_panel(g)


def latest_row(g: pd.DataFrame):
    """Current-week feature row (no base filter) for the live archetypes."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = _symbol_panel(g, snapshot=True)
    return r if isinstance(r, pd.DataFrame) else None


def _symbol_panel(g: pd.DataFrame, snapshot: bool = False):
    """Returns (base_rows DataFrame | None, premise dict)."""
    g = g.sort_values("week").reset_index(drop=True)
    n = len(g)
    if n < BASE_W + 30:
        return None, None
    c = g["close"].to_numpy(float)
    h = g["high"].to_numpy(float)
    lo = g["low"].to_numpy(float)
    v = g["volume"].to_numpy(float)
    # dollar volume in USD (NaN if the currency is unknown -> not tradeable-tested)
    _u = float(g["usd"].iloc[0]) if "usd" in g.columns and pd.notna(g["usd"].iloc[0]) else np.nan
    dv = g["dvol"].to_numpy(float) * _u
    s = pd.Series
    lr = np.log(c)
    ret = np.diff(lr, prepend=np.nan)
    hi104 = s(h).rolling(BASE_W).max().to_numpy()
    lo104 = s(lo).rolling(BASE_W).min().to_numpy()
    hi26 = s(h).rolling(26).max().to_numpy()
    lo26 = s(lo).rolling(26).min().to_numpy()
    r104 = c / s(c).shift(BASE_W).to_numpy() - 1
    r156 = c / s(c).shift(156).to_numpy() - 1
    hi156 = s(h).rolling(156).max().to_numpy()
    lo156 = s(lo).rolling(156).min().to_numpy()
    sd26 = s(ret).rolling(26).std().to_numpy()
    sd104 = s(ret).rolling(BASE_W).std().to_numpy()
    med_dv26 = s(dv).rolling(26).median().to_numpy()
    med_dv13 = s(dv).rolling(13).median().to_numpy()
    med_dv104 = s(dv).rolling(BASE_W).median().to_numpy()
    up = np.where(ret > 0, v, 0.0)
    dn = np.where(ret < 0, v, 0.0)
    _dn26 = s(dn).rolling(26).sum().to_numpy()
    updown = np.where(_dn26 > 0, s(up).rolling(26).sum().to_numpy() / _dn26, np.nan)
    obv = np.cumsum(np.sign(np.nan_to_num(ret)) * v)
    obv_n = obv / np.maximum(s(v).rolling(26).mean().to_numpy(), 1)   # in weeks-of-volume
    obv_slope = _roll_slope(obv_n, 26)
    px_slope = _roll_slope(lr, 26) * 26                                # log-return over 26w
    lows13 = s(lo).rolling(13).min().to_numpy()
    lows_slope = _roll_slope(np.log(np.maximum(lows13, 1e-9)), BASE_W) * 52
    hi5y_before = s(h).shift(BASE_W).rolling(156, min_periods=52).max().to_numpy()
    # forward outcomes (strictly after t)
    fmax13 = s(c[::-1]).rolling(13, min_periods=1).max().to_numpy()[::-1]
    fmax13 = np.append(fmax13[1:], np.nan)
    fmax26 = s(c[::-1]).rolling(26, min_periods=1).max().to_numpy()[::-1]
    fmax26 = np.append(fmax26[1:], np.nan)
    fmin52 = s(c[::-1]).rolling(52, min_periods=1).min().to_numpy()[::-1]
    fmin52 = np.append(fmin52[1:], np.nan)
    fwd13 = s(c).shift(-13).to_numpy() / c - 1
    fwd52 = s(c).shift(-52).to_numpy() / c - 1
    avail13 = np.arange(n) + 13 < n
    avail26 = np.arange(n) + 26 < n
    avail52 = np.arange(n) + 52 < n
    df = pd.DataFrame({
        "symbol": g["symbol"].iloc[0], "week": g["week"], "close": c,
        "r104": r104, "range104": hi104 / lo104, "r13": c / s(c).shift(13).to_numpy() - 1,
        "r26": c / s(c).shift(26).to_numpy() - 1,
        "vol_ratio": sd26 / sd104,
        "range_ratio": np.log(hi26 / lo26) / np.log(hi104 / lo104),
        "pos_in_range": (c - lo104) / (hi104 - lo104),
        "dist_high": c / hi104,
        "lows_slope": lows_slope,
        "updown_vol": updown,
        "obv_div": obv_slope - px_slope,
        "dvol_trend": np.where(med_dv104 > 0, med_dv13 / med_dv104, np.nan),
        "prior_dd": c / hi5y_before,
        "base_len_36": ((np.abs(r156) <= MAX_ABS_RET) & (hi156 / lo156 <= MAX_RANGE * 1.25)).astype(float),
        "med_dvol26": med_dv26,
        "ev2x_13w": np.where(avail13, (fmax13 / c >= 2.0).astype(float), np.nan),
        "ev3x_13w": np.where(avail13, (fmax13 / c >= 3.0).astype(float), np.nan),
        "ev2x_26w": np.where(avail26, (fmax26 / c >= 2.0).astype(float), np.nan),
        "fwd_13w": np.where(avail13, fwd13, np.nan),
        "fwd_52w": np.where(avail52, fwd52, np.nan),
        "fwd_dd_52w": np.where(avail52, fmin52 / c - 1, np.nan),
    })
    if snapshot:
        return df.iloc[[-1]]
    # month-end sampling: last available week of each calendar month
    df["ym"] = df["week"].dt.to_period("M")
    df = df.groupby("ym", sort=False).tail(1)
    base = ((df["r104"].abs() <= MAX_ABS_RET) & (df["range104"] <= MAX_RANGE)
            & (df["med_dvol26"] >= MIN_WEEKLY_DVOL))
    liquid = (df["med_dvol26"] >= MIN_WEEKLY_DVOL).fillna(False)
    # PREMISE check: of all liquid month-ends that went on to double within
    # 13 weeks, how many were sitting in a 2-year base (strict / loose)?
    loose = ((df["r104"].abs() <= 0.35) & (df["range104"] <= 2.5)).fillna(False)
    ev = (df["ev2x_13w"] == 1) & liquid
    ev3 = (df["ev3x_13w"] == 1) & liquid
    prem = {"symbol": g["symbol"].iloc[0], "liquid_months": int(liquid.sum()),
            "ev2x": int(ev.sum()), "ev2x_in_base": int((ev & base.fillna(False)).sum()),
            "ev2x_in_loose_base": int((ev & loose).sum()),
            "ev3x": int(ev3.sum()), "ev3x_in_base": int((ev3 & base.fillna(False)).sum())}
    df = df[base.fillna(False)].drop(columns="ym")
    return (df if len(df) else None), prem


def build_panel(prices_path: str = PRICES, out: str = PANEL, workers: int = 4) -> pd.DataFrame:
    from multiprocessing import Pool
    p = attach_usd(pd.read_parquet(prices_path))
    groups = [g for _, g in p.groupby("symbol", sort=False)]
    del p
    frames, prem = [], []
    with Pool(workers) as pool:
        for i, (r, pr) in enumerate(pool.imap_unordered(symbol_panel, groups, chunksize=64), 1):
            if r is not None:
                frames.append(r)
            if pr is not None:
                prem.append(pr)
            if i % 5000 == 0:
                print(f"  base panel: {i}/{len(groups)} symbols", flush=True)
    pd.DataFrame(prem).to_csv("base_premise.csv", index=False)
    d = pd.concat(frames, ignore_index=True)
    d["market"] = d["symbol"].map(_market)
    # relative strength vs same-market peers (cross-sectional median of r26,
    # computed on ALL base-months of that market in that month — a peer set
    # that exists at time t, so no look-ahead)
    d["ym"] = d["week"].dt.to_period("M")
    d["rs26"] = d["r26"] - d.groupby(["market", "ym"])["r26"].transform("median")
    d["size_dvol"] = np.log10(d["med_dvol26"])
    d = d.drop(columns="ym")
    d.to_parquet(out, index=False, compression="zstd")
    return d


if __name__ == "__main__":
    import sys
    d = build_panel()
    print(f"base-months: {len(d):,}  symbols: {d['symbol'].nunique():,}  "
          f"ev2x_13w rate: {d['ev2x_13w'].mean():.4f}  ev3x_13w: {d['ev3x_13w'].mean():.4f}",
          file=sys.stderr)
