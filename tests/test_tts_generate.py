"""Tests for tools.lib.tts_generate — chunking and validation logic.

Does NOT call the ElevenLabs API. Tests chunking, validation, and metadata only.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.tts_generate import (
    CHUNK_WORDS_MAX,
    CHUNK_WORDS_MIN,
    MAX_RETRIES,
    SPEAKING_WPM,
    ChunkMeta,
    chunk_script,
    validate_chunk_audio,
)


# Sample script text (~600 words, should produce 2 chunks)
SAMPLE_TEXT = (
    "These are the five best products you can buy in twenty twenty-six. "
    "I tested over twenty options, spent hundreds of hours comparing, and narrowed it "
    "down to these five. No sponsorships, no bias, just honest rankings based on "
    "real-world use. Let me walk you through each one from five to one. "
    "Starting at number five, the budget pick. The brand finally got "
    "the design right with these. The build looks premium and feels solid in "
    "your hand. Performance is smooth and reliable with a nice overall experience. The "
    "quality is solid but not class-leading. You get about seven hours of "
    "battery life on a single charge, which is respectable for this price range. The companion app "
    "gives you plenty of customization options. The downside is that it only works best with "
    "certain devices and the companion app feels a little slow at times. If you are in "
    "that ecosystem, this is a great pick. Outside of it, you lose some features. "
    "Number four, the comfort champion. This brand has always been about comfort, "
    "and this model continues that tradition beautifully. This is one of the most "
    "comfortable products I have ever used in this entire category. The premium features "
    "add a layer of quality that actually makes a meaningful difference in daily use. "
    "The overall performance improved significantly over the previous version. Battery "
    "life hits eight hours with heavy use. The connectivity works flawlessly across "
    "devices with seamless switching. My gripe is the app design. It is functional but "
    "feels dated compared to competitors. Still, for all-day comfort with great "
    "performance, this brand delivers consistently well. "
    "Number three, the value pick. This company keeps surprising me with their "
    "incredible value proposition. For under a hundred dollars, you get performance that "
    "rivals products twice the price. The unique design looks fresh and the "
    "build quality is surprisingly solid for the money. Performance is balanced with "
    "a slight emphasis on what most people will enjoy in everyday scenarios. Battery "
    "life is impressive at nine hours. The companion app is clean and intuitive with "
    "a modern interface. The honest downside is that the design has minor issues in "
    "certain outdoor conditions. For everyday indoor use, this punches way above "
    "its weight class and delivers remarkable results. "
    "Before we get to the top two, I want to hear from you. What matters most in "
    "your choice? Performance, comfort, or build quality? Drop your answer "
    "in the comments below. Now let us see which two earned the top spots. "
    "Number two, the premium option. This brand has been the quality king for years and "
    "this model continues that legacy with several meaningful upgrades. The performance "
    "is simply the best you can get at this level. Period. Advanced technology means "
    "everything works phenomenally well out of the box. The quality improvements make "
    "even casual everyday use feel noticeably better. Build quality is premium with "
    "attention to every detail. Battery hits eight hours, and the app is one of the "
    "best designed in the entire industry. The downside is the price. At three hundred "
    "dollars, this is expensive. And the fit can vary for different users depending on "
    "preferences. But if quality and performance are your top priorities, nothing on "
    "the market beats this right now. "
    "And the number one pick is the overall winner. It does everything well. Great "
    "performance, strong build quality, long battery life, and a comfortable design "
    "that works for almost everyone. The app is excellent with regular updates and it "
    "works perfectly across all major platforms without any compatibility issues. This "
    "is the product I reach for every single morning without hesitation. "
    "Those are my top five picks for twenty twenty-six. Every product on "
    "this list is genuinely worth your money for the right person. Links to all five "
    "are in the description below with special deals when available. If this video "
    "helped you make a decision, hit subscribe for more honest reviews every single "
    "week. Thanks for watching and I will see you in the next one."
)


class TestChunking(unittest.TestCase):
    def test_chunk_produces_multiple(self):
        chunks = chunk_script(SAMPLE_TEXT)
        self.assertGreater(len(chunks), 1)

    def test_chunk_word_counts_in_range(self):
        chunks = chunk_script(SAMPLE_TEXT)
        for i, chunk in enumerate(chunks):
            words = len(chunk.split())
            # Last chunk can be smaller
            if i < len(chunks) - 1:
                self.assertGreaterEqual(
                    words, 100,
                    f"Chunk {i} too small: {words} words"
                )
            self.assertLessEqual(
                words, CHUNK_WORDS_MAX + 50,  # small tolerance for sentence boundaries
                f"Chunk {i} too large: {words} words"
            )

    def test_chunk_preserves_all_words(self):
        chunks = chunk_script(SAMPLE_TEXT)
        total_words = sum(len(c.split()) for c in chunks)
        original_words = len(SAMPLE_TEXT.split())
        self.assertEqual(total_words, original_words)

    def test_chunk_short_text_single_chunk(self):
        short = "This is a short script. Only a few sentences."
        chunks = chunk_script(short)
        self.assertEqual(len(chunks), 1)

    def test_chunk_empty_text(self):
        chunks = chunk_script("")
        self.assertEqual(len(chunks), 0)

    def test_chunk_sentences_not_split_mid_sentence(self):
        chunks = chunk_script(SAMPLE_TEXT)
        for chunk in chunks:
            # Each chunk should end with sentence-ending punctuation
            stripped = chunk.strip()
            if stripped:
                self.assertTrue(
                    stripped[-1] in ".!?",
                    f"Chunk doesn't end with sentence punctuation: ...{stripped[-20:]}"
                )


class TestAudioValidation(unittest.TestCase):
    def test_missing_file(self):
        ok, msg = validate_chunk_audio(Path("/nonexistent/file.mp3"), 100)
        self.assertFalse(ok)
        self.assertIn("does not exist", msg)

    def test_empty_file(self):
        tmp = Path(tempfile.mktemp(suffix=".mp3"))
        tmp.write_bytes(b"")
        ok, msg = validate_chunk_audio(tmp, 100)
        self.assertFalse(ok)
        self.assertIn("too small", msg.lower())
        tmp.unlink()

    def test_reasonable_file(self):
        # Create a file that looks like ~30s of 128kbps MP3
        # 128kbps = 16000 bytes/sec, 30s = 480000 bytes
        tmp = Path(tempfile.mktemp(suffix=".mp3"))
        tmp.write_bytes(b"\x00" * 480000)  # ~30s at 128kbps
        # 30s ≈ 78 words at 155 WPM
        ok, msg = validate_chunk_audio(tmp, 78)
        self.assertTrue(ok, msg)
        tmp.unlink()

    def test_too_short_audio(self):
        # File representing ~5s but expecting 60s of speech
        tmp = Path(tempfile.mktemp(suffix=".mp3"))
        tmp.write_bytes(b"\x00" * 80000)  # ~5s
        ok, msg = validate_chunk_audio(tmp, 300)  # 300 words ≈ 116s
        self.assertFalse(ok)
        self.assertIn("too short", msg.lower())
        tmp.unlink()


class TestConstants(unittest.TestCase):
    def test_wpm(self):
        self.assertEqual(SPEAKING_WPM, 155)

    def test_chunk_range(self):
        self.assertEqual(CHUNK_WORDS_MIN, 300)
        self.assertEqual(CHUNK_WORDS_MAX, 450)

    def test_max_retries(self):
        self.assertEqual(MAX_RETRIES, 1)


class TestChunkMeta(unittest.TestCase):
    def test_default_status(self):
        meta = ChunkMeta(
            index=0, text_raw="test", text_preprocessed="test",
            word_count=1, estimated_duration_s=0.4,
            voice_id="abc", model_id="test",
            stability=0.5, similarity_boost=0.75,
            style=0.0, output_format="mp3",
        )
        self.assertEqual(meta.status, "pending")
        self.assertEqual(meta.retries, 0)
        self.assertEqual(meta.error, "")


if __name__ == "__main__":
    unittest.main()
