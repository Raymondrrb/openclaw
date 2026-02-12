#!/usr/bin/env python3
"""Production pipeline orchestrator for Rayviews YouTube channel.

Wraps all individual tools behind repeatable subcommands with validation,
resumability, and Telegram notifications.

Recommended daily flow:
    python3 tools/pipeline.py day --video-id <id> [--niche "<niche>"]
      (runs init → research → script-brief, then stops for human)

    ... human writes script_raw.txt from the brief ...

    python3 tools/pipeline.py script-review --video-id <id>
    python3 tools/pipeline.py assets --video-id <id> [--force] [--dry-run]
    python3 tools/pipeline.py tts --video-id <id> [--force] [--patch N ...]
    python3 tools/pipeline.py manifest --video-id <id>

Individual commands:
    python3 tools/pipeline.py init --video-id <id> --niche "<niche>"
    python3 tools/pipeline.py research --video-id <id>
    python3 tools/pipeline.py script-brief --video-id <id>
    python3 tools/pipeline.py script --video-id <id> [--charismatic ...]
    python3 tools/pipeline.py status --video-id <id> | --all

Exit codes: 0=ok, 1=error, 2=action_required

Stdlib only (except Playwright which is imported lazily by dzine_browser).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, now_iso, project_root
from tools.lib.video_paths import VIDEOS_BASE, VideoPaths

# Load .env early so all tools see credentials
load_env_file()

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_ACTION_REQUIRED = 2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_header(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}\n")


def _load_products(paths: VideoPaths):
    """Load and return products list from products.json, or None if missing."""
    if not paths.products_json.is_file():
        return None
    from tools.lib.amazon_research import load_products_json
    return load_products_json(paths.products_json)


def _load_niche(paths: VideoPaths) -> str:
    """Load niche string from niche.txt."""
    if paths.niche_txt.is_file():
        return paths.niche_txt.read_text(encoding="utf-8").strip()
    return ""


def _products_to_entries(products, raw_data: dict | None = None):
    """Convert AmazonProduct list to ProductEntry list for script_schema.

    If raw_data is provided (the full products.json dict), extract
    source_evidence per product so review data flows into script prompts.
    """
    from tools.lib.script_schema import ProductEntry

    # Build a rank → raw product dict lookup for evidence
    raw_by_rank: dict[int, dict] = {}
    if raw_data:
        for rp in raw_data.get("products", []):
            raw_by_rank[rp.get("rank", 0)] = rp

    entries = []
    for p in products:
        raw = raw_by_rank.get(p.rank, {})
        evidence = raw.get("evidence", [])

        entries.append(ProductEntry(
            rank=p.rank,
            name=p.name,
            positioning=p.positioning,
            benefits=p.benefits,
            target_audience=p.target_audience,
            downside=p.downside,
            amazon_url=p.affiliate_url or p.amazon_url,
            source_evidence=evidence,
        ))
    return entries


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:
    """Initialize a new video project."""
    from tools.lib.pipeline_status import start_pipeline, update_milestone
    from tools.lib.notify import notify_start

    _print_header(f"Init: {args.video_id}")

    paths = VideoPaths(args.video_id)

    if paths.root.exists() and not args.force:
        print(f"Video folder already exists: {paths.root}")
        print("Use --force to reinitialize")
        return EXIT_ERROR

    # Create directory structure
    paths.ensure_dirs()
    print(f"Created directory structure at {paths.root}")

    # Write niche.txt
    paths.niche_txt.write_text(args.niche + "\n", encoding="utf-8")
    print(f"Niche: {args.niche}")

    # Generate subcategory contract
    from tools.lib.subcategory_contract import generate_contract, write_contract
    from tools.lib.dzine_schema import detect_category
    contract = generate_contract(args.niche, detect_category(args.niche))
    write_contract(contract, paths.subcategory_contract)
    print(f"Wrote subcategory contract ({contract.category}): {len(contract.allowed_keywords)} allowed, {len(contract.disallowed_keywords)} disallowed keywords")

    # Write empty products.json template
    if not paths.products_json.is_file() or args.force:
        template = {
            "keyword": args.niche,
            "generated_at": now_iso(),
            "products": [
                {
                    "rank": rank,
                    "name": "",
                    "positioning": "",
                    "benefits": [],
                    "target_audience": "",
                    "downside": "",
                    "amazon_url": "",
                    "price": "",
                    "rating": "",
                    "reviews_count": "",
                    "image_url": "",
                    "asin": "",
                }
                for rank in [5, 4, 3, 2, 1]
            ],
        }
        paths.products_json.write_text(
            json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Created products.json template (fill in product data)")

    # Initialize status
    start_pipeline(args.video_id)
    update_milestone(args.video_id, "research", "")

    # Notify
    notify_start(args.video_id, details=[
        f"Niche: {args.niche}",
        f"Folder: {paths.root}",
    ])

    print(f"\nNext: Fill in {paths.products_json}")
    print(f"      Then run: python3 tools/pipeline.py research --video-id {args.video_id}")
    return EXIT_OK


def cmd_research(args) -> int:
    """Run the full research pipeline (RUN mode) or validate existing (BUILD mode).

    Default is RUN mode: executes the full chain end-to-end:
      niche_picker -> research_agent (browse pages) -> amazon_verify -> top5_ranker

    BUILD mode: only validate existing products.json for pipeline readiness.
    """
    import datetime
    from tools.lib.pipeline_status import update_milestone, record_error
    from tools.lib.notify import (
        notify_progress, notify_start, notify_action_required, notify_summary,
    )

    mode = getattr(args, "mode", "run")
    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    _print_header(f"Research: {args.video_id} [{mode.upper()} mode]")

    paths = VideoPaths(args.video_id)
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    # BUILD mode: just validate existing products.json
    if mode == "build":
        return _validate_existing_products(args.video_id, paths)

    # ---------------------------------------------------------------
    # RUN mode: execute the full research pipeline
    # ---------------------------------------------------------------

    # --- Step 1: Niche ---
    niche = _load_niche(paths)
    if not niche:
        print("Step 1: Picking niche...")
        from tools.niche_picker import pick_niche, update_history
        candidate = pick_niche(today)
        niche = candidate.keyword
        paths.ensure_dirs()
        paths.niche_txt.write_text(niche + "\n", encoding="utf-8")
        update_history(niche, today, video_id=args.video_id)
        print(f"  Niche: {niche} (score: {candidate.score:.1f})")
    else:
        print(f"Step 1: Niche: {niche}")

    # Generate subcategory contract if not already present
    if not paths.subcategory_contract.is_file():
        from tools.lib.subcategory_contract import generate_contract, write_contract
        from tools.lib.dzine_schema import detect_category
        contract = generate_contract(niche, detect_category(niche))
        write_contract(contract, paths.subcategory_contract)
        print(f"  Wrote subcategory contract ({contract.category})")

    update_milestone(args.video_id, "research", "search_started")
    notify_start(args.video_id, details=[f"Niche: {niche}", "Research started"])

    # --- Step 2: Research agent (browse real pages) ---
    shortlist_path = paths.root / "inputs" / "shortlist.json"
    report_path = paths.root / "inputs" / "research_report.md"

    if shortlist_path.is_file() and not force:
        print(f"\nStep 2: Shortlist exists ({shortlist_path.name}), skipping research")
        print(f"  Use --force to re-run research")
        shortlist_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
        shortlist = shortlist_data.get("shortlist", [])
    else:
        print(f"\nStep 2: Running research agent for '{niche}'...")
        from tools.research_agent import run_reviews_research

        report = run_reviews_research(
            args.video_id, niche,
            output_dir=paths.root / "inputs",
            force=force,
            dry_run=dry_run,
            contract_path=paths.subcategory_contract,
        )

        if dry_run:
            print("\n[DRY RUN] Would continue with Amazon verify + Top 5 ranking")
            return EXIT_OK

        shortlist_data = json.loads(shortlist_path.read_text(encoding="utf-8"))
        shortlist = shortlist_data.get("shortlist", [])

        # Check DONE criteria
        if report.validation_errors:
            print(f"\n  Research DONE criteria NOT met:")
            for err in report.validation_errors:
                print(f"    - {err}")
            notify_action_required(
                args.video_id, "research",
                f"Research incomplete: {report.validation_errors[0]}",
                next_action="Review research_report.md and re-run or add sources manually",
            )
            return EXIT_ACTION_REQUIRED

    if not shortlist:
        print("\n  No candidates found.")
        notify_action_required(
            args.video_id, "research", "No candidates from trusted sources",
            next_action="Try a different niche or add products manually",
        )
        return EXIT_ACTION_REQUIRED

    update_milestone(args.video_id, "research", "shortlist_built")
    notify_progress(
        args.video_id, "research", "shortlist_built",
        progress_done=len(shortlist), progress_total=len(shortlist),
        next_action="Verifying on Amazon US",
        details=[f"Shortlist: {len(shortlist)} products from reviewed articles"],
    )

    # --- Step 3: Amazon verification ---
    verified_path = paths.root / "inputs" / "verified.json"

    if verified_path.is_file() and not force:
        print(f"\nStep 3: Verified products exist ({verified_path.name}), skipping")
        verified_data = json.loads(verified_path.read_text(encoding="utf-8"))
        verified = verified_data.get("products", [])
    else:
        print(f"\nStep 3: Verifying {len(shortlist)} products on Amazon US...")
        import time as _time
        from tools.amazon_verify import verify_products, write_verified

        verified_objs = verify_products(shortlist, video_id=args.video_id)

        # Retry once if <5 products verified and shortlist had enough candidates
        if len(verified_objs) < 5 and len(shortlist) >= 5:
            verified_names = {v.product_name.lower() for v in verified_objs}
            failed = [s for s in shortlist if s.get("product_name", "").lower() not in verified_names]
            if failed:
                print(f"  Retrying {len(failed)} failed verifications...")
                _time.sleep(5)
                retry_objs = verify_products(failed, video_id=args.video_id)
                verified_objs.extend(retry_objs)

        verified = [
            {
                "product_name": v.product_name,
                "brand": v.brand,
                "asin": v.asin,
                "amazon_url": v.amazon_url,
                "affiliate_url": v.affiliate_url,
                "affiliate_short_url": v.affiliate_short_url,
                "amazon_title": v.amazon_title,
                "amazon_price": v.amazon_price,
                "amazon_rating": v.amazon_rating,
                "amazon_reviews": v.amazon_reviews,
                "amazon_image_url": v.amazon_image_url,
                "match_confidence": v.match_confidence,
                "verification_method": v.verification_method,
                "evidence": v.evidence,
                "key_claims": v.key_claims,
            }
            for v in verified_objs
        ]
        write_verified(verified_objs, verified_path)
        print(f"  Verified: {len(verified)}/{len(shortlist)}")

    if not verified:
        print("\n  No products verified on Amazon US.")
        notify_action_required(
            args.video_id, "research", "No products found on Amazon",
            next_action="Check shortlist and verify manually",
        )
        return EXIT_ACTION_REQUIRED

    # --- Step 4: Top 5 ranking ---
    print(f"\nStep 4: Selecting Top 5...")
    from tools.top5_ranker import select_top5, write_products_json

    top5 = select_top5(verified)

    write_products_json(
        top5, niche, paths.products_json,
        video_id=args.video_id, date=today,
    )

    update_milestone(args.video_id, "research", "affiliate_links_ready")

    print(f"\n  Top 5 ({niche}):")
    for p in top5:
        conf = p.get("match_confidence", "?")
        print(f"    #{p['rank']} {p.get('product_name', '?'):<45s} [{p.get('category_label', '?')}] ({conf})")

    notify_progress(
        args.video_id, "research", "affiliate_links_ready",
        next_action=f"python3 tools/pipeline.py script --video-id {args.video_id}",
        details=[
            f"Top 5 locked for '{niche}'",
            f"Verified {len(verified)} products, ranked {len(top5)}",
        ],
    )

    print(f"\nWrote {paths.products_json}")
    print(f"\nNext: python3 tools/pipeline.py script --video-id {args.video_id}")
    return EXIT_OK


def _validate_existing_products(video_id: str, paths: VideoPaths) -> int:
    """BUILD mode: validate existing products.json."""
    from tools.lib.amazon_research import validate_products
    from tools.lib.pipeline_status import update_milestone, record_error

    if not paths.products_json.is_file():
        print(f"products.json not found: {paths.products_json}")
        print(f"\nRun in RUN mode (default) to generate it:")
        print(f"  python3 tools/pipeline.py research --video-id {video_id}")
        return EXIT_ACTION_REQUIRED

    products = _load_products(paths)
    if products is None:
        print("Failed to load products.json")
        return EXIT_ERROR

    errors = validate_products(products)
    if errors:
        print(f"Validation failed ({len(errors)} issues):")
        for e in errors:
            print(f"  - {e}")
        record_error(video_id, "research", "validation", "; ".join(errors))
        return EXIT_ERROR

    missing_links = [p for p in products if not p.affiliate_url and not p.amazon_url]
    if missing_links:
        print("Products missing URLs:")
        for p in missing_links:
            print(f"  - Rank {p.rank}: {p.name}")
        return EXIT_ACTION_REQUIRED

    update_milestone(video_id, "research", "affiliate_links_ready")
    print(f"Products validated: {len(products)} products ready")
    for p in sorted(products, key=lambda x: -x.rank):
        url = p.affiliate_url or p.amazon_url
        print(f"  #{p.rank} {p.name} — {url[:50]}...")

    print(f"\nNext: python3 tools/pipeline.py script --video-id {video_id}")
    return EXIT_OK


def cmd_script(args) -> int:
    """Generate script prompts, optionally auto-generate script via LLM APIs."""
    from tools.lib.script_schema import (
        ScriptRequest,
        build_extraction_prompt,
        build_draft_prompt,
        build_refinement_prompt,
        validate_request,
    )
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress, notify_action_required, notify_error

    _print_header(f"Script: {args.video_id}")

    paths = VideoPaths(args.video_id)
    generate = getattr(args, "generate", False)
    force = getattr(args, "force", False)

    # Load products
    products = _load_products(paths)
    if products is None:
        print(f"products.json not found: {paths.products_json}")
        print(f"\nNext: python3 tools/pipeline.py research --video-id {args.video_id}")
        return EXIT_ACTION_REQUIRED

    niche = _load_niche(paths)
    if not niche:
        print(f"niche.txt not found: {paths.niche_txt}")
        return EXIT_ERROR

    # Load raw JSON to pass evidence through to script prompts
    raw_data = json.loads(paths.products_json.read_text(encoding="utf-8"))
    entries = _products_to_entries(products, raw_data)
    req = ScriptRequest(
        niche=niche,
        products=entries,
        charismatic_type=args.charismatic,
    )

    errors = validate_request(req)
    if errors:
        print(f"Request validation failed:")
        for e in errors:
            print(f"  - {e}")
        return EXIT_ERROR

    # Generate prompts
    paths.prompts_dir.mkdir(parents=True, exist_ok=True)

    extraction = build_extraction_prompt([], niche)
    prompt_path = paths.prompts_dir / "extraction_prompt.txt"
    prompt_path.write_text(extraction, encoding="utf-8")
    print(f"Wrote {prompt_path}")

    draft = build_draft_prompt(req, "(paste extraction notes here)")
    prompt_path = paths.prompts_dir / "draft_prompt.txt"
    prompt_path.write_text(draft, encoding="utf-8")
    print(f"Wrote {prompt_path}")

    refine = build_refinement_prompt("(paste draft here)", args.charismatic)
    prompt_path = paths.prompts_dir / "refine_prompt.txt"
    prompt_path.write_text(refine, encoding="utf-8")
    print(f"Wrote {prompt_path}")

    # Write script template
    template_path = paths.root / "script" / "script_template.txt"
    template_lines = [
        f"# Script Template: {niche}",
        f"# Target: 1300-1800 words (8-12 min at 150 WPM)",
        f"# Charismatic type: {args.charismatic}",
        "",
        "[HOOK]",
        "# 100-150 words. Open with problem/tension.",
        "",
        "[AVATAR_INTRO]",
        "# 3-6 seconds. Brief channel intro.",
        "",
    ]
    for rank in [5, 4, 3, 2, 1]:
        p = next((e for e in entries if e.rank == rank), None)
        name = p.name if p else f"Product {rank}"
        template_lines.extend([
            f"[PRODUCT_{rank}]",
            f"# 200-300 words. {name}",
            f"# Include: positioning, 2-3 benefits, target audience, honest downside, transition",
            "",
        ])
        if rank == 3:
            template_lines.extend([
                "[RETENTION_RESET]",
                "# 50-80 words. Pattern interrupt / audience question.",
                "",
            ])
    template_lines.extend([
        "[CONCLUSION]",
        "# CTA + affiliate disclosure.",
        '# Must include: "affiliate", "commission", "no extra cost"',
        "",
    ])
    template_path.write_text("\n".join(template_lines), encoding="utf-8")
    print(f"Wrote {template_path}")

    update_milestone(args.video_id, "script", "outline_generated")

    # --generate: auto-generate script via LLM APIs
    if generate:
        if paths.script_txt.is_file() and not force:
            print(f"\nScript already exists: {paths.script_txt}")
            print("Use --force to regenerate")
            _validate_existing_script(paths, args.video_id)
            return EXIT_OK

        return _auto_generate_script(
            args.video_id, paths, draft, args.charismatic,
        )

    # Manual mode: check if script.txt already exists
    if paths.script_txt.is_file():
        print(f"\nFound existing script: {paths.script_txt}")
        _validate_existing_script(paths, args.video_id)
    else:
        print(f"\nNext: Write {paths.script_txt} using the template and prompts")
        print(f"      Or run with --generate to auto-generate via GPT-4o + Claude:")
        print(f"      python3 tools/pipeline.py script --video-id {args.video_id} --generate")
        return EXIT_ACTION_REQUIRED

    return EXIT_OK


def _auto_generate_script(
    video_id: str,
    paths: VideoPaths,
    draft_prompt: str,
    charismatic: str,
) -> int:
    """Auto-generate script via OpenAI (draft) + Anthropic (refinement)."""
    import os
    from tools.lib.script_generate import run_script_pipeline
    from tools.lib.script_schema import build_refinement_prompt
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress, notify_error

    # Check API keys
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not openai_key:
        print("OPENAI_API_KEY not set in .env or environment")
        print("Add to .env: OPENAI_API_KEY=sk-...")
        return EXIT_ERROR

    skip_refine = not anthropic_key
    if skip_refine:
        print("ANTHROPIC_API_KEY not set — skipping refinement (using raw draft)")

    refine_template = build_refinement_prompt("(paste draft here)", charismatic)

    print(f"\nAuto-generating script for '{_load_niche(paths)}'...")
    result = run_script_pipeline(
        draft_prompt,
        refine_template,
        paths.root / "script",
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        skip_refinement=skip_refine,
    )

    if not result.success:
        for err in result.errors:
            print(f"  Error: {err}")
        notify_error(
            video_id, "script", "generation_failed",
            result.errors[0] if result.errors else "Unknown error",
        )
        return EXIT_ERROR

    # Validate the generated script
    print(f"\nValidating generated script...")
    _validate_existing_script(paths, video_id)

    update_milestone(video_id, "script", "script_generated")

    notify_progress(
        video_id, "script", "script_generated",
        details=[
            f"Words: {result.word_count}",
            f"Draft: {result.draft.model if result.draft else '?'} ({result.draft.duration_s:.0f}s)" if result.draft else "",
            f"Refined: {result.refinement.model if result.refinement else 'skipped'}" if result.refinement else "",
        ],
        next_action=f"python3 tools/pipeline.py assets --video-id {video_id}",
    )

    if result.errors:
        print(f"\nWarnings:")
        for err in result.errors:
            print(f"  - {err}")

    print(f"\nScript files:")
    if result.script_raw_path:
        print(f"  Raw draft:  {result.script_raw_path}")
    if result.script_final_path:
        print(f"  Refined:    {result.script_final_path}")
    print(f"  Final:      {result.script_txt_path}")
    print(f"\nNext: python3 tools/pipeline.py assets --video-id {video_id}")
    return EXIT_OK


def _validate_existing_script(paths: VideoPaths, video_id: str) -> None:
    """Validate an existing script.txt and write metadata."""
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.script_schema import (
        SECTION_ORDER,
        SPEAKING_WPM,
        ScriptOutput,
        ScriptSection,
        validate_script,
    )

    text = paths.script_txt.read_text(encoding="utf-8")

    # Parse sections
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

    sections: list[ScriptSection] = []
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip().upper()
        if stripped in marker_map:
            if current_key:
                sections.append(ScriptSection(
                    section_type=current_key,
                    content="\n".join(current_lines).strip(),
                ))
            current_key = marker_map[stripped]
            current_lines = []
        elif current_key:
            current_lines.append(line)

    if current_key:
        sections.append(ScriptSection(
            section_type=current_key,
            content="\n".join(current_lines).strip(),
        ))

    output = ScriptOutput(sections=sections)
    errors = validate_script(output)

    # Write script_meta.json
    meta = {
        "total_word_count": output.total_word_count,
        "estimated_duration_min": output.estimated_duration_min,
        "section_count": len(output.sections),
        "validation_errors": errors,
        "validated_at": now_iso(),
    }
    paths.script_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"  Word count: {output.total_word_count}")
    print(f"  Duration:   {output.estimated_duration_min} min")
    print(f"  Sections:   {len(output.sections)}")

    if errors:
        print(f"\n  Warnings ({len(errors)}):")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  Validation: PASSED")

    update_milestone(video_id, "script", "script_approved")


def cmd_script_brief(args) -> int:
    """Generate a structured manual brief from products.json + seo.json."""
    from tools.lib.script_brief import generate_brief
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress

    _print_header(f"Script Brief: {args.video_id}")

    paths = VideoPaths(args.video_id)

    # Check prereqs
    if not paths.products_json.is_file():
        print(f"products.json not found: {paths.products_json}")
        print(f"\nNext: python3 tools/pipeline.py research --video-id {args.video_id}")
        return EXIT_ACTION_REQUIRED

    niche = _load_niche(paths)
    if not niche:
        print(f"niche.txt not found: {paths.niche_txt}")
        return EXIT_ERROR

    # Load data
    products_data = json.loads(paths.products_json.read_text(encoding="utf-8"))
    seo_data = {}
    if paths.seo_json.is_file():
        seo_data = json.loads(paths.seo_json.read_text(encoding="utf-8"))

    # Load channel style (optional)
    style_path = project_root() / "channel" / "channel_style.md"
    channel_style = style_path.read_text(encoding="utf-8") if style_path.is_file() else ""

    # Generate brief
    brief_text = generate_brief(niche, products_data, seo_data, channel_style=channel_style)
    paths.manual_brief.parent.mkdir(parents=True, exist_ok=True)
    paths.manual_brief.write_text(brief_text, encoding="utf-8")

    product_count = len(products_data.get("products", []))
    sources = products_data.get("sources_used", [])

    update_milestone(args.video_id, "script", "brief_generated")
    notify_progress(
        args.video_id, "script", "brief_generated",
        details=[
            f"Niche: {niche}",
            f"Products: {product_count}",
            f"Sources: {', '.join(sources) if sources else 'derived'}",
        ],
    )

    print(f"Wrote {paths.manual_brief}")
    print(f"  Products: {product_count}")
    print(f"  Sources:  {', '.join(sources) if sources else '(derived from niche)'}")
    print(f"\nNext: Write your script in {paths.script_raw}")
    print(f"      Then run: python3 tools/pipeline.py script-review --video-id {args.video_id}")
    return EXIT_OK


def cmd_script_review(args) -> int:
    """Review script_raw.txt: validate claims, check structure, apply light fixes."""
    from tools.lib.script_brief import review_script, format_review_notes, apply_light_fixes
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress, notify_action_required

    _print_header(f"Script Review: {args.video_id}")

    paths = VideoPaths(args.video_id)

    # Check prereqs
    if not paths.script_raw.is_file():
        print(f"script_raw.txt not found: {paths.script_raw}")
        print(f"\nWrite your script there first, then re-run this command.")
        return EXIT_ACTION_REQUIRED

    if not paths.products_json.is_file():
        print(f"products.json not found: {paths.products_json}")
        return EXIT_ERROR

    script_text = paths.script_raw.read_text(encoding="utf-8")
    products_data = json.loads(paths.products_json.read_text(encoding="utf-8"))

    # Run review
    result = review_script(script_text, products_data)

    # Write review notes
    notes = format_review_notes(result, args.video_id)
    paths.script_review_notes.parent.mkdir(parents=True, exist_ok=True)
    paths.script_review_notes.write_text(notes, encoding="utf-8")
    print(f"Wrote {paths.script_review_notes}")

    # Print summary
    print(f"\n  Word count: {result.word_count} (target: 1300-1800)")
    print(f"  Duration:   {result.estimated_duration_min} min")

    if result.section_word_counts:
        print(f"\n  Sections:")
        for sec, wc in result.section_word_counts.items():
            print(f"    {sec}: {wc} words")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for issue in result.errors:
            print(f"    [{issue.section}] {issue.message}")

    if result.warnings:
        print(f"\n  Warnings ({len(result.warnings)}):")
        for issue in result.warnings:
            print(f"    [{issue.section}] {issue.message}")

    # Apply light fixes and write script_final.txt
    fixed_text, changes = apply_light_fixes(script_text)
    paths.script_final.parent.mkdir(parents=True, exist_ok=True)
    paths.script_final.write_text(fixed_text, encoding="utf-8")
    print(f"\nWrote {paths.script_final}")
    if changes:
        print(f"  Light fixes applied:")
        for c in changes:
            print(f"    - {c}")
    else:
        print(f"  No automatic fixes needed (clean copy)")

    if result.passed:
        update_milestone(args.video_id, "script", "script_approved")
        notify_progress(
            args.video_id, "script", "script_approved",
            details=[f"Words: {result.word_count}", f"Errors: 0"],
        )
        print(f"\n  Verdict: PASS")
        print(f"\nNext: Copy to script.txt and proceed:")
        print(f"  cp {paths.script_final} {paths.script_txt}")
        print(f"  python3 tools/pipeline.py tts --video-id {args.video_id}")
        return EXIT_OK
    else:
        notify_action_required(
            args.video_id, "script",
            f"Script review: {len(result.errors)} error(s)",
            next_action="Fix errors in script_raw.txt, re-run script-review",
        )
        print(f"\n  Verdict: NEEDS REVISION ({len(result.errors)} error(s))")
        print(f"\nNext: Fix errors in {paths.script_raw}, then re-run:")
        print(f"  python3 tools/pipeline.py script-review --video-id {args.video_id}")
        return EXIT_ACTION_REQUIRED


def _download_amazon_images(products, paths: VideoPaths) -> dict[int, Path]:
    """Download Amazon product reference images for Dzine generation.

    Returns {rank: local_path} for successfully downloaded images.
    Skips if file already exists and is >10KB.
    """
    import urllib.request
    ref_images: dict[int, Path] = {}
    paths.assets_amazon.mkdir(parents=True, exist_ok=True)

    for p in products:
        image_url = getattr(p, "image_url", "")
        if not image_url:
            continue
        dest = paths.amazon_ref_image(p.rank)
        if dest.is_file() and dest.stat().st_size > 10 * 1024:
            ref_images[p.rank] = dest
            continue
        try:
            urllib.request.urlretrieve(image_url, str(dest))
            if dest.is_file() and dest.stat().st_size > 1024:
                ref_images[p.rank] = dest
                print(f"  Downloaded ref image: {dest.name}")
            else:
                print(f"  Warning: ref image too small for rank {p.rank}, skipping")
        except Exception as exc:
            print(f"  Warning: could not download ref image for rank {p.rank}: {exc}")
    return ref_images


def cmd_assets(args) -> int:
    """Check/generate Dzine assets (thumbnail + variant product images)."""
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress, notify_action_required
    from tools.lib.preflight_gate import can_run_assets
    from tools.lib.dzine_schema import (
        DzineRequest, build_prompts, detect_category, variants_for_rank,
    )

    MIN_ASSET_SIZE = 80 * 1024  # 80 KB minimum for valid images

    _print_header(f"Assets: {args.video_id}")

    # Preflight safety gate (skip on --dry-run so status check still works)
    if not args.dry_run:
        ok, reason = can_run_assets(args.video_id)
        if not ok:
            print(f"Blocked: {reason}")
            notify_action_required(args.video_id, "assets", reason,
                                   next_action="Fix the issue above, then re-run assets")
            return EXIT_ACTION_REQUIRED

    paths = VideoPaths(args.video_id)

    products = _load_products(paths)
    if products is None:
        print(f"products.json not found: {paths.products_json}")
        return EXIT_ACTION_REQUIRED

    niche = _load_niche(paths)
    category = detect_category(niche) if niche else "default"

    # Build needed list: 1 thumbnail + variant images per product
    needed: list[tuple[str, Path, dict]] = []  # (label, path, params)
    needed.append(("thumbnail", paths.thumbnail_path(), {
        "asset_type": "thumbnail",
        "product_name": niche or "Top 5 Products",
        "key_message": "Top 5",
    }))

    for rank in [5, 4, 3, 2, 1]:
        p = next((pr for pr in products if pr.rank == rank), None)
        name = p.name if p else f"Product {rank}"
        for variant in variants_for_rank(rank):
            needed.append((
                f"{rank:02d}_{variant}",
                paths.product_image_path(rank, variant),
                {
                    "asset_type": "product",
                    "product_name": name,
                    "image_variant": variant,
                    "niche_category": category,
                },
            ))

    # Check existing
    existing = []
    missing = []
    for label, path, params in needed:
        if path.is_file() and path.stat().st_size >= MIN_ASSET_SIZE:
            existing.append((label, path, params))
        else:
            missing.append((label, path, params))

    print(f"Assets: {len(existing)} present, {len(missing)} missing (total: {len(needed)})")
    for label, path, _ in existing:
        size_kb = path.stat().st_size // 1024
        print(f"  [x] {label} ({size_kb} KB)")
    for label, path, _ in missing:
        print(f"  [ ] {label}")

    if args.dry_run:
        if not missing:
            print("\nAll assets present.")
        return EXIT_OK

    if not missing and not args.force:
        print("\nAll assets present. Use --force to regenerate.")
        update_milestone(args.video_id, "assets", "product_images_done")
        return EXIT_OK

    # Download Amazon reference images
    print(f"\nDownloading Amazon reference images...")
    ref_images = _download_amazon_images(products, paths)
    print(f"  {len(ref_images)} reference images available")

    # Import Dzine browser
    try:
        from tools.lib.dzine_browser import generate_image
    except ImportError as exc:
        print(f"Cannot import Dzine modules: {exc}")
        print("Install playwright: pip install playwright && playwright install")
        return EXIT_ERROR

    paths.assets_dzine.mkdir(parents=True, exist_ok=True)
    (paths.assets_dzine / "products").mkdir(parents=True, exist_ok=True)
    (paths.assets_dzine / "prompts").mkdir(parents=True, exist_ok=True)

    targets = missing if not args.force else needed
    generated = 0
    failed = 0

    notify_progress(
        args.video_id, "assets", "generation_started",
        progress_done=0, progress_total=len(targets),
        details=[f"Starting Dzine generation: {len(targets)} images"],
    )

    for i, (label, dest_path, params) in enumerate(targets):
        print(f"\nGenerating {label} ({i+1}/{len(targets)})...")

        # Add reference image if available for product variants
        is_thumbnail = label == "thumbnail"
        if not is_thumbnail:
            rank = int(label.split("_")[0])
            variant = label.split("_", 1)[1]
            if rank in ref_images:
                params["reference_image"] = str(ref_images[rank])

        req = DzineRequest(**params)
        req = build_prompts(req)

        # Save prompt to prompts dir
        if is_thumbnail:
            prompt_path = paths.thumbnail_prompt_path()
        else:
            prompt_path = paths.product_prompt_path(rank, variant)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(req.prompt, encoding="utf-8")

        result = generate_image(req, output_path=dest_path)

        if not result.success:
            # Single retry
            print(f"  Retry {label}...")
            result = generate_image(req, output_path=dest_path)

        if result.success and dest_path.is_file() and dest_path.stat().st_size >= MIN_ASSET_SIZE:
            size_kb = dest_path.stat().st_size // 1024
            print(f"  OK: {dest_path.name} ({size_kb} KB, {result.duration_s:.0f}s)")
            generated += 1
        elif result.success and dest_path.is_file():
            size_kb = dest_path.stat().st_size // 1024
            print(f"  Warning: {dest_path.name} too small ({size_kb} KB)")
            failed += 1
        else:
            print(f"  FAILED: {result.error}")
            failed += 1
            if "login" in (result.error or "").lower():
                notify_action_required(
                    args.video_id, "assets", "Dzine login required",
                    next_action="Log in to Dzine in the Brave browser",
                )
                return EXIT_ACTION_REQUIRED

        # Telegram progress every 5 images
        if (i + 1) % 5 == 0 or i + 1 == len(targets):
            notify_progress(
                args.video_id, "assets", f"generating",
                progress_done=i + 1, progress_total=len(targets),
            )

    update_milestone(args.video_id, "assets", "product_images_done")

    if failed == 0:
        notify_progress(
            args.video_id, "assets", "product_images_done",
            progress_done=len(targets), progress_total=len(targets),
            next_action=f"python3 tools/pipeline.py tts --video-id {args.video_id}",
            details=[f"Generated {generated} images, 0 failed"],
        )
    else:
        notify_action_required(
            args.video_id, "assets",
            f"{failed} image(s) failed generation",
            next_action=f"Re-run: python3 tools/pipeline.py assets --video-id {args.video_id}",
        )

    print(f"\nGenerated: {generated}, Failed: {failed}")
    print(f"\nNext: python3 tools/pipeline.py tts --video-id {args.video_id}")
    return EXIT_OK if failed == 0 else EXIT_ERROR


def cmd_tts(args) -> int:
    """Generate TTS voiceover chunks."""
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.tts_generate import generate_full, generate_patch
    from tools.lib.preflight_gate import can_run_tts
    from tools.lib.notify import notify_action_required, notify_progress, notify_error

    _print_header(f"TTS: {args.video_id}")

    paths = VideoPaths(args.video_id)

    # Preflight safety gate — requires reviewed script
    ok, reason = can_run_tts(args.video_id)
    if not ok:
        print(f"Blocked: {reason}")
        notify_action_required(args.video_id, "tts", reason,
                               next_action="Fix the issue above, then re-run tts")
        return EXIT_ACTION_REQUIRED

    if not paths.script_txt.is_file():
        print(f"Script not found: {paths.script_txt}")
        print(f"\nNext: python3 tools/pipeline.py script --video-id {args.video_id}")
        return EXIT_ACTION_REQUIRED

    script_text = paths.script_txt.read_text(encoding="utf-8")
    paths.audio_chunks.mkdir(parents=True, exist_ok=True)

    if args.patch:
        print(f"Patching chunks: {args.patch}")
        results = generate_patch(
            args.video_id,
            args.patch,
            script_text,
            output_dir=paths.audio_chunks,
        )
    else:
        # Check for existing chunks unless --force
        if not args.force:
            existing_chunks = list(paths.audio_chunks.glob("*.mp3"))
            existing_chunks = [f for f in existing_chunks if not f.stem.startswith("micro_")]
            if existing_chunks:
                print(f"Found {len(existing_chunks)} existing chunks. Use --force to regenerate.")
                print("Use --patch N to regenerate specific chunk(s).")
                return EXIT_OK

        results = generate_full(
            args.video_id,
            script_text,
            output_dir=paths.audio_chunks,
        )

    # Write tts_meta.json
    meta = {
        "video_id": args.video_id,
        "generated_at": now_iso(),
        "chunks": [
            {
                "index": m.index,
                "status": m.status,
                "word_count": m.word_count,
                "char_count": m.char_count,
                "estimated_duration_s": m.estimated_duration_s,
                "actual_duration_s": m.actual_duration_s,
                "file_path": m.file_path,
                "checksum_sha256": m.checksum_sha256,
                "error": m.error,
            }
            for m in results
        ],
    }
    paths.tts_meta.parent.mkdir(parents=True, exist_ok=True)
    paths.tts_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    ok = sum(1 for m in results if m.status == "success")
    failed = sum(1 for m in results if m.status == "failed")

    if failed:
        failed_indices = [m.index for m in results if m.status == "failed"]
        notify_error(
            args.video_id, "voice", "chunks_failed",
            f"{failed} chunk(s) failed",
            next_action=f"Retry: python3 tools/pipeline.py tts --video-id {args.video_id} --patch {' '.join(str(i) for i in failed_indices)}",
        )
        print(f"\n{failed} chunk(s) failed. Retry with:")
        print(f"  python3 tools/pipeline.py tts --video-id {args.video_id} --patch {' '.join(str(i) for i in failed_indices)}")
        return EXIT_ERROR

    update_milestone(args.video_id, "voice", "chunks_generated")
    notify_progress(
        args.video_id, "voice", "chunks_generated",
        progress_done=ok, progress_total=len(results),
        next_action=f"python3 tools/pipeline.py manifest --video-id {args.video_id}",
        details=[f"Generated {ok} TTS chunks successfully"],
    )
    print(f"\nNext: python3 tools/pipeline.py manifest --video-id {args.video_id}")
    return EXIT_OK


def cmd_broll_plan(args) -> int:
    """Generate B-roll search plan from products.json."""
    from tools.lib.dzine_schema import CATEGORY_BROLL_TERMS, detect_category

    _print_header(f"B-Roll Plan: {args.video_id}")

    paths = VideoPaths(args.video_id)
    products = _load_products(paths)
    niche = _load_niche(paths)

    if not products:
        print(f"Products not found: {paths.products_json}")
        return EXIT_ACTION_REQUIRED

    category = detect_category(niche) if niche else "default"
    broll_terms = CATEGORY_BROLL_TERMS.get(category, ("hands using product", "modern lifestyle technology"))

    lines = [
        f"# B-Roll Plan — {args.video_id}",
        f"Niche: {niche} (category: {category})",
        "",
        "Download 2-3 clips per product (3-6s each, 1080p minimum).",
        "Save to: assets/broll/",
        "Naming: <rank>_<description>.mp4 (e.g. 05_hands_using.mp4)",
        "",
        "Free sources: Pexels, Pixabay, Mixkit, Coverr",
        "",
        "---",
        "",
    ]

    for p in sorted(products, key=lambda x: x.rank, reverse=True):
        name_short = p.name.split("(")[0].strip()[:40]
        lines.append(f"## #{p.rank} — {p.name}")
        if p.positioning:
            lines.append(f"Positioning: {p.positioning}")
        lines.append("")
        lines.append("Search terms:")
        lines.append(f'  - "{name_short} in use"')
        lines.append(f'  - "{niche} lifestyle"')
        lines.append(f'  - "{broll_terms[0]}"')
        lines.append(f'  - "{broll_terms[1]}"')

        if p.benefits:
            lines.append(f'  - "{p.benefits[0][:30]}" (benefit visual)')
        lines.append("")
        lines.append("Suggested clips: hero transition, usage context, detail B-roll")
        lines.append("")

    # General clips section
    lines.extend([
        "---",
        "",
        "## General Clips (reusable across segments)",
        "",
        "Search terms:",
        '  - "transition whoosh motion"',
        '  - "abstract light leak"',
        '  - "modern technology montage"',
        f'  - "{niche} comparison"',
        "",
        "Retention reset clip:",
        '  - "split screen comparison" or "fast montage product"',
    ])

    plan_text = "\n".join(lines)

    # Write to resolve/ dir
    paths.resolve_dir.mkdir(parents=True, exist_ok=True)
    plan_path = paths.resolve_dir / "broll_plan.txt"
    plan_path.write_text(plan_text, encoding="utf-8")
    print(f"Wrote {plan_path}")

    # Also ensure broll dir exists
    paths.assets_broll.mkdir(parents=True, exist_ok=True)
    print(f"B-roll directory: {paths.assets_broll}")

    print(f"\n{len(products)} products, ~{len(products) * 2}-{len(products) * 3} clips needed")
    return EXIT_OK


def cmd_manifest(args) -> int:
    """Generate DaVinci Resolve edit manifest, markers, and notes."""
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.resolve_schema import (
        generate_manifest,
        manifest_to_edl,
        manifest_to_json,
        manifest_to_markers_csv,
        manifest_to_notes,
    )

    _print_header(f"Manifest: {args.video_id}")

    paths = VideoPaths(args.video_id)

    if not paths.script_txt.is_file():
        print(f"Script not found: {paths.script_txt}")
        return EXIT_ACTION_REQUIRED

    script_text = paths.script_txt.read_text(encoding="utf-8")

    products = _load_products(paths)
    niche = _load_niche(paths)
    product_names = {}
    product_benefits = {}
    product_data: dict[int, dict] = {}
    if products:
        for p in products:
            product_names[p.rank] = p.name
            product_benefits[p.rank] = p.benefits
            product_data[p.rank] = {
                "benefits": p.benefits,
                "downside": p.downside,
                "positioning": p.positioning,
            }

    # Generate manifest
    manifest = generate_manifest(
        args.video_id,
        script_text,
        paths.root,
        product_names=product_names,
        product_benefits=product_benefits,
    )

    # Write outputs
    paths.resolve_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = paths.resolve_dir / "edit_manifest.json"
    manifest_path.write_text(manifest_to_json(manifest), encoding="utf-8")
    print(f"Wrote {manifest_path}")

    markers_path = paths.resolve_dir / "markers.csv"
    markers_path.write_text(manifest_to_markers_csv(manifest), encoding="utf-8")
    print(f"Wrote {markers_path}")

    edl_path = paths.resolve_dir / "markers.edl"
    edl_path.write_text(manifest_to_edl(manifest), encoding="utf-8")
    print(f"Wrote {edl_path}")

    notes_path = paths.resolve_dir / "notes.md"
    notes_path.write_text(
        manifest_to_notes(manifest, product_data=product_data, niche=niche),
        encoding="utf-8",
    )
    print(f"Wrote {notes_path}")

    print(f"\nTotal duration: {manifest.total_duration_s:.0f}s ({manifest.total_duration_s/60:.1f} min)")
    print(f"Segments: {len(manifest.segments)}")

    update_milestone(args.video_id, "edit_prep", "notes_generated")

    from tools.lib.notify import notify_summary
    notify_summary(
        args.video_id,
        details=[
            f"Duration: {manifest.total_duration_s:.0f}s ({manifest.total_duration_s/60:.1f} min)",
            f"Segments: {len(manifest.segments)}",
            "Files: edit_manifest.json, markers.csv, markers.edl, notes.md",
        ],
        next_action="Open DaVinci Resolve > Import Timeline Markers from EDL > markers.edl",
    )

    print("\nNext: Open DaVinci Resolve > right-click timeline > Import > Timeline Markers from EDL > select markers.edl")
    return EXIT_OK


def cmd_run(args) -> int:
    """Run full pipeline via multi-agent orchestrator."""
    from tools.agent_orchestrator import Orchestrator, Stage

    _print_header(f"Run: {args.video_id}")

    orchestrator = Orchestrator()

    start_stage = None
    if args.stage:
        try:
            start_stage = Stage(args.stage)
        except ValueError:
            print(f"Unknown stage: {args.stage}")
            print(f"Available: {', '.join(s.value for s in Stage)}")
            return EXIT_ERROR

    stop_after = None
    if args.stop_after:
        try:
            stop_after = Stage(args.stop_after)
        except ValueError:
            print(f"Unknown stage: {args.stop_after}")
            return EXIT_ERROR

    ctx = orchestrator.run_pipeline(
        args.video_id,
        niche=args.niche,
        start_stage=start_stage,
        stop_after=stop_after,
        dry_run=args.dry_run,
        force=args.force,
    )

    # Print summary
    print(f"\nPipeline {'COMPLETE' if not ctx.aborted else 'STOPPED'}: {args.video_id}")
    print(f"  Niche: {ctx.niche}")
    print(f"  Stages: {len(ctx.stages_completed)}/{len(list(Stage))}")
    for s in ctx.stages_completed:
        print(f"    [x] {s.value}")
    pending = [s for s in Stage if s not in ctx.stages_completed]
    for s in pending:
        print(f"    [ ] {s.value}")
    if ctx.errors:
        print(f"  Errors ({len(ctx.errors)}):")
        for e in ctx.errors[:5]:
            print(f"    - {e}")

    if ctx.aborted:
        return EXIT_ACTION_REQUIRED
    return EXIT_OK


def cmd_day(args) -> int:
    """Daily pipeline: init (if needed) -> research -> script-brief. Stops for human."""
    import argparse
    import datetime
    from tools.lib.notify import notify_action_required

    _print_header(f"Day: {args.video_id}")

    paths = VideoPaths(args.video_id)
    niche = getattr(args, "niche", "") or ""
    force = getattr(args, "force", False)

    # --- Step 1: Init if root doesn't exist ---
    if not paths.root.exists() or force:
        if not niche:
            # Auto-pick niche
            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            from tools.niche_picker import pick_niche
            candidate = pick_niche(today)
            niche = candidate.keyword
            print(f"Auto-picked niche: {niche} (score: {candidate.score:.1f})")

        init_args = argparse.Namespace(
            video_id=args.video_id, niche=niche, force=force,
        )
        rc = cmd_init(init_args)
        if rc != EXIT_OK:
            return rc
    else:
        print(f"Video folder exists: {paths.root}")
        niche = _load_niche(paths)
        if not niche:
            print("niche.txt not found — run init first or pass --niche")
            return EXIT_ERROR

    # --- Step 2: Research ---
    print()
    research_args = argparse.Namespace(
        video_id=args.video_id, mode="run", dry_run=False, force=force,
    )
    rc = cmd_research(research_args)
    if rc != EXIT_OK:
        return rc

    # --- Step 3: Script brief ---
    print()
    brief_args = argparse.Namespace(video_id=args.video_id)
    rc = cmd_script_brief(brief_args)
    if rc != EXIT_OK:
        return rc

    # --- Done: signal human needed ---
    notify_action_required(
        args.video_id, "script",
        "Brief ready — write script_raw.txt",
        next_action=(
            f"Write script in {paths.script_raw}, then run: "
            f"python3 tools/pipeline.py script-review --video-id {args.video_id}"
        ),
    )

    print(f"\n{'=' * 50}")
    print(f"  Day pipeline complete — human needed")
    print(f"{'=' * 50}")
    print(f"\n  Brief: {paths.manual_brief}")
    print(f"  Write: {paths.script_raw}")
    print(f"\n  Then:  python3 tools/pipeline.py script-review --video-id {args.video_id}")

    return EXIT_ACTION_REQUIRED


def cmd_status(args) -> int:
    """Show pipeline status for one or all videos."""
    from tools.lib.pipeline_status import format_status_text, get_status
    from tools.lib.video_paths import VIDEOS_BASE

    if args.all:
        # List all video projects
        if not VIDEOS_BASE.is_dir():
            print("No videos found.")
            return EXIT_OK

        video_dirs = sorted(
            d for d in VIDEOS_BASE.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

        if not video_dirs:
            print("No video projects found.")
            return EXIT_OK

        print(f"Found {len(video_dirs)} video project(s):\n")
        has_action = False
        for vd in video_dirs:
            vid = vd.name
            status = get_status(vid)
            stage = status.stage or "not started"
            milestone = status.milestone or "-"
            mark = "done" if status.completed_at else stage
            print(f"  {vid:30s}  {mark:15s}  {milestone}")
            if not status.completed_at and status.started_at:
                has_action = True

        return EXIT_ACTION_REQUIRED if has_action else EXIT_OK

    # Single video status
    if not args.video_id:
        print("Error: --video-id or --all required")
        return EXIT_ERROR

    _print_header(f"Status: {args.video_id}")

    paths = VideoPaths(args.video_id)

    # Filesystem checks
    checks = [
        ("inputs/products.json", paths.products_json.is_file()),
        ("inputs/niche.txt", paths.niche_txt.is_file()),
        ("script/script.txt", paths.script_txt.is_file()),
        ("script/prompts/", paths.prompts_dir.is_dir() and any(paths.prompts_dir.iterdir()) if paths.prompts_dir.is_dir() else False),
        ("assets/dzine/thumbnail.png", paths.thumbnail_path().is_file()),
    ]

    # Check product images (variant-aware)
    from tools.lib.dzine_schema import variants_for_rank
    for rank in [5, 4, 3, 2, 1]:
        expected = variants_for_rank(rank)
        present = [v for v in expected if paths.product_image_path(rank, v).is_file()]
        missing_v = [v for v in expected if v not in present]
        if missing_v:
            checks.append((f"  product {rank:02d}: {len(present)}/{len(expected)} variants (missing: {', '.join(missing_v)})", False))
        else:
            checks.append((f"  product {rank:02d}: {len(present)}/{len(expected)} variants", True))

    # Check audio chunks
    chunk_count = 0
    if paths.audio_chunks.is_dir():
        chunk_count = len([f for f in paths.audio_chunks.glob("*.mp3") if not f.stem.startswith("micro_")])
    checks.append((f"audio/voice/chunks/ ({chunk_count} chunks)", chunk_count > 0))

    # Check resolve outputs
    checks.append(("resolve/edit_manifest.json", (paths.resolve_dir / "edit_manifest.json").is_file()))
    checks.append(("resolve/markers.csv", (paths.resolve_dir / "markers.csv").is_file()))
    checks.append(("resolve/markers.edl", (paths.resolve_dir / "markers.edl").is_file()))
    checks.append(("resolve/notes.md", (paths.resolve_dir / "notes.md").is_file()))

    print("Files:")
    for label, present in checks:
        mark = "[x]" if present else "[ ]"
        print(f"  {mark} {label}")

    # Pipeline status
    print()
    print(format_status_text(args.video_id))

    # Determine next action
    has_errors = False
    needs_action = False
    for _, present in checks:
        if not present:
            needs_action = True

    if has_errors:
        return EXIT_ERROR
    if needs_action:
        return EXIT_ACTION_REQUIRED
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rayviews production pipeline orchestrator",
    )
    sub = parser.add_subparsers(dest="command", help="Pipeline stage to run")

    # init
    p_init = sub.add_parser("init", help="Initialize a new video project")
    p_init.add_argument("--video-id", required=True, help="Unique video identifier")
    p_init.add_argument("--niche", required=True, help="Product niche")
    p_init.add_argument("--force", action="store_true", help="Reinitialize existing project")

    # research
    p_res = sub.add_parser("research", help="Run evidence-first research pipeline")
    p_res.add_argument("--video-id", required=True)
    p_res.add_argument("--mode", choices=("run", "build"), default="run",
                        help="run (default): execute full pipeline. build: validate only.")
    p_res.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without doing it")
    p_res.add_argument("--force", action="store_true",
                        help="Force re-run even if intermediate files exist")

    # script
    p_script = sub.add_parser("script", help="Generate script prompts / validate script")
    p_script.add_argument("--video-id", required=True)
    p_script.add_argument(
        "--charismatic", default="reality_check",
        choices=("reality_check", "micro_humor", "micro_comparison"),
        help="Charismatic signature type",
    )
    p_script.add_argument(
        "--generate", action="store_true",
        help="Auto-generate script via OpenAI (draft) + Anthropic (refinement)",
    )
    p_script.add_argument("--force", action="store_true", help="Regenerate even if script exists")

    # script-brief
    p_brief = sub.add_parser("script-brief", help="Generate structured manual brief for script writing")
    p_brief.add_argument("--video-id", required=True)

    # script-review
    p_review = sub.add_parser("script-review", help="Review script_raw.txt: validate, check claims, light fixes")
    p_review.add_argument("--video-id", required=True)

    # assets
    p_assets = sub.add_parser("assets", help="Check/generate Dzine assets")
    p_assets.add_argument("--video-id", required=True)
    p_assets.add_argument("--force", action="store_true", help="Regenerate all assets")
    p_assets.add_argument("--dry-run", action="store_true", help="Show status only")

    # tts
    p_tts = sub.add_parser("tts", help="Generate TTS voiceover")
    p_tts.add_argument("--video-id", required=True)
    p_tts.add_argument("--force", action="store_true", help="Regenerate all chunks")
    p_tts.add_argument("--patch", type=int, nargs="+", help="Regenerate specific chunk indices")

    # broll-plan
    p_broll = sub.add_parser("broll-plan", help="Generate B-roll search plan from products")
    p_broll.add_argument("--video-id", required=True)

    # manifest
    p_man = sub.add_parser("manifest", help="Generate Resolve edit manifest")
    p_man.add_argument("--video-id", required=True)

    # day (daily pipeline)
    p_day = sub.add_parser("day", help="Daily pipeline: init -> research -> script-brief (stops for human)")
    p_day.add_argument("--video-id", required=True)
    p_day.add_argument("--niche", default="", help="Product niche (auto-picked if empty)")
    p_day.add_argument("--force", action="store_true", help="Force re-run all stages")

    # run (full orchestrator)
    p_run = sub.add_parser("run", help="Run full pipeline via multi-agent orchestrator")
    p_run.add_argument("--video-id", required=True)
    p_run.add_argument("--niche", default="", help="Product niche (auto-picked if empty)")
    p_run.add_argument("--stage", default="", help="Start from this stage")
    p_run.add_argument("--stop-after", default="", help="Stop after this stage")
    p_run.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    p_run.add_argument("--force", action="store_true", help="Force re-run all stages")

    # status
    p_stat = sub.add_parser("status", help="Show pipeline status")
    p_stat.add_argument("--video-id", default="")
    p_stat.add_argument("--all", action="store_true", help="Show all video projects")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return EXIT_ERROR

    commands = {
        "init": cmd_init,
        "research": cmd_research,
        "script": cmd_script,
        "script-brief": cmd_script_brief,
        "script-review": cmd_script_review,
        "assets": cmd_assets,
        "tts": cmd_tts,
        "broll-plan": cmd_broll_plan,
        "manifest": cmd_manifest,
        "day": cmd_day,
        "run": cmd_run,
        "status": cmd_status,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
