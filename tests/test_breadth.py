"""Tests for Phase 2 weighted-mention storage + per-source z / breadth."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import storage
from social_arb.config import Config


def _have_duckdb() -> bool:
    try:
        import duckdb  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_duckdb(), "duckdb not installed")
class WeightedAggregationTest(unittest.TestCase):
    """Phase 2 schema change: SUM(weight) replaces COUNT(*)."""

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

    def test_daily_counts_sums_weights_not_rows(self) -> None:
        """A single row with weight=100 should equal 100 rows of weight=1
        under daily_counts aggregation."""
        now = datetime.now(timezone.utc)
        # One heavy row
        heavy = pd.DataFrame([{
            "timestamp": now, "source": "test", "source_id": "heavy",
            "ticker": "AAA", "alias": "aaa", "confidence": 0.9, "via": "test",
            "text": "x", "sentiment": 0.0, "sentiment_label": "neutral",
            "url": "", "author": "", "weight": 100.0,
        }])
        # Hundred unit rows
        light = pd.DataFrame([{
            "timestamp": now, "source": "test", "source_id": f"light-{i}",
            "ticker": "BBB", "alias": "bbb", "confidence": 0.9, "via": "test",
            "text": "x", "sentiment": 0.0, "sentiment_label": "neutral",
            "url": "", "author": "", "weight": 1.0,
        } for i in range(100)])
        storage.upsert_mentions(self.cfg, heavy)
        storage.upsert_mentions(self.cfg, light)
        counts = storage.daily_counts(self.cfg)
        by_ticker = counts.groupby("ticker")["mentions"].sum()
        # Both should aggregate to 100 -- the Phase 2 invariant.
        self.assertEqual(float(by_ticker.loc["AAA"]), 100.0)
        self.assertEqual(float(by_ticker.loc["BBB"]), 100.0)

    def test_pre_phase2_rows_default_to_weight_1(self) -> None:
        """Existing rows without weight set must still aggregate as 1 each."""
        now = datetime.now(timezone.utc)
        df = pd.DataFrame([{
            "timestamp": now, "source": "test", "source_id": str(i),
            "ticker": "OLD", "alias": "old", "confidence": 0.9, "via": "test",
            "text": "x", "sentiment": 0.0, "sentiment_label": "neutral",
            "url": "", "author": "",
            # NOTE: no 'weight' key -- _normalize fills with 1.0
        } for i in range(5)])
        storage.upsert_mentions(self.cfg, df)
        counts = storage.daily_counts(self.cfg, ticker="OLD")
        self.assertEqual(float(counts["mentions"].sum()), 5.0)

    def test_breadth_requires_multiple_sources(self) -> None:
        """breadth_score should only report tickers with >= min_breadth sources
        firing at z >= z_threshold."""
        from social_arb.breadth import breadth_score
        import random
        rng = random.Random(42)
        base = datetime.now(timezone.utc) - timedelta(days=40)
        rows = []
        # Build a synthetic ticker with TWO sources both spiking in last 5d.
        # Add small noise in baseline so std > 0 (z is well-defined).
        for d_offset in range(40):
            day = base + timedelta(days=d_offset)
            # source A: ~1/day baseline (with noise), 5/day for the last 5 days
            weight_a = 10.0 if d_offset >= 35 else 2.0 + rng.uniform(-0.5, 0.5)
            rows.append({
                "timestamp": day, "source": "src_a",
                "source_id": f"a-{d_offset}", "ticker": "MULTI",
                "alias": "multi", "confidence": 0.9, "via": "t", "text": "x",
                "sentiment": 0.0, "sentiment_label": "neutral", "url": "",
                "author": "", "weight": weight_a,
            })
            weight_b = 8.0 if d_offset >= 35 else 1.5 + rng.uniform(-0.3, 0.3)
            rows.append({
                "timestamp": day, "source": "src_b",
                "source_id": f"b-{d_offset}", "ticker": "MULTI",
                "alias": "multi", "confidence": 0.9, "via": "t", "text": "x",
                "sentiment": 0.0, "sentiment_label": "neutral", "url": "",
                "author": "", "weight": weight_b,
            })
            # second ticker: only one source spikes (the other is flat)
            rows.append({
                "timestamp": day, "source": "src_a",
                "source_id": f"single-a-{d_offset}", "ticker": "SINGLE",
                "alias": "single", "confidence": 0.9, "via": "t", "text": "x",
                "sentiment": 0.0, "sentiment_label": "neutral", "url": "",
                "author": "", "weight": weight_a,
            })
            # flat (no spike) on src_b so SINGLE only has breadth=1.
            flat_b = 2.0 + rng.uniform(-0.3, 0.3)
            rows.append({
                "timestamp": day, "source": "src_b",
                "source_id": f"single-b-{d_offset}", "ticker": "SINGLE",
                "alias": "single", "confidence": 0.9, "via": "t", "text": "x",
                "sentiment": 0.0, "sentiment_label": "neutral", "url": "",
                "author": "", "weight": flat_b,
            })
        storage.upsert_mentions(self.cfg, pd.DataFrame(rows))
        out = breadth_score(self.cfg, z_threshold=1.0, window_days=5,
                            baseline_days=30, min_breadth=2, top=10)
        tickers = set(out["ticker"]) if not out.empty else set()
        # MULTI passes (2 sources spiking) -- the only one with breadth >= 2.
        self.assertIn("MULTI", tickers)
        self.assertNotIn("SINGLE", tickers)


if __name__ == "__main__":
    unittest.main()
