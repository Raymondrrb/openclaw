import unittest
import sys
from pathlib import Path

# Ensure repo-local tools/ is importable (avoid collision with any installed `tools` pkg).
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


class TestChatGPTUIExtractJson(unittest.TestCase):
    def test_extract_plain_json(self):
        from chatgpt_ui import extract_json_object

        obj = extract_json_object('{"ok": true, "n": 1}')
        self.assertEqual(obj["ok"], True)
        self.assertEqual(obj["n"], 1)

    def test_extract_fenced_json(self):
        from chatgpt_ui import extract_json_object

        text = "```json\n{\n  \"ok\": true\n}\n```"
        obj = extract_json_object(text)
        self.assertEqual(obj["ok"], True)

    def test_extract_with_prefix_suffix(self):
        from chatgpt_ui import extract_json_object

        text = "Here you go:\n{\"ok\":true}\nThanks!"
        obj = extract_json_object(text)
        self.assertEqual(obj["ok"], True)

    def test_raises_on_missing_json(self):
        from chatgpt_ui import extract_json_object, ChatGPTUIError

        with self.assertRaises(ChatGPTUIError):
            extract_json_object("no json here")

    def test_repairs_raw_newline_in_string(self):
        from chatgpt_ui import extract_json_object

        # This is intentionally invalid JSON (raw newline inside a string).
        raw = "{\"a\":\"line1\nline2\"}"
        obj = extract_json_object(raw)
        self.assertEqual(obj["a"], "line1\nline2")


if __name__ == "__main__":
    unittest.main()
