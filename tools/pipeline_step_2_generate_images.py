#!/usr/bin/env python3
"""
Pipeline Step 2: Generate images from structured script.

Reads script.json and generates Dzine image prompts + assets manifest.
When Dzine API is configured, generates images directly.
Without API, produces the prompt pack for manual Dzine generation.

Usage:
    python3 tools/pipeline_step_2_generate_images.py --run-dir content/pipeline_runs/RUN_ID/

Input:  {run_dir}/script.json
Output: {run_dir}/assets_manifest.json
        {run_dir}/dzine_prompts.json
        {run_dir}/assets/  (images when API available)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_pipeline_lib import extract_dzine_scenes


def generate_dzine_prompts_from_scenes(scenes: list[dict], channel_name: str) -> list[dict]:
    """Convert visual_hint scenes into Dzine-ready prompts with 3 variants each."""
    prompts = []
    base_identity = (
        "Character: Ray, same face identity as channel avatar, confident reviewer style. "
        f"{channel_name} brand look: clean high-contrast lighting, soft neutral backgrounds, "
        "realistic skin tones, no cartoon style."
    )

    for i, scene in enumerate(scenes):
        hint = scene["visual_hint"]
        product = scene.get("product_name", "")
        seg_type = scene["segment_type"]

        prompt_entry = {
            "scene_index": i,
            "segment_type": seg_type,
            "product_name": product,
            "original_hint": hint,
            "variants": [
                {
                    "id": f"scene_{i:02d}_v1",
                    "model": "NanoBanana Pro",
                    "prompt": f"Model: NanoBanana Pro. {base_identity} {hint}. "
                              "No text in image, no price in image, leave negative space for DaVinci overlays.",
                },
                {
                    "id": f"scene_{i:02d}_v2",
                    "model": "NanoBanana Pro",
                    "prompt": f"Model: NanoBanana Pro. Alternative angle: {hint}. "
                              "High detail, coherent color palette, no text in image.",
                },
                {
                    "id": f"scene_{i:02d}_v3",
                    "model": "NanoBanana Pro",
                    "prompt": f"Model: NanoBanana Pro. Close-up detail of: {hint}. "
                              "Cinematic framing, product clearly visible, no embedded text or pricing.",
                },
            ],
        }
        prompts.append(prompt_entry)

    return prompts


def build_assets_manifest(prompts: list[dict], assets_dir: Path) -> dict:
    """Build assets manifest mapping products to their image paths.

    Checks for existing generated images. If none exist, marks as pending.
    """
    products = {}
    for prompt in prompts:
        product_name = prompt.get("product_name", "general")
        if not product_name:
            product_name = f"scene_{prompt['scene_index']:02d}"

        if product_name not in products:
            products[product_name] = {
                "name": product_name,
                "images": [],
                "status": "pending",
            }

        for variant in prompt.get("variants", []):
            vid = variant["id"]
            img_path = assets_dir / f"{vid}.png"
            entry = {
                "variant_id": vid,
                "path": str(img_path),
                "exists": img_path.exists(),
                "segment_type": prompt["segment_type"],
            }
            products[product_name]["images"].append(entry)

        # Mark as ready if all images exist
        all_exist = all(img["exists"] for img in products[product_name]["images"])
        if all_exist and products[product_name]["images"]:
            products[product_name]["status"] = "ready"

    return {
        "products": list(products.values()),
        "total_images": sum(len(p["images"]) for p in products.values()),
        "ready_images": sum(1 for p in products.values() for img in p["images"] if img["exists"]),
    }


def main():
    parser = argparse.ArgumentParser(description="Step 2: Generate images from script")
    parser.add_argument("--run-dir", required=True, help="Pipeline run directory")
    parser.add_argument("--channel-name", default="Rayviews")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    script_path = run_dir / "script.json"
    manifest_path = run_dir / "assets_manifest.json"
    prompts_path = run_dir / "dzine_prompts.json"

    if not script_path.exists():
        print(f"[ERROR] script.json not found at {script_path}")
        print("[HINT] Run pipeline_step_1_generate_script.py first")
        sys.exit(1)

    if manifest_path.exists():
        print(f"[SKIP] assets_manifest.json already exists at {manifest_path}")
        sys.exit(0)

    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    scenes = extract_dzine_scenes(script_data)

    if not scenes:
        print("[WARN] No visual_hint scenes found in script.json")
        sys.exit(1)

    print(f"[STEP 2] Generating Dzine prompts for {len(scenes)} scenes")

    prompts = generate_dzine_prompts_from_scenes(scenes, args.channel_name)

    # Write Dzine prompts
    tmp = prompts_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, prompts_path)
    print(f"[OK] Dzine prompts: {len(prompts)} scenes × 3 variants → {prompts_path}")

    # Build and write assets manifest
    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_assets_manifest(prompts, assets_dir)

    tmp = manifest_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, manifest_path)

    ready = manifest["ready_images"]
    total = manifest["total_images"]
    print(f"[DONE] Assets manifest: {ready}/{total} images ready → {manifest_path}")

    if ready < total:
        print(f"[ACTION] Generate {total - ready} images in Dzine using prompts in {prompts_path}")
        print("         When Dzine API key is configured, this step will generate automatically.")


if __name__ == "__main__":
    main()
