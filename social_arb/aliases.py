"""Brand / product aliases for entity resolution.

The single biggest implementation pitfall in social-arb pipelines is ticker
collisions ($X is US Steel and a domain; $APPL doesn't exist but "Apple" hits
fruit). We seed a small high-quality mapping for the Camillo-archetype names
and let users append to it via CSV.

Each row maps an alias (case-insensitive) to a ticker. An alias is "ambiguous"
if the term is also a common English word -- those require a finance-context
co-occurrence before they fire as a mention.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


# Curated seed: Camillo's published trades plus a handful of common collisions.
# Keep aliases lowercase; the resolver normalizes on read.
SEED_ALIASES: list[tuple[str, str, bool]] = [
    # (alias, ticker, ambiguous)
    ("cannondale", "DII.B.TO", False),         # Dorel (delisted post-buyout; placeholder)
    ("dorel", "DII.B.TO", False),
    ("mattel", "MAT", False),
    ("barbie", "MAT", True),                    # film + doll + name
    ("hot wheels", "MAT", False),
    ("crocs", "CROX", False),
    ("celsius energy", "CELH", False),
    ("celsius drink", "CELH", False),
    ("$celh", "CELH", False),
    ("tapestry", "TPR", False),
    ("coach handbag", "TPR", False),
    ("kate spade", "TPR", False),
    ("newell brands", "NWL", False),
    ("elmer's glue", "NWL", False),
    ("rubbermaid", "NWL", False),
    ("sharpie", "NWL", False),
    ("yankee candle", "NWL", False),
    ("under armour", "UAA", False),
    ("lululemon", "LULU", False),
    ("ugg", "DECK", True),                      # also slang
    ("hoka", "DECK", False),
    ("teva sandals", "DECK", False),
    ("nvidia", "NVDA", False),
    ("$nvda", "NVDA", False),
    ("stanley cup tumbler", "ELUX-B.ST", True), # Stanley brand owner placeholder; collides with NHL
    ("hydroflask", "HELE", False),              # Helen of Troy
    ("yeti", "YETI", False),
    ("owala", "PRIVATE", True),                 # private; tracked for read-across
    ("gamestop", "GME", False),
    ("$gme", "GME", False),
    ("sol de janeiro", "ULTA", True),           # sold at Ulta; read-across only
    ("temu", "PDD", False),
    ("shein", "PRIVATE", True),
    ("amazon", "AMZN", False),
    ("$amzn", "AMZN", False),
]


@dataclass(frozen=True)
class Alias:
    alias: str
    ticker: str
    ambiguous: bool


def write_seed_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["alias", "ticker", "ambiguous"])
        for alias, ticker, ambiguous in SEED_ALIASES:
            writer.writerow([alias, ticker, int(ambiguous)])
    return path


def load_aliases(cfg: Config) -> list[Alias]:
    path = Path(cfg.aliases_csv)
    if not path.exists():
        write_seed_csv(path)
    df = pd.read_csv(path)
    out: list[Alias] = []
    for row in df.itertuples(index=False):
        out.append(
            Alias(
                alias=str(row.alias).lower().strip(),
                ticker=str(row.ticker).upper().strip(),
                ambiguous=bool(int(row.ambiguous)),
            )
        )
    return out


def from_universe(universe: pd.DataFrame) -> list[Alias]:
    """Auto-derive aliases from a financedatabase universe.

    Adds:
      - the symbol itself (e.g. "AAPL")
      - the cashtag form ("$AAPL")
      - the company name with corporate suffixes stripped
    None are flagged ambiguous; consumer-facing aliases live in the CSV.
    """
    out: list[Alias] = []
    suffixes = (
        " inc", " inc.", " incorporated", " corp", " corp.", " corporation",
        " co", " co.", " ltd", " ltd.", " plc", " sa", " ag", " holdings",
        " holding", " group", " brands", " company",
    )
    for row in universe.itertuples(index=False):
        sym = str(getattr(row, "symbol", "")).upper().strip()
        name = str(getattr(row, "name", "")).lower().strip()
        if not sym:
            continue
        out.append(Alias(alias=sym.lower(), ticker=sym, ambiguous=len(sym) <= 2))
        out.append(Alias(alias=f"${sym.lower()}", ticker=sym, ambiguous=False))
        if name:
            short = name
            for suf in suffixes:
                if short.endswith(suf):
                    short = short[: -len(suf)].strip(" ,.")
                    break
            if short and len(short) >= 4:
                out.append(Alias(alias=short, ticker=sym, ambiguous=False))
    return out
