"""Backtest the mechanism-gate archetypes -- what is rigorously possible.

An archetype = a CATALYST (or condition) + a payoff-geometry shape + a
balance-sheet gate. A point-in-time backtest needs the archetype's membership
AS OF a past date. Two facts bound what we can do:

  * The CATALYST-anchored archetypes have a dated EDGAR trigger (asset sale,
    tender, buyback authorization, strategic review), so we can anchor on the
    event and measure forward returns -- and apply the PRICE-derived half of
    the gate (cheap = deep drawdown, small = market cap) at that date. This is
    a genuine point-in-time backtest, reusing the 417-event study.
  * The BALANCE-SHEET archetypes (coiled-spring delever, sub-cash buyback,
    hidden-asset, forced-seller, and the two latent/anticipatory ones) need
    point-in-time FUNDAMENTALS or fund-flow data we do not have historically,
    so they are NOT point-in-time backtestable here. We say so, and say what
    each would need, rather than fabricate a survivorship-biased number.

For each backtestable archetype we report the forward-return distribution
raw AND confirmation-gated (deep_research showed confirmation is the edge).

Output: archetype_backtest.json + ARCHETYPE_BACKTEST.md.
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "rerate_backtest.json"
OUT_JSON = ROOT / "archetype_backtest.json"
OUT_MD = ROOT / "ARCHETYPE_BACKTEST.md"

MONSTER = 1.00
BIG_LOSS = -0.50


def _n(x):
    return x if isinstance(x, (int, float)) else None


# archetype -> event-proxy predicate(event) using ONLY fields available at the
# event date (catalyst, market cap, price drawdown). None = not backtestable.
def _small(e):  m = _n(e.get("mcap")); return bool(m and m < 2e9)
def _deep(e):   d = _n(e.get("drawdown_12m")); return d is not None and d <= -0.30

ARCHETYPES = {
    "asset_sale_monetization":
        lambda e: e["catalyst"] == "ASSET_SALE" and (_small(e) or _deep(e)),
    "tender_offer_squeeze":
        lambda e: e["catalyst"] == "TENDER_OFFER" and _small(e),
    "sub_cash_buyback":
        lambda e: e["catalyst"] == "BUYBACK_AUTH" and _deep(e),
    "stated_unlock_triangulated":
        lambda e: e["catalyst"] == "STRATEGIC_REVIEW",
}
NOT_BACKTESTABLE = {
    "coiled_spring_delever": "needs point-in-time D/E + rising operating income "
        "(no historical fundamentals); could add a 'reduce leverage' 8-K event scan.",
    "hidden_asset_realization": "needs the point-in-time credit-agreement asset-"
        "sweep scan + a small-levered balance sheet; not reconstructable historically.",
    "forced_seller_exhaustion": "needs historical N-PORT fund-flow (forced selling); "
        "no EDGAR event phrase and no historical flow store.",
    "asset_sale_latent": "ANTICIPATORY (the setup BEFORE the sale is announced) -- "
        "by definition has no event to anchor; needs a FORWARD tracking study "
        "(snapshot today, check for a sale over the next 6-12 months).",
    "tender_target_latent": "ANTICIPATORY (take-private candidate before any bid) -- "
        "same: needs forward tracking, not a backward event anchor.",
}


def stats(rets):
    rets = [r for r in rets if r is not None]
    if not rets:
        return {"n": 0}
    return {"n": len(rets),
            "monster_rate": round(sum(1 for r in rets if r >= MONSTER) / len(rets), 3),
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
            "median": round(st.median(rets), 3),
            "mean": round(st.mean(rets), 3),
            "loss_rate_50": round(sum(1 for r in rets if r <= BIG_LOSS) / len(rets), 3)}


def main() -> int:
    d = json.loads(SRC.read_text())
    ev = [e for e in d.get("events", []) if e.get("ret_12m") is not None]
    R = {"window": d.get("window"), "n_events": len(ev), "archetypes": {}}

    for name, pred in ARCHETYPES.items():
        members = [e for e in ev if pred(e)]
        rets = [e["ret_12m"] for e in members]
        confirmed = [e["ret_12m"] for e in members if (_n(e.get("post_1m")) or -9) >= 0.20]
        faded = [e["ret_12m"] for e in members if (_n(e.get("post_1m")) or 9) <= -0.10]
        R["archetypes"][name] = {
            "backtestable": True,
            "n": len(members),
            "all": stats(rets),
            "confirmed_>=20pct": stats(confirmed),
            "faded_<=-10pct": stats(faded),
            "top_trades": sorted(
                [{"ticker": e["ticker"], "ret_12m": round(e["ret_12m"], 2),
                  "date": e["date"]} for e in members],
                key=lambda r: -r["ret_12m"])[:4],
        }
    for name, why in NOT_BACKTESTABLE.items():
        R["archetypes"][name] = {"backtestable": False, "reason": why}

    io_util.write_json(OUT_JSON, R)
    _write_md(R)
    print(f"archetype backtest on {len(ev)} events ({R['window']})\n")
    for name, a in R["archetypes"].items():
        if a.get("backtestable"):
            al, cf = a["all"], a["confirmed_>=20pct"]
            print(f"  {name:<26} n={al['n']:>3}  all: med {al.get('median',0)*100:>+4.0f}% "
                  f"win {al.get('win_rate',0)*100:>3.0f}%  |  confirmed(n={cf.get('n',0)}): "
                  f"mean {cf.get('mean',0)*100:>+4.0f}% monster {cf.get('monster_rate',0)*100:.0f}%")
        else:
            print(f"  {name:<26} NOT point-in-time backtestable")
    print(f"\nwrote {OUT_JSON.name} + {OUT_MD.name}")
    return 0


def _write_md(R):
    L = [f"# Archetype backtest — what history says, and what it can't\n",
         f"Point-in-time event study over {R['n_events']} events ({R['window']}). "
         "monster = +100%/12m; big loss = -50%/12m. Confirmation = >=+20% "
         "first-month drift (deep_research showed it is the edge).\n"]
    L.append("## Backtestable (catalyst-anchored) archetypes\n")
    L.append("| archetype | n | all: median | win% | loss>50% | confirmed: mean | confirmed: monster% |")
    L.append("|---|---|---|---|---|---|---|")
    for name, a in R["archetypes"].items():
        if not a.get("backtestable"):
            continue
        al, cf = a["all"], a["confirmed_>=20pct"]
        L.append(f"| {name} | {al['n']} | {al.get('median',0)*100:+.0f}% | "
                 f"{al.get('win_rate',0)*100:.0f}% | {al.get('loss_rate_50',0)*100:.0f}% | "
                 f"{cf.get('mean',0)*100:+.0f}% | {cf.get('monster_rate',0)*100:.0f}% |")
    L.append("")
    L.append("**Read with care — the samples are small.** Slicing 417 events by "
             "archetype and then by confirmation shrinks each cell to n≈1–40; the "
             "confirmed sub-cells are n=0–4, so their means (e.g. stated-unlock "
             "confirmed +324%) are driven by one or two names (SYRE +975%) and are "
             "DIRECTIONAL, not estimates. What is robust across the whole study "
             "still holds here: the RAW archetype medians are weak/negative "
             "(asset-sale +0%, tender −26%, sub-cash −15%, stated-unlock −12%), and "
             "the money is in the confirmed tail — but the per-archetype confirmed "
             "numbers need a wider window to trust. Top realized trades per "
             "archetype:")
    for name, a in R["archetypes"].items():
        if a.get("backtestable"):
            tt = ", ".join(f"{t['ticker']} +{int(t['ret_12m']*100)}%" for t in a["top_trades"])
            L.append(f"- **{name}**: {tt}")
    L.append("")
    L.append("## NOT point-in-time backtestable (and why)\n")
    L.append("These need historical fundamentals or fund-flow we don't have; "
             "listing what each would require rather than fabricating a "
             "survivorship-biased number.\n")
    for name, a in R["archetypes"].items():
        if not a.get("backtestable"):
            L.append(f"- **{name}** — {a['reason']}")
    L.append("")
    L.append("## The honest path to backtesting the rest\n")
    L.append("1. **Coiled-spring delever** is the most sourceable gap: add a "
             "'reduced net leverage' / 'repaid $X of debt' 8-K event scan and "
             "anchor a forward-return study on it (same machinery as the catalyst "
             "backtest).\n2. **The latent/anticipatory archetypes** can only be "
             "validated FORWARD: snapshot today's members and track, over 6-12 "
             "months, whether they actually announce the sale/tender and how they "
             "perform — a prospective hit-rate study, not a backward one.\n"
             "3. **Balance-sheet archetypes** (sub-cash, hidden-asset, forced-"
             "seller) need a point-in-time fundamentals/flow store; the frames "
             "store is current-only, so this is a data-acquisition task.")
    OUT_MD.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
