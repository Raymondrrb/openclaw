"""Video Study pipeline — download and job directory management.

Downloads YouTube videos via yt-dlp, extracts metadata + subtitles,
manages temp job directories with guaranteed cleanup.

External deps: yt-dlp (system binary, called via subprocess).
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# Temp base directory for all video study jobs
TEMP_BASE = Path(tempfile.gettempdir()) / "rayviews_video_study"


@dataclass
class DownloadResult:
    """Result of a video download or local file setup."""
    success: bool
    job_dir: Path = field(default_factory=lambda: Path("."))
    video_path: Path = field(default_factory=lambda: Path("."))
    video_id: str = ""
    title: str = ""
    channel: str = ""
    description: str = ""
    duration_s: float = 0.0
    subtitle_path: Path | None = None
    info_json_path: Path | None = None
    error: str = ""


# ---------------------------------------------------------------------------
# Job directory management
# ---------------------------------------------------------------------------

def create_job_dir(video_id: str = "") -> Path:
    """Create a temp job directory. Registers atexit cleanup."""
    job_id = video_id or uuid.uuid4().hex[:12]
    job_dir = TEMP_BASE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    # Safety net: register cleanup on process exit
    atexit.register(_cleanup_dir, job_dir)
    return job_dir


def cleanup_job_dir(job_dir: Path) -> None:
    """Remove a job directory and all contents."""
    _cleanup_dir(job_dir)


def _cleanup_dir(path: Path) -> None:
    """Safe recursive delete. Never raises."""
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# YouTube ID extraction
# ---------------------------------------------------------------------------

_YT_PATTERNS = [
    re.compile(r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:shorts/)([a-zA-Z0-9_-]{11})"),
]


def extract_youtube_id(url: str) -> str:
    """Extract the 11-char YouTube video ID from a URL, or empty string."""
    for pat in _YT_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# yt-dlp dependency check
# ---------------------------------------------------------------------------

def check_ytdlp() -> str | None:
    """Return path to yt-dlp binary, or None if not found."""
    return shutil.which("yt-dlp")


def check_ffmpeg() -> str | None:
    """Return path to ffmpeg binary, or None if not found."""
    return shutil.which("ffmpeg")


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_video(url: str, job_dir: Path) -> DownloadResult:
    """Download a YouTube video + metadata + subtitles to job_dir.

    Uses yt-dlp with sensible defaults:
    - Format: best video+audio up to 1080p (we don't need 4K for analysis)
    - Subtitles: auto-generated, prefer json3 format
    - Metadata: write .info.json
    """
    ytdlp = check_ytdlp()
    if not ytdlp:
        return DownloadResult(success=False, error="yt-dlp not found. Install: pip install yt-dlp")

    video_id = extract_youtube_id(url)

    output_template = str(job_dir / "video.%(ext)s")

    cmd = [
        ytdlp,
        "--format", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--sub-format", "json3",
        "--no-playlist",
        "--no-overwrites",
        "--output", output_template,
        url,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max
        )
    except subprocess.TimeoutExpired:
        return DownloadResult(
            success=False, job_dir=job_dir, video_id=video_id,
            error="Download timed out (10 min limit)",
        )
    except FileNotFoundError:
        return DownloadResult(
            success=False, job_dir=job_dir, video_id=video_id,
            error="yt-dlp binary not found",
        )

    if proc.returncode != 0:
        stderr = proc.stderr[:500] if proc.stderr else "unknown error"
        return DownloadResult(
            success=False, job_dir=job_dir, video_id=video_id,
            error=f"yt-dlp failed (exit {proc.returncode}): {stderr}",
        )

    # Find the downloaded video file
    video_path = _find_video(job_dir)
    if not video_path:
        return DownloadResult(
            success=False, job_dir=job_dir, video_id=video_id,
            error="Download completed but no video file found",
        )

    # Parse metadata from .info.json
    info_path = _find_info_json(job_dir)
    title, channel, description, duration = "", "", "", 0.0
    if info_path:
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            title = info.get("title", "")
            channel = info.get("channel", info.get("uploader", ""))
            description = info.get("description", "")
            duration = float(info.get("duration", 0))
            if not video_id:
                video_id = info.get("id", "")
        except (json.JSONDecodeError, OSError):
            pass

    # Find subtitle file
    sub_path = _find_subtitle(job_dir)

    return DownloadResult(
        success=True,
        job_dir=job_dir,
        video_path=video_path,
        video_id=video_id or uuid.uuid4().hex[:12],
        title=title,
        channel=channel,
        description=description,
        duration_s=duration,
        subtitle_path=sub_path,
        info_json_path=info_path,
    )


# ---------------------------------------------------------------------------
# Local file setup
# ---------------------------------------------------------------------------

def setup_local_file(file_path: str, job_dir: Path) -> DownloadResult:
    """Set up a local video file in a job directory (symlink, no copy)."""
    src = Path(file_path)
    if not src.is_file():
        return DownloadResult(success=False, error=f"File not found: {file_path}")

    # Symlink into job dir
    dest = job_dir / f"video{src.suffix}"
    try:
        dest.symlink_to(src.resolve())
    except OSError:
        # Fallback: copy if symlink fails
        shutil.copy2(src, dest)

    # Derive a video_id from filename
    video_id = src.stem[:40]

    return DownloadResult(
        success=True,
        job_dir=job_dir,
        video_path=dest,
        video_id=video_id,
        title=src.stem,
    )


# ---------------------------------------------------------------------------
# File finders
# ---------------------------------------------------------------------------

def _find_video(job_dir: Path) -> Path | None:
    """Find the downloaded video file."""
    for ext in (".mp4", ".mkv", ".webm", ".avi", ".mov"):
        for f in job_dir.glob(f"video{ext}"):
            if f.stat().st_size > 0:
                return f
    return None


def _find_info_json(job_dir: Path) -> Path | None:
    """Find the .info.json metadata file."""
    for f in job_dir.glob("*.info.json"):
        return f
    return None


def _find_subtitle(job_dir: Path) -> Path | None:
    """Find a subtitle file (prefer .json3, fallback to .vtt/.srt)."""
    for ext in (".json3", ".vtt", ".srt"):
        for f in job_dir.glob(f"*{ext}"):
            if f.stat().st_size > 0:
                return f
    return None
