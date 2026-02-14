"""ElevenLabs TTS agent — text-to-speech with validation.

Produces audio artifacts via the ElevenLabs API.
Stdlib only (urllib) — no requests/httpx dependency.

Usage:
    from tools.agents.elevenlabs_tts import ElevenLabsTTS, ElevenLabsConfig

    cfg = ElevenLabsConfig(api_key="...", voice_id="...")
    tts = ElevenLabsTTS(cfg)
    audio_path = tts.synthesize(run_id="abc-123", text="Hello world")
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class ElevenLabsConfig:
    """ElevenLabs API configuration."""
    api_key: str
    voice_id: str
    model_id: str = "eleven_multilingual_v2"
    output_dir: str = "state/artifacts/audio"
    min_output_bytes: int = 50_000     # reject truncated audio
    max_text_chars: int = 5000         # API limit guard
    timeout_sec: int = 60


class TTSValidationError(RuntimeError):
    """Raised when TTS output fails validation."""
    pass


class ElevenLabsTTS:
    """ElevenLabs TTS with validation + metadata artifact."""

    def __init__(self, cfg: ElevenLabsConfig):
        self.cfg = cfg
        Path(self.cfg.output_dir).mkdir(parents=True, exist_ok=True)

    def synthesize(self, *, run_id: str, text: str) -> Path:
        """Generate speech from text. Returns path to MP3 file.

        Also writes a metadata JSON sidecar ({run_id}.json).
        Raises TTSValidationError if output is too small.
        """
        if not text.strip():
            raise TTSValidationError("Empty text — nothing to synthesize")

        if len(text) > self.cfg.max_text_chars:
            raise TTSValidationError(
                f"Text too long: {len(text)} chars (max {self.cfg.max_text_chars})"
            )

        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{self.cfg.voice_id}"
        )
        headers = {
            "xi-api-key": self.cfg.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = json.dumps({
            "text": text,
            "model_id": self.cfg.model_id,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_sec) as resp:
                audio_data = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:500]
            raise TTSValidationError(
                f"ElevenLabs API error {e.code}: {body}"
            )
        except Exception as e:
            raise TTSValidationError(f"ElevenLabs request failed: {e}")

        out_mp3 = Path(self.cfg.output_dir) / f"{run_id}.mp3"
        out_mp3.write_bytes(audio_data)

        # Validate size (anti truncation / empty response)
        size = out_mp3.stat().st_size
        if size < self.cfg.min_output_bytes:
            raise TTSValidationError(
                f"TTS output too small: {size} bytes (min {self.cfg.min_output_bytes}). "
                f"Likely failed or truncated."
            )

        # Write metadata sidecar
        meta_path = Path(self.cfg.output_dir) / f"{run_id}.json"
        meta: Dict[str, Any] = {
            "run_id": run_id,
            "voice_id": self.cfg.voice_id,
            "model_id": self.cfg.model_id,
            "text_chars": len(text),
            "bytes": size,
            "path": str(out_mp3),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return out_mp3

    def has_artifact(self, run_id: str) -> bool:
        """Check if audio artifact already exists (idempotency precondition)."""
        out_mp3 = Path(self.cfg.output_dir) / f"{run_id}.mp3"
        return out_mp3.exists() and out_mp3.stat().st_size >= self.cfg.min_output_bytes
