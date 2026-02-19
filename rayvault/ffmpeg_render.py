#!/usr/bin/env python3
"""RayVault FFmpeg Render — segmented video assembler with per-segment caching.

Reads 05_render_config.json + overlays_index.json and produces
publish/video_final.mp4 via deterministic segment-by-segment rendering.

Strategy:
  1. Validate all inputs (gates)
  2. Render each segment to publish/render_cache/seg_XXX.mp4 (cached by inputs_hash)
  3. Concat segments via FFmpeg demuxer
  4. Apply audio track with optional loudnorm
  5. Write receipts (per-segment + global)

Golden rules:
  1. NEVER decide visual content. Follow render_config.json visual.mode exactly.
  2. Fail fast: validate everything before touching FFmpeg.
  3. Idempotent: same inputs_hash = skip render.
  4. Overlays come from overlays_index.json coords — no hardcoded positions.

Usage:
    python3 -m rayvault.ffmpeg_render --run-dir state/runs/RUN_2026_02_14_A --apply
    python3 -m rayvault.ffmpeg_render --run-dir state/runs/RUN_2026_02_14_A --apply --debug
    python3 -m rayvault.ffmpeg_render --run-dir state/runs/RUN_2026_02_14_A --apply --force-all

Exit codes:
    0: success (or dry-run validation passed)
    1: runtime error (FFmpeg failure)
    2: gate failure (missing inputs, temporal drift, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from rayvault.io import (
    atomic_write_json, read_json, sha1_file, sha1_text, utc_now_iso,
    wav_duration_seconds,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KENBURNS_ZOOM_FACTOR = 1.08  # 8% zoom-in
KENBURNS_UPSCALE_W = 4000  # scale source to this before zoompan
DURATION_TOLERANCE_SEC = 0.1
FRAME_TOLERANCE = 2  # allow +-2 frames for rounding
MIN_STABILITY_SCORE = 0  # disabled by default; set to 50 to gate on stability


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def ffprobe_duration(path: Path) -> Optional[float]:
    """Probe media duration via ffprobe."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def ffmpeg_version() -> str:
    """Get ffmpeg version string."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10,
        )
        line = proc.stdout.split("\n")[0] if proc.stdout else "unknown"
        return line.strip()
    except Exception:
        return "unknown"


def file_stat_sig(path: Path) -> str:
    """Quick file signature: size + mtime (for hash computation without full SHA1)."""
    try:
        st = path.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"
    except Exception:
        return "missing"


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

_FFMPEG_ERROR_PATTERNS = [
    ("No such file or directory", "MISSING_INPUT"),
    ("Invalid data found when processing input", "CORRUPT_MEDIA"),
    ("Cannot allocate memory", "OOM"),
    ("Unknown encoder", "FFMPEG_BUILD_MISSING"),
    ("Avi: avisynth", "CORRUPT_MEDIA"),
    ("Error opening input", "MISSING_INPUT"),
    ("does not contain any stream", "CORRUPT_MEDIA"),
    ("Permission denied", "PERMISSION_DENIED"),
    ("Discarding ID3 tags", ""),  # benign warning, skip
]


def classify_ffmpeg_error(stderr: str) -> str:
    """Classify FFmpeg stderr into an error code."""
    for pattern, code in _FFMPEG_ERROR_PATTERNS:
        if pattern in stderr and code:
            return code
    return "FFMPEG_UNKNOWN"


# ---------------------------------------------------------------------------
# Gates (fail-fast validation)
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def gate_essential_files(run_dir: Path) -> GateResult:
    """Gate A: verify essential files exist."""
    errors = []
    manifest = run_dir / "00_manifest.json"
    render_config = run_dir / "05_render_config.json"
    audio = run_dir / "02_audio.wav"
    overlays_index = run_dir / "publish" / "overlays" / "overlays_index.json"

    if not manifest.exists():
        errors.append("MISSING: 00_manifest.json")
    if not render_config.exists():
        errors.append("MISSING: 05_render_config.json")
    if not audio.exists():
        errors.append("MISSING: 02_audio.wav")
    if not overlays_index.exists():
        errors.append("MISSING: publish/overlays/overlays_index.json (run overlay builder first)")

    return GateResult(ok=len(errors) == 0, errors=errors)


def gate_temporal_consistency(
    render_config: Dict[str, Any],
    audio_duration: float,
) -> GateResult:
    """Gate B: timeline duration must match audio duration."""
    segments = render_config.get("segments", [])
    if not segments:
        return GateResult(ok=False, errors=["no segments in render_config"])

    timeline_duration = segments[-1].get("t1", 0.0)
    diff = timeline_duration - audio_duration

    errors = []
    warnings = []

    if diff > DURATION_TOLERANCE_SEC:
        # Timeline longer than audio — would cut speech
        errors.append(
            f"TIMELINE_EXCEEDS_AUDIO: timeline={timeline_duration:.3f}s "
            f"audio={audio_duration:.3f}s diff={diff:+.3f}s"
        )
    elif diff < -DURATION_TOLERANCE_SEC:
        # Timeline shorter than audio — silent tail
        warnings.append(
            f"AUDIO_TAIL: audio extends {abs(diff):.3f}s beyond timeline "
            f"(will use -shortest)"
        )

    return GateResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def gate_frames_consistency(render_config: Dict[str, Any]) -> GateResult:
    """Gate C: frames must match round((t1-t0)*fps)."""
    fps = render_config.get("output", render_config.get("canvas", {})).get("fps", 30)
    errors = []
    warnings = []

    for seg in render_config.get("segments", []):
        expected = round((seg["t1"] - seg["t0"]) * fps)
        actual = seg.get("frames")
        if actual is None:
            continue  # backward compat with v1.1 configs
        if abs(expected - actual) > FRAME_TOLERANCE:
            errors.append(
                f"FRAME_MISMATCH: {seg.get('id', '?')} "
                f"expected={expected} actual={actual}"
            )

    return GateResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def gate_segment_sources(
    run_dir: Path,
    render_config: Dict[str, Any],
) -> GateResult:
    """Gate D: verify segment visual sources exist."""
    errors = []
    warnings = []

    frame_path = run_dir / render_config.get("ray", {}).get("frame_path", "03_frame.png")

    for seg in render_config.get("segments", []):
        seg_id = seg.get("id", "?")
        seg_type = seg.get("type", "")

        if seg_type in ("intro", "outro"):
            if not frame_path.exists():
                errors.append(f"MISSING_SOURCE: {seg_id} needs {frame_path.name}")
            continue

        visual = seg.get("visual", {})
        mode = visual.get("mode", "SKIP")
        source = visual.get("source")

        if mode == "SKIP":
            continue

        if not source:
            errors.append(f"MISSING_SOURCE: {seg_id} mode={mode} but no source path")
            continue

        # Source can be absolute (library path) or relative to run_dir
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = run_dir / source

        if not source_path.exists():
            errors.append(f"MISSING_SOURCE: {seg_id} source={source}")

    return GateResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def gate_overlay_refs(
    run_dir: Path,
    overlays_index: Dict[str, Any],
) -> GateResult:
    """Gate D2: verify overlay PNGs referenced in index exist."""
    warnings = []

    for item in overlays_index.get("items", []):
        if item.get("display_mode") == "HIDE":
            continue
        for key in ("lowerthird_path", "qr_path"):
            rel = item.get(key)
            if rel and not (run_dir / rel).exists():
                warnings.append(
                    f"OVERLAY_MISSING: rank={item.get('rank')} "
                    f"{key}={rel} (will render without)"
                )

    return GateResult(ok=True, warnings=warnings)


def validate_run_inputs(
    run_dir: Path,
    render_config: Dict[str, Any],
    overlays_index: Dict[str, Any],
    audio_duration: float,
    manifest: Dict[str, Any],
) -> GateResult:
    """Run all gates. Returns combined result."""
    all_errors: List[str] = []
    all_warnings: List[str] = []

    for gate_fn, args in [
        (gate_temporal_consistency, (render_config, audio_duration)),
        (gate_frames_consistency, (render_config,)),
        (gate_segment_sources, (run_dir, render_config)),
        (gate_overlay_refs, (run_dir, overlays_index)),
    ]:
        r = gate_fn(*args)
        all_errors.extend(r.errors)
        all_warnings.extend(r.warnings)

    # Gate E: stability (optional)
    if MIN_STABILITY_SCORE > 0:
        score = manifest.get("products", {}).get("stability_score_products", 100)
        if score < MIN_STABILITY_SCORE:
            all_errors.append(
                f"LOW_STABILITY: score={score} < {MIN_STABILITY_SCORE}"
            )

    return GateResult(
        ok=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings,
    )


# ---------------------------------------------------------------------------
# Hash computation (idempotency)
# ---------------------------------------------------------------------------


def compute_segment_inputs_hash(
    seg: Dict[str, Any],
    run_dir: Path,
    overlays_index: Dict[str, Any],
    output_settings: Dict[str, Any],
) -> str:
    """Compute deterministic hash for a single segment's inputs."""
    parts = [
        json.dumps(seg, sort_keys=True),
        json.dumps(output_settings, sort_keys=True),
    ]

    # Visual source signature
    visual = seg.get("visual", {})
    source = visual.get("source")
    if source:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = run_dir / source
        parts.append(file_stat_sig(source_path))

    # Overlay PNGs for this segment's rank
    rank = seg.get("rank")
    if rank is not None:
        for item in overlays_index.get("items", []):
            if item.get("rank") == rank:
                for key in ("lowerthird_path", "qr_path"):
                    rel = item.get(key)
                    if rel:
                        p = run_dir / rel
                        parts.append(f"{key}:{file_stat_sig(p)}")
                break

    return sha1_text("|".join(parts))


def compute_global_inputs_hash(
    render_config_path: Path,
    audio_path: Path,
    overlays_index_path: Path,
    segment_hashes: List[str],
) -> str:
    """Compute global inputs hash for idempotency check."""
    parts = [
        sha1_file(render_config_path),
        file_stat_sig(audio_path),
    ]
    if overlays_index_path.exists():
        parts.append(sha1_file(overlays_index_path))
    parts.extend(segment_hashes)
    return sha1_text("|".join(parts))


# ---------------------------------------------------------------------------
# FFmpeg command builders
# ---------------------------------------------------------------------------


def _scale_pad_filter(w: int, h: int) -> str:
    """Scale to fit WxH and pad with black to exact size."""
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )


def _overlay_filters(
    run_dir: Path,
    rank: Optional[int],
    overlays_index: Dict[str, Any],
    input_idx: int,
) -> Tuple[List[str], str, int]:
    """Build overlay filter chain and return (input_args, filter_chain, next_input_idx).

    Returns overlay -i args, filter segments to append, and the next input index.
    """
    if rank is None:
        return [], "", input_idx

    overlay_item = None
    for item in overlays_index.get("items", []):
        if item.get("rank") == rank and item.get("display_mode") != "HIDE":
            overlay_item = item
            break

    if not overlay_item:
        return [], "", input_idx

    input_args: List[str] = []
    filter_parts: List[str] = []
    prev_label = "base"

    # Lower-third
    lt_path = overlay_item.get("lowerthird_path")
    if lt_path and (run_dir / lt_path).exists():
        input_args.extend(["-i", str(run_dir / lt_path)])
        coords = (overlay_item.get("coords") or {}).get("lowerthird") or {}
        x = coords.get("x", 0)
        y = coords.get("y", 0)
        out_label = f"ov{input_idx}"
        filter_parts.append(f"[{prev_label}][{input_idx}:v]overlay={x}:{y}[{out_label}]")
        prev_label = out_label
        input_idx += 1

    # QR
    qr_path = overlay_item.get("qr_path")
    if qr_path and (run_dir / qr_path).exists():
        input_args.extend(["-i", str(run_dir / qr_path)])
        coords = (overlay_item.get("coords") or {}).get("qr") or {}
        x = coords.get("x", 0)
        y = coords.get("y", 0)
        out_label = f"ov{input_idx}"
        filter_parts.append(f"[{prev_label}][{input_idx}:v]overlay={x}:{y}[{out_label}]")
        prev_label = out_label
        input_idx += 1

    filter_chain = ";".join(filter_parts) if filter_parts else ""
    return input_args, filter_chain, input_idx


def build_segment_cmd(
    seg: Dict[str, Any],
    run_dir: Path,
    output_settings: Dict[str, Any],
    overlays_index: Dict[str, Any],
    out_path: Path,
) -> List[str]:
    """Build FFmpeg command for a single segment."""
    w = output_settings["w"]
    h = output_settings["h"]
    fps = output_settings["fps"]
    crf = output_settings.get("crf", 18)
    preset = output_settings.get("preset", "slow")
    pix_fmt = output_settings.get("pix_fmt", "yuv420p")
    vcodec = output_settings.get("vcodec", "libx264")
    duration = round(seg["t1"] - seg["t0"], 3)
    seg_type = seg.get("type", "")
    visual = seg.get("visual", {})
    mode = visual.get("mode", "")
    rank = seg.get("rank")

    # Common encoding args
    encode_args = [
        "-c:v", vcodec, "-crf", str(crf), "-preset", preset,
        "-pix_fmt", pix_fmt, "-an",
    ]

    # --- Intro / Outro: static frame ---
    if seg_type in ("intro", "outro"):
        frame_path = run_dir / "03_frame.png"
        # Build overlay chain
        overlay_inputs, overlay_filter, _ = _overlay_filters(
            run_dir, rank, overlays_index, 1,
        )
        scale_filter = _scale_pad_filter(w, h)
        if overlay_filter:
            fc = f"[0:v]{scale_filter},fps={fps}[base];{overlay_filter}"
            last_label = overlay_filter.rsplit("[", 1)[-1].rstrip("]")
            cmd = (
                ["ffmpeg", "-y", "-loop", "1", "-i", str(frame_path)]
                + overlay_inputs
                + ["-filter_complex", fc, "-map", f"[{last_label}]"]
                + ["-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        else:
            vf = f"{scale_filter},fps={fps}"
            cmd = (
                ["ffmpeg", "-y", "-loop", "1", "-i", str(frame_path)]
                + ["-vf", vf, "-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        return cmd

    # --- Product: SKIP (black frame) ---
    if mode == "SKIP" or not visual.get("source"):
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:s={w}x{h}:d={duration}:r={fps}",
            "-t", str(duration),
        ] + encode_args + [str(out_path)]
        return cmd

    # --- Product: BROLL_VIDEO ---
    source = visual.get("source", "")
    source_path = Path(source)
    if not source_path.is_absolute():
        source_path = run_dir / source

    if mode == "BROLL_VIDEO":
        overlay_inputs, overlay_filter, _ = _overlay_filters(
            run_dir, rank, overlays_index, 1,
        )
        scale_filter = _scale_pad_filter(w, h)
        if overlay_filter:
            fc = f"[0:v]{scale_filter},fps={fps}[base];{overlay_filter}"
            last_label = overlay_filter.rsplit("[", 1)[-1].rstrip("]")
            cmd = (
                ["ffmpeg", "-y", "-stream_loop", "-1",
                 "-i", str(source_path)]
                + overlay_inputs
                + ["-filter_complex", fc, "-map", f"[{last_label}]"]
                + ["-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        else:
            vf = f"{scale_filter},fps={fps}"
            cmd = (
                ["ffmpeg", "-y", "-stream_loop", "-1",
                 "-i", str(source_path)]
                + ["-vf", vf, "-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        return cmd

    # --- Product: KEN_BURNS (zoom-in on still image) ---
    if mode == "KEN_BURNS":
        frames = seg.get("frames") or round(duration * fps)
        kb = visual.get("kenburns", {})
        zoom = kb.get("zoom", KENBURNS_ZOOM_FACTOR)
        zoom_inc = (zoom - 1.0) / max(1, frames)

        # Upscale source, then zoompan for smooth zoom
        zp_filter = (
            f"scale={KENBURNS_UPSCALE_W}:-1,"
            f"zoompan=z='min(zoom+{zoom_inc:.6f},{zoom})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={w}x{h}:fps={fps}"
        )

        overlay_inputs, overlay_filter, _ = _overlay_filters(
            run_dir, rank, overlays_index, 1,
        )
        if overlay_filter:
            fc = f"[0:v]{zp_filter}[base];{overlay_filter}"
            last_label = overlay_filter.rsplit("[", 1)[-1].rstrip("]")
            cmd = (
                ["ffmpeg", "-y", "-loop", "1", "-i", str(source_path)]
                + overlay_inputs
                + ["-filter_complex", fc, "-map", f"[{last_label}]"]
                + ["-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        else:
            cmd = (
                ["ffmpeg", "-y", "-loop", "1", "-i", str(source_path)]
                + ["-vf", zp_filter, "-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        return cmd

    # --- Product: STILL_ONLY (static image, no zoom) ---
    if mode == "STILL_ONLY":
        overlay_inputs, overlay_filter, _ = _overlay_filters(
            run_dir, rank, overlays_index, 1,
        )
        scale_filter = _scale_pad_filter(w, h)
        if overlay_filter:
            fc = f"[0:v]{scale_filter},fps={fps}[base];{overlay_filter}"
            last_label = overlay_filter.rsplit("[", 1)[-1].rstrip("]")
            cmd = (
                ["ffmpeg", "-y", "-loop", "1", "-i", str(source_path)]
                + overlay_inputs
                + ["-filter_complex", fc, "-map", f"[{last_label}]"]
                + ["-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        else:
            vf = f"{scale_filter},fps={fps}"
            cmd = (
                ["ffmpeg", "-y", "-loop", "1", "-i", str(source_path)]
                + ["-vf", vf, "-t", str(duration)]
                + encode_args
                + [str(out_path)]
            )
        return cmd

    # Fallback: unknown mode → black frame
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={w}x{h}:d={duration}:r={fps}",
        "-t", str(duration),
    ] + encode_args + [str(out_path)]
    return cmd


# ---------------------------------------------------------------------------
# Segment rendering
# ---------------------------------------------------------------------------


@dataclass
class SegmentResult:
    seg_id: str
    ok: bool
    cached: bool = False
    inputs_hash: str = ""
    output_path: Optional[str] = None
    output_sha1: Optional[str] = None
    duration_sec: float = 0.0
    error_code: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    cmdline: str = ""


def render_segment(
    seg: Dict[str, Any],
    run_dir: Path,
    output_settings: Dict[str, Any],
    overlays_index: Dict[str, Any],
    cache_dir: Path,
    receipts_dir: Path,
    debug_dir: Optional[Path],
    force: bool = False,
) -> SegmentResult:
    """Render a single segment with caching."""
    seg_id = seg.get("id", f"seg_{seg.get('rank', 0):03d}")
    out_path = cache_dir / f"{seg_id}.mp4"
    receipt_path = receipts_dir / f"{seg_id}.json"

    # Compute inputs hash
    inputs_hash = compute_segment_inputs_hash(
        seg, run_dir, overlays_index, output_settings,
    )

    # Check cache
    if not force and out_path.exists() and receipt_path.exists():
        try:
            receipt = read_json(receipt_path)
            if receipt.get("inputs_hash") == inputs_hash:
                return SegmentResult(
                    seg_id=seg_id, ok=True, cached=True,
                    inputs_hash=inputs_hash,
                    output_path=str(out_path),
                    output_sha1=receipt.get("output_sha1"),
                    duration_sec=receipt.get("duration_sec", 0.0),
                )
        except Exception:
            pass

    # Build command
    cmd = build_segment_cmd(seg, run_dir, output_settings, overlays_index, out_path)
    cmdline = " ".join(cmd)

    # Execute
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return SegmentResult(
            seg_id=seg_id, ok=False, inputs_hash=inputs_hash,
            error_code="TIMEOUT", cmdline=cmdline,
        )
    except Exception as e:
        return SegmentResult(
            seg_id=seg_id, ok=False, inputs_hash=inputs_hash,
            error_code=str(type(e).__name__), cmdline=cmdline,
        )

    if proc.returncode != 0:
        error_code = classify_ffmpeg_error(proc.stderr)

        # Save debug artifacts
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)
            _write_debug(debug_dir, seg_id, proc.stderr, cmdline, seg)

        return SegmentResult(
            seg_id=seg_id, ok=False, inputs_hash=inputs_hash,
            error_code=error_code, cmdline=cmdline,
            warnings=[proc.stderr[-500:] if proc.stderr else ""],
        )

    # Verify output
    if not out_path.exists():
        return SegmentResult(
            seg_id=seg_id, ok=False, inputs_hash=inputs_hash,
            error_code="OUTPUT_MISSING", cmdline=cmdline,
        )

    output_sha1 = sha1_file(out_path)
    duration = ffprobe_duration(out_path) or 0.0

    # Write segment receipt
    seg_receipt = {
        "segment_id": seg_id,
        "inputs_hash": inputs_hash,
        "created_at_utc": utc_now_iso(),
        "ffmpeg_version": ffmpeg_version(),
        "cmdline": cmdline,
        "output_path": str(out_path.relative_to(run_dir)),
        "output_sha1": output_sha1,
        "duration_sec": round(duration, 3),
        "warnings": [],
    }
    receipts_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, seg_receipt)

    return SegmentResult(
        seg_id=seg_id, ok=True, cached=False,
        inputs_hash=inputs_hash,
        output_path=str(out_path),
        output_sha1=output_sha1,
        duration_sec=duration,
        cmdline=cmdline,
    )


def _write_debug(
    debug_dir: Path, seg_id: str, stderr: str, cmdline: str, seg: Dict,
) -> None:
    """Write debug artifacts for a failed segment."""
    try:
        (debug_dir / f"{seg_id}_error_tail.log").write_text(
            stderr[-2000:] if stderr else "", encoding="utf-8",
        )
        (debug_dir / f"{seg_id}_cmd.txt").write_text(
            cmdline, encoding="utf-8",
        )
        atomic_write_json(debug_dir / f"{seg_id}_meta.json", seg)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Assembly (concat + audio)
# ---------------------------------------------------------------------------


def concat_segments(
    seg_paths: List[Path],
    out_path: Path,
    output_settings: Dict[str, Any],
) -> Tuple[bool, str, str]:
    """Concat segment videos via FFmpeg demuxer. Returns (ok, cmdline, error)."""
    concat_list = out_path.parent / "concat_list.txt"
    lines = [f"file '{p}'\n" for p in seg_paths]
    concat_list.write_text("".join(lines), encoding="utf-8")

    # Try stream copy first (fastest)
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ]
    cmdline = " ".join(cmd)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0 and out_path.exists():
            return True, cmdline, ""

        # Stream copy failed — fallback to reencode
        vcodec = output_settings.get("vcodec", "libx264")
        crf = output_settings.get("crf", 18)
        preset = output_settings.get("preset", "slow")
        pix_fmt = output_settings.get("pix_fmt", "yuv420p")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", vcodec, "-crf", str(crf), "-preset", preset,
            "-pix_fmt", pix_fmt, "-an",
            str(out_path),
        ]
        cmdline = " ".join(cmd)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0 and out_path.exists():
            return True, cmdline, "reencode_concat"
        return False, cmdline, proc.stderr[-500:] if proc.stderr else "concat_failed"
    except Exception as e:
        return False, cmdline, str(e)


def apply_audio(
    video_path: Path,
    audio_path: Path,
    out_path: Path,
    audio_config: Dict[str, Any],
) -> Tuple[bool, str, str]:
    """Mux audio onto video. Returns (ok, cmdline, error)."""
    lufs = audio_config.get("normalize_lufs")
    tp = audio_config.get("true_peak")

    if lufs is not None and tp is not None:
        # Single-pass loudnorm
        audio_filter = (
            f"loudnorm=I={lufs}:LRA=7:TP={tp}:print_format=none"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-filter_complex", f"[1:a]{audio_filter}[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]

    cmdline = " ".join(cmd)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0 and out_path.exists():
            return True, cmdline, ""
        return False, cmdline, proc.stderr[-500:] if proc.stderr else "audio_mux_failed"
    except Exception as e:
        return False, cmdline, str(e)


# ---------------------------------------------------------------------------
# Core render orchestrator
# ---------------------------------------------------------------------------


@dataclass
class RenderResult:
    ok: bool
    status: str = "UNKNOWN"
    inputs_hash: str = ""
    segments_rendered: int = 0
    segments_cached: int = 0
    segments_total: int = 0
    overlays_applied: int = 0
    overlays_suppressed: int = 0
    output_path: Optional[str] = None
    output_sha1: Optional[str] = None
    output_bytes: int = 0
    duration_sec: float = 0.0
    elapsed_sec: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    patient_zero: Optional[Dict[str, str]] = None


def render(
    run_dir: Path,
    apply: bool = False,
    debug: bool = False,
    force_all: bool = False,
    force_segments: Optional[Set[str]] = None,
) -> RenderResult:
    """Orchestrate full segmented render pipeline."""
    run_dir = run_dir.resolve()
    t_start = time.monotonic()

    # Load essential files
    files_gate = gate_essential_files(run_dir)
    if not files_gate.ok:
        return RenderResult(
            ok=False, status="BLOCKED",
            errors=files_gate.errors,
        )

    manifest = read_json(run_dir / "00_manifest.json")
    render_config = read_json(run_dir / "05_render_config.json")
    overlays_index = read_json(run_dir / "publish" / "overlays" / "overlays_index.json")
    audio_path = run_dir / "02_audio.wav"

    audio_duration = wav_duration_seconds(audio_path)
    if audio_duration is None:
        return RenderResult(
            ok=False, status="BLOCKED",
            errors=["UNREADABLE_AUDIO: cannot parse 02_audio.wav"],
        )

    # Output settings (v1.3 uses output section, fallback to canvas)
    output_settings = render_config.get(
        "output",
        render_config.get("canvas", {"w": 1920, "h": 1080, "fps": 30}),
    )
    # Ensure encoding defaults
    output_settings.setdefault("vcodec", "libx264")
    output_settings.setdefault("acodec", "aac")
    output_settings.setdefault("crf", 18)
    output_settings.setdefault("preset", "slow")
    output_settings.setdefault("pix_fmt", "yuv420p")

    # Run all gates
    gate = validate_run_inputs(
        run_dir, render_config, overlays_index, audio_duration, manifest,
    )
    if not gate.ok:
        return RenderResult(
            ok=False, status="BLOCKED",
            errors=gate.errors, warnings=gate.warnings,
        )

    segments = render_config.get("segments", [])

    # Compute global inputs hash
    seg_hashes = [
        compute_segment_inputs_hash(seg, run_dir, overlays_index, output_settings)
        for seg in segments
    ]
    global_hash = compute_global_inputs_hash(
        run_dir / "05_render_config.json",
        audio_path,
        run_dir / "publish" / "overlays" / "overlays_index.json",
        seg_hashes,
    )

    # Check global idempotency
    receipt_path = run_dir / "publish" / "render_receipt.json"
    final_path = run_dir / "publish" / "video_final.mp4"
    if (
        not force_all
        and not force_segments
        and receipt_path.exists()
        and final_path.exists()
    ):
        try:
            existing = read_json(receipt_path)
            if existing.get("inputs_hash") == global_hash:
                return RenderResult(
                    ok=True, status="RENDERED_CACHED",
                    inputs_hash=global_hash,
                    segments_total=len(segments),
                    segments_cached=len(segments),
                    output_path=str(final_path),
                    output_sha1=existing.get("output_sha1"),
                    output_bytes=existing.get("output_bytes", 0),
                    duration_sec=existing.get("duration_sec", 0.0),
                    elapsed_sec=0.0,
                    warnings=gate.warnings,
                )
        except Exception:
            pass

    # Dry-run: just report plan
    if not apply:
        # Count overlays
        ov_applied = 0
        ov_suppressed = 0
        tier = overlays_index.get("episode_truth_tier", "GREEN")
        for item in overlays_index.get("items", []):
            if item.get("display_mode") == "HIDE":
                ov_suppressed += 1
            else:
                ov_applied += 1

        elapsed = time.monotonic() - t_start
        return RenderResult(
            ok=True, status="DRY_RUN",
            inputs_hash=global_hash,
            segments_total=len(segments),
            overlays_applied=ov_applied,
            overlays_suppressed=ov_suppressed,
            duration_sec=audio_duration,
            elapsed_sec=round(elapsed, 2),
            warnings=gate.warnings,
        )

    # --- APPLY: render segments ---
    cache_dir = run_dir / "publish" / "render_cache"
    receipts_dir = run_dir / "publish" / "seg_receipts"
    debug_dir = (run_dir / "publish" / "render_debug") if debug else None

    seg_results: List[SegmentResult] = []
    seg_paths: List[Path] = []
    rendered = 0
    cached = 0

    for seg in segments:
        seg_id = seg.get("id", "?")
        force_this = force_all or (
            force_segments is not None and seg_id in force_segments
        )

        sr = render_segment(
            seg, run_dir, output_settings, overlays_index,
            cache_dir, receipts_dir, debug_dir,
            force=force_this,
        )
        seg_results.append(sr)

        if not sr.ok:
            # Fail fast
            elapsed = time.monotonic() - t_start
            return RenderResult(
                ok=False, status="FAILED",
                inputs_hash=global_hash,
                segments_rendered=rendered,
                segments_cached=cached,
                segments_total=len(segments),
                elapsed_sec=round(elapsed, 2),
                errors=[f"SEGMENT_FAIL: {sr.seg_id} code={sr.error_code}"],
                warnings=gate.warnings + sr.warnings,
                patient_zero={"code": sr.error_code or "UNKNOWN", "detail": sr.seg_id},
            )

        seg_paths.append(Path(sr.output_path))
        if sr.cached:
            cached += 1
        else:
            rendered += 1

    # --- Concat segments ---
    video_noaudio = run_dir / "publish" / "video_noaudio.mp4"
    concat_ok, concat_cmd, concat_err = concat_segments(
        seg_paths, video_noaudio, output_settings,
    )
    if not concat_ok:
        elapsed = time.monotonic() - t_start
        return RenderResult(
            ok=False, status="FAILED",
            inputs_hash=global_hash,
            segments_rendered=rendered,
            segments_cached=cached,
            segments_total=len(segments),
            elapsed_sec=round(elapsed, 2),
            errors=[f"CONCAT_FAIL: {concat_err}"],
            warnings=gate.warnings,
            patient_zero={"code": "CONCAT_FAIL", "detail": concat_err[:200]},
        )

    # --- Apply audio ---
    audio_config = render_config.get("audio", {})
    audio_ok, audio_cmd, audio_err = apply_audio(
        video_noaudio, audio_path, final_path, audio_config,
    )

    # Clean up intermediate
    try:
        video_noaudio.unlink(missing_ok=True)
    except OSError:
        pass

    if not audio_ok:
        elapsed = time.monotonic() - t_start
        return RenderResult(
            ok=False, status="FAILED",
            inputs_hash=global_hash,
            segments_rendered=rendered,
            segments_cached=cached,
            segments_total=len(segments),
            elapsed_sec=round(elapsed, 2),
            errors=[f"AUDIO_MUX_FAIL: {audio_err}"],
            warnings=gate.warnings,
            patient_zero={"code": "AUDIO_MUX_FAIL", "detail": audio_err[:200]},
        )

    # --- Compute output stats ---
    output_sha1 = sha1_file(final_path)
    output_bytes = final_path.stat().st_size
    output_duration = ffprobe_duration(final_path) or 0.0

    # Count overlays
    ov_applied = 0
    ov_suppressed = 0
    for item in overlays_index.get("items", []):
        if item.get("display_mode") == "HIDE":
            ov_suppressed += 1
        else:
            ov_applied += 1

    elapsed = time.monotonic() - t_start

    # --- Write global render receipt ---
    render_receipt = {
        "at_utc": utc_now_iso(),
        "ffmpeg_version": ffmpeg_version(),
        "inputs_hash": global_hash,
        "output_sha1": output_sha1,
        "output_bytes": output_bytes,
        "duration_sec": round(output_duration, 3),
        "audio_duration_sec": round(audio_duration, 3),
        "segments_rendered": rendered,
        "segments_cached": cached,
        "segments_total": len(segments),
        "overlays_applied": ov_applied,
        "overlays_suppressed": ov_suppressed,
        "concat_cmd": concat_cmd,
        "audio_cmd": audio_cmd,
        "reencode_concat": "reencode" in concat_err,
        "elapsed_sec": round(elapsed, 2),
        "warnings": gate.warnings,
    }
    atomic_write_json(receipt_path, render_receipt)

    # --- Update manifest ---
    manifest_path = run_dir / "00_manifest.json"
    if manifest_path.exists():
        m = read_json(manifest_path)
        r = m.setdefault("render", {})
        r["status"] = "RENDERED"
        r["inputs_hash"] = global_hash
        r["output_path"] = "publish/video_final.mp4"
        r["output_sha1"] = output_sha1
        r["output_bytes"] = output_bytes
        r["duration_sec"] = round(output_duration, 3)
        r["rendered_at_utc"] = utc_now_iso()
        r["segments_rendered"] = rendered
        r["segments_cached"] = cached
        atomic_write_json(manifest_path, m)

    return RenderResult(
        ok=True, status="RENDERED",
        inputs_hash=global_hash,
        segments_rendered=rendered,
        segments_cached=cached,
        segments_total=len(segments),
        overlays_applied=ov_applied,
        overlays_suppressed=ov_suppressed,
        output_path=str(final_path),
        output_sha1=output_sha1,
        output_bytes=output_bytes,
        duration_sec=output_duration,
        elapsed_sec=round(elapsed, 2),
        warnings=gate.warnings,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault FFmpeg Render — segmented video assembler",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument(
        "--apply", action="store_true",
        help="Render video (default: dry-run validation only)",
    )
    ap.add_argument(
        "--debug", action="store_true",
        help="Save intermediate artifacts on failure",
    )
    ap.add_argument(
        "--force-all", action="store_true",
        help="Re-render all segments (ignore cache)",
    )
    ap.add_argument(
        "--force-seg",
        default="",
        help="Re-render specific segments (comma-separated IDs, e.g. seg_001,seg_003)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    force_segments: Optional[Set[str]] = None
    if args.force_seg:
        force_segments = set(s.strip() for s in args.force_seg.split(",") if s.strip())

    result = render(
        run_dir,
        apply=args.apply,
        debug=args.debug,
        force_all=args.force_all,
        force_segments=force_segments,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"

    if result.ok:
        fps = 30
        w, h, crf = 1920, 1080, 18
        # Try to read from render_config
        try:
            rc = read_json(run_dir / "05_render_config.json")
            out = rc.get("output", rc.get("canvas", {}))
            fps = out.get("fps", 30)
            w = out.get("w", 1920)
            h = out.get("h", 1080)
            crf = out.get("crf", 18)
        except Exception:
            pass

        print(f"ffmpeg_render [{mode}]: {result.status}")
        print(
            f"  Segments: {result.segments_total} "
            f"(rendered={result.segments_rendered} cached={result.segments_cached})"
        )
        print(f"  Duration: {result.duration_sec:.1f}s")
        print(f"  Output: {w}x{h} {fps}fps crf={crf}")
        print(f"  Overlays: applied={result.overlays_applied} suppressed={result.overlays_suppressed}")
        if result.inputs_hash:
            print(f"  Inputs hash: {result.inputs_hash}")
        if result.output_path:
            print(f"  File: {result.output_path}")
            if result.output_sha1:
                print(f"  SHA1: {result.output_sha1}")
            if result.output_bytes:
                mb = result.output_bytes / (1024 * 1024)
                print(f"  Size: {mb:.1f} MB")
        if result.elapsed_sec:
            m, s = divmod(int(result.elapsed_sec), 60)
            print(f"  Time: {m:02d}:{s:02d}")
    else:
        print(f"ffmpeg_render [{mode}]: {result.status}", file=sys.stderr)
        for err in result.errors:
            print(f"  ERROR: {err}", file=sys.stderr)

    for w in result.warnings:
        print(f"  WARN: {w}")

    return 0 if result.ok else (2 if result.status == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
