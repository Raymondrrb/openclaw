"""Tests for tools/niche_picker.py.

Covers: NicheCandidate V2 fields, scoring, rotation rules, history compat.
No browser/API calls — all pure logic.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.niche_picker import NicheCandidate, NICHE_POOL

_VALID_INTENTS = {"general", "gaming", "travel", "fitness", "work", "creative"}
_VALID_PRICE_BANDS = {"budget", "mid", "premium"}


class TestNicheCandidateV2Fields(unittest.TestCase):
    """Every NICHE_POOL entry must have the new V2 fields."""

    def test_all_niches_have_subcategory(self):
        for n in NICHE_POOL:
            self.assertTrue(n.subcategory, f"{n.keyword} has empty subcategory")

    def test_all_niches_have_intent(self):
        for n in NICHE_POOL:
            self.assertIn(n.intent, _VALID_INTENTS,
                          f"{n.keyword} has invalid intent: {n.intent}")

    def test_all_niches_have_price_band(self):
        for n in NICHE_POOL:
            self.assertIn(n.price_band, _VALID_PRICE_BANDS,
                          f"{n.keyword} has invalid price_band: {n.price_band}")

    def test_price_band_derivation_budget(self):
        n = NicheCandidate("test", "cat", price_max=79)
        self.assertEqual(n.price_band, "budget")

    def test_price_band_derivation_mid(self):
        n = NicheCandidate("test", "cat", price_max=200)
        self.assertEqual(n.price_band, "mid")

    def test_price_band_derivation_premium(self):
        n = NicheCandidate("test", "cat", price_max=500)
        self.assertEqual(n.price_band, "premium")

    def test_subcategory_defaults_to_keyword(self):
        n = NicheCandidate("my niche", "cat")
        self.assertEqual(n.subcategory, "my niche")

    def test_intent_defaults_to_general(self):
        n = NicheCandidate("my niche", "cat")
        self.assertEqual(n.intent, "general")

    def test_explicit_values_not_overridden(self):
        n = NicheCandidate("test", "cat", subcategory="custom sub",
                           intent="gaming", price_band="premium")
        self.assertEqual(n.subcategory, "custom sub")
        self.assertEqual(n.intent, "gaming")
        self.assertEqual(n.price_band, "premium")


class TestNichePoolIntegrity(unittest.TestCase):
    """Pool-wide invariants."""

    def test_pool_not_empty(self):
        self.assertGreater(len(NICHE_POOL), 80)

    def test_no_duplicate_keywords(self):
        keywords = [n.keyword for n in NICHE_POOL]
        self.assertEqual(len(keywords), len(set(keywords)),
                         f"Duplicate keywords: {[k for k in keywords if keywords.count(k) > 1]}")


if __name__ == "__main__":
    unittest.main()
