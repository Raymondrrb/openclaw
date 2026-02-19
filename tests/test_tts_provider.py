#!/usr/bin/env python3
"""Tests for rayvault/tts_provider.py — TTS provider abstraction."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from rayvault.tts_provider import (
    MockTTSProvider,
    TTSProvider,
    available_providers,
    get_provider,
    tts_input_hash,
)


# ---------------------------------------------------------------
# tts_input_hash
# ---------------------------------------------------------------

class TestTTSInputHash(unittest.TestCase):

    def test_returns_24_char_hex(self):
        h = tts_input_hash("hello", "voice1", "elevenlabs")
        self.assertEqual(len(h), 24)
        int(h, 16)

    def test_deterministic(self):
        h1 = tts_input_hash("hello", "voice1", "elevenlabs")
        h2 = tts_input_hash("hello", "voice1", "elevenlabs")
        self.assertEqual(h1, h2)

    def test_different_text_different_hash(self):
        h1 = tts_input_hash("hello", "voice1", "elevenlabs")
        h2 = tts_input_hash("world", "voice1", "elevenlabs")
        self.assertNotEqual(h1, h2)

    def test_different_voice_different_hash(self):
        h1 = tts_input_hash("hello", "voice1", "elevenlabs")
        h2 = tts_input_hash("hello", "voice2", "elevenlabs")
        self.assertNotEqual(h1, h2)

    def test_different_provider_different_hash(self):
        h1 = tts_input_hash("hello", "voice1", "elevenlabs")
        h2 = tts_input_hash("hello", "voice1", "mock")
        self.assertNotEqual(h1, h2)

    def test_different_model_different_hash(self):
        h1 = tts_input_hash("hello", "v1", "el", model_id="a")
        h2 = tts_input_hash("hello", "v1", "el", model_id="b")
        self.assertNotEqual(h1, h2)

    def test_different_settings_different_hash(self):
        h1 = tts_input_hash("hello", "v1", "el", settings={"speed": 1.0})
        h2 = tts_input_hash("hello", "v1", "el", settings={"speed": 1.5})
        self.assertNotEqual(h1, h2)

    def test_none_settings_vs_no_settings(self):
        h1 = tts_input_hash("hello", "v1", "el", settings=None)
        h2 = tts_input_hash("hello", "v1", "el")
        self.assertEqual(h1, h2)

    def test_text_stripped(self):
        h1 = tts_input_hash("  hello  ", "v1", "el")
        h2 = tts_input_hash("hello", "v1", "el")
        self.assertEqual(h1, h2)

    def test_reference_audio_sha1_differs(self):
        h1 = tts_input_hash("hello", "v1", "el", reference_audio_sha1="sha_a")
        h2 = tts_input_hash("hello", "v1", "el", reference_audio_sha1="sha_b")
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------
# MockTTSProvider
# ---------------------------------------------------------------

class TestMockTTSProvider(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.provider = MockTTSProvider()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_name(self):
        self.assertEqual(self.provider.name, "mock")

    def test_capabilities(self):
        self.assertFalse(self.provider.supports_voice_clone)
        self.assertFalse(self.provider.supports_duration_control)

    def test_synthesize_creates_wav(self):
        out = Path(self.tmpdir) / "test.wav"
        self.provider.synthesize("Hello world", "v1", out)
        self.assertTrue(out.exists())
        self.assertGreater(out.stat().st_size, 0)

    def test_synthesize_valid_wav(self):
        out = Path(self.tmpdir) / "test.wav"
        self.provider.synthesize("Hello world", "v1", out)
        with wave.open(str(out), "r") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 48000)

    def test_synthesize_returns_metadata(self):
        out = Path(self.tmpdir) / "test.wav"
        result = self.provider.synthesize("Hello world", "v1", out)
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["voice_id"], "v1")
        self.assertIn("duration_sec", result)
        self.assertIn("sha1_audio", result)
        self.assertIn("tts_inputs_hash", result)
        self.assertIn("sample_rate", result)
        self.assertEqual(result["sample_rate"], 48000)

    def test_duration_proportional_to_text(self):
        out1 = Path(self.tmpdir) / "short.wav"
        out2 = Path(self.tmpdir) / "long.wav"
        r1 = self.provider.synthesize("Hello", "v1", out1)
        r2 = self.provider.synthesize("Hello " * 100, "v1", out2)
        self.assertGreater(r2["duration_sec"], r1["duration_sec"])

    def test_minimum_duration_1_sec(self):
        out = Path(self.tmpdir) / "test.wav"
        result = self.provider.synthesize("Hi", "v1", out)
        self.assertGreaterEqual(result["duration_sec"], 1.0)

    def test_creates_parent_dirs(self):
        out = Path(self.tmpdir) / "deep" / "nested" / "test.wav"
        self.provider.synthesize("Hello", "v1", out)
        self.assertTrue(out.exists())

    def test_sha1_deterministic(self):
        out1 = Path(self.tmpdir) / "a.wav"
        out2 = Path(self.tmpdir) / "b.wav"
        r1 = self.provider.synthesize("Hello world", "v1", out1)
        r2 = self.provider.synthesize("Hello world", "v1", out2)
        self.assertEqual(r1["sha1_audio"], r2["sha1_audio"])

    def test_implements_protocol(self):
        self.assertIsInstance(self.provider, TTSProvider)


# ---------------------------------------------------------------
# get_provider
# ---------------------------------------------------------------

class TestGetProvider(unittest.TestCase):

    def test_get_mock(self):
        p = get_provider("mock")
        self.assertIsInstance(p, MockTTSProvider)

    def test_get_elevenlabs(self):
        p = get_provider("elevenlabs")
        self.assertEqual(p.name, "elevenlabs")

    def test_get_moss(self):
        p = get_provider("moss")
        self.assertEqual(p.name, "moss_tts")

    def test_get_moss_tts(self):
        p = get_provider("moss_tts")
        self.assertEqual(p.name, "moss_tts")

    def test_case_insensitive(self):
        p = get_provider("MOCK")
        self.assertIsInstance(p, MockTTSProvider)

    def test_strips_whitespace(self):
        p = get_provider("  mock  ")
        self.assertIsInstance(p, MockTTSProvider)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_provider("nonexistent_provider")


# ---------------------------------------------------------------
# available_providers
# ---------------------------------------------------------------

class TestAvailableProviders(unittest.TestCase):

    def test_returns_list(self):
        providers = available_providers()
        self.assertIsInstance(providers, list)

    def test_contains_elevenlabs(self):
        self.assertIn("elevenlabs", available_providers())

    def test_contains_mock(self):
        self.assertIn("mock", available_providers())

    def test_contains_moss(self):
        self.assertIn("moss", available_providers())


# ---------------------------------------------------------------
# tts_input_hash edge cases
# ---------------------------------------------------------------

class TestTTSInputHashEdgeCases(unittest.TestCase):

    def test_empty_text(self):
        h = tts_input_hash("", "v1", "el")
        self.assertEqual(len(h), 24)

    def test_unicode_text(self):
        h = tts_input_hash("café résumé", "v1", "el")
        self.assertEqual(len(h), 24)

    def test_long_text(self):
        h = tts_input_hash("word " * 10000, "v1", "el")
        self.assertEqual(len(h), 24)

    def test_settings_order_irrelevant(self):
        h1 = tts_input_hash("hi", "v1", "el", settings={"a": 1, "b": 2})
        h2 = tts_input_hash("hi", "v1", "el", settings={"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_empty_settings_same_as_none(self):
        # Empty dict is falsy in `if settings:` check, same as None
        h1 = tts_input_hash("hi", "v1", "el", settings={})
        h2 = tts_input_hash("hi", "v1", "el", settings=None)
        self.assertEqual(h1, h2)


# ---------------------------------------------------------------
# get_provider edge cases
# ---------------------------------------------------------------

class TestGetProviderEdgeCases(unittest.TestCase):

    def test_empty_string_defaults(self):
        import os
        # Clear env to ensure fallback to default
        old = os.environ.pop("TTS_PROVIDER", None)
        try:
            p = get_provider("")
            self.assertEqual(p.name, "elevenlabs")
        finally:
            if old is not None:
                os.environ["TTS_PROVIDER"] = old

    def test_mixed_case(self):
        p = get_provider("ElevenLabs")
        self.assertEqual(p.name, "elevenlabs")

    def test_empty_raises_correct_error(self):
        with self.assertRaises(ValueError) as ctx:
            get_provider("fake_provider")
        self.assertIn("fake_provider", str(ctx.exception))
        self.assertIn("Available", str(ctx.exception))


# ---------------------------------------------------------------
# MockTTSProvider edge cases
# ---------------------------------------------------------------

class TestMockTTSProviderEdgeCases(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.provider = MockTTSProvider()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_text(self):
        out = Path(self.tmpdir) / "empty.wav"
        result = self.provider.synthesize("", "v1", out)
        self.assertTrue(out.exists())
        self.assertGreaterEqual(result["duration_sec"], 1.0)

    def test_single_word(self):
        out = Path(self.tmpdir) / "single.wav"
        result = self.provider.synthesize("hello", "v1", out)
        self.assertTrue(out.exists())
        self.assertGreaterEqual(result["duration_sec"], 1.0)

    def test_hash_differs_by_text(self):
        out1 = Path(self.tmpdir) / "a.wav"
        out2 = Path(self.tmpdir) / "b.wav"
        r1 = self.provider.synthesize("hello", "v1", out1)
        r2 = self.provider.synthesize("world", "v1", out2)
        self.assertNotEqual(r1["tts_inputs_hash"], r2["tts_inputs_hash"])

    def test_overwrite_existing(self):
        out = Path(self.tmpdir) / "test.wav"
        self.provider.synthesize("first", "v1", out)
        size1 = out.stat().st_size
        self.provider.synthesize("first " * 100, "v1", out)
        size2 = out.stat().st_size
        self.assertGreater(size2, size1)


# ---------------------------------------------------------------
# available_providers edge cases
# ---------------------------------------------------------------

class TestAvailableProvidersEdgeCases(unittest.TestCase):

    def test_all_strings(self):
        for name in available_providers():
            self.assertIsInstance(name, str)

    def test_all_resolvable(self):
        for name in available_providers():
            p = get_provider(name)
            self.assertIsNotNone(p)

    def test_contains_moss_tts(self):
        self.assertIn("moss_tts", available_providers())


if __name__ == "__main__":
    unittest.main()
