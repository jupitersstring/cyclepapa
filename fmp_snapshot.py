"""Point-in-time (PIT) snapshot of consensus estimates, coverage and float.

Estimate-revision momentum and coverage acceleration are NOT backfillable — they
require dated snapshots taken forward from today. This captures a compact daily
row per ticker so that, over time, we can compute:

    EPS/revenue/EBITDA consensus revision (today vs an N-day-old snapshot)
    analyst-coverage acceleration
    (and a proper historical float series)

Snapshots accumulate append-only in data/pit_snapshots/<YYYY-MM-DD>.csv.

Modes:
  --from-cache   build today's snapshot from the existing /tmp/fmp_cache (fast,
                 valid when the cache was fetched today) — used for snapshot #1
  (default)      fresh light fetch (analyst-estimates + grades + float + next
                 earnings estimate) for the panel — used by the daily Routine

`revision_panel()` reads the two most recent snapshots and returns per-ticker
revision momentum for the models to merge once >=2 snapshots exist.
"""
import os, sys, json, glob, time, urllib.parse, urllib.request
from datetime import datetime, timezone
import pandas as pd
import numpy as np

BASE = "https://financialmodelingprep.com/stable/"
KEYFILE = "/home/user/cyclepapa/.fmp_key"
CACHE = "/tmp/fmp_cache"
SNAPDIR = "/home/user/cyclepapa/data/pit_snapshots"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _key():
    return open(KEYFILE).read().strip()


def _get(endpoint, params, key, retries=3):
    params = dict(params); params["apikey"] = key
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(1.0 * (a + 1))
    return None


def _n(x):
    try:
        v = float(x); return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _grades_n(grades):
    g = (grades or [{}])
    g = g[0] if g else {}
    return sum(_n(g.get(k)) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))


def _row_from_parts(t, est, grades, flt, earnings):
    e0 = (est or [{}])[0] if est else {}
    up = [e for e in (earnings or []) if e.get("epsActual") is None and e.get("date")]
    nxt = sorted(up, key=lambda e: e["date"])[0] if up else {}
    return {
        "date": TODAY, "ticker": t,
        "est_rev_avg": _n(e0.get("revenueAvg")),
        "est_ebitda_avg": _n(e0.get("ebitdaAvg")),
        "est_ni_avg": _n(e0.get("netIncomeAvg")),
        "next_eps_est": _n(nxt.get("epsEstimated")),
        "next_rev_est": _n(nxt.get("revenueEstimated")),
        "n_analysts": _grades_n(grades),
        "float_shares": _n((flt or [{}])[0].get("floatShares") if flt else None),
    }


def build_from_cache():
    rows = []
    for f in glob.glob(os.path.join(CACHE, "*.json")):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        rows.append(_row_from_parts(d.get("symbol"), d.get("estimates"),
                                    d.get("grades"), d.get("float"), d.get("earnings")))
    return pd.DataFrame(rows)


def build_fetch(tickers, key):
    rows = []
    for i, t in enumerate(tickers):
        est = _get("analyst-estimates", {"symbol": t, "period": "annual", "limit": 1}, key)
        gr = _get("grades-consensus", {"symbol": t}, key)
        fl = _get("shares-float", {"symbol": t}, key)
        ea = _get("earnings", {"symbol": t, "limit": 4}, key)
        rows.append(_row_from_parts(t, est, gr, fl, ea))
        if (i + 1) % 100 == 0:
            print(f"  snapshot {i+1}/{len(tickers)}", file=sys.stderr)
        time.sleep(0.02)
    return pd.DataFrame(rows)


def revision_panel():
    """Revision momentum from the two most recent snapshots (empty if <2)."""
    snaps = sorted(glob.glob(os.path.join(SNAPDIR, "*.csv")))
    if len(snaps) < 2:
        return pd.DataFrame()
    cur = pd.read_csv(snaps[-1]); prev = pd.read_csv(snaps[-2])
    m = cur.merge(prev, on="ticker", suffixes=("", "_prev"))
    def rev(a, b):
        return (m[a] - m[b]) / m[b].abs().replace(0, np.nan)
    out = pd.DataFrame({"ticker": m["ticker"]})
    out["rev_rev_avg"] = rev("est_rev_avg", "est_rev_avg_prev")
    out["rev_ebitda_avg"] = rev("est_ebitda_avg", "est_ebitda_avg_prev")
    out["rev_ni_avg"] = rev("est_ni_avg", "est_ni_avg_prev")
    out["coverage_delta"] = m["n_analysts"] - m["n_analysts_prev"]
    return out


def main():
    os.makedirs(SNAPDIR, exist_ok=True)
    if "--from-cache" in sys.argv:
        df = build_from_cache()
    else:
        key = _key()
        if "--universe" in sys.argv:
            tickers = json.load(open(sys.argv[sys.argv.index("--universe") + 1]))
        else:
            tickers = [f[:-5].replace("__", "/") for f in os.listdir(CACHE)]
        df = build_fetch(tickers, key)
    if df.empty:
        print("no snapshot rows"); return
    path = os.path.join(SNAPDIR, f"{TODAY}.csv")
    df.to_csv(path, index=False)
    print(f"snapshot {TODAY}: {len(df)} tickers -> {path}")
    snaps = sorted(glob.glob(os.path.join(SNAPDIR, "*.csv")))
    print(f"  total snapshots stored: {len(snaps)}"
          + ("" if len(snaps) >= 2 else "  (need >=2 for revision momentum)"))


if __name__ == "__main__":
    main()
