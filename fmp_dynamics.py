"""Per-symbol DYNAMIC (multi-period) enrichment from FMP -> fmp_dynamics.csv.

The dynamic archetypes (inflection, step-change, streak, "unrerated coiled
spring", reinvestment acceleration, forward-crossing) are today driven by
noisy Yahoo sequential proxies (`*_qoq_ttm`, `*_seq`) and US-only EDGAR
streaks. FMP's clean multi-period statements let us compute the real
trajectories — first derivative (growth), second derivative (acceleration),
streak length, incremental margin, multiple-vs-fundamental divergence, and
FORWARD estimate crossings — for the global universe.

Everything here is `fmp_dyn_`-prefixed and merged as a SECONDARY, source-
tagged overlay, exactly like fmp_enrichment.csv. Nothing overwrites an
EDGAR-primary value; the archetype layer surfaces these as confirming
signals, never as vetoes.

Inputs per symbol (4 cached calls):
  income-statement  period=quarter limit=13   levels for streaks/accel/incr-margin/first-positive
  income-statement  period=annual  limit=4    revenue for the EV/sales path
  enterprise-values period=annual  limit=4    EV path for the re-rating measure
  analyst-estimates period=annual  limit=4    forward EBIT/EPS/revenue crossings

The pass checkpoints to CSV every N symbols, so a long global run is
resumable and a limit/timeout never loses completed work.
"""
from __future__ import annotations

import argparse
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_dynamics.csv"


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _yoy(series, i, lag=4):
    """YoY at position i (newest=0) vs i+lag; None if unavailable/degenerate."""
    if i + lag >= len(series):
        return None
    now, then = series[i], series[i + lag]
    if not (math.isfinite(now) and math.isfinite(then)) or then == 0:
        return None
    return now / abs(then) - 1.0 if then > 0 else None


def _quarterly_pack(q: list) -> dict:
    """Streaks, acceleration, incremental margin and inflection from quarters."""
    if not q or len(q) < 6:
        return {}
    q = sorted(q, key=lambda r: r.get("date", ""), reverse=True)  # newest first
    rev = [_f(r.get("revenue")) for r in q]
    ebitda = [_f(r.get("ebitda")) for r in q]
    ebit = [_f(r.get("operatingIncome")) for r in q]
    ni = [_f(r.get("netIncome")) for r in q]
    gp = [_f(r.get("grossProfit")) for r in q]

    out: dict = {"fmp_dyn_quarters": float(len(q))}

    # YoY series for revenue and NI (newest first)
    rev_yoy = [_yoy(rev, i) for i in range(len(rev))]
    ni_yoy = [_yoy(ni, i) for i in range(len(ni))]

    # streak of consecutive positive YoY quarters (from newest)
    def _streak(yoy):
        n = 0
        for v in yoy:
            if v is None:
                break
            if v > 0:
                n += 1
            else:
                break
        return float(n)
    out["fmp_dyn_rev_streak_q"] = _streak(rev_yoy)
    out["fmp_dyn_ni_streak_q"] = _streak(ni_yoy)

    # acceleration: latest YoY minus the prior quarter's YoY (2nd derivative)
    if rev_yoy[0] is not None and len(rev_yoy) > 1 and rev_yoy[1] is not None:
        out["fmp_dyn_rev_accel"] = rev_yoy[0] - rev_yoy[1]
    if rev_yoy[0] is not None:
        out["fmp_dyn_rev_yoy"] = rev_yoy[0]

    # positive-YoY share over the last 8 quarters (durability)
    window = [v for v in rev_yoy[:8] if v is not None]
    if window:
        out["fmp_dyn_rev_yoy_pos_share"] = float(np.mean([1.0 if v > 0 else 0.0 for v in window]))

    # incremental operating margin YoY: ΔEBIT / ΔRevenue (operating leverage)
    if len(rev) > 4 and math.isfinite(rev[0]) and math.isfinite(rev[4]) and rev[0] > rev[4] \
       and math.isfinite(ebit[0]) and math.isfinite(ebit[4]):
        d_rev = rev[0] - rev[4]
        if d_rev > 0:
            im = (ebit[0] - ebit[4]) / d_rev
            if -5 < im < 5:
                out["fmp_dyn_incremental_ebit_margin"] = im

    # inflection: a metric that was <=0 in the prior year and is >0 now
    def _turned_positive(series):
        if len(series) < 5:
            return 0
        recent = series[0]
        prior_year = [v for v in series[1:5] if math.isfinite(v)]
        if not math.isfinite(recent) or not prior_year:
            return 0
        return 1 if (recent > 0 and min(prior_year) <= 0) else 0
    out["fmp_dyn_ebitda_turned_positive"] = float(_turned_positive(ebitda))
    out["fmp_dyn_opinc_turned_positive"] = float(_turned_positive(ebit))
    out["fmp_dyn_ni_turned_positive"] = float(_turned_positive(ni))

    # gross-margin trend: latest GM minus GM four quarters ago (pts)
    if math.isfinite(gp[0]) and math.isfinite(rev[0]) and rev[0] > 0 and len(rev) > 4 \
       and math.isfinite(gp[4]) and math.isfinite(rev[4]) and rev[4] > 0:
        out["fmp_dyn_gross_margin_trend"] = gp[0] / rev[0] - gp[4] / rev[4]
    return out


def _rerating_pack(annual_is: list, ev: list) -> dict:
    """Multiple-vs-fundamental divergence — the 'unrerated coiled spring'."""
    if not annual_is or not ev or len(annual_is) < 3 or len(ev) < 3:
        return {}
    a = sorted(annual_is, key=lambda r: r.get("date", ""), reverse=True)
    e = sorted(ev, key=lambda r: r.get("date", ""), reverse=True)
    rev = {r.get("date", "")[:4]: _f(r.get("revenue")) for r in a}
    evmap = {r.get("date", "")[:4]: _f(r.get("enterpriseValue")) for r in e}
    yrs = sorted(set(rev) & set(evmap), reverse=True)
    if len(yrs) < 3:
        return {}
    y0, yN = yrs[0], yrs[min(3, len(yrs) - 1)]
    r0, rN = rev.get(y0), rev.get(yN)
    ev0, evN = evmap.get(y0), evmap.get(yN)
    out: dict = {}
    # Revenue CAGR needs both revenue levels positive; a fractional power of a
    # negative base is complex, so every ratio raised to 1/span is guarded > 0.
    if all(math.isfinite(x) for x in (r0, rN)) and r0 > 0 and rN > 0:
        span = max(1, int(y0) - int(yN))
        rev_cagr = (r0 / rN) ** (1.0 / span) - 1.0
        out["fmp_dyn_rev_cagr_3y"] = rev_cagr
        # EV/sales change only where BOTH enterprise values are positive
        # (a negative EV = net cash > mcap; its "multiple" is not comparable).
        if all(math.isfinite(x) for x in (ev0, evN)) and ev0 > 0 and evN > 0:
            evs0, evsN = ev0 / r0, evN / rN
            if evs0 > 0 and evsN > 0:
                evs_chg = (evs0 / evsN) ** (1.0 / span) - 1.0
                out["fmp_dyn_ev_sales_change_3y"] = evs_chg
                # positive gap = revenue compounded but the multiple did not follow
                out["fmp_dyn_unrerated_gap"] = rev_cagr - evs_chg
    return out


def _forward_pack(est: list, ttm_rev: float | None = None) -> dict:
    """Forward EBIT/EPS crossing and next-year growth from consensus estimates."""
    if not est:
        return {}
    e = sorted(est, key=lambda r: r.get("date", ""))  # ascending (forward)
    ebit = [_f(r.get("ebitAvg")) for r in e]
    eps = [_f(r.get("epsAvg")) for r in e]
    rev = [_f(r.get("revenueAvg")) for r in e]
    out: dict = {}

    def _crosses(series):
        vals = [v for v in series if math.isfinite(v)]
        if len(vals) < 2:
            return 0
        return 1 if (vals[0] <= 0 and any(v > 0 for v in vals[1:])) else 0
    out["fmp_dyn_fwd_ebit_crossing"] = float(_crosses(ebit))
    out["fmp_dyn_fwd_eps_crossing"] = float(_crosses(eps))

    fwd_rev = [v for v in rev if math.isfinite(v)]
    if len(fwd_rev) >= 2 and fwd_rev[0] > 0:
        out["fmp_dyn_fwd_rev_growth_1y"] = fwd_rev[1] / fwd_rev[0] - 1.0
    return out


def enrich_symbol(sym: str) -> dict:
    rec: dict = {"symbol": sym}
    q = fc.get_json("income-statement", {"symbol": sym, "period": "quarter", "limit": 13},
                    ttl=fc.TTL_FUNDAMENTAL)
    a = fc.get_json("income-statement", {"symbol": sym, "period": "annual", "limit": 4},
                    ttl=fc.TTL_FUNDAMENTAL)
    ev = fc.get_json("enterprise-values", {"symbol": sym, "period": "annual", "limit": 4},
                     ttl=fc.TTL_FUNDAMENTAL)
    est = fc.get_json("analyst-estimates", {"symbol": sym, "period": "annual", "limit": 4},
                      ttl=fc.TTL_ESTIMATE)
    rec.update(_quarterly_pack(q or []))
    rec.update(_rerating_pack(a or [], ev or []))
    rec.update(_forward_pack(est or []))

    # "Asleep at the wheel", forward edition: the consensus is not just wrong in
    # the PAST (beats), it is lowballing the FUTURE — forward revenue growth
    # sits well below the trajectory the company is actually delivering. A
    # positive gap = analysts still underestimate. Pair with a high historical
    # beat rate (fmp_earnings_beat_rate) for the full "market is asleep" thesis.
    ty = rec.get("fmp_dyn_rev_yoy"); fg = rec.get("fmp_dyn_fwd_rev_growth_1y")
    if ty is not None and fg is not None and math.isfinite(ty) and math.isfinite(fg):
        rec["fmp_dyn_fwd_underestimate_gap"] = ty - fg
    # forward EBIT margin trajectory vs trailing: is the consensus modelling the
    # operating-leverage the quarters already show? (guidance too conservative)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--relevant", default="archetype_tags.csv")
    ap.add_argument("--scope", choices=["dynamic", "firers", "all"], default="dynamic")
    ap.add_argument("--max", type=int, default=0, help="0 = no cap")
    ap.add_argument("--checkpoint-every", type=int, default=200)
    ap.add_argument("--gc-max-mb", type=int, default=300)
    args = ap.parse_args()

    t = pd.read_csv(args.relevant, low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    us = ~t["symbol"].str.contains(r"\.", regex=True)
    if args.scope == "dynamic":
        dyn_cols = [c for c in t.columns if c.startswith("arch_") and any(
            k in c for k in ("inflect", "wolf", "liger", "reinvest", "roic", "evsales",
                             "tenbagger", "asleep", "analyst", "growth", "leverage",
                             "streak", "kpi", "regime", "capital_light", "scaler",
                             "deleveraging", "order_conversion", "baron", "pre_scale",
                             "compounding_deployer", "forced_seller", "detonation"))]
        # Full universe of dynamic-archetype firers, US and non-US. FMP covers
        # many international exchanges; symbols it does not carry negative-cache
        # cheaply (one call, then skipped), so the run is resumable and the
        # misses cost little.
        mask = (t[dyn_cols].fillna(0).astype(float).sum(axis=1) > 0) if dyn_cols else pd.Series(True, index=t.index)
    elif args.scope == "firers":
        mask = t.get("archetype_count", pd.Series(0, index=t.index)).fillna(0) >= 1
    else:
        mask = pd.Series(True, index=t.index)
    syms = t.loc[mask, "symbol"].tolist()
    if args.max:
        syms = syms[: args.max]
    print(f"dynamics scope={args.scope}: {len(syms)} symbols", flush=True)

    gc_bytes = args.gc_max_mb * 1_048_576 if args.gc_max_mb else None
    done: set[str] = set()
    if os.path.exists(OUT):
        try:
            done = set(pd.read_csv(OUT, usecols=["symbol"])["symbol"].astype(str))
        except Exception:
            done = set()
    rows: list[dict] = []
    todo = [s for s in syms if s not in done]
    print(f"  {len(done)} already done, {len(todo)} to fetch", flush=True)
    for i, sym in enumerate(todo, 1):
        try:
            rows.append(enrich_symbol(sym))
        except fc.FMPError as exc:
            if "Limit Reach" in str(exc) or "429" in str(exc):
                print(f"  rate limited at {i}; checkpointing", flush=True)
                break
            rows.append({"symbol": sym})
        if i % args.checkpoint_every == 0:
            _flush(rows)
            rows = []
            st = fc.cache_stats()
            print(f"  dynamics {i}/{len(todo)} | hit_rate={st['hit_rate']} "
                  f"| cache {st['disk_mb']}MB", flush=True)
            if gc_bytes:
                fc.cache_gc(gc_bytes)
    _flush(rows)
    fin = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    print(f"\nwrote {OUT}: {len(fin)} rows, {len(fin.columns)} cols", flush=True)


def _flush(rows: list[dict]) -> None:
    if not rows:
        return
    new = pd.DataFrame(rows)
    if os.path.exists(OUT):
        old = pd.read_csv(OUT, low_memory=False)
        both = pd.concat([old, new], ignore_index=True).drop_duplicates("symbol", keep="last")
    else:
        both = new
    tmp = OUT + ".tmp"
    both.to_csv(tmp, index=False)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
