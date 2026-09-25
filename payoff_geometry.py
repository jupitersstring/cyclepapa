"""Payoff-geometry engine -- quantify the asymmetry explicitly.

An "exceptional return scenario" is not a high score on a checklist; it is a
SHAPE: limited, asset-backed downside and large, mechanically-plausible
upside. This module measures that shape per name from hard balance-sheet
data, so the shortlist can be ranked by the ratio the whole framework is
implicitly hunting for.

For each ticker (needs price + shares + a balance sheet):

  DOWNSIDE FLOOR -- the price level hard assets defend, as a fraction of
  the current price. Tiered by hardness:
    * net-cash floor   = max(0, (cash - total debt) / shares) / price
    * NCAV floor       = (current assets - total liabilities) / shares / price
    * book floor       = 1 / (P/B)         (soft -- includes goodwill; haircut)
  floor = max(net-cash, NCAV, 0.5 x book).  downside% = max(0, 1 - floor).

  UPSIDE TARGET -- re-rate the name to its SECTOR MEDIAN multiple (mean-
  reversion of a cheap name to its peers), on both P/B and P/S:
    * upside_pb = sector_median_PB / PB - 1
    * upside_ps = sector_median_PS / PS - 1
  upside% = a blended, capped re-rate target.

  ASYMMETRY RATIO = upside% / downside%  (downside floored at 5% so a
  net-cash name doesn't divide by ~0). This is the payoff geometry.

The SCORE rewards a high ratio, but only when the floor is real (hard
net-cash / NCAV support scores more than a goodwill-inflated book) and the
name is genuinely cheap vs its sector. Value traps -- cheap with no floor
and no catalyst -- score low; the mechanism gates (mechanism_gates.py) and
the consensus catalyst layers supply the "why now" this geometry omits.

The feature WEIGHTS are collected in GEOMETRY_WEIGHTS so the winners study
(winners_forensics.py) can recalibrate them from what actual re-raters
looked like before they moved.

Output: payoff_geometry.json keyed by ticker.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "payoff_geometry.json"

# Tunable feature weights (winners_forensics.py may rewrite these).
GEOMETRY_WEIGHTS = {
    "ratio_scale": 7.0,        # x log1p(ratio) -> continuous asymmetry score
    "ratio_cap_hi": 50.0,      # clamp absurd micro-cap ratios before the log
    "floor_netcash": 6.0,      # hard net-cash floor >= 40% of price
    "floor_ncav": 4.0,         # NCAV/liquidation floor >= 40%
    "floor_book": 1.0,         # only a (haircut) book floor
    "nonburner_bonus": 3.0,    # floor does not erode (profitable / cash-gen)
    "deep_value_bonus": 4.0,   # trades below 0.6x sector-median P/B
    "min_downside": 0.05,      # floor on downside% to avoid divide-by-zero
    "upside_cap": 3.0,         # cap re-rate upside at +300%
    "burn_horizon_yrs": 1.5,   # years of cash burn to erode from the floor
    "dilution_penalty": 6.0,   # burner with < burn_horizon runway
    "no_revenue_upside_mult": 0.5,  # halve re-rate upside for bookless/no-rev
}


_FIN: dict = {}


def _num(x):
    """Coerce to float or None (some source fields are strings)."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _median(xs):
    xs = [v for v in (_num(x) for x in xs) if v is not None and v > 0]
    return statistics.median(xs) if xs else None


def main() -> int:
    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    frames = json.loads((ROOT / "xbrl_frames_store.json").read_text()) \
        if (ROOT / "xbrl_frames_store.json").exists() else {}
    ncav = json.loads((ROOT / "net_net_ncav.json").read_text()) \
        if (ROOT / "net_net_ncav.json").exists() else {}

    # 1) sector-median multiples for the re-rate target.
    by_sector_pb: dict[str, list] = {}
    by_sector_ps: dict[str, list] = {}
    for tk, y in yf.items():
        sec = y.get("sector") or "Unknown"
        by_sector_pb.setdefault(sec, []).append(y.get("p_b"))
        by_sector_ps.setdefault(sec, []).append(y.get("p_s"))
    sec_pb = {s: _median(v) for s, v in by_sector_pb.items()}
    sec_ps = {s: _median(v) for s, v in by_sector_ps.items()}

    W = GEOMETRY_WEIGHTS
    out = {}
    global _FIN
    try:
        _FIN = json.loads((ROOT / "name_financials.json").read_text())
    except Exception:
        _FIN = {}
    for tk, y in yf.items():
        price = _num(y.get("price")); mcap = _num(y.get("mcap"))
        pb = _num(y.get("p_b")); ps = _num(y.get("p_s"))
        sec = y.get("sector") or "Unknown"
        if not price or not mcap or price <= 0 or mcap <= 0:
            continue
        shares = mcap / price
        fr = frames.get(tk) or {}

        # ---- downside floor ----
        net_cash = _num(fr.get("net_cash"))
        net_cash_frac = (max(0.0, net_cash) / shares / price) \
            if (net_cash is not None and shares) else 0.0
        # NCAV = current assets - TOTAL liabilities. Two sources: net_net_ncav.json
        # and the SEC frames (CA - (assets - equity)). They disagree when the
        # scanner picks up the wrong liabilities line (NUS: +$5.31/sh vs negative
        # from the frames) -- take the more conservative of the two.
        cands = []
        if tk in ncav and _num(ncav[tk].get("ncav_per_share")) is not None:
            cands.append(_num(ncav[tk]["ncav_per_share"]))
        ca, ta, eq = _num(fr.get("cur_assets")), _num(fr.get("assets")), _num(fr.get("equity"))
        if ca is not None and ta is not None and eq is not None and shares:
            cands.append((ca - (ta - eq)) / shares)
        ncav_ps = min(cands) if cands else None
        ncav_frac = (max(0.0, ncav_ps) / price) if ncav_ps is not None else 0.0
        book_frac = (1.0 / pb) if (pb and pb > 0) else 0.0   # = book/price

        # Cash-minus-debt and NCAV are meaningless for financials (deposits /
        # insurance reserves are not "debt") and unreliable for REITs (property
        # held at depreciated cost against mortgage debt) -- fall back to book.
        if sec in ("Financial Services", "Real Estate"):
            net_cash_frac = 0.0
            ncav_frac = 0.0

        # cross-check against the validated FMP balance sheet: a name FMP shows with net
        # debt > 50% of mcap, or a current ratio < 0.5, has no cash / NCAV floor whatever the
        # (older, sometimes mis-tagged) XBRL frames say (AERA: frames net cash vs FMP net debt 102%)
        fq = _FIN.get(tk) or {}
        if (fq.get("net_cash_pct") is not None and fq["net_cash_pct"] < -0.5) or \
                (fq.get("current") is not None and fq["current"] < 0.5):
            net_cash_frac = ncav_frac = 0.0
        if fq.get("not_common") or fq.get("pb_src") in ("mcap_suspect", "implausible", "inconsistent"):
            continue                         # the market cap itself is not trustworthy
        hard_floor = max(net_cash_frac, ncav_frac)
        # BURN HAIRCUT: a cash floor erodes as the company burns. op_income is
        # quarterly; annualise and erode up to burn_horizon years of burn from
        # the hard (cash/NCAV) floor. Book floor is not cash so is not eroded.
        op_income = _num(fr.get("op_income"))
        annual_burn = max(0.0, -op_income * 4) if op_income is not None else 0.0
        annual_burn_frac = (annual_burn / shares / price) if shares else 0.0
        runway_yrs = None
        if annual_burn > 0 and net_cash is not None and net_cash > 0:
            runway_yrs = (net_cash / annual_burn)
        hard_floor_eff = max(0.0, hard_floor - W["burn_horizon_yrs"] * annual_burn_frac)

        # Book is a SOFT floor: at 0.4x P/B, "half of book" is 125% of the price --
        # the market is saying the book is impaired. It can support at most 60%
        # of the price; only cash / working capital can take downside below 40%.
        # Equity stubs (net debt > 2x mcap) get no book floor at all.
        soft = min(0.5 * book_frac, 0.60)
        if net_cash is not None and shares and price and (-net_cash) / (shares * price) > 2.0:
            soft = 0.0
        floor_frac = max(hard_floor_eff, soft)
        floor_frac = min(floor_frac, 1.5)   # cap (net-net names can exceed 1)
        if hard_floor_eff >= 0.40:
            floor_source = "net-cash" if net_cash_frac >= ncav_frac else "NCAV"
        elif book_frac > 0:
            floor_source = "book(0.5x)"
        else:
            floor_source = "none"
        downside_pct = max(0.0, 1.0 - floor_frac)

        # ---- upside target: re-rate to sector median ----
        smpb, smps = sec_pb.get(sec), sec_ps.get(sec)
        upside_pb = (smpb / pb - 1.0) if (smpb and pb and pb > 0) else None
        upside_ps = (smps / ps - 1.0) if (smps and ps and ps > 0) else None
        ups = [u for u in (upside_pb, upside_ps) if u is not None and u > 0]
        if not ups:
            upside_pct = 0.0; upside_source = "none"
        else:
            # conservative: average the available re-rate targets, capped.
            upside_pct = min(sum(ups) / len(ups), W["upside_cap"])
            upside_source = ("PB+PS" if len(ups) == 2
                             else ("PB" if upside_pb and upside_pb > 0 else "PS"))
            # a re-rate multiple is an artifact when there is no real business
            # (no revenue / no gross profit): halve the claimed upside.
            gp = _num(fr.get("gross_profit")); rev = _num(fr.get("revenue"))
            if not ((gp and gp > 0) or (rev and rev > 0)):
                upside_pct *= W["no_revenue_upside_mult"]
                upside_source += "(no-rev)"

        # ---- asymmetry ratio + score ----
        denom = max(downside_pct, W["min_downside"])
        ratio = upside_pct / denom
        # CONTINUOUS asymmetry score: log of the ratio (diminishing returns,
        # never flat), so a 30:1 name still outranks a 12:1 name.
        score = W["ratio_scale"] * math.log1p(min(ratio, W["ratio_cap_hi"]))
        # FLOOR QUALITY: cash is harder than a liquidation estimate is harder
        # than goodwill-inflated book.
        if net_cash_frac >= 0.40 and net_cash_frac >= ncav_frac:
            score += W["floor_netcash"]
        elif hard_floor_eff >= 0.40:
            score += W["floor_ncav"]
        elif book_frac > 0:
            score += W["floor_book"]
        # a non-burner's floor does not erode -> trustworthy; long runway helps.
        if annual_burn <= 0:
            score += W["nonburner_bonus"]
        elif runway_yrs is not None and runway_yrs < W["burn_horizon_yrs"]:
            score -= W["dilution_penalty"]     # will dilute below the floor
        if smpb and pb and pb > 0 and pb < 0.6 * smpb:
            score += W["deep_value_bonus"]
        # a name with no real upside room is not asymmetric, whatever its floor
        if upside_pct <= 0.10:
            score = 0.0
        score = max(0.0, score)

        if score <= 0:
            continue
        out[tk] = {
            "ticker": tk,
            "price": round(price, 2),
            "sector": sec,
            "floor_frac": round(floor_frac, 3),
            "floor_source": floor_source,
            "downside_pct": round(downside_pct, 3),
            "upside_pct": round(upside_pct, 3),
            "upside_source": upside_source,
            "ratio": round(ratio, 2),
            "net_cash_frac": round(net_cash_frac, 3),
            "ncav_frac": round(ncav_frac, 3),
            "book_frac": round(book_frac, 3),
            "runway_yrs": round(runway_yrs, 1) if runway_yrs is not None else None,
            "burning": annual_burn > 0,
            "p_b": pb, "p_s": ps,
            "sector_med_pb": round(smpb, 2) if smpb else None,
            "score": round(score, 1),
        }

    io_util.write_json(OUT, out)
    ranked = sorted(out.values(), key=lambda r: -r["score"])
    print(f"wrote {OUT} ({len(out)} names with measurable asymmetry)")
    print(f"{'TKR':<7}{'SCORE':>6}{'RATIO':>7}{'UP%':>7}{'DOWN%':>7}  FLOOR      SECTOR")
    for r in ranked[:30]:
        print(f"{r['ticker']:<7}{r['score']:>6.1f}{r['ratio']:>7.1f}"
              f"{r['upside_pct']*100:>6.0f}%{r['downside_pct']*100:>6.0f}%  "
              f"{r['floor_source']:<10} {r['sector'][:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
