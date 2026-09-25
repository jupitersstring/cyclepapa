"""cyclepapa data store: one security master, one point-in-time fact store, one event store.

Why: the books were built from 240+ loose JSON/CSV files keyed three different ways
(`LOCAL`, `LOCAL.PA`, `EPA:LOCAL`), with 66 modules reading an old quote store and no
history kept. Most audit defects (ticker collisions, notes / preferreds treated as
stock, duplicate issuers, missing CIKs, ADR share-basis errors, a tab showing a value
the validator had rejected) come from that. This module is the single place to ask
"which security is this, which issuer is it, and what do we know about it as of date X".

Tables (SQLite, data/cyclepapa.db -- rebuilt from caches, not committed):

  issuers     issuer_id (CIK:<n> | CUSIP6:<x> | NAME:<country>:<name>), name, cik, country,
              sector, industry, kind (bank / insurer / reit / mreit / ep / operating / ...)
  securities  security_id (the FMP symbol, or X:<EXCH>:<SYM> when FMP has none), issuer_id,
              ticker, exchange, currency, isin, cusip, sec_type (common / adr / otc_line /
              note_pref / fund / spac / warrant_right_unit / bankrupt), status (active /
              delisted), delisted_date, is_primary, adv_usd
  aliases     alias -> security_id (FMP symbol, exchange-qualified forms EPA:LOCAL /
              XETR:TKA / HKEX:03991.HK, bare tickers where unambiguous, CIK0000123456,
              old tickers such as UREE -> USAR)
  facts       security_id, field, value, text, unit, currency, as_of, source, method,
              validated, run_id -- APPEND-ONLY: every run adds a dated snapshot, so any
              value can be read as of any past run
  events      one table for every dated fact-of-life: 8-K events (with the reviewed verdict),
              13D/13G moves, insider buys and sells, filing red flags, executive appointments,
              earnings-call commitments -- one taxonomy, one timeline per issuer
  runs        run_id, started, note

API: connect(), resolve(identifier), issuer_of(security_id), latest(security_id, field),
facts_asof(field, as_of), timeline(issuer_id), primary(issuer_id).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
DB = ROOT / "data" / "cyclepapa.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY, started TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS issuers (
  issuer_id TEXT PRIMARY KEY, name TEXT, cik TEXT, country TEXT, sector TEXT, industry TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS securities (
  security_id TEXT PRIMARY KEY, issuer_id TEXT, name TEXT, ticker TEXT, exchange TEXT, currency TEXT,
  isin TEXT, cusip TEXT, sec_type TEXT, status TEXT, delisted_date TEXT, is_primary INTEGER DEFAULT 0,
  adv_usd REAL);
CREATE INDEX IF NOT EXISTS sec_issuer ON securities(issuer_id);
CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, security_id TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS facts (
  security_id TEXT, field TEXT, value REAL, text TEXT, unit TEXT, currency TEXT, as_of TEXT,
  source TEXT, method TEXT, validated INTEGER, run_id INTEGER);
CREATE INDEX IF NOT EXISTS facts_key ON facts(security_id, field, as_of);
CREATE INDEX IF NOT EXISTS facts_field ON facts(field, as_of);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, security_id TEXT, issuer_id TEXT, date TEXT, type TEXT, family TEXT,
  source TEXT, doc_url TEXT, amount_usd REAL, counterparty TEXT, per_share REAL, status TEXT,
  verdict TEXT, reviewed INTEGER, what TEXT, evidence TEXT, extra TEXT, run_id INTEGER);
CREATE INDEX IF NOT EXISTS ev_issuer ON events(issuer_id, date);
CREATE INDEX IF NOT EXISTS ev_type ON events(type, date);
"""

# exchange prefixes used by the risk-reward engine / YAML -> FMP symbol suffix
EXCH_SUFFIX = {"EPA": ".PA", "XETR": ".DE", "FRA": ".F", "LSE": ".L", "LON": ".L", "TSE": ".T", "JPX": ".T",
               "KRX": ".KS", "KOSDAQ": ".KQ", "HKEX": ".HK", "HK": ".HK", "BME": ".MC", "SZSE": ".SZ",
               "SSE": ".SS", "BIT": ".MI", "AMS": ".AS", "EBR": ".BR", "SWX": ".SW", "STO": ".ST",
               "OSL": ".OL", "CPH": ".CO", "HEL": ".HE", "ASX": ".AX", "TSX": ".TO", "TSXV": ".V",
               "NZX": ".NZ", "JSE": ".JO", "TASE": ".TA", "BVMF": ".SA", "BMV": ".MX", "NSE": ".NS",
               "BSE": ".BO", "SGX": ".SI", "IDX": ".JK", "SET": ".BK", "KLSE": ".KL", "TWSE": ".TW",
               "WSE": ".WA", "VIE": ".VI", "ISE": ".IR", "ATH": ".AT", "IST": ".IS", "BVB": ".RO",
               "B3": ".SA", "BOVESPA": ".SA", "BCBA": ".BA", "SZ": ".SZ", "SS": ".SS", "KS": ".KS", "T": ".T"}
US_EXCH = {"NASDAQ", "NYSE", "AMEX", "NYSE American", "NYSEArca", "OTC", "PNK", "CBOE", "BATS"}
OLD_TICKERS = {"UREE": "USAR"}        # renamed / wrong tickers still used by inputs


def connect(readonly=False):
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{DB}?mode=ro" if readonly else str(DB), uri=readonly, timeout=60)
    con.row_factory = sqlite3.Row
    if not readonly:
        con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ resolver
_ALIAS: dict | None = None


def _aliases():
    global _ALIAS
    if _ALIAS is None:
        try:
            con = connect(readonly=True)
            _ALIAS = {r["alias"]: r["security_id"] for r in con.execute("SELECT alias, security_id FROM aliases")}
        except sqlite3.Error:
            _ALIAS = {}
    return _ALIAS


def normalise(ident: str) -> list[str]:
    """Candidate spellings of an identifier, most specific first."""
    s = str(ident or "").strip().replace("●", "").strip()
    if not s:
        return []
    out = [s, s.upper()]
    m = re.match(r"^([A-Z0-9]+):(.+)$", s.upper())
    if m:
        ex, sym = m.groups()
        suf = EXCH_SUFFIX.get(ex)
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", sym):
            out.append("ISIN:" + sym)                       # an ISIN sitting in the ticker slot
        hk = re.fullmatch(r"0*(\d{1,5})(?:\.HK)?", sym) if (suf == ".HK" or sym.endswith(".HK")) else None
        if hk:
            out.append(f"{int(hk.group(1)):04d}.HK")        # HKEX:00005.HK -> 0005.HK
        if sym.endswith(tuple(EXCH_SUFFIX.values())):
            out.append(sym)
        elif suf:
            out.append(sym + suf)
        out.append(sym)
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", s.upper()):
        out.append("ISIN:" + s.upper())
    if s.upper().startswith("CIK"):
        out.append("CIK" + str(int(re.sub(r"\D", "", s) or 0)))
    if s.upper() in OLD_TICKERS:
        out.insert(0, OLD_TICKERS[s.upper()])
    return list(dict.fromkeys(out))


def resolve(ident: str):
    """Any identifier (FMP symbol, EXCH:SYM, bare ticker, CIK..., old ticker) -> security_id or None."""
    al = _aliases()
    for c in normalise(ident):
        if c in al:
            return al[c]
    return None


def issuer_of(security_id, con=None):
    con = con or connect(readonly=True)
    r = con.execute("SELECT issuer_id FROM securities WHERE security_id=?", (security_id,)).fetchone()
    return r["issuer_id"] if r else None


def primary(issuer_id, con=None):
    con = con or connect(readonly=True)
    r = con.execute("SELECT security_id FROM securities WHERE issuer_id=? AND is_primary=1", (issuer_id,)).fetchone()
    return r["security_id"] if r else None


def security(ident, con=None):
    sid = resolve(ident)
    if not sid:
        return None
    con = con or connect(readonly=True)
    r = con.execute("SELECT * FROM securities WHERE security_id=?", (sid,)).fetchone()
    return dict(r) if r else None


def latest(security_id, field, validated_only=True, as_of=None, con=None):
    """The most recent value of a field (validated sources only by default), optionally as of a date."""
    con = con or connect(readonly=True)
    q = ("SELECT value, text, source, as_of FROM facts WHERE security_id=? AND field=?"
         + (" AND validated=1" if validated_only else "") + (" AND as_of<=?" if as_of else "")
         + " ORDER BY as_of DESC, run_id DESC LIMIT 1")
    r = con.execute(q, (security_id, field, as_of) if as_of else (security_id, field)).fetchone()
    return dict(r) if r else None


def facts_asof(field, as_of, con=None):
    """{security_id: value} for one field as it stood on a date (point in time)."""
    con = con or connect(readonly=True)
    rows = con.execute("""SELECT f.security_id, f.value FROM facts f JOIN (
                            SELECT security_id, MAX(as_of) m FROM facts WHERE field=? AND validated=1 AND as_of<=?
                            GROUP BY security_id) x ON f.security_id=x.security_id AND f.as_of=x.m
                          WHERE f.field=? AND f.validated=1""", (field, as_of, field)).fetchall()
    return {r["security_id"]: r["value"] for r in rows}


def timeline(issuer_id, con=None, types=None):
    con = con or connect(readonly=True)
    q = "SELECT * FROM events WHERE issuer_id=?" + (f" AND type IN ({','.join('?' * len(types))})" if types else "") \
        + " ORDER BY date DESC"
    return [dict(r) for r in con.execute(q, (issuer_id, *(types or [])))]


def new_run(con, note=""):
    cur = con.execute("INSERT INTO runs(started, note) VALUES (?, ?)", (time.strftime("%Y-%m-%dT%H:%M:%S"), note))
    return cur.lastrowid


def reload_aliases():
    global _ALIAS
    _ALIAS = None
    return _aliases()


# ------------------------------------------------------------------ helpers for the book builders
_SEC: dict | None = None


def _secs():
    global _SEC
    if _SEC is None:
        try:
            con = connect(readonly=True)
            _SEC = {r["security_id"]: (r["issuer_id"], r["sec_type"], r["status"], r["name"], r["is_primary"])
                    for r in con.execute("SELECT security_id, issuer_id, sec_type, status, name, is_primary FROM securities")}
        except sqlite3.Error:
            _SEC = {}
    return _SEC


EQUITY_TYPES = {"common", "adr", "otc_line"}


def sec_type_of(ident):
    """'common' / 'adr' / 'otc_line' / 'note_pref' / 'fund' / 'spac' / 'warrant_right_unit' / 'bankrupt', or None."""
    sid = resolve(ident)
    x = _secs().get(sid) if sid else None
    return x[1] if x else None


def issuer_key(ident):
    """Issuer id for grouping share lines (CIK-based where known)."""
    sid = resolve(ident)
    x = _secs().get(sid) if sid else None
    return x[0] if x else None
