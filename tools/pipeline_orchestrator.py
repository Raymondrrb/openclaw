#!/usr/bin/env python3
"""DEPRECATED — Legacy wrapper for ``tools/pipeline.py``.

Migration:
    # Old                                       # New
    pipeline_orchestrator.py --step 1            pipeline.py generate-script --run-id RUN
    pipeline_orchestrator.py --step 2            pipeline.py generate-assets --run-id RUN
    pipeline_orchestrator.py --step 3            pipeline.py generate-voice --run-id RUN
    pipeline_orchestrator.py --step 4            pipeline.py build-davinci --run-id RUN
    pipeline_orchestrator.py --step 5            pipeline.py render-and-upload --run-id RUN
    pipeline_orchestrator.py --step 6            pipeline.py collect-metrics --run-id RUN

Gate commands (no step number):
    pipeline.py approve-gate1 --run-id RUN --reviewer Ray --notes GO
    pipeline.py approve-gate2 --run-id RUN --reviewer Ray --notes GO

This wrapper will be removed in a future release.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PIPELINE = BASE_DIR / "tools" / "pipeline.py"

STEP_TO_COMMAND = {
    0: "init-run",
    1: "discover-products",
    2: "generate-script",
    3: "generate-assets",
    4: "generate-voice",
    5: "build-davinci",
    6: "render-and-upload",
    7: "collect-metrics",
    8: "status",
    9: "run-e2e",
    # Gate commands (not numbered steps):
    # approve-gate1, reject-gate1, approve-gate2, reject-gate2
}


def run_pipeline(run_id: str, command: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(PIPELINE), command, "--run-id", run_id]
    if extra:
        cmd.extend(extra)
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Legacy wrapper. Use tools/pipeline.py directly.")
    parser.add_argument("--run-dir", required=True, help="Path to run directory (pipeline_runs/<run_id>)")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--step", type=int, help="Run one step (1-6)")
    parser.add_argument("--from-step", type=int, default=1, help="Start step (1-6)")
    parser.add_argument("--to-step", type=int, default=6, help="End step (1-6)")
    args = parser.parse_args()

    run_id = Path(args.run_dir).name

    print("=" * 60)
    print("  DEPRECATED: tools/pipeline_orchestrator.py")
    print("  Use instead: python3 tools/pipeline.py <command> --run-id RUN")
    print("  See docstring for full migration table.")
    print("=" * 60)

    if args.status:
        return run_pipeline(run_id, "status")

    if args.step is not None:
        cmd = STEP_TO_COMMAND.get(int(args.step))
        if not cmd:
            print(f"[ERROR] invalid --step {args.step}; expected 1..6")
            return 1
        return run_pipeline(run_id, cmd)

    for n in range(int(args.from_step), int(args.to_step) + 1):
        cmd = STEP_TO_COMMAND.get(n)
        if not cmd:
            continue
        code = run_pipeline(run_id, cmd)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
