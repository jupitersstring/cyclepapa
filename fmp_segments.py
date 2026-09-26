"""FMP revenue segmentation (product + geographic) for the whole universe.

Why this exists: the segment archetypes and the segment book were fed only by
the EDGAR dimensional harvest (~10% of US filers). FMP carries multi-year
segment revenue for product lines and geographies across US and non-US
filers, so this engine gives every ticker FMP covers the same segment lens.

Outputs
  fmp_segments.csv          one row per symbol (summary, fmp_seg_* / fmp_geo_*)
  fmp_segments_detail.csv   long format: symbol, axis, fiscal_year, segment,
                            revenue, share, yoy — last 4 fiscal years, for the
                            segment book's per-ticker detail sheets

What FMP does NOT carry: segment operating income / margin. Segment EBIT legs
stay EDGAR-only; everything here is revenue-based (growth, mix, concentration,
geography). Revenues are in the filer's reporting currency; every derived
metric (shares, growth, HHI) is dimensionless, so currency does not matter.

Resumable: both CSVs checkpoint; symbols already in fmp_segments.csv are skipped.
"""
from __future__ import annotations

import argparse
import math
import os
import re

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_segments.csv"
OUT_DETAIL = "fmp_segments_detail.csv"
OUT_QDETAIL = "fmp_segments_qdetail.csv"
DETAIL_YEARS = 6          # FY history kept for the book (3y CAGR needs FY-3)
QDETAIL_QUARTERS = 8      # latest quarters kept for the book's momentum view
# Bumped when a field definition changes: rows from an older schema are
# recomputed from cache instead of being skipped as "done".
SCHEMA = 2

# Geography keywords. EM follows the MSCI Emerging Markets membership; broad
# mixed buckets ("Asia Pacific", "Rest of World", "International") are
# deliberately NOT counted as EM because they blend developed markets.
_EM_PAT = re.compile(
    r"china|prc|mainland|hong kong|macau|taiwan|india|brazil|latin america|"
    r"south america|central america|mexico|argentin|chile|colombia|peru|russia|"
    r"middle east|africa|turkey|t[uü]rkiye|indonesia|thailand|malaysia|philippin|"
    r"vietnam|korea|saudi|emirates|uae|qatar|kuwait|egypt|nigeria|pakistan|"
    r"poland|hungary|czech|greece|emerging", re.I)
_CHINA_PAT = re.compile(r"china|prc|mainland|hong kong|macau", re.I)
# Rows that are totals / eliminations rather than segments.
_SKIP_PAT = re.compile(r"^(total|consolidated|elimination|intersegment|"
                       r"corporate and elim|reconcil)", re.I)


def _clean_rows(payload):
    """[{fiscalYear, data{seg: rev}}] -> {fy: {seg: rev>0}} (newest first)."""
    out = {}
    for r in payload or []:
        fy = r.get("fiscalYear")
        data = r.get("data") or {}
        try:
            fy = int(fy)
        except (TypeError, ValueError):
            continue
        segs = {}
        for name, v in data.items():
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(v) or v <= 0 or _SKIP_PAT.search(str(name).strip()):
                continue
            segs[str(name).strip()] = v
        if segs:
            out[fy] = segs
    return dict(sorted(out.items(), reverse=True))


MAX_STALENESS_YEARS = 2     # latest segment FY must be within 2 years of today
MIN_PRIOR_BASE_OF_CURRENT = 0.05   # prior-year segment >= 5% of TODAY's total


def _axis_summary(years: dict, prefix: str) -> dict:
    """Summarise one axis (product or geographic). Three validity rules, each
    tied to an artifact the audit caught (not a cosmetic cap):
      * STALENESS: FMP sometimes carries segmentation that stopped updating
        years ago (NSYS's latest was FY2013). Older than MAX_STALENESS_YEARS
        -> the axis is not treated as current at all.
      * SINGLE SEGMENT: with one segment the "fastest segment" is just the
        company (FDMT: milestone revenue $37k -> $85M). Growth/mix metrics
        need >= 2 segments.
      * TINY BASE: a segment's prior-year revenue must be >= 5% of the
        company's CURRENT total, so a line that was immaterial last year
        cannot report 100x growth off a rounding-error base.
    """
    import datetime as _dt
    rec = {}
    if not years:
        return rec
    fys = list(years)
    if fys[0] < _dt.date.today().year - MAX_STALENESS_YEARS:
        return rec
    cur = years[fys[0]]
    tot = sum(cur.values())
    if tot <= 0:
        return rec
    shares = {k: v / tot for k, v in cur.items()}
    rec[f"{prefix}_fiscal_year"] = float(fys[0])
    rec[f"{prefix}_count"] = float(len(cur))
    rec[f"{prefix}_hhi"] = float(sum(s * s for s in shares.values()))
    big = max(shares, key=shares.get)
    rec[f"{prefix}_largest_name"] = big
    rec[f"{prefix}_largest_share"] = shares[big]
    rec[f"{prefix}_years"] = float(len(fys))
    if len(fys) >= 2 and len(cur) >= 2:
        prev = years[fys[1]]
        ptot = sum(prev.values())
        yoys = {k: cur[k] / prev[k] - 1.0 for k in cur
                if k in prev and prev[k] > 0 and ptot > 0
                and prev[k] / tot >= MIN_PRIOR_BASE_OF_CURRENT
                # same eligibility band as edgar_segment_signals: growth
                # outside [-100%, +500%] is an acquisition / reclassification
                # / launch-from-nothing, not an organic engine
                and -1.0 <= cur[k] / prev[k] - 1.0 <= 5.0}
        if yoys:
            fast = max(yoys, key=yoys.get)
            rec[f"{prefix}_fastest_name"] = fast
            rec[f"{prefix}_fastest_yoy"] = yoys[fast]
            rec[f"{prefix}_fastest_share"] = shares.get(fast, np.nan)
            rec[f"{prefix}_fastest_share_delta"] = shares.get(fast, np.nan) - prev[fast] / ptot
            if len(yoys) >= 2:
                rec[f"{prefix}_growth_dispersion"] = float(np.std(list(yoys.values())))
        if ptot > 0:
            rec[f"{prefix}_total_yoy"] = tot / ptot - 1.0
            prev_shares = {k: v / ptot for k, v in prev.items()}
            # concentration trend (EDGAR segment_hhi_delta): + = concentrating
            rec[f"{prefix}_hhi_delta"] = rec[f"{prefix}_hhi"] - sum(x * x for x in prev_shares.values())
            # ROTTING CORE (EDGAR seg_core_declining): a large (>= 25%) segment
            # shrinking >= 10% YoY — flat consolidated revenue can hide it
            rec[f"{prefix}_core_declining"] = float(any(
                prev_shares.get(k, 0) >= 0.25 and prev[k] > 0 and v / prev[k] - 1 <= -0.10
                for k, v in cur.items() if k in prev))
        fast = rec.get(f"{prefix}_fastest_name")
        # FY ACCELERATION of the fastest segment (EDGAR fastest_seg_accel_fy):
        # needs three consecutive fiscal years, both growth rates in [-1, 5]
        if fast and len(fys) >= 3 and fys[0] - fys[2] == 2:
            v0, v1, v2 = (years[fys[i]].get(fast) for i in range(3))
            if v0 and v1 and v2 and v1 > 0 and v2 > 0:
                g0, g1 = v0 / v1 - 1, v1 / v2 - 1
                if -1 <= g0 <= 5 and -1 <= g1 <= 5:
                    rec[f"{prefix}_fastest_accel_fy"] = g0 - g1
        # 3-YEAR view (base-effect-robust): fastest segment's 3y CAGR and the
        # 3y share change of every segment -> the biggest structural gainer
        y3 = fys[0] - 3
        if y3 in years and len(cur) >= 2:
            old = years[y3]
            otot = sum(old.values())
            if otot > 0:
                if fast and old.get(fast, 0) > 0 and cur.get(fast, 0) > 0 \
                        and old[fast] / otot >= MIN_PRIOR_BASE_OF_CURRENT * 0.5:
                    rec[f"{prefix}_fastest_cagr_3y"] = (cur[fast] / old[fast]) ** (1 / 3) - 1
                gains = {k: shares[k] - old[k] / otot for k in cur if k in old}
                if gains:
                    gk = max(gains, key=gains.get)
                    rec[f"{prefix}_share_gainer_3y_name"] = gk
                    rec[f"{prefix}_share_gainer_3y_delta"] = gains[gk]
                rec[f"{prefix}_hhi_delta_3y"] = rec[f"{prefix}_hhi"] - sum(
                    (v / otot) ** 2 for v in old.values())
    return rec


def _quarter_rows(payload):
    """[{date, data{seg: rev}}] -> [(date, {seg: rev>0})] newest first."""
    import datetime as _dt
    out = []
    for r in payload or []:
        try:
            d = _dt.date.fromisoformat(str(r.get("date"))[:10])
        except ValueError:
            continue
        segs = {}
        for name, v in (r.get("data") or {}).items():
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v) and v > 0 and not _SKIP_PAT.search(str(name).strip()):
                segs[str(name).strip()] = v
        if segs:
            out.append((d, segs))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _quarter_momentum(q, fast: str | None, prefix: str) -> dict:
    """Latest-quarter corroboration of the annual fastest segment (EDGAR
    fastest_seg_yoy_q / _q_confirm / _consec_growth), DATE-matched YoY (the
    same quarter a year earlier, 365 +/- 45 days — never a positional lag)."""
    import datetime as _dt
    rec = {}
    if not q or not fast:
        return rec
    if (_dt.date.today() - q[0][0]).days > 200:       # stale quarterly series
        return rec

    def _ya(i):
        target = q[i][0] - _dt.timedelta(days=365)
        for d, segs in q[i + 1:]:
            if abs((d - target).days) <= 45:
                return segs
        return None
    yoys = []
    for i in range(min(len(q), 8)):
        prev = _ya(i)
        cur_v = q[i][1].get(fast)
        pv = prev.get(fast) if prev else None
        yoys.append(cur_v / pv - 1 if (cur_v and pv and pv > 0) else np.nan)
    if yoys and math.isfinite(yoys[0]) and -1 <= yoys[0] <= 5:
        rec[f"{prefix}_fastest_yoy_q"] = yoys[0]
        rec[f"{prefix}_fastest_q_date"] = q[0][0].isoformat()
        if len(yoys) > 1 and math.isfinite(yoys[1]) and -1 <= yoys[1] <= 5:
            rec[f"{prefix}_fastest_q_accel"] = yoys[0] - yoys[1]
    streak = 0
    for y in yoys:
        if math.isfinite(y) and y > 0:
            streak += 1
        else:
            break
    rec[f"{prefix}_fastest_consec_growth_q"] = float(streak)
    return rec


def _detail_rows(sym: str, axis: str, years: dict, ccy: str | None) -> list[dict]:
    import datetime as _dt
    rows = []
    if not years or next(iter(years)) < _dt.date.today().year - MAX_STALENESS_YEARS:
        return rows
    fys = list(years)[:DETAIL_YEARS]
    for i, fy in enumerate(fys):
        segs = years[fy]
        tot = sum(segs.values())
        prev = years.get(fys[i + 1]) if i + 1 < len(fys) else None
        for name, rev in sorted(segs.items(), key=lambda kv: -kv[1]):
            yoy = (rev / prev[name] - 1.0) if prev and prev.get(name, 0) > 0 else np.nan
            rows.append({"symbol": sym, "axis": axis, "fiscal_year": fy, "segment": name,
                         "revenue": rev, "currency": ccy, "share": rev / tot if tot else np.nan,
                         "yoy": yoy})
    return rows


def enrich_symbol(sym: str):
    prod = fc.get_json("revenue-product-segmentation", {"symbol": sym, "period": "annual"},
                       ttl=fc.TTL_SLOW)
    geo = fc.get_json("revenue-geographic-segmentation", {"symbol": sym, "period": "annual"},
                      ttl=fc.TTL_SLOW)
    py, gy = _clean_rows(prod), _clean_rows(geo)
    ccy = None
    for payload in (prod, geo):
        if payload:
            ccy = payload[0].get("reportedCurrency") or ccy
    rec = {"symbol": sym, "fmp_seg_schema": float(SCHEMA)}
    rec.update(_axis_summary(py, "fmp_seg"))
    rec.update(_axis_summary(gy, "fmp_geo"))
    for axis_years, pre in ((gy, "fmp_geo"), ):
        if axis_years and f"{pre}_count" in rec:
            fys = list(axis_years)
            def _em(fy):
                cur = axis_years[fy]; tot = sum(cur.values())
                return ((sum(v for k, v in cur.items() if _EM_PAT.search(k)) / tot,
                         sum(v for k, v in cur.items() if _CHINA_PAT.search(k)) / tot)
                        if tot > 0 else (np.nan, np.nan))
            em0, cn0 = _em(fys[0])
            rec["fmp_geo_em_share"], rec["fmp_geo_china_share"] = em0, cn0
            if len(fys) >= 2 and fys[0] - fys[1] == 1:
                em1, cn1 = _em(fys[1])
                rec["fmp_geo_em_share_delta"] = em0 - em1
                rec["fmp_geo_china_share_delta"] = cn0 - cn1
    # RECONCILIATION: segment total vs consolidated revenue for the SAME FY
    # (cached annual income statement). Shares are only trustworthy when the
    # axis sums to the company: < 0.8 = partial disclosure (only some lines
    # tagged), > 1.2 = overlapping hierarchy (a total AND its parts, or
    # gross-of-eliminations). The ratio is surfaced; the book and archetype
    # fills use it to decide what to trust.
    try:
        isa = fc.get_json("income-statement", {"symbol": sym, "period": "annual", "limit": 8},
                          ttl=fc.TTL_FUNDAMENTAL) or []
    except fc.FMPError:
        isa = []
    rev_fy = {}
    for r in isa:
        try:
            rev_fy[int(r.get("fiscalYear"))] = float(r.get("revenue"))
        except (TypeError, ValueError):
            continue
    for axis_years, pre in ((py, "fmp_seg"), (gy, "fmp_geo")):
        if axis_years and f"{pre}_count" in rec:
            fy0 = next(iter(axis_years))
            rv = rev_fy.get(fy0)
            if rv and rv > 0:
                rec[f"{pre}_coverage"] = sum(axis_years[fy0].values()) / rv
    # QUARTERLY momentum (only for names with a current annual axis)
    qdetail = []
    for axis, ep, years, pre in (("product", "revenue-product-segmentation", py, "fmp_seg"),
                                 ("geographic", "revenue-geographic-segmentation", gy, "fmp_geo")):
        if f"{pre}_count" not in rec:
            continue
        try:
            qp = fc.get_json(ep, {"symbol": sym, "period": "quarter"}, ttl=fc.TTL_SLOW)
        except fc.FMPError:
            qp = None
        q = _quarter_rows(qp)
        rec.update(_quarter_momentum(q, rec.get(f"{pre}_fastest_name"), pre))
        for d, segs in q[:QDETAIL_QUARTERS]:
            tot = sum(segs.values())
            for name, v in segs.items():
                qdetail.append({"symbol": sym, "axis": axis, "date": d.isoformat(), "segment": name,
                                "revenue": v, "currency": ccy, "share": v / tot if tot else np.nan})
    detail = _detail_rows(sym, "product", py, ccy) + _detail_rows(sym, "geographic", gy, ccy)
    return rec, detail, qdetail


def _append(path: str, rows: list[dict], dedupe_on=None):
    if not rows:
        return
    new = pd.DataFrame(rows)
    if os.path.exists(path):
        old = pd.read_csv(path, low_memory=False)
        both = pd.concat([old, new], ignore_index=True)
        if dedupe_on:
            both = both.drop_duplicates(dedupe_on, keep="last")
    else:
        both = new
    tmp = path + ".tmp"
    both.to_csv(tmp, index=False)
    os.replace(tmp, path)


def ordered_universe(relevant: str = "archetype_tags.csv") -> list[str]:
    """Whole universe, most archetype-relevant names first (useful partial books)."""
    t = pd.read_csv(relevant, usecols=lambda c: c in {"symbol", "archetype_count"},
                    low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    t["archetype_count"] = pd.to_numeric(t.get("archetype_count"), errors="coerce").fillna(0)
    return t.sort_values("archetype_count", ascending=False)["symbol"].tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--checkpoint-every", type=int, default=200)
    ap.add_argument("--gc-max-mb", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    syms = ordered_universe()
    if args.max:
        syms = syms[: args.max]
    done = set()
    if os.path.exists(OUT):
        _d = pd.read_csv(OUT, low_memory=False)
        if "fmp_seg_schema" in _d.columns:
            done = set(_d.loc[pd.to_numeric(_d["fmp_seg_schema"], errors="coerce") == SCHEMA,
                              "symbol"].astype(str))
    if not done:
        # fresh schema: detail files are rebuilt from scratch alongside
        for pth in (OUT_DETAIL, OUT_QDETAIL):
            if os.path.exists(pth):
                os.remove(pth)
    todo = [s for s in syms if s not in done]
    print(f"segments: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)

    import time
    from concurrent.futures import ThreadPoolExecutor

    def _one(sym):
        for attempt in range(12):   # rate limit = wait and retry, never a hole
            try:
                return enrich_symbol(sym)
            except fc.FMPError as exc:
                if "Limit Reach" in str(exc) or "429" in str(exc):
                    time.sleep(30 * (attempt + 1))
                    continue
                return {"symbol": sym, "fmp_seg_schema": float(SCHEMA)}, [], []
        raise fc.FMPError(f"{sym}: still rate limited")

    step = args.checkpoint_every
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        for i in range(0, len(todo), step):
            recs, det, qdet = [], [], []
            for r, d, q in ex.map(_one, todo[i:i + step]):
                recs.append(r); det.extend(d); qdet.extend(q)
            _append(OUT, recs, "symbol"); _append(OUT_DETAIL, det); _append(OUT_QDETAIL, qdet)
            st = fc.cache_stats()
            print(f"  segments {min(i + step, len(todo))}/{len(todo)} | hit_rate={st['hit_rate']} "
                  f"| cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    n = len(pd.read_csv(OUT)) if os.path.exists(OUT) else 0
    print(f"\nwrote {OUT}: {n} rows", flush=True)


if __name__ == "__main__":
    main()
