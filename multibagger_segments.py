"""Multibaggers among ASSET-BASED businesses and PRE-PROFIT operators, mined
with the measures those populations are actually valued on
-> MULTIBAGGER_SEGMENTS.md

Populations (on the point-in-time panel, mb_panel.parquet):
  asset      Energy / Materials / Real Estate / Utilities sectors, plus
             shipping, marine, leasing, holding, REIT, mining, oil & gas,
             coal, steel, gold, silver, uranium, timber, farm industries
  preprofit  TTM operating loss or negative FCF, drug developers excluded
  biotech    drug developers (their own section, same machinery)

Population-specific measures added to every feature the study already has:
  asset      book / tangible-book value per share growth, P/B vs own history,
             debt-to-assets and its change (deleveraging), capex vs
             depreciation (reinvest vs harvest), asset turnover and trend,
             dividend and buyback yields, NCAV / mcap, margin vs own cycle,
             and the COMMODITY'S OWN TAPE at entry (oil / natural gas for
             Energy; copper / gold / silver for Materials): 26w and 52w
             return, distance from its 5-year high
  preprofit  runway in years (net cash / annual burn), burn shrinking, the
             margin slope and quarters to breakeven, gross margin and trend,
             dilution-adjusted revenue growth, SBC, opex discipline (SG&A /
             revenue change), R&D intensity, deferred-revenue growth proxy,
             financing dependence (share growth vs FCF)
For each: base rates, archetypes (k-means on the axes + population axes),
patterns ranked by lift (all conditions incl. the new measures), and winners
vs same-population lookalikes (paired, bootstrap intervals).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import multibagger_clusters as mc
import multibagger_forensics as mf
import multibagger_mine as mm

MD = "MULTIBAGGER_SEGMENTS.md"
LABEL = "t3_24"
ASSET_IND = r"shipping|marine|tanker|lessor|leasing|holding|reit|real estate|mining|oil|gas|coal|steel|aluminum|gold|silver|uranium|timber|farm|metals"
CMDTY = {"Energy": ["CLUSD", "NGUSD"], "Materials": ["HGUSD", "GCUSD", "SIUSD"]}


def commodity_tape() -> pd.DataFrame:
    """Weekly (W-FRI) 26w / 52w return and distance from the 5-year high for
    each commodity, keyed by week."""
    import fmp_client as fc
    frames = []
    for sym in sorted({s for v in CMDTY.values() for s in v}):
        try:
            r = fc.get_json("historical-price-eod/light", {"symbol": sym, "from": "2010-01-01"}, ttl=fc.TTL_SLOW) or []
        except fc.FMPError:
            r = []
        if not r:
            continue
        d = pd.DataFrame(r); d["date"] = pd.to_datetime(d["date"]); d["price"] = pd.to_numeric(d["price"], errors="coerce")
        w = d.set_index("date")["price"].resample("W-FRI").last().dropna()
        f = pd.DataFrame({"week": w.index, f"c_{sym}_r26": w / w.shift(26) - 1, f"c_{sym}_r52": w / w.shift(52) - 1,
                          f"c_{sym}_hi260": w / w.rolling(260, min_periods=104).max()})
        frames.append(f.set_index("week"))
    return pd.concat(frames, axis=1) if frames else pd.DataFrame()


def add_measures(d: pd.DataFrame) -> pd.DataFrame:
    g = lambda c: d[c] if c in d.columns else pd.Series(np.nan, index=d.index)
    # ---- pre-profit measures ----
    burn = (-g("fcf_yield")).where(g("fcf_yield") < 0)              # annual burn / mcap
    d["pp_runway_years"] = (g("netcash_mcap") / burn).where(burn > 0).clip(-1, 20)
    d["pp_burn_shrinking"] = ((g("fcf_margin_d1") > 0) & (g("fcf_margin") < 0)).astype(float)
    slope_q = g("tr_opm_slope8")
    d["pp_quarters_to_breakeven"] = ((-g("opm")) / slope_q).where((g("opm") < 0) & (slope_q > 0)).clip(0, 60)
    d["pp_loss_narrowing"] = ((g("opm") < 0) & (g("opm_d1") > 0)).astype(float)
    d["pp_dil_adj_rev_g"] = g("kr_revenuePerShare_g4").fillna(g("rev_g1") - g("share_g1"))
    d["pp_financing_dependence"] = (g("share_g1").clip(lower=0) - g("fcf_yield").clip(upper=0))
    d["pp_gm_x_growth"] = g("gm") * g("rev_g1")                     # the SaaS 'rule' ingredient
    # ---- asset measures ----
    d["as_book_growth"] = g("kr_bookValuePerShare_g4")
    d["as_tbv_growth"] = g("kr_tangibleBookValuePerShare_g4")
    d["as_pb_own"] = g("kr_priceToBookRatio_own")
    d["as_debt_assets"] = g("kr_debtToAssetsRatio")
    d["as_deleveraging"] = -g("kr_debtToAssetsRatio_d4")
    d["as_capex_da"] = g("capex_da")
    d["as_harvest"] = (g("capex_da") < 0.7).astype(float).where(g("capex_da").notna())
    d["as_asset_turn_d1"] = g("asset_turn_d1")
    d["as_payout"] = g("div_yield").fillna(0) + g("buyback_yield").fillna(0)
    return d


def attach_commodity(d: pd.DataFrame, ct: pd.DataFrame) -> pd.DataFrame:
    if not len(ct):
        return d
    x = d[["week", "sector"]].merge(ct, left_on="week", right_index=True, how="left")
    for m in ("r26", "r52", "hi260"):
        col = pd.Series(np.nan, index=d.index)
        for sec, syms in CMDTY.items():
            vals = pd.concat([x[f"c_{s}_{m}"] for s in syms if f"c_{s}_{m}" in x.columns], axis=1).mean(axis=1)
            col = col.where(~(d["sector"] == sec), vals)
        d[f"cmdty_{m}"] = col.values
    return d


EXTRA_BLOCKS = {
    "runway_and_burn": [("pp_runway_years", 1), ("pp_burn_shrinking", 1), ("fcf_margin_d1", 1), ("pp_financing_dependence", -1)],
    "path_to_profit": [("tr_opm_slope8", 1), ("pp_loss_narrowing", 1), ("pp_quarters_to_breakeven", -1), ("gm_d1", 1)],
    "unit_economics": [("gm", 1), ("pp_gm_x_growth", 1), ("rd_rev", 1), ("sga_rev_d1", -1)],
    "dilution": [("share_g1", -1), ("share_g3", -1), ("sbc_rev", -1), ("pp_dil_adj_rev_g", 1)],
    "asset_value": [("pb", -1), ("as_pb_own", -1), ("ncav_mcap", 1), ("as_book_growth", 1), ("as_tbv_growth", 1)],
    "asset_leverage": [("as_debt_assets", -1), ("as_deleveraging", 1), ("nd_ebitda", -1)],
    "reinvest_vs_harvest": [("as_capex_da", 1), ("capex_rev", 1), ("as_asset_turn_d1", 1), ("as_payout", 1)],
    "commodity_tape": [("cmdty_r26", 1), ("cmdty_r52", 1), ("cmdty_hi260", 1)],
}


def population_report(L, d, name, title):
    L.append(f"\n# {title}\n")
    if len(d) < 5000 or (d[LABEL] == 1).sum() < 150:
        L.append(f"too few observations ({len(d):,} month-ends, {int((d[LABEL]==1).sum())} multibagger month-ends)\n")
        return
    base = mm.base_rate(d, LABEL)
    b10 = mm.base_rate(d, "t10_60") if "t10_60" in d.columns else np.nan
    L.append(f"{len(d):,} liquid month-ends, {d['symbol'].nunique():,} symbols; 3x-within-24m rate {base:.2%}, "
             f"10x-within-5y rate {b10:.2%}. All features ranked within month x market INSIDE this population.\n")
    feats, R, S, Z = mm.prepare(d)
    for mth in ("kmeans", "gmm"):
        sel, tab, n_ent = mm.cluster_entries(d, feats, R, S, Z, LABEL, mth, kmax=10)
        mm.describe(L, tab, {"kmeans": "k-means archetypes", "gmm": "Gaussian-mixture archetypes"}[mth], sel, n_ent, base)
    for lab, ttl in ((LABEL, "3x within 24 months"), ("t10_60", "10x within 5 years")):
        if lab in d.columns and (d[lab] == 1).sum() >= 100:
            pats = mm.mine_patterns(d, R, lab, min_events=25)
            pats.to_csv(f"mb_seg_{name}_patterns_{lab}.csv", index=False)
            L.append(f"\n### Patterns ranked by lift — {ttl}\n")
            L.append(pats.head(25).round(3).to_markdown(index=False))
    # winners vs same-population lookalikes
    ent = mc.entries(d, LABEL)
    if ent.sum() >= 150:
        d2 = d.sort_values(["symbol", "week"]).reset_index(drop=True)
        d2["ym"] = d2["week"].dt.to_period("M")
        ent2 = mc.entries(d2, LABEL)
        pairs = mf.matched_controls(d2, d2.index[ent2])
        if len(pairs):
            R2 = mc.ranked(d2, feats); R2 = R2.loc[:, ~R2.columns.duplicated()]
            ld = mf.lookalike_diff(d2, R2, pairs)
            L.append("\n### Winners vs same-population lookalikes (paired rank differences, 90% intervals)\n")
            L.append(ld[ld["significant"]].head(30).round(3).to_markdown(index=False))


def main():
    d = mc.load()
    if "fwd_mult_60" in d.columns:
        d["t10_60"] = (d["fwd_mult_60"] >= 10).astype(float).where(d["fwd_mult_60"].notna())
    g = pd.read_csv("asymmetry_global.csv", usecols=["symbol", "sector", "industry"], low_memory=False).drop_duplicates("symbol")
    d = d.merge(g, on="symbol", how="left")
    d = add_measures(d)
    d = attach_commodity(d, commodity_tape())
    ind = d["industry"].fillna("").str.lower()
    asset = (d["sector"].isin(["Energy", "Materials", "Real Estate", "Utilities"]) | ind.str.contains(ASSET_IND, regex=True)) & ~d["bio"]
    preprofit = ((d["opm"] < 0) | (d["fcf_margin"] < 0)) & ~d["bio"] & ~asset
    mc.BLOCKS = {**mc.BLOCKS, **EXTRA_BLOCKS}
    mc.FEATS = mc.FEATS + [c for c in d.columns if c.startswith(("pp_", "as_", "cmdty_"))]
    L = ["# Multibaggers in asset-based businesses and pre-profit operators\n",
         "Same point-in-time panel as the main study, split into the populations whose value is measured "
         "differently, with population-specific measures added (runway, burn, path to profit, dilution; "
         "book growth, leverage, reinvest vs harvest, the commodity's own tape).\n"]
    population_report(L, d[asset].reset_index(drop=True), "asset", "Asset-based businesses")
    population_report(L, d[preprofit].reset_index(drop=True), "preprofit", "Pre-profit operators (non-biotech)")
    population_report(L, d[d["bio"]].reset_index(drop=True), "biotech", "Drug developers")
    open(MD, "w").write("\n".join(L))
    print(f"wrote {MD}", flush=True)


if __name__ == "__main__":
    main()
