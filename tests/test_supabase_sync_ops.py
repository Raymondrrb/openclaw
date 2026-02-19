#!/usr/bin/env python3
"""Tests for tools/supabase_sync_ops.py — row builders, JWT, chunking."""

from __future__ import annotations

import base64
import json
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from supabase_sync_ops import (  # noqa: E402
    build_event_rows,
    build_mission_rows,
    build_policy_rows,
    build_proposal_rows,
    build_step_rows,
    chunk_rows,
    decode_jwt_payload,
    validate_supabase_service_key,
)


def b64url(obj) -> str:
    raw = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _make_jwt(payload: dict) -> str:
    header = b64url({"alg": "HS256"})
    body = b64url(payload)
    sig = base64.urlsafe_b64encode(b"fakesig").decode().rstrip("=")
    return f"{header}.{body}.{sig}"


# ---------------------------------------------------------------
# decode_jwt_payload
# ---------------------------------------------------------------

class TestDecodeJwtPayload(unittest.TestCase):

    def test_valid_jwt(self):
        token = _make_jwt({"role": "service_role", "iss": "supabase"})
        result = decode_jwt_payload(token)
        self.assertEqual(result["role"], "service_role")

    def test_not_a_jwt(self):
        self.assertEqual(decode_jwt_payload("not-a-jwt"), {})

    def test_empty_string(self):
        self.assertEqual(decode_jwt_payload(""), {})

    def test_two_parts(self):
        self.assertEqual(decode_jwt_payload("a.b"), {})

    def test_invalid_base64(self):
        result = decode_jwt_payload("a.!!!invalid!!!.c")
        self.assertEqual(result, {})


# ---------------------------------------------------------------
# validate_supabase_service_key
# ---------------------------------------------------------------

class TestValidateSupabaseServiceKey(unittest.TestCase):

    def test_blocks_publishable_key(self):
        with self.assertRaises(RuntimeError):
            validate_supabase_service_key("sb_publishable_abc123")

    def test_allows_non_jwt_secret_key(self):
        validate_supabase_service_key("sb_secret_abc123")

    def test_rejects_jwt_missing_role(self):
        token = _make_jwt({"sub": "x"})
        with self.assertRaises(RuntimeError):
            validate_supabase_service_key(token)

    def test_allows_service_role_jwt(self):
        token = _make_jwt({"role": "service_role"})
        validate_supabase_service_key(token)

    def test_rejects_anon_jwt(self):
        token = _make_jwt({"role": "anon"})
        with self.assertRaises(RuntimeError):
            validate_supabase_service_key(token)

    def test_rejects_empty_role_jwt(self):
        token = _make_jwt({"role": ""})
        with self.assertRaises(RuntimeError):
            validate_supabase_service_key(token)


# ---------------------------------------------------------------
# build_policy_rows
# ---------------------------------------------------------------

class TestBuildPolicyRows(unittest.TestCase):

    def test_empty_policies(self):
        self.assertEqual(build_policy_rows({}), [])

    def test_single_policy(self):
        rows = build_policy_rows({"daily_video_cap": 1})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "daily_video_cap")
        self.assertEqual(rows[0]["value"], 1)
        self.assertIn("updated_at", rows[0])

    def test_multiple_policies(self):
        rows = build_policy_rows({"a": 1, "b": "two", "c": True})
        self.assertEqual(len(rows), 3)
        keys = {r["key"] for r in rows}
        self.assertEqual(keys, {"a", "b", "c"})


# ---------------------------------------------------------------
# build_proposal_rows
# ---------------------------------------------------------------

class TestBuildProposalRows(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(build_proposal_rows([]), [])

    def test_valid_proposal(self):
        rows = build_proposal_rows([{
            "id": "prop_001",
            "title": "Earbuds video",
            "category": "earbuds",
            "status": "approved",
        }])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "prop_001")
        self.assertEqual(rows[0]["status"], "approved")

    def test_missing_id_skipped(self):
        rows = build_proposal_rows([{"title": "No ID"}])
        self.assertEqual(len(rows), 0)

    def test_missing_title_skipped(self):
        rows = build_proposal_rows([{"id": "x"}])
        self.assertEqual(len(rows), 0)

    def test_default_status(self):
        rows = build_proposal_rows([{"id": "p1", "title": "T"}])
        self.assertEqual(rows[0]["status"], "pending")


# ---------------------------------------------------------------
# build_mission_rows
# ---------------------------------------------------------------

class TestBuildMissionRows(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(build_mission_rows([]), [])

    def test_valid_mission(self):
        rows = build_mission_rows([{
            "id": "mission_001",
            "title": "Produce earbuds video",
            "proposal_id": "prop_001",
        }])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "queued")

    def test_missing_id_skipped(self):
        rows = build_mission_rows([{"title": "No ID"}])
        self.assertEqual(len(rows), 0)


# ---------------------------------------------------------------
# build_step_rows
# ---------------------------------------------------------------

class TestBuildStepRows(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(build_step_rows([]), [])

    def test_mission_with_steps(self):
        missions = [{
            "id": "m1",
            "title": "Test",
            "steps": [
                {"id": "s1", "kind": "trend_scan", "status": "queued"},
                {"id": "s2", "kind": "research", "status": "running"},
            ],
        }]
        rows = build_step_rows(missions)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["mission_id"], "m1")
        self.assertEqual(rows[0]["kind"], "trend_scan")
        self.assertEqual(rows[1]["status"], "running")

    def test_step_missing_id_skipped(self):
        missions = [{"id": "m1", "steps": [{"kind": "script"}]}]
        rows = build_step_rows(missions)
        self.assertEqual(len(rows), 0)

    def test_step_missing_kind_skipped(self):
        missions = [{"id": "m1", "steps": [{"id": "s1"}]}]
        rows = build_step_rows(missions)
        self.assertEqual(len(rows), 0)

    def test_mission_without_steps(self):
        missions = [{"id": "m1", "title": "T"}]
        rows = build_step_rows(missions)
        self.assertEqual(len(rows), 0)


# ---------------------------------------------------------------
# build_event_rows
# ---------------------------------------------------------------

class TestBuildEventRows(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(build_event_rows([]), [])

    def test_single_event(self):
        events = [{"ts": "2026-02-15T10:00:00Z", "type": "video_published", "message": "ok"}]
        rows = build_event_rows(events)
        self.assertEqual(len(rows), 1)
        self.assertIn("event_hash", rows[0])
        self.assertEqual(rows[0]["type"], "video_published")

    def test_event_hash_deterministic(self):
        ev = {"ts": "2026-01-01T00:00:00Z", "type": "test", "message": "hello"}
        rows1 = build_event_rows([ev])
        rows2 = build_event_rows([ev])
        self.assertEqual(rows1[0]["event_hash"], rows2[0]["event_hash"])

    def test_different_events_different_hashes(self):
        ev1 = {"ts": "2026-01-01T00:00:00Z", "type": "a"}
        ev2 = {"ts": "2026-01-01T00:00:00Z", "type": "b"}
        rows = build_event_rows([ev1, ev2])
        self.assertNotEqual(rows[0]["event_hash"], rows[1]["event_hash"])

    def test_missing_type_defaults(self):
        rows = build_event_rows([{"ts": "2026-01-01T00:00:00Z"}])
        self.assertEqual(rows[0]["type"], "event")


# ---------------------------------------------------------------
# chunk_rows
# ---------------------------------------------------------------

class TestChunkRows(unittest.TestCase):

    def test_empty_list(self):
        chunks = list(chunk_rows([], 10))
        self.assertEqual(chunks, [])

    def test_single_chunk(self):
        rows = [{"a": 1}, {"a": 2}, {"a": 3}]
        chunks = list(chunk_rows(rows, 10))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 3)

    def test_multiple_chunks(self):
        rows = [{"i": i} for i in range(7)]
        chunks = list(chunk_rows(rows, 3))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 3)
        self.assertEqual(len(chunks[1]), 3)
        self.assertEqual(len(chunks[2]), 1)

    def test_exact_batch_size(self):
        rows = [{"i": i} for i in range(6)]
        chunks = list(chunk_rows(rows, 3))
        self.assertEqual(len(chunks), 2)

    def test_zero_batch_yields_all(self):
        rows = [{"i": i} for i in range(5)]
        chunks = list(chunk_rows(rows, 0))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 5)


# ---------------------------------------------------------------
# validate_supabase_service_key None/empty safety
# ---------------------------------------------------------------

class TestValidateKeyNoneSafety(unittest.TestCase):

    def test_none_raises(self):
        with self.assertRaises(RuntimeError) as cm:
            validate_supabase_service_key(None)
        self.assertIn("empty", str(cm.exception).lower())

    def test_empty_string_raises(self):
        with self.assertRaises(RuntimeError):
            validate_supabase_service_key("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(RuntimeError):
            validate_supabase_service_key("   ")


# ---------------------------------------------------------------
# build_event_rows edge cases
# ---------------------------------------------------------------

class TestBuildEventRowsEdgeCases(unittest.TestCase):

    def test_event_with_data_field(self):
        ev = {"ts": "2026-01-01T00:00:00Z", "type": "metric", "data": {"views": 100}}
        rows = build_event_rows([ev])
        self.assertEqual(rows[0]["data"], {"views": 100})

    def test_event_without_message(self):
        ev = {"ts": "2026-01-01T00:00:00Z", "type": "heartbeat"}
        rows = build_event_rows([ev])
        self.assertEqual(rows[0]["message"], "")

    def test_many_events(self):
        events = [{"ts": f"2026-01-{i+1:02d}T00:00:00Z", "type": "t"} for i in range(100)]
        rows = build_event_rows(events)
        self.assertEqual(len(rows), 100)
        # All hashes should be unique
        hashes = {r["event_hash"] for r in rows}
        self.assertEqual(len(hashes), 100)


# ---------------------------------------------------------------
# decode_jwt_payload edge cases
# ---------------------------------------------------------------

class TestDecodeJwtEdgeCases(unittest.TestCase):

    def test_four_parts_returns_empty(self):
        self.assertEqual(decode_jwt_payload("a.b.c.d"), {})

    def test_payload_is_array_returns_empty(self):
        # A JWT whose payload is a JSON array, not object
        body = base64.urlsafe_b64encode(b'[1,2,3]').decode().rstrip("=")
        header = base64.urlsafe_b64encode(b'{}').decode().rstrip("=")
        sig = "fakesig"
        token = f"{header}.{body}.{sig}"
        result = decode_jwt_payload(token)
        self.assertEqual(result, {})

    def test_valid_payload_extracts_all_fields(self):
        token = _make_jwt({"role": "service_role", "iss": "supabase", "exp": 9999999999})
        result = decode_jwt_payload(token)
        self.assertEqual(result["iss"], "supabase")
        self.assertEqual(result["exp"], 9999999999)


# ---------------------------------------------------------------
# build_step_rows edge cases
# ---------------------------------------------------------------

class TestBuildStepRowsEdgeCases(unittest.TestCase):

    def test_step_with_optional_fields(self):
        missions = [{
            "id": "m1",
            "steps": [{
                "id": "s1",
                "kind": "render",
                "status": "running",
                "reserved_at": "2026-02-16T10:00:00Z",
                "error": "timeout",
            }],
        }]
        rows = build_step_rows(missions)
        self.assertEqual(rows[0]["reserved_at"], "2026-02-16T10:00:00Z")
        self.assertEqual(rows[0]["error"], "timeout")

    def test_multiple_missions_multiple_steps(self):
        missions = [
            {"id": "m1", "steps": [{"id": "s1", "kind": "script"}, {"id": "s2", "kind": "voice"}]},
            {"id": "m2", "steps": [{"id": "s3", "kind": "render"}]},
        ]
        rows = build_step_rows(missions)
        self.assertEqual(len(rows), 3)
        mission_ids = {r["mission_id"] for r in rows}
        self.assertEqual(mission_ids, {"m1", "m2"})


# ---------------------------------------------------------------
# chunk_rows edge cases
# ---------------------------------------------------------------

class TestChunkRowsEdgeCases(unittest.TestCase):

    def test_batch_size_1(self):
        rows = [{"i": i} for i in range(3)]
        chunks = list(chunk_rows(rows, 1))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 1)

    def test_negative_batch_yields_all(self):
        rows = [{"i": i} for i in range(5)]
        chunks = list(chunk_rows(rows, -1))
        self.assertEqual(len(chunks), 1)

    def test_batch_larger_than_rows(self):
        rows = [{"i": 1}]
        chunks = list(chunk_rows(rows, 1000))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 1)


if __name__ == "__main__":
    unittest.main()
