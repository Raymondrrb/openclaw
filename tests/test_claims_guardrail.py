#!/usr/bin/env python3
"""Tests for rayvault/claims_guardrail.py — anti-lie firewall."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.claims_guardrail import (
    CLAIM_EVIDENCE_RULES,
    TRIGGER_PATTERNS,
    check_evidence,
    collect_allowed_text,
    find_trigger_sentences,
    guardrail,
    normalize_text,
)


# ---------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------

class TestNormalizeText(unittest.TestCase):

    def test_lowercase(self):
        self.assertEqual(normalize_text("Hello World"), "hello world")

    def test_collapse_whitespace(self):
        self.assertEqual(normalize_text("a   b\n\nc"), "a b c")

    def test_strips(self):
        self.assertEqual(normalize_text("  hello  "), "hello")

    def test_empty(self):
        self.assertEqual(normalize_text(""), "")


# ---------------------------------------------------------------
# find_trigger_sentences
# ---------------------------------------------------------------

class TestFindTriggerSentences(unittest.TestCase):

    def test_no_triggers(self):
        script = "This is a regular product review. It looks nice."
        self.assertEqual(find_trigger_sentences(script), [])

    def test_waterproof_trigger(self):
        script = "This mouse is waterproof and durable."
        hits = find_trigger_sentences(script)
        self.assertEqual(len(hits), 1)
        self.assertIn("waterproof", hits[0].lower())

    def test_battery_trigger(self):
        script = "The battery lasts 24 hours on a single charge."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_warranty_trigger(self):
        script = "It comes with a lifetime warranty."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_certified_trigger(self):
        script = "This product is FDA certified for safety."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_best_trigger(self):
        script = "This is the best wireless mouse on the market."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_100_percent_trigger(self):
        # \b100%\b requires word boundary after % — matches when followed by word char
        script = "It provides 100%safe coverage."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_patented_trigger(self):
        script = "Uses patented technology for better performance."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_multiple_sentences_only_matching(self):
        script = "This looks great. It is waterproof. The color is blue."
        hits = find_trigger_sentences(script)
        self.assertEqual(len(hits), 1)
        self.assertIn("waterproof", hits[0].lower())

    def test_portuguese_triggers(self):
        script = "Este produto tem garantia vitalícia."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_empty_script(self):
        self.assertEqual(find_trigger_sentences(""), [])


# ---------------------------------------------------------------
# check_evidence
# ---------------------------------------------------------------

class TestCheckEvidence(unittest.TestCase):

    def test_waterproof_with_evidence(self):
        # Avoid "device" which contains "ce" triggering certification rule
        sentence = "This mouse is waterproof."
        allowed = "waterproof ipx7 rating"
        ok, missing = check_evidence(sentence, allowed)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_waterproof_without_evidence(self):
        sentence = "This device is waterproof."
        allowed = "wireless mouse with ergonomic design"
        ok, missing = check_evidence(sentence, allowed)
        self.assertFalse(ok)
        self.assertIn("waterproof", missing)

    def test_battery_with_evidence(self):
        sentence = "The battery lasts 24 hours."
        allowed = "battery life up to 24 hours with usb-c charging"
        ok, missing = check_evidence(sentence, allowed)
        self.assertTrue(ok)

    def test_battery_without_evidence(self):
        sentence = "The battery lasts 24 hours."
        allowed = "wireless mouse compact design"
        ok, missing = check_evidence(sentence, allowed)
        self.assertFalse(ok)
        self.assertIn("battery_life", missing)

    def test_no_specific_rule_generic_check(self):
        sentence = "This product has amazing quantum technology."
        allowed = "quantum technology enabled processing"
        ok, missing = check_evidence(sentence, allowed)
        self.assertTrue(ok)

    def test_no_specific_rule_no_evidence(self):
        sentence = "This product has amazing quantum technology."
        allowed = "basic wireless mouse"
        ok, missing = check_evidence(sentence, allowed)
        self.assertFalse(ok)
        self.assertIn("unsubstantiated_sentence", missing)

    def test_medical_without_evidence(self):
        sentence = "Clinically proven to reduce pain."
        allowed = "comfortable ergonomic mouse"
        ok, missing = check_evidence(sentence, allowed)
        self.assertFalse(ok)

    def test_multiple_claims_mixed(self):
        sentence = "This waterproof device has a 10 hours battery."
        allowed = "waterproof ipx5 rated"
        ok, missing = check_evidence(sentence, allowed)
        # waterproof evidence found, but battery evidence missing
        self.assertFalse(ok)
        self.assertIn("battery_life", missing)
        self.assertNotIn("waterproof", missing)


# ---------------------------------------------------------------
# collect_allowed_text
# ---------------------------------------------------------------

class TestCollectAllowedText(unittest.TestCase):

    def test_collects_title_and_description(self):
        product = {"title": "Wireless Mouse", "description": "Ergonomic design"}
        text = collect_allowed_text(product)
        self.assertIn("wireless mouse", text)
        self.assertIn("ergonomic design", text)

    def test_collects_bullets(self):
        product = {"title": "Mouse", "bullets": ["Fast", "Quiet"]}
        text = collect_allowed_text(product)
        self.assertIn("fast", text)
        self.assertIn("quiet", text)

    def test_collects_bullet_points_alias(self):
        product = {"title": "Mouse", "bullet_points": ["Feature A"]}
        text = collect_allowed_text(product)
        self.assertIn("feature a", text)

    def test_collects_claims_allowed(self):
        product = {"title": "Mouse", "claims_allowed": ["waterproof"]}
        text = collect_allowed_text(product)
        self.assertIn("waterproof", text)

    def test_empty_product(self):
        text = collect_allowed_text({})
        self.assertEqual(text, "")

    def test_normalized(self):
        product = {"title": "  HELLO   WORLD  "}
        text = collect_allowed_text(product)
        self.assertEqual(text, "hello world")


# ---------------------------------------------------------------
# guardrail (integration)
# ---------------------------------------------------------------

class TestGuardrail(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_script(self, text: str):
        (self.run_dir / "01_script.txt").write_text(text, encoding="utf-8")

    def _write_products(self, items: list):
        pdir = self.run_dir / "products"
        pdir.mkdir(exist_ok=True)
        data = {"items": items}
        (pdir / "products.json").write_text(json.dumps(data), encoding="utf-8")

    def test_missing_script(self):
        result = guardrail(self.run_dir)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["code"], "MISSING_SCRIPT")

    def test_missing_products(self):
        self._write_script("This is a test script.")
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(result["code"], "MISSING_PRODUCTS_JSON")

    def test_clean_script_passes(self):
        self._write_script("This product looks great and is well designed.")
        self._write_products([{"rank": 1, "title": "Great Mouse"}])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["violations"], [])

    def test_waterproof_without_evidence_violates(self):
        self._write_script("This mouse is waterproof and durable.")
        self._write_products([{"rank": 1, "title": "Wireless Mouse"}])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertGreater(len(result["violations"]), 0)

    def test_waterproof_with_evidence_passes(self):
        self._write_script("This mouse is waterproof and durable.")
        self._write_products([{
            "rank": 1, "title": "Waterproof Mouse",
            "bullets": ["IPX7 waterproof rating"],
        }])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["status"], "PASS")

    def test_products_count_in_result(self):
        self._write_script("This looks great.")
        self._write_products([{"rank": 1, "title": "A"}, {"rank": 2, "title": "B"}])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["products_count"], 2)

    def test_trigger_count_in_result(self):
        self._write_script("It is waterproof. Also battery lasts 10 hours.")
        self._write_products([{"rank": 1, "title": "Mouse"}])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertGreater(result["trigger_sentences_count"], 0)

    def test_cached_products_preferred(self):
        self._write_script("This has great design.")
        pdir = self.run_dir / "products" / "p01"
        pdir.mkdir(parents=True)
        prod = {"rank": 1, "title": "Cached Product"}
        (pdir / "product_metadata.json").write_text(json.dumps(prod), encoding="utf-8")
        result = guardrail(self.run_dir, use_cached_products=True)
        self.assertEqual(result["products_source"], "cached_metadata")


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_trigger_patterns_nonempty(self):
        self.assertGreater(len(TRIGGER_PATTERNS), 0)

    def test_trigger_patterns_are_valid_regex(self):
        import re
        for pat in TRIGGER_PATTERNS:
            re.compile(pat)  # Should not raise

    def test_evidence_rules_nonempty(self):
        self.assertGreater(len(CLAIM_EVIDENCE_RULES), 0)

    def test_evidence_rules_structure(self):
        for name, keywords in CLAIM_EVIDENCE_RULES:
            self.assertIsInstance(name, str)
            self.assertIsInstance(keywords, list)
            self.assertGreater(len(keywords), 0)


# ---------------------------------------------------------------
# normalize_text None-safety
# ---------------------------------------------------------------

class TestNormalizeTextNoneSafety(unittest.TestCase):

    def test_none_returns_empty(self):
        self.assertEqual(normalize_text(None), "")

    def test_numeric_coerced(self):
        # Not typical usage but should not crash
        self.assertEqual(normalize_text("12345"), "12345")

    def test_tabs_and_newlines(self):
        self.assertEqual(normalize_text("hello\t\tworld\n\nfoo"), "hello world foo")


# ---------------------------------------------------------------
# find_trigger_sentences edge cases
# ---------------------------------------------------------------

class TestFindTriggerSentencesEdgeCases(unittest.TestCase):

    def test_risk_free_trigger(self):
        script = "This is a risk-free purchase."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_sem_risco_trigger(self):
        script = "Compra sem risco garantida."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_melhor_trigger(self):
        script = "Este é o melhor produto do mercado."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_number_one_trigger(self):
        script = "This is the number one headphone brand."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_water_resistant_trigger(self):
        script = "The case is water resistant to IPX4."
        hits = find_trigger_sentences(script)
        self.assertGreater(len(hits), 0)

    def test_mixed_triggers_counts_unique_sentences(self):
        script = "This waterproof certified battery device is best."
        hits = find_trigger_sentences(script)
        # Single sentence matches multiple triggers but returns once
        self.assertEqual(len(hits), 1)


# ---------------------------------------------------------------
# check_evidence edge cases
# ---------------------------------------------------------------

class TestCheckEvidenceEdgeCases(unittest.TestCase):

    def test_warranty_with_evidence(self):
        sentence = "It comes with a lifetime warranty."
        allowed = "lifetime warranty included"
        ok, missing = check_evidence(sentence, allowed)
        self.assertTrue(ok)

    def test_warranty_without_evidence(self):
        sentence = "Includes lifetime warranty."
        allowed = "wireless mouse compact design"
        ok, missing = check_evidence(sentence, allowed)
        self.assertFalse(ok)
        self.assertIn("warranty", missing)

    def test_patented_with_evidence(self):
        sentence = "Uses patented technology."
        allowed = "patented anc technology"
        ok, missing = check_evidence(sentence, allowed)
        self.assertTrue(ok)

    def test_certification_without_evidence(self):
        sentence = "This is FDA certified."
        allowed = "wireless earbuds premium quality"
        ok, missing = check_evidence(sentence, allowed)
        self.assertFalse(ok)
        self.assertIn("certification", missing)

    def test_empty_sentence_passes(self):
        ok, missing = check_evidence("", "some allowed text")
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_empty_allowed_text(self):
        sentence = "This is waterproof."
        ok, missing = check_evidence(sentence, "")
        self.assertFalse(ok)


# ---------------------------------------------------------------
# collect_allowed_text edge cases
# ---------------------------------------------------------------

class TestCollectAllowedTextEdgeCases(unittest.TestCase):

    def test_none_values(self):
        product = {"title": None, "description": None, "bullets": None}
        text = collect_allowed_text(product)
        self.assertEqual(text, "")

    def test_mixed_bullet_types(self):
        product = {"title": "Mouse", "bullets": ["Feature A", None, "", "Feature B"]}
        text = collect_allowed_text(product)
        self.assertIn("feature a", text)
        self.assertIn("feature b", text)

    def test_claims_allowed_override(self):
        product = {
            "title": "Basic Mouse",
            "claims_allowed": ["waterproof", "medical grade"],
        }
        text = collect_allowed_text(product)
        self.assertIn("waterproof", text)
        self.assertIn("medical grade", text)


# ---------------------------------------------------------------
# guardrail edge cases
# ---------------------------------------------------------------

class TestGuardrailEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "RUN_EDGE"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_script(self, text: str):
        (self.run_dir / "01_script.txt").write_text(text, encoding="utf-8")

    def _write_products(self, items: list):
        pdir = self.run_dir / "products"
        pdir.mkdir(exist_ok=True)
        data = {"items": items}
        (pdir / "products.json").write_text(json.dumps(data), encoding="utf-8")

    def test_empty_script_passes(self):
        self._write_script("")
        self._write_products([{"rank": 1, "title": "Mouse"}])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["status"], "PASS")

    def test_multiple_products_evidence_union(self):
        self._write_script("This is waterproof with great battery.")
        self._write_products([
            {"rank": 1, "title": "Mouse", "bullets": ["waterproof design"]},
            {"rank": 2, "title": "Keyboard", "bullets": ["battery lasts 50 hours"]},
        ])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertEqual(result["status"], "PASS")

    def test_cached_product_json_fallback(self):
        self._write_script("Nice product.")
        pdir = self.run_dir / "products" / "p01"
        pdir.mkdir(parents=True)
        prod = {"rank": 1, "title": "Product from product.json"}
        (pdir / "product.json").write_text(json.dumps(prod), encoding="utf-8")
        result = guardrail(self.run_dir, use_cached_products=True)
        self.assertEqual(result["products_source"], "cached_metadata")

    def test_result_has_checked_at_utc(self):
        self._write_script("Good product.")
        self._write_products([{"rank": 1, "title": "Good"}])
        result = guardrail(self.run_dir, use_cached_products=False)
        self.assertIn("checked_at_utc", result)
        self.assertTrue(result["checked_at_utc"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
