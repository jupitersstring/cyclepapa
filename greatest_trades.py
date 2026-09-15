"""Study the greatest trades per archetype -> the pre-rerating fingerprint.

Given the enriched event study (rerate_backtest.json: corporate-action events
with realized forward returns AND pre-event shape features), this isolates
the GREATEST trades -- the monster re-raters -- and asks what they looked
like BEFORE they moved, versus the events that fizzled. The output is a
data-driven fingerprint per archetype plus concrete, evidence-backed
proposals for improving the engine (features to add, thresholds to gate on,
weights to shift).

MONSTER = 12-month forward return >= +100% (a "great trade" doubled or more).
We also report the top-decile cut. For each observable pre-event feature we
compute P(monster | feature-bin) and the LIFT over the base monster rate,
overall and within each catalyst archetype, then assemble the dominant
conjunction and translate it into engine changes.

Features studied (all pre-event / observable): catalyst, sector, size,
drawdown_12m / drawdown_24m, range_pos, pre_12m momentum, pre_vol, basing
(consolidation vs knife), decel (is the decline decelerating), and the
post_1m confirmation drift (usable by the wait-for-confirmation rule).

Outputs: greatest_trades.json (structured) + GREATEST_TRADES.md (readable
findings + proposals).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "rerate_backtest.json"
OUT_JSON = ROOT / "greatest_trades.json"
OUT_MD = ROOT / "GREATEST_TRADES.md"

MONSTER = 1.00     # +100% / 12m = a "great trade"


def _bins(e):
    """Discrete feature bins for an event (None-safe)."""
    def b(v, cuts, labels):
        if v is None:
            return None
        for c, l in zip(cuts, labels):
            if v <= c:
                return l
        return labels[-1]
    mcap = e.get("mcap")
    return {
        "catalyst": e.get("catalyst"),
        "sector": e.get("sector"),
        "size": (None if not mcap else
                 "micro" if mcap < 3e8 else "small" if mcap < 2e9
                 else "mid" if mcap < 1e10 else "large"),
        "drawdown_12m": b(e.get("drawdown_12m"), [-0.5, -0.2], ["deep", "mod", "shallow"]),
        "drawdown_24m": b(e.get("drawdown_24m"), [-0.6, -0.3], ["deep", "mod", "shallow"]),
        "range_pos": b(e.get("range_pos"), [0.33, 0.66], ["low", "mid", "high"]),
        "pre_12m": b(e.get("pre_12m"), [-0.2, 0.2], ["down", "flat", "up"]),
        "pre_vol": b(e.get("pre_vol"), [0.08, 0.16], ["calm", "normal", "wild"]),
        "basing": ("basing" if e.get("basing") is True
                   else "not-basing" if e.get("basing") is False else None),
        "decel": ("decelerating" if (e.get("decel") or 0) > 0.05
                  else "accelerating-down" if (e.get("decel") or 0) < -0.05
                  else "steady"),
        "post_1m": b(e.get("post_1m"), [-0.05, 0.20], ["down", "flat", "up>20%"]),
    }


def _lift_table(events, is_monster, base):
    feats = {}
    for e in events:
        m = is_monster(e)
        for f, b in _bins(e).items():
            if b is None:
                continue
            d = feats.setdefault(f, {}).setdefault(b, {"n": 0, "mon": 0})
            d["n"] += 1
            d["mon"] += 1 if m else 0
    out = {}
    for f, bins in feats.items():
        out[f] = {}
        for b, v in bins.items():
            if v["n"] < 4:
                continue
            rate = v["mon"] / v["n"]
            out[f][b] = {"n": v["n"], "monster_rate": round(rate, 3),
                         "lift": round(rate / base, 2) if base > 0 else None}
    return out


def main() -> int:
    d = json.loads(SRC.read_text())
    events = [e for e in d.get("events", []) if e.get("ret_12m") is not None]
    n = len(events)
    monsters = [e for e in events if e["ret_12m"] >= MONSTER]
    base = len(monsters) / n if n else 0
    is_mon = lambda e: e["ret_12m"] >= MONSTER

    overall = _lift_table(events, is_mon, base)

    # per-archetype fingerprint
    per_arch = {}
    for cat in sorted({e["catalyst"] for e in events}):
        sub = [e for e in events if e["catalyst"] == cat]
        sub_mon = [e for e in sub if is_mon(e)]
        per_arch[cat] = {
            "n": len(sub), "n_monster": len(sub_mon),
            "monster_rate": round(len(sub_mon) / len(sub), 3) if sub else 0,
            "median_12m": round(statistics.median([e["ret_12m"] for e in sub]), 3) if sub else None,
            "top_trades": sorted(
                [{"ticker": e["ticker"], "date": e["date"],
                  "ret_12m": round(e["ret_12m"], 2),
                  "drawdown_12m": e.get("drawdown_12m"),
                  "basing": e.get("basing"), "post_1m": e.get("post_1m"),
                  "sector": e.get("sector")}
                 for e in sub], key=lambda r: -r["ret_12m"])[:5],
        }

    # median pre-event feature values: monster vs the rest
    def med(items, key):
        v = [i[key] for i in items if i.get(key) is not None]
        return round(statistics.median(v), 3) if v else None
    rest = [e for e in events if not is_mon(e)]
    compare = {}
    for key in ("drawdown_12m", "drawdown_24m", "range_pos", "pre_12m",
                "pre_vol", "post_1m", "decel"):
        compare[key] = {"monster": med(monsters, key), "rest": med(rest, key)}
    for key in ("basing",):
        compare[key] = {
            "monster_rate": round(sum(1 for e in monsters if e.get(key)) / len(monsters), 3) if monsters else None,
            "rest_rate": round(sum(1 for e in rest if e.get(key)) / len(rest), 3) if rest else None}

    result = {
        "monster_threshold": MONSTER, "n_events": n, "n_monsters": len(monsters),
        "base_monster_rate": round(base, 3),
        "overall_lifts": overall,
        "monster_vs_rest": compare,
        "by_archetype": per_arch,
    }
    io_util.write_json(OUT_JSON, result)
    _write_md(result)
    print(f"{len(monsters)}/{n} monsters (>= +{MONSTER*100:.0f}% / 12m), "
          f"base {base*100:.0f}%")
    print("\nTop overall pre-rerating lifts:")
    flat = [(f, b, v["lift"], v["n"]) for f, bins in overall.items()
            for b, v in bins.items() if v["lift"]]
    for f, b, lift, nn in sorted(flat, key=lambda x: -x[2])[:14]:
        print(f"  {f:<14}{b:<14} lift {lift:>4}  (n={nn})")
    print(f"\nwrote {OUT_JSON.name} + {OUT_MD.name}")
    return 0


def _write_md(r):
    L = []
    L.append("# Greatest Trades — pre-rerating fingerprint & engine proposals\n")
    L.append(f"Event study of {r['n_events']} corporate-action events. "
             f"A **monster** trade = +{int(r['monster_threshold']*100)}% or more "
             f"over 12 months; {r['n_monsters']} qualified "
             f"({r['base_monster_rate']*100:.0f}% base rate).\n")

    L.append("## What the monsters looked like BEFORE they moved\n")
    c = r["monster_vs_rest"]
    def row(k, label, pct=True):
        m, rst = c[k].get("monster"), c[k].get("rest")
        if m is None:
            m, rst = c[k].get("monster_rate"), c[k].get("rest_rate")
        f = (lambda x: f"{x*100:+.0f}%" if x is not None else "—") if pct else (lambda x: f"{x}" if x is not None else "—")
        return f"| {label} | {f(m)} | {f(rst)} |"
    L.append("| pre-event feature | monster | the rest |")
    L.append("|---|---|---|")
    L.append(row("drawdown_12m", "drawdown from 12m high"))
    L.append(row("drawdown_24m", "drawdown from 24m high"))
    L.append(row("range_pos", "position in 12m range", pct=False))
    L.append(row("pre_12m", "prior-12m return"))
    L.append(row("pre_vol", "pre-event monthly vol", pct=False))
    L.append(row("basing", "basing / consolidating"))
    L.append(row("decel", "decline decelerating (decel)", pct=False))
    L.append(row("post_1m", "+1m confirmation drift"))
    L.append("")

    L.append("## Strongest pre-rerating lifts (P(monster | feature) / base)\n")
    flat = [(f, b, v["lift"], v["n"]) for f, bins in r["overall_lifts"].items()
            for b, v in bins.items() if v["lift"]]
    L.append("| feature = bin | lift | n |")
    L.append("|---|---|---|")
    for f, b, lift, nn in sorted(flat, key=lambda x: -x[2])[:16]:
        L.append(f"| {f} = {b} | {lift}× | {nn} |")
    L.append("")

    L.append("## Greatest trades by archetype\n")
    for cat, a in sorted(r["by_archetype"].items(),
                         key=lambda kv: -(kv[1]["monster_rate"])):
        tops = ", ".join(f"{t['ticker']} +{int(t['ret_12m']*100)}%" for t in a["top_trades"][:4])
        L.append(f"- **{cat}** — {a['n_monster']}/{a['n']} monsters "
                 f"({a['monster_rate']*100:.0f}%), median {a['median_12m']*100:+.0f}%. "
                 f"Top: {tops}")
    L.append("")

    L.append("## Proposed engine improvements (data-driven)\n")
    L.append(_proposals(r))
    OUT_MD.write_text("\n".join(L) + "\n")


def _proposals(r):
    """Turn the measured separations into concrete engine changes."""
    c = r["monster_vs_rest"]
    P = []
    # basing
    b = c.get("basing", {})
    if b.get("monster_rate") is not None and b.get("rest_rate") is not None \
            and b["monster_rate"] > b["rest_rate"] * 1.2:
        P.append(f"1. **Add a BASING feature to tail_odds & a mechanism gate.** "
                 f"Monsters were consolidating pre-event {b['monster_rate']*100:.0f}% "
                 f"of the time vs {b['rest_rate']*100:.0f}% for the rest — buying a "
                 f"tight base beats catching a falling knife. Add `basing` as a "
                 f"tail-odds feature and require it (or 'not still making new lows') "
                 f"in the latent archetypes.")
    # drawdown
    dd = c.get("drawdown_24m", {})
    if dd.get("monster") is not None and dd.get("rest") is not None \
            and dd["monster"] < dd["rest"] - 0.05:
        P.append(f"2. **Deepen the drawdown gate on a 24-month lookback.** Monsters "
                 f"sat {dd['monster']*100:.0f}% below their 24m high vs "
                 f"{dd['rest']*100:.0f}% for the rest; the 24m drawdown separates "
                 f"better than the 12m. Add drawdown_24m to the geometry/tail "
                 f"feature set and weight the deep bucket.")
    # decel
    de = c.get("decel", {})
    if de.get("monster") is not None and de.get("rest") is not None \
            and de["monster"] > de["rest"]:
        P.append(f"3. **Add a DECELERATION filter.** Monsters' decline was "
                 f"decelerating pre-event (decel {de['monster']:+.2f} vs "
                 f"{de['rest']:+.2f}) — the fall was stopping, not accelerating. "
                 f"Gate latent archetypes on decel >= 0 to avoid knives.")
    # post_1m
    pm = c.get("post_1m", {})
    if pm.get("monster") is not None and pm.get("rest") is not None \
            and pm["monster"] > pm["rest"]:
        P.append(f"4. **Keep/strengthen the confirmation rule.** Monsters drifted "
                 f"{pm['monster']*100:+.0f}% in the first month vs "
                 f"{pm['rest']*100:+.0f}% — early confirmation remains the single "
                 f"cleanest separator; consider a lower confirmation threshold for "
                 f"the archetypes whose monsters confirmed most.")
    # per-archetype weighting
    best = sorted(r["by_archetype"].items(), key=lambda kv: -kv[1]["monster_rate"])[:3]
    worst = sorted(r["by_archetype"].items(), key=lambda kv: kv[1]["monster_rate"])[:3]
    P.append(f"5. **Re-weight archetypes by monster rate.** Highest: "
             + ", ".join(f"{k} ({v['monster_rate']*100:.0f}%)" for k, v in best)
             + "; lowest: "
             + ", ".join(f"{k} ({v['monster_rate']*100:.0f}%)" for k, v in worst)
             + " — tilt catalyst weights toward the monster-rich types.")
    P.append("6. **Pre-vol / size:** see the lift table above; add the "
             "highest-lift bins as explicit tail-odds features where not already "
             "present.")
    return "\n".join(P)


if __name__ == "__main__":
    raise SystemExit(main())
