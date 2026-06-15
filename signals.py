"""Qualitative-signal scraper — v2.

Hardening vs qualitative_signals.py:

  * Entity verification — headline must contain the ticker or a
    substantial substring of the fund name. Drops the OCI/Conduit and
    PSH/PSUS contamination found in the forensic audit.

  * Per-ticker exclusion list (params.SIGNAL_EXCLUSIONS) — explicit
    noise filters.

  * Direction parsing — POSITIVE/NEGATIVE_DIRECTOR_VERBS to distinguish
    "Director purchases £X" from "Director resigns". Termination
    headlines are dropped from director_dealings count entirely (was a
    false positive in SOHO.L).

  * £-amount extraction — TipRanks-style headlines often include the
    amount; parsed and used for magnitude-weighting.

  * Time decay — exponential half-life (default 30 days) so a 90-day-
    old story isn't counted equally with last week's.

  * Cross-category dedupe — one headline is assigned to the strongest
    category it matches; can't score 2x for the same news.

  * Fetch-failure handling — failed RSS fetches return None (not []) so
    coverage is observable and the multiplier is skipped on incomplete
    data, not silently applying the no-signal penalty.

  * Daily snapshot persistence — write each run's signal scores to
    signals_history.csv so rising signal density (the real forward
    indicator) can be tracked week-over-week.

  * Investegate RNS layer (NEW) — adds structured regulatory-news
    signal alongside Google News. RNS categories (TR-1 stake-building,
    PDMR insider deals, buyback execution, tender offers) are
    pre-classified by the regulatory wire and immune to the entity-
    contamination Google News suffers from. UK tickers get an extra
    `rns_score` component; final `signal_score` is a weighted blend
    of news_score (0.40) + rns_score (0.60) — RNS weighted higher
    because it's the higher-grade source.
"""

from __future__ import annotations

import csv
import math
import os
import pickle
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import params

try:
    import investegate_scraper as inv_mod
    _HAS_INV = True
except Exception:
    _HAS_INV = False


CACHE_PATH = "/tmp/signals_v2_cache.pkl"
# Cache version stamp. Bump whenever scraper / scoring logic changes
# in a way that would invalidate previously-cached TickerSignals.
# v2 = post fallback-page-detection fix in investegate_scraper.
CACHE_SCHEMA_VERSION = "2026-06-15-v2-fallback-fix"
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "signals_history.csv")
CACHE_TTL_SECONDS = 24 * 3600
USER_AGENT = "Mozilla/5.0 (compatible; CyclepapaSignals/2.0)"

# Category strength order (strongest first). When a headline matches
# multiple categories it's assigned to the strongest only.
CATEGORY_ORDER = [
    "wind_down",
    "advisor_hired",
    "strategic_review",
    "director_dealings",
    "buyback",
]

CATEGORY_PATTERNS = {
    "wind_down": re.compile(
        r"wind[- ]?down|managed realisation|tender offer|cash exit|"
        r"liquidation|reconstruction|continuation vote fail|"
        r"return of capital",
        re.IGNORECASE,
    ),
    "advisor_hired": re.compile(
        r"appoint(s|ed|ing) (a |an )?advis(o|e)r|"
        r"appointed Rothschild|hired Rothschild|"
        r"appointed Numis|hired Numis|appointed Peel Hunt|hired Peel Hunt|"
        r"appointed Investec|hired Investec|appointed Deutsche|hired Deutsche|"
        r"restructuring advis|financial advis(o|e)r appointed",
        re.IGNORECASE,
    ),
    "strategic_review": re.compile(
        r"strategic review|continuation vote|discount control|board review|"
        r"reset & roadmap|reset and roadmap|strategy refresh",
        re.IGNORECASE,
    ),
    "director_dealings": re.compile(
        r"PDMR shareholding|director.{0,40}(buy|bought|purchase|acquir|"
        r"increases? stake|raises? stake|ups? stake|boosts? holding)|"
        r"insider.{0,30}(buy|bought|purchase|acquir)",
        re.IGNORECASE,
    ),
    "buyback": re.compile(
        r"share buyback|share repurchase|transaction in own shares|"
        r"buy[- ]?back programme",
        re.IGNORECASE,
    ),
}

NEGATIVE_DIRECTOR_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in params.NEGATIVE_DIRECTOR_VERBS) + r")\b",
    re.IGNORECASE,
)

AMOUNT_RE = re.compile(
    r"£\s?([\d,]+(?:\.\d+)?)\s?(million|m\b|k\b|thousand)?", re.IGNORECASE,
)

WEIGHTS = {
    "director_dealings": 0.30,
    "advisor_hired":     0.25,
    "strategic_review":  0.20,
    "wind_down":         0.15,
    "buyback":           0.10,
}

QUERY_TEMPLATES = {
    "director_dealings": [
        '"{name}" director purchase',
        '"{name}" director buys',
        '"{name}" PDMR shareholding',
    ],
    "advisor_hired": [
        '"{name}" appoints adviser',
        '"{name}" restructuring adviser',
        '"{name}" financial adviser',
    ],
    "buyback": [
        '"{name}" buyback',
        '"{name}" transaction in own shares',
    ],
    "strategic_review": [
        '"{name}" strategic review',
        '"{name}" continuation vote',
        '"{name}" discount control',
    ],
    "wind_down": [
        '"{name}" wind-down',
        '"{name}" managed realisation',
        '"{name}" tender offer',
        '"{name}" cash exit',
    ],
}


@dataclass
class TickerSignals:
    ticker: str
    name: str
    # Google News component
    counts: dict[str, float] = field(default_factory=dict)         # decayed
    raw_counts: dict[str, int] = field(default_factory=dict)       # undecayed
    director_total_gbp: float = 0.0
    news_score: float = 0.0
    coverage_ok: bool = True   # False if any RSS fetch failed
    queries_run: int = 0
    queries_failed: int = 0
    sample_titles: dict[str, list[str]] = field(default_factory=dict)
    # Investegate RNS component (NEW; UK tickers only)
    rns_score: float = 0.0
    rns_counts: dict[str, int] = field(default_factory=dict)
    rns_decayed: dict[str, float] = field(default_factory=dict)
    rns_total_items: int = 0
    rns_available: bool = False
    # Combined
    signal_score: float = 0.0


# ---------------------------------------------------------------------------
# RSS

def _fetch_rss(url: str, timeout: int = 15) -> list[dict] | None:
    """Returns list on success, None on fetch failure (NOT empty list).
    This distinction lets the screener flag incomplete coverage rather
    than silently treating fetch failures as no-signal."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    items: list[dict] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        items.append({"title": title, "link": link, "pubDate": pub})
    return items


def _google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote_plus(query)
        + "&hl=en-GB&gl=GB&ceid=GB:en"
    )


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _decay_weight(dt: datetime | None, half_life_days: int) -> float:
    if dt is None:
        return 1.0
    age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    return 0.5 ** (age_days / max(1, half_life_days))


def _parse_amount_gbp(text: str) -> float:
    m = AMOUNT_RE.search(text)
    if not m:
        return 0.0
    val = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit in ("million", "m"):
        val *= 1_000_000
    elif unit in ("thousand", "k"):
        val *= 1_000
    return val


# ---------------------------------------------------------------------------
# Entity verification

def _entity_match(title: str, ticker: str, name: str,
                  exclusions: list[str]) -> bool:
    """Headline must mention either the ticker or the fund name; must
    not contain any exclusion term."""
    tl = title.lower()
    for excl in exclusions:
        if excl.lower() in tl:
            return False
    # Strict name match — require the AIC name (or the EPIC) to appear
    # somewhere in the title. Reduces Conduit/PSUS-style contamination.
    if name and len(name) >= 4:
        if name.lower() in tl:
            return True
    if ticker:
        # accept "EPIC.L", " EPIC ", "(EPIC)", "EPIC.L"
        epic = ticker.split(".")[0]
        for needle in (f" {epic} ", f"({epic})", f"{epic}.L", f"{epic}:"):
            if needle.lower() in tl:
                return True
    return False


def _classify(title: str) -> str | None:
    """Return the strongest single category that matches the title, or
    None if no category matches. Strongest first — categories higher
    up the ORDER list win when there's overlap."""
    for cat in CATEGORY_ORDER:
        if CATEGORY_PATTERNS[cat].search(title):
            # For director_dealings, additionally reject negative verbs
            if cat == "director_dealings" and NEGATIVE_DIRECTOR_RE.search(title):
                return None
            return cat
    return None


# ---------------------------------------------------------------------------
# Per-ticker fetch

def fetch_signals_for(
    ticker: str,
    name: str,
    *,
    lookback_days: int = params.SIGNAL_LOOKBACK_DAYS,
    half_life_days: int = params.SIGNAL_HALF_LIFE_DAYS,
    include_news: bool = True,
) -> TickerSignals:
    """include_news=False is the fast path: only Investegate RNS is
    fetched (1 HTTP request vs ~16 Google News queries). signal_score
    falls back to rns_score alone."""
    sig = TickerSignals(ticker=ticker, name=name or "")
    exclusions = list(params.SIGNAL_EXCLUSIONS.get(ticker, []))

    seen_titles: set[str] = set()
    by_cat: dict[str, list[tuple[float, str]]] = {c: [] for c in CATEGORY_ORDER}
    sample_titles: dict[str, list[str]] = {c: [] for c in CATEGORY_ORDER}

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    director_amount_total = 0.0

    for cat, templates in QUERY_TEMPLATES.items():
        if not name or not include_news:
            continue
        for tpl in templates:
            q = tpl.format(name=name)
            items = _fetch_rss(_google_news_url(q))
            sig.queries_run += 1
            if items is None:
                sig.queries_failed += 1
                sig.coverage_ok = False
                continue
            for it in items:
                title = it.get("title", "")
                if not title or title in seen_titles:
                    continue
                # Time window
                dt = _parse_dt(it.get("pubDate", ""))
                if dt is not None and dt < cutoff:
                    continue
                # Entity check
                if not _entity_match(title, ticker, name, exclusions):
                    continue
                # Best category for this headline (cross-cat dedupe)
                assigned = _classify(title)
                if assigned is None:
                    continue
                seen_titles.add(title)
                weight = _decay_weight(dt, half_life_days)
                by_cat[assigned].append((weight, title))
                if assigned == "director_dealings":
                    director_amount_total += _parse_amount_gbp(title)
                if len(sample_titles[assigned]) < 3:
                    sample_titles[assigned].append(title[:100])
            time.sleep(0.05)

    counts = {c: sum(w for w, _ in by_cat[c]) for c in CATEGORY_ORDER}
    raw_counts = {c: len(by_cat[c]) for c in CATEGORY_ORDER}

    # Saturating non-linearity per category — diminishing returns.
    def _sat(x: float) -> float:
        return 1.0 - 1.0 / (1.0 + x / 3.0)

    news_composite = 0.0
    for c, w in WEIGHTS.items():
        news_composite += w * _sat(counts.get(c, 0.0))

    # Bonus for verified £ insider buying — saturates at £500k.
    if director_amount_total > 0:
        amt_bonus = min(0.20, math.log1p(director_amount_total / 1e5) * 0.05)
        news_composite = min(1.0, news_composite + amt_bonus)

    sig.counts = counts
    sig.raw_counts = raw_counts
    sig.news_score = news_composite
    sig.director_total_gbp = director_amount_total
    sig.sample_titles = sample_titles

    # ---- Investegate RNS layer (UK tickers only) ----
    epic = inv_mod.epic_from_ticker(ticker) if _HAS_INV else None
    if epic:
        try:
            items = inv_mod.fetch_company(epic)
            sig.rns_total_items = len(items)
            sig.rns_available = bool(items)
            if items:
                rns_comp, dec, raw = inv_mod.signal_score_from_rns(
                    items,
                    lookback_days=lookback_days,
                    half_life_days=half_life_days,
                )
                sig.rns_score = rns_comp
                sig.rns_counts = raw
                sig.rns_decayed = dec
        except Exception:
            sig.rns_available = False

    # ---- Combined score ----
    # Weighted blend when both sources were attempted; single-source
    # fallback otherwise (don't dilute RNS with a zero news score that
    # was never scraped).
    if sig.rns_available and include_news:
        sig.signal_score = 0.60 * sig.rns_score + 0.40 * sig.news_score
    elif sig.rns_available:
        sig.signal_score = sig.rns_score
        sig.coverage_ok = False   # news not attempted
    else:
        sig.signal_score = sig.news_score

    return sig


# ---------------------------------------------------------------------------
# Batch + cache + history

def _read_cache() -> dict:
    """Read pickle cache. Returns the inner ticker->TickerSignals dict
    if the version stamp matches; otherwise treats the cache as stale
    and returns empty (forcing re-fetch). This is what saves us from
    the fallback-page-poisoning hangover."""
    if not os.path.exists(CACHE_PATH):
        return {}
    age = time.time() - os.path.getmtime(CACHE_PATH)
    if age > CACHE_TTL_SECONDS:
        return {}
    try:
        with open(CACHE_PATH, "rb") as f:
            raw = pickle.load(f)
    except Exception:
        return {}
    # Version-stamped envelope: {"version": "...", "entries": {...}}.
    # Old format (raw dict) is treated as unversioned -> invalidate.
    if isinstance(raw, dict) and raw.get("version") == CACHE_SCHEMA_VERSION:
        return raw.get("entries", {})
    return {}


def _write_cache(d: dict) -> None:
    try:
        with open(CACHE_PATH, "wb") as f:
            pickle.dump({"version": CACHE_SCHEMA_VERSION, "entries": d}, f)
    except Exception:
        pass


def _append_history(rows: list[TickerSignals]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new = not os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "ticker", "name",
                        "signal_score", "news_score", "rns_score",
                        "news_director_dec", "news_advisor_dec",
                        "news_review_dec", "news_winddown_dec",
                        "news_buyback_dec", "director_amount_gbp",
                        "rns_tr1", "rns_pdmr", "rns_winddown",
                        "rns_tender", "rns_review", "rns_buyback",
                        "queries_run", "queries_failed",
                        "rns_total_items", "rns_available"])
        for s in rows:
            w.writerow([
                today, s.ticker, s.name,
                round(s.signal_score, 4),
                round(s.news_score, 4),
                round(s.rns_score, 4),
                round(s.counts.get("director_dealings", 0), 3),
                round(s.counts.get("advisor_hired", 0), 3),
                round(s.counts.get("strategic_review", 0), 3),
                round(s.counts.get("wind_down", 0), 3),
                round(s.counts.get("buyback", 0), 3),
                round(s.director_total_gbp, 0),
                s.rns_counts.get("tr1", 0),
                s.rns_counts.get("pdmr", 0),
                s.rns_counts.get("winddown", 0),
                s.rns_counts.get("tender", 0),
                s.rns_counts.get("review", 0),
                s.rns_counts.get("buyback", 0),
                s.queries_run, s.queries_failed,
                s.rns_total_items, s.rns_available,
            ])


def fetch_signals_batch(
    pairs: list[tuple[str, str]],
    *,
    use_cache: bool = True,
    persist_history: bool = True,
    verbose: bool = False,
    include_news: bool = True,
) -> dict[str, TickerSignals]:
    cache = _read_cache() if use_cache else {}
    out: dict[str, TickerSignals] = {}
    need: list[tuple[str, str]] = []
    cache_key_suffix = "_rns" if not include_news else ""
    for t, n in pairs:
        ck = t + cache_key_suffix
        if use_cache and ck in cache:
            out[t] = cache[ck]
        else:
            need.append((t, n))
    if verbose:
        print(f"[signals] cache hits: {len(out)}; fetching: {len(need)} "
              f"(include_news={include_news})")
    for i, (t, n) in enumerate(need, 1):
        sig = fetch_signals_for(t, n, include_news=include_news)
        out[t] = sig
        cache[t + cache_key_suffix] = sig
        if verbose and i % 20 == 0:
            print(f"  [{i}/{len(need)}] {t}: score={sig.signal_score:.2f} "
                  f"(rns={sig.rns_score:.2f}, news={sig.news_score:.2f})",
                  flush=True)
    if use_cache:
        _write_cache(cache)
    if persist_history and need:
        _append_history([out[t] for t, _ in need])
    return out


if __name__ == "__main__":
    samples = [
        ("SEIT.L", "SDCL Efficiency Income"),
        ("CHRY.L", "Chrysalis Investments"),
        ("PSH.L",  "Pershing Square Holdings"),
        ("OCI.L",  "Oakley Capital Investments"),
        ("SOHO.L", "Social Housing REIT"),
    ]
    res = fetch_signals_batch(samples, verbose=True)
    print()
    print(f"{'Ticker':<8} {'Final':>6} {'News':>6} {'RNS':>6} "
          f"{'tr1':>4} {'pdmr':>5} {'wd':>4} {'buy':>4} {'Dir£':>10}")
    for t, s in sorted(res.items(), key=lambda kv: -kv[1].signal_score):
        print(f"{t:<8} {s.signal_score:>6.2f} {s.news_score:>6.2f} {s.rns_score:>6.2f} "
              f"{s.rns_counts.get('tr1',0):>4} "
              f"{s.rns_counts.get('pdmr',0):>5} "
              f"{s.rns_counts.get('winddown',0):>4} "
              f"{s.rns_counts.get('buyback',0):>4} "
              f"£{s.director_total_gbp:>9,.0f}")
