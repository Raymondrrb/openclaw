"""Dzine Handoff — "Alfândega" — nothing enters /final without full validation.

Closes the most unstable point in the pipeline: the moment between
"browser clicked Export" and "we have a validated mp4 in state/".

Flow:
  1. wait_file_stable() polls until size + mtime stop changing
  2. Move to staging (atomic via os.replace)
  3. validate_video_file() via full ffprobe JSON (duration + size + bitrate + codecs)
  4. Probe retries handle transient "moov atom not found" from incomplete writes
  5. Move to final (atomic via os.replace)
  6. Update state/video/index.json atomically

Also provides:
  - find_orphan_videos() — "zombie search" for files in /final not in index
  - ffprobe_json() — full JSON probe for detailed inspection

If any step fails, the file stays in staging for manual inspection.
Never deletes a file that hasn't been validated.

Dependencies:
  - ffprobe (required for duration + bitrate + codec checks)

Usage:
    from tools.lib.dzine_handoff import secure_handoff, find_orphan_videos

    result = secure_handoff(
        downloaded_path=Path("~/Downloads/export_123.mp4"),
        expected_final_path=Path("state/video/final/V_RAY-99_intro_a1b2c3d4.mp4"),
        run_id="RAY-99",
        segment_id="intro",
        audio_sha256="a1b2c3d4e5f6...",
        target_duration_sec=12.0,
    )
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Default paths + thresholds
# ---------------------------------------------------------------------------

STATE_DIR = Path("state")
VIDEO_DIR = STATE_DIR / "video"
FINAL_DIR = VIDEO_DIR / "final"
STAGING_DIR = VIDEO_DIR / "staging"
INDEX_PATH = VIDEO_DIR / "index.json"

MIN_BYTES_DEFAULT = 500_000
DURATION_TOL_SEC_DEFAULT = 0.15
BITRATE_MIN_BPS_DEFAULT = 1_000_000  # 1 Mbps
ALLOWED_AUDIO_CODECS_DEFAULT: Set[str] = {"aac", "mp3"}
ALLOWED_VIDEO_CODECS_DEFAULT: Set[str] = {"h264", "hevc"}


# ---------------------------------------------------------------------------
# Atomic JSON I/O
# ---------------------------------------------------------------------------

def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: write to .tmp, fsync, os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_index(index_path: Path = INDEX_PATH) -> dict:
    """Load video index. Returns empty structure on missing/corrupt file."""
    if not index_path.exists():
        return {"version": "1.0", "items": {}}
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "1.0", "items": {}}


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def _run_ffprobe(args: List[str], timeout: int = 6) -> Tuple[int, str, str]:
    """Run ffprobe and return (returncode, stdout, stderr)."""
    import subprocess
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def ffprobe_json(path: Path) -> Optional[dict]:
    """Full ffprobe JSON output (-show_format -show_streams)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    code, out, _ = _run_ffprobe(cmd)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def ffprobe_duration_sec(meta: dict) -> float:
    """Extract duration from ffprobe JSON metadata."""
    try:
        return float(meta.get("format", {}).get("duration", 0.0) or 0.0)
    except Exception:
        return 0.0


def ffprobe_bitrate_bps(meta: dict) -> int:
    """Extract bitrate (bps) from ffprobe JSON metadata."""
    br = meta.get("format", {}).get("bit_rate")
    try:
        return int(float(br)) if br else 0
    except Exception:
        return 0


def ffprobe_codecs(meta: dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract (video_codec, audio_codec) from ffprobe JSON metadata."""
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    for s in meta.get("streams", []) or []:
        if s.get("codec_type") == "video" and not vcodec:
            vcodec = s.get("codec_name")
        if s.get("codec_type") == "audio" and not acodec:
            acodec = s.get("codec_name")
    return vcodec, acodec


# ---------------------------------------------------------------------------
# Stable file wait
# ---------------------------------------------------------------------------

def wait_file_stable(
    path: Path,
    *,
    timeout: float = 90.0,
    check_interval: float = 1.5,
    stable_cycles: int = 3,
) -> bool:
    """Wait until file size + mtime stop changing.

    Considers stable when (size, mtime) are identical for `stable_cycles`
    consecutive polls. This prevents ffprobe from reading a partially-
    written file or one still being flushed by the browser.
    """
    start = time.monotonic()
    last: Optional[Tuple[int, float]] = None
    stable = 0

    while (time.monotonic() - start) < timeout:
        if not path.exists():
            time.sleep(check_interval)
            continue
        try:
            st = path.stat()
        except FileNotFoundError:
            time.sleep(check_interval)
            continue

        cur = (st.st_size, st.st_mtime)
        if st.st_size > 0 and last == cur:
            stable += 1
            if stable >= stable_cycles:
                return True
        else:
            stable = 0
            last = cur
        time.sleep(check_interval)

    return False


# ---------------------------------------------------------------------------
# Video validation — full probe
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    """Outcome of video file validation."""
    ok: bool
    duration_sec: float
    bitrate_bps: int
    video_codec: Optional[str]
    audio_codec: Optional[str]
    file_bytes: int = 0
    reason: Optional[str] = None


def validate_video_file(
    path: Path,
    target_duration_sec: Optional[float] = None,
    *,
    duration_tolerance_sec: float = DURATION_TOL_SEC_DEFAULT,
    min_bytes: int = MIN_BYTES_DEFAULT,
    bitrate_min_bps: int = BITRATE_MIN_BPS_DEFAULT,
    allowed_audio_codecs: Set[str] = ALLOWED_AUDIO_CODECS_DEFAULT,
    allowed_video_codecs: Set[str] = ALLOWED_VIDEO_CODECS_DEFAULT,
) -> ProbeResult:
    """Validate video: exists + size + duration + bitrate + codecs.

    Args:
        target_duration_sec: Expected duration. None = skip duration check.
            Use None for index refresh where target is unknown.
    """
    if not path.exists():
        return ProbeResult(False, 0.0, 0, None, None, 0, "missing_file")

    file_bytes = path.stat().st_size
    if file_bytes < min_bytes:
        return ProbeResult(False, 0.0, 0, None, None, file_bytes, "too_small")

    meta = ffprobe_json(path)
    if not meta:
        return ProbeResult(False, 0.0, 0, None, None, file_bytes, "ffprobe_failed")

    dur = ffprobe_duration_sec(meta)
    br = ffprobe_bitrate_bps(meta)
    vcodec, acodec = ffprobe_codecs(meta)

    if target_duration_sec is not None and target_duration_sec > 0:
        if abs(dur - target_duration_sec) > duration_tolerance_sec:
            return ProbeResult(False, dur, br, vcodec, acodec, file_bytes, "duration_mismatch")

    if br and br < bitrate_min_bps:
        return ProbeResult(False, dur, br, vcodec, acodec, file_bytes, "low_bitrate")

    if vcodec and vcodec not in allowed_video_codecs:
        return ProbeResult(False, dur, br, vcodec, acodec, file_bytes, "video_codec_unexpected")

    if acodec and acodec not in allowed_audio_codecs:
        return ProbeResult(False, dur, br, vcodec, acodec, file_bytes, "audio_codec_unexpected")

    return ProbeResult(True, dur, br, vcodec, acodec, file_bytes)


# ---------------------------------------------------------------------------
# Hash + naming helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def infer_sha8_from_filename(p: Path) -> Optional[str]:
    """Extract sha8 from V_{run_id}_{segment_id}_{sha8}.mp4 naming."""
    m = re.search(r"_([0-9a-fA-F]{8})\.mp4$", p.name)
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------------------
# The Customs: secure_handoff — nothing enters /final without validation
# ---------------------------------------------------------------------------

def secure_handoff(
    downloaded_path: Path,
    expected_final_path: Path,
    run_id: str,
    segment_id: str,
    audio_sha256: str,
    target_duration_sec: float,
    *,
    staging_dir: Path = STAGING_DIR,
    index_path: Path = INDEX_PATH,
    duration_tolerance_sec: float = DURATION_TOL_SEC_DEFAULT,
    min_bytes: int = MIN_BYTES_DEFAULT,
    bitrate_min_bps: int = BITRATE_MIN_BPS_DEFAULT,
    allowed_audio_codecs: Set[str] = ALLOWED_AUDIO_CODECS_DEFAULT,
    allowed_video_codecs: Set[str] = ALLOWED_VIDEO_CODECS_DEFAULT,
    retries_probe: int = 3,
    retry_sleep: float = 2.0,
    stable_timeout: float = 90.0,
    stable_interval: float = 1.5,
    stable_cycles: int = 3,
) -> ProbeResult:
    """Secure handoff: wait stable → staging → probe (w/ retry) → final → index.

    Flow:
      1) Wait for downloaded file to stabilize (size + mtime)
      2) Atomic move to staging dir
      3) Validate with ffprobe (retries for transient "moov atom not found")
      4) Atomic move to final dir
      5) Update video index atomically

    On failure, the file remains in staging for manual inspection.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    expected_final_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Wait for download to stabilize
    if not wait_file_stable(
        downloaded_path,
        timeout=stable_timeout,
        check_interval=stable_interval,
        stable_cycles=stable_cycles,
    ):
        return ProbeResult(False, 0.0, 0, None, None, 0, "download_never_stabilized")

    # 2. Atomic move to staging
    staging_path = staging_dir / expected_final_path.name
    try:
        os.replace(str(downloaded_path), str(staging_path))
    except Exception:
        try:
            downloaded_path.replace(staging_path)
        except Exception as e:
            return ProbeResult(False, 0.0, 0, None, None, 0, f"staging_move_failed:{e}")

    # 3. Probe with retry (handles transient "moov atom not found")
    last_res: Optional[ProbeResult] = None
    for _ in range(retries_probe):
        res = validate_video_file(
            staging_path,
            target_duration_sec=target_duration_sec,
            duration_tolerance_sec=duration_tolerance_sec,
            min_bytes=min_bytes,
            bitrate_min_bps=bitrate_min_bps,
            allowed_audio_codecs=allowed_audio_codecs,
            allowed_video_codecs=allowed_video_codecs,
        )
        last_res = res
        if res.ok:
            break
        if res.reason in {"ffprobe_failed", "too_small"}:
            time.sleep(retry_sleep)
            continue
        break  # logical failure (duration/codec/bitrate) — no retry

    if not last_res or not last_res.ok:
        return last_res or ProbeResult(False, 0.0, 0, None, None, 0, "unknown_probe_failure")

    # 4. Atomic move to final
    try:
        os.replace(str(staging_path), str(expected_final_path))
    except Exception as e:
        return ProbeResult(
            False, last_res.duration_sec, last_res.bitrate_bps,
            last_res.video_codec, last_res.audio_codec,
            last_res.file_bytes, f"final_move_failed:{e}",
        )

    # 5. Update video index
    idx = load_index(index_path)
    items = idx.setdefault("items", {})
    sha8 = audio_sha256[:8].lower()
    items[sha8] = {
        "run_id": run_id,
        "segment_id": segment_id,
        "audio_sha256": audio_sha256,
        "path": str(expected_final_path),
        "duration": last_res.duration_sec,
        "bitrate_bps": last_res.bitrate_bps,
        "video_codec": last_res.video_codec,
        "audio_codec": last_res.audio_codec,
        "file_bytes": last_res.file_bytes,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    atomic_write_json(index_path, idx)

    return last_res


# ---------------------------------------------------------------------------
# Zombie search — orphan files in /final not tracked by index
# ---------------------------------------------------------------------------

@dataclass
class ZombieReport:
    """Report of orphan video files not tracked in the index."""
    orphan_files: List[Path]
    orphan_count: int


def find_orphan_videos(
    final_dir: Path = FINAL_DIR,
    index_path: Path = INDEX_PATH,
) -> ZombieReport:
    """Find .mp4 files in final_dir not referenced by index.json."""
    idx = load_index(index_path)
    items = idx.get("items", {}) or {}
    indexed_paths = {
        v.get("path") for v in items.values() if isinstance(v, dict)
    }
    orphans: List[Path] = []

    if final_dir.exists():
        for fp in sorted(final_dir.glob("*.mp4")):
            if str(fp) not in indexed_paths:
                orphans.append(fp)

    return ZombieReport(orphan_files=orphans, orphan_count=len(orphans))
