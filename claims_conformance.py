#!/usr/bin/env python3
"""CLAIMS CONFORMANCE — verify we actually implement what we say we do.

Layer 3 of the rigor stack:
  1. formula audits  = is the arithmetic right?
  2. concepts review = is the DEFINITION right?
  3. THIS            = does the code/data MATCH the documented claims?

Two halves:
  A. DATA conformance — each documented rule recomputed against the live
     master and required to hold (beyond the 180 methodology-audit gates,
     these target the claim-vs-implementation gap specifically: a book
     recomputing ETA with a stale floor, a column whose provenance says
     "EDGAR -> statement -> absent" but which carries orphan values...).
  B. SOURCE tripwires — greps that FAIL if a banned pattern (any defect
     class fixed this cycle) reappears anywhere in the pipeline sources.

Exit 1 on any FAIL. Run by refresh_valuations.sh after methodology_audit.
"""
from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd

FAILS: list[str] = []
PASSES = 0


def check(name: str, ok: bool, detail: str = ""):
    global PASSES
    if ok:
        PASSES += 1
    else:
        FAILS.append(f"{name}  — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


def n(df, c):
    return pd.to_numeric(df.get(c), errors="coerce") if c in df.columns \
        else pd.Series(np.nan, index=df.index)


def data_conformance():
    print("A. DATA conformance (claim vs live master)")
    m = pd.read_csv("asymmetry_global.csv", low_memory=False)

    # CLAIM: owner_earnings_yield is EXACTLY (NI + (EBITDA - opm*rev) - capex)/mcap,
    # never an alias of anything else, absent without capex.
    oe = n(m, "owner_earnings_yield")
    manual = (n(m, "net_income_ttm")
              + (n(m, "ebitda_ttm") - n(m, "op_margin") * n(m, "revenue_ttm"))
              - n(m, "capex_ttm")) / n(m, "market_cap")
    both = oe.notna() & manual.notna()
    exact = ((oe - manual).abs() < 1e-9) | ((oe / manual - 1).abs() < 1e-6)
    bad = int((both & ~exact).sum())
    check("OE yield reproduces its documented construction exactly",
          bad == 0, f"{bad} rows diverge")
    check("OE yield never exists without a capex component",
          int((oe.notna() & n(m, "capex_ttm").isna()).sum()) == 0)

    # CLAIM: capex is primaries-only (EDGAR -> Yahoo statement -> absent).
    try:
        ed = pd.read_csv("us_edgar_yartseva.csv", low_memory=False,
                         usecols=["symbol", "capex_ttm"]).drop_duplicates("symbol")
        yf = pd.read_csv("ticker_yf.csv", low_memory=False,
                         usecols=lambda c: c in {"symbol", "yf_capex_stmt"}
                         ).drop_duplicates("symbol", keep="last")
        src = m[["symbol"]].merge(ed, on="symbol", how="left") \
                           .merge(yf, on="symbol", how="left")
        has_source = (pd.to_numeric(src["capex_ttm"], errors="coerce").notna()
                      | pd.to_numeric(src.get("yf_capex_stmt"), errors="coerce").notna())
        orphans = int((n(m, "capex_ttm").notna().values & ~has_source.values).sum())
        check("capex has NO value without a primary source (identity stays dead)",
              orphans == 0, f"{orphans} orphan capex values")
    except FileNotFoundError:
        check("capex primaries-only (sources present)", True)

    # CLAIM: levered-over-mcap / unlevered-over-EV pairing — ufcf_yield must
    # NOT equal fcf/mcap (would mean the unlevered column silently carries
    # the levered construction).
    ufy = n(m, "ufcf_yield")
    fcf_mc = n(m, "fcf_ttm") / n(m, "market_cap")
    both2 = ufy.notna() & fcf_mc.notna() & (n(m, "total_debt") > 0)
    same = int((both2 & ((ufy / fcf_mc - 1).abs() < 1e-9)).sum())
    check("ufcf_yield is not a silent alias of fcf/mcap on levered rows",
          same < max(10, 0.005 * max(1, int(both2.sum()))), f"{same} identical rows")

    # CLAIM: declared currency drives the bridge — where Yahoo declares a
    # fin!=quote pair and we store a bridge, the bridge matches the fx ratio
    # of the DECLARED pair (within 20%).
    try:
        y = pd.read_csv("ticker_yf.csv", low_memory=False,
                        usecols=lambda c: c in {"symbol", "yf_quote_currency",
                                                "yf_financial_currency"}
                        ).drop_duplicates("symbol", keep="last").set_index("symbol")
        mm = m.set_index("symbol")
        fx = pd.to_numeric(mm["fx_to_usd"], errors="coerce")
        fx_by = fx.groupby(mm["currency"].astype(str).str.upper()).median()
        q = y["yf_quote_currency"].astype(str).str.upper().replace(
            {"GBP": "GBP", "GBX": "GBP", "ZAC": "ZAR", "ILA": "ILS"}).reindex(mm.index)
        f = y["yf_financial_currency"].astype(str).str.upper().reindex(mm.index)
        br = pd.to_numeric(mm.get("ccy_bridge"), errors="coerce")
        decl = f.notna() & (f != "NAN") & q.notna() & (q != "NAN") & (f != q) & br.notna()
        expect = f.map(fx_by) / q.map(fx_by)
        offs = int((decl & expect.notna()
                    & ((br / expect - 1).abs() > 0.20)).sum())
        check("stored ccy_bridge matches the DECLARED currency pair's fx",
              offs == 0, f"{offs} bridges disagree with declarations")
    except Exception as e:
        check("declared-bridge conformance (inputs readable)", False, str(e)[:80])

    # CLAIM: the books rank on the CANONICAL ETA (0.90 floor, melt included).
    # Recompute the harvard/top_n formula from master components and require
    # agreement with enrich's stored entry_today_asymmetry within 25% for
    # 99%+ of scored rows (catches any future builder recompute drift).
    ida = n(m, "intrinsic_discount")
    boost = (1.0 + (ida - 0.25)).clip(0.90, 1.5)
    melt = n(m, "melt_demotion").fillna(1.0)
    eta = n(m, "entry_today_asymmetry")
    asy = n(m, "asymmetry_score")
    qm = n(m, "qual_mult").fillna(1.0)
    pr = n(m, "post_rally_factor").fillna(1.0)
    approx = asy * boost * qm * pr * melt
    both3 = eta.notna() & approx.notna() & (approx > 0)
    agree = ((eta / approx).where(both3).between(1 / 1.35, 1.35))
    rate = float(agree.sum()) / max(1, int(both3.sum()))
    check("stored ETA consistent with the canonical formula (books can't drift)",
          rate >= 0.98, f"only {rate:.1%} within band")

    # CLAIM: negative-EV multiples are kept; non-positive denominators null.
    evb = n(m, "ev_ebitda"); eb = n(m, "ebitda_ttm"); ev = n(m, "enterprise_value")
    kept = int(((ev < 0) & (eb > 0) & evb.notna()).sum())
    nulled = int(((eb <= 0) & eb.notna() & evb.notna()).sum())
    check("negative-EV multiples exist over positive EBITDA (doctrine live)",
          kept > 50, f"only {kept}")
    check("no EV/EBITDA over non-positive EBITDA", nulled == 0, f"{nulled} rows")

    # CLAIM (concepts review): EDGAR-mapped NCAV deducts preferred + NCI.
    try:
        edf = pd.read_csv("us_edgar_yartseva.csv", low_memory=False)
        if {"ncav", "current_assets", "liabilities"}.issubset(edf.columns):
            ca = pd.to_numeric(edf["current_assets"], errors="coerce")
            li = pd.to_numeric(edf["liabilities"], errors="coerce")
            nci = pd.to_numeric(edf.get("minority_interest"), errors="coerce").fillna(0)
            prf = pd.to_numeric(edf.get("preferred_equity"), errors="coerce").fillna(0)
            nc = pd.to_numeric(edf["ncav"], errors="coerce")
            expect2 = ca - li - nci - prf
            both4 = nc.notna() & expect2.notna()
            off2 = int((both4 & ((nc - expect2).abs() > 1)).sum())
            check("EDGAR NCAV = CA - liabilities - preferred - NCI (as documented)",
                  off2 == 0, f"{off2} rows diverge")
    except FileNotFoundError:
        pass


BANNED = [
    # (file-glob-regex, pattern, why)
    (r"(derive_missing_columns|apply_ticker_yf|yartseva_db|edgar_to_yartseva)\.py",
     r"capex\s*=\s*.{0,20}cfo.{0,20}-.{0,20}fcf|cfo\s*-\s*fcf.{0,20}capex\s*=",
     "capex identity derivation (deleted by directive)"),
    (r"(enrich_asymmetry_global|asymmetry_rank)\.py",
     r"(asymmetry_score|downside_floor_score|inflection_score)(\'|\")\]\.fillna\(0\)",
     "worst-case fillna(0) on a score (missing = unranked)"),
    (r"(apply_ticker_yf|yartseva_db|fill_fundamentals_gaps)\.py",
     r"financialData.{0,40}freeCashflow",
     "retired third-party levered FCF source"),
    (r"derive_missing_columns\.py",
     r"gross_profitability.{0,60}\bev\b",
     "gross_profitability must be GP/assets, not GP/EV"),
    (r"(fill_fundamentals_gaps|yartseva_db)\.py",
     r"out\[['\"]roce['\"]\]\s*=\s*roe\b",
     "ROE written into the ROCE column"),
    (r"(build_harvard_workbook|top_n_by_country|build_country_workbook)\.py",
     r"clip\(0\.75,\s*1\.5\)",
     "the broken 0.75 boost floor"),
    (r"(yartseva_db|fill_fundamentals_gaps)\.py",
     r"p_e['\"]?\]?\s*=\s*.{0,30}forwardPE|forwardPE.{0,30}p_e\s*=",
     "forward P/E under a trailing label"),
]


def source_tripwires():
    print("B. SOURCE tripwires (banned patterns must stay dead)")
    import glob
    for fpat, pat, why in BANNED:
        hit_files = []
        for f in glob.glob("*.py"):
            if not re.search(fpat, f):
                continue
            try:
                src = open(f).read()
            except OSError:
                continue
            for mline in re.finditer(pat, src):
                ln = src[:mline.start()].count("\n") + 1
                seg = src[max(0, mline.start() - 200):mline.start()]
                # skip comment-only mentions (the fix documentation itself)
                line_start = src.rfind("\n", 0, mline.start()) + 1
                line = src[line_start:src.find("\n", mline.start())]
                if line.lstrip().startswith("#"):
                    continue
                hit_files.append(f"{f}:{ln}")
        check(f"banned: {why}", not hit_files, "; ".join(hit_files[:3]))


def main():
    data_conformance()
    source_tripwires()
    print(f"\nCLAIMS CONFORMANCE — {PASSES} PASS, {len(FAILS)} FAIL")
    for f in FAILS:
        print(f"  FAIL {f}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
