"""Operating-inflection + deleveraging extractor (SEC XBRL).

The PSIX recipe (Power Solutions International, May 2024) turns on two
engines that a balance-sheet snapshot cannot see:

  1. OPERATING INFLECTION -- gross profit rising while revenue falls
     ("a bad headline concealing a better economic unit"): higher-value
     revenue replacing low-quality revenue, lifting gross margin.
  2. DELEVERAGING -- operating cash reducing debt, cutting interest
     expense, transferring enterprise value from lenders to equity.

Both are computable from structured XBRL (data.sec.gov/api/xbrl), which
is JSON -- far lighter than HTML 10-Q parsing. This runs on a SHORTLIST
(names that already pass the cheap assembly gates), so the expensive
pull stays small and rate-limit-friendly.

Output: financials_inflection.json {ticker: {revenue_yoy, gp_yoy,
gross_margin_delta_pp, interest_exp_yoy, capex_to_rev, opinc,
opinc_to_ppe, ...}}.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "financials_inflection.json"

# Concept fallbacks: SEC filers tag the same line differently.
REV_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet"]
GP_TAGS = ["GrossProfit"]
COGS_TAGS = ["CostOfRevenue", "CostOfGoodsAndServicesSold",
             "CostOfGoodsSold"]
INT_TAGS = ["InterestExpense", "InterestExpenseDebt",
            "InterestAndDebtExpense"]
CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"]
PPE_TAGS = ["PropertyPlantAndEquipmentNet"]
OPINC_TAGS = ["OperatingIncomeLoss"]
DEBT_TAGS = ["LongTermDebtNoncurrent", "LongTermDebt",
             "DebtLongtermAndShorttermCombinedAmount"]


def _get_json(url: str):
    from edgar import _get
    try:
        return _get(url).json()
    except Exception:
        return None


def _concept(cik: str, tag: str):
    url = (f"https://data.sec.gov/api/xbrl/companyconcept/"
           f"CIK{int(cik):010d}/us-gaap/{tag}.json")
    return _get_json(url)


def _quarterly_points(data: dict) -> list[dict]:
    """Flow points that span roughly one quarter (~80-100 days)."""
    if not data:
        return []
    units = data.get("units") or {}
    key = next((k for k in units if k.startswith("USD")), None)
    if not key:
        return []
    out = []
    for v in units[key]:
        s, e = v.get("start"), v.get("end")
        if not (s and e):
            continue
        try:
            from datetime import date
            d0 = date.fromisoformat(s)
            d1 = date.fromisoformat(e)
        except Exception:
            continue
        days = (d1 - d0).days
        if 80 <= days <= 100:            # single fiscal quarter
            out.append({"end": e, "val": v.get("val"), "days": days})
    out.sort(key=lambda x: x["end"])
    return out


def _instant_points(data: dict) -> list[dict]:
    if not data:
        return []
    units = data.get("units") or {}
    key = next((k for k in units if k.startswith("USD")), None)
    if not key:
        return []
    out = [{"end": v.get("end"), "val": v.get("val")}
           for v in units[key] if v.get("end") and v.get("val") is not None]
    out.sort(key=lambda x: x["end"])
    return out


def _first_series(cik, tags, kind="flow"):
    """Return the FRESHEST non-empty series across the tag fallbacks.

    Returning the first tag that had any points let a deprecated concept
    whose series ends years ago (e.g. SND's revenue tag ending 2021)
    masquerade as current. Pick the series whose latest point is the
    most recent instead."""
    best_pts, best_tag, best_end = [], None, ""
    for t in tags:
        d = _concept(cik, t)
        pts = _quarterly_points(d) if kind == "flow" else _instant_points(d)
        time.sleep(0.05)
        if pts and pts[-1]["end"] > best_end:
            best_pts, best_tag, best_end = pts, t, pts[-1]["end"]
    return best_pts, best_tag


def _latest_and_yearago(pts: list[dict], as_of: str | None = None):
    """Return (latest_val, yearago_val) matching the same quarter end.
    With as_of set, 'latest' is the last quarter ending on/before as_of
    -- a point-in-time view for validating the engine at a past date."""
    if not pts:
        return None, None
    if as_of:
        pts = [p for p in pts if p["end"] <= as_of]
        if not pts:
            return None, None
    latest = pts[-1]
    ly = latest["end"][:4]
    try:
        prev_year = str(int(ly) - 1)
    except Exception:
        return latest["val"], None
    mmdd = latest["end"][4:]
    ya = next((p for p in pts if p["end"] == prev_year + mmdd), None)
    if ya is None:
        # tolerate a few days of fiscal drift
        for p in pts:
            if p["end"].startswith(prev_year) and p["end"][4:7] == mmdd[:3]:
                ya = p
                break
    return latest["val"], (ya["val"] if ya else None)


def analyze(cik: str, as_of: str | None = None) -> dict | None:
    rev, _ = _first_series(cik, REV_TAGS)
    gp, _ = _first_series(cik, GP_TAGS)
    if not gp:  # derive from revenue - COGS
        cogs, _ = _first_series(cik, COGS_TAGS)
        if rev and cogs:
            cmap = {c["end"]: c["val"] for c in cogs}
            gp = [{"end": r["end"], "val": r["val"] - cmap[r["end"]]}
                  for r in rev if r["end"] in cmap]
    if as_of:
        rev = [p for p in rev if p["end"] <= as_of]
        gp = [p for p in gp if p["end"] <= as_of]
    if not rev or not gp:
        return None

    # Reject stale filers: a latest quarter older than ~18 months is not
    # a live inflection signal (deregistered, gone dark, or a concept
    # that stopped being tagged). Guards against period-mismatch
    # artifacts like SND's 2021 series. Skipped for as_of backtests,
    # which deliberately evaluate a past quarter.
    from datetime import date
    if not as_of:
        try:
            latest_end = max(rev[-1]["end"], gp[-1]["end"])
            if (date.today() - date.fromisoformat(latest_end)).days > 550:
                return None
        except Exception:
            return None

    rev_l, rev_y = _latest_and_yearago(rev, as_of)
    gp_l, gp_y = _latest_and_yearago(gp, as_of)
    out: dict = {"period_end": rev[-1]["end"], "as_of": as_of}

    if rev_l and rev_y:
        out["revenue_yoy"] = round((rev_l - rev_y) / abs(rev_y), 4)
    if gp_l and gp_y:
        out["gp_yoy"] = round((gp_l - gp_y) / abs(gp_y), 4)
    # gross margin delta (percentage points)
    gm_map = {g["end"]: g["val"] for g in gp}
    rv_map = {r["end"]: r["val"] for r in rev}
    common = sorted(set(gm_map) & set(rv_map))
    if len(common) >= 5:
        latest_e = common[-1]
        ya_e = next((e for e in common if e[:4] == str(int(latest_e[:4]) - 1)
                     and e[4:7] == latest_e[4:7]), None)
        if ya_e and rv_map[latest_e] and rv_map[ya_e]:
            gm_now = gm_map[latest_e] / rv_map[latest_e]
            gm_then = gm_map[ya_e] / rv_map[ya_e]
            out["gross_margin_delta_pp"] = round((gm_now - gm_then) * 100, 2)

    def _cut(pts):
        return [p for p in pts if p["end"] <= as_of] if as_of else pts

    intr, _ = _first_series(cik, INT_TAGS)
    intr = _cut(intr)
    if intr:
        il, iy = _latest_and_yearago(intr, as_of)
        if il is not None and iy:
            out["interest_exp_yoy"] = round((il - iy) / abs(iy), 4)

    capex = _cut(_first_series(cik, CAPEX_TAGS)[0])
    if capex and rev_l:
        out["capex_to_rev"] = round(abs(capex[-1]["val"]) / abs(rev_l), 4)
    opinc = _cut(_first_series(cik, OPINC_TAGS)[0])
    ppe = _cut(_first_series(cik, PPE_TAGS, kind="instant")[0])
    if opinc:
        out["opinc"] = opinc[-1]["val"]
        if ppe and ppe[-1]["val"]:
            out["opinc_to_ppe"] = round(opinc[-1]["val"] / ppe[-1]["val"], 3)

    debt = _cut(_first_series(cik, DEBT_TAGS, kind="instant")[0])
    if debt and len(debt) >= 2:
        out["debt_latest"] = debt[-1]["val"]
        out["debt_delta_qoq"] = debt[-1]["val"] - debt[-2]["val"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", help="comma list; else reads shortlist file")
    ap.add_argument("--shortlist", default="asymmetry_shortlist.json")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--sleep", type=float, default=0.12)
    args = ap.parse_args()

    from recent import _cik_to_ticker_map
    t2c = {v: k for k, v in _cik_to_ticker_map().items()}

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif Path(args.shortlist).exists():
        tickers = json.loads(Path(args.shortlist).read_text())
    else:
        print(f"no --tickers and no {args.shortlist}; nothing to do")
        return 1
    tickers = tickers[:args.limit]

    out = {}
    if OUT.exists():
        try:
            out = json.loads(OUT.read_text())
        except Exception:
            out = {}
    for i, tk in enumerate(tickers, 1):
        cik = t2c.get(tk)
        if not cik:
            continue
        try:
            rec = analyze(cik)
        except Exception as e:
            rec = None
            print(f"  {tk} ERR {repr(e)[:60]}", file=sys.stderr)
        if rec:
            out[tk] = rec
        if i % 20 == 0:
            OUT.write_text(json.dumps(out, indent=2))
            print(f"  [{i}/{len(tickers)}] {len(out)} with financials",
                  file=sys.stderr, flush=True)
        time.sleep(args.sleep)

    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT} ({len(out)} tickers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
