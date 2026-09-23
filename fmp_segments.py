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
DETAIL_YEARS = 4

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


def _axis_summary(years: dict, prefix: str) -> dict:
    rec = {}
    if not years:
        return rec
    fys = list(years)
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
    if len(fys) >= 2:
        prev = years[fys[1]]
        ptot = sum(prev.values())
        # growth only for segments present both years with a material prior
        # base (>=5% of the prior total) — tiny bases produce meaningless %.
        yoys = {k: cur[k] / prev[k] - 1.0 for k in cur
                if k in prev and prev[k] > 0 and ptot > 0 and prev[k] / ptot >= 0.05}
        if yoys:
            fast = max(yoys, key=yoys.get)
            rec[f"{prefix}_fastest_name"] = fast
            rec[f"{prefix}_fastest_yoy"] = yoys[fast]
            rec[f"{prefix}_fastest_share"] = shares.get(fast, np.nan)
            rec[f"{prefix}_fastest_share_delta"] = shares.get(fast, np.nan) - prev[fast] / ptot
            if len(yoys) >= 2:
                rec[f"{prefix}_growth_dispersion"] = float(np.std(list(yoys.values())))
        # whole-company growth implied by the segment sum (cross-check only)
        if ptot > 0:
            rec[f"{prefix}_total_yoy"] = tot / ptot - 1.0
    return rec


def _detail_rows(sym: str, axis: str, years: dict, ccy: str | None) -> list[dict]:
    rows = []
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
    rec = {"symbol": sym}
    rec.update(_axis_summary(py, "fmp_seg"))
    rec.update(_axis_summary(gy, "fmp_geo"))
    if gy:
        cur = gy[next(iter(gy))]
        tot = sum(cur.values())
        if tot > 0:
            rec["fmp_geo_em_share"] = sum(v for k, v in cur.items() if _EM_PAT.search(k)) / tot
            rec["fmp_geo_china_share"] = sum(v for k, v in cur.items() if _CHINA_PAT.search(k)) / tot
    detail = _detail_rows(sym, "product", py, ccy) + _detail_rows(sym, "geographic", gy, ccy)
    return rec, detail


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
    ap.add_argument("--gc-max-mb", type=int, default=2000)
    args = ap.parse_args()
    syms = ordered_universe()
    if args.max:
        syms = syms[: args.max]
    done = set()
    if os.path.exists(OUT):
        done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str))
    todo = [s for s in syms if s not in done]
    print(f"segments: {len(syms)} symbols, {len(done)} done, {len(todo)} to fetch", flush=True)
    recs, det = [], []
    for i, sym in enumerate(todo, 1):
        try:
            r, d = enrich_symbol(sym)
            recs.append(r); det.extend(d)
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                print(f"  rate limited at {i}; checkpointing", flush=True)
                break
            recs.append({"symbol": sym})
        if i % args.checkpoint_every == 0:
            _append(OUT, recs, "symbol"); _append(OUT_DETAIL, det); recs, det = [], []
            st = fc.cache_stats()
            print(f"  segments {i}/{len(todo)} | hit_rate={st['hit_rate']} | cache {st['disk_mb']}MB", flush=True)
            if args.gc_max_mb:
                fc.cache_gc(args.gc_max_mb * 1_048_576)
    _append(OUT, recs, "symbol"); _append(OUT_DETAIL, det)
    n = len(pd.read_csv(OUT)) if os.path.exists(OUT) else 0
    print(f"\nwrote {OUT}: {n} rows", flush=True)


if __name__ == "__main__":
    main()
