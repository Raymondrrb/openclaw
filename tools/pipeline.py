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
from tools.lib.error_log import log_error as _log_error
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
        update_history(
            niche, today, video_id=args.video_id,
            category=candidate.category, subcategory=candidate.subcategory,
            intent=candidate.intent,
        )
        print(f"  Niche: {niche}")
        print(f"  Score: {candidate.static_score:.0f} (static) + rotation bonus")
        print(f"  Intent: {candidate.intent} | Band: {candidate.price_band}")
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
    # Preflight check (research uses browser for page fetching)
    from tools.lib.preflight import preflight_check as _pf_check
    pf = _pf_check("research")
    if not pf.passed:
        for f in pf.failures:
            print(f"  Preflight: {f}", file=sys.stderr)

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
            _log_error(args.video_id, "research", report.validation_errors[0],
                       exit_code=2, context={"command": "research"})
            notify_action_required(
                args.video_id, "research",
                f"Research incomplete: {report.validation_errors[0]}",
                next_action="Review research_report.md and re-run or add sources manually",
            )
            return EXIT_ACTION_REQUIRED

    if not shortlist:
        print("\n  No candidates found.")
        _log_error(args.video_id, "research", "Empty shortlist",
                   exit_code=2, context={"command": "research"})
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

        # Build shortlist lookup to enrich verified products with research data
        _sl_lookup = {s.get("product_name", "").lower(): s for s in shortlist}

        verified = []
        for v in verified_objs:
            sl = _sl_lookup.get(v.product_name.lower(), {})

            # Build evidence with reasons from shortlist research
            evidence_enriched = []
            ebs = sl.get("evidence_by_source", {})
            for src in v.evidence or sl.get("sources", []):
                src_copy = dict(src)
                src_name = src.get("name", "").lower()
                # Merge reasons from evidence_by_source
                if not src_copy.get("reasons") and src_name in ebs:
                    src_copy["reasons"] = ebs[src_name].get("key_claims", [])
                if not src_copy.get("reasons"):
                    src_copy["reasons"] = sl.get("reasons", [])
                evidence_enriched.append(src_copy)

            # Build key_claims from evidence_by_source
            key_claims = v.key_claims or []
            if not key_claims:
                for src_data in ebs.values():
                    key_claims.extend(src_data.get("key_claims", []))

            verified.append({
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
                "evidence": evidence_enriched,
                "key_claims": key_claims,
                "downside": sl.get("downside", ""),
            })
        write_verified(verified_objs, verified_path)
        print(f"  Verified: {len(verified)}/{len(shortlist)}")

    if not verified:
        print("\n  No products verified on Amazon US.")
        _log_error(args.video_id, "research", "No verified products",
                   exit_code=2, context={"command": "research"})
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

    # Supabase: save top 5 products
    try:
        from tools.lib.supabase_pipeline import ensure_run_id, save_top5_product
        rid = ensure_run_id(args.video_id, "research")
        if rid:
            for p in top5:
                save_top5_product(rid,
                                  rank=p.get("rank", 0),
                                  asin=p.get("asin", ""),
                                  role_label=p.get("category_label", ""),
                                  benefits=p.get("benefits", []),
                                  downside=p.get("downside", ""),
                                  affiliate_short_url=p.get("affiliate_short_url", ""))
    except Exception:
        pass

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

    # --- Approval gate: Top 5 products ---
    from tools.lib.pipeline_approval import request_approval

    no_approval = getattr(args, "no_approval", False)
    detail_lines = [f"Niche: {niche}"]
    for p in top5:
        detail_lines.append(
            f"  #{p['rank']} {p.get('product_name', '?')}"
            f" - {p.get('amazon_price', '?')}"
            f" ({p.get('amazon_rating', '?')}*)"
            f" [{p.get('category_label', '?')}]"
        )
    detail_lines.append("")
    detail_lines.append("Products saved. Reject to edit products.json.")

    approved = request_approval(
        "products", f"Top 5 for '{niche}'", detail_lines,
        video_id=args.video_id, skip=no_approval,
    )
    if not approved:
        print("\nProducts rejected/timed out. Edit products.json and re-run.")
        return EXIT_ACTION_REQUIRED

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
        _log_error(video_id, "research", errors[0],
                   context={"command": "research", "mode": "build"})
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
    generate = getattr(args, "generate", True)
    force = getattr(args, "force", False)

    # Load products
    products = _load_products(paths)
    if products is None:
        print(f"products.json not found: {paths.products_json}")
        print(f"\nNext: python3 tools/pipeline.py research --video-id {args.video_id}")
        return EXIT_ACTION_REQUIRED

    # Validate product data quality before script generation
    from tools.lib.amazon_research import validate_products
    product_errors = validate_products(products)
    if product_errors:
        print("Products not ready for script generation:")
        for e in product_errors:
            print(f"  - {e}")
        print(f"\nFix products first: python3 tools/pipeline.py research --video-id {args.video_id}")
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
            no_approval=getattr(args, "no_approval", False),
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
    *,
    no_approval: bool = False,
) -> int:
    """Auto-generate script via OpenAI (draft) + Anthropic (refinement)."""
    import os
    from tools.lib.script_generate import run_script_pipeline
    from tools.lib.script_schema import build_refinement_prompt
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress, notify_error

    # Check API keys and browser mode
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    use_browser = os.environ.get("OPENCLAW_BROWSER_LLM", "") == "1" or (
        not openai_key and not anthropic_key
    )

    if use_browser:
        print("Browser LLM mode: will use logged-in Brave sessions")
        if openai_key or anthropic_key:
            print("  (API keys available as fallback)")
    elif not openai_key:
        print("OPENAI_API_KEY not set — will try browser for draft")
        use_browser = True

    skip_refine = not anthropic_key and not use_browser
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
        use_browser=use_browser,
    )

    if not result.success:
        for err in result.errors:
            print(f"  Error: {err}")
        _log_error(video_id, "script",
                   result.errors[0] if result.errors else "Script generation failed",
                   context={"command": "script", "mode": "generate"})
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

    # --- Approval gate: Script ---
    from tools.lib.pipeline_approval import request_approval

    wc = result.word_count
    dur = f"{wc / 150:.1f}"
    script_detail_lines = [
        f"Words: {wc}",
        f"Duration: ~{dur} min",
        f"Charismatic: {charismatic}",
        f"Path: {result.script_txt_path}",
        "",
        "Script saved. Reject to edit script.txt.",
    ]
    approved = request_approval(
        "script", f"Script ({wc} words)", script_detail_lines,
        video_id=video_id, skip=no_approval,
    )
    if not approved:
        print("\nScript rejected/timed out. Edit script.txt and re-run.")
        return EXIT_ACTION_REQUIRED

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
    from tools.lib.script_generate import (
        _match_marker,
        extract_metadata,
        extract_script_body,
        split_script_outputs,
    )
    from tools.lib.script_schema import (
        SECTION_ORDER,
        SPEAKING_WPM,
        ScriptOutput,
        ScriptSection,
        validate_script,
    )

    raw_text = paths.script_txt.read_text(encoding="utf-8")
    # Extract clean script body (normalizes markers + strips metadata)
    text = extract_script_body(raw_text)
    # Extract metadata — try script_final.txt first (has full LLM output),
    # then fall back to script.txt (metadata may have been stripped)
    meta_source = raw_text
    if paths.script_final.is_file():
        meta_source = paths.script_final.read_text(encoding="utf-8")
    meta = extract_metadata(meta_source)

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
        matched = _match_marker(line)
        if matched and matched in marker_map:
            if current_key:
                sections.append(ScriptSection(
                    section_type=current_key,
                    content="\n".join(current_lines).strip(),
                ))
            current_key = marker_map[matched]
            current_lines = []
        elif current_key:
            current_lines.append(line)

    if current_key:
        sections.append(ScriptSection(
            section_type=current_key,
            content="\n".join(current_lines).strip(),
        ))

    # If avatar_intro is in metadata but missing from body sections,
    # insert a placeholder section after hook (browser LLMs put it as metadata)
    section_types = [s.section_type for s in sections]
    if "avatar_intro" not in section_types and meta.get("avatar_intro"):
        hook_idx = section_types.index("hook") + 1 if "hook" in section_types else 0
        sections.insert(hook_idx, ScriptSection(
            section_type="avatar_intro",
            content="(avatar intro — see metadata)",
        ))

    output = ScriptOutput(
        sections=sections,
        avatar_intro=meta.get("avatar_intro", ""),
        youtube_description=meta.get("youtube_description", ""),
        thumbnail_headlines=meta.get("thumbnail_headlines", []),
    )
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

    # Write split outputs: narration.txt, avatar.txt, youtube_desc.txt
    outputs = split_script_outputs(text, {
        "avatar_intro": output.avatar_intro,
        "youtube_description": output.youtube_description,
    })
    paths.narration_txt.write_text(outputs["narration"], encoding="utf-8")
    paths.avatar_txt.write_text(outputs["avatar"], encoding="utf-8")
    paths.youtube_desc_txt.write_text(outputs["youtube_description"], encoding="utf-8")
    print(f"  Split outputs: narration.txt, avatar.txt, youtube_desc.txt")

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

    # Supabase: save brief
    try:
        from tools.lib.supabase_pipeline import ensure_run_id, save_script
        rid = ensure_run_id(args.video_id, "script-brief")
        if rid:
            wc = len(brief_text.split())
            save_script(rid, "brief", text=brief_text, word_count=wc)
    except Exception:
        pass

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

    # Supabase: save review + final
    try:
        from tools.lib.supabase_pipeline import ensure_run_id as _ensure_rid, save_script as _save_scr
        _rid = _ensure_rid(args.video_id, "script-review")
        if _rid:
            _save_scr(_rid, "review", text=notes, word_count=result.word_count)
            _save_scr(_rid, "final", text=fixed_text, word_count=result.word_count,
                       has_disclosure=result.has_disclosure if hasattr(result, "has_disclosure") else False)
    except Exception:
        pass

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

        # Preflight session check: Brave + Dzine login
        from tools.lib.preflight import preflight_check as _pf_check_assets
        pf = _pf_check_assets("assets")
        if not pf.passed:
            for f in pf.failures:
                print(f"Preflight: {f}")
            notify_action_required(args.video_id, "assets", pf.failures[0],
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

    # Load variant-specific prompts from skill graph (detailed, scene-specific).
    # Falls back to inline defaults if skill graph is unavailable.
    _BACKDROP_PROMPTS_FALLBACK = {
        "hero": "Premium dark matte surface with subtle reflections. Professional studio environment with three-point lighting: soft key light from 45-degree upper left, subtle fill from right, rim light highlighting product edges. Dark gradient background transitioning from charcoal to deep navy. Clean minimalist composition with dramatic cast shadow underneath. High-end e-commerce aesthetic.",
        "usage1": "Modern living room with warm oak hardwood flooring. Beige fabric sofa in soft-focus background, indoor potted plants in terracotta pots. Natural afternoon sunlight streaming through large floor-to-ceiling windows from the left, creating warm golden tones and soft natural shadows. Scandinavian minimalist interior, clean and inviting atmosphere. Low-angle perspective at 15 degrees above floor level. Shallow depth of field with softly blurred background.",
        "usage2": "Bright contemporary kitchen with white subway tile backsplash and marble countertops visible in soft-focus background. Polished medium-brown hardwood floor with warm tones. Morning sunlight from side window creating soft diffused illumination and gentle shadows. Clean modern aesthetic with stainless steel appliances blurred in background. 45-degree diagonal angle showing product in kitchen context.",
        "detail": "Pure white seamless studio surface. Soft even diffused lighting from two large softboxes positioned above and to the sides. Minimal shadows, bright and clean high-key environment. Professional e-commerce product photography setup. Neutral, clinical, technical aesthetic. Top-down 90-degree overhead perspective for maximum detail visibility.",
        "mood": "Dramatic industrial environment with polished concrete floor showing visible texture. Exposed brick wall with dark teal color grading in background. Single spotlight from upper left creating strong directional light and deep shadows. Atmospheric haze or light fog adding depth layers. Volumetric light rays visible in the air. Low-key cinematic lighting with warm amber key light and cool blue fill. Film noir aesthetic.",
    }

    def _get_backdrop_prompt(variant: str) -> str:
        """Load prompt from skill graph, fall back to inline defaults."""
        try:
            from tools.lib.skill_graph import get_variant_prompt
            prompt = get_variant_prompt(variant, "product-background")
            if prompt:
                return prompt
        except Exception:
            pass
        return _BACKDROP_PROMPTS_FALLBACK.get(variant, _BACKDROP_PROMPTS_FALLBACK["hero"])

    # Pre-run check: warn about known issues with current tool
    try:
        from tools.lib.skill_graph import pre_run_check
        warnings = pre_run_check("product-background")
        for w in warnings:
            print(f"  [skill-graph] {w}")
    except Exception:
        pass

    import random as _rng
    import time as _time

    for i, (label, dest_path, params) in enumerate(targets):
        # Anti-bot: random delay between generations (skip first)
        if i > 0:
            delay = _rng.uniform(3.0, 8.0)
            print(f"  (waiting {delay:.1f}s between generations)")
            _time.sleep(delay)

        print(f"\nGenerating {label} ({i+1}/{len(targets)})...")

        # Add reference image if available for product variants
        is_thumbnail = label == "thumbnail"
        if not is_thumbnail:
            rank = int(label.split("_")[0])
            variant = label.split("_", 1)[1]
            if rank in ref_images:
                params["reference_image"] = str(ref_images[rank])

        # Product variants with reference images → use product_faithful
        # (Product Background preferred, fallback to BG Remove + Expand)
        use_faithful = (not is_thumbnail
                        and params.get("reference_image")
                        and Path(params["reference_image"]).is_file())

        if use_faithful:
            from tools.lib.dzine_browser import generate_product_faithful
            ref_path = params["reference_image"]
            backdrop = _get_backdrop_prompt(variant)
            aspect = "1:1" if variant == "detail" else "16:9"

            # Save backdrop prompt
            prompt_path = paths.product_prompt_path(rank, variant)
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(f"[product_faithful] backdrop: {backdrop}", encoding="utf-8")

            result = generate_product_faithful(
                ref_path,
                output_path=dest_path,
                backdrop_prompt=backdrop,
                aspect=aspect,
            )

            if not result.success:
                print(f"  Retry {label} (faithful)...")
                result = generate_product_faithful(
                    ref_path,
                    output_path=dest_path,
                    backdrop_prompt=backdrop,
                    aspect=aspect,
                )
        else:
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
            # Supabase: upload + save asset
            try:
                from tools.lib.supabase_pipeline import (
                    ensure_run_id as _erid, upload_video_file as _uvf, save_asset as _sa,
                )
                _asset_rid = _erid(args.video_id, "assets")
                if _asset_rid:
                    s_url = _uvf(args.video_id, "rayviewslab-assets", str(dest_path), f"assets/{label}.png")
                    _sa(_asset_rid, asset_type=label, storage_url=s_url, ok=True)
            except Exception:
                pass
        elif result.success and dest_path.is_file():
            size_kb = dest_path.stat().st_size // 1024
            print(f"  Warning: {dest_path.name} too small ({size_kb} KB)")
            failed += 1
        else:
            print(f"  FAILED: {result.error}")
            failed += 1
            if "login" in (result.error or "").lower():
                _log_error(args.video_id, "assets", "Dzine login required",
                           exit_code=2, context={"command": "assets"})
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

    # --- Image approval gate ---
    from tools.lib.telegram_image_approval import request_image_approval, ImageEntry
    image_entries = []
    for label, dest_path, params in needed:
        if dest_path.is_file() and dest_path.stat().st_size >= MIN_ASSET_SIZE:
            image_entries.append(ImageEntry(
                label=label,
                path=dest_path,
                product_name=params.get("product_name", label),
                variant=params.get("image_variant", "thumbnail"),
            ))

    if image_entries:
        approval = request_image_approval(image_entries, video_id=args.video_id)
        if approval.rejected:
            print(f"\nRejected: {', '.join(approval.rejected)}")
            notify_action_required(args.video_id, "assets",
                f"{len(approval.rejected)} image(s) rejected",
                next_action="Analyze failures and regenerate")
            return EXIT_ACTION_REQUIRED

    update_milestone(args.video_id, "assets", "product_images_done")

    if failed == 0:
        notify_progress(
            args.video_id, "assets", "product_images_done",
            progress_done=len(targets), progress_total=len(targets),
            next_action=f"python3 tools/pipeline.py tts --video-id {args.video_id}",
            details=[f"Generated {generated} images, 0 failed"],
        )
    else:
        _log_error(args.video_id, "assets", f"{failed} image(s) failed generation",
                   context={"command": "assets", "generated": generated, "failed": failed})
        notify_action_required(
            args.video_id, "assets",
            f"{failed} image(s) failed generation",
            next_action=f"Re-run: python3 tools/pipeline.py assets --video-id {args.video_id}",
        )

    print(f"\nGenerated: {generated}, Failed: {failed}")
    print(f"\nNext: python3 tools/pipeline.py tts --video-id {args.video_id}")
    return EXIT_OK if failed == 0 else EXIT_ERROR


def cmd_discover_products(args) -> int:
    """Discover Amazon products via browser or scrape."""
    from tools.lib.amazon_research import save_products_json, validate_products
    from tools.lib.notify import notify_progress

    _print_header(f"Discover Products: {args.video_id}")

    paths = VideoPaths(args.video_id)
    paths.ensure_dirs()

    # Determine search keyword
    keyword = args.keyword or _load_niche(paths)
    if not keyword:
        print("No keyword provided and niche.txt not found.")
        print("Use --keyword or run init first.")
        return EXIT_ACTION_REQUIRED

    # Check if products.json already exists
    if paths.products_json.is_file() and not args.force:
        products = _load_products(paths)
        if products:
            print(f"products.json already exists with {len(products)} products.")
            print("Use --force to re-discover.")
            return EXIT_OK

    source = args.source
    top_n = args.top_n
    tag = args.tag

    if source == "browser":
        try:
            from tools.amazon_browser import discover_products_browser, AmazonBrowserError
        except ImportError as exc:
            print(f"Cannot import amazon_browser: {exc}")
            print("Install playwright: pip install playwright && playwright install")
            return EXIT_ERROR

        try:
            products = discover_products_browser(
                keyword=keyword,
                affiliate_tag=tag,
                top_n=top_n,
                min_rating=args.min_rating,
                min_reviews=args.min_reviews,
            )
        except AmazonBrowserError as exc:
            print(f"Browser discovery failed: {exc}")
            _log_error(args.video_id, "discover-products", str(exc),
                       context={"source": source, "keyword": keyword})
            return EXIT_ACTION_REQUIRED
        finally:
            try:
                from tools.amazon_browser import close_session
                close_session()
            except Exception:
                pass

    else:
        # Scrape path: raw HTTP (existing behavior, may hit 403)
        print(f"Source '{source}' not yet implemented. Use --source browser.")
        return EXIT_ERROR

    if not products:
        print(f"No products found for: {keyword}")
        return EXIT_ACTION_REQUIRED

    # Validate
    errors = validate_products(products)
    if errors:
        print(f"Validation warnings:")
        for e in errors:
            print(f"  - {e}")

    # Save
    save_products_json(products, paths.products_json, keyword=keyword)
    print(f"\nSaved {len(products)} products to {paths.products_json}")
    for p in products:
        print(f"  #{p.rank}: {p.name} ({p.price}, {p.rating}* {p.reviews_count} reviews)")

    notify_progress(
        args.video_id, "discover-products", "products_saved",
        details=[f"Discovered {len(products)} products for '{keyword}'"],
    )

    print(f"\nNext: python3 tools/pipeline.py script-brief --video-id {args.video_id}")
    return EXIT_OK


def cmd_generate_images(args) -> int:
    """Generate Dzine images for a video's product set via assets_manifest."""
    from tools.lib.pipeline_status import update_milestone
    from tools.lib.notify import notify_progress, notify_action_required
    from tools.lib.preflight_gate import can_run_assets

    _print_header(f"Generate Images: {args.video_id}")

    # Preflight safety gate
    ok, reason = can_run_assets(args.video_id)
    if not ok:
        print(f"Blocked: {reason}")
        return EXIT_ACTION_REQUIRED

    # Preflight session check: Brave + Dzine login
    from tools.lib.preflight import preflight_check as _pf_check
    pf = _pf_check("assets")
    if not pf.passed:
        for f in pf.failures:
            print(f"Preflight: {f}")
        return EXIT_ACTION_REQUIRED

    paths = VideoPaths(args.video_id)
    products = _load_products(paths)
    if products is None:
        print(f"products.json not found: {paths.products_json}")
        print(f"Run discover-products first.")
        return EXIT_ACTION_REQUIRED

    # Download Amazon reference images (needed for manifest building)
    print("Downloading Amazon reference images...")
    ref_images = _download_amazon_images(products, paths)
    print(f"  {len(ref_images)} reference images available")

    # Generate via manifest-based orchestrator
    try:
        from tools.dzine_browser import generate_all_assets
    except ImportError as exc:
        print(f"Cannot import dzine_browser: {exc}")
        print("Install playwright: pip install playwright && playwright install")
        return EXIT_ERROR

    result = generate_all_assets(
        video_id=args.video_id,
        rebuild=args.rebuild,
        dry_run=args.dry_run,
    )

    generated = result.get("generated", 0)
    failed = result.get("failed", 0)

    if not args.dry_run:
        # --- Image approval gate ---
        from tools.lib.telegram_image_approval import request_image_approval, ImageEntry
        from tools.lib.dzine_schema import variants_for_rank

        MIN_ASSET_SIZE_GEN = 80 * 1024
        image_entries = []
        for rank in [5, 4, 3, 2, 1]:
            p = next((pr for pr in products if pr.rank == rank), None)
            name = p.name if p else f"Product {rank}"
            for variant in variants_for_rank(rank):
                img_path = paths.product_image_path(rank, variant)
                if img_path.is_file() and img_path.stat().st_size >= MIN_ASSET_SIZE_GEN:
                    image_entries.append(ImageEntry(
                        label=f"{rank:02d}_{variant}",
                        path=img_path,
                        product_name=name,
                        variant=variant,
                    ))

        if image_entries:
            approval = request_image_approval(image_entries, video_id=args.video_id)
            if approval.rejected:
                print(f"\nRejected: {', '.join(approval.rejected)}")
                notify_action_required(args.video_id, "generate-images",
                    f"{len(approval.rejected)} image(s) rejected",
                    next_action="Analyze failures and regenerate")
                return EXIT_ACTION_REQUIRED

        update_milestone(args.video_id, "assets", "product_images_done")

        if failed == 0:
            notify_progress(
                args.video_id, "generate-images", "complete",
                details=[f"Generated {generated} images, 0 failed"],
                next_action=f"python3 tools/pipeline.py tts --video-id {args.video_id}",
            )
        else:
            _log_error(args.video_id, "generate-images",
                       f"{failed} image(s) failed generation",
                       context={"generated": generated, "failed": failed})

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

    # Prefer narration.txt (markers stripped, avatar removed) for TTS
    if paths.narration_txt.is_file():
        script_text = paths.narration_txt.read_text(encoding="utf-8")
    else:
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

    # Supabase: upload chunks + save metadata
    try:
        from tools.lib.supabase_pipeline import (
            ensure_run_id as _tts_erid, upload_video_file as _tts_uvf, save_tts_chunk as _tts_save,
        )
        _tts_rid = _tts_erid(args.video_id, "tts")
        if _tts_rid:
            for m in results:
                s_url = ""
                if m.status == "success" and m.file_path:
                    s_url = _tts_uvf(args.video_id, "rayviewslab-audio",
                                     m.file_path, f"chunks/chunk_{m.index:02d}.mp3")
                _tts_save(_tts_rid, chunk_index=m.index, text=getattr(m, "text", ""),
                          storage_url=s_url, ok=(m.status == "success"),
                          error=getattr(m, "error", ""),
                          duration_seconds=getattr(m, "actual_duration_s", 0) or 0)
    except Exception:
        pass

    if failed:
        failed_indices = [m.index for m in results if m.status == "failed"]
        _log_error(args.video_id, "voice", f"{failed} TTS chunk(s) failed",
                   context={"command": "tts", "failed_indices": failed_indices})
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

    # Supabase: upload resolve files
    try:
        from tools.lib.supabase_pipeline import ensure_run_id as _man_erid, upload_video_file as _man_uvf
        _man_rid = _man_erid(args.video_id, "manifest")
        if _man_rid:
            for fname in ["edit_manifest.json", "markers.csv", "markers.edl", "notes.md"]:
                fpath = paths.resolve_dir / fname
                if fpath.is_file():
                    _man_uvf(args.video_id, "rayviewslab-manifests", str(fpath), f"resolve/{fname}")
    except Exception:
        pass

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

    cluster_slug = getattr(args, "cluster", "") or ""

    # --- Step 1: Init if root doesn't exist ---
    if not paths.root.exists() or force:
        if not niche:
            # Try cluster-based selection first
            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            try:
                from tools.cluster_manager import (
                    current_week_monday,
                    load_clusters,
                    pick_cluster,
                    pick_micro_niche,
                    update_cluster_history,
                )
                if cluster_slug:
                    # Force a specific cluster
                    all_clusters = load_clusters()
                    matched = [c for c in all_clusters if c.slug == cluster_slug]
                    if not matched:
                        print(f"Unknown cluster slug: {cluster_slug}")
                        return EXIT_ERROR
                    cluster = matched[0]
                else:
                    cluster = pick_cluster(today)

                week_monday = current_week_monday(today)

                # Get existing video_ids for this week
                from tools.cluster_manager import load_cluster_history
                history = load_cluster_history()
                existing_ids = []
                for entry in history:
                    if entry.week_start == week_monday and entry.cluster_slug == cluster.slug:
                        existing_ids = entry.video_ids
                        break

                micro = pick_micro_niche(cluster, existing_ids)
                niche = micro.intent_phrase

                # Write cluster.txt and micro_niche.json
                paths.ensure_dirs()
                paths.cluster_txt.write_text(
                    f"{cluster.slug}\n", encoding="utf-8",
                )

                import json as _json
                mn_data = {
                    "subcategory": micro.subcategory,
                    "buyer_pain": micro.buyer_pain,
                    "intent_phrase": micro.intent_phrase,
                    "price_min": micro.price_min,
                    "price_max": micro.price_max,
                    "must_have_features": micro.must_have_features,
                    "forbidden_variants": micro.forbidden_variants,
                    "cluster_slug": cluster.slug,
                    "cluster_name": cluster.name,
                }
                paths.micro_niche_json.write_text(
                    _json.dumps(mn_data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

                # Generate subcategory contract from micro-niche
                from tools.lib.subcategory_contract import (
                    generate_contract_from_micro_niche,
                    write_contract,
                )
                contract = generate_contract_from_micro_niche(micro)
                write_contract(contract, paths.subcategory_contract)

                # Update cluster history
                update_cluster_history(cluster.slug, week_monday, args.video_id)

                print(f"Cluster: {cluster.name} ({cluster.slug})")
                print(f"Micro-niche: {micro.subcategory}")
                print(f"Intent: {micro.intent_phrase}")
                print(f"Price: ${micro.price_min}-${micro.price_max}")

            except Exception as exc:
                print(f"Cluster selection failed ({exc}), falling back to niche picker")
                from tools.niche_picker import pick_niche
                candidate = pick_niche(today)
                niche = candidate.keyword
                print(f"Auto-picked niche: {niche} (static: {candidate.static_score:.0f}, intent: {candidate.intent})")

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
    no_approval = getattr(args, "no_approval", False)
    research_args = argparse.Namespace(
        video_id=args.video_id, mode="run", dry_run=False, force=force,
        no_approval=no_approval,
    )
    rc = cmd_research(research_args)
    if rc != EXIT_OK:
        return rc

    # --- Step 3: Script brief (for reference) ---
    print()
    brief_args = argparse.Namespace(video_id=args.video_id)
    rc = cmd_script_brief(brief_args)
    if rc != EXIT_OK:
        return rc

    # --- Step 4: Script (auto-generate) ---
    print()
    script_args = argparse.Namespace(
        video_id=args.video_id, generate=True, force=force,
        charismatic="reality_check",
        no_approval=no_approval,
    )
    rc = cmd_script(script_args)
    if rc != EXIT_OK:
        from tools.lib.notify import notify_action_required
        notify_action_required(
            args.video_id, "script",
            "Script auto-generation failed — write manually",
            next_action=(
                f"Write script in {paths.script_raw}, then run: "
                f"python3 tools/pipeline.py script-review --video-id {args.video_id}"
            ),
        )
        return rc

    print(f"\n{'=' * 50}")
    print(f"  Day pipeline complete — script generated")
    print(f"{'=' * 50}")
    print(f"\n  Script: {paths.script_txt}")
    print(f"\n  Next: Review script.txt, then run:")
    print(f"    python3 tools/pipeline.py assets --video-id {args.video_id}")

    return EXIT_OK


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
# Runs subcommand
# ---------------------------------------------------------------------------


def cmd_runs(args) -> int:
    """Show pipeline run history."""
    from tools.lib.run_log import format_runs_text, get_daily_summary

    if args.summary:
        date = ""
        if args.today:
            from tools.lib.common import now_iso
            date = now_iso()[:10]
        summary = get_daily_summary(date=date)
        if summary["total_runs"] == 0:
            print(f"No runs recorded for {summary['date']}.")
            return EXIT_OK
        print(f"Date: {summary['date']}  |  Runs: {summary['total_runs']}  |  Videos: {', '.join(summary['videos_touched']) or 'none'}")
        for cmd, stats in sorted(summary["by_command"].items()):
            print(f"  {cmd:<15s}  {stats['count']} runs ({stats['ok']} ok, {stats['failed']} failed)  avg {stats['avg_duration_s']:.1f}s")
        return EXIT_OK

    since = ""
    if args.today:
        from tools.lib.common import now_iso
        since = now_iso()[:10]

    text = format_runs_text(
        video_id=args.video_id,
        command=args.filter_command,
        since=since,
    )
    print(text)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Errors subcommand
# ---------------------------------------------------------------------------


def cmd_metrics(args) -> int:
    """Record or view video performance metrics."""
    from tools.lib.video_analytics import record_metrics, get_niche_performance, update_niche_scores

    if args.update_scores:
        print("Recomputing niche performance scores...")
        update_niche_scores()
        print("Done. Scores saved to channel_memory['niche_performance_scores'].")
        return EXIT_OK

    if args.record:
        if not args.video_id:
            print("Error: --video-id required with --record")
            return EXIT_ERROR

        # Parse key=value pairs
        kw: dict = {}
        niche = ""
        if args.video_id:
            niche = _load_niche(VideoPaths(args.video_id))
        for pair in args.data:
            if "=" not in pair:
                print(f"Invalid data format: {pair} (expected key=value)")
                return EXIT_ERROR
            k, v = pair.split("=", 1)
            # Type coercion
            if k in ("views_24h", "views_48h", "views_7d", "views_30d",
                      "avd_seconds", "affiliate_clicks", "conversions"):
                kw[k] = int(v)
            elif k in ("ctr_percent", "avg_view_percent", "rpm_estimate"):
                kw[k] = float(v)
            else:
                kw[k] = v

        record_metrics(args.video_id, niche=niche, **kw)
        print(f"Recorded metrics for {args.video_id}: {kw}")
        return EXIT_OK

    # Show recent performance
    metrics = get_niche_performance(limit=20)
    if not metrics:
        print("No metrics recorded yet.")
        print("Record with: pipeline.py metrics --video-id <id> --record --data views_7d=5000 ctr_percent=5.2")
        return EXIT_OK

    _print_header("Recent Video Metrics")
    for m in metrics:
        vid = m.get("video_id", "?")
        niche = m.get("niche", "?")
        ctr = m.get("ctr", "?")
        v7 = m.get("views_7d", "?")
        ts = m.get("recorded_at", "?")[:10]
        print(f"  {vid:25s} {niche:25s} CTR={ctr}% Views7d={v7} ({ts})")

    return EXIT_OK


def cmd_study(args) -> int:
    """Study a YouTube video — download, analyze, extract knowledge."""
    from tools.video_study import run_study

    _print_header(f"Video Study")
    return run_study(
        url=args.url,
        file_path=args.file_path,
        context=args.context,
        max_frames=args.max_frames,
        frame_strategy=args.frame_strategy,
        video_id_override=getattr(args, "video_id", ""),
    )


def cmd_studies(args) -> int:
    """List or show existing video studies."""
    from tools.video_study import cmd_list, cmd_show

    if hasattr(args, "show_video_id") and args.show_video_id:
        return cmd_show(args.show_video_id, as_json=getattr(args, "json", False))
    return cmd_list()


def cmd_errors(args) -> int:
    """Review cross-video error log."""
    from tools.lib.error_log import (
        resolve_error, get_patterns, format_log_text,
        get_lessons, get_stale,
    )

    if args.resolve:
        root_cause = input("Root cause: ").strip()
        fix = input("Fix applied: ").strip()
        result = resolve_error(args.resolve, root_cause, fix)
        if result:
            print(f"Resolved: {result['id']}")
        else:
            print(f"Error ID not found: {args.resolve}")
            return EXIT_ERROR
        return EXIT_OK

    if args.patterns:
        patterns = get_patterns()
        if not patterns:
            print("No recurring patterns found.")
            return EXIT_OK
        for p in patterns:
            status = f"{p['unresolved']} open" if p['unresolved'] else "all resolved"
            print(
                f"[{p['count']}x] {p['stage']} | {p['pattern']}\n"
                f"       Videos: {', '.join(p['video_ids'])} | "
                f"Last: {p['last_seen'][:19]} | {status}"
            )
        return EXIT_OK

    if args.lessons:
        lessons = get_lessons()
        if not lessons:
            print("No lessons yet (resolve some errors first).")
            return EXIT_OK
        for l in lessons:
            print(
                f"[{l['occurrences']}x] {l['stage']} | {l['pattern']}\n"
                f"       Cause: {l['root_cause']}\n"
                f"       Fix:   {l['fix']}\n"
                f"       Last:  {l['last_resolved'][:19]}"
            )
        return EXIT_OK

    if args.stale:
        stale = get_stale()
        if not stale:
            print("No stale errors (all recent or resolved).")
            return EXIT_OK
        print(f"Stale unresolved errors (>7 days): {len(stale)}\n")
        for e in stale:
            ts = e.get("timestamp", "?")[:19]
            print(
                f"  {e.get('video_id', '?')} | {e.get('stage', '?')} | "
                f"{e.get('error', '?')}\n"
                f"         {ts}  id={e.get('id', '?')}"
            )
        return EXIT_OK

    text = format_log_text(
        stage=args.stage,
        video_id=args.video_id,
        show_resolved=args.all,
    )
    print(text)
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
    p_res.add_argument("--no-approval", action="store_true",
                        help="Skip Telegram approval gates")

    # script
    p_script = sub.add_parser("script", help="Generate script prompts / validate script")
    p_script.add_argument("--video-id", required=True)
    p_script.add_argument(
        "--charismatic", default="reality_check",
        choices=("reality_check", "micro_humor", "micro_comparison"),
        help="Charismatic signature type",
    )
    p_script.add_argument(
        "--generate", action="store_true", default=True,
        help="Auto-generate script via OpenAI (draft) + Anthropic (refinement) [default]",
    )
    p_script.add_argument(
        "--no-generate", action="store_false", dest="generate",
        help="Disable auto-generation, manual mode only",
    )
    p_script.add_argument("--force", action="store_true", help="Regenerate even if script exists")
    p_script.add_argument("--no-approval", action="store_true",
                          help="Skip Telegram approval gates")

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
    p_day.add_argument("--niche", default="", help="Product niche (auto-picked if empty, bypasses cluster)")
    p_day.add_argument("--cluster", default="", help="Force a specific cluster slug")
    p_day.add_argument("--force", action="store_true", help="Force re-run all stages")
    p_day.add_argument("--no-approval", action="store_true",
                       help="Skip Telegram approval gates")

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

    # runs
    p_runs = sub.add_parser("runs", help="Show pipeline run history")
    p_runs.add_argument("--video-id", default="")
    p_runs.add_argument("--cmd", default="", dest="filter_command",
                        help="Filter by pipeline command (e.g. research, script)")
    p_runs.add_argument("--today", action="store_true", help="Filter to today only")
    p_runs.add_argument("--summary", action="store_true", help="Show daily summary")

    # metrics
    p_metrics = sub.add_parser("metrics", help="Record or view video performance metrics")
    p_metrics.add_argument("--video-id", default="")
    p_metrics.add_argument("--record", action="store_true", help="Record metrics for a video")
    p_metrics.add_argument("--data", nargs="+", default=[],
                           help="Key=value pairs: views_7d=5000 ctr_percent=5.2")
    p_metrics.add_argument("--update-scores", action="store_true",
                           help="Recompute niche performance scores")

    # study
    p_study = sub.add_parser("study", help="Study a YouTube video (download, analyze, extract knowledge)")
    p_study.add_argument("--url", default="", help="YouTube video URL")
    p_study.add_argument("--file", default="", dest="file_path", help="Local video file path")
    p_study.add_argument("--context", default="", help="Context hint for analysis")
    p_study.add_argument("--max-frames", type=int, default=80, help="Max frames to extract")
    p_study.add_argument("--frame-strategy", default="scene", choices=("scene", "interval"))
    p_study.add_argument("--video-id", default="", help="Override video ID")

    # studies
    p_studies = sub.add_parser("studies", help="List or show existing video studies")
    p_studies.add_argument("--show", default="", dest="show_video_id", help="Show a specific study")
    p_studies.add_argument("--json", action="store_true", help="Output as JSON")

    # errors
    p_errors = sub.add_parser("errors", help="Review cross-video error log")
    p_errors.add_argument("--stage", default="")
    p_errors.add_argument("--video-id", default="")
    p_errors.add_argument("--all", action="store_true", help="Include resolved")
    p_errors.add_argument("--patterns", action="store_true",
                          help="Show recurring patterns only")
    p_errors.add_argument("--resolve", default="", metavar="ID",
                          help="Mark error resolved")
    p_errors.add_argument("--lessons", action="store_true",
                          help="Show lessons learned from resolved errors")
    p_errors.add_argument("--stale", action="store_true",
                          help="Show unresolved errors older than 7 days")

    # discover-products
    p_discover = sub.add_parser("discover-products",
                                help="Discover Amazon products via browser")
    p_discover.add_argument("--video-id", required=True)
    p_discover.add_argument("--source", default="browser",
                            choices=("browser", "scrape"),
                            help="Discovery method (default: browser)")
    p_discover.add_argument("--keyword", default="",
                            help="Search keyword (default: from niche.txt)")
    p_discover.add_argument("--top-n", type=int, default=5,
                            help="Number of products to discover")
    p_discover.add_argument("--tag", default="",
                            help="Amazon affiliate tag")
    p_discover.add_argument("--min-rating", type=float, default=3.5,
                            help="Minimum product rating")
    p_discover.add_argument("--min-reviews", type=int, default=50,
                            help="Minimum review count")
    p_discover.add_argument("--force", action="store_true",
                            help="Re-discover even if products.json exists")

    # generate-images
    p_genimg = sub.add_parser("generate-images",
                              help="Generate Dzine images for product set")
    p_genimg.add_argument("--video-id", required=True)
    p_genimg.add_argument("--rebuild", action="store_true",
                          help="Rebuild assets_manifest.json from products.json")
    p_genimg.add_argument("--dry-run", action="store_true",
                          help="Show what would be generated without doing it")

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
        "discover-products": cmd_discover_products,
        "generate-images": cmd_generate_images,
        "tts": cmd_tts,
        "broll-plan": cmd_broll_plan,
        "manifest": cmd_manifest,
        "day": cmd_day,
        "run": cmd_run,
        "status": cmd_status,
        "runs": cmd_runs,
        "metrics": cmd_metrics,
        "study": cmd_study,
        "studies": cmd_studies,
        "errors": cmd_errors,
    }

    # Run the command, timing it for the run log
    import time as _time
    _start = _time.monotonic()
    exit_code = commands[args.command](args)
    _duration = _time.monotonic() - _start

    # Log run for commands that operate on a video
    video_id = getattr(args, "video_id", "")
    if video_id:
        try:
            from tools.lib.run_log import log_run
            niche = ""
            niche_path = VideoPaths(video_id).niche_txt
            if niche_path.is_file():
                niche = niche_path.read_text(encoding="utf-8").strip()
            log_run(video_id, args.command, exit_code, round(_duration, 1), niche=niche)
        except Exception:
            pass  # never let logging break the pipeline

        # Supabase: ensure run exists for standalone commands
        try:
            from tools.lib.supabase_pipeline import ensure_run_id
            ensure_run_id(video_id, args.command)
        except Exception:
            pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
