"""Tests for tools/niche_picker.py.

Covers: NicheCandidate V2 fields, scoring, rotation rules, history compat.
No browser/API calls — all pure logic.
"""

from __future__ import annotations

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.niche_picker import (
    NicheCandidate,
    NicheHistoryEntry,
    NICHE_POOL,
    _rotation_penalties,
    pick_niche,
)

_VALID_INTENTS = {"general", "gaming", "travel", "fitness", "work", "creative"}
_VALID_PRICE_BANDS = {"budget", "mid", "premium"}


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _days_ago_str(days: int) -> str:
    d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return d.strftime("%Y-%m-%d")


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


class TestScoring(unittest.TestCase):
    """Static scoring and bounds."""

    def test_scoring_max_100(self):
        """No niche's static_score + max rotation bonus (30) exceeds 100."""
        for n in NICHE_POOL:
            total = n.static_score + 30  # max rotation bonus
            self.assertLessEqual(total, 100,
                                 f"{n.keyword} total {total} > 100")

    def test_scoring_min_positive(self):
        """All niches have positive static_score."""
        for n in NICHE_POOL:
            self.assertGreater(n.static_score, 0,
                               f"{n.keyword} has non-positive static_score")

    def test_static_score_backward_compat(self):
        """score property should equal static_score."""
        n = NicheCandidate("test", "cat", review_coverage=5, amazon_depth=5, monetization=5)
        self.assertEqual(n.score, n.static_score)


class TestRotationPenalties(unittest.TestCase):
    """Rotation bonus logic."""

    def test_rotation_no_penalty_when_clear(self):
        """Full 30 bonus when no conflicts at all."""
        niche = NicheCandidate("wireless earbuds", "audio", intent="general")
        history: list[NicheHistoryEntry] = []
        bonus = _rotation_penalties(niche, history)
        self.assertEqual(bonus, 30)

    def test_rotation_penalty_same_category_2_days(self):
        """Same category 1 day ago removes 15 bonus."""
        niche = NicheCandidate("wireless earbuds", "audio", intent="general")
        history = [
            NicheHistoryEntry(date=_days_ago_str(1), niche="over-ear headphones",
                              category="audio"),
        ]
        bonus = _rotation_penalties(niche, history)
        # Lost category bonus (15), still have subcategory (10) + intent depends
        self.assertLess(bonus, 30)
        # Category blocked = lose 15
        self.assertLessEqual(bonus, 15)

    def test_rotation_penalty_same_subcategory_14_days(self):
        """Same subcategory 10 days ago removes 10 bonus."""
        niche = NicheCandidate("wireless earbuds", "audio",
                               subcategory="true wireless earbuds", intent="general")
        history = [
            NicheHistoryEntry(date=_days_ago_str(10), niche="wireless earbuds",
                              subcategory="true wireless earbuds"),
        ]
        bonus = _rotation_penalties(niche, history)
        # Lost subcategory bonus (10)
        self.assertLessEqual(bonus, 20)

    def test_rotation_penalty_same_intent_7_days(self):
        """Same intent 3 days ago removes 5 bonus."""
        niche = NicheCandidate("wireless earbuds", "audio", intent="gaming")
        history = [
            NicheHistoryEntry(date=_days_ago_str(3), niche="gaming mice",
                              category="computing", intent="gaming"),
        ]
        bonus = _rotation_penalties(niche, history)
        # Lost intent bonus (5), but category/subcategory are fine
        self.assertLessEqual(bonus, 25)


class TestPickNiche(unittest.TestCase):
    """pick_niche() integration tests."""

    @patch("tools.niche_picker.load_history", return_value=[])
    @patch("tools.niche_picker._recently_used", return_value=set())
    def test_pick_niche_prefers_high_score(self, mock_used, mock_hist):
        """With no history, picks highest-scored niche."""
        niche = pick_niche("2026-01-01")
        self.assertIsInstance(niche, NicheCandidate)
        self.assertTrue(niche.keyword)
        # Should be one of the premium high-scoring niches
        self.assertGreater(niche.static_score, 50)

    @patch("tools.niche_picker.load_history", return_value=[])
    def test_pick_niche_excludes_60_day(self, mock_hist):
        """60-day keyword exclusion still works."""
        used = {"wireless earbuds"}
        with patch("tools.niche_picker._recently_used", return_value=used):
            niche = pick_niche("2026-01-01")
            self.assertNotEqual(niche.keyword, "wireless earbuds")

    @patch("tools.niche_picker.load_history", return_value=[])
    @patch("tools.niche_picker._recently_used", return_value=set())
    def test_pick_niche_deterministic(self, mock_used, mock_hist):
        """Same date + history = same pick."""
        n1 = pick_niche("2026-03-15")
        n2 = pick_niche("2026-03-15")
        self.assertEqual(n1.keyword, n2.keyword)


if __name__ == "__main__":
    unittest.main()
