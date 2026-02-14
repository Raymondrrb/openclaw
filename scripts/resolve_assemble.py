#!/usr/bin/env python3
"""DaVinci Resolve timeline assembly from media manifest.

Reads a media manifest JSON and assembles a timeline in DaVinci Resolve:
1. Creates/loads project
2. Imports video + audio media
3. Creates timeline and appends clips in segment order

Requirements:
  - DaVinci Resolve open with scripting enabled
  - DaVinciResolveScript module in PYTHONPATH
    (typically at /Library/Application Support/Blackmagic Design/
     DaVinci Resolve/Developer/Scripting/Modules)

Usage:
    python3 scripts/resolve_assemble.py state/jobs/media_manifest_RUNID.json

Exit codes:
    0: Success
    1: Runtime error
    2: Missing arguments or files
    3: Resolve project error
    4: Timeline creation error
    5: Missing media files
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def get_resolve():
    try:
        import DaVinciResolveScript as dvr
        resolve = dvr.scriptapp("Resolve")
        if not resolve:
            raise RuntimeError("Resolve returned None — is it running?")
        return resolve
    except ImportError as e:
        raise RuntimeError(
            "DaVinciResolveScript not found. "
            "Add Resolve's Scripting/Modules dir to PYTHONPATH."
        ) from e


def ensure_project(resolve, name: str):
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    if proj and proj.GetName() == name:
        return proj

    # Try loading existing project
    try:
        pm.LoadProject(name)
        proj = pm.GetCurrentProject()
        if proj:
            return proj
    except Exception:
        pass

    # Create new
    proj = pm.CreateProject(name)
    if not proj:
        raise RuntimeError(f"Failed to create project: {name}")
    return proj


def _build_clip_index(media_pool) -> dict:
    """Build name→MediaPoolItem map by recursively scanning all folders.

    Resolve's GetClipList() only returns clips in the current folder.
    After ImportMedia, clips may land in the root or a sub-bin.
    This helper walks the entire folder tree to find every clip.
    """
    index = {}

    def _scan_folder(folder):
        if not folder:
            return
        clips = folder.GetClipList() or []
        for clip in clips:
            name = clip.GetName()
            if name and name not in index:
                index[name] = clip
        # Recurse into sub-folders
        subs = folder.GetSubFolderList() or []
        for sub in subs:
            _scan_folder(sub)

    root = media_pool.GetRootFolder()
    _scan_folder(root)
    return index


def main():
    if len(sys.argv) < 2:
        print("Usage: resolve_assemble.py <manifest_path>", file=sys.stderr)
        sys.exit(2)

    manifest_path = Path(sys.argv[1])
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        sys.exit(2)

    m = load_manifest(manifest_path)
    run_id = m.get("run_id", "unknown")
    segments = m.get("segments", [])

    if not segments:
        print("No segments in manifest", file=sys.stderr)
        sys.exit(2)

    # Validate media files exist before touching Resolve
    video_paths = [s["video_path"] for s in segments if s.get("video_path")]
    audio_paths = [s["audio_path"] for s in segments if s.get("audio_path")]

    missing = []
    for p in video_paths + audio_paths:
        if p and not Path(p).exists():
            missing.append(p)
    if missing:
        for p in missing:
            print(f"Missing: {p}", file=sys.stderr)
        sys.exit(5)

    # Connect to Resolve
    try:
        resolve = get_resolve()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(3)

    proj_name = f"RayVault_{run_id}"
    try:
        proj = ensure_project(resolve, proj_name)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(3)

    mp = proj.GetMediaPool()
    if not mp:
        print("Failed to get MediaPool", file=sys.stderr)
        sys.exit(3)

    # Set timeline frame rate
    fps = m.get("fps", 30)
    proj.SetSetting("timelineFrameRate", str(fps))

    # Create timeline
    timeline_name = f"Timeline_{run_id}"
    timeline = mp.CreateEmptyTimeline(timeline_name)
    if not timeline:
        print(f"Failed to create timeline: {timeline_name}", file=sys.stderr)
        sys.exit(4)

    # Import all media
    all_paths = [str(Path(p).resolve()) for p in video_paths + audio_paths if p]
    imported = mp.ImportMedia(all_paths) or []

    # Build name→item map (recursive scan of all folders)
    by_name = _build_clip_index(mp)

    # Append segments in order (video on V1, audio on A1)
    for seg in segments:
        vp = seg.get("video_path")
        ap = seg.get("audio_path")

        if vp:
            v_name = Path(vp).name
            v_item = by_name.get(v_name)
            if v_item:
                mp.AppendToTimeline([v_item])
            else:
                print(f"Warning: clip not found in pool: {v_name}", file=sys.stderr)

        if ap:
            a_name = Path(ap).name
            a_item = by_name.get(a_name)
            if a_item:
                mp.AppendToTimeline([a_item])
            else:
                print(f"Warning: clip not found in pool: {a_name}", file=sys.stderr)

    proj.SetCurrentTimeline(timeline)
    proj.Save()

    print(f"Timeline assembled: {proj_name}/{timeline_name} ({len(segments)} segments)")
    sys.exit(0)


if __name__ == "__main__":
    main()
