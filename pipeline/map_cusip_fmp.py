"""Recover unmapped 13F CUSIPs via FMP's CUSIP search.

~1,200 holdings CUSIPs had no ticker (issuer-name quirks like "BRISTOL-MYER
SQB", ADR/NY-registry lines, post-IPO names) and were excluded from every
signal. FMP maps CUSIP -> listed symbol directly. Guardrails:
  * name validation — FMP's company name must share a real token with the
    13F issuer string, else rejected (caught "Ferguson Plc" -> Ferroglobe, and
    one-trust-many-ETF CUSIP families like "BLACKROCK ETF TRUST II");
  * prefer the US listing when FMP returns several venues;
  * ETFs / funds are recorded as sec_type 'etf' (kept out of stock signals);
  * fill gaps, never clobber: only CUSIPs with no ticker in cusip_map are
    written, and composite venue junk (TRI4EUR) is refused.
Verified aliases the token check can't see (SPACEX vs "Space Exploration
Technologies") live in CURATED.
"""
import json, os, re, sqlite3, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enrich_fmp import api_key, API, DB
from build_cusip_map import _valid_cusip, _valid_ticker

# CUSIP -> ticker, verified by hand (FMP match + profile check)
CURATED = {
    "84615Q103": "SPCX",   # SpaceX — IPO'd on NASDAQ 2026-06-12; 13F issuer reads "SPACEX"
}
STOP = {"INC", "CORP", "CORPORATION", "CO", "LTD", "PLC", "NV", "SA", "AG", "HOLDINGS",
        "HOLDING", "GROUP", "THE", "NEW", "CL", "CLASS", "COM", "SHS", "LP", "LLC",
        "TRUST", "FUND", "ETF", "N", "V", "A", "B"}
ETF_NAME = re.compile(r"\bETF\b|EXCH(ANGE)?[\s-]*TRAD|INDEX FUND|\bFUND\b|\bTRUST\b|"
                      r"ISHARES|SPDR|INVESCO|PROSHARES|DIREXION|WISDOMTREE|VANECK", re.I)

def toks(s):
    return {t for t in re.split(r"[^A-Z0-9]+", (s or "").upper()) if len(t) >= 3 and t not in STOP}

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

def run():
    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
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
    print(f"resolving {len(todo):,} unmapped CUSIPs via FMP ({len(etfs):,} ETF symbols loaded)", flush=True)

    def resolve(t):
        cusip, issuer, v = t
        if cusip in CURATED:
            return cusip, issuer, v, CURATED[cusip], "curated"
        d = get("search-cusip", cusip=cusip)
        if d is None:
            return cusip, issuer, v, None, "error"
        if not d:
            return cusip, issuer, v, None, "no-match"
        it = toks(issuer)
        ok = [x for x in d if it & toks(x.get("companyName"))]
        if not ok:
            return cusip, issuer, v, d[0].get("symbol"), "name-mismatch"
        us = [x for x in ok if "." not in (x.get("symbol") or "")]
        best = max(us or ok, key=lambda x: x.get("marketCap") or 0)
        return cusip, issuer, v, best.get("symbol"), "ok"

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(resolve, todo))

    asof = time.strftime("%Y-%m-%d")
    n_common = n_etf = 0
    val_common = 0.0
    for cusip, issuer, v, sym, status in res:
        if status not in ("ok", "curated") or not sym or not _valid_ticker(sym):
            continue
        is_etf = sym in etfs or bool(ETF_NAME.search(issuer or ""))
        st = "etf" if is_etf else "common"
        src = "curated" if status == "curated" else "fmp"
        conn.execute("""INSERT INTO cusip_map VALUES (?,?,?,?,?)
            ON CONFLICT(cusip) DO UPDATE SET ticker=excluded.ticker, sec_type=excluded.sec_type,
                source=excluded.source, asof=excluded.asof
            WHERE cusip_map.ticker IS NULL""", (cusip, sym, st, src, asof))
        if is_etf:
            n_etf += 1
        else:
            n_common += 1
            val_common += v or 0
    # back-apply COMMON mappings (ETFs stay NULL in holdings by convention)
    applied = 0
    for tbl in ("fund_13f_holdings", "fund_13f_prior", "broker_13f"):
        applied += conn.execute(f"""UPDATE {tbl}
            SET ticker = (SELECT ticker FROM cusip_map WHERE cusip = {tbl}.cusip)
            WHERE ticker IS NULL AND cusip IN
              (SELECT cusip FROM cusip_map WHERE ticker IS NOT NULL AND sec_type = 'common')""").rowcount
    conn.commit()
    from collections import Counter
    print("outcomes:", dict(Counter(r[4] for r in res)))
    print(f"mapped: {n_common:,} common (${val_common/1e3:,.1f}B held) + {n_etf:,} ETF/fund; "
          f"back-applied to {applied:,} holding rows")
    for r in sorted([r for r in res if r[4] in ("ok", "curated") and not ETF_NAME.search(r[1] or "")],
                    key=lambda r: -(r[2] or 0))[:12]:
        print(f"  {r[3]:8s} ${r[2]:>7,.0f}M  {(r[1] or '')[:44]}")
    conn.close()

if __name__ == "__main__":
    run()
