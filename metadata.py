"""Universe metadata loader.

Single source of truth: universe.csv with columns
    ticker, isin, name, group, catalyst, nav_quality, discount_override,
    aic_sector, market_cap_gbp_m, catalyst_date, catalyst_source_url, notes.

Loader rejects duplicate tickers (the bug class that previously caused
SEIT.L and NESF.L to be silently mis-tagged), validates catalyst and
nav_quality values against the known sets in params.py, and exposes:
    load_universe() -> dict[str, Row]
    catalyst_of(ticker)
    nav_quality_of(ticker)
    discount_override(ticker)
    isin_of(ticker)
    name_of(ticker)
    groups() -> dict[group, list[ticker]]
    all_tickers()
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from params import CATALYST_PROB_BASE, RECOVERY_RATE


UNIVERSE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "universe.csv")

VALID_CATALYSTS = set(CATALYST_PROB_BASE.keys()) | {""}
VALID_NAV_CLASSES = set(RECOVERY_RATE.keys()) | {""}


@dataclass
class Row:
    ticker: str
    isin: str = ""
    name: str = ""
    group: str = ""
    catalyst: str = ""
    nav_quality: str = ""
    discount_override: float | None = None
    aic_sector: str = ""
    market_cap_gbp_m: float | None = None
    catalyst_date: str = ""
    catalyst_source_url: str = ""
    notes: str = ""


class UniverseError(Exception):
    pass


def _to_float(s: str) -> float | None:
    if s is None or s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


_cache: dict[str, Row] | None = None


def load_universe(path: str = UNIVERSE_PATH, force: bool = False) -> dict[str, Row]:
    """Load and validate universe.csv. Returns ticker -> Row dict.

    Raises UniverseError on duplicate ticker, unknown catalyst, or
    unknown nav_quality tag — these are the silent-failure classes that
    bit us before.
    """
    global _cache
    if _cache is not None and not force:
        return _cache
    seen: dict[str, Row] = {}
    errors: list[str] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # row 2 = first data row
            t = (raw.get("ticker") or "").strip().upper()
            if not t:
                continue
            if t in seen:
                errors.append(f"row {i}: duplicate ticker {t}")
                continue
            cat = (raw.get("catalyst") or "").strip()
            if cat not in VALID_CATALYSTS:
                errors.append(f"row {i} {t}: unknown catalyst {cat!r}")
            nav = (raw.get("nav_quality") or "").strip()
            if nav not in VALID_NAV_CLASSES:
                errors.append(f"row {i} {t}: unknown nav_quality {nav!r}")
            seen[t] = Row(
                ticker=t,
                isin=(raw.get("isin") or "").strip(),
                name=(raw.get("name") or "").strip(),
                group=(raw.get("group") or "").strip(),
                catalyst=cat,
                nav_quality=nav,
                discount_override=_to_float(raw.get("discount_override") or ""),
                aic_sector=(raw.get("aic_sector") or "").strip(),
                market_cap_gbp_m=_to_float(raw.get("market_cap_gbp_m") or ""),
                catalyst_date=(raw.get("catalyst_date") or "").strip(),
                catalyst_source_url=(raw.get("catalyst_source_url") or "").strip(),
                notes=(raw.get("notes") or "").strip(),
            )
    if errors:
        raise UniverseError(
            f"{len(errors)} validation error(s) in {path}:\n  "
            + "\n  ".join(errors[:20])
        )
    _cache = seen
    return seen


def all_tickers() -> list[str]:
    return list(load_universe())


def groups() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for t, r in load_universe().items():
        out.setdefault(r.group or "_unassigned", []).append(t)
    return out


def catalyst_of(ticker: str) -> str:
    r = load_universe().get(ticker.upper())
    return r.catalyst if r else ""


def nav_quality_of(ticker: str) -> str:
    r = load_universe().get(ticker.upper())
    return r.nav_quality if r else ""


def discount_override(ticker: str) -> float | None:
    r = load_universe().get(ticker.upper())
    return r.discount_override if r else None


def isin_of(ticker: str) -> str:
    r = load_universe().get(ticker.upper())
    return r.isin if r else ""


def name_of(ticker: str) -> str:
    r = load_universe().get(ticker.upper())
    return r.name if r else ""


if __name__ == "__main__":
    u = load_universe()
    print(f"Loaded {len(u)} tickers")
    print(f"Groups: {len(groups())}")
    print(f"With ISIN: {sum(1 for r in u.values() if r.isin)}")
    print(f"With catalyst: {sum(1 for r in u.values() if r.catalyst)}")
    print(f"With nav_quality: {sum(1 for r in u.values() if r.nav_quality)}")
