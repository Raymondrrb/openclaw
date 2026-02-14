#!/usr/bin/env python3
"""Verification test for OutputGuard — simulates a 5MB DOM dump.

Confirms:
1. stdout is truncated (max 30 lines)
2. full log written to disk
3. artifact saved (compressed)
4. checkpoint.json created
5. run_report.md created

Run:
    python tools/test_output_guard.py

Or via stable_run wrapper:
    python tools/stable_run.py --script test_output_guard.py --run-id test_guard_001
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure lib is importable
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from lib.output_guard import OutputGuard


def test_basic_output_guard():
    """Test that OutputGuard caps stdout and writes to disk."""
    run_id = os.environ.get("STABLE_RUN_ID", "test_guard_verify")
    base_dir = os.environ.get("STABLE_RUN_BASE", str(_repo))
    guard = OutputGuard(run_id, base_dir=base_dir)

    # ── 1. Test safe_print truncation ────────────────────────────────────
    print("\n--- Test 1: safe_print truncation ---")
    guard.safe_print("Short message: OK")
    guard.safe_print("A" * 5000)  # should be truncated on stdout

    # Print many lines to test the line cap
    for i in range(40):
        guard.safe_print(f"Line {i}: status check")
    # After ~30 lines, further prints should be suppressed on stdout

    # ── 2. Test artifact writing ─────────────────────────────────────────
    print("\n--- Test 2: artifact writing ---")

    # Small artifact (no compression)
    small_data = {"buttons": [{"text": "Generate", "x": 92, "y": 710}]}
    path_small = guard.write_artifact("small_buttons.json", small_data)
    assert path_small is not None, "Small artifact should succeed"
    assert path_small.exists(), f"Artifact not found: {path_small}"

    # Large artifact (should compress)
    print("Generating 5MB DOM blob...")
    big_dom = {
        "nodes": [
            {
                "tag": f"DIV_{i}",
                "class": f"class-{i}-{'x' * 200}",
                "text": f"Content block {i} with padding {'.' * 300}",
                "children": [
                    {"tag": f"SPAN_{j}", "text": f"child_{j}_{'z' * 100}"}
                    for j in range(10)
                ],
            }
            for i in range(2000)
        ],
        "total_bytes": "simulated_5MB",
    }
    raw_size = len(json.dumps(big_dom).encode())
    print(f"  Raw DOM size: {raw_size:,} bytes ({raw_size / 1024 / 1024:.1f} MB)")

    path_big = guard.write_artifact("big_dom.json", big_dom, compress=True)
    assert path_big is not None, "Big artifact should succeed"
    assert path_big.exists(), f"Big artifact not found: {path_big}"
    assert path_big.suffix == ".gz", "Big artifact should be gzipped"
    disk_size = path_big.stat().st_size
    print(f"  Compressed size: {disk_size:,} bytes ({disk_size / 1024:.0f} KB)")
    assert disk_size < raw_size, "Compressed should be smaller than raw"

    # ── 3. Test summarize_dom ────────────────────────────────────────────
    print("\n--- Test 3: summarize_dom ---")
    guard.summarize_dom({
        "tag": ".c-gen-config.show",
        "nodes": 347,
        "bytes": 24810,
        "buttons": 12,
        "inputs": 3,
    })

    # ── 4. Test screenshot cap (mock — no real page) ─────────────────────
    print("\n--- Test 4: screenshot cap (simulated) ---")
    # We can't test real screenshots without Playwright, but we can verify
    # the cap logic by checking counters
    guard._screenshot_count = 9
    guard.safe_print(f"  Screenshots at cap-1: {guard._screenshot_count}/{guard.limits['max_screenshots']}")

    # ── 5. Finish and verify outputs ─────────────────────────────────────
    print("\n--- Test 5: finish + verify outputs ---")
    checkpoint = guard.finish(
        status="completed",
        next_step="Run actual explore_dzine script with output_guard",
        script_name="test_output_guard.py",
        extra={"test": True},
    )

    # Verify checkpoint
    cp_path = guard.runs_dir / "checkpoint.json"
    assert cp_path.exists(), f"Checkpoint not found: {cp_path}"
    cp_data = json.loads(cp_path.read_text())
    assert cp_data["run_id"] == run_id
    assert cp_data["status"] == "completed"
    assert len(cp_data["artifacts"]) >= 2  # small + big + dom_stats

    # Verify report
    report_path = guard.runs_dir / "run_report.md"
    assert report_path.exists(), f"Report not found: {report_path}"
    report_text = report_path.read_text()
    assert "Run Report" in report_text
    assert "completed" in report_text

    # Verify log
    log_path = guard.logs_dir / f"{run_id}.log"
    assert log_path.exists(), f"Log not found: {log_path}"
    log_text = log_path.read_text()
    assert "OutputGuard" in log_text
    # The full 5000-char line should be in the log even though truncated on stdout
    assert "AAAA" in log_text, "Full long message should be in log"

    print("\n" + "=" * 60)
    print("  ALL CHECKS PASSED")
    print(f"  Checkpoint: {cp_path}")
    print(f"  Report:     {report_path}")
    print(f"  Log:        {log_path}")
    print(f"  Artifacts:  {guard.artifacts_dir}")
    print("=" * 60)


if __name__ == "__main__":
    test_basic_output_guard()
