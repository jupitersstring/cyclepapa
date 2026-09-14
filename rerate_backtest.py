"""Historical re-rate event study -- did the catalysts the engine keys on
actually re-rate in the past?

rerate_catalysts.py scores names for spin-off / asset-sale / sale-of-company
/ strategic-review catalysts TODAY. This module looks BACKWARD: it finds the
same catalysts ANNOUNCED in a historical window (via EDGAR full-text
search), pulls each name's price around the announcement, and measures the
realized forward re-rate at +3 / +6 / +12 months, both absolute and in
excess of SPY. Aggregated by catalyst type, that answers the calibration
question directly: which corporate actions re-rated, by how much, and how
reliably -- so the engine's weights reflect what history paid, not a prior.

Method:
  * EVENTS -- one EFTS exact-phrase query per catalyst signature, restricted
    to a past window with >= 12 months of runway to now, gives
    {ticker, cik, date, catalyst}.
  * PRICES -- Yahoo chart API, monthly closes around each event; the close
    nearest the event date is t0, then t0+3/+6/+12 months.
  * OUTCOME -- forward return at each horizon, and excess vs SPY over the
    same span. Aggregated per catalyst type: n, median, hit-rate (>0),
    median excess.

Output: rerate_backtest.json {window, by_type, events}.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "rerate_backtest.json"

# catalyst signature -> (phrase, forms). Announcement-style language so t0 is
# near the catalyst reveal.
CATALYSTS = [
    ("SPINOFF", "completed the separation", "8-K"),
    ("SPINOFF", "completed the spin-off", "8-K"),
    ("SPINOFF", "plan to separate", "8-K"),
    ("ASSET_SALE", "completed the sale of", "8-K"),
    ("ASSET_SALE", "definitive agreement to sell", "8-K"),
    ("SALE_OF_COMPANY", "agreement and plan of merger", "8-K"),
    ("STRATEGIC_REVIEW", "review of strategic alternatives", "8-K"),
    ("STRATEGIC_REVIEW", "exploring strategic alternatives", "8-K"),
]

_DT = None
def _init_re():
    global _DT
    import re
    _DT = re.compile(r"\(([A-Z0-9][A-Z0-9.\-]{0,6})\)\s*\(CIK")


def efts(phrase, start, end, forms, cap=60):
    from recent import EFTS, _get, requests_quote
    url = (f"{EFTS}?dateRange=custom&startdt={start}&enddt={end}"
           f"&q={requests_quote(chr(34) + phrase + chr(34))}"
           f"&forms={requests_quote(forms)}")
    for _ in range(3):
        try:
            d = _get(url).json(); break
        except Exception:
            time.sleep(1.5); d = None
    if not d:
        return []
    out = []
    for h in (d.get("hits", {}).get("hits", []) or [])[:cap]:
        src = h.get("_source", {}) or {}
        tk = None
        for nm in (src.get("display_names") or []):
            m = _DT.search(nm)
            if m:
                tk = m.group(1); break
        if tk:
            out.append({"ticker": tk, "date": src.get("file_date")})
    return out


def chart_monthly(ticker, rng="5y"):
    """Monthly (timestamp, close) list from the Yahoo chart API."""
    u = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
         f"?range={rng}&interval=1mo")
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=25))
        r = d["chart"]["result"][0]
        ts = r["timestamp"]
        cl = r["indicators"]["quote"][0]["close"]
        return [(t, c) for t, c in zip(ts, cl) if c is not None]
    except Exception:
        return []


def _close_near(series, target_ts):
    """Close at the first bar on/after target_ts (or last before if none)."""
    after = [(t, c) for t, c in series if t >= target_ts]
    if after:
        return after[0][1]
    return series[-1][1] if series else None


def _fwd_return(series, t0_ts, months):
    base = _close_near(series, t0_ts)
    tgt_ts = t0_ts + months * 30 * 86400
    fwd = _close_near(series, tgt_ts)
    if base and fwd and base > 0:
        return fwd / base - 1.0
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2025-06-30")
    ap.add_argument("--cap", type=int, default=45)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()
    _init_re()

    # 1) discover events.
    events = {}   # (ticker,date,type) dedup
    for ctype, phrase, forms in CATALYSTS:
        hits = efts(phrase, args.start, args.end, forms, cap=args.cap)
        time.sleep(args.sleep)
        for h in hits:
            tk, dt = h["ticker"], h["date"]
            if not dt:
                continue
            key = (tk, ctype)
            if key not in events or dt < events[key]:   # earliest mention
                events[key] = dt
        print(f"  {ctype:<16} '{phrase}': {len(hits)} filings", flush=True)
    print(f"{len(events)} unique (ticker,catalyst) events", flush=True)

    # 2) SPY benchmark once.
    spy = chart_monthly("SPY", "5y")

    # 3) price each event.
    recs = []
    tickers = sorted({tk for (tk, _c) in events})
    px_cache = {}
    for i, tk in enumerate(tickers, 1):
        px_cache[tk] = chart_monthly(tk, "5y")
        time.sleep(args.sleep)
        if i % 25 == 0:
            print(f"  priced {i}/{len(tickers)}", flush=True)

    for (tk, ctype), dt in events.items():
        series = px_cache.get(tk) or []
        if not series:
            continue
        try:
            t0 = int(datetime.strptime(dt, "%Y-%m-%d")
                     .replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            continue
        r3, r6, r12 = (_fwd_return(series, t0, 3),
                       _fwd_return(series, t0, 6),
                       _fwd_return(series, t0, 12))
        s3, s6, s12 = (_fwd_return(spy, t0, 3),
                       _fwd_return(spy, t0, 6),
                       _fwd_return(spy, t0, 12))
        recs.append({
            "ticker": tk, "catalyst": ctype, "date": dt,
            "ret_3m": r3, "ret_6m": r6, "ret_12m": r12,
            "excess_12m": (r12 - s12) if (r12 is not None and s12 is not None) else None,
            "excess_6m": (r6 - s6) if (r6 is not None and s6 is not None) else None,
        })

    # 4) aggregate by catalyst type.
    def agg(rows, key):
        v = [r[key] for r in rows if r.get(key) is not None]
        if not v:
            return None
        return {"n": len(v), "median": round(statistics.median(v), 3),
                "mean": round(statistics.mean(v), 3),
                "hit_rate": round(sum(1 for x in v if x > 0) / len(v), 3)}

    by_type = {}
    for ctype in sorted({r["catalyst"] for r in recs}):
        rows = [r for r in recs if r["catalyst"] == ctype]
        by_type[ctype] = {
            "n_events": len(rows),
            "ret_6m": agg(rows, "ret_6m"),
            "ret_12m": agg(rows, "ret_12m"),
            "excess_12m": agg(rows, "excess_12m"),
        }
    overall = {
        "ret_12m": agg(recs, "ret_12m"),
        "excess_12m": agg(recs, "excess_12m"),
    }

    io_util.write_json(OUT, {
        "window": f"{args.start}..{args.end}",
        "n_events_priced": len(recs),
        "overall": overall,
        "by_type": by_type,
        "events": sorted(recs, key=lambda r: -(r.get("ret_12m") or -9)),
    })

    print(f"\nwrote {OUT} ({len(recs)} events priced, window "
          f"{args.start}..{args.end})")
    print(f"\n{'CATALYST':<18}{'N':>4}{'12m med':>9}{'hit':>6}{'12m xs':>9}")
    for ctype, v in sorted(by_type.items(),
                           key=lambda kv: -((kv[1]['ret_12m'] or {}).get('median') or -9)):
        r12 = v["ret_12m"] or {}; xs = v["excess_12m"] or {}
        print(f"{ctype:<18}{v['n_events']:>4}"
              f"{(r12.get('median') or 0)*100:>8.0f}%{(r12.get('hit_rate') or 0)*100:>5.0f}%"
              f"{(xs.get('median') or 0)*100:>8.0f}%")
    o = overall["ret_12m"] or {}
    print(f"{'OVERALL':<18}{o.get('n',0):>4}{(o.get('median') or 0)*100:>8.0f}%"
          f"{(o.get('hit_rate') or 0)*100:>5.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
