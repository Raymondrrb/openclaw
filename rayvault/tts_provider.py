"""TTS Provider abstraction — pluggable voice synthesis backends.

Architecture:
    TTSProvider (Protocol) → concrete providers
    ├── ElevenLabsProvider  (production default, API-based)
    ├── MossTTSProvider      (optional, requires CUDA endpoint)
    └── MockProvider         (testing, generates silence)

Usage:
    from rayvault.tts_provider import get_provider, synthesize_segments

    provider = get_provider()  # reads TTS_PROVIDER env / config
    result = provider.synthesize("Hello world", "ray_voice", Path("out.mp3"))

The provider is selected via:
    1. TTS_PROVIDER env var ("elevenlabs", "moss", "mock")
    2. Defaults to "elevenlabs"

MOSS-TTS requires a separate CUDA machine running the inference server.
Set MOSS_TTS_ENDPOINT=http://<cuda-host>:8090/synthesize to enable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTS input hashing (for cache lookups)
# ---------------------------------------------------------------------------

def tts_input_hash(
    text: str,
    voice_id: str,
    provider: str,
    *,
    reference_audio_sha1: str = "",
    model_id: str = "",
    settings: Optional[Dict] = None,
) -> str:
    """Deterministic hash of TTS inputs for cache key.

    Same inputs → same hash → reuse cached audio.
    """
    parts = [
        f"provider={provider}",
        f"model={model_id}",
        f"voice={voice_id}",
        f"ref={reference_audio_sha1}",
        f"text={text.strip()}",
    ]
    if settings:
        parts.append(f"settings={json.dumps(settings, sort_keys=True)}")
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class TTSProvider(Protocol):
    """Interface for TTS backends."""

    name: str

    # Capability flags
    supports_voice_clone: bool
    supports_duration_control: bool

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        *,
        reference_audio_path: Optional[Path] = None,
        model_id: str = "",
        speed: Optional[float] = None,
        seed: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
        log: Optional[logging.Logger] = None,
    ) -> Dict[str, Any]:
        """Synthesize speech and write to output_path.

        Returns metadata dict:
            provider, model_id, voice_id, duration_sec, sha1_audio,
            sample_rate, tts_inputs_hash, settings
        """
        ...


# ---------------------------------------------------------------------------
# ElevenLabs Provider
# ---------------------------------------------------------------------------

_ELEVENLABS_ENV = Path(os.path.expanduser("~/.config/newproject/elevenlabs.env"))

_ELEVENLABS_DEFAULTS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


def _load_elevenlabs_config() -> Dict[str, str]:
    cfg = {"api_key": "", "voice_id": "", "voice_name": "Thomas Louis"}
    if _ELEVENLABS_ENV.exists():
        for line in _ELEVENLABS_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k == "ELEVENLABS_API_KEY":
                cfg["api_key"] = v
            elif k == "ELEVENLABS_VOICE_ID":
                cfg["voice_id"] = v
            elif k == "ELEVENLABS_VOICE_NAME":
                cfg["voice_name"] = v
    cfg["api_key"] = os.environ.get("ELEVENLABS_API_KEY", cfg["api_key"])
    cfg["voice_id"] = os.environ.get("ELEVENLABS_VOICE_ID", cfg["voice_id"])
    return cfg


class ElevenLabsProvider:
    """ElevenLabs TTS via REST API."""

    name = "elevenlabs"
    supports_voice_clone = False  # via API settings, not zero-shot reference
    supports_duration_control = False

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        *,
        reference_audio_path: Optional[Path] = None,
        model_id: str = "eleven_multilingual_v2",
        speed: Optional[float] = None,
        seed: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
        log: Optional[logging.Logger] = None,
    ) -> Dict[str, Any]:
        cfg = _load_elevenlabs_config()
        api_key = cfg["api_key"]
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not configured")
        voice_id = voice_id or cfg["voice_id"]
        if not voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID not configured")

        voice_settings = dict(_ELEVENLABS_DEFAULTS)
        if settings:
            voice_settings.update(settings)

        payload = json.dumps({
            "text": text,
            "model_id": model_id,
            "voice_settings": voice_settings,
        }).encode("utf-8")

        req = Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            method="POST",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": api_key,
                "Accept": "audio/mpeg",
            },
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(".tmp.mp3")
        try:
            with urlopen(req, timeout=300) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
            os.replace(tmp, output_path)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            err_msg = str(e)
            if hasattr(e, "read"):
                err_msg = e.read().decode("utf-8", errors="replace")
            if log:
                log.error(f"ElevenLabs TTS error: {err_msg}")
            raise RuntimeError(f"ElevenLabs TTS error: {err_msg}") from e

        sha1 = _file_sha1(output_path)
        size_kb = output_path.stat().st_size / 1024
        if log:
            log.info(f"ElevenLabs TTS: {size_kb:.0f}KB → {output_path.name}")

        return {
            "provider": self.name,
            "model_id": model_id,
            "voice_id": voice_id,
            "sha1_audio": sha1,
            "tts_inputs_hash": tts_input_hash(
                text, voice_id, self.name,
                model_id=model_id, settings=voice_settings,
            ),
            "settings": voice_settings,
        }


# ---------------------------------------------------------------------------
# MOSS-TTS Provider (requires CUDA endpoint)
# ---------------------------------------------------------------------------

# Endpoint: MOSS_TTS_ENDPOINT env var (e.g. http://192.168.1.100:8090/synthesize)
# Model: MOSS_TTS_MODEL env var ("moss-tts-8b-delay" or "moss-tts-1.7b-local")
# Reference audio: optional WAV for zero-shot voice cloning

class MossTTSProvider:
    """MOSS-TTS via HTTP endpoint on a CUDA machine.

    Requires a running MOSS-TTS inference server. Does NOT run locally on macOS.

    Setup:
        1. On CUDA machine: run MOSS-TTS server (see OpenMOSS-Team/MOSS-TTS)
        2. Set MOSS_TTS_ENDPOINT=http://<host>:<port>/synthesize
        3. Optionally set MOSS_TTS_MODEL (default: moss-tts-8b-delay)
        4. Place reference audio at config/ray_voice_reference.wav for cloning
    """

    name = "moss_tts"
    supports_voice_clone = True
    supports_duration_control = True

    def __init__(self):
        self.endpoint = os.environ.get("MOSS_TTS_ENDPOINT", "")
        self.default_model = os.environ.get("MOSS_TTS_MODEL", "moss-tts-8b-delay")

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        *,
        reference_audio_path: Optional[Path] = None,
        model_id: str = "",
        speed: Optional[float] = None,
        seed: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
        log: Optional[logging.Logger] = None,
    ) -> Dict[str, Any]:
        if not self.endpoint:
            raise RuntimeError(
                "MOSS_TTS_ENDPOINT not configured. "
                "MOSS-TTS requires a CUDA machine running the inference server. "
                "Set MOSS_TTS_ENDPOINT=http://<host>:<port>/synthesize"
            )

        model = model_id or self.default_model
        ref_sha1 = ""

        # Build request payload
        request_body: Dict[str, Any] = {
            "text": text,
            "model_id": model,
            "voice_id": voice_id,
        }
        if speed is not None:
            request_body["speed"] = speed
        if seed is not None:
            request_body["seed"] = seed
        if settings:
            request_body["settings"] = settings

        # Include reference audio for voice cloning (base64-encoded)
        if reference_audio_path and reference_audio_path.exists():
            import base64
            audio_bytes = reference_audio_path.read_bytes()
            request_body["reference_audio_b64"] = base64.b64encode(audio_bytes).decode("ascii")
            ref_sha1 = _file_sha1(reference_audio_path)

        payload = json.dumps(request_body).encode("utf-8")

        req = Request(
            self.endpoint,
            method="POST",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "audio/wav",
            },
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix(".tmp.wav")
        try:
            with urlopen(req, timeout=600) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())
            os.replace(tmp, output_path)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            err_msg = str(e)
            if hasattr(e, "read"):
                err_msg = e.read().decode("utf-8", errors="replace")
            if log:
                log.error(f"MOSS-TTS error: {err_msg}")
            raise RuntimeError(f"MOSS-TTS error: {err_msg}") from e

        sha1 = _file_sha1(output_path)
        if log:
            size_kb = output_path.stat().st_size / 1024
            log.info(f"MOSS-TTS: {size_kb:.0f}KB → {output_path.name}")

        return {
            "provider": self.name,
            "model_id": model,
            "voice_id": voice_id,
            "sha1_audio": sha1,
            "reference_audio_sha1": ref_sha1,
            "tts_inputs_hash": tts_input_hash(
                text, voice_id, self.name,
                reference_audio_sha1=ref_sha1,
                model_id=model, settings=settings,
            ),
            "settings": settings or {},
        }


# ---------------------------------------------------------------------------
# Mock Provider (for testing)
# ---------------------------------------------------------------------------

class MockTTSProvider:
    """Generates a silent WAV file for testing."""

    name = "mock"
    supports_voice_clone = False
    supports_duration_control = False

    def synthesize(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        *,
        reference_audio_path: Optional[Path] = None,
        model_id: str = "mock",
        speed: Optional[float] = None,
        seed: Optional[int] = None,
        settings: Optional[Dict[str, Any]] = None,
        log: Optional[logging.Logger] = None,
    ) -> Dict[str, Any]:
        # Generate silent WAV proportional to text length
        words = len(text.split())
        duration_sec = max(1.0, words / 150.0 * 60.0)  # ~150 wpm
        sample_rate = 48000
        n_samples = int(sample_rate * duration_sec)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * n_samples)

        sha1 = _file_sha1(output_path)
        if log:
            log.info(f"Mock TTS: {duration_sec:.1f}s silence → {output_path.name}")

        return {
            "provider": self.name,
            "model_id": model_id,
            "voice_id": voice_id,
            "duration_sec": round(duration_sec, 2),
            "sha1_audio": sha1,
            "sample_rate": sample_rate,
            "tts_inputs_hash": tts_input_hash(text, voice_id, self.name, model_id=model_id),
            "settings": {},
        }


# ---------------------------------------------------------------------------
# Provider registry + factory
# ---------------------------------------------------------------------------

_PROVIDERS: Dict[str, type] = {
    "elevenlabs": ElevenLabsProvider,
    "moss": MossTTSProvider,
    "moss_tts": MossTTSProvider,
    "mock": MockTTSProvider,
}


def get_provider(name: str = "") -> TTSProvider:
    """Get a TTS provider by name.

    Resolution order:
        1. Explicit name argument
        2. TTS_PROVIDER env var
        3. Default: "elevenlabs"
    """
    name = name or os.environ.get("TTS_PROVIDER", "elevenlabs")
    name = name.lower().strip()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown TTS provider: {name!r}. Available: {list(_PROVIDERS.keys())}")
    return cls()


def available_providers() -> List[str]:
    """List available provider names."""
    return list(_PROVIDERS.keys())


# ---------------------------------------------------------------------------
# TTS cache
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_DIR = Path("state/cache/tts")


def cached_synthesize(
    provider: TTSProvider,
    text: str,
    voice_id: str,
    output_path: Path,
    *,
    cache_dir: Optional[Path] = None,
    reference_audio_path: Optional[Path] = None,
    model_id: str = "",
    settings: Optional[Dict[str, Any]] = None,
    log: Optional[logging.Logger] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Synthesize with caching. Reuses cached audio if inputs match."""
    ref_sha1 = _file_sha1(reference_audio_path) if reference_audio_path and reference_audio_path.exists() else ""
    cache_key = tts_input_hash(
        text, voice_id, provider.name,
        reference_audio_sha1=ref_sha1,
        model_id=model_id, settings=settings,
    )

    cache_root = cache_dir or _DEFAULT_CACHE_DIR
    cache_root.mkdir(parents=True, exist_ok=True)

    # Determine cached file extension from output_path
    ext = output_path.suffix or ".wav"
    cached_path = cache_root / f"{cache_key}{ext}"

    if cached_path.exists():
        # Cache hit — copy to output
        import shutil
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached_path, output_path)
        sha1 = _file_sha1(output_path)
        if log:
            log.info(f"TTS cache hit: {cache_key} → {output_path.name}")
        return {
            "provider": provider.name,
            "model_id": model_id,
            "voice_id": voice_id,
            "sha1_audio": sha1,
            "tts_inputs_hash": cache_key,
            "cache_hit": True,
            "settings": settings or {},
        }

    # Cache miss — synthesize
    result = provider.synthesize(
        text, voice_id, output_path,
        reference_audio_path=reference_audio_path,
        model_id=model_id, settings=settings, log=log, **kwargs,
    )
    result["cache_hit"] = False

    # Store in cache
    try:
        import shutil
        shutil.copy2(output_path, cached_path)
    except OSError:
        pass  # non-critical: cache write failure is OK

    return result


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

def synthesize_with_fallback(
    text: str,
    voice_id: str,
    output_path: Path,
    *,
    primary: str = "",
    fallback: str = "elevenlabs",
    log: Optional[logging.Logger] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Try primary provider, fall back to secondary on failure."""
    primary_name = primary or os.environ.get("TTS_PROVIDER", "elevenlabs")

    try:
        provider = get_provider(primary_name)
        return provider.synthesize(text, voice_id, output_path, log=log, **kwargs)
    except Exception as e:
        if log:
            log.warning(f"Primary TTS ({primary_name}) failed: {e}. Falling back to {fallback}.")
        if primary_name == fallback:
            raise
        fb_provider = get_provider(fallback)
        result = fb_provider.synthesize(text, voice_id, output_path, log=log, **kwargs)
        result["fallback_used"] = True
        result["primary_error"] = str(e)
        return result
