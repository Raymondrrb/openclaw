"""Video Study pipeline — multimodal analysis via Anthropic API.

Sends transcript + sampled frames to Claude for structured knowledge extraction.

Stdlib only — uses urllib.request for HTTP calls, no external deps.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from tools.lib.video_study_schema import (
    INSIGHT_CATEGORIES,
    KnowledgeOutput,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
ANTHROPIC_MAX_TOKENS = 8192
ANTHROPIC_TEMPERATURE = 0.3
API_TIMEOUT = 300  # 5 min for large multimodal requests

# Max frames to send in a single API call
MAX_API_FRAMES = 20

# Max transcript chars to include (avoid blowing token limits)
MAX_TRANSCRIPT_CHARS = 30000


# ---------------------------------------------------------------------------
# HTTP helpers (reused pattern from script_generate.py)
# ---------------------------------------------------------------------------

def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def _post_json(url: str, headers: dict, payload: dict, timeout: int = API_TIMEOUT) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error: {e.reason}") from e


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a video analysis expert for the Rayviews Lab pipeline — an automated \
Amazon Associates YouTube channel that produces Top 5 product ranking videos.

Your task: analyze the provided video content (transcript and frames) and \
extract structured knowledge relevant to the Rayviews pipeline.

The pipeline covers: niche research, product verification, script generation, \
image/video assets (Dzine AI), TTS voiceover (ElevenLabs), DaVinci Resolve \
editing, and YouTube publishing.

Target audience: 40+/50+ viewers who value trust and practical information.

You MUST respond with a single JSON object matching this exact schema:
{
  "relevance": "Why this video matters for Rayviews (1-2 sentences)",
  "summary": "3-5 sentence overview of the video content",
  "key_insights": [
    {
      "category": "<one of: editing, audio, thumbnail, scripting, growth, affiliate, dzine, workflow, tools, seo, general>",
      "insight": "Brief title of the insight",
      "details": "Detailed explanation",
      "actionable": true/false
    }
  ],
  "tools_mentioned": [
    {"name": "Tool name", "category": "Category", "url": "", "note": "Brief note"}
  ],
  "action_items": [
    {"priority": "high|medium|low", "action": "What to do", "timeline": "When"}
  ],
  "integration_plan": [
    {"phase": "Phase name", "steps": ["Step 1", "Step 2"]}
  ],
  "transcript_highlights": [
    {"timestamp": "M:SS", "text": "Quote or paraphrase", "note": "Why important"}
  ],
  "sources": [
    {"title": "Source name", "url": "URL if mentioned"}
  ]
}

Rules:
- Only include insights genuinely relevant to the Rayviews pipeline
- Prioritize actionable insights over general observations
- Use specific timestamps from the transcript when available
- Be precise about tool names, settings, and techniques
- Categories must be from the allowed list
- Respond ONLY with the JSON object, no markdown fences or explanation
"""


# ---------------------------------------------------------------------------
# Build API message content
# ---------------------------------------------------------------------------

def _encode_frame(path: Path) -> dict:
    """Encode a frame as base64 image content block for Anthropic API."""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    media_type = "image/jpeg"
    if path.suffix.lower() == ".png":
        media_type = "image/png"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64,
        },
    }


def _build_user_content(
    title: str,
    channel: str,
    description: str,
    transcript_text: str,
    frames: list[Path],
    context: str = "",
) -> list[dict]:
    """Build the user message content array with text + images."""
    parts: list[dict] = []

    # Text preamble
    text_parts = []
    text_parts.append(f"Video: {title}")
    if channel:
        text_parts.append(f"Channel: {channel}")
    if context:
        text_parts.append(f"Study context: {context}")
    if description:
        desc = description[:2000]
        text_parts.append(f"\nDescription:\n{desc}")
    if transcript_text:
        t = transcript_text[:MAX_TRANSCRIPT_CHARS]
        text_parts.append(f"\nTranscript:\n{t}")

    parts.append({"type": "text", "text": "\n".join(text_parts)})

    # Frames (up to MAX_API_FRAMES)
    for frame_path in frames[:MAX_API_FRAMES]:
        try:
            parts.append(_encode_frame(frame_path))
        except OSError:
            continue

    if frames:
        parts.append({
            "type": "text",
            "text": f"\n[{len(frames)} frames provided from the video. Analyze both the visual content and the transcript to extract knowledge.]",
        })

    return parts


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_video(
    title: str,
    channel: str,
    description: str,
    transcript_text: str,
    frames: list[Path],
    *,
    context: str = "",
    api_key: str = "",
) -> tuple[KnowledgeOutput | None, dict]:
    """Analyze video content via Anthropic multimodal API.

    Returns (KnowledgeOutput or None, analysis_meta dict).
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None, {"error": "ANTHROPIC_API_KEY not set"}

    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }

    user_content = _build_user_content(
        title, channel, description, transcript_text, frames, context
    )

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "temperature": ANTHROPIC_TEMPERATURE,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": user_content},
        ],
    }

    start = time.time()
    try:
        resp = _post_json(ANTHROPIC_API_URL, headers, payload)
    except RuntimeError as e:
        duration = time.time() - start
        return None, {"error": str(e), "duration_s": duration}

    duration = time.time() - start

    # Parse response text
    content_blocks = resp.get("content", [])
    text = ""
    for block in content_blocks:
        if block.get("type") == "text":
            text += block.get("text", "")

    if not text:
        return None, {"error": "No text in API response", "duration_s": duration}

    usage = resp.get("usage", {})
    meta = {
        "model": resp.get("model", ANTHROPIC_MODEL),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "duration_s": round(duration, 1),
        "frame_count": min(len(frames), MAX_API_FRAMES),
    }

    # Parse the JSON response
    try:
        data = _extract_json(text)
    except (json.JSONDecodeError, ValueError) as e:
        return None, {**meta, "error": f"Failed to parse JSON: {e}", "raw_response": text[:1000]}

    # Build KnowledgeOutput (video_id, url, study_date filled by caller)
    try:
        knowledge = KnowledgeOutput.from_dict({
            "video_id": "",
            "title": title,
            "channel": channel,
            "url": "",
            "study_date": "",
            **data,
        })
    except Exception as e:
        return None, {**meta, "error": f"Failed to build KnowledgeOutput: {e}"}

    return knowledge, meta


def _extract_json(text: str) -> dict:
    """Extract JSON from API response, handling optional markdown fences."""
    text = text.strip()
    # Strip markdown JSON fences if present
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else 3
        text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return json.loads(text)
