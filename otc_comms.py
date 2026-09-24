"""OTC management-communications intent -- the transcript engine, extended to
where OTC companies actually talk.

Most OTC companies never hold an earnings call. Their intent to act on a
discount shows up instead in:
  * press releases (FMP press-release feed; full text fetched from the wire
    when the headline/lead touches a capital action, a strategic topic or a
    shareholder letter),
  * SEC 8-K EX-99 exhibits (results releases, shareholder letters, buyback /
    tender announcements) for SEC-reporting OTC issuers,
  * earnings calls where they exist (foreign ordinaries trading as F-shares,
    larger domestic OTC names) -- the FMP transcript store.

Universe = the OTC book's own: US-domiciled OTC common (liquidity-tiered,
secondary lines removed) plus foreign OTC lines at P/B <= 1.2 and mcap >=
$50M (transcripts / press releases only).

Every document goes through call_intent's clause engine (commitment ladder,
agency, negation scope, specificity, new-vs-routine aspect); press releases
and letters are parsed in document mode (company voice; About-us, safe
harbour, contacts and table rows stripped; shareholder letters flagged and
weighted x1.2). Per company, the trailing-12-month signal is aggregated with
recency weights, NOVELTY is measured against the prior 12 months, and the
SIZE of any buyback / tender is expressed as % of market cap (the single most
informative number in micro-cap capital return).

Validation: each dated document is labelled with what the company then did
(share count down >= 2% / dividend step-up over the next two fiscal quarters,
FMP bulk statements) -> OTC_INTENT_VALIDATION.md.

Output: otc_intent.json {ticker: {score, tier, families, size_pct, novelty,
        docs, evidence[...]}}.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

import call_intent as ci
import fmp_client as fmp

ROOT = Path("/home/user/cyclepapa")
STORE = ROOT / "fmp_cache" / "comms"
OUT = ROOT / "otc_intent.json"
REPORT = ROOT / "OTC_INTENT_VALIDATION.md"
TODAY = date.today()
WIRE_UA = {"User-Agent": "Mozilla/5.0 (cyclepapa research)"}
KIND_W = {"LETTER": 1.2, "CALL": 1.0, "PR": 1.0, "EX99": 1.0}
TOPIC = re.compile(r"repurchas|buy\s?back|tender|dividend|return\w* capital|strategic|"
                   r"alternatives|sale of|divest|spin|merger|acqui|letter|shareholder|"
                   r"stockholder|going private|deregist|delist|reverse split|liquidat|"
                   r"undervalu|special", re.I)

_dead_lock = threading.Lock()
_dead: dict[str, int] = {}                          # wire domain -> failures (circuit breaker)


def wire_get(url):
    dom = re.sub(r"^https?://(?:www\.)?([^/]+).*$", r"\1", url)
    if _dead.get(dom, 0) >= 3:
        return None
    try:
        r = requests.get(url, headers=WIRE_UA, timeout=6)
        if r.status_code == 200:
            return r.text
    except requests.RequestException:
        pass
    with _dead_lock:
        _dead[dom] = _dead.get(dom, 0) + 1
    return None


_sec_lock = threading.Lock()
_sec_last = [0.0]


def sec_get(url):
    import edgar
    with _sec_lock:                                 # SEC fair access: <= ~8 req/s
        wait = 0.13 - (time.time() - _sec_last[0])
        if wait > 0:
            time.sleep(wait)
        _sec_last[0] = time.time()
    return edgar._get(url)


def html_text(h):
    h = re.sub(r"(?is)<(script|style|head|table)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n\n", h)
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    return "\n\n".join(" ".join(p.split()) for p in re.split(r"\n\s*\n", t) if p.strip())


# ---------------------------------------------------------------- universe
def universe():
    import build_otc_book as ob
    q = json.loads((ROOT / "fmp_quotes.json").read_text())
    otc = {k: v for k, v in q.items() if v.get("otc")}
    exch = {ob._norm(v.get("name")) for v in q.values() if not v.get("otc")}
    otc = {k: v for k, v in otc.items()
           if not ((len(k) == 5 and k[4] in ob._SECONDARY_5TH) or ob._norm(v.get("name")) in exch)}
    us = {k: v for k, v in otc.items() if v.get("country") == "US" and ob.tier(v) and ob.is_common(v)}
    fx = {k: v for k, v in otc.items() if v.get("country") not in (None, "US") and ob.tier(v)
          and ob.is_common(v) and (v.get("mcap") or 0) >= 5e7 and v.get("p_b") and 0 < v["p_b"] <= 1.2}
    return us, fx, q


# ---------------------------------------------------------------- fetch
def fetch_pr(sym, since):
    d = STORE / sym
    d.mkdir(parents=True, exist_ok=True)
    f = d / "pr.json"
    if f.exists() and time.time() - f.stat().st_mtime < 3 * 86400:
        return json.loads(f.read_text())
    try:
        rows = fmp.get_json("news/press-releases", symbols=sym, limit=100, **{"from": since}) or []
    except RuntimeError:
        rows = []
    old = {r["url"]: r for r in (json.loads(f.read_text()) if f.exists() else []) if r.get("url")}
    out = []
    for r in rows:
        prev = old.get(r.get("url"))
        if prev and prev.get("full"):
            out.append(prev); continue
        rec = {k: r.get(k) for k in ("publishedDate", "title", "text", "url", "site")}
        if TOPIC.search((r.get("title") or "") + " " + (r.get("text") or "")) and r.get("url"):
            page = wire_get(r["url"])
            if page:
                body = html_text(page)
                lead = (r.get("text") or "")[:60]
                i = body.find(lead[:40]) if lead else -1
                rec["full"] = body[i:i + 20000] if i >= 0 else body[:20000]
        out.append(rec)
    f.write_text(json.dumps(out))
    return out


EX99 = re.compile(r"ex[-_]?99|exhibit[-_]?99|dex99|ex991|ex992", re.I)


def fetch_8k(sym, cik, since):
    d = STORE / sym
    d.mkdir(parents=True, exist_ok=True)
    meta_f = d / "8k_index.json"
    if meta_f.exists() and time.time() - meta_f.stat().st_mtime < 5 * 86400:
        return json.loads(meta_f.read_text())
    try:
        sub = sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
    except Exception:
        meta_f.write_text("[]"); return []
    r = sub.get("filings", {}).get("recent", {})
    got = []
    for form, acc, items, dt in zip(r.get("form", []), r.get("accessionNumber", []),
                                    r.get("items", []), r.get("filingDate", [])):
        if form not in ("8-K", "8-K/A") or dt < since:
            continue
        if not re.search(r"2\.02|7\.01|8\.01|1\.01|3\.03|5\.03", items or ""):
            continue
        fn = d / f"8k_{acc}.txt.gz"
        rec = {"acc": acc, "date": dt, "items": items, "file": fn.name}
        if not fn.exists():
            base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
            try:
                idx = sec_get(base + "/index.json").json()["directory"]["item"]
                names = [x["name"] for x in idx if EX99.search(x["name"]) and
                         x["name"].lower().endswith((".htm", ".html", ".txt"))]
                txt = "\n\n".join(html_text(sec_get(f"{base}/{n}").text)[:40000] for n in names[:2])
            except Exception:
                txt = ""
            with gzip.open(fn, "wt", encoding="utf-8") as fh:
                fh.write(txt)
            rec["url"] = base
        got.append(rec)
        if len(got) >= 12:
            break
    meta_f.write_text(json.dumps(got))
    return got


# ---------------------------------------------------------------- analysis
_STOP = {"inc", "corp", "corporation", "company", "co", "ltd", "limited", "holdings", "holding",
         "group", "the", "plc", "sa", "ag", "nv", "bancorp", "bancshares", "financial", "international"}


def name_keys(name):
    toks = [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if t not in _STOP and len(t) > 2]
    return toks[:2]


def about_company(r, sym, name):
    """FMP's press-release feed occasionally returns another issuer's release:
    keep it only if it names the ticker or the company."""
    blob = ((r.get("title") or "") + " " + (r.get("text") or "") + " " + (r.get("full") or "")[:3000]).lower()
    if re.search(r"\b" + re.escape(sym.lower()) + r"\b", blob):
        return True
    keys = name_keys(name)
    return bool(keys) and all(k in blob for k in keys[:1]) and (len(keys) < 2 or keys[1] in blob)


def docs_for(sym, name=None):
    """[(date, kind, title, feats, evidence, url)] for every document."""
    out = []
    tdir = ROOT / "fmp_cache" / "transcripts" / sym
    for f in sorted(tdir.glob("*.json.gz")) if tdir.exists() else []:
        try:
            rec = json.load(gzip.open(f, "rt", encoding="utf-8"))
        except Exception:
            continue
        if rec.get("content"):
            fe, ev = ci.analyze(rec["content"])
            out.append((rec["date"][:10], "CALL", f"{rec.get('period')} {rec.get('year')} call", fe, ev, None))
    d = STORE / sym
    if (d / "pr.json").exists():
        for r in json.loads((d / "pr.json").read_text()):
            if name and not about_company(r, sym, name):
                continue
            text = r.get("full") or r.get("text") or ""
            kind = "LETTER" if ci.LETTER.search(text[:3000]) or re.search(r"letter to (?:share|stock)holders", r.get("title") or "", re.I) else "PR"
            fe, ev = ci.analyze_turns(ci.doc_turns(text, r.get("title") or ""), doc=True)
            out.append(((r.get("publishedDate") or "")[:10], kind, r.get("title") or "", fe, ev, r.get("url")))
    if (d / "8k_index.json").exists():
        for r in json.loads((d / "8k_index.json").read_text()):
            fn = d / r["file"]
            if not fn.exists():
                continue
            text = gzip.open(fn, "rt", encoding="utf-8").read()
            if len(text) < 200:
                continue
            kind = "LETTER" if ci.LETTER.search(text[:4000]) else "EX99"
            fe, ev = ci.analyze_turns(ci.doc_turns(text), doc=True)
            out.append((r["date"], kind, f"8-K {r.get('items')}", fe, ev, r.get("url")))
    return [o for o in out if o[0]]


# weights from the call study's measured lifts (CALL_INTENT_VALIDATION.md):
# tender 2.2x, buyback / dividend 1.6x, value-gap 1.4x, governance 1.4x,
# novelty 1.2x; anticipation / cost / delever ~1.0x carry no weight here.
OTC_W = {"TENDER": 1.5, "BUYBACK": 1.0, "DIVIDEND_RETURN": 1.0, "STRATEGIC_REVIEW": 0.7,
         "MONETIZE": 0.5, "GOVERNANCE": 0.6, "VALUE_GAP": 0.8}


def otc_score(agg, nov, size):
    s = sum(w * min(agg.get(k, 0.0), 2.0) for k, w in OTC_W.items())
    concrete = sum(agg.get(k, 0.0) for k in ci.SHAREHOLDER_ACT) > 0.8
    s += 0.5 * min(agg.get("VALUE_GAP", 0.0), 2.0) * concrete     # "we're cheap" AND acting
    s += 0.4 * nov + 0.4 * agg.get("a_commit", 0) - 0.4 * agg.get("a_evade", 0)
    s -= 0.3 * min(agg.get("neg_total", 0), 5)
    return s + 4.0 * min(size, 0.25) / 0.25                          # size of the action vs mcap


def aggregate(docs, mcap, price, domestic=True):
    """Trailing-12m signal vs the prior 12m baseline."""
    cur, base = [], []
    for dt, kind, title, fe, ev, url in docs:
        age = (TODAY - datetime.strptime(dt, "%Y-%m-%d").date()).days
        if age <= 365:
            cur.append(((1.0 if age <= 183 else 0.6) * KIND_W[kind], dt, kind, title, fe, ev, url))
        elif age <= 730:
            base.append(fe)
    if not cur:
        return None
    fam, evidence = {}, {}
    for k in ci.ACTION + ci.STANCE:
        vals = sorted(((w * fe[k], dt, kind, title, ev, url) for w, dt, kind, title, fe, ev, url in cur
                       if fe[k] > 0), key=lambda t: -t[0])
        if vals:
            fam[k] = round(vals[0][0] + 0.25 * sum(v[0] for v in vals[1:3]), 3)
            v = vals[0]
            q = (v[4].get(k) or [{}])[0].get("q", "")
            evidence[k] = {"date": v[1], "kind": v[2], "doc": v[3][:90], "q": q[:240], "url": v[5]}
    before = {k: max([b[k] for b in base], default=0.0) for k in ci.ACTION + ("VALUE_GAP",)}
    nov = sum(ci.ACT_W.get(k, 0.7) * min(max(0.0, fam.get(k, 0.0) - before[k]), 2.0)
              for k in ci.ACTION + ("VALUE_GAP",))
    new = [k for k in ci.SHAREHOLDER_ACT + ("VALUE_GAP",) if fam.get(k, 0) >= 0.8 and before[k] < 0.3 and base]
    size = 0.0
    for w, dt, kind, title, fe, ev, url in cur:
        if mcap and domestic:                        # foreign amounts are in local currency
            size = max(size, (fe.get("bb_usd") or 0) / mcap)
            if price and domestic:
                size = max(size, (fe.get("bb_shares") or 0) * price / mcap)
        size = max(size, (fe.get("bb_pct_out") or 0) / 100)
    # > 50% of mcap is almost always a mis-read (an offering, a facility) -- unless it's a tender
    if size > 0.5 and not fam.get("TENDER"):
        size = 0.0
    size = min(size, 1.0)
    agg = {k: fam.get(k, 0.0) for k in ci.ACTION + ci.STANCE}
    agg.update({"a_commit": sum(fe["a_commit"] for _, _, kind, _, fe, _, _ in cur if kind == "CALL"),
                "a_evade": sum(fe["a_evade"] for _, _, kind, _, fe, _, _ in cur if kind == "CALL"),
                "neg_total": sum(fe["neg_total"] for _, _, _, _, fe, _, _ in cur)})
    score = otc_score(agg, nov, size)
    kinds = {}
    for _, _, kind, _, _, _, _ in cur:
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"score": round(score, 2), "families": {k: v for k, v in fam.items() if v > 0},
            "novelty": round(nov, 2), "new_families": new, "size_pct_mcap": round(size, 4),
            "docs_12m": kinds, "last_doc": max(dt for _, dt, *_ in cur), "evidence": evidence}


def validate(rows_by_sym):
    """Doc-level: does a document's shareholder-action language predict what
    the company then did? (FMP bulk statements, same labels as calls)."""
    from call_intent_model import load_statements, behaviour, auc, lift_top
    stm = load_statements()
    pts = []
    for sym, docs in rows_by_sym.items():
        for dt, kind, title, fe, ev, url in docs:
            past, acted = behaviour(stm.get(sym, []), dt)
            if past is None or acted is None:
                continue
            s = sum(ci.ACT_W[k] * min(fe[k], 2.0) for k in ci.SHAREHOLDER_ACT) + 0.7 * min(fe["VALUE_GAP"], 2)
            pts.append((kind, s, int(acted), past["past_sh_chg"]))
    L = ["# OTC management communications -- validation", "",
         f"Generated {TODAY} by `otc_comms.py`. Each dated document (press release, 8-K EX-99, "
         "shareholder letter, call) is scored on its shareholder-action language and labelled "
         "with what the company did over the next two fiscal quarters (diluted share count down "
         ">= 2% or dividends up >= 25% / initiated; FMP bulk statements).", "",
         "| documents | n | base rate | AUC (language) | top-decile hit | lift |", "|---|---|---|---|---|---|"]
    res = {}
    for name, sel in [("all", lambda p: True), ("press releases", lambda p: p[0] == "PR"),
                      ("8-K EX-99", lambda p: p[0] == "EX99"), ("letters", lambda p: p[0] == "LETTER"),
                      ("calls", lambda p: p[0] == "CALL"),
                      ("not already shrinking", lambda p: p[3] > -0.01)]:
        sub = [p for p in pts if sel(p)]
        if len(sub) < 30 or not any(p[2] for p in sub):
            L.append(f"| {name} | {len(sub)} | — | — | — | — |"); continue
        a = auc([p[1] for p in sub], [p[2] for p in sub])
        top, base, lf = lift_top([p[1] for p in sub], [p[2] for p in sub])
        res[name] = {"n": len(sub), "auc": a, "top": top, "base": base}
        L.append(f"| {name} | {len(sub)} | {base:.1%} | {a:.3f} | {top:.1%} | {lf:.2f}x |")
    REPORT.write_text("\n".join(L) + "\n")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    since = (TODAY - timedelta(days=30 * args.months)).isoformat()
    us, fx, q = universe()
    syms = sorted(us) + sorted(fx)
    if args.limit:
        syms = syms[: args.limit]
    print(f"OTC comms: {len(us)} US + {len(fx)} foreign names")
    if not args.no_fetch:
        import transcript_fetch as tf

        def job(s):
            v = q[s]
            try:
                tf.fetch_one(s, 6)
            except Exception:
                pass
            fetch_pr(s, since)
            if s in us and v.get("cik"):
                fetch_8k(s, v["cik"], since)
            return s
        with ThreadPoolExecutor(args.workers) as ex:
            for i, _ in enumerate(ex.map(job, syms), 1):
                if i % 250 == 0:
                    print(f"  fetched {i}/{len(syms)}", flush=True)
    out, all_docs = {}, {}
    for s in syms:
        docs = docs_for(s, q[s].get("name"))
        if not docs:
            continue
        all_docs[s] = docs
        v = q[s]
        agg = aggregate(docs, v.get("mcap"), v.get("price"), s in us)
        if not agg:
            continue
        out[s] = {"ticker": s, "name": v.get("name"), "domestic": s in us, "p_b": v.get("p_b"),
                  "mcap": v.get("mcap"), **agg}
    # one company, several OTC lines (ordinary + ADR): keep the best-scoring line
    import build_otc_book as ob
    seen, ranked = set(), []
    for r in sorted(out.values(), key=lambda r: -r["score"]):
        key = ob._norm(r.get("name")) or r["ticker"]
        if key in seen:
            continue
        seen.add(key); ranked.append(r)
    for i, r in enumerate(ranked):
        pct = 1 - i / max(1, len(ranked))
        strong = any(r["families"].get(k, 0) >= 0.9 for k in ci.SHAREHOLDER_ACT)
        recent = (TODAY - datetime.strptime(r["last_doc"], "%Y-%m-%d").date()).days <= 200
        r["tier"] = ("ACT SIGNALLED" if pct >= 0.9 and recent and (strong or r["new_families"] or r["size_pct_mcap"] >= 0.05)
                     else "BUILDING" if pct >= 0.75 and recent else "")
    json_out = {r["ticker"]: r for r in ranked}
    OUT.write_text(json.dumps(json_out, indent=1))
    val = validate(all_docs)
    from collections import Counter
    kinds = Counter(k for d in all_docs.values() for _, k, *_ in d)
    print(f"wrote {OUT.name}: {len(out)} OTC names with communications "
          f"({dict(Counter(r['tier'] for r in ranked))}); documents {dict(kinds)}")
    print("validation:", {k: (v["n"], round(v["auc"], 3)) for k, v in val.items()})
    for r in ranked[:15]:
        k = max(r["families"], key=r["families"].get) if r["families"] else ""
        print(f"  {r['ticker']:<7}{r['score']:>6.1f} {r['tier']:<14} size={r['size_pct_mcap']:.1%} "
              f"{(r['evidence'].get(k) or {}).get('q', '')[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
