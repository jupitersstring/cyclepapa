"""Model B — Ignition score: "is today the ignition/breakout day?"

This is the fast clock of the two-model monster-breakout system. It does NOT
try to predict whether a stock becomes a +50/100/200% winner over 3-12 months
(that is Model A, which needs a fundamentals panel we don't yet have). It only
scores, from data available today, whether *right now* looks like the ignition
bar of a violent move — the moment demand shows up against limited supply near
highs.

Grounded in the extreme-winner literature (Reinganum; Doyle-Lundholm-Soliman;
Dyl-Yuksel-Zaynutdinova; George-Hwang-Li; Foerster):

  core (both REQUIRED, multiplicative — demand must actually show up on a real
        breakout, per Dyl et al. "move + information -> continuation"):
     breakout_acceptance : E leg — pivot break / new high / close strength /
                           bb break / coil break (clears a level, closes strong)
     participation       : sudden volume — weekly RVOL spike on an up week,
                           ADV slope/accel, v_bucket 'Triggered'

  amplifiers (modulate 0.7..1.3):
     strength_proximity  : RS (rel_score/weekly_rank) + near-high + MA-aligned
                           (monsters ignite near highs, not at 52w lows)
     supply_tightness    : scarcity amplifies the move (lower $ADV within a
                           tradeable floor scores higher)
     catalyst_proxy      : *unverified* surrogate for CatalystVerified — a big,
                           high-volume, strong-close, accelerating bar is more
                           likely information-driven than a drift. NOT a real
                           catalyst check (needs an earnings/news feed).

  gates / penalties:
     regime_gate         : must be in/near an uptrend (MA-aligned or positive
                           RS) — avoids the "spike into a falling bear stack =
                           distribution" reversal trap
     liquidity_gate      : exclude untradeable names ($ADV < FLOOR)
     extension_penalty   : Foerster "double then nothing" — fade names that
                           have already run (v_bucket Confirmed/Holding)

Output columns are transparent so each score can be audited.

Usage: python model_ignition.py [--floor 1e6] [--top 30]
"""

import sys
import json
import numpy as np
import pandas as pd

MASTER = "/tmp/master_full_universe.csv"
INFO = "/home/user/cyclepapa/data/ticker_info_cache.json"
OUT = "/tmp/ignition_rank.csv"
DELIVER = "/home/user/cyclepapa/data/ignition/ignition_candidates.csv"

FLOOR = 1e6   # $ ADV tradeability floor


def pctl(s: pd.Series) -> pd.Series:
    """Robust 0-1 percentile rank (NaN-safe)."""
    return s.rank(pct=True)


def clip01(s):
    return np.clip(s, 0.0, 1.0)


def build(floor=FLOOR):
    m = pd.read_csv(MASTER, low_memory=False)
    b = lambda col: m[col].fillna(0).astype(float).clip(0, 1) if col in m else pd.Series(0.0, index=m.index)
    f = lambda col: m[col].fillna(0).astype(float) if col in m else pd.Series(0.0, index=m.index)

    # ── breakout acceptance (daily E leg) ──
    E = f("E") / 100.0
    flags = pd.concat([b("E_pivot_break"), b("E_new_high"), b("E_close_strength"),
                       b("E_bb_break"), b("E_coil_break")], axis=1).mean(axis=1)
    breakout = clip01(0.5 * E + 0.5 * flags)

    # ── participation (sudden volume) ──
    wtier = (f("vspike_w_tier") / 5.0).clip(0, 1)
    wup = b("vspike_w_up")
    wspike = wtier * np.where(wup > 0, 1.0, 0.3)          # spike counts most on up weeks
    mtier = (f("vspike_m_tier") / 5.0).clip(0, 1)
    adv_acc = b("adv_accel_score")
    adv_slp = b("adv_slope_score")
    evol = b("E_vol_spike")
    triggered = (m.get("v_bucket") == "Triggered").astype(float) if "v_bucket" in m else 0.0
    participation = clip01(0.40 * wspike + 0.15 * mtier + 0.20 * adv_acc
                           + 0.10 * adv_slp + 0.10 * evol + 0.05 * triggered)
    # If volume leg wasn't scanned (vspike NaN), fall back to E_vol_spike/adv so
    # unscanned names aren't unfairly zeroed on participation.
    novol = m["vspike_w_tier"].isna() if "vspike_w_tier" in m else pd.Series(True, index=m.index)
    fallback_part = clip01(0.5 * evol + 0.3 * adv_acc + 0.2 * adv_slp)
    participation = participation.where(~novol, fallback_part)

    # ── amplifiers ──
    rs = 0.5 * pctl(f("rel_score")) + 0.5 * pctl(f("weekly_rank"))
    near_high = b("E_new_high")
    aligned = b("E_ma_aligned")
    strength_prox = clip01(0.5 * rs + 0.25 * near_high + 0.25 * aligned)

    adv = f("adv_usd")
    # scarcity amplifier: tradeable but tight scores highest; huge caps lowest
    supply_tight = pd.Series(0.5, index=m.index)
    supply_tight = supply_tight.mask(adv.between(floor, 5e6), 1.0)
    supply_tight = supply_tight.mask(adv.between(5e6, 5e7), 0.8)
    supply_tight = supply_tight.mask(adv.between(5e7, 5e8), 0.55)
    supply_tight = supply_tight.mask(adv >= 5e8, 0.4)

    # catalyst proxy (UNVERIFIED): big, strong-close, accelerating, high-vol bar
    catalyst_proxy = clip01(pd.concat([
        b("E_vol_spike"), b("E_ret_acceleration"), b("E_close_strength"),
        (f("E_vol_ratio") / 3.0).clip(0, 1), b("E_behavior_shift")], axis=1).mean(axis=1))

    # ── gates & penalties ──
    regime_gate = ((aligned > 0) | (rs >= 0.5) | (near_high > 0)).astype(float)
    liquidity_gate = (adv >= floor).astype(float)
    bucket = m.get("v_bucket", pd.Series(index=m.index, dtype=object))
    extension_penalty = np.where(bucket.isin(["Confirmed", "Holding"]), 0.6,
                         np.where(bucket == "Failed", 0.3, 1.0))

    # ── compose ──
    core = breakout * participation                        # both essential
    amp = (0.7 + 0.6 * strength_prox) * (0.7 + 0.6 * supply_tight) * (0.7 + 0.6 * catalyst_proxy)
    ign = 100.0 * core * amp * regime_gate * liquidity_gate * extension_penalty

    out = pd.DataFrame({
        "ticker": m["ticker"],
        "region": m.get("region", ""),
        "ignition": ign.round(2),
        "breakout_accept": breakout.round(3),
        "participation": participation.round(3),
        "strength_prox": strength_prox.round(3),
        "supply_tight": supply_tight.round(2),
        "catalyst_proxy": catalyst_proxy.round(3),
        "ext_pen": extension_penalty,
        "v_bucket": bucket,
        "E": f("E").round(0),
        "vspike_w_tier": f("vspike_w_tier"),
        "master": f("master").round(1),
        "adv_usd_M": (adv / 1e6).round(2),
        "vol_scanned": (~novol).astype(int),
    })
    # attach names/sector
    try:
        info = json.load(open(INFO))
        out["name"] = out.ticker.map(lambda t: info.get(t, {}).get("name", ""))
        out["sector"] = out.ticker.map(lambda t: info.get(t, {}).get("sector", ""))
    except Exception:
        pass
    return out.sort_values("ignition", ascending=False)


def main():
    floor = FLOOR
    top = 30
    if "--floor" in sys.argv:
        floor = float(sys.argv[sys.argv.index("--floor") + 1])
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    out = build(floor)
    out.to_csv(OUT, index=False)
    import os
    os.makedirs(os.path.dirname(DELIVER), exist_ok=True)
    out.to_csv(DELIVER, index=False)

    live = out[out.ignition > 0]
    print(f"Ignition candidates (>0): {len(live)} of {len(out)} (floor ${floor:,.0f} ADV)")
    print(f"  ...of which volume-scanned: {int(live.vol_scanned.sum())} "
          f"(the rest use the E/ADV participation fallback until the vspike scan finishes)")
    cols = ["ticker", "name", "region", "ignition", "breakout_accept", "participation",
            "strength_prox", "supply_tight", "catalyst_proxy", "v_bucket", "E", "master", "adv_usd_M"]
    cols = [c for c in cols if c in out.columns]
    with pd.option_context("display.width", 240, "display.max_columns", 30):
        print(f"\n=== TOP {top} IGNITION (catalyst_proxy is UNVERIFIED — no events feed yet) ===")
        print(live[cols].head(top).to_string(index=False))


if __name__ == "__main__":
    main()
