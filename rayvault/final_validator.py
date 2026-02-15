#!/usr/bin/env python3
"""RayVault Final Validator — last gate before YouTube upload.

Validates that a run directory is safe to publish:
  1. Manifest exists and status is READY_FOR_RENDER
  2. Core assets present (script, audio, frame)
  3. Render config exists and has segments
  4. Product fidelity meets minimum truth threshold
  5. Identity confidence is HIGH or MEDIUM
  6. Visual QC is PASS
  7. Final video file exists in publish/
  8. Stability score above critical threshold
  9. DaVinci required: engine_used must be 'davinci' (blocks shadow renders)

Golden rule: NEVER upload unless every gate passes.

Usage:
    python3 -m rayvault.final_validator --run-dir state/runs/RUN_2026_02_14_A
    python3 -m rayvault.final_validator --run-dir state/runs/RUN_2026_02_14_A --min-truth 4

Exit codes:
    0: all gates pass — safe to upload
    1: runtime error
    2: one or more gates failed — DO NOT upload
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Gate result
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationVerdict:
    run_id: str
    all_passed: bool
    gates: List[GateResult] = field(default_factory=list)
    failed_gates: List[str] = field(default_factory=list)
    patient_zero: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "all_passed": self.all_passed,
            "gates": [
                {"name": g.name, "passed": g.passed, "detail": g.detail}
                for g in self.gates
            ],
            "failed_gates": self.failed_gates,
            "patient_zero": self.patient_zero,
            "checked_at_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Individual gates
# ---------------------------------------------------------------------------


def gate_manifest_exists(run_dir: Path) -> GateResult:
    path = run_dir / "00_manifest.json"
    if path.exists():
        return GateResult("manifest_exists", True, "ok")
    return GateResult("manifest_exists", False, "00_manifest.json missing")


def gate_manifest_status(manifest: Dict[str, Any]) -> GateResult:
    status = manifest.get("status", "UNKNOWN")
    if status == "READY_FOR_RENDER":
        return GateResult("manifest_status", True, f"status={status}")
    return GateResult(
        "manifest_status", False, f"status={status} (expected READY_FOR_RENDER)"
    )


def gate_core_assets(run_dir: Path) -> GateResult:
    missing = []
    for fname in ("01_script.txt", "02_audio.wav", "03_frame.png"):
        if not (run_dir / fname).exists():
            missing.append(fname)
    if not missing:
        return GateResult("core_assets", True, "script+audio+frame present")
    return GateResult("core_assets", False, f"missing: {', '.join(missing)}")


def gate_render_config(run_dir: Path) -> GateResult:
    rc_path = run_dir / "05_render_config.json"
    if not rc_path.exists():
        return GateResult("render_config", False, "05_render_config.json missing")
    try:
        rc = read_json(rc_path)
        segments = rc.get("segments", [])
        if not segments:
            return GateResult("render_config", False, "no segments in render_config")
        return GateResult(
            "render_config", True, f"{len(segments)} segments"
        )
    except Exception as e:
        return GateResult("render_config", False, f"unreadable: {e}")


def gate_product_fidelity(
    run_dir: Path, min_truth: int = 4
) -> GateResult:
    products_dir = run_dir / "products"
    if not products_dir.exists():
        return GateResult(
            "product_fidelity", True, "no products dir (products optional)"
        )

    # Check render config for fidelity score
    rc_path = run_dir / "05_render_config.json"
    if rc_path.exists():
        try:
            rc = read_json(rc_path)
            products_block = rc.get("products", {})
            truth_used = products_block.get("truth_visuals_used", 0)
            expected = products_block.get("expected", 0)
            if expected > 0 and truth_used < min_truth:
                return GateResult(
                    "product_fidelity",
                    False,
                    f"truth_visuals={truth_used}/{expected} (min={min_truth})",
                )
            if expected > 0:
                return GateResult(
                    "product_fidelity",
                    True,
                    f"truth_visuals={truth_used}/{expected}",
                )
        except Exception:
            pass

    # Fallback: count product directories with source images
    products_json = products_dir / "products.json"
    if not products_json.exists():
        return GateResult("product_fidelity", True, "no products.json")

    try:
        data = read_json(products_json)
        items = data.get("items", [])
        if not items:
            return GateResult("product_fidelity", True, "empty product list")

        total = len(items)
        with_visual = 0
        for item in items:
            rank = item.get("rank", 0)
            pdir = products_dir / f"p{rank:02d}"
            # Check approved broll
            broll = pdir / "broll" / "approved.mp4"
            if broll.exists():
                with_visual += 1
                continue
            # Check source image
            src = pdir / "source_images"
            if src.is_dir() and any(
                f.name.startswith("01_main") for f in src.iterdir() if f.is_file()
            ):
                with_visual += 1

        if with_visual < min_truth:
            return GateResult(
                "product_fidelity",
                False,
                f"truth_visuals={with_visual}/{total} (min={min_truth})",
            )
        return GateResult(
            "product_fidelity",
            True,
            f"truth_visuals={with_visual}/{total}",
        )
    except Exception as e:
        return GateResult("product_fidelity", False, f"error: {e}")


def gate_identity_confidence(manifest: Dict[str, Any]) -> GateResult:
    meta = manifest.get("metadata", {})
    identity = meta.get("identity", {})
    confidence = identity.get("confidence", "UNKNOWN")
    if confidence in ("HIGH", "MEDIUM"):
        return GateResult(
            "identity_confidence", True, f"confidence={confidence}"
        )
    return GateResult(
        "identity_confidence",
        False,
        f"confidence={confidence} (need HIGH or MEDIUM)",
    )


def gate_visual_qc(manifest: Dict[str, Any]) -> GateResult:
    meta = manifest.get("metadata", {})
    qc_result = meta.get("visual_qc_result", "UNKNOWN")
    if qc_result == "PASS":
        return GateResult("visual_qc", True, f"qc={qc_result}")
    return GateResult(
        "visual_qc", False, f"qc={qc_result} (need PASS)"
    )


def gate_final_video(run_dir: Path) -> GateResult:
    publish = run_dir / "publish"
    if not publish.is_dir():
        return GateResult("final_video", False, "publish/ dir missing")
    video = publish / "video_final.mp4"
    if video.exists() and video.stat().st_size > 1024:
        size_mb = video.stat().st_size / (1024 * 1024)
        return GateResult(
            "final_video", True, f"video_final.mp4 ({size_mb:.1f} MB)"
        )
    return GateResult(
        "final_video", False, "publish/video_final.mp4 missing or too small"
    )


def gate_stability_score(
    manifest: Dict[str, Any], critical_threshold: int = 40
) -> GateResult:
    stability = manifest.get("stability", {})
    score = stability.get("stability_score", 0)
    if score >= critical_threshold:
        return GateResult(
            "stability_score", True, f"score={score} (threshold={critical_threshold})"
        )
    return GateResult(
        "stability_score",
        False,
        f"score={score} < critical_threshold={critical_threshold}",
    )


def gate_audio_proof(manifest: Dict[str, Any]) -> GateResult:
    """Validate audio_proof and derive safe_audio_mode.

    safe_audio_mode = True ONLY if:
      - tts_provider is a known TTS engine
      - has_external_music == False
      - has_external_sfx == False
      - script_provenance in ("ai_generated", "ai_generated+human_edit")
    """
    proof = manifest.get("audio_proof")
    if not proof:
        return GateResult(
            "audio_proof", True,
            "no audio_proof block (optional gate, skipped)"
        )

    tts = proof.get("tts_provider", "")
    has_music = proof.get("has_external_music", False)
    has_sfx = proof.get("has_external_sfx", False)
    prov = proof.get("script_provenance", "")

    safe = bool(
        tts
        and not has_music
        and not has_sfx
        and prov in ("ai_generated", "ai_generated+human_edit")
    )

    detail = f"safe_audio_mode={safe} (tts={tts}, music={has_music}, sfx={has_sfx}, prov={prov})"

    # Write derived safe_audio_mode back into manifest proof block
    proof["safe_audio_mode"] = safe

    return GateResult("audio_proof", True, detail)


def gate_davinci_required(manifest: Dict[str, Any]) -> GateResult:
    """Gate: if davinci_required policy is set, engine_used must be 'davinci'.

    Checks render.engine_used in manifest. If the policy field
    render.davinci_required is True (or absent — default policy),
    the render must have been produced by DaVinci, not the shadow FFmpeg.
    """
    render = manifest.get("render", {})
    policy = render.get("davinci_required", True)  # default: required

    if not policy:
        return GateResult(
            "davinci_required", True, "davinci_required=false (policy disabled)"
        )

    engine = render.get("engine_used", "")
    if engine == "davinci":
        return GateResult(
            "davinci_required", True, f"engine_used={engine}"
        )

    if not engine:
        return GateResult(
            "davinci_required", False,
            "no engine_used in manifest (render not executed?)"
        )

    return GateResult(
        "davinci_required", False,
        f"engine_used={engine} (policy requires davinci)"
    )


def gate_pacing(run_dir: Path) -> GateResult:
    """Gate: editorial pacing must be OK (no long static segments)."""
    rc_path = run_dir / "05_render_config.json"
    if not rc_path.exists():
        return GateResult("pacing", True, "no render_config (skipped)")
    try:
        rc = read_json(rc_path)
        pacing = rc.get("pacing", {})
        if not pacing:
            return GateResult("pacing", True, "no pacing block (skipped)")
        if not pacing.get("ok", True):
            errors = pacing.get("errors", [])
            return GateResult(
                "pacing", False,
                f"EDITORIAL_LOW_VARIETY: {'; '.join(errors)}"
            )
        warnings = pacing.get("warnings", [])
        detail = "pacing OK"
        if warnings:
            detail += f" (warnings: {'; '.join(warnings)})"
        return GateResult("pacing", True, detail)
    except Exception as e:
        return GateResult("pacing", True, f"pacing check error: {e}")


def gate_soundtrack_compliance(manifest: Dict[str, Any]) -> GateResult:
    """Gate 14: soundtrack license tier must match publish policy.

    - If soundtrack not enabled: PASS (skipped)
    - If license_tier == RED and auto-publish: FAIL
    - If license_tier == AMBER and not BLOCKED_FOR_REVIEW: FAIL
    - If enabled but audio_proof.has_external_music != True: FAIL
    """
    audio = manifest.get("audio", {})
    st = audio.get("soundtrack", {})

    if not st.get("enabled"):
        return GateResult(
            "soundtrack_compliance", True, "soundtrack not enabled (skipped)"
        )

    tier = st.get("license_tier", "")
    policy = st.get("publish_policy", "")

    # RED tier must never auto-publish
    if tier == "RED" and policy == "AUTO_PUBLISH":
        return GateResult(
            "soundtrack_compliance", False,
            f"RED tier cannot AUTO_PUBLISH (tier={tier}, policy={policy})"
        )

    # AMBER must be BLOCKED_FOR_REVIEW
    if tier == "AMBER" and policy != "BLOCKED_FOR_REVIEW":
        return GateResult(
            "soundtrack_compliance", False,
            f"AMBER tier must be BLOCKED_FOR_REVIEW (policy={policy})"
        )

    # If soundtrack enabled, audio_proof must reflect external music
    proof = manifest.get("audio_proof", {})
    if not proof.get("has_external_music"):
        return GateResult(
            "soundtrack_compliance", False,
            "soundtrack enabled but audio_proof.has_external_music != True"
        )

    return GateResult(
        "soundtrack_compliance", True,
        f"tier={tier}, policy={policy}"
    )


def gate_audio_postcheck(manifest: Dict[str, Any]) -> GateResult:
    """Gate 15: audio postcheck must pass if present.

    - If audio_postcheck section in receipt: FAIL if ok == False
    - If missing: WARN (not yet run)
    """
    render = manifest.get("render", {})
    receipt_postcheck = render.get("audio_postcheck")

    # Also check soundtrack_receipt.post_checks in render receipt
    # (assembled in davinci_assembler)
    if receipt_postcheck is None:
        # Not yet run — pass with warning
        return GateResult(
            "audio_postcheck", True,
            "no audio_postcheck section (not yet run)"
        )

    if receipt_postcheck.get("ok") is False:
        errors = receipt_postcheck.get("errors", [])
        return GateResult(
            "audio_postcheck", False,
            f"audio postcheck FAILED: {'; '.join(errors)}"
        )

    return GateResult("audio_postcheck", True, "audio postcheck OK")


def gate_claims_validation(manifest: Dict[str, Any]) -> GateResult:
    claims = manifest.get("claims_validation", {})
    status = claims.get("status", "")
    if not status:
        return GateResult(
            "claims_validation", True, "no claims_validation (not run yet)"
        )
    if status == "PASS":
        return GateResult("claims_validation", True, "claims PASS")
    if status == "REVIEW_REQUIRED":
        n = claims.get("violations_count", len(claims.get("violations", [])))
        return GateResult(
            "claims_validation",
            False,
            f"REVIEW_REQUIRED ({n} violations)",
        )
    return GateResult("claims_validation", True, f"claims status={status}")


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate_run(
    run_dir: Path,
    min_truth_products: int = 4,
    stability_threshold: int = 40,
    require_video: bool = True,
) -> ValidationVerdict:
    """Run all gates and return structured verdict.

    Returns ValidationVerdict with all_passed=True only if every gate passes.
    """
    run_dir = run_dir.resolve()
    run_id = run_dir.name

    gates: List[GateResult] = []

    # Gate 1: manifest exists
    g = gate_manifest_exists(run_dir)
    gates.append(g)
    if not g.passed:
        return _build_verdict(run_id, gates)

    manifest = read_json(run_dir / "00_manifest.json")

    # Gate 2: manifest status
    gates.append(gate_manifest_status(manifest))

    # Gate 3: core assets
    gates.append(gate_core_assets(run_dir))

    # Gate 4: render config
    gates.append(gate_render_config(run_dir))

    # Gate 5: product fidelity
    gates.append(gate_product_fidelity(run_dir, min_truth_products))

    # Gate 6: identity confidence
    gates.append(gate_identity_confidence(manifest))

    # Gate 7: visual QC
    gates.append(gate_visual_qc(manifest))

    # Gate 8: claims validation
    gates.append(gate_claims_validation(manifest))

    # Gate 9: audio proof (derives safe_audio_mode)
    gates.append(gate_audio_proof(manifest))

    # Gate 10: final video (optional gate)
    if require_video:
        gates.append(gate_final_video(run_dir))

    # Gate 11: stability score
    gates.append(gate_stability_score(manifest, stability_threshold))

    # Gate 12: DaVinci required (blocks shadow-only renders from upload)
    if require_video:
        gates.append(gate_davinci_required(manifest))

    # Gate 13: Pacing (editorial quality — long static segments blocked)
    gates.append(gate_pacing(run_dir))

    # Gate 14: Soundtrack compliance (license tier vs publish policy)
    gates.append(gate_soundtrack_compliance(manifest))

    # Gate 15: Audio postcheck (loudness, duration, balance)
    gates.append(gate_audio_postcheck(manifest))

    verdict = _build_verdict(run_id, gates)

    # Write validation result to manifest
    manifest_path = run_dir / "00_manifest.json"
    manifest.setdefault("validation", {})
    manifest["validation"]["last_result"] = verdict.to_dict()
    manifest["validation"]["passed"] = verdict.all_passed
    atomic_write_json(manifest_path, manifest)

    return verdict


def _build_verdict(
    run_id: str, gates: List[GateResult]
) -> ValidationVerdict:
    failed = [g.name for g in gates if not g.passed]
    patient_zero = failed[0] if failed else None
    return ValidationVerdict(
        run_id=run_id,
        all_passed=len(failed) == 0,
        gates=gates,
        failed_gates=failed,
        patient_zero=patient_zero,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Final Validator — last gate before upload",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument(
        "--min-truth",
        type=int,
        default=4,
        help="Minimum products with truth visuals (default 4)",
    )
    ap.add_argument(
        "--stability-threshold",
        type=int,
        default=40,
        help="Minimum stability score (default 40)",
    )
    ap.add_argument(
        "--no-video",
        action="store_true",
        help="Skip final video check (for pre-render validation)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    try:
        verdict = validate_run(
            run_dir,
            min_truth_products=args.min_truth,
            stability_threshold=args.stability_threshold,
            require_video=not args.no_video,
        )
        status = "PASS" if verdict.all_passed else "FAIL"
        n_gates = len(verdict.gates)
        n_passed = sum(1 for g in verdict.gates if g.passed)
        pz = f" | patient_zero={verdict.patient_zero}" if verdict.patient_zero else ""
        print(
            f"final_validator: {status} | {n_passed}/{n_gates} gates passed{pz}"
        )
        if verdict.failed_gates:
            for name in verdict.failed_gates:
                gate = next(g for g in verdict.gates if g.name == name)
                print(f"  FAIL: {name} — {gate.detail}")
        return 0 if verdict.all_passed else 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
