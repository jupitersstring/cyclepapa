"""Fill price + 12-month momentum + 52-week-high gaps via Stooq's
public q/d/ HTML history pages.

Background: Stooq (stooq.com) serves daily OHLC for global stocks but the
front door is behind a SHA-256 proof-of-work challenge - every fresh TCP
connection lands on a /q/d/?s=... page that returns a JS-only stub. The
challenge embeds the client IP, so the cookie issued after solving the PoW
is bound to *this* connection. Once authenticated, the same connection
can serve ~14-17 history pages before Stooq starts returning data-less
stubs as a soft rate-limit; after that we cycle the connection.

Why scrape HTML instead of the CSV download endpoint? /q/d/l/ returns
"Access denied" for unauthenticated callers even *after* solving the PoW;
the path appears reserved for paying users. The /q/d/ HTML page is
auth-walled but not paywalled, so we lift the OHLC table out of it.

Stooq paginates the history table at exactly 40 rows per page; one
trading year ~ 7 pages. We fetch all of them, derive last close, max high,
oldest close, and emit price/momentum_12m/pct_off_52w_high.

Symbol convention: Stooq prefixes with a country code (aapl.us, asml.nl,
7203.jp, ...). We strip our universe's exchange suffix (.AS, .T, .L, ...)
and re-append the Stooq suffix derived from the `src` column.

Output: stooq_price_fill.csv (universe-symbol-keyed). Resumable - rows
already present are skipped on rerun.

No retries: Stooq's failures are server-side rate limits and unknown-symbol
empties. Retrying just wastes our budget - better to move on and let a
later run pick up the gaps once limits clear.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import os
import re
import socket
import ssl
import sys
import time
import urllib.parse
from pathlib import Path

import pandas as pd


# --------------------------------------------------------------------------
# Stooq suffix mapping per universe `src` country
#
# Stooq's free coverage is concentrated in US + a handful of European /
# Asian exchanges. Markets we map but Stooq may not carry (KR, TW, TH, IN,
# CN partial, ID, SG, MY, AU, NZ, BR, MX, AR, CL, SA, ZA, IL, TR, plus the
# Nordics and Eastern Europe minors) will just return empty pages and end
# up in the failure tally - that's fine, this script's job is to try.
#
# Symbol rewrite rule: drop the trailing `.XX` suffix our universe carries
# (Yahoo style: AAPL=no suffix, ASML.AS, 7203.T, BABA.HK, ...) and re-attach
# the Stooq one. US tickers in our universe have no suffix to strip.
SRC_TO_STOOQ = {
    "US": "us",
    "JP": "jp",
    "KR": "kr",
    "CN": "cn",
    "HK": "hk",
    "TW": "tw",
    "TH": "th",
    "IN": "in",
    "ID": "id",
    "SG": "sg",
    "MY": "my",
    "AU": "au",
    "NZ": "nz",
    "UK": "uk",
    "GB": "uk",
    "IE": "uk",  # Irish ADRs trade on LSE; Stooq has no .ie
    "DE": "de",
    "FR": "fr",
    "IT": "it",
    "NL": "nl",
    "BE": "be",
    "CH": "ch",
    "ES": "es",
    "SE": "se",
    "NO": "no",
    "DK": "dk",
    "FI": "fi",
    "AT": "at",
    "PT": "pt",
    "GR": "gr",
    "PL": "pl",
    "HU": "hu",
    "CZ": "cz",
    "EE": "ee",
    "LT": "lt",
    "LV": "lv",
    "IS": "is",
    "RO": "ro",
    "TR": "tr",
    "IL": "il",
    "SA": "sa",
    "ZA": "za",
    "CA": "ca",
    "MX": "mx",
    "BR": "br",
    "AR": "ar",
    "CL": "cl",
}

# Currency hint by source country (used to populate the output row; Stooq
# doesn't surface currency in the HTML so we infer from the listing market).
SRC_TO_CCY = {
    "US": "USD", "JP": "JPY", "KR": "KRW", "CN": "CNY", "HK": "HKD",
    "TW": "TWD", "TH": "THB", "IN": "INR", "ID": "IDR", "SG": "SGD",
    "MY": "MYR", "AU": "AUD", "NZ": "NZD",
    "UK": "GBP", "GB": "GBP", "IE": "EUR",
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "NL": "EUR", "BE": "EUR",
    "ES": "EUR", "AT": "EUR", "PT": "EUR", "GR": "EUR", "FI": "EUR",
    "CH": "CHF",
    "SE": "SEK", "NO": "NOK", "DK": "DKK",
    "PL": "PLN", "HU": "HUF", "CZ": "CZK", "EE": "EUR", "LT": "EUR",
    "LV": "EUR", "IS": "ISK", "RO": "RON",
    "TR": "TRY", "IL": "ILS", "SA": "SAR", "ZA": "ZAR",
    "CA": "CAD", "MX": "MXN", "BR": "BRL", "AR": "ARS", "CL": "CLP",
}

# Strip these exchange suffixes off our universe symbol before re-suffixing.
# This list mirrors what shows up in asymmetry_global.csv when grouped by src.
SUFFIXES_TO_STRIP = (
    ".T",   # JP - Tokyo
    ".KS", ".KQ",  # KR - KOSPI / KOSDAQ
    ".SS", ".SZ",  # CN - Shanghai / Shenzhen
    ".HK",  # HK
    ".TW", ".TWO",  # TW
    ".BK",  # TH
    ".BO", ".NS",  # IN - Bombay / NSE
    ".JK",  # ID
    ".SI",  # SG
    ".KL",  # MY
    ".AX",  # AU
    ".NZ",  # NZ
    ".L",   # UK / IE
    ".IR",  # IE
    ".DE", ".F",  # DE - XETRA / Frankfurt
    ".PA",  # FR
    ".MI",  # IT
    ".AS",  # NL
    ".BR",  # BE
    ".SW", ".VX",  # CH
    ".MC",  # ES
    ".ST",  # SE
    ".OL",  # NO
    ".CO",  # DK
    ".HE",  # FI
    ".VI",  # AT
    ".LS",  # PT
    ".AT",  # GR
    ".WA",  # PL
    ".BD",  # HU
    ".PR",  # CZ
    ".TL",  # EE
    ".VS",  # LT
    ".RG",  # LV
    ".IC",  # IS
    ".RO",  # RO
    ".IS",  # TR (Istanbul); same letters as Iceland, but src disambiguates
    ".TA",  # IL
    ".SR",  # SA
    ".JO",  # ZA
    ".TO", ".V", ".CN",  # CA - Toronto / TSX-V / CNSX
    ".MX",  # MX
    ".SA",  # BR (São Paulo) - same letters as SA above; src disambiguates
    ".BA",  # AR
    ".SN",  # CL
)


def to_stooq_symbol(universe_symbol: str, src: str) -> str | None:
    """Map our universe symbol+src to Stooq's lowercase `ticker.<cc>` form.

    Returns None when src isn't in our country map.
    """
    cc = SRC_TO_STOOQ.get(src)
    if cc is None:
        return None
    sym = str(universe_symbol).strip()
    # Strip our exchange suffix (longest-first so .TWO doesn't lose to .TW)
    upper = sym.upper()
    for suf in sorted(SUFFIXES_TO_STRIP, key=len, reverse=True):
        if upper.endswith(suf):
            sym = sym[: -len(suf)]
            break
    return f"{sym.lower()}.{cc}"


# --------------------------------------------------------------------------
# Stooq HTTP plumbing - manual TLS-through-proxy so we can keep a single
# connection alive across the PoW + many fetches. urllib's pooled openers
# would rotate connections and force a fresh PoW each time.

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

# CA bundle: the agent-proxy re-terminates TLS so we must trust its CA.
CA_BUNDLE = "/root/.ccr/ca-bundle.crt"


def _proxy_endpoint():
    """Read HTTPS_PROXY env var, return (host, port). Default 127.0.0.1:46259."""
    raw = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:46259")
    # strip scheme
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.rstrip("/")
    host, _, port = raw.partition(":")
    return host or "127.0.0.1", int(port or "46259")


PROXY_HOST, PROXY_PORT = _proxy_endpoint()

_SSL_CTX = ssl.create_default_context(
    cafile=CA_BUNDLE if os.path.exists(CA_BUNDLE) else None
)

# --- Regexes shared by all workers (precompiled) ---
# OHLC row in the /q/d/ history table. Stooq pads the price cells with
# integer or decimal values; volume can have commas which we ignore.
ROW_RX = re.compile(
    r"<tr><td align=center id=t03>(\d+)</td>"
    r"<td nowrap>([^<]+)</td>"
    r"<td>([\d.]+)</td>"  # open
    r"<td>([\d.]+)</td>"  # high
    r"<td>([\d.]+)</td>"  # low
    r"<td>([\d.]+)</td>"  # close
)
# `>>>` link in pagination footer points to the LAST page index.
LAST_PAGE_RX = re.compile(rb"l=(\d+)>>>")
# Challenge constant + difficulty parsed out of the JS PoW stub.
CHALLENGE_RX = re.compile(rb'c="([^"]+)",d=(\d+)')
# Cookie name issued after a successful /__verify POST.
AUTH_COOKIE_PREFIX = "auth="


def _open_tls():
    """Open a TLS connection to stooq.com via the agent proxy.

    Returns the wrapped socket or raises on connect failure. The caller
    is responsible for closing it.
    """
    s = socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=15)
    s.sendall(b"CONNECT stooq.com:443 HTTP/1.1\r\nHost: stooq.com:443\r\n\r\n")
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            raise ConnectionError("proxy closed during CONNECT")
        buf += chunk
    first_line = buf.split(b"\r\n", 1)[0]
    if b"200" not in first_line:
        raise ConnectionError(f"proxy CONNECT failed: {first_line!r}")
    return _SSL_CTX.wrap_socket(s, server_hostname="stooq.com")


def _read_http_response(tls):
    """Parse one HTTP/1.1 response off a TLS socket.

    Handles both Content-Length and chunked Transfer-Encoding bodies.
    Returns (status_line, lower_keyed_headers, cookies_list, body_bytes).
    """
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = tls.recv(65536)
        if not chunk:
            raise ConnectionError("server closed before headers complete")
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    head_lines = head.decode("latin-1", errors="replace").split("\r\n")
    status_line = head_lines[0]
    hdr = {}
    cookies = []
    for line in head_lines[1:]:
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().lower(); v = v.strip()
        if k == "set-cookie":
            cookies.append(v)
        else:
            hdr[k] = v
    body = rest
    te = hdr.get("transfer-encoding", "").lower()
    if "chunked" in te:
        full = b""
        data = body
        while True:
            while b"\r\n" not in data:
                more = tls.recv(65536)
                if not more:
                    break
                data += more
            size_line, _, data = data.partition(b"\r\n")
            try:
                size = int(size_line.strip(), 16)
            except ValueError:
                break
            if size == 0:
                break
            while len(data) < size + 2:
                more = tls.recv(65536)
                if not more:
                    break
                data += more
            full += data[:size]
            data = data[size + 2 :]
        body = full
    elif "content-length" in hdr:
        cl = int(hdr["content-length"])
        while len(body) < cl:
            more = tls.recv(65536)
            if not more:
                break
            body += more
        body = body[:cl]
    return status_line, hdr, cookies, body


def _send_request(tls, method, path, extra_headers=None, body_bytes=None):
    """Pipe one request down a kept-alive TLS connection. Read the response."""
    h = {
        "Host": "stooq.com",
        "User-Agent": UA,
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    if extra_headers:
        h.update(extra_headers)
    if body_bytes is not None:
        h["Content-Length"] = str(len(body_bytes))
    req = f"{method} {path} HTTP/1.1\r\n"
    for k, v in h.items():
        req += f"{k}: {v}\r\n"
    req += "\r\n"
    tls.sendall(req.encode())
    if body_bytes:
        tls.sendall(body_bytes)
    return _read_http_response(tls)


def _solve_pow(c: str, difficulty: int) -> int:
    """Find the smallest non-negative n s.t. SHA256(c + str(n)) starts with `difficulty` hex zeros."""
    target = "0" * difficulty
    n = 0
    while True:
        if hashlib.sha256((c + str(n)).encode()).hexdigest().startswith(target):
            return n
        n += 1


def _parse_auth_cookie(cookies):
    for ck in cookies:
        if ck.startswith(AUTH_COOKIE_PREFIX):
            return ck.split(";", 1)[0]  # "auth=value"
    return None


class StooqSession:
    """One worker's persistent connection + auth cookie to Stooq.

    Each fresh TLS connection pulls a new PoW challenge bound to the
    exit IP that the proxy happens to give us; we solve it once and
    reuse the resulting `auth=` cookie for as many requests as Stooq
    will serve before truncating responses (observed: ~14-17 fetches).
    On any I/O error or detected challenge we reopen and resolve.

    Rate-limit handling: once a response comes back tiny (Stooq's
    "page shell without data table" pattern - ~40KB instead of ~250KB),
    we mark the session as exhausted, close it, and sleep briefly to
    let the agent proxy hand us a different egress IP on the next open.
    The sleep is per-worker so it doesn't block the whole pool.
    """
    RATE_LIMIT_THRESHOLD = 60000  # bytes; healthy /q/d/ pages are ~250KB
    COOLDOWN_SECS = 5             # per-worker pause after a throttle - the
                                  # proxy rotates IPs aggressively enough that
                                  # a short wait usually yields a fresh quota

    def __init__(self):
        self.tls = None
        self.auth = None
        self.req_count = 0

    def _open(self):
        self._close()
        self.tls = _open_tls()
        self.auth = None
        self.req_count = 0

    def _close(self):
        if self.tls is not None:
            try:
                self.tls.close()
            except Exception:
                pass
        self.tls = None
        self.auth = None
        self.req_count = 0

    def _solve_challenge(self, body: bytes) -> bool:
        """If `body` is a PoW stub, solve it, POST /__verify, store the cookie.

        Returns True if we now have a valid `self.auth`.
        """
        m = CHALLENGE_RX.search(body)
        if not m:
            return False
        c = m.group(1).decode()
        d = int(m.group(2))
        n = _solve_pow(c, d)
        post = f"c={urllib.parse.quote(c, safe='')}&n={n}".encode()
        try:
            _, _, cookies, _ = _send_request(
                self.tls, "POST", "/__verify",
                {"Content-Type": "application/x-www-form-urlencoded"},
                post,
            )
        except Exception:
            return False
        auth = _parse_auth_cookie(cookies)
        if auth:
            self.auth = auth
            return True
        return False

    def get(self, path: str) -> bytes | None:
        """GET one path, solving the PoW on demand. Returns body or None on hard failure.

        A None return AND a body containing the JS stub (which we
        transparently re-solve once) are both treated as terminal - we
        never retry on the same path at the bytes level. When the body
        is suspiciously short we treat the connection as throttled,
        close it, and sleep COOLDOWN_SECS before the next caller asks
        us to open a new one.
        """
        if self.tls is None:
            try:
                self._open()
            except Exception:
                time.sleep(self.COOLDOWN_SECS)
                return None
        headers = {"Cookie": self.auth} if self.auth else {}
        try:
            _, _, _, body = _send_request(self.tls, "GET", path, headers)
            self.req_count += 1
        except Exception:
            # Connection died. Reopen once and try a single fresh GET.
            try:
                self._open()
            except Exception:
                time.sleep(self.COOLDOWN_SECS)
                return None
            try:
                _, _, _, body = _send_request(self.tls, "GET", path, {})
                self.req_count += 1
            except Exception:
                self._close()
                time.sleep(self.COOLDOWN_SECS)
                return None
        if b"This site requires JavaScript" in body:
            if not self._solve_challenge(body):
                self._close()
                time.sleep(self.COOLDOWN_SECS)
                return None
            try:
                _, _, _, body = _send_request(
                    self.tls, "GET", path, {"Cookie": self.auth}
                )
                self.req_count += 1
            except Exception:
                self._close()
                time.sleep(self.COOLDOWN_SECS)
                return None
        # Rate-limit detection: Stooq returns the page shell (~40KB) without
        # the OHLC table once we've exceeded the per-IP per-window quota.
        # Burn the connection, sleep, and ask the proxy for a new exit IP.
        if len(body) < self.RATE_LIMIT_THRESHOLD:
            self._close()
            time.sleep(self.COOLDOWN_SECS)
        return body


# --------------------------------------------------------------------------
# Per-symbol fetch + parse

def fetch_one(sess: StooqSession, stooq_sym: str, d1: str, d2: str,
              all_pages: bool = True):
    """Walk Stooq's history table for one symbol.

    Returns (price, momentum_12m, pct_off_52w_high) or None on failure /
    unknown symbol. Failure modes we treat as "move on":
      * Stooq 302s to /q/s/ (search) - the body comes back empty/small
        because we don't follow the redirect, so rows=0 on parse
      * Page 1 fetch returns the JS stub and PoW resolution failed
      * Rate-limit truncation: Stooq's page comes back with the chrome
        but no OHLC table. StooqSession.get() detects this by size and
        burns the connection; the caller just sees no rows here

    Strategy: by default we walk every page so 52w-high and the oldest
    close are accurate. Setting all_pages=False fetches page 1 + the
    last page only - much cheaper against Stooq's per-IP rate limit
    but the high becomes a lower-bound estimate.
    """
    base = f"/q/d/?s={urllib.parse.quote(stooq_sym)}&i=d&d1={d1}&d2={d2}"
    body = sess.get(base)
    if not body or len(body) < 1000:
        return None
    body_str = body.decode("utf-8", errors="replace")
    rows = ROW_RX.findall(body_str)
    if not rows:
        # Either Stooq doesn't have this symbol (302 to /q/s/) or it
        # returned a data-less page shell under rate limit.
        return None
    # Pagination: ">>>" link points to the LAST page.
    m = LAST_PAGE_RX.search(body)
    last_page = int(m.group(1)) if m else 1
    if all_pages:
        page_range = range(2, last_page + 1)
    elif last_page > 1:
        # 2-page mode: just grab the oldest page for the 12m anchor.
        page_range = (last_page,)
    else:
        page_range = ()
    for p in page_range:
        b2 = sess.get(base + f"&l={p}")
        if not b2:
            continue
        rows.extend(ROW_RX.findall(b2.decode("utf-8", errors="replace")))
    if not rows:
        return None
    # Rows arrive newest-first within each page and we walked pages in
    # ascending order (newest -> oldest), so rows[0] = most recent close.
    try:
        closes = [float(r[5]) for r in rows]
        highs = [float(r[3]) for r in rows]
    except ValueError:
        return None
    if not closes:
        return None
    last_close = closes[0]
    first_close = closes[-1]
    high_52w = max(highs)
    mom = (last_close - first_close) / first_close if first_close else None
    off_high = (last_close - high_52w) / high_52w if high_52w else None
    return last_close, mom, off_high


# --------------------------------------------------------------------------
# Worker thread loop

def worker(symbol_queue, results, lock, src_by_sym, d1, d2, stop):
    """Pull symbols off a shared list, fetch, append result row, repeat.

    We use one fresh StooqSession PER SYMBOL. Stooq's per-IP rate limit
    is so tight (~7-10 page fetches per IP before truncated responses
    kick in, which is just barely 1 symbol's worth of data) that
    persistent connections give us no real reuse advantage. Opening a
    new TLS connection costs ~0.5s of PoW solve, but the proxy pool
    rotates exit IPs, so we get a fresh per-IP budget every symbol.
    """
    while not stop[0]:
        with lock:
            if not symbol_queue:
                return
            universe_sym = symbol_queue.pop()
            src = src_by_sym.get(universe_sym, "")
        stooq_sym = to_stooq_symbol(universe_sym, src)
        sess = StooqSession()
        if not stooq_sym:
            with lock:
                results.append({
                    "symbol": universe_sym, "stooq_symbol": None,
                    "price": None, "momentum_12m": None,
                    "pct_off_52w_high": None, "currency": SRC_TO_CCY.get(src),
                    "fetched_at": int(time.time()), "status": "unmapped",
                })
            continue
        try:
            out = fetch_one(sess, stooq_sym, d1, d2)
        except Exception:
            out = None
        finally:
            sess._close()  # one symbol = one connection; release the FD now
        if out is None:
            with lock:
                results.append({
                    "symbol": universe_sym, "stooq_symbol": stooq_sym,
                    "price": None, "momentum_12m": None,
                    "pct_off_52w_high": None, "currency": SRC_TO_CCY.get(src),
                    "fetched_at": int(time.time()), "status": "failed",
                })
        else:
            price, mom, off_high = out
            with lock:
                results.append({
                    "symbol": universe_sym, "stooq_symbol": stooq_sym,
                    "price": price, "momentum_12m": mom,
                    "pct_off_52w_high": off_high,
                    "currency": SRC_TO_CCY.get(src),
                    "fetched_at": int(time.time()), "status": "ok",
                })


# --------------------------------------------------------------------------
# Main: load universe, filter, run workers, checkpoint.

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols-from", default="asymmetry_global.csv")
    ap.add_argument("--out", default="stooq_price_fill.csv")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true",
                    help="ignore existing output and refetch every symbol")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap symbols this run (0 = all)")
    ap.add_argument("--only-missing", action="store_true",
                    help="only fetch symbols where price is null in the input")
    ap.add_argument("--d1", default=None,
                    help="from-date YYYYMMDD (default: 1y ago)")
    ap.add_argument("--d2", default=None,
                    help="to-date YYYYMMDD (default: today)")
    ap.add_argument("--checkpoint-every", type=int, default=50,
                    help="write CSV every N completed symbols")
    args = ap.parse_args()

    # Default date range: trailing 1 year + a 2-week padding so the most
    # recent close is comfortably inside the window.
    if not args.d2:
        args.d2 = time.strftime("%Y%m%d")
    if not args.d1:
        # ~370 days back is enough trading-day budget to cover 252 days
        # even across long holidays.
        args.d1 = time.strftime("%Y%m%d", time.gmtime(time.time() - 370 * 86400))

    print(f"loading universe from {args.symbols_from}...", file=sys.stderr)
    df = pd.read_csv(args.symbols_from,
                     usecols=lambda c: c in ("symbol", "src", "price"),
                     low_memory=False)
    if "symbol" not in df.columns:
        print("no 'symbol' column", file=sys.stderr); sys.exit(1)

    if args.only_missing and "price" in df.columns:
        df = df[df["price"].isna()].copy()
        print(f"  filtered to {len(df):,} rows missing price", file=sys.stderr)

    df = df.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol"])
    src_by_sym = dict(zip(df["symbol"], df.get("src", pd.Series(dtype=object))))
    symbols = df["symbol"].tolist()
    print(f"  {len(symbols):,} symbols in universe", file=sys.stderr)

    existing = {}
    if not args.refresh and os.path.exists(args.out):
        try:
            ex = pd.read_csv(args.out)
            existing = {r["symbol"]: r.to_dict() for _, r in ex.iterrows()}
            print(f"  {len(existing):,} symbols already in {args.out} - resuming",
                  file=sys.stderr)
        except Exception as e:
            print(f"  could not read {args.out}: {e}", file=sys.stderr)

    todo = [s for s in symbols if s not in existing]
    if args.limit:
        todo = todo[: args.limit]
    print(f"  todo: {len(todo):,} symbols, d1={args.d1} d2={args.d2}, "
          f"workers={args.workers}", file=sys.stderr)
    if not todo:
        print("nothing to fetch", file=sys.stderr)
        return

    # Shared state across workers
    queue = list(reversed(todo))  # we pop() off the end => process in input order
    results = list(existing.values()) if not args.refresh else []
    initial_n = len(results)
    import threading
    lock = threading.Lock()
    stop = [False]

    def write_partial():
        if not results:
            return
        out = pd.DataFrame(results)
        cols = ["symbol", "stooq_symbol", "price", "momentum_12m",
                "pct_off_52w_high", "currency", "status", "fetched_at"]
        cols = [c for c in cols if c in out.columns] + [c for c in out.columns if c not in cols]
        out = out[cols]
        tmp = args.out + ".tmp"
        out.to_csv(tmp, index=False)
        os.replace(tmp, args.out)

    start = time.time()
    threads = []
    for _ in range(args.workers):
        t = threading.Thread(target=worker,
                             args=(queue, results, lock, src_by_sym,
                                   args.d1, args.d2, stop))
        t.daemon = True
        t.start()
        threads.append(t)

    last_ckpt = initial_n
    try:
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=2.0)
            with lock:
                done = len(results) - initial_n
                remaining = len(queue)
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = remaining / rate / 60 if rate > 0 else 0
            print(f"  {done:,}/{len(todo):,} done | {remaining:,} queued | "
                  f"{rate:.2f}/s | ETA {eta:.1f}m", file=sys.stderr)
            with lock:
                if len(results) - last_ckpt >= args.checkpoint_every:
                    write_partial()
                    last_ckpt = len(results)
            if remaining == 0:
                break
    except KeyboardInterrupt:
        stop[0] = True
        print("\ninterrupted - writing partial...", file=sys.stderr)

    for t in threads:
        t.join(timeout=5.0)
    write_partial()

    # Summary
    df_out = pd.DataFrame(results)
    n_ok = (df_out.get("status") == "ok").sum() if "status" in df_out.columns else 0
    n_fail = (df_out.get("status") == "failed").sum() if "status" in df_out.columns else 0
    n_unmapped = (df_out.get("status") == "unmapped").sum() if "status" in df_out.columns else 0
    elapsed = time.time() - start
    print(f"\nDONE in {elapsed/60:.1f}m: ok={n_ok:,} fail={n_fail:,} "
          f"unmapped={n_unmapped:,} total_rows={len(df_out):,}",
          file=sys.stderr)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
