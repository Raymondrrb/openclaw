"""Error classification and retry with exponential backoff.

Used by page_reader, amazon_verify, and pipeline stages.

ErrorKind:
  TRANSIENT — timeout, network flake → retry with backoff
  SESSION   — login expired, CAPTCHA → 1 retry after callback
  PERMANENT — 404, out of stock → raise immediately
  CONFIG    — missing API key → raise immediately

Stdlib only.
"""

from __future__ import annotations

import sys
import time
from enum import Enum
from typing import Callable, TypeVar

T = TypeVar("T")


class ErrorKind(str, Enum):
    TRANSIENT = "transient"
    SESSION = "session"
    PERMANENT = "permanent"
    CONFIG = "config"


# Keyword patterns for classification (lowercased)
_TRANSIENT_PATTERNS = [
    "timeout", "timed out", "connection reset", "connection refused",
    "temporary failure", "service unavailable", "503", "502", "429",
    "too many requests", "rate limit", "econnreset", "econnrefused",
    "network is unreachable", "name resolution",
]

_SESSION_PATTERNS = [
    "captcha", "validatecaptcha", "not logged in", "login required",
    "session expired", "unauthorized", "401", "sign in", "bot detection",
    "robot", "access denied",
]

_PERMANENT_PATTERNS = [
    "404", "not found", "out of stock", "currently unavailable",
    "no longer available", "page not found", "does not exist",
]

_CONFIG_PATTERNS = [
    "api key", "api_key", "missing key", "not configured",
    "credentials", "environment variable",
]


def classify_error(error: Exception | str) -> ErrorKind:
    """Classify an error by pattern-matching against keyword lists."""
    text = str(error).lower()

    for pat in _CONFIG_PATTERNS:
        if pat in text:
            return ErrorKind.CONFIG

    for pat in _SESSION_PATTERNS:
        if pat in text:
            return ErrorKind.SESSION

    for pat in _PERMANENT_PATTERNS:
        if pat in text:
            return ErrorKind.PERMANENT

    for pat in _TRANSIENT_PATTERNS:
        if pat in text:
            return ErrorKind.TRANSIENT

    # Default: treat unknown errors as transient (safer for retries)
    return ErrorKind.TRANSIENT


def with_retry(
    fn: Callable[..., T],
    *,
    max_retries: int = 3,
    base_delay_s: float = 2.0,
    on_session_error: Callable[[], None] | None = None,
    _sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn() with retry logic based on error classification.

    TRANSIENT: retry up to max_retries with exponential backoff.
    SESSION:   1 retry after calling on_session_error callback.
    PERMANENT/CONFIG: raise immediately.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            kind = classify_error(exc)

            if kind == ErrorKind.PERMANENT or kind == ErrorKind.CONFIG:
                raise

            if kind == ErrorKind.SESSION:
                if attempt == 0 and on_session_error:
                    print(f"  [retry] Session error, running callback: {exc}", file=sys.stderr)
                    on_session_error()
                    continue  # one retry after callback
                raise

            # TRANSIENT: backoff
            if attempt < max_retries:
                delay = base_delay_s * (2 ** attempt)
                print(f"  [retry] Attempt {attempt + 1}/{max_retries + 1} failed ({exc}), "
                      f"retrying in {delay:.0f}s", file=sys.stderr)
                _sleep(delay)
            else:
                raise

    # Should never reach here, but satisfy type checker
    raise last_exc  # type: ignore[misc]
