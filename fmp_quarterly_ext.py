"""Growth-quality measures from the quarterly 3-statement panel (no API calls)
-> fmp_quarterly_ext.csv (fqx_*).

Reads fmp_quarterly_panel.parquet (placeholder periods already blanked by the
engine). Every year-on-year comparison is DATE-matched (the same quarter a
year earlier, 365 +/- 45 days) and only between contiguous quarterly periods,
so half-yearly filers are handled as their own cadence.

  fqx_eps_q_yoy          latest period diluted EPS vs the same period a year ago
                         (positive base only; a loss->profit turn is fqx_eps_turned)
  fqx_eps_q_yoy_prev     the same for the previous period
  fqx_eps_accel          fqx_eps_q_yoy - fqx_eps_q_yoy_prev (O'Neil "accelerating")
  fqx_eps_pos_share_8    share of the last 8 periods with EPS up YoY
  fqx_eps_turned         latest period EPS > 0 after <= 0 a year earlier
  fqx_ebit_ttm_g         TTM operating income now vs a year ago (both > 0)
  fqx_ni_ttm_g           TTM net income now vs a year ago (both > 0)
  fqx_inc_ebit_margin    change in TTM EBIT / change in TTM revenue (revenue up >= 3%)
  fqx_fcf_ps_g           TTM FCF per diluted share now vs a year ago (both > 0)
  fqx_roic_ttm           TTM EBIT x 0.75 / (equity + total debt - cash), latest balance sheet
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OUT = "fmp_quarterly_ext.csv"


def _ya(dates: np.ndarray, i: int):
    target = dates[i] - np.timedelta64(365, "D")
    j = np.where(np.abs((dates - target).astype("timedelta64[D]").astype(int)) <= 45)[0]
    j = j[j < i]
    return int(j[-1]) if len(j) else None


def one(g: pd.DataFrame) -> dict:
    g = g.sort_values("date")
    d = g["date"].to_numpy("datetime64[D]")
    n = len(g)
    rec = {"symbol": g["symbol"].iloc[0]}
    if n < 5:
        return rec
    gaps = np.diff(d).astype(int)
    per = 4 if np.median(gaps) < 130 else 2
    eps = (g["ni"] / g["shares_dil"].where(g["shares_dil"] > 0)).to_numpy(float)

    def yoy(i):
        j = _ya(d, i)
        if j is None or not (np.isfinite(eps[i]) and np.isfinite(eps[j])):
            return np.nan, None
        return (eps[i] / eps[j] - 1 if eps[j] > 0 else np.nan), j

    cur, j0 = yoy(n - 1)
    prev, _ = yoy(n - 2)
    rec["fqx_eps_q_yoy"], rec["fqx_eps_q_yoy_prev"] = cur, prev
    if np.isfinite(cur) and np.isfinite(prev):
        rec["fqx_eps_accel"] = cur - prev
    if j0 is not None and np.isfinite(eps[n - 1]) and np.isfinite(eps[j0]):
        rec["fqx_eps_turned"] = float(eps[j0] <= 0 < eps[n - 1])
    ups = []
    for i in range(max(0, n - 8), n):
        j = _ya(d, i)
        if j is not None and np.isfinite(eps[i]) and np.isfinite(eps[j]):
            ups.append(eps[i] > eps[j])
    if len(ups) >= 4:
        rec["fqx_eps_pos_share_8"] = float(np.mean(ups))
    # TTM sums over the last `per` contiguous periods and the year-ago window
    if n >= 2 * per:
        def ttm(col, end):
            seg = g[col].iloc[end - per + 1:end + 1]
            return float(seg.sum()) if seg.notna().all() else np.nan
        ok_now = np.all(np.abs(gaps[-(per - 1):] - 365 / per) < 45) if per > 1 else True
        ok_ya = np.all(np.abs(gaps[-(2 * per - 1):-(per)] - 365 / per) < 45) if per > 1 else True
        if ok_now and ok_ya:
            e, ey = ttm("opinc", n - 1), ttm("opinc", n - 1 - per)
            r_, ry = ttm("revenue", n - 1), ttm("revenue", n - 1 - per)
            ni_, niy = ttm("ni", n - 1), ttm("ni", n - 1 - per)
            f_, fy = ttm("fcf", n - 1), ttm("fcf", n - 1 - per)
            sh, shy = g["shares_dil"].iloc[-1], g["shares_dil"].iloc[-1 - per]
            if e > 0 and ey > 0:
                rec["fqx_ebit_ttm_g"] = e / ey - 1
            if ni_ > 0 and niy > 0:
                rec["fqx_ni_ttm_g"] = ni_ / niy - 1
            if np.isfinite(r_) and np.isfinite(ry) and ry > 0 and r_ / ry - 1 >= 0.03 and np.isfinite(e) and np.isfinite(ey):
                rec["fqx_inc_ebit_margin"] = float(np.clip((e - ey) / (r_ - ry), -5, 5))
            if f_ > 0 and fy > 0 and sh > 0 and shy > 0:
                rec["fqx_fcf_ps_g"] = (f_ / sh) / (fy / shy) - 1
            last = g.iloc[-1]
            ic = last.get("equity", np.nan) + (last.get("total_debt", 0) or 0) - (last.get("cash_sti", 0) or 0)
            if np.isfinite(e) and np.isfinite(ic) and ic > 0:
                rec["fqx_roic_ttm"] = float(np.clip(e * 0.75 / ic, -2, 5))
    return rec


def main() -> None:
    p = pd.read_parquet("fmp_quarterly_panel.parquet",
                        columns=["symbol", "date", "revenue", "opinc", "ni", "fcf", "shares_dil",
                                 "equity", "total_debt", "cash_sti"])
    p["date"] = pd.to_datetime(p["date"])
    with np.errstate(divide="ignore", invalid="ignore"):
        rows = [one(g) for _, g in p.groupby("symbol", sort=False)]
    d = pd.DataFrame(rows)
    d.to_csv(OUT, index=False, float_format="%.6g")
    print(f"wrote {OUT}: {len(d)} rows;", {c: int(d[c].notna().sum()) for c in d.columns if c != "symbol"})


if __name__ == "__main__":
    main()
