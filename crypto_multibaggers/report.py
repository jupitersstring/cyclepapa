"""Write data/crypto_multibaggers/REPORT.md and the narrative blocks of the atlas
from atlas.json and the analysis CSVs.

    python -m crypto_multibaggers.report
"""
from __future__ import annotations

import json
import math

import pandas as pd

from .config import ANALYSIS_DIR, DATA_DIR


def _p(x, d=0):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.{d}f}%"


def _f(x, d=2):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


def _pct_move(logx):
    return "–" if logx is None or (isinstance(logx, float) and math.isnan(logx)) else f"{100 * (math.exp(logx) - 1):+.0f}%"


def _grid_row(a, feature, fam):
    for r in a["grid"]["rows"]:
        if r["feature"] == feature and r["family"] == fam:
            return r
    return {}


def narrative(a: dict) -> dict:
    fam = {f["key"]: f for f in a["families"]}
    base = a["placebo_rates"]
    g = lambda f, k="all": _grid_row(a, f, k).get("auc", float("nan"))
    tl = pd.DataFrame(a.get("trigger_lb", []))
    lb = pd.DataFrame(a["screen"]["leaderboard"])
    ao = pd.DataFrame(a.get("arch_oos", []))
    top_screen = lb.iloc[0]
    d0 = tl[tl.feature == "d0_ret"].iloc[0] if len(tl) and (tl.feature == "d0_ret").any() else None
    best_arch = ao.dropna(subset=["conversion_test"]).sort_values("conversion_test", ascending=False).iloc[0] if len(ao) else None
    takes = {
        "b": (f"In equities, abnormal volume builds for weeks before a re-rating. In crypto it does not: final-week volume "
              f"sits at placebo levels (AUC {_f(g('av_mean_S'))}), and before 10x runs the prior two months are quieter than "
              f"ordinary tape (AUC {_f(g('av_mean_L', '10x+'))}). What moves first is volatility: final-week volatility "
              f"against the coin's own baseline is the strongest single separator (AUC {_f(g('vol_ratio_S'))}, "
              f"{_f(g('vol_ratio_S', '10x+'))} before 10x runs), with prior up-spikes and a high VPIN percentile close behind. "
              f"Prices were falling into day 0: run-up {_pct_move(fam['all']['runup'])} over 60 days."),
        "d": (f"Once a coin pops, strength separates the multibaggers. The day-0 move itself is the best single tell, then "
              f"money flow, a less negative 60-day trend and more days above the 20-day average. Younger, smaller coins that "
              f"trade less with the market convert more often. Faded pops come out of steeper downtrends with persistent selling."),
        "g": (f"Two different questions have two different answers. Which coins will 3x at some point? The washed-out ones: "
              f"deep 60-day drawdowns, trading under their 50- and 200-day averages and lagging BTC "
              f"({top_screen['label'].lower()}: {_f(top_screen['lift_test'])}x the base rate in 2022+). Which pops will follow "
              f"through? The strong ones: "
              + (f"the top fifth of 2022+ triggers by day-0 return reached 3x {_p(d0['hit_test'])} of the time vs "
                 f"{_p(d0['base_test'])} for all triggers. " if d0 is not None else "")
              + (f"The best archetype out of time was '{best_arch['name']}': fitted on 2017-21, it converted "
                 f"{_p(best_arch['conversion_test'])} of 2022+ triggers vs {_p(best_arch['base_test'])}. " if best_arch is not None else "")
              + "As standalone screens the toxic overlays do not beat their plain signals; their value is in the archetypes."),
    }
    use = [
        {"h": "Watch", "p": "Screen for washed-out coins whose volatility is waking up: a deep 60-day drawdown, below the 50- and "
                            "200-day averages, final-week volatility above the coin's own baseline and a high VPIN percentile. "
                            "Volume does not have to lead; quiet tapes produce the biggest runs."},
        {"h": "Confirm", "p": "Act on the pop, not before it. A big day-0 move (in sigmas and in percent), new 60-day highs in the "
                              "prior three weeks, positive toxic momentum and a toxic-breakout archetype are what separated "
                              "multibaggers from faded pops out of time."},
        {"h": "Avoid", "p": "Pops out of steep downtrends with persistent selling (negative money flow), coins that move with the "
                            "market, and busy, already-promoted tapes: heavy prior volume and volume build-ups precede faded pops "
                            "more than 10x runs."},
    ]
    footer = [
        f"Data: Financial Modeling Prep (universe of {a['n_universe']:,} crypto USD pairs and daily bars), CoinMetrics community API "
        f"(network activity, holders, supply, MVRV, market cap), DefiLlama (TVL, fees), CoinGecko categories (sectors). As of {a['asof']}.",
        "Code and full outputs: crypto_multibaggers/ and data/crypto_multibaggers/ (REPORT.md, analysis/*.csv, events_master.csv.gz).",
        "Etherscan: a V2 client for ERC-20 transfer data (onchain.Etherscan, transfer_activity: daily transfers, unique "
        "senders and receivers, first-time receivers) is included but was not run, because Etherscan refuses keyless requests. "
        "With ETHERSCAN_API_KEY in the environment, the next step is to pull transfers for the ERC-20 event windows. The toxic breakout, "
        "momentum, trend and OBV overlays are defined here from their names (VPIN above the coin's baseline 80th percentile, with "
        "buy-side BVC imbalance); the attribution engine's own definitions were not available to this session.",
        "Coins younger than 121 days cannot have a baseline, so launch-week memecoin runs are out of scope. Aggregated crypto bars "
        "carry placeholder, ticker-reuse and bad-print artefacts; the cleaning rules drop those windows, which also removes some "
        "genuine crash days. Research only, not investment advice.",
    ]
    return {"takes": takes, "use": use, "footer": footer}


def write_report(a: dict, nar: dict) -> str:
    fams = pd.DataFrame(a["families"])
    base = a["placebo_rates"]
    lines = [
        "# Crypto multibagger tape study",
        "",
        f"As of {a['asof']}. {a['n_events']:,} crypto re-ratings ({a['first']}-{a['last']}) across {a['n_tokens']:,} coins, "
        f"{a['n_placebo']:,} matched placebo windows, 180-day outcomes. Crypto counterpart of the equity special-situations "
        "tape study (same measures and placebo design).",
        "",
        "## What the study found",
        "",
        f"- **{_p(fams.loc[fams.key == 'all', 'p_3x'].item())} of re-ratings reached 3x within 180 days and "
        f"{_p(fams.loc[fams.key == 'all', 'p_10x'].item(), 1)} reached 10x**, against {_p(base['p_3x'], 1)} and "
        f"{_p(base['p_10x'], 1)} for matched placebo windows.",
        f"- {nar['takes']['b']}",
        f"- {nar['takes']['d']}",
        f"- {nar['takes']['g']}",
        "",
        "## Exhibit A: families",
        "",
        "| Family | Events | Coins | Paid | Durable 60d | 3x+ | 10x+ | Median multiple | Run-up -60..-1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for f in [f for f in a["families"] if not f["key"].startswith("sector:")]:
        lines.append(f"| {f['label']} | {f['events']:,} | {f['tokens']:,} | {_p(f['paid'])} | {_p(f['durable'])} | "
                     f"{_p(f['p_3x'])} | {_p(f['p_10x'], 1)} | {_f(f['mult_med'])}x | {_pct_move(f['runup'])} |")
    lines.append(f"| Matched placebo windows | {a['n_placebo']:,} | | {_p(base['paid'])} | {_p(base['durable'])} | "
                 f"{_p(base['p_3x'])} | {_p(base['p_10x'], 1)} | {_f(base['mult_med'])}x | |")
    if a.get("sectors"):
        lines += ["", "| Sector | Events | Coins | 3x+ | 10x+ | Durable 60d | Median multiple |", "|---|---:|---:|---:|---:|---:|---:|"]
        for r in a["sectors"]:
            lines.append(f"| {r['sector']} | {r['events']:,} | {r['tokens']:,} | {_p(r['p_3x'])} | {_p(r['p_10x'], 1)} | "
                         f"{_p(r['durable'])} | {_f(r['mult_med'])}x |")
    grid = pd.DataFrame(a["grid"]["rows"])
    w = grid.pivot_table(index="label", columns="family", values="auc")
    cols = [c["key"] for c in a["grid"]["families"]]
    w = w[cols]
    w = w.reindex(w["all"].sub(0.5).abs().sort_values(ascending=False).index).head(20)
    lines += ["", "## Exhibit C: events vs matched placebo (AUC, top 20 by |AUC-0.5| across all re-ratings)", "",
              "| Measure | " + " | ".join(c["label"] for c in a["grid"]["families"]) + " |",
              "|---|" + "---:|" * len(cols)]
    for lab, r in w.iterrows():
        lines.append(f"| {lab} | " + " | ".join(_f(r[c]) for c in cols) + " |")
    W = a["winners"]
    lines += ["", f"## Exhibit D: 3x+ multibaggers ({W['n_w']:,}) vs faded pops ({W['n_l']:,})", "",
              "| Measure | AUC | Multibaggers (median) | Faded (median) | q |", "|---|---:|---:|---:|---:|"]
    for r in W["rows"]:
        lines.append(f"| {r['label']} | {_f(r['auc'])} | {_f(r['m_w'])} | {_f(r['m_l'])} | {r['q']:.1e} |")
    lines += ["", "## Exhibit F: pre-re-rating archetypes (GMM on the pre-event tape of 3x+ multibaggers)", "",
              f"k = {a['arch_info']['k']} (BIC), mean adjusted Rand index across seeds {_f(a['arch_info']['ari_mean'])}, "
              f"base conversion of all triggers to 3x {_p(a['arch_info']['base_conversion'])}.", "",
              "| Archetype | Multibaggers | Lift vs placebo | Placebo share | Conversion of triggers | Median multiple | 10x+ share |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for r in a["archetypes"]:
        lines.append(f"| {r['name']} | {r['n']:,} | {_f(r['lift'], 1)}x | {_p(r['ctl'], 1)} | {_p(r['conversion'])} | "
                     f"{_f(r['mult_med'])}x | {_p(r['p_10x'])} |")
    if a.get("arch_oos"):
        lines += ["", "Out of time (fitted on 2017-21 multibaggers, applied to 2022+ triggers):", "",
                  "| Archetype (2017-21 fit) | Conversion 2017-21 | 2022+ triggers | Conversion 2022+ | Base 2022+ |",
                  "|---|---:|---:|---:|---:|"]
        for r in sorted(a["arch_oos"], key=lambda r: -(r["conversion_test"] or -1)):
            lines.append(f"| {r['name']} | {_p(r['train_conversion'])} | {r['n_test']:,} | {_p(r['conversion_test'])} | "
                         f"{_p(r['base_test'])} |")
    S = a["screen"]
    lines += ["", "## Exhibit G: what works best", "",
              f"Unconditional screen: every eligible coin every 14 days ({S['n']:,} coin-dates), label 3x within 180 days "
              f"(base {_p(S['base3'], 1)} over 2017-26). Direction fixed on 2017-21, scored on 2022+.", "",
              "| Signal | Direction | AUC 2022+ | Top-decile 3x rate 2022+ | Base | Lift 2022+ | Lift 2017-21 |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for r in S["model"] + S["leaderboard"][:15]:
        lines.append(f"| {r['label']} | {'high' if r['direction'] > 0 else 'low'} | {_f(r['auc_test_dir'])} | {_p(r['hit_test'], 1)} | "
                     f"{_p(r['base_test'], 1)} | {_f(r['lift_test'])}x | {_f(r['lift_train'])}x |")
    lines += ["", "Toxic overlays vs plain signals (same screen, 2022+):", "",
              "| Signal | Plain AUC | Toxic AUC | Plain lift | Toxic lift |", "|---|---:|---:|---:|---:|"]
    for r in S["pairs"]:
        lines.append(f"| {r['signal']} | {_f(r['plain_auc'])} | {_f(r['toxic_auc'])} | {_f(r['plain_lift'])}x | {_f(r['toxic_lift'])}x |")
    if a.get("recipes"):
        lines += ["", "Best one-, two- and three-signal screens (top quintile on each; chosen on 2017-21):", "",
                  "| Screen | Lift 2017-21 | Coin-dates 2022+ | 3x rate 2022+ | Lift 2022+ |", "|---|---:|---:|---:|---:|"]
        for r in a["recipes"]:
            lines.append(f"| {' + '.join(r['labels'])} | {_f(r['lift_train'])}x | {r['n_test']:,} | {_p(r['hit_test'], 1)} | "
                         f"{_f(r['lift_test'])}x |")
    if a.get("trigger_lb"):
        lines += ["", "Once a coin pops (triggers only; direction from 2017-21, top fifth of 2022+ triggers):", "",
                  "| Measure | Direction | AUC 2022+ | 3x rate, top fifth | Base | Lift |", "|---|---|---:|---:|---:|---:|"]
        for r in a["trigger_lb"][:15]:
            lines.append(f"| {r['label']} | {'high' if r['direction'] > 0 else 'low'} | {_f(r['auc_test'])} | "
                         f"{_p(r['hit_test'], 1)} | {_p(r['base_test'], 1)} | {_f(r['lift_test'])}x |")
    lines += ["", "Classifiers:", "", "| Sample | Model | Split | AUC | Caught at 10% FPR | n |", "|---|---|---|---:|---:|---:|"]
    for c in a["cv"]:
        lines.append(f"| {c['sample']} | {c['model']} | {c['split']} | {_f(c['auc'])} | {_p(c['cap'])} | {c['n']:,} |")
    O = a["onchain"]
    og = pd.DataFrame(O["rows"])
    ow = og.pivot_table(index="label", columns="family", values="auc")[[f["key"] for f in O["families"]]]
    on = og.pivot_table(index="label", columns="family", values="n")["all"]
    lines += ["", "## Exhibit O: on-chain layer (coverage-limited; indicative)", "",
              "| Measure | Events covered | " + " | ".join(f["label"] for f in O["families"]) + " |",
              "|---|---:|" + "---:|" * len(O["families"])]
    for lab, r in ow.iterrows():
        lines.append(f"| {lab} | {int(on[lab]):,} | " + " | ".join(_f(r[k]) for k in ow.columns) + " |")
    lines += ["", "## Exhibit H: validation cases", "",
              "| Case | Date | Trigger | Day-0 return | Best multiple 180d | Return 60d | Pre-event score pct |",
              "|---|---|---|---:|---:|---:|---:|"]
    for v in a["validation"]:
        lines.append(f"| {v['symbol']}: {v['desc']} | {v['date']} | {'yes' if v['trigger'] else 'no'} | "
                     f"{_p(v.get('d0_ret'), 1)} | {_f(v.get('mult_180'))}x | {_pct_move(v.get('r_60'))} | {_p(v.get('score_pct'))} |")
    lines += ["", f"## Exhibit L: live scan ({a['asof']}, top 25 of {a['live_n']:,} tradeable coins)", "",
              "| Coin | Blend | Event-model pct | Screen pct | Archetype | $ volume 7d |", "|---|---:|---:|---:|---|---:|"]
    for r in a["live"][:25]:
        lines.append(f"| {r['symbol'][:-3]} ({r.get('name', '')}) | {_f(r['blend'])} | {_p(r['score_pct'], 1)} | "
                     f"{_p(r['screen_pct'])} | {r['archetype']} | ${r['dv7'] / 1e6:.1f}m |")
    lines += ["", "## Using it", ""] + [f"- **{u['h']}.** {u['p']}" for u in nar["use"]]
    lines += ["", "## Data and caveats", ""] + [f"- {x}" for x in nar["footer"]]
    lines += ["", "Method details: see crypto_multibaggers/README.md.", ""]
    out = DATA_DIR / "REPORT.md"
    out.write_text("\n".join(lines))
    return str(out)


def export_events() -> str:
    """Compact event table for the repo (the parquet caches stay local)."""
    from . import study
    from .analysis import CORE
    ev = study.load()[0]
    keep = ["event_id", "symbol", "name", "date", "tier", "complete", "d0_ret", "d0_z", "car01", "paid", "mult_90",
            "mult_180", "mult_180_entry", "mult_365", "days_to_peak", "r_20", "r_60", "r_180", "maxdd_180", "durable",
            "btc_bull", "_dv_base"] + [c for c in CORE if c not in ("log_dv_base",)]
    out = DATA_DIR / "events_master.csv.gz"
    ev[[k for k in keep if k in ev]].round(5).to_csv(out, index=False, compression="gzip")
    return str(out)


def pa_narrative(pa: dict) -> str:
    by = {}
    for r in pa.get("portfolio", []):
        by.setdefault(r["rule"], {})[r["period"]] = r
    b, base = by.get("don+candles+sanyaku"), by.get("donchian55")
    if not b or not base:
        return ""
    return (f"Qualitative confirmation works the way the old books describe, but only on top of a breakout. A plain 55-day "
            f"breakout lost {_p(-base['test']['cagr'])} a year from 2022; requiring a strong close without bearish candles "
            f"and all four Ichimoku lines bullish made {_p(b['test']['cagr'])} a year with a {_p(-b['test']['max_dd'])} worst "
            f"drawdown, and the same filters also improved 2017-21 ({_p(b['train']['cagr'])} a year vs "
            f"{_p(base['train']['cagr'])}). Reversal-style entries (Heikin-Ashi, Renko and three-line-break turns, "
            f"trendline and head-and-shoulders breaks) lost heavily after 2021. Once a coin pops, Dalton's value migration "
            f"and acceptance, a wide pop-day range and Ichimoku alignment raised the 3x odds by 1.2-1.3x in both periods.")


def pa_report(pa: dict) -> list[str]:
    by = {}
    for r in pa.get("portfolio", []):
        by.setdefault(r["rule"], {})[r["period"]] = r
    trades = {r["rule"]: r for r in pa.get("trades", []) if r["exit"] == "3 ATR chandelier"}
    rows = sorted([r for r in by if "test" in by[r] and "train" in by[r]], key=lambda r: -by[r]["test"]["sharpe"])
    out = ["", "## Exhibit P: price-action schools (Schabacker, Japanese, Dalton)", "",
           pa_narrative(pa), "",
           "Rulebook that held up in both periods: enter on a close at a new 55-day high when that day closes strong (white "
           "marubozu or top quarter of its range), no bearish candle pattern printed in the prior five days and all four "
           "Ichimoku lines agree; exit on a close below the highest close since entry minus 3 ATR (or below Kijun-sen); "
           "1% of equity per trade, one position per coin.", "",
           "Books: 1% of equity per entry, no rebalancing, 3 ATR chandelier exit, 0.25% cost per side (0.5% below $1M/day).", "",
           "| Entry rule | Trades 2022+ | Return/yr 2017-21 | Sharpe 2017-21 | Return/yr 2022+ | Sharpe 2022+ | Max DD 2022+ | Profit factor 2022+ |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        a, b, t = by[r]["train"], by[r]["test"], trades.get(r, {})
        out.append(f"| {b['label']} | {b['trades']:,} | {_p(a['cagr'])} | {_f(a['sharpe'])} | {_p(b['cagr'])} | "
                   f"{_f(b['sharpe'])} | {_p(b['max_dd'])} | {_f(t.get('pf_test'))} |")
    fi = pa.get("follow_info", {})
    out += ["", f"Once a coin pops (triggers only; base 3x rate {_p(fi.get('base_test'), 1)} in 2022+), factors that lifted "
            "the rate in both periods:", "",
            "| Factor | School | Triggers with it 2022+ | 3x rate with | without | Lift 2017-21 | Lift 2022+ |",
            "|---|---|---:|---:|---:|---:|---:|"]
    for r in [r for r in pa.get("follow", []) if r.get("consistent") and r["lift_test"] > 1][:14]:
        out.append(f"| {r['label']} | {r['group']} | {r['n_test']:,} | {_p(r['hit_test'], 1)} | {_p(r['hit_off_test'], 1)} | "
                   f"{_f(r['lift_train'])}x | {_f(r['lift_test'])}x |")
    sc = pa.get("screen", [])
    if sc:
        out += ["", f"As standalone screens (3x hits vs the same-day base rate) the best 2022+ factor reached "
                f"{_f(sc[0]['lift_test'])}x ({sc[0]['label']}); most factors flipped between periods."]
    lv = pa.get("live")
    if lv:
        out += ["", f"Live ({lv['asof']}): {lv['n_breakout']:,} of {lv['n']:,} tradeable coins made a 55-day breakout in the "
                f"last five days; the full rule fired on {lv['n_fired']}: "
                + ", ".join(f"{r['symbol'][:-3]}" for r in lv["fired"]) + "."]
    out += ["", "Dalton's market profile is built from intraday time-price data; here it is adapted to daily bars (value area "
            "from a 20-day volume-weighted price distribution). Windows (gaps) barely exist in a 24/7 market, so gap "
            "patterns drop out."]
    return out


def main():
    print(export_events())
    a = json.loads((DATA_DIR / "atlas.json").read_text())
    nar = narrative(a)
    pa_path = DATA_DIR / "pa_atlas.json"
    pa = json.loads(pa_path.read_text()) if pa_path.exists() else None
    if pa:
        nar["takes"]["p"] = pa_narrative(pa)
    path = write_report(a, nar)
    if pa:
        txt = open(path).read().rstrip("\n").split("\n")
        cut = txt.index("## Exhibit O: on-chain layer (coverage-limited; indicative)") if \
            "## Exhibit O: on-chain layer (coverage-limited; indicative)" in txt else len(txt)
        txt = txt[:cut] + pa_report(pa)[1:] + [""] + txt[cut:]
        open(path, "w").write("\n".join(txt) + "\n")
    print(path)
    from . import atlas_page
    extra = dict(nar)
    if pa:
        extra["pa"] = pa
    print(atlas_page.build(extra=extra))


if __name__ == "__main__":
    main()
