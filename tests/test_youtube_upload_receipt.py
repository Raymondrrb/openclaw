#!/usr/bin/env python3
"""Tests for rayvault/youtube_upload_receipt.py — HMAC-signed upload proof."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rayvault.youtube_upload_receipt import (
    RECEIPT_SCHEMA_VERSION,
    _canonical_payload,
    _compute_hmac,
    _derive_key,
    generate_receipt,
    preflight_check,
    sha256_file,
    sign_receipt,
    verify_receipt,
)


# ---------------------------------------------------------------
# _derive_key
# ---------------------------------------------------------------

class TestDeriveKey(unittest.TestCase):

    def test_returns_bytes(self):
        key = _derive_key("RUN_2026_02_14_A")
        self.assertIsInstance(key, bytes)

    def test_length_32(self):
        key = _derive_key("RUN_2026_02_14_A")
        self.assertEqual(len(key), 32)  # SHA-256 = 32 bytes

    def test_deterministic(self):
        k1 = _derive_key("RUN_A")
        k2 = _derive_key("RUN_A")
        self.assertEqual(k1, k2)

    def test_different_run_ids(self):
        k1 = _derive_key("RUN_A")
        k2 = _derive_key("RUN_B")
        self.assertNotEqual(k1, k2)


# ---------------------------------------------------------------
# _compute_hmac
# ---------------------------------------------------------------

class TestComputeHmac(unittest.TestCase):

    def test_returns_hex_string(self):
        h = _compute_hmac("RUN_A", "payload")
        self.assertEqual(len(h), 64)  # SHA-256 hex = 64 chars
        int(h, 16)  # valid hex

    def test_deterministic(self):
        h1 = _compute_hmac("RUN_A", "payload")
        h2 = _compute_hmac("RUN_A", "payload")
        self.assertEqual(h1, h2)

    def test_different_payload_different_hmac(self):
        h1 = _compute_hmac("RUN_A", "payload_1")
        h2 = _compute_hmac("RUN_A", "payload_2")
        self.assertNotEqual(h1, h2)

    def test_different_run_id_different_hmac(self):
        h1 = _compute_hmac("RUN_A", "payload")
        h2 = _compute_hmac("RUN_B", "payload")
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------
# _canonical_payload
# ---------------------------------------------------------------

class TestCanonicalPayload(unittest.TestCase):

    def _make_receipt(self, **overrides):
        r = {
            "version": "1.0",
            "run_id": "RUN_A",
            "status": "UPLOADED",
            "uploaded_at_utc": "2026-02-14T12:00:00Z",
            "inputs": {
                "video_sha256": "abcdef1234",
                "video_size_bytes": 1048576,
            },
            "youtube": {
                "video_id": "dQw4w9WgXcQ",
                "channel_id": "UC123",
            },
        }
        r.update(overrides)
        return r

    def test_returns_string(self):
        canon = _canonical_payload(self._make_receipt())
        self.assertIsInstance(canon, str)

    def test_pipe_separated(self):
        canon = _canonical_payload(self._make_receipt())
        parts = canon.split("|")
        self.assertEqual(len(parts), 8)

    def test_includes_all_fields(self):
        canon = _canonical_payload(self._make_receipt())
        self.assertIn("1.0", canon)
        self.assertIn("RUN_A", canon)
        self.assertIn("UPLOADED", canon)
        self.assertIn("abcdef1234", canon)
        self.assertIn("1048576", canon)
        self.assertIn("dQw4w9WgXcQ", canon)
        self.assertIn("UC123", canon)
        self.assertIn("2026-02-14T12:00:00Z", canon)

    def test_order_matters(self):
        r = self._make_receipt()
        canon = _canonical_payload(r)
        parts = canon.split("|")
        self.assertEqual(parts[0], "1.0")  # version
        self.assertEqual(parts[1], "RUN_A")  # run_id
        self.assertEqual(parts[2], "UPLOADED")  # status

    def test_missing_fields_empty_string(self):
        canon = _canonical_payload({})
        parts = canon.split("|")
        self.assertEqual(parts[0], "")  # version
        self.assertEqual(parts[1], "")  # run_id


# ---------------------------------------------------------------
# sign_receipt / verify_receipt
# ---------------------------------------------------------------

class TestSignVerifyReceipt(unittest.TestCase):

    def _make_receipt(self):
        return {
            "version": "1.0",
            "run_id": "RUN_TEST",
            "status": "UPLOADED",
            "uploaded_at_utc": "2026-02-14T12:00:00Z",
            "inputs": {
                "video_sha256": "abc123",
                "video_size_bytes": 999,
            },
            "youtube": {
                "video_id": "vid123",
                "channel_id": "chan456",
            },
        }

    def test_sign_returns_hex(self):
        receipt = self._make_receipt()
        sig = sign_receipt(receipt)
        self.assertEqual(len(sig), 64)
        int(sig, 16)

    def test_sign_deterministic(self):
        receipt = self._make_receipt()
        s1 = sign_receipt(receipt)
        s2 = sign_receipt(receipt)
        self.assertEqual(s1, s2)

    def test_verify_valid(self):
        receipt = self._make_receipt()
        sig = sign_receipt(receipt)
        receipt["integrity"] = {"hmac_sha256": sig}
        self.assertTrue(verify_receipt(receipt))

    def test_verify_tampered_field(self):
        receipt = self._make_receipt()
        sig = sign_receipt(receipt)
        receipt["integrity"] = {"hmac_sha256": sig}
        receipt["status"] = "TAMPERED"
        self.assertFalse(verify_receipt(receipt))

    def test_verify_tampered_video_id(self):
        receipt = self._make_receipt()
        sig = sign_receipt(receipt)
        receipt["integrity"] = {"hmac_sha256": sig}
        receipt["youtube"]["video_id"] = "HACKED"
        self.assertFalse(verify_receipt(receipt))

    def test_verify_no_integrity_block(self):
        receipt = self._make_receipt()
        self.assertFalse(verify_receipt(receipt))

    def test_verify_empty_hmac(self):
        receipt = self._make_receipt()
        receipt["integrity"] = {"hmac_sha256": ""}
        self.assertFalse(verify_receipt(receipt))

    def test_verify_wrong_hmac(self):
        receipt = self._make_receipt()
        receipt["integrity"] = {"hmac_sha256": "0" * 64}
        self.assertFalse(verify_receipt(receipt))


# ---------------------------------------------------------------
# sha256_file
# ---------------------------------------------------------------

class TestSha256File(unittest.TestCase):

    def test_returns_hex(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"hello world")
            f.flush()
            p = Path(f.name)
        try:
            h = sha256_file(p)
            self.assertEqual(len(h), 64)
            int(h, 16)
        finally:
            p.unlink()

    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"test data")
            f.flush()
            p = Path(f.name)
        try:
            h1 = sha256_file(p)
            h2 = sha256_file(p)
            self.assertEqual(h1, h2)
        finally:
            p.unlink()

    def test_different_content(self):
        paths = []
        for data in (b"AAA", b"BBB"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
                f.write(data)
                f.flush()
                paths.append(Path(f.name))
        try:
            self.assertNotEqual(sha256_file(paths[0]), sha256_file(paths[1]))
        finally:
            for p in paths:
                p.unlink()


# ---------------------------------------------------------------
# preflight_check
# ---------------------------------------------------------------

class TestPreflightCheck(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "RUN_TEST"
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_missing_manifest(self):
        ok, reason = preflight_check(self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_manifest")

    def test_not_ready_status(self):
        manifest = {"status": "INIT", "validation": {"passed": False}}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))
        ok, reason = preflight_check(self.run_dir)
        self.assertFalse(ok)
        self.assertIn("not_ready", reason)

    def test_ready_status_but_no_video(self):
        manifest = {"status": "READY_FOR_RENDER"}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))
        ok, reason = preflight_check(self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_video_final")

    def test_video_too_small(self):
        manifest = {"status": "READY_FOR_RENDER"}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))
        pub = self.run_dir / "publish"
        pub.mkdir()
        (pub / "video_final.mp4").write_bytes(b"\x00" * 100)  # < 1024
        ok, reason = preflight_check(self.run_dir)
        self.assertFalse(ok)
        self.assertEqual(reason, "video_too_small")

    def test_full_pass(self):
        manifest = {"status": "READY_FOR_RENDER"}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))
        pub = self.run_dir / "publish"
        pub.mkdir()
        (pub / "video_final.mp4").write_bytes(b"\x00" * 2048)
        ok, reason = preflight_check(self.run_dir)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_validation_passed_overrides_status(self):
        manifest = {"status": "SOME_OTHER", "validation": {"passed": True}}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))
        pub = self.run_dir / "publish"
        pub.mkdir()
        (pub / "video_final.mp4").write_bytes(b"\x00" * 2048)
        ok, reason = preflight_check(self.run_dir)
        self.assertTrue(ok)

    def test_no_video_check(self):
        manifest = {"status": "READY_FOR_RENDER"}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))
        ok, reason = preflight_check(self.run_dir, require_video=False)
        self.assertTrue(ok)


# ---------------------------------------------------------------
# generate_receipt
# ---------------------------------------------------------------

class TestGenerateReceipt(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.run_dir = Path(self.tmpdir) / "RUN_GEN_TEST"
        self.run_dir.mkdir(parents=True)
        pub = self.run_dir / "publish"
        pub.mkdir()
        (pub / "video_final.mp4").write_bytes(b"\x00" * 4096)
        manifest = {"status": "READY_FOR_RENDER"}
        (self.run_dir / "00_manifest.json").write_text(json.dumps(manifest))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generates_receipt(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        self.assertEqual(receipt["status"], "UPLOADED")
        self.assertEqual(receipt["youtube"]["video_id"], "vid123")

    def test_receipt_has_integrity(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        self.assertIn("integrity", receipt)
        self.assertIn("hmac_sha256", receipt["integrity"])

    def test_receipt_verifiable(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        self.assertTrue(verify_receipt(receipt))

    def test_receipt_written_to_disk(self):
        generate_receipt(self.run_dir, video_id="vid123")
        receipt_path = self.run_dir / "publish" / "upload_receipt.json"
        self.assertTrue(receipt_path.exists())
        loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertTrue(verify_receipt(loaded))

    def test_manifest_updated(self):
        generate_receipt(self.run_dir, video_id="vid123")
        manifest = json.loads((self.run_dir / "00_manifest.json").read_text())
        self.assertEqual(manifest["status"], "UPLOADED")
        self.assertEqual(manifest["publish"]["video_id"], "vid123")

    def test_default_video_url(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        self.assertEqual(receipt["youtube"]["video_url"], "https://youtu.be/vid123")

    def test_custom_video_url(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123",
                                   video_url="https://custom.url/x")
        self.assertEqual(receipt["youtube"]["video_url"], "https://custom.url/x")

    def test_empty_video_id_raises(self):
        with self.assertRaises(ValueError):
            generate_receipt(self.run_dir, video_id="")

    def test_preflight_failure_raises(self):
        bad_dir = Path(self.tmpdir) / "RUN_BAD"
        bad_dir.mkdir()
        with self.assertRaises(ValueError):
            generate_receipt(bad_dir, video_id="vid123")

    def test_video_sha256_populated(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        sha = receipt["inputs"]["video_sha256"]
        self.assertEqual(len(sha), 64)
        int(sha, 16)

    def test_video_size_populated(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        self.assertEqual(receipt["inputs"]["video_size_bytes"], 4096)

    def test_schema_version(self):
        receipt = generate_receipt(self.run_dir, video_id="vid123")
        self.assertEqual(receipt["version"], RECEIPT_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
