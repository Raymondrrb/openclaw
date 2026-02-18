"""Tests for page_reader heading extraction.

No network calls — all pure HTML parsing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.page_reader import extract_headings, html_to_text


class TestHeadingExtractor(unittest.TestCase):
    """Basic h2/h3 extraction."""

    def test_simple_h2(self):
        html = "<h2>Best Overall: Sony WF-1000XM5</h2>"
        result = extract_headings(html)
        self.assertEqual(result, [("h2", "Best Overall: Sony WF-1000XM5")])

    def test_simple_h3(self):
        html = "<h3>Budget Pick: EarFun Free 2S</h3>"
        result = extract_headings(html)
        self.assertEqual(result, [("h3", "Budget Pick: EarFun Free 2S")])

    def test_multiple_headings(self):
        html = (
            "<h2>Our pick: Sony WF-1000XM5</h2>"
            "<p>Some text here</p>"
            "<h2>Also great: Apple AirPods Pro 3</h2>"
            "<p>More text</p>"
            "<h3>Best budget: EarFun Free 2S</h3>"
        )
        result = extract_headings(html)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("h2", "Our pick: Sony WF-1000XM5"))
        self.assertEqual(result[1], ("h2", "Also great: Apple AirPods Pro 3"))
        self.assertEqual(result[2], ("h3", "Best budget: EarFun Free 2S"))

    def test_empty_heading_skipped(self):
        html = "<h2></h2><h2>Real Heading</h2>"
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Real Heading")

    def test_h1_h4_ignored(self):
        html = "<h1>Page Title</h1><h4>Sidebar</h4><h2>Product Pick</h2>"
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Product Pick")

    def test_whitespace_collapsed(self):
        html = "<h2>  Sony   WF-1000XM5  </h2>"
        result = extract_headings(html)
        self.assertEqual(result[0][1], "Sony WF-1000XM5")


class TestHeadingExtractorNested(unittest.TestCase):
    """Headings with inline elements (links, spans, strong)."""

    def test_heading_with_link(self):
        html = '<h2>Our pick: <a href="/sony">Sony WF-1000XM5</a></h2>'
        result = extract_headings(html)
        self.assertEqual(result[0][1], "Our pick: Sony WF-1000XM5")

    def test_heading_with_span(self):
        html = '<h2><span class="label">Best budget:</span> <span>EarFun Free 2S</span></h2>'
        result = extract_headings(html)
        self.assertEqual(result[0][1], "Best budget: EarFun Free 2S")

    def test_heading_with_strong(self):
        html = "<h3><strong>Apple</strong> AirPods Pro 3</h3>"
        result = extract_headings(html)
        self.assertEqual(result[0][1], "Apple AirPods Pro 3")


class TestHeadingExtractorSkipTags(unittest.TestCase):
    """Headings inside nav/footer/header/aside are ignored."""

    def test_nav_heading_skipped(self):
        html = (
            "<nav><h2>Navigation Menu</h2></nav>"
            "<h2>Our pick: Sony WF-1000XM5</h2>"
        )
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Our pick: Sony WF-1000XM5")

    def test_footer_heading_skipped(self):
        html = (
            "<h2>Product Recommendation</h2>"
            "<footer><h3>Footer Heading</h3></footer>"
        )
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Product Recommendation")

    def test_header_heading_skipped(self):
        html = "<header><h2>Site Header</h2></header><h2>Content</h2>"
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Content")

    def test_aside_heading_skipped(self):
        html = "<aside><h3>Related Articles</h3></aside><h2>Main Pick</h2>"
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Main Pick")

    def test_nested_skip_depth(self):
        """Heading inside nested nav > div should still be skipped."""
        html = "<nav><div><h2>Nav Sub-heading</h2></div></nav><h2>Real</h2>"
        result = extract_headings(html)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Real")


class TestExtractHeadingsPublic(unittest.TestCase):
    """Public function extract_headings()."""

    def test_returns_list_of_tuples(self):
        html = "<h2>Hello</h2>"
        result = extract_headings(html)
        self.assertIsInstance(result, list)
        self.assertIsInstance(result[0], tuple)
        self.assertEqual(len(result[0]), 2)

    def test_empty_html(self):
        self.assertEqual(extract_headings(""), [])

    def test_no_headings(self):
        self.assertEqual(extract_headings("<p>Just text</p>"), [])

    def test_malformed_html_no_crash(self):
        result = extract_headings("<h2>Unclosed heading<h3>Another</h3>")
        self.assertIsInstance(result, list)


class TestHtmlToTextRegression(unittest.TestCase):
    """html_to_text must remain unchanged."""

    def test_basic_conversion(self):
        html = "<p>Hello <strong>world</strong></p>"
        text = html_to_text(html)
        self.assertIn("Hello world", text)

    def test_scripts_stripped(self):
        html = "<script>var x=1;</script><p>Content</p>"
        text = html_to_text(html)
        self.assertNotIn("var x", text)
        self.assertIn("Content", text)

    def test_nav_stripped(self):
        html = "<nav>Menu items</nav><p>Content</p>"
        text = html_to_text(html)
        self.assertNotIn("Menu", text)
        self.assertIn("Content", text)

    def test_block_tags_add_newlines(self):
        html = "<p>First</p><p>Second</p>"
        text = html_to_text(html)
        self.assertIn("First", text)
        self.assertIn("Second", text)
        # They should be on separate lines
        lines = [l for l in text.splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 2)


class TestFetchPageData(unittest.TestCase):
    """fetch_page_data returns 3-tuple."""

    def test_signature_returns_three(self):
        """fetch_page_data returns (text, method, raw_html) — test with failed fetch."""
        from unittest.mock import patch
        from tools.lib.page_reader import fetch_page_data

        # Patch the lazy import inside fetch_page_data so markdown path raises ImportError
        with patch.dict("sys.modules", {"tools.lib.markdown_fetch": None}):
            with patch("tools.lib.page_reader._http_fetch", return_value=None):
                with patch("tools.lib.page_reader._browser_fetch", return_value=None):
                    text, method, raw_html = fetch_page_data("https://example.com")
                    self.assertEqual(text, "")
                    self.assertEqual(method, "failed")
                    self.assertIsNone(raw_html)

    def test_http_path_returns_html(self):
        """When HTTP succeeds, raw_html is returned."""
        from unittest.mock import patch
        from tools.lib.page_reader import fetch_page_data

        fake_html = "<html><body><p>Hello world this is enough content for the threshold</p>" + "x" * 500 + "</body></html>"
        with patch.dict("sys.modules", {"tools.lib.markdown_fetch": None}):
            with patch("tools.lib.page_reader._http_fetch", return_value=fake_html):
                text, method, raw_html = fetch_page_data("https://example.com")
                self.assertEqual(method, "http")
                self.assertEqual(raw_html, fake_html)
                self.assertIn("Hello world", text)


if __name__ == "__main__":
    unittest.main()
