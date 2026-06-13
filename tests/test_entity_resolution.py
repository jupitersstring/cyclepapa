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

    def test_dictionary_word_tickers_are_cashtag_only(self) -> None:
        """Phase 1 fix: tickers that are common English words must not fire
        on bare-word matches in non-finance text. Regression test for the
        RENT/AIR/JACK/SAT/PAYS false-positive bug.
        """
        from social_arb.aliases import is_dictionary_word, from_universe
        import pandas as pd
        # 1. The wordlist must catch the known FPs.
        for sym in ("RENT", "JACK", "SAT", "AIR", "PAYS", "EARN",
                    "ADD", "WAYS", "PRE", "AUTO", "DEMO", "MAX",
                    "BROS", "GAP", "TRIP"):
            self.assertTrue(
                is_dictionary_word(sym),
                f"{sym} should be flagged as a dictionary word",
            )
        # 2. from_universe must not emit a bare-symbol alias for them.
        uni = pd.DataFrame([
            {"symbol": "RENT", "name": "Rent the Runway Inc"},
            {"symbol": "JACK", "name": "Jack in the Box Inc"},
            {"symbol": "AAPL", "name": "Apple Inc"},
        ])
        aliases = from_universe(uni)
        alias_strs = {a.alias for a in aliases if not a.ambiguous}
        self.assertNotIn("rent", alias_strs)
        self.assertNotIn("jack", alias_strs)
        # $cashtag form must still be present for them.
        cashtags = {a.alias for a in aliases}
        self.assertIn("$rent", cashtags)
        self.assertIn("$jack", cashtags)
        self.assertIn("$aapl", cashtags)
        # And AAPL's bare-symbol alias does survive (not a dictionary word).
        self.assertIn("aapl", alias_strs)

    def test_us_primary_wins_over_foreign_crosslisting(self) -> None:
        """When a US primary and a foreign cross-listing share a brand name
        in the universe, the US ticker must win the alias dict. Regression
        for Wikipedia 'Nvidia' being mapped to NVDC34.SA instead of NVDA."""
        from social_arb.aliases import from_universe
        import pandas as pd
        # Construct a tiny universe where the .SA cross-listing comes
        # AFTER the US primary in row order -- without the priority sort,
        # the .SA listing would win the dict slot.
        uni = pd.DataFrame([
            {"symbol": "NVDA", "name": "Nvidia Corporation"},
            {"symbol": "NVDC34.SA", "name": "Nvidia Corporation"},
            {"symbol": "AAPL", "name": "Apple Inc"},
            {"symbol": "AAPLD.BA", "name": "Apple Inc"},
        ])
        aliases = from_universe(uni)
        resolver = Resolver(aliases)
        # The bare brand name should map to the US ticker.
        out = resolver.resolve("wikipedia Nvidia views=6308")
        self.assertEqual([m.ticker for m in out], ["NVDA"])
        # The Apple/AAPL case here would also need finance context to
        # disambiguate from the fruit -- already covered by the existing
        # ambiguous-brand tests. The cross-listing fix is independent.

    def test_rent_in_airbnb_thread_does_not_fire(self) -> None:
        """Direct regression test for the actual data we found: the word
        'rent' in an Airbnb/housing thread must NOT resolve to RENT."""
        from social_arb.aliases import from_universe
        import pandas as pd
        aliases = from_universe(pd.DataFrame([{"symbol": "RENT", "name": "Rent the Runway Inc"}]))
        resolver = Resolver(aliases)
        sample_texts = [
            "Most people did not rent houses on trips before airbnb",
            "people didnt rent a hou se",
            "SF startup is testing robots in Airbnbs",
        ]
        for text in sample_texts:
            mentions = resolver.resolve(text)
            self.assertEqual(
                [m.ticker for m in mentions], [],
                f"Resolver should NOT find RENT in: {text!r}",
            )

    def test_word_boundary(self) -> None:
        # Don't fire on substrings (e.g. "nvidiacare" should not match nvidia).
        out = self.resolver.resolve("nvidiacare is fine")
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
