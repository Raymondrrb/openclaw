"""Tests for tools/lib/retry.py.

Covers: classify_error patterns, with_retry behavior, backoff timing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.retry import ErrorKind, classify_error, with_retry


class TestClassifyError(unittest.TestCase):
    """Test error classification by keyword patterns."""

    def test_timeout_is_transient(self):
        self.assertEqual(classify_error("Connection timed out"), ErrorKind.TRANSIENT)

    def test_timeout_exception_is_transient(self):
        self.assertEqual(classify_error(TimeoutError("read timed out")), ErrorKind.TRANSIENT)

    def test_503_is_transient(self):
        self.assertEqual(classify_error("HTTP 503 Service Unavailable"), ErrorKind.TRANSIENT)

    def test_429_is_transient(self):
        self.assertEqual(classify_error("429 Too Many Requests"), ErrorKind.TRANSIENT)

    def test_rate_limit_is_transient(self):
        self.assertEqual(classify_error("rate limit exceeded"), ErrorKind.TRANSIENT)

    def test_connection_reset_is_transient(self):
        self.assertEqual(classify_error("Connection reset by peer"), ErrorKind.TRANSIENT)

    def test_captcha_is_session(self):
        self.assertEqual(classify_error("CAPTCHA detected on page"), ErrorKind.SESSION)

    def test_validate_captcha_is_session(self):
        self.assertEqual(classify_error("form action validateCaptcha"), ErrorKind.SESSION)

    def test_login_required_is_session(self):
        self.assertEqual(classify_error("Login required to continue"), ErrorKind.SESSION)

    def test_401_is_session(self):
        self.assertEqual(classify_error("HTTP 401 Unauthorized"), ErrorKind.SESSION)

    def test_bot_detection_is_session(self):
        self.assertEqual(classify_error("Bot detection triggered"), ErrorKind.SESSION)

    def test_robot_is_session(self):
        self.assertEqual(classify_error("make sure you're not a robot"), ErrorKind.SESSION)

    def test_404_is_permanent(self):
        self.assertEqual(classify_error("HTTP 404 Not Found"), ErrorKind.PERMANENT)

    def test_out_of_stock_is_permanent(self):
        self.assertEqual(classify_error("Product is out of stock"), ErrorKind.PERMANENT)

    def test_no_longer_available_is_permanent(self):
        self.assertEqual(classify_error("This item is no longer available"), ErrorKind.PERMANENT)

    def test_api_key_is_config(self):
        self.assertEqual(classify_error("API key not set"), ErrorKind.CONFIG)

    def test_missing_credentials_is_config(self):
        self.assertEqual(classify_error("Missing credentials"), ErrorKind.CONFIG)

    def test_unknown_error_defaults_to_transient(self):
        self.assertEqual(classify_error("Something went wrong"), ErrorKind.TRANSIENT)

    def test_config_takes_priority_over_transient(self):
        """Config keywords checked before transient."""
        self.assertEqual(classify_error("API key timeout"), ErrorKind.CONFIG)

    def test_session_takes_priority_over_permanent(self):
        """Session keywords checked before permanent."""
        self.assertEqual(classify_error("CAPTCHA not found on page"), ErrorKind.SESSION)


class TestWithRetry(unittest.TestCase):
    """Test retry behavior and backoff."""

    def test_success_on_first_try(self):
        fn = MagicMock(return_value="ok")
        result = with_retry(fn, max_retries=3)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 1)

    def test_transient_retries_with_backoff(self):
        fn = MagicMock(side_effect=[TimeoutError("timed out"), "ok"])
        mock_sleep = MagicMock()
        result = with_retry(fn, max_retries=3, base_delay_s=2.0, _sleep=mock_sleep)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 2)
        # First retry: 2.0 * 2^0 = 2.0s
        mock_sleep.assert_called_once_with(2.0)

    def test_transient_exponential_backoff(self):
        fn = MagicMock(side_effect=[
            TimeoutError("timed out"),
            TimeoutError("timed out"),
            "ok",
        ])
        mock_sleep = MagicMock()
        result = with_retry(fn, max_retries=3, base_delay_s=1.0, _sleep=mock_sleep)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 3)
        # Backoff: 1.0, 2.0
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertEqual(calls, [1.0, 2.0])

    def test_transient_exhausts_retries(self):
        fn = MagicMock(side_effect=TimeoutError("timed out"))
        mock_sleep = MagicMock()
        with self.assertRaises(TimeoutError):
            with_retry(fn, max_retries=2, base_delay_s=1.0, _sleep=mock_sleep)
        # 1 initial + 2 retries = 3 attempts
        self.assertEqual(fn.call_count, 3)
        # 2 sleeps (before retry 1 and retry 2)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_permanent_raises_immediately(self):
        fn = MagicMock(side_effect=Exception("HTTP 404 Not Found"))
        mock_sleep = MagicMock()
        with self.assertRaises(Exception) as cm:
            with_retry(fn, max_retries=3, _sleep=mock_sleep)
        self.assertIn("404", str(cm.exception))
        self.assertEqual(fn.call_count, 1)
        mock_sleep.assert_not_called()

    def test_config_raises_immediately(self):
        fn = MagicMock(side_effect=Exception("API key not configured"))
        with self.assertRaises(Exception):
            with_retry(fn, max_retries=3)
        self.assertEqual(fn.call_count, 1)

    def test_session_error_calls_callback_once(self):
        callback = MagicMock()
        fn = MagicMock(side_effect=[
            Exception("CAPTCHA detected"),
            "ok",
        ])
        result = with_retry(fn, max_retries=3, on_session_error=callback)
        self.assertEqual(result, "ok")
        callback.assert_called_once()
        self.assertEqual(fn.call_count, 2)

    def test_session_error_without_callback_raises(self):
        fn = MagicMock(side_effect=Exception("Login required"))
        with self.assertRaises(Exception):
            with_retry(fn, max_retries=3, on_session_error=None)
        # No callback: first attempt fails with session, second attempt also fails → raises
        # Actually: attempt 0 fails, no callback, raises on attempt 0
        self.assertEqual(fn.call_count, 1)

    def test_session_error_callback_then_second_fail_raises(self):
        callback = MagicMock()
        fn = MagicMock(side_effect=Exception("CAPTCHA detected"))
        with self.assertRaises(Exception):
            with_retry(fn, max_retries=3, on_session_error=callback)
        callback.assert_called_once()
        # attempt 0: fails → callback → attempt 1: fails → raise (no more session retries)
        self.assertEqual(fn.call_count, 2)

    def test_max_retries_zero(self):
        fn = MagicMock(side_effect=TimeoutError("timed out"))
        with self.assertRaises(TimeoutError):
            with_retry(fn, max_retries=0)
        self.assertEqual(fn.call_count, 1)


if __name__ == "__main__":
    unittest.main()
