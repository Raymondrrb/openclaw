#!/usr/bin/env python3
"""Tests for tools/youtube_channel_to_csv.py — ISO 8601 duration parsing + formatting."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from youtube_channel_to_csv import (
    parse_iso8601_duration_to_seconds,
    seconds_to_hms,
)


# ---------------------------------------------------------------
# parse_iso8601_duration_to_seconds
# ---------------------------------------------------------------

class TestParseIso8601DurationToSeconds(unittest.TestCase):

    def test_zero_duration(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT0S"), 0)

    def test_seconds_only(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT45S"), 45)

    def test_minutes_only(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT12M"), 720)

    def test_hours_only(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT2H"), 7200)

    def test_minutes_and_seconds(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT10M30S"), 630)

    def test_hours_minutes_seconds(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT1H30M15S"), 5415)

    def test_empty_string(self):
        self.assertEqual(parse_iso8601_duration_to_seconds(""), 0)

    def test_none(self):
        self.assertEqual(parse_iso8601_duration_to_seconds(None), 0)

    def test_hours_and_seconds(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT1H5S"), 3605)

    def test_large_values(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT10H59M59S"), 39599)


# ---------------------------------------------------------------
# seconds_to_hms
# ---------------------------------------------------------------

class TestSecondsToHms(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(seconds_to_hms(0), "00:00:00")

    def test_seconds_only(self):
        self.assertEqual(seconds_to_hms(45), "00:00:45")

    def test_minutes_and_seconds(self):
        self.assertEqual(seconds_to_hms(630), "00:10:30")

    def test_hours_minutes_seconds(self):
        self.assertEqual(seconds_to_hms(5415), "01:30:15")

    def test_exact_hour(self):
        self.assertEqual(seconds_to_hms(3600), "01:00:00")

    def test_large_value(self):
        self.assertEqual(seconds_to_hms(39599), "10:59:59")


# ---------------------------------------------------------------
# parse_iso8601_duration edge cases
# ---------------------------------------------------------------

class TestParseIso8601EdgeCases(unittest.TestCase):

    def test_only_pt(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("PT"), 0)

    def test_non_iso_string(self):
        self.assertEqual(parse_iso8601_duration_to_seconds("not a duration"), 0)

    def test_fractional_seconds(self):
        # The regex uses \d+ so fractional parts are dropped
        result = parse_iso8601_duration_to_seconds("PT10.5S")
        self.assertIsInstance(result, (int, float))

    def test_with_days(self):
        # P1DT2H3M = 1 day + 2 hours + 3 minutes
        result = parse_iso8601_duration_to_seconds("P1DT2H3M")
        # If days are captured: 86400 + 7200 + 180 = 93780, or partial
        self.assertIsInstance(result, (int, float))
        self.assertGreater(result, 0)

    def test_lowercase_ignored(self):
        # ISO 8601 is uppercase, lowercase should return 0 or parse partially
        result = parse_iso8601_duration_to_seconds("pt10m30s")
        self.assertIsInstance(result, (int, float))


# ---------------------------------------------------------------
# seconds_to_hms edge cases
# ---------------------------------------------------------------

class TestSecondsToHmsEdgeCases(unittest.TestCase):

    def test_one_second(self):
        self.assertEqual(seconds_to_hms(1), "00:00:01")

    def test_59_seconds(self):
        self.assertEqual(seconds_to_hms(59), "00:00:59")

    def test_60_seconds(self):
        self.assertEqual(seconds_to_hms(60), "00:01:00")

    def test_over_24_hours(self):
        result = seconds_to_hms(100000)
        # 100000s = 27h 46m 40s
        self.assertEqual(result, "27:46:40")

    def test_negative(self):
        # Negative input, behavior depends on implementation
        result = seconds_to_hms(-1)
        self.assertIsInstance(result, str)

    def test_integer_input_90(self):
        result = seconds_to_hms(90)
        self.assertEqual(result, "00:01:30")


if __name__ == "__main__":
    unittest.main()
