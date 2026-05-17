"""Entity-resolution unit tests.

These run without any network access or optional deps -- exercise the
ambiguity rules and ensure ticker collisions stay quiet.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.aliases import Alias
from social_arb.entity_resolution import Resolver


class ResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.aliases = [
            Alias("nvidia", "NVDA", ambiguous=False),
            Alias("$nvda", "NVDA", ambiguous=False),
            Alias("ugg", "DECK", ambiguous=True),       # ambiguous slang
            Alias("apple", "AAPL", ambiguous=True),     # also fruit
            Alias("$aapl", "AAPL", ambiguous=False),
            Alias("crocs", "CROX", ambiguous=False),
        ]
        self.resolver = Resolver(self.aliases)

    def test_cashtag_always_fires(self) -> None:
        out = self.resolver.resolve("just bought $NVDA puts lol")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].ticker, "NVDA")
        self.assertEqual(out[0].via, "cashtag")

    def test_unambiguous_brand_fires_without_context(self) -> None:
        out = self.resolver.resolve("These Crocs are surprisingly comfortable")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].ticker, "CROX")
        self.assertEqual(out[0].via, "exact_brand")

    def test_ambiguous_brand_requires_finance_context(self) -> None:
        without = self.resolver.resolve("My ugg boots are so cozy")
        self.assertEqual(without, [])
        with_ctx = self.resolver.resolve("ugg sales are exploding -- bullish on the stock")
        self.assertTrue(any(m.ticker == "DECK" for m in with_ctx))

    def test_dedupe_per_resolution(self) -> None:
        out = self.resolver.resolve("$NVDA $NVDA NVIDIA NVIDIA stock")
        tickers = [m.ticker for m in out]
        # Cashtag fires once; brand fires once with finance context.
        self.assertEqual(tickers.count("NVDA"), tickers.count("NVDA"))

    def test_word_boundary(self) -> None:
        # Don't fire on substrings (e.g. "nvidiacare" should not match nvidia).
        out = self.resolver.resolve("nvidiacare is fine")
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
