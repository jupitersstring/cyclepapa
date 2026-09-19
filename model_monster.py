"""Model A — Monster-candidate score: P(+50/100/200% over ~3-12 months).

The slow clock of the two-model system. Where Model B (ignition) asks "is today
the breakout bar?", Model A asks "does this look like a stock BEFORE/EARLY in a
monster move?" — the expectations-gap setup the extreme-winner literature points
to, which needs fundamentals (F/I/R) that yfinance couldn't give but FMP can.

Composite, following the revised Monster-Breakout structure
    MB ~= F^1.5 * I * T * R_gap / S
combined multiplicatively so a huge score needs a big change in perceived
business value (F,I) that the market hasn't recognised (R_gap) against limited
supply (S), with price already confirming (T) — not any single leg alone.

  F        fundamental acceleration      (FMP: rev/EPS growth 2nd derivative, margin inflection)
  I        information surprise          (FMP: latest EPS/rev surprise + streak)
  T        already-strong price near high(master: RS via rel_score/weekly_rank + near-high)  -- Reinganum
  R_gap    recognition gap / neglect     (FMP: low coverage + dispersion)                     -- Doyle-Lundholm-Soliman
  S        supply                        (FMP float; master $ADV) -- scarcity amplifies

Bessembinder caveat: static attributes barely predict (R^2~0.008), so this is a
RANKING of setup quality, not a probability — the dynamic F/I legs are what earn
it. Only names with FMP fundamentals get a score.

Usage: python model_monster.py [--top 30]
"""

import sys
import json
import numpy as np
import pandas as pd

MASTER = "/tmp/master_full_universe.csv"
PANEL = "/tmp/fmp_panel.csv"
INFO = "/home/user/cyclepapa/data/ticker_info_cache.json"
OUT = "/tmp/monster_rank.csv"
DELIVER = "/home/user/cyclepapa/data/monster/monster_candidates.csv"


def pctl(s):
    return s.rank(pct=True)


def build():
    m = pd.read_csv(MASTER, low_memory=False)
    p = pd.read_csv(PANEL, low_memory=False)
    df = p.merge(m[["ticker", "adv_usd", "rel_score", "weekly_rank", "E",
                    "E_new_high", "E_ma_aligned", "master", "V", "vspike_w_tier",
                    "v_bucket"]], on="ticker", how="left")

    # T — already-strong price near a long-term high (Reinganum), from master legs
    T = (0.45 * pctl(df["rel_score"]) + 0.35 * pctl(df["weekly_rank"])
         + 0.20 * df["E_new_high"].fillna(0).clip(0, 1))
    F = df["F"].clip(0, 1).fillna(df["F"].median())
    I = df["I"].clip(0, 1).fillna(0.5)
    Rg = df["R_gap"].clip(0, 1).fillna(0.5)
    S = df["S_supply"].clip(0, 1).fillna(df["S_supply"].median())

    # buyback (supply reduction) + insider open-market buying (internal
    # accumulation / conviction) — both from FMP; modest conviction multiplier.
    BB = df["BB"].clip(0, 1).fillna(0) if "BB" in df else pd.Series(0.0, index=df.index)
    INS = df["INS"].clip(0, 1).fillna(0) if "INS" in df else pd.Series(0.0, index=df.index)
    conviction = 1 + 0.30 * BB + 0.30 * INS

    # multiplicative MB core (F emphasised ^1.5); +0.5 offsets keep any single
    # modest leg from zeroing the product, while zeros still hurt. Buybacks also
    # tighten effective supply (divide S).
    raw = (F ** 1.5) * (0.5 + I) * (0.5 + T) * (0.5 + Rg) / (0.5 + S * (1 - 0.4 * BB)) * conviction
    df["monster"] = (100 * pctl(raw)).round(1)     # rank -> 0-100 (setup quality, not probability)
    df["T"] = T.round(3)
    df["BB"] = BB.round(3)
    df["INS"] = INS.round(3)

    # require real fundamentals (F from income acceleration) to score
    df.loc[df["f_rev_accel"].isna() & df["f_eps_accel"].isna(), "monster"] = np.nan

    keep = ["ticker", "monster", "F", "I", "T", "R_gap", "S_supply", "BB", "INS",
            "f_rev_g", "f_rev_accel", "f_eps_accel", "f_margin_delta",
            "i_eps_surprise", "i_pos_streak", "r_n_analysts", "r_dispersion",
            "s_free_float_pct", "buyback_yoy_dil", "ins_n_buyers", "ins_senior_buy",
            "ins_offmkt_buys", "last_surprise_pos", "days_since_last", "days_to_next",
            "adv_usd", "master", "V", "v_bucket"]
    keep = [c for c in keep if c in df.columns]
    out = df[keep].copy()
    out["adv_usd_M"] = (out["adv_usd"] / 1e6).round(2)
    out.drop(columns=["adv_usd"], inplace=True)
    try:
        info = json.load(open(INFO))
        out["name"] = out.ticker.map(lambda t: info.get(t, {}).get("name", ""))
        out["sector"] = out.ticker.map(lambda t: info.get(t, {}).get("sector", ""))
    except Exception:
        pass
    return out.sort_values("monster", ascending=False)


def main():
    top = 30
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    out = build()
    out.to_csv(OUT, index=False)
    import os
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    out.round(4).to_csv(DELIVER, index=False)
    live = out[out.monster.notna()]
    print(f"Monster candidates scored: {len(live)} (of {len(out)} in panel)")
    cols = ["ticker", "name", "monster", "F", "I", "T", "R_gap", "S_supply",
            "f_rev_g", "i_eps_surprise", "i_pos_streak", "r_n_analysts",
            "last_surprise_pos", "master", "adv_usd_M"]
    cols = [c for c in cols if c in out.columns]
    with pd.option_context("display.width", 260, "display.max_columns", 30):
        print(f"\n=== TOP {top} MONSTER CANDIDATES (F^1.5 * I * T * R_gap / S) ===")
        print(live[cols].head(top).to_string(index=False))


if __name__ == "__main__":
    main()
