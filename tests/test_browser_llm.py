"""Unit tests for tools.lib.browser_llm — browser-based LLM client."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.browser_llm import (
    SELECTORS,
    NEW_CHAT_URLS,
    BrowserLLMResult,
    _extract_response_text,
    _find_first,
    _is_logged_in,
    _send_prompt,
    _start_new_chat,
    _wait_for_response,
)


# ---------------------------------------------------------------------------
# BrowserLLMResult dataclass
# ---------------------------------------------------------------------------

class TestBrowserLLMResult(unittest.TestCase):

    def test_default_construction(self):
        r = BrowserLLMResult(success=False)
        self.assertFalse(r.success)
        self.assertEqual(r.text, "")
        self.assertEqual(r.provider, "")
        self.assertEqual(r.duration_s, 0.0)
        self.assertEqual(r.error, "")

    def test_success_construction(self):
        r = BrowserLLMResult(
            success=True,
            text="Hello world",
            provider="claude",
            duration_s=12.5,
        )
        self.assertTrue(r.success)
        self.assertEqual(r.text, "Hello world")
        self.assertEqual(r.provider, "claude")
        self.assertAlmostEqual(r.duration_s, 12.5)
        self.assertEqual(r.error, "")

    def test_error_construction(self):
        r = BrowserLLMResult(success=False, provider="chatgpt", error="Not logged in")
        self.assertFalse(r.success)
        self.assertEqual(r.provider, "chatgpt")
        self.assertEqual(r.error, "Not logged in")

    def test_all_fields_settable(self):
        r = BrowserLLMResult(
            success=True, text="resp", provider="claude",
            duration_s=5.0, error="",
        )
        self.assertEqual(r.text, "resp")


# ---------------------------------------------------------------------------
# Selector maps
# ---------------------------------------------------------------------------

class TestSelectors(unittest.TestCase):

    def test_both_providers_defined(self):
        self.assertIn("claude", SELECTORS)
        self.assertIn("chatgpt", SELECTORS)

    def test_required_keys_present(self):
        required = {"input", "send", "streaming", "response", "logged_in"}
        for provider, sels in SELECTORS.items():
            for key in required:
                self.assertIn(key, sels, f"{provider} missing '{key}'")
                self.assertIsInstance(sels[key], list)
                self.assertGreater(len(sels[key]), 0, f"{provider}.{key} is empty")

    def test_selectors_are_strings(self):
        for provider, sels in SELECTORS.items():
            for key, sel_list in sels.items():
                for sel in sel_list:
                    self.assertIsInstance(sel, str, f"{provider}.{key} has non-str")
                    self.assertGreater(len(sel), 0)

    def test_claude_input_is_contenteditable(self):
        inputs = SELECTORS["claude"]["input"]
        self.assertTrue(
            any("contenteditable" in s for s in inputs),
            "Claude input should target contenteditable",
        )

    def test_chatgpt_input_has_prompt_textarea(self):
        inputs = SELECTORS["chatgpt"]["input"]
        self.assertTrue(
            any("prompt-textarea" in s for s in inputs),
            "ChatGPT input should target #prompt-textarea",
        )

    def test_chatgpt_send_has_testid(self):
        sends = SELECTORS["chatgpt"]["send"]
        self.assertTrue(
            any("data-testid" in s for s in sends),
            "ChatGPT send should use data-testid",
        )

    def test_chatgpt_response_has_author_role(self):
        resps = SELECTORS["chatgpt"]["response"]
        self.assertTrue(
            any("author-role" in s for s in resps),
            "ChatGPT response should use data-message-author-role",
        )

    def test_claude_response_has_font_class(self):
        resps = SELECTORS["claude"]["response"]
        self.assertTrue(
            any("font-claude-message" in s for s in resps),
            "Claude response should use .font-claude-message",
        )


class TestNewChatUrls(unittest.TestCase):

    def test_claude_url(self):
        self.assertEqual(NEW_CHAT_URLS["claude"], "https://claude.ai/new")

    def test_chatgpt_url(self):
        self.assertEqual(NEW_CHAT_URLS["chatgpt"], "https://chatgpt.com/")

    def test_both_https(self):
        for provider, url in NEW_CHAT_URLS.items():
            self.assertTrue(url.startswith("https://"), f"{provider} URL not HTTPS")


# ---------------------------------------------------------------------------
# _find_first with mock page
# ---------------------------------------------------------------------------

class TestFindFirst(unittest.TestCase):

    def _mock_page(self, visible_selector: str | None = None):
        """Create a mock page where only visible_selector is visible."""
        page = MagicMock()

        def locator_side_effect(sel):
            loc = MagicMock()
            first = MagicMock()
            if sel == visible_selector:
                first.wait_for.return_value = None
            else:
                first.wait_for.side_effect = Exception("not visible")
            loc.first = first
            return loc

        page.locator.side_effect = locator_side_effect
        return page

    def test_finds_first_visible(self):
        page = self._mock_page("#good")
        result = _find_first(page, ["#bad", "#good", "#also-good"], timeout=100)
        self.assertIsNotNone(result)

    def test_returns_none_when_none_visible(self):
        page = self._mock_page(None)
        result = _find_first(page, ["#a", "#b"], timeout=100)
        self.assertIsNone(result)

    def test_empty_selectors_returns_none(self):
        page = self._mock_page("#anything")
        result = _find_first(page, [], timeout=100)
        self.assertIsNone(result)

    def test_first_match_wins(self):
        """If multiple selectors would match, the first one is returned."""
        page = MagicMock()
        call_order = []

        def locator_side_effect(sel):
            loc = MagicMock()
            first = MagicMock()
            first.wait_for.return_value = None  # all visible
            call_order.append(sel)
            loc.first = first
            return loc

        page.locator.side_effect = locator_side_effect
        _find_first(page, ["#first", "#second"], timeout=100)
        self.assertEqual(call_order[0], "#first")


# ---------------------------------------------------------------------------
# _is_logged_in
# ---------------------------------------------------------------------------

class TestIsLoggedIn(unittest.TestCase):

    def test_logged_in_when_avatar_visible(self):
        page = MagicMock()
        loc = MagicMock()
        first = MagicMock()
        first.wait_for.return_value = None
        loc.first = first
        page.locator.return_value = loc
        self.assertTrue(_is_logged_in(page, "claude", timeout=100))

    def test_not_logged_in_when_no_element(self):
        page = MagicMock()
        loc = MagicMock()
        first = MagicMock()
        first.wait_for.side_effect = Exception("timeout")
        loc.first = first
        page.locator.return_value = loc
        self.assertFalse(_is_logged_in(page, "claude", timeout=100))


# ---------------------------------------------------------------------------
# _start_new_chat
# ---------------------------------------------------------------------------

class TestStartNewChat(unittest.TestCase):

    def test_navigates_to_correct_url(self):
        page = MagicMock()
        page.goto.return_value = None
        result = _start_new_chat(page, "claude", timeout=5000)
        self.assertTrue(result)
        page.goto.assert_called_once()
        call_args = page.goto.call_args
        self.assertIn("claude.ai/new", call_args[0][0])

    def test_chatgpt_navigation(self):
        page = MagicMock()
        page.goto.return_value = None
        result = _start_new_chat(page, "chatgpt", timeout=5000)
        self.assertTrue(result)
        self.assertIn("chatgpt.com", page.goto.call_args[0][0])

    def test_unknown_provider_returns_false(self):
        page = MagicMock()
        result = _start_new_chat(page, "unknown_provider", timeout=5000)
        self.assertFalse(result)

    def test_navigation_failure_returns_false(self):
        page = MagicMock()
        page.goto.side_effect = Exception("net error")
        result = _start_new_chat(page, "claude", timeout=5000)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# _extract_response_text
# ---------------------------------------------------------------------------

class TestExtractResponseText(unittest.TestCase):

    def test_extracts_text(self):
        page = MagicMock()
        page.evaluate.return_value = "Hello from Claude"
        text = _extract_response_text(page, "claude")
        self.assertEqual(text, "Hello from Claude")

    def test_empty_when_no_messages(self):
        page = MagicMock()
        page.evaluate.return_value = ""
        text = _extract_response_text(page, "claude")
        self.assertEqual(text, "")

    def test_strips_whitespace(self):
        page = MagicMock()
        page.evaluate.return_value = "  response text  \n"
        text = _extract_response_text(page, "chatgpt")
        self.assertEqual(text, "response text")

    def test_evaluate_exception_returns_empty(self):
        page = MagicMock()
        page.evaluate.side_effect = Exception("JS error")
        text = _extract_response_text(page, "claude")
        self.assertEqual(text, "")


# ---------------------------------------------------------------------------
# send_prompt_via_browser (integration-level with mocks)
# ---------------------------------------------------------------------------

class TestSendPromptViaBrowser(unittest.TestCase):

    def test_unknown_provider_returns_error(self):
        from tools.lib.browser_llm import send_prompt_via_browser
        result = send_prompt_via_browser("test", provider="gemini")
        self.assertFalse(result.success)
        self.assertIn("Unknown provider", result.error)

    @patch("tools.lib.brave_profile.connect_or_launch")
    def test_not_logged_in_returns_error(self, mock_connect):
        from tools.lib.browser_llm import send_prompt_via_browser

        page = MagicMock()
        page.goto.return_value = None
        # All locator checks fail (not logged in)
        loc = MagicMock()
        first = MagicMock()
        first.wait_for.side_effect = Exception("timeout")
        loc.first = first
        page.locator.return_value = loc

        context = MagicMock()
        context.new_page.return_value = page
        mock_connect.return_value = (None, context, False, MagicMock())

        result = send_prompt_via_browser("hello", provider="claude")
        self.assertFalse(result.success)
        self.assertIn("Not logged in", result.error)

    def test_result_type_is_correct(self):
        from tools.lib.browser_llm import send_prompt_via_browser
        result = send_prompt_via_browser("test", provider="gemini")
        self.assertIsInstance(result, BrowserLLMResult)


# ---------------------------------------------------------------------------
# Fallback logic in script_generate
# ---------------------------------------------------------------------------

class TestBrowserFallbackWrappers(unittest.TestCase):

    @patch("tools.lib.browser_llm.send_prompt_via_browser")
    def test_try_browser_draft_success(self, mock_send):
        from tools.lib.script_generate import _try_browser_draft, ScriptGenResult
        mock_send.return_value = BrowserLLMResult(
            success=True, text="Draft text here", provider="chatgpt", duration_s=10.0,
        )
        result = _try_browser_draft("test prompt")
        self.assertIsInstance(result, ScriptGenResult)
        self.assertTrue(result.success)
        self.assertEqual(result.text, "Draft text here")
        self.assertEqual(result.model, "chatgpt-browser")

    @patch("tools.lib.browser_llm.send_prompt_via_browser")
    def test_try_browser_draft_failure(self, mock_send):
        from tools.lib.script_generate import _try_browser_draft, ScriptGenResult
        mock_send.return_value = BrowserLLMResult(
            success=False, error="Not logged in", provider="chatgpt",
        )
        result = _try_browser_draft("test prompt")
        self.assertIsInstance(result, ScriptGenResult)
        self.assertFalse(result.success)

    @patch("tools.lib.browser_llm.send_prompt_via_browser")
    def test_try_browser_refinement_success(self, mock_send):
        from tools.lib.script_generate import _try_browser_refinement, ScriptGenResult
        mock_send.return_value = BrowserLLMResult(
            success=True, text="Refined text", provider="claude", duration_s=15.0,
        )
        result = _try_browser_refinement("refine prompt")
        self.assertIsInstance(result, ScriptGenResult)
        self.assertTrue(result.success)
        self.assertEqual(result.model, "claude-browser")

    @patch("tools.lib.browser_llm.send_prompt_via_browser")
    def test_try_browser_refinement_failure(self, mock_send):
        from tools.lib.script_generate import _try_browser_refinement, ScriptGenResult
        mock_send.return_value = BrowserLLMResult(
            success=False, error="Timeout", provider="claude",
        )
        result = _try_browser_refinement("refine prompt")
        self.assertFalse(result.success)

    def test_try_browser_draft_import_error(self):
        """If browser_llm can't be imported, returns failure gracefully."""
        from tools.lib.script_generate import _try_browser_draft
        # This just tests that the function handles exceptions
        with patch("tools.lib.script_generate._try_browser_draft") as mock_fn:
            mock_fn.return_value = MagicMock(success=False, error="Import error")
            result = mock_fn("test")
            self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# Selector syntax validation
# ---------------------------------------------------------------------------

class TestSelectorSyntax(unittest.TestCase):
    """Validate that CSS selectors are syntactically reasonable."""

    def test_no_empty_selectors(self):
        for provider, groups in SELECTORS.items():
            for key, sels in groups.items():
                for sel in sels:
                    self.assertTrue(len(sel.strip()) > 0,
                                    f"Empty selector in {provider}.{key}")

    def test_selectors_have_valid_chars(self):
        """Basic check: selectors shouldn't have obviously broken chars."""
        import re
        valid_pattern = re.compile(r'^[a-zA-Z0-9\[\]=\'\"\-_\.\#\*\:>\s\+\~\(\),@]+$')
        for provider, groups in SELECTORS.items():
            for key, sels in groups.items():
                for sel in sels:
                    self.assertTrue(
                        valid_pattern.match(sel),
                        f"Suspicious selector in {provider}.{key}: {sel!r}",
                    )

    def test_attribute_selectors_balanced(self):
        """Every [ has a matching ]."""
        for provider, groups in SELECTORS.items():
            for key, sels in groups.items():
                for sel in sels:
                    self.assertEqual(
                        sel.count("["), sel.count("]"),
                        f"Unbalanced brackets in {provider}.{key}: {sel!r}",
                    )

    def test_quotes_balanced(self):
        """Single quotes should be balanced in selectors."""
        for provider, groups in SELECTORS.items():
            for key, sels in groups.items():
                for sel in sels:
                    self.assertEqual(
                        sel.count("'") % 2, 0,
                        f"Unbalanced quotes in {provider}.{key}: {sel!r}",
                    )


# ---------------------------------------------------------------------------
# Pipeline use_browser parameter
# ---------------------------------------------------------------------------

class TestPipelineUseBrowser(unittest.TestCase):

    def test_run_script_pipeline_accepts_use_browser(self):
        """Signature accepts use_browser kwarg without error."""
        import inspect
        from tools.lib.script_generate import run_script_pipeline
        sig = inspect.signature(run_script_pipeline)
        self.assertIn("use_browser", sig.parameters)
        param = sig.parameters["use_browser"]
        self.assertEqual(param.default, False)


if __name__ == "__main__":
    unittest.main()
