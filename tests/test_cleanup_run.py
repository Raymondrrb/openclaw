#!/usr/bin/env python3
"""Tests for rayvault/cleanup_run.py — selective purge of heavy assets."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.cleanup_run import (
    du_bytes,
    safe_rmtree,
    safe_unlink,
    utc_now_iso,
)


# ---------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------

class TestUtcNowIso(unittest.TestCase):

    def test_returns_string(self):
        self.assertIsInstance(utc_now_iso(), str)

    def test_ends_with_z(self):
        self.assertTrue(utc_now_iso().endswith("Z"))


class TestDuBytes(unittest.TestCase):

    def test_nonexistent(self):
        self.assertEqual(du_bytes(Path("/nonexistent")), 0)

    def test_single_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello")
            p = Path(f.name)
        try:
            self.assertEqual(du_bytes(p), 5)
        finally:
            p.unlink()

    def test_directory(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_bytes(b"12345")
            (Path(d) / "b.txt").write_bytes(b"67890")
            self.assertEqual(du_bytes(Path(d)), 10)


class TestSafeUnlink(unittest.TestCase):

    def test_removes_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = Path(f.name)
        self.assertTrue(safe_unlink(p))
        self.assertFalse(p.exists())

    def test_nonexistent_returns_false(self):
        self.assertFalse(safe_unlink(Path("/nonexistent")))

    def test_dir_returns_false(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(safe_unlink(Path(d)))


class TestSafeRmtree(unittest.TestCase):

    def test_removes_dir(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "sub"
            sub.mkdir()
            (sub / "file.txt").write_bytes(b"x")
            self.assertTrue(safe_rmtree(sub))
            self.assertFalse(sub.exists())

    def test_nonexistent_returns_false(self):
        self.assertFalse(safe_rmtree(Path("/nonexistent")))

    def test_file_returns_false(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = Path(f.name)
        try:
            self.assertFalse(safe_rmtree(p))
        finally:
            p.unlink()


# ---------------------------------------------------------------
# cleanup (core function)
# ---------------------------------------------------------------

class _TmpRunDir:
    def __init__(self):
        self._tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self._tmpdir) / "RUN_TEST"
        self.run_dir.mkdir()

    def cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def write_manifest(self, data: dict):
        (self.run_dir / "00_manifest.json").write_text(
            json.dumps(data), encoding="utf-8"
        )

    def write_receipt(self, status: str = "UPLOADED", hmac: str = "fake"):
        publish = self.run_dir / "publish"
        publish.mkdir(exist_ok=True)
        receipt = {
            "status": status,
            "integrity": {"hmac_sha256": hmac},
            "uploaded_at_utc": "2020-01-01T00:00:00Z",
        }
        (publish / "upload_receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8"
        )

    def create_heavy_assets(self):
        (self.run_dir / "02_audio.wav").write_bytes(b"\x00" * 500)
        (self.run_dir / "03_frame.png").write_bytes(b"\x00" * 500)


class TestCleanup(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_missing_run_dir(self):
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(Path("/nonexistent"))
        self.assertFalse(ok)
        self.assertEqual(info, "missing_run_dir")

    def test_missing_manifest(self):
        from rayvault.cleanup_run import cleanup
        ok, info = cleanup(self.h.run_dir)
        self.assertFalse(ok)
        self.assertEqual(info, "missing_manifest")

    def test_missing_receipt_no_force(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        ok, info = cleanup(self.h.run_dir)
        self.assertFalse(ok)
        self.assertEqual(info, "missing_receipt")

    def test_force_skips_receipt(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        self.h.create_heavy_assets()
        ok, info = cleanup(self.h.run_dir, force=True, apply=False)
        self.assertTrue(ok)
        self.assertIsInstance(info, dict)
        self.assertGreater(info["targets"], 0)

    def test_dry_run_no_delete(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        self.h.create_heavy_assets()
        ok, info = cleanup(self.h.run_dir, force=True, apply=False)
        self.assertTrue(ok)
        # Files should still exist
        self.assertTrue((self.h.run_dir / "02_audio.wav").exists())

    def test_apply_deletes_assets(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        self.h.create_heavy_assets()
        ok, info = cleanup(self.h.run_dir, force=True, apply=True)
        self.assertTrue(ok)
        self.assertGreater(info["deleted"], 0)
        self.assertFalse((self.h.run_dir / "02_audio.wav").exists())
        self.assertFalse((self.h.run_dir / "03_frame.png").exists())

    def test_cleanup_writes_history(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        cleanup(self.h.run_dir, force=True, apply=False)
        m = json.loads((self.h.run_dir / "00_manifest.json").read_text())
        self.assertIn("housekeeping", m)
        self.assertIn("cleanup_history", m["housekeeping"])
        self.assertEqual(len(m["housekeeping"]["cleanup_history"]), 1)


# ---------------------------------------------------------------
# du_bytes edge cases
# ---------------------------------------------------------------

class TestDuBytesEdgeCases(unittest.TestCase):

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(du_bytes(Path(d)), 0)

    def test_nested_directories(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "a" / "b"
            sub.mkdir(parents=True)
            (sub / "data.bin").write_bytes(b"\x00" * 100)
            self.assertEqual(du_bytes(Path(d)), 100)

    def test_multiple_files(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                (Path(d) / f"f{i}.txt").write_bytes(b"x" * 10)
            self.assertEqual(du_bytes(Path(d)), 50)

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = Path(f.name)
        try:
            self.assertEqual(du_bytes(p), 0)
        finally:
            p.unlink()


# ---------------------------------------------------------------
# safe_unlink edge cases
# ---------------------------------------------------------------

class TestSafeUnlinkEdgeCases(unittest.TestCase):

    def test_readonly_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            p = Path(f.name)
        import os
        os.chmod(str(p), 0o444)
        try:
            # May succeed or fail depending on OS — should not crash
            result = safe_unlink(p)
            self.assertIsInstance(result, bool)
        finally:
            if p.exists():
                os.chmod(str(p), 0o644)
                p.unlink()

    def test_symlink_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "target.txt"
            target.write_text("data")
            link = Path(d) / "link.txt"
            link.symlink_to(target)
            result = safe_unlink(link)
            self.assertTrue(result)
            self.assertFalse(link.exists())
            self.assertTrue(target.exists())  # target should survive


# ---------------------------------------------------------------
# safe_rmtree edge cases
# ---------------------------------------------------------------

class TestSafeRmtreeEdgeCases(unittest.TestCase):

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            sub = Path(d) / "empty"
            sub.mkdir()
            self.assertTrue(safe_rmtree(sub))
            self.assertFalse(sub.exists())

    def test_deeply_nested(self):
        with tempfile.TemporaryDirectory() as d:
            deep = Path(d) / "a" / "b" / "c" / "d"
            deep.mkdir(parents=True)
            (deep / "file.txt").write_text("data")
            self.assertTrue(safe_rmtree(Path(d) / "a"))
            self.assertFalse((Path(d) / "a").exists())


# ---------------------------------------------------------------
# cleanup edge cases
# ---------------------------------------------------------------

class TestCleanupEdgeCases(unittest.TestCase):

    def setUp(self):
        self.h = _TmpRunDir()

    def tearDown(self):
        self.h.cleanup()

    def test_double_cleanup(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        self.h.create_heavy_assets()
        cleanup(self.h.run_dir, force=True, apply=True)
        # Second cleanup should succeed with 0 targets
        ok, info = cleanup(self.h.run_dir, force=True, apply=True)
        self.assertTrue(ok)
        self.assertEqual(info["deleted"], 0)

    def test_manifest_preserved_after_cleanup(self):
        from rayvault.cleanup_run import cleanup
        self.h.write_manifest({"status": "READY_FOR_RENDER"})
        self.h.create_heavy_assets()
        cleanup(self.h.run_dir, force=True, apply=True)
        manifest = self.h.run_dir / "00_manifest.json"
        self.assertTrue(manifest.exists())
        data = json.loads(manifest.read_text())
        self.assertIn("housekeeping", data)


if __name__ == "__main__":
    unittest.main()
