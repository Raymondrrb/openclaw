#!/usr/bin/env python3
"""Rayviews → RayVault converter — bridge between pipeline edit plans and DaVinci render configs.

Reads Rayviews pipeline_runs/{run_id}/ artifacts (timestamps, products, assets, script)
and produces a RayVault-compatible directory structure with:
  - 00_manifest.json
  - 01_script.txt
  - 02_audio.wav  (ffmpeg convert from voiceover.mp3)
  - 03_frame.png  (dark frame or provided)
  - 05_render_config.json (v1.3 typed segments)
  - products/p{rank:02d}/source_images/{01_main,02_glam,03_broll}.png
  - publish/overlays/overlays_index.json

Usage:
    python3 tools/markdown_to_render_config.py --run-id portable_monitors_2026-02-16_1254
    python3 tools/pipeline.py convert-to-rayvault --run-id portable_monitors_2026-02-16_1254
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
RUNS_DIR = BASE_DIR / "pipeline_runs"

# ---------------------------------------------------------------------------
# RayVault imports (with graceful fallback)
# ---------------------------------------------------------------------------

_RAYVAULT_AVAILABLE = False

try:
    from rayvault.segment_id import ensure_segment_ids
    from rayvault.io import atomic_write_json, sha1_file, utc_now_iso
    from rayvault.policies import (
        OUTPUT_W, OUTPUT_H, OUTPUT_FPS, OUTPUT_CRF, OUTPUT_PRESET,
        AUDIO_SAMPLE_RATE, LUFS_TARGET, TRUE_PEAK_MAX,
        MAX_STATIC_SECONDS, MIN_SEGMENT_TYPE_VARIETY,
    )
    _RAYVAULT_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Fallback constants (used when rayvault is not importable)
# ---------------------------------------------------------------------------

if not _RAYVAULT_AVAILABLE:
    OUTPUT_W = 1920
    OUTPUT_H = 1080
    OUTPUT_FPS = 30
    OUTPUT_CRF = 18
    OUTPUT_PRESET = "slow"
    AUDIO_SAMPLE_RATE = 48000
    LUFS_TARGET = -14.0
    TRUE_PEAK_MAX = -0.5
    MAX_STATIC_SECONDS = 18
    MIN_SEGMENT_TYPE_VARIETY = 2

    def ensure_segment_ids(segments):
        """Fallback: compute segment IDs locally."""
        for seg in segments:
            if "segment_id" not in seg:
                canon = {k: v for k, v in sorted(seg.items())
                         if k not in ("segment_id",)}
                blob = json.dumps(canon, separators=(",", ":"), sort_keys=True).encode()
                seg["segment_id"] = hashlib.sha1(blob).hexdigest()[:16]
        return segments

    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def atomic_write_json(path: Path, data: Any) -> None:
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

RENDER_CONFIG_VERSION = "1.3"

OUTPUT_DEFAULTS = {
    "w": OUTPUT_W, "h": OUTPUT_H, "fps": OUTPUT_FPS,
    "vcodec": "libx264", "acodec": "aac",
    "crf": OUTPUT_CRF, "preset": OUTPUT_PRESET, "pix_fmt": "yuv420p",
}
CANVAS_DEFAULTS = {"w": OUTPUT_W, "h": OUTPUT_H, "fps": OUTPUT_FPS}
AUDIO_DEFAULTS = {
    "normalize_lufs": LUFS_TARGET, "true_peak": TRUE_PEAK_MAX,
    "sample_rate": AUDIO_SAMPLE_RATE,
    "voice_track_gain_db": 0.0, "music_bed_gain_db": -18.0, "limiter": True,
}
RAY_DEFAULTS = {
    "frame_path": "03_frame.png",
    "face_safe_box_norm": {"x": 0.33, "y": 0.18, "w": 0.34, "h": 0.52},
}

# Variant-to-name mapping for product images
VARIANT_MAP = {
    "variant_01.png": "01_main.png",
    "variant_02.png": "02_glam.png",
    "variant_03.png": "03_broll.png",
}

# Script IDs that map to intro/outro segment types
NARRATION_TYPE_MAP = {
    "hook": "intro",
    "credibility": "intro",
    "winner": "outro",
    "outro": "outro",
    "tier_break": "intro",
    "comparison": "outro",
    "myth_bust": "intro",
    "winner_tease": "intro",
    "surprise_pick": "outro",
}

# ---------------------------------------------------------------------------
# 1. Load Rayviews run
# ---------------------------------------------------------------------------


def load_rayviews_run(run_dir: Path) -> Dict[str, Any]:
    """Load all Rayviews run artifacts. Validate required files exist."""
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    files = {
        "run.json": run_dir / "run.json",
        "products.json": run_dir / "products.json",
        "script.json": run_dir / "script.json",
        "assets_manifest.json": run_dir / "assets_manifest.json",
        "timestamps.json": run_dir / "voice" / "timestamps.json",
    }

    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required files: {', '.join(missing)}")

    data = {}
    for name, path in files.items():
        with open(path, "r", encoding="utf-8") as f:
            data[name] = json.load(f)

    return data


# ---------------------------------------------------------------------------
# 2. Convert MP3 → WAV
# ---------------------------------------------------------------------------


def convert_mp3_to_wav(mp3_path: Path, wav_path: Path) -> bool:
    """Convert voiceover.mp3 to 48kHz mono WAV via ffmpeg. Returns True on success."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found. Install: brew install ffmpeg"
        )
    if not mp3_path.exists():
        return False

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = wav_path.with_suffix(".wav.tmp")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path),
             "-ar", str(AUDIO_SAMPLE_RATE), "-ac", "1", str(tmp)],
            check=True, capture_output=True,
        )
        os.replace(tmp, wav_path)
        return True
    except subprocess.CalledProcessError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg conversion failed: {e.stderr.decode()[:200]}") from e


# ---------------------------------------------------------------------------
# 3. Ensure frame
# ---------------------------------------------------------------------------


def ensure_frame(rayvault_dir: Path, frame_path: Optional[Path] = None) -> Path:
    """Copy provided frame or generate a dark 1920x1080 frame via ffmpeg."""
    dest = rayvault_dir / "03_frame.png"
    if dest.exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)

    if frame_path and frame_path.exists():
        shutil.copy2(frame_path, dest)
        return dest

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found. Install: brew install ffmpeg")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "color=c=0x1a1a2e:s=1920x1080:d=1",
         "-frames:v", "1", str(dest)],
        check=True, capture_output=True,
    )
    return dest


# ---------------------------------------------------------------------------
# 4. Copy product images
# ---------------------------------------------------------------------------


def copy_product_images(
    run_dir: Path, rayvault_dir: Path, assets_manifest: Dict[str, Any],
) -> Dict[int, Dict[str, str]]:
    """Copy variant images to RayVault product directories.

    Returns {rank: {variant_key: relative_path}} for found images.
    """
    product_images: Dict[int, Dict[str, str]] = {}

    for asset in assets_manifest.get("assets", []):
        rank = asset["product_rank"]
        dzine_images = asset.get("files", {}).get("dzine_images", [])
        rank_images: Dict[str, str] = {}

        for src_rel in dzine_images:
            src = run_dir / src_rel
            variant_name = Path(src_rel).name  # e.g. variant_01.png
            dest_name = VARIANT_MAP.get(variant_name)
            if not dest_name:
                continue

            dest_rel = f"products/p{rank:02d}/source_images/{dest_name}"
            dest = rayvault_dir / dest_rel

            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                rank_images[dest_name] = dest_rel
            # else: image missing, will use SKIP mode

        product_images[rank] = rank_images

    return product_images


# ---------------------------------------------------------------------------
# 5. Build segment map
# ---------------------------------------------------------------------------


def build_segment_map(
    timestamps: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Parse timestamp segments into typed entries with rank/kind info.

    Returns list of dicts with keys:
      script_id, start_ms, end_ms, seg_type, rank (optional), kind (optional)
    """
    product_re = re.compile(r"^p(\d+)_intro_(AVATAR_TALK|PRODUCT_GLAM|BROLL)$")
    entries = []

    for seg in timestamps.get("segments", []):
        script_id = seg["script_id"]
        start_ms = seg["start_ms"]
        end_ms = seg["end_ms"]

        entry = {
            "script_id": script_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
        }

        m = product_re.match(script_id)
        if m:
            entry["seg_type"] = "product"
            entry["rank"] = int(m.group(1))
            entry["kind"] = m.group(2)
        elif script_id in NARRATION_TYPE_MAP:
            entry["seg_type"] = NARRATION_TYPE_MAP[script_id]
        else:
            entry["seg_type"] = "intro"  # fallback for unknown narration

        entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# 6. Build RayVault segments
# ---------------------------------------------------------------------------


def _image_for_kind(kind: str) -> str:
    """Map sub-segment kind to image name."""
    return {
        "AVATAR_TALK": "01_main.png",
        "PRODUCT_GLAM": "02_glam.png",
        "BROLL": "03_broll.png",
    }.get(kind, "01_main.png")


def build_rayvault_segments(
    segment_map: List[Dict[str, Any]],
    product_images: Dict[int, Dict[str, str]],
    products_data: Dict[str, Any],
    fps: int = OUTPUT_FPS,
) -> List[Dict[str, Any]]:
    """Convert segment map entries to RayVault v1.3 segments."""
    # Build title lookup from products
    title_map: Dict[int, str] = {}
    asin_map: Dict[int, str] = {}
    for p in products_data.get("products", []):
        title_map[p["rank"]] = p.get("title", "")[:60]
        asin_map[p["rank"]] = p.get("asin", "")

    segments = []

    for idx, entry in enumerate(segment_map):
        t0 = round(entry["start_ms"] / 1000, 3)
        t1 = round(entry["end_ms"] / 1000, 3)
        frames = round((t1 - t0) * fps)
        seg_type = entry["seg_type"]

        seg: Dict[str, Any] = {
            "id": f"seg_{idx:03d}",
            "type": seg_type,
            "t0": t0,
            "t1": t1,
            "frames": frames,
        }

        if seg_type == "product":
            rank = entry["rank"]
            kind = entry.get("kind", "AVATAR_TALK")
            seg["rank"] = rank
            seg["asin"] = asin_map.get(rank, "")

            if rank in title_map:
                seg["title"] = title_map[rank]

            # Resolve visual
            image_name = _image_for_kind(kind)
            rank_images = product_images.get(rank, {})

            if image_name in rank_images:
                seg["visual"] = {
                    "mode": "KEN_BURNS",
                    "source": rank_images[image_name],
                    "reason": "truth_main_image",
                }
            else:
                seg["visual"] = {
                    "mode": "SKIP",
                    "source": None,
                    "reason": "image_not_available",
                }

        segments.append(seg)

    return segments


# ---------------------------------------------------------------------------
# 7. Build render config
# ---------------------------------------------------------------------------


def build_render_config(
    segments: List[Dict[str, Any]],
    audio_duration_sec: float,
    run_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Assemble full 05_render_config.json matching v1.3 schema."""
    # Product truth telemetry
    product_segs = [s for s in segments if s.get("type") == "product"]
    truth_count = sum(
        1 for s in product_segs
        if s.get("visual", {}).get("mode") in ("KEN_BURNS", "BROLL_VIDEO", "STILL_ONLY")
    )
    skipped_count = sum(
        1 for s in product_segs
        if s.get("visual", {}).get("mode") == "SKIP"
    )
    total_products = max(1, len(set(s.get("rank") for s in product_segs if s.get("rank"))))
    fidelity_score = int(truth_count / max(1, len(product_segs)) * 100)

    config = {
        "version": RENDER_CONFIG_VERSION,
        "generated_at_utc": utc_now_iso(),
        "generator": "markdown_to_render_config",
        "output": OUTPUT_DEFAULTS.copy(),
        "canvas": CANVAS_DEFAULTS.copy(),
        "audio": {
            "path": "02_audio.wav",
            "duration_sec": round(audio_duration_sec, 3),
            **AUDIO_DEFAULTS,
        },
        "ray": RAY_DEFAULTS.copy(),
        "products": {
            "expected": total_products,
            "truth_visuals_used": truth_count,
            "skipped_count": skipped_count,
            "fidelity_score": fidelity_score,
            "min_truth_required": 4,
        },
        "segments": segments,
        "pacing": {
            "ok": True,
            "variety_warning": False,
            "max_static_seconds": MAX_STATIC_SECONDS,
            "errors": [],
            "warnings": [],
        },
    }

    return config


# ---------------------------------------------------------------------------
# 8. Build manifest
# ---------------------------------------------------------------------------


def build_manifest(
    run_id: str,
    rayvault_dir: Path,
    products_data: Dict[str, Any],
    audio_available: bool,
) -> Dict[str, Any]:
    """Assemble 00_manifest.json."""
    products = products_data.get("products", [])
    status = "READY_FOR_RENDER" if audio_available else "WAITING_ASSETS"

    manifest = {
        "version": "1.3",
        "run_id": run_id,
        "status": status,
        "created_at_utc": utc_now_iso(),
        "generator": "markdown_to_render_config",
        "metadata": {
            "identity": {
                "confidence": "HIGH",
                "source": "rayviews_pipeline",
            },
            "product_count": len(products),
        },
        "render": {
            "davinci_required": True,
            "render_config_path": "05_render_config.json",
        },
        "audio": {
            "voiceover": {
                "path": "02_audio.wav",
                "available": audio_available,
            },
        },
        "products": [
            {
                "rank": p["rank"],
                "asin": p.get("asin", ""),
                "title": p.get("title", "")[:60],
            }
            for p in products
        ],
    }

    return manifest


# ---------------------------------------------------------------------------
# 9. Create minimal overlays index
# ---------------------------------------------------------------------------


def create_minimal_overlays_index(
    rayvault_dir: Path,
    products_data: Dict[str, Any],
) -> Path:
    """Write overlays_index.json with all HIDE. Satisfies gate_essential_files()."""
    products = products_data.get("products", [])

    index = {
        "version": "1.0",
        "episode_truth_tier": "GREEN",
        "generated_at_utc": utc_now_iso(),
        "items": [
            {
                "product_rank": p["rank"],
                "asin": p.get("asin", ""),
                "display_mode": "HIDE",
                "overlay_path": None,
            }
            for p in products
        ],
    }

    dest = rayvault_dir / "publish" / "overlays" / "overlays_index.json"
    atomic_write_json(dest, index)
    return dest


# ---------------------------------------------------------------------------
# 10. Extract script text
# ---------------------------------------------------------------------------


def extract_script_text(script_data: Dict[str, Any]) -> str:
    """Extract full narration text from script.json for 01_script.txt."""
    parts = []
    for seg in script_data.get("structure", []):
        voice = seg.get("voice_text", "")
        if voice:
            parts.append(voice)
        for sub in seg.get("segments", []):
            sv = sub.get("voice_text", "")
            if sv:
                parts.append(sv)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 11. Build products.json for RayVault
# ---------------------------------------------------------------------------


def build_rayvault_products_json(
    products_data: Dict[str, Any],
    product_images: Dict[int, Dict[str, str]],
) -> Dict[str, Any]:
    """Build products/products.json in RayVault format."""
    items = []
    for p in products_data.get("products", []):
        rank = p["rank"]
        rank_imgs = product_images.get(rank, {})
        main_img = rank_imgs.get("01_main.png")

        item = {
            "rank": rank,
            "asin": p.get("asin", ""),
            "title": p.get("title", "")[:60],
            "price": p.get("price", 0),
        }
        if main_img:
            item["main_image"] = main_img
        items.append(item)

    return {"items": items}


# ---------------------------------------------------------------------------
# 12. Orchestrator
# ---------------------------------------------------------------------------


def convert(
    run_id: str,
    frame_path: Optional[str] = None,
    force: bool = False,
    dry_run: bool = False,
    no_overlays: bool = False,
) -> Dict[str, Any]:
    """Main orchestrator: convert Rayviews run → RayVault directory.

    Returns result dict with status, paths, and any warnings.
    """
    run_dir = RUNS_DIR / run_id
    rayvault_dir = run_dir / "rayvault"

    if rayvault_dir.exists() and not force:
        config_path = rayvault_dir / "05_render_config.json"
        if config_path.exists():
            raise FileExistsError(
                f"RayVault output already exists: {rayvault_dir}. Use --force to overwrite."
            )

    # Load all Rayviews artifacts
    data = load_rayviews_run(run_dir)
    run_config = data["run.json"]
    products_data = data["products.json"]
    script_data = data["script.json"]
    assets_manifest = data["assets_manifest.json"]
    timestamps = data["timestamps.json"]

    warnings: List[str] = []

    if dry_run:
        seg_map = build_segment_map(timestamps)
        return {
            "status": "DRY_RUN",
            "run_id": run_id,
            "segments_planned": len(seg_map),
            "products": len(products_data.get("products", [])),
            "estimated_duration_sec": round(timestamps.get("estimated_duration_ms", 0) / 1000, 1),
        }

    # Create output directory
    rayvault_dir.mkdir(parents=True, exist_ok=True)

    # --- Audio conversion ---
    mp3_path = run_dir / "voice" / "voiceover.mp3"
    wav_path = rayvault_dir / "02_audio.wav"
    audio_available = False
    audio_duration_sec = timestamps.get("estimated_duration_ms", 0) / 1000

    if mp3_path.exists():
        convert_mp3_to_wav(mp3_path, wav_path)
        audio_available = True
        # Try to get actual duration from WAV
        try:
            import wave
            with wave.open(str(wav_path), "rb") as w:
                rate = w.getframerate()
                if rate > 0:
                    audio_duration_sec = w.getnframes() / float(rate)
        except Exception:
            pass
    else:
        # Check if wav already exists in voice/
        wav_source = run_dir / "voice" / "voiceover.wav"
        if wav_source.exists():
            shutil.copy2(wav_source, wav_path)
            audio_available = True
        else:
            warnings.append(
                "WAITING_ASSETS: voiceover.mp3 not found, using estimated duration"
            )

    # --- Frame ---
    frame = Path(frame_path) if frame_path else None
    ensure_frame(rayvault_dir, frame)

    # --- Copy product images ---
    product_images = copy_product_images(run_dir, rayvault_dir, assets_manifest)

    # Count missing images
    for asset in assets_manifest.get("assets", []):
        rank = asset["product_rank"]
        expected = len(asset.get("files", {}).get("dzine_images", []))
        actual = len(product_images.get(rank, {}))
        if actual < expected:
            warnings.append(f"p{rank:02d}: {actual}/{expected} images copied")

    # --- Build segments ---
    seg_map = build_segment_map(timestamps)
    segments = build_rayvault_segments(seg_map, product_images, products_data)

    # Add deterministic segment IDs
    segments = ensure_segment_ids(segments)

    # --- Build render config ---
    render_config = build_render_config(segments, audio_duration_sec, run_config)
    atomic_write_json(rayvault_dir / "05_render_config.json", render_config)

    # --- Build manifest ---
    manifest = build_manifest(run_id, rayvault_dir, products_data, audio_available)

    # Add render config hash
    config_path = rayvault_dir / "05_render_config.json"
    manifest["render"]["render_config_sha1"] = sha1_file(config_path)
    manifest["render"]["products_fidelity_score"] = render_config["products"]["fidelity_score"]

    atomic_write_json(rayvault_dir / "00_manifest.json", manifest)

    # --- Script text ---
    script_text = extract_script_text(script_data)
    script_dest = rayvault_dir / "01_script.txt"
    script_dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = script_dest.with_suffix(".txt.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(script_text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, script_dest)

    # --- Products JSON ---
    rv_products = build_rayvault_products_json(products_data, product_images)
    atomic_write_json(rayvault_dir / "products" / "products.json", rv_products)

    # --- Overlays ---
    if not no_overlays:
        create_minimal_overlays_index(rayvault_dir, products_data)

    status = "READY_FOR_RENDER" if audio_available else "WAITING_ASSETS"

    result = {
        "status": status,
        "run_id": run_id,
        "rayvault_dir": str(rayvault_dir),
        "segments": len(segments),
        "audio_duration_sec": round(audio_duration_sec, 1),
        "fidelity_score": render_config["products"]["fidelity_score"],
        "warnings": warnings,
    }

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Rayviews → RayVault converter",
    )
    ap.add_argument("--run-id", required=True, help="Pipeline run ID")
    ap.add_argument("--frame-path", default=None, help="Path to 03_frame.png (or generate dark)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing output")
    ap.add_argument("--dry-run", action="store_true", help="Show plan without writing files")
    ap.add_argument("--no-overlays", action="store_true", help="Skip overlays_index.json")
    args = ap.parse_args(argv)

    try:
        result = convert(
            run_id=args.run_id,
            frame_path=args.frame_path,
            force=args.force,
            dry_run=args.dry_run,
            no_overlays=args.no_overlays,
        )

        if args.dry_run:
            print(f"[DRY RUN] {result['segments_planned']} segments, "
                  f"{result['products']} products, "
                  f"~{result['estimated_duration_sec']}s")
            return 0

        status = result["status"]
        n_seg = result["segments"]
        fidelity = result["fidelity_score"]
        duration = result["audio_duration_sec"]

        print(f"[OK] convert-to-rayvault: {status}")
        print(f"     segments={n_seg} | fidelity={fidelity}/100 | duration={duration}s")
        print(f"     output: {result['rayvault_dir']}")

        for w in result.get("warnings", []):
            print(f"     [WARN] {w}")

        return 0

    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    except FileExistsError as e:
        print(f"[SKIP] {e}", file=sys.stderr)
        return 0
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
