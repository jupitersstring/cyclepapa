"""Recent-incentive-change asymmetry leg.

The thesis: a name where the board has *just* changed its incentive
structure (PSU plan amendment, 10b5-1 termination, fresh 13D, new
tender, fresh insider cluster) but the price hasn't moved is the
cleanest mis-priced asymmetry. The market hasn't yet incorporated
the new information.

Per ticker, find the most recent material incentive event in the
trailing N days and check whether the equity has priced it. Scores
highest where:
  * Event is recent (within 30-60 days)
  * Price has NOT moved up since the event date (or has moved down)
  * Drawdown from 52w high is still material (> 30%)

CLI:
  python3 recent_incentive_asymmetry.py                    # 120-day window
  python3 recent_incentive_asymmetry.py --window-days 30   # 30-day window

Output: recent_incentive_asymmetry.csv (window-tagged)
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


def load_proxy() -> dict:
    proxy = {}
    for fn in sorted(glob.glob(str(ROOT / "proxy_scan*.json"))):
        try: d = json.load(open(fn))
        except: continue
        rows = d if isinstance(d, list) else d.values()
        for r in rows:
            if isinstance(r, dict) and r.get("ticker"):
                tk = r["ticker"]
                if (tk not in proxy or
                    r.get("filing_date","") > proxy[tk].get("filing_date","")):
                    proxy[tk] = r
    return proxy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=120,
                    help="lookback window for material events (default 120)")
    ap.add_argument("--output", default=None,
                    help="output CSV path; default derived from window")
    args = ap.parse_args()
    window_days = args.window_days
    OUT = (Path(args.output) if args.output
            else ROOT / f"recent_incentive_asymmetry_{window_days}d.csv")

    today = datetime.now(timezone.utc).replace(tzinfo=None)
    proxy = load_proxy()
    yf = json.load(open(ROOT / "yfinance_quick.json"))
    tender = json.load(open(ROOT / "tender_scan.json"))
    c10 = json.load(open(ROOT / "cancel_10b5_1.json"))
    f4 = json.load(open(ROOT / "form4_buys.json"))

    # Optional auxiliary streams
    try:
        spec = list(csv.DictReader(
            open(ROOT / "special_situations_unified.csv")))
    except FileNotFoundError:
        spec = []
    try:
        activist = list(csv.DictReader(
            open(ROOT / "activist_13d.csv")))
    except FileNotFoundError:
        activist = []

    spec_by_tk = {}
    for r in spec:
        tk = r.get("ticker")
        if tk:
            d = parse_date(r.get("filing_date"))
            if d and (tk not in spec_by_tk
                       or d > spec_by_tk[tk][0]):
                spec_by_tk[tk] = (d, r.get("kind"), r.get("score"))
    activist_by_tk = {}
    for r in activist:
        tk = r.get("ticker")
        if tk:
            d = parse_date(r.get("filing_date"))
            if d and (tk not in activist_by_tk
                       or d > activist_by_tk[tk][0]):
                activist_by_tk[tk] = (d, r.get("filer"),
                                       r.get("is_known_activist"))

    universe = set(proxy) | set(yf) | set(tender) | set(c10) | set(f4)
    universe = {t for t in universe if not t.startswith("CIK")}

    rows = []
    for tk in universe:
        # Find latest material event date + label
        events = []

        # Proxy / DEF 14A -- only when PSU is non-trivial
        p = proxy.get(tk, {})
        if p:
            pd = parse_date(p.get("filing_date"))
            if pd and (p.get("psu_core") or p.get("cond_cats")
                       or (p.get("gov_score") or 0) >= 10):
                events.append((pd, "DEF14A_PSU",
                               f"PSU core {p.get('psu_core', 0)} gov {p.get('gov_score',0)}"))

        # Tender / 13E-3 (no date field per ticker; use anything reasonable)
        td = tender.get(tk, {})
        if isinstance(td, dict) and td.get("role") in (
                "SELF_TENDER", "TARGET") or td.get("has_13e3"):
            # tender file shape doesn't carry a date column directly;
            # fall through to special_situations / activist for dating
            pass

        # 10b5-1 events
        cd = c10.get(tk, {})
        if isinstance(cd, dict):
            for ev in (cd.get("events") or []):
                ed = parse_date(ev.get("filing_date"))
                if ed and ev.get("action") in ("TERMINATE", "CANCEL"):
                    events.append((ed, "10b5-1_TERM",
                                   f"{ev.get('role','?')} {ev.get('action')}"))
                elif ed and ev.get("action") == "ADOPT":
                    events.append((ed, "10b5-1_ADOPT",
                                   f"{ev.get('role','?')} {ev.get('action')}"))

        # F4 insider P-buy
        fd_ = f4.get(tk, {})
        if isinstance(fd_, dict):
            for fil in (fd_.get("filings") or []):
                ed = parse_date(fil.get("date"))
                if ed:
                    events.append((ed, "F4_PBUY",
                                   f"{fil.get('person','?')[:18]} "
                                   f"${fil.get('dollar',0)/1000:.0f}k"))

        # Special situations 8-K / Form 10
        if tk in spec_by_tk:
            ed, kind, score = spec_by_tk[tk]
            events.append((ed, kind or "SPEC_SIT",
                           f"score {score}"))

        # 13D activist
        if tk in activist_by_tk:
            ed, filer, is_known = activist_by_tk[tk]
            label = "13D_KNOWN_ACTIVIST" if is_known == "True" else "13D_FILER"
            events.append((ed, label, (filer or "")[:30]))

        if not events:
            continue

        # Latest event wins; collect distinct kinds in window
        events.sort(key=lambda e: -e[0].timestamp())
        latest = events[0]
        latest_date, latest_kind, latest_detail = latest
        days_since = (today - latest_date).days

        # Drop names whose latest event falls outside the window
        if days_since > window_days:
            continue

        # Count events in last min(60, window) and full window
        n_inner = sum(1 for e in events
                      if (today - e[0]).days <= min(60, window_days))
        n_window = sum(1 for e in events
                       if (today - e[0]).days <= window_days)

        # Get valuation overlay
        y = yf.get(tk, {}) or {}
        px = y.get("price")
        hi = y.get("fwk_high")
        lo = y.get("fwk_low")
        pb = y.get("p_b")
        mcap = y.get("mcap")
        sector = y.get("sector")
        dd_high = (1 - px / hi) * 100 if (px and hi and hi > 0) else None
        run_low = (px / lo - 1) * 100 if (px and lo and lo > 0) else None

        # Score: recent event + price stagnation
        score = 0.0
        reasons = []
        # Recency tiering scales with window
        if days_since <= max(7, window_days // 4):
            score += 25; reasons.append(f"event {days_since}d ago")
        elif days_since <= max(14, window_days // 2):
            score += 18; reasons.append(f"event {days_since}d ago")
        elif days_since <= max(21, (3 * window_days) // 4):
            score += 12; reasons.append(f"event {days_since}d ago")
        else:
            score += 6
            reasons.append(f"event {days_since}d ago")

        # Boost for event quality
        if latest_kind == "DEF14A_PSU":
            score += 10; reasons.append("PSU/gov in latest proxy")
        elif latest_kind == "10b5-1_TERM":
            score += 18; reasons.append("10b5-1 termination")
        elif latest_kind in ("13D_KNOWN_ACTIVIST",):
            score += 20; reasons.append("known activist 13D")
        elif latest_kind == "13D_FILER":
            score += 10; reasons.append("13D filed")
        elif latest_kind == "F4_PBUY":
            score += 12; reasons.append("insider P-buy")
        elif latest_kind in ("RESTRUCT_8K", "FORM_10_SPINOFF"):
            score += 15; reasons.append(f"{latest_kind}")

        # Boost for multi-event clustering
        inner_label = f"{min(60, window_days)}d"
        if n_inner >= 3:
            score += 12; reasons.append(f"{n_inner} events in {inner_label}")
        elif n_inner >= 2:
            score += 6; reasons.append(f"{n_inner} events in {inner_label}")

        # Price-stagnation kicker (KEY: market hasn't reacted)
        if dd_high is not None and dd_high > 60:
            score += 15; reasons.append(f"DD {dd_high:.0f}% (unpriced)")
        elif dd_high is not None and dd_high > 40:
            score += 10; reasons.append(f"DD {dd_high:.0f}%")
        elif dd_high is not None and dd_high > 20:
            score += 5
        if run_low is not None and run_low < 10:
            score += 8; reasons.append(f"only {run_low:.0f}% above 52w low")

        # P/B floor kicker
        if pb is not None and 0 < pb < 0.5:
            score += 12; reasons.append(f"P/B {pb:.2f}")
        elif pb is not None and 0 < pb < 1.0:
            score += 6

        rows.append({
            "ticker": tk,
            "score": round(score, 1),
            "latest_event_date": latest_date.strftime("%Y-%m-%d"),
            "days_since": days_since,
            "latest_event_kind": latest_kind,
            "latest_event_detail": latest_detail,
            "n_events_inner": n_inner,
            "n_events_window": n_window,
            "window_days": window_days,
            "all_event_kinds": ",".join(
                sorted({e[1] for e in events
                         if (today - e[0]).days <= window_days})),
            "mcap_M": round((mcap or 0) / 1e6, 0),
            "price": px,
            "p_b": pb,
            "drawdown_pct": round(dd_high, 0) if dd_high is not None else None,
            "above_52w_low_pct": round(run_low, 0) if run_low is not None else None,
            "sector": sector,
            "reasons": "; ".join(reasons),
        })

    rows.sort(key=lambda r: -r["score"])
    fieldnames = list(rows[0].keys())

    # Always write to the windowed filename
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows)")

    # When default 120-day run, ALSO write the canonical unwindowed
    # filename so existing consumers (full_universe_consensus.py)
    # keep working without churn.
    if window_days == 120 and not args.output:
        canon = ROOT / "recent_incentive_asymmetry.csv"
        with canon.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"  + canonical: {canon} ({len(rows)} rows)")

    print(f"\n=== TOP 30 by recent-incentive-change asymmetry ===")
    print(f"{'#':<3}{'TKR':<8}{'SCR':<5}{'AGE':<5}{'KIND':<22}"
          f"{'DD%':<5}{'P/B':<6}{'MCAP$M':<10}{'REASONS'}")
    for i, r in enumerate(rows[:30], 1):
        print(f"{i:<3}{r['ticker']:<8}{r['score']:<5}{r['days_since']:<5}"
              f"{r['latest_event_kind']:<22}"
              f"{(r['drawdown_pct'] or 0):<5.0f}"
              f"{(r['p_b'] or 0):<6.2f}"
              f"{r['mcap_M'] or 0:<10.0f}"
              f"{r['reasons'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
