"""Media Manifest builder — single source of truth for Dzine + Resolve.

Generates a deterministic manifest from a validated voice script that
serves as the "executable checklist" for:
  1. Dzine UI agent (lip-sync rendering)
  2. DaVinci Resolve timeline assembly
  3. Doctor / forensics (audit trail)

Per-segment audio paths use content-addressed digests for idempotency:
  audio_digest = sha256(voice_id + model + text + settings)
  path = state/audio/{run_id}/seg_{digest[:16]}.mp3

Stdlib only — no external deps.

Usage:
    from tools.lib.media_manifest import build_media_manifest, compute_audio_digest

    manifest = build_media_manifest(
        voice_script=validated_voice_script,
        run_id="RAY-99",
        audio_dir="state/audio/RAY-99",
        video_dir="state/video/RAY-99",
    )
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _canonical_json(obj: Any) -> str:
    """Canonical JSON for stable hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_audio_digest(
    voice_id: str,
    text: str,
    model: str,
    stability: float = 0.4,
    style: float = 0.35,
) -> str:
    """Compute idempotent digest for an audio segment.

    Same inputs → same digest → skip re-generation.
    Text is normalized (strip + collapse whitespace) before hashing.
    """
    normalized_text = " ".join(text.strip().split())
    payload = {
        "voice_id": voice_id,
        "model": model,
        "text": normalized_text,
        "stability": round(stability, 3),
        "style": round(style, 3),
    }
    return _sha256(_canonical_json(payload))


def build_media_manifest(
    voice_script: Dict[str, Any],
    *,
    run_id: str,
    audio_dir: str = "state/audio",
    video_dir: str = "state/video",
    output_path: str = "state/output/final.mp4",
    fps: int = 30,
    resolution: str = "1920x1080",
    render_preset: str = "H264_1080p",
    avatar_image_path: str = "state/runtime/avatar/latest.png",
) -> Dict[str, Any]:
    """Build a media manifest from a validated voice script.

    The manifest is the "contract" between:
    - Audio generation (ElevenLabs, per-segment)
    - Video generation (Dzine lip-sync, per-segment)
    - Timeline assembly (DaVinci Resolve)

    Args:
        voice_script: Validated output from VOICE_SCRIPT_SCHEMA.
        run_id: Pipeline run identifier.
        audio_dir: Base directory for audio files.
        video_dir: Base directory for video files.
        output_path: Final rendered video path.
        fps: Target frame rate.
        resolution: Target resolution string.
        render_preset: DaVinci Resolve render preset.
        avatar_image_path: Avatar image for lip-sync.

    Returns:
        Manifest dict ready for JSON serialization.
    """
    segments = voice_script.get("segments", [])
    audio_plan = voice_script.get("audio_plan", [])

    # Index audio_plan by segment_id
    plan_by_id = {p["segment_id"]: p for p in audio_plan}

    manifest_segments = []
    for seg in segments:
        sid = seg["segment_id"]
        plan = plan_by_id.get(sid, {})

        # Compute audio digest for idempotent file naming
        digest = compute_audio_digest(
            voice_id=plan.get("voice_id", "default"),
            text=seg.get("text", ""),
            model=plan.get("model", "eleven_multilingual_v2"),
            stability=plan.get("stability", 0.4),
            style=plan.get("style", 0.35),
        )

        audio_filename = f"seg_{digest[:16]}.mp3"
        video_filename = f"{sid}.mp4"

        manifest_segments.append({
            "segment_id": sid,
            "kind": seg.get("kind", ""),
            "slot": seg.get("product_key", ""),
            "lip_sync_hint": seg.get("lip_sync_hint", "neutral"),
            "approx_duration_sec": seg.get("approx_duration_sec", 0),
            "audio_path": f"{audio_dir}/{run_id}/{audio_filename}",
            "audio_digest": digest,
            "video_path": f"{video_dir}/{run_id}/{video_filename}",
        })

    return {
        "manifest_version": "1.0",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fps": fps,
        "resolution": resolution,
        "avatar_image_path": avatar_image_path,
        "contract_version": voice_script.get("contract_version", ""),
        "total_duration_sec": voice_script.get("total_duration_sec", 0),
        "segments": manifest_segments,
        "deliver": {
            "output_path": output_path,
            "preset": render_preset,
        },
    }


def validate_manifest_paths(manifest: Dict[str, Any]) -> List[str]:
    """Validate that manifest audio/video paths exist on disk.

    Returns list of missing paths (empty = all present).
    For use in Doctor/preflight before Resolve assembly.
    """
    missing = []
    for seg in manifest.get("segments", []):
        audio = seg.get("audio_path", "")
        if audio and not Path(audio).exists():
            missing.append(f"audio missing: {audio}")
        video = seg.get("video_path", "")
        if video and not Path(video).exists():
            missing.append(f"video missing: {video}")
    return missing


def stamp_manifest_integrity(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Add sha256 + bytes to each segment's audio/video paths.

    Call this AFTER all media files are generated but BEFORE assembly.
    Enables the media gate to detect:
    - Truncated files (size mismatch)
    - Swapped files (hash mismatch)
    - Corrupt files (hash mismatch)

    Returns a new manifest with integrity fields added.
    Does not modify the original.
    """
    import copy
    stamped = copy.deepcopy(manifest)

    for seg in stamped.get("segments", []):
        for key in ("audio_path", "video_path"):
            path_str = seg.get(key, "")
            if not path_str:
                continue
            p = Path(path_str)
            if p.exists():
                seg[f"{key}_bytes"] = p.stat().st_size
                seg[f"{key}_sha256"] = _file_sha256(p)

    return stamped


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_manifest_integrity(manifest: Dict[str, Any]) -> List[str]:
    """Validate manifest integrity stamps against actual files.

    Checks sha256 and bytes for each stamped path.
    Returns list of issues (empty = all intact).
    """
    issues = []
    for seg in manifest.get("segments", []):
        for key in ("audio_path", "video_path"):
            path_str = seg.get(key, "")
            expected_sha = seg.get(f"{key}_sha256")
            expected_bytes = seg.get(f"{key}_bytes")

            if not path_str or not expected_sha:
                continue

            p = Path(path_str)
            if not p.exists():
                issues.append(f"{key} missing: {path_str}")
                continue

            actual_bytes = p.stat().st_size
            if expected_bytes is not None and actual_bytes != expected_bytes:
                issues.append(
                    f"{key} size mismatch: {path_str} "
                    f"(expected {expected_bytes}, got {actual_bytes})"
                )

            actual_sha = _file_sha256(p)
            if actual_sha != expected_sha:
                issues.append(
                    f"{key} hash mismatch: {path_str} "
                    f"(expected {expected_sha[:12]}..., got {actual_sha[:12]}...)"
                )

    return issues
