"""RayVault Soundtrack Policy — enforce license tiers and produce SoundtrackDecision.

License tiers:
  GREEN  — proof-of-license, auto-publish OK
  AMBER  — rights uncertain, BLOCKED_FOR_REVIEW
  RED    — no license proof, MANUAL_ONLY

Broadcast hardening features:
  - Motif group cooldown (avoid same feel across runs)
  - Safety jitter for AMBER (anti-Content-ID false positive)
  - AI Music Editor proof (before/after duration measurement)
  - Chapter gain jitter (deterministic per seed)
  - Conformed track cache

Usage:
    from rayvault.soundtrack_policy import decide_soundtrack
    decision = decide_soundtrack(manifest, render_config, library)
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from rayvault.policies import (
    SOUNDTRACK_MUSIC_GAIN_DB,
    SOUNDTRACK_DUCK_AMOUNT_DB,
    SOUNDTRACK_DUCK_ATTACK_MS,
    SOUNDTRACK_DUCK_RELEASE_MS,
    SOUNDTRACK_CROSSFADE_IN_SEC,
    SOUNDTRACK_CROSSFADE_OUT_SEC,
    SOUNDTRACK_LOOP_CROSSFADE_SEC,
    SOUNDTRACK_CHAPTER_GAIN_JITTER_DB,
    SOUNDTRACK_MAX_LOOP_RATIO,
    SOUNDTRACK_MIN_VIDEO_SEC,
    SOUNDTRACK_AI_EDITOR_EPS_SEC,
    SOUNDTRACK_TRACK_COOLDOWN_RUNS,
    SOUNDTRACK_MOTIF_COOLDOWN_RUNS,
    SAFETY_JITTER_PITCH_RATIO,
    SAFETY_JITTER_TEMPO_RATIO,
    CONFORM_CACHE_DIR,
)
from rayvault.soundtrack_library import SoundtrackLibrary, TrackInfo


# ---------------------------------------------------------------------------
# SoundtrackDecision
# ---------------------------------------------------------------------------


@dataclass
class SoundtrackDecision:
    enabled: bool
    track_id: str = ""
    audio_path: str = ""
    license_tier: str = ""
    track_sha1: str = ""
    bpm: Optional[float] = None
    motif_group: str = ""
    source: str = ""
    target_duration_sec: float = 0.0
    track_duration_sec: float = 0.0
    loop_count: int = 1
    loop_warning: str = ""
    gain_db: float = SOUNDTRACK_MUSIC_GAIN_DB
    ducking: Dict[str, Any] = field(default_factory=dict)
    fades: Dict[str, float] = field(default_factory=dict)
    fallback_plan: str = ""
    chapter_gain_jitter: List[Dict[str, Any]] = field(default_factory=list)
    safety_jitter: Dict[str, Any] = field(default_factory=dict)
    ai_music_editor: Dict[str, Any] = field(default_factory=dict)
    conform_cache_key: str = ""
    tools_requested: List[str] = field(default_factory=list)
    publish_policy: str = ""
    skip_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "track_id": self.track_id,
            "audio_path": self.audio_path,
            "license_tier": self.license_tier,
            "track_sha1": self.track_sha1,
            "bpm": self.bpm,
            "motif_group": self.motif_group,
            "source": self.source,
            "target_duration_sec": self.target_duration_sec,
            "track_duration_sec": self.track_duration_sec,
            "loop_count": self.loop_count,
            "loop_warning": self.loop_warning,
            "gain_db": self.gain_db,
            "ducking": self.ducking,
            "fades": self.fades,
            "fallback_plan": self.fallback_plan,
            "chapter_gain_jitter": self.chapter_gain_jitter,
            "safety_jitter": self.safety_jitter,
            "ai_music_editor": self.ai_music_editor,
            "conform_cache_key": self.conform_cache_key,
            "tools_requested": self.tools_requested,
            "publish_policy": self.publish_policy,
            "skip_reason": self.skip_reason,
        }


# ---------------------------------------------------------------------------
# Publish policy
# ---------------------------------------------------------------------------


def publish_policy_for_tier(tier: str) -> str:
    """Return publish policy string for a license tier."""
    if tier == "GREEN":
        return "AUTO_PUBLISH"
    if tier == "AMBER":
        return "BLOCKED_FOR_REVIEW"
    return "MANUAL_ONLY"  # RED


# ---------------------------------------------------------------------------
# Cooldown (track_id + motif_group)
# ---------------------------------------------------------------------------


def collect_recent_track_ids(
    runs_dir: Path,
    max_runs: int = SOUNDTRACK_TRACK_COOLDOWN_RUNS,
) -> Set[str]:
    """Scan recent run manifests to find recently used track IDs."""
    used: Set[str] = set()
    if not runs_dir.is_dir():
        return used

    run_dirs = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir()),
        reverse=True,
    )

    for rd in run_dirs[:max_runs]:
        manifest_path = rd / "00_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            st = m.get("audio", {}).get("soundtrack", {})
            tid = st.get("track_id", "")
            if tid:
                used.add(tid)
        except Exception:
            continue

    return used


def collect_recent_motif_groups(
    runs_dir: Path,
    max_runs: int = SOUNDTRACK_MOTIF_COOLDOWN_RUNS,
) -> Set[str]:
    """Scan recent run manifests to find recently used motif groups."""
    used: Set[str] = set()
    if not runs_dir.is_dir():
        return used

    run_dirs = sorted(
        (d for d in runs_dir.iterdir() if d.is_dir()),
        reverse=True,
    )

    for rd in run_dirs[:max_runs]:
        manifest_path = rd / "00_manifest.json"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            st = m.get("audio", {}).get("soundtrack", {})
            mg = st.get("motif_group", "")
            if mg:
                used.add(mg)
        except Exception:
            continue

    return used


# ---------------------------------------------------------------------------
# Safety jitter (AMBER only)
# ---------------------------------------------------------------------------


def compute_safety_jitter(tier: str) -> Dict[str, Any]:
    """Compute safety jitter params for AMBER tier.

    Applied ONLY when tier==AMBER (AI-generated / uncertain rights).
    Imperceptible pitch/tempo shift to reduce Content ID false positives.
    """
    if tier != "AMBER":
        return {"applied": False, "reason": f"tier={tier}, jitter only for AMBER"}

    return {
        "applied": True,
        "pitch_ratio": SAFETY_JITTER_PITCH_RATIO,
        "tempo_ratio": SAFETY_JITTER_TEMPO_RATIO,
        "description": "micro-jitter: pitch -0.05%, tempo +0.1%",
    }


# ---------------------------------------------------------------------------
# Chapter gain jitter (deterministic)
# ---------------------------------------------------------------------------


def compute_chapter_gain_jitter(
    run_id: str,
    track_id: str,
    chapters: List[Dict[str, Any]],
    jitter_db: float = SOUNDTRACK_CHAPTER_GAIN_JITTER_DB,
) -> List[Dict[str, Any]]:
    """Compute per-chapter gain jitter, deterministic by seed.

    Each chapter gets a small gain variation (+-jitter_db) seeded by
    sha1(run_id + track_id + chapter_id) for reproducibility.
    """
    result = []
    for ch in chapters:
        ch_id = ch.get("id", ch.get("type", "unknown"))
        seed = hashlib.sha1(
            f"{run_id}:{track_id}:{ch_id}".encode()
        ).hexdigest()[:8]
        # Map to [-jitter_db, +jitter_db]
        val = int(seed, 16) / 0xFFFFFFFF  # 0.0 to 1.0
        jitter = (val * 2 - 1) * jitter_db
        result.append({
            "chapter_id": ch_id,
            "gain_offset_db": round(jitter, 2),
            "seed": seed,
        })
    return result


# ---------------------------------------------------------------------------
# AI Music Editor proof
# ---------------------------------------------------------------------------


def build_ai_music_editor_proof(
    before_duration_sec: Optional[float] = None,
    after_duration_sec: Optional[float] = None,
    target_duration_sec: float = 0.0,
    attempted: bool = False,
    eps: float = SOUNDTRACK_AI_EDITOR_EPS_SEC,
) -> Dict[str, Any]:
    """Build AI Music Editor proof structure.

    Success = abs(after - target) <= eps.
    """
    proof: Dict[str, Any] = {
        "attempted": attempted,
        "success": False,
        "before_duration_sec": before_duration_sec,
        "after_duration_sec": after_duration_sec,
        "target_duration_sec": target_duration_sec,
        "eps_sec": eps,
        "proof": None,
    }

    if attempted and after_duration_sec is not None and target_duration_sec > 0:
        diff = abs(after_duration_sec - target_duration_sec)
        proof["success"] = diff <= eps
        proof["diff_sec"] = round(diff, 3)

    return proof


# ---------------------------------------------------------------------------
# Conform cache
# ---------------------------------------------------------------------------


def conform_cache_key(
    track_sha1: str,
    target_duration_sec: float,
    bpm: Optional[float] = None,
) -> str:
    """Compute cache key for a conformed track."""
    parts = f"{track_sha1}:{target_duration_sec:.1f}"
    if bpm:
        parts += f":{bpm:.1f}"
    return hashlib.sha1(parts.encode()).hexdigest()[:16]


def lookup_conform_cache(
    cache_dir: Path,
    cache_key: str,
) -> Optional[Path]:
    """Look up a conformed track in cache. Returns path if found."""
    cached = cache_dir / f"{cache_key}.wav"
    if cached.exists():
        return cached
    return None


# ---------------------------------------------------------------------------
# Core decision
# ---------------------------------------------------------------------------


def decide_soundtrack(
    manifest: Dict[str, Any],
    render_config: Dict[str, Any],
    library: SoundtrackLibrary,
    mood_override: Optional[Set[str]] = None,
    track_override: Optional[str] = None,
    opt_out: bool = False,
    policy_allow_amber: bool = False,
    recent_track_ids: Optional[Set[str]] = None,
    recent_motif_groups: Optional[Set[str]] = None,
) -> SoundtrackDecision:
    """Decide whether and how to add a soundtrack.

    Args:
        manifest: Run manifest dict.
        render_config: Render config dict.
        library: SoundtrackLibrary instance.
        mood_override: Force specific mood tags for query.
        track_override: Force a specific track_id.
        opt_out: If True, skip soundtrack entirely.
        policy_allow_amber: Allow AMBER tracks in auto-selection.
        recent_track_ids: Track IDs to exclude (cooldown).
        recent_motif_groups: Motif groups to exclude (cooldown).
    """
    # Video duration from render_config audio block
    audio_block = render_config.get("audio", {})
    video_duration = audio_block.get("duration_sec", 0.0)
    if not video_duration:
        segments = render_config.get("segments", [])
        if segments:
            video_duration = max(s.get("t1", 0) for s in segments)

    # Opt-out
    if opt_out:
        return SoundtrackDecision(enabled=False, skip_reason="opt_out")

    # Too short
    if video_duration < SOUNDTRACK_MIN_VIDEO_SEC:
        return SoundtrackDecision(
            enabled=False,
            skip_reason=f"video_too_short ({video_duration:.1f}s < {SOUNDTRACK_MIN_VIDEO_SEC}s)",
        )

    run_id = manifest.get("run_id", "")

    # Track override
    if track_override:
        track = library.get_track(track_override)
        if not track or not track.valid:
            return SoundtrackDecision(
                enabled=False,
                skip_reason=f"track_override '{track_override}' not found or invalid",
            )
        return _build_decision(track, video_duration, run_id, render_config)

    # Query library
    tiers: Set[str] = {"GREEN"}
    if policy_allow_amber:
        tiers.add("AMBER")

    mood_tags = mood_override
    if mood_tags is None:
        meta = manifest.get("metadata", {})
        mood_tags = set(meta.get("mood_tags", []))

    candidates = library.query(
        mood_tags=mood_tags or None,
        license_tiers=tiers,
        exclude_ids=recent_track_ids,
        exclude_motif_groups=recent_motif_groups,
    )

    if not candidates:
        return SoundtrackDecision(
            enabled=False,
            skip_reason="no_eligible_tracks",
        )

    track = candidates[0]
    return _build_decision(track, video_duration, run_id, render_config)


def _build_decision(
    track: TrackInfo,
    video_duration: float,
    run_id: str = "",
    render_config: Optional[Dict[str, Any]] = None,
) -> SoundtrackDecision:
    """Build a SoundtrackDecision from a selected track."""
    loop_count = 1
    loop_warning = ""
    fallback_plan = ""

    if track.duration_sec > 0:
        ratio = video_duration / track.duration_sec
        loop_count = max(1, math.ceil(ratio))

        if ratio > SOUNDTRACK_MAX_LOOP_RATIO:
            loop_warning = (
                f"loop_ratio={ratio:.2f} exceeds max={SOUNDTRACK_MAX_LOOP_RATIO}"
            )

        if loop_count > 1:
            fallback_plan = "loop_with_crossfade"

    ducking = {
        "amount_db": SOUNDTRACK_DUCK_AMOUNT_DB,
        "attack_ms": SOUNDTRACK_DUCK_ATTACK_MS,
        "release_ms": SOUNDTRACK_DUCK_RELEASE_MS,
    }

    fades = {
        "fade_in_sec": SOUNDTRACK_CROSSFADE_IN_SEC,
        "fade_out_sec": SOUNDTRACK_CROSSFADE_OUT_SEC,
        "loop_crossfade_sec": SOUNDTRACK_LOOP_CROSSFADE_SEC,
    }

    # Safety jitter for AMBER
    safety_jitter = compute_safety_jitter(track.license_tier)

    # Chapter gain jitter (deterministic)
    chapters = (render_config or {}).get("segments", [])
    chapter_jitter = compute_chapter_gain_jitter(
        run_id, track.track_id, chapters,
    )

    # AI Music Editor proof (stub — not yet attempted)
    ai_proof = build_ai_music_editor_proof(
        before_duration_sec=track.duration_sec,
        target_duration_sec=video_duration,
        attempted=False,
    )

    # Conform cache key
    cache_key = conform_cache_key(
        track.sha1, video_duration, track.bpm,
    )

    publish_policy = publish_policy_for_tier(track.license_tier)
    tools_requested = ["ai_music_editor", "ai_audio_assistant"]

    return SoundtrackDecision(
        enabled=True,
        track_id=track.track_id,
        audio_path=str(track.audio_path),
        license_tier=track.license_tier,
        track_sha1=track.sha1,
        bpm=track.bpm,
        motif_group=track.motif_group,
        source=track.source,
        target_duration_sec=video_duration,
        track_duration_sec=track.duration_sec,
        loop_count=loop_count,
        loop_warning=loop_warning,
        gain_db=SOUNDTRACK_MUSIC_GAIN_DB,
        ducking=ducking,
        fades=fades,
        fallback_plan=fallback_plan,
        chapter_gain_jitter=chapter_jitter,
        safety_jitter=safety_jitter,
        ai_music_editor=ai_proof,
        conform_cache_key=cache_key,
        tools_requested=tools_requested,
        publish_policy=publish_policy,
    )


# ---------------------------------------------------------------------------
# Manifest integration
# ---------------------------------------------------------------------------


def write_decision_to_manifest(manifest_path: Path, decision: SoundtrackDecision) -> None:
    """Atomic write of soundtrack decision to manifest audio.soundtrack section."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    audio = manifest.setdefault("audio", {})
    audio["soundtrack"] = decision.to_dict()

    from rayvault.io import atomic_write_json
    atomic_write_json(manifest_path, manifest)
