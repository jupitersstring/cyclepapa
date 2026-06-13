"""Map free text (social posts, news, transcripts) to tickers.

The resolver uses a two-pass strategy that mirrors the report's
recommendation:

  1. Unambiguous match -- explicit cashtag (`$AAPL`) or unique brand alias.
  2. Ambiguous match -- term is a common word ("apple", "ugg") or short
     symbol (`X`); only fires when a finance-context word co-occurs within
     the same post.

Finance-context word list deliberately conservative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .aliases import Alias

CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")

FINANCE_CONTEXT_WORDS = {
    "stock", "stocks", "shares", "share", "ticker", "earnings", "eps",
    "revenue", "guidance", "calls", "puts", "options", "iv", "delta",
    "buyback", "dividend", "guidance", "10-q", "10-k", "8-k", "filing",
    "analyst", "upgrade", "downgrade", "price target", "pt",
    "long", "short", "puts", "yolo", "position", "portfolio", "bagholder",
    "moass", "bull", "bear", "rally", "dump", "moon", "tendies",
}


@dataclass
class Mention:
    text: str
    ticker: str
    alias: str
    confidence: float          # 0.0 - 1.0
    via: str                   # "cashtag" | "exact_brand" | "context_brand"


class Resolver:
    def __init__(self, aliases: list[Alias]) -> None:
        # Build a lookup: alias -> (ticker, ambiguous)
        self._exact: dict[str, tuple[str, bool]] = {}
        for a in aliases:
            # last-write wins; user CSV should put canonical first
            self._exact[a.alias] = (a.ticker, a.ambiguous)
        # Cache compiled regex for brand phrases (longest first to prefer
        # multi-word brands over single-word substrings).
        terms = sorted(self._exact.keys(), key=len, reverse=True)
        # Escape and join into one alternation; word boundaries handled below.
        if terms:
            pattern = "|".join(re.escape(t) for t in terms)
            self._brand_re = re.compile(r"(?<![\w$])(" + pattern + r")(?![\w])", re.IGNORECASE)
        else:
            self._brand_re = None

    def resolve(self, text: str) -> list[Mention]:
        if not text:
            return []
        # Normalize underscores and hyphens to spaces so multi-word brand
        # aliases ("lululemon athletica") match Wikipedia URL-slug titles
        # ("Lululemon_Athletica") and hyphen-joined forms ("Build-A-Bear").
        # Apply for both finance-context detection and brand matching.
        text_norm = re.sub(r"[_-]", " ", text)
        lower = text_norm.lower()
        finance_hit = any(w in lower for w in FINANCE_CONTEXT_WORDS)

        seen: set[tuple[str, str]] = set()
        out: list[Mention] = []

        # Pass 1: cashtags - always unambiguous. Run on the ORIGINAL text
        # (cashtags don't contain hyphens / underscores, and the original
        # preserves casing for the symbol).
        for m in CASHTAG_RE.finditer(text):
            sym = m.group(1).upper()
            key = (sym, "$" + sym.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(Mention(text=text, ticker=sym, alias=key[1], confidence=0.95, via="cashtag"))

        # Pass 2: brand aliases -- run against the normalized text.
        if self._brand_re is not None:
            for m in self._brand_re.finditer(text_norm):
                alias = m.group(1).lower()
                ticker, ambiguous = self._exact.get(alias, ("", True))
                if not ticker or ticker == "PRIVATE":
                    continue
                key = (ticker, alias)
                if key in seen:
                    continue
                if ambiguous and not finance_hit:
                    continue
                conf = 0.85 if not ambiguous else 0.55
                via = "exact_brand" if not ambiguous else "context_brand"
                seen.add(key)
                out.append(Mention(text=text, ticker=ticker, alias=alias, confidence=conf, via=via))

        return out
