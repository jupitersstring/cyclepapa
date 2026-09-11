"""Merge authoritative Yahoo fundamentals (ticker_yf.csv) into the master.

ticker_yf.py pulls Yahoo's own mcap / EV / EV-EBITDA / P/B / P/E and a
broad fundamentals set via the cookie/crumb quoteSummary endpoint — for
US *and* foreign tickers, which is the gap SEC XBRL can't reach.

Policy (the rigorous valuation process)
---------------------------------------
Trust hierarchy, applied in order, so every row ends INTERNALLY CONSISTENT:
  0. AUDITED EDGAR levels (us_edgar_yartseva.csv) are THE PREFERRED source
     for US filers — they win every level conflict; Yahoo arbitrates only
     where EDGAR has no figure (validated: Yahoo FCF/FCF-yield agree with
     audited accounts on only 30%/29% of names; see
     audit_reports/fcf_source_study.md). Provenance: qc_flags edgar_grounded.
  1. price / market_cap / enterprise_value: Yahoo, authoritative (overwrite —
     EDGAR carries no market data).
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
    # ---- SOURCE-FRAME CURRENCY BRIDGE (crosscheck round-2 root cause) ----
    # On a bridged (cross-currency) row, EVERY later adoption from y —
    # reconcile pull-backs, the statement-FCF waterfall, the capex rebuild —
    # must arrive already in the row's QUOTE currency. Re-adopting raw
    # financial-currency values per-column while re-restatement was
    # all-or-nothing left MIXED rows (ERIXF: raw-SEK EBITDA beside
    # converted-USD revenue). Bridging the source frame ONCE up front makes
    # every downstream path basis-coherent by construction. Yahoo's own EV
    # is deliberately NOT bridged (mixed by construction; rebuilt later).
    if "ccy_bridge" in m.columns:
        _br_src = pd.to_numeric(m["ccy_bridge"], errors="coerce")
        _br_y0 = _br_src.reindex(y.index)
        _has_br0 = _br_y0.notna() & (_br_y0 != 0)
        if int(_has_br0.sum()):
            for _ylc in ("yf_revenue", "yf_ebitda", "yf_cash", "yf_total_debt",
                         "yf_cfo", "yf_fcf", "yf_net_income", "yf_fcf_stmt",
                         "yf_cfo_stmt", "yf_capex_stmt", "yf_book_value"):
                if _ylc in y.columns:
                    _yv0 = pd.to_numeric(y[_ylc], errors="coerce")
                    y.loc[_has_br0, _ylc] = (_yv0 * _br_y0)[_has_br0]
            print(f"  bridged {int(_has_br0.sum())} cross-ccy source rows to quote currency",
                  file=sys.stderr)
    # AUDITED EDGAR levels (us_edgar_yartseva.csv) — THE PREFERRED SOURCE where
    # present (user directive): audited accounts outrank Yahoo for every level;
    # Yahoo arbitrates only where EDGAR has no figure. Market data (price/mcap/
    # EV) stays Yahoo — EDGAR carries no prices.
    try:
        ed = pd.read_csv("us_edgar_yartseva.csv", low_memory=False,
                         usecols=lambda c: c in {
                             "symbol", "revenue_ttm", "ebitda_ttm", "cfo_ttm",
                             "fcf_ttm", "cash", "total_debt", "op_margin",
                             "capex_ttm", "equity", "balance_sheet_date"}
                         ).drop_duplicates("symbol").set_index("symbol")
        # FRESHNESS GATE (user rule): prefer Yahoo when the EDGAR data is more
        # stale than ONE QUARTER — a period end older than ~135 days (one
        # 90-day quarter + ~45-day filing lag) means a newer filing exists
        # that this snapshot missed, and its TTM window is behind (KROS: the
        # stale audited window held a +72M milestone year vs the current
        # -97M burn).
        _bsd = pd.to_datetime(ed.get("balance_sheet_date"), errors="coerce")
        _fresh_ed = (pd.Timestamp.now() - _bsd).dt.days <= 135
        ed = ed[_fresh_ed.fillna(False)]
    except FileNotFoundError:
        ed = pd.DataFrame()
    _edavg_merged_n = 0
    # Audited MULTI-YEAR fields (Graham/Templeton averages, equity CAGR,
    # forensic balance items) merge STRUCTURALLY here — they were previously
    # carried into master by a one-off merge, so a rebuild silently dropped
    # them (the ni_avg-leg gates went dark). No TTM freshness gate: a 5-year
    # average is not invalidated by a missed quarter.
    try:
        _edavg = pd.read_csv("us_edgar_yartseva.csv", low_memory=False,
                             usecols=lambda c: c in {
                                 "symbol", "oe_avg", "ni_avg", "fcf_avg",
                                 "capex_avg", "oe_avg_years",
                                 "equity_cagr_5y", "financing_cf_ttm",
                                 "net_working_capital",
                                 "goodwill_intangibles_pct_assets",
                                 "capital_return_ttm", "dividends_ttm",
                                 "buybacks_ttm", "minority_interest",
                                 "preferred_equity"}
                             ).drop_duplicates("symbol").set_index("symbol")
        _n_avg = 0
        for _ac in _edavg.columns:
            if _ac not in m.columns:
                m[_ac] = np.nan
            _vv = pd.to_numeric(_edavg[_ac], errors="coerce").reindex(m.index)
            _upd = _vv.notna()
            m.loc[_upd, _ac] = _vv[_upd]
            _n_avg += int(_upd.sum())
        _edavg_merged_n = _n_avg
    except FileNotFoundError:
        pass

    def edgar_col(c, yahoo_series=None):
        if len(ed) and c in ed.columns:
            v = pd.to_numeric(ed[c], errors="coerce").reindex(m.index)
            # ABSENCE-OF-EVIDENCE GUARD (balance-sheet items): EDGAR's alias
            # sets are partial — a revolver under LineOfCredit or cash parked
            # in money-market instruments simply is not seen, producing a
            # HOLLOW low (TTEC: EDGAR debt 0 vs real $933M; STG: cash $82M vs
            # real $858M). An audited figure that is a SMALL FRACTION of the
            # fresh Yahoo figure is treated as incomplete coverage, not truth:
            # for cash/debt, EDGAR only wins when >= half of Yahoo's figure.
            if c in ("cash", "total_debt") and yahoo_series is not None:
                _hollow = v.notna() & yahoo_series.notna() \
                    & (yahoo_series > 0) & (v < 0.5 * yahoo_series)
                v = v.where(~_hollow)
            # SIGN-FLIP SUPERSESSION: when the audited and the fresh source
            # disagree in SIGN, a regime change (loss->profit or the reverse)
            # rolled through between their windows — only the FRESHER source
            # sees it, so Yahoo supersedes for that cell.
            if yahoo_series is not None:
                _flip = v.notna() & yahoo_series.notna() \
                    & (np.sign(v) != np.sign(yahoo_series)) \
                    & (v != 0) & (yahoo_series != 0)
                v = v.where(~_flip)
            return v
        return pd.Series(np.nan, index=m.index)
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
        _ni_margin = (pd.to_numeric(y["yf_profit_margin"], errors="coerce")
                      * pd.to_numeric(y["yf_revenue"], errors="coerce"))
        # DIRECT netIncomeToCommon (fetched as yf_net_income) outranks the
        # margin-implied construction; the implied value is last resort only.
        _ni_direct = pd.to_numeric(y.get("yf_net_income"), errors="coerce") \
            if "yf_net_income" in y.columns else pd.Series(np.nan, index=y.index)
        y["yf_net_income_implied"] = _ni_direct.combine_first(_ni_margin)
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
    # CFO window coherence (deep-trace round 9): fcf and capex adopt
    # STATEMENT-window figures where present, so cfo must prefer the same
    # window (yf_cfo_stmt) over the snapshot — mixing windows manufactured
    # fcf-vs-(cfo-capex) divergences on JP/OTC names.
    if "yf_cfo_stmt" in y.columns:
        _cfo_st0 = pd.to_numeric(y["yf_cfo_stmt"], errors="coerce")
        _cfo_sn0 = pd.to_numeric(y.get("yf_cfo"), errors="coerce")
        y["yf_cfo"] = _cfo_st0.where(_cfo_st0.notna(), _cfo_sn0)
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
                 ("yf_net_income_implied", "net_income_ttm", None),
                 # (spot-check finding) debt must be FRESH and lease-inclusive:
                 # Yahoo totalDebt capitalizes leases; master copies were stale
                 # (4629.T Y5M vs Y300M). A stale-LOW debt OVERSTATES net cash
                 # and therefore CashAdjPE/HiddenAssets cheapness — the
                 # conservative direction is the fresher, larger measure. Cash
                 # keeps its broad-basis exception; debt gets none.
                 ("yf_total_debt", "total_debt", None)]
    recon = {}
    if _edavg_merged_n:
        recon["EDGAR multi-year fields merged (averages/forensic)"] = _edavg_merged_n
    # audited EQUITY level (fresh-gated EDGAR) — the PRIMARY behind pb.
    _eq_ed_adopt = edgar_col("equity")
    if "equity" not in m.columns:
        m["equity"] = np.nan
    _eq_cur0 = pd.to_numeric(m["equity"], errors="coerce")
    _eq_upd0 = _eq_ed_adopt.notna() & (
        _eq_cur0.isna() | ((_eq_cur0 / _eq_ed_adopt) - 1).abs().gt(0.10))
    m.loc[_eq_upd0, "equity"] = _eq_ed_adopt[_eq_upd0]
    if int(_eq_upd0.sum()):
        recon["equity adopted from audited EDGAR"] = int(_eq_upd0.sum())
    repaired_any = pd.Series(False, index=m.index)
    edgar_won = pd.Series(False, index=m.index)
    for yf_col, mcol, usd_col in RECONCILE:
        if yf_col not in y.columns or mcol not in m.columns:
            continue
        _src_y = pd.to_numeric(y[yf_col], errors="coerce").reindex(m.index)
        _src_e = edgar_col(mcol, _src_y)
        src = _src_e.combine_first(_src_y)      # EDGAR preferred, Yahoo fills
        edgar_won |= _src_e.notna()
        cur = pd.to_numeric(m[mcol], errors="coerce")
        # cur == 0 IS a value and must be repairable: a hollow zero (TTEC
        # debt 0 vs real $933M) was immortal under a nonzero-cur guard.
        both = src.notna() & cur.notna() & (src != 0)
        ratio = (cur / src).where(both)
        disagree = both & ((ratio > 1.4) | (ratio < 1 / 1.4) | (cur == 0))
        if usd_col and usd_col in m.columns:
            usd = pd.to_numeric(m[usd_col], errors="coerce")
            factor = (src / cur).where(disagree)
            m.loc[disagree, usd_col] = (usd * factor)[disagree]
        m.loc[disagree, mcol] = src[disagree]
        recon[mcol] = int(disagree.sum())
        repaired_any |= disagree

    # cash — DIRECTIONAL reconcile: the broad-basis defense says master cash
    # (incl. investments) may legitimately EXCEED Yahoo's narrow totalCash —
    # but it can never legitimately sit at a FRACTION of it (STG: master 82M
    # vs Yahoo 858M = missing money-market instruments). Adopt Yahoo when the
    # master is under half of it; the broad side stays untouched.
    if "cash" in m.columns and "yf_cash" in y.columns:
        _ca_cur = pd.to_numeric(m["cash"], errors="coerce")
        _ca_y = pd.to_numeric(y["yf_cash"], errors="coerce").reindex(m.index)
        # (deep-trace round 9, GASS) stale-LOW cash at 0.59x Yahoo survived
        # the old half-rule: the broad-basis defense only ever justifies the
        # master sitting ABOVE Yahoo's narrow cash — BELOW it by more than
        # the reconcile tolerance is staleness, not basis. Adopt at <1/1.4.
        _poor = _ca_y.notna() & _ca_cur.notna() & (_ca_y > 0) \
            & (_ca_cur < _ca_y / 1.4)
        m.loc[_poor, "cash"] = _ca_y[_poor]
        recon["cash (directional: master stale-low vs Yahoo)"] = int(_poor.sum())

    # shares_outstanding: mcap and price are BOTH Yahoo-fresh, and shares is
    # definitionally mcap/price — a stale share count (splits, new issues) is
    # the only way the three can disagree. Snap it to mcap/price when >10% off.
    _p = pd.to_numeric(m.get("price"), errors="coerce")
    _mc = pd.to_numeric(m.get("market_cap"), errors="coerce")
    if "shares_outstanding" in m.columns:
        _sh = pd.to_numeric(m["shares_outstanding"], errors="coerce")
        # London lines are PENCE-priced (GBp) against GBP market caps — the
        # implied share count there is mcap/(price/100). The naive mcap/price
        # snap corrupted 6 .L names by 100x (caught by the pence-mint gate).
        _is_L = m.index.to_series().astype(str).str.endswith(".L")
        _eff_p = _p.where(~_is_L, _p / 100.0)
        _imp = (_mc / _eff_p).where((_eff_p > 0) & (_mc > 0))
        _dev = (_sh / _imp)
        _fix_sh = _imp.notna() & _sh.notna() & ((_dev > 1.10) | (_dev < 1 / 1.10))
        m.loc[_fix_sh, "shares_outstanding"] = _imp[_fix_sh]
        recon["shares_outstanding"] = int(_fix_sh.sum())

    # ----- CURRENCY ARBITRATION (EDGAR, any age <= 500d) -----
    # Foreign private issuers (20-F, annual-only) are ALWAYS older than the
    # one-quarter gate — and their Yahoo levels are exactly the population
    # with home-currency-vs-USD corruption (JFU/9F: Yahoo served CNY 289.9M
    # revenue & 207.7M CFO against a USD mcap; EDGAR audited USD 19.2M/29.7M,
    # and CFO/6.99 == EDGAR exactly = the FX rate). Detection: revenue AND cfo
    # both disagree with audited EDGAR by the SAME factor (within 30%), factor
    # in [2, 500] — a rate, not a restatement. Action: adopt the audited USD
    # levels for every field EDGAR carries, set USD twins equal (EDGAR is
    # USD), flag edgar_currency_arbitration. Stale-but-right-currency beats
    # fresh-but-wrong-currency.
    try:
        _edA = pd.read_csv("us_edgar_yartseva.csv", low_memory=False,
                           usecols=lambda c: c in {
                               "symbol", "revenue_ttm", "ebitda_ttm", "cfo_ttm",
                               "fcf_ttm", "cash", "total_debt",
                               "balance_sheet_date"}).drop_duplicates(
                           "symbol").set_index("symbol")
        _bsdA = pd.to_datetime(_edA.get("balance_sheet_date"), errors="coerce")
        _edA = _edA[(((pd.Timestamp.now() - _bsdA).dt.days <= 500)).fillna(False)]
    except FileNotFoundError:
        _edA = pd.DataFrame()
    if len(_edA):
        def _ea(c):
            return pd.to_numeric(_edA.get(c), errors="coerce").reindex(m.index)
        _r_rev = pd.to_numeric(m.get("revenue_ttm"), errors="coerce") / _ea("revenue_ttm")
        _r_cfo = pd.to_numeric(m.get("cfo_ttm"), errors="coerce") / _ea("cfo_ttm")
        # both flow fields inflated >2x vs audited USD is corruption regardless
        # of whether the factors cohere as one clean FX rate (JFU: 15.1x rev /
        # 7.0x cfo — messier than a rate, still wrong; audited wins).
        _fx_like = (_r_rev > 2) & (_r_rev < 500) & (_r_cfo > 2) & (_r_cfo < 500)
        _fx_like = _fx_like.fillna(False)
        if int(_fx_like.sum()):
            for _lvl in ("revenue_ttm", "ebitda_ttm", "cfo_ttm", "fcf_ttm",
                         "cash", "total_debt"):
                if _lvl in m.columns:
                    _ev_l = _ea(_lvl)
                    _mask_l = _fx_like & _ev_l.notna()
                    m.loc[_mask_l, _lvl] = _ev_l[_mask_l]
                    _twin = _lvl + "_usd"
                    if _twin in m.columns:
                        m.loc[_mask_l, _twin] = _ev_l[_mask_l]   # EDGAR is USD
            recon["currency arbitration (EDGAR usd adopted)"] = int(_fx_like.sum())
            _qc_flag_pending_currency = _fx_like
        else:
            _qc_flag_pending_currency = pd.Series(False, index=m.index)
    else:
        _qc_flag_pending_currency = pd.Series(False, index=m.index)

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
            if _mmc == "op_margin":
                _ysrc = edgar_col("op_margin").combine_first(_ysrc)  # audited margin preferred
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

    # capex_ttm — PRIMARY SOURCES ONLY (user directive: no identity
    # derivation where an alternative exists; and since every historical value
    # was identity-manufactured, the column is REBUILT from primaries each run
    # so no relic survives): audited EDGAR capex (fresh-gated) -> Yahoo
    # STATEMENT capex (|trailingCapitalExpenditure|) -> NaN (honest absence).
    if "capex_ttm" in m.columns:
        _cx_ed = edgar_col("capex_ttm")
        _cx_ed = _cx_ed.where(_cx_ed >= 0)
        _cx_stmt = pd.to_numeric(y.get("yf_capex_stmt"), errors="coerce").reindex(m.index).abs() \
            if "yf_capex_stmt" in y.columns else pd.Series(np.nan, index=m.index)
        _cx_new = _cx_ed.combine_first(_cx_stmt)
        _changed_cx = ~((_cx_new == pd.to_numeric(m["capex_ttm"], errors="coerce"))
                        | (_cx_new.isna() & pd.to_numeric(m["capex_ttm"], errors="coerce").isna()))
        m["capex_ttm"] = _cx_new
        recon["capex_ttm (rebuilt: EDGAR -> statement -> NaN)"] = int(_changed_cx.sum())

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

        # EDGAR audited FCF (same CFO-minus-capex basis) is PRIMARY where present
        _fcf_cur = pd.to_numeric(m["fcf_ttm"], errors="coerce")
        _fcf_ed = edgar_col("fcf_ttm", (_cfoB - _cx))
        _r_e = (_fcf_cur / _fcf_ed).where(_fcf_ed != 0)
        _dis_e = _fcf_ed.notna() & _fcf_cur.notna() \
            & ((_r_e > 1.4) | (_r_e < 1 / 1.4))
        _apply_fcf(_fcf_ed, _dis_e, "fcf_ttm (EDGAR audited, preferred)")
        # Yahoo STATEMENT-grade trailing FCF (fundamentals-timeseries; validated
        # == audited CFO-minus-capex, AAPL exact) — the arbiter where EDGAR has
        # no figure. NOT financialData.freeCashflow (that is third-party
        # levered FCF and stays retired).
        _fcf_stmt = pd.to_numeric(y.get("yf_fcf_stmt"), errors="coerce").reindex(m.index) \
            if "yf_fcf_stmt" in y.columns else pd.Series(np.nan, index=m.index)
        _fcf_cur = pd.to_numeric(m["fcf_ttm"], errors="coerce")
        _r_s = (_fcf_cur / _fcf_stmt).where(_fcf_stmt != 0)
        _dis_s = _fcf_stmt.notna() & _fcf_cur.notna() & _fcf_ed.isna() \
            & ((_r_s > 1.4) | (_r_s < 1 / 1.4))
        _apply_fcf(_fcf_stmt, _dis_s, "fcf_ttm (Yahoo statement trailing, non-EDGAR)")
        # (identity fallback REMOVED per user directive — where neither the
        # audited nor the statement source covers a name, its snapshot fcf
        # stands or the field stays honestly absent.)

    # ---- CROSS-CURRENCY LINE RESTATEMENT (root repair, not a null) ----
    # A secondary listing (Frankfurt .F, OTC pinksheet, LSE line of a foreign
    # company, B-share) quotes in one currency while Yahoo serves its
    # statement LEVELS in the company's FINANCIAL currency. Every
    # level-over-mcap and level-over-EV ratio on such a line is then off by
    # exactly the fx factor — 150x for a JPY company on a USD line, and the
    # moderate cases (GBP/USD, 1.3x) sit INSIDE every sanity band, silently.
    # Evidence-based repair: rows sharing a normalized company name form a
    # group; the group's financial currency is the home line's quote currency
    # (the line whose quote currency matches its country's currency). A
    # sibling line whose raw levels MATCH the home line's (unconverted
    # evidence) while its quote currency differs gets its level columns
    # RESTATED into its own quote currency via the fx bridge
    # b = fx_fin_to_usd / fx_quote_to_usd, so every downstream recompute
    # (yields, multiples, EV, net-cash family) is automatically correct.
    # Price-quoted ratios Yahoo built cross-currency (pb, p_e) divide by b.
    _restated_mask = pd.Series(False, index=m.index)
    _noanchor_mask = pd.Series(False, index=m.index)
    _CTRY_CCY = {
        "United States": "USD", "Japan": "JPY", "United Kingdom": "GBP",
        "Canada": "CAD", "Australia": "AUD", "Hong Kong": "HKD",
        "China": "CNY", "South Korea": "KRW", "Taiwan": "TWD",
        "India": "INR", "Singapore": "SGD", "Thailand": "THB",
        "Malaysia": "MYR", "Indonesia": "IDR", "Sweden": "SEK",
        "Norway": "NOK", "Denmark": "DKK", "Finland": "EUR",
        "Germany": "EUR", "France": "EUR", "Netherlands": "EUR",
        "Italy": "EUR", "Spain": "EUR", "Belgium": "EUR",
        "Austria": "EUR", "Portugal": "EUR", "Ireland": "EUR",
        "Greece": "EUR", "Switzerland": "CHF", "Poland": "PLN",
        "Turkey": "TRY", "Israel": "ILS", "Brazil": "BRL",
        "Mexico": "MXN", "South Africa": "ZAR", "New Zealand": "NZD",
        "Philippines": "PHP", "Vietnam": "VND", "Chile": "CLP",
        "Saudi Arabia": "SAR", "United Arab Emirates": "AED",
        "Qatar": "QAR", "Kuwait": "KWD", "Egypt": "EGP",
    }
    _LEVEL_COLS = [c for c in (
        "cash", "total_debt", "revenue_ttm", "ebitda_ttm", "net_income_ttm",
        "cfo_ttm", "fcf_ttm", "capex_ttm", "ncav", "net_cash", "ebit_ttm",
        "gross_profit_ttm", "financing_cf_ttm", "net_working_capital",
        "oe_avg", "ni_avg", "fcf_avg", "capex_avg", "normalized_ebitda",
        "normalized_ebit", "normalized_revenue", "net_buyback_ttm",
        "equity", "tangible_equity",
    ) if c in m.columns]
    if "name" in m.columns and "currency" in m.columns and "fx_to_usd" in m.columns:
        import re as _re_ccy
        _nn = m["name"].map(lambda s: _re_ccy.sub(
            r"[^a-z0-9]", "", _re_ccy.sub(
                r"\b(inc|corp|corporation|ltd|limited|plc|co|company|holdings?"
                r"|group|ag|se|sa|nv|kk|gmbh|the|adr)\b", "",
                str(s).lower())))
        _cur = m["currency"].astype(str).str.upper().replace({"GBP": "GBP", "GBX": "GBP", "GBP0.01": "GBP"})
        _fx = pd.to_numeric(m["fx_to_usd"], errors="coerce")
        # fx per currency code (mode across rows — one rate per code)
        _fx_by_ccy = _fx.groupby(_cur).median()
        _fin_ccy_row = m["country"].map(_CTRY_CCY) if "country" in m.columns else pd.Series(np.nan, index=m.index)
        _grp = pd.DataFrame({"nn": _nn, "cur": _cur, "fin": _fin_ccy_row,
                             "rev": pd.to_numeric(m.get("revenue_ttm"), errors="coerce"),
                             "ca": pd.to_numeric(m.get("cash"), errors="coerce")})
        _grp = _grp[_grp["nn"].str.len() > 3]
        # ---- PASS 0: DECLARED FINANCIAL CURRENCY (authoritative) ----
        # Yahoo's financialData.financialCurrency names the statements'
        # currency outright (1900.HK: quote HKD, financialCurrency CNY) —
        # where fetched, it SUPERSEDES every inference below: a declared
        # mismatch is restated with the exact fx bridge, a declared match
        # is verified-coherent and exempt from the no-anchor treatment.
        _CENTS_MAJ = {"GBP": "GBP", "GBX": "GBP", "ZAC": "ZAR", "ILA": "ILS"}
        _decl_fin = (y["yf_financial_currency"].astype(str).str.upper()
                     .reindex(m.index)
                     if "yf_financial_currency" in y.columns
                     else pd.Series(np.nan, index=m.index))
        _decl_fin = _decl_fin.replace({"NAN": np.nan, "NONE": np.nan, "": np.nan})
        _decl_q = (y["yf_quote_currency"].astype(str).str.upper().reindex(m.index)
                   if "yf_quote_currency" in y.columns
                   else _cur.reindex(m.index))
        _decl_q = _decl_q.replace(_CENTS_MAJ).replace({"NAN": np.nan, "": np.nan})
        _decl_q = _decl_q.where(_decl_q.notna(), _cur.reindex(m.index))
        _decl_known = _decl_fin.notna() & _decl_q.notna()
        _bD = _decl_fin.map(_fx_by_ccy) / _decl_q.map(_fx_by_ccy)
        # ANY declared mismatch restates — no magnitude threshold: the
        # declaration removes the ambiguity the threshold guarded against,
        # and a 15% EUR/USD error is still an error.
        _needD = (_decl_known & (_decl_fin != _decl_q)
                  & _bD.notna() & (_bD != 1.0)).fillna(False)
        # rows already carrying a bridge are maintained by the SOURCE-frame
        # conversion (their incoming levels arrive pre-converted) — running
        # the in-master multiplication again would double-convert them
        if "ccy_bridge" in m.columns:
            _needD &= ~pd.to_numeric(m["ccy_bridge"], errors="coerce").notna()
        # UN-RESTATEMENT (spot-check round 8 finding): the country/twin
        # inference restated USD-REPORTING foreign companies (Genel, Yara,
        # Hunting OTC — financial ccy != country ccy), corrupting correct
        # levels by the bridge. Where Yahoo now DECLARES quote==financial,
        # a previously-restated row is un-restated: reconcile-covered
        # levels re-adopt the fresh raw figure, build-only levels divide
        # by the stored ccy_bridge, and the flag clears.
        _decl_same = (_decl_known & (_decl_fin == _decl_q)).fillna(False)
        _was_rs0 = (m["qc_flags"].fillna("").astype(str)
                    .str.contains("ccy_restated")
                    if "qc_flags" in m.columns
                    else pd.Series(False, index=m.index))
        _undo = _decl_same & _was_rs0
        if int(_undo.sum()) and "ccy_bridge" in m.columns:
            _obr = pd.to_numeric(m["ccy_bridge"], errors="coerce")
            for _mcol_u, _ycol_u in (("revenue_ttm", "yf_revenue"),
                                     ("ebitda_ttm", "yf_ebitda"),
                                     ("cash", "yf_cash"),
                                     ("total_debt", "yf_total_debt"),
                                     ("cfo_ttm", "yf_cfo"),
                                     ("net_income_ttm", "yf_net_income")):
                if _mcol_u in m.columns and _ycol_u in y.columns:
                    _yv_u = pd.to_numeric(y[_ycol_u], errors="coerce").reindex(m.index)
                    _hit_u = _undo & _yv_u.notna()
                    m.loc[_hit_u, _mcol_u] = _yv_u[_hit_u]
            for _bcol_u in ("ncav", "net_cash", "net_buyback_ttm",
                            "normalized_ebitda", "normalized_ebit",
                            "normalized_revenue", "gross_profit_ttm",
                            "ebit_ttm"):
                if _bcol_u in m.columns:
                    _bv_u = pd.to_numeric(m[_bcol_u], errors="coerce")
                    _hit_u = _undo & _obr.notna() & (_obr != 0)
                    m.loc[_hit_u, _bcol_u] = (_bv_u / _obr)[_hit_u]
            m.loc[_undo, "ccy_bridge"] = np.nan
            m["qc_flags"] = m["qc_flags"].astype(str).where(
                ~_undo, m["qc_flags"].astype(str)
                .str.replace("ccy_restated", "", regex=False))
            recon["cross-ccy restatement UNDONE (declared same-currency)"] = int(_undo.sum())
        if int(_needD.sum()):
            for _lc in _LEVEL_COLS:
                _v = pd.to_numeric(m[_lc], errors="coerce")
                m.loc[_needD, _lc] = (_v * _bD)[_needD]
            for _uc, _lc in (("revenue_ttm_usd", "revenue_ttm"),
                             ("ebitda_ttm_usd", "ebitda_ttm"),
                             ("fcf_ttm_usd", "fcf_ttm"),
                             ("net_cash_usd", "net_cash"),
                             ("ncav_usd", "ncav")):
                if _uc in m.columns and _lc in m.columns:
                    _lv = pd.to_numeric(m[_lc], errors="coerce")
                    m.loc[_needD, _uc] = (_lv * _fx)[_needD]
            if "p_e" in m.columns:
                _ni_d = pd.to_numeric(m["net_income_ttm"], errors="coerce")
                m.loc[_needD, "p_e"] = ((_mc / _ni_d).where(_ni_d > 0))[_needD]
            if "ccy_bridge" not in m.columns:
                m["ccy_bridge"] = np.nan
            m.loc[_needD, "ccy_bridge"] = _bD[_needD]
            recon["cross-ccy restated (DECLARED financial currency)"] = int(_needD.sum())
        _restated_mask = _restated_mask | _needD
        # group financial currency = home line's quote currency: the line
        # whose quote currency equals its own country's currency.
        _home = _grp[_grp["cur"] == _grp["fin"]]
        _fin_by_name = _home.groupby("nn")["fin"].agg(
            lambda s: s.mode().iloc[0] if len(s.mode()) else np.nan)
        _ref_rev = _home.groupby("nn")["rev"].median()
        _ref_ca = _home.groupby("nn")["ca"].median()
        _g_fin = _grp["nn"].map(_fin_by_name)
        _g_rrev = _grp["nn"].map(_ref_rev)
        _g_rca = _grp["nn"].map(_ref_ca)
        # unconverted evidence: raw levels match the home line's raw levels.
        # Band ±10%: TTM vintages drift between fetch dates (Chudenko's OTC
        # line sat at 1.054x its home line and was missed at ±5%), while a
        # REAL fx factor is >=1.25x by the bridge gate below — the two are
        # not confusable.
        _lvl_match = (((_grp["rev"] / _g_rrev).between(0.90, 1.10))
                      | (_grp["rev"].isna() & (_grp["ca"] / _g_rca).between(0.90, 1.10)))
        _b = _g_fin.map(_fx_by_ccy) / _grp["cur"].map(_fx_by_ccy)
        _need = (_g_fin.notna() & (_grp["cur"] != _g_fin)
                 & _lvl_match.fillna(False)
                 & _b.notna() & ((_b > 1.25) | (_b < 0.8))
                 # any row with a DECLARED currency is settled by PASS 0 —
                 # inference must never override or double-convert it (the
                 # country/twin heuristic mis-restated USD-reporting
                 # foreign firms; declarations retire it row by row)
                 & ~_decl_known.reindex(_grp.index).fillna(False))
        _twin_mask = _need.reindex(m.index).fillna(False)
        _restated_mask = _restated_mask | _twin_mask
        if int(_twin_mask.sum()):
            _bv = _b.reindex(m.index)
            for _lc in _LEVEL_COLS:
                _v = pd.to_numeric(m[_lc], errors="coerce")
                m.loc[_twin_mask, _lc] = (_v * _bv)[_twin_mask]
            # pb: Yahoo is INCONSISTENT across secondary lines — some carry
            # price_quote/bookvalue_fin (needs /b), others already-converted
            # book (correct as stored; HOIEF showed 0.83 correct, and a
            # blanket /b would print 133). Never scale blindly: recompute
            # from the row's own CONVERTED net income and its currency-free
            # roe (equity = NI/roe, now in quote ccy) where that evidence
            # exists; otherwise leave the stored value (row is flagged).
            if "pb" in m.columns:
                _ever_rs = _restated_mask
                if "qc_flags" in m.columns:
                    _ever_rs = _ever_rs | m["qc_flags"].fillna("").astype(str) \
                        .str.contains("ccy_restated")
                _ni_cv = pd.to_numeric(m["net_income_ttm"], errors="coerce")
                _roe_cv = pd.to_numeric(m.get("roe"), errors="coerce")
                _eq_cv = (_ni_cv / _roe_cv).where(_roe_cv != 0)
                _pb_tru = (_mc / _eq_cv).where(_eq_cv > 0)
                _has_pb = _ever_rs & _pb_tru.notna()
                m.loc[_has_pb, "pb"] = _pb_tru[_has_pb]
                recon["pb recomputed on cross-ccy lines (NI/roe equity)"] = int(_has_pb.sum())
            # p_e is recomputed outright from the RESTATED net income — the
            # identity, not a scaled guess (the p_e-vs-mcap/NI audit gate
            # verifies it).
            if "p_e" in m.columns:
                _ever_rs2 = _restated_mask
                if "qc_flags" in m.columns:
                    _ever_rs2 = _ever_rs2 | m["qc_flags"].fillna("").astype(str) \
                        .str.contains("ccy_restated")
                _ni_rs = pd.to_numeric(m["net_income_ttm"], errors="coerce")
                _pe_rs = (_mc / _ni_rs).where(_ni_rs > 0)
                m.loc[_ever_rs2, "p_e"] = _pe_rs[_ever_rs2]
            # *_usd columns: converted level (quote ccy) x quote fx == level_fin x fx_fin
            for _uc, _lc in (("revenue_ttm_usd", "revenue_ttm"),
                             ("ebitda_ttm_usd", "ebitda_ttm"),
                             ("fcf_ttm_usd", "fcf_ttm"),
                             ("net_cash_usd", "net_cash"),
                             ("ncav_usd", "ncav")):
                if _uc in m.columns and _lc in m.columns:
                    _lv = pd.to_numeric(m[_lc], errors="coerce")
                    m.loc[_twin_mask, _uc] = (_lv * _fx)[_twin_mask]
            pass
        # NO-ANCHOR MIXED GROUPS: siblings share IDENTICAL raw levels while
        # quoting in DIFFERENT currencies, but no home line exists in master
        # to anchor the financial currency (New China Life: NWWCF/USD and
        # NCL.F/EUR share raw CNY levels; at most one quote currency can be
        # coherent and neither is provable). Every quote-vs-level ratio on
        # such rows is unverifiable-and-likely-corrupt — and the moderate
        # cases (p_s 0.24 from JPY-over-USD) sit INSIDE every band. Null the
        # quote-vs-level ratios on ALL group members and flag; repairable
        # once yf_financial_currency arrives with the next fetch.
        _n_ccy = _grp.groupby("nn")["cur"].transform("nunique")
        _has_home = _grp["nn"].map(_fin_by_name).notna()
        _noanchor_mask = ((_n_ccy > 1) & ~_has_home).reindex(m.index).fillna(False)
        # only rows whose group actually shares raw levels (true mixed group)
        _grp_ref_rev = _grp.groupby("nn")["rev"].transform("median")
        _shares_lvl = ((_grp["rev"] / _grp_ref_rev).between(0.90, 1.10)).reindex(m.index).fillna(False)
        _noanchor_mask &= _shares_lvl
        # a row with a DECLARED financial currency is not unknowable: a
        # declared match is verified-coherent, a declared mismatch was
        # restated above — either way it leaves the no-anchor class.
        _noanchor_mask &= ~_decl_known.fillna(False)
        # NEVER null the group's principal line: without a country anchor the
        # largest-mcap-USD line is presumed home (Freddie Mac's US OTC line
        # was being nulled beside its tiny Frankfurt satellite because its
        # country field is empty). Satellites are duplicates — the company
        # stays represented through the presumed-home line. (A presumed-home
        # line whose financials are in yet another currency — the XP/BRL
        # class — is undetectable until yf_financial_currency lands.)
        _mcu_g = (pd.to_numeric(m.get("market_cap"), errors="coerce") * _fx)
        _gmax = pd.DataFrame({"nn": _nn, "mcu": _mcu_g}).groupby("nn")["mcu"].transform("max")
        _is_principal = (_mcu_g >= _gmax * 0.999).fillna(False)
        _noanchor_mask &= ~_is_principal.reindex(m.index).fillna(False)
        # (the actual ratio nulls happen in the LATE sanitation region — after
        # every recompute — or they would be refilled from the raw levels)
        if int(_twin_mask.sum()):
            # persist the bridge so later merges of financial-currency data
            # onto a restated row can convert without re-deriving the twin
            if "ccy_bridge" not in m.columns:
                m["ccy_bridge"] = np.nan
            m.loc[_twin_mask, "ccy_bridge"] = _bv[_twin_mask]
            recon["cross-ccy line levels restated to quote currency (twin)"] = int(_twin_mask.sum())
        # ---- SECOND PASS, PB-ANCHORED (no twin needed) ----
        # An unconverted line whose home listing is NOT in master has no
        # twin — but Yahoo's priceToBook on such lines is CONVERTED and
        # sane (SKY Perfect JSAT OTC: pb 0.88 correct while NI/roe equity
        # is raw JPY), so pb anchors the bridge: b = (mcap/pb)/(NI/roe).
        # The noisy estimate is only ACCEPTED when it sits within ±20% of a
        # REAL currency pair's fx ratio, and then the EXACT rate is used —
        # never the estimate itself.
        _pb_a2 = pd.to_numeric(m.get("pb"), errors="coerce")
        _roe_a2 = pd.to_numeric(m.get("roe"), errors="coerce")
        _ni_a2 = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")
        _eq_q = (_mc / _pb_a2).where((_pb_a2 > 0.05) & (_pb_a2 < 50))
        _eq_f = (_ni_a2 / _roe_a2).where((_roe_a2 != 0) & _ni_a2.notna())
        _b_raw = (_eq_q / _eq_f).where(_eq_f.abs() > 0)
        _cur_m = _cur.reindex(m.index)
        _fx_q2 = _cur_m.map(_fx_by_ccy)
        _cand = None
        for _k, _fxk in _fx_by_ccy.items():
            _b_k = _fxk / _fx_q2      # exact rate for candidate fin ccy k
            _close = (_b_raw / _b_k).between(0.8, 1.25) & ((_b_k > 1.25) | (_b_k < 0.8))
            _cand = _b_k.where(_close) if _cand is None else _cand.where(_cand.notna(), _b_k.where(_close))
        _need2 = (_cand.notna() & ~_restated_mask.reindex(m.index).fillna(False)
                  & ~_decl_known.reindex(m.index).fillna(False)
                  & ((_b_raw > 20) | (_b_raw < 0.05)))   # unambiguous, far-fx class only
        _need2 = _need2.fillna(False)
        if int(_need2.sum()):
            _bv2 = _cand
            for _lc in _LEVEL_COLS:
                _v = pd.to_numeric(m[_lc], errors="coerce")
                m.loc[_need2, _lc] = (_v * _bv2)[_need2]
            for _uc, _lc in (("revenue_ttm_usd", "revenue_ttm"),
                             ("ebitda_ttm_usd", "ebitda_ttm"),
                             ("fcf_ttm_usd", "fcf_ttm"),
                             ("net_cash_usd", "net_cash"),
                             ("ncav_usd", "ncav")):
                if _uc in m.columns and _lc in m.columns:
                    _lv = pd.to_numeric(m[_lc], errors="coerce")
                    m.loc[_need2, _uc] = (_lv * _fx)[_need2]
            if "p_e" in m.columns:
                _ni_r2 = pd.to_numeric(m["net_income_ttm"], errors="coerce")
                _pe_r2 = (_mc / _ni_r2).where(_ni_r2 > 0)
                m.loc[_need2, "p_e"] = _pe_r2[_need2]
            if "ccy_bridge" not in m.columns:
                m["ccy_bridge"] = np.nan
            m.loc[_need2, "ccy_bridge"] = _bv2[_need2]
            recon["cross-ccy line levels restated (pb-anchored, twinless)"] = int(_need2.sum())
            _restated_mask = _restated_mask | _need2

        # ---- EV/PRICE RATIO REBUILD on every EVER-restated line ----
        # Yahoo's own enterpriseValue and its multiples are built from the
        # MIXED-currency raw levels on these lines (T3O.F proof: EV ≈ quote
        # mcap + raw JPY net debt), and every run's Yahoo overwrite
        # re-adopts them — so EV, EV multiples and the price ratios are
        # reconstructed HERE from the restated components on every run.
        # Yahoo's pre-computed ratios stay authoritative everywhere else.
        _ever_rs3 = _restated_mask
        if "qc_flags" in m.columns:
            _ever_rs3 = _ever_rs3 | m["qc_flags"].fillna("").astype(str) \
                .str.contains("ccy_restated")
        if int(_ever_rs3.sum()):
            _ca_r = pd.to_numeric(m.get("cash"), errors="coerce")
            _td_r = pd.to_numeric(m.get("total_debt"), errors="coerce")
            _eb_r = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
            _rv_r = pd.to_numeric(m.get("revenue_ttm"), errors="coerce")
            _om_r = pd.to_numeric(m.get("op_margin"), errors="coerce")
            _ni_r3 = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")
            _ev_r = (_mc + _td_r.fillna(0) - _ca_r.fillna(0)).where(_mc.notna())
            if "enterprise_value" in m.columns:
                m.loc[_ever_rs3, "enterprise_value"] = _ev_r[_ever_rs3]
            if "enterprise_value_usd" in m.columns:
                m.loc[_ever_rs3, "enterprise_value_usd"] = (_ev_r * _fx)[_ever_rs3]
            for _rcol, _num_s, _den_s in (
                    ("ev_ebitda", _ev_r, _eb_r),
                    ("ev_sales", _ev_r, _rv_r),
                    ("ev_ebit", _ev_r, _om_r * _rv_r),
                    ("p_e", _mc, _ni_r3),
                    ("p_s", _mc, _rv_r)):
                if _rcol in m.columns:
                    _mv = (_num_s / _den_s).where(_den_s > 0)
                    m.loc[_ever_rs3, _rcol] = _mv[_ever_rs3]
            recon["EV/price ratios rebuilt on cross-ccy lines"] = int(_ever_rs3.sum())

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
    _recompute("fcf_yield", (_fcf / _mc).where(_mc > 0), band=(-1.0, 1.0))  # |FCF| beyond 100% of mcap in EITHER sign is a unit/ADR mismatch, not information (YYAI at -33x/+77x)
    if "fcf_yield" in m.columns:
        _fy_now = pd.to_numeric(m["fcf_yield"], errors="coerce")
        _fy_fresh_imposs = ((_fcf / _mc).abs() > 1.0) & _fcf.notna() & (_mc > 0)
        # when the COMPONENTS prove corruption (|fcf/mcap|>1, the ADR unit
        # class — WIMI at -4.16x), the stored yield is equally untrustworthy:
        # null it too, never let a stale plausible-looking number survive a
        # provably-corrupt recomputation (band-reject alone left it standing).
        _fy_bad = (_fy_now.abs() > 1.0) | (_fy_fresh_imposs & _fy_now.notna())
        m.loc[_fy_bad, "fcf_yield"] = np.nan
        if int(_fy_bad.sum()):
            recon["fcf_yield nulled (impossible level/components)"] = int(_fy_bad.sum())
    # The whole equity-cash-yield family shares the mcap denominator and the
    # same price-staleness disease (computed once at derive-time, then price
    # moves): recompute them all from current components every run. These feed
    # the melt logic (_cash_return_ok) and the weschler/liger cheapness gates.
    _cfo2 = pd.to_numeric(m.get("cfo_ttm"), errors="coerce")
    _ni3 = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")
    # (owner_earnings_yield is rebuilt in the LATE sanitation region — after
    # the margin ordering/de-minimis nulls — because its implied D&A uses
    # op_margin: built here it could hold a value its FINAL components no
    # longer reproduce, the KTTA class.)
    _recompute("cfo_yield", (_cfo2 / _mc).where(_mc > 0), band=(-50, 50))
    _recompute("earnings_yield", (_ni3 / _mc).where(_mc > 0), band=(-50, 50))
    if "robust_cash_yield" in m.columns:
        _rcy_new = pd.concat([(_fcf / _mc).where(_mc > 0),
                              (_cfo2 / _mc).where(_mc > 0),
                              (_ni3 / _mc).where(_mc > 0)],
                             axis=1).median(axis=1, skipna=True)
        _recompute("robust_cash_yield", _rcy_new, band=(-50, 50))
    # payout yields — audited EDGAR flow LEVELS over CURRENT mcap (they were
    # frozen against map-time mcap, the ncav vintage disease).
    for _yc2, _lc2 in (("capital_return_yield", "capital_return_ttm"),
                       ("buyback_yield", "buybacks_ttm")):
        if _lc2 in m.columns:
            _lv2 = pd.to_numeric(m[_lc2], errors="coerce")
            _recompute(_yc2, (_lv2 / _mc).where(_mc > 0), band=(0, 2))
    # PRICE-HISTORY EVIDENCE BOUND: a 1-year return cannot exceed the 52-week
    # range by multiples — 1841.T's price_yoy of +14,413,000% is a
    # redenomination artifact, not a return. Null price_yoy (and its alias
    # momentum_12m) where (1+yoy) is over 3x the high/low span, or where
    # yoy < -1 (price below zero — impossible).
    _hi_py = pd.to_numeric(m.get("price_52w_high"), errors="coerce")
    _lo_py = pd.to_numeric(m.get("yf_52w_low"), errors="coerce")
    _span_py = (_hi_py / _lo_py).where((_lo_py > 0) & (_hi_py > 0))
    for _pyc in ("price_yoy", "momentum_12m"):
        if _pyc in m.columns:
            _pyv = pd.to_numeric(m[_pyc], errors="coerce")
            _py_bad = ((_pyv < -1)
                       | (_span_py.notna() & ((1 + _pyv) > 3 * _span_py))).fillna(False)
            m.loc[_py_bad, _pyc] = np.nan
            if int(_py_bad.sum()):
                recon[f"{_pyc} nulled (return exceeds 52w-range evidence)"] = int(_py_bad.sum())

    # net_cash_pct_mcap = (broad cash - fresh debt) / current mcap — gates the
    # net-cash archetype family (liger/oak/negative-EV) and was never refreshed.
    _ca_nc = pd.to_numeric(m.get("cash"), errors="coerce")
    _td_nc = pd.to_numeric(m.get("total_debt"), errors="coerce")
    _recompute("net_cash_pct_mcap",
               ((_ca_nc - _td_nc) / _mc).where(_mc > 0), band=(-50, 50))
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
    _qc_flag(edgar_won, "edgar_grounded")
    _qc_flag(_qc_flag_pending_currency, "edgar_currency_arbitration")
    _row_consistent("p_e", (_mc / _ni2).where(_ni2 > 0), _pe_yf, band=(0, 2000))
    # (NI-from-p_e derivation REMOVED per user directive: NI now comes from
    # audited EDGAR, Yahoo's DIRECT netIncomeToCommon (yf_net_income), or the
    # margin-implied last resort — never back-derived from a ratio.)
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

    # PAIRING ENFORCEMENT after reconciliation: debt/nde just changed, so a
    # name that BECAME materially levered must not keep a CFO/EV approximation
    # computed under its old balance sheet (unlevered flows only over EV).
    _nde_pr = pd.to_numeric(m.get("net_debt_ebitda"), errors="coerce")
    _ncp_pr = pd.to_numeric(m.get("net_cash_pct_mcap"), errors="coerce")
    _icov_pr = pd.to_numeric(m.get("interest_coverage"), errors="coerce")
    _lev_pr = (_nde_pr > 0.5) & (_nde_pr < 90) & (_ncp_pr < 0) & _icov_pr.isna()
    for _uc in ("cash_return_ev", "ufcf_yield"):
        if _uc in m.columns:
            _bad_uc = _lev_pr & pd.to_numeric(m[_uc], errors="coerce").notna()
            m.loc[_bad_uc, _uc] = np.nan
            if int(_bad_uc.sum()):
                recon[f"{_uc} nulled (levered, no interest data)"] = int(_bad_uc.sum())

    # UNIT-SANITY LEVEL REPAIR: when the components imply an ABSURD multiple
    # (outside (0.001, 500) — a KRW-vs-thousands / mixed-unit level) while the
    # stored ratio is in-band and plausible, the LEVEL is the corrupt side:
    # repair it from EV / stored-ratio (USD twin rescaled).
    for _rat_c, _lvl_c, _usd_c in (("ev_ebitda", "ebitda_ttm", "ebitda_ttm_usd"),
                                   ("ev_sales", "revenue_ttm", "revenue_ttm_usd")):
        if _rat_c not in m.columns or _lvl_c not in m.columns:
            continue
        _rv_u = pd.to_numeric(m[_rat_c], errors="coerce")
        _lv_u = pd.to_numeric(m[_lvl_c], errors="coerce")
        _ev_u = pd.to_numeric(m.get("enterprise_value"), errors="coerce")
        _impl_mult = (_ev_u / _lv_u).where((_lv_u > 0) & (_ev_u > 0))
        _absurd = _impl_mult.notna() & ((_impl_mult > 500) | (_impl_mult < 1e-3))
        _plaus = _rv_u.notna() & (_rv_u > 1e-3) & (_rv_u <= 500)
        _fix_u = _absurd & _plaus
        _new_lvl = (_ev_u / _rv_u).where(_fix_u)
        if _usd_c in m.columns:
            _usd_u = pd.to_numeric(m[_usd_c], errors="coerce")
            _fac_u = (_new_lvl / _lv_u).where(_fix_u & (_lv_u != 0))
            m.loc[_fix_u, _usd_c] = (_usd_u * _fac_u)[_fix_u]
        m.loc[_fix_u, _lvl_c] = _new_lvl[_fix_u]
        if int(_fix_u.sum()):
            recon[f"{_lvl_c} unit-repaired (from in-band {_rat_c})"] = int(_fix_u.sum())
            _qc_flag(_fix_u, "unit_repaired")

    # DE-MINIMIS REVENUE: under $0.5M USD TTM revenue a sales multiple or a
    # margin is arithmetic noise on a near-empty denominator (ASCLF-class
    # shells showing P/S 695) — null the revenue-denominated ratios there.
    _rvu_dm = pd.to_numeric(m.get("revenue_ttm_usd"), errors="coerce")
    _dm = (_rvu_dm > 0) & (_rvu_dm < 2e6)   # $2M: no gate reads a sales ratio below the $5M revenue floors anyway (ASCLF at $0.9M rev / $1.4B mcap showed P/S 695)
    for _dc in ("p_s", "ev_sales", "ebitda_margin", "gross_margin", "op_margin"):
        if _dc in m.columns:
            _hit = _dm & pd.to_numeric(m[_dc], errors="coerce").notna()
            m.loc[_hit, _dc] = np.nan
            if int(_hit.sum()):
                recon[f"{_dc} nulled (de-minimis revenue)"] =                     recon.get(f"{_dc} nulled (de-minimis revenue)", 0) + int(_hit.sum())

    # CROSS-CURRENCY CASH-FAMILY IMPOSSIBILITY BAND: net cash above 20x market
    # cap cannot persist in a real market (someone tenders) — every observed
    # case is a listing whose BALANCE LEVELS are home-currency while mcap is
    # quote-currency (Frankfurt .F lines, OTC ...F pinksheets: T3O.F showed
    # "74x mcap" in cash = JPY levels over a EUR mcap). fx_to_usd is keyed off
    # the QUOTE currency, so the *_usd twins agree with each other and can't
    # catch it — the magnitude itself is the only in-band evidence. Null the
    # mcap-vs-level cash family on those rows and flag them; the real cure
    # (fetching financialCurrency and converting levels) lands with the next
    # full fetch (ticker_yf now requests it).
    # flag hygiene: this tag is re-derived from CURRENT evidence each run
    # (both here and in the no-anchor block) — a row that no longer earns it
    # (a principal line spared by the presumed-home rule) must not keep it.
    if "qc_flags" in m.columns:
        m["qc_flags"] = m["qc_flags"].fillna("").astype(str).str.replace(
            "ccy_mismatch_suspect", "", regex=False)
    _ca_x = pd.to_numeric(m.get("cash"), errors="coerce")
    _td_x = pd.to_numeric(m.get("total_debt"), errors="coerce")
    _ccy_bad = ((((_ca_x - _td_x) / _mc) > 20) | ((_ca_x / _mc) > 20)) & (_mc > 0)
    # FINANCIALS EXEMPTION: a bank/insurer/broker legitimately holds cash
    # far above a depressed market cap (Freddie Mac in conservatorship:
    # real cash >20x mcap) — that is balance-sheet reality, not currency
    # corruption. Financials are already excluded from the operating
    # archetypes this band protects.
    if "sector" in m.columns:
        _is_fin_x = m["sector"].fillna("").astype(str).str.lower().str.contains("financ")
        _ccy_bad &= ~_is_fin_x
    _ccy_bad = _ccy_bad.fillna(False)
    for _cc_col in ("net_cash_pct_mcap", "cash_pct_mcap", "ncav_pct_mcap", "cash_pct_ev"):
        if _cc_col in m.columns:
            _ccv_s = pd.to_numeric(m[_cc_col], errors="coerce")
            # component evidence — or the STORED value itself beyond the band
            # (WIMI rule: a provably-impossible stored figure never survives
            # just because its components went missing). cash_pct_ev is
            # exempt from the stored test: a near-zero EV legitimately
            # explodes that ratio, so only component evidence applies there.
            _hit = _ccy_bad & _ccv_s.notna()
            if _cc_col != "cash_pct_ev":
                _hit |= _ccv_s > 20
            m.loc[_hit, _cc_col] = np.nan
            if int(_hit.sum()):
                recon[f"{_cc_col} nulled (cash>20x mcap, ccy-mismatch class)"] = int(_hit.sum())
    _qc_flag(_ccy_bad, "ccy_mismatch_suspect")

    # PENCE-CORRUPT P/B REPAIR (root-caused, repaired — not nulled): on LSE
    # (and other cents-quoted markets: .IL, .JO ZAc, .TA agorot) Yahoo's
    # priceToBook divides a PENCE price by a POUNDS book value — exactly
    # 100x. p_e and p_s are computed consistently (verified: .L medians
    # match world), ONLY priceToBook carries the disease, and it EXCLUDED
    # cheap UK names from every pb-floor gate (Hunting stored 94.8 vs real
    # 0.63; Jupiter 92.4 vs ~0.9). Per-row evidence, never a blanket /100:
    # Yahoo's own NI/ROE gives a pence-immune equity, so pb vs mcap*roe/NI
    # ~100x proves corruption while a GENUINE high-P/B name shows ~1x
    # (Games Workshop stored 21.28 vs independent 21.29 — untouched).
    # Loss-makers (no ROE leg) use the NCAV identity as secondary evidence:
    # /100 must restore equity >= NCAV where stored pb violates it.
    _pb_x = pd.to_numeric(m.get("pb"), errors="coerce")
    _pence_sfx = m.index.to_series().astype(str).str.endswith((".L", ".IL", ".JO", ".TA"))
    _roe_pp = pd.to_numeric(m.get("roe"), errors="coerce")
    _ni_pp = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")
    _eq_ind = (_ni_pp / _roe_pp).where((_roe_pp != 0) & _ni_pp.notna())
    _pb_ind = (_mc / _eq_ind).where(_eq_ind > 0)
    _ratio_pp = _pb_x / _pb_ind
    _ncav_lvl_pp = pd.to_numeric(m.get("ncav"), errors="coerce")
    _pence_hit = _pence_sfx & (
        _ratio_pp.between(50, 200)
        | (_pb_ind.isna() & (_pb_x > 15) & (_ncav_lvl_pp > 0)
           & ((_mc / (_pb_x / 100.0)) >= 0.66 * _ncav_lvl_pp)
           & ((_mc / _pb_x) < 0.66 * _ncav_lvl_pp)))
    _pence_hit = _pence_hit.fillna(False)
    if "pb" in m.columns and int(_pence_hit.sum()):
        m.loc[_pence_hit, "pb"] = _pb_x[_pence_hit] / 100.0
        recon["pb repaired /100 (pence-vs-pounds, evidence-confirmed)"] = int(_pence_hit.sum())
    # DIRECT BOOK-VALUE EVIDENCE (fetched adjudication file): for suspects
    # with neither an NI/ROE discriminator nor an NCAV identity leg, the
    # decisive evidence was fetched from the source itself — Yahoo's
    # defaultKeyStatistics.bookValue is in MAJOR units while price.currency
    # says "GBp"/"ZAc" explicitly, so pb_true = price/100/bookValue with no
    # inference at all (Virgin Wines 0.75, Derwent London 0.59).
    try:
        _bvev = pd.read_csv("audit_reports/pence_bookvalue_evidence.csv"
                            ).drop_duplicates("symbol").set_index("symbol")
        _bv_v = pd.to_numeric(_bvev["bookValue"], errors="coerce").reindex(m.index)
        _px_v = pd.to_numeric(_bvev["price"], errors="coerce").reindex(m.index)
        _cc_v = _bvev["quote_ccy"].astype(str).reindex(m.index)
        _cents = _cc_v.isin(["GBp", "ZAc", "ILA", "GBX"])
        _px_maj = _px_v.where(~_cents, _px_v / 100.0)
        _pb_ev = (_px_maj / _bv_v).where(_bv_v > 0)
        _ev_hit = _pb_ev.notna() & (_pb_x > 15) & ~_pence_hit \
            & ((_pb_x / _pb_ev).between(50, 200))
        if int(_ev_hit.sum()):
            m.loc[_ev_hit, "pb"] = _pb_ev[_ev_hit]
            recon["pb repaired from fetched bookValue evidence"] = int(_ev_hit.sum())
        _pence_hit = _pence_hit | _ev_hit.fillna(False)
    except FileNotFoundError:
        pass
    _qc_pence_mask = _pence_hit

    # P/B FROM PRIMARIES (user directive: construct from the source figures,
    # never approximate where a primary exists). Yahoo's priceToBook is a
    # LAST resort — it divides cents prices by major-unit book on GBp/ZAc/
    # ILA markets and is inconsistent across cross-currency lines. Order:
    #   A. equity LEVEL (audited EDGAR fresh-gated for US filers; build-time
    #      balance sheet elsewhere; restated where cross-ccy)  -> mcap/equity
    #   B. fetched bookValue per share (major units): the adjudication file
    #      today, yf_book_value universally at the next full pull, valid
    #      when the quote and financial currencies agree -> price_maj/bvps
    #   C. Yahoo priceToBook with the per-row evidence guards above.
    # A/B override a stored pb deviating >25% (non-churn tolerance absorbs
    # minority-interest basis differences).
    _eq_pA = pd.to_numeric(m.get("equity"), errors="coerce")
    _pb_primary = (_mc / _eq_pA).where(_eq_pA > 0)
    if "yf_book_value" in y.columns:
        _bvy = pd.to_numeric(y["yf_book_value"], errors="coerce").reindex(m.index)
        _qcy = (y["yf_quote_currency"].astype(str).reindex(m.index)
                if "yf_quote_currency" in y.columns
                else pd.Series("", index=m.index))
        _pxm = _p.where(~_qcy.isin(["GBp", "GBX", "ZAc", "ILA"]), _p / 100.0)
        _pb_bv = (_pxm / _bvy).where(_bvy > 0)
        if "yf_financial_currency" in y.columns:
            _fcy = y["yf_financial_currency"].astype(str).reindex(m.index)
            _qmaj = _qcy.replace({"GBp": "GBP", "GBX": "GBP",
                                  "ZAc": "ZAR", "ILA": "ILS"})
            _pb_bv = _pb_bv.where(_fcy == _qmaj)
        _pb_primary = _pb_primary.combine_first(_pb_bv)
    try:
        _bvev2 = pd.read_csv("audit_reports/pence_bookvalue_evidence.csv"
                             ).drop_duplicates("symbol").set_index("symbol")
        _bv2 = pd.to_numeric(_bvev2["bookValue"], errors="coerce").reindex(m.index)
        _px2 = pd.to_numeric(_bvev2["price"], errors="coerce").reindex(m.index)
        _cc2 = _bvev2["quote_ccy"].astype(str).reindex(m.index)
        _pxm2 = _px2.where(~_cc2.isin(["GBp", "GBX", "ZAc", "ILA"]), _px2 / 100.0)
        _pb_primary = _pb_primary.combine_first((_pxm2 / _bv2).where(_bv2 > 0))
    except FileNotFoundError:
        pass
    if "pb" in m.columns:
        _pb_cur2 = pd.to_numeric(m["pb"], errors="coerce")
        _pb_dev2 = _pb_cur2 / _pb_primary
        _pb_fix2 = _pb_primary.notna() & (
            _pb_cur2.isna() | (_pb_dev2 > 1.25) | (_pb_dev2 < 0.8))
        m.loc[_pb_fix2, "pb"] = _pb_primary[_pb_fix2]
        if int(_pb_fix2.sum()):
            recon["pb constructed from primary book (equity/bookValue)"] = int(_pb_fix2.sum())

    # NCAV VINTAGE RECOMPUTE (root repair): ncav_pct_mcap was computed at
    # build time and never refreshed against the CURRENT mcap (unlike the
    # cash family), so a price move since build fakes an identity violation
    # against fresh pb. Recompute from the stored NCAV level (restated above
    # where cross-currency) over today's mcap.
    if "ncav_pct_mcap" in m.columns and "ncav" in m.columns:
        _ncv_lvl2 = pd.to_numeric(m["ncav"], errors="coerce")
        _recompute("ncav_pct_mcap", (_ncv_lvl2 / _mc).where(_mc > 0), band=(-50, 50))

    # NCAV-VS-EQUITY IDENTITY: NCAV can never exceed total equity (equity
    # adds non-current assets on top). After the pence repair, the
    # cross-currency restatement and the vintage recompute above, a
    # surviving violation is a contradiction we cannot yet adjudicate —
    # FLAGGED (identifiable, kept), never silently consumed and never
    # nulled without understanding.
    _pb_x2 = pd.to_numeric(m.get("pb"), errors="coerce")
    _ncv_x2 = pd.to_numeric(m.get("ncav_pct_mcap"), errors="coerce")
    _eq_x2 = (1.0 / _pb_x2).where(_pb_x2 > 0)
    _ncv_contra = ((_ncv_x2 > 1.5 * _eq_x2) & (_ncv_x2 > 0) & _eq_x2.notna()).fillna(False)
    if int(_ncv_contra.sum()):
        recon["ncav_gt_equity flagged (unresolved contradiction, kept)"] = int(_ncv_contra.sum())
    _qc_flag(_ncv_contra, "ncav_gt_equity")
    _qc_flag(_qc_pence_mask, "pence_pb_repaired")
    _qc_flag(_restated_mask, "ccy_restated")

    # CASH-CONVERSION BASE-EFFECT BAND: CFO/EBITDA beyond ±50x is a near-zero
    # EBITDA denominator artifact, not information (same disease as the NPI
    # base effects). Consumers read its SIGN — an artifact magnitude may not
    # carry one.
    if "cash_conversion" in m.columns:
        _ccv = pd.to_numeric(m["cash_conversion"], errors="coerce")
        _ccv_bad = _ccv.abs() > 50
        m.loc[_ccv_bad.fillna(False), "cash_conversion"] = np.nan
        if int(_ccv_bad.fillna(False).sum()):
            recon["cash_conversion nulled (|CFO/EBITDA|>50 base effect)"] = int(_ccv_bad.fillna(False).sum())

    # op_margin above 100% of revenue is impossible for an OPERATING margin.
    if "op_margin" in m.columns:
        _opm_x = pd.to_numeric(m["op_margin"], errors="coerce")
        _opm_bad = _opm_x > 1.0
        m.loc[_opm_bad.fillna(False), "op_margin"] = np.nan
        if int(_opm_bad.fillna(False).sum()):
            recon["op_margin nulled (>100%, impossible)"] = int(_opm_bad.fillna(False).sum())

    # owner_earnings_yield = TRUE Buffett owner earnings (NI + D&A − capex)
    # over mcap — REBUILT WHOLESALE each run, HERE, after every margin
    # sanitation (its implied D&A uses op_margin; building it earlier left
    # values the final components could not reproduce — the KTTA class).
    # The column historically held fcf/mcap under this name: one measure
    # living under two names silently double-counted the FCF lens in every
    # downstream OR-leg and in robust_cash_yield, so no aliased relic may
    # survive. D&A is implied EBITDA − EBIT within the same row (the
    # construction the forensic archetypes use); capex is the PRIMARY column
    # only. Rows missing a component leave the field honestly absent.
    # Levered measure → mcap denominator; ±100% impossibility band.
    _ebd_oe = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
    _opm_oe = pd.to_numeric(m.get("op_margin"), errors="coerce")
    _rev_oe = pd.to_numeric(m.get("revenue_ttm"), errors="coerce")
    _cx_oe = pd.to_numeric(m.get("capex_ttm"), errors="coerce")
    _ni_oe = pd.to_numeric(m.get("net_income_ttm"), errors="coerce")
    _dna_oe = (_ebd_oe - _opm_oe * _rev_oe).where(lambda s: s >= 0)
    _oe_lvl = (_ni_oe + _dna_oe - _cx_oe).where(_cx_oe >= 0)
    _oe_yield = (_oe_lvl / _mc).where(_mc > 0)
    _oe_yield = _oe_yield.where(_oe_yield.abs() <= 1.0)
    if "owner_earnings_yield" in m.columns:
        _oe_old = pd.to_numeric(m["owner_earnings_yield"], errors="coerce")
        recon["owner_earnings_yield rebuilt as true OE (was fcf alias)"] = int(
            (_oe_old.notna() | _oe_yield.notna()).sum())
    m["owner_earnings_yield"] = _oe_yield

    # ---- STORED-VALUE BAND ENFORCEMENT (the WIMI rule, generalized) ----
    # _recompute's bands reject bad FRESH values, but a stored value beyond
    # the band survived whenever its components went missing — cfo_yield
    # carried 1e8, net_cash_pct_mcap -1.6e6, ebitda_margin -34,000. A value
    # outside its own construction's band is arithmetic noise (near-zero
    # denominators, unit corruption), not information: there is no true
    # value to repair TO, so it is nulled with the band documented here.
    _STORED_BANDS = {
        "cfo_yield": (-50, 50), "earnings_yield": (-50, 50),
        "robust_cash_yield": (-50, 50), "ufcf_yield": (-50, 50),
        "cash_return_ev": (-50, 50), "fcf_conversion": (-50, 50),
        "net_cash_pct_mcap": (-50, 50), "cash_pct_mcap": (-50, 50),
        "ncav_pct_mcap": (-50, 50),
        # years-to-repay net debt from FCF: beyond 200 the figure is a
        # near-zero-FCF artifact, not a leverage measure
        "net_debt_to_fcf": (-100, 200),
        "fcf_eta_quarters": (0, 40),   # a 10-year "runway to positive" is noise
        "ebitda_margin": (-5, 5), "op_margin": (-5, 5),
        "net_margin": (-5, 5), "gross_margin": (-1.5, 1.5),
        "pretax_margin": (-5, 5),
        "sbc_pct_revenue": (0, 100),
        "analyst_target_upside_pct": (-1, 20),
        "yf_institution_pct": (0, 1.2),
        # goodwill+intangibles are a SUBSET of total assets — above 1 is an
        # accounting impossibility, not a tail
        "goodwill_intangibles_pct_assets": (0, 1.05),
    }
    # build-time growth family: beyond +/-1000% a yoy/delta is a base-effect
    # artifact (near-zero prior), the same class the NPI guard drops — the
    # true growth off a ~zero base is undefined, so nothing exists to
    # repair to. Sign-consumers are unaffected in-band.
    for _gcol2 in ("rev_yoy", "ebitda_yoy", "cfo_yoy", "fcf_yoy",
                   "gross_profit_yoy", "ebit_growth_yoy", "fcf_per_share_yoy",
                   "ebitda_margin_delta_yoy", "op_margin_delta_yoy",
                   "gross_margin_delta_yoy", "fcf_margin_delta_yoy",
                   "roce_delta_yoy", "ev_sales_change_yoy",
                   "incremental_ebitda_margin", "fcf_margin"):
        _STORED_BANDS[_gcol2] = (-10, 10)
    _STORED_BANDS["operating_leverage_ratio"] = (-100, 100)
    for _bc2, (_blo2, _bhi2) in _STORED_BANDS.items():
        if _bc2 in m.columns:
            _bv3 = pd.to_numeric(m[_bc2], errors="coerce")
            _bad3 = ((_bv3 < _blo2) | (_bv3 > _bhi2)).fillna(False)
            if int(_bad3.sum()):
                m.loc[_bad3, _bc2] = np.nan
                recon[f"{_bc2} nulled (outside stored band {_blo2},{_bhi2})"] = int(_bad3.sum())
    # EV-MULTIPLE SELF-CONSISTENCY (HOLO class — the WIMI rule for
    # multiples): a stored EV multiple must agree with the row's OWN stored
    # EV over its own denominator; when the band-reject left a stale
    # multiple standing beside components that prove a different one
    # (HOLO: stored -209 vs -6,233 from its own EV/EBITDA), the stored
    # value is unfounded and is nulled.
    _ev_sc = pd.to_numeric(m.get("enterprise_value"), errors="coerce")
    for _mc_col, _dn_s in (("ev_ebitda", pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")),
                           ("ev_sales", pd.to_numeric(m.get("revenue_ttm"), errors="coerce"))):
        if _mc_col in m.columns:
            _st_v = pd.to_numeric(m[_mc_col], errors="coerce")
            _im_v = (_ev_sc / _dn_s).where(_dn_s > 0)
            _inc = _st_v.notna() & _im_v.notna() & (
                ((_st_v / _im_v) - 1).abs() > 0.5)
            m.loc[_inc.fillna(False), _mc_col] = np.nan
            if int(_inc.fillna(False).sum()):
                recon[f"{_mc_col} nulled (inconsistent with own EV/denominator)"] = int(_inc.fillna(False).sum())

    # price_yoy absolute fallback where the 52w-range evidence is missing:
    # a +10,000%+ print with no range corroboration is a redenomination
    # artifact; the derived price_minus_* differentials inherit the null.
    for _pyc2 in ("price_yoy", "momentum_12m"):
        if _pyc2 in m.columns:
            _pv2 = pd.to_numeric(m[_pyc2], errors="coerce")
            _pbad2 = (_pv2 > 100).fillna(False)
            m.loc[_pbad2, _pyc2] = np.nan
            if int(_pbad2.sum()):
                recon[f"{_pyc2} nulled (>10000%, no evidence)"] = int(_pbad2.sum())
    if "price_yoy" in m.columns:
        _pyN = pd.to_numeric(m["price_yoy"], errors="coerce")
        for _dcp in ("price_minus_rev_yoy", "price_minus_ebitda_yoy",
                     "price_minus_fcf_yoy"):
            if _dcp in m.columns:
                _dv3 = pd.to_numeric(m[_dcp], errors="coerce")
                _dbad = (_pyN.isna() & _dv3.notna()) | (_dv3.abs() > 20)
                m.loc[_dbad.fillna(False), _dcp] = np.nan
                if int(_dbad.fillna(False).sum()):
                    recon[f"{_dcp} nulled (inherits price_yoy evidence)"] = int(_dbad.fillna(False).sum())

    # NO-ANCHOR MIXED-CCY GROUPS (detected in the restatement pass): siblings
    # share identical raw levels across different quote currencies with no
    # home line to anchor the financial currency (New China Life NWWCF/NCL.F)
    # — every quote-vs-level ratio is unverifiable-and-likely-corrupt, and the
    # moderate cases (p_s 0.24 from CNY-over-USD) sit INSIDE every band.
    # Nulled HERE, after all recomputes, or they would be refilled from the
    # raw levels. Repairable once yf_financial_currency lands with the next
    # full fetch.
    if int(_noanchor_mask.sum()):
        for _rc2 in ("p_s", "p_e", "pb", "ev_sales", "ev_ebitda", "ev_ebit",
                     "fcf_yield", "cfo_yield", "earnings_yield",
                     "owner_earnings_yield", "robust_cash_yield",
                     "net_cash_pct_mcap", "cash_pct_mcap", "ncav_pct_mcap",
                     "cash_pct_ev", "not_priced_in_score"):
            if _rc2 in m.columns:
                m.loc[_noanchor_mask, _rc2] = np.nan
        recon["no-anchor mixed-ccy group: quote-vs-level ratios nulled"] = int(_noanchor_mask.sum())
        _qc_flag(_noanchor_mask, "ccy_mismatch_suspect")

    # NORMALIZED-PAIR ORDERING: normalized_ebit (5yr avg EBIT) can only exceed
    # normalized_ebitda (5yr avg EBITDA) through negative D&A — impossible in
    # any filing — so an inverted pair means the two averages were taken over
    # DIFFERENT year sets or inconsistent source rows (yartseva_db now aligns
    # them at build; this heals rows built before the fix). The EBIT average
    # is the dangerous one (an inflated denominator understates EV/normEBIT,
    # faking cheapness) — null it; the EBITDA average stands on its own years.
    if "normalized_ebit" in m.columns and "normalized_ebitda" in m.columns:
        _nbe = pd.to_numeric(m["normalized_ebit"], errors="coerce")
        _nbd = pd.to_numeric(m["normalized_ebitda"], errors="coerce")
        _inv = _nbe.notna() & _nbd.notna() & (_nbe > _nbd)
        m.loc[_inv, "normalized_ebit"] = np.nan
        if int(_inv.sum()):
            recon["normalized_ebit nulled (exceeds normalized_ebitda)"] = int(_inv.sum())

    # NOT-PRICED-IN REPAIR: the score is a mean of (growth − price-return)
    # differentials; a growth rate off a near-zero prior year (ANSC's fcf_yoy
    # of 3.29e6 — a SPAC's first real cash year) is an arithmetic artifact
    # that flooded the mean and auto-passed every (not_priced_in > 0.20) gate
    # leg. ROOT-CAUSE VERIFIED per name, and REPAIRED, not nulled: recompute
    # from the stored yoy components with the same guards yartseva_db now
    # applies at build (drop any component whose input moved >1000% — base
    # effect, not information; clip kept differentials to ±300pp). Rows out
    # of band or missing get the guarded recomputation; only rows with NO
    # sane component left stay honestly absent (e.g. 1841.T, whose price_yoy
    # of +14,413,000% is its own corruption, tracked separately).
    if "not_priced_in_score" in m.columns:
        _npi = pd.to_numeric(m["not_priced_in_score"], errors="coerce")
        _rev_np = pd.to_numeric(m.get("rev_yoy"), errors="coerce")
        _ebd_np = pd.to_numeric(m.get("ebitda_yoy"), errors="coerce")
        _fcf_np = pd.to_numeric(m.get("fcf_yoy"), errors="coerce")
        _px_np = pd.to_numeric(m.get("price_yoy"), errors="coerce")
        _px_ok = _px_np.where(_px_np.abs() <= 10.0)
        _comps = pd.concat(
            [(gr.where(gr.abs() <= 10.0) - _px_ok).clip(-3.0, 3.0)
             for gr in (_rev_np, _ebd_np, _fcf_np)], axis=1)
        _npi_new = _comps.mean(axis=1, skipna=True)
        _npi_bad = _npi.notna() & (_npi.abs() > 3.0)
        # repair out-of-band rows AND refill rows previously nulled (or
        # never built) where the guarded components support a score.
        _fix = (_npi_bad | _npi.isna()) & _npi_new.notna()
        m.loc[_fix, "not_priced_in_score"] = _npi_new[_fix]
        _dead = _npi_bad & _npi_new.isna()
        m.loc[_dead, "not_priced_in_score"] = np.nan
        if int(_fix.sum()) or int(_dead.sum()):
            recon["not_priced_in_score repaired/refilled from guarded components"] = int(_fix.sum())
            recon["not_priced_in_score nulled (no sane component)"] = int(_dead.sum())

    # remaining identifiability flags: anomalies that are KEPT (legitimate
    # accounting can produce them) but must never be silent.
    _fcf3 = pd.to_numeric(m.get("fcf_ttm"), errors="coerce")
    _cfo3 = pd.to_numeric(m.get("cfo_ttm"), errors="coerce")
    _cx3 = pd.to_numeric(m.get("capex_ttm"), errors="coerce")
    _qc_flag((_cfo3 > 0) & (_fcf3 > _cfo3 * 1.05), "fcf_gt_cfo")
    # independent primaries (statement FCF vs CFO/capex) may straddle
    # reporting windows — a >40% divergence between fcf and cfo-capex is
    # KEPT (never identity-derived away, by directive) but must be
    # identifiable (deep-trace round 9: SKUYF sign-flip class).
    _fc_id3 = _cfo3 - _cx3
    _wmm = (_fcf3.notna() & _fc_id3.notna() & (_fc_id3 != 0)
            & (((_fcf3 / _fc_id3) - 1).abs() > 0.40))
    _qc_flag(_wmm, "fcf_window_mismatch")
    _td3 = pd.to_numeric(m.get("total_debt"), errors="coerce")
    _ca3 = pd.to_numeric(m.get("cash"), errors="coerce")
    # gap measured on BOTH bases: relative to mcap (equity materiality) and
    # relative to |EV| (every EV multiple is distorted by exactly that
    # fraction) — a net-cash name with tiny EV escaped the mcap basis while
    # its multiples were 48% off components (088910.KQ class, spot-check
    # round 9). Near-zero EV uses a 5%-of-mcap floor so the ratio basis
    # cannot explode.
    _gap_abs3 = (_ev_now - (_mc + _td3 - _ca3)).abs()
    _gap3 = (_gap_abs3 / _mc).where(_mc > 0)
    _gap_ev3 = _gap_abs3 / np.maximum(_ev_now.abs(), 0.05 * _mc)
    _qc_flag((_gap3 > 0.25) | (_gap_ev3 > 0.25), "ev_comp_gap")
    _rvu3 = pd.to_numeric(m.get("revenue_ttm_usd"), errors="coerce")
    _rv3 = pd.to_numeric(m.get("revenue_ttm"), errors="coerce")
    _ebu3 = pd.to_numeric(m.get("ebitda_ttm_usd"), errors="coerce")
    _eb3 = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce")
    _fx1 = (_rvu3 / _rv3).where(_rv3 != 0)
    _fx2 = (_ebu3 / _eb3).where(_eb3 != 0)
    _fx_bad = (_fx1 > 0) & (_fx2 > 0) & ((_fx1 / _fx2 > 1.10) | (_fx2 / _fx1 > 1.10))
    _qc_flag(_fx_bad, "fx_twin_dev")
    # (concepts review) Yahoo's EV = mcap + debt - cash omits preferred and
    # NCI; where those audited claims are MATERIAL (>5% of |EV|) the EV
    # multiples run light — identifiable, never silent.
    _nci_q = (pd.to_numeric(m["minority_interest"], errors="coerce").fillna(0)
              if "minority_interest" in m.columns
              else pd.Series(0.0, index=m.index))
    _prf_q = (pd.to_numeric(m["preferred_equity"], errors="coerce").fillna(0)
              if "preferred_equity" in m.columns
              else pd.Series(0.0, index=m.index))
    _sen_q = _nci_q + _prf_q
    _qc_flag((_sen_q > 0.05 * _ev_now.abs()) & (_sen_q > 0) & _ev_now.notna(),
             "ev_ex_senior_claims")
    m["qc_flags"] = m["qc_flags"].str.lstrip("|")

    # REPAIR-MAGNITUDE DRIFT DETECTOR: our own manipulations are watched. A
    # column whose repair count JUMPS vs the committed baseline (>3x + 100)
    # signals creep in the machinery itself — shout, never silently absorb.
    try:
        import json as _json
        _bl_path = "audit_reports/reconcile_baseline.json"
        try:
            _bl = _json.load(open(_bl_path))
        except Exception:
            _bl = {}
        _alerts = []
        for _c, _k in recon.items():
            _b = _bl.get(_c)
            if _b is not None and _k > 3 * _b + 100:
                _alerts.append(f"{_c}: {_k} vs baseline {_b}")
        if _alerts:
            print("\n!! REPAIR-DRIFT ALERT (counts far above baseline — check "
                  "the machinery before trusting this run):", file=sys.stderr)
            for _a in _alerts:
                print(f"   {_a}", file=sys.stderr)
        _json.dump({**_bl, **{k: int(v) for k, v in recon.items()}},
                   open(_bl_path, "w"), indent=1)
    except Exception as _e:
        print(f"  (drift detector failed: {_e})", file=sys.stderr)

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
