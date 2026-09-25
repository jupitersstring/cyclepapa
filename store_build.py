"""Build / refresh the data store (store.py) from what the pipeline already produces.

  1. security master  -- FMP profiles (93k listings) + FMP delisted list + the quote
     store + the cross book's exchange-qualified tickers; issuers grouped by CIK, then
     CUSIP issuer code, then name + country; security type classified once; one
     primary line per issuer (common, active, most traded)
  2. facts snapshot   -- validated FMP financials, the old quote store (kept as an
     UNVALIDATED source so disagreements are visible), expectations, ownership,
     red flags and payoff floors, each with source, method and as-of date; appended
     as a new run (history kept)
  3. events           -- 8-K events (with reviewed verdicts), 13D/13G moves, insider
     transactions, filing red flags, executive appointments, earnings-call
     commitments, and the older scanners' events in pipeline.db -- one taxonomy
  4. reports          -- DATA_STORE.md: master coverage, cross-source disagreements,
     book-name coverage matrix (which sources exist for each name)

Run: python3 store_build.py            (all steps)
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import store

ROOT = store.ROOT
C = ROOT / "fmp_cache"


def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _j(name):
    p = ROOT / name
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def norm_name(n):
    n = re.sub(r"[^a-z0-9 ]", " ", str(n or "").lower())
    n = re.sub(r"\b(inc|corp|corporation|co|company|ltd|limited|plc|holdings?|group|the|sa|ag|nv|se|lp|llc|"
               r"class [a-c]|ordinary shares|common stock|adr|ads|sponsored|unsponsored)\b", " ", n)
    return " ".join(n.split())[:40]


def sec_type(sym, r, prof_syms):
    nm = r.get("companyName") or ""
    ind = r.get("industry") or ""
    ex = r.get("exchange") or ""
    if re.search(r"\d%|\bnotes?\b|debenture|\bpfd\b|preferred|\bZONES\b|capital securities|cap secs|depositary shares? each", nm, re.I) \
            or re.search(r"-P[A-Z]?$", sym):
        return "note_pref"
    if str(r.get("isFund")).lower() == "true" or str(r.get("isEtf")).lower() == "true":
        return "fund"
    if ind == "Shell Companies" and re.search(r"Acquisition|Capital Corp|SPAC|Merger|Blank Check", nm, re.I):
        return "spac"
    if re.search(r"-(?:WT|WS|U|UN|R|RI|CVR)$", sym) or re.search(r"\b(?:Rights?|Units?|Warrants?)\b|Contingent Value", nm):
        return "warrant_right_unit"
    if len(sym) == 5 and sym[-1] in "WRUZ" and sym[:4] in prof_syms and "." not in sym \
            and norm_name((prof_syms.get(sym[:4]) or {}).get("companyName")) == norm_name(nm):
        return "warrant_right_unit"
    q = prof_syms.get(sym + "Q") if isinstance(prof_syms, dict) else None
    same_issuer = bool(q) and str(q.get("isActivelyTrading")).lower() != "false" and (_f(q.get("price")) or 0) < 5 and (
        (r.get("cik") and r.get("cik") == q.get("cik")) or norm_name(q.get("companyName")) == norm_name(nm))
    if sym.endswith("Q") and len(sym) == 5 and "." not in sym and (_f(r.get("price")) or 0) < 5:
        return "bankrupt"                     # the Q line itself (NOTVQ, BTAIQ)
    if same_issuer or (str(r.get("isActivelyTrading")).lower() == "false" and (_f(r.get("price")) or 0) < 1):
        return "bankrupt"                     # an old line whose issuer now trades as a bankrupt Q line
    if str(r.get("isAdr")).lower() == "true":
        return "adr"
    if ex in ("OTC", "PNK") and len(sym) == 5 and sym[-1] in "FY":
        return "otc_line"
    return "common"


def kind_of(r):
    import name_financials
    return name_financials.kind_of(r.get("sector"), r.get("industry"))


# ------------------------------------------------------------------ 1. security master
def build_master(con):
    prof = {}
    for fn in glob.glob(str(C / "profile-bulk_part*.csv")):
        for r in csv.DictReader(open(fn, encoding="utf-8", errors="ignore")):
            prof[r["symbol"]] = r
    psyms = prof
    issuers, secs, aliases = {}, {}, {}
    fx_usd = {}

    def usd(ccy):
        if ccy not in fx_usd:
            import fmp_book
            c = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(ccy, ccy)
            fx_usd[ccy] = (fmp_book.fx(c, "USD") or 0) / (100 if ccy in ("GBp", "GBX", "ZAc", "ILA") else 1) if c and c != "USD" else 1.0
        return fx_usd[ccy]

    for s, r in prof.items():
        cik = (r.get("cik") or "").lstrip("0")
        cus = (r.get("cusip") or "").strip()
        if cik:
            iid = f"CIK:{cik}"
        elif len(cus) >= 6:
            iid = f"CUSIP6:{cus[:6]}"
        else:
            iid = f"NAME:{r.get('country') or '?'}:{norm_name(r.get('companyName'))}"
        if iid not in issuers:
            issuers[iid] = (iid, r.get("companyName"), cik or None, r.get("country"), r.get("sector"), r.get("industry"), kind_of(r))
        adv = (_f(r.get("averageVolume")) or 0) * (_f(r.get("price")) or 0) * usd(r.get("currency") or "USD")
        st = "active" if str(r.get("isActivelyTrading")).lower() != "false" else "inactive"
        secs[s] = [s, iid, r.get("companyName"), s.split(".")[0], r.get("exchange"), r.get("currency"), r.get("isin"), cus,
                   sec_type(s, r, psyms), st, None, 0, adv]
        aliases[s] = (s, "fmp")
        if cik:
            aliases.setdefault(f"CIK{cik}", (s, "cik"))
    # delisted names FMP no longer profiles
    for r in _j("fmp_cache/delisted_companies.json") or []:
        s = r.get("symbol")
        if not s:
            continue
        if s in secs:
            secs[s][9], secs[s][10] = "delisted", r.get("delistedDate")
            continue
        iid = f"NAME:?:{norm_name(r.get('companyName'))}"
        issuers.setdefault(iid, (iid, r.get("companyName"), None, None, None, None, "operating"))
        secs[s] = [s, iid, r.get("companyName"), s.split(".")[0], r.get("exchange"), None, None, None,
                   "common", "delisted", r.get("delistedDate"), 0, 0.0]
        aliases.setdefault(s, (s, "fmp_delisted"))
    # quote-store CIKs fill gaps; names only in the quote store become X: securities
    for t, v in (_j("yfinance_quick.json") or {}).items():
        if t in secs:
            if v.get("cik") and f"CIK{str(v['cik']).lstrip('0')}" not in aliases:
                aliases[f"CIK{str(v['cik']).lstrip('0')}"] = (t, "cik_yq")
            continue
        sid = f"X:US:{t}"
        iid = f"CIK:{str(v.get('cik')).lstrip('0')}" if v.get("cik") else f"NAME:US:{norm_name(v.get('name'))}"
        issuers.setdefault(iid, (iid, v.get("name"), str(v.get("cik") or "").lstrip("0") or None, "US",
                                 v.get("sector"), v.get("industry"), "operating"))
        secs[sid] = [sid, iid, v.get("name"), t, v.get("exchange"), "USD", None, v.get("cusip"), "common", "unknown", None, 0, 0.0]
        aliases.setdefault(t, (sid, "yq"))
    # primary line per issuer: common/adr, active, most traded
    rank = {"common": 0, "adr": 1, "otc_line": 2}
    by_iss = defaultdict(list)
    for s, row in secs.items():
        by_iss[row[1]].append(row)
    for iid, rows in by_iss.items():
        cands = [x for x in rows if x[8] in rank and x[9] != "delisted"] or rows
        best = min(cands, key=lambda x: (rank.get(x[8], 9), x[9] != "active", -(x[12] or 0), len(x[0])))
        best[11] = 1
    # bare-ticker aliases: 'LOCAL' -> the primary line when unambiguous; US listing preferred
    bare = defaultdict(list)
    for s, row in secs.items():
        b = s.split(".")[0] if "." in s and not s.startswith("X:") else None
        if b:
            bare[b].append(row)
    for b, rows in bare.items():
        if b in aliases:
            continue
        prim = [x for x in rows if x[11] == 1]
        pick = prim[0] if len(prim) == 1 else (rows[0] if len(rows) == 1 else None)
        if pick:
            aliases[b] = (pick[0], "bare")
    # exchange-qualified spellings used by the cross book / YAML
    rev = {v: k for k, v in store.EXCH_SUFFIX.items()}
    for s in list(secs):
        m = re.match(r"^(.+)(\.[A-Z]{1,3})$", s)
        if m and m.group(2) in rev:
            for ex, suf in store.EXCH_SUFFIX.items():
                if suf == m.group(2):
                    aliases.setdefault(f"{ex}:{m.group(1)}", (s, "exch"))
                    aliases.setdefault(f"{ex}:{s}", (s, "exch"))
        elif "." not in s and not s.startswith("X:"):
            for ex in ("NASDAQ", "NYSE", "AMEX", "OTC", "NYSEAMERICAN"):
                aliases.setdefault(f"{ex}:{s}", (s, "exch"))
    for s, row in secs.items():
        if row[6]:
            aliases.setdefault("ISIN:" + row[6].upper(), (s, "isin"))
    # the cross book's own ticker -> FMP mapping (name-verified by rr_fmp_overlay) and its YAML symbols
    xm = _j("cross_symbol_map.json") or {}
    try:
        import rr_postprocess
        xm = {**getattr(rr_postprocess, "YAML_SYM", {}), **xm}
    except Exception:
        pass
    for k, v in xm.items():
        if v in secs and k not in aliases:
            aliases[k] = (v, "cross_map")
    for old, new in store.OLD_TICKERS.items():
        if new in secs:
            aliases[old] = (new, "renamed")
    con.execute("DELETE FROM issuers"); con.execute("DELETE FROM securities"); con.execute("DELETE FROM aliases")
    con.executemany("INSERT INTO issuers VALUES (?,?,?,?,?,?,?)", list(issuers.values()))
    con.executemany("INSERT INTO securities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(x) for x in secs.values()])
    con.executemany("INSERT OR REPLACE INTO aliases VALUES (?,?,?)", [(a, s, k) for a, (s, k) in aliases.items()])
    con.commit()
    store.reload_aliases()
    return len(issuers), len(secs), len(aliases), Counter(x[8] for x in secs.values())


# ------------------------------------------------------------------ 2. facts snapshot
FIN_FIELDS = {"price": "ccy", "mcap": "ccy", "mcap_usd": "USD", "ev": "ccy", "p_b": "x", "p_tbv": "x", "pe": "x",
              "ps": "x", "ev_ebitda": "x", "fcf_yield": "frac", "earn_yield": "frac", "div_yield": "frac",
              "gross_m": "frac", "op_m": "frac", "net_m": "frac", "roe": "frac", "roic": "frac", "roa": "frac",
              "net_cash_pct": "frac", "nd_ebitda": "x", "de": "x", "int_cover": "x", "current": "x",
              "rev_growth": "frac", "shares_yoy": "frac", "range_pos": "frac", "adv_usd": "USD", "tce_ta": "frac",
              "aoci_eq": "frac", "nii_assets": "frac", "ffo_yield": "frac", "buyback_ttm_mcap": "frac",
              "div_paid_ttm_mcap": "frac", "lt_inv_mcap": "frac"}


def snapshot_facts(con, run):
    today = date.today().isoformat()
    rows = []
    fin = _j("name_financials.json")
    for s, r in fin.items():
        sid = store.resolve(s) or s
        for k, unit in FIN_FIELDS.items():
            v = r.get(k)
            if isinstance(v, (int, float)):
                rows.append((sid, k, float(v), None, unit, r.get("currency") if unit == "ccy" else None, today,
                             "fmp_validated", r.get("pb_src") if k == "p_b" else "name_financials", 1, run))
        for k in ("stmt_date", "kind", "security", "pb_src"):
            if r.get(k):
                rows.append((sid, k, None, str(r[k]), "text", None, today, "fmp_validated", "name_financials", 1, run))
        if r.get("flags"):
            rows.append((sid, "flags", None, "; ".join(r["flags"]), "text", None, today, "fmp_validated", "sanity", 1, run))
    for t, v in (_j("yfinance_quick.json") or {}).items():         # legacy store: unvalidated, kept for reconciliation
        sid = store.resolve(t) or f"X:US:{t}"
        for k, fk in (("mcap", "mcap"), ("p_b", "p_b"), ("price", "price"), ("p_e_trailing", "pe"), ("ev_ebitda", "ev_ebitda")):
            if isinstance(v.get(k), (int, float)):
                rows.append((sid, fk, float(v[k]), None, "ccy" if fk in ("mcap", "price") else "x", None, today,
                             "quote_store", v.get("_src") or "yq", 0, run))
    exp = _j("expectations.json")
    for s, r in exp.items():
        if s.startswith("_") or not isinstance(r, dict):
            continue
        sid = store.resolve(s) or s
        for k in ("n_analysts", "pt", "pt_upside", "pt_trend", "fwd_pe", "short_pct_float", "days_to_cover",
                  "short_change", "upgrades_90d", "downgrades_90d"):
            if isinstance(r.get(k), (int, float)):
                rows.append((sid, k, float(r[k]), None, None, None, today, "fmp+finra", "expectations_layer", 1, run))
    own = _j("ownership.json")
    for s, r in own.items():
        sid = store.resolve(s) or s
        ins = r.get("insiders") or {}
        for k, v in (("insider_buy_12m_usd", ins.get("buy_usd")), ("insider_sell_12m_usd", ins.get("sell_usd")),
                     ("inst_holders", (r.get("inst") or {}).get("investorsHolding")),
                     ("inst_holders_chg", (r.get("inst") or {}).get("investorsHoldingChange")),
                     ("inst_own_pct", (r.get("inst") or {}).get("ownershipPercent")),
                     ("active_13d_max_pct", max([h.get("pct") or 0 for h in r.get("active_13d") or []] or [0]) or None)):
            if isinstance(v, (int, float)):
                rows.append((sid, k, float(v), None, None, None, today, "fmp", "ownership_layer", 1, run))
    dist = _j("distress_flags.json")
    for s, r in dist.items():
        sid = store.resolve(s) or s
        for k in ("severity", "altman_z", "piotroski"):
            if isinstance(r.get(k), (int, float)):
                rows.append((sid, k, float(r[k]), None, None, None, today, "edgar+fmp", "distress_flags", 1, run))
    geo = _j("payoff_geometry.json")
    for s, r in geo.items():
        if not isinstance(r, dict):
            continue
        sid = store.resolve(s) or s
        for k in ("floor_frac", "downside_pct", "upside_pct"):
            if isinstance(r.get(k), (int, float)):
                rows.append((sid, k, float(r[k]), None, "frac", None, today, "derived", "payoff_geometry", 1, run))
        if r.get("floor_source"):
            rows.append((sid, "floor_source", None, r["floor_source"], "text", None, today, "derived", "payoff_geometry", 1, run))
    con.execute("DELETE FROM facts WHERE as_of=? AND run_id<>?", (today, run))   # one snapshot per day (latest wins)
    con.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def backfill_history(con, run):
    """Point-in-time history from git: every committed snapshot of the quote store and of the
    validated financials becomes a dated facts snapshot (once; skipped if already loaded)."""
    import subprocess
    n = 0
    for fn, source, validated in (("yfinance_quick.json", "quote_store", 0), ("name_financials.json", "fmp_validated", 1)):
        log = subprocess.run(["git", "log", "--format=%h %ad", "--date=short", "--", fn], cwd=ROOT,
                             capture_output=True, text=True).stdout.split("\n")
        seen = set()
        for line in log:
            if not line.strip():
                continue
            h, d = line.split()
            if d in seen or d == date.today().isoformat():
                continue                                   # newest commit of each day only; today = live snapshot
            seen.add(d)
            if con.execute("SELECT 1 FROM facts WHERE as_of=? AND source=? LIMIT 1", (d, source)).fetchone():
                continue
            try:
                data = json.loads(subprocess.run(["git", "show", f"{h}:{fn}"], cwd=ROOT, capture_output=True,
                                                 text=True).stdout)
            except Exception:
                continue
            rows = []
            for t, v in data.items():
                if not isinstance(v, dict):
                    continue
                sid = store.resolve(t) or t
                for k, fk in (("price", "price"), ("mcap", "mcap"), ("p_b", "p_b"), ("p_e_trailing", "pe"), ("pe", "pe"),
                              ("ev_ebitda", "ev_ebitda"), ("mcap_usd", "mcap_usd"), ("roe", "roe"), ("net_cash_pct", "net_cash_pct")):
                    if isinstance(v.get(k), (int, float)):
                        rows.append((sid, fk, float(v[k]), None, None, None, d, source, f"git:{h}", validated, run))
            con.executemany("INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
    con.commit()
    return n


# ------------------------------------------------------------------ 3. events
def _eid(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def load_events(con, run):
    ev = []

    def add(t, dt, typ, fam, src, url=None, amt=None, cp=None, ps=None, status=None, verdict=None, reviewed=0,
            what=None, evidence=None, extra=None):
        sid = store.resolve(t) or t
        r = con.execute("SELECT issuer_id FROM securities WHERE security_id=?", (sid,)).fetchone()
        iid = r["issuer_id"] if r else None
        ev.append((_eid(sid, dt, typ, src, url or what), sid, iid, dt, typ, fam, src, url, amt, cp, ps, status, verdict,
                   reviewed, what, evidence, json.dumps(extra) if extra else None, run))

    for t, lst in (_j("event_detail.json") or {}).items():
        for e in lst:
            if not e.get("date"):
                continue
            typ = (e.get("reviewed_type") or e["family"]) if e.get("verdict") != "NOT AN EVENT" else "NOT_AN_EVENT"
            add(t, e["date"], typ, e["family"], "8-K", e.get("url"), e.get("amount_usd"), e.get("counterparty"),
                e.get("per_share"), e.get("status"), e.get("verdict"), int(e.get("source") == "reviewed"),
                e.get("what"), e.get("evidence") or (e.get("excerpt") or "")[:400],
                {k: e.get(k) for k in ("xret_since", "deal_state", "offer_spread", "amount_ev", "pct_mcap") if e.get(k) is not None})
    for t, r in (_j("ownership.json") or {}).items():
        for e in r.get("events_13d") or []:
            add(t, e["date"], {"new_13d": "NEW_13D", "switch": "13G_TO_13D", "13d_add": "13D_ADD", "13d_cut": "13D_CUT"}[e["type"]],
                "OWNERSHIP", "13D/13G", e.get("url"), None, e.get("holder"), None, None, None, 0, e.get("what"), None,
                {"pct": e.get("pct"), "activist": e.get("activist")})
    for fn in glob.glob(str(C / "own" / "*__f4.json")):
        t = Path(fn).name.split("__")[0]
        try:
            rows = json.loads(Path(fn).read_text())
        except Exception:
            continue
        for x in rows or []:
            tt = str(x.get("transactionType") or "")
            if not (tt.startswith("P-") or tt.startswith("S-")):
                continue
            v = (x.get("securitiesTransacted") or 0) * (x.get("price") or 0)
            if v < 25_000:
                continue
            add(t, (x.get("transactionDate") or x.get("filingDate") or "")[:10], "INSIDER_BUY" if tt.startswith("P-") else "INSIDER_SELL",
                "INSIDER", "Form 4", x.get("url"), v, x.get("reportingName"), x.get("price"), None, None, 0,
                f"{x.get('reportingName')} ({x.get('typeOfOwner')}) {'bought' if tt.startswith('P-') else 'sold'} ${v / 1e3:,.0f}k")
    for t, r in (_j("distress_flags.json") or {}).items():
        for x in r.get("flags") or []:
            if x.get("date"):
                add(t, x["date"], "RED_FLAG_" + x["kind"].upper(), "RED_FLAG", "EDGAR/FMP", x.get("url"), what=x.get("detail"))
    tcsv = ROOT / "turnaround_signal.csv"
    if tcsv.exists():
        for x in csv.DictReader(tcsv.open()):
            if x.get("filing_date"):
                add(x["ticker"], x["filing_date"], "EXEC_" + (x.get("event_type") or "OTHER").replace(" ", "_"), "EXEC",
                    "8-K 5.02", None, None, x.get("person"), None, None, None, int(x.get("source") == "reviewed"),
                    f"{x.get('person')}: {x.get('role')}", (x.get("excerpt") or "")[:400])
    for t, v in (_j("call_intent.json") or {}).items():
        if isinstance(v, dict) and v.get("tier") and v.get("date"):
            add(t, v["date"][:10], "CALL_" + v["tier"].replace(" ", "_"), "CALL_INTENT", "earnings call", None, None, None, None,
                None, None, 0, ", ".join((v.get("families") or {}).keys()), None,
                {"act_prob": v.get("act_prob"), "size_pct": v.get("size_pct")})
    pdb = ROOT / "pipeline.db"
    if pdb.exists():
        try:
            pc = sqlite3.connect(f"file:{pdb}?mode=ro", uri=True)
            cols = [c[1] for c in pc.execute("PRAGMA table_info(events)")]
            for row in pc.execute("SELECT * FROM events"):
                d = dict(zip(cols, row))
                dt = str(d.get("event_date") or d.get("filing_date") or d.get("date") or "")[:10]
                if d.get("ticker") and dt:
                    add(d["ticker"], dt, str(d.get("event_type") or d.get("source") or "LEGACY").upper(), "LEGACY_SCANNER",
                        "pipeline.db:" + str(d.get("source")), None, what=str(d.get("detail") or d.get("summary") or "")[:200])
        except sqlite3.Error:
            pass
    con.execute("DELETE FROM events")
    con.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ev)
    con.commit()
    return Counter(x[5] for x in ev)


# ------------------------------------------------------------------ 4. reports
def book_names():
    import openpyxl
    out = set()
    for b in ("MOST_ASYMMETRIC.xlsx", "OTC_BOOK.xlsx", "cyclepapa_risk_reward_workbook.xlsx"):
        try:
            wb = openpyxl.load_workbook(ROOT / b, read_only=True)
        except Exception:
            continue
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                v = (r or (None,))[0]
                for v in (r or ())[:4]:
                    if isinstance(v, str) and 0 < len(v.strip()) < 22 and " " not in v.strip():
                        out.add((b, v.replace("●", "").strip()))
    return out


def report(con, stats):
    n_iss, n_sec, n_al, types = stats["master"]
    L = [f"# Data store — {date.today()}", "",
         "One security master, one point-in-time fact store and one event store (`store.py`, built by "
         "`store_build.py` into `data/cyclepapa.db`, rebuilt from the caches). Every run appends a dated snapshot "
         "of the facts, so values can be read as of any past run.", "",
         "## Security master", "",
         f"- {n_iss:,} issuers, {n_sec:,} securities, {n_al:,} aliases (FMP symbol, exchange-qualified `EPA:LOCAL`, "
         "bare tickers where unambiguous, `CIK…`, old tickers).",
         "- Security types: " + ", ".join(f"{k} {v:,}" for k, v in types.most_common()) + ".", ""]
    # resolution of every identifier used in the books
    names = book_names()
    unres = Counter()
    res_ok = 0
    per_book = Counter()
    for b, t in names:
        if store.resolve(t):
            res_ok += 1; per_book[(b, "ok")] += 1
        elif re.fullmatch(r"[A-Z][A-Z0-9:.\-]{2,19}", t) and not re.fullmatch(r"\d{4}-.*|[A-Z]\d+", t):
            unres[(b, t)] += 1; per_book[(b, "miss")] += 1
    L += ["## Book identifiers resolved", "", "| Book | Resolved | Not resolved |", "|---|---|---|"]
    for b in ("MOST_ASYMMETRIC.xlsx", "OTC_BOOK.xlsx", "cyclepapa_risk_reward_workbook.xlsx"):
        L.append(f"| {b} | {per_book[(b, 'ok')]:,} | {per_book[(b, 'miss')]:,} |")
    miss = sorted({t for (b, t) in unres if re.fullmatch(r"[A-Z][A-Z0-9:.\-]{2,19}", t)
                   and not re.fullmatch(r"\d{4}-.*|[A-Z]\d+|ANNOUNCED|COMPLETED|PENDING|PROMOTION|OVERALL", t)})[:40]
    L += ["", "Unresolved samples (headers / non-tickers included): " + ", ".join(miss), ""]
    # cross-source disagreements
    today = date.today().isoformat()
    q = """SELECT a.security_id sid, a.field, a.value v_fmp, b.value v_old FROM facts a JOIN facts b
           ON a.security_id=b.security_id AND a.field=b.field AND a.as_of=b.as_of
           WHERE a.as_of=? AND a.source='fmp_validated' AND b.source='quote_store' AND a.field IN ('mcap','p_b','pe')"""
    dis = Counter()
    ex = defaultdict(list)
    for r in con.execute(q, (today,)):
        a, b = r["v_fmp"], r["v_old"]
        if a and b and a > 0 and b > 0 and abs(a / b - 1) > 0.25:
            dis[r["field"]] += 1
            ex[r["field"]].append((r["sid"], a, b))
    tot = Counter(r["field"] for r in con.execute(
        "SELECT field FROM facts WHERE as_of=? AND source='quote_store' AND field IN ('mcap','p_b','pe')", (today,)))
    L += ["## Cross-source disagreements (validated FMP vs the old quote store, > 25% apart)", "",
          "66 modules still read the old quote store; these are the names where it disagrees with the validated value.", "",
          "| Field | Disagreements | of names in both |", "|---|---|---|"]
    for k in ("mcap", "p_b", "pe"):
        L.append(f"| {k} | {dis[k]:,} | {tot[k]:,} |")
    for k in ("p_b", "mcap"):
        L.append("")
        L.append(f"{k} examples: " + "; ".join(f"{s} {a:,.2f} vs {b:,.2f}" for s, a, b in
                                                sorted(ex[k], key=lambda x: -abs(x[1] / x[2] - 1))[:8]))
    # coverage matrix for book names
    cov_src = {"financials": "SELECT DISTINCT security_id FROM facts WHERE source='fmp_validated' AND as_of=?",
               "expectations": "SELECT DISTINCT security_id FROM facts WHERE source='fmp+finra' AND as_of=?",
               "ownership": "SELECT DISTINCT security_id FROM facts WHERE source='fmp' AND as_of=?",
               "red-flag scan": "SELECT DISTINCT security_id FROM facts WHERE source='edgar+fmp' AND as_of=?"}
    have = {k: {r[0] for r in con.execute(q_, (today,))} for k, q_ in cov_src.items()}
    ev_have = defaultdict(set)
    for r in con.execute("SELECT DISTINCT security_id, family FROM events"):
        ev_have[r[1]].add(r[0])
    tr = {p.name for p in (C / "transcripts").glob("*")} if (C / "transcripts").exists() else set()
    psu = set(_j("psu_detail.json"))
    L += ["", "## Source coverage of the names in each book", "",
          "| Book | Names | Financials | Expectations | Ownership | Red-flag scan | 8-K events | Transcripts | PSU plan |",
          "|---|---|---|---|---|---|---|---|---|"]
    for b in ("MOST_ASYMMETRIC.xlsx", "OTC_BOOK.xlsx", "cyclepapa_risk_reward_workbook.xlsx"):
        sids = {store.resolve(t) for bb, t in names if bb == b} - {None}
        sids = {s for s in sids if con.execute("SELECT 1 FROM securities WHERE security_id=? AND sec_type IN ('common','adr','otc_line')", (s,)).fetchone()}
        n = len(sids) or 1
        pc = lambda st: f"{len(sids & st) / n:.0%}"
        L.append(f"| {b} | {len(sids):,} | {pc(have['financials'])} | {pc(have['expectations'])} | {pc(have['ownership'])} | "
                 f"{pc(have['red-flag scan'])} | {pc(ev_have['REAL'] | ev_have.get('8-K', set()) | {r[0] for r in con.execute(chr(83)+'ELECT DISTINCT security_id FROM events WHERE source=' + chr(39) + '8-K' + chr(39))})} | "
                 f"{pc(tr)} | {pc(psu)} |")
    L += ["", "## Events", "", "| Family | Events |", "|---|---|"]
    for k, v in stats["events"].most_common():
        L.append(f"| {k} | {v:,} |")
    hist = con.execute("SELECT as_of, source, COUNT(*) n FROM facts GROUP BY as_of, source ORDER BY as_of").fetchall()
    L += ["", "## Point-in-time history", "",
          "Dated snapshots in the fact store (live runs plus snapshots recovered from git history):", "",
          "| As of | Source | Rows |", "|---|---|---|"] + [f"| {r['as_of']} | {r['source']} | {r['n']:,} |" for r in hist]
    L += ["", f"Facts rows this run: {stats['facts']:,}."]
    (ROOT / "DATA_STORE.md").write_text("\n".join(L) + "\n")
    return L


def main() -> int:
    con = store.connect()
    run = store.new_run(con, "store_build")
    stats = {"master": build_master(con)}
    print(f"master: {stats['master'][0]:,} issuers, {stats['master'][1]:,} securities, {stats['master'][2]:,} aliases")
    stats["facts"] = snapshot_facts(con, run)
    stats["history"] = backfill_history(con, run)
    print(f"history backfilled from git: {stats['history']:,} rows")
    print(f"facts: {stats['facts']:,} rows")
    stats["events"] = load_events(con, run)
    print(f"events: {sum(stats['events'].values()):,} ({dict(stats['events'])})")
    L = report(con, stats)
    print("\n".join(L[:60]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
