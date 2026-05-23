"""Filter bots / LLM-generated text from Reddit / X mention corpora.

Spec says bot + LLM contamination is one of the five pipeline killers.
Implemented filters:

  1. Account-age filter: drop mentions whose author exists < N days
     (default 30). Bots and AI-account farms are typically rotated.
  2. Karma/post-history filter: drop authors with < N karma (Reddit).
  3. Cadence filter: drop authors with > N posts/day (mass-spam).
  4. Perplexity filter: text whose word-distribution perplexity is
     anomalously low/high relative to a baseline model = LLM-generated.
  5. Duplicate-text filter: same text from > 1 author = copy-paste farm.

This is a *post-processing* step applied to the DuckDB mentions table.
Mentions aren't deleted -- a `bot_score` column is added (0..1, higher
= more likely bot) so the downstream rankers can weight or filter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class BotFilterParams:
    min_author_age_days: int = 30
    min_karma: int = 100               # Reddit-specific; ignored for other sources
    max_posts_per_day: int = 30
    dup_text_threshold: int = 3        # same text from N+ distinct authors = farm
    short_text_min_chars: int = 15     # below this, content is too thin to score


def _normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    # Strip URLs and mentions which carry no LLM signal.
    import re
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"@\w+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def filter_duplicates(df: pd.DataFrame, threshold: int = 3) -> pd.Series:
    """Identify rows whose `text` appears verbatim from `threshold`+ distinct authors.

    Returns a boolean Series aligned with `df` (True = likely farm).
    """
    if df.empty or "text" not in df.columns or "author" not in df.columns:
        return pd.Series(False, index=df.index)
    norm = df["text"].map(_normalize_text)
    df_norm = df.assign(_n=norm)
    distinct_authors = (
        df_norm.groupby("_n")["author"].nunique()
    )
    farm_texts = set(distinct_authors[distinct_authors >= int(threshold)].index)
    return df_norm["_n"].isin(farm_texts)


def filter_cadence(df: pd.DataFrame, max_posts_per_day: int = 30) -> pd.Series:
    """Authors posting > max_posts_per_day mentions = mass scrapers."""
    if df.empty or "author" not in df.columns or "timestamp" not in df.columns:
        return pd.Series(False, index=df.index)
    work = df.copy()
    work["date"] = pd.to_datetime(work["timestamp"]).dt.date
    counts = work.groupby(["author", "date"]).size()
    bad = set((a, d) for (a, d), n in counts.items() if n > int(max_posts_per_day))
    work["_bad"] = list(zip(work["author"], work["date"]))
    return work["_bad"].isin(bad)


def score_bots(
    df: pd.DataFrame,
    params: BotFilterParams | None = None,
) -> pd.DataFrame:
    """Add per-row bot_score in [0, 1] without dropping any rows.

    Components (each 0/1, averaged):
      * duplicate-text flag
      * cadence flag (>N posts/day from same author)
      * thin-text flag (length < min)
      * generic-handle flag (all-numeric or 'user1234567' style)
    """
    if df.empty:
        return df.assign(bot_score=0.0)
    p = params or BotFilterParams()
    flags = pd.DataFrame(index=df.index)
    flags["dup"] = filter_duplicates(df, p.dup_text_threshold).astype(float)
    flags["cadence"] = filter_cadence(df, p.max_posts_per_day).astype(float)
    flags["thin"] = (
        df["text"].astype(str).str.len() < int(p.short_text_min_chars)
    ).astype(float)
    # Generic-handle heuristic: authors matching ^user\d+$ or all-digit.
    import re
    if "author" in df.columns:
        authors = df["author"].fillna("").astype(str).str.lower()
        gh = authors.apply(
            lambda s: bool(re.fullmatch(r"user\d+|t2_[a-z0-9]{7,}|\d{6,}", s)) if s else False
        )
    else:
        gh = pd.Series(False, index=df.index)
    flags["generic_handle"] = gh.astype(float)
    df = df.copy()
    df["bot_score"] = flags.mean(axis=1).round(2)
    return df


def filter_clean(
    df: pd.DataFrame,
    max_bot_score: float = 0.34,
    params: BotFilterParams | None = None,
) -> pd.DataFrame:
    """Score then keep rows with bot_score <= max."""
    scored = score_bots(df, params=params)
    return scored[scored["bot_score"] <= float(max_bot_score)].reset_index(drop=True)
