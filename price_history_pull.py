"""Price-history puller for the Lynch reawakening layer.

Populates price_history.json (monthly 10y + weekly 2y closes) for the
FUNDAMENTALLY-ADVANCED shortlist -- the names the assembly, residual-stub,
emergence, distressed-progress and top-consensus legs have flagged as
"the business advanced significantly". That is the correct population for
the reawakening overlay (Lynch's Fannie Mae: fundamentals transformed,
THEN the price re-rated) and keeps the pull bounded vs the 6,166 universe.

Resumable + atomic; if the price source is rate-limited the layer simply
stays sparse until a later run fills it (the source-health gate makes the
sparseness visible rather than silent).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "price_history.json"


def _load(name):
    p = ROOT / name
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def build_shortlist(limit: int) -> list[str]:
    """Union of the fundamentally-advanced signals + top consensus."""
    tks: set[str] = set()
    for name, key in [("asymmetry_assembly.json", "score"),
                      ("emergence_crossfeed.json", "score"),
                      ("distressed_stub_progress.json", "score"),
                      ("equity_committee_scan.json", "score"),
                      ("discretionary_insider_conviction.json", "score")]:
        d = _load(name)
        for tk, v in d.items():
            if isinstance(v, dict) and (v.get(key) or 0) > 0:
                tks.add(tk)
    # residual-stub names (negative equity + op income) from the assembly
    aa = _load("asymmetry_assembly.json")
    for tk, v in aa.items():
        ev = (v.get("components", {}).get("C2_leveraged_survivor", {}) or {}).get("evidence", "")
        if "residual stub" in ev:
            tks.add(tk)
    # top consensus
    import csv
    p = ROOT / "full_universe_consensus.csv"
    if p.exists():
        rows = list(csv.DictReader(p.open()))
        for r in rows[:400]:
            tks.add(r["ticker"])
    tks = {t for t in tks if t and t.isascii() and t.replace(".", "").replace("-", "").isalnum()}
    return sorted(tks)[:limit]


def pull(tk):
    """OHLC arrays: monthly 10y, quarterly 10y, weekly 2y (yfinance)."""
    import yfinance as yf
    t = yf.Ticker(tk)
    def ohlc(df):
        if not len(df):
            return [], [], []
        h = [round(float(x), 4) for x in df["High"].tolist()]
        l = [round(float(x), 4) for x in df["Low"].tolist()]
        c = [round(float(x), 4) for x in df["Close"].tolist()]
        # drop rows with any NaN (keep arrays aligned)
        keep = [i for i in range(len(c)) if c[i] == c[i] and h[i] == h[i] and l[i] == l[i]]
        return ([h[i] for i in keep], [l[i] for i in keep], [c[i] for i in keep])
    mh, ml, mc = ohlc(t.history(period="10y", interval="1mo"))
    qh, ql, qc = ohlc(t.history(period="10y", interval="3mo"))
    wh, wl, wc = ohlc(t.history(period="2y", interval="1wk"))
    return mh, ml, mc, qh, ql, qc, wh, wl, wc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--sleep", type=float, default=0.6)
    args = ap.parse_args()

    shortlist = build_shortlist(args.limit)
    out = _load("price_history.json")
    print(f"price pull: {len(shortlist)} fundamentally-advanced names "
          f"({len(out)} already cached)", file=sys.stderr)

    done = ok = 0
    for tk in shortlist:
        if tk in out and out[tk].get("monthly_close"):
            continue
        try:
            mh, ml, mc, qh, ql, qc, wh, wl, wc = pull(tk)
            if mc:
                out[tk] = {"monthly_high": mh, "monthly_low": ml, "monthly_close": mc,
                           "quarterly_high": qh, "quarterly_low": ql, "quarterly_close": qc,
                           "weekly_high": wh, "weekly_low": wl, "weekly_close": wc}
                ok += 1
        except Exception as e:
            if "RateLimit" in type(e).__name__ or "Too Many" in str(e):
                print(f"  rate-limited at {tk}; stopping (resume later). "
                      f"{ok} pulled this run.", file=sys.stderr)
                break
            out.setdefault(tk, {"_error": str(e)[:80]})
        done += 1
        if done % 20 == 0:
            io_util.write_json(OUT, out)
            print(f"  [{done}] {ok} priced", file=sys.stderr, flush=True)
        time.sleep(args.sleep)

    io_util.write_json(OUT, out)
    priced = sum(1 for v in out.values() if isinstance(v, dict) and v.get("monthly_close"))
    print(f"wrote {OUT} ({priced} priced of {len(shortlist)} shortlisted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
