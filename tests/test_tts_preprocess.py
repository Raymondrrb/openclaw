"""Tests for tools.lib.tts_preprocess — TTS text normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.tts_preprocess import (
    expand_acronyms,
    normalize_currency,
    normalize_numbers,
    normalize_punctuation,
    normalize_units,
    preprocess,
    simplify_product_codes,
)


class TestNormalizePunctuation(unittest.TestCase):
    def test_em_dash_to_comma(self):
        self.assertIn(",", normalize_punctuation("great sound — amazing bass"))

    def test_en_dash_to_comma(self):
        self.assertIn(",", normalize_punctuation("great sound – amazing bass"))

    def test_repeated_exclamation(self):
        result = normalize_punctuation("Amazing!!!")
        self.assertEqual(result.count("!"), 1)

    def test_repeated_question(self):
        result = normalize_punctuation("Really???")
        self.assertEqual(result.count("?"), 1)

    def test_ellipsis_collapsed(self):
        result = normalize_punctuation("wait for it...")
        self.assertNotIn("..", result.replace(".", ""))  # Only one period

    def test_parentheses_removed(self):
        result = normalize_punctuation("Battery (8 hours) is great")
        self.assertNotIn("(", result)
        self.assertNotIn(")", result)
        self.assertIn("8 hours", result)

    def test_double_spaces_cleaned(self):
        result = normalize_punctuation("hello  world   test")
        self.assertNotIn("  ", result)


class TestNormalizeCurrency(unittest.TestCase):
    def test_price_with_cents(self):
        result = normalize_currency("costs $39.99")
        self.assertIn("thirty-nine", result)
        self.assertIn("ninety-nine", result)
        self.assertNotIn("$", result)

    def test_price_whole_dollars(self):
        result = normalize_currency("only $50")
        self.assertIn("fifty", result)
        self.assertNotIn("$", result)

    def test_price_with_zero_cents(self):
        result = normalize_currency("$100.00")
        self.assertIn("one hundred", result)
        self.assertIn("dollars", result)

    def test_price_299(self):
        result = normalize_currency("at $299.99")
        self.assertIn("two hundred ninety-nine", result)


class TestNormalizeNumbers(unittest.TestCase):
    def test_x_in_1(self):
        result = normalize_numbers("12-in-1 adapter")
        self.assertIn("twelve in one", result)
        self.assertNotIn("12", result)

    def test_comma_thousands(self):
        result = normalize_numbers("10,000 users")
        self.assertIn("ten thousand", result)
        self.assertNotIn("10,000", result)

    def test_large_comma_number(self):
        result = normalize_numbers("costs 1,299 units")
        self.assertIn("one thousand two hundred ninety-nine", result)


class TestNormalizeUnits(unittest.TestCase):
    def test_mah(self):
        result = normalize_units("5000mAh battery")
        self.assertIn("milliamp hours", result)

    def test_mm(self):
        result = normalize_units("10mm driver")
        self.assertIn("millimeters", result)

    def test_hours(self):
        result = normalize_units("8hrs battery")
        self.assertIn("hours", result)


class TestExpandAcronyms(unittest.TestCase):
    def test_usb_c(self):
        result = expand_acronyms("charges via USB-C")
        self.assertIn("U S B C", result)

    def test_anc(self):
        result = expand_acronyms("great ANC performance")
        self.assertIn("A N C", result)

    def test_ldac(self):
        result = expand_acronyms("supports LDAC codec")
        self.assertIn("L D A C", result)

    def test_multiple_acronyms(self):
        result = expand_acronyms("ANC with LDAC and USB-C")
        self.assertIn("A N C", result)
        self.assertIn("L D A C", result)
        self.assertIn("U S B C", result)

    def test_case_sensitive(self):
        # "ai" (lowercase) should NOT be expanded
        result = expand_acronyms("aim for the best")
        self.assertNotIn("A I", result)


class TestSimplifyProductCodes(unittest.TestCase):
    def test_first_mention_kept(self):
        text = "The AB-1234X is great."
        result = simplify_product_codes(text)
        self.assertIn("AB-1234X", result)

    def test_second_mention_simplified(self):
        text = "The AB-1234X is great. The AB-1234X costs three hundred."
        result = simplify_product_codes(text)
        # First kept, second replaced
        self.assertEqual(result.count("AB-1234X"), 1)
        self.assertIn("this model", result)


class TestFullPipeline(unittest.TestCase):
    def test_preprocess_combined(self):
        text = "The AB-1234X costs $299.99 — amazing ANC with 10,000mAh!!!"
        result = preprocess(text)
        # Currency converted
        self.assertNotIn("$", result)
        # Dash converted
        self.assertNotIn("—", result)
        # Repeated ! collapsed
        self.assertEqual(result.count("!"), 1)
        # ANC expanded
        self.assertIn("A N C", result)
        # mAh expanded
        self.assertIn("milliamp hours", result)

    def test_preprocess_preserves_normal_text(self):
        text = "This is a great product with amazing sound quality."
        result = preprocess(text)
        self.assertEqual(text, result)

    def test_preprocess_empty(self):
        self.assertEqual(preprocess(""), "")


if __name__ == "__main__":
    unittest.main()
