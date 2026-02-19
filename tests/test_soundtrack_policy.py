#!/usr/bin/env python3
"""Tests for rayvault/soundtrack_policy.py — license tiers and soundtrack decisions."""

from __future__ import annotations

import unittest

from rayvault.policies import (
    SAFETY_JITTER_PITCH_RATIO,
    SAFETY_JITTER_TEMPO_RATIO,
    SOUNDTRACK_CHAPTER_GAIN_JITTER_DB,
)
from rayvault.soundtrack_policy import (
    SoundtrackDecision,
    build_ai_music_editor_proof,
    compute_chapter_gain_jitter,
    compute_safety_jitter,
    conform_cache_key,
    publish_policy_for_tier,
)


# ---------------------------------------------------------------
# publish_policy_for_tier
# ---------------------------------------------------------------

class TestPublishPolicyForTier(unittest.TestCase):

    def test_green(self):
        self.assertEqual(publish_policy_for_tier("GREEN"), "AUTO_PUBLISH")

    def test_amber(self):
        self.assertEqual(publish_policy_for_tier("AMBER"), "BLOCKED_FOR_REVIEW")

    def test_red(self):
        self.assertEqual(publish_policy_for_tier("RED"), "MANUAL_ONLY")

    def test_unknown_defaults_manual(self):
        self.assertEqual(publish_policy_for_tier("UNKNOWN"), "MANUAL_ONLY")

    def test_empty_defaults_manual(self):
        self.assertEqual(publish_policy_for_tier(""), "MANUAL_ONLY")


# ---------------------------------------------------------------
# compute_safety_jitter
# ---------------------------------------------------------------

class TestComputeSafetyJitter(unittest.TestCase):

    def test_amber_applied(self):
        result = compute_safety_jitter("AMBER")
        self.assertTrue(result["applied"])
        self.assertEqual(result["pitch_ratio"], SAFETY_JITTER_PITCH_RATIO)
        self.assertEqual(result["tempo_ratio"], SAFETY_JITTER_TEMPO_RATIO)

    def test_green_not_applied(self):
        result = compute_safety_jitter("GREEN")
        self.assertFalse(result["applied"])

    def test_red_not_applied(self):
        result = compute_safety_jitter("RED")
        self.assertFalse(result["applied"])

    def test_empty_not_applied(self):
        result = compute_safety_jitter("")
        self.assertFalse(result["applied"])


# ---------------------------------------------------------------
# compute_chapter_gain_jitter
# ---------------------------------------------------------------

class TestComputeChapterGainJitter(unittest.TestCase):

    def test_returns_list(self):
        chapters = [{"id": "ch_intro"}, {"id": "ch_p1"}, {"id": "ch_p2"}]
        result = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)

    def test_each_entry_has_keys(self):
        chapters = [{"id": "ch_intro"}]
        result = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        entry = result[0]
        self.assertIn("chapter_id", entry)
        self.assertIn("gain_offset_db", entry)
        self.assertIn("seed", entry)

    def test_deterministic(self):
        chapters = [{"id": "ch_intro"}, {"id": "ch_p1"}]
        r1 = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        r2 = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        self.assertEqual(r1, r2)

    def test_different_run_id_different_jitter(self):
        chapters = [{"id": "ch_intro"}]
        r1 = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        r2 = compute_chapter_gain_jitter("RUN_B", "track_01", chapters)
        # Seeds differ
        self.assertNotEqual(r1[0]["seed"], r2[0]["seed"])

    def test_jitter_within_bounds(self):
        chapters = [{"id": f"ch_{i}"} for i in range(20)]
        result = compute_chapter_gain_jitter("RUN_X", "track_Y", chapters)
        for entry in result:
            self.assertGreaterEqual(
                entry["gain_offset_db"],
                -SOUNDTRACK_CHAPTER_GAIN_JITTER_DB,
            )
            self.assertLessEqual(
                entry["gain_offset_db"],
                SOUNDTRACK_CHAPTER_GAIN_JITTER_DB,
            )

    def test_empty_chapters(self):
        result = compute_chapter_gain_jitter("RUN_A", "track_01", [])
        self.assertEqual(result, [])

    def test_chapter_id_fallback_to_type(self):
        chapters = [{"type": "intro"}]
        result = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        self.assertEqual(result[0]["chapter_id"], "intro")

    def test_chapter_id_fallback_to_unknown(self):
        chapters = [{}]
        result = compute_chapter_gain_jitter("RUN_A", "track_01", chapters)
        self.assertEqual(result[0]["chapter_id"], "unknown")


# ---------------------------------------------------------------
# build_ai_music_editor_proof
# ---------------------------------------------------------------

class TestBuildAIMusicEditorProof(unittest.TestCase):

    def test_not_attempted(self):
        proof = build_ai_music_editor_proof(attempted=False)
        self.assertFalse(proof["attempted"])
        self.assertFalse(proof["success"])

    def test_success_within_eps(self):
        proof = build_ai_music_editor_proof(
            before_duration_sec=180.0,
            after_duration_sec=600.1,
            target_duration_sec=600.0,
            attempted=True,
        )
        self.assertTrue(proof["attempted"])
        self.assertTrue(proof["success"])
        self.assertAlmostEqual(proof["diff_sec"], 0.1, places=2)

    def test_failure_beyond_eps(self):
        proof = build_ai_music_editor_proof(
            before_duration_sec=180.0,
            after_duration_sec=605.0,
            target_duration_sec=600.0,
            attempted=True,
        )
        self.assertTrue(proof["attempted"])
        self.assertFalse(proof["success"])

    def test_custom_eps(self):
        proof = build_ai_music_editor_proof(
            after_duration_sec=601.0,
            target_duration_sec=600.0,
            attempted=True,
            eps=2.0,
        )
        self.assertTrue(proof["success"])

    def test_none_after_duration(self):
        proof = build_ai_music_editor_proof(
            after_duration_sec=None,
            target_duration_sec=600.0,
            attempted=True,
        )
        self.assertFalse(proof["success"])

    def test_zero_target(self):
        proof = build_ai_music_editor_proof(
            after_duration_sec=600.0,
            target_duration_sec=0.0,
            attempted=True,
        )
        self.assertFalse(proof["success"])


# ---------------------------------------------------------------
# conform_cache_key
# ---------------------------------------------------------------

class TestConformCacheKey(unittest.TestCase):

    def test_returns_16_char_hex(self):
        key = conform_cache_key("abc123sha1", 600.0)
        self.assertEqual(len(key), 16)
        int(key, 16)

    def test_deterministic(self):
        k1 = conform_cache_key("sha_A", 600.0)
        k2 = conform_cache_key("sha_A", 600.0)
        self.assertEqual(k1, k2)

    def test_different_sha_different_key(self):
        k1 = conform_cache_key("sha_A", 600.0)
        k2 = conform_cache_key("sha_B", 600.0)
        self.assertNotEqual(k1, k2)

    def test_different_duration_different_key(self):
        k1 = conform_cache_key("sha_A", 600.0)
        k2 = conform_cache_key("sha_A", 700.0)
        self.assertNotEqual(k1, k2)

    def test_bpm_changes_key(self):
        k1 = conform_cache_key("sha_A", 600.0, bpm=120.0)
        k2 = conform_cache_key("sha_A", 600.0, bpm=140.0)
        self.assertNotEqual(k1, k2)

    def test_no_bpm_vs_bpm(self):
        k1 = conform_cache_key("sha_A", 600.0)
        k2 = conform_cache_key("sha_A", 600.0, bpm=120.0)
        self.assertNotEqual(k1, k2)


# ---------------------------------------------------------------
# SoundtrackDecision
# ---------------------------------------------------------------

class TestSoundtrackDecision(unittest.TestCase):

    def test_default_disabled(self):
        d = SoundtrackDecision(enabled=False, skip_reason="test")
        self.assertFalse(d.enabled)
        self.assertEqual(d.skip_reason, "test")

    def test_to_dict_keys(self):
        d = SoundtrackDecision(enabled=True, track_id="t1")
        dd = d.to_dict()
        expected_keys = {
            "enabled", "track_id", "audio_path", "license_tier",
            "track_sha1", "bpm", "motif_group", "source",
            "target_duration_sec", "track_duration_sec", "loop_count",
            "loop_warning", "gain_db", "ducking", "fades",
            "fallback_plan", "chapter_gain_jitter", "safety_jitter",
            "ai_music_editor", "conform_cache_key", "tools_requested",
            "publish_policy", "skip_reason",
        }
        self.assertEqual(set(dd.keys()), expected_keys)

    def test_to_dict_values(self):
        d = SoundtrackDecision(enabled=True, track_id="track_01", license_tier="GREEN")
        dd = d.to_dict()
        self.assertTrue(dd["enabled"])
        self.assertEqual(dd["track_id"], "track_01")
        self.assertEqual(dd["license_tier"], "GREEN")


if __name__ == "__main__":
    unittest.main()
