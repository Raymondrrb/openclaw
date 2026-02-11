"""Per-video pipeline status tracking.

Persists status as JSON in artifacts/videos/<video_id>/.status.json.
In-memory cache for fast reads during a session.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.common import now_iso, project_root

VIDEOS_BASE = project_root() / "artifacts" / "videos"

# ---------------------------------------------------------------------------
# Stages + milestones
# ---------------------------------------------------------------------------

STAGES = (
    "research",
    "script",
    "assets",
    "voice",
    "edit_prep",
    "export",
)

# Milestones per stage (ordered)
MILESTONES: dict[str, tuple[str, ...]] = {
    "research": (
        "search_started",
        "candidates_found",
        "affiliate_links_ready",
    ),
    "script": (
        "outline_generated",
        "script_approved",
    ),
    "assets": (
        "thumbnail_done",
        "product_images_done",
        "backgrounds_done",
    ),
    "voice": (
        "chunks_generated",
        "patches_applied",
    ),
    "edit_prep": (
        "manifest_generated",
        "markers_generated",
        "notes_generated",
    ),
    "export": (
        "render_complete",
        "upload_complete",
    ),
}


# ---------------------------------------------------------------------------
# Status data
# ---------------------------------------------------------------------------


@dataclass
class VideoStatus:
    video_id: str
    stage: str = ""
    milestone: str = ""
    progress_done: int = 0
    progress_total: int = 0
    started_at: str = ""
    updated_at: str = ""
    completed_at: str = ""
    last_notify_at: float = 0.0  # unix timestamp of last telegram notification
    last_notify_key: str = ""  # dedup key for last notification
    errors: list[dict] = field(default_factory=list)  # [{stage, milestone, error, ts}]
    stages_done: dict[str, bool] = field(default_factory=dict)
    next_action: str = ""
    blockers: list[str] = field(default_factory=list)


# In-memory cache
_cache: dict[str, VideoStatus] = {}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _status_path(video_id: str) -> Path:
    # Prefer status.json (new layout), fall back to .status.json (legacy)
    new_path = VIDEOS_BASE / video_id / "status.json"
    if new_path.is_file():
        return new_path
    legacy = VIDEOS_BASE / video_id / ".status.json"
    if legacy.is_file():
        return legacy
    # Default to new layout for fresh projects
    return new_path


def _load(video_id: str) -> VideoStatus:
    """Load status from disk, or create new."""
    if video_id in _cache:
        return _cache[video_id]

    path = _status_path(video_id)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            status = VideoStatus(
                video_id=data.get("video_id", video_id),
                stage=data.get("stage", ""),
                milestone=data.get("milestone", ""),
                progress_done=data.get("progress_done", 0),
                progress_total=data.get("progress_total", 0),
                started_at=data.get("started_at", ""),
                updated_at=data.get("updated_at", ""),
                completed_at=data.get("completed_at", ""),
                last_notify_at=data.get("last_notify_at", 0.0),
                last_notify_key=data.get("last_notify_key", ""),
                errors=data.get("errors", []),
                stages_done=data.get("stages_done", {}),
                next_action=data.get("next_action", ""),
                blockers=data.get("blockers", []),
            )
            _cache[video_id] = status
            return status
        except Exception:
            pass

    status = VideoStatus(video_id=video_id)
    _cache[video_id] = status
    return status


def _save(status: VideoStatus) -> None:
    """Persist status to disk."""
    path = _status_path(status.video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "video_id": status.video_id,
        "stage": status.stage,
        "milestone": status.milestone,
        "progress_done": status.progress_done,
        "progress_total": status.progress_total,
        "started_at": status.started_at,
        "updated_at": status.updated_at,
        "completed_at": status.completed_at,
        "last_notify_at": status.last_notify_at,
        "last_notify_key": status.last_notify_key,
        "errors": status.errors[-20:],  # keep last 20 errors max
        "stages_done": status.stages_done,
        "next_action": status.next_action,
        "blockers": status.blockers,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_status(video_id: str) -> VideoStatus:
    """Get current status for a video_id."""
    return _load(video_id)


def start_pipeline(video_id: str) -> VideoStatus:
    """Mark pipeline start for a video_id."""
    status = _load(video_id)
    status.started_at = now_iso()
    status.updated_at = now_iso()
    status.stage = "research"
    status.milestone = ""
    status.completed_at = ""
    _save(status)
    return status


def update_milestone(
    video_id: str,
    stage: str,
    milestone: str,
    *,
    progress_done: int = 0,
    progress_total: int = 0,
) -> VideoStatus:
    """Update stage/milestone and optional progress counters."""
    status = _load(video_id)
    status.stage = stage
    status.milestone = milestone
    status.updated_at = now_iso()
    if progress_total > 0:
        status.progress_done = progress_done
        status.progress_total = progress_total
    _save(status)
    return status


def record_error(video_id: str, stage: str, milestone: str, error: str) -> VideoStatus:
    """Record an error for a video_id."""
    status = _load(video_id)
    status.errors.append({
        "stage": stage,
        "milestone": milestone,
        "error": error,
        "ts": now_iso(),
    })
    status.updated_at = now_iso()
    _save(status)
    return status


def complete_pipeline(video_id: str) -> VideoStatus:
    """Mark pipeline as complete."""
    status = _load(video_id)
    status.completed_at = now_iso()
    status.updated_at = now_iso()
    status.stage = "export"
    status.milestone = "complete"
    _save(status)
    return status


def mark_notified(video_id: str, dedup_key: str) -> None:
    """Record that a notification was sent (for anti-spam)."""
    status = _load(video_id)
    status.last_notify_at = time.time()
    status.last_notify_key = dedup_key
    _save(status)


def should_heartbeat(video_id: str, threshold_minutes: float = 8.0) -> bool:
    """Check if a heartbeat is warranted (no notification in threshold_minutes)."""
    status = _load(video_id)
    if not status.started_at or status.completed_at:
        return False
    elapsed = time.time() - status.last_notify_at
    return elapsed > threshold_minutes * 60


def format_status_text(video_id: str) -> str:
    """Format current status as human-readable text (for CLI)."""
    status = _load(video_id)
    lines = [
        f"Pipeline Status: {video_id}",
        f"{'=' * 40}",
    ]

    if not status.started_at:
        lines.append("Not started")
        return "\n".join(lines)

    lines.append(f"Started:  {status.started_at}")
    if status.completed_at:
        lines.append(f"Complete: {status.completed_at}")
    lines.append(f"Stage:    {status.stage}")
    lines.append(f"Milestone: {status.milestone}")

    if status.progress_total > 0:
        lines.append(f"Progress: {status.progress_done}/{status.progress_total}")

    # Per-stage checklist
    if status.stages_done:
        lines.append("")
        lines.append("Stages:")
        for stage_name in STAGES:
            done = status.stages_done.get(stage_name, False)
            mark = "[x]" if done else "[ ]"
            lines.append(f"  {mark} {stage_name}")

    # Blockers
    if status.blockers:
        lines.append("")
        lines.append("Blockers:")
        for b in status.blockers:
            lines.append(f"  - {b}")

    if status.errors:
        lines.append(f"\nRecent errors ({len(status.errors)}):")
        for err in status.errors[-3:]:
            lines.append(f"  [{err.get('ts', '?')}] {err.get('stage')}/{err.get('milestone')}: {err.get('error')}")

    # Next action hint
    next_action = _suggest_next_action(status)
    if next_action:
        lines.append(f"\nNext: {next_action}")

    return "\n".join(lines)


def _suggest_next_action(status: VideoStatus) -> str:
    """Suggest next action based on current state."""
    vid = status.video_id

    if status.completed_at:
        return "Pipeline complete. Review exports."

    # Use explicit next_action if set
    if status.next_action:
        return status.next_action

    if status.errors:
        last_err = status.errors[-1]
        return f"Fix error in {last_err.get('stage')}/{last_err.get('milestone')}: {last_err.get('error', '')[:60]}"

    stage = status.stage
    milestone = status.milestone

    if stage == "research":
        if milestone == "affiliate_links_ready":
            return f"python3 tools/pipeline.py script --video-id {vid}"
        return f"python3 tools/pipeline.py research --video-id {vid}"
    elif stage == "script":
        if milestone == "script_approved":
            return f"python3 tools/pipeline.py assets --video-id {vid}"
        return f"python3 tools/pipeline.py script --video-id {vid}"
    elif stage == "assets":
        if milestone == "backgrounds_done":
            return f"python3 tools/pipeline.py tts --video-id {vid}"
        return f"python3 tools/pipeline.py assets --video-id {vid}"
    elif stage == "voice":
        if milestone in ("chunks_generated", "patches_applied"):
            return f"python3 tools/pipeline.py manifest --video-id {vid}"
        return f"python3 tools/pipeline.py tts --video-id {vid}"
    elif stage == "edit_prep":
        if milestone == "notes_generated":
            return "Open DaVinci Resolve and edit"
        return f"python3 tools/pipeline.py manifest --video-id {vid}"
    elif stage == "export":
        return "Upload to YouTube"

    return f"python3 tools/pipeline.py status --video-id {vid}"
