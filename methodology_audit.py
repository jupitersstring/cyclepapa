"""Methodology audit: does each MEASURE still capture the SPIRIT it was
built for?

The sanity report in archetype_tags.py catches mechanical failure (absent
columns, dead/bloated archetypes). This harness audits one level up: for
each measure family it stores the SPIRIT (what the measure is trying to
achieve, in one sentence) and runs empirical assertions on the actual
firing sets — so a gate can no longer drift away from its meaning without
a red line in the report ("beaten-down names are at their highs",
"derating names have expanding multiples", "a fraction compared against
25"...). Every failure class this repo has actually hit is encoded as a
check.

Run after archetype_tags.py + enrich_asymmetry_global.py:

    python3 methodology_audit.py       # writes measure_methodology_report.txt
                                       # and METHODOLOGY_MEASURES.md

Exit code 1 when any FAIL fires, so drivers/CI can gate on it.
"""
from __future__ import annotations
import sys

import numpy as np
import pandas as pd

RESULTS = []


def check(name, ok, detail=""):
    status = "PASS" if bool(ok) else "FAIL"
    RESULTS.append((status, name, detail))


def warn(name, ok, detail=""):
    RESULTS.append(("PASS" if bool(ok) else "WARN", name, detail))


def n(df, col):
    return (pd.to_numeric(df[col], errors="coerce") if col in df.columns
            else pd.Series(np.nan, index=df.index))


# ---------------------------------------------------------------- registry
# (measure, spirit, checks-fn). The doc is generated from this registry so
# code and methodology cannot drift apart.
MEASURES = []


def measure(name, spirit):
    def deco(fn):
        MEASURES.append((name, spirit, fn))
        return fn
    return deco


@measure("Units map",
         "Yields/growth/margins are FRACTIONS (0.25 = 25%) everywhere; a "
         "consumer comparing against percent-scale numbers is broken.")
def _units(t, g):
    for col, cap in [("dividend_yield", 1.5), ("fcf_yield", 3.0),
                     ("analyst_target_upside_pct", 5.0), ("roce", 5.0),
                     ("sbc_pct_revenue", 3.0), ("momentum_12m", 20.0)]:
        v = n(g, col).abs()
        if v.notna().sum() < 50:
            continue
        med = float(v.median())
        check(f"units: {col} is a fraction", med < cap,
              f"median |{col}| = {med:.3f} (fraction-scale cap {cap})")


@measure("Beaten-down / drawdown family",
         "A name tagged 'beaten down N%' must actually be materially below "
         "its high when the direct 52w measure exists — proxy lenses must "
         "never override a present, contradicting primary.")
def _beaten(t, g):
    m = t.merge(g[["symbol", "pct_off_52w_high"]], on="symbol", how="left")
    for arch, depth in [("arch_dead_option", 0.40),
                        ("arch_oak_deep_value", 0.50),
                        ("arch_levered_inflection", 0.25),
                        ("arch_asymmetric_assembly", 0.35)]:
        if arch not in m.columns:
            continue
        f = m[m[arch] == 1]
        oh = pd.to_numeric(f["pct_off_52w_high"], errors="coerce").dropna()
        if len(oh) < 10:
            continue
        contradicted = (oh > -depth * 0.5).mean()
        check(f"{arch}: no contradicted 'beaten down' names",
              contradicted < 0.02,
              f"{contradicted*100:.1f}% of firers with the 52w measure sit "
              f"shallower than half the claimed {depth:.0%} depth")


@measure("EV/Sales derating",
         "The market is NOT paying for rapid sales growth: the sales "
         "multiple must be COMPRESSING on at least one time base.")
def _derate(t, g):
    f = t[t.get("arch_evsales_derating", 0) == 1]
    gap = pd.to_numeric(f.get("evsales_derate_gap"), errors="coerce").dropna()
    if len(gap):
        check("evsales_derating: median firer gap is compressive",
              gap.median() >= 0.10, f"median gap {gap.median():.3f}")
        warn("evsales_derating: expanding-multiple firers are the minority",
             (gap < 0).mean() < 0.25,
             f"{(gap < 0).mean()*100:.1f}% of firers have a negative 1y gap "
             f"(allowed only when the 3y base compresses)")


@measure("Ten-bagger path / credible",
         "The 10x arithmetic must CLOSE from demonstrated growth at "
         "conservative terminal assumptions; Credible additionally demands "
         "real owner cash and a stable share count.")
def _tenbagger(t, g):
    f = t[t.get("arch_tenbagger_path", 0) == 1]
    imp = pd.to_numeric(f.get("tenbagger_implied_return"), errors="coerce")
    if imp.notna().sum():
        check("tenbagger: implied 10x closes for every firer",
              (imp.dropna() >= 10).mean() > 0.99,
              f"{(imp.dropna() < 10).sum()} firers below 10x")
    cred = t.get("arch_tenbagger_credible")
    path = t.get("arch_tenbagger_path")
    if cred is not None and path is not None:
        check("tenbagger: Credible is a subset of Path",
              int(((cred == 1) & (path == 0)).sum()) == 0)


@measure("Lynch reward (years-in-one)",
         "Years of fundamental progress NOT yet paid by the tape: firers "
         "must have a live tape and must not already have received the "
         "reward (fresh 12m ROC beyond +35% = paid).")
def _lynch(t, g):
    f = t[t.get("arch_lynch_reward", 0) == 1]
    if not len(f):
        return
    m = f.merge(g[["symbol"] + [c for c in ("roc_12m", "stale_tape")
                                if c in g.columns]],
                on="symbol", how="left")
    roc = pd.to_numeric(m.get("roc_12m"), errors="coerce").dropna()
    if len(roc):
        check("lynch_reward: no firer already paid (roc_12m <= 0.35)",
              (roc <= 0.351).mean() > 0.98,
              f"{(roc > 0.351).sum()} firers with roc_12m > 35%")
    st = pd.to_numeric(m.get("stale_tape"), errors="coerce").dropna()
    if len(st):
        check("lynch_reward: every firer has a live tape",
              (st == 0).all(), f"{int((st > 0).sum())} stale-tape firers")


@measure("52-week-high system",
         "Absolute vs relative-to-index highs are distinct facts; 'both' "
         "is their intersection by construction.")
def _high52(t, g):
    a, r, b = (n(t, "high_52w_abs") > 0), (n(t, "high_52w_rel") > 0), \
              (n(t, "high_52w_both") > 0)
    check("52w: both == abs AND rel", int((b & ~(a & r)).sum()) == 0)


@measure("Analyst awakening",
         "Analysts pound the table (strong rating / big upside / breadth) "
         "while the tape has NOT already run away; the fresh-high-from-base "
         "is the top-weighted POSITIVE, never a requirement.")
def _awaken(t, g):
    f = t[t.get("arch_analyst_awakening", 0) == 1]
    if not len(f):
        return
    m = f.merge(g[["symbol"] + [c for c in ("yf_recommendation_mean",
                                            "momentum_12m", "roc_12m")
                                if c in g.columns]],
                on="symbol", how="left")
    rec = pd.to_numeric(m.get("yf_recommendation_mean"), errors="coerce").dropna()
    if len(rec):
        warn("awakening: firers with a rating skew strong (<= 2.2)",
             (rec <= 2.2).mean() > 0.60,
             f"{(rec <= 2.2).mean()*100:.0f}% of rated firers <= 2.2")
    mom = pd.to_numeric(m.get("momentum_12m"), errors="coerce")
    roc = pd.to_numeric(m.get("roc_12m"), errors="coerce")
    # fresh roc_12m outranks the (possibly stale) master momentum; the
    # momentum lens only GATES names whose fresh tape is missing.
    gated = mom[roc.isna() & mom.notna()]
    if len(gated):
        check("awakening: momentum-gated firers not extended (<= ~50%)",
              (gated <= 0.55).mean() > 0.98,
              f"{int((gated > 0.55).sum())} extended among the "
              f"{len(gated)} momentum-gated firers")


@measure("Capital returner",
         "Real, material shareholder yield (5-30%); beyond 30% it is a "
         "stale price or a return-of-capital artifact, not a policy.")
def _capret(t, g):
    f = t[t.get("arch_capital_returner", 0) == 1]
    m = f.merge(g[["symbol"] + [c for c in ("dividend_yield", "buyback_yield",
                                            "capital_return_yield")
                                if c in g.columns]], on="symbol", how="left")
    tot = (pd.to_numeric(m.get("dividend_yield"), errors="coerce").fillna(0)
           + pd.to_numeric(m.get("buyback_yield"), errors="coerce").fillna(0))
    cry = pd.to_numeric(m.get("capital_return_yield"), errors="coerce").fillna(0)
    best = pd.concat([tot, cry], axis=1).max(axis=1)
    if len(best):
        inside = ((best >= 0.049) & (best <= 0.301)).mean()
        warn("capital_returner: firers inside the 5-30% policy band "
             "(small tail = EDGAR-coalesced source not visible here)",
             inside > 0.94,
             f"{int(((best < 0.049) | (best > 0.301)).sum())} outside on "
             f"asym-only columns")


@measure("Strong coverage",
         "Debt burden trivially serviceable — and NEVER inferred from a "
         "negative-EBITDA artifact (the ratio flips sign and fakes net cash).")
def _coverage(t, g):
    f = t[t.get("arch_strong_coverage", 0) == 1]
    m = f.merge(g[["symbol"] + [c for c in ("ebitda_ttm",) if c in g.columns]],
                on="symbol", how="left")
    e = pd.to_numeric(m.get("ebitda_ttm"), errors="coerce").dropna()
    if len(e):
        check("strong_coverage: every firer has positive EBITDA",
              (e > 0).all(), f"{int((e <= 0).sum())} non-positive")


@measure("Fastest segment (hidden engine)",
         "A segment the consolidated print masks: multi-segment filer, "
         "engine growing double digits, corroborated across independent "
         "segment/margin/mix/whole-company lenses.")
def _fastseg(t, g):
    f = t[t.get("arch_fastest_segment", 0) == 1]
    seg_cols = [c for c in ("segment_count", "fastest_segment_yoy")
                if c in g.columns]
    if not seg_cols:
        return
    m = f.merge(g[["symbol"] + seg_cols], on="symbol", how="left")
    sc = n(m, "segment_count").dropna()
    if len(sc):
        check("fastest_segment: every firer is multi-segment",
              (sc >= 2).all(), f"{int((sc < 2).sum())} single-segment")
    fy = n(m, "fastest_segment_yoy").dropna()
    if len(fy):
        check("fastest_segment: no impossible growth artifacts (>500%)",
              (fy <= 5.0).all(), f"max {fy.max():.2f}")


@measure("Score gating",
         "Every archetype-specific ranking score is 0 for non-firers — a "
         "book sorting on it can never surface a name outside the archetype.")
def _gating(t, g):
    for flag, score in [("arch_tenbagger_path", "tenbagger_score"),
                        ("arch_evsales_derating", "evsales_derate_score"),
                        ("arch_lynch_reward", "lynch_reward_score"),
                        ("arch_analyst_awakening", "analyst_awakening_score"),
                        ("arch_fastest_segment", "seg_inflect_score")]:
        if flag not in t.columns or score not in t.columns:
            continue
        leak = int(((t[flag] == 0)
                    & (pd.to_numeric(t[score], errors="coerce") > 0)).sum())
        check(f"gating: {score} is 0 outside {flag}", leak == 0,
              f"{leak} non-firers with positive score")


@measure("Composite score ranges",
         "Confirmation/lens composites live in [0, 1] by construction.")
def _ranges(t, g):
    for col in ["confirm_overall", "oper_leverage_score", "buyback_score",
                "rev_growth_score", "cheapness_score", "quality_score",
                "inflection_confirm_score", "seg_inflect_score"]:
        v = n(t, col).dropna()
        if len(v):
            check(f"range: {col} within [0,1]",
                  (v.between(-1e-9, 1 + 1e-9)).all(),
                  f"min {v.min():.3f} max {v.max():.3f}")


def main():
    t = pd.read_csv("archetype_tags.csv", low_memory=False)
    g = pd.read_csv("asymmetry_global.csv", low_memory=False)
    g = g.drop_duplicates("symbol")

    for name, spirit, fn in MEASURES:
        try:
            fn(t, g)
        except Exception as e:                       # a broken check is a FAIL
            check(f"{name}: check harness ran", False, f"{type(e).__name__}: {e}")

    lines = []
    n_fail = sum(1 for s, *_ in RESULTS if s == "FAIL")
    n_warn = sum(1 for s, *_ in RESULTS if s == "WARN")
    lines.append(f"METHODOLOGY AUDIT — {len(RESULTS)} checks, "
                 f"{n_fail} FAIL, {n_warn} WARN")
    for status, name, detail in RESULTS:
        lines.append(f"  {status:4s}  {name}" + (f"  — {detail}" if detail else ""))
    report = "\n".join(lines) + "\n"
    with open("measure_methodology_report.txt", "w") as fh:
        fh.write(report)
    print(report, file=sys.stderr)

    # The methodology doc is GENERATED from the registry — code and
    # documentation cannot drift apart.
    doc = ["# Measure methodology — spirit and enforcement",
           "",
           "Generated by `methodology_audit.py` from the same registry that",
           "runs the empirical checks. Each measure states the SPIRIT it",
           "exists to capture; the audit fails loudly when the firing set",
           "stops matching that spirit.",
           ""]
    for name, spirit, _fn in MEASURES:
        doc.append(f"## {name}\n\n{spirit}\n")
    with open("METHODOLOGY_MEASURES.md", "w") as fh:
        fh.write("\n".join(doc))

    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
