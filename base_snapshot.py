"""Live snapshot of the base / coil measures for every current name ->
base_snapshot.csv (bs_* columns), read by archetype_tags.

Price legs come from the weekly panel (fmp_weekly_prices.parquet, or the
in-progress parts), computed exactly as in the event study (event_study_base)
so the live archetype and the backtest measure the same thing. Fundamental
coil comes from the quarterly 3-statement panel: TTM revenue / operating
income now vs eight quarters earlier, set against the 104-week price return.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

import event_study_base as es


def _prices() -> pd.DataFrame:
    if os.path.exists(es.PRICES):
        return pd.read_parquet(es.PRICES)
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob("fmp_price_parts/*.parquet"))],
                     ignore_index=True)


def _ttm_2y(panel: pd.DataFrame) -> pd.DataFrame:
    """TTM revenue / EBIT now and eight quarters earlier (contiguous quarters)."""
    p = panel.sort_values(["symbol", "date"]).copy()
    p["date"] = pd.to_datetime(p["date"])
    out = []
    for sym, g in p.groupby("symbol", sort=False):
        g = g.tail(13)
        if len(g) < 12:
            continue
        gaps = g["date"].diff().dt.days.iloc[1:]
        if not gaps.between(70, 120).all():
            continue
        now, then = g.iloc[-4:], g.iloc[-12:-8]
        rec = {"symbol": sym, "bs_rev_ttm": now["revenue"].sum(), "bs_rev_ttm_2y": then["revenue"].sum(),
               "bs_ebit_ttm": now["opinc"].sum(), "bs_ebit_ttm_2y": then["opinc"].sum()}
        out.append(rec)
    return pd.DataFrame(out)


def build(out: str = "base_snapshot.csv") -> pd.DataFrame:
    from multiprocessing import Pool
    p = es.attach_usd(_prices())
    groups = [g for _, g in p.groupby("symbol", sort=False)]
    del p
    with Pool(4) as pool:
        rows = [r for r in pool.imap_unordered(es.latest_row, groups, chunksize=64) if r is not None]
    d = pd.concat(rows, ignore_index=True)
    # the snapshot must be CURRENT: a series that stopped trading is not a live base
    d = d[d["week"] >= d["week"].max() - pd.Timedelta(days=21)].copy()
    d["market"] = d["symbol"].map(es._market)
    d["rs26"] = d["r26"] - d.groupby("market")["r26"].transform("median")
    d["size_dvol"] = np.log10(d["med_dvol26"].where(d["med_dvol26"] > 0))
    keep = ["symbol", "week", "r104", "range104", "r13", "r26", "vol_ratio", "range_ratio", "pos_in_range",
            "dist_high", "lows_slope", "updown_vol", "obv_div", "dvol_trend", "prior_dd", "base_len_36",
            "med_dvol26", "rs26", "size_dvol"]
    d = d[keep].rename(columns={c: "bs_" + c for c in keep if c != "symbol"})
    d["bs_is_base"] = ((d["bs_r104"].abs() <= es.MAX_ABS_RET) & (d["bs_range104"] <= es.MAX_RANGE)).astype(int)
    if os.path.exists("fmp_quarterly_panel.parquet"):
        f = _ttm_2y(pd.read_parquet("fmp_quarterly_panel.parquet",
                                    columns=["symbol", "date", "revenue", "opinc"]))
        d = d.merge(f, on="symbol", how="left")
        with np.errstate(divide="ignore", invalid="ignore"):
            ok = (d["bs_rev_ttm"] > 0) & (d["bs_rev_ttm_2y"] > 0)
            d["bs_rev_g_2y"] = (d["bs_rev_ttm"] / d["bs_rev_ttm_2y"] - 1).where(ok)
            # fundamentals compounding under the price: + = the multiple coiled
            d["bs_coil_rev"] = (np.log(d["bs_rev_ttm"] / d["bs_rev_ttm_2y"]) - np.log1p(d["bs_r104"])).where(ok)
            okE = (d["bs_ebit_ttm"] > 0) & (d["bs_ebit_ttm_2y"] > 0)
            d["bs_coil_ebit"] = (np.log(d["bs_ebit_ttm"] / d["bs_ebit_ttm_2y"]) - np.log1p(d["bs_r104"])).where(okE)
            d["bs_ebit_turned"] = ((d["bs_ebit_ttm_2y"] <= 0) & (d["bs_ebit_ttm"] > 0)).astype(float) \
                .where(d["bs_ebit_ttm"].notna() & d["bs_ebit_ttm_2y"].notna())
        d = d.drop(columns=["bs_rev_ttm", "bs_rev_ttm_2y", "bs_ebit_ttm", "bs_ebit_ttm_2y"])
    d.to_csv(out, index=False, float_format="%.6g")
    return d


if __name__ == "__main__":
    d = build()
    print(f"base_snapshot: {len(d)} names; in a 2y base now: {int(d['bs_is_base'].sum())}")
