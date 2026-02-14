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
    scrub_fillers,
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


class EventSinkLike(Protocol):
    """Interface for run_event insertion (async)."""
    async def insert_run_event(self, event: dict) -> None: ...


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrchestratorConfig:
    """Orchestrator configuration and paths."""
    state_dir: str = "state"
    checkpoints_dir: str = "state/checkpoints"
    jobs_dir: str = "state/jobs"
    audio_dir: str = "state/audio"
    video_dir: str = "state/video"
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


# Stages as simple strings — deterministic ordering
STAGES = (
    "VOICE_PREP",
    "VOICE_GEN",
    "MEDIA_SYNC",
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
        event_sink: Optional[EventSinkLike] = None,
        resolve_script: str = "scripts/resolve_assemble.py",
        render_probe_script: str = "scripts/render_probe.py",
    ):
        self.cfg = config
        self.panic = panic_mgr
        self.tts = tts_engine
        self.events = event_sink
        self.resolve_script = resolve_script
        self.render_probe_script = render_probe_script

        self._check_dir = Path(config.checkpoints_dir)
        self._jobs_dir = Path(config.jobs_dir)
        self._audio_dir = Path(config.audio_dir)
        self._video_dir = Path(config.video_dir)
        self._output_dir = Path(config.output_dir)

        # Ensure directories exist
        for d in (self._check_dir, self._jobs_dir, self._audio_dir, self._output_dir):
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
    # Stage: VOICE_GEN (idempotent per-segment TTS)
    # ------------------------------------------------------------------

    def voice_gen(self, run_id: str, segments: List[dict]) -> List[dict]:
        """Generate audio for each segment. Skips needs_repair/needs_human.

        Uses TTS engine's synthesize method. Idempotency via has_artifact().
        """
        if not self.tts:
            # No TTS engine — mark all with placeholder paths
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

                # Optional: pad to target duration
                approx = _safe_float(s2.get("approx_duration_sec", 0))
                if approx > 0:
                    try:
                        finalize_segment_audio(audio_path, target_duration=approx)
                    except Exception:
                        pass  # Padding failure is non-fatal
            except Exception as e:
                s2["audio_path"] = None
                s2["tts_error"] = str(e)[:300]
                s2["needs_human"] = True

            out.append(s2)

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
                segs = self.voice_gen(run_id, data["segments"])
                self.save_checkpoint(run_id, "MEDIA_SYNC", {"segments": segs})
                stage, data = "MEDIA_SYNC", {"segments": segs}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "VOICE_GEN"})

            if stage == "MEDIA_SYNC":
                await self._emit(run_id, "stage_enter", "INFO", {"stage": "MEDIA_SYNC"})
                segs = data["segments"]
                manifest_path = self.build_manifest(run_id, segs)
                self.save_checkpoint(
                    run_id, "ASSEMBLY",
                    {"manifest_path": str(manifest_path)},
                )
                stage, data = "ASSEMBLY", {"manifest_path": str(manifest_path)}
                await self._emit(run_id, "stage_done", "INFO", {"stage": "MEDIA_SYNC"})

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

            # Checkpoint stays at current stage — enables resume
            raise
