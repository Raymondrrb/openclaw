"""Tests for subcategory contract generation and gate enforcement.

No browser/API calls — all pure logic.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


class TestGenerateContract(unittest.TestCase):
    """Contract generation for known and unknown niches."""

    def test_generate_contract_known_niche_earbuds(self):
        from tools.lib.subcategory_contract import generate_contract
        c = generate_contract("wireless earbuds", "audio")
        self.assertEqual(c.niche_name, "wireless earbuds")
        self.assertEqual(c.category, "audio")
        self.assertIn("earbuds", c.allowed_keywords)
        self.assertIn("headphone", c.disallowed_keywords)

    def test_generate_contract_known_niche_luggage(self):
        from tools.lib.subcategory_contract import generate_contract
        c = generate_contract("carry on luggage", "travel")
        self.assertIn("luggage", c.allowed_keywords)
        self.assertIn("suitcase", c.allowed_keywords)
        self.assertIn("headphone", c.disallowed_keywords)
        self.assertIn("camera", c.disallowed_keywords)

    def test_generate_contract_unknown_niche(self):
        from tools.lib.subcategory_contract import generate_contract
        c = generate_contract("ergonomic pillows", "home")
        # Should fall back to category keywords
        self.assertEqual(c.category, "home")
        self.assertTrue(len(c.allowed_keywords) > 0)
        self.assertTrue(len(c.disallowed_keywords) > 0)

    def test_generate_contract_partial_match(self):
        from tools.lib.subcategory_contract import generate_contract
        c = generate_contract("best wireless earbuds 2026", "audio")
        # Should match "wireless earbuds" template via partial match
        self.assertIn("earbuds", c.allowed_keywords)
        self.assertIn("headphone", c.disallowed_keywords)


class TestPassesGate(unittest.TestCase):
    """Gate enforcement — accepts/rejects products."""

    def _make_contract(self):
        from tools.lib.subcategory_contract import SubcategoryContract
        return SubcategoryContract(
            niche_name="wireless earbuds",
            category="audio",
            allowed_subcategory_labels=["earbuds", "true wireless", "tws"],
            disallowed_labels=["headphone", "over-ear", "on-ear", "speaker", "soundbar"],
            allowed_keywords=["earbuds", "earbud", "true wireless", "tws", "in-ear"],
            disallowed_keywords=["headphone", "over-ear", "speaker", "soundbar"],
            mandatory_keywords=["earbuds", "earbud", "in-ear", "tws"],
            acceptance_test={
                "name_must_not_contain": ["headphone", "over-ear", "speaker", "soundbar"],
                "brand_is_not_product_name": True,
            },
        )

    def test_passes_gate_valid(self):
        from tools.lib.subcategory_contract import passes_gate
        c = self._make_contract()
        # Real product names don't need "earbuds" keyword — negative filtering is enough
        ok, reason = passes_gate("Sony WF-1000XM5", "Sony", c)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_passes_gate_drift_headphones(self):
        from tools.lib.subcategory_contract import passes_gate
        c = self._make_contract()
        ok, reason = passes_gate("Sony WH-1000XM5 Headphones", "Sony", c)
        self.assertFalse(ok)
        self.assertIn("headphone", reason.lower())

    def test_passes_gate_noise_brand_only(self):
        """Brand-only product name is rejected."""
        from tools.lib.subcategory_contract import SubcategoryContract, passes_gate
        c = SubcategoryContract(
            niche_name="carry on luggage",
            category="travel",
            allowed_keywords=["luggage", "suitcase", "carry-on"],
            disallowed_keywords=["backpack", "duffel"],
            mandatory_keywords=["luggage", "suitcase", "carry-on"],
            acceptance_test={
                "name_must_not_contain": ["backpack", "duffel"],
                "brand_is_not_product_name": True,
            },
        )
        ok, reason = passes_gate("Away", "Away", c)
        self.assertFalse(ok)

    def test_passes_gate_disallowed_labels_rejected(self):
        from tools.lib.subcategory_contract import passes_gate
        c = self._make_contract()
        # A soundbar should be rejected
        ok, reason = passes_gate("Bose Smart Soundbar 600 Earbuds Edition", "Bose", c)
        self.assertFalse(ok)
        self.assertIn("soundbar", reason.lower())

    def test_passes_gate_allowed_keyword_in_name(self):
        from tools.lib.subcategory_contract import passes_gate
        c = self._make_contract()
        ok, _ = passes_gate("EarFun Air Pro 3 True Wireless Earbuds", "EarFun", c)
        self.assertTrue(ok)


class TestWriteLoad(unittest.TestCase):
    """JSON roundtrip."""

    def test_write_load_roundtrip(self):
        from tools.lib.subcategory_contract import (
            SubcategoryContract, write_contract, load_contract,
        )
        c = SubcategoryContract(
            niche_name="test",
            category="audio",
            allowed_subcategory_labels=["earbuds"],
            disallowed_labels=["headphone"],
            allowed_keywords=["a", "b"],
            disallowed_keywords=["x", "y"],
            mandatory_keywords=["a"],
            disambiguation_rules="test rule",
            acceptance_test={
                "name_must_contain_one_of": ["a"],
                "name_must_not_contain": ["x"],
                "brand_is_not_product_name": True,
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.json"
            write_contract(c, path)
            loaded = load_contract(path)
        self.assertEqual(loaded.niche_name, "test")
        self.assertEqual(loaded.allowed_subcategory_labels, ["earbuds"])
        self.assertEqual(loaded.disallowed_labels, ["headphone"])
        self.assertEqual(loaded.allowed_keywords, ["a", "b"])
        self.assertEqual(loaded.disallowed_keywords, ["x", "y"])
        self.assertEqual(loaded.mandatory_keywords, ["a"])
        self.assertEqual(loaded.disambiguation_rules, "test rule")
        self.assertEqual(loaded.acceptance_test["name_must_contain_one_of"], ["a"])


class TestAcceptanceTestEnforcement(unittest.TestCase):
    """Acceptance test structured checks."""

    def test_acceptance_test_passes_model_name(self):
        """Product model names pass without needing category keywords."""
        from tools.lib.subcategory_contract import SubcategoryContract, passes_gate
        c = SubcategoryContract(
            niche_name="wireless earbuds",
            category="audio",
            acceptance_test={
                "name_must_not_contain": ["headphone"],
                "brand_is_not_product_name": True,
            },
        )
        ok, reason = passes_gate("Sony WF-1000XM5", "Sony", c)
        self.assertTrue(ok)
        ok, reason = passes_gate("Bose QuietComfort 45 Headphones", "Bose", c)
        self.assertFalse(ok)
        self.assertIn("DRIFT", reason)

    def test_acceptance_test_rejects_disallowed(self):
        from tools.lib.subcategory_contract import SubcategoryContract, passes_gate
        c = SubcategoryContract(
            niche_name="wireless earbuds",
            category="audio",
            disallowed_labels=["gaming headset"],
            acceptance_test={
                "name_must_not_contain": ["headphone", "speaker"],
                "brand_is_not_product_name": True,
            },
        )
        ok, reason = passes_gate("HyperX Cloud Gaming Headset", "HyperX", c)
        self.assertFalse(ok)

    def test_generated_contract_has_acceptance_test(self):
        from tools.lib.subcategory_contract import generate_contract
        c = generate_contract("wireless earbuds", "audio")
        self.assertTrue(len(c.acceptance_test) > 0)
        self.assertIn("name_must_not_contain", c.acceptance_test)
        self.assertTrue(c.acceptance_test.get("brand_is_not_product_name", False))

    def test_generated_contract_has_subcategory_labels(self):
        from tools.lib.subcategory_contract import generate_contract
        c = generate_contract("carry on luggage", "travel")
        self.assertTrue(len(c.allowed_subcategory_labels) > 0)
        self.assertTrue(len(c.disallowed_labels) > 0)


class TestResearchReferencesOnlyThreeDomains(unittest.TestCase):
    """URLs in allowed domains only."""

    def test_research_references_only_3_domains(self):
        from tools.research_agent import _ALLOWED_DOMAINS
        # The module-level constant should list exactly these
        self.assertEqual(_ALLOWED_DOMAINS, {"nytimes.com", "rtings.com", "pcmag.com"})


if __name__ == "__main__":
    unittest.main()
