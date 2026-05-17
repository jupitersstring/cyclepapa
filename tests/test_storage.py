"""Storage smoke tests.

Use a temp DuckDB file so the live store isn't touched. Skips if duckdb
isn't installed.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.config import Config
from social_arb import storage


def _have_duckdb() -> bool:
    try:
        import duckdb  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_duckdb(), "duckdb not installed")
class StorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cfg = Config(
            data_dir=Path(self.tmpdir.name),
            duckdb_path=Path(self.tmpdir.name) / "test.duckdb",
            universe_parquet=Path(self.tmpdir.name) / "u.parquet",
            aliases_csv=Path(self.tmpdir.name) / "a.csv",
        )
        self.cfg.ensure_dirs()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_upsert_idempotent(self) -> None:
        now = datetime.now(timezone.utc)
        df = pd.DataFrame([{
            "timestamp": now, "source": "test", "source_id": "abc", "ticker": "NVDA",
            "alias": "nvidia", "confidence": 0.9, "via": "exact_brand",
            "text": "test text", "sentiment": 0.5, "sentiment_label": "bullish",
            "url": "https://example.com", "author": "user1",
        }])
        n1 = storage.upsert_mentions(self.cfg, df)
        n2 = storage.upsert_mentions(self.cfg, df)
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 0)
        counts = storage.daily_counts(self.cfg, ticker="NVDA")
        self.assertEqual(int(counts["mentions"].sum()), 1)


if __name__ == "__main__":
    unittest.main()
