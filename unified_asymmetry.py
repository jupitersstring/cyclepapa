"""Unified asymmetry composite — combines every signal layer:

  1. PSU comp asymmetry      (psu_scoring)
  2. Process quality          (governance, special committee, advisers, bid)
  3. Special situations       (Bastian: distressed stub, spin, take-private)
  4. Cluster insider buying   (Cohen-Malloy-Pomorski via Form 4)
  5. Buyback intensity        (Bonaimé-Ryngaert)
  6. U-Index                  (Peyer-Vermaelen: size + B/M + prior 6m)
  7. Accumulation pattern     (volume spike + flat base + near 6m low)
  8. Buyback price-flat       (buyback while 90d return flat)
  9. Activist primary source  (SC 13D filings)

Output: unified_asymmetry.csv with top-N overall + top-15 per axis.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from universe_filter import is_excluded


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_detail_jsons() -> dict[str, dict]:
    """Merge all *_detail.json sources into per-ticker dict."""
    by_ticker: dict[str, dict] = {}
    sources = ["v2_detail.json", "wide180_detail.json", "wide365_detail.json",
               "induce_detail.json", "restruct_v10.json", "missing_v10.json",
               "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json",
               "uk_v2_detail.json", "intl_detail.json"]
    for fn in sources:
        p = Path(fn)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
            for r in data:
                if r.get("error"):
                    continue
                tk = (r.get("ticker") or "").upper()
                if not tk:
                    continue
                cur = by_ticker.setdefault(tk, {})
                # Take max numeric across runs
                for k in ("asymmetry", "alignment", "upside_kicker",
                          "process_quality", "special_situations_score",
                          "distressed_stub_score", "munger_composite",
                          "buyback_authorisation_musd", "largest_owner_pct",
                          "insiders_group_pct",
                          "balance_sheet_convexity", "common_preservation",
                          "catalyst_hardness", "strategic_review",
                          "change_of_control", "activist_score",
                          "board_score", "financing_score"):
                    v = r.get(k)
                    if v is not None and (cur.get(k) is None or
                                          v > (cur.get(k) or 0)):
                        cur[k] = v
                # Take union of boolean flags
                for k in ("transformation_signal", "has_special_committee",
                          "strategic_alts_language", "engaged_adviser",
                          "active_bid", "majority_of_minority",
                          "has_debt_event", "has_spinoff",
                          "go_private_language", "governance_reset",
                          "creditor_board_control", "discretionary_language",
                          "repricing_language", "retirement_language"):
                    cur[k] = cur.get(k) or r.get(k)
                # Lists union
                for k in ("activists_named", "advisers_named",
                          "stock_price_hurdles", "per_share_metrics",
                          "aggregate_metrics"):
                    a = cur.get(k) or []
                    b = r.get(k) or []
                    cur[k] = list(dict.fromkeys((a or []) + (b or [])))
                # Take latest non-empty meta
                for k in ("company", "filing_date", "filing_url",
                          "current_price", "market_cap"):
                    if r.get(k) and not cur.get(k):
                        cur[k] = r[k]
        except Exception:
            pass
    return by_ticker


def load_yf_enrichment() -> dict[str, dict]:
    p = Path("yfinance_enrichment.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_form4_buys() -> dict[str, dict]:
    p = Path("form4_buys.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_enrichment_overlay() -> dict[str, dict]:
    p = Path("enrichment_overlay.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_accumulation() -> dict[str, dict]:
    p = Path("accumulation_scan.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Per-axis scoring helpers (each returns 0-100)
# ---------------------------------------------------------------------------

def axis_psu(r: dict, px: float | None) -> float:
    """PSU comp asymmetry leg."""
    asym = r.get("asymmetry") or 0
    kick = r.get("upside_kicker") or 0
    h = r.get("stock_price_hurdles") or []
    bonus = 15 if r.get("transformation_signal") else 0
    ladder_kicker = 0
    if h and px and px > 0:
        plausible = [v for v in h if 1.0 < v / px <= 30.0]
        if plausible:
            moneyness = max(plausible) / px
            if moneyness >= 1.5:
                ladder_kicker = min(100, (moneyness - 1.0) * 50.0)
    return min(100.0, max(asym, kick, ladder_kicker) + bonus)


def axis_process(r: dict) -> float:
    """Process / governance / special-situations leg."""
    pq = r.get("process_quality") or 0
    sr = r.get("strategic_review") or 0
    ds = r.get("distressed_stub_score") or 0
    ac = r.get("activist_score") or 0
    cc = r.get("change_of_control") or 0
    sp = r.get("special_situations_score") or 0
    syn = 0.0
    if r.get("has_special_committee"): syn += 30
    if r.get("activists_named") or (r.get("sc13d_filings_1y") or 0) > 0: syn += 20
    if r.get("active_bid"): syn += 15
    if r.get("engaged_adviser") or r.get("advisers_named"): syn += 10
    if r.get("has_debt_event"): syn += 10
    if r.get("has_spinoff"): syn += 8
    if r.get("go_private_language"): syn += 10
    syn = min(100.0, syn)
    return max(pq, sr, ds, ac, cc, sp, syn)


def axis_cluster(insider: dict, market_cap: float | None) -> float:
    """Cohen-Malloy-Pomorski insider cluster."""
    if not insider:
        return 0.0
    buyers = insider.get("buyer_set") or []
    n = len(set(buyers))
    score = 0.0
    if n >= 5: score += 50
    elif n >= 4: score += 40
    elif n >= 3: score += 30
    elif n == 2: score += 15
    elif n == 1: score += 5
    total = insider.get("total_dollar") or 0
    if market_cap and market_cap > 0:
        pct = total / market_cap * 100
        if pct >= 2.0: score += 35
        elif pct >= 1.0: score += 25
        elif pct >= 0.5: score += 15
        elif pct >= 0.1: score += 6
    return min(100.0, score)


def axis_buyback(buyback_musd: float | None, market_cap: float | None,
                 ret_90d: float | None) -> float:
    """Bonaimé-Ryngaert buyback + price-flat."""
    if not buyback_musd or not market_cap or market_cap <= 0:
        return 0.0
    pct = buyback_musd * 1e6 / market_cap * 100
    score = 0.0
    if pct >= 30: score += 50
    elif pct >= 15: score += 40
    elif pct >= 10: score += 30
    elif pct >= 5: score += 20
    elif pct >= 2: score += 10
    # Price-flat amplifier: more-negative 90d return at high buyback = supply absorbed
    if ret_90d is not None:
        if ret_90d <= -20: score += 25
        elif ret_90d <= -10: score += 15
        elif ret_90d <= 5: score += 10
    return min(100.0, score)


def axis_u_index(market_cap: float | None, p_b: float | None,
                 ret_180d: float | None) -> float:
    """Peyer-Vermaelen U-Index."""
    s = 0.0
    if market_cap and market_cap > 0:
        mc_m = market_cap / 1e6
        if mc_m <= 250: s += 33
        elif mc_m <= 1000: s += 25
        elif mc_m <= 5000: s += 17
        elif mc_m <= 20000: s += 10
        else: s += 3
    if p_b is not None and p_b > 0:
        if p_b <= 0.8: s += 33
        elif p_b <= 1.5: s += 25
        elif p_b <= 3.0: s += 15
        elif p_b <= 6.0: s += 5
    if ret_180d is not None:
        if ret_180d <= -30: s += 33
        elif ret_180d <= -15: s += 24
        elif ret_180d <= 0: s += 16
        elif ret_180d <= 10: s += 8
    return min(100.0, s)


def axis_accumulation(acc: dict | None) -> float:
    if not acc or acc.get("_error"):
        return 0.0
    return float(acc.get("accumulation_score") or 0)


# ---------------------------------------------------------------------------
# Master composite
# ---------------------------------------------------------------------------

def compute_master(r: dict, ins: dict, yf_d: dict, enr: dict,
                   acc: dict) -> dict:
    px = r.get("current_price") or yf_d.get("price")
    market_cap = r.get("market_cap") or yf_d.get("market_cap")
    p_b = yf_d.get("p_b")
    ret_90 = yf_d.get("ret_90d_pct") if "ret_90d_pct" in yf_d else None
    ret_180 = yf_d.get("ret_180d_pct") if "ret_180d_pct" in yf_d else None
    # If yfinance enrichment doesn't have returns, derive from drawdown_pct.
    if ret_180 is None and yf_d.get("drawdown_pct") is not None:
        # 52w_pos low = price closer to low = more negative implied return
        dd = yf_d["drawdown_pct"]
        ret_180 = (dd - 50) / 2  # rough: pos<10% maps to ~-20

    psu = axis_psu(r, px)
    proc = axis_process(r)
    cluster = axis_cluster(ins, market_cap)
    bb = axis_buyback(r.get("buyback_authorisation_musd"), market_cap, ret_90)
    u = axis_u_index(market_cap, p_b, ret_180)
    accum = axis_accumulation(acc)

    # SC 13D primary-source bonus
    sc13d = enr.get("sc13d_filings_1y", 0) if enr else 0
    f4_count = enr.get("insider_form4_count_90d", 0) if enr else 0
    sc13d_bonus = 10 if sc13d else 0
    tape_bonus = 5 if f4_count >= 5 else 0

    # Master composite (weights tuned for asymmetric event-driven hunt)
    master = (
        0.18 * psu +
        0.20 * proc +
        0.22 * cluster +
        0.12 * bb +
        0.10 * u +
        0.10 * accum +
        sc13d_bonus + tape_bonus
    )
    master = min(100.0, master)

    return {
        "psu": round(psu, 1),
        "process": round(proc, 1),
        "cluster": round(cluster, 1),
        "buyback": round(bb, 1),
        "u_index": round(u, 1),
        "accumulation": round(accum, 1),
        "master": round(master, 1),
        "sc13d_1y": sc13d,
        "form4_90d_count": f4_count,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--top-per-axis", type=int, default=15)
    p.add_argument("--min-master", type=float, default=10.0)
    p.add_argument("--csv", default="unified_asymmetry.csv")
    args = p.parse_args()

    by_tk = load_detail_jsons()
    yf_d_all = load_yf_enrichment()
    form4_all = load_form4_buys()
    enr_all = load_enrichment_overlay()
    acc_all = load_accumulation()

    # Build full set including yfinance-only tickers
    all_tickers = set(by_tk.keys()) | set(yf_d_all.keys()) | set(form4_all.keys())
    print(f"Combined universe: {len(all_tickers)} tickers")

    rows = []
    for tk in all_tickers:
        bad, _ = is_excluded(tk)
        if bad:
            continue
        r = by_tk.get(tk, {})
        yf_d = yf_d_all.get(tk, {})
        ins = form4_all.get(tk, {})
        enr = enr_all.get(tk, {})
        acc = acc_all.get(tk, {})

        scores = compute_master(r, ins, yf_d, enr, acc)
        if scores["master"] < args.min_master:
            continue

        mc = r.get("market_cap") or yf_d.get("market_cap") or 0
        px = r.get("current_price") or yf_d.get("price") or 0
        co = r.get("company") or yf_d.get("name") or ""

        # Flags
        sigs = []
        if r.get("transformation_signal"): sigs.append("TR")
        if r.get("active_bid"): sigs.append("BID")
        if r.get("has_special_committee"): sigs.append("CMTE")
        acts = r.get("activists_named") or []
        if acts: sigs.append(f"ACT({acts[0][:14]})")
        if r.get("has_debt_event"): sigs.append("DEBT")
        if r.get("has_spinoff"): sigs.append("SPIN")
        if r.get("go_private_language"): sigs.append("PRIV")
        n_ins = len((ins.get("buyer_set") or []))
        if n_ins: sigs.append(f"INS({n_ins})")
        if scores["sc13d_1y"]: sigs.append(f"13D({scores['sc13d_1y']})")

        rows.append({
            "ticker": tk,
            "company": co[:50],
            "current_price": round(float(px or 0), 2),
            "market_cap_musd": round(mc / 1e6, 1),
            "psu": scores["psu"],
            "process": scores["process"],
            "cluster": scores["cluster"],
            "buyback": scores["buyback"],
            "u_index": scores["u_index"],
            "accumulation": scores["accumulation"],
            "master": scores["master"],
            "n_insiders": n_ins,
            "insider_dollar": round((ins.get("total_dollar") or 0), 0),
            "insider_pct_mcap": round(((ins.get("total_dollar") or 0) /
                                       mc * 100) if mc else 0, 2),
            "buyback_musd": r.get("buyback_authorisation_musd") or 0,
            "buyback_pct_mcap": round(((r.get("buyback_authorisation_musd")
                                       or 0) * 1e6 / mc * 100) if mc else 0, 1),
            "sc13d_1y": scores["sc13d_1y"],
            "form4_90d_count": scores["form4_90d_count"],
            "ret_90d_pct": yf_d.get("ret_90d_pct"),
            "drawdown_pct": yf_d.get("drawdown_pct"),
            "p_b": yf_d.get("p_b"),
            "div_yield": yf_d.get("div_yield"),
            "signals": " ".join(sigs),
            "activists_named": ", ".join(acts[:3]),
            "filing_url": r.get("filing_url") or "",
        })

    rows.sort(key=lambda r: r["master"], reverse=True)

    fields = ["rank", "ticker", "company", "current_price", "market_cap_musd",
              "master", "psu", "process", "cluster", "buyback", "u_index",
              "accumulation", "n_insiders", "insider_dollar",
              "insider_pct_mcap", "buyback_musd", "buyback_pct_mcap",
              "sc13d_1y", "form4_90d_count",
              "ret_90d_pct", "drawdown_pct", "p_b", "div_yield",
              "signals", "activists_named", "filing_url"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    # Overall ranking
    print(f"\n=== TOP {args.top} OVERALL by MASTER ===")
    print(f"{'#':<3}{'TKR':<10}{'MCAP':>8}{'PX':>9}{'MAS':>5}"
          f"{'PSU':>5}{'PRC':>5}{'CLU':>5}{'BB':>5}{'U':>4}{'ACC':>5}  SIGNALS")
    print("-" * 130)
    for i, r in enumerate(rows[: args.top], 1):
        mc = r["market_cap_musd"]
        print(f"{i:<3}{r['ticker']:<10}{mc:>7.0f}M{r['current_price']:>9.2f}"
              f"{r['master']:>5.1f}{r['psu']:>5.0f}{r['process']:>5.0f}"
              f"{r['cluster']:>5.0f}{r['buyback']:>5.0f}{r['u_index']:>4.0f}"
              f"{r['accumulation']:>5.0f}  {r['signals'][:60]}")

    # Per-axis top
    axes = [("psu", "PSU comp asymmetry"),
            ("process", "Process / governance"),
            ("cluster", "Insider cluster"),
            ("buyback", "Buyback intensity"),
            ("u_index", "U-Index (size+B/M+6m)"),
            ("accumulation", "Accumulation tape")]
    for key, label in axes:
        print(f"\n=== TOP {args.top_per_axis} BY {label} ===")
        axis_sorted = sorted(rows, key=lambda r: r[key], reverse=True)
        print(f"{'#':<3}{'TKR':<10}{'MCAP':>8}{'PX':>9}{key.upper():>5}"
              f"{'MAS':>5}  SIGNALS")
        for i, r in enumerate(axis_sorted[: args.top_per_axis], 1):
            print(f"{i:<3}{r['ticker']:<10}{r['market_cap_musd']:>7.0f}M"
                  f"{r['current_price']:>9.2f}{r[key]:>5.0f}"
                  f"{r['master']:>5.1f}  {r['signals'][:60]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
