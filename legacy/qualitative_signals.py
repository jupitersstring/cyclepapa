"""Qualitative-signal scraper for catalyst probability refinement.

The catalyst probability per ticker should reflect what's actually
happening at the company — directors buying their own shares, advisors
being appointed, board communications signalling a tender or wind-down
— not just the static catalyst tag.

This module runs targeted Google News queries per ticker and counts
hits in five signal categories over a configurable lookback window
(default 90 days). The composite signal_score is used downstream to
shift the catalyst_realisation_probability up or down.

Signals tracked:
  - director_dealings: PDMR/director buy / sell activity
  - advisor_hired: investment-bank or restructuring-advisor mandate
  - buyback: share-buyback programme intensity
  - strategic_review: review / continuation / discount-control mentions
  - wind_down: managed wind-down / realisation / tender / liquidation

Per-signal counts feed a weighted composite:
  signal_score = 0.30*director + 0.25*advisor + 0.20*review
               + 0.15*winddown + 0.10*buyback

Cache: /tmp/qual_signals_cache.pkl, TTL 24h.
"""

from __future__ import annotations

import os
import pickle
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


CACHE_PATH = "/tmp/qual_signals_cache.pkl"
CACHE_TTL_SECONDS = 24 * 3600

USER_AGENT = "Mozilla/5.0 (compatible; QualSignals/1.0)"

# Per-signal Google News query templates. Each query is a quoted name
# plus a signal-specific keyword. Multiple queries per signal lets us
# capture variant phrasings.
SIGNAL_QUERIES: dict[str, list[str]] = {
    "director_dealings": [
        '"{name}" director dealings',
        '"{name}" PDMR shareholding',
        '"{name}" director purchase',
        '"{name}" director buys',
    ],
    "advisor_hired": [
        '"{name}" appoints advisor',
        '"{name}" hired Rothschild',
        '"{name}" hired Numis',
        '"{name}" hired Peel Hunt',
        '"{name}" hired Investec',
        '"{name}" restructuring adviser',
        '"{name}" financial adviser appointed',
    ],
    "buyback": [
        '"{name}" buyback',
        '"{name}" share repurchase',
        '"{name}" transaction in own shares',
    ],
    "strategic_review": [
        '"{name}" strategic review',
        '"{name}" continuation vote',
        '"{name}" discount control',
        '"{name}" board review',
    ],
    "wind_down": [
        '"{name}" wind-down',
        '"{name}" wind down',
        '"{name}" managed realisation',
        '"{name}" tender offer',
        '"{name}" cash exit',
        '"{name}" liquidation',
    ],
}

# Composite weighting. Reflects how much each signal type *moves* the
# probability that the discount actually narrows in the next 12-18m.
SIGNAL_WEIGHTS: dict[str, float] = {
    "director_dealings": 0.30,
    "advisor_hired": 0.25,
    "strategic_review": 0.20,
    "wind_down": 0.15,
    "buyback": 0.10,
}


def _read_cache() -> dict | None:
    if not os.path.exists(CACHE_PATH):
        return None
    age = time.time() - os.path.getmtime(CACHE_PATH)
    if age > CACHE_TTL_SECONDS:
        return None
    try:
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _write_cache(data: dict) -> None:
    try:
        with open(CACHE_PATH, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass


def _fetch_rss(url: str, timeout: int = 15) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    items: list[dict] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        pub_date = (node.findtext("pubDate") or "").strip()
        items.append({"title": title, "pubDate": pub_date})
    return items


def _within_window(pub_date_str: str, days: int) -> bool:
    if not pub_date_str:
        return True  # err on inclusive side
    try:
        dt = parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt) <= timedelta(days=days)
    except Exception:
        return True


def fetch_signals_for_ticker(
    ticker: str,
    name: str,
    lookback_days: int = 90,
) -> dict:
    """Return dict of per-signal counts (within window) + composite score."""
    counts: dict[str, int] = {k: 0 for k in SIGNAL_QUERIES}
    seen_titles: dict[str, set[str]] = {k: set() for k in SIGNAL_QUERIES}

    if not name:
        return {**counts, "signal_score": 0.0, "queries_run": 0}

    queries_run = 0
    for signal, templates in SIGNAL_QUERIES.items():
        for tpl in templates:
            q = tpl.format(name=name)
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote_plus(q)
                + "&hl=en-GB&gl=GB&ceid=GB:en"
            )
            items = _fetch_rss(url)
            queries_run += 1
            for it in items:
                title = it.get("title", "")
                # Dedupe — Google News often returns the same story
                # via multiple syndicated sources.
                if title in seen_titles[signal]:
                    continue
                if not _within_window(it.get("pubDate", ""), lookback_days):
                    continue
                seen_titles[signal].add(title)
                counts[signal] += 1
            time.sleep(0.05)  # be polite

    # Normalise each signal to [0, 1] via a saturating logistic-ish curve.
    # Map 0->0, 3->0.5, 10->0.9 — diminishing returns above 10 hits.
    def _sat(n: int) -> float:
        return 1.0 - 1.0 / (1.0 + n / 3.0)

    composite = 0.0
    normalised: dict[str, float] = {}
    for signal, n in counts.items():
        norm = _sat(n)
        normalised[signal] = norm
        composite += SIGNAL_WEIGHTS.get(signal, 0.0) * norm

    return {
        **counts,
        **{f"{k}_norm": v for k, v in normalised.items()},
        "signal_score": composite,
        "queries_run": queries_run,
    }


def fetch_signals_batch(
    tickers_and_names: list[tuple[str, str]],
    lookback_days: int = 90,
    use_cache: bool = True,
    verbose: bool = False,
) -> dict[str, dict]:
    cache = _read_cache() or {} if use_cache else {}
    out: dict[str, dict] = {}
    needed: list[tuple[str, str]] = []
    for tk, nm in tickers_and_names:
        if tk in cache:
            out[tk] = cache[tk]
        else:
            needed.append((tk, nm))
    if verbose:
        print(f"[qual] cache hits: {len(out)}; fetching: {len(needed)}")
    for i, (tk, nm) in enumerate(needed, 1):
        sig = fetch_signals_for_ticker(tk, nm, lookback_days=lookback_days)
        out[tk] = sig
        cache[tk] = sig
        if verbose and i % 5 == 0:
            print(f"  [{i}/{len(needed)}] {tk}: score={sig['signal_score']:.2f}",
                  flush=True)
    if use_cache:
        _write_cache(cache)
    return out


if __name__ == "__main__":
    # Smoke test on a handful of named UK CEFs
    samples = [
        ("SEIT.L", "SDCL Efficiency Income"),
        ("HGT.L", "HgCapital Trust"),
        ("SYNC.L", "Syncona"),
        ("GCP.L", "GCP Infrastructure"),
        ("AEET.L", "Parvus Energy Efficiency Trust"),
        ("SOHO.L", "Social Housing REIT"),
        ("DIVI.L", "Diverse Income Trust"),
        ("CHRY.L", "Chrysalis Investments"),
        ("III.L", "3i Group"),
        ("RESI.L", "Residential Secure Income"),
    ]
    res = fetch_signals_batch(samples, verbose=True)
    print("\nResults:")
    print(f"{'Ticker':<8} {'Score':>6}  {'Dir':>3} {'Adv':>3} {'Rev':>3} {'WD':>3} {'BB':>3}")
    for tk, sig in sorted(res.items(), key=lambda kv: -kv[1].get("signal_score", 0)):
        print(f"{tk:<8} {sig['signal_score']:>6.2f}  "
              f"{sig['director_dealings']:>3} "
              f"{sig['advisor_hired']:>3} "
              f"{sig['strategic_review']:>3} "
              f"{sig['wind_down']:>3} "
              f"{sig['buyback']:>3}")
