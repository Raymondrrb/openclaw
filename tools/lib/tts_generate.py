"""ElevenLabs TTS generation — chunked, credit-efficient, deterministic.

Modes:
  full  — generate all chunks for a video
  patch — regenerate specific chunk(s)
  micro — generate a small replacement clip (10-40s)

Stdlib only for core logic. Uses urllib for API calls.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.common import now_iso, project_root, require_env
from tools.lib.notify import notify_error, notify_heartbeat, notify_progress
from tools.lib.pipeline_status import update_milestone
from tools.lib.tts_preprocess import preprocess

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPEAKING_WPM = 155
CHUNK_WORDS_MIN = 300
CHUNK_WORDS_MAX = 450
MAX_RETRIES = 1

# Voice settings (frozen — do not change between videos)
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_STABILITY = 0.50
DEFAULT_SIMILARITY_BOOST = 0.75
DEFAULT_STYLE = 0.00
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

VIDEOS_BASE = project_root() / "artifacts" / "videos"

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChunkMeta:
    index: int
    text_raw: str
    text_preprocessed: str
    word_count: int
    estimated_duration_s: float
    voice_id: str
    model_id: str
    stability: float
    similarity_boost: float
    style: float
    output_format: str
    status: str = "pending"  # pending, success, failed
    file_path: str = ""
    checksum_sha256: str = ""
    actual_duration_s: float = 0.0
    char_count: int = 0
    error: str = ""
    created_at: str = ""
    retries: int = 0


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_script(text: str) -> list[str]:
    """Split script into chunks of ~300-450 words.

    Splits on sentence boundaries. Accumulates sentences until adding
    the next one would exceed CHUNK_WORDS_MAX, then starts a new chunk.
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        word_count = len(sentence.split())

        # If adding this sentence exceeds max, close current chunk
        if current_words + word_count > CHUNK_WORDS_MAX and current:
            chunks.append(" ".join(current))
            current = [sentence]
            current_words = word_count
        else:
            current.append(sentence)
            current_words += word_count

    if current:
        last = " ".join(current)
        # Merge tiny remainder with previous chunk
        if chunks and current_words < 100:
            chunks[-1] = chunks[-1] + " " + last
        else:
            chunks.append(last)

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, keeping sentence-ending punctuation."""
    import re
    # Split on sentence boundaries but keep the punctuation with the sentence
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Audio validation
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def _get_mp3_duration_estimate(path: Path) -> float:
    """Rough MP3 duration estimate from file size and bitrate."""
    size_bytes = path.stat().st_size
    # 128 kbps = 16000 bytes/sec
    return size_bytes / 16000


def validate_chunk_audio(path: Path, expected_words: int) -> tuple[bool, str]:
    """Quick validation of generated audio file.

    Returns (ok, message).
    """
    if not path.is_file():
        return False, "File does not exist"

    size = path.stat().st_size
    if size < 1000:
        return False, f"File too small ({size} bytes) — likely empty or corrupt"

    # Duration check (rough)
    expected_s = expected_words / SPEAKING_WPM * 60
    actual_s = _get_mp3_duration_estimate(path)

    # Allow 50% tolerance
    if actual_s < expected_s * 0.4:
        return False, f"Audio too short: {actual_s:.0f}s vs expected {expected_s:.0f}s"
    if actual_s > expected_s * 2.0:
        return False, f"Audio too long: {actual_s:.0f}s vs expected {expected_s:.0f}s"

    return True, "OK"


# ---------------------------------------------------------------------------
# ElevenLabs API
# ---------------------------------------------------------------------------


def _call_elevenlabs(
    text: str,
    voice_id: str,
    output_path: Path,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    stability: float = DEFAULT_STABILITY,
    similarity_boost: float = DEFAULT_SIMILARITY_BOOST,
    style: float = DEFAULT_STYLE,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> None:
    """Call ElevenLabs TTS API and save audio to output_path."""
    api_key = require_env("ELEVENLABS_API_KEY")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    if output_format:
        url += f"?output_format={output_format}"

    payload = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
        data=payload,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(req, timeout=120) as resp:
        with open(output_path, "wb") as f:
            while True:
                block = resp.read(8192)
                if not block:
                    break
                f.write(block)


# ---------------------------------------------------------------------------
# Generation modes
# ---------------------------------------------------------------------------


def generate_full(
    video_id: str,
    script_text: str,
    *,
    voice_id: str = "",
    output_dir: Path | None = None,
) -> list[ChunkMeta]:
    """Generate all chunks for a video. Returns list of chunk metadata."""
    voice_id = voice_id or require_env("ELEVENLABS_VOICE_ID")
    chunks_dir = output_dir or (VIDEOS_BASE / video_id / "audio" / "chunks")
    chunks_dir.mkdir(parents=True, exist_ok=True)

    # Preprocess and chunk
    preprocessed = preprocess(script_text)
    chunks = chunk_script(preprocessed)

    update_milestone(video_id, "voice", "chunks_started",
                     progress_done=0, progress_total=len(chunks))

    print(f"Generating {len(chunks)} chunks for {video_id}")
    print(f"Voice: {voice_id}, Model: {DEFAULT_MODEL_ID}")

    results: list[ChunkMeta] = []

    for i, chunk_text in enumerate(chunks):
        meta = _generate_single_chunk(
            video_id=video_id,
            chunk_index=i,
            chunk_text_raw=script_text,  # raw not used for generation
            chunk_text=chunk_text,
            voice_id=voice_id,
            chunks_dir=chunks_dir,
        )
        results.append(meta)

        if meta.status == "failed":
            print(f"  Chunk {i:02d}: FAILED — {meta.error}", file=sys.stderr)
            notify_error(
                video_id, "voice", "chunk_generation",
                f"Chunk {i:02d}: {meta.error}",
                next_action=f"Run patch mode: --patch {i}",
            )
        else:
            print(f"  Chunk {i:02d}: OK ({meta.actual_duration_s:.0f}s, {meta.char_count} chars)")
            update_milestone(video_id, "voice", "chunks_generating",
                             progress_done=i + 1, progress_total=len(chunks))
            # Heartbeat on longer runs
            notify_heartbeat(video_id, "voice", "chunks_generating",
                             progress_done=i + 1, progress_total=len(chunks))

    # Summary
    ok = sum(1 for m in results if m.status == "success")
    failed = sum(1 for m in results if m.status == "failed")
    total_chars = sum(m.char_count for m in results if m.status == "success")
    print(f"\nDone: {ok}/{len(results)} chunks OK, {total_chars} total characters")
    if failed:
        print(f"{failed} chunk(s) failed — use patch mode to retry")

    if failed == 0:
        update_milestone(video_id, "voice", "chunks_generated",
                         progress_done=len(chunks), progress_total=len(chunks))
        notify_progress(
            video_id, "voice", "chunks_generated",
            progress_done=len(chunks), progress_total=len(chunks),
            next_action="Review audio chunks, then generate edit manifest",
            details=[f"{len(chunks)} chunks, {total_chars} chars"],
        )

    return results


def generate_patch(
    video_id: str,
    chunk_indices: list[int],
    script_text: str,
    *,
    voice_id: str = "",
    output_dir: Path | None = None,
) -> list[ChunkMeta]:
    """Regenerate specific chunk(s). Same preprocessing + chunking, only generates selected."""
    voice_id = voice_id or require_env("ELEVENLABS_VOICE_ID")
    chunks_dir = output_dir or (VIDEOS_BASE / video_id / "audio" / "chunks")
    chunks_dir.mkdir(parents=True, exist_ok=True)

    preprocessed = preprocess(script_text)
    chunks = chunk_script(preprocessed)

    results: list[ChunkMeta] = []
    for i in chunk_indices:
        if i >= len(chunks):
            print(f"  Chunk {i:02d}: index out of range (only {len(chunks)} chunks)", file=sys.stderr)
            continue

        print(f"Patching chunk {i:02d}...")
        meta = _generate_single_chunk(
            video_id=video_id,
            chunk_index=i,
            chunk_text_raw="",
            chunk_text=chunks[i],
            voice_id=voice_id,
            chunks_dir=chunks_dir,
        )
        results.append(meta)

        if meta.status == "success":
            print(f"  Chunk {i:02d}: OK ({meta.actual_duration_s:.0f}s)")
        else:
            print(f"  Chunk {i:02d}: FAILED — {meta.error}", file=sys.stderr)

    return results


def generate_micro(
    video_id: str,
    text: str,
    label: str = "micro",
    *,
    voice_id: str = "",
    output_dir: Path | None = None,
) -> ChunkMeta:
    """Generate a small replacement clip (10-40s). For stitching in DaVinci."""
    voice_id = voice_id or require_env("ELEVENLABS_VOICE_ID")
    chunks_dir = output_dir or (VIDEOS_BASE / video_id / "audio" / "chunks")
    chunks_dir.mkdir(parents=True, exist_ok=True)

    preprocessed = preprocess(text)
    word_count = len(preprocessed.split())

    print(f"Generating micro patch: '{label}' ({word_count} words)")

    # Use a special naming: micro_<label>_<timestamp>.mp3
    ts = now_iso().replace(":", "").replace("-", "")[:15]
    file_name = f"micro_{label}_{ts}.mp3"
    output_path = chunks_dir / file_name

    meta = ChunkMeta(
        index=-1,
        text_raw=text,
        text_preprocessed=preprocessed,
        word_count=word_count,
        estimated_duration_s=round(word_count / SPEAKING_WPM * 60, 1),
        voice_id=voice_id,
        model_id=DEFAULT_MODEL_ID,
        stability=DEFAULT_STABILITY,
        similarity_boost=DEFAULT_SIMILARITY_BOOST,
        style=DEFAULT_STYLE,
        output_format=DEFAULT_OUTPUT_FORMAT,
        char_count=len(preprocessed),
        created_at=now_iso(),
    )

    for attempt in range(1 + MAX_RETRIES):
        try:
            _call_elevenlabs(preprocessed, voice_id, output_path)
            ok, msg = validate_chunk_audio(output_path, word_count)
            if ok:
                meta.status = "success"
                meta.file_path = str(output_path)
                meta.checksum_sha256 = _file_sha256(output_path)
                meta.actual_duration_s = _get_mp3_duration_estimate(output_path)
                meta.retries = attempt
                break
            else:
                meta.error = msg
                meta.retries = attempt
        except Exception as exc:
            meta.error = str(exc)
            meta.retries = attempt

    if meta.status != "success":
        meta.status = "failed"

    # Save metadata
    meta_path = output_path.with_suffix(".json")
    _save_chunk_meta(meta, meta_path)

    return meta


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_single_chunk(
    *,
    video_id: str,
    chunk_index: int,
    chunk_text_raw: str,
    chunk_text: str,
    voice_id: str,
    chunks_dir: Path,
) -> ChunkMeta:
    """Generate a single chunk with up to 1 retry."""
    word_count = len(chunk_text.split())
    output_path = chunks_dir / f"{chunk_index:02d}.mp3"

    meta = ChunkMeta(
        index=chunk_index,
        text_raw=chunk_text_raw,
        text_preprocessed=chunk_text,
        word_count=word_count,
        estimated_duration_s=round(word_count / SPEAKING_WPM * 60, 1),
        voice_id=voice_id,
        model_id=DEFAULT_MODEL_ID,
        stability=DEFAULT_STABILITY,
        similarity_boost=DEFAULT_SIMILARITY_BOOST,
        style=DEFAULT_STYLE,
        output_format=DEFAULT_OUTPUT_FORMAT,
        char_count=len(chunk_text),
        created_at=now_iso(),
    )

    for attempt in range(1 + MAX_RETRIES):
        try:
            _call_elevenlabs(chunk_text, voice_id, output_path)

            ok, msg = validate_chunk_audio(output_path, word_count)
            if ok:
                meta.status = "success"
                meta.file_path = str(output_path)
                meta.checksum_sha256 = _file_sha256(output_path)
                meta.actual_duration_s = _get_mp3_duration_estimate(output_path)
                meta.retries = attempt
                break
            else:
                meta.error = msg
                meta.retries = attempt
                if attempt < MAX_RETRIES:
                    print(f"    Retry {attempt + 1}: {msg}", file=sys.stderr)
                    time.sleep(2)

        except Exception as exc:
            meta.error = str(exc)
            meta.retries = attempt
            if attempt < MAX_RETRIES:
                print(f"    Retry {attempt + 1}: {exc}", file=sys.stderr)
                time.sleep(2)

    if meta.status != "success":
        meta.status = "failed"

    # Save metadata JSON alongside audio
    meta_path = output_path.with_suffix(".json")
    _save_chunk_meta(meta, meta_path)

    return meta


def _save_chunk_meta(meta: ChunkMeta, path: Path) -> None:
    """Write chunk metadata to JSON file."""
    data = {
        "index": meta.index,
        "text_preprocessed": meta.text_preprocessed,
        "word_count": meta.word_count,
        "char_count": meta.char_count,
        "estimated_duration_s": meta.estimated_duration_s,
        "actual_duration_s": meta.actual_duration_s,
        "voice_id": meta.voice_id,
        "model_id": meta.model_id,
        "settings": {
            "stability": meta.stability,
            "similarity_boost": meta.similarity_boost,
            "style": meta.style,
        },
        "output_format": meta.output_format,
        "status": meta.status,
        "file_path": meta.file_path,
        "checksum_sha256": meta.checksum_sha256,
        "error": meta.error,
        "retries": meta.retries,
        "created_at": meta.created_at,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
