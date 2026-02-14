"""Job worker — executes jobs in controlled workspaces.

Runs jobs using the Anthropic API (Claude) with:
- Isolated workspace per job
- Allowlisted tool execution only
- Permission gating for risky actions
- Periodic checkpoint updates
- Structured artifact production

Stdlib only (plus urllib for API calls) — no external deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from tools.lib.job_system import (
    JOBS_ROOT,
    Job,
    PermissionRequest,
    add_artifact,
    append_log,
    block_job,
    complete_job,
    fail_job,
    load_job,
    save_job,
    start_job,
    update_checkpoint,
)
from tools.lib.notify import send_telegram

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = os.environ.get("JOB_WORKER_MODEL", "claude-sonnet-4-5-20250929")
ANTHROPIC_MAX_TOKENS = 4096

# Allowlisted tools the worker can use
ALLOWED_TOOLS = {
    "web_search",       # search the web for information
    "read_file",        # read a file in the workspace
    "write_file",       # write a file in the workspace
    "list_files",       # list files in the workspace
    "read_url",         # fetch a URL and extract text
    "summarize",        # summarize text
    "pipeline_status",  # check pipeline status
}

# Actions that require permission
RISKY_ACTIONS = {
    "install_package": ("medium", "Install a package via pip/npm"),
    "run_script": ("medium", "Execute a script file"),
    "network_request": ("low", "Make an HTTP request to a non-allowlisted domain"),
    "modify_config": ("high", "Modify a configuration file"),
    "deploy": ("high", "Deploy or restart a service"),
}

# Domains allowed without permission
ALLOWED_DOMAINS = {
    "nytimes.com", "rtings.com", "pcmag.com",
    "amazon.com", "dzine.ai",
    "api.anthropic.com", "api.openai.com",
}

# Max iterations per job run (safety limit)
MAX_ITERATIONS = 20

# Checkpoint interval (iterations)
CHECKPOINT_INTERVAL = 5


# ---------------------------------------------------------------------------
# Anthropic API client (stdlib)
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    """Get Anthropic API key from environment."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return key


def _call_anthropic(
    messages: list[dict],
    system: str = "",
    tools: list[dict] | None = None,
) -> dict:
    """Call the Anthropic Messages API."""
    api_key = _get_api_key()

    body: dict = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic API error {e.code}: {error_body}") from e


# ---------------------------------------------------------------------------
# Tool definitions for Claude
# ---------------------------------------------------------------------------


CLAUDE_TOOLS = [
    {
        "name": "write_file",
        "description": "Write content to a file in the job workspace. Use for notes, output, plans.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename relative to workspace (e.g., 'output.md')"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the job workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename relative to workspace"},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in the job workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Subdirectory to list (default: root)", "default": "."},
            },
        },
    },
    {
        "name": "add_source",
        "description": "Add a source to sources.json with URL, title, and notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "reliability": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["url", "title"],
        },
    },
    {
        "name": "update_checkpoint",
        "description": "Update the job's checkpoint summary (visible to admin via /checkpoint).",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Current progress summary"},
                "progress_percent": {"type": "integer", "description": "Progress 0-100"},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "request_permission",
        "description": "Request admin permission for a risky action. Job will be blocked until approved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "What you want to do"},
                "reason": {"type": "string", "description": "Why it's needed"},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "safe_alternative": {"type": "string", "description": "What to do if denied"},
            },
            "required": ["action", "reason"],
        },
    },
    {
        "name": "complete",
        "description": "Mark the job as completed with a final summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Final completion summary"},
            },
            "required": ["summary"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool execution (safe, workspace-scoped)
# ---------------------------------------------------------------------------


def _execute_tool(job: Job, tool_name: str, tool_input: dict) -> str:
    """Execute a tool call safely within the job's workspace."""
    ws = job.workspace

    if tool_name == "write_file":
        filename = tool_input["filename"]
        content = tool_input["content"]
        # Security: prevent path traversal
        target = (ws / filename).resolve()
        if not str(target).startswith(str(ws.resolve())):
            return "Error: path traversal not allowed."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        append_log(job, f"Wrote file: {filename} ({len(content)} chars)")
        return f"Written: {filename}"

    if tool_name == "read_file":
        filename = tool_input["filename"]
        target = (ws / filename).resolve()
        if not str(target).startswith(str(ws.resolve())):
            return "Error: path traversal not allowed."
        if not target.is_file():
            return f"File not found: {filename}"
        content = target.read_text(encoding="utf-8")
        if len(content) > 10000:
            content = content[:10000] + "\n... (truncated at 10000 chars)"
        return content

    if tool_name == "list_files":
        subpath = tool_input.get("path", ".")
        target = (ws / subpath).resolve()
        if not str(target).startswith(str(ws.resolve())):
            return "Error: path traversal not allowed."
        if not target.is_dir():
            return f"Not a directory: {subpath}"
        files = sorted(target.iterdir())
        return "\n".join(
            f"{'[DIR] ' if f.is_dir() else ''}{f.name}"
            for f in files
        )

    if tool_name == "add_source":
        sources_path = ws / "sources.json"
        sources = []
        if sources_path.is_file():
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
        source = {
            "url": tool_input.get("url", ""),
            "title": tool_input.get("title", ""),
            "notes": tool_input.get("notes", ""),
            "reliability": tool_input.get("reliability", "medium"),
            "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        sources.append(source)
        sources_path.write_text(json.dumps(sources, indent=2), encoding="utf-8")
        append_log(job, f"Added source: {source['title']}")
        return f"Source added ({len(sources)} total)"

    if tool_name == "update_checkpoint":
        summary = tool_input["summary"]
        progress = tool_input.get("progress_percent", -1)
        update_checkpoint(job, summary, progress)
        append_log(job, f"Checkpoint: {summary[:80]}")
        return "Checkpoint updated."

    if tool_name == "request_permission":
        perm = PermissionRequest(
            perm_id="",
            job_id=job.id,
            action=tool_input["action"],
            reason=tool_input["reason"],
            risk_level=tool_input.get("risk_level", "medium"),
            safe_alternative=tool_input.get("safe_alternative", ""),
        )
        block_job(job, perm)
        append_log(job, f"Permission requested: {perm.action}")
        # Notify admin via Telegram
        _notify_permission_request(job, perm)
        return f"Permission requested (ID: {perm.perm_id}). Job blocked until approved."

    if tool_name == "complete":
        summary = tool_input["summary"]
        # Register output.md as artifact if it exists
        output_md = ws / "output.md"
        if output_md.is_file():
            add_artifact(job, "output.md", output_md.read_text(encoding="utf-8"), "text/markdown")
        complete_job(job, summary=summary)
        append_log(job, f"Completed: {summary[:80]}")
        _notify_completion(job)
        return "Job completed."

    return f"Unknown tool: {tool_name}"


# ---------------------------------------------------------------------------
# Telegram notifications
# ---------------------------------------------------------------------------


def _notify_permission_request(job: Job, perm: PermissionRequest) -> None:
    """Send Telegram notification for a permission request."""
    msg = (
        f"[Rayviews Lab] Job {job.id} BLOCKED\n"
        f"Title: {job.title}\n"
        f"Permission requested: {perm.action}\n"
        f"Reason: {perm.reason}\n"
        f"Risk: {perm.risk_level}\n"
    )
    if perm.safe_alternative:
        msg += f"Alternative: {perm.safe_alternative}\n"
    msg += f"\n/approve {perm.perm_id}  |  /deny {perm.perm_id}"
    try:
        send_telegram(msg)
    except Exception:
        pass  # Don't fail the job over a notification


def _notify_completion(job: Job) -> None:
    """Send Telegram notification for job completion."""
    msg = (
        f"[Rayviews Lab] Job {job.id} COMPLETED\n"
        f"Title: {job.title}\n"
        f"Summary: {job.checkpoint[:200]}\n"
        f"Artifacts: {len(job.artifacts)}\n"
        f"\n/artifacts {job.id}"
    )
    try:
        send_telegram(msg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Job runner
# ---------------------------------------------------------------------------


def _build_system_prompt(job: Job) -> str:
    """Build the system prompt for a job based on its type."""
    base = (
        "You are a research and operations assistant for Rayviews Lab, "
        "an Amazon Associates YouTube channel that produces Top 5 product ranking videos.\n\n"
        "You are executing a job in an isolated workspace. Use the provided tools to:\n"
        "- Read and write files in your workspace\n"
        "- Track sources with add_source\n"
        "- Update checkpoints so the admin can monitor progress\n"
        "- Request permission for any risky actions\n"
        "- Mark the job complete when done\n\n"
        "Important rules:\n"
        "- Work only within your workspace directory\n"
        "- Do NOT execute arbitrary shell commands\n"
        "- Request permission for anything that could have side effects\n"
        "- Be thorough but efficient\n"
        "- Update checkpoints regularly\n"
    )

    if job.job_type == "study":
        base += (
            "\nThis is a STUDY task. Follow this approach:\n"
            "Phase 1 (20%): Quick landscape map — identify key concepts and subtopics\n"
            "Phase 2 (60%): Deep dive into the 2-3 most important subtopics\n"
            "Phase 3 (20%): Verify, cross-check, and synthesize findings\n\n"
            "Write your findings to output.md. Track sources in sources.json.\n"
            "Stop when the done criteria in plan.md are met, not infinite browsing.\n"
        )

    if job.instructions:
        base += "\nAdditional instructions from admin:\n"
        for i, instr in enumerate(job.instructions, 1):
            base += f"{i}. {instr}\n"

    return base


def run_job(job_id: str) -> None:
    """Run a job to completion (or until blocked/failed)."""
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    if job.status not in ("queued", "running"):
        raise ValueError(f"Job {job_id} is {job.status}, cannot run")

    start_job(job)
    append_log(job, f"Job started: {job.title}")

    system_prompt = _build_system_prompt(job)
    messages: list[dict] = [
        {"role": "user", "content": job.prompt},
    ]

    # If workspace has existing files, include context
    ws = job.workspace
    plan_path = ws / "plan.md"
    if plan_path.is_file():
        plan_content = plan_path.read_text(encoding="utf-8")
        messages[0]["content"] += f"\n\nExisting plan:\n{plan_content}"

    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1

        # Check if job was canceled externally
        fresh = load_job(job_id)
        if fresh and fresh.status == "canceled":
            append_log(job, "Job canceled by admin.")
            return

        # Check if job was blocked (permission pending)
        if fresh and fresh.status == "blocked":
            append_log(job, "Job blocked, waiting for permission approval.")
            return

        try:
            response = _call_anthropic(
                messages=messages,
                system=system_prompt,
                tools=CLAUDE_TOOLS,
            )
        except Exception as e:
            fail_job(job, f"API error: {e}")
            append_log(job, f"API error: {e}")
            return

        # Process response
        content = response.get("content", [])
        stop_reason = response.get("stop_reason", "")

        # Collect text and tool_use blocks
        text_parts: list[str] = []
        tool_uses: list[dict] = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                tool_uses.append(block)

        # Add assistant message to history
        messages.append({"role": "assistant", "content": content})

        # If no tool uses, we're done with this turn
        if not tool_uses:
            if text_parts:
                append_log(job, f"Claude: {text_parts[0][:200]}")
            break

        # Execute tools
        tool_results: list[dict] = []
        job_blocked = False
        job_completed = False

        for tool_use in tool_uses:
            tool_name = tool_use["name"]
            tool_input = tool_use.get("input", {})
            tool_id = tool_use["id"]

            append_log(job, f"Tool: {tool_name}({json.dumps(tool_input)[:100]})")
            result = _execute_tool(job, tool_name, tool_input)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })

            if tool_name == "request_permission":
                job_blocked = True
            if tool_name == "complete":
                job_completed = True

        # Add tool results to messages
        messages.append({"role": "user", "content": tool_results})

        if job_blocked:
            return  # Wait for permission
        if job_completed:
            return  # Done

        # Periodic checkpoint
        if iteration % CHECKPOINT_INTERVAL == 0:
            update_checkpoint(job, f"Iteration {iteration}/{MAX_ITERATIONS}", iteration * 100 // MAX_ITERATIONS)

    # Max iterations reached
    if job.status == "running":
        update_checkpoint(job, f"Reached max iterations ({MAX_ITERATIONS}). Review and /continue if needed.")
        append_log(job, f"Max iterations ({MAX_ITERATIONS}) reached.")
        # Don't fail — mark as needing continuation
        job.status = "blocked"
        perm = PermissionRequest(
            perm_id="",
            job_id=job.id,
            action="Continue past iteration limit",
            reason=f"Reached {MAX_ITERATIONS} iterations without completing",
            risk_level="low",
            safe_alternative="Cancel or review current output",
        )
        block_job(job, perm)


def resume_job(job_id: str) -> None:
    """Resume a job after permission was approved."""
    job = load_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    if job.status != "running":
        raise ValueError(f"Job {job_id} is {job.status}, cannot resume (must be running after approval)")

    append_log(job, "Job resumed after permission approval.")
    run_job(job_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    """Run a job from command line."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m tools.lib.job_worker <job_id>")
        print("       python -m tools.lib.job_worker --resume <job_id>")
        sys.exit(1)

    if sys.argv[1] == "--resume":
        if len(sys.argv) < 3:
            print("Usage: python -m tools.lib.job_worker --resume <job_id>")
            sys.exit(1)
        resume_job(sys.argv[2])
    else:
        run_job(sys.argv[1])


if __name__ == "__main__":
    main()
