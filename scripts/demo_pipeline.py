"""End-to-end demo using synthetic mentions.

Useful for offline validation: generates 90 days of fake mentions for a few
Camillo-archetype tickers (MAT, CROX, CELH, DECK) with an injected
mention-spike event, then runs the anomaly detector and prints what fired.

    python scripts/demo_pipeline.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import storage
from social_arb.anomaly import AnomalyParams
from social_arb.config import Config
from social_arb.pipeline import Pipeline


def synthesize(rng: np.random.Generator, n_days: int = 90) -> pd.DataFrame:
    end = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    rows = []
    tickers = [("MAT", 4), ("CROX", 6), ("CELH", 8), ("DECK", 5)]
    spike_day = 75
    for ticker, lam in tickers:
        for d in range(n_days):
            count = int(rng.poisson(lam))
            if ticker == "CROX" and d == spike_day:
                count = 250  # injected attention spike
            ts = end - timedelta(days=n_days - d)
            for i in range(count):
                rows.append({
                    "timestamp": ts + timedelta(seconds=i),
                    "source": "demo",
                    "source_id": f"{ticker}-{d}-{i}",
                    "ticker": ticker,
                    "alias": ticker.lower(),
                    "confidence": 0.9,
                    "via": "exact_brand",
                    "text": f"demo mention {ticker} day {d}",
                    "sentiment": float(rng.normal(0.1 if ticker != "DECK" else -0.1, 0.2)),
                    "sentiment_label": "neutral",
                    "url": "https://example.com",
                    "author": f"user{rng.integers(1, 100)}",
                })
    return pd.DataFrame(rows)


def main() -> int:
    rng = np.random.default_rng(2026)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(
            data_dir=Path(tmp),
            duckdb_path=Path(tmp) / "demo.duckdb",
            universe_parquet=Path(tmp) / "u.parquet",
            aliases_csv=Path(tmp) / "a.csv",
        )
        cfg.ensure_dirs()
        df = synthesize(rng)
        inserted = storage.upsert_mentions(cfg, df)
        print(f"synthesized + stored {inserted:,} mentions")

        pipe = Pipeline(
            cfg=cfg,
            resolver=None,        # not needed -- mentions already resolved
            sentiment=None,
            universe_df=pd.DataFrame(),
        )

        for ticker in ["MAT", "CROX", "CELH", "DECK"]:
            params = AnomalyParams(halflife_days=14, z_thresh=3.0, min_periods=7)
            out = pipe.detect_anomalies(ticker, params=params)
            flagged = out[out["anomaly"]]
            print(f"\n=== {ticker} ===")
            print(f"days observed: {len(out)}, anomalies: {len(flagged)}")
            if not flagged.empty:
                print(flagged[["log_mentions", "mu", "sigma", "z"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
