#!/usr/bin/env python3
"""
Script Quality Gate — Automated checker for anti-AI, conversion structure, and rhythm.

Usage (standalone):
    python3 tools/script_quality_gate.py path/to/script.md
    python3 tools/script_quality_gate.py script_a.md script_b.md --max-violations 3

Usage (imported by pipeline):
    from script_quality_gate import evaluate_script_quality, write_quality_report
    result = evaluate_script_quality(script_text, max_violations=3)

Checks:
  1. Anti-AI phrase blacklist (from SOUL.md)
  2. AI structural patterns (humanizer-derived)
  3. Sentence rhythm (monotone detection)
  4. Conversion structure (problem/critique/who-should per product)
  5. Short punch presence (<=4 words per product)
  6. Varied opener check
  7. Contraction usage
  8. Em dash overuse
  9. Rule of three overuse
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOUL_FILE = PROJECT_ROOT / "agents" / "scriptwriter" / "SOUL.md"

# ---------------------------------------------------------------------------
# 1. Anti-AI phrase blacklist
# ---------------------------------------------------------------------------

DEFAULT_BANNED_PHRASES = [
    "without further ado", "let's dive in", "let's dive right in",
    "it's worth noting", "it's worth mentioning", "in today's video",
    "whether you're a", "at the end of the day", "takes it to the next level",
    "boasts", "features an impressive", "offers a seamless",
    "elevate your experience", "look no further", "game-changer", "game changer",
    "in the realm of", "when it comes to", "a testament to",
    "if you're in the market for", "packed with features", "sleek design",
    "bang for your buck",
    # Humanizer additions (Wikipedia AI Cleanup patterns)
    "serves as a testament", "stands as a testament", "is a testament",
    "it's not just", "it's not merely",  # negative parallelism
    "I hope this helps", "let me know if",  # chatbot artifacts
    "the future looks bright",  # generic positive conclusion
    "exciting times lie ahead",
    "in order to achieve",
    "due to the fact that",
    "at this point in time",
    "it is important to note",
    "nestled in", "in the heart of",  # promotional
    "groundbreaking", "breathtaking", "must-visit", "stunning",
]

# AI vocabulary words (high frequency in AI text, from humanizer)
AI_VOCABULARY = [
    "delve", "tapestry", "interplay", "intricacies", "pivotal",
    "fostering", "garner", "underscore", "vibrant", "landscape",
    "showcasing", "exemplifies", "enduring",
]

# Structural patterns
STRUCTURAL_PATTERNS = [
    ("template_opening", re.compile(
        r"^\s*this\s+.{0,120}\b(boasts|features|offers|delivers)\b", re.I)),
    ("ranking_transition", re.compile(
        r"\bcoming in at number\s*#?\d+\b", re.I)),
    ("next_up", re.compile(r"\bnext up\b", re.I)),
    ("moving_on", re.compile(r"\bmoving on to\b", re.I)),
    ("copula_avoidance", re.compile(
        r"\b(serves as|stands as|marks) (a|the|an)\b", re.I)),
]


def _normalize(text: str) -> str:
    low = (text or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    low = low.replace("'", "'").replace("-", " ")
    return re.sub(r"\s+", " ", low).strip()


def load_banned_phrases() -> List[str]:
    phrases = list(DEFAULT_BANNED_PHRASES)
    if not SOUL_FILE.exists():
        return phrases
    try:
        lines = SOUL_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return phrases

    in_block = False
    for raw in lines:
        line = raw.strip()
        if line.lower().startswith("### frases proibidas"):
            in_block = True
            continue
        if in_block and line.startswith("### "):
            break
        if not in_block or not line.startswith("- "):
            continue
        item = re.sub(r"\s*\(.*?\)\s*$", "", line[2:].strip()).strip('`"\'  ')
        if not item:
            continue
        if "/" in item and "http" not in item.lower():
            for v in item.split("/"):
                v = v.strip().strip('`"\'  ')
                if v:
                    phrases.append(v)
        else:
            phrases.append(item)

    # Deduplicate
    seen = set()
    out = []
    for p in phrases:
        key = _normalize(p)
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# 2. Violation detection
# ---------------------------------------------------------------------------

def find_phrase_violations(text: str, banned: List[str]) -> List[Dict]:
    violations = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        norm = _normalize(line)
        for phrase in banned:
            key = _normalize(phrase)
            if key and key in norm:
                violations.append({
                    "line": i, "type": "banned_phrase",
                    "rule": phrase, "excerpt": line[:200],
                    "severity": "HIGH",
                })
    return violations


def find_ai_vocabulary(text: str) -> List[Dict]:
    violations = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        for word in AI_VOCABULARY:
            if re.search(rf"\b{re.escape(word)}\b", low):
                violations.append({
                    "line": i, "type": "ai_vocabulary",
                    "rule": word, "excerpt": line[:200],
                    "severity": "MEDIUM",
                })
    return violations


def find_structural_violations(text: str) -> List[Dict]:
    violations = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        for name, pattern in STRUCTURAL_PATTERNS:
            if pattern.search(line):
                violations.append({
                    "line": i, "type": "structural_pattern",
                    "rule": name, "excerpt": line[:200],
                    "severity": "HIGH",
                })
    return violations


# ---------------------------------------------------------------------------
# 3. Sentence rhythm analysis
# ---------------------------------------------------------------------------

def _sentence_lengths(text: str) -> List[int]:
    """Split into sentences and return word counts."""
    # Remove markdown headers
    clean = re.sub(r"^#+\s+.*$", "", text, flags=re.MULTILINE)
    # Split on sentence-ending punctuation
    sentences = re.split(r"[.!?]+", clean)
    lengths = []
    for s in sentences:
        words = s.split()
        if len(words) >= 2:  # skip fragments
            lengths.append(len(words))
    return lengths


def check_rhythm(text: str) -> List[Dict]:
    """Flag monotone stretches: 5+ sentences within ±3 words of each other."""
    violations = []
    lengths = _sentence_lengths(text)
    window = 5
    for i in range(len(lengths) - window + 1):
        chunk = lengths[i:i + window]
        avg = sum(chunk) / len(chunk)
        if all(abs(l - avg) <= 3 for l in chunk):
            violations.append({
                "line": 0, "type": "rhythm_monotone",
                "rule": f"5 consecutive sentences ~{int(avg)} words each ({chunk})",
                "excerpt": "", "severity": "MEDIUM",
            })
            break  # one flag is enough
    return violations


# ---------------------------------------------------------------------------
# 4. Conversion structure check
# ---------------------------------------------------------------------------

def _split_product_sections(text: str) -> List[Tuple[str, str]]:
    """Split script into product sections. Returns [(header, body), ...]
    Only considers ## level headers (product sections), not ### (sub-sections).
    """
    # Match ## headers that look like product entries (#5, #4, etc.)
    pattern = re.compile(r"^##\s+.+$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        header = m.group().strip()
        # Only include product sections (skip intro/outro/recap/comparison/buyer)
        skip_kw = ["recap", "cta", "intro", "closing", "final", "hook",
                    "comparison", "buyer", "mapping", "disclosure", "context"]
        if any(kw in header.lower() for kw in skip_kw):
            continue
        if len(body) > 50:  # substantive section
            sections.append((header, body))
    return sections


CRITIQUE_MARKERS = [
    r"\bbut\b", r"\bhowever\b", r"\bdownside\b", r"\blimitation\b",
    r"\bdrawback\b", r"\bweak\b", r"\bnot (great|ideal|perfect|the best)\b",
    r"\bwish\b", r"\bmiss(ing|es)?\b", r"\black(s|ing)?\b",
    r"\bcatch\b", r"\bproblem\b", r"\bissue\b", r"\bcaveat\b",
    r"\bheavier\b", r"\bbulk(y|ier)\b", r"\bnois(y|ier)\b",
    r"\bcheap(er|ly)?\b.*\bfeel\b",
]

WHO_SHOULD_MARKERS = [
    r"\bif you\b", r"\bfor (anyone|someone|people|those) who\b",
    r"\b(best|great|ideal|perfect) for\b", r"\b(runners|gamers|students|travelers)\b",
    r"\bwho (should|want|need|like)\b",
]

WHO_SHOULDNT_MARKERS = [
    r"\bnot (for|ideal|great|the best)\b",
    r"\bif you don.?t\b", r"\bskip (this|it)\b",
    r"\bavoid\b", r"\bwon.?t (work|suit|fit)\b",
    r"\bshouldn.?t\b",
]

SHORT_PUNCH_MAX_WORDS = 4


def check_conversion_structure(text: str) -> List[Dict]:
    """Check each product section for required conversion elements."""
    sections = _split_product_sections(text)
    violations = []

    if not sections:
        violations.append({
            "line": 0, "type": "structure_missing",
            "rule": "no_product_sections_found",
            "excerpt": "Could not identify product sections in script",
            "severity": "HIGH",
        })
        return violations

    openers = []
    for header, body in sections:
        low = body.lower()
        first_line = body.split("\n")[0].strip()
        openers.append(first_line[:60])

        # Check critique/limitation
        has_critique = any(re.search(p, low) for p in CRITIQUE_MARKERS)
        if not has_critique:
            violations.append({
                "line": 0, "type": "missing_critique",
                "rule": f"No honest limitation found in section: {header[:60]}",
                "excerpt": header, "severity": "HIGH",
            })

        # Check who-should-buy
        has_who = any(re.search(p, low) for p in WHO_SHOULD_MARKERS)
        if not has_who:
            violations.append({
                "line": 0, "type": "missing_buyer_profile",
                "rule": f"No 'who should buy' in section: {header[:60]}",
                "excerpt": header, "severity": "MEDIUM",
            })

        # Check who-should-NOT-buy
        has_who_not = any(re.search(p, low) for p in WHO_SHOULDNT_MARKERS)
        if not has_who_not:
            violations.append({
                "line": 0, "type": "missing_anti_buyer",
                "rule": f"No 'who should NOT buy' in section: {header[:60]}",
                "excerpt": header, "severity": "LOW",
            })

        # Check short punch (<=4 words)
        sentences = re.split(r"[.!?]+", body)
        has_punch = any(
            1 <= len(s.split()) <= SHORT_PUNCH_MAX_WORDS
            for s in sentences if s.strip()
        )
        if not has_punch:
            violations.append({
                "line": 0, "type": "missing_short_punch",
                "rule": f"No short punch (<=4 words) in section: {header[:60]}",
                "excerpt": header, "severity": "LOW",
            })

    # Check varied openers (flag if >50% start similarly)
    if len(openers) >= 3:
        normalized_openers = [_normalize(o)[:30] for o in openers]
        # Check for same starting pattern
        starts = [o.split()[:3] if o.split() else [] for o in normalized_openers]
        if len(set(tuple(s) for s in starts)) <= len(starts) // 2:
            violations.append({
                "line": 0, "type": "repetitive_openers",
                "rule": "Product sections open with similar patterns",
                "excerpt": " | ".join(openers[:3]),
                "severity": "MEDIUM",
            })

    return violations


# ---------------------------------------------------------------------------
# 5. Style checks (humanizer-derived)
# ---------------------------------------------------------------------------

def check_em_dash_overuse(text: str) -> List[Dict]:
    """Flag if em dashes appear more than 3 times."""
    count = text.count("—") + text.count("--")
    if count > 3:
        return [{
            "line": 0, "type": "em_dash_overuse",
            "rule": f"Em dashes used {count} times (max 3 recommended)",
            "excerpt": "", "severity": "LOW",
        }]
    return []


def check_rule_of_three(text: str) -> List[Dict]:
    """Flag triple-adjective or triple-noun patterns."""
    violations = []
    pattern = re.compile(
        r"\b(\w+),\s+(\w+),\s+and\s+(\w+)\b", re.I
    )
    matches = list(pattern.finditer(text))
    if len(matches) > 2:
        violations.append({
            "line": 0, "type": "rule_of_three_overuse",
            "rule": f"'X, Y, and Z' pattern used {len(matches)} times (limit 2)",
            "excerpt": matches[0].group()[:100],
            "severity": "LOW",
        })
    return violations


def check_contraction_usage(text: str) -> List[Dict]:
    """Flag if contractions are underused (suggests formal/AI tone)."""
    # Count potential contraction sites vs actual contractions
    formal = len(re.findall(r"\b(it is|do not|you will|that is|does not|can not|will not|is not|are not|would not|could not|should not)\b", text, re.I))
    contracted = len(re.findall(r"\b(it's|don't|you'll|that's|doesn't|can't|won't|isn't|aren't|wouldn't|couldn't|shouldn't)\b", text, re.I))

    total = formal + contracted
    if total > 0 and formal / total > 0.5:
        return [{
            "line": 0, "type": "low_contraction_rate",
            "rule": f"Only {contracted}/{total} potential contractions used ({int(contracted/total*100)}%). Use contractions for natural tone.",
            "excerpt": "", "severity": "MEDIUM",
        }]
    return []


# ---------------------------------------------------------------------------
# 6. Claim source check
# ---------------------------------------------------------------------------

STRONG_CLAIM_PATTERNS = [
    r"\bguarantee(?:d|s)?\b",
    r"\bperfect\b",
    r"\bbest(?:\s+ever)?\b",
    r"\bno\.?\s*1\b",
    r"\balways\b",
    r"\bnever\b",
    r"\bultimate\b",
    r"\bproven\b",
    r"\bclinically\b",
    r"\bscientifically\b",
]

SOURCE_MARKERS = [
    r"http", r"amazon\.com", r"according to",
    r"\bstudy\b", r"\btest(ed|s|ing)?\b",
    r"\brating\b", r"\breviews?\b",
    r"\brtings\b", r"\bwirecutter\b",
]


def check_claims_without_sources(text: str) -> List[Dict]:
    """Flag strong claims that lack nearby source references."""
    violations = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if not any(re.search(p, low) for p in STRONG_CLAIM_PATTERNS):
            continue
        # Check ±2 lines for source markers
        context = " ".join(
            lines[max(0, i - 2):min(len(lines), i + 3)]
        ).lower()
        has_source = any(re.search(p, context) for p in SOURCE_MARKERS)
        if not has_source:
            violations.append({
                "line": i + 1, "type": "claim_without_source",
                "rule": "Strong claim without nearby evidence/source",
                "excerpt": line.strip()[:200],
                "severity": "MEDIUM",
            })
    # Limit to most important
    return violations[:10]


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def evaluate_script_quality(
    script_text: str,
    max_violations: int = 3,
    variation_plan: Optional[Dict] = None,
    recent_scripts: Optional[List[Dict]] = None,
) -> Dict:
    """Run all quality checks. Returns structured result with pass/fail.

    When variation_plan is provided, also runs variation quality checks
    from variation_quality_checks module.
    """
    banned = load_banned_phrases()

    checks = {
        "phrase_violations": find_phrase_violations(script_text, banned),
        "ai_vocabulary": find_ai_vocabulary(script_text),
        "structural_patterns": find_structural_violations(script_text),
        "rhythm": check_rhythm(script_text),
        "conversion_structure": check_conversion_structure(script_text),
        "em_dash": check_em_dash_overuse(script_text),
        "rule_of_three": check_rule_of_three(script_text),
        "contractions": check_contraction_usage(script_text),
        "claims_without_sources": check_claims_without_sources(script_text),
    }

    # Variation quality checks (when variation_plan is available)
    if variation_plan:
        try:
            from variation_quality_checks import evaluate_variation_quality
            # Build a minimal script_data dict for the variation checker
            script_data = {"segments": [], "structure": []}
            try:
                script_data = json.loads(script_text)
            except (json.JSONDecodeError, ValueError):
                pass
            variation_violations = evaluate_variation_quality(
                script_data, variation_plan, recent_scripts or [],
            )
            checks["variation_quality"] = variation_violations
        except ImportError:
            pass

    # Score: HIGH = 3, MEDIUM = 1, LOW = 0.5
    severity_weights = {"HIGH": 3, "MEDIUM": 1, "LOW": 0.5}
    all_violations = []
    total_score = 0
    for check_name, violations in checks.items():
        for v in violations:
            v["check"] = check_name
            all_violations.append(v)
            total_score += severity_weights.get(v.get("severity", "LOW"), 0.5)

    high_count = sum(1 for v in all_violations if v.get("severity") == "HIGH")
    passed = high_count <= max_violations

    # Deduplicate by (type, rule)
    seen = set()
    unique_rules = []
    for v in all_violations:
        key = (v["type"], v["rule"])
        if key not in seen:
            seen.add(key)
            unique_rules.append(v["rule"])

    return {
        "pass": passed,
        "score": round(total_score, 1),
        "max_violations": max_violations,
        "high_count": high_count,
        "medium_count": sum(1 for v in all_violations if v.get("severity") == "MEDIUM"),
        "low_count": sum(1 for v in all_violations if v.get("severity") == "LOW"),
        "total_violations": len(all_violations),
        "unique_rules": unique_rules,
        "checks": {k: len(v) for k, v in checks.items()},
        "violations": all_violations,
    }


def write_quality_report(result: Dict, script_path: str = "") -> str:
    """Generate markdown report."""
    status = "PASS" if result["pass"] else "FAIL"
    lines = [
        "# Script Quality Gate Report",
        "",
        f"- **Status**: `{status}`",
        f"- **Score**: `{result['score']}` (lower is better)",
        f"- **HIGH violations**: `{result['high_count']}` (max allowed: `{result['max_violations']}`)",
        f"- **MEDIUM violations**: `{result['medium_count']}`",
        f"- **LOW violations**: `{result['low_count']}`",
    ]
    if script_path:
        lines.append(f"- **Script**: `{script_path}`")
    lines.append("")

    if not result["pass"]:
        lines.extend([
            "## BLOCKER",
            "Rewrite script before approving Gate 1.",
            "Focus on HIGH severity violations first.",
            "",
        ])

    # Group by check
    by_check = {}
    for v in result["violations"]:
        check = v.get("check", "unknown")
        by_check.setdefault(check, []).append(v)

    for check_name, violations in by_check.items():
        lines.append(f"## {check_name.replace('_', ' ').title()} ({len(violations)})")
        for v in violations[:20]:
            sev = v.get("severity", "")
            rule = v.get("rule", "")
            excerpt = v.get("excerpt", "")
            line_num = v.get("line", 0)
            loc = f"line {line_num}" if line_num else ""
            lines.append(f"- [{sev}] {loc}: `{rule}`")
            if excerpt:
                lines.append(f"  > {excerpt[:150]}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Script Quality Gate — anti-AI + conversion checker")
    p.add_argument("scripts", nargs="+", help="Script file(s) to check")
    p.add_argument("--max-violations", type=int, default=3, help="Max HIGH violations before FAIL")
    p.add_argument("--json", action="store_true", help="Output JSON instead of markdown")
    args = p.parse_args()

    exit_code = 0
    for path in args.scripts:
        text = Path(path).read_text(encoding="utf-8")
        result = evaluate_script_quality(text, args.max_violations)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            report = write_quality_report(result, path)
            print(report)

        if not result["pass"]:
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
