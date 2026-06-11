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


def _parse_page(html: str, base_url: str = BASE) -> list[Announcement]:
    out: list[Announcement] = []
    seen_urls: set[str] = set()
    for tr_match in _TR_RE.finditer(html):
        block = tr_match.group(1)
        link_m = _LINK_RE.search(block)
        if not link_m:
            continue
        url, title = link_m.group(1), link_m.group(2).strip()
        if url in seen_urls:
            continue
        # The date is in the first <td> of the same row.
        tds = _TD_TEXT_RE.findall(block)
        date_str = None
        for td in tds:
            d = _parse_date(td)
            if d:
                date_str = d
                break
        # Extract slug from URL — the path between EPIC and the
        # numeric ID is the category slug.
        # https://www.investegate.co.uk/announcement/rns/{slug-name}/{category-slug}/{id}
        slug_parts = url.split("/")
        category_slug = slug_parts[-2] if len(slug_parts) >= 2 else ""
        label = _categorise(category_slug)
        if label is None:
            # Title fallback — sometimes slug is generic but the title
            # is descriptive.
            label = _categorise(title.lower().replace(" ", "-"))
        if label is None:
            label = "other"
        seen_urls.add(url)
        out.append(Announcement(
            date=date_str or "",
            title=title,
            category=label,
            raw_slug=category_slug,
            url=url,
        ))
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
    items = _parse_page(html)
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
