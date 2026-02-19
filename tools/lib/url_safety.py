"""URL and text safety checks for pipeline data.

Inspired by sheeki03/tirith — lightweight Python port of the checks
most relevant to ingesting external URLs and titles from Brave/YouTube.

Usage:
    from lib.url_safety import check_url, sanitize_text, check_items

    findings = check_url("https://exаmple.com")  # Cyrillic 'а'
    clean = sanitize_text("some title\u200bwith zero-width")
    items, report = check_items(brave_results)
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse
from typing import Any, Dict, List, Tuple

# Characters that look like ASCII but aren't (most common homoglyphs)
# Subset of Unicode confusables relevant to URL hostnames
_CONFUSABLE_MAP: Dict[str, str] = {
    "\u0430": "a",  # Cyrillic а
    "\u0435": "e",  # Cyrillic е
    "\u043e": "o",  # Cyrillic о
    "\u0440": "p",  # Cyrillic р
    "\u0441": "c",  # Cyrillic с
    "\u0443": "y",  # Cyrillic у
    "\u0445": "x",  # Cyrillic х
    "\u0456": "i",  # Cyrillic і
    "\u0455": "s",  # Cyrillic ѕ
    "\u04bb": "h",  # Cyrillic һ
    "\u0501": "d",  # Cyrillic ԁ
    "\u051b": "q",  # Cyrillic ԛ
    "\u0261": "g",  # Latin ɡ
    "\u03bf": "o",  # Greek ο
    "\u03b1": "a",  # Greek α
    "\u03b5": "e",  # Greek ε
    "\u03b9": "i",  # Greek ι
    "\u03ba": "k",  # Greek κ
    "\u03c1": "p",  # Greek ρ
    "\u03c5": "u",  # Greek υ
    "\u0391": "A",  # Greek Α
    "\u0392": "B",  # Greek Β
    "\u0395": "E",  # Greek Ε
    "\u0397": "H",  # Greek Η
    "\u039a": "K",  # Greek Κ
    "\u039c": "M",  # Greek Μ
    "\u039d": "N",  # Greek Ν
    "\u039f": "O",  # Greek Ο
    "\u03a1": "P",  # Greek Ρ
    "\u03a4": "T",  # Greek Τ
    "\u03a7": "X",  # Greek Χ
    "\u0410": "A",  # Cyrillic А
    "\u0412": "B",  # Cyrillic В
    "\u0415": "E",  # Cyrillic Е
    "\u041d": "H",  # Cyrillic Н
    "\u041e": "O",  # Cyrillic О
    "\u0420": "P",  # Cyrillic Р
    "\u0421": "C",  # Cyrillic С
    "\u0422": "T",  # Cyrillic Т
    "\u0425": "X",  # Cyrillic Х
}

# Dangerous invisible/formatting Unicode characters
_INVISIBLE_CHARS = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
    "\u202a",  # left-to-right embedding
    "\u202b",  # right-to-left embedding
    "\u202c",  # pop directional formatting
    "\u202d",  # left-to-right override
    "\u202e",  # right-to-left override (can reverse displayed text)
    "\u2060",  # word joiner
    "\u2061",  # function application
    "\u2062",  # invisible times
    "\u2063",  # invisible separator
    "\u2064",  # invisible plus
    "\ufeff",  # BOM / zero-width no-break space
    "\ufff9",  # interlinear annotation anchor
    "\ufffa",  # interlinear annotation separator
    "\ufffb",  # interlinear annotation terminator
}

# ANSI escape sequence pattern
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\].*?\x07")


class Finding:
    """A single security finding."""
    __slots__ = ("severity", "rule", "detail")

    def __init__(self, severity: str, rule: str, detail: str):
        self.severity = severity  # CRITICAL, HIGH, MEDIUM, LOW
        self.rule = rule
        self.detail = detail

    def __repr__(self):
        return f"[{self.severity}] {self.rule}: {self.detail}"


def check_url(url: str) -> List[Finding]:
    """Check a single URL for safety issues."""
    findings: List[Finding] = []
    if not url:
        return findings

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        findings.append(Finding("HIGH", "malformed_url", f"Cannot parse URL: {url[:80]}"))
        return findings

    host = parsed.hostname or ""

    # 1. Non-ASCII in hostname (homograph attack)
    if host and any(ord(c) > 127 for c in host):
        confusables = []
        for c in host:
            if c in _CONFUSABLE_MAP:
                name = unicodedata.name(c, f"U+{ord(c):04X}")
                confusables.append(f"'{c}' (U+{ord(c):04X} {name}) looks like '{_CONFUSABLE_MAP[c]}'")
        if confusables:
            findings.append(Finding(
                "CRITICAL", "homograph_hostname",
                f"Hostname '{host}' contains confusable characters: {'; '.join(confusables)}"
            ))
        else:
            findings.append(Finding(
                "HIGH", "non_ascii_hostname",
                f"Hostname '{host}' contains non-ASCII characters"
            ))

    # 2. Punycode domain
    if host:
        for label in host.split("."):
            if label.startswith("xn--"):
                findings.append(Finding(
                    "HIGH", "punycode_domain",
                    f"Hostname contains punycode label '{label}'"
                ))
                break

    # 3. Userinfo credential leak (user:pass@host)
    if parsed.username or parsed.password:
        findings.append(Finding(
            "HIGH", "credential_in_url",
            f"URL contains embedded credentials (userinfo): {parsed.username}@{host}"
        ))

    # 4. Insecure transport
    if parsed.scheme == "http" and host and host not in ("localhost", "127.0.0.1", "::1"):
        findings.append(Finding(
            "MEDIUM", "insecure_transport",
            f"Plain HTTP to external host: {host}"
        ))

    # 5. Suspicious port
    if parsed.port and parsed.port not in (80, 443, 8080, 8443):
        findings.append(Finding(
            "LOW", "non_standard_port",
            f"Non-standard port {parsed.port} on {host}"
        ))

    return findings


def sanitize_text(text: str) -> str:
    """Remove dangerous invisible characters and ANSI escapes from text."""
    if not text:
        return text
    # Strip ANSI escape sequences
    text = _ANSI_RE.sub("", text)
    # Strip dangerous invisible characters
    return "".join(c for c in text if c not in _INVISIBLE_CHARS)


def check_items(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate and sanitize a list of search result items.

    Returns (clean_items, flagged_report) where:
    - clean_items: items with sanitized text and URLs checked
    - flagged_report: list of {index, url, findings} for items with issues
    """
    clean = []
    flagged = []

    for i, item in enumerate(items):
        url = item.get("url", "")
        findings = check_url(url)

        # Sanitize text fields
        sanitized = dict(item)
        for field in ("title", "description"):
            if field in sanitized and isinstance(sanitized[field], str):
                sanitized[field] = sanitize_text(sanitized[field])

        # Flag critical/high findings but still include the item (marked)
        if any(f.severity in ("CRITICAL", "HIGH") for f in findings):
            sanitized["_safety_flag"] = [repr(f) for f in findings]
            flagged.append({
                "index": i,
                "url": url[:120],
                "findings": [repr(f) for f in findings],
            })

        clean.append(sanitized)

    return clean, flagged
