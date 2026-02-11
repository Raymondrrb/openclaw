#!/usr/bin/env python3
"""CLI entry point for video script generation workflow.

Amazon Associates product ranking channel (Top 5 format).

Usage:
    # Generate workflow prompts from product JSON
    python3 tools/script_gen.py --products products.json --niche "your niche"

    # Validate an existing script
    python3 tools/script_gen.py --validate script.txt

    # Generate prompts only (step 1-3)
    python3 tools/script_gen.py --products products.json --niche "your niche" --step extraction
    python3 tools/script_gen.py --products products.json --niche "your niche" --step draft --notes extraction.txt
    python3 tools/script_gen.py --step refinement --draft draft.txt --charismatic micro_humor

Product JSON format:
[
  {"rank": 5, "name": "Product A", "positioning": "budget pick", "benefits": ["benefit 1"], "downside": "minor issue", "amazon_url": "..."},
  {"rank": 4, "name": "Product B", ...},
  ...
]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.script_schema import (
    CHARISMATIC_TYPES,
    SECTION_ORDER,
    ProductEntry,
    ScriptOutput,
    ScriptRequest,
    ScriptSection,
    build_draft_prompt,
    build_extraction_prompt,
    build_refinement_prompt,
    build_validation_prompt,
    validate_request,
    validate_script,
)


def _load_products(path: str) -> list[ProductEntry]:
    """Load product entries from JSON file."""
    data = json.loads(Path(path).read_text())
    products = []
    for item in data:
        products.append(ProductEntry(
            rank=item["rank"],
            name=item["name"],
            positioning=item.get("positioning", ""),
            benefits=item.get("benefits", []),
            target_audience=item.get("target_audience", ""),
            downside=item.get("downside", ""),
            amazon_url=item.get("amazon_url", ""),
        ))
    return products


def _parse_script_file(path: str) -> ScriptOutput:
    """Parse a structured script file into ScriptOutput.

    Expected format: sections separated by markers like [HOOK], [AVATAR_INTRO],
    [PRODUCT_5], etc. After the main script: AVATAR_INTRO:, DESCRIPTION:,
    THUMBNAILS: sections.
    """
    text = Path(path).read_text()

    # Parse sections
    sections: list[ScriptSection] = []
    avatar_intro = ""
    youtube_desc = ""
    thumbnails: list[str] = []

    # Map section markers to types
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

    current_section = None
    current_lines: list[str] = []
    meta_mode = None  # "avatar", "description", "thumbnails"

    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()

        # Check for section markers
        if upper in marker_map:
            # Save previous section
            if current_section:
                sections.append(ScriptSection(
                    section_type=current_section,
                    content="\n".join(current_lines).strip(),
                ))
            current_section = marker_map[upper]
            current_lines = []
            meta_mode = None
            continue

        # Check for meta sections (after main script)
        if stripped.startswith("AVATAR_INTRO:") or stripped.startswith("AVATAR INTRO:"):
            if current_section:
                sections.append(ScriptSection(
                    section_type=current_section,
                    content="\n".join(current_lines).strip(),
                ))
                current_section = None
                current_lines = []
            avatar_intro = stripped.split(":", 1)[1].strip()
            meta_mode = "avatar"
            continue
        if stripped.startswith("DESCRIPTION:") or stripped.startswith("YOUTUBE DESCRIPTION:"):
            meta_mode = "description"
            youtube_desc = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("THUMBNAILS:") or stripped.startswith("THUMBNAIL HEADLINES:"):
            meta_mode = "thumbnails"
            continue

        # Accumulate content
        if meta_mode == "avatar" and stripped and not avatar_intro:
            avatar_intro = stripped
        elif meta_mode == "description":
            if stripped:
                youtube_desc += (" " + stripped) if youtube_desc else stripped
        elif meta_mode == "thumbnails":
            if stripped and stripped.startswith(("-", "*", "1", "2", "3")):
                # Strip list markers
                clean = stripped.lstrip("-*0123456789.) ").strip()
                if clean:
                    thumbnails.append(clean)
        elif current_section:
            current_lines.append(line)

    # Save last section
    if current_section:
        sections.append(ScriptSection(
            section_type=current_section,
            content="\n".join(current_lines).strip(),
        ))

    return ScriptOutput(
        sections=sections,
        avatar_intro=avatar_intro,
        youtube_description=youtube_desc,
        thumbnail_headlines=thumbnails,
    )


def cmd_generate(args) -> int:
    """Generate workflow prompts for script creation."""
    step = args.step

    # Refinement step can run standalone (no products needed)
    if step == "refinement":
        draft = ""
        if args.draft:
            draft = Path(args.draft).read_text()
        else:
            print("Error: --draft is required for refinement step", file=sys.stderr)
            return 2
        prompt = build_refinement_prompt(draft, args.charismatic)
        print("=" * 60)
        print("STEP 3: CLAUDE REFINEMENT PROMPT")
        print("=" * 60)
        print(prompt)
        return 0

    # All other steps need products
    if not args.products:
        print("Error: --products is required", file=sys.stderr)
        return 2

    products = _load_products(args.products)
    req = ScriptRequest(
        niche=args.niche,
        products=products,
        charismatic_type=args.charismatic,
        reference_videos=args.reference.split(",") if args.reference else [],
    )

    errors = validate_request(req)
    if errors:
        for e in errors:
            print(f"Validation error: {e}", file=sys.stderr)
        return 2

    if step in ("extraction", "all"):
        prompt = build_extraction_prompt(req.reference_videos, req.niche)
        print("=" * 60)
        print("STEP 1: VIRAL PATTERN EXTRACTION PROMPT")
        print("=" * 60)
        print(prompt)
        print()

    if step in ("draft", "all"):
        notes = ""
        if args.notes:
            notes = Path(args.notes).read_text()
        elif step == "all":
            notes = "(run step 1 first to get extraction notes)"
        prompt = build_draft_prompt(req, notes)
        print("=" * 60)
        print("STEP 2: STRUCTURED DRAFT PROMPT (for GPT)")
        print("=" * 60)
        print(prompt)
        print()

    if step in ("refinement", "all"):
        draft = ""
        if args.draft:
            draft = Path(args.draft).read_text()
        elif step == "all":
            draft = "(run step 2 first to get draft)"
        prompt = build_refinement_prompt(draft, req.charismatic_type)
        print("=" * 60)
        print("STEP 3: CLAUDE REFINEMENT PROMPT")
        print("=" * 60)
        print(prompt)
        print()

    if step == "all":
        print("=" * 60)
        print("STEP 4: Run --validate on the final script")
        print("=" * 60)

    return 0


def cmd_validate(args) -> int:
    """Validate a completed script."""
    output = _parse_script_file(args.validate)
    errors = validate_script(output)

    print(f"Word count:         {output.total_word_count}")
    print(f"Estimated duration: {output.estimated_duration_min} min")
    print(f"Sections found:     {len(output.sections)}")
    print(f"Avatar intro:       {'yes' if output.avatar_intro else 'MISSING'}")
    print(f"Thumbnail headlines: {len(output.thumbnail_headlines)}")
    print()

    if errors:
        print(f"VALIDATION FAILED — {len(errors)} issue(s):\n")
        for i, e in enumerate(errors, 1):
            print(f"  {i}. {e}")
        return 1
    else:
        print("VALIDATION PASSED")

        # Also print the validation prompt for a final LLM review
        if args.llm_review:
            full_text = "\n\n".join(s.content for s in output.sections)
            prompt = build_validation_prompt(full_text)
            print()
            print("=" * 60)
            print("STEP 4: FINAL VALIDATION PROMPT (for LLM review)")
            print("=" * 60)
            print(prompt)

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Video script generation workflow (Amazon Associates Top 5)"
    )
    parser.add_argument(
        "--products", default=None,
        help="Path to products JSON file",
    )
    parser.add_argument(
        "--niche", default="",
        help="Product niche (e.g. 'portable speakers', 'desk accessories')",
    )
    parser.add_argument(
        "--step", default="all",
        choices=["extraction", "draft", "refinement", "all"],
        help="Which workflow step to generate prompts for",
    )
    parser.add_argument(
        "--charismatic", default="reality_check",
        choices=CHARISMATIC_TYPES,
        help="Charismatic signature type for this video",
    )
    parser.add_argument(
        "--reference", default="",
        help="Comma-separated YouTube URLs for viral pattern extraction",
    )
    parser.add_argument(
        "--notes", default=None,
        help="Path to extraction notes file (for draft step)",
    )
    parser.add_argument(
        "--draft", default=None,
        help="Path to draft script file (for refinement step)",
    )
    parser.add_argument(
        "--validate", default=None,
        help="Path to completed script file to validate",
    )
    parser.add_argument(
        "--llm-review", action="store_true",
        help="Also output LLM validation prompt after passing",
    )
    args = parser.parse_args()

    if args.validate:
        return cmd_validate(args)

    if args.products or args.step == "refinement":
        return cmd_generate(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
