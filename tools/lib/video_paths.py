"""Canonical per-video file paths for the pipeline.

Single source of truth — eliminates hardcoded path logic scattered across tools.
Every tool should reference VideoPaths instead of constructing paths manually.

Stdlib only — no external deps.
"""

from __future__ import annotations

from pathlib import Path

from tools.lib.common import project_root

VIDEOS_BASE = project_root() / "artifacts" / "videos"


class VideoPaths:
    """All file paths for a single video project."""

    def __init__(self, video_id: str):
        self.video_id = video_id
        self.root = VIDEOS_BASE / video_id

        # inputs/
        self.products_json = self.root / "inputs" / "products.json"
        self.niche_txt = self.root / "inputs" / "niche.txt"

        # inputs/
        self.seo_json = self.root / "inputs" / "seo.json"

        # script/
        self.script_txt = self.root / "script" / "script.txt"
        self.script_raw = self.root / "script" / "script_raw.txt"
        self.script_final = self.root / "script" / "script_final.txt"
        self.manual_brief = self.root / "script" / "manual_brief.txt"
        self.script_review_notes = self.root / "script" / "script_review_notes.md"
        self.script_meta = self.root / "script" / "script_meta.json"
        self.prompts_dir = self.root / "script" / "prompts"

        # assets/
        self.assets_dzine = self.root / "assets" / "dzine"
        self.assets_amazon = self.root / "assets" / "amazon"

        # audio/
        self.audio_chunks = self.root / "audio" / "voice" / "chunks"
        self.tts_meta = self.root / "audio" / "voice" / "tts_meta.json"
        self.audio_music = self.root / "audio" / "music"
        self.audio_sfx = self.root / "audio" / "sfx"

        # resolve/
        self.resolve_dir = self.root / "resolve"

        # export/
        self.export_dir = self.root / "export"

        # status
        self.status_json = self.root / "status.json"

    def thumbnail_path(self) -> Path:
        """Dzine-generated thumbnail."""
        return self.assets_dzine / "thumbnail.png"

    def product_image_path(self, rank: int) -> Path:
        """Dzine-generated product image: assets/dzine/products/05.png"""
        return self.assets_dzine / "products" / f"{rank:02d}.png"

    def chunk_path(self, index: int) -> Path:
        """TTS audio chunk: audio/voice/chunks/01.mp3"""
        return self.audio_chunks / f"{index:02d}.mp3"

    def ensure_dirs(self) -> None:
        """Create all subdirectories (mkdir -p)."""
        dirs = [
            self.root / "inputs",
            self.prompts_dir,
            self.assets_dzine / "products",
            self.assets_amazon,
            self.audio_chunks,
            self.audio_music,
            self.audio_sfx,
            self.resolve_dir,
            self.export_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
