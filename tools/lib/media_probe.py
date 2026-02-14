"""Media probe — ffprobe-based post-render validation.

Validates rendered video files before marking Stage.RENDER as done.
Prevents corrupted/truncated/empty renders from passing the pipeline.

Dependencies: ffprobe (comes with ffmpeg — brew install ffmpeg)

Usage:
    from tools.lib.media_probe import validate_render, ffprobe_json

    validate_render(Path("output.mp4"), min_bytes=500_000, min_duration_sec=10.0)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict


class RenderValidationError(RuntimeError):
    """Raised when a rendered file fails validation."""
    pass


def ffprobe_json(path: Path) -> Dict[str, Any]:
    """Run ffprobe and return parsed JSON with format + streams info.

    Raises subprocess.CalledProcessError if ffprobe fails.
    Raises FileNotFoundError if ffprobe is not installed.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(result.stdout)


def get_duration(path: Path) -> float:
    """Get media duration in seconds. Returns 0.0 on error."""
    try:
        info = ffprobe_json(path)
        return float(info.get("format", {}).get("duration", 0.0))
    except Exception:
        return 0.0


def get_video_info(path: Path) -> Dict[str, Any]:
    """Get video stream info (codec, resolution, fps). Returns {} on error."""
    try:
        info = ffprobe_json(path)
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                return {
                    "codec": stream.get("codec_name", ""),
                    "width": stream.get("width", 0),
                    "height": stream.get("height", 0),
                    "fps": stream.get("r_frame_rate", ""),
                    "duration": float(stream.get("duration", 0.0)),
                }
        return {}
    except Exception:
        return {}


def validate_render(
    path: Path,
    *,
    min_bytes: int = 500_000,
    min_duration_sec: float = 5.0,
    require_video_stream: bool = True,
    require_audio_stream: bool = False,
) -> Dict[str, Any]:
    """Validate a rendered video file. Returns info dict on success.

    Raises RenderValidationError on failure with descriptive message.
    """
    if not path.exists():
        raise RenderValidationError(f"Render missing: {path}")

    size = path.stat().st_size
    if size < min_bytes:
        raise RenderValidationError(
            f"Render too small: {size} bytes (min {min_bytes})"
        )

    try:
        info = ffprobe_json(path)
    except FileNotFoundError:
        raise RenderValidationError(
            "ffprobe not installed — run: brew install ffmpeg"
        )
    except subprocess.CalledProcessError as e:
        raise RenderValidationError(f"ffprobe failed: {e.stderr[:200]}")

    duration = float(info.get("format", {}).get("duration", 0.0))
    if duration < min_duration_sec:
        raise RenderValidationError(
            f"Render too short: {duration:.1f}s (min {min_duration_sec}s)"
        )

    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    if require_video_stream and not has_video:
        raise RenderValidationError("Render has no video stream")
    if require_audio_stream and not has_audio:
        raise RenderValidationError("Render has no audio stream")

    return {
        "path": str(path),
        "bytes": size,
        "duration_sec": duration,
        "has_video": has_video,
        "has_audio": has_audio,
        "format": info.get("format", {}).get("format_name", ""),
    }
