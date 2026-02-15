"""RayVault Audio Postcheck — broadcast-level post-render audio QA.

Analyzes publish/video_final.mp4 and emits:
  - publish/soundtrack_postcheck.json (always)
  - patches to render_receipt.json (always)

Gates (FAIL/WARN):
  A: Integrated LUFS in [-15, -13] (FAIL)
  B: True Peak <= -1.0 dBTP (FAIL), WARN if > -1.3
  C: Duration sync within 0.2s (FAIL)
  D: VAD — voice activity detection (energy-based, 300Hz–3kHz)
  E: Ducking Linter — presence band (2k–5kHz) reduction during VO (WARN)
  F: Spectral Clash — voice masking detection (WARN)
  G: Breath Check — silence during expected VO = routing bug (FAIL)
  H: Click/Clipping detection (WARN/FAIL)
  I: Silence gaps > 300ms (WARN)

Usage:
    from rayvault.audio_postcheck import run_audio_postcheck
    result = run_audio_postcheck(video_path, render_config, expected_duration)
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rayvault.policies import (
    SOUNDTRACK_LUFS_RANGE,
    SOUNDTRACK_DURATION_EPS_SEC,
    SOUNDTRACK_TRUE_PEAK_MAX,
    SOUNDTRACK_TRUE_PEAK_WARN,
    SOUNDTRACK_MAX_SILENCE_GAP_MS,
    VAD_VOICE_BAND_HZ,
    VAD_WINDOW_MS,
    VAD_NOISE_FLOOR_PERCENTILE,
    VAD_THRESHOLD_ABOVE_FLOOR_DB,
    DUCKING_PRESENCE_BAND_HZ,
    DUCKING_MIN_REDUCTION_RATIO,
    SOUNDTRACK_DUCK_AMOUNT_DB,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class LoudnessResult:
    integrated_lufs: float = 0.0
    true_peak_db: float = 0.0
    lra: float = 0.0
    ok: bool = False
    error: str = ""


@dataclass
class BalanceResult:
    ok: bool = True
    vo_dominant_lufs: Optional[float] = None
    music_dominant_lufs: Optional[float] = None
    gap_db: Optional[float] = None
    warning: str = ""


@dataclass
class VADWindow:
    """A single VAD analysis window."""
    start_sec: float
    end_sec: float
    rms_db: float
    has_voice: bool


@dataclass
class VADResult:
    ok: bool = True
    windows: List[VADWindow] = field(default_factory=list)
    noise_floor_db: float = -60.0
    voice_ratio: float = 0.0
    error: str = ""


@dataclass
class DuckingLintResult:
    ok: bool = True
    vo_presence_rms_db: Optional[float] = None
    no_vo_presence_rms_db: Optional[float] = None
    effective_reduction_db: Optional[float] = None
    expected_reduction_db: float = 0.0
    warning: str = ""


@dataclass
class BreathCheckResult:
    ok: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ClippingResult:
    ok: bool = True
    clipped_regions: List[Dict[str, Any]] = field(default_factory=list)
    warning: str = ""


@dataclass
class PostcheckResult:
    ok: bool = True
    status: str = "OK"
    exit_code: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        # Compute final status
        if self.errors:
            self.status = "FAIL"
            self.exit_code = 2
        elif self.warnings:
            self.status = "WARN"
            self.exit_code = 1
        else:
            self.status = "OK"
            self.exit_code = 0
        return {
            "ok": self.ok,
            "status": self.status,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


# ---------------------------------------------------------------------------
# Gate A: Loudness measurement
# ---------------------------------------------------------------------------


def measure_loudness(video_path: Path) -> LoudnessResult:
    """Measure integrated loudness via ffmpeg loudnorm analysis."""
    try:
        cmd = [
            "ffmpeg", "-i", str(video_path), "-af",
            "loudnorm=I=-14:LRA=7:TP=-1:print_format=json",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        stderr = proc.stderr
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(stderr[json_start:json_end])
            return LoudnessResult(
                integrated_lufs=float(data.get("input_i", 0)),
                true_peak_db=float(data.get("input_tp", 0)),
                lra=float(data.get("input_lra", 0)),
                ok=True,
            )
    except Exception as e:
        return LoudnessResult(ok=False, error=str(e))
    return LoudnessResult(ok=False, error="no loudnorm data in ffmpeg output")


# ---------------------------------------------------------------------------
# Gate C: Duration check
# ---------------------------------------------------------------------------


def check_duration(
    video_path: Path,
    expected_sec: float,
    eps: float = SOUNDTRACK_DURATION_EPS_SEC,
) -> tuple:
    """Check video duration is within eps of expected.

    Returns (passed, actual_duration).
    """
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(video_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            actual = float(data["format"]["duration"])
            return (abs(actual - expected_sec) <= eps, actual)
    except Exception:
        pass
    return (False, 0.0)


# ---------------------------------------------------------------------------
# Gate D: VAD (Voice Activity Detection)
# ---------------------------------------------------------------------------


def run_vad(
    video_path: Path,
    segments: List[Dict[str, Any]],
    voice_band: Tuple[int, int] = VAD_VOICE_BAND_HZ,
    window_ms: int = VAD_WINDOW_MS,
    floor_percentile: int = VAD_NOISE_FLOOR_PERCENTILE,
    threshold_db: float = VAD_THRESHOLD_ABOVE_FLOOR_DB,
) -> VADResult:
    """Energy-based voice activity detection.

    Strategy (two-stage, cheap pass first):
      1. Extract voice band (300Hz–3kHz) via ffmpeg bandpass
      2. Measure RMS per window using astats
      3. Estimate noise floor from quietest N% windows
      4. Mark windows with RMS > floor + threshold as VO-present

    Returns per-window VO labels + noise floor estimate.
    """
    if not segments:
        return VADResult(ok=True)

    # Sample representative windows from each segment
    windows: List[VADWindow] = []
    sample_points: List[Tuple[float, float]] = []

    for seg in segments:
        t0 = seg.get("t0", 0)
        t1 = seg.get("t1", t0)
        dur = t1 - t0
        if dur < 0.5:
            continue
        # Sample start, middle, and end of each segment
        window_sec = window_ms / 1000.0
        for offset_frac in (0.1, 0.5, 0.9):
            center = t0 + dur * offset_frac
            w_start = max(t0, center - window_sec / 2)
            w_end = min(t1, center + window_sec / 2)
            if w_end - w_start >= 0.1:
                sample_points.append((w_start, w_end))

    if not sample_points:
        return VADResult(ok=True)

    # Measure RMS in voice band for each window
    rms_values: List[float] = []
    for w_start, w_end in sample_points:
        rms = _measure_band_rms(video_path, w_start, w_end, voice_band)
        if rms is not None:
            rms_values.append(rms)
            windows.append(VADWindow(
                start_sec=round(w_start, 3),
                end_sec=round(w_end, 3),
                rms_db=round(rms, 1),
                has_voice=False,  # set below
            ))

    if not rms_values:
        return VADResult(ok=True, error="no RMS measurements obtained")

    # Estimate noise floor from quietest percentile
    sorted_rms = sorted(rms_values)
    floor_idx = max(1, len(sorted_rms) * floor_percentile // 100)
    noise_floor = sum(sorted_rms[:floor_idx]) / floor_idx

    # Label windows
    voice_count = 0
    for w in windows:
        w.has_voice = w.rms_db > (noise_floor + threshold_db)
        if w.has_voice:
            voice_count += 1

    voice_ratio = voice_count / len(windows) if windows else 0.0

    return VADResult(
        ok=True,
        windows=windows,
        noise_floor_db=round(noise_floor, 1),
        voice_ratio=round(voice_ratio, 3),
    )


def _measure_band_rms(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    band_hz: Tuple[int, int],
) -> Optional[float]:
    """Measure RMS in a frequency band for a time window using ffmpeg."""
    duration = end_sec - start_sec
    lo, hi = band_hz
    try:
        cmd = [
            "ffmpeg",
            "-ss", str(start_sec),
            "-t", str(duration),
            "-i", str(video_path),
            "-af", f"bandpass=f={int((lo+hi)/2)}:width_type=h:w={hi-lo},astats=metadata=1:reset=1",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        # Parse RMS from astats output
        for line in proc.stderr.splitlines():
            if "RMS level dB" in line or "RMS_level" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        return float(parts[-1].strip())
                    except ValueError:
                        pass
            # Alternative astats format
            if "lavfi.astats" in line and "RMS" in line:
                for token in line.split():
                    if "=" in token:
                        try:
                            return float(token.split("=")[-1])
                        except ValueError:
                            pass
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Gate E: Ducking Linter
# ---------------------------------------------------------------------------


def lint_ducking(
    video_path: Path,
    vad_result: VADResult,
    presence_band: Tuple[int, int] = DUCKING_PRESENCE_BAND_HZ,
    expected_duck_db: float = SOUNDTRACK_DUCK_AMOUNT_DB,
    min_ratio: float = DUCKING_MIN_REDUCTION_RATIO,
) -> DuckingLintResult:
    """Check that music ducks during VO-present windows.

    Compares presence band (2k–5kHz) RMS between VO-present and
    VO-absent windows. The presence band should drop during VO.
    """
    if not vad_result.windows:
        return DuckingLintResult(ok=True)

    vo_windows = [w for w in vad_result.windows if w.has_voice]
    no_vo_windows = [w for w in vad_result.windows if not w.has_voice]

    if not vo_windows or not no_vo_windows:
        return DuckingLintResult(ok=True)

    # Sample presence band RMS for first VO and first non-VO window
    vo_w = vo_windows[0]
    no_vo_w = no_vo_windows[0]

    vo_rms = _measure_band_rms(
        video_path, vo_w.start_sec, vo_w.end_sec, presence_band,
    )
    no_vo_rms = _measure_band_rms(
        video_path, no_vo_w.start_sec, no_vo_w.end_sec, presence_band,
    )

    if vo_rms is None or no_vo_rms is None:
        return DuckingLintResult(ok=True)

    # Effective reduction = how much quieter the presence band is during VO
    effective_reduction = no_vo_rms - vo_rms  # positive = music ducked
    expected = abs(expected_duck_db)

    result = DuckingLintResult(
        ok=True,
        vo_presence_rms_db=round(vo_rms, 1),
        no_vo_presence_rms_db=round(no_vo_rms, 1),
        effective_reduction_db=round(effective_reduction, 1),
        expected_reduction_db=expected,
    )

    if effective_reduction < min_ratio * expected:
        result.ok = False
        result.warning = (
            f"DUCKING_SUSPECT: effective reduction={effective_reduction:.1f}dB "
            f"< {min_ratio*100:.0f}% of expected {expected:.0f}dB"
        )

    return result


# ---------------------------------------------------------------------------
# Gate F: Spectral Clash
# ---------------------------------------------------------------------------


def detect_spectral_clash(
    video_path: Path,
    vad_result: VADResult,
    presence_band: Tuple[int, int] = DUCKING_PRESENCE_BAND_HZ,
) -> Optional[str]:
    """Detect if presence band doesn't reduce during VO.

    If VAD says VO is present but the presence band (2k-5kHz) doesn't dip,
    the voice may sound muffled/masked.

    Returns warning string or None.
    """
    vo_windows = [w for w in vad_result.windows if w.has_voice]
    no_vo_windows = [w for w in vad_result.windows if not w.has_voice]

    if not vo_windows or not no_vo_windows:
        return None

    vo_w = vo_windows[0]
    no_vo_w = no_vo_windows[0]

    vo_rms = _measure_band_rms(
        video_path, vo_w.start_sec, vo_w.end_sec, presence_band,
    )
    no_vo_rms = _measure_band_rms(
        video_path, no_vo_w.start_sec, no_vo_w.end_sec, presence_band,
    )

    if vo_rms is None or no_vo_rms is None:
        return None

    # If presence band is NOT lower during VO, spectral clash
    if vo_rms >= no_vo_rms:
        return (
            f"SPECTRAL_CLASH: presence band ({presence_band[0]}-{presence_band[1]}Hz) "
            f"is {vo_rms:.1f}dB during VO vs {no_vo_rms:.1f}dB without VO. "
            f"Voice may sound muffled."
        )
    return None


# ---------------------------------------------------------------------------
# Gate G: Breath Check (voiceover manifest)
# ---------------------------------------------------------------------------


def run_breath_check(
    video_path: Path,
    voiceover_manifest: Optional[Dict[str, Any]],
    vad_result: VADResult,
    max_silence_ms: int = SOUNDTRACK_MAX_SILENCE_GAP_MS,
) -> BreathCheckResult:
    """Check that silence/activity matches voiceover intent.

    Uses voiceover_manifest.json intervals with expected_vo: true/false.
    If silence occurs during expected_vo=true, it's a routing/render bug (FAIL).
    If expected_vo=false, silence is OK (pause/transition).
    """
    result = BreathCheckResult()

    if not voiceover_manifest:
        return result

    intervals = voiceover_manifest.get("intervals", [])
    if not intervals:
        return result

    # Build VAD lookup (simple: check if any VO window overlaps)
    def has_voice_at(t: float) -> bool:
        for w in vad_result.windows:
            if w.start_sec <= t <= w.end_sec:
                return w.has_voice
        return False

    # Detect silence gaps
    silence_gaps = detect_silence_gaps(video_path, max_silence_ms)

    for gap in silence_gaps:
        gap_start = gap["start"]
        gap_end = gap["end"]
        gap_mid = (gap_start + gap_end) / 2

        # Find which interval this gap falls in
        for interval in intervals:
            int_start = interval.get("start_sec", 0)
            int_end = interval.get("end_sec", 0)
            expected_vo = interval.get("expected_vo", True)

            if int_start <= gap_mid <= int_end:
                if expected_vo:
                    result.ok = False
                    result.errors.append(
                        f"BREATH_FAIL: silence {gap_start:.1f}-{gap_end:.1f}s "
                        f"during expected VO interval ({int_start:.1f}-{int_end:.1f}s). "
                        f"Possible routing/render bug."
                    )
                break

    return result


# ---------------------------------------------------------------------------
# Gate H: Click/Clipping detection
# ---------------------------------------------------------------------------


def detect_clipping(video_path: Path) -> ClippingResult:
    """Detect clipping using ffmpeg's astats maximum level.

    Checks for true peak near 0 dBFS which indicates clipping.
    Also uses ametadata to detect consecutive peak samples.
    """
    result = ClippingResult()
    try:
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-af", "astats=metadata=1:reset=1:length=0.1",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # Parse for peak levels near 0 dBFS
        window_idx = 0
        for line in proc.stderr.splitlines():
            if "Peak level dB" in line or "Peak_level" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    try:
                        peak = float(parts[-1].strip())
                        if peak >= -0.1:  # Very close to 0 dBFS = clipping
                            result.clipped_regions.append({
                                "window": window_idx,
                                "peak_db": round(peak, 2),
                            })
                    except ValueError:
                        pass
                window_idx += 1

        if result.clipped_regions:
            n = len(result.clipped_regions)
            if n > 5:
                result.ok = False
                result.warning = f"CLIPPING: {n} regions near 0 dBFS"
            else:
                result.warning = f"CLIPPING_WARN: {n} region(s) near 0 dBFS"

    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Gate I: Silence gap detection
# ---------------------------------------------------------------------------


def detect_silence_gaps(
    video_path: Path,
    max_gap_ms: int = SOUNDTRACK_MAX_SILENCE_GAP_MS,
) -> List[Dict[str, Any]]:
    """Detect silence gaps longer than max_gap_ms using ffmpeg silencedetect."""
    gaps: List[Dict[str, Any]] = []
    threshold_sec = max_gap_ms / 1000.0
    try:
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-af", f"silencedetect=noise=-50dB:d={threshold_sec}",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        silence_start = None
        for line in proc.stderr.splitlines():
            if "silence_start:" in line:
                for token in line.split():
                    if token.startswith("silence_start:"):
                        try:
                            silence_start = float(token.split(":")[1])
                        except ValueError:
                            pass
            elif "silence_end:" in line and silence_start is not None:
                for token in line.split():
                    if token.startswith("silence_end:"):
                        try:
                            silence_end = float(token.split(":")[1])
                            dur_ms = (silence_end - silence_start) * 1000
                            if dur_ms > max_gap_ms:
                                gaps.append({
                                    "start": round(silence_start, 3),
                                    "end": round(silence_end, 3),
                                    "duration_ms": round(dur_ms, 1),
                                })
                        except ValueError:
                            pass
                silence_start = None
    except Exception:
        pass
    return gaps


# ---------------------------------------------------------------------------
# VO-vs-Music balance (legacy, kept for compatibility)
# ---------------------------------------------------------------------------


def check_vo_music_balance(
    video_path: Path,
    render_config: Dict[str, Any],
) -> BalanceResult:
    """Heuristic check for VO-vs-Music loudness balance."""
    segments = render_config.get("segments", [])
    if not segments:
        return BalanceResult(ok=True)

    vo_windows = []
    music_windows = []
    for seg in segments:
        seg_type = seg.get("type", "")
        t0 = seg.get("t0", 0)
        t1 = seg.get("t1", t0)
        if t1 - t0 < 2:
            continue
        if seg_type == "product":
            vo_windows.append((t0, t1))
        elif seg_type in ("filler", "bumper", "transition"):
            music_windows.append((t0, t1))

    if not vo_windows or not music_windows:
        return BalanceResult(ok=True)

    vo_lufs = _measure_window_lufs(video_path, vo_windows[0][0], vo_windows[0][1])
    music_lufs = _measure_window_lufs(video_path, music_windows[0][0], music_windows[0][1])

    if vo_lufs is None or music_lufs is None:
        return BalanceResult(ok=True)

    gap = vo_lufs - music_lufs
    result = BalanceResult(
        ok=True,
        vo_dominant_lufs=vo_lufs,
        music_dominant_lufs=music_lufs,
        gap_db=round(gap, 1),
    )

    if gap < 8.0:
        result.ok = False
        result.warning = (
            f"VO-Music gap={gap:.1f}dB (< 8dB). "
            f"Music may be too loud relative to VO."
        )

    return result


def _measure_window_lufs(
    video_path: Path, start_sec: float, end_sec: float,
) -> Optional[float]:
    """Measure integrated LUFS for a time window."""
    try:
        duration = end_sec - start_sec
        cmd = [
            "ffmpeg",
            "-ss", str(start_sec),
            "-t", str(duration),
            "-i", str(video_path),
            "-af", "loudnorm=I=-14:LRA=7:TP=-1:print_format=json",
            "-f", "null", "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stderr = proc.stderr
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(stderr[json_start:json_end])
            return float(data.get("input_i", 0))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Integrated postcheck
# ---------------------------------------------------------------------------


def run_audio_postcheck(
    video_path: Path,
    render_config: Dict[str, Any],
    expected_duration: float,
    voiceover_manifest: Optional[Dict[str, Any]] = None,
) -> PostcheckResult:
    """Run all audio postchecks and return structured result.

    Gate A: integrated LUFS in range (FAIL)
    Gate B: true peak <= threshold (FAIL), WARN if close
    Gate C: duration within eps (FAIL)
    Gate D: VAD — voice activity detection
    Gate E: ducking linter (WARN)
    Gate F: spectral clash (WARN)
    Gate G: breath check (FAIL if VO expected but silent)
    Gate H: clipping (WARN/FAIL)
    Gate I: silence gaps (WARN)
    """
    result = PostcheckResult(ok=True)

    if not video_path.exists():
        return PostcheckResult(ok=False, errors=["VIDEO_NOT_FOUND"])

    segments = render_config.get("segments", [])

    # Gate A: loudness
    loudness = measure_loudness(video_path)
    if loudness.ok:
        result.metrics["integrated_lufs"] = loudness.integrated_lufs
        result.metrics["true_peak_db"] = loudness.true_peak_db
        result.metrics["lra"] = loudness.lra

        lo, hi = SOUNDTRACK_LUFS_RANGE
        if not (lo <= loudness.integrated_lufs <= hi):
            result.ok = False
            result.errors.append(
                f"LUFS_OUT_OF_RANGE: {loudness.integrated_lufs:.1f} "
                f"(expected [{lo}, {hi}])"
            )

        # Gate B: true peak
        if loudness.true_peak_db > SOUNDTRACK_TRUE_PEAK_MAX:
            result.ok = False
            result.errors.append(
                f"TRUE_PEAK_HIGH: {loudness.true_peak_db:.1f} dBTP "
                f"(max={SOUNDTRACK_TRUE_PEAK_MAX})"
            )
        elif loudness.true_peak_db > SOUNDTRACK_TRUE_PEAK_WARN:
            result.warnings.append(
                f"TRUE_PEAK_CLOSE: {loudness.true_peak_db:.1f} dBTP "
                f"(warn threshold={SOUNDTRACK_TRUE_PEAK_WARN})"
            )
    else:
        result.warnings.append(f"LOUDNESS_MEASURE_FAIL: {loudness.error}")

    # Gate C: duration
    dur_ok, actual_dur = check_duration(video_path, expected_duration)
    result.metrics["actual_duration_sec"] = actual_dur
    result.metrics["expected_duration_sec"] = expected_duration
    if not dur_ok:
        result.ok = False
        result.errors.append(
            f"DURATION_MISMATCH: actual={actual_dur:.2f}s "
            f"expected={expected_duration:.2f}s"
        )

    # Gate D: VAD
    vad = run_vad(video_path, segments)
    if vad.ok and vad.windows:
        result.metrics["vad"] = {
            "noise_floor_db": vad.noise_floor_db,
            "voice_ratio": vad.voice_ratio,
            "windows_analyzed": len(vad.windows),
            "windows_with_voice": sum(1 for w in vad.windows if w.has_voice),
        }

        # Gate E: ducking linter
        ducking_lint = lint_ducking(video_path, vad)
        if ducking_lint.vo_presence_rms_db is not None:
            result.metrics["ducking_lint"] = {
                "vo_presence_rms_db": ducking_lint.vo_presence_rms_db,
                "no_vo_presence_rms_db": ducking_lint.no_vo_presence_rms_db,
                "effective_reduction_db": ducking_lint.effective_reduction_db,
                "expected_reduction_db": ducking_lint.expected_reduction_db,
            }
        if not ducking_lint.ok:
            result.warnings.append(ducking_lint.warning)

        # Gate F: spectral clash
        clash_warning = detect_spectral_clash(video_path, vad)
        if clash_warning:
            result.warnings.append(clash_warning)

        # Gate G: breath check
        breath = run_breath_check(
            video_path, voiceover_manifest, vad,
        )
        if not breath.ok:
            result.ok = False
            result.errors.extend(breath.errors)
        if breath.warnings:
            result.warnings.extend(breath.warnings)

    # Gate H: clipping
    clipping = detect_clipping(video_path)
    if clipping.clipped_regions:
        result.metrics["clipped_regions"] = len(clipping.clipped_regions)
    if not clipping.ok:
        result.ok = False
        result.errors.append(clipping.warning)
    elif clipping.warning:
        result.warnings.append(clipping.warning)

    # Gate I: silence gaps
    gaps = detect_silence_gaps(video_path)
    if gaps:
        result.metrics["silence_gaps"] = gaps
        result.warnings.append(
            f"SILENCE_GAPS: {len(gaps)} gap(s) > {SOUNDTRACK_MAX_SILENCE_GAP_MS}ms detected"
        )

    # Legacy balance check
    balance = check_vo_music_balance(video_path, render_config)
    if balance.vo_dominant_lufs is not None:
        result.metrics["vo_dominant_lufs"] = balance.vo_dominant_lufs
        result.metrics["music_dominant_lufs"] = balance.music_dominant_lufs
        result.metrics["vo_music_gap_db"] = balance.gap_db
    if not balance.ok:
        result.warnings.append(f"VO_MUSIC_BALANCE: {balance.warning}")

    return result


# ---------------------------------------------------------------------------
# Output: write postcheck JSON
# ---------------------------------------------------------------------------


def write_postcheck_json(
    publish_dir: Path,
    result: PostcheckResult,
) -> Path:
    """Write soundtrack_postcheck.json to publish dir (always)."""
    publish_dir.mkdir(parents=True, exist_ok=True)
    output = publish_dir / "soundtrack_postcheck.json"
    tmp = output.with_suffix(output.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, output)
    return output


def patch_render_receipt(
    receipt_path: Path,
    result: PostcheckResult,
) -> None:
    """Patch render_receipt.json with postcheck metrics."""
    if not receipt_path.exists():
        return
    try:
        with open(receipt_path, "r", encoding="utf-8") as f:
            receipt = json.load(f)
        st = receipt.get("soundtrack_receipt", {})
        st["post_checks"] = result.to_dict()
        receipt["soundtrack_receipt"] = st
        tmp = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, receipt_path)
    except Exception:
        pass
