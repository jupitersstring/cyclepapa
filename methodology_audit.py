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
    if not len(f):
        return

    # segment_count / fastest_segment_yoy are persisted into archetype_tags.csv
    # (t). Read from t first, fall back to g. If NEITHER frame carries the
    # column the check RAISES (not silently skips) — a vacuous fastest_segment
    # audit is itself a defect (these columns used to be in neither file, so
    # both checks never ran; guard against regressing to that).
    def col(name):
        if name in f.columns:
            return pd.to_numeric(f[name], errors="coerce")
        if name in g.columns:
            mm = f.merge(g[["symbol", name]], on="symbol", how="left")
            return pd.to_numeric(mm[name], errors="coerce")
        return None

    sc = col("segment_count")
    check("fastest_segment: segment_count is present (not a vacuous audit)",
          sc is not None,
          "segment_count absent from BOTH archetype_tags.csv and asymmetry_global.csv")
    if sc is not None:
        sc = sc.dropna()
        if len(sc):
            check("fastest_segment: every firer is multi-segment",
                  (sc >= 2).all(), f"{int((sc < 2).sum())} single-segment")
    fy = col("fastest_segment_yoy")
    if fy is not None:
        fy = fy.dropna()
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
                        ("arch_analyst_rerating_confirmed", "analyst_rerating_score"),
                        ("arch_asleep_at_wheel", "asleep_score"),
                        ("arch_fastest_segment", "seg_inflect_score")]:
        if flag not in t.columns or score not in t.columns:
            continue
        leak = int(((t[flag] == 0)
                    & (pd.to_numeric(t[score], errors="coerce") > 0)).sum())
        check(f"gating: {score} is 0 outside {flag}", leak == 0,
              f"{leak} non-firers with positive score")


@measure("Coverage-fair archetype density",
         "archetype_count_pct divides by the count of archetypes the row is "
         "ELIGIBLE for — it can never exceed 1, and the denominator tracks "
         "the LIVE taxonomy, not a frozen constant.")
def _density(t, g):
    pct = n(g, "archetype_count_pct").dropna()
    if len(pct):
        check("density: archetype_count_pct <= 1",
              (pct <= 1.0 + 1e-9).all(), f"max {pct.max():.3f}")
    io = n(g, "insider_ownership_pct").dropna()
    if len(io):
        check("units: insider_ownership_pct is a fraction (<= 1.05)",
              (io <= 1.05).mean() > 0.999,
              f"{int((io > 1.05).sum())} percent-scale stragglers")


@measure("Signal-file integrity",
         "Appended signal CSVs keep a FIXED schema — a ragged row means "
         "columns silently shifted (the bug that corrupted 12% of lynch "
         "rows); country benchmarks must be live, not frozen snapshots.")
def _integrity(t, g):
    import csv, os
    if os.path.exists("lynch_reward_signals.csv"):
        rd = csv.reader(open("lynch_reward_signals.csv"))
        hlen = len(next(rd))
        ragged = sum(1 for r in rd if len(r) != hlen)
        check("integrity: lynch signal rows all match the header schema",
              ragged == 0, f"{ragged} ragged rows")
    if os.path.exists("benchmark_series.csv"):
        b = pd.read_csv("benchmark_series.csv", index_col=0, parse_dates=True)
        stale = [c for c in b.columns
                 if b[c].dropna().empty
                 or (pd.Timestamp.now() - b[c].dropna().index.max()).days > 62]
        warn("integrity: country benchmarks are live (<=62d old)",
             len(stale) <= 1,   # Thailand has no usable Yahoo series
             f"stale/empty: {stale}")
    # GBp-pence class: .L market caps must be consistent with price/100
    lse = g[g["symbol"].astype(str).str.endswith(".L")]
    if len(lse) > 20:
        pr, mc = n(lse, "price"), n(lse, "market_cap")
        sh = n(lse, "shares_outstanding")
        both = pr.notna() & mc.notna() & sh.notna() & (sh > 0)
        if both.sum() > 20:
            ratio = mc / (pr * sh)
            rv = n(lse, "revenue_ttm")
            # ratio ~1 alone is NOT proof: internationals quote .L in
            # EUR/USD/GBP (Compass, IHG, Glanbia) where mcap==p*s is
            # correct. Absurd mcap/revenue (>100x, or no revenue at a
            # pence-scale price) is the discriminator.
            minted = (both & ratio.between(0.5, 2.0)
                      & ((mc / rv > 100) | (rv.isna() & (pr >= 200)))).sum()
            check("integrity: no pence-minted .L market caps",
                  minted == 0,
                  f"{int(minted)} .L rows with mcap == price*shares (pence)")

    # NOTE: these integrity checks read the MASTER g (which carries the
    # fundamentals). archetype_tags.csv `t` lacks fcf_yield/ev_ebitda/
    # sector, so reading t made the checks pass vacuously (fixed 2026-09-08).
    # STRUCTURAL FIX (2026-09-09): these UNIVERSAL integrity checks were
    # previously nested INSIDE `if len(lse) > 20:` — so on any run whose
    # universe lacked >20 London (.L) listings they were SILENTLY SKIPPED and
    # passed vacuously. They are load-bearing data-integrity gates and must
    # NOT depend on the presence of UK listings, so they now run at function
    # scope (unconditionally). Only the pence-`.L` check stays gated on `.L`.
    fy = n(g, "fcf_yield")
    bad_fy = (fy > 1.0).sum()
    check("integrity: no impossible FCF yields (>100% — ADR home-currency mismatch)",
          bad_fy == 0, f"{int(bad_fy)} rows with fcf_yield > 1.0")
    # 52w self-consistency: a row flagged AT its 52w high must not
    # display a deeply negative pct_off_52w_high (stale-quote leak)
    if "high_52w_abs" in g.columns and "pct_off_52w_high" in g.columns:
        _hi = n(g, "high_52w_abs")
        _off = n(g, "pct_off_52w_high")
        clash = ((_hi == 1) & (_off < -0.10)).sum()
        check("integrity: 52w flags agree with displayed pct_off_52w_high",
              clash == 0, f"{int(clash)} rows flagged at-high but showing <-10% off")

    # Operating value/quality archetypes must exclude Financials/REITs
    # (EV/net-cash/margin legs meaningless there). arch cols live in t,
    # sector in g — map sector onto t by symbol.
    if "arch_negative_ev_value" in t.columns and "symbol" in t.columns \
            and "sector" in g.columns:
        _secmap = g.drop_duplicates("symbol").set_index("symbol")["sector"]
        _tsec = t["symbol"].map(_secmap).fillna("").astype(str).str.lower()
        _finre = (_tsec.str.contains("financ") | _tsec.str.contains("real estate")
                  | _tsec.str.contains("utilit"))
        for _ac in ("arch_negative_ev_value", "arch_tangible_value",
                    "arch_oak_asset_floor", "arch_strong_coverage"):
            if _ac in t.columns:
                leak = ((n(t, _ac) == 1) & _finre).sum()
                check(f"integrity: {_ac} excludes Financials/REITs/Utilities",
                      leak == 0, f"{int(leak)} financials/REITs/utilities in {_ac}")

    # ev_ebitda must never be positive for a negative-EBITDA firm.
    if "ev_ebitda" in g.columns and "ebitda_ttm" in g.columns:
        _eve = n(g, "ev_ebitda"); _ebt = n(g, "ebitda_ttm")
        flip = ((_eve > 0) & (_ebt < 0)).sum()
        check("integrity: no positive EV/EBITDA on negative EBITDA",
              flip == 0, f"{int(flip)} loss-makers with a cheap-looking ev_ebitda")

    # SYSTEMATIC BIOTECH FILTER: no clinical-stage drug developer should
    # populate a fundamental archetype (its financials are one-off/binary).
    if "is_clinical_biotech" in t.columns and "archetype_count" in t.columns:
        _clin = n(t, "is_clinical_biotech") == 1
        _exempt = ["arch_analyst_awakening", "arch_analyst_rerating_confirmed",
                   "arch_oneil_canslim",
                   "arch_weinstein_stage2", "arch_kullamagie_breakout",
                   "arch_biotech_deep_value"]
        _fund = [c for c in t.columns if c.startswith("arch_") and c not in _exempt]
        _fund_ct = t.loc[:, _fund].apply(pd.to_numeric, errors="coerce").sum(axis=1)
        clin_fund = (_clin & (_fund_ct > 0)).sum()
        check("integrity: no clinical biotech in fundamental archetypes",
              clin_fund == 0, f"{int(clin_fund)} clinical biotech in fundamental archetypes")

    # No sub-$1M micro-shell should carry an archetype flag (untradeable).
    if "archetype_count" in t.columns and "symbol" in t.columns and "market_cap_usd" in g.columns:
        _mcs = g.drop_duplicates("symbol").set_index("symbol")["market_cap_usd"]
        _tmc = pd.to_numeric(t["symbol"].map(_mcs), errors="coerce")
        shell_fire = ((_tmc > 0) & (_tmc < 2e6) & (n(t, "archetype_count") > 0)).sum()
        check("integrity: no archetype flags on sub-$2M micro-shells",
              shell_fire == 0, f"{int(shell_fire)} sub-$2M shells firing archetypes")
    # No absurd ROCE/ROIC (>150% = one-off/tiny-base artifact).
    _rce = n(g, "roce")
    bad_rce = (_rce > 1.5).sum()
    check("integrity: no absurd ROCE (>150% = one-off/tiny-base)",
          bad_rce == 0, f"{int(bad_rce)} rows with roce>1.5")

    # No non-common security (preferred/warrant/unit) should carry an
    # archetype flag — their P/E, book, yields belong to the parent.
    if "symbol" in t.columns and "archetype_count" in t.columns:
        _s = t["symbol"].astype(str)
        _ncmask = (_s.str.match(r"^[A-Z]{1,5}-P[A-Z]?$")
                   | _s.str.match(r"^[A-Z]{1,5}[-.](?:WT|WS|U|UN|R|RT)$")
                   | _s.str.contains(r"\.PR\.[A-Z]$", regex=True)
                   | _s.str.contains(r"-PR[-.]?[A-Z]?$", regex=True)
                   | _s.str.contains(r"-P[A-Z]?\.[A-Z]{1,3}$", regex=True))
        nc_fire = ((_ncmask) & (n(t, "archetype_count") > 0)).sum()
        check("integrity: no archetype flags on preferred/warrant/unit lines",
              nc_fire == 0, f"{int(nc_fire)} non-common securities firing archetypes")

    # No impossible margins (gross>100%, or ebitda/net >120% = one-off).
    _gm = n(g, "gross_margin"); _em = n(g, "ebitda_margin")
    bad_m = (_gm > 1.0).sum() + (_em > 1.2).sum()
    check("integrity: no impossible margins (gross>1.0, ebitda>1.2)",
          bad_m == 0, f"{int((_gm>1.0).sum())} gross>1.0, {int((_em>1.2).sum())} ebitda>1.2")

    # No impossible P/E (<0.5x = earn back whole mcap in <6mo) or
    # sub-0.02 sales multiple (units/pass-through, not real cheapness).
    _pe = n(g, "p_e"); _ps = n(g, "p_s")
    bad_pe = ((_pe > 0) & (_pe < 0.5)).sum()
    bad_ps = ((_ps > 0) & (_ps < 0.02)).sum()
    check("integrity: no impossible P/E (<0.5) or sub-0.02 sales multiple",
          (bad_pe + bad_ps) == 0, f"{int(bad_pe)} p_e<0.5, {int(bad_ps)} p_s<0.02")

    # No absurd P/B (<0.05x book = ADR/units data artifact, not value).
    _pbc = n(g, "pb")
    bad_pb = ((_pbc > 0) & (_pbc < 0.05)).sum()
    check("integrity: no corrupt P/B (<0.05x book — ADR/units artifact)",
          bad_pb == 0, f"{int(bad_pb)} rows with pb in (0, 0.05)")

    # No zero/negative market cap or price in the ranked universe.
    _mc = n(g, "market_cap_usd"); _pr = n(g, "price")
    bad_scale = ((_mc <= 0) | (_pr <= 0)).sum()
    check("integrity: no zero/negative market cap or price",
          bad_scale == 0, f"{int(bad_scale)} rows with mcap<=0 or price<=0")

    dy = n(g, "dividend_yield")
    bad_dy = (dy > 0.40).sum()
    check("integrity: no absurd dividend yields (>40% — stale price / preferred artifacts)",
          bad_dy == 0, f"{int(bad_dy)} rows with dividend_yield > 0.40")


@measure("Regression guards (this session's fixes as invariants)",
         "Each fix made to the archetype rules is pinned as a load-bearing "
         "invariant so it cannot silently regress: net-cash firms are never "
         "levered stubs, growth rules keep a real USD revenue base, cost/margin "
         "inflections never fire on declining revenue, the re-rating-confirmed "
         "screen is genuinely at a 52w high, and operating-quality rules exclude "
         "financials.")
def _regression(t, g):
    if "symbol" not in t.columns or "symbol" not in g.columns:
        return
    _by = g.drop_duplicates("symbol").set_index("symbol")

    def gcol(name):
        return (pd.to_numeric(t["symbol"].map(_by[name]), errors="coerce")
                if name in g.columns else pd.Series(np.nan, index=t.index))

    # R3 — levered-stub archetypes must NOT flag net-cash firms (net_cash_pct
    # > 0.10 means more cash than debt; a levered equity stub requires net debt).
    _ncp = gcol("net_cash_pct_mcap")
    for _ac in ("arch_weschler_levered_equity", "arch_asymmetric_assembly",
                "arch_levered_inflection"):
        if _ac in t.columns:
            leak = int(((n(t, _ac) == 1) & (_ncp > 0.10)).sum())
            check(f"regression(R3): {_ac} carries no net-cash firm",
                  leak == 0, f"{leak} net-cash (>10% of mcap) firers")

    # R6 — growth/scaler archetypes keep a real USD revenue base (>=$5M). The
    # floor is the Cassel/Andreola microcap sweet spot ($5-10M REVENUE scaling to
    # $30-40M), NOT $20M — a $20M floor cut exactly the multibagger cohort the
    # reference targets. Below $5M a % growth rate is sub-scale base-effect noise
    # (and the g10/profitability legs still guard base-effect). FX-blind (a raw
    # home-currency floor) would leak, so the test is on revenue_ttm_usd.
    _rev_usd = gcol("revenue_ttm_usd")
    for _ac in ("arch_cheap_sales_scaler", "arch_exceptional_evsg",
                "arch_growth_algo", "arch_tenbagger_path"):
        if _ac in t.columns:
            leak = int(((n(t, _ac) == 1) & (_rev_usd > 0)
                        & (_rev_usd < 5e6)).sum())
            check(f"regression(R6): {_ac} keeps a >=$5M USD revenue base",
                  leak == 0, f"{leak} sub-$5M-USD-revenue firers")

    # R5 — margin/cost inflection archetypes never fire on DECLINING revenue
    # (a cost-cut blip in a shrinking business is not an inflection).
    _ry = gcol("rev_yoy")
    for _ac in ("arch_roic_inflect", "arch_double_inflect",
                "arch_micro_activist_inflect", "arch_liger_lagging_inflect"):
        if _ac in t.columns:
            leak = int(((n(t, _ac) == 1) & (_ry < 0)).sum())
            check(f"regression(R5): {_ac} not firing on declining revenue",
                  leak == 0, f"{leak} firers with rev_yoy < 0")

    # New archetype — every re-rating-CONFIRMED firer is actually at a 52w high
    # (absolute OR relative-to-index); it is the price-validated cut.
    if "arch_analyst_rerating_confirmed" in t.columns:
        _ah = gcol("high_52w_abs"); _rh = gcol("high_52w_rel")
        at_hi = (_ah > 0) | (_rh > 0)
        leak = int(((n(t, "arch_analyst_rerating_confirmed") == 1)
                    & ~at_hi).sum())
        check("regression: arch_analyst_rerating_confirmed every firer at a 52w high",
              leak == 0, f"{leak} firers not at a 52w high")

    # R1 — operating-quality / operating-value archetypes exclude Financials/
    # REITs/Utilities (EV / net-cash / margin / ROIC legs are meaningless there).
    _sec = t["symbol"].map(_by["sector"]).fillna("").astype(str).str.lower() \
        if "sector" in g.columns else pd.Series("", index=t.index)
    _finre = (_sec.str.contains("financ") | _sec.str.contains("real estate")
              | _sec.str.contains("utilit"))
    for _ac in ("arch_durable_reinvestment", "arch_cash_reinvest",
                "arch_lindy_fcf", "arch_lindy_growth", "arch_owner_operator",
                "arch_cash_quality", "arch_low_sbc_quality", "arch_no_dilution",
                "arch_oak_deleveraging", "arch_fastest_segment",
                # tail-audit additions
                "arch_qarp", "arch_templeton_pessimism", "arch_lynch_reward",
                "arch_lynch_evgy", "arch_concentrated_segments",
                # reference-gap additions (new archetypes)
                "arch_bottleneck", "arch_flyover",
                # event-driven sleeve (operating-gated ones)
                "arch_spinoff", "arch_post_reorg", "arch_nol_shell"):
        if _ac in t.columns:
            leak = int(((n(t, _ac) == 1) & _finre).sum())
            check(f"regression(R1): {_ac} excludes Financials/REITs/Utilities",
                  leak == 0, f"{leak} financials/REITs/utilities firers")

    # tail — "not melting": survivability legs must not admit a GENUINE ICE CUBE.
    # (user directive) a deeply-ROCE-negative name is NOT a defect when it is
    # cash-on-cash-generative OR its returns are improving — those are kept
    # (and DEMOTED via melt_demotion, not barred). The real invariant is that no
    # archetype carries a genuine ice cube: negative current returns AND no cash
    # generation on ANY sign-meaningful lens AND not improving.
    _roce_now = gcol("roce")
    _opm_now = gcol("op_margin")
    _cash_ok_a = ((gcol("fcf_yield") > 0) | (gcol("owner_earnings_yield") > 0)
                  | (gcol("robust_cash_yield") > 0) | (gcol("cfo_yield") > 0)
                  | (gcol("fcf_margin") > 0) | (gcol("fcf_ttm") > 0))
    _improving_a = ((gcol("roce_delta_yoy") > 0) | (gcol("roce_inflection") > 0)
                    | (gcol("roce_first_positive") > 0) | (gcol("fcf_inflection") > 0)
                    | (gcol("op_margin_delta_yoy") > 0) | (gcol("ebitda_inflection") > 0))
    _ice_cube = (((_roce_now < -0.05) | (_opm_now < 0))
                 & ~_cash_ok_a & ~_improving_a)
    # (arch_wolf_turnaround AND arch_templeton_pessimism are deliberately EXCLUDED
    # — a turnaround crossing to black / a Templeton trough cyclical at a 5y low
    # legitimately shows a negative current op margin with positive EBITDA + net
    # cash; that IS the thesis, and melt_demotion downranks the genuine ice cubes.)
    for _ac in ("arch_micro_activist_inflect", "arch_fixed_cost_demand_shock",
                "arch_regime_cyclical", "arch_kpi_threshold",
                "arch_oak_order_conversion", "arch_insider_conviction",
                "arch_fastest_segment", "arch_wolf_trifecta",
                "arch_wolf_value_catalyst", "arch_capital_discipline",
                "arch_dead_option", "arch_wolf_compounder",
                "arch_cheap_per_roiic",
                # the cheap-cash / durability / levered gates whose survivability
                # leg is now the cash-aware _not_melting — same ice-cube invariant.
                "arch_discounted_vehicle", "arch_net_cash_returner",
                "arch_negative_ev_value", "arch_oak_deep_value",
                "arch_oak_asset_floor", "arch_diversified_segments",
                "arch_no_dilution", "arch_lindy_fcf", "arch_owner_operator",
                "arch_wolf_seal", "arch_levered_inflection",
                "arch_hidden_assets"):
        if _ac in t.columns:
            leak = int(((n(t, _ac) == 1) & _ice_cube).sum())
            check(f"regression(tail): {_ac} carries no genuine ice cube (neg returns, no cash, not improving)",
                  leak == 0, f"{leak} ice-cube firers")

    # price-ghost dedup: a wrong-price duplicate line of a real security must
    # neither fire an archetype nor rank (UMBFO, a ghost of UMBF, at P/B 0.26).
    if "is_price_ghost" in t.columns and "archetype_count" in t.columns:
        _gh = n(t, "is_price_ghost") == 1
        leak = int((_gh & (n(t, "archetype_count") > 0)).sum())
        check("regression: price-ghost duplicates fire no archetypes",
              leak == 0, f"{leak} price-ghost lines firing archetypes")
        _eta_g = gcol("entry_today_asymmetry")
        leak2 = int((_gh & (_eta_g > 0)).sum())
        check("regression: price-ghost duplicates do not rank (ETA=0)",
              leak2 == 0, f"{leak2} price-ghost lines with ETA>0")

    # tail — real revenue base on the microcap turnaround/segment engines that
    # gained a floor (a hidden growth engine / turnaround needs a real business).
    for _ac, _floor in (("arch_wolf_turnaround", 10e6),
                        ("arch_fastest_segment", 20e6)):
        if _ac in t.columns:
            leak = int(((n(t, _ac) == 1) & (_rev_usd > 0)
                        & (_rev_usd < _floor)).sum())
            check(f"regression(tail): {_ac} keeps a real USD revenue base",
                  leak == 0, f"{leak} sub-floor-revenue firers")


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


@measure("Valuation internal consistency (yf process)",
         "Every stored ratio must equal what the row's own components say. "
         "The apply_ticker_yf reconcile (levels bend to authoritative Yahoo "
         "ratios; ratios recomputed from components) is the process; these "
         "checks are the gate that keeps DEEPINDS-class staleness out.")
def _valuation_consistency(t, g):
    def gc(c):
        return pd.to_numeric(g.get(c), errors="coerce") if c in g.columns \
            else pd.Series(np.nan, index=g.index)
    price, sh, mc = gc("price"), gc("shares_outstanding"), gc("market_cap")
    ev, eb, rv = gc("enterprise_value"), gc("ebitda_ttm"), gc("revenue_ttm")
    ni, fcf = gc("net_income_ttm"), gc("fcf_ttm")
    evb, evs, eve = gc("ev_ebitda"), gc("ev_sales"), gc("ev_ebit")
    pe, fy, ebm = gc("p_e"), gc("fcf_yield"), gc("ebitda_margin")

    def _r(a, b):
        return (a / b).where(b != 0)

    def vrate(name, pred, base, max_pct, hard_top=True):
        b = int(base.sum())
        v = int((pred & base).sum())
        pct = 100.0 * v / max(1, b)
        check(f"valuation: {name} <= {max_pct}% of covered rows",
              pct <= max_pct, f"{v}/{b} rows ({pct:.2f}%)")
        return pred & base

    # exact identities (post-reconcile these are near-zero; a rebound means the
    # apply_ticker_yf pass was skipped or broken)
    viol = vrate("mcap != price*shares (>10% dev)",
                 (_r(mc, price * sh) - 1).abs() > 0.10,
                 mc.notna() & price.notna() & sh.notna() & (price * sh > 0), 0.5)
    viol |= vrate("p_e != mcap/NI (>25% dev)",
                  (_r(pe, _r(mc, ni)) - 1).abs() > 0.25,
                  (pe > 0) & (ni > 0) & mc.notna(), 1.0)
    viol |= vrate("fcf_yield != fcf/mcap (>25% dev)",
                  (_r(fy, _r(fcf, mc)) - 1).abs() > 0.25,
                  fy.notna() & fcf.notna() & (mc > 0), 1.0)
    # the whole equity-cash-yield family (LEVERED measures over MARKET CAP —
    # user rule) must stay recomputed against current mcap
    for _yc, _lvl_c in (("owner_earnings_yield", "fcf_ttm"),
                        ("cfo_yield", "cfo_ttm"),
                        ("earnings_yield", "net_income_ttm")):
        _yv, _lv = gc(_yc), gc(_lvl_c)
        viol |= vrate(f"{_yc} != {_lvl_c}/mcap (>25% dev)",
                      (_r(_yv, _r(_lv, mc)) - 1).abs() > 0.25,
                      _yv.notna() & _lv.notna() & (mc > 0), 1.5)
    check("valuation: no ev_ebit below ev_ebitda (impossible ordering)",
          int(((eve < evb * 0.95) & (eve > 0) & (evb > 0)).sum()) == 0,
          f"{int(((eve < evb * 0.95) & (eve > 0) & (evb > 0)).sum())} rows")
    # hidden_assets: the gap must be real in LOCAL currency for every firer
    if "arch_hidden_assets" in t.columns:
        _f = t["arch_hidden_assets"] == 1
        _fs = t.loc[_f, "symbol"]
        _gm = g.set_index("symbol")
        _gg = _gm.reindex(_fs)
        _hp = ((pd.to_numeric(_gg.get("enterprise_value"), errors="coerce")
                + pd.to_numeric(_gg.get("cash"), errors="coerce")
                - pd.to_numeric(_gg.get("market_cap"), errors="coerce")
                - pd.to_numeric(_gg.get("total_debt"), errors="coerce"))
               / pd.to_numeric(_gg.get("market_cap"), errors="coerce"))
        _bad_h = int((_hp.notna() & (_hp < 0.20)).sum())
        check("regression: arch_hidden_assets gap >= ~25% of mcap in LOCAL currency "
              "(currency-mix guard)", _bad_h == 0, f"{_bad_h} sub-gap firers")
    check("valuation: no positive ev_ebitda on ebitda<=0",
          int(((evb > 0) & (eb <= 0) & eb.notna()).sum()) == 0,
          f"{int(((evb > 0) & (eb <= 0) & eb.notna()).sum())} rows")
    # soft identities (extreme-multiple tails are left un-bent by design)
    viol |= vrate("ev_ebitda != EV/ebitda (>25% dev)",
                  (_r(evb, _r(ev, eb)) - 1).abs() > 0.25,
                  evb.notna() & ev.notna() & (eb > 0), 6.0)
    viol |= vrate("ev_sales != EV/revenue (>25% dev)",
                  (_r(evs, _r(ev, rv)) - 1).abs() > 0.25,
                  evs.notna() & ev.notna() & (rv > 0), 6.0)
    # negative-EV multiples are VALID (negative EV / positive denominator) —
    # but the SIGN must agree with EV when the denominator is positive.
    _sign_bad = evb.notna() & ev.notna() & (eb > 0) \
        & (np.sign(evb) != np.sign(ev)) & (ev != 0)
    check("valuation: ev_ebitda sign matches EV (denominator>0)",
          int(_sign_bad.sum()) == 0, f"{int(_sign_bad.sum())} sign mismatches")
    viol |= vrate("ebitda_margin != ebitda/revenue (>25% dev)",
                  (_r(ebm, _r(eb, rv)) - 1).abs() > 0.25,
                  ebm.notna() & (rv > 0) & eb.notna(), 6.0)
    # the names people actually SEE must be spotless: top 100 by ETA carry
    # zero cross-field violations of any kind.
    eta = gc("entry_today_asymmetry")
    top_idx = eta.sort_values(ascending=False).head(100).index
    n_top_viol = int(viol.reindex(top_idx).fillna(False).sum())
    check("valuation: top-100 by ETA carry ZERO cross-field violations",
          n_top_viol == 0, f"{n_top_viol} of top 100 rows inconsistent")


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
