"""Merge authoritative Yahoo fundamentals (ticker_yf.csv) into the master.

ticker_yf.py pulls Yahoo's own mcap / EV / EV-EBITDA / P/B / P/E and a
broad fundamentals set via the cookie/crumb quoteSummary endpoint — for
US *and* foreign tickers, which is the gap SEC XBRL can't reach.

Policy (the rigorous valuation process)
---------------------------------------
Trust hierarchy, applied in order, so every row ends INTERNALLY CONSISTENT:
  1. price / market_cap / enterprise_value: Yahoo, authoritative (overwrite).
  2. LEVELS (ebitda/revenue/cfo/net-income/shares): gap-fill, PLUS a
     reconcile — where the stored level disagrees >1.4x (or by sign) with
     Yahoo's level (or the level implied by Yahoo's own EV/ratio pair, or
     mcap/p_e), the level bends to Yahoo; the USD twin is rescaled so the
     embedded FX rate survives. Within 1.4x the master keeps (EDGAR
     precision). EXCEPTIONS (measure-basis differences, never "staleness"):
     fcf_ttm (Yahoo freeCashflow is levered FCF, a different lower measure
     than our CFO-minus-capex) and cash/total_debt (master cash is the
     broader cash+investments basis the net-cash archetypes rely on) stay
     gap-fill only.
  3. DERIVED RATIOS (fcf_yield, ebitda_margin, net_debt_ebitda, ev_ebit,
     and finally ev_ebitda/ev_sales/p_e): recomputed from the row's own
     components whenever they disagree >25% — a stored snapshot ratio next
     to a refreshed price is how DEEPINDS-class staleness happened. A
     provably-wrong value with no recompute candidate is NULLED (wrong is
     worse than missing), incl. EV multiples on EV<=0 or EBITDA<=0 and
     ev_ebit sitting below ev_ebitda.
The aggregate gate lives in methodology_audit.py ("Valuation internal
consistency"); the per-name top-N report is valuation_crosscheck.py.

A provenance column `valuation_source` records 'yahoo' where we took
Yahoo's authoritative ratios, else leaves the existing source.

Writes back to asymmetry_global.csv in place (or --out).
"""
from __future__ import annotations
import argparse
import sys

import numpy as np
import pandas as pd


# Yahoo column -> master column, and whether Yahoo is authoritative
# (overwrite) or only gap-fills.
#   ('overwrite')  : Yahoo's own computed ratio, prefer it
#   ('fill')       : only fill where master is null
MERGE_SPEC = [
    # Authoritative valuation ratios — prefer Yahoo
    ("yf_market_cap", "market_cap", "overwrite"),
    ("yf_enterprise_value", "enterprise_value", "overwrite"),
    ("yf_ev_ebitda", "ev_ebitda", "overwrite"),
    ("yf_ev_sales", "ev_sales", "overwrite"),
    ("yf_pb", "pb", "overwrite"),
    ("yf_pe", "p_e", "overwrite"),
    ("yf_ps", "p_s", "overwrite"),
    ("yf_price", "price", "overwrite"),
    # Margins / returns — fill gaps (EDGAR audited wins where present)
    ("yf_ebitda_margin", "ebitda_margin", "fill"),
    ("yf_gross_margin", "gross_margin", "fill"),
    ("yf_operating_margin", "op_margin", "fill"),
    ("yf_profit_margin", "net_margin", "fill"),
    ("yf_roe", "roe", "fill"),
    ("yf_roa", "roa", "fill"),
    # Levels — fill gaps only
    ("yf_revenue", "revenue_ttm", "fill"),
    ("yf_ebitda", "ebitda_ttm", "fill"),
    ("yf_fcf", "fcf_ttm", "fill"),
    ("yf_cfo", "cfo_ttm", "fill"),
    ("yf_cash", "cash", "fill"),
    ("yf_total_debt", "total_debt", "fill"),
    ("yf_shares_outstanding", "shares_outstanding", "fill"),
    # Ownership / sell-side — fill gaps
    ("yf_insider_pct", "insider_ownership_pct", "fill"),
    ("yf_dividend_yield", "dividend_yield", "fill"),
    ("yf_target_mean", "analyst_target_mean", "fill"),
    ("yf_n_analysts", "n_analysts", "fill"),
    # 52-week
    ("yf_52w_high", "price_52w_high", "fill"),
]

# Extra Yahoo-native columns we keep with a yf_ prefix (no master equivalent)
YF_NATIVE_KEEP = [
    "yf_forward_pe", "yf_peg", "yf_beta", "yf_revenue_growth",
    "yf_earnings_growth", "yf_recommendation_mean", "yf_institution_pct",
    "yf_52w_low",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default="asymmetry_global.csv")
    ap.add_argument("--yf", default="ticker_yf.csv")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_path = args.out or args.master

    print(f"loading master {args.master}...", file=sys.stderr)
    master = pd.read_csv(args.master).drop_duplicates("symbol")
    print(f"  {len(master):,} rows", file=sys.stderr)

    try:
        yf = pd.read_csv(args.yf).drop_duplicates("symbol", keep="last")
    except FileNotFoundError:
        print(f"  {args.yf} not found — nothing to merge", file=sys.stderr)
        sys.exit(0)
    print(f"  {len(yf):,} Yahoo rows", file=sys.stderr)

    m = master.set_index("symbol")
    y = yf.set_index("symbol")
    common = m.index.intersection(y.index)
    print(f"  {len(common):,} symbols overlap", file=sys.stderr)

    # Plausibility bands per master column. Yahoo's quoteSummary sometimes
    # returns garbage ratios (negative EV/EBITDA from negative EBITDA,
    # absurd >100 multiples, near-zero from data errors). For OVERWRITE
    # columns we only clobber the master with an in-band Yahoo value;
    # out-of-band values fall through (the existing master value, often a
    # clean EDGAR-derived figure, is kept). FILL columns still only touch
    # nulls, but the band keeps us from filling a gap with garbage too.
    #   (lo, hi) inclusive bounds; None = unbounded on that side.
    BANDS = {
        "ev_ebitda": (-150, 150),   # negative EV / positive EBITDA is a REAL multiple (paid to own the earnings)
        "p_e": (0, 500),
        "pb": (0, 100),
        "ev_sales": (-100, 100),    # ditto for negative-EV sales multiples
        "p_s": (0, 100),
        "market_cap": (0, None),
        "enterprise_value": (None, None),  # EV can be negative (net cash)
        "price": (0, None),
        "ebitda_margin": (-5, 5),
        "gross_margin": (-1, 1),
        "op_margin": (-5, 5),
        "net_margin": (-5, 5),
        "roe": (-10, 10),
        "roa": (-5, 5),
        "dividend_yield": (0, 0.5),
        "revenue_ttm": (0, None),
        "ebitda_ttm": (None, None),
        "fcf_ttm": (None, None),
        "cfo_ttm": (None, None),
        "cash": (0, None),
        "total_debt": (0, None),
        "shares_outstanding": (0, None),
        "insider_ownership_pct": (0, 1),
        "price_52w_high": (0, None),
    }

    def in_band(series, col):
        lo, hi = BANDS.get(col, (None, None))
        ok = series.notna()
        if lo is not None:
            ok &= series >= lo
        if hi is not None:
            ok &= series <= hi
        return ok

    changes = {}
    rejected = {}
    for yf_col, master_col, mode in MERGE_SPEC:
        if yf_col not in y.columns:
            continue
        src = pd.to_numeric(y[yf_col], errors="coerce")
        src = src.reindex(m.index)
        if master_col not in m.columns:
            m[master_col] = np.nan
        before = m[master_col].notna().sum()
        band_ok = in_band(src, master_col)
        n_rej = int((src.notna() & ~band_ok).sum())
        if mode == "overwrite":
            mask = band_ok
        else:  # fill
            mask = band_ok & m[master_col].isna()
        m.loc[mask, master_col] = src[mask]
        after = m[master_col].notna().sum()
        changes[master_col] = (before, after, int(mask.sum()), mode)
        if n_rej:
            rejected[master_col] = rejected.get(master_col, 0) + n_rej

    # ----- RECONCILE levels with the authoritative Yahoo valuation -----
    # The fill-only policy for levels assumed the existing master level was an
    # audited (EDGAR) figure. For most non-US names it is a quarterly-sum
    # scrape that can undercount (missing quarters) or even carry the wrong
    # SIGN, leaving the row internally INCONSISTENT with the Yahoo ratios we
    # just overwrote. DEEPINDS.NS was the tell: ev_ebitda 13.5 (Yahoo, implies
    # EBITDA 3.84B / a 39.5% margin, correct for the business) while ebitda_ttm
    # said 1.57B (a 17.7% margin from a broken quarterly sum). At scale: 41% of
    # Yahoo-covered names disagreed >1.4x, and 2,550 carried the wrong SIGN —
    # failing (or passing) every ebitda>0 survivability leg wrongly. Where the
    # two disagree MATERIALLY (>1.4x either way, or opposite sign), prefer
    # Yahoo's level — the same source authority as the ratios the books rank
    # on — and rescale the USD twin by the same factor so the embedded FX rate
    # is preserved. Close values (<=1.4x) keep the master (EDGAR precision).
    # Implied Yahoo net income: Yahoo computes profit_margin = NI / revenue on
    # its own consolidated TTM, so margin x revenue reconstructs Yahoo's NI —
    # the level consistent with the p_e we just overwrote.
    y = y.copy()
    if "yf_profit_margin" in y.columns and "yf_revenue" in y.columns:
        y["yf_net_income_implied"] = (
            pd.to_numeric(y["yf_profit_margin"], errors="coerce")
            * pd.to_numeric(y["yf_revenue"], errors="coerce"))
    # Where Yahoo supplies the RATIO but not the LEVEL, derive the level from
    # Yahoo's own internally-consistent pair (EV / ratio) so the reconcile can
    # still bend the master level to the authoritative source.
    _yev0 = pd.to_numeric(y.get("yf_enterprise_value"), errors="coerce")
    for _rat, _lvl in (("yf_ev_ebitda", "yf_ebitda"), ("yf_ev_sales", "yf_revenue")):
        if _rat in y.columns:
            _rv0 = pd.to_numeric(y[_rat], errors="coerce")
            _implied = (_yev0 / _rv0).where((_rv0 > 0) & _yev0.notna())
            if _lvl in y.columns:
                _cur0 = pd.to_numeric(y[_lvl], errors="coerce")
                y[_lvl] = _cur0.fillna(_implied)
            else:
                y[_lvl] = _implied
    # NOTE: yf_fcf is deliberately NOT reconciled. Yahoo's freeCashflow is its
    # "levered FCF" — a methodologically different, systematically LOWER measure
    # than this pipeline's CFO-minus-capex fcf_ttm (MSFT: Yahoo 16.5B vs real
    # ~68B; GOOGL 22.7B vs 63B). Overwriting on a disagreement rule would swap
    # measures, not fix staleness — it stays gap-fill-only. yf_cfo
    # (operatingCashflow) IS apples-to-apples and is reconciled; price-staleness
    # in fcf_yield is fixed by the derived-ratio recompute below instead.
    RECONCILE = [("yf_ebitda", "ebitda_ttm", "ebitda_ttm_usd"),
                 ("yf_revenue", "revenue_ttm", "revenue_ttm_usd"),
                 ("yf_cfo", "cfo_ttm", None),
                 ("yf_net_income_implied", "net_income_ttm", None)]
    recon = {}
    repaired_any = pd.Series(False, index=m.index)
    for yf_col, mcol, usd_col in RECONCILE:
        if yf_col not in y.columns or mcol not in m.columns:
            continue
        src = pd.to_numeric(y[yf_col], errors="coerce").reindex(m.index)
        cur = pd.to_numeric(m[mcol], errors="coerce")
        both = src.notna() & cur.notna() & (src != 0) & (cur != 0)
        ratio = (cur / src).where(both)
        disagree = both & ((ratio > 1.4) | (ratio < 1 / 1.4))
        if usd_col and usd_col in m.columns:
            usd = pd.to_numeric(m[usd_col], errors="coerce")
            factor = (src / cur).where(disagree)
            m.loc[disagree, usd_col] = (usd * factor)[disagree]
        m.loc[disagree, mcol] = src[disagree]
        recon[mcol] = int(disagree.sum())
        repaired_any |= disagree

    # shares_outstanding: mcap and price are BOTH Yahoo-fresh, and shares is
    # definitionally mcap/price — a stale share count (splits, new issues) is
    # the only way the three can disagree. Snap it to mcap/price when >10% off.
    _p = pd.to_numeric(m.get("price"), errors="coerce")
    _mc = pd.to_numeric(m.get("market_cap"), errors="coerce")
    if "shares_outstanding" in m.columns:
        _sh = pd.to_numeric(m["shares_outstanding"], errors="coerce")
        _imp = (_mc / _p).where((_p > 0) & (_mc > 0))
        _dev = (_sh / _imp)
        _fix_sh = _imp.notna() & _sh.notna() & ((_dev > 1.10) | (_dev < 1 / 1.10))
        m.loc[_fix_sh, "shares_outstanding"] = _imp[_fix_sh]
        recon["shares_outstanding"] = int(_fix_sh.sum())

    # ----- MARGIN RECONCILE -----
    # op/gross/net margins were fill-only and NEVER re-touched, so corrupt or
    # stale snapshot margins (KROS op_margin +246% on a burning biotech) sat
    # beside reconciled levels and violated hard orderings (EBIT <= EBITDA).
    # Margins are bounded quantities: reconcile on ABSOLUTE disagreement
    # (>0.10) with Yahoo's own margin, which shares the basis of the levels
    # we just reconciled. op_margin feeds the melt logic — correctness matters.
    for _ymc, _mmc in (("yf_operating_margin", "op_margin"),
                       ("yf_gross_margin", "gross_margin"),
                       ("yf_profit_margin", "net_margin"),
                       ("yf_roe", "roe")):
        if _ymc in y.columns and _mmc in m.columns:
            _ysrc = pd.to_numeric(y[_ymc], errors="coerce").reindex(m.index)
            _mcur = pd.to_numeric(m[_mmc], errors="coerce")
            _dis = _ysrc.notna() & _mcur.notna() & ((_mcur - _ysrc).abs() > 0.10)
            m.loc[_dis, _mmc] = _ysrc[_dis]
            recon[_mmc] = recon.get(_mmc, 0) + int(_dis.sum())

    # ----- DERIVED-RATIO RECOMPUTE (the rigorous-process core) -----
    # A ratio the pipeline can derive from current components must NEVER be a
    # carried snapshot value: price/mcap/EV refresh every run, so any stored
    # price-linked ratio silently goes stale (fcf_yield was 25%+ off on 19% of
    # names purely because the price had moved since the snapshot). Recompute
    # from the freshly merged + reconciled components, overwriting when the
    # stored value materially disagrees (>25%) or is missing.
    _eb = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
    _rv = pd.to_numeric(m.get("revenue_ttm"), errors="coerce")

    def _recompute(colname, fresh, tol=0.25, band=(None, None)):
        if colname not in m.columns:
            return
        cur = pd.to_numeric(m[colname], errors="coerce")
        lo, hi = band
        ok = fresh.notna()
        if lo is not None:
            ok &= fresh >= lo
        if hi is not None:
            ok &= fresh <= hi
        dev = (cur / fresh).where(ok & (fresh != 0))
        stale = ok & cur.notna() & ((dev > 1 + tol) | (dev < 1 / (1 + tol)) | (dev < 0))
        fillm = ok & cur.isna()
        m.loc[stale | fillm, colname] = fresh[stale | fillm]
        recon[colname] = recon.get(colname, 0) + int((stale | fillm).sum())

    # fcf_ttm policy — ADJUDICATED AGAINST AUDITED ACCOUNTS (EDGAR XBRL, US
    # names, n=2,821): Yahoo's FCF agrees with the audited CFO-minus-capex on
    # only 30% of names (median 0.91, q25 = 0.53 — a QUARTER of names at half
    # the audited value), while the same-definition CFO control agrees 44%
    # (freshness scatter only) and revenue/EBITDA agree 81%/64%. Yahoo FCF is
    # therefore a DIFFERENT MEASURE, not a fresher one — so the identity
    # FCF = reconciled CFO - capex (exact on 36k rows) is PRIMARY, and yf_fcf
    # is never conflict-adopted (gap-fill only, in MERGE_SPEC). Study:
    # audit_reports/fcf_source_study.md.
    _cx = pd.to_numeric(m.get("capex_ttm"), errors="coerce")
    _cfoB = pd.to_numeric(m.get("cfo_ttm"), errors="coerce")
    _fcf_adopted_yf = pd.Series(False, index=m.index)   # retained for the qc flag (now marks nothing)
    if "fcf_ttm" in m.columns:
        def _apply_fcf(new_vals, mask, label):
            if "fcf_ttm_usd" in m.columns:
                _cur0 = pd.to_numeric(m["fcf_ttm"], errors="coerce")
                _usd0 = pd.to_numeric(m["fcf_ttm_usd"], errors="coerce")
                _fac0 = (new_vals / _cur0).where(mask & (_cur0 != 0))
                m.loc[mask, "fcf_ttm_usd"] = (_usd0 * _fac0)[mask]
            m.loc[mask, "fcf_ttm"] = new_vals[mask]
            recon[label] = int(mask.sum())

        _fcf_cur = pd.to_numeric(m["fcf_ttm"], errors="coerce")
        _fcf_new = (_cfoB - _cx).where(_cfoB.notna() & _cx.notna())
        _ratio_f = (_fcf_cur / _fcf_new).where(_fcf_new != 0)
        _imposs = _fcf_cur.notna() & (_cfoB > 0) & (_fcf_cur > _cfoB * 1.05) & (_cx > 0)
        _dis_f = _fcf_new.notna() & _fcf_cur.notna() \
            & ((_ratio_f > 1.4) | (_ratio_f < 1 / 1.4) | _imposs)
        _apply_fcf(_fcf_new, _dis_f, "fcf_ttm (cfo - capex, accounts-referred primary)")

    # price_52w_high: a running max is definitionally valid — the stored high
    # can never sit BELOW the current price.
    if "price_52w_high" in m.columns:
        _hi = pd.to_numeric(m["price_52w_high"], errors="coerce")
        _lift = _hi.notna() & (_p > _hi)
        m.loc[_lift, "price_52w_high"] = _p[_lift]
        recon["price_52w_high lifted to price"] = int(_lift.sum())

    # fcf_yield = fcf_ttm / market_cap (repo convention, median dev 0.005).
    # fcf_ttm is LEVERED FCF (CFO - capex, post-interest) — an equity-holder
    # cash flow — so its yield is against MARKET CAP, never EV (user rule).
    _fcf = pd.to_numeric(m.get("fcf_ttm"), errors="coerce")
    _recompute("fcf_yield", (_fcf / _mc).where(_mc > 0), band=(-50, 50))
    # The whole equity-cash-yield family shares the mcap denominator and the
    # same price-staleness disease (computed once at derive-time, then price
    # moves): recompute them all from current components every run. These feed
    # the melt logic (_cash_return_ok) and the weschler/liger cheapness gates.
    _cfo2 = pd.to_numeric(m.get("cfo_ttm"), errors="coerce")
    _ni3 = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")
    _recompute("owner_earnings_yield", (_fcf / _mc).where(_mc > 0), band=(-50, 50))
    _recompute("cfo_yield", (_cfo2 / _mc).where(_mc > 0), band=(-50, 50))
    _recompute("earnings_yield", (_ni3 / _mc).where(_mc > 0), band=(-50, 50))
    if "robust_cash_yield" in m.columns:
        _rcy_new = pd.concat([(_fcf / _mc).where(_mc > 0),
                              (_cfo2 / _mc).where(_mc > 0),
                              (_ni3 / _mc).where(_mc > 0)],
                             axis=1).median(axis=1, skipna=True)
        _recompute("robust_cash_yield", _rcy_new, band=(-50, 50))
    # p_tb = mcap / tangible_equity (verified convention, median drift 12%)
    _te = pd.to_numeric(m.get("tangible_equity"), errors="coerce")
    _recompute("p_tb", (_mc / _te).where((_te > 0) & (_mc > 0)), band=(0, 500))
    # ebitda_margin = ebitda_ttm / revenue_ttm
    _recompute("ebitda_margin", (_eb / _rv).where(_rv > 0), band=(-100, 5))  # a pre-revenue burner CAN sit at -6x revenue; keeping a wrong-SIGN stored margin (KROS +28% vs true -645%) is worse than an extreme true one
    # net_debt_ebitda — only where all components are present and EBITDA is
    # positive (the 99 'unknown' sentinel and negative-EBITDA rows keep their
    # existing semantics untouched).
    _td = pd.to_numeric(m.get("total_debt"), errors="coerce")
    _ca = pd.to_numeric(m.get("cash"), errors="coerce")
    if "net_debt_ebitda" in m.columns:
        _nde_new = ((_td - _ca) / _eb).where((_eb > 0) & _td.notna() & _ca.notna())
        _cur_nde = pd.to_numeric(m["net_debt_ebitda"], errors="coerce")
        _ok = _nde_new.notna() & _nde_new.between(-90, 90) & (_cur_nde != 99)
        _dev = (_cur_nde / _nde_new).where(_ok & (_nde_new != 0))
        _stale = _ok & _cur_nde.notna() & ((_dev > 1.25) | (_dev < 1 / 1.25) | (_dev < 0)) \
                 & ((_cur_nde - _nde_new).abs() > 0.5)   # absolute guard: tiny-leverage noise is not staleness
        m.loc[_stale, "net_debt_ebitda"] = _nde_new[_stale]
        recon["net_debt_ebitda"] = recon.get("net_debt_ebitda", 0) + int(_stale.sum())

    # ev_ebit repair: Yahoo has no EV/EBIT, so the master's can be a stale copy
    # of an OLD ev_ebitda (the snapshot filled ev_ebit from ev_ebitda when EBIT
    # was missing) — 3,305 rows even sat BELOW the fresh ev_ebitda, which is
    # arithmetically impossible (EBIT <= EBITDA). Recompute EV / (op_margin x
    # revenue) from Yahoo's own margin+revenue and overwrite where the stored
    # value is impossible or deviates >1.4x from the recomputation.
    if "ev_ebit" in m.columns and "yf_operating_margin" in y.columns:
        _om = pd.to_numeric(y["yf_operating_margin"], errors="coerce").reindex(m.index)
        _yrev = pd.to_numeric(y["yf_revenue"], errors="coerce").reindex(m.index)
        _yev = pd.to_numeric(y["yf_enterprise_value"], errors="coerce").reindex(m.index)
        _ebit = (_om * _yrev).where((_om > 0) & (_yrev > 0))
        _cand = (_yev / _ebit).where((_ebit > 0) & (_yev > 0))
        _cand = _cand.where((_cand > 0) & (_cand <= 300))
        _cur_ee = pd.to_numeric(m["ev_ebit"], errors="coerce")
        _cur_eeb = pd.to_numeric(m.get("ev_ebitda"), errors="coerce")
        _impossible = (_cur_ee > 0) & (_cur_eeb > 0) & (_cur_ee < _cur_eeb * 0.95)
        _dev = (_cur_ee / _cand)
        _stale = _cand.notna() & _cur_ee.notna() & ((_dev > 1.4) | (_dev < 1 / 1.4))
        _fix = _cand.notna() & (_impossible | _stale | _cur_ee.isna())
        m.loc[_fix, "ev_ebit"] = _cand[_fix]
        recon["ev_ebit"] = int(_fix.sum())

    # ----- FINAL ROW-CONSISTENCY PASS -----
    # Trust hierarchy: where Yahoo supplied an authoritative ratio this run, the
    # LEVEL bends to it (implied level := components / ratio). Where Yahoo did
    # NOT supply the ratio (absent or band-rejected), the stored ratio is a
    # snapshot computed at an old price sitting next to a FRESH Yahoo EV/mcap —
    # so the RATIO bends to the row's own components. Either way every row ends
    # internally consistent: ratio == components, which is what the books rank
    # on and what the integrity audit asserts.
    _ev = pd.to_numeric(m.get("enterprise_value"), errors="coerce")
    _eb2 = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
    _rv2 = pd.to_numeric(m.get("revenue_ttm"), errors="coerce")
    _ni2 = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")

    def _yf_ok(col, band_col):
        if col not in y.columns:
            return pd.Series(False, index=m.index)
        s_ = pd.to_numeric(y[col], errors="coerce").reindex(m.index)
        return in_band(s_, band_col)

    _pe_yf = _yf_ok("yf_pe", "p_e")
    _evb_yf = _yf_ok("yf_ev_ebitda", "ev_ebitda")
    _evs_yf = _yf_ok("yf_ev_sales", "ev_sales")

    def _row_consistent(ratio_col, comp, yf_mask, tol=0.25, band=(0, None)):
        if ratio_col not in m.columns:
            return
        cur = pd.to_numeric(m[ratio_col], errors="coerce")
        lo, hi = band
        ok = comp.notna()
        if lo is not None:
            ok &= comp > lo
        if hi is not None:
            ok &= comp <= hi
        dev = (cur / comp).where(ok & (comp != 0))
        off = ok & cur.notna() & ((dev > 1 + tol) | (dev < 1 / (1 + tol)))
        # The ratio ALWAYS bends to the row's own components in the end — even a
        # Yahoo-precomputed ratio (enterpriseToEbitda lags Yahoo's own
        # price-fresh EV). The Yahoo ratio's role was arbitrating LEVELS above;
        # the final stored ratio must equal what the components say. A MISSING
        # ratio with valid components is filled the same way (this is also what
        # restores negative-EV multiples: negative EV / positive denominator is
        # a real, interpretable number — per user, do NOT null those).
        fix = off | (ok & cur.isna())
        m.loc[fix, ratio_col] = comp[fix]
        recon[f"{ratio_col} (row-consistency)"] = int(fix.sum())

    _row_consistent("ev_ebitda", (_ev / _eb2).where(_eb2 > 0), _evb_yf, band=(-500, 500))
    _row_consistent("ev_sales", (_ev / _rv2).where(_rv2 > 0), _evs_yf, band=(-500, 500))
    _row_consistent("p_s", (_mc / _rv2).where((_rv2 > 0) & (_mc > 0)),
                    _yf_ok("yf_ps", "p_s"), band=(0, 500))
    # Margin-ordering anomalies after the Yahoo reconcile. These orderings are
    # STRONG heuristics, not inalienable laws (associates' income, other
    # operating income, period-basis gaps can legitimately bend them) — so
    # (per user) a mild violation is KEPT and FLAGGED in qc_flags (identifiable,
    # never silent), and only the EXTREME / definitionally-impossible cases
    # (gap > 15pts, or op margin > 102% of revenue) are nulled.
    if "qc_flags" not in m.columns:
        m["qc_flags"] = ""
    m["qc_flags"] = m["qc_flags"].fillna("").astype(str)

    def _qc_flag(mask, tag):
        mask = mask.fillna(False)
        m.loc[mask, "qc_flags"] = (m.loc[mask, "qc_flags"]
                                   .str.replace(tag, "", regex=False) + "|" + tag)
        recon[f"qc_flag {tag}"] = int(mask.sum())

    _om2 = pd.to_numeric(m.get("op_margin"), errors="coerce")
    _ebm2 = pd.to_numeric(m.get("ebitda_margin"), errors="coerce")
    _gm2 = pd.to_numeric(m.get("gross_margin"), errors="coerce")
    if "op_margin" in m.columns:
        _viol_om = _om2.notna() & _ebm2.notna() & (_om2 > _ebm2 + 0.02)
        _null_om = _viol_om & ((_om2 > _ebm2 + 0.15) | (_om2 > 1.02))
        m.loc[_null_om, "op_margin"] = np.nan
        recon["op_margin nulled (extreme > ebitda_margin)"] = int(_null_om.sum())
        _qc_flag(_viol_om & ~_null_om, "op_gt_ebitda_margin")
    if "gross_margin" in m.columns:
        _om3 = pd.to_numeric(m.get("op_margin"), errors="coerce")
        _viol_gm = _gm2.notna() & _om3.notna() & (_gm2 < _om3 - 0.02)
        _null_gm = _viol_gm & (_gm2 < _om3 - 0.15)
        m.loc[_null_gm, "gross_margin"] = np.nan
        recon["gross_margin nulled (extreme < op_margin)"] = int(_null_gm.sum())
        _qc_flag(_viol_gm & ~_null_gm, "gross_lt_op_margin")
    _qc_flag(_fcf_adopted_yf, "fcf_yf_adopted")
    _row_consistent("p_e", (_mc / _ni2).where(_ni2 > 0), _pe_yf, band=(0, 2000))
    # where Yahoo's p_e IS authoritative but NI still disagrees (margin-implied
    # NI was unavailable), derive the level from the ratio: NI := mcap / p_e.
    _pe_cur = pd.to_numeric(m.get("p_e"), errors="coerce")
    _ni_imp = (_mc / _pe_cur).where((_pe_cur > 0) & (_mc > 0))
    _dev_ni = (_ni2 / _ni_imp)
    _fix_ni = _pe_yf & _ni_imp.notna() & _ni2.notna() & (_ni2 > 0) \
        & ((_dev_ni > 1.25) | (_dev_ni < 1 / 1.25))
    m.loc[_fix_ni, "net_income_ttm"] = _ni_imp[_fix_ni]
    recon["net_income_ttm (from authoritative p_e)"] = int(_fix_ni.sum())
    # EV/EBIT ordering: after every repair, a multiple still sitting BELOW
    # EV/EBITDA (EBIT <= EBITDA makes that impossible) is provably wrong —
    # and a wrong multiple is worse than a missing one. Null the survivors.
    if "ev_ebit" in m.columns:
        _ee2 = pd.to_numeric(m["ev_ebit"], errors="coerce")
        _eeb2 = pd.to_numeric(m.get("ev_ebitda"), errors="coerce")
        _still = (_ee2 > 0) & (_eeb2 > 0) & (_ee2 < _eeb2 * 0.95)
        m.loc[_still, "ev_ebit"] = np.nan
        recon["ev_ebit nulled (impossible ordering)"] = int(_still.sum())

    # After the level repair, a name whose EBITDA is now (correctly) NEGATIVE
    # must not keep a stale positive EV/EBITDA or EV/EBIT — Yahoo's own negative
    # ratio was band-rejected above, so the stale master multiple survives and a
    # loss-maker wears a cheap-looking multiple. Same convention as
    # derive_missing_columns: the multiple is meaningless on a negative
    # denominator -> null it (EBIT <= EBITDA, so ebitda<=0 implies ebit<=0).
    _eb_now = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
    for _mult in ("ev_ebitda", "ev_ebit"):
        if _mult in m.columns:
            _bad = (_eb_now <= 0) & pd.to_numeric(m[_mult], errors="coerce").notna()
            m.loc[_bad, _mult] = np.nan
            if int(_bad.sum()):
                recon[f"{_mult} nulled (ebitda<=0)"] = int(_bad.sum())
    # NEGATIVE-EV multiples are KEPT (per user): negative EV over a positive
    # denominator is a real, interpretable number — you are paid to own the
    # earnings/sales. Only a NON-POSITIVE DENOMINATOR makes a multiple
    # meaningless (handled above). Flag the negative-EV rows so the state is
    # identifiable at a glance, and enforce SIGN consistency: with a positive
    # denominator the multiple must carry EV's sign.
    _ev_now = pd.to_numeric(m.get("enterprise_value"), errors="coerce")
    _qc_flag(( _ev_now < 0) & _ev_now.notna(), "neg_ev")
    for _mult, _den in (("ev_ebitda", _eb_now),):
        if _mult in m.columns:
            _mv = pd.to_numeric(m[_mult], errors="coerce")
            _wrong_sign = (_den > 0) & _mv.notna() & _ev_now.notna()                 & (np.sign(_mv) != np.sign(_ev_now)) & (_ev_now != 0)
            m.loc[_wrong_sign, _mult] = (_ev_now / _den)[_wrong_sign]
            if int(_wrong_sign.sum()):
                recon[f"{_mult} sign-fixed"] = int(_wrong_sign.sum())

    # remaining identifiability flags: anomalies that are KEPT (legitimate
    # accounting can produce them) but must never be silent.
    _fcf3 = pd.to_numeric(m.get("fcf_ttm"), errors="coerce")
    _cfo3 = pd.to_numeric(m.get("cfo_ttm"), errors="coerce")
    _cx3 = pd.to_numeric(m.get("capex_ttm"), errors="coerce")
    _qc_flag((_cfo3 > 0) & (_fcf3 > _cfo3 * 1.05), "fcf_gt_cfo")
    _td3 = pd.to_numeric(m.get("total_debt"), errors="coerce")
    _ca3 = pd.to_numeric(m.get("cash"), errors="coerce")
    _gap3 = ((_ev_now - (_mc + _td3 - _ca3)).abs() / _mc).where(_mc > 0)
    _qc_flag(_gap3 > 0.25, "ev_comp_gap")
    _rvu3 = pd.to_numeric(m.get("revenue_ttm_usd"), errors="coerce")
    _rv3 = pd.to_numeric(m.get("revenue_ttm"), errors="coerce")
    _ebu3 = pd.to_numeric(m.get("ebitda_ttm_usd"), errors="coerce")
    _eb3 = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
    _fx1 = (_rvu3 / _rv3).where(_rv3 != 0)
    _fx2 = (_ebu3 / _eb3).where(_eb3 != 0)
    _fx_bad = (_fx1 > 0) & (_fx2 > 0) & ((_fx1 / _fx2 > 1.10) | (_fx2 / _fx1 > 1.10))
    _qc_flag(_fx_bad, "fx_twin_dev")
    m["qc_flags"] = m["qc_flags"].str.lstrip("|")

    # persist the repair record — every reconciliation batch is identifiable
    # after the fact, not just in scrollback.
    try:
        import datetime as _dt, os as _os
        _os.makedirs("audit_reports", exist_ok=True)
        with open("audit_reports/reconcile_log.txt", "a") as _lf:
            _lf.write(f"\n=== {_dt.datetime.utcnow().isoformat()}Z "
                      f"apply_ticker_yf on {args.master} ===\n")
            for _c, _k in sorted(recon.items()):
                _lf.write(f"  {_c:44s} {_k}\n")
    except Exception as _e:
        print(f"  (reconcile log write failed: {_e})", file=sys.stderr)

    if recon:
        print("\nLevel/ratio reconciliation (master -> Yahoo where materially "
              "inconsistent):", file=sys.stderr)
        for c, k in recon.items():
            print(f"  {c:24s} repaired {k:6,}", file=sys.stderr)

    # Keep Yahoo-native extras
    for yf_col in YF_NATIVE_KEEP:
        if yf_col in y.columns:
            m[yf_col] = pd.to_numeric(y[yf_col], errors="coerce").reindex(m.index)

    # Provenance
    if "valuation_source" not in m.columns:
        m["valuation_source"] = ""
    has_yf_val = pd.to_numeric(y.get("yf_ev_ebitda"), errors="coerce").reindex(m.index).notna() \
        if "yf_ev_ebitda" in y.columns else pd.Series(False, index=m.index)
    m.loc[has_yf_val.fillna(False), "valuation_source"] = "yahoo"

    out = m.reset_index()
    # Sanitize any inf that slipped through (e.g. Yahoo forward PE / zero
    # denominators in native passthrough cols) so it never reaches a book.
    out = out.replace([np.inf, -np.inf], np.nan)
    out.to_csv(out_path, index=False)
    print(f"\nwrote {out_path}: {len(out):,} rows, {len(out.columns)} cols",
          file=sys.stderr)

    n = len(out)
    print("\nMerge results (col: before -> after, applied, mode):", file=sys.stderr)
    for col, (b, a, applied, mode) in sorted(changes.items(), key=lambda kv: -kv[1][2]):
        rej = rejected.get(col, 0)
        rej_s = f"  (rejected {rej} out-of-band)" if rej else ""
        print(f"  {col:24s} {b:6,} -> {a:6,}  applied={applied:6,}  [{mode}]  "
              f"{100*a/n:.1f}%{rej_s}", file=sys.stderr)
    total_rej = sum(rejected.values())
    if total_rej:
        print(f"\nTotal out-of-band Yahoo values rejected (kept master): {total_rej:,}",
              file=sys.stderr)


if __name__ == "__main__":
    main()
