"""Unified European composite: implicit buyback + PDMR + fundamentals.

Combines three layers into one ranking:
  - eu_buyback_detect.json: share-count change, P/B, drawdown, size
  - eu_pdmr.json:           PDMR keyword counts + buyback execution
                            keyword counts from yfinance news feed
  - intl_detail.json, uk_v2_detail.json: existing fundamentals composite

Master composite for European names:
  master = 0.35 * implicit_buyback_score
         + 0.25 * pdmr_score (50 if 3+ events; 30 if 1-2)
         + 0.20 * fundamentals composite (from uk_v2 / intl_detail)
         + 0.20 * peer fundamentals normalisation
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from universe_filter import is_excluded


def load_json(path: str) -> dict | list:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--min-master", type=float, default=15.0)
    p.add_argument("--csv", default="eu_combined.csv")
    p.add_argument("--region", choices=["UK", "EU", "INTL", "ALL"], default="ALL")
    args = p.parse_args()

    bb = load_json("european_buyback.json")          # implicit buyback layer
    pdmr = load_json("eu_pdmr.json")                  # PDMR keyword layer
    uk_fund = load_json("uk_v2_detail.json")          # UK fundamentals
    intl_fund = load_json("intl_detail.json")         # INTL fundamentals

    # Build fundamentals index
    fund_by_tk: dict = {}
    for r in uk_fund + intl_fund:
        tk = r.get("ticker")
        if tk:
            fund_by_tk[tk] = r

    all_tickers = set(bb.keys()) | set(pdmr.keys()) | set(fund_by_tk.keys())
    print(f"Universe: {len(all_tickers)} European tickers")

    rows = []
    for tk in all_tickers:
        bad, _ = is_excluded(tk)
        if bad:
            continue
        if args.region == "UK" and not tk.endswith(".L"):
            continue
        if args.region == "EU":
            eu_suffixes = (".DE", ".PA", ".MI", ".AS", ".BR", ".VI", ".HE", ".ST",
                           ".CO", ".SW", ".OL", ".MC", ".LS", ".AT", ".WA", ".F")
            if not any(tk.endswith(s) for s in eu_suffixes):
                continue
        if args.region == "INTL" and not (
            tk.endswith(".AX") or tk.endswith(".TO") or tk.endswith(".HK") or
            tk.endswith(".T") or tk.endswith(".SI") or tk.endswith(".V")
        ):
            continue

        bb_d = bb.get(tk, {})
        pd_d = pdmr.get(tk, {})
        fund = fund_by_tk.get(tk, {})

        bb_score = bb_d.get("score") or 0
        # PDMR score: 50 if 3+ events, 30 if 1-2, 0 if none
        pdmr_total = pd_d.get("total_signal_count") or 0
        if pdmr_total >= 3:
            pdmr_score = 60
        elif pdmr_total >= 1:
            pdmr_score = 35
        else:
            pdmr_score = 0
        # Bonus for directional buy detected
        if (pd_d.get("buy_directional_count") or 0) >= 1:
            pdmr_score += 15
        pdmr_score = min(100, pdmr_score)

        # Fundamentals composite (from uk_v2 / intl_detail)
        f_comp = fund.get("composite") or 0
        f_comp = min(100, f_comp)

        master = (
            0.40 * bb_score
            + 0.30 * pdmr_score
            + 0.30 * f_comp
        )

        if master < args.min_master:
            continue

        sh = bb_d.get("share_history") or {}
        ph = bb_d.get("price_summary") or {}
        ff = bb_d.get("fundamentals") or {}

        rows.append({
            "ticker": tk,
            "name": (ff.get("name") or fund.get("name") or "")[:50],
            "sector": ff.get("sector") or fund.get("sector"),
            "currency": ff.get("currency"),
            "price": ph.get("last") or ff.get("price") or fund.get("price"),
            "market_cap_musd": round((ff.get("market_cap") or
                                       fund.get("market_cap") or 0) / 1e6, 1),
            "master": round(master, 1),
            "implicit_buyback_score": bb_score,
            "pdmr_score": pdmr_score,
            "fundamentals_composite": f_comp,
            "shares_change_1y_pct": sh.get("pct_change_1y"),
            "shares_change_2y_pct": sh.get("pct_change_2y"),
            "ret_90d_pct": ph.get("ret_90d_pct"),
            "ret_180d_pct": ph.get("ret_180d_pct"),
            "p_b": ff.get("p_b") or fund.get("p_b"),
            "div_yield": ff.get("div_yield") or fund.get("div_yield"),
            "pdmr_events": pdmr_total,
            "buyback_news_events": pd_d.get("buyback_count") or 0,
            "buy_directional_events": pd_d.get("buy_directional_count") or 0,
            "example_headline": ((pd_d.get("hits") or [""])[0] if pd_d.get("hits") else "")[:120],
            "reasons": " | ".join(bb_d.get("reasons") or []),
        })

    rows.sort(key=lambda r: r["master"], reverse=True)

    fields = ["rank", "ticker", "name", "sector", "currency", "price",
              "market_cap_musd", "master", "implicit_buyback_score",
              "pdmr_score", "fundamentals_composite",
              "shares_change_1y_pct", "shares_change_2y_pct",
              "ret_90d_pct", "ret_180d_pct", "p_b", "div_yield",
              "pdmr_events", "buyback_news_events", "buy_directional_events",
              "example_headline", "reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nEligible: {len(rows)} | wrote {args.csv}")
    print(f"\n=== TOP {args.top} EUROPEAN COMPOSITE ===")
    print(f"{'#':<3}{'TKR':<11}{'CCY':<4}{'PX':>9}{'MCAP':>9}{'MAS':>5}"
          f"{'BB':>5}{'PDM':>5}{'FUN':>5}{'SH1Y':>7}{'180D':>7}{'P/B':>6}"
          f"  NAME")
    for i, r in enumerate(rows[: args.top], 1):
        cur = (r.get("currency") or "")[:3]
        px = r.get("price") or 0
        mc = r.get("market_cap_musd") or 0
        sh = r.get("shares_change_1y_pct")
        sh_s = f"{sh:+.1f}%" if sh is not None else "-"
        r180 = r.get("ret_180d_pct")
        r180_s = f"{r180:+.0f}%" if r180 is not None else "-"
        pb = r.get("p_b")
        pb_s = f"{pb:.2f}" if pb else "-"
        print(f"{i:<3}{r['ticker']:<11}{cur:<4}{px:>9.2f}{mc:>8.0f}M"
              f"{r['master']:>5.0f}{r['implicit_buyback_score']:>5.0f}"
              f"{r['pdmr_score']:>5.0f}{r['fundamentals_composite']:>5.0f}"
              f"{sh_s:>7}{r180_s:>7}{pb_s:>6}  {r.get('name','')[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
