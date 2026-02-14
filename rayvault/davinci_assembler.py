#!/usr/bin/env python3
"""RayVault DaVinci Assembler — production render via Resolve Studio.

Orchestrates the full DaVinci render pipeline:
  1. Gates (files, Resolve connection, temporal consistency)
  2. Project creation with output settings
  3. Media import + bin organization
  4. Timeline construction (V1 video + V2 overlays + A1 audio)
  5. Ken Burns via seed-deterministic patterns
  6. Deliver configuration + render
  7. Stall detection (watchdog)
  8. Post-render verification (ffprobe + loudness)
  9. Receipts + manifest patch
  10. FFmpeg shadow fallback if DaVinci fails

Golden rules:
  1. DaVinci is PRIMARY. FFmpeg is shadow/lifeboat only.
  2. API-first for everything. OpenClaw only for Deliver lacunas.
  3. Every step produces evidence (receipts, screenshots, hashes).
  4. davinci_required=true blocks publish unless engine_used=davinci.

Usage:
    python3 -m rayvault.davinci_assembler --run-dir state/runs/RUN_2026_02_14_A --apply
    python3 -m rayvault.davinci_assembler --run-dir state/runs/RUN_2026_02_14_A --apply --debug

Exit codes:
    0: success (or dry-run)
    1: runtime error
    2: gate failure
    3: Resolve connection failed
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALL_TIMEOUT_SEC = 120  # No output growth for this long = stall
RENDER_POLL_SEC = 10  # Poll render status every N seconds
RENDER_TIMEOUT_SEC = 3600  # Max 1 hour render
MAX_RETRY = 1  # Max 1 retry after stall (no infinite loops)
DURATION_TOLERANCE_SEC = 0.2
LUFS_TARGET = -14.0
LUFS_TOLERANCE = 1.5
TRUE_PEAK_MAX = -0.5

TEMPLATE_PROJECT_NAME = "RayVault_Template_v1"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def wav_duration_seconds(path: Path) -> Optional[float]:
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return frames / float(rate) if rate > 0 else None
    except Exception:
        return None


def ffprobe_json(path: Path) -> Optional[Dict[str, Any]]:
    """Run ffprobe and return parsed JSON output."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return json.loads(proc.stdout)
    except Exception:
        pass
    return None


def ffprobe_duration(path: Path) -> Optional[float]:
    info = ffprobe_json(path)
    if info:
        try:
            return float(info["format"]["duration"])
        except (KeyError, ValueError):
            pass
    return None


def measure_loudness(path: Path) -> Optional[Dict[str, float]]:
    """Measure integrated loudness via ffmpeg loudnorm in analysis mode."""
    try:
        cmd = [
            "ffmpeg", "-i", str(path), "-af",
            "loudnorm=I=-14:LRA=7:TP=-1:print_format=json",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # Parse the JSON output from stderr (ffmpeg prints loudnorm stats there)
        stderr = proc.stderr
        # Find the JSON block in stderr
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(stderr[json_start:json_end])
            return {
                "input_i": float(data.get("input_i", 0)),
                "input_tp": float(data.get("input_tp", 0)),
                "input_lra": float(data.get("input_lra", 0)),
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def gate_essential_files(run_dir: Path) -> GateResult:
    """Gate A: essential files must exist."""
    errors = []
    for name in ("00_manifest.json", "05_render_config.json", "02_audio.wav"):
        if not (run_dir / name).exists():
            errors.append(f"MISSING: {name}")
    if not (run_dir / "publish" / "overlays" / "overlays_index.json").exists():
        errors.append("MISSING: publish/overlays/overlays_index.json")
    return GateResult(ok=len(errors) == 0, errors=errors)


def gate_resolve_connection() -> Tuple[GateResult, Optional[Any]]:
    """Gate B: DaVinci Resolve must be running and scriptable."""
    from rayvault.resolve_bridge import ResolveBridge
    bridge = ResolveBridge()
    if not bridge.connect():
        if not bridge.caps.scripting_available:
            return GateResult(
                ok=False,
                errors=["RESOLVE_SCRIPT_NOT_FOUND: DaVinciResolveScript module not available"],
            ), None
        return GateResult(
            ok=False,
            errors=["RESOLVE_NOT_RUNNING: Cannot connect to DaVinci Resolve (is it open?)"],
        ), None
    return GateResult(ok=True), bridge


# ---------------------------------------------------------------------------
# Inputs hash (idempotency)
# ---------------------------------------------------------------------------


def compute_inputs_hash(run_dir: Path) -> str:
    """Compute global render inputs hash for idempotency."""
    parts = []
    for name in ("05_render_config.json",):
        p = run_dir / name
        if p.exists():
            parts.append(sha1_file(p))

    oi = run_dir / "publish" / "overlays" / "overlays_index.json"
    if oi.exists():
        parts.append(sha1_file(oi))

    audio = run_dir / "02_audio.wav"
    if audio.exists():
        st = audio.stat()
        parts.append(f"audio:{st.st_size}:{int(st.st_mtime)}")

    parts.append(f"engine:davinci")
    return sha1_text("|".join(parts))


# ---------------------------------------------------------------------------
# Post-render verification
# ---------------------------------------------------------------------------


@dataclass
class VerifyResult:
    ok: bool
    duration_sec: float = 0.0
    codec_video: str = ""
    codec_audio: str = ""
    fps: float = 0.0
    lufs_integrated: Optional[float] = None
    true_peak: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def verify_output(
    output_path: Path,
    expected_duration: float,
    expected_fps: float = 30.0,
) -> VerifyResult:
    """Verify rendered output with ffprobe + loudness analysis."""
    result = VerifyResult(ok=True)

    if not output_path.exists():
        return VerifyResult(ok=False, errors=["OUTPUT_MISSING"])

    if output_path.stat().st_size < 1024 * 1024:  # < 1MB
        return VerifyResult(ok=False, errors=["OUTPUT_TOO_SMALL"])

    # ffprobe analysis
    info = ffprobe_json(output_path)
    if not info:
        return VerifyResult(ok=False, errors=["FFPROBE_FAILED"])

    # Duration
    try:
        result.duration_sec = float(info["format"]["duration"])
    except (KeyError, ValueError):
        result.errors.append("DURATION_UNREADABLE")
        result.ok = False
        return result

    diff = abs(result.duration_sec - expected_duration)
    if diff > DURATION_TOLERANCE_SEC:
        result.errors.append(
            f"DURATION_MISMATCH: got={result.duration_sec:.2f}s "
            f"expected={expected_duration:.2f}s diff={diff:.2f}s"
        )
        result.ok = False

    # Codec verification
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            result.codec_video = stream.get("codec_name", "")
            try:
                fps_parts = stream.get("r_frame_rate", "30/1").split("/")
                result.fps = float(fps_parts[0]) / float(fps_parts[1])
            except (ValueError, ZeroDivisionError, IndexError):
                pass
        elif stream.get("codec_type") == "audio":
            result.codec_audio = stream.get("codec_name", "")

    if not result.codec_video:
        result.errors.append("NO_VIDEO_STREAM")
        result.ok = False
    if not result.codec_audio:
        result.errors.append("NO_AUDIO_STREAM")
        result.ok = False

    # Loudness analysis
    loudness = measure_loudness(output_path)
    if loudness:
        result.lufs_integrated = loudness["input_i"]
        result.true_peak = loudness["input_tp"]

        if abs(result.lufs_integrated - LUFS_TARGET) > LUFS_TOLERANCE:
            result.warnings.append(
                f"LOUDNESS_OFF: {result.lufs_integrated:.1f} LUFS "
                f"(target={LUFS_TARGET})"
            )
        if result.true_peak > TRUE_PEAK_MAX:
            result.warnings.append(
                f"TRUE_PEAK_HIGH: {result.true_peak:.1f} dBTP "
                f"(max={TRUE_PEAK_MAX})"
            )

    return result


# ---------------------------------------------------------------------------
# Shadow render (FFmpeg fallback)
# ---------------------------------------------------------------------------


def run_shadow_render(run_dir: Path, debug: bool = False) -> Dict[str, Any]:
    """Run FFmpeg shadow render as fallback. Returns receipt-like dict."""
    try:
        from rayvault.ffmpeg_render import render as ffmpeg_render
        result = ffmpeg_render(
            run_dir, apply=True, debug=debug,
        )
        # Move output to shadow path
        final = run_dir / "publish" / "video_final.mp4"
        shadow = run_dir / "publish" / "video_shadow.mp4"
        if final.exists():
            os.replace(final, shadow)
        return {
            "ok": result.ok,
            "engine": "shadow_ffmpeg",
            "output_path": str(shadow) if shadow.exists() else None,
            "output_sha1": sha1_file(shadow) if shadow.exists() else None,
            "status": result.status,
            "errors": result.errors,
        }
    except Exception as e:
        return {
            "ok": False,
            "engine": "shadow_ffmpeg",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Render watchdog
# ---------------------------------------------------------------------------


def watch_render(
    bridge,
    output_path: Path,
    stall_timeout: int = STALL_TIMEOUT_SEC,
    max_timeout: int = RENDER_TIMEOUT_SEC,
    poll_interval: int = RENDER_POLL_SEC,
) -> Dict[str, Any]:
    """Monitor render progress with stall detection.

    Returns {ok, stalled, elapsed_sec, completion}.
    """
    t_start = time.monotonic()
    last_size = 0
    last_growth_time = t_start
    stalled = False

    while True:
        elapsed = time.monotonic() - t_start
        if elapsed > max_timeout:
            return {"ok": False, "stalled": False, "reason": "TIMEOUT",
                    "elapsed_sec": round(elapsed, 1)}

        # Check if still rendering
        if not bridge.is_rendering():
            # Render finished
            status = bridge.get_render_status()
            completion = status.get("completion", 0) if status else 0
            return {"ok": True, "stalled": False,
                    "elapsed_sec": round(elapsed, 1),
                    "completion": completion}

        # Check output file growth
        try:
            if output_path.exists():
                current_size = output_path.stat().st_size
                if current_size > last_size:
                    last_size = current_size
                    last_growth_time = time.monotonic()
        except OSError:
            pass

        # Stall detection
        since_growth = time.monotonic() - last_growth_time
        if since_growth > stall_timeout:
            stalled = True
            return {"ok": False, "stalled": True, "reason": "STALL",
                    "stall_seconds": round(since_growth, 1),
                    "elapsed_sec": round(elapsed, 1)}

        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Core assembler
# ---------------------------------------------------------------------------


@dataclass
class AssembleResult:
    ok: bool
    status: str = "UNKNOWN"
    engine_used: str = ""
    inputs_hash: str = ""
    output_path: Optional[str] = None
    output_sha1: Optional[str] = None
    output_bytes: int = 0
    duration_sec: float = 0.0
    elapsed_sec: float = 0.0
    resolve_caps: Optional[Dict[str, Any]] = None
    verify: Optional[Dict[str, Any]] = None
    shadow: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def assemble(
    run_dir: Path,
    apply: bool = False,
    debug: bool = False,
    shadow_on_fail: bool = True,
    template_name: str = TEMPLATE_PROJECT_NAME,
) -> AssembleResult:
    """Orchestrate the full DaVinci render pipeline."""
    run_dir = run_dir.resolve()
    t_start = time.monotonic()

    # --- Gate A: essential files ---
    fg = gate_essential_files(run_dir)
    if not fg.ok:
        return AssembleResult(ok=False, status="BLOCKED", errors=fg.errors)

    manifest = read_json(run_dir / "00_manifest.json")
    render_config = read_json(run_dir / "05_render_config.json")
    overlays_index = read_json(run_dir / "publish" / "overlays" / "overlays_index.json")
    audio_path = run_dir / "02_audio.wav"

    audio_duration = wav_duration_seconds(audio_path)
    if audio_duration is None:
        return AssembleResult(ok=False, status="BLOCKED",
                              errors=["UNREADABLE_AUDIO"])

    output_settings = render_config.get(
        "output",
        render_config.get("canvas", {"w": 1920, "h": 1080, "fps": 30}),
    )

    # Inputs hash
    inputs_hash = compute_inputs_hash(run_dir)

    # Check idempotency
    receipt_path = run_dir / "publish" / "render_receipt.json"
    final_path = run_dir / "publish" / "video_final.mp4"
    if receipt_path.exists() and final_path.exists():
        try:
            existing = read_json(receipt_path)
            if (existing.get("inputs_hash") == inputs_hash
                    and existing.get("engine_used") == "davinci"):
                elapsed = time.monotonic() - t_start
                return AssembleResult(
                    ok=True, status="RENDERED_CACHED",
                    engine_used="davinci", inputs_hash=inputs_hash,
                    output_path=str(final_path),
                    output_sha1=existing.get("output_sha1"),
                    elapsed_sec=round(elapsed, 2),
                )
        except Exception:
            pass

    # Dry-run: just validate
    if not apply:
        elapsed = time.monotonic() - t_start
        segments = render_config.get("segments", [])
        return AssembleResult(
            ok=True, status="DRY_RUN",
            engine_used="davinci", inputs_hash=inputs_hash,
            duration_sec=audio_duration,
            elapsed_sec=round(elapsed, 2),
            warnings=fg.warnings,
        )

    # --- Gate B: Resolve connection ---
    rg, bridge = gate_resolve_connection()
    if not rg.ok or not bridge:
        errors = rg.errors + ["Falling back to shadow render" if shadow_on_fail else ""]
        if shadow_on_fail:
            shadow = run_shadow_render(run_dir, debug=debug)
            elapsed = time.monotonic() - t_start
            return AssembleResult(
                ok=False, status="SHADOW_RENDERED",
                engine_used="shadow_ffmpeg", inputs_hash=inputs_hash,
                shadow=shadow, elapsed_sec=round(elapsed, 2),
                errors=rg.errors,
                warnings=["DaVinci unavailable — shadow render created"],
            )
        return AssembleResult(ok=False, status="BLOCKED",
                              errors=rg.errors)

    # --- Build project ---
    run_id = manifest.get("run_id", run_dir.name)
    project_name = f"RAY_{run_id}"
    if not bridge.create_project(project_name, output_settings):
        bridge.disconnect()
        return AssembleResult(ok=False, status="FAILED",
                              errors=[f"PROJECT_CREATE_FAIL: {project_name}"],
                              resolve_caps=bridge.caps.to_dict())

    # --- Create bins ---
    bins = bridge.create_bins()

    # --- Import media ---
    segments = render_config.get("segments", [])

    # Collect all media paths
    audio_imports = [str(audio_path)]
    video_imports = []
    overlay_imports = []

    frame_path = run_dir / render_config.get("ray", {}).get("frame_path", "03_frame.png")
    if frame_path.exists():
        video_imports.append(str(frame_path))

    for seg in segments:
        visual = seg.get("visual", {})
        source = visual.get("source")
        if source:
            sp = Path(source)
            if not sp.is_absolute():
                sp = run_dir / source
            if sp.exists():
                video_imports.append(str(sp))

    # Overlay PNGs
    for item in overlays_index.get("items", []):
        if item.get("display_mode") == "HIDE":
            continue
        for key in ("lowerthird_path", "qr_path"):
            rel = item.get(key)
            if rel and (run_dir / rel).exists():
                overlay_imports.append(str(run_dir / rel))

    # Import to bins
    bridge.import_media(audio_imports, bins.get("Audio"))
    bridge.import_media(video_imports, bins.get("Products"))
    bridge.import_media(overlay_imports, bins.get("Overlays"))

    clip_index = bridge.build_clip_index()

    # --- Create timeline ---
    timeline_name = f"Timeline_{run_id}"
    if not bridge.create_timeline(timeline_name):
        bridge.save_project()
        bridge.disconnect()
        return AssembleResult(ok=False, status="FAILED",
                              errors=["TIMELINE_CREATE_FAIL"],
                              resolve_caps=bridge.caps.to_dict())

    # Add V2 track for overlays
    bridge.add_track("video")  # Adds V2

    # --- Build V1 (main video) ---
    kenburns_notes = []
    for seg in segments:
        seg_type = seg.get("type", "")
        visual = seg.get("visual", {})
        mode = visual.get("mode", "")
        source = visual.get("source")

        if seg_type in ("intro", "outro"):
            # Use frame image
            clip = clip_index.get(frame_path.name)
            if clip:
                bridge.append_clips_to_timeline([clip], track_index=1)
        elif mode == "SKIP" or not source:
            # SKIP: no visual (gap on V1)
            pass
        else:
            # Product visual (BROLL or KEN_BURNS or STILL_ONLY)
            source_name = Path(source).name
            clip = clip_index.get(source_name)
            if clip:
                bridge.append_clips_to_timeline([clip], track_index=1)

                # Ken Burns: attempt Dynamic Zoom
                if mode == "KEN_BURNS":
                    items = bridge.get_timeline_items("video", 1)
                    if items:
                        last_item = items[-1]
                        pattern = None
                        from rayvault.resolve_bridge import kenburns_pattern_for_segment
                        pattern = kenburns_pattern_for_segment(
                            run_id, seg.get("asin", ""), seg.get("rank", 0),
                        )
                        applied = bridge.set_dynamic_zoom(last_item, pattern)
                        kenburns_notes.append({
                            "rank": seg.get("rank"),
                            "pattern": pattern.get("name", "unknown") if pattern else "none",
                            "api_applied": applied,
                        })

    # --- Build A1 (audio) ---
    audio_clip = clip_index.get(audio_path.name)
    if audio_clip:
        bridge.append_clips_to_timeline([audio_clip], track_index=1, media_type=2)

    # --- Build V2 (overlays) ---
    # Overlay PNGs are placed on V2 in segment order.
    # Due to API limitations, overlays are appended sequentially.
    # Manual adjustment may be needed for precise positioning.
    tier = overlays_index.get("episode_truth_tier", "GREEN")
    overlays_placed = 0
    overlays_suppressed = 0

    for item in overlays_index.get("items", []):
        if item.get("display_mode") == "HIDE":
            overlays_suppressed += 1
            continue

        lt_path = item.get("lowerthird_path")
        if lt_path:
            lt_name = Path(lt_path).name
            lt_clip = clip_index.get(lt_name)
            if lt_clip:
                bridge.append_clips_to_timeline([lt_clip], track_index=2)
                overlays_placed += 1

    # --- Save project ---
    bridge.save_project()

    # --- Configure Deliver ---
    final_output = run_dir / "publish" / "video_final.mp4"
    render_set = bridge.set_render_settings(
        str(final_output), output_settings=output_settings,
    )

    if not render_set:
        # Render settings failed via API — mark for manual/OpenClaw deliver
        bridge.save_project()
        bridge.disconnect()
        elapsed = time.monotonic() - t_start
        return AssembleResult(
            ok=False, status="NEEDS_MANUAL_DELIVER",
            engine_used="davinci", inputs_hash=inputs_hash,
            elapsed_sec=round(elapsed, 2),
            resolve_caps=bridge.caps.to_dict(),
            warnings=[
                "Resolve API could not set render settings. "
                "Use DaVinci UI or OpenClaw to configure Deliver and render.",
                f"Project: {project_name} / Timeline: {timeline_name}",
            ],
        )

    # --- Add to render queue + start render ---
    job_id = bridge.add_render_job()
    if not job_id:
        bridge.save_project()
        bridge.disconnect()
        return AssembleResult(
            ok=False, status="RENDER_QUEUE_FAIL",
            engine_used="davinci", inputs_hash=inputs_hash,
            resolve_caps=bridge.caps.to_dict(),
            errors=["Failed to add render job to queue"],
        )

    if not bridge.start_rendering():
        bridge.save_project()
        bridge.disconnect()
        return AssembleResult(
            ok=False, status="RENDER_START_FAIL",
            engine_used="davinci", inputs_hash=inputs_hash,
            resolve_caps=bridge.caps.to_dict(),
            errors=["Failed to start rendering"],
        )

    # --- Watchdog ---
    watch = watch_render(bridge, final_output)

    bridge.save_project()
    bridge.disconnect()

    if not watch["ok"]:
        elapsed = time.monotonic() - t_start

        # Stall or timeout — try shadow render
        shadow = None
        if shadow_on_fail:
            shadow = run_shadow_render(run_dir, debug=debug)

        return AssembleResult(
            ok=False,
            status="STALL" if watch.get("stalled") else "RENDER_TIMEOUT",
            engine_used="davinci", inputs_hash=inputs_hash,
            elapsed_sec=round(elapsed, 2),
            resolve_caps=bridge.caps.to_dict(),
            shadow=shadow,
            errors=[f"RENDER_{watch.get('reason', 'FAIL')}"],
            warnings=["Shadow render created" if shadow and shadow.get("ok") else ""],
        )

    # --- Post-render verification ---
    verify = verify_output(final_output, audio_duration, output_settings.get("fps", 30))

    elapsed = time.monotonic() - t_start
    output_sha1 = sha1_file(final_output) if final_output.exists() else None
    output_bytes = final_output.stat().st_size if final_output.exists() else 0

    # --- Write render receipt ---
    receipt = {
        "engine_used": "davinci",
        "run_id": run_id,
        "inputs_hash": inputs_hash,
        "at_utc": utc_now_iso(),
        "output_path": "publish/video_final.mp4",
        "output_sha1": output_sha1,
        "output_bytes": output_bytes,
        "resolve_caps": bridge.caps.to_dict(),
        "resolve_version": bridge.caps.resolve_version,
        "project_name": project_name,
        "timeline_name": timeline_name,
        "template_name": template_name,
        "kenburns_notes": kenburns_notes,
        "overlays_placed": overlays_placed,
        "overlays_suppressed": overlays_suppressed,
        "episode_truth_tier": tier,
        "watchdog": {
            "stalled": watch.get("stalled", False),
            "elapsed_sec": watch.get("elapsed_sec", 0),
        },
        "metrics_post_render": {
            "duration_sec": round(verify.duration_sec, 3),
            "codec_video": verify.codec_video,
            "codec_audio": verify.codec_audio,
            "fps": verify.fps,
            "lufs_integrated": verify.lufs_integrated,
            "true_peak": verify.true_peak,
        },
        "verify_ok": verify.ok,
        "verify_errors": verify.errors,
        "verify_warnings": verify.warnings,
        "elapsed_sec": round(elapsed, 2),
    }
    atomic_write_json(run_dir / "publish" / "render_receipt.json", receipt)

    # --- Update manifest ---
    manifest_path = run_dir / "00_manifest.json"
    if manifest_path.exists():
        m = read_json(manifest_path)
        r = m.setdefault("render", {})
        r["status"] = "RENDERED" if verify.ok else "RENDER_VERIFY_FAIL"
        r["engine_used"] = "davinci"
        r["inputs_hash"] = inputs_hash
        r["output_path"] = "publish/video_final.mp4"
        r["output_sha1"] = output_sha1
        r["output_bytes"] = output_bytes
        r["duration_sec"] = round(verify.duration_sec, 3)
        r["rendered_at_utc"] = utc_now_iso()
        r["resolve_version"] = bridge.caps.resolve_version
        atomic_write_json(manifest_path, m)

    status = "RENDERED" if verify.ok else "RENDER_VERIFY_FAIL"

    return AssembleResult(
        ok=verify.ok,
        status=status,
        engine_used="davinci",
        inputs_hash=inputs_hash,
        output_path=str(final_output) if final_output.exists() else None,
        output_sha1=output_sha1,
        output_bytes=output_bytes,
        duration_sec=verify.duration_sec,
        elapsed_sec=round(elapsed, 2),
        resolve_caps=bridge.caps.to_dict(),
        verify={
            "ok": verify.ok,
            "duration_sec": verify.duration_sec,
            "codec_video": verify.codec_video,
            "codec_audio": verify.codec_audio,
            "lufs_integrated": verify.lufs_integrated,
            "true_peak": verify.true_peak,
            "errors": verify.errors,
            "warnings": verify.warnings,
        },
        errors=verify.errors,
        warnings=verify.warnings,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault DaVinci Assembler — production render via Resolve Studio",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument(
        "--apply", action="store_true",
        help="Execute render (default: dry-run validation)",
    )
    ap.add_argument("--debug", action="store_true", help="Save debug artifacts")
    ap.add_argument(
        "--no-shadow", action="store_true",
        help="Disable FFmpeg shadow render on DaVinci failure",
    )
    ap.add_argument(
        "--template", default=TEMPLATE_PROJECT_NAME,
        help=f"Template project name (default: {TEMPLATE_PROJECT_NAME})",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    result = assemble(
        run_dir,
        apply=args.apply,
        debug=args.debug,
        shadow_on_fail=not args.no_shadow,
        template_name=args.template,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"

    if result.ok:
        print(f"davinci_assembler [{mode}]: {result.status}")
        print(f"  Engine: {result.engine_used}")
        if result.duration_sec:
            print(f"  Duration: {result.duration_sec:.1f}s")
        if result.output_path:
            print(f"  Output: {result.output_path}")
        if result.output_sha1:
            print(f"  SHA1: {result.output_sha1}")
        if result.output_bytes:
            print(f"  Size: {result.output_bytes / (1024*1024):.1f} MB")
        if result.verify:
            v = result.verify
            if v.get("lufs_integrated") is not None:
                print(f"  Loudness: {v['lufs_integrated']:.1f} LUFS")
            if v.get("true_peak") is not None:
                print(f"  True Peak: {v['true_peak']:.1f} dBTP")
        if result.elapsed_sec:
            m, s = divmod(int(result.elapsed_sec), 60)
            print(f"  Time: {m:02d}:{s:02d}")
    else:
        print(f"davinci_assembler [{mode}]: {result.status}", file=sys.stderr)
        for err in result.errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        if result.shadow and result.shadow.get("ok"):
            print(f"  Shadow render: {result.shadow.get('output_path')}")

    for w in result.warnings:
        if w:
            print(f"  WARN: {w}")

    if result.status == "NEEDS_MANUAL_DELIVER":
        return 3
    return 0 if result.ok else (2 if result.status == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
