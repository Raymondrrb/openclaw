"""Video Study pipeline — frame extraction and transcript parsing.

Extracts keyframes via ffmpeg (scene change detection or interval) and
parses YouTube json3 caption format into plain text with timestamps.

External deps: ffmpeg (system binary, called via subprocess).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.video_study_download import check_ffmpeg


@dataclass
class TranscriptSegment:
    """A single transcript segment with timestamp."""
    start_s: float
    end_s: float
    text: str


@dataclass
class ExtractionResult:
    """Result of frame extraction + transcript parsing."""
    success: bool
    frames: list[Path] = field(default_factory=list)
    transcript: list[TranscriptSegment] = field(default_factory=list)
    transcript_text: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def parse_json3_captions(path: Path) -> list[TranscriptSegment]:
    """Parse YouTube json3 subtitle file into TranscriptSegments."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    segments: list[TranscriptSegment] = []

    # json3 format: {"events": [{"tStartMs": N, "dDurationMs": N, "segs": [{"utf8": "..."}]}]}
    events = data if isinstance(data, list) else data.get("events", [])

    for event in events:
        if not isinstance(event, dict):
            continue

        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        segs = event.get("segs", [])

        text_parts = []
        for seg in segs:
            if isinstance(seg, dict):
                text_parts.append(seg.get("utf8", ""))

        text = "".join(text_parts).strip()
        if not text or text == "\n":
            continue

        segments.append(TranscriptSegment(
            start_s=start_ms / 1000.0,
            end_s=(start_ms + duration_ms) / 1000.0,
            text=text,
        ))

    return segments


def parse_vtt_captions(path: Path) -> list[TranscriptSegment]:
    """Parse WebVTT subtitle file into TranscriptSegments (basic parser)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    segments: list[TranscriptSegment] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for timestamp lines: "00:00:01.000 --> 00:00:04.000"
        if " --> " in line:
            parts = line.split(" --> ")
            start = _parse_vtt_time(parts[0].strip())
            end = _parse_vtt_time(parts[1].strip().split(" ")[0])
            # Collect text lines until blank
            text_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            text = " ".join(text_lines)
            # Strip VTT tags like <c> </c>
            import re
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text:
                segments.append(TranscriptSegment(start_s=start, end_s=end, text=text))
        else:
            i += 1

    return segments


def _parse_vtt_time(ts: str) -> float:
    """Parse VTT timestamp (HH:MM:SS.mmm or MM:SS.mmm) to seconds."""
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
    except (ValueError, IndexError):
        pass
    return 0.0


def segments_to_text(segments: list[TranscriptSegment]) -> str:
    """Join transcript segments into plain text with timestamps."""
    lines = []
    for seg in segments:
        ts = _format_timestamp(seg.start_s)
        lines.append(f"[{ts}] {seg.text}")
    return "\n".join(lines)


def _format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

def extract_frames_scene(
    video_path: Path,
    output_dir: Path,
    *,
    threshold: float = 0.3,
    max_frames: int = 80,
) -> list[Path]:
    """Extract keyframes using ffmpeg scene change detection."""
    ffmpeg = check_ffmpeg()
    if not ffmpeg:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "frame_%04d.jpg")

    cmd = [
        ffmpeg,
        "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr",
        "-q:v", "2",
        pattern,
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # 5 min max
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    frames = sorted(output_dir.glob("frame_*.jpg"))

    # Subsample if over max
    if len(frames) > max_frames:
        frames = _subsample(frames, max_frames)

    return frames


def extract_frames_interval(
    video_path: Path,
    output_dir: Path,
    *,
    fps: float = 0.5,
    max_frames: int = 80,
) -> list[Path]:
    """Extract frames at fixed interval using ffmpeg."""
    ffmpeg = check_ffmpeg()
    if not ffmpeg:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "frame_%04d.jpg")

    cmd = [
        ffmpeg,
        "-i", str(video_path),
        "-vf", f"fps={fps}",
        "-q:v", "2",
        pattern,
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    frames = sorted(output_dir.glob("frame_*.jpg"))

    if len(frames) > max_frames:
        frames = _subsample(frames, max_frames)

    return frames


def _subsample(frames: list[Path], target: int) -> list[Path]:
    """Evenly subsample a list of frames to target count."""
    if not frames or target >= len(frames):
        return frames
    step = len(frames) / target
    return [frames[int(i * step)] for i in range(target)]


# ---------------------------------------------------------------------------
# Sample frames for API (select N evenly from available)
# ---------------------------------------------------------------------------

def sample_frames(frames: list[Path], count: int = 20) -> list[Path]:
    """Select count frames evenly distributed from the full list."""
    return _subsample(frames, count)


# ---------------------------------------------------------------------------
# Full extraction pipeline
# ---------------------------------------------------------------------------

def extract_all(
    video_path: Path,
    job_dir: Path,
    *,
    subtitle_path: Path | None = None,
    frame_strategy: str = "scene",
    max_frames: int = 80,
) -> ExtractionResult:
    """Run full extraction: transcript + frames."""
    # Parse transcript
    transcript: list[TranscriptSegment] = []
    if subtitle_path and subtitle_path.is_file():
        if subtitle_path.suffix == ".json3":
            transcript = parse_json3_captions(subtitle_path)
        elif subtitle_path.suffix in (".vtt", ".srt"):
            transcript = parse_vtt_captions(subtitle_path)

    transcript_text = segments_to_text(transcript) if transcript else ""

    # Extract frames
    frames_dir = job_dir / "frames"
    if frame_strategy == "scene":
        frames = extract_frames_scene(video_path, frames_dir, max_frames=max_frames)
        # Fallback to interval if scene detection yields too few frames
        if len(frames) < 5:
            frames = extract_frames_interval(video_path, frames_dir, max_frames=max_frames)
    else:
        frames = extract_frames_interval(video_path, frames_dir, max_frames=max_frames)

    if not frames and not transcript:
        return ExtractionResult(
            success=False,
            error="No frames extracted and no transcript available",
        )

    return ExtractionResult(
        success=True,
        frames=frames,
        transcript=transcript,
        transcript_text=transcript_text,
    )
