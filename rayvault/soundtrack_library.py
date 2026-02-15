"""RayVault Soundtrack Library — manage licensed music tracks.

Manages state/library/soundtracks/<track_id>/ directories, each containing:
  - audio.wav (or .aif)
  - track_meta.json with license tier, sha1, mood tags, etc.

Usage:
    from rayvault.soundtrack_library import SoundtrackLibrary
    lib = SoundtrackLibrary(Path("state/library/soundtracks"))
    tracks = lib.scan()
    green = lib.query(license_tiers={"GREEN"})
"""

from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha1_file(path: Path) -> str:
    """Compute SHA1 hash of a file."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wav_duration(path: Path) -> Optional[float]:
    """Read WAV duration in seconds via the wave module."""
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return frames / float(rate) if rate > 0 else None
    except Exception:
        return None


AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff"}

_REQUIRED_META_KEYS = {"track_id", "sha1", "license_tier"}
_VALID_TIERS = {"GREEN", "AMBER", "RED"}


# ---------------------------------------------------------------------------
# TrackInfo
# ---------------------------------------------------------------------------


@dataclass
class TrackInfo:
    track_id: str
    title: str
    duration_sec: float
    mood_tags: List[str]
    license_tier: str
    audio_path: Path
    sha1: str
    bpm: Optional[float] = None
    motif_group: str = ""
    source: str = ""
    valid: bool = True
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_track_meta(meta: Dict[str, Any], track_dir: Path) -> TrackInfo:
    """Validate a track_meta.json and its audio file.

    Returns a TrackInfo with valid=False and errors populated on failure.
    """
    errors: List[str] = []

    # Required keys
    for key in _REQUIRED_META_KEYS:
        if key not in meta:
            errors.append(f"missing key: {key}")

    track_id = meta.get("track_id", track_dir.name)
    title = meta.get("title", track_id)
    license_tier = meta.get("license_tier", "")
    stored_sha1 = meta.get("sha1", "")
    mood_tags = meta.get("mood_tags", [])
    bpm = meta.get("bpm")
    motif_group = meta.get("motif_group", "")
    source = meta.get("source", "")

    if license_tier not in _VALID_TIERS:
        errors.append(f"invalid license_tier: {license_tier}")

    # GREEN tier requires license_proof_path with real file
    if license_tier == "GREEN":
        proof_path_rel = meta.get("license_proof_path", "")
        if not proof_path_rel:
            errors.append("GREEN tier requires license_proof_path in track_meta.json")
        else:
            proof_file = track_dir / proof_path_rel
            if not proof_file.exists():
                errors.append(f"license_proof_path not found: {proof_path_rel}")
            else:
                proof_sha1_stored = meta.get("license_proof_sha1", "")
                if proof_sha1_stored:
                    actual_proof_sha1 = sha1_file(proof_file)
                    if actual_proof_sha1 != proof_sha1_stored:
                        errors.append(
                            f"license_proof sha1 mismatch: "
                            f"stored={proof_sha1_stored[:12]}... "
                            f"actual={actual_proof_sha1[:12]}..."
                        )

    # Find audio file
    audio_path = None
    for ext in AUDIO_EXTENSIONS:
        candidate = track_dir / f"audio{ext}"
        if candidate.exists():
            audio_path = candidate
            break

    if audio_path is None:
        errors.append("no audio file found (audio.wav / audio.aif)")
        return TrackInfo(
            track_id=track_id, title=title, duration_sec=0.0,
            mood_tags=mood_tags, license_tier=license_tier,
            audio_path=track_dir / "audio.wav", sha1=stored_sha1,
            bpm=bpm, motif_group=motif_group, source=source,
            valid=False, errors=errors,
        )

    # Duration
    duration = wav_duration(audio_path)
    if duration is None:
        errors.append("cannot read audio duration")
        duration = 0.0

    # SHA1 check
    if stored_sha1:
        actual = sha1_file(audio_path)
        if actual != stored_sha1:
            errors.append(f"sha1 mismatch: stored={stored_sha1[:12]}... actual={actual[:12]}...")

    return TrackInfo(
        track_id=track_id, title=title, duration_sec=duration,
        mood_tags=mood_tags, license_tier=license_tier,
        audio_path=audio_path, sha1=stored_sha1,
        bpm=bpm, motif_group=motif_group, source=source,
        valid=len(errors) == 0, errors=errors,
    )


# ---------------------------------------------------------------------------
# SoundtrackLibrary
# ---------------------------------------------------------------------------


class SoundtrackLibrary:
    """Discover and query licensed music tracks."""

    def __init__(self, library_dir: Path):
        self.library_dir = library_dir
        self._tracks: Dict[str, TrackInfo] = {}

    def scan(self) -> List[TrackInfo]:
        """Discover and validate all tracks in the library directory."""
        self._tracks.clear()
        results: List[TrackInfo] = []

        if not self.library_dir.is_dir():
            return results

        for child in sorted(self.library_dir.iterdir()):
            if not child.is_dir():
                continue
            meta_path = child / "track_meta.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                info = TrackInfo(
                    track_id=child.name, title=child.name, duration_sec=0.0,
                    mood_tags=[], license_tier="", audio_path=child / "audio.wav",
                    sha1="", valid=False, errors=["track_meta.json unreadable"],
                )
                results.append(info)
                continue

            info = validate_track_meta(meta, child)
            self._tracks[info.track_id] = info
            results.append(info)

        return results

    def query(
        self,
        mood_tags: Optional[Set[str]] = None,
        license_tiers: Optional[Set[str]] = None,
        min_duration: Optional[float] = None,
        exclude_ids: Optional[Set[str]] = None,
        exclude_motif_groups: Optional[Set[str]] = None,
    ) -> List[TrackInfo]:
        """Filter and rank tracks. Higher mood tag overlap ranks first."""
        if not self._tracks:
            self.scan()

        results: List[TrackInfo] = []
        for t in self._tracks.values():
            if not t.valid:
                continue
            if license_tiers and t.license_tier not in license_tiers:
                continue
            if min_duration is not None and t.duration_sec < min_duration:
                continue
            if exclude_ids and t.track_id in exclude_ids:
                continue
            if exclude_motif_groups and t.motif_group in exclude_motif_groups:
                continue
            results.append(t)

        if mood_tags:
            results.sort(
                key=lambda t: len(set(t.mood_tags) & mood_tags),
                reverse=True,
            )

        return results

    def get_track(self, track_id: str) -> Optional[TrackInfo]:
        """Get a specific track by ID."""
        if not self._tracks:
            self.scan()
        return self._tracks.get(track_id)

    def verify_integrity(self, track_id: str) -> bool:
        """Recompute SHA1 and compare to stored value."""
        track = self.get_track(track_id)
        if not track or not track.audio_path.exists():
            return False
        actual = sha1_file(track.audio_path)
        return actual == track.sha1
