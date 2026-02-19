#!/usr/bin/env python3
"""Tests for rayvault/resolve_bridge.py — pure functions and dataclasses.

Note: Tests do NOT require a running DaVinci Resolve instance.
Only pure utility functions, dataclasses, and filesystem discovery are tested.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rayvault.resolve_bridge import (
    KENBURNS_PATTERNS,
    ResolveCapabilities,
    ResolveBridge,
    _format_version,
    discover_fusion_templates,
    discover_luts,
    kenburns_pattern_for_segment,
)


# ---------------------------------------------------------------
# _format_version
# ---------------------------------------------------------------

class TestFormatVersion(unittest.TestCase):

    def test_list_version(self):
        ver = [20, 3, 1, 6, ""]
        self.assertEqual(_format_version(ver), "20.3.1.6")

    def test_list_no_empty(self):
        ver = [20, 3, 1]
        self.assertEqual(_format_version(ver), "20.3.1")

    def test_list_with_none(self):
        ver = [20, 3, None, ""]
        self.assertEqual(_format_version(ver), "20.3")

    def test_tuple_version(self):
        ver = (20, 3, 1)
        self.assertEqual(_format_version(ver), "20.3.1")

    def test_string_passthrough(self):
        self.assertEqual(_format_version("20.3.1"), "20.3.1")

    def test_empty_list(self):
        self.assertEqual(_format_version([]), "unknown")

    def test_all_empty(self):
        self.assertEqual(_format_version(["", "", ""]), "unknown")

    def test_integer(self):
        self.assertEqual(_format_version(20), "20")


# ---------------------------------------------------------------
# ResolveCapabilities
# ---------------------------------------------------------------

class TestResolveCapabilities(unittest.TestCase):

    def test_defaults(self):
        caps = ResolveCapabilities()
        self.assertFalse(caps.scripting_available)
        self.assertFalse(caps.resolve_connected)
        self.assertFalse(caps.can_create_project)
        self.assertFalse(caps.can_create_timeline)
        self.assertFalse(caps.can_import_media)
        self.assertFalse(caps.can_set_project_settings)
        self.assertFalse(caps.can_set_render_settings)
        self.assertFalse(caps.can_start_render)
        self.assertFalse(caps.can_get_render_status)
        self.assertFalse(caps.can_add_track)
        self.assertEqual(caps.resolve_version, "unknown")
        self.assertEqual(caps.resolve_name, "unknown")
        self.assertEqual(caps.available_luts, [])
        self.assertEqual(caps.fusion_templates, [])

    def test_to_dict_keys(self):
        caps = ResolveCapabilities()
        d = caps.to_dict()
        expected_keys = {
            "scripting_available", "resolve_connected",
            "can_create_project", "can_create_timeline",
            "can_import_media", "can_set_project_settings",
            "can_set_render_settings", "can_start_render",
            "can_get_render_status", "can_add_track",
            "resolve_version", "resolve_name",
            "available_luts", "fusion_templates",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_values(self):
        caps = ResolveCapabilities(
            scripting_available=True,
            resolve_connected=True,
            resolve_version="20.3.1.6",
            resolve_name="DaVinci Resolve Studio",
        )
        d = caps.to_dict()
        self.assertTrue(d["scripting_available"])
        self.assertTrue(d["resolve_connected"])
        self.assertEqual(d["resolve_version"], "20.3.1.6")


# ---------------------------------------------------------------
# KENBURNS_PATTERNS
# ---------------------------------------------------------------

class TestKenburnsPatterns(unittest.TestCase):

    def test_count(self):
        self.assertEqual(len(KENBURNS_PATTERNS), 6)

    def test_all_have_required_keys(self):
        for p in KENBURNS_PATTERNS:
            self.assertIn("name", p)
            self.assertIn("zoom", p)
            self.assertIn("pan_x", p)
            self.assertIn("pan_y", p)

    def test_all_tuples_length_2(self):
        for p in KENBURNS_PATTERNS:
            self.assertEqual(len(p["zoom"]), 2)
            self.assertEqual(len(p["pan_x"]), 2)
            self.assertEqual(len(p["pan_y"]), 2)

    def test_unique_names(self):
        names = [p["name"] for p in KENBURNS_PATTERNS]
        self.assertEqual(len(names), len(set(names)))


# ---------------------------------------------------------------
# kenburns_pattern_for_segment
# ---------------------------------------------------------------

class TestKenburnsPatternForSegment(unittest.TestCase):

    def test_deterministic(self):
        p1 = kenburns_pattern_for_segment("RUN_A", "B000ASIN1", 1)
        p2 = kenburns_pattern_for_segment("RUN_A", "B000ASIN1", 1)
        self.assertEqual(p1, p2)

    def test_different_runs(self):
        p1 = kenburns_pattern_for_segment("RUN_A", "B000ASIN1", 1)
        p2 = kenburns_pattern_for_segment("RUN_B", "B000ASIN1", 1)
        # Not guaranteed different for all inputs, but verify format
        self.assertIn("name", p1)
        self.assertIn("name", p2)

    def test_different_ranks(self):
        p1 = kenburns_pattern_for_segment("RUN_A", "B000ASIN1", 1)
        p2 = kenburns_pattern_for_segment("RUN_A", "B000ASIN1", 2)
        # Format check
        self.assertIn("zoom", p1)
        self.assertIn("zoom", p2)

    def test_returns_valid_pattern(self):
        p = kenburns_pattern_for_segment("RUN_X", "B001ABC", 3)
        self.assertIn(p, KENBURNS_PATTERNS)


# ---------------------------------------------------------------
# discover_luts (with test dir)
# ---------------------------------------------------------------

class TestDiscoverLuts(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.lut_dir = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_dir(self):
        luts = discover_luts(extra_dirs=[str(self.lut_dir)])
        # May find system LUTs; at least no crash
        self.assertIsInstance(luts, list)

    def test_finds_cube_files(self):
        sub = self.lut_dir / "_rayvault_test_luts_"
        sub.mkdir()
        (sub / "Vintage.cube").write_text("LUT_3D_SIZE 33")
        (sub / "Warm.cube").write_text("LUT_3D_SIZE 33")
        luts = discover_luts(extra_dirs=[str(self.lut_dir)])
        found = [l for l in luts if "_rayvault_test_luts_" in l]
        self.assertEqual(len(found), 2)

    def test_finds_3dl_files(self):
        (self.lut_dir / "test.3dl").write_text("3dl data")
        luts = discover_luts(extra_dirs=[str(self.lut_dir)])
        found = [l for l in luts if "test.3dl" in l]
        self.assertEqual(len(found), 1)

    def test_sorted(self):
        (self.lut_dir / "z_last.cube").write_text("data")
        (self.lut_dir / "a_first.cube").write_text("data")
        luts = discover_luts(extra_dirs=[str(self.lut_dir)])
        # Our test LUTs should be sorted
        test_luts = [l for l in luts if l in ("z_last.cube", "a_first.cube")]
        if len(test_luts) == 2:
            self.assertEqual(test_luts[0], "a_first.cube")

    def test_no_duplicates(self):
        (self.lut_dir / "test.cube").write_text("data")
        luts = discover_luts(extra_dirs=[str(self.lut_dir), str(self.lut_dir)])
        count = luts.count("test.cube")
        self.assertEqual(count, 1)


# ---------------------------------------------------------------
# discover_fusion_templates (with test dir)
# ---------------------------------------------------------------

class TestDiscoverFusionTemplates(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.tmpl_dir = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_dir(self):
        templates = discover_fusion_templates(extra_dirs=[str(self.tmpl_dir)])
        self.assertIsInstance(templates, list)

    def test_finds_drfx(self):
        (self.tmpl_dir / "LowerThirds.drfx").write_text("template data")
        templates = discover_fusion_templates(extra_dirs=[str(self.tmpl_dir)])
        found = [t for t in templates if "LowerThirds.drfx" in t]
        self.assertEqual(len(found), 1)

    def test_finds_setting(self):
        (self.tmpl_dir / "Effect.setting").write_text("setting data")
        templates = discover_fusion_templates(extra_dirs=[str(self.tmpl_dir)])
        found = [t for t in templates if "Effect.setting" in t]
        self.assertEqual(len(found), 1)

    def test_sorted(self):
        (self.tmpl_dir / "z.drfx").write_text("data")
        (self.tmpl_dir / "a.drfx").write_text("data")
        templates = discover_fusion_templates(extra_dirs=[str(self.tmpl_dir)])
        test = [t for t in templates if t in ("z.drfx", "a.drfx")]
        if len(test) == 2:
            self.assertEqual(test[0], "a.drfx")


# ---------------------------------------------------------------
# ResolveBridge (construction only, no connect)
# ---------------------------------------------------------------

class TestResolveBridgeInit(unittest.TestCase):

    def test_initial_state(self):
        bridge = ResolveBridge()
        self.assertFalse(bridge.connected)
        self.assertIsNone(bridge.project)
        self.assertIsNone(bridge.media_pool)
        self.assertIsNone(bridge.timeline)

    def test_initial_caps(self):
        bridge = ResolveBridge()
        self.assertFalse(bridge.caps.scripting_available)
        self.assertFalse(bridge.caps.resolve_connected)
        self.assertEqual(bridge.caps.resolve_version, "unknown")

    def test_disconnect_clears_state(self):
        bridge = ResolveBridge()
        bridge.disconnect()
        self.assertFalse(bridge.connected)
        self.assertIsNone(bridge.project)
        self.assertIsNone(bridge.media_pool)
        self.assertIsNone(bridge.timeline)


if __name__ == "__main__":
    unittest.main()
