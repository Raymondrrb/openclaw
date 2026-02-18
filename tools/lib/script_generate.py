"""Auto-generate video scripts via LLM APIs (OpenAI draft + Anthropic refinement).

Stdlib only — uses urllib.request for HTTP calls, no external deps.

Flow:
    1. generate_draft() — sends draft_prompt to OpenAI GPT-4o → script_raw.txt
    2. generate_refinement() — sends refine_prompt (with raw draft) to Anthropic Claude → script_final.txt
    3. parse_script() — parses [SECTION] markers from generated text
    4. run_script_pipeline() — orchestrates the full flow

Env vars:
    OPENAI_API_KEY   — for GPT-4o draft generation
    ANTHROPIC_API_KEY — for Claude refinement pass
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import now_iso


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"
OPENAI_MAX_TOKENS = 4096
OPENAI_TEMPERATURE = 0.7

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
ANTHROPIC_MAX_TOKENS = 4096
ANTHROPIC_TEMPERATURE = 0.5

# Timeout for API calls (seconds)
API_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScriptGenResult:
    """Result of a script generation step."""
    success: bool
    text: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""
    file_path: str = ""
    duration_s: float = 0.0


@dataclass
class ScriptPipelineResult:
    """Result of the full script generation pipeline."""
    success: bool
    draft: ScriptGenResult | None = None
    refinement: ScriptGenResult | None = None
    script_raw_path: str = ""
    script_final_path: str = ""
    script_txt_path: str = ""
    word_count: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib)
# ---------------------------------------------------------------------------


def _ssl_context() -> ssl.SSLContext:
    """Create an SSL context for HTTPS requests."""
    ctx = ssl.create_default_context()
    return ctx


def _post_json(url: str, headers: dict, payload: dict, timeout: int = API_TIMEOUT) -> dict:
    """POST JSON to a URL and return the parsed response."""
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
# OpenAI: draft generation
# ---------------------------------------------------------------------------


def generate_draft(prompt: str, *, api_key: str = "") -> ScriptGenResult:
    """Send the draft prompt to OpenAI GPT-4o and return the generated script."""
    import time

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return ScriptGenResult(success=False, error="OPENAI_API_KEY not set")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional YouTube scriptwriter specializing in "
                    "product review/ranking videos. Write natural, engaging scripts "
                    "that feel human — not robotic or salesy. Every claim must be "
                    "grounded in the review evidence provided. When a fact comes from "
                    "a specific source (Wirecutter, RTINGS, PCMag), attribute it "
                    "naturally in the script."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": OPENAI_MAX_TOKENS,
        "temperature": OPENAI_TEMPERATURE,
    }

    start = time.time()
    try:
        resp = _post_json(OPENAI_API_URL, headers, payload)
    except RuntimeError as e:
        return ScriptGenResult(success=False, error=str(e), duration_s=time.time() - start)

    duration = time.time() - start

    # Parse response
    choices = resp.get("choices", [])
    if not choices:
        return ScriptGenResult(success=False, error="No choices in response", duration_s=duration)

    text = choices[0].get("message", {}).get("content", "")
    usage = resp.get("usage", {})

    return ScriptGenResult(
        success=True,
        text=text,
        model=resp.get("model", OPENAI_MODEL),
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        duration_s=duration,
    )


# ---------------------------------------------------------------------------
# Anthropic: refinement pass
# ---------------------------------------------------------------------------


def generate_refinement(prompt: str, *, api_key: str = "") -> ScriptGenResult:
    """Send the refinement prompt to Anthropic Claude and return the refined script."""
    import time

    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return ScriptGenResult(success=False, error="ANTHROPIC_API_KEY not set")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": ANTHROPIC_MAX_TOKENS,
        "temperature": ANTHROPIC_TEMPERATURE,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    start = time.time()
    try:
        resp = _post_json(ANTHROPIC_API_URL, headers, payload)
    except RuntimeError as e:
        return ScriptGenResult(success=False, error=str(e), duration_s=time.time() - start)

    duration = time.time() - start

    # Parse response
    content_blocks = resp.get("content", [])
    text = ""
    for block in content_blocks:
        if block.get("type") == "text":
            text += block.get("text", "")

    if not text:
        return ScriptGenResult(success=False, error="No text in response", duration_s=duration)

    usage = resp.get("usage", {})

    return ScriptGenResult(
        success=True,
        text=text,
        model=resp.get("model", ANTHROPIC_MODEL),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        duration_s=duration,
    )


# ---------------------------------------------------------------------------
# Script parsing
# ---------------------------------------------------------------------------


# Regex patterns that browser LLMs produce instead of formal [SECTION] markers.
# Order matters: match #5 before #1 to avoid false positives on substrings.
_PRODUCT_RE = re.compile(
    r"^#{0,3}\s*#?(\d)\s*[–—\-:\.]\s*.+$",
    re.IGNORECASE,
)
_RESET_RE = re.compile(
    r"^#{0,3}\s*(quick\s+reset|mid[- ]?video\s+reset|retention\s+reset)\b",
    re.IGNORECASE,
)
_CONCLUSION_RE = re.compile(
    r"^#{0,3}\s*(conclusion|conclusion\s*\+?\s*cta)\s*$",
    re.IGNORECASE,
)
_AVATAR_INTRO_RE = re.compile(
    r"^#{0,3}\s*\[?\s*avatar\s+intro\s*\]?\s*$",
    re.IGNORECASE,
)


def normalize_section_markers(text: str) -> str:
    """Convert informal browser-LLM section headers to formal [SECTION] markers.

    Browser LLMs (ChatGPT draft + Claude refinement) produce headers like:
        #5 – Narwal Freo Pro (Best Alternative)
        Quick Reset
        Conclusion + CTA

    This normalizes them to:
        [PRODUCT_5]
        [RETENTION_RESET]
        [CONCLUSION]

    Text before the first product marker gets [HOOK] prepended.
    Already-formal markers ([HOOK], [PRODUCT_5], etc.) pass through unchanged.
    """
    lines = text.splitlines()

    # Quick check: if formal markers are already present, return as-is
    formal_markers = {
        "[HOOK]", "[AVATAR_INTRO]",
        "[PRODUCT_5]", "[PRODUCT_4]", "[PRODUCT_3]", "[PRODUCT_2]", "[PRODUCT_1]",
        "[RETENTION_RESET]", "[CONCLUSION]",
    }
    for line in lines:
        if line.strip().upper() in formal_markers:
            return text

    result: list[str] = []
    found_first_product = False
    has_hook = False

    for line in lines:
        stripped = line.strip()

        # Check for inline avatar intro marker
        if _AVATAR_INTRO_RE.match(stripped):
            result.append("[AVATAR_INTRO]")
            continue

        # Check for product markers (#5 – Name, #4 – Name, etc.)
        m = _PRODUCT_RE.match(stripped)
        if m:
            num = m.group(1)
            if num in "54321":
                if not found_first_product and not has_hook:
                    # Insert [HOOK] before first product if there's preceding content
                    # Find where content starts (skip blank lines at top)
                    content_before = "\n".join(result).strip()
                    if content_before:
                        result.insert(0, "[HOOK]")
                        has_hook = True
                found_first_product = True
                result.append(f"[PRODUCT_{num}]")
                continue

        # Check for retention reset
        if _RESET_RE.match(stripped):
            result.append("[RETENTION_RESET]")
            continue

        # Check for conclusion
        if _CONCLUSION_RE.match(stripped):
            result.append("[CONCLUSION]")
            continue

        result.append(line)

    # If we found products but no hook was inserted and there's content before first product
    if found_first_product and not has_hook:
        # Find the index of the first [PRODUCT_ marker in result
        for i, line in enumerate(result):
            if line.strip().startswith("[PRODUCT_"):
                # Check if there's non-blank content before it
                before = "\n".join(result[:i]).strip()
                if before:
                    result.insert(0, "[HOOK]")
                break

    return "\n".join(result)


def extract_script_body(text: str) -> str:
    """Extract the script body from LLM output.

    LLMs sometimes wrap the script in markdown code blocks or add
    preamble/postamble text. This extracts just the script portion
    that contains [SECTION] markers.
    """
    # Normalize informal markers before parsing
    text = normalize_section_markers(text)
    lines = text.splitlines()

    # Known section markers (case-insensitive)
    section_markers = {
        "[HOOK]", "[AVATAR_INTRO]",
        "[PRODUCT_5]", "[PRODUCT_4]", "[PRODUCT_3]", "[PRODUCT_2]", "[PRODUCT_1]",
        "[RETENTION_RESET]", "[CONCLUSION]",
    }

    # Find first section marker
    start_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped in section_markers:
            start_idx = i
            break

    if start_idx < 0:
        # No markers found — strip markdown fences and return
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.index("\n") if "\n" in cleaned else 3
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    # Find end: last non-empty line that is part of the script body.
    # Walk forward from [CONCLUSION] to include its content, stop at
    # metadata sections (avatar intro, description, thumbnail, ---).
    conclusion_idx = -1
    for i in range(len(lines) - 1, start_idx - 1, -1):
        if lines[i].strip().upper() == "[CONCLUSION]":
            conclusion_idx = i
            break

    end_idx = len(lines)
    if conclusion_idx >= 0:
        # Include content after [CONCLUSION] until we hit metadata / postamble
        metadata_signals = (
            "avatar intro", "youtube description", "short youtube",
            "thumbnail headline", "thumbnail option", "---", "===",
            "i hope this", "here's the", "let me know",
        )
        for i in range(conclusion_idx + 1, len(lines)):
            lower = lines[i].strip().lower()
            if any(sig in lower for sig in metadata_signals):
                end_idx = i
                break
        else:
            # No metadata found — trim trailing blanks
            end_idx = len(lines)
            while end_idx > conclusion_idx and not lines[end_idx - 1].strip():
                end_idx -= 1

    result = "\n".join(lines[start_idx:end_idx]).strip()
    # Strip trailing markdown fence if present
    if result.endswith("```"):
        result = result[:-3].rstrip()
    return result


def extract_metadata(text: str) -> dict:
    """Extract avatar intro, description, and thumbnail headlines from after the script.

    Claude's refinement output includes these after the main script body.
    """
    meta: dict = {
        "avatar_intro": "",
        "youtube_description": "",
        "thumbnail_headlines": [],
    }

    lines = text.splitlines()

    # Find content after the script body
    in_avatar = False
    in_description = False
    in_thumbnails = False
    description_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        # Skip parenthetical meta-instructions like "(Max 320 characters, ...)"
        if lower.startswith("(") and lower.endswith(")"):
            continue

        if "avatar intro" in lower and (
            ":" in lower or "script" in lower or lower == "avatar intro"
        ):
            in_avatar = True
            in_description = False
            in_thumbnails = False
            # Check if intro is on the same line after ':'
            after_colon = stripped.split(":", 1)[-1].strip() if ":" in stripped else ""
            if after_colon and len(after_colon) > 10:
                meta["avatar_intro"] = after_colon.strip('"').strip("'")
            continue

        if any(kw in lower for kw in ("youtube description", "short youtube", "description:")):
            if "thumbnail" not in lower:
                in_avatar = False
                in_description = True
                in_thumbnails = False
                after = stripped.split(":", 1)[-1].strip() if ":" in stripped else ""
                if after and len(after) > 10:
                    description_lines.append(after)
                continue

        if "thumbnail" in lower and ("headline" in lower or "option" in lower):
            in_avatar = False
            in_description = False
            in_thumbnails = True
            continue

        if in_avatar and stripped and not meta["avatar_intro"]:
            meta["avatar_intro"] = stripped.strip('"').strip("'").lstrip("- ")
            in_avatar = False

        if in_description and stripped:
            if stripped.startswith("---") or stripped.startswith("==="):
                in_description = False
                continue
            description_lines.append(stripped)

        if in_thumbnails and stripped:
            # Parse numbered, bulleted, or plain headlines
            headline = stripped
            for prefix in ("1.", "2.", "3.", "4.", "-", "*"):
                if headline.startswith(prefix):
                    headline = headline[len(prefix):].strip()
                    break
            # Strip quotes
            headline = headline.strip('"').strip("'")
            if headline and len(headline.split()) <= 6:
                meta["thumbnail_headlines"].append(headline)

    if description_lines:
        meta["youtube_description"] = "\n".join(description_lines)

    return meta


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def _try_browser_draft(prompt: str) -> ScriptGenResult:
    """Attempt draft generation via browser (ChatGPT)."""
    try:
        from tools.lib.browser_llm import send_prompt_via_browser
        result = send_prompt_via_browser(prompt, provider="chatgpt", timeout_s=180)
        if result.success and result.text:
            return ScriptGenResult(
                success=True,
                text=result.text,
                model="chatgpt-browser",
                duration_s=result.duration_s,
            )
        return ScriptGenResult(success=False, error=result.error or "Browser draft empty")
    except Exception as exc:
        return ScriptGenResult(success=False, error=f"Browser draft error: {exc}")


def _try_browser_refinement(prompt: str) -> ScriptGenResult:
    """Attempt refinement via browser (Claude)."""
    try:
        from tools.lib.browser_llm import send_prompt_via_browser
        result = send_prompt_via_browser(prompt, provider="claude", timeout_s=180)
        if result.success and result.text:
            return ScriptGenResult(
                success=True,
                text=result.text,
                model="claude-browser",
                duration_s=result.duration_s,
            )
        return ScriptGenResult(success=False, error=result.error or "Browser refinement empty")
    except Exception as exc:
        return ScriptGenResult(success=False, error=f"Browser refinement error: {exc}")


def run_script_pipeline(
    draft_prompt: str,
    refine_prompt_template: str,
    output_dir: Path,
    *,
    openai_key: str = "",
    anthropic_key: str = "",
    skip_refinement: bool = False,
    use_browser: bool = False,
) -> ScriptPipelineResult:
    """Run the full script generation pipeline.

    1. Send draft_prompt to OpenAI → script_raw.txt
    2. Inject raw draft into refine_prompt_template → send to Anthropic → script_final.txt
    3. Copy final script to script.txt

    The refine_prompt_template should contain "(paste draft here)" which
    will be replaced with the actual draft text.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    result = ScriptPipelineResult(success=False)

    # Step 1: Draft — browser-first (ChatGPT) with API fallback
    draft_result = None
    _okey = openai_key or os.environ.get("OPENAI_API_KEY", "")

    if use_browser or not _okey:
        print("  Generating draft via browser (ChatGPT)...")
        draft_result = _try_browser_draft(draft_prompt)
        if not draft_result.success:
            print(f"  Browser draft failed: {draft_result.error}")
            if _okey:
                print("  Falling back to OpenAI API...")
                draft_result = None  # let API try below

    if draft_result is None:
        print("  Generating draft via OpenAI GPT-4o...")
        draft_result = generate_draft(draft_prompt, api_key=openai_key)

    result.draft = draft_result

    if not draft_result.success:
        result.errors.append(f"Draft generation failed: {draft_result.error}")
        return result

    # Write script_raw.txt
    raw_path = output_dir / "script_raw.txt"
    raw_text = extract_script_body(draft_result.text)
    raw_path.write_text(raw_text, encoding="utf-8")
    result.script_raw_path = str(raw_path)
    draft_result.file_path = str(raw_path)

    word_count = len(raw_text.split())
    print(f"  Draft: {word_count} words, {draft_result.duration_s:.1f}s")
    print(f"  Tokens: {draft_result.input_tokens} in / {draft_result.output_tokens} out")

    if skip_refinement:
        # Use raw draft as final
        final_path = output_dir / "script.txt"
        final_path.write_text(raw_text, encoding="utf-8")
        result.script_txt_path = str(final_path)
        result.word_count = word_count
        result.success = True
        return result

    # Step 2: Refinement — browser-first (Claude) with API fallback
    refine_prompt = refine_prompt_template.replace("(paste draft here)", raw_text)
    refine_result = None
    _akey = anthropic_key or os.environ.get("ANTHROPIC_API_KEY", "")

    if use_browser or not _akey:
        print("  Refining via browser (Claude)...")
        refine_result = _try_browser_refinement(refine_prompt)
        if not refine_result.success:
            print(f"  Browser refinement failed: {refine_result.error}")
            if _akey:
                print("  Falling back to Anthropic API...")
                refine_result = None  # let API try below

    if refine_result is None:
        print("  Refining via Anthropic Claude...")
        refine_result = generate_refinement(refine_prompt, api_key=anthropic_key)

    result.refinement = refine_result

    if not refine_result.success:
        # Fall back to raw draft
        print(f"  Refinement failed: {refine_result.error}")
        print("  Using raw draft as final script")
        result.errors.append(f"Refinement failed (using raw draft): {refine_result.error}")
        final_text = raw_text
    else:
        final_text = extract_script_body(refine_result.text)
        final_word_count = len(final_text.split())
        print(f"  Refined: {final_word_count} words, {refine_result.duration_s:.1f}s")
        print(f"  Tokens: {refine_result.input_tokens} in / {refine_result.output_tokens} out")

        # Write script_final.txt (full output with metadata)
        final_full_path = output_dir / "script_final.txt"
        final_full_path.write_text(refine_result.text, encoding="utf-8")
        result.script_final_path = str(final_full_path)
        refine_result.file_path = str(final_full_path)

        # Extract metadata (avatar intro, description, thumbnails)
        meta = extract_metadata(refine_result.text)
        meta_path = output_dir / "script_gen_meta.json"
        gen_meta = {
            "generated_at": now_iso(),
            "draft_model": draft_result.model,
            "draft_tokens": {"input": draft_result.input_tokens, "output": draft_result.output_tokens},
            "draft_duration_s": draft_result.duration_s,
            "refine_model": refine_result.model,
            "refine_tokens": {"input": refine_result.input_tokens, "output": refine_result.output_tokens},
            "refine_duration_s": refine_result.duration_s,
            "avatar_intro": meta.get("avatar_intro", ""),
            "youtube_description": meta.get("youtube_description", ""),
            "thumbnail_headlines": meta.get("thumbnail_headlines", []),
        }
        meta_path.write_text(json.dumps(gen_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write script.txt (the canonical script file)
    script_path = output_dir / "script.txt"
    script_path.write_text(final_text, encoding="utf-8")
    result.script_txt_path = str(script_path)
    result.word_count = len(final_text.split())
    result.success = True

    print(f"  Script written: {result.word_count} words")
    return result
