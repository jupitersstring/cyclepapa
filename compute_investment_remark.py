"""Investment-remark signal (the LanzaTech / JV-stake-remarked-higher pattern).

When a company remeasures a minority JV / equity stake to fair value — e.g. on
the investee's public listing, a step-up to control, or a revaluation — the
investment's CARRYING VALUE steps up and a large NON-OPERATING gain flows through
income, crystallising hidden value on the balance sheet (LanzaTech Q2-2026: its
8.3% Shougang LanzaTech stake, held as an equity security without readily
determinable fair value, went $15.0m -> $223.1m = +$208.1m on SGLT's listing).

Reads the EDGAR companyfacts cache (edgar_cache/*.json.gz — already local, no
network) and computes, per symbol:
  inv_carry_now      latest investment carrying value (broadest available line)
  inv_carry_prior    value ~1yr earlier (the pre-remark base)
  inv_remark_jump    now - prior (absolute step-up)
  inv_remark_pct     jump / prior (relative step-up)
  nonop_gain_ttm     latest non-operating income/expense (confirms a remark gain)

Output: investment_remark.csv (symbol-keyed).
"""
import glob
import gzip
import json
import os
import sys
from datetime import datetime

import pandas as pd

# carrying-value lines, broadest first (the total investments line captures the
# remark regardless of how the specific stake is classified)
INV_CONCEPTS = [
    "Investments",
    "LongTermInvestments",
    "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
    "EquitySecuritiesFvNiAndWithoutReadilyDeterminableFairValue",
    "EquityMethodInvestments",
    "MarketableSecuritiesNoncurrent",
]
NONOP_CONCEPTS = ["NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense"]
# forensic best-practice additions (full gamut):
EM_CARRY_CONCEPTS = ["EquityMethodInvestments"]                       # carrying value of associates/JVs
EM_FV_CONCEPTS = ["EquityMethodInvestmentsFairValueDisclosure"]       # DISCLOSED fair value of the stake (the #1 tell)
EM_INCOME_CONCEPTS = ["IncomeLossFromEquityMethodInvestments"]        # look-through earnings from associates
UNREAL_GAIN_CONCEPTS = ["UnrealizedGainLossOnInvestments",           # the remark gain (unrealized)
                        "GainLossOnInvestments",
                        "EquitySecuritiesFvNiUnrealizedGainLoss"]


def _series(gaap, concepts, unit="USD"):
    """{end_date: val} for the first concept that has USD observations."""
    for c in concepts:
        obs = (gaap.get(c, {}) or {}).get("units", {}).get(unit, [])
        if obs:
            out = {}
            for o in obs:
                e, v = o.get("end"), o.get("val")
                if e and v is not None:
                    out[e] = v          # newest wins per end-date
            if out:
                return out, c
    return {}, None


def _parse(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except Exception:
        return None


def main():
    # ALL tickers per CIK (a CIK often maps to common stock + warrants/units;
    # a last-wins dict emitted under the warrant, e.g. LNZAW, hiding LNZA).
    from collections import defaultdict
    tickers_by_cik = defaultdict(list)
    if os.path.exists("edgar_universe_facts.csv"):
        ef = pd.read_csv("edgar_universe_facts.csv", low_memory=False)
        if "cik" in ef.columns:
            for _, r in ef.iterrows():
                try:
                    tickers_by_cik[int(r["cik"])].append(r["symbol"])
                except Exception:
                    pass

    rows = []
    files = glob.glob("edgar_cache/*.json.gz")
    for i, f in enumerate(files):
        if i % 1000 == 0:
            print(f"  {i}/{len(files)}", file=sys.stderr)
        try:
            cik = int(os.path.basename(f).replace("CIK", "").replace(".json.gz", ""))
        except Exception:
            continue
        syms = tickers_by_cik.get(cik)
        if not syms:
            continue
        try:
            d = json.loads(gzip.open(f, "rt").read())
        except Exception:
            continue
        gaap = (d.get("facts", {}) or {}).get("us-gaap", {}) or {}
        carry, concept = _series(gaap, INV_CONCEPTS)
        if not carry:
            continue
        ends = sorted(carry, key=lambda e: e)
        now_e = ends[-1]
        now_d = _parse(now_e)
        if now_d is None:
            continue
        now_v = carry[now_e]
        # prior base: the immediately-PRECEDING period (a remark is a discrete
        # recent event — LanzaTech's SGLT step-up was QoQ, Q1->Q2 2026, and its
        # investment line is only a few quarters old). Take the latest
        # observation >= 45 days before `now` (prior quarter, or prior year for
        # annual-only filers), and also record the ~1yr-ago value when present.
        prior = None
        prior_1y = None
        for e in ends[:-1]:
            pd_ = _parse(e)
            if pd_ is None:
                continue
            gap = (now_d - pd_).days
            if gap >= 45:
                prior = (e, carry[e], gap)          # keep the LATEST such (closest prior period)
            if 270 <= gap <= 540:
                prior_1y = (e, carry[e], gap)
        if prior is None:
            continue
        prior_e, prior_v, _ = prior
        jump = now_v - prior_v
        # non-operating income (latest period value) — confirms a gain
        nonop, _ = _series(gaap, NONOP_CONCEPTS)
        nonop_v = nonop.get(now_e) or (nonop[sorted(nonop)[-1]] if nonop else None)
        # forensic full gamut: equity-method carrying value, DISCLOSED fair
        # value (idea #1), look-through earnings, and the unrealized remark gain.
        def _latest(concepts):
            s, _c = _series(gaap, concepts)
            if not s:
                return None
            return s[sorted(s, key=lambda e: e)[-1]]
        em_carry = _latest(EM_CARRY_CONCEPTS)
        em_fv = _latest(EM_FV_CONCEPTS)
        em_income = _latest(EM_INCOME_CONCEPTS)
        unreal_gain = _latest(UNREAL_GAIN_CONCEPTS)
        _rowbase = {
            "inv_carry_now": now_v, "inv_carry_prior": prior_v,
            "inv_carry_now_end": now_e, "inv_carry_concept": concept,
            "inv_remark_jump": jump,
            "inv_remark_pct": (jump / prior_v) if prior_v not in (0, None) else None,
            "nonop_gain_ttm": nonop_v,
            # equity-method / JV forensics
            "em_carry": em_carry, "em_fair_value": em_fv,
            "em_fv_gap": (em_fv - em_carry) if (em_fv is not None and em_carry is not None) else None,
            "em_income": em_income,
            "unrealized_inv_gain": unreal_gain,
        }
        for sym in syms:
            rows.append({"symbol": sym, **_rowbase})

    out = pd.DataFrame(rows).drop_duplicates("symbol")
    out.to_csv("investment_remark.csv", index=False)
    big = out[(out["inv_remark_pct"].fillna(0) >= 0.5) & (out["inv_remark_jump"].fillna(0) > 0)]
    print(f"symbols {len(out)} | with a >=50% positive carry step-up: {len(big)}", file=sys.stderr)


if __name__ == "__main__":
    main()
