"""Point-in-time, survivorship-free backtest of the value floor the books rely on.

Every earlier validation used TODAY's names, so companies that failed or were
delisted since were missing -- that flatters anything that buys cheap, stressed
stocks. This test rebuilds the universe as it stood on each formation date:

  universe   every US-exchange symbol with a price in FMP's end-of-day bulk file
             on the formation date (so it includes names that later went
             bankrupt, were delisted or were acquired), with a balance sheet
             FILED before that date (FMP bulk statements carry the filing date)
  exit       the same bulk file ~6 months later; a name missing then is looked
             up individually and its LAST traded price used (a failure shows as
             the loss it was; an acquisition as its take-out price); names with
             no price at all after the formation date are reported separately and
             tested both ways (as -100% and as excluded)
  buckets    P/B (validated: price x shares / latest equity filed), deep value
             0.1-0.7x book, and deep value split by filing red flags in the prior
             12 months (reverse split; 8-K 3.01 delisting notice / 4.02 non-reliance /
             1.03 bankruptcy; NT late filing)
  measure    6-month return minus SPY; mean, median, hit rate; share of names
             delisted in the window; survivors-only vs everyone (= the bias)

Output: SURVIVORSHIP_BACKTEST.md, survivorship_backtest.json
"""

from __future__ import annotations

import csv
import glob
import json
import statistics as st
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
C = ROOT / "fmp_cache"
US_EX = {"NASDAQ", "NYSE", "AMEX", "NYSE American", "NYSEArca", "NYSE ARCA"}
FORMATION = ["2024-05-20", "2024-08-19", "2024-11-19", "2025-02-19", "2025-05-20", "2025-08-19",
             "2025-11-19", "2026-02-19"]
HOLD_DAYS = 182


def eod(d: str):
    """{symbol: adjClose} for the first trading day on/after d (FMP eod-bulk, cached)."""
    x = date.fromisoformat(d)
    for k in range(0, 6):
        dd = (x + timedelta(days=k)).isoformat()
        if (x + timedelta(days=k)).weekday() >= 5:
            continue
        try:
            rows = fmp.get_bulk_csv("eod-bulk", f"eodbulk_{dd}.csv", max_age_hours=10 ** 6, date=dd)
        except RuntimeError:
            rows = []
        px = {}
        for r in rows:
            try:
                v = float(r.get("adjClose") or r.get("close") or 0)
            except ValueError:
                continue
            if v > 0:
                px[r["symbol"]] = v
        if len(px) > 20000 and "SPY" in px and "AAPL" in px:     # a US holiday file holds only foreign listings
            return dd, px
    return None, {}


def exchanges():
    ex = {}
    for fn in glob.glob(str(C / "profile-bulk_part*.csv")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            fund = str(r.get("isEtf")).lower() == "true" or str(r.get("isFund")).lower() == "true"
            ex[r["symbol"]] = (r.get("exchange"), fund, r.get("companyName") or "")
    for r in json.loads((C / "delisted_companies.json").read_text()):
        ex.setdefault(r["symbol"], (r.get("exchange"), False, r.get("companyName") or ""))
    return ex


def statements():
    """{symbol: [(filingDate, equity, shares, cik)]} from the cached bulk balance-sheet / income files."""
    sh = {}
    for fn in glob.glob(str(C / "isbulk_*")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            try:
                v = float(r.get("weightedAverageShsOut") or r.get("weightedAverageShsOutDil") or 0)
            except ValueError:
                continue
            if v > 0 and r.get("date"):
                sh[(r["symbol"], r["date"][:10])] = v
    out = {}
    for fn in glob.glob(str(C / "bsbulk_*")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            if (r.get("reportedCurrency") or "USD") != "USD" or not r.get("filingDate"):
                continue
            try:
                eq = float(r.get("totalStockholdersEquity") or 0)
            except ValueError:
                continue
            s = sh.get((r["symbol"], (r.get("date") or "")[:10]))
            if s:
                out.setdefault(r["symbol"], []).append((r["filingDate"][:10], eq, s, r.get("cik")))
    for v in out.values():
        v.sort()
    return out


def last_price(sym, d0, d1):
    """Last traded price between d0 and d1 for a name missing from the exit file."""
    try:
        rows = fmp.get_json("historical-price-eod/light", symbol=sym, **{"from": d0, "to": d1})
    except Exception:
        return None
    rows = [r for r in rows or [] if r.get("price")]
    if not rows:
        return None
    r = max(rows, key=lambda r: r["date"])
    return r["date"], float(r["price"])


def red_flags(cik, d, fl_cache):
    """Filing red flags in the 12 months before d (EDGAR submissions; cached per CIK)."""
    if not cik:
        return set()
    import edgar_doc
    if cik not in fl_cache:
        try:
            fl_cache[cik] = edgar_doc.filings(cik, forms=("8-K", "8-K/A", "NT 10-K", "NT 10-Q"))
        except Exception:
            fl_cache[cik] = []
    lo = (date.fromisoformat(d) - timedelta(days=365)).isoformat()
    out = set()
    for form, acc, fd, items in fl_cache[cik]:
        if not (lo <= fd < d):
            continue
        if form.startswith("NT "):
            out.add("late filing")
        for it in str(items or "").split(","):
            k = {"3.01": "delisting notice", "4.02": "non-reliance", "1.03": "bankruptcy"}.get(it.strip())
            if k:
                out.add(k)
    return out


def splits_before():
    """{symbol: [dates of reverse splits]} 2023-2026 (FMP split calendar)."""
    out = {}
    d1 = date.today()
    while d1.isoformat() > "2023-01-01":
        d0 = d1 - timedelta(days=90)
        try:
            rows = fmp.get_json("splits-calendar", **{"from": d0.isoformat(), "to": d1.isoformat()})
        except Exception:
            rows = []
        for r in rows or []:
            if (r.get("numerator") or 0) < (r.get("denominator") or 0):
                out.setdefault(r["symbol"], []).append(r.get("date"))
        d1 = d0
    return out


def summ(xs):
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": st.mean(xs), "median": st.median(xs), "hit": sum(x > 0 for x in xs) / len(xs)}


def main() -> int:
    ex = exchanges()
    stm = statements()
    rs = splits_before()
    fl_cache = {}
    res = {}          # bucket -> list of (excess, delisted flag, missing flag)
    counts = []
    for f in FORMATION:
        d0, p0 = eod(f)
        d1, p1 = eod((date.fromisoformat(f) + timedelta(days=HOLD_DAYS)).isoformat())
        if not d0 or not d1 or d1 > date.today().isoformat():
            continue
        _, spy0 = d0, p0.get("SPY")
        spy1 = p1.get("SPY")
        spy = spy1 / spy0 - 1 if spy0 and spy1 else 0.0
        rows = []
        for s, px in p0.items():
            e = ex.get(s)
            if not e or e[0] not in US_EX or e[1] or px < 0.25 or "." in s:
                continue
            nm = e[2].lower()
            if any(k in nm for k in (" etf", " fund", " trust", "acquisition corp", " notes", "%", "preferred", "warrant")):
                continue
            hist = [x for x in stm.get(s, []) if x[0] <= d0]
            if not hist:
                continue
            fdate, eq, shares, cik = hist[-1]
            mcap = px * shares
            if mcap < 10e6:
                continue
            pb = mcap / eq if eq > 0 else None
            rows.append((s, px, pb, cik))
        miss = [s for s, *_ in rows if s not in p1]
        with ThreadPoolExecutor(8) as exr:
            lp = dict(zip(miss, exr.map(lambda s: last_price(s, d0, d1), miss)))
        cheap = [r for r in rows if r[2] is not None and 0.1 <= r[2] < 0.7]
        with ThreadPoolExecutor(6) as exr:
            flags = dict(zip([r[0] for r in cheap], exr.map(lambda r: red_flags(r[3], d0, fl_cache), cheap)))
        n_del = n_missing = 0
        for s, px, pb, cik in rows:
            if s in p1:
                ret, delisted, missing = p1[s] / px - 1, False, False
            elif lp.get(s):
                ret, delisted, missing = lp[s][1] / px - 1, True, False
                n_del += 1
            else:
                ret, delisted, missing = None, True, True
                n_missing += 1
            if ret is not None and ret > 20:
                continue                                  # split / data artefact
            buckets = ["all"]
            if pb is None:
                buckets.append("negative equity")
            elif pb < 0.1:
                buckets.append("P/B < 0.1 (data or wipe-out)")
            elif pb < 0.7:
                buckets.append("deep value 0.1-0.7x book")
                fl = set(flags.get(s) or set())
                if any(d0 > x >= (date.fromisoformat(d0) - timedelta(days=365)).isoformat() for x in rs.get(s, []) if x):
                    fl.add("reverse split")
                buckets.append("deep value + red flag" if fl else "deep value, no red flag")
                for k in fl:
                    buckets.append(f"deep value + {k}")
            elif pb < 1.0:
                buckets.append("0.7-1.0x book")
            elif pb < 3.0:
                buckets.append("1-3x book")
            else:
                buckets.append("> 3x book")
            for b in buckets:
                res.setdefault(b, []).append((None if ret is None else ret - spy, delisted, missing))
        counts.append((d0, d1, len(rows), n_del, n_missing))
        print(f"  {d0} -> {d1}: {len(rows)} names, {n_del} delisted in window (last price used), {n_missing} no price", flush=True)
    out = {}
    for b, xs in res.items():
        have = [x for x, _, m in xs if not m]
        surv = [x for x, dl, m in xs if not dl]
        worst = have + [-1.0 - 0 for _, _, m in xs if m]
        base = [x for x, _, m in res["all"] if not m]
        tt = None
        if b != "all" and len(have) >= 20:
            se = (st.pvariance(have) / len(have) + st.pvariance(base) / len(base)) ** 0.5
            tt = (st.mean(have) - st.mean(base)) / se if se else None
        out[b] = {"everyone": summ(have), "survivors_only": summ(surv), "missing_as_-100%": summ(worst), "t_vs_all": tt,
                  "delisted_share": sum(1 for _, dl, _ in xs if dl) / len(xs), "missing": sum(1 for *_, m in xs if m)}
    (ROOT / "survivorship_backtest.json").write_text(json.dumps({"windows": counts, "buckets": out}, indent=1))
    order = ["all", "> 3x book", "1-3x book", "0.7-1.0x book", "deep value 0.1-0.7x book", "deep value, no red flag",
             "deep value + red flag", "deep value + reverse split", "deep value + delisting notice", "deep value + late filing",
             "deep value + non-reliance", "deep value + bankruptcy", "P/B < 0.1 (data or wipe-out)", "negative equity"]
    f = lambda x: f"{x * 100:+.1f}%" if isinstance(x, (int, float)) else "—"
    L = [f"# Survivorship-free backtest ({date.today()})", "",
         f"{len(counts)} six-month windows ({counts[0][0]} to {counts[-1][1]}), US-exchange common stocks as they stood on "
         "each formation date — including every name that later failed, delisted or was acquired (FMP end-of-day bulk "
         "files + statements filed before the date). Return = 6-month total return minus SPY. 'Survivors only' drops the "
         "names that delisted in the window: the gap between the two columns is the survivorship bias earlier tests "
         "carried.", "",
         "| Bucket | n | Mean (everyone) | Median | Hit | t vs all | Mean (survivors only) | Bias | Delisted in window | "
         "Mean if no-price names = -100% |", "|---|---|---|---|---|---|---|---|---|---|"]
    for b in order + [k for k in out if k not in order]:
        if b not in out:
            continue
        o = out[b]
        e, s_, w = o["everyone"], o["survivors_only"], o["missing_as_-100%"]
        if e.get("n", 0) < 20:
            continue
        bias = (s_.get("mean") or 0) - (e.get("mean") or 0)
        L.append(f"| {b} | {e['n']} | {f(e.get('mean'))} | {f(e.get('median'))} | {e.get('hit', 0) * 100:.0f}% | "
                 f"{o['t_vs_all']:.1f} | " if o.get("t_vs_all") is not None else f"| {b} | {e['n']} | {f(e.get('mean'))} | "
                 f"{f(e.get('median'))} | {e.get('hit', 0) * 100:.0f}% | — | ")
        L[-1] += (f"{f(s_.get('mean'))} | {f(bias)} | {o['delisted_share'] * 100:.1f}% | {f(w.get('mean'))} |")
    L += ["", "**Reading it.** Means are skewed by a minority of large winners (medians are negative almost everywhere "
          "in a market that SPY led). Windows overlap and the same names recur, so t-stats overstate precision "
          "somewhat -- treat |t| < 3 as suggestive. Delisted names nearly all have a last traded price in FMP (acquired "
          "or faded before delisting), which is why the survivorship bias here is small; bankruptcies where trading "
          "stopped abruptly would show in the '-100%' column.",
          "", "Windows: " + "; ".join(f"{a}→{b}: {n} names, {d} delisted (last price used), {m} with no price"
                                      for a, b, n, d, m in counts)]
    (ROOT / "SURVIVORSHIP_BACKTEST.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
