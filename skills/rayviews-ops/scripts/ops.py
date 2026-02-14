#!/usr/bin/env python3
"""Rayviews Ops — Telegram command handler for pipeline control and job management.

This skill handles admin commands from Telegram, routing them to:
1. Pipeline operations (safe allowlist)
2. Job system (task creation, monitoring, approval)
3. Status/monitoring queries

Admin-only. No arbitrary shell execution.
Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

# Add project root to path so we can import tools.lib
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from tools.lib.job_system import (
    ADMIN_IDS,
    PIPELINE_COMMANDS,
    Job,
    add_instruction,
    approve_permission,
    cancel_job,
    check_concurrency,
    check_rate_limit,
    create_job,
    deny_permission,
    format_job_list,
    format_job_status,
    format_permission_list,
    init_study_workspace,
    is_admin,
    list_jobs,
    list_pending_permissions,
    load_job,
    log_admin_action,
    read_logs,
    start_job,
)

# Two-step confirmation store (in-memory, resets on restart)
_pending_confirms: dict[str, dict] = {}


def _confirm_token() -> str:
    import secrets
    return secrets.token_hex(2)


# ---------------------------------------------------------------------------
# Command router
# ---------------------------------------------------------------------------


def handle_command(text: str, admin_id: int) -> str:
    """Route a command to the appropriate handler. Returns response text."""
    if not is_admin(admin_id):
        return "Unauthorized."

    text = text.strip()
    if not text:
        return "Empty command."

    # Parse command and args
    parts = text.split(None, 1)
    cmd = parts[0].lower().lstrip("/").lstrip("!")
    args_str = parts[1].strip() if len(parts) > 1 else ""

    log_admin_action(admin_id, cmd, {"args": args_str})

    # Route
    handlers = {
        "task": _handle_task,
        "status": _handle_status,
        "logs": _handle_logs,
        "checkpoint": _handle_checkpoint,
        "cancel": _handle_cancel,
        "list": _handle_list,
        "continue": _handle_continue,
        "artifacts": _handle_artifacts,
        "get": _handle_get_artifact,
        "approve": _handle_approve,
        "deny": _handle_deny,
        "pending": _handle_pending,
        "pipeline": _handle_pipeline_status,
        "pipeline-status": _handle_pipeline_status,
        "run": _handle_pipeline_run,
        "confirm": _handle_confirm,
        "help": _handle_help,
    }

    handler = handlers.get(cmd)
    if handler:
        return handler(args_str, admin_id)

    return f"Unknown command: /{cmd}\nUse /help for available commands."


# ---------------------------------------------------------------------------
# Job commands
# ---------------------------------------------------------------------------


def _handle_task(args: str, admin_id: int) -> str:
    """Create a new task/job."""
    if not args:
        return "Usage: /task <title or natural language prompt>"

    # Rate limit
    rate_msg = check_rate_limit(admin_id)
    if rate_msg:
        return rate_msg

    # Concurrency
    conc_msg = check_concurrency()
    if conc_msg:
        return conc_msg

    # Detect study task
    lower = args.lower()
    is_study = any(kw in lower for kw in ("study", "research", "investigate", "explore", "learn about"))
    job_type = "study" if is_study else "general"

    # Extract topic for study tasks
    title = args[:100] if len(args) > 100 else args

    job = create_job(
        title=title,
        prompt=args,
        admin_id=admin_id,
        job_type=job_type,
    )

    if is_study:
        # Extract topic (remove study/research prefix)
        topic = args
        for prefix in ("study ", "research ", "investigate ", "explore ", "learn about "):
            if lower.startswith(prefix):
                topic = args[len(prefix):]
                break
        init_study_workspace(job, topic)

    response = [
        f"Job created: {job.id}",
        f"Title: {title}",
        f"Type: {job_type}",
        f"Status: queued",
    ]
    if is_study:
        response.append("Study workspace initialized with plan.md, sources.json, output.md")
    response.append(f"\nUse /status {job.id} to check progress.")

    return "\n".join(response)


def _handle_status(args: str, admin_id: int) -> str:
    """Show job status."""
    job_id = args.strip()
    if not job_id:
        # Show status of most recent job
        jobs = list_jobs(limit=1)
        if not jobs:
            return "No jobs found."
        return format_job_status(jobs[0])

    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."
    return format_job_status(job)


def _handle_logs(args: str, admin_id: int) -> str:
    """Show job logs."""
    parts = args.strip().split()
    if not parts:
        return "Usage: /logs <job_id> [last N]"
    job_id = parts[0]
    last_n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 50

    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."

    logs = read_logs(job, last_n)
    if not logs.strip():
        return f"Job {job_id}: no logs yet."
    return f"Logs for job {job_id} (last {last_n}):\n\n{logs}"


def _handle_checkpoint(args: str, admin_id: int) -> str:
    """Show job checkpoint."""
    job_id = args.strip()
    if not job_id:
        return "Usage: /checkpoint <job_id>"

    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."

    if not job.checkpoint:
        return f"Job {job_id}: no checkpoint yet."
    return f"Checkpoint for job {job_id}:\n\n{job.checkpoint}"


def _handle_cancel(args: str, admin_id: int) -> str:
    """Cancel a job."""
    job_id = args.strip()
    if not job_id:
        return "Usage: /cancel <job_id>"

    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."
    if job.status in ("completed", "failed", "canceled"):
        return f"Job {job_id} is already {job.status}."

    cancel_job(job)
    return f"Job {job_id} canceled."


def _handle_list(args: str, admin_id: int) -> str:
    """List recent jobs."""
    status_filter = args.strip() if args.strip() else ""
    jobs = list_jobs(limit=20, status=status_filter)
    return format_job_list(jobs)


def _handle_continue(args: str, admin_id: int) -> str:
    """Add instruction to a running job."""
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return "Usage: /continue <job_id> <instruction>"

    job_id = parts[0]
    instruction = parts[1]

    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."
    if job.status not in ("running", "queued", "blocked"):
        return f"Job {job_id} is {job.status}. Cannot add instructions."

    add_instruction(job, instruction)
    return f"Instruction added to job {job_id}: {instruction[:80]}..."


def _handle_artifacts(args: str, admin_id: int) -> str:
    """List job artifacts."""
    job_id = args.strip()
    if not job_id:
        return "Usage: /artifacts <job_id>"

    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."

    if not job.artifacts:
        return f"Job {job_id}: no artifacts."

    lines = [f"Artifacts for job {job_id}:"]
    for a in job.artifacts:
        lines.append(f"  - {a.name} ({a.mime_type})")
    lines.append(f"\nUse /get {job_id} <name> to retrieve.")
    return "\n".join(lines)


def _handle_get_artifact(args: str, admin_id: int) -> str:
    """Get artifact content."""
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return "Usage: /get <job_id> <artifact_name>"

    job_id, artifact_name = parts[0], parts[1]
    job = load_job(job_id)
    if not job:
        return f"Job {job_id} not found."

    for a in job.artifacts:
        if a.name == artifact_name:
            try:
                content = open(a.path, encoding="utf-8").read()
                # Telegram message limit is ~4096 chars
                if len(content) > 3800:
                    content = content[:3800] + "\n\n... (truncated)"
                return f"Artifact: {a.name}\n\n{content}"
            except (OSError, FileNotFoundError):
                return f"Artifact file not found: {a.path}"

    return f"Artifact '{artifact_name}' not found in job {job_id}."


# ---------------------------------------------------------------------------
# Permission commands
# ---------------------------------------------------------------------------


def _handle_approve(args: str, admin_id: int) -> str:
    """Approve a permission request."""
    perm_id = args.strip()
    if not perm_id:
        return "Usage: /approve <perm_id>"

    job, perm = approve_permission(perm_id)
    if not job or not perm:
        return f"Permission {perm_id} not found or already resolved."

    return f"Approved: {perm.action}\nJob {job.id} status: {job.status}"


def _handle_deny(args: str, admin_id: int) -> str:
    """Deny a permission request."""
    perm_id = args.strip()
    if not perm_id:
        return "Usage: /deny <perm_id>"

    job, perm = deny_permission(perm_id)
    if not job or not perm:
        return f"Permission {perm_id} not found or already resolved."

    return f"Denied: {perm.action}\nJob {job.id} remains blocked. Worker will use safe alternative or fail."


def _handle_pending(args: str, admin_id: int) -> str:
    """List pending permission requests."""
    pending = list_pending_permissions()
    return format_permission_list(pending)


# ---------------------------------------------------------------------------
# Pipeline commands (safe allowlist)
# ---------------------------------------------------------------------------


def _handle_pipeline_status(args: str, admin_id: int) -> str:
    """Show pipeline status."""
    video_id = args.strip()
    if not video_id:
        return "Usage: /pipeline-status <video_id>"

    cmd = PIPELINE_COMMANDS["status"]
    full_cmd = cmd["cmd"] + ["--video-id", video_id]
    return _run_safe_command(full_cmd, timeout=30)


def _handle_pipeline_run(args: str, admin_id: int) -> str:
    """Run a pipeline stage. Requires two-step confirmation for full runs."""
    parts = args.strip().split()
    if len(parts) < 2:
        return (
            "Usage: /run <stage> <video_id>\n"
            "Stages: research, verify, script, assets, tts, manifest, run, day"
        )

    stage, video_id = parts[0].lower(), parts[1]

    if stage not in PIPELINE_COMMANDS:
        return f"Unknown stage: {stage}\nAvailable: {', '.join(PIPELINE_COMMANDS.keys())}"

    cmd_spec = PIPELINE_COMMANDS[stage]

    # Full pipeline run requires confirmation
    if stage in ("run", "day"):
        token = _confirm_token()
        _pending_confirms[token] = {
            "cmd": cmd_spec["cmd"] + ["--video-id", video_id],
            "stage": stage,
            "video_id": video_id,
            "admin_id": admin_id,
            "created_at": time.time(),
        }
        return (
            f"Full pipeline {stage} for {video_id} requires confirmation.\n"
            f"Confirm with: /confirm {token}"
        )

    full_cmd = cmd_spec["cmd"] + ["--video-id", video_id]
    return _run_safe_command(full_cmd, timeout=300)


def _handle_confirm(args: str, admin_id: int) -> str:
    """Confirm a two-step operation."""
    token = args.strip()
    if not token:
        return "Usage: /confirm <token>"

    pending = _pending_confirms.pop(token, None)
    if not pending:
        return f"Confirmation token {token} not found or expired."

    # Check expiry (5 minutes)
    if time.time() - pending["created_at"] > 300:
        return "Confirmation expired. Re-run the command."

    if pending["admin_id"] != admin_id:
        return "Confirmation token belongs to a different admin."

    return _run_safe_command(pending["cmd"], timeout=600)


def _run_safe_command(cmd: list[str], timeout: int = 120) -> str:
    """Run a safe, allowlisted command and return output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip()
            return f"Command failed (exit {result.returncode}):\n{error}\n\n{output}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s."
    except Exception as e:
        return f"Command error: {e}"


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


def _handle_help(args: str, admin_id: int) -> str:
    """Show available commands."""
    return """Rayviews Ops Commands:

Job Control:
  /task <prompt>          — Create a new job
  /status [job_id]        — Show job status
  /logs <job_id> [N]      — Show last N log lines
  /checkpoint <job_id>    — Show current checkpoint
  /cancel <job_id>        — Cancel a job
  /list [status]          — List recent jobs
  /continue <job_id> <msg>— Add instruction to job

Artifacts:
  /artifacts <job_id>     — List artifacts
  /get <job_id> <name>    — Get artifact content

Permissions:
  /approve <perm_id>      — Approve permission
  /deny <perm_id>         — Deny permission
  /pending                — List pending permissions

Pipeline:
  /pipeline-status <vid>  — Show pipeline status
  /run <stage> <vid>      — Run pipeline stage
    Stages: research, verify, script, assets, tts, manifest, run, day

Other:
  /help                   — This message"""


# ---------------------------------------------------------------------------
# Main (for OpenClaw skill execution)
# ---------------------------------------------------------------------------


def main():
    """Entry point when called as an OpenClaw skill."""
    # Read command from stdin or args
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read().strip()

    if not text:
        print(_handle_help("", 0))
        return

    # In skill context, the admin ID comes from the Telegram context
    # For now, use the first admin ID (single-admin system)
    admin_id = next(iter(ADMIN_IDS))
    result = handle_command(text, admin_id)
    print(result)


if __name__ == "__main__":
    main()
