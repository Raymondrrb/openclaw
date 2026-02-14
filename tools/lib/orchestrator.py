"""RayVault Orchestrator — stage-based pipeline with checkpoint recovery.

Transforms validated voice scripts into rendered video through:
  VOICE_PREP → VOICE_GEN → MEDIA_SYNC → ASSEMBLY → RENDER_PROBE → DONE

Each stage writes an atomic checkpoint before advancing.
On crash/restart, resumes from the last completed stage.

Features:
  - Tone Gate 3-level auto-cutter (rate → filler → LLM repair)
  - Idempotent TTS generation (per-segment digest)
  - Media gate validation before Resolve assembly
  - run_event telemetry per stage transition
  - Integrates with PanicManager for local-first error handling

Stdlib + tools.lib only.

Usage:
    from tools.lib.orchestrator import RayVaultOrchestrator, OrchestratorConfig

    orch = RayVaultOrchestrator(config=cfg, panic_mgr=pm, tts_engine=tts)
    await orch.run(run_id="RAY-99", segments_plan=segments)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from tools.lib.audio_utils import (
    atomic_write_json,
    estimate_duration_sec,
    finalize_segment_audio,
    FinalizeResult,
    scrub_fillers,
)
from tools.lib.media_manifest import (
    has_ffprobe,
    is_video_valid,
    load_video_index,
    upsert_video_index,
)
from tools.lib.tone_gate import (
    strip_tts_tags,
    tone_gate_validate,
    ToneGateRules,
    build_tone_repair_prompt,
)


# ---------------------------------------------------------------------------
# Protocols (pluggable interfaces)
# ---------------------------------------------------------------------------

class PanicLike(Protocol):
    """Interface for panic reporting."""
    def report_panic(
        self, reason_key: str, run_id: str, error_msg: str, **kw: Any,
    ) -> None: ...


class TTSEngineLike(Protocol):
    """Interface for TTS generation."""
    def synthesize(self, *, run_id: str, text: str) -> Path: ...
    def has_artifact(self, run_id: str) -> bool: ...


class RepairEngineLike(Protocol):
    """Interface for LLM-based text repair (shorten segment)."""
    def repair_segment(
        self, *, segment_id: str, text: str, reduce_by_ms: int,
    ) -> Optional[str]:
        """Return shortened text, or None if repair failed."""
        ...


class EventSinkLike(Protocol):
    """Interface for run_event insertion (async)."""
    async def insert_run_event(self, event: dict) -> None: ...


class DzineAgentLike(Protocol):
    """Interface for Dzine UI automation (Playwright/operator).

    Contract: render must produce the mp4 at the expected_video_path.
    """
    def render_segment(
        self, *, audio_path: Path, expected_video_path: Path,
        avatar_ref: str, project_preset: str,
        lip_sync_hint: str, target_duration_sec: float,
    ) -> None:
        """Render one segment. Raises on failure."""
        ...


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DzineBudget:
    """Budget control for Dzine credits."""
    available_credits: int = 100
    cost_per_segment: int = 1
    max_dzine_attempts: int = 1


@dataclass(frozen=True)
class OrchestratorConfig:
    """Orchestrator configuration and paths."""
    state_dir: str = "state"
    checkpoints_dir: str = "state/checkpoints"
    jobs_dir: str = "state/jobs"
    audio_dir: str = "state/audio"
    video_dir: str = "state/video"
    video_final_dir: str = "state/video/final"
    video_index_path: str = "state/video/index.json"
    output_dir: str = "state/output"

    # Tone Gate tuning
    wpm: int = 165
    max_overage_ratio: float = 1.15
    rate_tweak_max_ratio: float = 1.05
    filler_scrub_max_ratio: float = 1.10
    max_repair_attempts: int = 1

    # Media Gate
    min_mp3_bytes: int = 50_000
    min_mp4_bytes: int = 1_000_000

    # Render Probe
    min_render_bytes: int = 5_000_000
    min_render_duration_sec: float = 5.0

    # Video validation (ffprobe)
    video_tolerance_sec: float = 0.15
    min_video_bytes: int = 500_000


# Stages as simple strings — deterministic ordering
STAGES = (
    "VOICE_PREP",
    "VOICE_GEN",
    "MEDIA_SYNC",
    "PREFLIGHT",
    "DZINE_RENDER",
    "ASSEMBLY",
    "RENDER_PROBE",
    "DONE",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class RayVaultOrchestrator:
    """Stage-based orchestrator with checkpoint recovery.

    Each stage is idempotent — re-running a completed stage is a no-op
    because the checkpoint advances the stage pointer forward.
    """

    def __init__(
        self,
        *,
        config: OrchestratorConfig = OrchestratorConfig(),
        panic_mgr: PanicLike,
        tts_engine: Optional[TTSEngineLike] = None,
        repair_engine: Optional[RepairEngineLike] = None,
        dzine_agent: Optional[DzineAgentLike] = None,
        dzine_budget: Optional[DzineBudget] = None,
        event_sink: Optional[EventSinkLike] = None,
        resolve_script: str = "scripts/resolve_assemble.py",
        render_probe_script: str = "scripts/render_probe.py",
    ):
        self.cfg = config
        self.panic = panic_mgr
        self.tts = tts_engine
        self.repair = repair_engine
        self.dzine = dzine_agent
        self.budget = dzine_budget or DzineBudget()
        self.events = event_sink
        self.resolve_script = resolve_script
        self.render_probe_script = render_probe_script

        self._check_dir = Path(config.checkpoints_dir)
        self._jobs_dir = Path(config.jobs_dir)
        self._audio_dir = Path(config.audio_dir)
        self._video_dir = Path(config.video_dir)
        self._video_final_dir = Path(config.video_final_dir)
        self._video_index_path = Path(config.video_index_path)
        self._output_dir = Path(config.output_dir)

        # Ensure directories exist
        for d in (self._check_dir, self._jobs_dir, self._audio_dir,
                  self._output_dir, self._video_final_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Checkpoint management
    # ------------------------------------------------------------------

    def checkpoint_path(self, run_id: str) -> Path:
        return self._check_dir / f"{run_id}.json"

    def load_checkpoint(self, run_id: str) -> dict:
        """Load checkpoint or create initial state."""
        cp = _read_json(self.checkpoint_path(run_id))
        if not cp:
            return {
                "run_id": run_id,
                "stage": "VOICE_PREP",
                "updated_at": _utcnow_iso(),
                "data": {},
            }
        return cp

    def save_checkpoint(self, run_id: str, stage: str, data: dict) -> None:
        """Atomically save checkpoint for a stage."""
        cp = {
            "run_id": run_id,
            "stage": stage,
            "updated_at": _utcnow_iso(),
            "data": data,
        }
        atomic_write_json(self.checkpoint_path(run_id), cp)

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def _emit(
        self, run_id: str, event_type: str, severity: str, payload: dict,
    ) -> None:
        """Emit a run_event (best-effort, never blocks pipeline)."""
        if not self.events:
            return
        event = {
            "event_id": _sha256(
                json.dumps({"r": run_id, "t": event_type, "p": payload}, sort_keys=True)
            )[:32],
            "run_id": run_id,
            "event_type": event_type,
            "severity": severity,
            "occurred_at": _utcnow_iso(),
            "payload": payload,
        }
        try:
            await self.events.insert_run_event(event)
        except Exception:
            pass  # Best effort — spool catches failures elsewhere

    # ------------------------------------------------------------------
    # Stage: VOICE_PREP (Tone Gate 3-level auto-cutter)
    # ------------------------------------------------------------------

    def voice_prep(
        self, segments: List[dict], lang: str = "en",
    ) -> List[dict]:
        """Apply Tone Gate: rate tweak → filler scrub → mark for repair.

        Returns new list with tone_gate metadata and needs_repair flags.
        """
        fixed: List[dict] = []

        for s in segments:
            s2 = dict(s)
            text = s2.get("text", "")
            approx = _safe_float(s2.get("approx_duration_sec", 0))

            if not text:
                s2["needs_repair"] = True
                s2["tone_gate"] = {"reason": "empty_text"}
                fixed.append(s2)
                continue

            est = estimate_duration_sec(text, wpm=self.cfg.wpm)
            ratio = (est / approx) if approx > 0 else 1.0

            # Level A: Rate tweak (free — just inject TTS speed hint)
            if 0 < approx and ratio <= self.cfg.rate_tweak_max_ratio:
                s2.setdefault("tts_hints", {})
                s2["tts_hints"]["rate"] = round(ratio, 3)
                s2["tone_gate"] = {
                    "est_sec": round(est, 2), "approx_sec": approx,
                    "ratio": round(ratio, 3), "action": "rate_tweak",
                }
                fixed.append(s2)
                continue

            # Level B: Filler scrub (free — regex, deterministic)
            if 0 < approx and ratio <= self.cfg.filler_scrub_max_ratio:
                s2["text"] = scrub_fillers(text, lang=lang)
                est2 = estimate_duration_sec(s2["text"], wpm=self.cfg.wpm)
                ratio2 = (est2 / approx) if approx > 0 else 1.0
                s2["tone_gate"] = {
                    "est_sec": round(est2, 2), "approx_sec": approx,
                    "ratio": round(ratio2, 3), "action": "filler_scrub",
                }
                # If still over after scrub, mark for repair
                if ratio2 > self.cfg.max_overage_ratio:
                    s2["needs_repair"] = True
                fixed.append(s2)
                continue

            # Level C: Mark for LLM repair (expensive — done in next step)
            if 0 < approx and ratio > self.cfg.max_overage_ratio:
                s2["needs_repair"] = True
                s2["tone_gate"] = {
                    "est_sec": round(est, 2), "approx_sec": approx,
                    "ratio": round(ratio, 3), "action": "needs_repair",
                }
            else:
                s2["tone_gate"] = {
                    "est_sec": round(est, 2), "approx_sec": approx,
                    "ratio": round(ratio, 3), "action": "ok",
                }
            fixed.append(s2)

        return fixed

    # ------------------------------------------------------------------
    # Stage: VOICE_GEN (TTS → finalize gate → repair loop)
    # ------------------------------------------------------------------

    def voice_gen(self, run_id: str, segments: List[dict]) -> List[dict]:
        """Generate audio for each segment with smart finalize gate.

        Per-segment flow:
        1. Skip needs_repair/needs_human segments
        2. Synthesize TTS (idempotent via has_artifact)
        3. Run finalize gate → FinalizeResult with 4 possible actions:
           - ok/pad_silence/rate_tweak: audio is ready for Dzine
           - needs_repair: flag segment for LLM text patch (pre-Dzine)
        4. Store finalize_result metadata per segment for telemetry

        Dzine only gets segments where finalize.action != needs_repair.
        """
        if not self.tts:
            return [
                {**s, "audio_path": None, "needs_human": True}
                for s in segments
            ]

        out: List[dict] = []
        for i, s in enumerate(segments):
            s2 = dict(s)

            if s2.get("needs_repair") or s2.get("needs_human"):
                s2["audio_path"] = None
                out.append(s2)
                continue

            text = s2.get("text", "")
            if not text:
                s2["audio_path"] = None
                s2["needs_human"] = True
                out.append(s2)
                continue

            # Apply rate hint as TTS tag
            rate = None
            if isinstance(s2.get("tts_hints"), dict):
                rate = s2["tts_hints"].get("rate")
            tts_text = f"[rate={rate}] {text}" if rate else text

            seg_id = s2.get("segment_id", f"seg_{i}")
            artifact_id = f"{run_id}_{seg_id}"

            # Idempotency check
            if self.tts.has_artifact(artifact_id):
                audio_dir = Path(self.tts.cfg.output_dir) if hasattr(self.tts, 'cfg') else self._audio_dir
                s2["audio_path"] = str(audio_dir / f"{artifact_id}.mp3")
                out.append(s2)
                continue

            try:
                audio_path = self.tts.synthesize(
                    run_id=artifact_id, text=tts_text,
                )
                s2["audio_path"] = str(audio_path)

                # Smart finalize gate
                approx = _safe_float(s2.get("approx_duration_sec", 0))
                kind = s2.get("kind", "product")
                if approx > 0:
                    fr = finalize_segment_audio(
                        audio_path,
                        target_duration=approx,
                        source_text=text,
                        kind=kind,
                    )
                    s2["finalize_result"] = {
                        "action": fr.action,
                        "delta_ms": fr.delta_ms,
                        "measured_sec": round(fr.measured_duration_sec, 3),
                        "target_sec": fr.target_duration_sec,
                        "rate": fr.rate,
                        "reason": fr.reason,
                    }

                    if fr.action == "needs_repair":
                        s2["needs_repair"] = True
                        s2["repair_reason"] = fr.reason

            except Exception as e:
                s2["audio_path"] = None
                s2["tts_error"] = str(e)[:300]
                s2["needs_human"] = True

            out.append(s2)

        return out

    # ------------------------------------------------------------------
    # Repair loop: TTS → finalize → (repair if needed) → re-TTS
    # ------------------------------------------------------------------

    _SAFETY_MS = 250  # extra buffer on repair prompt

    def voice_gen_with_repair(
        self, run_id: str, segments: List[dict],
    ) -> List[dict]:
        """TTS → finalize gate → repair loop (max attempts).

        For each segment that comes back as needs_repair:
        1. Calculate reduce_by_ms = over_ms + safety (250ms)
        2. Call repair_engine to shorten text
        3. Re-synthesize + re-finalize
        4. If still needs_repair after max attempts → panic

        Requires repair_engine. Without it, behaves like voice_gen.
        """
        segs = self.voice_gen(run_id, segments)

        if not self.repair or not self.tts:
            return segs

        max_attempts = self.cfg.max_repair_attempts
        out: List[dict] = []

        for s in segs:
            if not s.get("needs_repair") or not s.get("finalize_result"):
                out.append(s)
                continue

            seg_id = s.get("segment_id", "?")
            text = s.get("text", "")
            approx = _safe_float(s.get("approx_duration_sec", 0))
            kind = s.get("kind", "product")

            repaired = False
            for attempt in range(1, max_attempts + 1):
                fr = s.get("finalize_result", {})
                over_ms = abs(fr.get("delta_ms", 0))
                reduce_by_ms = over_ms + self._SAFETY_MS

                # Ask LLM to shorten
                new_text = self.repair.repair_segment(
                    segment_id=seg_id,
                    text=text,
                    reduce_by_ms=reduce_by_ms,
                )
                if not new_text:
                    break

                # Re-synthesize with repaired text
                artifact_id = f"{run_id}_{seg_id}_r{attempt}"
                try:
                    audio_path = self.tts.synthesize(
                        run_id=artifact_id, text=new_text,
                    )
                except Exception as e:
                    s["tts_error"] = f"repair attempt {attempt}: {e}"
                    break

                # Re-finalize
                if approx > 0:
                    fr_new = finalize_segment_audio(
                        audio_path, target_duration=approx,
                        source_text=new_text, kind=kind,
                    )
                    s["finalize_result"] = {
                        "action": fr_new.action,
                        "delta_ms": fr_new.delta_ms,
                        "measured_sec": round(fr_new.measured_duration_sec, 3),
                        "target_sec": fr_new.target_duration_sec,
                        "rate": fr_new.rate,
                        "reason": fr_new.reason,
                    }

                    if fr_new.action != "needs_repair":
                        s["audio_path"] = str(audio_path)
                        s["text"] = new_text
                        s["repair_attempts"] = attempt
                        s.pop("needs_repair", None)
                        s.pop("repair_reason", None)
                        repaired = True
                        break

                    text = new_text  # use repaired text for next attempt

            if not repaired and s.get("needs_repair"):
                s["needs_human"] = True
                s["repair_exhausted"] = True
                self.panic.report_panic(
                    "panic_voice_contract_drift", run_id,
                    f"segment {seg_id}: repair exhausted after "
                    f"{max_attempts} attempts, still over by "
                    f"{abs(s.get('finalize_result', {}).get('delta_ms', 0))}ms",
                )

            out.append(s)

        return out

    # ------------------------------------------------------------------
    # Stage: MEDIA_SYNC (build manifest)
    # ------------------------------------------------------------------

    def build_manifest(self, run_id: str, segments: List[dict]) -> Path:
        """Build media manifest — single source of truth for assembly."""
        manifest = {
            "manifest_version": "1.0",
            "run_id": run_id,
            "created_at": _utcnow_iso(),
            "segments": [],
        }

        for s in segments:
            seg_id = s.get("segment_id", "seg")
            manifest["segments"].append({
                "segment_id": seg_id,
                "kind": s.get("kind", ""),
                "slot": s.get("slot", ""),
                "lip_sync_hint": s.get("lip_sync_hint", "neutral"),
                "approx_duration_sec": s.get("approx_duration_sec", 0),
                "audio_path": s.get("audio_path"),
                "video_path": s.get("video_path", str(self._video_dir / f"{seg_id}.mp4")),
            })

        path = self._jobs_dir / f"media_manifest_{run_id}.json"
        atomic_write_json(path, manifest)
        return path

    # ------------------------------------------------------------------
    # Stage: PREFLIGHT (GO/NO_GO before spending Dzine credits)
    # ------------------------------------------------------------------

    def preflight(self, manifest_path: Path) -> Dict[str, Any]:
        """Pre-flight check: budget, probe tools, cache hits.

        Returns preflight dict with status GO/NO_GO.
        Raises RuntimeError if NO_GO (fail-fast, zero credits spent).
        """
        m = _read_json(manifest_path)
        if not m or "segments" not in m:
            raise RuntimeError("PREFLIGHT_FAIL: invalid manifest")

        segments = m.get("segments", [])
        cache_hits = 0
        needs_render: List[str] = []
        probe_available = has_ffprobe()

        for seg in segments:
            video_path_str = seg.get("video_path", "")
            target_sec = _safe_float(seg.get("approx_duration_sec", 0))
            seg_id = seg.get("segment_id", "?")

            if video_path_str and probe_available:
                ok, dur = is_video_valid(
                    Path(video_path_str), target_sec,
                    tolerance_sec=self.cfg.video_tolerance_sec,
                    min_bytes=self.cfg.min_video_bytes,
                )
                if ok:
                    cache_hits += 1
                    continue

            needs_render.append(seg_id)

        credits_needed = len(needs_render) * self.budget.cost_per_segment
        go = credits_needed <= self.budget.available_credits

        # If ffprobe is unavailable and there are segments to render,
        # refuse to proceed — can't validate output
        if not probe_available and needs_render:
            go = False

        pf = {
            "run_id": m.get("run_id", "?"),
            "total_segments": len(segments),
            "cache_hits": cache_hits,
            "needs_render": needs_render,
            "credits_needed": credits_needed,
            "credits_available": self.budget.available_credits,
            "probe_available": probe_available,
            "status": "GO" if go else "NO_GO",
        }

        if not go:
            reason = "insufficient credits" if probe_available else "ffprobe not available"
            raise RuntimeError(
                f"PREFLIGHT_NO_GO: {reason} "
                f"(need {credits_needed}, have {self.budget.available_credits})"
            )

        return pf

    # ------------------------------------------------------------------
    # Stage: DZINE_RENDER (per-segment lip-sync with fail-fast)
    # ------------------------------------------------------------------

    def dzine_render(
        self, run_id: str, manifest_path: Path,
    ) -> Dict[str, Any]:
        """Render segments via Dzine UI agent with fail-fast protection.

        For each segment not cached:
        1. Check local cache (SKIP_DZINE if valid video exists)
        2. Render via Dzine agent (max attempts per segment)
        3. Post-render probe (ffprobe duration + size)
        4. Index validated video atomically
        5. ABORT on first failure (capital protection)

        Returns summary dict. Raises RuntimeError on any failure.
        """
        m = _read_json(manifest_path)
        if not m:
            raise RuntimeError("DZINE_RENDER_FAIL: manifest not found")

        segments = m.get("segments", [])
        rendered = 0
        skipped = 0

        for seg in segments:
            seg_id = seg.get("segment_id", "?")
            video_path_str = seg.get("video_path", "")
            audio_path_str = seg.get("audio_path", "")
            target_sec = _safe_float(seg.get("approx_duration_sec", 0))

            if not video_path_str or not audio_path_str:
                continue

            video_path = Path(video_path_str)

            # Cache hit: skip
            ok, dur = is_video_valid(
                video_path, target_sec,
                tolerance_sec=self.cfg.video_tolerance_sec,
                min_bytes=self.cfg.min_video_bytes,
            )
            if ok:
                self._index_video(
                    run_id, seg_id, video_path, dur,
                    seg.get("audio_sha256", "")[:8], "skip_cache_hit",
                )
                skipped += 1
                continue

            # No Dzine agent → mark incomplete
            if not self.dzine:
                raise RuntimeError(
                    f"DZINE_RENDER_FAIL: no dzine_agent for segment {seg_id}"
                )

            # Attempt render (capped at max_dzine_attempts)
            dzine_block = seg.get("dzine", {})
            upload = dzine_block.get("upload", {})
            settings = dzine_block.get("settings", {})

            try:
                self.dzine.render_segment(
                    audio_path=Path(audio_path_str),
                    expected_video_path=video_path,
                    avatar_ref=upload.get("avatar_ref", ""),
                    project_preset=upload.get("project_preset", ""),
                    lip_sync_hint=settings.get("lip_sync_hint", "neutral"),
                    target_duration_sec=target_sec,
                )
            except Exception as e:
                self.panic.report_panic(
                    "panic_dzine_ui_failure", run_id,
                    f"segment {seg_id}: {e}",
                )
                raise RuntimeError(
                    f"DZINE_RENDER_FAIL: UI failure on {seg_id}: {str(e)[:300]}"
                )

            # Post-render probe
            ok2, dur2 = is_video_valid(
                video_path, target_sec,
                tolerance_sec=self.cfg.video_tolerance_sec,
                min_bytes=self.cfg.min_video_bytes,
            )
            if not ok2:
                self.panic.report_panic(
                    "panic_dzine_probe_fail", run_id,
                    f"segment {seg_id}: video probe failed "
                    f"(duration={dur2:.2f}s, expected={target_sec:.2f}s)",
                )
                raise RuntimeError(
                    f"DZINE_PROBE_FAIL: segment {seg_id} "
                    f"(duration={dur2:.2f}s, expected={target_sec:.2f}s)"
                )

            self._index_video(
                run_id, seg_id, video_path, dur2,
                seg.get("audio_sha256", "")[:8], "render_ok",
            )
            rendered += 1

        return {
            "rendered": rendered,
            "skipped": skipped,
            "total": len(segments),
        }

    def _index_video(
        self, run_id: str, segment_id: str,
        path: Path, duration: float, sha8: str, note: str,
    ) -> None:
        """Atomically index a validated video."""
        item = {
            "segment_id": segment_id,
            "run_id": run_id,
            "path": str(path),
            "duration": round(duration, 3),
            "timestamp": _utcnow_iso(),
            "note": note,
        }
        try:
            upsert_video_index(self._video_index_path, sha8, item)
        except Exception:
            pass  # Index is best-effort — doesn't block pipeline

    # ------------------------------------------------------------------
    # Gate: Media Ready
    # ------------------------------------------------------------------

    def media_gate(self, manifest_path: Path) -> None:
        """Validate all media files exist and meet minimum size.

        Raises RuntimeError if any file is missing or too small.
        Must pass before Resolve assembly (saves time and avoids errors).
        """
        m = _read_json(manifest_path)
        if not m or "segments" not in m:
            raise RuntimeError("MEDIA_GATE_FAIL: invalid manifest")

        for seg in m["segments"]:
            audio = seg.get("audio_path")
            video = seg.get("video_path")

            if audio:
                p = Path(audio)
                if not p.exists():
                    raise RuntimeError(f"MEDIA_GATE_FAIL: audio missing {audio}")
                if p.stat().st_size < self.cfg.min_mp3_bytes:
                    raise RuntimeError(
                        f"MEDIA_GATE_FAIL: audio too small {audio} "
                        f"({p.stat().st_size} < {self.cfg.min_mp3_bytes})"
                    )

            if video:
                p = Path(video)
                if not p.exists():
                    raise RuntimeError(f"MEDIA_GATE_FAIL: video missing {video}")
                if p.stat().st_size < self.cfg.min_mp4_bytes:
                    raise RuntimeError(
                        f"MEDIA_GATE_FAIL: video too small {video} "
                        f"({p.stat().st_size} < {self.cfg.min_mp4_bytes})"
                    )

    # ------------------------------------------------------------------
    # Stage: ASSEMBLY (DaVinci Resolve via subprocess)
    # ------------------------------------------------------------------

    def assemble_resolve(self, manifest_path: Path) -> None:
        """Run Resolve assembly script as subprocess."""
        cmd = [sys.executable, self.resolve_script, str(manifest_path)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"RESOLVE_ASSEMBLY_FAIL (exit {result.returncode}): "
                f"{result.stderr[:700]}"
            )

    # ------------------------------------------------------------------
    # Stage: RENDER_PROBE (post-render validation)
    # ------------------------------------------------------------------

    def render_probe(self, output_path: Path) -> Dict[str, Any]:
        """Validate rendered output using media_probe.

        Returns info dict on success, raises on failure.
        Falls back to size-only check if ffprobe is not available.
        """
        if not output_path.exists():
            raise RuntimeError(f"RENDER_PROBE_FAIL: missing {output_path}")

        size = output_path.stat().st_size
        if size < self.cfg.min_render_bytes:
            raise RuntimeError(
                f"RENDER_PROBE_FAIL: too small {size} bytes "
                f"(min {self.cfg.min_render_bytes})"
            )

        # Try ffprobe-based validation if available
        try:
            from tools.lib.media_probe import validate_render
            return validate_render(
                output_path,
                min_bytes=self.cfg.min_render_bytes,
                min_duration_sec=self.cfg.min_render_duration_sec,
            )
        except ImportError:
            return {"path": str(output_path), "bytes": size}
        except Exception:
            # ffprobe not installed — size check already passed
            return {"path": str(output_path), "bytes": size}

    # ------------------------------------------------------------------
    # Top-level run (resume from last checkpoint)
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        run_id: str,
        segments_plan: List[dict],
        lang: str = "en",
        output_path: Optional[str] = None,
    ) -> bool:
        """Execute pipeline from current checkpoint to DONE.

        Resumes from the last completed stage on restart.
        Returns True on success, raises on failure.
        """
        cp = self.load_checkpoint(run_id)
        stage = cp.get("stage", "VOICE_PREP")
        data = cp.get("data", {})

        try:
            if stage == "VOICE_PREP":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "VOICE_PREP"})
                segs = self.voice_prep(segments_plan, lang=lang)
                self.save_checkpoint(run_id, "VOICE_GEN", {"segments": segs})
                stage, data = "VOICE_GEN", {"segments": segs}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "VOICE_PREP"})

            if stage == "VOICE_GEN":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "VOICE_GEN"})
                # Use repair loop when repair engine is available
                if self.repair:
                    segs = self.voice_gen_with_repair(run_id, data["segments"])
                else:
                    segs = self.voice_gen(run_id, data["segments"])

                # Emit per-segment finalize telemetry (SRE)
                for seg in segs:
                    fr = seg.get("finalize_result")
                    if fr:
                        severity = "WARN" if fr["action"] == "needs_repair" else "INFO"
                        await self._emit(
                            run_id, "tone_gate_finalize", severity,
                            {
                                "segment_id": seg.get("segment_id", ""),
                                "kind": seg.get("kind", ""),
                                **fr,
                            },
                        )

                self.save_checkpoint(run_id, "MEDIA_SYNC", {"segments": segs})
                stage, data = "MEDIA_SYNC", {"segments": segs}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "VOICE_GEN"})

            if stage == "MEDIA_SYNC":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "MEDIA_SYNC"})
                segs = data["segments"]
                manifest_path = self.build_manifest(run_id, segs)
                self.save_checkpoint(
                    run_id, "PREFLIGHT",
                    {"manifest_path": str(manifest_path)},
                )
                stage, data = "PREFLIGHT", {"manifest_path": str(manifest_path)}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "MEDIA_SYNC"})

            if stage == "PREFLIGHT":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "PREFLIGHT"})
                manifest_path = Path(data["manifest_path"])
                pf = self.preflight(manifest_path)
                await self._emit(run_id, "preflight_result", "INFO", pf)
                self.save_checkpoint(
                    run_id, "DZINE_RENDER",
                    {"manifest_path": str(manifest_path), "preflight": pf},
                )
                stage = "DZINE_RENDER"
                data = {"manifest_path": str(manifest_path), "preflight": pf}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "PREFLIGHT"})

            if stage == "DZINE_RENDER":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "DZINE_RENDER"})
                manifest_path = Path(data["manifest_path"])
                render_summary = self.dzine_render(run_id, manifest_path)
                await self._emit(
                    run_id, "dzine_render_done", "INFO", render_summary,
                )
                self.save_checkpoint(
                    run_id, "ASSEMBLY",
                    {"manifest_path": str(manifest_path), "render_summary": render_summary},
                )
                stage = "ASSEMBLY"
                data = {"manifest_path": str(manifest_path), "render_summary": render_summary}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "DZINE_RENDER"})

            if stage == "ASSEMBLY":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "ASSEMBLY"})
                manifest_path = Path(data["manifest_path"])
                self.media_gate(manifest_path)
                self.assemble_resolve(manifest_path)
                out = output_path or str(self._output_dir / f"{run_id}.mp4")
                self.save_checkpoint(
                    run_id, "RENDER_PROBE", {"output_path": out},
                )
                stage, data = "RENDER_PROBE", {"output_path": out}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "ASSEMBLY"})

            if stage == "RENDER_PROBE":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "RENDER_PROBE"})
                outp = Path(data["output_path"])
                info = self.render_probe(outp)
                self.save_checkpoint(
                    run_id, "DONE",
                    {"output_path": str(outp), "render_info": info},
                )
                await self._emit(
                    run_id, "stage_done", "INFO",
                    {"stage": "RENDER_PROBE", "render_info": info},
                )

            return True

        except Exception as e:
            # Emit failure event (best-effort)
            try:
                await self._emit(
                    run_id, "stage_fail", "ERROR",
                    {"stage": stage, "error": str(e)[:500]},
                )
            except Exception:
                pass

            # Report panic (local-first — always succeeds)
            self.panic.report_panic("panic_orchestrator", run_id, str(e))

            # Write fail reason to checkpoint — enables forensics on resume
            try:
                cp = self.load_checkpoint(run_id)
                cp["fail_reason"] = str(e)[:500]
                cp["failed_at"] = _utcnow_iso()
                atomic_write_json(self.checkpoint_path(run_id), cp)
            except Exception:
                pass  # Best-effort — don't mask the original error

            raise
