"""Build ``fmp_enrichment.csv`` — a per-symbol, source-tagged FMP overlay.

Provenance contract (the reason this is a separate file, not an edit to the
master): FMP is a SECONDARY source. Every column it produces is prefixed
``fmp_`` and merged into ``archetype_tags.compute`` the same optional way as
every other enrichment CSV. Nothing here overwrites an EDGAR-primary value;
the archetype layer decides, narrowly and auditably, where an ``fmp_`` column
may fill a NaN or add a new signal. Forensic / NNWC inputs are never fed from
FMP.

What it produces
  Universe-wide (cheap bulk, one stream per part):
    fmp_piotroski, fmp_altman_z                    (scores-bulk)
    fmp_roic, fmp_ebitda_margin, fmp_gross_margin,
    fmp_fcf_yield, fmp_net_debt_ebitda, fmp_ev_ebitda,
    fmp_pb, fmp_dividend_yield                      (ratios/key-metrics TTM bulk)

  Per-symbol for the archetype-relevant US set (revealed-preference / SEC):
    fmp_exec_comp_total, fmp_exec_comp_year         (governance exec comp)
    fmp_insider_buy_usd_12m, fmp_insider_sell_usd_12m,
    fmp_insider_net_usd_12m, fmp_insider_buyers_12m (Form-4 open-market)
    fmp_insider_alignment_ratio                     (buy$ / exec comp; >5x = the tell)
    fmp_earnings_beat_rate, fmp_avg_earnings_surprise,
    fmp_earnings_surprise_cv, fmp_earnings_n        (actual vs estimate)

The per-symbol pass checkpoints to CSV as it goes, so a long run is
resumable and a limit/timeout never loses completed work.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os

import numpy as np
import pandas as pd

import fmp_client as fc

OUT = "fmp_enrichment.csv"
_TODAY = dt.date.today()

# ---- field maps for the TTM bulk fills (FMP header -> our fmp_ column) ----
_RATIOS_MAP = {
    "ebitdaMarginTTM": "fmp_ebitda_margin",
    "grossProfitMarginTTM": "fmp_gross_margin",
    "priceToBookRatioTTM": "fmp_pb",
    "dividendYieldTTM": "fmp_dividend_yield",
}
_KEYM_MAP = {
    "returnOnInvestedCapitalTTM": "fmp_roic",
    "freeCashFlowYieldTTM": "fmp_fcf_yield",
    "netDebtToEBITDATTM": "fmp_net_debt_ebitda",
    "evToEBITDATTM": "fmp_ev_ebitda",
}


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def load_universe_symbols(path: str = "asymmetry_global.csv") -> pd.Index:
    return pd.Index(pd.read_csv(path, usecols=["symbol"])["symbol"].astype(str).unique())


# --------------------------------------------------------------------------
# Universe-wide bulk enrichment (streamed; the 40-70 MB payload never lands)
# --------------------------------------------------------------------------
def enrich_bulk(symbols: set[str], max_parts: int = 20) -> pd.DataFrame:
    scores: dict[str, dict] = {}
    ratios: dict[str, dict] = {}
    keym: dict[str, dict] = {}

    def _run(endpoint, sink, field_map=None, raw=None):
        # These /stable bulk endpoints ignore ``part`` and return the whole
        # file every call, so we stop as soon as a part yields no symbol we
        # have not already seen (guards against refetching a 40-70 MB payload
        # in a loop). ``seen`` tracks ALL symbols, not just universe matches,
        # so genuine pagination (new tickers, none in our universe) would not
        # be mistaken for a duplicate.
        seen: set[str] = set()
        for part in range(max_parts):
            before_seen = len(seen)

            def cb(row, _sink=sink, _seen=seen):
                s = row.get("symbol")
                if s is not None:
                    _seen.add(s)
                if s not in symbols:
                    return
                if raw:
                    _sink[s] = {out: _f(row.get(src)) for src, out in raw.items()}
                else:
                    _sink[s] = row
            n = fc.stream_bulk_csv(endpoint, cb, params={"part": part})
            new_syms = len(seen) - before_seen
            print(f"  {endpoint} part {part}: {n} rows, +{new_syms} new symbols, "
                  f"matched {len(sink)}", flush=True)
            if n == 0 or new_syms == 0:
                break

    print("bulk: scores-bulk (Piotroski / Altman Z)")
    _run("scores-bulk", scores)
    print("bulk: ratios-ttm-bulk")
    _run("ratios-ttm-bulk", ratios, raw=_RATIOS_MAP)
    print("bulk: key-metrics-ttm-bulk")
    _run("key-metrics-ttm-bulk", keym, raw=_KEYM_MAP)

    rows = []
    for s in set(scores) | set(ratios) | set(keym):
        rec = {"symbol": s}
        sc = scores.get(s)
        if sc:
            rec["fmp_piotroski"] = _f(sc.get("piotroskiScore"))
            rec["fmp_altman_z"] = _f(sc.get("altmanZScore"))
        rec.update(ratios.get(s, {}))
        rec.update(keym.get(s, {}))
        rows.append(rec)
    df = pd.DataFrame(rows)
    print(f"bulk: {len(df)} symbols enriched from bulk endpoints")
    return df


# --------------------------------------------------------------------------
# Per-symbol: executive comp + insider trading -> alignment ratio
# --------------------------------------------------------------------------
_BUY_TYPES = ("P-Purchase",)   # open-market purchase = revealed-preference cash in
# excluded on purpose: M-Exempt (option exercise), A-Award/grant, G-Gift,
# C-Conversion — none is a cash conviction buy.
# NOTE on "outside regular market hours": Form 4 (and thus FMP's insider
# feed) records only the transaction DATE, price, share count and code — no
# intraday timestamp and no regular-vs-extended-hours flag exists in the
# data. So we cannot filter by session; "open-market purchase" (code P) is
# the strongest revealed-preference signal the filings actually support.


def _exec_comp_total(data) -> tuple[float, float]:
    """Most-recent-year total NEO compensation (sum across named execs)."""
    if not data:
        return np.nan, np.nan
    by_year: dict[int, float] = {}
    for r in data:
        y = _f(r.get("year")); t = _f(r.get("total"))
        if math.isfinite(y) and math.isfinite(t):
            by_year[int(y)] = by_year.get(int(y), 0.0) + t
    if not by_year:
        return np.nan, np.nan
    yr = max(by_year)
    return by_year[yr], float(yr)


def _insider_flows(data, months: int = 12) -> dict:
    """Trailing-window open-market buy/sell dollars and distinct buyers."""
    if not data:
        return {}
    cutoff = _TODAY - dt.timedelta(days=int(months * 30.44))
    buy = sell = 0.0
    buyers: set[str] = set()
    for r in data:
        d = str(r.get("transactionDate") or "")[:10]
        try:
            when = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if when < cutoff:
            continue
        ttype = str(r.get("transactionType") or "")
        val = _f(r.get("securitiesTransacted")) * _f(r.get("price"))
        if not math.isfinite(val):
            continue
        ad = str(r.get("acquisitionOrDisposition") or "")
        if ttype in _BUY_TYPES and ad == "A":
            buy += val
            buyers.add(str(r.get("reportingName") or ""))
        elif ttype.startswith("S-") and ad == "D":
            sell += val
    return {
        "fmp_insider_buy_usd_12m": buy,
        "fmp_insider_sell_usd_12m": sell,
        "fmp_insider_net_usd_12m": buy - sell,
        "fmp_insider_buyers_12m": float(len(buyers)),
    }


def enrich_alignment(symbols: list[str], gc_max_bytes: int | None) -> pd.DataFrame:
    rows = []
    for i, sym in enumerate(symbols, 1):
        comp = fc.get_json("governance-executive-compensation", {"symbol": sym}, ttl=fc.TTL_SLOW)
        ins = fc.get_json("insider-trading/search",
                          {"symbol": sym, "page": 0, "limit": 100}, ttl=fc.TTL_SLOW)
        comp_total, comp_year = _exec_comp_total(comp)
        rec = {"symbol": sym, "fmp_exec_comp_total": comp_total, "fmp_exec_comp_year": comp_year}
        rec.update(_insider_flows(ins))
        buy = rec.get("fmp_insider_buy_usd_12m", np.nan)
        if math.isfinite(comp_total) and comp_total > 0 and math.isfinite(buy):
            rec["fmp_insider_alignment_ratio"] = buy / comp_total
        rows.append(rec)
        if i % 250 == 0:
            st = fc.cache_stats()
            print(f"  alignment {i}/{len(symbols)} | hit_rate={st['hit_rate']} "
                  f"| cache {st['disk_mb']}MB", flush=True)
            if gc_max_bytes:
                fc.cache_gc(gc_max_bytes)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Per-symbol: earnings actual vs estimate -> beat rate / surprise / variability
# --------------------------------------------------------------------------
def _earnings_stats(data, max_q: int = 12) -> dict:
    """Beat rate, mean surprise, and surprise dispersion over recent quarters.

    Each quarter's surprise ``(actual - estimate) / |estimate|`` is winsorized
    to +/-100% before aggregating. Raw, a single quarter with an estimate near
    zero produces a surprise of tens or hundreds (e.g. an unclipped mean of
    -46 or a dispersion of 69), which would swamp the average and make the
    dispersion meaningless. Clipping keeps the mean on the same fractional
    scale as our native ``avg_earnings_surprise`` (whose gates sit at 0.02 /
    0.10) and bounds the dispersion to [0, 1] so a variability threshold is
    interpretable. Beat rate is computed on the raw sign, unaffected by the cap.
    """
    if not data:
        return {}
    pairs = []
    for r in data:
        a = _f(r.get("epsActual")); e = _f(r.get("epsEstimated"))
        if math.isfinite(a) and math.isfinite(e) and e != 0:
            pairs.append((a, e))
        if len(pairs) >= max_q:
            break
    if len(pairs) < 4:
        return {"fmp_earnings_n": float(len(pairs))}
    surprises = [max(-1.0, min(1.0, (a - e) / abs(e))) for a, e in pairs]
    beats = [1.0 if a > e else 0.0 for a, e in pairs]
    arr = np.array(surprises)
    return {
        "fmp_earnings_beat_rate": float(np.mean(beats)),
        "fmp_avg_earnings_surprise": float(np.mean(arr)),
        "fmp_earnings_surprise_cv": float(np.std(arr)),
        "fmp_earnings_n": float(len(pairs)),
    }


def enrich_earnings(symbols: list[str], gc_max_bytes: int | None) -> pd.DataFrame:
    rows = []
    for i, sym in enumerate(symbols, 1):
        e = fc.get_json("earnings", {"symbol": sym, "limit": 16}, ttl=fc.TTL_ESTIMATE)
        rec = {"symbol": sym}
        rec.update(_earnings_stats(e))
        rows.append(rec)
        if i % 500 == 0:
            st = fc.cache_stats()
            print(f"  earnings {i}/{len(symbols)} | hit_rate={st['hit_rate']}", flush=True)
            if gc_max_bytes:
                fc.cache_gc(gc_max_bytes)
    return pd.DataFrame(rows)


def _merge_on_symbol(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame(columns=["symbol"])
    out = frames[0]
    for f in frames[1:]:
        out = out.merge(f, on="symbol", how="outer")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--relevant", default="archetype_tags.csv",
                    help="source of the archetype-relevant symbol set")
    ap.add_argument("--per-symbol-scope", choices=["value", "firers", "none"], default="firers")
    ap.add_argument("--max-per-symbol", type=int, default=0, help="0 = no cap")
    ap.add_argument("--gc-max-mb", type=int, default=300)
    ap.add_argument("--skip-bulk", action="store_true")
    args = ap.parse_args()

    gc_bytes = args.gc_max_mb * 1_048_576 if args.gc_max_mb else None
    universe = set(load_universe_symbols())
    print(f"universe: {len(universe)} symbols")

    # ---- pick the per-symbol set (US-style tickers only; SEC endpoints) ----
    t = pd.read_csv(args.relevant, low_memory=False)
    t["symbol"] = t["symbol"].astype(str)
    us = ~t["symbol"].str.contains(r"\.", regex=True)
    if args.per_symbol_scope == "value":
        val_cols = [c for c in ["arch_cluseau_realizable_book", "arch_cluseau_buyback_accel",
                                "cash_squatter_flag", "arch_tangible_value",
                                "arch_cannibal_at_discount", "arch_net_net"] if c in t.columns]
        mask = us & (t[val_cols].fillna(0).astype(float).sum(axis=1) > 0)
    elif args.per_symbol_scope == "firers":
        ac = t.get("archetype_count", pd.Series(0, index=t.index)).fillna(0)
        mask = us & (ac >= 1)
    else:
        mask = pd.Series(False, index=t.index)
    per_syms = t.loc[mask, "symbol"].tolist()
    if args.max_per_symbol:
        per_syms = per_syms[: args.max_per_symbol]
    print(f"per-symbol scope={args.per_symbol_scope}: {len(per_syms)} US symbols")

    frames = []
    if not args.skip_bulk:
        frames.append(enrich_bulk(universe))
    if per_syms:
        frames.append(enrich_alignment(per_syms, gc_bytes))
        frames.append(enrich_earnings(per_syms, gc_bytes))

    out = _merge_on_symbol(frames)
    out.to_csv(OUT, index=False)
    st = fc.cache_stats()
    print(f"\nwrote {OUT}: {len(out)} rows, {len(out.columns)} cols")
    print(f"cache: {st['disk_mb']}MB / {st['entries']} entries | "
          f"hit_rate={st['hit_rate']} writes={st['write']} evicts={st['evict']}")


if __name__ == "__main__":
    main()
