#!/usr/bin/env python3
"""RayVault Run Handoff — deterministic run folder + manifest creation.

Creates a run folder with canonical filenames, computes hashes,
evaluates READY_FOR_RENDER status, and writes 00_manifest.json atomically.

The manifest is the single source of truth for render scripts and Telegram.

Usage:
    python3 -m rayvault.handoff_run \\
        --run-id RUN_2026_02_14_A \\
        --script path/to/script.txt \\
        --audio path/to/audio.wav \\
        --frame path/to/frame.png \\
        --prompt-id OFFICE_V1 \\
        --seed 101 \\
        --fallback-level 0 \\
        --attempts 1 \\
        --identity-confidence HIGH \\
        --identity-reason verified_visual_identity \\
        --products-json path/to/products.json \\
        --render-config path/to/render_config.json

Output structure:
    state/runs/{run_id}/
        00_manifest.json        (atomic, single source of truth)
        01_script.txt           (copied)
        02_audio.wav            (copied, optional)
        03_frame.png            (copied, optional)
        04_metadata.json        (detailed run metadata)
        05_render_config.json   (copied, optional)
        products/               (product bundles, optional)
            products.json       (Top-5 list)
            p01/ .. p05/        (per-product assets)
        publish/                (empty, ready for render output)

Exit codes:
    0: success
    1: runtime error
    2: validation error (bad run-id, missing required file, etc.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

VALID_STATUSES = {
    "INCOMPLETE",
    "WAITING_ASSETS",
    "READY_FOR_RENDER",
    "BLOCKED",
    "PUBLISHED",
}

VALID_CONFIDENCES = {"HIGH", "MEDIUM", "LOW", "NONE"}

VALID_FIDELITY = {"PASS", "FAIL", "FALLBACK_IMAGES", "PENDING"}

MANIFEST_SCHEMA_VERSION = "1.1"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_text(s: str) -> str:
    return hashlib.sha1(s.strip().encode("utf-8")).hexdigest()[:12]


def atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    """Write JSON atomically via tmp + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def copy_asset(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


# ---------------------------------------------------------------------------
# Stability score (canonical formula from safe_mode.json)
# ---------------------------------------------------------------------------


def compute_stability_score(fallback_level: int, attempts: int) -> int:
    """100 - (fallback_level * 25) - ((attempts - 1) * 8). Library = 0."""
    if fallback_level >= 3:
        return 0
    score = 100 - (fallback_level * 25) - (max(0, attempts - 1) * 8)
    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Product fidelity evaluation
# ---------------------------------------------------------------------------


def evaluate_products(products_dir: Path) -> Dict[str, Any]:
    """Evaluate product fidelity from products/ directory.

    Returns:
        {
            "count": int,
            "list_path": str,
            "fidelity": {"result": str, "fail_reason": str|None, "fallback_used": bool},
            "summary": [{"rank": int, "asin": str, ...}, ...]
        }
    """
    products_json = products_dir / "products.json"
    if not products_json.exists():
        return {
            "count": 0,
            "list_path": "products/products.json",
            "fidelity": {
                "result": "PENDING",
                "fail_reason": "products.json not found",
                "fallback_used": False,
            },
            "summary": [],
        }

    data = json.loads(products_json.read_text(encoding="utf-8"))
    items = data.get("items", [])
    summary = []
    any_fail = False
    any_fallback = False

    for item in items:
        rank = item.get("rank", 0)
        asin = item.get("asin", "")
        title = item.get("title", "")
        pdir = products_dir / f"p{rank:02d}"

        # Check per-product QC
        qc_path = pdir / "qc.json"
        if qc_path.exists():
            qc = json.loads(qc_path.read_text(encoding="utf-8"))
            fidelity = qc.get("product_fidelity_result", "PENDING")
            broll = qc.get("broll_method", "PENDING")
        else:
            fidelity = "PENDING"
            broll = "PENDING"

        if fidelity == "FAIL":
            any_fail = True
        if fidelity == "FALLBACK_IMAGES":
            any_fallback = True

        # Check source images exist
        src_imgs = pdir / "source_images"
        has_images = src_imgs.is_dir() and any(src_imgs.iterdir())

        summary.append({
            "rank": rank,
            "asin": asin,
            "title": title[:60],
            "fidelity": fidelity,
            "broll": broll,
            "has_source_images": has_images if src_imgs.is_dir() else False,
        })

    # Aggregate fidelity
    if any_fail:
        agg_result = "BLOCKED"
        fail_reason = "product fidelity FAIL without fallback"
    elif all(
        s["fidelity"] in ("PASS", "FALLBACK_IMAGES") for s in summary
    ):
        agg_result = "PASS"
        fail_reason = None
    else:
        agg_result = "PENDING"
        fail_reason = "some products pending QC"

    return {
        "count": len(items),
        "list_path": "products/products.json",
        "fidelity": {
            "result": agg_result,
            "fail_reason": fail_reason,
            "fallback_used": any_fallback,
        },
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Status decision
# ---------------------------------------------------------------------------


def decide_status(
    visual_qc: str,
    identity_confidence: str,
    has_script: bool,
    has_audio: bool,
    has_frame: bool,
    has_render_config: bool = False,
    has_products: bool = False,
    products_fidelity: str = "PENDING",
) -> str:
    """Deterministic status from inputs. No side effects."""
    if not has_script:
        return "INCOMPLETE"
    if identity_confidence == "NONE":
        return "BLOCKED"
    if visual_qc == "FAIL":
        return "BLOCKED"
    if products_fidelity == "BLOCKED":
        return "BLOCKED"

    # All required for READY_FOR_RENDER
    all_present = has_script and has_audio and has_frame
    if all_present and visual_qc == "PASS":
        return "READY_FOR_RENDER"

    if not has_audio or not has_frame:
        return "WAITING_ASSETS"
    return "INCOMPLETE"


# ---------------------------------------------------------------------------
# Prompt loading (reuse prompt_registry logic)
# ---------------------------------------------------------------------------


def load_prompt_text(prompt_id: str, prompts_dir: Path) -> Optional[str]:
    """Load prompt text from prompts/{prompt_id}.txt."""
    path = prompts_dir / f"{prompt_id}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Main handoff
# ---------------------------------------------------------------------------


def handoff(
    run_id: str,
    script_path: Path,
    audio_path: Optional[Path],
    frame_path: Optional[Path],
    prompt_id: str,
    seed: Optional[int],
    fallback_level: int,
    attempts: int,
    identity_confidence: str,
    identity_reason: str,
    identity_method: str = "human_overlay_3_anchor",
    anchors: Optional[List[str]] = None,
    reference_strength: Optional[float] = None,
    visual_qc: str = "UNKNOWN",
    visual_fail_reason: Optional[str] = None,
    products_json_path: Optional[Path] = None,
    render_config_path: Optional[Path] = None,
    state_dir: Path = Path("state"),
    prompts_dir: Path = Path("prompts"),
    force: bool = False,
) -> Dict[str, Any]:
    """Create run folder, copy assets, write manifest. Returns manifest dict."""

    # Validate run_id
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run-id: {run_id!r}. Allowed: A-Za-z0-9_-")

    # Validate confidence
    if identity_confidence not in VALID_CONFIDENCES:
        raise ValueError(
            f"Invalid identity-confidence: {identity_confidence!r}. "
            f"Allowed: {VALID_CONFIDENCES}"
        )

    run_dir = (state_dir / "runs" / run_id).resolve()
    publish_dir = run_dir / "publish"

    if run_dir.exists() and not force:
        raise FileExistsError(
            f"Run dir exists: {run_dir}. Use force=True to overwrite."
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    publish_dir.mkdir(parents=True, exist_ok=True)

    # Load prompt for hashing
    prompt_text = load_prompt_text(prompt_id, prompts_dir)
    prompt_hash = sha1_text(prompt_text) if prompt_text else None

    # Default reference_strength
    if reference_strength is None:
        reference_strength = 0.85

    # Default anchors
    if anchors is None:
        anchors = ["hairline", "nose_bridge", "jawline"]

    # Copy script (required)
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    script_dst = run_dir / "01_script.txt"
    copy_asset(script_path, script_dst)
    script_sha1 = sha1_file(script_dst)

    # Copy audio (optional)
    has_audio = False
    audio_sha1 = None
    audio_dst = run_dir / "02_audio.wav"
    if audio_path and audio_path.exists():
        copy_asset(audio_path, audio_dst)
        audio_sha1 = sha1_file(audio_dst)
        has_audio = True

    # Copy frame (optional)
    has_frame = False
    frame_sha1 = None
    frame_dst = run_dir / "03_frame.png"
    if frame_path and frame_path.exists():
        copy_asset(frame_path, frame_dst)
        frame_sha1 = sha1_file(frame_dst)
        has_frame = True

    # Copy render config (optional)
    has_render_config = False
    render_config_sha1 = None
    render_dst = run_dir / "05_render_config.json"
    if render_config_path and render_config_path.exists():
        copy_asset(render_config_path, render_dst)
        render_config_sha1 = sha1_file(render_dst)
        has_render_config = True

    # Copy products.json and evaluate (optional)
    has_products = False
    products_block = None
    products_dir = run_dir / "products"
    if products_json_path and products_json_path.exists():
        products_dir.mkdir(parents=True, exist_ok=True)
        copy_asset(products_json_path, products_dir / "products.json")
        has_products = True
        products_block = evaluate_products(products_dir)

    products_fidelity = "PENDING"
    if products_block:
        products_fidelity = products_block["fidelity"]["result"]

    # Stability score
    stability_score = compute_stability_score(fallback_level, attempts)

    # Status decision
    status = decide_status(
        visual_qc=visual_qc,
        identity_confidence=identity_confidence,
        has_script=True,
        has_audio=has_audio,
        has_frame=has_frame,
        has_render_config=has_render_config,
        has_products=has_products,
        products_fidelity=products_fidelity,
    )

    created_at = utc_now_iso()

    # Metadata (detailed)
    metadata = {
        "run_id": run_id,
        "created_at_utc": created_at,
        "prompt_id": prompt_id,
        "prompt_hash": prompt_hash,
        "seed": seed,
        "fallback_level": fallback_level,
        "attempts": attempts,
        "stability_score": stability_score,
        "visual_qc_result": visual_qc,
        "visual_fail_reason": visual_fail_reason,
        "identity_proof": {
            "confidence": identity_confidence,
            "reason": identity_reason,
            "method": identity_method,
            "anchors_verified": anchors,
            "reference_strength": reference_strength,
            "seed": seed,
        },
    }
    atomic_write_json(run_dir / "04_metadata.json", metadata)

    # Manifest (single source of truth)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at_utc": created_at,
        "status": status,
        "stability": {
            "fallback_level": fallback_level,
            "attempts": attempts,
            "stability_score": stability_score,
        },
        "assets": {
            "script": {"path": "01_script.txt", "sha1": script_sha1},
            "audio": {"path": "02_audio.wav", "sha1": audio_sha1},
            "frame": {"path": "03_frame.png", "sha1": frame_sha1},
            "render_config": {
                "path": "05_render_config.json",
                "sha1": render_config_sha1,
            },
        },
        "metadata": {
            "prompt_id": prompt_id,
            "prompt_hash": prompt_hash,
            "seed": seed,
            "identity": {
                "confidence": identity_confidence,
                "reason": identity_reason,
                "method": identity_method,
                "anchors_verified": anchors,
                "reference_strength": reference_strength,
            },
            "visual_qc_result": visual_qc,
            "visual_fail_reason": visual_fail_reason,
        },
        "paths": {
            "run_dir": str(run_dir),
            "publish_dir": str(publish_dir),
        },
    }

    # Add products block if present
    if products_block:
        manifest["products"] = products_block

    atomic_write_json(run_dir / "00_manifest.json", manifest)

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Run Handoff — create run folder + manifest",
    )
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--frame", default=None)
    ap.add_argument("--prompt-id", required=True)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fallback-level", type=int, required=True)
    ap.add_argument("--attempts", type=int, default=1)
    ap.add_argument(
        "--identity-confidence",
        required=True,
        choices=sorted(VALID_CONFIDENCES),
    )
    ap.add_argument("--identity-reason", required=True)
    ap.add_argument("--identity-method", default="human_overlay_3_anchor")
    ap.add_argument("--anchors", default="hairline,nose_bridge,jawline")
    ap.add_argument("--reference-strength", type=float, default=None)
    ap.add_argument(
        "--visual-qc",
        choices=["PASS", "FAIL", "UNKNOWN"],
        default="UNKNOWN",
    )
    ap.add_argument("--visual-fail-reason", default=None)
    ap.add_argument("--products-json", default=None)
    ap.add_argument("--render-config", default=None)
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--prompts-dir", default="prompts")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    anchors_list = [a.strip() for a in args.anchors.split(",") if a.strip()]

    try:
        manifest = handoff(
            run_id=args.run_id,
            script_path=Path(args.script).expanduser().resolve(),
            audio_path=(
                Path(args.audio).expanduser().resolve() if args.audio else None
            ),
            frame_path=(
                Path(args.frame).expanduser().resolve() if args.frame else None
            ),
            prompt_id=args.prompt_id,
            seed=args.seed,
            fallback_level=args.fallback_level,
            attempts=args.attempts,
            identity_confidence=args.identity_confidence,
            identity_reason=args.identity_reason,
            identity_method=args.identity_method,
            anchors=anchors_list,
            reference_strength=args.reference_strength,
            visual_qc=args.visual_qc,
            visual_fail_reason=args.visual_fail_reason,
            products_json_path=(
                Path(args.products_json).expanduser().resolve()
                if args.products_json
                else None
            ),
            render_config_path=(
                Path(args.render_config).expanduser().resolve()
                if args.render_config
                else None
            ),
            state_dir=Path(args.state_dir),
            prompts_dir=Path(args.prompts_dir),
            force=args.force,
        )
        status = manifest["status"]
        score = manifest["stability"]["stability_score"]
        products_info = ""
        if "products" in manifest:
            pf = manifest["products"]["fidelity"]["result"]
            pc = manifest["products"]["count"]
            products_info = f" | products={pc} fidelity={pf}"
        print(
            f"handoff_run done: {args.run_id} | status={status} "
            f"| score={score}{products_info}"
        )
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
