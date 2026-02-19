#!/usr/bin/env python3
"""Tests for tools/security_check.py — file permission auditing utilities."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from security_check import check_permissions, format_mode


# ---------------------------------------------------------------
# check_permissions
# ---------------------------------------------------------------

class TestCheckPermissions(unittest.TestCase):

    def test_matching_permissions(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = f.name
        try:
            os.chmod(p, 0o600)
            ok, actual = check_permissions(p, 0o600)
            self.assertTrue(ok)
            self.assertEqual(actual, 0o600)
        finally:
            os.unlink(p)

    def test_mismatched_permissions(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = f.name
        try:
            os.chmod(p, 0o644)
            ok, actual = check_permissions(p, 0o600)
            self.assertFalse(ok)
            self.assertEqual(actual, 0o644)
        finally:
            os.unlink(p)

    def test_nonexistent_file(self):
        ok, actual = check_permissions("/nonexistent/file/path", 0o600)
        self.assertIsNone(ok)
        self.assertIsNone(actual)

    def test_directory_permissions(self):
        d = tempfile.mkdtemp()
        try:
            os.chmod(d, 0o700)
            ok, actual = check_permissions(d, 0o700)
            self.assertTrue(ok)
            self.assertEqual(actual, 0o700)
        finally:
            os.rmdir(d)

    def test_directory_too_permissive(self):
        d = tempfile.mkdtemp()
        try:
            os.chmod(d, 0o755)
            ok, actual = check_permissions(d, 0o700)
            self.assertFalse(ok)
            self.assertEqual(actual, 0o755)
        finally:
            os.chmod(d, 0o700)
            os.rmdir(d)


# ---------------------------------------------------------------
# format_mode
# ---------------------------------------------------------------

class TestFormatMode(unittest.TestCase):

    def test_none_returns_na(self):
        self.assertEqual(format_mode(None), "N/A")

    def test_600(self):
        result = format_mode(0o600)
        self.assertIn("0o600", result)
        self.assertIn("rw", result)

    def test_644(self):
        result = format_mode(0o644)
        self.assertIn("0o644", result)

    def test_700(self):
        result = format_mode(0o700)
        self.assertIn("0o700", result)
        self.assertIn("rwx", result)

    def test_755(self):
        result = format_mode(0o755)
        self.assertIn("0o755", result)


    def test_000(self):
        result = format_mode(0o000)
        self.assertIn("0o0", result)

    def test_777(self):
        result = format_mode(0o777)
        self.assertIn("0o777", result)
        self.assertIn("rwx", result)

    def test_400(self):
        result = format_mode(0o400)
        self.assertIn("0o400", result)


# ---------------------------------------------------------------
# check_permissions — additional edge cases
# ---------------------------------------------------------------

class TestCheckPermissionsEdgeCases(unittest.TestCase):

    def test_executable_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = f.name
        try:
            os.chmod(p, 0o755)
            ok, actual = check_permissions(p, 0o755)
            self.assertTrue(ok)
        finally:
            os.unlink(p)

    def test_readonly_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = f.name
        try:
            os.chmod(p, 0o400)
            ok, actual = check_permissions(p, 0o400)
            self.assertTrue(ok)
            self.assertEqual(actual, 0o400)
        finally:
            os.chmod(p, 0o600)  # restore writable to delete
            os.unlink(p)

    def test_world_readable(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = f.name
        try:
            os.chmod(p, 0o644)
            ok, _ = check_permissions(p, 0o644)
            self.assertTrue(ok)
        finally:
            os.unlink(p)

    def test_empty_path(self):
        ok, actual = check_permissions("", 0o600)
        self.assertIsNone(ok)
        self.assertIsNone(actual)


# ---------------------------------------------------------------
# format_mode edge cases
# ---------------------------------------------------------------

class TestFormatModeEdgeCases(unittest.TestCase):

    def test_octal_prefix_present(self):
        result = format_mode(0o644)
        self.assertTrue(result.startswith("0o"))

    def test_symbolic_has_dash(self):
        result = format_mode(0o600)
        # -rw------- pattern
        self.assertIn("-", result)

    def test_all_execute(self):
        result = format_mode(0o111)
        self.assertIn("x", result)

    def test_suid_bit(self):
        result = format_mode(0o4755)
        self.assertIn("s", result.lower())

    def test_returns_string(self):
        self.assertIsInstance(format_mode(0o644), str)
        self.assertIsInstance(format_mode(None), str)


# ---------------------------------------------------------------
# check_permissions — symlink + special cases
# ---------------------------------------------------------------

class TestCheckPermissionsSpecial(unittest.TestCase):

    def test_symlink_follows_target(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            target = f.name
        link = target + ".link"
        try:
            os.chmod(target, 0o644)
            os.symlink(target, link)
            ok, actual = check_permissions(link, 0o644)
            self.assertTrue(ok)
            self.assertEqual(actual, 0o644)
        finally:
            if os.path.exists(link):
                os.unlink(link)
            os.unlink(target)

    def test_returns_actual_mode_int(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = f.name
        try:
            os.chmod(p, 0o755)
            _, actual = check_permissions(p, 0o600)
            self.assertIsInstance(actual, int)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
