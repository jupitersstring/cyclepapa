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
    ap.add_argument("--per-archetype", type=int, default=0,
                    help="sample N firers from EVERY archetype (top-ETA + "
                         "seeded random) and check those instead of/besides "
                         "the top-N")
    ap.add_argument("--sample", type=int, default=0,
                    help="ALSO check N random rows (seeded) beyond the top — "
                         "verification must not be top-N-biased")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--master", default="asymmetry_global.csv")
    ap.add_argument("--yf", default="ticker_yf.csv")
    ap.add_argument("--fresh-yf", default=None,
                    help="a JUST-fetched ticker_yf-format csv for the same "
                         "names: verifies the stored source itself is fresh")
    args = ap.parse_args()

    g = pd.read_csv(args.master, low_memory=False)
    try:
        y = pd.read_csv(args.yf, low_memory=False).drop_duplicates(
            "symbol", keep="last").set_index("symbol")
    except FileNotFoundError:
        y = pd.DataFrame()

    fresh = pd.DataFrame()
    if args.fresh_yf and os.path.exists(args.fresh_yf):
        fresh = pd.read_csv(args.fresh_yf, low_memory=False).drop_duplicates(
            "symbol", keep="last").set_index("symbol")

    g["_eta"] = pd.to_numeric(g.get("entry_today_asymmetry"), errors="coerce")
    top = g.sort_values("_eta", ascending=False).head(args.top)
    if args.per_archetype:
        try:
            tt = pd.read_csv("archetype_tags.csv", low_memory=False)
            gi = g.set_index("symbol")
            picks = []
            rng = np.random.RandomState(args.seed)
            for a in [c for c in tt.columns if c.startswith("arch_")]:
                f = tt.loc[tt[a] == 1, "symbol"]
                if not len(f):
                    continue
                etas = gi.reindex(f)["_eta"] if "_eta" in gi.columns else None
                f_eta = pd.Series(
                    pd.to_numeric(gi.reindex(f).get("entry_today_asymmetry"),
                                  errors="coerce").values, index=f)
                picks.append(f_eta.idxmax() if f_eta.notna().any() else f.iloc[0])
                extra = min(max(args.per_archetype - 1, 0), len(f) - 1)
                if extra:
                    picks += list(rng.choice(f[f != picks[-1]], size=extra,
                                             replace=False))
            uniq = list(dict.fromkeys(picks))
            top = pd.concat([top, g[g["symbol"].isin(uniq)]]).drop_duplicates("symbol")
            print(f"  per-archetype sample: {len(uniq)} unique firers added",
                  file=sys.stderr)
        except FileNotFoundError:
            pass
    if args.sample:
        rest = g.drop(top.index)
        rest = rest[pd.to_numeric(rest.get("market_cap"), errors="coerce") > 0]
        top = pd.concat([top, rest.sample(min(args.sample, len(rest)),
                                          random_state=args.seed)])

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
        _effp = price / 100.0 if str(sym).endswith(".L") else price  # GBp lines
        d = dev(mc, _effp * sh) if np.isfinite(price) and np.isfinite(sh) else np.nan
        if np.isfinite(d) and d > 0.10:
            flag("ERROR", f"mcap {mc:.3g} != price*shares {_effp*sh:.3g} (dev {d:.0%})")
        if np.isfinite(ev) and np.isfinite(eb) and eb > 0 and np.isfinite(evb):
            d = dev(evb, ev / eb)
            if d > 0.25:
                flag("ERROR", f"ev_ebitda {evb:.2f} != EV/ebitda {ev/eb:.2f} (dev {d:.0%})")
        if np.isfinite(ev) and np.isfinite(rv) and rv > 0 and np.isfinite(evs):
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
            if d > 0.25 and abs(ebm - eb / rv) > 0.03:   # absolute floor: near-zero margins explode % dev
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

        # --- DEEP per-figure checks (accounting identities & triangulations)
        gm, om = num(r, "gross_margin"), num(r, "op_margin")
        cfo, roe, pb_v, ps_v = num(r, "cfo_ttm"), num(r, "roe"), num(r, "pb"), num(r, "p_s")
        rvu, ebu = num(r, "revenue_ttm_usd"), num(r, "ebitda_ttm_usd")
        p52h = num(r, "price_52w_high")
        dvy = num(r, "dividend_yield")
        ncp = num(r, "net_cash_pct_mcap")
        # hard accounting identities (violation = corrupted figure, not noise)
        # Margin orderings are STRONG heuristics, not inalienable laws
        # (associates' income / other operating income / period bases bend
        # them). Policy: mild violation is KEPT + qc-FLAGGED (WARN here);
        # only an extreme gap — which the harmonizer nulls — is an ERROR.
        if np.isfinite(ebm) and np.isfinite(om) and ebm < om - 0.02:
            sev_m = "ERROR" if (om - ebm) > 0.15 else "WARN"
            flag(sev_m, f"ebitda_margin {ebm:.3f} < op_margin {om:.3f} "
                        f"(gap {om-ebm:.2f} — kept & qc-flagged"
                        f"{'' if sev_m=='WARN' else '; EXTREME, should be nulled'})")
        if np.isfinite(gm) and np.isfinite(om) and gm < om - 0.02:
            sev_m = "ERROR" if (om - gm) > 0.15 else "WARN"
            flag(sev_m, f"gross_margin {gm:.3f} < op_margin {om:.3f} "
                        f"(gap {om-gm:.2f} — kept & qc-flagged"
                        f"{'' if sev_m=='WARN' else '; EXTREME, should be nulled'})")
        if np.isfinite(gm) and gm > 1.02:
            flag("ERROR", f"gross_margin {gm:.3f} > 100% of revenue")
        # near-hard: FCF cannot exceed CFO with capex >= 0 (asset-sale years rare)
        if np.isfinite(fcf) and np.isfinite(cfo) and cfo > 0 and fcf > cfo * 1.05:
            flag("WARN", f"fcf_ttm {fcf:.3g} > cfo_ttm {cfo:.3g} "
                         f"(negative capex? check basis)")
        # ROE triangulation: NI/equity == (mcap/equity)/(mcap/NI) => roe == pb/p_e
        if all(np.isfinite(x) and x > 0 for x in (roe, pb_v, pe)):
            d = dev(roe, pb_v / pe)
            if d > 0.35:
                flag("WARN", f"roe {roe:.3f} vs pb/p_e {pb_v/pe:.3f} "
                             f"(dev {d:.0%} — one of roe/pb/pe on a different "
                             f"period or equity basis)")
        # p_s identity
        if all(np.isfinite(x) for x in (ps_v, mc, rv)) and rv > 0 and ps_v > 0:
            d = dev(ps_v, mc / rv)
            if d > 0.25:
                flag("ERROR", f"p_s {ps_v:.2f} != mcap/revenue {mc/rv:.2f} "
                              f"(dev {d:.0%})")
        # FX-twin coherence: both USD twins must imply the SAME fx rate
        if all(np.isfinite(x) and x != 0 for x in (rvu, rv, ebu, eb)):
            fx1, fx2 = rvu / rv, ebu / eb
            if fx1 > 0 and fx2 > 0 and (max(fx1, fx2) / min(fx1, fx2)) > 1.10:
                flag("ERROR", f"FX-twin mismatch: revenue implies fx {fx1:.4g}, "
                              f"ebitda implies {fx2:.4g} (partial rescale)")
            if np.isfinite(fx1) and fx1 > 0 and not (1e-5 <= fx1 <= 4.5):
                flag("ERROR", f"implausible USD conversion rate {fx1:.4g} "
                              f"(revenue_ttm_usd vs revenue_ttm)")
        # price inside the 52w envelope (a new high can exceed slightly)
        if np.isfinite(price) and np.isfinite(p52h) and p52h > 0 and price > p52h * 1.05:
            flag("WARN", f"price {price:.4g} above 52w high {p52h:.4g} "
                         f"(stale 52w high or unadjusted split)")
        # payout sanity
        if np.isfinite(dvy) and dvy > 0.30:
            flag("WARN", f"dividend_yield {dvy:.2%} implausible (>30%)")
        # net-cash consistency vs components (broad-cash basis tolerated)
        if all(np.isfinite(x) for x in (ncp, ca, td, mc)) and mc > 0:
            comp_nc = (ca - td) / mc
            if abs(ncp - comp_nc) > 0.30:
                flag("WARN", f"net_cash_pct_mcap {ncp:.2f} vs (cash-debt)/mcap "
                             f"{comp_nc:.2f} (basis gap > 30pts of mcap)")

        # --- source FRESHNESS (a just-fetched Yahoo pull for these names)
        if len(fresh) and sym in fresh.index:
            fr = fresh.loc[sym]
            fmc = pd.to_numeric(pd.Series([fr.get("yf_market_cap")]), errors="coerce").iloc[0]
            fpx = pd.to_numeric(pd.Series([fr.get("yf_price")]), errors="coerce").iloc[0]
            d = dev(mc, fmc)
            if np.isfinite(d) and d > 0.25:
                flag("ERROR", f"market_cap {mc:.4g} vs FRESH Yahoo {fmc:.4g} "
                              f"(dev {d:.0%} — stored source is stale)")
            elif np.isfinite(d) and d > 0.10:
                flag("WARN", f"market_cap {mc:.4g} vs FRESH Yahoo {fmc:.4g} "
                             f"(dev {d:.0%} — price drift since last pull)")
            for fc, mv2, nm2 in (("yf_ebitda", eb, "ebitda_ttm"),
                                 ("yf_revenue", rv, "revenue_ttm")):
                fv = pd.to_numeric(pd.Series([fr.get(fc)]), errors="coerce").iloc[0]
                if np.isfinite(fv) and fv != 0 and np.isfinite(mv2) and mv2 != 0:
                    ratio = mv2 / fv
                    if ratio > 1.4 or ratio < 1 / 1.4:
                        _qcf2 = str(r.get("qc_flags", "") or "")
                        sev = "WARN" if ("edgar_grounded" in _qcf2 or "unit_repaired" in _qcf2) else "ERROR"
                        flag(sev, f"{nm2} {mv2:.3g} vs FRESH Yahoo {fv:.3g} "
                                  f"({'EDGAR-preferred divergence' if sev == 'WARN' else 'level moved outside tolerance'})")

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
            _qcf = str(r.get("qc_flags", "") or "")
            _edgar_row = ("edgar_grounded" in _qcf) or ("unit_repaired" in _qcf)
            for yc, mv, name in (("yf_ebitda", eb, "ebitda_ttm"),
                                 ("yf_revenue", rv, "revenue_ttm")):
                yv = pd.to_numeric(pd.Series([yr.get(yc)]), errors="coerce").iloc[0]
                if np.isfinite(yv) and yv != 0 and np.isfinite(mv) and mv != 0:
                    ratio = mv / yv
                    if ratio > 1.4 or ratio < 1 / 1.4:
                        # audited EDGAR outranks Yahoo BY DESIGN — divergence on
                        # an edgar_grounded row is the hierarchy working
                        sev = "WARN" if _edgar_row else "ERROR"
                        flag(sev, f"{name} {mv:.3g} vs Yahoo {yv:.3g} "
                                  f"({'EDGAR-preferred divergence' if _edgar_row else 'outside reconcile tolerance'})")
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
