#!/usr/bin/env python3
"""RayVault Render Config Generator — deterministic timeline + product truth constraints.

Reads run assets (script, audio, products, per-product QC) and produces
05_render_config.json with a normalized timeline and product visual modes.

Golden rule: NEVER generate AI product shots from text.
Only: approved.mp4 broll, Ken Burns on real image, still frame, or SKIP.

Usage:
    python3 -m rayvault.render_config_generate --run-dir state/runs/RUN_2026_02_14_A

Exit codes:
    0: success
    1: runtime error
    2: validation error (missing run_dir, script, products)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RENDER_CONFIG_VERSION = "1.3"

T_INTRO = 2.0
T_OUTRO = 1.5
T_PER_PRODUCT_MIN = 3.5
T_PER_PRODUCT_MAX = 7.0
T_PER_PRODUCT_DEFAULT = 4.0

AUDIO_DEFAULTS = {
    "normalize_lufs": -14.0,
    "true_peak": -1.0,
    "sample_rate": 48000,
    "voice_track_gain_db": 0.0,
    "music_bed_gain_db": -18.0,
    "limiter": True,
}

CANVAS_DEFAULTS = {"w": 1920, "h": 1080, "fps": 30}

OUTPUT_DEFAULTS = {
    "w": 1920,
    "h": 1080,
    "fps": 30,
    "vcodec": "libx264",
    "acodec": "aac",
    "crf": 18,
    "preset": "slow",
    "pix_fmt": "yuv420p",
}

RAY_DEFAULTS = {
    "frame_path": "03_frame.png",
    "face_safe_box_norm": {"x": 0.33, "y": 0.18, "w": 0.34, "h": 0.52},
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wav_duration_seconds(path: Path) -> Optional[float]:
    """Read actual WAV duration via wave module. Returns None if unreadable."""
    if not path.exists():
        return None
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


def estimate_duration_from_words(script_path: Path) -> float:
    """Fallback: estimate ~150 words/minute."""
    text = script_path.read_text(encoding="utf-8")
    words = len(text.split())
    return max(10.0, words / 150.0 * 60.0)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Product visual mode resolution (strict naming)
# ---------------------------------------------------------------------------


def find_main_image(pdir: Path) -> Optional[str]:
    """Find 01_main.* in source_images/. Returns path relative to run_dir."""
    src = pdir / "source_images"
    if not src.is_dir():
        return None
    for f in sorted(src.iterdir()):
        if f.is_file() and f.name.startswith("01_main"):
            return str(f.relative_to(pdir.parent.parent))
    return None


def resolve_visual_mode(
    pdir: Path,
    run_dir: Path,
    qc: Optional[Dict[str, Any]],
    asin: str = "",
    library_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Determine visual mode for a product.

    Strict priority:
    1. QC override (SKIP, STILL_ONLY)
    2. Library approved b-roll (digital patrimony from prior runs)
    3. Run approved.mp4 in broll/ (BROLL_VIDEO)
    4. 01_main.* in source_images/ (KEN_BURNS)
    5. SKIP (never invent)
    """
    requested_method = ""
    fidelity_result = "UNKNOWN"
    if qc:
        requested_method = (qc.get("broll_method") or "").upper()
        fidelity_result = qc.get("product_fidelity_result", "UNKNOWN")

    # QC forced SKIP
    if requested_method == "SKIP" or fidelity_result == "FAIL":
        return {"mode": "SKIP", "source": None, "reason": fidelity_result}

    # QC forced STILL_ONLY
    main_img = find_main_image(pdir)
    if requested_method == "STILL_ONLY":
        if main_img:
            return {"mode": "STILL_ONLY", "source": main_img, "reason": "qc_still_only"}
        return {"mode": "SKIP", "source": None, "reason": "qc_still_only_but_missing_main"}

    # Library approved b-roll (reuse from prior runs — saves Dzine credits)
    if library_dir and asin and requested_method in ("", "AUTO", "DZINE_I2V", "KEN_BURNS"):
        lib_broll = library_dir / "products" / asin / "approved_broll" / "approved.mp4"
        if lib_broll.exists():
            return {
                "mode": "BROLL_VIDEO",
                "source": str(lib_broll),
                "reason": "library_approved_broll",
            }

    # Run approved broll (strict: only approved.mp4, never glob random mp4)
    approved_broll = pdir / "broll" / "approved.mp4"
    if approved_broll.exists() and requested_method in ("", "AUTO", "DZINE_I2V", "KEN_BURNS"):
        return {
            "mode": "BROLL_VIDEO",
            "source": str(approved_broll.relative_to(run_dir)),
            "reason": "approved_broll",
        }

    # Ken Burns on truth main image
    if main_img and requested_method in ("", "AUTO", "KEN_BURNS", "DZINE_I2V"):
        return {"mode": "KEN_BURNS", "source": main_img, "reason": "truth_main_image"}

    # No visual available → SKIP (never invent)
    return {"mode": "SKIP", "source": None, "reason": "no_truth_visual_available"}


# ---------------------------------------------------------------------------
# Timeline generation
# ---------------------------------------------------------------------------


def generate_timeline(
    product_visuals: List[Dict[str, Any]],
    audio_duration: float,
) -> List[Dict[str, Any]]:
    """Build normalized timeline segments."""
    total = len(product_visuals)
    remaining = max(6.0, audio_duration - T_INTRO - T_OUTRO)
    per_product = clamp(
        remaining / max(1, total),
        T_PER_PRODUCT_MIN,
        T_PER_PRODUCT_MAX,
    ) if total > 0 else T_PER_PRODUCT_DEFAULT

    fps = CANVAS_DEFAULTS["fps"]
    segments: List[Dict[str, Any]] = []
    seg_idx = 0
    t = 0.0

    # Intro
    t0 = round(t, 3)
    t1 = round(t + T_INTRO, 3)
    segments.append({
        "id": f"seg_{seg_idx:03d}",
        "type": "intro",
        "t0": t0,
        "t1": t1,
        "frames": round((t1 - t0) * fps),
    })
    t += T_INTRO
    seg_idx += 1

    # Product segments
    for p in product_visuals:
        t0 = round(t, 3)
        t1 = round(t + per_product, 3)
        seg: Dict[str, Any] = {
            "id": f"seg_{seg_idx:03d}",
            "type": "product",
            "rank": p["rank"],
            "asin": p.get("asin", ""),
            "t0": t0,
            "t1": t1,
            "frames": round((t1 - t0) * fps),
            "visual": p["visual"],
        }
        if p.get("title"):
            seg["title"] = p["title"][:60]
        segments.append(seg)
        t += per_product
        seg_idx += 1

    # Outro
    t0 = round(t, 3)
    t1 = round(t + T_OUTRO, 3)
    segments.append({
        "id": f"seg_{seg_idx:03d}",
        "type": "outro",
        "t0": t0,
        "t1": t1,
        "frames": round((t1 - t0) * fps),
    })

    return segments


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def generate_render_config(
    run_dir: Path,
    require_audio: bool = False,
    min_truth_products: int = 4,
    library_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Generate 05_render_config.json for a run directory.

    Returns:
        {
            "config": <render_config dict>,
            "fidelity_score": int (0-100),
            "needs_manual_review": bool,
            "patient_zero": None | {"code": str, "detail": str},
        }
    """
    run_dir = run_dir.resolve()
    script_path = run_dir / "01_script.txt"
    audio_path = run_dir / "02_audio.wav"
    products_dir = run_dir / "products"
    products_json = products_dir / "products.json"

    # Script is required
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    # Audio duration: prefer WAV, fallback to word estimate
    audio_duration = wav_duration_seconds(audio_path)
    if require_audio and audio_duration is None:
        raise FileNotFoundError(
            f"Audio required but missing/unreadable: {audio_path}"
        )
    if audio_duration is None:
        audio_duration = estimate_duration_from_words(script_path)

    # Load products
    items: List[Dict[str, Any]] = []
    if products_json.exists():
        data = read_json(products_json)
        items = sorted(
            data.get("items", []),
            key=lambda x: x.get("rank", 999),
        )

    # Resolve visual mode for each product
    product_visuals: List[Dict[str, Any]] = []
    patient_zero = None
    truth_count = 0

    for item in items:
        rank = item.get("rank", 0)
        asin = item.get("asin", "")
        title = item.get("title", "")
        pdir = products_dir / f"p{rank:02d}"

        # Load QC if exists
        qc = None
        qc_path = pdir / "qc.json"
        if qc_path.exists():
            try:
                qc = read_json(qc_path)
            except Exception:
                qc = None

        visual = resolve_visual_mode(
            pdir, run_dir, qc, asin=asin, library_dir=library_dir,
        )

        if visual["mode"] in ("BROLL_VIDEO", "KEN_BURNS", "STILL_ONLY"):
            truth_count += 1
        elif patient_zero is None:
            patient_zero = {
                "code": "MISSING_PRODUCT_IMAGE",
                "detail": f"p{rank:02d} ({asin}) {visual['reason']}",
            }

        product_visuals.append({
            "rank": rank,
            "asin": asin,
            "title": title,
            "visual": visual,
        })

    # Product truth telemetry
    skipped_count = sum(
        1 for p in product_visuals if p["visual"]["mode"] == "SKIP"
    )
    total = max(1, len(product_visuals))
    fidelity_score = int(truth_count / total * 100)
    needs_manual_review = truth_count < min_truth_products

    # Build timeline
    segments = generate_timeline(product_visuals, audio_duration)

    # Assemble config
    config = {
        "version": RENDER_CONFIG_VERSION,
        "generated_at_utc": utc_now_iso(),
        "output": OUTPUT_DEFAULTS.copy(),
        "canvas": CANVAS_DEFAULTS.copy(),
        "audio": {
            "path": "02_audio.wav",
            "duration_sec": round(audio_duration, 3),
            **AUDIO_DEFAULTS,
        },
        "ray": RAY_DEFAULTS.copy(),
        "products": {
            "expected": len(items),
            "truth_visuals_used": truth_count,
            "skipped_count": skipped_count,
            "fidelity_score": fidelity_score,
            "min_truth_required": min_truth_products,
        },
        "segments": segments,
    }

    # Write render config atomically
    config_path = run_dir / "05_render_config.json"
    atomic_write_json(config_path, config)

    # Update manifest if it exists
    manifest_path = run_dir / "00_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        render = manifest.setdefault("render", {})
        render["render_config_path"] = "05_render_config.json"
        render["render_config_sha1"] = sha1_file(config_path)
        render["products_fidelity_score"] = fidelity_score
        render["truth_visuals_used"] = truth_count
        render["skipped_count"] = skipped_count
        render["min_truth_required"] = min_truth_products
        render["needs_manual_review"] = needs_manual_review
        render["generated_at_utc"] = utc_now_iso()
        if patient_zero:
            manifest["patient_zero"] = patient_zero
        atomic_write_json(manifest_path, manifest)

    return {
        "config": config,
        "fidelity_score": fidelity_score,
        "needs_manual_review": needs_manual_review,
        "patient_zero": patient_zero,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Render Config Generator — deterministic timeline",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument(
        "--require-audio",
        action="store_true",
        help="Refuse if 02_audio.wav missing/unreadable",
    )
    ap.add_argument(
        "--min-truth-products",
        type=int,
        default=4,
        help="Minimum products with truth visuals (default 4 of 5)",
    )
    ap.add_argument(
        "--library-dir",
        default="state/library",
        help="Truth cache library root for b-roll reuse (default: state/library)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    lib_dir = Path(args.library_dir).expanduser().resolve() if args.library_dir else None

    try:
        result = generate_render_config(
            run_dir,
            require_audio=args.require_audio,
            min_truth_products=args.min_truth_products,
            library_dir=lib_dir,
        )
        score = result["fidelity_score"]
        review = result["needs_manual_review"]
        n_seg = len(result["config"]["segments"])
        pz = result["patient_zero"]
        pz_info = f" | patient_zero={pz['code']}" if pz else ""
        print(
            f"render_config_generate: fidelity={score}/100 "
            f"| segments={n_seg} | review={review}{pz_info}"
        )
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
