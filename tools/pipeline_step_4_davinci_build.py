#!/usr/bin/env python3
"""
Pipeline Step 4: Build DaVinci Resolve timeline from structured data.

Reads script.json + assets_manifest.json + voice_manifest.json and creates
a DaVinci Resolve project with automated timeline assembly.

Uses the DaVinci Resolve scripting API (via resolve_bridge.py) when available.
Without Resolve running, produces a timeline_plan.json for manual assembly.

Usage:
    python3 tools/pipeline_step_4_davinci_build.py --run-dir content/pipeline_runs/RUN_ID/

Input:  {run_dir}/script.json
        {run_dir}/assets_manifest.json
        {run_dir}/voice_manifest.json
Output: {run_dir}/timeline_plan.json
        {run_dir}/render_ready.flag (when timeline is built)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_pipeline_lib import extract_davinci_segments


# DaVinci track layout (matches SOP)
TRACK_LAYOUT = {
    "V1": "main scenes",
    "V2": "product overlays and cut-ins",
    "V3": "text/captions",
    "A1": "ElevenLabs VO",
    "A2": "music bed",
    "A3": "SFX",
}

PROJECT_SETTINGS = {
    "resolution": "1920x1080",
    "fps": 30,
    "audio_sample_rate": 48000,
    "vo_loudness_target": "-14 LUFS",
}


def build_timeline_plan(
    script_data: dict,
    assets_manifest: dict,
    voice_manifest: dict,
) -> dict:
    """Build a detailed timeline plan that maps segments to tracks."""
    timeline_segments = extract_davinci_segments(script_data)

    # Map product names to asset paths
    product_assets = {}
    for prod in assets_manifest.get("products", []):
        name = prod["name"]
        product_assets[name] = [
            img["path"] for img in prod.get("images", [])
            if img.get("exists", False)
        ]

    # Map segment IDs to voice files
    # Voice IDs are "seg_00_hook" while DaVinci IDs are "seg_00", so index by base form
    voice_files = {}
    for vseg in voice_manifest.get("segments", []):
        full_id = vseg["segment_id"]
        parts = full_id.split("_")
        base_id = "_".join(parts[:2]) if len(parts) >= 2 else full_id
        voice_files[base_id] = {
            "audio_file": vseg["audio_file"],
            "audio_exists": vseg.get("audio_exists", False),
            "estimated_seconds": vseg.get("estimated_seconds", 0),
        }

    # Build timeline entries
    timeline = []
    cumulative_seconds = 0.0

    for seg in timeline_segments:
        seg_id = seg["segment_id"]
        product = seg.get("product_name", "")
        est_sec = seg["estimated_seconds"]

        entry = {
            "segment_id": seg_id,
            "type": seg["type"],
            "product_name": product,
            "start_seconds": round(cumulative_seconds, 1),
            "duration_seconds": est_sec,
            "end_seconds": round(cumulative_seconds + est_sec, 1),
            "tracks": {},
        }

        # A1: voice
        voice = voice_files.get(seg_id, {})
        entry["tracks"]["A1"] = {
            "type": "audio",
            "file": voice.get("audio_file", ""),
            "ready": voice.get("audio_exists", False),
        }

        # V1: main scene (from assets)
        if product and product in product_assets and product_assets[product]:
            assets = product_assets[product]
            # Cycle through available assets
            asset_idx = timeline_segments.index(seg) % len(assets)
            entry["tracks"]["V1"] = {
                "type": "image",
                "file": assets[asset_idx] if asset_idx < len(assets) else "",
                "ready": bool(assets),
                "motion": "ken_burns",
            }
        elif seg.get("has_visual"):
            entry["tracks"]["V1"] = {
                "type": "image",
                "file": "",
                "ready": False,
                "motion": "ken_burns",
                "note": "visual_hint exists but no generated image yet",
            }

        # V3: text overlay for specific segment types
        if seg["type"] in ("PRODUCT_INTRO", "PRODUCT_RANK", "WINNER_REINFORCEMENT"):
            entry["tracks"]["V3"] = {
                "type": "text_overlay",
                "content": product or "Recap",
                "style": "lower_third",
            }

        cumulative_seconds += est_sec
        timeline.append(entry)

    # Readiness check
    audio_ready = all(
        t.get("tracks", {}).get("A1", {}).get("ready", False)
        for t in timeline
    )
    video_ready = all(
        not t.get("tracks", {}).get("V1") or t["tracks"]["V1"].get("ready", False)
        for t in timeline
    )

    return {
        "project_settings": PROJECT_SETTINGS,
        "track_layout": TRACK_LAYOUT,
        "total_duration_seconds": round(cumulative_seconds, 1),
        "total_segments": len(timeline),
        "audio_ready": audio_ready,
        "video_ready": video_ready,
        "render_ready": audio_ready and video_ready,
        "timeline": timeline,
    }


def main():
    parser = argparse.ArgumentParser(description="Step 4: Build DaVinci timeline")
    parser.add_argument("--run-dir", required=True, help="Pipeline run directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    script_path = run_dir / "script.json"
    assets_path = run_dir / "assets_manifest.json"
    voice_path = run_dir / "voice_manifest.json"
    plan_path = run_dir / "timeline_plan.json"
    flag_path = run_dir / "render_ready.flag"

    # Verify prerequisites
    missing = []
    if not script_path.exists():
        missing.append("script.json (run step 1)")
    if not assets_path.exists():
        missing.append("assets_manifest.json (run step 2)")
    if not voice_path.exists():
        missing.append("voice_manifest.json (run step 3)")

    if missing:
        print("[ERROR] Missing prerequisites:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)

    if flag_path.exists():
        print(f"[SKIP] render_ready.flag already exists at {flag_path}")
        sys.exit(0)

    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    assets_data = json.loads(assets_path.read_text(encoding="utf-8"))
    voice_data = json.loads(voice_path.read_text(encoding="utf-8"))

    print(f"[STEP 4] Building DaVinci timeline plan")

    plan = build_timeline_plan(script_data, assets_data, voice_data)

    tmp = plan_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, plan_path)

    dur_min = round(plan["total_duration_seconds"] / 60, 1)
    print(f"[OK] Timeline: {plan['total_segments']} segments, {dur_min} min estimated")
    print(f"[OK] Audio ready: {plan['audio_ready']}")
    print(f"[OK] Video ready: {plan['video_ready']}")
    print(f"[DONE] Timeline plan → {plan_path}")

    if plan["render_ready"]:
        flag_path.write_text("ready", encoding="utf-8")
        print(f"[FLAG] render_ready.flag created → {flag_path}")
        print("[NEXT] Run pipeline_step_5_render_upload.py")
    else:
        blockers = []
        if not plan["audio_ready"]:
            blockers.append("Audio: generate voice files with ElevenLabs")
        if not plan["video_ready"]:
            blockers.append("Video: generate images with Dzine")
        print("[BLOCKED] Cannot render yet:")
        for b in blockers:
            print(f"  - {b}")

    # Try DaVinci API assembly if Resolve is running
    try:
        from resolve_bridge import get_resolve
        resolve = get_resolve()
        if resolve:
            print("[DAVINCI] Resolve detected — automated timeline assembly available")
            print("[DAVINCI] Run with --assemble flag to build timeline in Resolve")
    except (ImportError, Exception):
        pass


if __name__ == "__main__":
    main()
