"""Targeted PE / EV/EBITDA refresh + PSU-universe-only ranker.

Two jobs:
  1. Refresh yfinance for the PSU-scored universe (4,410 names) so
     trailingPE / forwardPE / enterpriseToEbitda are populated. Reuses
     the enrich_yfinance.fetch_one schema (now includes new fields).
  2. Rank all PSU-scored names on PSU-forensic strength alone, then
     overlay valuation (P/E, EV/EBITDA, P/B) to surface "best PSU +
     cheapest by earnings multiple" names. Verifies whether the
     convergent 12 actually sit at the top of the PSU universe.

Outputs:
  psu_universe_ranked.csv  -- all 4,410 PSU names ranked by composite
                               of PSU forensics + valuation multiples
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
YF_OUT = ROOT / "yfinance_quick.json"


def load_proxy() -> dict:
    out = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try: d = json.loads(open(fn).read())
        except: continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in out or
                    r.get("filing_date", "") > out[tk].get("filing_date", "")):
                    out[tk] = r
    return out


def refresh_yf(tickers: list[str], sleep: float = 0.2,
                refresh_keys: list[str] | None = None,
                limit: int = 10000) -> None:
    """For each ticker, if any refresh_keys are missing in the existing
    yfinance_quick.json record, re-fetch and update in place. Default:
    refresh if p_e_trailing absent (i.e. row predates the new schema)."""
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance required", file=sys.stderr)
        return
    from enrich_yfinance import fetch_one

    existing = json.loads(YF_OUT.read_text()) if YF_OUT.exists() else {}
    needs_refresh = []
    refresh_keys = refresh_keys or ["p_e_trailing"]
    for tk in tickers:
        cur = existing.get(tk)
        if not cur:
            needs_refresh.append(tk)
        elif any(k not in cur for k in refresh_keys):
            needs_refresh.append(tk)

    print(f"[refresh] {len(needs_refresh)} tickers need refresh "
          f"(of {len(tickers)} requested)", file=sys.stderr)
    n_done = n_failed = 0
    for i, tk in enumerate(needs_refresh, 1):
        if n_done >= limit:
            break
        try:
            row = fetch_one(yf, tk)
        except Exception as e:
            row = {"_error": str(e)[:120]}
        if row and not row.get("_error"):
            # Merge with existing (preserve any extra fields)
            cur = existing.get(tk) or {}
            cur.update(row)
            existing[tk] = cur
            n_done += 1
        else:
            n_failed += 1
        time.sleep(sleep)
        if i % 25 == 0:
            tmp = YF_OUT.with_suffix(".tmp")
            tmp.write_text(json.dumps(existing, default=str))
            tmp.replace(YF_OUT)
            print(f"  [{i}/{len(needs_refresh)}] refreshed={n_done} "
                  f"failed={n_failed}", file=sys.stderr, flush=True)

    tmp = YF_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, default=str))
    tmp.replace(YF_OUT)
    print(f"[refresh] done: {n_done} refreshed, {n_failed} failed",
          file=sys.stderr)


def psu_universe_rank(proxy: dict, yf: dict) -> list[dict]:
    """Score every PSU-scored name on:
       PSU forensic core + governance + forward cond_cats + per-share metrics
     then overlay valuation: P/E (lower better), EV/EBITDA (lower better),
     P/B (lower better).
     Returns ranked list with all relevant fields exposed.
    """
    fwd_event_weight = {
        "revenue_dollar_target": 12, "ebitda_dollar_target": 12,
        "fcf_dollar_target": 12, "operating_margin_target": 10,
        "fda_phase_milestone": 10, "merger_acquisition_close": 12,
        "spin_separation": 10, "asset_sale_named": 12,
        "debt_leverage_target": 10, "restructuring_milestone": 12,
        "chapter11_emergence": 15, "backlog_target": 8,
        "subscriber_arr_target": 8,
    }

    rows = []
    for tk, p in proxy.items():
        # require actual PSU presence (not just proxy row)
        if not p.get("psu_core") and not p.get("cond_cats"):
            continue

        psu_pts = 0.0
        core = p.get("psu_core") or 0
        psu_pts += min(core * 0.5, 30)
        for cat in (p.get("cond_cats") or []):
            psu_pts += fwd_event_weight.get(cat, 0)
        pct = p.get("psu_pct_lti") or 0
        if pct >= 80: psu_pts += 8
        elif pct >= 60: psu_pts += 4
        gov = p.get("gov_score") or 0
        psu_pts += min(gov * 0.5, 15)
        n_per_share = len(p.get("per_share_metrics") or [])
        psu_pts += min(n_per_share * 2, 10)

        y = yf.get(tk, {}) or {}
        mcap = y.get("mcap")
        px = y.get("price")
        pb = y.get("p_b")
        pe_t = y.get("p_e_trailing")
        pe_f = y.get("p_e_forward")
        ev_ebitda = y.get("ev_ebitda")
        ev_rev = y.get("ev_revenue")
        sector = y.get("sector")

        # Valuation kicker (lower = cheaper = bigger asymmetry)
        val_pts = 0.0
        val_reasons = []
        if pb and 0 < pb < 0.5: val_pts += 12; val_reasons.append(f"P/B {pb:.2f}")
        elif pb and 0 < pb < 1.0: val_pts += 6; val_reasons.append(f"P/B {pb:.2f}")
        if pe_t and 0 < pe_t < 10:
            val_pts += 10; val_reasons.append(f"P/E {pe_t:.1f}")
        elif pe_t and 0 < pe_t < 15:
            val_pts += 5; val_reasons.append(f"P/E {pe_t:.1f}")
        if ev_ebitda and 0 < ev_ebitda < 6:
            val_pts += 12; val_reasons.append(f"EV/EBITDA {ev_ebitda:.1f}")
        elif ev_ebitda and 0 < ev_ebitda < 10:
            val_pts += 6; val_reasons.append(f"EV/EBITDA {ev_ebitda:.1f}")

        total = psu_pts + val_pts
        rows.append({
            "ticker": tk,
            "name": y.get("name") or "",
            "sector": sector or "",
            "mcap_M": round((mcap or 0) / 1e6, 0),
            "price": px,
            "p_b": pb,
            "pe_trailing": pe_t,
            "pe_forward": pe_f,
            "ev_ebitda": ev_ebitda,
            "ev_revenue": ev_rev,
            "psu_core": p.get("psu_core"),
            "gov_score": p.get("gov_score"),
            "psu_pct_lti": p.get("psu_pct_lti"),
            "cond_cats": ",".join(p.get("cond_cats") or []),
            "per_share_metrics": ",".join(p.get("per_share_metrics") or []),
            "psu_points": round(psu_pts, 1),
            "value_points": round(val_pts, 1),
            "total": round(total, 1),
            "value_reasons": "; ".join(val_reasons),
        })

    rows.sort(key=lambda r: -r["total"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch yfinance for PSU universe to populate "
                         "PE / EV/EBITDA fields")
    ap.add_argument("--refresh-limit", type=int, default=5000)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    print("Loading PSU universe from disk...", file=sys.stderr)
    proxy = load_proxy()
    psu_tickers = [tk for tk, p in proxy.items()
                   if p.get("psu_core") or p.get("cond_cats")]
    print(f"PSU-scored universe: {len(psu_tickers)} tickers",
          file=sys.stderr)

    if args.refresh:
        refresh_yf(psu_tickers, sleep=args.sleep, limit=args.refresh_limit)

    yf = json.loads(YF_OUT.read_text()) if YF_OUT.exists() else {}
    rows = psu_universe_rank(proxy, yf)

    out = ROOT / "psu_universe_ranked.csv"
    fieldnames = list(rows[0].keys())
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out} ({len(rows)} rows)")

    # Coverage on PE / EV/EBITDA
    n_pe = sum(1 for r in rows if r["pe_trailing"])
    n_evb = sum(1 for r in rows if r["ev_ebitda"])
    print(f"  P/E coverage:      {n_pe}/{len(rows)} ({n_pe/len(rows)*100:.0f}%)")
    print(f"  EV/EBITDA coverage: {n_evb}/{len(rows)} ({n_evb/len(rows)*100:.0f}%)")

    # Print top 30
    print(f"\n=== TOP 30 by PSU + valuation total ===")
    print(f"{'#':<3}{'TKR':<8}{'TOT':<6}{'PSU':<6}{'VAL':<6}"
          f"{'MCAP$M':<10}{'P/B':<6}{'P/E':<7}{'EV/EBT':<8}{'NAME'}")
    for i, r in enumerate(rows[:30], 1):
        print(f"{i:<3}{r['ticker']:<8}{r['total']:<6}{r['psu_points']:<6}"
              f"{r['value_points']:<6}"
              f"{r['mcap_M'] or 0:<10.0f}"
              f"{r['p_b'] or 0:<6.2f}"
              f"{(r['pe_trailing'] or 0):<7.1f}"
              f"{(r['ev_ebitda'] or 0):<8.1f}"
              f"{(r['name'] or '')[:30]}")

    # Convergent 12 check: are they actually at the top of the PSU universe?
    try:
        consensus_rows = list(csv.DictReader(
            open(ROOT / "consensus_ranking.csv")))
        convergent = {r["ticker"] for r in consensus_rows
                      if int(r.get("n_screens") or 0) >= 3
                      and int(r.get("n_archetypes_won") or 0) >= 1}
    except Exception:
        convergent = set()

    print(f"\n=== Convergent 12 rank within PSU universe ===")
    rank_map = {r["ticker"]: i+1 for i, r in enumerate(rows)}
    for tk in sorted(convergent, key=lambda t: rank_map.get(t, 99999)):
        rk = rank_map.get(tk, "—")
        row = next((r for r in rows if r["ticker"] == tk), None)
        if row:
            print(f"  #{rk:<5} {tk:<8} tot={row['total']:<6} "
                  f"psu={row['psu_points']:<6} val={row['value_points']:<6} "
                  f"P/E={row['pe_trailing'] or '—'} "
                  f"EV/EBITDA={row['ev_ebitda'] or '—'}")
        else:
            print(f"  not-in-PSU  {tk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
