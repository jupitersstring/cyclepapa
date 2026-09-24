"""Shared EDGAR filing-document fetcher (text), cached.

Several engines need the ACTUAL words of a filing -- who was appointed and on
what terms (8-K Item 5.02), what is being sold to whom for how much (8-K /
EX-99 press release), what the PSU plan is (DEF 14A CD&A). Until now some of
them read only a local cache and silently got nothing for new filings.

  docs(cik, accession, want=("primary", "ex99"))  -> [(name, kind, text)]
  text(cik, accession, ...)                       -> concatenated text
  find_filing(cik, form, near_date, days=5)       -> accession | None

Documents are resolved from the filing's index.json, fetched at the SEC's
fair-access rate (shared lock, ~8 req/s), converted to plain text (tables
kept as ' | ' separated rows so figures stay readable) and cached gzip-
compressed under fmp_cache/edgar/ (gitignored).
"""

from __future__ import annotations

import gzip
import html as _html
import json
import re
import threading
import time
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
CACHE = ROOT / "fmp_cache" / "edgar"
_lock = threading.Lock()
_last = [0.0]


def _get(url):
    """SEC fair access (<=10 req/s) is per client, not per process: the slot is
    taken under an OS file lock shared by every process on this machine."""
    import edgar
    import fcntl
    CACHE.mkdir(parents=True, exist_ok=True)
    with _lock, open(CACHE / ".rate", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            last = float(fh.read().strip() or 0)
        except ValueError:
            last = 0.0
        wait = 0.125 - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        fh.seek(0); fh.truncate(); fh.write(str(time.time())); fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)
    return edgar._get(url)


def html_to_text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", h)
    h = re.sub(r"(?i)</t[dh]>", " | ", h)                 # keep table cells apart
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>|</table>", "\n", h)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = t.replace("\xa0", " ")
    lines = []
    for ln in t.split("\n"):
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        ln = re.sub(r"(\|\s*){2,}", "| ", ln).strip(" |")
        if ln:
            lines.append(ln)
    return "\n".join(lines)


def _index(cik, acc):
    """(base_url, [(filename, doc_type, description)]) from the filing's
    -index.htm, which states each document's official type (8-K, EX-99.1,
    EX-2.1, DEF 14A ...)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    cf = CACHE / acc / "_index2.json"
    if cf.exists():
        return base, [tuple(x) for x in json.loads(cf.read_text())]
    rows = []
    try:
        h = _get(f"{base}/{acc}-index.htm").text
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", h):
            tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)
            a = re.search(r'href="[^"]*/([^/"]+)"', tr)
            if a and len(tds) >= 4:
                clean = lambda x: re.sub(r"<[^>]+>", "", x).strip()
                rows.append((a.group(1), clean(tds[3]), clean(tds[1])))
    except Exception:
        rows = []
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(rows))
    return base, rows


EX99 = re.compile(r"ex[-_]?99|exhibit[-_]?99|dex99|ex991|ex992", re.I)
EX10 = re.compile(r"ex[-_]?10|exhibit[-_]?10|dex10", re.I)


def docs(cik, acc, want=("primary", "ex99"), max_chars=400_000):
    """[(name, kind, text)] for the wanted documents of one filing."""
    if not cik or not acc:
        return []
    base, items = _index(cik, acc)
    items = [(n, t.upper(), d) for n, t, d in items
             if n.lower().endswith((".htm", ".html", ".txt")) and not n.lower().endswith("-index.htm")]
    picks = []
    if "primary" in want:
        prim = [n for n, t, _ in items if t in ("8-K", "8-K/A", "DEF 14A", "DEFA14A", "10-K", "10-Q",
                                                   "SC TO-I", "SC 13D", "6-K", "20-F", "DEFM14A", "PRE 14A")]
        if prim:
            picks.append((prim[0], "primary"))
    if "ex99" in want:
        picks += [(n, "ex99") for n, t, _ in items if t.startswith("EX-99")][:3]
    if "ex10" in want:
        picks += [(n, "ex10") for n, t, _ in items if t.startswith("EX-10")][:2]
    if "ex2" in want:
        picks += [(n, "ex2") for n, t, _ in items if t.startswith("EX-2")][:1]
    out = []
    for name, kind in picks:
        cf = CACHE / acc / (re.sub(r"[^\w.-]", "_", name) + ".txt.gz")
        t = None
        if cf.exists():
            try:
                t = gzip.open(cf, "rt", encoding="utf-8").read()
            except (EOFError, OSError):
                t = None                              # truncated cache entry: re-fetch
        if t is None:
            try:
                raw = _get(f"{base}/{name}").text
                t = html_to_text(raw) if "<" in raw[:2000] else raw
            except Exception:
                t = ""
            t = t[:max_chars]
            cf.parent.mkdir(parents=True, exist_ok=True)
            tmp = cf.with_suffix(f".tmp{threading.get_ident()}")
            with gzip.open(tmp, "wt", encoding="utf-8") as fh:     # atomic: write then rename
                fh.write(t)
            tmp.replace(cf)
        if t:
            out.append((name, kind, t))
    return out


def text(cik, acc, want=("primary", "ex99"), max_chars=400_000):
    return "\n\n".join(t for _, _, t in docs(cik, acc, want, max_chars))


def url(cik, acc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"


_SUBS: dict = {}


def filings(cik, forms=("8-K",)):
    """[(form, accession, filing_date, items)] from the submissions API (cached per process)."""
    if cik in _SUBS:
        sub = _SUBS[cik]
    else:
        cf = CACHE / "_subs" / f"{int(cik)}.json"
        if cf.exists() and time.time() - cf.stat().st_mtime < 3 * 86400:
            sub = json.loads(cf.read_text())
        else:
            try:
                sub = _get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").json()
            except Exception:
                sub = {}
            cf.parent.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(sub))
        _SUBS[cik] = sub
    r = (sub.get("filings") or {}).get("recent") or {}
    return [(f, a, d, i) for f, a, d, i in zip(r.get("form", []), r.get("accessionNumber", []),
                                               r.get("filingDate", []), r.get("items", []))
            if f in forms]


def find_filing(cik, near_date, forms=("8-K", "8-K/A"), days=4, items_rx=None):
    """Accessions of `forms` filed within +-days of near_date (closest first)."""
    from datetime import date
    d0 = date.fromisoformat(near_date[:10])
    hits = []
    for f, a, d, it in filings(cik, forms):
        try:
            gap = abs((date.fromisoformat(d) - d0).days)
        except ValueError:
            continue
        if gap <= days and (not items_rx or re.search(items_rx, it or "")):
            hits.append((gap, a, d))
    return [(a, d) for _, a, d in sorted(hits)]
