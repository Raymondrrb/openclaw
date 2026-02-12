"""Manual-first script workflow: brief generation and script review.

No API calls. All logic is deterministic text assembly from products.json
and optional seo.json data. Human stays in the creative loop.

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (shared with script_schema)
# ---------------------------------------------------------------------------

SCRIPT_WORD_MIN = 1300
SCRIPT_WORD_MAX = 1800
SPEAKING_WPM = 150

HYPE_WORDS = frozenset({
    "insane", "crazy", "unbelievable", "mind-blowing", "mind blowing",
    "game-changer", "game changer", "jaw-dropping", "jaw dropping",
    "incredible", "revolutionary", "groundbreaking", "earth-shattering",
    "life-changing", "life changing", "unreal", "epic",
})

AI_CLICHES = (
    "when it comes to", "in today's fast-paced world", "in today's world",
    "whether you're a beginner or professional", "in this day and age",
    "without further ado", "let's dive in", "let's dive right in",
    "buckle up", "you won't believe", "stay tuned", "in today's video",
    "hey guys welcome back", "what's up guys", "smash that like button",
)

COMPLIANCE_VIOLATIONS = (
    "official amazon partner", "guaranteed lowest price",
    "best price guaranteed", "limited time only", "act now",
    "don't miss out", "exclusive deal", "secret discount",
)

DISCLOSURE_KEYWORDS = ("affiliate", "commission", "no extra cost")

_DOWNSIDE_KEYWORDS = (
    "downside", "drawback", "weakness", "complaint", "disappointing",
    "worse", "mediocre", "struggles", "falls short", "however",
    "unfortunately", "trade-off", "tradeoff", "con:", "not great",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_words(text: str) -> int:
    cleaned = re.sub(r"\[.*?\]", "", text)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    return len(cleaned.split())


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _find_phrases(text: str, phrases) -> list[str]:
    lower = text.lower()
    return [p for p in phrases if p in lower]


# ---------------------------------------------------------------------------
# Brief generation
# ---------------------------------------------------------------------------


@dataclass
class BriefData:
    """Inputs collected for the brief."""
    niche: str
    primary_keyword: str
    secondary_keywords: list[str]
    products: list[dict]
    sources_used: list[str]


def _derive_keywords(niche: str, seo: dict) -> tuple[str, list[str]]:
    """Get primary + secondary keywords from seo.json or derive from niche."""
    primary = seo.get("primary_keyword", "").strip()
    secondary = seo.get("secondary_keywords", [])

    if not primary:
        primary = f"best {niche}"

    if not secondary:
        secondary = [
            f"top 5 {niche}",
            f"{niche} review",
            f"best {niche} to buy",
        ]

    return primary, secondary


def _build_hook_suggestions(niche: str, products: list[dict]) -> list[str]:
    """Generate 3 hook variants from the data."""
    # Collect a notable claim for hooks
    top_product = ""
    notable_claim = ""
    for p in products:
        if p.get("rank") == 1:
            top_product = p.get("name", "")
        for ev in p.get("evidence", []):
            for reason in ev.get("reasons", []):
                if len(reason) > 20 and not notable_claim:
                    notable_claim = reason

    hooks = [
        (
            f"Problem hook: \"You searched '{niche}' and got 10,000 results. "
            f"Half the reviews are fake. Here are the 5 that actually hold up "
            f"under expert testing.\""
        ),
        (
            f"Contrarian hook: \"Most '{niche}' recommendation videos just "
            f"read Amazon listings back to you. I went through Wirecutter, "
            f"RTINGS, and PCMag so you don't have to.\""
        ),
    ]

    if notable_claim:
        hooks.append(
            f"Stat hook: Lead with a specific finding — \"{notable_claim}\" "
            f"— then explain why it matters."
        )
    else:
        hooks.append(
            f"Question hook: \"What if the {niche.split()[0]} you're about to buy "
            f"is the one that every expert reviewer says to skip?\""
        )

    return hooks


def _build_product_section(p: dict) -> str:
    """Build the brief section for one product."""
    rank = p.get("rank", 0)
    name = p.get("name", "Unknown")
    positioning = p.get("positioning", "")
    price = p.get("price", "")
    rating = p.get("rating", "")
    benefits = p.get("benefits", [])
    downside = p.get("downside", "")
    evidence = p.get("evidence", [])

    lines = [f"### Product #{rank}: {name}"]

    if positioning:
        lines.append(f"Positioning: {positioning}")
    if price:
        lines.append(f"Price: {price}")
    if rating:
        lines.append(f"Amazon rating: {rating}")

    lines.append("")
    lines.append("Benefits (from expert reviews):")
    if benefits:
        for b in benefits:
            lines.append(f"  - {b}")
    else:
        lines.append("  - (no benefits extracted — check evidence below)")

    lines.append("")
    if downside:
        lines.append(f"Honest downside: {downside}")
    else:
        lines.append("Honest downside: (none extracted — find one in evidence or note 'no major complaints')")

    if evidence:
        lines.append("")
        lines.append("Source evidence (cite naturally when impactful):")
        for ev in evidence:
            src = ev.get("source", "Unknown")
            label = ev.get("label", "")
            label_str = f" [{label}]" if label else ""
            reasons = ev.get("reasons", [])
            lines.append(f"  {src}{label_str}:")
            for r in reasons[:4]:
                lines.append(f"    - {r}")

    lines.append("")
    lines.append(f"Word target: 200-300 words")
    lines.append(f"Must include: positioning, 2-3 benefits, who it's for, honest downside, transition to next")

    return "\n".join(lines)


def _build_signature_suggestion(niche: str) -> str:
    """One signature moment suggestion."""
    return (
        f"Signature moment suggestion (pick one approach):\n"
        f"  - Reality check: \"Remember, the most expensive {niche.split()[0]} "
        f"isn't always the best one for you.\"\n"
        f"  - Micro comparison: Compare two products on a specific metric the "
        f"audience cares about (e.g., battery life, comfort, noise cancellation).\n"
        f"  - Micro humor: A one-liner that shows you actually use these products. "
        f"Keep it natural, not forced."
    )


def generate_brief(
    niche: str,
    products_data: dict,
    seo_data: dict,
    channel_style: str = "",
) -> str:
    """Build the manual_brief.txt content from structured data.

    No API calls. Pure text assembly.
    """
    products = products_data.get("products", [])
    sources_used = products_data.get("sources_used", [])
    primary_kw, secondary_kws = _derive_keywords(niche, seo_data)

    lines: list[str] = []

    # Header
    lines.append(f"{'=' * 60}")
    lines.append(f"SCRIPT BRIEF: {niche.upper()}")
    lines.append(f"{'=' * 60}")
    lines.append("")

    # SEO keywords
    lines.append("## Keywords")
    lines.append(f"Primary: {primary_kw}")
    lines.append(f"Secondary: {', '.join(secondary_kws)}")
    lines.append("")

    # Target
    lines.append("## Target")
    lines.append(f"Word count: {SCRIPT_WORD_MIN}-{SCRIPT_WORD_MAX}")
    lines.append(f"Duration: {SCRIPT_WORD_MIN // SPEAKING_WPM}-{SCRIPT_WORD_MAX // SPEAKING_WPM} minutes at {SPEAKING_WPM} WPM")
    lines.append("")

    # Tone
    lines.append("## Tone guidance")
    lines.append("- Energetic but trustworthy. You're the friend who did the research.")
    lines.append("- Confident, not salesy. State facts, don't hype.")
    lines.append("- Mix short punchy lines with longer explanations.")
    lines.append("- Attribute expert sources naturally when making strong claims.")
    lines.append("- Every product gets an honest downside. This builds trust.")
    lines.append("")

    # Channel style (from channel/channel_style.md if provided)
    if channel_style:
        lines.append("## Channel Style")
        lines.append(channel_style.strip())
        lines.append("")

    # Hook suggestions
    lines.append("## Hook suggestions (pick one or remix)")
    lines.append(f"Target: 100-150 words")
    lines.append("")
    for i, hook in enumerate(_build_hook_suggestions(niche, products), 1):
        lines.append(f"{i}. {hook}")
        lines.append("")

    # Structured outline
    lines.append("## Structured outline")
    lines.append("")
    lines.append("[HOOK] (100-150 words)")
    lines.append("  Open with problem or tension. NOT 'In today's video'.")
    lines.append("")
    lines.append("[AVATAR_INTRO] (3-6 seconds)")
    lines.append("  Brief channel intro. 1-2 sentences max.")
    lines.append("")
    lines.append("[CREDIBILITY] (weave into hook or first product)")
    lines.append(f"  Sources used: {', '.join(sources_used) if sources_used else 'Wirecutter, RTINGS, PCMag'}")
    lines.append("  Mention you reviewed expert sources. Don't list them like a bibliography.")
    lines.append("")

    # Products 5 to 1
    sorted_products = sorted(products, key=lambda p: -p.get("rank", 0))
    for p in sorted_products:
        rank = p.get("rank", 0)
        lines.append(f"{'—' * 50}")
        lines.append(_build_product_section(p))
        lines.append("")
        if rank == 3:
            lines.append("[RETENTION_RESET] (50-80 words)")
            lines.append("  Pattern interrupt. Break the rhythm.")
            lines.append("  Suggestions:")
            lines.append("    - Ask the audience a question")
            lines.append("    - Share a surprising stat")
            lines.append("    - Quick comparison between two products already covered")
            lines.append("")

    # Signature moment
    lines.append(f"{'—' * 50}")
    lines.append("")
    lines.append("## Signature moment")
    lines.append(_build_signature_suggestion(niche))
    lines.append("")

    # Pattern interrupt suggestions
    lines.append("## Pattern interrupt ideas")
    lines.append("- \"Quick question — have you ever returned a product because of one small thing?\"")
    lines.append("- \"Before we get to number 2, here's something most reviews don't mention...\"")
    lines.append("- Direct comparison: \"Product X does [thing] better, but Product Y wins on [other thing].\"")
    lines.append("")

    # Conclusion
    lines.append("[CONCLUSION]")
    lines.append("  - Recap: quick 1-line summary of each pick and who it's for")
    lines.append("  - CTA: \"Links in the description\"")
    lines.append("  - FTC affiliate disclosure (MANDATORY)")
    lines.append("")

    # FTC disclosure
    lines.append("## FTC affiliate disclosure (MANDATORY — include word-for-word or equivalent)")
    lines.append("")
    lines.append("\"Links in the description may be affiliate links, which means I may")
    lines.append("earn a small commission at no extra cost to you. This helps support")
    lines.append("the channel.\"")
    lines.append("")
    lines.append("Must contain the words: affiliate, commission, no extra cost")
    lines.append("")

    # Source attribution notes
    lines.append("## Source attribution notes")
    lines.append("- Cite sources naturally: \"According to Wirecutter...\" or \"RTINGS measured...\"")
    lines.append("- Don't cite every claim. Cite when the source adds credibility.")
    lines.append("- Never say \"studies show\" or \"experts agree\" without naming the source.")
    lines.append("- Never invent specs, measurements, or test results.")
    lines.append("")

    # Words to avoid
    lines.append("## Words to avoid")
    lines.append(f"Hype: {', '.join(sorted(HYPE_WORDS))}")
    lines.append(f"AI cliches: {', '.join(AI_CLICHES[:6])}...")
    lines.append("")

    # File instructions
    lines.append("## Next steps")
    lines.append("1. Write your script in: script/script_raw.txt")
    lines.append("2. Use [SECTION] markers: [HOOK], [AVATAR_INTRO], [PRODUCT_5]...[PRODUCT_1], [RETENTION_RESET], [CONCLUSION]")
    lines.append("3. Run review: python3 tools/pipeline.py script-review --video-id <id>")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Script review (no API calls)
# ---------------------------------------------------------------------------


@dataclass
class ReviewIssue:
    """One issue found during script review."""
    severity: str  # "error" or "warning"
    section: str   # which section or "global"
    message: str


@dataclass
class ReviewResult:
    """Full review output."""
    word_count: int = 0
    estimated_duration_min: float = 0.0
    issues: list[ReviewIssue] = field(default_factory=list)
    section_word_counts: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == "warning"]


def _parse_sections(text: str) -> dict[str, str]:
    """Parse [SECTION] markers into a dict of section_name -> content."""
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
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
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


def _check_claim_against_evidence(
    script_text: str, products_data: dict,
) -> list[ReviewIssue]:
    """Check if strong claims in the script are backed by product evidence.

    Looks for specific numbers, measurements, and attributions.
    Flags claims that look like invented specs.
    """
    issues: list[ReviewIssue] = []
    products = products_data.get("products", [])

    # Collect all known facts from evidence
    known_facts: set[str] = set()
    known_numbers: set[str] = set()
    for p in products:
        name = p.get("name", "").lower()
        for ev in p.get("evidence", []):
            for reason in ev.get("reasons", []):
                known_facts.add(reason.lower()[:60])
                # Extract numbers from evidence
                for num in re.findall(r'\d+\.?\d*', reason):
                    known_numbers.add(num)
        for claim in p.get("key_claims", []):
            known_facts.add(claim.lower()[:60])
            for num in re.findall(r'\d+\.?\d*', claim):
                known_numbers.add(num)

    # Look for specific measurement claims in the script
    # Pattern: number + unit that looks like a spec
    spec_pattern = re.compile(
        r'(\d+\.?\d*)\s*(dB|decibel|hours?|mAh|mm|Hz|ms|watts?|W|grams?|g|percent|%)',
        re.IGNORECASE,
    )
    for match in spec_pattern.finditer(script_text):
        number = match.group(1)
        if number not in known_numbers:
            context = script_text[max(0, match.start() - 40):match.end() + 40].strip()
            context = re.sub(r'\s+', ' ', context)
            issues.append(ReviewIssue(
                severity="warning",
                section="global",
                message=f"Spec '{match.group()}' not found in evidence. Verify: ...{context}...",
            ))

    return issues


def review_script(
    script_text: str,
    products_data: dict,
) -> ReviewResult:
    """Review a script_raw.txt against products.json evidence.

    No API calls. Pure validation logic.
    """
    result = ReviewResult()
    full_text = script_text

    # Word count
    result.word_count = _count_words(full_text)
    result.estimated_duration_min = round(result.word_count / SPEAKING_WPM, 1)

    if result.word_count < SCRIPT_WORD_MIN:
        result.issues.append(ReviewIssue(
            "error", "global",
            f"Too short: {result.word_count} words (min {SCRIPT_WORD_MIN})",
        ))
    if result.word_count > SCRIPT_WORD_MAX:
        result.issues.append(ReviewIssue(
            "error", "global",
            f"Too long: {result.word_count} words (max {SCRIPT_WORD_MAX})",
        ))

    # Parse sections
    sections = _parse_sections(full_text)
    result.section_word_counts = {k: _count_words(v) for k, v in sections.items()}

    if not sections:
        result.issues.append(ReviewIssue(
            "error", "global",
            "No [SECTION] markers found. Use [HOOK], [PRODUCT_5], etc.",
        ))
        return result

    # Section word counts
    expected_sections = [
        "hook", "avatar_intro", "product_5", "product_4", "product_3",
        "retention_reset", "product_2", "product_1", "conclusion",
    ]
    for sec in expected_sections:
        if sec not in sections:
            result.issues.append(ReviewIssue(
                "error", "global",
                f"Missing section: [{sec.upper()}]",
            ))

    hook_wc = result.section_word_counts.get("hook", 0)
    if hook_wc < 100:
        result.issues.append(ReviewIssue("error", "hook", f"Hook too short: {hook_wc} words (min 100)"))
    if hook_wc > 150:
        result.issues.append(ReviewIssue("warning", "hook", f"Hook long: {hook_wc} words (target 100-150)"))

    for rank in [5, 4, 3, 2, 1]:
        key = f"product_{rank}"
        wc = result.section_word_counts.get(key, 0)
        if wc < 200:
            result.issues.append(ReviewIssue("error", key, f"Product #{rank} too short: {wc} words (min 200)"))
        if wc > 300:
            result.issues.append(ReviewIssue("warning", key, f"Product #{rank} long: {wc} words (target 200-300)"))

    rr_wc = result.section_word_counts.get("retention_reset", 0)
    if rr_wc < 50:
        result.issues.append(ReviewIssue("error", "retention_reset", f"Retention reset too short: {rr_wc} words (min 50)"))
    if rr_wc > 80:
        result.issues.append(ReviewIssue("warning", "retention_reset", f"Retention reset long: {rr_wc} words (target 50-80)"))

    # Downside check per product
    downside_markers = (
        "keep in mind", "downside", "the catch", "not perfect",
        "one drawback", "one con", "minor issue", "only complaint",
        "worth noting", "trade-off", "trade off", "on the flip side",
        "however", "that said",
    )
    for rank in [5, 4, 3, 2, 1]:
        key = f"product_{rank}"
        content = sections.get(key, "")
        if content and not any(m in content.lower() for m in downside_markers):
            result.issues.append(ReviewIssue(
                "error", key,
                f"Product #{rank}: no honest downside found. Every product needs one.",
            ))

    # Disclosure check
    conclusion = sections.get("conclusion", "")
    for kw in DISCLOSURE_KEYWORDS:
        if kw not in conclusion.lower():
            result.issues.append(ReviewIssue(
                "error", "conclusion",
                f"Conclusion missing disclosure keyword: '{kw}'",
            ))

    # Hype words
    hype_found = _find_phrases(full_text, HYPE_WORDS)
    if hype_found:
        result.issues.append(ReviewIssue(
            "error", "global",
            f"Hype words found (remove): {', '.join(hype_found)}",
        ))

    # AI cliches
    cliches_found = _find_phrases(full_text, AI_CLICHES)
    if cliches_found:
        result.issues.append(ReviewIssue(
            "warning", "global",
            f"AI cliches found (consider removing): {', '.join(cliches_found)}",
        ))

    # Compliance violations
    violations = _find_phrases(full_text, COMPLIANCE_VIOLATIONS)
    if violations:
        result.issues.append(ReviewIssue(
            "error", "global",
            f"Compliance violations (remove): {', '.join(violations)}",
        ))

    # Claim verification against evidence
    claim_issues = _check_claim_against_evidence(full_text, products_data)
    result.issues.extend(claim_issues)

    return result


def format_review_notes(result: ReviewResult, video_id: str) -> str:
    """Format ReviewResult into script_review_notes.md content."""
    lines: list[str] = []
    lines.append(f"# Script Review: {video_id}")
    lines.append("")
    lines.append(f"Word count: {result.word_count} (target: {SCRIPT_WORD_MIN}-{SCRIPT_WORD_MAX})")
    lines.append(f"Estimated duration: {result.estimated_duration_min} min")
    lines.append(f"Verdict: {'PASS' if result.passed else 'NEEDS REVISION'}")
    lines.append("")

    # Section breakdown
    if result.section_word_counts:
        lines.append("## Section word counts")
        for sec, wc in result.section_word_counts.items():
            lines.append(f"  {sec}: {wc}")
        lines.append("")

    # Errors
    errors = result.errors
    if errors:
        lines.append(f"## Errors ({len(errors)}) — must fix")
        for issue in errors:
            lines.append(f"- [{issue.section}] {issue.message}")
        lines.append("")

    # Warnings
    warnings = result.warnings
    if warnings:
        lines.append(f"## Warnings ({len(warnings)}) — consider fixing")
        for issue in warnings:
            lines.append(f"- [{issue.section}] {issue.message}")
        lines.append("")

    if result.passed:
        lines.append("## Next steps")
        lines.append("Script passes validation. Copy to script.txt or run TTS:")
        lines.append(f"  cp script/script_raw.txt script/script.txt")
        lines.append(f"  python3 tools/pipeline.py tts --video-id {video_id}")
    else:
        lines.append("## Next steps")
        lines.append("Fix the errors above, then re-run review:")
        lines.append(f"  python3 tools/pipeline.py script-review --video-id {video_id}")

    lines.append("")
    return "\n".join(lines)


def apply_light_fixes(script_text: str) -> tuple[str, list[str]]:
    """Apply safe, non-creative fixes to script text.

    Only touches things that are clearly wrong — never rewrites content.
    Returns (fixed_text, list_of_changes_made).
    """
    text = script_text
    changes: list[str] = []

    # Fix double spaces
    before = text
    text = re.sub(r'  +', ' ', text)
    if text != before:
        changes.append("Collapsed double spaces")

    # Fix trailing whitespace on lines
    before = text
    text = "\n".join(line.rstrip() for line in text.splitlines())
    if text != before:
        changes.append("Removed trailing whitespace")

    # Remove AI cliches (case-insensitive, whole phrase)
    for cliche in AI_CLICHES:
        pattern = re.compile(re.escape(cliche), re.IGNORECASE)
        if pattern.search(text):
            text = pattern.sub("", text)
            changes.append(f"Removed AI cliche: '{cliche}'")

    # Clean up empty lines left by removals (max 2 consecutive)
    before = text
    text = re.sub(r'\n{3,}', '\n\n', text)
    if text != before:
        changes.append("Collapsed excess blank lines")

    return text, changes
