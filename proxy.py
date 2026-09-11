"""Convert a DEF 14A filing into clean text and slice the executive
compensation sections we care about for PSU analysis."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


SECTION_TITLES = (
    "compensation discussion and analysis",
    "executive compensation",
    "grants of plan-based awards",
    "outstanding equity awards",
    "performance share units",
    "performance stock units",
    "long-term incentive",
    "long term incentive",
    "summary compensation table",
)


def html_to_text(html: str) -> str:
    """Strip HTML to whitespace-normalised plain text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def extract_comp_section(text: str, max_chars: int = 200_000) -> str:
    """Return text starting at the earliest known compensation-section
    header. Falls back to the full document if no header matches."""
    lower = text.lower()
    starts = [lower.find(t) for t in SECTION_TITLES]
    starts = [s for s in starts if s >= 0]
    if not starts:
        return text[:max_chars]
    start = min(starts)
    return text[start : start + max_chars]
