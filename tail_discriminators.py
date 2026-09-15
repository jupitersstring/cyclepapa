"""Tail discriminators -- what separated the right-tail re-raters from the
duds, measured on the historical event set.

The backtest showed corporate-action catalysts are median-underperformers
but tail-driven (~15% of events > +50% / 12m). This module asks the
actionable question: WITHIN the events, which features observable AT/BEFORE
the event raised the probability of landing in the tail? For each feature,
binned, it reports P(tail | bin) and the LIFT over the base tail rate.

Features (all pre-event / observable, no look-ahead):
  * catalyst   -- SPINOFF / ASSET_SALE / SALE_OF_COMPANY / STRATEGIC_REVIEW
  * sector     -- GICS-ish sector
  * size       -- micro / small / mid / large by market cap
  * drawdown_12m -- how far below its trailing-12m high the name sat at t0
  * range_pos  -- where in its trailing 12m range t0 sat (0 low .. 1 high)
  * pre_12m    -- trailing 12-month return into the event (momentum)
  * post_1m    -- the market's INITIAL reaction (usable by a strategy that
                  waits one month for confirmation before entering)

Output: tail_discriminators.json -- base rate, per-feature bin lifts, and the
subset of features usable for LIVE screening (those computable from current
data), which tail_odds.py applies to today's candidates.
"""

from __future__ import annotations

import json
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "rerate_backtest.json"
OUT = ROOT / "tail_discriminators.json"

TAIL_THRESHOLD = 0.50        # 12m return that counts as "right tail"

# features computable for a LIVE candidate today (from yfinance + catalyst
# engine): catalyst type, sector, size, drawdown from 52wk high, range
# position. pre_12m/post_1m are analysis-only (need history / a wait).
SCREENABLE = ["catalyst", "sector", "size", "drawdown_12m", "range_pos"]


def size_bin(mcap):
    if not mcap:
        return None
    if mcap < 3e8:
        return "micro"
    if mcap < 2e9:
        return "small"
    if mcap < 1e10:
        return "mid"
    return "large"


def dd_bin(dd):
    if dd is None:
        return None
    if dd <= -0.5:
        return "deep(<-50%)"
    if dd <= -0.2:
        return "mod(-50..-20%)"
    return "shallow(>-20%)"


def pos_bin(p):
    if p is None:
        return None
    if p < 0.33:
        return "low"
    if p < 0.66:
        return "mid"
    return "high"


def ret_bin(r):
    if r is None:
        return None
    if r <= -0.2:
        return "down(<-20%)"
    if r < 0.2:
        return "flat"
    return "up(>+20%)"


def feature_bins(e):
    return {
        "catalyst": e.get("catalyst"),
        "sector": e.get("sector"),
        "size": size_bin(e.get("mcap")),
        "drawdown_12m": dd_bin(e.get("drawdown_12m")),
        "range_pos": pos_bin(e.get("range_pos")),
        "pre_12m": ret_bin(e.get("pre_12m")),
        "post_1m": ret_bin(e.get("post_1m")),
    }


def main() -> int:
    d = json.loads(SRC.read_text())
    events = [e for e in d.get("events", []) if e.get("ret_12m") is not None]
    n = len(events)
    if not n:
        print("no priced events"); io_util.write_json(OUT, {}); return 0

    tail = [e for e in events if e["ret_12m"] >= TAIL_THRESHOLD]
    base = len(tail) / n

    # accumulate per feature/bin.
    feats: dict[str, dict] = {}
    for e in events:
        is_tail = e["ret_12m"] >= TAIL_THRESHOLD
        for f, b in feature_bins(e).items():
            if b is None:
                continue
            fb = feats.setdefault(f, {}).setdefault(b, {"n": 0, "tail": 0})
            fb["n"] += 1
            fb["tail"] += 1 if is_tail else 0

    out_feats = {}
    for f, bins in feats.items():
        out_feats[f] = {}
        for b, v in bins.items():
            if v["n"] < 3:            # too few to trust
                continue
            tr = v["tail"] / v["n"]
            out_feats[f][b] = {"n": v["n"], "tail_rate": round(tr, 3),
                               "lift": round(tr / base, 2) if base > 0 else None}

    result = {
        "n_events": n, "n_tail": len(tail),
        "tail_threshold": TAIL_THRESHOLD,
        "base_tail_rate": round(base, 3),
        "screenable": SCREENABLE,
        "features": out_feats,
    }
    io_util.write_json(OUT, result)

    print(f"tail = 12m >= {TAIL_THRESHOLD*100:.0f}%  |  "
          f"{len(tail)}/{n} events ({base*100:.0f}% base rate)\n")
    for f in ["catalyst", "sector", "size", "drawdown_12m", "range_pos",
              "pre_12m", "post_1m"]:
        if f not in out_feats:
            continue
        tag = "" if f in SCREENABLE else "  (analysis-only)"
        print(f"{f}{tag}")
        for b, v in sorted(out_feats[f].items(),
                           key=lambda kv: -(kv[1]["lift"] or 0)):
            bar = "#" * int((v["lift"] or 0) * 5)
            print(f"   {b:<16} n={v['n']:>3}  tail {v['tail_rate']*100:>4.0f}%"
                  f"  lift {v['lift']:>4}  {bar}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
