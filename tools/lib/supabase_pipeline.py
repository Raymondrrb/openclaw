"""Pipeline-specific Supabase write helpers.

Every function takes run_id as first arg, wraps supabase_client calls.
All writes are fire-and-forget — failures log to stderr, never raise.
"""

from __future__ import annotations

from tools.lib.common import now_iso
from tools.lib.supabase_client import insert, update, upsert, query, upload_file, _enabled


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------

def create_run(video_id: str, niche: str, *, config: dict | None = None) -> str:
    """Insert a pipeline_runs row and return the UUID (or "" on failure)."""
    row = {
        "video_id": video_id,
        "status": "running",
        "config_snapshot": config or {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    if niche:
        row["micro_niche"] = {"niche": niche}
    result = insert("pipeline_runs", row, return_row=True)
    if result and "id" in result:
        return result["id"]
    return ""


def complete_run(
    run_id: str,
    status: str,
    stages_completed: list[str],
    errors: list[str],
    *,
    elapsed_ms: int = 0,
) -> None:
    """Update a pipeline_runs row with final status."""
    if not run_id:
        return
    data = {
        "status": status,
        "stages_completed": stages_completed,
        "updated_at": now_iso(),
    }
    if elapsed_ms:
        data["elapsed_ms"] = elapsed_ms
    if errors:
        data["error_message"] = errors[0][:500]
    update("pipeline_runs", {"id": run_id}, data)


def ensure_run_id(video_id: str, command: str) -> str:
    """Get or create a run_id for standalone commands."""
    if not _enabled():
        return ""
    # Try to find existing run
    rows = query("pipeline_runs", filters={"video_id": video_id}, limit=1)
    if rows:
        return rows[0].get("id", "")
    # Create new
    return create_run(video_id, "", config={"command": command})


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------

def log_event(
    run_id: str,
    sender: str,
    receiver: str,
    msg_type: str,
    stage: str,
    content: str,
    data: dict | None = None,
) -> None:
    """Log an inter-agent message to agent_events."""
    if not run_id:
        return
    insert("agent_events", {
        "run_id": run_id,
        "stage": stage,
        "agent_name": sender,
        "event_type": msg_type,
        "payload": {
            "receiver": receiver,
            "content": content[:500],
            "data": data or {},
        },
        "created_at": now_iso(),
    })


# ---------------------------------------------------------------------------
# Niche
# ---------------------------------------------------------------------------

def save_niche(run_id: str, video_id: str, **fields) -> None:
    """Insert a niche record."""
    if not run_id:
        return
    row = {"run_id": run_id, "video_id": video_id, "created_at": now_iso()}
    row.update(fields)
    insert("niches", row)


# ---------------------------------------------------------------------------
# Research data
# ---------------------------------------------------------------------------

def save_research_source(run_id: str, **fields) -> None:
    """Insert a research_sources record."""
    if not run_id:
        return
    row = {"run_id": run_id, "created_at": now_iso()}
    row.update(fields)
    insert("research_sources", row)


def save_shortlist_item(run_id: str, **fields) -> None:
    """Insert a shortlist_items record."""
    if not run_id:
        return
    row = {"run_id": run_id, "created_at": now_iso()}
    row.update(fields)
    insert("shortlist_items", row)


def save_amazon_product(run_id: str, **fields) -> None:
    """Insert an amazon_products record."""
    if not run_id:
        return
    row = {"run_id": run_id, "created_at": now_iso()}
    row.update(fields)
    insert("amazon_products", row)


def save_top5_product(run_id: str, **fields) -> None:
    """Insert a top5 record."""
    if not run_id:
        return
    row = {"run_id": run_id, "created_at": now_iso()}
    row.update(fields)
    insert("top5", row)


# ---------------------------------------------------------------------------
# Content pipeline
# ---------------------------------------------------------------------------

def save_script(run_id: str, stage: str, *, text: str = "", word_count: int = 0,
                has_disclosure: bool = False) -> None:
    """Insert or update a scripts record."""
    if not run_id:
        return
    row = {
        "run_id": run_id,
        "status": stage,
        "word_count": word_count,
        "has_disclosure": has_disclosure,
        "created_at": now_iso(),
    }
    if stage == "brief":
        row["brief_text"] = text[:10000]
    elif stage == "raw":
        row["script_raw"] = text[:20000]
    elif stage in ("reviewed", "review"):
        row["review_notes"] = text[:10000]
    elif stage in ("final", "approved"):
        row["script_final"] = text[:20000]
    insert("scripts", row)


def save_asset(run_id: str, *, asset_type: str = "", label: str = "",
               storage_url: str = "", ok: bool = True, error: str = "",
               **extra) -> None:
    """Insert an assets record."""
    if not run_id:
        return
    row = {
        "run_id": run_id,
        "asset_type": asset_type,
        "storage_path": storage_url,
        "ok": ok,
        "error": error[:500],
        "created_at": now_iso(),
    }
    row.update(extra)
    insert("assets", row)


def save_tts_chunk(run_id: str, *, chunk_index: int = 0, text: str = "",
                   storage_url: str = "", ok: bool = True, error: str = "",
                   duration_seconds: float = 0, **extra) -> None:
    """Insert a tts_audio record."""
    if not run_id:
        return
    row = {
        "run_id": run_id,
        "chunk_index": chunk_index,
        "text": text[:2000],
        "storage_path": storage_url,
        "duration_seconds": round(duration_seconds, 2),
        "ok": ok,
        "error": error[:500],
        "created_at": now_iso(),
    }
    row.update(extra)
    insert("tts_audio", row)


def upload_video_file(video_id: str, bucket: str, local_path: str,
                      remote_subpath: str) -> str:
    """Upload a file with path convention videos/<video_id>/<remote_subpath>."""
    remote = f"videos/{video_id}/{remote_subpath}"
    return upload_file(bucket, remote, local_path)


# ---------------------------------------------------------------------------
# Long-term memory
# ---------------------------------------------------------------------------

def save_lesson(scope: str, trigger: str, rule: str, *,
                example: dict | None = None, severity: str = "med") -> None:
    """Upsert a lesson into the lessons table."""
    upsert("lessons", {
        "scope": scope,
        "trigger": trigger,
        "rule": rule,
        "example": example or {},
        "severity": severity,
        "active": True,
        "updated_at": now_iso(),
    }, on_conflict="scope,trigger")


def get_active_lessons(scope: str = "") -> list[dict]:
    """Query active lessons, optionally filtered by scope."""
    filters = {"active": "true"}
    if scope:
        filters["scope"] = scope
    return query("lessons", filters=filters, order="updated_at.desc")


def set_channel_memory(key: str, value: dict) -> None:
    """Upsert a channel_memory row."""
    upsert("channel_memory", {
        "key": key,
        "value": value,
        "updated_at": now_iso(),
    }, on_conflict="key")


def get_channel_memory(key: str) -> dict | None:
    """Get a single channel_memory value by key."""
    rows = query("channel_memory", filters={"key": key}, limit=1)
    if rows:
        return rows[0].get("value")
    return None


def get_all_channel_memory() -> dict[str, dict]:
    """Get all channel_memory as {key: value} dict."""
    rows = query("channel_memory")
    return {r["key"]: r.get("value", {}) for r in rows}
