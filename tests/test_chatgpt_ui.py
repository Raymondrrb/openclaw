#!/usr/bin/env python3
"""Tests for tools/chatgpt_ui.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure repo-local tools/ is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from chatgpt_ui import ChatGPTUIError, extract_json_object, send_prompt_and_wait_for_assistant


class TestChatGPTUIExtractJson(unittest.TestCase):
    def test_extract_plain_json(self):
        obj = extract_json_object('{"ok": true, "n": 1}')
        self.assertEqual(obj["ok"], True)
        self.assertEqual(obj["n"], 1)

    def test_extract_fenced_json(self):
        text = "```json\n{\n  \"ok\": true\n}\n```"
        obj = extract_json_object(text)
        self.assertEqual(obj["ok"], True)

    def test_extract_with_prefix_suffix(self):
        text = "Here you go:\n{\"ok\":true}\nThanks!"
        obj = extract_json_object(text)
        self.assertEqual(obj["ok"], True)

    def test_raises_on_missing_json(self):
        with self.assertRaises(ChatGPTUIError):
            extract_json_object("no json here")

    def test_repairs_raw_newline_in_string(self):
        # Intentionally invalid JSON (raw newline inside a string).
        raw = "{\"a\":\"line1\nline2\"}"
        obj = extract_json_object(raw)
        self.assertEqual(obj["a"], "line1\nline2")


class TestSendPromptWaitPath(unittest.TestCase):
    def test_prefers_single_wait_call(self):
        calls = []
        state_calls = {"n": 0}

        def fake_counts(*, timeout_ms=30000):
            state_calls["n"] += 1
            if state_calls["n"] == 1:
                return {"url": "https://chatgpt.com/", "assistant": 2, "stop": False}
            return {"url": "https://chatgpt.com/c/abc", "assistant": 3, "stop": False}

        def fake_run_browser_json(args, *, timeout_ms=30000):
            calls.append(args)
            if args[0] in {"press", "wait"}:
                return {}
            raise AssertionError(f"unexpected browser command: {args}")

        with patch("chatgpt_ui.ensure_chatgpt_ready", return_value="tab1"), \
             patch("chatgpt_ui._eval_counts", side_effect=fake_counts), \
             patch("chatgpt_ui._eval_set_prompt", return_value=None), \
             patch("chatgpt_ui._eval_last_assistant_text", return_value="ok"), \
             patch("chatgpt_ui._run_browser_json", side_effect=fake_run_browser_json):
            out = send_prompt_and_wait_for_assistant("hello", timeout_sec=30)

        self.assertEqual(out["assistant_text"], "ok")
        self.assertEqual(out["conversation_url"], "https://chatgpt.com/c/abc")
        first_commands = [c[0] for c in calls]
        self.assertIn("wait", first_commands)

    def test_fallback_poll_when_wait_errors(self):
        state = {
            "idx": 0,
            "items": [
                {"url": "https://chatgpt.com/", "assistant": 1, "stop": False},  # before
                {"url": "https://chatgpt.com/", "assistant": 1, "stop": False},  # poll 1
                {"url": "https://chatgpt.com/c/xyz", "assistant": 2, "stop": False},  # poll 2 done
                {"url": "https://chatgpt.com/c/xyz", "assistant": 2, "stop": False},  # after
            ],
        }

        def fake_counts(*, timeout_ms=30000):
            i = state["idx"]
            state["idx"] += 1
            return state["items"][i]

        def fake_run_browser_json(args, *, timeout_ms=30000):
            if args[0] == "press":
                return {}
            if args[0] == "wait":
                raise ChatGPTUIError("wait unsupported")
            raise AssertionError(f"unexpected browser command: {args}")

        with patch("chatgpt_ui.ensure_chatgpt_ready", return_value="tab1"), \
             patch("chatgpt_ui._eval_counts", side_effect=fake_counts), \
             patch("chatgpt_ui._eval_set_prompt", return_value=None), \
             patch("chatgpt_ui._eval_last_assistant_text", return_value="fallback-ok"), \
             patch("chatgpt_ui._run_browser_json", side_effect=fake_run_browser_json):
            out = send_prompt_and_wait_for_assistant("hello", timeout_sec=10, poll_sec=0)

        self.assertEqual(out["assistant_text"], "fallback-ok")
        self.assertEqual(out["conversation_url"], "https://chatgpt.com/c/xyz")


if __name__ == "__main__":
    unittest.main()
