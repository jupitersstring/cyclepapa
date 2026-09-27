"""USD outcome labels for the multibagger panel -> mb_labels_usd.parquet

The panel's outcomes (t3_24, t10_60, fwd_mult_*, fwd_min_24 ...) are in the
LISTING currency. In a debasing currency a "3x" is partly the currency: 72%
of Turkish month-ends in 2021 "tripled" in lira while the lira lost three
quarters of its dollar value. So every outcome is recomputed in USD, from
the same spike-cleaned weekly closes, converted week by week with FMP's
forex history (USDTRY, EURUSD, ... ; London / Johannesburg / Tel Aviv minor
units divided by 100), at exactly the panel's month-end rows.

  mb_labels_usd.parquet: symbol, week, t3_12, t3_24, t3_36, t5_60,
                         fwd_mult_24, fwd_mult_60, months_to_3x, fwd_ret_24,
                         fwd_min_24, usd_per_unit  (all USD)

multibagger_clusters.load() merges these over the local-currency columns
unless MB_LOCAL=1 (the local ones are kept as <col>_local).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

import event_study_base as es
import fmp_client as fc
import price_hygiene
from multibagger_story import outcomes

OUT = "mb_labels_usd.parquet"
PANEL = "mb_panel.parquet"
MINOR = {"GBp": ("GBP", 100.0), "ZAc": ("ZAR", 100.0), "ZAC": ("ZAR", 100.0), "ILA": ("ILS", 100.0)}


def symbol_currency(syms: pd.Index) -> pd.Series:
    """Listing currency per symbol, the way event_study_base.attach_usd
    resolves it (master label -> alias override -> exchange suffix; minor-unit
    lines on .L / .JO / .TA)."""
    ccy = pd.Series(np.nan, index=syms, dtype=object)
    if os.path.exists("asymmetry_global.csv"):
        m = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "currency"],
                        low_memory=False).drop_duplicates("symbol").set_index("symbol")["currency"]
        ccy = m.reindex(syms)
    if os.path.exists("fmp_symbol_map.csv"):
        am = pd.read_csv("fmp_symbol_map.csv")
        am = am[(am["use_for_prices"] == 1) & am["fmp_currency"].notna()].drop_duplicates("symbol")
        over = am.set_index("symbol")["fmp_currency"].reindex(syms)
        ccy = over.where(over.notna(), ccy)
    suf = pd.Series([es._market(s) for s in syms], index=syms)
    ccy = ccy.where(ccy.notna(), suf.map(es._SUFFIX_CCY))
    minor = {"L": ("GBP", "GBp"), "JO": ("ZAR", "ZAc"), "TA": ("ILS", "ILA")}
    fixed = [minor[sf][1] if (sf in minor and c == minor[sf][0]) else c for sf, c in zip(suf.values, ccy.values)]
    return pd.Series(fixed, index=syms, dtype=object)


def fx_weekly(currencies) -> pd.DataFrame:
    """USD per unit of each currency by week (W-FRI, forward-filled), from
    FMP's forex history; either quote direction, inverted as needed."""
    frames = {}
    for c in sorted({c for c in currencies if isinstance(c, str)}):
        major, div = MINOR.get(c, (c, 1.0))
        if major == "USD":
            continue
        ser = None
        for pair, invert in ((f"USD{major}", True), (f"{major}USD", False)):
            try:
                r = fc.get_json("historical-price-eod/light", {"symbol": pair, "from": "2010-01-01"}, ttl=fc.TTL_SLOW) or []
            except fc.FMPError:
                r = []
            if len(r) < 200:
                continue
            d = pd.DataFrame(r)
            d["date"] = pd.to_datetime(d["date"]); d["price"] = pd.to_numeric(d["price"], errors="coerce")
            s = d.set_index("date")["price"].where(lambda x: x > 0).dropna().sort_index()
            ser = (1.0 / s) if invert else s
            break
        if ser is None:
            print(f"  no FX history for {c}", file=sys.stderr, flush=True)
            continue
        frames[c] = ser.resample("W-FRI").last().ffill() / div
    fx = pd.DataFrame(frames)
    fx.index.name = "week"
    return fx


def main():
    import pyarrow.parquet as pq
    keys = pq.read_table(PANEL, columns=["symbol", "week"]).to_pandas()
    keys["week"] = pd.to_datetime(keys["week"])
    syms = pd.Index(keys["symbol"].unique())
    ccy = symbol_currency(syms)
    print(f"usd labels: {len(syms):,} symbols, {len(keys):,} month-ends; currencies {ccy.value_counts().head(12).to_dict()}", flush=True)
    fx = fx_weekly(ccy.unique())
    print(f"  fx: {fx.shape[1]} currencies, {fx.index.min().date()} .. {fx.index.max().date()}", flush=True)
    px = pd.read_parquet(es.PRICES, columns=["symbol", "week", "close"])
    px = px[px["symbol"].isin(syms)]
    px = price_hygiene.clean_weekly(px).drop(columns=["px_spike"])
    px["week"] = pd.to_datetime(px["week"])
    last_global = px["week"].max()
    fxw = fx.reindex(pd.date_range(fx.index.min(), max(fx.index.max(), last_global), freq="W-FRI")).ffill()
    want = keys.groupby("symbol")["week"].apply(lambda s: set(s.values)).to_dict()
    rows = []
    n = 0
    for sym, g in px.groupby("symbol", sort=False):
        c = ccy.get(sym)
        if not isinstance(c, str):
            continue
        g = g.sort_values("week").reset_index(drop=True)
        if c == "USD":
            rate = pd.Series(1.0, index=g.index)
        else:
            if c not in fxw.columns:
                continue
            rate = fxw[c].reindex(g["week"]).to_numpy()
            rate = pd.Series(rate, index=g.index).ffill().bfill()
        cu = (g["close"].astype(float).where(lambda x: x > 0) * rate.to_numpy())
        held = cu.rolling(4).min()
        cv, hv = cu.to_numpy(float), held.to_numpy(float)
        delisted = g["week"].iloc[-1] < last_global - pd.Timedelta(weeks=8)
        wk = set(want.get(sym, ()))
        idx = np.flatnonzero(g["week"].isin(wk).to_numpy())
        if not len(idx):
            continue
        o = outcomes(idx, cv, hv, delisted)
        o.insert(0, "week", g["week"].iloc[idx].to_numpy())
        o.insert(0, "symbol", sym)
        o["usd_per_unit"] = rate.iloc[idx].to_numpy()
        rows.append(o)
        n += 1
        if n % 5000 == 0:
            print(f"  {n:,} symbols", flush=True)
    out = pd.concat(rows, ignore_index=True)
    for col in ("t3_12", "t3_24", "t3_36", "t5_60", "fwd_mult_24", "fwd_mult_60", "months_to_3x", "fwd_ret_24", "fwd_min_24"):
        if col not in out.columns:
            out[col] = np.nan
    out["t10_60"] = (out["fwd_mult_60"] >= 10).astype(float).where(out["fwd_mult_60"].notna())
    out.to_parquet(OUT, index=False)
    m = out.merge(keys, on=["symbol", "week"], how="inner")
    print(f"wrote {OUT}: {len(out):,} rows ({len(m):,} matched panel month-ends); "
          f"3x/24m rate USD {out['t3_24'].mean():.2%}", flush=True)
    print("USD_LABELS_DONE", flush=True)


if __name__ == "__main__":
    main()
