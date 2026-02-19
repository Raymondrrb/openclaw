"""
Comprehensive unit tests for pure functions in tools/top5_video_pipeline.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Allow import from the tools/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from top5_video_pipeline import (
    ANTI_AI_STRUCTURAL_PATTERNS,
    best_for,
    downside_for,
    enforce_word_bounds,
    ensure_disclaimer_line,
    ensure_feature_benefits,
    estimate_elevenlabs_chars,
    extract_hook,
    find_anti_ai_violations,
    find_strong_claims,
    normalize_phrase_match,
    pad_script,
    short_title,
    trim_script_to_max_words,
    word_count,
)
from video_pipeline_lib import Product, normalize_ws


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_product(**kwargs) -> Product:
    """Create a Product with sensible defaults; override any field via kwargs."""
    defaults = {
        "product_title": "Test Widget Pro",
        "asin": "B0TEST1234",
        "current_price_usd": 29.99,
        "rating": 4.5,
        "review_count": 5000,
        "feature_bullets": [
            "Durable construction for everyday use.",
            "Easy to set up in minutes.",
            "Compatible with most desks and surfaces.",
        ],
        "amazon_url": "https://amazon.com/dp/B0TEST1234",
        "affiliate_url": "https://amazon.com/dp/B0TEST1234?tag=rayviews-20",
        "ranking_score": 85.0,
    }
    defaults.update(kwargs)
    return Product(**defaults)


# ---------------------------------------------------------------------------
# Tests — normalize_phrase_match
# ---------------------------------------------------------------------------

class TestNormalizePhraseMatch(unittest.TestCase):

    def test_empty_string(self):
        self.assertEqual(normalize_phrase_match(""), "")

    def test_none_input(self):
        # The function guards with (text or ""), so None should not crash.
        self.assertEqual(normalize_phrase_match(None), "")

    def test_normal_text(self):
        result = normalize_phrase_match("Hello World")
        self.assertEqual(result, "hello world")

    def test_apostrophe_variants(self):
        # Curly apostrophe replaced with straight then stripped.
        result = normalize_phrase_match("it\u2019s worth noting")
        self.assertIn("its worth noting", result)

    def test_straight_apostrophe(self):
        result = normalize_phrase_match("it's worth")
        self.assertIn("its worth", result)

    def test_hyphens_become_spaces(self):
        result = normalize_phrase_match("game-changer")
        self.assertIn("game changer", result)

    def test_special_chars_replaced(self):
        result = normalize_phrase_match("hello! @world #test")
        self.assertEqual(result, "hello world test")

    def test_whitespace_normalized(self):
        result = normalize_phrase_match("  lots   of   spaces  ")
        self.assertEqual(result, "lots of spaces")


# ---------------------------------------------------------------------------
# Tests — find_strong_claims
# ---------------------------------------------------------------------------

class TestFindStrongClaims(unittest.TestCase):

    def test_no_claims(self):
        self.assertEqual(find_strong_claims("This is a normal line."), [])

    def test_one_claim_guaranteed(self):
        result = find_strong_claims("This product is guaranteed to work.")
        self.assertEqual(len(result), 1)
        self.assertIn("guaranteed", result[0].lower())

    def test_one_claim_perfect(self):
        result = find_strong_claims("A perfect solution for everyone.")
        self.assertEqual(len(result), 1)

    def test_one_claim_best(self):
        result = find_strong_claims("This is the best gadget ever.")
        self.assertEqual(len(result), 1)

    def test_one_claim_ultimate(self):
        result = find_strong_claims("The ultimate desk accessory.")
        self.assertEqual(len(result), 1)

    def test_one_claim_always(self):
        result = find_strong_claims("It always delivers on time.")
        self.assertEqual(len(result), 1)

    def test_one_claim_never(self):
        result = find_strong_claims("It never disappoints.")
        self.assertEqual(len(result), 1)

    def test_multiple_claims_on_different_lines(self):
        script = "This is guaranteed.\nA perfect product.\nThe ultimate pick."
        result = find_strong_claims(script)
        self.assertEqual(len(result), 3)

    def test_duplicate_claims_deduped(self):
        script = "This is guaranteed.\nThis is guaranteed.\nThis is guaranteed."
        result = find_strong_claims(script)
        self.assertEqual(len(result), 1)

    def test_long_line_truncation(self):
        long_line = "This is guaranteed " + "a" * 300
        result = find_strong_claims(long_line)
        self.assertEqual(len(result), 1)
        self.assertLessEqual(len(result[0]), 240)

    def test_max_20_results(self):
        lines = [f"Line {i} is guaranteed to work." for i in range(30)]
        script = "\n".join(lines)
        result = find_strong_claims(script)
        self.assertLessEqual(len(result), 20)

    def test_empty_string(self):
        self.assertEqual(find_strong_claims(""), [])

    def test_no1_pattern(self):
        result = find_strong_claims("This is the no.1 pick.")
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# Tests — ANTI_AI_STRUCTURAL_PATTERNS
# ---------------------------------------------------------------------------

class TestAntiAiStructuralPatterns(unittest.TestCase):

    def test_has_three_patterns(self):
        self.assertEqual(len(ANTI_AI_STRUCTURAL_PATTERNS), 3)

    def test_template_opening_match(self):
        names = [name for name, _ in ANTI_AI_STRUCTURAL_PATTERNS]
        self.assertIn("template_opening", names)

    def test_ranking_transition_cliche_match(self):
        names = [name for name, _ in ANTI_AI_STRUCTURAL_PATTERNS]
        self.assertIn("ranking_transition_cliche", names)

    def test_next_up_cliche_match(self):
        names = [name for name, _ in ANTI_AI_STRUCTURAL_PATTERNS]
        self.assertIn("next_up_cliche", names)


# ---------------------------------------------------------------------------
# Tests — find_anti_ai_violations
# ---------------------------------------------------------------------------

class TestFindAntiAiViolations(unittest.TestCase):

    def test_no_violations(self):
        result = find_anti_ai_violations("Completely clean line.", [])
        self.assertEqual(result, [])

    def test_no_violations_with_banned_list(self):
        result = find_anti_ai_violations("A normal everyday sentence.", ["let's dive in"])
        self.assertEqual(result, [])

    def test_phrase_violation(self):
        result = find_anti_ai_violations("Let's dive in to this review!", ["let's dive in"])
        self.assertTrue(len(result) >= 1)
        found = any(v["type"] == "phrase" for v in result)
        self.assertTrue(found, "Expected at least one phrase violation")

    def test_structural_pattern_next_up(self):
        result = find_anti_ai_violations("Next up we have a great product.", [])
        found = any(v["type"] == "pattern" and v["rule"] == "next_up_cliche" for v in result)
        self.assertTrue(found, "Expected next_up_cliche pattern violation")

    def test_structural_pattern_coming_in(self):
        result = find_anti_ai_violations("Coming in at number 3, we have a great pick.", [])
        found = any(v["type"] == "pattern" and v["rule"] == "ranking_transition_cliche" for v in result)
        self.assertTrue(found, "Expected ranking_transition_cliche pattern violation")

    def test_structural_pattern_template_opening(self):
        result = find_anti_ai_violations("This sleek widget boasts amazing features.", [])
        found = any(v["type"] == "pattern" and v["rule"] == "template_opening" for v in result)
        self.assertTrue(found, "Expected template_opening pattern violation")

    def test_combined_phrase_and_pattern(self):
        script = "Let's dive in to discover great products.\nNext up is a powerful device."
        result = find_anti_ai_violations(script, ["let's dive in"])
        types = {v["type"] for v in result}
        self.assertIn("phrase", types)
        self.assertIn("pattern", types)

    def test_violation_dict_keys(self):
        result = find_anti_ai_violations("Next up is awesome.", [])
        self.assertTrue(len(result) >= 1)
        v = result[0]
        self.assertIn("line", v)
        self.assertIn("type", v)
        self.assertIn("rule", v)
        self.assertIn("excerpt", v)

    def test_empty_script(self):
        result = find_anti_ai_violations("", ["let's dive in"])
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Tests — word_count
# ---------------------------------------------------------------------------

class TestWordCount(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(word_count(""), 0)

    def test_one_word(self):
        self.assertEqual(word_count("hello"), 1)

    def test_multiple_words(self):
        self.assertEqual(word_count("hello world foo bar"), 4)

    def test_punctuation_ignored(self):
        self.assertEqual(word_count("hello, world! foo."), 3)

    def test_only_whitespace(self):
        self.assertEqual(word_count("   "), 0)

    def test_mixed_content(self):
        # \b\w+\b splits on apostrophes and hyphens: It|s|a|test|driven|approach|v2
        self.assertEqual(word_count("It's a test-driven approach (v2)."), 7)


# ---------------------------------------------------------------------------
# Tests — short_title
# ---------------------------------------------------------------------------

class TestShortTitle(unittest.TestCase):

    def test_short_title_no_truncation(self):
        result = short_title("Good Widget")
        self.assertEqual(result, "Good Widget")

    def test_long_title_truncated(self):
        title = "One Two Three Four Five Six Seven Eight Nine Ten Eleven"
        result = short_title(title, max_words=8)
        self.assertTrue(result.endswith("..."))
        # Should have max 8 words before "..."
        words_before = result.replace("...", "").strip().split()
        self.assertEqual(len(words_before), 8)

    def test_removes_parenthetical(self):
        result = short_title("Amazing Widget (2024 Edition)")
        self.assertNotIn("2024", result)
        self.assertNotIn("(", result)

    def test_splits_on_dash(self):
        result = short_title("Cool Gadget - Premium Version With Extras")
        self.assertEqual(result, "Cool Gadget")

    def test_splits_on_pipe(self):
        result = short_title("Cool Gadget | Premium Pack")
        self.assertEqual(result, "Cool Gadget")

    def test_empty_string(self):
        result = short_title("")
        self.assertEqual(result, "")

    def test_none_input(self):
        result = short_title(None)
        self.assertEqual(result, "")

    def test_custom_max_words(self):
        title = "One Two Three Four Five"
        result = short_title(title, max_words=3)
        self.assertTrue(result.endswith("..."))


# ---------------------------------------------------------------------------
# Tests — pad_script
# ---------------------------------------------------------------------------

class TestPadScript(unittest.TestCase):

    def _make_ranked(self, n=3):
        return [
            _make_product(product_title=f"Product {i}", asin=f"B000{i}")
            for i in range(1, n + 1)
        ]

    def test_already_meets_min_words(self):
        text = " ".join(["word"] * 200)
        result = pad_script(text, min_words=100, theme="desk", ranked=self._make_ranked())
        self.assertEqual(result, text)

    def test_needs_padding(self):
        text = "A short script."
        ranked = self._make_ranked()
        result = pad_script(text, min_words=100, theme="desk gadgets", ranked=ranked)
        self.assertGreaterEqual(word_count(result), 100)
        # Original text should still be at the start.
        self.assertTrue(result.startswith(text))

    def test_padding_adds_content(self):
        text = "Small text."
        ranked = self._make_ranked()
        result = pad_script(text, min_words=50, theme="desk", ranked=ranked)
        self.assertGreater(len(result), len(text))


# ---------------------------------------------------------------------------
# Tests — trim_script_to_max_words
# ---------------------------------------------------------------------------

class TestTrimScriptToMaxWords(unittest.TestCase):

    def test_under_limit_no_change(self):
        text = "Hello world foo bar."
        result = trim_script_to_max_words(text, max_words=100)
        self.assertEqual(result, text)

    def test_over_limit_trimmed(self):
        text = "one two three four five six seven eight nine ten"
        result = trim_script_to_max_words(text, max_words=5)
        wc = word_count(result)
        self.assertLessEqual(wc, 5)

    def test_preserves_structure(self):
        text = "Hello, world! This is great."
        result = trim_script_to_max_words(text, max_words=2)
        # Should keep "Hello, world" or similar (2 words).
        self.assertLessEqual(word_count(result), 2)

    def test_empty_string(self):
        result = trim_script_to_max_words("", max_words=10)
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Tests — enforce_word_bounds
# ---------------------------------------------------------------------------

class TestEnforceWordBounds(unittest.TestCase):

    def _make_ranked(self, n=3):
        return [
            _make_product(product_title=f"Product {i}", asin=f"B000{i}")
            for i in range(1, n + 1)
        ]

    def test_within_bounds(self):
        text = " ".join(["word"] * 150)
        result = enforce_word_bounds(text, min_words=100, max_words=200, theme="desk", ranked=self._make_ranked())
        self.assertEqual(word_count(result), 150)

    def test_below_min_gets_padded(self):
        text = "A tiny script."
        ranked = self._make_ranked()
        result = enforce_word_bounds(text, min_words=100, max_words=500, theme="desk", ranked=ranked)
        self.assertGreaterEqual(word_count(result), 100)

    def test_above_max_gets_trimmed(self):
        text = " ".join(["word"] * 300)
        ranked = self._make_ranked()
        result = enforce_word_bounds(text, min_words=10, max_words=50, theme="desk", ranked=ranked)
        self.assertLessEqual(word_count(result), 50)


# ---------------------------------------------------------------------------
# Tests — extract_hook
# ---------------------------------------------------------------------------

class TestExtractHook(unittest.TestCase):

    def test_normal_script(self):
        script = "# Title\nThis is a really solid opening line for the hook that should be picked.\nMore text here."
        result = extract_hook(script)
        self.assertIn("opening line", result)

    def test_script_starting_with_headings(self):
        script = "# Heading One\n## Heading Two\nThe actual content starts here and it should be long enough."
        result = extract_hook(script)
        self.assertNotIn("#", result)
        self.assertIn("actual content", result)

    def test_short_lines_only_falls_back(self):
        script = "# Title\nShort.\nTiny."
        result = extract_hook(script)
        # All non-heading lines are < 30 chars, so fallback to full text.
        self.assertTrue(len(result) > 0)

    def test_max_chars_respected(self):
        script = "A" * 500 + " extra words here"
        result = extract_hook(script, max_chars=100)
        self.assertLessEqual(len(result), 100)

    def test_empty_script(self):
        result = extract_hook("")
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Tests — estimate_elevenlabs_chars
# ---------------------------------------------------------------------------

class TestEstimateElevenlabsChars(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(estimate_elevenlabs_chars(""), 0)

    def test_non_empty(self):
        text = "Hello world, this is a test."
        self.assertEqual(estimate_elevenlabs_chars(text), len(text))

    def test_multiline(self):
        text = "Line one.\nLine two.\nLine three."
        self.assertEqual(estimate_elevenlabs_chars(text), len(text))


# ---------------------------------------------------------------------------
# Tests — ensure_disclaimer_line
# ---------------------------------------------------------------------------

class TestEnsureDisclaimerLine(unittest.TestCase):

    DISCLAIMER = "Prices may change\u2014check the link for current price."

    def test_missing_disclaimer_appended(self):
        script = "This is my script content."
        result = ensure_disclaimer_line(script)
        self.assertIn(self.DISCLAIMER, result)

    def test_already_present_not_duplicated(self):
        script = f"Some content.\n\n{self.DISCLAIMER}\n"
        result = ensure_disclaimer_line(script)
        count = result.lower().count(self.DISCLAIMER.lower())
        self.assertEqual(count, 1)

    def test_case_insensitive_detection(self):
        script = "Some content.\n\nprices may change\u2014check the link for current price.\n"
        result = ensure_disclaimer_line(script)
        # Should not add a duplicate.
        occurrences = result.lower().count("prices may change")
        self.assertEqual(occurrences, 1)

    def test_disclaimer_at_end(self):
        script = "Hello world."
        result = ensure_disclaimer_line(script)
        self.assertTrue(result.strip().endswith(self.DISCLAIMER))


# ---------------------------------------------------------------------------
# Tests — ensure_feature_benefits
# ---------------------------------------------------------------------------

class TestEnsureFeatureBenefits(unittest.TestCase):

    def test_clock_product(self):
        product = _make_product(product_title="Digital Alarm Clock LED Display")
        result = ensure_feature_benefits(product)
        self.assertEqual(len(result), 3)
        # Clock-specific benefits mention glanceability.
        self.assertTrue(any("glanceability" in b.lower() for b in result))

    def test_power_strip_product(self):
        product = _make_product(product_title="USB C Power Strip with Surge Protection")
        result = ensure_feature_benefits(product)
        self.assertEqual(len(result), 3)
        self.assertTrue(any("charging" in b.lower() or "charge" in b.lower() for b in result))

    def test_generic_product_with_bullets(self):
        product = _make_product(
            product_title="Fancy Gizmo Deluxe",
            feature_bullets=[
                "Works great with any setup and integrates easily.",
                "Compact design saves desk space nicely.",
                "Premium materials last for many years.",
            ],
        )
        result = ensure_feature_benefits(product)
        self.assertEqual(len(result), 3)

    def test_generic_product_no_bullets_uses_fallback(self):
        product = _make_product(
            product_title="Unknown Rare Gadget XYZ",
            feature_bullets=[],
        )
        result = ensure_feature_benefits(product)
        self.assertEqual(len(result), 3)
        # Fallback mentions "dependable day-to-day value".
        self.assertTrue(any("dependable" in b.lower() for b in result))

    def test_lamp_product(self):
        product = _make_product(product_title="LED Desk Lamp Adjustable Brightness")
        result = ensure_feature_benefits(product)
        self.assertEqual(len(result), 3)
        self.assertTrue(any("brightness" in b.lower() or "eye" in b.lower() for b in result))


# ---------------------------------------------------------------------------
# Tests — downside_for
# ---------------------------------------------------------------------------

class TestDownsideFor(unittest.TestCase):

    def test_clock_product(self):
        product = _make_product(product_title="Digital Alarm Clock")
        result = downside_for(product, median_price=25.0)
        self.assertIn("smartwatch", result.lower())

    def test_cable_product(self):
        product = _make_product(product_title="Cable Tray Organizer")
        result = downside_for(product, median_price=25.0)
        self.assertIn("adhesive", result.lower())

    def test_expensive_product(self):
        product = _make_product(product_title="Super Fancy Gizmo", current_price_usd=100.0)
        result = downside_for(product, median_price=40.0)
        self.assertIn("expensive", result.lower())

    def test_low_review_count(self):
        product = _make_product(product_title="Rare Gizmo", review_count=500, current_price_usd=20.0)
        result = downside_for(product, median_price=30.0)
        self.assertIn("review volume", result.lower())

    def test_low_rating(self):
        product = _make_product(product_title="Average Gizmo", rating=4.2, review_count=5000, current_price_usd=20.0)
        result = downside_for(product, median_price=30.0)
        self.assertIn("satisfaction", result.lower())

    def test_generic_fallback(self):
        # High rating, plenty of reviews, not expensive, no keyword match.
        product = _make_product(
            product_title="Fancy Gizmo",
            rating=4.6,
            review_count=8000,
            current_price_usd=25.0,
        )
        result = downside_for(product, median_price=30.0)
        self.assertIn("niche power users", result.lower())

    def test_power_strip_product(self):
        product = _make_product(product_title="USB C Power Strip")
        result = downside_for(product, median_price=25.0)
        self.assertIn("clamp", result.lower())


# ---------------------------------------------------------------------------
# Tests — best_for
# ---------------------------------------------------------------------------

class TestBestFor(unittest.TestCase):

    def test_power_strip(self):
        product = _make_product(product_title="USB C Power Strip Surge Protector")
        result = best_for("desk accessories", product)
        self.assertIn("multi-device", result.lower())

    def test_cable_organizer(self):
        product = _make_product(product_title="Cable Organizer Tray")
        result = best_for("desk accessories", product)
        self.assertIn("cleaner desk", result.lower())

    def test_clock(self):
        product = _make_product(product_title="Alarm Clock Digital")
        result = best_for("desk accessories", product)
        self.assertIn("glanceable", result.lower())

    def test_generic_product(self):
        product = _make_product(product_title="Unknown Fancy Gizmo")
        result = best_for("desk accessories", product)
        self.assertIn("desk accessories", result.lower())

    def test_dock_product(self):
        product = _make_product(product_title="USB-C Docking Station")
        result = best_for("desk accessories", product)
        self.assertIn("remote workers", result.lower())

    def test_lamp_product(self):
        product = _make_product(product_title="LED Desk Lamp")
        result = best_for("desk accessories", product)
        self.assertIn("eye-friendly", result.lower())

    def test_mouse_product(self):
        product = _make_product(product_title="Ergonomic Mouse Wireless")
        result = best_for("desk accessories", product)
        self.assertIn("comfort", result.lower())


# ---------------------------------------------------------------------------
# Tests — normalize_ws (from video_pipeline_lib)
# ---------------------------------------------------------------------------

class TestNormalizeWs(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(normalize_ws(""), "")

    def test_none(self):
        self.assertEqual(normalize_ws(None), "")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize_ws("  hello   world  "), "hello world")

    def test_newlines_collapsed(self):
        self.assertEqual(normalize_ws("hello\n\n  world"), "hello world")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
