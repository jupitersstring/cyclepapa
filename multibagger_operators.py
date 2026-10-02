"""Third forensic investigation: PROFITABLE OPERATORS — the population that is
neither asset-based nor pre-profit nor a drug developer — mined for more lift
and for the archetypes the pooled study did not name -> MULTIBAGGER_OPERATORS.md

Population (mb_panel.parquet, point-in-time): operating margin >= 0 AND FCF
margin >= 0 at the month-end, not Energy / Materials / Real Estate /
Utilities or an asset-heavy industry, not a drug developer.

Operator measures added to the study's ~400 features (the manipulations of
the endpoints an operator is judged by):
  operating leverage    EBIT growth / revenue growth; incremental margin
  earnings quality      cash margin minus accounting margin; CFO / NI;
                        receivable- and inventory-days drift vs revenue
  capital cycle         capex / D&A and its roll-off (capex falling while
                        revenue holds = the harvest ahead)
  dilution-adjusted     revenue growth net of share growth; shareholder yield
  path shape            V-shape (rise off the 52w low while still far from
                        the high), coil (tight 2y range x compressed vol),
                        base age
  valuation vs growth   FCF yield + growth, EV/EBIT vs EBIT growth, P/E vs
                        revenue growth (the Lynch-shaped ratios)
  sector-relative       P/S, EV/EBIT, op margin, growth, ROIC ranked within
                        month x sector (the peer frame the tape uses)
  industry-relative     the same and more (P/B, FCF yield, gross margin,
                        acceleration, drawdown, returns, size) ranked within
                        month x INDUSTRY (thin industries fall back to the
                        sector); the industry's own tape that month (median
                        26w / 52w return, distance from high, breadth, growth,
                        margin change) and the name's position against it
  quality x price       ROIC x FCF yield

What is asked of it:
  1. base rates, k-means / GMM archetypes on the operator population
  2. patterns by lift (3x/24m and 10x/5y), full population
  3. NOT FALLEN: patterns among operators >= 60% of their 5-year high — the
     family the fallen-dominated pooled study buried
  4. NEAR HIGHS: patterns among operators within 15% of the 52w high — the
     continuation archetypes
  5. UNCOVERED: month-ends no implemented multibagger archetype claims
     (the study's own definitions of the eleven + the four segment ones)
     — clustered and mined for what is left
  6. REFINEMENT of the operator archetypes (inflecting operator, margin
     inflection under a weak tape, grew-into-valuation, sequence
     pre-ignition) with the new measures in the candidate conditions
  7. lift by size bucket and by quality tercile inside each operator archetype
  8. winners vs same-population lookalikes with the new measures
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc
import multibagger_forensics as mf
import multibagger_lift2 as L2
import multibagger_mine as mm
import multibagger_segments as ms

MD = "MULTIBAGGER_OPERATORS.md"
LABEL = "t3_24"


def add_measures(d: pd.DataFrame) -> pd.DataFrame:
    g = lambda c: d[c] if c in d.columns else pd.Series(np.nan, index=d.index)
    rg = g("rev_g1")
    d["op_lev"] = (g("ebit_g1") / rg).where(rg.abs() >= 0.02).clip(-20, 20)
    d["op_cash_gap"] = g("fcf_margin") - g("npm")                     # cash margin vs accounting margin
    d["op_wc_drift"] = g("dso_d1").fillna(0) + g("inv_rev_d1").fillna(0)   # receivable + inventory days drift
    d["op_capex_rolloff"] = (-g("capex_rev_d1")).where(g("capex_da") > 1.0)  # capex still above D&A but falling
    d["op_dil_adj_g"] = rg - g("share_g1")
    d["op_sh_yield"] = g("buyback_yield").fillna(0) + g("div_yield").fillna(0)
    d["op_v_shape"] = g("up_lo52") * (1 - g("dist_hi52"))
    d["op_coil"] = -(g("range104").rank(pct=True) + g("vol_ratio").rank(pct=True))
    d["op_base_age"] = g("wks_since_hi52")
    d["op_fcfy_plus_g"] = g("fcf_yield") + rg
    d["op_evebit_vs_g"] = (g("ev_ebit") / (1 + g("ebit_g1"))).where((g("ev_ebit") > 0) & (g("ebit_g1") > -0.9))
    d["op_pe_vs_g"] = (g("pe") / (rg * 100)).where((g("pe") > 0) & (rg > 0.02))
    d["op_roic_x_fcfy"] = g("roic").clip(-1, 1) * g("fcf_yield").clip(-1, 1)
    # SECTOR and INDUSTRY frames: the name against its peers at that month —
    # its multiples, returns, margins and growth ranked within month x sector
    # and within month x industry (the finer frame; an industry with fewer
    # than 12 names that month falls back to the sector), and the PEER
    # GROUP'S OWN TAPE (median 26w / 52w return and distance from the 5-year
    # high of the industry that month: the wave the name sits in) with the
    # name's position relative to it
    ym = d["week"].dt.to_period("M").astype(str)
    sec = ym + "|" + d["sector"].fillna("?").astype(str)
    indk = ym + "|" + d["industry"].fillna("?").astype(str)
    thin = indk.map(indk.value_counts()) < 12
    indk = indk.where(~thin, sec)
    REL = (("ps", "ps"), ("ev_ebit", "evebit"), ("opm", "opm"), ("rev_g1", "growth"), ("roic", "roic"),
           ("gm", "gm"), ("fcf_yield", "fcfy"), ("pb", "pb"), ("rev_accel", "accel"), ("dist_hi260", "disthi"),
           ("r52", "r52"), ("r26", "r26"), ("vol52", "vol"), ("mcap_usd_log", "size"))
    for c, nm in REL:
        d[f"op_sec_{nm}"] = g(c).groupby(sec).rank(pct=True).astype("float32")
        d[f"op_ind_{nm}"] = g(c).groupby(indk).rank(pct=True).astype("float32")
    for c, nm in (("r26", "r26"), ("r52", "r52"), ("dist_hi260", "disthi"), ("rev_g1", "growth"), ("opm_d1", "opm_d1")):
        med = g(c).groupby(indk).transform("median")
        d[f"ind_tape_{nm}"] = med.astype("float32")                    # the industry's own state
        d[f"op_vs_ind_{nm}"] = (g(c) - med).astype("float32")           # the name against it
    d["ind_breadth_up52"] = (g("r52") > 0).groupby(indk).transform("mean").astype("float32")
    # MARKET frame: the country's own tape that month (median distance from
    # the 5-year high, 1y return, breadth) and the name against it — the
    # wave the Turkish 2020 / SUZLON 2019 / CS.TO 2019 ten-baggers sat in
    mk = ym + "|" + d["market"].astype(str)
    for c, nm in (("dist_hi260", "disthi"), ("r52", "r52"), ("r26", "r26")):
        med = g(c).groupby(mk).transform("median")
        d[f"mkt_tape_{nm}"] = med.astype("float32")
        d[f"op_vs_mkt_{nm}"] = (g(c) - med).astype("float32")
    d["mkt_breadth_up52"] = (g("r52") > 0).groupby(mk).transform("mean").astype("float32")
    return d


OP_BLOCKS = {
    "operating_leverage": [("op_lev", 1), ("inc_margin", 1)],
    "earnings_quality": [("op_cash_gap", 1), ("cfo_ni", 1), ("op_wc_drift", -1)],
    "capital_cycle": [("op_capex_rolloff", 1), ("capex_da", -1)],
    "dilution_adjusted": [("op_dil_adj_g", 1), ("op_sh_yield", 1)],
    "path_shape": [("op_v_shape", 1), ("op_coil", 1), ("op_base_age", 1)],
    "value_vs_growth": [("op_fcfy_plus_g", 1), ("op_evebit_vs_g", -1), ("op_pe_vs_g", -1)],
    "sector_relative": [("op_sec_ps", -1), ("op_sec_evebit", -1), ("op_sec_opm", 1), ("op_sec_growth", 1),
                        ("op_sec_roic", 1)],
    "industry_cheap": [("op_ind_ps", -1), ("op_ind_evebit", -1), ("op_ind_pb", -1), ("op_ind_fcfy", 1)],
    "industry_quality": [("op_ind_opm", 1), ("op_ind_roic", 1), ("op_ind_gm", 1)],
    "industry_growth": [("op_ind_growth", 1), ("op_ind_accel", 1)],
    "industry_laggard": [("op_ind_disthi", -1), ("op_ind_r52", -1), ("op_ind_r26", -1),
                         ("op_vs_ind_r52", -1), ("op_vs_ind_disthi", -1)],
    "industry_wave": [("ind_tape_r26", 1), ("ind_tape_r52", 1), ("ind_tape_disthi", 1), ("ind_breadth_up52", 1),
                      ("ind_tape_growth", 1), ("ind_tape_opm_d1", 1)],
    "market_wave": [("mkt_tape_r26", 1), ("mkt_tape_r52", 1), ("mkt_tape_disthi", 1), ("mkt_breadth_up52", 1)],
    "vs_market": [("op_vs_mkt_r52", 1), ("op_vs_mkt_disthi", 1)],
    "quality_x_price": [("op_roic_x_fcfy", 1)],
}


def segment_archetypes(d: pd.DataFrame) -> dict:
    """The four segment archetypes as the segment study defined them (so the
    uncovered population is what NO implemented archetype claims)."""
    g = lambda c: d[c] if c in d.columns else pd.Series(np.nan, index=d.index)
    fallen = g("dist_hi260") <= 0.40
    informed = (g("ins_buy_quarters_4q") >= 2) | (g("bo_new_holders_12m") >= 1) | (g("st_insider_buying") == 1)
    nl = (g("gap_sales_1y") > 0) | (g("gap_sales_2y") > 0) | (g("gap_sales_3y") > 0)
    return {
        "asset_trough_informed": d["asset"] & fallen & nl & informed,
        "preprofit_beats_rewarded": d["preprofit"] & (g("ignored_beats_2y") == 0) & (g("beats_4q") >= 2),
        "preprofit_freefall_informed": d["preprofit"] & fallen & informed,
        "biotech_financed_hiring": d["bio"] & (g("dist_hi260") <= 0.5) & (g("share_g3") >= 0.10)
                                   & ((g("emp_g1") >= 0.10) | informed) & (g("netcash_mcap") > 0),
    }


def operator_archetypes(d: pd.DataFrame) -> dict:
    """The four operator archetypes as implemented in the engine, in the
    panel's vocabulary (needs add_measures' peer and market frames)."""
    g = lambda c: d[c] if c in d.columns else pd.Series(np.nan, index=d.index)
    deep = ((g("ev_ebit").between(0, 6)) | (g("pb").between(0, 0.7, inclusive="right")) | (g("ps") <= 0.3))
    debt_not_rising = ~(g("tr_debt_streak") > 0) | (g("netcash_mcap") >= 0) | g("nd_ebitda").between(0, 1.0)
    depressed = (g("mkt_tape_disthi") <= 0.70) | (g("ind_tape_disthi") <= 0.70)
    price_ahead = (g("gap_sales_3y") < 0) | (g("gap_sales_1y") < 0)
    ind_wave = (g("ind_breadth_up52") >= 0.5) | (g("ind_tape_r52") > 0)
    margin_up = (g("opm_d1") > 0.01) | ((g("tr_opm_slope8") > 0) & (g("tr_opm_consist") >= 0.6))
    return {
        "wave_neglected_value_accel": (deep | (g("op_ind_evebit") <= 0.2)) & (g("n_analysts").fillna(0) <= 2)
                                      & (g("rev_accel") > 0) & debt_not_rising & depressed,
        "leader_in_wave": (g("n_analysts") >= 8) & price_ahead & (g("vol52") >= 0.45) & margin_up
                          & (g("rev_g1") >= 0.15) & ind_wave,
        "improving_unturned_sellside": (g("rev_g1") > 0) & (g("opm_d1") > 0) & ~(g("buy_share_d12") > 0)
                                       & ((g("op_ind_gm") <= 0.35) | (g("gm") < 0.25))
                                       & ((g("ps_vs_own") > 1.0) | (g("r52") > 0.20)),
        "peer_worst_cheapest": (g("op_ind_evebit") <= 0.20) & (g("op_ind_roic") <= 0.25)
                               & ((g("fcf_margin") <= 0.03) | (g("op_ind_ps") <= 0.25)),
        # from the not-fallen / near-highs / uncovered passes
        "compounder_insiders_at_high": (g("dist_hi52") >= 0.85) & (g("op_ind_roic") >= 0.75) & (g("rd_rev") >= 0.08)
                                       & ((g("ins_buy_quarters_4q") >= 2) | (g("st_insider_buying") == 1)),
        "hiring_beating_uncovered": ((g("emp_g1") >= 0.15) | (g("emp_g1").isna() & (g("rev_g1") >= 0.20)))
                                    & (g("opm_vs_5y") >= 0.02) & ((g("beats_4q") >= 3) | (g("surprise_4q") > 0))
                                    & (g("n_analysts").fillna(0) <= 1) & g("dist_hi260").between(0.35, 0.80),
        "cheap_growth_targets_up": (g("rev_g1") >= 0.15) & (g("ev_ebit").between(0, 10) | ((g("fcf_yield") + g("rev_g1")) >= 0.20))
                                   & (g("pt_rev_6m") > 0) & (g("dist_hi260") >= 0.60),
    }


def _pat(L, d, R, lab, title, min_events):
    if lab in d.columns and (d[lab] == 1).sum() >= max(60, min_events):
        pats = mm.mine_patterns(d, R, lab, min_events=min_events)
        L.append(f"\n### {title}\n")
        L.append(pats.head(25).round(3).to_markdown(index=False))
        return pats
    L.append(f"\n### {title}\n\ntoo few events ({int((d[lab] == 1).sum()) if lab in d.columns else 0})\n")
    return pd.DataFrame()


def subpop(L, d, mask, name, title, feats):
    """Base rate, clusters and patterns inside a sub-population, features
    re-ranked INSIDE it."""
    s = d[mask].reset_index(drop=True)
    L.append(f"\n## {title}\n")
    if len(s) < 5000 or (s[LABEL] == 1).sum() < 150:
        L.append(f"too few observations ({len(s):,} month-ends, {int((s[LABEL]==1).sum())} multibagger month-ends)\n")
        return
    base = mm.base_rate(s, LABEL)
    b10 = mm.base_rate(s, "t10_60")
    L.append(f"{len(s):,} month-ends, {s['symbol'].nunique():,} symbols; 3x-within-24m rate {base:.2%}, "
             f"10x-within-5y rate {b10:.2%} (features ranked within month x market inside this sub-population).\n")
    feats2, R, S, Z = mm.prepare(s)
    sel, tab, n_ent = mm.cluster_entries(s, feats2, R, S, Z, LABEL, "kmeans", kmax=8)
    mm.describe(L, tab, "k-means archetypes", sel, n_ent, base)
    p3 = _pat(L, s, R, LABEL, "Patterns ranked by lift — 3x within 24 months", 30)
    p3.to_csv(f"mb_op_{name}_patterns_t3_24.csv", index=False)
    p10 = _pat(L, s, R, "t10_60", "Patterns ranked by lift — 10x within 5 years", 25)
    p10.to_csv(f"mb_op_{name}_patterns_t10_60.csv", index=False)


def main():
    d = mc.load()
    d = mm.outcome_cols(d)
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "sector", "industry"], low_memory=False).drop_duplicates("symbol")
    d = d.merge(g, on="symbol", how="left")
    d = ms.add_measures(d)
    ind = d["industry"].fillna("").str.lower()
    d["asset"] = ((d["sector"].isin(["Energy", "Materials", "Real Estate", "Utilities"])
                   | ind.str.contains(ms.ASSET_IND, regex=True)) & ~d["bio"])
    d["preprofit"] = ((d["opm"] < 0) | (d["fcf_margin"] < 0)) & ~d["bio"] & ~d["asset"]
    op = ((d["opm"] >= 0) & (d["fcf_margin"] >= 0)).fillna(False) & ~d["bio"] & ~d["asset"]
    d = add_measures(d)                 # peer frames on the WHOLE panel: the industry's tape is the industry's
    # the implemented archetypes' claims, on the FULL panel (before the cut)
    A = L2.archetypes(d); A.update(segment_archetypes(d)); A.update(operator_archetypes(d))
    covered = pd.concat([m.fillna(False) for m in A.values()], axis=1).any(axis=1)
    for k, m in A.items():
        d[f"arch_{k}"] = m.fillna(False).astype(int)
    d["covered"] = covered.astype(int)
    d = d[op].reset_index(drop=True)
    mc.BLOCKS = {**mc.BLOCKS, **OP_BLOCKS}
    mc.FEATS = mc.FEATS + [c for c in d.columns if c.startswith(("pp_", "as_", "op_", "ind_", "mkt_"))]
    feats = mc.feats_all(d)

    L = ["# Multibaggers among profitable operators\n",
         "The population the asset-based and pre-profit studies left: operating margin and FCF margin both "
         "non-negative, not an asset business, not a drug developer. Operator measures added (operating "
         "leverage, earnings quality, capital cycle, dilution-adjusted growth, path shape, value vs growth, "
         "sector-relative ranks, quality x price). Every feature ranked within month x market inside the "
         "population; sub-populations re-ranked inside themselves.\n"]
    base = mm.base_rate(d, LABEL); b10 = mm.base_rate(d, "t10_60")
    L.append(f"{len(d):,} month-ends, {d['symbol'].nunique():,} symbols; 3x-within-24m rate {base:.2%}, "
             f"10x-within-5y rate {b10:.2%}; {d['covered'].mean():.1%} of month-ends claimed by an implemented "
             f"archetype, holding {d.loc[d['covered'] == 1, LABEL].sum() / d[LABEL].sum():.1%} of the multibagger month-ends.\n")

    # 1. archetypes
    L.append("\n# 1. Archetypes of the operator population\n")
    feats, R, S, Z = mm.prepare(d)
    for mth in ("kmeans", "gmm"):
        sel, tab, n_ent = mm.cluster_entries(d, feats, R, S, Z, LABEL, mth, kmax=10)
        mm.describe(L, tab, {"kmeans": "k-means archetypes", "gmm": "Gaussian-mixture archetypes"}[mth], sel, n_ent, base)
    # 2. patterns, full population
    L.append("\n# 2. Patterns by lift, whole operator population\n")
    _pat(L, d, R, LABEL, "3x within 24 months", 40).to_csv("mb_op_all_patterns_t3_24.csv", index=False)
    _pat(L, d, R, "t10_60", "10x within 5 years", 25).to_csv("mb_op_all_patterns_t10_60.csv", index=False)
    # 6. refinement of the operator archetypes (before the sub-populations, R is for the full population)
    L.append("\n# 6. Refining the operator archetypes with the new measures\n")
    M, names = L2.conditions(d, R)
    for k in ("wave_neglected_value_accel", "leader_in_wave", "improving_unturned_sellside", "peer_worst_cheapest",
              "margin_inflect_weak_tape", "sequence_preignition", "tree_recipe", "left_for_dead_value",
              "smart_money_wreckage", "fallen_below_cycle"):
        mask = d[f"arch_{k}"] == 1
        st = L2.stats(d, mask)
        if not st:
            continue
        L.append(f"\n## {k}: n={st['n']:,}, rate {st['rate']:.2%} (lift {st['rate']/base:.2f}x), "
                 f"blow-up {st['p_blowup_50']:.0%}, 10x/5y {st['t10_60_rate']:.1%}\n")
        up, down = L2.refine(d, M, names, mask, st["rate"], min_n=120, min_events=20)
        L.append("raises the rate most:\n\n" + up.round(3).to_markdown(index=False))
        L.append("\nlowers it most:\n\n" + down.round(3).to_markdown(index=False))
    # 7. where inside each archetype
    L.append("\n# 7. Size and quality inside the operator archetypes\n")
    d["size_bucket"] = pd.cut(d["mcap_usd_log"], [0, 7.7, 8.5, 9.3, 20], labels=["<50M", "50-300M", "300M-2B", ">2B"])
    d["quality_tercile"] = pd.qcut(R["roic"], 3, labels=["low ROIC", "mid", "high ROIC"]) if "roic" in R.columns else np.nan
    d["year"] = d["week"].dt.year
    for k in ("wave_neglected_value_accel", "leader_in_wave", "improving_unturned_sellside", "peer_worst_cheapest",
              "margin_inflect_weak_tape", "sequence_preignition", "left_for_dead_value", "smart_money_wreckage"):
        mask = d[f"arch_{k}"] == 1
        if mask.sum() < 400:
            continue
        for key in ("size_bucket", "quality_tercile", "year", "market"):
            try:
                t = L2.by_group(d, mask, key, min_n=150)
            except Exception as exc:          # a split that cannot be formed must not end the report
                L.append(f"\n{k} by {key}: not computable ({exc})\n")
                continue
            if len(t):
                L.append(f"\n{k} by {key}:\n\n" + t.round(3).to_markdown(index=False))
    # 8. lookalikes
    L.append("\n# 8. Winners vs same-population lookalikes (paired rank differences, 90% intervals)\n")
    d2 = d.sort_values(["symbol", "week"]).reset_index(drop=True)
    d2["ym"] = d2["week"].dt.to_period("M")
    ent2 = mc.entries(d2, LABEL)
    pairs = mf.matched_controls(d2, d2.index[ent2])
    if len(pairs):
        R2 = mc.ranked(d2, feats); R2 = R2.loc[:, ~R2.columns.duplicated()]
        ld = mf.lookalike_diff(d2, R2, pairs)
        L.append(ld[ld["significant"]].head(40).round(3).to_markdown(index=False))
        new = ld[ld["feature"].str.startswith("op_")]
        L.append("\n\nthe operator measures specifically:\n\n" + new.round(3).to_markdown(index=False))
        del d2, R2
    del M, R, S, Z
    # 3-5. sub-populations
    open(MD, "w").write("\n".join(L))            # partial report survives a failure below
    for title, mask, name, ttl in (
            ("\n# 3. Not fallen: operators at >= 60% of their 5-year high\n", (d["dist_hi260"] >= 0.60).fillna(False), "notfallen", "Not fallen"),
            ("\n# 4. Near highs: operators within 15% of the 52-week high\n", (d["dist_hi52"] >= 0.85).fillna(False), "nearhigh", "Near highs"),
            ("\n# 5. Uncovered: month-ends no implemented archetype claims\n", d["covered"] == 0, "uncovered", "Uncovered")):
        L.append(title)
        try:
            subpop(L, d, mask, name, ttl, feats)
        except Exception as exc:
            L.append(f"\nfailed: {exc!r}\n")
        open(MD, "w").write("\n".join(L))
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
