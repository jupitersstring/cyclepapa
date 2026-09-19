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

    # extra acceleration legs (gross profit, operating income/EBIT, EBITDA) —
    # all present in the income statement, no extra fetch.
    def accel(series):
        g0, g1 = yoy(series, 0), yoy(series, 1)
        return (g0 - g1) if np.isfinite(g0) and np.isfinite(g1) else np.nan
    gp = [_num(q.get("grossProfit")) for q in inc]
    ebit = [_num(q.get("operatingIncome")) for q in inc]
    ebitda = [_num(q.get("ebitda")) for q in inc]
    r["f_gp_accel"] = accel(gp)
    r["f_ebit_accel"] = accel(ebit)
    r["f_ebitda_accel"] = accel(ebitda)

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

    # ── buybacks / share-count reduction (limited-supply pillar) ──
    # diluted share count best captures net buyback after stock-comp dilution.
    shs = [_num(q.get("weightedAverageShsOut")) for q in inc]
    shd = [_num(q.get("weightedAverageShsOutDil")) for q in inc]
    r["buyback_yoy"] = -_growth(shs[0], shs[4]) if len(shs) > 4 else np.nan          # +ve = shrinking
    r["buyback_yoy_dil"] = -_growth(shd[0], shd[4]) if len(shd) > 4 else np.nan
    # consistency: share count lower than the year-ago quarter in each of last 4q
    if len(shd) >= 8:
        downs = [shd[i] < shd[i + 4] for i in range(4) if np.isfinite(shd[i]) and np.isfinite(shd[i + 4])]
        r["buyback_consistent"] = float(np.mean(downs)) if downs else np.nan
    else:
        r["buyback_consistent"] = np.nan
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

        # SUE — standardised unexpected earnings: latest EPS surprise divided by
        # the volatility of past surprises (Jegadeesh/Livnat). Robust to scale.
        surp = []
        for e in reported[:8]:
            a, es = _num(e.get("epsActual")), _num(e.get("epsEstimated"))
            if np.isfinite(a) and np.isfinite(es):
                surp.append(a - es)
        if len(surp) >= 4:
            sd = np.std(surp[1:]) if len(surp) > 1 else np.nan   # vol of prior surprises
            r["i_sue"] = surp[0] / sd if sd and np.isfinite(sd) and sd > 0 else np.nan
        else:
            r["i_sue"] = np.nan
        # revenue confirmation (Jegadeesh/Livnat): EPS & revenue beats agreeing
        es_, rs_ = r["i_eps_surprise"], r["i_rev_surprise"]
        if np.isfinite(es_) and np.isfinite(rs_):
            r["i_rev_confirm"] = 1.0 if (es_ > 0 and rs_ > 0) else (-1.0 if (es_ < 0 and rs_ < 0) else 0.0)
        else:
            r["i_rev_confirm"] = np.nan
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
        for k in ("i_eps_surprise", "i_rev_surprise", "i_pos_streak", "days_since_last",
                  "i_sue", "i_rev_confirm"):
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


INSIDER_CACHE = "/tmp/fmp_insider"
SENIOR = ("ceo", "chief executive", "cfo", "chief financial", "president",
          "chairman", "chair", "chief operating", "coo", "director")


def insider_feats(ticker, window_days=180):
    """Open-market insider-BUY conviction over the last `window_days`."""
    path = os.path.join(INSIDER_CACHE, ticker.replace("/", "__") + ".json")
    out = {"ticker": ticker, "ins_n_buys": 0, "ins_n_buyers": 0, "ins_buy_usd": 0.0,
           "ins_net_usd": 0.0, "ins_senior_buy": 0, "ins_offmkt_buys": 0,
           "ins_days_since_buy": np.nan}
    if not os.path.exists(path):
        for k in out:
            if k != "ticker":
                out[k] = np.nan
        return out
    try:
        txns = json.load(open(path)) or []
    except Exception:
        return out
    buy_usd = sell_usd = 0.0
    buyers = set(); n_buys = 0; senior = 0; offmkt = 0; last_buy = None
    for t in txns:
        dt = t.get("transactionDate")
        try:
            d = datetime.fromisoformat(dt).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if (NOW - d).days > window_days or (NOW - d).days < 0:
            continue
        px = _num(t.get("price")); sh = _num(t.get("securitiesTransacted"))
        if not np.isfinite(px) or not np.isfinite(sh) or px <= 0 or sh <= 0:
            continue                                        # skip awards/option exercises (price 0)
        val = px * sh
        ad = (t.get("acquisitionOrDisposition") or "")
        tt = (t.get("transactionType") or "")
        is_buy = ad == "A" and tt.upper().startswith("P")   # genuine open-market purchase
        is_sell = ad == "D" and tt.upper().startswith("S")
        if is_buy:
            buy_usd += val; n_buys += 1
            buyers.add(t.get("reportingName"))
            if any(s in (t.get("typeOfOwner") or "").lower() for s in SENIOR):
                senior += 1
            if d.weekday() >= 5:                            # dated on a weekend = off-market/off-hours proxy
                offmkt += 1
            if last_buy is None or d > last_buy:
                last_buy = d
        elif is_sell:
            sell_usd += val
    out.update(ins_n_buys=n_buys, ins_n_buyers=len(buyers), ins_buy_usd=buy_usd,
               ins_net_usd=buy_usd - sell_usd, ins_senior_buy=senior, ins_offmkt_buys=offmkt,
               ins_days_since_buy=((NOW - last_buy).days if last_buy else np.nan))
    return out


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

    # merge insider conviction (open-market buys)
    ins = pd.DataFrame([insider_feats(t) for t in p["ticker"]])
    p = p.merge(ins, on="ticker", how="left")

    # cross-sectional composites (percentile within the fetched panel)
    def pc(col, invert=False):
        s = p[col].rank(pct=True)
        return (1 - s) if invert else s

    # F: acceleration-weighted (2nd derivative emphasised) across EPS/rev/GP/
    # EBIT/EBITDA + margin inflection + growth level (Reinganum/He-Narayanamoorthy)
    p["F"] = (0.24 * pc("f_eps_accel") + 0.20 * pc("f_rev_accel")
              + 0.12 * pc("f_gp_accel") + 0.12 * pc("f_ebit_accel")
              + 0.08 * pc("f_ebitda_accel") + 0.16 * pc("f_margin_delta")
              + 0.04 * pc("f_rev_g") + 0.04 * pc("f_eps_g"))
    # I: SUE + surprise magnitude + streak, boosted when revenue confirms EPS
    p["I"] = (0.35 * pc("i_sue") + 0.25 * pc("i_eps_surprise")
              + 0.15 * pc("i_rev_surprise") + 0.15 * pc("i_pos_streak")
              + 0.10 * ((p["i_rev_confirm"].fillna(0) + 1) / 2))
    # R gap: neglect (LOW coverage) but not zero, plus dispersion
    neglect = 1 - pc("r_n_analysts")          # fewer analysts -> higher gap
    p["R_gap"] = 0.6 * neglect + 0.4 * pc("r_dispersion").fillna(0.5)
    # S supply: larger float -> more supply -> higher S (penalises in Model A)
    p["S_supply"] = pc("s_float_shares")

    # BB — buyback / share-count reduction (limited-supply, per-share leverage,
    # management conviction). Diluted YoY reduction + consistency.
    p["BB"] = (0.6 * pc("buyback_yoy_dil") + 0.2 * pc("buyback_yoy")
               + 0.2 * p["buyback_consistent"].fillna(0)).clip(0, 1)

    # INS — insider open-market BUY conviction: cluster of buyers + $ size +
    # senior participation + recency + off-market-dated buys.
    recency = 1 - (p["ins_days_since_buy"].fillna(999) / 180).clip(0, 1)   # newer = higher
    p["INS"] = (0.30 * pc("ins_n_buyers") + 0.25 * pc("ins_buy_usd")
                + 0.20 * pc("ins_senior_buy") + 0.15 * recency
                + 0.10 * pc("ins_offmkt_buys")).clip(0, 1)
    p.loc[p["ins_n_buys"].fillna(0) == 0, "INS"] = 0.0     # no buys -> no conviction

    p.to_csv(TMP, index=False)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    p.round(4).to_csv(OUT, index=False)
    print(f"panel: {len(p)} tickers")
    print(f"  with F (accel): {int(p['f_rev_accel'].notna().sum())}"
          f" | with surprise: {int(p['i_eps_surprise'].notna().sum())}"
          f" | with coverage: {int((p['r_n_analysts']>0).sum())}"
          f" | with float: {int(p['s_float_shares'].notna().sum())}")
    print(f"  buyback (dil YoY reduction >0): {int((p['buyback_yoy_dil']>0).sum())}"
          f" | insider open-mkt buys: {int((p['ins_n_buys'].fillna(0)>0).sum())}"
          f" | with off-market-dated buys: {int((p['ins_offmkt_buys'].fillna(0)>0).sum())}")


if __name__ == "__main__":
    main()
