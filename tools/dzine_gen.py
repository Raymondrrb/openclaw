#!/usr/bin/env python3
"""CLI entry point for Dzine image generation.

Amazon Associates product ranking channel — visual asset generator.

Usage:
    python3 tools/dzine_gen.py --asset-type thumbnail --product-name "Product Name" --key-message "Top Pick" --dry-run
    python3 tools/dzine_gen.py --asset-type product --product-name "Product Name" --reference-image ./photos/product.png
    python3 tools/dzine_gen.py --asset-type background
    python3 tools/dzine_gen.py --asset-type avatar_base
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
    STYLES,
    DzineRequest,
    build_prompts,
    validate_request,
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
        "--product-name", default="",
        help="Product name (required for thumbnail/product)",
    )
    parser.add_argument(
        "--key-message", default="",
        help="Headline text, max 4 words (required for thumbnail)",
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
        print(f"Asset type:  {req.asset_type}")
        print(f"Product:     {req.product_name}")
        print(f"Style:       {req.style}")
        print(f"Resolution:  {req.width}x{req.height}")
        if req.reference_image:
            print(f"Reference:   {req.reference_image}")
        print(f"\nPrompt:\n{req.prompt}")
        print(f"\nNegative prompt:\n{req.negative_prompt}")
        return 0

    # Generate via Playwright
    from tools.lib.dzine_browser import generate_image

    # Derive video_id from --product-name or asset_type for milestone tracking
    video_id = req.product_name.lower().replace(" ", "-")[:30] if req.product_name else req.asset_type

    print(f"Generating {req.asset_type} image ({req.width}x{req.height})...")
    if req.reference_image:
        print(f"Using reference: {req.reference_image}")

    update_milestone(video_id, "assets", f"{req.asset_type}_started")
    result = generate_image(req)

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
