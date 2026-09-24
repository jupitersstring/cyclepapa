"""Granular three-statement engine (quarterly / half-yearly) -> fmp_quarterly.csv
                                                         + fmp_quarterly_panel.parquet

Why: the forensic / XR archetypes read balance-sheet and cash-flow detail
(working capital, deferred revenue, retained earnings, PP&E, goodwill, cash
taxes paid, discontinued ops, assets, equity) that today comes from EDGAR only:
0% coverage outside the US, 20-40% inside it. FMP's periodic statements carry
all of it globally, and at quarterly granularity they also allow the classic
forensic-accounting tests we could not run: Beneish M-score, Sloan accruals,
receivables / inventory vs sales divergence, cash vs book tax, and trajectories
(net-debt paydown, gross-margin streaks) rather than point snapshots.

ROBUSTNESS RULES (each guards a known failure mode)
  * Point-in-time: a period counts only if its filingDate is on or before
    today (no restated-in-the-future or pre-announced periods).
  * One currency: every period used must share the latest period's
    reportedCurrency; a currency change mid-series breaks the comparison.
  * Cadence detected, not assumed: quarterly filers (~91-day spacing) sum
    4 periods for TTM, half-yearly filers (~182-day spacing, common in
    Europe/Australia/HK) sum 2. Anything else -> no TTM.
  * Contiguity: a TTM window must cover ~12 months with no missing period
    (period gaps within cadence +/- 45 days); year-ago windows must end
    ~12 months before the latest one. Otherwise the metric is NaN, never
    guessed.
  * Staleness: the latest period must be <= 9 months old (quarterly) or
    <= 12 months (half-yearly), else the name is marked stale and emits
    nothing forensic.
  * Dimensionless outputs: forensic metrics are ratios of statement items to
    each other, so currency cancels. Levels are emitted in the reporting
    currency with the currency code, and the archetype layer converts them
    to the master's currency via a revenue anchor before any comparison
    with market cap.
  * Beneish inputs are winsorised to [0.25, 4.0] (standard practice: a ratio
    of two tiny bases is not information) and M is emitted only when the
    five core variables are present.

Resumable: symbols already in fmp_quarterly.csv are skipped.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_quarterly.csv"
PANEL = "fmp_quarterly_panel.parquet"
_PANEL_PART_DIR = "fmp_quarterly_panel_parts"
TODAY = dt.date.today()

# flow fields (summed over a TTM window)
IS_FLOWS = {"revenue": "revenue", "costOfRevenue": "cogs", "grossProfit": "gp",
            "operatingIncome": "opinc", "ebitda": "ebitda", "netIncome": "ni",
            "netIncomeFromContinuingOperations": "ni_cont",
            "netIncomeFromDiscontinuedOperations": "ni_disc",
            "incomeBeforeTax": "pretax", "incomeTaxExpense": "tax_exp",
            "interestExpense": "int_exp",
            "sellingGeneralAndAdministrativeExpenses": "sga",
            "researchAndDevelopmentExpenses": "rnd"}
CF_FLOWS = {"operatingCashFlow": "cfo", "capitalExpenditure": "capex",
            "freeCashFlow": "fcf", "depreciationAndAmortization": "da",
            "stockBasedCompensation": "sbc", "incomeTaxesPaid": "taxes_paid",
            "commonStockRepurchased": "buyback", "commonDividendsPaid": "dividends",
            "acquisitionsNet": "acquisitions", "changeInWorkingCapital": "chg_wc"}
# stock fields (point-in-time balance)
BS_STOCKS = {"netReceivables": "receivables", "inventory": "inventory",
             "accountPayables": "payables", "totalCurrentAssets": "cur_assets",
             "totalCurrentLiabilities": "cur_liab", "totalAssets": "total_assets",
             "propertyPlantEquipmentNet": "ppe_net",
             "goodwillAndIntangibleAssets": "gw_intang",
             "deferredRevenue": "defrev_cur", "deferredRevenueNonCurrent": "defrev_nc",
             "longTermDebt": "lt_debt", "totalDebt": "total_debt",
             "cashAndShortTermInvestments": "cash_sti",
             "totalStockholdersEquity": "equity", "retainedEarnings": "retained_earnings",
             "totalLiabilities": "total_liab", "minorityInterest": "minority"}


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _clean(rows, ccy=None):
    """Newest-first, point-in-time, single-currency, de-duplicated periods."""
    out, seen = [], set()
    for r in rows or []:
        d = _d(r.get("date"))
        fd = _d(r.get("filingDate") or r.get("acceptedDate") or r.get("date"))
        if d is None or d in seen or d > TODAY or (fd and fd > TODAY):
            continue
        seen.add(d)
        out.append((d, r))
    out.sort(key=lambda t: t[0], reverse=True)
    if not out:
        return [], None
    ccy = ccy or out[0][1].get("reportedCurrency")
    out = [(d, r) for d, r in out if r.get("reportedCurrency") in (ccy, None)]
    return out, ccy


def _cadence(periods):
    if len(periods) < 3:
        return None
    gaps = [(periods[i][0] - periods[i + 1][0]).days for i in range(min(6, len(periods) - 1))]
    g = float(np.median(gaps))
    if 70 <= g <= 120:
        return 4, g
    if 150 <= g <= 215:
        return 2, g
    return None


def _window(periods, n, start, spacing):
    """n contiguous periods starting at index `start`, else None."""
    w = periods[start:start + n]
    if len(w) < n:
        return None
    for a, b in zip(w, w[1:]):
        if abs((a[0] - b[0]).days - spacing) > 45:
            return None
    return w


def _ttm(periods, n, spacing, field, year_ago=False):
    if not periods:
        return np.nan
    start = 0
    if year_ago:
        target = periods[0][0] - dt.timedelta(days=365)
        idx = [i for i, (d, _) in enumerate(periods) if abs((d - target).days) <= 45]
        if not idx:
            return np.nan
        start = idx[0]
    w = _window(periods, n, start, spacing)
    if w is None:
        return np.nan
    vals = [_f(r.get(field)) for _, r in w]
    return float(sum(vals)) if all(math.isfinite(v) for v in vals) else np.nan


def _snap(periods, field, year_ago=False):
    if not periods:
        return np.nan
    if not year_ago:
        return _f(periods[0][1].get(field))
    target = periods[0][0] - dt.timedelta(days=365)
    for d, r in periods:
        if abs((d - target).days) <= 45:
            return _f(r.get(field))
    return np.nan


def _div(a, b):
    return a / b if (math.isfinite(a) and math.isfinite(b) and b != 0) else np.nan


def _wins(x, lo=0.25, hi=4.0):
    return min(max(x, lo), hi) if math.isfinite(x) else np.nan


def enrich_symbol(sym: str):
    isr = fc.get_json("income-statement", {"symbol": sym, "period": "quarter", "limit": 13},
                      ttl=fc.TTL_FUNDAMENTAL)
    bs = fc.get_json("balance-sheet-statement", {"symbol": sym, "period": "quarter", "limit": 9},
                     ttl=fc.TTL_FUNDAMENTAL)
    cf = fc.get_json("cash-flow-statement", {"symbol": sym, "period": "quarter", "limit": 9},
                     ttl=fc.TTL_FUNDAMENTAL)
    rec = {"symbol": sym}
    ip, ccy = _clean(isr)
    if not ip:
        return rec, []
    bp, _ = _clean(bs, ccy)
    cp, _ = _clean(cf, ccy)
    cad = _cadence(ip)
    rec["fmp_q_ccy"] = ccy
    rec["fmp_q_latest"] = ip[0][0].isoformat()
    if cad is None:
        rec["fmp_q_status"] = "irregular_cadence"
        return rec, []
    n, spacing = cad
    age = (TODAY - ip[0][0]).days
    if age > (275 if n == 4 else 370):
        rec["fmp_q_status"] = "stale"
        return rec, []
    rec["fmp_q_status"] = "ok"
    rec["fmp_q_periods_per_year"] = float(n)

    L = {}   # levels: current TTM / snapshot, and year-ago
    for src, key in IS_FLOWS.items():
        L[key] = _ttm(ip, n, spacing, src)
        L[key + "_p"] = _ttm(ip, n, spacing, src, year_ago=True)
    for src, key in CF_FLOWS.items():
        L[key] = _ttm(cp, n, spacing, src)
        L[key + "_p"] = _ttm(cp, n, spacing, src, year_ago=True)
    # Quarterly incomeTaxesPaid is unusable in FMP: zero-filled for many
    # filers (KO, NESN every period), sporadic for others, and corrupted in
    # fourth quarters that FMP derives as annual minus nine-month YTD (AAPL
    # read -$37B). The ANNUAL cash-flow figure is reliable (AAPL $43.4B), so
    # cash taxes and the matching annual pretax come from the latest fiscal
    # year (same cached call the statements engine uses).
    L["taxes_paid"] = np.nan
    L["pretax_fy"] = np.nan
    try:
        cfa = fc.get_json("cash-flow-statement", {"symbol": sym, "period": "annual", "limit": 8},
                          ttl=fc.TTL_FUNDAMENTAL) or []
        isa = fc.get_json("income-statement", {"symbol": sym, "period": "annual", "limit": 8},
                          ttl=fc.TTL_FUNDAMENTAL) or []
        cfa = [r for r in cfa if r.get("reportedCurrency") == ccy]
        isa = {str(r.get("date"))[:10]: r for r in isa if r.get("reportedCurrency") == ccy}
        if cfa:
            latest = max(cfa, key=lambda r: str(r.get("date")))
            tp = _f(latest.get("incomeTaxesPaid"))
            pt = _f((isa.get(str(latest.get("date"))[:10]) or {}).get("incomeBeforeTax"))
            fy_age = (TODAY - (_d(latest.get("date")) or TODAY)).days
            if math.isfinite(tp) and tp > 0 and math.isfinite(pt) and fy_age <= 550:
                L["taxes_paid"], L["pretax_fy"] = tp, pt
    except fc.FMPError:
        pass
    for src, key in BS_STOCKS.items():
        L[key] = _snap(bp, src)
        L[key + "_p"] = _snap(bp, src, year_ago=True)
    for k in ("defrev", ):
        for sfx in ("", "_p"):
            a, b = L.get(f"defrev_cur{sfx}", np.nan), L.get(f"defrev_nc{sfx}", np.nan)
            L[f"defrev{sfx}"] = (0 if not math.isfinite(a) else a) + (0 if not math.isfinite(b) else b) \
                if (math.isfinite(a) or math.isfinite(b)) else np.nan
    shares = [_f(r.get("weightedAverageShsOutDil")) for _, r in ip]

    # ---- levels emitted (reporting currency; archetype layer converts) ----
    for k in ("revenue", "gp", "opinc", "ni", "ni_cont", "ni_disc", "pretax", "tax_exp",
              "int_exp", "cfo", "capex", "fcf", "da", "sbc", "taxes_paid", "buyback",
              "dividends", "receivables", "inventory", "payables", "cur_assets", "cur_liab",
              "total_assets", "ppe_net", "gw_intang", "defrev", "total_debt", "cash_sti",
              "equity", "retained_earnings", "total_liab", "minority", "revenue_p", "ni_p",
              "cfo_p", "equity_p", "defrev_p"):
        rec[f"fq_{k}"] = L.get(k, np.nan)

    rev, rev_p = L["revenue"], L["revenue_p"]
    # ---- working-capital forensics ----
    cogs = L["cogs"] if math.isfinite(L["cogs"]) else (rev - L["gp"] if math.isfinite(L["gp"]) else np.nan)
    cogs_p = L["cogs_p"] if math.isfinite(L["cogs_p"]) else (rev_p - L["gp_p"] if math.isfinite(L["gp_p"]) else np.nan)
    rec["fq_dso"] = _div(L["receivables"], rev) * 365
    rec["fq_dso_p"] = _div(L["receivables_p"], rev_p) * 365
    rec["fq_dio"] = _div(L["inventory"], cogs) * 365
    rec["fq_dio_p"] = _div(L["inventory_p"], cogs_p) * 365
    rec["fq_dpo"] = _div(L["payables"], cogs) * 365
    rec["fq_dpo_p"] = _div(L["payables_p"], cogs_p) * 365
    ccc = [rec["fq_dso"], rec["fq_dio"], rec["fq_dpo"]]
    ccc_p = [rec["fq_dso_p"], rec["fq_dio_p"], rec["fq_dpo_p"]]
    if all(math.isfinite(v) for v in ccc):
        rec["fq_ccc"] = ccc[0] + ccc[1] - ccc[2]
    if all(math.isfinite(v) for v in ccc_p):
        rec["fq_ccc_p"] = ccc_p[0] + ccc_p[1] - ccc_p[2]
    rev_g = _div(rev, rev_p) - 1
    rec["fq_rev_growth"] = rev_g
    # receivables / inventory growing faster than sales = channel stuffing /
    # unsold build (only meaningful off a material base)
    if math.isfinite(L["receivables_p"]) and L["receivables_p"] > 0.02 * (rev_p or np.inf):
        rec["fq_rec_vs_rev"] = _div(L["receivables"], L["receivables_p"]) - 1 - rev_g
    if math.isfinite(L["inventory_p"]) and L["inventory_p"] > 0.02 * (rev_p or np.inf):
        rec["fq_inv_vs_cogs"] = _div(L["inventory"], L["inventory_p"]) - _div(cogs, cogs_p)
    rec["fq_nwc"] = L["cur_assets"] - L["cur_liab"] if math.isfinite(L["cur_assets"]) and math.isfinite(L["cur_liab"]) else np.nan

    # ---- accrual quality ----
    avg_ta = np.nanmean([L["total_assets"], L["total_assets_p"]]) if (
        math.isfinite(L["total_assets"]) or math.isfinite(L["total_assets_p"])) else np.nan
    rec["fq_sloan_accruals"] = _div(L["ni"] - L["cfo"], avg_ta)
    rec["fq_cfo_to_ni"] = _div(L["cfo"], L["ni"]) if (math.isfinite(L["ni"]) and L["ni"] > 0) else np.nan
    rec["fq_cfo_growth_minus_ni_growth"] = (
        (_div(L["cfo"], L["cfo_p"]) - _div(L["ni"], L["ni_p"]))
        if all(math.isfinite(v) and v > 0 for v in (L["cfo"], L["cfo_p"], L["ni"], L["ni_p"])) else np.nan)
    rec["fq_sbc_to_cfo"] = _div(L["sbc"], L["cfo"]) if (math.isfinite(L["cfo"]) and L["cfo"] > 0) else np.nan

    # ---- capex / depreciation / asset life ----
    rec["fq_capex_to_da"] = _div(abs(L["capex"]) if math.isfinite(L["capex"]) else np.nan, L["da"])
    rec["fq_da_to_ppe"] = _div(L["da"], L["ppe_net"])
    rec["fq_gw_pct_assets"] = _div(L["gw_intang"], L["total_assets"])

    # ---- tax / one-offs / deferred revenue ----
    if math.isfinite(L["pretax"]) and L["pretax"] > 0:
        rec["fq_book_tax_rate"] = _div(L["tax_exp"], L["pretax"])
    if math.isfinite(L["pretax_fy"]) and L["pretax_fy"] > 0:
        rec["fq_cash_tax_rate"] = _div(L["taxes_paid"], L["pretax_fy"])   # annual basis
    rec["fq_disc_ops_share"] = _div(L["ni_disc"], abs(L["ni"]) if math.isfinite(L["ni"]) else np.nan)
    rec["fq_defrev_to_rev"] = _div(L["defrev"], rev)
    if math.isfinite(L["defrev_p"]) and L["defrev_p"] > 0.02 * (rev_p or np.inf):
        rec["fq_defrev_growth_minus_rev"] = _div(L["defrev"], L["defrev_p"]) - 1 - rev_g
    rec["fq_interest_cover"] = _div(L["opinc"], L["int_exp"]) if (math.isfinite(L["int_exp"]) and L["int_exp"] > 0) else np.nan
    rec["fq_equity_growth"] = _div(L["equity"], L["equity_p"]) - 1 if (
        math.isfinite(L["equity_p"]) and L["equity_p"] > 0) else np.nan

    # ---- Beneish M-score (TTM vs prior TTM; balance now vs year-ago) ----
    gm, gm_p = _div(L["gp"], rev), _div(L["gp_p"], rev_p)
    dsri = _div(_div(L["receivables"], rev), _div(L["receivables_p"], rev_p))
    gmi = _div(gm_p, gm) if (math.isfinite(gm) and gm > 0 and math.isfinite(gm_p) and gm_p > 0) else np.nan
    def _aq(ca, ppe, ta):
        return 1 - (ca + ppe) / ta if all(math.isfinite(v) for v in (ca, ppe, ta)) and ta > 0 else np.nan
    aqi = _div(_aq(L["cur_assets"], L["ppe_net"], L["total_assets"]),
               _aq(L["cur_assets_p"], L["ppe_net_p"], L["total_assets_p"]))
    sgi = _div(rev, rev_p)
    def _dep(da, ppe):
        return da / (da + ppe) if math.isfinite(da) and math.isfinite(ppe) and da + ppe > 0 else np.nan
    depi = _div(_dep(L["da_p"], L["ppe_net_p"]), _dep(L["da"], L["ppe_net"]))
    sgai = _div(_div(L["sga"], rev), _div(L["sga_p"], rev_p))
    def _lev(cl, ltd, ta):
        return (cl + (ltd if math.isfinite(ltd) else 0)) / ta if math.isfinite(cl) and math.isfinite(ta) and ta > 0 else np.nan
    lvgi = _div(_lev(L["cur_liab"], L["lt_debt"], L["total_assets"]),
                _lev(L["cur_liab_p"], L["lt_debt_p"], L["total_assets_p"]))
    tata = _div((L["ni_cont"] if math.isfinite(L["ni_cont"]) else L["ni"]) - L["cfo"], L["total_assets"])
    core = [dsri, gmi, aqi, sgi, tata]
    if all(math.isfinite(v) for v in core):
        dsri, gmi, aqi, sgi = (_wins(v) for v in (dsri, gmi, aqi, sgi))
        depi = _wins(depi) if math.isfinite(depi) else 1.0
        sgai = _wins(sgai) if math.isfinite(sgai) else 1.0
        lvgi = _wins(lvgi) if math.isfinite(lvgi) else 1.0
        tata = min(max(tata, -0.5), 0.5)
        rec["fq_beneish_m"] = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
                               + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
        rec["fq_beneish_dsri"], rec["fq_beneish_tata"] = dsri, tata

    # ---- trajectories from the raw periods ----
    # gross-margin YoY streak: consecutive latest periods whose GM beats the
    # same period a year earlier
    gms = []
    for d, r in ip:
        rv, g = _f(r.get("revenue")), _f(r.get("grossProfit"))
        gms.append((d, g / rv if math.isfinite(rv) and rv > 0 and math.isfinite(g) else np.nan))
    streak = 0
    for i, (d, g) in enumerate(gms):
        ya = [gg for dd, gg in gms if abs((d - dt.timedelta(days=365) - dd).days) <= 45]
        if not ya or not math.isfinite(g) or not math.isfinite(ya[0]) or g <= ya[0]:
            break
        streak += 1
    rec["fq_gm_yoy_streak"] = float(streak)
    # net-debt path over the balance snapshots (newest first)
    nd = []
    for d, r in bp[:5]:
        td, c = _f(r.get("totalDebt")), _f(r.get("cashAndShortTermInvestments"))
        if math.isfinite(td) and math.isfinite(c):
            nd.append(td - c)
    if len(nd) >= 3:
        dec = 0
        for a, b in zip(nd, nd[1:]):
            if a < b:
                dec += 1
            else:
                break
        rec["fq_netdebt_decline_periods"] = float(dec)
        # scaled by total assets: a near-zero starting net debt made a
        # percent-of-net-debt change explode (CRM read 834%)
        rec["fq_netdebt_change_pct_assets"] = _div(nd[0] - nd[-1], L["total_assets"])
        rec["fq_netdebt_span_periods"] = float(len(nd) - 1)
    # diluted share count, year over year
    ya_sh = [s for (d, _), s in zip(ip, shares) if abs((ip[0][0] - dt.timedelta(days=365) - d).days) <= 45]
    if shares and math.isfinite(shares[0]) and ya_sh and math.isfinite(ya_sh[0]) and ya_sh[0] > 0:
        rec["fq_shares_yoy"] = shares[0] / ya_sh[0] - 1

    # ---- compact panel rows (kept for future recipe work, no re-pull) ----
    panel = []
    bmap = {d: r for d, r in bp}
    cmap = {d: r for d, r in cp}
    for d, r in ip:
        row = {"symbol": sym, "date": d.isoformat(), "period": r.get("period"), "ccy": ccy}
        for src, key in IS_FLOWS.items():
            row[key] = _f(r.get(src))
        c = cmap.get(d, {})
        for src, key in CF_FLOWS.items():
            row[key] = _f(c.get(src))
        b = bmap.get(d, {})
        for src, key in BS_STOCKS.items():
            row[key] = _f(b.get(src))
        row["shares_dil"] = _f(r.get("weightedAverageShsOutDil"))
        panel.append(row)
    return rec, panel


def _flush(recs, panel, part_no):
    if recs:
        new = pd.DataFrame(recs)
        if os.path.exists(OUT):
            new = pd.concat([pd.read_csv(OUT, low_memory=False), new], ignore_index=True)\
                    .drop_duplicates("symbol", keep="last")
        new.to_csv(OUT + ".tmp", index=False)
        os.replace(OUT + ".tmp", OUT)
    if panel:
        os.makedirs(_PANEL_PART_DIR, exist_ok=True)
        pd.DataFrame(panel).to_parquet(os.path.join(_PANEL_PART_DIR, f"part_{part_no:05d}.parquet"),
                                       index=False)


def consolidate_panel():
    """Merge panel parts into one parquet (last write per symbol/date wins)."""
    if not os.path.isdir(_PANEL_PART_DIR):
        return 0
    parts = sorted(os.listdir(_PANEL_PART_DIR))
    frames = [pd.read_parquet(os.path.join(_PANEL_PART_DIR, p)) for p in parts]
    if os.path.exists(PANEL):
        frames.insert(0, pd.read_parquet(PANEL))
    df = pd.concat(frames, ignore_index=True).drop_duplicates(["symbol", "date"], keep="last")
    df.to_parquet(PANEL + ".tmp", index=False, compression="zstd")
    os.replace(PANEL + ".tmp", PANEL)
    for p in parts:
        os.remove(os.path.join(_PANEL_PART_DIR, p))
    return len(df)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--checkpoint-every", type=int, default=250)
    ap.add_argument("--gc-max-mb", type=int, default=3000)
    ap.add_argument("--consolidate", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.consolidate:
        print("panel rows:", consolidate_panel())
        return
    t = pd.read_csv("archetype_tags.csv", usecols=lambda c: c in {"symbol", "archetype_count"},
                    low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    t["archetype_count"] = pd.to_numeric(t["archetype_count"], errors="coerce").fillna(0)
    syms = t.sort_values("archetype_count", ascending=False)["symbol"].tolist()
    if args.max:
        syms = syms[: args.max]
    done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str)) if os.path.exists(OUT) else set()
    todo = [s for s in syms if s not in done]
    part = len(os.listdir(_PANEL_PART_DIR)) if os.path.isdir(_PANEL_PART_DIR) else 0
    print(f"quarterly: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    from concurrent.futures import ThreadPoolExecutor

    def _one(sym):
        try:
            return enrich_symbol(sym)
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                raise
            return {"symbol": sym, "fmp_q_status": "error"}, []

    recs, panel = [], []
    step = args.checkpoint_every
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for b0 in range(0, len(todo), step):
            batch = todo[b0:b0 + step]
            try:
                for r, p in ex.map(_one, batch):
                    recs.append(r); panel.extend(p)
            except fc.FMPError as exc:
                print(f"  rate limited near {b0}: {exc}; checkpointing", flush=True)
                break
            part += 1
            _flush(recs, panel, part); recs, panel = [], []
            st = fc.cache_stats()
            print(f"  quarterly {b0 + len(batch)}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb and (b0 // step) % 20 == 0:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    part += 1
    _flush(recs, panel, part)
    print(f"\nwrote {OUT}: {len(pd.read_csv(OUT)) if os.path.exists(OUT) else 0} rows; "
          f"panel rows {consolidate_panel()}", flush=True)


if __name__ == "__main__":
    main()
