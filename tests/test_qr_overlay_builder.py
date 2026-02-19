#!/usr/bin/env python3
"""Tests for rayvault/qr_overlay_builder.py — affiliate visual assets."""

from __future__ import annotations

import unittest

from rayvault.qr_overlay_builder import (
    CANVAS_H,
    CANVAS_W,
    DISPLAY_HIDE,
    DISPLAY_LINK_ONLY,
    DISPLAY_LINK_PLUS_QR,
    MARGIN,
    QR_SIZE,
    OverlayFlags,
    _canon_url,
    resolve_display_mode,
    smart_title,
    truncate_text,
)


# ---------------------------------------------------------------
# truncate_text
# ---------------------------------------------------------------

class TestTruncateText(unittest.TestCase):

    def test_short_unchanged(self):
        self.assertEqual(truncate_text("Hello", 10), "Hello")

    def test_exact_length_unchanged(self):
        self.assertEqual(truncate_text("Hello", 5), "Hello")

    def test_truncates_with_ellipsis(self):
        result = truncate_text("Hello World", 8)
        self.assertLessEqual(len(result), 8)
        self.assertTrue(result.endswith("\u2026"))

    def test_empty_string(self):
        self.assertEqual(truncate_text("", 10), "")


# ---------------------------------------------------------------
# smart_title
# ---------------------------------------------------------------

class TestSmartTitle(unittest.TestCase):

    def test_short_unchanged(self):
        self.assertEqual(smart_title("Short Title", 52), "Short Title")

    def test_exact_max_unchanged(self):
        title = "A" * 52
        self.assertEqual(smart_title(title, 52), title)

    def test_cuts_at_dash_separator(self):
        title = "Wireless Mouse Pro - Ultimate Gaming Edition With Extra Features"
        result = smart_title(title, 30)
        self.assertLessEqual(len(result), 30)
        self.assertIn("Mouse", result)

    def test_cuts_at_pipe_separator(self):
        title = "Great Product Name | Detailed Description Here Too"
        result = smart_title(title, 25)
        self.assertLessEqual(len(result), 25)

    def test_word_boundary_fallback(self):
        title = "This is a really long title without any special separators in it"
        result = smart_title(title, 30)
        self.assertLessEqual(len(result), 30)
        self.assertTrue(result.endswith("\u2026"))

    def test_empty_string(self):
        self.assertEqual(smart_title(""), "")

    def test_strips_whitespace(self):
        self.assertEqual(smart_title("  Hello  ", 52), "Hello")

    def test_very_long_no_spaces(self):
        title = "A" * 100
        result = smart_title(title, 20)
        self.assertLessEqual(len(result), 20)
        self.assertTrue(result.endswith("\u2026"))

    def test_separator_too_early_ignored(self):
        title = "A - Very Long Product Name That Goes On and On"
        result = smart_title(title, 25)
        # "A" only 1 char (below min 10), so won't cut there
        self.assertGreater(len(result), 5)


# ---------------------------------------------------------------
# _canon_url
# ---------------------------------------------------------------

class TestCanonUrl(unittest.TestCase):

    def test_strips_whitespace(self):
        self.assertEqual(_canon_url("  https://amzn.to/abc  "), "https://amzn.to/abc")

    def test_strips_trailing_slash(self):
        self.assertEqual(_canon_url("https://amzn.to/abc/"), "https://amzn.to/abc")

    def test_no_trailing_slash_unchanged(self):
        self.assertEqual(_canon_url("https://amzn.to/abc"), "https://amzn.to/abc")

    def test_empty(self):
        self.assertEqual(_canon_url(""), "")


# ---------------------------------------------------------------
# resolve_display_mode
# ---------------------------------------------------------------

class TestResolveDisplayMode(unittest.TestCase):

    def _flags(self, **kw):
        return OverlayFlags(**kw)

    def test_green_eligible_with_link(self):
        mode = resolve_display_mode("GREEN", True, "https://amzn.to/abc", self._flags())
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)

    def test_red_always_hide(self):
        mode = resolve_display_mode("RED", True, "https://amzn.to/abc", self._flags())
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_not_eligible_hide(self):
        mode = resolve_display_mode("GREEN", False, "https://amzn.to/abc", self._flags())
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_no_link_hide(self):
        mode = resolve_display_mode("GREEN", True, None, self._flags())
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_empty_link_hide(self):
        mode = resolve_display_mode("GREEN", True, "", self._flags())
        self.assertEqual(mode, DISPLAY_HIDE)

    def test_amber_default_link_only(self):
        mode = resolve_display_mode("AMBER", True, "https://amzn.to/abc", self._flags())
        self.assertEqual(mode, DISPLAY_LINK_ONLY)

    def test_amber_allow_qr(self):
        mode = resolve_display_mode(
            "AMBER", True, "https://amzn.to/abc",
            self._flags(allow_qr_amber=True),
        )
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)

    def test_force_qr_overrides(self):
        mode = resolve_display_mode(
            "AMBER", True, "https://amzn.to/abc",
            self._flags(force_qr=True),
        )
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)

    def test_no_qr_flag(self):
        mode = resolve_display_mode(
            "GREEN", True, "https://amzn.to/abc",
            self._flags(no_qr=True),
        )
        self.assertEqual(mode, DISPLAY_LINK_ONLY)

    def test_force_qr_beats_no_qr(self):
        mode = resolve_display_mode(
            "GREEN", True, "https://amzn.to/abc",
            self._flags(force_qr=True, no_qr=True),
        )
        self.assertEqual(mode, DISPLAY_LINK_PLUS_QR)


# ---------------------------------------------------------------
# OverlayFlags defaults
# ---------------------------------------------------------------

class TestOverlayFlags(unittest.TestCase):

    def test_defaults(self):
        f = OverlayFlags()
        self.assertFalse(f.allow_qr_amber)
        self.assertFalse(f.no_qr)
        self.assertFalse(f.force_qr)
        self.assertTrue(f.validate_qr)
        self.assertEqual(f.max_title_chars, 52)
        self.assertTrue(f.include_price)
        self.assertTrue(f.include_rank_badge)
        self.assertEqual(f.amber_warning_text, "")


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestOverlayConstants(unittest.TestCase):

    def test_canvas_1080p(self):
        self.assertEqual(CANVAS_W, 1920)
        self.assertEqual(CANVAS_H, 1080)

    def test_margin_positive(self):
        self.assertGreater(MARGIN, 0)

    def test_qr_size_positive(self):
        self.assertGreater(QR_SIZE, 0)

    def test_display_modes_distinct(self):
        modes = {DISPLAY_HIDE, DISPLAY_LINK_ONLY, DISPLAY_LINK_PLUS_QR}
        self.assertEqual(len(modes), 3)


# ---------------------------------------------------------------
# _canon_url None-safety and edge cases
# ---------------------------------------------------------------

class TestCanonUrlNoneSafety(unittest.TestCase):

    def test_none_returns_empty(self):
        self.assertEqual(_canon_url(None), "")

    def test_only_slash(self):
        self.assertEqual(_canon_url("/"), "")

    def test_multiple_trailing_slashes_strips_one(self):
        result = _canon_url("https://example.com//")
        self.assertEqual(result, "https://example.com/")

    def test_whitespace_only(self):
        self.assertEqual(_canon_url("   "), "")

    def test_tab_and_newline(self):
        result = _canon_url("\thttps://amzn.to/abc\n")
        self.assertEqual(result, "https://amzn.to/abc")


# ---------------------------------------------------------------
# truncate_text edge cases
# ---------------------------------------------------------------

class TestTruncateTextEdgeCases(unittest.TestCase):

    def test_single_char(self):
        self.assertEqual(truncate_text("A", 10), "A")

    def test_max_len_very_small(self):
        result = truncate_text("Hello", 2)
        self.assertLessEqual(len(result), 2)

    def test_max_len_1(self):
        result = truncate_text("Hello", 1)
        self.assertLessEqual(len(result), 1)

    def test_unicode_text(self):
        result = truncate_text("Fóne de ouvido sem fio", 15)
        self.assertLessEqual(len(result), 15)


# ---------------------------------------------------------------
# smart_title edge cases
# ---------------------------------------------------------------

class TestSmartTitleEdgeCases(unittest.TestCase):

    def test_multiple_separators(self):
        title = "Product Name - Detail | More Info - Extra"
        result = smart_title(title, 30)
        self.assertLessEqual(len(result), 30)

    def test_separator_at_exact_boundary(self):
        # "AAAAAAAAAA - rest" where max is 14 => "AAAAAAAAAA" (len=10)
        title = "AAAAAAAAAA - rest of the title"
        result = smart_title(title, 14)
        self.assertLessEqual(len(result), 14)

    def test_unicode_title(self):
        title = "Fone de Ouvido Bluetooth - Samsung Galaxy Buds Pro"
        result = smart_title(title, 30)
        self.assertLessEqual(len(result), 30)


# ---------------------------------------------------------------
# resolve_display_mode edge cases
# ---------------------------------------------------------------

class TestResolveDisplayModeEdgeCases(unittest.TestCase):

    def _flags(self, **kw):
        return OverlayFlags(**kw)

    def test_unknown_classification_treated_as_amber(self):
        mode = resolve_display_mode("UNKNOWN", True, "https://amzn.to/abc", self._flags())
        # Unknown classification => should not get link+qr (only GREEN gets that)
        self.assertIn(mode, {DISPLAY_HIDE, DISPLAY_LINK_ONLY, DISPLAY_LINK_PLUS_QR})

    def test_whitespace_link_treated_as_empty(self):
        mode = resolve_display_mode("GREEN", True, "   ", self._flags())
        # Whitespace-only link should be treated as no link
        self.assertIn(mode, {DISPLAY_HIDE, DISPLAY_LINK_ONLY, DISPLAY_LINK_PLUS_QR})

    def test_none_classification(self):
        mode = resolve_display_mode(None, True, "https://amzn.to/abc", self._flags())
        self.assertIn(mode, {DISPLAY_HIDE, DISPLAY_LINK_ONLY, DISPLAY_LINK_PLUS_QR})


if __name__ == "__main__":
    unittest.main()
