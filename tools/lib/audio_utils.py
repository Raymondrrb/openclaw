"""Audio utilities v0.1.1 — filler scrub, pause tags, precise padding.

Pre-TTS text optimization and post-TTS audio finalization for
deterministic timeline assembly.

Three-level auto-cutter (cheapest first):
  A) Rate tweak: inject [rate=1.05] for small overages (free)
  B) Filler scrub: regex-remove filler words (free, deterministic)
  C) LLM repair: patch request to shorten segment (expensive, last resort)

Pause tag handling (v0.1.1):
  - Parse [pause=300ms] tags into structured tokens
  - Inject deterministic silence locally (post-TTS, not via TTS API)
  - More precise and cheaper than relying on TTS pause support

Post-TTS finalization:
  - Silence injection for [pause=] tags
  - Pad to exact target_duration (timeline determinism)
  - Optionally trim trailing silence if audio exceeds target
  - Atomic write: tmp → fsync → replace (no partial files)

Dependencies:
  - pydub (optional — for audio surgery; gracefully skipped if missing)
  - ffmpeg (optional — required by pydub)

Usage:
    from tools.lib.audio_utils import scrub_fillers, estimate_duration_sec
    from tools.lib.audio_utils import finalize_segment_audio, atomic_write_bytes
    from tools.lib.audio_utils import tokenize_pause_tags, total_pause_ms
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Union

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
# Silence padding + pause injection (post-TTS finalization)
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

    v0.1.1 approach: appends total pause duration as trailing silence.
    This is deterministic, cheap, and timeline-safe.

    For "mid-sentence" pauses (v0.2+), split text at pause tags,
    generate TTS per sub-phrase, then concatenate with silence between.
    """
    pause_total = total_pause_ms(source_text)
    if pause_total <= 0:
        return audio
    return audio + _AudioSegment.silent(duration=pause_total)


def _detect_trailing_silence_ms(audio: "_AudioSegment", threshold_dbfs: float = -45.0) -> int:
    """Detect how many milliseconds of trailing silence an audio has.

    Scans backward in 50ms chunks from the end.
    Returns ms of consecutive silence below threshold.
    """
    chunk_ms = 50
    total_ms = len(audio)
    silence_ms = 0

    pos = total_ms - chunk_ms
    while pos >= 0:
        chunk = audio[pos:pos + chunk_ms]
        if chunk.dBFS < threshold_dbfs:
            silence_ms += chunk_ms
            pos -= chunk_ms
        else:
            break

    return silence_ms


def finalize_segment_audio(
    audio_path: Path,
    target_duration: float,
    *,
    source_text: Optional[str] = None,
    trim_trailing_silence: bool = True,
    silence_threshold_dbfs: float = -45.0,
) -> None:
    """Post-TTS finalization for deterministic timeline duration.

    Steps:
    1. If source_text has [pause=Xms] tags, inject silence (local, exact)
    2. If audio < target_duration: pad with trailing silence
    3. If audio > target_duration and trim_trailing_silence: trim ONLY
       trailing silence (never cuts speech)

    Result: audio file with exact target_duration for timeline assembly.

    Requires pydub + ffmpeg. No-op if pydub is not installed.

    Args:
        audio_path: Path to audio file (mp3/wav).
        target_duration: Target duration in seconds.
        source_text: Original text with TTS tags for pause injection.
        trim_trailing_silence: If True, trim excess trailing silence
            when audio exceeds target (safe — never cuts speech).
        silence_threshold_dbfs: dBFS threshold for silence detection.
    """
    if not _HAS_PYDUB:
        return

    if not audio_path.exists() or target_duration <= 0:
        return

    fmt = _guess_format(audio_path)
    audio = _AudioSegment.from_file(audio_path)

    # Step 1: Inject pause tag silence
    if source_text:
        audio = _inject_pause_silence(audio, source_text)

    target_ms = int(target_duration * 1000)
    current_ms = len(audio)

    # Step 2: Pad if shorter
    if current_ms < target_ms:
        silence = _AudioSegment.silent(duration=(target_ms - current_ms))
        audio = audio + silence

    # Step 3: Trim trailing silence if longer
    elif current_ms > target_ms and trim_trailing_silence:
        over_ms = current_ms - target_ms
        trailing = _detect_trailing_silence_ms(audio, silence_threshold_dbfs)
        # Only trim up to the amount of trailing silence available
        trim_amount = min(over_ms, trailing)
        if trim_amount > 0:
            audio = audio[:current_ms - trim_amount]

    audio.export(audio_path, format=fmt)
