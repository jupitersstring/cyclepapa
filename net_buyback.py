"""Net-buyback quality -- did the buyback actually shrink the share count?

Buyback-logic improvement. Naive buyback screening (and gross
authorisation headlines) reward dollars announced. The substantive test
is whether DILUTED shares outstanding actually FELL year-over-year -- i.e.
the repurchase beat stock-based-comp dilution and is genuinely accretive
to per-share value -- AND whether it was done while the stock was cheap
(Mauboussin: a buyback creates value only below intrinsic value).

Uses the SEC XBRL frames API for WeightedAverageNumberOfDilutedShares
Outstanding (best coverage, and the diluted count is what EPS accretion
actually depends on), universe-wide. Signals:

  net_buyback_yield = (shares_year_ago - shares_now) / shares_year_ago
    > 0  net share COUNT reduction (real buyback, net of dilution)
    < 0  net dilution (SBC / issuance outran any buyback)

Scored positively only when shares shrank; the reduction is rewarded
more when the stock is cheap (P/B < 1.5 or EV/EBIT < 10 from the frames
store), and net dilution scores a small negative (a genuine anti-signal
the buyback layers previously ignored).

Additive overlay; complements buyback_verify (gross/verified shrinkage)
and selective_buyback (revealed-valuation classes).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
CACHE = ROOT / "xbrl_frames"
OUT = ROOT / "net_buyback.json"
TAG = "WeightedAverageNumberOfDilutedSharesOutstanding"


def fetch_frame(period):
    cf = CACHE / f"{TAG}_{period}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass
    from edgar import _get
    url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{TAG}/shares/{period}.json"
    try:
        d = _get(url).json()
    except Exception:
        return {}
    out = {str(r["cik"]): r["val"] for r in d.get("data", [])
           if r.get("cik") is not None and r.get("val")}
    CACHE.mkdir(exist_ok=True)
    io_util.write_json(cf, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--q", type=int, default=1)
    args = ap.parse_args()
    now_p = f"CY{args.year}Q{args.q}"
    ya_p = f"CY{args.year - 1}Q{args.q}"          # same quarter, year ago
    print(f"net-buyback: diluted shares {now_p} vs {ya_p}", file=sys.stderr)

    now = fetch_frame(now_p); time.sleep(0.2)
    ya = fetch_frame(ya_p)
    if not now or not ya:
        print("frames unavailable; writing empty", file=sys.stderr)
        io_util.write_json(OUT, {}); return 0

    from recent import _cik_to_ticker_map
    cik_tk = {str(int(k)): v for k, v in _cik_to_ticker_map().items()}
    yf = json.loads((ROOT / "yfinance_quick.json").read_text()) \
        if (ROOT / "yfinance_quick.json").exists() else {}
    fr = json.loads((ROOT / "xbrl_frames_store.json").read_text()) \
        if (ROOT / "xbrl_frames_store.json").exists() else {}

    out = {}
    for cik, sh_now in now.items():
        sh_ya = ya.get(cik)
        if not sh_ya or not sh_now or sh_ya <= 0:
            continue
        tk = cik_tk.get(str(int(cik))) if cik.isdigit() else None
        if not tk:
            continue
        nby = (sh_ya - sh_now) / sh_ya            # >0 = shrinking
        # cheapness gate (reward accretive buybacks done cheap)
        y = yf.get(tk, {}) or {}
        r = fr.get(tk, {}) or {}
        pb = None
        try:
            pb = float(y.get("p_b")) if y.get("p_b") is not None else None
        except Exception:
            pb = None
        if pb is None and y.get("mcap") and (r.get("equity") or 0) > 0:
            pb = y["mcap"] / r["equity"]
        cheap = (pb is not None and 0 < pb < 1.5)

        score = 0.0; reasons = []
        # Reverse-split guard: an organic buyback almost never retires
        # >35% of diluted shares in a year (AutoZone-class serial
        # cannibals top out ~10-25%). A larger drop is a reverse split,
        # not a repurchase -- exclude it rather than crown it.
        if nby >= 0.35:
            continue
        if nby >= 0.10:
            score = 16; reasons.append(f"net shares -{nby*100:.0f}% YoY (heavy)")
        elif nby >= 0.05:
            score = 11; reasons.append(f"net shares -{nby*100:.0f}% YoY")
        elif nby >= 0.02:
            score = 6; reasons.append(f"net shares -{nby*100:.0f}% YoY (modest)")
        elif nby <= -0.10:
            score = -6; reasons.append(f"net DILUTION +{-nby*100:.0f}% YoY")
        elif nby <= -0.03:
            score = -3; reasons.append(f"net dilution +{-nby*100:.0f}% YoY")
        if score > 0 and cheap:
            score += 6; reasons.append(f"buying cheap (P/B {pb:.2f})")
        if score == 0:
            continue
        out[tk] = {"ticker": tk, "net_buyback_yield": round(nby, 4),
                   "shares_now": sh_now, "shares_year_ago": sh_ya,
                   "cheap": cheap, "score": round(score, 1),
                   "reasons": reasons}

    io_util.write_json(OUT, out)
    shrink = sum(1 for v in out.values() if v["score"] > 0)
    dilut = sum(1 for v in out.values() if v["score"] < 0)
    print(f"wrote {OUT} ({len(out)} names: {shrink} net-shrinking, {dilut} diluting)")
    for tk, v in sorted(out.items(), key=lambda x: -x[1]["score"])[:15]:
        print(f"  {tk:<7}{v['score']:>6.0f}  {'; '.join(v['reasons'])[:55]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
