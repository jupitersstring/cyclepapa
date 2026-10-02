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
  fqx_{opm,fcfm,gm,roic}_slope8 / _consist / _streak   trend shape over 8 quarters
  fqx_{opm,fcfm,gm,roic}_ttm                        the latest TTM level of the series
  fqx_m_since_{rev_accel,margin_inflect,turn_positive,share_shrink}   months since the
                         sign first appeared in the last 18 months; fqx_<sign>_now
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
    g = g.sort_values("date").copy()
    from unit_scale import normalize_shares
    g["shares_dil"] = normalize_shares(g["shares_dil"].tolist())
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
    # ---- TREND SHAPES over the last 8 quarters (the multibagger study's
    # tr_* measures): slope, consistency (share of quarters improving), the
    # current improving streak; on TTM series so seasonality cancels ----
    def ttm_series(col):
        v = g[col].to_numpy(float)
        out = np.full(n, np.nan)
        for i in range(per - 1, n):
            if np.all(np.abs(gaps[i - per + 1:i] - 365 / per) < 45) and np.all(np.isfinite(v[i - per + 1:i + 1])):
                out[i] = v[i - per + 1:i + 1].sum()
        return out
    T = {c: ttm_series(c) for c in ("revenue", "opinc", "fcf", "gp", "ni")}
    rev_t = np.where(T["revenue"] > 0, T["revenue"], np.nan)
    series = {"opm": T["opinc"] / rev_t, "fcfm": T["fcf"] / rev_t, "gm": T["gp"] / rev_t}
    eq = g.get("equity"); td = g.get("total_debt"); cs = g.get("cash_sti")
    if eq is not None:
        ic = (eq.fillna(np.nan).to_numpy(float) + (td.fillna(0).to_numpy(float) if td is not None else 0)
              - (cs.fillna(0).to_numpy(float) if cs is not None else 0))
        series["roic"] = np.where(ic > 0, T["opinc"] * 0.75 / np.where(ic > 0, ic, np.nan), np.nan)
    for k, s in series.items():
        if np.isfinite(s[-1]):
            rec[f"fqx_{k}_ttm"] = float(s[-1])          # the latest TTM level (one source for margin-vs-cycle gaps)
        w = s[-8:]
        ok = np.isfinite(w)
        if ok.sum() >= 5:
            x = np.arange(len(w), dtype=float)[ok]
            rec[f"fqx_{k}_slope8"] = float(np.polyfit(x, w[ok], 1)[0])
            dq = np.diff(s[-9:])
            dq = dq[np.isfinite(dq)]
            if len(dq) >= 4:
                rec[f"fqx_{k}_consist"] = float((dq > 0).mean())
                streak = 0
                for v in dq[::-1]:
                    if v > 0:
                        streak += 1
                    else:
                        break
                rec[f"fqx_{k}_streak"] = float(streak)
    # ---- SIGN TIMING (the forensic sequence): months since each sign FIRST
    # appeared inside the last 18 months (NaN = not in the window) ----
    yoy = np.full(n, np.nan)
    for i in range(n):
        j = _ya(d, i)
        if j is not None and np.isfinite(T["revenue"][i]) and T["revenue"][j] > 0:
            yoy[i] = T["revenue"][i] / T["revenue"][j] - 1
    def ya_val(arr, i):
        j = _ya(d, i)
        return arr[j] if j is not None else np.nan
    signs = {}
    for i in range(n):
        signs.setdefault("rev_accel", []).append(np.isfinite(yoy[i]) and np.isfinite(ya_val(yoy, i)) and yoy[i] - ya_val(yoy, i) >= 0.10)
        o, oy = series["opm"][i], ya_val(series["opm"], i)
        signs.setdefault("margin_inflect", []).append(np.isfinite(o) and np.isfinite(oy) and o - oy >= 0.03)
        turned = False
        for c in ("opinc", "ni", "fcf"):
            v, vy = T[c][i], ya_val(T[c], i)
            if np.isfinite(v) and np.isfinite(vy) and vy <= 0 < v:
                turned = True
        signs.setdefault("turn_positive", []).append(turned)
        sh, shy = g["shares_dil"].iloc[i], ya_val(g["shares_dil"].to_numpy(float), i)
        signs.setdefault("share_shrink", []).append(np.isfinite(sh) and np.isfinite(shy) and shy > 0 and sh / shy - 1 <= -0.02)
    last = d[-1]
    for k, flags in signs.items():
        idx = [i for i in range(n) if flags[i] and (last - d[i]).astype(int) <= 548]
        rec[f"fqx_{k}_now"] = float(bool(flags[-1]))
        if idx:
            rec[f"fqx_m_since_{k}"] = float((last - d[idx[0]]).astype(int) / 30.4)
    return rec


def main() -> None:
    p = pd.read_parquet("fmp_quarterly_panel.parquet",
                        columns=["symbol", "date", "revenue", "opinc", "ni", "fcf", "gp", "shares_dil",
                                 "equity", "total_debt", "cash_sti"])
    p["date"] = pd.to_datetime(p["date"])
    with np.errstate(divide="ignore", invalid="ignore"):
        rows = [one(g) for _, g in p.groupby("symbol", sort=False)]
    d = pd.DataFrame(rows)
    d.to_csv(OUT, index=False, float_format="%.6g")
    print(f"wrote {OUT}: {len(d)} rows;", {c: int(d[c].notna().sum()) for c in d.columns if c != "symbol"})


if __name__ == "__main__":
    main()
