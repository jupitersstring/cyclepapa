"""Net Net Hunter Core-7 NCAV scorecard.

The signal: Benjamin Graham's net-net working capital filter
generalized by Evan Bleker (Net Net Hunter). A name passes if it
hits the seven conjunction gates:

  1. price / NCAV  <  0.66  (price below 2/3 of net current asset value)
  2. current_ratio > 1.5
  3. burn rate     >  -15% annual (op_cf / NCAV not too negative)
  4. Piotroski-lite F-score >= 5 (we use 6 components we can pull)
  5. insider ownership > 0
  6. non-China / non-HK domiciled
  7. positive net cash position

NCAV = Total Current Assets - Total Liabilities

For each yfinance-covered ticker we fetch a balance sheet from yfinance
(one-time) and compute NCAV. To keep API load bounded we PRE-FILTER
to names with P/B < 1.5 (Graham boundary -- net-nets are below P/B 1
by definition; the relaxed filter catches edge cases).

Output: net_net_ncav.json
  {ticker: {ncav_per_share, price_to_ncav, current_ratio,
            insider_pct, piotroski_lite, country, score, reasons}}

Honest limitation: yfinance balance sheets are batched annual, not
quarterly. NCAV is therefore a Q-stale snapshot. Good for screening,
not precision.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "net_net_ncav.json"


def _num(v):
    if v is None: return None
    try: return float(v)
    except Exception: return None


def piotroski_lite(y: dict) -> int:
    """Six-component proxy for the 9-point Piotroski F-score using
    yfinance fields available without quarterly history.
      1. ROA > 0
      2. ROE > 0
      3. FCF > 0
      4. profit_margin > 0
      5. current_ratio > 1.0
      6. debt_to_equity < 2.0 (less than 200%)
    Score: 0-6 (we scale to a 5-threshold gate)."""
    score = 0
    roa = _num(y.get("roa"))
    roe = _num(y.get("roe"))
    fcf = _num(y.get("fcf"))
    pm = _num(y.get("profit_margin"))
    cr = _num(y.get("current_ratio"))
    de = _num(y.get("debt_to_equity"))
    if roa is not None and roa > 0: score += 1
    if roe is not None and roe > 0: score += 1
    if fcf is not None and fcf > 0: score += 1
    if pm is not None and pm > 0: score += 1
    if cr is not None and cr > 1.0: score += 1
    if de is not None and de < 200: score += 1
    return score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10000)
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--max-pb", type=float, default=1.5,
                    help="pre-filter on price/book before fetching balance sheet")
    args = ap.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr)
        return 1

    yf_data = json.loads((ROOT / "yfinance_quick.json").read_text())
    print(f"yfinance_quick: {len(yf_data)}", file=sys.stderr)

    # Pre-filter
    cands = []
    for tk, y in yf_data.items():
        if not isinstance(y, dict): continue
        pb = _num(y.get("p_b"))
        cr = _num(y.get("current_ratio"))
        if pb is None or pb <= 0 or pb > args.max_pb: continue
        if cr is None or cr < 1.0: continue
        cands.append(tk)
    print(f"pre-filtered candidates (P/B<{args.max_pb}, CR>1): {len(cands)}",
          file=sys.stderr)

    # Existing partial output (resumable)
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text())
        except Exception:
            existing = {}
    else:
        existing = {}

    out = dict(existing)
    n_fetched = 0
    n_passed = 0
    for i, tk in enumerate(cands[:args.limit], 1):
        if tk in out:
            continue
        try:
            t = yf.Ticker(tk)
            bs = t.balance_sheet  # annual
            info = t.info or {}
        except Exception:
            time.sleep(args.sleep)
            continue
        if bs is None or len(bs) == 0:
            time.sleep(args.sleep)
            continue

        # Pull most recent column
        latest_col = bs.columns[0]
        cur_assets = None
        tot_liab = None
        for label, val in bs[latest_col].items():
            label_lc = (label or "").lower()
            if cur_assets is None and "current assets" in label_lc and "total" in label_lc:
                cur_assets = _num(val)
            if cur_assets is None and label_lc == "current assets":
                cur_assets = _num(val)
            if tot_liab is None and "total liabilities" in label_lc:
                tot_liab = _num(val)

        if cur_assets is None or tot_liab is None:
            time.sleep(args.sleep)
            continue

        ncav = cur_assets - tot_liab
        if ncav <= 0:
            time.sleep(args.sleep)
            continue

        shares_out = _num(info.get("sharesOutstanding") or info.get("impliedSharesOutstanding"))
        price = _num(yf_data[tk].get("price")) or _num(info.get("currentPrice"))
        if not shares_out or not price:
            time.sleep(args.sleep)
            continue

        ncav_per_share = ncav / shares_out
        price_to_ncav = price / ncav_per_share if ncav_per_share > 0 else None

        cr = _num(yf_data[tk].get("current_ratio"))
        insider_pct = _num(yf_data[tk].get("insider_pct")) or _num(info.get("heldPercentInsiders"))
        op_cf = _num(yf_data[tk].get("op_cf")) or _num(info.get("operatingCashflow"))
        burn_rate = (op_cf / ncav) if (op_cf and ncav) else None
        country = info.get("country") or ""
        f_lite = piotroski_lite(yf_data[tk])
        n_fetched += 1

        # Core-7 gate
        gates = []
        gates.append(("price/NCAV<0.66", price_to_ncav is not None and price_to_ncav < 0.66))
        gates.append(("CR>1.5", cr is not None and cr > 1.5))
        gates.append(("burn>-15%", burn_rate is None or burn_rate > -0.15))
        gates.append(("F-lite>=5", f_lite >= 5))
        gates.append(("insider>0", insider_pct is not None and insider_pct > 0))
        gates.append(("non-China",
                      "china" not in country.lower()
                      and "hong kong" not in country.lower()))
        gates.append(("NCAV>0", ncav > 0))

        n_passed_gates = sum(1 for _, ok in gates if ok)

        score = 0.0
        reasons = []
        if price_to_ncav is not None and price_to_ncav < 0.66:
            score += 25
            reasons.append(f"P/NCAV {price_to_ncav:.2f}")
        elif price_to_ncav is not None and price_to_ncav < 1.0:
            score += 12
            reasons.append(f"P/NCAV {price_to_ncav:.2f}")
        if n_passed_gates == 7:
            score += 25
            reasons.append("FULL Core-7 PASS")
        elif n_passed_gates >= 5:
            score += 12
            reasons.append(f"{n_passed_gates}/7 gates")

        out[tk] = {
            "ncav_per_share": round(ncav_per_share, 3),
            "price": price,
            "price_to_ncav": round(price_to_ncav, 3) if price_to_ncav else None,
            "current_ratio": cr,
            "insider_pct": insider_pct,
            "burn_rate": round(burn_rate, 3) if burn_rate is not None else None,
            "piotroski_lite": f_lite,
            "country": country,
            "n_gates_passed": n_passed_gates,
            "gates": {name: bool(ok) for name, ok in gates},
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

        if n_passed_gates >= 5:
            n_passed += 1

        time.sleep(args.sleep)
        if n_fetched % 25 == 0:
            tmp = OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2, default=str))
            tmp.replace(OUT)
            print(f"  [{i}/{len(cands)}] fetched={n_fetched} passed5+={n_passed}",
                  file=sys.stderr, flush=True)

    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, default=str))
    tmp.replace(OUT)
    print(f"\nwrote {OUT} ({len(out)} rows; {n_passed} passed >=5 gates)")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 net-net NCAV ===")
    print(f"  {'TKR':<7}{'SCR':<5}{'P/NCAV':<8}{'CR':<5}{'FL':<3}{'GT':<3}{'COUNTRY':<14}")
    for tk, v in ranked[:20]:
        p = v.get("price_to_ncav") or 0
        cr = v.get("current_ratio") or 0
        fl = v.get("piotroski_lite") or 0
        gt = v.get("n_gates_passed") or 0
        print(f"  {tk:<7}{v['score']:<5.0f}{p:<8.2f}{cr:<5.1f}{fl:<3}{gt:<3}"
              f"{(v.get('country') or '')[:14]:<14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
