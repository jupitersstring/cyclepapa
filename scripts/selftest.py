"""Offline self-test of the analytics path (no network).

Builds a synthetic universe with one deliberately 'inflecting-but-cheap'
industry and asserts the toolkit surfaces it. Run: python scripts/selftest.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from earnings_model import aggregate, cluster, metrics, prebreakout, valuation


def make_raw(symbol, rev, ebitda, earn, val):
    return {
        "symbol": symbol,
        "asof": "2026-05-31T00:00:00+00:00",
        "annual": {"dates": ["2022", "2023", "2024", "2025"],
                   "revenue": rev, "ebitda": ebitda, "earnings": earn, "eps": []},
        "quarterly": {"revenue": [], "earnings": [], "ebitda": []},
        "valuation": val,
        "prices": {"ret_12m": val.pop("_ret"), "ret_6m": np.nan,
                   "ret_3m": np.nan, "ret_1m": np.nan, "last_price": 100.0},
        "fetch_ok": True,
    }


def synth_universe(seed=0):
    rng = np.random.default_rng(seed)
    rows, meta = [], []

    def add(ind, bucket, pe, evebitda, ps, ret, rev, ebitda, earn, i):
        sym = f"{ind[:3].upper()}{i}.L"
        rows.append(make_raw(sym, rev, ebitda, earn, {
            "forwardPE": pe, "trailingPE": pe * 1.1, "enterpriseToEbitda": evebitda,
            "priceToSalesTrailing12Months": ps, "priceToBook": 2.0,
            "marketCap": 5e8, "_ret": ret,
        }))
        meta.append({"symbol": sym, "name": sym, "industry": ind, "size_bucket": bucket})

    for i in range(15):  # INFLECTING + CHEAP + price hasn't moved -> should win
        j = rng.normal(0, 0.4)
        add("Inflect", "Small Cap", pe=8 + j, evebitda=5 + j, ps=0.8,
            ret=-0.1 + j * 0.02,
            rev=[80, 90, 100, 118], ebitda=[-2, -5, -1, 3], earn=[-5, -8, -3, 2], i=i)
    for i in range(15):  # inflecting but EXPENSIVE and already rallied
        j = rng.normal(0, 0.4)
        add("Hot", "Mid Cap", pe=45 + j, evebitda=30 + j, ps=12,
            ret=0.9 + j * 0.05,
            rev=[80, 90, 100, 120], ebitda=[1, 2, 4, 8], earn=[1, 2, 5, 10], i=i)
    for i in range(15):  # stable, dull
        j = rng.normal(0, 0.4)
        add("Stable", "Large Cap", pe=15 + j, evebitda=11 + j, ps=2.5,
            ret=0.05 + j * 0.02,
            rev=[100, 103, 106, 109], ebitda=[20, 21, 22, 23], earn=[10, 10.5, 11, 11.5], i=i)
    for i in range(15):  # decelerating / contracting
        j = rng.normal(0, 0.4)
        add("Fade", "Micro Cap", pe=12 + j, evebitda=9 + j, ps=1.5,
            ret=-0.3 + j * 0.02,
            rev=[120, 115, 108, 100], ebitda=[15, 12, 9, 6], earn=[8, 5, 2, -1], i=i)

    flat = [metrics.compute_metrics(r) for r in rows]
    df = pd.DataFrame(flat).merge(pd.DataFrame(meta), on="symbol", how="left")
    return df


def main():
    df = synth_universe()
    assert len(df) == 60, len(df)

    # --- metric math sanity on the inflecting cohort -----------------------
    one = df[df["industry"] == "Inflect"].iloc[0]
    assert abs(one["revenue_growth"] - (118 / 100 - 1)) < 1e-9
    assert bool(one["earnings_turned_positive"]) is True
    assert bool(one["ebitda_turned_positive"]) is True
    assert bool(one["broad_inflection"]) is True
    print("[ok] metric math + inflection flags")

    # --- scoring (global / cross-sectional, the default) --------------------
    scored = valuation.add_all_scores(df)
    # sanity: industry-relative mode also runs
    _ = valuation.add_all_scores(df, group_cols=("industry",))
    for col in ("inflection_score", "valuation_richness", "price_response", "gap_score"):
        assert col in scored.columns
    med_gap = scored.groupby("industry")["gap_score"].median().sort_values(ascending=False)
    print("[ok] gap_score by industry (desc):")
    print(med_gap.to_string())
    assert med_gap.index[0] == "Inflect", f"expected Inflect on top, got {med_gap.index[0]}"

    # Inflect should read CHEAP (low richness) vs Hot (rich)
    rich = scored.groupby("industry")["valuation_richness"].median()
    assert rich["Inflect"] < rich["Hot"]
    print("[ok] Inflect cheaper than Hot; valuation_richness:", dict(rich.round(2)))

    # --- aggregation --------------------------------------------------------
    ind = aggregate.industry_table(scored)
    ind_size = aggregate.industry_size_table(scored)
    lagging = aggregate.inflecting_lagging(scored, min_n=3)
    assert lagging.iloc[0]["industry"] == "Inflect", lagging[["industry", "cell_gap"]].head()
    print(f"[ok] aggregation: industry={len(ind)} rows, industry_size={len(ind_size)} rows")
    print("[ok] inflecting_lagging top:", lagging.iloc[0]["industry"],
          "cell_gap=", round(lagging.iloc[0]["cell_gap"], 3))

    # --- valuation gap shortlist -------------------------------------------
    gap = valuation.valuation_gap_table(scored, top=10)
    assert (gap["industry"] == "Inflect").mean() >= 0.5, gap[["symbol", "industry", "gap_score"]]
    print("[ok] valuation_gap top-10 is majority 'Inflect'")

    # --- clustering ---------------------------------------------------------
    res = cluster.run_kmeans(scored, k=4)
    prof = res["profile"]
    assert res["labeled"]["cluster"].notna().sum() == 60
    print(f"[ok] clustering k={res['k']} silhouette={res['silhouette']}")
    print(prof[["cluster", "cluster_label", "n"]].to_string(index=False))

    # --- pre-breakout mechanic ---------------------------------------------
    # Inject synthetic multi-year price context per cohort: (ret_24m, trend, range_pos, vol)
    ctx = {"Inflect": (-0.05, 0.02, 0.30, 0.20),   # dormant + improving  -> top
           "Hot": (1.20, 0.60, 0.95, 0.50),         # improving but already run
           "Stable": (0.10, 0.05, 0.60, 0.25),
           "Fade": (-0.40, -0.30, 0.10, 0.30)}      # dormant + cheap but NOT improving
    pb_in = scored.copy()
    for col, i in [("ret_24m", 0), ("trend_slope", 1), ("range_position", 2), ("realized_vol", 3)]:
        pb_in[col] = pb_in["industry"].map(lambda k: ctx[k][i])
    pb = prebreakout.add_prebreakout_score(pb_in)
    assert {"prebreakout_score", "dormancy", "cheapness", "prebreakout_gated"} <= set(pb.columns)
    med_pb = pb.groupby("industry")["prebreakout_score"].median().sort_values(ascending=False)
    print("[ok] pre-breakout score by industry:", med_pb.round(3).to_dict())
    assert med_pb.index[0] == "Inflect", med_pb
    # gate: improving cohort is gated in, contracting cohort is gated out (value-trap guard)
    assert bool(pb.loc[pb["industry"] == "Inflect", "prebreakout_gated"].all())
    assert not bool(pb.loc[pb["industry"] == "Fade", "prebreakout_gated"].any())
    print("[ok] gate: Inflect (improving) IN, Fade (contracting, cheap) OUT")

    # --- quality gate (exclude non-operating securities) -------------------
    fake = scored.iloc[[0]].copy()
    fake["symbol"] = "WRNT.TEST"
    fake["name"] = "Test Holdings Warrant"   # non-operating by name
    fake["gap_score"] = 1.0                   # would top the list if not excluded
    fake["revenue_n_periods"] = 4             # rev filter alone wouldn't catch it
    scored_q = pd.concat([scored, fake], ignore_index=True)
    assert not bool(valuation.is_operating(scored_q).iloc[-1])
    assert "WRNT.TEST" not in set(valuation.valuation_gap_table(scored_q, top=5)["symbol"])
    print("[ok] quality gate excludes warrant/preferred/CEF/BDC names")

    print("\nALL SELF-TESTS PASSED")


if __name__ == "__main__":
    main()
