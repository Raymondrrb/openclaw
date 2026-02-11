"""DaVinci Resolve edit manifest schema and generation logic.

Defines the JSON structure for automated/semi-automated video editing
of Amazon Associates Top 5 product ranking videos.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPEAKING_WPM = 155
FPS_DEFAULT = 30
RESOLUTION_DEFAULT = (1920, 1080)

# Visual change pacing: every 3-6 seconds
VISUAL_CHANGE_MIN_S = 3.0
VISUAL_CHANGE_MAX_S = 6.0

# Zoom range for static images (percent)
ZOOM_PERCENT_MIN = 3
ZOOM_PERCENT_MAX = 7

# Audio loudness targets
VOICEOVER_LUFS = -16
VOICEOVER_PEAK_DB = -1
MUSIC_BED_LUFS = -26
SFX_LUFS = -18

# Export
EXPORT_BITRATE_MBPS_MIN = 20
EXPORT_BITRATE_MBPS_MAX = 40

# Segment durations (estimated)
AVATAR_INTRO_DURATION_S = 4.0  # 3-5s max, then disappear
TRANSITION_DURATION_S = 0.5

# Overlay timing
OVERLAY_DURATION_S = 3.0
OVERLAY_MAX_WORDS = 6
RANK_BADGE_DURATION_S = 3.0
LOWER_THIRD_DURATION_S = 3.0

# Max benefits shown per segment (2 strong benefits per product)
MAX_BENEFITS_PER_SEGMENT = 2

# Affiliate disclosure (exact text)
DISCLOSURE_TEXT = "As an Amazon Associate I earn from qualifying purchases."


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Overlay:
    time_s: float
    duration_s: float
    text: str
    type: str  # "rank_badge", "benefit", "lower_third", "cta", "disclosure", "signature"
    position: str = "center"  # "center", "lower_left", "lower_right", "top_left"
    style: str = "default"


@dataclass
class SfxCue:
    time_s: float
    file: str  # relative path within video folder
    label: str = ""


@dataclass
class Visual:
    start_s: float
    duration_s: float
    file: str  # relative path within video folder
    type: str  # "image", "clip", "background"
    motion: str = "ken_burns"  # "ken_burns", "static", "zoom_in", "zoom_out", "pan_left"


@dataclass
class ProductSegment:
    rank: int  # 5 down to 1
    product_name: str
    start_s: float = 0.0
    end_s: float = 0.0
    word_count: int = 0
    duration_s: float = 0.0
    script_text: str = ""
    visuals: list[Visual] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    sfx: list[SfxCue] = field(default_factory=list)


@dataclass
class MusicBed:
    file: str
    start_s: float = 0.0
    end_s: float = 0.0
    volume_lufs: int = MUSIC_BED_LUFS
    duck_under_voice: bool = True  # duck music when voiceover plays


@dataclass
class EditManifest:
    video_id: str
    fps: int = FPS_DEFAULT
    resolution: tuple[int, int] = RESOLUTION_DEFAULT
    total_duration_s: float = 0.0

    # Sections
    hook_start_s: float = 0.0
    hook_end_s: float = 0.0
    hook_text: str = ""

    avatar_intro_file: str = ""
    avatar_intro_start_s: float = 0.0
    avatar_intro_end_s: float = 0.0
    avatar_intro_text: str = ""

    segments: list[ProductSegment] = field(default_factory=list)

    retention_reset_start_s: float = 0.0
    retention_reset_end_s: float = 0.0
    retention_reset_text: str = ""

    outro_start_s: float = 0.0
    outro_end_s: float = 0.0
    outro_text: str = ""

    # Audio
    voiceover_file: str = ""
    music: MusicBed = field(default_factory=lambda: MusicBed(file=""))
    global_sfx: list[SfxCue] = field(default_factory=list)

    # Overlays
    global_overlays: list[Overlay] = field(default_factory=list)

    # Metadata
    signature_line: str = ""
    signature_type: str = ""


# ---------------------------------------------------------------------------
# Time estimation
# ---------------------------------------------------------------------------


def words_to_seconds(word_count: int) -> float:
    """Convert word count to estimated speaking duration."""
    return round(word_count / SPEAKING_WPM * 60, 1)


def count_words(text: str) -> int:
    """Count words, ignoring stage directions."""
    cleaned = re.sub(r"\[.*?\]", "", text)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    return len(cleaned.split())


# ---------------------------------------------------------------------------
# Script parsing
# ---------------------------------------------------------------------------


def parse_script_sections(script_text: str) -> dict[str, str]:
    """Parse a script with [SECTION] markers into a dict.

    Returns dict with keys: hook, avatar_intro, product_5..product_1,
    retention_reset, conclusion.
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    marker_map = {
        "[HOOK]": "hook",
        "[AVATAR_INTRO]": "avatar_intro",
        "[PRODUCT_5]": "product_5",
        "[PRODUCT_4]": "product_4",
        "[PRODUCT_3]": "product_3",
        "[RETENTION_RESET]": "retention_reset",
        "[PRODUCT_2]": "product_2",
        "[PRODUCT_1]": "product_1",
        "[CONCLUSION]": "conclusion",
    }

    for line in script_text.splitlines():
        stripped = line.strip().upper()
        if stripped in marker_map:
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = marker_map[stripped]
            current_lines = []
        elif current_key:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


# ---------------------------------------------------------------------------
# Asset discovery
# ---------------------------------------------------------------------------


def discover_assets(video_dir: Path) -> dict:
    """Scan a video project folder and return discovered asset paths."""
    assets: dict = {
        "voiceover": "",
        "avatar_intro_audio": "",
        "avatar_intro_video": "",
        "music_bed": "",
        "thumbnail": "",
        "backgrounds": [],
        "sfx": [],
        "products": {},  # rank -> {amazon: [], dzine: [], clips: []}
    }

    vd = video_dir

    # Audio (check for combined voiceover file first)
    for name in ("voiceover.wav", "voiceover.mp3", "voiceover.aac"):
        p = vd / "audio" / name
        if p.is_file():
            assets["voiceover"] = f"audio/{name}"
            break

    # Also discover voice chunks (new layout: audio/voice/chunks/, legacy: audio/chunks/)
    voice_chunks_dirs = [vd / "audio" / "voice" / "chunks", vd / "audio" / "chunks"]
    for vc_dir in voice_chunks_dirs:
        if vc_dir.is_dir():
            chunk_files = sorted(
                f for f in vc_dir.iterdir()
                if f.suffix.lower() in (".mp3", ".wav", ".aac") and not f.stem.startswith("micro_")
            )
            if chunk_files:
                rel = vc_dir.relative_to(vd)
                assets.setdefault("voice_chunks", [])
                for cf in chunk_files:
                    assets["voice_chunks"].append(f"{rel}/{cf.name}")
                break

    for name in ("avatar_intro.wav", "avatar_intro.mp3"):
        p = vd / "audio" / name
        if p.is_file():
            assets["avatar_intro_audio"] = f"audio/{name}"
            break

    for name in ("avatar_intro.mp4", "avatar_intro.mov"):
        p = vd / "visuals" / name
        if p.is_file():
            assets["avatar_intro_video"] = f"visuals/{name}"
            break

    for name in ("music_bed.wav", "music_bed.mp3", "music.wav", "music.mp3"):
        p = vd / "audio" / name
        if p.is_file():
            assets["music_bed"] = f"audio/{name}"
            break

    # Thumbnail (check new layout first, then legacy)
    for name in ("thumbnail.png", "thumbnail.jpg"):
        p = vd / "assets" / "dzine" / name
        if p.is_file():
            assets["thumbnail"] = f"assets/dzine/{name}"
            break
    if not assets["thumbnail"]:
        for name in ("thumbnail.png", "thumbnail.jpg"):
            p = vd / "visuals" / name
            if p.is_file():
                assets["thumbnail"] = f"visuals/{name}"
                break

    # Backgrounds
    bg_dir = vd / "visuals" / "backgrounds"
    if bg_dir.is_dir():
        for f in sorted(bg_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".mp4", ".mov"):
                assets["backgrounds"].append(f"visuals/backgrounds/{f.name}")

    # SFX
    sfx_dir = vd / "audio" / "sfx"
    if sfx_dir.is_dir():
        for f in sorted(sfx_dir.iterdir()):
            if f.suffix.lower() in (".wav", ".mp3", ".aac"):
                assets["sfx"].append(f"audio/sfx/{f.name}")

    # Product assets (ranks 01-05)
    for rank in range(1, 6):
        rank_str = f"{rank:02d}"
        prod = {"amazon": [], "dzine": [], "clips": []}

        # New layout: assets/dzine/products/05.png
        dzine_img = vd / "assets" / "dzine" / "products" / f"{rank_str}.png"
        if dzine_img.is_file():
            prod["dzine"].append(f"assets/dzine/products/{rank_str}.png")

        # New layout: assets/amazon/05_main.jpg (and similar)
        amazon_dir = vd / "assets" / "amazon"
        if amazon_dir.is_dir():
            for f in sorted(amazon_dir.iterdir()):
                if f.stem.startswith(rank_str) and f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    prod["amazon"].append(f"assets/amazon/{f.name}")

        # Legacy layout: visuals/products/05/
        prod_dir = vd / "visuals" / "products" / rank_str
        if prod_dir.is_dir():
            for f in sorted(prod_dir.iterdir()):
                if f.is_dir() and f.name == "clips":
                    for clip in sorted(f.iterdir()):
                        if clip.suffix.lower() in (".mp4", ".mov"):
                            prod["clips"].append(f"visuals/products/{rank_str}/clips/{clip.name}")
                elif f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    if "amazon" in f.stem.lower():
                        prod["amazon"].append(f"visuals/products/{rank_str}/{f.name}")
                    elif "dzine" in f.stem.lower():
                        prod["dzine"].append(f"visuals/products/{rank_str}/{f.name}")
                    else:
                        prod["amazon"].append(f"visuals/products/{rank_str}/{f.name}")

        assets["products"][rank] = prod

    return assets


# ---------------------------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------------------------


def _assign_visuals(
    segment: ProductSegment,
    product_assets: dict,
    backgrounds: list[str],
    start_s: float,
) -> list[Visual]:
    """Assign visuals to a product segment with 3-6s pacing."""
    visuals: list[Visual] = []
    available_duration = segment.duration_s
    current_time = start_s

    # Collect images in priority order: amazon first, then dzine, then clips
    image_sources: list[tuple[str, str]] = []
    for path in product_assets.get("amazon", []):
        image_sources.append((path, "image"))
    for path in product_assets.get("dzine", []):
        image_sources.append((path, "image"))
    for path in product_assets.get("clips", []):
        image_sources.append((path, "clip"))

    # Add a background as fallback
    if backgrounds:
        image_sources.append((backgrounds[0], "background"))

    if not image_sources:
        return visuals

    # Distribute across the segment duration with visual changes every 4s
    visual_duration = 4.0
    idx = 0
    # Light zoom only (3-7%): alternate zoom_in / zoom_out / ken_burns
    motions = ["zoom_in", "zoom_out", "ken_burns"]

    while current_time < start_s + available_duration and image_sources:
        remaining = (start_s + available_duration) - current_time
        dur = min(visual_duration, remaining)
        if dur < 1.0:
            break

        source_path, source_type = image_sources[idx % len(image_sources)]
        motion = "static" if source_type == "clip" else motions[idx % len(motions)]

        visuals.append(Visual(
            start_s=round(current_time, 1),
            duration_s=round(dur, 1),
            file=source_path,
            type=source_type,
            motion=motion,
        ))

        current_time += dur
        idx += 1

    return visuals


def _create_segment_overlays(
    segment: ProductSegment,
    benefits: list[str],
) -> tuple[list[Overlay], list[SfxCue]]:
    """Create overlays and click SFX cues for a product segment.

    Returns (overlays, click_sfx) tuple. Benefits capped at MAX_BENEFITS_PER_SEGMENT.
    Each overlay is max OVERLAY_MAX_WORDS words — truncated if longer.
    """
    overlays: list[Overlay] = []
    click_sfx: list[SfxCue] = []
    t = segment.start_s

    # Rank badge at the start
    overlays.append(Overlay(
        time_s=round(t, 1),
        duration_s=RANK_BADGE_DURATION_S,
        text=f"#{segment.rank}",
        type="rank_badge",
        position="top_left",
        style="rank",
    ))

    # Product name lower third
    overlays.append(Overlay(
        time_s=round(t + 1.0, 1),
        duration_s=LOWER_THIRD_DURATION_S,
        text=segment.product_name,
        type="lower_third",
        position="lower_left",
        style="product_name",
    ))

    # Benefit overlays (max 2), staggered, with click SFX
    benefit_start = t + 5.0
    for i, benefit in enumerate(benefits[:MAX_BENEFITS_PER_SEGMENT]):
        # Truncate to max 6 words
        words = benefit.split()
        if len(words) > OVERLAY_MAX_WORDS:
            benefit = " ".join(words[:OVERLAY_MAX_WORDS])
        benefit_time = round(benefit_start + i * OVERLAY_DURATION_S, 1)
        overlays.append(Overlay(
            time_s=benefit_time,
            duration_s=OVERLAY_DURATION_S,
            text=benefit,
            type="benefit",
            position="lower_left",
            style="benefit",
        ))
        # Click SFX when benefit appears
        click_sfx.append(SfxCue(
            time_s=benefit_time,
            file="audio/sfx/click.wav",
            label=f"click_benefit_{segment.rank}_{i+1}",
        ))

    return overlays, click_sfx


def generate_manifest(
    video_id: str,
    script_text: str,
    video_dir: Path,
    *,
    product_names: dict[int, str] | None = None,
    product_benefits: dict[int, list[str]] | None = None,
    signature_line: str = "",
    signature_type: str = "reality_check",
    fps: int = FPS_DEFAULT,
    resolution: tuple[int, int] = RESOLUTION_DEFAULT,
) -> EditManifest:
    """Generate a complete edit manifest from script + assets.

    Args:
        video_id: Unique identifier for the video
        script_text: Full script with [SECTION] markers
        video_dir: Path to the video project folder
        product_names: Optional {rank: name} override
        product_benefits: Optional {rank: [benefit1, benefit2, ...]}
        signature_line: Channel signature line for this video
        signature_type: "reality_check", "micro_humor", or "micro_comparison"
    """
    sections = parse_script_sections(script_text)
    assets = discover_assets(video_dir)

    manifest = EditManifest(
        video_id=video_id,
        fps=fps,
        resolution=resolution,
        voiceover_file=assets["voiceover"],
        signature_line=signature_line,
        signature_type=signature_type,
    )

    # Timeline cursor
    t = 0.0

    # --- Hook ---
    hook_text = sections.get("hook", "")
    hook_words = count_words(hook_text)
    hook_dur = words_to_seconds(hook_words)
    manifest.hook_start_s = t
    manifest.hook_end_s = round(t + hook_dur, 1)
    manifest.hook_text = hook_text
    t += hook_dur

    # --- Avatar intro ---
    avatar_text = sections.get("avatar_intro", "")
    manifest.avatar_intro_file = assets.get("avatar_intro_video", "")
    manifest.avatar_intro_start_s = round(t, 1)
    manifest.avatar_intro_end_s = round(t + AVATAR_INTRO_DURATION_S, 1)
    manifest.avatar_intro_text = avatar_text
    t += AVATAR_INTRO_DURATION_S

    # --- Product segments (5 → 1, with retention reset after #3) ---
    segment_order = [5, 4, 3, 2, 1]
    product_names = product_names or {}
    product_benefits = product_benefits or {}

    for rank in segment_order:
        key = f"product_{rank}"
        text = sections.get(key, "")
        words = count_words(text)
        dur = words_to_seconds(words)

        # Extract product name from first line or override
        name = product_names.get(rank, "")
        if not name and text:
            first_line = text.strip().splitlines()[0] if text.strip() else ""
            name = first_line[:60]

        seg = ProductSegment(
            rank=rank,
            product_name=name,
            start_s=round(t, 1),
            end_s=round(t + dur, 1),
            word_count=words,
            duration_s=round(dur, 1),
            script_text=text,
        )

        # Assign visuals
        prod_assets = assets.get("products", {}).get(rank, {})
        seg.visuals = _assign_visuals(seg, prod_assets, assets.get("backgrounds", []), t)

        # Assign overlays + click SFX for benefits
        benefits = product_benefits.get(rank, [])
        seg.overlays, click_cues = _create_segment_overlays(seg, benefits)
        seg.sfx.extend(click_cues)

        # Whoosh SFX on transition into segment
        sfx_files = assets.get("sfx", [])
        whoosh = [f for f in sfx_files if "whoosh" in f.lower()]
        if whoosh:
            seg.sfx.insert(0, SfxCue(
                time_s=round(t, 1),
                file=whoosh[0],
                label=f"whoosh_product_{rank}",
            ))
        elif sfx_files:
            seg.sfx.insert(0, SfxCue(
                time_s=round(t, 1),
                file=sfx_files[0],
                label=f"whoosh_product_{rank}",
            ))

        manifest.segments.append(seg)
        t += dur

        # Insert retention reset after product #3
        if rank == 3:
            reset_text = sections.get("retention_reset", "")
            reset_words = count_words(reset_text)
            reset_dur = words_to_seconds(reset_words)
            manifest.retention_reset_start_s = round(t, 1)
            manifest.retention_reset_end_s = round(t + reset_dur, 1)
            manifest.retention_reset_text = reset_text
            t += reset_dur

    # --- Outro / Conclusion ---
    outro_text = sections.get("conclusion", "")
    outro_words = count_words(outro_text)
    outro_dur = words_to_seconds(outro_words)
    manifest.outro_start_s = round(t, 1)
    manifest.outro_end_s = round(t + outro_dur, 1)
    manifest.outro_text = outro_text

    # Affiliate disclosure overlay near the end
    manifest.global_overlays.append(Overlay(
        time_s=round(t + outro_dur - 8.0, 1),
        duration_s=6.0,
        text=DISCLOSURE_TEXT,
        type="disclosure",
        position="lower_left",
        style="disclosure",
    ))

    t += outro_dur
    manifest.total_duration_s = round(t, 1)

    # --- Music bed (duck under voice for entire duration) ---
    if assets.get("music_bed"):
        manifest.music = MusicBed(
            file=assets["music_bed"],
            start_s=0.0,
            end_s=manifest.total_duration_s,
            volume_lufs=MUSIC_BED_LUFS,
            duck_under_voice=True,
        )

    # --- Signature moment ---
    if signature_line and len(manifest.segments) >= 3:
        # Place signature moment in the middle segment
        mid_seg = manifest.segments[2]  # product #3
        mid_time = mid_seg.start_s + mid_seg.duration_s * 0.6
        manifest.global_overlays.append(Overlay(
            time_s=round(mid_time, 1),
            duration_s=4.0,
            text=signature_line,
            type="signature",
            position="center",
            style="signature",
        ))

    return manifest


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def manifest_to_dict(m: EditManifest) -> dict:
    """Convert manifest to a JSON-serializable dict."""
    def _overlay(o: Overlay) -> dict:
        return {"time_s": o.time_s, "duration_s": o.duration_s, "text": o.text,
                "type": o.type, "position": o.position, "style": o.style}

    def _sfx(s: SfxCue) -> dict:
        return {"time_s": s.time_s, "file": s.file, "label": s.label}

    def _visual(v: Visual) -> dict:
        return {"start_s": v.start_s, "duration_s": v.duration_s, "file": v.file,
                "type": v.type, "motion": v.motion}

    def _segment(s: ProductSegment) -> dict:
        return {
            "rank": s.rank, "product_name": s.product_name,
            "start_s": s.start_s, "end_s": s.end_s,
            "word_count": s.word_count, "duration_s": s.duration_s,
            "visuals": [_visual(v) for v in s.visuals],
            "overlays": [_overlay(o) for o in s.overlays],
            "sfx": [_sfx(x) for x in s.sfx],
        }

    return {
        "video_id": m.video_id,
        "resolution": list(m.resolution),
        "fps": m.fps,
        "total_duration_s": m.total_duration_s,
        "estimated_duration_min": round(m.total_duration_s / 60, 1),
        "intro": {
            "hook": {
                "start_s": m.hook_start_s, "end_s": m.hook_end_s,
                "text": m.hook_text[:200] + "..." if len(m.hook_text) > 200 else m.hook_text,
            },
            "avatar": {
                "file": m.avatar_intro_file,
                "start_s": m.avatar_intro_start_s, "end_s": m.avatar_intro_end_s,
            },
        },
        "segments": [_segment(s) for s in m.segments],
        "retention_reset": {
            "start_s": m.retention_reset_start_s, "end_s": m.retention_reset_end_s,
        },
        "music": {
            "file": m.music.file,
            "start_s": m.music.start_s, "end_s": m.music.end_s,
            "volume_lufs": m.music.volume_lufs,
            "duck_under_voice": m.music.duck_under_voice,
        },
        "outro": {
            "start_s": m.outro_start_s, "end_s": m.outro_end_s,
        },
        "voiceover": {
            "file": m.voiceover_file,
            "target_lufs": VOICEOVER_LUFS,
            "peak_db": VOICEOVER_PEAK_DB,
        },
        "global_overlays": [_overlay(o) for o in m.global_overlays],
        "signature": {"line": m.signature_line, "type": m.signature_type},
    }


def manifest_to_json(m: EditManifest) -> str:
    """Serialize manifest to JSON string."""
    return json.dumps(manifest_to_dict(m), indent=2)


# ---------------------------------------------------------------------------
# Markers CSV (for Resolve import)
# ---------------------------------------------------------------------------


def manifest_to_markers_csv(m: EditManifest) -> str:
    """Generate a markers CSV for DaVinci Resolve import.

    Format: Name, Start TC, Duration, Note, Color
    Timecode at the manifest's FPS.
    """
    lines = ["Name,Start TC,Duration,Note,Color"]

    def _tc(seconds: float) -> str:
        """Convert seconds to HH:MM:SS:FF timecode."""
        h = int(seconds // 3600)
        rem = seconds % 3600
        mi = int(rem // 60)
        rem = rem % 60
        s = int(rem)
        f = int((rem - s) * m.fps)
        return f"{h:02d}:{mi:02d}:{s:02d}:{f:02d}"

    # Section markers
    lines.append(f"Hook,{_tc(m.hook_start_s)},00:00:01:00,Hook start,Blue")
    lines.append(f"Avatar Intro,{_tc(m.avatar_intro_start_s)},00:00:01:00,Avatar clip,Green")

    for seg in m.segments:
        color = "Red" if seg.rank == 1 else "Yellow"
        lines.append(
            f"Product #{seg.rank} - {seg.product_name},{_tc(seg.start_s)},00:00:01:00,"
            f"{seg.word_count} words {seg.duration_s}s,{color}"
        )

    if m.retention_reset_start_s > 0:
        lines.append(f"Retention Reset,{_tc(m.retention_reset_start_s)},00:00:01:00,Pattern interrupt,Cyan")

    lines.append(f"Outro,{_tc(m.outro_start_s)},00:00:01:00,Conclusion + CTA,Purple")

    # Overlay markers
    for ov in m.global_overlays:
        lines.append(f"{ov.type}: {ov.text[:30]},{_tc(ov.time_s)},00:00:01:00,{ov.type},Cream")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Edit notes (human-readable instructions)
# ---------------------------------------------------------------------------


def manifest_to_notes(m: EditManifest) -> str:
    """Generate human-readable editing notes for Resolve."""
    lines = [
        f"# Edit Notes — {m.video_id}",
        f"",
        f"**Duration:** {m.total_duration_s:.0f}s ({m.total_duration_s/60:.1f} min)",
        f"**Resolution:** {m.resolution[0]}x{m.resolution[1]} @ {m.fps}fps",
        f"**Voiceover:** {m.voiceover_file or 'NOT FOUND'}",
        f"**Music:** {m.music.file or 'NOT FOUND'}",
        f"",
        f"## Timeline Layout",
        f"",
        f"| Time | Section | Duration |",
        f"|------|---------|----------|",
        f"| {m.hook_start_s:.0f}s | Hook | {m.hook_end_s - m.hook_start_s:.0f}s |",
        f"| {m.avatar_intro_start_s:.0f}s | Avatar Intro | {AVATAR_INTRO_DURATION_S:.0f}s |",
    ]

    for seg in m.segments:
        lines.append(f"| {seg.start_s:.0f}s | #{seg.rank} {seg.product_name[:25]} | {seg.duration_s:.0f}s |")
        if seg.rank == 3:
            dur = m.retention_reset_end_s - m.retention_reset_start_s
            lines.append(f"| {m.retention_reset_start_s:.0f}s | Retention Reset | {dur:.0f}s |")

    lines.append(f"| {m.outro_start_s:.0f}s | Outro | {m.outro_end_s - m.outro_start_s:.0f}s |")

    lines.extend([
        f"",
        f"## Audio Mix",
        f"",
        f"- Voiceover: {VOICEOVER_LUFS} LUFS, {VOICEOVER_PEAK_DB} dB peak",
        f"- Music bed: {MUSIC_BED_LUFS} LUFS (duck under voice)",
        f"- SFX: {SFX_LUFS} LUFS",
        f"- Whoosh SFX on segment transitions, click SFX on benefit highlights",
        f"",
        f"## Per-Segment Visuals",
        f"",
    ])

    for seg in m.segments:
        lines.append(f"### #{seg.rank} — {seg.product_name}")
        if seg.visuals:
            for v in seg.visuals:
                lines.append(f"  - [{v.start_s:.1f}s–{v.start_s+v.duration_s:.1f}s] {v.file} ({v.motion})")
        else:
            lines.append(f"  - No visuals found — add images to visuals/products/{seg.rank:02d}/")
        if seg.overlays:
            for o in seg.overlays:
                lines.append(f"  - Overlay [{o.time_s:.1f}s] \"{o.text}\" ({o.type})")
        lines.append("")

    lines.extend([
        f"## Resolve Workflow",
        f"",
        f"1. Import all media from the video folder",
        f"2. Create timeline: {m.resolution[0]}x{m.resolution[1]} @ {m.fps}fps",
        f"3. Place voiceover on A1",
        f"4. Place music bed on A2, set volume to {MUSIC_BED_LUFS} LUFS (duck under voice)",
        f"5. Import markers.csv (Edit > Import > Timeline Markers)",
        f"6. Follow markers to place visuals and overlays",
        f"7. Add Fusion titles for rank badges and lower thirds",
        f"8. Apply light zoom ({ZOOM_PERCENT_MIN}-{ZOOM_PERCENT_MAX}%) to static images",
        f"9. Add transition (0.5s dissolve) between segments",
        f"10. Export: H.264, 1080p, {EXPORT_BITRATE_MBPS_MIN}-{EXPORT_BITRATE_MBPS_MAX} Mbps VBR",
    ])

    return "\n".join(lines)
