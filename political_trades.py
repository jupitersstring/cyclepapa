"""Congressional (Senate + House) trading as an insider-style signal.

Members of Congress must disclose trades (STOCK Act PTRs) within 45 days.
The literature is mixed: aggregate congressional trading shows little edge,
but the signal concentrates in specific slices (purchases rather than sales,
larger size bands, smaller companies, clustered buying, members with a track
record). So this layer does NOT assume an edge. It:

 1. pulls every PTR since --since from FMP (senate-latest / house-latest),
 2. runs an EVENT STUDY from the DISCLOSURE date (the first day the trade is
    public, i.e. tradeable): 126-trading-day return vs SPY, sliced by
    direction, size band, market-cap bucket, owner, disclosure lag, asset
    type (stock vs options), clustering (>= 2 distinct members buying the
    same name within 90 days), and member track record (out of sample:
    a member's skill is measured only on trades disclosed BEFORE the trade
    being scored),
 3. derives slice weights from the measured excess returns (shrunk toward 0
    by sample size, so thin slices can't dominate) and scores each ticker's
    RECENT (--window days) disclosed activity with them.

Outputs: political_trades.json {"scores": {ticker: {score, ...}}, "meta": ...}
         POLITICAL_TRADES_VALIDATION.md (the event study).
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import time
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import fmp_client as fmp
import io_util

ROOT = Path("/home/user/cyclepapa")
CACHE = ROOT / "fmp_cache"
PX = CACHE / "px"
OUT = ROOT / "political_trades.json"
REPORT = ROOT / "POLITICAL_TRADES_VALIDATION.md"
H = 126                                   # ~6 months of trading days
SHRINK = 60                               # pseudo-observations toward zero


def fetch(chamber, since):
    cf = CACHE / f"congress_{chamber}.json"
    if cf.exists() and time.time() - cf.stat().st_mtime < 20 * 3600:
        return json.loads(cf.read_text())
    rows = []
    for page in range(0, 400):
        try:
            d = fmp.get_json(f"{chamber}-latest", page=page, limit=250) or []
        except RuntimeError:
            break
        if not d:
            break
        rows += d
        if min(r.get("disclosureDate") or "9" for r in d) < since:
            break
    cf.write_text(json.dumps(rows))
    return rows


def band(amount):
    nums = [int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", amount or "")]
    if not nums:
        return None, None
    lo = nums[0]
    mid = (nums[0] + nums[1]) / 2 if len(nums) > 1 else nums[0] * 1.5
    return lo, mid


def size_bucket(lo):
    if lo is None:
        return "?"
    return "<15k" if lo < 15000 else "15-50k" if lo < 50000 else "50-250k" if lo < 250000 else ">250k"


def cap_bucket(m):
    if not m:
        return "?"
    return "micro<300m" if m < 3e8 else "small<2b" if m < 2e9 else "mid<10b" if m < 1e10 else "large"


def closes(sym):
    PX.mkdir(parents=True, exist_ok=True)
    f = PX / (sym.replace("/", "_") + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < 5 * 86400:
        return json.loads(f.read_text())
    try:
        rows = fmp.daily_adjusted(sym, "2021-10-01")
    except RuntimeError:
        rows = []
    d = [[r[0], r[4]] for r in rows]
    f.write_text(json.dumps(d))
    return d


def px_at(px, d):
    i = bisect_right([r[0] for r in px], d) if px else 0
    return px[i - 1][1] if px and i > 0 else None


def fwd(px, spy, d):
    if not px or not spy:
        return None
    i = bisect_right([r[0] for r in px], d)
    j = bisect_right([r[0] for r in spy], d)
    if i + H >= len(px) or j + H >= len(spy) or px[i][1] <= 0:
        return None
    return (px[i + H][1] / px[i][1] - 1) - (spy[j + H][1] / spy[j][1] - 1)


def stats(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mean = sum(s) / n
    return {"n": n, "mean": mean, "median": s[n // 2],
            "hit": sum(1 for x in s if x > 0) / n,
            "shrunk": mean * n / (n + SHRINK)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2022-01-01")
    ap.add_argument("--window", type=int, default=180, help="scoring window (days of disclosures)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    prof = {}
    for fn in glob.glob(str(CACHE / "profile-bulk_part*.csv")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            prof[r["symbol"]] = r
    trades = []
    for ch in ("senate", "house"):
        rows = fetch(ch, args.since)
        print(f"{ch}: {len(rows)} disclosures")
        for r in rows:
            sym = (r.get("symbol") or "").strip().upper()
            at = (r.get("assetType") or "").lower()
            ty = (r.get("type") or "").lower()
            dd, td = (r.get("disclosureDate") or "")[:10], (r.get("transactionDate") or "")[:10]
            if not sym or sym not in prof or not dd or dd < args.since:
                continue
            if "stock" not in at and at not in ("", "equity"):
                continue                       # bonds, funds, crypto, etc.
            if prof[sym].get("isEtf") == "true" or prof[sym].get("isFund") == "true":
                continue
            side = "buy" if ty.startswith("purchase") else "sell" if ty.startswith("sale") else None
            if not side:
                continue
            lo, mid = band(r.get("amount"))
            try:
                lag = (datetime.strptime(dd, "%Y-%m-%d") - datetime.strptime(td, "%Y-%m-%d")).days
            except ValueError:
                lag = None
            trades.append({
                "sym": sym, "chamber": ch, "member": r.get("senateID") or f"{r.get('firstName')} {r.get('lastName')}",
                "name": f"{r.get('firstName', '')} {r.get('lastName', '')}".strip(),
                "owner": (r.get("owner") or "Self").strip() or "Self", "option": "option" in at,
                "side": side, "lo": lo, "mid": mid, "size": size_bucket(lo),
                "cap": cap_bucket(fmp.num(prof[sym].get("marketCap"))),
                "tdate": td, "ddate": dd, "lag": lag})
    # dedupe identical lines (same member/sym/side/date/band)
    seen, uniq = set(), []
    for t in trades:
        k = (t["member"], t["sym"], t["side"], t["tdate"], t["lo"], t["owner"])
        if k not in seen:
            seen.add(k); uniq.append(t)
    trades = sorted(uniq, key=lambda t: t["ddate"])
    syms = sorted({t["sym"] for t in trades})
    print(f"{len(trades)} equity trades in {len(syms)} listed names since {args.since}; pricing...")
    with ThreadPoolExecutor(args.workers) as ex:
        px = dict(zip(syms, ex.map(closes, syms)))
    spy = closes("SPY")
    for t in trades:
        p = px.get(t["sym"])
        t["x"] = fwd(p, spy, t["ddate"])                 # tradeable: from disclosure
        t["x_txn"] = fwd(p, spy, t["tdate"]) if t["tdate"] else None   # member's own timing
        # market cap AT DISCLOSURE (today's cap x price ratio) -- today's cap
        # would sort losers into "small" after the fact (survivorship bias)
        now, then = (p[-1][1] if p else None), px_at(p, t["ddate"])
        mc = fmp.num(prof[t["sym"]].get("marketCap"))
        t["cap"] = cap_bucket(mc * then / now if (mc and now and then) else None)

    # cluster flag: >= 2 distinct members buying the same name within 90 days (as of disclosure)
    by_sym = defaultdict(list)
    for t in trades:
        if t["side"] == "buy":
            by_sym[t["sym"]].append(t)
    for lst in by_sym.values():
        for t in lst:
            d0 = datetime.strptime(t["ddate"], "%Y-%m-%d")
            mem = {u["member"] for u in lst
                   if 0 <= (d0 - datetime.strptime(u["ddate"], "%Y-%m-%d")).days <= 90}
            t["cluster"] = len(mem) >= 2
    # member track record, strictly out of sample (only earlier-disclosed, already-resolved trades)
    hist = defaultdict(list)
    for t in trades:
        prior = [x for d, x in hist[t["member"]] if d <= (datetime.strptime(t["ddate"], "%Y-%m-%d") - timedelta(days=183)).strftime("%Y-%m-%d")]
        t["skill"] = (sum(prior) / len(prior)) if len(prior) >= 5 else None
        if t["x"] is not None:
            sgn = 1 if t["side"] == "buy" else -1
            hist[t["member"]].append((t["ddate"], sgn * t["x"]))

    res = [t for t in trades if t["x"] is not None]
    buys = [t for t in res if t["side"] == "buy"]
    sells = [t for t in res if t["side"] == "sell"]

    def slice_(name, fn, pool):
        g = defaultdict(list)
        for t in pool:
            g[fn(t)].append(t["x"])
        return name, {k: stats(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}

    txn = [t for t in trades if t["x_txn"] is not None]
    g_txn = defaultdict(list)
    for t in txn:
        g_txn[t["side"]].append(t["x_txn"])
    slices = [("direction, from TRANSACTION date (member's own timing, not tradeable)",
               {k: stats(v) for k, v in sorted(g_txn.items())}),
              slice_("direction", lambda t: t["side"], res),
              slice_("buy size band", lambda t: t["size"], buys),
              slice_("buy market cap (at disclosure)", lambda t: t["cap"], buys),
              slice_("buy owner", lambda t: t["owner"].split()[0], buys),
              slice_("buy asset", lambda t: "option" if t["option"] else "stock", buys),
              slice_("buy clustered", lambda t: "cluster>=2 members" if t.get("cluster") else "single member", buys),
              slice_("buy disclosure lag", lambda t: "?" if t["lag"] is None else "<=15d" if t["lag"] <= 15 else "16-45d" if t["lag"] <= 45 else ">45d (late)", buys),
              slice_("buy member track record (OOS)", lambda t: "no record" if t["skill"] is None else "skilled (>+2%)" if t["skill"] > 0.02 else "unskilled", buys),
              slice_("sell size band", lambda t: t["size"], sells),
              slice_("sell market cap", lambda t: t["cap"], sells)]
    S = dict(slices)

    # weights = shrunk mean excess return of each slice, relative to all buys
    all_buy = stats([t["x"] for t in buys])["mean"] if buys else 0.0

    def w(sl, key):
        s = S.get(sl, {}).get(key)
        return (s["shrunk"] - all_buy * s["n"] / (s["n"] + SHRINK)) if s else 0.0

    buy_edge = (S["direction"].get("buy") or {}).get("shrunk", 0.0)
    sell_edge = (S["direction"].get("sell") or {}).get("shrunk", 0.0)

    def trade_edge(t):
        """Expected 6-month excess return implied by this trade's slices."""
        if t["side"] == "buy":
            e = buy_edge + w("buy size band", t["size"]) + w("buy market cap (at disclosure)", t["cap"]) \
                + w("buy asset", "option" if t["option"] else "stock") \
                + w("buy clustered", "cluster>=2 members" if t.get("cluster") else "single member") \
                + w("buy member track record (OOS)", "no record" if t["skill"] is None
                    else "skilled (>+2%)" if t["skill"] > 0.02 else "unskilled")
        else:
            e = sell_edge + w("sell size band", t["size"]) + w("sell market cap", t["cap"])
        return e

    # score recent disclosures
    cutoff = (date.today() - timedelta(days=args.window)).isoformat()
    per = defaultdict(lambda: {"score": 0.0, "buys": 0, "sells": 0, "members": set(),
                               "buy_min_usd": 0, "last": "", "trades": []})
    for t in trades:
        if t["ddate"] < cutoff:
            continue
        age = (date.today() - datetime.strptime(t["ddate"], "%Y-%m-%d").date()).days
        rec = max(0.2, 1 - age / args.window)
        e = trade_edge(t)
        p = per[t["sym"]]
        p["score"] += e * rec * 100            # in excess-return percentage points
        p["buys" if t["side"] == "buy" else "sells"] += 1
        if t["side"] == "buy":
            p["members"].add(t["name"]); p["buy_min_usd"] += t["lo"] or 0
        p["last"] = max(p["last"], t["ddate"])
        p["trades"].append(f"{t['ddate']} {t['name']} ({t['chamber'][0].upper()}, {t['owner']}) "
                           f"{t['side']} {t['size']}{' opt' if t['option'] else ''}")
    scores = {}
    for s, p in per.items():
        scores[s] = {"score": round(p["score"], 2), "buys": p["buys"], "sells": p["sells"],
                     "n_buy_members": len(p["members"]), "buy_members": sorted(p["members"])[:6],
                     "buy_min_usd": p["buy_min_usd"], "last_disclosure": p["last"],
                     "name": (prof.get(s) or {}).get("companyName"),
                     "recent": p["trades"][-5:]}
    io_util.write_json(OUT, {"scores": scores, "meta": {
        "generated": date.today().isoformat(), "since": args.since, "window_days": args.window,
        "n_trades": len(trades), "n_resolved": len(res),
        "buy_edge_6m": buy_edge, "sell_edge_6m": sell_edge}})

    # report
    L = ["# Congressional trades -- event study", "",
         f"Generated {date.today()} by `political_trades.py`. {len(trades)} equity PTR trades "
         f"(Senate + House) in {len(syms)} listed names disclosed since {args.since}; "
         f"{len(res)} with a full {H}-trading-day forward window.", "",
         "Return = excess vs SPY over 126 trading days from the first close AFTER the "
         "disclosure date (when the trade becomes public). `shrunk` = mean x n/(n+60), the "
         "weight used for scoring. Market-cap buckets use today's cap (a survivorship caveat).", ""]
    for name, tab in slices:
        L += [f"## {name}", "", "| slice | n | mean | median | hit rate | shrunk |", "|---|---|---|---|---|---|"]
        for k, s in tab.items():
            if s:
                L.append(f"| {k} | {s['n']} | {s['mean']:+.1%} | {s['median']:+.1%} | {s['hit']:.0%} | {s['shrunk']:+.2%} |")
        L.append("")
    top = sorted(scores.items(), key=lambda kv: -kv[1]["score"])[:25]
    L += ["## Top current names (last %d days of disclosures)" % args.window, "",
          "| ticker | score | buys | sells | buying members | last |", "|---|---|---|---|---|---|"]
    for s, v in top:
        L.append(f"| {s} | {v['score']:+.1f} | {v['buys']} | {v['sells']} | {', '.join(v['buy_members'][:3])} | {v['last_disclosure']} |")
    REPORT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT.name} ({len(scores)} names) and {REPORT.name}")
    for name, tab in slices[:9]:
        print(name, {k: (s["n"], f"{s['mean']:+.1%}", f"{s['hit']:.0%}") for k, s in tab.items() if s})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
