#!/usr/bin/env python3
"""CLI entry point for Dzine image generation.

Amazon Associates product ranking channel — visual asset generator.

Usage:
    # Single image
    python3 tools/dzine_gen.py --asset-type thumbnail --product-name "Product Name" --key-message "Top Pick" --dry-run
    python3 tools/dzine_gen.py --asset-type product --product-name "Product Name" --rank 1 --variant hero --niche "wireless earbuds"
    python3 tools/dzine_gen.py --asset-type background --niche "air fryers"
    python3 tools/dzine_gen.py --asset-type avatar_base

    # Full video set
    python3 tools/dzine_gen.py --asset-type product --video-id 20260213 --all-variants
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path for imports
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import load_env_file, project_root
from tools.lib.notify import notify_error, notify_progress
from tools.lib.pipeline_status import update_milestone
from tools.lib.dzine_schema import (
    ASSET_TYPES,
    IMAGE_VARIANTS,
    STYLES,
    DzineRequest,
    build_prompts,
    detect_category,
    validate_request,
    variants_for_rank,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate images via Dzine browser automation (Amazon Associates visual system)"
    )
    parser.add_argument(
        "--asset-type", required=True, choices=ASSET_TYPES,
        help="Type of asset to generate",
    )
    parser.add_argument(
        "--video-id", default="",
        help="Video identifier (for file paths and tracking)",
    )
    parser.add_argument(
        "--product-name", default="",
        help="Product name (required for thumbnail/product)",
    )
    parser.add_argument(
        "--key-message", default="",
        help="Headline text, max 4 words (required for thumbnail)",
    )
    parser.add_argument(
        "--rank", type=int, default=0,
        help="Product rank 1-5 (for product images)",
    )
    parser.add_argument(
        "--variant", default="", choices=("", *IMAGE_VARIANTS),
        help="Image variant: hero, usage1, usage2, detail, mood",
    )
    parser.add_argument(
        "--niche", default="",
        help="Niche keyword for category detection (e.g., 'wireless earbuds')",
    )
    parser.add_argument(
        "--all-variants", action="store_true",
        help="Generate all variants for the given rank (uses variants_for_rank)",
    )
    parser.add_argument(
        "--style", default="photorealistic", choices=STYLES,
        help="Visual style (default: photorealistic)",
    )
    parser.add_argument(
        "--width", type=int, default=0,
        help="Width in px (0 = use default for asset type)",
    )
    parser.add_argument(
        "--height", type=int, default=0,
        help="Height in px (0 = use default for asset type)",
    )
    parser.add_argument(
        "--reference-image", default=None,
        help="Path to real product photo to use as reference in Dzine",
    )
    parser.add_argument(
        "--prompt-override", default=None,
        help="Override the template prompt entirely",
    )
    parser.add_argument("--skip-upload", action="store_true", help="Skip Supabase upload")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts and exit")
    args = parser.parse_args()

    # Load env files
    load_env_file(project_root() / ".env")
    load_env_file(Path.home() / ".config" / "newproject" / "dzine.env")

    # Determine category from niche
    category = detect_category(args.niche) if args.niche else ""

    # Multi-variant mode
    if args.all_variants and args.rank > 0:
        return _generate_all_variants(args, category)

    # Build request
    req = DzineRequest(
        asset_type=args.asset_type,
        product_name=args.product_name,
        key_message=args.key_message,
        style=args.style,
        width=args.width,
        height=args.height,
        prompt_override=args.prompt_override,
        reference_image=args.reference_image,
        image_variant=args.variant,
        niche_category=category,
    )

    # Validate
    errors = validate_request(req)
    if errors:
        for err in errors:
            print(f"Validation error: {err}", file=sys.stderr)
        return 2

    # Build prompts from templates
    req = build_prompts(req)

    # Dry run: print and exit
    if args.dry_run:
        _print_request(req, args)
        return 0

    # Determine output path
    output_path = _resolve_output_path(args, req)

    # Generate via Playwright
    video_id = args.video_id or (req.product_name.lower().replace(" ", "-")[:30] if req.product_name else req.asset_type)

    # Route product_faithful to the specialized workflow
    if args.asset_type == "product_faithful":
        if not args.reference_image:
            print("product_faithful requires --reference-image (Amazon product photo)", file=sys.stderr)
            return 2
        from tools.lib.dzine_browser import generate_product_faithful
        print(f"Generating product-faithful image from: {args.reference_image}")
        update_milestone(video_id, "assets", "product_faithful_started")
        result = generate_product_faithful(
            args.reference_image,
            output_path=output_path,
            backdrop_prompt=args.prompt_override or "Clean white studio backdrop with soft professional lighting, subtle shadow underneath product",
        )
    else:
        from tools.lib.dzine_browser import generate_image
        print(f"Generating {req.asset_type} image ({req.width}x{req.height})...")
        if req.image_variant:
            print(f"  Variant: {req.image_variant}")
        if req.reference_image:
            print(f"  Reference: {req.reference_image}")

        update_milestone(video_id, "assets", f"{req.asset_type}_started")
        result = generate_image(req, output_path=output_path)

    if not result.success:
        print(f"Generation failed: {result.error}", file=sys.stderr)
        notify_error(
            video_id, "assets", f"{req.asset_type}_generation",
            result.error,
            next_action=f"Fix issue and retry: dzine_gen --asset-type {req.asset_type}",
        )
        _log_result(req, result, skip_upload=True)
        return 1

    print(f"Generated: {result.local_path} ({result.duration_s:.1f}s)")
    print(f"SHA-256:   {result.checksum_sha256}")
    if result.retries_used > 0:
        print(f"Retries:   {result.retries_used}")

    milestone = f"{req.asset_type}_done"
    update_milestone(video_id, "assets", milestone)
    notify_progress(
        video_id, "assets", milestone,
        next_action="Continue with remaining assets",
        details=[f"{req.asset_type} generated in {result.duration_s:.0f}s"],
    )

    _log_result(req, result, skip_upload=args.skip_upload)

    full_path = Path(result.local_path).resolve()
    print(f"\nMEDIA: {full_path}")
    return 0


def _generate_all_variants(args, category: str) -> int:
    """Generate all variants for a given rank."""
    from tools.lib.dzine_browser import generate_image
    from tools.lib.video_paths import VideoPaths

    variants = variants_for_rank(args.rank)
    video_id = args.video_id or f"rank{args.rank}"
    vp = VideoPaths(video_id) if args.video_id else None

    print(f"Generating {len(variants)} variants for rank #{args.rank}: {', '.join(variants)}")

    success_count = 0
    fail_count = 0

    for variant in variants:
        req = DzineRequest(
            asset_type="product",
            product_name=args.product_name,
            style=args.style,
            image_variant=variant,
            niche_category=category,
            reference_image=args.reference_image,
            prompt_override=args.prompt_override,
        )
        req = build_prompts(req)

        if args.dry_run:
            print(f"\n--- {variant} ---")
            _print_request(req, args)
            continue

        output_path = vp.product_image_path(args.rank, variant) if vp else None
        print(f"\nGenerating {variant} for rank #{args.rank}...")

        result = generate_image(req, output_path=output_path)

        if result.success:
            success_count += 1
            print(f"  OK: {result.local_path} ({result.duration_s:.1f}s)")
        else:
            fail_count += 1
            print(f"  FAIL: {result.error}", file=sys.stderr)

    if args.dry_run:
        return 0

    print(f"\nDone: {success_count} success, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def _print_request(req: DzineRequest, args) -> None:
    """Print request details for dry run."""
    print(f"Asset type:  {req.asset_type}")
    print(f"Product:     {req.product_name}")
    if req.image_variant:
        print(f"Variant:     {req.image_variant}")
    if req.niche_category:
        print(f"Category:    {req.niche_category}")
    print(f"Style:       {req.style}")
    print(f"Resolution:  {req.width}x{req.height}")
    if req.reference_image:
        print(f"Reference:   {req.reference_image}")
    print(f"\nPrompt:\n{req.prompt}")
    print(f"\nNegative prompt:\n{req.negative_prompt}")


def _resolve_output_path(args, req: DzineRequest) -> Path | None:
    """Determine output path based on video_id, rank, and variant."""
    if args.video_id:
        from tools.lib.video_paths import VideoPaths
        vp = VideoPaths(args.video_id)
        vp.ensure_dirs()

        if req.asset_type == "thumbnail":
            return vp.thumbnail_path()
        if req.asset_type == "product" and args.rank > 0:
            return vp.product_image_path(args.rank, req.image_variant or "hero")
    return None


def _log_result(req: DzineRequest, result, *, skip_upload: bool) -> None:
    """Upload to Supabase Storage and log the generation."""
    from tools.lib.supabase_storage import log_generation, upload_to_storage

    storage_url = ""
    if result.success and not skip_upload:
        try:
            remote_name = Path(result.local_path).name
            storage_url = upload_to_storage(result.local_path, remote_name)
            print(f"Uploaded:  {storage_url}")
        except Exception as exc:
            print(f"Upload failed (continuing): {exc}", file=sys.stderr)

    try:
        log_generation(
            asset_type=req.asset_type,
            product_name=req.product_name,
            style=req.style,
            status="success" if result.success else "failed",
            local_path=result.local_path,
            storage_url=storage_url,
            checksum_sha256=result.checksum_sha256,
            duration_s=result.duration_s,
            error=result.error,
            prompt_character=req.prompt,
            prompt_scene="",
            width=req.width,
            height=req.height,
        )
    except Exception as exc:
        print(f"Logging failed (continuing): {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
