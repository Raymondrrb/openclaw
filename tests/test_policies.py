#!/usr/bin/env python3
"""Tests for rayvault/policies.py — policy constants and motion_group_for_preset."""

from __future__ import annotations

import unittest

from rayvault.policies import (
    AUDIO_SAMPLE_RATE,
    BEAT_MAX_SEC,
    BEAT_MIN_SEC,
    BLACK_FRAME_MIN_RATIO,
    BLACK_LUMA_THRESHOLD,
    BUS_MASTER_NAME,
    BUS_MUSIC_NAME,
    BUS_SFX_NAME,
    BUS_VO_NAME,
    CLIPPING_MAX_CONSECUTIVE_SAMPLES,
    CLIPPING_PEAK_RATIO,
    CTA_SEC_RANGE,
    DUCKING_MIN_REDUCTION_RATIO,
    DURATION_TOLERANCE_SEC,
    FIDELITY_SCORE_MIN,
    FILLER_CHAPTER_SEC_RANGE,
    INTRO_SEC_RANGE,
    LUFS_TARGET,
    LUFS_TOLERANCE,
    MAX_RETRY,
    MAX_STATIC_SECONDS,
    MIN_CACHE_FREE_GB,
    MIN_MOTION_POS_FRAC,
    MIN_MOTION_SCALE,
    MIN_SEGMENT_TYPE_VARIETY,
    MIN_TRUTH_PRODUCTS,
    MOTION_GROUPS,
    MOTION_MAX_CONSECUTIVE_SAME,
    OUTPUT_CRF,
    OUTPUT_FPS,
    OUTPUT_H,
    OUTPUT_PRESET,
    OUTPUT_W,
    PRODUCT_BLOCK_SEC_RANGE,
    RECAP_SEC_RANGE,
    RED_CHANNEL_DOMINANCE,
    RENDER_POLL_SEC,
    RENDER_TIMEOUT_SEC,
    SAFETY_JITTER_PITCH_RATIO,
    SAFETY_JITTER_TEMPO_RATIO,
    SOUNDTRACK_CROSSFADE_IN_SEC,
    SOUNDTRACK_CROSSFADE_OUT_SEC,
    SOUNDTRACK_DUCK_AMOUNT_DB,
    SOUNDTRACK_DUCK_ATTACK_MS,
    SOUNDTRACK_DUCK_RELEASE_MS,
    SOUNDTRACK_LICENSE_TIERS,
    SOUNDTRACK_LOOP_CROSSFADE_SEC,
    SOUNDTRACK_MAX_LOOP_RATIO,
    SOUNDTRACK_MIN_VIDEO_SEC,
    SOUNDTRACK_MUSIC_GAIN_DB,
    SOUNDTRACK_VALID_SOURCES,
    STALL_TIMEOUT_SEC,
    TARGET_MAX_SEC,
    TARGET_MIN_SEC,
    TRUE_PEAK_MAX,
    TTS_DEFAULT_PROVIDER,
    TTS_KNOWN_PROVIDERS,
    TTS_MAX_SEGMENT_CHARS,
    TTS_NORMALIZE_LUFS,
    TTS_WPM_ESTIMATE,
    motion_group_for_preset,
)


# ---------------------------------------------------------------
# motion_group_for_preset
# ---------------------------------------------------------------

class TestMotionGroupForPreset(unittest.TestCase):

    def test_zoom_in_center(self):
        self.assertEqual(motion_group_for_preset("zoom_in_center"), "zoom_in")

    def test_slow_push_in(self):
        self.assertEqual(motion_group_for_preset("slow_push_in"), "zoom_in")

    def test_push_in(self):
        self.assertEqual(motion_group_for_preset("push_in"), "zoom_in")

    def test_zoom_out_center(self):
        self.assertEqual(motion_group_for_preset("zoom_out_center"), "zoom_out")

    def test_pull_out(self):
        self.assertEqual(motion_group_for_preset("pull_out"), "zoom_out")

    def test_pan_left_to_right(self):
        self.assertEqual(motion_group_for_preset("pan_left_to_right"), "pan_lr")

    def test_pan_right_to_left(self):
        self.assertEqual(motion_group_for_preset("pan_right_to_left"), "pan_rl")

    def test_slow_push_up(self):
        self.assertEqual(motion_group_for_preset("slow_push_up"), "pan_ud")

    def test_push_up(self):
        self.assertEqual(motion_group_for_preset("push_up"), "pan_ud")

    def test_diagonal_drift(self):
        self.assertEqual(motion_group_for_preset("diagonal_drift"), "diagonal")

    def test_unknown_preset_returns_other(self):
        self.assertEqual(motion_group_for_preset("nonexistent_preset"), "other")

    def test_empty_string_returns_other(self):
        self.assertEqual(motion_group_for_preset(""), "other")

    def test_all_presets_covered(self):
        """Every preset in MOTION_GROUPS resolves to a non-other group."""
        for group, presets in MOTION_GROUPS.items():
            for p in presets:
                self.assertEqual(motion_group_for_preset(p), group,
                                 f"Preset {p!r} should be in group {group!r}")


# ---------------------------------------------------------------
# MOTION_GROUPS structure
# ---------------------------------------------------------------

class TestMotionGroups(unittest.TestCase):

    def test_is_dict(self):
        self.assertIsInstance(MOTION_GROUPS, dict)

    def test_all_values_are_sets(self):
        for group, presets in MOTION_GROUPS.items():
            self.assertIsInstance(presets, set, f"{group} should be a set")

    def test_no_empty_groups(self):
        for group, presets in MOTION_GROUPS.items():
            self.assertGreater(len(presets), 0, f"{group} should not be empty")

    def test_expected_groups(self):
        expected = {"zoom_in", "zoom_out", "pan_lr", "pan_rl", "pan_ud", "diagonal"}
        self.assertEqual(set(MOTION_GROUPS.keys()), expected)

    def test_no_duplicate_presets_across_groups(self):
        """Each preset should only appear in one group."""
        seen = {}
        for group, presets in MOTION_GROUPS.items():
            for p in presets:
                self.assertNotIn(p, seen,
                                 f"Preset {p!r} in both {seen.get(p)!r} and {group!r}")
                seen[p] = group


# ---------------------------------------------------------------
# Duration targets
# ---------------------------------------------------------------

class TestDurationConstants(unittest.TestCase):

    def test_min_less_than_max(self):
        self.assertLess(TARGET_MIN_SEC, TARGET_MAX_SEC)

    def test_min_is_8_minutes(self):
        self.assertEqual(TARGET_MIN_SEC, 480)

    def test_max_is_12_minutes(self):
        self.assertEqual(TARGET_MAX_SEC, 720)

    def test_tolerance_positive(self):
        self.assertGreater(DURATION_TOLERANCE_SEC, 0)


# ---------------------------------------------------------------
# Pacing constants
# ---------------------------------------------------------------

class TestPacingConstants(unittest.TestCase):

    def test_max_static_positive(self):
        self.assertGreater(MAX_STATIC_SECONDS, 0)

    def test_beat_min_less_than_max(self):
        self.assertLess(BEAT_MIN_SEC, BEAT_MAX_SEC)

    def test_min_variety_at_least_2(self):
        self.assertGreaterEqual(MIN_SEGMENT_TYPE_VARIETY, 2)

    def test_motion_scale_positive(self):
        self.assertGreater(MIN_MOTION_SCALE, 0)

    def test_motion_pos_frac_positive(self):
        self.assertGreater(MIN_MOTION_POS_FRAC, 0)

    def test_consecutive_same_at_least_1(self):
        self.assertGreaterEqual(MOTION_MAX_CONSECUTIVE_SAME, 1)


# ---------------------------------------------------------------
# Chapter duration ranges
# ---------------------------------------------------------------

class TestChapterRanges(unittest.TestCase):

    def _check_range(self, r, label):
        self.assertIsInstance(r, tuple, f"{label} should be a tuple")
        self.assertEqual(len(r), 2, f"{label} should have 2 elements")
        self.assertLess(r[0], r[1], f"{label} min should be < max")
        self.assertGreater(r[0], 0, f"{label} min should be > 0")

    def test_intro_range(self):
        self._check_range(INTRO_SEC_RANGE, "INTRO_SEC_RANGE")

    def test_cta_range(self):
        self._check_range(CTA_SEC_RANGE, "CTA_SEC_RANGE")

    def test_recap_range(self):
        self._check_range(RECAP_SEC_RANGE, "RECAP_SEC_RANGE")

    def test_product_block_range(self):
        self._check_range(PRODUCT_BLOCK_SEC_RANGE, "PRODUCT_BLOCK_SEC_RANGE")

    def test_filler_range(self):
        self._check_range(FILLER_CHAPTER_SEC_RANGE, "FILLER_CHAPTER_SEC_RANGE")


# ---------------------------------------------------------------
# Audio / loudness
# ---------------------------------------------------------------

class TestAudioConstants(unittest.TestCase):

    def test_lufs_target_negative(self):
        self.assertLess(LUFS_TARGET, 0)

    def test_lufs_tolerance_positive(self):
        self.assertGreater(LUFS_TOLERANCE, 0)

    def test_true_peak_negative(self):
        self.assertLess(TRUE_PEAK_MAX, 0)

    def test_sample_rate(self):
        self.assertEqual(AUDIO_SAMPLE_RATE, 48000)


# ---------------------------------------------------------------
# TTS constants
# ---------------------------------------------------------------

class TestTTSConstants(unittest.TestCase):

    def test_default_provider_in_known(self):
        self.assertIn(TTS_DEFAULT_PROVIDER, TTS_KNOWN_PROVIDERS)

    def test_known_providers_is_set(self):
        self.assertIsInstance(TTS_KNOWN_PROVIDERS, set)

    def test_max_segment_chars_positive(self):
        self.assertGreater(TTS_MAX_SEGMENT_CHARS, 0)

    def test_wpm_reasonable(self):
        self.assertGreater(TTS_WPM_ESTIMATE, 100)
        self.assertLess(TTS_WPM_ESTIMATE, 300)

    def test_normalize_lufs_negative(self):
        self.assertLess(TTS_NORMALIZE_LUFS, 0)


# ---------------------------------------------------------------
# Render output
# ---------------------------------------------------------------

class TestRenderConstants(unittest.TestCase):

    def test_resolution_1080p(self):
        self.assertEqual(OUTPUT_W, 1920)
        self.assertEqual(OUTPUT_H, 1080)

    def test_fps_30(self):
        self.assertEqual(OUTPUT_FPS, 30)

    def test_crf_reasonable(self):
        self.assertGreater(OUTPUT_CRF, 0)
        self.assertLess(OUTPUT_CRF, 51)

    def test_preset_is_string(self):
        self.assertIsInstance(OUTPUT_PRESET, str)


# ---------------------------------------------------------------
# Soundtrack constants
# ---------------------------------------------------------------

class TestSoundtrackConstants(unittest.TestCase):

    def test_music_gain_negative(self):
        self.assertLess(SOUNDTRACK_MUSIC_GAIN_DB, 0)

    def test_duck_amount_positive(self):
        self.assertGreater(SOUNDTRACK_DUCK_AMOUNT_DB, 0)

    def test_duck_attack_positive(self):
        self.assertGreater(SOUNDTRACK_DUCK_ATTACK_MS, 0)

    def test_duck_release_positive(self):
        self.assertGreater(SOUNDTRACK_DUCK_RELEASE_MS, 0)

    def test_crossfade_in_positive(self):
        self.assertGreater(SOUNDTRACK_CROSSFADE_IN_SEC, 0)

    def test_crossfade_out_positive(self):
        self.assertGreater(SOUNDTRACK_CROSSFADE_OUT_SEC, 0)

    def test_loop_crossfade_positive(self):
        self.assertGreater(SOUNDTRACK_LOOP_CROSSFADE_SEC, 0)

    def test_max_loop_ratio_at_least_1(self):
        self.assertGreaterEqual(SOUNDTRACK_MAX_LOOP_RATIO, 1.0)

    def test_min_video_sec_positive(self):
        self.assertGreater(SOUNDTRACK_MIN_VIDEO_SEC, 0)

    def test_license_tiers_is_set(self):
        self.assertIsInstance(SOUNDTRACK_LICENSE_TIERS, set)
        self.assertIn("GREEN", SOUNDTRACK_LICENSE_TIERS)
        self.assertIn("AMBER", SOUNDTRACK_LICENSE_TIERS)
        self.assertIn("RED", SOUNDTRACK_LICENSE_TIERS)

    def test_valid_sources_is_set(self):
        self.assertIsInstance(SOUNDTRACK_VALID_SOURCES, set)
        self.assertIn("artlist", SOUNDTRACK_VALID_SOURCES)
        self.assertIn("suno", SOUNDTRACK_VALID_SOURCES)


# ---------------------------------------------------------------
# Black frame / media offline
# ---------------------------------------------------------------

class TestBlackFrameConstants(unittest.TestCase):

    def test_luma_threshold_in_range(self):
        self.assertGreater(BLACK_LUMA_THRESHOLD, 0)
        self.assertLess(BLACK_LUMA_THRESHOLD, 255)

    def test_min_ratio_in_range(self):
        self.assertGreater(BLACK_FRAME_MIN_RATIO, 0)
        self.assertLessEqual(BLACK_FRAME_MIN_RATIO, 1.0)

    def test_red_dominance_in_range(self):
        self.assertGreater(RED_CHANNEL_DOMINANCE, 0)
        self.assertLessEqual(RED_CHANNEL_DOMINANCE, 1.0)


# ---------------------------------------------------------------
# Render watchdog
# ---------------------------------------------------------------

class TestWatchdogConstants(unittest.TestCase):

    def test_stall_timeout_positive(self):
        self.assertGreater(STALL_TIMEOUT_SEC, 0)

    def test_poll_less_than_stall(self):
        self.assertLess(RENDER_POLL_SEC, STALL_TIMEOUT_SEC)

    def test_render_timeout_large(self):
        self.assertGreaterEqual(RENDER_TIMEOUT_SEC, 3600)

    def test_max_retry_non_negative(self):
        self.assertGreaterEqual(MAX_RETRY, 0)


# ---------------------------------------------------------------
# Bus names
# ---------------------------------------------------------------

class TestBusNames(unittest.TestCase):

    def test_vo_name(self):
        self.assertEqual(BUS_VO_NAME, "BUS_VO")

    def test_music_name(self):
        self.assertEqual(BUS_MUSIC_NAME, "BUS_MUSIC")

    def test_sfx_name(self):
        self.assertEqual(BUS_SFX_NAME, "BUS_SFX")

    def test_master_name(self):
        self.assertEqual(BUS_MASTER_NAME, "BUS_MASTER")


# ---------------------------------------------------------------
# Safety jitter
# ---------------------------------------------------------------

class TestSafetyJitter(unittest.TestCase):

    def test_pitch_ratio_near_1(self):
        self.assertAlmostEqual(SAFETY_JITTER_PITCH_RATIO, 1.0, places=2)
        self.assertNotEqual(SAFETY_JITTER_PITCH_RATIO, 1.0)

    def test_tempo_ratio_near_1(self):
        self.assertAlmostEqual(SAFETY_JITTER_TEMPO_RATIO, 1.0, places=2)
        self.assertNotEqual(SAFETY_JITTER_TEMPO_RATIO, 1.0)


# ---------------------------------------------------------------
# Clipping / ducking thresholds
# ---------------------------------------------------------------

class TestClippingDuckingConstants(unittest.TestCase):

    def test_clipping_peak_ratio_near_1(self):
        self.assertGreater(CLIPPING_PEAK_RATIO, 0.9)
        self.assertLessEqual(CLIPPING_PEAK_RATIO, 1.0)

    def test_clipping_consecutive_positive(self):
        self.assertGreater(CLIPPING_MAX_CONSECUTIVE_SAMPLES, 0)

    def test_ducking_min_reduction_in_range(self):
        self.assertGreater(DUCKING_MIN_REDUCTION_RATIO, 0)
        self.assertLessEqual(DUCKING_MIN_REDUCTION_RATIO, 1.0)


# ---------------------------------------------------------------
# Disk / product truth
# ---------------------------------------------------------------

class TestMiscConstants(unittest.TestCase):

    def test_min_cache_free_positive(self):
        self.assertGreater(MIN_CACHE_FREE_GB, 0)

    def test_min_truth_products_positive(self):
        self.assertGreater(MIN_TRUTH_PRODUCTS, 0)

    def test_fidelity_score_range(self):
        self.assertGreater(FIDELITY_SCORE_MIN, 0)
        self.assertLessEqual(FIDELITY_SCORE_MIN, 100)


if __name__ == "__main__":
    unittest.main()
