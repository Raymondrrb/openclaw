"""Worker capabilities detection — reports what this node can do."""

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

CAPS_FILE = "caps.json"

# Distributed step kinds this worker can handle
DISTRIBUTED_STEP_KINDS = [
    "audio_concat_chunks",
    "tts_render_chunks",  # deprecated → alias for audio_concat_chunks
    "audio_postcheck",
    "pacing_validator",
    "final_validator",
    "render_config_generate",
    "script_generation",
    "ffmpeg_render",
    "ffprobe_analyze",
    "product_asset_fetch",
    "claims_guardrail",
]


def _run(cmd: list[str]) -> str | None:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def detect_gpu() -> dict:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"available": False}
    raw = _run([smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
    if not raw:
        return {"available": False}
    parts = [p.strip() for p in raw.split(",")]
    return {
        "available": True,
        "name": parts[0] if len(parts) > 0 else "unknown",
        "vram_mb": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
        "driver": parts[2] if len(parts) > 2 else "unknown",
    }


def _find_tool(name: str) -> str | None:
    """Find a tool on PATH or in well-known Windows locations."""
    found = shutil.which(name)
    if found:
        return found
    # Check common Windows install locations
    extra_dirs = [
        Path.home() / "AppData/Local/Microsoft/WinGet/Links",
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages",
        Path("C:/ProgramData/chocolatey/bin"),
        Path("C:/tools/ffmpeg/bin"),
    ]
    exe = f"{name}.exe" if platform.system() == "Windows" else name
    for d in extra_dirs:
        candidate = d / exe
        if candidate.exists():
            # Add the directory to PATH for this process so subprocess calls work
            import os
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            return str(candidate)
    return None


def detect_ffmpeg() -> dict:
    ff = _find_tool("ffmpeg")
    fp = _find_tool("ffprobe")
    version = _run([ff, "-version"]) if ff else None
    ver_line = version.split("\n")[0] if version else None
    return {"ffmpeg": ff is not None, "ffprobe": fp is not None, "version": ver_line}


def detect_capabilities() -> dict:
    gpu = detect_gpu()
    fftools = detect_ffmpeg()

    # Base capabilities (always available — pure Python / JSON)
    capabilities = [
        "pacing_validator",
        "final_validator",
        "render_config_generate",
        "script_generation",
        "product_asset_fetch",
        "claims_guardrail",
    ]

    # Distributed step kinds (the new protocol)
    supported_steps = [
        "pacing_validator",
        "final_validator",
        "render_config_generate",
        "script_generation",
        "product_asset_fetch",
        "claims_guardrail",
    ]

    # FFmpeg-dependent
    if fftools["ffprobe"]:
        capabilities.append("audio_postcheck")
        capabilities.append("ffprobe_analyze")
        supported_steps.append("audio_postcheck")
        supported_steps.append("ffprobe_analyze")
    if fftools["ffmpeg"]:
        capabilities.append("ffmpeg_render")
        capabilities.append("audio_concat_chunks")
        capabilities.append("tts_render_chunks")  # deprecated alias
        supported_steps.append("ffmpeg_render")
        supported_steps.append("audio_concat_chunks")
        supported_steps.append("tts_render_chunks")  # deprecated alias

    # GPU
    if gpu["available"]:
        capabilities.append("gpu_accelerated")

    return {
        "worker_version": "0.5.0",
        "platform": platform.system(),
        "platform_version": platform.version(),
        "hostname": platform.node(),
        "python": sys.version,
        "gpu": gpu,
        "ffmpeg": fftools,
        "capabilities": capabilities,
        "supported_steps": supported_steps,
    }


def write_caps(workspace: Path) -> dict:
    caps = detect_capabilities()
    out = workspace / CAPS_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(caps, indent=2))
    return caps


if __name__ == "__main__":
    print(json.dumps(detect_capabilities(), indent=2))
