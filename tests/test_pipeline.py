#!/usr/bin/env python3
"""Tests for pipeline.py — core functions: retry, locking, gates, validation, run management."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Ensure tools/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from pipeline import (
    _count_openclaw_processes,
    _guard_openclaw_process_pressure,
    _ensure_intro_disclosure,
    _normalize_script_payload,
    _voice_source_requests_tts,
    RunLock,
    append_affiliate_tag,
    atomic_write_json,
    atomic_write_text,
    build_youtube_description,
    cmd_init_run,
    compute_artifact_checksums,
    ensure_quality_gates,
    file_checksum,
    gate_is_approved,
    generate_run_id,
    get_run_dir,
    load_run,
    validate_affiliate_url,
    with_retries,
    GATE_STATUSES,
)


# ---------------------------------------------------------------------------
# with_retries
# ---------------------------------------------------------------------------

class TestWithRetries(unittest.TestCase):
    def test_success_first_try(self):
        result = with_retries(lambda: 42, backoff=[0])
        self.assertEqual(result, 42)

    def test_retries_on_failure(self):
        call_count = {"n": 0}
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("not yet")
            return "ok"
        result = with_retries(flaky, max_attempts=3, backoff=[0, 0])
        self.assertEqual(result, "ok")
        self.assertEqual(call_count["n"], 3)

    def test_raises_after_max_attempts(self):
        def always_fail():
            raise RuntimeError("boom")
        with self.assertRaises(RuntimeError) as cm:
            with_retries(always_fail, max_attempts=2, backoff=[0], label="test_op")
        self.assertIn("test_op", str(cm.exception))
        self.assertIn("2 attempts", str(cm.exception))

    def test_default_backoff_is_not_shared(self):
        # The mutable default bug fix: each call should get its own list
        def succeed():
            return True
        with_retries(succeed)
        with_retries(succeed)
        # If the mutable default was shared, the second call would see
        # a modified list. This test just ensures no crash.

    def test_backoff_clamps_to_last(self):
        call_count = {"n": 0}
        def fail_twice():
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise ValueError("fail")
            return "done"
        result = with_retries(fail_twice, max_attempts=3, backoff=[0])
        self.assertEqual(result, "done")


class TestVoiceSourceRouting(unittest.TestCase):
    def test_enables_tts_for_minimax(self):
        self.assertTrue(_voice_source_requests_tts("minimax"))

    def test_enables_tts_for_openclaw(self):
        self.assertTrue(_voice_source_requests_tts("openclaw"))

    def test_enables_tts_for_elevenlabs(self):
        self.assertTrue(_voice_source_requests_tts("elevenlabs"))

    def test_disables_tts_for_mock(self):
        self.assertFalse(_voice_source_requests_tts("mock"))


class TestOpenClawProcessGuard(unittest.TestCase):
    def test_count_openclaw_processes(self):
        fake_ps = SimpleNamespace(
            returncode=0,
            stdout="\n".join([
                "python -m something",
                "openclaw browser --json tabs",
                "openclaw-channels run",
                "bash tools/openclaw_recover.sh",
            ]),
        )
        with patch("pipeline.subprocess.run", return_value=fake_ps):
            self.assertEqual(_count_openclaw_processes(), 2)

    def test_guard_warns_only(self):
        logger = SimpleNamespace(warning=lambda *a, **k: None)
        with patch("pipeline._count_openclaw_processes", return_value=50), \
             patch.dict("pipeline.os.environ", {
                 "RAYVIEWS_OPENCLAW_PROC_GUARD": "1",
                 "RAYVIEWS_OPENCLAW_PROC_WARN": "35",
                 "RAYVIEWS_OPENCLAW_PROC_BLOCK": "120",
             }, clear=False):
            _guard_openclaw_process_pressure(logger)

    def test_guard_blocks(self):
        logger = SimpleNamespace(warning=lambda *a, **k: None)
        with patch("pipeline._count_openclaw_processes", return_value=140), \
             patch.dict("pipeline.os.environ", {
                 "RAYVIEWS_OPENCLAW_PROC_GUARD": "1",
                 "RAYVIEWS_OPENCLAW_PROC_WARN": "35",
                 "RAYVIEWS_OPENCLAW_PROC_BLOCK": "120",
             }, clear=False):
            with self.assertRaises(RuntimeError):
                _guard_openclaw_process_pressure(logger)


# ---------------------------------------------------------------------------
# RunLock
# ---------------------------------------------------------------------------

class TestRunLock(unittest.TestCase):
    def test_acquire_and_release(self):
        with tempfile.TemporaryDirectory() as td:
            lock = RunLock(Path(td))
            self.assertTrue(lock.acquire())
            self.assertTrue(lock.held)
            self.assertTrue(lock.lock_path.exists())
            lock.release()
            self.assertFalse(lock.lock_path.exists())

    def test_double_acquire_fails(self):
        with tempfile.TemporaryDirectory() as td:
            lock = RunLock(Path(td))
            self.assertTrue(lock.acquire())
            # Second acquire by another lock should fail (same PID, process alive)
            lock2 = RunLock(Path(td))
            self.assertFalse(lock2.acquire())
            lock.release()

    def test_corrupt_lock_file_handled(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "run.lock"
            lock_path.write_text("not valid json!!!")
            lock = RunLock(Path(td))
            # Should handle corrupt file without infinite recursion
            result = lock.acquire()
            self.assertTrue(result)
            lock.release()

    def test_stale_lock_taken_over(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path = Path(td) / "run.lock"
            # Write a lock with a PID that doesn't exist
            lock_data = {"pid": 99999999, "acquired_at": "2024-01-01T00:00:00Z"}
            lock_path.write_text(json.dumps(lock_data))
            lock = RunLock(Path(td))
            result = lock.acquire()
            self.assertTrue(result)
            lock.release()

    def test_context_manager(self):
        with tempfile.TemporaryDirectory() as td:
            with RunLock(Path(td)) as lock:
                self.assertTrue(lock.held)
            self.assertFalse(Path(td, "run.lock").exists())


# ---------------------------------------------------------------------------
# atomic_write_json / atomic_write_text
# ---------------------------------------------------------------------------

class TestAtomicWrite(unittest.TestCase):
    def test_atomic_write_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            data = {"key": "value", "number": 42}
            result = atomic_write_json(path, data)
            self.assertEqual(result, path)
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded, data)

    def test_atomic_write_text(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.txt"
            text = "hello world\nline two"
            result = atomic_write_text(path, text)
            self.assertEqual(result, path)
            self.assertEqual(path.read_text(), text)

    def test_no_tmp_file_left(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out.json"
            atomic_write_json(path, {"ok": True})
            files = list(Path(td).iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].name, "out.json")


# ---------------------------------------------------------------------------
# file_checksum / compute_artifact_checksums
# ---------------------------------------------------------------------------

class TestFileChecksum(unittest.TestCase):
    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"hello world")
            path = f.name
        try:
            c1 = file_checksum(Path(path))
            c2 = file_checksum(Path(path))
            self.assertEqual(c1, c2)
            self.assertEqual(len(c1), 64)  # SHA256 hex
        finally:
            os.unlink(path)

    def test_different_content_different_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"content A")
            path_a = f.name
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"content B")
            path_b = f.name
        try:
            self.assertNotEqual(file_checksum(Path(path_a)), file_checksum(Path(path_b)))
        finally:
            os.unlink(path_a)
            os.unlink(path_b)


class TestComputeArtifactChecksums(unittest.TestCase):
    def test_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "products.json").write_text('{"products": []}')
            (run_dir / "script.json").write_text('{"segments": []}')
            checksums = compute_artifact_checksums(run_dir)
            self.assertIn("products.json", checksums)
            self.assertIn("script.json", checksums)
            self.assertEqual(len(checksums), 2)

    def test_no_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            checksums = compute_artifact_checksums(Path(td))
            self.assertEqual(checksums, {})


# ---------------------------------------------------------------------------
# generate_run_id / get_run_dir
# ---------------------------------------------------------------------------

class TestGenerateRunId(unittest.TestCase):
    def test_format(self):
        run_id = generate_run_id("desk gadgets!")
        # Should be slug + date
        self.assertTrue(run_id.startswith("desk_gadgets_"))
        self.assertRegex(run_id, r"^[a-z0-9_]+_\d{4}-\d{2}-\d{2}_\d{4}$")

    def test_truncates_long_category(self):
        run_id = generate_run_id("a" * 100)
        slug_part = run_id.split("_20")[0]  # before date
        self.assertLessEqual(len(slug_part), 30)

    def test_strips_special_chars(self):
        run_id = generate_run_id("USB-C Hubs & Docks")
        self.assertNotIn("&", run_id)
        self.assertNotIn("-", run_id.split("_20")[0])


# ---------------------------------------------------------------------------
# ensure_quality_gates
# ---------------------------------------------------------------------------

class TestEnsureQualityGates(unittest.TestCase):
    def test_creates_gates_if_missing(self):
        config = {}
        gates, changed = ensure_quality_gates(config)
        self.assertTrue(changed)
        self.assertIn("gate1", gates)
        self.assertIn("gate2", gates)
        self.assertEqual(gates["gate1"]["status"], "pending")

    def test_preserves_existing_gates(self):
        config = {
            "quality_gates": {
                "gate1": {"status": "approved", "reviewer": "Ray", "notes": "GO", "decided_at": "2024-01-01"},
                "gate2": {"status": "pending", "reviewer": "", "notes": "", "decided_at": ""},
            }
        }
        gates, changed = ensure_quality_gates(config)
        self.assertFalse(changed)
        self.assertEqual(gates["gate1"]["status"], "approved")
        self.assertEqual(gates["gate1"]["reviewer"], "Ray")

    def test_normalizes_invalid_status(self):
        config = {
            "quality_gates": {
                "gate1": {"status": "INVALID"},
                "gate2": {"status": "approved"},
            }
        }
        gates, changed = ensure_quality_gates(config)
        self.assertTrue(changed)
        self.assertEqual(gates["gate1"]["status"], "pending")

    def test_gate_statuses_constant(self):
        self.assertIn("pending", GATE_STATUSES)
        self.assertIn("approved", GATE_STATUSES)
        self.assertIn("rejected", GATE_STATUSES)


class TestGateIsApproved(unittest.TestCase):
    def test_approved(self):
        config = {"quality_gates": {
            "gate1": {"status": "approved", "reviewer": "R", "notes": "", "decided_at": ""},
            "gate2": {"status": "pending", "reviewer": "", "notes": "", "decided_at": ""},
        }}
        self.assertTrue(gate_is_approved(config, "gate1"))
        self.assertFalse(gate_is_approved(config, "gate2"))

    def test_missing_gate(self):
        self.assertFalse(gate_is_approved({}, "gate1"))


# ---------------------------------------------------------------------------
# append_affiliate_tag / validate_affiliate_url
# ---------------------------------------------------------------------------

class TestAppendAffiliateTag(unittest.TestCase):
    def test_adds_tag(self):
        url = "https://amazon.com/dp/B08N5WRWNW"
        result = append_affiliate_tag(url, "rayviews-20")
        self.assertIn("tag=rayviews-20", result)

    def test_replaces_existing_tag(self):
        url = "https://amazon.com/dp/B08N5WRWNW?tag=old-20"
        result = append_affiliate_tag(url, "rayviews-20")
        self.assertIn("tag=rayviews-20", result)
        self.assertNotIn("old-20", result)

    def test_empty_tag_returns_unchanged(self):
        url = "https://amazon.com/dp/B08N5WRWNW"
        self.assertEqual(append_affiliate_tag(url, ""), url)

    def test_amzn_short_link_unchanged(self):
        url = "https://amzn.to/3OjKBMV"
        self.assertEqual(append_affiliate_tag(url, "rayviews-20"), url)


class TestValidateAffiliateUrl(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_affiliate_url("https://amazon.com?tag=ray-20", "ray-20"))

    def test_missing_tag(self):
        self.assertFalse(validate_affiliate_url("https://amazon.com", "ray-20"))

    def test_duplicate_tag(self):
        self.assertFalse(validate_affiliate_url("https://amazon.com?tag=ray-20&tag=other-20", "ray-20"))

    def test_empty_tag_always_valid(self):
        self.assertTrue(validate_affiliate_url("https://amazon.com", ""))

    def test_amzn_short_link_valid(self):
        self.assertTrue(validate_affiliate_url("https://amzn.to/3OjKBMV", "ray-20"))


class TestBuildYoutubeDescription(unittest.TestCase):
    def test_includes_disclosure_and_tracking_override_links(self):
        with tempfile.TemporaryDirectory() as td:
            run_id = "run_test_2026_02_18"
            run_dir = Path(td) / run_id
            run_dir.mkdir(parents=True)
            products = {
                "products": [
                    {
                        "rank": 1,
                        "title": "Product One",
                        "price": 129.99,
                        "affiliate_url": "https://amzn.to/abc123",
                        "product_url": "https://www.amazon.com/dp/B0TEST001",
                    }
                ]
            }
            (run_dir / "products.json").write_text(json.dumps(products), encoding="utf-8")
            script = {"run_id": run_id, "chapters": [{"timecode": "00:00", "title": "Intro"}]}
            run_config = {"run_id": run_id, "category": "desk_gadgets"}
            with patch("pipeline.RUNS_DIR", Path(td)):
                desc = build_youtube_description(script, run_config, tracking_id_override="video-001-20")
            self.assertIn("As an Amazon Associate I earn from qualifying purchases.", desc)
            self.assertIn("Product 1 — Product One $129.99", desc)
            self.assertIn("tag=video-001-20", desc)


# ---------------------------------------------------------------------------
# load_run — path traversal validation
# ---------------------------------------------------------------------------

class TestLoadRun(unittest.TestCase):
    def test_rejects_path_traversal(self):
        args = SimpleNamespace(run_id="../../etc/passwd")
        with self.assertRaises(RuntimeError) as cm:
            load_run(args)
        self.assertIn("path separators", str(cm.exception))

    def test_rejects_forward_slash(self):
        args = SimpleNamespace(run_id="foo/bar")
        with self.assertRaises(RuntimeError):
            load_run(args)

    def test_rejects_backslash(self):
        args = SimpleNamespace(run_id="foo\\bar")
        with self.assertRaises(RuntimeError):
            load_run(args)

    def test_rejects_empty(self):
        args = SimpleNamespace(run_id="")
        with self.assertRaises(RuntimeError) as cm:
            load_run(args)
        self.assertIn("required", str(cm.exception))

    def test_valid_run_id(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "test_run_2024"
            run_dir.mkdir()
            config = {"run_id": "test_run_2024", "status": "draft"}
            (run_dir / "run.json").write_text(json.dumps(config))
            with patch("pipeline.RUNS_DIR", Path(td)):
                args = SimpleNamespace(run_id="test_run_2024")
                result_dir, result_id, result_config = load_run(args)
                self.assertEqual(result_id, "test_run_2024")
                self.assertEqual(result_config["status"], "draft")


class TestInitRunBehavior(unittest.TestCase):
    def _args(self, run_id: str, force: bool = False):
        return SimpleNamespace(
            category="desk_gadgets",
            run_id=run_id,
            force=force,
            duration=8,
            voice="Thomas Louis",
            affiliate_tag="rayviewslab-20",
            tracking_id_override="",
            min_rating=4.2,
            min_reviews=500,
            min_price=100.0,
            max_price=500.0,
            exclude_last_days=15,
            resolution="1920x1080",
            daily_budget_usd=30.0,
            spent_usd=0.0,
            critical_failures=0,
        )

    def test_init_run_creates_run_json_even_if_dir_exists_without_run_json(self):
        with tempfile.TemporaryDirectory() as td:
            run_id = "init_run_existing_dir"
            run_dir = Path(td) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            with patch("pipeline.RUNS_DIR", Path(td)):
                cmd_init_run(self._args(run_id))
            self.assertTrue((run_dir / "run.json").exists())

    def test_init_run_skips_when_run_json_exists_and_not_force(self):
        with tempfile.TemporaryDirectory() as td:
            run_id = "init_run_skip_existing"
            run_dir = Path(td) / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            existing = {"run_id": run_id, "status": "existing"}
            (run_dir / "run.json").write_text(json.dumps(existing), encoding="utf-8")
            with patch("pipeline.RUNS_DIR", Path(td)):
                cmd_init_run(self._args(run_id, force=False))
            loaded = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["status"], "existing")


# ---------------------------------------------------------------------------
# count_script_words
# ---------------------------------------------------------------------------

from pipeline import count_script_words


class TestCountScriptWords(unittest.TestCase):

    def test_empty_structure(self):
        self.assertEqual(count_script_words({}), 0)

    def test_flat_segments(self):
        data = {"structure": [
            {"type": "HOOK", "voice_text": "Hello world from here"},
            {"type": "CRITERIA", "voice_text": "One two three"},
        ]}
        self.assertEqual(count_script_words(data), 7)

    def test_nested_segments(self):
        data = {"structure": [
            {"type": "PRODUCT_BLOCK", "voice_text": "",
             "segments": [
                 {"voice_text": "First part words"},
                 {"voice_text": "Second part"},
             ]},
        ]}
        self.assertEqual(count_script_words(data), 5)

    def test_mixed_flat_and_nested(self):
        data = {"structure": [
            {"type": "HOOK", "voice_text": "Opening hook"},
            {"type": "PRODUCT_BLOCK", "voice_text": "Block intro",
             "segments": [{"voice_text": "Sub words here"}]},
        ]}
        self.assertEqual(count_script_words(data), 7)


# ---------------------------------------------------------------------------
# extract_full_narration
# ---------------------------------------------------------------------------

from pipeline import extract_full_narration


class TestExtractFullNarration(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(extract_full_narration({}), "")

    def test_flat_voice(self):
        data = {"structure": [
            {"type": "HOOK", "voice_text": "Hello"},
            {"type": "CRITERIA", "voice_text": "World"},
        ]}
        result = extract_full_narration(data)
        self.assertIn("Hello", result)
        self.assertIn("World", result)

    def test_nested_voice(self):
        data = {"structure": [
            {"type": "BLOCK", "voice_text": "",
             "segments": [{"voice_text": "Nested text"}]},
        ]}
        result = extract_full_narration(data)
        self.assertIn("Nested text", result)

    def test_separator(self):
        data = {"structure": [
            {"type": "A", "voice_text": "Part one"},
            {"type": "B", "voice_text": "Part two"},
        ]}
        result = extract_full_narration(data)
        self.assertIn("\n\n", result)

    def test_empty_voice_skipped(self):
        data = {"structure": [
            {"type": "A", "voice_text": ""},
            {"type": "B", "voice_text": "Only this"},
        ]}
        result = extract_full_narration(data)
        self.assertEqual(result, "Only this")


class TestIntroDisclosureInjection(unittest.TestCase):
    def test_injects_disclosure_when_missing(self):
        script = {
            "structure": [
                {"type": "NARRATION", "voice_text": "Welcome to RayViews."},
                {"type": "NARRATION", "voice_text": "Let's rank products."},
            ]
        }
        import logging
        logger = logging.getLogger("test")
        _ensure_intro_disclosure(script, logger)
        text = script["structure"][0]["voice_text"].lower()
        self.assertIn("as an amazon associate i earn from qualifying purchases", text)

    def test_no_duplicate_when_already_present(self):
        line = "As an Amazon Associate I earn from qualifying purchases. Welcome."
        script = {
            "structure": [
                {"type": "NARRATION", "voice_text": line},
                {"type": "NARRATION", "voice_text": "Other."},
            ]
        }
        import logging
        logger = logging.getLogger("test")
        _ensure_intro_disclosure(script, logger)
        merged = " ".join(s["voice_text"] for s in script["structure"][:2]).lower()
        self.assertEqual(merged.count("as an amazon associate i earn from qualifying purchases"), 1)


class TestNormalizeScriptPayload(unittest.TestCase):
    def test_converts_legacy_segments_shape(self):
        payload = {
            "video_title": "Test",
            "estimated_duration_minutes": 10,
            "segments": [
                {"type": "HOOK", "narration": "Hook text."},
                {"type": "PRODUCT_INTRO", "narration": "Product intro 1."},
                {"type": "PRODUCT_REVIEW", "narration": "Product review 1."},
                {"type": "PRODUCT_INTRO", "narration": "Product intro 2."},
            ],
        }
        products = [
            {"rank": 1, "title": "One"},
            {"rank": 2, "title": "Two"},
        ]
        out = _normalize_script_payload(
            payload=payload,
            run_id="run_x",
            category="portable_monitors",
            products=products,
            duration=8,
        )
        self.assertIn("structure", out)
        self.assertGreaterEqual(len(out["structure"]), 3)
        ids = [s.get("id") for s in out["structure"]]
        self.assertIn("hook", ids)
        self.assertIn("p1_intro", ids)
        self.assertIn("p1_review", ids)
        self.assertIn("p2_intro", ids)


# ---------------------------------------------------------------------------
# validate_products_json
# ---------------------------------------------------------------------------

from pipeline import validate_products_json


class TestValidateProductsJson(unittest.TestCase):

    def _valid_products(self, n=5):
        return {"products": [
            {"asin": f"B{i:09d}", "title": f"Product {i}", "price": 29.99 + i}
            for i in range(n)
        ]}

    def test_valid(self):
        self.assertEqual(validate_products_json(self._valid_products()), [])

    def test_missing_products_key(self):
        errors = validate_products_json({})
        self.assertTrue(any("Missing" in e for e in errors))

    def test_too_few_products(self):
        errors = validate_products_json(self._valid_products(3))
        self.assertTrue(any("at least 5" in e for e in errors))

    def test_missing_asin(self):
        data = self._valid_products()
        data["products"][0].pop("asin")
        errors = validate_products_json(data)
        self.assertTrue(any("asin" in e for e in errors))

    def test_missing_title(self):
        data = self._valid_products()
        data["products"][2].pop("title")
        errors = validate_products_json(data)
        self.assertTrue(any("title" in e for e in errors))

    def test_invalid_price(self):
        data = self._valid_products()
        data["products"][0]["price"] = 0
        errors = validate_products_json(data)
        self.assertTrue(any("price" in e for e in errors))


# ---------------------------------------------------------------------------
# validate_script_json
# ---------------------------------------------------------------------------

from pipeline import validate_script_json


class TestValidateScriptJson(unittest.TestCase):

    def _valid_script(self):
        segs = [{"type": "HOOK", "voice_text": " ".join(["word"] * 250)}]
        for i in range(5):
            segs.append({
                "type": "PRODUCT_BLOCK",
                "voice_text": " ".join(["text"] * 200),
                "segments": [],
            })
        return {"structure": segs}

    def test_valid_script(self):
        self.assertEqual(validate_script_json(self._valid_script()), [])

    def test_missing_structure(self):
        errors = validate_script_json({})
        self.assertTrue(any("structure" in e for e in errors))

    def test_missing_hook(self):
        data = {"structure": [
            {"type": "PRODUCT_BLOCK", "voice_text": " ".join(["w"] * 300)}
            for _ in range(5)
        ]}
        errors = validate_script_json(data)
        self.assertTrue(any("hook" in e.lower() for e in errors))

    def test_too_few_products(self):
        data = {"structure": [
            {"type": "HOOK", "voice_text": " ".join(["w"] * 300)},
            {"type": "PRODUCT_BLOCK", "voice_text": " ".join(["w"] * 200)},
        ]}
        errors = validate_script_json(data)
        self.assertTrue(any("5 products" in e for e in errors))

    def test_too_few_words(self):
        data = {"structure": [
            {"type": "HOOK", "voice_text": "Short"},
        ] + [
            {"type": "PRODUCT_BLOCK", "voice_text": "Brief"} for _ in range(5)
        ]}
        errors = validate_script_json(data)
        self.assertTrue(any("below minimum" in e for e in errors))


# ---------------------------------------------------------------------------
# generate_mock_products
# ---------------------------------------------------------------------------

from pipeline import generate_mock_products


class TestGenerateMockProducts(unittest.TestCase):

    def test_returns_5_products(self):
        products = generate_mock_products("earbuds", "tag-20")
        self.assertEqual(len(products), 5)

    def test_all_have_required_fields(self):
        products = generate_mock_products("monitors", "rv-20")
        for p in products:
            self.assertIn("asin", p)
            self.assertIn("title", p)
            self.assertIn("price", p)
            self.assertIn("affiliate_url", p)
            self.assertIn("rank", p)

    def test_ranks_sequential(self):
        products = generate_mock_products("keyboards", "tag-20")
        ranks = [p["rank"] for p in products]
        self.assertEqual(ranks, [1, 2, 3, 4, 5])

    def test_affiliate_tag_applied(self):
        products = generate_mock_products("mice", "myshop-20")
        for p in products:
            self.assertIn("myshop-20", p["affiliate_url"])

    def test_category_in_title(self):
        products = generate_mock_products("smart_rings", "tag-20")
        for p in products:
            self.assertIn("Smart Rings", p["title"])

    def test_deterministic(self):
        p1 = generate_mock_products("earbuds", "tag-20")
        p2 = generate_mock_products("earbuds", "tag-20")
        self.assertEqual(p1, p2)

    def test_start_index_changes_asins_without_changing_ranks(self):
        p1 = generate_mock_products("earbuds", "tag-20", start_index=1)
        p2 = generate_mock_products("earbuds", "tag-20", start_index=6)
        self.assertEqual([p["rank"] for p in p2], [1, 2, 3, 4, 5])
        self.assertNotEqual([p["asin"] for p in p1], [p["asin"] for p in p2])


# ---------------------------------------------------------------------------
# _retry_backoff
# ---------------------------------------------------------------------------

from pipeline import _retry_backoff


class TestRetryBackoff(unittest.TestCase):

    def test_single_attempt_returns_default(self):
        result = _retry_backoff(5, 1)
        self.assertEqual(result, [5.0])

    def test_two_attempts(self):
        result = _retry_backoff(2, 2)
        self.assertEqual(result, [2.0])

    def test_three_attempts(self):
        result = _retry_backoff(2, 3)
        self.assertEqual(result, [2.0, 6.0])

    def test_four_attempts(self):
        result = _retry_backoff(1, 4)
        self.assertEqual(result, [1.0, 3.0, 9.0])

    def test_zero_attempts_returns_default(self):
        result = _retry_backoff(5, 0)
        self.assertEqual(result, [5.0])

    def test_exponential_growth(self):
        result = _retry_backoff(1, 5)
        self.assertEqual(len(result), 4)
        for i in range(len(result) - 1):
            self.assertEqual(result[i + 1], result[i] * 3)


if __name__ == "__main__":
    unittest.main()
