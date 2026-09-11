"""Triangulate accumulation candidates with insider, 13D, short, news.

The cleanest "pre-news accumulation" signal is:
   volume spike + flat base
 + insider Form 4 buying OR 13D filed
 + high short interest (squeeze setup)
 + no recent news (so the spike isn't market reaction)
 + cross-confirms a governance/PSU signal we already detected
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
    p.add_argument("--min-acc", type=int, default=50)
    p.add_argument("--csv", default="triangulated.csv")
    p.add_argument("--region", choices=["US", "UK", "INTL", "ALL"], default="ALL")
    args = p.parse_args()

    acc = load_json("accumulation_scan.json")
    enr = load_json("enrichment_overlay.json")
    yfo = load_json("yfinance_enrichment.json")
    rns = load_json("uk_rns_overlay.json")

    gov_top = set()
    try:
        for r in csv.DictReader(open("top100.csv")):
            gov_top.add((r.get("ticker") or "").upper())
    except Exception:
        pass

    rows = []
    for tk, a in acc.items():
        if not isinstance(a, dict) or a.get("_error"):
            continue
        if (a.get("accumulation_score") or 0) < args.min_acc:
            continue
        bad, _ = is_excluded(tk)
        if bad:
            continue
        is_uk = tk.endswith(".L")
        is_intl = any(tk.endswith(s) for s in (".AX", ".TO", ".V", ".HK", ".SI",
                                                ".T", ".DE", ".PA", ".MI", ".F"))
        is_us = "." not in tk
        if args.region == "US" and not is_us: continue
        if args.region == "UK" and not is_uk: continue
        if args.region == "INTL" and not is_intl: continue

        e = enr.get(tk) or {}
        y = yfo.get(tk) or {}
        n = rns.get(tk) or {}

        sc13d = (e.get("sc13d_filings_1y") or 0)
        f4_count = (e.get("insider_form4_count_90d") or 0)
        short_pct = y.get("short_pct_float")
        days_cover = y.get("short_ratio")
        analyst_count = y.get("analyst_count")
        earnings_in = y.get("earnings_date_days")
        sector = y.get("sector") or n.get("sector")
        company = y.get("name") or ""
        news_count = len(n.get("news_titles") or [])

        tri = 0
        reasons = []
        if sc13d >= 1:
            tri += 25; reasons.append(f"13D filed ({sc13d})")
        if f4_count >= 5:
            tri += 20; reasons.append(f"Insider Form 4 tape ({f4_count})")
        elif f4_count >= 3:
            tri += 10
        if short_pct is not None and short_pct >= 0.15:
            tri += 18; reasons.append(f"High short ({short_pct*100:.1f}%)")
        elif short_pct is not None and short_pct >= 0.08:
            tri += 10; reasons.append(f"Notable short ({short_pct*100:.1f}%)")
        if days_cover is not None and days_cover >= 7:
            tri += 10; reasons.append(f"Days-to-cover {days_cover:.1f}")
        if analyst_count is not None and analyst_count <= 2:
            tri += 8; reasons.append(f"Neglected (analysts={int(analyst_count)})")
        if news_count == 0:
            tri += 8; reasons.append("News-quiet (no RNS in feed)")
        if earnings_in is not None and 1 <= earnings_in <= 14:
            tri += 12; reasons.append(f"Earnings in {earnings_in}d")
        if tk.upper() in gov_top:
            tri += 20; reasons.append("Cross-confirmed in gov/PSU top 100")

        acc_score = a.get("accumulation_score") or 0
        composite = round((acc_score * (50 + tri)) / 150, 1)

        rows.append({
            "ticker": tk, "company": company, "sector": sector,
            "last_close": a.get("last_close"),
            "vol_spike": a.get("vol_spike"),
            "max_4w_spike": a.get("max_4w_spike"),
            "pos_in_6m_range": a.get("pos_in_6m_range"),
            "volatility_13w": a.get("volatility_13w"),
            "mfi": a.get("mfi"),
            "accumulation_score": acc_score,
            "sc13d_filings_1y": sc13d,
            "insider_form4_count_90d": f4_count,
            "short_pct_float": short_pct,
            "days_to_cover": days_cover,
            "analyst_count": analyst_count,
            "earnings_in_days": earnings_in,
            "news_count_recent": news_count,
            "in_gov_top100": tk.upper() in gov_top,
            "triangulation_score": tri,
            "composite": composite,
            "reasons": " | ".join(reasons),
        })

    rows.sort(key=lambda r: r["composite"], reverse=True)

    fields = ["rank", "ticker", "company", "sector", "last_close",
              "composite", "accumulation_score", "triangulation_score",
              "vol_spike", "max_4w_spike", "pos_in_6m_range",
              "volatility_13w", "mfi",
              "sc13d_filings_1y", "insider_form4_count_90d",
              "short_pct_float", "days_to_cover",
              "analyst_count", "earnings_in_days",
              "news_count_recent", "in_gov_top100", "reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"Triangulated {len(rows)} candidates (acc>={args.min_acc}, "
          f"region={args.region}). Top {args.top}:\n")
    print(f"{'#':<3}{'TKR':<11}{'PX':>9}{'CMP':>5}{'ACC':>5}{'TRI':>5}"
          f"{'SPK':>5}{'POS':>5}{'F4':>4}{'13D':>4}{'SHRT':>6}  {'GOV':<3}  REASONS")
    print("-" * 130)
    for i, r in enumerate(rows[: args.top], 1):
        spk = max(r.get("vol_spike") or 0, r.get("max_4w_spike") or 0)
        pos = (r.get("pos_in_6m_range") or 0) * 100
        sht = (r.get("short_pct_float") or 0) * 100
        gov = "Y" if r.get("in_gov_top100") else "-"
        reasons = (r.get("reasons") or "")[:60]
        print(f"{i:<3}{r['ticker']:<11}{r.get('last_close') or 0:>9.2f}"
              f"{r['composite']:>5.0f}{r['accumulation_score']:>5}"
              f"{r['triangulation_score']:>5}"
              f"{spk:>5.1f}{pos:>4.0f}%"
              f"{(r.get('insider_form4_count_90d') or 0):>4}"
              f"{(r.get('sc13d_filings_1y') or 0):>4}"
              f"{sht:>5.1f}%  {gov:<3}  {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
