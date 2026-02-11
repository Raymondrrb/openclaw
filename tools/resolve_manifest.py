#!/usr/bin/env python3
"""CLI tool for DaVinci Resolve edit manifest generation.

Generates JSON edit manifests, Resolve markers CSV, and human-readable
edit notes from a finished script + video assets folder.

Usage:
    # Scaffold a new video project folder
    python3 tools/resolve_manifest.py --scaffold --video-id my-video

    # Generate manifest from script + assets
    python3 tools/resolve_manifest.py --generate --video-id my-video --script final_script.txt

    # Generate with product metadata
    python3 tools/resolve_manifest.py --generate --video-id my-video --script final_script.txt \
        --products products.json --signature "But here's the reality check..."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, project_root
from tools.lib.notify import notify_progress
from tools.lib.pipeline_status import update_milestone
from tools.lib.resolve_schema import (
    generate_manifest,
    manifest_to_json,
    manifest_to_markers_csv,
    manifest_to_notes,
)

# Project videos live under artifacts/videos/<video_id>/
VIDEOS_BASE = Path(__file__).resolve().parent.parent / "artifacts" / "videos"

# Standard folder structure
SCAFFOLD_DIRS = [
    "audio",
    "audio/sfx",
    "visuals",
    "visuals/backgrounds",
    "visuals/products/01",
    "visuals/products/01/clips",
    "visuals/products/02",
    "visuals/products/02/clips",
    "visuals/products/03",
    "visuals/products/03/clips",
    "visuals/products/04",
    "visuals/products/04/clips",
    "visuals/products/05",
    "visuals/products/05/clips",
    "resolve",
    "exports",
]


def cmd_scaffold(video_id: str) -> int:
    """Create the standardized folder structure for a new video."""
    video_dir = VIDEOS_BASE / video_id

    if video_dir.exists():
        print(f"Video folder already exists: {video_dir}")
        print("Ensuring all subdirectories exist...")

    for subdir in SCAFFOLD_DIRS:
        (video_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Write a placeholder README
    readme = video_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {video_id}\n\n"
            "## Folder Structure\n\n"
            "```\n"
            "audio/\n"
            "  voiceover.wav       # ElevenLabs voiceover\n"
            "  music_bed.wav       # Background music\n"
            "  sfx/                # Sound effects (whoosh, ding, etc.)\n"
            "visuals/\n"
            "  thumbnail.png       # YouTube thumbnail (2048x1152)\n"
            "  backgrounds/        # Channel backgrounds\n"
            "  products/\n"
            "    01/ (to 05/)      # Product images per rank\n"
            "      amazon_*.png    # Amazon product photos\n"
            "      dzine_*.png     # Dzine-generated images\n"
            "      clips/          # Short product video clips\n"
            "resolve/\n"
            "  edit_manifest.json  # Generated edit manifest\n"
            "  markers.csv         # Resolve timeline markers\n"
            "  notes.md            # Human-readable edit notes\n"
            "exports/\n"
            "  final.mp4           # Exported video\n"
            "```\n\n"
            "## Workflow\n\n"
            "1. Place script as `script.txt` in this folder\n"
            "2. Add voiceover + music to `audio/`\n"
            "3. Add product images to `visuals/products/NN/`\n"
            "4. Run: `python3 tools/resolve_manifest.py --generate "
            f"--video-id {video_id} --script script.txt`\n"
            "5. Open DaVinci Resolve, import media, import markers.csv\n"
            "6. Follow notes.md for editing instructions\n"
        )

    print(f"Scaffolded: {video_dir}")
    print(f"  {len(SCAFFOLD_DIRS)} directories created")
    print(f"\nNext steps:")
    print(f"  1. Place your script as: {video_dir}/script.txt")
    print(f"  2. Add voiceover to: {video_dir}/audio/voiceover.wav")
    print(f"  3. Add product images to: {video_dir}/visuals/products/NN/")
    print(f"  4. Run: python3 tools/resolve_manifest.py --generate --video-id {video_id} --script script.txt")
    return 0


def cmd_generate(
    video_id: str,
    script_path: str,
    products_path: str | None,
    signature: str,
    signature_type: str,
    fps: int,
) -> int:
    """Generate edit manifest, markers CSV, and notes from script + assets."""
    video_dir = VIDEOS_BASE / video_id

    if not video_dir.is_dir():
        print(f"Video folder not found: {video_dir}", file=sys.stderr)
        print(f"Run: python3 tools/resolve_manifest.py --scaffold --video-id {video_id}", file=sys.stderr)
        return 1

    # Read script
    script_file = Path(script_path)
    if not script_file.is_absolute():
        # Try relative to video dir first, then cwd
        if (video_dir / script_file).is_file():
            script_file = video_dir / script_file
        elif not script_file.is_file():
            print(f"Script not found: {script_path}", file=sys.stderr)
            return 1

    script_text = script_file.read_text(encoding="utf-8")
    if not script_text.strip():
        print("Script file is empty", file=sys.stderr)
        return 1

    # Load product metadata if provided
    product_names: dict[int, str] = {}
    product_benefits: dict[int, list[str]] = {}

    if products_path:
        pf = Path(products_path)
        if not pf.is_absolute():
            if (video_dir / pf).is_file():
                pf = video_dir / pf
        if pf.is_file():
            data = json.loads(pf.read_text(encoding="utf-8"))
            for entry in data.get("products", []):
                rank = entry.get("rank")
                if rank:
                    product_names[rank] = entry.get("name", "")
                    product_benefits[rank] = entry.get("benefits", [])
            print(f"Loaded {len(product_names)} product(s) from {pf.name}")
        else:
            print(f"Products file not found: {products_path} (continuing without)", file=sys.stderr)

    # Generate
    print(f"Generating manifest for {video_id}...")
    manifest = generate_manifest(
        video_id=video_id,
        script_text=script_text,
        video_dir=video_dir,
        product_names=product_names,
        product_benefits=product_benefits,
        signature_line=signature,
        signature_type=signature_type,
        fps=fps,
    )

    # Write outputs
    resolve_dir = video_dir / "resolve"
    resolve_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = resolve_dir / "edit_manifest.json"
    manifest_path.write_text(manifest_to_json(manifest), encoding="utf-8")
    print(f"  Manifest: {manifest_path}")
    update_milestone(video_id, "edit_prep", "manifest_generated")

    markers_path = resolve_dir / "markers.csv"
    markers_path.write_text(manifest_to_markers_csv(manifest), encoding="utf-8")
    print(f"  Markers:  {markers_path}")
    update_milestone(video_id, "edit_prep", "markers_generated")

    notes_path = resolve_dir / "notes.md"
    notes_path.write_text(manifest_to_notes(manifest), encoding="utf-8")
    print(f"  Notes:    {notes_path}")
    update_milestone(video_id, "edit_prep", "notes_generated")

    notify_progress(
        video_id, "edit_prep", "notes_generated",
        next_action="Open DaVinci Resolve and edit",
        details=[
            f"{len(manifest.segments)} segments, {manifest.total_duration_s:.0f}s",
            f"Outputs: {resolve_dir}",
        ],
    )

    # Summary
    print(f"\nManifest summary:")
    print(f"  Duration: {manifest.total_duration_s:.0f}s ({manifest.total_duration_s/60:.1f} min)")
    print(f"  Segments: {len(manifest.segments)}")
    total_visuals = sum(len(s.visuals) for s in manifest.segments)
    total_overlays = sum(len(s.overlays) for s in manifest.segments) + len(manifest.global_overlays)
    print(f"  Visuals:  {total_visuals}")
    print(f"  Overlays: {total_overlays}")
    print(f"  Voiceover: {manifest.voiceover_file or 'NOT FOUND'}")
    print(f"  Music:     {manifest.music.file or 'NOT FOUND'}")

    missing = []
    if not manifest.voiceover_file:
        missing.append("audio/voiceover.wav")
    if not manifest.music.file:
        missing.append("audio/music_bed.wav")
    for seg in manifest.segments:
        if not seg.visuals:
            missing.append(f"visuals/products/{seg.rank:02d}/ (no images)")

    if missing:
        print(f"\nMissing assets:")
        for m in missing:
            print(f"  - {m}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DaVinci Resolve edit manifest generator for Amazon product ranking videos"
    )
    parser.add_argument("--video-id", required=True, help="Video project identifier (e.g. my-video)")
    parser.add_argument("--scaffold", action="store_true", help="Create folder structure for a new video")
    parser.add_argument("--generate", action="store_true", help="Generate manifest from script + assets")
    parser.add_argument("--script", default="script.txt", help="Path to script file (default: script.txt)")
    parser.add_argument("--products", default=None, help="Path to products.json with names/benefits")
    parser.add_argument("--signature", default="", help="Channel signature line for this video")
    parser.add_argument(
        "--signature-type", default="reality_check",
        choices=["reality_check", "micro_humor", "micro_comparison"],
        help="Signature moment type",
    )
    parser.add_argument("--fps", type=int, default=30, help="Timeline FPS (default: 30)")
    args = parser.parse_args()

    load_env_file(project_root() / ".env")

    if not args.scaffold and not args.generate:
        print("Specify --scaffold or --generate (or both)", file=sys.stderr)
        parser.print_help()
        return 2

    rc = 0
    if args.scaffold:
        rc = cmd_scaffold(args.video_id)
        if rc != 0:
            return rc

    if args.generate:
        rc = cmd_generate(
            video_id=args.video_id,
            script_path=args.script,
            products_path=args.products,
            signature=args.signature,
            signature_type=args.signature_type,
            fps=args.fps,
        )

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
