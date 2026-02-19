#!/usr/bin/env python3
"""Contract runtime + schema tests."""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from lib.contract_runtime import (  # noqa: E402
    build_receipt,
    collect_file_hashes,
    sha1_json,
    validate_schema,
)


class TestContractSchemas(unittest.TestCase):
    def test_validate_job_schema(self):
        schema = ROOT / "schemas" / "job.schema.json"
        job = {
            "schema_version": "1.0.0",
            "run_id": "run_123",
            "step_name": "discover-products",
            "command": "discover-products",
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "inputs": {
                "args": {"run_id": "run_123"},
                "required_files": ["run.json"],
                "file_digests": {"run.json": "abc"},
            },
            "requirements": {"os_in": ["windows"]},
        }
        validate_schema(schema_path=schema, data=job, context="test job")

    def test_validate_run_schema(self):
        schema = ROOT / "schemas" / "run.schema.json"
        run_data = {
            "schema_version": "1.0.0",
            "run_id": "run_123",
            "category": "desk_gadgets",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "config": {
                "target_duration_minutes": 8,
                "voice": "Thomas Louis",
                "affiliate_tag": "rayviews-20",
            },
            "status": "initialized",
            "step_status": {"init": "done"},
            "quality_gates": {
                "gate1": {"status": "pending"},
                "gate2": {"status": "pending"},
            },
        }
        validate_schema(schema_path=schema, data=run_data, context="test run")

    def test_validate_receipt_schema(self):
        schema = ROOT / "schemas" / "receipt.schema.json"
        started = dt.datetime.now(dt.timezone.utc)
        started_mono = 10.0
        finished_mono = 12.5
        receipt = build_receipt(
            schema_version="1.0.0",
            run_id="run_123",
            step_name="discover-products",
            ok=True,
            status="OK",
            exit_code=0,
            inputs_hash=sha1_json({"a": 1}),
            outputs_hash=sha1_json({"b": 2}),
            started_monotonic=started_mono,
            finished_monotonic=finished_mono,
            started_at=started.isoformat(),
            finished_at=(started + dt.timedelta(seconds=2.5)).isoformat(),
            artifacts=[{"path": "products.json"}],
        )
        validate_schema(schema_path=schema, data=receipt, context="test receipt")


class TestContractHashes(unittest.TestCase):
    def test_collect_file_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            p = base / "a.txt"
            p.write_text("hello", encoding="utf-8")
            hashes, aggregate = collect_file_hashes(base, ["a.txt", "missing.txt"])
            self.assertIn("a.txt", hashes)
            self.assertEqual(len(hashes["a.txt"]), 40)
            self.assertEqual(len(aggregate), 40)


if __name__ == "__main__":
    unittest.main()
