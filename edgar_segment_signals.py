"""Derive multi-bagger archetypes from the harvested segment-level XBRL.

Reads edgar_segments.csv (produced by edgar_segments_extract.py) and
computes per-filer signals that aren't visible in companyfacts JSON.

ROBUSTNESS (v2 — post-audit rewrite). The v1 derivation pivoted facts on
period_end alone with aggfunc='sum', which (a) summed a quarterly fact and
a YTD fact sharing an end date into one number, (b) summed the same
economic fact restated across filings/concepts 4-5x (median filer's
"segment revenue" was 5x its actual revenue), and (c) let Corporate /
Elimination rollup members count as segments. Everything here now runs on
a DURATION-AWARE, DEDUPED panel keyed on (symbol, member, period_start,
period_end, period_type), compares only like-for-like period types, and
excludes non-operating members.

Time-base triangulation (house doctrine): the harvest pulls the latest TWO
10-Ks + latest 10-Q per filer, giving
  seg_yoy_fy       latest FY vs prior FY (slow, clean)
  seg_yoy_q        latest quarter vs the same quarter a year earlier —
                   true YoY, seasonality-immune (both live in one 10-Q)
  seg_accel_fy     FY YoY now minus FY YoY a year earlier (2nd derivative)
plus a SECOND ACCOUNTING MEASURE: segment operating income / gross profit
(margin level, margin delta, segment operating leverage) — a genuinely
independent lens agreeing or disagreeing with the revenue story.

Materiality: the "fastest segment" must hold >= 5% of revenue (or be
rising by >= 1pp) — a 1%-of-revenue segment tripling no longer drives the
archetype.

Output: edgar_segment_signals.csv (symbol-keyed) + edgar_segment_detail.csv.
"""
from __future__ import annotations
import argparse
import re
import sys

import numpy as np
import pandas as pd


SEGMENT_AXIS = "us-gaap:StatementBusinessSegmentsAxis"
GEOGRAPHIC_AXES = [
    "us-gaap:StatementGeographicalAxis",
    "srt:StatementGeographicalAxis",
    "srt:GeographicalAxis",
]
PRODUCT_AXES = ["srt:ProductOrServiceAxis", "us-gaap:ProductOrServiceAxis"]
CUSTOMER_AXES = ["us-gaap:MajorCustomersAxis",
                 "us-gaap:CustomerConcentrationRiskAxis"]

REVENUE_CONCEPTS = {
    "us-gaap:Revenues",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
    "us-gaap:SalesRevenueNet",
    "us-gaap:SalesRevenueGoodsNet",
    "us-gaap:SalesRevenueServicesNet",
}
MARGIN_CONCEPTS = {
    "us-gaap:OperatingIncomeLoss",
    "us-gaap:GrossProfit",
}

# Members that are NOT operating segments — never counted, never ranked.
EXCLUDE_MEMBER_RE = re.compile(
    r"(Corporate|Elimination|Intersegment|Unallocated|AllOther|Consolidat"
    r"|Reconcil|Total|ParentCompany|Discontinued)", re.I)


def _clean_member(m: str) -> str:
    """Strip XBRL prefixes + 'Member' suffix from a segment label."""
    if not isinstance(m, str):
        return ""
    if ":" in m:
        m = m.split(":", 1)[1]
    for suf in ("Member", "Segment"):
        while m.endswith(suf):
            m = m[: -len(suf)]
    m = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", m)
    m = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", m)
    return m.strip()


def _panel(df: pd.DataFrame, concepts, axis: str,
           exclude_rollups: bool = True) -> pd.DataFrame:
    """Duration-aware, deduped (symbol, member, ps, pe, ptype) fact panel.

    The duration BUCKET is part of the identity key so a quarterly fact and
    a YTD fact ending the same day never merge; the same economic fact
    restated across filings (or tagged under two revenue concepts) keeps
    ONE row (latest accession wins).
    """
    p = df[df["concept"].isin(concepts) & (df["axis"] == axis)].copy()
    if exclude_rollups:
        p = p[~p["member"].astype(str).str.contains(EXCLUDE_MEMBER_RE)]
    if p.empty:
        return p
    p["ps"] = pd.to_datetime(p["period_start"], errors="coerce")
    p["pe"] = pd.to_datetime(p["period_end"], errors="coerce")
    p = p.dropna(subset=["pe"])
    # Missing period_start (23% of facts): fiscal_period labels the duration.
    dur = (p["pe"] - p["ps"]).dt.days
    ptype = pd.cut(dur, [0, 120, 200, 300, 400], labels=["Q", "H", "T3Q", "FY"])
    fp = p["fiscal_period"].astype(str).str.upper()
    ptype = ptype.astype(object)
    ptype = np.where(ptype == None, np.nan, ptype)  # noqa: E711
    ptype = pd.Series(ptype, index=p.index)
    ptype = ptype.fillna(fp.map({"FY": "FY", "Q1": "Q", "Q2": "Q",
                                 "Q3": "Q", "Q4": "Q"}))
    p["ptype"] = ptype
    p = p.dropna(subset=["ptype"])
    p["value"] = pd.to_numeric(p["value"], errors="coerce")
    p = p.dropna(subset=["value"])
    # Dedupe restatements/concept double-tags: one row per economic fact.
    p = (p.sort_values("accession")
          .drop_duplicates(["symbol", "member", "pe", "ptype"], keep="last"))
    return p


def _yoy_pairs(g: pd.DataFrame, ptype: str, tol_days: int = 21):
    """Like-for-like YoY pairs for one symbol's panel at one period type.

    Returns list of (member, pe_latest, v_latest, v_prior, yoy) using the
    fact whose period_end sits ~365 days before the latest, per member.
    """
    sub = g[g["ptype"] == ptype]
    if sub.empty:
        return []
    out = []
    for member, m in sub.groupby("member"):
        m = m.sort_values("pe")
        latest = m.iloc[-1]
        target = latest["pe"] - pd.Timedelta(days=365)
        prior = m[(m["pe"] - target).abs() <= pd.Timedelta(days=tol_days)]
        if prior.empty:
            continue
        v_l, v_p = float(latest["value"]), float(prior.iloc[-1]["value"])
        if v_p <= 0:          # negative/zero prior inverts the growth sign
            continue
        yoy = (v_l - v_p) / v_p
        if -1.0 <= yoy <= 5.0:
            out.append((member, latest["pe"], v_l, v_p, yoy))
    return out


def _fy_series(g: pd.DataFrame):
    """Per-member FY revenue series (pe-sorted) for acceleration/mix-drift."""
    sub = g[g["ptype"] == "FY"]
    return {m: mm.sort_values("pe")[["pe", "value"]]
            for m, mm in sub.groupby("member")} if not sub.empty else {}


def _mix_from_latest(g: pd.DataFrame, top_n: int = 3):
    """Mix (share dict, top list, total) from the LATEST like-for-like
    period: prefer the latest FY column; else the latest quarter."""
    for ptype in ("FY", "Q", "H", "T3Q"):
        sub = g[g["ptype"] == ptype]
        if sub.empty:
            continue
        latest_pe = sub["pe"].max()
        snap = sub[sub["pe"] == latest_pe]
        mix = snap.groupby("member")["value"].sum()
        mix = mix[mix > 0]
        if mix.empty:
            continue
        total = float(mix.sum())
        shares = (mix / total).sort_values(ascending=False)
        top = [(m, float(shares[m])) for m in shares.head(top_n).index]
        return shares.to_dict(), top, total, latest_pe, ptype
    return {}, [], None, None, None


def _hhi(shares: dict) -> float | None:
    return float(sum(v * v for v in shares.values())) if shares else None


def derive(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    seg_rev = _panel(df, REVENUE_CONCEPTS, SEGMENT_AXIS)
    seg_opinc = _panel(df, {"us-gaap:OperatingIncomeLoss"}, SEGMENT_AXIS)
    seg_gp = _panel(df, {"us-gaap:GrossProfit"}, SEGMENT_AXIS)
    geo_panels = {ax: _panel(df, REVENUE_CONCEPTS, ax, exclude_rollups=False)
                  for ax in GEOGRAPHIC_AXES}
    prod_rev = pd.concat([_panel(df, REVENUE_CONCEPTS, ax,
                                 exclude_rollups=False)
                          for ax in PRODUCT_AXES], axis=0) \
        if any(len(_panel(df, REVENUE_CONCEPTS, ax, exclude_rollups=False))
               for ax in PRODUCT_AXES) else pd.DataFrame()

    cust_syms = set(df[df["axis"].isin(CUSTOMER_AXES)]["symbol"].unique())

    rows = []
    for sym in df["symbol"].unique():
        g = seg_rev[seg_rev["symbol"] == sym] if not seg_rev.empty else seg_rev
        rec: dict = {"symbol": sym}

        # ---- mix (latest like-for-like snapshot, deduped) ----
        shares, top, total, mix_pe, mix_ptype = ({}, [], None, None, None)
        if g is not None and not g.empty:
            shares, top, total, mix_pe, mix_ptype = _mix_from_latest(g)
        rec["segment_count"] = int(len(shares))
        rec["segment_revenue_hhi"] = _hhi(shares)
        rec["largest_segment_share"] = (max(shares.values()) if shares else None)
        rec["largest_segment_name"] = (_clean_member(top[0][0]) if top else None)
        rec["top_segments"] = "; ".join(
            f"{_clean_member(m)} {s*100:.0f}%" for m, s in top)
        rec["segment_revenue_total"] = total

        # ---- growth family (like-for-like, per member, material only) ----
        fy_pairs = _yoy_pairs(g, "FY") if g is not None and not g.empty else []
        q_pairs = _yoy_pairs(g, "Q") if g is not None and not g.empty else []
        # Per-member robust growth = best available like-for-like base
        growth: dict[str, dict] = {}
        _hist: dict[str, list] = {}
        for member, pe, v_l, v_p, yoy in fy_pairs:
            growth.setdefault(member, {})["fy"] = yoy
            _hist.setdefault(member, []).append((str(pe), float(yoy)))
        for member, pe, v_l, v_p, yoy in q_pairs:
            growth.setdefault(member, {})["q"] = yoy
            _hist.setdefault(member, []).append((str(pe), float(yoy)))
        # Materiality + robust per-member growth
        n_periods = len(fy_pairs) + len(q_pairs)
        member_rows = []
        for member, gg in growth.items():
            share = shares.get(member)
            # (audit #5) FY preferred, Q only as FALLBACK — nanmax cherry-picked
            # the more flattering of two noisy estimates, inflating
            # fastest_segment_yoy by construction
            robust = gg.get("fy", np.nan)
            if pd.isna(robust):
                robust = gg.get("q", np.nan)
            member_rows.append((member, share, gg.get("fy"), gg.get("q"),
                                float(robust)))
        rec["n_segment_periods"] = n_periods

        # share_delta from the FY series (mix drift toward the winner)
        fy_by_member = _fy_series(g) if g is not None and not g.empty else {}
        share_prior: dict[str, float] = {}
        if fy_by_member:
            pes = sorted({pe for mm in fy_by_member.values()
                          for pe in mm["pe"]})
            if len(pes) >= 2:
                prior_pe = pes[-2]
                tot_prior = sum(float(mm[mm["pe"] == prior_pe]["value"].sum())
                                for mm in fy_by_member.values())
                if tot_prior > 0:
                    for m, mm in fy_by_member.items():
                        v = float(mm[mm["pe"] == prior_pe]["value"].sum())
                        if v > 0:
                            share_prior[m] = v / tot_prior
        # (audit #6) prior mix is FY-only; the delta is meaningful only when
        # the CURRENT mix is FY-basis too (a Q-basis latest vs FY prior
        # compares concentration over different-duration windows)
        rec["segment_hhi_delta"] = (
            round(_hhi(shares) - _hhi(share_prior), 4)
            if shares and share_prior and mix_ptype == "FY" else None)

        # fastest MATERIAL segment (share >= 5%, or rising >= 1pp)
        fastest = None
        for member, share, fy, q, robust in member_rows:
            if not np.isfinite(robust):
                continue
            sh = share if share is not None else 0.0
            sh_d = (sh - share_prior.get(member, sh)) if share_prior else 0.0
            material = (sh >= 0.05) or (sh_d >= 0.01)
            if not material:
                continue
            if fastest is None or robust > fastest[4]:
                fastest = (member, sh, fy, q, robust, sh_d)
        if fastest:
            member, sh, fy, q, robust, sh_d = fastest
            rec["fastest_segment_name"] = _clean_member(member)
            rec["fastest_segment_share"] = round(sh, 4)
            rec["fastest_segment_share_delta"] = round(sh_d, 4)
            rec["fastest_seg_yoy_fy"] = (round(fy, 4) if fy is not None else None)
            rec["fastest_seg_yoy_q"] = (round(q, 4) if q is not None else None)
            rec["fastest_segment_yoy"] = round(robust, 4)   # legacy name
            # (user directive) the latest QUARTER is not the base number but
            # it is CORROBORATION: a fresh quarter confirming the FY growth,
            # and a streak of consecutive growing periods, are upweighted by
            # the book blends rather than cherry-picked into the base.
            _qc_seg = (q is not None and np.isfinite(q) and q > 0
                       and (fy is None or not np.isfinite(fy) or q >= 0.5 * fy))
            rec["fastest_seg_q_confirm"] = int(bool(_qc_seg))
            _hh = sorted(_hist.get(member, []), key=lambda t: t[0], reverse=True)
            _streak = 0
            for _pe_h, _yy_h in _hh:
                if np.isfinite(_yy_h) and _yy_h > 0:
                    _streak += 1
                else:
                    break
            rec["fastest_seg_consec_growth"] = int(_streak)
        robust_all = [r for *_x, r in
                      [(m, s, f, q, r) for m, s, f, q, r in member_rows]
                      if np.isfinite(r)]
        if len(robust_all) >= 2:
            rec["segment_growth_dispersion"] = round(float(np.std(robust_all,
                                                                  ddof=1)), 4)
            rec["seg_growth_range"] = round(float(max(robust_all)
                                                  - min(robust_all)), 4)

        # FY acceleration for the fastest segment (needs 3 FY points)
        if fastest and fastest[0] in fy_by_member:
            mm = fy_by_member[fastest[0]].sort_values("pe")
            vals = mm["value"].astype(float).tolist()
            if len(vals) >= 3 and vals[-3] > 0 and vals[-2] > 0:
                yoy_now = (vals[-1] - vals[-2]) / vals[-2]
                yoy_prev = (vals[-2] - vals[-3]) / vals[-3]
                if -1 <= yoy_now <= 5 and -1 <= yoy_prev <= 5:
                    rec["fastest_seg_accel_fy"] = round(yoy_now - yoy_prev, 4)

        # ---- margin lens (2nd accounting measure) on the fastest segment ----
        if fastest is not None:
            member = fastest[0]
            for panel, tag in ((seg_opinc, "op"), (seg_gp, "gp")):
                if panel.empty:
                    continue
                mp = panel[(panel["symbol"] == sym)
                           & (panel["member"] == member)]
                if mp.empty:
                    continue
                # margin now + a year ago, matched to the same-revenue period
                for ptype in ("FY", "Q"):
                    mm = mp[mp["ptype"] == ptype].sort_values("pe")
                    gg = g[(g["member"] == member) & (g["ptype"] == ptype)] \
                        .sort_values("pe")
                    if mm.empty or gg.empty:
                        continue
                    joined = pd.merge(mm[["pe", "value"]],
                                      gg[["pe", "value"]], on="pe",
                                      suffixes=("_p", "_r"))
                    joined = joined[joined["value_r"] > 0]
                    if joined.empty:
                        continue
                    joined["margin"] = joined["value_p"] / joined["value_r"]
                    m_now = float(joined.iloc[-1]["margin"])
                    if tag == "op" and "fastest_seg_opmargin" not in rec:
                        rec["fastest_seg_opmargin"] = round(m_now, 4)
                    if len(joined) >= 2:
                        target = joined.iloc[-1]["pe"] - pd.Timedelta(days=365)
                        prior = joined[(joined["pe"] - target).abs()
                                       <= pd.Timedelta(days=21)]
                        if not prior.empty:
                            d = m_now - float(prior.iloc[-1]["margin"])
                            key = ("fastest_seg_opmargin_delta_yoy"
                                   if tag == "op"
                                   else "fastest_seg_gpmargin_delta_yoy")
                            if key not in rec:
                                rec[key] = round(d, 4)
                            # segment operating leverage: profit vs revenue yoy
                            if tag == "op" and "seg_oplev" not in rec:
                                p_prior = float(prior.iloc[-1]["value_p"])
                                r_prior = float(prior.iloc[-1]["value_r"])
                                p_now = float(joined.iloc[-1]["value_p"])
                                r_now = float(joined.iloc[-1]["value_r"])
                                if p_prior > 0 and r_prior > 0:
                                    rec["seg_opinc_yoy"] = round(
                                        (p_now - p_prior) / p_prior, 4)
                                    rec["seg_oplev"] = round(
                                        (p_now - p_prior) / p_prior
                                        - (r_now - r_prior) / r_prior, 4)
                    break   # first available ptype wins per measure
        _omd = rec.get("fastest_seg_opmargin_delta_yoy")
        _gmd = rec.get("fastest_seg_gpmargin_delta_yoy")
        rec["seg_margin_inflect_flag"] = int(
            (_omd is not None and _omd >= 0.02)
            or (_gmd is not None and _gmd >= 0.02))

        # ---- geographic mix: best single axis, never summed across axes ----
        best_geo = None
        for ax, panel in geo_panels.items():
            if panel.empty:
                continue
            gp_ = panel[panel["symbol"] == sym]
            if gp_.empty:
                continue
            shares_g, top_g, _t, _pe, _pt = _mix_from_latest(gp_)
            if shares_g and (best_geo is None
                             or len(shares_g) > len(best_geo[0])):
                best_geo = (shares_g, top_g)
        rec["geographic_region_count"] = (len(best_geo[0]) if best_geo else 0)
        rec["largest_region_share"] = (max(best_geo[0].values())
                                       if best_geo else None)
        rec["largest_region_name"] = (_clean_member(best_geo[1][0][0])
                                      if best_geo and best_geo[1] else None)
        rec["top_regions"] = ("; ".join(
            f"{_clean_member(m)} {s*100:.0f}%" for m, s in best_geo[1])
            if best_geo else "")

        # ---- product lines / customer concentration ----
        if not prod_rev.empty:
            pr = prod_rev[prod_rev["symbol"] == sym]
            rec["product_line_count"] = int(pr["member"].nunique())
        else:
            rec["product_line_count"] = 0
        rec["customer_concentration_flag"] = int(sym in cust_syms)

        rows.append(rec)
    return pd.DataFrame(rows)


def derive_detail(df: pd.DataFrame) -> pd.DataFrame:
    """Long-form (symbol, segment_name, revenue_latest, share, yoy, margin)."""
    if df.empty:
        return pd.DataFrame()
    seg_rev = _panel(df, REVENUE_CONCEPTS, SEGMENT_AXIS)
    seg_opinc = _panel(df, {"us-gaap:OperatingIncomeLoss"}, SEGMENT_AXIS)
    if seg_rev.empty:
        return pd.DataFrame()

    rows = []
    for sym, g in seg_rev.groupby("symbol"):
        shares, top, total, mix_pe, mix_ptype = _mix_from_latest(g, top_n=99)
        if not shares:
            continue
        fy_pairs = {m: yoy for m, pe, vl, vp, yoy in _yoy_pairs(g, "FY")}
        q_pairs = {m: yoy for m, pe, vl, vp, yoy in _yoy_pairs(g, "Q")}
        snap = g[(g["pe"] == mix_pe) & (g["ptype"] == mix_ptype)]
        op_snap = seg_opinc[(seg_opinc["symbol"] == sym)
                            & (seg_opinc["pe"] == mix_pe)
                            & (seg_opinc["ptype"] == mix_ptype)] \
            if not seg_opinc.empty else pd.DataFrame()
        for member, share in sorted(shares.items(), key=lambda kv: -kv[1]):
            v_latest = float(snap[snap["member"] == member]["value"].sum())
            yoy = fy_pairs.get(member, q_pairs.get(member))
            opmargin = None
            if not op_snap.empty and v_latest > 0:
                ov = op_snap[op_snap["member"] == member]["value"]
                if len(ov):
                    opmargin = round(float(ov.iloc[-1]) / v_latest, 4)
            rows.append({
                "symbol": sym,
                "segment_name": _clean_member(member),
                "segment_member_raw": member,
                "revenue_latest": v_latest,
                "share_of_revenue": round(float(share), 4),
                "yoy_growth": (round(yoy, 4) if yoy is not None else None),
                "op_margin": opmargin,
                "period_end": str(pd.to_datetime(mix_pe).date()),
                "period_type": mix_ptype,
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["symbol", "share_of_revenue"],
                              ascending=[True, False])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="edgar_segments.csv")
    ap.add_argument("--out", default="edgar_segment_signals.csv")
    ap.add_argument("--detail-out", default="edgar_segment_detail.csv")
    args = ap.parse_args()

    print(f"loading {args.segments}...", file=sys.stderr)
    df = pd.read_csv(args.segments, low_memory=False)
    print(f"  {len(df):,} fact rows, {df.symbol.nunique():,} filers",
          file=sys.stderr)

    out = derive(df)

    detail = derive_detail(df)
    detail.to_csv(args.detail_out, index=False)
    print(f"wrote {args.detail_out}: {len(detail):,} rows", file=sys.stderr)

    # Fold in segment sum-of-parts / mix-shift valuation features (durable):
    # computed from the detail rows and currency-reconciled against consolidated
    # revenue, so a segment-signals rebuild always carries these columns.
    try:
        from compute_segment_valuation import compute_segment_valuation, _load_cons_rev
        val = compute_segment_valuation(detail, _load_cons_rev())
        val.to_csv("segment_valuation.csv", index=False)
        out = out.drop(columns=[c for c in val.columns if c != "symbol" and c in out.columns],
                       errors="ignore").merge(val, on="symbol", how="left")
        print(f"  merged segment valuation: best_ebit cov "
              f"{int(val['seg_best_ebit_usd'].notna().sum())}", file=sys.stderr)
    except Exception as e:  # never let the valuation add-on break the core signals
        print(f"  WARN segment valuation skipped: {e}", file=sys.stderr)

    out.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}: {len(out):,} filers", file=sys.stderr)

    print("\nCoverage by field:", file=sys.stderr)
    for c in out.columns:
        if c == "symbol":
            continue
        non_null = out[c].notna().sum()
        print(f"  {c:34s} {non_null:5d} / {len(out):,}", file=sys.stderr)


if __name__ == "__main__":
    main()
