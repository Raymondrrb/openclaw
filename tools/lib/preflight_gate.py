"""Preflight safety gates for expensive pipeline stages.

Check prerequisites before spending Dzine credits (assets) or
ElevenLabs credits (TTS). Pure functions, no side effects.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tools.lib.video_paths import VideoPaths

# Domains allowed in research reports (plus amazon.com for product links)
_ALLOWED_DOMAINS = {"nytimes.com", "rtings.com", "pcmag.com", "amazon.com"}

_URL_RE = re.compile(r"https?://([^/\s\"')]+)")


def _extract_domains(text: str) -> set[str]:
    """Extract unique root domains from URLs in text."""
    domains: set[str] = set()
    for match in _URL_RE.finditer(text):
        host = match.group(1).lower()
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        # Get root domain (last 2 parts)
        parts = host.split(".")
        if len(parts) >= 2:
            domains.add(".".join(parts[-2:]))
    return domains


def can_run_assets(video_id: str) -> tuple[bool, str]:
    """Check if assets stage can proceed.

    Blocks unless:
    - inputs/products.json exists with exactly 5 items, each having ASIN + affiliate_url
    - inputs/research_report.md only contains allowed domains (warn-only if missing)

    Returns (ok, reason).
    """
    paths = VideoPaths(video_id)

    # --- products.json ---
    if not paths.products_json.is_file():
        return False, f"products.json not found: {paths.products_json}"

    try:
        data = json.loads(paths.products_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"Cannot read products.json: {exc}"

    products = data.get("products", [])
    if len(products) != 5:
        return False, f"products.json has {len(products)} products (expected 5)"

    for p in products:
        rank = p.get("rank", "?")
        if not p.get("asin"):
            return False, f"Product #{rank} missing ASIN in products.json"
        if not p.get("affiliate_url"):
            return False, f"Product #{rank} missing affiliate_url in products.json"

    # --- research_report.md (warn-only) ---
    if paths.research_report.is_file():
        report = paths.research_report.read_text(encoding="utf-8")
        domains = _extract_domains(report)
        bad = domains - _ALLOWED_DOMAINS
        if bad:
            return False, (
                f"research_report.md contains disallowed domains: {', '.join(sorted(bad))}. "
                f"Only {', '.join(sorted(_ALLOWED_DOMAINS))} are permitted."
            )

    return True, ""


def can_run_tts(video_id: str) -> tuple[bool, str]:
    """Check if TTS stage can proceed.

    Blocks unless:
    - script/script_final.txt exists
    - script/script_review_notes.md exists (implies review passed)

    Returns (ok, reason).
    """
    paths = VideoPaths(video_id)

    if not paths.script_final.is_file():
        return False, (
            f"script_final.txt not found: {paths.script_final}. "
            f"Run script-review first: python3 tools/pipeline.py script-review --video-id {video_id}"
        )

    if not paths.script_review_notes.is_file():
        return False, (
            f"script_review_notes.md not found: {paths.script_review_notes}. "
            f"Run script-review first: python3 tools/pipeline.py script-review --video-id {video_id}"
        )

    return True, ""
