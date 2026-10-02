"""Point-in-time backtest of the pre-rerating signals against REAL forward returns.

The honest test. We do NOT have a historical price panel, but we DO have:
  (a) every past EDGAR filing, each stamped with its SEC `filed` date, so we can
      reconstruct fundamentals EXACTLY as they were visible on any past date
      (no lookahead: use only observations with filed <= T); and
  (b) a realized trailing-12m price return (`momentum_12m`, fetched 2026-06-25),
      which IS the realized FORWARD return over the window 2025-06-25 -> 2026-06-25.

So we snapshot signals as of T = 2025-06-25 and ask: did they predict the
realized 12-month forward return in our own universe?

This is a SINGLE-COHORT test (one 12m window, one regime) -> treat spreads as
directional evidence, not statistical proof. Caveats are printed in the report.
Because EDGAR filers report in USD and momentum is a local-currency price return,
FX is a non-issue for exactly the population this test covers (US filers).

Signals reconstructed point-in-time (annual, Piotroski-style):
  * Piotroski F-score (9 binary components) -- the canonical, HIGH-confidence anchor
  * Sloan accrual quality              -- -(NI - CFO)/assets
  * Novy-Marx gross profitability      -- gross_profit / assets
  * N1 decline-deceleration (2nd deriv) -- is the rate of revenue decline shrinking?
  * cheapness at T (P/B_T, earnings yield_T) using price_at_T = price_now/(1+fwd)
  * composite pre_rerating proxy        -- F-score gated on cheapness (TURN x DISBELIEF)

Outputs:
  backtest_panel.csv     -- per-ticker signals + realized forward return (inspectable)
  BACKTEST_PRERERATING.md -- decile tables, IC, spreads, caveats
"""
import datetime
import glob
import gzip
import json
import os
import sys
from collections import defaultdict

import pandas as pd

T = datetime.date(2025, 6, 25)          # snapshot date (fwd window T -> 2026-06-25)
DUR_LO, DUR_HI = 340, 380               # annual-period duration window (days)

# ---- concept aliases (freshest-alias, us-gaap) --------------------------------
ASSETS = ["Assets"]
EQUITY = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
NI = ["NetIncomeLoss", "ProfitLoss"]
CFO = ["NetCashProvidedByUsedInOperatingActivities",
       "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
GROSS = ["GrossProfit"]
COGS = ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"]
LTDEBT = ["LongTermDebtNoncurrent", "LongTermDebt"]
CUR_A = ["AssetsCurrent"]
CUR_L = ["LiabilitiesCurrent"]
SHARES = ["CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding",
          "WeightedAverageNumberOfSharesOutstandingBasic"]


def _obs(g, concepts, unit="USD"):
    """All observations for the first alias that has data in `unit`, filed<=T."""
    for c in concepts:
        units = (g.get(c, {}) or {}).get("units", {})
        obs = units.get(unit, [])
        if obs:
            keep = [o for o in obs if o.get("filed") and o["filed"] <= T.isoformat()
                    and o.get("val") is not None and o.get("end")]
            if keep:
                return keep
    return []


def _annual(g, concepts, unit="USD"):
    """Return (latest_annual, prior_annual) flow values as visible at T.

    Selects duration-~1yr periods; prior is the one whose end is ~365d before
    the latest end. Freshest-alias: prefers the alias with the most annual obs.
    """
    best = []
    for c in concepts:
        obs = (g.get(c, {}) or {}).get("units", {}).get(unit, [])
        ann = []
        for o in obs:
            if not (o.get("filed") and o["filed"] <= T.isoformat()):
                continue
            if o.get("val") is None or not o.get("start") or not o.get("end"):
                continue
            try:
                d = (datetime.date.fromisoformat(o["end"]) - datetime.date.fromisoformat(o["start"])).days
            except Exception:
                continue
            if DUR_LO <= d <= DUR_HI:
                ann.append((o["end"], o["val"]))
        if len(ann) > len(best):
            best = ann
    if not best:
        return None, None
    # dedupe by end (keep last filed -> already ordered by SEC; take max val-stable: last)
    by_end = {}
    for end, val in best:
        by_end[end] = val
    ends = sorted(by_end)
    latest_end = ends[-1]
    latest = by_end[latest_end]
    le = datetime.date.fromisoformat(latest_end)
    prior = None
    for end in reversed(ends[:-1]):
        gap = (le - datetime.date.fromisoformat(end)).days
        if 300 <= gap <= 430:
            prior = by_end[end]
            break
    return latest, prior


def _inst(g, concepts, unit="USD"):
    """Return (latest_instant, prior_instant ~1yr earlier) balance values at T."""
    obs = _obs(g, concepts, unit)
    if not obs:
        return None, None
    by_end = {}
    for o in obs:
        by_end[o["end"]] = o["val"]         # SEC lists in filing order; last wins
    ends = sorted(by_end)
    latest_end = ends[-1]
    latest = by_end[latest_end]
    le = datetime.date.fromisoformat(latest_end)
    prior = None
    for end in reversed(ends[:-1]):
        gap = (le - datetime.date.fromisoformat(end)).days
        if 300 <= gap <= 430:
            prior = by_end[end]
            break
    return latest, prior


def _annual3(g, concepts, unit="USD"):
    """Latest three annual flow values (t, t-1, t-2) for 2nd-derivative signals."""
    best = []
    for c in concepts:
        obs = (g.get(c, {}) or {}).get("units", {}).get(unit, [])
        ann = {}
        for o in obs:
            if not (o.get("filed") and o["filed"] <= T.isoformat()):
                continue
            if o.get("val") is None or not o.get("start") or not o.get("end"):
                continue
            try:
                d = (datetime.date.fromisoformat(o["end"]) - datetime.date.fromisoformat(o["start"])).days
            except Exception:
                continue
            if DUR_LO <= d <= DUR_HI:
                ann[o["end"]] = o["val"]
        if len(ann) > len(best):
            best = ann
    if not best:
        return []
    ends = sorted(best)
    out = [best[e] for e in ends[-3:]]
    return out


def compute_signals(g):
    """Point-in-time signal dict from one company's us-gaap facts blob."""
    assets, assets_p = _inst(g, ASSETS)
    equity, _ = _inst(g, EQUITY)
    cur_a, cur_a_p = _inst(g, CUR_A)
    cur_l, cur_l_p = _inst(g, CUR_L)
    ltd, ltd_p = _inst(g, LTDEBT)
    sh, sh_p = _inst(g, SHARES, unit="shares")
    ni, ni_p = _annual(g, NI)
    cfo, _ = _annual(g, CFO)
    rev, rev_p = _annual(g, REV)
    gross, _ = _annual(g, GROSS)
    cogs, _ = _annual(g, COGS)
    if gross is None and rev is not None and cogs is not None:
        gross = rev - cogs
    if assets is None or assets == 0:
        return None

    d = {"assets": assets, "equity": equity, "ni": ni, "cfo": cfo, "rev": rev,
         "gross": gross, "shares_pit": sh}

    # --- Piotroski F-score (9) --------------------------------------------
    f = 0
    comps = {}
    roa = (ni / assets) if ni is not None else None
    comps["F_roa_pos"] = 1 if (roa is not None and roa > 0) else 0
    comps["F_cfo_pos"] = 1 if (cfo is not None and cfo > 0) else 0
    # ROA change
    roa_p = (ni_p / assets_p) if (ni_p is not None and assets_p) else None
    comps["F_droa_pos"] = 1 if (roa is not None and roa_p is not None and roa > roa_p) else 0
    # accrual: CFO > NI
    comps["F_accrual"] = 1 if (cfo is not None and ni is not None and cfo > ni) else 0
    # leverage down (LT debt / assets)
    lev = (ltd / assets) if (ltd is not None) else None
    lev_p = (ltd_p / assets_p) if (ltd_p is not None and assets_p) else None
    comps["F_lev_down"] = 1 if (lev is not None and lev_p is not None and lev < lev_p) else 0
    # current ratio up
    cr = (cur_a / cur_l) if (cur_a is not None and cur_l) else None
    cr_p = (cur_a_p / cur_l_p) if (cur_a_p is not None and cur_l_p) else None
    comps["F_curratio_up"] = 1 if (cr is not None and cr_p is not None and cr > cr_p) else 0
    # no dilution
    comps["F_no_dilution"] = 1 if (sh is not None and sh_p is not None and sh <= sh_p * 1.001) else 0
    # gross margin up
    gm = (gross / rev) if (gross is not None and rev) else None
    gross_pp, rev_pp = None, None  # prior gross/rev via annual3
    g3 = _annual3(g, GROSS)
    r3 = _annual3(g, REV)
    gm_p = None
    if len(r3) >= 2:
        if len(g3) >= 2 and r3[-2]:
            gm_p = g3[-2] / r3[-2]
        elif cogs is not None and r3[-2]:
            pass
    comps["F_gm_up"] = 1 if (gm is not None and gm_p is not None and gm > gm_p) else 0
    # asset turnover up
    at = (rev / assets) if (rev is not None and assets) else None
    at_p = (rev_p / assets_p) if (rev_p is not None and assets_p) else None
    comps["F_turn_up"] = 1 if (at is not None and at_p is not None and at > at_p) else 0
    f = sum(comps.values())
    d.update(comps)
    d["f_score"] = f

    # --- Sloan accruals (lower better -> store negative accrual = quality) --
    if ni is not None and cfo is not None:
        d["accrual_quality"] = -((ni - cfo) / assets)     # higher = cleaner earnings
    else:
        d["accrual_quality"] = None
    # --- Novy-Marx gross profitability ------------------------------------
    d["gross_profitability"] = (gross / assets) if gross is not None else None
    # --- N1 decline-deceleration (2nd derivative of revenue) --------------
    if len(r3) == 3 and r3[0] and r3[1]:
        yoy_recent = (r3[2] - r3[1]) / abs(r3[1]) if r3[1] else None
        yoy_prior = (r3[1] - r3[0]) / abs(r3[0]) if r3[0] else None
        if yoy_recent is not None and yoy_prior is not None:
            d["rev_yoy_recent"] = yoy_recent
            d["rev_yoy_prior"] = yoy_prior
            # decline decelerating: still <=0 recent but improving vs prior
            d["decline_decel"] = 1 if (yoy_recent < 0.05 and yoy_recent > yoy_prior) else 0
            d["accel"] = yoy_recent - yoy_prior           # continuous 2nd-derivative
    return d


def main():
    # cik -> tickers
    tickers_by_cik = defaultdict(list)
    ef = pd.read_csv("edgar_universe_facts.csv", low_memory=False)
    for _, r in ef.iterrows():
        try:
            tickers_by_cik[int(r["cik"])].append(r["symbol"])
        except Exception:
            pass

    # forward returns (realized) + current mcap for cheapness reconstruction
    yc = pd.read_csv("yahoo_chart_fill.csv")
    fwd = dict(zip(yc["symbol"], yc["momentum_12m"]))
    ag = pd.read_csv("asymmetry_global.csv", low_memory=False)
    mcap = dict(zip(ag["symbol"], ag.get("market_cap")))

    rows = []
    files = glob.glob("edgar_cache/*.json.gz")
    for i, fpath in enumerate(files):
        if i % 1500 == 0:
            print(f"  {i}/{len(files)}", file=sys.stderr)
        try:
            cik = int(os.path.basename(fpath).replace("CIK", "").replace(".json.gz", ""))
        except Exception:
            continue
        syms = [s for s in tickers_by_cik.get(cik, []) if s in fwd]
        if not syms:
            continue
        try:
            g = json.loads(gzip.open(fpath, "rt").read()).get("facts", {}).get("us-gaap", {})
        except Exception:
            continue
        sig = compute_signals(g)
        if sig is None:
            continue
        for sym in syms:
            fr = fwd.get(sym)
            if fr is None or pd.isna(fr):
                continue
            mc = mcap.get(sym)
            row = {"symbol": sym, "fwd_return": fr, **sig}
            # cheapness at T: price_at_T -> mcap_T = mcap_now / (1+fwd)
            if mc is not None and not pd.isna(mc) and (1 + fr) != 0:
                mcap_T = mc / (1 + fr)
                row["mcap_T"] = mcap_T
                if sig.get("equity") and sig["equity"] > 0:
                    row["pb_T"] = mcap_T / sig["equity"]
                if sig.get("ni") is not None and mcap_T > 0:
                    row["eyield_T"] = sig["ni"] / mcap_T
            rows.append(row)

    df = pd.DataFrame(rows).drop_duplicates("symbol")
    df.to_csv("backtest_panel.csv", index=False)
    print(f"\npanel: {len(df)} tickers with PIT signals + realized fwd return", file=sys.stderr)
    return df


if __name__ == "__main__":
    main()
