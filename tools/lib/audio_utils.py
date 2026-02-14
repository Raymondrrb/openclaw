"""Audio utilities — filler scrub, silence padding, TTS helpers.

Pre-TTS text optimization and post-TTS audio finalization for
deterministic timeline assembly.

Three-level auto-cutter (cheapest first):
  A) Rate tweak: inject [rate=1.05] for small overages (free)
  B) Filler scrub: regex-remove filler words (free, deterministic)
  C) LLM repair: patch request to shorten segment (expensive, last resort)

Post-TTS finalization:
  - Silence padding: pad audio to exact approx_duration_sec
  - Atomic write: tmp → fsync → replace (no partial files)

Dependencies:
  - pydub (optional — for silence padding; gracefully skipped if missing)
  - ffmpeg (optional — required by pydub)

Usage:
    from tools.lib.audio_utils import scrub_fillers, estimate_duration_sec
    from tools.lib.audio_utils import finalize_segment_audio, atomic_write_bytes
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

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
# Silence padding (post-TTS finalization)
# ---------------------------------------------------------------------------

try:
    from pydub import AudioSegment as _AudioSegment
    _HAS_PYDUB = True
except ImportError:
    _HAS_PYDUB = False


def finalize_segment_audio(
    audio_path: Path,
    target_duration: float,
) -> None:
    """Pad audio with trailing silence to match target duration.

    Only adds silence if audio is shorter than target.
    Does NOT trim audio that's longer (leave that to Tone Gate).

    Requires pydub + ffmpeg. No-op if pydub is not installed.

    Args:
        audio_path: Path to audio file (mp3/wav).
        target_duration: Target duration in seconds.
    """
    if not _HAS_PYDUB:
        return

    if not audio_path.exists() or target_duration <= 0:
        return

    audio = _AudioSegment.from_file(audio_path)
    current_ms = len(audio)
    target_ms = int(target_duration * 1000)

    if current_ms >= target_ms:
        return  # Already long enough

    silence = _AudioSegment.silent(duration=(target_ms - current_ms))
    padded = audio + silence

    # Determine format from extension
    ext = audio_path.suffix.lower().lstrip(".")
    fmt = ext if ext in ("mp3", "wav", "m4a", "ogg") else "mp3"
    padded.export(audio_path, format=fmt)
