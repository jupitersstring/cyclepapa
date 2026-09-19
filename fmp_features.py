"""Distil FMP raw cache (/tmp/fmp_cache/*.json) into the F/I/R/S + catalyst
panel used by Model A (monster candidate) and Model B (ignition, catalyst).

Feature blocks (per the extreme-winner literature):

  F  fundamental acceleration  — the 2nd derivative Reinganum / He-Narayanamoorthy
     stress: change in YoY revenue & EPS growth, plus operating-margin inflection.
  I  information surprise      — latest reported EPS/revenue surprise vs consensus
     and a positive-surprise streak (Doyle-Lundholm-Soliman persistence).
  R  recognition gap           — LOW analyst coverage (neglect) + forecast
     dispersion; neglect x surprise is the DLS combo.
  S  supply                    — free float and float in $ (scarcity).
  catalyst — days since last earnings / to next earnings + whether the last
     surprise was positive: the raw material for real CatalystVerified.

Writes data/fmp/fundamentals.csv (committed) and /tmp/fmp_panel.csv.
"""

import os
import glob
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

CACHE = "/tmp/fmp_cache"
OUT = "/home/user/cyclepapa/data/fmp/fundamentals.csv"
TMP = "/tmp/fmp_panel.csv"
MASTER = "/tmp/master_full_universe.csv"
NOW = datetime.now(timezone.utc)


def _num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _growth(cur, base):
    cur, base = _num(cur), _num(base)
    if not np.isfinite(cur) or not np.isfinite(base) or base == 0:
        return np.nan
    return cur / abs(base) - 1.0 if base > 0 else np.nan


def feats(d):
    r = {"ticker": d.get("symbol")}
    inc = d.get("income") or []
    # income-statement: most-recent quarter first; need >=5 for one YoY, >=6 for accel
    rev = [_num(q.get("revenue")) for q in inc]
    opi = [_num(q.get("operatingIncome")) for q in inc]
    ni = [_num(q.get("netIncome")) for q in inc]
    eps = [_num(q.get("epsdiluted") if q.get("epsdiluted") is not None else q.get("eps")) for q in inc]

    def yoy(series, i):
        return _growth(series[i], series[i + 4]) if len(series) > i + 4 else np.nan

    r["f_rev_g"] = yoy(rev, 0)
    r["f_rev_g_prev"] = yoy(rev, 1)
    r["f_rev_accel"] = (r["f_rev_g"] - r["f_rev_g_prev"]) if np.isfinite(r["f_rev_g"]) and np.isfinite(r["f_rev_g_prev"]) else np.nan
    r["f_eps_g"] = yoy(ni, 0)                      # use net income (eps can be diluted/adjusted noisily)
    r["f_eps_g_prev"] = yoy(ni, 1)
    r["f_eps_accel"] = (r["f_eps_g"] - r["f_eps_g_prev"]) if np.isfinite(r["f_eps_g"]) and np.isfinite(r["f_eps_g_prev"]) else np.nan

    # growth STABILITY (Frog-in-the-Pan: continuous, steady improvement is
    # underreacted to). Over the last 4 YoY revenue-growth readings: reward
    # consistently-positive, low-variance (smooth) growth. 1 = steady climb.
    yoy_rev = [yoy(rev, i) for i in range(4)]
    yoy_rev = [g for g in yoy_rev if np.isfinite(g)]
    if len(yoy_rev) >= 3:
        arr = np.array(yoy_rev)
        pos_frac = float((arr > 0).mean())
        cv = float(np.std(arr) / (abs(np.mean(arr)) + 1e-6))   # coefficient of variation
        r["growth_stability"] = pos_frac / (1.0 + cv)
        r["rev_ttm_ttm_g"] = float(np.mean(arr))               # avg YoY over the window
    else:
        r["growth_stability"] = np.nan
        r["rev_ttm_ttm_g"] = np.nan
    # trailing EPS (ttm) for the valuation-lag check in Model FIP
    eps_ttm = sum(e for e in eps[:4] if np.isfinite(e)) if len(eps) >= 4 else np.nan
    r["eps_ttm"] = eps_ttm if (isinstance(eps_ttm, float) and np.isfinite(eps_ttm)) else np.nan
    # operating-margin inflection: current vs year-ago quarter
    if len(rev) > 4 and rev[0] and rev[4] and np.isfinite(opi[0]) and np.isfinite(opi[4]):
        r["f_margin"] = opi[0] / rev[0]
        r["f_margin_delta"] = opi[0] / rev[0] - opi[4] / rev[4]
    else:
        r["f_margin"] = r["f_margin_delta"] = np.nan

    # ── earnings: surprise (I) + catalyst ──
    ear = d.get("earnings") or []
    reported = [e for e in ear if e.get("epsActual") is not None]
    upcoming = [e for e in ear if e.get("epsActual") is None and e.get("date")]
    if reported:
        last = reported[0]
        ea, ee = _num(last.get("epsActual")), _num(last.get("epsEstimated"))
        ra, re_ = _num(last.get("revenueActual")), _num(last.get("revenueEstimated"))
        r["i_eps_surprise"] = (ea - ee) / abs(ee) if np.isfinite(ea) and np.isfinite(ee) and ee != 0 else np.nan
        r["i_rev_surprise"] = (ra - re_) / abs(re_) if np.isfinite(ra) and np.isfinite(re_) and re_ != 0 else np.nan
        # positive-surprise streak
        streak = 0
        for e in reported:
            a, es = _num(e.get("epsActual")), _num(e.get("epsEstimated"))
            if np.isfinite(a) and np.isfinite(es) and a > es:
                streak += 1
            else:
                break
        r["i_pos_streak"] = streak
        r["last_earnings_date"] = last.get("date")
        try:
            r["days_since_last"] = (NOW - datetime.fromisoformat(last["date"]).replace(tzinfo=timezone.utc)).days
        except Exception:
            r["days_since_last"] = np.nan
        r["last_surprise_pos"] = bool(np.isfinite(r["i_eps_surprise"]) and r["i_eps_surprise"] > 0)
    else:
        for k in ("i_eps_surprise", "i_rev_surprise", "i_pos_streak", "days_since_last"):
            r[k] = np.nan
        r["last_earnings_date"] = None
        r["last_surprise_pos"] = False
    if upcoming:
        nxt = sorted(upcoming, key=lambda e: e["date"])[0]
        r["next_earnings_date"] = nxt["date"]
        try:
            r["days_to_next"] = (datetime.fromisoformat(nxt["date"]).replace(tzinfo=timezone.utc) - NOW).days
        except Exception:
            r["days_to_next"] = np.nan
    else:
        r["next_earnings_date"] = None
        r["days_to_next"] = np.nan

    # ── recognition gap (R) ──
    gr = (d.get("grades") or [{}])
    gr = gr[0] if gr else {}
    n_an = sum(_num(gr.get(k)) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))
    r["r_n_analysts"] = n_an
    est = d.get("estimates") or []
    if est:
        e0 = est[0]
        lo, hi, av = _num(e0.get("revenueLow")), _num(e0.get("revenueHigh")), _num(e0.get("revenueAvg"))
        r["r_dispersion"] = (hi - lo) / abs(av) if np.isfinite(lo) and np.isfinite(hi) and np.isfinite(av) and av else np.nan
    else:
        r["r_dispersion"] = np.nan

    # ── supply (S) ──
    fl = (d.get("float") or [{}])
    fl = fl[0] if fl else {}
    r["s_float_shares"] = _num(fl.get("floatShares"))
    r["s_free_float_pct"] = _num(fl.get("freeFloat"))
    return r


def main():
    files = glob.glob(os.path.join(CACHE, "*.json"))
    rows = []
    for f in files:
        try:
            d = json.load(open(f))
        except Exception:
            continue
        rows.append(feats(d))
    p = pd.DataFrame(rows)
    if p.empty:
        print("no cache yet"); return

    # cross-sectional composites (percentile within the fetched panel)
    def pc(col, invert=False):
        s = p[col].rank(pct=True)
        return (1 - s) if invert else s

    # F: acceleration-weighted (2nd derivative emphasised) + level
    p["F"] = (0.35 * pc("f_rev_accel") + 0.25 * pc("f_eps_accel")
              + 0.20 * pc("f_margin_delta") + 0.10 * pc("f_rev_g") + 0.10 * pc("f_eps_g"))
    # I: positive surprise magnitude + streak
    p["I"] = 0.6 * pc("i_eps_surprise") + 0.2 * pc("i_rev_surprise") + 0.2 * pc("i_pos_streak")
    # R gap: neglect (LOW coverage) but not zero, plus dispersion
    neglect = 1 - pc("r_n_analysts")          # fewer analysts -> higher gap
    p["R_gap"] = 0.6 * neglect + 0.4 * pc("r_dispersion").fillna(0.5)
    # S supply: larger float -> more supply -> higher S (penalises in Model A)
    p["S_supply"] = pc("s_float_shares")

    p.to_csv(TMP, index=False)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    p.round(4).to_csv(OUT, index=False)
    print(f"panel: {len(p)} tickers")
    print(f"  with F (accel): {int(p['f_rev_accel'].notna().sum())}"
          f" | with surprise: {int(p['i_eps_surprise'].notna().sum())}"
          f" | with coverage: {int((p['r_n_analysts']>0).sum())}"
          f" | with float: {int(p['s_float_shares'].notna().sum())}")


if __name__ == "__main__":
    main()
