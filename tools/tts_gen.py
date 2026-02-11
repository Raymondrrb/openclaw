#!/usr/bin/env python3
"""CLI for ElevenLabs voiceover generation — credit-efficient chunked TTS.

Usage:
    # Generate full voiceover from script
    python3 tools/tts_gen.py --video-id my-video --script script.txt

    # Regenerate chunk 03 only
    python3 tools/tts_gen.py --video-id my-video --script script.txt --patch 3

    # Generate a micro patch (10-40s replacement)
    python3 tools/tts_gen.py --video-id my-video --micro "This product lasts eight hours on a single charge."

    # Dry run: preprocess + chunk without calling API
    python3 tools/tts_gen.py --video-id my-video --script script.txt --dry-run
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
from tools.lib.tts_preprocess import preprocess
from tools.lib.tts_generate import (
    VIDEOS_BASE,
    chunk_script,
    generate_full,
    generate_micro,
    generate_patch,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ElevenLabs TTS generation for Amazon product ranking videos"
    )
    parser.add_argument("--video-id", required=True, help="Video project identifier")
    parser.add_argument("--script", default=None, help="Path to script file")
    parser.add_argument("--patch", type=int, nargs="+", default=None, help="Chunk index(es) to regenerate")
    parser.add_argument("--micro", default=None, help="Text for micro patch generation")
    parser.add_argument("--micro-label", default="fix", help="Label for micro patch file (default: fix)")
    parser.add_argument("--voice-id", default="", help="Override voice_id (default: from env)")
    parser.add_argument("--dry-run", action="store_true", help="Preprocess + chunk, show plan without calling API")
    args = parser.parse_args()

    # Load env
    load_env_file(project_root() / ".env")

    # --- Micro mode ---
    if args.micro:
        if args.dry_run:
            processed = preprocess(args.micro)
            print(f"Preprocessed text:\n{processed}")
            print(f"\nWords: {len(processed.split())}")
            print(f"Estimated: {len(processed.split()) / 155 * 60:.0f}s")
            return 0

        result = generate_micro(
            args.video_id,
            args.micro,
            label=args.micro_label,
            voice_id=args.voice_id,
        )
        if result.status == "success":
            print(f"\nGenerated: {result.file_path}")
            print(f"Duration:  {result.actual_duration_s:.0f}s")
            print(f"Chars:     {result.char_count}")
            return 0
        else:
            print(f"\nFailed: {result.error}", file=sys.stderr)
            return 1

    # --- Full / Patch mode: need script ---
    if not args.script:
        print("--script is required for full/patch mode", file=sys.stderr)
        return 2

    script_path = Path(args.script)
    video_dir = VIDEOS_BASE / args.video_id

    if not script_path.is_absolute():
        if (video_dir / script_path).is_file():
            script_path = video_dir / script_path
        elif not script_path.is_file():
            print(f"Script not found: {args.script}", file=sys.stderr)
            return 2

    script_text = script_path.read_text(encoding="utf-8")
    if not script_text.strip():
        print("Script file is empty", file=sys.stderr)
        return 2

    # --- Dry run ---
    if args.dry_run:
        processed = preprocess(script_text)
        chunks = chunk_script(processed)

        print(f"Video:  {args.video_id}")
        print(f"Chunks: {len(chunks)}")
        print(f"Total words: {sum(len(c.split()) for c in chunks)}")
        print(f"Total chars: {sum(len(c) for c in chunks)}")
        print()

        for i, chunk in enumerate(chunks):
            words = len(chunk.split())
            chars = len(chunk)
            est_s = words / 155 * 60
            print(f"  Chunk {i:02d}: {words} words, {chars} chars, ~{est_s:.0f}s")
            # Show first 80 chars
            preview = chunk[:80].replace("\n", " ")
            print(f"           \"{preview}...\"")
            print()

        est_total = sum(len(c.split()) for c in chunks) / 155 * 60
        print(f"Estimated total duration: {est_total:.0f}s ({est_total/60:.1f} min)")
        print(f"Estimated credits: ~{sum(len(c) for c in chunks)} characters")
        return 0

    # --- Patch mode ---
    if args.patch is not None:
        results = generate_patch(
            args.video_id,
            args.patch,
            script_text,
            voice_id=args.voice_id,
        )
        failed = [m for m in results if m.status == "failed"]
        if failed:
            return 1
        return 0

    # --- Full mode ---
    results = generate_full(
        args.video_id,
        script_text,
        voice_id=args.voice_id,
    )

    failed = [m for m in results if m.status == "failed"]
    if failed:
        print(f"\n{len(failed)} chunk(s) failed. Retry with:", file=sys.stderr)
        indices = " ".join(str(m.index) for m in failed)
        print(f"  python3 tools/tts_gen.py --video-id {args.video_id} --script {args.script} --patch {indices}",
              file=sys.stderr)
        return 1

    # Print final file list
    print(f"\nAll chunks saved to: {VIDEOS_BASE / args.video_id / 'audio' / 'chunks'}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
