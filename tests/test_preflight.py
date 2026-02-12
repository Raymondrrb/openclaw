"""Tests for tools/lib/preflight.py.

Covers: PreflightResult, STAGE_SESSIONS, preflight_check with mocked Playwright.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.preflight import (
    PreflightResult,
    STAGE_SESSIONS,
    LOGIN_CHECKS,
    preflight_check,
)


class TestPreflightResult(unittest.TestCase):
    """Test PreflightResult dataclass."""

    def test_passed(self):
        r = PreflightResult(passed=True)
        self.assertTrue(r.passed)
        self.assertEqual(r.failures, [])

    def test_failed_with_reasons(self):
        r = PreflightResult(passed=False, failures=["Not logged in to Amazon"])
        self.assertFalse(r.passed)
        self.assertEqual(len(r.failures), 1)


class TestStageSessionsConfig(unittest.TestCase):
    """Test STAGE_SESSIONS configuration."""

    def test_research_no_sessions(self):
        self.assertEqual(STAGE_SESSIONS["research"], [])

    def test_verify_needs_amazon(self):
        self.assertIn("amazon", STAGE_SESSIONS["verify"])

    def test_assets_needs_dzine(self):
        self.assertIn("dzine", STAGE_SESSIONS["assets"])

    def test_login_checks_have_required_keys(self):
        for service, check in LOGIN_CHECKS.items():
            self.assertIn("url", check)
            self.assertIn("logged_out_selector", check)
            self.assertIn("name", check)


class TestPreflightCheckResearch(unittest.TestCase):
    """Research stage needs no session checks."""

    def test_research_always_passes(self):
        result = preflight_check("research")
        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])


class TestPreflightCheckBrowserDown(unittest.TestCase):
    """Verify/assets fail fast if browser is not running."""

    @patch("tools.lib.preflight._is_browser_running", return_value=False)
    def test_verify_fails_without_browser(self, mock_browser):
        result = preflight_check("verify")
        self.assertFalse(result.passed)
        self.assertTrue(any("Brave browser" in f for f in result.failures))

    @patch("tools.lib.preflight._is_browser_running", return_value=False)
    def test_assets_fails_without_browser(self, mock_browser):
        result = preflight_check("assets")
        self.assertFalse(result.passed)
        self.assertTrue(any("Brave browser" in f for f in result.failures))


class TestPreflightCheckLoggedOut(unittest.TestCase):
    """Service session logged out detection."""

    def _mock_browser(self):
        """Create a mock browser/context/page chain."""
        mock_pw = MagicMock()
        mock_context = MagicMock()
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        return mock_browser, mock_context, mock_page, mock_pw

    @patch("tools.lib.preflight._is_browser_running", return_value=True)
    @patch("tools.lib.brave_profile.connect_or_launch")
    def test_verify_fails_when_amazon_logged_out(self, mock_col, mock_running):
        browser, context, page, pw = self._mock_browser()
        mock_col.return_value = (browser, context, False, pw)

        # Simulate logged out: selector is visible
        mock_locator = MagicMock()
        mock_locator.first.is_visible.return_value = True
        page.locator.return_value = mock_locator

        result = preflight_check("verify")
        self.assertFalse(result.passed)
        self.assertTrue(any("Amazon" in f for f in result.failures))

    @patch("tools.lib.preflight._is_browser_running", return_value=True)
    @patch("tools.lib.brave_profile.connect_or_launch")
    def test_verify_passes_when_amazon_logged_in(self, mock_col, mock_running):
        browser, context, page, pw = self._mock_browser()
        mock_col.return_value = (browser, context, False, pw)

        # Simulate logged in: selector not visible
        mock_locator = MagicMock()
        mock_locator.first.is_visible.return_value = False
        page.locator.return_value = mock_locator

        result = preflight_check("verify")
        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])

    @patch("tools.lib.preflight._is_browser_running", return_value=True)
    @patch("tools.lib.brave_profile.connect_or_launch")
    def test_assets_fails_when_dzine_logged_out(self, mock_col, mock_running):
        browser, context, page, pw = self._mock_browser()
        mock_col.return_value = (browser, context, False, pw)

        mock_locator = MagicMock()
        mock_locator.first.is_visible.return_value = True
        page.locator.return_value = mock_locator

        result = preflight_check("assets")
        self.assertFalse(result.passed)
        self.assertTrue(any("Dzine" in f for f in result.failures))

    @patch("tools.lib.preflight._is_browser_running", return_value=True)
    @patch("tools.lib.brave_profile.connect_or_launch")
    def test_navigation_error_reported(self, mock_col, mock_running):
        browser, context, page, pw = self._mock_browser()
        mock_col.return_value = (browser, context, False, pw)

        page.goto.side_effect = Exception("Navigation timeout")

        result = preflight_check("verify")
        self.assertFalse(result.passed)
        self.assertTrue(any("Could not check" in f for f in result.failures))


class TestPreflightUnknownStage(unittest.TestCase):
    """Unknown stages should pass (no checks needed)."""

    def test_unknown_stage_passes(self):
        result = preflight_check("unknown_stage")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
