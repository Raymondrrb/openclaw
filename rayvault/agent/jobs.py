"""Job executors for RayVault distributed worker."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from rayvault.agent.protocol import Envelope
from rayvault.audio_postcheck import run_audio_postcheck
from rayvault.tts_provider import cached_synthesize, get_provider, tts_input_hash


from rayvault.io import atomic_write_json as _atomic_write_json


class JobExecutionError(RuntimeError):
    """Structured execution failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class JobArtifact:
    path: str
    sha256: str
    size_bytes: int


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact(path: Path) -> JobArtifact:
    return JobArtifact(path=str(path), sha256=_sha256_file(path), size_bytes=path.stat().st_size)


def _run(cmd: List[str], *, timeout: int = 600) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise JobExecutionError("COMMAND_FAILED", f"Command failed: {' '.join(cmd)} :: {stderr[:500]}")
    return proc


def _ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _first_line(cmd: List[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        return out[0].strip() if out else ""
    except Exception:
        return ""


def _detect_cpu_model() -> str:
    cpu = platform.processor().strip()
    if cpu:
        return cpu
    if sys.platform == "darwin":
        return _first_line(["sysctl", "-n", "machdep.cpu.brand_string"]) or "unknown"
    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                ["wmic", "cpu", "get", "name"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if len(lines) >= 2:
                return lines[1]
            if lines:
                return lines[0]
        except Exception:
            pass
        return "unknown"
    return _first_line(["bash", "-lc", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"]) or "unknown"


def _detect_ram_gb() -> float:
    try:
        import psutil  # type: ignore

        return round(float(psutil.virtual_memory().total) / (1024 ** 3), 2)
    except Exception:
        pass
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if isinstance(pages, int) and isinstance(page_size, int) and pages > 0 and page_size > 0:
                return round((pages * page_size) / (1024 ** 3), 2)
    except Exception:
        pass
    return 0.0


def _detect_gpu() -> Dict[str, Any]:
    out = {"gpu": False, "gpu_model": "", "vram_gb": 0.0}
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        line = (proc.stdout or "").strip().splitlines()
        if proc.returncode == 0 and line:
            parts = [x.strip() for x in line[0].split(",")]
            if parts:
                out["gpu"] = True
                out["gpu_model"] = parts[0]
                if len(parts) > 1:
                    try:
                        out["vram_gb"] = round(float(parts[1]) / 1024.0, 2)
                    except Exception:
                        out["vram_gb"] = 0.0
    except Exception:
        pass
    return out


def _davinci_available() -> bool:
    # Check common binaries across macOS/Windows/Linux.
    candidates = [
        shutil.which("resolve"),
        shutil.which("DaVinciResolve"),
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve",
        r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe",
    ]
    return any(bool(c and Path(c).exists()) for c in candidates if c)


def _convert_to_wav(src: Path, dst: Path, *, sample_rate: int = 48000) -> None:
    if not _ffmpeg_exists():
        raise JobExecutionError("FFMPEG_MISSING", "ffmpeg/ffprobe not found in PATH")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        str(tmp),
    ]
    _run(cmd, timeout=300)
    os.replace(tmp, dst)


def _safe_output_dir(workspace_root: Path, payload: Dict[str, Any], default_rel: str) -> Path:
    rel = str(payload.get("output_dir", default_rel)).strip() or default_rel
    rel = rel.lstrip("/")
    out = (workspace_root / rel).resolve()
    workspace_real = workspace_root.resolve()
    if workspace_real not in out.parents and out != workspace_real:
        raise JobExecutionError("INVALID_OUTPUT_DIR", f"Output dir escapes workspace: {out}")
    out.mkdir(parents=True, exist_ok=True)
    return out


def _has_active_ui_session() -> bool:
    if sys.platform == "win32":
        session_name = str(os.environ.get("SESSIONNAME", "")).strip().lower()
        if session_name and session_name not in {"services"}:
            return True
        # Best-effort fallback
        try:
            proc = subprocess.run(["query", "user"], capture_output=True, text=True, timeout=10, check=False)
            out = (proc.stdout or "").lower()
            return "active" in out
        except Exception:
            return False
    if sys.platform == "darwin":
        return bool(os.environ.get("DISPLAY") or os.environ.get("TERM_PROGRAM"))
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _capture_screenshot(path: Path) -> Optional[Path]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            _run(["screencapture", "-x", str(path)], timeout=30)
            return path if path.exists() else None
        if sys.platform == "win32":
            win_path = str(path).replace("\\", "\\\\")
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "Add-Type -AssemblyName System.Drawing;"
                "$bounds=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
                "$bmp=New-Object System.Drawing.Bitmap $bounds.Width,$bounds.Height;"
                "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                "$g.CopyFromScreen($bounds.Location,[System.Drawing.Point]::Empty,$bounds.Size);"
                f"$bmp.Save('{win_path}');"
                "$g.Dispose();$bmp.Dispose();"
            )
            _run(["powershell", "-NoProfile", "-Command", ps], timeout=40)
            return path if path.exists() else None
        # Linux fallback
        if shutil.which("gnome-screenshot"):
            _run(["gnome-screenshot", "-f", str(path)], timeout=30)
            return path if path.exists() else None
    except Exception:
        return None
    return None


def _ocr_image(path: Path) -> str:
    if not path.exists() or shutil.which("tesseract") is None:
        return ""
    try:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        return ""
    return ""


def detect_capabilities() -> Dict[str, Any]:
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    ffmpeg_version = _first_line(["ffmpeg", "-version"]) if ffmpeg_bin else ""
    gpu = _detect_gpu()
    caps: Dict[str, Any] = {
        # Contract-first capabilities (required by controller requirement matching)
        "os": platform.system().lower() or sys.platform.lower(),
        "cpu": _detect_cpu_model(),
        "ram_gb": _detect_ram_gb(),
        "gpu_model": gpu.get("gpu_model", ""),
        "vram_gb": gpu.get("vram_gb", 0.0),
        "python_version": sys.version.split()[0],
        "ffmpeg_version": ffmpeg_version or "missing",
        "davinci_available": _davinci_available(),
        # Backward compatibility fields
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "ffmpeg": bool(ffmpeg_bin),
        "ffprobe": bool(ffprobe_bin),
        "openclaw_available": bool(shutil.which("openclaw")),
        "gpu": bool(gpu.get("gpu", False)),
        "tts_provider": os.environ.get("TTS_PROVIDER", "elevenlabs"),
        "ui_session_active": _has_active_ui_session(),
    }
    return caps


def _execute_tts_render_chunks(
    env: Envelope,
    payload: Dict[str, Any],
    *,
    workspace_root: Path,
) -> Dict[str, Any]:
    chunks = payload.get("chunks") or []
    if not isinstance(chunks, list) or not chunks:
        raise JobExecutionError("INVALID_INPUT", "payload.chunks must be a non-empty list")

    provider_name = str(payload.get("provider") or os.environ.get("TTS_PROVIDER", "mock")).strip()
    provider = get_provider(provider_name)
    voice_id = str(payload.get("voice_id") or os.environ.get("ELEVENLABS_VOICE_ID", "")).strip() or "default"
    model_id = str(payload.get("model_id", "")).strip()
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}

    out_dir = _safe_output_dir(workspace_root, payload, f"artifacts/{env.job_id}/tts")
    cache_dir = (workspace_root / "cache" / "tts_chunks").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    artifacts: List[JobArtifact] = []
    chunk_meta: List[Dict[str, Any]] = []

    for i, chunk in enumerate(chunks, 1):
        if not isinstance(chunk, dict):
            raise JobExecutionError("INVALID_INPUT", f"chunk {i} must be object")
        chunk_id = str(chunk.get("chunk_id") or f"chunk_{i:02d}").strip()
        text = str(chunk.get("text", "")).strip()
        if not text:
            raise JobExecutionError("INVALID_INPUT", f"chunk {chunk_id} has empty text")

        input_hash = tts_input_hash(
            text,
            voice_id,
            provider.name,
            model_id=model_id,
            settings=settings,
        )
        wav_name = f"{chunk_id}.wav"
        wav_path = out_dir / wav_name
        cached_wav = cache_dir / f"{input_hash}.wav"

        cache_hit = False
        if cached_wav.exists() and not bool(payload.get("force", False)):
            shutil.copy2(cached_wav, wav_path)
            cache_hit = True
        else:
            if provider.name == "mock":
                cached_synthesize(
                    provider,
                    text,
                    voice_id,
                    wav_path,
                    cache_dir=cache_dir,
                    model_id=model_id,
                    settings=settings,
                )
            else:
                tmp_mp3 = out_dir / f"{chunk_id}.mp3"
                cached_synthesize(
                    provider,
                    text,
                    voice_id,
                    tmp_mp3,
                    cache_dir=cache_dir,
                    model_id=model_id,
                    settings=settings,
                )
                _convert_to_wav(tmp_mp3, wav_path)
                tmp_mp3.unlink(missing_ok=True)

            if not cached_wav.exists():
                shutil.copy2(wav_path, cached_wav)

        art = _artifact(wav_path)
        artifacts.append(art)
        chunk_meta.append(
            {
                "chunk_id": chunk_id,
                "path": str(wav_path),
                "sha256": art.sha256,
                "size_bytes": art.size_bytes,
                "cache_hit": cache_hit,
                "inputs_hash": input_hash,
            }
        )

    manifest = {
        "run_id": env.run_id,
        "job_id": env.job_id,
        "step_name": env.step_name,
        "chunks": chunk_meta,
    }
    manifest_path = out_dir / "tts_chunks_manifest.json"
    _atomic_write_json(manifest_path, manifest)
    artifacts.append(_artifact(manifest_path))

    return {
        "exit_code": 0,
        "status": "succeeded",
        "metrics": {
            "chunks": len(chunks),
            "provider": provider.name,
            "voice_id": voice_id,
        },
        "artifacts": [a.__dict__ for a in artifacts],
    }


def _execute_audio_postcheck(env: Envelope, payload: Dict[str, Any], *, workspace_root: Path) -> Dict[str, Any]:
    video_path = Path(str(payload.get("video_path", "")).strip()).expanduser()
    if not video_path.exists():
        raise JobExecutionError("INVALID_INPUT", f"video_path not found: {video_path}")

    render_config: Dict[str, Any] = {}
    render_cfg_raw = payload.get("render_config")
    if isinstance(render_cfg_raw, dict):
        render_config = render_cfg_raw
    elif isinstance(render_cfg_raw, str) and render_cfg_raw.strip():
        cfg_path = Path(render_cfg_raw).expanduser()
        if cfg_path.exists():
            render_config = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not render_config:
        render_config = {"segments": []}

    try:
        expected_duration = float(payload.get("expected_duration_sec", 0) or 0)
    except (ValueError, TypeError):
        expected_duration = 0.0
    if expected_duration <= 0:
        expected_duration = 0.0
        if _ffmpeg_exists():
            proc = _run([
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ], timeout=30)
            try:
                expected_duration = float((proc.stdout or "0").strip() or 0)
            except ValueError:
                expected_duration = 0.0

    result = run_audio_postcheck(video_path, render_config, expected_duration)
    out_dir = _safe_output_dir(workspace_root, payload, f"artifacts/{env.job_id}/audio_postcheck")
    report_path = out_dir / "audio_postcheck.json"
    _atomic_write_json(report_path, result.to_dict())
    art = _artifact(report_path)
    return {
        "exit_code": int(result.to_dict().get("exit_code", 0)),
        "status": "succeeded" if result.ok else "failed",
        "metrics": result.to_dict().get("metrics", {}),
        "artifacts": [art.__dict__],
    }


def _execute_ffmpeg_probe(env: Envelope, payload: Dict[str, Any], *, workspace_root: Path) -> Dict[str, Any]:
    if not _ffmpeg_exists():
        raise JobExecutionError("FFMPEG_MISSING", "ffmpeg/ffprobe not found in PATH")

    media_path = Path(str(payload.get("media_path", "")).strip()).expanduser()
    if not media_path.exists():
        raise JobExecutionError("INVALID_INPUT", f"media_path not found: {media_path}")

    out_dir = _safe_output_dir(workspace_root, payload, f"artifacts/{env.job_id}/probe")
    probe_path = out_dir / "ffprobe.json"

    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-print_format",
            "json",
            str(media_path),
        ],
        timeout=60,
    )
    _atomic_write_json(probe_path, json.loads(proc.stdout or "{}"))
    art = _artifact(probe_path)
    return {
        "exit_code": 0,
        "status": "succeeded",
        "metrics": {"media_path": str(media_path)},
        "artifacts": [art.__dict__],
    }


def _execute_frame_sampling(env: Envelope, payload: Dict[str, Any], *, workspace_root: Path) -> Dict[str, Any]:
    if not _ffmpeg_exists():
        raise JobExecutionError("FFMPEG_MISSING", "ffmpeg/ffprobe not found in PATH")

    video_path = Path(str(payload.get("video_path", "")).strip()).expanduser()
    if not video_path.exists():
        raise JobExecutionError("INVALID_INPUT", f"video_path not found: {video_path}")

    try:
        every_sec = float(payload.get("every_sec", 5.0) or 5.0)
    except (ValueError, TypeError):
        every_sec = 5.0
    if every_sec <= 0:
        every_sec = 5.0

    out_dir = _safe_output_dir(workspace_root, payload, f"artifacts/{env.job_id}/frames")
    out_pattern = out_dir / "frame_%06d.jpg"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{every_sec}",
            str(out_pattern),
        ],
        timeout=600,
    )

    frame_files = sorted(out_dir.glob("frame_*.jpg"))
    if not frame_files:
        raise JobExecutionError("FRAME_SAMPLING_EMPTY", "No frames generated")

    artifacts = [_artifact(p).__dict__ for p in frame_files[:200]]
    index_path = out_dir / "frames_index.json"
    _atomic_write_json(index_path, {
        "run_id": env.run_id,
        "job_id": env.job_id,
        "count": len(frame_files),
        "every_sec": every_sec,
        "frames": [str(p) for p in frame_files],
    })
    artifacts.append(_artifact(index_path).__dict__)

    return {
        "exit_code": 0,
        "status": "succeeded",
        "metrics": {"frames": len(frame_files), "every_sec": every_sec},
        "artifacts": artifacts,
    }


def _execute_openclaw_task(env: Envelope, payload: Dict[str, Any], *, workspace_root: Path) -> Dict[str, Any]:
    if shutil.which("openclaw") is None:
        raise JobExecutionError("OPENCLAW_MISSING", "openclaw CLI not found")

    if not _has_active_ui_session():
        raise JobExecutionError("UI_SESSION_REQUIRED", "No active graphical session for OPENCLAW_TASK")

    message = str(payload.get("message", "")).strip()
    if not message:
        raise JobExecutionError("INVALID_INPUT", "payload.message is required for OPENCLAW_TASK")

    agent = str(payload.get("agent", "researcher")).strip() or "researcher"
    try:
        timeout_sec = int(payload.get("timeout_sec", 600) or 600)
    except (ValueError, TypeError):
        timeout_sec = 600
    out_dir = _safe_output_dir(workspace_root, payload, f"artifacts/{env.job_id}/openclaw")

    proc = _run(
        [
            "openclaw",
            "agent",
            "--agent",
            agent,
            "--timeout",
            str(timeout_sec),
            "--message",
            message,
        ],
        timeout=timeout_sec + 120,
    )

    raw_out = out_dir / "openclaw_output.txt"
    raw_out.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")

    screenshot = _capture_screenshot(out_dir / "proof_screenshot.png")
    ocr_text = ""
    if screenshot and screenshot.exists():
        ocr_text = _ocr_image(screenshot)
        if ocr_text:
            (out_dir / "proof_ocr.txt").write_text(ocr_text, encoding="utf-8")

    artifacts = [_artifact(raw_out).__dict__]
    if screenshot and screenshot.exists():
        artifacts.append(_artifact(screenshot).__dict__)
        ocr_path = out_dir / "proof_ocr.txt"
        if ocr_path.exists():
            artifacts.append(_artifact(ocr_path).__dict__)

    return {
        "exit_code": 0,
        "status": "succeeded",
        "metrics": {
            "agent": agent,
            "proof_screenshot": bool(screenshot and screenshot.exists()),
            "proof_ocr_chars": len(ocr_text),
        },
        "artifacts": artifacts,
    }


def execute_job(
    env: Envelope,
    payload: Dict[str, Any],
    *,
    workspace_root: Path,
) -> Dict[str, Any]:
    """Execute a supported job step and return normalized result."""
    workspace_root = workspace_root.resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "TTS_RENDER_CHUNKS": _execute_tts_render_chunks,
        "AUDIO_POSTCHECK": _execute_audio_postcheck,
        "FFMPEG_PROBE": _execute_ffmpeg_probe,
        "FRAME_SAMPLING": _execute_frame_sampling,
        "OPENCLAW_TASK": _execute_openclaw_task,
    }

    fn = dispatch.get(env.step_name)
    if not fn:
        raise JobExecutionError("STEP_UNSUPPORTED", f"Unsupported step_name={env.step_name}")

    started = time.time()
    out = fn(env, payload or {}, workspace_root=workspace_root)
    out.setdefault("exit_code", 0)
    out.setdefault("status", "succeeded")
    out.setdefault("metrics", {})
    out.setdefault("artifacts", [])
    out["duration_ms"] = int((time.time() - started) * 1000)
    return out
