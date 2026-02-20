"""Tests for tools/lib/script_generate.py.

Covers: generate_draft, generate_refinement, extract_script_body,
        extract_metadata, run_script_pipeline.
No real API calls — mocks urllib.request.urlopen.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.script_generate import (
    _match_marker,
    extract_metadata,
    extract_script_body,
    normalize_section_markers,
    split_script_outputs,
    generate_draft,
    generate_refinement,
    run_script_pipeline,
    ScriptGenResult,
    ScriptPipelineResult,
)
from tools.lib.tts_preprocess import strip_section_markers


# ---------------------------------------------------------------------------
# Mock HTTP responses
# ---------------------------------------------------------------------------

MOCK_OPENAI_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": (
                    "[HOOK]\n"
                    "You spent hours scrolling Amazon reviews. Half of them are fake.\n"
                    "The other half? Contradictory. So how do you actually find\n"
                    "the best wireless earbuds without wasting money?\n\n"
                    "[AVATAR_INTRO]\n"
                    "I'm Ray, and I test products so you don't have to.\n\n"
                    "[PRODUCT_5]\n"
                    "Starting at number five, the JBL Tune 230NC.\n"
                    "According to PCMag, these deliver surprisingly punchy bass\n"
                    "for under fifty dollars. The active noise cancellation\n"
                    "blocks about 20 decibels — decent for the price.\n"
                    "However, the call quality is mediocre in windy conditions.\n\n"
                    "[PRODUCT_4]\n"
                    "At number four, Samsung Galaxy Buds3 Pro.\n"
                    "RTINGS measured these at 32 decibels of noise isolation.\n"
                    "The fit is comfortable for long listening sessions.\n"
                    "That said, the touch controls can be finicky.\n\n"
                    "[PRODUCT_3]\n"
                    "Number three brings us the AirPods Pro 2.\n"
                    "Wirecutter calls these the best overall for iPhone users.\n"
                    "Spatial audio actually sounds good here.\n"
                    "Keep in mind, Android users lose some features.\n\n"
                    "[RETENTION_RESET]\n"
                    "Quick question — have you ever returned earbuds\n"
                    "because they just didn't fit right?\n\n"
                    "[PRODUCT_2]\n"
                    "Number two, Sony WF-1000XM5.\n"
                    "RTINGS rates these as best noise cancelling earbuds overall.\n"
                    "The sound quality is reference-grade.\n"
                    "One drawback: the case is larger than competitors.\n\n"
                    "[PRODUCT_1]\n"
                    "And the number one pick: Bose QuietComfort Ultra Earbuds.\n"
                    "Wirecutter named these a top pick for noise cancellation.\n"
                    "The immersive audio is next level.\n"
                    "The trade-off is battery life at 6 hours vs Sony's 8.\n\n"
                    "[CONCLUSION]\n"
                    "Links to all five are in the description below.\n"
                    "Just a heads up — those are affiliate links, which means\n"
                    "I may earn a small commission at no extra cost to you.\n"
                ),
            }
        }
    ],
    "model": "gpt-4o-2025-01-01",
    "usage": {"prompt_tokens": 1500, "completion_tokens": 800},
}

MOCK_ANTHROPIC_RESPONSE = {
    "content": [
        {
            "type": "text",
            "text": (
                "[HOOK]\n"
                "You spent hours reading Amazon reviews. Half are fake.\n"
                "The rest contradict each other. Here's what trusted reviewers actually say.\n\n"
                "[AVATAR_INTRO]\n"
                "I'm Ray, and I research products so you don't have to.\n\n"
                "[PRODUCT_5]\n"
                "Starting at five, the JBL Tune 230NC.\n"
                "PCMag highlights the punchy bass and active noise cancellation\n"
                "that blocks around 20 decibels.\n"
                "However, call quality drops in windy conditions.\n\n"
                "[PRODUCT_4]\n"
                "Number four, Samsung Galaxy Buds3 Pro.\n"
                "RTINGS measured 32 decibels of noise isolation.\n"
                "Comfortable fit for all-day use.\n"
                "That said, the touch controls need practice.\n\n"
                "[PRODUCT_3]\n"
                "The AirPods Pro 2 at number three.\n"
                "Wirecutter's top pick for iPhone users.\n"
                "Keep in mind, some features are iOS-only.\n\n"
                "[RETENTION_RESET]\n"
                "Have you ever returned earbuds because they didn't fit?\n\n"
                "[PRODUCT_2]\n"
                "Number two, Sony WF-1000XM5.\n"
                "RTINGS rates them best for noise cancellation overall.\n"
                "One drawback: the charging case is bulkier than competitors.\n\n"
                "[PRODUCT_1]\n"
                "Number one: Bose QuietComfort Ultra Earbuds.\n"
                "Wirecutter's top pick for noise cancellation.\n"
                "The trade-off is 6 hours of battery vs Sony's 8.\n\n"
                "[CONCLUSION]\n"
                "Links to all five products are in the description.\n"
                "Those are affiliate links — I may earn a small commission\n"
                "at no extra cost to you.\n\n"
                "---\n\n"
                "Avatar intro script:\n"
                '"I\'m Ray, and I research products so you don\'t have to."\n\n'
                "Short YouTube description:\n"
                "The 5 best wireless earbuds based on expert reviews from Wirecutter, "
                "RTINGS, and PCMag. Links are affiliate links.\n\n"
                "Thumbnail headline options:\n"
                "1. Best Earbuds 2025\n"
                "2. Top 5 Earbuds\n"
                "3. Expert Picks\n"
            ),
        }
    ],
    "model": "claude-sonnet-4-5-20250929",
    "usage": {"input_tokens": 2000, "output_tokens": 900},
}


BROWSER_LLM_SCRIPT = (
    "You spent hours scrolling Amazon reviews. Half of them are fake.\n"
    "The other half? Contradictory.\n\n"
    "#5 – Narwal Freo Pro (Best Alternative)\n"
    "Starting at number five, the Narwal Freo Pro.\n"
    "According to RTINGS, this robot vacuum delivers excellent mopping.\n"
    "However, the dustbin is on the smaller side.\n\n"
    "#4 – Roborock S8 MaxV Ultra\n"
    "At number four, the Roborock S8 MaxV Ultra.\n"
    "Wirecutter calls this a top pick for obstacle avoidance.\n"
    "That said, the price is steep.\n\n"
    "#3 – Ecovacs Deebot X2 Omni\n"
    "Number three, the Ecovacs Deebot X2 Omni.\n"
    "Its square design cleans corners better than round competitors.\n"
    "Keep in mind, the app can be confusing.\n\n"
    "Quick Reset\n"
    "Have you ever had a robot vacuum get stuck under your couch?\n\n"
    "#2 – iRobot Roomba j9+\n"
    "Number two, the Roomba j9+.\n"
    "Consumer Reports rates this highly for carpet cleaning.\n"
    "One drawback: no mopping capability.\n\n"
    "#1 – Roborock Q Revo MaxV\n"
    "And the number one pick: Roborock Q Revo MaxV.\n"
    "Best overall value with both vacuuming and mopping.\n"
    "The trade-off is it's louder than competitors.\n\n"
    "Conclusion + CTA\n"
    "Links to all five are in the description below.\n"
    "Those are affiliate links — I may earn a small commission\n"
    "at no extra cost to you.\n"
)

BROWSER_LLM_METADATA = (
    BROWSER_LLM_SCRIPT + "\n"
    "---\n\n"
    "Avatar Intro Script\n"
    "(Max 320 characters, friendly and direct)\n"
    "I tested and compared five of the best robot vacuums so you don't have to.\n\n"
    "Short YouTube description:\n"
    "The 5 best robot vacuums based on expert reviews from Wirecutter, "
    "RTINGS, and Consumer Reports. Links are affiliate links.\n\n"
    "Thumbnail Headline Options\n"
    "DON'T BUY WRONG\n"
    "ONLY ONE WORTH IT\n"
    "BEST ROBOT VACUUMS\n"
)


def _mock_urlopen(response_dict):
    """Create a mock for urllib.request.urlopen that returns response_dict."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_dict).encode("utf-8")
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNormalizeSectionMarkers(unittest.TestCase):
    """Test normalize_section_markers() conversion logic."""

    def test_informal_to_formal(self):
        result = normalize_section_markers(BROWSER_LLM_SCRIPT)
        self.assertIn("[HOOK]", result)
        self.assertIn("[PRODUCT_5]", result)
        self.assertIn("[PRODUCT_4]", result)
        self.assertIn("[PRODUCT_3]", result)
        self.assertIn("[PRODUCT_2]", result)
        self.assertIn("[PRODUCT_1]", result)
        self.assertIn("[RETENTION_RESET]", result)
        self.assertIn("[CONCLUSION]", result)

    def test_informal_no_raw_markers_remain(self):
        result = normalize_section_markers(BROWSER_LLM_SCRIPT)
        self.assertNotIn("#5 –", result)
        self.assertNotIn("#4 –", result)
        self.assertNotIn("Quick Reset", result)
        self.assertNotIn("Conclusion + CTA", result)

    def test_formal_markers_noop(self):
        """Already-formal markers should pass through unchanged."""
        formal = (
            "[HOOK]\nHook text.\n\n"
            "[PRODUCT_5]\nProduct five.\n\n"
            "[CONCLUSION]\nConclusion.\n"
        )
        result = normalize_section_markers(formal)
        self.assertEqual(result, formal)

    def test_hook_inserted_when_content_before_product(self):
        text = "Some hook content here.\n\n#5 – Product Name\nDetails.\n"
        result = normalize_section_markers(text)
        lines = result.splitlines()
        self.assertEqual(lines[0], "[HOOK]")

    def test_no_hook_when_no_content_before_product(self):
        text = "#5 – Product Name\nDetails.\n"
        result = normalize_section_markers(text)
        lines = result.splitlines()
        self.assertEqual(lines[0], "[PRODUCT_5]")

    def test_mid_video_reset(self):
        text = "#5 – Prod\nDetails.\n\nMid-Video Reset\nSomething.\n"
        result = normalize_section_markers(text)
        self.assertIn("[RETENTION_RESET]", result)

    def test_avatar_intro_inline(self):
        text = "[HOOK]\nHook.\n\nAvatar Intro\nI'm Ray.\n"
        # Has formal [HOOK] so won't normalize — let's test pure informal
        text2 = "Hook content.\n\n#5 – Prod\nDetails.\n\nAvatar Intro\nI'm Ray.\n"
        result = normalize_section_markers(text2)
        self.assertIn("[AVATAR_INTRO]", result)


class TestExtractScriptBody(unittest.TestCase):
    """Test extract_script_body() parsing logic."""

    def test_extracts_from_markers(self):
        text = (
            "Sure, here's the script:\n\n"
            "[HOOK]\n"
            "Some hook text.\n\n"
            "[CONCLUSION]\n"
            "Some conclusion.\n\n"
            "I hope this helps!"
        )
        result = extract_script_body(text)
        self.assertTrue(result.startswith("[HOOK]"))
        self.assertIn("[CONCLUSION]", result)
        self.assertIn("Some conclusion.", result)
        self.assertNotIn("I hope this helps", result)

    def test_strips_markdown_fences(self):
        text = "```markdown\n[HOOK]\nHello\n[CONCLUSION]\nBye\n```"
        result = extract_script_body(text)
        self.assertIn("[HOOK]", result)
        self.assertNotIn("```", result)

    def test_returns_full_text_when_no_markers(self):
        text = "Just a plain script without any section markers."
        result = extract_script_body(text)
        self.assertEqual(result, text)


class TestExtractMetadata(unittest.TestCase):
    """Test extract_metadata() from refinement output."""

    def test_extracts_avatar_intro(self):
        text = (
            "[HOOK]\nSome hook.\n[CONCLUSION]\nBye.\n\n"
            "Avatar intro script:\n"
            '"I\'m Ray, and I test products so you don\'t have to."\n'
        )
        meta = extract_metadata(text)
        self.assertIn("Ray", meta["avatar_intro"])

    def test_extracts_thumbnail_headlines(self):
        text = (
            "Thumbnail headline options:\n"
            "1. Best Earbuds 2025\n"
            "2. Top 5 Picks\n"
            "3. Expert Rated\n"
        )
        meta = extract_metadata(text)
        self.assertEqual(len(meta["thumbnail_headlines"]), 3)
        self.assertEqual(meta["thumbnail_headlines"][0], "Best Earbuds 2025")

    def test_extracts_youtube_description(self):
        text = (
            "Short YouTube description:\n"
            "The best wireless earbuds based on expert reviews.\n"
            "Links are affiliate links.\n"
        )
        meta = extract_metadata(text)
        self.assertIn("wireless earbuds", meta["youtube_description"])

    def test_handles_empty_text(self):
        meta = extract_metadata("")
        self.assertEqual(meta["avatar_intro"], "")
        self.assertEqual(meta["thumbnail_headlines"], [])

    def test_browser_avatar_intro_script(self):
        """Browser Claude uses 'Avatar Intro Script' header with parenthetical instructions."""
        meta = extract_metadata(BROWSER_LLM_METADATA)
        self.assertIn("robot vacuum", meta["avatar_intro"])

    def test_browser_thumbnail_plain_lines(self):
        """Browser Claude outputs thumbnail headlines without numbering."""
        meta = extract_metadata(BROWSER_LLM_METADATA)
        self.assertEqual(len(meta["thumbnail_headlines"]), 3)
        self.assertIn("DON'T BUY WRONG", meta["thumbnail_headlines"])
        self.assertIn("ONLY ONE WORTH IT", meta["thumbnail_headlines"])
        self.assertIn("BEST ROBOT VACUUMS", meta["thumbnail_headlines"])

    def test_browser_description_extracted(self):
        meta = extract_metadata(BROWSER_LLM_METADATA)
        self.assertIn("robot vacuum", meta["youtube_description"])

    def test_parenthetical_meta_instruction_skipped(self):
        """Lines like '(Max 320 characters, ...)' should not become avatar intro."""
        meta = extract_metadata(BROWSER_LLM_METADATA)
        self.assertNotIn("320", meta["avatar_intro"])


class TestExtractScriptBodyBrowser(unittest.TestCase):
    """Test extract_script_body() with informal browser LLM output."""

    def test_browser_script_has_formal_markers(self):
        result = extract_script_body(BROWSER_LLM_SCRIPT)
        self.assertIn("[HOOK]", result)
        self.assertIn("[PRODUCT_5]", result)
        self.assertIn("[PRODUCT_1]", result)
        self.assertIn("[RETENTION_RESET]", result)
        self.assertIn("[CONCLUSION]", result)

    def test_browser_script_word_count_positive(self):
        result = extract_script_body(BROWSER_LLM_SCRIPT)
        word_count = len(result.split())
        self.assertGreater(word_count, 50)

    def test_browser_script_section_count(self):
        """Should produce all 8 sections (hook + 5 products + reset + conclusion)."""
        result = extract_script_body(BROWSER_LLM_SCRIPT)
        markers = [
            "[HOOK]", "[PRODUCT_5]", "[PRODUCT_4]", "[PRODUCT_3]",
            "[RETENTION_RESET]", "[PRODUCT_2]", "[PRODUCT_1]", "[CONCLUSION]",
        ]
        for m in markers:
            self.assertIn(m, result, f"Missing marker: {m}")


class TestMatchMarker(unittest.TestCase):
    """Test _match_marker() with various line formats."""

    def test_exact_marker(self):
        self.assertEqual(_match_marker("[PRODUCT_5]"), "[PRODUCT_5]")

    def test_marker_with_product_name(self):
        self.assertEqual(_match_marker("[PRODUCT_5] — Narwal Freo Pro"), "[PRODUCT_5]")

    def test_marker_with_dash(self):
        self.assertEqual(_match_marker("[PRODUCT_3] - Dreame D20 Plus"), "[PRODUCT_3]")

    def test_marker_with_whitespace(self):
        self.assertEqual(_match_marker("  [HOOK]  "), "[HOOK]")

    def test_non_marker_returns_none(self):
        self.assertIsNone(_match_marker("Just a regular line"))

    def test_conclusion_exact(self):
        self.assertEqual(_match_marker("[CONCLUSION]"), "[CONCLUSION]")

    def test_marker_case_insensitive(self):
        self.assertEqual(_match_marker("[product_5] — Some Name"), "[PRODUCT_5]")

    def test_marker_with_tab_suffix(self):
        self.assertEqual(_match_marker("[RETENTION_RESET]\tsome text"), "[RETENTION_RESET]")


class TestExtractScriptBodySuffixed(unittest.TestCase):
    """Test extract_script_body() with [MARKER] — Product Name format."""

    def test_suffixed_markers_parsed(self):
        text = (
            "[HOOK]\nHook text.\n\n"
            "[PRODUCT_5] — Narwal Freo Pro\nProduct five text.\n\n"
            "[PRODUCT_4] — Roborock Saros 10\nProduct four text.\n\n"
            "[PRODUCT_3] — Dreame D20 Plus\nProduct three text.\n\n"
            "[RETENTION_RESET]\nReset text.\n\n"
            "[PRODUCT_2] — Tapo RV30 Max Plus\nProduct two text.\n\n"
            "[PRODUCT_1] — Roborock Q7 M5+\nProduct one text.\n\n"
            "[CONCLUSION]\nConclusion text.\n"
        )
        result = extract_script_body(text)
        for m in ("[HOOK]", "[PRODUCT_5]", "[PRODUCT_1]", "[CONCLUSION]"):
            self.assertIn(m, result)


class TestGenerateDraft(unittest.TestCase):
    """Test generate_draft() with mocked HTTP."""

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(MOCK_OPENAI_RESPONSE)

        result = generate_draft("Write a script", api_key="sk-test-123")
        self.assertTrue(result.success)
        self.assertIn("[HOOK]", result.text)
        self.assertEqual(result.model, "gpt-4o-2025-01-01")
        self.assertEqual(result.input_tokens, 1500)
        self.assertEqual(result.output_tokens, 800)

    def test_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = generate_draft("Write a script")
            self.assertFalse(result.success)
            self.assertIn("OPENAI_API_KEY", result.error)

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.openai.com", 429, "Rate limited",
            {}, MagicMock(read=MagicMock(return_value=b'{"error":"rate_limited"}'))
        )
        result = generate_draft("Write a script", api_key="sk-test-123")
        self.assertFalse(result.success)
        self.assertIn("429", result.error)


class TestGenerateRefinement(unittest.TestCase):
    """Test generate_refinement() with mocked HTTP."""

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(MOCK_ANTHROPIC_RESPONSE)

        result = generate_refinement("Refine this script", api_key="sk-ant-test")
        self.assertTrue(result.success)
        self.assertIn("[HOOK]", result.text)
        self.assertEqual(result.input_tokens, 2000)

    def test_missing_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            result = generate_refinement("Refine this")
            self.assertFalse(result.success)
            self.assertIn("ANTHROPIC_API_KEY", result.error)

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_empty_response(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen({"content": [], "usage": {}})
        result = generate_refinement("Refine this", api_key="sk-ant-test")
        self.assertFalse(result.success)
        self.assertIn("No text", result.error)


class TestRunScriptPipeline(unittest.TestCase):
    """Test run_script_pipeline() end-to-end with mocked APIs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp.name) / "script"

    def tearDown(self):
        self.tmp.cleanup()

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_full_pipeline(self, mock_urlopen):
        # First call = OpenAI, second call = Anthropic
        mock_urlopen.side_effect = [
            _mock_urlopen(MOCK_OPENAI_RESPONSE),
            _mock_urlopen(MOCK_ANTHROPIC_RESPONSE),
        ]

        result = run_script_pipeline(
            "Write a draft",
            "Refine: (paste draft here)",
            self.output_dir,
            openai_key="sk-test",
            anthropic_key="sk-ant-test",
        )

        self.assertTrue(result.success)
        self.assertGreater(result.word_count, 0)

        # Check files were written
        self.assertTrue((self.output_dir / "script_raw.txt").is_file())
        self.assertTrue((self.output_dir / "script_final.txt").is_file())
        self.assertTrue((self.output_dir / "script.txt").is_file())
        self.assertTrue((self.output_dir / "script_gen_meta.json").is_file())

        # Check script.txt has section markers
        script = (self.output_dir / "script.txt").read_text()
        self.assertIn("[HOOK]", script)
        self.assertIn("[CONCLUSION]", script)

        # Check metadata
        meta = json.loads((self.output_dir / "script_gen_meta.json").read_text())
        self.assertIn("draft_model", meta)
        self.assertIn("refine_model", meta)
        self.assertIn("thumbnail_headlines", meta)

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_skip_refinement(self, mock_urlopen):
        mock_urlopen.return_value = _mock_urlopen(MOCK_OPENAI_RESPONSE)

        result = run_script_pipeline(
            "Write a draft",
            "Refine: (paste draft here)",
            self.output_dir,
            openai_key="sk-test",
            skip_refinement=True,
        )

        self.assertTrue(result.success)
        self.assertTrue((self.output_dir / "script_raw.txt").is_file())
        self.assertTrue((self.output_dir / "script.txt").is_file())
        # No script_final.txt when refinement skipped
        self.assertFalse((self.output_dir / "script_final.txt").is_file())

    @patch("tools.lib.script_generate._try_browser_draft",
           return_value=ScriptGenResult(success=False, error="no browser in test"))
    def test_missing_openai_key(self, _mock_browser):
        with patch.dict("os.environ", {}, clear=True):
            result = run_script_pipeline(
                "Write a draft",
                "Refine: (paste draft here)",
                self.output_dir,
            )
            self.assertFalse(result.success)
            self.assertTrue(any("Draft generation failed" in e for e in result.errors))

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_refinement_failure_falls_back(self, mock_urlopen):
        """When refinement fails, pipeline should still succeed using raw draft."""
        import urllib.error

        def side_effect(*args, **kwargs):
            # Track call count to differentiate calls
            if not hasattr(side_effect, 'call_count'):
                side_effect.call_count = 0
            side_effect.call_count += 1
            if side_effect.call_count == 1:
                # First call (OpenAI): success
                return _mock_urlopen(MOCK_OPENAI_RESPONSE)
            # Second call (Anthropic): fail
            err = urllib.error.HTTPError(
                "https://api.anthropic.com", 500, "Server Error",
                {}, MagicMock(read=MagicMock(return_value=b'error'))
            )
            raise err

        mock_urlopen.side_effect = side_effect

        result = run_script_pipeline(
            "Write a draft",
            "Refine: (paste draft here)",
            self.output_dir,
            openai_key="sk-test",
            anthropic_key="sk-ant-test",
        )

        # Should still succeed (using raw draft as fallback)
        self.assertTrue(result.success)
        self.assertTrue(any("Refinement failed" in e for e in result.errors))
        self.assertTrue((self.output_dir / "script.txt").is_file())


class TestPipelineScriptGenerate(unittest.TestCase):
    """Test pipeline.py cmd_script with --generate flag."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.videos_base = Path(self.tmp.name)
        self.patchers = [
            patch("tools.lib.video_paths.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.pipeline_status._cache", {}),
            patch("tools.lib.amazon_research.VIDEOS_BASE", self.videos_base),
            patch("tools.lib.notify.send_telegram", return_value=False),
            patch("tools.pipeline._run_learning_gate", return_value=None),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def _setup_video(self, video_id: str, niche: str = "wireless earbuds"):
        """Create minimal video structure with valid products."""
        from tools.lib.video_paths import VideoPaths
        from tools.lib.pipeline_status import start_pipeline

        paths = VideoPaths(video_id)
        paths.ensure_dirs()
        start_pipeline(video_id)

        paths.niche_txt.write_text(niche + "\n", encoding="utf-8")

        data = {
            "keyword": niche,
            "products": [
                {
                    "rank": r,
                    "name": f"Product {r}",
                    "positioning": f"best for {r}",
                    "benefits": [f"Benefit A for {r}", f"Benefit B for {r}"],
                    "target_audience": "everyone",
                    "downside": f"Minor issue with {r}",
                    "amazon_url": f"https://amazon.com/dp/B00{r}",
                    "affiliate_url": f"https://amzn.to/test{r}",
                    "asin": f"B00{r}TEST",
                    "price": "$99.99",
                    "rating": "4.5",
                    "reviews_count": "1234",
                    "evidence": [
                        {
                            "source": "Wirecutter",
                            "label": "top pick" if r == 1 else "",
                            "url": "https://nytimes.com/wirecutter/test",
                            "reasons": [f"Wirecutter says product {r} is great"],
                        },
                    ],
                    "key_claims": [f"Best in class for {r}"],
                }
                for r in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(json.dumps(data), encoding="utf-8")
        return paths

    @patch("tools.lib.script_generate.urllib.request.urlopen")
    def test_generate_flag(self, mock_urlopen):
        """Test that --generate calls LLM APIs and writes script.txt."""
        import argparse

        mock_urlopen.side_effect = [
            _mock_urlopen(MOCK_OPENAI_RESPONSE),
            _mock_urlopen(MOCK_ANTHROPIC_RESPONSE),
        ]

        paths = self._setup_video("test-gen")

        from tools.pipeline import cmd_script
        args = argparse.Namespace(
            video_id="test-gen",
            charismatic="reality_check",
            generate=True,
            force=False,
            no_approval=True,
        )

        with patch.dict("os.environ", {
            "OPENAI_API_KEY": "sk-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }):
            result = cmd_script(args)

        self.assertEqual(result, 0)

        # Verify script files exist
        self.assertTrue(paths.script_txt.is_file())
        script = paths.script_txt.read_text()
        self.assertIn("[HOOK]", script)
        self.assertIn("[CONCLUSION]", script)

    def test_generate_without_api_key(self):
        """Test --generate without OPENAI_API_KEY fails gracefully."""
        import argparse

        self._setup_video("test-gen-nokey")

        from tools.pipeline import cmd_script
        from tools.lib.script_generate import ScriptGenResult
        args = argparse.Namespace(
            video_id="test-gen-nokey",
            charismatic="reality_check",
            generate=True,
            force=False,
            no_approval=True,
        )

        # Mock browser fallback to fail so we test the no-key path
        failed_browser = ScriptGenResult(success=False, error="no browser in test")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENCLAW_BROWSER_LLM": ""}, clear=False), \
             patch("tools.lib.script_generate._try_browser_draft", return_value=failed_browser):
            # Need to ensure the key isn't inherited
            import os
            old_key = os.environ.pop("OPENAI_API_KEY", None)
            try:
                result = cmd_script(args)
            finally:
                if old_key:
                    os.environ["OPENAI_API_KEY"] = old_key

        self.assertEqual(result, 1)  # EXIT_ERROR

    def test_script_without_generate_returns_action_required(self):
        """Without --generate, cmd_script should return action_required when no script.txt."""
        import argparse

        self._setup_video("test-manual")

        from tools.pipeline import cmd_script
        args = argparse.Namespace(
            video_id="test-manual",
            charismatic="reality_check",
            generate=False,
            force=False,
        )
        result = cmd_script(args)
        self.assertEqual(result, 2)  # EXIT_ACTION_REQUIRED


class TestSplitScriptOutputs(unittest.TestCase):
    """Test split_script_outputs() separation logic."""

    SCRIPT_BODY = (
        "[HOOK]\n"
        "You spent hours reading Amazon reviews.\n\n"
        "[AVATAR_INTRO]\n"
        "I'm Ray, and I research products so you don't have to.\n\n"
        "[PRODUCT_5]\n"
        "Starting at five, the JBL Tune 230NC.\n\n"
        "[PRODUCT_4]\n"
        "Number four, Samsung Galaxy Buds3 Pro.\n\n"
        "[PRODUCT_3]\n"
        "The AirPods Pro 2 at number three.\n\n"
        "[RETENTION_RESET]\n"
        "Have you ever returned earbuds because they didn't fit?\n\n"
        "[PRODUCT_2]\n"
        "Number two, Sony WF-1000XM5.\n\n"
        "[PRODUCT_1]\n"
        "Number one: Bose QuietComfort Ultra Earbuds.\n\n"
        "[CONCLUSION]\n"
        "Links to all five products are in the description.\n"
    )

    META = {
        "avatar_intro": "I'm Ray, and I research products so you don't have to.",
        "youtube_description": "The 5 best wireless earbuds based on expert reviews.",
    }

    def test_split_script_outputs_basic(self):
        """narration has no markers, avatar extracted, desc extracted."""
        result = split_script_outputs(self.SCRIPT_BODY, self.META)
        self.assertIn("Amazon reviews", result["narration"])
        self.assertIn("Ray", result["avatar"])
        self.assertIn("wireless earbuds", result["youtube_description"])

    def test_split_narration_strips_markers(self):
        """[PRODUCT_5] and other markers must not appear in narration."""
        result = split_script_outputs(self.SCRIPT_BODY, self.META)
        self.assertNotIn("[PRODUCT_5]", result["narration"])
        self.assertNotIn("[HOOK]", result["narration"])
        self.assertNotIn("[RETENTION_RESET]", result["narration"])
        self.assertNotIn("[CONCLUSION]", result["narration"])

    def test_split_narration_excludes_avatar(self):
        """Avatar intro section must not appear in narration."""
        result = split_script_outputs(self.SCRIPT_BODY, self.META)
        self.assertNotIn("[AVATAR_INTRO]", result["narration"])
        # The avatar content line should be removed from narration
        self.assertNotIn("I'm Ray, and I research products", result["narration"])

    def test_split_empty_metadata(self):
        """Gracefully handle empty metadata."""
        result = split_script_outputs(self.SCRIPT_BODY, {})
        self.assertEqual(result["avatar"], "")
        self.assertEqual(result["youtube_description"], "")
        # Narration should still be clean
        self.assertNotIn("[PRODUCT_5]", result["narration"])


class TestStripSectionMarkers(unittest.TestCase):
    """Test tts_preprocess.strip_section_markers() safety net."""

    def test_strips_all_marker_types(self):
        text = (
            "[HOOK]\n"
            "Hook text.\n"
            "[PRODUCT_5]\n"
            "Product text.\n"
            "[RETENTION_RESET]\n"
            "Reset text.\n"
            "[CONCLUSION]\n"
            "Conclusion text.\n"
        )
        result = strip_section_markers(text)
        self.assertNotIn("[HOOK]", result)
        self.assertNotIn("[PRODUCT_5]", result)
        self.assertNotIn("[RETENTION_RESET]", result)
        self.assertNotIn("[CONCLUSION]", result)
        self.assertIn("Hook text.", result)
        self.assertIn("Product text.", result)

    def test_strips_marker_with_suffix(self):
        text = "[PRODUCT_3] — AirPods Pro 2\nGreat earbuds.\n"
        result = strip_section_markers(text)
        self.assertNotIn("[PRODUCT_3]", result)
        self.assertIn("Great earbuds.", result)

    def test_preserves_clean_text(self):
        text = "Just normal text without markers."
        result = strip_section_markers(text)
        self.assertEqual(result, text)

    def test_strips_avatar_intro_marker(self):
        text = "[AVATAR_INTRO]\nI'm Ray.\n[PRODUCT_5]\nProduct.\n"
        result = strip_section_markers(text)
        self.assertNotIn("[AVATAR_INTRO]", result)
        self.assertNotIn("[PRODUCT_5]", result)
        self.assertIn("I'm Ray.", result)


if __name__ == "__main__":
    unittest.main()
