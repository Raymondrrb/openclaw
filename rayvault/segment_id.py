"""RayVault Segment ID — canonical, immutable segment identifiers.

Segment IDs are SHA1 hashes of the segment's *content-defining* fields.
start_sec/end_sec are EXCLUDED so that time-shifting doesn't break IDs.

Usage:
    from rayvault.segment_id import compute_segment_id, validate_segment_ids

    seg_id = compute_segment_id(segment_dict)
    errors = validate_segment_ids(segments_list)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def canonical_segment_dict(segment: Dict[str, Any]) -> Dict[str, Any]:
    """Extract content-defining fields from a segment for ID computation.

    Included (defines content): type, role, asin, product_rank, visual mode,
    visual source, motion preset/params, overlay_refs.

    Excluded (positional only): start_sec/end_sec/t0/t1, frames, id, segment_id.
    """
    canon = {}

    # Core identity
    for key in ("type", "role", "asin", "rank"):
        if key in segment:
            canon[key] = segment[key]

    # Visual mode (defines what we see)
    visual = segment.get("visual", {})
    if visual:
        canon["visual_mode"] = visual.get("mode", "")
        canon["visual_source"] = visual.get("source", "")

    # Motion params (defines movement)
    motion = segment.get("motion", {})
    if motion:
        canon["motion_preset"] = motion.get("preset", "")
        canon["motion_start_scale"] = motion.get("start_scale", 1.0)
        canon["motion_end_scale"] = motion.get("end_scale", 1.0)

    # Overlay refs (defines what overlays appear)
    overlay_refs = segment.get("overlay_refs", [])
    if overlay_refs:
        # Normalize: sort by overlay_id for determinism
        refs = sorted(
            [{"kind": r.get("kind", ""), "overlay_id": r.get("overlay_id", "")}
             for r in overlay_refs],
            key=lambda x: x.get("overlay_id", ""),
        )
        canon["overlay_refs"] = refs

    # Title (for product segments)
    if "title" in segment:
        canon["title"] = segment["title"]

    return canon


def compute_segment_id(segment: Dict[str, Any]) -> str:
    """Compute a deterministic, immutable segment ID from content fields.

    Returns 16-character hex string (truncated SHA1).
    """
    canon = canonical_segment_dict(segment)
    blob = json.dumps(canon, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def validate_segment_ids(segments: List[Dict[str, Any]]) -> List[str]:
    """Validate existing segment_ids by recomputing and comparing.

    Returns list of error strings. Empty = all valid.
    """
    errors = []
    for i, seg in enumerate(segments):
        existing_id = seg.get("segment_id") or seg.get("id")
        if not existing_id:
            continue  # No ID to validate

        # Only validate segment_id field (not the old "id" field like "seg_000")
        if "segment_id" not in seg:
            continue

        computed = compute_segment_id(seg)
        if computed != existing_id:
            errors.append(
                f"SEGMENT_ID_MISMATCH: index={i} "
                f"existing={existing_id} computed={computed}"
            )

    return errors


def ensure_segment_ids(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Add segment_id to segments that don't have one. Returns modified list."""
    for seg in segments:
        if "segment_id" not in seg:
            seg["segment_id"] = compute_segment_id(seg)
    return segments
