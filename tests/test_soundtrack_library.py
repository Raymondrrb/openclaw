#!/usr/bin/env python3
"""Tests for rayvault/soundtrack_library.py — licensed music track management."""

from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from rayvault.io import sha1_file, wav_duration_seconds
from rayvault.soundtrack_library import (
    AUDIO_EXTENSIONS,
    SoundtrackLibrary,
    TrackInfo,
    _REQUIRED_META_KEYS,
    _VALID_TIERS,
    validate_track_meta,
)


def _make_wav(path: Path, duration_sec: float = 2.0, rate: int = 44100) -> str:
    """Create a minimal WAV file and return its sha1."""
    n_frames = int(rate * duration_sec)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return sha1_file(path)


def _make_track_dir(
    lib_dir: Path,
    track_id: str,
    tier: str = "GREEN",
    duration: float = 30.0,
    mood_tags: list | None = None,
    bpm: float | None = None,
    motif_group: str = "",
    include_proof: bool = True,
) -> Path:
    """Create a complete track directory with audio and metadata."""
    d = lib_dir / track_id
    d.mkdir(parents=True, exist_ok=True)
    audio = d / "audio.wav"
    sha = _make_wav(audio, duration)

    meta = {
        "track_id": track_id,
        "title": f"Track {track_id}",
        "sha1": sha,
        "license_tier": tier,
        "mood_tags": mood_tags or [],
        "bpm": bpm,
        "motif_group": motif_group,
        "source": "test",
    }

    if tier == "GREEN" and include_proof:
        proof = d / "license.pdf"
        proof.write_bytes(b"%PDF-stub")
        meta["license_proof_path"] = "license.pdf"

    (d / "track_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_audio_extensions(self):
        self.assertIn(".wav", AUDIO_EXTENSIONS)
        self.assertIn(".aif", AUDIO_EXTENSIONS)

    def test_required_keys(self):
        self.assertIn("track_id", _REQUIRED_META_KEYS)
        self.assertIn("sha1", _REQUIRED_META_KEYS)
        self.assertIn("license_tier", _REQUIRED_META_KEYS)

    def test_valid_tiers(self):
        self.assertEqual(_VALID_TIERS, {"GREEN", "AMBER", "RED"})


# ---------------------------------------------------------------
# sha1_file / wav_duration
# ---------------------------------------------------------------

class TestSha1File(unittest.TestCase):

    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"test data")
            p = Path(f.name)
        try:
            self.assertEqual(sha1_file(p), sha1_file(p))
        finally:
            p.unlink()


class TestWavDuration(unittest.TestCase):

    def test_valid_wav(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            p = Path(f.name)
        _make_wav(p, 2.0)
        try:
            d = wav_duration_seconds(p)
            self.assertIsNotNone(d)
            self.assertAlmostEqual(d, 2.0, places=1)
        finally:
            p.unlink()

    def test_invalid_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(b"not a wav")
            p = Path(f.name)
        try:
            self.assertIsNone(wav_duration_seconds(p))
        finally:
            p.unlink()

    def test_nonexistent(self):
        self.assertIsNone(wav_duration_seconds(Path("/nonexistent.wav")))


# ---------------------------------------------------------------
# TrackInfo
# ---------------------------------------------------------------

class TestTrackInfo(unittest.TestCase):

    def test_defaults(self):
        t = TrackInfo(
            track_id="T1", title="Test", duration_sec=30.0,
            mood_tags=["upbeat"], license_tier="GREEN",
            audio_path=Path("audio.wav"), sha1="abc",
        )
        self.assertTrue(t.valid)
        self.assertEqual(t.errors, [])
        self.assertIsNone(t.bpm)
        self.assertEqual(t.motif_group, "")


# ---------------------------------------------------------------
# validate_track_meta
# ---------------------------------------------------------------

class TestValidateTrackMeta(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.lib = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_valid_green(self):
        d = _make_track_dir(self.lib, "T_GREEN", tier="GREEN")
        meta = json.loads((d / "track_meta.json").read_text())
        info = validate_track_meta(meta, d)
        self.assertTrue(info.valid)
        self.assertEqual(info.license_tier, "GREEN")

    def test_valid_amber(self):
        d = _make_track_dir(self.lib, "T_AMBER", tier="AMBER")
        meta = json.loads((d / "track_meta.json").read_text())
        info = validate_track_meta(meta, d)
        self.assertTrue(info.valid)

    def test_valid_red(self):
        d = _make_track_dir(self.lib, "T_RED", tier="RED")
        meta = json.loads((d / "track_meta.json").read_text())
        info = validate_track_meta(meta, d)
        self.assertTrue(info.valid)

    def test_invalid_tier(self):
        d = self.lib / "T_BAD"
        d.mkdir()
        _make_wav(d / "audio.wav")
        meta = {"track_id": "T_BAD", "sha1": sha1_file(d / "audio.wav"), "license_tier": "UNKNOWN"}
        info = validate_track_meta(meta, d)
        self.assertFalse(info.valid)
        self.assertTrue(any("invalid license_tier" in e for e in info.errors))

    def test_missing_keys(self):
        d = self.lib / "T_EMPTY"
        d.mkdir()
        _make_wav(d / "audio.wav")
        info = validate_track_meta({}, d)
        self.assertFalse(info.valid)

    def test_green_no_proof_fails(self):
        d = self.lib / "T_NOPROOF"
        d.mkdir()
        sha = _make_wav(d / "audio.wav")
        meta = {"track_id": "T_NOPROOF", "sha1": sha, "license_tier": "GREEN"}
        info = validate_track_meta(meta, d)
        self.assertFalse(info.valid)
        self.assertTrue(any("license_proof_path" in e for e in info.errors))

    def test_no_audio_file(self):
        d = self.lib / "T_NOAUDIO"
        d.mkdir()
        meta = {"track_id": "T_NOAUDIO", "sha1": "abc", "license_tier": "AMBER"}
        info = validate_track_meta(meta, d)
        self.assertFalse(info.valid)
        self.assertTrue(any("no audio file" in e for e in info.errors))

    def test_sha1_mismatch(self):
        d = self.lib / "T_SHAMIS"
        d.mkdir()
        _make_wav(d / "audio.wav")
        meta = {"track_id": "T_SHAMIS", "sha1": "0" * 40, "license_tier": "AMBER"}
        info = validate_track_meta(meta, d)
        self.assertFalse(info.valid)
        self.assertTrue(any("sha1 mismatch" in e for e in info.errors))


# ---------------------------------------------------------------
# SoundtrackLibrary — scan
# ---------------------------------------------------------------

class TestSoundtrackLibraryScan(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.lib_dir = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_empty_dir(self):
        lib = SoundtrackLibrary(self.lib_dir)
        self.assertEqual(lib.scan(), [])

    def test_nonexistent_dir(self):
        lib = SoundtrackLibrary(self.lib_dir / "nope")
        self.assertEqual(lib.scan(), [])

    def test_discovers_tracks(self):
        _make_track_dir(self.lib_dir, "T1", tier="AMBER")
        _make_track_dir(self.lib_dir, "T2", tier="RED")
        lib = SoundtrackLibrary(self.lib_dir)
        tracks = lib.scan()
        self.assertEqual(len(tracks), 2)
        ids = {t.track_id for t in tracks}
        self.assertEqual(ids, {"T1", "T2"})

    def test_corrupt_meta(self):
        d = self.lib_dir / "T_CORRUPT"
        d.mkdir()
        (d / "track_meta.json").write_text("not json", encoding="utf-8")
        lib = SoundtrackLibrary(self.lib_dir)
        tracks = lib.scan()
        self.assertEqual(len(tracks), 1)
        self.assertFalse(tracks[0].valid)


# ---------------------------------------------------------------
# SoundtrackLibrary — query
# ---------------------------------------------------------------

class TestSoundtrackLibraryQuery(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.lib_dir = Path(self._tmpdir)
        _make_track_dir(self.lib_dir, "G1", tier="GREEN", mood_tags=["upbeat", "energetic"])
        _make_track_dir(self.lib_dir, "G2", tier="GREEN", mood_tags=["calm"])
        _make_track_dir(self.lib_dir, "A1", tier="AMBER", mood_tags=["upbeat"])
        _make_track_dir(self.lib_dir, "R1", tier="RED", mood_tags=["dark"])
        self.lib = SoundtrackLibrary(self.lib_dir)
        self.lib.scan()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_all_valid(self):
        results = self.lib.query()
        self.assertEqual(len(results), 4)

    def test_filter_by_tier(self):
        results = self.lib.query(license_tiers={"GREEN"})
        self.assertEqual(len(results), 2)
        for t in results:
            self.assertEqual(t.license_tier, "GREEN")

    def test_exclude_ids(self):
        results = self.lib.query(exclude_ids={"G1"})
        ids = {t.track_id for t in results}
        self.assertNotIn("G1", ids)

    def test_mood_sorting(self):
        results = self.lib.query(mood_tags={"upbeat"})
        # Tracks with "upbeat" should be first
        self.assertIn(results[0].track_id, {"G1", "A1"})

    def test_exclude_motif_groups(self):
        _make_track_dir(self.lib_dir, "M1", tier="AMBER", motif_group="chill")
        self.lib.scan()
        results = self.lib.query(exclude_motif_groups={"chill"})
        ids = {t.track_id for t in results}
        self.assertNotIn("M1", ids)


# ---------------------------------------------------------------
# SoundtrackLibrary — get_track
# ---------------------------------------------------------------

class TestSoundtrackLibraryGetTrack(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.lib_dir = Path(self._tmpdir)
        _make_track_dir(self.lib_dir, "T1", tier="AMBER")
        self.lib = SoundtrackLibrary(self.lib_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_found(self):
        t = self.lib.get_track("T1")
        self.assertIsNotNone(t)
        self.assertEqual(t.track_id, "T1")

    def test_not_found(self):
        t = self.lib.get_track("NOPE")
        self.assertIsNone(t)


# ---------------------------------------------------------------
# SoundtrackLibrary — verify_integrity
# ---------------------------------------------------------------

class TestSoundtrackLibraryVerifyIntegrity(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.lib_dir = Path(self._tmpdir)
        _make_track_dir(self.lib_dir, "T1", tier="AMBER")
        self.lib = SoundtrackLibrary(self.lib_dir)
        self.lib.scan()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_valid(self):
        self.assertTrue(self.lib.verify_integrity("T1"))

    def test_missing_track(self):
        self.assertFalse(self.lib.verify_integrity("NOPE"))


if __name__ == "__main__":
    unittest.main()
