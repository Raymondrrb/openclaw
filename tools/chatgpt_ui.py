#!/usr/bin/env python3
"""ChatGPT UI automation via OpenClaw Browser.

This module intentionally does NOT use any LLM API keys.
It drives the user's logged-in ChatGPT web session in the OpenClaw browser profile.

Primary use-case (RayViewsLab): generate structured JSON scripts via chatgpt.com UI,
then parse/validate them locally.
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from typing import Any, Dict, Optional


class ChatGPTUIError(RuntimeError):
    pass


def _run_browser_json(args: list[str], *, timeout_ms: int = 30000) -> Dict[str, Any]:
    cmd = ["openclaw", "browser", "--timeout", str(int(timeout_ms)), "--json", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        stderr = (p.stderr or "").strip()
        stdout = (p.stdout or "").strip()
        msg = stderr or stdout[:500] or "unknown error"
        raise ChatGPTUIError(f"OpenClaw browser failed (rc={p.returncode}): {msg}")
    out = (p.stdout or "").strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise ChatGPTUIError(f"OpenClaw browser returned non-JSON output: {out[:200]}")


def _pick_chatgpt_target_id(tabs: Dict[str, Any]) -> Optional[str]:
    for tab in tabs.get("tabs", []) or []:
        url = str(tab.get("url", "") or "")
        title = str(tab.get("title", "") or "")
        if "chatgpt.com" in url or title.strip().lower() == "chatgpt":
            tid = str(tab.get("targetId", "") or "").strip()
            if tid:
                return tid
    return None


def ensure_chatgpt_ready(*, timeout_ms: int = 30000) -> str:
    """Ensure OpenClaw browser is running and a ChatGPT tab is focused.

    Returns: targetId of the focused ChatGPT tab.
    """
    _run_browser_json(["start"], timeout_ms=timeout_ms)
    tabs = _run_browser_json(["tabs"], timeout_ms=timeout_ms)
    tid = _pick_chatgpt_target_id(tabs)
    if not tid:
        _run_browser_json(["open", "https://chatgpt.com/"], timeout_ms=timeout_ms)
        time.sleep(0.8)
        tabs = _run_browser_json(["tabs"], timeout_ms=timeout_ms)
        tid = _pick_chatgpt_target_id(tabs)
    if not tid:
        raise ChatGPTUIError("Could not locate a ChatGPT tab. Open chatgpt.com in the OpenClaw browser profile.")

    _run_browser_json(["focus", tid], timeout_ms=timeout_ms)

    # Navigate to a fresh chat (reduces context contamination).
    _run_browser_json(["navigate", "https://chatgpt.com/"], timeout_ms=timeout_ms)
    _run_browser_json(
        [
            "wait",
            "--fn",
            "() => !!document.querySelector('#prompt-textarea')",
            "--timeout-ms",
            "20000",
        ],
        timeout_ms=max(timeout_ms, 25000),
    )

    # Prefer speed + deterministic formatting: disable "Thinking" toggle if enabled.
    # (The UI label changes by locale; we match a few common variants.)
    _run_browser_json(
        [
            "evaluate",
            "--fn",
            """() => {
  const candidates = Array.from(document.querySelectorAll('button'))
    .filter(b => {
      const t = (b.innerText || '').trim().toLowerCase();
      const a = (b.getAttribute('aria-label') || '').trim().toLowerCase();
      const s = t + ' ' + a;
      return s.includes('pensar, clique para remover')
        || s.includes('think, click to remove')
        || s.includes('thinking, click to remove');
    });
  if (!candidates.length) return {disabled: false};
  candidates[0].click();
  return {disabled: true};
}""",
        ],
        timeout_ms=timeout_ms,
    )

    # Sanity check: composer must exist.
    ok = _run_browser_json(
        [
            "evaluate",
            "--fn",
            "() => ({hasComposer: !!document.querySelector('#prompt-textarea')})",
        ],
        timeout_ms=timeout_ms,
    ).get("result", {})
    if not ok or not ok.get("hasComposer"):
        raise ChatGPTUIError(
            "ChatGPT UI not ready in OpenClaw browser (composer not found). "
            "Likely not logged in; log in once in that browser profile and retry."
        )
    return tid


def _b64_utf8(s: str) -> str:
    return base64.b64encode((s or "").encode("utf-8")).decode("ascii")


def _eval_set_prompt(prompt: str, *, timeout_ms: int = 30000) -> None:
    b64 = _b64_utf8(prompt)
    fn = f"""() => {{
  const b64 = {json.dumps(b64)};
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const text = new TextDecoder('utf-8').decode(bytes);
  const el = document.querySelector('#prompt-textarea');
  if (!el) return {{ok: false, error: 'composer_missing'}};
  el.focus();
  // ProseMirror: set content via textContent and dispatch input.
  el.innerHTML = '';
  el.textContent = text;
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return {{ok: true, len: text.length}};
}}"""
    res = _run_browser_json(["evaluate", "--fn", fn], timeout_ms=timeout_ms).get("result", {})
    if not res or not res.get("ok"):
        raise ChatGPTUIError(f"Failed to set prompt text in ChatGPT UI: {res}")


def _eval_counts(*, timeout_ms: int = 30000) -> Dict[str, Any]:
    fn = """() => ({
  url: location.href,
  assistant: document.querySelectorAll('[data-message-author-role=\"assistant\"]').length,
  user: document.querySelectorAll('[data-message-author-role=\"user\"]').length,
  stop: !!document.querySelector('button[data-testid=\"stop-button\"], button[aria-label*=\"Stop\"], button[aria-label*=\"Parar\"], button[aria-label*=\"Interromper\"]'),
})"""
    return _run_browser_json(["evaluate", "--fn", fn], timeout_ms=timeout_ms).get("result", {}) or {}


def _eval_last_assistant_text(*, timeout_ms: int = 30000) -> str:
    fn = """() => {
  const msgs = Array.from(document.querySelectorAll('[data-message-author-role=\"assistant\"]'));
  const last = msgs.length ? msgs[msgs.length - 1] : null;
  return { ok: !!last, text: last ? last.innerText : '' };
}"""
    res = _run_browser_json(["evaluate", "--fn", fn], timeout_ms=timeout_ms).get("result", {}) or {}
    if not res.get("ok"):
        raise ChatGPTUIError("No assistant message found after generation.")
    return str(res.get("text", "") or "")


def send_prompt_and_wait_for_assistant(
    prompt: str,
    *,
    timeout_sec: int = 300,
    poll_sec: float = 1.0,
    timeout_ms: int = 30000,
) -> Dict[str, Any]:
    """Send a prompt to ChatGPT UI and wait for the assistant reply.

    Returns:
      {
        "conversation_url": str,
        "assistant_text": str,
      }
    """
    ensure_chatgpt_ready(timeout_ms=timeout_ms)

    before = _eval_counts(timeout_ms=timeout_ms)
    prev_assistant = int(before.get("assistant", 0) or 0)

    _eval_set_prompt(prompt, timeout_ms=timeout_ms)
    _run_browser_json(["press", "Enter"], timeout_ms=timeout_ms)

    start = time.time()
    last_url = str(before.get("url", "") or "")
    while time.time() - start < max(5, int(timeout_sec)):
        state = _eval_counts(timeout_ms=timeout_ms)
        last_url = str(state.get("url", "") or last_url)
        assistant_count = int(state.get("assistant", 0) or 0)
        stop = bool(state.get("stop", False))
        if assistant_count > prev_assistant and not stop:
            break
        time.sleep(max(0.25, float(poll_sec)))
    else:
        raise ChatGPTUIError(
            f"Timed out waiting for ChatGPT response (timeout={timeout_sec}s). "
            "Open the ChatGPT tab and confirm it can respond."
        )

    text = _eval_last_assistant_text(timeout_ms=max(timeout_ms, 45000))
    return {"conversation_url": last_url, "assistant_text": text}


def extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Extract a JSON object from ChatGPT output text.

    ChatGPT often wraps JSON in markdown fences or adds extra text; this extracts the
    first top-level {...} block and parses it.
    """
    s = str(raw_text or "").strip()
    if not s:
        raise ChatGPTUIError("Empty assistant response.")

    # Strip markdown fences if present.
    if s.startswith("```"):
        lines = s.splitlines()
        # Drop first fence line
        if lines:
            lines = lines[1:]
        # Drop last fence line
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()

    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ChatGPTUIError("Could not find a JSON object in assistant response.")
    candidate = s[start : end + 1]

    def _repair_control_chars_in_json_strings(text: str) -> str:
        # Replace raw control chars (<0x20) inside JSON strings with escaped forms.
        out = []
        in_str = False
        esc = False
        for ch in text:
            if not in_str:
                out.append(ch)
                if ch == '"':
                    in_str = True
                continue

            # in string
            if esc:
                out.append(ch)
                esc = False
                continue
            if ch == "\\":
                out.append(ch)
                esc = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue

            code = ord(ch)
            if code < 0x20:
                if ch == "\n":
                    out.append("\\n")
                elif ch == "\r":
                    out.append("\\r")
                elif ch == "\t":
                    out.append("\\t")
                else:
                    out.append("\\u%04x" % code)
            else:
                out.append(ch)

        return "".join(out)

    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError as e:
        repaired = _repair_control_chars_in_json_strings(candidate)
        if repaired != candidate:
            try:
                obj = json.loads(repaired)
            except json.JSONDecodeError:
                raise ChatGPTUIError(f"Assistant response is not valid JSON: {e}") from None
        else:
            raise ChatGPTUIError(f"Assistant response is not valid JSON: {e}") from None
    if not isinstance(obj, dict):
        raise ChatGPTUIError("Parsed JSON is not an object.")
    return obj
