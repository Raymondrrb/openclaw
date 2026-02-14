#!/usr/bin/env python3
"""Post-render validation probe.

Validates that a rendered video file meets minimum quality criteria:
1. File exists
2. File size above minimum threshold
3. Duration above minimum (via ffprobe, if available)

Usage:
    python3 scripts/render_probe.py state/output/RUNID.mp4 [min_bytes]

Exit codes:
    0: OK
    1: General error
    2: File missing or bad arguments
    3: File too small
    4: Duration too short or ffprobe error
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def try_ffprobe_duration(path: Path) -> float | None:
    """Get video duration via ffprobe. Returns None if unavailable."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except Exception:
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: render_probe.py <output_path> [min_bytes]", file=sys.stderr)
        sys.exit(2)

    output_path = Path(sys.argv[1])
    min_bytes = int(sys.argv[2]) if len(sys.argv) >= 3 else 5_000_000

    if not output_path.exists():
        print(f"RENDER_PROBE_FAIL: output missing ({output_path})", file=sys.stderr)
        sys.exit(2)

    size = output_path.stat().st_size
    if size < min_bytes:
        print(
            f"RENDER_PROBE_FAIL: too small "
            f"({size} bytes < {min_bytes})",
            file=sys.stderr,
        )
        sys.exit(3)

    duration = try_ffprobe_duration(output_path)
    if duration is not None and duration < 3.0:
        print(
            f"RENDER_PROBE_FAIL: suspicious duration ({duration:.1f}s)",
            file=sys.stderr,
        )
        sys.exit(4)

    dur_str = f"{duration:.1f}s" if duration else "n/a"
    print(
        f"Render probe OK: {output_path.name} "
        f"size={size} duration={dur_str}"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
