#!/usr/bin/env python3
"""Cross-reference the TOP-N book names' financial figures and ratios against
source (ticker_yf.csv = Yahoo quoteSummary) and against the row's own
components. The per-name, human-readable companion to the aggregate
"Valuation internal consistency" gate in methodology_audit.py.

For each of the top N by entry_today_asymmetry it verifies:
  INTERNAL IDENTITIES (the row must agree with itself):
    mcap  = price x shares          (10%)
    ev_ebitda = EV / ebitda_ttm     (25%, EV>0, ebitda>0)
    ev_sales  = EV / revenue_ttm    (25%, EV>0)
    p_e   = mcap / net_income       (25%, NI>0)
    fcf_yield = fcf_ttm / mcap      (25%)
    ebitda_margin = ebitda / revenue(25%)
    EV vs mcap + debt - cash        (40% — minority interest/prefs allowed)
  SOURCE AGREEMENT (where the name has a ticker_yf row):
    price / market_cap / enterprise_value match Yahoo exactly-ish (2%)
    ebitda_ttm / revenue_ttm within 1.4x of Yahoo's level (the reconcile
    tolerance — inside it the master may deliberately keep EDGAR precision)

Writes audit_reports/valuation_crosscheck_top{N}.md and exits 1 if any name
has an ERROR-severity finding, so drivers can gate on it.

Usage: python3 valuation_crosscheck.py [--top 60]
"""
from __future__ import annotations
import argparse, os, sys
import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--master", default="asymmetry_global.csv")
    ap.add_argument("--yf", default="ticker_yf.csv")
    args = ap.parse_args()

    g = pd.read_csv(args.master, low_memory=False)
    try:
        y = pd.read_csv(args.yf, low_memory=False).drop_duplicates(
            "symbol", keep="last").set_index("symbol")
    except FileNotFoundError:
        y = pd.DataFrame()

    g["_eta"] = pd.to_numeric(g.get("entry_today_asymmetry"), errors="coerce")
    top = g.sort_values("_eta", ascending=False).head(args.top)

    def num(row, c):
        try:
            v = float(row.get(c))
            return v if np.isfinite(v) else np.nan
        except (TypeError, ValueError):
            return np.nan

    def dev(a, b):
        if not (np.isfinite(a) and np.isfinite(b)) or b == 0:
            return np.nan
        return abs(a / b - 1)

    rows_out, n_err, n_warn = [], 0, 0
    for _, r in top.iterrows():
        sym = r["symbol"]
        price, sh, mc = num(r, "price"), num(r, "shares_outstanding"), num(r, "market_cap")
        ev, td, ca = num(r, "enterprise_value"), num(r, "total_debt"), num(r, "cash")
        eb, rv, ni = num(r, "ebitda_ttm"), num(r, "revenue_ttm"), num(r, "net_income_ttm")
        fcf = num(r, "fcf_ttm")
        evb, evs, pe = num(r, "ev_ebitda"), num(r, "ev_sales"), num(r, "p_e")
        fy, ebm = num(r, "fcf_yield"), num(r, "ebitda_margin")
        issues = []

        def flag(sev, msg):
            issues.append((sev, msg))

        # --- internal identities
        d = dev(mc, price * sh) if np.isfinite(price) and np.isfinite(sh) else np.nan
        if np.isfinite(d) and d > 0.10:
            flag("ERROR", f"mcap {mc:.3g} != price*shares {price*sh:.3g} (dev {d:.0%})")
        if np.isfinite(ev) and ev > 0 and np.isfinite(eb) and eb > 0 and np.isfinite(evb):
            d = dev(evb, ev / eb)
            if d > 0.25:
                flag("ERROR", f"ev_ebitda {evb:.2f} != EV/ebitda {ev/eb:.2f} (dev {d:.0%})")
        if np.isfinite(ev) and ev > 0 and np.isfinite(rv) and rv > 0 and np.isfinite(evs):
            d = dev(evs, ev / rv)
            if d > 0.25:
                flag("ERROR", f"ev_sales {evs:.2f} != EV/revenue {ev/rv:.2f} (dev {d:.0%})")
        if np.isfinite(ni) and ni > 0 and np.isfinite(pe) and pe > 0 and np.isfinite(mc):
            d = dev(pe, mc / ni)
            if d > 0.25:
                flag("ERROR", f"p_e {pe:.2f} != mcap/NI {mc/ni:.2f} (dev {d:.0%})")
        if np.isfinite(fy) and np.isfinite(fcf) and np.isfinite(mc) and mc > 0:
            d = dev(fy, fcf / mc)
            if d > 0.25:
                flag("ERROR", f"fcf_yield {fy:.3f} != fcf/mcap {fcf/mc:.3f} (dev {d:.0%})")
        if np.isfinite(ebm) and np.isfinite(eb) and np.isfinite(rv) and rv > 0:
            d = dev(ebm, eb / rv)
            if d > 0.25:
                flag("ERROR", f"ebitda_margin {ebm:.3f} != ebitda/rev {eb/rv:.3f} (dev {d:.0%})")
        # EV-composition gap measured vs MCAP, not vs EV (a near-zero-EV
        # net-cash name explodes any %-of-EV metric on a tiny absolute gap).
        # A gap here is usually the CASH-BASIS difference: master `cash` is
        # the broader cash+investments measure (deliberate — Japanese/HK
        # net-nets hold securities), while Yahoo's EV nets only totalCash.
        if all(np.isfinite(x) for x in (ev, mc, td, ca)) and mc > 0:
            gap = abs(ev - (mc + td - ca)) / mc
            if gap > 0.25:
                flag("WARN", f"EV {ev:.3g} vs mcap+debt-cash {mc+td-ca:.3g} "
                             f"(gap {gap:.0%} of mcap — likely broad-cash/"
                             f"investments basis vs Yahoo totalCash)")

        # --- source agreement (Yahoo)
        if len(y) and sym in y.index:
            yr = y.loc[sym]
            for yc, mv, name, tol in (("yf_price", price, "price", 0.02),
                                      ("yf_market_cap", mc, "market_cap", 0.02),
                                      ("yf_enterprise_value", ev, "enterprise_value", 0.02)):
                yv = pd.to_numeric(pd.Series([yr.get(yc)]), errors="coerce").iloc[0]
                d = dev(mv, yv)
                if np.isfinite(d) and d > tol:
                    flag("ERROR", f"{name} {mv:.4g} != Yahoo {yv:.4g} (dev {d:.0%})")
            for yc, mv, name in (("yf_ebitda", eb, "ebitda_ttm"),
                                 ("yf_revenue", rv, "revenue_ttm")):
                yv = pd.to_numeric(pd.Series([yr.get(yc)]), errors="coerce").iloc[0]
                if np.isfinite(yv) and yv != 0 and np.isfinite(mv) and mv != 0:
                    ratio = mv / yv
                    if ratio > 1.4 or ratio < 1 / 1.4:
                        flag("ERROR", f"{name} {mv:.3g} vs Yahoo {yv:.3g} "
                                      f"(outside reconcile tolerance)")
            src_tag = "yahoo"
        else:
            src_tag = "snapshot-only"

        sev = ("ERROR" if any(s == "ERROR" for s, _ in issues)
               else "WARN" if issues else "OK")
        n_err += sev == "ERROR"
        n_warn += sev == "WARN"
        rows_out.append((sym, str(r.get("src", "")), src_tag, sev, issues))

    os.makedirs("audit_reports", exist_ok=True)
    out = f"audit_reports/valuation_crosscheck_top{args.top}.md"
    with open(out, "w") as fh:
        fh.write(f"# Valuation cross-check — top {args.top} by ETA\n\n"
                 f"Master: {args.master} | Source: {args.yf}\n\n"
                 f"**{n_err} ERROR, {n_warn} WARN, "
                 f"{len(rows_out)-n_err-n_warn} clean.**\n\n")
        for sym, src, tag, sev, issues in rows_out:
            if not issues:
                continue
            fh.write(f"## {sym} ({src}, {tag}) — {sev}\n")
            for s, msg in issues:
                fh.write(f"- {s}: {msg}\n")
            fh.write("\n")
        fh.write("\n## Clean names\n" + ", ".join(
            s for s, _, _, sev, i in rows_out if not i) + "\n")
    print(f"top {args.top}: {n_err} ERROR, {n_warn} WARN, "
          f"{len(rows_out)-n_err-n_warn} clean -> {out}")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
