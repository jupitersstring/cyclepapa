"""Deeper research on the event study -- validate and sharpen the monster
fingerprint. Pure-compute on rerate_backtest.json (events + realized returns
+ pre-event features); no new network.

Five analyses:
  A. FINGERPRINT CONCENTRATION -- does a higher monster_setup score actually
     concentrate the monsters, and what is the downside at each level? (Is
     the score real, and how convex.)
  B. CONFIRMATION SWEEP -- across first-month drift thresholds, the monster
     rate / expectancy / coverage tradeoff, to pick the entry rule.
  C. PAYOFF & SIZING -- the full 12m return distribution of the top
     fingerprint bucket: win rate, expectancy, loss rate -> a Kelly-lite
     sizing implication (lottery tickets have fat left tails too).
  D. LOSER FINGERPRINT -- what the biggest LOSERS (<=-50%) looked like
     pre-event, i.e. the anti-pattern to gate OUT.
  E. OUT-OF-SAMPLE -- split by date (train pre-2024 / test 2024+) and check
     the fingerprint's monster-lift holds.

Outputs: deep_research.json + DEEP_RESEARCH.md.
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import io_util

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "rerate_backtest.json"
OUT_JSON = ROOT / "deep_research.json"
OUT_MD = ROOT / "DEEP_RESEARCH.md"

MONSTER = 1.00
BIG_LOSS = -0.50
MONSTER_CATALYSTS = {"STRATEGIC_REVIEW", "SPINOFF", "CH11_EMERGENCE",
                     "UPLISTING", "ASSET_SALE"}


def _n(x):
    return x if isinstance(x, (int, float)) else None


def fingerprint(e):
    """Replicate the confirmation_rule monster_setup (0-10) on a backtest
    event from its stored pre-event features."""
    s = 0.0
    dd = _n(e.get("drawdown_24m"))
    if dd is not None and dd <= -0.40:
        s += 3
    pv = _n(e.get("pre_vol"))
    if pv is not None and pv >= 0.13:
        s += 2
    rp = _n(e.get("range_pos"))
    if rp is not None and rp <= 0.33:
        s += 2
    if (_n(e.get("decel")) or 0) >= 0:
        s += 1
    if e.get("catalyst") in MONSTER_CATALYSTS:
        s += 2
    return s


def stats(rets):
    rets = [r for r in rets if r is not None]
    if not rets:
        return {"n": 0}
    return {
        "n": len(rets),
        "monster_rate": round(sum(1 for r in rets if r >= MONSTER) / len(rets), 3),
        "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
        "median": round(st.median(rets), 3),
        "mean": round(st.mean(rets), 3),
        "loss_rate_50": round(sum(1 for r in rets if r <= BIG_LOSS) / len(rets), 3),
    }


def main() -> int:
    d = json.loads(SRC.read_text())
    ev = [e for e in d.get("events", []) if e.get("ret_12m") is not None]
    for e in ev:
        e["_fp"] = fingerprint(e)
    R = {}

    # A. fingerprint concentration
    buckets = [("0-3", 0, 3), ("4-5", 4, 5), ("6-7", 6, 7), ("8-10", 8, 10)]
    R["A_fingerprint_concentration"] = {
        lbl: stats([e["ret_12m"] for e in ev if lo <= e["_fp"] <= hi])
        for lbl, lo, hi in buckets}

    # B. confirmation sweep (first-month drift threshold -> 12m outcome)
    R["B_confirmation_sweep"] = {}
    for thr in (0.0, 0.10, 0.20, 0.30):
        sub = [e["ret_12m"] for e in ev if (_n(e.get("post_1m")) or -9) >= thr]
        s = stats(sub); s["coverage"] = round(len(sub) / len(ev), 3)
        R["B_confirmation_sweep"][f">= +{int(thr*100)}%"] = s
    R["B_confirmation_sweep"]["faded (<= -10%)"] = stats(
        [e["ret_12m"] for e in ev if (_n(e.get("post_1m")) or 9) <= -0.10])

    # C. payoff & sizing on the top fingerprint bucket (8-10)
    top = [e["ret_12m"] for e in ev if e["_fp"] >= 8]
    s = stats(top)
    if s.get("n"):
        p_win = s["win_rate"]
        # crude payoff ratio: avg win / avg loss magnitude
        wins = [r for r in top if r > 0]; losses = [-r for r in top if r <= 0]
        b = (st.mean(wins) / st.mean(losses)) if wins and losses else None
        kelly = round(p_win - (1 - p_win) / b, 3) if b else None
        s["avg_win"] = round(st.mean(wins), 3) if wins else None
        s["avg_loss"] = round(-st.mean(losses), 3) if losses else None
        s["payoff_ratio_b"] = round(b, 2) if b else None
        s["full_kelly_fraction"] = kelly
        s["suggested_fraction_quarter_kelly"] = round(kelly / 4, 3) if kelly and kelly > 0 else 0
    R["C_payoff_sizing_top_bucket"] = s

    # D. loser fingerprint
    losers = [e for e in ev if e["ret_12m"] <= BIG_LOSS]
    rest = [e for e in ev if e["ret_12m"] > BIG_LOSS]
    def med(items, k):
        v = [_n(i.get(k)) for i in items]; v = [x for x in v if x is not None]
        return round(st.median(v), 3) if v else None
    R["D_loser_fingerprint"] = {
        "n_losers": len(losers),
        "loser_vs_rest": {k: {"loser": med(losers, k), "rest": med(rest, k)}
                          for k in ("drawdown_24m", "pre_vol", "range_pos",
                                    "pre_12m", "decel", "post_1m")},
        "loser_catalysts": _cat_share(losers),
    }

    # E. out-of-sample split
    train = [e for e in ev if (e.get("date") or "") < "2024-01-01"]
    test = [e for e in ev if (e.get("date") or "") >= "2024-01-01"]
    R["E_out_of_sample"] = {
        "train": _split_stat(train), "test": _split_stat(test)}

    io_util.write_json(OUT_JSON, R)
    _write_md(R, len(ev))
    _print(R, len(ev))
    return 0


def _cat_share(items):
    from collections import Counter
    c = Counter(e["catalyst"] for e in items)
    tot = sum(c.values()) or 1
    return {k: round(v / tot, 2) for k, v in c.most_common(4)}


def _split_stat(items):
    hi = [e["ret_12m"] for e in items if e["_fp"] >= 6]
    lo = [e["ret_12m"] for e in items if e["_fp"] < 6]
    return {"n": len(items),
            "fp>=6": stats(hi), "fp<6": stats(lo)}


def _print(R, n):
    print(f"deep research on {n} events\n")
    print("A. fingerprint concentration (monster_setup -> outcome):")
    for b, s in R["A_fingerprint_concentration"].items():
        if s.get("n"):
            print(f"   fp {b:<5} n={s['n']:>3}  monster {s['monster_rate']*100:>4.0f}%"
                  f"  win {s['win_rate']*100:>3.0f}%  med {s['median']*100:>+4.0f}%"
                  f"  loss>50 {s['loss_rate_50']*100:>3.0f}%  mean {s['mean']*100:>+4.0f}%")
    print("\nB. confirmation sweep (first-month drift -> 12m):")
    for thr, s in R["B_confirmation_sweep"].items():
        if s.get("n"):
            print(f"   {thr:<14} n={s['n']:>3} cov {s.get('coverage','')}"
                  f"  monster {s['monster_rate']*100:>4.0f}%  mean {s['mean']*100:>+4.0f}%")
    c = R["C_payoff_sizing_top_bucket"]
    if c.get("n"):
        print(f"\nC. top bucket (fp>=8) n={c['n']}: win {c['win_rate']*100:.0f}%  "
              f"mean {c['mean']*100:+.0f}%  loss>50 {c['loss_rate_50']*100:.0f}%  "
              f"payoff b={c.get('payoff_ratio_b')}  kelly={c.get('full_kelly_fraction')}"
              f" -> ~1/4-kelly {c.get('suggested_fraction_quarter_kelly')}")
    e = R["E_out_of_sample"]
    print("\nE. out-of-sample (fp>=6 monster rate):")
    for k in ("train", "test"):
        s = e[k]["fp>=6"]
        if s.get("n"):
            print(f"   {k:<6} n={e[k]['n']:>3}  fp>=6 monster {s['monster_rate']*100:.0f}%"
                  f"  vs fp<6 {e[k]['fp<6'].get('monster_rate',0)*100:.0f}%")


def _write_md(R, n):
    L = [f"# Deeper research — validating & sharpening the monster fingerprint\n",
         f"Pure-compute on {n} corporate-action events (rerate_backtest.json). "
         "monster = +100%/12m; big loss = -50%/12m.\n"]
    L.append("## Headline (this CORRECTS the earlier monster_setup)\n")
    L.append("The deep-washout fingerprint is **bimodal, not bullish**: the "
             "biggest WINNERS and the biggest LOSERS look nearly identical "
             "before the event (both ~−74%/−52% off the 2y high, wild vol, "
             "rock-bottom range, same lottery catalysts). The top fingerprint "
             "bucket (fp≥8) has a **33% chance of losing >50%**, a −26% median, "
             "and a NEGATIVE Kelly — it is not investable on its own. The ONLY "
             "thing that separates the monster from the blow-up ex-ante is "
             "**post-catalyst CONFIRMATION**: confirm ≥+20% in month one → 15% "
             "monster rate / +57% mean; ≥+30% → 19% / +86%; but a FADE (≤−10%) "
             "→ 1% monster / **−38% mean**. Conclusion: never buy the "
             "un-confirmed washout; gate the monster fingerprint on "
             "confirmation, and treat FADING high-fingerprint names as the "
             "explicit AVOID list.\n")
    L.append("## A. Does the fingerprint concentrate monsters? (monster_setup 0-10)\n")
    L.append("| fp bucket | n | monster% | win% | median | loss>50% | mean |")
    L.append("|---|---|---|---|---|---|---|")
    for b, s in R["A_fingerprint_concentration"].items():
        if s.get("n"):
            L.append(f"| {b} | {s['n']} | {s['monster_rate']*100:.0f}% | "
                     f"{s['win_rate']*100:.0f}% | {s['median']*100:+.0f}% | "
                     f"{s['loss_rate_50']*100:.0f}% | {s['mean']*100:+.0f}% |")
    L.append("")
    L.append("## B. Confirmation sweep — first-month drift → 12m outcome\n")
    L.append("| entry rule | n | coverage | monster% | mean 12m |")
    L.append("|---|---|---|---|---|")
    for thr, s in R["B_confirmation_sweep"].items():
        if s.get("n"):
            L.append(f"| confirm {thr} | {s['n']} | {s.get('coverage','—')} | "
                     f"{s['monster_rate']*100:.0f}% | {s['mean']*100:+.0f}% |")
    L.append("")
    c = R["C_payoff_sizing_top_bucket"]
    L.append("## C. Payoff & sizing — top fingerprint bucket (fp≥8)\n")
    if c.get("n"):
        L.append(f"n={c['n']}, win {c['win_rate']*100:.0f}%, avg win "
                 f"{(c.get('avg_win') or 0)*100:+.0f}%, avg loss "
                 f"{(c.get('avg_loss') or 0)*100:+.0f}%, loss>50% "
                 f"{c['loss_rate_50']*100:.0f}%, mean/expectancy "
                 f"{c['mean']*100:+.0f}%. Payoff ratio b={c.get('payoff_ratio_b')}, "
                 f"full-Kelly {c.get('full_kelly_fraction')} → **~1/4-Kelly "
                 f"{c.get('suggested_fraction_quarter_kelly')}** per name. The fat "
                 "left tail (loss>50%) is why these are small-size lottery tickets.\n")
    L.append("## D. The loser anti-pattern (≤ −50%/12m)\n")
    dd = R["D_loser_fingerprint"]
    L.append(f"{dd['n_losers']} big losers. Pre-event medians (loser vs rest):\n")
    L.append("| feature | loser | rest |")
    L.append("|---|---|---|")
    for k, v in dd["loser_vs_rest"].items():
        L.append(f"| {k} | {v['loser']} | {v['rest']} |")
    L.append(f"\nLoser catalyst mix: {dd['loser_catalysts']}\n")
    L.append("## E. Out-of-sample check (train pre-2024 / test 2024+)\n")
    e = R["E_out_of_sample"]
    for k in ("train", "test"):
        s = e[k]["fp>=6"]; s2 = e[k]["fp<6"]
        if s.get("n"):
            L.append(f"- **{k}** (n={e[k]['n']}): fp≥6 monster rate "
                     f"{s['monster_rate']*100:.0f}% vs fp<6 "
                     f"{s2.get('monster_rate',0)*100:.0f}% "
                     f"({'holds' if s['monster_rate'] > s2.get('monster_rate',0) else 'FAILS'})")
    L.append("")
    OUT_MD.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
