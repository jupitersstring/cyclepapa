"""Russell reconstitution forced-flow scanner (best-effort).

Each year (rank day in late April, effective end-June) FTSE Russell rebuilds
its indices by market-cap rank. Stocks crossing INTO the Russell 2000/1000
draw mechanical index buying; stocks falling OUT draw forced selling and
often a post-recon reversal. The band around each breakpoint is where the
flow -- and the opportunity -- lives.

DATA CAVEAT (stated in output): a precise breakpoint needs the FULL ranked
US common-stock universe (~4,000 names) plus FTSE Russell's float
adjustment; this environment has ~2,800 priced names, so the breakpoints
here are ESTIMATED from the available distribution. Treat this as a watchlist
of boundary-band candidates, not the definitive add/delete list. It replaces
a frozen June snapshot with a live, if approximate, re-computation.

Bands (approximate market-cap breakpoints):
  * R1000/R2000 boundary  ~ $4-6B   -> up-cross = R1000 add (large buy)
  * R2000 inclusion floor ~ $150-300M -> the microcap add/delete band
  * below the floor         -> deletion risk (forced selling, then reversal)

Output: russell_recon.json keyed by ticker.
"""

from __future__ import annotations

import json
from pathlib import Path

import io_util
from universe_filter import is_excluded

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "russell_recon.json"

# Estimated breakpoints (USD). Adjust as the universe grows.
R1000_BOUNDARY = 5.0e9
R2000_FLOOR_LO = 1.5e8
R2000_FLOOR_HI = 4.0e8
BAND = 0.25          # +/-25% band around a breakpoint counts as "near"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main() -> int:
    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    names = []
    for tk, y in yf.items():
        mcap = _num(y.get("mcap"))
        if not mcap or mcap <= 0:
            continue
        bad, _ = is_excluded(tk)
        if bad:
            continue
        names.append((tk, mcap, y))

    out = {}
    for tk, mcap, y in names:
        band = None; score = 0.0
        # R1000/R2000 boundary
        if R1000_BOUNDARY * (1 - BAND) <= mcap <= R1000_BOUNDARY * (1 + BAND):
            band = "R1000/R2000 boundary"; score = 8.0
        # microcap R2000 inclusion band
        elif R2000_FLOOR_LO <= mcap <= R2000_FLOOR_HI:
            band = "R2000 inclusion band"; score = 7.0
        # just below the floor -> deletion risk / post-recon reversal
        elif R2000_FLOOR_LO * 0.6 <= mcap < R2000_FLOOR_LO:
            band = "below R2000 floor (deletion risk)"; score = 6.0
        if not band:
            continue
        pb = _num(y.get("p_b"))
        # a boundary name that is ALSO cheap is the better reversal setup
        if pb is not None and 0 < pb < 1.0:
            score += 2
        out[tk] = {
            "ticker": tk, "name": y.get("name", tk),
            "mcap": mcap, "band": band, "p_b": pb,
            "sector": y.get("sector"), "score": round(score, 1),
        }

    io_util.write_json(OUT, out)
    from collections import Counter
    c = Counter(v["band"] for v in out.values())
    ranked = sorted(out.values(), key=lambda r: -r["score"])
    print(f"wrote {OUT} ({len(out)} boundary-band names -- ESTIMATED "
          f"breakpoints, see caveat)")
    for b, n in c.most_common():
        print(f"  {b:<36} {n}")
    print(f"\n{'TKR':<8}{'SCORE':>6}{'MCAP($M)':>10}  BAND")
    for r in ranked[:20]:
        print(f"{r['ticker']:<8}{r['score']:>6.1f}{r['mcap']/1e6:>10.0f}  {r['band']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
