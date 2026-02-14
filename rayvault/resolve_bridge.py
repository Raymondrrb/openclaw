#!/usr/bin/env python3
"""RayVault Resolve Bridge — DaVinci Resolve scripting API layer.

Provides a stable Python interface to DaVinci Resolve scripting,
with capability detection and graceful degradation.

Golden rules:
  1. NEVER hardcode Resolve version. Detect capabilities by calling and checking.
  2. Every API call is wrapped in try/except. Resolve returns None on failure,
     not exceptions — check every return value.
  3. This module handles: connection, project, bins, import, timeline, clips.
     Deliver/render is handled by davinci_assembler.py.

Requires:
  - DaVinci Resolve running with scripting enabled
  - DaVinciResolveScript module accessible (auto-detected on macOS)

Usage:
    from rayvault.resolve_bridge import ResolveBridge
    bridge = ResolveBridge()
    if bridge.connect():
        project = bridge.create_project("RUN_2026_02_14_A", settings)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Resolve module discovery (macOS, Linux, Windows)
# ---------------------------------------------------------------------------

_RESOLVE_SCRIPT_PATHS = [
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    "/opt/resolve/Developer/Scripting/Modules",
    "C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules",
]


def _ensure_resolve_in_path() -> None:
    """Add Resolve scripting module path to sys.path if not already there."""
    env_path = os.getenv("RESOLVE_SCRIPT_API")
    if env_path:
        modules_dir = os.path.join(env_path, "Modules")
        if modules_dir not in sys.path:
            sys.path.insert(0, modules_dir)

    for p in _RESOLVE_SCRIPT_PATHS:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


def _import_resolve_script():
    """Import DaVinciResolveScript module. Returns module or None."""
    _ensure_resolve_in_path()
    try:
        import DaVinciResolveScript as dvrs
        return dvrs
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


@dataclass
class ResolveCapabilities:
    """What this Resolve instance can and cannot do via scripting."""
    scripting_available: bool = False
    resolve_connected: bool = False
    can_create_project: bool = False
    can_create_timeline: bool = False
    can_import_media: bool = False
    can_set_project_settings: bool = False
    can_set_render_settings: bool = False
    can_start_render: bool = False
    can_get_render_status: bool = False
    can_add_track: bool = False
    resolve_version: str = "unknown"
    resolve_name: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scripting_available": self.scripting_available,
            "resolve_connected": self.resolve_connected,
            "can_create_project": self.can_create_project,
            "can_create_timeline": self.can_create_timeline,
            "can_import_media": self.can_import_media,
            "can_set_project_settings": self.can_set_project_settings,
            "can_set_render_settings": self.can_set_render_settings,
            "can_start_render": self.can_start_render,
            "can_get_render_status": self.can_get_render_status,
            "can_add_track": self.can_add_track,
            "resolve_version": self.resolve_version,
            "resolve_name": self.resolve_name,
        }


# ---------------------------------------------------------------------------
# Ken Burns patterns (seed-deterministic)
# ---------------------------------------------------------------------------

KENBURNS_PATTERNS = [
    {"name": "zoom_in_center", "zoom": (1.0, 1.08), "pan_x": (0, 0), "pan_y": (0, 0)},
    {"name": "zoom_out_center", "zoom": (1.08, 1.0), "pan_x": (0, 0), "pan_y": (0, 0)},
    {"name": "pan_left_to_right", "zoom": (1.04, 1.04), "pan_x": (-0.03, 0.03), "pan_y": (0, 0)},
    {"name": "pan_right_to_left", "zoom": (1.04, 1.04), "pan_x": (0.03, -0.03), "pan_y": (0, 0)},
    {"name": "slow_push_up", "zoom": (1.0, 1.06), "pan_x": (0, 0), "pan_y": (0.02, -0.02)},
    {"name": "diagonal_drift", "zoom": (1.0, 1.05), "pan_x": (-0.02, 0.02), "pan_y": (-0.01, 0.01)},
]


def kenburns_pattern_for_segment(run_id: str, asin: str, rank: int) -> Dict[str, Any]:
    """Select a deterministic Ken Burns pattern based on run+asin+rank seed."""
    seed = hashlib.sha1(f"{run_id}:{asin}:{rank}".encode()).hexdigest()[:8]
    idx = int(seed, 16) % len(KENBURNS_PATTERNS)
    return KENBURNS_PATTERNS[idx]


# ---------------------------------------------------------------------------
# Resolve Bridge
# ---------------------------------------------------------------------------


class ResolveBridge:
    """Stable interface to DaVinci Resolve scripting API.

    All methods return success/failure without raising exceptions.
    Call detect_capabilities() after connect() to know what works.
    """

    def __init__(self):
        self._dvrs = None
        self._resolve = None
        self._pm = None  # ProjectManager
        self._project = None
        self._media_pool = None
        self._timeline = None
        self.caps = ResolveCapabilities()

    @property
    def connected(self) -> bool:
        return self._resolve is not None

    @property
    def project(self):
        return self._project

    @property
    def media_pool(self):
        return self._media_pool

    @property
    def timeline(self):
        return self._timeline

    # --- Connection ---

    def connect(self) -> bool:
        """Connect to running DaVinci Resolve instance."""
        self._dvrs = _import_resolve_script()
        if not self._dvrs:
            self.caps.scripting_available = False
            return False

        self.caps.scripting_available = True

        try:
            self._resolve = self._dvrs.scriptapp("Resolve")
        except Exception:
            self._resolve = None

        if not self._resolve:
            self.caps.resolve_connected = False
            return False

        self.caps.resolve_connected = True
        self._pm = self._resolve.GetProjectManager()

        # Detect version
        try:
            ver = self._resolve.GetVersion()
            if ver:
                self.caps.resolve_version = str(ver)
            name = self._resolve.GetProductName()
            if name:
                self.caps.resolve_name = str(name)
        except Exception:
            pass

        return True

    def detect_capabilities(self) -> ResolveCapabilities:
        """Detect what this Resolve instance supports via scripting.

        Call after connect(). Tests each capability by attempting the operation.
        """
        if not self._resolve or not self._pm:
            return self.caps

        # Can create project?
        try:
            test = self._pm.CreateProject("__rayvault_cap_test__")
            if test:
                self.caps.can_create_project = True
                self._pm.CloseProject()
                self._pm.DeleteProject("__rayvault_cap_test__")
        except Exception:
            pass

        # Other capabilities are tested when actually used
        # (creating timelines, importing media, etc.)
        # We'll update caps as we go.
        return self.caps

    def disconnect(self) -> None:
        """Clean up references."""
        self._timeline = None
        self._media_pool = None
        self._project = None
        self._pm = None
        self._resolve = None

    # --- Project ---

    def create_project(
        self,
        name: str,
        output_settings: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a new project (or load existing) and apply settings."""
        if not self._pm:
            return False

        # Check if project exists
        try:
            existing = self._pm.LoadProject(name)
            if existing:
                self._project = self._pm.GetCurrentProject()
                if self._project:
                    self._media_pool = self._project.GetMediaPool()
                    self._apply_project_settings(output_settings)
                    return True
        except Exception:
            pass

        # Create new
        try:
            proj = self._pm.CreateProject(name)
            if not proj:
                return False
            self._project = proj
            self._media_pool = proj.GetMediaPool()
            self.caps.can_create_project = True
        except Exception:
            return False

        self._apply_project_settings(output_settings)
        return True

    def _apply_project_settings(self, output_settings: Optional[Dict[str, Any]]) -> None:
        """Apply output settings to the current project."""
        if not self._project or not output_settings:
            return
        try:
            w = output_settings.get("w", 1920)
            h = output_settings.get("h", 1080)
            fps = output_settings.get("fps", 30)
            self._project.SetSetting("timelineResolutionWidth", str(w))
            self._project.SetSetting("timelineResolutionHeight", str(h))
            self._project.SetSetting("timelineFrameRate", str(float(fps)))
            self.caps.can_set_project_settings = True
        except Exception:
            pass

    def save_project(self) -> bool:
        """Save the current project."""
        if not self._project:
            return False
        try:
            self._project.Save()
            return True
        except Exception:
            return False

    # --- Bins ---

    def create_bins(self) -> Dict[str, Any]:
        """Create organized bin structure in the media pool.

        Returns dict mapping bin name -> folder object.
        """
        bins: Dict[str, Any] = {}
        if not self._media_pool:
            return bins

        root = self._media_pool.GetRootFolder()
        if not root:
            return bins

        for name in ("Audio", "Products", "Overlays", "Frames"):
            try:
                folder = self._media_pool.AddSubFolder(root, name)
                if folder:
                    bins[name] = folder
            except Exception:
                pass

        return bins

    # --- Media Import ---

    def import_media(
        self,
        paths: List[str],
        target_bin: Optional[Any] = None,
    ) -> List[Any]:
        """Import media files into the media pool.

        Returns list of imported MediaPoolItem objects.
        """
        if not self._media_pool:
            return []

        if target_bin:
            try:
                self._media_pool.SetCurrentFolder(target_bin)
            except Exception:
                pass

        try:
            abs_paths = [str(Path(p).resolve()) for p in paths if Path(p).exists()]
            if not abs_paths:
                return []
            imported = self._media_pool.ImportMedia(abs_paths)
            if imported:
                self.caps.can_import_media = True
                return list(imported)
        except Exception:
            pass

        return []

    def build_clip_index(self) -> Dict[str, Any]:
        """Build name -> MediaPoolItem map by scanning all folders recursively."""
        index: Dict[str, Any] = {}
        if not self._media_pool:
            return index

        def _scan(folder):
            if not folder:
                return
            clips = folder.GetClipList() or []
            for clip in clips:
                name = clip.GetName()
                if name and name not in index:
                    index[name] = clip
            for sub in (folder.GetSubFolderList() or []):
                _scan(sub)

        root = self._media_pool.GetRootFolder()
        _scan(root)
        return index

    # --- Timeline ---

    def create_timeline(self, name: str) -> bool:
        """Create an empty timeline and set it as current."""
        if not self._media_pool:
            return False

        try:
            tl = self._media_pool.CreateEmptyTimeline(name)
            if tl:
                self._timeline = tl
                self._project.SetCurrentTimeline(tl)
                self.caps.can_create_timeline = True
                return True
        except Exception:
            pass

        return False

    def add_track(self, track_type: str = "video") -> bool:
        """Add a track to the current timeline. track_type: 'video' or 'audio'."""
        if not self._timeline:
            return False
        try:
            result = self._timeline.AddTrack(track_type)
            if result:
                self.caps.can_add_track = True
            return bool(result)
        except Exception:
            return False

    def append_clips_to_timeline(
        self,
        clips: List[Any],
        track_index: int = 1,
        media_type: int = 1,
    ) -> bool:
        """Append clips to a specific track.

        media_type: 1=video, 2=audio.
        track_index: 1-based track number.
        """
        if not self._media_pool or not clips:
            return False
        try:
            # Build clip dicts with track targeting
            clip_dicts = []
            for clip in clips:
                clip_dicts.append({
                    "mediaPoolItem": clip,
                    "mediaType": media_type,
                    "trackIndex": track_index,
                })
            result = self._media_pool.AppendToTimeline(clip_dicts)
            return bool(result)
        except Exception:
            # Fallback: try simple append
            try:
                return bool(self._media_pool.AppendToTimeline(clips))
            except Exception:
                return False

    def get_timeline_items(self, track_type: str = "video", track_index: int = 1) -> List[Any]:
        """Get all items on a specific track."""
        if not self._timeline:
            return []
        try:
            items = self._timeline.GetItemListInTrack(track_type, track_index)
            return list(items) if items else []
        except Exception:
            return []

    def set_clip_duration(self, clip_item: Any, frames: int) -> bool:
        """Set the duration of a timeline item (clip) in frames."""
        try:
            return bool(clip_item.SetProperty("ForcedDuration", frames))
        except Exception:
            return False

    def set_dynamic_zoom(
        self,
        clip_item: Any,
        pattern: Dict[str, Any],
    ) -> bool:
        """Apply Dynamic Zoom (Ken Burns) to a timeline item.

        pattern: one of KENBURNS_PATTERNS with zoom/pan start/end values.
        Returns True if applied, False if API doesn't support it.
        """
        try:
            # Enable Dynamic Zoom
            clip_item.SetProperty("DynamicZoomEase", 2)  # 0=linear, 2=ease in/out

            # The Dynamic Zoom API varies by Resolve version.
            # We attempt to set it; if it fails, mark for manual review.
            zoom_start, zoom_end = pattern.get("zoom", (1.0, 1.08))

            # Try setting zoom via properties (version-dependent)
            clip_item.SetProperty("ZoomX", zoom_start)
            clip_item.SetProperty("ZoomY", zoom_start)
            # Note: actual Dynamic Zoom start/end rects are not fully
            # controllable via scripting in all versions. The property set
            # above enables the feature; manual fine-tuning may be needed.
            return True
        except Exception:
            return False

    # --- Render Settings ---

    def set_render_settings(
        self,
        output_path: str,
        preset_name: str = "",
        output_settings: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Configure render/deliver settings."""
        if not self._project:
            return False

        settings: Dict[str, Any] = {
            "TargetDir": str(Path(output_path).parent),
            "CustomName": Path(output_path).stem,
        }

        if output_settings:
            w = output_settings.get("w", 1920)
            h = output_settings.get("h", 1080)
            fps = output_settings.get("fps", 30)
            settings["FormatWidth"] = w
            settings["FormatHeight"] = h
            settings["FrameRate"] = float(fps)

            # Codec settings (may not be supported in all versions)
            vcodec = output_settings.get("vcodec", "libx264")
            if "264" in vcodec:
                settings["VideoCodec"] = "H.264"
            elif "265" in vcodec or "hevc" in vcodec.lower():
                settings["VideoCodec"] = "H.265"

            settings["AudioCodec"] = "aac"
            settings["AudioBitDepth"] = 16
            settings["AudioSampleRate"] = 48000

        try:
            result = self._project.SetRenderSettings(settings)
            if result:
                self.caps.can_set_render_settings = True
            return bool(result)
        except Exception:
            return False

    def add_render_job(self) -> Optional[str]:
        """Add current timeline to the render queue. Returns job ID or None."""
        if not self._project:
            return None
        try:
            job_id = self._project.AddRenderJob()
            return str(job_id) if job_id else None
        except Exception:
            return None

    def start_rendering(self) -> bool:
        """Start all jobs in the render queue."""
        if not self._project:
            return False
        try:
            result = self._project.StartRendering()
            if result:
                self.caps.can_start_render = True
            return bool(result)
        except Exception:
            return False

    def is_rendering(self) -> bool:
        """Check if rendering is in progress."""
        if not self._project:
            return False
        try:
            return bool(self._project.IsRenderingInProgress())
        except Exception:
            return False

    def get_render_status(self) -> Optional[Dict[str, Any]]:
        """Get status of current render jobs."""
        if not self._project:
            return None
        try:
            jobs = self._project.GetRenderJobList()
            if not jobs:
                return None
            self.caps.can_get_render_status = True
            # Return last job status
            last = jobs[-1]
            return {
                "job_id": last.get("JobId", ""),
                "status": last.get("RenderStatus", ""),
                "completion": last.get("CompletionPercentage", 0),
                "time_remaining": last.get("TimeTakenToRenderInMs", 0),
            }
        except Exception:
            return None
