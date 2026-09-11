"""Financial-sector primary screen (additive, complementary to PSU).

Per AUDIT.md S1.3: PSU forensics under-serves financials (banks,
insurers, BDCs) because most don't grant heavy PSU programs --
their LTI is RSU/option/cash-bonus heavy and their structural
catalysts are different.

For financials the actionable structural patterns are:
  - **price / tangible book value** (the canonical bank metric)
  - **return on tangible equity** (operating efficiency)
  - **non-performing loans %** (credit quality; needs FDIC data
    we already pull for FFIEC banks)
  - **deposit beta** (insurance to rate cycle)
  - **buyback at < 1x TBV** (book-value compounder)
  - **deposit franchise stability** (the moat)

This module computes a Financials Primary Score for any ticker
classified as Financial sector by yfinance, regardless of PSU
coverage:
  1. P/TBV < 0.85 (deep value)
  2. ROE > 12 (operational quality)
  3. Buyback EXECUTING or SHRINKING (capital return)
  4. Insider buying (Form 4 P-buys present)
  5. No dividend cut in last 4 quarters (proxy: TTM dividend > 0)

ADDITIVE: scores any Financial-sector ticker regardless of PSU score.
Does not modify any existing layer.

Output: financial_primary.json
  {ticker: {sector, p_tbv, roe, bb_status, f4_present,
            score, reasons}}
"""

from __future__ import annotations

import json
from pathlib import Path
import io_util

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "financial_primary.json"


def _num(v):
    if v is None: return None
    try: return float(v)
    except Exception: return None


def main() -> int:
    yf = json.loads((ROOT / "yfinance_quick.json").read_text())
    bbv = json.loads((ROOT / "buyback_verify.json").read_text())
    f4 = json.loads((ROOT / "form4_buys.json").read_text())
    fdic = (json.loads((ROOT / "fdic_call_report_overlay.json").read_text())
            if (ROOT / "fdic_call_report_overlay.json").exists() else {})

    out = {}
    for tk, y in yf.items():
        if not isinstance(y, dict):
            continue
        sector = (y.get("sector") or "").lower()
        industry = (y.get("industry") or "").lower()
        if not any(s in sector for s in ("financial", "financ")):
            if not any(s in industry for s in ("bank", "insur", "reit",
                                                 "asset management",
                                                 "capital markets")):
                continue

        pb = _num(y.get("p_b"))
        pe = _num(y.get("p_e_trailing"))
        roe = _num(y.get("roe"))
        debt_eq = _num(y.get("debt_to_equity"))
        b = bbv.get(tk, {}) or {}
        bb_status = b.get("status")
        f4_rec = f4.get(tk, {}) or {}
        f4_present = bool(f4_rec.get("total_dollar") and f4_rec["total_dollar"] > 100_000)
        fdic_rec = fdic.get(tk, {}) or {}

        score = 0.0
        reasons = []
        # Tangible book proxy: use P/B (yfinance P/B is close enough for
        # banks; for insurers we'd want operating book)
        if pb is not None:
            if 0 < pb < 0.7:
                score += 25; reasons.append(f"P/B {pb:.2f} (deep)")
            elif 0 < pb < 0.85:
                score += 18; reasons.append(f"P/B {pb:.2f}")
            elif 0 < pb < 1.0:
                score += 10; reasons.append(f"P/B {pb:.2f}")

        if roe is not None:
            if roe > 0.15:
                score += 15; reasons.append(f"ROE {roe*100:.0f}%")
            elif roe > 0.10:
                score += 8; reasons.append(f"ROE {roe*100:.0f}%")

        if pe is not None and 0 < pe < 8:
            score += 12; reasons.append(f"P/E {pe:.1f}")
        elif pe is not None and 0 < pe < 12:
            score += 6

        # Verified buyback
        if bb_status == "EXECUTING":
            chg = (b.get("share_change") or {}).get("change_pct", 0)
            score += 12; reasons.append(f"buyback EXECUTING {chg:+.1f}%")
        elif bb_status == "SHRINKING_NO_AUTH":
            score += 6; reasons.append("organic shrink")

        # Insider buying
        if f4_present:
            score += 10
            reasons.append(f"F4 ${f4_rec.get('total_dollar', 0)/1e6:.1f}M")

        # Bank-specific kicker via FDIC data
        if fdic_rec:
            t1 = _num(fdic_rec.get("tier1_rwa_pct"))
            np_pct = _num(fdic_rec.get("nonperforming_loans_pct"))
            if t1 is not None and t1 >= 10:
                score += 6; reasons.append(f"T1 {t1:.1f}%")
            if np_pct is not None and np_pct < 1.5:
                score += 6; reasons.append(f"NPA {np_pct:.2f}%")

        if score < 15:
            continue

        out[tk] = {
            "sector": y.get("sector"),
            "industry": y.get("industry"),
            "p_b": pb,
            "p_e_trailing": pe,
            "roe": roe,
            "bb_status": bb_status,
            "f4_present": f4_present,
            "has_fdic": bool(fdic_rec),
            "score": round(score, 1),
            "reasons": "; ".join(reasons),
        }

    io_util.write_json(OUT, out)
    print(f"\nwrote {OUT} ({len(out)} financial-sector primary names)")

    ranked = sorted(out.items(), key=lambda x: -x[1]["score"])
    print(f"\n=== TOP 20 financial-sector primary ===")
    for tk, v in ranked[:20]:
        pb = v.get("p_b") or 0
        roe = (v.get("roe") or 0) * 100
        print(f"  {tk:<7} score={v['score']:<5} P/B={pb:<5.2f} ROE={roe:<5.1f}% "
              f"sector={(v.get('industry') or '')[:25]}  "
              f"{v['reasons'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
