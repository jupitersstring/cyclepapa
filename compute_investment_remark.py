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
    ticker_by_cik = {}
    if os.path.exists("edgar_universe_facts.csv"):
        ef = pd.read_csv("edgar_universe_facts.csv", low_memory=False)
        if "cik" in ef.columns:
            for _, r in ef.iterrows():
                try:
                    ticker_by_cik[int(r["cik"])] = r["symbol"]
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
        sym = ticker_by_cik.get(cik)
        if not sym:
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
        # prior base: the observation closest to ~1 year before `now` (270-540d)
        prior = None
        for e in ends[:-1]:
            pd_ = _parse(e)
            if pd_ is None:
                continue
            gap = (now_d - pd_).days
            if 270 <= gap <= 540:
                prior = (e, carry[e], gap)
        if prior is None:
            continue
        prior_e, prior_v, _ = prior
        jump = now_v - prior_v
        # non-operating income (latest annual/period value) — confirms a gain
        nonop, _ = _series(gaap, NONOP_CONCEPTS)
        nonop_v = nonop.get(now_e)
        if nonop_v is None and nonop:
            nonop_v = nonop[sorted(nonop)[-1]]
        rows.append({
            "symbol": sym,
            "inv_carry_now": now_v, "inv_carry_prior": prior_v,
            "inv_carry_now_end": now_e, "inv_carry_concept": concept,
            "inv_remark_jump": jump,
            "inv_remark_pct": (jump / prior_v) if prior_v not in (0, None) else None,
            "nonop_gain_ttm": nonop_v,
        })

    out = pd.DataFrame(rows).drop_duplicates("symbol")
    out.to_csv("investment_remark.csv", index=False)
    big = out[(out["inv_remark_pct"].fillna(0) >= 0.5) & (out["inv_remark_jump"].fillna(0) > 0)]
    print(f"symbols {len(out)} | with a >=50% positive carry step-up: {len(big)}", file=sys.stderr)


if __name__ == "__main__":
    main()
