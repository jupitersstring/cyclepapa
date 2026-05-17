"""Runtime configuration for the social arbitrage pipeline.

Loads from env vars; everything has sane defaults so the no-key path works.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    duckdb_path: Path = field(default_factory=lambda: REPO_ROOT / "data" / "social_arb.duckdb")
    universe_parquet: Path = field(default_factory=lambda: REPO_ROOT / "data" / "universe.parquet")
    aliases_csv: Path = field(default_factory=lambda: REPO_ROOT / "data" / "aliases.csv")

    user_agent: str = os.environ.get(
        "SOCIAL_ARB_UA",
        "social-arb/0.1 (research; contact via github issues)",
    )
    http_timeout: float = float(os.environ.get("SOCIAL_ARB_TIMEOUT", "30"))

    reddit_client_id: str | None = os.environ.get("REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = os.environ.get("REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = os.environ.get(
        "REDDIT_USER_AGENT",
        "social-arb/0.1 by u/anon",
    )

    pullpush_base: str = "https://api.pullpush.io/reddit"
    apewisdom_base: str = "https://apewisdom.io/api/v1.0"
    gdelt_doc_base: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    stocktwits_base: str = "https://api.stocktwits.com/api/2"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
