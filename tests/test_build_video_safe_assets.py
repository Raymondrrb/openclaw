#!/usr/bin/env python3
"""Tests for tools/build_video_safe_assets.py — video-safe image conversion utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from build_video_safe_assets import (
    IMAGE_EXTS,
    build_filter,
    ratio_label,
    video_safe_path,
)


# ---------------------------------------------------------------
# IMAGE_EXTS
# ---------------------------------------------------------------

class TestImageExts(unittest.TestCase):

    def test_contains_common_formats(self):
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            self.assertIn(ext, IMAGE_EXTS)

    def test_all_lowercase(self):
        for ext in IMAGE_EXTS:
            self.assertEqual(ext, ext.lower())


# ---------------------------------------------------------------
# ratio_label
# ---------------------------------------------------------------

class TestRatioLabel(unittest.TestCase):

    def test_portrait(self):
        self.assertEqual(ratio_label(600, 800), "portrait")

    def test_near_square(self):
        self.assertEqual(ratio_label(1000, 1000), "near-square")

    def test_landscape_16x9(self):
        self.assertEqual(ratio_label(1920, 1080), "landscape")

    def test_ultra_wide(self):
        self.assertEqual(ratio_label(2560, 1080), "ultra-wide")

    def test_zero_width(self):
        self.assertEqual(ratio_label(0, 100), "unknown")

    def test_zero_height(self):
        self.assertEqual(ratio_label(100, 0), "unknown")

    def test_both_zero(self):
        self.assertEqual(ratio_label(0, 0), "unknown")

    def test_negative_values(self):
        self.assertEqual(ratio_label(-100, 200), "unknown")

    def test_boundary_portrait_near_square(self):
        # ratio < 0.9 is portrait, >= 0.9 is near-square
        # 89/100 = 0.89 → portrait
        self.assertEqual(ratio_label(89, 100), "portrait")
        # 90/100 = 0.90 → near-square
        self.assertEqual(ratio_label(90, 100), "near-square")

    def test_boundary_near_square_landscape(self):
        # ratio < 1.5 is near-square, >= 1.5 is landscape
        # 149/100 = 1.49 → near-square
        self.assertEqual(ratio_label(149, 100), "near-square")
        # 150/100 = 1.5 → landscape
        self.assertEqual(ratio_label(150, 100), "landscape")

    def test_boundary_landscape_ultra_wide(self):
        # ratio < 2.0 is landscape, >= 2.0 is ultra-wide
        # 199/100 = 1.99 → landscape
        self.assertEqual(ratio_label(199, 100), "landscape")
        # 200/100 = 2.0 → ultra-wide
        self.assertEqual(ratio_label(200, 100), "ultra-wide")


# ---------------------------------------------------------------
# build_filter
# ---------------------------------------------------------------

class TestBuildFilter(unittest.TestCase):

    def test_default_1920x1080(self):
        f = build_filter(1920, 1080)
        # Background: 1920x1080
        self.assertIn("scale=1920:1080", f)
        self.assertIn("crop=1920:1080", f)
        self.assertIn("boxblur=28:8", f)
        # Foreground: 78% of 1920x1080 = 1497x842
        fg_w = int(1920 * 0.78)
        fg_h = int(1080 * 0.78)
        self.assertIn(f"scale={fg_w}:{fg_h}", f)
        self.assertIn("overlay=(W-w)/2:(H-h)/2", f)

    def test_custom_resolution(self):
        f = build_filter(3840, 2160)
        self.assertIn("scale=3840:2160", f)
        fg_w = int(3840 * 0.78)
        fg_h = int(2160 * 0.78)
        self.assertIn(f"scale={fg_w}:{fg_h}", f)

    def test_stream_labels(self):
        f = build_filter(1920, 1080)
        self.assertIn("[bg]", f)
        self.assertIn("[fg]", f)
        self.assertIn("[out]", f)

    def test_small_resolution(self):
        f = build_filter(640, 480)
        fg_w = int(640 * 0.78)
        fg_h = int(480 * 0.78)
        self.assertIn(f"scale={fg_w}:{fg_h}", f)


# ---------------------------------------------------------------
# video_safe_path
# ---------------------------------------------------------------

class TestVideoSafePath(unittest.TestCase):

    def test_basic_path(self):
        src = Path("/project/assets/products/p01/img.jpg")
        assets = Path("/project/assets")
        result = video_safe_path(src, assets)
        self.assertEqual(result, Path("/project/assets/video_safe/products/p01/img_16x9.jpg"))

    def test_preserves_stem(self):
        src = Path("/a/b/photo.png")
        assets = Path("/a/b")
        result = video_safe_path(src, assets)
        self.assertEqual(result.name, "photo_16x9.jpg")

    def test_nested_path(self):
        src = Path("/assets/deep/nested/dir/image.webp")
        assets = Path("/assets")
        result = video_safe_path(src, assets)
        self.assertEqual(result, Path("/assets/video_safe/deep/nested/dir/image_16x9.jpg"))

    def test_root_level(self):
        src = Path("/assets/main.png")
        assets = Path("/assets")
        result = video_safe_path(src, assets)
        self.assertEqual(result, Path("/assets/video_safe/main_16x9.jpg"))


# ---------------------------------------------------------------
# ratio_label edge cases
# ---------------------------------------------------------------

class TestRatioLabelEdgeCases(unittest.TestCase):

    def test_1x1_square(self):
        self.assertEqual(ratio_label(1, 1), "near-square")

    def test_very_wide(self):
        self.assertEqual(ratio_label(10000, 100), "ultra-wide")

    def test_very_tall(self):
        self.assertEqual(ratio_label(100, 10000), "portrait")

    def test_large_equal_dimensions(self):
        self.assertEqual(ratio_label(4096, 4096), "near-square")

    def test_one_negative_one_positive(self):
        self.assertEqual(ratio_label(-100, 100), "unknown")

    def test_float_like_boundary(self):
        # 900/1000 = 0.9 exactly → near-square
        self.assertEqual(ratio_label(900, 1000), "near-square")


# ---------------------------------------------------------------
# build_filter edge cases
# ---------------------------------------------------------------

class TestBuildFilterEdgeCases(unittest.TestCase):

    def test_square_resolution(self):
        f = build_filter(1080, 1080)
        self.assertIn("scale=1080:1080", f)
        fg_w = int(1080 * 0.78)
        fg_h = int(1080 * 0.78)
        self.assertIn(f"scale={fg_w}:{fg_h}", f)

    def test_4k_resolution(self):
        f = build_filter(3840, 2160)
        self.assertIn("crop=3840:2160", f)

    def test_filter_has_required_parts(self):
        f = build_filter(1920, 1080)
        # Must have background, foreground, and overlay
        self.assertIn("boxblur", f)
        self.assertIn("overlay", f)
        self.assertIn("[bg]", f)
        self.assertIn("[fg]", f)


# ---------------------------------------------------------------
# video_safe_path edge cases
# ---------------------------------------------------------------

class TestVideoSafePathEdgeCases(unittest.TestCase):

    def test_webp_becomes_jpg(self):
        src = Path("/assets/img.webp")
        result = video_safe_path(src, Path("/assets"))
        self.assertEqual(result.suffix, ".jpg")

    def test_png_becomes_jpg(self):
        src = Path("/assets/img.png")
        result = video_safe_path(src, Path("/assets"))
        self.assertEqual(result.suffix, ".jpg")

    def test_jpg_stays_jpg(self):
        src = Path("/assets/img.jpg")
        result = video_safe_path(src, Path("/assets"))
        self.assertEqual(result.suffix, ".jpg")

    def test_16x9_suffix(self):
        src = Path("/assets/photo.png")
        result = video_safe_path(src, Path("/assets"))
        self.assertTrue(result.stem.endswith("_16x9"))

    def test_deeply_nested(self):
        src = Path("/assets/a/b/c/d/e/img.png")
        result = video_safe_path(src, Path("/assets"))
        self.assertIn("video_safe", str(result))
        self.assertEqual(result.name, "img_16x9.jpg")


if __name__ == "__main__":
    unittest.main()
