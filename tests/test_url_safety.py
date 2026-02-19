#!/usr/bin/env python3
"""Tests for lib/url_safety.py — homograph detection, sanitization, check_items."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure tools/ is on the path so lib/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from lib.url_safety import Finding, check_url, sanitize_text, check_items


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

class TestFinding(unittest.TestCase):
    def test_repr(self):
        f = Finding("HIGH", "test_rule", "detail text")
        self.assertEqual(repr(f), "[HIGH] test_rule: detail text")

    def test_slots(self):
        f = Finding("LOW", "r", "d")
        self.assertEqual(f.severity, "LOW")
        self.assertEqual(f.rule, "r")
        self.assertEqual(f.detail, "d")


# ---------------------------------------------------------------------------
# check_url
# ---------------------------------------------------------------------------

class TestCheckUrl(unittest.TestCase):
    def test_empty_url(self):
        self.assertEqual(check_url(""), [])

    def test_safe_https_url(self):
        findings = check_url("https://www.amazon.com/dp/B08N5WRWNW")
        self.assertEqual(findings, [])

    def test_homograph_cyrillic_a(self):
        # Uses Cyrillic а (U+0430) instead of ASCII a
        url = "https://\u0430mazon.com/phish"
        findings = check_url(url)
        self.assertTrue(any(f.severity == "CRITICAL" and f.rule == "homograph_hostname" for f in findings))

    def test_homograph_cyrillic_o(self):
        url = "https://g\u043e\u043egle.com"
        findings = check_url(url)
        self.assertTrue(any(f.rule == "homograph_hostname" for f in findings))

    def test_non_ascii_hostname_no_confusable(self):
        # Chinese characters — non-ASCII but not in confusable map
        url = "https://\u4e2d\u6587.com/page"
        findings = check_url(url)
        self.assertTrue(any(f.rule == "non_ascii_hostname" for f in findings))

    def test_punycode_domain(self):
        url = "https://xn--n3h.example.com/path"
        findings = check_url(url)
        self.assertTrue(any(f.rule == "punycode_domain" for f in findings))

    def test_credential_in_url(self):
        url = "https://admin:secret@internal.company.com/api"
        findings = check_url(url)
        self.assertTrue(any(f.rule == "credential_in_url" for f in findings))

    def test_insecure_transport(self):
        url = "http://api.example.com/data"
        findings = check_url(url)
        self.assertTrue(any(f.rule == "insecure_transport" for f in findings))

    def test_localhost_http_ok(self):
        url = "http://localhost:8080/health"
        findings = check_url(url)
        self.assertFalse(any(f.rule == "insecure_transport" for f in findings))

    def test_non_standard_port(self):
        url = "https://example.com:9999/api"
        findings = check_url(url)
        self.assertTrue(any(f.rule == "non_standard_port" for f in findings))

    def test_standard_ports_ok(self):
        for port in (80, 443, 8080, 8443):
            url = f"https://example.com:{port}/api"
            findings = check_url(url)
            self.assertFalse(any(f.rule == "non_standard_port" for f in findings), f"Port {port} flagged")

    def test_multiple_findings(self):
        # HTTP + credentials + non-standard port
        url = "http://user:pass@api.example.com:9999/data"
        findings = check_url(url)
        rules = {f.rule for f in findings}
        self.assertIn("insecure_transport", rules)
        self.assertIn("credential_in_url", rules)
        self.assertIn("non_standard_port", rules)


# ---------------------------------------------------------------------------
# sanitize_text
# ---------------------------------------------------------------------------

class TestSanitizeText(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(sanitize_text(""), "")

    def test_none(self):
        self.assertIsNone(sanitize_text(None))

    def test_clean_text_unchanged(self):
        self.assertEqual(sanitize_text("Hello World"), "Hello World")

    def test_removes_zero_width_space(self):
        self.assertEqual(sanitize_text("hello\u200bworld"), "helloworld")

    def test_removes_zero_width_joiner(self):
        self.assertEqual(sanitize_text("test\u200dtext"), "testtext")

    def test_removes_bom(self):
        self.assertEqual(sanitize_text("\ufeffstart"), "start")

    def test_removes_rtl_override(self):
        # Right-to-left override can reverse displayed text
        self.assertEqual(sanitize_text("safe\u202eevil"), "safeevil")

    def test_removes_ansi_escapes(self):
        self.assertEqual(sanitize_text("\x1b[31mred\x1b[0m"), "red")

    def test_removes_ansi_osc(self):
        self.assertEqual(sanitize_text("\x1b]0;title\x07text"), "text")

    def test_combined_invisible_and_ansi(self):
        text = "\ufeff\x1b[1mBold\x1b[0m\u200b"
        self.assertEqual(sanitize_text(text), "Bold")


# ---------------------------------------------------------------------------
# check_items
# ---------------------------------------------------------------------------

class TestCheckItems(unittest.TestCase):
    def test_empty_list(self):
        clean, flagged = check_items([])
        self.assertEqual(clean, [])
        self.assertEqual(flagged, [])

    def test_safe_items_pass_through(self):
        items = [
            {"title": "Good Product", "url": "https://amazon.com/dp/B123"},
            {"title": "Another Item", "url": "https://amazon.com/dp/B456"},
        ]
        clean, flagged = check_items(items)
        self.assertEqual(len(clean), 2)
        self.assertEqual(len(flagged), 0)

    def test_sanitizes_title(self):
        items = [{"title": "Hidden\u200bText", "url": "https://safe.com"}]
        clean, flagged = check_items(items)
        self.assertEqual(clean[0]["title"], "HiddenText")

    def test_sanitizes_description(self):
        items = [{"description": "Has\u200einvisible", "url": "https://safe.com"}]
        clean, flagged = check_items(items)
        self.assertEqual(clean[0]["description"], "Hasinvisible")

    def test_flags_homograph(self):
        items = [{"title": "Fake", "url": "https://\u0430mazon.com/phish"}]
        clean, flagged = check_items(items)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["index"], 0)
        self.assertIn("_safety_flag", clean[0])

    def test_flags_credentials(self):
        items = [{"title": "Internal", "url": "https://user:pass@host.com/api"}]
        clean, flagged = check_items(items)
        self.assertEqual(len(flagged), 1)

    def test_medium_findings_not_flagged(self):
        # HTTP is MEDIUM severity — should not be in flagged report
        items = [{"title": "Normal", "url": "http://example.com/page"}]
        clean, flagged = check_items(items)
        self.assertEqual(len(flagged), 0)
        self.assertNotIn("_safety_flag", clean[0])

    def test_preserves_extra_fields(self):
        items = [{"title": "T", "url": "https://safe.com", "score": 42}]
        clean, _ = check_items(items)
        self.assertEqual(clean[0]["score"], 42)

    def test_url_truncated_in_report(self):
        long_url = "https://\u0430" + "a" * 200 + ".com"
        items = [{"title": "X", "url": long_url}]
        _, flagged = check_items(items)
        self.assertLessEqual(len(flagged[0]["url"]), 120)


if __name__ == "__main__":
    unittest.main()
