"""Investegate RNS scraper.

Pulls structured regulatory-news announcements from
investegate.co.uk/company/{EPIC}. Categories are encoded in the URL
slug, which is far cleaner than Google News headline parsing:

  tr-1-notification-of-major-holdings    -> tr1
      (institutional stake-building disclosure — TR-1 filing under
       DTR 5. Directly maps to "accumulation before news is announced")
  holding-s-in-company                   -> holdings (same, older form)
  director-pdmr-shareholding             -> pdmr (insider deal)
  transaction-in-own-shares              -> buyback
  tender-offer / result-of-tender        -> tender
  wind-down / managed-realisation        -> winddown
  strategic-review / strategy            -> review
  result-of-agm / continuation-vote      -> agm
  disposal / completion-of-disposal      -> disposal
  trading-update / interim-results       -> trading

Why this is high-grade signal vs Google News:
  · Source is the regulatory wire, not third-party aggregators
  · No name-collision contamination (PSH vs PSUS is impossible —
    each EPIC has its own page)
  · Categories are pre-classified by the issuer's RNS submission
  · TR-1 / Holdings are direct counterparty disclosures of who is
    accumulating — the exact thing the screener tries to *infer*
    from volume bars

Cache: data/investegate/{epic}.json with 24h TTL.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


BASE = "https://www.investegate.co.uk"
CACHE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "investegate"
PDMR_DETAIL_DIR = CACHE_DIR / "pdmr"
CACHE_TTL_SECONDS = 24 * 3600

USER_AGENT = ("Mozilla/5.0 (compatible; CyclepapaRns/1.0; "
              "investegate-RNS-aggregator)")


# Category map: slug regex -> internal label
CATEGORY_RULES = [
    (re.compile(r"tr-?1-notification-of-major-holdings"), "tr1"),
    (re.compile(r"holding-?s?-in-company"),               "tr1"),
    (re.compile(r"notification-of-major-(holdings?|interests?)"), "tr1"),
    (re.compile(r"director-?pdmr-?shareholding|pdmr-shareholding|director-shareholding"), "pdmr"),
    (re.compile(r"director-?dealing|transactions?-by-pdmr"), "pdmr"),
    (re.compile(r"transaction-in-own-shares|own-share-purchase"
                r"|share-buy-?back|repurchase-of-shares?|own-shares"), "buyback"),
    (re.compile(r"tender-offer|result-of-tender|tender-results?"
                r"|tender-circular"), "tender"),
    (re.compile(r"wind-?down|managed-wind-?down|managed-realis"
                r"|liquidation|scheme-of-arrangement"), "winddown"),
    (re.compile(r"strategic-review|strategy-(update|refresh|reset)"
                r"|portfolio-proposals|reset-(and|&)-roadmap"), "review"),
    (re.compile(r"continuation-vote|result-of-agm|agm-results?"
                r"|annual-general-meeting"), "agm"),
    (re.compile(r"completion-of-disposal|disposal[-_]"), "disposal"),
    (re.compile(r"capital-distribution|return-of-capital|cash-distribution"
                r"|capital-reduction"), "capdistribution"),
    (re.compile(r"appointment.*adviser|appointment.*broker|broker-change"), "advisor"),
]

# Weights into the composite signal score — RNS is high-grade so we
# give it parity with the Google News weights but on a separate
# additive track that's added to the news composite.
WEIGHTS = {
    "tr1":             0.30,
    "pdmr":            0.25,
    "winddown":        0.20,
    "tender":          0.15,
    "review":          0.15,
    "advisor":         0.15,
    "agm":             0.10,
    "buyback":         0.10,
    "capdistribution": 0.10,
    "disposal":        0.05,
}


@dataclass
class Announcement:
    date: str              # ISO date "YYYY-MM-DD"
    title: str
    category: str          # internal label
    raw_slug: str          # original URL slug
    url: str


# ---------------------------------------------------------------------------

def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(epic: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", epic.upper())
    return CACHE_DIR / f"{safe}.json"


def _cache_age_hours(p: Path) -> float:
    if not p.exists():
        return float("inf")
    return (time.time() - p.stat().st_mtime) / 3600.0


def _categorise(slug: str) -> str | None:
    for rx, label in CATEGORY_RULES:
        if rx.search(slug):
            return label
    return None


# Date parsing — Investegate's row format is "28 May 2026"
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{4})",
    re.IGNORECASE,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


def _parse_date(s: str) -> str | None:
    m = _DATE_RE.search(s)
    if not m:
        return None
    d, mon, y = m.groups()
    return f"{int(y):04d}-{_MONTHS[mon[:3].title()]:02d}-{int(d):02d}"


# Row extraction. Each <tr> contains: date td, time td, [other tds],
# source td, link td. We pair each announcement-link with the date
# from the same <tr>.
_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_LINK_RE = re.compile(
    r'<a class="announcement-link"\s+href="([^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)
_TD_TEXT_RE = re.compile(r"<td[^>]*>\s*([^<]+?)\s*</td>", re.IGNORECASE)


def _parse_page(html: str, epic: str | None = None,
                base_url: str = BASE) -> list[Announcement]:
    """Parse the company page. When `epic` is supplied we additionally
    verify that the announcement URLs actually carry that EPIC — when
    Investegate doesn't recognise an EPIC it serves a *generic* news
    feed (no 404) and the scraper previously cached it as if it were
    the EPIC's real data. We detect the fallback by checking the
    fraction of links whose slug ends `--{epic}/...`; below 50% we
    treat the page as not-found."""
    out: list[Announcement] = []
    seen_urls: set[str] = set()
    epic_lc = (epic or "").lower()
    matching_epic = 0
    total_links = 0
    for tr_match in _TR_RE.finditer(html):
        block = tr_match.group(1)
        link_m = _LINK_RE.search(block)
        if not link_m:
            continue
        url, title = link_m.group(1), link_m.group(2).strip()
        if url in seen_urls:
            continue
        total_links += 1
        # Slug check — investegate URLs are .../{slug-name}--{epic}/...
        if epic_lc and f"--{epic_lc}/" in url.lower():
            matching_epic += 1
        tds = _TD_TEXT_RE.findall(block)
        date_str = None
        for td in tds:
            d = _parse_date(td)
            if d:
                date_str = d
                break
        slug_parts = url.split("/")
        category_slug = slug_parts[-2] if len(slug_parts) >= 2 else ""
        label = _categorise(category_slug)
        if label is None:
            label = _categorise(title.lower().replace(" ", "-"))
        if label is None:
            label = "other"
        seen_urls.add(url)
        out.append(Announcement(
            date=date_str or "", title=title, category=label,
            raw_slug=category_slug, url=url,
        ))
    # Fallback-page detection — when we asked for SEIT but the page
    # returned 50 entries none of which contain "--seit/" in the URL,
    # this is the generic news feed (Investegate's silent 404).
    if epic_lc and total_links >= 5 and matching_epic / total_links < 0.50:
        return []
    return out


# ---------------------------------------------------------------------------

def fetch_company(epic: str, *, use_cache: bool = True,
                  ttl_hours: float = 24.0) -> list[Announcement]:
    """Fetch RNS announcements for EPIC. Returns chronological list
    (most recent first), already in cache for next call."""
    _ensure_cache_dir()
    epic = (epic or "").strip().upper().replace(".L", "")
    if not epic:
        return []
    cp = _cache_path(epic)
    if use_cache and _cache_age_hours(cp) < ttl_hours:
        try:
            with open(cp) as f:
                data = json.load(f)
            return [Announcement(**a) for a in data]
        except Exception:
            pass
    url = f"{BASE}/company/{epic}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []
    items = _parse_page(html, epic=epic)
    if use_cache:
        try:
            with open(cp, "w") as f:
                json.dump([asdict(a) for a in items], f)
        except Exception:
            pass
    return items


def signal_score_from_rns(
    items: list[Announcement],
    *,
    lookback_days: int = 120,
    half_life_days: int = 30,
) -> tuple[float, dict[str, float], dict[str, int]]:
    """Compute exponentially-decayed RNS-category counts + composite
    signal. Returns (composite_0..1, decayed_counts, raw_counts)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    decayed: dict[str, float] = {c: 0.0 for c in WEIGHTS}
    raw: dict[str, int] = {c: 0 for c in WEIGHTS}
    for a in items:
        if a.category not in WEIGHTS:
            continue
        if not a.date:
            continue
        try:
            dt = datetime.fromisoformat(a.date).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        age_days = (now - dt).total_seconds() / 86400.0
        w = 0.5 ** (age_days / max(1, half_life_days))
        decayed[a.category] += w
        raw[a.category] += 1
    # Saturating non-linearity per category, then weighted sum
    def _sat(x: float) -> float:
        return 1.0 - 1.0 / (1.0 + x / 3.0)
    composite = sum(WEIGHTS[c] * _sat(decayed[c]) for c in WEIGHTS)
    return min(1.0, composite), decayed, raw


# ---------------------------------------------------------------------------
# PDMR detail fetch — RNS titles never carry direction ("Director/PDMR
# Shareholding" is the only title format), so to distinguish buys from
# sells we have to fetch the announcement body. The body has a
# standardised "Nature of the transaction" line we can parse, plus
# Price(s) × Volume(s) for £-magnitude. Announcements are immutable so
# we cache per-URL forever.

_NATURE_RE = re.compile(
    r"Nature of the transaction[^A-Za-z]{0,8}([A-Za-z][A-Za-z /\-]{2,60})",
    re.IGNORECASE,
)
# Match either "£1.23 4,567" pairs OR plain "Price 1.23  Volume 4,567"
_PRICE_VOL_RE = re.compile(
    r"(?:£|GBP|GBp|p)?\s?([\d,]+\.\d{1,4})\s+([\d,]+)",
    re.IGNORECASE,
)
_BUY_WORDS = re.compile(
    r"\b(?:purchas\w*|acqui\w*|buy|bought|subscri\w*|allotment)\b",
    re.IGNORECASE,
)
_SELL_WORDS = re.compile(
    r"\b(?:sale|sell|sold|dispos\w*|transfer out|gift)\b",
    re.IGNORECASE,
)
# Scrip / DRIP / vesting / award — NOT a conviction buy. Detected
# separately so they neither inflate the buy count nor get classified
# as sells.
_NON_CONVICTION_WORDS = re.compile(
    r"\b(?:scrip|dividend\s+(?:re)?investment|drip|in\s+lieu|"
    r"vesting|vested|award|grant|option\s+exercise|exercis\w*\s+of\s+options?|"
    r"rsu|psp|deferred\s+bonus|ltip)\b",
    re.IGNORECASE,
)


def _pdmr_cache_path(url: str) -> Path:
    PDMR_DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    rns_id = re.sub(r"[^A-Za-z0-9]+", "_", url.rstrip("/").split("/")[-1])
    return PDMR_DETAIL_DIR / f"{rns_id}.json"


def fetch_pdmr_detail(url: str, *, use_cache: bool = True) -> dict:
    """Fetch one PDMR announcement body and parse direction + £.

    Returns dict with keys: {direction: 'buy'|'sell'|'unknown',
    gbp_amount: float, raw_nature: str}. Cached per-URL forever — RNS
    announcements don't change."""
    cp = _pdmr_cache_path(url)
    if use_cache and cp.exists():
        try:
            with open(cp) as f:
                return json.load(f)
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {"direction": "unknown", "gbp_amount": 0.0, "raw_nature": ""}
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&#160;|&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    nature_m = _NATURE_RE.search(text)
    raw_nature = nature_m.group(1).strip() if nature_m else ""
    direction = _classify_pdmr_direction(raw_nature)
    gbp = _extract_pdmr_gbp(text, raw_nature)
    rec = {"direction": direction, "gbp_amount": round(gbp, 2),
           "raw_nature": raw_nature[:80]}
    if use_cache:
        try:
            with open(cp, "w") as f:
                json.dump(rec, f)
        except Exception:
            pass
    return rec


def _classify_pdmr_direction(nature: str) -> str:
    """Returns 'buy' / 'sell' / 'scrip' / 'unknown'.

    'scrip' covers dividend reinvestments, LTIP vesting, RSU/option
    exercise — these inflate director holdings without conviction
    behind the move, so they should not count toward the insider-buy
    signal. We keep them as a separate class rather than 'unknown' so
    we can audit the rejection rate."""
    if not nature:
        return "unknown"
    if _NON_CONVICTION_WORDS.search(nature):
        return "scrip"
    if _BUY_WORDS.search(nature):
        return "buy"
    if _SELL_WORDS.search(nature):
        return "sell"
    return "unknown"


_DECIMAL_RE = re.compile(r"(?<![\d.,])([\d,]*\d\.\d{1,4})(?![\d.,])")
_INTEGER_RE = re.compile(r"(?<![\d.,])([\d,]+)(?![\d.,])")


def _extract_pdmr_gbp(text: str, nature: str) -> float:
    """Find the first plausible price × volume pair after the Nature
    line. Returns £ amount, or 0.0 if not parseable. Detects pence
    quotation by the presence of GBp / "pence" near the price."""
    i = text.find("Price(s)")
    chunk = text[i:i+400] if i >= 0 else text[:1500]
    price_m = _DECIMAL_RE.search(chunk)
    if not price_m:
        return 0.0
    try:
        price = float(price_m.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    # Look for the volume *after* the price; nature lines can sit before
    after = chunk[price_m.end():]
    vol_m = _INTEGER_RE.search(after)
    if not vol_m:
        return 0.0
    try:
        volume = float(vol_m.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    if volume < 1:
        return 0.0
    gbp = price * volume
    # Heuristic: if GBp / pence marker is in the vicinity, the price
    # is in pence — divide by 100.
    nearby = chunk[max(0, price_m.start()-40):price_m.end()+40]
    if re.search(r"GBp|pence", nearby, re.IGNORECASE):
        gbp = gbp / 100.0
    return gbp


def enrich_pdmr_directions(
    items: list[Announcement],
    *,
    lookback_days: int = 120,
    max_fetches: int = 25,
) -> dict[str, int | float]:
    """For each PDMR within the lookback window, fetch the body and
    classify direction. Returns aggregate counts and £-totals.

    Scrip / vesting / DRIP / LTIP nature lines are bucketed separately
    in pdmr_scrip so they don't inflate the conviction-buy signal.
    max_fetches caps the per-ticker HTTP cost — older PDMRs already
    matter less and the cache will fill in over multiple runs."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    out = {"pdmr_buys": 0, "pdmr_sells": 0, "pdmr_scrip": 0,
           "pdmr_unknown": 0,
           "pdmr_buy_gbp": 0.0, "pdmr_sell_gbp": 0.0}
    fetched = 0
    for a in items:
        if a.category != "pdmr" or not a.date:
            continue
        try:
            dt = datetime.fromisoformat(a.date).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        if fetched >= max_fetches:
            break
        cp = _pdmr_cache_path(a.url)
        had_cache = cp.exists()
        det = fetch_pdmr_detail(a.url)
        if not had_cache:
            fetched += 1
        d = det.get("direction", "unknown")
        gbp = float(det.get("gbp_amount", 0.0))
        if d == "buy":
            out["pdmr_buys"] += 1
            out["pdmr_buy_gbp"] += gbp
        elif d == "sell":
            out["pdmr_sells"] += 1
            out["pdmr_sell_gbp"] += gbp
        elif d == "scrip":
            out["pdmr_scrip"] += 1
        else:
            out["pdmr_unknown"] += 1
    return out


# ---------------------------------------------------------------------------
# TR-1 detail fetch — like PDMRs, TR-1 announcement titles are
# uniformly "Holding(s) in Company" so direction (buy/sell) and
# materiality (1% step vs 10% accumulator) live only in the body. The
# body has a structured table:
#
#   Position of notification:           Above the notification threshold
#   Resulting situation: % of voting rights:  6.12%
#   Previous notification: % of voting rights: 4.95%
#   Name of the holder:                       <institution>
#
# We parse holder + new% + prev%, derive direction (new > prev = buy),
# magnitude (new - prev = pp delta), and flag known activists.

# Known activist holders — loaded lazily from data/activist_holders.csv
# so new activists can be added without editing code. Falls back to a
# tiny built-in seed if the CSV is unreadable. Each entry is matched
# as a substring against the holder string (case-insensitive).
_ACTIVIST_SEED = [
    "saba capital", "boaz weinstein", "asset value investors",
    "city of london investment", "colim", "elliott",
    "metage capital", "almitas capital", "1607 capital",
]
_ACTIVIST_CACHE: list[str] | None = None


def _activist_holders() -> list[str]:
    global _ACTIVIST_CACHE
    if _ACTIVIST_CACHE is not None:
        return _ACTIVIST_CACHE
    path = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "activist_holders.csv"
    out: list[str] = []
    try:
        with open(path) as f:
            import csv as _csv
            for row in _csv.DictReader(f):
                v = (row.get("name_substring") or "").strip().lower()
                if v:
                    out.append(v)
    except (OSError, IOError):
        pass
    _ACTIVIST_CACHE = out or list(_ACTIVIST_SEED)
    return _ACTIVIST_CACHE


# Backwards compat — direct attribute access still works but is now
# computed on first use.
ACTIVIST_HOLDERS: list[str] = _activist_holders()

TR1_DETAIL_DIR = CACHE_DIR / "tr1"

# Two TR-1 body formats:
#   (a) DTR-5 long-form with explicit "%" labels — synthetic / older
#       wires. Pattern: "Resulting situation: % of voting rights: 6.12%"
#   (b) Modern Investegate template — bare decimals in column layout.
#       Pattern: "Resulting situation on the date on which threshold
#       was crossed or reached 1.337000 0.000000 1.337000 538371
#       Position of previous notification (if applicable) 14.488423 ..."
#
# We try (a) first; if no %-suffixed match, fall back to (b) parsing
# the first plausible decimal (< 100) after each marker.
_TR1_NEW_RE = re.compile(
    r"resulting\s+situation.{0,160}?(?<![\d.])(\d{1,3}(?:\.\d{1,6})?)\s*%(?!\s*of\s+voting)",
    re.IGNORECASE | re.DOTALL,
)
_TR1_PREV_RE = re.compile(
    r"previous\s+notification.{0,160}?(?<![\d.])(\d{1,3}(?:\.\d{1,6})?)\s*%(?!\s*of\s+voting)",
    re.IGNORECASE | re.DOTALL,
)
_TR1_NEW_BARE_RE = re.compile(
    r"resulting\s+situation\s+on\s+the\s+date.{0,180}?"
    r"(\d{1,3}(?:\.\d{1,6})?)\b",
    re.IGNORECASE | re.DOTALL,
)
_TR1_PREV_BARE_RE = re.compile(
    r"position\s+of\s+previous\s+notification.{0,180}?"
    r"(\d{1,3}(?:\.\d{1,6})?)\b",
    re.IGNORECASE | re.DOTALL,
)
# Holder lives under "person subject to the notification obligation Name X City of"
# OR the synthetic format "Name of the shareholder: X"
_TR1_HOLDER_RE = re.compile(
    r"person\s+subject\s+to\s+the\s+notification\s+obligation\s+Name\s+"
    r"([A-Z0-9][A-Za-z0-9 ,.&/\-']{3,100}?)\s+City\s+of\s+registered",
    re.IGNORECASE | re.DOTALL,
)
_TR1_HOLDER_FALLBACK_RE = re.compile(
    r"name\s+of\s+(?:the\s+)?(?:shareholder|holder)[^:]{0,40}?:?\s*"
    r"([A-Z0-9][A-Za-z0-9 ,.&/\-']{4,80})",
    re.IGNORECASE,
)


def _parse_tr1_pct(text: str, primary_re: re.Pattern,
                   fallback_re: re.Pattern) -> float | None:
    m = primary_re.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = fallback_re.search(text)
    if m:
        try:
            v = float(m.group(1))
            # Sanity: voting-rights % should be 0-100
            if 0 <= v <= 100:
                return v
        except ValueError:
            pass
    return None


def _tr1_cache_path(url: str) -> Path:
    TR1_DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    rns_id = re.sub(r"[^A-Za-z0-9]+", "_", url.rstrip("/").split("/")[-1])
    return TR1_DETAIL_DIR / f"{rns_id}.json"


def fetch_tr1_detail(url: str, *, use_cache: bool = True) -> dict:
    """Fetch one TR-1 body and parse holder + position. Returns dict
    {holder, new_pct, prev_pct, delta_pp, direction, is_activist}.
    Cached per-URL forever."""
    cp = _tr1_cache_path(url)
    if use_cache and cp.exists():
        try:
            with open(cp) as f:
                return json.load(f)
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {"holder": "", "new_pct": None, "prev_pct": None,
                "delta_pp": 0.0, "direction": "unknown", "is_activist": False}
    import html as _html
    text = re.sub(r"<[^>]+>", " ", html)
    text = _html.unescape(text)
    text = re.sub(r"&#160;|&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    new_pct = _parse_tr1_pct(text, _TR1_NEW_RE, _TR1_NEW_BARE_RE)
    prev_pct = _parse_tr1_pct(text, _TR1_PREV_RE, _TR1_PREV_BARE_RE)
    holder_m = _TR1_HOLDER_RE.search(text) or _TR1_HOLDER_FALLBACK_RE.search(text)
    holder = (holder_m.group(1).strip() if holder_m else "")[:80]
    if new_pct is not None and prev_pct is not None:
        delta = new_pct - prev_pct
        direction = "buy" if delta > 0 else ("sell" if delta < 0 else "flat")
    elif new_pct is not None and prev_pct is None:
        # First notification crossing threshold — treat as buy
        delta = new_pct
        direction = "buy"
    else:
        delta = 0.0
        direction = "unknown"
    holder_lc = holder.lower()
    is_activist = any(a in holder_lc for a in _activist_holders())
    rec = {"holder": holder, "new_pct": new_pct, "prev_pct": prev_pct,
           "delta_pp": round(delta, 4), "direction": direction,
           "is_activist": is_activist}
    if use_cache:
        try:
            with open(cp, "w") as f:
                json.dump(rec, f)
        except Exception:
            pass
    return rec


def enrich_tr1_directions(
    items: list[Announcement],
    *,
    lookback_days: int = 120,
    max_fetches: int = 25,
    material_pp: float = 1.0,
) -> dict:
    """For each in-window TR-1, fetch body and classify. Returns
    {tr1_buys, tr1_sells, tr1_material_adds, tr1_activist_buys,
    tr1_buy_total_pp, activist_holders}."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    out = {"tr1_buys": 0, "tr1_sells": 0, "tr1_unknown": 0,
           "tr1_material_adds": 0, "tr1_activist_buys": 0,
           "tr1_buy_total_pp": 0.0,
           "activist_holders": []}
    fetched = 0
    for a in items:
        if a.category != "tr1" or not a.date:
            continue
        try:
            dt = datetime.fromisoformat(a.date).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        if fetched >= max_fetches:
            break
        cp = _tr1_cache_path(a.url)
        had_cache = cp.exists()
        det = fetch_tr1_detail(a.url)
        if not had_cache:
            fetched += 1
        d = det.get("direction", "unknown")
        delta = float(det.get("delta_pp", 0.0))
        if d == "buy":
            out["tr1_buys"] += 1
            out["tr1_buy_total_pp"] += delta
            if abs(delta) >= material_pp:
                out["tr1_material_adds"] += 1
            if det.get("is_activist"):
                out["tr1_activist_buys"] += 1
                holder = det.get("holder", "")
                if holder and holder not in out["activist_holders"]:
                    out["activist_holders"].append(holder)
        elif d == "sell":
            out["tr1_sells"] += 1
        else:
            out["tr1_unknown"] += 1
    return out


# ---------------------------------------------------------------------------
# Resolution score — composite "is a corporate-action resolution
# imminent" indicator. Uses a *short* (15-day) half-life because the
# resolution signal is fresh-only: an advisor appointment from 6 months
# ago is just background, but one from 3 weeks ago next to a strategic
# review and accelerating PDMR buys is the real tell.

RESOLUTION_HALF_LIFE_DAYS = 15
RESOLUTION_LOOKBACK_DAYS = 90

RESOLUTION_WEIGHTS = {
    "advisor":         0.25,   # broker / financial adviser appointment
    "review":          0.20,   # strategic review formally opened
    "agm":             0.15,   # continuation vote / AGM result imminent
    "capdistribution": 0.20,   # return of capital live
    "tender":          0.20,   # tender announced
    "winddown":        0.25,   # formal wind-down announcement
    "buyback":         0.15,   # sustained buyback = DCM intensifying
    # TR-1 raw count is no longer weighted — the direction-enriched
    # buckets below carry the load.
    "pdmr_buys":       0.20,   # insider conviction (direction-resolved)
    "tr1_buys":        0.15,   # net-positive TR-1s (NEW institutional buys)
    "tr1_material_adds": 0.15, # ≥1pp stake adds (real conviction, not 1%-tick)
    "tr1_activist_buys": 0.20, # Saba / AVI / etc. fingerprint
}


def resolution_score_from_rns(
    items: list[Announcement],
    *,
    lookback_days: int = RESOLUTION_LOOKBACK_DAYS,
    half_life_days: int = RESOLUTION_HALF_LIFE_DAYS,
    pdmr_buys_count: int = 0,
    tr1_buys: int = 0,
    tr1_material_adds: int = 0,
    tr1_activist_buys: int = 0,
) -> tuple[float, dict[str, float]]:
    """Composite 0..1 score for "resolution imminent". Returns (score,
    per-category decayed weights).

    pdmr_buys_count / tr1_* are passed in from the body-enriched steps
    (direction + materiality can't be inferred from slug + title).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    decayed: dict[str, float] = {c: 0.0 for c in RESOLUTION_WEIGHTS}
    # Date-anchored categories come from the announcement list with
    # a 15d half-life. Direction-enriched categories are fed as
    # already-windowed counts.
    date_anchored = {"advisor", "review", "agm", "capdistribution",
                     "tender", "winddown", "buyback"}
    for a in items:
        cat = a.category
        if cat not in date_anchored:
            continue
        if not a.date:
            continue
        try:
            dt = datetime.fromisoformat(a.date).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            continue
        age_days = (now - dt).total_seconds() / 86400.0
        w = 0.5 ** (age_days / max(1, half_life_days))
        decayed[cat] += w
    # Body-enriched counts (already filtered to lookback window upstream)
    decayed["pdmr_buys"] = float(pdmr_buys_count)
    decayed["tr1_buys"] = float(tr1_buys)
    decayed["tr1_material_adds"] = float(tr1_material_adds)
    decayed["tr1_activist_buys"] = float(tr1_activist_buys)

    def _sat(x: float) -> float:
        # Tighter saturation than the strength score — 1.5 hits = strong
        return 1.0 - 1.0 / (1.0 + x / 1.5)

    composite = sum(RESOLUTION_WEIGHTS[c] * _sat(decayed[c])
                    for c in RESOLUTION_WEIGHTS)
    return min(1.0, composite), decayed


# ---------------------------------------------------------------------------

def epic_from_ticker(ticker: str) -> str | None:
    """Investegate uses LSE EPIC codes (no suffix). Only .L tickers
    are supported."""
    if not ticker.endswith(".L"):
        return None
    return ticker[:-2].upper()


if __name__ == "__main__":
    for epic in ["SEIT", "CHRY", "GCP", "SOHO", "RSE", "III", "PSH"]:
        items = fetch_company(epic, use_cache=False)
        composite, dec, raw = signal_score_from_rns(items)
        print(f"\n{epic}  composite={composite:.2f}  items={len(items)}")
        for c, n in sorted(raw.items(), key=lambda kv: -kv[1])[:7]:
            if n:
                print(f"  {c:<16} n={n}  decayed={dec[c]:.2f}")
        for a in items[:3]:
            print(f"  [{a.date}] {a.category:<12} {a.title[:70]}")
