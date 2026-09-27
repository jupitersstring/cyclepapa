"""Mining the UNCOVERED multibaggers for intuitive patterns with lift that
holds up -> MULTIBAGGER_UNCOVERED.md, mb_uncovered_candidates_*.csv

The month-ends no implemented archetype claims (the 22 rule archetypes, as
the studies define them) still hold more than half of the multibagger
month-ends among profitable operators. This mines THEM, with three rules of
its own:

  readable features   the story features, the divergences, the trend shapes,
                      the own-history percentiles, the path shape and the
                      peer / industry / market frames — not the raw FMP ratio
                      levels and their year changes (those repeat the story
                      features under opaque names); every condition is
                      rendered in words
  USD outcomes        the labels are the USD recomputation (a lira triple is
                      not a triple)
  demonstrated lift   a pattern is a CANDIDATE only if its lift is >= 2x in
                      BOTH halves of the sample (month-ends to 2018-12 and
                      from 2019-01), its events span >= 4 calendar years and
                      >= 3 markets, and no single market holds more than 60%
                      of them; blow-up (worst close -50% within 24 months)
                      and the 10x rate are shown beside every one

Populations mined: all uncovered (non-biotech); uncovered profitable
operators; uncovered NOT fallen (>= 60% of the 5-year high); uncovered
fallen. Each re-ranked inside itself. Nothing here changes an archetype:
the candidates are for reading and choosing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc
import multibagger_lift2 as L2
import multibagger_mine as mm
import multibagger_operators as mo
import multibagger_segments as ms

MD = "MULTIBAGGER_UNCOVERED.md"
LABEL = "t3_24"
SPLIT = pd.Timestamp("2018-12-31")

WORDS = {
    "rev_g1": "revenue growth 1y", "rev_g2": "revenue growth 2y", "rev_accel": "revenue acceleration",
    "rev_q_yoy": "latest-quarter revenue growth", "rev_q_accel": "quarterly revenue acceleration",
    "gm": "gross margin", "opm": "operating margin", "npm": "net margin", "gm_d1": "gross margin change 1y",
    "opm_d1": "operating margin change 1y", "opm_d2": "operating margin change 2y", "opm_vs_5y": "margin vs own 5y",
    "inc_margin": "incremental margin", "ebit_g1": "EBIT growth 1y", "eps_g1": "EPS growth 1y",
    "rd_rev": "R&D / revenue", "sga_rev": "SG&A / revenue", "sga_rev_d1": "SG&A ratio change",
    "share_g1": "share count change 1y", "share_g3": "share count change 3y", "fcf_margin": "FCF margin",
    "fcf_margin_d1": "FCF margin change", "cfo_ni": "cash conversion (CFO/NI)", "capex_rev": "capex / revenue",
    "capex_rev_d1": "capex ratio change", "capex_da": "capex / D&A", "sbc_rev": "SBC / revenue",
    "netcash_mcap": "net cash / mcap", "nd_ebitda": "net debt / EBITDA", "debt_chg1": "debt change 1y",
    "current_ratio": "current ratio", "equity_assets": "equity / assets", "intang_assets": "intangibles / assets",
    "ncav_mcap": "NCAV / mcap", "buyback_yield": "buyback yield", "div_yield": "dividend yield", "roic": "ROIC",
    "roic_d1": "ROIC change 1y", "roe": "ROE", "asset_turn_d1": "asset turnover change", "dso_d1": "receivable days change",
    "inv_rev_d1": "inventory / revenue change", "ps": "P/S", "ev_sales": "EV/sales", "ev_ebit": "EV/EBIT", "pe": "P/E",
    "pb": "P/B", "fcf_yield": "FCF yield", "earn_yield": "earnings yield", "ps_vs_own": "P/S vs own history",
    "evs_chg_1y": "EV/sales change 1y", "mcap_usd_log": "size", "emp_g1": "headcount growth",
    "rev_per_emp_g1": "revenue per employee growth", "n_analysts": "analysts", "buy_share": "analyst buy share",
    "buy_share_d12": "buy share change 12m", "upgrades_12m": "upgrades 12m", "downgrades_12m": "downgrades 12m",
    "months_since_up": "months since last upgrade", "beats_4q": "beats last 4q", "surprise_4q": "earnings surprise 4q",
    "ignored_beats_2y": "beats the market ignored", "react_beats_mean": "price reaction to beats", "last_react": "last earnings reaction",
    "pt_prem_12m": "target premium", "pt_rev_6m": "target revisions 6m", "ins_buy_quarters_4q": "insider-buy quarters",
    "ins_net_buy_4q": "insider net buying", "bo_new_holders_12m": "new 5% holders", "bo_increasing_12m": "5% holders adding",
    "r4": "return 4w", "r13": "return 13w", "r26": "return 26w", "r52": "return 1y", "r104": "return 2y", "r156": "return 3y",
    "r260": "return 5y", "rs26": "26w return vs market", "dist_hi52": "price / 52w high", "dist_hi260": "price / 5y high",
    "up_lo52": "rise off 52w low", "range104": "2y range", "pos104": "position in 2y range", "pos156": "position in 3y range",
    "maxdd104": "max drawdown 2y", "vol13": "volatility 13w", "vol52": "volatility 1y", "vol_ratio": "vol 13w / 1y",
    "dvol26_usd": "dollar volume", "dvol_trend": "volume trend", "updown26": "up/down volume", "dvol_z13": "volume surge",
    "above_ma30": "vs 30w MA", "ma30_slope13": "30w MA slope", "slope_brk": "trend break", "trend_r2_52": "trend strength 1y",
    "wks_since_hi52": "weeks since 52w high", "wks_since_lo260": "weeks since 5y low", "dd_time_share_260": "share of 5y in drawdown",
    "dvol_usd_log": "dollar volume", "gap_sales_1y": "sales/share ahead of price 1y", "gap_sales_2y": "sales/share ahead of price 2y",
    "gap_sales_3y": "sales/share ahead of price 3y", "gap_fcfps_1y": "FCF/share ahead of price 1y", "gap_eps_1y": "EPS ahead of price 1y",
    "gap_own_opm": "margin at own high, price at own low", "gap_own_roic": "ROIC at own high, price at own low",
    "gap_own_fcfps": "FCF/share at own high, price at own low", "gap_own_gm": "gross margin at own high, price at own low",
    "gap_trend_opm": "margin rising while price falls", "gap_trend_roic": "ROIC rising while price falls",
    "gap_perc_buyshare": "fundamentals up, sell side unturned", "gap_perc_targets": "fundamentals up, targets unmoved",
}
TR = {"revg": "revenue growth", "gm": "gross margin", "opm": "operating margin", "fcfm": "FCF margin", "roic": "ROIC",
      "shares": "share count", "debt": "debt"}
SHAPE = {"slope8": "8q slope", "accel": "acceleration", "consist": "trend consistency", "streak": "rising streak"}
FRAME = {"op_sec": "vs sector", "op_ind": "vs industry", "op_vs_ind": "minus industry", "op_vs_mkt": "minus market",
         "ind_tape": "industry's own", "mkt_tape": "market's own"}
REL = {"ps": "P/S", "evebit": "EV/EBIT", "opm": "op margin", "growth": "growth", "roic": "ROIC", "gm": "gross margin",
       "fcfy": "FCF yield", "pb": "P/B", "accel": "acceleration", "disthi": "distance from 5y high", "r52": "return 1y",
       "r26": "return 26w", "vol": "volatility", "size": "size", "opm_d1": "margin change"}


def words(cond: str) -> str:
    f, _, lvl = cond.rpartition(" ")
    if lvl not in ("LOW", "HIGH"):
        return "state: " + cond.replace("_", " ")
    name = None
    if f in WORDS:
        name = WORDS[f]
    elif f.startswith("tr_"):
        _, k, s = f.split("_", 2)
        name = f"{TR.get(k, k)} {SHAPE.get(s, s)}"
    elif f.startswith("kr_") and f.endswith("_own"):
        name = f[3:-4] + " vs own history"
    elif f.startswith(("op_sec_", "op_ind_", "op_vs_ind_", "op_vs_mkt_", "ind_tape_", "mkt_tape_")):
        for p, w in FRAME.items():
            if f.startswith(p + "_"):
                name = f"{REL.get(f[len(p)+1:], f[len(p)+1:])} {w}"
                break
    elif f.startswith("op_"):
        name = {"op_lev": "operating leverage", "op_cash_gap": "cash vs accounting margin", "op_wc_drift": "working-capital drift",
                "op_capex_rolloff": "capex roll-off", "op_dil_adj_g": "dilution-adjusted growth", "op_sh_yield": "shareholder yield",
                "op_v_shape": "V-shape recovery", "op_coil": "coiled range", "op_base_age": "base age",
                "op_fcfy_plus_g": "FCF yield + growth", "op_evebit_vs_g": "EV/EBIT vs growth", "op_pe_vs_g": "P/E vs growth",
                "op_roic_x_fcfy": "ROIC x FCF yield"}.get(f, f)
    elif f.startswith("pp_") or f.startswith("as_"):
        name = f[3:].replace("_", " ")
    elif f in ("ind_breadth_up52", "mkt_breadth_up52"):
        name = ("industry" if f.startswith("ind") else "market") + " breadth up on the year"
    if name is None:
        name = f.replace("_", " ")
    return f"{name} {'low' if lvl == 'LOW' else 'high'}"


def readable_features(R: pd.DataFrame) -> list:
    keep = []
    for c in R.columns:
        if c.startswith("st_") or c in mc.MISS:
            continue
        if c.startswith("kr_") and not c.endswith("_own"):
            continue                        # raw ratio levels / year changes: opaque duplicates
        keep.append(c)
    return keep


def mine(d, R, label, feats, min_events=40, min_share=0.0005, max_depth=4, beam=80, top=60):
    """Beam pattern search returning the rules AND their masks."""
    C, names = [], []
    for f in feats:
        r = R[f].to_numpy()
        C.append(r <= 0.2); names.append(f"{f} LOW")
        C.append(r >= 0.8); names.append(f"{f} HIGH")
    for s in [c for c in R.columns if c.startswith("st_")]:
        C.append(R[s].to_numpy() == 1); names.append(s[3:])
    M = np.vstack([np.nan_to_num(c, nan=0).astype(bool) for c in C])
    y = d[label].to_numpy(float); ok = ~np.isnan(y)
    w = d["w_cc"].to_numpy(float) * ok; y = np.nan_to_num(y)
    tot, br = w.sum(), (w * y).sum() / w.sum()

    def score(mask):
        ww = w[mask]; s = ww.sum(); ev = int((y[mask] > 0).sum())
        if s / tot < min_share or ev < min_events:
            return None
        return (ww * y[mask]).sum() / s / br, s / tot, ev

    singles, cand = [], []
    for i in range(len(names)):
        r = score(M[i])
        if r:
            singles.append(i); cand.append(((i,), r))
    cand.sort(key=lambda x: -x[1][0])
    beam_, allr = cand[:beam], list(cand)
    for _ in range(2, max_depth + 1):
        nxt = {}
        for rule, _r in beam_:
            bm = np.logical_and.reduce([M[i] for i in rule])
            for j in singles:
                if j in rule:
                    continue
                key = tuple(sorted(rule + (j,)))
                if key in nxt:
                    continue
                r = score(bm & M[j])
                if r:
                    nxt[key] = r
        lst = sorted(nxt.items(), key=lambda x: -x[1][0])
        allr += lst; beam_ = lst[:beam]
    allr.sort(key=lambda x: -x[1][0])
    keep, seen = [], []
    for rule, (lift, share, ev) in allr:
        m = np.logical_and.reduce([M[i] for i in rule])
        if any((m & k).sum() >= 0.7 * min(m.sum(), k.sum()) for k in seen):
            continue
        seen.append(m)
        keep.append({"rule": " & ".join(names[i] for i in rule), "conditions": [names[i] for i in rule],
                     "lift": lift, "share": share, "events": ev, "mask": m})
        if len(keep) >= top:
            break
    return keep, br


def robustness(d, rules, label, br_all):
    """Lift in both halves of time, markets and years of the events, blow-up,
    10x rate, examples — and whether the pattern qualifies."""
    y = d[label]; w = d["w_cc"]; wk = d["week"]
    early, late = wk <= SPLIT, wk > SPLIT
    rows = []
    for r in rules:
        m = pd.Series(r["mask"], index=d.index) & y.notna()
        ev = m & (y == 1)
        def lift(mask):
            mm_ = m & mask
            return float(np.average(y[mm_], weights=w[mm_]) / np.average(y[mask & y.notna()], weights=w[mask & y.notna()])) if mm_.sum() >= 200 and (y[mm_] == 1).sum() >= 10 else np.nan
        le, ll = lift(early), lift(late)
        mk = d.loc[ev, "market"].value_counts(normalize=True)
        yrs = d.loc[ev, "week"].dt.year.nunique()
        fm = d.loc[m, "fwd_min_24"].dropna()
        t10 = d.loc[m, "t10_60"].dropna()
        qualifies = (np.nan_to_num(le) >= 2) and (np.nan_to_num(ll) >= 2) and yrs >= 4 and len(mk) >= 3 and (mk.iloc[0] if len(mk) else 1) <= 0.6
        rows.append({"pattern": r["rule"], "in_words": "; ".join(words(c) for c in r["conditions"]),
                     "lift": r["lift"], "lift_to_2018": le, "lift_2019_on": ll, "events": r["events"],
                     "share_of_month_ends": r["share"], "years": yrs, "markets": len(mk),
                     "top_market": f"{mk.index[0]} {mk.iloc[0]:.0%}" if len(mk) else "",
                     "p_blowup_50": float((fm <= -0.5).mean()) if len(fm) >= 40 else np.nan,
                     "t10_60_rate": float(t10.mean()) if len(t10) >= 40 else np.nan,
                     "median_months_to_3x": float(d.loc[ev, "months_to_3x"].median()) if ev.any() else np.nan,
                     "qualifies": bool(qualifies), "examples": mm.examples(d, d.index[ev], 6)})
    t = pd.DataFrame(rows)
    return t.sort_values(["qualifies", "lift"], ascending=[False, False])


def population(L, d, name, title):
    L.append(f"\n# {title}\n")
    if len(d) < 5000 or (d[LABEL] == 1).sum() < 150:
        L.append(f"too few observations ({len(d):,} month-ends)\n"); return
    base = mm.base_rate(d, LABEL)
    L.append(f"{len(d):,} month-ends, {d['symbol'].nunique():,} symbols; USD 3x-within-24m rate {base:.2%}, "
             f"10x-within-5y rate {mm.base_rate(d, 't10_60'):.2%}; features ranked within month x market inside this population.\n")
    feats = mc.feats_all(d)
    R = mc.ranked(d, feats); R = R.loc[:, ~R.columns.duplicated()]
    rf = readable_features(R)
    for lab, ttl, me in ((LABEL, "3x within 24 months", 40), ("t10_60", "10x within 5 years", 25)):
        if (d[lab] == 1).sum() < 100:
            continue
        rules, br = mine(d, R, lab, rf, min_events=me)
        t = robustness(d, rules, lab, br)
        t.drop(columns=[]).to_csv(f"mb_uncovered_{name}_{lab}.csv", index=False)
        q = t[t["qualifies"]]
        L.append(f"\n## {ttl}: {len(q)} candidates that hold in both halves of time and across markets (of {len(t)} patterns mined)\n")
        cols = ["in_words", "lift", "lift_to_2018", "lift_2019_on", "events", "years", "markets", "top_market", "p_blowup_50",
                "t10_60_rate", "median_months_to_3x", "examples"]
        L.append(q.head(20)[cols].round(3).to_markdown(index=False) if len(q) else "none")
        L.append(f"\nthe strongest patterns that did NOT qualify (one era or one market):\n\n"
                 + t[~t["qualifies"]].head(8)[cols].round(3).to_markdown(index=False))


def main():
    d = mc.load(); d = mm.outcome_cols(d)
    d = d[~d["bio"]].reset_index(drop=True)
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "sector", "industry"], low_memory=False).drop_duplicates("symbol")
    d = d.merge(g, on="symbol", how="left")
    d = ms.add_measures(d); d = mo.add_measures(d)
    ind = d["industry"].fillna("").str.lower()
    d["asset"] = ((d["sector"].isin(["Energy", "Materials", "Real Estate", "Utilities"]) | ind.str.contains(ms.ASSET_IND, regex=True)))
    d["preprofit"] = ((d["opm"] < 0) | (d["fcf_margin"] < 0)) & ~d["asset"]
    A = L2.archetypes(d); A.update(mo.segment_archetypes(d)); A.update(mo.operator_archetypes(d))
    covered = pd.concat([m.fillna(False) for m in A.values()], axis=1).any(axis=1)
    mc.BLOCKS = {**mc.BLOCKS, **mo.OP_BLOCKS}
    mc.FEATS = mc.FEATS + [c for c in d.columns if c.startswith(("pp_", "as_", "op_", "ind_", "mkt_"))]
    ev = d[LABEL] == 1
    L = ["# Mining the uncovered multibaggers\n",
         f"{len(d):,} non-biotech month-ends; the 22 archetypes claim {covered.mean():.1%} of month-ends and "
         f"{(covered & ev).sum() / ev.sum():.1%} of the USD multibagger month-ends. Below: the rest, mined for readable "
         "patterns whose lift holds in both halves of time and across markets. Candidates only — nothing changes an archetype.\n"]
    u = d[~covered].reset_index(drop=True)
    population(L, u, "all", "Uncovered, all")
    op = ((u["opm"] >= 0) & (u["fcf_margin"] >= 0)).fillna(False) & ~u["asset"]
    population(L, u[op].reset_index(drop=True), "operators", "Uncovered profitable operators")
    population(L, u[(u["dist_hi260"] >= 0.6).fillna(False)].reset_index(drop=True), "notfallen", "Uncovered, not fallen (>= 60% of 5y high)")
    population(L, u[(u["dist_hi260"] <= 0.4).fillna(False)].reset_index(drop=True), "fallen", "Uncovered, fallen (<= 40% of 5y high)")
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
