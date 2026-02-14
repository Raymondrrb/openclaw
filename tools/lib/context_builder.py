"""Context Builder — filesystem-first, deterministic context pack selection.

Reads the local vault index (vault_notes.json) and canonicals config
(canonicals.yml) to build a budget-aware "context pack" for each run.

Source of truth: markdown files in the vault directory.
Supabase: optional operational index (fast lookup, graceful degradation).

Selection is deterministic:
    1. Canonical SOPs always included (if defined and healthy)
    2. Remaining budget filled by priority (red > yellow > green)
    3. Tie-breaker: authority_score > version > last_verified > priority

Safeguards:
    - Alias collisions across different IDs → hard BLOCKED
    - Stale or low-confidence canonicals → BLOCKED (manual verification needed)
    - Budget cap (default 6 notes per run)

Stdlib only.

Usage:
    from lib.context_builder import build_context_pack, ContextPack

    pack = build_context_pack(task_type="research")
    if pack.blocked:
        print(f"BLOCKED: {pack.block_reason}")
    else:
        for note in pack.notes:
            print(f"  {note['id']} ({note['role']})")
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default max notes per context pack
DEFAULT_MAX_NOTES = 6

# Priority levels (lower number = higher priority = loaded first)
PRIORITY_ORDER = {"red": 0, "yellow": 1, "green": 2}

# Minimum confidence level for canonical notes
MIN_CANONICAL_CONFIDENCE = "medium"  # "low" < "medium" < "high"
CONFIDENCE_LEVELS = {"low": 0, "medium": 1, "high": 2}

# Max age (days) before a canonical is considered stale
CANONICAL_MAX_STALE_DAYS = 30


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NoteRef:
    """A reference to a vault note for context injection."""
    id: str
    path: str
    role: str = ""              # "canonical", "sop", "skill", "lesson", etc.
    priority: str = "green"     # "red", "yellow", "green"
    authority_score: float = 0.0
    version: int = 1
    last_verified: str = ""     # ISO timestamp
    content_hash: str = ""
    token_estimate: int = 0
    is_archived: bool = False
    aliases: list[str] = field(default_factory=list)

    @property
    def priority_rank(self) -> int:
        return PRIORITY_ORDER.get(self.priority, 2)


@dataclass
class ContextPack:
    """The assembled context pack for a run."""
    task_type: str
    notes: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    blocked: bool = False
    block_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_snapshot(self) -> dict:
        """Serialize for runs.context_snapshot storage."""
        return {
            "task_type": self.task_type,
            "note_count": len(self.notes),
            "total_tokens": self.total_tokens,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "warnings": self.warnings,
            "notes": [
                {
                    "id": n["id"],
                    "path": n.get("path", ""),
                    "role": n.get("role", ""),
                    "version": n.get("version", 1),
                    "content_hash": n.get("content_hash", ""),
                    "last_verified": n.get("last_verified", ""),
                }
                for n in self.notes
            ],
        }

    @property
    def summary(self) -> str:
        """One-line summary for logging."""
        if self.blocked:
            return f"BLOCKED: {self.block_reason}"
        roles = [n.get("role", "?") for n in self.notes]
        return (
            f"{len(self.notes)} notes (~{self.total_tokens} tokens) "
            f"roles={roles}"
        )


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

def _default_vault_dir() -> Path:
    """Default vault directory: <repo>/agents/vault/"""
    return Path(__file__).resolve().parent.parent.parent / "agents" / "vault"


def _default_index_path() -> Path:
    """Default vault index: <repo>/agents/vault/vault_notes.json"""
    return _default_vault_dir() / "vault_notes.json"


def _default_canonicals_path() -> Path:
    """Default canonicals config: <repo>/agents/vault/canonicals.yml"""
    return _default_vault_dir() / "canonicals.yml"


def load_vault_index(
    path: str | Path | None = None,
) -> dict[str, dict]:
    """Load the vault_notes.json index.

    Returns: {note_id: {path, aliases, authority_score, ...}}
    """
    p = Path(path) if path else _default_index_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        # If it's a list, convert to dict keyed by normalized_id or path
        if isinstance(data, list):
            return {
                item.get("normalized_id", item.get("path", f"note_{i}")): item
                for i, item in enumerate(data)
            }
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[context_builder] Failed to load vault index: {exc}", file=sys.stderr)
    return {}


def load_canonicals(
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Load canonicals.yml (or .json fallback).

    Supports two formats:
    - Simple: {task_type: note_id}
    - Advanced: {task_type: {id: note_id, min_confidence: "high", variant: "..."}}

    Returns: {task_type: canonical_config}
    """
    p = Path(path) if path else _default_canonicals_path()

    # Try YAML first, fall back to JSON
    if p.is_file():
        text = p.read_text(encoding="utf-8")
        # Simple YAML parser for key: value format
        return _parse_simple_yaml(text)

    # Try .json variant
    json_path = p.with_suffix(".json")
    if json_path.is_file():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return {}


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML parser for canonicals config (no external deps).

    Handles:
        task_type: note_id
        task_type:
          id: note_id
          min_confidence: high
          variant: v2
    """
    result: dict[str, Any] = {}
    lines = text.split("\n")
    current_key = ""
    current_obj: dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            # Flush previous
            if current_key and current_obj:
                result[current_key] = current_obj
            elif current_key:
                pass  # already set as simple value

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                # Simple format: task_type: note_id
                result[key] = value
                current_key = ""
                current_obj = {}
            else:
                # Start of nested object
                current_key = key
                current_obj = {}
        elif indent > 0 and current_key and ":" in stripped:
            # Nested key: value
            k, _, v = stripped.partition(":")
            current_obj[k.strip()] = v.strip()

    # Flush last
    if current_key and current_obj:
        result[current_key] = current_obj

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_no_alias_collisions(
    index: dict[str, dict],
) -> list[str]:
    """Check for alias collisions across different note IDs.

    Returns list of error messages (empty = clean).
    """
    alias_to_ids: dict[str, list[str]] = {}

    for note_id, note in index.items():
        aliases = note.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]

        for alias in aliases:
            alias_lower = alias.lower()
            alias_to_ids.setdefault(alias_lower, []).append(note_id)

        # Also check the note_id itself
        alias_to_ids.setdefault(note_id.lower(), []).append(note_id)

    errors = []
    for alias, ids in alias_to_ids.items():
        unique_ids = list(set(ids))
        if len(unique_ids) > 1:
            errors.append(
                f"Alias collision: '{alias}' maps to {unique_ids}"
            )
    return errors


def _check_canonical_health(
    canonical_config: Any,
    index: dict[str, dict],
) -> tuple[str | None, str]:
    """Check if a canonical note is healthy.

    Returns: (note_id, error_message). error_message is empty if healthy.
    """
    # Normalize config
    if isinstance(canonical_config, str):
        note_id = canonical_config
        min_confidence = MIN_CANONICAL_CONFIDENCE
    elif isinstance(canonical_config, dict):
        note_id = canonical_config.get("id", "")
        min_confidence = canonical_config.get("min_confidence", MIN_CANONICAL_CONFIDENCE)
    else:
        return None, f"Invalid canonical config type: {type(canonical_config)}"

    if not note_id:
        return None, "Canonical has no note ID"

    # Check note exists in index
    note = index.get(note_id)
    if note is None:
        return note_id, f"Canonical '{note_id}' not found in vault index"

    # Check archived
    if note.get("is_archived", False):
        return note_id, f"Canonical '{note_id}' is archived"

    # Check confidence
    note_confidence = note.get("confidence", "medium")
    if CONFIDENCE_LEVELS.get(note_confidence, 1) < CONFIDENCE_LEVELS.get(min_confidence, 1):
        return note_id, (
            f"Canonical '{note_id}' confidence={note_confidence} "
            f"below required={min_confidence}"
        )

    # Check staleness
    last_verified = note.get("last_verified", "")
    if last_verified:
        try:
            from datetime import datetime, timezone
            import time as _time
            ts = datetime.fromisoformat(last_verified).timestamp()
            age_days = (_time.time() - ts) / 86400
            if age_days > CANONICAL_MAX_STALE_DAYS:
                return note_id, (
                    f"Canonical '{note_id}' is stale "
                    f"(last verified {age_days:.0f} days ago, max={CANONICAL_MAX_STALE_DAYS})"
                )
        except (ValueError, OSError):
            pass

    return note_id, ""


# ---------------------------------------------------------------------------
# Supabase fallback (optional)
# ---------------------------------------------------------------------------

def _try_supabase_index() -> dict[str, dict] | None:
    """Try to load vault note metadata from Supabase. Returns None if unavailable."""
    try:
        from tools.lib.supabase_client import query, _enabled
        if not _enabled():
            return None
        rows = query("vault_notes", select="*", limit=200)
        if not rows:
            return None
        return {
            r.get("normalized_id", r.get("id", "")): r
            for r in rows
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _note_to_ref(note_id: str, note: dict) -> NoteRef:
    """Convert index entry to NoteRef."""
    return NoteRef(
        id=note_id,
        path=note.get("path", ""),
        role=note.get("type", note.get("role", "")),
        priority=note.get("priority", "green"),
        authority_score=float(note.get("authority_score", 0)),
        version=int(note.get("version", 1)),
        last_verified=note.get("last_verified", ""),
        content_hash=note.get("content_hash", ""),
        token_estimate=int(note.get("token_estimate", 0)),
        is_archived=bool(note.get("is_archived", False)),
        aliases=note.get("aliases", []),
    )


def _sort_key(ref: NoteRef) -> tuple:
    """Sort key: priority rank ASC, authority DESC, version DESC, last_verified DESC."""
    return (
        ref.priority_rank,
        -ref.authority_score,
        -ref.version,
        ref.last_verified or "",  # empty string sorts first (oldest)
    )


def build_context_pack(
    task_type: str,
    *,
    vault_index_path: str | Path | None = None,
    canonicals_path: str | Path | None = None,
    max_notes: int = DEFAULT_MAX_NOTES,
    use_supabase: bool = True,
) -> ContextPack:
    """Build a deterministic context pack for a pipeline run.

    Args:
        task_type: The type of task (e.g. "research", "script", "ranking").
        vault_index_path: Path to vault_notes.json. Uses default if None.
        canonicals_path: Path to canonicals.yml. Uses default if None.
        max_notes: Maximum notes in the pack (default 6).
        use_supabase: Try Supabase index first (graceful degradation).

    Returns:
        ContextPack with selected notes, or blocked=True if validation fails.
    """
    pack = ContextPack(task_type=task_type)

    # 1. Load vault index (Supabase first, local fallback)
    index: dict[str, dict] = {}
    if use_supabase:
        sb_index = _try_supabase_index()
        if sb_index:
            index = sb_index
            pack.warnings.append("Using Supabase vault index")

    if not index:
        index = load_vault_index(vault_index_path)
        if not index:
            # No index at all — not necessarily blocked, just empty
            pack.warnings.append("No vault index found (vault_notes.json missing)")
            return pack

    # 2. Validate: no alias collisions
    collisions = _validate_no_alias_collisions(index)
    if collisions:
        pack.blocked = True
        pack.block_reason = (
            "Alias collisions detected — cannot build deterministic pack. "
            + "; ".join(collisions)
        )
        return pack

    # 3. Load canonicals
    canonicals = load_canonicals(canonicals_path)
    canonical_for_task = canonicals.get(task_type)

    # 4. If canonical defined, validate health
    canonical_id: str | None = None
    if canonical_for_task is not None:
        cid, error = _check_canonical_health(canonical_for_task, index)
        if error:
            pack.blocked = True
            pack.block_reason = (
                f"Canonical note unhealthy for task '{task_type}': {error}. "
                f"Manual verification required — do not continue silently."
            )
            return pack
        canonical_id = cid

    # 5. Build candidate list (exclude archived)
    candidates: list[NoteRef] = []
    for note_id, note in index.items():
        ref = _note_to_ref(note_id, note)
        if ref.is_archived:
            continue
        candidates.append(ref)

    # 6. Deterministic selection
    selected: list[NoteRef] = []

    # 6a. Canonical first (always included if defined)
    if canonical_id:
        for c in candidates:
            if c.id == canonical_id:
                c.role = "canonical"
                selected.append(c)
                break

    # 6b. Fill remaining budget by priority + authority
    remaining = max_notes - len(selected)
    selected_ids = {s.id for s in selected}

    # Sort candidates by priority rank, then authority desc, etc.
    sorted_candidates = sorted(candidates, key=_sort_key)

    for ref in sorted_candidates:
        if remaining <= 0:
            break
        if ref.id in selected_ids:
            continue
        selected.append(ref)
        selected_ids.add(ref.id)
        remaining -= 1

    # 7. Build output
    total_tokens = 0
    for ref in selected:
        note_dict = {
            "id": ref.id,
            "path": ref.path,
            "role": ref.role,
            "priority": ref.priority,
            "authority_score": ref.authority_score,
            "version": ref.version,
            "last_verified": ref.last_verified,
            "content_hash": ref.content_hash,
            "token_estimate": ref.token_estimate,
        }
        pack.notes.append(note_dict)
        total_tokens += ref.token_estimate

    pack.total_tokens = total_tokens
    return pack
