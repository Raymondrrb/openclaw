"""Job system for Telegram-controlled task execution.

Admin-only, allowlist-based job queue with permission gating.
Each job runs in an isolated workspace with structured artifacts.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

JOBS_ROOT = Path(os.environ.get("RAYVIEWS_JOBS_ROOT", "jobs"))

JOB_STATUS = Literal[
    "queued", "running", "blocked", "completed", "failed", "canceled"
]

RISK_LEVEL = Literal["low", "medium", "high"]

# Admin Telegram user IDs (strict whitelist)
ADMIN_IDS: set[int] = {5853624777}

# Rate limit: max jobs created per hour
MAX_JOBS_PER_HOUR = 10

# Max concurrent running jobs
MAX_CONCURRENT_JOBS = 1


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Artifact:
    """A file produced by a job."""
    name: str
    path: str
    mime_type: str = "text/plain"
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _now_iso()


@dataclass
class PermissionRequest:
    """A request for admin approval before a risky action."""
    perm_id: str
    job_id: str
    action: str
    reason: str
    risk_level: RISK_LEVEL = "medium"
    safe_alternative: str = ""
    created_at: str = ""
    approved: bool | None = None  # None = pending, True = approved, False = denied
    resolved_at: str = ""

    def __post_init__(self):
        if not self.perm_id:
            self.perm_id = _short_id()
        if not self.created_at:
            self.created_at = _now_iso()


@dataclass
class Job:
    """A task/job in the queue."""
    id: str
    title: str
    prompt: str = ""
    status: JOB_STATUS = "queued"
    progress_percent: int = 0
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    admin_id: int = 0
    job_type: str = "general"  # general, study, pipeline
    logs_path: str = ""
    artifacts: list[Artifact] = field(default_factory=list)
    permissions: list[PermissionRequest] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    checkpoint: str = ""
    error: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = _short_id()
        if not self.created_at:
            self.created_at = _now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    @property
    def workspace(self) -> Path:
        return JOBS_ROOT / self.id

    @property
    def pending_permissions(self) -> list[PermissionRequest]:
        return [p for p in self.permissions if p.approved is None]

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("workspace", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        artifacts = [Artifact(**a) for a in data.pop("artifacts", [])]
        permissions = [PermissionRequest(**p) for p in data.pop("permissions", [])]
        instructions = data.pop("instructions", [])
        data.pop("pending_permissions", None)
        data.pop("workspace", None)
        return cls(
            artifacts=artifacts,
            permissions=permissions,
            instructions=instructions,
            **data,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_id() -> str:
    """Generate a short alphanumeric job/perm ID."""
    return secrets.token_hex(4)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Job store (filesystem-based)
# ---------------------------------------------------------------------------


def _job_meta_path(job_id: str) -> Path:
    return JOBS_ROOT / job_id / "job.json"


def save_job(job: Job) -> None:
    """Persist job metadata to disk."""
    job.updated_at = _now_iso()
    workspace = job.workspace
    workspace.mkdir(parents=True, exist_ok=True)
    meta = _job_meta_path(job.id)
    meta.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")


def load_job(job_id: str) -> Job | None:
    """Load a job from disk by ID."""
    meta = _job_meta_path(job_id)
    if not meta.is_file():
        return None
    data = json.loads(meta.read_text(encoding="utf-8"))
    return Job.from_dict(data)


def list_jobs(*, limit: int = 20, status: str = "") -> list[Job]:
    """List recent jobs, optionally filtered by status."""
    if not JOBS_ROOT.is_dir():
        return []
    jobs: list[Job] = []
    for entry in sorted(JOBS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_dir():
            continue
        job = load_job(entry.name)
        if job is None:
            continue
        if status and job.status != status:
            continue
        jobs.append(job)
        if len(jobs) >= limit:
            break
    return jobs


def count_recent_jobs(admin_id: int, hours: float = 1.0) -> int:
    """Count jobs created by admin in the last N hours (rate limiting)."""
    cutoff = time.time() - (hours * 3600)
    count = 0
    for job in list_jobs(limit=100):
        if job.admin_id != admin_id:
            continue
        try:
            created = datetime.fromisoformat(job.created_at).timestamp()
        except (ValueError, TypeError):
            continue
        if created >= cutoff:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


def create_job(
    title: str,
    prompt: str,
    admin_id: int,
    *,
    job_type: str = "general",
) -> Job:
    """Create a new job and initialize its workspace."""
    job = Job(
        id=_short_id(),
        title=title,
        prompt=prompt,
        admin_id=admin_id,
        job_type=job_type,
    )
    ws = job.workspace
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "artifacts").mkdir(exist_ok=True)
    (ws / "logs.txt").write_text("", encoding="utf-8")
    job.logs_path = str(ws / "logs.txt")
    save_job(job)
    return job


def start_job(job: Job) -> None:
    """Mark a job as running."""
    job.status = "running"
    job.started_at = _now_iso()
    job.progress_percent = 0
    save_job(job)


def complete_job(job: Job, *, summary: str = "") -> None:
    """Mark a job as completed."""
    job.status = "completed"
    job.progress_percent = 100
    job.completed_at = _now_iso()
    if summary:
        job.checkpoint = summary
    save_job(job)


def fail_job(job: Job, error: str) -> None:
    """Mark a job as failed."""
    job.status = "failed"
    job.completed_at = _now_iso()
    job.error = error
    save_job(job)


def cancel_job(job: Job) -> None:
    """Cancel a job."""
    job.status = "canceled"
    job.completed_at = _now_iso()
    save_job(job)


def block_job(job: Job, perm: PermissionRequest) -> None:
    """Block a job pending permission approval."""
    job.status = "blocked"
    job.permissions.append(perm)
    save_job(job)


def approve_permission(perm_id: str) -> tuple[Job | None, PermissionRequest | None]:
    """Approve a pending permission request. Returns (job, perm) or (None, None)."""
    for job in list_jobs(limit=50, status="blocked"):
        for perm in job.permissions:
            if perm.perm_id == perm_id and perm.approved is None:
                perm.approved = True
                perm.resolved_at = _now_iso()
                # Unblock job if no more pending permissions
                if not job.pending_permissions:
                    job.status = "running"
                save_job(job)
                return job, perm
    return None, None


def deny_permission(perm_id: str) -> tuple[Job | None, PermissionRequest | None]:
    """Deny a pending permission request."""
    for job in list_jobs(limit=50, status="blocked"):
        for perm in job.permissions:
            if perm.perm_id == perm_id and perm.approved is None:
                perm.approved = False
                perm.resolved_at = _now_iso()
                save_job(job)
                return job, perm
    return None, None


def list_pending_permissions() -> list[tuple[Job, PermissionRequest]]:
    """List all pending permission requests across blocked jobs."""
    results: list[tuple[Job, PermissionRequest]] = []
    for job in list_jobs(limit=50, status="blocked"):
        for perm in job.pending_permissions:
            results.append((job, perm))
    return results


def update_checkpoint(job: Job, checkpoint: str, progress: int = -1) -> None:
    """Update job checkpoint and optionally progress."""
    job.checkpoint = checkpoint
    if progress >= 0:
        job.progress_percent = min(progress, 100)
    save_job(job)


def add_instruction(job: Job, instruction: str) -> None:
    """Add a follow-up instruction to a running/queued job."""
    job.instructions.append(instruction)
    save_job(job)


def add_artifact(job: Job, name: str, content: str, mime_type: str = "text/plain") -> Artifact:
    """Write an artifact file and register it on the job."""
    artifact_dir = job.workspace / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    path = artifact_dir / name
    path.write_text(content, encoding="utf-8")
    artifact = Artifact(name=name, path=str(path), mime_type=mime_type)
    job.artifacts.append(artifact)
    save_job(job)
    return artifact


def append_log(job: Job, message: str) -> None:
    """Append a line to the job's log file."""
    log_path = job.workspace / "logs.txt"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{_now_iso()}] {message}\n")


def read_logs(job: Job, last_n: int = 50) -> str:
    """Read the last N lines of the job's log file."""
    log_path = job.workspace / "logs.txt"
    if not log_path.is_file():
        return "(no logs)"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    if last_n > 0:
        lines = lines[-last_n:]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def is_admin(telegram_user_id: int) -> bool:
    """Check if a Telegram user ID is in the admin whitelist."""
    return telegram_user_id in ADMIN_IDS


def check_rate_limit(admin_id: int) -> str | None:
    """Check rate limit. Returns error message if exceeded, None if OK."""
    count = count_recent_jobs(admin_id)
    if count >= MAX_JOBS_PER_HOUR:
        return f"Rate limit: {count}/{MAX_JOBS_PER_HOUR} jobs in the last hour. Wait before creating more."
    return None


def check_concurrency() -> str | None:
    """Check concurrency limit. Returns error message if exceeded, None if OK."""
    running = list_jobs(limit=50, status="running")
    if len(running) >= MAX_CONCURRENT_JOBS:
        ids = ", ".join(j.id for j in running)
        return f"Concurrency limit: {len(running)} job(s) already running ({ids}). Wait or cancel."
    return None


# ---------------------------------------------------------------------------
# Action logging
# ---------------------------------------------------------------------------


def log_admin_action(
    admin_id: int,
    action: str,
    details: dict | None = None,
) -> None:
    """Append an admin action to the audit log."""
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = JOBS_ROOT / "admin_actions.jsonl"
    entry = {
        "timestamp": _now_iso(),
        "admin_id": admin_id,
        "action": action,
        "details": details or {},
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Study task template
# ---------------------------------------------------------------------------


def create_study_plan(topic: str) -> str:
    """Generate a study plan template for research tasks."""
    return f"""# Study Plan: {topic}

## Research Questions
1. What is {topic}? Core concepts and terminology.
2. What are the current best practices?
3. What are the common pitfalls and known issues?
4. How does this apply to the Rayviews pipeline?

## Done Criteria
- [ ] Landscape mapped (key players, tools, approaches)
- [ ] 2-3 subtopics explored in depth
- [ ] Contradictions or risks identified
- [ ] Actionable recommendations written
- [ ] Sources documented with URLs

## Phases
### Phase 1: Quick Landscape Map
- Broad search across official docs, reviews, comparisons
- Identify the 2-3 most important subtopics
- Time limit: ~20% of total effort

### Phase 2: Deep Dive
- Detailed exploration of top subtopics
- Extract specific data, numbers, procedures
- Time limit: ~60% of total effort

### Phase 3: Verification & Synthesis
- Cross-check claims across sources
- Note contradictions or outdated info
- Write final summary with recommendations
- Time limit: ~20% of total effort

## Expected Artifacts
- plan.md (this file)
- sources.json (structured source list)
- output.md (final report with findings)
- notes.md (raw research notes)
"""


def init_study_workspace(job: Job, topic: str) -> None:
    """Initialize a study job's workspace with template files."""
    ws = job.workspace
    # Plan
    plan = create_study_plan(topic)
    (ws / "plan.md").write_text(plan, encoding="utf-8")
    # Empty sources
    (ws / "sources.json").write_text("[]", encoding="utf-8")
    # Empty output
    (ws / "output.md").write_text(f"# Study: {topic}\n\n(in progress)\n", encoding="utf-8")
    # Empty notes
    (ws / "notes.md").write_text(f"# Research Notes: {topic}\n\n", encoding="utf-8")
    # Register plan as artifact
    job.artifacts.append(Artifact(
        name="plan.md",
        path=str(ws / "plan.md"),
        mime_type="text/markdown",
    ))
    save_job(job)


# ---------------------------------------------------------------------------
# Pipeline command mapping (safe allowlist)
# ---------------------------------------------------------------------------

PIPELINE_COMMANDS: dict[str, dict] = {
    "status": {
        "cmd": ["python3", "tools/pipeline.py", "status"],
        "description": "Show pipeline status for a video",
        "args": ["--video-id"],
        "destructive": False,
    },
    "research": {
        "cmd": ["python3", "tools/pipeline.py", "research"],
        "description": "Run research stage",
        "args": ["--video-id"],
        "destructive": False,
    },
    "verify": {
        "cmd": ["python3", "tools/pipeline.py", "verify"],
        "description": "Run Amazon verify stage",
        "args": ["--video-id"],
        "destructive": False,
    },
    "script": {
        "cmd": ["python3", "tools/pipeline.py", "script", "--generate"],
        "description": "Generate script",
        "args": ["--video-id"],
        "destructive": False,
    },
    "assets": {
        "cmd": ["python3", "tools/pipeline.py", "assets"],
        "description": "Generate visual assets",
        "args": ["--video-id"],
        "destructive": False,
    },
    "tts": {
        "cmd": ["python3", "tools/pipeline.py", "tts"],
        "description": "Generate TTS audio",
        "args": ["--video-id"],
        "destructive": False,
    },
    "manifest": {
        "cmd": ["python3", "tools/pipeline.py", "manifest"],
        "description": "Generate export manifest",
        "args": ["--video-id"],
        "destructive": False,
    },
    "run": {
        "cmd": ["python3", "tools/pipeline.py", "run"],
        "description": "Run full pipeline",
        "args": ["--video-id"],
        "destructive": False,
    },
    "day": {
        "cmd": ["python3", "tools/pipeline.py", "day"],
        "description": "Run daily pipeline (niche + full run)",
        "args": ["--video-id"],
        "destructive": False,
    },
}

# Destructive pipeline ops that require confirmation
DESTRUCTIVE_COMMANDS: dict[str, dict] = {
    "clear-cache": {
        "cmd": ["python3", "-c", "from tools.lib.pipeline_status import clear_cache; clear_cache()"],
        "description": "Clear pipeline cache",
        "destructive": True,
    },
}


# ---------------------------------------------------------------------------
# Telegram message formatting
# ---------------------------------------------------------------------------


def format_job_status(job: Job) -> str:
    """Format a job status for Telegram."""
    status_emoji = {
        "queued": "[QUEUED]",
        "running": "[RUNNING]",
        "blocked": "[BLOCKED]",
        "completed": "[DONE]",
        "failed": "[FAILED]",
        "canceled": "[CANCELED]",
    }
    lines = [
        f"{status_emoji.get(job.status, '[?]')} Job {job.id}: {job.title}",
        f"Status: {job.status} ({job.progress_percent}%)",
        f"Type: {job.job_type}",
        f"Created: {job.created_at}",
    ]
    if job.checkpoint:
        lines.append(f"Checkpoint: {job.checkpoint}")
    if job.error:
        lines.append(f"Error: {job.error}")
    if job.artifacts:
        lines.append(f"Artifacts: {len(job.artifacts)}")
    pending = job.pending_permissions
    if pending:
        lines.append(f"Pending permissions: {len(pending)}")
        for p in pending:
            lines.append(f"  - [{p.risk_level}] {p.action}")
            lines.append(f"    /approve {p.perm_id}  |  /deny {p.perm_id}")
    return "\n".join(lines)


def format_job_list(jobs: list[Job]) -> str:
    """Format a list of jobs for Telegram."""
    if not jobs:
        return "No jobs found."
    lines = ["Recent jobs:"]
    for job in jobs:
        status_tag = {
            "queued": "Q",
            "running": "R",
            "blocked": "B",
            "completed": "D",
            "failed": "F",
            "canceled": "X",
        }.get(job.status, "?")
        lines.append(f"  [{status_tag}] {job.id} — {job.title} ({job.progress_percent}%)")
    return "\n".join(lines)


def format_permission_list(pending: list[tuple[Job, PermissionRequest]]) -> str:
    """Format pending permissions for Telegram."""
    if not pending:
        return "No pending permissions."
    lines = ["Pending permissions:"]
    for job, perm in pending:
        lines.append(f"  [{perm.risk_level}] Job {job.id}: {perm.action}")
        lines.append(f"    Reason: {perm.reason}")
        if perm.safe_alternative:
            lines.append(f"    Alternative: {perm.safe_alternative}")
        lines.append(f"    /approve {perm.perm_id}  |  /deny {perm.perm_id}")
    return "\n".join(lines)
