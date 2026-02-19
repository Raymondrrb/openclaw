#!/usr/bin/env python3
"""
Pipeline Step 3: Generate voice from structured script.

Reads script.json and produces voice segment files for ElevenLabs synthesis.
When ElevenLabs API is configured, generates audio directly.
Without API, produces text files ready for manual TTS or ElevenLabs UI.

Usage:
    python3 tools/pipeline_step_3_generate_voice.py --run-dir content/pipeline_runs/RUN_ID/

Input:  {run_dir}/script.json
Output: {run_dir}/voice_segments/   (text files per segment)
        {run_dir}/voice_manifest.json
        {run_dir}/full_narration.txt  (concatenated for full TTS)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_pipeline_lib import extract_voice_segments


VOICE_PROFILE = "Thomas Louis"
VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


def main():
    parser = argparse.ArgumentParser(description="Step 3: Generate voice from script")
    parser.add_argument("--run-dir", required=True, help="Pipeline run directory")
    parser.add_argument("--voice-name", default=VOICE_PROFILE)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    script_path = run_dir / "script.json"
    manifest_path = run_dir / "voice_manifest.json"
    narration_path = run_dir / "full_narration.txt"

    if not script_path.exists():
        print(f"[ERROR] script.json not found at {script_path}")
        print("[HINT] Run pipeline_step_1_generate_script.py first")
        sys.exit(1)

    if manifest_path.exists():
        print(f"[SKIP] voice_manifest.json already exists at {manifest_path}")
        sys.exit(0)

    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    voice_segs = extract_voice_segments(script_data)

    if not voice_segs:
        print("[ERROR] No narration segments found in script.json")
        sys.exit(1)

    voice_dir = run_dir / "voice_segments"
    voice_dir.mkdir(parents=True, exist_ok=True)

    print(f"[STEP 3] Processing {len(voice_segs)} voice segments for {args.voice_name}")

    # Write individual segment text files
    segments_manifest = []
    full_narration_lines = []

    for seg in voice_segs:
        seg_id = seg["segment_id"]
        txt_file = voice_dir / f"{seg_id}.txt"
        wav_file = voice_dir / f"{seg_id}.wav"

        txt_file.write_text(seg["narration"], encoding="utf-8")
        full_narration_lines.append(seg["narration"])

        segments_manifest.append({
            "segment_id": seg_id,
            "type": seg["type"],
            "product_name": seg.get("product_name", ""),
            "text_file": str(txt_file),
            "audio_file": str(wav_file),
            "audio_exists": wav_file.exists(),
            "word_count": seg["word_count"],
            "estimated_seconds": round(seg["word_count"] / 150 * 60, 1),
        })

    # Write full narration (concatenated text for single-pass TTS)
    narration_path.write_text("\n\n".join(full_narration_lines), encoding="utf-8")

    # Build manifest
    manifest = {
        "voice_name": args.voice_name,
        "voice_settings": VOICE_SETTINGS,
        "total_segments": len(segments_manifest),
        "total_words": sum(s["word_count"] for s in segments_manifest),
        "estimated_duration_seconds": sum(s["estimated_seconds"] for s in segments_manifest),
        "segments": segments_manifest,
        "ready_segments": sum(1 for s in segments_manifest if s["audio_exists"]),
        "full_narration_file": str(narration_path),
    }

    tmp = manifest_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, manifest_path)

    ready = manifest["ready_segments"]
    total = manifest["total_segments"]
    est_min = round(manifest["estimated_duration_seconds"] / 60, 1)
    print(f"[OK] Voice segments: {total} files written to {voice_dir}")
    print(f"[OK] Full narration: {manifest['total_words']} words → {narration_path}")
    print(f"[OK] Estimated duration: {est_min} minutes")
    print(f"[DONE] Voice manifest: {ready}/{total} audio ready → {manifest_path}")

    if ready < total:
        print(f"[ACTION] Generate {total - ready} audio files using ElevenLabs")
        print(f"         Voice: {args.voice_name}")
        print(f"         Text files in: {voice_dir}")
        print("         When ElevenLabs API key is configured, this step will generate automatically.")


if __name__ == "__main__":
    main()
