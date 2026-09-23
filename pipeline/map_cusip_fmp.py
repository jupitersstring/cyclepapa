"""Recover unmapped 13F CUSIPs via FMP's CUSIP search.

~1,200 holdings CUSIPs had no ticker (issuer-name quirks like "BRISTOL-MYER
SQB", ADR/NY-registry lines, post-IPO names) and were excluded from every
signal. FMP maps CUSIP -> listed symbol directly. Guardrails:
  * name validation — FMP's company name must share a real token with the
    13F issuer string (catches one-trust-many-ETF CUSIP families like
    "BLACKROCK ETF TRUST II");
  * price validation — the 13F's own implied price (value / shares) must agree
    with the symbol's price. FMP files some CUSIPs under the wrong company:
    Ferguson plc's G3421J106 sits on Ferroglobe's GSM profile (13F implies
    $237/sh, GSM trades ~$4); Barrick's old 067901108 on a dead "NOV" line;
  * renamed issuers (13F keeps "FACEBOOK" for META) are accepted only when the
    symbol's own FMP profile carries this CUSIP, it still trades, and the
    price agrees tightly;
  * prefer the US listing when FMP returns several venues;
  * ETFs / funds are recorded as sec_type 'etf' (kept out of stock signals);
  * fill gaps, never clobber: only CUSIPs with no ticker in cusip_map are
    written, and composite venue junk (TRI4EUR) is refused.
Every earlier FMP mapping is re-audited against the same rules on each run.
Verified cases the automatic tiers can't settle live in CURATED, which
outranks every other source.
"""
import json, os, re, sqlite3, statistics, subprocess, sys, time, unicodedata, urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import api_key, API, DB, load_profiles, is_true, num
from build_cusip_map import _valid_cusip, _valid_ticker
from unified_score import _FX_USD

# CUSIP -> ticker, verified by hand (FMP match + profile + implied-price check)
CURATED = {
    "84615Q103": "SPCX",   # SpaceX — IPO'd on NASDAQ 2026-06-12; 13F issuer reads "SPACEX"
    "G3421J106": "FERG",   # Ferguson plc (Jersey) -> Ferguson Enterprises Inc. 1:1 (Aug 2024,
                           # new CUSIP 31488V107); Trian still files the old CUSIP
    "067901108": "B",      # Barrick Gold -> Barrick Mining (May 2025, NYSE GOLD -> B, new
                           # CUSIP 06849F108); "GOLD" now belongs to Gold.com (ex A-Mark)
    "30231G102": "XOM",    # Exxon Mobil Corp's pre-reorganization CUSIP; FMP's XOM profile
                           # now carries ExxonMobil Holdings Corp's 30233Q108. OpenFIGI had "EXMOC"
}
TABLES = ("fund_13f_holdings", "fund_13f_prior", "broker_13f")
STOP = {"INC", "CORP", "CORPORATION", "CO", "LTD", "PLC", "NV", "SA", "AG", "HOLDINGS",
        "HOLDING", "GROUP", "THE", "NEW", "CL", "CLASS", "COM", "SHS", "LP", "LLC",
        "TRUST", "FUND", "ETF", "N", "V", "A", "B"}
ETF_NAME = re.compile(r"\bETF\b|EXCH(ANGE)?[\s-]*TRAD|INDEX FUND|\bFUND\b|\bTRUST\b|"
                      r"ISHARES|SPDR|INVESCO|PROSHARES|DIREXION|WISDOMTREE|VANECK", re.I)
BAND_NAMED = (0.2, 5.0)     # named match: FMP price (today) vs 13F price (quarter-end)
BAND_RENAMED = (0.5, 2.0)   # no name overlap: the price has to carry the proof
BAND_SEARCH = (0.67, 1.5)   # name-search tier: no CUSIP evidence at all, so tightest
QSTOP = STOP | {"SHS", "ORD", "US", "ADR", "ADS", "SPONSORED", "SPON", "UNSPON", "REG",
                "COMMON", "STOCK", "COR", "SE", "C", "NPV", "PAR", "USD", "EACH", "REPR"}
LISTED = {"NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "NYSEARCA", "CBOE", "BATS"}

def equity_cusip(c):
    """Issue number 10-89 = equity. Letters (345370CZ1 Ford notes) = debt;
    9x = options / other (78462F953 = a SPY put line)."""
    return c[6:8].isdigit() and "10" <= c[6:8] <= "89"

def name_words(issuer):
    s = unicodedata.normalize("NFKD", issuer or "").encode("ascii", "ignore").decode()
    return [w for w in re.split(r"[^A-Za-z0-9]+", s) if w and w.upper() not in QSTOP]

def name_queries(issuer):
    """'MIND MEDICINE MINDMED INC' -> ['MIND MEDICINE MINDMED', 'MIND MEDICINE', 'MIND'].
    Always anchored on the first distinctive word (the brand); generic trailing
    words alone ('Acquisition', 'Ventures') would match any SPAC near $10."""
    words = name_words(issuer)
    qs = [" ".join(words[:n]) for n in (3, 2, 1) if len(words) >= n]
    return list(dict.fromkeys(q for q in qs if len(q) >= 4))

def toks(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()   # Nestlé -> NESTLE
    return {t for t in re.split(r"[^A-Z0-9]+", s.upper()) if len(t) >= 3 and t not in STOP}

def get(path, **p):
    q = "&".join(f"{k}={v}" for k, v in p.items())
    url = f"{API}/{path}?{q}{'&' if q else ''}apikey={api_key()}"
    for attempt in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "60", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if isinstance(d, list):
                return d
        except ValueError:
            pass
        time.sleep(1.5 * (attempt + 1))       # transient errors must not read as "no match"
    return None

def implied_prices(conn):
    """CUSIP -> median 13F-implied USD price (value / shares) across every
    share-denominated line in the fund, prior-quarter and broker books."""
    px = defaultdict(list)
    for t in TABLES:
        for cusip, v, sh in conn.execute(f"""SELECT cusip, value_k, shares FROM {t}
                WHERE sh_type = 'SH' AND shares > 0 AND value_k > 0"""):
            px[cusip].append(v * 1000.0 / sh)
    return {c: statistics.median(v) for c, v in px.items()}

def run():
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    asof = time.strftime("%Y-%m-%d")
    prof = load_profiles()
    implied = implied_prices(conn)
    names = defaultdict(set)                     # CUSIP -> tokens of every issuer string filed
    for t in TABLES:
        for cusip, issuer in conn.execute(f"SELECT DISTINCT cusip, issuer FROM {t}"):
            names[cusip] |= toks(issuer)

    def px_ratio(cusip, sym):
        """FMP price (USD) / 13F-implied price; None when either side is unknown."""
        p = prof.get(sym or "") or {}
        fp, fx, ip = num(p.get("price")), _FX_USD.get(p.get("currency") or "USD"), implied.get(cusip)
        return fp * fx / ip if (fp and fx and ip) else None

    def in_band(r, band, unknown_ok):
        return unknown_ok if r is None else band[0] <= r <= band[1]

    def named(cusip, company):
        return bool(names.get(cusip, set()) & toks(company))

    # 1. curated entries outrank every source, and repair rows already applied
    for cusip, sym in CURATED.items():
        conn.execute("""INSERT INTO cusip_map VALUES (?,?,'common','curated',?)
            ON CONFLICT(cusip) DO UPDATE SET ticker=excluded.ticker, sec_type='common',
                source='curated', asof=excluded.asof""", (cusip, sym, asof))
        for t in TABLES:
            conn.execute(f"UPDATE {t} SET ticker=? WHERE cusip=?", (sym, cusip))

    # 2. re-audit every earlier FMP mapping under the current rules
    dropped = []
    for cusip, sym, src in conn.execute("""SELECT cusip, ticker, source FROM cusip_map
            WHERE source IN ('fmp', 'fmp-name') AND ticker IS NOT NULL""").fetchall():
        p = prof.get(sym) or {}
        r = px_ratio(cusip, sym)
        if src == "fmp-name":             # name-search pick: re-prove it every run
            bad = not (named(cusip, p.get("companyName")) and is_true(p.get("isActivelyTrading"))
                       and in_band(r, BAND_RENAMED, False))
        elif named(cusip, p.get("companyName")) or not p:
            bad = not in_band(r, BAND_NAMED, True)
        else:
            bad = not (is_true(p.get("isActivelyTrading")) and p.get("cusip") == cusip
                       and in_band(r, BAND_RENAMED, False))
        if bad:
            dropped.append((cusip, sym, r))
            conn.execute("DELETE FROM cusip_map WHERE cusip=? AND source=?", (cusip, src))
            for t in TABLES:
                conn.execute(f"UPDATE {t} SET ticker=NULL WHERE cusip=? AND ticker=?", (cusip, sym))
    conn.commit()

    # 3. Confirm EVERY held CUSIP against FMP's own CUSIP -> symbol index. The
    #    older name-derived tickers mislabel share classes and lines: Morgan
    #    Stanley / Goldman / Boeing / Oracle common carried preferred tickers
    #    (MS-PQ, GS-PD, BA-PA, ORCL-PD) and scored as preferreds; Berkshire A and
    #    B were crossed; Global Payments sat on Global Partners (GLP); six iShares
    #    CUSIPs collapsed onto GSG; RSP onto Invesco Ltd. A correction needs the
    #    FMP line to be US-listed, trading, priced within 2x of the 13F's own
    #    implied price, and either share a name token with the filing or replace
    #    a ticker that fails the price test.
    by_cusip = defaultdict(list)
    for s, p in prof.items():
        if p.get("cusip") and "." not in s and is_true(p.get("isActivelyTrading")):
            by_cusip[p["cusip"].upper()].append(s)
    cmap = {c: (tk, src) for c, tk, src in conn.execute("SELECT cusip, ticker, source FROM cusip_map")}
    held = defaultdict(Counter)
    for t in TABLES:
        for cusip, tk, n in conn.execute(f"SELECT cusip, ticker, COUNT(*) FROM {t} GROUP BY 1, 2"):
            held[cusip][tk] += n

    def is_fund(sym):
        p = prof.get(sym) or {}
        return is_true(p.get("isEtf")) or is_true(p.get("isFund"))

    corrected = []
    for cusip, tks in held.items():
        if not _valid_cusip(cusip) or cmap.get(cusip, (None, None))[1] == "curated":
            continue
        cands = [s for s in by_cusip.get(cusip, [])
                 if in_band(px_ratio(cusip, s), BAND_RENAMED, False)]
        if len(cands) > 1:                        # base line over -P / -WT siblings
            plain = [s for s in cands if "-" not in s]
            cands = plain if len(plain) == 1 else cands
        if len(cands) != 1:
            continue
        sym = cands[0]
        want = None if is_fund(sym) else sym      # funds stay NULL on holdings (ingest rule)
        if cmap.get(cusip, (None, None))[0] == sym and set(tks) <= {want}:
            continue                              # already right everywhere
        olds = [tk for tk in tks if tk and tk != sym]
        if olds and not named(cusip, prof[sym].get("companyName")) and all(
                in_band(px_ratio(cusip, tk), BAND_NAMED, True) for tk in olds):
            continue                              # no name proof and nothing visibly wrong
        conn.execute("""INSERT INTO cusip_map VALUES (?,?,?,'fmp',?)
            ON CONFLICT(cusip) DO UPDATE SET ticker=excluded.ticker, sec_type=excluded.sec_type,
                source='fmp', asof=excluded.asof WHERE cusip_map.source <> 'curated'""",
            (cusip, sym, "etf" if want is None else "common", asof))
        for t in TABLES:
            conn.execute(f"UPDATE {t} SET ticker=? WHERE cusip=? AND ticker IS NOT ?", (want, cusip, want))
        corrected.append((cusip, sym, dict(tks)))
    conn.commit()
    print(f"FMP confirmation: corrected {len(corrected):,} held CUSIPs "
          f"({sum(1 for c in corrected if any(c[2].keys() - {None}))} had a wrong ticker, "
          f"the rest were unmapped)", flush=True)
    for cusip, sym, tks in sorted(corrected, key=lambda c: -sum(c[2].values()))[:15]:
        print(f"  {cusip} -> {sym:7s} was {tks}")

    todo = conn.execute("""
        WITH u AS (
          SELECT cusip, issuer, value_k FROM fund_13f_holdings WHERE ticker IS NULL
          UNION ALL SELECT cusip, issuer, value_k FROM fund_13f_prior WHERE ticker IS NULL
          UNION ALL SELECT cusip, issuer, value_k FROM broker_13f WHERE ticker IS NULL)
        SELECT u.cusip, MAX(u.issuer), SUM(u.value_k)/1e3 FROM u
        LEFT JOIN cusip_map cm ON cm.cusip = u.cusip
        WHERE u.cusip IS NOT NULL AND length(u.cusip) = 9 AND cm.ticker IS NULL
        GROUP BY u.cusip""").fetchall()
    todo = [t for t in todo if _valid_cusip(t[0])]
    etfs = {r.get("symbol") for r in (get("etf-list") or [])}
    print(f"resolving {len(todo):,} unmapped CUSIPs via FMP ({len(prof):,} profiles, "
          f"{len(etfs):,} ETF symbols loaded); re-audit dropped {len(dropped)} earlier FMP picks",
          flush=True)
    for cusip, sym, r in dropped[:10]:
        print(f"  dropped {cusip} -> {sym}  (FMP/13F price ratio {r:.2f})" if r else
              f"  dropped {cusip} -> {sym}  (renamed-tier proof missing)")

    def fund_like(sym, issuer):
        p = prof.get(sym)
        if p is not None:                   # FMP's own flags are authoritative
            return is_true(p.get("isEtf")) or is_true(p.get("isFund"))
        return sym in etfs or bool(ETF_NAME.search(issuer or ""))

    def resolve(t):
        cusip, issuer, v = t
        d = get("search-cusip", cusip=cusip)
        if d is None:
            return cusip, issuer, v, None, "error"
        if not d:
            return cusip, issuer, v, None, "no-match"
        ok = [x for x in d if named(cusip, x.get("companyName"))]
        if ok:
            ok = [x for x in ok if in_band(px_ratio(cusip, x.get("symbol")), BAND_NAMED, True)]
            if not ok:
                return cusip, issuer, v, d[0].get("symbol"), "price-mismatch"
            us = [x for x in ok if "." not in (x.get("symbol") or "")]
            best = max(us or ok, key=lambda x: x.get("marketCap") or 0)
            return cusip, issuer, v, best.get("symbol"), "ok"
        # Renamed issuer: FMP's OWN profile for the symbol must carry this
        # exact CUSIP, the line must still trade, and the price must agree.
        conf = [x for x in d
                if (prof.get(x.get("symbol") or "") or {}).get("cusip") == cusip
                and is_true(prof[x["symbol"]].get("isActivelyTrading"))
                and in_band(px_ratio(cusip, x["symbol"]), BAND_RENAMED, False)]
        if len(conf) == 1:
            return cusip, issuer, v, conf[0].get("symbol"), "ok-renamed"
        return cusip, issuer, v, d[0].get("symbol"), "name-mismatch"

    def search_by_name(cusip, issuer):
        """Third tier, for equity lines FMP's CUSIP index lacks (Indivior after
        its US redomicile, Qiagen's post-consolidation shares, fresh IPOs like
        INNIO): search by issuer name, then demand a shared name token, a live
        US line, a price within 1.5x of the 13F's, and a single survivor."""
        words = name_words(issuer)
        if not words:
            return None
        brand = toks(words[0])
        for q in name_queries(issuer):
            d = get("search-name", query=urllib.parse.quote(q))
            if not d:
                continue
            ok = []
            for x in d:
                s = x.get("symbol") or ""
                p = prof.get(s)
                if ("." in s or not p or not is_true(p.get("isActivelyTrading"))
                        or not (brand and brand <= toks(p.get("companyName")))
                        or not in_band(px_ratio(cusip, s), BAND_SEARCH, False)):
                    continue
                ok.append(s)
            listed = [s for s in ok if (prof[s].get("exchange") or "").upper() in LISTED]
            ok = listed or ok
            if len(set(ok)) == 1:
                return ok[0]
            if ok:
                return None                  # several plausible lines: leave it unmapped
        return None

    def resolve_all(t):
        r = resolve(t)
        if r[4] in ("no-match", "name-mismatch", "price-mismatch") and equity_cusip(t[0]):
            s = search_by_name(t[0], t[1])
            if s:
                return t[0], t[1], t[2], s, "ok-name"
        return r

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(resolve_all, todo))

    n_common = n_etf = 0
    val_common = 0.0
    for cusip, issuer, v, sym, status in res:
        if status not in ("ok", "ok-renamed", "ok-name") or not sym or not _valid_ticker(sym):
            continue
        is_etf = fund_like(sym, issuer)
        st = "etf" if is_etf else "common"
        conn.execute("""INSERT INTO cusip_map VALUES (?,?,?,?,?)
            ON CONFLICT(cusip) DO UPDATE SET ticker=excluded.ticker, sec_type=excluded.sec_type,
                source=excluded.source, asof=excluded.asof
            WHERE cusip_map.ticker IS NULL""",
            (cusip, sym, st, "fmp-name" if status == "ok-name" else "fmp", asof))
        if is_etf:
            n_etf += 1
        else:
            n_common += 1
            val_common += v or 0
    # reconcile: earlier FMP rows tagged 'common' that FMP's profile flags as an
    # ETF / fund (closed-end funds like BDJ, MQY; fund lines like MSLC) -> 'etf',
    # and pull their tickers back off the holdings so they leave stock signals.
    fixed_etf = 0
    for cusip, sym in conn.execute("""SELECT cusip, ticker FROM cusip_map
            WHERE source IN ('fmp', 'fmp-name') AND sec_type = 'common' AND ticker IS NOT NULL""").fetchall():
        p = prof.get(sym)
        if p is not None and (is_true(p.get("isEtf")) or is_true(p.get("isFund"))):
            conn.execute("UPDATE cusip_map SET sec_type='etf' WHERE cusip=?", (cusip,))
            for t in TABLES:
                conn.execute(f"UPDATE {t} SET ticker=NULL WHERE cusip=? AND ticker=?", (cusip, sym))
            fixed_etf += 1
    # back-apply COMMON mappings (ETFs stay NULL in holdings by convention)
    applied = 0
    for t in TABLES:
        applied += conn.execute(f"""UPDATE {t}
            SET ticker = (SELECT ticker FROM cusip_map WHERE cusip = {t}.cusip)
            WHERE ticker IS NULL AND cusip IN
              (SELECT cusip FROM cusip_map WHERE ticker IS NOT NULL AND sec_type = 'common')""").rowcount
    conn.commit()
    print("outcomes:", dict(Counter(r[4] for r in res)))
    print(f"mapped: {n_common:,} common (${val_common/1e3:,.1f}B held) + {n_etf:,} ETF/fund; "
          f"reclassified {fixed_etf} fund lines to etf; back-applied to {applied:,} holding rows")
    for r in sorted([r for r in res if r[4] in ("ok", "ok-renamed", "ok-name")
                     and not fund_like(r[3], r[1])], key=lambda r: -(r[2] or 0))[:15]:
        print(f"  {r[3]:8s} ${r[2]:>7,.0f}M  {(r[1] or '')[:40]}  [{r[4]}]")
    for r in sorted([r for r in res if r[4] == "price-mismatch"], key=lambda r: -(r[2] or 0))[:8]:
        print(f"  REJECTED {r[3]:8s} ${r[2]:>7,.0f}M  {(r[1] or '')[:40]}  "
              f"[price ratio {px_ratio(r[0], r[3]) or 0:.2f}]")
    conn.close()

if __name__ == "__main__":
    run()
