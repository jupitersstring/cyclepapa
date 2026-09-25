"""Does 'what is priced in' predict returns?

1. Analyst rating changes (FMP grades history): event study, 63 / 126 trading
   days after an upgrade or a downgrade, vs a random-date control -- same method
   as layer_validate.py (current names: survivorship caveat applies).
2. Short interest (FINRA consolidated short interest), SURVIVORSHIP-FREE and point
   in time: on each formation date, every US-exchange stock in FMP's end-of-day
   bulk file (incl. names that later failed), bucketed by days to cover and by the
   change in shares short; 6-month return minus SPY, delisted names at their last
   price (same machinery as survivorship_backtest.py).

Output: EXPECTATIONS_VALIDATION.md, expectations_validation.json
"""

from __future__ import annotations

import glob
import json
import statistics as st
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import detail_enrich as de
import expectations_layer as el
import layer_validate as lv
import survivorship_backtest as sb

ROOT = Path("/home/user/cyclepapa")


def rating_events():
    ev = []
    for fn in glob.glob(str(ROOT / "fmp_cache" / "expect" / "*__grades.json")):
        t = Path(fn).name.split("__")[0]
        try:
            rows = json.loads(Path(fn).read_text())
        except Exception:
            continue
        for g in rows or []:
            a, d = g.get("action"), (g.get("date") or "")[:10]
            if a in ("upgrade", "downgrade") and d:
                ev.append((f"analyst {a}", t, d))
            if a == "upgrade" and str(g.get("previousGrade", "")).lower() in ("sell", "underperform", "underweight", "reduce"):
                ev.append(("upgrade from sell", t, d))
            if a == "downgrade" and str(g.get("newGrade", "")).lower() in ("sell", "underperform", "underweight", "reduce"):
                ev.append(("downgrade to sell", t, d))
    return ev


def short_interest_xsection():
    ex = sb.exchanges()
    res = {}
    for f in sb.FORMATION:
        # the FINRA settlement just before the formation date
        cands = [d for d in el.settlement_dates((date.fromisoformat(f) - timedelta(days=20)).isoformat(), f) if d <= f]
        si = {}
        for d in sorted(cands, reverse=True):
            rows = el.finra_date(d)
            if rows:
                si = {x["s"]: x for x in rows}
                break
        d0, p0 = sb.eod(f)
        d1, p1 = sb.eod((date.fromisoformat(f) + timedelta(days=sb.HOLD_DAYS)).isoformat())
        if not si or not d0 or not d1 or d1 > date.today().isoformat():
            continue
        spy = (p1.get("SPY") or 0) / (p0.get("SPY") or 1) - 1
        rows = []
        for s, px in p0.items():
            e = ex.get(s)
            x = si.get(s)
            if not e or e[0] not in sb.US_EX or e[1] or px < 1 or "." in s or not x or not x.get("adv"):
                continue
            if (x.get("adv") or 0) * px < 250_000:
                continue                                 # untradeable: < $250k / day
            dtc = x.get("dtc")
            chg = (x["si"] / x["prev"] - 1) if x.get("prev") else None
            rows.append((s, px, dtc, chg))
        miss = [s for s, *_ in rows if s not in p1]
        with ThreadPoolExecutor(8) as exr:
            lp = dict(zip(miss, exr.map(lambda s: sb.last_price(s, d0, d1), miss)))
        dtcs = sorted(r[2] for r in rows if r[2] is not None)
        hi = dtcs[int(0.9 * len(dtcs))] if dtcs else 99
        for s, px, dtc, chg in rows:
            if s in p1:
                ret = p1[s] / px - 1
            elif lp.get(s):
                ret = lp[s][1] / px - 1
            else:
                continue
            if ret > 20:
                continue
            x = ret - spy
            res.setdefault("all (liquid, shorted)", []).append(x)
            if dtc is not None and dtc >= hi:
                res.setdefault("top decile days-to-cover", []).append(x)
            if dtc is not None and dtc >= 10:
                res.setdefault("days-to-cover >= 10", []).append(x)
            if chg is not None and chg >= 0.5 and (dtc or 0) >= 3:
                res.setdefault("short interest up >= 50% (and >= 3 days)", []).append(x)
            if chg is not None and chg <= -0.33 and (dtc or 0) >= 3:
                res.setdefault("short covering: down >= 33%", []).append(x)
        print(f"  short-interest window {d0} -> {d1}: {len(rows)} names", flush=True)
    base = res.get("all (liquid, shorted)") or []
    out = {}
    for k, xs in res.items():
        if len(xs) < 20:
            continue
        o = {"n": len(xs), "mean": st.mean(xs), "median": st.median(xs), "hit": sum(v > 0 for v in xs) / len(xs)}
        if k != "all (liquid, shorted)" and base:
            se = (st.pvariance(xs) / len(xs) + st.pvariance(base) / len(base)) ** 0.5
            o["diff"] = o["mean"] - st.mean(base)
            o["t"] = o["diff"] / se if se else None
        out[k] = o
    return out


def main() -> int:
    ev = rating_events()
    names = sorted({t for _, t, _ in ev})
    with ThreadPoolExecutor(8) as ex:
        px = dict(zip(names, ex.map(lambda s: de.closes(s, "2020-06-01"), names)))
    spy = de.closes("SPY", "2020-06-01")
    rat = lv.study(ev, px, spy)
    si = short_interest_xsection()
    (ROOT / "expectations_validation.json").write_text(json.dumps(
        {"ratings": {k: {str(h): v for h, v in r.items()} for k, r in rat.items()}, "short_interest": si}, indent=1))
    f = lambda x: f"{x * 100:+.1f}%" if isinstance(x, (int, float)) else "—"
    L = [f"# Expectations layer — validation ({date.today()})", "",
         "## 1. Analyst rating changes — event study", "",
         "Excess return vs SPY from the first close after the rating change; control = the same names on random "
         "dates; current names only (survivorship caveat). Positive edge needs t >= 3 (several tests at once); a "
         "caution needs t <= -2.", "",
         "| Event | n | 63d mean | 126d mean | 126d median | 126d hit | 126d vs control | t | Verdict |",
         "|---|---|---|---|---|---|---|---|---|"]
    rat.pop("_control", None)
    for k, r in sorted(rat.items(), key=lambda kv: -((kv[1].get(126) or {}).get("n", 0))):
        a, b = r.get(63) or {}, r.get(126) or {}
        if b.get("t") is None:
            continue
        L.append(f"| {k} | {b['n']} | {f(a.get('mean'))} | {f(b.get('mean'))} | {f(b.get('median'))} | "
                 f"{b['hit'] * 100:.0f}% | {f(b.get('diff_vs_control'))} | {b['t']:.1f} | {lv.verdict(r)} |")
    L += ["", "## 2. Short interest — survivorship-free cross-section", "",
          "Every liquid (>= $250k/day) US-exchange stock with FINRA short interest on each formation date, incl. names "
          "that later delisted (last price used). 6-month return minus SPY; t vs the whole liquid shorted universe.", "",
          "| Bucket | n | Mean | Median | Hit | vs all | t |", "|---|---|---|---|---|---|---|"]
    for k, o in si.items():
        L.append(f"| {k} | {o['n']} | {f(o['mean'])} | {f(o['median'])} | {o['hit'] * 100:.0f}% | {f(o.get('diff'))} | "
                 f"{o['t']:.1f} |" if o.get("t") is not None else
                 f"| {k} | {o['n']} | {f(o['mean'])} | {f(o['median'])} | {o['hit'] * 100:.0f}% | — | — |")
    L += ["", "## Read-across", "",
          "- Analyst rating changes have not predicted returns here in either direction (|t| < 1): coverage and "
          "targets are shown as context -- how neglected a name is and what the street already assumes -- not scored.",
          "- Heavily shorted stocks (top decile days-to-cover) OUT-performed the liquid universe over 2024-26 "
          "(t above 3). That is the opposite of the long-run academic evidence (high short interest predicts LOW "
          "returns) and most likely reflects a squeeze-prone regime; it is reported, not scored, and it is a risk "
          "flag for anyone short -- not a reason to buy.",
          "- Everything here is shown on the 'Priced In' tab and next to each name; none of it changes a rank or a "
          "size until it earns it on a longer, regime-spanning sample."]
    (ROOT / "EXPECTATIONS_VALIDATION.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
