"""Video script schema: structure, validation, language rules, compliance.

Amazon Associates product ranking channel (Top 5 format).
Stdlib only — no external deps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Word count targets
SCRIPT_WORD_MIN = 1300
SCRIPT_WORD_MAX = 1800
SPEAKING_WPM = 150  # ~150 words per minute average

# Section word limits
HOOK_WORD_MIN = 100
HOOK_WORD_MAX = 150
PRODUCT_WORD_MIN = 200
PRODUCT_WORD_MAX = 300
RETENTION_RESET_WORD_MIN = 50
RETENTION_RESET_WORD_MAX = 80
AVATAR_INTRO_MAX_CHARS = 320

# Thumbnail headline: max 4 words
THUMBNAIL_HEADLINE_MAX_WORDS = 4

PRODUCT_COUNT = 5

SECTION_ORDER = (
    "hook",
    "avatar_intro",
    "product_5",
    "product_4",
    "product_3",
    "retention_reset",
    "product_2",
    "product_1",
    "conclusion",
)

# Words that signal hype / exaggeration — reject these
HYPE_WORDS = frozenset({
    "insane", "crazy", "unbelievable", "mind-blowing", "mind blowing",
    "game-changer", "game changer", "jaw-dropping", "jaw dropping",
    "incredible", "revolutionary", "groundbreaking", "earth-shattering",
    "life-changing", "life changing", "unreal", "epic", "literally insane",
    "absolutely insane", "out of this world",
})

# AI cliche phrases — flag these for removal
AI_CLICHES = (
    "when it comes to",
    "in today's fast-paced world",
    "in today's world",
    "whether you're a beginner or professional",
    "whether you're a beginner or a pro",
    "in this day and age",
    "it goes without saying",
    "at the end of the day",
    "without further ado",
    "let's dive in",
    "let's dive right in",
    "buckle up",
    "you won't believe",
    "stay tuned",
    "in today's video",
    "hey guys welcome back",
    "what's up guys",
    "so without wasting any time",
    "before we get started",
    "make sure to like and subscribe",
    "smash that like button",
    "hit that bell icon",
)

# Compliance: phrases that must NOT appear
COMPLIANCE_VIOLATIONS = (
    "official amazon partner",
    "guaranteed lowest price",
    "lowest price guaranteed",
    "best price guaranteed",
    "limited time only",
    "hurry before it's gone",
    "act now",
    "don't miss out",
    "once in a lifetime",
    "exclusive deal",
    "secret discount",
)

# Required affiliate disclosure (must appear in conclusion)
AFFILIATE_DISCLOSURE_KEYWORDS = ("affiliate", "commission", "no extra cost")

# Charismatic signature types
CHARISMATIC_TYPES = ("reality_check", "micro_humor", "micro_comparison")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProductEntry:
    """One product in the ranking (position 1-5)."""
    rank: int  # 1 = best, 5 = entry-level pick
    name: str
    positioning: str = ""       # why it made the list
    benefits: list[str] = field(default_factory=list)  # 2-3 core benefits
    target_audience: str = ""   # who it's for
    downside: str = ""          # honest downside (mandatory)
    amazon_url: str = ""        # Associates link
    transition: str = ""        # bridge to next product
    source_evidence: list[dict] = field(default_factory=list)  # [{source, url, label, reasons}]


@dataclass
class ScriptRequest:
    """Input for script generation."""
    niche: str                                    # e.g. "portable speakers", "desk accessories"
    products: list[ProductEntry] = field(default_factory=list)
    target_duration_min: int = 8                  # minutes
    target_duration_max: int = 12
    charismatic_type: str = "reality_check"       # which signature element
    reference_videos: list[str] = field(default_factory=list)  # URLs for viral pattern extraction


@dataclass
class ScriptSection:
    """One section of the final script."""
    section_type: str  # one of SECTION_ORDER
    content: str
    word_count: int = 0

    def __post_init__(self):
        self.word_count = _count_words(self.content)


@dataclass
class ScriptOutput:
    """Complete validated script output."""
    sections: list[ScriptSection] = field(default_factory=list)
    avatar_intro: str = ""
    youtube_description: str = ""
    thumbnail_headlines: list[str] = field(default_factory=list)
    total_word_count: int = 0
    estimated_duration_min: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_words(text: str) -> int:
    """Count words in text, ignoring stage directions in brackets."""
    # Remove [stage directions] and (parentheticals)
    cleaned = re.sub(r"\[.*?\]", "", text)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    return len(cleaned.split())


def _find_phrases(text: str, phrases) -> list[str]:
    """Find which phrases from a collection appear in text (case-insensitive)."""
    lower = text.lower()
    return [p for p in phrases if p in lower]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_request(req: ScriptRequest) -> list[str]:
    """Validate a ScriptRequest before generation."""
    errors: list[str] = []

    if not req.niche.strip():
        errors.append("niche is required")

    if len(req.products) != PRODUCT_COUNT:
        errors.append(f"Exactly {PRODUCT_COUNT} products required, got {len(req.products)}")

    if req.charismatic_type not in CHARISMATIC_TYPES:
        errors.append(
            f"Invalid charismatic_type {req.charismatic_type!r}. "
            f"Must be one of: {', '.join(CHARISMATIC_TYPES)}"
        )

    # Validate each product
    ranks_seen: set[int] = set()
    for p in req.products:
        if p.rank < 1 or p.rank > 5:
            errors.append(f"Product rank must be 1-5, got {p.rank}")
        if p.rank in ranks_seen:
            errors.append(f"Duplicate rank {p.rank}")
        ranks_seen.add(p.rank)

        if not p.name.strip():
            errors.append(f"Product at rank {p.rank} has no name")

        # Require real product data to prevent LLM hallucination
        if not p.amazon_url.strip():
            errors.append(f"Product #{p.rank} '{p.name}' has no Amazon URL — run research first")

        if not p.downside.strip():
            errors.append(f"Product #{p.rank} '{p.name}' has no downside — run research first")

        if not p.benefits:
            errors.append(f"Product #{p.rank} '{p.name}' has no benefits — run research first")

    return errors


def validate_script(output: ScriptOutput) -> list[str]:
    """Validate a completed script against all rules."""
    errors: list[str] = []
    warnings: list[str] = []

    full_text = "\n".join(s.content for s in output.sections)
    total_words = _count_words(full_text)
    output.total_word_count = total_words
    output.estimated_duration_min = round(total_words / SPEAKING_WPM, 1)

    # --- Word count ---
    if total_words < SCRIPT_WORD_MIN:
        errors.append(f"Script too short: {total_words} words (min {SCRIPT_WORD_MIN})")
    if total_words > SCRIPT_WORD_MAX:
        errors.append(f"Script too long: {total_words} words (max {SCRIPT_WORD_MAX})")

    # --- Section structure ---
    section_types = [s.section_type for s in output.sections]
    expected = list(SECTION_ORDER)
    if section_types != expected:
        errors.append(
            f"Section order mismatch. Expected: {expected}, got: {section_types}"
        )

    # --- Per-section word counts ---
    for s in output.sections:
        if s.section_type == "hook":
            if s.word_count < HOOK_WORD_MIN:
                errors.append(f"Hook too short: {s.word_count} words (min {HOOK_WORD_MIN})")
            if s.word_count > HOOK_WORD_MAX:
                errors.append(f"Hook too long: {s.word_count} words (max {HOOK_WORD_MAX})")

        if s.section_type.startswith("product_"):
            if s.word_count < PRODUCT_WORD_MIN:
                errors.append(
                    f"{s.section_type} too short: {s.word_count} words (min {PRODUCT_WORD_MIN})"
                )
            if s.word_count > PRODUCT_WORD_MAX:
                errors.append(
                    f"{s.section_type} too long: {s.word_count} words (max {PRODUCT_WORD_MAX})"
                )

        if s.section_type == "retention_reset":
            if s.word_count < RETENTION_RESET_WORD_MIN:
                errors.append(
                    f"Retention reset too short: {s.word_count} words (min {RETENTION_RESET_WORD_MIN})"
                )
            if s.word_count > RETENTION_RESET_WORD_MAX:
                errors.append(
                    f"Retention reset too long: {s.word_count} words (max {RETENTION_RESET_WORD_MAX})"
                )

    # --- Avatar intro ---
    if output.avatar_intro:
        if len(output.avatar_intro) > AVATAR_INTRO_MAX_CHARS:
            errors.append(
                f"Avatar intro too long: {len(output.avatar_intro)} chars (max {AVATAR_INTRO_MAX_CHARS})"
            )
    else:
        errors.append("Avatar intro is required")

    # --- Thumbnail headlines ---
    for i, hl in enumerate(output.thumbnail_headlines):
        wc = len(hl.split())
        if wc > THUMBNAIL_HEADLINE_MAX_WORDS:
            errors.append(
                f"Thumbnail headline #{i+1} too long: {wc} words (max {THUMBNAIL_HEADLINE_MAX_WORDS})"
            )

    if len(output.thumbnail_headlines) < 3:
        errors.append(
            f"Need at least 3 thumbnail headlines, got {len(output.thumbnail_headlines)}"
        )

    # --- Language rules ---
    hype_found = _find_phrases(full_text, HYPE_WORDS)
    if hype_found:
        errors.append(f"Hype words found (remove): {', '.join(hype_found)}")

    cliches_found = _find_phrases(full_text, AI_CLICHES)
    if cliches_found:
        errors.append(f"AI cliches found (remove): {', '.join(cliches_found)}")

    # --- Compliance ---
    violations = _find_phrases(full_text, COMPLIANCE_VIOLATIONS)
    if violations:
        errors.append(f"Compliance violations (remove): {', '.join(violations)}")

    # Check affiliate disclosure in conclusion
    conclusion = [s for s in output.sections if s.section_type == "conclusion"]
    if conclusion:
        conc_lower = conclusion[0].content.lower()
        missing_disclosure = [
            kw for kw in AFFILIATE_DISCLOSURE_KEYWORDS if kw not in conc_lower
        ]
        if missing_disclosure:
            errors.append(
                f"Conclusion missing affiliate disclosure keywords: {', '.join(missing_disclosure)}"
            )

    # --- Honest downside check (look for downside phrasing in product sections) ---
    downside_markers = (
        "one thing to keep in mind",
        "keep in mind",
        "downside",
        "the catch",
        "not perfect",
        "one drawback",
        "one con",
        "one issue",
        "minor issue",
        "only complaint",
        "worth noting",
        "the trade-off",
        "trade off",
        "on the flip side",
        "however",
        "that said",
    )
    for s in output.sections:
        if s.section_type.startswith("product_"):
            has_downside = any(m in s.content.lower() for m in downside_markers)
            if not has_downside:
                errors.append(
                    f"{s.section_type}: missing honest downside. "
                    "Each product must include at least one candid limitation."
                )

    return errors


# ---------------------------------------------------------------------------
# LLM prompt generation (for workflow steps)
# ---------------------------------------------------------------------------


def build_extraction_prompt(reference_urls: list[str], niche: str) -> str:
    """Step 1: Prompt for viral pattern extraction."""
    url_list = "\n".join(f"- {u}" for u in reference_urls) if reference_urls else "- (no references provided, use general Top 5 product ranking patterns)"
    return f"""Analyze these viral Top 5 product ranking videos in the "{niche}" niche:

{url_list}

Extract and summarize in bullet form:
1. Hook structure — how do they open? What tension/problem do they lead with?
2. Sentence pacing — short vs long sentence rhythm
3. Emotional triggers — what makes viewers keep watching?
4. Retention tactics — pattern interrupts, cliffhangers, comparisons
5. Transition style — how do they bridge between products?
6. Tone — casual, authoritative, enthusiastic?

Be specific. Quote notable phrases if relevant. Focus on patterns that drive retention."""


def build_draft_prompt(req: ScriptRequest, extraction_notes: str) -> str:
    """Step 2: Prompt for GPT to expand into structured draft."""
    product_block = ""
    for p in sorted(req.products, key=lambda x: -x.rank):  # 5 down to 1
        benefits_str = "\n".join(f"    - {b}" for b in p.benefits) if p.benefits else "    - (expand from product research)"
        downside_str = p.downside or "(must include one real limitation)"

        # Source-attributed evidence
        evidence_str = ""
        if p.source_evidence:
            evidence_lines = []
            for src in p.source_evidence:
                src_name = src.get("source", src.get("name", "Unknown"))
                src_label = src.get("label", "")
                reasons = src.get("reasons", [])
                label_note = f" [{src_label}]" if src_label else ""
                evidence_lines.append(f"      {src_name}{label_note}:")
                for r in reasons[:3]:
                    evidence_lines.append(f"        - {r}")
            if evidence_lines:
                evidence_str = "\n    Review sources (use these facts, attribute when impactful):\n" + "\n".join(evidence_lines)

        product_block += f"""
  Product #{p.rank}: {p.name}
    Positioning: {p.positioning or '(determine from research)'}
    Benefits:
{benefits_str}
    Target audience: {p.target_audience or '(determine from research)'}
    Honest downside: {downside_str}{evidence_str}
    Amazon URL: {p.amazon_url or '(to be added)'}
"""

    return f"""Write a YouTube script for a Top 5 product ranking video in the "{req.niche}" niche.

TARGET: {SCRIPT_WORD_MIN}–{SCRIPT_WORD_MAX} words ({req.target_duration_min}–{req.target_duration_max} minutes at ~{SPEAKING_WPM} wpm).

VIRAL PATTERNS TO APPLY:
{extraction_notes}

PRODUCTS (ranked 5 to 1):
{product_block}

MANDATORY STRUCTURE (word counts are HARD minimums — do NOT go under):
1. Hook (120–145 words) — open with problem or tension, NOT "In today's video"
2. [Avatar Intro] — will be inserted separately (3–6 sec)
3. Product #5 (230–280 words)
4. Product #4 (230–280 words)
5. Product #3 (230–280 words)
6. Mid-video retention reset (50–80 words) — pattern interrupt
7. Product #2 (230–280 words)
8. Product #1 (230–280 words)
9. Conclusion + CTA + affiliate disclosure

EACH PRODUCT MUST INCLUDE:
A) Quick positioning — why it made the list
B) 2–3 specific benefits in REAL-LIFE language (not specs)
   - BAD: "40dB ANC reduction" → GOOD: "blocks out airplane noise"
   - BAD: "30-hour battery" → GOOD: "lasts a full work week on one charge"
C) Who it's for (specific, practical — our audience is 30-65+, NOT tech enthusiasts)
D) One honest downside (mandatory — builds trust)
E) Warranty/return mention if available in evidence
F) Transition line to next product

AUDIENCE: Practical buyers aged 30-65+ who want to buy the right thing ONCE.
They value trust, reliability, and low-regret decisions over novelty.
Use calm authority. Reduce anxiety with phrases like "safe choice", "easy return",
"well-established brand". Give price context ("costs about as much as...").

TONE: Confident, grounded, conversational. Not salesy. Not tech-bro.

DO NOT USE: "insane", "crazy", "unbelievable", "game-changer", "mind-blowing",
"In today's video", "let's dive in", "without further ado", "smash that like button".

Include affiliate disclosure in conclusion:
"Links in the description may be affiliate links, which means I may earn a small commission at no extra cost to you."

Write the full script now. Use natural sentence rhythm — mix short punchy lines with longer explanations."""


def build_refinement_prompt(draft: str, charismatic_type: str) -> str:
    """Step 3: Prompt for Claude to refine the draft."""
    charismatic_instructions = {
        "reality_check": (
            'Insert one "reality check" line somewhere in the script. '
            'Example: "Remember, price doesn\'t always mean better."'
        ),
        "micro_humor": (
            "Insert one subtle humor line somewhere in the script. "
            'Example: "And no, this isn\'t one of those \'looks cool but breaks in a week\' gadgets."'
        ),
        "micro_comparison": (
            "Insert one everyday-life comparison somewhere in the script. "
            "Example: \"It's the kind of upgrade you don't notice until you go back to the old version.\""
        ),
    }

    return f"""Refine this YouTube product ranking script. Your job is quality control, not rewriting.

DRAFT:
---
{draft}
---

REFINEMENT CHECKLIST:

1. REMOVE AI cliches: "when it comes to", "in today's fast-paced world", "whether you're a beginner or professional", "let's dive in", "without further ado", etc.

2. REDUCE repetition: find repeated sentence structures and vary them. Mix short punchy lines with longer explanations.

3. TIGHTEN sentences: cut filler words, but do NOT trim sections below their minimums. If a product section is already around 230 words, leave it — don't shorten further.

4. CHECK flow: transitions between products should feel natural, not formulaic.

5. VERIFY tone: confident, grounded, conversational. Not salesy or overhyped. NOT tech-bro.

6. CHARISMATIC ELEMENT: {charismatic_instructions.get(charismatic_type, charismatic_instructions["reality_check"])}

7. VERIFY each product has an honest downside.

8. WORD COUNT CHECK (these are HARD floors — expand sections that fall short):
   - Total script: {SCRIPT_WORD_MIN}–{SCRIPT_WORD_MAX} words
   - Each product section: minimum 230 words (add real-life context or comparison if under)
   - Hook: 120–145 words
   If any section is under its minimum, add useful content (a practical scenario, a comparison to a competitor, or a "who this is NOT for" line).

9. VERIFY affiliate disclosure is present in conclusion.

10. NO hype words: "insane", "crazy", "unbelievable", "game-changer", "mind-blowing", "revolutionary", "groundbreaking".

11. BUYER-TRUST CHECK (audience is 30-65+, practical, NOT tech enthusiasts):
    - Specs must be translated to real-life impact (not raw numbers)
    - Each product mentions who it's for in practical terms
    - Warranty/return info included when available
    - Price context is relational ("costs about as much as...")
    - No jargon without explanation

Return the refined script in full. Do not summarize or skip sections.

After the script, provide:
- Avatar intro script (1–2 sentences, max 320 characters, friendly and direct)
- Short YouTube description with affiliate disclosure
- 3 thumbnail headline options (max 4 words each)"""


def build_validation_prompt(script: str) -> str:
    """Step 4: Prompt for final validation pass."""
    return f"""Review this YouTube script for final approval. Check ALL of the following:

SCRIPT:
---
{script}
---

VALIDATION CHECKLIST:
1. Total word count between {SCRIPT_WORD_MIN}–{SCRIPT_WORD_MAX}
2. Each product section has an honest downside
3. Hook is NOT generic ("In today's video...")
4. Transitions between products are smooth
5. No compliance violations (no fake urgency, no "official Amazon partner", no fake discounts)
6. No hype words ("insane", "crazy", "unbelievable", etc.)
7. No AI cliches ("when it comes to", "in today's fast-paced world", etc.)
8. Affiliate disclosure present in conclusion
9. At least one charismatic element (reality check, micro humor, or micro comparison)
10. Sentence rhythm varies (not all same length)

For each item, respond PASS or FAIL with a brief explanation.
At the end, give an overall APPROVED or NEEDS REVISION verdict."""
