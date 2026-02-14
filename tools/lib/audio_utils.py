"""Audio utilities v0.2.0 — smart finalize gate, filler scrub, pause tags.

Pre-TTS text optimization and post-TTS audio finalization for
deterministic timeline assembly.

finalize_segment_audio is a 4-action gate:
  1. PAD_SILENCE — audio shorter than target → inject trailing silence
  2. OK          — within tolerance → no change
  3. RATE_TWEAK  — slightly over (≤2%) → FFmpeg atempo speedup
  4. NEEDS_REPAIR — way over (>2%) → flag for LLM text patch

Returns FinalizeResult with action, delta_ms, rate, reason — the
orchestrator uses this to decide whether to re-TTS or proceed to Dzine.

Pause tag handling:
  - Parse [pause=300ms] tags into structured tokens
  - Inject deterministic silence locally (post-TTS, not via TTS API)

Tolerance by segment kind:
  - intro/outro: 80ms (tight — viewer attention)
  - product:     120ms (technical, forgiving)
  - transition:  150ms (brief, very forgiving)

Dependencies:
  - pydub (optional — for audio surgery; gracefully skipped if missing)
  - ffmpeg (optional — for atempo rate tweak; graceful fallback)

Usage:
    from tools.lib.audio_utils import scrub_fillers, estimate_duration_sec
    from tools.lib.audio_utils import finalize_segment_audio, FinalizeResult
    from tools.lib.audio_utils import tokenize_pause_tags, total_pause_ms
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

# Reuse TTS tag stripping from tone_gate
from tools.lib.tone_gate import strip_tts_tags, estimate_duration_sec, count_words


# ---------------------------------------------------------------------------
# Filler word scrubbing (deterministic, zero LLM cost)
# ---------------------------------------------------------------------------

FILLER_WORDS_EN = frozenset({
    "just", "really", "basically", "actually", "literally", "honestly",
    "kind", "sort", "like", "pretty", "very", "quite",
})

FILLER_WORDS_PT = frozenset({
    "tipo", "basicamente", "literalmente", "realmente", "assim", "meio",
    "na", "real", "bom", "enfim",
})

_FILLER_MAP = {
    "en": FILLER_WORDS_EN,
    "pt": FILLER_WORDS_PT,
}


def scrub_fillers(text: str, lang: str = "en") -> str:
    """Remove filler words from text without LLM.

    Preserves sentence structure and punctuation.
    Safe for TTS — only removes words that add no technical information.

    Args:
        text: Input text (may contain TTS tags).
        lang: Language code prefix ("en" or "pt").

    Returns:
        Text with filler words removed.
    """
    prefix = lang.lower()[:2]
    fillers = _FILLER_MAP.get(prefix, FILLER_WORDS_EN)

    parts = text.split()
    out = []
    for token in parts:
        # Normalize for comparison but keep original
        key = token.lower().strip(".,!?;:\"'")
        if key in fillers:
            continue
        out.append(token)
    return " ".join(out).strip()


# ---------------------------------------------------------------------------
# Pause tag parsing — structured tokens for deterministic silence injection
# ---------------------------------------------------------------------------

_PAUSE_TAG_RE = re.compile(r"\[pause=(\d+)ms\]", re.IGNORECASE)


@dataclass(frozen=True)
class PauseToken:
    """A parsed [pause=Xms] tag."""
    ms: int


@dataclass(frozen=True)
class TextToken:
    """A text fragment between pause tags."""
    text: str


# Union type for tokens
Token = Union[PauseToken, TextToken]


def tokenize_pause_tags(text: str) -> List[Token]:
    """Parse text with [pause=Xms] tags into structured tokens.

    Example:
        "Hello [pause=300ms] world" →
        [TextToken("Hello "), PauseToken(300), TextToken(" world")]

    Returns list of PauseToken and TextToken instances.
    """
    tokens: List[Token] = []
    last = 0
    for m in _PAUSE_TAG_RE.finditer(text):
        if m.start() > last:
            tokens.append(TextToken(text=text[last:m.start()]))
        tokens.append(PauseToken(ms=int(m.group(1))))
        last = m.end()
    if last < len(text):
        tokens.append(TextToken(text=text[last:]))
    return tokens


def total_pause_ms(text: str) -> int:
    """Sum all [pause=Xms] durations in text. Returns 0 if no tags."""
    return sum(
        t.ms for t in tokenize_pause_tags(text)
        if isinstance(t, PauseToken)
    )


# ---------------------------------------------------------------------------
# Canonical JSON + digest (for idempotent audio caching)
# ---------------------------------------------------------------------------

def canonical_json(obj: Any) -> str:
    """Canonical JSON for stable hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalize_text(text: str) -> str:
    """Normalize text for hashing: strip + collapse whitespace."""
    return " ".join(text.strip().split())


def compute_audio_digest(
    voice_id: str,
    text: str,
    model: str,
    stability: float = 0.4,
    style: float = 0.35,
) -> str:
    """Compute idempotent digest for audio segment.

    Same inputs → same digest → skip re-generation.
    """
    payload = {
        "voice_id": voice_id,
        "model": model,
        "text": normalize_text(text),
        "stability": round(stability, 3),
        "style": round(style, 3),
    }
    return hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 of a file. For manifest integrity checks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Atomic file write (crash-safe)
# ---------------------------------------------------------------------------

def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically: tmp → fsync → os.replace.

    Prevents partial/corrupt files on crash or power loss.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: tmp → fsync → os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        with open(tmp, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# FinalizeResult — structured return from the finalize gate
# ---------------------------------------------------------------------------

Action = Literal["ok", "pad_silence", "rate_tweak", "needs_repair", "error"]


@dataclass(frozen=True)
class FinalizeResult:
    """Outcome of finalize_segment_audio gate decision."""
    action: Action
    input_path: Path
    output_path: Path
    target_duration_sec: float
    measured_duration_sec: float
    delta_ms: int
    rate: Optional[float] = None
    reason: Optional[str] = None


# Tolerance per segment kind (ms)
_KIND_TOLERANCE_MS: Dict[str, int] = {
    "intro": 80,
    "outro": 80,
    "product": 120,
    "transition": 150,
}
_DEFAULT_TOLERANCE_MS = 80


def tolerance_ms_for_kind(kind: str) -> int:
    """Return tolerance in ms for a segment kind."""
    return _KIND_TOLERANCE_MS.get(kind, _DEFAULT_TOLERANCE_MS)


# ---------------------------------------------------------------------------
# Silence padding + pause injection + smart finalize gate
# ---------------------------------------------------------------------------

try:
    from pydub import AudioSegment as _AudioSegment
    _HAS_PYDUB = True
except ImportError:
    _HAS_PYDUB = False


def _guess_format(path: Path) -> str:
    """Guess audio format from file extension."""
    ext = path.suffix.lower().lstrip(".")
    return ext if ext in ("mp3", "wav", "m4a", "ogg") else "mp3"


def _inject_pause_silence(audio: "_AudioSegment", source_text: str) -> "_AudioSegment":
    """Inject silence corresponding to [pause=Xms] tags.

    Appends total pause duration as trailing silence.
    Deterministic, cheap, and timeline-safe.
    """
    pause_total = total_pause_ms(source_text)
    if pause_total <= 0:
        return audio
    return audio + _AudioSegment.silent(duration=pause_total)


def _export_atomic(seg: "_AudioSegment", out_path: Path, fmt: str = "mp3") -> None:
    """Export AudioSegment atomically: tmp → fsync → replace."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    try:
        seg.export(tmp, format=fmt)
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp, out_path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _ffmpeg_atempo(in_path: Path, out_path: Path, rate: float) -> None:
    """Speed up/down audio with FFmpeg atempo filter.

    atempo accepts 0.5–2.0. For our use case rate is always 1.00–1.05.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_path),
        "-filter:a", f"atempo={rate}",
        "-vn",
        str(tmp),
    ]
    p = subprocess.run(cmd, capture_output=True, timeout=30)
    if p.returncode != 0:
        raise RuntimeError(
            f"ffmpeg atempo failed: {p.stderr.decode('utf-8', errors='ignore')[:400]}"
        )
    with open(tmp, "rb") as f:
        os.fsync(f.fileno())
    os.replace(tmp, out_path)


def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available on PATH."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def finalize_segment_audio(
    audio_path: Path,
    target_duration: float,
    *,
    source_text: Optional[str] = None,
    kind: str = "product",
    allow_rate_tweak: bool = True,
    max_over_pct_for_rate: float = 0.02,
    max_rate: float = 1.05,
    force_format: str = "mp3",
) -> FinalizeResult:
    """Smart 4-action finalize gate for post-TTS audio.

    Decision logic:
    1. Inject [pause=Xms] silence from source_text (if present)
    2. If within tolerance → OK (no change)
    3. If shorter → PAD_SILENCE (trailing silence to hit target)
    4. If slightly over (≤max_over_pct_for_rate) → RATE_TWEAK (FFmpeg atempo)
    5. If way over → NEEDS_REPAIR (flag for LLM text patch)

    The orchestrator inspects FinalizeResult.action to decide next step.
    Dzine only receives audio with action in {ok, pad_silence, rate_tweak}.

    Returns FinalizeResult even when pydub is not installed (action=error).
    """
    # Error: bad target
    if target_duration <= 0:
        return FinalizeResult(
            action="error", input_path=audio_path, output_path=audio_path,
            target_duration_sec=target_duration, measured_duration_sec=0.0,
            delta_ms=0, reason="target_duration must be > 0",
        )

    # Error: pydub not available
    if not _HAS_PYDUB:
        return FinalizeResult(
            action="error", input_path=audio_path, output_path=audio_path,
            target_duration_sec=target_duration, measured_duration_sec=0.0,
            delta_ms=0, reason="pydub not installed",
        )

    # Error: file missing
    if not audio_path.exists():
        return FinalizeResult(
            action="error", input_path=audio_path, output_path=audio_path,
            target_duration_sec=target_duration, measured_duration_sec=0.0,
            delta_ms=0, reason=f"audio file missing: {audio_path}",
        )

    fmt = force_format or _guess_format(audio_path)
    audio = _AudioSegment.from_file(audio_path)

    # Step 1: Inject pause tag silence
    if source_text:
        audio = _inject_pause_silence(audio, source_text)

    target_ms = int(target_duration * 1000)
    measured_ms = len(audio)
    tol_ms = tolerance_ms_for_kind(kind)
    delta_ms = target_ms - measured_ms  # positive = short, negative = over

    measured_sec = measured_ms / 1000.0

    # Action: OK — within tolerance
    if abs(delta_ms) <= tol_ms:
        return FinalizeResult(
            action="ok", input_path=audio_path, output_path=audio_path,
            target_duration_sec=target_duration, measured_duration_sec=measured_sec,
            delta_ms=delta_ms, reason=f"within {tol_ms}ms tolerance ({kind})",
        )

    # Action: PAD_SILENCE — audio shorter than target
    if delta_ms > 0:
        silence = _AudioSegment.silent(duration=delta_ms)
        padded = audio + silence
        _export_atomic(padded, audio_path, fmt=fmt)
        return FinalizeResult(
            action="pad_silence", input_path=audio_path, output_path=audio_path,
            target_duration_sec=target_duration,
            measured_duration_sec=len(padded) / 1000.0,
            delta_ms=int(target_ms - len(padded)),
            reason=f"padded +{delta_ms}ms",
        )

    # Audio is over target — decide rate_tweak vs needs_repair
    over_ms = -delta_ms
    over_pct = over_ms / max(target_ms, 1)

    # Action: RATE_TWEAK — slightly over, use FFmpeg atempo
    if allow_rate_tweak and over_pct <= max_over_pct_for_rate:
        rate = measured_ms / target_ms
        rate = max(1.0, min(rate, max_rate))

        if _has_ffmpeg():
            try:
                _ffmpeg_atempo(audio_path, audio_path, rate=rate)
                # After tweak, pad any remaining gap
                tweaked = _AudioSegment.from_file(audio_path)
                tweaked_ms = len(tweaked)
                gap_ms = target_ms - tweaked_ms
                if gap_ms > 0:
                    tweaked = tweaked + _AudioSegment.silent(duration=gap_ms)
                    _export_atomic(tweaked, audio_path, fmt=fmt)
                    tweaked_ms = len(tweaked)
                return FinalizeResult(
                    action="rate_tweak", input_path=audio_path, output_path=audio_path,
                    target_duration_sec=target_duration,
                    measured_duration_sec=tweaked_ms / 1000.0,
                    delta_ms=int(target_ms - tweaked_ms),
                    rate=rate,
                    reason=f"over by {over_ms}ms ({over_pct:.1%}); atempo={rate:.3f}",
                )
            except Exception as e:
                # FFmpeg failed — fall through to needs_repair
                return FinalizeResult(
                    action="needs_repair", input_path=audio_path, output_path=audio_path,
                    target_duration_sec=target_duration,
                    measured_duration_sec=measured_sec,
                    delta_ms=delta_ms, rate=rate,
                    reason=f"rate_tweak failed ({e}); needs text repair",
                )
        else:
            # No ffmpeg — fall through to needs_repair
            return FinalizeResult(
                action="needs_repair", input_path=audio_path, output_path=audio_path,
                target_duration_sec=target_duration,
                measured_duration_sec=measured_sec,
                delta_ms=delta_ms,
                reason=f"over by {over_ms}ms ({over_pct:.1%}); ffmpeg not available",
            )

    # Action: NEEDS_REPAIR — way over, needs LLM text patch
    return FinalizeResult(
        action="needs_repair", input_path=audio_path, output_path=audio_path,
        target_duration_sec=target_duration, measured_duration_sec=measured_sec,
        delta_ms=delta_ms,
        reason=f"over by {over_ms}ms ({over_pct:.1%}) exceeds rate_tweak threshold",
    )
