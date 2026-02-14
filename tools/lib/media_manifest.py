"""Media Manifest builder — single source of truth for Dzine + Resolve.

Generates a deterministic manifest from a validated voice script that
serves as the "executable checklist" for:
  1. Dzine UI agent (lip-sync rendering)
  2. DaVinci Resolve timeline assembly
  3. Doctor / forensics (audit trail)

Per-segment audio paths use content-addressed digests for idempotency:
  audio_digest = sha256(voice_id + model + text + settings)
  path = state/audio/{run_id}/seg_{digest[:16]}.mp3

Naming convention (deterministic, hash-versioned):
  Audio: A_{run_id}_{segment_id}_{sha8}.mp3
  Video: V_{run_id}_{segment_id}_{sha8}.mp4
  where sha8 = audio_sha256[:8] of the finalized audio file.

prepare_manifest_for_dzine() adds:
  - sha256 + measured_duration per audio file
  - dzine block (upload/settings/export) for UI agent
  - budget_control with credit_cost + cache_hit (SKIP_DZINE)
  - budget_summary with total estimated credits

Stdlib only — no external deps.

Usage:
    from tools.lib.media_manifest import build_media_manifest, compute_audio_digest
    from tools.lib.media_manifest import prepare_manifest_for_dzine, DzineHints

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


# ---------------------------------------------------------------------------
# Dzine manifest preparation — UI-proof contract for lip-sync agent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DzineHints:
    """Configuration for Dzine UI agent."""
    avatar_ref: str = "assets/avatars/ray.png"
    project_preset: str = "Ray_16x9_Lipsync"
    lip_sync_style_default: str = "neutral"
    credit_cost_per_segment: int = 1
    min_video_bytes: int = 500_000


def _video_expected_path(
    video_dir: Path, run_id: str, segment_id: str, sha8: str,
) -> Path:
    """Deterministic video filename: V_{run_id}_{segment_id}_{sha8}.mp4"""
    return video_dir / f"V_{run_id}_{segment_id}_{sha8}.mp4"


def _audio_final_path(
    audio_dir: Path, run_id: str, segment_id: str, sha8: str,
) -> Path:
    """Deterministic audio filename: A_{run_id}_{segment_id}_{sha8}.mp3"""
    return audio_dir / f"A_{run_id}_{segment_id}_{sha8}.mp3"


def prepare_manifest_for_dzine(
    manifest: Dict[str, Any],
    *,
    video_final_dir: str = "state/video/final",
    hints: Optional[DzineHints] = None,
) -> Dict[str, Any]:
    """Prepare manifest for Dzine UI agent with budget control.

    For each segment with an audio_path:
    1. Compute sha256 of the finalized audio file
    2. Determine expected video path (deterministic naming)
    3. Check if video already exists (cache hit → SKIP_DZINE)
    4. Build dzine block with upload/settings/export + ui_checklist
    5. Calculate budget summary (total credits needed)

    Returns a new manifest with dzine blocks + budget_summary.
    Does not modify the original.
    """
    import copy

    if hints is None:
        hints = DzineHints()

    ready = copy.deepcopy(manifest)
    run_id = ready.get("run_id", "unknown")
    vdir = Path(video_final_dir)

    segments_to_render = []
    total_credits = 0

    for seg in ready.get("segments", []):
        audio_path_str = seg.get("audio_path", "")
        if not audio_path_str:
            continue

        audio_p = Path(audio_path_str)
        seg_id = seg.get("segment_id", "?")

        # Compute sha256 of finalized audio
        if audio_p.exists():
            audio_sha = _file_sha256(audio_p)
            seg["audio_sha256"] = audio_sha
            seg["audio_bytes"] = audio_p.stat().st_size
        else:
            audio_sha = seg.get("audio_digest", "unknown")[:64]
            seg["audio_sha256"] = audio_sha

        sha8 = audio_sha[:8]

        # Deterministic expected video path
        expected_video = _video_expected_path(vdir, run_id, seg_id, sha8)

        # Cache hit check
        cache_hit = (
            expected_video.exists()
            and expected_video.stat().st_size >= hints.min_video_bytes
        )

        credit_cost = 0 if cache_hit else hints.credit_cost_per_segment

        seg["video_path"] = str(expected_video)
        seg["dzine"] = {
            "budget_control": {
                "credit_cost": credit_cost,
                "cache_hit": cache_hit,
                "skip_dzine": cache_hit,
                "expected_video_path": str(expected_video),
            },
            "upload": {
                "audio_file": str(audio_p.resolve()) if audio_p.exists() else audio_path_str,
                "avatar_ref": hints.avatar_ref,
                "project_preset": hints.project_preset,
            },
            "settings": {
                "lip_sync_hint": seg.get("lip_sync_hint", hints.lip_sync_style_default),
                "target_duration_sec": seg.get("approx_duration_sec", 0),
            },
            "export": {
                "expected_filename": expected_video.name,
            },
            "ui_checklist": [
                f"Upload audio: {audio_p.name}",
                f"Select preset: {hints.project_preset}",
                f"Set avatar: {hints.avatar_ref}",
                "Generate lip-sync",
                f"Export as: {expected_video.name}",
                f"Move to: {expected_video}",
            ],
        }

        if not cache_hit:
            segments_to_render.append(seg_id)
            total_credits += hints.credit_cost_per_segment

    ready["budget_summary"] = {
        "estimated_dzine_credits": total_credits,
        "segments_to_render": segments_to_render,
        "segments_cached": len(ready.get("segments", [])) - len(segments_to_render),
    }
    ready["prepared_at"] = datetime.now(timezone.utc).isoformat()

    return ready
