"""The STORY of every stock at every month-end, point-in-time -> mb_panel.parquet
(input to multibagger_clusters.py: the latent-cluster study of the conditions
that PRECEDE multibagging).

Sample: the 10,160 symbols of the base-breakout case-control sample (every
symbol with a base explosion + 8,000 random controls; w_cc re-weights them to
the population), ALL liquid month-ends (no base requirement), 2012-06 on.

Outcomes (from the weekly split/dividend-adjusted closes; a level counts only
if HELD for 4 consecutive weeks, so a bad tick cannot make a multibagger):
  t3_12 / t3_24 / t3_36   reached 3x within 12 / 24 / 36 months
  t5_60                   reached 5x within 60 months
  months_to_3x            months until the 3x was first held (<= 36)
  fwd_ret_24, fwd_min_24  24-month return, worst close in 24 months (blow-up)
  Censoring: a still-trading name's window must be complete; a name that
  stopped trading (delisted) is OBSERVED through its last week — delisting
  is an outcome, not missing data.

Features — the story, not raw line items (all point-in-time: statements are
keyed on FILING date, 75 days after period end where FMP has none):
  tape       multi-horizon returns, distance from 52w / 5y highs, drawdown,
             volatility and its regime, dollar-volume level / trend / change
             point, up-vs-down volume, trend strength, position in range
  growth     TTM revenue 1y / 2y, latest-quarter YoY, acceleration (TTM and
             quarterly), EBIT / EPS growth, turning points (EBIT, NI, FCF)
  margins    gross / operating / FCF margin, their 1y and 2y changes,
             incremental margin, margin vs its own 5y median (cycle position)
  cash       FCF margin, CFO / NI (accrual quality), capex intensity and trend
  balance    net cash / mcap, net debt / EBITDA, debt change (deleveraging),
             current ratio, equity / assets, intangibles, Graham net-net / mcap
  capital    share-count change 1y / 3y (dilution / buyback), buyback and
             dividend yield, SBC / revenue
  efficiency ROIC, ROE and their change, asset turnover change, DSO / DIO /
             cash-cycle change, R&D and SG&A intensity
  valuation  P/S, EV/Sales, EV/EBIT, P/E, P/B, FCF and earnings yield — FMP's
             own period-end multiples (currency-consistent with the
             statements) rolled forward by the price move since the period
             end; P/S vs its own 3y median; 1y change in EV/Sales (re-/de-rating)
  people     employee growth, revenue-per-employee growth (SEC filers)
  perception analysts, buy share and its change, upgrades / downgrades /
             initiations, beats, surprise, ignored beats, reactions, target
             premium and revision, insider buying, new / increasing 13D holders
  states     interpretable composites ("cheap and net-cash", "over-levered and
             deleveraging", "diluting cash-burner", "fallen angel", ...)
"""
from __future__ import annotations

import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

import event_study_base as es
import event_study_pit as ep
import multibagger_fetch as mf

OUT = "mb_panel.parquet"
START = pd.Timestamp("2012-06-01")
LIQ_USD = 250_000          # median weekly USD dollar volume (the books' floor)
HOLD = 4                   # weeks a level must hold to count


# --------------------------------------------------------------------------
# quarterly statement frames
# --------------------------------------------------------------------------
def _frame(rows, cols) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    if "date" not in d.columns:
        return pd.DataFrame()
    d["period_end"] = pd.to_datetime(d["date"], errors="coerce")
    fd = pd.to_datetime(d.get("filingDate"), errors="coerce") if "filingDate" in d.columns else pd.Series(pd.NaT, index=d.index)
    d["avail"] = fd.where(fd.notna() & (fd > d["period_end"]), d["period_end"] + pd.Timedelta(days=75))
    if "reportedCurrency" in d.columns and d["reportedCurrency"].notna().any():
        cur = d.sort_values("period_end")["reportedCurrency"].dropna().iloc[-1]
        d = d[d["reportedCurrency"] == cur]
    d = d.dropna(subset=["period_end"]).drop_duplicates("period_end").sort_values("period_end")
    out = d[["period_end", "avail"]].copy()
    for c in cols:
        out[c] = pd.to_numeric(d.get(c), errors="coerce") if c in d.columns else np.nan
    return out.reset_index(drop=True)


def _ttm(q: pd.DataFrame, cols) -> pd.DataFrame:
    """TTM sums over 4 CONTIGUOUS quarters (gaps 70-120 days)."""
    gaps = q["period_end"].diff().dt.days
    contig = gaps.between(70, 120).astype(int).rolling(3).sum() == 3
    out = q[["period_end", "avail"]].copy()
    for c in cols:
        out[c] = q[c].rolling(4).sum().where(contig)
    return out


def _lag(s: pd.Series, pe: pd.Series, n: int) -> pd.Series:
    """s shifted n quarters back, only where the period ends ~n quarters apart."""
    ok = (pe - pe.shift(n)).dt.days.between(91 * n - 45, 91 * n + 45)
    return s.shift(n).where(ok)


def _safe_div(a, b):
    b = b.where(b != 0)
    return a / b


def quarterly_story(raw: dict, raw2: dict) -> pd.DataFrame:
    import fy_q4                      # FY-in-Q4 substitution -> true Q4
    is_rows, q4 = fy_q4.restore(raw.get("is"), "is")
    cf_rows, _ = fy_q4.restore(raw2.get("cf"), "cf", q4)
    raw = {**raw, "is": is_rows}
    raw2 = {**raw2, "cf": cf_rows}
    IS = _frame(raw.get("is"), ["revenue", "grossProfit", "operatingIncome", "netIncome", "ebitda",
                                "weightedAverageShsOutDil", "researchAndDevelopmentExpenses",
                                "sellingGeneralAndAdministrativeExpenses"])
    if len(IS) < 5:
        return pd.DataFrame()
    t = _ttm(IS, ["revenue", "grossProfit", "operatingIncome", "netIncome", "ebitda",
                  "researchAndDevelopmentExpenses", "sellingGeneralAndAdministrativeExpenses"])
    t["shares"] = IS["weightedAverageShsOutDil"].where(IS["weightedAverageShsOutDil"] > 0)
    from unit_scale import normalize_shares
    t["shares"] = normalize_shares(t["shares"].tolist())
    t["rev_q"] = IS["revenue"]
    pe = t["period_end"]
    rev, ebit, ni, gp = t["revenue"], t["operatingIncome"], t["netIncome"], t["grossProfit"]
    f = pd.DataFrame({"period_end": pe, "avail": t["avail"]})
    rev4, rev8 = _lag(rev, pe, 4), _lag(rev, pe, 8)
    f["rev_ttm"] = rev
    f["rev_g1"] = _safe_div(rev, rev4.where(rev4 > 0)) - 1
    f["rev_g2"] = (_safe_div(rev, rev8.where(rev8 > 0)) ** 0.5) - 1
    f["rev_g1_prev"] = _lag(f["rev_g1"], pe, 4)
    f["rev_accel"] = f["rev_g1"] - f["rev_g1_prev"]
    rq, rq4 = t["rev_q"], _lag(t["rev_q"], pe, 4)
    f["rev_q_yoy"] = _safe_div(rq, rq4.where(rq4 > 0)) - 1
    f["rev_q_accel"] = f["rev_q_yoy"] - _lag(f["rev_q_yoy"], pe, 1)
    f["gm"] = _safe_div(gp, rev.where(rev > 0))
    f["opm"] = _safe_div(ebit, rev.where(rev > 0))
    f["npm"] = _safe_div(ni, rev.where(rev > 0))
    f["gm_d1"] = f["gm"] - _lag(f["gm"], pe, 4)
    f["opm_d1"] = f["opm"] - _lag(f["opm"], pe, 4)
    f["opm_d2"] = f["opm"] - _lag(f["opm"], pe, 8)
    f["opm_vs_5y"] = f["opm"] - f["opm"].rolling(20, min_periods=8).median()
    dR, dE = rev - rev4, ebit - _lag(ebit, pe, 4)
    inc = _safe_div(dE, dR.where(dR > 0.03 * rev4.abs()))
    f["inc_margin"] = inc.where(inc.between(-2, 2))
    e4 = _lag(ebit, pe, 4)
    f["ebit_g1"] = (_safe_div(ebit, e4) - 1).where((ebit > 0) & (e4 > 0))
    f["ebit_turned"] = ((e4 <= 0) & (ebit > 0)).astype(float).where(e4.notna() & ebit.notna())
    n4 = _lag(ni, pe, 4)
    f["ni_turned"] = ((n4 <= 0) & (ni > 0)).astype(float).where(n4.notna() & ni.notna())
    eps = _safe_div(ni, t["shares"])
    eps4 = _lag(eps, pe, 4)
    f["eps_g1"] = (_safe_div(eps, eps4) - 1).where((eps > 0) & (eps4 > 0))
    f["rd_rev"] = _safe_div(t["researchAndDevelopmentExpenses"], rev.where(rev > 0))
    f["sga_rev"] = _safe_div(t["sellingGeneralAndAdministrativeExpenses"], rev.where(rev > 0))
    f["sga_rev_d1"] = f["sga_rev"] - _lag(f["sga_rev"], pe, 4)
    sh4, sh12 = _lag(t["shares"], pe, 4), _lag(t["shares"], pe, 12)
    f["share_g1"] = _safe_div(t["shares"], sh4) - 1
    f["share_g3"] = _safe_div(t["shares"], sh12) - 1
    f["ebit_ttm"], f["ni_ttm"], f["ebitda_ttm"] = ebit, ni, t["ebitda"]

    CF = _frame(raw2.get("cf"), ["operatingCashFlow", "capitalExpenditure", "freeCashFlow",
                                 "stockBasedCompensation", "commonStockRepurchased", "commonDividendsPaid",
                                 "depreciationAndAmortization", "netDebtIssuance"])
    if len(CF) >= 4:
        c = _ttm(CF, ["operatingCashFlow", "capitalExpenditure", "freeCashFlow", "stockBasedCompensation",
                      "commonStockRepurchased", "commonDividendsPaid", "depreciationAndAmortization"])
        c = c.drop(columns=["avail"]).rename(columns=lambda x: "cf_" + x if x != "period_end" else x)
        f = f.merge(c, on="period_end", how="left")
        r = f["rev_ttm"].where(f["rev_ttm"] > 0)
        fcf = f["cf_operatingCashFlow"] - f["cf_capitalExpenditure"].abs()
        f["fcf_ttm"] = fcf
        f["fcf_margin"] = fcf / r
        f["fcf_margin_d1"] = f["fcf_margin"] - _lag(f["fcf_margin"], f["period_end"], 4)
        fc4 = _lag(fcf, f["period_end"], 4)
        f["fcf_turned"] = ((fc4 <= 0) & (fcf > 0)).astype(float).where(fc4.notna() & fcf.notna())
        f["cfo_ni"] = (f["cf_operatingCashFlow"] / f["ni_ttm"].where(f["ni_ttm"] > 0)).where(
            lambda x: x.between(-5, 10))
        f["capex_rev"] = f["cf_capitalExpenditure"].abs() / r
        f["capex_rev_d1"] = f["capex_rev"] - _lag(f["capex_rev"], f["period_end"], 4)
        da = f["cf_depreciationAndAmortization"].where(f["cf_depreciationAndAmortization"] > 0)
        f["capex_da"] = (f["cf_capitalExpenditure"].abs() / da).where(lambda x: x < 20)
        f["sbc_rev"] = f["cf_stockBasedCompensation"].where(f["cf_stockBasedCompensation"] > 0) / r
        f["buyback_ttm"] = f["cf_commonStockRepurchased"].abs()
        f["div_ttm"] = f["cf_commonDividendsPaid"].abs()

    BS = _frame(raw2.get("bs"), ["cashAndShortTermInvestments", "totalDebt", "totalStockholdersEquity",
                                 "totalAssets", "totalCurrentAssets", "totalCurrentLiabilities", "inventory",
                                 "netReceivables", "goodwillAndIntangibleAssets", "totalLiabilities"])
    if len(BS):
        b = BS.drop(columns=["avail"]).rename(columns=lambda x: "bs_" + x if x != "period_end" else x)
        f = f.merge(b, on="period_end", how="left")
        pe2 = f["period_end"]
        debt, cash = f["bs_totalDebt"].fillna(0), f["bs_cashAndShortTermInvestments"]
        f["net_cash"] = cash - debt
        eb = f["ebitda_ttm"].where(f["ebitda_ttm"] > 0)
        f["nd_ebitda"] = ((debt - cash) / eb).where(lambda x: x.between(-50, 50))
        d4 = _lag(f["bs_totalDebt"], pe2, 4)
        f["debt_chg1"] = (_safe_div(f["bs_totalDebt"], d4.where(d4 > 0)) - 1).where(lambda x: x < 10)
        f["current_ratio"] = _safe_div(f["bs_totalCurrentAssets"], f["bs_totalCurrentLiabilities"].where(
            f["bs_totalCurrentLiabilities"] > 0)).where(lambda x: x < 50)
        ta = f["bs_totalAssets"].where(f["bs_totalAssets"] > 0)
        f["equity_assets"] = f["bs_totalStockholdersEquity"] / ta
        f["intang_assets"] = f["bs_goodwillAndIntangibleAssets"] / ta
        f["neg_equity"] = (f["bs_totalStockholdersEquity"] < 0).astype(float).where(
            f["bs_totalStockholdersEquity"].notna())
        ic = f["bs_totalStockholdersEquity"] + debt - cash.fillna(0)
        f["roic"] = (f["ebit_ttm"] * 0.75 / ic.where(ic > 0)).where(lambda x: x.between(-2, 5))
        f["roic_d1"] = f["roic"] - _lag(f["roic"], pe2, 4)
        eq = f["bs_totalStockholdersEquity"].where(f["bs_totalStockholdersEquity"] > 0)
        f["roe"] = (f["ni_ttm"] / eq).where(lambda x: x.between(-3, 3))
        f["asset_turn"] = f["rev_ttm"] / ta
        f["asset_turn_d1"] = f["asset_turn"] - _lag(f["asset_turn"], pe2, 4)
        r = f["rev_ttm"].where(f["rev_ttm"] > 0)
        f["dso"] = f["bs_netReceivables"] / r * 365
        f["dso_d1"] = f["dso"] - _lag(f["dso"], pe2, 4)
        f["inv_rev"] = f["bs_inventory"] / r
        f["inv_rev_d1"] = f["inv_rev"] - _lag(f["inv_rev"], pe2, 4)
        ncav = f["bs_totalCurrentAssets"] - f["bs_totalLiabilities"]
        f["ncav"] = ncav

    KM = _frame(raw2.get("km"), ["marketCap", "enterpriseValue"])
    if len(KM):
        k = KM.drop(columns=["avail"]).rename(columns={"marketCap": "km_mcap", "enterpriseValue": "km_ev"})
        f = f.merge(k, on="period_end", how="left")
    return f


def employees(raw2: dict) -> pd.DataFrame:
    e = pd.DataFrame(raw2.get("emp") or [])
    if not len(e) or "employeeCount" not in e.columns:
        return pd.DataFrame()
    e["avail"] = pd.to_datetime(e.get("filingDate"), errors="coerce")
    e["emp"] = pd.to_numeric(e["employeeCount"], errors="coerce")
    e["period"] = pd.to_datetime(e.get("periodOfReport"), errors="coerce")
    e = e.dropna(subset=["avail", "emp", "period"]).sort_values("period").drop_duplicates("period", keep="last")
    e = e[e["emp"] > 0]
    if len(e) < 2:
        return pd.DataFrame()
    # growth vs the report ~1y earlier (annual 10-K cadence or quarterly)
    left = e[["period"]].assign(key=e["period"] - pd.Timedelta(days=300)).sort_values("key")
    right = e[["period", "emp"]].rename(columns={"period": "p2", "emp": "emp_ya"}).sort_values("p2")
    m = pd.merge_asof(left, right, left_on="key", right_on="p2", direction="backward")
    m.index = left.index
    e["emp_ya"] = m["emp_ya"]
    ok = (e["period"] - m["p2"]).dt.days.between(300, 430)
    e["emp_g1"] = (e["emp"] / e["emp_ya"] - 1).where(ok)
    return e[["avail", "emp", "emp_g1", "emp_ya", "period"]].sort_values("avail")


# --------------------------------------------------------------------------
# weekly tape + outcomes
# --------------------------------------------------------------------------
def _roll_slope(y: pd.Series, n: int) -> pd.Series:
    x = pd.Series(np.arange(len(y), dtype=float), index=y.index)
    return y.rolling(n).cov(x) / x.rolling(n).var()


def tape(px: pd.DataFrame, last_global: pd.Timestamp) -> pd.DataFrame:
    px = px.sort_values("week").reset_index(drop=True)
    c = px["close"].astype(float).where(lambda x: x > 0)
    lc = np.log(c)
    hi = px["high"].astype(float).where(lambda x: x > 0).fillna(c)
    lo = px["low"].astype(float).where(lambda x: x > 0).fillna(c)
    dv = (px["dvol"].astype(float) * px["usd"]).where(lambda x: x > 0)
    lr = lc.diff()
    T = pd.DataFrame({"week": px["week"], "close": c})
    for k in (4, 13, 26, 52, 104, 156, 260):
        T[f"r{k}"] = c / c.shift(k) - 1
    T["dist_hi52"] = c / hi.rolling(52, min_periods=40).max()
    T["dist_hi260"] = c / hi.rolling(260, min_periods=104).max()
    T["up_lo52"] = c / lo.rolling(52, min_periods=40).min() - 1
    h104, l104 = hi.rolling(104, min_periods=80).max(), lo.rolling(104, min_periods=80).min()
    T["range104"] = h104 / l104
    T["pos104"] = (c - l104) / (h104 - l104)
    dd = c / c.rolling(104, min_periods=52).max()
    T["maxdd104"] = dd.rolling(104, min_periods=52).min() - 1
    T["vol13"] = lr.rolling(13).std() * np.sqrt(52)
    T["vol52"] = lr.rolling(52, min_periods=40).std() * np.sqrt(52)
    T["vol_ratio"] = T["vol13"] / T["vol52"]
    T["dvol26_usd"] = dv.rolling(26, min_periods=13).median()
    T["dvol_trend"] = dv.rolling(13, min_periods=8).median() / dv.rolling(52, min_periods=26).median()
    up = (lr > 0).astype(float)
    vol = px["volume"].astype(float)
    T["updown26"] = (vol * up).rolling(26).sum() / (vol * (1 - up)).rolling(26).sum().where(lambda x: x > 0)
    ldv = np.log(dv.clip(lower=1))
    mu, sd = ldv.shift(26).rolling(78, min_periods=52).mean(), ldv.shift(26).rolling(78, min_periods=52).std()
    T["dvol_z13"] = (ldv.rolling(13).mean() - mu) / sd.where(sd > 0)
    ma30 = c.rolling(30).mean()
    T["above_ma30"] = c / ma30 - 1
    T["ma30_slope13"] = ma30 / ma30.shift(13) - 1
    s26, s78 = _roll_slope(lc, 26), _roll_slope(lc, 78).shift(26)
    T["slope_brk"] = (s26 - s78) / (T["vol52"] / np.sqrt(52)).where(T["vol52"] > 0)
    x = pd.Series(np.arange(len(lc), dtype=float))
    T["trend_r2_52"] = lc.rolling(52, min_periods=40).corr(x) ** 2 * np.sign(_roll_slope(lc, 52))
    # ---- outcomes: forward max of a 4-week HELD level ----
    held = c.rolling(HOLD).min()
    n = len(c)
    cv, hv = c.to_numpy(float), held.to_numpy(float)
    last_week = px["week"].iloc[-1]
    delisted = last_week < last_global - pd.Timedelta(weeks=8)
    return T, cv, hv, delisted


def outcomes(idx: np.ndarray, cv: np.ndarray, hv: np.ndarray, delisted: bool) -> pd.DataFrame:
    n = len(cv)
    rows = []
    for i in idx:
        rec = {}
        c0 = cv[i]
        if not (np.isfinite(c0) and c0 > 0):
            rows.append(rec)
            continue
        for key, h, mult in (("t3_12", 52, 3), ("t3_24", 104, 3), ("t3_36", 156, 3), ("t5_60", 260, 5)):
            j1 = min(n, i + h + 1)
            seg = hv[i + HOLD:j1] if i + HOLD < j1 else np.array([])
            hit = bool(len(seg) and np.nanmax(seg) >= mult * c0) if len(seg) else False
            complete = (i + h < n) or delisted
            rec[key] = 1.0 if hit else (0.0 if complete else np.nan)
        seg = hv[i + HOLD:min(n, i + 157)]
        if len(seg):
            w = np.where(seg >= 3 * c0)[0]
            if len(w):
                rec["months_to_3x"] = (w[0] + HOLD) / 4.345
        if i + 104 < n:
            rec["fwd_ret_24"] = cv[i + 104] / c0 - 1
            rec["fwd_min_24"] = np.nanmin(cv[i + 1:i + 105]) / c0 - 1
        elif delisted and i + 1 < n:
            rec["fwd_min_24"] = np.nanmin(cv[i + 1:n]) / c0 - 1
        rows.append(rec)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
def one(args):
    sym, px, last_global = args
    try:
        return _one(sym, px, last_global)
    except Exception as exc:                      # one bad symbol must not stop the panel
        print(f"  {sym}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def _one(sym, px, last_global):
    if px is None or len(px) < 110:
        return None
    T, cv, hv, delisted = tape(px, last_global)
    wk = T["week"]
    me = T.groupby(wk.dt.to_period("M")).tail(1)
    me = me[(me["week"] >= START) & (me["dvol26_usd"] >= LIQ_USD)]
    if not len(me):
        return None
    idx = me.index.to_numpy()
    out = me.reset_index(drop=True)
    out.insert(0, "symbol", sym)
    out = pd.concat([out, outcomes(idx, cv, hv, delisted)], axis=1)
    raw = ep.fetch(sym)
    raw2 = mf.fetch_bs_cf(sym)
    q = quarterly_story(raw, raw2)
    if len(q):
        q = q.sort_values("avail")
        m = pd.merge_asof(out[["week"]].reset_index(), q, left_on="week", right_on="avail",
                          direction="backward").set_index("index")
        m = m.drop(columns=["week"])
        # the statements must be recent enough to describe the company now
        stale = (out["week"] - m["avail"]).dt.days > 270
        m.loc[stale.values, :] = np.nan
        # VALUATION at the month-end = FMP's period-end market cap / EV rolled
        # forward by the price move since the period end (currency-consistent
        # with the statements; net debt held at the period-end level)
        pe_close = pd.merge_asof(m[["period_end"]].dropna().reset_index().sort_values("period_end"),
                                 T[["week", "close"]].rename(columns={"close": "pe_close"}),
                                 left_on="period_end", right_on="week", direction="backward").set_index("index")
        ratio = out["close"] / pe_close["pe_close"].reindex(out.index)
        mcap = m["km_mcap"].where(m["km_mcap"] > 0) * ratio
        ev = mcap + (m["km_ev"] - m["km_mcap"])
        r = m["rev_ttm"].where(m["rev_ttm"] > 0)
        coh = (mcap / r).between(0.01, 200) | r.isna()        # ADR / listing-currency mismatch guard
        mcap = mcap.where(coh)
        ev = ev.where(coh)
        m["ps"] = mcap / r
        m["ev_sales"] = ev / r
        m["ev_ebit"] = (ev / m["ebit_ttm"].where(m["ebit_ttm"] > 0)).where(lambda x: x.between(0, 500))
        m["pe"] = (mcap / m["ni_ttm"].where(m["ni_ttm"] > 0)).where(lambda x: x < 1000)
        eqv = m.get("bs_totalStockholdersEquity")
        if eqv is not None:
            m["pb"] = (mcap / eqv.where(eqv > 0)).where(lambda x: x < 200)
        m["earn_yield"] = (m["ni_ttm"] / mcap).clip(-3, 3)
        if "fcf_ttm" in m.columns:
            m["fcf_yield"] = (m["fcf_ttm"] / mcap).clip(-3, 3)
            m["buyback_yield"] = (m["buyback_ttm"] / mcap).clip(0, 1)
            m["div_yield"] = (m["div_ttm"] / mcap).clip(0, 1)
        if "net_cash" in m.columns:
            m["netcash_mcap"] = (m["net_cash"] / mcap).clip(-10, 10)
            m["ncav_mcap"] = (m["ncav"] / mcap).clip(-10, 10)
        # size in USD: the reporting-currency market cap at today's spot
        m["mcap_usd_log"] = np.log10((mcap * _FX.get(_rep_ccy(raw), np.nan)).where(lambda x: x > 0))
        out = pd.concat([out, m], axis=1)
        # P/S vs its own history (period-end P/S over the prior 12 quarters)
        q2 = q.copy()
        if "km_mcap" in q2.columns:
            q2["ps_pe"] = q2["km_mcap"] / q2["rev_ttm"].where(q2["rev_ttm"] > 0)
            q2["evs_pe"] = q2["km_ev"] / q2["rev_ttm"].where(q2["rev_ttm"] > 0)
            q2["ps_med12"] = q2["ps_pe"].rolling(12, min_periods=6).median()
            q2["evs_pe_4"] = q2["evs_pe"].shift(4)
            h = pd.merge_asof(out[["week"]].reset_index(), q2[["avail", "ps_med12", "evs_pe_4"]].sort_values("avail"),
                              left_on="week", right_on="avail", direction="backward").set_index("index")
            out["ps_vs_own"] = out["ps"] / h["ps_med12"].where(h["ps_med12"] > 0)
            out["evs_chg_1y"] = out["ev_sales"] / h["evs_pe_4"].where(h["evs_pe_4"] > 0) - 1
    out["dvol_usd_log"] = np.log10(out["dvol26_usd"].clip(lower=1))
    E = employees(raw2)
    if len(E):
        e = pd.merge_asof(out[["week"]].reset_index(), E, left_on="week", right_on="avail",
                          direction="backward").set_index("index")
        fresh = (out["week"] - e["avail"]).dt.days <= 460
        out["emp_g1"] = e["emp_g1"].where(fresh)
        if "rev_ttm" in out.columns:
            # revenue per employee growth: TTM revenue now vs a year ago, over headcount growth
            out["rev_per_emp_g1"] = ((1 + out.get("rev_g1")) / (1 + out["emp_g1"]) - 1).where(fresh)
    # perception (the event study's point-in-time function)
    per = ep.features_for(sym, out["week"], out["r104"].fillna(0), raw, px[["week", "close"]])
    keep = ["n_analysts", "buy_share", "buy_share_d12", "upgrades_12m", "downgrades_12m", "initiations_12m",
            "months_since_up", "beats_4q", "surprise_4q", "beats_2y", "ignored_beats_2y", "react_beats_mean",
            "last_react", "pt_n_12m", "pt_prem_12m", "pt_rev_6m", "ins_buys_8q", "ins_buy_quarters_4q",
            "ins_net_buy_4q", "bo_new_holders_12m", "bo_increasing_12m"]
    out = pd.concat([out, per.reindex(columns=keep)], axis=1)
    drop = [c for c in out.columns if c.startswith(("bs_", "cf_", "km_"))]
    return out.drop(columns=[c for c in drop if c in out.columns])


_FX = (pd.read_csv("fmp_fx_usd.csv").set_index("currency")["usd_per_unit"].to_dict()
       if os.path.exists("fmp_fx_usd.csv") else {})


def _rep_ccy(raw: dict):
    rows = [r for r in (raw.get("is") or []) if r.get("reportedCurrency")]
    return max(rows, key=lambda r: r.get("date", ""))["reportedCurrency"] if rows else None


def states(d: pd.DataFrame) -> pd.DataFrame:
    """Interpretable composite STATES (the story in words). Each is a flag on
    point-in-time features; the clustering sees them alongside the continuous
    features, and they label the clusters in the report."""
    g = lambda c: d[c] if c in d.columns else pd.Series(np.nan, index=d.index)
    S = pd.DataFrame(index=d.index)
    S["st_cheap_netcash"] = ((g("netcash_mcap") >= 0.25) & ((g("ev_ebit") <= 8) | (g("pb") <= 1.0)
                                                            | (g("ev_sales") <= 0.5)))
    S["st_net_net"] = (g("ncav_mcap") >= 1.0)
    S["st_overlevered_delevering"] = ((g("nd_ebitda") >= 3.5) & (g("debt_chg1") <= -0.10))
    S["st_overlevered_stressed"] = ((g("nd_ebitda") >= 5) | (g("neg_equity") == 1)) & ~(g("debt_chg1") <= -0.10)
    S["st_diluting_burner"] = (g("share_g1") >= 0.10) & (g("fcf_margin") < 0)
    S["st_fallen_angel"] = g("dist_hi260") <= 0.40
    S["st_near_highs"] = g("dist_hi52") >= 0.90
    S["st_turnaround"] = (g("ebit_turned") == 1) | (g("ni_turned") == 1) | (g("fcf_turned") == 1)
    S["st_hypergrowth"] = g("rev_g1") >= 0.40
    S["st_accelerating"] = (g("rev_accel") >= 0.10) | (g("rev_q_accel") >= 0.10)
    S["st_margin_inflect_derated"] = (g("opm_d1") >= 0.03) & (g("evs_chg_1y") <= -0.20)
    S["st_cyclical_trough"] = (g("opm_vs_5y") <= -0.05) & (g("rev_accel") > 0)
    S["st_compounder"] = (g("roic") >= 0.15) & (g("rev_g1") >= 0.10) & (g("share_g3") <= 0.05)
    S["st_cannibal"] = g("share_g1") <= -0.03
    S["st_neglected"] = ~(g("n_analysts") > 1)
    S["st_accumulation"] = (g("dvol_z13") >= 1.0) & (g("r13") > 0)
    S["st_flat_base"] = (g("r104").abs() <= 0.25) & (g("range104") <= 2.0)
    S["st_deep_value"] = (g("ev_ebit").between(0, 6)) | (g("pb").between(0, 0.7)) | (g("ps") <= 0.3)
    S["st_expensive"] = (g("ps") >= 10) | (g("ev_ebit") >= 40)
    S["st_insider_buying"] = g("ins_buy_quarters_4q") >= 2
    S["st_new_activist"] = g("bo_new_holders_12m") >= 1
    S["st_headcount_growth"] = g("emp_g1") >= 0.15
    S["st_productivity_gain"] = g("rev_per_emp_g1") >= 0.15
    return S.astype(float)


def main(workers: int = 4) -> None:
    samp = pd.read_parquet("base_panel_pit.parquet", columns=["symbol", "w_cc"]).drop_duplicates("symbol")
    syms = set(samp["symbol"])
    px = pd.read_parquet(es.PRICES, columns=["symbol", "week", "high", "low", "close", "volume", "dvol"])
    px = px[px["symbol"].isin(syms)]
    last_global = px["week"].max()
    px = es.attach_usd(px)
    groups = [(s, g, last_global) for s, g in px.groupby("symbol", sort=False)]
    del px
    print(f"story: {len(groups)} symbols; prices through {last_global.date()}", flush=True)
    parts = []
    with Pool(workers) as pool:
        for i, r in enumerate(pool.imap_unordered(one, groups, chunksize=16), 1):
            if r is not None and len(r):
                parts.append(r)
            if i % 1000 == 0:
                print(f"  {i}/{len(groups)}", flush=True)
    d = pd.concat(parts, ignore_index=True)
    d = d.merge(samp, on="symbol", how="left")
    # relative strength vs the market's median 26w return that month
    d["_m"] = d["week"].dt.to_period("M")
    d["market"] = d["symbol"].map(es._market)
    d["rs26"] = d["r26"] - d.groupby(["_m", "market"])["r26"].transform("median")
    d = d.drop(columns=["_m"])
    d = pd.concat([d, states(d)], axis=1)
    d.to_parquet(OUT, index=False, compression="zstd")
    print(f"wrote {OUT}: {len(d):,} month-ends, {d['symbol'].nunique():,} symbols; "
          f"t3_24 rate {d['t3_24'].mean():.4f}", flush=True)


if __name__ == "__main__":
    main()
