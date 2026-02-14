#!/usr/bin/env python3
"""Stable exploration runner — wraps any explore_dzine*.py script with output guards.

Captures stdout/stderr, truncates console output, writes full logs to disk,
manages artifacts, and produces checkpoint.json + run_report.md.

Usage:
    python tools/stable_run.py --script explore_dzine161.py --run-id dzine_161_stable
    python tools/stable_run.py --script explore_dzine161.py  # auto-generates run_id
    RAY_TOKEN_MODE=1 python tools/stable_run.py --script explore_dzine161.py  # strict mode

Output structure:
    logs/<run_id>.log            Full captured stdout+stderr
    artifacts/<run_id>/          Screenshots, DOM dumps, JSON artifacts
    runs/<run_id>/checkpoint.json  { run_id, script_name, status, artifacts, next_step }
    runs/<run_id>/run_report.md    Human-readable summary
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a Dzine exploration script with output guards",
    )
    parser.add_argument(
        "--script",
        required=True,
        help="Script filename (e.g. explore_dzine161.py). Resolved relative to tools/",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Run identifier. Auto-generated from script name + timestamp if omitted.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=30,
        help="Max stdout lines to show in console (default: 30)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds before killing the script (default: 300)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be run without executing",
    )
    args = parser.parse_args()

    # Resolve paths
    repo_root = Path(__file__).resolve().parent.parent
    tools_dir = repo_root / "tools"
    script_path = tools_dir / args.script
    if not script_path.exists():
        # Try as absolute or relative to cwd
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"ERROR: Script not found: {args.script}")
            return 1

    # Generate run_id
    if args.run_id:
        run_id = args.run_id
    else:
        stem = script_path.stem
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{stem}_{ts}"

    # Output dirs
    logs_dir = repo_root / "logs"
    artifacts_dir = repo_root / "artifacts" / run_id
    runs_dir = repo_root / "runs" / run_id

    for d in (logs_dir, artifacts_dir, runs_dir):
        d.mkdir(parents=True, exist_ok=True)

    log_path = logs_dir / f"{run_id}.log"
    checkpoint_path = runs_dir / "checkpoint.json"
    report_path = runs_dir / "run_report.md"

    # Token mode
    strict = os.environ.get("RAY_TOKEN_MODE", "") == "1"
    max_lines = args.max_lines // 2 if strict else args.max_lines

    if args.dry_run:
        print(f"DRY RUN:")
        print(f"  Script:     {script_path}")
        print(f"  Run ID:     {run_id}")
        print(f"  Log:        {log_path}")
        print(f"  Artifacts:  {artifacts_dir}")
        print(f"  Checkpoint: {checkpoint_path}")
        print(f"  Max lines:  {max_lines}")
        print(f"  Timeout:    {args.timeout}s")
        print(f"  Token mode: {'STRICT' if strict else 'normal'}")
        return 0

    # Banner
    started_at = datetime.now(timezone.utc).isoformat()
    print(f"{'=' * 60}")
    print(f"  stable_run: {args.script}")
    print(f"  run_id:     {run_id}")
    print(f"  mode:       {'STRICT' if strict else 'normal'}")
    print(f"  max_lines:  {max_lines}")
    print(f"  timeout:    {args.timeout}s")
    print(f"{'=' * 60}")

    # Set up environment for child process
    env = os.environ.copy()
    env["STABLE_RUN_ID"] = run_id
    env["STABLE_RUN_ARTIFACTS"] = str(artifacts_dir)
    env["STABLE_RUN_BASE"] = str(repo_root)

    # Run script, capturing output
    start_ts = time.monotonic()
    status = "completed"
    return_code = 0
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(tools_dir),
            text=True,
            bufsize=1,
        )

        # Read output with timeout
        console_lines_shown = 0

        def stream_output(pipe, lines_list: list, prefix: str = ""):
            nonlocal console_lines_shown
            for line in pipe:
                line = line.rstrip("\n")
                lines_list.append(line)
                if console_lines_shown < max_lines:
                    display = line
                    if len(display) > 200:
                        display = display[:197] + "..."
                    print(f"{prefix}{display}", flush=True)
                    console_lines_shown += 1
                elif console_lines_shown == max_lines:
                    print(f"  [stable_run] stdout cap ({max_lines} lines) — rest in {log_path.name}", flush=True)
                    console_lines_shown += 1

        # We need to handle both streams. Use threads for simplicity.
        import threading
        stdout_thread = threading.Thread(
            target=stream_output, args=(proc.stdout, stdout_lines, "")
        )
        stderr_thread = threading.Thread(
            target=stream_output, args=(proc.stderr, stderr_lines, "ERR: ")
        )
        stdout_thread.start()
        stderr_thread.start()

        # Wait with timeout
        try:
            return_code = proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            status = "timeout"
            return_code = -1
            print(f"\n  [stable_run] TIMEOUT after {args.timeout}s — killed", flush=True)

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        if return_code != 0 and status != "timeout":
            status = "error"

    except Exception as e:
        status = "crash"
        return_code = -2
        stderr_lines.append(f"stable_run crash: {e}")
        print(f"\n  [stable_run] CRASH: {e}", flush=True)

    elapsed = round(time.monotonic() - start_ts, 1)
    finished_at = datetime.now(timezone.utc).isoformat()

    # Write full log to disk
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== stable_run log: {run_id} ===\n")
        f.write(f"Script: {script_path}\n")
        f.write(f"Started: {started_at}\n")
        f.write(f"Finished: {finished_at}\n")
        f.write(f"Status: {status}\n")
        f.write(f"Return code: {return_code}\n")
        f.write(f"Elapsed: {elapsed}s\n")
        f.write(f"\n{'=' * 40} STDOUT {'=' * 40}\n")
        for line in stdout_lines:
            f.write(line + "\n")
        if stderr_lines:
            f.write(f"\n{'=' * 40} STDERR {'=' * 40}\n")
            for line in stderr_lines:
                f.write(line + "\n")

    # Collect artifacts list
    artifacts_list = []
    if artifacts_dir.exists():
        for p in sorted(artifacts_dir.iterdir()):
            artifacts_list.append({
                "name": p.name,
                "bytes": p.stat().st_size,
            })

    # Write checkpoint
    checkpoint = {
        "run_id": run_id,
        "script_name": args.script,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed,
        "status": status,
        "return_code": return_code,
        "stdout_lines": len(stdout_lines),
        "stderr_lines": len(stderr_lines),
        "artifacts": artifacts_list,
        "next_step": "",
        "log_file": str(log_path),
    }
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2))

    # Write run report
    report = [
        f"# Run Report: {run_id}",
        "",
        f"- **Script:** `{args.script}`",
        f"- **Status:** {status}",
        f"- **Return code:** {return_code}",
        f"- **Duration:** {elapsed}s",
        f"- **Started:** {started_at}",
        f"- **Finished:** {finished_at}",
        "",
        "## Output",
        f"- stdout: {len(stdout_lines)} lines",
        f"- stderr: {len(stderr_lines)} lines",
        f"- console shown: {min(console_lines_shown, max_lines)}/{max_lines} max",
        f"- full log: `{log_path}`",
        "",
    ]

    if artifacts_list:
        report.append("## Artifacts")
        total_bytes = sum(a["bytes"] for a in artifacts_list)
        report.append(f"- Total: {len(artifacts_list)} files, {total_bytes:,} bytes")
        for a in artifacts_list[:20]:
            report.append(f"- `{a['name']}` ({a['bytes']:,} bytes)")
        if len(artifacts_list) > 20:
            report.append(f"- … +{len(artifacts_list) - 20} more")
        report.append("")

    if stderr_lines:
        report.append("## Errors (last 10 lines)")
        for line in stderr_lines[-10:]:
            report.append(f"    {line[:200]}")
        report.append("")

    report_path.write_text("\n".join(report))

    # Final banner
    print(f"\n{'=' * 60}")
    print(f"  stable_run complete")
    print(f"  Status:     {status}")
    print(f"  Duration:   {elapsed}s")
    print(f"  Output:     {len(stdout_lines)} lines (showed {min(console_lines_shown, max_lines)})")
    print(f"  Artifacts:  {len(artifacts_list)}")
    print(f"  Log:        {log_path}")
    print(f"  Report:     {report_path}")
    print(f"  Checkpoint: {checkpoint_path}")
    print(f"{'=' * 60}")

    return 0 if status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
