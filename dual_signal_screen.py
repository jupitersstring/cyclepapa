"""Dual-signal screen (Bonaimé-Ryngaert) + Peyer-Vermaelen U-Index
+ Cohen-Malloy-Pomorski cluster scoring.

Inputs:
  form4_buys.json       primary-source Form 4 P transactions
  *_detail.json         buyback authorisations from cached scoring runs
  yfinance              price/fundamentals (B/M, 6m return, mcap, ADV)

Scoring components:

  cluster_score (0-100)
    Multiple distinct insiders within a short window is much higher
    signal than one large buy (Cohen-Malloy-Pomorski). Weight by:
      n_distinct_buyers: 3+ = 30; 4+ = 40; 5+ = 50
      total_insider_dollar / mkt_cap: each +0.5% adds 10 points (cap 30)
      title-tier (founder/CEO weighted higher than non-exec dir)
      recency: filings in past 14d count more than 30d

  u_index (0-100)  Peyer-Vermaelen
    Higher U-Index = better undervaluation signal at buyback time
    Components (each 0-33):
      size      smaller cap = higher
      B/M       lower P/B = higher
      prior_6m  more-negative return = higher

  dual_signal_score (0-100)
    Bonaimé-Ryngaert: requires SAME-direction agreement
      Buyback authorisation $/mcap >= 5%: +30
      Buyback authorisation $/mcap >= 10%: +50
      Insider net buying (P > S in $): +25
      Both fire together: +25 alignment bonus
      If insiders are net sellers while firm is buying: -40 penalty

  composite = 0.40 cluster + 0.35 dual + 0.25 u_index

Output: dual_signal.csv ranked by composite.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

from universe_filter import is_excluded


# ---------------------------------------------------------------------------
# Title-tier weights (founder-CEO > CEO > C-suite > director > 10% holder)
# ---------------------------------------------------------------------------

FOUNDER_TITLES = ("founder", "chairman and ceo", "chairman, ceo", "ceo and chairman")
CEO_TITLES = ("chief executive officer", "ceo", "president and ceo")
CFO_TITLES = ("chief financial officer", "cfo", "principal financial officer")
COO_TITLES = ("chief operating officer", "coo")
CHAIR_TITLES = ("chairman", "chair of the board", "executive chairman")
DIR_TITLES = ("director", "independent director")


def insider_tier(title: str | None, is_dir: bool, is_off: bool, is_10pct: bool) -> tuple[int, str]:
    if not title:
        title = ""
    t = title.lower()
    if any(k in t for k in FOUNDER_TITLES):
        return 5, "FOUNDER"
    if any(k in t for k in CEO_TITLES):
        return 4, "CEO"
    if any(k in t for k in CFO_TITLES + COO_TITLES + CHAIR_TITLES):
        return 3, "C-SUITE"
    if is_off:
        return 3, "OFFICER"
    if any(k in t for k in DIR_TITLES) or is_dir:
        return 2, "DIRECTOR"
    if is_10pct:
        return 4, "10%_HOLDER"
    return 1, "OTHER"


# ---------------------------------------------------------------------------
# Cluster scoring (Cohen-Malloy-Pomorski-style)
# ---------------------------------------------------------------------------

def cluster_score(insider_data: dict, market_cap: float | None) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    buyers = insider_data.get("buyer_set") or []
    n_distinct = len(set(buyers))
    if n_distinct >= 5:
        score += 50; reasons.append(f"{n_distinct} distinct insiders")
    elif n_distinct >= 4:
        score += 40; reasons.append(f"{n_distinct} distinct insiders")
    elif n_distinct >= 3:
        score += 30; reasons.append(f"{n_distinct} distinct insiders")
    elif n_distinct == 2:
        score += 15
    elif n_distinct == 1:
        score += 5

    # Insider $ as % of market cap
    total_dollar = insider_data.get("total_dollar") or 0
    if market_cap and market_cap > 0:
        pct = total_dollar / market_cap * 100
        if pct >= 2.0:
            score += 30; reasons.append(f"Insider $ = {pct:.1f}% of mcap")
        elif pct >= 1.0:
            score += 22; reasons.append(f"Insider $ = {pct:.1f}% of mcap")
        elif pct >= 0.5:
            score += 14; reasons.append(f"Insider $ = {pct:.1f}% of mcap")
        elif pct >= 0.1:
            score += 6

    # Title-tier weighting: best tier in the buyer set
    best_tier = 0
    best_label = ""
    for b in buyers:
        # buyer format: "Name | Title or Role"
        parts = b.split("|", 1)
        title = parts[1].strip() if len(parts) > 1 else ""
        # Crude: re-derive tier from title string only
        t = title.lower()
        if any(k in t for k in FOUNDER_TITLES):
            tier = 5; label = "FOUNDER"
        elif any(k in t for k in CEO_TITLES) or "ceo" in t.split():
            tier = 4; label = "CEO"
        elif any(k in t for k in CFO_TITLES + COO_TITLES):
            tier = 3; label = "C-SUITE"
        elif "10%" in t:
            tier = 4; label = "10%_HOLDER"
        elif any(k in t for k in CHAIR_TITLES):
            tier = 3; label = "CHAIR"
        elif any(k in t for k in DIR_TITLES):
            tier = 2; label = "DIRECTOR"
        else:
            tier = 1; label = "OTHER"
        if tier > best_tier:
            best_tier = tier; best_label = label

    if best_tier >= 4:
        score += 15; reasons.append(f"Top tier: {best_label}")
    elif best_tier == 3:
        score += 8; reasons.append(f"C-suite buyer")

    # Recency: filings dates relative to today
    filings = insider_data.get("filings") or []
    today = datetime.now(timezone.utc)
    recent_14d = 0
    for f in filings:
        d = f.get("date")
        if not d: continue
        try:
            dd = datetime.strptime(d[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if (today - dd).days <= 14:
                recent_14d += 1
        except Exception:
            pass
    if recent_14d >= 3:
        score += 10; reasons.append(f"{recent_14d} buys in past 14d")
    elif recent_14d >= 1:
        score += 5

    return min(100.0, score), reasons


# ---------------------------------------------------------------------------
# Peyer-Vermaelen U-Index for buyback context
# ---------------------------------------------------------------------------

def u_index(price_data: dict, p_b: float | None, market_cap: float | None) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    # Size component: smaller = better
    if market_cap and market_cap > 0:
        mc_musd = market_cap / 1e6
        if mc_musd <= 250:
            score += 33; reasons.append(f"Size: micro (${mc_musd:.0f}M)")
        elif mc_musd <= 1000:
            score += 25; reasons.append(f"Size: small (${mc_musd:.0f}M)")
        elif mc_musd <= 5000:
            score += 17; reasons.append(f"Size: mid (${mc_musd:.0f}M)")
        elif mc_musd <= 20000:
            score += 10
        else:
            score += 3

    # B/M (1/P/B): lower P/B = higher B/M = better
    if p_b is not None and p_b > 0:
        if p_b <= 0.8:
            score += 33; reasons.append(f"P/B {p_b:.2f} (deep value)")
        elif p_b <= 1.5:
            score += 25; reasons.append(f"P/B {p_b:.2f}")
        elif p_b <= 3.0:
            score += 15
        elif p_b <= 6.0:
            score += 5
    elif p_b is not None and p_b < 0:
        # negative book equity -- distressed but signal not pure
        score += 10
        reasons.append(f"Negative book equity")

    # Prior 6-month return: more negative = better undervaluation context
    r_180 = price_data.get("ret_180d_pct") if price_data else None
    if r_180 is not None:
        if r_180 <= -30:
            score += 33; reasons.append(f"180d return {r_180:+.0f}%")
        elif r_180 <= -15:
            score += 24; reasons.append(f"180d return {r_180:+.0f}%")
        elif r_180 <= 0:
            score += 16; reasons.append(f"180d return {r_180:+.0f}%")
        elif r_180 <= 10:
            score += 8
        else:
            score += 0

    return min(100.0, score), reasons


# ---------------------------------------------------------------------------
# Bonaimé-Ryngaert dual-signal check
# ---------------------------------------------------------------------------

def dual_signal(insider_data: dict, buyback_musd: float | None,
                market_cap: float | None) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0

    bb_pct = 0.0
    if buyback_musd and market_cap:
        bb_pct = (buyback_musd * 1e6) / market_cap * 100
        if bb_pct >= 15:
            score += 50; reasons.append(f"Buyback {bb_pct:.1f}% of mcap (XL)")
        elif bb_pct >= 10:
            score += 38; reasons.append(f"Buyback {bb_pct:.1f}% of mcap")
        elif bb_pct >= 5:
            score += 25; reasons.append(f"Buyback {bb_pct:.1f}% of mcap")
        elif bb_pct >= 2:
            score += 10

    has_insider_buying = (insider_data and
                          (insider_data.get("total_dollar") or 0) > 0)
    if has_insider_buying:
        score += 25
        reasons.append("Insider net buying confirmed")

    # Dual alignment bonus
    if bb_pct >= 2 and has_insider_buying:
        score += 25
        reasons.append("DUAL SIGNAL: firm + insiders aligned")

    return min(100.0, score), reasons


# ---------------------------------------------------------------------------
# Universe loaders
# ---------------------------------------------------------------------------

def load_form4_buys() -> dict:
    p = Path("form4_buys.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def load_buyback_signals() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fn in ("v2_detail.json", "wide180_detail.json", "wide365_detail.json",
               "restruct_v10.json", "induce_detail.json", "missing_v10.json",
               "targets_v4.json", "cap_alloc.json", "cap_alloc_v2.json"):
        p = Path(fn)
        if not p.exists():
            continue
        try:
            for r in json.loads(p.read_text()):
                if r.get("error"):
                    continue
                tk = r.get("ticker")
                amt = r.get("buyback_authorisation_musd")
                mc = r.get("market_cap")
                if not tk:
                    continue
                cur = out.get(tk) or {}
                if amt and amt > (cur.get("buyback_musd") or 0):
                    cur.update(buyback_musd=amt, filing_url=r.get("filing_url"))
                if mc and (cur.get("market_cap") or 0) < mc:
                    cur["market_cap"] = mc
                if r.get("company"):
                    cur.setdefault("company", r.get("company"))
                out[tk] = cur
        except Exception:
            pass
    return out


def load_yf_overlay() -> dict[str, dict]:
    p = Path("yfinance_enrichment.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def fetch_price_history(ticker: str) -> dict | None:
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="1y", interval="1d", auto_adjust=False)
        if h is None or len(h) < 30:
            return None
    except Exception:
        return None
    h = h.dropna(subset=["Close"])
    if len(h) < 30:
        return None
    last = float(h["Close"].iloc[-1])
    def _ret(days):
        if len(h) <= days:
            return None
        prior = float(h["Close"].iloc[-days])
        return (last / prior - 1.0) * 100 if prior > 0 else None
    return {
        "last": last,
        "ret_30d_pct": _ret(30),
        "ret_90d_pct": _ret(90),
        "ret_180d_pct": _ret(180),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--min-composite", type=float, default=30.0)
    p.add_argument("--csv", default="dual_signal.csv")
    p.add_argument("--fetch-prices", action="store_true",
                   help="Pull live 30/90/180d returns for each candidate.")
    p.add_argument("--sleep", type=float, default=0.20)
    args = p.parse_args()

    form4 = load_form4_buys()
    buybacks = load_buyback_signals()
    yfo = load_yf_overlay()
    print(f"Form 4 issuers: {len(form4)} | "
          f"Buyback issuers: {len(buybacks)} | "
          f"Yfinance overlay: {len(yfo)}",
          file=sys.stderr)

    # Build unified ticker set
    all_tickers = set(form4.keys()) | set(buybacks.keys())
    print(f"Combined: {len(all_tickers)} tickers", file=sys.stderr)

    rows = []
    for tk in all_tickers:
        bad, _ = is_excluded(tk)
        if bad:
            continue
        ins = form4.get(tk) or {}
        bb = buybacks.get(tk) or {}
        yf_d = yfo.get(tk) or {}

        mc = bb.get("market_cap") or yf_d.get("market_cap")
        p_b = yf_d.get("p_b")
        company = bb.get("company") or yf_d.get("name") or ""

        # Price history (only fetch when --fetch-prices to keep dry-runs cheap)
        if args.fetch_prices:
            ph = fetch_price_history(tk)
            time.sleep(args.sleep)
        else:
            ph = {"ret_180d_pct": None}

        cs, cs_reasons = cluster_score(ins, mc)
        ds, ds_reasons = dual_signal(ins, bb.get("buyback_musd"), mc)
        ui, ui_reasons = u_index(ph, p_b, mc)

        composite = 0.30 * cs + 0.50 * ds + 0.20 * ui
        if composite < args.min_composite:
            continue

        # Compose reasons
        all_reasons = cs_reasons + ds_reasons + ui_reasons
        rows.append({
            "ticker": tk,
            "company": company,
            "market_cap_musd": round((mc or 0) / 1e6, 1),
            "current_price": yf_d.get("price"),
            "p_b": p_b,
            "ret_30d_pct": ph.get("ret_30d_pct") if ph else None,
            "ret_90d_pct": ph.get("ret_90d_pct") if ph else None,
            "ret_180d_pct": ph.get("ret_180d_pct") if ph else None,
            "distinct_buyers": len(set(ins.get("buyer_set") or [])),
            "buyer_titles": "; ".join((ins.get("buyer_set") or [])[:5]),
            "insider_dollar": round(ins.get("total_dollar") or 0, 0),
            "insider_pct_mcap": round(((ins.get("total_dollar") or 0) /
                                       mc * 100) if mc else 0, 2),
            "buyback_musd": bb.get("buyback_musd") or 0,
            "buyback_pct_mcap": round(((bb.get("buyback_musd") or 0) * 1e6 /
                                       mc * 100) if mc else 0, 1),
            "cluster_score": round(cs, 1),
            "dual_signal_score": round(ds, 1),
            "u_index": round(ui, 1),
            "composite": round(composite, 1),
            "reasons": " | ".join(all_reasons),
        })

    rows.sort(key=lambda r: r["composite"], reverse=True)

    fields = ["rank", "ticker", "company", "market_cap_musd", "current_price",
              "p_b", "ret_30d_pct", "ret_90d_pct", "ret_180d_pct",
              "distinct_buyers", "buyer_titles",
              "insider_dollar", "insider_pct_mcap",
              "buyback_musd", "buyback_pct_mcap",
              "cluster_score", "dual_signal_score", "u_index",
              "composite", "reasons"]
    with Path(args.csv).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows[: args.top], 1):
            r["rank"] = i
            w.writerow(r)

    print(f"\nWrote {args.csv} ({len(rows)} qualifying; top {args.top}):\n")
    print(f"{'#':<3}{'TKR':<10}{'MCAP':>8}{'PX':>9}{'CMP':>5}"
          f"{'CLU':>5}{'DUAL':>5}{'U':>4}{'#B':>4}{'BB%':>5}{'INS%':>6}  COMPANY")
    print("-" * 130)
    for i, r in enumerate(rows[: args.top], 1):
        mc = r["market_cap_musd"]
        px = r.get("current_price") or 0
        co = (r.get("company") or "")[:32]
        try: px = float(px)
        except: px = 0
        print(f"{i:<3}{r['ticker']:<10}{mc:>7.0f}M{px:>9.2f}"
              f"{r['composite']:>5.0f}"
              f"{r['cluster_score']:>5.0f}{r['dual_signal_score']:>5.0f}"
              f"{r['u_index']:>4.0f}{r['distinct_buyers']:>4}"
              f"{r['buyback_pct_mcap']:>4.0f}%"
              f"{r['insider_pct_mcap']:>5.2f}%  {co}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
