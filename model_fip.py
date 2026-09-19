"""Model FIP — "Frog in the Pan" / stored-energy score.

Da, Gurun & Warachka (2014) show that information delivered CONTINUOUSLY (in
small, steady increments) is underreacted to far more than the same information
delivered in a discrete jump — attention fails on gradual change, like a frog in
slowly heating water. Adapted here to fundamentals: we want stocks where the
business has quietly STEPPED UP — steady, consistent earnings/revenue growth
AND repeated beats vs expectations — yet PRICE has NOT responded proportionately.
That gap is stored energy: performance biding before a breakout (the £9.90
sitting under a £10 lid while fair value has moved to £13).

    FIP = fundamental_energy x growth_stability x beats   (the heat, from FMP)
          x (1 - price_response)                          (price hasn't moved, from master RS)
          x valuation_lag                                 (multiple compressed vs growth)
          x biding_bonus                                  (coiling just under a pivot)

High FIP is the complement of an already-extended winner: the fundamentals are
in place and steady, the market hasn't noticed yet. Pair with Model B (ignition)
to catch the moment the lid finally breaks.

Usage: python model_fip.py [--top 30]
"""

import sys
import json
import numpy as np
import pandas as pd

MASTER = "/tmp/master_full_universe.csv"
PANEL = "/tmp/fmp_panel.csv"
INFO = "/home/user/cyclepapa/data/ticker_info_cache.json"
OUT = "/tmp/fip_rank.csv"
DELIVER = "/home/user/cyclepapa/data/monster/frog_in_pan.csv"


def pctl(s):
    return s.rank(pct=True)


def build():
    m = pd.read_csv(MASTER, low_memory=False)
    p = pd.read_csv(PANEL, low_memory=False)
    mcols = ["ticker", "adv_usd", "rel_score", "rel_score_adj", "w_close",
             "vcp_pivot_distance_pct", "E_new_high", "v_bucket", "master", "E"]
    df = p.merge(m[[c for c in mcols if c in m.columns]], on="ticker", how="left")

    # ── the heat: steady fundamental step-up + beats ──
    F = df["F"].clip(0, 1)
    I = df["I"].clip(0, 1)
    stab = pctl(df["growth_stability"])
    streak = pctl(df["i_pos_streak"])
    margin = pctl(df["f_margin_delta"])
    fundamental_energy = (0.30 * F + 0.25 * I + 0.25 * stab + 0.10 * streak + 0.10 * margin)

    # ── low price response: RS lagging + not extended ──
    rs = pctl(df["rel_score"].fillna(df["rel_score"].median()))
    near_high = df["E_new_high"].fillna(0).clip(0, 1)
    price_response = (0.75 * rs + 0.25 * near_high).clip(0, 1)
    low_response = 1 - price_response

    # ── valuation lag: earnings up but multiple compressed (PEG-like) ──
    # trailing P/E from local price / ttm EPS; cheap vs growth => price lagged.
    pe = df["w_close"] / df["eps_ttm"].where(df["eps_ttm"] > 0)
    growth = df["rev_ttm_ttm_g"].clip(lower=0.01)
    peg = pe / (growth * 100)                          # PE per point of % growth
    val_lag = 1 - pctl(peg)                            # low PEG -> high lag
    val_lag = val_lag.fillna(0.5)

    # ── biding bonus: coiling just under a pivot / resistance ──
    dist = df["vcp_pivot_distance_pct"]
    biding = ((dist.between(-8, 0)).astype(float)      # just below pivot
              + (df["v_bucket"] == "Coiled").astype(float)) .clip(0, 1)

    stored = fundamental_energy * low_response
    raw = stored * (0.7 + 0.6 * val_lag) * (1 + 0.3 * biding)
    df["fip"] = (100 * pctl(raw)).round(1)
    df["fund_energy"] = fundamental_energy.round(3)
    df["low_price_resp"] = low_response.round(3)
    df["val_lag"] = val_lag.round(3)
    df["biding"] = biding.round(2)
    df["pe_ttm"] = pe.round(1)

    # require real fundamentals + a genuine step-up (don't flag falling names)
    ok = df["growth_stability"].notna() & (df["F"] >= 0.4) & (df["I"] >= 0.4)
    df.loc[~ok, "fip"] = np.nan

    keep = ["ticker", "fip", "fund_energy", "low_price_resp", "val_lag", "biding",
            "F", "I", "growth_stability", "i_pos_streak", "f_rev_g", "f_eps_g",
            "i_eps_surprise", "rel_score", "pe_ttm", "vcp_pivot_distance_pct",
            "v_bucket", "master", "adv_usd"]
    keep = [c for c in keep if c in df.columns]
    out = df[keep].copy()
    out["adv_usd_M"] = (out["adv_usd"] / 1e6).round(2)
    out.drop(columns=["adv_usd"], inplace=True)
    try:
        info = json.load(open(INFO))
        out["name"] = out.ticker.map(lambda t: info.get(t, {}).get("name", ""))
    except Exception:
        pass
    return out.sort_values("fip", ascending=False)


def main():
    top = 30
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    out = build()
    out.to_csv(OUT, index=False)
    import os
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    out.round(4).to_csv(DELIVER, index=False)
    live = out[out.fip.notna()]
    print(f"Frog-in-the-Pan candidates: {len(live)} (strong+steady fundamentals, lagging price)")
    cols = ["ticker", "name", "fip", "fund_energy", "low_price_resp", "val_lag", "biding",
            "growth_stability", "i_pos_streak", "i_eps_surprise", "f_rev_g", "rel_score",
            "pe_ttm", "master", "adv_usd_M"]
    cols = [c for c in cols if c in out.columns]
    with pd.option_context("display.width", 260, "display.max_columns", 30):
        print(f"\n=== TOP {top} FROG-IN-THE-PAN (steady fundamental step-up, price biding) ===")
        print(live[cols].head(top).to_string(index=False))


if __name__ == "__main__":
    main()
