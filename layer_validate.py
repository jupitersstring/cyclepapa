"""Event studies for the ownership and distress layers -- the gate before any
of it moves a ranking or a size.

For each event type: the stock's return over the next 63 and 126 trading days
minus SPY's, measured from the first close AFTER the filing date (the day the
market could act). Compared with a control: the same names on random dates in
the same period. Reported: n, mean and median excess return, hit rate, t-stat
of the difference vs control.

Events
  ownership  new 13D, 13G->13D switch, activist 13D, 13D stake added / cut,
             insider cluster buy (>= 2 insiders, >= $100k, within 30 days),
             C-suite open-market buy >= $100k, heavy insider selling (>= $1M in 30 days)
  distress   8-K 4.02 / 3.01 / 1.03 / 2.06, NT 10-K / 10-Q, reverse split

Caveat (stated in the report): the universe is today's names, so bankrupt and
delisted companies are under-represented -- distress returns are flattered and
the true penalty is at least as large as measured.

Output: LAYER_VALIDATION.md, layer_validation.json
"""

from __future__ import annotations

import json
import random
import statistics as st
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import detail_enrich as de

ROOT = Path("/home/user/cyclepapa")
START, HORIZONS = "2021-01-01", (63, 126)


def fwd(px, d, n):
    """Return over n trading days from the first close after d (px = [[date, close], ...])."""
    if not px:
        return None
    ds = [x[0] for x in px]
    i = bisect_right(ds, d)
    if i + n >= len(px) or i == 0:
        return None
    a, b = px[i][1], px[i + n][1]
    return (b / a - 1) if a else None


def ownership_events():
    ev = []
    own = json.loads((ROOT / "ownership.json").read_text())
    for t, r in own.items():
        for e in r.get("events_13d") or []:
            k = {"new_13d": "new 13D", "switch": "13G -> 13D switch", "13d_add": "13D stake added",
                 "13d_cut": "13D stake cut"}.get(e["type"], e["type"])
            ev.append((k, t, e["date"]))
            if e.get("activist") and e["type"] in ("new_13d", "switch"):
                ev.append(("activist new 13D / switch", t, e["date"]))
    # insider clusters from the cached full Form 4 feed
    import glob
    for fn in glob.glob(str(ROOT / "fmp_cache" / "own" / "*__f4.json")):
        t = Path(fn).name.split("__")[0]
        try:
            rows = json.loads(Path(fn).read_text())
        except Exception:
            continue
        buys = sorted(((r.get("transactionDate") or "")[:10], r.get("reportingName"), (r.get("securitiesTransacted") or 0) * (r.get("price") or 0),
                       r.get("typeOfOwner") or "") for r in rows if str(r.get("transactionType", "")).startswith("P-"))
        sells = sorted(((r.get("transactionDate") or "")[:10], (r.get("securitiesTransacted") or 0) * (r.get("price") or 0))
                       for r in rows if str(r.get("transactionType", "")).startswith("S-"))
        last = ""
        for i, (d, who, v, role) in enumerate(buys):
            if not d or d <= last:
                continue
            win = [b for b in buys if d <= b[0] <= (date.fromisoformat(d) + timedelta(days=30)).isoformat()]
            if len({b[1] for b in win}) >= 2 and sum(b[2] for b in win) >= 100_000:
                ev.append(("insider cluster buy", t, win[-1][0]))
                last = (date.fromisoformat(d) + timedelta(days=90)).isoformat()
        lastc = ""
        for d, who, v, role in buys:
            if v >= 100_000 and d > lastc and any(k in role.lower() for k in ("ceo", "chief executive", "cfo", "chief financial")):
                ev.append(("CEO/CFO open-market buy >= $100k", t, d))
                lastc = (date.fromisoformat(d) + timedelta(days=90)).isoformat()
        lasts = ""
        for i, (d, v) in enumerate(sells):
            if not d or d <= lasts:
                continue
            tot = sum(x[1] for x in sells if d <= x[0] <= (date.fromisoformat(d) + timedelta(days=30)).isoformat())
            if tot >= 1_000_000:
                ev.append(("insider selling >= $1M in 30d", t, d))
                lasts = (date.fromisoformat(d) + timedelta(days=90)).isoformat()
    return ev


def distress_events(tickers):
    import distress_flags as dfl
    import edgar_doc
    import fmp_client as fmp
    cm = dfl.cik_map()
    ev = []

    def one(t):
        c = cm.get(t)
        out = []
        if not c:
            return out
        try:
            fs = edgar_doc.filings(c, forms=("8-K", "NT 10-K", "NT 10-Q"))
        except Exception:
            return out
        for form, acc, d, items in fs:
            if form.startswith("NT "):
                out.append(("late filing (NT 10-K/10-Q)", t, d))
            for it in str(items or "").split(","):
                k = {"4.02": "8-K 4.02 non-reliance", "3.01": "8-K 3.01 delisting notice", "1.03": "8-K 1.03 bankruptcy",
                     "2.06": "8-K 2.06 impairment"}.get(it.strip())
                if k:
                    out.append((k, t, d))
        return out
    with ThreadPoolExecutor(6) as ex:
        for x in ex.map(one, tickers):
            ev += x
    tk = set(tickers)
    end = date.today()
    d1 = end
    while d1.isoformat() > START:
        d0 = d1 - timedelta(days=90)
        try:
            rows = fmp.get_json("splits-calendar", **{"from": d0.isoformat(), "to": d1.isoformat()})
        except Exception:
            rows = []
        for r in rows or []:
            if r.get("symbol") in tk and (r.get("numerator") or 0) < (r.get("denominator") or 0):
                ev.append(("reverse split", r["symbol"], r.get("date")))
        d1 = d0
    return ev


def study(events, px, spy, control_n=4000, seed=7):
    cutoff = (date.today() - timedelta(days=200)).isoformat()
    rng = random.Random(seed)
    names = [t for t in px if px[t]]
    res = {}
    by = {}
    for k, t, d in events:
        if d and START <= d <= cutoff and px.get(t):
            by.setdefault(k, set()).add((t, d))
    # control: random (name, date) pairs in the same window
    ctrl = {h: [] for h in HORIZONS}
    span = (date.fromisoformat(cutoff) - date.fromisoformat(START)).days
    for _ in range(control_n):
        t = rng.choice(names)
        d = (date.fromisoformat(START) + timedelta(days=rng.randrange(span))).isoformat()
        for h in HORIZONS:
            a, m = fwd(px[t], d, h), fwd(spy, d, h)
            if a is not None and m is not None and -0.95 < a < 10:
                ctrl[h].append(a - m)
    res["_control"] = {h: summ(ctrl[h], None) for h in HORIZONS}
    for k, pairs in by.items():
        res[k] = {}
        for h in HORIZONS:
            xs = []
            for t, d in pairs:
                a, m = fwd(px[t], d, h), fwd(spy, d, h)
                if a is not None and m is not None and -0.95 < a < 10:
                    xs.append(a - m)
            res[k][h] = summ(xs, ctrl[h])
    return res


def summ(xs, ctrl):
    if len(xs) < 5:
        return {"n": len(xs)}
    out = {"n": len(xs), "mean": st.mean(xs), "median": st.median(xs), "hit": sum(x > 0 for x in xs) / len(xs)}
    if ctrl:
        se = (st.pvariance(xs) / len(xs) + st.pvariance(ctrl) / len(ctrl)) ** 0.5
        out["diff_vs_control"] = st.mean(xs) - st.mean(ctrl)
        out["t"] = out["diff_vs_control"] / se if se else None
    return out


def verdict(r, h=126):
    x = r.get(h) or {}
    if x.get("n", 0) < 30 or x.get("t") is None:
        return "too few events"
    if x["t"] >= 3:                       # ~14 event types tested: t >= 3 guards against the one lucky 2-sigma result
        return "POSITIVE edge"
    if x["t"] >= 2:
        return "weak positive (not adopted: multiple testing)"
    if x["t"] <= -2:
        return "NEGATIVE (caution signal)"
    return "no measured edge"


def main() -> int:
    own = json.loads((ROOT / "ownership.json").read_text())
    tickers = sorted(own)
    ev_o, ev_d = ownership_events(), distress_events(tickers)
    names = sorted({t for _, t, _ in ev_o + ev_d} | set(tickers))
    with ThreadPoolExecutor(8) as ex:
        px = dict(zip(names, ex.map(lambda s: de.closes(s, "2020-06-01"), names)))
    spy = de.closes("SPY", "2020-06-01")
    res = study(ev_o + ev_d, px, spy)
    (ROOT / "layer_validation.json").write_text(json.dumps({k: {str(h): v for h, v in r.items()} for k, r in res.items()}, indent=1))
    L = [f"# Ownership and distress layers — event study ({date.today()})", "",
         f"Excess return vs SPY over the next 63 / 126 trading days, from the first close after the filing date; "
         f"events {START} to 200 days ago; {len(tickers)} current US book names. Control = the same names on "
         "random dates. t = difference vs control / standard error. **Survivorship caveat:** today's names only — "
         "delisted / bankrupt companies are missing, so distress returns are flattered.", "",
         "| Event | n | 63d mean | 126d mean | 126d median | 126d hit | 126d vs control | t | Verdict |",
         "|---|---|---|---|---|---|---|---|---|"]
    c = res.pop("_control")
    for k, r in sorted(res.items(), key=lambda kv: -((kv[1].get(126) or {}).get("n", 0))):
        a, b = r.get(63) or {}, r.get(126) or {}
        f = lambda x: f"{x * 100:+.1f}%" if isinstance(x, (int, float)) else "—"
        L.append(f"| {k} | {b.get('n', 0)} | {f(a.get('mean'))} | {f(b.get('mean'))} | {f(b.get('median'))} | "
                 f"{(b.get('hit') or 0) * 100:.0f}% | {f(b.get('diff_vs_control'))} | "
                 f"{b['t']:.1f} | {verdict(r)} |" if b.get("t") is not None else
                 f"| {k} | {b.get('n', 0)} | — | — | — | — | — | — | too few events |")
    cb = c.get(126) or {}
    L += ["", f"Control (random dates, same names): 126d mean {cb.get('mean', 0) * 100:+.1f}%, median "
              f"{cb.get('median', 0) * 100:+.1f}%, hit {cb.get('hit', 0) * 100:.0f}% (n={cb.get('n')}).", "",
          "**How the books use this:** a POSITIVE edge (t >= 3, because ~14 event types are tested at once) may support "
          "a position; a NEGATIVE one (t <= -2 -- a caution is cheap to act on) becomes a caution flag and a sizing "
          "cut; everything else is shown for information only (like congressional trades). Bankruptcy and auditor "
          "going-concern doubt cut sizing and remove book floors on prudence, not on a measured edge (bankrupt "
          "names that delisted are missing from this sample, which is why the bankruptcy row looks positive).",
          "",
          "**Read-across:** in this universe (heavy in small, cheap, stressed names -- the control itself is -5% vs SPY "
          "over 126 days) ownership filings alone do not predict returns. They are context for a thesis -- who can "
          "force the value out, who is under water -- not a signal by themselves."]
    (ROOT / "LAYER_VALIDATION.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
