"""Text preprocessing for ElevenLabs TTS — normalize text to reduce errors.

Handles: punctuation, numbers, currency, units, acronyms, product names.
Stdlib only — no external deps.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Acronym expansions (space-separated for TTS)
# ---------------------------------------------------------------------------

ACRONYMS: dict[str, str] = {
    "USB-C": "U S B C",
    "USB": "U S B",
    "AI": "A I",
    "ANC": "A N C",
    "AAC": "A A C",
    "LDAC": "L D A C",
    "DSEE": "D S E E",
    "EQ": "E Q",
    "IP": "I P",
    "IPX": "I P X",
    "IPX4": "I P X 4",
    "IPX5": "I P X 5",
    "IPX7": "I P X 7",
    "NFC": "N F C",
    "BT": "bluetooth",
    "SBC": "S B C",
    "aptX": "apt X",
    "HD": "H D",
    "dB": "decibels",
    "Hz": "hertz",
    "kHz": "kilohertz",
    "LUFS": "L U F S",
    "LED": "L E D",
    "TWS": "T W S",
    "iOS": "I O S",
    "API": "A P I",
    "RGB": "R G B",
}

# ---------------------------------------------------------------------------
# Unit expansions
# ---------------------------------------------------------------------------

UNIT_PATTERNS: list[tuple[str, str]] = [
    (r"(\d+)\s*mAh", r"\1 milliamp hours"),
    (r"(\d+)\s*mm", r"\1 millimeters"),
    (r"(\d+)\s*ms", r"\1 milliseconds"),
    (r"(\d+)\s*hrs?", r"\1 hours"),
    (r"(\d+)\s*mins?", r"\1 minutes"),
    (r"(\d+)\s*secs?", r"\1 seconds"),
    (r"(\d+)\s*gb", r"\1 gigabytes"),
    (r"(\d+)\s*mb", r"\1 megabytes"),
    (r"(\d+)\s*g\b", r"\1 grams"),
    (r"(\d+)\s*oz", r"\1 ounces"),
]

# ---------------------------------------------------------------------------
# Number words (for common values)
# ---------------------------------------------------------------------------

_ONES = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
    5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
    10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
    14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
    18: "eighteen", 19: "nineteen",
}
_TENS = {
    2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
    6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety",
}


def _number_to_words(n: int) -> str:
    """Convert integer to English words (0–999999)."""
    if n < 0:
        return "negative " + _number_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + ("-" + _ONES[ones] if ones else "")
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        result = _ONES[hundreds] + " hundred"
        if rem:
            result += " " + _number_to_words(rem)
        return result
    if n < 1_000_000:
        thousands, rem = divmod(n, 1000)
        result = _number_to_words(thousands) + " thousand"
        if rem:
            result += " " + _number_to_words(rem)
        return result
    return str(n)


# ---------------------------------------------------------------------------
# Core preprocessing functions
# ---------------------------------------------------------------------------


def normalize_punctuation(text: str) -> str:
    """Clean punctuation that causes TTS issues."""
    # Long dashes to commas
    text = text.replace("—", ", ")
    text = text.replace("–", ", ")
    # Repeated punctuation
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    # Excessive parentheses — keep content, drop parens
    text = re.sub(r"\(([^)]+)\)", r", \1,", text)
    # Emojis (common unicode ranges)
    text = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
        r"\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
        r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]",
        "",
        text,
    )
    # Clean up double commas / spaces
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def normalize_currency(text: str) -> str:
    """Convert $XX.XX to spoken form."""
    def _price_with_cents(m: re.Match) -> str:
        dollars = int(m.group(1))
        cents_val = int(m.group(2))
        if cents_val == 0:
            return _number_to_words(dollars) + " dollars"
        if cents_val == 99:
            return _number_to_words(dollars) + " ninety-nine"
        return _number_to_words(dollars) + " " + _number_to_words(cents_val)

    def _price_whole(m: re.Match) -> str:
        return _number_to_words(int(m.group(1))) + " dollars"

    # Match $XX.XX first (more specific), then $XX
    text = re.sub(r"\$(\d{1,6})\.(\d{2})", _price_with_cents, text)
    text = re.sub(r"\$(\d{1,6})\b", _price_whole, text)
    return text


def normalize_numbers(text: str) -> str:
    """Convert numeric patterns to spoken form."""
    # X-in-1 patterns
    text = re.sub(
        r"(\d+)-in-(\d+)",
        lambda m: _number_to_words(int(m.group(1))) + " in " + _number_to_words(int(m.group(2))),
        text,
    )
    # Comma-separated thousands (10,000 → ten thousand)
    def _comma_num(m: re.Match) -> str:
        raw = m.group(0).replace(",", "")
        return _number_to_words(int(raw))
    text = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", _comma_num, text)

    return text


def normalize_units(text: str) -> str:
    """Expand unit abbreviations for TTS."""
    for pattern, replacement in UNIT_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def expand_acronyms(text: str) -> str:
    """Replace known acronyms with TTS-friendly expansions."""
    for acronym, expansion in sorted(ACRONYMS.items(), key=lambda x: -len(x[0])):
        # Word boundary match (case-sensitive for acronyms)
        text = re.sub(r"\b" + re.escape(acronym) + r"\b", expansion, text)
    return text


def simplify_product_codes(text: str) -> str:
    """Replace complex model codes after first mention with simpler references.

    E.g. "AB-1234X" on second+ occurrence → "this model"
    Only replaces patterns that look like model codes (letters+numbers+hyphens).
    """
    # Find product-code-like patterns (e.g. AB-1234X, CD-5678Y, EFG-AZ80)
    code_pattern = re.compile(r"\b[A-Z]{2,4}[-\s]?\d{2,5}[A-Z]*\d*\b")
    seen: dict[str, int] = {}

    def _replace(m: re.Match) -> str:
        code = m.group(0)
        seen[code] = seen.get(code, 0) + 1
        if seen[code] == 1:
            return code  # Keep first mention
        return "this model"

    return code_pattern.sub(_replace, text)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def strip_section_markers(text: str) -> str:
    """Remove [MARKER] lines from script text.

    Safety net so TTS never reads markers like [PRODUCT_5] aloud.
    """
    return re.sub(
        r"^\[(?:HOOK|AVATAR_INTRO|PRODUCT_\d+|RETENTION_RESET|CONCLUSION)\].*$",
        "",
        text,
        flags=re.MULTILINE,
    ).strip()


def preprocess(text: str) -> str:
    """Run the full preprocessing pipeline on script text.

    Order matters: currency before numbers, acronyms after units.
    """
    text = strip_section_markers(text)
    text = normalize_punctuation(text)
    text = normalize_currency(text)
    text = normalize_numbers(text)
    text = normalize_units(text)
    text = expand_acronyms(text)
    return text.strip()
